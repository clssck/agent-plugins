# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Function body optimization for Snowflake AI functions using GEPA optimize_anything.

This module provides ``run_body_optimization``, the default optimization
path that optimizes the **entire SQL function body** (not just the system
prompt).  It is invoked from ``run_optimization`` in ``snow_gepa_optimize``
when ``optimize_mode="body"`` (the default).

The candidate in this mode is a raw SQL body string.  The reflection LLM
is free to change model references, add SQL post-processing, restructure
the pipeline, etc. -- anything that produces valid Snowflake SQL with at
least one ``AI_COMPLETE`` call while preserving the function signature.

GEPA's ``OptimizeAnythingAdapter`` is replaced during ``run_body_optimization``
so each ``evaluate(batch, candidate)`` call performs **one** Snowpark
``collect()`` for the whole batch (after optional per-row adapter-cache hits).
The per-example ``make_body_evaluator`` closure remains for direct / unit tests.
"""

import contextlib
import dataclasses
import json
import logging
import os
import re
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Literal, cast

from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, parse_json
from snowflake.snowpark.types import (
    BooleanType,
    DataType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

import gepa.optimize_anything as _oa_module
from gepa.adapters.optimize_anything_adapter import optimize_anything_adapter
from gepa.adapters.optimize_anything_adapter.optimize_anything_adapter import (
    OptimizeAnythingAdapter,
)
from gepa.core.adapter import EvaluationBatch
from gepa.optimize_anything import (
    EngineConfig,
    GEPAConfig,
    MergeConfig,
    ReflectionConfig,
    TrackingConfig,
    _build_reflection_prompt_template,
    log,
    optimize_anything,
)
from snowflake_ai_optimize.core.ddl_rewrite import (
    ai_complete_returns_structured,
    inject_return_error_details,
    inject_show_details,
    semi_structured_param_names,
)
from snowflake_ai_optimize.core.evaluation import build_eval_detail_record, evaluate
from snowflake_ai_optimize.core.experiment import (
    FrontierCandidate,
    GlobalRunCounter,
    commit_runs,
    create_experiment,
    get_experiment_run_names,
    most_recent_running_run,
    seed_run_counter_from_experiment,
    select_frontier_candidates,
    set_run_error_message,
    stamp_frontier_metrics_on_runs,
)
from snowflake_ai_optimize.core.metrics.dispatch import (
    compute_metric,
    compute_metric_batch,
)
from snowflake_ai_optimize.core.metrics.utils import (
    get_table_column_names,
    parse_metric_options,
    resolve_expected_column,
    to_text,
    validate_input_columns,
)
from snowflake_ai_optimize.core.scorer import Evaluator
from snowflake_ai_optimize.core.sql_utils import (
    FunctionDefinition,
    build_query_text_function_def,
    build_temp_function_name,
    describe_function,
)
from snowflake_ai_optimize.core.stage import (
    extract_to_file_refs,
    file_type_param_names,
    validate_stage_file_access,
)
from snowflake_ai_optimize.core.timing import (
    TimingTracker,
    get_active_tracker,
    set_active_tracker,
)
from snowflake_ai_optimize.core.types import SnowflakeDataInst
from snowflake_ai_optimize.gepa.adapter import (
    _EVAL_DETAIL_MAX_LENGTH,
    SnowflakeLLM,
    _CapturedEval,
    candidate_detail_key,
    label_reflection_model,
    load_dataset,
    resolve_reflection_lm,
)
from snowflake_ai_optimize.gepa.engine_registry import resolve_engine
from snowflake_ai_optimize.gepa.experiment import (
    ProgressiveExperimentTracker,
    RejectedCandidateCollector,
    backfill_model_metrics,
    build_per_model_stats,
    compute_pareto_candidates,
    sum_seed_totals,
    upload_winning_artifacts,
    write_consolidated_seed,
)
from snowflake_ai_optimize.gepa.optimize import (
    MaxTotalBudgetStopper,
    PythonLoggingAdapter,
    split_dataset,
)

logger = logging.getLogger(__name__)


BudgetType = Literal["ultra-light", "light", "medium", "heavy", "demo"]
# Engine names are resolved dynamically via the engine registry.
# "default" is always available; research engines are registered by
# importing dev/engines/register_all.py (done by the benchmark framework).
EngineType = str

DEFAULT_REFLECTION_MINIBATCH_SIZE = 10
DEFAULT_PERFECT_SCORE = 1.0
DEFAULT_AUTO_BUDGET: BudgetType = "light"
DEFAULT_VALIDATION_FRACTION = 0.5
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192

# Number of cross-model hypervolume frontier candidates written as
# FRONTIER_CANDIDATE runs (and test-evaluated when a test table is provided).
DEFAULT_MAX_FRONTIER_CANDIDATES = 7

# Batched adapter uses one Snowflake round-trip per GEPA evaluate call;
# engine-level parallel eval is disabled (redundant with inline SQL).
DEFAULT_ENGINE_PARALLEL = False

# Identical (candidate, example) pairs reuse scores (e.g. repeated val passes).
DEFAULT_CACHE_EVALUATIONS = True
DEFAULT_MAX_MERGE_INVOCATIONS = 5
DEFAULT_MAX_PARALLELISM = 4

# Reflection AI_COMPLETE attempts before a failure is treated as fatal (only
# when ``fail_on_reflection_error`` is set — the spec-driven EXECUTE EXPERIMENT
# path).
REFLECTION_MAX_ATTEMPTS = 3
DEFAULT_MAX_CONCURRENCY = 8

_STR_CANDIDATE_KEY = "current_candidate"


@dataclass
class ModelOptimizationResult:
    """Result of a single-model body optimization run."""

    model: str
    status: Literal["completed", "failed"]
    elapsed_seconds: float
    error: str | None = None
    best_prompt: str | None = None
    best_score: float | None = None
    best_val_score: float | None = None
    seed_score: float | None = None
    seed_val_score: float | None = None
    score_source: str | None = None
    best_test_score: float | None = None
    seed_test_score: float | None = None
    num_test_examples: int | None = None
    avg_output_chars: int | None = None
    total_candidates: int | None = None
    total_metric_calls: int | None = None
    total_metric_seconds: float | None = None
    total_reflection_calls: int | None = None
    total_reflection_seconds: float | None = None
    total_udf_compile_calls: int | None = None
    total_udf_compile_seconds: float | None = None
    total_udf_exec_calls: int | None = None
    total_udf_exec_seconds: float | None = None
    total_udf_prompt_tokens: int | None = None
    total_udf_completion_tokens: int | None = None
    total_reflection_prompt_tokens_est: int | None = None
    total_reflection_completion_tokens_est: int | None = None
    total_experiment_calls: int | None = None
    total_experiment_seconds: float | None = None
    total_artifact_calls: int | None = None
    total_artifact_seconds: float | None = None
    all_val_scores: list[float] | None = None
    reflection_model: str | None = None
    reflection_backend: str | None = None
    pareto_candidates: list | None = None
    # Schema-v4 consolidated-SEED plumbing (set only when experiment_name):
    # the winning model's run_dir + seed eval detail feed the post-join
    # artifact upload, and per-model totals feed the SEED ``per_model_stats``.
    run_dir: str | None = None
    seed_eval_details: list | None = None
    # SEED/ITER run names whose commit was deferred so the cross-model
    # frontier test-eval can stamp test_score / is_frontier onto the
    # selected ones before they are committed.
    pending_commit_runs: list | None = None
    timeline_events: list | None = None
    test_eval_metric_calls: int | None = None
    test_eval_metric_seconds: float | None = None
    test_eval_reflection_calls: int | None = None
    test_eval_reflection_seconds: float | None = None
    test_eval_udf_compile_calls: int | None = None
    test_eval_udf_compile_seconds: float | None = None
    test_eval_udf_exec_calls: int | None = None
    test_eval_udf_exec_seconds: float | None = None
    test_eval_udf_prompt_tokens: int | None = None
    test_eval_udf_completion_tokens: int | None = None


@dataclass
class BodyOptConfig:
    """Validated configuration for a body optimization run."""

    function_def: FunctionDefinition
    seed_body: str
    function_signature: str
    function_name: str
    input_col_names: list[str]
    input_columns: list
    input_arg_names: list[str] | None
    models: list[str]
    reflection_model: str
    metric_name: str
    gepa_metric_opts: dict
    training_table: str
    test_table: str | None
    label_column: str
    validation_fraction: float
    temperature: float
    max_tokens: int
    auto_budget: BudgetType
    custom_metric_udf: str | None
    aggregation_metric: str | None
    experiment_name: str | None
    engine: EngineType
    max_concurrency: int
    reflection_backend: Literal["ai_complete", "agent_run", "agent_run_single_session"]
    run_id: str
    run_dir: str | None
    dataset_expected_columns: list[str] | None
    max_frontier_candidates: int
    # When False, the GEPA run_dir status/state artifacts are not uploaded to
    # the experiment stage (set by the spec-driven / YAML handler path).
    upload_run_dir: bool = True
    # When False the experiment is NOT created here — it must already exist and
    # runs are only attached to it. Set by the spec-driven / EXECUTE EXPERIMENT
    # path (the DDL layer creates the experiment before the SPROC runs); the
    # standalone OPTIMIZE_AI_FUNCTION path leaves it True to auto-create.
    create_experiment_if_missing: bool = True
    # Set only by the spec-driven / EXECUTE EXPERIMENT path (see
    # ``run_body_optimization`` docstring). Default False keeps standalone
    # OPTIMIZE_AI_FUNCTION behavior unchanged.
    fail_on_reflection_error: bool = False


@dataclass
class BodyBatchEvalContext:
    """Holds Snowflake + metric state for batched adapter evaluation.

    After the inline-eval migration ``compile_lock``/``compiled_body``/
    ``compile_error`` are no longer needed (each batch is independent and
    issues its own inline SELECT instead of sharing a compiled temp UDF).
    """

    session: Session
    function_def: FunctionDefinition
    temp_function_name: str
    input_columns: list[str]
    metric_evaluator: Evaluator
    pin_model: str | None = None
    # Full valset size, so the adapter can flag minibatch (subsample) evals; and
    # the shared per-candidate eval-detail buffer the tracker drains into
    # ``eval_detail.json``. Both default-empty so non-experiment runs
    # and existing callers are unaffected.
    full_valset_size: int | None = None
    eval_detail_buffer: dict = field(default_factory=dict)


oa_thread_local = threading.local()


# ---------------------------------------------------------------------------
# Thread-local GEPA-callbacks shim — body-mode rejected-candidate hook
# ---------------------------------------------------------------------------
#
# NOTE: ``gepa.optimize_anything()`` doesn't expose ``callbacks=`` on the
# GEPAEngine or ReflectiveMutationProposer it constructs internally. We
# need callbacks so RejectedCandidateCollector can persist rejected proposals
# to Snowflake Experiments. Both classes must be patched:
#   - GEPAEngine: fires accept/reject events (scores, reason)
#   - ReflectiveMutationProposer: fires events with candidate content
#
# Implementation: lazy monkey-patches both __init__ methods to merge
# thread-local callbacks. Patches are idempotent and no-op when TLS is
# empty, so unrelated GEPA usage is unaffected. The context manager
# _gepa_engine_callbacks() scopes callbacks to a single thread/block.

_engine_callbacks_tls = threading.local()
_real_engine_init = None  # populated by _ensure_engine_init_patch_installed
_real_reflective_init = None  # ditto for ReflectiveMutationProposer
_engine_init_patch_lock = threading.Lock()


def _ensure_engine_init_patch_installed() -> None:
    """Install GEPAEngine + ReflectiveMutationProposer __init__ wrappers.

    Idempotent and thread-safe (double-checked lock). Both patches merge
    thread-local callbacks into the constructor's kwargs; no-op when TLS
    is empty.
    """
    global _real_engine_init, _real_reflective_init
    if _real_engine_init is not None and _real_reflective_init is not None:
        return
    with _engine_init_patch_lock:
        if _real_engine_init is not None and _real_reflective_init is not None:
            return

        if _real_engine_init is None:
            from gepa.core.engine import GEPAEngine

            engine_real_init = GEPAEngine.__init__

            def _patched_engine(self: Any, *args: Any, **kwargs: Any) -> None:
                extra = getattr(_engine_callbacks_tls, "callbacks", None) or []
                if extra:
                    existing = list(kwargs.get("callbacks") or [])
                    kwargs["callbacks"] = existing + list(extra)
                return engine_real_init(self, *args, **kwargs)

            GEPAEngine.__init__ = _patched_engine  # type: ignore[method-assign]
            _real_engine_init = engine_real_init

        if _real_reflective_init is None:
            from gepa.proposer.reflective_mutation.reflective_mutation import (
                ReflectiveMutationProposer,
            )

            reflective_real_init = ReflectiveMutationProposer.__init__

            def _patched_reflective(self: Any, *args: Any, **kwargs: Any) -> None:
                extra = getattr(_engine_callbacks_tls, "callbacks", None) or []
                if extra:
                    existing = list(kwargs.get("callbacks") or [])
                    kwargs["callbacks"] = existing + list(extra)
                return reflective_real_init(self, *args, **kwargs)

            ReflectiveMutationProposer.__init__ = _patched_reflective  # type: ignore[method-assign]
            _real_reflective_init = reflective_real_init


@contextlib.contextmanager
def _gepa_engine_callbacks(callbacks: list | None) -> Iterator[None]:
    """Inject GEPA lifecycle callbacks into optimize_anything's engine + proposer.

    Scopes callbacks to the current thread via TLS. Passing None is a no-op.

    Example::

        with _gepa_engine_callbacks([rejected_collector]):
            result = optimize_anything(...)
    """
    _ensure_engine_init_patch_installed()
    prev = getattr(_engine_callbacks_tls, "callbacks", None)
    _engine_callbacks_tls.callbacks = callbacks or None
    try:
        yield
    finally:
        _engine_callbacks_tls.callbacks = prev


def _unwrap_str_candidate(candidate: dict[str, str]) -> str:
    body = candidate.get(_STR_CANDIDATE_KEY)
    if body is not None:
        return str(body)
    if candidate:
        return str(next(iter(candidate.values())))
    return ""


def truncate_for_feedback(value: object, limit: int = 500) -> str:
    """Render a candidate for reflection feedback without risking a second error.

    Every caller is inside an ``except`` handler that is already reporting a
    failure, so raising here replaces the real error with a bogus one and the
    original is lost.

    A candidate is normally the SQL body string, but a ``dict`` reaches these
    paths too -- this module anticipates it elsewhere (``if isinstance(best_body,
    dict)``). Slicing a dict raises ``KeyError``, whose ``str()`` is exactly
    ``slice(None, 500, None)``; that is how a server-side Snowpark type-mapping
    failure (``252011: Python data type [dict] cannot be automatically mapped``)
    came to be recorded as ``slice(None, 500, None)`` and stayed undiagnosed.

    Args:
        value: Candidate body, of any type.
        limit: Maximum characters to keep.

    Returns:
        A string of at most ``limit`` characters. Never raises.
    """
    if isinstance(value, str):
        return value[:limit]
    try:
        text = json.dumps(value, default=str)
    except Exception:
        text = repr(value)
    return text[:limit]


def _put_adapter_eval_cache(
    adapter: OptimizeAnythingAdapter,
    candidate: dict[str, str],
    example: object,
    result: tuple[float, Any, dict],
) -> None:
    if adapter.cache_mode == "off":
        return
    cache_key = adapter._cache_key(candidate, example)
    with adapter._eval_cache_lock:
        adapter._eval_cache[cache_key] = result
        if adapter.cache_mode == "disk":
            adapter._save_cache_entry(cache_key, result)


class _BatchedBodyOptimizeAnythingAdapter(OptimizeAnythingAdapter):
    """Runs the temp UDF once per ``evaluate()`` batch (one ``collect()``)."""

    def evaluate(
        self,
        batch: list,
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch:
        ctx = getattr(oa_thread_local, "body_batch_ctx", None)
        if ctx is None or self.refiner_config is not None or len(batch) == 0:
            return super().evaluate(batch, candidate, capture_traces=capture_traces)

        raw_results = self._sql_body_batched_raw_results(batch, candidate, ctx)
        eval_output: list = []
        for score, _, side_info in raw_results:
            out = (score, candidate, side_info)
            eval_output.append((score, out, side_info))
        for example, (score, _, side_info) in zip(batch, eval_output, strict=True):
            self._update_best_example_evals(example, score, side_info)

        scores = [score for score, _, _ in eval_output]
        side_infos = [info for _, _, info in eval_output]
        outputs = [out for _, out, _ in eval_output]
        objective_scores: list[dict[str, float]] = []
        for side_info in side_infos:
            objective_score: dict[str, float] = {}
            if "scores" in side_info:
                objective_score.update(side_info["scores"])
            for param_name in candidate:
                key = param_name + "_specific_info"
                if key in side_info and "scores" in side_info[key]:
                    objective_score.update(
                        {
                            f"{param_name}::{k}": v
                            for k, v in side_info[key]["scores"].items()
                        }
                    )
            objective_scores.append(objective_score)

        # Capture per-row detail for this candidate from data GEPA already
        # computed (no extra eval) so the tracker can persist
        # ``eval_detail.json``. A batch smaller than the full valset
        # (a rejected proposal's minibatch gate) is flagged subsample.
        subsample = (
            ctx.full_valset_size is not None and len(batch) < ctx.full_valset_size
        )
        split_tag = "val_subsample" if subsample else "val_full"
        metric_name = getattr(ctx.metric_evaluator, "metric_name", "")
        detail_records = [
            build_eval_detail_record(
                row_id=row_id,
                input_text="\n".join(f"{k}: {v}" for k, v in example["inputs"].items()),
                expected=example["answer"],
                predicted=str(side_info.get("Output", "")),
                metric_score=score,
                metric_feedback=str(side_info.get("Feedback", "")),
                metric_name=metric_name,
                model_name=ctx.pin_model or "",
                split=split_tag,
                error_message=str(side_info.get("Error", "")),
                max_length=_EVAL_DETAIL_MAX_LENGTH,
            )
            for row_id, (example, score, side_info) in enumerate(
                zip(batch, scores, side_infos, strict=True)
            )
        ]
        ctx.eval_detail_buffer[
            candidate_detail_key(_unwrap_str_candidate(candidate))
        ] = _CapturedEval(records=detail_records, subsample=subsample)

        return EvaluationBatch(
            outputs=outputs,
            scores=scores,
            trajectories=side_infos,
            objective_scores=objective_scores,
        )

    def _sql_body_batched_raw_results(
        self,
        batch: list,
        candidate: dict[str, str],
        ctx: BodyBatchEvalContext,
    ) -> list[tuple[float, Any, dict]]:
        body = _unwrap_str_candidate(candidate)
        if ctx.pin_model:
            body = _swap_model_in_body(body, ctx.pin_model)
        n = len(batch)
        raw: list[tuple[float, Any, dict] | None] = [None] * n

        need_indices: list[int] = []
        for i, example in enumerate(batch):
            if self.cache_mode != "off":
                ck = self._cache_key(candidate, example)
                with self._eval_cache_lock:
                    hit = self._eval_cache.get(ck)
                if hit is not None:
                    raw[i] = hit
                    continue
            need_indices.append(i)

        if need_indices:
            rows = [
                {c: batch[i]["inputs"].get(c, "") for c in ctx.input_columns}
                for i in need_indices
            ]
            try:
                # Inline-eval: skips CREATE TEMP FN entirely and runs a
                # single CTE-shaped SELECT against the batch with
                # show_details=>TRUE injected into AI_COMPLETE so the
                # response carries per-row token counts.  ``ctx.pin_model``
                # is the candidate model that the body bakes into its
                # AI_COMPLETE call; passing it lets the tracker bucket
                # char + token usage under the right model key.
                outs, _tokens = _evaluate_inline_body(
                    ctx.session,
                    ctx.function_def,
                    body,
                    rows,
                    udf_model=ctx.pin_model or "",
                )
            except Exception as e:
                # With inline SQL there's only ONE round-trip so both
                # compile-time (SQL syntax) and runtime errors arrive here.
                # We pattern-match the error message to preserve the GEPA
                # reflection feedback distinction today's adapter relies
                # on ("Fix the SQL syntax" vs "produced runtime error").
                err_msg = str(e)
                err_lc = err_msg.lower()
                is_compile_error = (
                    "sql compilation error" in err_lc
                    or "syntax error" in err_lc
                    or "syntactically invalid" in err_lc
                    or "invalid identifier" in err_lc
                )
                if is_compile_error:
                    log(f"Compilation failed: {e}")
                    for i in need_indices:
                        example = batch[i]
                        side_info = {
                            "Error": err_msg,
                            "Candidate (truncated)": truncate_for_feedback(body),
                            "Feedback": (
                                f"Function body failed SQL compilation: {err_msg}. "
                                "Fix the SQL syntax."
                            ),
                        }
                        triple = (0.0, None, side_info)
                        raw[i] = triple
                        _put_adapter_eval_cache(self, candidate, example, triple)
                else:
                    log(f"Runtime error (batch): {e}")
                    for i in need_indices:
                        example = batch[i]
                        side_info = {
                            "Error": err_msg,
                            "Candidate (truncated)": truncate_for_feedback(body),
                            "Feedback": (
                                f"Function body produced runtime error: {err_msg}."
                            ),
                        }
                        triple = (0.0, None, side_info)
                        raw[i] = triple
                        _put_adapter_eval_cache(self, candidate, example, triple)
            else:
                items = []
                responses = []
                for j, i in enumerate(need_indices):
                    # ``to_text`` (not ``str``) so a VARIANT array/object result
                    # reaches the metric as JSON, identical to the deployed-UDF
                    # (test) path's ``to_text`` serialization.  ``str(list)`` would
                    # emit a Python repr (``['a']``) that JSON-only metrics can't
                    # parse — silently zeroing the inline (val) score.
                    response = to_text(outs[j]) if j < len(outs) else ""
                    responses.append(response)
                    items.append((batch[i]["answer"], response))

                tracker = get_active_tracker()
                _t0 = time.perf_counter()
                try:
                    batch_results = compute_metric_batch(
                        ctx.metric_evaluator.metric_name,
                        items,
                        ctx.session,
                        ctx.metric_evaluator.custom_metric_udf,
                        **dict(ctx.metric_evaluator.kwargs),
                    )
                finally:
                    if tracker is not None and items:
                        # Record ONE timeline event covering the actual SQL
                        # window ``[_t0, now]``.  Calling ``add_metric``
                        # in a per-item loop pushed N events all stamped
                        # at the moment the batch returned, collapsing the
                        # whole batch into a microsecond-wide cluster on
                        # the Gantt chart (visible as 1k+ overlapping
                        # ``metric`` segments at the same start time on
                        # body-mode reports).  ``add_metric_batch`` still
                        # appends N copies of ``per_item`` to
                        # ``metric_durations`` so per-iteration totals,
                        # averages, and percentiles match what the
                        # per-item loop produced.
                        tracker.add_metric_batch(_t0, time.perf_counter(), len(items))

                for j, i in enumerate(need_indices):
                    example = batch[i]
                    quality_score, feedback = batch_results[j]
                    log(
                        f"Quality: {quality_score:.3f}, Feedback: {feedback}",
                    )
                    side_info = {
                        "Input": "\n".join(
                            f"{k}: {v}" for k, v in example["inputs"].items()
                        ),
                        "Output": responses[j],
                        "Expected": example["answer"],
                        "Feedback": feedback,
                    }
                    triple = (quality_score, None, side_info)
                    raw[i] = triple
                    _put_adapter_eval_cache(self, candidate, example, triple)

        unfilled = sum(1 for r in raw if r is None)
        if unfilled:
            raise RuntimeError(
                f"{unfilled} of {len(raw)} candidate evaluations were not "
                "populated; every slot must be filled before returning results"
            )
        return [r for r in raw if r is not None]


# ---------------------------------------------------------------------------
# DDL helpers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# AI_COMPLETE model-literal parsing
# ---------------------------------------------------------------------------
#
# Handles both calling forms:
#   Named:      AI_COMPLETE(model => 'mistral-large2', ...)
#   Positional: AI_COMPLETE('mistral-large2', ...)

_AI_COMPLETE_OPEN_RE = re.compile(r"\bAI_COMPLETE\s*\(", flags=re.IGNORECASE)
_NAMED_MODEL_RE = re.compile(r"model\s*=>\s*'([^']*)'", flags=re.IGNORECASE)
_POSITIONAL_MODEL_RE = re.compile(r"\s*'([^']*)'")


def _locate_model_literal(text: str) -> tuple[int, int, str] | None:
    """Locate the model-name string literal in a SQL fragment.

    Returns ``(start_idx, end_idx, model_name)`` indices into *text*
    pointing at the model name *without* its surrounding single quotes,
    or ``None`` when no AI_COMPLETE call is present.

    Assumes *text* contains at most one AI_COMPLETE call.  The named
    form (``model => 'name'``) is preferred when present so that calls
    like ``AI_COMPLETE(messages => ..., model => 'name')`` are handled
    correctly; otherwise the first positional string after the open
    parenthesis is treated as the model.
    """
    open_match = _AI_COMPLETE_OPEN_RE.search(text)
    if not open_match:
        return None
    args_start = open_match.end()

    named = _NAMED_MODEL_RE.search(text, pos=args_start)
    if named is not None:
        return named.start(1), named.end(1), named.group(1)

    positional = _POSITIONAL_MODEL_RE.match(text, pos=args_start)
    if positional is not None:
        return positional.start(1), positional.end(1), positional.group(1)

    return None


def _extract_model_from_body_ddl(ddl: str, function_name: str = "") -> str:
    """Extract the model name from a function body (or DDL) string.

    Supports both AI_COMPLETE calling forms (named ``model => '...'``
    and positional ``AI_COMPLETE('...', ...)``).  Operates directly on the
    text passed in — callers pass ``FunctionDefinition.body`` (the raw,
    un-escaped body from ``describe_function``).

    Deliberately uniquely-named (not ``extract_model_from_ddl_string``): in the
    inline-SPROC flat bundle every module's source is concatenated into ONE
    namespace, and the identically-named re-export in ``gepa/optimize.py`` (which
    lazily ``importlib.import_module``s ``optimize_prompt``) is concatenated last
    and would shadow this one — calling it inside the flat module raises
    ``ModuleNotFoundError: snowflake_ai_optimize``.  A unique name can't be
    shadowed, so the body path stays bundle-safe.
    """
    located = _locate_model_literal(ddl)
    if located is None:
        raise ValueError(
            f"Could not extract model name from DDL for function: {function_name}."
        )
    return located[2]


# Public API name for direct extraction (tests / external callers).  The
# body-mode optimization path deliberately calls ``_extract_model_from_body_ddl``
# by its unique name instead of this alias, to stay bundle-safe (see the def's
# docstring: the inline flat bundle would otherwise shadow this name with
# ``optimize.py``'s importlib-based re-export).
extract_model_from_ddl_string = _extract_model_from_body_ddl


# ---------------------------------------------------------------------------
# Objective / background construction
# ---------------------------------------------------------------------------


def build_objective_and_background(
    function_name: str,
    function_signature: str,
    original_body: str,
    model: str,
    metric_name: str,
) -> tuple[str, str]:
    """Build the objective and background strings for the reflection LLM."""
    objective = (
        f"Optimize the SQL function body of {function_name} to maximize quality "
        f"(measured by {metric_name}). "
        f"The function must maintain the same input/output contract."
    )

    background = dedent(
        f"""
        Function signature: {function_signature}

        Model: {model}

        Constraints:
        - The function body MUST call AI_COMPLETE at least once
        - The function MUST accept the same input parameters and return the same type
        - The model used in AI_COMPLETE should not be changed.
        - Valid Snowflake SQL syntax is required
        - Output the COMPLETE function body only, with no surrounding DDL
        - Preserve any result accessor suffix (e.g. :field_name::TYPE) at the end of the expression
        - Prefer to keep fixed instructions in the system message and put the per-row input expression last in the user message, with no static text after it. This keeps the cacheable prompt prefix stable across rows (lower cost) and does not change what the model is told.

        AI_COMPLETE correct syntax:
        AI_COMPLETE(
            model=>'model_name',
            messages=>ARRAY_CONSTRUCT(
                OBJECT_CONSTRUCT('role', 'system', 'content', '<system_prompt>'),
                OBJECT_CONSTRUCT('role', 'user', 'content', <input_expression>)
            ),
            response_format=>PARSE_JSON('<json_schema>')
        )

        Available SQL functions: CONCAT, REPLACE, REGEXP_REPLACE, SPLIT, ARRAY_AGG,
        PARSE_JSON, OBJECT_CONSTRUCT, TRY_PARSE_JSON, REDUCE, CASE, IFF, COALESCE, etc.

        Architecture — consider a TWO-STEP (extract-then-compose) body, not only
        prompt edits. Keep ONE AI_COMPLETE, but change its response_format to return
        structured facts, then compose the final answer with deterministic SQL. Two
        shapes that compile cleanly as a single scalar UDF body:
        - decision / routing: extract predicate fields, branch with CASE:
            ( SELECT CASE WHEN v:field::TYPE ... THEN ... ELSE ... END
              FROM ( SELECT TRY_PARSE_JSON(AI_COMPLETE(...)) AS v ) )
        - aggregate over an array the model returns: fold with REDUCE (a scalar):
            ( SELECT TO_CHAR(ROUND(REDUCE(TRY_PARSE_JSON(AI_COMPLETE(...)):items,
                0::FLOAT, (acc, r) -> acc + r:a::FLOAT * r:b::FLOAT), 2), 'FM999990.00') )
        Do NOT use LATERAL FLATTEN to aggregate: a SQL UDF is inlined into the calling
        query, so a LATERAL FLATTEN in the body becomes a correlated lateral over rows
        and fails to compile ("Unsupported subquery type ... inside Function object").
        Use REDUCE (a scalar fold) instead. Wrap the call in TRY_PARSE_JSON and return
        one parenthesized scalar expression. Offloading the rule/arithmetic to SQL
        often beats a prompt-only body; let the metric decide.

        Current implementation for reference:
        {original_body}
    """
    ).strip()
    return objective, background


def estimate_body_reflection_weight(
    seed_body: str,
    objective: str,
    background: str,
    trainset: list[SnowflakeDataInst],
    metric_name: str = "exact_match",
    reflection_minibatch_size: int = DEFAULT_REFLECTION_MINIBATCH_SIZE,
) -> int:
    """Estimate the relative cost of one reflection call vs one metric call.

    Similar to ``MaxTotalBudgetStopper.estimate_reflection_weight`` in
    ``snow_gepa_optimize`` but adapted for body-mode where the reflection
    prompt includes objective, background, and the full candidate body.

    The reflection prompt is built via GEPA's
    ``_build_reflection_prompt_template`` so the estimate matches the actual
    template used during optimization.
    """
    if not trainset:
        return 1

    avg_input_len = sum(
        sum(len(str(v)) for v in item["inputs"].values()) for item in trainset
    ) / len(trainset)

    metric_prompt_len = len(seed_body) + avg_input_len
    if metric_prompt_len == 0:
        return 1

    template = _build_reflection_prompt_template(
        objective=objective,
        background=background,
    )
    sample = trainset[:reflection_minibatch_size]
    side_info_sample = "\n".join(
        f"Input: {' '.join(str(v) for v in item['inputs'].values())} | "
        f"Expected: {item.get('answer', '')} | Feedback: Needs improvement."
        for item in sample
    )
    reflection_prompt_len = len(template) + len(seed_body) + len(side_info_sample)

    return max(1, round(reflection_prompt_len / metric_prompt_len))


# ---------------------------------------------------------------------------
# Body-based evaluator (inline SQL)
# ---------------------------------------------------------------------------
#
# Evaluates candidates via a single CTE-shaped SELECT (no CREATE TEMP FUNCTION).
# The candidate body's AI_COMPLETE call is extracted, augmented with
# show_details=>TRUE for token capture, and run in a __ai_call CTE.
# udf_compile_* counters report 0; udf_exec_* covers the inline SELECT.


# Column names for the inline-eval CTE (__ prefix avoids collision with
# user-defined parameter names).
_INLINE_DETAILS_COL = "__DETAILS"
_INLINE_RESULT_COL = "RESULT"
_INLINE_PROMPT_TOKENS_COL = "PROMPT_TOKENS"
_INLINE_COMPLETION_TOKENS_COL = "COMPLETION_TOKENS"


def _build_response_case_expr(value_col: str) -> str:
    """Build the CASE expression to extract the model output from AI_COMPLETE response.

    NOTE: Uses CASE (not COALESCE) because Snowflake eagerly evaluates all
    COALESCE arms — including a diagnostic ::NUMBER cast sentinel — which
    caused silent failures in structured-output mode. CASE short-circuits.

    Handles three AI_COMPLETE response shapes:
      - Default: choices[0]:messages
      - OpenAI-style: choices[0]:message:content
      - Structured (response_format set): structured_output[0]:raw_message
    """
    return (
        f"CASE "
        f"WHEN {value_col}:choices[0]:messages IS NOT NULL "
        f"THEN {value_col}:choices[0]:messages "
        f"WHEN {value_col}:choices[0]:message:content IS NOT NULL "
        f"THEN {value_col}:choices[0]:message:content "
        f"WHEN {value_col}:structured_output[0]:raw_message IS NOT NULL "
        f"THEN {value_col}:structured_output[0]:raw_message "
        f"WHEN {value_col}:usage IS NOT NULL "
        f"THEN TO_VARIANT(("
        f"'Inline-eval: AI_COMPLETE returned an unrecognized response shape; "
        f"top-level choices keys: ' || COALESCE("
        f"ARRAY_TO_STRING(OBJECT_KEYS({value_col}:choices[0]), ','), "
        f"'(no choices)'))::NUMBER) "
        f"ELSE NULL "
        f"END"
    )


def _build_result_expr(
    candidate_body: str,
    ai_start: int,
    ai_end: int,
    value_col: str,
) -> str:
    """Build the RESULT column expression with type-preserving substitution.

    Replaces the AI_COMPLETE span in the original body with a column reference
    that extracts the model output from the CTE's __DETAILS column. Casts to
    ::STRING in text mode to preserve the VARCHAR contract; leaves as VARIANT
    in structured mode.
    """
    case_expr = _build_response_case_expr(value_col)
    if ai_complete_returns_structured(candidate_body):
        output_path = case_expr
    else:
        output_path = f"({case_expr})::STRING"
    return candidate_body[:ai_start] + output_path + candidate_body[ai_end:]


def _build_error_envelope(result_expr: str) -> str:
    """Wrap a result expression with per-row error handling.

    When AI_COMPLETE fails for a row, surfaces the error as
    "INFERENCE_ERROR: <msg>" instead of silently producing NULL.
    """
    return (
        f"CASE WHEN {_INLINE_DETAILS_COL}:error IS NOT NULL "
        f"THEN 'INFERENCE_ERROR: ' || {_INLINE_DETAILS_COL}:error::STRING "
        f"ELSE ({result_expr}) END"
    )


def _is_query_body(candidate_body: str) -> bool:
    """Return True when *candidate_body* is a full SQL query, not an expression."""
    return bool(re.match(r"^\s*(WITH|SELECT)\b", candidate_body or "", re.IGNORECASE))


def _input_passthrough_projection(input_view_name: str, row_id_col: str) -> str:
    """Projection that keeps original input columns visible after __ai_call."""
    return f"inp.*, __ai_call.{_INLINE_DETAILS_COL}"


def _build_inline_eval_sql(
    candidate_body: str,
    input_view_name: str,
    row_id_col: str = "__ROW_ID",
) -> tuple[str, bool]:
    """Build the inline-eval CTE SQL for a body-mode candidate.

    Returns ``(sql, tokens_captured)``. The SQL is a CTE that:
      1. Runs AI_COMPLETE with show_details=>TRUE in a __ai_call CTE
      2. Extracts the result via _build_result_expr (handles 3 response shapes)
      3. Wraps with _build_error_envelope for per-row error surfacing
      4. Projects PROMPT_TOKENS / COMPLETION_TOKENS from the usage block

    ``tokens_captured`` is False when no AI_COMPLETE call exists in the body.
    """
    rewrite = inject_show_details(candidate_body)
    if rewrite is None:
        # No AI_COMPLETE call — run the body verbatim with 0 tokens.
        return (
            f"SELECT {row_id_col} AS {row_id_col}, "
            f"({candidate_body}) AS {_INLINE_RESULT_COL}, "
            f"0::INTEGER AS {_INLINE_PROMPT_TOKENS_COL}, "
            f"0::INTEGER AS {_INLINE_COMPLETION_TOKENS_COL} "
            f"FROM {input_view_name} ORDER BY {row_id_col}",
            False,
        )

    rewritten_body, (ai_start, ai_end) = rewrite

    # Also force ``return_error_details=>TRUE`` so per-row inference errors
    # surface as ``__DETAILS:error`` (caught by the outer CASE below)
    # instead of a NULL ``__DETAILS`` that the body's accessors would
    # silently strip to NULL — the same error-handling contract the
    # prompt-mode path gets via TempAIFunction._rewrite_ai_complete_for_error_details.
    # Per Snowflake's AI_COMPLETE contract this changes the per-row return
    # shape from a bare value to ``OBJECT(value, error)``, so the CTE's
    # accessors below traverse through ``:value:`` and the outer SELECT
    # checks ``:error`` first.
    error_rewrite = inject_return_error_details(rewritten_body)
    if error_rewrite is not None:
        rewritten_body, _ = error_rewrite

    # ``(ai_start, ai_end)`` refer to the AI_COMPLETE span in the ORIGINAL
    # *candidate_body* — the appropriate coords for substituting the call
    # site in the body's downstream logic with a column reference.  But the
    # AI_COMPLETE call in ``rewritten_body`` is LONGER (show_details=>TRUE
    # AND return_error_details=>TRUE were appended), so we need its NEW
    # span to extract for the CTE's __ai_call projection.
    from snowflake_ai_optimize.core.temp_ai_function import TempAIFunction

    rewritten_call = TempAIFunction._find_ai_complete_call(rewritten_body)
    if rewritten_call is None:
        # Defensive: should not happen because both injectors just placed
        # the call there.  Fall back to the original coords.
        ai_call_span = rewritten_body[ai_start:ai_end]
    else:
        _, rewritten_start, rewritten_end = rewritten_call
        ai_call_span = rewritten_body[rewritten_start:rewritten_end]

    # Substitute the AI_COMPLETE call span with a column reference and wrap
    # with error handling. The body's surrounding accessor / SQL operators
    # (TRIM, :fieldname::TYPE, etc.) continue to operate on the result.
    #
    # NOTE: _find_ai_complete_call matches only the FIRST AI_COMPLETE call.
    # Bodies with multiple calls will only have the first call's tokens
    # captured; subsequent calls run inline but are not surfaced in the
    # token columns. Rare in practice.
    value_col = f"{_INLINE_DETAILS_COL}:value"
    result_expr = _build_result_expr(candidate_body, ai_start, ai_end, value_col)
    error_envelope = _build_error_envelope(result_expr)

    query_body = _is_query_body(candidate_body)
    source_projection = _input_passthrough_projection(input_view_name, row_id_col)
    if query_body:
        result_sql = (
            f"WITH __ai_call AS (\n"
            f"    SELECT {row_id_col}, ({ai_call_span}) AS {_INLINE_DETAILS_COL}\n"
            f"    FROM {input_view_name}\n"
            f"),\n"
            f"__candidate_input AS (\n"
            f"    SELECT {source_projection}\n"
            f"    FROM {input_view_name} inp\n"
            f"    JOIN __ai_call USING ({row_id_col})\n"
            f"),\n"
            f"__candidate_result AS (\n"
            f"    SELECT {row_id_col}, ({result_expr}) AS {_INLINE_RESULT_COL}\n"
            f"    FROM __candidate_input\n"
            f")\n"
            f"SELECT __candidate_result.{row_id_col} AS {row_id_col},\n"
            f"       CASE WHEN __ai_call.{_INLINE_DETAILS_COL}:error IS NOT NULL "
            f"THEN 'INFERENCE_ERROR: ' || __ai_call.{_INLINE_DETAILS_COL}:error::STRING "
            f"ELSE __candidate_result.{_INLINE_RESULT_COL} END AS {_INLINE_RESULT_COL},\n"
            f"       __ai_call.{value_col}:usage:prompt_tokens::INTEGER "
            f"AS {_INLINE_PROMPT_TOKENS_COL},\n"
            f"       __ai_call.{value_col}:usage:completion_tokens::INTEGER "
            f"AS {_INLINE_COMPLETION_TOKENS_COL}\n"
            f"FROM __candidate_result\n"
            f"JOIN __ai_call USING ({row_id_col})\n"
            f"ORDER BY {row_id_col}"
        )
        return result_sql, True

    sql = (
        f"WITH __ai_call AS (\n"
        f"    SELECT {row_id_col}, ({ai_call_span}) AS {_INLINE_DETAILS_COL}\n"
        f"    FROM {input_view_name}\n"
        f"),\n"
        f"__candidate_input AS (\n"
        f"    SELECT {source_projection}\n"
        f"    FROM {input_view_name} inp\n"
        f"    JOIN __ai_call USING ({row_id_col})\n"
        f")\n"
        f"SELECT {row_id_col} AS {row_id_col},\n"
        f"       ({error_envelope}) AS {_INLINE_RESULT_COL},\n"
        f"       {value_col}:usage:prompt_tokens::INTEGER "
        f"AS {_INLINE_PROMPT_TOKENS_COL},\n"
        f"       {value_col}:usage:completion_tokens::INTEGER "
        f"AS {_INLINE_COMPLETION_TOKENS_COL}\n"
        f"FROM __candidate_input\n"
        f"ORDER BY {row_id_col}"
    )
    return sql, True


def _build_input_projection(
    rows: list[dict[str, object]],
    function_def: FunctionDefinition | None,
) -> tuple[list[dict[str, object]], list[str]]:
    """Normalize input rows for the inline-eval CTE.

    Returns ``(indexed_rows, all_cols)``:

    * ``indexed_rows`` has each input row tagged with ``__ROW_ID``; ARRAY /
      VARIANT / OBJECT param values that arrived as Python lists/dicts are
      ``json.dumps``-encoded so the Snowpark DataFrame column type stays
      uniformly VARCHAR (mixed-type inference would otherwise reject).
    * ``all_cols`` is the union of column names across rows (with
      ``__ROW_ID`` first), preserving insertion order for stable SELECT
      column lists.

    Caller is responsible for binding ``indexed_rows`` to a temp view and
    issuing a SELECT that wraps semi-structured columns with ``PARSE_JSON``
    so the body sees the correct VARIANT / ARRAY / OBJECT type.
    """
    if not rows:
        return [], ["__ROW_ID"]

    indexed_rows: list[dict[str, object]] = []
    for idx, row in enumerate(rows):
        r: dict[str, object] = {"__ROW_ID": idx}
        for k, v in row.items():
            # Sanity: no user-defined column should start with __ — those
            # identifiers are reserved for inline-eval bookkeeping
            # (__ROW_ID, __DETAILS, etc.).
            if k.startswith("__") and k != "__ROW_ID" and not k.startswith("__STAGE_"):
                raise ValueError(
                    f"Input column {k!r} starts with '__' which is reserved "
                    "for inline-eval bookkeeping (__ROW_ID, __DETAILS, ...). "
                    "Rename the column or escape it before passing to the "
                    "body-mode adapter."
                )
            # A list/dict can never map to a StringType column in
            # ``create_dataframe`` (mixed-type inference rejects it), so
            # re-encode ANY list/dict value to a JSON string for transport.
            # The inline-eval SELECT PARSE_JSONs declared semi-structured
            # params back to VARIANT; a plain VARCHAR param whose value is
            # serialized JSON (e.g. a table passed as a VARCHAR input) stays a
            # string for the body to PARSE_JSON itself.  ``adapter`` parses any
            # ``{``/``[`` string input into a Python object, so without this a
            # JSON-valued VARCHAR input reaches create_dataframe as a dict.
            if isinstance(v, list | tuple | dict):
                r[k] = json.dumps(v)
            else:
                r[k] = v
        indexed_rows.append(r)

    all_cols: list[str] = ["__ROW_ID"]
    seen = {"__ROW_ID"}
    for row in rows:
        for k in row:
            if k not in seen:
                seen.add(k)
                all_cols.append(k)

    return indexed_rows, all_cols


def _inline_input_schema(
    indexed_rows: list[dict[str, object]], all_cols: list[str]
) -> StructType:
    """Build an explicit Snowpark schema for the inline-eval input rows.

    ``session.create_dataframe(rows)`` without a schema lets Snowpark infer
    each column's type from the first row's Python value.  On Snowpark 1.52.0
    a ``str`` value is inferred as ``StringType(1)`` (``VARCHAR(1)``); saving
    the dataframe to the temp eval table then fails with a truncation error on
    any multi-character input, and that failure is swallowed at DEBUG and
    silently zeroes out every metric call.  Pin text columns to an unbounded
    ``StringType()`` and ``__ROW_ID`` to ``LongType`` so inputs of any length
    round-trip intact.
    """
    fields: list[StructField] = []
    for column in all_cols:
        field_type: DataType = StringType()
        for row in indexed_rows:
            value = row.get(column)
            if value is None:
                continue
            if isinstance(value, bool):
                field_type = BooleanType()
            elif isinstance(value, int):
                field_type = LongType()
            elif isinstance(value, float):
                field_type = DoubleType()
            else:
                field_type = StringType()
            break
        fields.append(StructField(column, field_type))
    return StructType(fields)


def _evaluate_inline_body(
    session: Session,
    function_def: FunctionDefinition | None,
    candidate_body: str,
    rows: list[dict[str, Any]],
    udf_model: str = "",
) -> tuple[list[object], list[tuple[int, int]]]:
    """Evaluate *candidate_body* against *rows* via inline SQL.

    Returns ``(results, [(prompt_tokens, completion_tokens), ...])`` aligned
    by ``__ROW_ID`` order.  Token tuples are ``(0, 0)`` when the AI_COMPLETE
    response lacks a usage block (e.g. provider-side variation) or when
    ``_inject_show_details`` could not inject the kwarg (e.g. 5+ positional
    args already provided in the candidate body).

    Records ``udf_exec`` duration on the active ``TimingTracker``.  When
    *udf_model* is supplied, records char-based token estimates under
    ``(udf_model, "udf")`` for back-compat with the existing cost-quality
    Pareto plot, AND real token counts via ``tracker.add_tokens(...)``.
    """
    if not rows:
        return [], []

    tracker = get_active_tracker()
    indexed_rows, all_cols = _build_input_projection(rows, function_def)
    structured_params = (
        semi_structured_param_names(function_def.args) if function_def else set()
    )

    schema = _inline_input_schema(indexed_rows, all_cols)
    df = session.create_dataframe(indexed_rows, schema=schema)
    df = df.select(*[col(c) for c in all_cols])

    # Build the input projection: parse_json-wrap semi-structured params so
    # the body's references see the correct VARIANT/ARRAY/OBJECT type at
    # evaluation time.  Stage / non-structured cols pass through unchanged.
    proj_cols = [col("__ROW_ID")]
    string_columns = {
        c for c in all_cols if any(isinstance(row.get(c), str) for row in indexed_rows)
    }
    for c in all_cols:
        if c == "__ROW_ID":
            continue
        if structured_params and c.upper() in structured_params:
            proj_cols.append(parse_json(col(c)).alias(c))
        elif c in string_columns:
            proj_cols.append(col(c).cast("VARCHAR(16777216)").alias(c))
        else:
            proj_cols.append(col(c).alias(c))

    # Bind to a uniquely-named temp table per worker thread + call so
    # concurrent models in ThreadPoolExecutor cannot collide.  The table is
    # TEMPORARY (dies with the session) AND we drop it explicitly in the
    # finally so the session catalog stays tidy.
    #
    # Historical note: this used ``create_or_replace_temp_view`` until
    # BENCHMARK_GEPA's full-bench run on 2026-05-13 surfaced Snowflake
    # error 090222 ("View definition too large") for body / body_agent
    # test-eval on scenarios with large-text inputs (48K-char contracts
    # × 200 test rows inlined into the view DDL blew past the ~1 MB
    # view-definition budget).  Temporary TABLES store data in storage
    # rather than in the catalog definition, so the size limit doesn't apply.
    import threading

    tid = threading.get_ident()
    table_name = f"__INLINE_BODY_INPUT_{tid}_{time.time_ns()}"
    try:
        # ``mode="overwrite"`` makes the unique-per-call name idempotent
        # even on rare collision; ``table_type="temporary"`` creates a
        # session-scoped table that auto-drops on session end.
        df.select(*proj_cols).write.save_as_table(
            table_name, mode="overwrite", table_type="temporary"
        )
        sql, _tokens_ok = _build_inline_eval_sql(
            candidate_body=candidate_body,
            input_view_name=table_name,
        )
        _t0 = time.perf_counter()
        # NOTE: ``add_udf_exec`` was previously called inside this
        # ``finally`` block — but at that point we hadn't yet parsed the
        # per-row token counts out of ``collected``, so the timeline
        # event landed on the tracker WITHOUT prompt/completion token
        # info.  That broke the per-call token Gantt for body mode.
        # Defer the tracker.add_udf_exec call until AFTER token totals
        # are available so the event carries the same metadata as the
        # prompt-mode path in ``SnowflakeAdapter._call_udf_batch``.
        try:
            collected = session.sql(sql).collect()
            exec_dur = time.perf_counter() - _t0
        except Exception:
            # Still record duration on failure so the time-axis Gantt
            # shows the failed call; tokens stay (None, None) since no
            # rows were returned to extract from.
            if tracker is not None:
                tracker.add_udf_exec(time.perf_counter() - _t0, model=udf_model)
            raise
    finally:
        with contextlib.suppress(Exception):
            session.sql(f"DROP TABLE IF EXISTS {table_name}").collect()

    results: list[object] = []
    tokens: list[tuple[int, int]] = []
    for r in collected:
        v = r[_INLINE_RESULT_COL]
        if isinstance(v, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                v = json.loads(v)
        results.append(v if v is not None else "")

        pt = r[_INLINE_PROMPT_TOKENS_COL]
        ct = r[_INLINE_COMPLETION_TOKENS_COL]
        try:
            pt_int = int(pt) if pt is not None else 0
        except (TypeError, ValueError):
            pt_int = 0
        try:
            ct_int = int(ct) if ct is not None else 0
        except (TypeError, ValueError):
            ct_int = 0
        tokens.append((pt_int, ct_int))

    sum_p = sum(p for p, _ in tokens)
    sum_c = sum(c for _, c in tokens)
    in_chars = 0
    out_chars = 0
    if tracker is not None and udf_model:
        # Char-based estimate for back-compat with existing cost-quality
        # rendering (see ``TimingTracker.add_chars`` docstring).
        for row in rows:
            in_chars += sum(len(str(v) or "") for v in row.values())
        out_chars = sum(len(str(r) or "") for r in results)
        tracker.add_chars(udf_model, "udf", in_chars, out_chars)
        # Real token totals from the show_details usage block.  Both
        # buckets coexist so old plots keep working while new plots
        # can use real tokens.  See plan corner case #11 — failed rows
        # contribute (0, 0) here (their usage field is null), so this
        # slightly under-counts wasted tokens when callers retry.
        tracker.add_tokens(udf_model, "udf", sum_p, sum_c)

    if tracker is not None:
        # Stamp the per-call event with token + char metadata so the new
        # token Gantt chart can size each udf_exec segment.  Real token
        # counts come from the ``show_details`` ``usage`` block (REAL,
        # ``token_source="real"``).  ``model`` enables per-lane labelling
        # in the multi-model case.
        tracker.add_udf_exec(
            exec_dur,
            prompt_tokens=sum_p,
            completion_tokens=sum_c,
            input_chars=in_chars if udf_model else None,
            output_chars=out_chars if udf_model else None,
            model=udf_model or None,
        )

    return results, tokens


def make_body_evaluator(
    session: Session,
    function_def: FunctionDefinition,
    temp_function_name: str,
    input_columns: list[str],
    metric_evaluator: Evaluator,
    pin_model: str | None = None,
) -> Callable:
    """Closure factory that conforms to the optimize_anything Evaluator protocol.

    Each call to the returned evaluator runs a single inline-eval SELECT for
    the candidate body over one row.  No ``CREATE TEMPORARY FUNCTION`` is
    issued — the body's AI_COMPLETE call is augmented with
    ``show_details=>TRUE`` so the same SQL captures the model output AND
    per-row token counts in one round-trip.  See ``_evaluate_inline_body``.

    *temp_function_name* is preserved for API compatibility with callers
    (and used as a stable advisory label inside the inline-eval temp view
    name) but is no longer a Snowflake function name.

    Parameters
    ----------
    session : Session
        The Snowflake session used to run the inline-eval SELECT.
    function_def : FunctionDefinition
        The introspected definition of the function being optimized, used to
        build the inline-eval body (semi-structured param handling) from each
        candidate.
    temp_function_name : str
        Advisory label preserved for API compatibility; used only as a
        stable label inside the inline-eval temp view name.
    input_columns : list[str]
        Names of the input columns to pull from each example row.
    metric_evaluator : Evaluator
        Scores the function output against the labeled example.
    pin_model : str | None
        When set, the ``model => '...'`` tag in every candidate body is
        rewritten to *pin_model* before evaluation.  This prevents the
        reflection LM from inadvertently switching models mid-optimization.

    """
    del temp_function_name  # advisory only after the inline-eval migration

    def evaluator(candidate: str, example: dict) -> tuple[float, dict]:
        # Pin the model tag if requested, so the reflection LM
        # cannot inadvertently switch models during optimization.
        if pin_model:
            candidate = _swap_model_in_body(candidate, pin_model)

        # --- Execute + score (inline SELECT — no separate compile step) ---
        try:
            row = {c: example["inputs"].get(c, "") for c in input_columns}
            results, _tokens = _evaluate_inline_body(
                session,
                function_def,
                candidate,
                [row],
                udf_model=pin_model or "",
            )
            # ``to_text`` matches the deployed-UDF path so VARIANT array/object
            # outputs reach the metric as JSON, not a Python repr (see batch path).
            response = to_text(results[0]) if results else ""
        except Exception as e:
            # Inline SQL collapses today's separate compile / runtime error
            # feedback into one path.  Pattern-match the message so GEPA's
            # reflective proposer still receives the "Fix the SQL syntax"
            # signal when the candidate body is syntactically invalid.
            err_msg = str(e)
            err_lc = err_msg.lower()
            is_compile_error = (
                "sql compilation error" in err_lc
                or "syntax error" in err_lc
                or "syntactically invalid" in err_lc
                or "invalid identifier" in err_lc
            )
            if is_compile_error:
                log(f"Compilation failed: {e}")
                return 0.0, {
                    "Error": err_msg,
                    "Candidate (truncated)": truncate_for_feedback(candidate),
                    "Feedback": (
                        f"Function body failed SQL compilation: {err_msg}. "
                        "Fix the SQL syntax."
                    ),
                }
            log(f"Runtime error: {e}")
            return 0.0, {
                "Error": err_msg,
                "Candidate (truncated)": truncate_for_feedback(candidate),
                "Feedback": f"Function body produced runtime error: {err_msg}.",
            }

        tracker = get_active_tracker()
        _t0 = time.perf_counter()
        try:
            quality_score, feedback = compute_metric(
                metric_evaluator.metric_name,
                example["answer"],
                response,
                session,
                metric_evaluator.custom_metric_udf,
                **dict(metric_evaluator.kwargs),
            )
        finally:
            if tracker is not None:
                tracker.add_metric(time.perf_counter() - _t0)

        log(f"Quality: {quality_score:.3f}, Feedback: {feedback}")

        return quality_score, {
            "Input": "\n".join(f"{k}: {v}" for k, v in example["inputs"].items()),
            "Output": response,
            "Expected": example["answer"],
            "Feedback": feedback,
        }

    return evaluator


def _make_body_executor(
    session: Session,
    function_def: FunctionDefinition,
    candidate_body: str,
    temp_function_name: str,
    udf_model: str = "",
) -> Callable[[list[dict[str, object]]], list[object]]:
    """Build a PredictionExecutor that calls ``_evaluate_inline_body`` per batch.

    The previous implementation compiled a temp UDF once per executor; the
    inline-eval path does no per-executor compile step (each batch issues
    one ``session.sql(<CTE>)`` round-trip directly).  Net round-trip count
    is roughly the same: today's compile + N execs becomes N inline-eval
    SELECTs, but the per-call ``create_or_replace_temp_view`` for the input
    batch is a thin operation Snowflake optimizes across the session.

    *temp_function_name* is retained as an advisory label.  *udf_model*
    threads through to ``_evaluate_inline_body`` so char + token usage
    accumulate under the right model key on the active TimingTracker.
    """
    del temp_function_name  # advisory only after the inline-eval migration

    def executor(rows: list[dict[str, object]]) -> list[object]:
        results, _tokens = _evaluate_inline_body(
            session,
            function_def,
            candidate_body,
            rows,
            udf_model=udf_model,
        )
        return results

    return executor


def _swap_model_in_body(body: str, new_model: str) -> str:
    """Replace the model name in a body's single AI_COMPLETE call.

    Handles both calling forms:
      * Named:      ``AI_COMPLETE(model => 'old', ...)`` → keeps ``model =>``
      * Positional: ``AI_COMPLETE('old', ...)``         → rewrites first arg

    Returns *body* unchanged when no AI_COMPLETE call is present, so
    callers can pin a model on candidate bodies that the reflection LM
    occasionally emits without an AI_COMPLETE call (those candidates
    will fail compilation and be discarded downstream).
    """
    located = _locate_model_literal(body)
    if located is None:
        return body
    start, end, _ = located
    return body[:start] + new_model + body[end:]


def _run_single_model_body_optimization(
    *,
    model: str,
    session: Session,
    function_def: FunctionDefinition,
    seed_body: str,
    function_name: str,
    function_signature: str,
    trainset: list[SnowflakeDataInst],
    valset: list[SnowflakeDataInst],
    input_col_names: list[str],
    input_columns: list,
    metric_evaluator: Evaluator,
    reflection_model: str,
    temperature: float,
    max_tokens: int,
    resolved_budget: int,
    reflection_weight: int,
    metric_name: str,
    test_table: str | None,
    label_column: str,
    dataset_expected_columns: list[str] | None,
    run_id: str,
    aggregation_metric: str | None,
    experiment_name: str | None,
    dataset_load_start_perf: float | None,
    dataset_load_end_perf: float | None,
    reflection_backend: Literal[
        "ai_complete", "agent_run", "agent_run_single_session"
    ] = "ai_complete",
    run_dir: str | None = None,
    input_arg_names: list[str] | None = None,
    run_counter: GlobalRunCounter | None = None,
    fail_on_reflection_error: bool = False,
) -> ModelOptimizationResult:
    """Run body optimization for a single model. Designed for parallel execution."""
    model_start = time.time()
    logger.debug(f"    [{model}] Starting body optimization")

    # Shared across all parallel model workers so every model's ITER runs draw
    # from one global sequence.  A local fallback keeps direct/unit-test calls
    # (single worker, no shared counter) functional.
    if run_counter is None:
        run_counter = GlobalRunCounter()

    model_seed_body = _swap_model_in_body(seed_body, model)

    # Name each input column is presented under to candidates. With argument
    # binding these are the (already-resolved) AI-function parameter names that
    # ``load_dataset`` keyed each row's ``inputs`` dict by; otherwise the real
    # column names. ``None`` keeps behavior byte-identical to today.
    present_as = input_arg_names or input_col_names

    model_suffix = re.sub(r"[^A-Za-z0-9]", "_", model).upper()
    temp_fn = build_temp_function_name(function_name, f"__OPT_BODY_{model_suffix}")

    body_evaluator = make_body_evaluator(
        session,
        function_def,
        temp_fn,
        present_as,
        metric_evaluator,
        pin_model=model,
    )
    objective, background = build_objective_and_background(
        function_name,
        function_signature,
        model_seed_body,
        model,
        metric_name,
    )

    # Route the reflection LM through the reflection-backend registry.
    # Production registers "ai_complete" -> SnowflakeLLM; dev registers
    # "agent_run" / "agent_run_single_session" -> SnowflakeAgentLM.
    reflection_lm = resolve_reflection_lm(
        reflection_backend,
        session=session,
        model=reflection_model or model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    # When the caller wants reflection failures to be fatal (spec-driven /
    # EXECUTE EXPERIMENT path), turn on retries and give the reflection LM an
    # error sink. GEPA catches the reflection exception internally and returns
    # no candidate, so the sink is how the outer loop learns a reflection call
    # ultimately failed. Only the built-in ``ai_complete`` backend
    # (``SnowflakeLLM``) supports this; dev agent backends are left untouched.
    reflection_error_sink: list[Exception] = []
    if fail_on_reflection_error and isinstance(reflection_lm, SnowflakeLLM):
        reflection_lm.max_attempts = REFLECTION_MAX_ATTEMPTS
        reflection_lm.error_sink = reflection_error_sink
    budget_stopper = MaxTotalBudgetStopper(
        reflection_lm,
        max_budget=resolved_budget,
        reflection_call_weight=reflection_weight,
    )

    def _reflection_error_stopper(_state: Any) -> bool:
        """Stop the GEPA loop as soon as a reflection call has failed for good.

        Reflection produces the candidate for the next iteration; once it has
        failed there is nothing to continue with, so break instead of burning
        the remaining budget on retries that keep failing. Inert unless the
        sink is populated (i.e. unless ``fail_on_reflection_error`` is set and a
        reflection call exhausted its retries).
        """
        return bool(reflection_error_sink)

    tracker = TimingTracker()
    _iter_count = [0]

    def _iteration_marker(_state: Any) -> bool:
        _iter_count[0] += 1
        # Use get_program_average_val_subset to find the current best score.
        n_candidates = len(_state.program_candidates)
        best_score = None
        if n_candidates > 0:
            # Find the best average val score across all candidates
            best_score = max(
                _state.get_program_average_val_subset(i)[0] for i in range(n_candidates)
            )
        logger.debug(
            f"    [{model}] Iteration {_iter_count[0]} complete: "
            f"candidates={n_candidates}, "
            f"best_val_score={best_score}, "
            f"metric_calls={_state.total_num_evals}"
        )
        tracker.mark_iteration()
        return False

    run_dir_ctx: contextlib.AbstractContextManager
    if run_dir:
        # Persistent run_dir provided — use per-model subdirectory directly.
        model_run_dir = os.path.join(run_dir, re.sub(r"[^A-Za-z0-9]", "_", model))
        os.makedirs(model_run_dir, exist_ok=True)
        run_dir_ctx = contextlib.nullcontext(model_run_dir)
    else:
        run_dir_ctx = (
            tempfile.TemporaryDirectory(prefix="gepa_body_")
            if experiment_name
            else contextlib.nullcontext(None)
        )

    with run_dir_ctx as gepa_run_dir:
        batch_ctx = BodyBatchEvalContext(
            session=session,
            function_def=function_def,
            temp_function_name=temp_fn,
            input_columns=present_as,
            metric_evaluator=metric_evaluator,
            pin_model=model,
            full_valset_size=len(valset),
        )
        # Wrap BodyBatchEvalContext to record "gepa_thinking" phase events
        # — the time GEPA spends in Python between two consecutive evaluator
        # calls (candidate selection, Pareto frontier updates, minibatch
        # scheduling, score aggregation).  Each gap between the END of one
        # BodyBatchEvalContext.__call__ and the START of the next is one
        # gepa_thinking event.  The first call's pre-gap (GEPA initialisation
        # before the very first evaluate) and the final gap (GEPA cleanup
        # after the last evaluate) are also captured, giving a near-complete
        # decomposition of the GEPA engine overhead.
        _last_body_eval_end: list[float | None] = [None]
        _original_batch_ctx = batch_ctx

        # _gepa_loop_t0 is set right after this block; store a mutable
        # reference so the inner class can read it for the "gepa_init"
        # gap (time from optimize_anything() entry to the first evaluate).
        _gepa_loop_start_ref: list[float] = [0.0]

        class _ThinkingTimedCtx:
            def __call__(self, candidate_body: str, eval_batch: Any) -> Any:
                _t_call = time.perf_counter()
                if _last_body_eval_end[0] is not None:
                    # Normal inter-evaluate thinking gap.
                    tracker.add_phase(
                        "gepa_thinking",
                        _last_body_eval_end[0],
                        _t_call,
                        label="between_evals",
                    )
                elif _gepa_loop_start_ref[0] > 0:
                    # First evaluate call — gap from optimize_anything() entry.
                    tracker.add_phase(
                        "gepa_thinking",
                        _gepa_loop_start_ref[0],
                        _t_call,
                        label="gepa_init",
                    )
                result = _original_batch_ctx(candidate_body, eval_batch)  # type: ignore[operator]
                _last_body_eval_end[0] = time.perf_counter()
                return result

            def __getattr__(self, name: str) -> Any:
                return getattr(_original_batch_ctx, name)

        oa_thread_local.body_batch_ctx = _ThinkingTimedCtx()
        set_active_tracker(tracker)
        # Backfill the dataset_load phase event using the pre-tracker
        # perf_counter timestamps captured in run_body_optimization.
        # perf_counter() is monotonic and process-wide, so timestamps
        # recorded before the tracker was created are still valid and
        # resolve to epoch-ms values that pre-date the tracker's anchor.
        if dataset_load_start_perf is not None and dataset_load_end_perf is not None:
            tracker.add_phase(
                "dataset_load",
                dataset_load_start_perf,
                dataset_load_end_perf,
                label="load_dataset",
            )
        # Anchor for the high-level "gepa_loop" phase event recorded
        # at the end of the GEPA optimization (success path) so the
        # Gantt timeline shows one big block covering the entire
        # optimize_anything() call.  The per-call metric/reflection
        # events are nested inside that block.
        _gepa_loop_t0 = time.perf_counter()
        _gepa_loop_start_ref[0] = _gepa_loop_t0  # expose to inner class
        logger.debug(
            f"    [{model}] Entering GEPA loop "
            f"(budget={resolved_budget}, reflection_weight={reflection_weight})"
        )
        rejected_collector = RejectedCandidateCollector()
        progressive_tracker: ProgressiveExperimentTracker | None = None
        if experiment_name:
            progressive_tracker = ProgressiveExperimentTracker(
                session=session,
                experiment_name=experiment_name,
                model=model,
                function_name=function_name,
                run_counter=run_counter,
                # Same dict the batched adapter fills (shared by reference
                # through the _ThinkingTimedCtx __getattr__ delegation).
                eval_detail_buffer=batch_ctx.eval_detail_buffer,
            )
        _callbacks: list = [rejected_collector]
        if progressive_tracker is not None:
            _callbacks.append(progressive_tracker)
        try:
            engine_kwargs: dict = dict(
                max_metric_calls=None,
                candidate_selection_strategy="pareto",
                parallel=DEFAULT_ENGINE_PARALLEL,
                raise_on_exception=False,
                cache_evaluation=DEFAULT_CACHE_EVALUATIONS,
                cache_evaluation_storage="memory",
                frontier_type="instance",
            )
            if gepa_run_dir is not None:
                engine_kwargs["run_dir"] = gepa_run_dir

            with _gepa_engine_callbacks(_callbacks):
                result = optimize_anything(
                    seed_candidate=model_seed_body,
                    evaluator=body_evaluator,
                    dataset=trainset,
                    valset=valset,
                    objective=objective,
                    background=background,
                    config=GEPAConfig(
                        engine=EngineConfig(**engine_kwargs),
                        reflection=ReflectionConfig(
                            reflection_lm=reflection_lm,
                            skip_perfect_score=True,
                            perfect_score=DEFAULT_PERFECT_SCORE,
                            reflection_minibatch_size=DEFAULT_REFLECTION_MINIBATCH_SIZE,
                        ),
                        merge=MergeConfig(
                            max_merge_invocations=0,
                        ),
                        # Always pass a safe logger to prevent GEPA from creating
                        # a file-based Logger that mutates global sys.stdout/stderr
                        # — unsafe when multiple models run via ThreadPoolExecutor.
                        tracking=TrackingConfig(
                            logger=PythonLoggingAdapter(logger, prefix=model)
                        ),
                        stop_callbacks=[
                            _iteration_marker,  # type: ignore[list-item]
                            budget_stopper,
                            _reflection_error_stopper,  # type: ignore[list-item]
                        ],
                    ),
                )
            # A reflection call that exhausted its retries is fatal for this
            # model: GEPA swallowed the exception and produced no candidate, so
            # raise it here to fall into the failure path below, which commits
            # this model's runs FAILED with the reflection error on the run —
            # rather than letting the model finish SUCCEEDED with the error lost.
            if reflection_error_sink:
                raise RuntimeError(
                    f"Reflection call failed after {REFLECTION_MAX_ATTEMPTS} "
                    f"attempts: {reflection_error_sink[0]}"
                ) from reflection_error_sink[0]
        except Exception as e:
            error_msg = str(e)
            logger.debug(f"    [{model}] GEPA loop FAILED: {error_msg[:200]}")
            logger.error("[OPTIMIZATION_ERROR] %s: %s", model, error_msg)
            # Global run structure: a failed model gets NO separate
            # ``<MODEL>_FAILED`` run.  Commit the runs this model actually
            # wrote (its RUNNING ``ITER_<N>`` runs) with ``STATUS='FAILED'``
            # so the failure is carried on the real runs it produced.  The
            # error itself is surfaced on the returned ModelOptimizationResult.
            if experiment_name and progressive_tracker is not None:
                # Record WHY the failure happened on the most-recently-created
                # still-RUNNING run (highest ITER_<N>, else SEED) before failing
                # all of this model's runs — the error lives in the run's
                # error_message parameter (metadata has no such field).
                target = most_recent_running_run(progressive_tracker.persisted_runs)
                if target:
                    set_run_error_message(session, experiment_name, target, error_msg)
                commit_runs(
                    session,
                    experiment_name,
                    list(progressive_tracker.persisted_runs),
                    status="FAILED",
                )
            set_active_tracker(None)
            return ModelOptimizationResult(
                model=model,
                status="failed",
                error=error_msg,
                elapsed_seconds=round(time.time() - model_start, 2),
            )
        finally:
            oa_thread_local.body_batch_ctx = None
            # Capture the final "gepa_thinking" gap — time from the last
            # evaluator call returning to optimize_anything() itself returning.
            # This is GEPA's post-loop cleanup: final scoring, result
            # packaging, best-candidate selection.
            #
            # ``_gepa_engine_callbacks`` cleared its TLS binding on
            # ``__exit__`` already, so no additional cleanup is needed
            # for the rejected-collector wiring.
            _t_finally = time.perf_counter()
            if _last_body_eval_end[0] is not None:
                tracker.add_phase(
                    "gepa_thinking",
                    _last_body_eval_end[0],
                    _t_finally,
                    label="gepa_cleanup",
                )
            # NOTE: do NOT clear the active tracker here.  We need it to
            # stay live for the ``backfill_model_metrics`` call (below) so
            # the experiment-DDL timings land on the SAME tracker.  (The final
            # COMMIT + artifact PUTs run post-join in the orchestrator.)
            # The success path clears the tracker right before
            # ``return model_output`` further below; the failure path
            # already cleared it just above its return.
            tracker.mark_iteration()
            # Coarse phase event covering the whole GEPA loop so the
            # Gantt chart has a parent span the per-iteration metric /
            # reflection events sit inside.  Recorded in the outer
            # finally so that exceptions don't drop the marker.
            tracker.add_phase(
                "gepa_loop", _gepa_loop_t0, time.perf_counter(), label=model
            )

        # Any exception in the post-GEPA body (test-eval, experiment storage,
        # pareto computation) is caught here and surfaces as a failed
        # ModelOptimizationResult so the error reaches the caller's return
        # dict rather than being silently swallowed.
        model_output: ModelOptimizationResult | None = None
        try:
            best_body = result.best_candidate
            if isinstance(best_body, dict):
                best_body = next(iter(best_body.values()))
            best_body = _swap_model_in_body(str(best_body), model)

            best_val_score = (
                result.val_aggregate_scores[result.best_idx]
                if result.val_aggregate_scores
                else None
            )
            seed_val_score = (
                result.val_aggregate_scores[0] if result.val_aggregate_scores else None
            )
            logger.debug(
                f"    [{model}] GEPA loop done: "
                f"{len(result.candidates)} candidates, "
                f"seed_val={seed_val_score}, best_val={best_val_score}, "
                f"metric_calls={result.total_metric_calls}"
            )

            model_elapsed = round(time.time() - model_start, 2)
            model_output = ModelOptimizationResult(
                model=model,
                status="completed",
                elapsed_seconds=model_elapsed,
                best_prompt=best_body,
                best_val_score=best_val_score,
                seed_val_score=seed_val_score,
                total_candidates=len(result.candidates),
                total_metric_seconds=round(tracker.total_metric_seconds, 4),
                total_reflection_seconds=round(tracker.total_reflection_seconds, 4),
                total_udf_compile_calls=tracker.total_udf_compile_calls,
                total_udf_compile_seconds=round(tracker.total_udf_compile_seconds, 4),
                total_udf_exec_calls=tracker.total_udf_exec_calls,
                total_udf_exec_seconds=round(tracker.total_udf_exec_seconds, 4),
                total_udf_prompt_tokens=tracker.total_udf_prompt_tokens,
                total_udf_completion_tokens=tracker.total_udf_completion_tokens,
                total_reflection_prompt_tokens_est=(
                    tracker.total_reflection_prompt_tokens_est
                ),
                total_reflection_completion_tokens_est=(
                    tracker.total_reflection_completion_tokens_est
                ),
                total_experiment_calls=tracker.total_experiment_calls,
                total_experiment_seconds=round(tracker.total_experiment_seconds, 4),
                total_artifact_calls=tracker.total_artifact_calls,
                total_artifact_seconds=round(tracker.total_artifact_seconds, 4),
                all_val_scores=result.val_aggregate_scores,
                reflection_model=label_reflection_model(
                    reflection_model or model, reflection_backend
                ),
                reflection_backend=reflection_backend,
            )

            # Snapshot tracker counts before test eval so we can attribute
            # the test-set scoring cost to the BEST tracking row (instead
            # of letting it inflate the optimization-wide aggregates).
            pre_test_eval = tracker.snapshot()

            # Compute avg_output_chars from in-memory valset as a baseline so
            # it is always available for cost estimation even when no test table
            # is provided. The test-table path below overrides this with the
            # test data when available.
            if valset:
                model_output.avg_output_chars = int(
                    sum(len(d["answer"]) for d in valset) / len(valset)
                )

            # Test-set evaluation and experiment storage are wrapped in
            # try/except so that transient session errors (e.g. shared-session
            # I/O races across threads) degrade gracefully to validation-only
            # scores instead of losing the entire optimization result.
            _seed_eval_details = None
            _test_eval_t0 = time.perf_counter()
            try:
                if test_table and function_def:
                    logger.debug(f"    [{model}] Running test-set evaluation...")
                    eval_metric_options = dict(metric_evaluator.kwargs)
                    if metric_evaluator.metric_name == "llm_judge":
                        eval_metric_options["scoring_mode"] = "binary"
                    if dataset_expected_columns:
                        eval_metric_options["expected_columns"] = (
                            dataset_expected_columns
                        )

                    test_temp_fn = build_temp_function_name(
                        function_name,
                        f"__OPT_TEST_{model_suffix}",
                    )
                    seed_executor = _make_body_executor(
                        session,
                        function_def,
                        model_seed_body,
                        test_temp_fn,
                        udf_model=model,
                    )
                    seed_eval = evaluate(
                        session=session,
                        function_name=test_temp_fn,
                        test_table=test_table,
                        input_columns=input_columns,
                        label_column=label_column,
                        metric_name=metric_evaluator.metric_name,
                        custom_metric_udf=metric_evaluator.custom_metric_udf,
                        metric_options=eval_metric_options,
                        model_name=model,
                        executor=seed_executor,
                        run_id=run_id,
                        split="test_seed",
                        input_arg_names=input_arg_names,
                    )
                    model_output.seed_test_score = seed_eval.score
                    _seed_eval_details = seed_eval.details
                    test_count = session.sql(
                        f"SELECT COUNT(*) FROM {test_table}"
                    ).collect()[0][0]
                    model_output.num_test_examples = test_count
                    avg_out_raw = session.sql(
                        f"SELECT AVG(LENGTH({label_column})) FROM {test_table}"
                    ).collect()[0][0]
                    model_output.avg_output_chars = int(avg_out_raw or 0)

            finally:
                tracker.add_phase(
                    "test_eval", _test_eval_t0, time.perf_counter(), label=model
                )

            # Compute the test-eval delta.
            _delta = pre_test_eval.delta(tracker)
            model_output.test_eval_metric_calls = _delta.metric_calls
            model_output.test_eval_metric_seconds = _delta.metric_seconds
            model_output.test_eval_udf_compile_calls = _delta.udf_compile_calls
            model_output.test_eval_udf_compile_seconds = _delta.udf_compile_seconds
            model_output.test_eval_udf_exec_calls = _delta.udf_exec_calls
            model_output.test_eval_udf_exec_seconds = _delta.udf_exec_seconds
            model_output.test_eval_reflection_calls = _delta.reflection_calls
            model_output.test_eval_reflection_seconds = _delta.reflection_seconds
            model_output.test_eval_udf_prompt_tokens = _delta.udf_prompt_tokens
            model_output.test_eval_udf_completion_tokens = _delta.udf_completion_tokens

            # Cross-model selection in ``run_body_optimization`` reads
            # ``best_score`` to pick the winning model.  Always use the
            # validation score here so the held-out test set is not
            # used for selection -- even when test-eval was performed
            # on the SEED for baseline reporting.  Per-model
            # ``best_test_score`` will be filled in by
            # ``run_body_optimization`` for the winning model only,
            # after selection.
            model_output.seed_score = seed_val_score
            model_output.best_score = best_val_score
            model_output.score_source = "validation"

            # -- Pareto candidate data (pure computation, always set before save) --
            candidates_text = []
            for c in result.candidates:
                if isinstance(c, dict):
                    raw = str(next(iter(c.values())) if c else "")
                else:
                    raw = str(c)
                candidates_text.append(_swap_model_in_body(raw, model))

            # The SEED is evaluated before the GEPA loop, so its per-call
            # eval cost only exists in the iteration-0 tracker boundary.
            # Record it under candidate index 0 so cost estimation can
            # price the SEED like any ITER candidate.
            rejected_collector.capture_seed_from_iteration_stats(
                tracker.per_iteration_stats()
            )

            # Schema v4: the tracker wrote each ITER run under a GLOBAL name
            # (``ITER_<N>``).  Map each local population index to its global
            # run name so Pareto candidates + the metric backfill reference the
            # real runs.  Index 0 is the shared ``SEED``.
            run_names_map: dict[int, str] | None = None
            if progressive_tracker is not None:
                run_names_map = {0: "SEED", **progressive_tracker.local_to_global}

            model_output.pareto_candidates = compute_pareto_candidates(
                model=model,
                candidates=candidates_text,
                val_scores=result.val_aggregate_scores,
                discovery_iter=rejected_collector.discovery_iter,
                phase_breakdowns=rejected_collector.phase_breakdowns,
                run_names=run_names_map,
            )

            # Carry per-model finalize inputs to the post-join step.
            model_output.total_candidates = len(result.candidates)
            model_output.reflection_model = label_reflection_model(
                reflection_model or model, reflection_backend
            )
            model_output.run_dir = gepa_run_dir
            model_output.seed_eval_details = _seed_eval_details

            # -- Experiment storage (schema v4) --
            # Backfill full valset_score + per-call estimated_cost onto this
            # model's RUNNING ITER runs (written by the tracker under global
            # names).  The single consolidated SEED, cross-model Pareto
            # stamping, and the COMMIT of every run are deferred to the
            # post-join step (``_select_best_from_frontier``) so is_frontier /
            # test_score can be stamped in place; the returned ITER names are
            # committed there via ``commit_runs``.
            _save_t0 = time.perf_counter()
            try:
                if experiment_name and progressive_tracker is not None:
                    logger.debug(
                        f"    [{model}] Backfilling metrics to {experiment_name}..."
                    )
                    model_output.pending_commit_runs = backfill_model_metrics(
                        session,
                        experiment_name,
                        pareto_candidates=model_output.pareto_candidates,
                    )
            finally:
                tracker.add_phase("save", _save_t0, time.perf_counter(), label=model)

            # Refresh tracker-sourced totals AFTER the metric backfill so the
            # per-(scenario, mode) row in BENCH_RESULTS captures the experiment
            # DDL/DML writes done during backfill.  (Commit + artifact PUTs run
            # post-join in the orchestrator.)
            model_output.total_metric_calls = tracker.total_metric_calls
            model_output.total_reflection_calls = tracker.total_reflection_calls
            model_output.total_metric_seconds = round(tracker.total_metric_seconds, 6)
            model_output.total_reflection_seconds = round(
                tracker.total_reflection_seconds, 4
            )
            model_output.total_udf_compile_calls = tracker.total_udf_compile_calls
            model_output.total_udf_compile_seconds = round(
                tracker.total_udf_compile_seconds, 4
            )
            model_output.total_udf_exec_calls = tracker.total_udf_exec_calls
            model_output.total_udf_exec_seconds = round(
                tracker.total_udf_exec_seconds, 4
            )
            model_output.total_udf_prompt_tokens = tracker.total_udf_prompt_tokens
            model_output.total_udf_completion_tokens = (
                tracker.total_udf_completion_tokens
            )
            model_output.total_reflection_prompt_tokens_est = (
                tracker.total_reflection_prompt_tokens_est
            )
            model_output.total_reflection_completion_tokens_est = (
                tracker.total_reflection_completion_tokens_est
            )
            model_output.total_experiment_calls = tracker.total_experiment_calls
            model_output.total_experiment_seconds = round(
                tracker.total_experiment_seconds, 4
            )
            model_output.total_artifact_calls = tracker.total_artifact_calls
            model_output.total_artifact_seconds = round(
                tracker.total_artifact_seconds, 4
            )

            model_output.timeline_events = tracker.export_events()
        except Exception as post_gepa_err:
            # Surface post-GEPA errors (test-eval failure, pareto computation,
            # experiment storage) as a failed result rather than silently
            # swallowing them.  The error lands in model_results and propagates
            # into the return dict where the user can see it.
            logger.error(
                "[POST_GEPA_ERROR] %s: %s",
                model,
                post_gepa_err,
                exc_info=True,
            )
            if model_output is None:
                model_output = ModelOptimizationResult(
                    model=model,
                    status="failed",
                    error=str(post_gepa_err),
                    elapsed_seconds=round(time.time() - model_start, 2),
                )
            else:
                model_output.status = "failed"
                model_output.error = str(post_gepa_err)
            # No ``<MODEL>_FAILED`` run: commit whatever runs this model wrote
            # (RUNNING ``ITER_<N>``) as FAILED so they don't linger uncommitted.
            if experiment_name and progressive_tracker is not None:
                # Surface the reason on the most-recently-created still-RUNNING
                # run's error_message parameter before failing them all.
                target = most_recent_running_run(progressive_tracker.persisted_runs)
                if target:
                    set_run_error_message(
                        session, experiment_name, target, str(post_gepa_err)
                    )
                commit_runs(
                    session,
                    experiment_name,
                    list(progressive_tracker.persisted_runs),
                    status="FAILED",
                )
            return model_output
        finally:
            # Tracker stays live through the post-finally body above
            # (test eval + the ``backfill_model_metrics`` call need it so
            # experiment times land on the SAME tracker);
            # release it here so the worker thread doesn't carry it
            # into the next ``ThreadPoolExecutor`` task.
            set_active_tracker(None)
        logger.debug(
            f"    [{model}] Complete: elapsed={model_output.elapsed_seconds}s, "
            f"score_source={model_output.score_source}, "
            f"best_score={model_output.best_score}"
        )
        return model_output


# ---------------------------------------------------------------------------
# Orchestration helpers (extracted from run_body_optimization)
# ---------------------------------------------------------------------------


def _validate_and_prepare_config(
    session: Session,
    function_name: str,
    training_table: str,
    label_column: str,
    input_columns: list,
    metric_name: str,
    models: list,
    reflection_model: str,
    test_table: str | None,
    auto_budget: BudgetType,
    validation_fraction: float,
    temperature: float,
    max_tokens: int,
    metric_options: dict | None,
    custom_metric_udf: str | None,
    run_id: str | None,
    aggregation_metric: str | None,
    experiment_name: str | None,
    engine: EngineType,
    max_concurrency: int,
    reflection_backend: Literal["ai_complete", "agent_run", "agent_run_single_session"],
    max_frontier_candidates: int,
    run_dir: str | None,
    input_arg_names: list[str] | None = None,
    upload_run_dir: bool = True,
    query_text: str | None = None,
    create_experiment_if_missing: bool = True,
    fail_on_reflection_error: bool = False,
) -> BodyOptConfig:
    """Validate parameters and build a BodyOptConfig.

    Raises:
        ValueError: On invalid user-supplied parameters.

    """
    if not run_id:
        func_short_name = function_name.split(".")[-1].split("(")[0]
        run_id = f"ai_func_opt_{func_short_name}_{int(time.time() * 1000)}"

    if models is None or len(models) == 0:
        raise ValueError("models parameter is required and cannot be empty")
    if reflection_model is None:
        raise ValueError("reflection_model parameter is required")
    if validation_fraction <= 0.0:
        raise ValueError(
            f"validation_fraction must be greater than 0.0 (got {validation_fraction}). "
            "A zero validation fraction produces an empty validation set, which prevents "
            "the optimizer from scoring candidates and causes the optimization to hang."
        )
    if validation_fraction >= 1.0:
        raise ValueError(
            f"validation_fraction must be less than 1.0 (got {validation_fraction}). "
            "A validation fraction of 1.0 leaves no training data for reflection."
        )

    # ---- DDL extraction ----
    # A builtin (query_text) function has no DDL to introspect; its inline
    # expression is modeled as the seed body directly. The user path calls
    # ``describe_function`` (kept as the module-level monkeypatch seam).
    function_def = (
        build_query_text_function_def(query_text, input_columns, name=function_name)
        if query_text is not None
        else describe_function(session, function_name)
    )
    seed_body = function_def.body
    function_signature = f"{function_def.signature} RETURNS {function_def.returns}"
    logger.debug(f"  DDL extracted: seed body = {len(seed_body)} chars")

    # ---- Metric validation ----
    valid_metrics = {
        "exact_match",
        "fuzzy_match",
        "contains_match",
        "redaction_match",
        "llm_judge",
    }
    if metric_name not in valid_metrics and not custom_metric_udf:
        raise ValueError(
            f"Unknown metric: {metric_name}. "
            f"Available: {', '.join(sorted(valid_metrics))}. "
            f"For custom metrics, provide custom_metric_udf parameter."
        )

    input_col_names = [col_name.strip('"').strip("'") for col_name in input_columns]

    # ---- Column validation (training table) ----
    training_columns = get_table_column_names(session, training_table)
    validate_input_columns(training_columns, input_col_names, training_table)

    resolved_label = resolve_expected_column(training_columns, label_column)
    if training_columns and resolved_label.upper() not in training_columns:
        raise ValueError(
            f"Label column '{label_column}' not found in training table "
            f"{training_table}. Available columns: {sorted(training_columns)}"
        )

    # ---- Column validation (test table) ----
    if test_table:
        test_columns = get_table_column_names(session, test_table)
        validate_input_columns(test_columns, input_col_names, test_table)
        test_label = resolve_expected_column(test_columns, label_column)
        if test_columns and test_label.upper() not in test_columns:
            raise ValueError(
                f"Label column '{label_column}' not found in test table "
                f"{test_table}. Available columns: {sorted(test_columns)}. "
                "Training and test tables must use the same column names."
            )

    # ---- Metric options ----
    metric_opts, _, expected_columns = parse_metric_options(metric_options)

    if len(expected_columns) > 1 and metric_name != "llm_judge":
        raise ValueError("Multi-output optimization requires metric_name='llm_judge'.")

    valid_agg_metrics = {"accuracy", "f1-score"}
    if aggregation_metric and aggregation_metric not in valid_agg_metrics:
        raise ValueError(
            f"Unknown aggregation_metric: '{aggregation_metric}'. "
            f"Available: {', '.join(sorted(valid_agg_metrics))}"
        )

    # ---- llm_judge file/multimodal auto-detection ----
    gepa_metric_opts = dict(metric_opts)
    if metric_name == "llm_judge":
        gepa_metric_opts.setdefault("scoring_mode", "continuous")

        if "file_columns" not in gepa_metric_opts:
            all_file_columns: list[str] = []

            detected = extract_to_file_refs(function_def.body)
            if detected:
                stage, columns = detected
                gepa_metric_opts.setdefault("stage_name", stage)
                all_file_columns.extend(columns)

            file_params = file_type_param_names(function_def.args)
            if file_params:
                all_file_columns.extend(
                    p for p in file_params if p not in all_file_columns
                )
                gepa_metric_opts.setdefault("file_type_params", file_params)

            if all_file_columns:
                gepa_metric_opts["file_columns"] = all_file_columns

    dataset_expected_columns = expected_columns if len(expected_columns) > 1 else None

    return BodyOptConfig(
        function_def=function_def,
        seed_body=seed_body,
        function_signature=function_signature,
        function_name=function_name,
        input_col_names=input_col_names,
        input_columns=input_columns,
        input_arg_names=input_arg_names,
        models=models,
        reflection_model=reflection_model,
        metric_name=metric_name,
        gepa_metric_opts=gepa_metric_opts,
        training_table=training_table,
        test_table=test_table,
        label_column=label_column,
        validation_fraction=validation_fraction,
        temperature=temperature,
        max_tokens=max_tokens,
        auto_budget=auto_budget,
        custom_metric_udf=custom_metric_udf,
        aggregation_metric=aggregation_metric,
        experiment_name=experiment_name,
        engine=engine,
        max_concurrency=max_concurrency,
        reflection_backend=reflection_backend,
        run_id=run_id,
        run_dir=run_dir,
        dataset_expected_columns=dataset_expected_columns,
        max_frontier_candidates=max_frontier_candidates,
        upload_run_dir=upload_run_dir,
        create_experiment_if_missing=create_experiment_if_missing,
        fail_on_reflection_error=fail_on_reflection_error,
    )


def _load_and_split_dataset(
    session: Session,
    config: BodyOptConfig,
) -> tuple[list[SnowflakeDataInst], list[SnowflakeDataInst], Evaluator, float, float]:
    """Load dataset, build evaluator, split into train/val.

    Raises:
        ValueError: On invalid stage/file configuration.
        RuntimeError: If training table is empty or experiment already has runs.

    """
    _dataset_load_t0 = time.perf_counter()
    logger.debug(f"  Loading dataset from {config.training_table}...")
    dataset_result = load_dataset(
        session,
        config.training_table,
        config.input_columns,
        config.label_column,
        expected_columns=config.dataset_expected_columns,
        input_arg_names=config.input_arg_names,
    )
    _dataset_load_t1 = time.perf_counter()
    if not dataset_result:
        raise RuntimeError(f"No data found in training table: {config.training_table}")

    gepa_metric_opts = dict(config.gepa_metric_opts)
    if dataset_result.file_stage_name:
        gepa_metric_opts.setdefault("stage_name", dataset_result.file_stage_name)

    metric_evaluator = Evaluator(
        config.metric_name,
        session=session,
        custom_metric_udf=config.custom_metric_udf,
        aggregation_metric=config.aggregation_metric,
        **gepa_metric_opts,
    )

    full_dataset = dataset_result.dataset

    validate_stage_file_access(
        session,
        stage_name=gepa_metric_opts.get("stage_name"),
        file_columns=gepa_metric_opts.get("file_columns"),
        dataset=cast(list[dict[Any, Any]], full_dataset),
    )

    valset, trainset = split_dataset(full_dataset, config.validation_fraction)
    logger.debug(
        f"  Dataset loaded: {len(full_dataset)} rows → "
        f"val={len(valset)}, train={len(trainset)} "
        f"({_dataset_load_t1 - _dataset_load_t0:.2f}s)"
    )

    if config.experiment_name:
        if config.create_experiment_if_missing:
            create_experiment(session, config.experiment_name)

        existing_runs = get_experiment_run_names(session, config.experiment_name)
        if existing_runs:
            raise RuntimeError(
                f"Experiment '{config.experiment_name}' already contains "
                f"{len(existing_runs)} run(s) from a prior optimization. "
                "Delete the experiment before reoptimizing."
            )

    return trainset, valset, metric_evaluator, _dataset_load_t0, _dataset_load_t1


def _compute_optimization_budget(
    config: BodyOptConfig,
    trainset: list[SnowflakeDataInst],
    valset: list[SnowflakeDataInst],
) -> tuple[int, int]:
    """Compute resolved budget and reflection weight."""
    objective, background = build_objective_and_background(
        config.function_name,
        config.function_signature,
        config.seed_body,
        config.models[0],
        config.metric_name,
    )
    reflection_weight = estimate_body_reflection_weight(
        seed_body=config.seed_body,
        objective=objective,
        background=background,
        trainset=trainset,
        metric_name=config.metric_name,
        reflection_minibatch_size=DEFAULT_REFLECTION_MINIBATCH_SIZE,
    )
    resolved_budget = MaxTotalBudgetStopper.resolve_budget(
        auto=config.auto_budget,
        num_components=1,
        valset_size=len(valset),
        reflection_call_weight=reflection_weight,
    )
    logger.debug(
        f"  Budget resolved: {resolved_budget} "
        f"(auto_budget={config.auto_budget}, reflection_weight={reflection_weight})"
    )
    return resolved_budget, reflection_weight


@contextlib.contextmanager
def _patched_body_adapter() -> Iterator[None]:
    """Temporarily replace OptimizeAnythingAdapter with batched body variant."""
    saved_adapter_cls = optimize_anything_adapter.OptimizeAnythingAdapter
    saved_oa_ref = getattr(_oa_module, "OptimizeAnythingAdapter", None)
    optimize_anything_adapter.OptimizeAnythingAdapter = (  # type: ignore[misc]
        _BatchedBodyOptimizeAnythingAdapter
    )
    _oa_module.OptimizeAnythingAdapter = _BatchedBodyOptimizeAnythingAdapter  # type: ignore[misc]
    try:
        yield
    finally:
        optimize_anything_adapter.OptimizeAnythingAdapter = saved_adapter_cls  # type: ignore[misc]
        if saved_oa_ref is not None:
            _oa_module.OptimizeAnythingAdapter = saved_oa_ref  # type: ignore[misc]


def _dispatch_models(
    session: Session,
    config: BodyOptConfig,
    trainset: list[SnowflakeDataInst],
    valset: list[SnowflakeDataInst],
    metric_evaluator: Evaluator,
    resolved_budget: int,
    reflection_weight: int,
    run_id: str,
    dataset_load_start_perf: float,
    dataset_load_end_perf: float,
) -> list[ModelOptimizationResult]:
    """Dispatch parallel model workers and collect results."""
    engine_ctx, pool_ctx = resolve_engine(
        config.engine,
        session=session,
        models=config.models,
        max_concurrency=config.max_concurrency,
    )
    logger.debug(
        f"  Engine selected: {config.engine}. "
        f"Dispatching {len(config.models)} model worker(s): {config.models}"
    )

    common_kwargs: dict[str, Any] = dict(
        session=session,
        function_def=config.function_def,
        seed_body=config.seed_body,
        function_name=config.function_name,
        function_signature=config.function_signature,
        trainset=trainset,
        valset=valset,
        input_col_names=config.input_col_names,
        input_columns=config.input_columns,
        input_arg_names=config.input_arg_names,
        metric_evaluator=metric_evaluator,
        reflection_model=config.reflection_model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        resolved_budget=resolved_budget,
        reflection_weight=reflection_weight,
        metric_name=config.metric_name,
        test_table=config.test_table,
        label_column=config.label_column,
        dataset_expected_columns=config.dataset_expected_columns,
        run_id=run_id,
        aggregation_metric=config.aggregation_metric,
        experiment_name=config.experiment_name,
        dataset_load_start_perf=dataset_load_start_perf,
        dataset_load_end_perf=dataset_load_end_perf,
        reflection_backend=config.reflection_backend,
        run_dir=config.run_dir,
        fail_on_reflection_error=config.fail_on_reflection_error,
        # Shared across all workers → one global ITER_<N> sequence (schema v4).
        # Seeded from the experiment so a retry on the same experiment_name
        # resumes past existing ITER_<N> instead of colliding on ITER_1.
        run_counter=(
            seed_run_counter_from_experiment(session, config.experiment_name)
            if config.experiment_name
            else GlobalRunCounter()
        ),
    )

    model_results: list[ModelOptimizationResult] = []
    with (
        pool_ctx,
        engine_ctx,
        _patched_body_adapter(),
        ThreadPoolExecutor(max_workers=len(config.models)) as executor,
    ):
        future_to_model = {
            executor.submit(
                _run_single_model_body_optimization,
                model=model,
                **common_kwargs,
            ): model
            for model in config.models
        }

        for future in as_completed(future_to_model):
            model = future_to_model[future]
            try:
                model_output = future.result()
            except Exception as e:
                # Hard worker crash — the worker's own except handlers catch
                # normal failures and commit that model's runs with
                # STATUS='FAILED'.  We no longer write a ``<MODEL>_FAILED``
                # run; in this rare crash path the model's tracker is gone, so
                # log loudly rather than fabricate a synthetic failure run.
                logger.error("[MODEL_WORKER_CRASH] %s: %s", model, e, exc_info=True)
                model_output = ModelOptimizationResult(
                    model=model,
                    status="failed",
                    error=f"Future execution error: {e}",
                    elapsed_seconds=0,
                )
            model_results.append(model_output)
            logger.debug(
                f"  Model {model} done: "
                f"status={model_output.status}, "
                f"best_score={model_output.best_score}, "
                f"elapsed={model_output.elapsed_seconds}s"
            )

    return model_results


@dataclass
class _FrontierResult:
    """Result of frontier selection and test evaluation."""

    best_model: str
    best_body: str
    best_score: float
    best_score_source: str
    best_test_score: float | None
    best_val_score: float | None
    frontier_selection: list
    fc_test_scores: dict[int, float]


def _test_eval_frontier_candidates(
    session: Session,
    config: BodyOptConfig,
    metric_evaluator: Evaluator,
    frontier_selection: list,
    run_id: str,
) -> dict[int, float]:
    """Test-eval all frontier candidates and return per-index scores."""
    fc_test_scores: dict[int, float] = {}

    eval_metric_options = dict(metric_evaluator.kwargs)
    if metric_evaluator.metric_name == "llm_judge":
        eval_metric_options["scoring_mode"] = "binary"
    if config.dataset_expected_columns:
        eval_metric_options["expected_columns"] = config.dataset_expected_columns

    for fi, fc in enumerate(frontier_selection):
        try:
            model_suffix = re.sub(r"[^A-Za-z0-9]", "_", fc.model).upper()
            fc_temp_fn = build_temp_function_name(
                config.function_name,
                f"__OPT_TEST_FC_{model_suffix}_{fc.candidate_idx}",
            )
            fc_executor = _make_body_executor(
                session,
                config.function_def,
                fc.prompt_text,
                fc_temp_fn,
                udf_model=fc.model,
            )
            assert config.test_table is not None
            fc_eval = evaluate(
                session=session,
                function_name=fc_temp_fn,
                test_table=config.test_table,
                input_columns=config.input_columns,
                label_column=config.label_column,
                metric_name=metric_evaluator.metric_name,
                custom_metric_udf=metric_evaluator.custom_metric_udf,
                metric_options=eval_metric_options,
                model_name=fc.model,
                executor=fc_executor,
                run_id=run_id,
                split=f"test_frontier_{fi}",
                input_arg_names=config.input_arg_names,
            )
            fc_test_scores[fi] = fc_eval.score
            logger.info(
                "[FRONTIER_TEST_EVAL] %s candidate_%d: test_score=%.4f",
                fc.model,
                fc.candidate_idx,
                fc_eval.score,
            )
        except Exception as fc_err:
            logger.warning(
                "[FRONTIER_TEST_EVAL_ERROR] %s candidate_%d: %s",
                fc.model,
                fc.candidate_idx,
                fc_err,
                exc_info=True,
            )
            # Continue — score remaining candidates before deciding to fail.

    if not fc_test_scores:
        raise RuntimeError(
            f"Frontier test-eval failed for all {len(frontier_selection)} candidate(s). "
            "See logged [FRONTIER_TEST_EVAL_ERROR] entries for details."
        )

    return fc_test_scores


def _commit_deferred_model_runs(
    session: Session,
    experiment_name: str,
    model_results: list[ModelOptimizationResult],
) -> None:
    """Commit every deferred SEED/ITER run across completed models.

    Per-model saves ran with ``defer_commit=True`` so the cross-model frontier
    stamp could add ``is_frontier``/``test_score`` onto the lineage runs before
    they were committed (Snowflake rejects ADD METRICS after commit).  This
    drains each completed model's ``pending_commit_runs`` and commits them
    (fault-tolerant, deduped), clearing the marker so a repeat call is a no-op.
    """
    pending: list[str] = []
    for model_result in model_results:
        if model_result.status == "completed" and model_result.pending_commit_runs:
            pending.extend(model_result.pending_commit_runs)
            model_result.pending_commit_runs = None
    if pending:
        commit_runs(session, experiment_name, pending)


def _select_best_from_frontier(
    session: Session,
    config: BodyOptConfig,
    model_results: list[ModelOptimizationResult],
    metric_evaluator: Evaluator,
    run_id: str,
) -> _FrontierResult:
    """Build frontier, test-eval candidates, and select overall best.

    Raises:
        RuntimeError: If frontier selection or test-eval fails.

    """
    # The deferred SEED/ITER runs are committed in the ``finally`` below,
    # whether this function returns normally or raises.  On the happy path the
    # commit follows the frontier stamp; on failure it is the safety net that
    # keeps the runs from lingering in RUNNING (they still carry valid
    # valset/cost metrics, just without the frontier stamp).
    try:
        # Build frontier candidates directly from typed ModelOptimizationResult
        # objects. We do NOT use build_frontier_from_pareto (which expects
        # list[dict] with "_pareto_candidates" keys and destroys NamedTuples
        # via dataclasses.asdict()).
        all_frontier_candidates: list[FrontierCandidate] = []
        seed_val_score: float | None = None
        # Schema v4 uses ONE shared ``SEED`` run across models; every completed
        # model's Pareto set includes a "SEED" candidate (its own seed eval).
        # De-dup by run name so the cross-model frontier carries a single seed
        # point.  ITER_<N> names are globally unique, so this only collapses
        # the seed.
        seen_run_names: set[str] = set()

        for mr in model_results:
            if mr.status != "completed":
                continue
            if seed_val_score is None:
                seed_val_score = mr.seed_val_score

            if mr.pareto_candidates is None:
                raise RuntimeError(
                    f"Model '{mr.model}' completed but has no pareto_candidates. "
                    "This indicates a bug in compute_pareto_candidates or "
                    "missing cost data in models.json."
                )

            for pc in mr.pareto_candidates:
                if pc.estimated_cost is None:
                    raise RuntimeError(
                        f"Candidate '{pc.run_name}' for model '{pc.model}' "
                        "has no estimated_cost. Cannot build Pareto frontier "
                        "without cost data."
                    )
                if pc.run_name in seen_run_names:
                    continue
                seen_run_names.add(pc.run_name)
                all_frontier_candidates.append(
                    FrontierCandidate(
                        model=pc.model,
                        # ``candidate_idx`` is vestigial under global naming —
                        # frontier candidates are identified by ``run_name`` and
                        # stamped in place.  Kept at 0 for the NamedTuple field.
                        candidate_idx=0,
                        estimated_cost=pc.estimated_cost,
                        score=pc.score,
                        prompt_text=pc.prompt_text,
                        run_name=pc.run_name,
                    )
                )

        frontier_selection = select_frontier_candidates(
            all_frontier_candidates,
            max_candidates=config.max_frontier_candidates,
            seed_score=seed_val_score,
        )
        if not frontier_selection:
            completed_count = sum(1 for mr in model_results if mr.status == "completed")
            raise RuntimeError(
                f"No Pareto frontier candidates produced from "
                f"{completed_count} completed model(s). "
                "This indicates a bug in cost estimation or candidate data."
            )

        # Post-selection test-eval of ALL frontier candidates.  Validation
        # scores drove the hypervolume selection above; the test set is used
        # purely to report generalisation for each selected candidate.
        fc_test_scores: dict[int, float] = {}
        if config.test_table:
            # _test_eval_frontier_candidates raises RuntimeError if all fail.
            fc_test_scores = _test_eval_frontier_candidates(
                session=session,
                config=config,
                metric_evaluator=metric_evaluator,
                frontier_selection=frontier_selection,
                run_id=run_id,
            )
            # Attach test scores onto each selected candidate so its source
            # SEED/ITER run carries BOTH valset_score and test_score.
            frontier_selection = [
                fc._replace(test_score=fc_test_scores.get(fi))
                for fi, fc in enumerate(frontier_selection)
            ]

        # Pick overall best from the frontier set.  Prefer test scores when
        # available; otherwise fall back to validation scores.
        has_test = bool(fc_test_scores)

        def _authoritative_score(c: FrontierCandidate) -> float:
            if has_test and c.test_score is not None:
                return c.test_score
            return c.score

        best_fc = max(frontier_selection, key=_authoritative_score)
        overall_best_model = best_fc.model
        overall_best_body = best_fc.prompt_text
        overall_best_score = _authoritative_score(best_fc)
        overall_best_score_source = "test" if has_test else "validation"
        overall_best_test_score = best_fc.test_score if has_test else None

        # Single pass over model_results: the winning model's scores, the
        # seed's avg output chars, and the first completed model (SEED commit
        # anchor).
        overall_best_val_score = None
        winning_mr: ModelOptimizationResult | None = None
        seed_avg_output_chars: int | None = None
        first_completed: ModelOptimizationResult | None = None
        for mr in model_results:
            if mr.status != "completed":
                continue
            if first_completed is None:
                first_completed = mr
            if mr.model == overall_best_model:
                overall_best_val_score = mr.best_val_score
                if overall_best_test_score is not None:
                    mr.best_test_score = overall_best_test_score
                winning_mr = mr
            if seed_avg_output_chars is None and mr.avg_output_chars is not None:
                seed_avg_output_chars = mr.avg_output_chars

        if config.experiment_name:
            # Schema v4: write the SINGLE consolidated SEED run (RUNNING) with
            # the input function's model, per-model aggregate stats + summed
            # global totals, and shared seed eval scores.  Written BEFORE the
            # frontier stamp so is_frontier/test_score can land on it when the
            # seed is on the frontier; committed by the finally.
            seed_fc = next(
                (fc for fc in all_frontier_candidates if fc.run_name == "SEED"), None
            )
            per_model_stats = build_per_model_stats(model_results, getattr)
            # The seed IS the input function, so its model is that function's
            # own model (extracted from the unmodified seed body).  Fall back to
            # a completed model's name if the body has no readable model=> (real
            # AI-function bodies always do; this guards odd inputs/tests).
            try:
                seed_model = _extract_model_from_body_ddl(
                    config.seed_body, config.function_name
                )
            except ValueError:
                seed_model = next(
                    (mr.model for mr in model_results if mr.status == "completed"),
                    "",
                )
            write_consolidated_seed(
                session,
                config.experiment_name,
                function_name=config.function_name,
                seed_prompt=config.seed_body,
                model=seed_model,
                per_model_stats=per_model_stats,
                summed_totals=sum_seed_totals(per_model_stats),
                avg_output_chars=seed_avg_output_chars,
                seed_val_score=seed_val_score,
                seed_estimated_cost=(seed_fc.estimated_cost if seed_fc else None),
                score_source="validation",
                metric_name=config.metric_name,
                custom_metric_udf=config.custom_metric_udf,
            )
            # Route the SEED commit through the deferred-commit finally, on the
            # first completed model's pending list.
            if first_completed is not None:
                if first_completed.pending_commit_runs is None:
                    first_completed.pending_commit_runs = []
                first_completed.pending_commit_runs.append("SEED")

            # Stamp the cross-model frontier onto the SELECTED candidates'
            # source SEED/ITER runs (is_frontier + test_score) IN PLACE.  The
            # runs are RUNNING (deferred commit) so ADD METRICS is accepted;
            # the commit happens in the finally.
            stamp_frontier_metrics_on_runs(
                session,
                config.experiment_name,
                frontier_selection=frontier_selection,
            )

            # Upload run_dir + eval-detail artifacts to the overall-best run.
            if best_fc.run_name and winning_mr is not None:
                upload_winning_artifacts(
                    session,
                    config.experiment_name,
                    best_fc.run_name,
                    run_dir=winning_mr.run_dir,
                    seed_eval_details=winning_mr.seed_eval_details,
                    upload_run_dir=config.upload_run_dir,
                )

        return _FrontierResult(
            best_model=overall_best_model,
            best_body=overall_best_body,
            best_score=overall_best_score,
            best_score_source=overall_best_score_source,
            best_test_score=overall_best_test_score,
            best_val_score=overall_best_val_score,
            frontier_selection=frontier_selection,
            fc_test_scores=fc_test_scores,
        )
    finally:
        if config.experiment_name:
            _commit_deferred_model_runs(session, config.experiment_name, model_results)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_body_optimization(
    session: Session,
    function_name: str,
    training_table: str,
    label_column: str,
    input_columns: list,
    metric_name: str,
    models: list,
    reflection_model: str,
    test_table: str | None = None,
    auto_budget: BudgetType = DEFAULT_AUTO_BUDGET,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    metric_options: dict | None = None,
    custom_metric_udf: str | None = None,
    run_id: str | None = None,
    aggregation_metric: str | None = None,
    experiment_name: str | None = None,
    engine: EngineType = "default",
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    reflection_backend: Literal[
        "ai_complete", "agent_run", "agent_run_single_session"
    ] = "ai_complete",
    max_frontier_candidates: int = DEFAULT_MAX_FRONTIER_CANDIDATES,
    run_dir: str | None = None,
    input_arg_names: list[str] | None = None,
    upload_run_dir: bool = True,
    query_text: str | None = None,
    create_experiment_if_missing: bool = True,
    fail_on_reflection_error: bool = False,
) -> dict:
    """Run function body optimization using GEPA ``optimize_anything``.

    This function mirrors the parameter list and output format of
    ``run_optimization`` in ``snow_gepa_optimize`` so the caller sees a
    consistent interface regardless of ``optimize_mode``.

    Args:
        session: Snowpark session.
        function_name: Fully qualified name of the AI function to optimize.
        training_table: Table with training data (split into valset + trainset).
        label_column: Column containing expected outputs.
        input_columns: List of input column names.
        metric_name: Metric to use (exact_match, fuzzy_match, redaction_match, etc.).
        models: List of models to optimize with (required).
        reflection_model: Model used for reflection (required).
        test_table: Optional held-out test table for final evaluation only.
        auto_budget: Budget preset — ``"ultra-light"``, ``"light"``,
            ``"medium"``, or ``"heavy"`` (``"demo"`` is a back-compat alias
            for ``"ultra-light"``).
        validation_fraction: Fraction of training data used for validation.
        temperature: LLM sampling temperature.
        max_tokens: Maximum tokens in the LLM response.
        metric_options: Metric-specific options (e.g. threshold for fuzzy_match).
        custom_metric_udf: Fully qualified name of a custom metric UDF.
        run_id: Unique identifier for this run; auto-generated if not provided.
        aggregation_metric: Optional batch-level metric for selecting the best
            candidate (e.g. ``"accuracy"``, ``"f1-score"``).
        experiment_name: If provided, optimization results are persisted to a
            Snowflake Experiment object.
        engine: Optimizer engine variant to use.
        max_concurrency: Maximum number of models optimized concurrently.
        reflection_backend: Which Snowflake function to use for the
            reflection LLM call.  ``"ai_complete"`` (default) uses
            ``AI_COMPLETE`` via :class:`SnowflakeLLM`.  ``"agent_run"`` uses
            ``SNOWFLAKE.CORTEX.AGENT_RUN`` with ``web_search`` + ``sql_exec``
            tools via :class:`SnowflakeAgentLM` — selected when
            ``optimize_mode == "body_agent"``.  ``"agent_run_single_session"``
            uses the same agent LM but keeps its message history across every
            GEPA reflection call so the agent can build on its prior
            reasoning — selected when ``optimize_mode ==
            "body_agent_single_session"``.
        max_frontier_candidates: Maximum number of Pareto-frontier candidates
            to retain and report.
        run_dir: Optional directory for persisting per-run artifacts and logs.
        input_arg_names: Optional AI-function parameter name for each entry in
            ``input_columns`` (same length/order, already resolved from any
            ``$N`` markers). When provided, dataset columns are aliased to these
            parameter names so candidates bind by name; ``None`` (default)
            preserves the legacy behavior where column names must match the
            function's parameter names.
        upload_run_dir: When True (default), the GEPA ``run_dir`` status/state
            artifacts are uploaded to the winning run's experiment stage. Set
            False (spec-driven / YAML handler) to keep those internal files out
            of the experiment.
        query_text: Inline scalar SQL expression for a builtin AI function. When
            provided, the candidate program is seeded from this expression
            instead of introspecting a function DDL via ``DESCRIBE FUNCTION``.
        create_experiment_if_missing: When True (default), the experiment is
            created (``CREATE EXPERIMENT IF NOT EXISTS``) before runs are added.
            Set False by the spec-driven / EXECUTE EXPERIMENT path, where the
            experiment is created by the DDL layer beforehand and this SPROC
            only attaches ``SEED`` / ``ITER_<N>`` runs to it.
        fail_on_reflection_error: When True, a reflection call that keeps failing
            after retries is fatal for the model: it stops and its runs are
            committed FAILED with the reflection error surfaced on them, instead
            of GEPA swallowing the error and the model finishing SUCCEEDED. Set
            only by the spec-driven / EXECUTE EXPERIMENT path; defaults to False
            (standalone OPTIMIZE_AI_FUNCTION behavior unchanged).

    """
    start_time = time.time()
    logger.debug(
        f"run_body_optimization() starting: func={function_name}, "
        f"models={models}, engine={engine}, budget={auto_budget}, "
        f"reflection_model={reflection_model}"
    )

    try:
        # Validate & prepare config — raises ValueError on bad user input
        config = _validate_and_prepare_config(
            session=session,
            function_name=function_name,
            training_table=training_table,
            label_column=label_column,
            input_columns=input_columns,
            metric_name=metric_name,
            models=models,
            reflection_model=reflection_model,
            test_table=test_table,
            auto_budget=auto_budget,
            validation_fraction=validation_fraction,
            temperature=temperature,
            max_tokens=max_tokens,
            metric_options=metric_options,
            custom_metric_udf=custom_metric_udf,
            run_id=run_id,
            aggregation_metric=aggregation_metric,
            experiment_name=experiment_name,
            engine=engine,
            max_concurrency=max_concurrency,
            reflection_backend=reflection_backend,
            max_frontier_candidates=max_frontier_candidates,
            run_dir=run_dir,
            input_arg_names=input_arg_names,
            upload_run_dir=upload_run_dir,
            query_text=query_text,
            create_experiment_if_missing=create_experiment_if_missing,
            fail_on_reflection_error=fail_on_reflection_error,
        )

        # Load dataset & build evaluator — raises RuntimeError/ValueError on failure
        trainset, valset, metric_evaluator, _dataset_load_t0, _dataset_load_t1 = (
            _load_and_split_dataset(session, config)
        )

        # Budget
        resolved_budget, reflection_weight = _compute_optimization_budget(
            config=config, trainset=trainset, valset=valset
        )

        # Dispatch model workers
        model_results = _dispatch_models(
            session=session,
            config=config,
            trainset=trainset,
            valset=valset,
            metric_evaluator=metric_evaluator,
            resolved_budget=resolved_budget,
            reflection_weight=reflection_weight,
            run_id=config.run_id,
            dataset_load_start_perf=_dataset_load_t0,
            dataset_load_end_perf=_dataset_load_t1,
        )

        # Frontier selection & test evaluation
        completed_models = [mr for mr in model_results if mr.status == "completed"]
        if not completed_models:
            failed_errors = [mr.error for mr in model_results if mr.error]
            raise RuntimeError(
                f"All {len(model_results)} model(s) failed. "
                f"Errors: {'; '.join(str(e) for e in failed_errors[:3])}"
            )

        # _select_best_from_frontier raises RuntimeError on failure.  It owns
        # committing the deferred SEED/ITER runs in its own finally (stamping
        # the cross-model frontier first on the happy path), so no matter how
        # it exits the runs never linger in RUNNING state.
        frontier = _select_best_from_frontier(
            session=session,
            config=config,
            model_results=model_results,
            metric_evaluator=metric_evaluator,
            run_id=config.run_id,
        )

        elapsed = round(time.time() - start_time, 2)
        logger.debug(
            f"  run_body_optimization complete: best_model={frontier.best_model}, "
            f"best_score={frontier.best_score if frontier.best_score >= 0 else None}, "
            f"total_elapsed={elapsed}s"
        )

        # Build output
        output: dict = {
            "status": "completed",
            "run_id": config.run_id,
            "elapsed_seconds": elapsed,
            "function_name": config.function_name,
            "seed_body": config.seed_body,
            "best_body": frontier.best_body,
            "best_ddl": config.function_def.render_create_ddl(body=frontier.best_body),
            "metric": config.metric_name,
            "training_table": config.training_table,
            "trainset_size": len(trainset),
            "valset_size": len(valset),
            "validation_fraction": config.validation_fraction,
            "auto_budget": config.auto_budget,
            "resolved_budget": resolved_budget,
            "models": config.models,
            "model_results": [dataclasses.asdict(mr) for mr in model_results],
            "overall_best_model": frontier.best_model,
            "overall_best_prompt": frontier.best_body,
            "overall_best_val_score": frontier.best_val_score,
            "overall_best_test_score": frontier.best_test_score,
            "overall_best_score": (
                frontier.best_score if frontier.best_score >= 0 else None
            ),
            "overall_best_score_source": frontier.best_score_source,
            "frontier_candidates": [
                {
                    "model": fc.model,
                    "candidate_idx": fc.candidate_idx,
                    "estimated_cost": fc.estimated_cost,
                    "score": fc.score,
                    "test_score": frontier.fc_test_scores.get(fi),
                    "prompt": fc.prompt_text,
                }
                for fi, fc in enumerate(frontier.frontier_selection)
            ],
        }

        if config.aggregation_metric:
            output["aggregation_metric"] = config.aggregation_metric
        if config.dataset_expected_columns:
            output["expected_columns"] = config.dataset_expected_columns
        if config.test_table:
            output["test_table"] = config.test_table

        # Task cleanup (non-critical, best-effort)
        if config.run_id and config.run_id.startswith("ai_func_opt_"):
            try:
                parts = config.function_name.split("(")[0].split(".")
                if len(parts) >= 3:
                    task_fqn = f"{parts[0]}.{parts[1]}.{config.run_id}"
                    session.sql(f"DROP TASK IF EXISTS {task_fqn}").collect()
            except Exception as e:
                logger.debug("Task cleanup failed (non-critical): %s", e)

        return output

    except ValueError as e:
        # User input error (bad parameters, missing columns, unknown metric, etc.)
        return {"status": "failed", "error": str(e)}
    except Exception as e:
        # Internal error (data issue, Snowflake session error, optimizer bug, etc.)
        logger.error("[OPTIMIZATION_FATAL] %s", e, exc_info=True)
        return {"status": "failed", "error": str(e)}


def _body_mode_handler(**kwargs: Any) -> dict:
    """Adapter: inject reflection_backend for the production body mode."""
    kwargs["reflection_backend"] = "ai_complete"
    return run_body_optimization(**kwargs)
