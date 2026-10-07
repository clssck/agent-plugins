# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Prompt-mode GEPA optimization for Snowflake AI functions.

This module provides ``run_prompt_optimization``, the handler for
``optimize_mode="prompt"`` which optimizes only the system prompt while
preserving the function body. Extracted from ``optimize.py`` to reduce
inline SPROC bundle size (prompt mode is not used in the inline/task path).
"""

import contextlib
import json
import logging
import re
import tempfile
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Literal, cast

from snowflake.snowpark import Session

import gepa as gepa_pkg
from gepa import NoImprovementStopper
from gepa.core.result import GEPAResult
from snowflake_ai_optimize.core.evaluation import (
    evaluate,
)
from snowflake_ai_optimize.core.experiment import (
    FrontierCandidate,
    GlobalRunCounter,
    build_frontier_from_pareto,
    commit_runs,
    create_experiment,
    get_experiment_run_names,
    seed_run_counter_from_experiment,
    select_frontier_candidates,
    stamp_frontier_metrics_on_runs,
)
from snowflake_ai_optimize.core.metrics.utils import (
    get_table_column_names,
    parse_metric_options,
    resolve_expected_column,
    validate_input_columns,
)
from snowflake_ai_optimize.core.scorer import Evaluator, ScoredExample
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
from snowflake_ai_optimize.core.temp_ai_function import TempAIFunction
from snowflake_ai_optimize.core.timing import (
    TimingTracker,
    clear_evaluate_hooks,
    set_active_tracker,
    set_evaluate_hooks,
)
from snowflake_ai_optimize.core.types import SnowflakeDataInst
from snowflake_ai_optimize.gepa.adapter import (
    SnowflakeAdapter,
    SnowflakeLLM,
    load_dataset,
)
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

# Re-export constants needed by prompt mode
DEFAULT_REFLECTION_MINIBATCH_SIZE = 10
DEFAULT_AUTO_BUDGET: Literal["ultra-light", "light", "medium", "heavy", "demo"] = (
    "ultra-light"
)
DEFAULT_VALIDATION_FRACTION = 0.5
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192
DEFAULT_MAX_FRONTIER_CANDIDATES = 7
DEFAULT_PERFECT_SCORE = 1.0
DEFAULT_MAX_MERGE_INVOCATIONS = 5
DEFAULT_REFLECTION_CALL_WEIGHT = 1


def optimize(
    seed_candidate: dict[str, str],
    trainset: list[SnowflakeDataInst],
    evaluator: Callable[[SnowflakeDataInst, str], ScoredExample],
    session: Session,
    valset: list[SnowflakeDataInst],
    function_name: str,
    input_columns: list[str],
    model: str,
    reflection_model: str,
    reflection_lm: SnowflakeLLM,
    max_metric_calls: int,
    reflection_call_weight: int,
    function_def: FunctionDefinition | None = None,
    temp_function_name: str = "",
    reflection_minibatch_size: int = DEFAULT_REFLECTION_MINIBATCH_SIZE,
    skip_perfect_score: bool = True,
    perfect_score: float = DEFAULT_PERFECT_SCORE,
    candidate_selection_strategy: Literal[
        "pareto", "current_best", "epsilon_greedy"
    ] = "pareto",
    use_merge: bool = False,
    max_merge_invocations: int = DEFAULT_MAX_MERGE_INVOCATIONS,
    no_improvement_patience: int | None = None,
    seed: int = 0,
    log_dir: str | None = None,
    cache_evaluation: bool = True,
    file_type_params: list[str] | None = None,
    stage_name: str | None = None,
    tracker: TimingTracker | None = None,
    extra_callbacks: list | None = None,
    input_arg_names: list[str] | None = None,
    eval_detail_buffer: dict | None = None,
) -> GEPAResult:
    """Optimizes AI functions using the GEPA algorithm with Snowflake AI functions.

    The stopping condition uses a combined budget that accounts for both
    metric evaluation calls and reflection LLM calls, so that optimization
    stops when the total of both exceeds the resolved budget.

    Args:
        seed_candidate: Initial candidate mapping component names to prompt
            text. Example: {"instruction": "You are a helpful assistant..."}
        trainset: Training examples for reflection (learning from failures).
            Each example should have 'inputs' (dict) and 'answer' keys.
            Typically 1/3 of your labeled data.
        evaluator: Function to evaluate a response. Takes (data, response) and
            returns ScoredExample with score and feedback.
        session: Snowflake Snowpark session.
        valset: Validation examples for scoring candidates. Typically 2/3 of
            your labeled data. Must be provided (no default).
        function_name: Fully qualified UDF name (DB.SCHEMA.FUNC) to optimize.
        input_columns: List of input column names that map to UDF parameters.
        model: Snowflake Cortex model for task execution.
        reflection_model: Model for reflection/mutation.
        reflection_lm: SnowflakeLLM instance for reflection calls. Its
            call_count is used by the budget stopper to track reflection cost.
        max_metric_calls: Pre-resolved budget limit (weighted total of metric
            and reflection calls). Computed by
            ``MaxTotalBudgetStopper.resolve_budget``.
        reflection_call_weight: Weight of one reflection call relative to one
            metric call, from ``MaxTotalBudgetStopper.estimate_reflection_weight``.
        function_def: Introspected definition of the original function, used
            to create temp functions (model/prompt swapped into its body).
        temp_function_name: Fully qualified name for the temp function.
        reflection_minibatch_size: Examples per reflection step. Default 3.
        skip_perfect_score: Skip reflection when all scores are perfect.
        perfect_score: Score threshold considered perfect. Default 1.0.
        candidate_selection_strategy: How to select parent candidate.
        use_merge: Whether to use merge-based optimization. Default False.
        max_merge_invocations: Maximum merge operations. Default 5.
        no_improvement_patience: Stop optimization if no improvement after this
            many iterations. Set to None to disable. Default None.
        seed: Random seed for reproducibility. Default 0.
        log_dir: Directory for saving logs (optional).
        cache_evaluation: Whether to cache candidate evaluations. Default True.
        file_type_params: Optional list of file-type parameters passed to the
            adapter for file-based inputs.
        stage_name: Optional Snowflake stage name for file-based inputs.
        tracker: Optional TimingTracker for recording per-phase timing.
        extra_callbacks: Optional list of extra GEPA callbacks to register.
        input_arg_names: Optional AI-function parameter name for each entry in
            ``input_columns`` (same length/order, already resolved). When
            provided, the adapter reads each row's ``inputs`` dict by parameter
            name (the key ``load_dataset`` used); ``None`` (default) keeps the
            legacy behavior of keying by column name.
        eval_detail_buffer: Optional dict the adapter fills with per-candidate
            per-row eval detail (keyed by ``candidate_detail_key``). Shared with
            the experiment tracker, which drains it into
            ``eval_detail.json`` for each persisted run.

    Returns:
        GEPAResult containing:
            - candidates: All proposed candidates.
            - val_aggregate_scores: Per-candidate average validation scores.
            - best_candidate: The highest-scoring candidate.
            - best_idx: Index of best candidate.

    """
    reflection_model = reflection_model or model

    # Name each input column is presented under to candidates. With argument
    # binding these are the (already-resolved) AI-function parameter names that
    # ``load_dataset`` keyed each row's ``inputs`` dict by (see adapter.py); the
    # adapter reads ``inputs`` by these keys. ``None`` keeps behavior identical.
    present_as = input_arg_names or input_columns

    if function_def is None:
        raise ValueError("function_def is required to run prompt optimization")

    adapter = SnowflakeAdapter(
        session=session,
        evaluator=evaluator,
        function_name=function_name,
        input_columns=present_as,
        model=model,
        function_def=function_def,
        temp_function_name=temp_function_name,
        file_type_params=file_type_params,
        stage_name=stage_name,
        full_valset_size=len(valset),
        eval_detail_buffer=eval_detail_buffer,
    )

    stopper = MaxTotalBudgetStopper(
        reflection_lm,
        max_budget=max_metric_calls,
        reflection_call_weight=reflection_call_weight,
    )

    stop_callbacks: list[Callable] = []
    if tracker is not None:

        def _iteration_marker(_state: Any) -> bool:
            tracker.mark_iteration()
            return False

        stop_callbacks.append(_iteration_marker)
    stop_callbacks.append(stopper)
    if no_improvement_patience is not None:
        stop_callbacks.append(
            NoImprovementStopper(
                max_iterations_without_improvement=no_improvement_patience
            )
        )

    # Always pass a safe logger to prevent GEPA from creating a file-based
    # Logger that mutates global sys.stdout/stderr — unsafe when multiple
    # models run concurrently via ThreadPoolExecutor.
    gepa_logger = PythonLoggingAdapter(logger)

    return gepa_pkg.optimize(
        seed_candidate=seed_candidate,
        trainset=trainset,
        valset=valset,
        adapter=adapter,
        reflection_lm=reflection_lm,
        candidate_selection_strategy=candidate_selection_strategy,
        skip_perfect_score=skip_perfect_score,
        reflection_minibatch_size=reflection_minibatch_size,
        perfect_score=perfect_score,
        use_merge=use_merge,
        max_merge_invocations=max_merge_invocations,
        max_metric_calls=None,
        stop_callbacks=stop_callbacks,
        logger=gepa_logger,
        seed=seed,
        run_dir=log_dir,
        cache_evaluation=cache_evaluation,
        # ``extra_callbacks`` is the optimizer-supplied list of GEPA
        # lifecycle callbacks; today only used to plumb a
        # ``RejectedCandidateCollector`` through so rejected proposals
        # land in the Experiment object.  ``None`` disables (matches
        # GEPA's default).
        callbacks=extra_callbacks,
    )


def extract_prompt_from_ddl_string(ddl: str, function_name: str = "") -> str:
    """Extract the system prompt from a function body (or DDL) string.

    Looks for the pattern: 'role', 'system', 'content', '<prompt>'

    Operates directly on the text passed in — callers pass
    ``FunctionDefinition.body`` (the raw body from ``describe_function``,
    where SQL-level ``''`` escaping inside string literals is preserved).
    The captured group is then unescaped (``''`` -> ``'``).
    """
    prompt_pattern = r"'role'\s*,\s*'system'\s*,\s*'content'\s*,\s*'((?:[^']|'')*)'"
    match = re.search(prompt_pattern, ddl, re.DOTALL)

    if not match:
        raise ValueError(
            f"Could not extract system prompt from DDL for function: {function_name}. "
            f"Expected hardcoded system prompt in OBJECT_CONSTRUCT('role', 'system', 'content', '...')."
        )

    return match.group(1).replace("''", "'")


def extract_model_from_ddl_string(ddl: str, function_name: str = "") -> str:
    """Extract the model name from a function body (or DDL) string.

    Looks for the pattern: model=>'model_name'

    Operates directly on the text passed in — callers pass
    ``FunctionDefinition.body`` (the raw body from ``describe_function``).
    """
    model_pattern = r"model\s*=>\s*'([^']*)'"
    match = re.search(model_pattern, ddl, re.IGNORECASE)

    if not match:
        raise ValueError(
            f"Could not extract model name from DDL for function: {function_name}. "
            f"Expected hardcoded model in AI_COMPLETE(model=>'...')."
        )

    return match.group(1)


@dataclass
class _SeedTestEvalResult:
    """Result of evaluating the seed candidate on a held-out test set."""

    seed_score: float
    seed_eval_details: list
    num_examples: int


def _score_seed_on_test_set(
    session: Session,
    function_def: FunctionDefinition,
    function_name: str,
    model: str,
    seed_prompt: str,
    test_table: str,
    input_columns: list[str],
    label_column: str,
    evaluator: "Evaluator",
    expected_columns: list[str] | None,
    run_id: str,
    input_arg_names: list[str] | None = None,
) -> _SeedTestEvalResult:
    """Evaluate only the seed prompt on the held-out test set.

    Optimized candidates are test-eval'd post-selection in the orchestrator
    so the test set never influences model selection.
    """
    eval_metric_options = dict(evaluator.kwargs) if hasattr(evaluator, "kwargs") else {}
    if evaluator.metric_name == "llm_judge":
        eval_metric_options["scoring_mode"] = "binary"
    if expected_columns:
        eval_metric_options["expected_columns"] = expected_columns

    test_temp_fn = build_temp_function_name(function_name, "__OPT_TEST")

    seed_fn = TempAIFunction(
        session=session,
        function_def=function_def,
        temp_function_name=test_temp_fn,
        candidate_model=model,
        candidate_prompt=seed_prompt,
    )
    seed_eval = evaluate(
        session=session,
        function_name=test_temp_fn,
        test_table=test_table,
        input_columns=input_columns,
        label_column=label_column,
        metric_name=evaluator.metric_name,
        custom_metric_udf=evaluator.custom_metric_udf,
        metric_options=eval_metric_options,
        model_name=model,
        executor=seed_fn.call_rows,
        run_id=run_id,
        split="test_seed",
        input_arg_names=input_arg_names,
    )

    test_count = session.sql(f"SELECT COUNT(*) FROM {test_table}").collect()[0][0]

    return _SeedTestEvalResult(
        seed_score=seed_eval.score,
        seed_eval_details=seed_eval.details,
        num_examples=test_count,
    )


def _run_single_model_optimization(
    model: str,
    session: Session,
    seed_candidate: dict,
    trainset: list,
    valset: list,
    evaluator: "Evaluator",
    resolved_budget: int,
    reflection_call_weight: int,
    reflection_model: str,
    temperature: float,
    max_tokens: int,
    function_name: str,
    input_columns: list,
    test_table: str | None,
    label_column: str,
    expected_columns: list[str] | None,
    seed_prompt: str,
    run_id: str,
    aggregation_metric: str | None = None,
    function_def: FunctionDefinition | None = None,
    file_type_params: list[str] | None = None,
    stage_name: str | None = None,
    experiment_name: str | None = None,
    dataset_load_start_perf: float | None = None,
    dataset_load_end_perf: float | None = None,
    run_dir: str | None = None,
    input_arg_names: list[str] | None = None,
    run_counter: GlobalRunCounter | None = None,
) -> dict:
    """Run optimization for a single model. Designed to be called in parallel."""
    model_start_time = time.time()

    # Shared across all parallel model workers so every model's ITER runs draw
    # from one global sequence.  A local fallback keeps direct/unit-test calls
    # (single worker, no shared counter) functional.
    if run_counter is None:
        run_counter = GlobalRunCounter()

    if run_dir:
        # Persistent run_dir provided — use per-model subdirectory directly.
        import os

        model_run_dir = os.path.join(run_dir, re.sub(r"[^A-Za-z0-9]", "_", model))
        os.makedirs(model_run_dir, exist_ok=True)
        log_dir_ctx: AbstractContextManager[str | None] = contextlib.nullcontext(
            model_run_dir
        )
    else:
        log_dir_ctx = (
            tempfile.TemporaryDirectory(prefix="gepa_prompt_")
            if experiment_name
            else contextlib.nullcontext()
        )

    with log_dir_ctx as gepa_log_dir:
        temp_fn = build_temp_function_name(function_name, "__OPT_TEMP")

        reflection_lm = SnowflakeLLM(
            session=session,
            model=reflection_model or model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        tracker = TimingTracker()
        set_active_tracker(tracker)
        # Backfill the dataset_load phase event using pre-tracker perf timestamps.
        if dataset_load_start_perf is not None and dataset_load_end_perf is not None:
            tracker.add_phase(
                "dataset_load",
                dataset_load_start_perf,
                dataset_load_end_perf,
                label="load_dataset",
            )
        # Track "gepa_thinking" gaps — wall-time GEPA spends in Python
        # between consecutive evaluate calls (candidate selection, Pareto
        # frontier update, reflection-trigger decision). Thread-local hooks
        # avoid race conditions between concurrent model workers.
        _last_prompt_eval_end: list[float | None] = [None]
        _gepa_loop_start_ref_p: list[float] = [0.0]

        def _pre_evaluate() -> None:
            _t_call = time.perf_counter()
            if _last_prompt_eval_end[0] is not None:
                tracker.add_phase(
                    "gepa_thinking",
                    _last_prompt_eval_end[0],
                    _t_call,
                    label="between_evals",
                )
            elif _gepa_loop_start_ref_p[0] > 0:
                tracker.add_phase(
                    "gepa_thinking",
                    _gepa_loop_start_ref_p[0],
                    _t_call,
                    label="gepa_init",
                )

        def _post_evaluate() -> None:
            _last_prompt_eval_end[0] = time.perf_counter()

        set_evaluate_hooks(pre=_pre_evaluate, post=_post_evaluate)

        # Anchor for the high-level "gepa_loop" phase so the per-thread
        # Gantt timeline shows one big block covering optimize() with
        # the per-call metric/reflection events nested inside.
        _gepa_loop_t0 = time.perf_counter()
        _gepa_loop_start_ref_p[0] = _gepa_loop_t0
        # Collect every GEPA-rejected proposal (reflective + merge) so we
        # can persist them as ``{MODEL}_REJECTED_N`` runs alongside the
        # SEED / ITER_N / BEST runs.  The collector is per-thread (one
        # per model) and read after optimization completes; it only
        # appends — there are no concurrency concerns within a single
        # optimize() call.
        rejected_collector = RejectedCandidateCollector()
        # Shared per-worker eval-detail buffer: the adapter (built inside
        # ``optimize``) fills it; the tracker (built here, before the adapter)
        # drains it into ``eval_detail.json`` on each persisted run.
        eval_detail_buffer: dict = {}
        progressive_tracker: ProgressiveExperimentTracker | None = None
        if experiment_name:
            progressive_tracker = ProgressiveExperimentTracker(
                session=session,
                experiment_name=experiment_name,
                model=model,
                function_name=function_name,
                run_counter=run_counter,
                eval_detail_buffer=eval_detail_buffer,
            )
        _extra_callbacks: list = [rejected_collector]
        if progressive_tracker is not None:
            _extra_callbacks.append(progressive_tracker)
        try:
            try:
                result = optimize(
                    seed_candidate=seed_candidate,
                    trainset=trainset,
                    evaluator=evaluator,
                    session=session,
                    valset=valset,
                    function_name=function_name,
                    input_columns=input_columns,
                    model=model,
                    reflection_model=reflection_model or model,
                    reflection_lm=reflection_lm,
                    max_metric_calls=resolved_budget,
                    reflection_call_weight=reflection_call_weight,
                    function_def=function_def,
                    temp_function_name=temp_fn,
                    no_improvement_patience=None,
                    file_type_params=file_type_params,
                    stage_name=stage_name,
                    log_dir=gepa_log_dir,
                    tracker=tracker,
                    extra_callbacks=_extra_callbacks,
                    input_arg_names=input_arg_names,
                    eval_detail_buffer=eval_detail_buffer,
                )
            finally:
                # Detach this thread's hooks before any sibling thread or
                # follow-up task on this worker observes them.  Touches only
                # this thread's slot in the adapter module's thread-local,
                # so it does not disturb other in-flight optimizers.
                clear_evaluate_hooks()
                # Capture the final gepa_thinking gap (GEPA cleanup: result
                # packaging, best-candidate selection after the last evaluate).
                _t_finally = time.perf_counter()
                if _last_prompt_eval_end[0] is not None:
                    tracker.add_phase(
                        "gepa_thinking",
                        _last_prompt_eval_end[0],
                        _t_finally,
                        label="gepa_cleanup",
                    )
                tracker.mark_iteration()
                tracker.add_phase(
                    "gepa_loop", _gepa_loop_t0, time.perf_counter(), label=model
                )

            model_elapsed = round(time.time() - model_start_time, 2)

            best_val_score = (
                result.val_aggregate_scores[result.best_idx]
                if result.val_aggregate_scores
                else None
            )
            seed_val_score = (
                result.val_aggregate_scores[0] if result.val_aggregate_scores else None
            )

            assert best_val_score is not None
            assert isinstance(result.best_candidate, dict)
            best_prompt_raw = result.best_candidate.get("instruction", "")

            model_output: dict[str, Any] = {
                "model": model,
                "status": "completed",
                "elapsed_seconds": model_elapsed,
                "best_prompt": best_prompt_raw,
                "best_val_score": best_val_score,
                "seed_val_score": seed_val_score,
                "total_candidates": len(result.candidates),
                "total_metric_seconds": round(tracker.total_metric_seconds, 4),
                "total_reflection_seconds": round(tracker.total_reflection_seconds, 4),
                "total_udf_compile_calls": tracker.total_udf_compile_calls,
                "total_udf_compile_seconds": round(
                    tracker.total_udf_compile_seconds, 4
                ),
                "total_udf_exec_calls": tracker.total_udf_exec_calls,
                "total_udf_exec_seconds": round(tracker.total_udf_exec_seconds, 4),
                # Real token totals from AI_COMPLETE's usage block, captured
                # via the inline-eval migration's show_details=>TRUE inject
                # in ``TempAIFunction.call_rows``.  ``udf_compile_*`` above
                # reports 0 in prompt mode post-migration but is kept for
                # back-compat with downstream readers.
                "total_udf_prompt_tokens": tracker.total_udf_prompt_tokens,
                "total_udf_completion_tokens": tracker.total_udf_completion_tokens,
                # Char-based reflection token estimates (chars / 4).
                # Reflection AI_COMPLETE keeps show_details=False, so
                # the ``usage`` block isn't surfaced — fall back to the
                # chars/4 proxy already recorded on the tracker.
                "total_reflection_prompt_tokens_est": (
                    tracker.total_reflection_prompt_tokens_est
                ),
                "total_reflection_completion_tokens_est": (
                    tracker.total_reflection_completion_tokens_est
                ),
                "total_experiment_calls": tracker.total_experiment_calls,
                "total_experiment_seconds": round(tracker.total_experiment_seconds, 4),
                "total_artifact_calls": tracker.total_artifact_calls,
                "total_artifact_seconds": round(tracker.total_artifact_seconds, 4),
                "all_val_scores": result.val_aggregate_scores,
                "reflection_model": reflection_model or model,
            }

            # Test-set evaluation and experiment storage are wrapped in
            # try/except so that transient session errors (e.g. shared-session
            # I/O races across threads) degrade gracefully to validation-only
            # scores instead of losing the entire optimization result.
            # Snapshot tracker before test eval so the BEST tracking
            # row can surface the test-set scoring cost separately
            # (see corresponding logic in snow_gepa_optimize_anything.py).
            pre_test_eval = tracker.snapshot()

            _test_eval_t0 = time.perf_counter()
            try:
                if test_table and function_def:
                    test_result = _score_seed_on_test_set(
                        session=session,
                        function_def=function_def,
                        function_name=function_name,
                        model=model,
                        seed_prompt=seed_prompt,
                        test_table=test_table,
                        input_columns=input_columns,
                        label_column=label_column,
                        evaluator=evaluator,
                        expected_columns=expected_columns,
                        run_id=run_id,
                        input_arg_names=input_arg_names,
                    )
                    model_output["seed_test_score"] = test_result.seed_score
                    model_output["_seed_eval_details"] = test_result.seed_eval_details
                    model_output["num_test_examples"] = test_result.num_examples
            except Exception as test_eval_err:
                logger.warning(
                    "[TEST_EVAL_ERROR] %s: seed test-set evaluation failed, "
                    "falling back to validation scores: %s",
                    model,
                    test_eval_err,
                )
            finally:
                tracker.add_phase(
                    "test_eval", _test_eval_t0, time.perf_counter(), label=model
                )

            # Compute test-eval delta (zero if eval was skipped/failed).
            pre_test_eval.delta(tracker).apply_to(model_output, prefix="test_eval")

            # Always use validation scores for cross-model selection so the
            # held-out test set never influences which model/candidate wins.
            # Frontier candidates get test-eval'd post-selection in the
            # orchestrator.
            model_output["seed_score"] = seed_val_score
            model_output["best_score"] = best_val_score
            model_output["score_source"] = "validation"

            # -- Pareto candidate data (pure computation, always set before save) --
            candidates_text = [
                c.get("instruction", "") if isinstance(c, dict) else str(c)
                for c in result.candidates
            ]
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
            model_output["_pareto_candidates"] = compute_pareto_candidates(
                model=model,
                candidates=candidates_text,
                val_scores=result.val_aggregate_scores,
                discovery_iter=rejected_collector.discovery_iter,
                phase_breakdowns=rejected_collector.phase_breakdowns,
                run_names=run_names_map,
            )

            # Always compute avg_output_chars from in-memory valset so it is
            # available for cost estimation even without a separate test table.
            if valset:
                model_output["avg_output_chars"] = int(
                    sum(len(d["answer"]) for d in valset) / len(valset)
                )

            # Carry per-model finalize inputs to the post-join step (the
            # consolidated SEED's per_model_stats + the winning-run artifact
            # upload).
            model_output["total_candidates"] = len(result.candidates)
            model_output["reflection_model"] = reflection_model or model
            model_output["run_dir"] = gepa_log_dir
            model_output["seed_eval_details"] = model_output.get("_seed_eval_details")

            # -- Experiment storage (schema v4) --
            # Backfill full valset_score + per-call estimated_cost onto this
            # model's RUNNING ITER runs (written by the tracker under global
            # names).  The single consolidated SEED, cross-model Pareto
            # stamping, and the COMMIT of every run are deferred to the
            # orchestrator so is_frontier / test_score can be stamped in place;
            # the returned ITER names are committed there via ``commit_runs``.
            _save_t0 = time.perf_counter()
            try:
                if experiment_name and progressive_tracker is not None:
                    model_output["pending_commit_runs"] = backfill_model_metrics(
                        session,
                        experiment_name,
                        pareto_candidates=model_output["_pareto_candidates"],
                    )
            finally:
                tracker.add_phase("save", _save_t0, time.perf_counter(), label=model)

            # Refresh tracker-sourced totals AFTER the metric backfill so
            # BENCH_RESULTS captures the full cost — including experiment
            # DDL/DML writes.  (Commit + artifact PUTs run post-join in the
            # orchestrator.)  Both metric and reflection counts come from the
            # tracker (authoritative source of truth for actual AI_COMPLETE
            # calls).
            model_output["total_metric_calls"] = tracker.total_metric_calls
            model_output["total_reflection_calls"] = tracker.total_reflection_calls
            model_output["total_metric_seconds"] = round(
                tracker.total_metric_seconds, 6
            )
            model_output["total_reflection_seconds"] = round(
                tracker.total_reflection_seconds, 4
            )
            model_output["total_udf_compile_calls"] = tracker.total_udf_compile_calls
            model_output["total_udf_compile_seconds"] = round(
                tracker.total_udf_compile_seconds, 4
            )
            model_output["total_udf_exec_calls"] = tracker.total_udf_exec_calls
            model_output["total_udf_exec_seconds"] = round(
                tracker.total_udf_exec_seconds, 4
            )
            # Refresh real token totals AFTER the metric backfill so the
            # BENCH_RESULTS row captures the full cost (mirror of
            # body mode's tracker.total_* fields above).
            model_output["total_udf_prompt_tokens"] = tracker.total_udf_prompt_tokens
            model_output["total_udf_completion_tokens"] = (
                tracker.total_udf_completion_tokens
            )
            model_output["total_reflection_prompt_tokens_est"] = (
                tracker.total_reflection_prompt_tokens_est
            )
            model_output["total_reflection_completion_tokens_est"] = (
                tracker.total_reflection_completion_tokens_est
            )
            model_output["total_experiment_calls"] = tracker.total_experiment_calls
            model_output["total_experiment_seconds"] = round(
                tracker.total_experiment_seconds, 4
            )
            model_output["total_artifact_calls"] = tracker.total_artifact_calls
            model_output["total_artifact_seconds"] = round(
                tracker.total_artifact_seconds, 4
            )

            # Strip internal-only details before returning to the caller.
            model_output.pop("_seed_eval_details", None)
            model_output.pop("_best_eval_details", None)
            # Per-thread Gantt timeline events for the benchmark report.
            # See snow_gepa_optimize_anything.py for the full rationale.
            model_output["timeline_events"] = tracker.export_events()
            return model_output

        except (ValueError, json.JSONDecodeError):
            raise

        except Exception as e:
            model_elapsed = round(time.time() - model_start_time, 2)
            error_msg = str(e)
            print(f"[OPTIMIZATION_ERROR] {model}: {error_msg}")

            # Global run structure: no separate ``<MODEL>_FAILED`` run — commit
            # the runs this model actually wrote (RUNNING ``ITER_<N>``) with
            # ``STATUS='FAILED'`` so the failure is carried on the real runs.
            if experiment_name and progressive_tracker is not None:
                commit_runs(
                    session,
                    experiment_name,
                    list(progressive_tracker.persisted_runs),
                    status="FAILED",
                )

            return {
                "model": model,
                "status": "failed",
                "error": error_msg,
                "elapsed_seconds": model_elapsed,
            }
        finally:
            set_active_tracker(None)


def run_prompt_optimization(
    session: Session,
    function_name: str,
    training_table: str,
    label_column: str,
    input_columns: list,
    metric_name: str,
    models: list,
    reflection_model: str,
    test_table: str | None = None,
    auto_budget: Literal[
        "ultra-light", "light", "medium", "heavy", "demo"
    ] = DEFAULT_AUTO_BUDGET,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    metric_options: dict | None = None,
    custom_metric_udf: str | None = None,
    run_id: str | None = None,
    aggregation_metric: str | None = None,
    experiment_name: str | None = None,
    max_frontier_candidates: int = DEFAULT_MAX_FRONTIER_CANDIDATES,
    run_dir: str | None = None,
    input_arg_names: list[str] | None = None,
    upload_run_dir: bool = True,
    query_text: str | None = None,
    create_experiment_if_missing: bool = True,
) -> dict:
    """Run prompt-mode GEPA optimization on an AI function.

    Optimizes only the system prompt while preserving the function body.
    Each model in ``models`` is optimized in parallel via ThreadPoolExecutor.

    The training_table data is split into:
    - valset (validation_fraction, default 2/3): Used for scoring candidates
    - trainset (remainder, default 1/3): Used for reflection/learning from failures

    The test_table (if provided) is ONLY used for final evaluation after
    optimization completes - it is never touched during the optimization process.

    Args:
        session: Snowpark session
        function_name: Fully qualified name of the AI function to optimize
        training_table: Table with training data (split into valset + trainset)
        label_column: Column containing expected outputs
        input_columns: List of input column names
        metric_name: Metric to use (exact_match, fuzzy_match, redaction_match, etc.)
        models: List of models to optimize with (required)
        reflection_model: Model for reflection (required)
        test_table: Optional held-out test table for final evaluation only
        auto_budget: Budget preset - "light", "medium", or "heavy"
        validation_fraction: Fraction of training data for validation
            (default 0.667 = 2/3)
        temperature: LLM sampling temperature. Default 0.0.
        max_tokens: Maximum tokens in LLM response. Default 8192.
        metric_options: Metric-specific options (e.g., threshold for fuzzy_match,
            task_description for llm_judge). Default None.
        custom_metric_udf: Fully qualified name of a custom metric UDF
            (e.g., ``DB.SCHEMA.MY_METRIC``). The UDF must accept
            ``(EXPECTED VARCHAR, PREDICTED VARCHAR)`` and return VARIANT
            with ``score`` and ``feedback`` keys.
        run_id: Unique identifier for this optimization run. Auto-generated if not
            provided.
        aggregation_metric: Optional batch-level classification metric to use for
            selecting the best candidate. Supported: "accuracy", "f1-score". When
            provided, the final best candidate is chosen by the highest value of
            this metric across all candidates.
        experiment_name: If provided, optimization results are persisted to a
            Snowflake Experiment object.
        max_frontier_candidates: Maximum number of Pareto-frontier candidates
            to retain and report. Default 7.
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
            provided, the seed prompt is extracted from this expression instead
            of introspecting a function DDL via ``DESCRIBE FUNCTION``. Prompt
            mode requires a system-prompt message shape in the expression; if
            absent, a clear error is returned.
        create_experiment_if_missing: When True (default), the experiment is
            created before runs are added. Set False by the spec-driven /
            EXECUTE EXPERIMENT path, where the experiment already exists and
            only runs are attached to it.

    Returns:
        Dict with optimization results including the best candidate and scores for each
           model

    """
    start_time = time.time()

    if not run_id:
        func_short_name = function_name.split(".")[-1].split("(")[0]
        run_id = f"ai_func_opt_{func_short_name}_{int(time.time() * 1000)}"

    # Validate required parameters
    if models is None or len(models) == 0:
        return {
            "error": "models parameter is required and cannot be empty",
            "status": "failed",
        }
    if reflection_model is None:
        return {"error": "reflection_model parameter is required", "status": "failed"}

    try:
        function_def = (
            build_query_text_function_def(query_text, input_columns, name=function_name)
            if query_text is not None
            else describe_function(session, function_name)
        )
        seed_prompt = extract_prompt_from_ddl_string(function_def.body, function_name)
        extract_model_from_ddl_string(
            function_def.body, function_name
        )  # validate model exists
    except ValueError as e:
        return {"error": str(e), "status": "failed"}

    # Validate metric name
    valid_metrics = {
        "exact_match",
        "fuzzy_match",
        "contains_match",
        "redaction_match",
        "llm_judge",
    }
    if metric_name not in valid_metrics and not custom_metric_udf:
        return {
            "error": f"Unknown metric: {metric_name}. Available: {', '.join(sorted(valid_metrics))}. "
            f"For custom metrics, provide custom_metric_udf parameter.",
            "status": "failed",
        }

    input_col_names = [col.strip('"').strip("'") for col in input_columns]

    training_columns = get_table_column_names(session, training_table)
    try:
        validate_input_columns(training_columns, input_col_names, training_table)
    except ValueError as e:
        return {"error": str(e), "status": "failed"}

    resolved_label = resolve_expected_column(training_columns, label_column)
    if training_columns and resolved_label.upper() not in training_columns:
        return {
            "error": f"Label column '{label_column}' not found in training table {training_table}. "
            f"Available columns: {sorted(training_columns)}",
            "status": "failed",
        }

    if test_table:
        test_columns = get_table_column_names(session, test_table)
        try:
            validate_input_columns(test_columns, input_col_names, test_table)
        except ValueError as e:
            return {"error": str(e), "status": "failed"}

        test_label = resolve_expected_column(test_columns, label_column)
        if test_columns and test_label.upper() not in test_columns:
            return {
                "error": f"Label column '{label_column}' not found in test table {test_table}. "
                f"Available columns: {sorted(test_columns)}. "
                f"Training and test tables must use the same column names for the label/expected column.",
                "status": "failed",
            }

    metric_opts, _, expected_columns = parse_metric_options(metric_options)

    if len(expected_columns) > 1 and metric_name != "llm_judge":
        return {
            "error": "Multi-output optimization requires metric_name='llm_judge'.",
            "status": "failed",
        }

    valid_agg_metrics = {"accuracy", "f1-score"}
    if aggregation_metric and aggregation_metric not in valid_agg_metrics:
        return {
            "error": f"Unknown aggregation_metric: '{aggregation_metric}'. "
            f"Available: {', '.join(sorted(valid_agg_metrics))}",
            "status": "failed",
        }

    gepa_metric_opts = dict(metric_opts)
    if metric_name == "llm_judge":
        gepa_metric_opts.setdefault("scoring_mode", "continuous")

        # Auto-detect multimodal file inputs from DDL (both patterns)
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
    _dataset_load_t0 = time.perf_counter()
    dataset_result = load_dataset(
        session,
        training_table,
        input_columns,
        label_column,
        expected_columns=dataset_expected_columns,
        input_arg_names=input_arg_names,
    )
    _dataset_load_t1 = time.perf_counter()
    if not dataset_result:
        return {
            "error": f"No data found in training table: {training_table}",
            "status": "failed",
        }

    # If load_dataset detected FILE-typed columns, use the stage name
    # extracted from the FILE variant values (no extra SQL needed).
    if dataset_result.file_stage_name:
        gepa_metric_opts.setdefault("stage_name", dataset_result.file_stage_name)

    evaluator = Evaluator(
        metric_name,
        session=session,
        custom_metric_udf=custom_metric_udf,
        aggregation_metric=aggregation_metric,
        **gepa_metric_opts,
    )

    full_dataset = dataset_result.dataset

    try:
        validate_stage_file_access(
            session,
            stage_name=gepa_metric_opts.get("stage_name"),
            file_columns=gepa_metric_opts.get("file_columns"),
            dataset=cast(list[dict[Any, Any]], full_dataset),
        )
    except ValueError as e:
        return {"error": str(e), "status": "failed"}
    valset, trainset = split_dataset(full_dataset, validation_fraction)

    seed_candidate = {"instruction": seed_prompt}

    if experiment_name:
        if create_experiment_if_missing:
            create_experiment(session, experiment_name)

        # Guard: if this experiment already has runs, fail fast with a clear
        # message.  Protects users who call the SPROC directly (Snowsight)
        # without going through the skill pre-flight check.
        existing_runs = get_experiment_run_names(session, experiment_name)
        if existing_runs:
            return {
                "error": (
                    f"Experiment '{experiment_name}' already contains "
                    f"{len(existing_runs)} run(s) from a prior optimization. "
                    "Delete the experiment before reoptimizing."
                ),
                "status": "failed",
            }

    # Calculate budget once upfront - same budget for ALL models
    # This ensures consistent budget across all models regardless of run order
    reflection_weight = MaxTotalBudgetStopper.estimate_reflection_weight(
        seed_candidate=seed_candidate,
        trainset=trainset,
        metric_name=evaluator.metric_name,
        metric_kwargs=dict(evaluator.kwargs),
    )
    resolved_budget = MaxTotalBudgetStopper.resolve_budget(
        auto=auto_budget,
        num_components=len(seed_candidate),
        valset_size=len(valset),
        reflection_call_weight=reflection_weight,
    )

    # Run optimization for each model in parallel via ThreadPoolExecutor.
    model_results = []
    overall_best_score: float = -1
    overall_best_score_source = "validation"
    overall_best_model = None
    overall_best_prompt = seed_prompt

    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        file_type_params = gepa_metric_opts.get("file_type_params")
        file_stage_name = gepa_metric_opts.get("stage_name")
        # Shared across all workers → one global ITER_<N> sequence (schema v4).
        # Seeded from the experiment so a retry on the same experiment_name
        # resumes past existing ITER_<N> instead of colliding on ITER_1.
        run_counter = (
            seed_run_counter_from_experiment(session, experiment_name)
            if experiment_name
            else GlobalRunCounter()
        )

        future_to_model = {
            executor.submit(
                _run_single_model_optimization,
                model=model,
                session=session,
                seed_candidate=seed_candidate,
                trainset=trainset,
                valset=valset,
                evaluator=evaluator,
                resolved_budget=resolved_budget,
                reflection_call_weight=reflection_weight,
                reflection_model=reflection_model,
                temperature=temperature,
                max_tokens=max_tokens,
                function_name=function_name,
                input_columns=input_columns,
                test_table=test_table,
                label_column=label_column,
                expected_columns=dataset_expected_columns,
                seed_prompt=seed_prompt,
                run_id=run_id,
                aggregation_metric=aggregation_metric,
                function_def=function_def,
                file_type_params=file_type_params,
                stage_name=file_stage_name,
                experiment_name=experiment_name,
                dataset_load_start_perf=_dataset_load_t0,
                dataset_load_end_perf=_dataset_load_t1,
                run_dir=run_dir,
                input_arg_names=input_arg_names,
                run_counter=run_counter,
            ): model
            for model in models
        }

        for future in as_completed(future_to_model):
            model = future_to_model[future]
            try:
                model_output = future.result()
                model_results.append(model_output)

                # Track overall best using unified score
                if model_output.get("status") == "completed":
                    best_score = model_output.get("best_score")
                    if best_score is not None and best_score > overall_best_score:
                        overall_best_score = best_score
                        overall_best_model = model_output["model"]
                        overall_best_prompt = model_output["best_prompt"]
                        overall_best_score_source = model_output.get(
                            "score_source", "validation"
                        )

            except Exception as e:
                # Hard worker crash — the worker's own except handler commits
                # that model's runs with STATUS='FAILED'.  No ``<MODEL>_FAILED``
                # run; the tracker is gone in this rare path, so log loudly.
                logger.error("[MODEL_WORKER_CRASH] %s: %s", model, e, exc_info=True)
                model_results.append(
                    {
                        "model": model,
                        "status": "failed",
                        "error": f"Future execution error: {e!s}",
                        "elapsed_seconds": 0,
                    }
                )

    # Everything from frontier build through the frontier stamp can raise
    # (e.g. build_frontier_from_pareto on missing cost data).  Wrap it so the
    # deferred SEED/ITER runs — left RUNNING by the per-model save
    # (defer_commit=True) so is_frontier/test_score could be stamped onto the
    # real lineage runs — are committed no matter how this block exits and
    # never linger in RUNNING state.
    overall_best_test_score = None
    overall_best_val_score = None
    fc_test_scores: dict[int, float] = {}
    fc_eval_details: dict[int, list] = {}
    frontier_selection: list[FrontierCandidate] = []
    try:
        all_frontier_candidates, _seed_val_score = build_frontier_from_pareto(
            model_results, logger=logger
        )
        # Schema v4 uses ONE shared ``SEED`` run across models; every completed
        # model's Pareto set includes a "SEED" candidate (its own seed eval).
        # De-dup by run name so the cross-model frontier carries a single seed
        # point.  ITER_<N> names are globally unique, so this only collapses the
        # shared seed.  Keeps the first occurrence.
        _seen_run_names: set[str] = set()
        _deduped_frontier: list[FrontierCandidate] = []
        for fc in all_frontier_candidates:
            if fc.run_name in _seen_run_names:
                continue
            _seen_run_names.add(fc.run_name)
            _deduped_frontier.append(fc)
        all_frontier_candidates = _deduped_frontier

        frontier_selection = select_frontier_candidates(
            all_frontier_candidates,
            max_candidates=max_frontier_candidates,
            seed_score=_seed_val_score,
        )

        # -- Post-selection test-eval of frontier candidates --
        # Test-eval each frontier candidate on the held-out test set so the
        # user sees generalisation scores for every option, not just the
        # single best-per-model.  Validation scores are still used for
        # selection above; the test set is purely for reporting.
        _fc_test_count: int | None = None
        if test_table and function_def and frontier_selection:
            eval_metric_options = (
                dict(evaluator.kwargs) if hasattr(evaluator, "kwargs") else {}
            )
            if evaluator.metric_name == "llm_judge":
                eval_metric_options["scoring_mode"] = "binary"
            if dataset_expected_columns:
                eval_metric_options["expected_columns"] = dataset_expected_columns

            for fi, fc in enumerate(frontier_selection):
                try:
                    model_suffix = re.sub(r"[^A-Za-z0-9]", "_", fc.model).upper()
                    fc_temp_fn = build_temp_function_name(
                        function_name,
                        f"__OPT_TEST_FC_{model_suffix}_{fi}",
                    )
                    fc_fn = TempAIFunction(
                        session=session,
                        function_def=function_def,
                        temp_function_name=fc_temp_fn,
                        candidate_model=fc.model,
                        candidate_prompt=fc.prompt_text,
                    )
                    fc_eval = evaluate(
                        session=session,
                        function_name=fc_temp_fn,
                        test_table=test_table,
                        input_columns=input_columns,
                        label_column=label_column,
                        metric_name=evaluator.metric_name,
                        custom_metric_udf=evaluator.custom_metric_udf,
                        metric_options=eval_metric_options,
                        model_name=fc.model,
                        executor=fc_fn.call_rows,
                        run_id=run_id,
                        split=f"test_frontier_{fi}",
                        input_arg_names=input_arg_names,
                    )
                    fc_test_scores[fi] = fc_eval.score
                    fc_eval_details[fi] = fc_eval.details
                    if _fc_test_count is None:
                        _fc_test_count = session.sql(
                            f"SELECT COUNT(*) FROM {test_table}"
                        ).collect()[0][0]
                except Exception as fc_err:
                    logger.warning(
                        "[FRONTIER_TEST_EVAL_ERROR] %s candidate_%d: %s",
                        fc.model,
                        fi,
                        fc_err,
                    )

        # Attach test scores onto each selected candidate so its source
        # SEED/ITER run carries BOTH valset_score (``score``) and test_score.
        if fc_test_scores:
            frontier_selection = [
                fc._replace(test_score=fc_test_scores.get(fi))
                for fi, fc in enumerate(frontier_selection)
            ]

        # Pick overall best from frontier candidates.  Prefer test scores
        # when available; fall back to validation scores.
        overall_best_run_name: str | None = None
        if frontier_selection:
            if fc_test_scores:
                best_fi = max(fc_test_scores, key=lambda k: fc_test_scores[k])
                overall_best_model = frontier_selection[best_fi].model
                overall_best_prompt = frontier_selection[best_fi].prompt_text
                overall_best_score = fc_test_scores[best_fi]
                overall_best_score_source = "test"
                overall_best_test_score = fc_test_scores[best_fi]
                overall_best_run_name = frontier_selection[best_fi].run_name
            else:
                best_fc = max(frontier_selection, key=lambda c: c.score)
                overall_best_model = best_fc.model
                overall_best_prompt = best_fc.prompt_text
                overall_best_score = best_fc.score
                overall_best_score_source = "validation"
                overall_best_run_name = best_fc.run_name

        # Stamp best_test_score on the actual winning model's model_results
        # entry for backward compat with BENCH_RESULTS.best_test_score.  Also
        # capture the winning model dict for the post-frontier artifact upload.
        winning_mr: dict | None = None
        for mr in model_results:
            if (
                mr.get("model") == overall_best_model
                and mr.get("status") == "completed"
            ):
                overall_best_val_score = mr.get("best_val_score")
                if overall_best_test_score is not None:
                    mr["best_test_score"] = overall_best_test_score
                winning_mr = mr
                break

        # Stamp the cross-model frontier onto the SELECTED candidates' source
        # SEED/ITER runs (is_frontier flag + test_score).  Snowflake rejects
        # ADD METRICS after commit, so this must precede the commit in the
        # finally.
        if experiment_name and frontier_selection:
            # Schema v4: write the SINGLE consolidated SEED run (RUNNING) with
            # the input function's model, per-model aggregate stats + summed
            # global totals, and shared seed eval scores.  Written BEFORE the
            # frontier stamp so is_frontier/test_score can land on it when the
            # seed is on the frontier; committed by the finally.
            seed_fc = next(
                (fc for fc in all_frontier_candidates if fc.run_name == "SEED"), None
            )
            per_model_stats = build_per_model_stats(
                model_results, lambda mr, f: mr.get(f)
            )
            # SEED.model = the input function's own model (the seed IS that
            # function).  Fall back to a completed model if the body has no
            # readable model=> (real AI-function bodies always do).
            try:
                seed_model = extract_model_from_ddl_string(
                    function_def.body if function_def else "", function_name
                )
            except ValueError:
                seed_model = next(
                    (
                        mr.get("model", "")
                        for mr in model_results
                        if mr.get("status") == "completed"
                    ),
                    "",
                )
            seed_avg_output_chars = next(
                (
                    mr.get("avg_output_chars")
                    for mr in model_results
                    if mr.get("status") == "completed"
                    and mr.get("avg_output_chars") is not None
                ),
                None,
            )
            write_consolidated_seed(
                session,
                experiment_name,
                function_name=function_name,
                seed_prompt=seed_prompt,
                model=seed_model,
                per_model_stats=per_model_stats,
                summed_totals=sum_seed_totals(per_model_stats),
                avg_output_chars=seed_avg_output_chars,
                seed_val_score=_seed_val_score,
                seed_estimated_cost=(seed_fc.estimated_cost if seed_fc else None),
                score_source="validation",
                metric_name=metric_name,
                custom_metric_udf=custom_metric_udf,
            )
            # Route the SEED commit through the deferred-commit finally by
            # appending it to a completed model's pending_commit_runs.
            for mr in model_results:
                if mr.get("status") == "completed":
                    if mr.get("pending_commit_runs") is None:
                        mr["pending_commit_runs"] = []
                    mr["pending_commit_runs"].append("SEED")
                    break

            stamp_frontier_metrics_on_runs(
                session,
                experiment_name,
                frontier_selection=frontier_selection,
            )

            # Upload run_dir + seed eval-detail artifacts to the overall-best
            # run (schema v4 uploads once, cross-model, not per model).
            if overall_best_run_name and winning_mr is not None:
                upload_winning_artifacts(
                    session,
                    experiment_name,
                    overall_best_run_name,
                    run_dir=winning_mr.get("run_dir"),
                    seed_eval_details=winning_mr.get("seed_eval_details"),
                    best_eval_details=winning_mr.get("_best_eval_details"),
                    upload_run_dir=upload_run_dir,
                )
    finally:
        # Commit every deferred SEED/ITER run across completed models,
        # regardless of whether a candidate landed on the frontier or whether
        # the block above raised — so no SEED/ITER run is left uncommitted.
        if experiment_name:
            pending_runs: list[str] = []
            for mr in model_results:
                if mr.get("status") == "completed" and mr.get("pending_commit_runs"):
                    pending_runs.extend(mr["pending_commit_runs"])
                    mr["pending_commit_runs"] = None
            if pending_runs:
                commit_runs(session, experiment_name, pending_runs)

    elapsed_seconds = round(time.time() - start_time, 2)

    output = {
        "status": "completed",
        "run_id": run_id,
        "elapsed_seconds": elapsed_seconds,
        "function_name": function_name,
        "seed_prompt": seed_prompt,
        "metric": metric_name,
        "models": models,
        "model_results": model_results,
        "overall_best_model": overall_best_model,
        "overall_best_prompt": overall_best_prompt,
        "overall_best_val_score": overall_best_val_score,
        "overall_best_test_score": overall_best_test_score,
        "overall_best_score": overall_best_score if overall_best_score >= 0 else None,
        "overall_best_score_source": overall_best_score_source,
        "frontier_candidates": [
            {
                "model": fc.model,
                "candidate_idx": fi,
                "estimated_cost": fc.estimated_cost,
                "score": fc.score,
                "test_score": fc_test_scores.get(fi),
                "prompt": fc.prompt_text,
            }
            for fi, fc in enumerate(frontier_selection)
        ],
    }

    if aggregation_metric:
        output["aggregation_metric"] = aggregation_metric

    if dataset_expected_columns:
        output["expected_columns"] = dataset_expected_columns

    # Clean up async task if this was called from one (run_id matches task name)
    if run_id and run_id.startswith("ai_func_opt_"):
        try:
            parts = function_name.split("(")[0].split(".")
            if len(parts) >= 3:
                task_fqn = f"{parts[0]}.{parts[1]}.{run_id}"
                session.sql(f"DROP TASK IF EXISTS {task_fqn}").collect()
        except Exception:
            pass  # Cleanup failure should not break optimization

    return output


def _prompt_mode_handler(**kwargs: Any) -> dict:
    """Adapter: strip kwargs that run_prompt_optimization doesn't accept."""
    kwargs.pop("engine", None)
    return run_prompt_optimization(**kwargs)
