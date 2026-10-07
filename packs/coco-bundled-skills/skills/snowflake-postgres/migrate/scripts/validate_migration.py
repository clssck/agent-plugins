#!/usr/bin/env python3
"""
validate_migration.py
Compare source and target databases to validate migration correctness.

Replaces row_count_validation.sql with a single script that connects to BOTH
databases, compares row counts, and optionally checks checksums and aggregates.

Usage:
    python validate_migration.py --host src.example.com -d mydb -U admin \
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin

    python validate_migration.py ... --mode full --html report.html
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime

# Resolve pg_common from the shared generic-PG layer at snowflake-postgres/scripts/shared/.
# pytest handles this via pythonpath; for direct invocation we add it to sys.path here.
from pathlib import Path as _P
_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from pg_common import (
    check_driver, query, scalar,
    add_source_args, add_target_args,
    connect_source, connect_target,
    quote_ident, quote_qualified,
    _apply_source_service, _apply_target_service,
)


def get_materialized_views(conn):
    rows = query(conn, """
        SELECT schemaname || '.' || matviewname AS view_name
        FROM pg_matviews
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
    """)
    return {r['view_name'] for r in rows}


def get_table_row_counts(conn, schemas=None):
    schema_filter = ""
    params = ()
    if schemas:
        placeholders = ",".join(["%s"] * len(schemas))
        schema_filter = f"AND schemaname IN ({placeholders})"
        params = tuple(schemas)
    rows = query(conn, f"""
        SELECT schemaname || '.' || relname AS table_name,
               n_live_tup AS row_count,
               pg_total_relation_size(relid) AS size_bytes,
               pg_size_pretty(pg_total_relation_size(relid)) AS size_pretty
        FROM pg_stat_user_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
        {schema_filter}
        ORDER BY schemaname, relname
    """, params or None)
    return {r['table_name']: r for r in rows}


def get_exact_counts(conn, tables):
    """Run exact `count(*)` per table. On failure, surface a structured
    error dict so the caller can flag validation failure instead of silently
    treating the error string as a count.
    """
    results = {}
    for t in tables:
        try:
            cnt = scalar(conn, f'SELECT count(*) FROM {quote_qualified(t)}')
            results[t] = int(cnt) if cnt is not None else 0
        except Exception as e:
            results[t] = {'error': str(e)}
    return results


def get_table_checksums(conn, tables, limit=10, sample_rows=1000):
    """Sample-based checksum: hashes the first `sample_rows` rows ordered by
    column 1. This is a smoke-test for ordering/data drift on small samples;
    it is NOT a full-table hash and silently misses divergence past row N.
    Use --mode full for a real comparison or pgCompare for deep validation.
    """
    results = {}
    for t in tables[:limit]:
        try:
            rows = query(conn, f"""
                SELECT md5(string_agg(t::text, '' ORDER BY t)) AS checksum
                FROM (SELECT * FROM {quote_qualified(t)} ORDER BY 1 LIMIT {int(sample_rows)}) t
            """)
            results[t] = rows[0]['checksum'] if rows else None
        except Exception as e:
            results[t] = {'error': str(e)}
    return results


def get_numeric_aggregates(conn, tables, limit=10):
    results = {}
    for t in tables[:limit]:
        try:
            cols = query(conn, """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema || '.' || table_name = %s
                AND data_type IN ('integer', 'bigint', 'numeric', 'real', 'double precision', 'smallint')
                AND ordinal_position <= 5
                LIMIT 3
            """, (t,))
            if not cols:
                continue
            agg_parts = []
            for c in cols:
                cn = c['column_name']
                cn_q = quote_ident(cn)
                # Build the full alias name first then quote_ident it once. The
                # prior form `sum_{quote_ident(cn_alias)}` produced invalid SQL
                # like `AS sum_"id"` (alias half quoted, half not), which made
                # every full-mode aggregate query fail and silently report
                # "ALL MATCH" because both sides returned identical error dicts.
                sum_alias_q = quote_ident(f"sum_{cn}")
                count_alias_q = quote_ident(f"count_{cn}")
                agg_parts.append(f"sum({cn_q})::text AS {sum_alias_q}")
                agg_parts.append(f"count({cn_q})::text AS {count_alias_q}")
            sql = f"SELECT {', '.join(agg_parts)} FROM {quote_qualified(t)}"
            rows = query(conn, sql)
            results[t] = rows[0] if rows else {}
        except Exception as e:
            results[t] = {'error': str(e)}
    return results


def compare_row_counts(source_counts, target_counts, matviews=None):
    if matviews is None:
        matviews = set()
    all_tables = sorted(set(list(source_counts.keys()) + list(target_counts.keys())))
    results = []
    for t in all_tables:
        src = source_counts.get(t)
        tgt = target_counts.get(t)
        src_count = src['row_count'] if src else 0
        tgt_count = tgt['row_count'] if tgt else 0
        is_matview = t in matviews
        status = 'MATCH'
        if src is None:
            status = 'MISSING_SOURCE'
        elif tgt is None:
            status = 'MISSING_TARGET'
        elif int(src_count) != int(tgt_count):
            status = 'MATVIEW_MISMATCH' if is_matview else 'MISMATCH'
        results.append({
            'table': t,
            'source_rows': int(src_count) if src else 0,
            'target_rows': int(tgt_count) if tgt else 0,
            'diff': int(tgt_count or 0) - int(src_count or 0),
            'source_size': src.get('size_pretty', '?') if src else 'N/A',
            'status': status,
            'is_matview': is_matview,
        })
    return results


def print_comparison(results, exact_diffs=None, checksum_results=None, agg_diffs=None):
    print()
    print("=" * 90)
    print("  MIGRATION VALIDATION REPORT")
    print("=" * 90)

    matched = sum(1 for r in results if r['status'] == 'MATCH')
    mismatched = sum(1 for r in results if r['status'] == 'MISMATCH')
    matview_mismatched = sum(1 for r in results if r['status'] == 'MATVIEW_MISMATCH')
    missing_src = sum(1 for r in results if r['status'] == 'MISSING_SOURCE')
    missing_tgt = sum(1 for r in results if r['status'] == 'MISSING_TARGET')

    print(f"\n  Tables matched:        {matched}")
    print(f"  Tables mismatched:     {mismatched}")
    if matview_mismatched:
        print(f"  Matview mismatches:    {matview_mismatched}  (n_live_tup stats may be stale; use SELECT count(*) to verify)")
    print(f"  Missing on source:     {missing_src}")
    print(f"  Missing on target:     {missing_tgt}")
    print(f"  Total tables:          {len(results)}")

    if mismatched > 0 or missing_tgt > 0 or missing_src > 0 or matview_mismatched > 0:
        print(f"\n  {'Table':<45} {'Source':>12} {'Target':>12} {'Diff':>10} {'Status':<15}")
        print("  " + "-" * 94)
        for r in results:
            if r['status'] not in ('MATCH',):
                mv_tag = ' [MATVIEW]' if r.get('is_matview') else ''
                print(f"  {r['table']:<45} {r['source_rows']:>12,} {r['target_rows']:>12,} "
                      f"{r['diff']:>+10,} {r['status']:<15}{mv_tag}")

    if exact_diffs:
        print("\n  EXACT COUNT VERIFICATION (mismatched tables)")
        print("  " + "-" * 60)
        for t, counts in exact_diffs.items():
            src_c = counts.get('source', '?')
            tgt_c = counts.get('target', '?')
            # get_exact_counts returns {'error': ...} on failure; flag as ERROR
            # rather than treating the dict as a count-equal-to-itself match.
            if isinstance(src_c, dict) or isinstance(tgt_c, dict):
                match = 'ERROR'
                src_disp = (src_c.get('error', '?') if isinstance(src_c, dict) else src_c)
                tgt_disp = (tgt_c.get('error', '?') if isinstance(tgt_c, dict) else tgt_c)
                print(f"  {t:<45} src={src_disp} tgt={tgt_disp} {match}")
            else:
                match = 'MATCH' if src_c == tgt_c else 'MISMATCH'
                print(f"  {t:<45} {src_c:>12} {tgt_c:>12} {match}")

    if checksum_results:
        print("\n  CHECKSUM COMPARISON (sample of first 1000 rows)")
        print("  " + "-" * 60)
        for t, r in checksum_results.items():
            match = 'MATCH' if r.get('match') else 'MISMATCH'
            print(f"  {t:<45} {match}")

    if agg_diffs:
        print("\n  AGGREGATE COMPARISON")
        print("  " + "-" * 60)
        for t, diffs in agg_diffs.items():
            if diffs:
                issues = [f"{k}: src={v['source']} tgt={v['target']}" for k, v in diffs.items() if v.get('match') is False]
                if issues:
                    print(f"  {t}: {'; '.join(issues)}")
                else:
                    print(f"  {t}: ALL MATCH")

    print()
    # MISSING_SOURCE counts as a failure too: post-migration the target should
    # be a faithful copy of source. Extra user-namespace tables on target
    # (system schemas are already filtered out in get_table_row_counts) usually
    # mean target wasn't cleaned up or scope drift between source and target.
    # Reporting "VALIDATION PASSED" while the detail block prints MISSING_SOURCE
    # rows is the false-pass we're closing here.
    if mismatched == 0 and missing_tgt == 0 and missing_src == 0:
        if matview_mismatched > 0:
            print("  RESULT: VALIDATION PASSED (matview mismatches are expected - stats may be stale)")
        else:
            print("  RESULT: VALIDATION PASSED")
    else:
        print("  RESULT: VALIDATION FAILED - discrepancies found")
        if missing_src > 0 and mismatched == 0 and missing_tgt == 0:
            print("          (only MISSING_SOURCE — extra tables on target; "
                  "investigate whether target was cleaned before migration)")
    print("=" * 90)
    print()


def generate_html(results, data, output_path):
    matched = sum(1 for r in results if r['status'] == 'MATCH')
    failed = len(results) - matched

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Migration Validation Report</title>
    <style>
        :root {{ --ok: #10B981; --err: #EF4444; --warn: #F59E0B; --bg: #F8FAFC; }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); }}
        .header {{ background: linear-gradient(135deg, #11567F, #29B5E8); color: white; padding: 2rem; text-align: center; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin-bottom: 2rem; }}
        .card {{ background: white; border-radius: 12px; padding: 1.5rem; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .card .val {{ font-size: 2rem; font-weight: 700; }}
        .card .lbl {{ color: #64748B; font-size: 0.875rem; }}
        .ok {{ color: var(--ok); }}
        .err {{ color: var(--err); }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #E2E8F0; font-size: 0.875rem; }}
        th {{ background: #F1F5F9; font-weight: 600; color: #475569; text-transform: uppercase; font-size: 0.75rem; }}
        .status-match {{ color: var(--ok); font-weight: 600; }}
        .status-mismatch {{ color: var(--err); font-weight: 600; }}
        .status-missing {{ color: var(--warn); font-weight: 600; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Migration Validation Report</h1>
        <p>{data.get('timestamp', '')}</p>
    </div>
    <div class="container">
        <div class="cards">
            <div class="card"><div class="val">{len(results)}</div><div class="lbl">Total Tables</div></div>
            <div class="card"><div class="val ok">{matched}</div><div class="lbl">Matched</div></div>
            <div class="card"><div class="val err">{failed}</div><div class="lbl">Failed</div></div>
            <div class="card"><div class="val">{sum(r['source_rows'] for r in results):,}</div><div class="lbl">Source Rows</div></div>
            <div class="card"><div class="val">{sum(r['target_rows'] for r in results):,}</div><div class="lbl">Target Rows</div></div>
        </div>
        <table>
            <tr><th>Table</th><th>Source Rows</th><th>Target Rows</th><th>Diff</th><th>Size</th><th>Status</th></tr>"""

    for r in results:
        cls = 'status-match' if r['status'] == 'MATCH' else (
            'status-mismatch' if r['status'] == 'MISMATCH' else (
            'status-missing' if r['status'] in ('MISSING_SOURCE', 'MISSING_TARGET') else 'status-missing'))
        label = r['status']
        if r.get('is_matview') and r['status'] == 'MATVIEW_MISMATCH':
            label = 'MATVIEW (stats stale)'
        html += f"""
            <tr>
                <td>{r['table']}{' [MV]' if r.get('is_matview') else ''}</td>
                <td>{r['source_rows']:,}</td>
                <td>{r['target_rows']:,}</td>
                <td>{r['diff']:+,}</td>
                <td>{r['source_size']}</td>
                <td class="{cls}">{label}</td>
            </tr>"""

    html += """
        </table>
    </div>
</body>
</html>"""
    with open(output_path, 'w') as f:
        f.write(html)
    print(f"HTML report: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Validate migration by comparing source and target databases',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  quick   - Compare pg_stat row counts (fast, approximate)
  exact   - Run SELECT count(*) on mismatched tables
  full    - Row counts + checksums + aggregates on mismatched tables

Examples:
  python validate_migration.py -H src.example.com -d mydb -U admin \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin

  python validate_migration.py ... --mode full --html validation.html
""")
    add_source_args(parser)
    add_target_args(parser)
    parser.add_argument('--mode', choices=['quick', 'exact', 'full'], default='quick',
                        help='Validation depth (default: quick)')
    parser.add_argument('--html', metavar='FILE', help='Generate HTML report')
    parser.add_argument('--json', metavar='FILE', help='Save JSON results')
    parser.add_argument('--schemas', default=None,
                        help='Comma-separated list of schemas to include (default: all non-system schemas)')
    parser.add_argument('--analyze', action='store_true',
                        help='Run ANALYZE on both databases before validation (recommended after bulk load)')

    args = parser.parse_args()
    check_driver()

    # Resolve service profiles BEFORE validation: --source-service/--target-service
    # populate args.host/args.target_host etc from ~/.pg_service.conf so the
    # operator can pass service names alone (chat-safe, no creds in transcript).
    _apply_source_service(args)
    _apply_target_service(args)

    if not args.host or not args.dbname or not args.user:
        parser.error("Source connection params required (--host, --dbname, --user, OR --source-service NAME)")
    if not args.target_host or not args.target_dbname or not args.target_user:
        parser.error("Target connection params required (--target-host, --target-dbname, --target-user, OR --target-service NAME)")

    schemas = [s.strip() for s in args.schemas.split(',')] if args.schemas else None

    print(f"Connecting to source: {args.host}/{args.dbname}...")
    src_conn = connect_source(args)
    src_conn.autocommit = True

    print(f"Connecting to target: {args.target_host}/{args.target_dbname}...")
    tgt_conn = connect_target(args)
    tgt_conn.autocommit = True

    print("Detecting materialized views...")
    src_matviews = get_materialized_views(src_conn)
    tgt_matviews = get_materialized_views(tgt_conn)
    all_matviews = src_matviews | tgt_matviews
    if all_matviews:
        print(f"  {len(all_matviews)} materialized view(s) detected (will be flagged separately)")

    if args.analyze:
        print("Running ANALYZE on source (refreshing statistics)...")
        cur = src_conn.cursor()
        cur.execute("ANALYZE")
        print("Running ANALYZE on target (refreshing statistics)...")
        cur = tgt_conn.cursor()
        cur.execute("ANALYZE")
        print("  Statistics refreshed on both databases")

    print("Fetching source row counts...")
    src_counts = get_table_row_counts(src_conn, schemas=schemas)
    print(f"  {len(src_counts)} tables found on source")

    print("Fetching target row counts...")
    tgt_counts = get_table_row_counts(tgt_conn, schemas=schemas)
    print(f"  {len(tgt_counts)} tables found on target")

    results = compare_row_counts(src_counts, tgt_counts, all_matviews)

    exact_diffs = None
    checksum_results = None
    agg_diffs = None

    mismatched_tables = [r['table'] for r in results if r['status'] == 'MISMATCH']
    matview_mismatches = [r['table'] for r in results if r['status'] == 'MATVIEW_MISMATCH']

    if matview_mismatches:
        print(f"Running exact counts on {len(matview_mismatches)} materialized views (n_live_tup is unreliable)...")
        src_mv_exact = get_exact_counts(src_conn, matview_mismatches)
        tgt_mv_exact = get_exact_counts(tgt_conn, matview_mismatches)
        exact_diffs = {}
        for t in matview_mismatches:
            src_v = src_mv_exact.get(t)
            tgt_v = tgt_mv_exact.get(t)
            exact_diffs[t] = {'source': src_v, 'target': tgt_v}
            # Only promote MATVIEW_MISMATCH → MATCH when both sides returned
            # plain ints AND match. {'error': ...} == {'error': ...} would
            # otherwise sneak through since Python compares dicts structurally.
            if (isinstance(src_v, int) and isinstance(tgt_v, int) and src_v == tgt_v):
                for r in results:
                    if r['table'] == t:
                        r['status'] = 'MATCH'
                        r['source_rows'] = src_v
                        r['target_rows'] = tgt_v
                        r['diff'] = 0
                        break

    if args.mode in ('exact', 'full') and mismatched_tables:
        print(f"Running exact counts on {len(mismatched_tables)} mismatched tables...")
        src_exact = get_exact_counts(src_conn, mismatched_tables)
        tgt_exact = get_exact_counts(tgt_conn, mismatched_tables)
        if exact_diffs is None:
            exact_diffs = {}
        for t in mismatched_tables:
            src_v = src_exact.get(t)
            tgt_v = tgt_exact.get(t)
            exact_diffs[t] = {'source': src_v, 'target': tgt_v}
            # Promote MISMATCH → MATCH when both sides returned plain ints AND
            # match. Without this, a stale n_live_tup that triggered the
            # initial MISMATCH stays as MISMATCH in the final exit code even
            # when the exact count agrees — every post-bulk-load validation
            # without --analyze would false-fail.
            if isinstance(src_v, int) and isinstance(tgt_v, int) and src_v == tgt_v:
                for r in results:
                    if r['table'] == t:
                        r['status'] = 'MATCH'
                        r['source_rows'] = src_v
                        r['target_rows'] = tgt_v
                        r['diff'] = 0
                        break

    if args.mode == 'full':
        matched_tables = [r['table'] for r in results if r['status'] == 'MATCH'][:10]
        if matched_tables:
            print(f"Running checksum comparison on {len(matched_tables)} tables...")
            src_cs = get_table_checksums(src_conn, matched_tables)
            tgt_cs = get_table_checksums(tgt_conn, matched_tables)
            checksum_results = {}
            for t in matched_tables:
                src_v = src_cs.get(t)
                tgt_v = tgt_cs.get(t)
                # Don't claim a match when either side surfaced an error dict
                # (or when one returned None — possibly a permissions / driver
                # failure we don't want to silently call equal).
                is_error = isinstance(src_v, dict) or isinstance(tgt_v, dict)
                checksum_results[t] = {
                    'source': src_v,
                    'target': tgt_v,
                    'match': (not is_error) and src_v is not None and src_v == tgt_v,
                }

        if matched_tables:
            print("Running aggregate comparison...")
            src_agg = get_numeric_aggregates(src_conn, matched_tables)
            tgt_agg = get_numeric_aggregates(tgt_conn, matched_tables)
            agg_diffs = {}
            for t in matched_tables:
                if t not in src_agg or t not in tgt_agg:
                    continue
                src_v = src_agg[t]
                tgt_v = tgt_agg[t]
                # Surface aggregate-query failures explicitly. Identical error
                # dicts on both sides would otherwise compare equal and print
                # "ALL MATCH" — the exact silent-failure mode that masked the
                # invalid SQL alias bug for so long.
                if 'error' in src_v or 'error' in tgt_v:
                    agg_diffs[t] = {
                        '__aggregate_error__': {
                            'source': src_v.get('error', 'OK'),
                            'target': tgt_v.get('error', 'OK'),
                            'match': False,
                        }
                    }
                    continue
                diffs = {}
                for k in src_v:
                    diffs[k] = {
                        'source': src_v.get(k),
                        'target': tgt_v.get(k),
                        'match': src_v.get(k) == tgt_v.get(k),
                    }
                agg_diffs[t] = diffs

    src_conn.close()
    tgt_conn.close()

    print_comparison(results, exact_diffs, checksum_results, agg_diffs)

    data = {
        'timestamp': datetime.now().isoformat(),
        'source': f"{args.host}/{args.dbname}",
        'target': f"{args.target_host}/{args.target_dbname}",
        'mode': args.mode,
        'results': results,
    }

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"JSON saved: {args.json}")

    if args.html:
        generate_html(results, data, args.html)

    # MISSING_SOURCE is a failure too — see print_comparison() comment for why.
    # Keep this in sync with the verdict logic above.
    has_failures = any(
        r['status'] in ('MISMATCH', 'MISSING_TARGET', 'MISSING_SOURCE')
        for r in results
    )
    sys.exit(1 if has_failures else 0)


if __name__ == '__main__':
    main()
