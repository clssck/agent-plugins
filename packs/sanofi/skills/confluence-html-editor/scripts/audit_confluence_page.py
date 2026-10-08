#!/usr/bin/env python3
"""Audit fetched Confluence HTML and ADF before editing."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from check_confluence_html import as_dict as html_as_dict
from check_confluence_html import check as check_html
from verify_confluence_adf import analyze_adf, as_dict as adf_as_dict, parse_expect, read_json


@dataclass
class AuditResult:
    html: dict[str, Any] | None
    adf: dict[str, Any] | None
    findings: list[dict[str, str | None]]


def read_text(path: str | None) -> str | None:
    if not path:
        return None
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def prefixed_findings(prefix: str, findings: list[Any]) -> list[dict[str, str | None]]:
    return [
        {
            "severity": item.severity,
            "message": f"{prefix}: {item.message}",
            "context": item.context,
        }
        for item in findings
    ]


def audit_sources(
    *,
    html: str | None = None,
    adf_payload: Any | None = None,
    title: str | None = None,
    expected_adf: set[str] | None = None,
) -> AuditResult:
    html_result: dict[str, Any] | None = None
    adf_result: dict[str, Any] | None = None
    findings: list[dict[str, str | None]] = []

    if html is not None:
        html_stats, html_findings = check_html(html, title=title)
        html_result = html_as_dict(html_stats, html_findings)
        findings.extend(prefixed_findings("HTML", html_findings))

    if adf_payload is not None:
        adf_stats, adf_findings = analyze_adf(adf_payload, expected_adf or set())
        adf_result = adf_as_dict(adf_stats, adf_findings)
        findings.extend(prefixed_findings("ADF", adf_findings))

    if html is None and adf_payload is None:
        findings.append(
            {
                "severity": "error",
                "message": "Provide --html, --adf, or both",
                "context": None,
            }
        )

    return AuditResult(html_result, adf_result, findings)


def print_summary(result: AuditResult) -> None:
    if result.html:
        stats = result.html["stats"]
        print("HTML inventory:")
        print(
            "  "
            f"panels={stats['panels']}, statuses={stats['statuses']}, "
            f"extensions={stats['extensions']}, links={stats['links']}, "
            f"images={stats['images']}, embeds={stats['embeds']}, "
            f"mentions={stats['mentions']}, dates={stats['dates']}, "
            f"task_items={stats['task_items']}, decision_items={stats['decision_items']}"
        )
    if result.adf:
        stats = result.adf["stats"]
        print("ADF inventory:")
        print(
            "  "
            f"panels={stats['panels']}, statuses={stats['statuses']}, "
            f"layouts={stats['layouts']}, inline_cards={stats['inline_cards']}, "
            f"dates={stats['dates']}, embeds={stats['embeds']}, mermaid={stats['mermaid']}, "
            f"task_items={stats['task_items']}, decision_items={stats['decision_items']}, "
            f"unsupported={stats['unsupported']}"
        )
    if result.findings:
        for item in result.findings:
            context = f" [{item['context']}]" if item.get("context") else ""
            print(f"{item['severity'].upper()}: {item['message']}{context}")
    else:
        print("No findings.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", help="Fetched Confluence HTML body file")
    parser.add_argument("--adf", help="Fetched Confluence ADF JSON file")
    parser.add_argument("--title", help="Page title, used to catch duplicate HTML H1")
    parser.add_argument(
        "--expect-adf",
        action="append",
        help="Comma-separated ADF nodes expected after rich edits, e.g. panels,statuses,layouts,tasks,decisions,inline_cards,dates,embeds,mermaid",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    try:
        adf_payload = read_json(args.adf) if args.adf else None
    except ValueError as exc:
        result = AuditResult(
            None,
            None,
            [{"severity": "error", "message": f"ADF: {exc}", "context": None}],
        )
    else:
        result = audit_sources(
            html=read_text(args.html),
            adf_payload=adf_payload,
            title=args.title,
            expected_adf=parse_expect(args.expect_adf),
        )

    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        print_summary(result)

    has_errors = any(item["severity"] == "error" for item in result.findings)
    has_warnings = any(item["severity"] == "warning" for item in result.findings)
    if has_errors or (args.strict and has_warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
