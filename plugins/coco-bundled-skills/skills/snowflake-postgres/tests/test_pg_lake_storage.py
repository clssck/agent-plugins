"""Tests for pg_lake_storage.py — storage integration CRUD and sensitive output handling."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from pg_lake_storage import (
    _quote_identifier,
    _validate_arn,
    _validate_s3_location,
    _write_secure_json,
    attach_to_instance,
    create_storage_integration,
    describe_integration,
    detach_from_instance,
    drop_integration,
    get_snowflake_connection,
    verify_attachment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_sf_cursor(rows=None, description=None):
    """Create a mock Snowflake cursor."""
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = rows[0] if rows else None
    cur.description = description
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    return cur


def make_sf_conn(cursor):
    """Wrap a mock cursor in a mock Snowflake connection."""
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


# ---------------------------------------------------------------------------
# _quote_identifier
# ---------------------------------------------------------------------------

class TestQuoteIdentifier:
    """Tests for SQL injection prevention."""

    def test_simple_name(self):
        assert _quote_identifier("my_integration") == "my_integration"

    def test_name_with_special_chars(self):
        result = _quote_identifier("my-integration")
        assert result == '"my-integration"'

    def test_empty_name(self):
        with pytest.raises(ValueError, match="empty"):
            _quote_identifier("")

    def test_sql_injection_semicolon(self):
        with pytest.raises(ValueError, match="prohibited"):
            _quote_identifier("test; DROP TABLE users")

    def test_sql_injection_comment(self):
        with pytest.raises(ValueError, match="prohibited"):
            _quote_identifier("test--comment")


# ---------------------------------------------------------------------------
# _write_secure_json
# ---------------------------------------------------------------------------

class TestValidateArn:
    """Tests for IAM ARN validation."""

    def test_valid_arn(self):
        assert _validate_arn("arn:aws:iam::123456789012:role/my-role") == "arn:aws:iam::123456789012:role/my-role"

    def test_valid_arn_with_path(self):
        assert _validate_arn("arn:aws:iam::123456789012:role/path/to/role")

    def test_injection_in_arn(self):
        with pytest.raises(ValueError, match="Invalid IAM role ARN"):
            _validate_arn("arn:aws:iam::123:role/test'; DROP TABLE x; --")

    def test_empty_arn(self):
        with pytest.raises(ValueError, match="Invalid IAM role ARN"):
            _validate_arn("")


class TestValidateS3Location:
    """Tests for S3 location validation."""

    def test_valid_bucket(self):
        assert _validate_s3_location("s3://my-bucket/") == "s3://my-bucket/"

    def test_valid_bucket_with_prefix(self):
        assert _validate_s3_location("s3://my-bucket/some/prefix/")

    def test_injection_in_location(self):
        with pytest.raises(ValueError, match="Invalid S3 location"):
            _validate_s3_location("s3://bucket/'); DROP TABLE x; --")

    def test_not_s3(self):
        with pytest.raises(ValueError, match="Invalid S3 location"):
            _validate_s3_location("https://example.com/data")


class TestWriteSecureJson:
    """Tests for secure temp file creation."""

    def test_creates_readable_json(self):
        data = {"key": "value", "nested": {"a": 1}}
        path = _write_secure_json(data)
        try:
            content = json.loads(Path(path).read_text())
            assert content == data
        finally:
            os.unlink(path)

    def test_file_permissions(self):
        data = {"secret": "test"}
        path = _write_secure_json(data)
        try:
            stat = os.stat(path)
            # 0o600 = owner read/write only
            assert oct(stat.st_mode)[-3:] == "600"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# create_storage_integration
# ---------------------------------------------------------------------------

class TestCreateStorageIntegration:
    """Tests for create_storage_integration() function."""

    def test_creates_with_correct_type(self):
        """Uses POSTGRES_EXTERNAL_STORAGE, not EXTERNAL_STAGE."""
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        result = create_storage_integration(
            conn,
            name="my_s3_int",
            role_arn="arn:aws:iam::123456789012:role/myrole",
            locations=["s3://my-bucket/"],
        )

        assert result["success"] is True
        assert result["type"] == "POSTGRES_EXTERNAL_STORAGE"
        assert result["name"] == "my_s3_int"

        # Verify the SQL contains the correct integration type
        executed_sql = cur.execute.call_args[0][0]
        assert "POSTGRES_EXTERNAL_STORAGE" in executed_sql
        assert "EXTERNAL_STAGE" not in executed_sql

    def test_multiple_locations(self):
        """Supports multiple S3 locations."""
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        result = create_storage_integration(
            conn,
            name="multi_loc",
            role_arn="arn:aws:iam::123456789012:role/test",
            locations=["s3://bucket-a/", "s3://bucket-b/data/"],
        )

        assert result["success"] is True
        assert len(result["locations"]) == 2

        executed_sql = cur.execute.call_args[0][0]
        assert "s3://bucket-a/" in executed_sql
        assert "s3://bucket-b/data/" in executed_sql

    def test_rejects_malicious_arn(self):
        """SQL injection in role_arn is rejected."""
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        with pytest.raises(ValueError, match="Invalid IAM role ARN"):
            create_storage_integration(
                conn,
                name="test",
                role_arn="arn:aws:iam::123:role/x'; DROP TABLE y; --",
                locations=["s3://bucket/"],
            )

    def test_rejects_malicious_location(self):
        """SQL injection in S3 location is rejected."""
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        with pytest.raises(ValueError, match="Invalid S3 location"):
            create_storage_integration(
                conn,
                name="test",
                role_arn="arn:aws:iam::123456789012:role/valid",
                locations=["s3://bucket/'); DROP TABLE x; --"],
            )


# ---------------------------------------------------------------------------
# describe_integration
# ---------------------------------------------------------------------------

class TestDescribeIntegration:
    """Tests for describe_integration() — sensitive output handling."""

    def test_writes_sensitive_values_to_file(self):
        """IAM values go to a secure file, not stdout."""
        rows = [
            ("ENABLED", "Boolean", "true", "false"),
            ("STORAGE_PROVIDER", "String", "S3", ""),
            ("STORAGE_AWS_IAM_USER_ARN", "String", "arn:aws:iam::999:user/abc123", ""),
            ("STORAGE_AWS_EXTERNAL_ID", "String", "ABC_SFCRole=1_ext_id_12345", ""),
            ("STORAGE_AWS_ROLE_ARN", "String", "arn:aws:iam::123:role/myrole", ""),
        ]
        cur = make_sf_cursor(rows)
        conn = make_sf_conn(cur)

        result = describe_integration(conn, "my_int")

        assert result["success"] is True
        assert result["has_iam_values"] is True
        assert "sensitive_values_file" in result

        # Read the secure file and verify contents
        path = result["sensitive_values_file"]
        try:
            content = json.loads(Path(path).read_text())
            assert content["STORAGE_AWS_IAM_USER_ARN"] == "arn:aws:iam::999:user/abc123"
            assert content["STORAGE_AWS_EXTERNAL_ID"] == "ABC_SFCRole=1_ext_id_12345"
            assert "instructions" in content
        finally:
            os.unlink(path)

    def test_no_iam_values(self):
        """Handles integrations without IAM values gracefully."""
        rows = [
            ("ENABLED", "Boolean", "true", "false"),
            ("STORAGE_PROVIDER", "String", "S3", ""),
        ]
        cur = make_sf_cursor(rows)
        conn = make_sf_conn(cur)

        result = describe_integration(conn, "incomplete_int")

        assert result["success"] is True
        assert result["has_iam_values"] is False

        # Clean up the file that was still created
        os.unlink(result["sensitive_values_file"])

    def test_file_not_in_result_json(self):
        """The sensitive values themselves don't appear in the result dict."""
        rows = [
            ("STORAGE_AWS_IAM_USER_ARN", "String", "arn:aws:iam::999:user/secret", ""),
            ("STORAGE_AWS_EXTERNAL_ID", "String", "secret_external_id", ""),
        ]
        cur = make_sf_cursor(rows)
        conn = make_sf_conn(cur)

        result = describe_integration(conn, "test_int")

        # The ARN and external ID must NOT be in the result dict
        result_json = json.dumps(result)
        assert "arn:aws:iam::999:user/secret" not in result_json
        assert "secret_external_id" not in result_json

        os.unlink(result["sensitive_values_file"])


# ---------------------------------------------------------------------------
# attach_to_instance
# ---------------------------------------------------------------------------

class TestAttachToInstance:
    """Tests for attach_to_instance() function."""

    def test_attach(self):
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        result = attach_to_instance(conn, "my_pg_instance", "my_s3_int")

        assert result["success"] is True
        assert result["action"] == "attach"
        assert result["instance"] == "my_pg_instance"

        executed_sql = cur.execute.call_args[0][0]
        assert "ALTER POSTGRES INSTANCE" in executed_sql
        assert "STORAGE_INTEGRATION" in executed_sql


# ---------------------------------------------------------------------------
# verify_attachment
# ---------------------------------------------------------------------------

class TestVerifyAttachment:
    """Tests for verify_attachment() function."""

    def test_attached(self):
        """Instance has a storage integration attached (property/value format)."""
        desc = [("property",), ("value",)]
        rows = [
            ("name", "my_pg"),
            ("state", "READY"),
            ("host", "host.snowflake.com"),
            ("storage_integration", "my_s3_int"),
        ]
        cur = make_sf_cursor(rows, description=desc)
        conn = make_sf_conn(cur)

        result = verify_attachment(conn, "my_pg")

        assert result["success"] is True
        assert result["is_attached"] is True
        assert result["storage_integration"] == "my_s3_int"

    def test_not_attached(self):
        """Instance has no storage integration."""
        desc = [("property",), ("value",)]
        rows = [
            ("name", "my_pg"),
            ("state", "READY"),
            ("storage_integration", ""),
        ]
        cur = make_sf_cursor(rows, description=desc)
        conn = make_sf_conn(cur)

        result = verify_attachment(conn, "my_pg")

        assert result["success"] is True
        assert result["is_attached"] is False
        assert result["storage_integration"] is None

    def test_filters_sensitive_fields(self):
        """access_roles, password, and certificate fields are excluded from output."""
        desc = [("property",), ("value",)]
        rows = [
            ("name", "my_pg"),
            ("state", "READY"),
            ("access_roles", "SECRET_ROLES"),
            ("password", "SECRET_PASS"),
            ("certificate", "-----BEGIN CERT-----"),
        ]
        cur = make_sf_cursor(rows, description=desc)
        conn = make_sf_conn(cur)

        result = verify_attachment(conn, "my_pg")

        instance_info = result["instance_info"]
        assert "access_roles" not in instance_info
        assert "password" not in instance_info
        assert "certificate" not in instance_info
        assert instance_info["name"] == "my_pg"


# ---------------------------------------------------------------------------
# detach_from_instance
# ---------------------------------------------------------------------------

class TestDetachFromInstance:
    """Tests for detach_from_instance() function."""

    def test_detach(self):
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        result = detach_from_instance(conn, "my_pg")

        assert result["success"] is True
        assert result["action"] == "detach"

        executed_sql = cur.execute.call_args[0][0]
        assert "UNSET STORAGE_INTEGRATION" in executed_sql


# ---------------------------------------------------------------------------
# drop_integration
# ---------------------------------------------------------------------------

class TestDropIntegration:
    """Tests for drop_integration() function."""

    def test_drop(self):
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        result = drop_integration(conn, "my_s3_int")

        assert result["success"] is True
        assert result["action"] == "drop"

        executed_sql = cur.execute.call_args[0][0]
        assert "DROP STORAGE INTEGRATION" in executed_sql
        assert "IF EXISTS" in executed_sql


# ---------------------------------------------------------------------------
# JSON output format
# ---------------------------------------------------------------------------

class TestJsonOutput:
    """Test that all results serialize cleanly."""

    def test_create_result_serializes(self):
        cur = make_sf_cursor()
        conn = make_sf_conn(cur)

        result = create_storage_integration(
            conn, "test", "arn:aws:iam::123456789012:role/r", ["s3://mybucket/"]
        )
        output = json.dumps(result, indent=2)
        parsed = json.loads(output)
        assert parsed["success"] is True

    def test_verify_result_serializes(self):
        desc = [("property",), ("value",)]
        rows = [
            ("name", "pg"),
            ("state", "READY"),
            ("storage_integration", "int"),
        ]
        cur = make_sf_cursor(rows, description=desc)
        conn = make_sf_conn(cur)

        result = verify_attachment(conn, "pg")
        output = json.dumps(result, indent=2)
        parsed = json.loads(output)
        assert "instance_info" in parsed


# ---------------------------------------------------------------------------
# get_snowflake_connection — auth paths
# ---------------------------------------------------------------------------

class TestGetSnowflakeConnection:
    """
    Auth-path coverage: env-vars take the
    direct-connector branch (gated on WoA where the connector isn't
    available), and named-connection auth delegates to
    `sf_session.open_snowflake_connection`. The latter funnels through
    `pg_connect.get_snowflake_connection`, which owns the centralized
    private_key_path / token_file_path handling (see pg_connect tests).
    """

    def test_env_var_password_auth(self, monkeypatch):
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "ACME-TEST")
        monkeypatch.setenv("SNOWFLAKE_USER", "alice")
        monkeypatch.setenv("SNOWFLAKE_PASSWORD", "hunter2")
        monkeypatch.delenv("SNOWFLAKE_AUTHENTICATOR", raising=False)

        with patch("pg_lake_storage.snowflake.connector.connect") as mock_connect:
            mock_connect.return_value = MagicMock(name="conn")
            get_snowflake_connection()

        kwargs = mock_connect.call_args.kwargs
        assert kwargs["account"] == "ACME-TEST"
        assert kwargs["user"] == "alice"
        assert kwargs["password"] == "hunter2"

    def test_named_connection_delegates_to_sf_session(self, monkeypatch):
        """Saved-connection auth flows through sf_session.open_snowflake_connection
        so it works on hosts with only the `snow` CLI (Windows ARM64)."""
        monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)
        monkeypatch.delenv("SNOWFLAKE_USER", raising=False)

        fake_conn = MagicMock(name="conn")
        with patch("sf_session.open_snowflake_connection", return_value=fake_conn) as mock_open:
            result = get_snowflake_connection(connection_name="prod")

        mock_open.assert_called_once_with(connection="prod")
        assert result is fake_conn
