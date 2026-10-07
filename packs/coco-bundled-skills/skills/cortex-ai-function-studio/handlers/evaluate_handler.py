# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""SPROC entry point for EVALUATE_AI_FUNCTION.

Composition-root handler — wires core.evaluate + core.experiment + SPROC
decorators.  The inline bundler concatenates this file last in the evaluate
source list.
"""

import time
from dataclasses import asdict

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.evaluation import evaluate
from snowflake_ai_optimize.core.experiment import save_evaluation_to_experiment
from snowflake_ai_optimize.core.metrics.llm_judge import LLM_JUDGE_DEFAULT_MODEL
from snowflake_ai_optimize.core.sproc_decorators import (
    surface_sproc_error,
    with_ai_sql_error_handling_use_fail_on_error_disabled_for_sproc,
    with_custom_ai_function_query_tag,
)


@surface_sproc_error()
@with_ai_sql_error_handling_use_fail_on_error_disabled_for_sproc()
@with_custom_ai_function_query_tag("SPROC_EVALUATE")
def evaluate_handler(
    session: Session,
    function_name: str,
    test_table: str,
    input_columns: list,
    label_column: str,
    metric_name: str,
    model_name: str = LLM_JUDGE_DEFAULT_MODEL,
    sample_size: int | None = None,
    experiment_name: str | None = None,
    metric_options: dict | None = None,
    max_length: int = 500,
    custom_metric_udf: str | None = None,
    run_id: str | None = None,
) -> dict:
    """SPROC entry point for EVALUATE_AI_FUNCTION.

    Thin wrapper around :func:`evaluate` that exposes only the parameters
    available through the stored procedure interface. Persists per-row
    eval details as ``eval_detail.json`` to a per-evaluation Snowflake
    Experiment and returns a VARIANT pointing at the SnowURL where the
    results can be queried.
    """
    if custom_metric_udf is not None and not custom_metric_udf.strip():
        raise ValueError("Custom metric UDF name cannot be empty")

    start_time = time.time()

    if not run_id:
        func_short_name = function_name.split(".")[-1].split("(")[0]
        run_id = f"ai_func_eval_{func_short_name}_{int(time.time() * 1000)}"

    if not experiment_name:
        experiment_name = run_id

    result = evaluate(
        session,
        function_name,
        test_table,
        input_columns,
        label_column,
        metric_name,
        model_name=model_name,
        sample_size=sample_size,
        metric_options=metric_options,
        max_length=max_length,
        custom_metric_udf=custom_metric_udf,
        run_id=run_id,
    )

    elapsed = time.time() - start_time

    save_evaluation_to_experiment(
        session,
        experiment_name,
        function_name=function_name,
        metric_name=metric_name,
        model_name=model_name,
        score=result.score,
        num_examples=len(result.details),
        eval_details=result.details,
        sample_size=sample_size,
        custom_metric_udf=custom_metric_udf or "",
        elapsed_seconds=elapsed,
        cost_info=result.cost_measurement,
    )

    snowurl = f"snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json"
    return {
        "score": result.score,
        "run_id": run_id,
        "experiment_name": experiment_name,
        "snowurl": snowurl,
        "num_examples": len(result.details),
        "cost": asdict(result.cost_measurement) if result.cost_measurement else None,
    }
