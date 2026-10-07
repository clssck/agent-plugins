"""Tests for pg_common.py.

Green-baseline tests against the upstream untouched pg_common.py. These bake in
current behavior (quirks and all) as a contract for a subsequent port into the
main repo. Do not modify pg_common.py to make these pass — if behavior is
weird, the test asserts the weirdness.

Driver notes:
    pg_common resolves DB_DRIVER at import time from whichever driver is
    installed. In this environment psycopg2 is available, so DB_DRIVER ==
    'psycopg2'. To exercise the pg8000 branch we monkeypatch
    pg_common.DB_DRIVER (read at call-time inside connect) and inject a fake
    pg8000 module.
"""
from __future__ import annotations

import argparse
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

import pg_common


# ---------------------------------------------------------------------------
# Module-level import wiring
# ---------------------------------------------------------------------------


class TestModuleImport:
    """Sanity checks on module-level driver detection."""

    def test_db_driver_is_set(self):
        """DB_DRIVER is resolved to a known string at import time."""
        assert pg_common.DB_DRIVER in ("psycopg2", "pg8000", None)

    def test_psycopg2_available_in_test_env(self):
        """This test env ships with psycopg2 (per pyproject.toml)."""
        assert pg_common.DB_DRIVER == "psycopg2"
        assert pg_common.psycopg2 is not None


# ---------------------------------------------------------------------------
# check_driver
# ---------------------------------------------------------------------------


class TestCheckDriver:
    """Tests for check_driver — exits when no driver is available."""

    def test_no_op_when_driver_present(self):
        """With DB_DRIVER set, check_driver returns None silently."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"):
            assert pg_common.check_driver() is None

    def test_exits_when_no_driver(self, capsys):
        """With DB_DRIVER=None, check_driver prints to stderr and sys.exit(1)."""
        with patch.object(pg_common, "DB_DRIVER", None), \
             patch.object(pg_common, "_is_managed_python", return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                pg_common.check_driver()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "No PostgreSQL driver found" in err
        assert "psycopg2-binary" in err
        assert "pg8000" in err

    def test_shows_venv_hint_on_managed_python(self, capsys):
        """Managed-python detection triggers the venv hint block."""
        with patch.object(pg_common, "DB_DRIVER", None), \
             patch.object(pg_common, "_is_managed_python", return_value=True):
            with pytest.raises(SystemExit):
                pg_common.check_driver()
        err = capsys.readouterr().err
        assert "virtual environment" in err
        assert "python3 -m venv" in err

    def test_no_venv_hint_when_not_managed(self, capsys):
        """Without managed-python, the venv hint is omitted."""
        with patch.object(pg_common, "DB_DRIVER", None), \
             patch.object(pg_common, "_is_managed_python", return_value=False):
            with pytest.raises(SystemExit):
                pg_common.check_driver()
        err = capsys.readouterr().err
        assert "virtual environment" not in err


class TestIsManagedPython:
    """Tests for _is_managed_python helper."""

    def test_detects_externally_managed(self):
        """Returns True when pip reports externally-managed."""
        fake_result = MagicMock(stderr="error: externally-managed-environment\n")
        with patch("subprocess.run", return_value=fake_result):
            assert pg_common._is_managed_python() is True

    def test_non_managed_returns_false(self):
        """Returns False when pip runs normally."""
        fake_result = MagicMock(stderr="Requirement already satisfied\n")
        with patch("subprocess.run", return_value=fake_result):
            assert pg_common._is_managed_python() is False

    def test_swallows_exceptions(self):
        """Any subprocess failure returns False (never raises)."""
        with patch("subprocess.run", side_effect=OSError("boom")):
            assert pg_common._is_managed_python() is False


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------


class TestConnectPsycopg2:
    """connect() when DB_DRIVER == 'psycopg2'."""

    def test_basic_connect(self):
        """Passes host/port/database/user/password through to psycopg2.connect."""
        fake_conn = MagicMock()
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect", return_value=fake_conn) as mock_c:
            result = pg_common.connect("h", 5432, "db", "u", "pw")
        assert result is fake_conn
        mock_c.assert_called_once_with(host="h", port=5432, database="db", user="u", password="pw")

    def test_adds_sslmode_when_provided(self):
        """sslmode is forwarded to psycopg2 when non-empty."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect") as mock_c:
            pg_common.connect("h", 5432, "db", "u", "pw", sslmode="require")
        kwargs = mock_c.call_args.kwargs
        assert kwargs["sslmode"] == "require"

    def test_omits_sslmode_when_none(self):
        """sslmode is omitted from kwargs when None (default)."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect") as mock_c:
            pg_common.connect("h", 5432, "db", "u", "pw")
        assert "sslmode" not in mock_c.call_args.kwargs

    def test_omits_sslmode_when_empty_string(self):
        """Empty-string sslmode is falsy and omitted."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect") as mock_c:
            pg_common.connect("h", 5432, "db", "u", "pw", sslmode="")
        assert "sslmode" not in mock_c.call_args.kwargs

    def test_adds_sslrootcert_when_provided(self):
        """sslrootcert is forwarded to psycopg2 as the libpq kwarg of the
        same name. Required for verify-ca / verify-full to succeed against
        Snowflake Postgres (per-instance CA written by `pg_connect --create`).
        """
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect") as mock_c:
            pg_common.connect("h", 5432, "db", "u", "pw",
                              sslmode="verify-ca", sslrootcert="/etc/ca.pem")
        kwargs = mock_c.call_args.kwargs
        assert kwargs["sslrootcert"] == "/etc/ca.pem"
        assert kwargs["sslmode"] == "verify-ca"

    def test_adds_hostaddr_when_provided(self):
        """hostaddr is forwarded on the libpq/psycopg2 path for DNS-bypass
        environments while preserving host for TLS/pgpass identity."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect") as mock_c:
            pg_common.connect("db.example.com", 5432, "db", "u", "pw",
                              hostaddr="203.0.113.10")
        kwargs = mock_c.call_args.kwargs
        assert kwargs["host"] == "db.example.com"
        assert kwargs["hostaddr"] == "203.0.113.10"

    def test_omits_sslrootcert_when_none(self):
        """sslrootcert is omitted from kwargs when None (default)."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect") as mock_c:
            pg_common.connect("h", 5432, "db", "u", "pw", sslmode="require")
        assert "sslrootcert" not in mock_c.call_args.kwargs

    def test_psycopg2_preserves_string_port(self):
        """psycopg2 branch does NOT cast port to int (quirk — pg8000 does)."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common.psycopg2, "connect") as mock_c:
            pg_common.connect("h", "5432", "db", "u", "pw")
        assert mock_c.call_args.kwargs["port"] == "5432"

    def test_calls_check_driver(self):
        """connect() invokes check_driver before connecting."""
        with patch.object(pg_common, "DB_DRIVER", "psycopg2"), \
             patch.object(pg_common, "check_driver") as mock_check, \
             patch.object(pg_common.psycopg2, "connect"):
            pg_common.connect("h", 5432, "db", "u", "pw")
        mock_check.assert_called_once()


class TestConnectPg8000:
    """connect() when DB_DRIVER == 'pg8000'.

    pg8000 isn't installed in this env; we inject a fake module into
    pg_common to simulate the fallback path.
    """

    @pytest.fixture
    def fake_pg8000(self, monkeypatch):
        """Install a fake pg8000 module on pg_common and flip DB_DRIVER."""
        fake = types.SimpleNamespace(connect=MagicMock())
        monkeypatch.setattr(pg_common, "pg8000", fake, raising=False)
        monkeypatch.setattr(pg_common, "DB_DRIVER", "pg8000")
        return fake

    def test_basic_connect_casts_port_to_int(self, fake_pg8000):
        """pg8000 branch explicitly casts port to int."""
        pg_common.connect("h", "5432", "db", "u", "pw")
        kwargs = fake_pg8000.connect.call_args.kwargs
        assert kwargs == {"host": "h", "port": 5432, "database": "db", "user": "u", "password": "pw"}

    def test_pg8000_omits_sslmode_when_disable(self, fake_pg8000):
        """'disable' sslmode explicitly skips adding ssl_context."""
        pg_common.connect("h", 5432, "db", "u", "pw", sslmode="disable")
        kwargs = fake_pg8000.connect.call_args.kwargs
        assert "ssl_context" not in kwargs
        assert "sslmode" not in kwargs

    def test_pg8000_omits_ssl_context_when_none(self, fake_pg8000):
        """None sslmode → no ssl_context."""
        pg_common.connect("h", 5432, "db", "u", "pw")
        assert "ssl_context" not in fake_pg8000.connect.call_args.kwargs

    def test_pg8000_adds_ssl_context_when_require(self, fake_pg8000):
        """Non-disable, non-empty sslmode triggers ssl.create_default_context()."""
        import ssl as ssl_mod
        pg_common.connect("h", 5432, "db", "u", "pw", sslmode="require")
        kwargs = fake_pg8000.connect.call_args.kwargs
        assert "ssl_context" in kwargs
        assert isinstance(kwargs["ssl_context"], ssl_mod.SSLContext)

    def test_pg8000_loads_sslrootcert_via_cafile(self, fake_pg8000):
        """sslrootcert path is passed to ssl.create_default_context as cafile.
        We mock the ssl module to avoid needing a real CA file on disk —
        we only care that the plumbing routes the path to the right kwarg.
        """
        import ssl as ssl_mod
        with patch("ssl.create_default_context", wraps=ssl_mod.create_default_context) as mock_ctx:
            pg_common.connect("h", 5432, "db", "u", "pw",
                              sslmode="require", sslrootcert=None)
            assert mock_ctx.call_args.kwargs == {} or mock_ctx.call_args.kwargs.get("cafile") is None

        # With a path: cafile= is set on the ssl context constructor.
        fake_ctx = MagicMock(spec=ssl_mod.SSLContext)
        fake_ctx.check_hostname = True
        fake_ctx.verify_mode = ssl_mod.CERT_REQUIRED
        with patch("ssl.create_default_context", return_value=fake_ctx) as mock_ctx:
            pg_common.connect("h", 5432, "db", "u", "pw",
                              sslmode="require", sslrootcert="/etc/ca.pem")
            mock_ctx.assert_called_once_with(cafile="/etc/ca.pem")

    def test_pg8000_verify_ca_disables_hostname_check(self, fake_pg8000):
        """For sslmode=verify-ca we mirror libpq: chain is verified, hostname
        check is off. Otherwise self-signed Snowflake Postgres certs (whose
        CN does not match the public hostname) would be rejected.
        """
        import ssl as ssl_mod
        fake_ctx = MagicMock(spec=ssl_mod.SSLContext)
        # Initial values that connect() should override.
        fake_ctx.check_hostname = True
        fake_ctx.verify_mode = ssl_mod.CERT_NONE
        with patch("ssl.create_default_context", return_value=fake_ctx):
            pg_common.connect("h", 5432, "db", "u", "pw",
                              sslmode="verify-ca", sslrootcert="/etc/ca.pem")
        assert fake_ctx.check_hostname is False
        assert fake_ctx.verify_mode == ssl_mod.CERT_REQUIRED

    def test_pg8000_ignores_hostaddr(self, fake_pg8000):
        """pg8000 has no hostaddr parameter, so the fallback driver keeps using
        host without adding an unsupported kwarg."""
        pg_common.connect("db.example.com", 5432, "db", "u", "pw",
                          hostaddr="203.0.113.10")
        kwargs = fake_pg8000.connect.call_args.kwargs
        assert kwargs["host"] == "db.example.com"
        assert "hostaddr" not in kwargs

    def test_pg8000_returns_connection(self, fake_pg8000):
        """Return value is whatever pg8000.connect returns."""
        sentinel = object()
        fake_pg8000.connect.return_value = sentinel
        assert pg_common.connect("h", 5432, "db", "u", "pw") is sentinel


# ---------------------------------------------------------------------------
# query / scalar
# ---------------------------------------------------------------------------


class TestQuery:
    """Tests for the low-level query() helper."""

    def test_returns_empty_when_no_description(self, mock_conn, mock_cursor):
        """No cursor.description => empty list (e.g. DDL / writes)."""
        mock_cursor.description = None
        result = pg_common.query(mock_conn, "UPDATE t SET x=1")
        assert result == []

    def test_returns_dicts_keyed_by_column(self, mock_conn, mock_cursor):
        """Rows are zipped with column names into dicts."""
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "alice"), (2, "bob")]
        result = pg_common.query(mock_conn, "SELECT id, name FROM t")
        assert result == [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]

    def test_empty_fetchall_still_returns_list(self, mock_conn, mock_cursor):
        """description set but no rows => []."""
        mock_cursor.description = [("x",)]
        mock_cursor.fetchall.return_value = []
        assert pg_common.query(mock_conn, "SELECT x") == []

    def test_passes_params_to_execute(self, mock_conn, mock_cursor):
        """params are forwarded to cursor.execute."""
        mock_cursor.description = None
        pg_common.query(mock_conn, "SELECT %s", params=(42,))
        mock_cursor.execute.assert_called_once_with("SELECT %s", (42,))

    def test_default_params_is_none(self, mock_conn, mock_cursor):
        """Without params, execute is called with None."""
        mock_cursor.description = None
        pg_common.query(mock_conn, "SELECT 1")
        mock_cursor.execute.assert_called_once_with("SELECT 1", None)


class TestScalar:
    """Tests for scalar() — returns first value of first row."""

    def test_returns_first_value(self, mock_conn, mock_cursor):
        """Single row, single column."""
        mock_cursor.description = [("v",)]
        mock_cursor.fetchall.return_value = [(7,)]
        assert pg_common.scalar(mock_conn, "SELECT 7") == 7

    def test_returns_first_value_of_multi_col(self, mock_conn, mock_cursor):
        """First column's value wins when multiple columns are present."""
        mock_cursor.description = [("a",), ("b",)]
        mock_cursor.fetchall.return_value = [("first", "second")]
        assert pg_common.scalar(mock_conn, "SELECT a, b") == "first"

    def test_returns_none_when_no_rows(self, mock_conn, mock_cursor):
        """Empty result set => None."""
        mock_cursor.description = [("v",)]
        mock_cursor.fetchall.return_value = []
        assert pg_common.scalar(mock_conn, "SELECT v") is None

    def test_returns_none_when_no_description(self, mock_conn, mock_cursor):
        """No description => None (via the underlying query())."""
        mock_cursor.description = None
        assert pg_common.scalar(mock_conn, "UPDATE") is None


# ---------------------------------------------------------------------------
# detect_pg_version
# ---------------------------------------------------------------------------


class TestDetectPgVersion:
    """Tests for detect_pg_version."""

    def test_returns_int_version(self, mock_conn, mock_cursor):
        """Converts the scalar server_version_num to int."""
        mock_cursor.description = [("current_setting",)]
        mock_cursor.fetchall.return_value = [("160004",)]
        assert pg_common.detect_pg_version(mock_conn) == 160004

    def test_returns_zero_when_scalar_none(self, mock_conn, mock_cursor):
        """If the scalar is None/missing, returns 0."""
        mock_cursor.description = [("x",)]
        mock_cursor.fetchall.return_value = []
        assert pg_common.detect_pg_version(mock_conn) == 0

    def test_returns_zero_when_scalar_is_zero(self, mock_conn, mock_cursor):
        """QUIRK: a scalar of 0 (falsy) also collapses to 0 via the `if ver else 0` guard."""
        mock_cursor.description = [("x",)]
        mock_cursor.fetchall.return_value = [(0,)]
        assert pg_common.detect_pg_version(mock_conn) == 0

    def test_issues_server_version_num_query(self, mock_conn, mock_cursor):
        """Issues SELECT current_setting('server_version_num')::int."""
        mock_cursor.description = [("v",)]
        mock_cursor.fetchall.return_value = [(150001,)]
        pg_common.detect_pg_version(mock_conn)
        mock_cursor.execute.assert_called_once_with(
            "SELECT current_setting('server_version_num')::int", None
        )


# ---------------------------------------------------------------------------
# add_source_args / add_target_args
# ---------------------------------------------------------------------------


class TestAddSourceArgs:
    """Tests for add_source_args — source-side argparse wiring."""

    def _parser_with_source(self):
        p = argparse.ArgumentParser()
        pg_common.add_source_args(p)
        return p

    def test_defaults_when_env_clean(self, monkeypatch):
        """All SOURCE_* env vars unset → defaults to empty strings and 5432."""
        for v in ("SOURCE_PGHOST", "SOURCE_PGPORT", "SOURCE_PGDATABASE",
                  "SOURCE_PGUSER", "PGPASSWORD", "SOURCE_PGPASSWORD"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_source()
        args = p.parse_args([])
        assert args.host == ""
        assert args.port == 5432
        assert args.dbname == ""
        assert args.user == ""
        assert args.password == ""
        assert args.sslmode is None

    def test_env_defaults_are_picked_up(self, monkeypatch):
        """SOURCE_* env vars populate the argparse defaults at call time."""
        monkeypatch.setenv("SOURCE_PGHOST", "envhost")
        monkeypatch.setenv("SOURCE_PGPORT", "6432")
        monkeypatch.setenv("SOURCE_PGDATABASE", "envdb")
        monkeypatch.setenv("SOURCE_PGUSER", "envuser")
        p = self._parser_with_source()
        args = p.parse_args([])
        assert args.host == "envhost"
        assert args.port == 6432
        assert args.dbname == "envdb"
        assert args.user == "envuser"

    def test_cli_overrides_env(self, monkeypatch):
        """Explicit CLI flags beat env defaults."""
        monkeypatch.setenv("SOURCE_PGHOST", "envhost")
        p = self._parser_with_source()
        args = p.parse_args(["--host", "clihost", "--port", "7000"])
        assert args.host == "clihost"
        assert args.port == 7000

    def test_short_flags(self, monkeypatch):
        """-H, -p, -d, -U, -W short aliases are accepted."""
        for v in ("SOURCE_PGHOST", "SOURCE_PGPORT", "SOURCE_PGDATABASE", "SOURCE_PGUSER"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_source()
        args = p.parse_args(["-H", "h", "-p", "1234", "-d", "db", "-U", "u", "-W", "pw"])
        assert args.host == "h"
        assert args.port == 1234
        assert args.dbname == "db"
        assert args.user == "u"
        assert args.password == "pw"

    def test_source_aliases(self, monkeypatch):
        """--source-host / --source-port / etc. long aliases are accepted."""
        for v in ("SOURCE_PGHOST", "SOURCE_PGPORT", "SOURCE_PGDATABASE", "SOURCE_PGUSER"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_source()
        args = p.parse_args([
            "--source-host", "h",
            "--source-port", "2345",
            "--source-dbname", "db",
            "--source-user", "u",
        ])
        assert args.host == "h"
        assert args.port == 2345
        assert args.dbname == "db"
        assert args.user == "u"

    def test_sslmode_parses(self, monkeypatch):
        """--sslmode flag value lands on args.sslmode."""
        for v in ("SOURCE_PGHOST", "SOURCE_PGPORT"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_source()
        args = p.parse_args(["--sslmode", "verify-full"])
        assert args.sslmode == "verify-full"

    def test_hostaddr_parses(self, monkeypatch):
        """--hostaddr lands on args.hostaddr."""
        for v in ("SOURCE_PGHOST", "SOURCE_PGHOSTADDR"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_source()
        args = p.parse_args(["--hostaddr", "203.0.113.10"])
        assert args.hostaddr == "203.0.113.10"

    def test_bad_source_pgport_crashes_at_add_time(self, monkeypatch):
        """QUIRK: non-numeric SOURCE_PGPORT makes add_source_args raise at call time."""
        monkeypatch.setenv("SOURCE_PGPORT", "notanumber")
        with pytest.raises(ValueError):
            self._parser_with_source()


class TestAddTargetArgs:
    """Tests for add_target_args — target-side argparse wiring."""

    def _parser_with_target(self):
        p = argparse.ArgumentParser()
        pg_common.add_target_args(p)
        return p

    def test_target_defaults_when_env_clean(self, monkeypatch):
        """TARGET_* env vars unset → empty strings and port 5432."""
        for v in ("TARGET_PGHOST", "TARGET_PGPORT", "TARGET_PGDATABASE",
                  "TARGET_PGUSER", "TARGET_PGPASSWORD"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_target()
        args = p.parse_args([])
        assert args.target_host == ""
        assert args.target_port == 5432
        assert args.target_dbname == ""
        assert args.target_user == ""
        assert args.target_password == ""
        assert args.target_sslmode is None

    def test_target_env_defaults_are_picked_up(self, monkeypatch):
        """TARGET_* env vars populate argparse defaults."""
        monkeypatch.setenv("TARGET_PGHOST", "tgt.example.com")
        monkeypatch.setenv("TARGET_PGPORT", "6543")
        monkeypatch.setenv("TARGET_PGDATABASE", "tgtdb")
        monkeypatch.setenv("TARGET_PGUSER", "tgtuser")
        p = self._parser_with_target()
        args = p.parse_args([])
        assert args.target_host == "tgt.example.com"
        assert args.target_port == 6543
        assert args.target_dbname == "tgtdb"
        assert args.target_user == "tgtuser"

    def test_target_cli_overrides_env(self, monkeypatch):
        """Explicit --target-* flags beat env defaults."""
        monkeypatch.setenv("TARGET_PGHOST", "envhost")
        p = self._parser_with_target()
        args = p.parse_args(["--target-host", "clihost"])
        assert args.target_host == "clihost"

    def test_target_password_and_sslmode(self, monkeypatch):
        """--target-password and --target-sslmode parse onto the right attrs."""
        for v in ("TARGET_PGHOST", "TARGET_PGPORT"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_target()
        args = p.parse_args(["--target-password", "pw", "--target-sslmode", "require"])
        assert args.target_password == "pw"
        assert args.target_sslmode == "require"

    def test_target_hostaddr_parses(self, monkeypatch):
        """--target-hostaddr lands on args.target_hostaddr."""
        for v in ("TARGET_PGHOST", "TARGET_PGHOSTADDR"):
            monkeypatch.delenv(v, raising=False)
        p = self._parser_with_target()
        args = p.parse_args(["--target-hostaddr", "203.0.113.11"])
        assert args.target_hostaddr == "203.0.113.11"


# ---------------------------------------------------------------------------
# resolve_source_password / resolve_target_password
# ---------------------------------------------------------------------------


class TestResolveSourcePassword:
    """args.password wins; else PGPASSWORD; else SOURCE_PGPASSWORD; else ''."""

    def test_args_password_wins(self, monkeypatch):
        """A non-empty args.password takes priority over env vars."""
        monkeypatch.setenv("PGPASSWORD", "envpg")
        monkeypatch.setenv("SOURCE_PGPASSWORD", "envsrc")
        args = argparse.Namespace(password="argpw")
        assert pg_common.resolve_source_password(args) == "argpw"

    def test_pgpassword_used_when_args_empty(self, monkeypatch):
        """Empty args.password falls back to PGPASSWORD."""
        monkeypatch.setenv("PGPASSWORD", "envpg")
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = argparse.Namespace(password="")
        assert pg_common.resolve_source_password(args) == "envpg"

    def test_pgpassword_empty_shadows_source_pgpassword(self, monkeypatch):
        """QUIRK: PGPASSWORD='' (present but empty) shadows SOURCE_PGPASSWORD entirely.

        Fallback is `os.environ.get('PGPASSWORD', os.environ.get('SOURCE_PGPASSWORD', ''))`.
        `os.environ.get('PGPASSWORD', ...)` returns the actual value when the key is present
        — so PGPASSWORD='' yields '' and the SOURCE_PGPASSWORD fallback (second `get`'s default
        value) is never evaluated-as-chosen. The outer `args.password or …` then sees '' or ''
        and returns ''. SOURCE_PGPASSWORD is only reached when PGPASSWORD is absent from env.
        """
        monkeypatch.setenv("PGPASSWORD", "")
        monkeypatch.setenv("SOURCE_PGPASSWORD", "src_pw")
        args = argparse.Namespace(password="")
        assert pg_common.resolve_source_password(args) == ""

    def test_pgpassword_nonempty_wins_over_source_pgpassword(self, monkeypatch):
        """Non-empty PGPASSWORD wins over SOURCE_PGPASSWORD (PGPASSWORD takes priority)."""
        monkeypatch.setenv("PGPASSWORD", "pgpw")
        monkeypatch.setenv("SOURCE_PGPASSWORD", "srcpw")
        args = argparse.Namespace(password="")
        assert pg_common.resolve_source_password(args) == "pgpw"

    def test_source_pgpassword_used_when_pgpassword_unset(self, monkeypatch):
        """SOURCE_PGPASSWORD is used only when PGPASSWORD is missing."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.setenv("SOURCE_PGPASSWORD", "srcpw")
        args = argparse.Namespace(password="")
        assert pg_common.resolve_source_password(args) == "srcpw"

    def test_empty_everywhere_returns_empty_string(self, monkeypatch):
        """No password anywhere → ''."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = argparse.Namespace(password="")
        assert pg_common.resolve_source_password(args) == ""


class TestResolveTargetPassword:
    """args.target_password wins; else TARGET_PGPASSWORD; else ''."""

    def test_args_target_password_wins(self, monkeypatch):
        """Non-empty args.target_password wins."""
        monkeypatch.setenv("TARGET_PGPASSWORD", "envpw")
        args = argparse.Namespace(target_password="argpw")
        assert pg_common.resolve_target_password(args) == "argpw"

    def test_target_pgpassword_used_when_args_empty(self, monkeypatch):
        """Empty args.target_password falls back to TARGET_PGPASSWORD."""
        monkeypatch.setenv("TARGET_PGPASSWORD", "envpw")
        args = argparse.Namespace(target_password="")
        assert pg_common.resolve_target_password(args) == "envpw"

    def test_empty_everywhere_returns_empty(self, monkeypatch):
        """Nothing set → ''."""
        monkeypatch.delenv("TARGET_PGPASSWORD", raising=False)
        args = argparse.Namespace(target_password="")
        assert pg_common.resolve_target_password(args) == ""


# ---------------------------------------------------------------------------
# connect_source / connect_target
# ---------------------------------------------------------------------------


class TestConnectSource:
    """Tests for connect_source — composes resolve_source_password + connect()."""

    def test_forwards_args_and_resolved_password(self, monkeypatch):
        """Args fields and resolved password are forwarded to connect()."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = argparse.Namespace(
            host="h", port=5432, dbname="db", user="u", password="pw", sslmode="require"
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_source(args)
        # sslrootcert is forwarded as a kwarg (None when not on args, getattr default).
        mock_connect.assert_called_once_with(
            "h", 5432, "db", "u", "pw", "require", sslrootcert=None, hostaddr=None
        )

    def test_uses_env_password_when_args_empty(self, monkeypatch):
        """Empty args.password pulls PGPASSWORD for the final connect() call."""
        monkeypatch.setenv("PGPASSWORD", "envpg")
        args = argparse.Namespace(
            host="h", port=5432, dbname="db", user="u", password="", sslmode=None
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_source(args)
        assert mock_connect.call_args.args[4] == "envpg"

    def test_forwards_sslrootcert_when_set(self, monkeypatch):
        """args.sslrootcert reaches the underlying connect() call so verify-ca
        profiles work end-to-end without re-fetching the CA in every script."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = argparse.Namespace(
            host="h", port=5432, dbname="db", user="u", password="pw",
            sslmode="verify-ca", sslrootcert="/etc/ca.pem",
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_source(args)
        mock_connect.assert_called_once_with(
            "h", 5432, "db", "u", "pw", "verify-ca",
            sslrootcert="/etc/ca.pem", hostaddr=None
        )

    def test_forwards_hostaddr_when_set(self, monkeypatch):
        """args.hostaddr is forwarded so libpq-backed callers can bypass DNS."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = argparse.Namespace(
            host="db.example.com", port=5432, dbname="db", user="u", password="pw",
            sslmode="require", sslrootcert=None, hostaddr="203.0.113.10",
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_source(args)
        mock_connect.assert_called_once_with(
            "db.example.com", 5432, "db", "u", "pw", "require",
            sslrootcert=None, hostaddr="203.0.113.10"
        )


class TestConnectTarget:
    """Tests for connect_target — composes resolve_target_password + connect()."""

    def test_forwards_target_args_and_resolved_password(self, monkeypatch):
        """Target args + resolved password flow into connect()."""
        monkeypatch.delenv("TARGET_PGPASSWORD", raising=False)
        args = argparse.Namespace(
            target_host="th", target_port=6543, target_dbname="tdb",
            target_user="tu", target_password="tpw", target_sslmode="verify-full",
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_target(args)
        mock_connect.assert_called_once_with(
            "th", 6543, "tdb", "tu", "tpw", "verify-full",
            sslrootcert=None, hostaddr=None
        )

    def test_uses_env_target_password_when_args_empty(self, monkeypatch):
        """Empty args.target_password pulls TARGET_PGPASSWORD."""
        monkeypatch.setenv("TARGET_PGPASSWORD", "envpw")
        args = argparse.Namespace(
            target_host="th", target_port=6543, target_dbname="tdb",
            target_user="tu", target_password="", target_sslmode=None,
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_target(args)
        assert mock_connect.call_args.args[4] == "envpw"

    def test_forwards_target_sslrootcert_when_set(self, monkeypatch):
        """Snowflake Postgres targets registered via `pg_connect --create`
        carry sslrootcert in the service file; connect_target must thread it
        through so verify-ca succeeds against the per-instance CA."""
        monkeypatch.delenv("TARGET_PGPASSWORD", raising=False)
        args = argparse.Namespace(
            target_host="sf", target_port=5432, target_dbname="analytics",
            target_user="snowflake_admin", target_password="pw",
            target_sslmode="verify-ca", target_sslrootcert="/snowflake/ca.pem",
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_target(args)
        mock_connect.assert_called_once_with(
            "sf", 5432, "analytics", "snowflake_admin", "pw", "verify-ca",
            sslrootcert="/snowflake/ca.pem", hostaddr=None,
        )

    def test_forwards_target_hostaddr_when_set(self, monkeypatch):
        """target_hostaddr is forwarded so libpq-backed callers can bypass DNS."""
        monkeypatch.delenv("TARGET_PGPASSWORD", raising=False)
        args = argparse.Namespace(
            target_host="sf.example.com", target_port=5432, target_dbname="analytics",
            target_user="snowflake_admin", target_password="pw", target_sslmode="require",
            target_sslrootcert=None, target_hostaddr="203.0.113.11",
        )
        with patch.object(pg_common, "connect") as mock_connect:
            pg_common.connect_target(args)
        mock_connect.assert_called_once_with(
            "sf.example.com", 5432, "analytics", "snowflake_admin", "pw", "require",
            sslrootcert=None, hostaddr="203.0.113.11"
        )
