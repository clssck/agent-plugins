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
in <prefix>-metadata.json. Use a separate --out-dir per extraction when pulling
both the HTML and ADF of one page; the metadata file name is fixed per prefix.

Usage: uv run extract_confluence_fetch.py response.json --out-dir scratch/html --prefix fetched
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


def body_kind(body: Any) -> str:
    if isinstance(body, str):
        return "html"
    if isinstance(body, dict) and body.get("type") == "doc":
        return "adf"
    return "json"


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
    body = page.get("body")
    kind = body_kind(body)
    out_dir.mkdir(parents=True, exist_ok=True)

    if kind == "html":
        body_path = out_dir / f"{prefix}.html"
        body_text = body
    elif kind == "adf":
        body_path = out_dir / f"{prefix}-adf.json"
        body_text = json.dumps(body, indent=2)
    else:
        body_path = out_dir / f"{prefix}-body.json"
        body_text = json.dumps(body, indent=2)

    metadata_path = out_dir / f"{prefix}-metadata.json"

    for path in (body_path, metadata_path):
        if path.exists() and not force:
            raise FileExistsError(f"Refusing to overwrite existing file: {path}")

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
        payload = unwrap_tool_output(read_json(args.input))
        if not isinstance(payload, dict):
            raise ValueError("Input does not contain a Confluence page object")
        result = write_outputs(payload, Path(args.out_dir), args.prefix, args.force)
    except (OSError, ValueError) as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, indent=2))
        else:
            print(f"ERROR: {exc}")
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Wrote {result['bodyType']} body: {result['body']}")
        print(f"Wrote metadata: {result['metadata']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
