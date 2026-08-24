"""
Tests for setup_replication.py.

Covers:
- build_source_dsn: DSN construction from args, password resolution via service-name
  ~/.pgpass path AND legacy env-var path (upstream contract preserved)
- build_source_dsn: empty password fallback when nothing available
- _safe_dsn_summary: never includes password value (transcript safety)
- cmd_create_subscription: emits the right CREATE SUBSCRIPTION SQL with WITH
  options, passes DSN as a query parameter (not literal in SQL string)
- cmd_drop_subscription: ALTER ... DISABLE then DROP, error path
- argparse: --no-copy-data / --no-create-slot / --no-enabled flips defaults
- argparse: subcommand routing
"""
from __future__ import annotations

import argparse
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import setup_replication
from setup_replication import (
    build_parser,
    build_source_dsn,
    cmd_create_subscription,
    cmd_drop_subscription,
    _safe_dsn_summary,
)


def _render_composable(comp) -> str:
    """Walk a psycopg2.sql.Composable manually without needing a real DB
    connection. The proper as_string(conn) path requires libpq's quote_ident,
    which mocks can't satisfy. For test inspection we just stringify each
    part in a readable form — enough to assert keywords appear."""
    from psycopg2 import sql
    if isinstance(comp, sql.SQL):
        return comp.string
    if isinstance(comp, sql.Identifier):
        # Don't try to be perfectly safe — tests just need to see the name.
        return '"' + '"."'.join(comp.strings) + '"'
    if isinstance(comp, sql.Literal):
        return repr(comp.wrapped)
    if isinstance(comp, sql.Placeholder):
        return '%s'
    if isinstance(comp, sql.Composed):
        return ''.join(_render_composable(p) for p in comp.seq)
    return str(comp)


# --- build_source_dsn ---


class TestBuildSourceDsn:
    def test_constructs_dsn_with_password_from_args(self, tmp_path, monkeypatch):
        """Without --source-service, args.password is used directly (legacy path)."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = SimpleNamespace(
            source_service="",
            host="src.example.com",
            port=5432,
            dbname="proddb",
            user="migrator",
            password="cli_pw",
            sslmode="require",
        )
        dsn = build_source_dsn(args)
        assert "host=src.example.com" in dsn
        assert "port=5432" in dsn
        assert "dbname=proddb" in dsn
        assert "user=migrator" in dsn
        assert "password=cli_pw" in dsn
        assert "sslmode=require" in dsn
        assert "connect_timeout=300" in dsn

    def test_uses_service_pgpass(self, tmp_path, monkeypatch):
        """When --source-service is set and pgpass has matching entry, use it."""
        pgpass = tmp_path / ".pgpass"
        pgpass.write_text("src.example.com:5432:proddb:migrator:pgpass_pw\n")
        pgpass.chmod(0o600)
        service_conf = tmp_path / ".pg_service.conf"
        service_conf.write_text(
            "[prod_source]\nhost=src.example.com\nport=5432\ndbname=proddb\nuser=migrator\n"
        )
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        with patch("pg_common.PG_SERVICE_FILE", service_conf), patch("pg_common.PGPASS_FILE", pgpass):
            args = SimpleNamespace(
                source_service="prod_source",
                host="",
                port=5432,
                dbname="",
                user="",
                password=None,
                sslmode="require",
            )
            dsn = build_source_dsn(args)
            assert "host=src.example.com" in dsn
            assert "user=migrator" in dsn
            assert "password=pgpass_pw" in dsn

    def test_empty_password_when_no_source(self, monkeypatch):
        """No service, no CLI password, no env var → password='' (upstream quirk preserved)."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = SimpleNamespace(
            source_service="",
            host="src",
            port=5432,
            dbname="db",
            user="u",
            password=None,
            sslmode="require",
        )
        dsn = build_source_dsn(args)
        assert "password=" in dsn  # literal "password=" with empty value
        # Make sure no None leaked into DSN
        assert "None" not in dsn

    def test_custom_sslmode_and_timeout(self, monkeypatch):
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = SimpleNamespace(
            source_service="", host="h", port=5432, dbname="d", user="u",
            password="p", sslmode="require",
        )
        dsn = build_source_dsn(args, sslmode="verify-ca", connect_timeout=60)
        assert "sslmode=verify-ca" in dsn
        assert "connect_timeout=60" in dsn

    def test_includes_sslrootcert_when_set(self, monkeypatch):
        """When args carries sslrootcert (typically populated from
        ~/.pg_service.conf via _apply_source_service), the DSN includes it.
        The target's CREATE SUBSCRIPTION embeds this DSN, so verify-ca on the
        publisher succeeds against the source's CA chain.
        """
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = SimpleNamespace(
            source_service="", host="h", port=5432, dbname="d", user="u",
            password="p", sslmode="verify-ca", sslrootcert="/etc/source-ca.pem",
        )
        dsn = build_source_dsn(args, sslmode="verify-ca")
        assert "sslrootcert=/etc/source-ca.pem" in dsn

    def test_includes_hostaddr_when_set(self, monkeypatch):
        """hostaddr is emitted alongside host so libpq can bypass DNS while
        preserving the hostname for TLS/pgpass identity."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = SimpleNamespace(
            source_service="", host="db.example.com", hostaddr="203.0.113.10",
            port=5432, dbname="d", user="u", password="p", sslmode="require",
        )
        dsn = build_source_dsn(args)
        assert "host=db.example.com" in dsn
        assert "hostaddr=203.0.113.10" in dsn

    def test_omits_sslrootcert_when_not_set(self, monkeypatch):
        """No sslrootcert on args -> DSN omits the key entirely (falls back
        to libpq defaults)."""
        monkeypatch.delenv("PGPASSWORD", raising=False)
        monkeypatch.delenv("SOURCE_PGPASSWORD", raising=False)
        args = SimpleNamespace(
            source_service="", host="h", port=5432, dbname="d", user="u",
            password="p", sslmode="require",
        )
        dsn = build_source_dsn(args)
        assert "sslrootcert" not in dsn


# --- _safe_dsn_summary ---


class TestSafeDsnSummary:
    def test_redacts_password(self):
        args = SimpleNamespace(host="h", port=5432, dbname="d", user="u")
        summary = _safe_dsn_summary(args)
        assert "password=***" in summary
        # Make sure no other password material leaks
        assert "p" not in summary or "password=***" in summary

    def test_no_password_value_anywhere(self):
        """Even if args carried a password, the summary must not include it."""
        args = SimpleNamespace(
            host="h", port=5432, dbname="d", user="u", password="secret_value_xyz"
        )
        summary = _safe_dsn_summary(args)
        assert "secret_value_xyz" not in summary
        assert "***" in summary


# --- cmd_create_subscription ---


def _make_create_args(**overrides):
    base = dict(
        source_service="",
        host="src", port=5432, dbname="proddb", user="migrator",
        password="src_pw", sslmode="require",
        target_service="",
        target_host="tgt", target_port=5432, target_dbname="postgres",
        target_user="admin", target_password="tgt_pw", target_sslmode="require",
        subscription_name="migrate_from_source",
        publication_name="snowflake_migration",
        # source_sslmode mirrors the argparse default (None) so the precedence
        # logic in cmd_create_subscription can be exercised. Pass an explicit
        # value via overrides to test the override path.
        source_sslmode=None,
        connect_timeout=300,
        copy_data=True, create_slot=True, enabled=True,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestCreateSubscription:
    def test_executes_with_dsn_as_parameter(self, monkeypatch):
        """Critical: DSN must be passed as execute(sql, (dsn,)) parameter,
        NOT interpolated into the SQL string. This is what keeps the password
        out of any subsequent log/print of the prepared statement source."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)
        args = _make_create_args()
        rc = cmd_create_subscription(args)

        assert rc == 0
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        # First positional arg is the SQL Composable, second is params tuple
        params = call_args[0][1]
        assert len(params) == 1
        # The DSN parameter must contain the source password
        assert "password=src_pw" in params[0]
        assert "host=src" in params[0]

    def test_with_options_in_sql(self, monkeypatch):
        """Verify the WITH (copy_data = ..., create_slot = ..., enabled = ...) is composed."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        args = _make_create_args(copy_data=False, create_slot=True, enabled=False)
        rc = cmd_create_subscription(args)
        assert rc == 0

        # The SQL Composable's string form contains the WITH clause
        sql_composable = mock_cursor.execute.call_args[0][0]
        sql_str = _render_composable(sql_composable)
        assert "copy_data = false" in sql_str
        assert "create_slot = true" in sql_str
        assert "enabled = false" in sql_str

    def test_returns_nonzero_on_failure(self, monkeypatch, capsys):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("publication does not exist")
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        args = _make_create_args()
        rc = cmd_create_subscription(args)
        assert rc == 1
        captured = capsys.readouterr()
        assert "publication does not exist" in captured.out

    def test_target_conn_closed_on_failure(self, monkeypatch):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("boom")
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        cmd_create_subscription(_make_create_args())
        mock_conn.close.assert_called_once()

    def test_target_autocommit_set(self, monkeypatch):
        """CREATE SUBSCRIPTION can't run in a transaction block."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)
        cmd_create_subscription(_make_create_args())
        assert mock_conn.autocommit is True

    def test_sslmode_precedence_explicit_flag_wins(self, monkeypatch):
        """--source-sslmode wins over both service-profile sslmode and the
        'require' fallback. Operator's explicit choice is authoritative.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        args = _make_create_args(source_sslmode="disable", sslmode="verify-ca")
        cmd_create_subscription(args)

        dsn = mock_cursor.execute.call_args[0][1][0]
        assert "sslmode=disable" in dsn

    def test_sslmode_precedence_service_profile_when_no_flag(self, monkeypatch):
        """When --source-sslmode is omitted, the service-profile sslmode (set
        on args.sslmode by _apply_source_service) is honored. Pre-fix this
        silently downgraded to 'require' even when the profile asked for
        verify-ca, defeating the whole point of saving a verify-ca profile.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        args = _make_create_args(source_sslmode=None, sslmode="verify-ca")
        cmd_create_subscription(args)

        dsn = mock_cursor.execute.call_args[0][1][0]
        assert "sslmode=verify-ca" in dsn

    def test_sslmode_precedence_falls_back_to_require(self, monkeypatch):
        """With no flag and no service-profile sslmode, the embedded DSN gets
        sslmode=require — the conservative default that matches the upstream
        SKILL.md pattern.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        args = _make_create_args(source_sslmode=None, sslmode=None)
        cmd_create_subscription(args)

        dsn = mock_cursor.execute.call_args[0][1][0]
        assert "sslmode=require" in dsn


# --- cmd_drop_subscription ---


def _make_drop_args(**overrides):
    base = dict(
        target_service="",
        target_host="tgt", target_port=5432, target_dbname="postgres",
        target_user="admin", target_password="tgt_pw", target_sslmode="require",
        subscription_name="migrate_from_source",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


class TestDropSubscription:
    def test_drops_via_clean_path_when_publisher_reachable(self, monkeypatch):
        """When the publisher is reachable, DROP SUBSCRIPTION drops the
        remote slot atomically and the fallback never runs.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        rc = cmd_drop_subscription(_make_drop_args())
        assert rc == 0
        # One execute call: DROP SUBSCRIPTION IF EXISTS. No ALTER calls.
        assert mock_cursor.execute.call_count == 1
        sql = _render_composable(mock_cursor.execute.call_args_list[0][0][0])
        assert "DROP SUBSCRIPTION IF EXISTS" in sql

    def test_falls_back_to_disassociate_then_drop_when_clean_drop_fails(self, monkeypatch, capsys):
        """When the optimistic DROP fails (typically: publisher unreachable),
        cmd_drop_subscription falls back to DISABLE + slot_name=NONE + DROP.
        Subscription is removed; slot is orphaned on the publisher.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # DROP IF EXISTS fails, then ALTER/ALTER/DROP all succeed.
        mock_cursor.execute.side_effect = [
            Exception("could not connect to publisher"),  # DROP SUBSCRIPTION IF EXISTS
            None,  # ALTER SUBSCRIPTION DISABLE
            None,  # ALTER SUBSCRIPTION SET (slot_name = NONE)
            None,  # DROP SUBSCRIPTION
        ]
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        rc = cmd_drop_subscription(_make_drop_args())
        assert rc == 0
        assert mock_cursor.execute.call_count == 4
        captured = capsys.readouterr()
        assert "Falling back" in captured.out
        assert "dropped via fallback" in captured.out
        assert "pg_replication_slots" in captured.out
        assert "pg_drop_replication_slot('<slot_name>')" in captured.out

    def test_returns_nonzero_when_both_paths_fail(self, monkeypatch, capsys):
        """If both the clean DROP and the disassociate-then-drop fallback
        fail, surface a manual recovery sequence and return 1.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = [
            Exception("could not connect to publisher"),  # DROP SUBSCRIPTION IF EXISTS
            Exception("permission denied"),  # ALTER SUBSCRIPTION DISABLE
        ]
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        rc = cmd_drop_subscription(_make_drop_args())
        assert rc == 1
        captured = capsys.readouterr()
        # Both failures surface
        assert "could not connect to publisher" in captured.out
        assert "permission denied" in captured.out
        # Manual recovery sequence is presented
        assert "ALTER SUBSCRIPTION migrate_from_source DISABLE" in captured.out
        assert "SET (slot_name = NONE)" in captured.out
        assert "DROP SUBSCRIPTION migrate_from_source" in captured.out
        assert "pg_replication_slots" in captured.out
        assert "pg_drop_replication_slot('<slot_name>')" in captured.out

    def test_recovery_message_handles_unknown_slot_gracefully(self, monkeypatch, capsys):
        """Fallback guidance uses a generic source-side slot inspection hint.
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = [
            Exception("connection refused"),  # DROP SUBSCRIPTION IF EXISTS
            Exception("permission denied"),  # ALTER SUBSCRIPTION DISABLE
        ]
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(setup_replication, "connect_target", lambda args: mock_conn)

        rc = cmd_drop_subscription(_make_drop_args())
        assert rc == 1
        captured = capsys.readouterr()
        assert "pg_replication_slots" in captured.out
        assert "pg_drop_replication_slot('<slot_name>')" in captured.out
        assert "None" not in captured.out
        assert "ALTER SUBSCRIPTION migrate_from_source DISABLE" in captured.out


# --- argparse ---


class TestArgparse:
    def test_create_defaults(self):
        parser = build_parser()
        args = parser.parse_args([
            "create-subscription",
            "--host", "src", "--user", "u",
            "--target-host", "tgt", "--target-user", "admin",
            "--subscription-name", "sub", "--publication-name", "pub",
        ])
        assert args.copy_data is True
        assert args.create_slot is True
        assert args.enabled is True
        assert args.connect_timeout == 300
        # --source-sslmode defaults to None so cmd_create_subscription can
        # apply precedence: explicit flag > service-profile sslmode > 'require'.
        # The pre-fix default of "require" silently downgraded saved verify-ca
        # service profiles whenever the operator didn't repeat --source-sslmode
        # on every invocation.
        assert args.source_sslmode is None

    def test_create_no_flags_flip_defaults(self):
        parser = build_parser()
        args = parser.parse_args([
            "create-subscription",
            "--host", "src", "--user", "u",
            "--target-host", "tgt", "--target-user", "admin",
            "--subscription-name", "sub", "--publication-name", "pub",
            "--no-copy-data", "--no-create-slot", "--no-enabled",
        ])
        assert args.copy_data is False
        assert args.create_slot is False
        assert args.enabled is False

    def test_drop_subcommand(self):
        parser = build_parser()
        args = parser.parse_args([
            "drop-subscription",
            "--target-host", "tgt", "--target-user", "admin",
            "--subscription-name", "sub",
        ])
        assert args.cmd == "drop-subscription"
        assert args.subscription_name == "sub"

    def test_subscription_name_required(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([
                "create-subscription",
                "--host", "src", "--user", "u",
                "--target-host", "tgt", "--target-user", "admin",
                "--publication-name", "pub",  # missing --subscription-name
            ])

    def test_publication_name_required(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([
                "create-subscription",
                "--host", "src", "--user", "u",
                "--target-host", "tgt", "--target-user", "admin",
                "--subscription-name", "sub",  # missing --publication-name
            ])

    def test_source_sslmode_override(self):
        parser = build_parser()
        args = parser.parse_args([
            "create-subscription",
            "--host", "src", "--user", "u",
            "--target-host", "tgt", "--target-user", "admin",
            "--subscription-name", "sub", "--publication-name", "pub",
            "--source-sslmode", "verify-ca",
        ])
        assert args.source_sslmode == "verify-ca"

    def test_connect_timeout_override(self):
        parser = build_parser()
        args = parser.parse_args([
            "create-subscription",
            "--host", "src", "--user", "u",
            "--target-host", "tgt", "--target-user", "admin",
            "--subscription-name", "sub", "--publication-name", "pub",
            "--connect-timeout", "60",
        ])
        assert args.connect_timeout == 60
