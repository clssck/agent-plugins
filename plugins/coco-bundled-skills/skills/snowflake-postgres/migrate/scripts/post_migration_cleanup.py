#!/usr/bin/env python3
"""
post_migration_cleanup.py
Tear down replication artifacts after a successful migration.

Drops publications, subscriptions, replication slots, and migration test objects.

Usage:
    python post_migration_cleanup.py --host source.example.com -d mydb -U admin \
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin

    python post_migration_cleanup.py ... --dry-run   # Preview without executing
"""

import argparse
import os
import sys

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
    quote_ident, quote_literal,
    _apply_source_service, _apply_target_service,
)


DEFAULT_TARGET_SUBSCRIPTION_NAMES = (
    "migration_sub",
    "migrate_from_source",
    "reverse_sub",
)


def _dedupe_preserve_order(values):
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _discover_enabled_target_subscriptions(conn):
    rows = query(conn, """
        SELECT DISTINCT subname
        FROM pg_stat_subscription
        WHERE subname ILIKE '%migrat%'
           OR subname ILIKE '%migrate%'
           OR subname ILIKE '%reverse%'
        ORDER BY subname
    """)
    return _dedupe_preserve_order(row["subname"] for row in rows)


def cleanup_target(conn, dry_run=False, subscription_names=None):
    results = []
    errors = []

    discovered_names = _discover_enabled_target_subscriptions(conn)
    if subscription_names:
        candidate_names = _dedupe_preserve_order(list(subscription_names) + discovered_names)
    elif discovered_names:
        candidate_names = discovered_names
    else:
        candidate_names = list(DEFAULT_TARGET_SUBSCRIPTION_NAMES)

    for subname in candidate_names:
        sub_ident_sql = quote_ident(subname)
        drop_sql = f"DROP SUBSCRIPTION IF EXISTS {sub_ident_sql}"
        results.append(drop_sql)
        if dry_run:
            continue
        try:
            query(conn, drop_sql)
        except Exception as first_error:
            # The optimistic DROP usually fails when the publisher is
            # unreachable: PG cannot connect to drop the remote slot
            # atomically, so it aborts the whole DROP. Fall back to the
            # disassociate-then-drop pattern, which is local-only on the
            # target catalog and orphans the slot on the publisher. The
            # orphan is normally cleaned up by cleanup_source() in the
            # same run; with --target-only it must be dropped manually.
            results.append(f"  -- DROP failed: {first_error}")
            results.append("  -- falling back to DISABLE + slot_name=NONE + DROP")
            try:
                query(conn, f"ALTER SUBSCRIPTION {sub_ident_sql} DISABLE")
                query(conn, f"ALTER SUBSCRIPTION {sub_ident_sql} SET (slot_name = NONE)")
                query(conn, f"DROP SUBSCRIPTION {sub_ident_sql}")
                results.append(
                    f"  -- {subname}: dropped via fallback (source-side slot may be "
                    f"orphaned; inspect pg_replication_slots on source and drop it "
                    f"manually if needed with "
                    f"\"SELECT pg_drop_replication_slot('<slot_name>')\")"
                )
            except Exception as second_error:
                results.append(f"  -- ERROR (fallback): {second_error}")
                recovery = (
                    f"DROP SUBSCRIPTION {subname}: "
                    f"initial DROP failed ({first_error}); "
                    f"fallback also failed ({second_error}). "
                    f"Manual recovery on target: "
                    f"ALTER SUBSCRIPTION {subname} DISABLE; "
                    f"ALTER SUBSCRIPTION {subname} SET (slot_name = NONE); "
                    f"DROP SUBSCRIPTION {subname}; "
                    f"Then on source: inspect pg_replication_slots for the orphaned "
                    f"logical slot and drop it manually with "
                    f"SELECT pg_drop_replication_slot('<slot_name>');"
                    )
                errors.append(recovery)

    for obj in ['_migration_conn_test', '_migration_test_table']:
        sql = f"DROP TABLE IF EXISTS {quote_ident(obj)}"
        results.append(sql)
        if not dry_run:
            try:
                query(conn, sql)
            except Exception as e:
                results.append(f"  -- ERROR: {e}")
                errors.append(f"DROP TABLE {obj}: {e}")

    for srv in ['_migration_connectivity_test']:
        sql = f"DROP SERVER IF EXISTS {quote_ident(srv)} CASCADE"
        results.append(sql)
        if not dry_run:
            try:
                query(conn, sql)
            except Exception as e:
                results.append(f"  -- ERROR: {e}")
                errors.append(f"DROP SERVER {srv}: {e}")

    return results, errors


def cleanup_source(conn, dry_run=False):
    results = []
    errors = []

    pubs = query(conn, """
        SELECT pubname FROM pg_publication
        WHERE pubname LIKE '%migrat%' OR pubname LIKE '%snowflake%'
    """)
    for p in pubs:
        sql = f"DROP PUBLICATION IF EXISTS {quote_ident(p['pubname'])}"
        results.append(sql)
        if not dry_run:
            try:
                query(conn, sql)
            except Exception as e:
                results.append(f"  -- ERROR: {e}")
                errors.append(f"DROP PUBLICATION {p['pubname']}: {e}")

    slots = query(conn, """
        SELECT slot_name, active FROM pg_replication_slots
        WHERE slot_name LIKE '%migrat%' OR slot_name LIKE '%migrate%'
    """)
    for slot in slots:
        if slot.get('active'):
            results.append(f"-- SKIPPED (active): {slot['slot_name']}")
            continue
        # pg_drop_replication_slot takes a string literal, not an identifier.
        sql = f"SELECT pg_drop_replication_slot({quote_literal(slot['slot_name'])})"
        results.append(sql)
        if not dry_run:
            try:
                query(conn, sql)
            except Exception as e:
                results.append(f"  -- ERROR: {e}")
                errors.append(f"pg_drop_replication_slot({slot['slot_name']}): {e}")

    return results, errors


def main():
    parser = argparse.ArgumentParser(
        description='Clean up migration artifacts on source and target',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python post_migration_cleanup.py -H src.example.com -d mydb -U admin \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin --dry-run

  python post_migration_cleanup.py ... --source-only
  python post_migration_cleanup.py ... --target-only
""")
    add_source_args(parser)
    add_target_args(parser)
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be cleaned up without executing')
    parser.add_argument('--source-only', action='store_true',
                        help='Only clean up source artifacts')
    parser.add_argument('--target-only', action='store_true',
                        help='Only clean up target artifacts')
    parser.add_argument(
        '--subscription-name',
        dest='subscription_names',
        action='append',
        help='Optional target subscription name to drop. Repeat for multiple '
             'subscriptions; useful when subscriptions are disabled or custom-named.',
    )

    args = parser.parse_args()
    check_driver()
    # Resolve --source-service / --target-service from ~/.pg_service.conf BEFORE
    # the do_target / do_source gates below (which check args.target_host /
    # args.host as truthy). Without this, --target-only + --target-service
    # silently skipped target work because args.target_host was '' pre-resolution.
    _apply_source_service(args)
    _apply_target_service(args)

    mode = 'preview' if args.dry_run else 'execute'
    print(f"\n{'=' * 60}")
    print(f"  POST-MIGRATION CLEANUP ({mode.upper()})")
    print(f"{'=' * 60}")

    do_source = not args.target_only
    do_target = not args.source_only

    all_errors = []

    if do_target and args.target_host:
        print(f"\nTarget: {args.target_host}/{args.target_dbname}")
        print("-" * 40)
        tgt_conn = connect_target(args)
        tgt_conn.autocommit = True
        sqls, errs = cleanup_target(
            tgt_conn,
            dry_run=args.dry_run,
            subscription_names=getattr(args, "subscription_names", None),
        )
        for sql in sqls:
            print(f"  {sql}")
        all_errors.extend(errs)
        tgt_conn.close()

    if do_source and args.host:
        print(f"\nSource: {args.host}/{args.dbname}")
        print("-" * 40)
        src_conn = connect_source(args)
        src_conn.autocommit = True
        sqls, errs = cleanup_source(src_conn, dry_run=args.dry_run)
        for sql in sqls:
            print(f"  {sql}")
        all_errors.extend(errs)
        src_conn.close()

    print(f"\n{'=' * 60}")
    if args.dry_run:
        print("  DRY RUN COMPLETE - no changes made")
        print("  Re-run without --dry-run to execute")
    elif all_errors:
        print(f"  CLEANUP COMPLETED WITH {len(all_errors)} ERROR(S)")
        for err in all_errors:
            print(f"    - {err}")
        print("  Re-run after addressing the errors above; some artifacts may remain.")
    else:
        print("  CLEANUP COMPLETE")
    print(f"{'=' * 60}\n")

    if all_errors and not args.dry_run:
        sys.exit(1)


if __name__ == '__main__':
    main()
