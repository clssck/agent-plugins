"""Tests for the SnowflakeSession driver-agnostic shim.

Both backends are fully mocked so the tests run without a real Snowflake
account, without the connector wheel, and without `snow` on PATH. The
shim's contract is: same `list[dict]` shape from both backends with
lowercased column names, plus a clean error path when neither is
available.
"""
from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

import sf_session


class TestDetectSnowflakeBackend:
    def test_returns_connector_when_importable(self, monkeypatch):
        fake = MagicMock()
        monkeypatch.setitem(__import__("sys").modules, "snowflake", fake)
        monkeypatch.setitem(__import__("sys").modules, "snowflake.connector", fake.connector)
        assert sf_session.detect_snowflake_backend() == "connector"

    def test_returns_cli_when_connector_missing_but_snow_on_path(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "snowflake.connector" or name.startswith("snowflake.connector"):
                raise ImportError("no wheel for win_arm64")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        monkeypatch.setattr(sf_session.shutil, "which", lambda cmd: "/usr/local/bin/snow")
        assert sf_session.detect_snowflake_backend() == "cli"

    def test_returns_none_when_nothing_available(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "snowflake.connector" or name.startswith("snowflake.connector"):
                raise ImportError("no wheel for win_arm64")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        monkeypatch.setattr(sf_session.shutil, "which", lambda cmd: None)
        assert sf_session.detect_snowflake_backend() is None


class TestRequireSnowflakeBackend:
    def test_exits_when_no_backend_available(self, monkeypatch, capsys):
        monkeypatch.setattr(sf_session, "detect_snowflake_backend", lambda: None)
        with pytest.raises(SystemExit) as excinfo:
            sf_session.require_snowflake_backend()
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "no Snowflake backend available" in captured.err
        assert "snowflake-connector-python" in captured.err
        assert "snow CLI" in captured.err

    def test_returns_backend_when_available(self, monkeypatch):
        monkeypatch.setattr(sf_session, "detect_snowflake_backend", lambda: "cli")
        assert sf_session.require_snowflake_backend() == "cli"


class TestSnowflakeSessionConnectorBackend:
    """Connector path: holds one TCP connection open across .execute() calls."""

    def _make_session(self, monkeypatch, mock_conn):
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "connector")
        session = sf_session.SnowflakeSession(connection="prod", role="ADMIN")
        monkeypatch.setattr(session, "_open_connector_conn", lambda: mock_conn)
        return session

    def test_enter_opens_connection(self, monkeypatch):
        mock_conn = MagicMock()
        session = self._make_session(monkeypatch, mock_conn)
        with session as sf:
            assert sf.backend == "connector"
            assert sf._conn is mock_conn

    def test_exit_closes_connection(self, monkeypatch):
        mock_conn = MagicMock()
        session = self._make_session(monkeypatch, mock_conn)
        with session:
            pass
        mock_conn.close.assert_called_once()

    def test_execute_returns_lowercased_dicts(self, monkeypatch):
        mock_cur = MagicMock()
        mock_cur.description = [("PROPERTY",), ("VALUE",)]
        mock_cur.fetchall.return_value = [("state", "READY"), ("name", "myinst")]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        session = self._make_session(monkeypatch, mock_conn)
        with session as sf:
            rows = sf.execute("DESCRIBE POSTGRES INSTANCE myinst")

        assert rows == [
            {"property": "state", "value": "READY"},
            {"property": "name", "value": "myinst"},
        ]
        mock_cur.execute.assert_called_once_with("DESCRIBE POSTGRES INSTANCE myinst")

    def test_execute_returns_empty_for_no_rowset(self, monkeypatch):
        mock_cur = MagicMock()
        mock_cur.description = None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        session = self._make_session(monkeypatch, mock_conn)
        with session as sf:
            rows = sf.execute("ALTER POSTGRES INSTANCE myinst RESUME")

        assert rows == []

    def test_execute_outside_context_raises(self, monkeypatch):
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "connector")
        session = sf_session.SnowflakeSession(connection="prod")
        with pytest.raises(sf_session.SnowflakeError, match="context manager"):
            session.execute("SELECT 1")


class TestSnowflakeSessionCliBackend:
    """CLI path: shells out to `snow sql --format json` per .execute() call."""

    def _make_session(self, monkeypatch, **kwargs):
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        return sf_session.SnowflakeSession(**kwargs)

    def test_execute_invokes_snow_with_connection_and_role(self, monkeypatch):
        proc = MagicMock(returncode=0, stdout='[{"STATE": "READY"}]', stderr="")
        with patch.object(subprocess, "run", return_value=proc) as mock_run:
            session = self._make_session(monkeypatch, connection="prod", role="ADMIN")
            with session as sf:
                rows = sf.execute("DESCRIBE POSTGRES INSTANCE myinst")

        cmd = mock_run.call_args[0][0]
        assert cmd[:5] == ["snow", "sql", "--format", "json", "-q"]
        assert cmd[5] == "DESCRIBE POSTGRES INSTANCE myinst"
        assert "--connection" in cmd and "prod" in cmd
        assert "--role" in cmd and "ADMIN" in cmd
        assert rows == [{"state": "READY"}]

    def test_execute_omits_connection_flag_when_unset(self, monkeypatch):
        proc = MagicMock(returncode=0, stdout="[]", stderr="")
        with patch.object(subprocess, "run", return_value=proc) as mock_run:
            session = self._make_session(monkeypatch, connection=None, role=None)
            with session as sf:
                sf.execute("SELECT 1")
        cmd = mock_run.call_args[0][0]
        assert "--connection" not in cmd
        assert "--role" not in cmd

    def test_execute_empty_stdout_returns_empty_list(self, monkeypatch):
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(subprocess, "run", return_value=proc):
            session = self._make_session(monkeypatch, connection="prod")
            with session as sf:
                assert sf.execute("SELECT 1") == []

    def test_execute_non_zero_exit_raises_snowflake_error(self, monkeypatch):
        proc = MagicMock(returncode=2, stdout="", stderr="auth failed: invalid token\nblahblah\n")
        with patch.object(subprocess, "run", return_value=proc):
            session = self._make_session(monkeypatch, connection="prod")
            with session as sf:
                with pytest.raises(sf_session.SnowflakeError) as excinfo:
                    sf.execute("DESCRIBE POSTGRES INSTANCE myinst")
        err = excinfo.value
        assert err.backend == "cli"
        assert err.sql == "DESCRIBE POSTGRES INSTANCE myinst"
        assert "auth failed" in str(err)

    def test_execute_parses_banner_before_json(self, monkeypatch):
        """Some `snow` builds print a status banner before the JSON payload —
        the parser must skip past it rather than parse-bomb."""
        out = "Loading connection prod...\n[{\"COL_A\": 1, \"COL_B\": \"x\"}]"
        proc = MagicMock(returncode=0, stdout=out, stderr="")
        with patch.object(subprocess, "run", return_value=proc):
            session = self._make_session(monkeypatch, connection="prod")
            with session as sf:
                rows = sf.execute("SELECT 1")
        assert rows == [{"col_a": 1, "col_b": "x"}]


class TestParseSnowJson:
    """The CLI output parser is tolerant by design — assert the shapes it
    accepts so future `snow` version drift doesn't silently start dropping
    rows on the floor."""

    def test_array_of_objects(self):
        rows = sf_session._parse_snow_json('[{"A": 1, "B": 2}, {"A": 3, "B": 4}]')
        assert rows == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]

    def test_single_object_becomes_list(self):
        rows = sf_session._parse_snow_json('{"STATUS": "ok"}')
        assert rows == [{"status": "ok"}]

    def test_empty_array(self):
        assert sf_session._parse_snow_json("[]") == []

    def test_invalid_json_returns_empty(self):
        assert sf_session._parse_snow_json("not json at all") == []

    def test_scalar_payload_returns_empty(self):
        """e.g. snow returning a JSON number — we don't try to wrap scalars."""
        assert sf_session._parse_snow_json("42") == []


class TestOpenSnowflakeConnectionConnectorBackend:
    """Connector backend should return the underlying connector connection
    directly, not the adapter — gives callers full connector functionality."""

    def test_returns_underlying_connector_connection(self, monkeypatch):
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "connector")
        mock_conn = MagicMock(name="connector_conn")

        # Patch the lazy import path used by _open_connector_conn — pg_connect
        # is the auth-resolution module today.
        import sys as _sys
        fake_pg_connect = MagicMock()
        fake_pg_connect.get_snowflake_connection.return_value = mock_conn
        monkeypatch.setitem(_sys.modules, "pg_connect", fake_pg_connect)

        conn = sf_session.open_snowflake_connection(connection="prod", role="ADMIN")
        assert conn is mock_conn
        fake_pg_connect.get_snowflake_connection.assert_called_once_with(
            connection_name="prod", authenticator=None, role="ADMIN",
        )


class TestOpenSnowflakeConnectionCliBackend:
    """CLI backend should return the adapter so legacy `.cursor()` /
    `.fetchall()` / `.description` patterns keep working."""

    def test_returns_session_conn_adapter(self, monkeypatch):
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        conn = sf_session.open_snowflake_connection(connection="prod")
        try:
            assert isinstance(conn, sf_session._SessionConnAdapter)
        finally:
            conn.close()

    def test_cursor_execute_fetchall_round_trips_rows(self, monkeypatch):
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")

        proc = MagicMock(
            returncode=0,
            stdout='[{"NAME": "myinst", "STATE": "READY"}]',
            stderr="",
        )
        with patch.object(__import__("subprocess"), "run", return_value=proc):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("DESCRIBE POSTGRES INSTANCE myinst")
                    rows = cur.fetchall()
                    desc = cur.description
            finally:
                conn.close()

        # fetchall returns tuples in column order (lowercased names from
        # the snow CLI JSON output).
        assert rows == [("myinst", "READY")]
        # description shape matches DB-API: 7-tuples with name in [0].
        assert desc is not None
        assert [c[0] for c in desc] == ["name", "state"]
        assert all(len(c) == 7 for c in desc)

    def test_description_is_none_before_execute(self, monkeypatch):
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        conn = sf_session.open_snowflake_connection(connection="prod")
        try:
            with conn.cursor() as cur:
                assert cur.description is None
                assert cur.fetchall() == []
        finally:
            conn.close()

    def test_description_is_none_when_execute_returns_no_rowset(self, monkeypatch):
        """DDL (ALTER, DROP, etc.) returns no rows; description should remain None."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(__import__("subprocess"), "run", return_value=proc):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("ALTER POSTGRES INSTANCE myinst RESUME")
                    assert cur.fetchall() == []
                    assert cur.description is None
            finally:
                conn.close()

    def test_fetchone_returns_rows_one_at_a_time_then_none(self, monkeypatch):
        """fetchone pops rows from the front and returns None when drained.
        This matches DB-API semantics. Required for call sites like
        `pg_lake_catalog.cmd_describe_catalog_status` (SYSTEM$CATALOG_LINK_STATUS)
        that use fetchone for single-value lookups."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        proc = MagicMock(
            returncode=0,
            stdout='[{"STATUS": "linked"}, {"STATUS": "drifted"}]',
            stderr="",
        )
        with patch.object(__import__("subprocess"), "run", return_value=proc):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT SYSTEM$CATALOG_LINK_STATUS('db')")
                    first = cur.fetchone()
                    second = cur.fetchone()
                    third = cur.fetchone()
            finally:
                conn.close()
        assert first == ("linked",)
        assert second == ("drifted",)
        assert third is None

    def test_fetchone_returns_none_for_no_rowset(self, monkeypatch):
        """DDL / RESUME / etc. yield no rowset; fetchone must return None,
        not raise. pg_lake_catalog.cmd_describe_catalog_status guards on
        `status_row[0] if status_row else None` and relies on this."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        proc = MagicMock(returncode=0, stdout="", stderr="")
        with patch.object(__import__("subprocess"), "run", return_value=proc):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("ALTER POSTGRES INSTANCE x RESUME")
                    assert cur.fetchone() is None
            finally:
                conn.close()

    def test_fetchall_consumes_after_fetchone(self, monkeypatch):
        """fetchone drains from the front; fetchall returns only what's
        left. After full consumption, both return None / [] respectively."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        proc = MagicMock(
            returncode=0,
            stdout='[{"X": 1}, {"X": 2}, {"X": 3}]',
            stderr="",
        )
        with patch.object(__import__("subprocess"), "run", return_value=proc):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    first = cur.fetchone()
                    remaining = cur.fetchall()
                    after = cur.fetchall()
                    after_one = cur.fetchone()
            finally:
                conn.close()
        assert first == (1,)
        assert remaining == [(2,), (3,)]
        assert after == []
        assert after_one is None

    def test_description_survives_after_fetchall_drains_buffer(self, monkeypatch):
        """Real connector cursors keep `description` populated even after
        the rowset is consumed; the shim must do the same."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        proc = MagicMock(
            returncode=0,
            stdout='[{"NAME": "x", "STATE": "READY"}]',
            stderr="",
        )
        with patch.object(__import__("subprocess"), "run", return_value=proc):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT name, state FROM x")
                    cur.fetchall()  # drain
                    desc = cur.description
                    rows = cur.fetchall()  # no more rows
            finally:
                conn.close()
        assert desc is not None
        assert [c[0] for c in desc] == ["name", "state"]
        assert rows == []

    def test_second_execute_resets_cursor_state(self, monkeypatch):
        """pg_lake_catalog.cmd_describe_catalog_status does two executes on
        one cursor (SYSTEM$CATALOG_LINK_STATUS, then SHOW TABLES). The
        second execute must reset rowset + description, not append."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")

        proc_a = MagicMock(returncode=0, stdout='[{"STATUS": "linked"}]', stderr="")
        proc_b = MagicMock(
            returncode=0,
            stdout='[{"NAME": "t1"}, {"NAME": "t2"}]',
            stderr="",
        )
        with patch.object(__import__("subprocess"), "run", side_effect=[proc_a, proc_b]):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT SYSTEM$CATALOG_LINK_STATUS('db')")
                    status_row = cur.fetchone()

                    cur.execute("SHOW TABLES IN DATABASE db")
                    tables = cur.fetchall()
                    desc = cur.description
            finally:
                conn.close()
        assert status_row == ("linked",)
        assert tables == [("t1",), ("t2",)]
        assert desc is not None
        assert [c[0] for c in desc] == ["name"]

    def test_cursor_supports_iteration(self, monkeypatch):
        """`for row in cur:` (without explicit fetchall) is used by some
        call sites — network_policy_check.get_network_policy in particular."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")
        proc = MagicMock(
            returncode=0,
            stdout='[{"NAME": "a", "VALUE": "1"}, {"NAME": "b", "VALUE": "2"}]',
            stderr="",
        )
        with patch.object(__import__("subprocess"), "run", return_value=proc):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    collected = [row for row in cur]
            finally:
                conn.close()
        assert collected == [("a", "1"), ("b", "2")]

    def test_multiple_cursors_share_session(self, monkeypatch):
        """Each .cursor() call returns a fresh cursor adapter, but they
        all execute against the same underlying session so subprocess
        invocations are independent and don't share buffers."""
        monkeypatch.setattr(sf_session, "require_snowflake_backend", lambda: "cli")

        proc_a = MagicMock(returncode=0, stdout='[{"X": 1}]', stderr="")
        proc_b = MagicMock(returncode=0, stdout='[{"Y": 2}]', stderr="")
        with patch.object(__import__("subprocess"), "run", side_effect=[proc_a, proc_b]):
            conn = sf_session.open_snowflake_connection(connection="prod")
            try:
                cur1 = conn.cursor()
                cur2 = conn.cursor()
                cur1.execute("SELECT 1 AS x")
                cur2.execute("SELECT 2 AS y")
                # Each cursor has its own buffered rowset.
                assert cur1.fetchall() == [(1,)]
                assert cur2.fetchall() == [(2,)]
            finally:
                conn.close()


class TestExtractInstanceState:
    """Pin the _extract_instance_state helper in pg_connect against the two
    Snowflake response shapes for DESCRIBE POSTGRES INSTANCE."""

    def _extract(self, rows):
        import sys as _sys
        from pathlib import Path
        scripts = Path(__file__).resolve().parent.parent / "scripts"
        if str(scripts) not in _sys.path:
            _sys.path.insert(0, str(scripts))
        from pg_connect import _extract_instance_state
        return _extract_instance_state(rows)

    def test_property_value_shape(self):
        rows = [
            {"property": "name", "value": "myinst"},
            {"property": "state", "value": "ready"},
            {"property": "version", "value": "16"},
        ]
        assert self._extract(rows) == "READY"

    def test_flat_columns_shape(self):
        rows = [{"name": "myinst", "state": "Suspended", "version": "16"}]
        assert self._extract(rows) == "SUSPENDED"

    def test_empty_rows_returns_unknown(self):
        assert self._extract([]) == "UNKNOWN"

    def test_missing_state_column_returns_unknown(self):
        assert self._extract([{"name": "myinst", "version": "16"}]) == "UNKNOWN"
