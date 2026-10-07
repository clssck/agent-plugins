"""
Unit tests for pg_lake_catalog.py — validators, error translator, connection
wrapper, argparse surface, and subcommand handlers.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import snowflake.connector

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

from pg_lake_catalog import (
    AUTO_REFRESH_COST_SUGGESTED_INTERVAL,
    AUTO_REFRESH_COST_WARNING_THRESHOLD,
    ERROR_PATTERNS,
    REFRESH_INTERVAL_MAX,
    REFRESH_INTERVAL_MIN,
    _build_parser,
    _DISPATCH,
    _emit,
    _extract_iceberg_tables_from_show,
    _extract_instance_names,
    _extract_param_value,
    _param_is_true,
    _rank_available_roles,
    _run_query_safely,
    build_auto_refresh_cost_warning,
    get_snowflake_connection,
    main,
    translate_error,
    validate_catalog_name,
    validate_integration_name,
    validate_namespace,
    validate_refresh_interval,
    validate_table_name,
)


# ---------------------------------------------------------------------------
# test_validation (T011)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("validator", [
    validate_catalog_name,
    validate_integration_name,
    validate_table_name,
    validate_namespace,
])
class TestValidation:
    """Every validator rejects the same injection vectors and accepts the same shapes."""

    @pytest.mark.parametrize("good", [
        "postgres",
        "appdb",
        "my_integration",
        "_leading_underscore",
        "Mixed_Case_123",
        "with$dollar",
        "A",
    ])
    def test_accepts_valid_identifiers(self, validator, good):
        assert validator(good) == good

    @pytest.mark.parametrize("bad", [
        "",
        "1leading_digit",
        "has space",
        "has-dash",
        "has.dot",
        "has/slash",
        "'quoted'",
        '"double-quoted"',
        "drop; DROP TABLE users",
        "name--comment",
        "name/*comment*/",
        "null\x00byte",
    ])
    def test_rejects_injection_vectors(self, validator, bad):
        with pytest.raises(ValueError):
            validator(bad)

    def test_rejects_overflow(self, validator):
        with pytest.raises(ValueError):
            validator("a" * 300)


# ---------------------------------------------------------------------------
# test_error_translation (T012)
# ---------------------------------------------------------------------------

class TestErrorTranslation:

    def test_invalid_instance(self):
        raw = (
            "002001 (02000): SQL compilation error:\n"
            "Object 'definitely_not_a_real_instance_xyz' does not exist or not authorized."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "definitely_not_a_real_instance_xyz" in friendly
        # Friendly message must surface BOTH possibilities — instance doesn't
        # exist, OR role lacks USAGE on it. SHOW POSTGRES INSTANCES filters
        # silently by role, which is the most common cause and the easiest
        # to confuse with "doesn't exist".
        assert "USAGE" in friendly
        assert "check-account-params" in friendly
        assert "--use-role" in friendly
        # USAGE must appear before "does not exist" — most-likely cause
        # surfaces first so the agent investigates the right thing first.
        assert friendly.index("USAGE") < friendly.index("does not exist")

    def test_invalid_table_with_snowflake_template_bug(self):
        # Snowflake's error string contains literal {1}/{2} placeholders — the
        # pattern must be regex-based and extract table + namespace before
        # those placeholders appear.
        raw = (
            "093740 (22023): Could not find Iceberg table "
            "'Table 'definitely_not_a_real_table_xyz' not found in namespace "
            "'public'' in the schema '{1}' in the postgres database '{2}'."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "definitely_not_a_real_table_xyz" in friendly
        assert "public" in friendly
        assert "list-pg-iceberg" in friendly

    def test_wrong_catalog_name_lazy_failure(self):
        raw = (
            "000603 (XX000): SQL execution internal error:\n"
            "INTERNAL_ERROR: CrunchyCatalogSnapshotReader::readFileContents():"
            "Failed to read catalog file(...)- "
            "databaseName wrongdb, relativePath wrongdb/catalog.json, "
            "fullPath frompg/catalog/wrongdb/catalog.json caused by exception"
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "wrongdb" in friendly
        # Must clarify CATALOG_NAME = PG database (common point of confusion
        # with Snowflake database name) BEFORE jumping to the destructive
        # drop-and-recreate suggestion.
        assert "Postgres database" in friendly
        assert "list-pg-iceberg" in friendly
        # Drop-and-recreate is still mentioned (real recovery if the name
        # is genuinely wrong), but as a last resort.
        assert "drop and recreate" in friendly.lower()
        # The verify step (list-pg-iceberg) must appear before the destructive
        # drop-and-recreate suggestion.
        assert friendly.index("list-pg-iceberg") < friendly.lower().index("drop and recreate")

    def test_feature_not_enabled(self):
        # Raised on accounts without ENABLE_SNOWFLAKE_POSTGRES set — the
        # account-level flag for the catalog integration path. Distinct
        # from pg_instance_pg_lake_not_supported (instance-level).
        raw = "004101 (42601): Invalid option CATALOG_SOURCE on catalog integration."
        friendly = translate_error(raw)
        assert friendly is not None
        assert "ENABLE_SNOWFLAKE_POSTGRES" in friendly
        assert "check-account-params" in friendly

    def test_pg_instance_pg_lake_not_supported(self):
        # Distinct from feature_not_enabled: here the account accepts the
        # DDL but the PG instance layer rejects it. The friendly message
        # must direct the user at the server-side maintenance operation,
        # not at retrying with a different role.
        raw = (
            "604061 (22000): POSTGRES INSTANCE 'PG_LAKE_TEST2' does not "
            "support use of pg_lake. Please run a Postgres maintenance "
            "operation on your instance."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "PG_LAKE_TEST2" in friendly
        assert "maintenance" in friendly.lower()
        # Must NOT suggest --use-role (this isn't a privilege issue) — a
        # role-retry suggestion would send the agent chasing its tail.
        assert "--use-role" not in friendly

    def test_object_already_exists(self):
        raw = (
            "002002 (42710): SQL compilation error:\n"
            "Object 'MY_INTEGRATION' already exists."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "MY_INTEGRATION" in friendly
        assert "describe-integration" in friendly

    @pytest.mark.parametrize("kind,name", [
        ("Integration", "MY_CI"),
        ("Iceberg table", "PG_DB_ACCOUNTADMIN.PUBLIC.MY_TABLE"),
        ("Database", "MY_CLD"),
    ])
    def test_object_not_found(self, kind, name):
        raw = (
            f"002003 (02000): SQL compilation error:\n"
            f"{kind} '{name}' does not exist or not authorized."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert kind in friendly
        assert name in friendly

    def test_missing_external_volume_hints_at_catalog(self):
        # Raised when CREATE ICEBERG TABLE references a non-existent catalog
        # integration — SF falls back to treating it as a regular iceberg table.
        raw = (
            "393923 (42601): Iceberg table MY_TABLE must have the table parameter "
            "EXTERNAL_VOLUME defined on the table, schema, database, or account."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "MY_TABLE" in friendly
        assert "catalog" in friendly.lower()
        assert "describe-integration" in friendly
        # Must explicitly steer the user away from the EXTERNAL_VOLUME
        # rabbit hole — without this, agents tend to "fix" the symptom
        # (create an external volume) instead of the cause (wrong --catalog).
        assert "do NOT" in friendly or "do not" in friendly.lower()

    @pytest.mark.parametrize("value", [-1, 0, 1, 29, 86401, 99999999])
    def test_refresh_interval_out_of_range(self, value):
        raw = (
            f"001008 (22023): SQL compilation error:\n"
            f"invalid value [{value}] for parameter 'REFRESH_INTERVAL_SECONDS'"
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert str(value) in friendly
        assert "30" in friendly and "86400" in friendly

    def test_cld_allowed_write_missing(self):
        raw = (
            "094124 (22023): SQL Compilation Error: SNOWFLAKE_POSTGRES "
            "catalog-linked databases must explicitly specify "
            "ALLOWED_WRITE_OPERATIONS. ALLOWED_WRITE_OPERATIONS must be set "
            "to NONE for SNOWFLAKE_POSTGRES catalogs."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "ALLOWED_WRITE_OPERATIONS = NONE" in friendly
        assert "create-cld" in friendly

    @pytest.mark.parametrize("bad_value", ["ALL", "INSERT_ONLY", "SOMETHING_ELSE"])
    def test_cld_allowed_write_wrong_value(self, bad_value):
        raw = (
            "094123 (22023): SQL Compilation Error: SNOWFLAKE_POSTGRES "
            "catalog-linked databases must be read-only. "
            f"ALLOWED_WRITE_OPERATIONS must be set to NONE, but '{bad_value}' "
            "was provided."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert bad_value in friendly
        assert "NONE" in friendly

    @pytest.mark.parametrize("privilege", [
        "CREATE CATALOG INTEGRATION",
        "CREATE DATABASE",
        "CREATE ICEBERG TABLE",
    ])
    def test_insufficient_privileges_account(self, privilege):
        # One regex handles every "must have <PRIVILEGE> granted on ACCOUNT"
        # variant — captured on a role lacking the relevant ON ACCOUNT grant.
        raw = (
            "003001 (42501): SQL access control error:\n"
            f"Insufficient privileges to operate on account 'PGTEST'. "
            f"Your primary role PUBLIC must have {privilege} granted on "
            "ACCOUNT PGTEST."
        )
        friendly = translate_error(raw)
        assert friendly is not None
        assert "PUBLIC" in friendly
        assert privilege in friendly
        assert "PGTEST" in friendly
        assert "--use-role" in friendly
        assert "GRANT" in friendly

    def test_unknown_error_returns_none(self):
        raw = "some totally random error that doesn't match any pattern"
        assert translate_error(raw) is None

    def test_empty_error_returns_none(self):
        assert translate_error("") is None
        assert translate_error(None) is None  # type: ignore[arg-type]

    def test_all_patterns_have_format_fields_in_template(self):
        # Every ERROR_PATTERNS entry's template must only reference group
        # names present in its own regex — mismatches would raise KeyError
        # at runtime.
        for key, (pattern, template) in ERROR_PATTERNS.items():
            group_names = set(pattern.groupindex.keys())
            dummy_values = {name: f"<{name}>" for name in group_names}
            try:
                template.format(**dummy_values)
            except KeyError as e:
                pytest.fail(f"ERROR_PATTERNS[{key!r}] template references unknown group {e}")


# ---------------------------------------------------------------------------
# test_sf_connection_mock (T013)
# ---------------------------------------------------------------------------

class TestSnowflakeConnection:

    def test_env_var_path(self, monkeypatch):
        monkeypatch.setenv("SNOWFLAKE_ACCOUNT", "ACME-TEST")
        monkeypatch.setenv("SNOWFLAKE_USER", "alice")
        monkeypatch.setenv("SNOWFLAKE_PASSWORD", "hunter2")
        monkeypatch.delenv("SNOWFLAKE_AUTHENTICATOR", raising=False)
        monkeypatch.delenv("SNOWFLAKE_ROLE", raising=False)

        with patch("pg_lake_catalog.snowflake.connector.connect") as mock_connect:
            mock_connect.return_value = MagicMock(name="conn")
            conn = get_snowflake_connection()

        mock_connect.assert_called_once()
        kwargs = mock_connect.call_args.kwargs
        assert kwargs["account"] == "ACME-TEST"
        assert kwargs["user"] == "alice"
        assert kwargs["password"] == "hunter2"
        assert conn is mock_connect.return_value

    def test_named_connection_delegates_to_sf_session(self, monkeypatch):
        """Saved-connection auth flows through sf_session.open_snowflake_connection
        so it works on hosts with only the `snow` CLI (Windows ARM64).
        Centralized private_key_path / token_file_path handling lives in
        pg_connect.get_snowflake_connection now — covered by pg_connect's
        own test suite, not duplicated here."""
        monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)
        monkeypatch.delenv("SNOWFLAKE_USER", raising=False)

        fake_conn = MagicMock(name="conn")
        with patch("sf_session.open_snowflake_connection", return_value=fake_conn) as mock_open:
            result = get_snowflake_connection(connection_name="prod")

        mock_open.assert_called_once_with(connection="prod")
        assert result is fake_conn


# ---------------------------------------------------------------------------
# argparse surface (T010 checkpoint)
# ---------------------------------------------------------------------------

class TestArgparseSurface:

    def test_parser_lists_twelve_subcommands(self):
        parser = _build_parser()
        subparsers_action = next(
            a for a in parser._subparsers._group_actions  # type: ignore[attr-defined]
            if a.dest == "command"
        )
        commands = set(subparsers_action.choices.keys())
        expected = {
            "check-account-params", "list-pg-iceberg", "create-integration",
            "describe-integration", "drop-integration", "create-iceberg-table",
            "create-cld", "cld-status", "refresh", "set-auto-refresh",
            "set-refresh-interval", "status",
        }
        assert commands == expected, f"missing: {expected - commands}; extra: {commands - expected}"

    def test_every_command_has_a_dispatch_entry(self):
        parser = _build_parser()
        subparsers_action = next(
            a for a in parser._subparsers._group_actions  # type: ignore[attr-defined]
            if a.dest == "command"
        )
        for cmd in subparsers_action.choices.keys():
            assert cmd in _DISPATCH, f"no dispatch entry for {cmd}"

    def test_main_returns_1_when_no_command_given(self, capsys):
        rc = main([])
        assert rc == 1
        out = capsys.readouterr().out
        assert "usage:" in out.lower()

    # test_stub_subcommand_exits_2 was removed when T040 landed — all 12
    # subcommands now have real bodies. Per-command test classes cover
    # exit-code expectations for their respective subcommand.

    @pytest.mark.parametrize("argv", [
        ["create-integration", "--name", "n", "--postgres-instance", "i",
         "--database", "postgres", "--use-role", "ACCOUNTADMIN", "--json"],
        ["describe-integration", "--name", "n",
         "--use-role", "SYSADMIN", "--json"],
        ["drop-integration", "--name", "n", "--confirm",
         "--use-role", "ACCOUNTADMIN", "--json"],
        ["create-iceberg-table", "--name", "t", "--catalog", "c",
         "--catalog-table-name", "pt",
         "--use-role", "ACCOUNTADMIN", "--json"],
        ["create-cld", "--name", "db", "--catalog", "c",
         "--use-role", "ACCOUNTADMIN", "--json"],
        ["refresh", "--name", "t",
         "--use-role", "SYSADMIN", "--json"],
        ["set-auto-refresh", "--name", "t", "--enabled", "true",
         "--use-role", "SYSADMIN", "--json"],
        ["set-refresh-interval", "--integration", "c", "--seconds", "60",
         "--use-role", "ACCOUNTADMIN", "--json"],
    ])
    def test_use_role_accepted_by_mutating_subcommands(self, argv):
        # Pure argparse acceptance — catches drift where a new subcommand
        # forgets _add_use_role_arg(). Parses only; doesn't execute.
        parser = _build_parser()
        parsed = parser.parse_args(argv)
        assert parsed.use_role in {"ACCOUNTADMIN", "SYSADMIN"}

    @pytest.mark.parametrize("readonly_cmd", [
        "cld-status",
        "status",
    ])
    def test_readonly_object_query_subcommands_do_not_accept_use_role(
        self, capsys, readonly_cmd,
    ):
        """
        cld-status and status inspect a specific object the user already
        holds privilege on. Role escalation isn't the right affordance there
        — it would imply the command mutates or reaches across roles.
        check-account-params is the deliberate exception: role visibility
        IS its primary diagnostic.
        """
        argv_map = {
            "cld-status": [readonly_cmd, "--name", "db", "--use-role", "ACCOUNTADMIN"],
            "status": [readonly_cmd, "--name", "t", "--use-role", "ACCOUNTADMIN"],
        }
        with pytest.raises(SystemExit):
            main(argv_map[readonly_cmd])

    def test_check_account_params_accepts_use_role(self):
        # Parser acceptance only — the actual query path is tested with a
        # mocked connection in TestCheckAccountParams.
        parser = _build_parser()
        parsed = parser.parse_args([
            "check-account-params", "--use-role", "ACCOUNTADMIN", "--json",
        ])
        assert parsed.command == "check-account-params"
        assert parsed.use_role == "ACCOUNTADMIN"


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

class TestEmit:

    def test_json_output_roundtrip(self, capsys):
        _emit({"a": 1, "b": "two", "c": [1, 2, 3]}, as_json=True)
        out = capsys.readouterr().out
        import json as _json
        parsed = _json.loads(out)
        assert parsed == {"a": 1, "b": "two", "c": [1, 2, 3]}

    def test_pretty_output_key_value_lines(self, capsys):
        _emit({"status": "ok", "count": 3}, as_json=False)
        out = capsys.readouterr().out
        assert "status: ok" in out
        assert "count: 3" in out


# ---------------------------------------------------------------------------
# Client-side REFRESH_INTERVAL_SECONDS validation
# ---------------------------------------------------------------------------

class TestCheckAccountParamsHelpers:
    """
    Unit tests for the pure helper functions that underpin cmd_check_account_params.
    Kept separate from the integration-style cmd test so the building blocks can
    regress independently.
    """

    def test_extract_param_value_from_show_parameters_row(self):
        # SHOW PARAMETERS column shape: [key, value, default, level, description, type]
        rows = [("ENABLE_SNOWFLAKE_POSTGRES", "true", "false", "ACCOUNT", "...", "BOOLEAN")]
        got = _extract_param_value(rows)
        assert got == {"value": "true", "default": "false", "level": "ACCOUNT"}

    def test_extract_param_value_empty_means_param_not_present(self):
        # Params not enabled on an account return zero rows from
        # SHOW PARAMETERS — distinct from "param exists but is false".
        assert _extract_param_value([]) is None

    def test_extract_instance_names_finds_name_column_via_description(self):
        # Real Snowflake SHOW POSTGRES INSTANCES leads with `created_on`.
        description = [
            ("created_on", None), ("name", None), ("compute_pool", None),
        ]
        rows = [
            ("2026-04-23", "LH_TEST1", "GENERAL_64"),
            ("2026-04-22", "LH_TEST2", "GENERAL_32"),
        ]
        assert _extract_instance_names(rows, description) == ["LH_TEST1", "LH_TEST2"]

    def test_extract_instance_names_falls_back_when_no_name_column(self):
        rows = [("2026-04-23", "LH_TEST1"), ("2026-04-22", "LH_TEST2")]
        # Without a description that identifies "name", falls back to idx 1.
        assert _extract_instance_names(rows, None) == ["LH_TEST1", "LH_TEST2"]

    def test_extract_instance_names_empty(self):
        assert _extract_instance_names([], None) == []

    def test_rank_available_roles_puts_accountadmin_first(self):
        roles = ["PUBLIC", "ANALYST", "ACCOUNTADMIN", "SYSADMIN"]
        ranked = _rank_available_roles(roles, current="PUBLIC")
        assert ranked[0]["role"] == "ACCOUNTADMIN"
        assert ranked[0]["label"] == "Recommended"
        admin_labels = [r["label"] for r in ranked if "ADMIN" in r["role"] and r["role"] != "ACCOUNTADMIN"]
        assert all(label == "Likely works" for label in admin_labels)

    def test_rank_available_roles_flags_current(self):
        roles = ["ACCOUNTADMIN", "PUBLIC"]
        ranked = _rank_available_roles(roles, current="PUBLIC")
        labels_by_role = {r["role"]: r["label"] for r in ranked}
        assert labels_by_role.get("PUBLIC") == "Current role"

    def test_rank_available_roles_no_current(self):
        # When current is None (rare but possible if CURRENT_ROLE query failed),
        # ranking still works and picks the first non-admin label.
        roles = ["ACCOUNTADMIN", "ANALYST"]
        ranked = _rank_available_roles(roles, current=None)
        assert len(ranked) == 2
        assert ranked[0]["role"] == "ACCOUNTADMIN"

    def test_rank_available_roles_dedupes(self):
        # A role should never appear twice even if it qualifies under
        # multiple classification passes.
        roles = ["SECURITYADMIN"]
        ranked = _rank_available_roles(roles, current="SECURITYADMIN")
        assert len(ranked) == 1
        assert ranked[0]["role"] == "SECURITYADMIN"

    def test_param_is_true_various_shapes(self):
        assert _param_is_true({"value": "true"}) is True
        assert _param_is_true({"value": "TRUE"}) is True
        assert _param_is_true({"value": "True"}) is True
        assert _param_is_true({"value": "false"}) is False
        assert _param_is_true({"value": ""}) is False
        assert _param_is_true({"value": None}) is False
        assert _param_is_true({}) is False
        assert _param_is_true(None) is False

    def test_run_query_safely_ok_path(self):
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.fetchall.return_value = [("A",), ("B",)]
        conn = MagicMock()
        conn.cursor.return_value = cursor

        out = _run_query_safely(conn, "SELECT x", lambda rows: [r[0] for r in rows])
        assert out == {"status": "ok", "result": ["A", "B"]}

    def test_run_query_safely_error_path_captures_string(self):
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.execute.side_effect = RuntimeError("network policy blocked this query")
        conn = MagicMock()
        conn.cursor.return_value = cursor

        out = _run_query_safely(conn, "SHOW POSTGRES INSTANCES", lambda rows: rows)
        assert out["status"] == "error"
        assert "network policy" in out["error"]

    def test_run_query_safely_truncates_long_errors(self):
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.execute.side_effect = RuntimeError("x" * 1000)
        conn = MagicMock()
        conn.cursor.return_value = cursor

        out = _run_query_safely(conn, "SELECT 1", lambda rows: rows)
        assert out["status"] == "error"
        assert len(out["error"]) <= 500


class TestCheckAccountParamsCommand:
    """
    End-to-end test of cmd_check_account_params with a fake Snowflake
    connection. Covers both the happy path (all queries succeed) and the
    per-query graceful-degradation path (one query fails, rest still work).
    """

    @staticmethod
    def _build_fake_connection(query_handlers: dict[str, Any]):
        """
        Fake Snowflake connection where cursor.execute(sql) sets up the next
        fetchall() + description from query_handlers. Each handler value is
        either (rows, description) or an exception to raise on execute.
        """
        cursor = MagicMock()
        state = {"rows": [], "description": None}

        def on_execute(sql, *args, **kwargs):
            for key, value in query_handlers.items():
                if key in sql:
                    if isinstance(value, Exception):
                        raise value
                    rows, description = value
                    state["rows"] = rows
                    state["description"] = description
                    return
            state["rows"] = []
            state["description"] = None

        cursor.execute.side_effect = on_execute
        cursor.fetchall.side_effect = lambda: state["rows"]
        type(cursor).description = property(lambda self: state["description"])
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None

        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_happy_path_ok_true_everything_visible(self, capsys):
        conn = self._build_fake_connection({
            "ENABLE_SNOWFLAKE_POSTGRES": (
                [("ENABLE_SNOWFLAKE_POSTGRES", "true", "false", "ACCOUNT", "...", "BOOLEAN")],
                None,
            ),
            "ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME": (
                [("ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME", "true", "false", "ACCOUNT", "...", "BOOLEAN")],
                None,
            ),
            "ENABLE_POSTGRES_EXTERNAL_VOLUME": ([], None),
            "CURRENT_ROLE()": ([("ACCOUNTADMIN",)], None),
            "CURRENT_AVAILABLE_ROLES()": (
                [('["ACCOUNTADMIN","SYSADMIN","PUBLIC"]',)], None,
            ),
            "SHOW POSTGRES INSTANCES": (
                [("2026-04-23", "LH_TEST1", "GENERAL_64")],
                [("created_on", None), ("name", None), ("compute_pool", None)],
            ),
        })

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["check-account-params", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["current_role"] == "ACCOUNTADMIN"
        assert payload["instances_visible"] == ["LH_TEST1"]
        assert payload["instance_visibility_note"] is None
        assert payload["account_params"]["ENABLE_SNOWFLAKE_POSTGRES"]["status"] == "ok"
        roles = [r["role"] for r in payload["available_roles"]]
        assert roles[0] == "ACCOUNTADMIN"

    def test_zero_instances_emits_visibility_note(self, capsys):
        conn = self._build_fake_connection({
            "ENABLE_SNOWFLAKE_POSTGRES": (
                [("ENABLE_SNOWFLAKE_POSTGRES", "true", "false", "ACCOUNT", "...", "BOOLEAN")],
                None,
            ),
            "ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME": (
                [("ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME", "true", "false", "ACCOUNT", "...", "BOOLEAN")],
                None,
            ),
            "ENABLE_POSTGRES_EXTERNAL_VOLUME": ([], None),
            "CURRENT_ROLE()": ([("PUBLIC",)], None),
            "CURRENT_AVAILABLE_ROLES()": ([('["PUBLIC"]',)], None),
            "SHOW POSTGRES INSTANCES": ([], [("created_on", None), ("name", None)]),
        })

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["check-account-params", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["instances_visible"] == []
        note = payload["instance_visibility_note"]
        assert note is not None
        assert "PUBLIC" in note
        assert "no instances exist" in note
        assert "USAGE" in note
        assert "--use-role ACCOUNTADMIN" in note

    def test_feature_flag_off_ok_false_with_caution(self, capsys):
        conn = self._build_fake_connection({
            "ENABLE_SNOWFLAKE_POSTGRES": (
                [("ENABLE_SNOWFLAKE_POSTGRES", "false", "false", "", "", "BOOLEAN")],
                None,
            ),
            "ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME": ([], None),
            "ENABLE_POSTGRES_EXTERNAL_VOLUME": ([], None),
            "CURRENT_ROLE()": ([("ACCOUNTADMIN",)], None),
            "CURRENT_AVAILABLE_ROLES()": ([('["ACCOUNTADMIN"]',)], None),
            "SHOW POSTGRES INSTANCES": ([], None),
        })

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["check-account-params", "--json"])

        # The diagnostic itself ran cleanly → exit 0. The `ok` field is the
        # signal the agent/caller inspects to decide whether to proceed;
        # exit code is reserved for "the diagnostic couldn't complete".
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        cautions = " ".join(payload["cautions"])
        assert "ENABLE_SNOWFLAKE_POSTGRES" in cautions
        assert "returned FALSE" in cautions

    def test_feature_flag_absent_is_unknown_not_off(self, capsys):
        # Some accounts have the feature enabled but don't surface
        # ENABLE_SNOWFLAKE_POSTGRES via SHOW PARAMETERS — the query returns
        # 0 rows. This must NOT be treated as "feature off", or the agent
        # refuses to proceed on a perfectly provisioned account. The real
        # failure mode (feature actually off) still surfaces via the
        # feature_not_enabled translator on create-integration.
        conn = self._build_fake_connection({
            "ENABLE_SNOWFLAKE_POSTGRES": ([], None),
            "ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME": ([], None),
            "ENABLE_POSTGRES_EXTERNAL_VOLUME": ([], None),
            "CURRENT_ROLE()": ([("ACCOUNTADMIN",)], None),
            "CURRENT_AVAILABLE_ROLES()": ([('["ACCOUNTADMIN"]',)], None),
            "SHOW POSTGRES INSTANCES": ([], None),
        })

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["check-account-params", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        # ok must be True — we can't prove the feature is off, so don't block.
        assert payload["ok"] is True
        # The unverified state must be visible so the agent can relay it.
        assert "ENABLE_SNOWFLAKE_POSTGRES" in payload["unverified_params"]
        cautions = " ".join(payload["cautions"])
        assert "Could not verify" in cautions
        assert "feature_not_enabled" in cautions
        # Must NOT emit the strong "feature off" caution.
        assert "returned FALSE" not in cautions

    def test_one_query_error_does_not_kill_preflight(self, capsys):
        # Network policy blocking SHOW POSTGRES INSTANCES is realistic;
        # pre-flight should still return account_params + roles.
        conn = self._build_fake_connection({
            "ENABLE_SNOWFLAKE_POSTGRES": (
                [("ENABLE_SNOWFLAKE_POSTGRES", "true", "false", "ACCOUNT", "", "BOOLEAN")],
                None,
            ),
            "ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME": (
                [("ENABLE_POSTGRES_HIDDEN_EXTERNAL_VOLUME", "true", "false", "ACCOUNT", "", "BOOLEAN")],
                None,
            ),
            "ENABLE_POSTGRES_EXTERNAL_VOLUME": ([], None),
            "CURRENT_ROLE()": ([("ACCOUNTADMIN",)], None),
            "CURRENT_AVAILABLE_ROLES()": ([('["ACCOUNTADMIN"]',)], None),
            "SHOW POSTGRES INSTANCES": RuntimeError(
                "003001 (42501): SQL access control error: "
                "Insufficient privileges blocked by network policy"
            ),
        })

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["check-account-params", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True  # required params still TRUE
        assert isinstance(payload["instances_visible"], dict)
        assert payload["instances_visible"]["status"] == "error"
        assert "network policy" in payload["instances_visible"]["error"]
        assert payload["current_role"] == "ACCOUNTADMIN"

    def test_use_role_applies_session_override(self, capsys):
        captured_sqls: list[str] = []
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None

        def execute_recording(sql, *args, **kwargs):
            captured_sqls.append(sql)
            # Fixed minimal happy-path state: no rows, SHOW PARAMETERS empty,
            # roles empty. Just enough to confirm USE ROLE ran first.
            cursor.fetchall.return_value = []
            type(cursor).description = property(lambda self: None)

        cursor.execute.side_effect = execute_recording
        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main(["check-account-params", "--use-role", "ACCOUNTADMIN", "--json"])

        assert captured_sqls[0] == "USE ROLE ACCOUNTADMIN"

    def test_use_role_rejects_sql_injection(self, capsys):
        # _validate_unquoted_identifier should trip on the semicolon.
        conn = MagicMock()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "check-account-params",
                "--use-role", "ACCOUNTADMIN; DROP TABLE users",
                "--json",
            ])

        assert rc == 2  # ValueError path
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "prohibited characters" in payload["error"]


class TestListPgIceberg:
    """
    T021 — list-pg-iceberg reads the pg_lake `iceberg_tables` view on the PG
    side. Tests cover: happy-path row shape, missing-extension friendly error,
    and empty-result degenerate case.
    """

    @staticmethod
    def _fake_pg_connection(
        rows: list | None = None,
        raise_on_execute: Exception | None = None,
    ):
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        if raise_on_execute is not None:
            cursor.execute.side_effect = raise_on_execute
        cursor.fetchall.return_value = rows or []

        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_happy_path_returns_structured_rows(self, capsys):
        conn = self._fake_pg_connection(rows=[
            ("postgres", "public", "discovery_probe", "s3://owl/catalog/postgres/public/discovery_probe/metadata/v1.json"),
            ("postgres", "public", "sensor_readings", "s3://owl/catalog/postgres/public/sensor_readings/metadata/v2.json"),
        ])

        with patch("pg_lake_catalog.get_pg_connection", return_value=conn):
            rc = main(["list-pg-iceberg", "--connection-name", "lh_test1", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["count"] == 2
        assert payload["tables"][0] == {
            "catalog_name": "postgres",
            "namespace": "public",
            "table_name": "discovery_probe",
            "metadata_location": "s3://owl/catalog/postgres/public/discovery_probe/metadata/v1.json",
        }

    def test_empty_result_is_not_an_error(self, capsys):
        conn = self._fake_pg_connection(rows=[])
        with patch("pg_lake_catalog.get_pg_connection", return_value=conn):
            rc = main(["list-pg-iceberg", "--connection-name", "lh_test1", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["count"] == 0
        assert payload["tables"] == []

    def test_missing_view_emits_friendly_extension_hint(self, capsys):
        import pg_common

        # psycopg2.Error.pgcode is a readonly C descriptor — synthetic test
        # exceptions can't set it. Patch PgError to plain Exception so the
        # test exception can carry .pgcode as a regular attribute.
        class _UndefinedTable(Exception):
            def __init__(self, msg):
                super().__init__(msg)
                self.pgcode = "42P01"

        conn = self._fake_pg_connection(
            raise_on_execute=_UndefinedTable("relation \"iceberg_tables\" does not exist"),
        )

        with patch.object(pg_common, "PgError", Exception), \
             patch("pg_lake_catalog.get_pg_connection", return_value=conn):
            rc = main(["list-pg-iceberg", "--connection-name", "lh_test1", "--json"])

        assert rc == 1  # success=False path
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        friendly = payload["friendly_error"]
        assert "pg_lake extension is not installed" in friendly
        assert "pg_lake_setup.py" in friendly
        assert "--enable" in friendly
        # The target connection should be propagated so the agent can copy-paste the fix.
        assert "lh_test1" in friendly

    def test_other_pg_errors_surface_raw(self, capsys):
        # Auth errors, connection issues, unexpected SQL exceptions should
        # fall through to main()'s generic exception handler — not claim
        # the extension is missing when that's not the cause.
        conn = self._fake_pg_connection(
            raise_on_execute=RuntimeError("FATAL: password authentication failed"),
        )

        with patch("pg_lake_catalog.get_pg_connection", return_value=conn):
            rc = main(["list-pg-iceberg", "--connection-name", "lh_test1", "--json"])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "password authentication failed" in payload["error"]
        # We do NOT want to mislead with a "install pg_lake" hint when the
        # real problem is auth.
        assert "friendly_error" not in payload or \
            "pg_lake_setup" not in payload.get("friendly_error", "")


class TestCreateIntegration:
    """
    T022 — create-integration builds CREATE CATALOG INTEGRATION ... SQL with
    validated identifiers and soft-fails on already-exists so callers can
    branch on the flag instead of parsing exceptions.
    """

    @staticmethod
    def _fake_sf_connection(
        raise_on_execute: Exception | None = None,
    ):
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.executed_sql: list[str] = []  # type: ignore[attr-defined]

        def execute(sql, *args, **kwargs):
            cursor.executed_sql.append(sql)
            if raise_on_execute is not None and "CREATE CATALOG INTEGRATION" in sql:
                raise raise_on_execute

        cursor.execute.side_effect = execute
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn, cursor

    def test_happy_path_builds_canonical_sql(self, capsys):
        conn, cursor = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-integration",
                "--name", "pg_ci",
                "--postgres-instance", "LH_TEST1",
                "--database", "postgres",
                "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["name"] == "pg_ci"
        sql = payload["sql"]
        assert "CREATE CATALOG INTEGRATION pg_ci" in sql
        assert "CATALOG_SOURCE = SNOWFLAKE_POSTGRES" in sql
        assert "TABLE_FORMAT = ICEBERG" in sql
        assert "POSTGRES_INSTANCE = 'LH_TEST1'" in sql
        assert "CATALOG_NAME = 'postgres'" in sql
        assert "ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS" in sql
        assert "ENABLED = TRUE" in sql
        # CATALOG_NAMESPACE belongs to CREATE ICEBERG TABLE, not the
        # integration — make sure it isn't accidentally emitted here.
        assert "CATALOG_NAMESPACE" not in sql

    def test_already_exists_soft_fails_with_recovery_hint(self, capsys):
        prog_err = snowflake.connector.errors.ProgrammingError(
            msg="002002 (42710): SQL compilation error:\n"
                "Object 'PG_CI' already exists.",
        )
        conn, _ = self._fake_sf_connection(raise_on_execute=prog_err)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-integration",
                "--name", "pg_ci",
                "--postgres-instance", "LH_TEST1",
                "--database", "postgres",
                "--json",
            ])

        # success=False but NOT an exception — caller sees the soft-fail flag.
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert payload["already_exists"] is True
        assert "describe-integration" in payload["hint"]
        assert "drop-integration" in payload["hint"]
        assert "pg_ci" in payload["hint"]

    def test_other_programming_error_propagates_and_translates(self, capsys):
        prog_err = snowflake.connector.errors.ProgrammingError(
            msg="003001 (42501): SQL access control error:\n"
                "Insufficient privileges to operate on account 'PGTEST'. "
                "Your primary role PUBLIC must have CREATE CATALOG INTEGRATION "
                "granted on ACCOUNT PGTEST.",
        )
        conn, _ = self._fake_sf_connection(raise_on_execute=prog_err)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-integration",
                "--name", "pg_ci",
                "--postgres-instance", "LH_TEST1",
                "--database", "postgres",
                "--json",
            ])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        # The error surfaces to the main() translator, which produces a
        # friendly_error for known patterns.
        assert "friendly_error" in payload
        assert "--use-role" in payload["friendly_error"]

    @pytest.mark.parametrize("field,bad", [
        ("--name", "drop; DROP TABLE users"),
        ("--postgres-instance", "has'quote"),
        ("--database", "has space"),
    ])
    def test_rejects_identifier_injection(self, capsys, field, bad):
        conn, _ = self._fake_sf_connection()
        argv = [
            "create-integration",
            "--name", "pg_ci",
            "--postgres-instance", "LH_TEST1",
            "--database", "postgres",
            "--json",
        ]
        # Substitute the bad value for the targeted flag.
        idx = argv.index(field)
        argv[idx + 1] = bad

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(argv)

        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "prohibited" in payload["error"].lower() or \
            "not a valid unquoted identifier" in payload["error"]

    def test_use_role_applies_session_override_before_create(self, capsys):
        conn, cursor = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main([
                "create-integration",
                "--name", "pg_ci",
                "--postgres-instance", "LH_TEST1",
                "--database", "postgres",
                "--use-role", "ACCOUNTADMIN",
                "--json",
            ])

        assert cursor.executed_sql[0] == "USE ROLE ACCOUNTADMIN"
        assert "CREATE CATALOG INTEGRATION" in cursor.executed_sql[1]


class TestDescribeIntegration:
    """
    describe-integration returns the 4-column property set from
    DESCRIBE CATALOG INTEGRATION: (property, property_type, property_value,
    property_default).
    """

    def test_parses_describe_rows_into_properties_dict(self, capsys):
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.fetchall.return_value = [
            ("ENABLED", "Boolean", "true", "true"),
            ("CATALOG_SOURCE", "String", "SNOWFLAKE_POSTGRES", ""),
            ("REFRESH_INTERVAL_SECONDS", "Integer", "30", "30"),
            ("REST_CONFIG", "EnumMap",
             "{CATALOG_NAME=postgres, ACCESS_DELEGATION_MODE=VENDED_CREDENTIALS, POSTGRES_INSTANCE=LH_TEST1}", ""),
        ]
        type(cursor).description = property(lambda self: [
            ("property", None), ("property_type", None),
            ("property_value", None), ("property_default", None),
        ])

        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["describe-integration", "--name", "pg_ci", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["name"] == "pg_ci"
        # 4 DESCRIBE columns expected.
        assert payload["columns"] == [
            "property", "property_type", "property_value", "property_default",
        ]
        # Both raw rows and parsed properties dict are available.
        assert len(payload["rows"]) == 4
        assert payload["properties"]["ENABLED"]["value"] == "true"
        assert payload["properties"]["REFRESH_INTERVAL_SECONDS"]["value"] == "30"
        assert "POSTGRES_INSTANCE=LH_TEST1" in payload["properties"]["REST_CONFIG"]["value"]

    def test_rejects_invalid_identifier(self, capsys):
        conn = MagicMock()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["describe-integration", "--name", "bad; DROP", "--json"])

        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "prohibited" in payload["error"].lower() or "not a valid" in payload["error"]

    def test_not_found_error_is_translated(self, capsys):
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.execute.side_effect = snowflake.connector.errors.ProgrammingError(
            msg="002003 (02000): SQL compilation error:\n"
                "Integration 'MISSING_CI' does not exist or not authorized.",
        )
        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["describe-integration", "--name", "missing_ci", "--json"])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "friendly_error" in payload
        assert "MISSING_CI" in payload["friendly_error"]


class TestDropIntegration:
    """
    T024 — drop-integration is destructive. Without --confirm, dry-runs and
    returns success=False so pipelines can distinguish "not confirmed" from
    "dropped". With --confirm, DROP CATALOG INTEGRATION IF EXISTS runs.
    """

    def test_without_confirm_dry_runs_no_sql_executes(self, capsys):
        executed: list[str] = []
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.execute.side_effect = lambda sql, *a, **k: executed.append(sql)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["drop-integration", "--name", "pg_ci", "--json"])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert payload["confirmed"] is False
        assert "DROP CATALOG INTEGRATION IF EXISTS pg_ci" in payload["would_execute"]
        # Critical: no network side-effects when --confirm is missing.
        conn.cursor.assert_not_called()
        assert executed == []

    def test_with_confirm_executes_drop(self, capsys):
        executed: list[str] = []
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.execute.side_effect = lambda sql, *a, **k: executed.append(sql)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "drop-integration", "--name", "pg_ci", "--confirm", "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["confirmed"] is True
        assert executed == ["DROP CATALOG INTEGRATION IF EXISTS pg_ci"]

    def test_rejects_invalid_identifier_even_without_confirm(self, capsys):
        # Identifier validation runs before the --confirm check so we can't
        # sneak malicious SQL into a dry-run payload.
        conn = MagicMock()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["drop-integration", "--name", "bad; DROP", "--json"])

        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert "prohibited" in payload["error"].lower() or "not a valid" in payload["error"]

    def test_use_role_applies_before_drop(self, capsys):
        executed: list[str] = []
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.execute.side_effect = lambda sql, *a, **k: executed.append(sql)

        conn = MagicMock()
        conn.cursor.return_value = cursor

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main([
                "drop-integration", "--name", "pg_ci",
                "--confirm", "--use-role", "ACCOUNTADMIN", "--json",
            ])

        assert executed == [
            "USE ROLE ACCOUNTADMIN",
            "DROP CATALOG INTEGRATION IF EXISTS pg_ci",
        ]


class TestCreateIcebergTable:
    """
    create-iceberg-table. CATALOG_NAMESPACE is a per-table property
    (not integration-level). AUTO_REFRESH is opt-in. already_exists
    soft-fails with a recovery hint.
    """

    @staticmethod
    def _fake_sf_connection(raise_on_execute: Exception | None = None):
        executed: list[str] = []
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None

        def execute(sql, *args, **kwargs):
            executed.append(sql)
            if raise_on_execute is not None and "CREATE ICEBERG TABLE" in sql:
                raise raise_on_execute

        cursor.execute.side_effect = execute
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn, executed

    def test_happy_path_without_auto_refresh(self, capsys):
        conn, executed = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-iceberg-table",
                "--name", "pg_ib",
                "--catalog", "pg_ci",
                "--catalog-table-name", "discovery_probe",
                "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        sql = payload["sql"]
        assert sql == (
            "CREATE ICEBERG TABLE pg_ib "
            "CATALOG = 'pg_ci' "
            "CATALOG_TABLE_NAME = 'discovery_probe' "
            "CATALOG_NAMESPACE = 'public'"
        )
        assert payload["auto_refresh"] is False
        assert executed == [sql]

    def test_auto_refresh_appends_clause(self, capsys):
        conn, _ = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-iceberg-table",
                "--name", "pg_ib",
                "--catalog", "pg_ci",
                "--catalog-table-name", "discovery_probe",
                "--auto-refresh",
                "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["auto_refresh"] is True
        assert payload["sql"].endswith(" AUTO_REFRESH = TRUE")

    def test_custom_namespace(self, capsys):
        conn, _ = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-iceberg-table",
                "--name", "pg_ib",
                "--catalog", "pg_ci",
                "--catalog-table-name", "orders",
                "--catalog-namespace", "analytics",
                "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert "CATALOG_NAMESPACE = 'analytics'" in payload["sql"]

    def test_already_exists_soft_fails(self, capsys):
        prog_err = snowflake.connector.errors.ProgrammingError(
            msg="002002 (42710): SQL compilation error:\n"
                "Object 'PG_IB' already exists.",
        )
        conn, _ = self._fake_sf_connection(raise_on_execute=prog_err)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-iceberg-table",
                "--name", "pg_ib",
                "--catalog", "pg_ci",
                "--catalog-table-name", "discovery_probe",
                "--json",
            ])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert payload["already_exists"] is True

    def test_wrong_catalog_triggers_missing_external_volume_translation(self, capsys):
        # When --catalog points at a non-existent integration, Snowflake
        # returns the misleading "EXTERNAL_VOLUME must be defined" error.
        # The translator converts it to a "check your --catalog value" hint.
        prog_err = snowflake.connector.errors.ProgrammingError(
            msg="393923 (42601): Iceberg table PG_IB must have the table "
                "parameter EXTERNAL_VOLUME defined on the table, schema, "
                "database, or account.",
        )
        conn, _ = self._fake_sf_connection(raise_on_execute=prog_err)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-iceberg-table",
                "--name", "pg_ib",
                "--catalog", "typo_ci",
                "--catalog-table-name", "discovery_probe",
                "--json",
            ])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert "friendly_error" in payload
        assert "catalog" in payload["friendly_error"].lower()
        assert "describe-integration" in payload["friendly_error"]

    @pytest.mark.parametrize("field,bad", [
        ("--name", "bad; DROP"),
        ("--catalog", "has space"),
        ("--catalog-table-name", "has'quote"),
        ("--catalog-namespace", "has.dot"),
    ])
    def test_rejects_identifier_injection(self, capsys, field, bad):
        conn, _ = self._fake_sf_connection()
        argv = [
            "create-iceberg-table",
            "--name", "pg_ib",
            "--catalog", "pg_ci",
            "--catalog-table-name", "discovery_probe",
            "--json",
        ]
        if field in argv:
            idx = argv.index(field)
            argv[idx + 1] = bad
        else:
            argv.extend([field, bad])

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(argv)

        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False


class TestCreateCld:
    """
    create-cld must always emit ALLOWED_WRITE_OPERATIONS = NONE — hard
    server-side constraint for SNOWFLAKE_POSTGRES CLDs (the only accepted
    value). Identifiers validated, already_exists soft-fails, translator catches
    cld_allowed_write_* variants if server-side rules ever change.
    """

    @staticmethod
    def _fake_sf_connection(raise_on_execute: Exception | None = None):
        executed: list[str] = []
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None

        def execute(sql, *args, **kwargs):
            executed.append(sql)
            if raise_on_execute is not None and "CREATE DATABASE" in sql:
                raise raise_on_execute

        cursor.execute.side_effect = execute
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn, executed

    def test_happy_path_always_includes_allowed_write_none(self, capsys):
        conn, executed = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-cld",
                "--name", "pg_cld",
                "--catalog", "pg_ci",
                "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        sql = payload["sql"]
        assert sql == (
            "CREATE DATABASE pg_cld "
            "LINKED_CATALOG = (CATALOG = 'pg_ci', ALLOWED_WRITE_OPERATIONS = NONE)"
        )
        assert payload["allowed_write_operations"] == "NONE"
        # User never gets a knob to pick a different write mode — server
        # rejects anything but NONE, and the subcommand intentionally
        # doesn't expose a flag to fight that.
        assert executed == [sql]

    def test_propagation_note_present(self, capsys):
        conn, _ = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main(["create-cld", "--name", "pg_cld", "--catalog", "pg_ci", "--json"])

        payload = json.loads(capsys.readouterr().out)
        note = payload["propagation_note"]
        assert "30" in note  # seconds figure
        assert "cld-status" in note

    def test_already_exists_soft_fail(self, capsys):
        prog_err = snowflake.connector.errors.ProgrammingError(
            msg="002002 (42710): SQL compilation error:\n"
                "Object 'PG_CLD' already exists.",
        )
        conn, _ = self._fake_sf_connection(raise_on_execute=prog_err)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-cld", "--name", "pg_cld", "--catalog", "pg_ci", "--json",
            ])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False
        assert payload["already_exists"] is True
        assert "cld-status" in payload["hint"]

    def test_missing_allowed_writes_server_error_translates(self, capsys):
        # Sanity: if the server-side ALLOWED_WRITE_OPERATIONS rule ever
        # fires against our DDL, the translator produces a helpful message
        # even though create-cld always emits = NONE (defense in depth).
        prog_err = snowflake.connector.errors.ProgrammingError(
            msg="094124 (22023): SQL Compilation Error: SNOWFLAKE_POSTGRES "
                "catalog-linked databases must explicitly specify "
                "ALLOWED_WRITE_OPERATIONS. ALLOWED_WRITE_OPERATIONS must be "
                "set to NONE for SNOWFLAKE_POSTGRES catalogs.",
        )
        conn, _ = self._fake_sf_connection(raise_on_execute=prog_err)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "create-cld", "--name", "pg_cld", "--catalog", "pg_ci", "--json",
            ])

        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert "friendly_error" in payload
        assert "ALLOWED_WRITE_OPERATIONS = NONE" in payload["friendly_error"]

    def test_use_role_applies_before_create(self, capsys):
        conn, executed = self._fake_sf_connection()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main([
                "create-cld", "--name", "pg_cld", "--catalog", "pg_ci",
                "--use-role", "ACCOUNTADMIN", "--json",
            ])

        assert executed[0] == "USE ROLE ACCOUNTADMIN"
        assert "CREATE DATABASE pg_cld" in executed[1]

    @pytest.mark.parametrize("field,bad", [
        ("--name", "bad; DROP"),
        ("--catalog", "has space"),
    ])
    def test_rejects_identifier_injection(self, capsys, field, bad):
        conn, _ = self._fake_sf_connection()
        argv = ["create-cld", "--name", "pg_cld", "--catalog", "pg_ci", "--json"]
        idx = argv.index(field)
        argv[idx + 1] = bad
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(argv)
        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is False


class TestCldStatus:
    """
    T031 — cld-status combines SYSTEM$CATALOG_LINK_STATUS + SHOW TABLES
    IN DATABASE. Parses the status JSON, filters SHOW TABLES to iceberg
    tables only, surfaces `healthy` so agents don't have to parse
    executionState themselves.
    """

    @staticmethod
    def _fake_conn_returning(status_json: str, show_rows: list, show_description: list):
        state = {"phase": "status"}
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None

        def on_execute(sql, *args, **kwargs):
            if "SYSTEM$CATALOG_LINK_STATUS" in sql:
                state["phase"] = "status"
            elif "SHOW TABLES" in sql:
                state["phase"] = "tables"

        def on_fetchone():
            return (status_json,) if state["phase"] == "status" else None

        def on_fetchall():
            return show_rows if state["phase"] == "tables" else []

        cursor.execute.side_effect = on_execute
        cursor.fetchone.side_effect = on_fetchone
        cursor.fetchall.side_effect = on_fetchall
        type(cursor).description = property(
            lambda self: show_description if state["phase"] == "tables" else None
        )
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_parses_running_status_and_iceberg_tables(self, capsys):
        status_json = json.dumps({
            "failureDetails": [],
            "executionState": "RUNNING",
            "lastLinkAttemptStartTime": "2026-04-23 10:00:00",
        })
        description = [
            ("created_on", None), ("name", None), ("schema_name", None),
            ("kind", None), ("is_iceberg", None), ("rows", None),
        ]
        rows = [
            ("2026-04-23", "discovery_probe", "public", "TABLE", "Y", 3),
            ("2026-04-23", "non_iceberg_view", "public", "VIEW", "N", 0),
        ]
        conn = self._fake_conn_returning(status_json, rows, description)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["cld-status", "--name", "pg_cld", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["execution_state"] == "RUNNING"
        assert payload["healthy"] is True
        assert payload["failure_details"] == []
        assert payload["iceberg_table_count"] == 1
        assert payload["iceberg_tables"][0]["name"] == "discovery_probe"

    def test_non_running_state_marks_unhealthy(self, capsys):
        status_json = json.dumps({
            "failureDetails": [{"error": "sample failure"}],
            "executionState": "FAILED",
            "lastLinkAttemptStartTime": "2026-04-23 10:00:00",
        })
        conn = self._fake_conn_returning(status_json, [], [])

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["cld-status", "--name", "pg_cld", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["execution_state"] == "FAILED"
        assert payload["healthy"] is False
        assert payload["failure_details"] == [{"error": "sample failure"}]

    def test_malformed_status_json_does_not_crash(self, capsys):
        conn = self._fake_conn_returning("not-json-at-all", [], [])
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["cld-status", "--name", "pg_cld", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["execution_state"] is None
        assert payload["healthy"] is False
        assert payload["raw_status"] == "not-json-at-all"

    def test_rejects_identifier_injection(self, capsys):
        conn = MagicMock()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["cld-status", "--name", "bad; DROP", "--json"])
        assert rc == 2


class TestExtractIcebergTablesFromShow:
    """
    _extract_iceberg_tables_from_show is column-index-defensive — SHOW
    TABLES column layout changes across Snowflake versions. Tests pin
    the contract rather than a specific layout.
    """

    def test_finds_iceberg_via_is_iceberg_column(self):
        cols = ["created_on", "name", "schema_name", "is_iceberg"]
        rows = [
            ("2026-04-23", "t1", "public", "Y"),
            ("2026-04-23", "t2", "public", "N"),
        ]
        out = _extract_iceberg_tables_from_show(rows, cols)
        assert [t["name"] for t in out] == ["t1"]

    def test_finds_iceberg_via_kind_fallback(self):
        # Future Snowflake version might drop is_iceberg and use a kind
        # like "ICEBERG TABLE" instead. The helper falls back to kind.
        cols = ["name", "schema_name", "kind"]
        rows = [
            ("t1", "public", "ICEBERG TABLE"),
            ("t2", "public", "BASE TABLE"),
        ]
        out = _extract_iceberg_tables_from_show(rows, cols)
        assert [t["name"] for t in out] == ["t1"]

    def test_empty_inputs(self):
        assert _extract_iceberg_tables_from_show([], []) == []
        assert _extract_iceberg_tables_from_show([("t", "s", "Y")], []) == []


class TestRefreshCommands:
    """
    T040 — `refresh`, `set-auto-refresh`, `set-refresh-interval` are thin
    ALTER wrappers. Tests confirm SQL shape + identifier validation +
    client-side interval range check integration.
    """

    @staticmethod
    def _fake_conn():
        executed: list[str] = []
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None
        cursor.execute.side_effect = lambda sql, *a, **k: executed.append(sql)
        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn, executed

    def test_refresh_emits_alter_refresh(self, capsys):
        conn, executed = self._fake_conn()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["refresh", "--name", "pg_ib", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["success"] is True
        assert payload["sql"] == "ALTER ICEBERG TABLE pg_ib REFRESH"
        assert executed == [payload["sql"]]

    @pytest.mark.parametrize("enabled_str,expected_sql_suffix", [
        ("true", "SET AUTO_REFRESH = TRUE"),
        ("false", "SET AUTO_REFRESH = FALSE"),
    ])
    def test_set_auto_refresh_toggles_both_directions(
        self, capsys, enabled_str, expected_sql_suffix,
    ):
        conn, executed = self._fake_conn()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "set-auto-refresh", "--name", "pg_ib",
                "--enabled", enabled_str, "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["enabled"] is (enabled_str == "true")
        assert expected_sql_suffix in payload["sql"]
        assert executed == [payload["sql"]]

    def test_set_refresh_interval_happy_path(self, capsys):
        conn, executed = self._fake_conn()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "set-refresh-interval",
                "--integration", "pg_ci",
                "--seconds", "60",
                "--json",
            ])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["seconds"] == 60
        assert payload["sql"] == (
            "ALTER CATALOG INTEGRATION pg_ci SET REFRESH_INTERVAL_SECONDS = 60"
        )

    @pytest.mark.parametrize("bad_seconds", ["10", "86401", "-1"])
    def test_set_refresh_interval_rejects_out_of_range_before_sql(
        self, capsys, bad_seconds,
    ):
        conn, executed = self._fake_conn()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main([
                "set-refresh-interval",
                "--integration", "pg_ci",
                "--seconds", bad_seconds,
                "--json",
            ])

        assert rc == 2
        # Critical: client-side validation must run BEFORE any SQL lands
        # on the server — protects against a wasted round-trip and opaque
        # error surfacing to the agent.
        assert executed == []

    def test_use_role_applies_before_all_three(self, capsys):
        conn, executed = self._fake_conn()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main([
                "refresh", "--name", "pg_ib",
                "--use-role", "SYSADMIN", "--json",
            ])
        assert executed[0] == "USE ROLE SYSADMIN"

        executed.clear()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main([
                "set-auto-refresh", "--name", "pg_ib", "--enabled", "true",
                "--use-role", "SYSADMIN", "--json",
            ])
        assert executed[0] == "USE ROLE SYSADMIN"

        executed.clear()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            main([
                "set-refresh-interval", "--integration", "pg_ci", "--seconds", "60",
                "--use-role", "ACCOUNTADMIN", "--json",
            ])
        assert executed[0] == "USE ROLE ACCOUNTADMIN"

    @pytest.mark.parametrize("cmd,flag,bad", [
        ("refresh", "--name", "bad; DROP"),
        ("set-auto-refresh", "--name", "has'quote"),
        ("set-refresh-interval", "--integration", "has space"),
    ])
    def test_rejects_identifier_injection(self, capsys, cmd, flag, bad):
        argv: list[str] = [cmd, flag, bad, "--json"]
        if cmd == "set-auto-refresh":
            argv += ["--enabled", "true"]
        if cmd == "set-refresh-interval":
            argv += ["--seconds", "60"]

        conn, _ = self._fake_conn()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(argv)

        assert rc == 2


class TestStatusCommand:
    """
    T041 — status reads SYSTEM$AUTO_REFRESH_STATUS + LIMIT 10 of
    ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY and returns a structured payload.
    """

    @staticmethod
    def _fake_conn(status_json: str, history_rows: list, history_description: list):
        state = {"phase": "status"}
        cursor = MagicMock()
        cursor.__enter__ = lambda self: self
        cursor.__exit__ = lambda self, *a: None

        def on_execute(sql, *args, **kwargs):
            if "SYSTEM$AUTO_REFRESH_STATUS" in sql:
                state["phase"] = "status"
            elif "ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY" in sql:
                state["phase"] = "history"

        def on_fetchone():
            return (status_json,) if state["phase"] == "status" else None

        def on_fetchall():
            return history_rows if state["phase"] == "history" else []

        cursor.execute.side_effect = on_execute
        cursor.fetchone.side_effect = on_fetchone
        cursor.fetchall.side_effect = on_fetchall
        type(cursor).description = property(
            lambda self: history_description if state["phase"] == "history" else None
        )

        conn = MagicMock()
        conn.cursor.return_value = cursor
        return conn

    def test_running_status_with_history(self, capsys):
        status_json = json.dumps({
            "executionState": "RUNNING",
            "failureDetails": [],
            "lastRefreshedOn": "2026-04-24 09:00:00",
        })
        description = [
            ("REFRESHED_ON", None), ("STATUS", None), ("DURATION_MS", None),
        ]
        rows = [
            ("2026-04-24 09:00:00", "SUCCEEDED", 145),
            ("2026-04-24 08:59:30", "SUCCEEDED", 160),
        ]
        conn = self._fake_conn(status_json, rows, description)

        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["status", "--name", "pg_ib", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["execution_state"] == "RUNNING"
        assert payload["healthy"] is True
        assert payload["refresh_history_count"] == 2
        assert payload["refresh_history"][0]["status"] == "SUCCEEDED"

    def test_malformed_status_does_not_crash(self, capsys):
        conn = self._fake_conn("not-valid-json", [], [])
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["status", "--name", "pg_ib", "--json"])

        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["execution_state"] is None
        assert payload["healthy"] is False
        assert payload["raw_status"] == "not-valid-json"

    def test_rejects_identifier_injection(self, capsys):
        conn = MagicMock()
        with patch("pg_lake_catalog.get_snowflake_connection", return_value=conn):
            rc = main(["status", "--name", "bad; DROP", "--json"])
        assert rc == 2


class TestAutoRefreshCostWarning:
    """
    T042 — `build_auto_refresh_cost_warning` is the library-level
    helper the READ-FROM-SNOWFLAKE workflow calls before confirming a
    bulk `--auto-refresh` pass. Threshold is a module constant so eval
    T064 can tune it without editing prose.
    """

    def test_threshold_constants_are_the_documented_defaults(self):
        assert AUTO_REFRESH_COST_WARNING_THRESHOLD == 10
        assert AUTO_REFRESH_COST_SUGGESTED_INTERVAL == 300

    @pytest.mark.parametrize("count", [0, 1, 5, 9])
    def test_below_threshold_does_not_warn(self, count):
        out = build_auto_refresh_cost_warning(count)
        assert out["warn"] is False
        assert out["message"] == ""
        assert out["recovery_command"] == ""
        assert out["table_count"] == count

    @pytest.mark.parametrize("count", [10, 11, 25, 100])
    def test_at_or_above_threshold_emits_actionable_message(self, count):
        out = build_auto_refresh_cost_warning(count)
        assert out["warn"] is True
        assert str(count) in out["message"]
        # The message must reference the interval tuning lever, not just
        # say "this is expensive" and leave the agent stuck.
        assert "set-refresh-interval" in out["recovery_command"]
        assert f"--seconds {AUTO_REFRESH_COST_SUGGESTED_INTERVAL}" in out["recovery_command"]
        assert "integration-level" in out["message"]

    def test_threshold_tunable_for_eval(self):
        # Eval T064 validates the threshold is reasonable. It must be
        # parameter-tunable via call site rather than hardcoded in prose.
        out = build_auto_refresh_cost_warning(5, threshold=3)
        assert out["warn"] is True
        assert out["threshold"] == 3

    def test_interval_context_propagates(self):
        # A workflow that already raised the interval shouldn't get a
        # warning recommending the same lever. The message still includes
        # the current interval for auditing.
        out = build_auto_refresh_cost_warning(50, interval_seconds=600)
        assert out["interval_seconds"] == 600
        assert "600" in out["message"]


class TestRefreshIntervalValidation:
    """
    REFRESH_INTERVAL_SECONDS bounds [30, 86400] inclusive. Validate
    client-side so the opaque server error never reaches the user.
    """

    def test_bounds_constants(self):
        assert REFRESH_INTERVAL_MIN == 30
        assert REFRESH_INTERVAL_MAX == 86400

    @pytest.mark.parametrize("good", [30, 60, 300, 3600, 43200, 86400])
    def test_accepts_valid_values(self, good):
        assert validate_refresh_interval(good) == good

    @pytest.mark.parametrize("bad", [-1, 0, 1, 29, 86401, 99999999])
    def test_rejects_out_of_range(self, bad):
        with pytest.raises(ValueError, match="out of range"):
            validate_refresh_interval(bad)

    @pytest.mark.parametrize("not_int", ["30", 30.0, None, True])
    def test_rejects_non_int(self, not_int):
        if not_int is True:
            # bool is subclass of int in Python — accept since True == 1 is
            # rejected on range grounds anyway. Documented quirk.
            pytest.skip("bool is a subclass of int; range check handles it")
        with pytest.raises(ValueError):
            validate_refresh_interval(not_int)  # type: ignore[arg-type]

    def test_set_refresh_interval_rejects_out_of_range_end_to_end(self, capsys):
        # End-to-end proof that validate_refresh_interval runs at argparse
        # time, BEFORE any Snowflake connection is attempted. The valid-
        # value path is covered by TestRefreshCommands::test_set_refresh_interval_happy_path
        # (mocked connection); this test intentionally uses no mock so a
        # regression that swaps validation order would trigger a connection
        # error instead of a clean ValueError.
        rc = main([
            "set-refresh-interval",
            "--integration", "my_ci",
            "--seconds", "10",  # below the 30s floor
            "--json",
        ])
        assert rc == 2
        payload = capsys.readouterr().out
        assert "out of range" in payload
        assert "30" in payload
