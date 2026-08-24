"""
Live tests for test_connectivity.py.

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

Defaults are obvious placeholders; the live probes will fail fast on an
invalid host rather than silently running against the wrong cluster.
"""
from __future__ import annotations

import argparse
import os

import pytest
import test_connectivity as connectivity

# In the upstream layout these helpers were named test_* (pytest-auto-
# discoverable if imported by name). During T018 port we renamed them to
# probe_* in test_connectivity.py itself, so direct imports are fine here.
from test_connectivity import (
    probe_dns,
    probe_pg_connection,
    probe_source_replication,
    probe_target_to_source,
    probe_target_write,
    probe_tcp,
)


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
def live_args(live_source_host, live_source_port, live_source_db, live_source_user,
              live_source_password, live_target_host, live_target_port, live_target_db,
              live_target_user, live_target_password):
    """Emulate the argparse Namespace that test_connectivity.run_tests expects.

    The passwords are wired into the dedicated resolve_* fallbacks so the
    helpers in test_connectivity read them via the same code path as the
    real CLI.
    """
    return argparse.Namespace(
        host=live_source_host,
        port=live_source_port,
        dbname=live_source_db,
        user=live_source_user,
        password=live_source_password,
        sslmode=None,
        target_host=live_target_host,
        target_port=live_target_port,
        target_dbname=live_target_db,
        target_user=live_target_user,
        target_password=live_target_password,
        target_sslmode=None,
    )


# ---- tests --------------------------------------------------------------


def test_fdw_options_sql_quotes_literal_values():
    sql = connectivity._fdw_options_sql([
        ("host", "src.example.com"),
        ("dbname", "app'db"),
        ("sslmode", "verify-ca"),
    ])
    assert sql == "host 'src.example.com', dbname 'app''db', sslmode 'verify-ca'"
    assert "%s" not in sql


def test_probe_target_to_source_renders_literal_fdw_sql(monkeypatch):
    class DummyConn:
        autocommit = False

        def close(self):
            return None

    connect_calls = []
    query_calls = []
    conn = DummyConn()

    def fake_query(db_conn, sql, params=None):
        query_calls.append((sql, params))
        return []

    def fake_connect(*args, **kwargs):
        connect_calls.append((args, kwargs))
        return conn

    monkeypatch.setattr(connectivity, "connect", fake_connect)
    monkeypatch.setattr(connectivity, "query", fake_query)
    monkeypatch.setattr(connectivity, "scalar", lambda *args, **kwargs: 1)
    monkeypatch.setattr(connectivity, "resolve_target_password", lambda args: "targetpw")
    monkeypatch.setattr(connectivity, "resolve_source_password", lambda args: "src'p")

    args = argparse.Namespace(
        host="src.example.com",
        port=5432,
        dbname="appdb",
        user="replicator",
        password="",
        sslmode="verify-ca",
        hostaddr="203.0.113.10",
        sslrootcert="/tmp/source-ca.pem",
        target_host="target.example.com",
        target_port=5432,
        target_dbname="postgres",
        target_user="postgres",
        target_password="",
        target_sslmode="require",
        target_hostaddr="203.0.113.11",
        target_sslrootcert=None,
    )

    result = connectivity.probe_target_to_source(args, args)

    assert result["ok"] is True
    assert connect_calls[0][1]["hostaddr"] == "203.0.113.11"

    create_server_sql = next(
        sql for sql, _ in query_calls if "CREATE SERVER _migration_connectivity_test" in sql
    )
    assert "host 'src.example.com'" in create_server_sql
    assert "hostaddr '203.0.113.10'" in create_server_sql
    assert "dbname 'appdb'" in create_server_sql
    assert "sslmode 'verify-ca'" in create_server_sql
    assert "sslrootcert '/tmp/source-ca.pem'" in create_server_sql

    create_user_mapping_sql, create_user_mapping_params = next(
        (sql, params)
        for sql, params in query_calls
        if "CREATE USER MAPPING FOR CURRENT_USER" in sql
    )
    assert "password 'src''p'" in create_user_mapping_sql
    assert create_user_mapping_params is None


@pytest.mark.parametrize(
    ("stage", "expected_error"),
    [
        ("password", "target password resolution failed"),
        ("connect", "target connect failed"),
    ],
)
def test_probe_target_to_source_skips_cleanup_without_connection(
    monkeypatch, stage, expected_error
):
    query_calls = []
    connect_called = False

    def fake_query(db_conn, sql, params=None):
        query_calls.append((db_conn, sql, params))
        return []

    def fail_password(_args):
        raise RuntimeError("target password resolution failed")

    def fail_connect(*args, **kwargs):
        nonlocal connect_called
        connect_called = True
        raise RuntimeError("target connect failed")

    monkeypatch.setattr(connectivity, "query", fake_query)
    monkeypatch.setattr(connectivity, "resolve_source_password", lambda args: "srcpw")

    if stage == "password":
        monkeypatch.setattr(connectivity, "resolve_target_password", fail_password)
    else:
        monkeypatch.setattr(connectivity, "resolve_target_password", lambda args: "targetpw")
        monkeypatch.setattr(connectivity, "connect", fail_connect)

    args = argparse.Namespace(
        host="src.example.com",
        port=5432,
        dbname="appdb",
        user="replicator",
        password="",
        sslmode="require",
        sslrootcert=None,
        target_host="target.example.com",
        target_port=5432,
        target_dbname="postgres",
        target_user="postgres",
        target_password="",
        target_sslmode="require",
        target_sslrootcert=None,
    )

    result = connectivity.probe_target_to_source(args, args)

    assert result == {"ok": False, "error": expected_error}
    assert query_calls == []
    if stage == "password":
        assert connect_called is False
    else:
        assert connect_called is True


@pytest.mark.live
def test_dns_resolves_source_and_target(live_source_host, live_target_host):
    """test_dns returns a dict with ok/ip or ok=False/error; both forms valid."""
    src = probe_dns(live_source_host)
    tgt = probe_dns(live_target_host)
    assert "ok" in src and "ok" in tgt
    if src["ok"]:
        assert src.get("ip")
    if tgt["ok"]:
        assert tgt.get("ip")


@pytest.mark.live
def test_tcp_probe_returns_shape(live_source_host, live_source_port,
                                  live_target_host, live_target_port):
    """test_tcp attempts a real connect; we just assert the result shape."""
    src = probe_tcp(live_source_host, live_source_port, timeout=5)
    tgt = probe_tcp(live_target_host, live_target_port, timeout=5)
    assert "ok" in src and "ok" in tgt
    if not src["ok"]:
        assert "error" in src
    if not tgt["ok"]:
        assert "error" in tgt


@pytest.mark.live
def test_pg_connection_probe_against_target(live_target_host, live_target_port,
                                             live_target_db, live_target_user,
                                             live_target_password):
    """test_pg_connection returns a dict with label/host/port/dbname and ok."""
    result = probe_pg_connection(live_target_host, live_target_port, live_target_db,
                                 live_target_user, live_target_password, None, "TARGET")
    assert result["label"] == "TARGET"
    assert result["host"] == live_target_host
    assert result["dbname"] == live_target_db
    assert "ok" in result
    if result["ok"]:
        assert result.get("version")
        assert result.get("database") == live_target_db


@pytest.mark.live
def test_source_replication_readiness(live_source_host, live_source_port,
                                       live_source_db, live_source_user,
                                       live_source_password):
    """test_source_replication probes wal_level and slot counts on the source."""
    result = probe_source_replication(live_source_host, live_source_port, live_source_db,
                                      live_source_user, live_source_password, None)
    assert "ok" in result
    if result["ok"]:
        assert result["wal_level"] in {"logical", "replica", "minimal"}
        assert isinstance(result["max_replication_slots"], int)
        assert isinstance(result["used_replication_slots"], int)
        assert isinstance(result["user_has_replication"], bool)


@pytest.mark.live
def test_target_write_and_fdw_probe(live_args):
    """test_target_write creates + drops a probe table; test_target_to_source
    sets up and tears down a postgres_fdw server to verify the network
    path from target back to source.  Both return dicts with an 'ok' key."""
    wr = probe_target_write(live_args.target_host, live_args.target_port,
                           live_args.target_dbname, live_args.target_user,
                           live_args.target_password, live_args.target_sslmode)
    assert "ok" in wr
    if wr["ok"]:
        assert wr.get("write_ok") is True

    fdw = probe_target_to_source(live_args, live_args)
    assert "ok" in fdw
