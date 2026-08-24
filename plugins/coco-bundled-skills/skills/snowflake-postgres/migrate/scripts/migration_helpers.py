#!/usr/bin/env python3
"""
migration_helpers.py
Specialized migration helpers for PostGIS, pgvector, and logical replication blockers.

Subcommands:
  postgis            PostGIS spatial data assessment and migration command generation
  vector-indexes     pgvector index inventory, drop/rebuild command generation
  blockers           Comprehensive logical replication blocker detection
  replication-check  Quick replication readiness check
"""
import argparse
import json
import os
import sys

# Resolve pg_common from the shared generic-PG layer at snowflake-postgres/scripts/shared/.
# pytest handles this via pythonpath; for direct invocation we add it to sys.path here.
from pathlib import Path as _P
_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from pg_common import (
    add_source_args, connect_source, query, scalar, check_driver, detect_pg_version
)


def cmd_postgis(args):
    check_driver()
    conn = connect_source(args)

    has_postgis = scalar(conn, "SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
    if not has_postgis:
        print("PostGIS is not installed in this database. Nothing to do.")
        conn.close()
        return

    version = scalar(conn, "SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
    full_ver = None
    try:
        full_ver = scalar(conn, "SELECT PostGIS_Full_Version()")
    except Exception:
        pass

    print("=" * 72)
    print("POSTGIS MIGRATION ASSESSMENT")
    print("=" * 72)
    print(f"\nPostGIS version: {version}")
    if full_ver:
        print(f"Full version:    {full_ver}")

    print("\n--- Geometry Columns ---")
    geom_cols = query(conn, """
        SELECT f_table_schema || '.' || f_table_name AS table_name,
               f_geometry_column AS column_name,
               type AS geometry_type,
               srid,
               coord_dimension AS dims
        FROM geometry_columns
        ORDER BY f_table_schema, f_table_name
    """)
    if geom_cols:
        for g in geom_cols:
            print(f"  {g['table_name']}.{g['column_name']}  type={g['geometry_type']}  srid={g['srid']}  dims={g['dims']}")
    else:
        print("  (none)")

    print("\n--- Geography Columns ---")
    geog_cols = query(conn, """
        SELECT f_table_schema || '.' || f_table_name AS table_name,
               f_geography_column AS column_name,
               type AS geography_type,
               srid
        FROM geography_columns
        ORDER BY f_table_schema, f_table_name
    """)
    if geog_cols:
        for g in geog_cols:
            print(f"  {g['table_name']}.{g['column_name']}  type={g['geography_type']}  srid={g['srid']}")
    else:
        print("  (none)")

    has_raster = scalar(conn, "SELECT 1 FROM pg_extension WHERE extname = 'postgis_raster'")
    raster_cols = []
    if has_raster:
        print("\n--- Raster Columns ---")
        try:
            raster_cols = query(conn, """
                SELECT r_table_schema || '.' || r_table_name AS table_name,
                       r_raster_column AS column_name,
                       srid,
                       num_bands
                FROM raster_columns
            """)
            if raster_cols:
                for r in raster_cols:
                    print(f"  {r['table_name']}.{r['column_name']}  srid={r['srid']}  bands={r['num_bands']}  [REQUIRES SPECIAL HANDLING]")
            else:
                print("  (none)")
        except Exception:
            print("  (raster_columns view not available)")

    print("\n--- SRIDs In Use ---")
    srids = query(conn, """
        WITH used_srids AS (
            SELECT DISTINCT srid FROM geometry_columns
            UNION
            SELECT DISTINCT srid FROM geography_columns
        )
        SELECT s.srid,
               s.auth_name || ':' || s.auth_srid AS authority,
               CASE WHEN s.srid > 900000 THEN 'CUSTOM' ELSE 'Standard' END AS status
        FROM used_srids u
        JOIN spatial_ref_sys s ON s.srid = u.srid
        ORDER BY s.srid
    """)
    custom_srids = []
    for s in srids:
        tag = "  [CUSTOM - export required]" if s['status'] == 'CUSTOM' else ""
        print(f"  SRID {s['srid']}  ({s['authority']}){tag}")
        if s['status'] == 'CUSTOM':
            custom_srids.append(s['srid'])

    if custom_srids:
        print("\n--- Custom SRID Export (run on TARGET first) ---")
        for srid_val in custom_srids:
            rows = query(conn, """
                SELECT srid, auth_name, auth_srid, srtext, proj4text
                FROM spatial_ref_sys WHERE srid = %s
            """, (srid_val,))
            for r in rows:
                srtext = r['srtext'].replace("'", "''") if r['srtext'] else ''
                proj4 = ("'" + r['proj4text'].replace("'", "''") + "'") if r['proj4text'] else 'NULL'
                auth = ("'" + r['auth_name'] + "'") if r['auth_name'] else 'NULL'
                auth_srid = str(r['auth_srid']) if r['auth_srid'] is not None else 'NULL'
                print(f"INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, srtext, proj4text) VALUES "
                      f"({r['srid']}, {auth}, {auth_srid}, '{srtext}', {proj4}) ON CONFLICT (srid) DO NOTHING;")

    print("\n--- Spatial Indexes ---")
    sp_indexes = query(conn, """
        SELECT schemaname || '.' || tablename AS table_name,
               indexname,
               indexdef,
               pg_size_pretty(pg_relation_size((schemaname || '.' || indexname)::regclass)) AS size
        FROM pg_indexes
        WHERE (indexdef LIKE '%%gist%%' OR indexdef LIKE '%%spgist%%' OR indexdef LIKE '%%brin%%')
          AND (indexdef LIKE '%%geom%%' OR indexdef LIKE '%%geography%%' OR indexdef LIKE '%%geometry%%')
        ORDER BY schemaname, tablename
    """)
    if sp_indexes:
        for ix in sp_indexes:
            itype = 'GiST' if 'gist' in ix['indexdef'].lower() else ('SP-GiST' if 'spgist' in ix['indexdef'].lower() else 'BRIN')
            print(f"  {ix['table_name']}  {ix['indexname']}  type={itype}  size={ix['size']}  [Rebuild after migration]")
    else:
        print("  (none)")

    if sp_indexes:
        print("\n--- Index Rebuild Commands (run on TARGET after data load) ---")
        for ix in sp_indexes:
            rebuild = ix['indexdef'].replace('CREATE INDEX', 'CREATE INDEX CONCURRENTLY', 1)
            print(f"DROP INDEX IF EXISTS {ix['table_name'].split('.')[0]}.{ix['indexname']};")
            print(f"{rebuild};")
            print(f"ANALYZE {ix['table_name']};")
            print()

    print("\n--- Geometry Validation Queries (run on BOTH source and target) ---")
    for g in geom_cols:
        col = g['column_name']
        tbl = g['table_name']
        print(f"-- Validate {tbl}.{col}")
        print(f"SELECT count(*) AS total_rows,")
        print(f"       count(*) FILTER (WHERE ST_IsValid({col})) AS valid_geoms,")
        print(f"       count(*) FILTER (WHERE NOT ST_IsValid({col})) AS invalid_geoms,")
        print(f"       count(*) FILTER (WHERE {col} IS NULL) AS null_geoms,")
        print(f"       ST_AsText(ST_Extent({col})) AS extent")
        print(f"FROM {tbl};")
        print()

    has_topology = scalar(conn, "SELECT 1 FROM pg_extension WHERE extname = 'postgis_topology'")
    if has_topology:
        print("--- PostGIS Topology ---")
        try:
            topos = query(conn, "SELECT id, name, srid, precision, hasz FROM topology.topology")
            for t in topos:
                print(f"  Topology: {t['name']}  srid={t['srid']}  [REQUIRES SPECIAL HANDLING]")
        except Exception:
            print("  (topology schema not accessible)")

    print("\n--- Summary ---")
    print(f"  Geometry columns:  {len(geom_cols)}")
    print(f"  Geography columns: {len(geog_cols)}")
    print(f"  Custom SRIDs:      {len(custom_srids)}")
    print(f"  Spatial indexes:   {len(sp_indexes)}")
    print(f"  Raster tables:     {len(raster_cols)}")
    print("\nMigration steps:")
    print("  1. Install PostGIS on target: CREATE EXTENSION postgis;")
    print("  2. Export and import custom SRIDs (see above)")
    print("  3. Migrate data via logical replication or pg_dump")
    print("  4. Recreate spatial indexes (see rebuild commands above)")
    print("  5. Validate geometries (see validation queries above)")

    if args.output:
        data = {
            'postgis_version': version,
            'geometry_columns': geom_cols,
            'geography_columns': geog_cols,
            'custom_srids': custom_srids,
            'spatial_indexes': [{'table': ix['table_name'], 'index': ix['indexname']} for ix in sp_indexes],
            'raster_tables': raster_cols,
        }
        with open(args.output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"\nJSON data written to {args.output}")

    conn.close()


def cmd_vector_indexes(args):
    check_driver()
    conn = connect_source(args)

    has_vector = scalar(conn, "SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    if not has_vector:
        print("pgvector is not installed in this database. Nothing to do.")
        conn.close()
        return

    version = scalar(conn, "SELECT extversion FROM pg_extension WHERE extname = 'vector'")

    print("=" * 72)
    print("PGVECTOR INDEX MIGRATION")
    print("=" * 72)
    print(f"\npgvector version: {version}")

    print("\n--- Vector Columns ---")
    vec_cols = query(conn, """
        SELECT n.nspname || '.' || c.relname AS table_name,
               a.attname AS column_name,
               format_type(a.atttypid, a.atttypmod) AS data_type,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS table_size
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE a.atttypid = 'vector'::regtype
          AND a.attnum > 0 AND NOT a.attisdropped
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        ORDER BY n.nspname, c.relname, a.attnum
    """)
    if vec_cols:
        for v in vec_cols:
            print(f"  {v['table_name']}.{v['column_name']}  {v['data_type']}  table_size={v['table_size']}")
    else:
        print("  (none)")

    print("\n--- Vector Indexes ---")
    vec_indexes = query(conn, """
        SELECT schemaname || '.' || tablename AS table_name,
               indexname,
               indexdef,
               pg_size_pretty(pg_relation_size((schemaname || '.' || indexname)::regclass)) AS index_size
        FROM pg_indexes
        WHERE indexdef LIKE '%%vector%%'
          AND (indexdef LIKE '%%ivfflat%%' OR indexdef LIKE '%%hnsw%%')
        ORDER BY schemaname, tablename, indexname
    """)
    if vec_indexes:
        for ix in vec_indexes:
            itype = 'IVFFlat' if 'ivfflat' in ix['indexdef'].lower() else 'HNSW'
            dist = 'L2'
            if 'vector_ip_ops' in ix['indexdef']:
                dist = 'Inner Product'
            elif 'vector_cosine_ops' in ix['indexdef']:
                dist = 'Cosine'
            print(f"  {ix['table_name']}  {ix['indexname']}  type={itype}  distance={dist}  size={ix['index_size']}")
    else:
        print("  (none)")

    if vec_indexes:
        print("\n--- PRE-MIGRATION: Drop Commands (faster data load) ---")
        for ix in vec_indexes:
            schema = ix['table_name'].split('.')[0]
            print(f"DROP INDEX IF EXISTS {schema}.{ix['indexname']};")

        print("\n--- POST-MIGRATION: Rebuild Commands ---")
        for ix in vec_indexes:
            rebuild = ix['indexdef'].replace('CREATE INDEX', 'CREATE INDEX CONCURRENTLY', 1)
            print(f"-- Rebuild: {ix['indexname']}")
            print(f"{rebuild};")
            print(f"ANALYZE {ix['table_name']};")
            print()

        print("--- Tuning Guidance ---")
        print("  IVFFlat lists:      rows < 1M -> rows/1000; rows >= 1M -> sqrt(rows)")
        print("  HNSW m:             16 (default), 32-64 for better recall")
        print("  HNSW ef_construction: 64 (default), higher = better quality, slower build")

    print(f"\n--- Summary ---")
    print(f"  Vector columns: {len(vec_cols)}")
    ivf_count = sum(1 for ix in vec_indexes if 'ivfflat' in ix['indexdef'].lower())
    hnsw_count = sum(1 for ix in vec_indexes if 'hnsw' in ix['indexdef'].lower())
    print(f"  IVFFlat indexes: {ivf_count}")
    print(f"  HNSW indexes:    {hnsw_count}")
    print("\nMigration steps:")
    print("  1. Install pgvector on target: CREATE EXTENSION vector;")
    print("  2. (Optional) Drop indexes before migration for faster load")
    print("  3. Migrate data via logical replication or pg_dump")
    print("  4. Rebuild vector indexes using commands above")
    print("  5. Tune parameters based on actual data size")

    if args.output:
        data = {
            'pgvector_version': version,
            'vector_columns': vec_cols,
            'vector_indexes': [{'table': ix['table_name'], 'index': ix['indexname'], 'def': ix['indexdef']} for ix in vec_indexes],
        }
        with open(args.output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"\nJSON data written to {args.output}")

    conn.close()


def cmd_blockers(args):
    check_driver()
    conn = connect_source(args)
    pg_version = detect_pg_version(conn)

    schema_filter = None
    if args.schemas:
        schema_filter = [s.strip() for s in args.schemas.split(',')]

    def sf_clause(alias='n'):
        if schema_filter:
            placeholders = ','.join(['%s'] * len(schema_filter))
            return f" AND {alias}.nspname IN ({placeholders})", schema_filter
        return "", []

    print("=" * 72)
    print("LOGICAL REPLICATION BLOCKERS DETECTION")
    print("=" * 72)

    blockers = []

    sf_sql, sf_params = sf_clause('n')
    rows = query(conn, f"""
        SELECT n.nspname AS schema_name, c.relname AS object_name,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relpersistence = 'u' AND c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          {sf_sql}
        ORDER BY pg_total_relation_size(c.oid) DESC
    """, sf_params or None)
    for r in rows:
        blockers.append({**r, 'type': 'UNLOGGED_TABLE', 'severity': 'HIGH',
                         'remediation': f"ALTER TABLE {r['schema_name']}.{r['object_name']} SET LOGGED; OR use pg_dump"})

    sf_sql, sf_params = sf_clause('n')
    rows = query(conn, f"""
        SELECT n.nspname AS schema_name, c.relname AS object_name,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS size,
               CASE c.relreplident
                   WHEN 'd' THEN 'default' WHEN 'n' THEN 'nothing'
                   WHEN 'f' THEN 'full' WHEN 'i' THEN 'index'
               END AS replica_identity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
        WHERE c.relkind = 'r' AND c.relpersistence = 'p'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND pk.oid IS NULL
          {sf_sql}
        ORDER BY pg_total_relation_size(c.oid) DESC
    """, sf_params or None)
    for r in rows:
        if r['replica_identity'] in ('full', 'index'):
            sev = 'LOW' if r['replica_identity'] == 'index' else 'MEDIUM'
        else:
            sev = 'HIGH'
        blockers.append({**r, 'type': 'NO_PRIMARY_KEY', 'severity': sev,
                         'remediation': f"Add PK or set REPLICA IDENTITY FULL on {r['schema_name']}.{r['object_name']}"})

    sf_sql, sf_params = sf_clause('pn')
    rows = query(conn, f"""
        SELECT DISTINCT pn.nspname AS schema_name, parent.relname AS object_name,
               pg_size_pretty(pg_total_relation_size(parent.oid)) AS size,
               (SELECT count(*) FROM pg_inherits WHERE inhparent = parent.oid) AS child_count
        FROM pg_inherits
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_namespace pn ON pn.oid = parent.relnamespace
        WHERE parent.relkind = 'r'
          AND pn.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf_sql}
    """, sf_params or None)
    for r in rows:
        blockers.append({**r, 'type': 'TABLE_INHERITANCE', 'severity': 'HIGH',
                         'remediation': 'Denormalize, migrate each table separately via pg_dump, or use COPY'})

    rows = query(conn, """
        SELECT ft.foreign_table_schema AS schema_name,
               ft.foreign_table_name AS object_name,
               ft.foreign_server_name AS server
        FROM information_schema.foreign_tables ft
    """)
    for r in rows:
        if schema_filter and r['schema_name'] not in schema_filter:
            continue
        blockers.append({**r, 'type': 'FOREIGN_TABLE', 'severity': 'MEDIUM', 'size': '0 bytes',
                         'remediation': 'Recreate FDW and foreign table on target after migration'})

    lo_count = scalar(conn, "SELECT count(*) FROM pg_largeobject_metadata") or 0
    if lo_count > 0:
        lo_size = scalar(conn, "SELECT pg_size_pretty(COALESCE(sum(pg_lo_size(oid)), 0)) FROM pg_largeobject_metadata")
        blockers.append({'type': 'LARGE_OBJECTS', 'severity': 'MEDIUM',
                         'schema_name': 'pg_catalog', 'object_name': f'{lo_count} large objects',
                         'size': lo_size or '0 bytes',
                         'remediation': 'Export large objects: pg_dump -b OR lo_export() to files'})

    sf_sql, sf_params = sf_clause('n')
    rows = query(conn, f"""
        SELECT n.nspname AS schema_name, c.relname AS object_name,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'm'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf_sql}
    """, sf_params or None)
    for r in rows:
        blockers.append({**r, 'type': 'MATERIALIZED_VIEW', 'severity': 'LOW',
                         'remediation': 'Recreate and REFRESH MATERIALIZED VIEW after migration'})

    sf_sql, sf_params = sf_clause('n')
    rows = query(conn, f"""
        SELECT n.nspname AS schema_name, c.relname AS object_name
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema')
          {sf_sql}
    """, sf_params or None)
    for r in rows:
        blockers.append({**r, 'type': 'SEQUENCE', 'severity': 'INFO', 'size': '0 bytes',
                         'remediation': 'Sync sequences AFTER cutover using cutover_tools.py'})

    rows = query(conn, """
        SELECT evtname AS object_name, evtevent AS event
        FROM pg_event_trigger
    """)
    for r in rows:
        blockers.append({**r, 'type': 'EVENT_TRIGGER', 'severity': 'LOW',
                         'schema_name': 'pg_catalog', 'size': '0 bytes',
                         'remediation': 'Recreate event trigger manually on target'})

    print(f"\nFound {len(blockers)} items\n")

    severity_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2, 'INFO': 3}
    blockers.sort(key=lambda b: (severity_order.get(b['severity'], 9), b['type']))

    from collections import Counter
    type_counts = Counter((b['type'], b['severity']) for b in blockers)
    print("--- Summary by Type ---")
    for (btype, sev), cnt in sorted(type_counts.items(), key=lambda x: (severity_order.get(x[0][1], 9), x[0][0])):
        print(f"  {sev:6s}  {btype:25s}  count={cnt}")

    high_blockers = [b for b in blockers if b['severity'] == 'HIGH']
    if high_blockers:
        print("\n--- HIGH Severity Blockers ---")
        for b in high_blockers:
            obj = f"{b.get('schema_name', '')}.{b['object_name']}" if b.get('schema_name') else b['object_name']
            print(f"  {b['type']:25s}  {obj:40s}  {b.get('size', '')}")
            print(f"    Remediation: {b['remediation']}")

    no_high = len([b for b in blockers if b['severity'] == 'HIGH' and b['type'] not in ('SEQUENCE',)])
    if no_high == 0:
        print("\n  LOGICAL REPLICATION VIABLE - No high-severity blockers")
    elif any(b['type'] in ('UNLOGGED_TABLE', 'TABLE_INHERITANCE') for b in blockers if b['severity'] == 'HIGH'):
        print("\n  HYBRID MIGRATION REQUIRED - Some objects need pg_dump")
    else:
        print("\n  ACTION REQUIRED - Address high-severity blockers before migration")

    if args.output:
        with open(args.output, 'w') as f:
            json.dump(blockers, f, indent=2, default=str)
        print(f"\nJSON data written to {args.output}")

    conn.close()


def cmd_replication_check(args):
    check_driver()
    conn = connect_source(args)

    print("=" * 72)
    print("LOGICAL REPLICATION READINESS CHECK")
    print("=" * 72)

    checks = []

    wal_level = scalar(conn, "SELECT current_setting('wal_level')")
    ok = wal_level == 'logical'
    checks.append(('WAL Level', wal_level, ok, 'ALTER SYSTEM SET wal_level = logical; then restart'))
    print(f"\n  [{'PASS' if ok else 'FAIL'}] WAL level = {wal_level}")

    max_slots = int(scalar(conn, "SELECT current_setting('max_replication_slots')::int"))
    used_slots = int(scalar(conn, "SELECT count(*) FROM pg_replication_slots"))
    avail = max_slots - used_slots
    ok = avail >= 1
    checks.append(('Replication Slots', f'{used_slots}/{max_slots}', ok, 'Increase max_replication_slots'))
    print(f"  [{'PASS' if ok else 'FAIL'}] Replication slots: {used_slots}/{max_slots} ({avail} available)")

    max_senders = int(scalar(conn, "SELECT current_setting('max_wal_senders')::int"))
    active_senders = int(scalar(conn, "SELECT count(*) FROM pg_stat_replication"))
    ok = max_senders - active_senders >= 1
    checks.append(('WAL Senders', f'{active_senders}/{max_senders}', ok, 'Increase max_wal_senders'))
    print(f"  [{'PASS' if ok else 'FAIL'}] WAL senders: {active_senders}/{max_senders}")

    no_pk = query(conn, """
        SELECT n.nspname || '.' || c.relname AS table_name,
               CASE c.relreplident
                   WHEN 'd' THEN 'default' WHEN 'n' THEN 'nothing'
                   WHEN 'f' THEN 'full' WHEN 'i' THEN 'index'
               END AS replica_identity
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
        WHERE c.relkind = 'r'
          AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          AND pk.oid IS NULL AND c.relreplident NOT IN ('f', 'i')
        ORDER BY n.nspname, c.relname
    """)
    ok = len(no_pk) == 0
    checks.append(('Tables with PK/Identity', f'{len(no_pk)} missing', ok, 'Add PK or set REPLICA IDENTITY FULL'))
    print(f"  [{'PASS' if ok else 'FAIL'}] Tables needing PK/identity: {len(no_pk)}")
    if no_pk and args.verbose:
        for t in no_pk:
            print(f"         {t['table_name']}  identity={t['replica_identity']}")

    pubs = query(conn, """
        SELECT pubname, puballtables AS all_tables,
               pubinsert, pubupdate, pubdelete
        FROM pg_publication
    """)
    if pubs:
        print("\n--- Existing Publications ---")
        for p in pubs:
            print(f"  {p['pubname']}  all_tables={p['all_tables']}  INS={p['pubinsert']} UPD={p['pubupdate']} DEL={p['pubdelete']}")

    all_pass = all(c[2] for c in checks)
    print(f"\n{'='*72}")
    print(f"RESULT: {'READY' if all_pass else 'NOT READY'}")
    if not all_pass:
        print("Actions needed:")
        for name, val, ok, fix in checks:
            if not ok:
                print(f"  - {name}: {fix}")
    print(f"{'='*72}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description='Migration helpers for PostGIS, pgvector, and replication blockers')
    sub = parser.add_subparsers(dest='command')

    p_postgis = sub.add_parser('postgis', help='PostGIS spatial data assessment')
    add_source_args(p_postgis)
    p_postgis.add_argument('--output', '-o', help='Write JSON data to file')

    p_vector = sub.add_parser('vector-indexes', help='pgvector index assessment')
    add_source_args(p_vector)
    p_vector.add_argument('--output', '-o', help='Write JSON data to file')

    p_blockers = sub.add_parser('blockers', help='Detect logical replication blockers')
    add_source_args(p_blockers)
    p_blockers.add_argument('--schemas', help='Comma-separated list of schemas to check')
    p_blockers.add_argument('--output', '-o', help='Write JSON data to file')

    p_rep = sub.add_parser('replication-check', help='Quick replication readiness check')
    add_source_args(p_rep)
    p_rep.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        'postgis': cmd_postgis,
        'vector-indexes': cmd_vector_indexes,
        'blockers': cmd_blockers,
        'replication-check': cmd_replication_check,
    }
    commands[args.command](args)


if __name__ == '__main__':
    main()
