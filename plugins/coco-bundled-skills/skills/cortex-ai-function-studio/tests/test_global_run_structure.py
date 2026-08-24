# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for the schema-v4 global run structure.

Covers the pieces unique to the global SEED + ITER_<N> scheme (layered on top
of PR #81's deferred-commit / frontier-in-place machinery):

  * ``GlobalRunCounter`` — monotonic + thread-safe, shared across models.
  * ``make_iter_run_name`` — model-agnostic ``SEED`` / ``ITER_<N>``.
  * ``RunParams`` round-trip of the new ``run_type`` / ``global_iteration`` /
    ``per_model_stats`` fields.
  * ``write_consolidated_seed`` — a single ``SEED`` run carrying per-model JSON.
  * ``backfill_model_metrics`` — backfills ITER runs, skips SEED, returns the
    ITER run names for the deferred commit.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from snowflake_ai_optimize.core.experiment import (
    SEED_RUN_NAME,
    GlobalRunCounter,
    ParetoCandidateInfo,
    make_iter_run_name,
)
from snowflake_ai_optimize.core.run_params import RunParams
from snowflake_ai_optimize.gepa.experiment import (
    EXPERIMENT_SCHEMA_VERSION,
    backfill_model_metrics,
    write_consolidated_seed,
)


class _FakeSession:
    """Records the SQL statements issued (no real Snowflake round-trip)."""

    def __init__(self) -> None:
        self.statements: list[str] = []

        class _SQLBuilder:
            def __init__(s, sql: str, parent: _FakeSession) -> None:
                s.sql = sql
                s.parent = parent

            def collect(s):
                s.parent.statements.append(s.sql)
                return []

        self._SQLBuilder = _SQLBuilder

    def sql(self, sql: str):
        return self._SQLBuilder(sql, self)


# ---------------------------------------------------------------------------
# GlobalRunCounter
# ---------------------------------------------------------------------------


class TestGlobalRunCounter:
    def test_next_iter_is_monotonic_1_based(self):
        counter = GlobalRunCounter()
        assert [counter.next_iter() for _ in range(5)] == [1, 2, 3, 4, 5]

    def test_shared_counter_yields_unique_numbers_across_models(self):
        """Two model 'workers' drawing from ONE counter never collide."""
        counter = GlobalRunCounter()
        model_a = [counter.next_iter() for _ in range(3)]
        model_b = [counter.next_iter() for _ in range(3)]
        allocated = model_a + model_b
        assert len(set(allocated)) == len(allocated)  # all unique
        assert sorted(allocated) == [1, 2, 3, 4, 5, 6]

    def test_next_iter_is_thread_safe(self):
        """Concurrent next_iter() calls hand out a contiguous, unique range."""
        counter = GlobalRunCounter()
        with ThreadPoolExecutor(max_workers=8) as ex:
            results = list(ex.map(lambda _: counter.next_iter(), range(500)))
        assert sorted(results) == list(range(1, 501))


# ---------------------------------------------------------------------------
# make_iter_run_name
# ---------------------------------------------------------------------------


class TestMakeIterRunName:
    def test_seed_name_is_model_agnostic(self):
        assert SEED_RUN_NAME == "SEED"

    def test_iter_name_has_no_model_prefix(self):
        assert make_iter_run_name(1) == "ITER_1"
        assert make_iter_run_name(42) == "ITER_42"


# ---------------------------------------------------------------------------
# RunParams new fields
# ---------------------------------------------------------------------------


class TestRunParamsNewFields:
    def test_round_trip_new_fields(self):
        params = RunParams(
            function_impl="body",
            model="claude",
            iteration="3",
            run_type="iteration",
            global_iteration=7,
            per_model_stats=json.dumps({"claude": {"total_candidates": 4}}),
        )
        flat = {p["name"]: p["value"] for p in params.to_param_list()}
        assert flat["run_type"] == "iteration"
        assert flat["global_iteration"] == "7"
        assert json.loads(flat["per_model_stats"]) == {
            "claude": {"total_candidates": 4}
        }

        restored = RunParams.from_param_dict(flat)
        assert restored.run_type == "iteration"
        assert restored.global_iteration == 7
        assert json.loads(restored.per_model_stats) == {
            "claude": {"total_candidates": 4}
        }

    def test_new_fields_default_none_and_are_omitted(self):
        """Unset new fields serialize to nothing (None is skipped)."""
        params = RunParams(function_impl="b", model="m", iteration="1")
        names = {p["name"] for p in params.to_param_list()}
        assert "run_type" not in names
        assert "global_iteration" not in names
        assert "per_model_stats" not in names


# ---------------------------------------------------------------------------
# write_consolidated_seed
# ---------------------------------------------------------------------------


class TestWriteConsolidatedSeed:
    def test_writes_single_seed_run_with_per_model_stats(self):
        session = _FakeSession()
        per_model_stats = {
            "claude-haiku-4.5": {
                "status": "completed",
                "total_candidates": 3,
                "elapsed_seconds": 12.0,
            },
            "mistral-large2": {
                "status": "completed",
                "total_candidates": 5,
                "elapsed_seconds": 20.0,
            },
        }
        write_consolidated_seed(
            session,
            "DB.SC.EXP",
            function_name="DB.SC.FN",
            seed_prompt="SEED BODY",
            model="llama3.1-8b",
            per_model_stats=per_model_stats,
            summed_totals={"total_candidates": 8, "elapsed_seconds": 32.0},
            avg_output_chars=42,
            seed_val_score=0.6,
            seed_estimated_cost=0.001,
        )
        stmts = session.statements
        # Exactly one SEED run is added.
        add_run = [s for s in stmts if "ADD RUN SEED" in s]
        assert len(add_run) == 1
        # No per-model <MODEL>_SEED runs.
        assert not any("_SEED" in s and "ADD RUN" in s for s in stmts)

        params_sql = next(s for s in stmts if "MODIFY RUN SEED ADD PARAMETERS" in s)
        # run_type=seed, schema v4, input-function model, summed global totals,
        # and the per-model JSON all present.
        assert "run_type" in params_sql and "seed" in params_sql
        assert str(EXPERIMENT_SCHEMA_VERSION) in params_sql
        assert "llama3.1-8b" in params_sql  # SEED.model = input function's model
        assert "total_candidates" in params_sql  # summed global total (top-level)
        assert "per_model_stats" in params_sql
        assert "mistral-large2" in params_sql
        assert "claude-haiku-4.5" in params_sql

        metrics_sql = next(s for s in stmts if "MODIFY RUN SEED ADD METRICS" in s)
        assert "valset_score" in metrics_sql

    def test_seed_run_is_not_committed_by_writer(self):
        """The writer leaves SEED RUNNING; the orchestrator commits it later."""
        session = _FakeSession()
        write_consolidated_seed(
            session,
            "DB.SC.EXP",
            function_name="DB.SC.FN",
            seed_prompt="SEED BODY",
            model="llama3.1-8b",
            per_model_stats={"m": {"status": "completed", "total_candidates": 1}},
            seed_val_score=0.5,
        )
        assert not any("COMMIT RUN" in s for s in session.statements)


# ---------------------------------------------------------------------------
# backfill_model_metrics
# ---------------------------------------------------------------------------


class TestBackfillModelMetrics:
    def _candidates(self) -> list[ParetoCandidateInfo]:
        return [
            ParetoCandidateInfo(
                run_name="SEED",
                model="claude",
                estimated_cost=0.001,
                score=0.60,
                prompt_text="seed",
            ),
            ParetoCandidateInfo(
                run_name="ITER_1",
                model="claude",
                estimated_cost=0.002,
                score=0.70,
                prompt_text="c1",
            ),
            ParetoCandidateInfo(
                run_name="ITER_3",
                model="claude",
                estimated_cost=0.003,
                score=0.85,
                prompt_text="c3",
            ),
        ]

    def test_skips_seed_and_returns_iter_run_names(self):
        session = _FakeSession()
        pending = backfill_model_metrics(
            session, "DB.SC.EXP", pareto_candidates=self._candidates()
        )
        # Only the ITER runs are returned for the deferred commit — never SEED.
        assert pending == ["ITER_1", "ITER_3"]
        assert "SEED" not in pending

    def test_backfills_valset_cost_not_frontier(self):
        session = _FakeSession()
        backfill_model_metrics(
            session, "DB.SC.EXP", pareto_candidates=self._candidates()
        )
        stmts = session.statements
        # MODIFY METRICS on each ITER run, none on SEED.
        assert any("MODIFY RUN ITER_1 ADD METRICS" in s for s in stmts)
        assert any("MODIFY RUN ITER_3 ADD METRICS" in s for s in stmts)
        assert not any("MODIFY RUN SEED" in s for s in stmts)
        # Carries valset_score + estimated_cost, but NOT the cross-model
        # is_frontier/test_score (stamped later) and does NOT commit.
        metric_sql = " ".join(s for s in stmts if "ADD METRICS" in s)
        assert "valset_score" in metric_sql
        assert "estimated_cost" in metric_sql
        assert "is_frontier" not in metric_sql
        assert "test_score" not in metric_sql
        assert not any("COMMIT RUN" in s for s in stmts)
