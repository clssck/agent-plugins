"""Tests for pg_connect.py parsing and file management functions."""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

# Import from scripts directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from unittest.mock import MagicMock, patch

import pg_connect
from pg_connect import (
    _extract_password,
    _row_to_dict,
    _validate_sql_string,
    categorize_connection_error,
    create_postgres_instance,
    ensure_cert,
    parse_create_response,
    parse_reset_response,
    reset_postgres_access,
    load_pgpass,
    save_pgpass,
    find_pgpass_entry,
    upsert_pgpass_entry,
    load_service_file,
    save_service_entry,
    get_service_entry,
    save_connection,
    sanitize_error,
    validate_connection,
)


class TestExtractPassword:
    """Tests for _extract_password function."""
    
    def test_direct_password_field(self):
        """Password at top level of dict."""
        assert _extract_password({"password": "secret123"}) == "secret123"
    
    def test_password_in_access_roles(self):
        """Password nested in access_roles array."""
        data = {
            "access_roles": [
                {"name": "snowflake_admin", "password": "admin_pass"}
            ]
        }
        assert _extract_password(data) == "admin_pass"
    
    def test_password_in_data_wrapper(self):
        """Password nested under 'data' key."""
        data = {"data": {"password": "wrapped_pass"}}
        assert _extract_password(data) == "wrapped_pass"
    
    def test_password_in_rows_wrapper(self):
        """Password nested under 'rows' key (list of dicts)."""
        data = {"rows": [{"password": "row_pass"}]}
        assert _extract_password(data) == "row_pass"
    
    def test_sql_result_format_columns_rows(self):
        """SQL result format: {"columns": [...], "rows": [[...]]}."""
        data = {
            "columns": ["PASSWORD"],
            "rows": [["sql_password_value"]]
        }
        assert _extract_password(data) == "sql_password_value"
    
    def test_sql_result_format_case_insensitive(self):
        """SQL columns are matched case-insensitively."""
        data = {
            "columns": ["other", "Password", "more"],
            "rows": [["a", "the_password", "b"]]
        }
        assert _extract_password(data) == "the_password"
    
    def test_sql_result_format_no_password_column(self):
        """SQL result without password column returns None."""
        data = {
            "columns": ["name", "value"],
            "rows": [["test", "data"]]
        }
        assert _extract_password(data) is None
    
    def test_list_wrapper(self):
        """Password in first element of list."""
        data = [{"password": "list_pass"}]
        assert _extract_password(data) == "list_pass"
    
    def test_empty_dict(self):
        """Empty dict returns None."""
        assert _extract_password({}) is None
    
    def test_empty_list(self):
        """Empty list returns None."""
        assert _extract_password([]) is None
    
    def test_none_input(self):
        """None input returns None."""
        assert _extract_password(None) is None


class TestRowToDict:
    """Tests for _row_to_dict helper."""
    
    def test_basic_conversion(self):
        """Converts columns and row to dict."""
        columns = ["NAME", "VALUE"]
        row = ["test", 123]
        result = _row_to_dict(columns, row)
        assert result == {"name": "test", "value": 123}
    
    def test_lowercase_keys(self):
        """Column names are lowercased."""
        columns = ["HOST", "Port", "DbName"]
        row = ["host.com", 5432, "mydb"]
        result = _row_to_dict(columns, row)
        assert "host" in result
        assert "port" in result
        assert "dbname" in result


class TestParseCreateResponse:
    """Tests for parse_create_response function."""
    
    def test_direct_dict_format(self):
        """Parse direct dict response format."""
        data = {
            "host": "abc123.snowflakecomputing.com",
            "access_roles": [
                {"name": "snowflake_admin", "password": "admin_secret"}
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = parse_create_response(f.name)
            assert result["host"] == "abc123.snowflakecomputing.com"
            assert result["password"] == "admin_secret"
            assert result["port"] == 5432
            assert result["user"] == "snowflake_admin"
            
            os.unlink(f.name)
    
    def test_multiple_access_roles(self):
        """Parse response with both admin and application roles."""
        data = {
            "host": "multi.snowflakecomputing.com",
            "access_roles": [
                {"name": "snowflake_admin", "password": "admin_pass"},
                {"name": "application", "password": "app_pass"}
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = parse_create_response(f.name)
            assert result["host"] == "multi.snowflakecomputing.com"
            assert result["user"] == "snowflake_admin"
            assert result["password"] == "admin_pass"
            # access_roles should contain both
            assert len(result["access_roles"]) == 2
            role_names = [r["name"] for r in result["access_roles"]]
            assert "snowflake_admin" in role_names
            assert "application" in role_names
            
            os.unlink(f.name)
    
    def test_sql_result_format(self):
        """Parse SQL result format with columns/rows."""
        data = {
            "columns": ["host", "access_roles"],
            "rows": [[
                "xyz789.snowflakecomputing.com",
                json.dumps([{"name": "snowflake_admin", "password": "sql_secret"}])
            ]]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = parse_create_response(f.name)
            assert result["host"] == "xyz789.snowflakecomputing.com"
            assert result["password"] == "sql_secret"
            
            os.unlink(f.name)
    
    def test_sql_result_dict_access_roles(self):
        """Parse real Snowflake response with dict access_roles (role_name: password)."""
        data = {
            "columns": ["status", "host", "access_roles", "default_database"],
            "rows": [[
                "Postgres instance creation initiated.",
                "real.snowflakecomputing.com",
                json.dumps({"application": "app_secret", "snowflake_admin": "admin_secret"}),
                "postgres"
            ]]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = parse_create_response(f.name)
            assert result["host"] == "real.snowflakecomputing.com"
            assert result["user"] == "snowflake_admin"
            assert result["password"] == "admin_secret"
            assert len(result["access_roles"]) == 2
            role_names = [r["name"] for r in result["access_roles"]]
            assert "snowflake_admin" in role_names
            assert "application" in role_names
            # Verify passwords are correctly mapped
            for role in result["access_roles"]:
                if role["name"] == "snowflake_admin":
                    assert role["password"] == "admin_secret"
                elif role["name"] == "application":
                    assert role["password"] == "app_secret"
            
            os.unlink(f.name)
    
    def test_list_wrapped_response(self):
        """Parse response wrapped in a list."""
        data = [{
            "host": "wrapped.snowflakecomputing.com",
            "access_roles": [
                {"name": "snowflake_admin", "password": "wrapped_pass"}
            ]
        }]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = parse_create_response(f.name)
            assert result["host"] == "wrapped.snowflakecomputing.com"
            
            os.unlink(f.name)
    
    def test_missing_host_raises(self):
        """Missing host field raises ValueError."""
        data = {"access_roles": [{"name": "snowflake_admin", "password": "x"}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            with pytest.raises(ValueError, match="No 'host' field"):
                parse_create_response(f.name)
            
            os.unlink(f.name)
    
    def test_missing_password_raises(self):
        """Missing snowflake_admin password raises ValueError."""
        data = {"host": "test.com", "access_roles": []}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            with pytest.raises(ValueError, match="No snowflake_admin password"):
                parse_create_response(f.name)
            
            os.unlink(f.name)


class TestParseResetResponse:
    """Tests for parse_reset_response function."""
    
    def test_sql_result_format(self):
        """Parse RESET ACCESS SQL result format."""
        data = {
            "query": "ALTER POSTGRES SERVICE test RESET ACCESS FOR 'snowflake_admin';",
            "columns": ["password"],
            "rows": [["new_reset_password"]]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = parse_reset_response(f.name)
            assert result == "new_reset_password"
            
            os.unlink(f.name)
    
    def test_direct_password_format(self):
        """Parse direct password field format."""
        data = {"password": "direct_pass"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            result = parse_reset_response(f.name)
            assert result == "direct_pass"
            
            os.unlink(f.name)
    
    def test_missing_password_raises(self):
        """Missing password field raises ValueError."""
        data = {"columns": ["other"], "rows": [["value"]]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            
            with pytest.raises(ValueError, match="No password field"):
                parse_reset_response(f.name)
            
            os.unlink(f.name)


class TestPgpassManagement:
    """Tests for pgpass file management."""
    
    @pytest.fixture
    def temp_pgpass(self, tmp_path, monkeypatch):
        """Create a temporary pgpass file location."""
        pgpass_file = tmp_path / ".pgpass"
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        return pgpass_file
    
    def test_load_empty_pgpass(self, temp_pgpass):
        """Load returns empty list when file doesn't exist."""
        entries = load_pgpass()
        assert entries == []
    
    def test_save_and_load_pgpass(self, temp_pgpass):
        """Save and reload entries."""
        entries = [{
            "host": "test.com",
            "port": 5432,
            "database": "postgres",
            "user": "admin",
            "password": "secret",
        }]
        save_pgpass(entries)
        
        loaded = load_pgpass()
        assert len(loaded) == 1
        assert loaded[0]["host"] == "test.com"
        assert loaded[0]["password"] == "secret"
    
    def test_pgpass_permissions(self, temp_pgpass):
        """Pgpass file has 0600 permissions."""
        entries = [{"host": "*", "port": "*", "database": "*", "user": "*", "password": "x"}]
        save_pgpass(entries)
        
        mode = temp_pgpass.stat().st_mode & 0o777
        assert mode == 0o600
    
    def test_pgpass_escapes_colons_in_host(self, temp_pgpass):
        """Colons in host field are escaped."""
        entries = [{
            "host": "host:with:colons",
            "port": 5432,
            "database": "db",
            "user": "user",
            "password": "pass",
        }]
        save_pgpass(entries)
        
        loaded = load_pgpass()
        assert loaded[0]["host"] == "host:with:colons"
    
    def test_pgpass_escapes_colons_in_password(self, temp_pgpass):
        """Colons in password field are escaped and round-trip correctly."""
        entries = [{
            "host": "test.com",
            "port": 5432,
            "database": "db",
            "user": "user",
            "password": "pass:with:colons",
        }]
        save_pgpass(entries)
        
        loaded = load_pgpass()
        assert len(loaded) == 1
        assert loaded[0]["password"] == "pass:with:colons"
    
    def test_pgpass_strips_newlines_from_password(self, temp_pgpass):
        """Newlines in password are stripped to prevent file corruption."""
        entries = [{
            "host": "test.com",
            "port": 5432,
            "database": "db",
            "user": "user",
            "password": "pass\nwith\nnewlines",
        }]
        save_pgpass(entries)
        
        loaded = load_pgpass()
        assert "\n" not in loaded[0]["password"]
        assert loaded[0]["password"] == "passwithnewlines"
    
    def test_find_pgpass_entry_exact(self, temp_pgpass):
        """Find exact matching pgpass entry."""
        entries = [{
            "host": "specific.com",
            "port": "5432",
            "database": "mydb",
            "user": "myuser",
            "password": "mypass",
        }]
        save_pgpass(entries)
        
        found = find_pgpass_entry("specific.com", 5432, "mydb", "myuser")
        assert found is not None
        assert found["password"] == "mypass"
    
    def test_find_pgpass_entry_wildcard(self, temp_pgpass):
        """Wildcard entries match any value."""
        entries = [{
            "host": "*",
            "port": "*",
            "database": "*",
            "user": "*",
            "password": "wildcard_pass",
        }]
        save_pgpass(entries)
        
        found = find_pgpass_entry("any.host.com", 9999, "anydb", "anyuser")
        assert found is not None
        assert found["password"] == "wildcard_pass"
    
    def test_upsert_creates_new_entry(self, temp_pgpass):
        """Upsert creates entry when none exists."""
        upsert_pgpass_entry("new.com", 5432, "db", "user", "newpass")
        
        loaded = load_pgpass()
        assert len(loaded) == 1
        assert loaded[0]["password"] == "newpass"
    
    def test_upsert_updates_existing_entry(self, temp_pgpass):
        """Upsert updates password when entry exists."""
        entries = [{
            "host": "update.com",
            "port": 5432,
            "database": "db",
            "user": "user",
            "password": "oldpass",
        }]
        save_pgpass(entries)
        
        upsert_pgpass_entry("update.com", 5432, "db", "user", "newpass")
        
        loaded = load_pgpass()
        assert len(loaded) == 1
        assert loaded[0]["password"] == "newpass"


class TestServiceFileManagement:
    """Tests for pg_service.conf file management."""
    
    @pytest.fixture
    def temp_service_file(self, tmp_path, monkeypatch):
        """Create a temporary service file location."""
        service_file = tmp_path / ".pg_service.conf"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        return service_file
    
    def test_save_and_get_service_entry(self, temp_service_file):
        """Save and retrieve a service entry."""
        params = {
            "host": "test.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        }
        save_service_entry("myinstance", params)
        
        entry = get_service_entry("myinstance")
        assert entry is not None
        assert entry["host"] == "test.snowflakecomputing.com"
        assert entry["port"] == 5432
    
    def test_get_nonexistent_entry(self, temp_service_file):
        """Get returns None for missing entry."""
        entry = get_service_entry("nonexistent")
        assert entry is None
    
    def test_get_entry_missing_host(self, temp_service_file):
        """Entry without host field returns None."""
        # Manually create an invalid entry
        config = load_service_file()
        config.add_section("invalid")
        config.set("invalid", "port", "5432")
        with open(temp_service_file, "w") as f:
            config.write(f)
        
        entry = get_service_entry("invalid")
        assert entry is None
    
    def test_update_existing_entry(self, temp_service_file):
        """Saving same name updates existing entry."""
        params1 = {"host": "old.com", "port": 5432}
        params2 = {"host": "new.com", "port": 5433}
        
        save_service_entry("test", params1)
        save_service_entry("test", params2)
        
        entry = get_service_entry("test")
        assert entry["host"] == "new.com"
        assert entry["port"] == 5433


class TestSaveConnection:
    """Tests for save_connection combined operation."""
    
    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        """Create temporary service and pgpass file locations."""
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        return {"service": service_file, "pgpass": pgpass_file}
    
    def test_save_single_user(self, temp_pg_files):
        """Save connection with single user/password."""
        params = {
            "host": "single.com",
            "port": 5432,
            "database": "postgres",
            "user": "myuser",
            "password": "mypass",
            "sslmode": "require",
        }
        result = save_connection("myconn", params)
        
        assert result["roles_saved"] == ["myuser"]
        
        # Check service file
        entry = get_service_entry("myconn")
        assert entry["host"] == "single.com"
        assert entry["user"] == "myuser"
        
        # Check pgpass
        pgpass_entry = find_pgpass_entry("single.com", 5432, "postgres", "myuser")
        assert pgpass_entry is not None
        assert pgpass_entry["password"] == "mypass"
    
    def test_save_multiple_access_roles(self, temp_pg_files):
        """Save connection with multiple access_roles from CREATE response."""
        params = {
            "host": "multi.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "password": "admin_pass",
            "sslmode": "require",
            "access_roles": [
                {"name": "snowflake_admin", "password": "admin_pass"},
                {"name": "application", "password": "app_pass"},
            ]
        }
        result = save_connection("multiuser", params)
        
        # Both roles should be saved
        assert "snowflake_admin" in result["roles_saved"]
        assert "application" in result["roles_saved"]
        
        # Service file uses primary user
        entry = get_service_entry("multiuser")
        assert entry["user"] == "snowflake_admin"
        
        # Both users in pgpass
        admin_entry = find_pgpass_entry("multi.snowflakecomputing.com", 5432, "postgres", "snowflake_admin")
        assert admin_entry is not None
        assert admin_entry["password"] == "admin_pass"
        
        app_entry = find_pgpass_entry("multi.snowflakecomputing.com", 5432, "postgres", "application")
        assert app_entry is not None
        assert app_entry["password"] == "app_pass"
    
    def test_save_updates_existing_roles(self, temp_pg_files):
        """Saving again updates passwords for existing roles."""
        params1 = {
            "host": "update.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "password": "old_pass",
            "sslmode": "require",
            "access_roles": [
                {"name": "snowflake_admin", "password": "old_admin"},
                {"name": "application", "password": "old_app"},
            ]
        }
        save_connection("updatetest", params1)
        
        # Save again with new passwords
        params2 = {
            "host": "update.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "password": "new_pass",
            "sslmode": "require",
            "access_roles": [
                {"name": "snowflake_admin", "password": "new_admin"},
                {"name": "application", "password": "new_app"},
            ]
        }
        result = save_connection("updatetest", params2)
        
        assert result["password_updated"] is True
        
        # Check updated passwords
        admin_entry = find_pgpass_entry("update.com", 5432, "postgres", "snowflake_admin")
        assert admin_entry["password"] == "new_admin"
        
        app_entry = find_pgpass_entry("update.com", 5432, "postgres", "application")
        assert app_entry["password"] == "new_app"


class TestCLIOutputSecurity:
    """Tests that CLI output never exposes secrets."""
    
    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        """Create temporary service and pgpass file locations."""
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        return {"service": service_file, "pgpass": pgpass_file}
    
    def test_from_response_output_hides_password(self, temp_pg_files, tmp_path):
        """CLI output from --from-response should not contain passwords."""
        import subprocess
        
        # Create a response file with passwords
        response_file = tmp_path / "create_response.json"
        response_data = {
            "columns": ["status", "host", "access_roles", "default_database"],
            "rows": [[
                "Instance created.",
                "test.snowflakecomputing.com",
                json.dumps({
                    "application": "SECRET_APP_PASSWORD_12345",
                    "snowflake_admin": "SECRET_ADMIN_PASSWORD_67890"
                }),
                "postgres"
            ]]
        }
        response_file.write_text(json.dumps(response_data))
        
        # Run CLI command
        script_path = Path(__file__).parent.parent / "scripts" / "pg_connect.py"
        env = os.environ.copy()
        env["PGSERVICEFILE"] = str(temp_pg_files["service"])
        env["PGPASSFILE"] = str(temp_pg_files["pgpass"])
        
        result = subprocess.run(
            [
                sys.executable, str(script_path),
                "--from-response", str(response_file),
                "--connection-name", "test_conn",
                "--save"
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        
        output = result.stdout + result.stderr
        
        # Verify passwords are NOT in output
        assert "SECRET_APP_PASSWORD_12345" not in output
        assert "SECRET_ADMIN_PASSWORD_67890" not in output
        assert "access_roles" not in output.lower() or "access_roles" not in output
        
        # Verify safe fields ARE in output
        assert "test.snowflakecomputing.com" in output
        assert "has_password" in output or "True" in output
    
    def test_from_reset_response_output_hides_password(self, temp_pg_files, tmp_path):
        """CLI output from --from-reset-response should not contain passwords."""
        import subprocess
        
        # First create a service entry (required for reset)
        from pg_connect import save_service_entry
        save_service_entry("reset_test", {
            "host": "reset.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        })
        
        # Create a reset response file with password
        reset_file = tmp_path / "reset_response.json"
        reset_data = {
            "query": "ALTER POSTGRES SERVICE reset_test RESET ACCESS FOR 'snowflake_admin';",
            "columns": ["password"],
            "rows": [["SECRET_RESET_PASSWORD_ABCDEF"]]
        }
        reset_file.write_text(json.dumps(reset_data))
        
        # Run CLI command
        script_path = Path(__file__).parent.parent / "scripts" / "pg_connect.py"
        env = os.environ.copy()
        env["PGSERVICEFILE"] = str(temp_pg_files["service"])
        env["PGPASSFILE"] = str(temp_pg_files["pgpass"])
        
        result = subprocess.run(
            [
                sys.executable, str(script_path),
                "--from-reset-response", str(reset_file),
                "--connection-name", "reset_test"
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        
        output = result.stdout + result.stderr
        
        # Verify password is NOT in output
        assert "SECRET_RESET_PASSWORD_ABCDEF" not in output
    
    def test_json_output_hides_secrets(self, temp_pg_files, tmp_path):
        """JSON output mode should also hide secrets."""
        import subprocess
        
        # Create a response file with passwords
        response_file = tmp_path / "create_response.json"
        response_data = {
            "columns": ["host", "access_roles"],
            "rows": [[
                "json.snowflakecomputing.com",
                json.dumps({
                    "snowflake_admin": "JSON_SECRET_PASSWORD_XYZ"
                })
            ]]
        }
        response_file.write_text(json.dumps(response_data))
        
        # Run CLI command with --json
        script_path = Path(__file__).parent.parent / "scripts" / "pg_connect.py"
        env = os.environ.copy()
        env["PGSERVICEFILE"] = str(temp_pg_files["service"])
        env["PGPASSFILE"] = str(temp_pg_files["pgpass"])
        
        result = subprocess.run(
            [
                sys.executable, str(script_path),
                "--from-response", str(response_file),
                "--connection-name", "json_test",
                "--save",
                "--json"
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        
        output = result.stdout + result.stderr
        
        # Verify password is NOT in JSON output
        assert "JSON_SECRET_PASSWORD_XYZ" not in output
        
        # Parse JSON output and verify structure
        if result.stdout.strip():
            output_json = json.loads(result.stdout)
            assert "password" not in output_json.get("data", {})
            assert "access_roles" not in output_json.get("data", {})


class TestSanitizeError:
    """Tests for redacting secrets from error text."""

    def test_redacts_password_in_connection_string_param(self):
        """A raw postgres URI passed via --connection has its password masked."""
        conn = "postgres://alice:supersecret@db.example.com:5432/postgres?sslmode=require"
        msg = sanitize_error(f"Failed to connect using {conn}", {"connection": conn})
        assert "supersecret" not in msg
        assert "postgres://alice:[REDACTED]@db.example.com:5432/postgres?sslmode=require" in msg

    def test_redacts_postgres_uri_found_in_error_text(self):
        """Fallback URI redaction works even without parsed params."""
        msg = sanitize_error(
            "server rejected postgresql://bob:secret%40pw@db.example.com/postgres?sslmode=require",
            {},
        )
        assert "secret%40pw" not in msg
        assert "postgresql://bob:[REDACTED]@db.example.com/postgres?sslmode=require" in msg

    def test_redacts_explicit_password_param(self):
        """Non-URI error text still redacts a parsed password value."""
        msg = sanitize_error("authentication failed for password supersecret", {"password": "supersecret"})
        assert "supersecret" not in msg
        assert "[REDACTED]" in msg


# Sample PEM certificate for testing (not a real cert, just valid PEM structure)
SAMPLE_PEM = """-----BEGIN CERTIFICATE-----
MIIBkTCB+wIUYz3MHFH0RkO8L3lOZ2jXQ8KLMB0wDQYJKoZIhvcNAQELBQAw
EzERMA8GA1UEAwwIdGVzdC1jYTAeFw0yNjAxMDEwMDAwMDBaFw00NjAxMDEwMDAw
MDBaMBMxETAPBgNVBAMMCHRlc3QtY2EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNC
AARtb3O+0bvPyqK3LJ+dN8RGxekvIpKXTgjEkA+KjFN5GBoaF/FD6gkJbCdIrlu
Lf/ZFUQqxnqvDB5yrVKjLqBRoyMwITAPBgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB
/wQEAwICBDANBgkqhkiG9w0BAQsFAANBADlk6J/Bj+E3Li5MNT3pVG2C3epCn3eW
Sj8cOn4bKcZDpII3WNJf9lXl+o9WoKNJRUFPq0F8BF5K9KSM8yUMm7s=
-----END CERTIFICATE-----"""


class TestEnsureCert:
    """Tests for ensure_cert() CA certificate fetch and cache."""

    @pytest.fixture
    def temp_cert_dir(self, tmp_path, monkeypatch):
        """Redirect CERT_DIR to a temp location."""
        cert_dir = tmp_path / "certs"
        monkeypatch.setattr("pg_connect.CERT_DIR", cert_dir)
        return cert_dir

    def _mock_describe_result(self, cert_pem=SAMPLE_PEM):
        """Build a mock DESCRIBE POSTGRES INSTANCE result with a certificate field."""
        return {
            "columns": ["property", "value"],
            "rows": [
                ["name", "MY_INSTANCE"],
                ["host", "abc.snowflakecomputing.com"],
                ["certificate", cert_pem],
                ["status", "RUNNING"],
            ],
        }

    def test_fetches_and_saves_cert(self, temp_cert_dir):
        """ensure_cert writes PEM to CERT_DIR/<name>.pem and returns the path."""
        with patch("pg_connect.execute_snowflake_sql", return_value=self._mock_describe_result()):
            path = ensure_cert("MY_INSTANCE", connection_name="myinst")

        assert path is not None
        assert path.exists()
        assert path.name == "myinst.pem"
        assert path.parent == temp_cert_dir
        content = path.read_text()
        assert content.startswith("-----BEGIN CERTIFICATE-----")
        assert content.strip().endswith("-----END CERTIFICATE-----")

    def test_cert_file_permissions(self, temp_cert_dir):
        """Cert file is written with 0600, directory with 0700."""
        with patch("pg_connect.execute_snowflake_sql", return_value=self._mock_describe_result()):
            path = ensure_cert("MY_INSTANCE", connection_name="permtest")

        assert path.stat().st_mode & 0o777 == 0o600
        assert temp_cert_dir.stat().st_mode & 0o777 == 0o700

    def test_uses_instance_name_when_no_connection_name(self, temp_cert_dir):
        """Falls back to lowercased instance name as identifier."""
        with patch("pg_connect.execute_snowflake_sql", return_value=self._mock_describe_result()):
            path = ensure_cert("BIG_INSTANCE")

        assert path.name == "big_instance.pem"

    def test_returns_none_when_no_cert(self, temp_cert_dir):
        """Returns None when DESCRIBE has no certificate field."""
        result = {
            "columns": ["property", "value"],
            "rows": [
                ["name", "MY_INSTANCE"],
                ["host", "abc.com"],
                ["status", "RUNNING"],
            ],
        }
        with patch("pg_connect.execute_snowflake_sql", return_value=result):
            path = ensure_cert("MY_INSTANCE")

        assert path is None

    def test_returns_none_for_empty_cert(self, temp_cert_dir):
        """Returns None when certificate field is empty string."""
        with patch("pg_connect.execute_snowflake_sql", return_value=self._mock_describe_result(cert_pem="")):
            path = ensure_cert("MY_INSTANCE")

        assert path is None

    def test_returns_none_for_non_pem_cert(self, temp_cert_dir):
        """Returns None when certificate field doesn't look like PEM."""
        with patch("pg_connect.execute_snowflake_sql", return_value=self._mock_describe_result(cert_pem="not-a-cert")):
            path = ensure_cert("MY_INSTANCE")

        assert path is None

    def test_returns_none_when_no_rows(self, temp_cert_dir):
        """Returns None when DESCRIBE returns no rows."""
        result = {"columns": ["property", "value"], "rows": []}
        with patch("pg_connect.execute_snowflake_sql", return_value=result):
            path = ensure_cert("MY_INSTANCE")

        assert path is None

    def test_overwrites_existing_cert(self, temp_cert_dir):
        """Overwrites an existing cert file (always-refresh strategy)."""
        temp_cert_dir.mkdir(parents=True)
        existing = temp_cert_dir / "myinst.pem"
        existing.write_text("old cert data")

        with patch("pg_connect.execute_snowflake_sql", return_value=self._mock_describe_result()):
            path = ensure_cert("MY_INSTANCE", connection_name="myinst")

        assert "old cert data" not in path.read_text()
        assert "BEGIN CERTIFICATE" in path.read_text()

    def test_passes_snowflake_connection_args(self, temp_cert_dir):
        """Passes connection_name and authenticator through to execute_snowflake_sql."""
        with patch("pg_connect.execute_snowflake_sql", return_value=self._mock_describe_result()) as mock_sql:
            ensure_cert("MY_INSTANCE", snowflake_connection="myconn", authenticator="externalbrowser")

        mock_sql.assert_called_once_with(
            "DESCRIBE POSTGRES INSTANCE MY_INSTANCE;",
            "myconn",
            "externalbrowser",
            None,
        )


class TestServiceFileWithCert:
    """Tests for sslrootcert in service file entries."""

    @pytest.fixture
    def temp_service_file(self, tmp_path, monkeypatch):
        """Create a temporary service file location."""
        service_file = tmp_path / ".pg_service.conf"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        return service_file

    def test_save_with_sslrootcert(self, temp_service_file):
        """Saving with sslrootcert sets verify-ca and writes the cert path."""
        params = {
            "host": "test.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        }
        save_service_entry("myinst", params, sslrootcert="/path/to/cert.pem")

        entry = get_service_entry("myinst")
        assert entry["sslmode"] == "verify-ca"
        assert entry["sslrootcert"] == "/path/to/cert.pem"

    def test_save_without_sslrootcert_keeps_require(self, temp_service_file):
        """Saving without sslrootcert keeps sslmode as-is (default: require)."""
        params = {
            "host": "test.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        }
        save_service_entry("myinst", params)

        entry = get_service_entry("myinst")
        assert entry["sslmode"] == "require"
        assert "sslrootcert" not in entry

    def test_get_entry_without_sslrootcert(self, temp_service_file):
        """Existing entries without sslrootcert don't include it in the dict."""
        params = {"host": "test.com", "port": 5432}
        save_service_entry("plain", params)

        entry = get_service_entry("plain")
        assert "sslrootcert" not in entry

    def test_upgrade_existing_entry_with_cert(self, temp_service_file):
        """An existing require entry can be upgraded to verify-ca."""
        params = {
            "host": "upgrade.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        }
        save_service_entry("upgrademe", params)

        # Verify it starts as require
        entry = get_service_entry("upgrademe")
        assert entry["sslmode"] == "require"

        # Upgrade with cert
        save_service_entry("upgrademe", entry, sslrootcert="/certs/account.pem")

        upgraded = get_service_entry("upgrademe")
        assert upgraded["sslmode"] == "verify-ca"
        assert upgraded["sslrootcert"] == "/certs/account.pem"
        # Other fields unchanged
        assert upgraded["host"] == "upgrade.snowflakecomputing.com"
        assert upgraded["user"] == "snowflake_admin"

    def test_sslrootcert_persists_in_file(self, temp_service_file):
        """sslrootcert is written to the actual file and survives reload."""
        params = {"host": "persist.com", "port": 5432}
        save_service_entry("persist", params, sslrootcert="/my/cert.pem")

        # Read raw file to verify format
        content = temp_service_file.read_text()
        assert "sslrootcert=/my/cert.pem" in content
        assert "sslmode=verify-ca" in content

    def test_overwrite_without_cert_removes_stale_sslrootcert(self, temp_service_file):
        """Re-saving without sslrootcert removes a previously written sslrootcert."""
        params = {"host": "downgrade.com", "port": 5432, "database": "postgres", "user": "snowflake_admin"}

        # First save with cert
        save_service_entry("downgrade", params, sslrootcert="/old/cert.pem")
        entry = get_service_entry("downgrade")
        assert entry["sslmode"] == "verify-ca"
        assert entry["sslrootcert"] == "/old/cert.pem"

        # Re-save without cert (e.g. user wants to revert to require)
        save_service_entry("downgrade", params)
        entry = get_service_entry("downgrade")
        assert entry["sslmode"] == "require"
        assert "sslrootcert" not in entry

        # Verify the raw file has no orphaned sslrootcert line
        content = temp_service_file.read_text()
        assert "sslrootcert" not in content


class TestCreateInstanceWithCert:
    """Tests that create_postgres_instance() fetches cert and saves with verify-ca."""

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        cert_dir = tmp_path / "certs"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        monkeypatch.setattr("pg_connect.CERT_DIR", cert_dir)
        monkeypatch.setattr(
            "pg_connect.probe_postgres_port",
            lambda host, port=5432, timeout=20: {
                "reachable": True,
                "status": "reachable",
                "message": f"Port {port} reachable on {host}",
            },
        )
        return {"service": service_file, "pgpass": pgpass_file, "certs": cert_dir}

    def _mock_create_response(self):
        """SQL result from CREATE POSTGRES INSTANCE."""
        return {
            "columns": ["status", "host", "access_roles", "default_database"],
            "rows": [[
                "Postgres instance creation initiated.",
                "abc.snowflakecomputing.com",
                json.dumps({"snowflake_admin": "admin_pass", "application": "app_pass"}),
                "postgres",
            ]],
        }

    def _mock_describe_response(self):
        """SQL result from DESCRIBE POSTGRES INSTANCE (with cert)."""
        return {
            "columns": ["property", "value"],
            "rows": [
                ["name", "MY_INST"],
                ["host", "abc.snowflakecomputing.com"],
                ["certificate", SAMPLE_PEM],
                ["status", "RUNNING"],
            ],
        }

    def test_create_fetches_cert_and_saves_verify_ca(self, temp_pg_files):
        """CREATE flow calls ensure_cert and sets sslmode=verify-ca in service file."""
        call_count = {"n": 0}
        def mock_sql(query, conn=None, auth=None, role=None):
            call_count["n"] += 1
            if "CREATE" in query:
                return self._mock_create_response()
            elif "DESCRIBE" in query:
                return self._mock_describe_response()
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            result = create_postgres_instance("MY_INST", "STANDARD_M", 10)

        assert result["cert_path"] is not None
        assert "certs/my_inst.pem" in result["cert_path"]

        entry = get_service_entry("my_inst")
        assert entry["sslmode"] == "verify-ca"
        assert entry["sslrootcert"] is not None

    def test_create_falls_back_to_require_if_cert_fails(self, temp_pg_files):
        """CREATE still works if cert fetch fails (DESCRIBE raises)."""
        def mock_sql(query, conn=None, auth=None, role=None):
            if "CREATE" in query:
                return self._mock_create_response()
            elif "DESCRIBE" in query:
                raise RuntimeError("Snowflake DESCRIBE failed")
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            result = create_postgres_instance("MY_INST", "STANDARD_M", 10)

        assert result["cert_path"] is None

        entry = get_service_entry("my_inst")
        assert entry["sslmode"] == "require"
        assert "sslrootcert" not in entry

    def test_create_uses_conn_info_port_for_probe(self, temp_pg_files):
        """CREATE probes the saved connection's port instead of assuming 5432."""
        captured = {}

        def fake_probe(host, port=5432, timeout=20):
            captured["host"] = host
            captured["port"] = port
            captured["timeout"] = timeout
            return {
                "reachable": True,
                "status": "reachable",
                "message": f"Port {port} reachable on {host}",
            }

        parsed_conn_info = {
            "host": "custom.example.com",
            "port": 6543,
            "database": "postgres",
            "user": "snowflake_admin",
            "password": "admin_pass",
            "sslmode": "require",
            "access_roles": [
                {"name": "snowflake_admin", "password": "admin_pass"},
                {"name": "application", "password": "app_pass"},
            ],
        }

        with (
            patch("pg_connect.execute_snowflake_sql", return_value=self._mock_create_response()),
            patch("pg_connect.parse_create_response", return_value=parsed_conn_info),
            patch("pg_connect.ensure_cert", return_value=None),
            patch("pg_connect.probe_postgres_port", side_effect=fake_probe),
        ):
            result = create_postgres_instance("MY_INST", "STANDARD_M", 10)

        assert captured == {"host": "custom.example.com", "port": 6543, "timeout": 20}
        assert result["probe"]["message"] == "Port 6543 reachable on custom.example.com"

        entry = get_service_entry("my_inst")
        assert entry["port"] == 6543


class TestCreateInstanceSQLGeneration:
    """Tests that create_postgres_instance() builds correct SQL for various param combos."""

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        cert_dir = tmp_path / "certs"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        monkeypatch.setattr("pg_connect.CERT_DIR", cert_dir)
        monkeypatch.setattr(
            "pg_connect.probe_postgres_port",
            lambda host, port=5432, timeout=20: {
                "reachable": True,
                "status": "reachable",
                "message": f"Port {port} reachable on {host}",
            },
        )
        return {"service": service_file, "pgpass": pgpass_file, "certs": cert_dir}

    def _mock_create_response(self):
        return {
            "columns": ["status", "host", "access_roles", "default_database"],
            "rows": [[
                "Postgres instance creation initiated.",
                "abc.snowflakecomputing.com",
                json.dumps({"snowflake_admin": "admin_pass", "application": "app_pass"}),
                "postgres",
            ]],
        }

    def _mock_describe_response(self):
        return {
            "columns": ["property", "value"],
            "rows": [["name", "INST"], ["host", "abc.snowflakecomputing.com"]],
        }

    def _capture_sql(self, **kwargs):
        """Run create_postgres_instance with mocks and return the SQL that was executed."""
        captured = {}
        def mock_sql(query, conn=None, auth=None, role=None):
            if "CREATE" in query:
                captured["sql"] = query
                return self._mock_create_response()
            elif "DESCRIBE" in query:
                return self._mock_describe_response()
            raise ValueError(f"Unexpected query: {query}")

        defaults = {"instance_name": "TEST_INST", "compute_pool": "STANDARD_M", "storage": 10}
        defaults.update(kwargs)
        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            create_postgres_instance(**defaults)
        return captured["sql"]

    def test_postgres_version_is_numeric(self, temp_pg_files):
        """POSTGRES_VERSION must be a bare integer, not a quoted string."""
        sql = self._capture_sql(postgres_version="18")
        assert "POSTGRES_VERSION = 18" in sql
        assert "POSTGRES_VERSION = '18'" not in sql

    def test_default_auth_authority(self, temp_pg_files):
        """Default auth authority is POSTGRES (unquoted keyword)."""
        sql = self._capture_sql()
        assert "AUTHENTICATION_AUTHORITY = POSTGRES" in sql

    def test_snowflake_token_auth(self, temp_pg_files):
        """POSTGRES_OR_SNOWFLAKE auth authority is passed through unquoted."""
        sql = self._capture_sql(auth_authority="POSTGRES_OR_SNOWFLAKE")
        assert "AUTHENTICATION_AUTHORITY = POSTGRES_OR_SNOWFLAKE" in sql

    def test_storage_integration(self, temp_pg_files):
        """Storage integration is quoted string."""
        sql = self._capture_sql(storage_integration="my_lake_int")
        assert "STORAGE_INTEGRATION = 'my_lake_int'" in sql

    def test_postgres_settings(self, temp_pg_files):
        """Postgres settings JSON is passed as quoted string."""
        settings = '{"postgres:work_mem": "128MB"}'
        sql = self._capture_sql(postgres_settings=settings)
        assert f"POSTGRES_SETTINGS = '{settings}'" in sql

    def test_comment(self, temp_pg_files):
        """Comment is quoted string."""
        sql = self._capture_sql(comment="Production billing")
        assert "COMMENT = 'Production billing'" in sql

    def test_all_optional_params(self, temp_pg_files):
        """All optional params appear in SQL when provided."""
        sql = self._capture_sql(
            postgres_version="17",
            enable_ha=True,
            network_policy="my_policy",
            auth_authority="POSTGRES_OR_SNOWFLAKE",
            storage_integration="lake_int",
            comment="test instance",
        )
        assert "POSTGRES_VERSION = 17" in sql
        assert "HIGH_AVAILABILITY = TRUE" in sql
        assert "NETWORK_POLICY = 'my_policy'" in sql
        assert "AUTHENTICATION_AUTHORITY = POSTGRES_OR_SNOWFLAKE" in sql
        assert "STORAGE_INTEGRATION = 'lake_int'" in sql
        assert "COMMENT = 'test instance'" in sql

    def test_network_policy_is_quoted(self, temp_pg_files):
        """Network policy is a quoted string (not a bare keyword)."""
        sql = self._capture_sql(network_policy="prod_ingress")
        assert "NETWORK_POLICY = 'prod_ingress'" in sql

    def test_compute_family_is_quoted(self, temp_pg_files):
        """Compute family is a quoted string."""
        sql = self._capture_sql(compute_pool="HIGHMEM_XL")
        assert "COMPUTE_FAMILY = 'HIGHMEM_XL'" in sql

    def test_storage_is_numeric(self, temp_pg_files):
        """Storage size is a bare integer."""
        sql = self._capture_sql(storage=500)
        assert "STORAGE_SIZE_GB = 500" in sql


class TestInputValidation:
    """Tests that SQL-interpolated parameters are validated against injection."""

    def test_validate_sql_string_rejects_single_quote(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            _validate_sql_string("test'; DROP TABLE x; --", "param")

    def test_validate_sql_string_rejects_semicolon(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            _validate_sql_string("value; DROP TABLE x", "param")

    def test_validate_sql_string_rejects_backslash(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            _validate_sql_string("value\\n", "param")

    def test_validate_sql_string_accepts_normal_values(self):
        _validate_sql_string("STANDARD_M", "compute_pool")
        _validate_sql_string("my_network_policy", "network_policy")
        _validate_sql_string('{"postgres:work_mem": "128MB"}', "postgres_settings")
        _validate_sql_string("Production billing instance", "comment")

    def test_create_rejects_invalid_auth_authority(self):
        with pytest.raises(ValueError, match="Invalid auth_authority"):
            create_postgres_instance("INST", "STANDARD_M", 10, auth_authority="INVALID")

    def test_create_rejects_non_numeric_version(self):
        with pytest.raises(ValueError, match="must be a number"):
            create_postgres_instance("INST", "STANDARD_M", 10, postgres_version="18; DROP")

    def test_create_rejects_injection_in_compute_pool(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            create_postgres_instance("INST", "STANDARD_M'; DROP TABLE x; --", 10)

    def test_create_rejects_injection_in_comment(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            create_postgres_instance("INST", "STANDARD_M", 10, comment="test'; DROP INSTANCE x; --")

    def test_create_rejects_injection_in_network_policy(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            create_postgres_instance("INST", "STANDARD_M", 10, network_policy="pol'; DROP x; --")

    def test_reset_rejects_injection_in_role(self):
        with pytest.raises(ValueError, match="Invalid characters"):
            reset_postgres_access("INST", role="admin'; DROP INSTANCE x; --")


class TestResetAccessSQL:
    """Tests that reset_postgres_access() uses correct SQL syntax."""

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        cert_dir = tmp_path / "certs"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        monkeypatch.setattr("pg_connect.CERT_DIR", cert_dir)
        return {"service": service_file, "pgpass": pgpass_file, "certs": cert_dir}

    def test_reset_uses_alter_postgres_instance(self, temp_pg_files):
        """RESET ACCESS must use ALTER POSTGRES INSTANCE, not ALTER POSTGRES SERVICE."""
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
        })

        captured = {}
        def mock_sql(query, conn=None, auth=None, role=None):
            if "RESET ACCESS" in query:
                captured["sql"] = query
                return {"columns": ["password"], "rows": [["new_pass"]]}
            elif "DESCRIBE" in query:
                return {"columns": ["property", "value"], "rows": []}
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            reset_postgres_access("MY_INST")

        assert "ALTER POSTGRES INSTANCE" in captured["sql"]
        assert "ALTER POSTGRES SERVICE" not in captured["sql"]


class TestResetWithCertUpgrade:
    """Tests that reset_postgres_access() upgrades to verify-ca when cert is missing."""

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        cert_dir = tmp_path / "certs"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        monkeypatch.setattr("pg_connect.CERT_DIR", cert_dir)
        return {"service": service_file, "pgpass": pgpass_file, "certs": cert_dir}

    def test_reset_upgrades_require_to_verify_ca(self, temp_pg_files):
        """RESET fetches cert and upgrades service entry from require to verify-ca."""
        # Pre-create a service entry with sslmode=require (no cert)
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        })

        def mock_sql(query, conn=None, auth=None, role=None):
            if "RESET ACCESS" in query:
                return {"columns": ["password"], "rows": [["new_pass"]]}
            elif "DESCRIBE" in query:
                return {
                    "columns": ["property", "value"],
                    "rows": [
                        ["name", "MY_INST"],
                        ["host", "abc.snowflakecomputing.com"],
                        ["certificate", SAMPLE_PEM],
                    ],
                }
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            result = reset_postgres_access("MY_INST")

        assert result["success"] is True
        assert result["cert_upgraded"] is True

        entry = get_service_entry("my_inst")
        assert entry["sslmode"] == "verify-ca"
        assert entry.get("sslrootcert") is not None

    def test_reset_skips_cert_if_already_verified(self, temp_pg_files):
        """RESET does not re-fetch cert if service entry already has sslrootcert."""
        # Pre-create with verify-ca
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
        }, sslrootcert="/existing/cert.pem")

        def mock_sql(query, conn=None, auth=None, role=None):
            if "RESET ACCESS" in query:
                return {"columns": ["password"], "rows": [["new_pass"]]}
            elif "DESCRIBE" in query:
                # Should NOT be called
                raise AssertionError("DESCRIBE should not be called when cert exists")
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            result = reset_postgres_access("MY_INST")

        assert result["success"] is True
        assert result["cert_upgraded"] is False


class TestCategorizeConnectionErrorCert:
    """Tests for cert-specific error categorization."""

    def test_certificate_verify_failed(self):
        """Detects SSL certificate verification failure."""
        err = Exception("SSL error: certificate verify failed")
        msg = categorize_connection_error(err, {"host": "x"})
        assert "certificate verification failed" in msg.lower()
        assert "--fetch-cert" in msg

    def test_generic_ssl_suggests_fetch_cert(self):
        """Generic SSL error now mentions --fetch-cert for upgrade."""
        err = Exception("SSL SYSCALL error: EOF detected")
        msg = categorize_connection_error(err, {"host": "x"})
        assert "--fetch-cert" in msg


class TestProbeStatusContract:
    """Lock the probe-status keyword contract.

    manage/SKILL.md Step 7 has a probe-outcome table that references the exact
    strings produced by pg_connect.probe_postgres_port. If these keywords drift
    without updating the docs, the agent guidance stops matching the script
    output. These tests fail loudly when either side is changed in isolation.
    """

    def test_probe_status_values(self):
        """probe_postgres_port returns one of four documented status values."""
        from pg_connect import probe_postgres_port
        allowed = {"reachable", "timeout", "refused", "dns_error", "error"}

        result = probe_postgres_port(
            "this-host-definitely-does-not-exist-abc123.invalid",
            port=5432,
            timeout=2,
        )
        assert result["status"] in allowed
        assert "reachable" in result
        assert "message" in result

    def test_probe_timeout_message_keywords(self):
        """Timeout message mentions 'timed out' — referenced by manage/SKILL.md Step 7."""
        from pg_connect import probe_postgres_port
        result = probe_postgres_port("192.0.2.1", port=5432, timeout=2)
        if result["status"] == "timeout":
            assert "timed out" in result["message"].lower()

    def test_probe_dns_error_message_keywords(self):
        """DNS error message mentions 'DNS' — referenced by manage/SKILL.md Step 7."""
        from pg_connect import probe_postgres_port
        result = probe_postgres_port(
            "this-host-definitely-does-not-exist-abc123.invalid",
            port=5432,
            timeout=2,
        )
        if result["status"] == "dns_error":
            assert "dns" in result["message"].lower()


class TestTranslateSnowflakeError:
    """Tests for translate_snowflake_error — agent-facing error guidance."""

    def test_insufficient_privileges_suggests_use_role(self):
        """Privilege errors point the agent at --use-role ACCOUNTADMIN."""
        from pg_connect import translate_snowflake_error
        err = Exception("Insufficient privileges to operate on account 'X'")
        msg = translate_snowflake_error(err, current_role="ANALYST_ROLE")
        assert msg is not None
        assert "ANALYST_ROLE" in msg
        assert "--use-role" in msg
        assert "ACCOUNTADMIN" in msg

    def test_insufficient_privileges_without_current_role(self):
        """Works even if current_role isn't passed."""
        from pg_connect import translate_snowflake_error
        err = Exception("Insufficient privileges to operate on account")
        msg = translate_snowflake_error(err)
        assert msg is not None
        assert "--use-role" in msg

    def test_backend_iam_error(self):
        """team_iam_role_arn_not_found gets soft backend guidance."""
        from pg_connect import translate_snowflake_error
        err = Exception(
            "INTERNAL_ERROR: PostgresUtils::getOrCreateTeamAndTeamIamRole():"
            "team_iam_role_arn_not_found for accountId=2057"
        )
        msg = translate_snowflake_error(err)
        assert msg is not None
        assert "internal error" in msg.lower()
        assert "retry once" in msg.lower()
        assert "exact error text" in msg.lower()

    def test_internal_error_gets_soft_guidance(self):
        """Generic INTERNAL_ERROR gets guidance without a hard root-cause claim."""
        from pg_connect import translate_snowflake_error
        err = Exception("INTERNAL_ERROR: Postgres service failed during operation")
        msg = translate_snowflake_error(err)
        assert msg is not None
        assert "internal error" in msg.lower()
        assert "retry once" in msg.lower()
        assert "supports snowflake postgres" in msg.lower()

    def test_feature_not_enabled_unsupported(self):
        """'unsupported feature' hints that Postgres isn't enabled on the account."""
        from pg_connect import translate_snowflake_error
        err = Exception("Unsupported feature 'POSTGRES INSTANCE'")
        msg = translate_snowflake_error(err)
        assert msg is not None
        assert "not be enabled" in msg

    def test_feature_not_enabled_syntax_error_near_postgres(self):
        """Parser rejection of the POSTGRES keyword gets feature-availability guidance."""
        from pg_connect import translate_snowflake_error
        err = Exception("SQL compilation error: syntax error near POSTGRES")
        msg = translate_snowflake_error(err)
        assert msg is not None
        assert "not be enabled" in msg

    def test_generic_syntax_error_with_postgres_context_returns_none(self):
        """Generic syntax errors that merely mention postgres should pass through."""
        from pg_connect import translate_snowflake_error
        err = Exception(
            "SQL compilation error: syntax error line 1 at position 7 unexpected 'FROM' "
            "while building a postgres health query"
        )
        assert translate_snowflake_error(err) is None

    def test_unknown_error_returns_none(self):
        """Unrecognized errors pass through — caller surfaces the raw text."""
        from pg_connect import translate_snowflake_error
        err = Exception("some other unrelated failure")
        assert translate_snowflake_error(err) is None


class TestUseRolePlumbing:
    """Verify --use-role reaches the Snowflake connector as `role=<ROLE>`.

    Regression net for accidental arg-dropping when refactoring the
    Snowflake-connection call chain.
    """

    def test_get_snowflake_connection_passes_role(self, tmp_path, monkeypatch):
        from pg_connect import get_snowflake_connection
        connections_toml = tmp_path / "connections.toml"
        connections_toml.write_text(
            'default_connection_name = "test"\n'
            '[test]\n'
            'account = "acct"\n'
            'user = "usr"\n'
            'password = "pw"\n'
        )
        monkeypatch.setattr("pg_connect._SF_CONNECTIONS_TOML", connections_toml)
        monkeypatch.setattr("pg_connect._SF_CONFIG_TOML", tmp_path / "config.toml")
        for var in ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_ROLE"):
            monkeypatch.delenv(var, raising=False)

        captured = {}

        def fake_connect(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr("snowflake.connector.connect", fake_connect)
        get_snowflake_connection(role="ACCOUNTADMIN")
        assert captured.get("role") == "ACCOUNTADMIN"

    def test_get_snowflake_connection_env_vars_with_role(self, monkeypatch):
        from pg_connect import get_snowflake_connection
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
        monkeypatch.setenv("SNOWFLAKE_USER", "usr")
        monkeypatch.setenv("SNOWFLAKE_PASSWORD", "pw")
        monkeypatch.delenv("SNOWFLAKE_ROLE", raising=False)

        captured = {}

        def fake_connect(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr("snowflake.connector.connect", fake_connect)
        get_snowflake_connection(role="SYSADMIN")
        assert captured.get("role") == "SYSADMIN"

    def test_get_snowflake_connection_env_var_role_default(self, monkeypatch):
        """SNOWFLAKE_ROLE env var is honored when no explicit role is passed."""
        from pg_connect import get_snowflake_connection
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "acct")
        monkeypatch.setenv("SNOWFLAKE_USER", "usr")
        monkeypatch.setenv("SNOWFLAKE_PASSWORD", "pw")
        monkeypatch.setenv("SNOWFLAKE_ROLE", "ENV_ROLE")

        captured = {}

        def fake_connect(**kwargs):
            captured.update(kwargs)
            return MagicMock()

        monkeypatch.setattr("snowflake.connector.connect", fake_connect)
        get_snowflake_connection()
        assert captured.get("role") == "ENV_ROLE"


class TestCliTestSavedConnection:
    """Tests that `pg_connect.py --test --connection-name <name>` looks up a
    saved connection rather than silently doing nothing. This supports the
    non-Snowflake Postgres flow where users save a connection to
    ~/.pg_service.conf and want to validate it without re-supplying the
    connection string.
    """

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        return {"service": service_file, "pgpass": pgpass_file}

    def test_test_unknown_saved_name_reports_not_found(self, temp_pg_files):
        """--test --connection-name <missing> returns a clear not-found message."""
        import subprocess
        import sys
        script = Path(__file__).parent.parent / "scripts" / "pg_connect.py"
        env = {**os.environ, "HOME": str(temp_pg_files["service"].parent)}
        result = subprocess.run(
            [sys.executable, str(script), "--test", "--connection-name", "does_not_exist"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode == 1
        assert "No saved connection named 'does_not_exist'" in result.stdout

    def test_test_no_args_suggests_required_flags(self, temp_pg_files):
        """--test with no connection args reports which flags are needed."""
        import subprocess
        import sys
        script = Path(__file__).parent.parent / "scripts" / "pg_connect.py"
        env = {**os.environ, "HOME": str(temp_pg_files["service"].parent)}
        result = subprocess.run(
            [sys.executable, str(script), "--test"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode == 1
        combined = result.stdout + result.stderr
        assert "--connection" in combined
        assert "--connection-name" in combined


class TestExecuteSnowflakeSqlRoutesThroughSession:
    """execute_snowflake_sql() dispatches through SnowflakeSession so
    --create, --reset, and --fetch-cert all work on hosts that only have the
    `snow` CLI (Windows ARM64). These tests pin the dispatch + shape contract
    without touching a real Snowflake account or backend."""

    def test_routes_through_snowflake_session(self):
        """The function builds a SnowflakeSession with the right kwargs and
        forwards the SQL to .execute()."""
        from pg_connect import execute_snowflake_sql

        fake_session = MagicMock()
        fake_session.__enter__ = MagicMock(return_value=fake_session)
        fake_session.__exit__ = MagicMock(return_value=False)
        fake_session.execute.return_value = [{"state": "READY", "name": "x"}]

        with patch("sf_session.SnowflakeSession", return_value=fake_session) as ctor:
            result = execute_snowflake_sql(
                "DESCRIBE POSTGRES INSTANCE x",
                connection_name="prod",
                authenticator="externalbrowser",
                role="ACCOUNTADMIN",
            )

        ctor.assert_called_once_with(
            connection="prod", role="ACCOUNTADMIN", authenticator="externalbrowser",
        )
        fake_session.execute.assert_called_once_with("DESCRIBE POSTGRES INSTANCE x")
        assert result == {
            "query": "DESCRIBE POSTGRES INSTANCE x",
            "columns": ["state", "name"],
            "rows": [("READY", "x")],
        }

    def test_empty_result_set_returns_empty_columns_and_rows(self):
        """DDL / no-rowset statements (e.g. CREATE POSTGRES INSTANCE returning
        an empty set in some cases) yield columns=[] and rows=[] without
        blowing up the shape reconstruction."""
        from pg_connect import execute_snowflake_sql

        fake_session = MagicMock()
        fake_session.__enter__ = MagicMock(return_value=fake_session)
        fake_session.__exit__ = MagicMock(return_value=False)
        fake_session.execute.return_value = []

        with patch("sf_session.SnowflakeSession", return_value=fake_session):
            result = execute_snowflake_sql("ALTER POSTGRES INSTANCE x RESUME")

        assert result == {
            "query": "ALTER POSTGRES INSTANCE x RESUME",
            "columns": [],
            "rows": [],
        }

    def test_session_is_closed_on_exception(self):
        """SnowflakeSession context manager exit fires even when .execute
        raises so the underlying connection (connector path) is released."""
        from pg_connect import execute_snowflake_sql

        fake_session = MagicMock()
        fake_session.__enter__ = MagicMock(return_value=fake_session)
        fake_session.__exit__ = MagicMock(return_value=False)
        fake_session.execute.side_effect = RuntimeError("boom")

        with patch("sf_session.SnowflakeSession", return_value=fake_session):
            with pytest.raises(RuntimeError, match="boom"):
                execute_snowflake_sql("SELECT 1")

        fake_session.__exit__.assert_called_once()


class TestTempPathsArePortable:
    """create_postgres_instance and reset_postgres_access write a debug JSON
    response to a temp file. The hardcoded `/tmp/` path that used to live
    here doesn't exist on native Windows; the OS-default tmpdir does."""

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service = tmp_path / ".pg_service.conf"
        pgpass = tmp_path / ".pgpass"
        certs = tmp_path / "certs"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass)
        monkeypatch.setattr("pg_connect.CERT_DIR", certs)
        return {"service": service, "pgpass": pgpass, "certs": certs}

    def _mock_create_response(self):
        return {
            "query": "CREATE",
            "columns": ["host", "access_roles"],
            "rows": [(
                "abc.snowflakecomputing.com",
                json.dumps({"snowflake_admin": "p"}),
            )],
        }

    def test_create_writes_response_under_tempfile_gettempdir(
        self, tmp_path, monkeypatch, temp_pg_files,
    ):
        """The response JSON is written under tempfile.gettempdir(), so
        native Windows hosts (no `/tmp/`) work the same as macOS / Linux."""
        fake_tmpdir = tmp_path / "fake_tmp"
        fake_tmpdir.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(fake_tmpdir))

        with (
            patch(
                "pg_connect.execute_snowflake_sql",
                return_value=self._mock_create_response(),
            ),
            patch("pg_connect.ensure_cert", return_value=None),
            patch(
                "pg_connect.probe_postgres_port",
                return_value={"reachable": True, "status": "reachable", "message": ""},
            ),
        ):
            create_postgres_instance("MY_INST", "STANDARD_M", 10)

        expected = fake_tmpdir / "pg_create_MY_INST.json"
        assert expected.exists(), (
            f"Expected debug JSON at {expected}, got {list(fake_tmpdir.iterdir())}"
        )

    def test_reset_writes_response_under_tempfile_gettempdir(
        self, tmp_path, monkeypatch, temp_pg_files,
    ):
        fake_tmpdir = tmp_path / "fake_tmp"
        fake_tmpdir.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(fake_tmpdir))

        # Seed an existing service entry so reset_postgres_access takes the
        # happy path rather than asking for --host.
        save_service_entry("my_inst", {
            "host": "h.example.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        })

        reset_response = {
            "query": "ALTER",
            "columns": ["password"],
            "rows": [("newpw",)],
        }
        with (
            patch("pg_connect.execute_snowflake_sql", return_value=reset_response),
            patch("pg_connect.ensure_cert", return_value=None),
        ):
            reset_postgres_access("MY_INST")

        expected = fake_tmpdir / "pg_reset_MY_INST.json"
        assert expected.exists(), (
            f"Expected debug JSON at {expected}, got {list(fake_tmpdir.iterdir())}"
        )


class TestValidateConnection:
    """Tests for validate_connection (the `pg_connect.py --test` path)."""

    PARAMS = {
        "host": "h.example.com",
        "port": 5432,
        "database": "postgres",
        "user": "snowflake_admin",
        "password": "pw",
        "sslmode": "require",
    }

    def test_success_closes_connection(self):
        """Happy path: connects via pg_common, closes, reports success."""
        fake_conn = MagicMock()
        with patch("pg_connect.pg_common.connect", return_value=fake_conn) as conn:
            ok, msg = validate_connection(dict(self.PARAMS))
        assert ok is True
        assert msg == "Connection successful"
        conn.assert_called_once()
        fake_conn.close.assert_called_once()

    def test_pgerror_is_categorized(self):
        """A driver PgError is caught and turned into a friendly message."""
        with (
            patch("pg_connect.pg_common.connect", side_effect=pg_connect.pg_common.PgError("boom")),
            patch("pg_connect.categorize_connection_error", return_value="categorized"),
        ):
            ok, msg = validate_connection(dict(self.PARAMS))
        assert ok is False
        assert msg == "categorized"

    def test_module_binds_pg_common(self):
        """Regression: validate_connection references pg_common.* — the module
        name must be bound, not just specific names imported from it."""
        assert hasattr(pg_connect, "pg_common")


class TestTargetDatabaseSelection:
    """The saved connection must point at whatever Postgres database the user's
    tables live in — not always the `postgres` default.

    Regression net for the live-mirror bug (R1/H1): source tables were in
    `appdb`, but --reset/--create always saved a service entry for `postgres`,
    so the preflight connection reached the wrong database and auth/connect
    failed. The default stays `postgres` (a real instance always has it and
    most users use it); --database just lets any other database be selected.
    """

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        cert_dir = tmp_path / "certs"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        monkeypatch.setattr("pg_connect.CERT_DIR", cert_dir)
        monkeypatch.setattr(
            "pg_connect.probe_postgres_port",
            lambda host, port=5432, timeout=20: {
                "reachable": True,
                "status": "reachable",
                "message": f"Port {port} reachable on {host}",
            },
        )
        return {"service": service_file, "pgpass": pgpass_file, "certs": cert_dir}

    def _mock_create_response(self):
        return {
            "columns": ["status", "host", "access_roles", "default_database"],
            "rows": [[
                "Postgres instance creation initiated.",
                "abc.snowflakecomputing.com",
                json.dumps({"snowflake_admin": "admin_pass", "application": "app_pass"}),
                "postgres",
            ]],
        }

    # --- --create --------------------------------------------------------

    def test_create_defaults_to_postgres(self, temp_pg_files):
        """Default (no database arg) keeps the historical `postgres` target."""
        with (
            patch("pg_connect.execute_snowflake_sql", return_value=self._mock_create_response()),
            patch("pg_connect.ensure_cert", return_value=None),
        ):
            create_postgres_instance("MY_INST", "STANDARD_M", 10)

        entry = get_service_entry("my_inst")
        assert entry["database"] == "postgres"
        assert find_pgpass_entry("abc.snowflakecomputing.com", 5432, "postgres", "snowflake_admin")

    def test_create_honors_explicit_database(self, temp_pg_files):
        """--database appdb makes the saved service entry + pgpass rows target appdb."""
        with (
            patch("pg_connect.execute_snowflake_sql", return_value=self._mock_create_response()),
            patch("pg_connect.ensure_cert", return_value=None),
        ):
            create_postgres_instance("MY_INST", "STANDARD_M", 10, database="appdb")

        entry = get_service_entry("my_inst")
        assert entry["database"] == "appdb"
        # pgpass row is written for appdb, not postgres
        assert find_pgpass_entry("abc.snowflakecomputing.com", 5432, "appdb", "snowflake_admin")
        assert find_pgpass_entry("abc.snowflakecomputing.com", 5432, "postgres", "snowflake_admin") is None

    # --- --reset ---------------------------------------------------------

    def test_reset_new_entry_defaults_to_postgres(self, temp_pg_files):
        """--reset --host with no database creates a postgres service entry."""
        def mock_sql(query, conn=None, auth=None, role=None):
            if "RESET ACCESS" in query:
                return {"columns": ["password"], "rows": [["new_pass"]]}
            elif "DESCRIBE" in query:
                return {"columns": ["property", "value"], "rows": []}
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            result = reset_postgres_access("MY_INST", host="abc.snowflakecomputing.com")

        assert result["success"] is True
        entry = get_service_entry("my_inst")
        assert entry["database"] == "postgres"
        assert find_pgpass_entry("abc.snowflakecomputing.com", 5432, "postgres", "snowflake_admin")

    def test_reset_new_entry_honors_explicit_database(self, temp_pg_files):
        """--reset --host --database appdb creates an appdb-targeted entry + pgpass row."""
        def mock_sql(query, conn=None, auth=None, role=None):
            if "RESET ACCESS" in query:
                return {"columns": ["password"], "rows": [["new_pass"]]}
            elif "DESCRIBE" in query:
                return {"columns": ["property", "value"], "rows": []}
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            result = reset_postgres_access(
                "MY_INST", host="abc.snowflakecomputing.com", database="appdb",
            )

        assert result["success"] is True
        entry = get_service_entry("my_inst")
        assert entry["database"] == "appdb"
        # The password row is written under the same database as the service entry
        assert find_pgpass_entry("abc.snowflakecomputing.com", 5432, "appdb", "snowflake_admin")

    def test_reset_existing_entry_leaves_database_untouched(self, temp_pg_files):
        """Resetting an existing connection only rotates the password; the saved
        database is not changed by a stray --database (backward compatible)."""
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "appdb",
            "user": "snowflake_admin",
            "sslmode": "require",
        })

        def mock_sql(query, conn=None, auth=None, role=None):
            if "RESET ACCESS" in query:
                return {"columns": ["password"], "rows": [["new_pass"]]}
            elif "DESCRIBE" in query:
                return {"columns": ["property", "value"], "rows": []}
            raise ValueError(f"Unexpected query: {query}")

        with patch("pg_connect.execute_snowflake_sql", side_effect=mock_sql):
            reset_postgres_access("MY_INST", database="postgres")

        entry = get_service_entry("my_inst")
        assert entry["database"] == "appdb"
        # Password row updated under the entry's own database (appdb)
        row = find_pgpass_entry("abc.snowflakecomputing.com", 5432, "appdb", "snowflake_admin")
        assert row is not None
        assert row["password"] == "new_pass"

    # --- --connection <url> --save (params-path override) ----------------

    def test_save_connection_url_database_preserved(self, temp_pg_files):
        """A connection-string db is preserved when --database is omitted."""
        params = pg_connect.parse_connection_string(
            "postgres://user:pw@h.example.com:5432/appdb?sslmode=require"
        )
        assert params["database"] == "appdb"
        save_connection("urlconn", params)
        entry = get_service_entry("urlconn")
        assert entry["database"] == "appdb"

    # --- repoint_connection_database (used by --ensure-ready --database) --

    def test_repoint_updates_service_and_pgpass(self, temp_pg_files):
        """Repointing moves the service entry + pgpass row to the new database."""
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        })
        upsert_pgpass_entry("abc.snowflakecomputing.com", 5432, "postgres", "snowflake_admin", "pw123")

        changed = pg_connect.repoint_connection_database("my_inst", "appdb")
        assert changed is True

        entry = get_service_entry("my_inst")
        assert entry["database"] == "appdb"
        # Password is now discoverable under the new database
        row = find_pgpass_entry("abc.snowflakecomputing.com", 5432, "appdb", "snowflake_admin")
        assert row is not None
        assert row["password"] == "pw123"

    def test_repoint_noop_when_same_database(self, temp_pg_files):
        """Repointing to the current database is a no-op (returns False)."""
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "appdb",
            "user": "snowflake_admin",
            "sslmode": "require",
        })
        assert pg_connect.repoint_connection_database("my_inst", "appdb") is False

    def test_repoint_missing_connection_returns_false(self, temp_pg_files):
        """Repointing an unknown connection is a safe no-op."""
        assert pg_connect.repoint_connection_database("nope", "appdb") is False

    def test_repoint_preserves_verify_ca(self, temp_pg_files):
        """Repointing keeps an existing verify-ca sslrootcert on the entry."""
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
        }, sslrootcert="/certs/acct.pem")

        pg_connect.repoint_connection_database("my_inst", "appdb")
        entry = get_service_entry("my_inst")
        assert entry["database"] == "appdb"
        assert entry["sslmode"] == "verify-ca"
        assert entry["sslrootcert"] == "/certs/acct.pem"


class TestDatabaseFlagCLI:
    """End-to-end CLI coverage that --database threads into the saved service
    entry via the argparse plumbing (default postgres; explicit override).

    Uses the --from-response --save path so no Snowflake account is touched.
    """

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        return {"service": service_file, "pgpass": pgpass_file}

    def _run(self, args, temp_pg_files, tmp_path):
        import subprocess
        response_file = tmp_path / "create_response.json"
        response_file.write_text(json.dumps({
            "columns": ["status", "host", "access_roles", "default_database"],
            "rows": [[
                "Instance created.",
                "cli.snowflakecomputing.com",
                json.dumps({"snowflake_admin": "CLI_ADMIN_PW"}),
                "postgres",
            ]],
        }))
        script = Path(__file__).parent.parent / "scripts" / "pg_connect.py"
        env = os.environ.copy()
        # pg_common resolves ~/.pg_service.conf and ~/.pgpass from Path.home(),
        # so point HOME at the temp dir (matching TestCliTestSavedConnection).
        env["HOME"] = str(temp_pg_files["service"].parent)
        return subprocess.run(
            [sys.executable, str(script), "--from-response", str(response_file),
             "--connection-name", "cli_conn", "--save", *args],
            capture_output=True, text=True, env=env, timeout=15, check=False,
        )

    def test_cli_default_database_is_postgres(self, temp_pg_files, tmp_path):
        result = self._run([], temp_pg_files, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        entry = get_service_entry("cli_conn")
        assert entry["database"] == "postgres"
        # Secret never echoed
        assert "CLI_ADMIN_PW" not in (result.stdout + result.stderr)

    def test_cli_database_flag_is_honored(self, temp_pg_files, tmp_path):
        result = self._run(["--database", "appdb"], temp_pg_files, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        entry = get_service_entry("cli_conn")
        assert entry["database"] == "appdb"
        assert find_pgpass_entry("cli.snowflakecomputing.com", 5432, "appdb", "snowflake_admin")
        assert "CLI_ADMIN_PW" not in (result.stdout + result.stderr)

    def test_cli_dbname_alias_is_honored(self, temp_pg_files, tmp_path):
        result = self._run(["--dbname", "reporting"], temp_pg_files, tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        entry = get_service_entry("cli_conn")
        assert entry["database"] == "reporting"

    def test_cli_database_overrides_url_dbname(self, temp_pg_files, tmp_path):
        """Explicit --database wins over the database named in a connection URL."""
        script = Path(__file__).parent.parent / "scripts" / "pg_connect.py"
        env = os.environ.copy()
        env["HOME"] = str(temp_pg_files["service"].parent)
        result = subprocess.run(
            [sys.executable, str(script),
             "--connection", "postgres://user:pw@h.example.com:5432/db_from_url",
             "--connection-name", "url_conn", "--save",
             "--database", "db_override"],
            capture_output=True, text=True, env=env, timeout=15, check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        entry = get_service_entry("url_conn")
        assert entry["database"] == "db_override"
        assert find_pgpass_entry("h.example.com", 5432, "db_override", "user")
        assert find_pgpass_entry("h.example.com", 5432, "db_from_url", "user") is None

    def test_cli_rejects_database_with_newline(self, temp_pg_files, tmp_path):
        result = self._run(["--database", "appdb\nattacker"], temp_pg_files, tmp_path)
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "control characters" in combined.lower() or "Invalid database" in combined
        assert get_service_entry("cli_conn") is None


class TestEnsureReadyRepointsDatabase:
    """`pg_connect.py --ensure-ready --database <db>` repoints the saved
    connection so the SKILL.md preflight example (which pairs --ensure-ready
    with --database <POSTGRES_DATABASE>) actually reaches the right database
    instead of the flag being silently ignored.
    """

    @pytest.fixture
    def temp_pg_files(self, tmp_path, monkeypatch):
        service_file = tmp_path / ".pg_service.conf"
        pgpass_file = tmp_path / ".pgpass"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", service_file)
        monkeypatch.setattr("pg_common.PGPASS_FILE", pgpass_file)
        return {"service": service_file, "pgpass": pgpass_file}

    def test_ensure_ready_repoints_saved_connection(self, temp_pg_files, monkeypatch):
        # Seed a saved connection for the instance, pointing at postgres.
        save_service_entry("my_inst", {
            "host": "abc.snowflakecomputing.com",
            "port": 5432,
            "database": "postgres",
            "user": "snowflake_admin",
            "sslmode": "require",
        })
        upsert_pgpass_entry("abc.snowflakecomputing.com", 5432, "postgres", "snowflake_admin", "pw")

        monkeypatch.setattr(
            "pg_connect.ensure_instance_ready",
            lambda **kw: {"success": True, "instance": "MY_INST", "state": "READY",
                          "resumed": False, "waited_seconds": 0},
        )
        monkeypatch.setattr(
            sys, "argv",
            ["pg_connect.py", "--ensure-ready", "--instance-name", "MY_INST",
             "--database", "appdb", "--connection-name", "my_inst"],
        )

        with pytest.raises(SystemExit) as exc:
            pg_connect.main()
        assert exc.value.code == 0

        entry = get_service_entry("my_inst")
        assert entry["database"] == "appdb"
        assert find_pgpass_entry("abc.snowflakecomputing.com", 5432, "appdb", "snowflake_admin")
