# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""SPROC entry point for OPTIMIZE_AI_FUNCTION.

Composition-root dispatcher — validates parameters, resolves the optimize mode,
and dispatches to the appropriate handler.  The inline bundler concatenates
this file last in the optimize source list.
"""

from typing import Literal

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.optimize_registry import resolve_mode
from snowflake_ai_optimize.core.sproc_decorators import (
    surface_sproc_error,
    with_ai_sql_error_handling_use_fail_on_error_disabled_for_sproc,
    with_custom_ai_function_query_tag,
)

# SPROC-contract constants: define the SQL DEFAULT clause values exposed to
# customers.  Each algorithm module defines its own internal defaults; these
# are the public interface.
DEFAULT_AUTO_BUDGET: Literal["ultra-light", "light", "medium", "heavy", "demo"] = (
    "ultra-light"
)
DEFAULT_VALIDATION_FRACTION = 0.5
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192
OptimizeMode = str
DEFAULT_OPTIMIZE_MODE: OptimizeMode = "body"


@surface_sproc_error()
@with_ai_sql_error_handling_use_fail_on_error_disabled_for_sproc()
@with_custom_ai_function_query_tag("SPROC_OPTIMIZATION")
def run_optimization(
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
    optimize_mode: OptimizeMode = DEFAULT_OPTIMIZE_MODE,
    experiment_name: str | None = None,
    engine: str = "default",
    run_dir: str | None = None,
    input_arg_names: list[str] | None = None,
    evolve_overrides: dict | None = None,
    upload_run_dir: bool = False,
    query_text: str | None = None,
    create_experiment_if_missing: bool = True,
    fail_on_reflection_error: bool = False,
) -> dict:
    """Run GEPA optimization on an AI function. SPROC handler function.

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
        auto_budget: Budget preset - "ultra-light", "light", "medium", or
            "heavy" ("demo" is a back-compat alias for "ultra-light")
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
        optimize_mode: Optimization strategy. ``"body"`` (default) optimizes
            the entire SQL function body. ``"prompt"`` optimizes only the system
            prompt. See full mode docs in ``snow_gepa_optimize.py``.
        experiment_name: If provided, optimization results are persisted to a
            Snowflake Experiment object.
        engine: Optimizer engine variant to use (e.g. ``"default"``);
            forwarded to the mode-specific optimizer.
        run_dir: Optional directory for persisting per-run artifacts and logs.
        input_arg_names: Optional list of AI-function parameter names, one per
            entry in ``input_columns`` (same length/order, already resolved from
            any ``$N`` markers by the caller). When provided, each dataset column
            is bound to its parameter name; ``None`` (default; the SPROC passes
            nothing) preserves the legacy positional/name-match behavior.
        evolve_overrides: Optional dict of evolve/frontier-only optimizer knobs
            (e.g. ``evolve_budget_multiplier``, ``frontier_minibatch_size``,
            ``num_top_programs``, ``num_diverse_programs``, ``frontier_adapter_fix``).
            Forwarded to ``run_evolve_optimization`` ONLY for evolve-family modes;
            ignored for body/prompt (whose handlers have fixed signatures). Used by
            the benchmark's ablation-mode presets.
        upload_run_dir: When True, the GEPA ``run_dir`` status/state artifacts
            are uploaded to the winning run's experiment stage (body/prompt
            family only). Defaults to False — these are internal optimizer files
            that the skill docs tell users not to query; only the benchmark
            tooling (which analyzes run_dir) opts in.
        query_text: Inline scalar SQL expression for a builtin AI function
            (e.g. ``AI_COMPLETE('llama3.1-70b', 'Answer: ' || question)``). When
            set, every optimize mode seeds its candidate program from this
            expression instead of introspecting a user function DDL; forwarded
            to each mode handler only on the builtin path.
        create_experiment_if_missing: When True (default), the optimizer creates
            the experiment before adding runs. Set False by the spec-driven /
            EXECUTE EXPERIMENT handler, where the experiment already exists
            (created by the DDL layer) and only runs are added. Forwarded to
            every optimize mode.
        fail_on_reflection_error: When True, a reflection call that keeps failing
            after retries is fatal — the model stops and its runs are committed
            FAILED with the reflection error, instead of GEPA swallowing the
            error and the run finishing SUCCEEDED. Set only by the spec-driven /
            EXECUTE EXPERIMENT handler; forwarded to body mode only. Defaults to
            False (standalone OPTIMIZE_AI_FUNCTION behavior unchanged).

    Returns:
        Dict with optimization results including the best candidate and scores for each
            model

    """
    # Validate validation_fraction before mode dispatch (all modes need it).
    if validation_fraction <= 0.0:
        return {
            "error": (
                f"validation_fraction must be greater than 0.0 (got {validation_fraction}). "
                "A zero validation fraction produces an empty validation set, which prevents "
                "the optimizer from scoring candidates and causes the optimization to hang."
            ),
            "status": "failed",
        }
    if validation_fraction >= 1.0:
        return {
            "error": (
                f"validation_fraction must be less than 1.0 (got {validation_fraction}). "
                "A validation fraction of 1.0 leaves no training data for reflection."
            ),
            "status": "failed",
        }

    # Mode dispatch. Coerce SQL NULL → default (Snowflake passes None for
    # unset SPROC params instead of honoring DEFAULT).
    if optimize_mode is None:
        optimize_mode = DEFAULT_OPTIMIZE_MODE

    handler = resolve_mode(optimize_mode)
    kwargs = dict(
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
        run_dir=run_dir,
        # Whether the optimizer creates the experiment before adding runs.
        # Every mode handler accepts this; the spec-driven / EXECUTE EXPERIMENT
        # caller sets it False (the DDL layer already created the experiment),
        # regardless of optimize_mode.
        create_experiment_if_missing=create_experiment_if_missing,
    )
    # Forward the resolved per-column parameter names only when the caller
    # supplied them.  The production SPROC passes nothing (``None``), so
    # omitting the key keeps forwarding byte-identical to today for every
    # mode handler — including the evolve/coco experiment handlers whose
    # underlying optimizers don't accept this parameter.
    if input_arg_names is not None:
        kwargs["input_arg_names"] = input_arg_names
    # Forward the run_dir-upload toggle ONLY to the body/prompt family, whose
    # handlers route to run_body_optimization / run_prompt_optimization (which
    # accept it). The evolve-family handlers have fixed signatures and would
    # raise TypeError on the extra key, so gate by mode. Defaults to False — the
    # GEPA run_dir artifacts are internal state that the skill docs tell users
    # not to query; only the benchmark opts in (upload_run_dir=True).
    if optimize_mode in (
        "body",
        "prompt",
        "body_agent",
        "body_agent_single_session",
    ):
        kwargs["upload_run_dir"] = upload_run_dir
    # Forward the builtin ``query_text`` only when set (builtin AI function
    # optimization). Every mode's ``run_*`` accepts a ``query_text`` kwarg and
    # seeds its candidate program from it instead of introspecting a function
    # DDL; omitting the key on the user-function path keeps forwarding
    # byte-identical to today.
    if query_text is not None:
        kwargs["query_text"] = query_text
    # Forward only to body mode (only run_body_optimization accepts the kwarg)
    # and only when opted in, so other callers/modes stay byte-identical.
    if fail_on_reflection_error and optimize_mode == "body":
        kwargs["fail_on_reflection_error"] = True
    # Forward evolve/frontier ablation knobs (minibatch sizes, budget
    # multiplier, MAP-Elites selection params, adapter_fix, ...) ONLY to the
    # evolve-family handlers.  The body/prompt handlers forward **kwargs into
    # run_body_optimization / run_prompt_optimization, whose signatures are
    # fixed and would raise TypeError on these extra keys — so gate by mode.
    if evolve_overrides and optimize_mode in (
        "evolve",
        "evolve_agent",
        "evolve_agent_single_session",
    ):
        kwargs.update(evolve_overrides)
    return handler(**kwargs)
