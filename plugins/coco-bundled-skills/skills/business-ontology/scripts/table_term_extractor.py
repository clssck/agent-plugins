"""
table_term_extractor.py — Scan INFORMATION_SCHEMA tables/columns for COMMENT fields
and produce ontology node candidates in the standard candidate JSON format.

Usage:
  python table_term_extractor.py \\
      --connection <snow_cli_connection> \\
      --database <db> \\
      --schema <schema> \\
      --output /tmp/table_candidates.json \\
      [--include-columns] \\
      [--domain-map path/to/domain_map.yaml]

Output format (array of candidate objects):
  [{"name": "...", "description": "...", "domainName": "...",
    "itemKind": "TERM|METRIC|ENTITY", "tags": [], "synonyms": []}]

Exit codes:
  0 — success (candidates written to --output or stdout)
  1 — error (message on stderr, no output file written)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# itemKind heuristics
# ---------------------------------------------------------------------------
_METRIC_PATTERNS = re.compile(
    r"(fact|metric|measure|stat|kpi|aggregate|summary|report)s?$",
    re.IGNORECASE,
)
_ENTITY_PATTERNS = re.compile(
    r"(dim|dimension|lookup|master|entity|ref|reference|catalog)s?$",
    re.IGNORECASE,
)


def _infer_item_kind(table_name: str) -> str:
    normalized = table_name.lower().replace(" ", "_")
    last_part = normalized.split("_")[-1]
    if _METRIC_PATTERNS.search(last_part) or _METRIC_PATTERNS.search(normalized):
        return "METRIC"
    if _ENTITY_PATTERNS.search(last_part) or _ENTITY_PATTERNS.search(normalized):
        return "ENTITY"
    return "TERM"


def _normalize_name(raw: str) -> str:
    """Convert TABLE_NAME or table_name to Title Case human label."""
    return raw.replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------------------
# Domain resolution
# ---------------------------------------------------------------------------

def _load_domain_map(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    import yaml  # type: ignore[import]
    with open(path) as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _resolve_domain(
    database: str,
    schema: str,
    domain_map: dict[str, str],
) -> str:
    key = f"{database}.{schema}".upper()
    if key in domain_map:
        return domain_map[key]
    key_schema = schema.upper()
    if key_schema in domain_map:
        return domain_map[key_schema]
    # Heuristic: strip common prefixes (DW_, DWH_, STG_, etc.) and use what's left
    clean = re.sub(r"^(DW_|DWH_|STG_|STAGING_|RAW_|PROD_|DEV_)", "", schema, flags=re.IGNORECASE)
    return clean.replace("_", " ").title() if clean else "Default"


# ---------------------------------------------------------------------------
# Identifier validation
# ---------------------------------------------------------------------------

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_$]+$")


def _validate_identifier(value: str, label: str) -> None:
    """Reject values that are not safe Snowflake identifiers.

    Prevents SQL injection when identifiers are interpolated into queries
    (snow sql has no bind-variable support). Only alphanumerics, underscores,
    and dollar signs are allowed — quotes, spaces, and special characters are
    rejected before any query runs.
    """
    if not _SAFE_IDENTIFIER.match(value):
        raise ValueError(
            f"--{label} contains characters not allowed in a Snowflake identifier: {value!r}"
        )


# ---------------------------------------------------------------------------
# Snowflake query helpers
# ---------------------------------------------------------------------------

def _run_sql(connection: str | None, sql: str) -> list[dict[str, Any]]:
    # Uses `snow sql` rather than the `cortex` CLI because these scripts run
    # outside the agent session (invoked by the steward directly), where only
    # the Snowflake CLI is guaranteed to be available.
    cmd = ["snow", "sql", "--format", "json", "-q", sql]
    if connection:
        cmd += ["--connection", connection]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"snow sql exited {result.returncode}")
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Could not parse snow sql output: {exc}") from exc
    return rows if isinstance(rows, list) else []


def _fetch_tables(
    connection: str | None,
    database: str,
    schema: str,
) -> list[dict[str, Any]]:
    sql = f"""
SELECT TABLE_NAME, COMMENT
FROM {database}.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '{schema.upper()}'
  AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
  AND COMMENT IS NOT NULL
  AND COMMENT != ''
ORDER BY TABLE_NAME
"""
    return _run_sql(connection, sql.strip())


def _fetch_columns(
    connection: str | None,
    database: str,
    schema: str,
) -> list[dict[str, Any]]:
    sql = f"""
SELECT TABLE_NAME, COLUMN_NAME, COMMENT
FROM {database}.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '{schema.upper()}'
  AND COMMENT IS NOT NULL
  AND COMMENT != ''
ORDER BY TABLE_NAME, ORDINAL_POSITION
"""
    return _run_sql(connection, sql.strip())


# ---------------------------------------------------------------------------
# Candidate builders
# ---------------------------------------------------------------------------

_SKIP_SUFFIXES = re.compile(
    r"_(id|key|uuid|pk|fk|at|date|time|flag|ind|indicator|num|no|nr)$",
    re.IGNORECASE,
)


def _should_skip_column(column_name: str) -> bool:
    return bool(_SKIP_SUFFIXES.search(column_name.lower()))


def _build_table_candidates(
    rows: list[dict[str, Any]],
    database: str,
    schema: str,
    domain_map: dict[str, str],
) -> list[dict[str, Any]]:
    domain = _resolve_domain(database, schema, domain_map)
    candidates = []
    for row in rows:
        raw_name = row.get("TABLE_NAME") or row.get("table_name") or ""
        comment = row.get("COMMENT") or row.get("comment") or ""
        if not raw_name or not comment.strip():
            continue
        name = _normalize_name(raw_name)
        candidates.append(
            {
                "name": name,
                "description": comment.strip(),
                "domainName": domain,
                "itemKind": _infer_item_kind(raw_name),
                "tags": [],
                "synonyms": [{"text": raw_name}] if raw_name.upper() != name.upper() else [],
            }
        )
    return candidates


def _build_column_candidates(
    rows: list[dict[str, Any]],
    database: str,
    schema: str,
    domain_map: dict[str, str],
) -> list[dict[str, Any]]:
    domain = _resolve_domain(database, schema, domain_map)
    candidates = []
    for row in rows:
        raw_col = row.get("COLUMN_NAME") or row.get("column_name") or ""
        comment = row.get("COMMENT") or row.get("comment") or ""
        if not raw_col or not comment.strip():
            continue
        if _should_skip_column(raw_col):
            continue
        name = _normalize_name(raw_col)
        candidates.append(
            {
                "name": name,
                "description": comment.strip(),
                "domainName": domain,
                "itemKind": "TERM",
                "tags": ["column-derived"],
                "synonyms": [{"text": raw_col}] if raw_col.upper() != name.upper() else [],
            }
        )
    return candidates


def _deduplicate(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for c in candidates:
        key = (c["name"].lower(), c["domainName"].lower())
        if key not in seen:
            seen[key] = c
        else:
            existing = seen[key]
            if len(c["description"]) > len(existing["description"]):
                seen[key] = c
    return list(seen.values())


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract ontology data candidates from INFORMATION_SCHEMA comments."
    )
    parser.add_argument("--connection", default=None, help="Snowflake CLI connection name")
    parser.add_argument("--database", required=True, help="Snowflake database to scan")
    parser.add_argument("--schema", required=True, help="Schema within the database to scan")
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path; omit to print to stdout",
    )
    parser.add_argument(
        "--include-columns",
        action="store_true",
        default=False,
        help="Also extract columns with non-empty COMMENT (generates many candidates for large schemas)",
    )
    parser.add_argument(
        "--domain-map",
        default=None,
        help="YAML file mapping DB.SCHEMA (or SCHEMA) to domain name",
    )
    args = parser.parse_args()

    try:
        _validate_identifier(args.database, "database")
        _validate_identifier(args.schema, "schema")
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)

    domain_map = _load_domain_map(args.domain_map)

    try:
        table_rows = _fetch_tables(args.connection, args.database, args.schema)
    except RuntimeError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)

    candidates = _build_table_candidates(table_rows, args.database, args.schema, domain_map)

    if args.include_columns:
        try:
            col_rows = _fetch_columns(args.connection, args.database, args.schema)
        except RuntimeError as exc:
            print(json.dumps({"error": str(exc)}), file=sys.stderr)
            sys.exit(1)
        candidates += _build_column_candidates(col_rows, args.database, args.schema, domain_map)

    candidates = _deduplicate(candidates)

    output = json.dumps(candidates, indent=2)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Wrote {len(candidates)} candidate(s) to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
