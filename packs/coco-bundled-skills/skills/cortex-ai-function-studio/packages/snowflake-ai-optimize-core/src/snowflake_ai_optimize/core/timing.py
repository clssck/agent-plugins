# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Timing instrumentation for AI optimization runs.

Provides :class:`TimingTracker` — a thread-safe collector of per-call durations
and token counts for metric evaluation, reflection, UDF execution, experiment
DDL, and artifact uploads.  Also provides context-variable accessors
(:func:`get_active_tracker` / :func:`set_active_tracker`) so any code path in
the call stack can record timing events without explicit tracker threading.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

# Thread-local active tracker, looked up by batched evaluators and timing hooks.
_tracker_thread_local = threading.local()

# Per-thread hooks invoked by SnowflakeAdapter.evaluate. Used to capture
# "gepa_thinking" gaps (wall-time between consecutive evaluate calls).
# Thread-local to avoid race conditions between concurrent model workers.
_evaluate_hooks_thread_local = threading.local()


# ---------------------------------------------------------------------------
# Public module-level API
# ---------------------------------------------------------------------------


def get_active_tracker() -> TimingTracker | None:
    """Return the TimingTracker for the current thread, if any."""
    return getattr(_tracker_thread_local, "tracker", None)


def set_active_tracker(tracker: TimingTracker | None) -> None:
    """Bind a TimingTracker to the current thread (None to clear)."""
    _tracker_thread_local.tracker = tracker


def set_evaluate_hooks(
    pre: Callable[[], None] | None = None,
    post: Callable[[], None] | None = None,
) -> None:
    """Bind ``pre`` / ``post`` evaluate hooks to the current thread.

    The wrapper inside ``SnowflakeAdapter.evaluate`` invokes ``pre()``
    immediately before the evaluation body and ``post()`` from a
    ``finally`` block so it runs on both success and failure.  Pass
    ``None`` for either argument to leave that hook unset.

    Hooks are scoped to the current thread; concurrent calls from
    sibling worker threads cannot observe or clobber each other.
    """
    _evaluate_hooks_thread_local.pre = pre
    _evaluate_hooks_thread_local.post = post


def clear_evaluate_hooks() -> None:
    """Remove the current thread's pre/post evaluate hooks."""
    _evaluate_hooks_thread_local.pre = None
    _evaluate_hooks_thread_local.post = None


# ---------------------------------------------------------------------------
# Private module-level helpers
# ---------------------------------------------------------------------------


def _get_evaluate_hooks() -> tuple[
    Callable[[], None] | None, Callable[[], None] | None
]:
    return (
        getattr(_evaluate_hooks_thread_local, "pre", None),
        getattr(_evaluate_hooks_thread_local, "post", None),
    )


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = round(q * (len(s) - 1))
    return float(s[max(0, min(idx, len(s) - 1))])


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrackerSnapshot:
    """Immutable point-in-time snapshot of a TimingTracker's totals.

    Use ``tracker.snapshot()`` before an operation and ``snapshot.delta(tracker)``
    afterward to compute a clean set of per-operation cost deltas without
    manually declaring 10+ local variables.
    """

    metric_calls: int
    metric_seconds: float
    udf_compile_calls: int
    udf_compile_seconds: float
    udf_exec_calls: int
    udf_exec_seconds: float
    reflection_calls: int
    reflection_seconds: float
    udf_prompt_tokens: int
    udf_completion_tokens: int

    def delta(self, tracker: TimingTracker) -> TrackerDelta:
        """Compute difference between this snapshot and the tracker's current state."""
        return TrackerDelta(
            metric_calls=tracker.total_metric_calls - self.metric_calls,
            metric_seconds=round(tracker.total_metric_seconds - self.metric_seconds, 6),
            udf_compile_calls=tracker.total_udf_compile_calls - self.udf_compile_calls,
            udf_compile_seconds=round(
                tracker.total_udf_compile_seconds - self.udf_compile_seconds, 4
            ),
            udf_exec_calls=tracker.total_udf_exec_calls - self.udf_exec_calls,
            udf_exec_seconds=round(
                tracker.total_udf_exec_seconds - self.udf_exec_seconds, 4
            ),
            reflection_calls=tracker.total_reflection_calls - self.reflection_calls,
            reflection_seconds=round(
                tracker.total_reflection_seconds - self.reflection_seconds, 4
            ),
            udf_prompt_tokens=tracker.total_udf_prompt_tokens - self.udf_prompt_tokens,
            udf_completion_tokens=(
                tracker.total_udf_completion_tokens - self.udf_completion_tokens
            ),
        )


@dataclass(frozen=True)
class TrackerDelta:
    """Result of ``TrackerSnapshot.delta(tracker)`` — cost of one phase."""

    metric_calls: int
    metric_seconds: float
    udf_compile_calls: int
    udf_compile_seconds: float
    udf_exec_calls: int
    udf_exec_seconds: float
    reflection_calls: int
    reflection_seconds: float
    udf_prompt_tokens: int
    udf_completion_tokens: int

    def apply_to(self, output: dict[str, object], prefix: str = "test_eval") -> None:
        """Write all delta fields into *output* with the given key prefix."""
        output[f"{prefix}_metric_calls"] = self.metric_calls
        output[f"{prefix}_metric_seconds"] = self.metric_seconds
        output[f"{prefix}_udf_compile_calls"] = self.udf_compile_calls
        output[f"{prefix}_udf_compile_seconds"] = self.udf_compile_seconds
        output[f"{prefix}_udf_exec_calls"] = self.udf_exec_calls
        output[f"{prefix}_udf_exec_seconds"] = self.udf_exec_seconds
        output[f"{prefix}_reflection_calls"] = self.reflection_calls
        output[f"{prefix}_reflection_seconds"] = self.reflection_seconds
        output[f"{prefix}_udf_prompt_tokens"] = self.udf_prompt_tokens
        output[f"{prefix}_udf_completion_tokens"] = self.udf_completion_tokens


@dataclass
class IterationStats:
    """Per-iteration timing snapshot.

    Captures the deltas in metric/reflection counts and durations between
    successive iteration boundaries, plus the wall-clock duration of the
    iteration itself.

    Token columns (added 2026-05): per-iteration token consumption split
    by call kind so reports can answer "how many tokens did THIS iteration
    spend on evaluating candidates vs running reflection".
    - ``udf_*`` are REAL token counts from AI_COMPLETE's ``usage`` block.
    - ``reflection_*_est`` are CHAR-BASED estimates (input_chars // 4 /
      output_chars // 4) since the reflection path keeps
      ``show_details=False``.  ``_est`` suffix is preserved through to
      the experiment params so downstream readers can distinguish.
    """

    iter_index: int
    iter_seconds: float
    metric_call_count: int
    metric_seconds_total: float
    metric_seconds_avg: float
    metric_seconds_p95: float
    reflection_call_count: int
    reflection_seconds_total: float
    reflection_seconds_avg: float
    udf_compile_count: int
    udf_compile_seconds_total: float
    udf_exec_count: int
    udf_exec_seconds_total: float
    experiment_count: int
    experiment_seconds_total: float
    artifact_count: int
    artifact_seconds_total: float
    udf_prompt_tokens: int = 0
    udf_completion_tokens: int = 0
    reflection_prompt_tokens_est: int = 0
    reflection_completion_tokens_est: int = 0


class TimingTracker:
    """Thread-safe collector of per-call durations for metric and reflection.

    The tracker accumulates one entry in ``metric_durations`` per metric
    call and one entry in ``reflection_durations`` per reflection LLM
    invocation.  Iteration boundaries are recorded via ``mark_iteration``;
    the per-iteration view is reconstructed by diffing successive
    boundary indices.

    UDF lifecycle is tracked separately: ``udf_compile_durations``
    captures every ``CREATE OR REPLACE TEMPORARY FUNCTION`` round-trip
    while ``udf_exec_durations`` captures every Snowpark
    ``select(...).collect()`` that invokes a candidate function on a
    batch of rows.  Splitting compile vs exec exposes whether GEPA's
    iteration cost is dominated by repeated DDL or by actual model
    inference on the candidate.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.metric_durations: list[float] = []
        self.reflection_durations: list[float] = []
        # ``udf_compile_*`` counters predate the inline-eval migration.  Body
        # and prompt mode both retired the ``CREATE TEMPORARY FUNCTION`` step
        # in favor of a single inline CTE SELECT, so these counters report 0
        # in body/body_agent/prompt mode after that migration.  Kept for
        # back-compat with downstream readers (BENCH_RESULTS, plot_html.py,
        # experiment params, model_output aggregates) so report viewers see
        # the field as 0 rather than missing.  ``udf_exec_*`` still tracks
        # the inline SELECT round-trip.
        self.udf_compile_durations: list[float] = []
        self.udf_exec_durations: list[float] = []
        self.experiment_durations: list[float] = []
        self.artifact_durations: list[float] = []
        # Per-call token tuples (prompt_tokens, completion_tokens) recorded
        # alongside ``udf_exec_durations`` and ``reflection_durations`` so
        # ``per_iteration_stats`` can slice them with the same iteration
        # boundaries.  UDF entries hold REAL token counts from
        # AI_COMPLETE's usage block; reflection entries hold char-based
        # estimates (input_chars // 4 / output_chars // 4) since the
        # current reflection path keeps ``show_details=False``.  Lists
        # stay aligned with their duration counterparts even when token
        # info is missing — entries are recorded as ``(0, 0)`` to keep
        # indexing trivial.
        self.udf_exec_tokens: list[tuple[int, int]] = []
        self.reflection_tokens: list[tuple[int, int]] = []
        self._metric_iter_boundaries: list[int] = [0]
        self._reflection_iter_boundaries: list[int] = [0]
        self._udf_compile_iter_boundaries: list[int] = [0]
        self._udf_exec_iter_boundaries: list[int] = [0]
        self._experiment_iter_boundaries: list[int] = [0]
        self._artifact_iter_boundaries: list[int] = [0]
        self._iter_wall_times: list[float] = []
        self._last_iter_start: float = time.perf_counter()
        # Anchor perf_counter (monotonic, process-wide) to wall-clock
        # time so events from this tracker can be stitched onto the same
        # absolute timeline as events from sibling trackers running on
        # other model threads.  Each event carries an absolute epoch-ms
        # start/end, computed via ``_perf_to_epoch_ms``.
        self._wall_start_perf: float = time.perf_counter()
        self._wall_start_epoch_ms: float = time.time() * 1000.0
        # Phase-level events (``phase``, ``test_eval``, ``save``,
        # ``setup``, ``gepa_loop``) live in a regular list — they are
        # coarse markers we always keep so the Gantt timeline shows the
        # high-level shape even if fine-grained events are decimated.
        self._phase_events: list[dict] = []
        # Fine-grained per-call events are split into two buckets:
        #
        # 1. ``_metric_events``: bounded deque for metric events, which
        #    can number 5000-10000+ in a single run.  Oldest metric events
        #    are evicted to cap memory, which is acceptable since they're
        #    individually low-value on the Gantt (dense ribbons).
        #
        # 2. ``_important_fine_events``: unbounded list for reflection,
        #    udf_compile, udf_exec, experiment, and artifact events.
        #    These are few per run (typically <300 total) but crucial for
        #    understanding the Gantt structure — a single reflection call
        #    taking 30s is far more informative than any one metric event.
        #    Previously these were evicted by the flood of metric events
        #    sharing one deque.
        self._max_metric_events: int = 5000
        self._metric_events: deque[dict] = deque(maxlen=self._max_metric_events)
        self._important_fine_events: list[dict] = []
        # Op types that are "phase-level" and bypass fine-grained storage.
        self._phase_event_types: frozenset[str] = frozenset(
            {"phase", "test_eval", "save", "setup", "gepa_loop"}
        )
        # Op types routed to the unbounded important-events list.
        # The ``cocoevolve_*`` family is emitted by ``snow_gepa_optimize_evolve``
        # to mark every per-iteration CocoEvolve worker boundary plus the
        # synthetic engine-overhead gaps computed post-loop.  These are
        # few per run (~6 types × tens of iterations) but central to the
        # Gantt timeline + ``_synthesize_engine_overhead_events`` analysis,
        # so we keep them in the unbounded list rather than letting them
        # share the 5000-cap ``_metric_events`` deque with per-row metric
        # events that can crowd them out via FIFO eviction.
        self._important_event_types: frozenset[str] = frozenset(
            {
                "reflection",
                "udf_compile",
                "udf_exec",
                "experiment",
                "artifact",
                "dataset_load",
                "gepa_thinking",
                "cocoevolve_iter",
                "cocoevolve_propose",
                "cocoevolve_eval",
                "cocoevolve_db_write",
                "cocoevolve_db_snapshot",
                "cocoevolve_graph_update",
                "cocoevolve_engine",
            }
        )
        # Char-level cost accounting: (model, kind) → {input_chars, output_chars}.
        # ``kind`` is "reflection" or "udf". Converted to token estimates
        # (chars / 4) and USD at experiment-save time.
        self.char_usage: dict[tuple[str, str], dict[str, int]] = {}
        # Real token accounting from AI_COMPLETE's usage block (injected via
        # show_details=>TRUE). Same (model, kind) key. Coexists with char_usage
        # for back-compat with the cost-quality Pareto plot.
        self.token_usage: dict[tuple[str, str], dict[str, int]] = {}

    def _perf_to_epoch_ms(self, perf_ts: float) -> float:
        """Convert a process-local perf_counter() value to an absolute
        epoch-millisecond timestamp using the anchor captured at __init__.

        Two trackers in the same process share a clock: any pair of
        events recorded in this process can be ordered and overlapped
        on the same timeline by their epoch_ms values, regardless of
        which tracker recorded them.
        """  # noqa: D205
        return (perf_ts - self._wall_start_perf) * 1000.0 + self._wall_start_epoch_ms

    def _push_event(
        self,
        op_type: str,
        start_perf: float,
        end_perf: float,
        label: str = "",
        thread_id: int | None = None,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        input_chars: int | None = None,
        output_chars: int | None = None,
        model: str | None = None,
        token_source: str | None = None,
    ) -> None:
        """Append an event to the appropriate per-tracker bucket.

        Caller MUST hold ``self._lock``.

        Routing:
        - Phase markers (``phase``, ``test_eval``, ``save``, ``setup``,
          ``gepa_loop``) → unbounded ``_phase_events`` list.
        - Important fine-grained events (``reflection``, ``udf_compile``,
          ``udf_exec``, ``experiment``, ``artifact``, ``dataset_load``,
          ``gepa_thinking``) → unbounded ``_important_fine_events`` list.
          These are few per run (<300) but critical for Gantt readability.
        - Metric events → bounded ``_metric_events`` deque (oldest evicted
          when cap is reached).  These are numerous (5000-10000+) but
          individually low-value.

        Token / char metadata (added 2026-05 for the per-call token Gantt):
        - ``prompt_tokens`` / ``completion_tokens``: real counts for UDF
          (sourced from AI_COMPLETE's ``usage`` block via
          ``show_details=>TRUE``) or char-based estimates for reflection
          (input_chars // 4 / output_chars // 4).  Both fields are
          ``None`` for events that don't carry token info (metric, setup,
          save, experiment, artifact, …) so the renderer can decide
          whether to draw a token-axis bar.
        - ``input_chars`` / ``output_chars``: raw char totals captured at
          the same call site.  Coexist with the token fields so reports
          rendered against pre-token-tracking data can still derive a
          chars-based proxy.
        - ``token_source``: ``"real"`` (UDF eval) or ``"char_est"``
          (reflection) — lets the report disambiguate at hover time.
          ``None`` when no token info is attached.
        - ``model``: model name (per-call), useful for legend grouping
          when a single thread serves multiple candidate models.
        """
        if thread_id is None:
            thread_id = threading.get_ident()
        evt = {
            "type": op_type,
            "start_ms": round(self._perf_to_epoch_ms(start_perf), 3),
            "end_ms": round(self._perf_to_epoch_ms(end_perf), 3),
            "thread_id": thread_id,
            "label": label,
        }
        if prompt_tokens is not None:
            evt["prompt_tokens"] = int(prompt_tokens)
        if completion_tokens is not None:
            evt["completion_tokens"] = int(completion_tokens)
        if input_chars is not None:
            evt["input_chars"] = int(input_chars)
        if output_chars is not None:
            evt["output_chars"] = int(output_chars)
        if token_source is not None:
            evt["token_source"] = token_source
        if model is not None:
            evt["model"] = model
        if op_type in self._phase_event_types:
            self._phase_events.append(evt)
        elif op_type in self._important_event_types:
            self._important_fine_events.append(evt)
        else:
            self._metric_events.append(evt)

    def add_metric(self, duration: float) -> None:
        end_perf = time.perf_counter()
        start_perf = end_perf - duration
        with self._lock:
            self.metric_durations.append(duration)
            self._push_event("metric", start_perf, end_perf)

    def add_metric_batch(
        self, start_perf: float, end_perf: float, n_items: int
    ) -> None:
        """Record a batched metric call (e.g. ``llm_judge_batch``).

        Unlike ``add_metric`` which produces one event per call (with the
        event spanning ``[end-duration, end]``), batched metric calls run
        N items inside a SINGLE SQL round-trip.  Naively recording N
        events of width ``per_item`` all timestamped at the moment the
        SQL call returned (the previous behaviour) collapsed the whole
        batch into a microsecond-wide cluster on the Gantt timeline,
        leaving the actual ``[start_perf, end_perf]`` SQL window blank.

        This method instead records ONE event covering the real
        ``[start_perf, end_perf]`` window (so the chart shows where the
        wall time actually went) while still appending ``n_items`` copies
        of ``per_item`` to ``metric_durations`` so the per-call totals,
        averages, and percentiles stay comparable to single-call mode.
        """
        if n_items <= 0:
            return
        per_item = (end_perf - start_perf) / n_items
        with self._lock:
            self.metric_durations.extend([per_item] * n_items)
            # ``label`` carries the batch size so the Gantt tooltip
            # disambiguates a 1-item "batch" (degenerate case) from a
            # 60-item batch with the same wall time.
            self._push_event("metric", start_perf, end_perf, label=f"batch_x{n_items}")

    def add_reflection(
        self,
        duration: float,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        input_chars: int | None = None,
        output_chars: int | None = None,
        model: str | None = None,
    ) -> None:
        """Record a reflection LLM call.

        Token args are accepted as char-based ESTIMATES today (the
        reflection path keeps ``show_details=False`` on AI_COMPLETE so
        the ``usage`` block is not surfaced).  Callers should pass
        ``input_chars // 4`` / ``output_chars // 4`` when known.  The
        ``token_source`` stamped on the event reflects this provenance
        (``"char_est"``) so downstream renderers can communicate the
        ~10–20% accuracy caveat at hover time.
        """
        end_perf = time.perf_counter()
        start_perf = end_perf - duration
        with self._lock:
            self.reflection_durations.append(duration)
            self.reflection_tokens.append(
                (
                    int(prompt_tokens) if prompt_tokens is not None else 0,
                    int(completion_tokens) if completion_tokens is not None else 0,
                )
            )
            self._push_event(
                "reflection",
                start_perf,
                end_perf,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                input_chars=input_chars,
                output_chars=output_chars,
                model=model,
                token_source=(
                    "char_est"
                    if (prompt_tokens is not None or completion_tokens is not None)
                    else None
                ),
            )

    def add_udf_compile(self, duration: float) -> None:
        end_perf = time.perf_counter()
        start_perf = end_perf - duration
        with self._lock:
            self.udf_compile_durations.append(duration)
            self._push_event("udf_compile", start_perf, end_perf)

    def add_udf_exec(
        self,
        duration: float,
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        input_chars: int | None = None,
        output_chars: int | None = None,
        model: str | None = None,
    ) -> None:
        """Record a UDF execution batch (one inline AI_COMPLETE round-trip).

        ``prompt_tokens`` / ``completion_tokens`` are REAL counts from
        AI_COMPLETE's ``usage`` block (since the inline-eval migration
        injects ``show_details=>TRUE``).  ``token_source="real"`` is
        stamped on the event so the renderer can mark this as the
        authoritative token count rather than an estimate.
        """
        end_perf = time.perf_counter()
        start_perf = end_perf - duration
        with self._lock:
            self.udf_exec_durations.append(duration)
            self.udf_exec_tokens.append(
                (
                    int(prompt_tokens) if prompt_tokens is not None else 0,
                    int(completion_tokens) if completion_tokens is not None else 0,
                )
            )
            self._push_event(
                "udf_exec",
                start_perf,
                end_perf,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                input_chars=input_chars,
                output_chars=output_chars,
                model=model,
                token_source=(
                    "real"
                    if (prompt_tokens is not None or completion_tokens is not None)
                    else None
                ),
            )

    def add_experiment(self, duration: float, label: str = "") -> None:
        """Record a Snowflake Experiment DDL/DML round-trip.

        Covers ``CREATE EXPERIMENT``, ``ALTER EXPERIMENT ADD RUN``,
        ``ALTER EXPERIMENT MODIFY RUN ADD PARAMETERS/METRICS``, and
        ``COMMIT RUN`` — the bookkeeping cost of persisting per-iteration
        results to the experiment object.

        ``label`` (e.g. ``"add_run"`` / ``"commit"``) is recorded on the
        timeline event so the Gantt chart can disambiguate which
        experiment SQL contributed to a given segment.
        """
        end_perf = time.perf_counter()
        start_perf = end_perf - duration
        with self._lock:
            self.experiment_durations.append(duration)
            self._push_event("experiment", start_perf, end_perf, label=label)

    def add_artifact_upload(self, duration: float, label: str = "") -> None:
        """Record a ``session.file.put`` upload to an experiment stage.

        Used to surface the time spent shipping ``run_dir/`` and
        ``eval_detail.json`` artifacts — typically the slowest part of
        post-optimization persistence for large run dirs.
        """
        end_perf = time.perf_counter()
        start_perf = end_perf - duration
        with self._lock:
            self.artifact_durations.append(duration)
            self._push_event("artifact", start_perf, end_perf, label=label)

    def add_chars(
        self, model: str, kind: str, input_chars: int, output_chars: int
    ) -> None:
        """Record character counts for one AI call.

        We use chars (not real token counts) because Snowflake's
        ``AI_COMPLETE`` doesn't surface usage info on the default
        path; per-token cost is later approximated as ``chars / 4``
        when ``_save_optimization_to_experiment_impl`` converts
        these totals to dollars using the per-model rates from
        ``src/models.json``.  ~10-20% off the real number — fine
        for the cost-quality Pareto plot, where we care about
        relative ranking, not absolute USD.
        """
        if not model or not kind:
            return
        with self._lock:
            key = (model, kind)
            bucket = self.char_usage.get(key)
            if bucket is None:
                bucket = {"input_chars": 0, "output_chars": 0}
                self.char_usage[key] = bucket
            bucket["input_chars"] += max(0, int(input_chars))
            bucket["output_chars"] += max(0, int(output_chars))

    @property
    def char_usage_snapshot(self) -> dict[tuple[str, str], dict[str, int]]:
        """Return a deep-ish copy of ``char_usage`` for cross-thread reads."""
        with self._lock:
            return {k: dict(v) for k, v in self.char_usage.items()}

    def add_tokens(
        self,
        model: str,
        kind: str,
        prompt_tokens: int | None,
        completion_tokens: int | None,
    ) -> None:
        """Record real prompt/completion token counts for one AI call batch.

        Sourced from AI_COMPLETE's ``usage`` block, surfaced by injecting
        ``show_details=>TRUE`` into the inline-eval SQL.  Coexists with
        :meth:`add_chars` (char-based proxy used by legacy cost rendering)
        so old reports keep working while new reports can use real tokens.

        Guards against ``None`` / non-int inputs: per
        ``_parse_throughput_response`` (run_benchmark_sproc.py lines 460-494),
        ``usage`` field names vary by provider, so callers may pass through
        whatever the JSON path returned.
        """
        if not model or not kind:
            return
        try:
            pt = int(prompt_tokens) if prompt_tokens is not None else 0
        except (TypeError, ValueError):
            pt = 0
        try:
            ct = int(completion_tokens) if completion_tokens is not None else 0
        except (TypeError, ValueError):
            ct = 0
        if pt == 0 and ct == 0:
            # Nothing useful to record (failed rows have null usage); avoid
            # bloating the bucket with no-op entries.
            return
        with self._lock:
            key = (model, kind)
            bucket = self.token_usage.get(key)
            if bucket is None:
                bucket = {"prompt_tokens": 0, "completion_tokens": 0}
                self.token_usage[key] = bucket
            bucket["prompt_tokens"] += max(0, pt)
            bucket["completion_tokens"] += max(0, ct)

    @property
    def token_usage_snapshot(self) -> dict[tuple[str, str], dict[str, int]]:
        """Return a deep-ish copy of ``token_usage`` for cross-thread reads."""
        with self._lock:
            return {k: dict(v) for k, v in self.token_usage.items()}

    @property
    def total_udf_prompt_tokens(self) -> int:
        """Sum of prompt tokens across all UDF (candidate-eval) AI calls.

        Reads only the ``("udf", *)`` entries of ``token_usage`` — reflection
        LLM tokens are excluded so the reported number matches the
        candidate's per-batch cost.  Returns 0 in pre-inline-eval runs (or
        for candidates where AI_COMPLETE lacks a usage block).
        """
        with self._lock:
            return sum(
                v.get("prompt_tokens", 0)
                for (_, kind), v in self.token_usage.items()
                if kind == "udf"
            )

    @property
    def total_udf_completion_tokens(self) -> int:
        """Sum of completion tokens across all UDF AI calls."""
        with self._lock:
            return sum(
                v.get("completion_tokens", 0)
                for (_, kind), v in self.token_usage.items()
                if kind == "udf"
            )

    @property
    def total_reflection_prompt_tokens_est(self) -> int:
        """Char-based estimate of reflection prompt tokens (input_chars // 4).

        Reflection AI_COMPLETE calls run with ``show_details=False`` today,
        so we fall back to a chars/4 proxy (the same 4-chars-per-token
        rule of thumb used by ``_estimate_iter_credits`` in the
        experiment writer).  Roughly ~10–20% off the true prompt-token
        count for English text, but consistent across runs so it works
        well for the cost-quality Pareto plot's RELATIVE ranking and
        for the per-iteration token breakdown surfaced by the new
        token Gantt chart.

        ``("reflection", *)`` is the relevant subset of ``char_usage``
        — the UDF (eval) bucket is excluded because UDF calls already
        have real token counts via ``total_udf_prompt_tokens``.
        """
        with self._lock:
            return (
                sum(
                    v.get("input_chars", 0)
                    for (_, kind), v in self.char_usage.items()
                    if kind == "reflection"
                )
                // 4
            )

    @property
    def total_reflection_completion_tokens_est(self) -> int:
        """Char-based estimate of reflection completion tokens.

        Mirrors :attr:`total_reflection_prompt_tokens_est` for output
        chars.  Same caveat (chars/4 ~ 10–20% off real token counts;
        adequate for relative comparison and report rendering).
        """
        with self._lock:
            return (
                sum(
                    v.get("output_chars", 0)
                    for (_, kind), v in self.char_usage.items()
                    if kind == "reflection"
                )
                // 4
            )

    def add_phase(
        self,
        op_type: str,
        start_perf: float,
        end_perf: float,
        label: str = "",
        *,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        input_chars: int | None = None,
        output_chars: int | None = None,
        model: str | None = None,
        token_source: str | None = None,
    ) -> None:
        """Record a high-level phase event.

        Unlike the per-call add_* methods, phase events do NOT bump any
        operation counter — they exist purely to explain large blocks
        of wall-time on the Gantt timeline (e.g. ``setup``, ``gepa_loop``,
        ``test_eval``, ``save``).  Use ``time.perf_counter()`` for the
        ``start_perf`` / ``end_perf`` arguments so the resulting
        timeline aligns with the per-call events recorded by other
        wrappers.

        Optional token parameters (added 2026-06) allow phase events to
        carry per-call token info so the token-consumption Gantt can
        render them (e.g. ``cocoevolve_propose`` carrying char-est tokens).
        """
        with self._lock:
            self._push_event(
                op_type,
                start_perf,
                end_perf,
                label=label,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                input_chars=input_chars,
                output_chars=output_chars,
                model=model,
                token_source=token_source,
            )

    def export_events(self) -> list[dict]:
        """Return a copy of all recorded events in chronological order.

        Each event is ``{type, start_ms, end_ms, thread_id, label}``
        with ``start_ms`` / ``end_ms`` being absolute epoch milliseconds.
        Phase events, important fine-grained events (reflection, udf_*,
        experiment, artifact), and metric events are merged and sorted by
        ``start_ms`` so consumers see one chronologically-ordered stream.

        Callers (the optimize SPROC handler) bundle this list into
        ``model_output["timeline_events"]`` so the benchmark SPROC can
        store it and the CLI report can render the per-thread timeline.
        """
        with self._lock:
            merged = list(self._phase_events)
            merged.extend(self._important_fine_events)
            merged.extend(self._metric_events)
        merged.sort(key=lambda e: e["start_ms"])
        return merged

    def mark_iteration(self) -> None:
        """Snapshot current call counts as an iteration boundary."""
        now = time.perf_counter()
        with self._lock:
            self._metric_iter_boundaries.append(len(self.metric_durations))
            self._reflection_iter_boundaries.append(len(self.reflection_durations))
            self._udf_compile_iter_boundaries.append(len(self.udf_compile_durations))
            self._udf_exec_iter_boundaries.append(len(self.udf_exec_durations))
            self._experiment_iter_boundaries.append(len(self.experiment_durations))
            self._artifact_iter_boundaries.append(len(self.artifact_durations))
            self._iter_wall_times.append(now - self._last_iter_start)
            self._last_iter_start = now

    def reset_iteration_clock(self) -> None:
        """Re-anchor the per-iteration wall-clock to the current time.

        Use this to *exclude* a one-time setup phase (e.g. CocoEvolve's
        ``_build_similarity_matrix``, which runs synchronously on the
        per-model worker thread BEFORE the parallel iteration loop
        starts and routinely takes 60-80s for a 200-row valset) from
        the next ``mark_iteration`` call's ``iter_seconds``.

        Without this reset, the wall time between two consecutive
        ``mark_iteration`` calls is attributed in full to the second
        boundary's iteration window — even though most of that time
        was spent on infrastructure setup that the iteration didn't
        cause.  Concretely for evolve mode, ITER_1's iter_seconds
        reported 80+ seconds (almost all of which was matrix build),
        making the iteration look pathologically slow on the report's
        per-iteration table; ITER_2..ITER_N then read 3-8s as expected.
        Calling ``reset_iteration_clock`` once after the matrix is
        cached re-anchors the delta clock so ITER_1 shows the true
        iteration cost (~5s) and the matrix-build time appears only
        in its own ``cocoevolve_similarity_matrix`` phase event.

        This method does NOT modify any previously-recorded events,
        durations, or boundaries — it only changes the reference
        timestamp for the *next* ``mark_iteration``.  Safe to call
        from any thread; lock-protected to match the rest of the
        public API.
        """
        with self._lock:
            self._last_iter_start = time.perf_counter()

    @property
    def total_metric_calls(self) -> int:
        return len(self.metric_durations)

    @property
    def total_reflection_calls(self) -> int:
        return len(self.reflection_durations)

    @property
    def total_metric_seconds(self) -> float:
        return float(sum(self.metric_durations))

    @property
    def total_reflection_seconds(self) -> float:
        return float(sum(self.reflection_durations))

    @property
    def total_udf_compile_calls(self) -> int:
        return len(self.udf_compile_durations)

    @property
    def total_udf_exec_calls(self) -> int:
        return len(self.udf_exec_durations)

    @property
    def total_udf_compile_seconds(self) -> float:
        return float(sum(self.udf_compile_durations))

    @property
    def total_udf_exec_seconds(self) -> float:
        return float(sum(self.udf_exec_durations))

    @property
    def total_experiment_calls(self) -> int:
        return len(self.experiment_durations)

    @property
    def total_experiment_seconds(self) -> float:
        return float(sum(self.experiment_durations))

    @property
    def total_artifact_calls(self) -> int:
        return len(self.artifact_durations)

    @property
    def total_artifact_seconds(self) -> float:
        return float(sum(self.artifact_durations))

    def snapshot(self) -> TrackerSnapshot:
        """Capture the current totals as an immutable snapshot for delta computation."""
        return TrackerSnapshot(
            metric_calls=self.total_metric_calls,
            metric_seconds=self.total_metric_seconds,
            udf_compile_calls=self.total_udf_compile_calls,
            udf_compile_seconds=self.total_udf_compile_seconds,
            udf_exec_calls=self.total_udf_exec_calls,
            udf_exec_seconds=self.total_udf_exec_seconds,
            reflection_calls=self.total_reflection_calls,
            reflection_seconds=self.total_reflection_seconds,
            udf_prompt_tokens=self.total_udf_prompt_tokens,
            udf_completion_tokens=self.total_udf_completion_tokens,
        )

    def per_iteration_stats(self) -> list[IterationStats]:
        """Return per-iteration timing/count snapshots.

        Iteration ``i`` covers calls between boundaries ``i`` and ``i+1``.
        """
        with self._lock:
            metric_bounds = list(self._metric_iter_boundaries)
            reflection_bounds = list(self._reflection_iter_boundaries)
            udf_compile_bounds = list(self._udf_compile_iter_boundaries)
            udf_exec_bounds = list(self._udf_exec_iter_boundaries)
            experiment_bounds = list(self._experiment_iter_boundaries)
            artifact_bounds = list(self._artifact_iter_boundaries)
            wall_times = list(self._iter_wall_times)
            metric_durs = list(self.metric_durations)
            reflection_durs = list(self.reflection_durations)
            udf_compile_durs = list(self.udf_compile_durations)
            udf_exec_durs = list(self.udf_exec_durations)
            experiment_durs = list(self.experiment_durations)
            artifact_durs = list(self.artifact_durations)
            udf_exec_tokens = list(self.udf_exec_tokens)
            reflection_tokens = list(self.reflection_tokens)

        results: list[IterationStats] = []
        n = (
            min(
                len(metric_bounds),
                len(reflection_bounds),
                len(udf_compile_bounds),
                len(udf_exec_bounds),
                len(experiment_bounds),
                len(artifact_bounds),
                len(wall_times) + 1,
            )
            - 1
        )
        for i in range(max(0, n)):
            m_start, m_end = metric_bounds[i], metric_bounds[i + 1]
            r_start, r_end = reflection_bounds[i], reflection_bounds[i + 1]
            uc_start, uc_end = udf_compile_bounds[i], udf_compile_bounds[i + 1]
            ue_start, ue_end = udf_exec_bounds[i], udf_exec_bounds[i + 1]
            ex_start, ex_end = experiment_bounds[i], experiment_bounds[i + 1]
            ar_start, ar_end = artifact_bounds[i], artifact_bounds[i + 1]
            m_window = metric_durs[m_start:m_end]
            r_window = reflection_durs[r_start:r_end]
            uc_window = udf_compile_durs[uc_start:uc_end]
            ue_window = udf_exec_durs[ue_start:ue_end]
            ex_window = experiment_durs[ex_start:ex_end]
            ar_window = artifact_durs[ar_start:ar_end]
            # Per-iteration token windows.  ``udf_exec_tokens`` aligns
            # 1:1 with ``udf_exec_durations`` (one entry per add_udf_exec
            # call), so the same boundary slices apply.  Same story
            # for reflection.  When the lists are shorter than expected
            # (older trackers without per-call token recording), the
            # slice silently truncates and the iteration reports zero
            # tokens — preserving back-compat with old runs.
            ue_tok_window = udf_exec_tokens[ue_start:ue_end]
            r_tok_window = reflection_tokens[r_start:r_end]
            m_total = float(sum(m_window))
            r_total = float(sum(r_window))
            uc_total = float(sum(uc_window))
            ue_total = float(sum(ue_window))
            ex_total = float(sum(ex_window))
            ar_total = float(sum(ar_window))
            m_count = len(m_window)
            r_count = len(r_window)
            m_avg = (m_total / m_count) if m_count else 0.0
            r_avg = (r_total / r_count) if r_count else 0.0
            m_p95 = _percentile(m_window, 0.95)
            udf_pt = sum(p for p, _ in ue_tok_window)
            udf_ct = sum(c for _, c in ue_tok_window)
            ref_pt_est = sum(p for p, _ in r_tok_window)
            ref_ct_est = sum(c for _, c in r_tok_window)
            results.append(
                IterationStats(
                    iter_index=i,
                    iter_seconds=float(wall_times[i]),
                    metric_call_count=m_count,
                    # 6 decimals so sub-millisecond values (typical for
                    # local-Python metrics like exact_match scoring 100+
                    # rows in a few hundred microseconds) survive
                    # serialisation.  4 decimals lost everything below
                    # 50µs to literal-zero rounding.
                    metric_seconds_total=round(m_total, 6),
                    metric_seconds_avg=round(m_avg, 6),
                    metric_seconds_p95=round(m_p95, 6),
                    reflection_call_count=r_count,
                    reflection_seconds_total=round(r_total, 6),
                    reflection_seconds_avg=round(r_avg, 6),
                    udf_compile_count=len(uc_window),
                    udf_compile_seconds_total=round(uc_total, 4),
                    udf_exec_count=len(ue_window),
                    udf_exec_seconds_total=round(ue_total, 4),
                    experiment_count=len(ex_window),
                    experiment_seconds_total=round(ex_total, 4),
                    artifact_count=len(ar_window),
                    artifact_seconds_total=round(ar_total, 4),
                    udf_prompt_tokens=int(udf_pt),
                    udf_completion_tokens=int(udf_ct),
                    reflection_prompt_tokens_est=int(ref_pt_est),
                    reflection_completion_tokens_est=int(ref_ct_est),
                )
            )
        return results
