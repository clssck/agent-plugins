#!/usr/bin/env python3
"""
cutover_tools.py
Generate and optionally execute cutover commands for PostgreSQL migration.

Consolidates sequence_sync.sql and trigger_management.sql into a single
Python script that connects directly to source/target databases.

Subcommands:
    sequences   - Generate sequence sync commands (run AFTER cutover)
    triggers    - Generate trigger disable/enable commands
    all         - Generate full cutover runbook

Usage:
    python cutover_tools.py sequences --host src.example.com -d mydb -U admin
    python cutover_tools.py triggers --host src.example.com -d mydb -U admin
    python cutover_tools.py all --host src.example.com -d mydb -U admin --output cutover.sql
"""

import argparse
import json
import sys
from datetime import datetime

# Resolve pg_common from the shared generic-PG layer at snowflake-postgres/scripts/shared/.
# pytest handles this via pythonpath; for direct invocation we add it to sys.path here.
from pathlib import Path as _P
_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from pg_common import (
    check_driver, query,
    add_source_args, add_target_args,
    connect_source, connect_target,
    quote_ident,
    _apply_source_service, _apply_target_service,
)


def _normalize_schemas(schemas):
    if not schemas:
        return []
    if isinstance(schemas, str):
        schemas = schemas.split(',')
    return [str(s).strip() for s in schemas if str(s).strip()]


def _schema_filter_clause(schemas):
    schemas = _normalize_schemas(schemas)
    if not schemas:
        return "", ()
    placeholders = ", ".join(["%s"] * len(schemas))
    return f" AND n.nspname IN ({placeholders})", tuple(schemas)


def collect_sequences(conn, schemas=None):
    schema_filter_sql, params = _schema_filter_clause(schemas)
    return query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS name,
               pg_sequence_last_value(c.oid) AS last_value,
               (SELECT t.relname || '.' || a.attname
                FROM pg_depend d
                JOIN pg_class t ON t.oid = d.refobjid
                JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
                WHERE d.objid = c.oid AND d.deptype = 'a'
                LIMIT 1) AS owned_by
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S'
        AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        {schema_filter_sql}
        ORDER BY n.nspname, c.relname
    """, params if params else None)


def generate_sequence_sync_sql(sequences, buffer=1000):
    lines = [
        f"-- Sequence Sync Script",
        f"-- Generated: {datetime.now().isoformat()}",
        f"-- Buffer: +{buffer} to ensure new inserts get unique IDs",
        f"-- Run this on the TARGET database AFTER cutover",
        "",
        "BEGIN;",
        "",
    ]
    for seq in sequences:
        # The fqn is embedded as a SQL literal (regclass), not an identifier;
        # escape any embedded `'` in either part. quote_ident handles `"` for
        # the regclass-cast resolution side.
        ident_fqn = f"{quote_ident(seq['schema'])}.{quote_ident(seq['name'])}"
        literal_fqn = ident_fqn.replace("'", "''")
        last = seq['last_value']
        new_val = (int(last) if last else 1) + buffer
        owned = f"  -- owned by: {seq['owned_by']}" if seq.get('owned_by') else ""
        lines.append(f"SELECT setval('{literal_fqn}', {new_val});{owned}")
    lines.extend(["", "COMMIT;", ""])
    return '\n'.join(lines)


def collect_triggers(conn, schemas=None):
    schema_filter_sql, params = _schema_filter_clause(schemas)
    return query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS table_name,
               t.tgname AS trigger_name,
               CASE
                   WHEN t.tgtype & 2 = 2 THEN 'BEFORE'
                   WHEN t.tgtype & 64 = 64 THEN 'INSTEAD OF'
                   ELSE 'AFTER'
               END AS timing,
               array_to_string(array_remove(ARRAY[
                   CASE WHEN t.tgtype & 4 = 4 THEN 'INSERT' END,
                   CASE WHEN t.tgtype & 8 = 8 THEN 'DELETE' END,
                   CASE WHEN t.tgtype & 16 = 16 THEN 'UPDATE' END,
                   CASE WHEN t.tgtype & 32 = 32 THEN 'TRUNCATE' END
               ], NULL), '/') AS events,
               CASE t.tgenabled
                   WHEN 'O' THEN 'origin'
                   WHEN 'D' THEN 'disabled'
                   WHEN 'R' THEN 'replica'
                   WHEN 'A' THEN 'always'
               END AS current_status,
               p.proname AS function_name
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_proc p ON p.oid = t.tgfoid
        WHERE NOT t.tgisinternal
        AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        {schema_filter_sql}
        ORDER BY n.nspname, c.relname, t.tgname
    """, params if params else None)


def _qualified_table_names(triggers):
    return sorted(set(
        f"{quote_ident(t['schema'])}.{quote_ident(t['table_name'])}" for t in triggers
    ))


def generate_trigger_disable_sql(triggers):
    tables = _qualified_table_names(triggers)
    lines = [
        "-- Disable ALL triggers (run on TARGET before initial sync)",
        f"-- Generated: {datetime.now().isoformat()}",
        "",
        "BEGIN;",
    ]
    for t in tables:
        lines.append(f"ALTER TABLE {t} DISABLE TRIGGER ALL;")
    lines.extend(["COMMIT;", ""])
    return '\n'.join(lines)


def generate_trigger_enable_sql(triggers):
    tables = _qualified_table_names(triggers)
    lines = [
        "-- Re-enable ALL triggers (run on TARGET after cutover)",
        f"-- Generated: {datetime.now().isoformat()}",
        "",
        "BEGIN;",
    ]
    for t in tables:
        lines.append(f"ALTER TABLE {t} ENABLE TRIGGER ALL;")
    lines.extend(["COMMIT;", ""])
    return '\n'.join(lines)


def collect_problematic_triggers(conn, schemas=None):
    schema_filter_sql, params = _schema_filter_clause(schemas)
    always_triggers = query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS table_name,
               t.tgname AS trigger_name
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal
        AND t.tgenabled = 'A'
        AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        {schema_filter_sql}
    """, params if params else None)
    return always_triggers


def cmd_sequences(args):
    print(f"Connecting to {args.host}/{args.dbname}...")
    conn = connect_source(args)
    conn.autocommit = True

    print("Collecting sequences...")
    sequences = collect_sequences(conn, schemas=getattr(args, 'schemas', None))
    conn.close()

    print(f"  Found {len(sequences)} sequences")

    sql = generate_sequence_sync_sql(sequences, buffer=args.buffer)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(sql)
        print(f"Sequence sync SQL written to: {args.output}")
    else:
        print()
        print(sql)

    if args.execute:
        print("Executing on target...")
        tgt_conn = connect_target(args)
        tgt_conn.autocommit = False
        try:
            for seq in sequences:
                # setval('schema.seq', N) requires the regclass-cast argument
                # to be a string literal containing a fully-qualified name. We
                # build the qualified name with quote_ident() on each part and
                # pass the cast text as a parameter to keep both sides safe.
                fqn = f"{quote_ident(seq['schema'])}.{quote_ident(seq['name'])}"
                new_val = (int(seq['last_value']) if seq['last_value'] else 1) + args.buffer
                query(tgt_conn, "SELECT setval(%s::regclass, %s)", (fqn, new_val))
            tgt_conn.commit()
            print(f"  Synced {len(sequences)} sequences on target")
        except Exception as e:
            tgt_conn.rollback()
            print(f"  ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            tgt_conn.close()

    if args.json:
        with open(args.json, 'w') as f:
            json.dump([dict(s) for s in sequences], f, indent=2, default=str)
        print(f"JSON saved: {args.json}")


def cmd_triggers(args):
    print(f"Connecting to {args.host}/{args.dbname}...")
    conn = connect_source(args)
    conn.autocommit = True

    print("Collecting triggers...")
    triggers = collect_triggers(conn, schemas=getattr(args, 'schemas', None))
    always = collect_problematic_triggers(conn, schemas=getattr(args, 'schemas', None))
    conn.close()

    print(f"  Found {len(triggers)} user triggers")
    if always:
        print(f"  WARNING: {len(always)} ALWAYS triggers (fire during replication):")
        for t in always:
            print(f"    - {t['schema']}.{t['table_name']}.{t['trigger_name']}")

    disable_sql = generate_trigger_disable_sql(triggers)
    enable_sql = generate_trigger_enable_sql(triggers)

    if args.output:
        with open(args.output, 'w') as f:
            f.write("-- ============================================\n")
            f.write("-- PART 1: DISABLE TRIGGERS (before sync)\n")
            f.write("-- ============================================\n\n")
            f.write(disable_sql)
            f.write("\n\n")
            f.write("-- ============================================\n")
            f.write("-- PART 2: ENABLE TRIGGERS (after cutover)\n")
            f.write("-- ============================================\n\n")
            f.write(enable_sql)
        print(f"Trigger management SQL written to: {args.output}")
    else:
        print()
        print(disable_sql)
        print()
        print(enable_sql)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump({
                'triggers': [dict(t) for t in triggers],
                'always_triggers': [dict(t) for t in always],
            }, f, indent=2, default=str)
        print(f"JSON saved: {args.json}")


def cmd_all(args):
    print(f"Connecting to {args.host}/{args.dbname}...")
    conn = connect_source(args)
    conn.autocommit = True

    print("Collecting sequences...")
    sequences = collect_sequences(conn, schemas=getattr(args, 'schemas', None))
    print("Collecting triggers...")
    triggers = collect_triggers(conn, schemas=getattr(args, 'schemas', None))
    always = collect_problematic_triggers(conn, schemas=getattr(args, 'schemas', None))
    conn.close()

    lines = [
        f"-- =================================================================",
        f"-- CUTOVER RUNBOOK",
        f"-- Generated: {datetime.now().isoformat()}",
        f"-- Database: {args.dbname} on {args.host}",
        f"-- =================================================================",
        f"",
        f"-- Sequences: {len(sequences)}",
        f"-- Triggers:  {len(triggers)}",
        f"-- ALWAYS triggers (warning): {len(always)}",
        f"",
    ]

    if triggers:
        lines.append("-- =================================================================")
        lines.append("-- STEP 1: DISABLE TRIGGERS (run on TARGET before initial sync)")
        lines.append("-- =================================================================")
        lines.append("")
        lines.append(generate_trigger_disable_sql(triggers))
        lines.append("")

    lines.append("-- =================================================================")
    lines.append("-- STEP 2: SYNC SEQUENCES (run on TARGET after stopping writes)")
    lines.append("-- =================================================================")
    lines.append("")
    lines.append(generate_sequence_sync_sql(sequences, buffer=args.buffer))
    lines.append("")

    if triggers:
        lines.append("-- =================================================================")
        lines.append("-- STEP 3: RE-ENABLE TRIGGERS (run on TARGET after cutover)")
        lines.append("-- =================================================================")
        lines.append("")
        lines.append(generate_trigger_enable_sql(triggers))

    full_sql = '\n'.join(lines)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(full_sql)
        print(f"Cutover runbook written to: {args.output}")
    else:
        print()
        print(full_sql)

    print(f"\nSummary:")
    print(f"  Sequences to sync:  {len(sequences)}")
    print(f"  Triggers to manage: {len(triggers)}")
    if always:
        print(f"  ALWAYS triggers:    {len(always)} (review these!)")


def main():
    parser = argparse.ArgumentParser(
        description='Generate cutover commands for PostgreSQL migration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Subcommands:
  sequences   Generate sequence sync SQL (run after cutover)
  triggers    Generate trigger disable/enable SQL
  all         Generate full cutover runbook

Examples:
  python cutover_tools.py sequences -H src.example.com -d mydb -U admin
  python cutover_tools.py triggers -H src.example.com -d mydb -U admin -o triggers.sql
  python cutover_tools.py all -H src.example.com -d mydb -U admin -o cutover.sql
  python cutover_tools.py sequences ... --execute --target-host sf-pg.example.com
""")
    sub = parser.add_subparsers(dest='command')

    seq_p = sub.add_parser('sequences', help='Generate sequence sync commands')
    add_source_args(seq_p)
    add_target_args(seq_p)
    seq_p.add_argument('--output', '-o', help='Write SQL to file')
    seq_p.add_argument('--json', help='Save sequence data as JSON')
    seq_p.add_argument('--buffer', type=int, default=1000, help='Buffer to add to sequence values (default: 1000)')
    seq_p.add_argument('--execute', action='store_true', help='Execute sync on target (requires target params)')
    seq_p.add_argument('--schemas', help='Comma-separated list of schemas to include (default: all non-system schemas)')

    trig_p = sub.add_parser('triggers', help='Generate trigger management commands')
    add_source_args(trig_p)
    trig_p.add_argument('--output', '-o', help='Write SQL to file')
    trig_p.add_argument('--json', help='Save trigger data as JSON')
    trig_p.add_argument('--schemas', help='Comma-separated list of schemas to include (default: all non-system schemas)')

    all_p = sub.add_parser('all', help='Generate full cutover runbook')
    add_source_args(all_p)
    add_target_args(all_p)
    all_p.add_argument('--output', '-o', help='Write SQL to file')
    all_p.add_argument('--json', help='Save data as JSON')
    all_p.add_argument('--buffer', type=int, default=1000, help='Sequence buffer (default: 1000)')
    all_p.add_argument('--schemas', help='Comma-separated list of schemas to include (default: all non-system schemas)')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    check_driver()
    # --source-service / --target-service populate args from ~/.pg_service.conf
    # before validation. _apply_*_service short-circuits when service is unset
    # OR when the subcommand doesn't define the corresponding flag (triggers
    # subcommand has source-only via add_source_args; target_service attr is
    # absent → getattr default '' → no-op).
    _apply_source_service(args)
    _apply_target_service(args)

    if not args.host or not args.dbname or not args.user:
        parser.error("Source connection params required (--host, --dbname, --user, OR --source-service NAME)")

    if args.command == 'sequences':
        cmd_sequences(args)
    elif args.command == 'triggers':
        cmd_triggers(args)
    elif args.command == 'all':
        cmd_all(args)


if __name__ == '__main__':
    main()
