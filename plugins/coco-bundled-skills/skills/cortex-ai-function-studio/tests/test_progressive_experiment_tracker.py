# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for ProgressiveExperimentTracker.

Covers the progressive experiment tracking callback that persists
global ITER_N runs to Snowflake as each GEPA iteration completes
(instead of batching writes after the full optimization).  Under
schema v4 the run names are global and model-agnostic: accepted
candidates AND rejected/merge-rejected proposals share a single
``ITER_<N>`` sequence handed out by a ``GlobalRunCounter``; the
producing model and the accepted/rejected role are run *params*
(``model`` / ``run_type`` / ``status``), never encoded in the name.
The SEED run (named ``SEED``) is still written only by the post-loop
save, never the progressive tracker.

Tests are structured in layers:

1. Callback state machine — verifies that the duck-typed GEPA event
   sequence produces the correct Snowflake writes at the right times.

2. Fault tolerance — verifies that SQL failures in one write don't
   break subsequent writes or the optimization loop.

3. Integration with save_optimization_to_experiment — verifies that
   already-persisted runs are skipped by the post-loop save.

Run:
    uv run --group test pytest tests/test_progressive_experiment_tracker.py -v
"""

from __future__ import annotations

import pytest

from snowflake_ai_optimize.core.experiment import GlobalRunCounter
from snowflake_ai_optimize.gepa.experiment import (
    IterationPhaseBreakdown,
    OptimizationRunStats,
    ProgressiveExperimentTracker,
    RejectedCandidate,
    _PhaseDelta,
    save_optimization_to_experiment,
)

_SEED_BREAKDOWN = IterationPhaseBreakdown(
    new_cand_eval=_PhaseDelta(eval_prompt_tokens=20000, eval_completion_tokens=2000),
    new_cand_eval_minibatch_size=10,
)
_ITER1_BREAKDOWN = IterationPhaseBreakdown(
    new_cand_eval=_PhaseDelta(eval_prompt_tokens=50000, eval_completion_tokens=10000),
    new_cand_eval_minibatch_size=5,
)


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed."""
    yield


# ---------------------------------------------------------------------------
# Fake session (same pattern as test_rejected_candidate_persist.py)
# ---------------------------------------------------------------------------


class _FakeSession:
    """Minimal stand-in for snowpark Session.

    Records every ``session.sql(...).collect()`` call so the test can
    assert which DDL statements ran without a live Snowflake connection.
    """

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


def _extract_param_value(add_params_stmt: str, param_name: str) -> str | None:
    """Pull a single param value out of an ALTER ... ADD PARAMETERS SQL.

    Params are serialised as a JSON array of ``{"name": ..., "value": ...}``
    objects.  Under schema v4 the producing model and the accepted/rejected
    role live in these params (``model`` / ``run_type`` / ``status``) rather
    than in the run name, so name-based assertions become param assertions.
    """
    import json
    import re

    m = re.search(r"ADD PARAMETERS\s*=\s*'(\[.*?\])'", add_params_stmt, re.DOTALL)
    if not m:
        return None
    # Reverse the SQL string-escape applied at write time.
    raw = m.group(1).replace(r"\'", "'").replace(r"\\", "\\")
    try:
        params = json.loads(raw)
    except json.JSONDecodeError:
        return None
    for p in params:
        if p.get("name") == param_name:
            return str(p.get("value"))
    return None


# ---------------------------------------------------------------------------
# ProgressiveExperimentTracker — SEED run handled by post-loop
# ---------------------------------------------------------------------------


class TestProgressiveTrackerSeedNotWritten:
    def test_tracker_does_not_write_seed(self):
        """SEED is always written by the post-loop save with full timing
        data.  The progressive tracker should never touch it.
        """  # noqa: D205
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        assert not hasattr(tracker, "write_seed_run")
        # v4: the seed run name is global (``SEED``), and the tracker still
        # never touches it — no ADD RUN SEED, no ADD RUN at all yet.
        assert "SEED" not in tracker.persisted_runs
        assert not any("ADD RUN" in s for s in sess.statements)


# ---------------------------------------------------------------------------
# ProgressiveExperimentTracker — accepted iterations
# ---------------------------------------------------------------------------


class TestProgressiveTrackerAcceptedIteration:
    def _fire_accepted(self, tracker, iteration=1, candidate_idx=1, parent_idx=0):
        tracker.on_iteration_start({"iteration": iteration})
        tracker.on_candidate_selected(
            {"iteration": iteration, "candidate_idx": parent_idx}
        )
        tracker.on_proposal_end(
            {"iteration": iteration, "new_instructions": {"instruction": "improved"}}
        )
        tracker.on_evaluation_end(
            {"iteration": iteration, "candidate_idx": None, "scores": [0.8, 0.9]}
        )
        tracker.on_candidate_accepted(
            {
                "iteration": iteration,
                "new_candidate_idx": candidate_idx,
                "new_score": 1.7,
            }
        )

    def test_accepted_candidate_emits_iter_run(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        self._fire_accepted(tracker, iteration=2, candidate_idx=1)

        # One accept event -> global counter N=1 -> run name "ITER_1".
        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        assert any("ADD RUN ITER_1" in s for s in add_stmts)
        assert "ITER_1" in tracker.persisted_runs
        # The producing model is now a PARAM, not part of the run name.
        params_sql = next(
            s for s in sess.statements if "MODIFY RUN ITER_1 ADD PARAMETERS" in s
        )
        assert _extract_param_value(params_sql, "model") == "claude-haiku-4-5"

    def test_accepted_candidate_not_committed_by_tracker(self):
        """Progressive tracker leaves runs in RUNNING state so the batch
        save can backfill Pareto metrics before committing.
        """  # noqa: D205
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        self._fire_accepted(tracker)

        commit_stmts = [s for s in sess.statements if "COMMIT RUN" in s]
        assert not any("ITER_1" in s for s in commit_stmts)

    def test_multiple_accepted_iterations(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        self._fire_accepted(tracker, iteration=1, candidate_idx=1, parent_idx=0)
        self._fire_accepted(tracker, iteration=2, candidate_idx=2, parent_idx=1)

        # Two accept events -> global ITER_1 then ITER_2.
        assert "ITER_1" in tracker.persisted_runs
        assert "ITER_2" in tracker.persisted_runs

    def test_accepted_without_new_candidate_idx_is_noop(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        tracker.on_iteration_start({"iteration": 1})
        tracker.on_candidate_accepted({"iteration": 1})

        assert len(tracker.persisted_runs) == 0

    def test_progressive_iter_run_includes_token_breakdown(self):
        """Regression: the progressive ITER write must include the new
        per-iteration token columns (``iter_eval_*``,
        ``iter_reflection_*_est``) and per-phase token splits
        (``new_cand_eval_prompt_tokens``, ``parent_eval_prompt_tokens``,
        ``phase_reflection_prompt_tokens_est``).

        Before this fix, ``_per_iter_kwargs`` only emitted the
        char-based columns the report's existing per-iteration table
        relied on (``iter_input_chars``, ``parent_eval_input_chars``,
        …) but skipped the new token columns added 2026-05.  As a
        result, BENCH_TRACKING_DETAILS rendered the new
        ``iter_eval_prompt_tokens`` / ``new_cand_eval_prompt_tokens``
        columns as NULL on every ITER_N / REJECTED_N row even though
        SEED rows had them.
        """  # noqa: D205
        from snowflake_ai_optimize.core.timing import TimingTracker, set_active_tracker

        # Drive a real TimingTracker so ``_PhaseSnapshot.from_tracker``
        # captures non-zero eval tokens / chars.  We add UDF tokens
        # before / after the iteration boundary so the per-iteration
        # delta comes out non-zero.
        ttracker = TimingTracker()
        set_active_tracker(ttracker)
        try:
            # Pre-iteration: nothing.  Iteration 1 starts → snapshot
            # captures 0 tokens.
            sess = _FakeSession()
            tracker = ProgressiveExperimentTracker(
                session=sess,
                experiment_name="DB.S.EXP",
                model="claude-haiku-4-5",
                function_name="DB.S.FN",
                run_counter=GlobalRunCounter(),
            )
            tracker.on_iteration_start({"iteration": 1})

            # Parent eval: snap BEFORE the work, then do the work, then
            # snap AFTER.  ``_PhaseSnapshot``s are captured from the
            # tracker's token_usage / char_usage at the moment each
            # ``on_evaluation_start`` / ``on_evaluation_end`` /
            # ``on_proposal_*`` callback fires; the per-phase delta is
            # ``end - start``.  Adding tokens BEFORE on_evaluation_start
            # would put them outside the parent_eval window.
            tracker.on_evaluation_start({"iteration": 1, "candidate_idx": 0})
            ttracker.add_chars(
                "claude-haiku-4-5", "udf", input_chars=2000, output_chars=400
            )
            ttracker.add_tokens(
                "claude-haiku-4-5",
                "udf",
                prompt_tokens=500,
                completion_tokens=100,
            )
            tracker.on_evaluation_end(
                {"iteration": 1, "candidate_idx": 0, "scores": [0.7]}
            )

            # Reflection phase: char-only on the reflection bucket.
            tracker.on_proposal_start({"iteration": 1})
            ttracker.add_chars(
                "claude-opus-4-6",
                "reflection",
                input_chars=1600,
                output_chars=320,
            )
            tracker.on_proposal_end(
                {
                    "iteration": 1,
                    "new_instructions": {"instruction": "improved"},
                }
            )

            # New-candidate eval: more UDF tokens, snapshotted by
            # ``candidate_idx=None`` evaluation_start/end events.
            tracker.on_evaluation_start({"iteration": 1, "candidate_idx": None})
            ttracker.add_chars(
                "claude-haiku-4-5", "udf", input_chars=2200, output_chars=440
            )
            ttracker.add_tokens(
                "claude-haiku-4-5",
                "udf",
                prompt_tokens=550,
                completion_tokens=110,
            )
            tracker.on_evaluation_end(
                {"iteration": 1, "candidate_idx": None, "scores": [0.85]}
            )

            tracker.on_candidate_accepted(
                {
                    "iteration": 1,
                    "new_candidate_idx": 1,
                    "new_score": 0.85,
                }
            )
        finally:
            set_active_tracker(None)

        # Find the ADD PARAMETERS for ITER_1 and inspect the param
        # names the progressive write emitted.  Run names are global now
        # (no model prefix); the model is carried as a param.
        iter_params_sql = next(
            s for s in sess.statements if "MODIFY RUN ITER_1 ADD PARAMETERS" in s
        )
        assert _extract_param_value(iter_params_sql, "model") == "claude-haiku-4-5"
        # Per-iteration token breakdown (new columns, must be present).
        for token_param in (
            "iter_eval_prompt_tokens",
            "iter_eval_completion_tokens",
            "iter_reflection_prompt_tokens_est",
            "iter_reflection_completion_tokens_est",
            "new_cand_eval_prompt_tokens",
            "new_cand_eval_completion_tokens",
            "parent_eval_prompt_tokens",
            "parent_eval_completion_tokens",
            "phase_reflection_prompt_tokens_est",
            "phase_reflection_completion_tokens_est",
        ):
            assert token_param in iter_params_sql, (
                f"Progressive ITER write must emit {token_param!r} so "
                f"BENCH_TRACKING_DETAILS doesn't silently render it as NULL"
            )


# ---------------------------------------------------------------------------
# ProgressiveExperimentTracker — rejected iterations
# ---------------------------------------------------------------------------


class TestProgressiveTrackerRejectedIteration:
    def test_reflective_rejection_emits_rejected_run(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        tracker.on_iteration_start({"iteration": 3})
        tracker.on_candidate_selected({"iteration": 3, "candidate_idx": 0})
        tracker.on_proposal_end(
            {"iteration": 3, "new_instructions": {"instruction": "bad idea"}}
        )
        tracker.on_candidate_rejected(
            {"iteration": 3, "old_score": 2.0, "new_score": 1.0, "reason": "worse"}
        )

        # A rejected proposal is a run in the SAME global ITER sequence
        # (one reject event -> global N=1 -> "ITER_1"), distinguished by
        # run_type/status params rather than a "_REJECTED_" name.
        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        assert any("ADD RUN ITER_1" in s for s in add_stmts)
        assert "ITER_1" in tracker.persisted_runs
        params_sql = next(
            s for s in sess.statements if "MODIFY RUN ITER_1 ADD PARAMETERS" in s
        )
        assert _extract_param_value(params_sql, "run_type") == "rejected"
        assert _extract_param_value(params_sql, "status") == "rejected"

    def test_merge_rejection_emits_rejected_run(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        tracker.on_merge_attempted(
            {
                "iteration": 5,
                "parent_ids": [1, 2],
                "merged_candidate": {"body": "merged text"},
            }
        )
        tracker.on_merge_rejected(
            {"iteration": 5, "reason": "merge worse than parents"}
        )

        # Merge rejection also lands in the global ITER sequence (N=1),
        # distinguished by run_type="rejected" / rejection_kind="merge".
        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        assert any("ADD RUN ITER_1" in s for s in add_stmts)
        assert "ITER_1" in tracker.persisted_runs
        params_sql = next(
            s for s in sess.statements if "MODIFY RUN ITER_1 ADD PARAMETERS" in s
        )
        assert _extract_param_value(params_sql, "run_type") == "rejected"
        assert _extract_param_value(params_sql, "status") == "rejected"
        assert _extract_param_value(params_sql, "rejection_kind") == "merge"

    def test_rejected_ordinals_increment(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        for i in range(3):
            tracker.on_iteration_start({"iteration": i + 1})
            tracker.on_candidate_selected({"iteration": i + 1, "candidate_idx": 0})
            tracker.on_proposal_end(
                {"iteration": i + 1, "new_instructions": {"instruction": f"try {i}"}}
            )
            tracker.on_candidate_rejected(
                {"iteration": i + 1, "old_score": 1.0, "new_score": 0.5, "reason": "no"}
            )

        # Three rejections consume global counters ITER_1, ITER_2, ITER_3.
        assert "ITER_1" in tracker.persisted_runs
        assert "ITER_2" in tracker.persisted_runs
        assert "ITER_3" in tracker.persisted_runs
        # The per-model rejected ordinal moved from the run NAME into the
        # ``iteration`` param; it still increments 1, 2, 3 in reject order.
        for global_n, expected_ordinal in ((1, "1"), (2, "2"), (3, "3")):
            params_sql = next(
                s
                for s in sess.statements
                if f"MODIFY RUN ITER_{global_n} ADD PARAMETERS" in s
            )
            assert _extract_param_value(params_sql, "iteration") == expected_ordinal
            assert _extract_param_value(params_sql, "run_type") == "rejected"

    def test_merge_accept_clears_pending_state(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        tracker.on_merge_attempted(
            {"iteration": 1, "parent_ids": [0, 1], "merged_candidate": {"body": "x"}}
        )
        tracker.on_merge_accepted({"iteration": 1})

        assert len(tracker.persisted_runs) == 0


# ---------------------------------------------------------------------------
# Fault tolerance
# ---------------------------------------------------------------------------


class TestProgressiveTrackerFaultTolerance:
    def test_sql_failure_does_not_propagate(self):
        """A Snowflake error during a progressive write must not raise."""
        sess = _FakeSession(fail_on="ADD RUN")
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        tracker.on_iteration_start({"iteration": 1})
        tracker.on_candidate_selected({"iteration": 1, "candidate_idx": 0})
        tracker.on_proposal_end(
            {"iteration": 1, "new_instructions": {"instruction": "try"}}
        )
        tracker.on_candidate_accepted(
            {"iteration": 1, "new_candidate_idx": 1, "new_score": 1.5}
        )
        assert "ITER_1" not in tracker.persisted_runs

    def test_failed_iter_does_not_block_next_iter(self):
        """A failed write for one iteration must not prevent the next."""
        sess = _FakeSession(fail_on="ADD RUN ITER_1")
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        # First iteration fails
        tracker.on_iteration_start({"iteration": 1})
        tracker.on_candidate_selected({"iteration": 1, "candidate_idx": 0})
        tracker.on_proposal_end(
            {"iteration": 1, "new_instructions": {"instruction": "v1"}}
        )
        tracker.on_candidate_accepted(
            {"iteration": 1, "new_candidate_idx": 1, "new_score": 1.5}
        )
        assert "ITER_1" not in tracker.persisted_runs

        # Second iteration succeeds
        tracker.on_iteration_start({"iteration": 2})
        tracker.on_candidate_selected({"iteration": 2, "candidate_idx": 1})
        tracker.on_proposal_end(
            {"iteration": 2, "new_instructions": {"instruction": "v2"}}
        )
        tracker.on_candidate_accepted(
            {"iteration": 2, "new_candidate_idx": 2, "new_score": 1.8}
        )
        assert "ITER_2" in tracker.persisted_runs


# ---------------------------------------------------------------------------
# Integration: already_persisted_runs skips duplicate writes
# ---------------------------------------------------------------------------


class TestAlreadyPersistedRunsSkipping:
    def _base_kwargs(self):
        return dict(
            function_name="DB.S.FN",
            model="claude-haiku-4-5",
            seed_prompt="SEED",
            best_prompt="SEED",
            candidates=["SEED", "ITER1"],
            val_scores=[0.5, 0.8],
            best_idx=1,
        )

    def _base_stats(self, **extra):
        defaults: dict = dict(
            discovery_iter={0: 0, 1: 1},
            phase_breakdowns={0: _SEED_BREAKDOWN, 1: _ITER1_BREAKDOWN},
        )
        defaults.update(extra)
        return OptimizationRunStats(seed_val_score=0.5, best_val_score=0.8, **defaults)

    def test_seed_skipped_when_already_persisted(self):
        sess = _FakeSession()
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(already_persisted_runs={"CLAUDE_HAIKU_4_5_SEED"}),
        )

        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        seed_adds = [s for s in add_stmts if "SEED" in s and "REJECTED" not in s]
        assert len(seed_adds) == 0, "SEED should be skipped"

    def test_iter_skipped_when_already_persisted(self):
        sess = _FakeSession()
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(already_persisted_runs={"CLAUDE_HAIKU_4_5_ITER_1"}),
        )

        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        iter_adds = [s for s in add_stmts if "ITER_1" in s]
        assert len(iter_adds) == 0, "ITER_1 should be skipped"

    def test_best_always_written_even_if_iters_persisted(self):
        sess = _FakeSession()
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(
                already_persisted_runs={
                    "CLAUDE_HAIKU_4_5_SEED",
                    "CLAUDE_HAIKU_4_5_ITER_1",
                }
            ),
        )

        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        # v3: no BEST run; aggregate stats stamped on SEED run
        best_adds = [s for s in add_stmts if "BEST" in s]
        assert len(best_adds) == 0, "BEST run must NOT be written in v3 schema"

    def test_rejected_skipped_when_already_persisted(self):
        sess = _FakeSession()
        rejected = [
            RejectedCandidate(
                gepa_iteration=1,
                kind="reflective",
                candidate_text="bad",
                parent_candidate_idxs=[0],
                old_score=1.0,
                new_score=0.5,
                reason="worse",
            ),
        ]
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(
                rejected_candidates=rejected,
                already_persisted_runs={"CLAUDE_HAIKU_4_5_REJECTED_1"},
            ),
        )

        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        rejected_adds = [s for s in add_stmts if "REJECTED_1" in s]
        assert len(rejected_adds) == 0, "REJECTED_1 should be skipped"

    def test_no_already_persisted_writes_everything(self):
        sess = _FakeSession()
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            **self._base_kwargs(),
            stats=self._base_stats(already_persisted_runs=None),
        )

        add_stmts = [s for s in sess.statements if "ADD RUN" in s]
        assert any("SEED" in s for s in add_stmts)
        assert any("ITER_1" in s for s in add_stmts)
        # v3: no BEST run created; aggregate stats on SEED run
        assert not any("BEST" in s for s in add_stmts)


# ---------------------------------------------------------------------------
# Full lifecycle: tracker + save_optimization_to_experiment
# ---------------------------------------------------------------------------


class TestProgressiveTrackerFullLifecycle:
    """Simulate a full optimization: 2 iterations (1 rejected, 1
    accepted) → post-loop save.

    Under schema v4 the progressive tracker writes GLOBAL, model-agnostic
    runs (``ITER_1`` for the rejection, ``ITER_2`` for the acceptance) via
    the shared ``GlobalRunCounter``, and never writes the SEED run.  The
    post-loop ``save_optimization_to_experiment`` remains the LEGACY /
    evolve per-model save path (names like ``CLAUDE_HAIKU_4_5_SEED``); it
    is the one that creates the SEED run with full timing / aggregate
    stats.  This test verifies:

      * the progressive tracker persisted a rejected + an accepted GLOBAL
        run and left SEED alone, and
      * the post-loop save creates the SEED run carrying the aggregate
        stats, and creates no BEST run (v3+).

    Note (reinterpreted intent): the original test asserted the post-loop
    save skipped ITER_1 / REJECTED_1 via ``already_persisted_runs``.  That
    de-dup coupling no longer applies because the progressive path (global
    ``ITER_<N>`` names) and the legacy save path (per-model
    ``CLAUDE_HAIKU_4_5_*`` names) now live in disjoint name spaces; the
    two paths are not both live for a single model in v4.  The invariant
    that still holds — and that this test now asserts — is that the SEED
    run is written only by the post-loop save (never the tracker) and
    carries the aggregate stats, with no BEST run.
    """  # noqa: D205

    def test_full_flow_no_duplicates(self):
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )

        # Progressive: iteration 1 rejected
        tracker.on_iteration_start({"iteration": 1})
        tracker.on_candidate_selected({"iteration": 1, "candidate_idx": 0})
        tracker.on_proposal_end(
            {"iteration": 1, "new_instructions": {"instruction": "bad"}}
        )
        tracker.on_candidate_rejected(
            {"iteration": 1, "old_score": 1.0, "new_score": 0.5, "reason": "worse"}
        )

        # Progressive: iteration 2 accepted
        tracker.on_iteration_start({"iteration": 2})
        tracker.on_candidate_selected({"iteration": 2, "candidate_idx": 0})
        tracker.on_proposal_end(
            {"iteration": 2, "new_instructions": {"instruction": "improved"}}
        )
        tracker.on_candidate_accepted(
            {"iteration": 2, "new_candidate_idx": 1, "new_score": 1.8}
        )

        progressive_stmts = list(sess.statements)

        # Post-loop: save_optimization_to_experiment
        rejected = [
            RejectedCandidate(
                gepa_iteration=1,
                kind="reflective",
                candidate_text="bad",
                parent_candidate_idxs=[0],
                old_score=1.0,
                new_score=0.5,
                reason="worse",
            ),
        ]
        save_optimization_to_experiment(
            sess,
            "DB.S.EXP",
            function_name="DB.S.FN",
            model="claude-haiku-4-5",
            seed_prompt="be helpful",
            best_prompt="improved",
            candidates=["be helpful", "improved"],
            val_scores=[0.5, 0.9],
            best_idx=1,
            stats=OptimizationRunStats(
                seed_val_score=0.5,
                best_val_score=0.9,
                total_candidates=2,
                rejected_candidates=rejected,
                already_persisted_runs=tracker.persisted_runs,
                discovery_iter={0: 0, 1: 1},
                phase_breakdowns={0: _SEED_BREAKDOWN, 1: _ITER1_BREAKDOWN},
            ),
        )

        # Progressive tracker wrote GLOBAL runs: ITER_1 for the rejected
        # proposal and ITER_2 for the accepted candidate — never SEED.
        assert tracker.persisted_runs == {"ITER_1", "ITER_2"}
        assert "SEED" not in tracker.persisted_runs
        progressive_add_runs = [s for s in progressive_stmts if "ADD RUN" in s]
        assert any("ADD RUN ITER_1" in s for s in progressive_add_runs)
        assert any("ADD RUN ITER_2" in s for s in progressive_add_runs)
        # The rejected proposal carries rejected metadata, not a name.
        iter1_params = next(
            s for s in progressive_stmts if "MODIFY RUN ITER_1 ADD PARAMETERS" in s
        )
        assert _extract_param_value(iter1_params, "run_type") == "rejected"
        iter2_params = next(
            s for s in progressive_stmts if "MODIFY RUN ITER_2 ADD PARAMETERS" in s
        )
        assert _extract_param_value(iter2_params, "run_type") == "iteration"

        post_loop_stmts = sess.statements[len(progressive_stmts) :]
        post_loop_add_runs = [s for s in post_loop_stmts if "ADD RUN" in s]

        # Post-loop (legacy per-model save) SHOULD create the SEED run with
        # full timing data.  The tracker never touches SEED.
        # v3+: no BEST run; aggregate stats stamped on SEED run.
        assert any("SEED" in s for s in post_loop_add_runs), (
            "SEED must be created by post-loop save (has full timing data)"
        )
        assert not any("BEST" in s for s in post_loop_add_runs), (
            "BEST run must NOT be created in v3 schema"
        )

        # Verify aggregate stats are stamped on SEED (not winning ITER)
        modify_stmts = [s for s in sess.statements if "MODIFY RUN" in s]
        seed_agg = [
            s
            for s in modify_stmts
            if "MODIFY RUN CLAUDE_HAIKU_4_5_SEED ADD PARAMETERS" in s
            and "total_candidates" in s
        ]
        assert seed_agg, (
            "Aggregate stats (total_candidates) must be stamped on SEED run"
        )


# ---------------------------------------------------------------------------
# Per-iteration timing capture (regression for ITER_N / REJECTED_N rows
# rendering all per-iter columns as NULL because ProgressiveExperimentTracker
# wrote with minimal params and the post-loop save's rich data was skipped
# by ``already_persisted_runs``).
# ---------------------------------------------------------------------------


class _FakeTimingTracker:
    """Stand-in for the real ``TimingTracker`` snapshot + accumulator interface.

    Exposes the ``total_*`` properties read by ``_PhaseSnapshot.from_tracker``
    so we can drive the progressive tracker through a synthetic iteration
    and verify the per-iter delta makes it onto the persisted run.

    Mutable counters let the test simulate "work happened during the
    iteration" by simply bumping them between ``on_iteration_start`` and
    ``on_candidate_*``.

    The accumulator methods (``add_experiment`` / ``add_artifact_upload``
    / ``add_metric`` / etc.) are no-ops because the test directly mutates
    the totals.  They exist solely to satisfy ``_timed_experiment_sql``
    and ``add_experiment_run``, which would otherwise raise
    ``AttributeError`` and cause ``_safe_write`` to swallow the failure
    — silently masking the assertion the test is trying to make.
    """

    def __init__(self) -> None:
        self.total_metric_calls = 0
        self.total_metric_seconds = 0.0
        self.total_reflection_calls = 0
        self.total_reflection_seconds = 0.0
        self.total_udf_compile_calls = 0
        self.total_udf_compile_seconds = 0.0
        self.total_udf_exec_calls = 0
        self.total_udf_exec_seconds = 0.0
        self.total_experiment_calls = 0
        self.total_experiment_seconds = 0.0
        self.total_artifact_calls = 0
        self.total_artifact_seconds = 0.0

    # No-op accumulators — tests bump the ``total_*`` fields directly.
    def add_metric(self, duration: float) -> None: ...

    def add_metric_batch(self, *args, **kwargs) -> None: ...

    def add_reflection(self, duration: float) -> None: ...

    def add_udf_compile(self, duration: float) -> None: ...

    def add_udf_exec(self, duration: float) -> None: ...

    def add_experiment(self, duration: float, label: str = "") -> None: ...

    def add_artifact_upload(self, duration: float, label: str = "") -> None: ...

    def add_chars(self, *args, **kwargs) -> None: ...

    def add_tokens(self, *args, **kwargs) -> None: ...


def _bind_fake_tracker_for_test(tracker: _FakeTimingTracker | None):
    """Bind ``tracker`` as the active TLS tracker for the current thread.

    Returns a callable that restores the previous binding on exit.
    Mirrors :func:`core_timing.set_active_tracker` so the test
    drives the same code path that body / prompt mode hit at runtime.
    """
    from snowflake_ai_optimize.core.timing import get_active_tracker, set_active_tracker

    prev = get_active_tracker()
    set_active_tracker(tracker)

    def _restore() -> None:
        set_active_tracker(prev)

    return _restore


class TestProgressiveTrackerPerIterationTiming:
    """Regression: progressive ITER_N / REJECTED_N writes must include
    per-iteration tracker totals so the BENCH_TRACKING_DETAILS columns
    (``metric_call_count``, ``reflection_call_count``,
    ``udf_compile_count``, ``udf_exec_count``, ``experiment_count``,
    ``artifact_count``, plus their ``*_seconds_total`` companions) are
    populated.

    The original bug: ``ProgressiveExperimentTracker`` wrote its runs
    with only a handful of identifying params (``function_impl``,
    ``model``, ``iteration``, ``parent_candidate``, ``gepa_iteration``,
    ``status`` and a few rejection-specific fields).  The rich post-loop
    ``save_optimization_to_experiment`` then skipped these runs via
    ``already_persisted_runs`` — so every ITER_N / REJECTED_N row in
    BENCH_TRACKING_DETAILS rendered all per-iter timing columns as
    ``—``, making accepted-vs-rejected cost comparison impossible.

    The fix snaps the tracker at ``on_iteration_start`` and again at
    write time and stamps the delta on the run via
    :meth:`ProgressiveExperimentTracker._per_iter_kwargs`.
    """  # noqa: D205

    def _extract_param_value(self, add_params_stmt: str, param_name: str) -> str | None:
        """Pull a single param value out of an ALTER ADD PARAMETERS SQL.

        Params are serialised as a JSON array of ``{"name": ..., "value": ...}``
        objects.  We do a substring-then-bracket-pair extraction so the
        test doesn't have to import the SQL formatter.
        """
        import json
        import re

        m = re.search(r"ADD PARAMETERS\s*=\s*'(\[.*?\])'", add_params_stmt, re.DOTALL)
        if not m:
            return None
        # Reverse the SQL string-escape applied at write time
        # (see the JSON-quote escape in build_run_params' ALTER call).
        raw = m.group(1).replace(r"\'", "'").replace(r"\\", "\\")
        try:
            params = json.loads(raw)
        except json.JSONDecodeError:
            return None
        for p in params:
            if p.get("name") == param_name:
                return str(p.get("value"))
        return None

    def test_accepted_iter_persists_per_iter_tracker_delta(self):
        """End-to-end: drive an accepted iteration through the tracker
        with mock TimingTracker totals and assert the delta lands in
        the ALTER ADD PARAMETERS payload.
        """  # noqa: D205
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        timing = _FakeTimingTracker()
        restore = _bind_fake_tracker_for_test(timing)
        try:
            # Iteration starts — snap the baseline.
            tracker.on_iteration_start({"iteration": 1})

            # Simulate work during the iteration: 5 metric calls (0.25s),
            # 1 reflection call (3s), 2 udf_exec calls (1.4s), and one
            # experiment write (0.05s) for the rejected proposal that
            # preceded acceptance.
            timing.total_metric_calls = 5
            timing.total_metric_seconds = 0.25
            timing.total_reflection_calls = 1
            timing.total_reflection_seconds = 3.0
            timing.total_udf_exec_calls = 2
            timing.total_udf_exec_seconds = 1.4
            timing.total_experiment_calls = 1
            timing.total_experiment_seconds = 0.05

            tracker.on_candidate_selected({"iteration": 1, "candidate_idx": 0})
            tracker.on_proposal_end(
                {"iteration": 1, "new_instructions": {"instruction": "improved"}}
            )
            tracker.on_candidate_accepted(
                {"iteration": 1, "new_candidate_idx": 1, "new_score": 1.8}
            )
        finally:
            restore()

        # The progressive write uses two SQL calls: ADD RUN (no params)
        # then MODIFY RUN ADD PARAMETERS (with the build_run_params JSON).
        params_stmts = [
            s for s in sess.statements if "ADD PARAMETERS" in s and "ITER_1" in s
        ]
        assert len(params_stmts) >= 1, (
            f"expected an ADD PARAMETERS for ITER_1, got: {sess.statements}"
        )
        params_sql = params_stmts[0]

        # Per-iter counts must reflect the synthetic deltas.  We assert
        # the *integer* / *string* form because that's what
        # build_run_params serialises into the JSON.
        assert self._extract_param_value(params_sql, "metric_call_count") == "5"
        assert self._extract_param_value(params_sql, "reflection_call_count") == "1"
        assert self._extract_param_value(params_sql, "udf_exec_count") == "2"
        assert self._extract_param_value(params_sql, "experiment_count") == "1"
        # Seconds may render with trailing decimals; just check the
        # numeric portion is present (Snowflake will parse as FLOAT).
        assert "0.25" in (
            self._extract_param_value(params_sql, "metric_seconds_total") or ""
        )
        # ``num_examples`` falls out of metric_call_count.
        assert self._extract_param_value(params_sql, "num_examples") == "5"

    def test_rejected_iter_persists_per_iter_tracker_delta(self):
        """Same regression for rejected runs (now global ITER_N rows)."""
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        timing = _FakeTimingTracker()
        restore = _bind_fake_tracker_for_test(timing)
        try:
            tracker.on_iteration_start({"iteration": 7})
            # Work on the rejected proposal: parent eval + reflection +
            # new-cand eval all happen before the rejection event fires.
            timing.total_metric_calls = 4
            timing.total_metric_seconds = 0.18
            timing.total_reflection_calls = 1
            timing.total_reflection_seconds = 2.5
            tracker.on_candidate_selected({"iteration": 7, "candidate_idx": 0})
            tracker.on_proposal_end(
                {"iteration": 7, "new_instructions": {"instruction": "bad"}}
            )
            tracker.on_candidate_rejected(
                {
                    "iteration": 7,
                    "old_score": 1.0,
                    "new_score": 0.5,
                    "reason": "worse",
                }
            )
        finally:
            restore()

        # One reject event -> global counter N=1 -> run name "ITER_1"
        # (rejection is distinguished by run_type/status params, not name).
        params_stmts = [
            s for s in sess.statements if "ADD PARAMETERS" in s and "ITER_1" in s
        ]
        assert len(params_stmts) >= 1, (
            f"expected an ADD PARAMETERS for ITER_1, got: {sess.statements}"
        )
        params_sql = params_stmts[0]
        assert self._extract_param_value(params_sql, "run_type") == "rejected"
        assert self._extract_param_value(params_sql, "metric_call_count") == "4"
        assert self._extract_param_value(params_sql, "reflection_call_count") == "1"

    def test_accepted_iter_persists_per_phase_breakdown(self):
        """Per-phase breakdown columns (``parent_eval_seconds`` /
        ``phase_reflection_seconds`` / ``new_cand_eval_seconds`` plus
        per-phase chars + minibatch sizes) must land on the persisted
        ITER_N row.

        Regression: ``ProgressiveExperimentTracker`` previously
        inherited the base class's no-op lifecycle methods that did not
        capture per-phase snapshots, so ``self._reflective.phase_breakdown()``
        always returned zeros — and the report's per-phase columns
        rendered as ``—`` even though the optimizer's own
        ``RejectedCandidateCollector`` had captured the same data
        (which the post-loop save would have written, except the
        ``already_persisted_runs`` skip prevented that).

        The fix hoists per-phase snapshot capture into the base class
        so both subclasses see populated snapshots at ``on_candidate_*``
        time without duplicated overrides.
        """  # noqa: D205
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        timing = _FakeTimingTracker()
        restore = _bind_fake_tracker_for_test(timing)
        try:
            tracker.on_iteration_start({"iteration": 1})
            tracker.on_candidate_selected({"iteration": 1, "candidate_idx": 0})

            # --- Parent eval phase: 3 metric calls + 1 udf_exec.
            tracker.on_evaluation_start({"iteration": 1, "candidate_idx": 0})
            timing.total_metric_calls = 3
            timing.total_metric_seconds = 0.12
            timing.total_udf_exec_calls = 1
            timing.total_udf_exec_seconds = 0.6
            tracker.on_evaluation_end(
                {
                    "iteration": 1,
                    "candidate_idx": 0,
                    "scores": [0.5, 0.6, 0.4],  # minibatch size 3
                }
            )

            # --- Reflection phase: 1 reflection LLM call.
            tracker.on_proposal_start({"iteration": 1})
            timing.total_reflection_calls = 1
            timing.total_reflection_seconds = 2.5
            tracker.on_proposal_end(
                {"iteration": 1, "new_instructions": {"instruction": "improved"}}
            )

            # --- New-cand eval phase: 3 metric calls + 1 udf_exec.
            tracker.on_evaluation_start({"iteration": 1, "candidate_idx": None})
            timing.total_metric_calls = 6
            timing.total_metric_seconds = 0.24
            timing.total_udf_exec_calls = 2
            timing.total_udf_exec_seconds = 1.3
            tracker.on_evaluation_end(
                {
                    "iteration": 1,
                    "candidate_idx": None,
                    "scores": [0.7, 0.8, 0.9],  # minibatch size 3
                }
            )

            # --- Acceptance.
            tracker.on_candidate_accepted(
                {"iteration": 1, "new_candidate_idx": 1, "new_score": 2.4}
            )
        finally:
            restore()

        params_stmts = [
            s for s in sess.statements if "ADD PARAMETERS" in s and "ITER_1" in s
        ]
        assert len(params_stmts) >= 1
        params_sql = params_stmts[0]

        # Per-phase wall-clock (seconds) MUST be present.  The numeric
        # value depends on real perf_counter() time between the
        # ``on_evaluation_start`` and ``on_evaluation_end`` calls (which
        # the test fires back-to-back, so the duration may round to
        # ``0.0`` at 4 decimal places).  The regression we're guarding
        # against is the field being ABSENT from the persisted params
        # (which previously caused the BENCH_TRACKING_DETAILS row to
        # render as ``—`` on the report), so we assert presence + valid
        # float-coercibility, not strictly positive duration.
        for phase_name in (
            "parent_eval_seconds",
            "phase_reflection_seconds",
            "new_cand_eval_seconds",
        ):
            value = self._extract_param_value(params_sql, phase_name)
            assert value is not None, (
                f"{phase_name} missing from progressive write — base class "
                "snapshot capture must populate the phase deltas."
            )
            assert float(value) >= 0.0, f"{phase_name}={value!r} not a number"
        # Per-phase minibatch size — captured by the base class's
        # on_evaluation_end snapshot from the ``scores`` list length.
        assert (
            self._extract_param_value(params_sql, "new_cand_eval_minibatch_size") == "3"
        )
        assert (
            self._extract_param_value(params_sql, "parent_eval_minibatch_size") == "3"
        )

    def test_no_active_tracker_degrades_gracefully(self):
        """Without an active TimingTracker, per-iter fields are simply
        absent (build_run_params skips None / 0 by default) but the run
        itself is still written.  This protects callers that wire the
        progressive tracker without a TLS tracker bound (e.g. ad-hoc
        unit tests, degraded paths).
        """  # noqa: D205
        sess = _FakeSession()
        tracker = ProgressiveExperimentTracker(
            session=sess,
            experiment_name="DB.S.EXP",
            model="claude-haiku-4-5",
            function_name="DB.S.FN",
            run_counter=GlobalRunCounter(),
        )
        # Don't bind any tracker.
        tracker.on_iteration_start({"iteration": 1})
        tracker.on_candidate_selected({"iteration": 1, "candidate_idx": 0})
        tracker.on_proposal_end(
            {"iteration": 1, "new_instructions": {"instruction": "v1"}}
        )
        tracker.on_candidate_accepted(
            {"iteration": 1, "new_candidate_idx": 1, "new_score": 1.5}
        )
        # Run is still persisted — the absence of a tracker just means
        # zero deltas, not a hard failure.
        assert "ITER_1" in tracker.persisted_runs
