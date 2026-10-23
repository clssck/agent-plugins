"""Subprocess contract tests: unreadable or invalid invocation exits 2, content findings exit 1."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

SCRIPTS = Path(__file__).resolve().parent
BAD_HTML = '<p><img src="file:///C:/tmp/chart.png"></p>'
EMPTY_ADF = {"type": "doc", "version": 1, "content": []}


def run(script: str, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


class CliExitContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.missing = str(self.tmp / "missing.txt")
        self.directory = str(self.tmp)
        self.binary = self.tmp / "binary.bin"
        self.binary.write_bytes(b"\xff\xfe\x00\xd8not utf-8")
        self.good_html = self.tmp / "good.html"
        self.good_html.write_text("<p>Hello</p>", encoding="utf-8")
        self.bad_html = self.tmp / "bad.html"
        self.bad_html.write_text(BAD_HTML, encoding="utf-8")
        self.good_adf = self.tmp / "good.json"
        self.good_adf.write_text(json.dumps(EMPTY_ADF), encoding="utf-8")
        self.invalid_json = self.tmp / "invalid.json"
        self.invalid_json.write_text("{not json", encoding="utf-8")

    def assert_exit(self, result: subprocess.CompletedProcess[str], code: int) -> None:
        self.assertEqual(code, result.returncode, msg=f"stdout={result.stdout!r} stderr={result.stderr!r}")
        self.assertNotIn("Traceback", result.stdout + result.stderr)

    def assert_unreadable(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assert_exit(result, 2)
        self.assertIn("ERROR", result.stderr)

    def test_check_html_unreadable_inputs_exit_2(self) -> None:
        for label, args in {
            "missing input": (self.missing,),
            "directory input": (self.directory,),
            "non-utf8 input": (str(self.binary),),
            "missing original": (str(self.good_html), "--original", self.missing),
            "non-utf8 original": (str(self.good_html), "--original", str(self.binary)),
        }.items():
            with self.subTest(label):
                self.assert_unreadable(run("check_confluence_html.py", *args))

    def test_check_html_content_findings_exit_1_and_clean_exit_0(self) -> None:
        self.assert_exit(run("check_confluence_html.py", str(self.bad_html)), 1)
        self.assert_exit(run("check_confluence_html.py", str(self.good_html)), 0)
        self.assert_exit(run("check_confluence_html.py", stdin="<p>Hello</p>"), 0)

    def test_review_publish_unreadable_inputs_exit_2(self) -> None:
        for label, args in {
            "missing proposed": ("--proposed", self.missing),
            "directory proposed": ("--proposed", self.directory),
            "non-utf8 proposed": ("--proposed", str(self.binary)),
            "missing original": ("--proposed", str(self.good_html), "--original", self.missing),
            "non-utf8 original": ("--proposed", str(self.good_html), "--original", str(self.binary)),
        }.items():
            with self.subTest(label):
                self.assert_unreadable(run("review_confluence_publish.py", *args))

    def test_review_publish_content_findings_exit_1(self) -> None:
        result = run(
            "review_confluence_publish.py",
            "--proposed",
            str(self.bad_html),
            "--original",
            str(self.good_html),
            "--title",
            "Example",
            "--page-id",
            "123",
            "--version-message",
            "Update page",
        )
        self.assert_exit(result, 1)

    def test_review_publish_invalid_option_exits_2(self) -> None:
        self.assert_exit(run("review_confluence_publish.py", "--proposed", str(self.good_html), "--operation", "bogus"), 2)

    def test_verify_adf_unreadable_inputs_exit_2(self) -> None:
        for label, args in {
            "missing input": (self.missing,),
            "directory input": (self.directory,),
            "non-utf8 input": (str(self.binary),),
            "invalid json": (str(self.invalid_json),),
            "invalid json with --json": (str(self.invalid_json), "--json"),
        }.items():
            with self.subTest(label):
                self.assert_unreadable(run("verify_confluence_adf.py", *args))
        self.assert_unreadable(run("verify_confluence_adf.py", stdin="  "))

    def test_verify_adf_content_findings_exit_1(self) -> None:
        self.assert_exit(run("verify_confluence_adf.py", str(self.good_adf), "--expect", "panels"), 1)
        self.assert_exit(run("verify_confluence_adf.py", stdin='{"a": 1}'), 1)
        self.assert_exit(run("verify_confluence_adf.py", str(self.good_adf)), 0)

    def test_extract_fetch_unreadable_inputs_exit_2(self) -> None:
        out = str(self.tmp / "out")
        wrong_shape = self.tmp / "wrong-shape.json"
        wrong_shape.write_text("[1, 2]", encoding="utf-8")
        for label, args in {
            "missing input": (self.missing,),
            "directory input": (self.directory,),
            "invalid json": (str(self.invalid_json),),
            "non-page json": (str(wrong_shape),),
        }.items():
            with self.subTest(label):
                self.assert_unreadable(run("extract_confluence_fetch.py", *args, "--out-dir", out))

    def test_extract_fetch_refuses_overwrite_with_exit_2(self) -> None:
        page = self.tmp / "page.json"
        page.write_text(json.dumps({"id": "1", "title": "T", "body": "<p>x</p>"}), encoding="utf-8")
        out = str(self.tmp / "out")
        self.assert_exit(run("extract_confluence_fetch.py", str(page), "--out-dir", out), 0)
        self.assert_unreadable(run("extract_confluence_fetch.py", str(page), "--out-dir", out))
        self.assert_exit(run("extract_confluence_fetch.py", str(page), "--out-dir", out, "--force"), 0)

    def test_extract_fetch_accepts_exactly_one_page_across_text_blocks(self) -> None:
        page = {"id": "1", "title": "T", "body": "<p>x</p>"}
        blocks = self.tmp / "blocks.json"
        blocks.write_text(
            json.dumps(
                {
                    "content": [
                        {"type": "text", "text": "Fetched page"},
                        {"type": "text", "text": json.dumps(page)},
                    ]
                }
            ),
            encoding="utf-8",
        )
        out = self.tmp / "out-blocks"
        self.assert_exit(run("extract_confluence_fetch.py", str(blocks), "--out-dir", str(out)), 0)
        self.assertEqual("<p>x</p>", (out / "fetched.html").read_text(encoding="utf-8"))

    def test_extract_fetch_rejects_candidate_errors_without_outputs(self) -> None:
        def block(value: object) -> dict[str, str]:
            return {"type": "text", "text": json.dumps(value)}

        cases = {
            "zero candidates": [{"type": "text", "text": "Fetched page"}, {"type": "text", "text": "Done"}],
            "summary-only object": [block({"id": "1", "title": "T"})],
            "null body": [block({"id": "1", "title": "T", "body": None})],
            "missing id": [block({"title": "T", "body": "<p>x</p>"})],
            "two pages": [
                block({"id": "1", "body": "<p>a</p>"}),
                block({"id": "2", "body": "<p>b</p>"}),
            ],
            "summary then null body page": [
                block({"id": "1", "title": "T"}),
                block({"id": "1", "title": "T", "body": None}),
            ],
        }
        for label, payload in cases.items():
            with self.subTest(label):
                source = self.tmp / "candidate.json"
                source.write_text(json.dumps(payload), encoding="utf-8")
                out = self.tmp / f"out-{label.replace(' ', '-')}"
                self.assert_unreadable(run("extract_confluence_fetch.py", str(source), "--out-dir", str(out)))
                self.assertFalse(out.exists())

    def test_audit_page_json_null_adf_exits_2(self) -> None:
        null_adf = self.tmp / "null.json"
        null_adf.write_text("null", encoding="utf-8")
        self.assert_unreadable(run("audit_confluence_page.py", "--adf", str(null_adf)))
        self.assert_unreadable(run("audit_confluence_page.py", "--html", str(self.good_html), "--adf", str(null_adf)))
        self.assert_unreadable(run("audit_confluence_page.py", "--adf", "-", stdin="null"))

    def test_audit_page_expect_adf_requires_adf_exits_2(self) -> None:
        for label, args in {
            "html only": ("--html", str(self.good_html), "--expect-adf", "panels"),
            "empty expectation": ("--html", str(self.good_html), "--expect-adf", ""),
        }.items():
            with self.subTest(label):
                result = run("audit_confluence_page.py", *args)
                self.assert_exit(result, 2)
                self.assertIn("--expect-adf", result.stderr)

    def test_verify_adf_mermaid_needs_extension_key_identity(self) -> None:
        fake = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "extension",
                    "attrs": {
                        "extensionKey": "app/static/diagram",
                        "extensionType": "com.atlassian.ecosystem",
                        "parameters": {"text": "mermaid"},
                    },
                }
            ],
        }
        real = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "extension",
                    "attrs": {
                        "extensionKey": "app/module/static/mermaid-diagram",
                        "extensionType": "com.atlassian.ecosystem",
                    },
                }
            ],
        }
        self.assert_exit(run("verify_confluence_adf.py", "--expect", "mermaid", stdin=json.dumps(fake)), 1)
        self.assert_exit(run("audit_confluence_page.py", "--adf", "-", "--expect-adf", "mermaid", stdin=json.dumps(fake)), 1)
        self.assert_exit(run("verify_confluence_adf.py", "--expect", "mermaid", stdin=json.dumps(real)), 0)

    def test_check_html_whitespace_padded_local_url_exits_1(self) -> None:
        self.assert_exit(run("check_confluence_html.py", stdin='<p><img src=" file:///C:/tmp/chart.png "></p>'), 1)
        self.assert_exit(run("check_confluence_html.py", stdin='<p><img src="\t/Users/me/chart.png\n"></p>'), 1)
        self.assert_exit(run("check_confluence_html.py", stdin='<p><img src=" https://example.com/chart.png "></p>'), 0)

    def test_audit_page_unreadable_inputs_exit_2(self) -> None:
        for label, args in {
            "missing html": ("--html", self.missing),
            "directory html": ("--html", self.directory),
            "non-utf8 html": ("--html", str(self.binary)),
            "missing adf": ("--adf", self.missing),
            "invalid adf json": ("--adf", str(self.invalid_json)),
            "good html, missing adf": ("--html", str(self.good_html), "--adf", self.missing),
        }.items():
            with self.subTest(label):
                self.assert_unreadable(run("audit_confluence_page.py", *args))

    def test_audit_page_without_inputs_exits_2(self) -> None:
        result = run("audit_confluence_page.py")
        self.assert_exit(result, 2)
        self.assertIn("--html", result.stderr)

    def test_audit_page_content_findings_exit_1(self) -> None:
        self.assert_exit(run("audit_confluence_page.py", "--html", str(self.bad_html)), 1)
        self.assert_exit(run("audit_confluence_page.py", "--adf", str(self.good_adf), "--expect-adf", "panels"), 1)
        self.assert_exit(run("audit_confluence_page.py", "--html", str(self.good_html), "--adf", str(self.good_adf)), 0)


if __name__ == "__main__":
    unittest.main()
