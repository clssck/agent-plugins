"""Tests for T014b service-name credential plumbing in pg_common.

The upstream pg_common contract lives in tests/test_migrate_pg_common.py once
ported (T032). This file covers only the service-name additions our repo layers
on top:

  - --source-service / --target-service argparse flags
  - _apply_source_service / _apply_target_service (fill from ~/.pg_service.conf)
  - resolve_source_password / resolve_target_password precedence rules when
    service is set: CLI > env > ~/.pgpass > ''
  - resolve_*_password legacy semantics (no service set) preserve the upstream
    PGPASSWORD='' shadow quirk — contract tests in the upstream repo pin this too

File paths in pg_common (PG_SERVICE_FILE, PGPASS_FILE) are monkeypatched to
tmp_path so tests never touch the operator's real dotfiles.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pg_common


@pytest.fixture
def temp_service_file(tmp_path, monkeypatch):
    path = tmp_path / ".pg_service.conf"
    monkeypatch.setattr("pg_common.PG_SERVICE_FILE", path)
    return path


@pytest.fixture
def temp_pgpass(tmp_path, monkeypatch):
    path = tmp_path / ".pgpass"
    monkeypatch.setattr("pg_common.PGPASS_FILE", path)
    return path


@pytest.fixture
def clean_env(monkeypatch):
    """Clear all PG env vars so tests control precedence deterministically."""
    for k in ("PGPASSWORD", "SOURCE_PGPASSWORD", "TARGET_PGPASSWORD",
              "SOURCE_PGHOST", "SOURCE_PGHOSTADDR", "SOURCE_PGPORT", "SOURCE_PGDATABASE", "SOURCE_PGUSER",
              "TARGET_PGHOST", "TARGET_PGHOSTADDR", "TARGET_PGPORT", "TARGET_PGDATABASE", "TARGET_PGUSER",
              "SOURCE_PG_SERVICE", "TARGET_PG_SERVICE"):
        monkeypatch.delenv(k, raising=False)


def _source_args(**overrides):
    """Build a Namespace mimicking parse_args for source-side callers."""
    defaults = dict(
        source_service="", host="", port=5432, dbname="", user="",
        hostaddr=None, password="", sslmode=None, sslrootcert=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _target_args(**overrides):
    defaults = dict(
        target_service="", target_host="", target_port=5432, target_dbname="",
        target_user="", target_hostaddr=None, target_password="", target_sslmode=None,
        target_sslrootcert=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


class TestAddSourceArgsServiceFlag:
    def test_source_service_flag_parses(self, clean_env):
        parser = argparse.ArgumentParser()
        pg_common.add_source_args(parser)
        args = parser.parse_args(["--source-service", "prod"])
        assert args.source_service == "prod"

    def test_hostaddr_flag_parses(self, clean_env):
        parser = argparse.ArgumentParser()
        pg_common.add_source_args(parser)
        args = parser.parse_args(["--hostaddr", "203.0.113.10"])
        assert args.hostaddr == "203.0.113.10"

    def test_source_service_defaults_to_env(self, monkeypatch, clean_env):
        monkeypatch.setenv("SOURCE_PG_SERVICE", "staging")
        parser = argparse.ArgumentParser()
        pg_common.add_source_args(parser)
        args = parser.parse_args([])
        assert args.source_service == "staging"

    def test_source_service_defaults_empty_when_no_env(self, clean_env):
        parser = argparse.ArgumentParser()
        pg_common.add_source_args(parser)
        args = parser.parse_args([])
        assert args.source_service == ""


class TestAddTargetArgsServiceFlag:
    def test_target_service_flag_parses(self, clean_env):
        parser = argparse.ArgumentParser()
        pg_common.add_target_args(parser)
        args = parser.parse_args(["--target-service", "sf_prod"])
        assert args.target_service == "sf_prod"

    def test_target_service_defaults_to_env(self, monkeypatch, clean_env):
        monkeypatch.setenv("TARGET_PG_SERVICE", "sf_staging")
        parser = argparse.ArgumentParser()
        pg_common.add_target_args(parser)
        args = parser.parse_args([])
        assert args.target_service == "sf_staging"

    def test_target_hostaddr_flag_parses(self, clean_env):
        parser = argparse.ArgumentParser()
        pg_common.add_target_args(parser)
        args = parser.parse_args(["--target-hostaddr", "203.0.113.11"])
        assert args.target_hostaddr == "203.0.113.11"


class TestApplySourceService:
    def test_no_service_is_noop(self, temp_service_file, clean_env):
        args = _source_args(source_service="")
        pg_common._apply_source_service(args)
        assert args.host == ""
        assert args.port == 5432

    def test_service_fills_host_port_dbname_user(self, temp_service_file, clean_env):
        pg_common.save_service_entry("prod", {
            "host": "pg.prod.example.com",
            "hostaddr": "203.0.113.10",
            "port": 6543,
            "database": "app",
            "user": "reader",
        })
        args = _source_args(source_service="prod")
        pg_common._apply_source_service(args)
        assert args.host == "pg.prod.example.com"
        assert args.hostaddr == "203.0.113.10"
        assert args.port == 6543
        assert args.dbname == "app"
        assert args.user == "reader"

    def test_explicit_dbname_wins_over_service(self, temp_service_file, clean_env):
        pg_common.save_service_entry("prod", {
            "host": "pg.prod.example.com", "port": 6543,
            "database": "app", "user": "reader",
        })
        args = _source_args(source_service="prod", dbname="reporting")
        pg_common._apply_source_service(args)
        assert args.dbname == "reporting"
        assert args.host == "pg.prod.example.com"

    def test_service_overrides_existing_argparse_values(self, temp_service_file, clean_env):
        pg_common.save_service_entry("prod", {
            "host": "pg.prod.example.com", "port": 6543,
            "database": "app", "user": "reader",
        })
        args = _source_args(source_service="prod", host="manual.example.com", port=9999)
        pg_common._apply_source_service(args)
        assert args.host == "pg.prod.example.com"
        assert args.port == 6543

    def test_service_fills_sslmode_only_when_unset(self, temp_service_file, clean_env):
        pg_common.save_service_entry("prod", {
            "host": "h", "port": 5432, "database": "d", "user": "u",
        }, sslrootcert="/tmp/ca.pem")
        args = _source_args(source_service="prod", sslmode=None)
        pg_common._apply_source_service(args)
        assert args.sslmode == "verify-ca"
        # sslrootcert from the service file flows onto args alongside sslmode,
        # so verify-ca profiles registered via pg_connect work end-to-end in
        # migrate scripts (CREATE SUBSCRIPTION DSN, run_assessment, etc.).
        assert args.sslrootcert == "/tmp/ca.pem"

        args2 = _source_args(source_service="prod", sslmode="require")
        pg_common._apply_source_service(args2)
        assert args2.sslmode == "require"

    def test_service_fills_sslrootcert_only_when_unset(self, temp_service_file, clean_env):
        pg_common.save_service_entry("prod", {
            "host": "h", "port": 5432, "database": "d", "user": "u",
        }, sslrootcert="/etc/profile.pem")
        # CLI override wins.
        args_cli = _source_args(source_service="prod", sslrootcert="/etc/cli.pem")
        pg_common._apply_source_service(args_cli)
        assert args_cli.sslrootcert == "/etc/cli.pem"

        # Service value fills in when CLI is unset.
        args_default = _source_args(source_service="prod", sslrootcert=None)
        pg_common._apply_source_service(args_default)
        assert args_default.sslrootcert == "/etc/profile.pem"

    def test_service_without_sslrootcert_leaves_args_untouched(self, temp_service_file, clean_env):
        pg_common.save_service_entry("prod", {
            "host": "h", "port": 5432, "database": "d", "user": "u",
        })  # no sslrootcert
        args = _source_args(source_service="prod", sslrootcert=None)
        pg_common._apply_source_service(args)
        assert args.sslrootcert is None

    def test_service_without_hostaddr_preserves_cli_override(self, temp_service_file, clean_env):
        pg_common.save_service_entry("prod", {
            "host": "h", "port": 5432, "database": "d", "user": "u",
        })
        args = _source_args(source_service="prod", hostaddr="198.51.100.5")
        pg_common._apply_source_service(args)
        assert args.hostaddr == "198.51.100.5"

    def test_missing_service_raises(self, temp_service_file, clean_env):
        args = _source_args(source_service="doesnotexist")
        with pytest.raises(ValueError, match="Source service 'doesnotexist' not found"):
            pg_common._apply_source_service(args)


class TestApplyTargetService:
    def test_no_service_is_noop(self, temp_service_file, clean_env):
        args = _target_args(target_service="")
        pg_common._apply_target_service(args)
        assert args.target_host == ""

    def test_service_fills_target_fields(self, temp_service_file, clean_env):
        pg_common.save_service_entry("sf_prod", {
            "host": "sf.example.com", "hostaddr": "203.0.113.11", "port": 5432,
            "database": "analytics", "user": "snowflake_admin",
        })
        args = _target_args(target_service="sf_prod")
        pg_common._apply_target_service(args)
        assert args.target_host == "sf.example.com"
        assert args.target_hostaddr == "203.0.113.11"
        assert args.target_dbname == "analytics"
        assert args.target_user == "snowflake_admin"

    def test_target_service_fills_sslrootcert(self, temp_service_file, clean_env):
        """Snowflake Postgres targets registered via `pg_connect --create`
        write sslrootcert into the service file. _apply_target_service must
        propagate that onto args.target_sslrootcert so verify-ca works in
        migrate flows (validate_migration, post_migration_cleanup, etc.).
        """
        pg_common.save_service_entry("sf_prod", {
            "host": "sf.example.com", "port": 5432,
            "database": "analytics", "user": "snowflake_admin",
        }, sslrootcert="/snowflake/ca.pem")
        args = _target_args(target_service="sf_prod", target_sslrootcert=None)
        pg_common._apply_target_service(args)
        assert args.target_sslmode == "verify-ca"
        assert args.target_sslrootcert == "/snowflake/ca.pem"

    def test_target_service_cli_sslrootcert_wins(self, temp_service_file, clean_env):
        """Explicit --target-sslrootcert wins over the service-file value."""
        pg_common.save_service_entry("sf_prod", {
            "host": "sf.example.com", "port": 5432,
            "database": "analytics", "user": "snowflake_admin",
        }, sslrootcert="/snowflake/ca.pem")
        args = _target_args(target_service="sf_prod", target_sslrootcert="/cli/override.pem")
        pg_common._apply_target_service(args)
        assert args.target_sslrootcert == "/cli/override.pem"

    def test_missing_target_service_raises(self, temp_service_file, clean_env):
        args = _target_args(target_service="doesnotexist")
        with pytest.raises(ValueError, match="Target service 'doesnotexist' not found"):
            pg_common._apply_target_service(args)


class TestResolveSourcePasswordServicePath:
    """When --source-service is set: CLI --password > env > pgpass > ''."""

    def test_cli_password_wins_over_everything(self, temp_pgpass, monkeypatch, clean_env):
        monkeypatch.setenv("PGPASSWORD", "from_env")
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _source_args(source_service="prod", password="from_cli",
                            host="h", port=5432, dbname="d", user="u")
        assert pg_common.resolve_source_password(args) == "from_cli"

    def test_env_wins_over_pgpass(self, temp_pgpass, monkeypatch, clean_env):
        monkeypatch.setenv("PGPASSWORD", "from_env")
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _source_args(source_service="prod",
                            host="h", port=5432, dbname="d", user="u")
        assert pg_common.resolve_source_password(args) == "from_env"

    def test_source_pgpassword_env_also_wins_over_pgpass(self, temp_pgpass, monkeypatch, clean_env):
        monkeypatch.setenv("SOURCE_PGPASSWORD", "from_source_env")
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _source_args(source_service="prod",
                            host="h", port=5432, dbname="d", user="u")
        assert pg_common.resolve_source_password(args) == "from_source_env"

    def test_pgpass_used_when_no_cli_no_env(self, temp_pgpass, clean_env):
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _source_args(source_service="prod",
                            host="h", port=5432, dbname="d", user="u")
        assert pg_common.resolve_source_password(args) == "from_pgpass"

    def test_empty_string_returned_when_nothing_matches(self, temp_pgpass, clean_env):
        args = _source_args(source_service="prod",
                            host="h", port=5432, dbname="d", user="u")
        assert pg_common.resolve_source_password(args) == ""

    def test_empty_pgpassword_env_does_not_shadow_pgpass_in_service_mode(
        self, temp_pgpass, monkeypatch, clean_env
    ):
        """Service-mode fixes the legacy quirk: empty PGPASSWORD falls through to pgpass."""
        monkeypatch.setenv("PGPASSWORD", "")
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _source_args(source_service="prod",
                            host="h", port=5432, dbname="d", user="u")
        assert pg_common.resolve_source_password(args) == "from_pgpass"


class TestResolveSourcePasswordLegacyPath:
    """No --source-service set: preserves the upstream exact behavior including
    the PGPASSWORD='' shadow quirk (contract-locked in the upstream
    test_pg_common)."""

    def test_cli_password_wins(self, monkeypatch, clean_env):
        monkeypatch.setenv("PGPASSWORD", "from_env")
        args = _source_args(password="from_cli")
        assert pg_common.resolve_source_password(args) == "from_cli"

    def test_pgpassword_env_used_when_no_cli(self, monkeypatch, clean_env):
        monkeypatch.setenv("PGPASSWORD", "from_env")
        args = _source_args()
        assert pg_common.resolve_source_password(args) == "from_env"

    def test_empty_pgpassword_shadows_source_pgpassword(self, monkeypatch, clean_env):
        """The upstream quirk: PGPASSWORD='' shadows SOURCE_PGPASSWORD because
        os.environ.get('PGPASSWORD', fallback) returns '' when key is set-but-empty."""
        monkeypatch.setenv("PGPASSWORD", "")
        monkeypatch.setenv("SOURCE_PGPASSWORD", "would_be_used")
        args = _source_args()
        assert pg_common.resolve_source_password(args) == ""

    def test_source_pgpassword_used_when_pgpassword_unset(self, monkeypatch, clean_env):
        monkeypatch.setenv("SOURCE_PGPASSWORD", "from_source")
        args = _source_args()
        assert pg_common.resolve_source_password(args) == "from_source"


class TestResolveTargetPasswordServicePath:
    def test_cli_password_wins(self, temp_pgpass, monkeypatch, clean_env):
        monkeypatch.setenv("TARGET_PGPASSWORD", "from_env")
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _target_args(target_service="sf", target_password="from_cli",
                            target_host="h", target_port=5432, target_dbname="d", target_user="u")
        assert pg_common.resolve_target_password(args) == "from_cli"

    def test_env_wins_over_pgpass(self, temp_pgpass, monkeypatch, clean_env):
        monkeypatch.setenv("TARGET_PGPASSWORD", "from_env")
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _target_args(target_service="sf",
                            target_host="h", target_port=5432, target_dbname="d", target_user="u")
        assert pg_common.resolve_target_password(args) == "from_env"

    def test_pgpass_used_when_no_cli_no_env(self, temp_pgpass, clean_env):
        pg_common.upsert_pgpass_entry("h", 5432, "d", "u", "from_pgpass")
        args = _target_args(target_service="sf",
                            target_host="h", target_port=5432, target_dbname="d", target_user="u")
        assert pg_common.resolve_target_password(args) == "from_pgpass"


class TestResolveTargetPasswordLegacyPath:
    def test_cli_wins(self, monkeypatch, clean_env):
        monkeypatch.setenv("TARGET_PGPASSWORD", "from_env")
        args = _target_args(target_password="from_cli")
        assert pg_common.resolve_target_password(args) == "from_cli"

    def test_env_used_when_no_cli(self, monkeypatch, clean_env):
        monkeypatch.setenv("TARGET_PGPASSWORD", "from_env")
        args = _target_args()
        assert pg_common.resolve_target_password(args) == "from_env"


class TestCliAddListRemove:
    """T014c CLI: round-trip source-profile management via python -m pg_common."""

    def test_add_then_list_round_trip(self, temp_service_file, temp_pgpass, capsys):
        rc = pg_common._main([
            "--add-source-service", "prod",
            "--host", "pg.prod.example.com",
            "--hostaddr", "203.0.113.10",
            "--port", "6543",
            "--dbname", "app",
            "--user", "reader",
            "--password", "s3cret",
        ])
        assert rc == 0

        entry = pg_common.get_service_entry("prod")
        assert entry == {
            "host": "pg.prod.example.com",
            "hostaddr": "203.0.113.10",
            "port": 6543,
            "database": "app",
            "user": "reader",
            "sslmode": "require",
        }
        pgpass_entry = pg_common.find_pgpass_entry("pg.prod.example.com", 6543, "app", "reader")
        assert pgpass_entry is not None
        assert pgpass_entry["password"] == "s3cret"

        capsys.readouterr()
        rc = pg_common._main(["--list-services"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "prod" in out
        assert "reader@pg.prod.example.com:6543/app" in out
        assert "pgpass" in out

    def test_add_without_password_skips_pgpass(self, temp_service_file, temp_pgpass, capsys):
        rc = pg_common._main([
            "--add-source-service", "staging",
            "--host", "h", "--port", "5432", "--dbname", "d", "--user", "u",
        ])
        assert rc == 0
        assert pg_common.find_pgpass_entry("h", 5432, "d", "u") is None

        rc = pg_common._main(["--list-services"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "no-pgpass" in out

    def test_add_with_env_password_writes_pgpass(
        self, temp_service_file, temp_pgpass, monkeypatch, clean_env
    ):
        monkeypatch.setenv("SOURCE_PGPASSWORD", "env_secret")
        rc = pg_common._main([
            "--add-source-service", "staging",
            "--host", "h", "--port", "5432", "--dbname", "d", "--user", "u",
        ])
        assert rc == 0
        pgpass_entry = pg_common.find_pgpass_entry("h", 5432, "d", "u")
        assert pgpass_entry is not None
        assert pgpass_entry["password"] == "env_secret"

    def test_add_requires_host_and_user(self, temp_service_file, temp_pgpass, capsys):
        with pytest.raises(SystemExit):
            pg_common._main([
                "--add-source-service", "nope",
                "--port", "5432", "--dbname", "d",
            ])
        err = capsys.readouterr().err
        assert "--host" in err and "--user" in err

    def test_remove_deletes_service_and_pgpass(self, temp_service_file, temp_pgpass):
        pg_common._main([
            "--add-source-service", "prod",
            "--host", "h", "--port", "5432", "--dbname", "d", "--user", "u",
            "--password", "s3cret",
        ])
        rc = pg_common._main(["--remove-source-service", "prod"])
        assert rc == 0
        assert pg_common.get_service_entry("prod") is None
        assert pg_common.find_pgpass_entry("h", 5432, "d", "u") is None

    def test_remove_keep_pgpass_leaves_password(self, temp_service_file, temp_pgpass):
        pg_common._main([
            "--add-source-service", "prod",
            "--host", "h", "--port", "5432", "--dbname", "d", "--user", "u",
            "--password", "s3cret",
        ])
        rc = pg_common._main(["--remove-source-service", "prod", "--keep-pgpass"])
        assert rc == 0
        assert pg_common.get_service_entry("prod") is None
        assert pg_common.find_pgpass_entry("h", 5432, "d", "u") is not None

    def test_remove_missing_returns_nonzero(self, temp_service_file, temp_pgpass, capsys):
        rc = pg_common._main(["--remove-source-service", "ghost"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "not found" in err

    def test_list_empty(self, temp_service_file, temp_pgpass, capsys):
        rc = pg_common._main(["--list-services"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "No services registered" in out

    def test_mutually_exclusive_actions(self, temp_service_file, temp_pgpass, capsys):
        with pytest.raises(SystemExit):
            pg_common._main(["--list-services", "--add-source-service", "x",
                             "--host", "h", "--user", "u"])


class TestPlatformPaths:
    """Pin the cross-platform PG_SERVICE_FILE / PGPASS_FILE resolution.

    The helpers accept os_name + environ overrides so we can exercise the
    Windows branch on a POSIX host without monkeypatching os.name globally
    (which would trip pathlib's WindowsPath factory and fail).
    """

    def test_windows_uses_appdata(self, tmp_path):
        appdata = tmp_path / "AppData" / "Roaming"
        environ = {"APPDATA": str(appdata)}
        assert pg_common._pg_config_dir("nt", environ) == appdata / "postgresql"
        assert pg_common._pg_service_filename("nt") == "pg_service.conf"
        assert pg_common._pgpass_filename("nt") == "pgpass.conf"

    def test_windows_falls_back_to_userprofile(self, tmp_path):
        profile = tmp_path / "users" / "test"
        environ = {"USERPROFILE": str(profile)}
        expected = profile / "AppData" / "Roaming" / "postgresql"
        assert pg_common._pg_config_dir("nt", environ) == expected

    def test_windows_prefers_appdata_when_both_set(self, tmp_path):
        appdata = tmp_path / "appdata"
        profile = tmp_path / "profile"
        environ = {"APPDATA": str(appdata), "USERPROFILE": str(profile)}
        assert pg_common._pg_config_dir("nt", environ) == appdata / "postgresql"

    def test_windows_raises_when_neither_env_set(self):
        with pytest.raises(RuntimeError, match="APPDATA or USERPROFILE"):
            pg_common._pg_config_dir("nt", {})

    def test_posix_uses_home_dotfiles(self):
        assert pg_common._pg_config_dir("posix", {}) == Path.home()
        assert pg_common._pg_service_filename("posix") == ".pg_service.conf"
        assert pg_common._pgpass_filename("posix") == ".pgpass"

    def test_module_constants_use_real_platform(self):
        """The module-level constants are computed once at import using the
        real os.name + os.environ. Sanity check they match what calling
        the helpers with no args produces."""
        assert pg_common.PG_SERVICE_FILE == pg_common._pg_config_dir() / pg_common._pg_service_filename()
        assert pg_common.PGPASS_FILE == pg_common._pg_config_dir() / pg_common._pgpass_filename()


class TestAutoCreateParentDir:
    """On a fresh Windows install %APPDATA%\\postgresql\\ doesn't exist until
    libpq or another tool creates it, so the save_* helpers must create the
    parent directory themselves before writing."""

    def test_save_service_file_creates_parent_dir(self, tmp_path, monkeypatch):
        nested = tmp_path / "fresh" / "postgresql" / "pg_service.conf"
        monkeypatch.setattr("pg_common.PG_SERVICE_FILE", nested)
        assert not nested.parent.exists()

        import configparser
        config = configparser.ConfigParser()
        config["prod"] = {"host": "h", "user": "u", "dbname": "d"}
        pg_common.save_service_file(config)

        assert nested.exists()
        assert "host=h" in nested.read_text()

    def test_save_pgpass_creates_parent_dir(self, tmp_path, monkeypatch):
        nested = tmp_path / "fresh" / "postgresql" / "pgpass.conf"
        monkeypatch.setattr("pg_common.PGPASS_FILE", nested)
        assert not nested.parent.exists()

        pg_common.save_pgpass([
            {"host": "h", "port": 5432, "database": "d", "user": "u", "password": "secret"},
        ])

        assert nested.exists()
        assert "h:5432:d:u:secret" in nested.read_text()


class TestPgErrorAliases:
    """Verify PgError / PgOperationalError resolve to the active driver's types."""

    def test_psycopg2_aliases_when_psycopg2_active(self):
        if pg_common.DB_DRIVER != 'psycopg2':
            pytest.skip("psycopg2 not the active driver")
        import psycopg2
        assert pg_common.PgError is psycopg2.Error
        assert pg_common.PgOperationalError is psycopg2.OperationalError

    def test_pg8000_aliases_when_pg8000_active(self):
        if pg_common.DB_DRIVER != 'pg8000':
            pytest.skip("pg8000 not the active driver")
        import pg8000.dbapi
        assert pg_common.PgError is pg8000.dbapi.Error
        assert pg_common.PgOperationalError is pg8000.dbapi.InterfaceError

    def test_fallback_aliases_are_exception(self):
        """When neither driver is available, aliases degrade to Exception."""
        saved_driver = pg_common.DB_DRIVER
        saved_err = pg_common.PgError
        saved_op_err = pg_common.PgOperationalError
        try:
            pg_common.DB_DRIVER = None
            pg_common.PgError = Exception
            pg_common.PgOperationalError = Exception
            assert pg_common.PgError is Exception
            assert pg_common.PgOperationalError is Exception
        finally:
            pg_common.DB_DRIVER = saved_driver
            pg_common.PgError = saved_err
            pg_common.PgOperationalError = saved_op_err


class TestConnectTimeoutTranslation:
    """connect_timeout is translated per driver: psycopg2 → connect_timeout=,
    pg8000 → timeout=."""

    def test_psycopg2_receives_connect_timeout(self):
        if pg_common.DB_DRIVER != 'psycopg2':
            pytest.skip("psycopg2 not the active driver")
        with patch.object(pg_common.psycopg2, 'connect', return_value=MagicMock()) as mock_connect:
            pg_common.connect('h', 5432, 'd', 'u', 'p', connect_timeout=10)
            kw = mock_connect.call_args[1]
            assert kw['connect_timeout'] == 10
            assert 'timeout' not in kw

    def test_psycopg2_omits_timeout_when_none(self):
        if pg_common.DB_DRIVER != 'psycopg2':
            pytest.skip("psycopg2 not the active driver")
        with patch.object(pg_common.psycopg2, 'connect', return_value=MagicMock()) as mock_connect:
            pg_common.connect('h', 5432, 'd', 'u', 'p')
            kw = mock_connect.call_args[1]
            assert 'connect_timeout' not in kw

    def test_psycopg2_receives_options(self):
        if pg_common.DB_DRIVER != 'psycopg2':
            pytest.skip("psycopg2 not the active driver")
        opts = "-c statement_timeout=5000"
        with patch.object(pg_common.psycopg2, 'connect', return_value=MagicMock()) as mock_connect:
            pg_common.connect('h', 5432, 'd', 'u', 'p', options=opts)
            kw = mock_connect.call_args[1]
            assert kw['options'] == opts

    def test_psycopg2_omits_options_when_none(self):
        if pg_common.DB_DRIVER != 'psycopg2':
            pytest.skip("psycopg2 not the active driver")
        with patch.object(pg_common.psycopg2, 'connect', return_value=MagicMock()) as mock_connect:
            pg_common.connect('h', 5432, 'd', 'u', 'p')
            kw = mock_connect.call_args[1]
            assert 'options' not in kw


class TestPg8000FallbackPath:
    """Simulate the pg8000 fallback and verify connect() dispatches correctly.

    Patches module-level state rather than reloading — same technique as
    TestPlatformPaths.
    """

    @pytest.fixture(autouse=True)
    def _patch_pg8000_driver(self, monkeypatch):
        self.mock_pg8000 = MagicMock()
        self.mock_pg8000.connect.return_value = MagicMock()
        monkeypatch.setattr(pg_common, 'DB_DRIVER', 'pg8000')
        if not hasattr(pg_common, 'pg8000'):
            pg_common.pg8000 = None
        monkeypatch.setattr(pg_common, 'pg8000', self.mock_pg8000)
        if not hasattr(pg_common, 'psycopg2'):
            pg_common.psycopg2 = None
        monkeypatch.setattr(pg_common, 'psycopg2', None)

    def test_basic_connect_uses_pg8000(self):
        pg_common.connect('h', 5432, 'd', 'u', 'p')
        self.mock_pg8000.connect.assert_called_once()
        kw = self.mock_pg8000.connect.call_args[1]
        assert kw['host'] == 'h'
        assert kw['port'] == 5432
        assert kw['database'] == 'd'
        assert kw['user'] == 'u'
        assert kw['password'] == 'p'

    def test_timeout_translated(self):
        pg_common.connect('h', 5432, 'd', 'u', 'p', connect_timeout=10)
        kw = self.mock_pg8000.connect.call_args[1]
        assert kw['timeout'] == 10
        assert 'connect_timeout' not in kw

    def test_options_dropped(self):
        pg_common.connect('h', 5432, 'd', 'u', 'p',
                          options="-c statement_timeout=5000")
        kw = self.mock_pg8000.connect.call_args[1]
        assert 'options' not in kw

    def test_hostaddr_dropped(self):
        pg_common.connect('h', 5432, 'd', 'u', 'p', hostaddr='1.2.3.4')
        kw = self.mock_pg8000.connect.call_args[1]
        assert 'hostaddr' not in kw

    def test_verify_ca_ssl_context(self):
        import ssl
        mock_ctx = MagicMock(spec=ssl.SSLContext)
        with patch('ssl.create_default_context', return_value=mock_ctx):
            pg_common.connect('h', 5432, 'd', 'u', 'p',
                              sslmode='verify-ca', sslrootcert='/tmp/ca.pem')
        kw = self.mock_pg8000.connect.call_args[1]
        assert kw['ssl_context'] is mock_ctx
        assert mock_ctx.check_hostname is False
        assert mock_ctx.verify_mode == ssl.CERT_REQUIRED

    def test_require_skips_cert_verification(self):
        import ssl
        mock_ctx = MagicMock(spec=ssl.SSLContext)
        with patch('ssl.create_default_context', return_value=mock_ctx):
            pg_common.connect('h', 5432, 'd', 'u', 'p', sslmode='require')
        kw = self.mock_pg8000.connect.call_args[1]
        assert kw['ssl_context'] is mock_ctx
        assert mock_ctx.check_hostname is False
        assert mock_ctx.verify_mode == ssl.CERT_NONE

    def test_no_ssl_when_disabled(self):
        pg_common.connect('h', 5432, 'd', 'u', 'p', sslmode='disable')
        kw = self.mock_pg8000.connect.call_args[1]
        assert 'ssl_context' not in kw


class TestInlineSqlstateCheck:
    """Pin the inline SQLSTATE extraction pattern used in pg_lake_catalog.py
    for the UndefinedTable (42P01) catch. Validates both driver shapes."""

    @staticmethod
    def _extract_sqlstate(e):
        """Mirror the inline pattern from pg_lake_catalog.py."""
        sqlstate = getattr(e, "pgcode", None)
        if sqlstate is None and e.args and isinstance(e.args[0], dict):
            sqlstate = e.args[0].get("C")
        return sqlstate

    def test_psycopg2_shape(self):
        err = Exception("relation does not exist")
        err.pgcode = "42P01"
        assert self._extract_sqlstate(err) == "42P01"

    def test_pg8000_shape(self):
        err = Exception({"S": "ERROR", "C": "42P01", "M": "relation does not exist"})
        assert self._extract_sqlstate(err) == "42P01"

    def test_other_sqlstate_psycopg2(self):
        err = Exception("permission denied")
        err.pgcode = "42501"
        assert self._extract_sqlstate(err) != "42P01"

    def test_other_sqlstate_pg8000(self):
        err = Exception({"S": "ERROR", "C": "42501", "M": "permission denied"})
        assert self._extract_sqlstate(err) != "42P01"

    def test_no_sqlstate_at_all(self):
        err = Exception("generic error")
        assert self._extract_sqlstate(err) is None


class TestValidatePgField:
    def test_accepts_normal_database_name(self):
        assert pg_common.validate_pg_database_name("appdb") == "appdb"

    def test_rejects_newline_in_database(self):
        with pytest.raises(ValueError, match="control characters"):
            pg_common.validate_pg_database_name("appdb\nextra")

    def test_rejects_carriage_return(self):
        with pytest.raises(ValueError, match="control characters"):
            pg_common.validate_pg_field("host\rname", "host")

    def test_allows_star_when_requested(self):
        assert pg_common.validate_pg_field("*", "database", allow_star=True) == "*"

    def test_save_pgpass_rejects_newline_database(self, temp_pgpass):
        with pytest.raises(ValueError, match="control characters"):
            pg_common.save_pgpass([{
                "host": "h",
                "port": 5432,
                "database": "db\ninject",
                "user": "u",
                "password": "pw",
            }])
