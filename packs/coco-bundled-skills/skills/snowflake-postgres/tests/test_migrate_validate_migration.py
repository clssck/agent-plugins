"""Tests for validate_migration.py — row counts, checksums, matview detection, schema diff.

These tests establish a green baseline against the upstream migration script.
They bake in the script's current behavior (including quirks) so a subsequent port
into our repo has a contract to satisfy.

All DB interactions are mocked via the `mock_cursor` / `mock_conn` fixtures defined
in conftest.py. No live DB is required.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from validate_migration import (
    compare_row_counts,
    get_exact_counts,
    get_materialized_views,
    get_numeric_aggregates,
    get_table_checksums,
    get_table_row_counts,
)


# ---------------------------------------------------------------------------
# Helpers for configuring the mock cursor to mimic psycopg2's
# cursor.description / cursor.fetchall() contract used by pg_common.query().
# ---------------------------------------------------------------------------


def _set_query_result(cursor, columns, rows):
    """Configure cursor to return the given rows under the given columns.

    psycopg2's `cursor.description` is a sequence of 7-tuples; pg_common.query
    only looks at `d[0]` (the column name), so we fake it with 1-element tuples.
    """
    cursor.description = [(c,) for c in columns]
    cursor.fetchall.return_value = rows


def _queue_query_results(cursor, results):
    """Sequence multiple (columns, rows) results across successive execute() calls.

    Each call to cursor.execute resets description+fetchall to the next entry.
    """
    calls = list(results)

    def fake_execute(sql, params=None):
        if calls:
            cols, rows = calls.pop(0)
            cursor.description = [(c,) for c in cols]
            cursor.fetchall.return_value = rows
        return None

    cursor.execute.side_effect = fake_execute


# ---------------------------------------------------------------------------
# TestMaterializedViewDetection
# ---------------------------------------------------------------------------


class TestMaterializedViewDetection:
    """get_materialized_views() returns a set of 'schema.view' strings."""

    def test_empty_returns_empty_set(self, mock_conn, mock_cursor):
        _set_query_result(mock_cursor, ["view_name"], [])
        result = get_materialized_views(mock_conn)
        assert result == set()

    def test_returns_set_of_view_names(self, mock_conn, mock_cursor):
        _set_query_result(
            mock_cursor,
            ["view_name"],
            [("public.mv_sales",), ("analytics.mv_users",)],
        )
        result = get_materialized_views(mock_conn)
        assert result == {"public.mv_sales", "analytics.mv_users"}

    def test_single_view(self, mock_conn, mock_cursor):
        _set_query_result(mock_cursor, ["view_name"], [("public.only_one",)])
        result = get_materialized_views(mock_conn)
        assert result == {"public.only_one"}

    def test_duplicate_names_collapse_to_set(self, mock_conn, mock_cursor):
        # Defensive: even if the query returned dupes (it shouldn't), set() collapses.
        _set_query_result(
            mock_cursor,
            ["view_name"],
            [("public.mv",), ("public.mv",)],
        )
        result = get_materialized_views(mock_conn)
        assert result == {"public.mv"}

    def test_query_excludes_system_schemas(self, mock_conn, mock_cursor):
        """The SQL text excludes pg_catalog + information_schema."""
        _set_query_result(mock_cursor, ["view_name"], [])
        get_materialized_views(mock_conn)
        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "pg_catalog" in executed_sql
        assert "information_schema" in executed_sql
        assert "pg_matviews" in executed_sql


# ---------------------------------------------------------------------------
# TestRowCounts — get_table_row_counts() and compare_row_counts()
# ---------------------------------------------------------------------------


class TestRowCounts:
    """get_table_row_counts builds a dict of table_name -> stats row."""

    def test_empty_result(self, mock_conn, mock_cursor):
        _set_query_result(
            mock_cursor,
            ["table_name", "row_count", "size_bytes", "size_pretty"],
            [],
        )
        result = get_table_row_counts(mock_conn)
        assert result == {}

    def test_single_table(self, mock_conn, mock_cursor):
        _set_query_result(
            mock_cursor,
            ["table_name", "row_count", "size_bytes", "size_pretty"],
            [("public.users", 100, 16384, "16 kB")],
        )
        result = get_table_row_counts(mock_conn)
        assert "public.users" in result
        assert result["public.users"]["row_count"] == 100
        assert result["public.users"]["size_pretty"] == "16 kB"

    def test_multiple_tables_keyed_by_table_name(self, mock_conn, mock_cursor):
        _set_query_result(
            mock_cursor,
            ["table_name", "row_count", "size_bytes", "size_pretty"],
            [
                ("public.users", 100, 16384, "16 kB"),
                ("public.orders", 250, 32768, "32 kB"),
                ("analytics.events", 5000, 262144, "256 kB"),
            ],
        )
        result = get_table_row_counts(mock_conn)
        assert set(result.keys()) == {"public.users", "public.orders", "analytics.events"}
        assert result["public.orders"]["row_count"] == 250

    def test_no_schema_filter_when_schemas_none(self, mock_conn, mock_cursor):
        _set_query_result(
            mock_cursor, ["table_name", "row_count", "size_bytes", "size_pretty"], []
        )
        get_table_row_counts(mock_conn, schemas=None)
        sql = mock_cursor.execute.call_args[0][0]
        # No "schemaname IN (..." filter is appended when schemas is None
        assert "schemaname IN (" not in sql

    def test_schema_filter_single_schema(self, mock_conn, mock_cursor):
        _set_query_result(
            mock_cursor, ["table_name", "row_count", "size_bytes", "size_pretty"], []
        )
        get_table_row_counts(mock_conn, schemas=["public"])
        # Now uses %s placeholders + a params tuple (parameterized binding,
        # not f-string interpolation). The schema name is in args[1].
        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert "schemaname IN (%s)" in sql
        assert params == ("public",)

    def test_schema_filter_multiple_schemas(self, mock_conn, mock_cursor):
        _set_query_result(
            mock_cursor, ["table_name", "row_count", "size_bytes", "size_pretty"], []
        )
        get_table_row_counts(mock_conn, schemas=["public", "analytics"])
        sql = mock_cursor.execute.call_args[0][0]
        params = mock_cursor.execute.call_args[0][1]
        assert "schemaname IN (%s,%s)" in sql
        assert params == ("public", "analytics")


class TestCompareRowCounts:
    """compare_row_counts() produces per-table status rows."""

    def test_all_match(self):
        src = {
            "public.users": {"row_count": 100, "size_pretty": "16 kB"},
            "public.orders": {"row_count": 250, "size_pretty": "32 kB"},
        }
        tgt = {
            "public.users": {"row_count": 100, "size_pretty": "16 kB"},
            "public.orders": {"row_count": 250, "size_pretty": "32 kB"},
        }
        results = compare_row_counts(src, tgt)
        assert len(results) == 2
        for r in results:
            assert r["status"] == "MATCH"
            assert r["diff"] == 0
            assert r["is_matview"] is False

    def test_mismatch(self):
        src = {"public.users": {"row_count": 100, "size_pretty": "16 kB"}}
        tgt = {"public.users": {"row_count": 95, "size_pretty": "16 kB"}}
        results = compare_row_counts(src, tgt)
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "MISMATCH"
        assert r["source_rows"] == 100
        assert r["target_rows"] == 95
        assert r["diff"] == -5  # target - source

    def test_missing_on_source(self):
        src = {}
        tgt = {"public.only_in_tgt": {"row_count": 10, "size_pretty": "1 kB"}}
        results = compare_row_counts(src, tgt)
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "MISSING_SOURCE"
        assert r["source_rows"] == 0
        assert r["target_rows"] == 10
        assert r["source_size"] == "N/A"

    def test_missing_on_target(self):
        src = {"public.only_in_src": {"row_count": 7, "size_pretty": "2 kB"}}
        tgt = {}
        results = compare_row_counts(src, tgt)
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "MISSING_TARGET"
        assert r["source_rows"] == 7
        assert r["target_rows"] == 0
        assert r["source_size"] == "2 kB"

    def test_matview_mismatch_flagged_separately(self):
        src = {"public.mv_sales": {"row_count": 100, "size_pretty": "16 kB"}}
        tgt = {"public.mv_sales": {"row_count": 99, "size_pretty": "16 kB"}}
        matviews = {"public.mv_sales"}
        results = compare_row_counts(src, tgt, matviews=matviews)
        assert len(results) == 1
        r = results[0]
        assert r["status"] == "MATVIEW_MISMATCH"
        assert r["is_matview"] is True

    def test_matview_match_still_counts_as_match(self):
        src = {"public.mv_sales": {"row_count": 100, "size_pretty": "16 kB"}}
        tgt = {"public.mv_sales": {"row_count": 100, "size_pretty": "16 kB"}}
        results = compare_row_counts(src, tgt, matviews={"public.mv_sales"})
        r = results[0]
        assert r["status"] == "MATCH"
        assert r["is_matview"] is True

    def test_results_sorted_by_table_name(self):
        src = {
            "z.table": {"row_count": 1, "size_pretty": "1"},
            "a.table": {"row_count": 1, "size_pretty": "1"},
            "m.table": {"row_count": 1, "size_pretty": "1"},
        }
        tgt = dict(src)
        results = compare_row_counts(src, tgt)
        names = [r["table"] for r in results]
        assert names == sorted(names)

    def test_default_matviews_is_empty_set(self):
        """When matviews=None, no tables are considered matviews."""
        src = {"public.users": {"row_count": 100, "size_pretty": "16 kB"}}
        tgt = {"public.users": {"row_count": 50, "size_pretty": "16 kB"}}
        results = compare_row_counts(src, tgt, matviews=None)
        assert results[0]["status"] == "MISMATCH"
        assert results[0]["is_matview"] is False

    def test_diff_calculation_positive(self):
        """Target larger than source produces positive diff."""
        src = {"t": {"row_count": 10, "size_pretty": "1"}}
        tgt = {"t": {"row_count": 25, "size_pretty": "1"}}
        results = compare_row_counts(src, tgt)
        assert results[0]["diff"] == 15

    def test_diff_calculation_negative(self):
        """Source larger than target produces negative diff."""
        src = {"t": {"row_count": 100, "size_pretty": "1"}}
        tgt = {"t": {"row_count": 40, "size_pretty": "1"}}
        results = compare_row_counts(src, tgt)
        assert results[0]["diff"] == -60


# ---------------------------------------------------------------------------
# TestExactCounts
# ---------------------------------------------------------------------------


class TestExactCounts:
    """get_exact_counts runs COUNT(*) per table via scalar()."""

    def test_returns_int_count(self, mock_conn, mock_cursor):
        _set_query_result(mock_cursor, ["count"], [(42,)])
        result = get_exact_counts(mock_conn, ["public.users"])
        assert result == {"public.users": 42}

    def test_zero_count(self, mock_conn, mock_cursor):
        _set_query_result(mock_cursor, ["count"], [(0,)])
        result = get_exact_counts(mock_conn, ["public.empty"])
        assert result["public.empty"] == 0

    def test_none_result_becomes_zero(self, mock_conn, mock_cursor):
        """scalar() returning None yields 0 in results (current behavior)."""
        # An empty fetchall means scalar() returns None.
        _set_query_result(mock_cursor, ["count"], [])
        result = get_exact_counts(mock_conn, ["public.weird"])
        assert result["public.weird"] == 0

    def test_error_captured_as_dict(self, mock_conn, mock_cursor):
        """Exceptions are caught and stored as `{'error': msg}` dicts so the
        caller can flag validation failure rather than treating an error
        string as a count value."""
        mock_cursor.execute.side_effect = Exception("relation does not exist")
        result = get_exact_counts(mock_conn, ["public.missing"])
        assert isinstance(result["public.missing"], dict)
        assert "error" in result["public.missing"]
        assert "relation does not exist" in result["public.missing"]["error"]

    def test_multiple_tables(self, mock_conn, mock_cursor):
        _queue_query_results(
            mock_cursor,
            [
                (["count"], [(10,)]),
                (["count"], [(20,)]),
                (["count"], [(30,)]),
            ],
        )
        result = get_exact_counts(mock_conn, ["a.x", "b.y", "c.z"])
        assert result == {"a.x": 10, "b.y": 20, "c.z": 30}


# ---------------------------------------------------------------------------
# TestChecksumMatch
# ---------------------------------------------------------------------------


class TestChecksumMatch:
    """get_table_checksums returns dict of table -> md5 string."""

    def test_returns_checksum_per_table(self, mock_conn, mock_cursor):
        _set_query_result(mock_cursor, ["checksum"], [("abc123def456",)])
        result = get_table_checksums(mock_conn, ["public.users"])
        assert result == {"public.users": "abc123def456"}

    def test_limit_truncates_input(self, mock_conn, mock_cursor):
        """Default limit is 10; extra tables are silently dropped."""
        _set_query_result(mock_cursor, ["checksum"], [("hash",)])
        tables = [f"t{i}" for i in range(15)]
        result = get_table_checksums(mock_conn, tables, limit=5)
        assert len(result) == 5
        assert "t0" in result
        assert "t4" in result
        assert "t5" not in result

    def test_empty_result_yields_none(self, mock_conn, mock_cursor):
        """If the checksum query returns no rows, value is None."""
        _set_query_result(mock_cursor, ["checksum"], [])
        result = get_table_checksums(mock_conn, ["public.empty"])
        assert result == {"public.empty": None}

    def test_exception_yields_error_dict(self, mock_conn, mock_cursor):
        """Exceptions surface as `{'error': msg}` so a comparison code path
        won't treat None == None as a match."""
        mock_cursor.execute.side_effect = Exception("boom")
        result = get_table_checksums(mock_conn, ["public.bad"])
        assert isinstance(result["public.bad"], dict)
        assert "boom" in result["public.bad"]["error"]

    def test_matching_checksums_across_dbs(self, mock_conn, mock_cursor):
        """Two separate checksum calls that match (caller compares equality)."""
        _set_query_result(mock_cursor, ["checksum"], [("samehash",)])
        src = get_table_checksums(mock_conn, ["t"])

        # Reset mock for a second "db"
        mock_cursor2 = MagicMock()
        mock_cursor2.__enter__ = MagicMock(return_value=mock_cursor2)
        mock_cursor2.__exit__ = MagicMock(return_value=False)
        _set_query_result(mock_cursor2, ["checksum"], [("samehash",)])
        conn2 = MagicMock()
        conn2.cursor.return_value = mock_cursor2
        tgt = get_table_checksums(conn2, ["t"])

        assert src["t"] == tgt["t"] == "samehash"

    def test_mismatching_checksums(self, mock_conn, mock_cursor):
        """Two checksums that differ — caller considers this a mismatch."""
        _set_query_result(mock_cursor, ["checksum"], [("hash_a",)])
        src = get_table_checksums(mock_conn, ["t"])

        mock_cursor2 = MagicMock()
        mock_cursor2.__enter__ = MagicMock(return_value=mock_cursor2)
        mock_cursor2.__exit__ = MagicMock(return_value=False)
        _set_query_result(mock_cursor2, ["checksum"], [("hash_b",)])
        conn2 = MagicMock()
        conn2.cursor.return_value = mock_cursor2
        tgt = get_table_checksums(conn2, ["t"])

        assert src["t"] != tgt["t"]


# ---------------------------------------------------------------------------
# TestNumericAggregates
# ---------------------------------------------------------------------------


class TestNumericAggregates:
    """get_numeric_aggregates builds sum()/count() per numeric column."""

    def test_no_numeric_columns_skips_table(self, mock_conn, mock_cursor):
        """When information_schema returns no numeric cols, table is omitted."""
        _set_query_result(mock_cursor, ["column_name"], [])
        result = get_numeric_aggregates(mock_conn, ["public.no_nums"])
        assert result == {}

    def test_builds_sum_and_count_per_column(self, mock_conn, mock_cursor):
        _queue_query_results(
            mock_cursor,
            [
                # information_schema.columns lookup
                (["column_name"], [("id",), ("amount",)]),
                # aggregate query result
                (
                    ["sum_id", "count_id", "sum_amount", "count_amount"],
                    [("100", "10", "250", "10")],
                ),
            ],
        )
        result = get_numeric_aggregates(mock_conn, ["public.orders"])
        assert "public.orders" in result
        assert result["public.orders"]["sum_id"] == "100"
        assert result["public.orders"]["count_amount"] == "10"

    def test_exception_during_lookup_yields_error_dict(self, mock_conn, mock_cursor):
        """If anything raises, the table gets an `{'error': msg}` dict so
        downstream comparison code can flag failure instead of silently
        matching empty {} vs empty {}."""
        mock_cursor.execute.side_effect = Exception("oops")
        result = get_numeric_aggregates(mock_conn, ["public.bad"])
        assert isinstance(result["public.bad"], dict)
        assert "oops" in result["public.bad"].get("error", "")

    def test_limit_honored(self, mock_conn, mock_cursor):
        """Tables past the limit are never queried."""
        # Only the first 2 should be processed; stub returns "no columns" each time.
        _queue_query_results(
            mock_cursor,
            [
                (["column_name"], []),  # first table's info schema lookup
                (["column_name"], []),  # second table's info schema lookup
            ],
        )
        tables = ["a", "b", "c", "d", "e"]
        result = get_numeric_aggregates(mock_conn, tables, limit=2)
        # First two had no numeric cols, so they're skipped in result.
        # The key assertion is: only two execute calls happened.
        assert mock_cursor.execute.call_count == 2
        assert result == {}


# ---------------------------------------------------------------------------
# TestSchemaDiff — tables/columns present on one side but not the other
# ---------------------------------------------------------------------------


class TestSchemaDiff:
    """Schema-diff semantics via compare_row_counts: unions the two keyspaces."""

    def test_table_only_on_source(self):
        src = {"public.only_here": {"row_count": 5, "size_pretty": "1 kB"}}
        tgt = {}
        results = compare_row_counts(src, tgt)
        assert len(results) == 1
        assert results[0]["table"] == "public.only_here"
        assert results[0]["status"] == "MISSING_TARGET"

    def test_table_only_on_target(self):
        src = {}
        tgt = {"public.only_there": {"row_count": 3, "size_pretty": "1 kB"}}
        results = compare_row_counts(src, tgt)
        assert len(results) == 1
        assert results[0]["table"] == "public.only_there"
        assert results[0]["status"] == "MISSING_SOURCE"

    def test_all_three_states_in_one_diff(self):
        """Mix of common / source-only / target-only tables."""
        src = {
            "public.common": {"row_count": 10, "size_pretty": "1"},
            "public.src_only": {"row_count": 5, "size_pretty": "1"},
        }
        tgt = {
            "public.common": {"row_count": 10, "size_pretty": "1"},
            "public.tgt_only": {"row_count": 7, "size_pretty": "1"},
        }
        results = compare_row_counts(src, tgt)
        by_table = {r["table"]: r for r in results}
        assert by_table["public.common"]["status"] == "MATCH"
        assert by_table["public.src_only"]["status"] == "MISSING_TARGET"
        assert by_table["public.tgt_only"]["status"] == "MISSING_SOURCE"

    def test_empty_inputs_produce_empty_results(self):
        assert compare_row_counts({}, {}) == []

    def test_matview_only_on_source_is_missing_target(self):
        """A matview missing on the target is MISSING_TARGET (not MATVIEW_MISMATCH).

        Current behavior: the MATVIEW_MISMATCH branch is reached only when both
        sides exist but counts differ. A one-sided matview is still MISSING_*.
        """
        src = {"public.mv": {"row_count": 10, "size_pretty": "1"}}
        tgt = {}
        results = compare_row_counts(src, tgt, matviews={"public.mv"})
        assert results[0]["status"] == "MISSING_TARGET"
        # But it is still flagged as a matview
        assert results[0]["is_matview"] is True

    def test_source_size_pretty_default_question_mark(self):
        """When src row has no size_pretty key, '?' is used (not 'N/A')."""
        src = {"t": {"row_count": 5}}  # no size_pretty
        tgt = {"t": {"row_count": 5}}
        results = compare_row_counts(src, tgt)
        assert results[0]["source_size"] == "?"
