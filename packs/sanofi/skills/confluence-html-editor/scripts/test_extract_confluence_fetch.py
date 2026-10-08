#!/usr/bin/env python3
"""Regression tests for extract_confluence_fetch.py."""

from __future__ import annotations

import json
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from extract_confluence_fetch import unwrap_tool_output, write_outputs


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


if __name__ == "__main__":
    unittest.main()
