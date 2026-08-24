#!/usr/bin/env python3
"""Shared helpers for sv-ingest scripts."""
from __future__ import annotations

import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


def run_snow(
    connection: str,
    sql: str,
    *,
    role: str = "",
    warehouse: str = "",
) -> Any:
    """Run a SQL statement via `snow sql --format JSON` and return parsed rows.

    connection / role / warehouse are optional: when empty, the snow CLI default
    connection (and its default role/warehouse) is used. This keeps the scripts
    account-agnostic for shipping.
    """
    cmd = ["snow", "sql", "--format", "JSON", "-q", sql]
    if connection:
        cmd[2:2] = ["-c", connection]
    if role:
        cmd += ["--role", role]
    if warehouse:
        cmd += ["--warehouse", warehouse]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout or f"snow failed: {sql[:120]}")
    text = proc.stdout.strip()
    if not text:
        return []
    return json.loads(text)


def run_snow_batch(
    connection: str,
    sqls: list[str],
    *,
    role: str = "",
    warehouse: str = "",
) -> list[Any]:
    """Run many statements in a SINGLE `snow` process and return one result set per statement.

    `snow sql --format JSON` returns a JSON array of result sets when multiple statements
    are submitted (and a flat row list for a single statement). This collapses N process
    startups into 1, which matters a lot for the per-term asset inversion (one CALL per term).
    """
    if not sqls:
        return []
    joined = "\n".join(s if s.strip().endswith(";") else s + ";" for s in sqls)
    result = run_snow(connection, joined, role=role, warehouse=warehouse)
    if len(sqls) == 1:
        return [result]
    if not isinstance(result, list):
        return [[] for _ in sqls]
    # Normalize: multi-statement output is a list of result sets (each a list of rows).
    return [rs if isinstance(rs, list) else [rs] for rs in result]


def unwrap_procedure_json(rows: list[dict[str, Any]], key_hint: str = "SYSTEM$") -> dict[str, Any]:
    if not rows:
        return {}
    row = rows[0]
    for key, val in row.items():
        if key_hint in key and isinstance(val, str):
            return json.loads(val)
    return {}


def load_domain_map(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {"rules": [], "default_domain": "Default"}
    data = yaml.safe_load(Path(path).read_text()) or {}
    data.setdefault("rules", [])
    data.setdefault("default_domain", "Default")
    return data


def resolve_domain(
    database: str,
    schema: str,
    sv_name: str,
    domain_map: dict[str, Any],
) -> str:
    for rule in domain_map.get("rules", []):
        match = rule.get("match", {})
        if match.get("database") and match["database"].upper() != database.upper():
            continue
        if match.get("schema") and match["schema"].upper() != schema.upper():
            continue
        pattern = match.get("semantic_view_name_like")
        if pattern:
            fn_pat = pattern.replace("%", "*").replace("_", "?")
            if not fnmatch.fnmatchcase(sv_name.upper(), fn_pat.upper()):
                continue
        return rule["domain"]
    return domain_map.get("default_domain", "Default")


def humanize(name: str) -> str:
    return re.sub(r"\s+", " ", name.replace("_", " ").strip().title())


def normalize_expr(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", "", s.upper())


def normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().upper())


# SQL tokens that appear in metric/dimension expressions but are not columns.
_EXPR_STOPWORDS = {
    "SUM", "COUNT", "AVG", "MIN", "MAX", "DISTINCT", "CASE", "WHEN", "THEN",
    "ELSE", "END", "AND", "OR", "NOT", "NULL", "COALESCE", "CAST", "AS",
    "OVER", "PARTITION", "BY", "RATIO_TO_REPORT", "MEDIAN", "STDDEV", "VAR",
    "IFF", "NULLIF", "DIV0", "ROUND", "ABS", "GREATEST", "LEAST", "DATE",
    "TRUE", "FALSE", "IN", "IS", "LIKE", "BETWEEN",
}

_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def extract_referenced_columns(expression: str | None, known_columns: set[str]) -> list[str]:
    """Return the physical columns (uppercased) referenced by an SV expression.

    Intersects identifier tokens in the expression with the base table's real
    column set, so function names / keywords are naturally excluded.
    """
    if not expression:
        return []
    known_upper = {c.upper() for c in known_columns}
    found: list[str] = []
    for tok in _IDENT_RE.findall(expression):
        up = tok.upper()
        if up in _EXPR_STOPWORDS:
            continue
        if up in known_upper and up not in found:
            found.append(up)
    return found


def get_table_columns(
    connection: str, table_fqn: str, warehouse: str = "", role: str = ""
) -> list[str]:
    try:
        rows = run_snow(connection, f"SHOW COLUMNS IN TABLE {table_fqn}", warehouse=warehouse, role=role)
    except RuntimeError:
        return []
    return [r.get("column_name", "") for r in rows if r.get("column_name")]


def object_type_to_ref_type(object_type: str | None) -> str:
    mapping = {
        "table": "TABLE",
        "view": "VIEW",
        "column": "COLUMN",
        "semantic view": "SEMANTIC_VIEW",
        "dashboard": "DASHBOARD",
        "external object": "EXTERNAL_OBJECT",
    }
    return mapping.get((object_type or "").strip().lower(), (object_type or "").upper())
