# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for evaluation metrics (metrics_core.py).

Tests run locally without a Snowflake connection. LLM-based metrics
mock RobustAIComplete to avoid network calls.

Run:
    uv run --group test pytest tests/test_metrics.py -v
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from snowflake_ai_optimize.core.metrics.builtin import (
    contains_match_core,
    exact_match_core,
    fuzzy_match_core,
    redaction_match_core,
)
from snowflake_ai_optimize.core.metrics.dispatch import (
    METRIC_ERROR_PREFIX,
    compute_metric,
    compute_metric_batch_resilient,
)
from snowflake_ai_optimize.core.metrics.llm_judge import (
    _LLM_JUDGE_BINARY_SCHEMA,
    _LLM_JUDGE_BINARY_TEMPLATE,
    _LLM_JUDGE_CONTINUOUS_SCHEMA,
    _LLM_JUDGE_CONTINUOUS_TEMPLATE,
    _LLM_JUDGE_USER_TEMPLATE,
    _parse_binary_result,
    _parse_continuous_result,
    llm_judge_batch,
    llm_judge_core,
)
from snowflake_ai_optimize.core.metrics.utils import to_text


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed for unit tests."""
    yield


MOCK_AI_COMPLETE = (
    "snowflake_ai_optimize.core.metrics.llm_judge.RobustAIComplete.call_ai_complete"
)


def _mock_ai(return_value):
    """Patch RobustAIComplete.call_ai_complete with a canned return value."""
    return patch(MOCK_AI_COMPLETE, return_value=return_value)


# ---------------------------------------------------------------------------
# Pure helpers: to_text
# ---------------------------------------------------------------------------


class TestToText:
    def test_none(self):
        assert to_text(None) == ""

    def test_string(self):
        assert to_text("hello") == "hello"

    def test_dict_sorted_keys(self):
        assert to_text({"b": 2, "a": 1}) == '{"a": 1, "b": 2}'

    def test_list(self):
        assert to_text([1, 2]) == "[1, 2]"

    def test_int(self):
        assert to_text(42) == "42"


# ---------------------------------------------------------------------------
# Built-in metrics: exact_match, fuzzy_match, contains_match
# ---------------------------------------------------------------------------


class TestExactMatch:
    def test_match(self):
        score, feedback = exact_match_core("good", "good")
        assert score == 1.0
        assert "Correct" in feedback

    def test_case_insensitive(self):
        assert exact_match_core("Good", "GOOD")[0] == 1.0

    def test_whitespace_trimmed(self):
        assert exact_match_core("  good  ", "good")[0] == 1.0

    def test_mismatch(self):
        score, feedback = exact_match_core("good", "fair")
        assert score == 0.0
        assert "good" in feedback and "fair" in feedback


class TestFuzzyMatch:
    def test_exact(self):
        assert fuzzy_match_core("hello world", "hello world")[0] == 1.0

    def test_close_enough(self):
        assert fuzzy_match_core("hello world", "hello worlD", threshold=0.85)[0] == 1.0

    def test_too_different(self):
        assert fuzzy_match_core("hello", "xyz", threshold=0.85)[0] == 0.0

    def test_custom_threshold(self):
        assert fuzzy_match_core("abc", "abd", threshold=0.5)[0] == 1.0


class TestContainsMatch:
    def test_contained(self):
        assert contains_match_core("good", "the answer is good")[0] == 1.0

    def test_not_contained(self):
        assert contains_match_core("excellent", "the answer is good")[0] == 0.0

    def test_case_insensitive(self):
        assert contains_match_core("Good", "GOOD job")[0] == 1.0


# ---------------------------------------------------------------------------
# Prompt templates and JSON schema
# ---------------------------------------------------------------------------


class TestPromptTemplates:
    def test_system_templates_have_task_description(self):
        # task_description is constant per batch, so it lives in the system
        # prompt (part of the cacheable prefix).
        assert "{task_description}" in _LLM_JUDGE_BINARY_TEMPLATE
        assert "{task_description}" in _LLM_JUDGE_CONTINUOUS_TEMPLATE

    def test_system_templates_have_no_per_row_placeholders(self):
        # Per-row fields must NOT appear in the system prompt, or the shared
        # prefix would change on every judged row.
        for tmpl in (_LLM_JUDGE_BINARY_TEMPLATE, _LLM_JUDGE_CONTINUOUS_TEMPLATE):
            assert "{expected}" not in tmpl
            assert "{predicted}" not in tmpl

    def test_user_template_has_per_row_placeholders(self):
        for key in ("expected", "predicted"):
            assert f"{{{key}}}" in _LLM_JUDGE_USER_TEMPLATE

    def test_binary_template_mentions_score_values(self):
        assert "1" in _LLM_JUDGE_BINARY_TEMPLATE
        assert "0" in _LLM_JUDGE_BINARY_TEMPLATE

    def test_continuous_template_mentions_score_range(self):
        assert "0.0" in _LLM_JUDGE_CONTINUOUS_TEMPLATE
        assert "1.0" in _LLM_JUDGE_CONTINUOUS_TEMPLATE

    def test_templates_are_formattable(self):
        for tmpl in (_LLM_JUDGE_BINARY_TEMPLATE, _LLM_JUDGE_CONTINUOUS_TEMPLATE):
            result = tmpl.format(task_description="test")
            assert "test" in result
        user = _LLM_JUDGE_USER_TEMPLATE.format(expected="a", predicted="b")
        assert "a" in user and "b" in user


class TestBinarySchema:
    def test_required_fields(self):
        assert set(_LLM_JUDGE_BINARY_SCHEMA["required"]) == {"score", "feedback"}

    def test_score_is_integer(self):
        assert _LLM_JUDGE_BINARY_SCHEMA["properties"]["score"]["type"] == "integer"

    def test_feedback_is_string(self):
        assert _LLM_JUDGE_BINARY_SCHEMA["properties"]["feedback"]["type"] == "string"

    def test_no_extra_properties(self):
        assert _LLM_JUDGE_BINARY_SCHEMA["additionalProperties"] is False


class TestContinuousSchema:
    def test_required_fields(self):
        assert set(_LLM_JUDGE_CONTINUOUS_SCHEMA["required"]) == {"score", "feedback"}

    def test_score_is_number(self):
        assert _LLM_JUDGE_CONTINUOUS_SCHEMA["properties"]["score"]["type"] == "number"

    def test_feedback_is_string(self):
        assert (
            _LLM_JUDGE_CONTINUOUS_SCHEMA["properties"]["feedback"]["type"] == "string"
        )

    def test_no_extra_properties(self):
        assert _LLM_JUDGE_CONTINUOUS_SCHEMA["additionalProperties"] is False


# ---------------------------------------------------------------------------
# Response parsers: _parse_binary_result, _parse_continuous_result
# ---------------------------------------------------------------------------


class TestParseBinaryResult:
    def test_correct(self):
        assert _parse_binary_result({"score": 1, "feedback": "good match"}) == (
            1.0,
            "good match",
        )

    def test_correct_from_json_string(self):
        assert _parse_binary_result('{"score": 1, "feedback": "ok"}') == (1.0, "ok")

    def test_incorrect(self):
        assert _parse_binary_result({"score": 0, "feedback": "wrong"}) == (0.0, "wrong")

    def test_none_treated_as_incorrect(self):
        assert _parse_binary_result(None)[0] == 0.0

    def test_threshold_at_half(self):
        assert _parse_binary_result({"score": 0.5, "feedback": "edge"}) == (1.0, "edge")
        assert _parse_binary_result({"score": 0.49, "feedback": "edge"}) == (
            0.0,
            "edge",
        )


class TestParseContinuousResult:
    @pytest.mark.parametrize(
        "raw, expected_score",
        [
            ({"score": 0.0, "feedback": "wrong"}, 0.0),
            ({"score": 0.25, "feedback": "off by 3"}, 0.25),
            ({"score": 0.5, "feedback": "off by 2"}, 0.5),
            ({"score": 0.75, "feedback": "off by 1"}, 0.75),
            ({"score": 1.0, "feedback": "exact"}, 1.0),
        ],
    )
    def test_valid_scores(self, raw, expected_score):
        assert _parse_continuous_result(raw)[0] == expected_score

    def test_extracts_feedback(self):
        _, feedback = _parse_continuous_result({"score": 0.5, "feedback": "half right"})
        assert feedback == "half right"

    def test_json_string_input(self):
        raw = json.dumps({"score": 0.5, "feedback": "half"})
        assert _parse_continuous_result(raw) == (0.5, "half")

    def test_clamps_above_one(self):
        assert _parse_continuous_result({"score": 1.5, "feedback": ""})[0] == 1.0

    def test_clamps_below_zero(self):
        assert _parse_continuous_result({"score": -0.3, "feedback": ""})[0] == 0.0

    def test_none_returns_zero(self):
        score, _ = _parse_continuous_result(None)
        assert score == 0.0

    def test_non_dict_returns_zero(self):
        assert _parse_continuous_result([1, 2])[0] == 0.0

    def test_missing_score_returns_zero(self):
        assert _parse_continuous_result({"feedback": "no score"})[0] == 0.0

    def test_missing_feedback_defaults_to_empty(self):
        assert _parse_continuous_result({"score": 0.8})[1] == ""

    def test_non_numeric_score(self):
        assert _parse_continuous_result({"score": "bad", "feedback": "x"})[0] == 0.0


# ---------------------------------------------------------------------------
# llm_judge_batch -- binary mode (default)
# ---------------------------------------------------------------------------


class TestLlmJudgeBatchBinary:
    def test_correct(self):
        with _mock_ai([{"score": 1, "feedback": "matches exactly"}]):
            results = llm_judge_batch([("good", "good")], session="fake")
        assert results == [(1.0, "matches exactly")]

    def test_incorrect(self):
        with _mock_ai([{"score": 0, "feedback": "completely wrong"}]):
            results = llm_judge_batch([("good", "poor")], session="fake")
        assert results[0][0] == 0.0

    def test_multiple_items(self):
        with _mock_ai(
            [
                {"score": 1, "feedback": "a"},
                {"score": 0, "feedback": "b"},
                {"score": 1, "feedback": "c"},
            ]
        ):
            scores = [
                r[0]
                for r in llm_judge_batch(
                    [("a", "a"), ("b", "c"), ("d", "d")],
                    session="fake",
                )
            ]
        assert scores == [1.0, 0.0, 1.0]

    def test_empty_items(self):
        assert llm_judge_batch([], session="fake") == []

    def test_uses_binary_schema(self):
        with _mock_ai([{"score": 1, "feedback": "ok"}]) as mock_call:
            llm_judge_batch([("a", "a")], session="fake")
            schema = mock_call.call_args.kwargs["response_schema"]
            assert schema["properties"]["score"]["type"] == "integer"

    def test_none_response_scored_zero(self):
        with _mock_ai([None]):
            assert llm_judge_batch([("a", "b")], session="fake")[0][0] == 0.0

    def test_multimodal_forwards_file_context(self):
        with _mock_ai([{"score": 1, "feedback": "ok"}]) as mock_call:
            llm_judge_batch(
                [("expected", "predicted")],
                session="fake",
                file_paths=["images/example.png"],
                stage_name="@DB.SCH.STAGE",
            )

        assert mock_call.call_args.kwargs["file_paths"] == ["images/example.png"]
        assert mock_call.call_args.kwargs["stage_name"] == "@DB.SCH.STAGE"
        # The file note is a static instruction → system prompt; the per-row
        # user prompt carries only Expected/Predicted.
        system_prompt = mock_call.call_args.kwargs["system_prompt"]
        assert "The attached file shows the actual input." in system_prompt
        assert "Expected: expected" in mock_call.call_args.kwargs["user_prompts"][0]

    def test_multimodal_rejects_length_mismatch(self):
        with pytest.raises(ValueError, match="must match items length"):
            llm_judge_batch(
                [("expected", "predicted"), ("expected-2", "predicted-2")],
                session="fake",
                file_paths=["images/example.png"],
                stage_name="@DB.SCH.STAGE",
            )


# ---------------------------------------------------------------------------
# llm_judge_batch -- continuous mode
# ---------------------------------------------------------------------------


class TestLlmJudgeBatchContinuous:
    def test_partial_credit(self):
        with _mock_ai([{"score": 0.75, "feedback": "off by one grade"}]):
            results = llm_judge_batch(
                [("good", "fair")],
                session="fake",
                scoring_mode="continuous",
            )
        assert results == [(0.75, "off by one grade")]

    def test_multiple_items(self):
        with _mock_ai(
            [
                {"score": 1.0, "feedback": "exact"},
                {"score": 0.5, "feedback": "off by two"},
                {"score": 0.0, "feedback": "wrong"},
            ]
        ):
            scores = [
                r[0]
                for r in llm_judge_batch(
                    [("a", "a"), ("b", "d"), ("e", "z")],
                    session="fake",
                    scoring_mode="continuous",
                )
            ]
        assert scores == [1.0, 0.5, 0.0]

    def test_passes_response_schema(self):
        with _mock_ai([{"score": 0.5, "feedback": "test"}]) as mock_call:
            llm_judge_batch([("a", "b")], session="fake", scoring_mode="continuous")
            assert (
                mock_call.call_args.kwargs["response_schema"]
                is _LLM_JUDGE_CONTINUOUS_SCHEMA
            )

    def test_clamps_out_of_range(self):
        with _mock_ai([{"score": 2.0, "feedback": "over"}]):
            assert (
                llm_judge_batch(
                    [("a", "a")],
                    session="fake",
                    scoring_mode="continuous",
                )[0][0]
                == 1.0
            )

    def test_empty_items(self):
        assert llm_judge_batch([], session="fake", scoring_mode="continuous") == []

    def test_null_response(self):
        with _mock_ai([None]):
            assert (
                llm_judge_batch(
                    [("a", "b")],
                    session="fake",
                    scoring_mode="continuous",
                )[0][0]
                == 0.0
            )

    def test_task_description_in_system_prompt(self):
        with _mock_ai([{"score": 0.5, "feedback": "ok"}]) as mock_call:
            llm_judge_batch(
                [("a", "b")],
                session="fake",
                task_description="Classify garment condition",
                scoring_mode="continuous",
            )
            # task_description is constant per batch → system prompt, not the
            # per-row user prompt (keeps the cached prefix stable across rows).
            assert (
                "Classify garment condition"
                in mock_call.call_args.kwargs["system_prompt"]
            )


# ---------------------------------------------------------------------------
# llm_judge_core
# ---------------------------------------------------------------------------


class TestLlmJudgeCore:
    def test_binary_by_default(self):
        with _mock_ai([{"score": 1, "feedback": "ok"}]):
            assert llm_judge_core("a", "a", session="fake")[0] == 1.0

    def test_continuous_passthrough(self):
        with _mock_ai([{"score": 0.75, "feedback": "close"}]):
            score, feedback = llm_judge_core(
                "good",
                "fair",
                session="fake",
                scoring_mode="continuous",
            )
        assert score == 0.75 and feedback == "close"

    def test_requires_session(self):
        with pytest.raises(ValueError, match="requires a session"):
            llm_judge_core("a", "b", session=None)


# ---------------------------------------------------------------------------
# compute_metric dispatch
# ---------------------------------------------------------------------------


class TestComputeMetricDispatch:
    def test_exact_match(self):
        assert compute_metric("exact_match", "good", "good")[0] == 1.0

    def test_fuzzy_match(self):
        assert compute_metric("fuzzy_match", "hello", "hello")[0] == 1.0

    def test_contains_match(self):
        assert compute_metric("contains_match", "yes", "yes indeed")[0] == 1.0

    def test_unknown_metric_raises(self):
        with pytest.raises(ValueError, match="Unknown metric"):
            compute_metric("nonexistent", "a", "b")

    def test_llm_judge_dispatches(self):
        with _mock_ai(["INCORRECT: wrong"]):
            assert compute_metric("llm_judge", "a", "b", session="fake")[0] == 0.0


# ---------------------------------------------------------------------------
# Built-in metrics: redaction_match
# ---------------------------------------------------------------------------


class TestRedactionMatch:
    """Tests for redaction_match_core."""

    def test_exact_match_no_brackets(self):
        score, _ = redaction_match_core("Hello world", "Hello world")
        assert score == 1.0

    def test_exact_match_with_brackets(self):
        score, _ = redaction_match_core(
            "Hello [USERNAME], your ID is [ID]",
            "Hello [John], your ID is [12345]",
        )
        assert score == 1.0

    def test_mismatch_outside_brackets(self):
        score, _ = redaction_match_core("Hello world", "Goodbye world")
        assert score == 0.0

    def test_multiple_bracket_regions(self):
        score, _ = redaction_match_core(
            "[A] and [B] and [C]",
            "[X] and [Y] and [Z]",
        )
        assert score == 1.0

    def test_preamble_detected(self):
        # Predicted has extra text at the beginning
        score, feedback = redaction_match_core(
            "The answer is 42.",
            "Here is the result: The answer is 42.",
        )
        assert score == 0.0
        assert "preamble" in feedback.lower() or "prefix" in feedback.lower()

    def test_postamble_detected(self):
        # Predicted has extra text at the end
        score, feedback = redaction_match_core(
            "The answer is 42.",
            "The answer is 42. I hope this helps!",
        )
        assert score == 0.0
        assert "postamble" in feedback.lower() or "suffix" in feedback.lower()

    def test_missed_redaction(self):
        # Expected has bracket where predicted has literal text
        score, feedback = redaction_match_core(
            "Hello [REDACTED], welcome",
            "Hello John Smith, welcome",
        )
        assert score == 0.0
        assert "missed redaction" in feedback.lower() or "redact" in feedback.lower()

    def test_over_redaction(self):
        # Predicted has bracket where expected has literal text
        score, feedback = redaction_match_core(
            "Hello John, welcome",
            "Hello [REDACTED], welcome",
        )
        assert score == 0.0
        assert (
            "over-redact" in feedback.lower()
            or "redacted something" in feedback.lower()
        )

    def test_empty_strings(self):
        score, _ = redaction_match_core("", "")
        assert score == 1.0

    def test_whitespace_only(self):
        score, _ = redaction_match_core("  ", "  ")
        assert score == 1.0


class TestRedactionMatchDispatch:
    """Test compute_metric dispatch for redaction_match."""

    def test_dispatch_works(self):
        score, _ = compute_metric("redaction_match", "hello", "hello")
        assert score == 1.0


# ---------------------------------------------------------------------------
# compute_metric_batch_resilient -- a batch failure must not zero every row
# (§3.3: isolate the EVALUATE metric batch)
# ---------------------------------------------------------------------------


class TestComputeMetricBatchResilient:
    def test_passthrough_on_success(self):
        # Happy path: delegates to compute_metric_batch, no per-row fallback.
        items = [("hello", "hello"), ("world", "nope")]
        results = compute_metric_batch_resilient("exact_match", items)
        assert results == [(1.0, results[0][1]), (0.0, results[1][1])]

    def test_batch_failure_falls_back_per_row(self):
        # Whole-batch call blows up (e.g. judge count mismatch); per-row
        # scoring recovers the good row instead of aborting the run.
        items = [("hello", "hello"), ("world", "world")]
        with patch(
            "snowflake_ai_optimize.core.metrics.dispatch.compute_metric_batch",
            side_effect=RuntimeError("count mismatch"),
        ):
            results = compute_metric_batch_resilient("exact_match", items)
        assert [s for s, _ in results] == [1.0, 1.0]

    def test_per_row_failure_degrades_that_row_only(self):
        # Batch fails AND one row's per-row scoring also raises -> that row
        # degrades to (0.0, feedback); the other row still scores.
        items = [("a", "a"), ("b", "b")]

        def flaky(_metric, expected, _pred, *_a, **_k):
            if expected == "b":
                raise ValueError("boom")
            return (1.0, "ok")

        with (
            patch(
                "snowflake_ai_optimize.core.metrics.dispatch.compute_metric_batch",
                side_effect=RuntimeError("batch down"),
            ),
            patch(
                "snowflake_ai_optimize.core.metrics.dispatch.compute_metric",
                side_effect=flaky,
            ),
        ):
            results = compute_metric_batch_resilient("exact_match", items)
        assert results[0] == (1.0, "ok")
        assert results[1][0] == 0.0
        assert "boom" in results[1][1]

    def test_failed_row_feedback_is_tagged_for_surfacing(self):
        # A thrown row is tagged with METRIC_ERROR_PREFIX so the evaluator can
        # route it to the per-row error_message field (uniform across metrics),
        # not just the metric-dependent metric_feedback.
        items = [("a", "a")]
        with (
            patch(
                "snowflake_ai_optimize.core.metrics.dispatch.compute_metric_batch",
                side_effect=RuntimeError("batch down"),
            ),
            patch(
                "snowflake_ai_optimize.core.metrics.dispatch.compute_metric",
                side_effect=ValueError("boom"),
            ),
        ):
            (score, feedback) = compute_metric_batch_resilient("exact_match", items)[0]
        assert score == 0.0
        assert feedback.startswith(METRIC_ERROR_PREFIX)
