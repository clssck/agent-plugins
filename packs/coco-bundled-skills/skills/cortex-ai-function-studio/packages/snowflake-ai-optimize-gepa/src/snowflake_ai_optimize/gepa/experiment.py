# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.
"""Snowflake Experiment storage helpers for GEPA optimization.

This module wraps the native Snowflake Experiment DDL so that GEPA
optimization results can be persisted as first-class experiment objects
instead of ad-hoc tracking tables.

Supported DDL (validated by Snowfort tests):
  W1: CREATE EXPERIMENT IF NOT EXISTS
  W2: ALTER EXPERIMENT ... ADD RUN / MODIFY RUN ADD PARAMETERS/METRICS
  W3: PUT file:// snow://experiment/...  (eval detail)
  W4: PUT file:// snow://experiment/.../run_dir/  (GEPA artifacts)
  W5: ALTER EXPERIMENT ... COMMIT RUN
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from snowflake.snowpark import Session
from snowflake.snowpark.exceptions import SnowparkSessionException

from snowflake_ai_optimize.core.experiment import (
    SEED_RUN_NAME,
    GlobalRunCounter,
    ParetoCandidateInfo,
    add_experiment_run,
    build_run_metrics,
    commit_experiment_run,
    create_experiment,
    estimate_candidate_cost,
    make_iter_run_name,
    make_run_name,
    put_experiment_artifact,
    safe_float,
    timed_experiment_sql,
    write_eval_detail_artifact,
)
from snowflake_ai_optimize.core.run_params import RunParams
from snowflake_ai_optimize.core.sql_utils import escape_sql_string
from snowflake_ai_optimize.core.timing import get_active_tracker
from snowflake_ai_optimize.gepa.adapter import candidate_detail_key

# Backward-compat alias: callers that import ``create_gepa_experiment`` from
# this module continue to work until they switch to ``create_experiment``.
create_gepa_experiment = create_experiment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Experiment schema version
# ---------------------------------------------------------------------------
# Stamped on every SEED run as the ``experiment_schema_version`` param so a
# reader of ``SHOW RUNS`` can tell which run-naming contract wrote the set.
# Bump when the param/run-naming contract changes.
#   1 — legacy: SEED + ITER_N + BEST only (rejected proposals unpersisted)
#   2 — added <MODEL>_REJECTED_N runs + per-iteration counters (full history)
#   3 — removed MODEL_BEST; aggregate stats on <MODEL>_SEED
#   4 — global SEED + ITER_<N> across all models (GEPA body/prompt); model is a
#       param, role is run_type, per-model totals in per_model_stats on the one
#       SEED; frontier via is_frontier metric (PR #81). Evolve still writes v3.
EXPERIMENT_SCHEMA_VERSION: int = 4


# ---------------------------------------------------------------------------
# Rejected-candidate capture: dataclass + GEPA callback collector
# ---------------------------------------------------------------------------
#
# GEPA proposes new candidates each iteration via reflection (and
# optionally merge).  The engine then evaluates the proposal on the
# minibatch and ACCEPTS it (full-eval + add to population) only when
# ``sum(new_scores) > sum(old_scores)``.  Rejected proposals never
# reach the population, so without an explicit hook they never appear
# in the experiment object — even though we paid for the reflection
# LLM call + a temp-UDF compile + the minibatch eval that produced
# the rejection.  This collector listens for the GEPA callback events
# the engine fires on each accept/reject decision and snapshots
# enough state to write one ``REJECTED_N`` run per rejected proposal,
# alongside the SEED / ITER_N / BEST runs the optimizer already
# persists.


@dataclass
class _PhaseSnapshot:
    """Tracker totals captured at a single phase boundary.

    GEPA's reflective iteration has three time-distinguishable phases:
      1. Parent re-evaluation on the minibatch (between
         ``on_evaluation_start(candidate_idx=parent_idx)`` and
         ``on_evaluation_end(candidate_idx=parent_idx)``).
      2. Reflection LLM call (between ``on_proposal_start`` and
         ``on_proposal_end``).
      3. New-candidate evaluation on the same minibatch (between
         ``on_evaluation_start(candidate_idx=None)`` and
         ``on_evaluation_end(candidate_idx=None)``).

    By snapshotting tracker totals at each boundary and diffing
    consecutive snapshots we produce honest, non-overlapping per-phase
    counters.  An iteration's total cost is the sum of its phase
    deltas (plus any post-accept full-valset eval, attributed to the
    accepted run separately).
    """

    metric_call_count: int = 0
    metric_seconds_total: float = 0.0
    reflection_call_count: int = 0
    reflection_seconds_total: float = 0.0
    udf_compile_count: int = 0
    udf_compile_seconds_total: float = 0.0
    udf_exec_count: int = 0
    udf_exec_seconds_total: float = 0.0
    # Experiment + artifact bookkeeping totals — included so a
    # full-iteration snapshot diff (used by ProgressiveExperimentTracker
    # for per-iter timing on ITER_N / REJECTED_N rows) reports honest
    # experiment-DDL and artifact-PUT cost incurred during the iteration
    # (e.g. by the progressive write of THIS iteration's run).  Phase-level
    # snapshots (parent_eval / reflection / new_cand_eval) ignore these
    # fields because no experiment writes happen inside those windows.
    experiment_count: int = 0
    experiment_seconds_total: float = 0.0
    artifact_count: int = 0
    artifact_seconds_total: float = 0.0
    perf_seconds: float = 0.0  # wall_clock at snapshot
    # Token-cost char totals — sum across all (model, kind) buckets
    # at this snapshot point.  Per-iteration deltas drive the cost
    # column on each ITER/REJECTED row (and the cumulative-cost x-axis
    # on the Pareto plot).
    input_chars: int = 0
    output_chars: int = 0
    # Per-kind char totals (added 2026-05).  ``eval_*`` covers the
    # ``("udf", *)`` buckets, ``reflection_*`` covers
    # ``("reflection", *)``.  Their sum equals ``input_chars`` /
    # ``output_chars``.  Splitting them at the snapshot level lets
    # ``IterationPhaseBreakdown`` emit a per-iteration reflection-only
    # token estimate (chars/4) and a per-iteration evaluation-only
    # token total — both of which feed the new token Gantt chart and
    # the per-iteration token breakdown columns in BENCH_TRACKING_DETAILS.
    eval_input_chars: int = 0
    eval_output_chars: int = 0
    reflection_input_chars: int = 0
    reflection_output_chars: int = 0
    # REAL token counts from AI_COMPLETE's ``usage`` block, sourced
    # from the inline-eval migration's ``show_details=>TRUE`` injection.
    # Only populated for the ``("udf", *)`` buckets — reflection's
    # AI_COMPLETE call still runs with show_details=False so the
    # ``usage`` block is dropped.  Per-iteration deltas surface as the
    # ``new_cand_eval_prompt_tokens`` / ``parent_eval_prompt_tokens``
    # experiment params on each ITER_N / REJECTED_N run.
    eval_prompt_tokens: int = 0
    eval_completion_tokens: int = 0

    @classmethod
    def from_tracker(cls, tracker: Any) -> _PhaseSnapshot:
        """Snapshot the active tracker's running totals.

        Returns a zeroed snapshot if ``tracker`` is None — the caller
        can still diff two zeros and get a zero phase delta, which is
        the correct fallback when tracker wiring is somehow missing.
        """
        import time as _time

        if tracker is None:
            return cls(perf_seconds=_time.perf_counter())
        in_chars = 0
        out_chars = 0
        eval_in = 0
        eval_out = 0
        ref_in = 0
        ref_out = 0
        try:
            for (_, kind), bucket in tracker.char_usage_snapshot.items():
                ic = int(bucket.get("input_chars") or 0)
                oc = int(bucket.get("output_chars") or 0)
                in_chars += ic
                out_chars += oc
                if kind == "udf":
                    eval_in += ic
                    eval_out += oc
                elif kind == "reflection":
                    ref_in += ic
                    ref_out += oc
        except AttributeError:
            # Older tracker without char_usage_snapshot — char counts
            # stay zero, dollar computation collapses to zero, no harm.
            pass
        eval_pt = 0
        eval_ct = 0
        try:
            for (_, kind), bucket in tracker.token_usage_snapshot.items():
                if kind != "udf":
                    continue
                eval_pt += int(bucket.get("prompt_tokens") or 0)
                eval_ct += int(bucket.get("completion_tokens") or 0)
        except AttributeError:
            # Older tracker without ``token_usage_snapshot`` (pre-2026-05
            # inline-eval migration).  Eval token counts collapse to
            # zero and downstream experiment params land as ``None``,
            # which the renderer treats the same way as legacy rows.
            pass
        return cls(
            metric_call_count=tracker.total_metric_calls,
            metric_seconds_total=tracker.total_metric_seconds,
            reflection_call_count=tracker.total_reflection_calls,
            reflection_seconds_total=tracker.total_reflection_seconds,
            udf_compile_count=tracker.total_udf_compile_calls,
            udf_compile_seconds_total=tracker.total_udf_compile_seconds,
            udf_exec_count=tracker.total_udf_exec_calls,
            udf_exec_seconds_total=tracker.total_udf_exec_seconds,
            experiment_count=tracker.total_experiment_calls,
            experiment_seconds_total=tracker.total_experiment_seconds,
            artifact_count=tracker.total_artifact_calls,
            artifact_seconds_total=tracker.total_artifact_seconds,
            perf_seconds=_time.perf_counter(),
            input_chars=in_chars,
            output_chars=out_chars,
            eval_input_chars=eval_in,
            eval_output_chars=eval_out,
            reflection_input_chars=ref_in,
            reflection_output_chars=ref_out,
            eval_prompt_tokens=eval_pt,
            eval_completion_tokens=eval_ct,
        )


@dataclass
class _PhaseDelta:
    """Difference between two ``_PhaseSnapshot``s.

    All fields are clamped at zero (a negative delta would indicate
    a snapshot order mistake; clamp + carry on rather than abort the
    optimization).
    """

    seconds: float = 0.0
    metric_call_count: int = 0
    metric_seconds_total: float = 0.0
    reflection_call_count: int = 0
    reflection_seconds_total: float = 0.0
    udf_compile_count: int = 0
    udf_compile_seconds_total: float = 0.0
    udf_exec_count: int = 0
    udf_exec_seconds_total: float = 0.0
    # Experiment + artifact bookkeeping deltas — surfaced on full-iteration
    # snapshots only; phase-level snapshots leave these at zero because no
    # experiment writes happen inside reflective phase windows.
    experiment_count: int = 0
    experiment_seconds_total: float = 0.0
    artifact_count: int = 0
    artifact_seconds_total: float = 0.0
    input_chars: int = 0
    output_chars: int = 0
    # Per-kind char + token deltas (added 2026-05 for the per-call
    # token Gantt and the per-iteration token breakdown columns).
    # Mirrors the split fields on ``_PhaseSnapshot``; clamping at
    # zero matches the existing behaviour for the totals.
    eval_input_chars: int = 0
    eval_output_chars: int = 0
    reflection_input_chars: int = 0
    reflection_output_chars: int = 0
    eval_prompt_tokens: int = 0
    eval_completion_tokens: int = 0

    @classmethod
    def between(
        cls, before: _PhaseSnapshot | None, after: _PhaseSnapshot | None
    ) -> _PhaseDelta:
        if before is None or after is None:
            return cls()
        return cls(
            seconds=max(0.0, after.perf_seconds - before.perf_seconds),
            metric_call_count=max(
                0, after.metric_call_count - before.metric_call_count
            ),
            metric_seconds_total=max(
                0.0, after.metric_seconds_total - before.metric_seconds_total
            ),
            reflection_call_count=max(
                0, after.reflection_call_count - before.reflection_call_count
            ),
            reflection_seconds_total=max(
                0.0,
                after.reflection_seconds_total - before.reflection_seconds_total,
            ),
            udf_compile_count=max(
                0, after.udf_compile_count - before.udf_compile_count
            ),
            udf_compile_seconds_total=max(
                0.0,
                after.udf_compile_seconds_total - before.udf_compile_seconds_total,
            ),
            udf_exec_count=max(0, after.udf_exec_count - before.udf_exec_count),
            udf_exec_seconds_total=max(
                0.0, after.udf_exec_seconds_total - before.udf_exec_seconds_total
            ),
            experiment_count=max(0, after.experiment_count - before.experiment_count),
            experiment_seconds_total=max(
                0.0,
                after.experiment_seconds_total - before.experiment_seconds_total,
            ),
            artifact_count=max(0, after.artifact_count - before.artifact_count),
            artifact_seconds_total=max(
                0.0, after.artifact_seconds_total - before.artifact_seconds_total
            ),
            input_chars=max(0, after.input_chars - before.input_chars),
            output_chars=max(0, after.output_chars - before.output_chars),
            eval_input_chars=max(0, after.eval_input_chars - before.eval_input_chars),
            eval_output_chars=max(
                0, after.eval_output_chars - before.eval_output_chars
            ),
            reflection_input_chars=max(
                0, after.reflection_input_chars - before.reflection_input_chars
            ),
            reflection_output_chars=max(
                0, after.reflection_output_chars - before.reflection_output_chars
            ),
            eval_prompt_tokens=max(
                0, after.eval_prompt_tokens - before.eval_prompt_tokens
            ),
            eval_completion_tokens=max(
                0, after.eval_completion_tokens - before.eval_completion_tokens
            ),
        )

    @property
    def reflection_prompt_tokens_est(self) -> int:
        """Char-based estimate of reflection prompt tokens (chars // 4)."""
        return self.reflection_input_chars // 4

    @property
    def reflection_completion_tokens_est(self) -> int:
        """Char-based estimate of reflection completion tokens (chars // 4)."""
        return self.reflection_output_chars // 4


@dataclass
class IterationPhaseBreakdown:
    """Per-iteration phase decomposition for one GEPA iteration.

    Stored on the collector keyed by ``gepa_iteration`` so both the
    accepted ITER run (for its discovery iter) and the REJECTED run
    (for its rejection iter) can pick up an honest per-phase cost
    breakdown.  Sum of the three phases + any post-accept full-valset
    eval attributed to ITER separately equals the iteration's total
    wall-clock cost — no double counting between ITER and REJECTED.

    The two ``*_minibatch_size`` fields record the number of rows
    evaluated in each evaluation phase (typically the same — GEPA
    evaluates parent and new-cand on the SAME minibatch — but
    captured separately as a defensive measure).  Together with the
    per-phase chars they give the renderer the data needed to
    compute a per-call inference cost: ``new_cand_eval.input_chars
    / new_cand_eval_minibatch_size`` is the average input chars
    needed to invoke this candidate ONCE on a single input row.
    """

    parent_eval: _PhaseDelta = field(default_factory=_PhaseDelta)
    reflection: _PhaseDelta = field(default_factory=_PhaseDelta)
    new_cand_eval: _PhaseDelta = field(default_factory=_PhaseDelta)
    parent_eval_minibatch_size: int = 0
    new_cand_eval_minibatch_size: int = 0

    def total_input_chars(self) -> int:
        return (
            self.parent_eval.input_chars
            + self.reflection.input_chars
            + self.new_cand_eval.input_chars
        )

    def total_output_chars(self) -> int:
        return (
            self.parent_eval.output_chars
            + self.reflection.output_chars
            + self.new_cand_eval.output_chars
        )

    # Per-iteration token aggregates (added 2026-05) — used by the
    # benchmark experiment writer to populate the new ``iter_eval_*``
    # / ``iter_reflection_*_est`` params on every ITER_N / REJECTED_N
    # run.  Eval tokens are REAL (sourced from AI_COMPLETE's usage
    # block); reflection tokens are CHAR-BASED ESTIMATES (chars // 4)
    # because the reflection AI_COMPLETE call still runs with
    # show_details=False.
    def total_eval_prompt_tokens(self) -> int:
        return (
            self.parent_eval.eval_prompt_tokens + self.new_cand_eval.eval_prompt_tokens
        )

    def total_eval_completion_tokens(self) -> int:
        return (
            self.parent_eval.eval_completion_tokens
            + self.new_cand_eval.eval_completion_tokens
        )

    def total_reflection_prompt_tokens_est(self) -> int:
        return self.reflection.reflection_prompt_tokens_est

    def total_reflection_completion_tokens_est(self) -> int:
        return self.reflection.reflection_completion_tokens_est


@dataclass
class RejectedCandidate:
    """One GEPA-proposed candidate that the engine rejected.

    Captured in real time via ``RejectedCandidateCollector`` (which
    listens to GEPA's ``on_candidate_rejected`` / ``on_merge_rejected``
    callback events) and later persisted as ``{MODEL}_REJECTED_{N}``
    experiment runs by ``save_optimization_to_experiment``.

    Fields:
        gepa_iteration: 1-indexed GEPA iteration in which the proposal
            was tried.  Matches the ``iteration`` field on
            ``CandidateRejectedEvent`` / ``MergeRejectedEvent``.
            Stored as a separate ``gepa_iteration`` parameter on the
            resulting REJECTED run (NOT used as the ``iteration``
            param — see ``save_optimization_to_experiment_impl`` for
            why we use the rejection ordinal there instead).
        kind: ``"reflective"`` or ``"merge"``.
        candidate_text: The proposed text.
        parent_candidate_idxs: Parent indices.
        old_score / new_score: Subsample sums from GEPA.
        subsample_size: Minibatch size (for per-row mean).
        reason: Human-readable rejection reason from GEPA.
        phase_breakdown: Per-phase delta (parent_eval, reflection,
            new_cand_eval).  ``None`` for merge rejections (no GEPA
            event surfaces those subsample boundaries).
    """

    gepa_iteration: int
    kind: str
    candidate_text: str
    parent_candidate_idxs: list[int]
    old_score: float | None
    new_score: float | None
    reason: str
    subsample_size: int | None = None
    phase_breakdown: IterationPhaseBreakdown | None = None


@dataclass
class _ReflectivePending:
    """Mutable scratch state for an in-flight reflective iteration."""

    iteration: int | None = None
    parent_idx: int | None = None
    candidate_text: str | None = None
    # ``subsample_size`` is the new-candidate eval's minibatch size
    # (kept for backward-compat — RejectedCandidate.subsample_size
    # still reads from here).  ``parent_eval_minibatch_size`` is
    # the parent's eval batch size, captured separately so the
    # renderer can derive SEED's per-call cost from ITER_1's parent
    # eval (when that parent IS SEED).
    subsample_size: int | None = None
    parent_eval_minibatch_size: int | None = None
    # Per-phase snapshots — populated as the engine fires the
    # corresponding events.  Diffs between successive snapshots give
    # us the honest per-phase cost.
    snap_iter_start: _PhaseSnapshot | None = None
    snap_parent_eval_start: _PhaseSnapshot | None = None
    snap_parent_eval_end: _PhaseSnapshot | None = None
    snap_proposal_start: _PhaseSnapshot | None = None
    snap_proposal_end: _PhaseSnapshot | None = None
    snap_new_cand_eval_start: _PhaseSnapshot | None = None
    snap_new_cand_eval_end: _PhaseSnapshot | None = None

    def phase_breakdown(self) -> IterationPhaseBreakdown:
        """Build the breakdown from accumulated snapshots."""
        return IterationPhaseBreakdown(
            parent_eval=_PhaseDelta.between(
                self.snap_parent_eval_start, self.snap_parent_eval_end
            ),
            reflection=_PhaseDelta.between(
                self.snap_proposal_start, self.snap_proposal_end
            ),
            new_cand_eval=_PhaseDelta.between(
                self.snap_new_cand_eval_start, self.snap_new_cand_eval_end
            ),
            parent_eval_minibatch_size=int(self.parent_eval_minibatch_size or 0),
            new_cand_eval_minibatch_size=int(self.subsample_size or 0),
        )


@dataclass
class _MergePending:
    """Mutable scratch state for an in-flight merge attempt."""

    iteration: int | None = None
    parent_idxs: list[int] = field(default_factory=list)
    candidate_text: str | None = None


class _GEPAIterationTracker:
    """Shared state and event parsing for GEPA iteration lifecycle.

    Both ``RejectedCandidateCollector`` and ``ProgressiveExperimentTracker``
    implement the duck-typed ``GEPACallback`` interface and share common
    scratch-state management (``_ReflectivePending`` / ``_MergePending``).
    This base class provides:

    - ``_reflective`` / ``_merge`` pending-state lifecycle
    - Common event parsing: iteration start, candidate selection,
      evaluation end (subsample size), proposal end, merge lifecycle
    - **Per-phase snapshot capture** at every reflective phase boundary
      (``on_iteration_start`` / ``on_evaluation_start`` /
      ``on_evaluation_end`` / ``on_proposal_start`` / ``on_proposal_end``)
      so ``self._reflective.phase_breakdown()`` always returns honest
      parent_eval / reflection / new_cand_eval deltas — both subclasses
      now read the breakdown at write time without duplicating the
      snap-capture logic.  Previously only ``RejectedCandidateCollector``
      captured these snapshots, so the progressively-persisted ITER_N /
      REJECTED_N runs landed with all three ``*_seconds`` columns NULL
      on BENCH_TRACKING_DETAILS — making per-phase cost comparison
      impossible to read on the report.
    - ``_component_text`` helper for extracting single-component text

    Subclasses override the "action" methods (``on_candidate_accepted``,
    ``on_candidate_rejected``, ``on_merge_rejected``) and optionally
    extend other lifecycle hooks for extra work (e.g.
    ProgressiveExperimentTracker overrides ``on_iteration_start`` to
    additionally snap a full-iteration baseline for tracker totals).

    All methods are duck-typed (matched at runtime via ``hasattr``);
    we deliberately do not subclass / register against the GEPA protocol
    so ``gepa`` stays an optional import in the inline-SPROC bundle.

    Thread safety: each model thread owns its own callback instance.
    """

    def __init__(self) -> None:
        self._reflective: _ReflectivePending = _ReflectivePending()
        self._merge: _MergePending = _MergePending()

    @staticmethod
    def _component_text(components: dict[str, str] | None) -> str:
        """Pull the single-component text from a GEPA candidate dict.

        Cortex Code only ever optimizes one component (system prompt
        in prompt mode, function body in body mode) so we collapse
        the dict to its sole value.  Empty / missing dicts collapse
        to ``""`` rather than raising — a missing text is unfortunate
        but should not break optimization.
        """
        if not components:
            return ""
        try:
            return str(next(iter(components.values())) or "")
        except StopIteration:
            return ""

    def _snap(self) -> _PhaseSnapshot:
        """Snapshot the active TimingTracker.  None-tolerant.

        Returns a zeroed snapshot if no TLS tracker is bound (e.g. ad-hoc
        tests, degraded paths) — diffing two zeros gives a zero phase
        delta which is the correct fallback when tracker wiring is somehow missing.
        """
        tracker = None
        # Try direct global first (works in inline SPROC where all code is
        # concatenated into one flat module).
        with contextlib.suppress(NameError):
            tracker = get_active_tracker()
        # Fall back to module import (works in normal multi-file execution).
        if tracker is None:
            try:
                import importlib

                mod = importlib.import_module("snowflake_ai_optimize.gepa.adapter")
                getter = getattr(mod, "get_active_tracker", None)
                tracker = getter() if getter is not None else None
            except Exception:
                pass
        return _PhaseSnapshot.from_tracker(tracker)

    # -- reflective lifecycle (common) --------------------------------

    def on_iteration_start(self, event: dict) -> None:
        self._reflective = _ReflectivePending(
            iteration=int(event.get("iteration", 0)),
            snap_iter_start=self._snap(),
        )

    def on_candidate_selected(self, event: dict) -> None:
        self._reflective.parent_idx = (
            int(event["candidate_idx"])
            if event.get("candidate_idx") is not None
            else None
        )

    def on_evaluation_start(self, event: dict) -> None:
        if event.get("candidate_idx") is None:
            self._reflective.snap_new_cand_eval_start = self._snap()
        else:
            self._reflective.snap_parent_eval_start = self._snap()

    def on_evaluation_end(self, event: dict) -> None:
        scores = event.get("scores")
        size = len(scores) if isinstance(scores, list) else None
        if event.get("candidate_idx") is None:
            self._reflective.snap_new_cand_eval_end = self._snap()
            if size is not None:
                self._reflective.subsample_size = size
        else:
            self._reflective.snap_parent_eval_end = self._snap()
            if size is not None:
                self._reflective.parent_eval_minibatch_size = size

    def on_proposal_start(self, event: dict) -> None:
        self._reflective.snap_proposal_start = self._snap()

    def on_proposal_end(self, event: dict) -> None:
        self._reflective.snap_proposal_end = self._snap()
        self._reflective.candidate_text = self._component_text(
            event.get("new_instructions")
        )

    # -- merge lifecycle (common) -------------------------------------

    def on_merge_attempted(self, event: dict) -> None:
        parents_raw = event.get("parent_ids") or []
        parents = [int(p) for p in parents_raw if p is not None]
        self._merge = _MergePending(
            iteration=int(event.get("iteration", 0)),
            parent_idxs=parents,
            candidate_text=self._component_text(event.get("merged_candidate")),
        )

    def on_merge_accepted(self, event: dict) -> None:
        self._merge = _MergePending()


class RejectedCandidateCollector(_GEPAIterationTracker):
    """GEPA callback that snapshots rejected proposals to a list.

    Extends ``_GEPAIterationTracker`` with phase-timing snapshots and
    in-memory record collection.  The post-loop save path reads
    ``records``, ``discovery_iter``, and ``phase_breakdowns`` to
    persist the full optimization history.

    Lifecycle:
        on_iteration_start          → reset per-iteration scratch + snapshot
        on_candidate_selected       → record reflective parent (inherited)
        on_evaluation_start         → snapshot for phase-delta diffs
        on_evaluation_end           → snapshot + record minibatch size
        on_proposal_start           → snapshot for reflection phase
        on_proposal_end             → snapshot + record candidate text
        on_candidate_rejected       → finalize a RejectedCandidate
        on_candidate_accepted       → record discovery_iter + phase_breakdown
        on_merge_attempted          → record merge parents + text (inherited)
        on_merge_rejected           → finalize a RejectedCandidate
        on_merge_accepted           → drop scratch (inherited)

    The collector is lock-free because every model thread owns its
    own collector instance (see callers in ``snow_gepa_optimize.py``
    / ``snow_gepa_optimize_anything.py``).  The TLS-based
    ``GEPAEngine.__init__`` patch in the body-mode runner ensures
    only this thread's collector sees this thread's events.
    """

    def __init__(self) -> None:
        super().__init__()
        self.records: list[RejectedCandidate] = []
        # ``discovery_iter[candidate_idx] = gepa_iteration`` — the GEPA
        # iteration in which each accepted candidate was added to the
        # population.  Lets the experiment-save path look up the
        # correct per-iteration tracker stats for accepted ITER_N runs
        # (instead of the buggy old behaviour of using the population
        # index as the iteration index, which collided with rejected
        # iterations and caused the same iter_lookup entry to be
        # billed twice).
        self.discovery_iter: dict[int, int] = {}
        # ``phase_breakdowns[gepa_iteration]`` — per-iteration phase
        # decomposition (parent eval, reflection, new cand eval).
        # Populated for both accepted and rejected iterations so the
        # save path can attach the breakdown to whichever run kind
        # the iteration produced.
        self.phase_breakdowns: dict[int, IterationPhaseBreakdown] = {}

    # -- seed lifecycle ---------------------------------------------------

    def on_optimization_start(self, event: dict) -> None:
        # Baseline snapshot taken just before the engine evaluates the seed
        # on the valset.  Diffed against the post-seed snapshot in
        # on_valset_evaluated to build phase_breakdowns[0].
        self._snap_pre_seed: _PhaseSnapshot = self._snap()

    def on_valset_evaluated(self, event: dict) -> None:
        # Only handle the seed's initial valset evaluation (iteration 0).
        if (
            int(event.get("iteration", -1)) != 0
            or int(event.get("candidate_idx", -1)) != 0
        ):
            return
        snap_post = self._snap()
        num_evals = int(event.get("num_examples_evaluated", 0))
        snap_pre = getattr(self, "_snap_pre_seed", None)
        self.discovery_iter[0] = 0
        self.phase_breakdowns[0] = IterationPhaseBreakdown(
            new_cand_eval=_PhaseDelta.between(snap_pre, snap_post),
            new_cand_eval_minibatch_size=num_evals,
        )

    # -- reflective lifecycle (action methods only; base class handles
    #    snapshot capture and the lookalike state-machine plumbing) ----

    def on_candidate_accepted(self, event: dict) -> None:
        gepa_iter = int(event.get("iteration", 0))
        new_idx = event.get("new_candidate_idx")
        if new_idx is not None:
            self.discovery_iter[int(new_idx)] = gepa_iter
        self.phase_breakdowns[gepa_iter] = self._reflective.phase_breakdown()
        self._reflective = _ReflectivePending()

    def capture_seed_from_iteration_stats(
        self, iteration_stats: list[Any] | None
    ) -> None:
        """Record the SEED's per-call eval cost under iteration key 0 from
        the tracker's iteration-0 stats.

        GEPA evaluates the SEED on the full valset *before* the loop, so it
        never fires an ``on_candidate_accepted`` event and has no
        ``discovery_iter`` entry of its own.  Its per-call eval cost lives
        in the iteration-0 tracker boundary (``udf_prompt_tokens`` /
        ``udf_completion_tokens`` over ``metric_call_count`` rows) — the
        same source the persisted SEED run reads.  Re-package those totals
        into a ``new_cand_eval`` phase so the cost-estimation path prices
        the SEED exactly like an ITER candidate instead of aborting with
        "Candidate 0 ... has no token data".

        Deriving from the iteration-0 boundary (rather than the first
        iteration's ``parent_eval``) is deliberate: a cached parent
        re-evaluation reports a zero-token delta, which would leave the
        SEED unpriced.  Idempotent via the ``0 in discovery_iter`` guard
        and a no-op when iteration-0 stats are missing or carry no tokens.

        Call once after the GEPA loop, before reading ``discovery_iter`` /
        ``phase_breakdowns`` for cost estimation.
        """  # noqa: D205
        if 0 in self.discovery_iter:
            return
        seed_stats = next(
            (
                s
                for s in (iteration_stats or [])
                if int(getattr(s, "iter_index", -1)) == 0
            ),
            None,
        )
        if seed_stats is None:
            return
        rows = int(getattr(seed_stats, "metric_call_count", 0) or 0)
        prompt_tokens = int(getattr(seed_stats, "udf_prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(seed_stats, "udf_completion_tokens", 0) or 0)
        if rows <= 0 or prompt_tokens <= 0:
            return
        self.discovery_iter[0] = 0
        self.phase_breakdowns[0] = IterationPhaseBreakdown(
            new_cand_eval=_PhaseDelta(
                eval_prompt_tokens=prompt_tokens,
                eval_completion_tokens=completion_tokens,
            ),
            new_cand_eval_minibatch_size=rows,
        )

    def on_candidate_rejected(self, event: dict) -> None:
        text = self._reflective.candidate_text or ""
        parents = (
            [int(self._reflective.parent_idx)]
            if self._reflective.parent_idx is not None
            else []
        )
        gepa_iter = int(event.get("iteration", 0))
        breakdown = self._reflective.phase_breakdown()
        if gepa_iter > 0:
            self.phase_breakdowns[gepa_iter] = breakdown
        self.records.append(
            RejectedCandidate(
                gepa_iteration=gepa_iter,
                kind="reflective",
                candidate_text=text,
                parent_candidate_idxs=parents,
                old_score=safe_float(event.get("old_score")),
                new_score=safe_float(event.get("new_score")),
                reason=str(event.get("reason") or "rejected by minibatch gate"),
                subsample_size=self._reflective.subsample_size,
                phase_breakdown=breakdown,
            )
        )
        self._reflective = _ReflectivePending()

    # -- merge lifecycle (action) -------------------------------------

    def on_merge_rejected(self, event: dict) -> None:
        text = self._merge.candidate_text or ""
        parents = list(self._merge.parent_idxs)
        if not parents:
            parents_raw = event.get("parent_ids") or []
            parents = [int(p) for p in parents_raw if p is not None]
        self.records.append(
            RejectedCandidate(
                gepa_iteration=int(event.get("iteration", 0)),
                kind="merge",
                candidate_text=text,
                parent_candidate_idxs=parents,
                old_score=None,
                new_score=None,
                reason=str(event.get("reason") or "rejected by merge gate"),
                subsample_size=None,
            )
        )
        self._merge = _MergePending()


class ProgressiveExperimentTracker(_GEPAIterationTracker):
    """GEPA callback that persists experiment runs to Snowflake progressively.

    Extends ``_GEPAIterationTracker`` with immediate Snowflake writes.
    Instead of buffering in memory, writes each ITER_N / REJECTED_N
    run to the Snowflake Experiment as soon as the corresponding GEPA
    event fires.

    SEED and BEST runs are **not** written here.  SEED is written by
    the post-loop ``save_optimization_to_experiment`` because it needs
    detailed timing stats from ``iter_lookup`` that are only available
    after the loop.  BEST needs test-set scores, aggregate stats, and
    artifact uploads.  Both are handled by the post-loop save, which
    skips ITER/REJECTED runs already persisted by this tracker (via
    ``persisted_runs``).

    Lifecycle:
        on_iteration_start          → reset per-iteration scratch (inherited)
        on_candidate_selected       → record reflective parent (inherited)
        on_proposal_end             → record candidate text (inherited)
        on_evaluation_end           → record minibatch scores (inherited)
        on_candidate_accepted       → persist ITER_N run
        on_candidate_rejected       → persist REJECTED_N run
        on_merge_attempted          → record merge parents + text (inherited)
        on_merge_rejected           → persist REJECTED_N run

    Thread safety: each model thread owns its own instance.  All
    Snowflake writes use the thread's own ``session``.  Writes are
    fault-tolerant — failures are logged but never propagated.
    """

    def __init__(
        self,
        session: Session,
        experiment_name: str,
        model: str,
        function_name: str,
        run_counter: GlobalRunCounter,
        eval_detail_buffer: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._session = session
        self._experiment_name = experiment_name
        self._model = model
        self._function_name = function_name
        # Per-candidate eval-detail buffer populated by the active adapter (or
        # the body-mode batch context) on the SAME worker thread, so no locking.
        # Maps candidate_detail_key(candidate_text) -> _CapturedEval. When set,
        # each persisted run drains its entry into ``eval_detail.json``.
        self._eval_detail_buffer = eval_detail_buffer
        # Shared across ALL model workers: hands out the global ITER number
        # for every candidate this tracker writes, so accepted + rejected
        # runs from every model form one monotonic ``ITER_<N>`` sequence.
        self._run_counter = run_counter
        # Maps this model's local GEPA population index -> the global run name
        # it was written under (``ITER_<N>``).  Used to resolve
        # ``parent_candidate`` links: a child's parent is looked up here, or
        # ``"SEED"`` for population index 0.  Only ACCEPTED candidates are
        # recorded (rejected proposals never become anyone's parent).
        self._local_to_global: dict[int, str] = {}
        self.persisted_runs: set[str] = set()
        self._rejected_ordinal = 0
        # ``_iter_start_snap`` captures tracker totals at the BEGINNING of
        # the GEPA iteration currently in flight.  Diffed against a
        # snapshot taken at write time (``on_candidate_accepted`` /
        # ``on_candidate_rejected`` / ``on_merge_rejected``) this gives
        # honest per-iteration counters that we can stamp on the ITER_N
        # / REJECTED_N row in the same write that creates it — no
        # post-loop amend needed.  Without this snapshot, the
        # progressive write produces a run whose per-iter timing fields
        # are all NULL, and the post-loop ``save_optimization_to_experiment``
        # path skips already-persisted runs (see ``persisted_runs`` below)
        # so the rich timing data never lands.  Both prompt mode and
        # body / body_agent / body_agent_single_session modes hit this
        # path because they all wire a ``ProgressiveExperimentTracker``
        # callback into GEPAEngine.
        self._iter_start_snap: _PhaseSnapshot | None = None

    @property
    def local_to_global(self) -> Mapping[int, str]:
        """Read-only view of local population index → global ``ITER_<N>`` name.

        Index 0 is the shared ``SEED`` and is not present here.
        """
        return MappingProxyType(self._local_to_global)

    def _resolve_parent(self, parent_idx: int | None) -> str:
        """Resolve a single local population index to its global run name.

        Population index 0 (or a missing parent) is the seed, whose global run
        is ``"SEED"``.  Any other index is looked up in ``_local_to_global``;
        an unrecorded parent falls back to ``"SEED"``.
        """
        if parent_idx is None or parent_idx == 0:
            return "SEED"
        return self._local_to_global.get(parent_idx, "SEED")

    def _resolve_parents(self, parent_idxs: list[int]) -> str:
        """Resolve local parent indices to a comma-joined global run-name string."""
        return ", ".join(self._resolve_parent(idx) for idx in parent_idxs)

    def on_iteration_start(self, event: dict) -> None:
        """Reset the reflective scratch + capture the per-iter baseline.

        Extends the base class's snapshot capture (which records
        per-PHASE boundaries: parent_eval / reflection / new_cand_eval)
        with an extra full-iteration snapshot diffed at write time to
        produce the per-iteration tracker counters
        (``metric_call_count`` / ``udf_exec_count`` / etc.) for the
        ITER_N / REJECTED_N row stamped from this iteration.
        """
        super().on_iteration_start(event)
        self._iter_start_snap = self._snap()

    def _per_iter_kwargs(self) -> dict[str, Any]:
        """Compute per-iteration tracker delta + per-phase breakdown
        to pass into build_run_params.

        Combines two complementary deltas captured by the base class
        and the override above:

        * **Per-iteration totals** (``metric_call_count`` /
          ``reflection_*`` / ``udf_*`` / ``experiment_*`` / ``artifact_*``
          / ``iter_seconds``) — diff between ``self._iter_start_snap``
          (taken in ``on_iteration_start``) and a fresh snapshot at
          write time.  Covers ALL work attributable to this iteration,
          including any post-accept full-valset eval.
        * **Per-phase breakdown** (``parent_eval_seconds`` /
          ``phase_reflection_seconds`` / ``new_cand_eval_seconds`` plus
          per-phase chars + minibatch sizes) — built from
          ``self._reflective.phase_breakdown()``, whose snapshots are
          captured by the base class's
          ``on_evaluation_start/end`` / ``on_proposal_start/end``
          overrides.  These are the same fields the post-loop save
          would write for a run that was NOT persisted progressively;
          without populating them here, ITER_N / REJECTED_N rows
          rendered ``parentEvalSec`` / ``reflectionPhaseSec`` /
          ``newCandEvalSec`` as ``—`` on the report.

        Returns ``{}`` when no iteration-start snapshot was captured
        (e.g. the very first call before any ``on_iteration_start``
        event, or a degraded path where the tracker wiring is missing).
        """  # noqa: D205
        if self._iter_start_snap is None:
            return {}
        delta = _PhaseDelta.between(self._iter_start_snap, self._snap())
        breakdown = self._reflective.phase_breakdown()
        return {
            "iter_seconds": delta.seconds,
            # ``num_examples`` is the per-iter ``metric_call_count`` so a
            # reader of BENCH_TRACKING_DETAILS sees a single source of
            # truth for "how many examples did this iteration evaluate?"
            # — same convention SEED uses (where num_examples is the
            # full-eval valset size, which equals metric_call_count for
            # the seed eval).
            "num_examples": delta.metric_call_count or None,
            "metric_call_count": delta.metric_call_count,
            "metric_seconds_total": delta.metric_seconds_total,
            "reflection_call_count": delta.reflection_call_count,
            "reflection_seconds_total": delta.reflection_seconds_total,
            "udf_compile_count": delta.udf_compile_count,
            "udf_compile_seconds_total": delta.udf_compile_seconds_total,
            "udf_exec_count": delta.udf_exec_count,
            "udf_exec_seconds_total": delta.udf_exec_seconds_total,
            "experiment_count": delta.experiment_count,
            "experiment_seconds_total": delta.experiment_seconds_total,
            "artifact_count": delta.artifact_count,
            "artifact_seconds_total": delta.artifact_seconds_total,
            # Per-phase breakdown — populated by the base class's
            # ``on_evaluation_start/end`` and ``on_proposal_start/end``
            # snapshots.  Each phase's wall-clock seconds + char totals
            # surface in the report's ``parentEvalSec`` /
            # ``reflectionPhaseSec`` / ``newCandEvalSec`` columns and
            # drive the per-call cost computation on the Pareto plot.
            "parent_eval_seconds": breakdown.parent_eval.seconds or None,
            "phase_reflection_seconds": breakdown.reflection.seconds or None,
            "new_cand_eval_seconds": breakdown.new_cand_eval.seconds or None,
            "new_cand_eval_input_chars": (breakdown.new_cand_eval.input_chars or None),
            "new_cand_eval_output_chars": (
                breakdown.new_cand_eval.output_chars or None
            ),
            "new_cand_eval_minibatch_size": (
                breakdown.new_cand_eval_minibatch_size or None
            ),
            "parent_eval_input_chars": breakdown.parent_eval.input_chars or None,
            "parent_eval_output_chars": breakdown.parent_eval.output_chars or None,
            "parent_eval_minibatch_size": (
                breakdown.parent_eval_minibatch_size or None
            ),
            # Cumulative input/output chars during this iteration (drives
            # the per-iter cost column in the report).
            "iter_input_chars": delta.input_chars or None,
            "iter_output_chars": delta.output_chars or None,
            # Per-iteration token breakdown (added 2026-05).  Eval tokens
            # are REAL counts from AI_COMPLETE's ``usage`` block (sum of
            # parent_eval + new_cand_eval + any post-accept full-valset
            # eval); reflection tokens are CHAR-BASED estimates
            # (input_chars // 4) since the reflection AI_COMPLETE call
            # keeps ``show_details=False``.  Drives the per-iteration
            # token columns in BENCH_TRACKING_DETAILS and the new
            # token-axis Gantt chart in the HTML report.  Without these,
            # ITER_N / REJECTED_N rows would render the new token
            # columns as ``—`` even though SEED rows already had them.
            "iter_eval_prompt_tokens": delta.eval_prompt_tokens or None,
            "iter_eval_completion_tokens": delta.eval_completion_tokens or None,
            "iter_reflection_prompt_tokens_est": (
                delta.reflection_input_chars // 4
                if delta.reflection_input_chars
                else None
            ),
            "iter_reflection_completion_tokens_est": (
                delta.reflection_output_chars // 4
                if delta.reflection_output_chars
                else None
            ),
            # Per-phase token splits — same provenance as per-phase
            # chars + minibatch sizes above.  Eval phases (parent and
            # new-cand) report real tokens; reflection phase reports
            # the char-based estimate.
            "new_cand_eval_prompt_tokens": (
                breakdown.new_cand_eval.eval_prompt_tokens or None
            ),
            "new_cand_eval_completion_tokens": (
                breakdown.new_cand_eval.eval_completion_tokens or None
            ),
            "parent_eval_prompt_tokens": (
                breakdown.parent_eval.eval_prompt_tokens or None
            ),
            "parent_eval_completion_tokens": (
                breakdown.parent_eval.eval_completion_tokens or None
            ),
            "phase_reflection_prompt_tokens_est": (
                breakdown.reflection.reflection_prompt_tokens_est or None
            ),
            "phase_reflection_completion_tokens_est": (
                breakdown.reflection.reflection_completion_tokens_est or None
            ),
        }

    def _safe_write(
        self,
        run_name: str,
        params: RunParams,
        metrics: list[dict[str, float]] | None = None,
    ) -> None:
        """Write a single run to the experiment, swallowing errors.

        The run is left in RUNNING state (not committed) so the
        batch save can backfill Pareto frontier metrics before
        committing.  If no batch save follows (e.g. the optimization
        crashes), RUNNING runs are harmless orphans.
        """
        try:
            add_experiment_run(
                self._session,
                self._experiment_name,
                run_name,
                params=params,
                metrics=metrics,
            )
            self.persisted_runs.add(run_name)
        except Exception:
            logger.exception(
                "Progressive tracker: failed to persist run %s to experiment %s",
                run_name,
                self._experiment_name,
            )

    def _upload_run_eval_detail(self, run_name: str, candidate_text: str) -> None:
        """Drain this candidate's captured per-row eval into the run's stage.

        Writes ``eval_detail.json`` to the run's own nested stage so the run can
        be recovered from the JSON (each run has its own stage, so no run-name
        prefix is needed). Best-effort: a missing capture or an upload failure
        must never abort optimization (mirrors ``_safe_write``). Uses only data
        GEPA already computed — no re-evaluation.
        """
        buffer = self._eval_detail_buffer
        if buffer is None:
            return
        try:
            captured = buffer.pop(candidate_detail_key(candidate_text), None)
            if captured is None or not captured.records:
                return
            detail_path = write_eval_detail_artifact(captured.records)
            put_experiment_artifact(
                self._session,
                self._experiment_name,
                run_name,
                local_path=detail_path,
            )
        except Exception:
            logger.exception(
                "Progressive tracker: failed to upload eval detail for run %s",
                run_name,
            )

    # -- action methods (write to Snowflake) ----------------------------

    def on_candidate_accepted(self, event: dict) -> None:
        """Persist an accepted candidate as a global ITER_<N> run immediately."""
        gepa_iter = int(event.get("iteration", 0))
        new_idx = event.get("new_candidate_idx")
        if new_idx is None:
            self._reflective = _ReflectivePending()
            self._iter_start_snap = None
            return

        new_idx = int(new_idx)
        global_iter = self._run_counter.next_iter()
        iter_run = make_iter_run_name(global_iter)
        # Record local population index -> global run name so later candidates
        # can resolve this one as their parent.
        self._local_to_global[new_idx] = iter_run
        candidate_text = self._reflective.candidate_text or ""
        parent = self._resolve_parent(self._reflective.parent_idx)
        # NOTE: Do NOT write valset_score here.  The callback's
        # ``new_score`` is the subsample SUM (not the full-eval score).
        # Dividing by subsample_size gives the subsample MEAN which is
        # incorrect for the tracking table (it inflates scores to 1.0
        # when all minibatch rows score perfectly).  The correct
        # full-eval score is written later by ``backfill_model_metrics``
        # from ``result.val_aggregate_scores``.
        valset_score = None

        params = RunParams(
            function_impl=candidate_text,
            model=self._model,
            iteration=str(new_idx),
            global_iteration=global_iter,
            run_type="iteration",
            parent_candidate=parent,
            function_name=self._function_name,
            status="completed",
            gepa_iteration=gepa_iter,
            **self._per_iter_kwargs(),
        )
        metrics = build_run_metrics(valset_score=valset_score)
        self._safe_write(iter_run, params, metrics)
        self._upload_run_eval_detail(iter_run, candidate_text)
        self._reflective = _ReflectivePending()
        self._iter_start_snap = None

    def on_candidate_rejected(self, event: dict) -> None:
        """Persist a rejected reflective proposal as a global ITER_<N> run.

        Rejected proposals are full runs in the single global ITER sequence,
        distinguished only by ``run_type="rejected"`` / ``status="rejected"``
        metadata — there is no ``*_REJECTED_*`` name namespace.  They are not
        recorded in ``_local_to_global`` because they never become a parent.
        """
        self._rejected_ordinal += 1
        text = self._reflective.candidate_text or ""
        parents = (
            [int(self._reflective.parent_idx)]
            if self._reflective.parent_idx is not None
            else []
        )
        gepa_iter = int(event.get("iteration", 0))
        parent_str = self._resolve_parents(parents)
        subsample_mean = None
        new_score = safe_float(event.get("new_score"))
        if (
            new_score is not None
            and self._reflective.subsample_size
            and self._reflective.subsample_size > 0
        ):
            subsample_mean = new_score / self._reflective.subsample_size

        global_iter = self._run_counter.next_iter()
        rejected_run = make_iter_run_name(global_iter)
        params = RunParams(
            function_impl=text,
            model=self._model,
            iteration=str(self._rejected_ordinal),
            global_iteration=global_iter,
            run_type="rejected",
            parent_candidate=parent_str,
            function_name=self._function_name,
            status="rejected",
            rejection_kind="reflective",
            rejection_reason=str(event.get("reason") or "rejected by minibatch gate"),
            subsample_score_old=safe_float(event.get("old_score")),
            subsample_score_new=new_score,
            subsample_size=self._reflective.subsample_size,
            subsample_score_new_mean=subsample_mean,
            gepa_iteration=gepa_iter,
            **self._per_iter_kwargs(),
        )
        self._safe_write(rejected_run, params)
        self._upload_run_eval_detail(rejected_run, text)
        self._reflective = _ReflectivePending()
        self._iter_start_snap = None

    def on_merge_rejected(self, event: dict) -> None:
        """Persist a rejected merge proposal as a global ITER_<N> run."""
        self._rejected_ordinal += 1
        text = self._merge.candidate_text or ""
        parents = list(self._merge.parent_idxs)
        if not parents:
            parents_raw = event.get("parent_ids") or []
            parents = [int(p) for p in parents_raw if p is not None]
        parent_str = self._resolve_parents(parents)

        global_iter = self._run_counter.next_iter()
        rejected_run = make_iter_run_name(global_iter)
        params = RunParams(
            function_impl=text,
            model=self._model,
            iteration=str(self._rejected_ordinal),
            global_iteration=global_iter,
            run_type="rejected",
            parent_candidate=parent_str,
            function_name=self._function_name,
            status="rejected",
            rejection_kind="merge",
            rejection_reason=str(event.get("reason") or "rejected by merge gate"),
            gepa_iteration=int(event.get("iteration", 0)),
            **self._per_iter_kwargs(),
        )
        self._safe_write(rejected_run, params)
        self._upload_run_eval_detail(rejected_run, text)
        self._merge = _MergePending()
        self._iter_start_snap = None


def _estimate_iter_credits(
    breakdown: IterationPhaseBreakdown,
    udf_model: str,
    reflection_model: str,
) -> float:
    """Estimate Snowflake credit cost for a single GEPA iteration.

    UDF eval phases (parent_eval + new_cand_eval) use real token counts
    sourced from AI_COMPLETE's usage block.  The reflection phase uses
    char-based token estimates (chars // 4) because reflection runs with
    ``show_details=False``.  Per-token rates from ``src/models.json``
    (credits per million tokens) via :func:`estimate_candidate_cost`.

    Raises:
        ValueError: If either model is absent from the rate table.

    """
    udf_cost = estimate_candidate_cost(
        udf_model,
        breakdown.total_eval_prompt_tokens(),
        breakdown.total_eval_completion_tokens(),
    )
    refl_cost = (
        estimate_candidate_cost(
            reflection_model,
            breakdown.total_reflection_prompt_tokens_est(),
            breakdown.total_reflection_completion_tokens_est(),
        )
        if reflection_model
        else 0.0
    )
    return udf_cost + refl_cost


def make_rejected_run_name(model: str, ordinal: int) -> str:
    """Build a run name for the *N*-th rejected candidate of a model.

    Convention:
        <MODEL>_REJECTED_<N>     -- 1-indexed; N = order in which the
                                    rejection event fired

    Run names are model-scoped (same as SEED / ITER_N / BEST) so
    parallel per-model optimization cannot create naming conflicts.
    Ordinal counter is independent of the GEPA ``iteration`` field
    because multiple rejections can fire in the same iteration (e.g.
    one merge_rejected followed by one candidate_rejected) and run
    names must remain unique within an experiment.
    """
    model_suffix = re.sub(r"[^A-Za-z0-9]", "_", model).upper()
    return f"{model_suffix}_REJECTED_{ordinal}"


# ---------------------------------------------------------------------------
# High-level: persist a full optimization run
# ---------------------------------------------------------------------------


@dataclass
class OptimizationRunStats:
    """Optional stats collected from a completed GEPA run for experiment persistence.

    Passed as a single ``stats`` argument to ``save_optimization_to_experiment``
    to keep the call signature manageable as new tracking fields are added.
    """

    seed_val_score: float | None = None
    best_val_score: float | None = None
    seed_test_score: float | None = None
    best_test_score: float | None = None
    score_source: str = "validation"
    num_examples: int | None = None
    avg_output_chars: int | None = None
    reflection_model: str = ""
    total_candidates: int | None = None
    total_metric_calls: int | None = None
    total_reflection_calls: int | None = None
    elapsed_seconds: float | None = None
    run_dir: str | None = None
    seed_eval_details: list[dict[str, Any]] | None = None
    best_eval_details: list[dict[str, Any]] | None = None
    iteration_stats: list[Any] | None = None
    total_metric_seconds: float | None = None
    total_reflection_seconds: float | None = None
    total_udf_compile_calls: int | None = None
    total_udf_compile_seconds: float | None = None
    total_udf_exec_calls: int | None = None
    total_udf_exec_seconds: float | None = None
    total_experiment_calls: int | None = None
    total_experiment_seconds: float | None = None
    total_artifact_calls: int | None = None
    total_artifact_seconds: float | None = None
    test_eval_metric_calls: int | None = None
    test_eval_metric_seconds: float | None = None
    test_eval_reflection_calls: int | None = None
    test_eval_reflection_seconds: float | None = None
    test_eval_udf_compile_calls: int | None = None
    test_eval_udf_compile_seconds: float | None = None
    test_eval_udf_exec_calls: int | None = None
    test_eval_udf_exec_seconds: float | None = None
    total_udf_prompt_tokens: int | None = None
    total_udf_completion_tokens: int | None = None
    test_eval_udf_prompt_tokens: int | None = None
    test_eval_udf_completion_tokens: int | None = None
    total_reflection_prompt_tokens_est: int | None = None
    total_reflection_completion_tokens_est: int | None = None
    parents: list[list[int | None]] | None = None
    rejected_candidates: list[RejectedCandidate] | None = None
    discovery_iter: dict[int, int] | None = None
    phase_breakdowns: dict[int, IterationPhaseBreakdown] | None = None
    iter_extra_meta: dict[int, dict[str, Any]] | None = None
    already_persisted_runs: set[str] | None = None
    # When True, SEED and ITER runs are written but NOT committed here;
    # their names are returned so the cross-model orchestrator can stamp
    # frontier metrics (test_score / is_frontier) onto the selected ones
    # and then commit the whole set.  REJECTED runs are always committed
    # immediately (they never join the frontier).  Snowflake rejects
    # ADD METRICS on a committed run, so deferring the commit is what lets
    # the frontier scores land on the real SEED/ITER lineage runs.
    defer_commit: bool = False


def _candidate_text(candidate: object) -> str:
    """Collapse a candidate (dict of components, or raw string) to its text."""
    if isinstance(candidate, dict):
        return " ".join(str(v) for v in candidate.values())
    return str(candidate)


def _avg_tokens_from_breakdown(bd: Any) -> tuple[int, int]:
    """Per-call (prompt, completion) tokens from a phase breakdown, else (0, 0).

    Prefers real token counts from the AI_COMPLETE usage block; falls back to
    the ``chars // 4`` proxy already recorded on the breakdown. Returns
    ``(0, 0)`` when the candidate's ``new_cand_eval`` was never populated — e.g.
    GEPA reused a cached score for a duplicate candidate without re-invoking the
    adapter, so no eval flowed through token/char accounting.
    """
    if not bd or bd.new_cand_eval_minibatch_size <= 0:
        return 0, 0
    mb = bd.new_cand_eval_minibatch_size
    if bd.new_cand_eval.eval_prompt_tokens > 0:
        return (
            bd.new_cand_eval.eval_prompt_tokens // mb,
            bd.new_cand_eval.eval_completion_tokens // mb,
        )
    if bd.new_cand_eval.eval_input_chars > 0:
        return (
            bd.new_cand_eval.eval_input_chars // (4 * mb),
            bd.new_cand_eval.eval_output_chars // (4 * mb),
        )
    return 0, 0


def _resolve_candidate_tokens(
    candidates: list[str],
    discovery_iter: dict[int, int],
    phase_breakdowns: dict[int, Any],
) -> tuple[dict[int, tuple[int, int]], dict[str, tuple[int, int]]]:
    """Return (per-index tokens, tokens-by-prompt-text) from tracked breakdowns.

    ``tokens_by_text`` lets a duplicate candidate whose eval GEPA reused (no
    fresh breakdown) inherit the REAL per-call token counts of the identical
    candidate that WAS tracked. GEPA only reuses a score when the candidate is
    identical to one it already evaluated, so an identical tracked twin exists.
    """
    tracked: dict[int, tuple[int, int]] = {}
    by_text: dict[str, tuple[int, int]] = {}
    for idx in range(len(candidates)):
        gepa_iter = discovery_iter.get(idx)
        bd = phase_breakdowns.get(gepa_iter) if gepa_iter is not None else None
        avg_pt, avg_ct = _avg_tokens_from_breakdown(bd)
        if avg_pt > 0:
            tracked[idx] = (avg_pt, avg_ct)
            by_text.setdefault(_candidate_text(candidates[idx]), (avg_pt, avg_ct))
    return tracked, by_text


def compute_pareto_candidates(
    model: str,
    candidates: list[str],
    val_scores: list[float],
    discovery_iter: dict[int, int],
    phase_breakdowns: dict[int, Any],
    run_names: dict[int, str] | None = None,
) -> list[ParetoCandidateInfo]:
    """Compute ParetoCandidateInfo for every candidate in a GEPA result.

    Pure in-memory computation — no Snowflake session required. Call this
    BEFORE ``save_optimization_to_experiment`` so that cross-model Pareto
    data is always available even when experiment persistence fails.

    Args:
        model: Model identifier string.
        candidates: Ordered list of candidate texts (index 0 = SEED).
        val_scores: Validation score for each candidate.
        discovery_iter: Maps candidate index → GEPA loop iteration, used to
            look up phase token/char counts for accurate cost estimation.
            The SEED (index 0) is tracked under iteration key 0 by
            ``RejectedCandidateCollector.capture_seed_from_iteration_stats``.
        phase_breakdowns: Per-GEPA-iteration phase breakdown objects.
        run_names: Optional map of candidate index → the global run name the
            candidate was persisted under (schema-v4 body/prompt path).  When
            ``None`` (evolve/legacy), names are derived per-model via
            :func:`make_run_name`.  When provided, every candidate index must
            have an entry (a ``KeyError`` surfaces a missing mapping rather
            than silently mislabelling a run).

    Returns:
        One ``ParetoCandidateInfo`` per candidate (SEED + all ITERs).

    """
    if len(candidates) != len(val_scores):
        raise ValueError(
            f"candidates and val_scores must have the same length; "
            f"got {len(candidates)} candidates and {len(val_scores)} scores"
        )

    tracked_tokens, tokens_by_text = _resolve_candidate_tokens(
        candidates, discovery_iter, phase_breakdowns
    )
    estimated_costs: dict[int, float | None] = {}
    for idx in range(len(candidates)):
        avg = tracked_tokens.get(idx) or tokens_by_text.get(
            _candidate_text(candidates[idx])
        )
        if avg is None:
            gepa_iter = discovery_iter.get(idx)
            bd = phase_breakdowns.get(gepa_iter) if gepa_iter is not None else None
            raise ValueError(
                f"Candidate {idx} for model '{model}' has no token data and no "
                f"identical tracked candidate to inherit it from (discovery_iter "
                f"entry={discovery_iter.get(idx)}, "
                f"phase_breakdown={'present' if bd else 'missing'}). "
                "All candidates require tracked token counts for cost estimation."
            )
        if idx not in tracked_tokens:
            # Duplicate candidate whose eval GEPA reused (no fresh breakdown);
            # it inherits the REAL per-call cost of the identical tracked twin.
            logger.warning(
                "Candidate %d for model %r had no tracked eval usage (its eval "
                "was reused from an identical candidate); inheriting that "
                "candidate's tracked per-call cost (~%d input tokens).",
                idx,
                model,
                avg[0],
            )
        estimated_costs[idx] = estimate_candidate_cost(model, avg[0], avg[1])

    result: list[ParetoCandidateInfo] = []
    for idx in range(len(candidates)):
        if run_names is not None:
            run_name = run_names[idx]
        else:
            run_name = make_run_name(model, idx, is_seed=(idx == 0))
        result.append(
            ParetoCandidateInfo(
                run_name=run_name,
                model=model,
                estimated_cost=estimated_costs.get(idx),
                score=val_scores[idx],
                prompt_text=candidates[idx],
            )
        )
    return result


def save_optimization_to_experiment(
    session: Session,
    experiment_name: str,
    *,
    function_name: str,
    model: str,
    seed_prompt: str,
    best_prompt: str,
    candidates: list[str],
    val_scores: list[float] | None,
    best_idx: int,
    stats: OptimizationRunStats,
) -> list[str] | None:
    """Persist a full GEPA optimization result to a Snowflake Experiment.

    Creates runs for: SEED, each iteration, and one
    ``MODEL_REJECTED_N`` run per entry in ``rejected_candidates``.
    Aggregate stats are stamped on the SEED run (summary anchor).
    Uploads ``run_dir`` artifacts to the winning ITER run, plus the held-out
    SEED detail as the SEED run's ``eval_detail.json`` and the held-out BEST
    detail as the winning ITER run's ``eval_detail.json`` (when provided).

    When ``already_persisted_runs`` is provided (from a
    ``ProgressiveExperimentTracker``), runs whose names appear in that
    set are skipped — they were already written during the GEPA loop.
    The SEED run is always stamped with aggregate stats here.

    Rejected candidates are GEPA proposals that lost their minibatch
    accept/reject gate — they consumed a reflection LLM call + a temp
    UDF compile + a minibatch eval but never reached the population.
    Persisting them preserves the full optimization history and
    answers "what did the reflection LLM try and why was it dropped?"
    questions that the seed/iter/best runs alone can't.

    ``iter_extra_meta`` is a mode-specific bag of per-iteration metadata
    keyed on candidate index (0 = SEED, 1..N = ITER_N).  Each entry is a
    JSON-serialisable dict whose contents the renderer interprets per
    mode — currently only consumed by ``mode == "evolve"`` to surface
    MAP-Elites cell ownership, parent_id, archive size deltas, and the
    other CocoEvolve bookkeeping captured by the ``database.add`` hook
    in ``snow_gepa_optimize_evolve._tracking_add``.  GEPA-driven body /
    prompt optimization passes ``None`` and the field is omitted.

    Pareto candidate data is NOT returned here — call ``compute_pareto_candidates``
    before this function to get that independently of whether the save succeeds.

    Returns the list of SEED/ITER run names whose commit was deferred (when
    ``stats.defer_commit`` is set) so the caller can stamp cross-model
    frontier metrics onto them and then commit.  Returns ``[]`` when nothing
    was deferred and ``None`` when persistence failed.

    Intentionally fault-tolerant: failures are logged but never propagated
    so that experiment persistence cannot break an optimization run.
    """
    try:
        return _save_optimization_to_experiment_impl(
            session=session,
            experiment_name=experiment_name,
            function_name=function_name,
            model=model,
            seed_prompt=seed_prompt,
            best_prompt=best_prompt,
            candidates=candidates,
            val_scores=val_scores,
            best_idx=best_idx,
            run_stats=stats,
        )
    except Exception:
        logger.exception(
            "Failed to persist optimization to experiment %s",
            experiment_name,
        )
        return None


# ---------------------------------------------------------------------------
# Schema-v4 global run structure (GEPA body + prompt modes)
# ---------------------------------------------------------------------------
#
# In schema v4 the ProgressiveExperimentTracker writes every candidate
# (accepted + rejected) as a global ``ITER_<N>`` run (RUNNING).  The two
# helpers below replace the per-model ``<MODEL>_SEED`` write of
# ``_save_optimization_to_experiment_impl`` for body/prompt: a per-model
# metric backfill onto those RUNNING ITER runs, and a single consolidated
# ``SEED`` run carrying per-model aggregate stats.  Cross-model frontier
# stamping + the final commit reuse PR #81's ``stamp_frontier_metrics_on_runs``
# / ``commit_runs`` in the orchestrators.  Evolve mode still uses
# ``save_optimization_to_experiment`` (per-model SEED/ITER) until migrated.


def backfill_model_metrics(
    session: Session,
    experiment_name: str,
    *,
    pareto_candidates: list[ParetoCandidateInfo],
) -> list[str]:
    """Stamp within-model metrics onto this model's RUNNING ``ITER_<N>`` runs.

    Adds ``valset_score`` + ``estimated_cost``; skips the shared ``SEED``;
    does not commit (schema v4, per-model, run after one model's GEPA loop).

    Does NOT set the cross-model ``is_frontier`` / ``test_score`` (later, via
    ``stamp_frontier_metrics_on_runs``) and does NOT write or commit the SEED.

    Returns the ITER run names touched, for the caller's later
    ``commit_runs``.  Errors surface — a failed ``MODIFY`` means the run is
    missing or already committed, a real bug.
    """
    # Base seed cost for the cost_compared_to_base metric — the SEED candidate's
    # estimated cost (skipped in the loop below, but its cost is the denominator).
    seed_cost = next(
        (pc.estimated_cost for pc in pareto_candidates if pc.run_name == "SEED"),
        None,
    )
    touched: list[str] = []
    for pc in pareto_candidates:
        if pc.run_name == "SEED":
            continue
        metrics = build_run_metrics(
            valset_score=pc.score,
            estimated_cost=pc.estimated_cost,
            base_cost=seed_cost,
        )
        if metrics:
            metrics_json = json.dumps(metrics)
            timed_experiment_sql(
                session,
                f"ALTER EXPERIMENT {experiment_name} MODIFY RUN "
                f"{pc.run_name} ADD METRICS = '{metrics_json}'",
            )
        touched.append(pc.run_name)
    return touched


def write_consolidated_seed(
    session: Session,
    experiment_name: str,
    *,
    function_name: str,
    seed_prompt: str,
    model: str,
    per_model_stats: dict[str, Any],
    seed_val_score: float | None,
    summed_totals: dict[str, Any] | None = None,
    avg_output_chars: int | None = None,
    seed_estimated_cost: float | None = None,
    score_source: str = "validation",
    metric_name: str | None = None,
    custom_metric_udf: str | None = None,
) -> None:
    """Write the single consolidated ``SEED`` run (left RUNNING; caller commits).

    Schema v4's one ``SEED`` run (the input function's own eval) doubles as the
    global summary anchor: ``model`` is the input function's model,
    ``per_model_stats`` holds each optimization model's aggregates, ``summed_totals``
    stamps those summed as top-level params for existing consumers, and seed eval
    scores land as metrics.  Left RUNNING so the orchestrator can stamp
    cross-model ``is_frontier`` / ``test_score`` and commit it with the ITER
    runs.
    """
    params = RunParams(
        function_impl=seed_prompt,
        # The seed IS the input function, so its model is the input function's
        # own model (per-optimization-model detail lives in per_model_stats).
        model=model,
        iteration="0",
        global_iteration=0,
        run_type="seed",
        function_name=function_name,
        score_source=score_source,
        status="completed",
        avg_output_chars=avg_output_chars,
        experiment_schema_version=EXPERIMENT_SCHEMA_VERSION,
        per_model_stats=json.dumps(per_model_stats, default=str),
        metric_name=metric_name,
        custom_metric_udf=custom_metric_udf,
        # Global summary totals (summed across optimization models).
        **(summed_totals or {}),
    )
    metrics = build_run_metrics(
        valset_score=seed_val_score,
        estimated_cost=seed_estimated_cost,
        base_cost=seed_estimated_cost,  # SEED is the base → 1.0
    )
    add_experiment_run(
        session, experiment_name, SEED_RUN_NAME, params=params, metrics=metrics
    )


# Numeric per-model totals that are summed across models onto the consolidated
# SEED run (top-level params) so the SEED remains a global summary anchor.  All
# are valid ``RunParams`` fields.
# Per-model fields copied into the consolidated SEED's ``per_model_stats`` when
# a model completes (schema v4).  ``status``/``elapsed_seconds`` (always) and
# ``error`` (on failure) are handled separately in build_per_model_stats.
_PER_MODEL_STAT_FIELDS: tuple[str, ...] = (
    "total_candidates",
    "total_metric_calls",
    "total_metric_seconds",
    "total_reflection_calls",
    "total_reflection_seconds",
    "total_udf_compile_calls",
    "total_udf_compile_seconds",
    "total_udf_exec_calls",
    "total_udf_exec_seconds",
    "total_udf_prompt_tokens",
    "total_udf_completion_tokens",
    "total_reflection_prompt_tokens_est",
    "total_reflection_completion_tokens_est",
    "total_experiment_calls",
    "total_experiment_seconds",
    "total_artifact_calls",
    "total_artifact_seconds",
    "reflection_model",
    "seed_val_score",
    "best_val_score",
    "seed_test_score",
    "best_test_score",
    "test_eval_metric_calls",
    "test_eval_metric_seconds",
    "test_eval_udf_prompt_tokens",
    "test_eval_udf_completion_tokens",
)


def build_per_model_stats(
    model_results: list[Any], get: Callable[[Any, str], Any]
) -> dict[str, Any]:
    """Aggregate each model's optimization totals into a JSON-safe dict.

    Keyed by model, for the consolidated SEED's ``per_model_stats`` param
    (schema v4).  ``get(mr, field)`` reads a field from one model result —
    ``getattr`` for
    body mode's dataclass, ``dict.get``-style for prompt mode's dict — so the
    single body works for both.  Values are scalars (numbers / strings / None).
    """
    stats: dict[str, Any] = {}
    for mr in model_results:
        status = get(mr, "status")
        entry: dict[str, Any] = {
            "status": status,
            "elapsed_seconds": get(mr, "elapsed_seconds"),
        }
        if status == "completed":
            for field_name in _PER_MODEL_STAT_FIELDS:
                entry[field_name] = get(mr, field_name)
        else:
            entry["error"] = get(mr, "error")
        stats[str(get(mr, "model"))] = entry
    return stats


_SUMMABLE_SEED_TOTALS: tuple[str, ...] = (
    "total_candidates",
    "total_metric_calls",
    "total_metric_seconds",
    "total_reflection_calls",
    "total_reflection_seconds",
    "total_udf_compile_calls",
    "total_udf_compile_seconds",
    "total_udf_exec_calls",
    "total_udf_exec_seconds",
    "total_udf_prompt_tokens",
    "total_udf_completion_tokens",
    "total_reflection_prompt_tokens_est",
    "total_reflection_completion_tokens_est",
    "total_experiment_calls",
    "total_experiment_seconds",
    "total_artifact_calls",
    "total_artifact_seconds",
    "elapsed_seconds",
    "test_eval_metric_calls",
    "test_eval_metric_seconds",
    "test_eval_udf_prompt_tokens",
    "test_eval_udf_completion_tokens",
)


def sum_seed_totals(per_model_stats: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Sum the per-model numeric totals into global totals for the SEED run.

    Takes the same per-model dict written to ``per_model_stats`` and returns the
    subset of :data:`_SUMMABLE_SEED_TOTALS` summed across COMPLETED models.
    ``elapsed_seconds`` is summed too (per the chosen contract); note that
    across parallel models this exceeds wall-clock, so treat it as a cost total
    rather than a duration.
    """
    summed: dict[str, Any] = {}
    for stats in per_model_stats.values():
        if stats.get("status") != "completed":
            continue
        for key in _SUMMABLE_SEED_TOTALS:
            value = stats.get(key)
            if value is None:
                continue
            summed[key] = (summed.get(key) or 0) + value
    return summed


def upload_winning_artifacts(
    session: Session,
    experiment_name: str,
    winning_run_name: str,
    *,
    run_dir: str | None = None,
    seed_eval_details: list[dict[str, Any]] | None = None,
    best_eval_details: list[dict[str, Any]] | None = None,
    seed_run_name: str = SEED_RUN_NAME,
    upload_run_dir: bool = True,
) -> None:
    """Upload run_dir + seed/best eval-detail JSON to their runs' stages.

    Schema v4 body/prompt bypass ``_save_optimization_to_experiment_impl`` (which
    uploads artifacts per model), so the orchestrator uploads them once: the
    held-out SEED detail lands on the ``SEED`` run and the best detail on the
    winning ITER run, each as that run's own ``eval_detail.json`` (one detail
    file per run; no prefix). The ``SEED`` / winning runs are written (RUNNING,
    deferred commit) before this call.  Best-effort: upload failures are logged,
    not propagated — a missing stage file must not discard the optimization
    result.

    When ``upload_run_dir`` is False, the GEPA ``run_dir`` status/state
    artifacts (candidates.json.gz, gepa_state.bin.gz, logs) are NOT uploaded —
    the spec-driven (YAML) handler sets this to keep those internal files out
    of the experiment stage. Per-run ``eval_detail.json`` is unaffected.
    """
    if upload_run_dir and run_dir and os.path.isdir(run_dir):
        run_dir_contents = [
            f for f in os.listdir(run_dir) if os.path.isfile(os.path.join(run_dir, f))
        ]
        if run_dir_contents:
            try:
                put_experiment_artifact(
                    session,
                    experiment_name,
                    winning_run_name,
                    local_path=run_dir,
                    subdir="run_dir",
                )
            except Exception as exc:
                logger.warning(
                    "Failed to upload run_dir artifacts (%d files in %s): %s",
                    len(run_dir_contents),
                    run_dir,
                    exc,
                )
    # (label, details, target run) — the held-out SEED detail lands on the SEED
    # run and the held-out BEST detail on the winning ITER run, each as that
    # run's own ``eval_detail.json`` (one detail file per run; no prefix). On
    # the winning ITER run this is the held-out test eval; it is written after
    # the loop, so it supersedes the in-loop val capture for that run.
    for label, details, target_run in (
        ("SEED", seed_eval_details, seed_run_name),
        ("BEST", best_eval_details, winning_run_name),
    ):
        if not details:
            continue
        try:
            detail_path = write_eval_detail_artifact(details)
            put_experiment_artifact(
                session,
                experiment_name,
                target_run,
                local_path=detail_path,
            )
        except Exception as exc:
            logger.warning("Failed to upload %s eval detail: %s", label, exc)


# ---------------------------------------------------------------------------
# Internal implementation
# ---------------------------------------------------------------------------


def _save_optimization_to_experiment_impl(
    session: Session,
    experiment_name: str,
    *,
    function_name: str,
    model: str,
    seed_prompt: str,
    best_prompt: str,
    candidates: list[str],
    val_scores: list[float] | None,
    best_idx: int,
    run_stats: OptimizationRunStats,
) -> list[str]:
    seed_val_score = run_stats.seed_val_score
    seed_test_score = run_stats.seed_test_score
    score_source = run_stats.score_source
    num_examples = run_stats.num_examples
    avg_output_chars = run_stats.avg_output_chars
    reflection_model = run_stats.reflection_model
    total_candidates = run_stats.total_candidates
    total_metric_calls = run_stats.total_metric_calls
    total_reflection_calls = run_stats.total_reflection_calls
    elapsed_seconds = run_stats.elapsed_seconds
    run_dir = run_stats.run_dir
    seed_eval_details = run_stats.seed_eval_details
    best_eval_details = run_stats.best_eval_details
    iteration_stats = run_stats.iteration_stats
    total_metric_seconds = run_stats.total_metric_seconds
    total_reflection_seconds = run_stats.total_reflection_seconds
    total_udf_compile_calls = run_stats.total_udf_compile_calls
    total_udf_compile_seconds = run_stats.total_udf_compile_seconds
    total_udf_exec_calls = run_stats.total_udf_exec_calls
    total_udf_exec_seconds = run_stats.total_udf_exec_seconds
    total_experiment_calls = run_stats.total_experiment_calls
    total_experiment_seconds = run_stats.total_experiment_seconds
    total_artifact_calls = run_stats.total_artifact_calls
    total_artifact_seconds = run_stats.total_artifact_seconds
    test_eval_metric_calls = run_stats.test_eval_metric_calls
    test_eval_metric_seconds = run_stats.test_eval_metric_seconds
    test_eval_reflection_calls = run_stats.test_eval_reflection_calls
    test_eval_reflection_seconds = run_stats.test_eval_reflection_seconds
    test_eval_udf_compile_calls = run_stats.test_eval_udf_compile_calls
    test_eval_udf_compile_seconds = run_stats.test_eval_udf_compile_seconds
    test_eval_udf_exec_calls = run_stats.test_eval_udf_exec_calls
    test_eval_udf_exec_seconds = run_stats.test_eval_udf_exec_seconds
    total_udf_prompt_tokens = run_stats.total_udf_prompt_tokens
    total_udf_completion_tokens = run_stats.total_udf_completion_tokens
    test_eval_udf_prompt_tokens = run_stats.test_eval_udf_prompt_tokens
    test_eval_udf_completion_tokens = run_stats.test_eval_udf_completion_tokens
    total_reflection_prompt_tokens_est = run_stats.total_reflection_prompt_tokens_est
    total_reflection_completion_tokens_est = (
        run_stats.total_reflection_completion_tokens_est
    )
    parents = run_stats.parents
    rejected_candidates = run_stats.rejected_candidates
    already_persisted_runs = run_stats.already_persisted_runs or set()
    defer_commit = run_stats.defer_commit
    # SEED/ITER run names whose commit is deferred (see ``defer_commit``).
    # The cross-model orchestrator stamps frontier metrics onto the selected
    # ones and then commits every name in this list.
    pending_commit_runs: list[str] = []
    discovery_iter = run_stats.discovery_iter or {}
    phase_breakdowns = run_stats.phase_breakdowns or {}
    iter_extra_meta = run_stats.iter_extra_meta or {}
    # Per-million-token rates from src/models.json — loaded once per
    # save call so each ITER/REJECTED row can stamp its own dollar
    # estimate.  Empty dict (e.g. inside the inline SPROC where the
    # data file isn't bundled) collapses to None on every dollar
    # column, which the report-side Pareto plot then recomputes from
    # the persisted char totals using a locally-loaded rate table.
    iter_lookup: dict[int, Any] = {}
    if iteration_stats:
        for stats in iteration_stats:
            iter_lookup[int(getattr(stats, "iter_index", -1))] = stats

    # -- Cost metrics --------------------------------------------------------
    # Compute per-candidate estimated dollar cost, attached as a metric on
    # SEED and ITER_N runs so downstream tools can identify interesting
    # candidates without re-computing.
    _estimated_costs: dict[int, float | None] = {}
    if candidates and val_scores:
        # Per-call token counts per candidate; a duplicate candidate whose eval
        # GEPA reused (no fresh breakdown) inherits the REAL cost of the
        # identical tracked twin (see compute_pareto_candidates / #16).
        _tracked_tokens, _tokens_by_text = _resolve_candidate_tokens(
            candidates, discovery_iter, phase_breakdowns
        )
        for idx in range(len(candidates)):
            avg = _tracked_tokens.get(idx) or _tokens_by_text.get(
                _candidate_text(candidates[idx])
            )
            if avg is None:
                gepa_iter = discovery_iter.get(idx)
                bd = phase_breakdowns.get(gepa_iter) if gepa_iter is not None else None
                raise ValueError(
                    f"Candidate {idx} for model '{model}' has no token data and "
                    f"no identical tracked candidate to inherit it from "
                    f"(discovery_iter entry={discovery_iter.get(idx)}, "
                    f"phase_breakdown={'present' if bd else 'missing'}). "
                    "All candidates require tracked token counts for cost estimation."
                )
            if idx not in _tracked_tokens:
                logger.warning(
                    "Candidate %d for model %r had no tracked eval usage (its "
                    "eval was reused from an identical candidate); inheriting "
                    "that candidate's tracked per-call cost (~%d input tokens).",
                    idx,
                    model,
                    avg[0],
                )
            _estimated_costs[idx] = estimate_candidate_cost(model, avg[0], avg[1])

    # Render the parent indices for candidate ``idx`` as a comma-separated
    # list of run names (e.g. "CLAUDE_HAIKU_4_5_ITER_3" for a single parent,
    # "CLAUDE_HAIKU_4_5_ITER_1, CLAUDE_HAIKU_4_5_ITER_5" for a merge).
    # Falls back to the previous ``idx-1`` heuristic when ``parents`` wasn't
    # supplied (older callers).
    def _parent_str(idx: int) -> str:
        if parents and 0 <= idx < len(parents):
            parent_ids = [p for p in parents[idx] if p is not None]
            if parent_ids:
                names = [
                    make_run_name(model, int(p), is_seed=(int(p) == 0))
                    for p in parent_ids
                ]
                return ", ".join(names)
        # Fallback: linear chain (idx-1).
        if idx <= 0:
            return ""
        if idx == 1:
            return make_run_name(model, 0, is_seed=True)
        return make_run_name(model, idx - 1)

    # -- per-run experiment+artifact attribution --
    # Snapshot tracker counts BEFORE writing each run, then again
    # AFTER, and emit the delta as additional ``self_*`` params on
    # the run.  This lets the benchmark reader attribute experiment
    # bookkeeping cost to individual seed/iter/best runs (rather than
    # rolling everything into the BEST aggregate).
    tracker = get_active_tracker()

    def _tracker_snapshot() -> tuple[int, float, int, float]:
        if tracker is None:
            return (0, 0.0, 0, 0.0)
        return (
            tracker.total_experiment_calls,
            tracker.total_experiment_seconds,
            tracker.total_artifact_calls,
            tracker.total_artifact_seconds,
        )

    def _attach_self_attribution(
        run_name: str, before: tuple[int, float, int, float]
    ) -> None:
        """Add ``self_*`` params capturing exp/art deltas for one run.

        Issues one extra ``ALTER EXPERIMENT MODIFY RUN ADD PARAMETERS``
        call after the run is already written but before commit.  The
        cost of this extra call is itself attributed to the NEXT run's
        snapshot, which is acceptable approximation noise.
        """
        if tracker is None:
            return
        after = _tracker_snapshot()
        d_exp_calls = after[0] - before[0]
        d_exp_secs = after[1] - before[1]
        d_art_calls = after[2] - before[2]
        d_art_secs = after[3] - before[3]
        if not (d_exp_calls or d_art_calls):
            return
        extra = [
            {"name": "self_experiment_calls", "value": str(d_exp_calls)},
            {
                "name": "self_experiment_seconds",
                "value": str(round(d_exp_secs, 4)),
            },
            {"name": "self_artifact_calls", "value": str(d_art_calls)},
            {
                "name": "self_artifact_seconds",
                "value": str(round(d_art_secs, 4)),
            },
        ]
        try:
            extras_json = escape_sql_string(json.dumps(extra))
            timed_experiment_sql(
                session,
                f"ALTER EXPERIMENT {experiment_name} MODIFY RUN {run_name} "
                f"ADD PARAMETERS = '{extras_json}'",
            )
        except Exception as exc:
            logger.warning(
                "Failed to attach self_* attribution to run %s: %s",
                run_name,
                exc,
            )

    # -- Backfill Pareto metrics + commit already-persisted runs -------
    # ProgressiveExperimentTracker writes SEED/ITER/REJECTED runs during
    # the GEPA loop (left in RUNNING state) before the Pareto frontier
    # can be computed.  Now that we have all candidates, stamp metrics
    # and commit each run so every run carries the full frontier.
    if already_persisted_runs:
        for run_name_ap in already_persisted_runs:
            # Determine the candidate index for this run name so we can
            # look up its Pareto metrics.  Convention:
            #   SEED  → idx 0
            #   ITER_N → idx N
            #   REJECTED_N → no candidate in the population; skip
            #     Pareto metrics but still commit.
            idx_ap: int | None = None
            if "_SEED" in run_name_ap:
                idx_ap = 0
            elif "_ITER_" in run_name_ap:
                with contextlib.suppress(ValueError, IndexError):
                    idx_ap = int(run_name_ap.rsplit("_ITER_", 1)[1])

            if idx_ap is not None:
                if not _estimated_costs:
                    raise RuntimeError(
                        f"No cost estimates available for run {run_name_ap} "
                        f"(candidate {idx_ap}). Cannot compute cost metrics "
                        "without cost data."
                    )
                pareto_metrics = build_run_metrics(
                    valset_score=(
                        val_scores[idx_ap]
                        if val_scores and idx_ap < len(val_scores)
                        else None
                    ),
                    estimated_cost=_estimated_costs.get(idx_ap),
                    base_cost=_estimated_costs.get(0),
                )
                if pareto_metrics:
                    try:
                        metrics_json = json.dumps(pareto_metrics)
                        timed_experiment_sql(
                            session,
                            f"ALTER EXPERIMENT {experiment_name} MODIFY RUN "
                            f"{run_name_ap} ADD METRICS = '{metrics_json}'",
                        )
                    except Exception as exc:
                        logger.warning(
                            "Failed to backfill Pareto metrics on %s: %s",
                            run_name_ap,
                            exc,
                        )

            # Defer commit for SEED/ITER runs (idx_ap is not None) when the
            # caller will stamp cross-model frontier metrics on them; commit
            # REJECTED runs (idx_ap is None) immediately — they never join
            # the frontier.
            if defer_commit and idx_ap is not None:
                pending_commit_runs.append(run_name_ap)
                continue
            try:
                commit_experiment_run(session, experiment_name, run_name_ap)
            except Exception as exc:
                logger.warning(
                    "Failed to commit already-persisted run %s: %s",
                    run_name_ap,
                    exc,
                )

    # -- SEED run --
    seed_run = make_run_name(model, 0, is_seed=True)
    if seed_run not in already_persisted_runs:
        seed_stats = iter_lookup.get(0)
        seed_params = RunParams(
            function_impl=seed_prompt,
            model=model,
            iteration="0",
            function_name=function_name,
            score_source=score_source,
            num_examples=num_examples,
            avg_output_chars=avg_output_chars,
            status="completed",
            # Stamp the schema version on the SEED run only — anchors the
            # whole experiment to a known generation of cortex-code-skills.
            # See ``EXPERIMENT_SCHEMA_VERSION`` for what each version means.
            # Older experiments lack this param entirely, so a downstream
            # query like ``WHERE param:experiment_schema_version >= '2'``
            # cleanly partitions "has REJECTED runs" from "doesn't".
            experiment_schema_version=EXPERIMENT_SCHEMA_VERSION,
            # -- Aggregate stats (optimization-wide totals) --
            total_candidates=total_candidates,
            total_metric_calls=total_metric_calls,
            total_reflection_calls=total_reflection_calls,
            elapsed_seconds=elapsed_seconds,
            reflection_model=reflection_model,
            total_metric_seconds=total_metric_seconds,
            total_reflection_seconds=total_reflection_seconds,
            total_udf_compile_calls=total_udf_compile_calls,
            total_udf_compile_seconds=total_udf_compile_seconds,
            total_udf_exec_calls=total_udf_exec_calls,
            total_udf_exec_seconds=total_udf_exec_seconds,
            total_experiment_calls=total_experiment_calls,
            total_experiment_seconds=total_experiment_seconds,
            total_artifact_calls=total_artifact_calls,
            total_artifact_seconds=total_artifact_seconds,
            test_eval_metric_calls=test_eval_metric_calls,
            test_eval_metric_seconds=test_eval_metric_seconds,
            test_eval_reflection_calls=test_eval_reflection_calls,
            test_eval_reflection_seconds=test_eval_reflection_seconds,
            test_eval_udf_compile_calls=test_eval_udf_compile_calls,
            test_eval_udf_compile_seconds=test_eval_udf_compile_seconds,
            test_eval_udf_exec_calls=test_eval_udf_exec_calls,
            test_eval_udf_exec_seconds=test_eval_udf_exec_seconds,
            total_udf_prompt_tokens=total_udf_prompt_tokens,
            total_udf_completion_tokens=total_udf_completion_tokens,
            test_eval_udf_prompt_tokens=test_eval_udf_prompt_tokens,
            test_eval_udf_completion_tokens=test_eval_udf_completion_tokens,
            total_reflection_prompt_tokens_est=total_reflection_prompt_tokens_est,
            total_reflection_completion_tokens_est=total_reflection_completion_tokens_est,
            # -- Per-iteration timing for seed (iteration 0) --
            iter_seconds=(
                getattr(seed_stats, "iter_seconds", None) if seed_stats else None
            ),
            metric_call_count=(
                getattr(seed_stats, "metric_call_count", None) if seed_stats else None
            ),
            metric_seconds_total=(
                getattr(seed_stats, "metric_seconds_total", None)
                if seed_stats
                else None
            ),
            metric_seconds_avg=(
                getattr(seed_stats, "metric_seconds_avg", None) if seed_stats else None
            ),
            metric_seconds_p95=(
                getattr(seed_stats, "metric_seconds_p95", None) if seed_stats else None
            ),
            reflection_call_count=(
                getattr(seed_stats, "reflection_call_count", None)
                if seed_stats
                else None
            ),
            reflection_seconds_total=(
                getattr(seed_stats, "reflection_seconds_total", None)
                if seed_stats
                else None
            ),
            reflection_seconds_avg=(
                getattr(seed_stats, "reflection_seconds_avg", None)
                if seed_stats
                else None
            ),
            udf_compile_count=(
                getattr(seed_stats, "udf_compile_count", None) if seed_stats else None
            ),
            udf_compile_seconds_total=(
                getattr(seed_stats, "udf_compile_seconds_total", None)
                if seed_stats
                else None
            ),
            udf_exec_count=(
                getattr(seed_stats, "udf_exec_count", None) if seed_stats else None
            ),
            udf_exec_seconds_total=(
                getattr(seed_stats, "udf_exec_seconds_total", None)
                if seed_stats
                else None
            ),
            experiment_count=(
                getattr(seed_stats, "experiment_count", None) if seed_stats else None
            ),
            experiment_seconds_total=(
                getattr(seed_stats, "experiment_seconds_total", None)
                if seed_stats
                else None
            ),
            artifact_count=(
                getattr(seed_stats, "artifact_count", None) if seed_stats else None
            ),
            artifact_seconds_total=(
                getattr(seed_stats, "artifact_seconds_total", None)
                if seed_stats
                else None
            ),
            iter_eval_prompt_tokens=(
                getattr(seed_stats, "udf_prompt_tokens", None) if seed_stats else None
            ),
            iter_eval_completion_tokens=(
                getattr(seed_stats, "udf_completion_tokens", None)
                if seed_stats
                else None
            ),
            iter_reflection_prompt_tokens_est=(
                getattr(seed_stats, "reflection_prompt_tokens_est", None)
                if seed_stats
                else None
            ),
            iter_reflection_completion_tokens_est=(
                getattr(seed_stats, "reflection_completion_tokens_est", None)
                if seed_stats
                else None
            ),
            extra_metadata=(
                json.dumps(iter_extra_meta[0], default=str)
                if iter_extra_meta and 0 in iter_extra_meta
                else ""
            ),
        )
        seed_metrics = build_run_metrics(
            valset_score=seed_val_score,
            test_score=seed_test_score,
            estimated_cost=_estimated_costs.get(0),
            base_cost=_estimated_costs.get(0),  # SEED is the base → 1.0
        )
        seed_before = _tracker_snapshot()
        add_experiment_run(
            session,
            experiment_name,
            seed_run,
            params=seed_params,
            metrics=seed_metrics,
        )
        _attach_self_attribution(seed_run, seed_before)
        if defer_commit:
            pending_commit_runs.append(seed_run)
        else:
            commit_experiment_run(session, experiment_name, seed_run)

    # -- Iteration runs (skip index 0 = seed, already covered) --
    for idx, candidate_text in enumerate(candidates):
        if idx == 0:
            continue
        iter_run = make_run_name(model, idx)
        iter_score = val_scores[idx] if val_scores and idx < len(val_scores) else None
        if iter_run in already_persisted_runs:
            # Already fully handled by the backfill loop above, which wrote
            # the full-eval valset_score + estimated_cost (from
            # val_aggregate_scores) and committed the run.  Re-writing
            # metrics here would target a committed run and be rejected by
            # Snowflake, so just skip it.
            continue
        parent = _parent_str(idx) or seed_run
        # Look up the per-iteration tracker stats by GEPA's
        # discovery iteration (NOT by population position).  When the
        # collector observed an ``on_candidate_accepted`` event for
        # this candidate, it recorded the GEPA iteration that
        # produced it; that's the iteration whose tracker boundary
        # holds the work attributable to this run.
        #
        # Old behaviour mapped ``iter_lookup[idx]`` (idx = position
        # in result.candidates), which silently misattributed work
        # whenever GEPA had rejections in the middle: e.g. iter 1
        # rejected, iter 2 accepted → result.candidates[1] = iter 2,
        # but iter_lookup[1] still held iter 1's REJECTED work, so
        # ITER_1's row reported the wrong totals.  Worse, REJECTED_1
        # ALSO read iter_lookup[1] (correctly, by event.iteration-1),
        # producing a duplicate-looking row.
        gepa_iter_for_idx = (discovery_iter or {}).get(idx)
        # ``iter_lookup`` is keyed by ``IterationStats.iter_index`` =
        # the boundary index from ``per_iteration_stats``, where
        # ``iter_lookup[K]`` holds the work between mark_iteration
        # call K and K+1.  GEPA's ``mark_iteration`` fires at the top
        # of every main-loop iteration BEFORE ``state.i += 1``, and
        # events fire with ``iteration = state.i + 1`` AFTER the
        # increment.  So work for the iteration where the event
        # reports ``iteration = N`` is at ``iter_lookup[N - 1]``.
        # Both the accepted ITER and rejected REJECTED paths use
        # this same mapping; previously the accepted-ITER path was
        # off-by-one (or worse, used position-in-population), which
        # was the root cause of iter_seconds appearing identical
        # for an accepted ITER and rejected REJECTED neighbour.
        if gepa_iter_for_idx and gepa_iter_for_idx > 0:
            stats_idx = gepa_iter_for_idx - 1
        else:
            stats_idx = idx
        stats = iter_lookup.get(stats_idx)
        # Per-iteration ``num_examples`` = the metric_call_count for that
        # iteration.  Each metric invocation = one example evaluated, so
        # this matches the seed/best run's ``num_examples`` semantics
        # (size of the evaluation set used for that run).
        iter_num_examples = getattr(stats, "metric_call_count", None) if stats else None
        # Per-phase breakdown (parent_eval, reflection, new_cand_eval).
        # Picked up by the collector from the same on_candidate_accepted
        # event that supplied ``discovery_iter``; absent only if the
        # collector wasn't wired (older deploys).
        breakdown = (
            (phase_breakdowns or {}).get(gepa_iter_for_idx)
            if gepa_iter_for_idx
            else None
        )
        iter_params = RunParams(
            function_impl=candidate_text,
            model=model,
            iteration=str(idx),
            parent_candidate=parent,
            function_name=function_name,
            status="completed",
            num_examples=iter_num_examples,
            iter_seconds=getattr(stats, "iter_seconds", None) if stats else None,
            metric_call_count=(
                getattr(stats, "metric_call_count", None) if stats else None
            ),
            metric_seconds_total=(
                getattr(stats, "metric_seconds_total", None) if stats else None
            ),
            metric_seconds_avg=(
                getattr(stats, "metric_seconds_avg", None) if stats else None
            ),
            metric_seconds_p95=(
                getattr(stats, "metric_seconds_p95", None) if stats else None
            ),
            reflection_call_count=(
                getattr(stats, "reflection_call_count", None) if stats else None
            ),
            reflection_seconds_total=(
                getattr(stats, "reflection_seconds_total", None) if stats else None
            ),
            reflection_seconds_avg=(
                getattr(stats, "reflection_seconds_avg", None) if stats else None
            ),
            udf_compile_count=(
                getattr(stats, "udf_compile_count", None) if stats else None
            ),
            udf_compile_seconds_total=(
                getattr(stats, "udf_compile_seconds_total", None) if stats else None
            ),
            udf_exec_count=(getattr(stats, "udf_exec_count", None) if stats else None),
            udf_exec_seconds_total=(
                getattr(stats, "udf_exec_seconds_total", None) if stats else None
            ),
            experiment_count=(
                getattr(stats, "experiment_count", None) if stats else None
            ),
            experiment_seconds_total=(
                getattr(stats, "experiment_seconds_total", None) if stats else None
            ),
            artifact_count=(getattr(stats, "artifact_count", None) if stats else None),
            artifact_seconds_total=(
                getattr(stats, "artifact_seconds_total", None) if stats else None
            ),
            gepa_iteration=gepa_iter_for_idx,
            parent_eval_seconds=(breakdown.parent_eval.seconds if breakdown else None),
            phase_reflection_seconds=(
                breakdown.reflection.seconds if breakdown else None
            ),
            new_cand_eval_seconds=(
                breakdown.new_cand_eval.seconds if breakdown else None
            ),
            iter_input_chars=(
                breakdown.total_input_chars()
                if breakdown
                else (
                    (
                        getattr(stats, "udf_prompt_tokens", 0) * 4
                        + getattr(stats, "reflection_prompt_tokens_est", 0) * 4
                    )
                    if stats
                    and (
                        getattr(stats, "udf_prompt_tokens", 0)
                        or getattr(stats, "reflection_prompt_tokens_est", 0)
                    )
                    else None
                )
            ),
            iter_output_chars=(
                breakdown.total_output_chars()
                if breakdown
                else (
                    (
                        getattr(stats, "udf_completion_tokens", 0) * 4
                        + getattr(stats, "reflection_completion_tokens_est", 0) * 4
                    )
                    if stats
                    and (
                        getattr(stats, "udf_completion_tokens", 0)
                        or getattr(stats, "reflection_completion_tokens_est", 0)
                    )
                    else None
                )
            ),
            iter_dollars=(
                _estimate_iter_credits(breakdown, model, reflection_model)
                if breakdown is not None
                else None
            ),
            # Per-phase chars + minibatch sizes — feed the cleaner
            # per-call cost computation in the report renderer.
            new_cand_eval_input_chars=(
                breakdown.new_cand_eval.input_chars if breakdown else None
            ),
            new_cand_eval_output_chars=(
                breakdown.new_cand_eval.output_chars if breakdown else None
            ),
            new_cand_eval_minibatch_size=(
                breakdown.new_cand_eval_minibatch_size if breakdown else None
            ),
            parent_eval_input_chars=(
                breakdown.parent_eval.input_chars if breakdown else None
            ),
            parent_eval_output_chars=(
                breakdown.parent_eval.output_chars if breakdown else None
            ),
            parent_eval_minibatch_size=(
                breakdown.parent_eval_minibatch_size if breakdown else None
            ),
            # Per-iteration token breakdown.  Prefer per-phase
            # breakdown totals when available (they're the closest
            # honest accounting of "this candidate's iteration cost"
            # and stay consistent with the per-phase columns).  Fall
            # back to per-iteration tracker stats so older deploys
            # without ``phase_breakdowns`` still surface tokens.
            iter_eval_prompt_tokens=(
                breakdown.total_eval_prompt_tokens()
                if breakdown
                else (getattr(stats, "udf_prompt_tokens", None) if stats else None)
            ),
            iter_eval_completion_tokens=(
                breakdown.total_eval_completion_tokens()
                if breakdown
                else (getattr(stats, "udf_completion_tokens", None) if stats else None)
            ),
            iter_reflection_prompt_tokens_est=(
                breakdown.total_reflection_prompt_tokens_est()
                if breakdown
                else (
                    getattr(stats, "reflection_prompt_tokens_est", None)
                    if stats
                    else None
                )
            ),
            iter_reflection_completion_tokens_est=(
                breakdown.total_reflection_completion_tokens_est()
                if breakdown
                else (
                    getattr(stats, "reflection_completion_tokens_est", None)
                    if stats
                    else None
                )
            ),
            # Per-phase token splits — same provenance as per-phase
            # chars + minibatch sizes above.
            new_cand_eval_prompt_tokens=(
                breakdown.new_cand_eval.eval_prompt_tokens if breakdown else None
            ),
            new_cand_eval_completion_tokens=(
                breakdown.new_cand_eval.eval_completion_tokens if breakdown else None
            ),
            parent_eval_prompt_tokens=(
                breakdown.parent_eval.eval_prompt_tokens if breakdown else None
            ),
            parent_eval_completion_tokens=(
                breakdown.parent_eval.eval_completion_tokens if breakdown else None
            ),
            phase_reflection_prompt_tokens_est=(
                breakdown.reflection.reflection_prompt_tokens_est if breakdown else None
            ),
            phase_reflection_completion_tokens_est=(
                breakdown.reflection.reflection_completion_tokens_est
                if breakdown
                else None
            ),
            extra_metadata=(
                json.dumps(iter_extra_meta[idx], default=str)
                if iter_extra_meta and idx in iter_extra_meta
                else ""
            ),
        )
        iter_metrics = build_run_metrics(
            valset_score=iter_score,
            estimated_cost=_estimated_costs.get(idx),
            base_cost=_estimated_costs.get(0),
        )
        iter_before = _tracker_snapshot()
        try:
            add_experiment_run(
                session,
                experiment_name,
                iter_run,
                params=iter_params,
                metrics=iter_metrics,
            )
            _attach_self_attribution(iter_run, iter_before)
            if defer_commit:
                pending_commit_runs.append(iter_run)
            else:
                commit_experiment_run(session, experiment_name, iter_run)
        except SnowparkSessionException:
            logger.warning("Session closed — aborting remaining experiment saves")
            return pending_commit_runs

    # -- Upload artifacts to the winning ITER run --
    # Note: when this model's SEED/ITER runs are on the cross-model frontier,
    # their test_score / is_frontier metrics are stamped by the orchestrator
    # (stamp_frontier_metrics_on_runs) while the runs are still RUNNING, then
    # committed via the deferred-commit path — no separate run kind involved.
    winning_iter_run = make_run_name(model, best_idx, is_seed=(best_idx == 0))

    # Upload artifacts to the winning ITER run.
    if run_dir and os.path.isdir(run_dir):
        run_dir_contents = [
            f for f in os.listdir(run_dir) if os.path.isfile(os.path.join(run_dir, f))
        ]
        if run_dir_contents:
            try:
                put_experiment_artifact(
                    session,
                    experiment_name,
                    winning_iter_run,
                    local_path=run_dir,
                    subdir="run_dir",
                )
            except Exception as exc:
                logger.warning(
                    "Failed to upload run_dir artifacts (%d files in %s): %s",
                    len(run_dir_contents),
                    run_dir,
                    exc,
                )

    # SEED detail → this model's SEED run; BEST detail → the winning ITER run.
    # Each is written as that run's own ``eval_detail.json`` (one per run).
    model_seed_run = make_run_name(model, 0, is_seed=True)
    for label, details, target_run in (
        ("SEED", seed_eval_details, model_seed_run),
        ("BEST", best_eval_details, winning_iter_run),
    ):
        if not details:
            continue
        try:
            detail_path = write_eval_detail_artifact(details)
            put_experiment_artifact(
                session,
                experiment_name,
                target_run,
                local_path=detail_path,
            )
        except Exception as exc:
            logger.warning("Failed to upload %s eval detail: %s", label, exc)

    # -- REJECTED runs (one per GEPA-rejected proposal) --
    # Captured by the GEPACallback collector that the optimizer
    # passes in.  Persisted AFTER the winning ITER run is stamped so
    # an experiment reader can browse SEED → ITER_N → REJECTED_N in
    # the natural order in which the runs were observed.  Each rejected
    # candidate gets its own ALTER EXPERIMENT round-trip — same as
    # accepted runs — so the ``self_*`` attribution mechanism stays
    # consistent across run kinds.
    #
    # Failures here are caught per-run rather than aborting the
    # whole loop: one malformed rejection (e.g. a GEPA bug emitting
    # a NaN score) shouldn't lose all the others.  The caller
    # already wraps the entire ``save_optimization_to_experiment``
    # in try/except, so any uncaught exception inside this loop is
    # contained at that level.
    for ordinal, rec in enumerate(rejected_candidates or [], start=1):
        try:
            rejected_run = make_rejected_run_name(model, ordinal)
            if rejected_run in already_persisted_runs:
                continue
            # Map GEPA candidate indices to run names so the lineage
            # links back to actual runs in the experiment.  Empty
            # parent list collapses to "" (matches ITER_N default).
            parent_names = [
                make_run_name(model, idx, is_seed=(idx == 0))
                for idx in rec.parent_candidate_idxs
            ]
            parent_str = ", ".join(parent_names)
            # Look up the per-iteration tracker delta for this rejected
            # iteration.  ``mark_iteration`` fires once at the top of
            # every GEPA main-loop iteration via the ``_iteration_marker``
            # stop_callback, so the boundary at index ``K`` captures
            # the work done during the iteration where ``state.i == K``
            # (which GEPA reports on the rejection event as
            # ``iteration == K + 1``).  Mapping is therefore
            # ``iter_lookup[gepa_iteration - 1]``.
            #
            # Without this attribution the REJECTED run would carry
            # ``status='rejected'`` + the candidate text but ZERO
            # per-call counters, so per-candidate attribution in
            # BENCH_TRACKING_DETAILS would be incomplete even after
            # writing individual REJECTED runs.
            iter_idx = rec.gepa_iteration - 1 if rec.gepa_iteration > 0 else None
            rstats = iter_lookup.get(iter_idx) if iter_idx is not None else None
            # Per-row mean of the rejected proposal's subsample scores.
            # GEPA reports ``new_score`` as a SUM over the minibatch
            # (one score per training example).  Divide by the
            # minibatch size to get an average comparable to the
            # per-row valset score that accepted ITER runs persist —
            # otherwise the report's Score column compares
            # ``sum(0..1)`` (0..N range) to ``mean(0..1)`` (0..1 range)
            # and rejected rows look ~10x higher than accepted ones.
            subsample_mean = None
            if (
                rec.new_score is not None
                and rec.subsample_size
                and rec.subsample_size > 0
            ):
                subsample_mean = rec.new_score / rec.subsample_size
            rejected_params = RunParams(
                function_impl=rec.candidate_text,
                model=model,
                # ``iteration`` is the rejection ORDINAL (1-indexed,
                # matches the run name suffix ``REJECTED_<N>``) — NOT
                # the GEPA iteration number.  This deliberately mimics
                # the accepted ITER convention where ``iteration``
                # is the position in ``result.candidates``: both are
                # positional indices in their own series, just in
                # different series (population vs rejection list).
                # Showing the GEPA iter here previously caused
                # "iter=5 / accepted" rows to appear next to "iter=5
                # / rejected" rows that referred to completely
                # different events, which was confusing.  The actual
                # GEPA iter survives in the ``gepa_iteration`` param
                # below for tooling that wants the original number.
                iteration=str(ordinal),
                parent_candidate=parent_str,
                function_name=function_name,
                status="rejected",
                rejection_kind=rec.kind,
                rejection_reason=rec.reason,
                subsample_score_old=rec.old_score,
                subsample_score_new=rec.new_score,
                subsample_size=rec.subsample_size,
                subsample_score_new_mean=subsample_mean,
                gepa_iteration=rec.gepa_iteration,
                # Per-phase breakdown — same fields the accepted ITER
                # path uses, so the report can render them in identical
                # columns and a reader can directly compare a rejected
                # iter's phase costs against the accepted iter that
                # surrounds it.
                parent_eval_seconds=(
                    rec.phase_breakdown.parent_eval.seconds
                    if rec.phase_breakdown
                    else None
                ),
                phase_reflection_seconds=(
                    rec.phase_breakdown.reflection.seconds
                    if rec.phase_breakdown
                    else None
                ),
                new_cand_eval_seconds=(
                    rec.phase_breakdown.new_cand_eval.seconds
                    if rec.phase_breakdown
                    else None
                ),
                iter_input_chars=(
                    rec.phase_breakdown.total_input_chars()
                    if rec.phase_breakdown
                    else None
                ),
                iter_output_chars=(
                    rec.phase_breakdown.total_output_chars()
                    if rec.phase_breakdown
                    else None
                ),
                iter_dollars=(
                    _estimate_iter_credits(rec.phase_breakdown, model, reflection_model)
                    if rec.phase_breakdown is not None
                    else None
                ),
                # Per-phase chars + minibatch sizes for per-call cost
                # computation; rejected runs always have a phase
                # breakdown, so populate unconditionally.
                new_cand_eval_input_chars=(
                    rec.phase_breakdown.new_cand_eval.input_chars
                    if rec.phase_breakdown
                    else None
                ),
                new_cand_eval_output_chars=(
                    rec.phase_breakdown.new_cand_eval.output_chars
                    if rec.phase_breakdown
                    else None
                ),
                new_cand_eval_minibatch_size=(
                    rec.phase_breakdown.new_cand_eval_minibatch_size
                    if rec.phase_breakdown
                    else None
                ),
                parent_eval_input_chars=(
                    rec.phase_breakdown.parent_eval.input_chars
                    if rec.phase_breakdown
                    else None
                ),
                parent_eval_output_chars=(
                    rec.phase_breakdown.parent_eval.output_chars
                    if rec.phase_breakdown
                    else None
                ),
                parent_eval_minibatch_size=(
                    rec.phase_breakdown.parent_eval_minibatch_size
                    if rec.phase_breakdown
                    else None
                ),
                # Per-iteration token breakdown — prefer phase totals
                # (always populated for rejected runs by the GEPA
                # collector); fall back to tracker stats so older
                # deploys still surface the value.
                iter_eval_prompt_tokens=(
                    rec.phase_breakdown.total_eval_prompt_tokens()
                    if rec.phase_breakdown
                    else (
                        getattr(rstats, "udf_prompt_tokens", None) if rstats else None
                    )
                ),
                iter_eval_completion_tokens=(
                    rec.phase_breakdown.total_eval_completion_tokens()
                    if rec.phase_breakdown
                    else (
                        getattr(rstats, "udf_completion_tokens", None)
                        if rstats
                        else None
                    )
                ),
                iter_reflection_prompt_tokens_est=(
                    rec.phase_breakdown.total_reflection_prompt_tokens_est()
                    if rec.phase_breakdown
                    else (
                        getattr(rstats, "reflection_prompt_tokens_est", None)
                        if rstats
                        else None
                    )
                ),
                iter_reflection_completion_tokens_est=(
                    rec.phase_breakdown.total_reflection_completion_tokens_est()
                    if rec.phase_breakdown
                    else (
                        getattr(rstats, "reflection_completion_tokens_est", None)
                        if rstats
                        else None
                    )
                ),
                # Per-phase token splits — same provenance as the
                # per-phase chars + minibatch sizes above.
                new_cand_eval_prompt_tokens=(
                    rec.phase_breakdown.new_cand_eval.eval_prompt_tokens
                    if rec.phase_breakdown
                    else None
                ),
                new_cand_eval_completion_tokens=(
                    rec.phase_breakdown.new_cand_eval.eval_completion_tokens
                    if rec.phase_breakdown
                    else None
                ),
                parent_eval_prompt_tokens=(
                    rec.phase_breakdown.parent_eval.eval_prompt_tokens
                    if rec.phase_breakdown
                    else None
                ),
                parent_eval_completion_tokens=(
                    rec.phase_breakdown.parent_eval.eval_completion_tokens
                    if rec.phase_breakdown
                    else None
                ),
                phase_reflection_prompt_tokens_est=(
                    rec.phase_breakdown.reflection.reflection_prompt_tokens_est
                    if rec.phase_breakdown
                    else None
                ),
                phase_reflection_completion_tokens_est=(
                    rec.phase_breakdown.reflection.reflection_completion_tokens_est
                    if rec.phase_breakdown
                    else None
                ),
                # Per-iteration counters: the cost of the rejected
                # iteration (parent eval + reflection LLM call + new
                # candidate minibatch eval).  Lifted from the same
                # IterationStats that drives ``num_examples`` /
                # ``metric_call_count`` on accepted ITER_N runs, so
                # rejected and accepted runs use a single source of
                # truth for per-iter timing.
                num_examples=(
                    getattr(rstats, "metric_call_count", None) if rstats else None
                ),
                iter_seconds=(
                    getattr(rstats, "iter_seconds", None) if rstats else None
                ),
                metric_call_count=(
                    getattr(rstats, "metric_call_count", None) if rstats else None
                ),
                metric_seconds_total=(
                    getattr(rstats, "metric_seconds_total", None) if rstats else None
                ),
                metric_seconds_avg=(
                    getattr(rstats, "metric_seconds_avg", None) if rstats else None
                ),
                metric_seconds_p95=(
                    getattr(rstats, "metric_seconds_p95", None) if rstats else None
                ),
                reflection_call_count=(
                    getattr(rstats, "reflection_call_count", None) if rstats else None
                ),
                reflection_seconds_total=(
                    getattr(rstats, "reflection_seconds_total", None)
                    if rstats
                    else None
                ),
                reflection_seconds_avg=(
                    getattr(rstats, "reflection_seconds_avg", None) if rstats else None
                ),
                udf_compile_count=(
                    getattr(rstats, "udf_compile_count", None) if rstats else None
                ),
                udf_compile_seconds_total=(
                    getattr(rstats, "udf_compile_seconds_total", None)
                    if rstats
                    else None
                ),
                udf_exec_count=(
                    getattr(rstats, "udf_exec_count", None) if rstats else None
                ),
                udf_exec_seconds_total=(
                    getattr(rstats, "udf_exec_seconds_total", None) if rstats else None
                ),
                experiment_count=(
                    getattr(rstats, "experiment_count", None) if rstats else None
                ),
                experiment_seconds_total=(
                    getattr(rstats, "experiment_seconds_total", None)
                    if rstats
                    else None
                ),
                artifact_count=(
                    getattr(rstats, "artifact_count", None) if rstats else None
                ),
                artifact_seconds_total=(
                    getattr(rstats, "artifact_seconds_total", None) if rstats else None
                ),
            )
            rejected_before = _tracker_snapshot()
            add_experiment_run(
                session,
                experiment_name,
                rejected_run,
                params=rejected_params,
                # No metrics for rejected runs — valset_score / test_score
                # were never computed (GEPA short-circuited at the
                # subsample gate).  Subsample scores live in the
                # ``subsample_score_old`` / ``..._new`` parameters.
                metrics=None,
            )
            _attach_self_attribution(rejected_run, rejected_before)
            commit_experiment_run(session, experiment_name, rejected_run)
        except SnowparkSessionException:
            logger.warning("Session closed — aborting remaining experiment saves")
            return pending_commit_runs
        except Exception as exc:
            logger.warning(
                "Failed to persist rejected candidate #%d for model %s: %s",
                ordinal,
                model,
                exc,
            )

    return pending_commit_runs
