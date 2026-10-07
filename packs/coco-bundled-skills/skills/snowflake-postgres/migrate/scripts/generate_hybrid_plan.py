#!/usr/bin/env python3
"""
generate_hybrid_plan.py
Generate a hybrid migration plan for databases with mixed replicable/non-replicable objects

Usage:
    python generate_hybrid_plan.py --host <host> --dbname <db> --user <user>
    python generate_hybrid_plan.py --source-service <source_service> --target-service <target_service>
    
Output:
    - HTML migration runbook
    - Shell script with commands
    - JSON plan file for automation
"""

import argparse
import json
import os
import shlex
import sys
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

# Resolve pg_common from the shared generic-PG layer at snowflake-postgres/scripts/shared/.
# pytest handles this via pythonpath; for direct invocation we add it to sys.path here.
from pathlib import Path as _P
_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))
from pg_common import (
    check_driver,
    connect,
    query,
    scalar,
    add_source_args,
    resolve_source_password,
    _apply_source_service,
    _apply_target_service,
    quote_ident,
)

@dataclass
class MigrationObject:
    """Represents an object to migrate"""
    schema: str
    name: str
    object_type: str
    size_bytes: int
    method: str  # 'logical_replication', 'pg_dump', 'copy', 'manual'
    reason: str
    order: int
    dependencies: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class MigrationPlan:
    """Complete migration plan"""
    database: str
    source_host: str
    target_host: str
    generated_at: str
    total_size_bytes: int
    complexity_score: int
    recommended_method: str
    dump_timing: str = 'now'
    phases: List[Dict[str, Any]] = field(default_factory=list)
    objects: List[MigrationObject] = field(default_factory=list)
    pre_migration_commands: List[str] = field(default_factory=list)
    post_migration_commands: List[str] = field(default_factory=list)
    validation_commands: List[str] = field(default_factory=list)


def _source_service_name(args: argparse.Namespace) -> str:
    return (getattr(args, "source_service", "") or "").strip()


def _target_service_name(args: argparse.Namespace) -> str:
    return (getattr(args, "target_service", "") or "").strip()


def _source_python_args(args: argparse.Namespace) -> str:
    source_service = _source_service_name(args)
    if source_service:
        return f"--source-service {shlex.quote(source_service)}"
    return (
        f"-H {shlex.quote(args.host)} -d {shlex.quote(args.dbname)} "
        f"-U {shlex.quote(args.user)}"
    )


def _target_python_args(args: argparse.Namespace) -> str:
    target_service = _target_service_name(args)
    if target_service:
        return f"--target-service {shlex.quote(target_service)}"
    return (
        "--target-host $TARGET_PGHOST --target-dbname $TARGET_PGDATABASE "
        "--target-user $TARGET_PGUSER"
    )


def _source_pg_dump_base(args: argparse.Namespace) -> str:
    source_service = _source_service_name(args)
    if source_service:
        return f"PGSERVICE={shlex.quote(source_service)} pg_dump"
    return (
        f"pg_dump -h {shlex.quote(args.host)} -U {shlex.quote(args.user)} "
        f"-d {shlex.quote(args.dbname)}"
    )


def _source_pg_dumpall_base(args: argparse.Namespace) -> str:
    source_service = _source_service_name(args)
    if source_service:
        return f"PGSERVICE={shlex.quote(source_service)} pg_dumpall"
    return (
        f"pg_dumpall -h {shlex.quote(args.host)} -p {shlex.quote(str(args.port))} "
        f"-U {shlex.quote(args.user)} --database={shlex.quote(args.dbname)}"
    )


def _target_psql_base(args: argparse.Namespace) -> str:
    # -X (=--no-psqlrc) prevents the user's ~/.psqlrc from flipping AUTOCOMMIT,
    # ON_ERROR_STOP, output format, etc. mid-migration. Required on every
    # generated psql line — see migrate/SKILL.md "Tool Usage Rules".
    target_service = _target_service_name(args)
    if target_service:
        return f"PGSERVICE={shlex.quote(target_service)} psql -X"
    return "psql -X -h $TARGET_PGHOST -d $TARGET_PGDATABASE -U $TARGET_PGUSER"


def _setup_replication_command(args: argparse.Namespace) -> str:
    return (
        "python migrate/scripts/setup_replication.py create-subscription "
        f"{_source_python_args(args)} "
        f"{_target_python_args(args)} "
        "--subscription-name migration_sub "
        "--publication-name migration_pub"
    )


def run_pg_query(conn, sql: str) -> List[Dict]:
    """Execute a PostgreSQL query and return results as list of dicts"""
    return query(conn, sql)


def get_blocker_analysis(conn, schemas=None) -> Dict[str, List]:
    """Analyze database for migration blockers"""
    schema_filter = ""
    if schemas:
        quoted = ", ".join(f"'{s}'" for s in schemas)
        schema_filter = f"AND n.nspname IN ({quoted})"
    blockers = {
        'unlogged_tables': [],
        'no_pk_tables': [],
        'inherited_tables': [],
        'inherited_children': [],
        'partitioned_tables': [],
        'foreign_tables': [],
        'large_objects': [],
        'materialized_views': [],
        'sequences': [],
        'replicable_tables': []
    }

    for r in run_pg_query(conn, """
        SELECT n.nspname AS schema, c.relname AS name, pg_total_relation_size(c.oid) AS size
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relpersistence = 'u' AND c.relkind = 'r'
        AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        {sf}
    """.format(sf=schema_filter)):
        blockers['unlogged_tables'].append({'schema': r['schema'], 'name': r['name'], 'size': int(r['size'] or 0)})

    for r in run_pg_query(conn, """
        SELECT n.nspname AS schema, c.relname AS name, pg_total_relation_size(c.oid) AS size, c.relreplident AS ri
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
        WHERE c.relkind = 'r' AND c.relpersistence = 'p'
        AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast') AND pk.oid IS NULL
        {sf}
    """.format(sf=schema_filter)):
        blockers['no_pk_tables'].append({'schema': r['schema'], 'name': r['name'], 'size': int(r['size'] or 0), 'replica_identity': r['ri']})

    # System-schema filter (matches the WHERE clause used by the other inventory
    # queries in this file) — without it, pg-internal inheritance from
    # pg_catalog/information_schema would surface as user data and skew
    # generate_hybrid_plan's method selection.
    for r in run_pg_query(conn, """
        SELECT DISTINCT pn.nspname AS schema, parent.relname AS name, pg_total_relation_size(parent.oid) AS size,
               (SELECT count(*) FROM pg_inherits WHERE inhparent = parent.oid) AS children,
               parent.relkind AS kind
        FROM pg_inherits JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_namespace pn ON pn.oid = parent.relnamespace
        WHERE parent.relkind IN ('r', 'p')
        AND pn.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        {schema_filter_pn}
    """.format(schema_filter_pn=schema_filter.replace('n.nspname', 'pn.nspname') if schema_filter else '')):
        entry = {'schema': r['schema'], 'name': r['name'], 'size': int(r['size'] or 0), 'children': int(r['children'] or 0)}
        if r['kind'] == 'p':
            blockers['partitioned_tables'].append(entry)
        else:
            blockers['inherited_tables'].append(entry)

    for r in run_pg_query(conn, """
        SELECT cn.nspname AS schema, child.relname AS name, pg_total_relation_size(child.oid) AS size,
               pn.nspname AS parent_schema, parent.relname AS parent_name,
               child.relkind AS kind,
               EXISTS (SELECT 1 FROM pg_constraint pk WHERE pk.conrelid = child.oid AND pk.contype = 'p') AS has_pk
        FROM pg_inherits
        JOIN pg_class child ON pg_inherits.inhrelid = child.oid
        JOIN pg_namespace cn ON cn.oid = child.relnamespace
        JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
        JOIN pg_namespace pn ON pn.oid = parent.relnamespace
        WHERE child.relkind = 'r'
          AND cn.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
          {schema_filter_cn}
    """.format(schema_filter_cn=schema_filter.replace('n.nspname', 'cn.nspname') if schema_filter else '')):
        blockers['inherited_children'].append({
            'schema': r['schema'], 'name': r['name'], 'size': int(r['size'] or 0),
            'parent': f"{r['parent_schema']}.{r['parent_name']}", 'has_pk': r['has_pk'],
        })

    for r in run_pg_query(conn, "SELECT foreign_table_schema AS schema, foreign_table_name AS name, foreign_server_name AS server FROM information_schema.foreign_tables"):
        blockers['foreign_tables'].append({'schema': r['schema'], 'name': r['name'], 'server': r['server']})

    try:
        lo = run_pg_query(conn, "SELECT count(*) AS cnt, COALESCE(sum(pg_lo_size(oid)), 0) AS sz FROM pg_largeobject_metadata")
        if lo:
            blockers['large_objects'] = [{'count': int(lo[0]['cnt'] or 0), 'size': int(lo[0]['sz'] or 0)}]
    except Exception:
        blockers['large_objects'] = [{'count': 0, 'size': 0}]

    for r in run_pg_query(conn, """
        SELECT n.nspname AS schema, c.relname AS name, pg_total_relation_size(c.oid) AS size
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.relkind = 'm'
        {sf}
    """.format(sf=schema_filter)):
        blockers['materialized_views'].append({'schema': r['schema'], 'name': r['name'], 'size': int(r['size'] or 0)})

    for r in run_pg_query(conn, """
        SELECT n.nspname AS schema, c.relname AS name, pg_sequence_last_value(c.oid) AS last_value
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S' AND n.nspname NOT IN ('pg_catalog', 'information_schema')
        {sf}
    """.format(sf=schema_filter)):
        blockers['sequences'].append({'schema': r['schema'], 'name': r['name'], 'last_value': int(r['last_value']) if r['last_value'] else 0})

    for r in run_pg_query(conn, """
        SELECT n.nspname AS schema, c.relname AS name, pg_total_relation_size(c.oid) AS size
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
        WHERE c.relkind = 'r' AND c.relpersistence = 'p'
        AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
        AND NOT EXISTS (SELECT 1 FROM pg_inherits WHERE inhparent = c.oid)
        {sf}
    """.format(sf=schema_filter)):
        blockers['replicable_tables'].append({'schema': r['schema'], 'name': r['name'], 'size': int(r['size'] or 0)})

    return blockers


def generate_plan(blockers: Dict, args: argparse.Namespace) -> MigrationPlan:
    """Generate the migration plan based on blocker analysis"""
    dump_timing = getattr(args, 'dump_timing', 'now')
    plan = MigrationPlan(
        database=args.dbname,
        source_host=args.host,
        target_host=args.target_host or 'snowflake-postgres.example.com',
        generated_at=datetime.now().isoformat(),
        total_size_bytes=0,
        complexity_score=0,
        recommended_method='hybrid',
        dump_timing=dump_timing
    )
    
    replicable_children = [c for c in blockers.get('inherited_children', []) if c.get('has_pk')]
    dump_children = [c for c in blockers.get('inherited_children', []) if not c.get('has_pk')]

    replicable_size = (
        sum(t['size'] for t in blockers['replicable_tables']) +
        sum(t['size'] for t in replicable_children)
    )
    non_replicable_size = (
        sum(t['size'] for t in blockers['unlogged_tables']) +
        sum(t['size'] for t in blockers['no_pk_tables']) +
        sum(t['size'] for t in blockers['inherited_tables']) +
        sum(t['size'] for t in dump_children)
    )
    
    plan.total_size_bytes = replicable_size + non_replicable_size
    
    plan.complexity_score = (
        len(blockers['unlogged_tables']) * 10 +
        len(blockers['no_pk_tables']) * 5 +
        len(blockers['inherited_tables']) * 8 +
        len(blockers.get('partitioned_tables', [])) * 2 +
        len(blockers.get('inherited_children', [])) * 2 +
        len(blockers['foreign_tables']) * 3 +
        (15 if blockers['large_objects'] and blockers['large_objects'][0]['count'] > 0 else 0) +
        len(blockers['materialized_views']) * 2
    )
    
    # Method selection is driven by COUNTS of non-replicable objects (an empty
    # unlogged table is still unloggable, regardless of size). Pre-fix we were
    # using `non_replicable_size == 0` which classified empty unlogged tables
    # as "logical replication" (they cannot replicate at all) and a 0-size
    # inheritance parent as "hybrid" (which it can be, but only via pg_dump,
    # not via mixed paths).
    has_inheritance = len(blockers['inherited_tables']) > 0
    has_unlogged = len(blockers['unlogged_tables']) > 0
    has_no_pk = len(blockers['no_pk_tables']) > 0
    has_dump_children = bool(dump_children)
    has_replicable = (len(blockers['replicable_tables']) > 0) or bool(replicable_children)

    has_non_replicable = has_inheritance or has_unlogged or has_no_pk or has_dump_children

    if not has_non_replicable:
        plan.recommended_method = 'logical_replication'
    elif not has_replicable:
        plan.recommended_method = 'pg_dump'
    else:
        plan.recommended_method = 'hybrid'
    
    # Generate phases
    phase_order = 0
    
    schema_names = [
        s.strip()
        for s in (getattr(args, 'schemas', None) or '').split(',')
        if s.strip()
    ]
    normalized_schemas = ",".join(schema_names)
    # Carry --schemas through to every generated command that supports it, so
    # a plan generated for a subset of schemas keeps that scope across
    # assessment + validation + schema dump. Without this, the plan-level
    # scope silently expands back to whole-database in the runbook. Normalize
    # away whitespace so emitted shell commands stay single-argument safe.
    schemas_arg = (
        f"--schemas {shlex.quote(normalized_schemas)} "
        if schema_names
        else ""
    )
    # pg_dump uses repeatable --schema=NAME (or -n NAME) flags rather than a
    # single comma-separated list, so build a separate string for it.
    pg_dump_schema_flags = (
        " ".join(f"--schema={shlex.quote(s)}" for s in schema_names)
        if schema_names
        else ""
    )
    sequence_schemas_arg = (
        f" --schemas {shlex.quote(normalized_schemas)}"
        if schema_names
        else ""
    )
    source_python_args = _source_python_args(args)
    target_python_args = _target_python_args(args)
    source_pg_dump_base = _source_pg_dump_base(args)
    source_pg_dumpall_base = _source_pg_dumpall_base(args)
    target_psql_base = _target_psql_base(args)

    # Phase 0: Pre-migration
    phase_order += 1
    pre_phase = {
        'phase': phase_order,
        'name': 'Pre-Migration Setup',
        'description': 'Configure source and target, verify connectivity',
        'pause_after': True,
        'pause_hint': 'Safe to pause. No replication or data transfer started yet.',
        'repeatable': True,
        'commands': [
            '# Verify connectivity (source + target):',
            f"python scripts/shared/test_connectivity.py "
            f"{source_python_args} {target_python_args}",
            '# Run full migration assessment:',
            f"python migrate/scripts/run_assessment.py "
            f"{source_python_args} "
            f"{schemas_arg}"
            "--html migration_assessment_report.html"
        ]
    }
    plan.phases.append(pre_phase)
    
    # Phase 1: Roles (if any)
    phase_order += 1
    roles_phase = {
        'phase': phase_order,
        'name': 'Migrate Roles (Optional)',
        'description': 'Export and import roles if needed',
        'pause_after': True,
        'pause_hint': 'Safe to pause. Roles are idempotent — re-running is harmless.',
        'repeatable': True,
        'commands': [
            f"{source_pg_dumpall_base} --globals-only --no-role-passwords -f globals.sql",
            "python ./scripts/filter_vendor_dump.py globals.sql > globals_clean.sql",
            f"# Apply to target: {target_psql_base} -f globals_clean.sql"
        ]
    }
    plan.phases.append(roles_phase)
    
    # Phase 2: Schema DDL
    phase_order += 1
    schema_phase = {
        'phase': phase_order,
        'name': 'Migrate Schema DDL',
        'description': 'Export and apply schema to target',
        'pause_after': True,
        'pause_hint': 'Safe to pause indefinitely. Schema is on target; no data transfer yet. This is a common pause point (days/weeks) before starting replication.',
        'repeatable': True,
        'commands': [
            f"{source_pg_dump_base} "
            f"{pg_dump_schema_flags + ' ' if pg_dump_schema_flags else ''}"
            f"--schema-only --no-owner -f schema.sql",
            "python ./scripts/filter_vendor_dump.py schema.sql > schema_clean.sql",
            f"# Apply: {target_psql_base} -f schema_clean.sql"
        ]
    }
    plan.phases.append(schema_phase)
    
    # Phase 3: Logical Replication for replicable tables
    has_partitioned = len(blockers.get('partitioned_tables', [])) > 0
    all_replicable = blockers['replicable_tables'] + replicable_children
    if all_replicable:
        phase_order += 1
        rep_tables = [f"{t['schema']}.{t['name']}" for t in all_replicable]
        pub_options = ""
        if has_partitioned:
            pub_options = " WITH (publish_via_partition_root = true)"
        publication_sql = f"CREATE PUBLICATION migration_pub FOR ALL TABLES{pub_options};"
        if schema_names:
            publication_tables = ", ".join(
                f"{quote_ident(t['schema'])}.{quote_ident(t['name'])}"
                for t in all_replicable
            )
            publication_sql = (
                f"CREATE PUBLICATION migration_pub FOR TABLE "
                f"{publication_tables}{pub_options};"
            )

        rep_phase = {
            'phase': phase_order,
            'name': 'Logical Replication',
            'description': f"Replicate {len(rep_tables)} tables via logical replication",
            'pause_after': True,
            'pause_hint': 'Safe to pause for days/weeks. Replication runs autonomously — initial sync completes and streaming continues without intervention. Monitor with: SELECT * FROM pg_stat_subscription;',
            'repeatable': False,
            'table_count': len(rep_tables),
            'total_size': sum(t['size'] for t in all_replicable),
            'commands': [
                "# On SOURCE:",
                publication_sql,
                "",
                "# On TARGET (safe DSN wrapper; uses service profiles when available):",
                _setup_replication_command(args),
            ]
        }
        if has_partitioned:
            rep_phase['commands'].insert(0, "# Partitioned tables replicate via leaf partitions (PG13+ native, PG10-12 via publish_via_partition_root)")
        plan.phases.append(rep_phase)
        
        for i, t in enumerate(all_replicable):
            is_child = t in replicable_children
            plan.objects.append(MigrationObject(
                schema=t['schema'],
                name=t['name'],
                object_type='partition_child' if is_child else 'table',
                size_bytes=t['size'],
                method='logical_replication',
                reason=f"Inherited child of {t.get('parent', '?')} with PK" if is_child else 'Has primary key, logged, not inherited',
                order=phase_order * 100 + i
            ))
        for i, t in enumerate(blockers.get('partitioned_tables', [])):
            plan.objects.append(MigrationObject(
                schema=t['schema'],
                name=t['name'],
                object_type='partitioned_parent',
                size_bytes=0,
                method='logical_replication',
                reason=f'Partitioned table with {t["children"]} partitions (leaf partitions replicate automatically)',
                order=phase_order * 100 + len(all_replicable) + i
            ))
    
    # Phase 4: pg_dump for non-replicable objects
    non_rep_objects = (
        blockers['unlogged_tables'] + 
        blockers['no_pk_tables'] +
        blockers['inherited_tables'] +
        dump_children
    )
    
    def build_dump_commands(blockers_data, dump_children_data, phase_num, plan_obj):
        """Build pg_dump commands and MigrationObjects for non-replicable tables"""
        commands = []
        for t in blockers_data['unlogged_tables']:
            table_fqn = "{}.{}".format(t['schema'], t['name'])
            commands.append(
                "{} -t {} --data-only | {}".format(
                    source_pg_dump_base,
                    shlex.quote(table_fqn),
                    target_psql_base,
                )
            )
            plan_obj.objects.append(MigrationObject(
                schema=t['schema'],
                name=t['name'],
                object_type='unlogged_table',
                size_bytes=t['size'],
                method='pg_dump',
                reason='Unlogged table - not in WAL',
                order=phase_num * 100
            ))
        
        for t in blockers_data['no_pk_tables']:
            table_fqn = "{}.{}".format(t['schema'], t['name'])
            commands.append(
                "{} -t {} --data-only | {}".format(
                    source_pg_dump_base,
                    shlex.quote(table_fqn),
                    target_psql_base,
                )
            )
            plan_obj.objects.append(MigrationObject(
                schema=t['schema'],
                name=t['name'],
                object_type='no_pk_table',
                size_bytes=t['size'],
                method='pg_dump',
                reason='No primary key - cannot use logical replication',
                order=phase_num * 100
            ))
        
        for t in blockers_data['inherited_tables']:
            table_fqn = "{}.{}".format(t['schema'], t['name'])
            commands.append(
                "# Inherited parent: {} -t {} --data-only | {}".format(
                    source_pg_dump_base,
                    shlex.quote(table_fqn),
                    target_psql_base,
                )
            )
            plan_obj.objects.append(MigrationObject(
                schema=t['schema'],
                name=t['name'],
                object_type='inherited_parent',
                size_bytes=t['size'],
                method='pg_dump',
                reason='Inheritance parent with {} children'.format(t["children"]),
                order=phase_num * 100
            ))

        for t in dump_children_data:
            table_fqn = "{}.{}".format(t['schema'], t['name'])
            commands.append(
                "# Child (no PK): {} -t {} --data-only | {}".format(
                    source_pg_dump_base,
                    shlex.quote(table_fqn),
                    target_psql_base,
                )
            )
            plan_obj.objects.append(MigrationObject(
                schema=t['schema'],
                name=t['name'],
                object_type='inherited_child',
                size_bytes=t['size'],
                method='pg_dump',
                reason='Inherited child of {} without PK'.format(t.get("parent", "?")),
                order=phase_num * 100
            ))
        return commands
    
    if non_rep_objects and dump_timing == 'now':
        phase_order += 1
        dump_phase = {
            'phase': phase_order,
            'name': 'pg_dump for Non-Replicable Objects',
            'description': "Dump {} objects that cannot use logical replication".format(len(non_rep_objects)),
            'pause_after': True,
            'pause_hint': 'Safe to pause. Dumped data is on target. Replication continues independently.',
            'repeatable': True,
            'repeat_hint': 'Re-running pg_dump overwrites previous data. Truncate target tables first if re-dumping.',
            'object_count': len(non_rep_objects),
            'commands': build_dump_commands(blockers, dump_children, phase_order, plan)
        }
        plan.phases.append(dump_phase)
    
    # Phase 5: Materialized views
    if blockers['materialized_views']:
        phase_order += 1
        mv_phase = {
            'phase': phase_order,
            'name': 'Recreate Materialized Views',
            'description': "Refresh {} materialized views".format(len(blockers['materialized_views'])),
            'pause_after': True,
            'pause_hint': 'Safe to pause. Materialized views can be refreshed again before cutover.',
            'repeatable': True,
            'repeat_hint': 'Repeat this phase to refresh materialized views with latest data before cutover.',
            'commands': ["REFRESH MATERIALIZED VIEW {};".format(
                            "{}.{}".format(quote_ident(mv['schema']), quote_ident(mv['name']))
                        )
                        for mv in blockers['materialized_views']]
        }
        plan.phases.append(mv_phase)
    
    # Phase 6: Sequences (and deferred dump if dump_timing=cutover)
    if blockers['sequences'] or (non_rep_objects and dump_timing == 'cutover'):
        phase_order += 1
        
        if non_rep_objects and dump_timing == 'cutover':
            cutover_commands = [
                "# ============================================",
                "# STOP WRITES on source before this phase",
                "# ============================================",
                ""
            ]
            cutover_commands.extend(build_dump_commands(blockers, dump_children, phase_order, plan))
            
            if blockers['sequences']:
                cutover_commands.extend([
                    "",
                    "# ============================================",
                    "# Sync sequences",
                    "# ============================================",
                    "# Generate sync SQL from source sequence values:",
                    "python migrate/scripts/cutover_tools.py sequences "
                    "{}{} -o seq_sync.sql".format(
                        source_python_args,
                        sequence_schemas_arg,
                    ),
                    "# Apply on target:",
                    f"{target_psql_base} -f seq_sync.sql"
                ])
            
            seq_phase = {
                'phase': phase_order,
                'name': 'Cutover: Dump Non-Replicable Objects + Sync Sequences',
                'description': "AFTER stopping writes: dump {} non-replicable objects and sync {} sequences".format(
                    len(non_rep_objects), len(blockers['sequences'])),
                'pause_after': False,
                'pause_hint': 'DO NOT pause here — writes are stopped. Proceed immediately to validation.',
                'repeatable': True,
                'repeat_hint': 'Safe to repeat if cutover is aborted. Re-dump and re-sync after stopping writes again.',
                'commands': cutover_commands
            }
        else:
            seq_phase = {
                'phase': phase_order,
                'name': 'Sync Sequences (FINAL STEP)',
                'description': "Sync {} sequences after cutover".format(len(blockers['sequences'])),
                'pause_after': False,
                'pause_hint': 'DO NOT pause here — writes are stopped. Proceed immediately to validation.',
                'repeatable': True,
                'repeat_hint': 'Safe to re-sync sequences. Values are read fresh from source each time.',
                'commands': [
                    "# Generate sync SQL from source sequence values:",
                    "python migrate/scripts/cutover_tools.py sequences "
                    "{}{} -o seq_sync.sql".format(
                        source_python_args,
                        sequence_schemas_arg,
                    ),
                    "# Apply on target AFTER stopping writes:",
                    f"{target_psql_base} -f seq_sync.sql"
                ]
            }
        plan.phases.append(seq_phase)
    
    # Phase 7: Validation
    phase_order += 1
    val_phase = {
        'phase': phase_order,
        'name': 'Validation',
        'description': 'Verify data integrity',
        'pause_after': True,
        'pause_hint': 'Safe to pause if replication is still active. If writes are stopped (cutover), minimize pause to reduce downtime.',
        'repeatable': True,
        'repeat_hint': 'Repeat validation as many times as needed. Run before cutover to verify, then again after cutover to confirm.',
        'commands': [
            "# Row counts (compares source vs target in one pass):",
            f"python migrate/scripts/validate_migration.py "
            f"{source_python_args} {target_python_args} "
            f"{schemas_arg}"
            "--mode exact --html validation.html",
            "# For deeper validation (checksums + numeric aggregates):",
            f"python migrate/scripts/validate_migration.py "
            f"{source_python_args} {target_python_args} "
            f"{schemas_arg}"
            "--mode full --html validation_full.html",
            "# Or use pgCompare for the deepest validation"
        ]
    }
    plan.phases.append(val_phase)
    
    return plan


def generate_html_report(plan: MigrationPlan, output_path: str):
    """Generate HTML runbook"""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Hybrid Migration Plan - {plan.database}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
        h2 {{ color: #333; margin-top: 30px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .summary-card {{ background: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center; }}
        .summary-card h3 {{ margin: 0 0 10px 0; color: #666; font-size: 14px; }}
        .summary-card .value {{ font-size: 28px; font-weight: bold; color: #1a73e8; }}
        .phase {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; margin: 20px 0; padding: 20px; }}
        .phase-header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 15px; }}
        .phase-number {{ background: #1a73e8; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; }}
        .phase-title {{ font-size: 18px; font-weight: bold; }}
        .commands {{ background: #1e1e1e; color: #d4d4d4; padding: 15px; border-radius: 4px; font-family: 'Monaco', 'Menlo', monospace; font-size: 13px; overflow-x: auto; white-space: pre; }}
        .object-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        .object-table th, .object-table td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        .object-table th {{ background: #f8f9fa; font-weight: 600; }}
        .method-tag {{ padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .method-logical {{ background: #e8f5e9; color: #2e7d32; }}
        .method-pgdump {{ background: #fff3e0; color: #ef6c00; }}
        .method-manual {{ background: #fce4ec; color: #c2185b; }}
        .complexity {{ padding: 10px 20px; border-radius: 4px; display: inline-block; font-weight: bold; }}
        .complexity-simple {{ background: #e8f5e9; color: #2e7d32; }}
        .complexity-moderate {{ background: #fff3e0; color: #ef6c00; }}
        .complexity-complex {{ background: #ffebee; color: #c62828; }}
        .phase-badges {{ display: flex; gap: 8px; margin-top: 6px; }}
        .badge {{ padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        .badge-pause {{ background: #e3f2fd; color: #1565c0; }}
        .badge-no-pause {{ background: #ffebee; color: #c62828; }}
        .badge-repeat {{ background: #f3e5f5; color: #7b1fa2; }}
        .pause-hint {{ font-size: 12px; color: #1565c0; margin-top: 8px; padding: 6px 10px; background: #e3f2fd; border-radius: 4px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🗄️ Hybrid Migration Plan</h1>
        <p><strong>Database:</strong> {plan.database} | <strong>Generated:</strong> {plan.generated_at}</p>
        
        <div class="summary">
            <div class="summary-card">
                <h3>Total Size</h3>
                <div class="value">{plan.total_size_bytes / (1024**3):.2f} GB</div>
            </div>
            <div class="summary-card">
                <h3>Complexity Score</h3>
                <div class="value">{plan.complexity_score}</div>
            </div>
            <div class="summary-card">
                <h3>Migration Method</h3>
                <div class="value">{plan.recommended_method.upper()}</div>
            </div>
            <div class="summary-card">
                <h3>Dump Timing</h3>
                <div class="value">{plan.dump_timing.upper()}</div>
            </div>
            <div class="summary-card">
                <h3>Total Phases</h3>
                <div class="value">{len(plan.phases)}</div>
            </div>
        </div>
        
        <h2>Migration Phases</h2>
"""
    
    for phase in plan.phases:
        badges = '<div class="phase-badges">'
        if phase.get('pause_after'):
            badges += '<span class="badge badge-pause">PAUSE OK</span>'
        else:
            badges += '<span class="badge badge-no-pause">NO PAUSE</span>'
        if phase.get('repeatable'):
            badges += '<span class="badge badge-repeat">REPEATABLE</span>'
        badges += '</div>'
        hint_html = ''
        if phase.get('pause_hint'):
            hint_html = f'<div class="pause-hint">{phase["pause_hint"]}</div>'
        if phase.get('repeat_hint'):
            hint_html += f'<div class="pause-hint" style="background:#f3e5f5;color:#7b1fa2;">{phase["repeat_hint"]}</div>'
        # f-strings prior to Python 3.12 forbid `\n` inside `{...}`, so the
        # join is computed first and then interpolated. The CSS sets
        # `white-space: pre`, so an actual newline renders as a line break.
        commands_block = '\n'.join(phase.get('commands', []))
        html += f"""
        <div class="phase">
            <div class="phase-header">
                <div class="phase-number">{phase['phase']}</div>
                <div>
                    <div class="phase-title">{phase['name']}</div>
                    <div style="color: #666; font-size: 14px;">{phase['description']}</div>
                    {badges}
                </div>
            </div>
            {hint_html}
            <div class="commands">{commands_block}</div>
        </div>
"""
    
    if plan.objects:
        html += """
        <h2>Objects by Migration Method</h2>
        <table class="object-table">
            <tr>
                <th>Schema.Object</th>
                <th>Type</th>
                <th>Size</th>
                <th>Method</th>
                <th>Reason</th>
            </tr>
"""
        for obj in sorted(plan.objects, key=lambda x: x.order):
            method_class = {
                'logical_replication': 'method-logical',
                'pg_dump': 'method-pgdump',
                'manual': 'method-manual'
            }.get(obj.method, 'method-manual')
            
            html += f"""
            <tr>
                <td>{obj.schema}.{obj.name}</td>
                <td>{obj.object_type}</td>
                <td>{obj.size_bytes / (1024**2):.2f} MB</td>
                <td><span class="method-tag {method_class}">{obj.method}</span></td>
                <td>{obj.reason}</td>
            </tr>
"""
        html += "</table>"
    
    html += """
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"HTML report generated: {output_path}")


def generate_shell_script(plan: MigrationPlan, output_path: str):
    """Generate executable shell script"""
    script = f"""#!/bin/bash
# =============================================================================
# Hybrid Migration Script - {plan.database}
# Generated: {plan.generated_at}
# =============================================================================
# This script executes the hybrid migration plan
# Review each step before running!
# =============================================================================

set -e

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  HYBRID MIGRATION: {plan.database:^56} ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"

source ~/.pg_migration_env

"""
    
    for phase in plan.phases:
        pause_line = ''
        if phase.get('pause_after'):
            pause_line = f"""echo ""
echo "    [PAUSE OK] {phase.get('pause_hint', 'Safe to pause after this phase.')}"
echo "    To resume later: update migration_state.yaml, then say 'resume migration'"
read -p "Press Enter to continue, or Ctrl+C to pause here..."
"""
        else:
            pause_line = 'read -p "Press Enter to continue or Ctrl+C to abort..."\n'
        repeat_note = ''
        if phase.get('repeatable'):
            repeat_note = f'echo "    [REPEATABLE] {phase.get("repeat_hint", "This phase can be safely re-run.")}"\n'
        script += f"""
# =============================================================================
# Phase {phase['phase']}: {phase['name']}
# =============================================================================
echo ""
echo ">>> Phase {phase['phase']}: {phase['name']}"
echo "    {phase['description']}"
{repeat_note}echo ""
{pause_line}
"""
        for cmd in phase.get('commands', []):
            if cmd.startswith('#'):
                script += f"echo \"{cmd}\"\n"
            elif cmd.strip():
                script += f"{cmd}\n"
    
    script += """
echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║  MIGRATION COMPLETE                                                          ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
"""
    
    with open(output_path, 'w') as f:
        f.write(script)

    # 0o700 (owner-only rwx) instead of 0o755 because operators often run the
    # generated script alongside owner-only service profiles / pgpass files, and
    # local hand-edits can still introduce secrets. Broader access should be an
    # explicit choice after review.
    os.chmod(output_path, 0o700)
    print(f"Shell script generated: {output_path} (permissions: 0700 — owner-only).")
    print("  NOTE: prefer service profiles / ~/.pgpass for credentials.")
    print("        Do not edit the generated commands to inline passwords unless")
    print("        you also keep the file owner-only and delete it after cutover.")


def main():
    parser = argparse.ArgumentParser(description='Generate hybrid migration plan')
    add_source_args(parser)
    parser.add_argument('--target-host', default=os.environ.get('TARGET_PGHOST', ''), help='Target Snowflake Postgres host')
    parser.add_argument('--target-service', default=os.environ.get('TARGET_PG_SERVICE', ''),
                        help='Optional target service name from ~/.pg_service.conf for plan metadata and emitted runbook commands')
    parser.add_argument('--output', '-o', default='migration_plan', help='Output base filename')
    parser.add_argument('--format', '-f', choices=['all', 'html', 'json', 'sh'], default='all',
                        help='Output format')
    parser.add_argument('--schemas', default=None,
                        help='Comma-separated list of schemas to include (default: all non-system schemas)')
    parser.add_argument('--dump-timing', choices=['now', 'cutover'], default='now',
                        help='When to dump non-replicable tables: now (during migration) or cutover (deferred to cutover phase with sequences)')

    args = parser.parse_args()
    check_driver()
    # Resolve --source-service NAME from ~/.pg_service.conf BEFORE validation.
    _apply_source_service(args)
    _apply_target_service(args)

    if not args.host or not args.dbname or not args.user:
        parser.error("Source connection params required (--host, --dbname, --user, OR --source-service NAME)")

    password = resolve_source_password(args)

    schemas = [s.strip() for s in args.schemas.split(',')] if args.schemas else None

    print(f"Analyzing database: {args.dbname} on {args.host}...")
    # sslrootcert is populated by _apply_source_service from --source-service's
    # ~/.pg_service.conf entry; forwarding it lets sslmode=verify-ca actually
    # verify against the per-instance CA instead of the system bundle.
    conn = connect(args.host, args.port, args.dbname, args.user, password, args.sslmode,
                   sslrootcert=getattr(args, 'sslrootcert', None),
                   hostaddr=getattr(args, 'hostaddr', None))
    conn.autocommit = True
    blockers = get_blocker_analysis(conn, schemas=schemas)
    conn.close()
    
    print("Generating migration plan...")
    plan = generate_plan(blockers, args)
    
    # Generate outputs
    if args.format in ('all', 'html'):
        generate_html_report(plan, f"{args.output}.html")
    
    if args.format in ('all', 'json'):
        with open(f"{args.output}.json", 'w') as f:
            json.dump({
                'database': plan.database,
                'source_host': plan.source_host,
                'target_host': plan.target_host,
                'generated_at': plan.generated_at,
                'total_size_bytes': plan.total_size_bytes,
                'complexity_score': plan.complexity_score,
                'recommended_method': plan.recommended_method,
                'dump_timing': plan.dump_timing,
                'phases': plan.phases,
                'objects': [
                    {
                        'schema': o.schema,
                        'name': o.name,
                        'type': o.object_type,
                        'size_bytes': o.size_bytes,
                        'method': o.method,
                        'reason': o.reason
                    }
                    for o in plan.objects
                ]
            }, f, indent=2)
        print(f"JSON plan generated: {args.output}.json")
    
    if args.format in ('all', 'sh'):
        generate_shell_script(plan, f"{args.output}.sh")
    
    print(f"""
Summary:
  Database: {plan.database}
  Total size: {plan.total_size_bytes / (1024**3):.2f} GB
  Complexity score: {plan.complexity_score}
  Recommended method: {plan.recommended_method}
  Dump timing: {plan.dump_timing}
  Phases: {len(plan.phases)}
  Objects: {len(plan.objects)}
""")


if __name__ == '__main__':
    main()
