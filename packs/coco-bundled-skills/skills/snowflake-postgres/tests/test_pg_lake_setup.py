"""Tests for pg_lake_setup.py — extension checks, config, and verification functions."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock


sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pg_lake_setup import (
    check_config,
    check_extensions,
    create_test_table,
    enable_extensions,
    get_iceberg_tables,
    set_config,
    verify_s3_access,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_cursor(rows, description=None):
    """Create a mock cursor that returns given rows on fetchall/fetchone."""
    cur = MagicMock()
    cur.fetchall.return_value = rows
    cur.fetchone.return_value = rows[0] if rows else None
    cur.description = description
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    return cur


def make_conn(cursor):
    """Wrap a mock cursor in a mock connection."""
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# check_extensions
# ---------------------------------------------------------------------------

class TestCheckExtensions:
    """Tests for check_extensions() function."""

    def test_all_installed(self):
        """All pg_lake extensions are installed."""
        rows = [
            ("pg_lake", "3.2", "3.2", "Data lake extensions"),
            ("pg_lake_copy", "3.2", "3.2", "COPY to/from S3"),
            ("pg_lake_engine", "3.2", "3.2", "Shared internals"),
            ("pg_lake_iceberg", "3.2", "3.2", "Iceberg tables"),
            ("pg_lake_table", "3.2", "3.2", "Foreign data wrapper"),
        ]
        cur = make_cursor(rows)
        conn = make_conn(cur)

        result = check_extensions(conn)
        assert result["pg_lake_available"] is True
        assert result["pg_lake_installed"] is True
        assert result["all_installed"] is True
        assert result["installed_count"] == 5
        assert len(result["extensions"]) == 5

    def test_available_but_not_installed(self):
        """Extensions available but none installed yet."""
        rows = [
            ("pg_lake", "3.2", None, "Data lake extensions"),
            ("pg_lake_copy", "3.2", None, "COPY to/from S3"),
            ("pg_lake_engine", "3.2", None, "Shared internals"),
            ("pg_lake_iceberg", "3.2", None, "Iceberg tables"),
            ("pg_lake_table", "3.2", None, "Foreign data wrapper"),
        ]
        cur = make_cursor(rows)
        conn = make_conn(cur)

        result = check_extensions(conn)
        assert result["pg_lake_available"] is True
        assert result["pg_lake_installed"] is False
        assert result["all_installed"] is False
        assert result["installed_count"] == 0

    def test_not_available(self):
        """pg_lake not available on this instance."""
        cur = make_cursor([])
        conn = make_conn(cur)

        result = check_extensions(conn)
        assert result["pg_lake_available"] is False
        assert result["pg_lake_installed"] is False
        assert result["available_count"] == 0

    def test_partial_install(self):
        """Some extensions installed, others not."""
        rows = [
            ("pg_lake", "3.2", "3.2", "Meta extension"),
            ("pg_lake_engine", "3.2", "3.2", "Engine"),
            ("pg_lake_table", "3.2", None, "FDW"),
        ]
        cur = make_cursor(rows)
        conn = make_conn(cur)

        result = check_extensions(conn)
        assert result["pg_lake_installed"] is True
        assert result["all_installed"] is False
        assert result["installed_count"] == 2
        assert result["available_count"] == 3


# ---------------------------------------------------------------------------
# enable_extensions
# ---------------------------------------------------------------------------

class TestEnableExtensions:
    """Tests for enable_extensions() function."""

    def test_enable_success(self):
        """Enabling extensions succeeds."""
        # First call: CREATE EXTENSION, second call: check_extensions query
        installed_rows = [
            ("pg_lake", "3.2", "3.2", "Data lake"),
            ("pg_lake_copy", "3.2", "3.2", "Copy"),
            ("pg_lake_engine", "3.2", "3.2", "Engine"),
            ("pg_lake_iceberg", "3.2", "3.2", "Iceberg"),
            ("pg_lake_table", "3.2", "3.2", "FDW"),
        ]
        cur = MagicMock()
        # CREATE EXTENSION call returns nothing, then check query returns rows
        cur.fetchall.return_value = installed_rows
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = enable_extensions(conn)
        assert result["success"] is True
        assert result["action"] == "enable"
        assert result["pg_lake_installed"] is True


# ---------------------------------------------------------------------------
# check_config / set_config
# ---------------------------------------------------------------------------

class TestCheckConfig:
    """Tests for check_config() function."""

    def test_configured(self):
        """S3 location prefix is set."""
        rows = [
            ("pg_lake_iceberg.default_location_prefix", "s3://my-bucket/pg-lake", None, "session", "", ""),
        ]
        cur = make_cursor(rows)
        conn = make_conn(cur)

        result = check_config(conn)
        assert result["is_configured"] is True
        assert result["default_location_prefix"] == "s3://my-bucket/pg-lake"
        assert len(result["settings"]) == 1

    def test_not_configured(self):
        """No S3 location set."""
        rows = [
            ("pg_lake_iceberg.default_location_prefix", "", None, "default", "", ""),
        ]
        cur = make_cursor(rows)
        conn = make_conn(cur)

        result = check_config(conn)
        assert result["is_configured"] is False

    def test_no_settings(self):
        """pg_lake not installed — no settings found."""
        cur = make_cursor([])
        conn = make_conn(cur)

        result = check_config(conn)
        assert result["is_configured"] is False
        assert result["default_location_prefix"] is None
        assert result["settings"] == []


class TestSetConfig:
    """Tests for set_config() function."""

    def test_set_session(self):
        """Set prefix for current session."""
        cur = MagicMock()
        # GUC existence check returns a row, then SET, then check_config query
        cur.fetchone.side_effect = [(1,), ("s3://bucket/path",)]
        cur.fetchall.return_value = [
            ("pg_lake_iceberg.default_location_prefix", "s3://bucket/path", None, "session", "", "s3://bucket/path"),
        ]
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = set_config(conn, "s3://bucket/path")
        assert result["success"] is True
        assert result["action"] == "set_config"

    def test_guc_not_found(self):
        """GUC doesn't exist — pg_lake not loaded."""
        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = set_config(conn, "s3://bucket/path")
        assert result["success"] is False
        assert "not found" in result["error"]

    def test_persisted_by_platform(self):
        """Platform persisted the value — reset_val matches prefix."""
        cur = MagicMock()
        # GUC check returns row, reset_val query returns matching prefix
        cur.fetchone.side_effect = [(1,), ("s3://bucket/path",)]
        cur.fetchall.return_value = [
            ("pg_lake_iceberg.default_location_prefix", "s3://bucket/path", None, "session", "", "s3://bucket/path"),
        ]
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = set_config(conn, "s3://bucket/path")
        assert result["success"] is True
        assert result["persisted_by_platform"] is True


# ---------------------------------------------------------------------------
# verify_s3_access
# ---------------------------------------------------------------------------

class TestVerifyS3Access:
    """Tests for verify_s3_access() function."""

    def test_success_with_files(self):
        """S3 listing returns files."""
        desc = [("file_name",), ("file_size",)]
        rows = [
            ("file1.parquet", 1024),
            ("file2.parquet", 2048),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.description = desc
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = verify_s3_access(conn, "s3://my-bucket/")
        assert result["success"] is True
        assert result["file_count"] == 2
        assert result["prefix"] == "s3://my-bucket/"

    def test_success_empty_bucket(self):
        """S3 listing succeeds with empty result — still valid access."""
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur.description = [("file_name",)]
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = verify_s3_access(conn, "s3://empty-bucket/")
        assert result["success"] is True
        assert result["file_count"] == 0

    def test_no_prefix_no_default(self):
        """No prefix provided and no default_location_prefix set."""
        cur = MagicMock()
        cur.fetchone.return_value = (None,)
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = verify_s3_access(conn, None)
        assert result["success"] is False
        assert "no pg_lake_iceberg" in result["error"].lower() or "not set" in result["error"].lower()

    def test_s3_error(self):
        """S3 access fails — returns error details."""
        import psycopg2

        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.execute.side_effect = [
            None,  # SHOW succeeds
            psycopg2.OperationalError("could not access S3"),
        ]
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        # Provide prefix so we skip the SHOW path
        # but the lake_file.list() call fails
        cur2 = MagicMock()
        cur2.execute.side_effect = psycopg2.OperationalError("access denied to S3")
        cur2.__enter__ = lambda s: s
        cur2.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cur2

        result = verify_s3_access(conn, "s3://no-access/")
        assert result["success"] is False
        assert "access denied" in result["error"].lower()


# ---------------------------------------------------------------------------
# create_test_table
# ---------------------------------------------------------------------------

class TestCreateTestTable:
    """Tests for create_test_table() function."""

    def test_success(self):
        """Full test table lifecycle succeeds."""
        call_count = [0]
        
        def execute_side_effect(sql, params=None):
            nonlocal call_count
            call_count[0] += 1

        cur = MagicMock()
        cur.execute.side_effect = execute_side_effect
        # Query result: (1, 'pg_lake_test')
        cur.fetchall.return_value = [(1, "pg_lake_test")]
        # Catalog check: table found
        cur.fetchone.return_value = ("pg_lake_test_iceberg",)
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = create_test_table(conn)
        assert result["success"] is True
        assert result["table_created"] is True
        assert result["in_catalog"] is True
        assert result["cleaned_up"] is True

    def test_create_failure(self):
        """CREATE TABLE fails — returns error at create step."""
        import psycopg2

        call_idx = [0]

        def execute_side_effect(sql, params=None):
            call_idx[0] += 1
            # First call: DROP IF EXISTS (ok)
            # Second call: CREATE TABLE (fail)
            if call_idx[0] == 2:
                raise psycopg2.ProgrammingError("permission denied")

        cur = MagicMock()
        cur.execute.side_effect = execute_side_effect
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = create_test_table(conn)
        assert result["success"] is False
        assert result["step"] == "create_table"
        assert "permission denied" in result["error"]


# ---------------------------------------------------------------------------
# get_iceberg_tables
# ---------------------------------------------------------------------------

class TestGetIcebergTables:
    """Tests for get_iceberg_tables() function."""

    def test_returns_tables(self):
        """Lists Iceberg tables from catalog."""
        desc = [("table_schema",), ("table_name",), ("location",)]
        rows = [
            ("public", "events", "s3://bucket/events"),
            ("public", "users", "s3://bucket/users"),
        ]
        cur = MagicMock()
        cur.fetchall.return_value = rows
        cur.description = desc
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = get_iceberg_tables(conn)
        assert result["success"] is True
        assert result["table_count"] == 2
        assert result["tables"][0]["table_name"] == "events"

    def test_empty(self):
        """No Iceberg tables exist."""
        cur = MagicMock()
        cur.fetchall.return_value = []
        cur.description = [("table_schema",), ("table_name",)]
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = get_iceberg_tables(conn)
        assert result["success"] is True
        assert result["table_count"] == 0

    def test_view_not_exists(self):
        """iceberg_tables view doesn't exist — returns error."""
        import psycopg2

        cur = MagicMock()
        cur.execute.side_effect = psycopg2.ProgrammingError(
            'relation "iceberg_tables" does not exist'
        )
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = get_iceberg_tables(conn)
        assert result["success"] is False
        assert "iceberg_tables" in result["error"]


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------

class TestJsonOutput:
    """Test that results serialize cleanly to JSON."""

    def test_check_extensions_json(self):
        """check_extensions result serializes to valid JSON."""
        rows = [("pg_lake", "3.2", "3.2", "Data lake")]
        cur = make_cursor(rows)
        conn = make_conn(cur)

        result = check_extensions(conn)
        output = json.dumps(result, indent=2)
        parsed = json.loads(output)
        assert "extensions" in parsed
        assert isinstance(parsed["extensions"], list)

    def test_verify_s3_json(self):
        """verify_s3_access result serializes to valid JSON."""
        desc = [("file_name",)]
        cur = MagicMock()
        cur.fetchall.return_value = [("test.parquet",)]
        cur.description = desc
        cur.__enter__ = lambda s: s
        cur.__exit__ = MagicMock(return_value=False)

        conn = MagicMock()
        conn.cursor.return_value = cur

        result = verify_s3_access(conn, "s3://bucket/")
        output = json.dumps(result, indent=2)
        parsed = json.loads(output)
        assert parsed["success"] is True
