#!/usr/bin/env python3
"""discover_usage.py — Authority signal for discovery: hot tables, Streamlits, and semantic views.

SQL-only. No cortex search calls — search is handled by the fast-pass snowflake_object_search
batch in the skill. This script runs three ACCOUNT_USAGE queries in parallel and is launched
at T=0 alongside the search calls. Results fold in silently after the fast-pass draft is
rendered.

Usage:
    python discover_usage.py [--lookback-days 30] [--connection <name>]

Output: JSON with hot_tables, hot_streamlits, hot_svs, and an optional fallbacks key.
Each query is independent — a permission error on one does not block the others.

The agent cross-references these results with the fast-pass search hits:
  - hot_tables    → re-order schema groups by distinct_users; add tables not in search
  - hot_streamlits → annotate search hits that appear in usage; add usage-only apps
  - hot_svs       → same annotation pattern as hot_streamlits
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

_SUBPROCESS_TIMEOUT = 120  # seconds — ACCOUNT_USAGE queries scan large history tables
_TEMP_MIN_USERS = 5        # noise threshold: TEMP.* and _PREVIEW__ items below this are dropped
_MIN_USERS = 2             # global minimum distinct-user count for all sources


def _run_sql(sql: str, connection: str | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Run SQL via snow CLI. Returns (rows, success_flag)."""
    cmd = ["snow", "sql", "-q", sql, "--format", "json"]
    if connection:
        cmd.extend(["-c", connection])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(json.dumps({"warning": "snow sql timed out"}), file=sys.stderr)
        return [], False
    if result.returncode != 0:
        err = result.stderr.strip()
        if any(k in err.lower() for k in ("access control error", "insufficient privileges", "does not exist")):
            return [], False
        print(json.dumps({"warning": f"snow sql failed: {err[:200]}"}), file=sys.stderr)
        return [], False
    try:
        rows = json.loads(result.stdout)
        return (rows if isinstance(rows, list) else []), True
    except json.JSONDecodeError:
        return [], False


def _noise_filter(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop TEMP.* and _PREVIEW__ entries below the noise threshold."""
    out = []
    for item in items:
        fqn = (item.get("fqn") or "").upper()
        users = item.get("distinct_users", 0)
        if fqn.startswith("TEMP.") and users < _TEMP_MIN_USERS:
            continue
        if "._PREVIEW__" in fqn and users < _TEMP_MIN_USERS:
            continue
        out.append(item)
    return out


def _normalize_key(row: dict[str, Any], key: str) -> Any:
    """Read a column that snow CLI may return as uppercase or lowercase."""
    return row.get(key.upper()) or row.get(key.lower())


# ---------------------------------------------------------------------------
# Hot tables
# ---------------------------------------------------------------------------

def _hot_tables_sql(days: int) -> str:
    return f"""
    SELECT
      object_modified.value:"objectName"::STRING AS fqn,
      object_modified.value:"objectDomain"::STRING AS domain_,
      COUNT(*) AS access_count,
      COUNT(DISTINCT user_name) AS distinct_users,
      MAX(query_start_time)::DATE AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
         LATERAL FLATTEN(input => direct_objects_accessed) object_modified
    WHERE query_start_time > CURRENT_TIMESTAMP - INTERVAL '{days} days'
      AND object_modified.value:"objectDomain"::STRING IN ('Table', 'View')
    GROUP BY 1, 2
    ORDER BY access_count DESC
    LIMIT 200;
    """


def query_hot_tables(
    lookback_days: int, connection: str | None
) -> tuple[list[dict[str, Any]], bool]:
    """Query ACCESS_HISTORY for hot tables and views.

    Auto-widens to 90 days if the initial window yields fewer than 3 distinct schemas,
    matching the rule in DISCOVERY.md.
    """
    rows, ok = _run_sql(_hot_tables_sql(lookback_days), connection)
    if not ok:
        return [], False

    def _schemas(r_list: list[dict[str, Any]]) -> set[str]:
        out = set()
        for r in r_list:
            fqn = _normalize_key(r, "fqn") or ""
            parts = str(fqn).rsplit(".", 1)
            if len(parts) == 2:
                out.add(parts[0].upper())
        return out

    if len(_schemas(rows)) < 3 and lookback_days < 90:
        wider_rows, wider_ok = _run_sql(_hot_tables_sql(90), connection)
        if wider_ok and wider_rows:
            rows = wider_rows

    normalized = [
        {
            "fqn": str(_normalize_key(r, "fqn") or ""),
            "domain": str(_normalize_key(r, "domain_") or ""),
            "access_count": int(_normalize_key(r, "access_count") or 0),
            "distinct_users": int(_normalize_key(r, "distinct_users") or 0),
            "last_accessed": str(_normalize_key(r, "last_accessed") or ""),
        }
        for r in rows
        if _normalize_key(r, "fqn")
    ]
    return _noise_filter(normalized), True


# ---------------------------------------------------------------------------
# Hot Streamlits
# ---------------------------------------------------------------------------

def query_hot_streamlits(
    lookback_days: int, connection: str | None
) -> tuple[list[dict[str, Any]], bool]:
    """Query AGGREGATE_QUERY_HISTORY for hot Streamlit apps ranked by distinct_users."""
    sql = f"""
    WITH raw AS (
        SELECT
            TRY_PARSE_JSON(query_tag):"StreamlitName"::STRING AS streamlit_fqn,
            SUM(calls) AS query_count,
            COUNT(DISTINCT user_name) AS distinct_users
        FROM SNOWFLAKE.ACCOUNT_USAGE.AGGREGATE_QUERY_HISTORY
        WHERE interval_start_time > CURRENT_TIMESTAMP - INTERVAL '{lookback_days} days'
            AND query_tag LIKE '%StreamlitEngine%'
            AND query_tag LIKE '%StreamlitName%'
            AND TRY_PARSE_JSON(query_tag):"StreamlitName" IS NOT NULL
        GROUP BY 1
        HAVING distinct_users >= {_MIN_USERS}
    )
    SELECT * FROM raw
    ORDER BY distinct_users DESC
    LIMIT 100;
    """
    rows, ok = _run_sql(sql, connection)
    if not ok:
        return [], False

    normalized = [
        {
            "fqn": str(_normalize_key(r, "streamlit_fqn") or ""),
            "query_count": int(_normalize_key(r, "query_count") or 0),
            "distinct_users": int(_normalize_key(r, "distinct_users") or 0),
        }
        for r in rows
        if _normalize_key(r, "streamlit_fqn")
    ]
    return _noise_filter(normalized), True


# ---------------------------------------------------------------------------
# Hot semantic views
# ---------------------------------------------------------------------------

def query_hot_svs(
    lookback_days: int, connection: str | None
) -> tuple[list[dict[str, Any]], bool]:
    """Query ACCESS_HISTORY for hot semantic views ranked by distinct_users."""
    sql = f"""
    SELECT
      object_modified.value:"objectName"::STRING AS fqn,
      COUNT(*) AS access_count,
      COUNT(DISTINCT user_name) AS distinct_users,
      MAX(query_start_time)::DATE AS last_accessed
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY,
         LATERAL FLATTEN(input => direct_objects_accessed) object_modified
    WHERE query_start_time > CURRENT_TIMESTAMP - INTERVAL '{lookback_days} days'
      AND object_modified.value:"objectDomain"::STRING = 'Semantic View'
    GROUP BY 1
    HAVING distinct_users >= {_MIN_USERS}
    ORDER BY distinct_users DESC
    LIMIT 50;
    """
    rows, ok = _run_sql(sql, connection)
    if not ok:
        return [], False

    normalized = [
        {
            "fqn": str(_normalize_key(r, "fqn") or ""),
            "access_count": int(_normalize_key(r, "access_count") or 0),
            "distinct_users": int(_normalize_key(r, "distinct_users") or 0),
            "last_accessed": str(_normalize_key(r, "last_accessed") or ""),
        }
        for r in rows
        if _normalize_key(r, "fqn")
    ]
    return _noise_filter(normalized), True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Authority signal for discovery: hot tables, Streamlits, and semantic views. "
            "Launched at T=0 alongside snowflake_object_search calls; results fold in silently."
        )
    )
    parser.add_argument(
        "--lookback-days", type=int, default=30,
        help="Initial lookback window in days (default: 30; auto-widens to 90 for hot tables if < 3 schemas returned)",
    )
    parser.add_argument("--connection", "-c", help="Snow CLI connection name")
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=3) as pool:
        fut_tables = pool.submit(query_hot_tables, args.lookback_days, args.connection)
        fut_streamlits = pool.submit(query_hot_streamlits, args.lookback_days, args.connection)
        fut_svs = pool.submit(query_hot_svs, args.lookback_days, args.connection)

        tables, tables_ok = fut_tables.result()
        streamlits, streamlits_ok = fut_streamlits.result()
        svs, svs_ok = fut_svs.result()

    fallbacks: dict[str, str] = {}
    if not tables_ok:
        fallbacks["hot_tables"] = "no_access_history"
    if not streamlits_ok:
        fallbacks["hot_streamlits"] = "no_aggregate_query_history"
    if not svs_ok:
        fallbacks["hot_svs"] = "no_access_history"

    output: dict[str, Any] = {
        "hot_tables": tables,
        "hot_streamlits": streamlits,
        "hot_svs": svs,
    }
    if fallbacks:
        output["fallbacks"] = fallbacks

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
