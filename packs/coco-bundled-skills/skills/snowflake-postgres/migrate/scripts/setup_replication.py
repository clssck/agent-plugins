#!/usr/bin/env python3
"""
setup_replication.py
Set up logical replication from PostgreSQL source to Snowflake Postgres target
without leaking credentials to chat transcripts or shell history.

Why this exists
---------------
The upstream replicate/SKILL.md, large-db/SKILL.md, and rollback/SKILL.md
all show this pattern for CREATE SUBSCRIPTION:

    psql --no-psqlrc <<EOF
    CREATE SUBSCRIPTION migrate_from_source
    CONNECTION 'host=$SOURCE_PGHOST dbname=$SOURCE_PGDATABASE
                user=$SOURCE_PGUSER password=$SOURCE_PGPASSWORD sslmode=require'
    PUBLICATION snowflake_migration
    WITH (copy_data = true, create_slot = true);
    EOF

When an agent runs that command in a coco chat session, the literal command
text (including the env-var name being interpolated) ends up in the chat
transcript. If the agent has set $SOURCE_PGPASSWORD inside the chat session,
the password leaks. Even if the env var was set in a trusted shell beforehand,
the heredoc pattern still couples credential handling to the operator's
environment in fragile ways.

This script removes that coupling: source credentials resolve from ~/.pgpass
(via pg_common.resolve_source_password), the DSN is constructed in-process,
and the CREATE SUBSCRIPTION statement is executed via psycopg2 with the DSN
passed as a parameter — never echoed, never logged, never in argv.

Caveat we can NOT fix here
--------------------------
PostgreSQL's CREATE SUBSCRIPTION stores the connection string (including the
password) in the pg_subscription system catalog on the target. Anyone with
sufficient target-side privileges can SELECT it. That is a libpq subscription
protocol constraint, not something this script controls. The contribution
this script makes is removing the *additional* leakage paths through chat
transcripts, shell history, and process argv.

Subcommands
-----------
  create-subscription  Construct DSN in-process from --source-service /
                       ~/.pgpass and execute CREATE SUBSCRIPTION on target.
  drop-subscription    ALTER SUBSCRIPTION ... DISABLE then DROP SUBSCRIPTION.

Usage
-----
    # Forward replication (source -> target)
    uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \\
        create-subscription \\
        --source-service prod_source --target-service sf_target \\
        --subscription-name migrate_from_source \\
        --publication-name snowflake_migration

    # Reverse replication for rollback (target acts as source)
    uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \\
        create-subscription \\
        --source-service sf_target --target-service prod_source \\
        --subscription-name reverse_sub \\
        --publication-name reverse_pub \\
        --no-enabled

    # Drop subscription
    uv run --project <SKILL_DIR> python <SKILL_DIR>/migrate/scripts/setup_replication.py \\
        drop-subscription \\
        --target-service sf_target \\
        --subscription-name migrate_from_source
"""

import argparse
import os
import sys
from pathlib import Path as _P

_SHARED_DIR = _P(__file__).resolve().parent.parent.parent / "scripts" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from pg_common import (  # noqa: E402  — sys.path mutation must precede import
    check_driver,
    add_source_args,
    add_target_args,
    connect_target,
    resolve_source_password,
    _apply_source_service,
)


def _libpq_quote(value) -> str:
    """Quote a value per libpq DSN rules (PostgreSQL §34.1.1).

    Values containing whitespace, single quotes, or backslashes must be wrapped
    in single quotes, with embedded single quotes and backslashes escaped via
    backslash. Empty values must also be quoted (otherwise libpq parses the
    next `key=value` token as the value).

    Raw concatenation broke for any password / sslrootcert path containing
    spaces or quotes — those are common in real deployments (RDS-generated
    passwords with `+`/`/`, Windows-style cert paths copied across, paste
    errors with leading/trailing whitespace) and would silently corrupt the
    subscription DSN.
    """
    s = "" if value is None else str(value)
    if s == "" or any(c in s for c in " \t\r\n'\\"):
        s = s.replace("\\", "\\\\").replace("'", "\\'")
        return f"'{s}'"
    return s


def build_source_dsn(args, sslmode: str = "require", connect_timeout: int = 300) -> str:
    """Construct a libpq DSN string for the source connection.

    Resolves the password via ~/.pgpass (when --source-service is set) or via
    the legacy PGPASSWORD/SOURCE_PGPASSWORD env-var path. The returned string
    contains the literal password and is meant to be passed only into
    psycopg2.cursor.execute(...) as a parameter — never logged, never printed.

    sslmode defaults to 'require' (matches the upstream pattern); set to
    'verify-ca' for a stricter posture once you have the cert in place.

    sslrootcert is included when present on args (auto-populated from
    ~/.pg_service.conf via _apply_source_service when the source profile
    has a CA cert path). The receiving target's CREATE SUBSCRIPTION embeds
    this DSN verbatim, so the publisher-side libpq honors verify-ca/full
    against the source's CA chain.

    connect_timeout=300 (5 min) avoids premature timeout during initial slot
    creation for large databases. The libpq default of 60s is often too short.

    Each value is libpq-quoted so a password / cert path containing spaces or
    quotes doesn't corrupt the DSN.
    """
    _apply_source_service(args)
    pw = resolve_source_password(args)
    pairs = [
        ("host", args.host),
        ("port", args.port),
        ("dbname", args.dbname),
        ("user", args.user),
        ("password", pw),
        ("sslmode", sslmode),
        ("connect_timeout", connect_timeout),
    ]
    hostaddr = getattr(args, 'hostaddr', None)
    if hostaddr:
        pairs.insert(1, ("hostaddr", hostaddr))
    sslrootcert = getattr(args, 'sslrootcert', None)
    if sslrootcert:
        pairs.append(("sslrootcert", sslrootcert))
    return " ".join(f"{k}={_libpq_quote(v)}" for k, v in pairs)


def _safe_dsn_summary(args, sslmode: str = "require") -> str:
    """DSN summary safe to print: redacts the password."""
    return (
        f"host={args.host} port={args.port} dbname={args.dbname} "
        f"user={args.user} password=*** sslmode={sslmode}"
    )


def cmd_create_subscription(args) -> int:
    """CREATE SUBSCRIPTION on target with in-process DSN construction.

    The subscription identifier and publication identifier are quoted via
    psycopg2.sql.Identifier; the DSN is passed as a query parameter so libpq
    handles escaping. The resulting SQL never contains the password as a
    literal in the prepared statement source.
    """
    try:
        from psycopg2 import sql
    except ImportError:
        print(
            "[ERROR] setup_replication requires psycopg2 (the safe-DSN path uses "
            "psycopg2.sql.Identifier and parameterized DSN). Install with:\n"
            "    uv sync --project <SKILL_DIR>\n"
            "or fall back to the manual heredoc pattern from the SKILL.md "
            "appendix (not recommended in coco chat — leaks credentials)."
        )
        return 1

    # Resolve service profile first so args.sslmode (from ~/.pg_service.conf)
    # is populated before we pick the sslmode to embed in the subscription DSN.
    # Precedence: explicit --source-sslmode > service-profile sslmode > 'require'.
    # The prior code unconditionally used args.source_sslmode, whose argparse
    # default is 'require' — that silently downgraded a saved verify-ca source
    # profile to require unless the operator also passed --source-sslmode on
    # every invocation.
    _apply_source_service(args)
    sslmode = args.source_sslmode or getattr(args, 'sslmode', None) or 'require'
    dsn = build_source_dsn(args, sslmode=sslmode, connect_timeout=args.connect_timeout)

    target_conn = connect_target(args)
    target_conn.autocommit = True  # CREATE SUBSCRIPTION cannot run inside a tx block

    copy_data = "true" if args.copy_data else "false"
    create_slot = "true" if args.create_slot else "false"
    enabled = "true" if args.enabled else "false"

    stmt = sql.SQL(
        "CREATE SUBSCRIPTION {sub_name} CONNECTION %s "
        "PUBLICATION {pub_name} "
        "WITH (copy_data = {copy_data}, create_slot = {create_slot}, enabled = {enabled})"
    ).format(
        sub_name=sql.Identifier(args.subscription_name),
        pub_name=sql.Identifier(args.publication_name),
        copy_data=sql.SQL(copy_data),
        create_slot=sql.SQL(create_slot),
        enabled=sql.SQL(enabled),
    )

    print(f"Creating subscription '{args.subscription_name}' on target...")
    print(f"  source: {_safe_dsn_summary(args, sslmode=sslmode)}")
    print(f"  publication: {args.publication_name}")
    print(f"  copy_data: {copy_data}, create_slot: {create_slot}, enabled: {enabled}")

    cur = target_conn.cursor()
    try:
        cur.execute(stmt, (dsn,))
        print(f"[OK] subscription '{args.subscription_name}' created.")
        return 0
    except Exception as e:
        print(f"[ERROR] CREATE SUBSCRIPTION failed: {e}")
        return 1
    finally:
        target_conn.close()


def cmd_drop_subscription(args) -> int:
    """Drop a subscription on target with publisher-state-resilient fallback.

    Tries the clean path first: DROP SUBSCRIPTION drops the remote slot
    atomically when the publisher is reachable. On failure (typically
    publisher unreachable), falls back to disassociate-then-drop, which is
    local to the target catalog and orphans the slot on the publisher.
    To keep the Snowflake Postgres target path portable across accounts /
    releases, the script does not depend on reading pg_subscription for slot-
    name lookup. Recovery guidance therefore points the operator at
    pg_replication_slots on the source side.
    """
    try:
        from psycopg2 import sql
    except ImportError:
        print("[ERROR] setup_replication requires psycopg2.")
        return 1

    target_conn = connect_target(args)
    target_conn.autocommit = True
    try:
        cur = target_conn.cursor()
        sub_ident = sql.Identifier(args.subscription_name)
        sub_name_lit = args.subscription_name

        print(f"Dropping subscription '{sub_name_lit}'...")
        try:
            cur.execute(sql.SQL("DROP SUBSCRIPTION IF EXISTS {}").format(sub_ident))
            print(f"[OK] subscription '{sub_name_lit}' dropped.")
            return 0
        except Exception as first_error:
            print(f"[WARN] DROP SUBSCRIPTION failed: {first_error}")
            print("[INFO] Falling back to DISABLE + slot_name=NONE + DROP (orphans slot on publisher)")

        try:
            cur.execute(sql.SQL("ALTER SUBSCRIPTION {} DISABLE").format(sub_ident))
            cur.execute(sql.SQL("ALTER SUBSCRIPTION {} SET (slot_name = NONE)").format(sub_ident))
            cur.execute(sql.SQL("DROP SUBSCRIPTION {}").format(sub_ident))
            print(f"[OK] subscription '{sub_name_lit}' dropped via fallback.")
            print(
                "[NOTE] A source-side replication slot may now be orphaned on the "
                "publisher. Inspect pg_replication_slots on the source and drop it "
                "manually if needed: SELECT pg_drop_replication_slot('<slot_name>');"
            )
            return 0
        except Exception as second_error:
            print(f"[ERROR] Fallback DROP also failed: {second_error}")
            print(
                f"[ACTION] Manual recovery on target: "
                f"ALTER SUBSCRIPTION {sub_name_lit} DISABLE; "
                f"ALTER SUBSCRIPTION {sub_name_lit} SET (slot_name = NONE); "
                f"DROP SUBSCRIPTION {sub_name_lit};"
            )
            print(
                "[ACTION] Then on source: inspect pg_replication_slots for the "
                "orphaned logical slot and drop it manually with "
                "SELECT pg_drop_replication_slot('<slot_name>');"
            )
            return 1
    finally:
        target_conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Set up logical replication safely. Source credentials resolve "
            "from ~/.pgpass via --source-service; passwords never appear on "
            "the command line, in shell history, or in chat transcripts."
        )
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_create = sub.add_parser(
        "create-subscription",
        help="Create CREATE SUBSCRIPTION with in-process DSN construction",
    )
    add_source_args(p_create)
    add_target_args(p_create)
    p_create.add_argument("--subscription-name", required=True, help="Name for the new subscription")
    p_create.add_argument("--publication-name", required=True, help="Name of the existing publication on source")
    p_create.add_argument(
        "--source-sslmode",
        default=os.environ.get("SOURCE_PGSSLMODE"),
        help="sslmode for the source DSN written into the subscription. "
             "If omitted, falls back to the sslmode in --source-service's "
             "~/.pg_service.conf entry, then to 'require'. Pass explicitly "
             "to override the service profile (e.g. for a one-off downgrade).",
    )
    p_create.add_argument(
        "--connect-timeout",
        type=int,
        default=300,
        help="connect_timeout seconds for the source DSN (default: 300, generous for slot creation on large DBs)",
    )
    p_create.add_argument("--copy-data", dest="copy_data", action="store_true")
    p_create.add_argument("--no-copy-data", dest="copy_data", action="store_false")
    p_create.add_argument("--create-slot", dest="create_slot", action="store_true")
    p_create.add_argument("--no-create-slot", dest="create_slot", action="store_false")
    p_create.add_argument("--enabled", dest="enabled", action="store_true")
    p_create.add_argument("--no-enabled", dest="enabled", action="store_false")
    p_create.set_defaults(copy_data=True, create_slot=True, enabled=True, func=cmd_create_subscription)

    p_drop = sub.add_parser("drop-subscription", help="Disable + drop a subscription on target")
    add_target_args(p_drop)
    p_drop.add_argument("--subscription-name", required=True)
    p_drop.set_defaults(func=cmd_drop_subscription)

    return parser


def main() -> int:
    check_driver()
    args = build_parser().parse_args()
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
