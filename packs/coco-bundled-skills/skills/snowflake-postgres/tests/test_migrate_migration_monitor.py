"""
Live tests for migration_monitor.py.

These tests are decorated with @pytest.mark.live and are skipped by default.
Pass --live to run them against a real Postgres pair. Override defaults with:

    PG_MIGRATE_LIVE_SOURCE_HOST       (default: source.example.invalid)
    PG_MIGRATE_LIVE_SOURCE_PORT       (default: 5432)
    PG_MIGRATE_LIVE_SOURCE_DB         (default: postgres)
    PG_MIGRATE_LIVE_SOURCE_USER       (default: postgres)
    PG_MIGRATE_LIVE_SOURCE_PASSWORD   (default: "")
    PG_MIGRATE_LIVE_TARGET_HOST       (default: target.example.invalid)
    PG_MIGRATE_LIVE_TARGET_PORT       (default: 5432)
    PG_MIGRATE_LIVE_TARGET_DB         (default: postgres)
    PG_MIGRATE_LIVE_TARGET_USER       (default: postgres)
    PG_MIGRATE_LIVE_TARGET_PASSWORD   (default: "")

When the env vars aren't set, the placeholder defaults are intentionally
non-existent so the connection step fails fast rather than silently running
against the wrong cluster.
"""
from __future__ import annotations

import os

import pytest

from migration_monitor import format_bytes, progress_bar
from pg_common import connect, query, scalar


# ---- env-var fixtures --------------------------------------------------


@pytest.fixture(scope="session")
def live_source_host() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_SOURCE_HOST", "source.example.invalid")


@pytest.fixture(scope="session")
def live_source_port() -> int:
    return int(os.environ.get("PG_MIGRATE_LIVE_SOURCE_PORT", "5432"))


@pytest.fixture(scope="session")
def live_source_db() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_SOURCE_DB", "postgres")


@pytest.fixture(scope="session")
def live_source_user() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_SOURCE_USER", "postgres")


@pytest.fixture(scope="session")
def live_source_password() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_SOURCE_PASSWORD", "")


@pytest.fixture(scope="session")
def live_target_host() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_TARGET_HOST", "target.example.invalid")


@pytest.fixture(scope="session")
def live_target_port() -> int:
    return int(os.environ.get("PG_MIGRATE_LIVE_TARGET_PORT", "5432"))


@pytest.fixture(scope="session")
def live_target_db() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_TARGET_DB", "postgres")


@pytest.fixture(scope="session")
def live_target_user() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_TARGET_USER", "postgres")


@pytest.fixture(scope="session")
def live_target_password() -> str:
    return os.environ.get("PG_MIGRATE_LIVE_TARGET_PASSWORD", "")


@pytest.fixture
def live_source_conn(live_source_host, live_source_port, live_source_db,
                     live_source_user, live_source_password):
    conn = connect(live_source_host, live_source_port, live_source_db,
                   live_source_user, live_source_password, None)
    conn.autocommit = True
    yield conn
    conn.close()


@pytest.fixture
def live_target_conn(live_target_host, live_target_port, live_target_db,
                     live_target_user, live_target_password):
    conn = connect(live_target_host, live_target_port, live_target_db,
                   live_target_user, live_target_password, None)
    conn.autocommit = True
    yield conn
    conn.close()


# ---- tests --------------------------------------------------------------


@pytest.mark.live
def test_sync_state_query_runs_on_target(live_target_conn):
    """The sync-progress query used by cmd_sync must execute without error
    against a live target and return a list of dict rows.

    NOTE: Snowflake Postgres denies SELECT on pg_subscription, so this query
    intentionally reads only from pg_subscription_rel (which IS accessible).
    Keep the shape in sync with cmd_sync — adding a join back to
    pg_subscription will break the live target run with permission denied.
    """
    rows = query(live_target_conn, """
        SELECT
            srrelid::regclass::text AS table_name,
            srsubstate AS state_code
        FROM pg_subscription_rel
        ORDER BY srsubstate, srrelid::regclass::text
    """)
    assert isinstance(rows, list)
    for row in rows:
        assert {"table_name", "state_code"}.issubset(row.keys())


@pytest.mark.live
def test_replication_slots_query_runs_on_source(live_source_conn):
    """The replication-lag query used by cmd_replication must execute
    against a live source and return iterable rows with expected columns."""
    rows = query(live_source_conn, """
        SELECT slot_name, active,
               pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn) AS lag_bytes,
               pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag_pretty
        FROM pg_replication_slots
        WHERE slot_type = 'logical'
    """)
    assert isinstance(rows, list)
    for row in rows:
        assert {"slot_name", "active", "lag_bytes", "lag_pretty"}.issubset(row.keys())


@pytest.mark.live
def test_dashboard_source_stats_query(live_source_conn):
    """The dashboard's source-side stats query returns size/tables/rows."""
    rows = query(live_source_conn, """
        SELECT pg_size_pretty(pg_database_size(current_database())) AS size,
               (SELECT count(*) FROM pg_stat_user_tables) AS tables,
               (SELECT coalesce(sum(n_live_tup), 0) FROM pg_stat_user_tables) AS rows
    """)
    assert len(rows) == 1
    assert {"size", "tables", "rows"}.issubset(rows[0].keys())


@pytest.mark.live
def test_row_progress_queries_both_sides(live_source_conn, live_target_conn):
    """cmd_row_progress pulls pg_stat_user_tables from source + target;
    both queries should execute and return lists of dicts."""
    src_rows = query(live_source_conn, """
        SELECT schemaname || '.' || relname AS table_name, n_live_tup AS rows
        FROM pg_stat_user_tables ORDER BY n_live_tup DESC
    """)
    tgt_rows = query(live_target_conn, """
        SELECT schemaname || '.' || relname AS table_name, n_live_tup AS rows
        FROM pg_stat_user_tables ORDER BY n_live_tup DESC
    """)
    assert isinstance(src_rows, list)
    assert isinstance(tgt_rows, list)


@pytest.mark.live
def test_format_helpers_behave_on_live_wal_size(live_source_conn):
    """format_bytes + progress_bar are pure-python, but we exercise them on
    a value pulled live from the source (pg_ls_waldir total size)."""
    wal_total = scalar(live_source_conn,
                       "SELECT coalesce(sum(size), 0) FROM pg_ls_waldir()")
    formatted = format_bytes(int(wal_total) if wal_total is not None else 0)
    assert isinstance(formatted, str) and formatted.split()[-1] in {
        "B", "KB", "MB", "GB", "TB", "PB"
    }
    bar = progress_bar(50)
    assert "50%" in bar and bar.startswith("[")
