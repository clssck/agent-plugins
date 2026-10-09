#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Verify Confluence ADF for native rich-page nodes.

Feed this script the JSON returned by the Atlassian MCP page read tool with the
ADF content format, including MCP text-content wrappers. It intentionally does
not call Confluence itself; fetch ADF with the active Atlassian tool, save it,
then run this verifier.

Usage: uv run verify_confluence_adf.py fetched-adf.json --expect panels,statuses,layouts,tasks,decisions,inline_cards,dates
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from extract_confluence_fetch import unwrap_tool_output


@dataclass
class Finding:
    severity: str
    message: str
    context: str | None = None


@dataclass
class AdfStats:
    nodes: int = 0
    node_types: Counter[str] = field(default_factory=Counter)
    panels: int = 0
    statuses: int = 0
    layouts: int = 0
    layout_columns: int = 0
    task_lists: int = 0
    task_items: int = 0
    decision_lists: int = 0
    decision_items: int = 0
    expands: int = 0
    inline_cards: int = 0
    block_cards: int = 0
    dates: int = 0
    embeds: int = 0
    code_blocks: int = 0
    mermaid: int = 0
    mermaid_sources: int = 0
    extensions: int = 0
    unsupported: int = 0
    media: int = 0
    extension_keys: Counter[str] = field(default_factory=Counter)
    card_urls: Counter[str] = field(default_factory=Counter)
    embed_urls: Counter[str] = field(default_factory=Counter)


EXPECT_ALIASES = {
    "panel": "panels",
    "panels": "panels",
    "status": "statuses",
    "statuses": "statuses",
    "layout": "layouts",
    "layouts": "layouts",
    "task": "task_items",
    "tasks": "task_items",
    "task_items": "task_items",
    "decision": "decision_items",
    "decisions": "decision_items",
    "decision_items": "decision_items",
    "inline_card": "inline_cards",
    "inline_cards": "inline_cards",
    "card": "inline_cards",
    "cards": "inline_cards",
    "date": "dates",
    "dates": "dates",
    "embed": "embeds",
    "embeds": "embeds",
    "mermaid": "mermaid",
    "mermaid_source": "mermaid_sources",
    "mermaid_sources": "mermaid_sources",
    "expand": "expands",
    "expands": "expands",
}


def read_json(path: str | None) -> Any:
    text = sys.stdin.read() if not path or path == "-" else Path(path).read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("No JSON input provided")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON input: {exc}") from exc


def maybe_json(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return value
    return value


def extract_adf(payload: Any) -> Any:
    """Accept raw ADF docs, API wrappers, and MCP text-content results."""
    payload = maybe_json(payload)
    if isinstance(payload, dict) and payload.get("type") == "doc":
        return payload
    payload = unwrap_tool_output(payload)
    if isinstance(payload, dict) and payload.get("type") == "doc":
        return payload
    if isinstance(payload, list):
        # MCP results may carry several text blocks; the ADF doc is one of them.
        for item in payload:
            candidate = extract_adf(item)
            if isinstance(candidate, dict) and candidate.get("type") == "doc":
                return candidate
        return payload
    if isinstance(payload, dict):
        for key in ("body", "atlas_doc_format", "value", "content", "text"):
            if key in payload:
                candidate = extract_adf(payload[key])
                if isinstance(candidate, dict) and candidate.get("type") == "doc":
                    return candidate
    return payload


def text_contains_mermaid(value: Any) -> bool:
    try:
        return "mermaid" in json.dumps(value, sort_keys=True).lower()
    except TypeError:
        return "mermaid" in str(value).lower()


def node_url(attrs: dict[str, Any]) -> str | None:
    for key in ("url", "href", "src"):
        value = attrs.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def analyze_node(node: Any, stats: AdfStats, findings: list[Finding]) -> None:
    if isinstance(node, list):
        for item in node:
            analyze_node(item, stats, findings)
        return
    if not isinstance(node, dict):
        return

    node_type = node.get("type")
    attrs = node.get("attrs") if isinstance(node.get("attrs"), dict) else {}
    if isinstance(node_type, str):
        stats.nodes += 1
        stats.node_types[node_type] += 1

        if node_type == "panel":
            stats.panels += 1
        elif node_type == "status":
            stats.statuses += 1
        elif node_type == "layoutSection":
            stats.layouts += 1
        elif node_type == "layoutColumn":
            stats.layout_columns += 1
        elif node_type == "taskList":
            stats.task_lists += 1
        elif node_type == "taskItem":
            stats.task_items += 1
        elif node_type == "decisionList":
            stats.decision_lists += 1
        elif node_type == "decisionItem":
            stats.decision_items += 1
        elif node_type in {"expand", "nestedExpand"}:
            stats.expands += 1
        elif node_type == "inlineCard":
            stats.inline_cards += 1
            url = node_url(attrs)
            if url:
                stats.card_urls[url] += 1
        elif node_type == "blockCard":
            stats.block_cards += 1
            url = node_url(attrs)
            if url:
                stats.card_urls[url] += 1
        elif node_type == "date":
            stats.dates += 1
        elif node_type == "embedCard":
            stats.embeds += 1
            url = node_url(attrs)
            if url:
                stats.embed_urls[url] += 1
        elif node_type == "codeBlock":
            stats.code_blocks += 1
            language = str(attrs.get("language", "")).lower()
            if language == "mermaid":
                stats.mermaid_sources += 1
        elif node_type in {"extension", "bodiedExtension", "inlineExtension"}:
            stats.extensions += 1
            extension_key = attrs.get("extensionKey")
            if isinstance(extension_key, str) and extension_key:
                stats.extension_keys[extension_key] += 1
            else:
                findings.append(Finding("warning", "Extension node is missing extensionKey"))
            if text_contains_mermaid(attrs):
                stats.mermaid += 1
        elif node_type in {"unsupportedBlock", "unsupportedInline"}:
            stats.unsupported += 1
            findings.append(Finding("error", f"ADF contains {node_type}"))
        elif node_type in {"media", "mediaSingle", "mediaGroup"}:
            stats.media += 1

    for value in node.values():
        if isinstance(value, (dict, list)):
            analyze_node(value, stats, findings)


def parse_expect(values: Iterable[str] | None) -> set[str]:
    expected: set[str] = set()
    for item in values or []:
        for raw in item.split(","):
            name = raw.strip().lower().replace("-", "_")
            if not name:
                continue
            expected.add(EXPECT_ALIASES.get(name, name))
    return expected


def stat_value(stats: AdfStats, name: str) -> int:
    value = getattr(stats, name, None)
    return value if isinstance(value, int) else 0


def analyze_adf(payload: Any, expected: set[str] | None = None) -> tuple[AdfStats, list[Finding]]:
    adf = extract_adf(payload)
    stats = AdfStats()
    findings: list[Finding] = []
    if not isinstance(adf, dict) or adf.get("type") != "doc":
        findings.append(Finding("error", "Input does not look like an ADF doc"))
        return stats, findings

    analyze_node(adf, stats, findings)

    for name in sorted(expected or set()):
        if name not in EXPECT_ALIASES.values() and not hasattr(stats, name):
            findings.append(Finding("warning", f"Unknown expected ADF component: {name}"))
            continue
        if stat_value(stats, name) <= 0:
            findings.append(Finding("error", f"Expected ADF component is missing: {name}"))

    return stats, findings


def as_dict(stats: AdfStats, findings: Iterable[Finding]) -> dict[str, Any]:
    return {
        "stats": {
            "nodes": stats.nodes,
            "panels": stats.panels,
            "statuses": stats.statuses,
            "layouts": stats.layouts,
            "layout_columns": stats.layout_columns,
            "task_lists": stats.task_lists,
            "task_items": stats.task_items,
            "decision_lists": stats.decision_lists,
            "decision_items": stats.decision_items,
            "expands": stats.expands,
            "inline_cards": stats.inline_cards,
            "block_cards": stats.block_cards,
            "dates": stats.dates,
            "embeds": stats.embeds,
            "code_blocks": stats.code_blocks,
            "mermaid": stats.mermaid,
            "mermaid_sources": stats.mermaid_sources,
            "extensions": stats.extensions,
            "unsupported": stats.unsupported,
            "media": stats.media,
            "extension_keys": dict(stats.extension_keys),
            "card_urls": dict(stats.card_urls),
            "embed_urls": dict(stats.embed_urls),
            "node_types": dict(stats.node_types),
        },
        "findings": [finding.__dict__ for finding in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="ADF JSON file, or stdin")
    parser.add_argument(
        "--expect",
        action="append",
        help="Comma-separated native nodes expected, e.g. panels,statuses,layouts,tasks,decisions,inline_cards,dates,embeds,mermaid (rendered Mermaid extension) or mermaid_source (plain code block only)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    try:
        payload = read_json(args.input)
    except ValueError as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "stats": as_dict(AdfStats(), [])["stats"],
                        "findings": [
                            {
                                "severity": "error",
                                "message": str(exc),
                                "context": None,
                            }
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print(f"ERROR: {exc}")
        return 1

    stats, findings = analyze_adf(payload, parse_expect(args.expect))
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity == "warning"]

    if args.json:
        print(json.dumps(as_dict(stats, findings), indent=2))
    else:
        print(f"Confluence ADF check: {stats.nodes} nodes")
        print(
            "Counts: "
            f"panels={stats.panels}, statuses={stats.statuses}, "
            f"layouts={stats.layouts}, task_items={stats.task_items}, "
            f"decision_items={stats.decision_items}, inline_cards={stats.inline_cards}, "
            f"dates={stats.dates}, embeds={stats.embeds}, mermaid={stats.mermaid}, mermaid_sources={stats.mermaid_sources}, "
            f"extensions={stats.extensions}, unsupported={stats.unsupported}"
        )
        if stats.extension_keys:
            print("Extension keys: " + ", ".join(sorted(stats.extension_keys)))
        if findings:
            for item in findings:
                context = f" [{item.context}]" if item.context else ""
                print(f"{item.severity.upper()}: {item.message}{context}")
        else:
            print("No findings.")

    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
