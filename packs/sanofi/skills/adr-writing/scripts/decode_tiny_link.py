#!/usr/bin/env python3
"""Decode a Confluence tiny-link token (the part after /x/) to candidate page IDs.

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
    b64 += "=" * (-len(b64) % 4)
    raw = base64.b64decode(b64, validate=True)
    if not raw or len(raw) > 8:
        raise ValueError(f"unexpected decoded width: {len(raw)} bytes")
    return int.from_bytes(raw, "little")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        print("usage: decode_tiny_link.py <token-or-tiny-url>", file=sys.stderr)
        return 0 if sys.argv[1:] in (["-h"], ["--help"]) else 2
    try:
        print(decode(sys.argv[1]))
    except ValueError as exc:
        print(f"cannot decode: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
