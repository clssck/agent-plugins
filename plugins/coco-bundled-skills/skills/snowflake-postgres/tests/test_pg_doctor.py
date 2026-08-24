"""
Unit tests for pg_doctor.py.

Tests evaluator functions, check registry, SQL file loading, and output
formatting. No live Postgres connection required — psycopg2 is mocked.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

# Ensure scripts directory is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pg_doctor import (
    CHECKS,
    SQL_DIR,
    connect_readonly,
    evaluate_bloat,
    evaluate_blocking,
    evaluate_cache_hit,
    evaluate_connections,
    evaluate_locks,
    evaluate_long_running,
    evaluate_outliers,
    evaluate_table_sizes,
    evaluate_unused_indexes,
    evaluate_vacuum_stats,
    format_detailed,
    format_json,
    format_summary,
    get_all_checks,
    get_checks_for_category,
    load_sql,
    run_check,
    status_icon,
)


# ---------------------------------------------------------------------------
# Check registry completeness
# ---------------------------------------------------------------------------

class TestCheckRegistry:
    """Verify the CHECKS registry is complete and well-formed."""

    EXPECTED_CHECKS = [
        "cache_hit", "bloat", "vacuum_stats", "connections",
        "locks", "blocking", "long_running", "outliers",
        "unused_indexes", "table_sizes",
    ]

    def test_all_checks_registered(self):
        for name in self.EXPECTED_CHECKS:
            assert name in CHECKS, f"Check '{name}' missing from registry"

    def test_registry_count(self):
        assert len(CHECKS) == 10

    def test_each_check_has_required_keys(self):
        for name, info in CHECKS.items():
            assert "category" in info, f"{name} missing 'category'"
            assert "description" in info, f"{name} missing 'description'"
            assert "evaluate" in info, f"{name} missing 'evaluate'"
            assert callable(info["evaluate"]), f"{name} 'evaluate' not callable"

    def test_all_checks_are_health_category(self):
        for name, info in CHECKS.items():
            assert info["category"] == "health"

    def test_get_checks_for_category(self):
        health = get_checks_for_category("health")
        assert len(health) == 10
        assert set(health) == set(self.EXPECTED_CHECKS)

    def test_get_checks_for_unknown_category(self):
        assert get_checks_for_category("nonexistent") == []

    def test_get_all_checks(self):
        assert len(get_all_checks()) == 10


# ---------------------------------------------------------------------------
# SQL file loading
# ---------------------------------------------------------------------------

class TestLoadSQL:
    """Verify SQL files exist and are loadable."""

    EXPECTED_FILES = [
        "bloat.sql", "blocking.sql", "cache_hit.sql", "connections.sql",
        "locks.sql", "long_running.sql", "outliers.sql", "vacuum_stats.sql",
        "unused_indexes.sql", "table_sizes.sql",
    ]

    def test_sql_dir_exists(self):
        assert SQL_DIR.exists(), f"SQL directory not found: {SQL_DIR}"

    def test_all_sql_files_exist(self):
        for filename in self.EXPECTED_FILES:
            filepath = SQL_DIR / filename
            assert filepath.exists(), f"Missing SQL file: {filepath}"

    def test_load_sql_returns_content(self):
        sql = load_sql("cache_hit")
        assert "pg_statio_user_indexes" in sql

    def test_load_sql_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_sql("nonexistent_check")

    def test_each_registered_check_has_sql_file(self):
        for name in CHECKS:
            sql = load_sql(name)
            assert len(sql) > 0, f"SQL file for '{name}' is empty"


# ---------------------------------------------------------------------------
# Evaluator functions
# ---------------------------------------------------------------------------

class TestEvaluateCacheHit:
    def test_good(self):
        rows = [["index hit rate", 0.998], ["table hit rate", 0.995]]
        status, msg = evaluate_cache_hit(rows, ["name", "ratio"])
        assert status == "good"
        assert "table hit rate" in msg
        assert "99.5%" in msg

    def test_warning(self):
        rows = [["index hit rate", 0.97], ["table hit rate", 0.96]]
        status, msg = evaluate_cache_hit(rows, ["name", "ratio"])
        assert status == "warning"
        assert "table hit rate" in msg

    def test_critical(self):
        rows = [["index hit rate", 0.80], ["table hit rate", 0.85]]
        status, msg = evaluate_cache_hit(rows, ["name", "ratio"])
        assert status == "critical"
        assert "index hit rate" in msg

    def test_empty_rows(self):
        status, msg = evaluate_cache_hit([], ["name", "ratio"])
        assert status == "warning"
        assert "No cache data" in msg

    def test_null_ratios(self):
        rows = [["index hit rate", None], ["table hit rate", None]]
        status, msg = evaluate_cache_hit(rows, ["name", "ratio"])
        assert status == "warning"


class TestEvaluateBloat:
    def test_good(self):
        rows = [["table", "public", "users", 1.1, "8192 bytes"]]
        status, msg = evaluate_bloat(rows, ["type", "schema", "name", "bloat", "waste"])
        assert status == "good"

    def test_warning(self):
        rows = [["table", "public", "users", 1.4, "64 kB"]]
        status, _ = evaluate_bloat(rows, [])
        assert status == "warning"

    def test_warning_boundary(self):
        """Exactly 1.5x (50% bloat) should be warning, not critical."""
        rows = [["table", "public", "users", 1.5, "96 kB"]]
        status, _ = evaluate_bloat(rows, [])
        assert status == "warning"

    def test_critical(self):
        rows = [["table", "public", "users", 2.0, "128 kB"]]
        status, _ = evaluate_bloat(rows, [])
        assert status == "critical"

    def test_empty(self):
        status, msg = evaluate_bloat([], [])
        assert status == "good"
        assert "No bloat" in msg

    def test_null_ratios(self):
        rows = [["table", "public", "users", None, "0 bytes"]]
        status, _ = evaluate_bloat(rows, [])
        assert status == "good"


class TestEvaluateVacuumStats:
    def test_healthy(self):
        rows = [["public", "users", "2026-01-01", "2026-01-02", "10", "1000", "250", None]]
        status, _ = evaluate_vacuum_stats(rows, [])
        assert status == "good"

    def test_needs_vacuum(self):
        rows = [["public", "users", "2026-01-01", "2026-01-02", "500", "1000", "250", "yes"]]
        status, msg = evaluate_vacuum_stats(rows, [])
        assert status == "warning"
        assert "1 table(s)" in msg

    def test_multiple_needing_vacuum(self):
        rows = [
            ["public", "t1", None, None, "500", "100", "50", "yes"],
            ["public", "t2", None, None, "300", "100", "50", "yes"],
            ["public", "t3", None, None, "10", "1000", "250", None],
        ]
        status, msg = evaluate_vacuum_stats(rows, [])
        assert status == "warning"
        assert "2 table(s)" in msg

    def test_empty(self):
        status, _ = evaluate_vacuum_stats([], [])
        assert status == "good"


class TestEvaluateConnections:
    def test_counts(self):
        rows = [[15, "app_user"], [3, "admin"]]
        status, msg = evaluate_connections(rows, [])
        assert status == "good"
        assert "18" in msg

    def test_empty(self):
        status, msg = evaluate_connections([], [])
        assert status == "good"
        assert "0" in msg


class TestEvaluateLocks:
    def test_no_locks(self):
        status, _ = evaluate_locks([], [])
        assert status == "good"

    def test_locks_present(self):
        rows = [[123, "users", 456, True, "SELECT ...", "00:01:30"]]
        status, msg = evaluate_locks(rows, [])
        assert status == "warning"
        assert "1" in msg


class TestEvaluateBlocking:
    def test_no_blocking(self):
        status, _ = evaluate_blocking([], [])
        assert status == "good"

    def test_blocking_present(self):
        rows = [[1, "UPDATE ...", "00:00:30", 2, "SELECT ...", "00:00:25"]]
        status, msg = evaluate_blocking(rows, [])
        assert status == "critical"
        assert "1" in msg


class TestEvaluateLongRunning:
    def test_none(self):
        status, _ = evaluate_long_running([], [])
        assert status == "good"

    def test_long_queries(self):
        rows = [[100, "00:15:00", "SELECT pg_sleep(900)"]]
        status, msg = evaluate_long_running(rows, [])
        assert status == "warning"


class TestEvaluateOutliers:
    def test_informational(self):
        rows = [["00:05:00", "45.2%", "1,234", "N/A", "SELECT ..."]] * 5
        status, msg = evaluate_outliers(rows, [])
        assert status == "good"
        assert "5" in msg


class TestEvaluateUnusedIndexes:
    def test_none(self):
        status, msg = evaluate_unused_indexes([], [])
        assert status == "good"
        assert "No unused" in msg

    def test_some_found(self):
        rows = [
            ["public", "users", "idx_users_old", "64 kB"],
            ["public", "orders", "idx_orders_legacy", "128 kB"],
        ]
        status, msg = evaluate_unused_indexes(rows, [])
        assert status == "warning"
        assert "2" in msg


class TestEvaluateTableSizes:
    def test_no_tables(self):
        status, msg = evaluate_table_sizes([], [])
        assert status == "good"

    def test_tables_present(self):
        rows = [
            ["public", "users", 1000, "128 kB", "32 kB", "0 bytes", "96 kB"],
            ["public", "orders", 500, "64 kB", "16 kB", "0 bytes", "48 kB"],
        ]
        status, msg = evaluate_table_sizes(rows, [])
        assert status == "good"
        assert "2" in msg


# ---------------------------------------------------------------------------
# run_check (with mocked connection)
# ---------------------------------------------------------------------------

class TestRunCheck:
    def _mock_conn(self, rows, columns):
        """Create a mock connection that returns given rows/columns."""
        mock_cur = MagicMock()
        mock_cur.description = [(col,) for col in columns]
        mock_cur.fetchall.return_value = [tuple(r) for r in rows]
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        return mock_conn

    def test_run_known_check(self):
        conn = self._mock_conn(
            [["index hit rate", 0.998], ["table hit rate", 0.995]],
            ["name", "ratio"],
        )
        result = run_check(conn, "cache_hit")
        assert result["name"] == "cache_hit"
        assert result["status"] == "good"
        assert len(result["rows"]) == 2

    def test_run_unknown_check(self):
        conn = self._mock_conn([], [])
        result = run_check(conn, "nonexistent")
        assert result["status"] == "critical"
        assert "Unknown check" in result["message"]

    def test_run_check_query_error(self):
        import psycopg2
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = psycopg2.Error("relation does not exist")
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        result = run_check(mock_conn, "cache_hit")
        assert result["status"] == "critical"
        assert "Query error" in result["message"]

    def test_run_outliers_missing_pg_stat_statements_is_warning(self):
        import psycopg2
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = psycopg2.Error(
            'relation "pg_stat_statements" does not exist'
        )
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        result = run_check(mock_conn, "outliers")
        assert result["status"] == "warning"
        assert "pg_stat_statements not enabled" in result["message"]

    def test_run_outliers_shared_preload_error_is_warning(self):
        import psycopg2
        mock_cur = MagicMock()
        mock_cur.execute.side_effect = psycopg2.Error(
            "pg_stat_statements must be loaded via shared_preload_libraries"
        )
        mock_cur.__enter__ = MagicMock(return_value=mock_cur)
        mock_cur.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        result = run_check(mock_conn, "outliers")
        assert result["status"] == "warning"
        assert "pg_stat_statements not enabled" in result["message"]


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

class TestFormatting:
    SAMPLE_RESULTS = [
        {"name": "cache_hit", "status": "good", "message": "Min hit rate: 99.5%", "rows": [], "columns": []},
        {"name": "bloat", "status": "warning", "message": "Max bloat: 1.4x", "rows": [], "columns": []},
        {"name": "blocking", "status": "critical", "message": "2 blocked queries", "rows": [], "columns": []},
    ]

    def test_format_summary(self):
        output = format_summary(self.SAMPLE_RESULTS)
        assert "cache_hit" in output
        assert "bloat" in output
        assert "blocking" in output

    def test_format_detailed(self):
        output = format_detailed(self.SAMPLE_RESULTS)
        assert "CACHE_HIT" in output
        assert "BLOAT" in output
        assert "Status: good" in output

    def test_format_json(self):
        output = format_json(self.SAMPLE_RESULTS)
        parsed = json.loads(output)
        assert parsed["success"] is True
        assert len(parsed["results"]) == 3

    def test_format_json_failure(self):
        output = format_json([], success=False)
        parsed = json.loads(output)
        assert parsed["success"] is False


# ---------------------------------------------------------------------------
# Connection options
# ---------------------------------------------------------------------------

class TestConnectionOptions:
    @patch("pg_common.connect")
    def test_readonly_and_timeout_set(self, mock_connect):
        mock_connect.return_value = MagicMock()
        params = {
            "host": "localhost",
            "port": 5432,
            "database": "postgres",
            "user": "admin",
            "password": "secret",
            "sslmode": "require",
        }
        connect_readonly(params, statement_timeout_ms=30000)
        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args[1]
        assert "default_transaction_read_only=on" in call_kwargs["options"]
        assert "statement_timeout=30000" in call_kwargs["options"]
        assert call_kwargs["sslmode"] == "require"
        assert call_kwargs["sslrootcert"] is None

    @patch("pg_common.connect")
    def test_custom_timeout(self, mock_connect):
        mock_connect.return_value = MagicMock()
        params = {
            "host": "localhost", "port": 5432, "database": "postgres",
            "user": "admin", "sslmode": "require",
        }
        connect_readonly(params, statement_timeout_ms=60000)
        call_kwargs = mock_connect.call_args[1]
        assert "statement_timeout=60000" in call_kwargs["options"]

    @patch("pg_common.connect")
    def test_sslrootcert_passed_when_present(self, mock_connect):
        """When params include sslrootcert (cert support), pass it through."""
        mock_connect.return_value = MagicMock()
        params = {
            "host": "localhost", "port": 5432, "database": "postgres",
            "user": "admin", "sslmode": "verify-ca",
            "sslrootcert": "/home/user/.snowflake/postgres/certs/acct.pem",
        }
        connect_readonly(params)
        call_kwargs = mock_connect.call_args[1]
        assert call_kwargs["sslrootcert"] == "/home/user/.snowflake/postgres/certs/acct.pem"
        assert call_kwargs["sslmode"] == "verify-ca"


# ---------------------------------------------------------------------------
# Status icons
# ---------------------------------------------------------------------------

class TestStatusIcon:
    def test_known_statuses(self):
        assert status_icon("good") == "✅"
        assert status_icon("warning") == "⚠️"
        assert status_icon("critical") == "❌"
        assert status_icon("unknown") == "❓"

    def test_unknown_status(self):
        assert status_icon("bogus") == "❓"


# ---------------------------------------------------------------------------
# Transaction isolation (cascade fix)
# ---------------------------------------------------------------------------


class TestRunCheckRollbackIsolation:
    """Tests the fix for cascading "current transaction is aborted" errors.

    Before the fix, a single check failure (e.g. missing pg_stat_statements on
    a non-Snowflake Postgres) aborted the transaction and any subsequent
    checks in the same run also failed. run_check() now calls
    conn.rollback() in a finally block so each check starts fresh.
    """

    def _make_conn_with_sql_file(self, tmp_path, monkeypatch, cursor_execute):
        """Create a mock conn whose cursor.execute uses cursor_execute callable."""
        sql_file = tmp_path / "cache_hit.sql"
        sql_file.write_text("SELECT 1;")
        monkeypatch.setattr("pg_doctor.SQL_DIR", tmp_path)

        cur = MagicMock()
        cur.description = [("col",)]
        cur.fetchall.return_value = []
        cur.execute.side_effect = cursor_execute

        cursor_ctx = MagicMock()
        cursor_ctx.__enter__ = MagicMock(return_value=cur)
        cursor_ctx.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cursor_ctx
        return conn

    def test_rollback_called_after_successful_check(self, tmp_path, monkeypatch):
        """Even on success, rollback is called (read-only, no-op effect)."""
        conn = self._make_conn_with_sql_file(tmp_path, monkeypatch, lambda *a, **kw: None)
        run_check(conn, "cache_hit")
        assert conn.rollback.called

    def test_rollback_called_after_failed_check(self, tmp_path, monkeypatch):
        """On psycopg2.Error the finally clause rolls back so next check is clean."""
        def raise_pg_error(*args, **kwargs):
            raise psycopg2.Error("relation does not exist")

        conn = self._make_conn_with_sql_file(tmp_path, monkeypatch, raise_pg_error)
        result = run_check(conn, "cache_hit")
        assert result["status"] == "critical"
        assert "Query error" in result["message"]
        assert conn.rollback.called

    def test_rollback_error_does_not_propagate(self, tmp_path, monkeypatch):
        """If rollback itself fails (broken connection), we swallow it."""
        def raise_pg_error(*args, **kwargs):
            raise psycopg2.Error("query failed")

        conn = self._make_conn_with_sql_file(tmp_path, monkeypatch, raise_pg_error)
        conn.rollback.side_effect = psycopg2.Error("connection lost")
        # Must not raise — the check error should still be returned
        result = run_check(conn, "cache_hit")
        assert result["status"] == "critical"

    def test_consecutive_failed_checks_each_get_rollback(self, tmp_path, monkeypatch):
        """Two failing checks in a row each trigger their own rollback."""
        def raise_pg_error(*args, **kwargs):
            raise psycopg2.Error("boom")

        conn = self._make_conn_with_sql_file(tmp_path, monkeypatch, raise_pg_error)
        run_check(conn, "cache_hit")
        run_check(conn, "cache_hit")
        assert conn.rollback.call_count == 2
