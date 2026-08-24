#!/usr/bin/env python3
"""
run_analysis.py — Standalone CLI entry point for AI Readiness Score.

Runs the full analysis pipeline (CR scoring, VQR extraction, SV quality)
directly using the Snowflake connector. Outputs scores JSON to a temp directory.

Usage:
    python run_analysis.py --sample-pct 30
    python run_analysis.py  # full scan
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add scripts dir to path
sys.path.insert(0, str(Path(__file__).parent))

from scoring import compute_composite_scores

try:
    import snowflake.connector
except ImportError:
    import subprocess
    _install_dir = os.path.join(tempfile.gettempdir(), "_snowflake_deps")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install",
        "--target", _install_dir,
        "--quiet",
        "snowflake-connector-python"
    ])
    sys.path.insert(0, _install_dir)
    import snowflake.connector

from snowflake.connector import connect, DictCursor


def _lower(row):
    return {k.lower(): v for k, v in row.items()}


def _ensure_db_context(conn):
    """Ensure the session has a database/schema context."""
    try:
        row = conn.cursor().execute("SELECT CURRENT_DATABASE(), CURRENT_SCHEMA()").fetchone()
        if row and row[0] and row[1]:
            return True
        if row and row[0] and not row[1]:
            conn.cursor().execute("USE SCHEMA PUBLIC")
            return True
    except Exception:
        pass
    try:
        _user = conn.cursor().execute("SELECT CURRENT_USER()").fetchone()[0]
        conn.cursor().execute(f'USE DATABASE "USER${_user}"')
        conn.cursor().execute("USE SCHEMA PUBLIC")
        return True
    except Exception:
        pass
    raise RuntimeError(
        "NO_DATABASE_CONTEXT: No database is set and USER$ database is not available. "
        "Please specify a database and schema to use."
    )


def _cache_path(stage, label):
    return f"{stage}/{label}.parquet"


def _cache_exists(conn, path):
    try:
        cur = conn.cursor()
        cur.execute(f"LIST {path}")
        return len(cur.fetchall()) > 0
    except Exception:
        return False


def _read_json_cache(conn, path):
    _ensure_db_context(conn)
    cur = conn.cursor()
    cur.execute("CREATE OR REPLACE TEMP FILE FORMAT _ai_readiness_parquet TYPE = PARQUET")
    rows = [{k.lower(): v for k, v in r.items()} for r in conn.cursor(DictCursor).execute(
        f"SELECT $1:JSON_PAYLOAD::STRING AS jp FROM {path} (FILE_FORMAT => _ai_readiness_parquet)"
    ).fetchall()]
    return rows[0].get("jp") if rows else None


def _write_json_cache(conn, data, path):
    _ensure_db_context(conn)
    escaped = data.replace("\\", "\\\\").replace("'", "''")
    conn.cursor().execute(
        f"""COPY INTO {path} FROM (SELECT '{escaped}' AS json_payload)
        FILE_FORMAT = (TYPE = PARQUET) OVERWRITE = TRUE SINGLE = TRUE
        HEADER = TRUE MAX_FILE_SIZE = 268435456"""
    )


def _run_query(conn, sql):
    with conn.cursor(DictCursor) as cur:
        cur.execute(sql)
        return [_lower(r) for r in cur.fetchall()]


def _write_cache(conn, sql, path):
    _ensure_db_context(conn)
    sql = sql.rstrip().rstrip(";")
    conn.cursor().execute(
        f"""COPY INTO {path} FROM ({sql})
        FILE_FORMAT = (TYPE = PARQUET) OVERWRITE = TRUE SINGLE = TRUE
        HEADER = TRUE MAX_FILE_SIZE = 268435456"""
    )


def _read_cache(conn, path):
    _ensure_db_context(conn)
    cur = conn.cursor()
    cur.execute("CREATE OR REPLACE TEMP FILE FORMAT _ai_readiness_parquet TYPE = PARQUET")
    cur.execute(f"SELECT $1 FROM {path} (FILE_FORMAT => _ai_readiness_parquet)")
    rows = []
    for (v,) in cur.fetchall():
        obj = json.loads(v) if isinstance(v, str) else (v if isinstance(v, dict) else json.loads(str(v)))
        rows.append({k.lower(): val for k, val in obj.items()})
    return rows


def main():
    parser = argparse.ArgumentParser(description="Run AI Readiness analysis")
    parser.add_argument("--sample-pct", type=int, default=None,
                        help="Sample percentage (e.g. 30). Omit for full scan.")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore cached results and re-run all queries.")
    parser.add_argument("--output", default=os.path.join(tempfile.gettempdir(), "scores.json"),
                        help="Output path for scores JSON.")
    args = parser.parse_args()

    sample_pct = args.sample_pct
    use_cache = not args.no_cache
    scripts_dir = Path(__file__).parent
    cache_stage = "@~/ai_readiness_cache"
    sample_suffix = f"_s{sample_pct}" if sample_pct else "_full"

    # Connect
    conn = connect(connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default")
    _ensure_db_context(conn)

    # Check for cached scores first
    scores_cache_p = _cache_path(cache_stage, f"scores{sample_suffix}")
    if use_cache and _cache_exists(conn, scores_cache_p):
        print(f"✅ Using cached scores from {scores_cache_p}")
        cached_json = _read_json_cache(conn, scores_cache_p)
        if cached_json:
            scores = json.loads(cached_json)
            with open(args.output, "w") as f:
                json.dump(scores, f)
            print(f"   AI Readiness: {scores['ai_readiness']}/100")
            print(f"   Output: {args.output}")
            return

    print("⏳ Running full analysis...")

    # Time window
    now = datetime.now(timezone.utc)
    start_ts = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    end_ts = now.strftime("%Y-%m-%d %H:%M:%S")
    freshness_start_ts = (now - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")

    sample_predicate = f"AND MOD(ABS(HASH(ah.query_id) % 100), 100) < {sample_pct}" if sample_pct else ""

    # --- CR Scoring ---
    cr_cache_p = _cache_path(cache_stage, f"cr_tables{sample_suffix}")
    if use_cache and _cache_exists(conn, cr_cache_p):
        print("  [CR] Reading from cache...")
        cr_results = _read_cache(conn, cr_cache_p)
    else:
        print("  [CR] Scoring table consumption readiness...")
        t0 = time.time()
        cr_sql_template = (scripts_dir / "cr_tables.sql").read_text(encoding="utf-8")
        cr_sql = cr_sql_template.format(
            sample_predicate=sample_predicate,
            start_ts=start_ts,
            end_ts=end_ts,
            freshness_start_ts=freshness_start_ts,
        )
        cr_results = _run_query(conn, cr_sql)
        print(f"  [CR] Query returned {len(cr_results):,} rows [{time.time()-t0:.1f}s]")
        try:
            _write_cache(conn, cr_sql, cr_cache_p)
        except Exception as exc:
            print(f"  [CR] Cache write failed (non-fatal): {exc}")

    n_cr = sum(1 for r in cr_results if float(r.get("consumption_readiness_score") or 0) >= 0.80)
    print(f"  [CR] ✅ {len(cr_results):,} tables scored, {n_cr:,} consumption-ready")

    # --- VQR Extraction ---
    vqr_cache_p = _cache_path(cache_stage, f"vqr_counts{sample_suffix}")
    vqr_map = {}
    if use_cache and _cache_exists(conn, vqr_cache_p):
        print("  [SV] Reading VQR counts from cache...")
        cached_json = _read_json_cache(conn, vqr_cache_p)
        vqr_data = json.loads(cached_json) if cached_json else {}
    else:
        print("  [SV] Extracting VQR counts...")
        t0 = time.time()
        # List semantic views
        with conn.cursor(DictCursor) as cur:
            cur.execute("SHOW SEMANTIC VIEWS IN ACCOUNT")
            cur.execute(
                "SELECT \"database_name\" || '.' || \"schema_name\" || '.' || \"name\" AS display_fqn, "
                "'\"' || REPLACE(\"database_name\", '\"', '\"\"') || '\".\"' || "
                "REPLACE(\"schema_name\", '\"', '\"\"') || '\".\"' || "
                "REPLACE(\"name\", '\"', '\"\"') || '\"' AS quoted_fqn "
                "FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) ORDER BY display_fqn"
            )
            show_rows = [_lower(r) for r in cur.fetchall()]

        fqns = []
        seen = set()
        for row in show_rows:
            d = row["display_fqn"]
            if d not in seen:
                seen.add(d)
                fqns.append({"display": d, "quoted": row["quoted_fqn"]})
        print(f"  [SV] Found {len(fqns):,} semantic views")

        # Describe in parallel using local ThreadPoolExecutor with shared connection
        def _describe_sv(fqn):
            cur = conn.cursor(DictCursor)
            try:
                cur.execute(f"DESCRIBE SEMANTIC VIEW {fqn['quoted']}", timeout=30)
                rows = [_lower(r) for r in cur.fetchall()]
                vqr_count = 0
                for row in rows:
                    kind = (row.get("object_kind") or "").upper()
                    if kind in ("AI_VERIFIED_QUERY", "VERIFIED_QUERY"):
                        vqr_count += 1
                    elif kind == "EXTENSION" and (row.get("object_name") or "").upper() == "CA" and (row.get("property") or "").upper() == "VALUE":
                        try:
                            ext = json.loads(row.get("property_value", "{}"))
                            vqr_count += len(ext.get("verified_queries", []))
                            vqr_count += len(ext.get("ai_verified_queries", []))
                        except Exception:
                            pass
                return {"fqn": fqn["display"], "vqr_count": vqr_count}
            except Exception:
                return {"fqn": fqn["display"], "vqr_count": 0}
            finally:
                cur.close()

        results = []
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(_describe_sv, fqn): fqn["display"] for fqn in fqns}
            for f in as_completed(futures):
                results.append(f.result())

        vqr_data = {
            "total_views_scanned": len(results),
            "total_vqrs": sum(r["vqr_count"] for r in results),
            "results": results,
        }
        print(f"  [SV] Scanned {len(results):,} views, {vqr_data['total_vqrs']:,} VQRs [{time.time()-t0:.1f}s]")
        try:
            _write_json_cache(conn, json.dumps(vqr_data), vqr_cache_p)
        except Exception as exc:
            print(f"  [SV] VQR cache write failed (non-fatal): {exc}")

    for item in vqr_data.get("results", []):
        fqn = item.get("fqn", "")
        count = item.get("vqr_count")
        if fqn and count is not None:
            vqr_map[fqn] = int(count)

    # --- SV Quality Scoring ---
    sv_cache_p = _cache_path(cache_stage, f"sv_quality{sample_suffix}")
    if use_cache and _cache_exists(conn, sv_cache_p):
        print("  [SV] Reading SV quality from cache...")
        sv_results = _read_cache(conn, sv_cache_p)
    else:
        print("  [SV] Scoring semantic view quality...")
        t0 = time.time()
        sv_sql_template = (scripts_dir / "sv_quality.sql").read_text(encoding="utf-8")
        if vqr_map:
            vqr_unions = " UNION ALL ".join(
                f"SELECT '{fqn.replace(chr(39), chr(39)+chr(39))}' AS sv_fqn, {count} AS n_verified_queries"
                for fqn, count in vqr_map.items()
            )
            vqr_source = vqr_unions
        else:
            vqr_source = "SELECT NULL AS sv_fqn, NULL AS n_verified_queries WHERE 1=0"
        sv_sql = sv_sql_template.format(vqr_source=vqr_source)
        sv_results = _run_query(conn, sv_sql)
        print(f"  [SV] Query returned {len(sv_results):,} rows [{time.time()-t0:.1f}s]")
        try:
            _write_cache(conn, sv_sql, sv_cache_p)
        except Exception as exc:
            print(f"  [SV] Cache write failed (non-fatal): {exc}")

    n_sv = len({str(r.get("sv_fqn") or "") for r in sv_results if r.get("sv_fqn")})
    print(f"  [SV] ✅ {n_sv:,} semantic views scored")

    # --- Compute composite scores ---
    scores = compute_composite_scores(cr_results, sv_results)

    # Add account metadata
    info = [_lower(r) for r in conn.cursor(DictCursor).execute(
        "SELECT CURRENT_ACCOUNT() AS account_name, CURRENT_ORGANIZATION_NAME() AS org_name, CURRENT_ROLE() AS role"
    ).fetchall()]
    scores["account_name"] = str(info[0].get("account_name", "UNKNOWN"))
    scores["org_name"] = str(info[0].get("org_name", ""))
    scores["role"] = str(info[0].get("role", ""))
    scores["run_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    scores["sample_pct"] = sample_pct

    # Cache scores
    try:
        _write_json_cache(conn, json.dumps(scores), scores_cache_p)
        print("💾 Scores cached for future runs")
    except Exception as exc:
        print(f"⚠️ Scores cache write failed (non-fatal): {exc}")

    # Write output
    with open(args.output, "w") as f:
        json.dump(scores, f)

    print(f"\n✅ AI Readiness: {scores['ai_readiness']}/100")
    print(f"   Output: {args.output}")


if __name__ == "__main__":
    main()
