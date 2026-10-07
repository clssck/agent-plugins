#!/usr/bin/env python3
"""
migration_monitor.py
Monitor migration progress: replication lag, sync status, row counts.

Replaces migration_monitor.sh - no psql dependency required.

Subcommands:
    sync         - Monitor logical replication initial sync progress
    replication  - Monitor ongoing replication lag
    dashboard    - Full dashboard with source/target stats
    row-progress - Compare row counts between source and target

Usage:
    python migration_monitor.py sync --target-host sf-pg.example.com --target-dbname postgres --target-user admin
    python migration_monitor.py replication --host src.example.com -d mydb -U admin
    python migration_monitor.py dashboard --host src.example.com -d mydb -U admin \
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Resolve pg_common from the shared generic-PG layer at snowflake-postgres/scripts/shared/.
# pytest handles this via pythonpath; for direct invocation we add it to sys.path here.
from pathlib import Path as _P
_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from pg_common import (
    check_driver, connect, query, scalar,
    add_source_args, add_target_args,
    connect_source, connect_target,
    resolve_source_password, resolve_target_password,
    _apply_source_service, _apply_target_service,
)


def format_bytes(b):
    if not b or b == 0:
        return '0 B'
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(b) < 1024:
            return f"{b:.2f} {unit}"
        b /= 1024
    return f"{b:.2f} PB"


def progress_bar(percent, width=40):
    filled = int(percent * width / 100)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}] {percent:3d}%"


# ANSI: clear screen + home cursor. Avoids the per-refresh fork of
# /usr/bin/clear that os.system('clear') incurred (and the Windows-specific
# branch). Falls back to two newlines if stdout is not a TTY (e.g. piped).
_CLEAR_SCREEN = "\x1b[2J\x1b[H"


def clear_screen():
    if sys.stdout.isatty():
        sys.stdout.write(_CLEAR_SCREEN)
        sys.stdout.flush()
    else:
        print()
        print()


def _loop_should_continue(start_time, errors_in_row, max_seconds, max_errors):
    """Decide whether a monitor loop should iterate again.

    Returns False when the monitor has exceeded its --timeout budget OR when
    consecutive failures exceed --max-errors. Pre-fix the loops were
    `while True:` with bare-except retry, which would hammer a dead DB
    forever (no timeout, no max-retries).
    """
    if max_seconds and (time.time() - start_time) >= max_seconds:
        return False
    if max_errors and errors_in_row >= max_errors:
        return False
    return True


def cmd_sync(args):
    print(f"Connecting to target: {args.target_host}/{args.target_dbname}...")
    pw = resolve_target_password(args)
    # Hoisted out of the loop so we don't getattr on every iteration. The
    # service profile populates target_sslrootcert in main(); without forwarding
    # it here, sslmode=verify-ca falls back to the system CA bundle and
    # connection fails with "certificate verify failed" for Snowflake Postgres
    # targets that ship a per-instance CA via pg_connect --create.
    target_sslrootcert = getattr(args, 'target_sslrootcert', None)

    start = time.time()
    errors_in_row = 0
    while _loop_should_continue(start, errors_in_row, args.timeout, args.max_errors):
        try:
            conn = connect(args.target_host, args.target_port, args.target_dbname,
                           args.target_user, pw, args.target_sslmode,
                           sslrootcert=target_sslrootcert,
                           hostaddr=getattr(args, 'target_hostaddr', None))
            conn.autocommit = True

            # pg_subscription is NOT accessible on Snowflake Postgres (the
            # target this command runs against). pg_subscription_rel IS
            # accessible and carries everything we render below — subname is
            # never displayed, only counts and table_name. The prior JOIN on
            # pg_subscription failed with "permission denied" the first time
            # cmd_sync ran against a real Snowflake target.
            states = query(conn, """
                SELECT
                    srrelid::regclass AS table_name,
                    srsubstate AS state_code
                FROM pg_subscription_rel
                ORDER BY srsubstate, srrelid::regclass::text
            """)

            state_names = {'i': 'initializing', 'd': 'copying', 'f': 'finished', 's': 'synced', 'r': 'ready'}
            total = len(states)
            by_state = {}
            for s in states:
                code = s['state_code']
                by_state.setdefault(code, []).append(s['table_name'])

            done = len(by_state.get('s', [])) + len(by_state.get('r', [])) + len(by_state.get('f', []))
            percent = int(done * 100 / total) if total > 0 else 0

            conn.close()
            errors_in_row = 0

            clear_screen()
            print("=" * 65)
            print("  INITIAL SYNC PROGRESS")
            print("=" * 65)
            print()
            print(f"  {progress_bar(percent)}")
            print()
            print(f"  Initializing:  {len(by_state.get('i', []))} tables")
            print(f"  Copying data:  {len(by_state.get('d', []))} tables")
            print(f"  Finished:      {len(by_state.get('f', []))} tables")
            print(f"  Synced:        {len(by_state.get('s', []))} tables")
            print(f"  Ready:         {len(by_state.get('r', []))} tables")
            print(f"  Total:         {total} tables")

            copying = by_state.get('d', [])
            if copying:
                print(f"\n  Currently copying:")
                for t in copying[:5]:
                    print(f"    -> {t}")

            # An empty pg_subscription_rel (total == 0) means subscription is
            # disabled or doesn't exist — the loop would otherwise spin forever
            # waiting for "done >= total" with both sides at zero.
            if total == 0:
                print("\n  No subscription rows in pg_subscription_rel.")
                print("  Subscription may be disabled or not yet created. Exiting.")
                return

            if done >= total:
                print(f"\n  COMPLETE: All {total} tables synchronized!")
                return

            print(f"\n  {datetime.now().strftime('%H:%M:%S')} - refreshing every 5s (Ctrl+C to stop)")
            time.sleep(5)

        except KeyboardInterrupt:
            print("\nStopped.")
            return
        except Exception as e:
            errors_in_row += 1
            print(f"  Error ({errors_in_row}/{args.max_errors or '∞'}): {e}")
            time.sleep(5)

    if errors_in_row >= args.max_errors and args.max_errors:
        print(f"\nGiving up after {errors_in_row} consecutive errors.")
        sys.exit(1)
    elif args.timeout:
        print(f"\nTimed out after {args.timeout}s.")


def cmd_replication(args):
    print(f"Connecting to source: {args.host}/{args.dbname}...")
    pw = resolve_source_password(args)
    source_sslrootcert = getattr(args, 'sslrootcert', None)

    start = time.time()
    errors_in_row = 0
    while _loop_should_continue(start, errors_in_row, args.timeout, args.max_errors):
        try:
            conn = connect(args.host, args.port, args.dbname, args.user, pw, args.sslmode,
                           sslrootcert=source_sslrootcert,
                           hostaddr=getattr(args, 'hostaddr', None))
            conn.autocommit = True

            slots = query(conn, """
                SELECT slot_name, active,
                       pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) AS lag_bytes,
                       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag_pretty
                FROM pg_replication_slots
                WHERE slot_type = 'logical'
            """)

            wal = scalar(conn, "SELECT pg_size_pretty(sum(size)) FROM pg_ls_waldir()")
            conn.close()
            errors_in_row = 0

            clear_screen()
            print("=" * 65)
            print("  REPLICATION LAG MONITOR")
            print("=" * 65)

            if slots:
                for s in slots:
                    lag = int(s['lag_bytes']) if s['lag_bytes'] else 0
                    icon = 'ACTIVE' if s['active'] else 'INACTIVE'
                    level = 'OK'
                    if lag > 104857600:
                        level = 'CRITICAL'
                    elif lag > 1048576:
                        level = 'WARNING'
                    print(f"\n  Slot: {s['slot_name']}")
                    print(f"    Status:  {icon}")
                    print(f"    Lag:     {s['lag_pretty']} ({lag:,} bytes)  [{level}]")
            else:
                print("\n  No logical replication slots found")

            print(f"\n  WAL directory: {wal}")
            print(f"\n  {datetime.now().strftime('%H:%M:%S')} - refreshing every 10s (Ctrl+C to stop)")
            time.sleep(10)

        except KeyboardInterrupt:
            print("\nStopped.")
            return
        except Exception as e:
            errors_in_row += 1
            print(f"  Error ({errors_in_row}/{args.max_errors or '∞'}): {e}")
            time.sleep(10)

    if errors_in_row >= args.max_errors and args.max_errors:
        print(f"\nGiving up after {errors_in_row} consecutive errors.")
        sys.exit(1)
    elif args.timeout:
        print(f"\nTimed out after {args.timeout}s.")


def cmd_dashboard(args):
    src_pw = resolve_source_password(args)
    tgt_pw = resolve_target_password(args)
    source_sslrootcert = getattr(args, 'sslrootcert', None)
    target_sslrootcert = getattr(args, 'target_sslrootcert', None)

    start = time.time()
    errors_in_row = 0
    while _loop_should_continue(start, errors_in_row, args.timeout, args.max_errors):
        try:
            src_stats = {}
            tgt_stats = {}
            lag_info = None

            try:
                src_conn = connect(args.host, args.port, args.dbname, args.user, src_pw, args.sslmode,
                                   sslrootcert=source_sslrootcert,
                                   hostaddr=getattr(args, 'hostaddr', None))
                src_conn.autocommit = True
                row = query(src_conn, """
                    SELECT pg_size_pretty(pg_database_size(current_database())) AS size,
                           (SELECT count(*) FROM pg_stat_user_tables) AS tables,
                           (SELECT coalesce(sum(n_live_tup), 0) FROM pg_stat_user_tables) AS rows
                """)
                src_stats = row[0] if row else {}

                lag_rows = query(src_conn, """
                    SELECT slot_name,
                           pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag
                    FROM pg_replication_slots
                    WHERE slot_type = 'logical'
                    LIMIT 1
                """)
                lag_info = lag_rows[0] if lag_rows else None

                wal_size = scalar(src_conn, "SELECT pg_size_pretty(sum(size)) FROM pg_ls_waldir()")
                src_stats['wal'] = wal_size
                src_conn.close()
            except Exception as e:
                src_stats = {'error': str(e)}

            try:
                tgt_conn = connect(args.target_host, args.target_port, args.target_dbname,
                                   args.target_user, tgt_pw, args.target_sslmode,
                                   sslrootcert=target_sslrootcert,
                                   hostaddr=getattr(args, 'target_hostaddr', None))
                tgt_conn.autocommit = True
                row = query(tgt_conn, """
                    SELECT pg_size_pretty(pg_database_size(current_database())) AS size,
                           (SELECT count(*) FROM pg_stat_user_tables) AS tables,
                           (SELECT coalesce(sum(n_live_tup), 0) FROM pg_stat_user_tables) AS rows
                """)
                tgt_stats = row[0] if row else {}

                sync = query(tgt_conn, """
                    SELECT count(*) FILTER (WHERE srsubstate IN ('s', 'r')) AS synced,
                           count(*) AS total
                    FROM pg_subscription_rel
                """)
                tgt_stats['sync'] = f"{sync[0]['synced']}/{sync[0]['total']}" if sync else 'N/A'
                tgt_conn.close()
            except Exception as e:
                tgt_stats = {'error': str(e)}

            # Treat both sides erroring in the same iteration as a "failed
            # tick" so persistent dual-side breakage trips --max-errors.
            if 'error' in src_stats and 'error' in tgt_stats:
                errors_in_row += 1
            else:
                errors_in_row = 0

            clear_screen()
            print("=" * 70)
            print("  MIGRATION DASHBOARD")
            print("=" * 70)
            print(f"\n  Source: {args.host}/{args.dbname}")
            print(f"  Target: {args.target_host}/{args.target_dbname}")

            print(f"\n  {'':30} {'SOURCE':>15} {'TARGET':>15}")
            print(f"  {'-' * 62}")
            print(f"  {'Database size':<30} {src_stats.get('size', '?'):>15} {tgt_stats.get('size', '?'):>15}")
            print(f"  {'Tables':<30} {str(src_stats.get('tables', '?')):>15} {str(tgt_stats.get('tables', '?')):>15}")
            print(f"  {'Total rows':<30} {str(src_stats.get('rows', '?')):>15} {str(tgt_stats.get('rows', '?')):>15}")

            print(f"\n  WAL directory:    {src_stats.get('wal', 'N/A')}")
            print(f"  Replication lag:  {lag_info['lag'] if lag_info else 'N/A'}")
            print(f"  Sync status:      {tgt_stats.get('sync', 'N/A')}")

            print(f"\n  {datetime.now().strftime('%H:%M:%S')} - refreshing every 15s (Ctrl+C to stop)")
            time.sleep(15)

        except KeyboardInterrupt:
            print("\nStopped.")
            return
        except Exception as e:
            errors_in_row += 1
            print(f"  Error ({errors_in_row}/{args.max_errors or '∞'}): {e}")
            time.sleep(15)

    if errors_in_row >= args.max_errors and args.max_errors:
        print(f"\nGiving up after {errors_in_row} consecutive errors.")
        sys.exit(1)
    elif args.timeout:
        print(f"\nTimed out after {args.timeout}s.")


def cmd_row_progress(args):
    src_pw = resolve_source_password(args)
    tgt_pw = resolve_target_password(args)

    print("Fetching row counts from both databases...")
    src_conn = connect(args.host, args.port, args.dbname, args.user, src_pw, args.sslmode,
                       sslrootcert=getattr(args, 'sslrootcert', None),
                       hostaddr=getattr(args, 'hostaddr', None))
    src_conn.autocommit = True
    tgt_conn = connect(args.target_host, args.target_port, args.target_dbname,
                       args.target_user, tgt_pw, args.target_sslmode,
                       sslrootcert=getattr(args, 'target_sslrootcert', None),
                       hostaddr=getattr(args, 'target_hostaddr', None))
    tgt_conn.autocommit = True

    src_rows = query(src_conn, """
        SELECT schemaname || '.' || relname AS table_name, n_live_tup AS rows
        FROM pg_stat_user_tables ORDER BY n_live_tup DESC
    """)
    tgt_rows = query(tgt_conn, """
        SELECT schemaname || '.' || relname AS table_name, n_live_tup AS rows
        FROM pg_stat_user_tables ORDER BY n_live_tup DESC
    """)

    src_conn.close()
    tgt_conn.close()

    src_map = {r['table_name']: int(r['rows']) for r in src_rows}
    tgt_map = {r['table_name']: int(r['rows']) for r in tgt_rows}

    total_src = sum(src_map.values())
    total_tgt = sum(tgt_map.values())
    percent = int(total_tgt * 100 / total_src) if total_src > 0 else 0

    print()
    print("=" * 70)
    print("  ROW COUNT PROGRESS")
    print("=" * 70)
    print(f"\n  {progress_bar(min(percent, 100))}")
    print(f"\n  Source total rows:  {total_src:>15,}")
    print(f"  Target total rows:  {total_tgt:>15,}")
    print(f"  Difference:         {total_tgt - total_src:>+15,}")
    print()

    behind = []
    for t, src_c in src_map.items():
        tgt_c = tgt_map.get(t, 0)
        if tgt_c < src_c:
            behind.append((t, src_c, tgt_c))

    if behind:
        behind.sort(key=lambda x: x[1] - x[2], reverse=True)
        print(f"  Tables still syncing ({len(behind)}):")
        print(f"  {'Table':<40} {'Source':>12} {'Target':>12} {'Remaining':>12}")
        print("  " + "-" * 78)
        for t, s, tg in behind[:20]:
            print(f"  {t:<40} {s:>12,} {tg:>12,} {s - tg:>12,}")
    else:
        print("  All table row counts match!")

    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Monitor PostgreSQL migration progress',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  sync          Monitor initial sync table states (on target)
  replication   Monitor replication lag (on source)
  dashboard     Full source/target comparison dashboard
  row-progress  One-shot row count progress comparison

Examples:
  python migration_monitor.py sync --target-host sf-pg.example.com --target-dbname postgres --target-user admin
  python migration_monitor.py replication -H src.example.com -d mydb -U admin
  python migration_monitor.py dashboard -H src.example.com -d mydb -U admin \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin
""")
    sub = parser.add_subparsers(dest='command')

    def _add_loop_args(p):
        # Default to a 24h budget and 12 retries (~1 minute of dead-DB hammering
        # before bailing). Setting 0 disables the corresponding guard.
        p.add_argument('--timeout', type=int, default=86400,
                       help='Stop monitoring after N seconds (default: 86400 = 24h; 0 = run forever)')
        p.add_argument('--max-errors', type=int, default=12,
                       help='Stop after N consecutive errors (default: 12; 0 = retry forever)')

    sync_p = sub.add_parser('sync', help='Monitor initial sync progress')
    add_target_args(sync_p)
    _add_loop_args(sync_p)

    rep_p = sub.add_parser('replication', help='Monitor replication lag')
    add_source_args(rep_p)
    _add_loop_args(rep_p)

    dash_p = sub.add_parser('dashboard', help='Full migration dashboard')
    add_source_args(dash_p)
    add_target_args(dash_p)
    _add_loop_args(dash_p)

    row_p = sub.add_parser('row-progress', help='Row count progress comparison')
    add_source_args(row_p)
    add_target_args(row_p)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    check_driver()
    # Resolve --source-service / --target-service BEFORE dispatching to cmd_*.
    # Each subcommand only adds the flag(s) it needs; getattr-based short-circuit
    # in _apply_*_service handles the missing-attr case for source-only or
    # target-only subcommands. Without this, cmd_sync / cmd_replication called
    # bare connect(args.target_host, ...) with args.target_host='' and looped
    # forever in a broad `except Exception` retry block.
    _apply_source_service(args)
    _apply_target_service(args)

    if args.command == 'sync':
        cmd_sync(args)
    elif args.command == 'replication':
        cmd_replication(args)
    elif args.command == 'dashboard':
        cmd_dashboard(args)
    elif args.command == 'row-progress':
        cmd_row_progress(args)


if __name__ == '__main__':
    main()
