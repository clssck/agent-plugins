#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Extract Confluence page fetch results into audit-ready files.

This accepts raw JSON from the Atlassian MCP Confluence content/page read tool
(getConfluenceContent, or getConfluencePage on older servers), including common
tool-output wrappers such as [{"type":"text","text":"{...}"}]. It writes
the fetched body to <prefix>.html or <prefix>-adf.json and stores page metadata
in <prefix>-metadata.json. Every MCP text block is inspected; exactly one page
object with an id and an HTML or ADF body must be present, otherwise the script
exits 2 without writing files. Use a separate --out-dir per extraction when
pulling both the HTML and ADF of one page; the metadata file name is fixed per prefix.

Usage: uv run "$(realpath skill://confluence-html-editor/scripts/extract_confluence_fetch.py)" "$(realpath local://html-response.json)" --out-dir "$(realpath local://)/html" --prefix fetched
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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


def unwrap_tool_output(payload: Any) -> Any:
    payload = maybe_json(payload)
    if isinstance(payload, list) and len(payload) == 1:
        item = payload[0]
        if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
            return unwrap_tool_output(item["text"])
    if isinstance(payload, dict) and "content" in payload and isinstance(payload["content"], list):
        content = payload["content"]
        if len(content) == 1 and isinstance(content[0], dict) and content[0].get("type") == "text":
            return unwrap_tool_output(content[0].get("text"))
    return payload


def page_body(page: dict[str, Any]) -> tuple[str, Any] | None:
    """Return (kind, body) for a supported HTML or ADF page body, else None."""
    body = page.get("body")
    if isinstance(body, dict) and "atlas_doc_format" in body:
        wrapper = body["atlas_doc_format"]
        body = wrapper.get("value") if isinstance(wrapper, dict) else None
    if isinstance(body, str):
        decoded = maybe_json(body)
        if isinstance(decoded, dict) and decoded.get("type") == "doc":
            return "adf", decoded
        return "html", body
    if isinstance(body, dict) and body.get("type") == "doc":
        return "adf", body
    return None


def has_page_id(value: dict[str, Any]) -> bool:
    page_id = value.get("id")
    if isinstance(page_id, bool):
        return False
    if isinstance(page_id, int):
        return True
    return isinstance(page_id, str) and bool(page_id.strip())


def collect_pages(value: Any, pages: list[dict[str, Any]], bodiless: list[str]) -> None:
    """Walk every nested value and MCP text block, collecting page objects."""
    value = maybe_json(value)
    if isinstance(value, list):
        for item in value:
            collect_pages(item, pages, bodiless)
        return
    if not isinstance(value, dict):
        return
    if has_page_id(value):
        if page_body(value) is not None:
            pages.append(value)
            return
        bodiless.append(str(value["id"]))
    for item in value.values():
        collect_pages(item, pages, bodiless)


def select_page(payload: Any) -> dict[str, Any]:
    """Return the single page object with an id and an HTML or ADF body."""
    pages: list[dict[str, Any]] = []
    bodiless: list[str] = []
    collect_pages(payload, pages, bodiless)
    unique: list[dict[str, Any]] = []
    for page in pages:
        if page not in unique:
            unique.append(page)
    if len(unique) == 1:
        return unique[0]
    if unique:
        ids = ", ".join(str(page["id"]) for page in unique)
        raise ValueError(f"Input contains {len(unique)} different page objects (ids: {ids}); save one page fetch per file")
    detail = ""
    if bodiless:
        detail = f"; objects with id {', '.join(bodiless)} have no HTML or ADF body (null, missing, or summary-only)"
    raise ValueError(f"Input does not contain a Confluence page object with an id and an HTML or ADF body{detail}")


def page_metadata(page: dict[str, Any], body_type: str) -> dict[str, Any]:
    keys = (
        "id",
        "type",
        "status",
        "title",
        "spaceId",
        "parentId",
        "parentType",
        "createdAt",
    )
    metadata = {key: page.get(key) for key in keys if key in page}
    metadata["bodyType"] = body_type
    if isinstance(page.get("version"), dict):
        metadata["version"] = page["version"]
    if isinstance(page.get("links"), dict):
        metadata["links"] = page["links"]
    return metadata


def write_outputs(page: dict[str, Any], out_dir: Path, prefix: str, force: bool = False) -> dict[str, str]:
    resolved = page_body(page)
    if resolved is None:
        raise ValueError("Page object has no HTML or ADF body")
    kind, body = resolved

    if kind == "html":
        body_path = out_dir / f"{prefix}.html"
        body_text = body
    else:
        body_path = out_dir / f"{prefix}-adf.json"
        body_text = json.dumps(body, indent=2)

    metadata_path = out_dir / f"{prefix}-metadata.json"

    for path in (body_path, metadata_path):
        if path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file: {path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    body_path.write_text(body_text, encoding="utf-8")
    metadata_path.write_text(
        json.dumps(page_metadata(page, kind), indent=2),
        encoding="utf-8",
    )
    return {"body": str(body_path), "metadata": str(metadata_path), "bodyType": kind}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", default="-", help="Saved page fetch JSON, or stdin")
    parser.add_argument("--out-dir", default=".", help="Output directory")
    parser.add_argument("--prefix", default="fetched", help="Output filename prefix")
    parser.add_argument("--force", action="store_true", help="Overwrite existing output files")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    args = parser.parse_args()

    try:
        page = select_page(read_json(args.input))
        result = write_outputs(page, Path(args.out_dir), args.prefix, args.force)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Wrote {result['bodyType']} body: {result['body']}")
        print(f"Wrote metadata: {result['metadata']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
