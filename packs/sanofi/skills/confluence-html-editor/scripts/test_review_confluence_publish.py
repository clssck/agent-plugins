#!/usr/bin/env python3
"""Regression tests for review_confluence_publish.py."""

from __future__ import annotations

import unittest

from review_confluence_publish import review_publish


class ReviewConfluencePublishTests(unittest.TestCase):
    def test_ready_when_update_is_complete_and_clean(self) -> None:
        original = """
        <h2>Overview</h2>
        <p><a href="https://example.com/source">Source</a></p>
        <ul data-type="task-list">
          <li data-type="task-item"><input type="checkbox"> Confirm</li>
        </ul>
        """
        proposed = """
        <h2>Overview</h2>
        <div data-type="panel-info"><p><strong>Context:</strong> Updated.</p></div>
        <p><a href="https://example.com/source">Source</a></p>
        <ul data-type="task-list">
          <li data-type="task-item"><input type="checkbox"> Confirm</li>
        </ul>
        <p><span data-type="status" data-color="green">Ready</span></p>
        """

        result = review_publish(
            proposed_html=proposed,
            original_html=original,
            title="Example",
            page_id="123",
            version_message="Polish page",
        )

        self.assertEqual("READY", result.status)
        self.assertEqual([], result.findings)
        self.assertGreater(result.proposed_stats["panels"], 0)

    def test_blocks_for_invalid_publish_markup(self) -> None:
        result = review_publish(
            proposed_html='<p><img src="file:///C:/tmp/chart.png"></p>',
            original_html="<p>Original</p>",
            title="Example",
            page_id="123",
            version_message="Update page",
        )

        self.assertEqual("BLOCKED", result.status)
        self.assertTrue(
            any(item["severity"] == "error" for item in result.findings)
        )

    def test_warns_when_body_shrinks_like_fragment_upload(self) -> None:
        original = "<h2>Kept</h2>" + ("<p>Original content.</p>" * 60)
        proposed = "<h2>Kept</h2><p>Short.</p>"

        result = review_publish(
            proposed_html=proposed,
            original_html=original,
            title="Example",
            page_id="123",
            version_message="Update page",
        )

        self.assertEqual("REVIEW", result.status)
        self.assertTrue(
            any("much shorter" in item["message"] for item in result.findings)
        )

    def test_allow_major_rewrite_suppresses_shrink_warning(self) -> None:
        original = "<h2>Kept</h2>" + ("<p>Original content.</p>" * 60)
        proposed = "<h2>Kept</h2><p>Short but intentional.</p>"

        result = review_publish(
            proposed_html=proposed,
            original_html=original,
            title="Example",
            page_id="123",
            version_message="Rewrite page",
            allow_major_rewrite=True,
        )

        self.assertFalse(
            any("much shorter" in item["message"] for item in result.findings)
        )

    def test_reports_dropped_headings(self) -> None:
        original = "<h2>Overview</h2><h2>Risk Log</h2><p>Body.</p>"
        proposed = "<h2>Overview</h2><p>Body.</p>"

        result = review_publish(
            proposed_html=proposed,
            original_html=original,
            title="Example",
            page_id="123",
            version_message="Update page",
        )

        self.assertEqual("REVIEW", result.status)
        self.assertIn("h2: Risk Log", result.dropped_headings)
        self.assertTrue(
            any("Heading dropped" in item["message"] for item in result.findings)
        )


if __name__ == "__main__":
    unittest.main()
