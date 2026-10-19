"""Subprocess tests for run_confluence_attachment_upload.py using a fake curl on PATH."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

HELPER = Path(__file__).resolve().parent / "run_confluence_attachment_upload.py"
SECRET_TOKEN = "SECRETBEARER123"
QUERY_SECRET = "QUERYSECRET456"
UPLOAD_URL = f"https://api.media.atlassian.com/upload/v1?token={QUERY_SECRET}"

FAKE_CURL = f"""#!{sys.executable}
import json, os, sys
with open(os.environ["FAKE_CURL_LOG"], "w", encoding="utf-8") as handle:
    json.dump(sys.argv[1:], handle)
swap_path = os.environ.get("FAKE_CURL_SWAP_PATH")
if swap_path:
    replacement = swap_path + ".replacement"
    with open(replacement, "wb") as handle:
        handle.write(b"replacement-bytes")
    os.replace(replacement, swap_path)
stdin_log = os.environ.get("FAKE_CURL_STDIN_LOG")
if stdin_log:
    with open(stdin_log, "wb") as handle:
        handle.write(sys.stdin.buffer.read())
print(os.environ.get("FAKE_CURL_STDOUT", ""))
print(os.environ.get("FAKE_CURL_STDERR", ""), file=sys.stderr)
status = int(os.environ.get("FAKE_CURL_HTTP_STATUS", "0"))
if status >= 400 and ("--fail" in sys.argv or "--fail-with-body" in sys.argv):
    sys.exit(22)
sys.exit(int(os.environ.get("FAKE_CURL_EXIT", "0")))
"""


class AttachmentUploadHelperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.work = self.tmp / "work"
        self.work.mkdir()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "curl"
        fake.write_text(FAKE_CURL, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.fake_curl = fake
        self.log = self.tmp / "curl-argv.json"
        self.upload = self.tmp / "diagram.png"
        self.upload.write_bytes(b"png-bytes")
        self.other = self.tmp / "other.png"
        self.other.write_bytes(b"other")
        self.marker = self.work / "PWNED"
        self.env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
            "FAKE_CURL_LOG": str(self.log),
        }

    def command(self, *, url: str = UPLOAD_URL, file: Path | None = None, extra: str = "") -> str:
        target = file or self.upload
        return (
            f"curl -X POST -H 'Authorization: Bearer {SECRET_TOKEN}' -H 'X-Atlassian-Token: no-check' "
            f"{extra} -F 'file=@{target}' '{url}'"
        )

    def run_helper(
        self,
        command: str,
        *,
        file: Path | None = None,
        dry_run: bool = False,
        command_file: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        if command_file is None:
            path = self.tmp / "command.txt"
            path.write_text(command, encoding="utf-8")
            command_file = str(path)
        args = [sys.executable, str(HELPER), "--command-file", command_file, "--file", str(file or self.upload)]
        if dry_run:
            args.append("--dry-run")
        return subprocess.run(
            args,
            cwd=self.work,
            env={**self.env, **(extra_env or {})},
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_exit(self, result: subprocess.CompletedProcess[str], code: int) -> None:
        self.assertEqual(code, result.returncode, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def assert_no_leak(self, result: subprocess.CompletedProcess[str]) -> None:
        combined = result.stdout + result.stderr
        self.assertNotIn(SECRET_TOKEN, combined)
        self.assertNotIn(QUERY_SECRET, combined)

    def assert_rejected(self, command: str, code: int = 1) -> subprocess.CompletedProcess[str]:
        result = self.run_helper(command)
        self.assert_exit(result, code)
        self.assertFalse(self.log.exists(), "curl must not run for a rejected command")
        self.assertFalse(self.marker.exists(), "shell side effect observed")
        self.assert_no_leak(result)
        return result

    def test_valid_upload_runs_curl_as_validated_argv(self) -> None:
        result = self.run_helper(self.command(extra="-s -S --fail"))

        self.assert_exit(result, 0)
        argv = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual(["-q", "--proto", "=https", "--proto-redir", "=https", "--max-redirs", "0", "--globoff"], argv[:8])
        self.assertIn("Authorization: Bearer " + SECRET_TOKEN, argv)
        self.assertIn("X-Atlassian-Token: no-check", argv)
        self.assertEqual(["--request", "POST"], argv[argv.index("--request") : argv.index("--request") + 2])
        self.assertEqual("file=@-;filename=diagram.png", argv[argv.index("--form") + 1])
        self.assertEqual(["--url", UPLOAD_URL], argv[-2:])
        self.assertNotIn("-L", argv)
        self.assertNotIn("--location", argv)
        self.assert_no_leak(result)

    def test_data_binary_upload_is_accepted(self) -> None:
        command = f"curl -X PUT -H 'Authorization: Bearer {SECRET_TOKEN}' --data-binary '@{self.upload}' '{UPLOAD_URL}'"
        result = self.run_helper(command)

        self.assert_exit(result, 0)
        argv = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual("@-", argv[argv.index("--data-binary") + 1])

    def fail_flags(self, argv: list[str]) -> list[str]:
        return [arg for arg in argv if arg in {"--fail", "--fail-with-body"}]

    def test_fail_is_added_when_command_omits_it(self) -> None:
        for label, command in {
            "form": self.command(),
            "data-binary": f"curl -X PUT -H 'Authorization: Bearer {SECRET_TOKEN}' --data-binary '@{self.upload}' '{UPLOAD_URL}'",
            "silent only": self.command(extra="-s -S"),
        }.items():
            with self.subTest(label):
                self.log.unlink(missing_ok=True)
                self.assert_exit(self.run_helper(command), 0)
                argv = json.loads(self.log.read_text(encoding="utf-8"))
                self.assertEqual(["--fail"], self.fail_flags(argv))

    def test_explicit_fail_flags_are_kept_without_duplication(self) -> None:
        cases = {
            "--fail": ["--fail"],
            "-f": ["--fail"],
            "-sSf": ["--fail"],
            "--fail-with-body": ["--fail-with-body"],
        }
        for extra, expected in cases.items():
            with self.subTest(extra):
                self.log.unlink(missing_ok=True)
                self.assert_exit(self.run_helper(self.command(extra=extra)), 0)
                argv = json.loads(self.log.read_text(encoding="utf-8"))
                self.assertEqual(expected, self.fail_flags(argv))

    def test_conflicting_fail_flags_are_rejected(self) -> None:
        for extra in ("--fail --fail-with-body", "-f --fail-with-body"):
            with self.subTest(extra):
                result = self.assert_rejected(self.command(extra=extra))
                self.assertIn("mutually exclusive", result.stderr)

    def test_dry_run_shows_injected_fail_flag(self) -> None:
        result = self.run_helper(self.command(), dry_run=True)

        self.assert_exit(result, 0)
        self.assertIn("--fail", result.stderr)

    def test_http_error_status_surfaces_as_failure(self) -> None:
        for label, extra in {"fail omitted": "", "explicit --fail": "--fail", "fail-with-body": "--fail-with-body"}.items():
            with self.subTest(label):
                result = self.run_helper(self.command(extra=extra), extra_env={"FAKE_CURL_HTTP_STATUS": "500"})
                self.assert_exit(result, 3)
                self.assert_no_leak(result)

    def test_line_continuations_are_joined(self) -> None:
        command = (
            f"curl -X POST \\\n  -H 'Authorization: Bearer {SECRET_TOKEN}' \\\n  -F 'file=@{self.upload}' \\\n  '{UPLOAD_URL}'\n"
        )
        self.assert_exit(self.run_helper(command), 0)
        self.assertTrue(self.log.exists())

    def test_shell_metacharacters_inside_quotes_stay_one_literal_argument(self) -> None:
        command = self.command(extra=f"-H 'X-Note: a;touch {self.marker}|b'")
        result = self.run_helper(command)

        self.assert_exit(result, 0)
        argv = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertIn(f"X-Note: a;touch {self.marker}|b", argv)
        self.assertFalse(self.marker.exists())

    def test_shell_syntax_is_rejected_without_running_anything(self) -> None:
        marker = self.marker
        cases = {
            "command substitution": self.command(extra=f"-H 'X-Note: $(touch {marker})'"),
            "backticks": self.command(extra=f"-H 'X-Note: `touch {marker}`'"),
            "parameter expansion": self.command(extra="-H 'X-Note: ${HOME}'"),
            "bare variable": self.command(extra="-H X-Note:$HOME"),
            "semicolon": self.command() + f"; touch {marker}",
            "and-list": self.command() + f" && touch {marker}",
            "pipe": self.command() + " | cat",
            "background": self.command() + f" & touch {marker}",
            "redirect": self.command() + f" > {marker}",
            "subshell": f"({self.command()})",
            "newline second command": self.command() + f"\ntouch {marker}",
            "comment": self.command() + " # trailing",
            "unterminated quote": self.command() + " 'oops",
            "control character": self.command(extra="-H 'X-Note: a\x07b'"),
        }
        for label, command in cases.items():
            with self.subTest(label):
                self.assert_rejected(command)

    def test_non_curl_commands_are_rejected(self) -> None:
        for command in (
            f"wget '{UPLOAD_URL}'",
            f"sh -c 'curl {UPLOAD_URL}'",
            f"/usr/bin/curl -F 'file=@{self.upload}' '{UPLOAD_URL}'",
            f"env curl -F 'file=@{self.upload}' '{UPLOAD_URL}'",
        ):
            with self.subTest(command):
                self.assert_rejected(command)

    def test_unsupported_options_are_rejected(self) -> None:
        for extra in (
            "-k",
            "--insecure",
            "-K /tmp/curlrc",
            "--config /tmp/curlrc",
            "-x http://proxy.example.com:3128",
            "--proxy http://proxy.example.com:3128",
            "-d secret=1",
            "--data secret=1",
            "-T /etc/passwd",
            "--upload-file /etc/passwd",
            "-u user:pass",
            "--cacert /tmp/ca.pem",
            "--resolve x.atlassian.net:443:127.0.0.1",
            "--connect-to x.atlassian.net:443:evil.example.com:443",
            "--proto-default http",
            "-e http://evil.example.com",
            "-w '%{url_effective}'",
            "--trace /tmp/trace",
            "-v",
            "--request=POST",
            "-XDELETE",
            "-X GET",
        ):
            with self.subTest(extra):
                self.assert_rejected(self.command(extra=extra))

    def test_rejection_reasons_do_not_echo_untrusted_values(self) -> None:
        cases = (
            self.command(extra=f"-X {SECRET_TOKEN}"),
            (
                f"curl -X POST -H 'Authorization: Bearer safe' "
                f"-F 'file=@{self.upload};{SECRET_TOKEN}=x' '{UPLOAD_URL}'"
            ),
        )
        for command in cases:
            with self.subTest(command=command):
                self.assert_rejected(command)

    def test_download_and_redirect_options_are_rejected(self) -> None:
        for extra in ("-L", "--location", "--location-trusted", "--max-redirs 5", "-o /tmp/out", "--output /tmp/out", "-O", "-sSL"):
            with self.subTest(extra):
                self.assert_rejected(self.command(extra=extra))
        download = f"curl --output out.png --location -H 'Authorization: Bearer {SECRET_TOKEN}' '{UPLOAD_URL}'"
        result = self.assert_rejected(download)
        self.assertIn("download", result.stderr.lower())

    def test_file_options_that_read_other_files_are_rejected(self) -> None:
        for extra in ("-F 'meta=<" + str(self.other) + "'", "-H @" + str(self.other), f"--data-binary @{self.other}"):
            with self.subTest(extra):
                self.assert_rejected(self.command(extra=extra))

    def test_wrong_hosts_and_schemes_are_rejected(self) -> None:
        for url in (
            "https://evil.example.com/upload",
            "https://atlassian.net.evil.example.com/upload",
            "https://evilatlassian.net/upload",
            "https://x.atlassian.net@evil.example.com/upload",
            "https://user:pw@x.atlassian.net/upload",
            "https://x.atlassian.net:8443/upload",
            "https://127.0.0.1/upload",
            "http://x.atlassian.net/upload",
            "ftp://x.atlassian.net/upload",
            "file:///etc/passwd",
            "x.atlassian.net/upload",
            "https://x.atlassian.net/upload#frag",
            "https://x.atlassian.net/up load",
            "https://x.atlassian.net/{a,b}",
            "https://x.atlassian.net/[1-9]",
        ):
            with self.subTest(url):
                self.assert_rejected(self.command(url=url))

    def test_atlassian_hosts_are_accepted(self) -> None:
        for url in ("https://example.atlassian.net/wiki/rest/api/content/1/child/attachment", "https://api.media.atlassian.com/up"):
            with self.subTest(url):
                self.log.unlink(missing_ok=True)
                self.assert_exit(self.run_helper(self.command(url=url)), 0)
                self.assertTrue(self.log.exists())

    def test_multiple_urls_or_files_are_rejected(self) -> None:
        self.assert_rejected(self.command() + " 'https://example.atlassian.net/second'")
        self.assert_rejected(self.command(extra=f"-F 'second=@{self.upload}'"))
        self.assert_rejected(self.command(extra="--url 'https://example.atlassian.net/second'"))

    def test_command_without_file_or_url_is_rejected(self) -> None:
        self.assert_rejected(f"curl -X POST -H 'Authorization: Bearer {SECRET_TOKEN}' '{UPLOAD_URL}'")
        self.assert_rejected(f"curl -X POST -F 'file=@{self.upload}'")

    def test_command_must_upload_the_intended_file(self) -> None:
        result = self.assert_rejected(self.command(file=self.other))
        self.assertIn("intended file", result.stderr)

    def test_symlink_to_intended_file_uses_the_held_descriptor(self) -> None:
        link = self.tmp / "link.png"
        try:
            link.symlink_to(self.upload)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assert_exit(self.run_helper(self.command(file=link)), 0)
        argv = json.loads(self.log.read_text(encoding="utf-8"))
        self.assertEqual("file=@-;filename=diagram.png", argv[argv.index("--form") + 1])

    def test_path_replacement_cannot_change_the_uploaded_bytes(self) -> None:
        stdin_log = self.tmp / "curl-stdin.bin"
        result = self.run_helper(
            self.command(),
            extra_env={
                "FAKE_CURL_SWAP_PATH": str(self.upload),
                "FAKE_CURL_STDIN_LOG": str(stdin_log),
            },
        )

        self.assert_exit(result, 0)
        self.assertEqual(b"png-bytes", stdin_log.read_bytes())
        self.assertEqual(b"replacement-bytes", self.upload.read_bytes())

    def test_unsafe_form_filenames_are_rejected(self) -> None:
        explicit = (
            f"curl -X POST -H 'Authorization: Bearer {SECRET_TOKEN}' "
            f"-F 'file=@{self.upload};filename=bad,name.png' '{UPLOAD_URL}'"
        )
        self.assert_rejected(explicit)
        for index, name in enumerate(("comma,name.png", "semi;name.png")):
            target = self.tmp / name
            target.write_bytes(b"special")
            link = self.tmp / f"safe-{index}.png"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlinks unavailable")
            result = self.run_helper(self.command(file=link), file=target)
            self.assert_exit(result, 1)
            self.assertIn("filename", result.stderr)
            self.assertFalse(self.log.exists())

    def test_missing_or_non_regular_intended_file_exits_2(self) -> None:
        missing = self.tmp / "absent.png"
        for label, target in {"missing": missing, "directory": self.tmp}.items():
            with self.subTest(label):
                result = self.run_helper(self.command(file=target), file=target)
                self.assert_exit(result, 2)
                self.assertFalse(self.log.exists())
                self.assert_no_leak(result)

    def test_relative_intended_file_exits_2(self) -> None:
        relative = Path("relative.png")
        (self.work / relative).write_bytes(b"png")
        result = self.run_helper(self.command(file=relative), file=relative)
        self.assert_exit(result, 2)
        self.assertIn("absolute path", result.stderr)
        self.assertFalse(self.log.exists())

    def test_unreadable_command_file_exits_2(self) -> None:
        for label, path in {"missing": str(self.tmp / "none.txt"), "directory": str(self.tmp)}.items():
            with self.subTest(label):
                self.assert_exit(self.run_helper("", command_file=path), 2)
        binary = self.tmp / "binary.bin"
        binary.write_bytes(b"\xff\xfe\x00")
        self.assert_exit(self.run_helper("", command_file=str(binary)), 2)
        self.assert_exit(self.run_helper("   \n"), 2)
        self.assertFalse(self.log.exists())

    def test_missing_arguments_exit_2(self) -> None:
        result = subprocess.run([sys.executable, str(HELPER)], capture_output=True, text=True, check=False)
        self.assert_exit(result, 2)

    def test_dry_run_validates_without_running_curl_and_redacts(self) -> None:
        result = self.run_helper(self.command(), dry_run=True)

        self.assert_exit(result, 0)
        self.assertFalse(self.log.exists())
        self.assertIn("Authorization: <redacted>", result.stderr)
        self.assertIn("https://api.media.atlassian.com/upload/v1?<redacted>", result.stderr)
        self.assert_no_leak(result)

    def test_curl_output_is_discarded(self) -> None:
        result = self.run_helper(
            self.command(),
            extra_env={
                "FAKE_CURL_STDOUT": f"stdout {SECRET_TOKEN} {QUERY_SECRET} reflected",
                "FAKE_CURL_STDERR": f"stderr {SECRET_TOKEN} {QUERY_SECRET} reflected",
            },
        )

        self.assert_exit(result, 0)
        self.assertEqual(result.stdout, "")
        self.assertNotIn("reflected", result.stderr)
        self.assert_no_leak(result)

    def test_curl_failure_exits_3_without_leaking(self) -> None:
        result = self.run_helper(self.command(), extra_env={"FAKE_CURL_EXIT": "22", "FAKE_CURL_STDOUT": SECRET_TOKEN})

        self.assert_exit(result, 3)
        self.assertIn("22", result.stderr)
        self.assert_no_leak(result)

    def test_missing_curl_exits_2(self) -> None:
        result = self.run_helper(self.command(), extra_env={"PATH": str(self.tmp / "empty")})

        self.assert_exit(result, 2)
        self.assertIn("curl not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
