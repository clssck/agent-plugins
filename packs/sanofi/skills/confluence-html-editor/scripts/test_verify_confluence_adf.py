#!/usr/bin/env python3
"""Regression tests for ADF verification and page audit."""

from __future__ import annotations

import json
import unittest

from audit_confluence_page import audit_sources
from verify_confluence_adf import analyze_adf, extract_adf, parse_expect


def sample_adf() -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "panel",
                "attrs": {"panelType": "info"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Status "},
                            {
                                "type": "status",
                                "attrs": {"text": "Pass", "color": "green"},
                            },
                            {
                                "type": "date",
                                "attrs": {"timestamp": "1781827200000"},
                            },
                            {
                                "type": "inlineCard",
                                "attrs": {"url": "https://example.com/doc"},
                            },
                        ],
                    }
                ],
            },
            {
                "type": "layoutSection",
                "content": [
                    {"type": "layoutColumn", "attrs": {"width": 50}, "content": []},
                    {"type": "layoutColumn", "attrs": {"width": 50}, "content": []},
                ],
            },
            {
                "type": "taskList",
                "content": [
                    {"type": "taskItem", "attrs": {"state": "TODO"}, "content": []}
                ],
            },
            {
                "type": "decisionList",
                "content": [
                    {"type": "decisionItem", "attrs": {"state": "DECIDED"}, "content": []}
                ],
            },
            {"type": "embedCard", "attrs": {"url": "https://example.com/embed"}},
            {
                "type": "extension",
                "attrs": {
                    "extensionKey": "app/static/mermaid-diagram",
                    "extensionType": "com.atlassian.ecosystem",
                    "parameters": {"diagram": "flowchart LR"},
                },
            },
            {"type": "codeBlock", "attrs": {"language": "mermaid"}, "content": []},
            {"type": "expand", "attrs": {"title": "Details"}, "content": []},
        ],
    }


class VerifyConfluenceAdfTests(unittest.TestCase):
    def test_counts_native_adf_nodes(self) -> None:
        stats, findings = analyze_adf(
            sample_adf(),
            parse_expect(
                [
                    "panels,statuses,layouts,tasks,decisions,inline_cards,dates,embeds,mermaid"
                ]
            ),
        )

        self.assertEqual([], findings)
        self.assertEqual(1, stats.panels)
        self.assertEqual(1, stats.statuses)
        self.assertEqual(1, stats.layouts)
        self.assertEqual(2, stats.layout_columns)
        self.assertEqual(1, stats.task_items)
        self.assertEqual(1, stats.decision_items)
        self.assertEqual(1, stats.inline_cards)
        self.assertEqual(1, stats.dates)
        self.assertEqual(1, stats.embeds)
        self.assertEqual(1, stats.mermaid)
        self.assertEqual(1, stats.mermaid_sources)

    def test_accepts_common_response_wrappers(self) -> None:
        wrapped = {"body": {"atlas_doc_format": {"value": sample_adf()}}}

        self.assertEqual("doc", extract_adf(wrapped)["type"])

    def test_unwraps_mcp_text_results(self) -> None:
        text = json.dumps({"id": "1", "body": sample_adf()})
        for wrapped in (
            {"content": [{"type": "text", "text": text}]},
            [{"type": "text", "text": text}],
            {"content": [{"type": "text", "text": "Fetched page"}, {"type": "text", "text": text}]},
            {"content": [{"type": "text", "text": json.dumps(sample_adf())}], "isError": False},
        ):
            with self.subTest(wrapped=wrapped):
                stats, findings = analyze_adf(wrapped, parse_expect(["panels,statuses"]))
                self.assertEqual([], findings)
                self.assertEqual(1, stats.panels)

    def test_mermaid_code_block_alone_does_not_verify_native_diagram(self) -> None:
        adf = {
            "type": "doc",
            "version": 1,
            "content": [{"type": "codeBlock", "attrs": {"language": "mermaid"}, "content": []}],
        }

        stats, findings = analyze_adf(adf, parse_expect(["mermaid"]))
        self.assertEqual(0, stats.mermaid)
        self.assertEqual(1, stats.mermaid_sources)
        self.assertTrue(any("Expected ADF component is missing: mermaid" in f.message for f in findings))

        _, source_findings = analyze_adf(adf, parse_expect(["mermaid_source"]))
        self.assertEqual([], source_findings)

    def test_missing_expected_component_is_error(self) -> None:
        _, findings = analyze_adf(sample_adf(), parse_expect(["media"]))

        self.assertTrue(any(item.severity == "error" for item in findings))
        self.assertTrue(any("Expected ADF component is missing: media" in item.message for item in findings))

    def test_unsupported_adf_node_is_error(self) -> None:
        adf = sample_adf()
        adf["content"].append({"type": "unsupportedBlock"})

        _, findings = analyze_adf(adf)

        self.assertTrue(any(item.severity == "error" for item in findings))
        self.assertTrue(any("unsupportedBlock" in item.message for item in findings))

    def test_page_audit_combines_html_and_adf_findings(self) -> None:
        html = '<p><span data-type="status" data-color="green">Pass</span></p>'
        result = audit_sources(
            html=html,
            adf_payload=sample_adf(),
            expected_adf=parse_expect(["panels,statuses,mermaid"]),
        )

        self.assertEqual([], result.findings)
        self.assertIsNotNone(result.html)
        self.assertIsNotNone(result.adf)


if __name__ == "__main__":
    unittest.main()
