#!/usr/bin/env python3
"""
validate_schema_compatibility.py
Pre-flight schema validation for PostgreSQL to Snowflake Postgres migration

Validates:
- Extension compatibility
- Function language support
- Data type compatibility
- Index type support
- Constraint support

Usage:
    python validate_schema_compatibility.py --host <host> --dbname <db> --user <user>
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Set, Tuple
from datetime import datetime

# Resolve pg_common from the shared generic-PG layer at snowflake-postgres/scripts/shared/.
# pytest handles this via pythonpath; for direct invocation we add it to sys.path here.
from pathlib import Path as _P
_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from pg_common import (
    check_driver, connect, query, scalar,
    add_source_args, resolve_source_password, _apply_source_service,
    SUPPORTED_EXTENSIONS, SUPPORTED_LANGUAGES,
)

# Index types and their support
INDEX_SUPPORT = {
    'btree': {'supported': True, 'notes': 'Full support'},
    'hash': {'supported': True, 'notes': 'Full support'},
    'gist': {'supported': True, 'notes': 'Full support, rebuild recommended after migration'},
    'spgist': {'supported': True, 'notes': 'Full support'},
    'gin': {'supported': True, 'notes': 'Full support'},
    'brin': {'supported': True, 'notes': 'Full support'},
    'ivfflat': {'supported': True, 'notes': 'pgvector index, rebuild after data load'},
    'hnsw': {'supported': True, 'notes': 'pgvector index, rebuild after data load'}
}


@dataclass
class ValidationResult:
    """Single validation check result"""
    category: str
    item: str
    status: str  # 'OK', 'WARNING', 'ERROR'
    message: str
    details: Dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Complete validation report"""
    database: str
    host: str
    timestamp: str
    passed: int = 0
    warnings: int = 0
    errors: int = 0
    results: List[ValidationResult] = field(default_factory=list)


def run_query(conn, sql: str) -> List[List[str]]:
    """Execute PostgreSQL query, return rows as list of dicts"""
    return query(conn, sql)


def validate_extensions(conn) -> List[ValidationResult]:
    results = []
    rows = run_query(conn, "SELECT extname, extversion FROM pg_extension WHERE extname != 'plpgsql'")
    for r in rows:
        extname, version = r['extname'], r['extversion']
        if extname.lower() in SUPPORTED_EXTENSIONS:
            results.append(ValidationResult(
                category='extension', item=extname, status='OK',
                message=f'Extension {extname} v{version} is supported',
                details={'version': version}
            ))
        else:
            results.append(ValidationResult(
                category='extension', item=extname, status='ERROR',
                message=f'Extension {extname} is NOT supported in Snowflake Postgres',
                details={'version': version, 'action': 'Remove dependency or find alternative'}
            ))
    return results


def validate_function_languages(conn) -> List[ValidationResult]:
    results = []
    rows = run_query(conn, """
        SELECT l.lanname, count(*) AS func_count,
               array_agg(DISTINCT n.nspname || '.' || p.proname) AS functions
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_language l ON l.oid = p.prolang
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema')
        GROUP BY l.lanname
    """)
    for r in rows:
        lang = r['lanname']
        count = str(r['func_count'])
        funcs = str(r.get('functions', ''))
        if lang.lower() in SUPPORTED_LANGUAGES:
            results.append(ValidationResult(
                category='function_language', item=lang, status='OK',
                message=f'{count} functions in {lang} - supported',
                details={'count': int(count)}
            ))
        else:
            results.append(ValidationResult(
                category='function_language', item=lang, status='ERROR',
                message=f'{count} functions in {lang} - NOT supported, must rewrite',
                details={'count': int(count), 'functions': funcs, 'action': 'Rewrite functions in plpgsql or SQL'}
            ))
    return results


def validate_data_types(conn) -> List[ValidationResult]:
    """Inventory and assess custom types in the source database.

    All four kinds (ENUM/COMPOSITE/DOMAIN/RANGE) are migratable via pg_dump,
    but each has caveats that should surface as a WARNING — not OK — so the
    operator reviews them before cutover:

    - ENUMs cannot be added via logical replication; if you reorder or
      ALTER TYPE … ADD VALUE on the source after migration starts, the target
      will diverge. Recreate cleanly via DDL replay.
    - COMPOSITE types can drift if their column list changes during migration.
    - DOMAINs with CHECK constraints replay fine, but operators sometimes
      assume domain CHECKs run on logically-replicated INSERTs (they don't —
      replication bypasses DOMAIN checks).
    - RANGE types are fine but their subtype DOMAINs/composites need to land
      first — pg_dump handles ordering for full dumps, but `--data-only`
      flows can fail.

    Pre-fix this function blanket-marked every custom type as OK, which
    contradicted the module docstring's "validates… data type compatibility"
    claim. Now each kind gets a targeted message + WARNING.
    """
    results = []
    rows = run_query(conn, """
        SELECT t.typtype, n.nspname || '.' || t.typname AS type_name
        FROM pg_type t
        JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE t.typtype IN ('e', 'c', 'd', 'r')
        AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
    """)
    kind_meta = {
        'e': ('ENUM',
              'WARNING',
              'ENUM types migrate via pg_dump but ALTER TYPE … ADD VALUE on the source '
              'after cutover begins will diverge from the target. Re-DDL after migration.'),
        'c': ('COMPOSITE',
              'WARNING',
              'COMPOSITE type column list must not change during the migration window. '
              'Verify no pending ALTER TYPE … ADD/DROP ATTRIBUTE statements.'),
        'd': ('DOMAIN',
              'WARNING',
              'DOMAIN CHECK constraints run on direct INSERTs but are bypassed by logical '
              'replication. Re-validate domain-bound columns post-cutover.'),
        'r': ('RANGE',
              'OK',
              'RANGE types migrate cleanly via pg_dump (subtype dependencies are ordered).'),
    }
    for r in rows:
        type_code = r['typtype']
        type_name = r['type_name']
        kind, status, message = kind_meta.get(type_code, ('Custom', 'WARNING', 'Unknown custom type kind'))
        results.append(ValidationResult(
            category='data_type', item=type_name, status=status,
            message=f'{kind} type {type_name}: {message}',
            details={'type_kind': kind}
        ))
    return results


def validate_indexes(conn) -> List[ValidationResult]:
    results = []
    rows = run_query(conn, """
        SELECT am.amname AS index_type, count(*) AS index_count,
               pg_size_pretty(sum(pg_relation_size(i.indexrelid))) AS total_size
        FROM pg_index i
        JOIN pg_class c ON c.oid = i.indexrelid
        JOIN pg_am am ON am.oid = c.relam
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        GROUP BY am.amname
    """)
    for r in rows:
        idx_type = r['index_type']
        count = str(r['index_count'])
        size = r['total_size']
        support = INDEX_SUPPORT.get(idx_type.lower(), {'supported': True, 'notes': 'Check compatibility'})
        if support['supported']:
            results.append(ValidationResult(
                category='index_type', item=idx_type, status='OK',
                message=f'{count} {idx_type} indexes ({size}) - {support["notes"]}',
                details={'count': int(count), 'size': size}
            ))
        else:
            results.append(ValidationResult(
                category='index_type', item=idx_type, status='ERROR',
                message=f'{count} {idx_type} indexes - NOT supported',
                details={'count': int(count), 'size': size}
            ))

    vec_rows = run_query(conn, """
        SELECT indexname FROM pg_indexes WHERE indexdef LIKE '%ivfflat%' OR indexdef LIKE '%hnsw%'
    """)
    if vec_rows:
        results.append(ValidationResult(
            category='index_type', item='pgvector_indexes', status='WARNING',
            message=f'{len(vec_rows)} pgvector indexes found - rebuild required after migration',
            details={'count': len(vec_rows)}
        ))
    return results


def validate_constraints(conn) -> List[ValidationResult]:
    results = []
    rows = run_query(conn, """
        SELECT n.nspname || '.' || c.relname AS table_name, con.conname, con.contype
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE con.condeferrable = true AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    """)
    if rows:
        results.append(ValidationResult(
            category='constraint', item='deferred_constraints', status='WARNING',
            message=f'{len(rows)} deferred constraints found - verify behavior after migration',
            details={'count': len(rows)}
        ))

    excl = run_query(conn, """
        SELECT n.nspname || '.' || c.relname, con.conname
        FROM pg_constraint con
        JOIN pg_class c ON c.oid = con.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE con.contype = 'x' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    """)
    if excl:
        results.append(ValidationResult(
            category='constraint', item='exclusion_constraints', status='OK',
            message=f'{len(excl)} exclusion constraints - supported',
            details={'count': len(excl)}
        ))
    return results


def validate_tablespaces(conn) -> List[ValidationResult]:
    results = []
    rows = run_query(conn, "SELECT spcname FROM pg_tablespace WHERE spcname NOT IN ('pg_default', 'pg_global')")
    if rows:
        results.append(ValidationResult(
            category='tablespace', item='custom_tablespaces', status='WARNING',
            message=f'{len(rows)} custom tablespaces - will use default on target',
            details={'tablespaces': [r['spcname'] for r in rows]}
        ))
    return results


def validate_row_level_security(conn) -> List[ValidationResult]:
    results = []
    rows = run_query(conn, "SELECT count(*) AS cnt FROM pg_policies WHERE schemaname NOT IN ('pg_catalog', 'information_schema')")
    if rows and int(rows[0]['cnt']) > 0:
        count = int(rows[0]['cnt'])
        results.append(ValidationResult(
            category='security', item='rls_policies', status='OK',
            message=f'{count} RLS policies - supported via pg_dump',
            details={'count': count}
        ))
    return results


def generate_report(report: ValidationReport, output_format: str, output_path: str):
    """Generate validation report in specified format"""
    
    if output_format == 'json':
        data = {
            'database': report.database,
            'host': report.host,
            'timestamp': report.timestamp,
            'summary': {
                'passed': report.passed,
                'warnings': report.warnings,
                'errors': report.errors
            },
            'results': [
                {
                    'category': r.category,
                    'item': r.item,
                    'status': r.status,
                    'message': r.message,
                    'details': r.details
                }
                for r in report.results
            ]
        }
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    elif output_format == 'html':
        status_colors = {'OK': '#28a745', 'WARNING': '#ffc107', 'ERROR': '#dc3545'}
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Schema Validation Report - {report.database}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1000px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; }}
        h1 {{ color: #333; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .summary-item {{ padding: 20px; border-radius: 8px; text-align: center; flex: 1; }}
        .passed {{ background: #d4edda; }}
        .warnings {{ background: #fff3cd; }}
        .errors {{ background: #f8d7da; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f8f9fa; }}
        .status {{ padding: 4px 12px; border-radius: 4px; font-weight: bold; color: white; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Schema Validation Report</h1>
        <p><strong>Database:</strong> {report.database} | <strong>Host:</strong> {report.host} | <strong>Time:</strong> {report.timestamp}</p>
        
        <div class="summary">
            <div class="summary-item passed"><h2>{report.passed}</h2><p>Passed</p></div>
            <div class="summary-item warnings"><h2>{report.warnings}</h2><p>Warnings</p></div>
            <div class="summary-item errors"><h2>{report.errors}</h2><p>Errors</p></div>
        </div>
        
        <table>
            <tr><th>Category</th><th>Item</th><th>Status</th><th>Message</th></tr>
"""
        for r in report.results:
            html += f"""
            <tr>
                <td>{r.category}</td>
                <td>{r.item}</td>
                <td><span class="status" style="background: {status_colors[r.status]}">{r.status}</span></td>
                <td>{r.message}</td>
            </tr>"""
        
        html += """
        </table>
    </div>
</body>
</html>"""
        
        with open(output_path, 'w') as f:
            f.write(html)
    
    else:  # text
        lines = [
            "=" * 80,
            f"SCHEMA VALIDATION REPORT - {report.database}",
            "=" * 80,
            f"Host: {report.host}",
            f"Timestamp: {report.timestamp}",
            "",
            f"Summary: {report.passed} passed, {report.warnings} warnings, {report.errors} errors",
            "",
            "-" * 80,
        ]
        
        for r in report.results:
            status_icon = {'OK': '✅', 'WARNING': '⚠️', 'ERROR': '❌'}.get(r.status, '?')
            lines.append(f"{status_icon} [{r.category}] {r.item}: {r.message}")
        
        lines.append("=" * 80)
        
        with open(output_path, 'w') as f:
            f.write('\n'.join(lines))
    
    print(f"Report generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Validate schema compatibility for Snowflake Postgres')
    add_source_args(parser)
    parser.add_argument('--output', '-o', default='validation_report', help='Output filename')
    parser.add_argument('--format', '-f', choices=['text', 'json', 'html'], default='text', help='Output format')

    args = parser.parse_args()
    check_driver()
    # --source-service NAME populates host/port/dbname/user from ~/.pg_service.conf
    # (chat-safe path). Resolve the profile BEFORE validation so the operator
    # can pass a service name alone.
    _apply_source_service(args)
    password = resolve_source_password(args)

    if not args.host or not args.dbname or not args.user:
        parser.error("Source connection params required (--host, --dbname, --user, OR --source-service NAME)")

    print(f"Validating schema compatibility for: {args.dbname} on {args.host}")

    # sslrootcert is populated by _apply_source_service from --source-service's
    # ~/.pg_service.conf entry; forwarding it lets sslmode=verify-ca verify
    # against the per-instance CA instead of the system bundle.
    conn = connect(args.host, args.port, args.dbname, args.user, password, args.sslmode,
                   sslrootcert=getattr(args, 'sslrootcert', None),
                   hostaddr=getattr(args, 'hostaddr', None))
    conn.autocommit = True

    report = ValidationReport(
        database=args.dbname,
        host=args.host,
        timestamp=datetime.now().isoformat()
    )

    validators = [
        ('Extensions', validate_extensions),
        ('Function Languages', validate_function_languages),
        ('Data Types', validate_data_types),
        ('Indexes', validate_indexes),
        ('Constraints', validate_constraints),
        ('Tablespaces', validate_tablespaces),
        ('Row Level Security', validate_row_level_security),
    ]

    for name, validator in validators:
        print(f"  Checking {name}...")
        results = validator(conn)
        report.results.extend(results)

    conn.close()
    
    # Calculate totals
    for r in report.results:
        if r.status == 'OK':
            report.passed += 1
        elif r.status == 'WARNING':
            report.warnings += 1
        else:
            report.errors += 1
    
    # Generate report
    ext = {'text': '.txt', 'json': '.json', 'html': '.html'}[args.format]
    generate_report(report, args.format, f"{args.output}{ext}")
    
    # Print summary
    print(f"""
Validation Complete:
  ✅ Passed:   {report.passed}
  ⚠️  Warnings: {report.warnings}
  ❌ Errors:   {report.errors}
""")
    
    if report.errors > 0:
        print("⚠️  There are compatibility errors that must be resolved before migration.")
        sys.exit(1)
    elif report.warnings > 0:
        print("⚠️  Review warnings before proceeding with migration.")
        sys.exit(0)
    else:
        print("✅ Schema is compatible with Snowflake Postgres.")
        sys.exit(0)


if __name__ == '__main__':
    main()
