#!/usr/bin/env python3
"""
test_connectivity.py
Test network connectivity between source PostgreSQL and target Snowflake Postgres.

Replaces test_connectivity.sh - no psql dependency required.

Usage:
    python test_connectivity.py --host source.example.com --dbname mydb --user admin \
        --target-host sf-pg.example.com --target-dbname postgres --target-user admin

Environment variables (alternative to flags):
    SOURCE_PGHOST, SOURCE_PGDATABASE, SOURCE_PGUSER, SOURCE_PGPORT
    TARGET_PGHOST, TARGET_PGDATABASE, TARGET_PGUSER, TARGET_PGPORT
    PGPASSWORD / SOURCE_PGPASSWORD, TARGET_PGPASSWORD
"""

import argparse
import json
import os
import socket
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pg_common import (
    check_driver, connect, query, scalar,
    add_source_args, add_target_args,
    resolve_source_password, resolve_target_password,
    quote_literal,
    _apply_source_service, _apply_target_service,
)


def probe_dns(host):
    try:
        ips = socket.getaddrinfo(host, None, socket.AF_INET)
        ip = ips[0][4][0] if ips else None
        return {'ok': True, 'ip': ip}
    except socket.gaierror as e:
        return {'ok': False, 'error': str(e)}


def probe_tcp(host, port, timeout=10):
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.close()
        return {'ok': True}
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        return {'ok': False, 'error': str(e)}


def probe_pg_connection(host, port, dbname, user, password, sslmode, label,
                        sslrootcert=None, hostaddr=None):
    result = {'label': label, 'host': host, 'port': port, 'dbname': dbname}
    try:
        conn = connect(host, port, dbname, user, password, sslmode,
                       sslrootcert=sslrootcert, hostaddr=hostaddr)
        conn.autocommit = True
        ver = scalar(conn, "SELECT version()")
        db = scalar(conn, "SELECT current_database()")
        usr = scalar(conn, "SELECT current_user")
        result.update({'ok': True, 'version': ver, 'database': db, 'user': usr})
        conn.close()
    except Exception as e:
        result.update({'ok': False, 'error': str(e)})
    return result


def probe_source_replication(host, port, dbname, user, password, sslmode,
                             sslrootcert=None, hostaddr=None):
    result = {}
    try:
        conn = connect(host, port, dbname, user, password, sslmode,
                       sslrootcert=sslrootcert, hostaddr=hostaddr)
        conn.autocommit = True
        result['wal_level'] = scalar(conn, "SELECT current_setting('wal_level')")
        result['wal_level_ok'] = result['wal_level'] == 'logical'
        result['max_replication_slots'] = int(scalar(conn, "SELECT current_setting('max_replication_slots')::int"))
        result['used_replication_slots'] = int(scalar(conn, "SELECT count(*) FROM pg_replication_slots"))
        result['max_wal_senders'] = int(scalar(conn, "SELECT current_setting('max_wal_senders')::int"))
        result['active_wal_senders'] = int(scalar(conn, "SELECT count(*) FROM pg_stat_replication"))
        has_rep = scalar(conn, "SELECT rolreplication FROM pg_roles WHERE rolname = current_user")
        result['user_has_replication'] = bool(has_rep)
        conn.close()
        result['ok'] = True
    except Exception as e:
        result['ok'] = False
        result['error'] = str(e)
    return result


def probe_target_write(host, port, dbname, user, password, sslmode,
                       sslrootcert=None, hostaddr=None):
    result = {}
    try:
        conn = connect(host, port, dbname, user, password, sslmode,
                       sslrootcert=sslrootcert, hostaddr=hostaddr)
        conn.autocommit = True
        query(conn, "CREATE TABLE IF NOT EXISTS _migration_conn_test (id int)")
        query(conn, "DROP TABLE IF EXISTS _migration_conn_test")
        result['write_ok'] = True
        conn.close()
        result['ok'] = True
    except Exception as e:
        result['ok'] = False
        result['error'] = str(e)
    return result


def _fdw_options_sql(options):
    """Render postgres_fdw option pairs as literal SQL fragments."""
    return ", ".join(f"{key} {quote_literal(value)}" for key, value in options)


def probe_target_to_source(target_args, source_args):
    result = {}
    conn = None
    try:
        target_pw = resolve_target_password(target_args)
        target_hostaddr = getattr(target_args, 'target_hostaddr', None)
        conn = connect(target_args.target_host, target_args.target_port,
                       target_args.target_dbname, target_args.target_user,
                       target_pw, target_args.target_sslmode,
                       sslrootcert=getattr(target_args, 'target_sslrootcert', None),
                       hostaddr=target_hostaddr)
        conn.autocommit = True

        query(conn, "CREATE EXTENSION IF NOT EXISTS postgres_fdw")
        query(conn, "DROP SERVER IF EXISTS _migration_connectivity_test CASCADE")

        source_pw = resolve_source_password(source_args)

        # postgres_fdw inherits libpq's default sslmode ('prefer') unless the
        # SERVER explicitly sets it. Direct source auth in step 3 uses
        # source_args.sslmode/sslrootcert, so without forwarding them here a
        # source that requires verify-ca (Azure DB for PostgreSQL, RDS with
        # rds.force_ssl, etc.) passes step 3 and false-fails step 6. Build the
        # OPTIONS list dynamically so we only emit sslrootcert when present.
        fdw_options = [
            ("host", source_args.host),
            ("port", str(source_args.port)),
            ("dbname", source_args.dbname),
            ("connect_timeout", "10"),
            ("sslmode", source_args.sslmode or "require"),
        ]
        source_hostaddr = getattr(source_args, 'hostaddr', None)
        if source_hostaddr:
            fdw_options.insert(1, ("hostaddr", source_hostaddr))
        source_sslrootcert = getattr(source_args, 'sslrootcert', None)
        if source_sslrootcert:
            fdw_options.append(("sslrootcert", source_sslrootcert))

        # CREATE SERVER / USER MAPPING option values must be SQL literals in the
        # statement text, not DB-API bind params.
        opts_sql = _fdw_options_sql(fdw_options)
        query(conn, f"""
            CREATE SERVER _migration_connectivity_test
                FOREIGN DATA WRAPPER postgres_fdw
                OPTIONS ({opts_sql})
        """)

        query(conn, f"""
            CREATE USER MAPPING FOR CURRENT_USER
                SERVER _migration_connectivity_test
                OPTIONS (user {quote_literal(source_args.user)}, password {quote_literal(source_pw)})
        """)

        query(conn, """
            DROP FOREIGN TABLE IF EXISTS _migration_test_table
        """)
        query(conn, """
            CREATE FOREIGN TABLE _migration_test_table (setting text, val text)
                SERVER _migration_connectivity_test
                OPTIONS (schema_name 'pg_catalog', table_name 'pg_settings')
        """)

        row = scalar(conn, "SELECT count(*) FROM _migration_test_table")
        result['ok'] = row is not None and int(row) > 0

        query(conn, "DROP FOREIGN TABLE IF EXISTS _migration_test_table")
        query(conn, "DROP SERVER IF EXISTS _migration_connectivity_test CASCADE")
        conn.close()
    except Exception as e:
        result['ok'] = False
        result['error'] = str(e)
        try:
            if conn is not None:
                query(conn, "DROP FOREIGN TABLE IF EXISTS _migration_test_table")
                query(conn, "DROP SERVER IF EXISTS _migration_connectivity_test CASCADE")
                conn.close()
        except Exception:
            pass
    return result


def icon(ok):
    return 'PASS' if ok else 'FAIL'


def run_tests(args):
    results = {'timestamp': datetime.now().isoformat(), 'tests': []}
    source_pw = resolve_source_password(args)
    target_pw = resolve_target_password(args)
    source_hostaddr = getattr(args, 'hostaddr', None)
    target_hostaddr = getattr(args, 'target_hostaddr', None)

    print()
    print("=" * 70)
    print("  CONNECTIVITY TEST - PostgreSQL Migration")
    print("=" * 70)

    print("\n1. DNS Resolution")
    print("-" * 40)
    if args.host:
        if source_hostaddr:
            dns = {'ok': True, 'skipped': True, 'ip': source_hostaddr}
            print(f"  [SKIP] Source: {args.host} (using hostaddr {source_hostaddr})")
        else:
            dns = probe_dns(args.host)
            print(f"  [{icon(dns['ok'])}] Source: {args.host} -> {dns.get('ip', dns.get('error'))}")
        results['tests'].append({'name': 'source_dns', **dns})
    if args.target_host:
        if target_hostaddr:
            dns_t = {'ok': True, 'skipped': True, 'ip': target_hostaddr}
            print(f"  [SKIP] Target: {args.target_host} (using hostaddr {target_hostaddr})")
        else:
            dns_t = probe_dns(args.target_host)
            print(f"  [{icon(dns_t['ok'])}] Target: {args.target_host} -> {dns_t.get('ip', dns_t.get('error'))}")
        results['tests'].append({'name': 'target_dns', **dns_t})

    print("\n2. TCP Connectivity")
    print("-" * 40)
    if args.host:
        source_probe_host = source_hostaddr or args.host
        tcp = probe_tcp(source_probe_host, args.port)
        print(f"  [{icon(tcp['ok'])}] Source: {args.host}:{args.port}")
        if source_hostaddr:
            print(f"       Using hostaddr: {source_hostaddr}")
        results['tests'].append({'name': 'source_tcp', **tcp})
    if args.target_host:
        target_probe_host = target_hostaddr or args.target_host
        tcp_t = probe_tcp(target_probe_host, args.target_port)
        print(f"  [{icon(tcp_t['ok'])}] Target: {args.target_host}:{args.target_port}")
        if target_hostaddr:
            print(f"       Using hostaddr: {target_hostaddr}")
        results['tests'].append({'name': 'target_tcp', **tcp_t})

    # _apply_*_service in main() populates these from the service profile when
    # --source-service / --target-service is used; resolved here once so the
    # probes don't have to re-getattr or know about the service plumbing.
    source_sslrootcert = getattr(args, 'sslrootcert', None)
    target_sslrootcert = getattr(args, 'target_sslrootcert', None)

    print("\n3. PostgreSQL Authentication")
    print("-" * 40)
    if args.host and args.dbname and args.user:
        pg_s = probe_pg_connection(args.host, args.port, args.dbname,
                                   args.user, source_pw, args.sslmode, 'SOURCE',
                                   sslrootcert=source_sslrootcert,
                                   hostaddr=source_hostaddr)
        print(f"  [{icon(pg_s['ok'])}] Source: {args.user}@{args.host}/{args.dbname}")
        if pg_s['ok']:
            print(f"       Version: {pg_s.get('version', '?')}")
        else:
            print(f"       Error: {pg_s.get('error', '?')}")
        results['tests'].append({'name': 'source_auth', **pg_s})

    if args.target_host and args.target_dbname and args.target_user:
        pg_t = probe_pg_connection(args.target_host, args.target_port, args.target_dbname,
                                   args.target_user, target_pw, args.target_sslmode, 'TARGET',
                                   sslrootcert=target_sslrootcert,
                                   hostaddr=target_hostaddr)
        print(f"  [{icon(pg_t['ok'])}] Target: {args.target_user}@{args.target_host}/{args.target_dbname}")
        if pg_t['ok']:
            print(f"       Version: {pg_t.get('version', '?')}")
        else:
            print(f"       Error: {pg_t.get('error', '?')}")
        results['tests'].append({'name': 'target_auth', **pg_t})

    print("\n4. Source Replication Settings")
    print("-" * 40)
    if args.host and args.dbname and args.user:
        rep = probe_source_replication(args.host, args.port, args.dbname,
                                      args.user, source_pw, args.sslmode,
                                      sslrootcert=source_sslrootcert,
                                      hostaddr=source_hostaddr)
        if rep.get('ok'):
            print(f"  [{icon(rep['wal_level_ok'])}] wal_level = {rep['wal_level']}")
            print(f"  [{'PASS' if rep['used_replication_slots'] < rep['max_replication_slots'] else 'FAIL'}] "
                  f"Replication slots: {rep['used_replication_slots']}/{rep['max_replication_slots']}")
            print(f"  [{icon(rep['user_has_replication'])}] User has REPLICATION privilege")
        else:
            print(f"  [SKIP] Could not check: {rep.get('error', '?')}")
        results['tests'].append({'name': 'source_replication', **rep})

    print("\n5. Target Write Access")
    print("-" * 40)
    if args.target_host and args.target_dbname and args.target_user:
        wr = probe_target_write(args.target_host, args.target_port, args.target_dbname,
                               args.target_user, target_pw, args.target_sslmode,
                               sslrootcert=target_sslrootcert,
                               hostaddr=target_hostaddr)
        print(f"  [{icon(wr.get('write_ok', False))}] Write access on target")
        results['tests'].append({'name': 'target_write', **wr})

    print("\n6. Network Path: Target -> Source (for logical replication)")
    print("-" * 40)
    if (args.target_host and args.target_dbname and args.target_user and
            args.host and args.dbname and args.user):
        net = probe_target_to_source(args, args)
        print(f"  [{icon(net.get('ok', False))}] Target can reach source via postgres_fdw")
        if not net.get('ok'):
            print(f"       Error: {net.get('error', '?')}")
            print()
            print("  Troubleshooting:")
            print("  1. Create network rule: TYPE=IPV4, MODE=POSTGRES_EGRESS")
            print("  2. Resolve source IP: dig +short", args.host)
            print("  3. Add IP/32 to VALUE_LIST in network rule")
            print("  4. Ensure source firewall allows inbound from Snowflake")
        results['tests'].append({'name': 'target_to_source', **net})
    else:
        print("  [SKIP] Both source and target params required")

    all_ok = all(t.get('ok', False) for t in results['tests'] if 'ok' in t)

    print()
    print("=" * 70)
    if all_ok:
        print("  RESULT: ALL TESTS PASSED - Ready for migration")
    else:
        failed = [t['name'] for t in results['tests'] if not t.get('ok', True)]
        print(f"  RESULT: FAILED - {len(failed)} test(s) failed: {', '.join(failed)}")
    print("=" * 70)
    print()

    return results, all_ok


def main():
    parser = argparse.ArgumentParser(
        description='Test migration connectivity (source and target PostgreSQL)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_connectivity.py --host src.example.com -d mydb -U admin \\
      --target-host sf-pg.example.com --target-dbname postgres --target-user admin

Environment variables:
  SOURCE_PGHOST, SOURCE_PGDATABASE, SOURCE_PGUSER, SOURCE_PGPORT
  TARGET_PGHOST, TARGET_PGDATABASE, TARGET_PGUSER, TARGET_PGPORT
  PGPASSWORD / SOURCE_PGPASSWORD, TARGET_PGPASSWORD
""")
    add_source_args(parser)
    add_target_args(parser)
    parser.add_argument('--json', metavar='FILE', help='Save results as JSON')

    args = parser.parse_args()
    check_driver()
    # Resolve --source-service / --target-service from ~/.pg_service.conf BEFORE
    # run_tests inspects args.host / args.target_host (which gate the DNS / TCP
    # probes). Without this, --source-service alone would skip ALL probes.
    _apply_source_service(args)
    _apply_target_service(args)

    results, all_ok = run_tests(args)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Results saved: {args.json}")

    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
