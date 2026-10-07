"""Tests for validate_schema_compatibility.py validator functions.

These tests mock the psycopg2 cursor to exercise each of the five primary
validators (extensions, function_languages, data_types, indexes, constraints)
without requiring a live Postgres. They bake in the upstream current behavior
against the UNTOUCHED code and act as a contract for a subsequent port.

The validator code uses pg_common.query(), which in turn calls
cur.execute(sql); if cur.description is truthy, zips cur.description[i][0]
with fetchall rows to return list[dict]. We drive each test by stubbing
.description (as list of single-element tuples) and .fetchall.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from validate_schema_compatibility import (
    INDEX_SUPPORT,
    SUPPORTED_EXTENSIONS,
    SUPPORTED_LANGUAGES,
    ValidationResult,
    validate_constraints,
    validate_data_types,
    validate_extensions,
    validate_function_languages,
    validate_indexes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _desc(*columns):
    """Build a cursor-description-style tuple of tuples for given column names.

    psycopg2 sets cur.description to a sequence of 7-tuples whose first element
    is the column name. pg_common.query() only uses index [0], so a single-
    element tuple per column is enough.
    """
    return tuple((c,) for c in columns)


def make_stage_cursor(*stages):
    """Return a cursor mock that returns scripted stages across repeated queries.

    Each stage is a (description, rows) pair. The first execute() yields the
    first stage, the second execute() yields the second stage, and so on.
    """
    cursor = MagicMock()
    stage_iter = iter(stages)

    def on_execute(sql, params=None):
        try:
            description, rows = next(stage_iter)
        except StopIteration:
            description, rows = None, []
        cursor.description = description
        cursor.fetchall.return_value = rows
        return None

    cursor.execute.side_effect = on_execute
    return cursor


def make_conn(cursor):
    """Wrap a cursor in a connection mock compatible with conn.cursor()."""
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def single_stage_conn(columns, rows):
    """Shorthand for a connection whose first (and only) query returns rows."""
    cursor = make_stage_cursor((_desc(*columns), rows))
    return make_conn(cursor)


# ---------------------------------------------------------------------------
# Tests: validate_extensions
# ---------------------------------------------------------------------------


class TestValidateExtensions:
    """Cover the extension compatibility validator."""

    def test_empty_catalog_returns_no_results(self):
        """No extensions installed (beyond plpgsql, which the SQL filters out)."""
        conn = single_stage_conn(["extname", "extversion"], [])
        results = validate_extensions(conn)
        assert results == []

    def test_single_supported_extension_ok(self):
        """A supported extension produces a single OK result."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("pgcrypto", "1.3")],
        )
        results = validate_extensions(conn)
        assert len(results) == 1
        r = results[0]
        assert r.status == "OK"
        assert r.category == "extension"
        assert r.item == "pgcrypto"
        assert "pgcrypto v1.3" in r.message
        assert r.details == {"version": "1.3"}

    def test_single_unsupported_extension_errors(self):
        """An unsupported extension produces a single ERROR result with action."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("timescaledb", "2.11.0")],
        )
        results = validate_extensions(conn)
        assert len(results) == 1
        r = results[0]
        assert r.status == "ERROR"
        assert r.category == "extension"
        assert r.item == "timescaledb"
        assert "NOT supported" in r.message
        assert r.details["version"] == "2.11.0"
        assert "Remove dependency" in r.details["action"]

    def test_mixed_supported_and_unsupported(self):
        """Returns one result per row, in order."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [
                ("pgcrypto", "1.3"),
                ("timescaledb", "2.11.0"),
                ("pg_trgm", "1.6"),
            ],
        )
        results = validate_extensions(conn)
        assert [r.status for r in results] == ["OK", "ERROR", "OK"]
        assert [r.item for r in results] == ["pgcrypto", "timescaledb", "pg_trgm"]

    def test_case_insensitive_supported_lookup(self):
        """Extension names are compared case-insensitively against SUPPORTED_EXTENSIONS."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("PgCrypto", "1.3")],
        )
        results = validate_extensions(conn)
        assert results[0].status == "OK"
        # Item preserves original casing
        assert results[0].item == "PgCrypto"

    def test_pgvector_ok(self):
        """pgvector lives in the supported set."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("pgvector", "0.5.1")],
        )
        results = validate_extensions(conn)
        assert results[0].status == "OK"
        assert "pgvector" in results[0].message

    def test_postgis_family_all_supported(self):
        """All postgis_* extensions are supported."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [
                ("postgis", "3.4"),
                ("postgis_topology", "3.4"),
                ("postgis_raster", "3.4"),
                ("postgis_sfcgal", "3.4"),
            ],
        )
        results = validate_extensions(conn)
        assert all(r.status == "OK" for r in results)
        assert len(results) == 4

    def test_unknown_extension_reports_version_in_details(self):
        """ERROR results still include the version in details for operator context."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("mystery_ext", "9.9.9")],
        )
        results = validate_extensions(conn)
        assert results[0].details["version"] == "9.9.9"

    def test_hyphenated_extension_name_supported(self):
        """uuid-ossp (with a hyphen) is in the supported set."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("uuid-ossp", "1.1")],
        )
        results = validate_extensions(conn)
        assert results[0].status == "OK"

    def test_result_category_is_extension(self):
        """All results from this validator use category='extension'."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("pgcrypto", "1.3"), ("timescaledb", "2.0")],
        )
        results = validate_extensions(conn)
        assert all(r.category == "extension" for r in results)

    def test_every_result_is_validationresult(self):
        """Defensive: every return element is a ValidationResult dataclass."""
        conn = single_stage_conn(
            ["extname", "extversion"],
            [("pgcrypto", "1.3")],
        )
        results = validate_extensions(conn)
        assert all(isinstance(r, ValidationResult) for r in results)


# ---------------------------------------------------------------------------
# Tests: validate_function_languages
# ---------------------------------------------------------------------------


class TestValidateFunctionLanguages:
    """Cover the function-language validator."""

    def test_empty_catalog_returns_no_results(self):
        """No user functions => no results."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [],
        )
        results = validate_function_languages(conn)
        assert results == []

    def test_plpgsql_is_supported(self):
        """plpgsql functions produce an OK result."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [("plpgsql", 7, ["public.foo", "public.bar"])],
        )
        results = validate_function_languages(conn)
        assert len(results) == 1
        r = results[0]
        assert r.status == "OK"
        assert r.item == "plpgsql"
        assert "7 functions in plpgsql" in r.message
        assert r.details["count"] == 7

    def test_sql_language_supported(self):
        """sql functions produce OK."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [("sql", 2, ["public.sq1", "public.sq2"])],
        )
        results = validate_function_languages(conn)
        assert results[0].status == "OK"
        assert results[0].item == "sql"

    def test_plpython_unsupported_errors(self):
        """plpython3u => ERROR with rewrite action."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [("plpython3u", 3, ["public.py_a", "public.py_b", "public.py_c"])],
        )
        results = validate_function_languages(conn)
        r = results[0]
        assert r.status == "ERROR"
        assert r.item == "plpython3u"
        assert "NOT supported" in r.message
        assert r.details["count"] == 3
        assert "Rewrite functions" in r.details["action"]
        # The functions list is stringified onto the details dict
        assert "public.py_a" in r.details["functions"]

    def test_plperl_unsupported(self):
        """plperl is also not supported."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [("plperl", 1, ["public.perl_fn"])],
        )
        results = validate_function_languages(conn)
        assert results[0].status == "ERROR"

    def test_multiple_languages_mixed(self):
        """Returns one result per language row."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [
                ("plpgsql", 10, ["public.a"]),
                ("plpython3u", 2, ["public.py"]),
                ("sql", 4, ["public.s1"]),
            ],
        )
        results = validate_function_languages(conn)
        assert [r.status for r in results] == ["OK", "ERROR", "OK"]
        assert [r.item for r in results] == ["plpgsql", "plpython3u", "sql"]

    def test_case_insensitive_language_lookup(self):
        """Language names are compared case-insensitively."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [("PLPGSQL", 1, ["public.foo"])],
        )
        results = validate_function_languages(conn)
        assert results[0].status == "OK"

    def test_internal_and_c_are_supported(self):
        """internal and c are in SUPPORTED_LANGUAGES."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [
                ("internal", 5, ["pg.builtin"]),
                ("c", 3, ["pg.extfunc"]),
            ],
        )
        results = validate_function_languages(conn)
        assert all(r.status == "OK" for r in results)

    def test_details_count_is_integer(self):
        """details['count'] is cast to int even when input is a string-like."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [("plpgsql", "12", ["public.x"])],
        )
        results = validate_function_languages(conn)
        assert results[0].details["count"] == 12
        assert isinstance(results[0].details["count"], int)

    def test_functions_missing_in_row_uses_empty_default(self):
        """The validator uses r.get('functions', '') so a missing key is tolerated."""
        # query() returns dicts keyed by cur.description, so we use 2 cols only.
        conn = single_stage_conn(
            ["lanname", "func_count"],
            [("plperl", 1)],
        )
        results = validate_function_languages(conn)
        # plperl is unsupported, so details['functions'] is set from '' default
        assert results[0].status == "ERROR"
        assert results[0].details["functions"] == ""

    def test_category_is_function_language(self):
        """All results use category='function_language'."""
        conn = single_stage_conn(
            ["lanname", "func_count", "functions"],
            [("plpgsql", 1, [])],
        )
        results = validate_function_languages(conn)
        assert all(r.category == "function_language" for r in results)


# ---------------------------------------------------------------------------
# Tests: validate_data_types
# ---------------------------------------------------------------------------


class TestValidateDataTypes:
    """Cover the custom-data-type validator."""

    def test_empty_catalog_returns_no_results(self):
        """No custom types => no results."""
        conn = single_stage_conn(["typtype", "type_name"], [])
        results = validate_data_types(conn)
        assert results == []

    def test_enum_type(self):
        """typtype='e' classifies as ENUM with a WARNING (caveat: ALTER TYPE
        ADD VALUE on the source post-migration will diverge from target)."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("e", "public.mood")],
        )
        results = validate_data_types(conn)
        r = results[0]
        assert r.status == "WARNING"
        assert r.category == "data_type"
        assert r.item == "public.mood"
        assert "ENUM type public.mood" in r.message
        assert r.details["type_kind"] == "ENUM"

    def test_composite_type(self):
        """typtype='c' classifies as COMPOSITE."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("c", "public.address")],
        )
        results = validate_data_types(conn)
        assert "COMPOSITE type public.address" in results[0].message
        assert results[0].details["type_kind"] == "COMPOSITE"

    def test_domain_type(self):
        """typtype='d' classifies as DOMAIN."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("d", "public.us_postal_code")],
        )
        results = validate_data_types(conn)
        assert "DOMAIN type public.us_postal_code" in results[0].message
        assert results[0].details["type_kind"] == "DOMAIN"

    def test_range_type(self):
        """typtype='r' classifies as RANGE."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("r", "public.int_range")],
        )
        results = validate_data_types(conn)
        assert "RANGE type public.int_range" in results[0].message
        assert results[0].details["type_kind"] == "RANGE"

    def test_unknown_typtype_falls_back_to_custom(self):
        """A typtype not in the known-kind map falls back to 'Custom' kind +
        WARNING status (since we can't know whether it's safe)."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("b", "public.weird_base")],
        )
        results = validate_data_types(conn)
        r = results[0]
        assert r.status == "WARNING"
        assert "Custom type public.weird_base" in r.message
        assert r.details["type_kind"] == "Custom"

    def test_multiple_kinds_at_once(self):
        """One result per row, order preserved."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [
                ("e", "public.mood"),
                ("d", "public.email"),
                ("c", "public.addr"),
                ("r", "public.daterange"),
            ],
        )
        results = validate_data_types(conn)
        assert len(results) == 4
        kinds = [r.details["type_kind"] for r in results]
        assert kinds == ["ENUM", "DOMAIN", "COMPOSITE", "RANGE"]

    def test_status_per_kind(self):
        """Per-kind statuses: ENUM/COMPOSITE/DOMAIN are WARNING (each has a
        migration caveat); RANGE is OK (pg_dump handles dependency ordering)."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [
                ("e", "public.a"),
                ("c", "public.b"),
                ("d", "public.c"),
                ("r", "public.d"),
            ],
        )
        results = validate_data_types(conn)
        statuses = {r.details["type_kind"]: r.status for r in results}
        assert statuses["ENUM"] == "WARNING"
        assert statuses["COMPOSITE"] == "WARNING"
        assert statuses["DOMAIN"] == "WARNING"
        assert statuses["RANGE"] == "OK"

    def test_category_is_data_type(self):
        """All results use category='data_type'."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("e", "x.y")],
        )
        results = validate_data_types(conn)
        assert all(r.category == "data_type" for r in results)

    def test_item_matches_qualified_name(self):
        """The item field is set to the schema.name string returned by the query."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("e", "analytics.report_status")],
        )
        results = validate_data_types(conn)
        assert results[0].item == "analytics.report_status"

    def test_message_mentions_pg_dump(self):
        """All messages reassure the operator that pg_dump will handle the type."""
        conn = single_stage_conn(
            ["typtype", "type_name"],
            [("e", "public.x")],
        )
        results = validate_data_types(conn)
        assert "pg_dump" in results[0].message


# ---------------------------------------------------------------------------
# Tests: validate_indexes
# ---------------------------------------------------------------------------


class TestValidateIndexes:
    """Cover the index-compatibility validator.

    validate_indexes runs TWO queries: an index_type summary, then a pgvector
    indexname scan. Both need to be staged on the same cursor.
    """

    def test_empty_catalog_returns_no_results(self):
        """No indexes and no pgvector rows => empty result list."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"), []),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert results == []

    def test_btree_indexes_ok(self):
        """A btree row produces one OK result."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("btree", 42, "128 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert len(results) == 1
        r = results[0]
        assert r.status == "OK"
        assert r.item == "btree"
        assert "42 btree indexes" in r.message
        assert "Full support" in r.message
        assert r.details == {"count": 42, "size": "128 kB"}

    def test_gist_indexes_have_rebuild_note(self):
        """gist indexes are OK but the message notes rebuild-recommended."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("gist", 3, "24 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert results[0].status == "OK"
        assert "rebuild recommended" in results[0].message

    def test_all_supported_index_types_ok(self):
        """Every AM listed in INDEX_SUPPORT maps to OK."""
        rows = [(name, 1, "8 kB") for name in INDEX_SUPPORT.keys()]
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"), rows),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert len(results) == len(INDEX_SUPPORT)
        assert all(r.status == "OK" for r in results)

    def test_unknown_index_type_uses_default_supported(self):
        """Unknown AMs fall back to the default {'supported': True, 'notes': 'Check compatibility'}."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("some_new_am", 1, "8 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        r = results[0]
        assert r.status == "OK"
        assert "Check compatibility" in r.message

    def test_ivfflat_pgvector_note(self):
        """ivfflat indexes get the pgvector rebuild note."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("ivfflat", 2, "16 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert results[0].status == "OK"
        assert "rebuild after data load" in results[0].message

    def test_hnsw_pgvector_note(self):
        """hnsw indexes get the pgvector rebuild note."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("hnsw", 1, "8 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert "rebuild after data load" in results[0].message

    def test_pgvector_scan_adds_warning_when_indexes_found(self):
        """The 2nd query (pgvector indexdef scan) triggers a WARNING result."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("btree", 10, "80 kB")]),
            (_desc("indexname"),
             [("idx_vec_1",), ("idx_vec_2",), ("idx_vec_3",)]),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        # First result is the btree OK, second is the pgvector WARNING.
        assert len(results) == 2
        warn = results[1]
        assert warn.status == "WARNING"
        assert warn.item == "pgvector_indexes"
        assert "3 pgvector indexes" in warn.message
        assert warn.details["count"] == 3

    def test_pgvector_scan_empty_adds_no_warning(self):
        """If the pgvector scan is empty, no extra WARNING is appended."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("btree", 10, "80 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert len(results) == 1
        assert results[0].status == "OK"

    def test_case_insensitive_am_lookup(self):
        """AM names are lowercased before lookup."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("BTREE", 1, "8 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert results[0].status == "OK"
        assert "Full support" in results[0].message

    def test_details_count_is_integer(self):
        """details['count'] is explicitly cast to int."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("btree", "42", "128 kB")]),
            (_desc("indexname"), []),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert results[0].details["count"] == 42
        assert isinstance(results[0].details["count"], int)

    def test_category_is_index_type(self):
        """All index results use category='index_type'."""
        cursor = make_stage_cursor(
            (_desc("index_type", "index_count", "total_size"),
             [("btree", 1, "8 kB"), ("gin", 1, "8 kB")]),
            (_desc("indexname"), [("foo",)]),
        )
        conn = make_conn(cursor)
        results = validate_indexes(conn)
        assert all(r.category == "index_type" for r in results)


# ---------------------------------------------------------------------------
# Tests: validate_constraints
# ---------------------------------------------------------------------------


class TestValidateConstraints:
    """Cover the constraint-compatibility validator.

    validate_constraints runs TWO queries: deferred-constraints, then
    exclusion-constraints. Each may produce 0 or 1 aggregated ValidationResult.
    """

    def test_empty_catalog_returns_no_results(self):
        """No deferrable and no exclusion constraints => no results."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"), []),
            (_desc("qualified_name", "conname"), []),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert results == []

    def test_only_deferred_constraints(self):
        """Deferred constraints alone produce a single WARNING result."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"),
             [
                 ("public.orders", "orders_fk", "f"),
                 ("public.orders", "orders_uq", "u"),
             ]),
            (_desc("qualified_name", "conname"), []),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert len(results) == 1
        r = results[0]
        assert r.status == "WARNING"
        assert r.item == "deferred_constraints"
        assert r.category == "constraint"
        assert "2 deferred constraints" in r.message
        assert r.details["count"] == 2

    def test_only_exclusion_constraints(self):
        """Exclusion constraints alone produce a single OK result."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"), []),
            (_desc("qualified_name", "conname"),
             [("public.bookings", "bookings_no_overlap")]),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert len(results) == 1
        r = results[0]
        assert r.status == "OK"
        assert r.item == "exclusion_constraints"
        assert r.category == "constraint"
        assert "1 exclusion constraints" in r.message
        assert r.details["count"] == 1

    def test_both_deferred_and_exclusion(self):
        """Both kinds present => two results in order: deferred WARNING, exclusion OK."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"),
             [("public.t1", "c1", "f"), ("public.t2", "c2", "u"), ("public.t3", "c3", "p")]),
            (_desc("qualified_name", "conname"),
             [("public.t4", "c4"), ("public.t5", "c5")]),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert len(results) == 2
        assert results[0].item == "deferred_constraints"
        assert results[0].status == "WARNING"
        assert results[0].details["count"] == 3
        assert results[1].item == "exclusion_constraints"
        assert results[1].status == "OK"
        assert results[1].details["count"] == 2

    def test_deferred_single_row(self):
        """A single deferred constraint still produces one aggregated result."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"),
             [("public.orders", "orders_fk", "f")]),
            (_desc("qualified_name", "conname"), []),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert len(results) == 1
        assert results[0].details["count"] == 1
        assert "1 deferred constraints" in results[0].message

    def test_exclusion_single_row(self):
        """A single exclusion constraint still produces one aggregated result."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"), []),
            (_desc("qualified_name", "conname"),
             [("public.rooms", "rooms_no_overlap")]),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert len(results) == 1
        assert results[0].details["count"] == 1

    def test_message_mentions_verify_behavior_for_deferred(self):
        """Deferred WARNING message asks the operator to verify behavior after migration."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"),
             [("public.t", "c", "f")]),
            (_desc("qualified_name", "conname"), []),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert "verify behavior" in results[0].message

    def test_message_declares_exclusion_supported(self):
        """Exclusion OK message says 'supported'."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"), []),
            (_desc("qualified_name", "conname"),
             [("public.t", "c")]),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert "supported" in results[0].message

    def test_many_deferred_constraints_counted(self):
        """The aggregated count reflects the number of rows returned."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"),
             [("public.t", f"c{i}", "f") for i in range(25)]),
            (_desc("qualified_name", "conname"), []),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert results[0].details["count"] == 25
        assert "25 deferred" in results[0].message

    def test_many_exclusion_constraints_counted(self):
        """The exclusion count reflects the number of rows returned."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"), []),
            (_desc("qualified_name", "conname"),
             [("public.t", f"c{i}") for i in range(7)]),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert results[0].details["count"] == 7

    def test_all_results_use_constraint_category(self):
        """Both result variants use category='constraint'."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"),
             [("public.t", "c", "f")]),
            (_desc("qualified_name", "conname"),
             [("public.t2", "c2")]),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        assert all(r.category == "constraint" for r in results)

    def test_details_counts_are_ints(self):
        """The aggregated counts are plain ints."""
        cursor = make_stage_cursor(
            (_desc("table_name", "conname", "contype"),
             [("public.t", "c1", "f"), ("public.t", "c2", "f")]),
            (_desc("qualified_name", "conname"),
             [("public.t2", "c3")]),
        )
        conn = make_conn(cursor)
        results = validate_constraints(conn)
        for r in results:
            assert isinstance(r.details["count"], int)


# ---------------------------------------------------------------------------
# Tests: module-level constants (sanity)
# ---------------------------------------------------------------------------


class TestModuleConstants:
    """Sanity checks on the module-level sets so accidental typos trip the suite."""

    def test_supported_extensions_is_non_empty(self):
        assert len(SUPPORTED_EXTENSIONS) > 0

    def test_plpgsql_in_supported_languages(self):
        assert "plpgsql" in SUPPORTED_LANGUAGES

    def test_index_support_has_btree(self):
        assert "btree" in INDEX_SUPPORT
        assert INDEX_SUPPORT["btree"]["supported"] is True
