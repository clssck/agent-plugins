#!/usr/bin/env python3
"""
prepare_target.py
Pre-restore target preparation and safety checks.

Subcommands:
  preflight-check  MANDATORY safety check before any migration. Verifies that
                   schemas to be migrated (except 'public') do not already exist
                   on the target. If they do and own objects, aborts with a warning
                   to prevent data loss or conflicts.
  extensions       Query source for extensions and create them on target before restore.
  check-data       Check if target schemas already contain data (pre-restore safety).
  clean-schemas    DROP and recreate target schemas before re-restore.

Usage:
    python prepare_target.py preflight-check \\
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin \\
        --schemas analytics,reporting

    python prepare_target.py extensions \\
        --host src.example.com -d mydb -U admin \\
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin

    python prepare_target.py check-data \\
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin \\
        --schemas public,analytics

    python prepare_target.py clean-schemas \\
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin \\
        --schemas analytics,reporting --confirm
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
    check_driver, query, scalar,
    add_source_args, add_target_args,
    connect_source, connect_target,
    quote_ident as _quote_ident,
    SUPPORTED_EXTENSIONS,
    _apply_source_service, _apply_target_service,
)

# psycopg2.sql.Identifier safely quotes schema/table names against names that
# embed `"` characters. Falls back to pg_common.quote_ident on the pg8000
# path. Schema names here come from --schemas CLI input, so the operator is
# trusted, but identifier-safe quoting is the right pattern.
try:
    from psycopg2 import sql as _pg_sql
    _HAS_PG_SQL = True
except ImportError:
    _HAS_PG_SQL = False


def cmd_preflight_check(args):
    if not args.schemas:
        print("ERROR: --schemas is required for preflight-check", file=sys.stderr)
        print("Provide the comma-separated list of schemas you plan to migrate.", file=sys.stderr)
        sys.exit(1)

    schema_list = [s.strip() for s in args.schemas.split(',')]
    check_schemas = [s for s in schema_list if s != 'public']

    if not check_schemas:
        print("All migration schemas are 'public' - skipping preflight schema check.")
        print("PREFLIGHT: PASSED")
        return

    print(f"Connecting to target: {args.target_host}/{args.target_dbname}...")
    tgt_conn = connect_target(args)
    tgt_conn.autocommit = True

    placeholders = ','.join(['%s'] * len(check_schemas))
    existing = query(tgt_conn, f"""
        SELECT nspname AS schema_name
        FROM pg_namespace
        WHERE nspname IN ({placeholders})
    """, tuple(check_schemas))
    existing_names = {r['schema_name'] for r in existing}

    if not existing_names:
        print(f"\nChecked {len(check_schemas)} schema(s): none exist on target.")
        print("PREFLIGHT: PASSED")
        tgt_conn.close()
        return

    print(f"\nWARNING: {len(existing_names)} of {len(check_schemas)} migration schema(s) already exist on target:")
    for s in sorted(existing_names):
        print(f"  - {s}")

    existing_tuple = tuple(existing_names)
    placeholders_existing = ','.join(['%s'] * len(existing_tuple))
    objects = query(tgt_conn, f"""
        SELECT n.nspname AS schema_name,
               c.relkind,
               count(*) AS object_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname IN ({placeholders_existing})
        AND c.relkind IN ('r', 'v', 'm', 'S', 'i', 'f', 'p')
        GROUP BY n.nspname, c.relkind
        ORDER BY n.nspname, c.relkind
    """, existing_tuple)

    kind_labels = {
        'r': 'tables', 'v': 'views', 'm': 'materialized views',
        'S': 'sequences', 'i': 'indexes', 'f': 'foreign tables', 'p': 'partitioned tables',
    }

    schemas_with_objects = {}
    for row in objects:
        s = row['schema_name']
        if s not in schemas_with_objects:
            schemas_with_objects[s] = []
        label = kind_labels.get(row['relkind'], row['relkind'])
        schemas_with_objects[s].append(f"{int(row['object_count'])} {label}")

    routines = query(tgt_conn, f"""
        SELECT n.nspname AS schema_name, count(*) AS func_count
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname IN ({placeholders_existing})
        GROUP BY n.nspname
    """, existing_tuple)
    for row in routines:
        s = row['schema_name']
        if s not in schemas_with_objects:
            schemas_with_objects[s] = []
        schemas_with_objects[s].append(f"{int(row['func_count'])} functions/procedures")

    tgt_conn.close()

    if not schemas_with_objects:
        print("\nSchemas exist but are EMPTY (no objects). Safe to proceed.")
        print("PREFLIGHT: PASSED (with note: empty schemas exist)")
        return

    print("\n" + "=" * 78)
    print("  PREFLIGHT FAILED: Target schemas contain existing objects")
    print("=" * 78)
    for s in sorted(schemas_with_objects):
        print(f"\n  Schema '{s}':")
        for item in schemas_with_objects[s]:
            print(f"    - {item}")

    empty_existing = existing_names - set(schemas_with_objects.keys())
    if empty_existing:
        print(f"\n  Empty schemas (OK): {', '.join(sorted(empty_existing))}")

    print("\n" + "-" * 78)
    print("  MIGRATION ABORTED. Restoring into schemas that already contain objects")
    print("  will cause conflicts, duplicate data, or partial overwrites.")
    print("")
    print("  Options:")
    print("    1) Drop and recreate the schemas first:")
    print(f"       python prepare_target.py clean-schemas --schemas {','.join(sorted(schemas_with_objects.keys()))} --confirm ...")
    print("    2) Use a different target database")
    print("    3) Manually verify the existing objects are acceptable and re-run with --i-understand-the-risks")
    print("=" * 78)
    sys.exit(1)


def cmd_extensions(args):
    print(f"Connecting to source: {args.host}/{args.dbname}...")
    src_conn = connect_source(args)
    src_conn.autocommit = True

    print(f"Connecting to target: {args.target_host}/{args.target_dbname}...")
    tgt_conn = connect_target(args)
    tgt_conn.autocommit = True

    src_exts = query(src_conn, """
        SELECT e.extname, e.extversion, n.nspname AS schema
        FROM pg_extension e
        JOIN pg_namespace n ON n.oid = e.extnamespace
        WHERE e.extname != 'plpgsql'
        ORDER BY e.extname
    """)

    tgt_exts_rows = query(tgt_conn, "SELECT extname FROM pg_extension")
    tgt_existing = {r['extname'] for r in tgt_exts_rows}

    print(f"\nSource extensions: {len(src_exts)}")
    print(f"Target extensions already installed: {len(tgt_existing) - 1}")

    created = 0
    skipped = 0
    unsupported = []

    for ext in src_exts:
        name = ext['extname']
        schema = ext['schema']

        if name in tgt_existing:
            print(f"  [SKIP] {name} - already installed on target")
            skipped += 1
            continue

        if name.lower() not in SUPPORTED_EXTENSIONS:
            print(f"  [UNSUPPORTED] {name} - not available in Snowflake Postgres")
            unsupported.append(name)
            continue

        # CREATE EXTENSION takes a name (treated case-insensitively when
        # unquoted but case-sensitive when quoted). The allowlist match is
        # done case-insensitively above; emit the original-case name with
        # standard identifier quoting so it round-trips.
        ext_ident = _quote_ident(name)
        schema_ident = _quote_ident(schema)
        schema_clause = f' SCHEMA {schema_ident}' if schema != 'public' else ''

        if args.dry_run:
            if schema != 'public':
                print(f"  [DRY RUN] CREATE SCHEMA IF NOT EXISTS {schema_ident};")
            print(f"  [DRY RUN] CREATE EXTENSION IF NOT EXISTS {ext_ident}{schema_clause};")
            created += 1
        else:
            try:
                cur = tgt_conn.cursor()
                if schema != 'public':
                    if _HAS_PG_SQL:
                        cur.execute(_pg_sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(_pg_sql.Identifier(schema)))
                    else:
                        cur.execute(f'CREATE SCHEMA IF NOT EXISTS {schema_ident}')
                if _HAS_PG_SQL:
                    if schema != 'public':
                        cur.execute(_pg_sql.SQL("CREATE EXTENSION IF NOT EXISTS {} SCHEMA {}").format(
                            _pg_sql.Identifier(name), _pg_sql.Identifier(schema)))
                    else:
                        cur.execute(_pg_sql.SQL("CREATE EXTENSION IF NOT EXISTS {}").format(
                            _pg_sql.Identifier(name)))
                else:
                    cur.execute(f'CREATE EXTENSION IF NOT EXISTS {ext_ident}{schema_clause}')
                print(f"  [CREATED] {name} (schema: {schema})")
                created += 1
            except Exception as e:
                print(f"  [ERROR] {name}: {e}")

    src_conn.close()
    tgt_conn.close()

    print(f"\nSummary: {created} created, {skipped} already existed, {len(unsupported)} unsupported")
    if unsupported:
        print(f"Unsupported extensions (require manual handling): {', '.join(unsupported)}")


def cmd_check_data(args):
    print(f"Connecting to target: {args.target_host}/{args.target_dbname}...")
    tgt_conn = connect_target(args)
    tgt_conn.autocommit = True

    schema_filter = ''
    params = ()
    if args.schemas:
        schema_list = [s.strip() for s in args.schemas.split(',')]
        placeholders = ','.join(['%s'] * len(schema_list))
        schema_filter = f"AND schemaname IN ({placeholders})"
        params = tuple(schema_list)

    rows = query(tgt_conn, f"""
        SELECT schemaname, relname, n_live_tup AS approx_rows
        FROM pg_stat_user_tables
        WHERE n_live_tup > 0
        {schema_filter}
        ORDER BY schemaname, relname
    """, params or None)

    if not rows:
        print("\nTarget schemas are empty - safe to restore.")
        tgt_conn.close()
        return

    no_pk_rows = query(tgt_conn, f"""
        SELECT s.schemaname, s.relname, s.n_live_tup AS approx_rows
        FROM pg_stat_user_tables s
        LEFT JOIN pg_constraint pk
            ON pk.conrelid = s.relid AND pk.contype = 'p'
        WHERE s.n_live_tup > 0
        AND pk.oid IS NULL
        {schema_filter}
        ORDER BY s.schemaname, s.relname
    """, params or None)

    tgt_conn.close()

    print(f"\nWARNING: {len(rows)} table(s) already contain data on target!")
    print(f"         {len(no_pk_rows)} of these have NO primary key (HIGH RISK for duplicates)\n")

    if no_pk_rows:
        print("Tables WITHOUT primary keys (will get DUPLICATE data on re-restore):")
        print(f"  {'Schema':<25} {'Table':<35} {'Approx Rows':>12}")
        print("  " + "-" * 72)
        for r in no_pk_rows:
            print(f"  {r['schemaname']:<25} {r['relname']:<35} {r['approx_rows']:>12,}")

    pk_rows = [r for r in rows if r not in no_pk_rows]
    if pk_rows:
        print(f"\nTables WITH primary keys ({len(pk_rows)} - safe, will get harmless 'already exists' errors):")
        for r in pk_rows[:10]:
            print(f"  {r['schemaname']}.{r['relname']}: ~{r['approx_rows']:,} rows")
        if len(pk_rows) > 10:
            print(f"  ... and {len(pk_rows) - 10} more")

    print("\nRECOMMENDATION: Run 'clean-schemas' to DROP and recreate target schemas before re-restoring.")
    print("DO NOT simply re-run pg_restore on top of existing data.")


def cmd_clean_schemas(args):
    if not args.schemas:
        print("ERROR: --schemas is required for clean-schemas", file=sys.stderr)
        sys.exit(1)

    schema_list = [s.strip() for s in args.schemas.split(',')]

    if not args.confirm:
        print(f"This will DROP and recreate the following schemas on the target:")
        for s in schema_list:
            print(f"  - {s}")
        print(f"\nTarget: {args.target_host}/{args.target_dbname}")
        print("\nAll data in these schemas will be permanently deleted.")
        print("Re-run with --confirm to execute.")
        return

    print(f"Connecting to target: {args.target_host}/{args.target_dbname}...")
    tgt_conn = connect_target(args)
    tgt_conn.autocommit = True

    for schema in schema_list:
        try:
            print(f"  Dropping schema {schema}...")
            cur = tgt_conn.cursor()
            if _HAS_PG_SQL:
                cur.execute(_pg_sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(_pg_sql.Identifier(schema)))
                cur.execute(_pg_sql.SQL("CREATE SCHEMA {}").format(_pg_sql.Identifier(schema)))
            else:
                cur.execute(f'DROP SCHEMA IF EXISTS {_quote_ident(schema)} CASCADE')
                cur.execute(f'CREATE SCHEMA {_quote_ident(schema)}')
            print(f"  [OK] {schema} dropped and recreated")
        except Exception as e:
            print(f"  [ERROR] {schema}: {e}")

    tgt_conn.close()
    print("\nSchemas cleaned. You can now re-run pg_restore safely.")


def main():
    parser = argparse.ArgumentParser(
        description='Pre-restore target preparation for pg_dump/pg_restore migrations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  preflight-check  MANDATORY: verify target schemas are clean before migration
  extensions       Query source for extensions and create them on target
  check-data       Check if target schemas already contain data (pre-restore safety check)
  clean-schemas    DROP and recreate target schemas before re-restore

Examples:
  python prepare_target.py preflight-check \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin \\
      --schemas analytics,reporting

  python prepare_target.py extensions -H src.example.com -d mydb -U admin \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin

  python prepare_target.py extensions ... --dry-run  # Preview only

  python prepare_target.py check-data \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin \\
      --schemas analytics,reporting

  python prepare_target.py clean-schemas \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin \\
      --schemas analytics,reporting --confirm
""")

    subparsers = parser.add_subparsers(dest='command')
    subparsers.required = True

    pre_parser = subparsers.add_parser('preflight-check',
                                       help='MANDATORY: verify target schemas are clean before migration')
    add_target_args(pre_parser)
    add_source_args(pre_parser)
    pre_parser.add_argument('--schemas', required=True,
                            help='Comma-separated list of schemas being migrated')
    pre_parser.add_argument('--i-understand-the-risks', dest='force', action='store_true',
                            help='Bypass preflight: ACKNOWLEDGE that target schemas may already contain '
                                 'objects that will be overwritten or merged. Refuses to proceed with the '
                                 'plain --force flag — you must use the long form so this never gets typed '
                                 'by accident in CI.')

    ext_parser = subparsers.add_parser('extensions', help='Create source extensions on target')
    add_source_args(ext_parser)
    add_target_args(ext_parser)
    ext_parser.add_argument('--dry-run', action='store_true',
                            help='Show SQL without executing')

    check_parser = subparsers.add_parser('check-data', help='Check for existing data on target')
    add_target_args(check_parser)
    add_source_args(check_parser)
    check_parser.add_argument('--schemas', help='Comma-separated list of schemas to check')

    clean_parser = subparsers.add_parser('clean-schemas', help='Drop and recreate target schemas')
    add_target_args(clean_parser)
    add_source_args(clean_parser)
    clean_parser.add_argument('--schemas', help='Comma-separated list of schemas to drop/recreate')
    clean_parser.add_argument('--confirm', action='store_true',
                              help='Actually execute (without this flag, dry run only)')

    args = parser.parse_args()
    check_driver()
    # Resolve --source-service / --target-service from ~/.pg_service.conf BEFORE
    # validation. Each subcommand only adds the flag(s) it needs; getattr-based
    # short-circuit in _apply_*_service handles the missing-attr case safely.
    _apply_source_service(args)
    _apply_target_service(args)

    if args.command == 'preflight-check':
        if not args.target_host or not args.target_dbname or not args.target_user:
            parser.error("Target connection required for preflight-check command (--target-host/--target-dbname/--target-user OR --target-service NAME)")
        if args.force:
            # Loud warning to stderr so this can never quietly green a CI job.
            print("WARNING: --i-understand-the-risks set; preflight schema-collision check SKIPPED.",
                  file=sys.stderr)
            print("         Target schemas MAY ALREADY CONTAIN objects that will be overwritten or merged.",
                  file=sys.stderr)
            print("PREFLIGHT: SKIPPED (acknowledged)")
        else:
            cmd_preflight_check(args)
    elif args.command == 'extensions':
        if not args.host or not args.dbname or not args.user:
            parser.error("Source connection required for extensions command (OR --source-service NAME)")
        if not args.target_host or not args.target_dbname or not args.target_user:
            parser.error("Target connection required for extensions command (OR --target-service NAME)")
        cmd_extensions(args)
    elif args.command == 'check-data':
        if not args.target_host or not args.target_dbname or not args.target_user:
            parser.error("Target connection required for check-data command (OR --target-service NAME)")
        cmd_check_data(args)
    elif args.command == 'clean-schemas':
        if not args.target_host or not args.target_dbname or not args.target_user:
            parser.error("Target connection required for clean-schemas command (OR --target-service NAME)")
        cmd_clean_schemas(args)


if __name__ == '__main__':
    main()
