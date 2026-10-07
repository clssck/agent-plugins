"""
Tests for cutover_tools.py.

Covers:
- collect_sequences / generate_sequence_sync_sql
- collect_triggers / generate_trigger_disable_sql / generate_trigger_enable_sql
- collect_problematic_triggers (ALWAYS triggers)
- cmd_sequences / cmd_triggers / cmd_all orchestration
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cutover_tools import (
    collect_sequences,
    collect_problematic_triggers,
    collect_triggers,
    generate_sequence_sync_sql,
    generate_trigger_disable_sql,
    generate_trigger_enable_sql,
    cmd_sequences,
    cmd_triggers,
    cmd_all,
)


# --------------------------------------------------------------------------
# Helpers: wire mock_cursor / mock_conn to simulate query()
# --------------------------------------------------------------------------


def _configure_cursor_sequence(cursor, result_sequences):
    """Make cursor.execute/fetchall/description return a series of results per query.

    Each call to cursor.execute() consumes one entry from result_sequences.
    Each entry is either (columns, rows) or None (no rows / no description).
    """
    states = iter(result_sequences)

    def _on_execute(sql, params=None):
        try:
            payload = next(states)
        except StopIteration:
            cursor.description = None
            cursor.fetchall.return_value = []
            return
        if payload is None:
            cursor.description = None
            cursor.fetchall.return_value = []
        else:
            cols, rows = payload
            cursor.description = [(c,) for c in cols]
            cursor.fetchall.return_value = rows

    cursor.execute.side_effect = _on_execute


# --------------------------------------------------------------------------
# Basic SQL-text generators
# --------------------------------------------------------------------------


class TestGenerateSequenceSyncSQL:
    """Tests for generate_sequence_sync_sql()."""

    def test_empty_sequences_still_produces_header(self):
        sql = generate_sequence_sync_sql([])
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql
        assert "-- Sequence Sync Script" in sql

    def test_single_sequence_with_last_value(self):
        seqs = [{"schema": "public", "name": "users_id_seq", "last_value": 100, "owned_by": "users.id"}]
        sql = generate_sequence_sync_sql(seqs, buffer=1000)
        # Always-quoted output (matches psycopg2.sql.Identifier convention)
        # protects mixed-case / reserved-word identifiers from being silently
        # case-folded.
        assert "SELECT setval('\"public\".\"users_id_seq\"', 1100);" in sql
        assert "-- owned by: users.id" in sql

    def test_null_last_value_uses_1_plus_buffer(self):
        """When last_value is None (never used), setval falls back to 1 + buffer."""
        seqs = [{"schema": "public", "name": "new_seq", "last_value": None, "owned_by": None}]
        sql = generate_sequence_sync_sql(seqs, buffer=500)
        assert "SELECT setval('\"public\".\"new_seq\"', 501);" in sql

    def test_custom_buffer(self):
        seqs = [{"schema": "s", "name": "q", "last_value": 42, "owned_by": None}]
        sql = generate_sequence_sync_sql(seqs, buffer=7)
        assert "setval('\"s\".\"q\"', 49)" in sql

    def test_multiple_sequences_ordered(self):
        seqs = [
            {"schema": "a", "name": "x", "last_value": 1, "owned_by": None},
            {"schema": "b", "name": "y", "last_value": 2, "owned_by": "b.tbl.id"},
        ]
        sql = generate_sequence_sync_sql(seqs, buffer=10)
        assert "setval('\"a\".\"x\"', 11)" in sql
        assert "setval('\"b\".\"y\"', 12)" in sql
        assert "owned by: b.tbl.id" in sql

    def test_quotes_mixed_case_and_reserved_words(self):
        """Mixed-case and reserved-word identifiers must be quoted in the SQL
        so PG doesn't fold them to lowercase or reject them outright."""
        seqs = [
            {"schema": "Public", "name": "Order_id_seq", "last_value": 1, "owned_by": None},
            # `"order"` is a reserved word; quoted form is the only valid spelling
            {"schema": "public", "name": "order", "last_value": 2, "owned_by": None},
            # Embedded `"` characters are doubled
            {"schema": "weird", "name": 'has"quote', "last_value": 3, "owned_by": None},
        ]
        sql = generate_sequence_sync_sql(seqs, buffer=0)
        assert '"Public"."Order_id_seq"' in sql
        assert '"public"."order"' in sql
        assert '"weird"."has""quote"' in sql


class TestGenerateTriggerDisableSQL:
    """Tests for generate_trigger_disable_sql()."""

    def test_empty_triggers_has_begin_commit(self):
        sql = generate_trigger_disable_sql([])
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql
        assert "DISABLE TRIGGER ALL" not in sql

    def test_disables_per_unique_table(self):
        trigs = [
            {"schema": "public", "table_name": "t1", "trigger_name": "trg1"},
            {"schema": "public", "table_name": "t1", "trigger_name": "trg2"},
            {"schema": "public", "table_name": "t2", "trigger_name": "trg3"},
        ]
        sql = generate_trigger_disable_sql(trigs)
        # Dedupes by schema.table
        assert sql.count("DISABLE TRIGGER ALL") == 2
        assert 'ALTER TABLE "public"."t1" DISABLE TRIGGER ALL;' in sql
        assert 'ALTER TABLE "public"."t2" DISABLE TRIGGER ALL;' in sql

    def test_disable_tables_sorted(self):
        trigs = [
            {"schema": "z", "table_name": "zz", "trigger_name": "trg"},
            {"schema": "a", "table_name": "aa", "trigger_name": "trg"},
        ]
        sql = generate_trigger_disable_sql(trigs)
        a_idx = sql.index('"a"."aa"')
        z_idx = sql.index('"z"."zz"')
        assert a_idx < z_idx


class TestGenerateTriggerEnableSQL:
    """Tests for generate_trigger_enable_sql()."""

    def test_empty_triggers(self):
        sql = generate_trigger_enable_sql([])
        assert "BEGIN;" in sql
        assert "COMMIT;" in sql

    def test_enables_per_table_dedup(self):
        trigs = [
            {"schema": "public", "table_name": "t", "trigger_name": "a"},
            {"schema": "public", "table_name": "t", "trigger_name": "b"},
        ]
        sql = generate_trigger_enable_sql(trigs)
        assert sql.count("ENABLE TRIGGER ALL") == 1
        assert 'ALTER TABLE "public"."t" ENABLE TRIGGER ALL;' in sql


# --------------------------------------------------------------------------
# DB-interacting collect_* helpers
# --------------------------------------------------------------------------


class TestCollectSequences:
    """Tests for collect_sequences() — uses query() -> cursor dance."""

    def test_returns_list_of_dicts(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "name", "last_value", "owned_by"],
                    [("public", "s1", 10, "users.id"), ("other", "s2", None, None)],
                )
            ],
        )
        result = collect_sequences(mock_conn)
        assert len(result) == 2
        assert result[0]["schema"] == "public"
        assert result[0]["name"] == "s1"
        assert result[0]["last_value"] == 10
        assert result[1]["last_value"] is None

    def test_query_text_mentions_pg_sequence_last_value(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["schema", "name", "last_value", "owned_by"], [])])
        collect_sequences(mock_conn)
        sql = mock_cursor.execute.call_args.args[0]
        assert "pg_sequence_last_value" in sql
        assert "pg_catalog" in sql  # excludes pg_catalog

    def test_empty_result(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["schema", "name", "last_value", "owned_by"], [])])
        result = collect_sequences(mock_conn)
        assert result == []

    def test_schema_filter_adds_where_clause_and_params(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["schema", "name", "last_value", "owned_by"], [])])
        collect_sequences(mock_conn, schemas=["public", "app"])
        sql, params = mock_cursor.execute.call_args.args
        assert "n.nspname IN (%s, %s)" in sql
        assert params == ("public", "app")


class TestCollectTriggers:
    """Tests for collect_triggers()."""

    def test_returns_trigger_rows(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "table_name", "trigger_name", "timing", "events", "current_status", "function_name"],
                    [("public", "orders", "audit", "AFTER", "INSERT/UPDATE", "origin", "audit_fn")],
                )
            ],
        )
        result = collect_triggers(mock_conn)
        assert len(result) == 1
        assert result[0]["trigger_name"] == "audit"
        assert result[0]["current_status"] == "origin"

    def test_excludes_internal_triggers(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["schema"], [])])
        collect_triggers(mock_conn)
        sql = mock_cursor.execute.call_args.args[0]
        assert "NOT t.tgisinternal" in sql


class TestCollectProblematicTriggers:
    """Tests for collect_problematic_triggers() — the ALWAYS trigger check."""

    def test_filters_by_tgenabled_a(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(mock_cursor, [(["schema", "table_name", "trigger_name"], [])])
        collect_problematic_triggers(mock_conn)
        sql = mock_cursor.execute.call_args.args[0]
        assert "t.tgenabled = 'A'" in sql

    def test_returns_rows(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "table_name", "trigger_name"],
                    [("public", "t", "always_trg")],
                )
            ],
        )
        rows = collect_problematic_triggers(mock_conn)
        assert len(rows) == 1
        assert rows[0]["trigger_name"] == "always_trg"


# --------------------------------------------------------------------------
# cmd_* orchestration
# --------------------------------------------------------------------------


def _make_args(**overrides):
    """Build an argparse-like namespace with safe defaults."""
    defaults = dict(
        host="src.example.com",
        port=5432,
        dbname="mydb",
        user="admin",
        password="",
        sslmode=None,
        schemas=None,
        target_host="tgt.example.com",
        target_port=5432,
        target_dbname="postgres",
        target_user="admin",
        target_password="",
        target_sslmode=None,
        output=None,
        json=None,
        buffer=1000,
        execute=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestCmdSequences:
    """Integration-style tests for cmd_sequences()."""

    def test_prints_sql_when_no_output(self, mock_conn, mock_cursor, capsys):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "name", "last_value", "owned_by"],
                    [("public", "s1", 100, None)],
                )
            ],
        )
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_sequences(_make_args())
        out = capsys.readouterr().out
        assert "setval('\"public\".\"s1\"', 1100)" in out
        assert "Found 1 sequences" in out

    def test_writes_output_file_when_output_set(self, mock_conn, mock_cursor, tmp_path):
        _configure_cursor_sequence(
            mock_cursor,
            [(["schema", "name", "last_value", "owned_by"], [("public", "s1", 10, None)])],
        )
        outfile = tmp_path / "seq.sql"
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_sequences(_make_args(output=str(outfile)))
        assert "setval('\"public\".\"s1\"', 1010)" in outfile.read_text()

    def test_writes_json_when_json_arg(self, mock_conn, mock_cursor, tmp_path, capsys):
        _configure_cursor_sequence(
            mock_cursor,
            [(["schema", "name", "last_value", "owned_by"], [("public", "s1", 10, None)])],
        )
        jsonfile = tmp_path / "seq.json"
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_sequences(_make_args(json=str(jsonfile)))
        data = json.loads(jsonfile.read_text())
        assert data[0]["name"] == "s1"

    def test_schema_filter_reaches_collection_query(self, mock_conn, mock_cursor):
        _configure_cursor_sequence(
            mock_cursor,
            [(["schema", "name", "last_value", "owned_by"], [("public", "s1", 10, None)])],
        )
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_sequences(_make_args(schemas="public, app"))
        sql, params = mock_cursor.execute.call_args.args
        assert "n.nspname IN (%s, %s)" in sql
        assert params == ("public", "app")

    def test_execute_calls_setval_on_target(self, tmp_path, capsys):
        # Two cursors: one for source (collection), one for target (setval).
        src_cursor = MagicMock()
        src_cursor.__enter__ = MagicMock(return_value=src_cursor)
        src_cursor.__exit__ = MagicMock(return_value=False)
        _configure_cursor_sequence(
            src_cursor,
            [(["schema", "name", "last_value", "owned_by"], [("public", "s1", 5, None)])],
        )
        src_conn = MagicMock()
        src_conn.cursor.return_value = src_cursor

        tgt_cursor = MagicMock()
        tgt_cursor.__enter__ = MagicMock(return_value=tgt_cursor)
        tgt_cursor.__exit__ = MagicMock(return_value=False)
        tgt_cursor.description = None
        tgt_cursor.fetchall.return_value = []
        tgt_conn = MagicMock()
        tgt_conn.cursor.return_value = tgt_cursor

        with patch("cutover_tools.connect_source", return_value=src_conn), \
             patch("cutover_tools.connect_target", return_value=tgt_conn):
            cmd_sequences(_make_args(execute=True))

        # The setval is now parameterized: cursor.execute is called with the
        # SQL template `SELECT setval(%s::regclass, %s)` and the params
        # `('"public"."s1"', 1005)`. Inspect both.
        executed = list(tgt_cursor.execute.call_args_list)
        assert any(
            "setval(%s::regclass, %s)" in c.args[0]
            and c.args[1] == ('"public"."s1"', 1005)
            for c in executed
        )
        tgt_conn.commit.assert_called_once()
        tgt_conn.close.assert_called_once()


class TestCmdTriggers:
    """Integration-style tests for cmd_triggers()."""

    def test_prints_disable_and_enable_sql(self, mock_conn, mock_cursor, capsys):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "table_name", "trigger_name", "timing", "events", "current_status", "function_name"],
                    [("public", "t1", "trg", "AFTER", "INSERT", "origin", "fn")],
                ),
                (["schema", "table_name", "trigger_name"], []),
            ],
        )
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_triggers(_make_args())
        out = capsys.readouterr().out
        assert "DISABLE TRIGGER ALL" in out
        assert "ENABLE TRIGGER ALL" in out

    def test_warns_about_always_triggers(self, mock_conn, mock_cursor, capsys):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "table_name", "trigger_name", "timing", "events", "current_status", "function_name"],
                    [("public", "t1", "trg", "AFTER", "INSERT", "always", "fn")],
                ),
                (["schema", "table_name", "trigger_name"], [("public", "t1", "trg")]),
            ],
        )
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_triggers(_make_args())
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "ALWAYS triggers" in out
        assert "public.t1.trg" in out

    def test_writes_output_file_with_two_parts(self, mock_conn, mock_cursor, tmp_path):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "table_name", "trigger_name", "timing", "events", "current_status", "function_name"],
                    [("public", "t1", "trg", "AFTER", "INSERT", "origin", "fn")],
                ),
                (["schema", "table_name", "trigger_name"], []),
            ],
        )
        outfile = tmp_path / "trig.sql"
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_triggers(_make_args(output=str(outfile)))
        content = outfile.read_text()
        assert "PART 1: DISABLE TRIGGERS" in content
        assert "PART 2: ENABLE TRIGGERS" in content


class TestCmdAll:
    """Integration-style tests for cmd_all()."""

    def test_generates_full_runbook(self, mock_conn, mock_cursor, capsys):
        _configure_cursor_sequence(
            mock_cursor,
            [
                # sequences
                (["schema", "name", "last_value", "owned_by"], [("public", "s", 10, None)]),
                # triggers
                (
                    ["schema", "table_name", "trigger_name", "timing", "events", "current_status", "function_name"],
                    [("public", "t", "trg", "AFTER", "INSERT", "origin", "fn")],
                ),
                # always_triggers
                (["schema", "table_name", "trigger_name"], []),
            ],
        )
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_all(_make_args())
        out = capsys.readouterr().out
        assert "CUTOVER RUNBOOK" in out
        assert "STEP 1: DISABLE TRIGGERS" in out
        assert "STEP 2: SYNC SEQUENCES" in out
        assert "STEP 3: RE-ENABLE TRIGGERS" in out
        assert "setval('\"public\".\"s\"', 1010)" in out

    def test_skips_trigger_steps_when_no_triggers(self, mock_conn, mock_cursor, capsys):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (["schema", "name", "last_value", "owned_by"], [("public", "s", 10, None)]),
                (
                    ["schema", "table_name", "trigger_name", "timing", "events", "current_status", "function_name"],
                    [],
                ),
                (["schema", "table_name", "trigger_name"], []),
            ],
        )
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_all(_make_args())
        out = capsys.readouterr().out
        assert "STEP 2: SYNC SEQUENCES" in out
        # No trigger-related steps
        assert "STEP 1: DISABLE TRIGGERS" not in out
        assert "STEP 3: RE-ENABLE TRIGGERS" not in out

    def test_summary_counts(self, mock_conn, mock_cursor, capsys):
        _configure_cursor_sequence(
            mock_cursor,
            [
                (
                    ["schema", "name", "last_value", "owned_by"],
                    [("public", "s1", 10, None), ("public", "s2", 20, None)],
                ),
                (
                    ["schema", "table_name", "trigger_name", "timing", "events", "current_status", "function_name"],
                    [("public", "t", "trg", "AFTER", "INSERT", "origin", "fn")],
                ),
                (
                    ["schema", "table_name", "trigger_name"],
                    [("public", "t", "trg")],
                ),
            ],
        )
        with patch("cutover_tools.connect_source", return_value=mock_conn):
            cmd_all(_make_args())
        out = capsys.readouterr().out
        assert "Sequences to sync:  2" in out
        assert "Triggers to manage: 1" in out
        assert "ALWAYS triggers:    1" in out
