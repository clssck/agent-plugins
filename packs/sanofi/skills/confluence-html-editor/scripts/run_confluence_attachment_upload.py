#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Run the curl upload command returned by createConfluenceAttachment, without a shell.

The Rovo MCP documents only that createConfluenceAttachment returns "a local curl
command"; no structured response schema is published. This helper therefore
takes that command text verbatim, treats it as untrusted data, and runs it only
if it matches a strict upload shape:

- POSIX quoting only: no newline (outside backslash continuations), control
  character, `$`, backtick, or unquoted shell operator (`; & | < > ( )`).
- First word `curl`; options limited to -X/--request POST|PUT, -H/--header,
  -F/--form, --form-string, --data-binary @file, --url, -s, -S, -f, --fail,
  --fail-with-body, -g/--globoff, -m/--max-time, --connect-timeout.
- Exactly one https URL on an atlassian.net or atlassian.com host, no
  credentials in the URL, port 443 only.
- Exactly one file body, resolving to the same regular file as --file.
- Download and redirect options (-o, -O, -L, --output, --location, ...) are
  rejected: downloadConfluenceAttachment is unsupported.

curl runs as an argv list (shell=False) with .curlrc disabled, https-only
protocols, no redirects, and URL globbing off. It reads the already-validated,
open file descriptor through stdin; header values, text form values, URL
queries, and curl response streams are never printed.

Usage: uv run "$(realpath skill://confluence-html-editor/scripts/run_confluence_attachment_upload.py)" --command-file "$(realpath local://attachment-command.txt)" --file /abs/path/diagram.png

Exit codes: 0 curl succeeded; 1 command rejected; 2 unreadable input or invalid
invocation; 3 curl ran and failed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import sys
from typing import BinaryIO
from urllib.parse import urlsplit

ALLOWED_HOST_SUFFIXES = ("atlassian.net", "atlassian.com")
ALLOWED_METHODS = {"POST", "PUT"}
SHELL_OPERATOR_CHARS = set("();<>|&")
FORBIDDEN_HEADERS = {"host", "proxy-authorization", "cookie"}
HEADER_RE = re.compile(r"^([!#%'*+.^_|~0-9A-Za-z-]+):[ \t]*(\S.*)$")
FIELD_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
MIME_RE = re.compile(r"^[A-Za-z0-9!#&^_.+-]+/[A-Za-z0-9!#&^_.+-]+$")
NUMBER_RE = re.compile(r"^\d+(\.\d+)?$")

FLAG_OPTIONS = {
    "-s": "--silent",
    "--silent": "--silent",
    "-S": "--show-error",
    "--show-error": "--show-error",
    "-f": "--fail",
    "--fail": "--fail",
    "--fail-with-body": "--fail-with-body",
    "-g": "--globoff",
    "--globoff": "--globoff",
}
COMBINABLE_SHORT_FLAGS = set("sSfg")
VALUE_OPTIONS = {
    "-X": "method",
    "--request": "method",
    "-H": "header",
    "--header": "header",
    "-F": "form",
    "--form": "form",
    "--form-string": "form_string",
    "--data-binary": "data_binary",
    "--url": "url",
    "-m": "max_time",
    "--max-time": "max_time",
    "--connect-timeout": "connect_timeout",
}
DOWNLOAD_OPTIONS = {
    "-o",
    "--output",
    "-O",
    "--remote-name",
    "--remote-name-all",
    "--output-dir",
    "--create-dirs",
    "-J",
    "--remote-header-name",
    "-G",
    "--get",
}
REDIRECT_OPTIONS = {"-L", "--location", "--location-trusted", "--max-redirs", "--proto-redir"}
ENFORCED_PREFIX = ["-q", "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "0", "--globoff"]


class Rejected(Exception):
    """The command text does not match the supported upload shape."""


class InvalidInput(Exception):
    """Unreadable input or invalid invocation."""


@dataclass
class UploadCommand:
    method: str | None = None
    url: str | None = None
    options: list[str] = field(default_factory=list)
    display: list[str] = field(default_factory=list)
    file_path: str | None = None


def read_command(path: str) -> str:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise InvalidInput(f"cannot read command file: {exc}") from exc
    if not text.strip():
        raise InvalidInput("command file is empty")
    return text


def reject_unquoted_operators(text: str) -> None:
    """Reject shell operators and comments outside quotes; the helper never uses a shell."""
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote == "'":
            if char == "'":
                quote = None
        elif quote == '"':
            if char == "\\":
                index += 1
            elif char == '"':
                quote = None
        elif char == "\\":
            index += 1
        elif char in "'\"":
            quote = char
        elif char in SHELL_OPERATOR_CHARS:
            raise Rejected("shell operator in command; only a single curl command is supported")
        elif char == "#" and (index == 0 or text[index - 1] in " \t"):
            raise Rejected("shell comment in command")
        index += 1


def tokenize(text: str) -> list[str]:
    text = re.sub(r"\\\r?\n[ \t]*", " ", text.strip())
    for char in text:
        if char in "\r\n":
            raise Rejected("newline in command; only a single curl command is supported")
        if (ord(char) < 32 and char != "\t") or ord(char) == 127:
            raise Rejected("control character in command")
    if "$" in text or "`" in text:
        raise Rejected("command or parameter substitution (`$` or backtick) in command")
    reject_unquoted_operators(text)
    try:
        return shlex.split(text, comments=False, posix=True)
    except ValueError as exc:
        raise Rejected(f"unparseable quoting: {exc}") from exc


def option_name(token: str) -> str:
    if token.startswith("--"):
        return token.split("=", 1)[0]
    return token[:2]


def validate_url(value: str) -> str:
    if any(char in value for char in "\\{}[] \t\"'"):
        raise Rejected("URL contains characters outside the supported shape")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise Rejected("URL is malformed") from exc
    if parts.scheme != "https":
        raise Rejected("URL scheme must be https")
    if parts.username is not None or parts.password is not None:
        raise Rejected("URL must not embed credentials")
    if port not in (None, 443):
        raise Rejected("URL port must be 443")
    if parts.fragment:
        raise Rejected("URL must not carry a fragment")
    host = (parts.hostname or "").lower()
    if not host.isascii() or not any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_HOST_SUFFIXES):
        raise Rejected(f"host {host or '(none)'} is not an Atlassian host (atlassian.net, atlassian.com)")
    return value


def redact_url(value: str) -> str:
    parts = urlsplit(value)
    query = "?<redacted>" if parts.query else ""
    return f"{parts.scheme}://{parts.hostname}{parts.path}{query}"


def set_file(command: UploadCommand, path: str) -> None:
    if command.file_path is not None:
        raise Rejected("command sends more than one file body")
    if not path or path == "-":
        raise Rejected("file body must name a local file, not stdin")
    command.file_path = path


def add_header(command: UploadCommand, value: str) -> None:
    if value.startswith("@"):
        raise Rejected("-H @file (headers read from a file) is unsupported")
    match = HEADER_RE.match(value)
    if not match:
        raise Rejected("header is not `Name: value`")
    name = match.group(1)
    if name.lower() in FORBIDDEN_HEADERS:
        raise Rejected(f"header {name} is unsupported")
    command.options += ["--header", value]
    command.display += ["--header", f"{name}: <redacted>"]


def add_form(command: UploadCommand, value: str) -> None:
    name, sep, content = value.partition("=")
    if not sep or not FIELD_NAME_RE.match(name):
        raise Rejected("-F must be `name=value` with a plain field name")
    if '"' in content:
        raise Rejected("-F quoting inside the field value is unsupported")
    if content.startswith("<"):
        raise Rejected("-F name=<file (file content as text field) is unsupported")
    if not content.startswith("@"):
        if ";" in content:
            raise Rejected("-F text field with `;` parameters is unsupported; use --form-string")
        command.options += ["--form", value]
        command.display += ["--form", f"{name}=<redacted>"]
        return
    path, *params = content[1:].split(";")
    for param in params:
        key, _, param_value = param.partition("=")
        if key == "type" and MIME_RE.match(param_value):
            continue
        if (
            key == "filename"
            and param_value
            and not any(char in param_value for char in "/\\,")
            and param_value not in (".", "..")
        ):
            continue
        raise Rejected("-F file parameter is unsupported")
    set_file(command, path)
    command.options += ["--form", value]
    command.display += ["--form", value]


def add_value_option(command: UploadCommand, kind: str, token: str, value: str) -> None:
    if kind == "method":
        method = value.upper()
        if method not in ALLOWED_METHODS:
            raise Rejected("request method is unsupported; upload uses POST or PUT")
        command.method = method
        command.options += ["--request", method]
        command.display += ["--request", method]
    elif kind == "header":
        add_header(command, value)
    elif kind == "form":
        add_form(command, value)
    elif kind == "form_string":
        name, sep, content = value.partition("=")
        if not sep or not FIELD_NAME_RE.match(name):
            raise Rejected("--form-string must be `name=value` with a plain field name")
        command.options += ["--form-string", value]
        command.display += ["--form-string", f"{name}=<redacted>"]
    elif kind == "data_binary":
        if not value.startswith("@"):
            raise Rejected("--data-binary must send a file (`@path`)")
        set_file(command, value[1:])
        command.options += ["--data-binary", value]
        command.display += ["--data-binary", value]
    elif kind == "url":
        if command.url is not None:
            raise Rejected("command names more than one URL")
        command.url = validate_url(value)
    else:
        if not NUMBER_RE.match(value):
            raise Rejected(f"{option_name(token)} needs a numeric value")
        flag = "--max-time" if kind == "max_time" else "--connect-timeout"
        command.options += [flag, value]
        command.display += [flag, value]


def parse_command(text: str) -> UploadCommand:
    tokens = tokenize(text)
    if not tokens or tokens[0] != "curl":
        raise Rejected("command must start with `curl`")
    command = UploadCommand()
    index = 1
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token.startswith("-") or token == "-":
            if command.url is not None:
                raise Rejected("command names more than one URL")
            command.url = validate_url(token)
            continue
        name = option_name(token)
        if name in DOWNLOAD_OPTIONS:
            raise Rejected(f"{name} is a download option; downloadConfluenceAttachment commands are unsupported")
        if name in REDIRECT_OPTIONS:
            raise Rejected(f"{name} is unsupported; the helper never follows redirects")
        if token in FLAG_OPTIONS:
            flag = FLAG_OPTIONS[token]
            command.options.append(flag)
            command.display.append(flag)
            continue
        if token in VALUE_OPTIONS:
            if index >= len(tokens):
                raise Rejected(f"{token} is missing its value")
            add_value_option(command, VALUE_OPTIONS[token], token, tokens[index])
            index += 1
            continue
        if not token.startswith("--") and len(token) > 2:
            if token[:2] in VALUE_OPTIONS:
                add_value_option(command, VALUE_OPTIONS[token[:2]], token, token[2:])
                continue
            letters = token[1:]
            if set(letters) <= COMBINABLE_SHORT_FLAGS:
                for letter in letters:
                    flag = FLAG_OPTIONS["-" + letter]
                    command.options.append(flag)
                    command.display.append(flag)
                continue
            if any(f"-{letter}" in DOWNLOAD_OPTIONS | REDIRECT_OPTIONS for letter in letters):
                raise Rejected(f"{name} includes a download or redirect option; unsupported")
        raise Rejected(f"curl option {name} is unsupported")
    if command.url is None:
        raise Rejected("command has no URL")
    if command.file_path is None:
        raise Rejected("command sends no file (`-F name=@path` or `--data-binary @path`); download commands are unsupported")
    return command


def verify_file(command: UploadCommand, expected: str) -> BinaryIO:
    expected_path = Path(expected)
    if not expected_path.is_absolute():
        raise InvalidInput("--file must be an absolute path")
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(expected_path, flags)
    except OSError as exc:
        raise InvalidInput(f"--file is not an openable regular file: {expected}") from exc
    try:
        expected_stat = os.fstat(descriptor)
        if not stat.S_ISREG(expected_stat.st_mode):
            raise InvalidInput(f"--file is not an openable regular file: {expected}")
        upload = os.fdopen(descriptor, "rb")
    except (InvalidInput, OSError) as exc:
        os.close(descriptor)
        if isinstance(exc, InvalidInput):
            raise
        raise InvalidInput(f"--file is not an openable regular file: {expected}") from exc
    try:
        assert command.file_path is not None
        try:
            command_stat = os.stat(command.file_path)
        except OSError as exc:
            raise Rejected("command file body is not the intended file") from exc
        if (command_stat.st_dev, command_stat.st_ino) != (expected_stat.st_dev, expected_stat.st_ino):
            raise Rejected("command does not upload the intended file")

        # curl reads the held descriptor through stdin. It never reopens a path
        # from the untrusted command after the identity check.
        for index, option in enumerate(command.options[:-1]):
            value = command.options[index + 1]
            if option == "--data-binary":
                command.options[index + 1] = "@-"
                command.display[index + 1] = "@<validated-file-stdin>"
                return upload
            if option == "--form":
                name, separator, content = value.partition("=")
                if separator and content.startswith("@"):
                    _, _, raw_params = content.partition(";")
                    params = raw_params.split(";") if raw_params else []
                    if not any(param.startswith("filename=") for param in params):
                        filename = expected_path.name
                        if not filename or any(char in filename for char in '\\",;'):
                            raise Rejected("intended filename needs unsupported curl form quoting")
                        params.append(f"filename={filename}")
                    suffix = ";" + ";".join(params) if params else ""
                    command.options[index + 1] = f"{name}=@-{suffix}"
                    command.display[index + 1] = f"{name}=@<validated-file-stdin>{suffix}"
                    return upload
        raise Rejected("command has no supported file option")
    except Exception:
        upload.close()
        raise


def build_argv(curl: str, command: UploadCommand) -> tuple[list[str], list[str]]:
    assert command.url is not None
    argv = [curl, *ENFORCED_PREFIX, *command.options, "--url", command.url]
    display = ["curl", *ENFORCED_PREFIX, *command.display, "--url", redact_url(command.url)]
    return argv, display


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--command-file", required=True, help="File holding the returned curl command verbatim, or - for stdin")
    parser.add_argument("--file", required=True, help="Local file the upload must send")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the redacted argv without running curl")
    args = parser.parse_args()

    try:
        text = read_command(args.command_file)
        command = parse_command(text)
        curl = shutil.which("curl")
        if curl is None:
            raise InvalidInput("curl not found on PATH")
        upload = verify_file(command, args.file)
    except InvalidInput as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Rejected as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1

    with upload:
        argv, display = build_argv(curl, command)
        print("curl argv (redacted): " + shlex.join(display), file=sys.stderr)
        if args.dry_run:
            return 0

        result = subprocess.run(
            argv,
            shell=False,
            stdin=upload,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            print(f"ERROR: curl exited {result.returncode}", file=sys.stderr)
            return 3
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
