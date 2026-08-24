# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Metric dispatch — routes metric names to their implementations.

Changes when metrics are added or removed from the system.
"""

import logging
from collections.abc import Callable
from typing import Any

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.metrics.builtin import (
    contains_match_core,
    exact_match_core,
    fuzzy_match_core,
    redaction_match_core,
)
from snowflake_ai_optimize.core.metrics.custom_udf import (
    call_custom_metric_udf,
    call_custom_metric_udf_batch,
)
from snowflake_ai_optimize.core.metrics.llm_judge import (
    llm_judge_batch,
    llm_judge_core,
)

logger = logging.getLogger(__name__)

PredictionExecutor = Callable[[list[dict[str, object]]], list[object]]

# Prefix stamped on the feedback of a row whose metric scoring *threw* (as
# opposed to legitimately scoring 0). Lets the evaluator route it to the
# per-row ``error_message`` field, which is uniform across metrics, rather
# than leaving it only in ``metric_feedback`` (which many metrics leave terse
# or empty). Callers that surface errors should key off this.
METRIC_ERROR_PREFIX = "Metric error: "


def compute_metric_batch_resilient(
    metric_name: str,
    items: list[tuple[str, str]],
    session: Session | None = None,
    custom_metric_udf: str | None = None,
    **kwargs: Any,
) -> list[tuple[float, str]]:
    """Batch-score, degrading to per-row scoring instead of aborting on failure.

    The single batch call (llm_judge AI_COMPLETE, custom-UDF batch SQL, or the
    sequential fallback) can fail for the *whole* batch on one bad row — a
    count mismatch, a malformed judge response, a UDF signature error. This
    retries each item individually so a genuinely-bad row is isolated to a
    ``(0.0, feedback)`` score and every other row still gets a real score.

    Returns ``(score, feedback)`` for every item, in input order — never raises.
    """
    try:
        return compute_metric_batch(
            metric_name, items, session, custom_metric_udf, **kwargs
        )
    except Exception as exc:
        # Per-row retry is O(n) SQL calls when the whole judge/model is down —
        # acceptable for a run-level eval; the alternative (aborting) loses
        # every row's result. Prediction pass degrades the same way.
        logger.warning(
            "[METRIC_BATCH_ERROR] compute_metric_batch raised; "
            "falling back to per-row scoring: %s",
            exc,
        )
        results: list[tuple[float, str]] = []
        for exp, pred in items:
            try:
                results.append(
                    compute_metric(
                        metric_name,
                        exp,
                        pred,
                        session,
                        custom_metric_udf=custom_metric_udf,
                        **kwargs,
                    )
                )
            except Exception as row_exc:
                results.append((0.0, f"{METRIC_ERROR_PREFIX}{row_exc}"))
        return results


def compute_metric(
    metric_name: str,
    expected: str,
    predicted: str,
    session: Session | None = None,
    custom_metric_udf: str | None = None,
    **kwargs: Any,
) -> tuple[float, str]:
    """Dispatch to built-in or custom metric function.

    Args:
        metric_name: Name of the metric to use
        expected: Expected output value
        predicted: Predicted output value
        session: Snowpark session (required for llm_judge and custom metrics)
        custom_metric_udf: Fully qualified name of a Python UDF that
            implements the custom metric. The UDF must accept
            ``(EXPECTED VARCHAR, PREDICTED VARCHAR)`` and return VARIANT
            with ``score`` (float) and ``feedback`` (string) keys.
        **kwargs: Metric-specific options

    """
    metric_functions: dict[str, Callable[..., tuple[float, str]]] = {
        "exact_match": exact_match_core,
        "fuzzy_match": fuzzy_match_core,
        "contains_match": contains_match_core,
        "redaction_match": redaction_match_core,
        "llm_judge": llm_judge_core,
    }
    metric_fn = metric_functions.get(metric_name)
    if metric_fn is not None:
        return metric_fn(expected, predicted, session, **kwargs)

    if custom_metric_udf:
        if session is None:
            raise ValueError("custom_metric_udf requires a session")
        return call_custom_metric_udf(custom_metric_udf, expected, predicted, session)

    raise ValueError(
        f"Unknown metric: {metric_name}. "
        f"Available built-in: {', '.join(sorted(metric_functions.keys()))}. "
        f"For custom metrics, provide fully qualified custom_metric_udf name."
    )


# Registry of metrics that have optimized batch implementations.
BATCH_FUNCTIONS: dict[str, Callable[..., list[tuple[float, str]]]] = {
    "llm_judge": llm_judge_batch,
}


def compute_metric_batch(
    metric_name: str,
    items: list[tuple[str, str]],
    session: Session | None = None,
    custom_metric_udf: str | None = None,
    **kwargs: Any,
) -> list[tuple[float, str]]:
    """Batch evaluate multiple (expected, predicted) pairs.

    Uses optimized batch implementation if available, otherwise falls back
    to sequential evaluation.

    Args:
        metric_name: Name of the metric to use
        items: List of (expected, predicted) tuples
        session: Snowpark session (required for llm_judge and custom metrics)
        custom_metric_udf: Fully qualified name of a custom metric UDF
        **kwargs: Metric-specific options

    Returns:
        List of (score, feedback) tuples in same order as input

    """
    if metric_name in BATCH_FUNCTIONS:
        if session is None:
            raise ValueError("batched functions require a session")
        return BATCH_FUNCTIONS[metric_name](items, session, **kwargs)

    if custom_metric_udf:
        if session is None:
            raise ValueError("custom_metric_udf requires a session")
        return call_custom_metric_udf_batch(custom_metric_udf, items, session)

    return [
        compute_metric(metric_name, exp, pred, session, **kwargs) for exp, pred in items
    ]
