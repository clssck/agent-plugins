#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Check Confluence HTML body fragments before publishing.

This is a lightweight dry-run gate for the confluence-html-editor skill. It
uses only the Python standard library and intentionally validates body
fragments, not full HTML documents.

Usage: uv run check_confluence_html.py proposed.html --original fetched.html --title "Page title"
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable


FORBIDDEN_WRAPPERS = {"html", "head", "body"}
FORBIDDEN_TAGS = {"script", "style"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK_TAGS = {
    "blockquote",
    "details",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "ul",
}
INLINE_TAGS = {"a", "code", "em", "span", "strong", "time"}
VALID_STATUS_COLORS = {"green", "red", "yellow", "blue", "neutral", "purple"}
KNOWN_DATA_ATTRS = {
    "data-breakout",
    "data-breakout-width",
    "data-card-appearance",
    "data-color",
    "data-extension-key",
    "data-extension-type",
    "data-layout",
    "data-local-id",
    "data-parameters",
    "data-state",
    "data-type",
    "data-user-id",
    "data-width",
}
# Absolute paths that only exist on the author's machine (macOS, Linux, WSL).
# Confluence-relative URLs such as /wiki/download/... stay allowed.
LOCAL_POSIX_PATH = re.compile(
    r"^/(?:Users|home|private|var/folders|tmp|Volumes|mnt|root|opt|etc)(?:/|$)"
)
# HTML elements whose end tag may be omitted; implicit closure is legal.
OPTIONAL_END_TAGS = {
    "p", "li", "dt", "dd", "tr", "td", "th", "thead", "tbody", "tfoot",
    "option", "optgroup", "colgroup", "caption", "rt", "rp",
}


@dataclass
class Finding:
    severity: str
    message: str
    context: str | None = None


@dataclass
class Stats:
    chars: int = 0
    tags: dict[str, int] = field(default_factory=dict)
    panels: int = 0
    statuses: int = 0
    extensions: int = 0
    details: int = 0
    task_lists: int = 0
    decision_lists: int = 0
    code_blocks: int = 0
    links: int = 0
    smart_links: int = 0
    images: int = 0
    embeds: int = 0
    mentions: int = 0
    dates: int = 0
    h1: int = 0
    task_items: int = 0
    decision_items: int = 0


@dataclass
class Inventory:
    extension_keys: Counter[str] = field(default_factory=Counter)
    local_ids: Counter[str] = field(default_factory=Counter)
    link_hrefs: Counter[str] = field(default_factory=Counter)
    image_srcs: Counter[str] = field(default_factory=Counter)
    embed_srcs: Counter[str] = field(default_factory=Counter)
    mention_user_ids: Counter[str] = field(default_factory=Counter)
    date_datetimes: Counter[str] = field(default_factory=Counter)


class BodyChecker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.findings: list[Finding] = []
        self.stats = Stats()
        self.inventory = Inventory()
        self.stack: list[str] = []
        self._status_stack: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value for name, value in attrs}
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        self.stats.tags[tag] = self.stats.tags.get(tag, 0) + 1

        if tag in FORBIDDEN_WRAPPERS:
            self._error(f"Do not include <{tag}> in a Confluence body fragment")
        if tag in FORBIDDEN_TAGS:
            self._error(f"Unsupported tag <{tag}> is not allowed")

        for name in attr_map:
            if name.startswith("on"):
                self._error(f"Inline event handler attribute is not allowed: {name}")
            if name.startswith("data-") and name not in KNOWN_DATA_ATTRS:
                self._error(f"Unknown data attribute is likely to be rejected: {name}")
            if name in {"style", "class"} and tag not in {"code", "pre"}:
                if name == "class":
                    self._error(f"Unsupported class attribute on <{tag}>")
                else:
                    self._warn(f"Avoid styling attribute on <{tag}>: {name}")

        local_id = attr_map.get("data-local-id")
        if local_id:
            self.inventory.local_ids[local_id] += 1

        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"} and self._inside_table_cell():
            self._error(f"Do not put <{tag}> inside table cells; use paragraphs")
        if tag == "h1":
            self.stats.h1 += 1

        data_type = attr_map.get("data-type")
        if data_type:
            if str(data_type).startswith("panel-"):
                self.stats.panels += 1
            elif data_type == "status":
                self.stats.statuses += 1
                self._status_stack.append(
                    {"color": attr_map.get("data-color"), "text": ""}
                )
                color = attr_map.get("data-color")
                if color and color not in VALID_STATUS_COLORS:
                    self._warn(f"Unknown status lozenge color: {color}")
            elif data_type == "extension":
                self.stats.extensions += 1
                extension_key = attr_map.get("data-extension-key")
                if extension_key:
                    self.inventory.extension_keys[extension_key] += 1
                if not attr_map.get("data-extension-key"):
                    self._warn("Extension block is missing data-extension-key")
                if not attr_map.get("data-extension-type"):
                    self._warn("Extension block is missing data-extension-type")
            elif data_type == "task-list":
                self.stats.task_lists += 1
            elif data_type == "task-item":
                self.stats.task_items += 1
            elif data_type == "decision-list":
                self.stats.decision_lists += 1
            elif data_type == "decision-item":
                self.stats.decision_items += 1
            elif data_type == "embed-card":
                self.stats.embeds += 1
            elif data_type == "mention":
                self.stats.mentions += 1
                user_id = attr_map.get("data-user-id")
                if user_id:
                    self.inventory.mention_user_ids[user_id] += 1

        if tag == "details":
            self.stats.details += 1
        if tag == "pre":
            self.stats.code_blocks += 1
        if tag == "a":
            self.stats.links += 1
            href = attr_map.get("href")
            self._check_urlish(href, "href", tag)
            if href:
                self.inventory.link_hrefs[href] += 1
            if attr_map.get("data-card-appearance"):
                self.stats.smart_links += 1
        if tag == "img":
            self.stats.images += 1
            src = attr_map.get("src")
            self._check_urlish(src, "src", tag)
            if src:
                self.inventory.image_srcs[src] += 1
        if tag == "iframe":
            self.stats.embeds += 1
            src = attr_map.get("src")
            self._check_urlish(src, "src", tag)
            if src:
                self.inventory.embed_srcs[src] += 1
            for name in attr_map:
                if name != "src":
                    self._error(f"Iframe attribute is likely to be rejected: {name}")
        if tag == "time":
            value = attr_map.get("datetime")
            if value:
                self.stats.dates += 1
                self.inventory.date_datetimes[value] += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.stack:
            if tag in self.stack:
                while self.stack:
                    popped = self.stack.pop()
                    if popped == tag:
                        break
                    if popped not in OPTIONAL_END_TAGS:
                        self._warn(
                            f"Unclosed <{popped}> was implicitly closed by </{tag}>",
                            "add the missing closing tag or fix the nesting",
                        )
            else:
                self._warn(f"Closing tag </{tag}> did not match open tags")

        if tag == "span" and self._status_stack:
            status = self._status_stack.pop()
            text = (status.get("text") or "").strip()
            if len(text) > 20:
                self._warn(f"Status lozenge text is long and may truncate: {text}")
            if len(text.split()) > 3:
                self._warn(f"Status lozenge should be short: {text}")

    def handle_data(self, data: str) -> None:
        if self._status_stack:
            self._status_stack[-1]["text"] = (self._status_stack[-1]["text"] or "") + data

    def error(self, message: str) -> None:
        self._error(message)

    def _inside_table_cell(self) -> bool:
        return "td" in self.stack or "th" in self.stack

    def _check_urlish(self, value: str | None, attr: str, tag: str) -> None:
        if not value:
            self._warn(f"<{tag}> is missing {attr}")
            return
        lower = value.lower()
        if lower.startswith("data:image/"):
            self._error("Do not embed base64/data URI images in Confluence HTML")
        if lower.startswith("file:"):
            self._error(f"Local file URL is not publishable: {value}")
        elif re.match(r"^[a-zA-Z]:[\\/]", value) or value.startswith("\\\\"):
            self._error(f"Windows local path is not publishable: {value}")
        elif value.startswith("~/") or LOCAL_POSIX_PATH.match(value):
            self._error(f"Local filesystem path is not publishable: {value}")
        elif value.startswith(("./", "../")):
            self._warn(f"Relative {attr} may not work after publish: {value}")
        elif tag in {"img", "iframe"} and not re.match(r"^(?:[a-zA-Z][a-zA-Z0-9+.-]*:|/)", value):
            self._warn(f"Relative {attr} may not work after publish; use a full URL: {value}")

    def _error(self, message: str, context: str | None = None) -> None:
        self.findings.append(Finding("error", message, context))

    def _warn(self, message: str, context: str | None = None) -> None:
        self.findings.append(Finding("warning", message, context))


def read_text(path: str | None) -> str:
    if not path or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def count_extensions(html: str) -> int:
    return len(re.findall(r'data-type\s*=\s*["\']extension["\']', html, re.I))


def raw_checks(html: str) -> list[Finding]:
    findings: list[Finding] = []
    for match in re.finditer(r"<pre\b[^>]*>\s*<code\b[^>]*>(.*?)</code>\s*</pre>", html, re.I | re.S):
        code = match.group(1)
        if re.search(r"(?<!&lt;)<[/A-Za-z][^>]*>", code):
            findings.append(
                Finding(
                    "warning",
                    "Code block may contain unescaped HTML; escape <, >, and & inside code",
                )
            )
    return findings


def duplicate_counter_findings(kind: str, values: Counter[str]) -> list[Finding]:
    findings: list[Finding] = []
    for value, count in values.items():
        if count > 1:
            findings.append(Finding("warning", f"Duplicate {kind}: {value}", str(count)))
    return findings


def parse_body(html: str) -> tuple[Stats, Inventory, list[Finding]]:
    parser = BodyChecker()
    parser.stats.chars = len(html)
    parser.feed(html)
    parser.close()
    findings = parser.findings + raw_checks(html)
    findings.extend(duplicate_counter_findings("data-local-id", parser.inventory.local_ids))
    if parser.stack:
        findings.append(
            Finding("warning", "Unclosed tags remain at end of fragment", ", ".join(parser.stack))
        )
    return parser.stats, parser.inventory, findings


def counter_drop_findings(kind: str, old: Counter[str], new: Counter[str]) -> list[Finding]:
    dropped = old - new
    if not dropped:
        return []

    findings: list[Finding] = []
    for value, count in dropped.most_common(5):
        context = f"{value} ({count})" if count > 1 else value
        findings.append(Finding("warning", f"{kind} dropped from original", context))

    remaining = len(dropped) - 5
    if remaining > 0:
        findings.append(
            Finding("warning", f"{kind} dropped from original", f"{remaining} more")
        )
    return findings


def count_drop_finding(kind: str, old: int, new: int) -> Finding | None:
    if new < old:
        return Finding("warning", f"{kind} count dropped from {old} to {new}")
    return None


def check(html: str, original_html: str | None = None, title: str | None = None) -> tuple[Stats, list[Finding]]:
    stats, inventory, findings = parse_body(html)

    if title and stats.h1:
        h1_texts = [
            m.group(1).strip()
            for m in re.finditer(r"<h1\b[^>]*>(.*?)</h1>", html, re.I | re.S)
        ]
        compact_title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", title)).strip().lower()
        for h1 in h1_texts:
            compact_h1 = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h1)).strip().lower()
            if compact_h1 == compact_title:
                findings.append(
                    Finding(
                        "warning",
                        "Body has an <h1> that duplicates the page title",
                        h1,
                    )
                )

    if original_html is not None:
        old_stats, old_inventory, _ = parse_body(original_html)
        old_extensions = count_extensions(original_html)
        new_extensions = count_extensions(html)
        if new_extensions < old_extensions:
            findings.append(
                Finding(
                    "warning",
                    f"Extension count dropped from {old_extensions} to {new_extensions}",
                )
            )
        findings.extend(
            counter_drop_findings(
                "Extension key", old_inventory.extension_keys, inventory.extension_keys
            )
        )
        findings.extend(
            counter_drop_findings("Link href", old_inventory.link_hrefs, inventory.link_hrefs)
        )
        findings.extend(
            counter_drop_findings("Image source", old_inventory.image_srcs, inventory.image_srcs)
        )
        findings.extend(
            counter_drop_findings("Embed source", old_inventory.embed_srcs, inventory.embed_srcs)
        )
        findings.extend(
            counter_drop_findings(
                "Mention user id",
                old_inventory.mention_user_ids,
                inventory.mention_user_ids,
            )
        )
        findings.extend(
            counter_drop_findings(
                "Date marker", old_inventory.date_datetimes, inventory.date_datetimes
            )
        )
        for item in (
            count_drop_finding("Task item", old_stats.task_items, stats.task_items),
            count_drop_finding("Decision item", old_stats.decision_items, stats.decision_items),
        ):
            if item:
                findings.append(item)

    return stats, findings


def as_dict(stats: Stats, findings: Iterable[Finding]) -> dict[str, object]:
    return {
        "stats": {
            "chars": stats.chars,
            "panels": stats.panels,
            "statuses": stats.statuses,
            "extensions": stats.extensions,
            "details": stats.details,
            "task_lists": stats.task_lists,
            "decision_lists": stats.decision_lists,
            "code_blocks": stats.code_blocks,
            "links": stats.links,
            "smart_links": stats.smart_links,
            "images": stats.images,
            "embeds": stats.embeds,
            "mentions": stats.mentions,
            "dates": stats.dates,
            "h1": stats.h1,
            "task_items": stats.task_items,
            "decision_items": stats.decision_items,
        },
        "findings": [finding.__dict__ for finding in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="HTML body file, or stdin")
    parser.add_argument("--original", help="Original fetched HTML body for preservation checks")
    parser.add_argument("--title", help="Page title, used to catch duplicate body H1")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    html = read_text(args.input)
    original_html = read_text(args.original) if args.original else None
    stats, findings = check(html, original_html=original_html, title=args.title)
    errors = [item for item in findings if item.severity == "error"]
    warnings = [item for item in findings if item.severity == "warning"]

    if args.json:
        print(json.dumps(as_dict(stats, findings), indent=2))
    else:
        print(f"Confluence HTML check: {stats.chars} chars")
        print(
            "Counts: "
            f"panels={stats.panels}, statuses={stats.statuses}, "
            f"extensions={stats.extensions}, details={stats.details}, "
            f"task_lists={stats.task_lists}, task_items={stats.task_items}, "
            f"decision_lists={stats.decision_lists}, decision_items={stats.decision_items}, "
            f"code_blocks={stats.code_blocks}, links={stats.links}, images={stats.images}"
            f", embeds={stats.embeds}, mentions={stats.mentions}, dates={stats.dates}"
        )
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
