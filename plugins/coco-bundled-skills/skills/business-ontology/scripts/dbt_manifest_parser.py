"""
dbt_manifest_parser.py — Parse a dbt manifest.json and produce ontology node candidates
in the standard candidate JSON format.

Supports:
  - dbt manifest v7 through v12 (manifest_schema_version 7–12)
  - Local file path or Snowflake stage URI (@DB.SCHEMA.STAGE/path/manifest.json)

Usage:
  python dbt_manifest_parser.py \\
      --manifest path/to/manifest.json \\
      --output /tmp/dbt_candidates.json

  python dbt_manifest_parser.py \\
      --manifest @MY_DB.MY_SCHEMA.MY_STAGE/target/manifest.json \\
      --connection my_conn \\
      --output /tmp/dbt_candidates.json

Output format (array of candidate objects):
  [{"name": "...", "description": "...", "domainName": "...",
    "itemKind": "TERM|METRIC|ENTITY", "tags": [], "synonyms": []}]

Exit codes:
  0 — success
  1 — error (message on stderr, no output file written)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Stage download
# ---------------------------------------------------------------------------

def _download_from_stage(stage_uri: str, connection: str | None, warehouse: str | None = None) -> tuple[str, str]:
    """Download a stage file into a temp directory.

    Returns (local_file_path, tmp_dir) — the caller owns tmp_dir and must
    remove it when done. Uses a directory target because Snowflake GET requires
    a directory, not a file path: GET @stage/file file://local_dir/

    Uses `snow sql` rather than the `cortex` CLI because these scripts run
    outside the agent session where only the Snowflake CLI is guaranteed available.
    """
    tmp_dir = tempfile.mkdtemp(suffix="_dbt_manifest")
    # Snowflake GET requires a trailing slash on the directory target
    get_sql = f"GET {stage_uri} file://{tmp_dir}/"
    full_sql = f"USE WAREHOUSE {warehouse}; {get_sql}" if warehouse else get_sql
    cmd = [
        "snow", "sql", "--format", "json", "-q", full_sql,
    ]
    if connection:
        cmd += ["--connection", connection]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(
            f"Failed to download {stage_uri}: {result.stderr.strip()}"
        )
    # GET downloads the file with its original name; find it in the directory
    candidates = sorted(Path(tmp_dir).iterdir())
    if not candidates:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise RuntimeError(f"GET succeeded but no file found in {tmp_dir} for {stage_uri}")
    return str(candidates[0]), tmp_dir


# ---------------------------------------------------------------------------
# Domain resolution
# ---------------------------------------------------------------------------

def _resolve_domain(node: dict[str, Any], package_name: str) -> str:
    meta = node.get("meta") or {}
    if isinstance(meta, dict):
        for key in ("domain", "business_domain", "glossary_domain", "ontology_domain"):
            if key in meta and meta[key]:
                return str(meta[key]).strip()
        tags: list = node.get("tags") or []
        for tag in tags:
            if isinstance(tag, str) and tag.startswith("domain:"):
                return tag[len("domain:"):].strip()
    if package_name:
        clean = re.sub(r"^(dbt_|project_|pkg_)", "", package_name, flags=re.IGNORECASE)
        return clean.replace("_", " ").title()
    return "Default"


# ---------------------------------------------------------------------------
# Node parsers
# ---------------------------------------------------------------------------

_SKIP_MODEL_PREFIXES = re.compile(
    r"^(stg_|staging_|raw_|base_|int_|intermediate_|tmp_|temp_)",
    re.IGNORECASE,
)


def _node_to_name(raw: str) -> str:
    """Convert dbt node name (snake_case) to Title Case."""
    return raw.replace("_", " ").title()


def _parse_models(
    nodes: dict[str, Any],
    package_name: str,
) -> list[dict[str, Any]]:
    candidates = []
    for unique_id, node in nodes.items():
        if node.get("resource_type") not in ("model", "seed"):
            continue
        raw_name = node.get("name") or ""
        if not raw_name:
            continue
        if _SKIP_MODEL_PREFIXES.match(raw_name):
            continue
        description = (node.get("description") or "").strip()
        if not description:
            continue
        name = _node_to_name(raw_name)
        domain = _resolve_domain(node, package_name)
        synonyms = []
        meta = node.get("meta") or {}
        if isinstance(meta, dict):
            for s in meta.get("synonyms") or []:
                synonyms.append({"text": str(s)})
        if raw_name.lower() != name.lower():
            synonyms.append({"text": raw_name})
        label = node.get("label") or ""
        if label and label.lower() != name.lower() and label not in {s["text"] for s in synonyms}:
            synonyms.append({"text": label})
        tags = [str(t) for t in (node.get("tags") or []) if not str(t).startswith("domain:")]
        candidates.append(
            {
                "name": name,
                "description": description,
                "domainName": domain,
                "itemKind": "ENTITY",
                "tags": tags,
                "synonyms": synonyms,
            }
        )
    return candidates


def _parse_metrics(
    metrics: dict[str, Any],
    package_name: str,
) -> list[dict[str, Any]]:
    candidates = []
    for unique_id, metric in metrics.items():
        raw_name = metric.get("name") or ""
        if not raw_name:
            continue
        label = (metric.get("label") or "").strip()
        description = (metric.get("description") or "").strip()
        name = label if label else _node_to_name(raw_name)
        domain = _resolve_domain(metric, package_name)
        synonyms = []
        if raw_name.lower() != name.lower():
            synonyms.append({"text": raw_name})
        if label and label.lower() != name.lower() and label not in {s["text"] for s in synonyms}:
            synonyms.append({"text": label})
        full_description = description
        calculation_method = metric.get("calculation_method") or metric.get("type") or ""
        expression = metric.get("expression") or ""
        if calculation_method and expression:
            formula_note = f"Formula: {calculation_method}({expression})."
            full_description = (
                f"{description} {formula_note}".strip() if description else formula_note
            )
        tags = [str(t) for t in (metric.get("tags") or []) if not str(t).startswith("domain:")]
        candidates.append(
            {
                "name": name,
                "description": full_description or name,
                "domainName": domain,
                "itemKind": "METRIC",
                "tags": tags,
                "synonyms": synonyms,
            }
        )
    return candidates


def _parse_exposures(
    exposures: dict[str, Any],
    package_name: str,
) -> list[dict[str, Any]]:
    candidates = []
    for unique_id, exposure in exposures.items():
        raw_name = exposure.get("name") or ""
        if not raw_name:
            continue
        label = (exposure.get("label") or "").strip()
        description = (exposure.get("description") or "").strip()
        if not description:
            continue
        name = label if label else _node_to_name(raw_name)
        domain = _resolve_domain(exposure, package_name)
        item_kind = "ENTITY"
        synonyms = []
        if raw_name.lower() != name.lower():
            synonyms.append({"text": raw_name})
        tags = [str(t) for t in (exposure.get("tags") or []) if not str(t).startswith("domain:")]
        candidates.append(
            {
                "name": name,
                "description": description,
                "domainName": domain,
                "itemKind": item_kind,
                "tags": tags,
                "synonyms": synonyms,
            }
        )
    return candidates


def _parse_sources(
    sources: dict[str, Any],
    package_name: str,
) -> list[dict[str, Any]]:
    candidates = []
    for unique_id, source in sources.items():
        raw_name = source.get("name") or ""
        if not raw_name:
            continue
        description = (source.get("description") or "").strip()
        if not description:
            continue
        name = _node_to_name(raw_name)
        domain = _resolve_domain(source, package_name)
        synonyms = []
        if raw_name.lower() != name.lower():
            synonyms.append({"text": raw_name})
        tags = ["source-derived"] + [
            str(t) for t in (source.get("tags") or []) if not str(t).startswith("domain:")
        ]
        candidates.append(
            {
                "name": name,
                "description": description,
                "domainName": domain,
                "itemKind": "ENTITY",
                "tags": tags,
                "synonyms": synonyms,
            }
        )
    return candidates


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple, dict[str, Any]] = {}
    for c in candidates:
        key = (c["name"].lower(), c["domainName"].lower(), c.get("itemKind", ""))
        if key not in seen:
            seen[key] = c
        else:
            existing = seen[key]
            if len(c.get("description", "")) > len(existing.get("description", "")):
                seen[key] = c
    return list(seen.values())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse a dbt manifest.json and produce ontology node candidates."
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Local path or Snowflake stage URI (@DB.SCHEMA.STAGE/path) to manifest.json",
    )
    parser.add_argument(
        "--connection",
        default=None,
        help="Snowflake CLI connection name (required for stage URIs)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path; omit to print to stdout",
    )
    parser.add_argument(
        "--no-models",
        action="store_true",
        default=False,
        help="Skip model nodes",
    )
    parser.add_argument(
        "--no-metrics",
        action="store_true",
        default=False,
        help="Skip metric nodes",
    )
    parser.add_argument(
        "--no-exposures",
        action="store_true",
        default=False,
        help="Skip exposure nodes",
    )
    parser.add_argument(
        "--no-sources",
        action="store_true",
        default=False,
        help="Skip source nodes",
    )
    parser.add_argument(
        "--warehouse",
        default=None,
        help="Warehouse to USE before running queries (for stage downloads)",
    )
    args = parser.parse_args()

    # Validate warehouse identifier if provided
    if args.warehouse and not re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", args.warehouse):
        print(json.dumps({"error": f"--warehouse contains unsafe characters: {args.warehouse!r}"}), file=sys.stderr)
        sys.exit(1)

    manifest_path = args.manifest
    tmp_dir = None

    if manifest_path.startswith("@"):
        try:
            manifest_path, tmp_dir = _download_from_stage(manifest_path, args.connection, args.warehouse)
        except RuntimeError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            sys.exit(1)

    try:
        manifest_text = Path(manifest_path).read_text()
        manifest = json.loads(manifest_text)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": f"Could not read manifest: {exc}"}), file=sys.stderr)
        sys.exit(1)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    metadata = manifest.get("metadata") or {}
    package_name = metadata.get("project_name") or ""

    candidates: list[dict[str, Any]] = []

    if not args.no_models:
        candidates += _parse_models(manifest.get("nodes") or {}, package_name)
        candidates += _parse_sources(manifest.get("sources") or {}, package_name)

    if not args.no_metrics:
        candidates += _parse_metrics(manifest.get("metrics") or {}, package_name)

    if not args.no_exposures:
        candidates += _parse_exposures(manifest.get("exposures") or {}, package_name)

    candidates = _deduplicate(candidates)

    output = json.dumps(candidates, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Wrote {len(candidates)} candidate(s) to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
