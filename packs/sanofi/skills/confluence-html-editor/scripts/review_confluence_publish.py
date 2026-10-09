#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Review a proposed Confluence HTML publish before calling the update tool.

This script is intentionally local-only. It does not call Confluence. Use it
after saving a fetched HTML body and a proposed full replacement body.

Usage: uv run review_confluence_publish.py --original fetched.html --proposed proposed.html --title "Page title" --page-id 123 --version-message "Polish page"
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable

from check_confluence_html import Finding, Stats, as_dict, check


@dataclass
class ReviewResult:
    status: str
    operation: str
    original_chars: int | None
    proposed_chars: int
    char_delta: int | None
    char_ratio: float | None
    proposed_stats: dict[str, Any]
    findings: list[dict[str, str | None]]
    dropped_headings: list[str]
    checklist: list[str]


class HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.headings: list[tuple[int, str]] = []
        self._level: int | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._level = int(tag[1])
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._level is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._level is None or tag.lower() != f"h{self._level}":
            return
        text = normalize_text("".join(self._buffer))
        if text:
            self.headings.append((self._level, text))
        self._level = None
        self._buffer = []


def read_text(path: str | None) -> str | None:
    if not path:
        return None
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def heading_keys(html: str) -> Counter[str]:
    parser = HeadingParser()
    parser.feed(html)
    parser.close()
    return Counter(f"h{level}: {text}" for level, text in parser.headings)


def finding_dict(finding: Finding) -> dict[str, str | None]:
    return {
        "severity": finding.severity,
        "message": finding.message,
        "context": finding.context,
    }


def add_finding(
    findings: list[dict[str, str | None]],
    severity: str,
    message: str,
    context: str | None = None,
) -> None:
    findings.append({"severity": severity, "message": message, "context": context})


def dropped_heading_list(original_html: str, proposed_html: str) -> list[str]:
    dropped = heading_keys(original_html) - heading_keys(proposed_html)
    result: list[str] = []
    for key, count in dropped.most_common(10):
        result.append(f"{key} ({count})" if count > 1 else key)
    if len(dropped) > 10:
        result.append(f"{len(dropped) - 10} more")
    return result


def review_publish(
    *,
    proposed_html: str,
    original_html: str | None = None,
    title: str | None = None,
    operation: str = "update",
    page_id: str | None = None,
    version_message: str | None = None,
    allow_major_rewrite: bool = False,
) -> ReviewResult:
    original_chars = len(original_html) if original_html is not None else None
    proposed_chars = len(proposed_html)
    char_delta = proposed_chars - original_chars if original_chars is not None else None
    char_ratio = (
        round(proposed_chars / original_chars, 3)
        if original_chars and original_chars > 0
        else None
    )

    stats, html_findings = check(proposed_html, original_html=original_html, title=title)
    findings = [finding_dict(item) for item in html_findings]

    dropped_headings: list[str] = []
    if operation == "update":
        if original_html is None:
            add_finding(findings, "error", "Update review requires --original fetched HTML")
        if not page_id:
            add_finding(findings, "warning", "Pass --page-id to make the target explicit")
        if not title:
            add_finding(findings, "warning", "Pass --title to catch duplicate body H1")
        if not version_message:
            add_finding(findings, "warning", "Pass --version-message for audit-friendly page history")

    if proposed_chars < 80:
        add_finding(findings, "warning", "Proposed body is very short; confirm this is not a fragment")

    if original_html is not None:
        if normalize_text(proposed_html) == normalize_text(original_html):
            add_finding(findings, "warning", "Proposed body is unchanged from original")
        if (
            not allow_major_rewrite
            and original_chars is not None
            and original_chars >= 500
            and char_ratio is not None
            and char_ratio < 0.35
        ):
            add_finding(
                findings,
                "warning",
                "Proposed body is much shorter than original; pass --allow-major-rewrite only if intentional",
                f"ratio={char_ratio}",
            )

        dropped_headings = dropped_heading_list(original_html, proposed_html)
        for heading in dropped_headings[:5]:
            add_finding(findings, "warning", "Heading dropped from original", heading)
        if len(dropped_headings) > 5:
            add_finding(
                findings,
                "warning",
                "Additional headings dropped from original",
                str(len(dropped_headings) - 5),
            )

    severities = {item["severity"] for item in findings}
    if "error" in severities:
        status = "BLOCKED"
    elif "warning" in severities:
        status = "REVIEW"
    else:
        status = "READY"

    checklist = [
        "Refetch latest HTML immediately before write if editing took significant time",
        "Send the complete proposed body with contentFormat=html",
        "Preserve fetched title, spaceId, and parentId unless the user asked to change them",
        "Use a concise versionMessage",
        "Fetch HTML after writing and compare important markers",
        "Fetch ADF after rich edits and verify native nodes",
    ]

    return ReviewResult(
        status=status,
        operation=operation,
        original_chars=original_chars,
        proposed_chars=proposed_chars,
        char_delta=char_delta,
        char_ratio=char_ratio,
        proposed_stats=as_dict(stats, [])["stats"],
        findings=findings,
        dropped_headings=dropped_headings,
        checklist=checklist,
    )


def result_as_dict(result: ReviewResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "operation": result.operation,
        "originalChars": result.original_chars,
        "proposedChars": result.proposed_chars,
        "charDelta": result.char_delta,
        "charRatio": result.char_ratio,
        "proposedStats": result.proposed_stats,
        "findings": result.findings,
        "droppedHeadings": result.dropped_headings,
        "checklist": result.checklist,
    }


def print_summary(result: ReviewResult) -> None:
    print(f"Confluence publish review: {result.status}")
    print(f"Operation: {result.operation}")
    if result.original_chars is None:
        print(f"Body chars: proposed={result.proposed_chars}")
    else:
        print(
            "Body chars: "
            f"original={result.original_chars}, proposed={result.proposed_chars}, "
            f"delta={result.char_delta}, ratio={result.char_ratio}"
        )
    stats = result.proposed_stats
    print(
        "Proposed counts: "
        f"panels={stats['panels']}, statuses={stats['statuses']}, "
        f"extensions={stats['extensions']}, links={stats['links']}, "
        f"images={stats['images']}, embeds={stats['embeds']}, "
        f"task_items={stats['task_items']}, decision_items={stats['decision_items']}"
    )
    if result.findings:
        for item in result.findings:
            context = f" [{item['context']}]" if item.get("context") else ""
            print(f"{item['severity'].upper()}: {item['message']}{context}")
    else:
        print("No findings.")
    print("Checklist:")
    for item in result.checklist:
        print(f"- {item}")


def has_severity(findings: Iterable[dict[str, str | None]], severity: str) -> bool:
    return any(item.get("severity") == severity for item in findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposed", required=True, help="Proposed full HTML body file")
    parser.add_argument("--original", help="Fetched original HTML body file")
    parser.add_argument("--title", help="Live Confluence page title")
    parser.add_argument("--page-id", help="Target page ID for update reviews")
    parser.add_argument("--version-message", help="Intended update version message")
    parser.add_argument(
        "--operation",
        choices=("update", "create"),
        default="update",
        help="Review mode",
    )
    parser.add_argument(
        "--allow-major-rewrite",
        action="store_true",
        help="Suppress body-shrink warnings for intentional large rewrites",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    result = review_publish(
        proposed_html=read_text(args.proposed) or "",
        original_html=read_text(args.original),
        title=args.title,
        operation=args.operation,
        page_id=args.page_id,
        version_message=args.version_message,
        allow_major_rewrite=args.allow_major_rewrite,
    )

    if args.json:
        print(json.dumps(result_as_dict(result), indent=2))
    else:
        print_summary(result)

    if has_severity(result.findings, "error"):
        return 1
    if args.strict and has_severity(result.findings, "warning"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
