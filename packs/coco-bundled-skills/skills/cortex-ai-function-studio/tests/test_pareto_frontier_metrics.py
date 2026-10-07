# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Tests for Pareto frontier computation and metrics (cross-model)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from snowflake_ai_optimize.core.experiment import (
    FrontierCandidate,
    ParetoCandidateInfo,
    _marginal_hypervolume_2d,
    commit_runs,
    compute_pareto_frontier,
    estimate_candidate_cost,
    hypervolume_subset_selection,
    select_frontier_candidates,
    stamp_frontier_metrics_on_runs,
)
from snowflake_ai_optimize.gepa.experiment import (
    IterationPhaseBreakdown,
    OptimizationRunStats,
    _PhaseDelta,
    compute_pareto_candidates,
    save_optimization_to_experiment,
)

# ---------------------------------------------------------------------------
# Fake session (same as test_progressive_experiment_tracker)
# ---------------------------------------------------------------------------


class _FakeSession:
    """Minimal stand-in for snowpark Session."""

    def __init__(self, *, fail_on: str | None = None):
        self.statements: list[str] = []
        self._fail_on = fail_on

        class _SQLBuilder:
            def __init__(s, sql, parent):
                s.sql = sql
                s.parent = parent

            def collect(s):
                s.parent.statements.append(s.sql)
                if s.parent._fail_on and s.parent._fail_on in s.sql:
                    raise RuntimeError(f"Simulated failure on: {s.sql}")

        self._SQLBuilder = _SQLBuilder

        class _FileApi:
            def __init__(s, parent):
                s.parent = parent
                s.put_calls: list[tuple] = []

            def put(s, *args, **kwargs):
                s.put_calls.append((args, kwargs))

        self.file = _FileApi(self)

    def sql(self, sql: str):
        return self._SQLBuilder(sql, self)


# ---------------------------------------------------------------------------
# compute_pareto_frontier
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# estimate_candidate_cost
# ---------------------------------------------------------------------------


_FAKE_RATES = {"test-model": {"input_cost": 1.0, "output_cost": 2.0}}
_PATCH_RATES = patch(
    "snowflake_ai_optimize.core.experiment._load_model_rates",
    return_value=_FAKE_RATES,
)


class TestEstimateCandidateCost:
    def test_prompt_tokens_only(self):
        with _PATCH_RATES:
            assert estimate_candidate_cost("test-model", 1_000_000, 0) == pytest.approx(
                1.0
            )

    def test_prompt_and_completion_tokens(self):
        with _PATCH_RATES:
            cost = estimate_candidate_cost("test-model", 500_000, 250_000)
        assert cost == pytest.approx(500_000 * 1.0 / 1e6 + 250_000 * 2.0 / 1e6)

    def test_zero_tokens_returns_zero(self):
        with _PATCH_RATES:
            assert estimate_candidate_cost("test-model", 0, 0) == 0.0

    def test_raises_for_unknown_model(self):
        with _PATCH_RATES, pytest.raises(ValueError, match="unknown"):
            estimate_candidate_cost("unknown", 1000, 500)

    def test_raises_for_empty_rates(self):
        with (
            patch(
                "snowflake_ai_optimize.core.experiment._load_model_rates",
                return_value={},
            ),
            pytest.raises(ValueError, match="test-model"),
        ):
            estimate_candidate_cost("test-model", 1000, 500)


# ---------------------------------------------------------------------------
# compute_pareto_frontier
# ---------------------------------------------------------------------------


class TestComputeParetoFrontier:
    def test_empty_input(self):
        assert compute_pareto_frontier([]) == set()

    def test_single_point(self):
        assert compute_pareto_frontier([(1.0, 0.5)]) == {0}

    def test_dominated_point_excluded(self):
        # Point 1 has higher cost AND lower score than point 0.
        points = [(1.0, 0.8), (2.0, 0.7)]
        assert compute_pareto_frontier(points) == {0}

    def test_both_pareto_optimal(self):
        # Point 0: cheaper but lower score; point 1: costlier but higher score.
        points = [(1.0, 0.5), (2.0, 0.9)]
        assert compute_pareto_frontier(points) == {0, 1}

    def test_same_cost_higher_score_dominates(self):
        points = [(1.0, 0.5), (1.0, 0.8)]
        frontier = compute_pareto_frontier(points)
        assert 1 in frontier
        assert 0 not in frontier

    def test_three_points_all_on_frontier(self):
        # Each point trades cost for score — none is dominated.
        points = [(1.0, 0.5), (3.0, 0.7), (5.0, 0.9)]
        assert compute_pareto_frontier(points) == {0, 1, 2}

    def test_middle_dominated_by_cheaper_and_better(self):
        # Point 1 (cost=3, score=0.4) dominated by point 0 (cost=1, score=0.5).
        points = [(1.0, 0.5), (3.0, 0.4), (5.0, 0.9)]
        assert compute_pareto_frontier(points) == {0, 2}

    def test_marginal_improvement_still_on_frontier(self):
        # 2x prompt for +0.001 score IS on the frontier (pareto optimality
        # doesn't judge whether the trade-off is "worth it").
        points = [(1000.0, 0.500), (2000.0, 0.501)]
        assert compute_pareto_frontier(points) == {0, 1}

    def test_realistic_multi_candidate(self):
        points = [
            (500.0, 0.60),  # seed
            (800.0, 0.75),  # iter 1
            (1200.0, 0.74),  # iter 2: dominated by iter 1
            (1500.0, 0.85),  # iter 3
            (2000.0, 0.84),  # iter 4: dominated by iter 3
        ]
        frontier = compute_pareto_frontier(points)
        assert frontier == {0, 1, 3}


# ---------------------------------------------------------------------------
# Pareto metrics in save_optimization_to_experiment
# ---------------------------------------------------------------------------


_SEED_BREAKDOWN = IterationPhaseBreakdown(
    new_cand_eval=_PhaseDelta(eval_prompt_tokens=20000, eval_completion_tokens=2000),
    new_cand_eval_minibatch_size=10,
)
_ITER1_BREAKDOWN = IterationPhaseBreakdown(
    new_cand_eval=_PhaseDelta(eval_prompt_tokens=50000, eval_completion_tokens=10000),
    new_cand_eval_minibatch_size=5,
)
_BASE_DISCOVERY_ITER: dict[int, int] = {0: 0, 1: 1}
_BASE_PHASE_BREAKDOWNS: dict[int, IterationPhaseBreakdown] = {
    0: _SEED_BREAKDOWN,
    1: _ITER1_BREAKDOWN,
}


class TestParetoMetricsInSave:
    def _base_kwargs(self):
        return dict(
            function_name="DB.S.FN",
            model="claude-haiku-4-5",
            seed_prompt="short seed",
            best_prompt="a longer improved prompt with more detail",
            candidates=["short seed", "a longer improved prompt with more detail"],
            val_scores=[0.5, 0.8],
            best_idx=1,
        )

    def _base_stats(self, **extra):
        defaults: dict = dict(
            discovery_iter=_BASE_DISCOVERY_ITER,
            phase_breakdowns=_BASE_PHASE_BREAKDOWNS,
            reflection_model="claude-haiku-4-5",
        )
        defaults.update(extra)
        return OptimizationRunStats(seed_val_score=0.5, best_val_score=0.8, **defaults)

    def test_estimated_cost_in_metrics(self):
        sess = _FakeSession()
        save_optimization_to_experiment(
            sess, "DB.S.EXP", **self._base_kwargs(), stats=self._base_stats()
        )

        metric_stmts = [s for s in sess.statements if "ADD METRICS" in s]
        cost_stmts = [s for s in metric_stmts if "estimated_cost" in s]
        assert len(cost_stmts) > 0, "estimated_cost should appear in metrics"

    def test_seed_and_iter_both_get_pareto_metrics(self):
        """Both SEED and ITER_1 runs should have pareto metrics."""
        sess = _FakeSession()
        save_optimization_to_experiment(
            sess, "DB.S.EXP", **self._base_kwargs(), stats=self._base_stats()
        )

        metric_stmts = [s for s in sess.statements if "ADD METRICS" in s]
        seed_metrics = [s for s in metric_stmts if "SEED" in s]
        iter_metrics = [s for s in metric_stmts if "ITER_1" in s]
        assert any("estimated_cost" in s for s in seed_metrics)
        assert any("estimated_cost" in s for s in iter_metrics)

    def test_backfill_pareto_on_already_persisted_runs(self):
        """When already_persisted_runs is set, the batch save should issue
        ADD METRICS to backfill Pareto metrics onto those runs.
        """  # noqa: D205
        sess = _FakeSession()
        persisted = {
            "CLAUDE_HAIKU_4_5_SEED",
            "CLAUDE_HAIKU_4_5_ITER_1",
        }
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(already_persisted_runs=persisted),
        )

        metric_stmts = [s for s in sess.statements if "ADD METRICS" in s]
        seed_backfill = [
            s for s in metric_stmts if "SEED" in s and "estimated_cost" in s
        ]
        iter_backfill = [
            s for s in metric_stmts if "ITER_1" in s and "estimated_cost" in s
        ]
        assert len(seed_backfill) >= 1, "SEED should get Pareto metrics backfilled"
        assert len(iter_backfill) >= 1, "ITER_1 should get Pareto metrics backfilled"

    def test_persisted_runs_never_get_metrics_after_commit(self):
        """Regression: metrics for an already-persisted run must all be
        written BEFORE that run is committed.

        Snowflake rejects ``ADD METRICS`` on a committed run.  The backfill
        loop owns already-persisted runs (it writes val/cost/pareto then
        commits); the ITER loop must not re-write metrics afterward.
        """  # noqa: D205
        sess = _FakeSession()
        persisted = {
            "CLAUDE_HAIKU_4_5_SEED",
            "CLAUDE_HAIKU_4_5_ITER_1",
        }
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(already_persisted_runs=persisted),
        )

        for run in persisted:
            add_idx = [
                i
                for i, s in enumerate(sess.statements)
                if "ADD METRICS" in s and run in s
            ]
            commit_idx = [
                i
                for i, s in enumerate(sess.statements)
                if "COMMIT RUN" in s and run in s
            ]
            assert add_idx, f"{run} should have metrics written"
            assert commit_idx, f"{run} should be committed"
            assert max(add_idx) < min(commit_idx), (
                f"{run}: ADD METRICS at {add_idx} must all precede "
                f"COMMIT RUN at {commit_idx} (Snowflake rejects metrics on "
                "a committed run)"
            )

    def test_iter_cost_exceeds_seed_cost(self):
        """ITER_1 has more tokens per call than SEED and should cost more."""
        sess = _FakeSession()
        seed_bd = IterationPhaseBreakdown(
            new_cand_eval=_PhaseDelta(
                eval_prompt_tokens=10000,
                eval_completion_tokens=500,
            ),
            new_cand_eval_minibatch_size=10,
        )  # avg_pt=1000, avg_ct=50
        iter1_bd = IterationPhaseBreakdown(
            new_cand_eval=_PhaseDelta(
                eval_prompt_tokens=50000,
                eval_completion_tokens=10000,
            ),
            new_cand_eval_minibatch_size=10,
        )  # avg_pt=5000, avg_ct=1000 — more expensive per call
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(
                discovery_iter={0: 0, 1: 1},
                phase_breakdowns={0: seed_bd, 1: iter1_bd},
            ),
        )

        metric_stmts = [s for s in sess.statements if "ADD METRICS" in s]
        iter_stmts = [s for s in metric_stmts if "ITER_1" in s]
        seed_stmts = [s for s in metric_stmts if "SEED" in s]

        def _extract_cost(stmts):
            for s in stmts:
                if "estimated_cost" in s:
                    metrics = json.loads(s.split("ADD METRICS = '")[1].rstrip("'"))
                    for m in metrics:
                        if m["name"] == "estimated_cost":
                            return m["value"]
            return None

        iter_cost = _extract_cost(iter_stmts)
        seed_cost = _extract_cost(seed_stmts)

        assert iter_cost is not None
        assert seed_cost is not None
        assert iter_cost > seed_cost, (
            f"ITER_1 cost ({iter_cost}) should exceed SEED cost ({seed_cost}) "
            "because ITER_1 has real token counts from AI_COMPLETE"
        )

    def test_pareto_candidates_via_compute_fn(self):
        """compute_pareto_candidates returns ParetoCandidateInfo list independently of save."""  # noqa: W505
        kwargs = self._base_kwargs()
        result = compute_pareto_candidates(
            model=kwargs["model"],
            candidates=kwargs["candidates"],
            val_scores=kwargs["val_scores"],
            discovery_iter=_BASE_DISCOVERY_ITER,
            phase_breakdowns=_BASE_PHASE_BREAKDOWNS,
        )
        assert isinstance(result, list)
        assert len(result) == 2  # SEED + ITER_1
        assert all(isinstance(c, ParetoCandidateInfo) for c in result)
        assert result[0].model == "claude-haiku-4-5"
        assert result[0].estimated_cost is not None
        assert result[1].estimated_cost is not None

    def test_reused_duplicate_candidate_inherits_twin_cost(self):
        """A duplicate candidate whose eval GEPA reused inherits the twin's cost.

        When GEPA reuses a cached score for a candidate identical to one it
        already evaluated, the adapter is never re-invoked, so that candidate's
        new_cand_eval records no tokens/chars. Cost estimation must reuse the
        REAL per-call cost of the identical tracked candidate (keyed by prompt
        text) rather than aborting — the failure that killed composed
        benchmark scenarios with cached GEPA re-evaluations.
        """
        dup = "an improved iter prompt"
        result = compute_pareto_candidates(
            model="claude-haiku-4-5",
            candidates=["seed", dup, dup],  # candidate 2 duplicates candidate 1
            val_scores=[0.5, 0.7, 0.7],
            # Candidate 2 is intentionally absent from discovery_iter (its eval
            # was reused by GEPA and never tracked).
            discovery_iter={0: 0, 1: 1},
            phase_breakdowns=_BASE_PHASE_BREAKDOWNS,
        )
        assert len(result) == 3
        assert result[2].estimated_cost is not None
        # Inherits the identical tracked candidate's REAL per-call cost.
        assert result[2].estimated_cost == result[1].estimated_cost

    def test_save_returns_empty_when_not_deferring(self):
        """With defer_commit unset, all runs are committed here and nothing
        is left pending, so the return is an empty list.
        """  # noqa: D205
        sess = _FakeSession()
        result = save_optimization_to_experiment(
            sess, "DB.S.EXP", **self._base_kwargs(), stats=self._base_stats()
        )
        assert result == []
        # Every SEED/ITER run is committed inline when not deferring.
        assert any("COMMIT RUN" in s and "SEED" in s for s in sess.statements)
        assert any("COMMIT RUN" in s and "ITER_1" in s for s in sess.statements)

    def test_defer_commit_leaves_seed_iter_uncommitted(self):
        """With defer_commit set, SEED/ITER runs are written but NOT committed;
        their names are returned so the orchestrator can stamp + commit them.
        """  # noqa: D205
        sess = _FakeSession()
        result = save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(defer_commit=True),
        )
        assert result is not None
        assert any("SEED" in r for r in result)
        assert any("ITER_1" in r for r in result)
        # No SEED/ITER commit happened inside save when deferring.
        assert not any("COMMIT RUN" in s and "SEED" in s for s in sess.statements)
        assert not any("COMMIT RUN" in s and "ITER_1" in s for s in sess.statements)


# ---------------------------------------------------------------------------
# save_optimization_to_experiment returns ParetoCandidateInfo
# ---------------------------------------------------------------------------


class TestSaveReturnsParetoCandidates:
    def test_pareto_candidates_available_on_save_failure(self):
        """compute_pareto_candidates succeeds even when experiment save fails."""
        candidates = ["seed", "best"]
        val_scores = [0.5, 0.8]
        # Pareto candidates are computed before save — unaffected by save failure.
        result = compute_pareto_candidates(
            model="claude-haiku-4-5",
            candidates=candidates,
            val_scores=val_scores,
            discovery_iter=_BASE_DISCOVERY_ITER,
            phase_breakdowns=_BASE_PHASE_BREAKDOWNS,
        )
        assert isinstance(result, list)
        assert len(result) == 2

        # Save failure is logged but does not propagate.
        sess = _FakeSession(fail_on="ADD RUN")
        save_result = save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            function_name="DB.S.FN",
            model="claude-haiku-4-5",
            seed_prompt="seed",
            best_prompt="best",
            candidates=candidates,
            val_scores=val_scores,
            best_idx=1,
            stats=OptimizationRunStats(),
        )
        assert save_result is None


class TestComputeParetoCandidatesStrictGuard:
    """The SEED is tracked under iteration key 0 by the collector
    (``capture_seed_from_iteration_stats``), so it is priced like any ITER.
    A candidate with no tracked breakdown that has an identical, already-tracked
    twin inherits the twin's REAL per-call cost (GEPA reuses scores only for
    duplicate candidates). A candidate with no breakdown AND no identical twin
    still raises — the #16 fail-fast is preserved (no silent char/prompt
    fallback for genuinely-untracked candidates).
    """  # noqa: D205

    def test_seed_tracked_at_iter0_is_priced(self):
        # discovery_iter[0] = 0 + phase_breakdowns[0] is what the collector
        # now produces for the SEED; it must be priced without raising.
        result = compute_pareto_candidates(
            model="claude-haiku-4-5",
            candidates=["a seed prompt", "an improved iter prompt"],
            val_scores=[0.5, 0.8],
            discovery_iter={0: 0, 1: 1},
            phase_breakdowns={0: _SEED_BREAKDOWN, 1: _ITER1_BREAKDOWN},
        )
        assert len(result) == 2
        assert result[0].estimated_cost is not None
        assert result[1].estimated_cost is not None

    def test_missing_breakdown_still_raises(self):
        # A candidate with no tracked breakdown must raise (fail-fast),
        # not silently fall back to a char estimate.
        with pytest.raises(ValueError, match="has no token data"):
            compute_pareto_candidates(
                model="claude-haiku-4-5",
                candidates=["seed", "iter"],
                val_scores=[0.5, 0.8],
                discovery_iter={0: 0},
                phase_breakdowns={0: _SEED_BREAKDOWN},
            )


# ---------------------------------------------------------------------------
# _marginal_hypervolume_2d
# ---------------------------------------------------------------------------


class TestMarginalHypervolume2D:
    """Test the inner helper that computes marginal contribution."""

    def test_single_point_no_selection(self):
        """First point selected: full rectangle to reference."""
        points = [(2.0, 0.6)]
        ref_cost, ref_score = 10.0, 0.0
        contrib = _marginal_hypervolume_2d(2.0, 0.6, [], points, ref_cost, ref_score)
        assert contrib == (10.0 - 2.0) * (0.6 - 0.0)

    def test_point_outside_reference(self):
        """Point at or beyond reference bounds contributes nothing."""
        points = [(10.0, 0.5)]
        assert _marginal_hypervolume_2d(10.0, 0.5, [], points, 10.0, 0.0) == 0.0
        assert _marginal_hypervolume_2d(5.0, 0.0, [], points, 10.0, 0.0) == 0.0

    def test_marginal_between_two_selected(self):
        """Point inserted between two selected points on the staircase."""
        #   A=(1,0.5), P=(3,0.7), C=(5,0.9), ref=(5.5, 0)
        #   Marginal of P = (score_P - score_A) * (cost_C - cost_P)
        #                  = (0.7 - 0.5) * (5.0 - 3.0) = 0.4
        points = [(1.0, 0.5), (3.0, 0.7), (5.0, 0.9)]
        selected = [0, 2]  # A and C are selected
        ref_cost, ref_score = 5.5, 0.0
        contrib = _marginal_hypervolume_2d(
            3.0, 0.7, selected, points, ref_cost, ref_score
        )
        assert abs(contrib - 0.4) < 1e-9

    def test_marginal_cheapest_point(self):
        """Cheapest point: bottom bound is ref_score."""
        points = [(1.0, 0.5), (5.0, 0.9)]
        selected = [1]  # only C is selected
        ref_cost, ref_score = 10.0, 0.0
        # marginal of A = (0.5 - 0.0) * (5.0 - 1.0) = 2.0
        contrib = _marginal_hypervolume_2d(
            1.0, 0.5, selected, points, ref_cost, ref_score
        )
        assert abs(contrib - 2.0) < 1e-9

    def test_marginal_most_expensive_point(self):
        """Most expensive point: right bound is ref_cost."""
        points = [(1.0, 0.5), (5.0, 0.9)]
        selected = [0]  # only A is selected
        ref_cost, ref_score = 10.0, 0.0
        # marginal of C = (0.9 - 0.5) * (10.0 - 5.0) = 2.0
        contrib = _marginal_hypervolume_2d(
            5.0, 0.9, selected, points, ref_cost, ref_score
        )
        assert abs(contrib - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# hypervolume_subset_selection
# ---------------------------------------------------------------------------


class TestHypervolumeSubsetSelection:
    def test_empty_input(self):
        assert hypervolume_subset_selection([], k=3) == []

    def test_all_returned_when_k_gte_n(self):
        points = [(1.0, 0.5), (2.0, 0.7)]
        result = hypervolume_subset_selection(points, k=5)
        assert set(result) == {0, 1}

    def test_exactly_k_returned(self):
        points = [(1.0, 0.5), (2.0, 0.7), (3.0, 0.8), (4.0, 0.9)]
        result = hypervolume_subset_selection(points, k=2)
        assert len(result) == 2

    def test_three_point_frontier_select_two(self):
        """A=(1,0.5), B=(3,0.7), C=(5,0.9), ref=(5.5,0), select 2.

        After normalisation to [0,1] the points become (0,0), (0.5,0.5),
        (1,1) and ref becomes (1.125, -1.25).

        First pick: A has the largest rectangle (widest, despite
        short height).  Second pick: B beats C because C's rectangle
        is very thin (close to ref_cost in normalised space).
        """
        points = [(1.0, 0.5), (3.0, 0.7), (5.0, 0.9)]
        result = hypervolume_subset_selection(points, k=2, reference=(5.5, 0.0))
        assert result == [0, 1]

    def test_middle_point_can_beat_expensive_extreme(self):
        """Even after normalisation, the most expensive point's rectangle
        is thin when ref_cost is close to max_cost.  The middle point
        contributes more volume and is selected instead.
        """  # noqa: D205
        points = [(1.0, 0.3), (5.0, 0.5), (10.0, 0.9)]
        result = hypervolume_subset_selection(points, k=2, reference=(11.0, 0.0))
        assert set(result) == {0, 1}

    def test_seed_score_as_reference_filters_baseline(self):
        """Using (max_cost * 1.1, seed_score) as reference restricts
        volume to the region that improves over the seed baseline.
        A point barely above seed score gets very little volume.
        """  # noqa: D205
        seed_score = 0.5
        points = [
            (2.0, 0.51),  # barely better than seed
            (3.0, 0.7),
            (5.0, 0.9),
        ]
        max_cost = max(c for c, _s in points)
        reference = (max_cost * 1.1, seed_score)
        result = hypervolume_subset_selection(points, k=2, reference=reference)
        # Point 0 (score=0.51) contributes almost no volume above the
        # seed baseline; the two higher-scoring points are preferred.
        assert 0 not in result
        assert set(result) == {1, 2}

    def test_cheaper_preferred_at_equal_score(self):
        """Two candidates with the same score: the cheaper one has a
        wider rectangle after normalisation and is selected first.
        """  # noqa: D205
        points = [(2.0, 0.8), (8.0, 0.8)]
        result = hypervolume_subset_selection(points, k=1, reference=(10.0, 0.0))
        assert result == [0]

    def test_extremes_preferred_with_distant_reference(self):
        """With a far-away reference, all normalised widths are similar
        (~10-11), so height (score) dominates.  The highest-scoring
        point is picked first, then the cheapest fills the remaining
        gap in cost space.
        """  # noqa: D205
        points = [(1.0, 0.3), (5.0, 0.5), (10.0, 0.9)]
        result = hypervolume_subset_selection(points, k=2, reference=(100.0, 0.0))
        assert set(result) == {0, 2}

    def test_default_reference_normalised_spread(self):
        """When no reference is given, the normalised (1.1, -0.1)
        default is used for spread-maximising selection.
        """  # noqa: D205
        points = [(1.0, 0.5), (2.0, 0.7), (3.0, 0.9)]
        result = hypervolume_subset_selection(points, k=2)
        assert len(result) == 2
        assert all(0 <= idx < 3 for idx in result)

    def test_normalisation_is_scale_invariant(self):
        """Multiplying one axis by a constant must not change the
        selection order — normalisation maps both axes to [0,1] so
        the raw numeric scale is irrelevant.
        """  # noqa: D205
        base_points = [(1.0, 0.5), (3.0, 0.7), (5.0, 0.8), (8.0, 0.9)]
        scaled_points = [(c * 1000, s) for c, s in base_points]
        result_base = hypervolume_subset_selection(base_points, k=2)
        result_scaled = hypervolume_subset_selection(scaled_points, k=2)
        assert result_base == result_scaled

    def test_realistic_five_model_frontier(self):
        """Simulate a realistic cross-model frontier with 10 candidates,
        select 7.  Verify correctness: exactly K returned, cheapest
        point included (it spans the most width), and no duplicates.
        """  # noqa: D205
        points = [
            (0.10, 0.60),  # cheap model seed
            (0.15, 0.65),  # cheap model iter
            (0.30, 0.72),  # mid model seed
            (0.45, 0.78),  # mid model iter
            (0.60, 0.82),  # mid-high model seed
            (0.80, 0.85),  # mid-high model iter
            (1.00, 0.88),  # expensive model seed
            (1.20, 0.90),  # expensive model iter 1
            (1.50, 0.91),  # expensive model iter 2
            (2.00, 0.92),  # very expensive model iter
        ]
        result = hypervolume_subset_selection(points, k=7, reference=(2.2, 0.0))
        assert len(result) == 7
        assert len(set(result)) == 7
        # The cheapest point spans the widest rectangle; it should
        # always be selected.
        assert 0 in result


# ---------------------------------------------------------------------------
# select_frontier_candidates
# ---------------------------------------------------------------------------


def _fc(
    model: str, idx: int, cost: float, score: float, prompt_text: str = ""
) -> FrontierCandidate:
    return FrontierCandidate(
        model=model,
        candidate_idx=idx,
        estimated_cost=cost,
        score=score,
        prompt_text=prompt_text,
    )


class TestSelectFrontierCandidates:
    def test_empty(self):
        assert select_frontier_candidates([]) == []

    def test_all_returned_when_under_cap(self):
        candidates = [
            _fc("a", 0, 1.0, 0.5),
            _fc("b", 1, 3.0, 0.7),
            _fc("c", 2, 5.0, 0.9),
        ]
        result = select_frontier_candidates(candidates, max_candidates=7)
        assert len(result) == 3
        assert {r.model for r in result} == {"a", "b", "c"}

    def test_dominated_candidates_filtered(self):
        """A dominated candidate should never appear in the output."""
        candidates = [
            _fc("cheap", 0, 1.0, 0.8),  # dominates "bad"
            _fc("bad", 1, 2.0, 0.7),  # dominated
            _fc("expensive", 2, 5.0, 0.9),
        ]
        result = select_frontier_candidates(candidates, max_candidates=7)
        models = [r.model for r in result]
        assert "bad" not in models
        assert "cheap" in models
        assert "expensive" in models

    def test_capped_to_max_candidates(self):
        """With 10 frontier points and cap=3, only 3 should be returned."""
        candidates = [_fc("m", i, float(i + 1), 0.1 * (i + 1)) for i in range(10)]
        result = select_frontier_candidates(candidates, max_candidates=3)
        assert len(result) == 3

    def test_seed_score_filters_baseline(self):
        """With seed_score set, candidates barely above baseline should
        be deprioritized in favour of clearly-better ones.
        """  # noqa: D205
        candidates = [
            _fc("a", 0, 2.0, 0.51),  # barely above seed 0.5
            _fc("b", 1, 3.0, 0.7),
            _fc("c", 2, 4.0, 0.8),
            _fc("d", 3, 5.0, 0.9),
        ]
        result = select_frontier_candidates(
            candidates, max_candidates=2, seed_score=0.5
        )
        models = {r.model for r in result}
        # "a" contributes almost no volume above seed_score=0.5
        assert "a" not in models
        assert len(result) == 2

    def test_multi_model_realistic(self):
        """Simulate two models with overlapping cost ranges."""
        candidates = [
            _fc("haiku", 0, 0.10, 0.60),
            _fc("haiku", 1, 0.15, 0.72),
            _fc("haiku", 2, 0.20, 0.75),
            _fc("sonnet", 0, 0.50, 0.80),
            _fc("sonnet", 1, 0.80, 0.88),
            _fc("sonnet", 2, 1.00, 0.90),
        ]
        result = select_frontier_candidates(candidates, max_candidates=4)
        assert len(result) == 4
        # At least one from each model should survive.
        models = {r.model for r in result}
        assert "haiku" in models
        assert "sonnet" in models

    def test_preserves_frontier_candidate_fields(self):
        """Returned items should be FrontierCandidate with correct fields."""
        candidates = [_fc("m", 42, 1.0, 0.9, prompt_text="You are a classifier.")]
        result = select_frontier_candidates(candidates, max_candidates=5)
        assert len(result) == 1
        r = result[0]
        assert r.model == "m"
        assert r.candidate_idx == 42
        assert r.estimated_cost == 1.0
        assert r.score == 0.9
        assert r.prompt_text == "You are a classifier."

    def test_prompt_text_preserved_through_selection(self):
        """prompt_text survives hypervolume subset selection."""
        candidates = [
            _fc("a", 0, 1.0, 0.5, prompt_text="prompt_a"),
            _fc("b", 1, 2.0, 0.7, prompt_text="prompt_b"),
            _fc("c", 2, 3.0, 0.9, prompt_text="prompt_c"),
        ]
        result = select_frontier_candidates(candidates, max_candidates=2)
        assert len(result) == 2
        for r in result:
            assert r.prompt_text.startswith("prompt_")


# ---------------------------------------------------------------------------
# stamp_frontier_metrics_on_runs + commit_runs
# ---------------------------------------------------------------------------


class TestStampFrontierMetricsOnRuns:
    """The optimizer stamps is_frontier (+ test_score) directly onto the
    source SEED/ITER lineage runs — no separate run kind.
    """  # noqa: D205

    def _statements(self, session: _FakeSession) -> str:
        return "\n".join(session.statements)

    def test_stamps_metrics_onto_source_runs(self):
        session = _FakeSession()
        frontier = [
            FrontierCandidate(
                model="m1",
                candidate_idx=0,
                estimated_cost=0.001,
                score=0.80,
                prompt_text="SEED BODY",
                run_name="M1_SEED",
                test_score=0.78,
            ),
            FrontierCandidate(
                model="m1",
                candidate_idx=2,
                estimated_cost=0.004,
                score=0.91,
                prompt_text="ITER BODY",
                run_name="M1_ITER_2",
                test_score=0.88,
            ),
        ]
        stamp_frontier_metrics_on_runs(
            session, "DB.SC.EXP", frontier_selection=frontier
        )
        stmts = self._statements(session)
        # ADD METRICS targets the SEED/ITER lineage runs directly — no
        # FRONTIER_CANDIDATE run kind, and no new ADD RUN.
        assert "ADD RUN" not in stmts
        assert "MODIFY RUN M1_SEED ADD METRICS" in stmts
        assert "MODIFY RUN M1_ITER_2 ADD METRICS" in stmts
        assert '"name": "is_frontier"' in stmts
        assert '"name": "test_score"' in stmts
        # valset_score / estimated_cost already live on the run — not re-written.
        assert '"name": "valset_score"' not in stmts
        assert '"name": "estimated_cost"' not in stmts

    def test_omits_test_score_when_absent(self):
        """No test table → only the is_frontier flag is stamped."""
        session = _FakeSession()
        frontier = [
            FrontierCandidate(
                model="m1",
                candidate_idx=1,
                estimated_cost=0.002,
                score=0.85,
                prompt_text="BODY",
                run_name="M1_ITER_1",
                test_score=None,
            ),
        ]
        stamp_frontier_metrics_on_runs(
            session, "DB.SC.EXP", frontier_selection=frontier
        )
        stmts = self._statements(session)
        assert "MODIFY RUN M1_ITER_1 ADD METRICS" in stmts
        assert '"name": "is_frontier"' in stmts
        assert '"name": "test_score"' not in stmts

    def test_skips_candidate_without_run_name(self):
        session = _FakeSession()
        frontier = [
            FrontierCandidate(
                model="m1",
                candidate_idx=1,
                estimated_cost=0.002,
                score=0.85,
                prompt_text="BODY",
                run_name="",
                test_score=0.9,
            ),
        ]
        stamp_frontier_metrics_on_runs(
            session, "DB.SC.EXP", frontier_selection=frontier
        )
        assert session.statements == []

    def test_no_statements_for_empty_selection(self):
        session = _FakeSession()
        stamp_frontier_metrics_on_runs(session, "DB.SC.EXP", frontier_selection=[])
        assert session.statements == []


class TestCommitRuns:
    def test_commits_each_run_once(self):
        session = _FakeSession()
        commit_runs(session, "DB.SC.EXP", ["M1_SEED", "M1_ITER_1", "M1_ITER_2"])
        commits = [s for s in session.statements if "COMMIT RUN" in s]
        assert len(commits) == 3
        assert any("M1_SEED" in s for s in commits)
        assert any("M1_ITER_2" in s for s in commits)

    def test_dedupes_repeated_names(self):
        session = _FakeSession()
        commit_runs(session, "DB.SC.EXP", ["M1_SEED", "M1_SEED"])
        commits = [s for s in session.statements if "COMMIT RUN" in s]
        assert len(commits) == 1

    def test_one_failure_does_not_block_the_rest(self):
        session = _FakeSession(fail_on="COMMIT RUN M1_SEED")
        # M1_SEED commit raises inside commit_runs but is swallowed; M1_ITER_1
        # still commits.
        commit_runs(session, "DB.SC.EXP", ["M1_SEED", "M1_ITER_1"])
        assert any("COMMIT RUN M1_ITER_1" in s for s in session.statements)
