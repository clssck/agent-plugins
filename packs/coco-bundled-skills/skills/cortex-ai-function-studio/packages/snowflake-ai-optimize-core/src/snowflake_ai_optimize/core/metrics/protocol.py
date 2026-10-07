# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Protocol definition for custom evaluation metrics."""

from typing import Any, Protocol, runtime_checkable

from snowflake.snowpark import Session


@runtime_checkable
class CustomMetric(Protocol):
    """Protocol for custom evaluation metrics.

    Every custom metric file must define a class named ``CustomMetric`` that
    satisfies this protocol. The class must be callable with the signature
    below -- that is the only requirement.

    The file name (without ``.py``) becomes the metric name used in
    ``EVALUATE_AI_FUNCTION``. The class name is always ``CustomMetric``.
    Different metrics are distinguished by file name, not class name.

    Evaluation metrics produce a numeric score **and** text feedback explaining
    why the prediction is correct or incorrect. The feedback is used during the
    optimization step to refine the prompt your function uses, so it should be
    specific and actionable (e.g., "Found 3 of 5 keywords; missing: X, Y").
    """

    def __call__(
        self,
        expected: str,
        predicted: str,
        session: Session | None = None,
        **kwargs: Any,
    ) -> tuple[float, str]:
        """Evaluate a single (expected, predicted) pair.

        Args:
            expected: Ground truth value.
            predicted: Model output.
            session: Snowpark session (needed for LLM-based metrics).
            **kwargs: Metric-specific options.

        Returns:
            (score, feedback) where score is 0.0-1.0 and feedback explains
            the score in a way that is useful for optimization.

        """
        ...
