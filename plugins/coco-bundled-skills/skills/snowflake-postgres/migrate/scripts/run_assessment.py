#!/usr/bin/env python3
"""
run_assessment.py
Comprehensive PostgreSQL migration assessment for Snowflake Postgres.

Replaces the need for psql + multiple SQL scripts + shell report generator.
Handles PG version differences (e.g., PG17 column name changes).

Usage:
    python run_assessment.py --host <host> --dbname <db> --user <user>
    python run_assessment.py --host <host> --dbname <db> --user <user> --html report.html
    python run_assessment.py --host <host> --dbname <db> --user <user> --json data.json --html report.html

Environment variables:
    PGPASSWORD          - Password for authentication
    SOURCE_PGHOST       - Alternative to --host
    SOURCE_PGDATABASE   - Alternative to --dbname
    SOURCE_PGUSER       - Alternative to --user
    SOURCE_PGPORT       - Alternative to --port
"""

import argparse
import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path as _P

# Resolve pg_common from the shared generic-PG layer at snowflake-postgres/scripts/shared/.
# pytest handles this via pythonpath; for direct invocation we add it to sys.path here.
# Standalone driver detection below is intentionally preserved for contract fidelity
# (the upstream run_assessment is historically self-contained); pg_common is imported
# only for the credential-safety helpers (--source-service flag + ~/.pgpass resolution).
_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from pg_common import (  # noqa: E402
    add_source_args, resolve_source_password, _apply_source_service,
    SUPPORTED_EXTENSIONS, SUPPORTED_LANGUAGES,
)

try:
    import psycopg2
    import psycopg2.extras
    DB_DRIVER = 'psycopg2'
except ImportError:
    psycopg2 = None
    try:
        import pg8000
        DB_DRIVER = 'pg8000'
    except ImportError:
        pg8000 = None
        DB_DRIVER = None


def connect(host, port, dbname, user, password, sslmode=None, sslrootcert=None, hostaddr=None):
    """Local driver-agnostic connect mirroring pg_common.connect().

    Kept self-contained (upstream contract for run_assessment); see pg_common
    for the canonical implementation. sslrootcert is honored on both drivers:
    psycopg2 takes the path directly; pg8000 loads it into an SSLContext.
    For sslmode=verify-ca on pg8000 we disable hostname checking to match
    libpq semantics (chain verification only). hostaddr is forwarded only on
    the psycopg2/libpq path; pg8000 does not expose an equivalent parameter.
    """
    connect_kwargs = dict(host=host, port=port, database=dbname, user=user, password=password)
    if hostaddr and DB_DRIVER == 'psycopg2':
        connect_kwargs['hostaddr'] = hostaddr
    if sslmode:
        connect_kwargs['sslmode'] = sslmode
    if sslrootcert and DB_DRIVER == 'psycopg2':
        connect_kwargs['sslrootcert'] = sslrootcert

    if DB_DRIVER == 'psycopg2':
        return psycopg2.connect(**connect_kwargs)
    elif DB_DRIVER == 'pg8000':
        kw = dict(host=host, port=port, database=dbname, user=user, password=password)
        if sslmode and sslmode != 'disable':
            import ssl
            ctx = ssl.create_default_context(cafile=sslrootcert) if sslrootcert else ssl.create_default_context()
            if sslmode == 'verify-ca':
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_REQUIRED
            kw['ssl_context'] = ctx
        return pg8000.connect(**kw)
    else:
        print("ERROR: No PostgreSQL driver found.", file=sys.stderr)
        print("Install one of:", file=sys.stderr)
        print("  pip install psycopg2-binary", file=sys.stderr)
        print("  pip install pg8000", file=sys.stderr)
        sys.exit(1)


def query(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params)
    if cur.description:
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    return []


def scalar(conn, sql, params=None):
    rows = query(conn, sql, params)
    if rows:
        vals = list(rows[0].values())
        return vals[0] if vals else None
    return None


def detect_pg_version(conn):
    ver = scalar(conn, "SELECT current_setting('server_version_num')::int")
    return int(ver) if ver else 0


def detect_platform(conn):
    checks = [
        ("SELECT 1 FROM pg_roles WHERE rolname = 'rds_superuser'",
         "SELECT 1 FROM pg_proc WHERE proname = 'aurora_version'",
         'AWS Aurora PostgreSQL', 'AWS RDS PostgreSQL'),
        ("SELECT 1 FROM pg_roles WHERE rolname = 'azure_pg_admin'",
         None, 'Azure Database for PostgreSQL', None),
        ("SELECT 1 FROM pg_roles WHERE rolname = 'cloudsqlsuperuser'",
         None, 'Google Cloud SQL', None),
        ("SELECT setting FROM pg_settings WHERE name = 'neon.timeline_id'",
         None, 'Neon', None),
        ("SELECT 1 FROM pg_roles WHERE rolname LIKE '%heroku%'",
         None, 'Heroku Postgres', None),
    ]
    for primary_q, secondary_q, primary_name, fallback_name in checks:
        try:
            if scalar(conn, primary_q):
                if secondary_q:
                    if scalar(conn, secondary_q):
                        return primary_name
                    return fallback_name or primary_name
                return primary_name
        except Exception:
            pass
    return 'Self-managed PostgreSQL'


def lo_size_column():
    # pg_largeobject_metadata.oid is the LO identifier on all PG versions
    # we support (12+); older versions used `lo` but those predate the
    # current toolchain. Kept as a function (not inlined) as the hook for
    # re-introducing version-branched logic if a future PG release changes
    # the column again.
    return 'oid'


def collect_report_metadata(conn, pg_version, display_host=None, display_port=None, display_hostaddr=None):
    row = query(conn, """
        SELECT
            to_char(now(), 'YYYY-MM-DD HH24:MI:SS TZ') AS generated_at,
            inet_server_addr()::text AS source_host,
            inet_server_port() AS source_port,
            current_database() AS database,
            current_user AS connected_user,
            version() AS pg_version,
            current_setting('server_version_num')::int AS pg_version_num
    """)
    meta = row[0] if row else {}
    if display_host:
        if display_hostaddr and display_hostaddr != display_host:
            meta['source_host'] = f"{display_host} (via {display_hostaddr})"
        else:
            meta['source_host'] = display_host
    elif display_hostaddr:
        meta['source_host'] = display_hostaddr
    if display_port is not None:
        meta['source_port'] = display_port
    if display_hostaddr:
        meta['source_hostaddr'] = display_hostaddr
    meta['source_platform'] = detect_platform(conn)
    return meta


def collect_database_overview(conn, schema_filter=None):
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        row = query(conn, f"""
            SELECT
                current_database() AS database_name,
                pg_database_size(current_database()) AS size_bytes,
                pg_size_pretty(pg_database_size(current_database())) AS size_pretty,
                (SELECT count(*) FROM pg_stat_user_tables WHERE schemaname IN ({placeholders})) AS table_count,
                (SELECT count(*) FROM pg_stat_user_indexes WHERE schemaname IN ({placeholders})) AS index_count,
                (SELECT coalesce(sum(n_live_tup), 0) FROM pg_stat_user_tables WHERE schemaname IN ({placeholders})) AS total_rows,
                {len(schema_filter)} AS schema_count
        """)
    else:
        row = query(conn, """
            SELECT
                current_database() AS database_name,
                pg_database_size(current_database()) AS size_bytes,
                pg_size_pretty(pg_database_size(current_database())) AS size_pretty,
                (SELECT count(*) FROM pg_stat_user_tables) AS table_count,
                (SELECT count(*) FROM pg_stat_user_indexes) AS index_count,
                (SELECT coalesce(sum(n_live_tup), 0) FROM pg_stat_user_tables) AS total_rows,
                (SELECT count(DISTINCT schemaname) FROM pg_stat_user_tables) AS schema_count
        """)
    return row[0] if row else {}


def collect_replication_readiness(conn):
    row = query(conn, """
        SELECT
            current_setting('wal_level') AS wal_level,
            current_setting('wal_level') = 'logical' AS wal_level_ok,
            current_setting('max_replication_slots')::int AS max_replication_slots,
            (SELECT count(*) FROM pg_replication_slots) AS used_replication_slots,
            current_setting('max_wal_senders')::int AS max_wal_senders,
            (SELECT count(*) FROM pg_stat_replication) AS active_wal_senders
    """)
    return row[0] if row else {}


def collect_extensions(conn):
    rows = query(conn, "SELECT extname, extversion FROM pg_extension WHERE extname != 'plpgsql'")
    results = []
    for r in rows:
        results.append({
            'name': r['extname'],
            'version': r['extversion'],
            'supported': r['extname'].lower() in SUPPORTED_EXTENSIONS
        })
    return results


def collect_unsupported_extensions(conn):
    rows = query(conn, "SELECT extname, extversion FROM pg_extension WHERE extname != 'plpgsql'")
    return [{'name': r['extname'], 'version': r['extversion']}
            for r in rows if r['extname'].lower() not in SUPPORTED_EXTENSIONS]


def collect_unsupported_languages(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT l.lanname AS language, count(*) AS function_count
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
        AND l.lanname NOT IN ('sql', 'plpgsql', 'c', 'internal')
        {extra}
        GROUP BY l.lanname
    """)
    return [{'language': r['language'], 'function_count': int(r['function_count'])} for r in rows]


def collect_blockers(conn, pg_version, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    no_pk = query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS table,
               pg_total_relation_size(c.oid) AS size_bytes,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty,
               coalesce(s.n_live_tup, 0) AS row_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
        LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
        WHERE c.relkind = 'r'
        AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        AND pk.oid IS NULL
        {extra}
    """)

    col = lo_size_column()
    # Two failure modes are surfaced separately: pg_lo_size unavailable
    # (managed-PG variants where lo_*() functions are blocked) versus
    # pg_largeobject_metadata unreadable (permissions). Anything else
    # bubbles up so a flaky connection doesn't silently report 0 LOs.
    lo = {'count': 0, 'total_size_bytes': 0, 'error': None}
    try:
        lo_row = query(conn, f"""
            SELECT count(*) AS count,
                   coalesce(sum(pg_lo_size({col})), 0) AS total_size_bytes
            FROM pg_largeobject_metadata
        """)
        if lo_row:
            lo = {'count': int(lo_row[0]['count']), 'total_size_bytes': int(lo_row[0]['total_size_bytes']), 'error': None}
    except Exception as e:
        msg = str(e).lower()
        if 'pg_lo_size' in msg or 'function' in msg:
            try:
                lo_row = query(conn, "SELECT count(*) AS count, 0 AS total_size_bytes FROM pg_largeobject_metadata")
                if lo_row:
                    lo = {'count': int(lo_row[0]['count']), 'total_size_bytes': 0,
                          'error': 'pg_lo_size unavailable; size unknown'}
            except Exception as inner:
                lo['error'] = f'large-object check failed: {inner}'
                print(f"  [WARNING] large-objects check failed: {inner}")
        else:
            lo['error'] = f'large-object check failed: {e}'
            print(f"  [WARNING] large-objects check failed: {e}")

    return {
        'tables_without_pk': [dict(r) for r in no_pk],
        'large_objects': lo,
        'tables_without_pk_count': len(no_pk)
    }


def collect_sequences(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    try:
        rows = query(conn, f"""
            SELECT n.nspname AS schema, c.relname AS name,
                   pg_sequence_last_value(c.oid) AS last_value
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'S'
            AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            {extra}
        """)
        return [dict(r) for r in rows]
    except Exception as e:
        # Detect permission errors via SQLSTATE first (locale-independent),
        # then fall back to substring match for drivers that don't expose pgcode.
        sqlstate = getattr(e, 'pgcode', None) or getattr(getattr(e, 'orig', None), 'pgcode', None)
        is_permission_error = sqlstate == '42501'
        if not is_permission_error:
            err_str = str(e).lower()
            is_permission_error = 'permission denied' in err_str or 'insufficient_privilege' in err_str
        if is_permission_error:
            count_rows = query(conn, f"""
                SELECT n.nspname AS schema, c.relname AS name
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relkind = 'S'
                AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                {extra}
            """)
            count = len(count_rows)
            print(f"  [WARNING] sequence access denied — {count} sequences could not be inspected (insufficient privileges for pg_sequence_last_value)")
            return [dict(r, last_value=None) for r in count_rows]
        raise


def collect_materialized_views(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS name,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'm'
        {extra}
    """)
    return [dict(r) for r in rows]


def collect_foreign_tables(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" WHERE foreign_table_schema IN ({placeholders})"
    rows = query(conn, f"""
        SELECT foreign_table_schema AS schema,
               foreign_table_name AS name,
               foreign_server_name
        FROM information_schema.foreign_tables
        {extra}
    """)
    return [dict(r) for r in rows]


def collect_partitioned_tables(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS name,
               pg_get_partkeydef(c.oid) AS partition_key,
               (SELECT count(*) FROM pg_inherits WHERE inhparent = c.oid) AS partition_count
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'p'
        {extra}
    """)
    return [dict(r) for r in rows]


def collect_inherited_tables(conn, schema_filter=None):
    # relkind IN ('r', 'p') captures both classic INHERITS parents and
    # partitioned-table parents — generate_hybrid_plan branches on both,
    # so the assessment must surface both flavours.
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND pn.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT pn.nspname AS parent_schema, pc.relname AS parent_table,
               cn.nspname AS child_schema, cc.relname AS child_table,
               pc.relkind AS parent_kind
        FROM pg_inherits i
        JOIN pg_class pc ON i.inhparent = pc.oid
        JOIN pg_class cc ON i.inhrelid = cc.oid
        JOIN pg_namespace pn ON pc.relnamespace = pn.oid
        JOIN pg_namespace cn ON cc.relnamespace = cn.oid
        WHERE pc.relkind IN ('r', 'p')
        {extra}
    """)
    return [dict(r) for r in rows]


def collect_custom_types(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT n.nspname AS schema, t.typname AS name,
               CASE t.typtype
                   WHEN 'e' THEN 'enum'
                   WHEN 'c' THEN 'composite'
                   WHEN 'd' THEN 'domain'
                   WHEN 'r' THEN 'range'
               END AS type_kind
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typtype IN ('c', 'e', 'd', 'r')
        AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        {extra}
    """)
    return [dict(r) for r in rows]


def collect_functions_by_language(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT l.lanname AS language, count(*) AS count
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
        {extra}
        GROUP BY l.lanname
    """)
    return [{'language': r['language'], 'count': int(r['count'])} for r in rows]


def collect_triggers(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS table,
               t.tgname AS trigger_name,
               CASE t.tgenabled
                   WHEN 'O' THEN 'origin'
                   WHEN 'D' THEN 'disabled'
                   WHEN 'R' THEN 'replica'
                   WHEN 'A' THEN 'always'
               END AS enabled
        FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE NOT t.tgisinternal
        AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        {extra}
    """)
    return [dict(r) for r in rows]


def collect_postgis_info(conn):
    has_postgis = scalar(conn, "SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
    if not has_postgis:
        return {'installed': False}
    try:
        version = scalar(conn, "SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
        geom_count = scalar(conn, "SELECT count(*) FROM geometry_columns") or 0
        geog_count = scalar(conn, "SELECT count(*) FROM geography_columns") or 0
        custom_srids = scalar(conn, "SELECT count(*) FROM spatial_ref_sys WHERE srid > 900000") or 0
        return {
            'installed': True,
            'version': version,
            'geometry_columns': int(geom_count),
            'geography_columns': int(geog_count),
            'custom_srids': int(custom_srids)
        }
    except Exception as e:
        # Surface the partial-read state instead of returning a clean-looking
        # zero counts dict that masks an underlying error.
        print(f"  [WARNING] PostGIS detail query failed: {e}")
        return {'installed': True, 'version': 'unknown', 'geometry_columns': 0,
                'geography_columns': 0, 'custom_srids': 0,
                'error': str(e)}


def collect_tables(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" WHERE schemaname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT schemaname AS schema, relname AS name,
               n_live_tup AS row_count, n_dead_tup AS dead_tuples,
               pg_total_relation_size(relid) AS size_bytes,
               pg_size_pretty(pg_total_relation_size(relid)) AS size_pretty,
               last_vacuum, last_autovacuum, last_analyze
        FROM pg_stat_user_tables
        {extra}
        ORDER BY n_live_tup DESC
    """)
    result = []
    for r in rows:
        d = dict(r)
        for k in ('last_vacuum', 'last_autovacuum', 'last_analyze'):
            if d.get(k) is not None:
                d[k] = str(d[k])
        result.append(d)
    return result


def collect_indexes(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" WHERE schemaname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT schemaname AS schema, relname, indexrelname AS index,
               idx_scan AS scans, idx_tup_read AS tuples_read,
               idx_tup_fetch AS tuples_fetched,
               pg_size_pretty(pg_relation_size(indexrelid)) AS size_pretty
        FROM pg_stat_user_indexes
        {extra}
        ORDER BY idx_scan DESC
        LIMIT 100
    """)
    return [dict(r) for r in rows]


def collect_roles(conn):
    rows = query(conn, """
        SELECT rolname AS name, rolcanlogin AS can_login,
               rolsuper AS superuser, rolcreatedb AS create_db,
               rolcreaterole AS create_role, rolreplication AS replication
        FROM pg_roles
        WHERE rolname NOT LIKE 'pg_%%'
        AND rolname NOT IN ('postgres')
    """)
    return [dict(r) for r in rows]


def collect_database_settings(conn):
    rows = query(conn, """
        SELECT name, setting, unit, source
        FROM pg_settings
        WHERE source NOT IN ('default', 'override')
        AND setting IS DISTINCT FROM boot_val
    """)
    return [dict(r) for r in rows]


def collect_unlogged_tables(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS name,
               pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty,
               pg_total_relation_size(c.oid) AS size_bytes
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relpersistence = 'u' AND c.relkind = 'r'
        AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        {extra}
    """)
    return [dict(r) for r in rows]


def collect_postgres_owned_objects(conn, schema_filter=None):
    extra = ''
    if schema_filter:
        placeholders = ','.join(f"'{s}'" for s in schema_filter)
        extra = f" AND n.nspname IN ({placeholders})"
    rows = query(conn, f"""
        SELECT n.nspname AS schema, c.relname AS name,
               CASE c.relkind
                   WHEN 'r' THEN 'table'
                   WHEN 'v' THEN 'view'
                   WHEN 'm' THEN 'materialized view'
                   WHEN 'S' THEN 'sequence'
                   WHEN 'i' THEN 'index'
               END AS object_type
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_roles r ON r.oid = c.relowner
        WHERE r.rolname = 'postgres'
        AND c.relkind IN ('r', 'v', 'm', 'S')
        AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        {extra}
    """)
    return [dict(r) for r in rows]


def calculate_complexity_score(data):
    score = 0
    score += data['blockers']['tables_without_pk_count'] * 5
    score += len(data.get('unlogged_tables', [])) * 10
    score += len(data.get('inherited_tables', [])) * 4
    if data['blockers']['large_objects']['count'] > 0:
        score += 15
    score += len(data.get('unsupported_extensions', [])) * 10
    score += sum(l['function_count'] for l in data.get('unsupported_languages', [])) * 5
    score += len(data.get('partitioned_tables', [])) * 2
    score += len(data.get('custom_types', [])) * 2
    score += len(data.get('materialized_views', [])) * 2
    score += len(data.get('foreign_tables', [])) * 3
    score += len(data.get('triggers', [])) * 2

    # +5 for every full 100 GB of source data (107374182400 = 100 * 1024^3).
    db_size = data.get('database_overview', {}).get('size_bytes', 0) or 0
    score += int(db_size / 107374182400) * 5

    return score


def calculate_instance_recommendations(data):
    """Calculate Snowflake Postgres instance sizing recommendations based on source DB.

    Returns a dict with compute_pool, storage, and high_availability
    recommendations, each with rationale and alternatives where applicable.
    """
    db_size_bytes = data.get('database_overview', {}).get('size_bytes', 0) or 0
    db_size_gb = db_size_bytes / (1024 ** 3)
    table_count = data.get('database_overview', {}).get('table_count', 0) or 0
    complexity = data.get('complexity_score', 0)
    postgis = data.get('postgis_info', {})
    has_postgis = postgis.get('installed', False)
    geometry_cols = postgis.get('geometry_columns', 0) or 0

    # Check for pgvector (vector similarity search)
    extensions = data.get('extensions', [])
    has_pgvector = any(e.get('name', '').lower() == 'vector' for e in extensions)

    # Compute family selection uses only valid Snowflake Postgres families.
    # These are intentionally conservative heuristics and must stay aligned
    # with snowflake-postgres/references/instance-options.md.
    if db_size_gb < 10:
        base_pool = 'STANDARD_L'
        base_rationale = (
            f'Source database is small ({db_size_gb:.1f} GB); '
            'STANDARD_L is a conservative general-purpose starting point'
        )
    elif db_size_gb < 50:
        base_pool = 'STANDARD_XL'
        base_rationale = (
            f'Source database ({db_size_gb:.1f} GB) should fit comfortably '
            'within the 16 GB memory profile of STANDARD_XL'
        )
    elif db_size_gb < 200:
        base_pool = 'STANDARD_2XL'
        base_rationale = (
            f'Source database ({db_size_gb:.1f} GB) benefits from the 32 GB '
            'memory profile of STANDARD_2XL for migration headroom'
        )
    elif db_size_gb < 1000:
        base_pool = 'STANDARD_4XL'
        base_rationale = (
            f'Large database ({db_size_gb:.1f} GB) benefits from the 64 GB '
            'memory profile of STANDARD_4XL for parallel queries and sync'
        )
    else:
        base_pool = 'STANDARD_8XL'
        base_rationale = (
            f'Very large database ({db_size_gb:.1f} GB) likely needs at least '
            'the 128 GB memory profile of STANDARD_8XL; consider HIGHMEM for '
            'memory-intensive workloads'
        )

    # Adjust for complexity.
    pool_order = ['STANDARD_L', 'STANDARD_XL', 'STANDARD_2XL', 'STANDARD_4XL', 'STANDARD_8XL']
    recommended_pool = base_pool
    adjustments = []

    if complexity > 200:
        idx = pool_order.index(base_pool)
        if idx < len(pool_order) - 1:
            recommended_pool = pool_order[idx + 1]
            adjustments.append(f'complexity score ({complexity}) suggests one tier up')

    if has_postgis and geometry_cols > 10:
        idx = pool_order.index(recommended_pool)
        if idx < len(pool_order) - 1:
            recommended_pool = pool_order[idx + 1]
        adjustments.append(f'PostGIS with {geometry_cols} geometry columns is memory-intensive')

    if has_pgvector:
        if recommended_pool in ('STANDARD_L', 'STANDARD_XL'):
            recommended_pool = 'STANDARD_2XL'
        adjustments.append('pgvector index operations benefit from more memory')

    if table_count > 500:
        adjustments.append(f'{table_count} tables increases metadata overhead')

    # Build rationale
    rationale = base_rationale
    if adjustments:
        rationale += '. Adjusted: ' + '; '.join(adjustments)

    # Generate alternatives
    idx = pool_order.index(recommended_pool)
    alternatives = []

    if idx > 0:
        smaller = pool_order[idx - 1]
        alternatives.append({
            'pool': smaller,
            'tier': 'cost-optimized',
            'pros': ['Lower hourly cost', 'May be sufficient for light workloads'],
            'cons': ['Less headroom for growth', 'May throttle under heavy load', 'Longer migration time']
        })

    if idx < len(pool_order) - 1:
        larger = pool_order[idx + 1]
        alternatives.append({
            'pool': larger,
            'tier': 'performance-optimized',
            'pros': ['More headroom for growth', 'Faster parallel queries', 'Better migration performance'],
            'cons': ['Higher hourly cost', 'May be oversized for current workload']
        })

    # Storage calculation: source × multiplier + buffer
    if db_size_gb < 100:
        multiplier = 1.5
    elif db_size_gb < 500:
        multiplier = 1.3
    else:
        multiplier = 1.2

    buffer_gb = 20
    calculated_storage = db_size_gb * multiplier + buffer_gb
    # Round up to nearest 10 GB, minimum 20 GB (Snowflake minimum is 10)
    recommended_storage = max(20, int((calculated_storage + 9) // 10 * 10))
    minimum_storage = max(20, int(db_size_gb * 1.1))

    storage_calc = f'{db_size_gb:.1f} GB source × {multiplier} multiplier + {buffer_gb} GB buffer = {calculated_storage:.1f} GB → {recommended_storage} GB'

    # High availability is driven by user intent, not source SQL alone.
    migration_context = data.get('migration_context', {}) or {}
    target_role = (migration_context.get('target_role') or data.get('target_role') or '').strip().lower()
    target_is_production = target_role in {'prod', 'production', 'primary', 'future_production'}

    source_signals = []
    if db_size_gb > 500:
        source_signals.append(f'large database ({db_size_gb:.1f} GB)')
    if complexity > 200:
        source_signals.append(f'high complexity score ({complexity})')
    if has_postgis:
        source_signals.append('PostGIS workload')
    if has_pgvector:
        source_signals.append('pgvector workload')

    ha_recommended = False
    if target_is_production:
        ha_recommended = True
        if source_signals:
            ha_rationale = (
                'This target is intended for production. Source signals ('
                + '; '.join(source_signals)
                + ') support enabling HA after validation and before cutover'
            )
        else:
            ha_rationale = (
                'This target is intended for production; enable HA after '
                'validation and before cutover'
            )
        ha_timing = 'after validation, before cutover'
    else:
        if source_signals:
            ha_rationale = (
                'Keep the migration target single-instance for now. Source '
                'signals ('
                + '; '.join(source_signals)
                + ') suggest HA may be appropriate if this target will become '
                'production; confirm intent before enabling it after validation '
                'and before cutover'
            )
        else:
            ha_rationale = (
                'Single-instance is suitable during migration. If this target '
                'will become the production system, confirm that intent before '
                'enabling HA after validation and before cutover'
            )
        ha_timing = 'after validation, before cutover if target is production'

    return {
        'compute_pool': {
            'recommended': recommended_pool,
            'alternatives': alternatives,
            'rationale': rationale
        },
        'storage': {
            'recommended_gb': recommended_storage,
            'minimum_gb': minimum_storage,
            'calculation': storage_calc
        },
        'high_availability': {
            'recommended': ha_recommended,
            'rationale': ha_rationale,
            'timing': ha_timing,
        },
        'source_metrics': {
            'size_gb': round(db_size_gb, 2),
            'table_count': table_count,
            'complexity_score': complexity,
            'has_postgis': has_postgis,
            'has_pgvector': has_pgvector
        }
    }


def run_assessment(host, port, dbname, user, password, sslmode=None, schemas=None,
                   sslrootcert=None, hostaddr=None):
    print(f"Connecting to {host}:{port}/{dbname} as {user}...")
    conn = connect(host, port, dbname, user, password, sslmode,
                   sslrootcert=sslrootcert, hostaddr=hostaddr)
    conn.autocommit = True

    schema_filter = None
    if schemas:
        schema_list = [s.strip() for s in schemas.split(',')]
        schema_filter = tuple(schema_list)
        print(f"Schema scope: {', '.join(schema_list)}")

    pg_version = detect_pg_version(conn)
    print(f"PostgreSQL version: {pg_version}")

    print("Collecting report metadata...")
    report_metadata = collect_report_metadata(
        conn,
        pg_version,
        display_host=host,
        display_port=port,
        display_hostaddr=hostaddr,
    )

    print("Collecting database overview...")
    database_overview = collect_database_overview(conn, schema_filter)

    print("Checking replication readiness...")
    replication_readiness = collect_replication_readiness(conn)

    print("Checking extensions...")
    extensions = collect_extensions(conn)
    unsupported_extensions = collect_unsupported_extensions(conn)

    print("Checking function languages...")
    unsupported_languages = collect_unsupported_languages(conn, schema_filter)
    functions_by_language = collect_functions_by_language(conn, schema_filter)

    print("Detecting blockers...")
    blockers = collect_blockers(conn, pg_version, schema_filter)

    print("Collecting sequences...")
    sequences = collect_sequences(conn, schema_filter)

    print("Collecting materialized views...")
    materialized_views = collect_materialized_views(conn, schema_filter)

    print("Collecting foreign tables...")
    foreign_tables = collect_foreign_tables(conn, schema_filter)

    print("Collecting partitioned tables...")
    partitioned_tables = collect_partitioned_tables(conn, schema_filter)

    print("Detecting table inheritance...")
    inherited_tables = collect_inherited_tables(conn, schema_filter)

    print("Collecting custom types...")
    custom_types = collect_custom_types(conn, schema_filter)

    print("Collecting triggers...")
    triggers = collect_triggers(conn, schema_filter)

    print("Checking PostGIS...")
    postgis_info = collect_postgis_info(conn)

    print("Collecting table details...")
    tables = collect_tables(conn, schema_filter)

    print("Collecting index details...")
    indexes = collect_indexes(conn, schema_filter)

    print("Collecting roles...")
    roles = collect_roles(conn)

    print("Collecting database settings...")
    database_settings = collect_database_settings(conn)

    print("Detecting unlogged tables...")
    unlogged_tables = collect_unlogged_tables(conn, schema_filter)

    print("Checking postgres-owned objects...")
    postgres_owned = collect_postgres_owned_objects(conn, schema_filter)

    conn.close()

    data = {
        'report_metadata': report_metadata,
        'database_overview': database_overview,
        'replication_readiness': replication_readiness,
        'extensions': extensions,
        'unsupported_extensions': unsupported_extensions,
        'unsupported_languages': unsupported_languages,
        'blockers': blockers,
        'sequences': sequences,
        'materialized_views': materialized_views,
        'foreign_tables': foreign_tables,
        'partitioned_tables': partitioned_tables,
        'inherited_tables': inherited_tables,
        'custom_types': custom_types,
        'functions_by_language': functions_by_language,
        'triggers': triggers,
        'postgis_info': postgis_info,
        'tables': tables,
        'indexes': indexes,
        'roles': roles,
        'database_settings': database_settings,
        'unlogged_tables': unlogged_tables,
        'postgres_owned': postgres_owned
    }

    data['complexity_score'] = calculate_complexity_score(data)
    data['instance_recommendations'] = calculate_instance_recommendations(data)
    if schema_filter:
        data['schemas_scope'] = list(schema_filter)

    return data


def generate_html_report(data, output_path):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_sh = os.path.join(script_dir, '..', 'sql', 'generate_assessment_report.sh')

    html_header = _get_html_header()
    html_script = _get_html_script()

    json_str = json.dumps(data, default=str)

    html = html_header
    html += f"const reportData = {json_str};\n"
    html += html_script

    with open(output_path, 'w') as f:
        f.write(html)

    print(f"HTML report generated: {output_path}")


PROVIDER_MANAGED_SUPERUSER_ROLE_NAMES = {
    'postgres',
    'crunchy_superuser',
    'rds_superuser',
    'cloudsqlsuperuser',
    'cloudsqladmin',
    'azure_pg_admin',
    'azure_superuser',
    'supabase_admin',
    'avnadmin',
}


def _provider_managed_superuser_roles(data):
    return [
        r for r in data.get('roles', [])
        if r.get('superuser') and r.get('name', '').lower() in PROVIDER_MANAGED_SUPERUSER_ROLE_NAMES
    ]


def _customer_superuser_roles(data):
    return [
        r for r in data.get('roles', [])
        if r.get('superuser') and r.get('name', '').lower() not in PROVIDER_MANAGED_SUPERUSER_ROLE_NAMES
    ]


def _needs_hybrid_investigation(data):
    blockers = data.get('blockers', {})
    return (
        blockers.get('tables_without_pk_count', 0) > 0
        or len(data.get('unlogged_tables', [])) > 0
        or len(data.get('inherited_tables', [])) > 0
    )


def _get_html_header():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PostgreSQL Migration Assessment Report</title>
    <style>
        :root {
            --primary-color: #29B5E8;
            --secondary-color: #11567F;
            --success-color: #10B981;
            --warning-color: #F59E0B;
            --danger-color: #EF4444;
            --bg-color: #F8FAFC;
            --card-bg: #FFFFFF;
            --text-color: #1E293B;
            --text-muted: #64748B;
            --border-color: #E2E8F0;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background-color: var(--bg-color); color: var(--text-color); line-height: 1.6;
        }
        .header {
            background: linear-gradient(135deg, var(--secondary-color) 0%, var(--primary-color) 100%);
            color: white; padding: 2rem; text-align: center;
        }
        .header h1 { font-size: 2rem; margin-bottom: 0.5rem; }
        .header p { opacity: 0.9; font-size: 0.95rem; }
        .container { max-width: 1400px; margin: 0 auto; padding: 2rem; }
        .summary-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem; margin-bottom: 2rem;
        }
        .summary-card {
            background: var(--card-bg); border-radius: 12px; padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center;
        }
        .summary-card .value { font-size: 2rem; font-weight: 700; color: var(--primary-color); }
        .summary-card .label { color: var(--text-muted); font-size: 0.875rem; margin-top: 0.25rem; }
        .section {
            background: var(--card-bg); border-radius: 12px; padding: 1.5rem;
            margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .section h2 {
            font-size: 1.25rem; margin-bottom: 1rem; padding-bottom: 0.75rem;
            border-bottom: 2px solid var(--border-color); display: flex; align-items: center; gap: 0.5rem;
        }
        .section h3 { font-size: 1rem; margin: 1.5rem 0 0.75rem 0; color: var(--text-muted); }
        .badge {
            display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px;
            font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
        }
        .badge-success { background: #D1FAE5; color: #065F46; }
        .badge-warning { background: #FEF3C7; color: #92400E; }
        .badge-danger { background: #FEE2E2; color: #991B1B; }
        .badge-info { background: #DBEAFE; color: #1E40AF; }
        .status-indicator {
            width: 12px; height: 12px; border-radius: 50%; display: inline-block; margin-right: 0.5rem;
        }
        .status-ok { background: var(--success-color); }
        .status-warning { background: var(--warning-color); }
        .status-error { background: var(--danger-color); }
        table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--border-color); }
        th {
            background: var(--bg-color); font-weight: 600; color: var(--text-muted);
            font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em;
        }
        tr:hover { background: var(--bg-color); }
        .readiness-box {
            display: flex; align-items: center; gap: 1rem; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;
        }
        .readiness-go { background: #D1FAE5; border: 1px solid #10B981; }
        .readiness-conditional { background: #FEF3C7; border: 1px solid #F59E0B; }
        .readiness-nogo { background: #FEE2E2; border: 1px solid #EF4444; }
        .readiness-box .icon { font-size: 2rem; }
        .readiness-box .text { flex: 1; }
        .readiness-box .title { font-weight: 600; font-size: 1.1rem; }
        .readiness-box .desc { color: var(--text-muted); font-size: 0.875rem; }
        .info-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 1rem; }
        .info-item { display: flex; justify-content: space-between; padding: 0.5rem 0; border-bottom: 1px solid var(--border-color); }
        .info-item .label { color: var(--text-muted); }
        .info-item .value { font-weight: 500; }
        .collapsible { cursor: pointer; user-select: none; }
        .collapsible::after { content: ' \\25BC'; font-size: 0.75rem; color: var(--text-muted); }
        .collapsible.collapsed::after { content: ' \\25B6'; }
        .collapsible-content { display: block; }
        .collapsible-content.hidden { display: none; }
        .extension-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.5rem; }
        .extension-item {
            display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem;
            background: var(--bg-color); border-radius: 6px; font-size: 0.875rem;
        }
        .method-card { border: 2px solid var(--border-color); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
        .method-card.recommended { border-color: var(--success-color); background: #F0FDF4; }
        .method-card h4 { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem; }
        .method-card ul { margin-left: 1.5rem; color: var(--text-muted); font-size: 0.875rem; }
        .footer { text-align: center; padding: 2rem; color: var(--text-muted); font-size: 0.875rem; }
        @media (max-width: 768px) { .container { padding: 1rem; } .summary-grid { grid-template-columns: repeat(2, 1fr); } }
        @media print { .collapsible-content { display: block !important; } .section { break-inside: avoid; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>PostgreSQL Migration Assessment Report</h1>
        <p>Migration to Snowflake Postgres</p>
    </div>
    <div class="container">
        <div id="report-content">
            <p style="text-align: center; padding: 2rem;">Loading report data...</p>
        </div>
    </div>
    <div class="footer">
        <p>Generated by Cortex Code - PostgreSQL to Snowflake Postgres Migration Skill</p>
    </div>
    <script>
"""


def _get_html_script():
    return """
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString();
}
function isProviderManagedSuperuserRole(roleName) {
    return [
        'postgres',
        'crunchy_superuser',
        'rds_superuser',
        'cloudsqlsuperuser',
        'cloudsqladmin',
        'azure_pg_admin',
        'azure_superuser',
        'supabase_admin',
        'avnadmin'
    ].includes((roleName || '').toLowerCase());
}
function getProviderManagedSuperuserRoles(data) {
    return (data.roles || []).filter(r => r.superuser && isProviderManagedSuperuserRole(r.name));
}
function getCustomerSuperuserRoles(data) {
    return (data.roles || []).filter(r => r.superuser && !isProviderManagedSuperuserRole(r.name));
}
function needsHybridInvestigation(data) {
    const blockers = data.blockers || {};
    return (blockers.tables_without_pk_count || 0) > 0
        || (data.unlogged_tables || []).length > 0
        || (data.inherited_tables || []).length > 0;
}
function hybridInvestigationGuidance(data) {
    if ((data.inherited_tables || []).length > 0) {
        return 'Do not approve hybrid from summary counts alone. Table inheritance needs follow-up investigation first: review the actual inheritance trees and any parent/child query or insert-routing behavior. After that, run migrate/scripts/generate_hybrid_plan.py to classify actual non-replicable objects and confirm whether redesign or remediation decisions remove the need for hybrid.';
    }
    return 'Do not approve hybrid from summary counts alone. The next workflow step is to run migrate/scripts/generate_hybrid_plan.py to classify actual non-replicable objects and confirm whether remediation decisions (for example adding primary keys) remove the need for hybrid.';
}
function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(2) + ' ' + sizes[i];
}
function getReadinessStatus(data) {
    const blockers = data.blockers;
    const replication = data.replication_readiness;
    const superuserRoleCount = getCustomerSuperuserRoles(data).length;
    const postgresOwnedCount = (data.postgres_owned || []).length;
    let criticalCount = 0, warningCount = 0;
    if (blockers.tables_without_pk_count > 0) criticalCount++;
    if (!replication.wal_level_ok) criticalCount++;
    if (data.unsupported_extensions && data.unsupported_extensions.length > 0) criticalCount++;
    if (data.unsupported_languages && data.unsupported_languages.length > 0) criticalCount++;
    if (data.inherited_tables && data.inherited_tables.length > 0) criticalCount++;
    if (blockers.large_objects.count > 0) warningCount++;
    if (data.unlogged_tables && data.unlogged_tables.length > 0) warningCount++;
    if (superuserRoleCount > 0) warningCount++;
    if (postgresOwnedCount > 0) warningCount++;
    if (criticalCount > 0) return { status: 'nogo', label: 'Action Required', desc: criticalCount + ' critical issue(s) must be resolved or reviewed before migration' };
    if (warningCount > 0) return { status: 'conditional', label: 'Conditional', desc: warningCount + ' item(s) require manual handling' };
    return { status: 'go', label: 'Ready', desc: 'No blocking issues detected. Ready for migration.' };
}
function getSuperuserRoles(data) {
    return getCustomerSuperuserRoles(data);
}
function getBlockerSummaryRows(data) {
    const blockers = data.blockers || {};
    const superuserRoles = getSuperuserRoles(data);
    const providerManagedRoles = getProviderManagedSuperuserRoles(data);
    const superuserNames = superuserRoles.map(r => r.name).join(', ');
    const providerManagedNames = providerManagedRoles.map(r => r.name).join(', ');
    return [
        {
            issue: 'Tables w/o PK',
            count: blockers.tables_without_pk_count || 0,
            notes: (blockers.tables_without_pk_count || 0) > 0
                ? 'Logical replication needs row identity. Add primary keys, use REPLICA IDENTITY FULL only as a last resort, or move these tables to pg_dump/hybrid.'
                : 'No blocker detected.'
        },
        {
            issue: 'Unsupported extensions',
            count: (data.unsupported_extensions || []).length,
            notes: (data.unsupported_extensions || []).length > 0
                ? 'These extensions are not available in Snowflake Postgres. Remove or replace the dependency before migration.'
                : 'No blocker detected.'
        },
        {
            issue: 'Unsupported languages',
            count: (data.unsupported_languages || []).length,
            notes: (data.unsupported_languages || []).length > 0
                ? 'Functions in unsupported procedural languages must be rewritten in plpgsql/SQL or moved into the application layer.'
                : 'No blocker detected.'
        },
        {
            issue: 'Unlogged tables',
            count: (data.unlogged_tables || []).length,
            notes: (data.unlogged_tables || []).length > 0
                ? 'Unlogged tables do not write to WAL, so logical replication will miss their changes. Convert them to LOGGED or keep them on the pg_dump/manual branch.'
                : 'No blocker detected.'
        },
        {
            issue: 'Table inheritance',
            count: (data.inherited_tables || []).length,
            notes: (data.inherited_tables || []).length > 0
                ? 'PostgreSQL inheritance is different from partitioning and needs follow-up investigation before method selection. Review the actual inheritance trees and application behavior, then decide whether redesign or pg_dump/manual handling is required.'
                : 'No blocker detected.'
        },
        {
            issue: 'SUPERUSER roles',
            count: superuserRoles.length,
            notes: superuserRoles.length > 0
                ? 'Snowflake Postgres has no SUPERUSER. Source roles (' + superuserNames + ') will be created without it. Use snowflake_admin for target administration, but it is not a drop-in replacement for each source superuser; map each role to specific grants.'
                : providerManagedRoles.length > 0
                    ? 'Known provider-managed admin role(s) detected (' + providerManagedNames + ') and not treated as customer blockers. Any other SUPERUSER roles still require review.'
                    : 'No source SUPERUSER roles detected.'
        }
    ];
}
function generateFindings(data) {
    const findings = [];
    const blockers = data.blockers;
    const replication = data.replication_readiness;
    const superuserRoles = getSuperuserRoles(data);
    const providerManagedRoles = getProviderManagedSuperuserRoles(data);
    if (!replication.wal_level_ok) findings.push({ severity: 'critical', category: 'Replication', finding: 'WAL level is not set to logical', recommendation: 'Run: ALTER SYSTEM SET wal_level = logical; then restart PostgreSQL.' });
    if (blockers.tables_without_pk_count > 0) findings.push({ severity: 'critical', category: 'Schema', finding: blockers.tables_without_pk_count + ' table(s) lack primary keys', recommendation: 'Add primary keys for logical replication, or use pg_dump/restore instead.' });
    if (data.unsupported_extensions && data.unsupported_extensions.length > 0) { const extList = data.unsupported_extensions.map(e => e.name).join(', '); findings.push({ severity: 'critical', category: 'Extensions', finding: 'Unsupported extension(s): ' + extList, recommendation: 'These extensions are not available in Snowflake Postgres. Refactor to remove dependencies.' }); }
    if (data.unsupported_languages && data.unsupported_languages.length > 0) { const langDetails = data.unsupported_languages.map(l => l.language + ' (' + l.function_count + ' functions)').join(', '); findings.push({ severity: 'critical', category: 'Languages', finding: 'Unsupported procedural language(s): ' + langDetails, recommendation: 'Rewrite functions in plpgsql or move logic to application layer.' }); }
    if (blockers.large_objects && blockers.large_objects.count > 0) findings.push({ severity: 'warning', category: 'Data', finding: blockers.large_objects.count + ' large object(s) detected', recommendation: 'Large objects are not replicated via logical replication. Export separately.' });
    if (data.inherited_tables && data.inherited_tables.length > 0) findings.push({ severity: 'critical', category: 'Schema', finding: data.inherited_tables.length + ' inherited table relationship(s) require follow-up investigation', recommendation: 'PostgreSQL inheritance is different from partitioning and does not replicate cleanly. Review the actual inheritance trees and any parent/child query or insert-routing behavior before choosing a migration method. After that, decide whether redesign or pg_dump/manual handling is required.' });
    if (data.unlogged_tables && data.unlogged_tables.length > 0) findings.push({ severity: 'warning', category: 'Schema', finding: data.unlogged_tables.length + ' unlogged table(s) detected', recommendation: 'Unlogged tables do not write to WAL, so logical replication will miss changes. Convert to LOGGED or keep them on the pg_dump/manual branch.' });
    if (needsHybridInvestigation(data)) findings.push({ severity: 'info', category: 'Method', finding: 'Potential hybrid candidate — object-level classification required', recommendation: hybridInvestigationGuidance(data) });
    if (superuserRoles.length > 0) { const roleList = superuserRoles.map(r => r.name).join(', '); findings.push({ severity: 'warning', category: 'Roles', finding: superuserRoles.length + ' source role(s) use SUPERUSER: ' + roleList, recommendation: 'Snowflake Postgres has no SUPERUSER. These roles will be created without it. Use snowflake_admin for target administration, but it is not a drop-in replacement for each source superuser; map each role to explicit target grants.' }); }
    if (providerManagedRoles.length > 0) { const roleList = providerManagedRoles.map(r => r.name).join(', '); findings.push({ severity: 'info', category: 'Platform', finding: 'Known provider-managed admin role(s) detected: ' + roleList, recommendation: 'These roles are internal to the source platform and are excluded from customer blocker counts. Any other SUPERUSER roles still require review and privilege mapping.' }); }
    if (data.postgres_owned && data.postgres_owned.length > 0) findings.push({ severity: 'warning', category: 'Ownership', finding: data.postgres_owned.length + " object(s) are owned by the source 'postgres' role", recommendation: "The source 'postgres' superuser is not accessible in Snowflake Postgres. Reassign these objects before or after migration." });
    if (data.sequences && data.sequences.length > 0) findings.push({ severity: 'info', category: 'Schema', finding: data.sequences.length + ' sequence(s) require manual sync', recommendation: 'Synchronize sequence values after cutover.' });
    if (data.materialized_views && data.materialized_views.length > 0) findings.push({ severity: 'info', category: 'Schema', finding: data.materialized_views.length + ' materialized view(s) need recreation', recommendation: 'Run REFRESH MATERIALIZED VIEW after migration.' });
    if (data.foreign_tables && data.foreign_tables.length > 0) findings.push({ severity: 'info', category: 'Schema', finding: data.foreign_tables.length + ' foreign table(s) need reconfiguration', recommendation: 'Review server and user mapping definitions.' });
    const platform = data.report_metadata.source_platform || 'Self-managed PostgreSQL';
    if (platform.includes('RDS') || platform.includes('Aurora')) findings.push({ severity: 'info', category: 'Platform', finding: 'Source platform: ' + platform, recommendation: 'Ensure rds_superuser has REPLICATION privilege. Check parameter groups for wal_level.' });
    else if (platform.includes('Azure')) findings.push({ severity: 'info', category: 'Platform', finding: 'Source platform: ' + platform, recommendation: 'Enable logical replication via Azure Portal server parameters.' });
    else if (platform.includes('Cloud SQL')) findings.push({ severity: 'info', category: 'Platform', finding: 'Source platform: ' + platform, recommendation: 'Enable cloudsql.logical_decoding flag.' });
    else if (platform.includes('Heroku')) findings.push({ severity: 'warning', category: 'Platform', finding: 'Source platform: ' + platform, recommendation: 'Logical replication requires Standard tier or higher.' });
    return findings;
}
function getRecommendedMethod(data) {
    const dbSize = data.database_overview.size_bytes;
    const hasBlockers = data.blockers.tables_without_pk_count > 0;
    const walOk = data.replication_readiness.wal_level_ok;
    if (hasBlockers) return 'dump';
    if (!walOk) return 'dump';
    if (dbSize > 50 * 1024 * 1024 * 1024) return 'replication';
    return 'replication';
}
function estimateSyncTime(bytes) {
    const hours = bytes / (10 * 1024 * 1024 * 1024);
    if (hours < 1) return '< 1 hour';
    if (hours < 24) return Math.ceil(hours) + ' hours';
    return Math.ceil(hours / 24) + ' days';
}
function estimateDumpTime(bytes) {
    const dumpHours = bytes / (10 * 1024 * 1024 * 1024);
    const restoreHours = bytes / (5 * 1024 * 1024 * 1024);
    const totalHours = dumpHours + restoreHours;
    if (totalHours < 1) return '< 1 hour';
    if (totalHours < 24) return Math.ceil(totalHours) + ' hours';
    return Math.ceil(totalHours / 24) + ' days';
}
function toggleSection(element) {
    element.classList.toggle('collapsed');
    element.nextElementSibling.classList.toggle('hidden');
}
function renderReport(data) {
    const readiness = getReadinessStatus(data);
    const recommendedMethod = getRecommendedMethod(data);
    const hybridInvestigation = needsHybridInvestigation(data);
    const findings = generateFindings(data);
    const meta = data.report_metadata;
    const overview = data.database_overview;
    const repl = data.replication_readiness;
    const criticalFindings = findings.filter(f => f.severity === 'critical');
    const warningFindings = findings.filter(f => f.severity === 'warning');
    const infoFindings = findings.filter(f => f.severity === 'info');
    let html = '<div class="section"><div class="readiness-box readiness-' + readiness.status + '"><div class="icon">' + (readiness.status === 'go' ? '&#x2705;' : readiness.status === 'conditional' ? '&#x26A0;&#xFE0F;' : '&#x274C;') + '</div><div class="text"><div class="title">Migration Readiness: ' + readiness.label + '</div><div class="desc">' + readiness.desc + '</div></div></div></div>';
    html += '<div class="summary-grid"><div class="summary-card"><div class="value">' + overview.size_pretty + '</div><div class="label">Database Size</div></div><div class="summary-card"><div class="value">' + formatNumber(overview.table_count) + '</div><div class="label">Tables</div></div><div class="summary-card"><div class="value">' + formatNumber(overview.index_count) + '</div><div class="label">Indexes</div></div><div class="summary-card"><div class="value">' + formatNumber(overview.total_rows) + '</div><div class="label">Total Rows</div></div><div class="summary-card"><div class="value">' + data.sequences.length + '</div><div class="label">Sequences</div></div><div class="summary-card"><div class="value">' + data.blockers.tables_without_pk_count + '</div><div class="label">Tables w/o PK</div></div></div>';
    const blockerRows = getBlockerSummaryRows(data);
    html += '<div class="section"><h2>Blockers & Warnings</h2><table><tr><th>Issue</th><th>Count</th><th>Notes</th></tr>' + blockerRows.map(r => '<tr' + (r.count > 0 ? ' style="background:#FFFBEB"' : '') + '><td>' + r.issue + '</td><td>' + formatNumber(r.count) + '</td><td>' + r.notes + '</td></tr>').join('') + '</table></div>';
    if (data.complexity_score !== undefined) { let lvl = 'SIMPLE', clr = '#10B981', desc = 'Straightforward migration with minimal special handling required.'; if (data.complexity_score > 500) { lvl = 'VERY COMPLEX'; clr = '#EF4444'; desc = 'Significant migration effort required. Consider a phased approach with extensive testing.'; } else if (data.complexity_score > 200) { lvl = 'COMPLEX'; clr = '#F59E0B'; desc = 'Multiple compatibility items need attention. Plan for additional migration steps and testing.'; } else if (data.complexity_score > 50) { lvl = 'MODERATE'; clr = '#F59E0B'; desc = 'Some items require manual handling but overall migration is manageable.'; } html += '<div class="section"><h2>Complexity Score</h2><p style="font-size:2rem;font-weight:700;color:' + clr + '">' + data.complexity_score + ' - ' + lvl + '</p><p style="margin-top:0.5rem;color:var(--text-muted)">' + desc + '</p><details style="margin-top:1rem"><summary style="cursor:pointer;color:var(--text-muted);font-size:0.875rem">How is this calculated?</summary><div style="margin-top:0.5rem;font-size:0.85rem;color:var(--text-muted);line-height:1.8">The complexity score is a weighted sum of migration factors: tables without primary keys (+5 each), unlogged tables (+10), inherited tables (+4), large objects (+15 if present), unsupported extensions (+10 each), unsupported language functions (+5 each), partitioned tables (+2), custom types (+2), materialized views (+2), foreign tables (+3), triggers (+2), and database size (+5 per 100 GB). <strong>0-50 = Simple</strong>, <strong>51-200 = Moderate</strong>, <strong>201-500 = Complex</strong>, <strong>500+ = Very Complex</strong>.</div></details></div>'; }
    html += '<div class="section"><h2>Recommended Migration Method</h2>' + (hybridInvestigation ? '<div style="background:#EFF6FF;border:1px solid #60A5FA;border-radius:8px;padding:1rem;margin-bottom:1rem"><strong>Potential hybrid candidate:</strong> ' + hybridInvestigationGuidance(data) + '</div>' : '') + '<div class="method-card ' + (recommendedMethod === 'replication' ? 'recommended' : '') + '"><h4>' + (recommendedMethod === 'replication' ? '&#x2B50; ' : '') + 'Logical Replication (Near-Zero Downtime)</h4><ul><li>Best for production databases requiring minimal downtime</li><li>Requires PostgreSQL 10+ with wal_level=logical</li><li>All tables must have primary keys</li><li>Estimated initial sync: ' + estimateSyncTime(overview.size_bytes) + '</li></ul>' + (!repl.wal_level_ok ? '<p style="color:#DC2626;margin-top:0.5rem">wal_level must be set to logical</p>' : '') + (data.blockers.tables_without_pk_count > 0 ? '<p style="color:#DC2626;margin-top:0.5rem">' + data.blockers.tables_without_pk_count + ' table(s) lack primary keys</p>' : '') + '</div><div class="method-card ' + (recommendedMethod === 'dump' ? 'recommended' : '') + '"><h4>' + (recommendedMethod === 'dump' ? '&#x2B50; ' : '') + 'pg_dump / pg_restore (Offline)</h4><ul><li>Best for dev/staging or when downtime is acceptable</li><li>Works with any table structure (no PK requirement)</li><li>Simpler setup, no ongoing replication</li><li>Estimated time: ' + estimateDumpTime(overview.size_bytes) + '</li></ul></div></div>';
    // Recommended Snowflake Postgres Instance section
    if (data.instance_recommendations) {
        const recs = data.instance_recommendations;
        const cp = recs.compute_pool || {};
        const st = recs.storage || {};
        const ha = recs.high_availability || {};
        html += '<div class="section"><h2>&#x2728; Recommended Snowflake Postgres Instance</h2>';
        html += '<p style="color:var(--text-muted);margin-bottom:1rem">Based on your source database characteristics, here are the recommended settings for your Snowflake Postgres instance:</p>';
        html += '<div class="info-grid"><div>';
        html += '<div class="info-item"><span class="label">Compute Pool</span><span class="value" style="color:var(--primary-color);font-weight:700">' + (cp.recommended || 'STANDARD_XL') + '</span></div>';
        html += '<div class="info-item"><span class="label">Storage</span><span class="value">' + (st.recommended_gb || 100) + ' GB</span></div>';
        html += '<div class="info-item"><span class="label">High Availability</span><span class="value">' + (ha.recommended ? 'Enable after validation &#x2705;' : 'Single-instance initially') + '</span></div>';
        html += '</div><div>';
        if (recs.source_metrics) {
            const sm = recs.source_metrics;
            html += '<div class="info-item"><span class="label">Source Size</span><span class="value">' + (sm.size_gb || 0).toFixed(1) + ' GB</span></div>';
            html += '<div class="info-item"><span class="label">Table Count</span><span class="value">' + (sm.table_count || 0) + '</span></div>';
            html += '<div class="info-item"><span class="label">PostGIS</span><span class="value">' + (sm.has_postgis ? 'Yes' : 'No') + '</span></div>';
            html += '<div class="info-item"><span class="label">pgvector</span><span class="value">' + (sm.has_pgvector ? 'Yes' : 'No') + '</span></div>';
        }
        html += '</div></div>';
        html += '<div style="margin-top:1rem;padding:1rem;background:var(--bg-color);border-radius:8px"><strong>Compute rationale:</strong> ' + (cp.rationale || '') + '</div>';
        if (ha.rationale) {
            html += '<div style="margin-top:1rem;padding:1rem;background:var(--bg-color);border-radius:8px"><strong>HA guidance:</strong> ' + ha.rationale + '</div>';
        }
        if (cp.alternatives && cp.alternatives.length > 0) {
            html += '<h3 style="margin-top:1.5rem">Alternative Options</h3><table><tr><th>Tier</th><th>Compute Pool</th><th>Pros</th><th>Cons</th></tr>';
            cp.alternatives.forEach(function(alt) {
                html += '<tr><td><span class="badge badge-info">' + (alt.tier || '') + '</span></td><td>' + (alt.pool || '') + '</td><td>' + (alt.pros || []).join(', ') + '</td><td>' + (alt.cons || []).join(', ') + '</td></tr>';
            });
            html += '</table>';
        }
        if (st.calculation) {
            html += '<p style="margin-top:1rem;color:var(--text-muted);font-size:0.85rem"><strong>Storage calculation:</strong> ' + st.calculation + '</p>';
        }
        if (ha.timing) {
            html += '<p style="margin-top:0.5rem;color:var(--text-muted);font-size:0.85rem"><strong>HA timing:</strong> ' + ha.timing + '</p>';
        }
        html += '</div>';
    }
    html += '<div class="section"><h2>Findings & Recommendations</h2>';
    if (criticalFindings.length > 0) { html += '<h3 style="color:var(--danger-color)">Critical Issues (' + criticalFindings.length + ')</h3><table><tr><th>Category</th><th>Finding</th><th>Recommendation</th></tr>' + criticalFindings.map(f => '<tr style="background:#FEF2F2"><td><span class="badge badge-danger">' + f.category + '</span></td><td>' + f.finding + '</td><td>' + f.recommendation + '</td></tr>').join('') + '</table>'; }
    if (warningFindings.length > 0) { html += '<h3 style="color:var(--warning-color)">Warnings (' + warningFindings.length + ')</h3><table><tr><th>Category</th><th>Finding</th><th>Recommendation</th></tr>' + warningFindings.map(f => '<tr style="background:#FFFBEB"><td><span class="badge badge-warning">' + f.category + '</span></td><td>' + f.finding + '</td><td>' + f.recommendation + '</td></tr>').join('') + '</table>'; }
    if (infoFindings.length > 0) { html += '<h3 style="color:var(--text-muted)">Information (' + infoFindings.length + ')</h3><table><tr><th>Category</th><th>Finding</th><th>Recommendation</th></tr>' + infoFindings.map(f => '<tr><td><span class="badge badge-info">' + f.category + '</span></td><td>' + f.finding + '</td><td>' + f.recommendation + '</td></tr>').join('') + '</table>'; }
    if (findings.length === 0) html += '<p style="color:var(--success-color)">No issues found. Database is ready for migration.</p>';
    html += '</div>';
    html += '<div class="section"><h2>Source Database Information</h2><div class="info-grid"><div><div class="info-item"><span class="label">Host</span><span class="value">' + (meta.source_host || 'localhost') + '</span></div><div class="info-item"><span class="label">Port</span><span class="value">' + meta.source_port + '</span></div><div class="info-item"><span class="label">Database</span><span class="value">' + meta.database + '</span></div><div class="info-item"><span class="label">Connected User</span><span class="value">' + meta.connected_user + '</span></div><div class="info-item"><span class="label">Source Platform</span><span class="value">' + (meta.source_platform || 'Self-managed') + '</span></div></div><div><div class="info-item"><span class="label">PostgreSQL Version</span><span class="value">' + meta.pg_version_num + '</span></div><div class="info-item"><span class="label">WAL Level</span><span class="value">' + repl.wal_level + ' ' + (repl.wal_level_ok ? '&#x2705;' : '&#x274C;') + '</span></div><div class="info-item"><span class="label">Replication Slots</span><span class="value">' + repl.used_replication_slots + ' / ' + repl.max_replication_slots + '</span></div><div class="info-item"><span class="label">Report Generated</span><span class="value">' + meta.generated_at + '</span></div></div></div></div>';
    if (data.extensions.length > 0) { html += '<div class="section"><h2 class="collapsible" onclick="toggleSection(this)">Extensions (' + data.extensions.length + ')</h2><div class="collapsible-content">' + (data.unsupported_extensions && data.unsupported_extensions.length > 0 ? '<div style="background:#FEF2F2;border:1px solid #EF4444;border-radius:8px;padding:1rem;margin-bottom:1rem"><strong style="color:#DC2626">Unsupported Extensions:</strong><ul style="margin:0.5rem 0 0 1.5rem;color:#991B1B">' + data.unsupported_extensions.map(e => '<li>' + e.name + ' (' + e.version + ')</li>').join('') + '</ul></div>' : '') + '<div class="extension-grid">' + data.extensions.map(ext => '<div class="extension-item"><span class="status-indicator ' + (ext.supported ? 'status-ok' : 'status-error') + '"></span><span>' + ext.name + ' (' + ext.version + ')</span></div>').join('') + '</div></div></div>'; }
    if (data.blockers.tables_without_pk_count > 0) { html += '<div class="section"><h2 class="collapsible" onclick="toggleSection(this)">Tables Without Primary Keys (' + data.blockers.tables_without_pk_count + ')</h2><div class="collapsible-content"><table><tr><th>Schema</th><th>Table</th><th>Rows</th><th>Size</th></tr>' + data.blockers.tables_without_pk.map(t => '<tr><td>' + t.schema + '</td><td>' + t.table + '</td><td>' + formatNumber(t.row_count) + '</td><td>' + t.size_pretty + '</td></tr>').join('') + '</table></div></div>'; }
    if (data.tables.length > 0) { html += '<div class="section"><h2 class="collapsible collapsed" onclick="toggleSection(this)">Tables Detail (' + data.tables.length + ')</h2><div class="collapsible-content hidden"><table><tr><th>Schema</th><th>Table</th><th>Rows</th><th>Dead Tuples</th><th>Size</th></tr>' + data.tables.slice(0, 50).map(t => '<tr><td>' + t.schema + '</td><td>' + t.name + '</td><td>' + formatNumber(t.row_count) + '</td><td>' + formatNumber(t.dead_tuples) + '</td><td>' + t.size_pretty + '</td></tr>').join('') + '</table>' + (data.tables.length > 50 ? '<p style="margin-top:1rem;color:var(--text-muted)">Showing top 50 of ' + data.tables.length + ' tables.</p>' : '') + '</div></div>'; }
    if (data.roles.length > 0) { html += '<div class="section"><h2 class="collapsible collapsed" onclick="toggleSection(this)">Roles (' + data.roles.length + ')</h2><div class="collapsible-content hidden"><table><tr><th>Role</th><th>Login</th><th>Superuser</th><th>Create DB</th><th>Replication</th></tr>' + data.roles.map(r => '<tr><td>' + r.name + '</td><td>' + (r.can_login ? '&#x2705;' : '&#x274C;') + '</td><td>' + (r.superuser ? '&#x2705;' : '&#x274C;') + '</td><td>' + (r.create_db ? '&#x2705;' : '&#x274C;') + '</td><td>' + (r.replication ? '&#x2705;' : '&#x274C;') + '</td></tr>').join('') + '</table></div></div>'; }
    if (data.database_settings.length > 0) { html += '<div class="section"><h2 class="collapsible collapsed" onclick="toggleSection(this)">Non-Default Settings (' + data.database_settings.length + ')</h2><div class="collapsible-content hidden"><table><tr><th>Setting</th><th>Value</th><th>Source</th></tr>' + data.database_settings.map(s => '<tr><td>' + s.name + '</td><td>' + s.setting + (s.unit ? ' ' + s.unit : '') + '</td><td>' + s.source + '</td></tr>').join('') + '</table></div></div>'; }
    document.getElementById('report-content').innerHTML = html;
}
renderReport(reportData);
    </script>
</body>
</html>
"""


def print_text_summary(data):
    meta = data['report_metadata']
    overview = data['database_overview']
    repl = data['replication_readiness']

    print()
    print("=" * 78)
    print("  MIGRATION ASSESSMENT SUMMARY")
    print("=" * 78)
    print(f"  Database:       {meta.get('database', '?')}")
    print(f"  Host:           {meta.get('source_host', '?')}")
    print(f"  PG Version:     {meta.get('pg_version_num', '?')}")
    print(f"  Platform:       {meta.get('source_platform', '?')}")
    print(f"  Size:           {overview.get('size_pretty', '?')}")
    print(f"  Tables:         {overview.get('table_count', '?')}")
    print(f"  Total Rows:     {overview.get('total_rows', '?')}")
    score = data.get('complexity_score', 0)
    if score > 500:
        lvl = 'VERY COMPLEX'
    elif score > 200:
        lvl = 'COMPLEX'
    elif score > 50:
        lvl = 'MODERATE'
    else:
        lvl = 'SIMPLE'
    print(f"  Complexity:     {score} ({lvl})")
    print(f"                  (0-50 Simple, 51-200 Moderate, 201-500 Complex, 500+ Very Complex)")
    print()

    has_pk_blocker = data['blockers']['tables_without_pk_count'] > 0
    wal_ok = repl.get('wal_level_ok', False)
    if has_pk_blocker or not wal_ok:
        print("  RECOMMENDED METHOD: pg_dump / pg_restore (Offline)")
        if not wal_ok:
            print("    Reason: WAL level is not set to logical")
        if has_pk_blocker:
            print(f"    Reason: {data['blockers']['tables_without_pk_count']} table(s) lack primary keys")
    else:
        print("  RECOMMENDED METHOD: Logical Replication (Near-Zero Downtime)")
    if _needs_hybrid_investigation(data):
        print("    NOTE: Potential hybrid candidate — do not approve hybrid from summary counts alone.")
        if data.get('inherited_tables'):
            print("          Table inheritance needs follow-up investigation first: review the actual")
            print("          inheritance trees and any parent/child query or insert-routing behavior.")
            print("          After that, run migrate/scripts/generate_hybrid_plan.py to classify")
            print("          actual non-replicable objects before choosing a method.")
        else:
            print("          The next workflow step is to run migrate/scripts/generate_hybrid_plan.py")
            print("          to classify actual non-replicable objects and confirm whether")
            print("          remediation (for example adding primary keys) removes the need")
            print("          for hybrid.")
    print()

    print("  REPLICATION READINESS")
    print("  " + "-" * 40)
    wal_ok = repl.get('wal_level_ok', False)
    print(f"  WAL Level:      {repl.get('wal_level', '?')}  {'OK' if wal_ok else 'NEEDS CHANGE'}")
    print(f"  Rep Slots:      {repl.get('used_replication_slots', '?')} / {repl.get('max_replication_slots', '?')}")
    print()

    blockers = data['blockers']
    print("  BLOCKERS")
    print("  " + "-" * 40)
    print(f"  Tables w/o PK:          {blockers['tables_without_pk_count']}")
    print(f"  Large Objects:          {blockers['large_objects']['count']}")
    print(f"  Unlogged Tables:        {len(data.get('unlogged_tables', []))}")
    print(f"  Inherited Tables:       {len(data.get('inherited_tables', []))}")
    print(f"  Unsupported Extensions: {len(data.get('unsupported_extensions', []))}")
    print(f"  Unsupported Languages:  {len(data.get('unsupported_languages', []))}")

    if data.get('unsupported_extensions'):
        for e in data['unsupported_extensions']:
            print(f"    - {e['name']} ({e['version']})")

    if data.get('unsupported_languages'):
        for l in data['unsupported_languages']:
            print(f"    - {l['language']} ({l['function_count']} functions)")

    inherited_tables = data.get('inherited_tables', [])
    if inherited_tables:
        print()
        print(f"  CRITICAL: {len(inherited_tables)} inherited table relationship(s) require follow-up investigation")
        print("  PostgreSQL inheritance is different from partitioning and does not replicate cleanly.")
        print("  Review the actual inheritance trees and application behavior before choosing")
        print("  a migration method, then decide whether redesign or pg_dump/manual handling is required.")

    unlogged_tables = data.get('unlogged_tables', [])
    if unlogged_tables:
        print()
        print(f"  WARNING: {len(unlogged_tables)} unlogged table(s)")
        print("  Unlogged tables do not write to WAL, so logical replication will miss changes.")
        print("  Convert them to LOGGED or migrate them with pg_dump.")

    postgres_owned = data.get('postgres_owned', [])
    if postgres_owned:
        print()
        print(f"  WARNING: {len(postgres_owned)} object(s) owned by 'postgres' role")
        print("  The 'postgres' superuser is not accessible in Snowflake Postgres.")
        print("  These objects must be reassigned before or after migration:")
        for obj in postgres_owned[:10]:
            print(f"    - {obj['schema']}.{obj['name']} ({obj['object_type']})")
        if len(postgres_owned) > 10:
            print(f"    ... and {len(postgres_owned) - 10} more")
        print("  Fix: ALTER TABLE/VIEW/SEQUENCE ... OWNER TO <new_role>;")

    provider_managed_superuser_roles = _provider_managed_superuser_roles(data)
    if provider_managed_superuser_roles:
        print()
        print("  INFO: Known provider-managed admin role(s) detected")
        for r in provider_managed_superuser_roles:
            print(f"    - {r['name']}")
        print("  These roles are internal to the source platform and are not treated as customer blockers.")
        print("  Any other SUPERUSER roles still require review and privilege mapping.")

    superuser_roles = _customer_superuser_roles(data)
    if superuser_roles:
        print()
        print(f"  WARNING: {len(superuser_roles)} role(s) with SUPERUSER privilege")
        print("  SUPERUSER is not available in Snowflake Postgres — these privileges will NOT be migrated.")
        for r in superuser_roles:
            print(f"    - {r['name']}")
        print("  These roles will be created without SUPERUSER.")
        print("  Snowflake Postgres provides 'snowflake_admin' for target administration,")
        print("  but it is not a drop-in replacement for each source superuser role.")
        print("  Plan a privilege mapping and grant only the specific capabilities needed.")

    print()

    has_critical = (
        blockers['tables_without_pk_count'] > 0 or
        not wal_ok or
        len(data.get('unsupported_extensions', [])) > 0 or
        len(data.get('unsupported_languages', [])) > 0
    )

    if has_critical:
        print("  STATUS: ACTION REQUIRED - Resolve critical blockers before migration")
    elif (blockers['large_objects']['count'] > 0 or
          len(data.get('inherited_tables', [])) > 0 or
          len(data.get('unlogged_tables', [])) > 0 or
          len(postgres_owned) > 0 or
          len(superuser_roles) > 0):
        print("  STATUS: CONDITIONAL - Some items require manual handling")
    else:
        print("  STATUS: READY - No blocking issues detected")

    # Instance recommendations
    recs = data.get('instance_recommendations', {})
    if recs:
        print()
        print("  RECOMMENDED SNOWFLAKE POSTGRES INSTANCE")
        print("  " + "-" * 40)
        cp = recs.get('compute_pool', {})
        st = recs.get('storage', {})
        ha = recs.get('high_availability', {})

        print(f"  Compute Pool:   {cp.get('recommended', 'STANDARD_XL')}")
        print(f"  Storage:        {st.get('recommended_gb', 100)} GB")
        print(
            "  High Avail:     "
            + ('Enable after validation' if ha.get('recommended') else 'Single-instance initially')
        )
        if ha.get('timing'):
            print(f"  HA timing:      {ha.get('timing')}")
        print()
        print(f"  Compute rationale: {cp.get('rationale', '')}")
        if ha.get('rationale'):
            print(f"  HA guidance:       {ha.get('rationale')}")

        alts = cp.get('alternatives', [])
        if alts:
            print()
            print("  ALTERNATIVES:")
            for alt in alts:
                tier = alt.get('tier', '')
                pool = alt.get('pool', '')
                pros = ', '.join(alt.get('pros', [])[:2])
                cons = ', '.join(alt.get('cons', [])[:2])
                print(f"    {tier}: {pool}")
                print(f"      Pros: {pros}")
                print(f"      Cons: {cons}")

    print("=" * 78)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='PostgreSQL to Snowflake Postgres migration assessment',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_assessment.py --host db.example.com --dbname mydb --user admin
  python run_assessment.py -H db.example.com -d mydb -U admin --html report.html
  python run_assessment.py -H db.example.com -d mydb -U admin --json data.json --html report.html

Environment variables (alternative to flags):
  SOURCE_PGHOST, SOURCE_PGDATABASE, SOURCE_PGUSER, SOURCE_PGPORT, PGPASSWORD
""")
    # Use add_source_args from pg_common: provides --source-service (chat-safe path
    # via ~/.pg_service.conf + ~/.pgpass) plus --host/-H/--port/-p/--dbname/-d/
    # --user/-U/--password/-W/--sslmode with identical dest names to the previous
    # standalone argparse, so downstream code (args.host etc) keeps working unchanged.
    add_source_args(parser)
    parser.add_argument('--html', metavar='FILE',
                        help='Generate HTML report to FILE')
    parser.add_argument('--json', metavar='FILE',
                        help='Save JSON assessment data to FILE')
    parser.add_argument('--quiet', '-q', action='store_true',
                        help='Suppress progress output')
    parser.add_argument('--schemas', metavar='LIST',
                        help='Comma-separated list of schemas to assess (default: all user schemas)')
    parser.add_argument('--open', dest='open_report', metavar='FILE', default=None,
                        help='Open an existing HTML report in the default browser and exit. '
                             'Does not re-run the assessment.')
    parser.add_argument('--no-open', action='store_true',
                        help='Do not auto-open the HTML report in a browser after assessment completes')

    args = parser.parse_args()

    if args.open_report:
        path = os.path.abspath(args.open_report)
        if not os.path.exists(path):
            parser.error(f"report not found: {path}")
        webbrowser.open(f"file://{path}")
        sys.exit(0)

    # Resolve --source-service NAME from ~/.pg_service.conf BEFORE validation.
    _apply_source_service(args)

    if not args.host or not args.dbname or not args.user:
        parser.error("--host, --dbname, and --user are required (OR --source-service NAME, OR set SOURCE_PG* env vars)")

    password = resolve_source_password(args)

    if DB_DRIVER is None:
        print("ERROR: No PostgreSQL driver found.", file=sys.stderr)
        print("Install one of:", file=sys.stderr)
        print("  pip install psycopg2-binary", file=sys.stderr)
        print("  pip install pg8000", file=sys.stderr)
        sys.exit(1)

    if not args.quiet:
        print(f"Using database driver: {DB_DRIVER}")

    data = run_assessment(args.host, args.port, args.dbname, args.user, password,
                          args.sslmode, args.schemas,
                          sslrootcert=getattr(args, 'sslrootcert', None),
                          hostaddr=getattr(args, 'hostaddr', None))

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        print(f"JSON data saved: {args.json}")

    html_path = args.html
    if not html_path:
        html_path = 'migration_assessment_report.html'

    generate_html_report(data, html_path)

    print_text_summary(data)

    if not args.no_open:
        abs_path = os.path.abspath(html_path)
        print(f"Opening report: {abs_path}")
        try:
            webbrowser.open(f"file://{abs_path}")
        except Exception as e:
            print(f"(could not auto-open browser: {e}; open {abs_path} manually)", file=sys.stderr)

    if data.get('unsupported_extensions') or data.get('unsupported_languages'):
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
