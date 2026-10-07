# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for builtin AI function (``query_text``) evaluation.

Covers the engine's ``query_text`` collection path — the SQL it builds for the
cost path (an ``AI_COMPLETE`` expression, ``show_details`` injected for token
usage) versus the direct path (other builtins like ``AI_CLASSIFY``, no token
capture) — and that ``evaluate(query_text=...)`` wires the collected rows
through metric scoring. The Snowpark session is faked; the generated SQL is
captured and asserted, no warehouse required.
"""

from __future__ import annotations

import pytest
from snowflake.snowpark import Row

import snowflake_ai_optimize.core.evaluation as ev
from snowflake_ai_optimize.core.evaluation import (
    _collect_query_text_rows,
    _query_text_is_single_bare_ai_complete,
    evaluate,
)


class FakeDF:
    def __init__(self, rows):
        self._rows = rows

    def collect(self):
        return self._rows


class FakeSession:
    """Captures the single SQL statement and returns pre-canned rows."""

    def __init__(self, rows):
        self._rows = rows
        self.sql_calls: list[str] = []

    def sql(self, query):
        self.sql_calls.append(query)
        return FakeDF(self._rows)


def _patch_columns(monkeypatch, *, columns, expected="EXPECTED_COL"):
    """Stub the table-introspection helpers so only the main query hits SQL."""
    monkeypatch.setattr(ev, "get_table_column_names", lambda s, t: set(columns))
    monkeypatch.setattr(ev, "resolve_expected_column", lambda cols, label: expected)
    monkeypatch.setattr(ev, "validate_input_columns", lambda *a, **k: None)


class TestSingleBareAiCompleteDetection:
    def test_bare_single_ai_complete_is_true(self):
        # Only a bare, single, top-level AI_COMPLETE takes the cost path.
        assert _query_text_is_single_bare_ai_complete("AI_COMPLETE('m', 'x' || c)")
        assert _query_text_is_single_bare_ai_complete("  ai_complete ( 'm', c )  ")

    def test_wrapped_or_accessed_is_false(self):
        # Wrapping or a trailing accessor -> direct path (not cost).
        assert not _query_text_is_single_bare_ai_complete("UPPER(AI_COMPLETE('m', c))")
        assert not _query_text_is_single_bare_ai_complete(
            "AI_COMPLETE('m', c):answer::VARCHAR"
        )

    def test_multiple_or_other_is_false(self):
        assert not _query_text_is_single_bare_ai_complete(
            "AI_COMPLETE('m', a) || AI_COMPLETE('m', b)"
        )
        assert not _query_text_is_single_bare_ai_complete("AI_CLASSIFY(c, ['a','b'])")
        assert not _query_text_is_single_bare_ai_complete("AI_FILTER(c)")


class TestReservedColumnGuard:
    def test_rejects_reserved_column_collision(self, monkeypatch):
        # A dataset column named like a reserved output alias (PREDICTED here)
        # is rejected up front with a clear error, not an opaque SQL failure.
        _patch_columns(monkeypatch, columns={"C", "EXPECTED_COL", "PREDICTED"})
        session = FakeSession([])
        with pytest.raises(ValueError, match="reserved output names"):
            _collect_query_text_rows(
                session,
                query_text="AI_COMPLETE('m', c)",
                test_table="db.sch.t",
                input_columns=["c"],
                label_column="expected_col",
                metric_name="exact_match",
                metric_options=None,
                sample_size=None,
            )
        # The guard fires before any query is issued.
        assert session.sql_calls == []


class TestCollectQueryTextRows:
    def test_cost_path_injects_show_details_and_tokens(self, monkeypatch):
        _patch_columns(monkeypatch, columns={"QUESTION_COL", "EXPECTED_COL"})
        # Tokens returned as NULL so cost estimation is skipped (no rate table
        # needed) while still exercising the cost-path SQL shape.
        rows = [
            Row(
                ROW_ID=1,
                EXPECTED="paris",
                PREDICTED="paris",
                __PROMPT_TOKENS=None,
                __COMPLETION_TOKENS=None,
            )
        ]
        session = FakeSession(rows)
        query_text = "AI_COMPLETE('llama3.1-70b', 'Answer: ' || question_col)"

        input_cols, _output_field, _opts, results, cost = _collect_query_text_rows(
            session,
            query_text=query_text,
            test_table="db.sch.qa",
            input_columns=["question_col"],
            label_column="expected_col",
            metric_name="exact_match",
            metric_options=None,
            sample_size=None,
        )

        assert input_cols == ["question_col"]
        assert results == rows
        assert cost is None  # tokens were NULL
        sql = session.sql_calls[-1]
        # show_details injected for per-row token usage, and the token columns
        # + single-evaluation CTE join are present.
        assert "show_details" in sql.lower()
        assert "__PROMPT_TOKENS" in sql and "__COMPLETION_TOKENS" in sql
        assert "__ai_call" in sql and "PARSE_JSON" in sql

    def test_cost_path_returns_cost_when_tokens_present(self, monkeypatch):
        _patch_columns(monkeypatch, columns={"QUESTION_COL", "EXPECTED_COL"})
        # estimate_candidate_cost is imported into the evaluation module namespace,
        # so patch it there (not on the experiment module).
        monkeypatch.setattr(ev, "estimate_candidate_cost", lambda model, pt, ct: 0.0007)
        rows = [
            Row(
                ROW_ID=1,
                EXPECTED="a",
                PREDICTED="a",
                __PROMPT_TOKENS=10.0,
                __COMPLETION_TOKENS=4.0,
            ),
            Row(
                ROW_ID=2,
                EXPECTED="b",
                PREDICTED="b",
                __PROMPT_TOKENS=20.0,
                __COMPLETION_TOKENS=6.0,
            ),
        ]
        session = FakeSession(rows)
        _, _, _, _, cost = _collect_query_text_rows(
            session,
            query_text="AI_COMPLETE('claude-3-5-sonnet', body_col)",
            test_table="db.sch.qa",
            input_columns=["body_col"],
            label_column="expected_col",
            metric_name="exact_match",
            metric_options=None,
            sample_size=None,
        )
        assert cost is not None
        assert cost.model == "claude-3-5-sonnet"
        assert cost.num_rows == 2
        assert cost.avg_prompt_tokens == 15.0
        assert cost.avg_completion_tokens == 5.0
        assert cost.estimated_cost_per_call == 0.0007

    def test_direct_path_no_ai_complete(self, monkeypatch):
        _patch_columns(monkeypatch, columns={"TEXT_COL", "EXPECTED_COL"})
        rows = [Row(ROW_ID=1, EXPECTED="spam", PREDICTED="spam")]
        session = FakeSession(rows)
        query_text = "AI_CLASSIFY(text_col, ['spam','ham'])"

        _, _, _, results, cost = _collect_query_text_rows(
            session,
            query_text=query_text,
            test_table="db.sch.msgs",
            input_columns=["text_col"],
            label_column="expected_col",
            metric_name="exact_match",
            metric_options=None,
            sample_size=None,
        )

        assert results == rows
        assert cost is None
        sql = session.sql_calls[-1]
        # The expression is evaluated directly as PREDICTED; no token capture.
        assert f"({query_text}) AS PREDICTED" in sql
        assert "show_details" not in sql.lower()
        assert "__PROMPT_TOKENS" not in sql

    def test_direct_path_wrapped_ai_complete(self, monkeypatch):
        # A single AI_COMPLETE wrapped in another call is NOT a bare AI_COMPLETE,
        # so it takes the direct path: the whole expression is the prediction
        # (the true formed-query result) and no cost is measured.
        _patch_columns(monkeypatch, columns={"C", "EXPECTED_COL"})
        session = FakeSession([Row(ROW_ID=1, EXPECTED="X", PREDICTED="X")])
        query_text = "UPPER(AI_COMPLETE('m', c))"
        _, _, _, _, cost = _collect_query_text_rows(
            session,
            query_text=query_text,
            test_table="db.sch.t",
            input_columns=["c"],
            label_column="expected_col",
            metric_name="exact_match",
            metric_options=None,
            sample_size=None,
        )
        assert cost is None
        sql = session.sql_calls[-1]
        assert f"({query_text}) AS PREDICTED" in sql
        assert "__PROMPT_TOKENS" not in sql

    def test_sample_size_applies_limit(self, monkeypatch):
        _patch_columns(monkeypatch, columns={"C", "EXPECTED_COL"})
        session = FakeSession([Row(ROW_ID=1, EXPECTED="x", PREDICTED="x")])
        _collect_query_text_rows(
            session,
            query_text="AI_FILTER(c)",
            test_table="db.sch.t",
            input_columns=["c"],
            label_column="expected_col",
            metric_name="exact_match",
            metric_options=None,
            sample_size=25,
        )
        assert "LIMIT 25" in session.sql_calls[-1]


class TestEvaluateQueryText:
    def test_evaluate_routes_query_text_and_scores(self, monkeypatch):
        # Route through the query_text collector (mocked) and let exact_match
        # score the collected rows — predicted == expected -> perfect score.
        rows = [
            Row(ROW_ID=1, EXPECTED="paris", PREDICTED="paris", question_col="?"),
            Row(ROW_ID=2, EXPECTED="rome", PREDICTED="rome", question_col="?"),
        ]
        monkeypatch.setattr(
            ev,
            "_collect_query_text_rows",
            lambda *a, **k: (["question_col"], None, {}, rows, None),
        )
        monkeypatch.setattr(ev, "validate_stage_file_access", lambda *a, **k: None)

        result = evaluate(
            object(),  # session unused after collection is mocked
            "",  # function_name ignored on the query_text path
            "db.sch.qa",
            ["question_col"],
            "expected_col",
            "exact_match",
            query_text="AI_COMPLETE('m', 'Answer: ' || question_col)",
        )
        assert result.score == 1.0
        assert len(result.details) == 2
        assert result.details[0]["predicted"] == "paris"
        assert result.details[0]["expected"] == "paris"

    def test_evaluate_query_text_empty_rows(self, monkeypatch):
        monkeypatch.setattr(
            ev, "_collect_query_text_rows", lambda *a, **k: ([], None, {}, [], None)
        )
        monkeypatch.setattr(ev, "validate_stage_file_access", lambda *a, **k: None)
        result = evaluate(
            object(),
            "",
            "db.sch.qa",
            [],
            "expected_col",
            "exact_match",
            query_text="AI_COMPLETE('m', c)",
        )
        assert result.score == 0.0
        assert result.details == []
