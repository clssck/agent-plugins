# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Custom UDF-based metric invocation."""

import json

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.sql_utils import validate_dotted_identifier


def parse_metric_result(raw: object) -> tuple[float, str]:
    """Parse the VARIANT result from a custom metric UDF call.

    Returns ``(score, feedback)``.  Falls back to ``(0.0, error_message)``
    on any parse failure so a single bad row never crashes the run.
    """
    if raw is None:
        return 0.0, "Custom metric UDF returned NULL"

    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return 0.0, f"Custom metric UDF returned non-JSON string: {raw[:200]}"

    if not isinstance(parsed, dict):
        return 0.0, (
            f"Custom metric UDF returned {type(parsed).__name__}, "
            f"expected dict with 'score' and 'feedback'"
        )

    if "score" not in parsed:
        return 0.0, (
            f"Custom metric UDF result missing 'score' key. "
            f"Keys: {sorted(parsed.keys())}"
        )

    try:
        score = float(parsed["score"])
    except (TypeError, ValueError):
        return 0.0, (f"Custom metric UDF 'score' is not numeric: {parsed['score']!r}")

    feedback = str(parsed.get("feedback", ""))
    return score, feedback


def call_custom_metric_udf(
    metric_udf: str,
    expected: str,
    predicted: str,
    session: Session,
) -> tuple[float, str]:
    """Call a custom metric implemented as a Python UDF.

    The UDF must accept (EXPECTED VARCHAR, PREDICTED VARCHAR) and return
    VARIANT with keys ``score`` (float 0.0-1.0) and ``feedback`` (string).

    Args:
        metric_udf: Fully qualified UDF name (e.g., ``DB.SCHEMA.MY_METRIC``).
        expected: Ground truth value.
        predicted: Model output.
        session: Snowpark session.

    Returns:
        (score, feedback) tuple.

    """
    safe_name = validate_dotted_identifier(
        metric_udf, kind="Custom metric UDF name", quote=True
    )

    result = session.sql(
        f"SELECT {safe_name}(?, ?) AS RESULT",
        params=[str(expected), str(predicted)],
    ).collect()

    if not result:
        return 0.0, "Custom metric UDF returned no result"

    return parse_metric_result(result[0]["RESULT"])


def call_custom_metric_udf_batch(
    metric_udf: str,
    items: list[tuple[str, str]],
    session: Session,
) -> list[tuple[float, str]]:
    """Batched evaluation using a custom metric UDF.

    Evaluates all (expected, predicted) pairs in a single SQL query using a
    VALUES clause, similar to ``llm_judge_batch``.

    Args:
        metric_udf: Fully qualified UDF name.
        items: List of (expected, predicted) tuples.
        session: Snowpark session.

    Returns:
        List of (score, feedback) tuples in same order as input.

    """
    if not items:
        return []

    safe_name = validate_dotted_identifier(
        metric_udf, kind="Custom metric UDF name", quote=True
    )

    value_qmarks = ", ".join(f"({idx}, ?, ?)" for idx in range(len(items)))
    bind_params: list[object] = []
    for expected, predicted in items:
        bind_params.extend([str(expected), str(predicted)])

    results = session.sql(
        f"""
        SELECT idx, {safe_name}(expected_val, predicted_val) AS RESULT
        FROM VALUES {value_qmarks} AS t(idx, expected_val, predicted_val)
        ORDER BY idx
    """,
        params=bind_params,
    ).collect()

    outputs = []
    for row in results:
        outputs.append(parse_metric_result(row["RESULT"]))

    return outputs
