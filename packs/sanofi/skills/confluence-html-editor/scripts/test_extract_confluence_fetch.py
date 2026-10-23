"""Regression tests for extract_confluence_fetch.py."""

from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from extract_confluence_fetch import select_page, unwrap_tool_output, write_outputs


class ExtractConfluenceFetchTests(unittest.TestCase):
    def test_unwraps_mcp_text_output(self) -> None:
        page = {"id": "123", "title": "Example", "body": "<p>Hello</p>"}
        wrapped = [{"type": "text", "text": json.dumps(page)}]

        self.assertEqual(page, unwrap_tool_output(wrapped))

    def test_writes_html_body_and_metadata(self) -> None:
        page = {
            "id": "123",
            "type": "page",
            "status": "draft",
            "title": "Example",
            "spaceId": "space",
            "parentId": "parent",
            "version": {"number": 1},
            "body": "<p>Hello</p>",
        }

        with TemporaryDirectory() as tmp:
            result = write_outputs(page, Path(tmp), "fetched")
            body = Path(result["body"]).read_text(encoding="utf-8")
            metadata = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))

        self.assertEqual("html", result["bodyType"])
        self.assertEqual("<p>Hello</p>", body)
        self.assertEqual("123", metadata["id"])
        self.assertEqual("html", metadata["bodyType"])

    def test_writes_adf_body_and_metadata(self) -> None:
        adf = {"type": "doc", "version": 1, "content": []}
        page = {"id": "123", "title": "Example", "body": adf}

        with TemporaryDirectory() as tmp:
            result = write_outputs(page, Path(tmp), "fetched")
            body = json.loads(Path(result["body"]).read_text(encoding="utf-8"))

        self.assertEqual("adf", result["bodyType"])
        self.assertTrue(result["body"].endswith("fetched-adf.json"))
        self.assertEqual(adf, body)

    def test_refuses_overwrite_without_force(self) -> None:
        page = {"id": "123", "title": "Example", "body": "<p>Hello</p>"}

        with TemporaryDirectory() as tmp:
            write_outputs(page, Path(tmp), "fetched")
            with self.assertRaises(FileExistsError):
                write_outputs(page, Path(tmp), "fetched")

    def test_separate_out_dirs_extract_html_and_adf_for_same_page(self) -> None:
        html_page = {"id": "123", "title": "Example", "body": "<p>Hello</p>"}
        adf_page = {"id": "123", "title": "Example", "body": {"type": "doc", "version": 1, "content": []}}

        with TemporaryDirectory() as tmp:
            html_result = write_outputs(html_page, Path(tmp) / "html", "fetched")
            adf_result = write_outputs(adf_page, Path(tmp) / "adf", "fetched")
            self.assertNotEqual(html_result["metadata"], adf_result["metadata"])
            self.assertTrue(Path(html_result["body"]).exists())
            self.assertTrue(Path(adf_result["body"]).exists())
            # Same directory and prefix still collides on the metadata file.
            with self.assertRaises(FileExistsError):
                write_outputs(adf_page, Path(tmp) / "html", "fetched")

    def test_select_page_scans_every_text_block(self) -> None:
        page = {"id": "123", "title": "Example", "body": "<p>Hello</p>"}
        text = json.dumps(page)
        for label, wrapped in {
            "single block": [{"type": "text", "text": text}],
            "summary then page": [
                {"type": "text", "text": "Fetched page"},
                {"type": "text", "text": text},
            ],
            "page then summary": {
                "content": [{"type": "text", "text": text}, {"type": "text", "text": "Done"}]
            },
            "summary-only object plus page": [
                {"type": "text", "text": json.dumps({"id": "123", "title": "Example"})},
                {"type": "text", "text": text},
            ],
            "identical page repeated": [
                {"type": "text", "text": text},
                {"type": "text", "text": text},
            ],
            "page nested in results": {"results": [page]},
            "bare page": page,
        }.items():
            with self.subTest(label):
                self.assertEqual(page, select_page(wrapped))

    def test_select_page_accepts_adf_bodies(self) -> None:
        adf = {"type": "doc", "version": 1, "content": []}
        for body in (adf, json.dumps(adf), {"atlas_doc_format": {"value": adf}}):
            with self.subTest(body=body):
                page = {"id": "9", "body": body}
                with TemporaryDirectory() as tmp:
                    result = write_outputs(select_page([{"type": "text", "text": json.dumps(page)}]), Path(tmp), "f")
                    written = json.loads(Path(result["body"]).read_text(encoding="utf-8"))
                self.assertEqual("adf", result["bodyType"])
                self.assertEqual(adf, written)

    def test_select_page_rejects_missing_or_ambiguous_candidates(self) -> None:
        page_a = {"id": "1", "body": "<p>A</p>"}
        page_b = {"id": "2", "body": "<p>B</p>"}
        for label, payload in {
            "no blocks": [],
            "text blocks without a page": [
                {"type": "text", "text": "Fetched page"},
                {"type": "text", "text": "Done"},
            ],
            "summary only": [{"type": "text", "text": json.dumps({"id": "1", "title": "T"})}],
            "null body": {"id": "1", "title": "T", "body": None},
            "null body in text block": [{"type": "text", "text": json.dumps({"id": "1", "body": None})}],
            "unsupported body shape": {"id": "1", "body": {"storage": {"value": "<p>x</p>"}}},
            "body without page id": {"title": "T", "body": "<p>x</p>"},
            "blank page id": {"id": " ", "body": "<p>x</p>"},
            "two different pages": [
                {"type": "text", "text": json.dumps(page_a)},
                {"type": "text", "text": json.dumps(page_b)},
            ],
            "same id, different bodies": [
                {"type": "text", "text": json.dumps(page_a)},
                {"type": "text", "text": json.dumps({"id": "1", "body": "<p>other</p>"})},
            ],
        }.items():
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    select_page(payload)

    def test_write_outputs_rejects_unsupported_body_without_creating_files(self) -> None:
        for page in ({"id": "1", "body": None}, {"id": "1"}, {"id": "1", "body": {"a": 1}}):
            with self.subTest(page=page), TemporaryDirectory() as tmp:
                out = Path(tmp) / "out"
                with self.assertRaises(ValueError):
                    write_outputs(page, out, "fetched")
                self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
