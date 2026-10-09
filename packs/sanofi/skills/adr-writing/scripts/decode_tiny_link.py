#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Decode a Confluence tiny-link token (the part after /x/) to a candidate page ID.

Usage: uv run decode_tiny_link.py <token-or-tiny-url>

Algorithm (Atlassian KB, "How to programmatically generate the Tiny link of a
Confluence page"): page ID -> little-endian bytes -> base64, with '/' -> '-',
'+' -> '_', '=' padding and trailing 'A' (zero) characters dropped.
Decoding reverses this. The result is a candidate: verify by fetching the page.
"""

import base64
import sys


def decode(token: str) -> int:
    token = token.strip().split("/")[-1]
    if not token:
        raise ValueError("empty token")
    b64 = token.replace("-", "/").replace("_", "+")
    # Encoding drops trailing "A" (zero) characters; restore them as zero high-order bytes.
    b64 += "A" * (-len(b64) % 4)
    try:
        raw = base64.b64decode(b64, validate=True).rstrip(b"\0")
    except ValueError as exc:  # binascii.Error subclasses ValueError
        raise ValueError(f"not a tiny-link token: {exc}") from exc
    if len(raw) > 8:
        raise ValueError(f"unexpected decoded width: {len(raw)} bytes")
    return int.from_bytes(raw, "little")


def main() -> int:
    # Tokens may start with "-" (base64 "/" is encoded as "-"), so only exact help flags are flags.
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: uv run decode_tiny_link.py <token-or-tiny-url>", file=sys.stderr)
        return 0 if sys.argv[1:] in (["-h"], ["--help"]) else 2
    try:
        print(decode(sys.argv[1]))
    except ValueError as exc:
        print(f"cannot decode: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
