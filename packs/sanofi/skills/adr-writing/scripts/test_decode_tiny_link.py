import base64
import subprocess
import sys
import unittest
from pathlib import Path

from decode_tiny_link import decode

SCRIPT = Path(__file__).with_name("decode_tiny_link.py")


def encode(page_id: int) -> str:
    """Atlassian tiny-link encoding: little-endian bytes, base64, '/'->'-', '+'->'_', strip '=' and trailing 'A'."""
    raw = page_id.to_bytes((page_id.bit_length() + 7) // 8 or 1, "little")
    return base64.b64encode(raw).decode().replace("/", "-").replace("+", "_").rstrip("=").rstrip("A")


class DecodeTinyLink(unittest.TestCase):
    def test_round_trips_page_ids(self):
        for page_id in (197121, 60467430731, 66306933380, 3221225472):
            with self.subTest(page_id=page_id):
                self.assertEqual(decode(encode(page_id)), page_id)

    def test_accepts_full_tiny_url(self):
        self.assertEqual(decode("https://example.atlassian.net/wiki/x/AQID"), 197121)

    def test_url_ignores_query_fragment_and_trailing_slash(self):
        for url in (
            "https://example.atlassian.net/wiki/x/AQID?foo=bar/baz",
            "https://example.atlassian.net/wiki/x/AQID#frag/ment",
            "https://example.atlassian.net/wiki/x/AQID/",
            "https://example.atlassian.net/wiki/x/AQID/?a=b#c",
        ):
            with self.subTest(url=url):
                self.assertEqual(decode(url), 197121)

    def test_url_with_dash_token(self):
        token = encode(0xFC)
        self.assertEqual(decode(f"https://example.atlassian.net/wiki/x/{token}?a=b"), 0xFC)

    def test_url_without_token_is_rejected(self):
        with self.assertRaises(ValueError):
            decode("https://example.atlassian.net/?x=AQID")

    def test_rejects_invalid_token(self):
        with self.assertRaises(ValueError):
            decode("!!!")

    def test_cli_decodes_token_starting_with_dash(self):
        token = encode(0xFC)  # first little-endian byte >= 0xFC encodes as "/" -> "-"
        self.assertTrue(token.startswith("-"), token)
        result = subprocess.run([sys.executable, str(SCRIPT), token], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, str(0xFC)))

    def test_cli_help_exits_zero(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage", result.stderr)


if __name__ == "__main__":
    unittest.main()
