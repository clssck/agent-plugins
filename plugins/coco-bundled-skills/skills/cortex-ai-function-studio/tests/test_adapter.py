# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for snow_gepa_adapter.py — DatasetResult, load_dataset, Evaluator.

Run:
    uv run --group test pytest tests/test_adapter.py -v
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from snowflake_ai_optimize.core.scorer import Evaluator, ScoredExample
from snowflake_ai_optimize.core.timing import (
    TimingTracker,
    _percentile,
    clear_evaluate_hooks,
    get_active_tracker,
    set_active_tracker,
    set_evaluate_hooks,
)
from snowflake_ai_optimize.gepa import adapter
from snowflake_ai_optimize.gepa.adapter import (
    DatasetResult,
    SnowflakeLLM,
    load_dataset,
)


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed for unit tests."""
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeRow:
    """Mimics a Snowpark Row supporting dict-style access."""

    def __init__(self, data: dict):
        self._data = {k.upper(): v for k, v in data.items()}

    def __getitem__(self, key):
        return self._data[key.upper()]


def _make_session(rows: list[dict]) -> MagicMock:
    """Return a mock Snowpark session whose .sql().collect() yields *rows*."""
    fake_rows = [FakeRow(r) for r in rows]
    session = MagicMock()
    session.sql.return_value.collect.return_value = fake_rows
    return session


# ---------------------------------------------------------------------------
# DatasetResult
# ---------------------------------------------------------------------------


class TestDatasetResult:
    def test_empty_is_falsy(self):
        result = DatasetResult(dataset=[])
        assert not result
        assert len(result) == 0

    def test_non_empty_is_truthy(self):
        result = DatasetResult(dataset=[{"inputs": {}, "answer": "a"}])
        assert result
        assert len(result) == 1

    def test_file_stage_name_stored(self):
        result = DatasetResult(
            dataset=[], file_stage_name="@my_stage", file_columns=["IMG"]
        )
        assert result.file_stage_name == "@my_stage"
        assert result.file_columns == ["IMG"]

    def test_file_columns_defaults_to_empty_list(self):
        result = DatasetResult(dataset=[], file_columns=None)
        assert result.file_columns == []


# ---------------------------------------------------------------------------
# load_dataset
# ---------------------------------------------------------------------------


class TestLoadDataset:
    """All helpers that touch Snowflake are patched at the snow_gepa_adapter level."""

    @patch("snowflake_ai_optimize.gepa.adapter.validate_input_columns")
    @patch(
        "snowflake_ai_optimize.gepa.adapter.get_table_column_names",
        return_value={"Q", "ANSWER"},
    )
    @patch("snowflake_ai_optimize.gepa.adapter.parse_file_value", return_value=None)
    def test_basic_load(self, _pf, _gcn, _vic):
        session = _make_session(
            [
                {"Q": "What is 2+2?", "ANSWER": "4"},
                {"Q": "Capital of France?", "ANSWER": "Paris"},
            ]
        )
        result = load_dataset(session, "DB.S.T", ["Q"], "ANSWER")
        assert len(result) == 2
        assert result.dataset[0]["inputs"]["Q"] == "What is 2+2?"
        assert result.dataset[0]["answer"] == "4"
        assert result.dataset[1]["answer"] == "Paris"

    @patch("snowflake_ai_optimize.gepa.adapter.validate_input_columns")
    @patch(
        "snowflake_ai_optimize.gepa.adapter.get_table_column_names",
        return_value={"Q", "ANSWER"},
    )
    @patch("snowflake_ai_optimize.gepa.adapter.parse_file_value", return_value=None)
    def test_none_value_becomes_empty_string(self, _pf, _gcn, _vic):
        session = _make_session([{"Q": None, "ANSWER": "x"}])
        result = load_dataset(session, "DB.S.T", ["Q"], "ANSWER")
        assert result.dataset[0]["inputs"]["Q"] == ""

    @patch("snowflake_ai_optimize.gepa.adapter.validate_input_columns")
    @patch(
        "snowflake_ai_optimize.gepa.adapter.get_table_column_names",
        return_value={"Q", "ANSWER"},
    )
    @patch("snowflake_ai_optimize.gepa.adapter.parse_file_value", return_value=None)
    def test_json_array_string_parsed(self, _pf, _gcn, _vic):
        session = _make_session([{"Q": '["a", "b"]', "ANSWER": "x"}])
        result = load_dataset(session, "DB.S.T", ["Q"], "ANSWER")
        assert result.dataset[0]["inputs"]["Q"] == ["a", "b"]

    @patch("snowflake_ai_optimize.gepa.adapter.validate_input_columns")
    @patch(
        "snowflake_ai_optimize.gepa.adapter.get_table_column_names",
        return_value={"COL1", "ANSWER"},
    )
    @patch("snowflake_ai_optimize.gepa.adapter.parse_file_value", return_value=None)
    def test_input_arg_names_aliases_and_rekeys(self, _pf, _gcn, _vic):
        # With argument binding the SELECT aliases each column to its parameter
        # name and the row's inputs dict is keyed by the parameter name.
        session = _make_session([{"arg1": "hello", "ANSWER": "x"}])
        result = load_dataset(
            session, "DB.S.T", ["col1"], "ANSWER", input_arg_names=["arg1"]
        )
        query = session.sql.call_args[0][0]
        assert '"col1" AS "arg1"' in query
        assert result.dataset[0]["inputs"]["arg1"] == "hello"
        assert "col1" not in result.dataset[0]["inputs"]

    @patch("snowflake_ai_optimize.gepa.adapter.validate_input_columns")
    @patch(
        "snowflake_ai_optimize.gepa.adapter.get_table_column_names",
        return_value={"IMG", "ANSWER"},
    )
    def test_file_variant_detection(self, _gcn, _vic):
        """parse_file_value returns a tuple → stage key injected into inputs."""
        with patch(
            "snowflake_ai_optimize.gepa.adapter.parse_file_value",
            return_value=("@DB.S.MY_STAGE", "images/cat.jpg"),
        ):
            session = _make_session(
                [
                    {
                        "IMG": '{"STAGE":"@DB.S.MY_STAGE","RELATIVE_PATH":"images/cat.jpg"}',
                        "ANSWER": "cat",
                    },
                ]
            )
            result = load_dataset(session, "DB.S.T", ["IMG"], "ANSWER")

        inst = result.dataset[0]
        assert inst["inputs"]["IMG"] == "images/cat.jpg"
        assert inst["inputs"]["__STAGE_IMG"] == "@DB.S.MY_STAGE"
        assert result.file_stage_name == "@DB.S.MY_STAGE"
        assert result.file_columns == ["IMG"]


# ---------------------------------------------------------------------------
# Evaluator.__call__
# ---------------------------------------------------------------------------


class TestEvaluatorCall:
    def test_exact_match_correct(self):
        evaluator = Evaluator("exact_match")
        result = evaluator({"inputs": {"Q": "hi"}, "answer": "hello"}, "hello")
        assert isinstance(result, ScoredExample)
        assert result.score == 1.0

    def test_exact_match_mismatch(self):
        evaluator = Evaluator("exact_match")
        result = evaluator({"inputs": {"Q": "hi"}, "answer": "hello"}, "world")
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# Evaluator.evaluate_batch
# ---------------------------------------------------------------------------


class TestEvaluateBatch:
    def test_empty_items(self):
        evaluator = Evaluator("exact_match")
        assert evaluator.evaluate_batch([]) == []

    @patch("snowflake_ai_optimize.core.scorer.compute_metric_batch")
    def test_returns_evaluation_results(self, mock_batch):
        mock_batch.return_value = [(1.0, "ok"), (0.0, "wrong")]
        evaluator = Evaluator("exact_match")
        items = [
            ({"inputs": {"Q": "q1"}, "answer": "a"}, "a"),
            ({"inputs": {"Q": "q2"}, "answer": "b"}, "c"),
        ]
        results = evaluator.evaluate_batch(items)
        assert len(results) == 2
        assert results[0].score == 1.0
        assert results[0].feedback == "ok"
        assert results[1].score == 0.0

    @patch("snowflake_ai_optimize.core.scorer.compute_classification_objectives")
    @patch("snowflake_ai_optimize.core.scorer.compute_metric_batch")
    def test_aggregation_metric_overrides_scores(self, mock_batch, mock_cls):
        mock_batch.return_value = [(1.0, "ok"), (0.0, "wrong")]
        mock_cls.return_value = {"f1-score": 0.75, "accuracy": 0.8}

        evaluator = Evaluator("exact_match", aggregation_metric="f1-score")
        items = [
            ({"inputs": {"Q": "q1"}, "answer": "a"}, "a"),
            ({"inputs": {"Q": "q2"}, "answer": "b"}, "c"),
        ]
        results = evaluator.evaluate_batch(items)
        # All scores should be overridden to the f1-score value
        assert all(r.score == 0.75 for r in results)
        assert all(
            r.objective_scores == {"f1-score": 0.75, "accuracy": 0.8} for r in results
        )

    @patch("snowflake_ai_optimize.core.scorer.compute_classification_objectives")
    @patch("snowflake_ai_optimize.core.scorer.compute_metric_batch")
    def test_aggregation_metric_accuracy_no_override(self, mock_batch, mock_cls):
        """When aggregation_metric='accuracy', scores are NOT overridden."""
        mock_batch.return_value = [(1.0, "ok"), (0.0, "wrong")]
        mock_cls.return_value = {"f1-score": 0.75, "accuracy": 0.8}

        evaluator = Evaluator("exact_match", aggregation_metric="accuracy")
        items = [
            ({"inputs": {"Q": "q1"}, "answer": "a"}, "a"),
            ({"inputs": {"Q": "q2"}, "answer": "b"}, "c"),
        ]
        results = evaluator.evaluate_batch(items)
        # accuracy is special-cased: original scores preserved
        assert results[0].score == 1.0
        assert results[1].score == 0.0
        # but objective_scores still populated
        assert results[0].objective_scores == {"f1-score": 0.75, "accuracy": 0.8}


# ---------------------------------------------------------------------------
# TimingTracker
# ---------------------------------------------------------------------------


class TestTimingTrackerAccumulation:
    def test_add_metric_accumulates(self):
        t = TimingTracker()
        t.add_metric(0.5)
        t.add_metric(1.5)
        assert t.total_metric_calls == 2
        assert t.total_metric_seconds == pytest.approx(2.0)

    def test_add_reflection_accumulates(self):
        t = TimingTracker()
        t.add_reflection(0.25)
        t.add_reflection(0.75)
        assert t.total_reflection_calls == 2
        assert t.total_reflection_seconds == pytest.approx(1.0)

    def test_add_udf_compile_and_exec_independent(self):
        t = TimingTracker()
        t.add_udf_compile(0.4)
        t.add_udf_exec(2.0)
        t.add_udf_exec(3.0)
        assert t.total_udf_compile_calls == 1
        assert t.total_udf_compile_seconds == pytest.approx(0.4)
        assert t.total_udf_exec_calls == 2
        assert t.total_udf_exec_seconds == pytest.approx(5.0)

    def test_add_experiment_and_artifact(self):
        t = TimingTracker()
        t.add_experiment(0.1, label="add_run")
        t.add_experiment(0.2, label="commit")
        t.add_artifact_upload(0.5, label="run_dir")
        assert t.total_experiment_calls == 2
        assert t.total_experiment_seconds == pytest.approx(0.3)
        assert t.total_artifact_calls == 1
        assert t.total_artifact_seconds == pytest.approx(0.5)

    def test_add_metric_batch_records_one_event_spanning_full_window(self):
        # Regression: previously evaluate_batch pushed N events all stamped
        # at ``end_perf`` (with width per_item), collapsing the whole batch
        # into a microsecond-wide cluster on the Gantt chart and leaving
        # the actual SQL window blank.  ``add_metric_batch`` must instead
        # push exactly ONE event spanning ``[start_perf, end_perf]`` while
        # still appending N copies of ``per_item`` to ``metric_durations``.
        t = TimingTracker()
        # Use perf_counter() so the event timestamps are realistic; the
        # test asserts on durations / counts, not absolute values.
        start = time.perf_counter()
        end = start + 8.85
        t.add_metric_batch(start, end, 53)

        # Per-call accounting unchanged (53 entries summing to wall time).
        assert t.total_metric_calls == 53
        assert t.total_metric_seconds == pytest.approx(8.85, rel=1e-6)

        # Exactly one timeline event, spanning the full SQL window.
        events = [e for e in t.export_events() if e["type"] == "metric"]
        assert len(events) == 1
        evt = events[0]
        span_seconds = (evt["end_ms"] - evt["start_ms"]) / 1000.0
        assert span_seconds == pytest.approx(8.85, rel=1e-6)
        # Label disambiguates a 1-item degenerate batch from a real one.
        assert evt["label"] == "batch_x53"

    def test_add_metric_batch_zero_items_is_noop(self):
        t = TimingTracker()
        now = time.perf_counter()
        t.add_metric_batch(now, now + 1.0, 0)
        assert t.total_metric_calls == 0
        assert t.export_events() == []

    def test_add_metric_batch_single_item_still_uses_real_window(self):
        # A batch of 1 still gets one event spanning [start, end] — no
        # special-casing.  This guards against a future "if N == 1, fall
        # back to add_metric" regression that would re-introduce the
        # zero-width-event bug at the bottom of the Gantt chart.
        t = TimingTracker()
        start = time.perf_counter()
        end = start + 0.5
        t.add_metric_batch(start, end, 1)
        events = [e for e in t.export_events() if e["type"] == "metric"]
        assert len(events) == 1
        span_seconds = (events[0]["end_ms"] - events[0]["start_ms"]) / 1000.0
        assert span_seconds == pytest.approx(0.5, rel=1e-6)

    def test_add_metric_batch_per_iteration_window_unchanged(self):
        # The per-iteration view (per_iteration_stats) slices
        # ``metric_durations`` between iteration boundaries.  A 50-item
        # batch must show as ``metric_call_count = 50`` in the iter that
        # contained it, exactly like 50 sequential add_metric() calls
        # would have — otherwise the BENCH_TRACKING_DETAILS rows for an
        # llm_judge scenario would lose their per-iter call counts.
        t = TimingTracker()
        # Iteration 0: a single 50-item batch.
        now = time.perf_counter()
        t.add_metric_batch(now, now + 5.0, 50)
        t.mark_iteration()
        # Iteration 1: a 30-item batch.
        now2 = time.perf_counter()
        t.add_metric_batch(now2, now2 + 3.0, 30)
        t.mark_iteration()

        stats = t.per_iteration_stats()
        assert len(stats) == 2
        assert stats[0].metric_call_count == 50
        assert stats[0].metric_seconds_total == pytest.approx(5.0)
        # Avg / p95 are per-item — every item in a batch shares the same
        # per_item duration, so avg == per_item == 0.1.
        assert stats[0].metric_seconds_avg == pytest.approx(5.0 / 50)
        assert stats[1].metric_call_count == 30
        assert stats[1].metric_seconds_total == pytest.approx(3.0)


class TestEvaluateBatchTrackerIntegration:
    """Regression: the llm_judge Gantt collapse bug surfaced because
    ``Evaluator.evaluate_batch`` pushed N tracker events all stamped at
    end_perf instead of one event spanning [start, end].  These tests
    pin the integrated path so the bug can't sneak back in via a
    refactor of either side.
    """  # noqa: D205

    @patch("snowflake_ai_optimize.core.scorer.compute_metric_batch")
    def test_evaluate_batch_records_one_event_for_full_window(self, mock_batch):
        from snowflake_ai_optimize.core.timing import set_active_tracker

        # Simulate a slow batched SQL call so the [start, end] window is
        # observably wider than the per-item duration.  Without the fix,
        # the tracker would record 10 events of 0.005s each clustered
        # at end_perf, leaving ~50ms of blank space on the Gantt chart.
        def slow_batch(metric_name, items, *args, **kwargs):
            time.sleep(0.05)
            return [(0.5, "ok")] * len(items)

        mock_batch.side_effect = slow_batch

        tracker = TimingTracker()
        set_active_tracker(tracker)
        try:
            evaluator = Evaluator("llm_judge", session=None)
            items = [
                ({"inputs": {"x": str(i)}, "answer": str(i)}, str(i)) for i in range(10)
            ]
            evaluator.evaluate_batch(items)
        finally:
            set_active_tracker(None)

        metric_events = [e for e in tracker.export_events() if e["type"] == "metric"]
        # ONE event for the whole batch — not 10.  This is the property
        # the user reported as missing on the Gantt chart.
        assert len(metric_events) == 1
        span_seconds = (
            metric_events[0]["end_ms"] - metric_events[0]["start_ms"]
        ) / 1000.0
        # Span must cover at least the simulated batch wall time (50ms).
        # Use a generous lower bound to absorb scheduler jitter.
        assert span_seconds >= 0.045
        assert metric_events[0]["label"] == "batch_x10"

        # Per-item totals unchanged: 10 entries, all equal to per_item.
        assert tracker.total_metric_calls == 10
        assert tracker.total_metric_seconds == pytest.approx(span_seconds, rel=1e-3)

    @patch("snowflake_ai_optimize.core.scorer.compute_metric_batch")
    def test_evaluate_batch_empty_items_emits_no_event(self, mock_batch):
        from snowflake_ai_optimize.core.timing import set_active_tracker

        # Defence-in-depth: empty batch must not push a degenerate
        # zero-width event.  ``evaluate_batch`` short-circuits before
        # hitting the tracker, but the assertion guards against a
        # future refactor that drops the early-return.
        mock_batch.return_value = []
        tracker = TimingTracker()
        set_active_tracker(tracker)
        try:
            Evaluator("llm_judge", session=None).evaluate_batch([])
        finally:
            set_active_tracker(None)
        assert tracker.export_events() == []
        assert tracker.total_metric_calls == 0


class TestPerIterationStats:
    def test_deltas_between_boundaries(self):
        t = TimingTracker()
        # Iteration 0: 2 metric calls, 1 reflection
        t.add_metric(0.1)
        t.add_metric(0.3)
        t.add_reflection(1.0)
        t.mark_iteration()
        # Iteration 1: 1 metric call, 0 reflections
        t.add_metric(0.5)
        t.mark_iteration()

        stats = t.per_iteration_stats()
        assert len(stats) == 2

        assert stats[0].iter_index == 0
        assert stats[0].metric_call_count == 2
        assert stats[0].metric_seconds_total == pytest.approx(0.4)
        assert stats[0].metric_seconds_avg == pytest.approx(0.2)
        assert stats[0].reflection_call_count == 1
        assert stats[0].reflection_seconds_total == pytest.approx(1.0)

        assert stats[1].iter_index == 1
        assert stats[1].metric_call_count == 1
        assert stats[1].metric_seconds_total == pytest.approx(0.5)
        assert stats[1].reflection_call_count == 0
        assert stats[1].reflection_seconds_total == 0.0

    def test_no_iterations_returns_empty(self):
        t = TimingTracker()
        assert t.per_iteration_stats() == []

    def test_p95_within_iteration(self):
        t = TimingTracker()
        for d in (0.1, 0.2, 0.3, 0.4, 0.5):
            t.add_metric(d)
        t.mark_iteration()
        stats = t.per_iteration_stats()
        # _percentile uses idx = round(0.95 * (5 - 1)) = round(3.8) = 4 → 0.5.
        assert stats[0].metric_seconds_p95 == pytest.approx(0.5)


class TestTokenTracking:
    """Per-call token capture + per-iteration aggregates (added 2026-05).

    These exercise the new ``add_udf_exec`` / ``add_reflection`` keyword
    arguments and the resulting ``IterationStats`` token fields.  The
    token Gantt in ``plot_html.py`` and the new
    ``iter_eval_*`` / ``iter_reflection_*_est`` columns in
    BENCH_TRACKING_DETAILS both rely on this plumbing producing accurate
    per-call and per-iteration counts; regressions here would silently
    zero those out without raising any error.
    """

    def test_udf_exec_records_token_event(self):
        t = TimingTracker()
        t.add_udf_exec(
            0.5,
            prompt_tokens=120,
            completion_tokens=30,
            input_chars=480,
            output_chars=120,
            model="claude-haiku-4-5",
        )
        events = [e for e in t.export_events() if e["type"] == "udf_exec"]
        assert len(events) == 1
        evt = events[0]
        assert evt["prompt_tokens"] == 120
        assert evt["completion_tokens"] == 30
        assert evt["input_chars"] == 480
        assert evt["output_chars"] == 120
        assert evt["model"] == "claude-haiku-4-5"
        assert evt["token_source"] == "real"
        # Per-call token tuple is stashed for per_iteration_stats.
        assert t.udf_exec_tokens == [(120, 30)]

    def test_reflection_records_char_estimated_token_event(self):
        t = TimingTracker()
        t.add_reflection(
            1.2,
            prompt_tokens=400,
            completion_tokens=80,
            input_chars=1600,
            output_chars=320,
            model="claude-opus-4-6",
        )
        events = [e for e in t.export_events() if e["type"] == "reflection"]
        assert len(events) == 1
        evt = events[0]
        assert evt["prompt_tokens"] == 400
        assert evt["completion_tokens"] == 80
        # Reflection always reports as char-est since show_details=False
        # for the AI_COMPLETE call.  The renderer uses this to label
        # the tooltip.
        assert evt["token_source"] == "char_est"
        assert t.reflection_tokens == [(400, 80)]

    def test_token_args_are_optional(self):
        # Old call sites (e.g. cleanup paths that don't compute token
        # diffs) must keep working without raising.  ``token_source``
        # stays unset when neither prompt nor completion is provided so
        # the renderer can reliably skip these events from the token
        # Gantt without misclassifying them.
        t = TimingTracker()
        t.add_udf_exec(0.1)
        t.add_reflection(0.2)
        events = t.export_events()
        for e in events:
            assert "prompt_tokens" not in e
            assert "completion_tokens" not in e
            assert "token_source" not in e
        # Per-call token lists still tick to keep alignment with the
        # _durations lists; missing fields land as (0, 0).
        assert t.udf_exec_tokens == [(0, 0)]
        assert t.reflection_tokens == [(0, 0)]

    def test_per_iteration_stats_split_eval_vs_reflection_tokens(self):
        t = TimingTracker()
        # Iteration 0: parent-eval (real tokens) + reflection (estimated).
        t.add_udf_exec(0.1, prompt_tokens=200, completion_tokens=50, model="m")
        t.add_reflection(0.2, prompt_tokens=400, completion_tokens=80, model="r")
        # Then new-cand-eval on the same iteration (real tokens).
        t.add_udf_exec(0.1, prompt_tokens=300, completion_tokens=70, model="m")
        t.mark_iteration()
        # Iteration 1: just one eval, no reflection.
        t.add_udf_exec(0.1, prompt_tokens=150, completion_tokens=20, model="m")
        t.mark_iteration()

        stats = t.per_iteration_stats()
        assert len(stats) == 2

        # Iteration 0: eval = 200+300 / 50+70, reflection = 400 / 80.
        assert stats[0].udf_prompt_tokens == 500
        assert stats[0].udf_completion_tokens == 120
        assert stats[0].reflection_prompt_tokens_est == 400
        assert stats[0].reflection_completion_tokens_est == 80

        # Iteration 1: only one eval, no reflection.
        assert stats[1].udf_prompt_tokens == 150
        assert stats[1].udf_completion_tokens == 20
        assert stats[1].reflection_prompt_tokens_est == 0
        assert stats[1].reflection_completion_tokens_est == 0

    def test_total_reflection_token_estimates_use_chars_div_4(self):
        t = TimingTracker()
        # add_chars is the canonical way reflection chars enter the
        # tracker; matches what SnowflakeLLM.__call__ does in production.
        t.add_chars("opus", "reflection", input_chars=4000, output_chars=800)
        t.add_chars("opus", "reflection", input_chars=2000, output_chars=400)
        # UDF chars must NOT contribute to reflection totals.
        t.add_chars("haiku", "udf", input_chars=10_000, output_chars=2_000)

        assert t.total_reflection_prompt_tokens_est == (4000 + 2000) // 4
        assert t.total_reflection_completion_tokens_est == (800 + 400) // 4


class TestPercentile:
    def test_empty_returns_zero(self):
        assert _percentile([], 0.95) == 0.0

    def test_single_value(self):
        assert _percentile([0.42], 0.5) == pytest.approx(0.42)
        assert _percentile([0.42], 0.0) == pytest.approx(0.42)
        assert _percentile([0.42], 1.0) == pytest.approx(0.42)

    def test_q_zero_returns_min(self):
        assert _percentile([3.0, 1.0, 2.0], 0.0) == pytest.approx(1.0)

    def test_q_one_returns_max(self):
        assert _percentile([3.0, 1.0, 2.0], 1.0) == pytest.approx(3.0)

    def test_q_half_returns_median_for_odd_count(self):
        # idx = round(0.5 * (5 - 1)) = 2 → sorted[2] = 3.0
        assert _percentile([5.0, 3.0, 1.0, 4.0, 2.0], 0.5) == pytest.approx(3.0)


class TestEventCap:
    def test_phase_events_kept_when_fine_events_overflow(self):
        t = TimingTracker()
        t._max_metric_events = 4
        # Replace the bounded deque so the smaller cap takes effect.
        from collections import deque

        t._metric_events = deque(maxlen=t._max_metric_events)

        # Two coarse phase events that must survive the deluge.
        now = time.perf_counter()
        t.add_phase("gepa_loop", now, now + 1.0, label="m")
        t.add_phase("test_eval", now + 1.0, now + 1.5, label="m")

        for _ in range(20):
            t.add_metric(0.001)

        events = t.export_events()
        types = [e["type"] for e in events]
        assert types.count("gepa_loop") == 1
        assert types.count("test_eval") == 1
        assert types.count("metric") == t._max_metric_events

    def test_export_events_chronological(self):
        t = TimingTracker()
        # Manually push out-of-order epoch_ms events to verify export sorts them.
        t._phase_events.append(
            {
                "type": "gepa_loop",
                "start_ms": 200.0,
                "end_ms": 300.0,
                "thread_id": 1,
                "label": "x",
            }
        )
        t._metric_events.append(
            {
                "type": "metric",
                "start_ms": 100.0,
                "end_ms": 110.0,
                "thread_id": 1,
                "label": "",
            }
        )
        events = t.export_events()
        assert [e["start_ms"] for e in events] == [100.0, 200.0]


class TestThreadSafety:
    def test_concurrent_add_metric_no_loss(self):
        import threading as _threading

        t = TimingTracker()
        n_threads = 8
        per_thread = 200

        def worker():
            for _ in range(per_thread):
                t.add_metric(0.001)

        threads = [_threading.Thread(target=worker) for _ in range(n_threads)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert t.total_metric_calls == n_threads * per_thread
        # Every duration was 0.001 → total ≈ n*per*0.001.
        assert t.total_metric_seconds == pytest.approx(n_threads * per_thread * 0.001)


# ---------------------------------------------------------------------------
# Thread-local active tracker + evaluate hooks
# ---------------------------------------------------------------------------


class TestActiveTracker:
    def teardown_method(self):
        set_active_tracker(None)

    def test_set_and_get(self):
        t = TimingTracker()
        set_active_tracker(t)
        assert get_active_tracker() is t

    def test_clear(self):
        set_active_tracker(TimingTracker())
        set_active_tracker(None)
        assert get_active_tracker() is None

    def test_isolated_per_thread(self):
        import threading as _threading

        main_tracker = TimingTracker()
        set_active_tracker(main_tracker)
        observed: dict = {}

        def worker():
            # Sibling thread starts with no tracker bound.
            observed["before"] = get_active_tracker()
            sibling = TimingTracker()
            set_active_tracker(sibling)
            observed["after_set"] = get_active_tracker()

        th = _threading.Thread(target=worker)
        th.start()
        th.join()

        assert observed["before"] is None
        assert observed["after_set"] is not main_tracker
        # Main thread's binding survived the sibling's set_active_tracker.
        assert get_active_tracker() is main_tracker


class TestEvaluateHooks:
    def teardown_method(self):
        clear_evaluate_hooks()

    def test_set_clear_hooks(self):
        from snowflake_ai_optimize.core.timing import _get_evaluate_hooks

        pre_called = []
        post_called = []
        set_evaluate_hooks(
            pre=lambda: pre_called.append(1),
            post=lambda: post_called.append(1),
        )
        pre, post = _get_evaluate_hooks()
        assert pre is not None and post is not None
        pre()
        post()
        assert pre_called == [1] and post_called == [1]

        clear_evaluate_hooks()
        pre2, post2 = _get_evaluate_hooks()
        assert pre2 is None and post2 is None

    def test_hooks_isolated_per_thread(self):
        import threading as _threading

        from snowflake_ai_optimize.core.timing import _get_evaluate_hooks

        main_pre = lambda: None
        set_evaluate_hooks(pre=main_pre, post=None)

        sibling_observed: dict = {}

        def worker():
            sibling_observed["before"] = _get_evaluate_hooks()
            set_evaluate_hooks(pre=lambda: None, post=lambda: None)
            sibling_observed["after_set"] = _get_evaluate_hooks()

        th = _threading.Thread(target=worker)
        th.start()
        th.join()

        # Sibling started with no hooks bound on its thread-local slot.
        assert sibling_observed["before"] == (None, None)
        # Sibling's bind didn't leak back into the main thread.
        main_pre_after, _ = _get_evaluate_hooks()
        assert main_pre_after is main_pre


# ---------------------------------------------------------------------------
# SnowflakeLLM reflection retry + error capture
# ---------------------------------------------------------------------------


class TestSnowflakeLLMReflectionRetry:
    """The reflection LM's retry / error-capture behavior.

    Defaults (``max_attempts=1``, ``error_sink=None``) must reproduce the
    original single-attempt behavior exactly; the spec-driven path opts in to
    retries + an ``error_sink`` so a persistently failing reflection call is
    observable after the GEPA loop instead of being silently swallowed.
    """

    def _lm(self) -> SnowflakeLLM:
        return SnowflakeLLM(
            session=MagicMock(), model="claude-opus-4-7", temperature=0.0, max_tokens=64
        )

    def test_default_is_single_attempt_and_reraises(self):
        """Default: one attempt, no capture, re-raise — byte-identical to before."""
        lm = self._lm()
        with (
            patch.object(
                adapter.RobustAIComplete,
                "call_ai_complete",
                side_effect=RuntimeError("boom"),
            ) as mock_call,
            pytest.raises(RuntimeError, match="boom"),
        ):
            lm("reflect please")
        assert mock_call.call_count == 1
        assert lm.error_sink is None

    def test_success_returns_response_without_retry(self):
        lm = self._lm()
        with patch.object(
            adapter.RobustAIComplete, "call_ai_complete", return_value=["improved"]
        ) as mock_call:
            assert lm("reflect please") == "improved"
        assert mock_call.call_count == 1

    def test_retries_up_to_max_attempts_then_records_and_reraises(self):
        """Opted-in: retries max_attempts times, records final error, re-raises."""
        lm = self._lm()
        lm.max_attempts = 3
        sink: list[Exception] = []
        lm.error_sink = sink
        with (
            patch.object(adapter.time, "sleep") as mock_sleep,
            patch.object(
                adapter.RobustAIComplete,
                "call_ai_complete",
                side_effect=RuntimeError("model unavailable"),
            ) as mock_call,
            pytest.raises(RuntimeError, match="model unavailable"),
        ):
            lm("reflect please")
        # Three attempts, two backoff sleeps between them.
        assert mock_call.call_count == 3
        assert mock_sleep.call_count == 2
        # The final error is captured for the caller to surface on the run.
        assert len(sink) == 1
        assert "model unavailable" in str(sink[0])

    def test_transient_failure_recovers_on_retry_no_capture(self):
        """A retry that eventually succeeds does not record an error."""
        lm = self._lm()
        lm.max_attempts = 3
        sink: list[Exception] = []
        lm.error_sink = sink
        with (
            patch.object(adapter.time, "sleep"),
            patch.object(
                adapter.RobustAIComplete,
                "call_ai_complete",
                side_effect=[RuntimeError("blip"), ["recovered"]],
            ) as mock_call,
        ):
            assert lm("reflect please") == "recovered"
        assert mock_call.call_count == 2
        assert sink == []
