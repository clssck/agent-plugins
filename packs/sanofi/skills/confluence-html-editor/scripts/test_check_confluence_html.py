#!/usr/bin/env python3
"""Regression tests for check_confluence_html.py."""

from __future__ import annotations

from pathlib import Path
import unittest

from check_confluence_html import check


def severities(
    html: str, *, original_html: str | None = None, title: str | None = None
) -> list[tuple[str, str]]:
    _, findings = check(html, original_html=original_html, title=title)
    return [(item.severity, item.message) for item in findings]


class CheckConfluenceHtmlTests(unittest.TestCase):
    def test_template_assets_pass_checker(self) -> None:
        assets_dir = Path(__file__).resolve().parents[1] / "assets"
        template_paths = sorted(assets_dir.glob("*.html"))

        self.assertGreaterEqual(len(template_paths), 1)
        for template_path in template_paths:
            with self.subTest(template=template_path.name):
                html = template_path.read_text(encoding="utf-8")
                stats, findings = check(html)

                self.assertEqual([], findings)
                self.assertGreaterEqual(stats.panels, 1)
                self.assertGreaterEqual(stats.statuses, 1)

    def test_native_rich_body_passes_without_findings(self) -> None:
        html = """
        <div data-type="panel-info"><p><strong>Context:</strong> Ready.</p></div>
        <table>
          <thead><tr><th><p>Area</p></th><th><p>Status</p></th></tr></thead>
          <tbody>
            <tr>
              <td><p>Probe</p></td>
              <td><p><span data-type="status" data-color="green">Pass</span></p></td>
            </tr>
          </tbody>
        </table>
        <ul data-type="task-list">
          <li data-type="task-item"><input type="checkbox" checked> Confirmed</li>
        </ul>
        <ul data-type="decision-list">
          <li data-type="decision-item" data-state="DECIDED">Use HTML first.</li>
        </ul>
        <details>
          <summary>Command</summary>
          <pre><code class="language-shell">python scripts/check_confluence_html.py proposed.html</code></pre>
        </details>
        <iframe src="https://example.com"></iframe>
        """
        stats, findings = check(html)

        self.assertEqual([], findings)
        self.assertEqual(1, stats.panels)
        self.assertEqual(1, stats.statuses)
        self.assertEqual(1, stats.task_lists)
        self.assertEqual(1, stats.task_items)
        self.assertEqual(1, stats.decision_lists)
        self.assertEqual(1, stats.decision_items)
        self.assertEqual(1, stats.details)
        self.assertEqual(1, stats.embeds)

    def test_mermaid_source_block_is_allowed(self) -> None:
        html = """
        <pre><code class="language-mermaid">flowchart LR
          A --&gt; B</code></pre>
        """

        self.assertEqual([], severities(html))

    def test_rejects_cloud_rejected_or_dangerous_markup(self) -> None:
        html = """
        <html><body>
          <style>.x { color: red; }</style>
          <script>alert(1)</script>
          <p><span class="unsupported-class" data-unknown-probe="1">Nope</span></p>
          <iframe src="https://example.com" width="800" height="400"></iframe>
          <img src="data:image/png;base64,AAAA">
          <a href="file:///C:/tmp/report.html">local</a>
          <img src="C:\\tmp\\chart.png">
          <table><tbody><tr><td><h2>Bad heading</h2></td></tr></tbody></table>
        </body></html>
        """

        messages = [message for severity, message in severities(html) if severity == "error"]

        self.assertTrue(any("Do not include <html>" in message for message in messages))
        self.assertTrue(any("Do not include <body>" in message for message in messages))
        self.assertTrue(any("Unsupported tag <style>" in message for message in messages))
        self.assertTrue(any("Unsupported tag <script>" in message for message in messages))
        self.assertTrue(any("Unsupported class attribute" in message for message in messages))
        self.assertTrue(any("Unknown data attribute" in message for message in messages))
        self.assertTrue(any("Iframe attribute" in message for message in messages))
        self.assertTrue(any("base64/data URI" in message for message in messages))
        self.assertTrue(any("Local file URL" in message for message in messages))
        self.assertTrue(any("Windows local path" in message for message in messages))
        self.assertTrue(any("Do not put <h2>" in message for message in messages))

    def test_warns_for_lossy_or_review_required_patterns(self) -> None:
        original_html = (
            '<div data-type="extension" data-extension-key="drawio" '
            'data-extension-type="com.atlassian.ecosystem"></div>'
        )
        html = """
        <h1>Skill Page</h1>
        <p><span style="color: #bf2600">Colored text</span></p>
        <p><span data-type="status" data-color="green">Very long status label</span></p>
        """

        messages = severities(html, original_html=original_html, title="Skill Page")

        self.assertIn(("warning", "Body has an <h1> that duplicates the page title"), messages)
        self.assertTrue(any("Avoid styling attribute" in message for _, message in messages))
        self.assertTrue(any("Status lozenge text is long" in message for _, message in messages))
        self.assertTrue(any("Extension count dropped" in message for _, message in messages))

    def test_original_comparison_reports_preservation_drops(self) -> None:
        original_html = """
        <div data-type="extension" data-extension-key="drawio-key" data-extension-type="com.atlassian.ecosystem"></div>
        <p><a href="https://example.com/source">Source</a></p>
        <p><img src="https://example.com/chart.png" /></p>
        <iframe src="https://example.com/embed"></iframe>
        <p><span data-type="mention" data-user-id="abc123">@Owner</span></p>
        <p><time datetime="2026-06-19">June 19, 2026</time></p>
        <ul data-type="task-list">
          <li data-type="task-item"><input type="checkbox"> One</li>
          <li data-type="task-item"><input type="checkbox"> Two</li>
        </ul>
        <ul data-type="decision-list">
          <li data-type="decision-item" data-state="DECIDED">Keep macro.</li>
        </ul>
        """
        new_html = """
        <p><a href="https://example.com/other">Other</a></p>
        <ul data-type="task-list">
          <li data-type="task-item"><input type="checkbox"> One</li>
        </ul>
        """

        messages = severities(new_html, original_html=original_html)

        self.assertTrue(any("Extension key dropped" in message for _, message in messages))
        self.assertTrue(any("Link href dropped" in message for _, message in messages))
        self.assertTrue(any("Image source dropped" in message for _, message in messages))
        self.assertTrue(any("Embed source dropped" in message for _, message in messages))
        self.assertTrue(any("Mention user id dropped" in message for _, message in messages))
        self.assertTrue(any("Date marker dropped" in message for _, message in messages))
        self.assertTrue(any("Task item count dropped from 2 to 1" in message for _, message in messages))
        self.assertTrue(any("Decision item count dropped from 1 to 0" in message for _, message in messages))

    def test_void_tags_do_not_create_unclosed_tag_warnings(self) -> None:
        html = """
        <p><img src="https://example.com/chart.png"><input type="checkbox"><br></p>
        <hr>
        """

        messages = severities(html)

        self.assertFalse(any("Unclosed tags" in message for _, message in messages))

    def test_duplicate_local_ids_are_warned(self) -> None:
        html = """
        <p><span data-type="status" data-color="green" data-local-id="same">Pass</span></p>
        <p><span data-type="status" data-color="blue" data-local-id="same">Review</span></p>
        """

        messages = severities(html)

        self.assertTrue(any("Duplicate data-local-id: same" in message for _, message in messages))

    def test_rejects_local_posix_and_home_image_paths(self) -> None:
        for src in (
            "/Users/example/Desktop/chart.png",
            "/private/var/folders/ab/xyz/T/chart.png",
            "/home/example/chart.png",
            "/tmp/chart.png",
            "~/Pictures/chart.png",
            "file:///Users/example/chart.png",
            "\\\\server\\share\\chart.png",
        ):
            with self.subTest(src=src):
                messages = [m for s, m in severities(f'<p><img src="{src}"></p>') if s == "error"]
                self.assertTrue(messages, f"no error for {src}")

    def test_allows_confluence_and_https_image_urls(self) -> None:
        html = (
            '<p><img src="https://example.atlassian.net/wiki/download/attachments/1/a.png"></p>'
            '<p><img src="/wiki/download/attachments/1/b.png"></p>'
        )
        self.assertEqual([], severities(html))

    def test_bare_relative_image_name_is_warned(self) -> None:
        messages = severities('<p><img src="chart.png"></p>')
        self.assertTrue(any(s == "warning" and "Relative src" in m for s, m in messages))

    def test_unclosed_inner_tag_is_reported(self) -> None:
        messages = severities("<p><strong>Missing close</p>")
        self.assertTrue(
            any("Unclosed <strong> was implicitly closed by </p>" in m for _, m in messages)
        )

    def test_optional_end_tags_are_not_reported(self) -> None:
        html = "<ul><li>One<li>Two</ul><table><tbody><tr><td><p>A<td><p>B</table>"
        messages = severities(html)
        self.assertFalse(any("implicitly closed" in m for _, m in messages))


if __name__ == "__main__":
    unittest.main()
