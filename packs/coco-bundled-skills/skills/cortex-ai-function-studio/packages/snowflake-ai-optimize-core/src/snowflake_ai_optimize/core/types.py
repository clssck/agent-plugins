# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Shared data types for AI function optimization.

Types defined here are consumed by both core infrastructure (Layer 0) and
algorithm packages (Layer 1).  Keeping them in core avoids circular imports.
"""

from dataclasses import dataclass
from typing import TypedDict


class SnowflakeDataInst(TypedDict):
    """Input data instance for Snowflake-based evaluation."""

    inputs: dict[str, str]
    answer: str


@dataclass(frozen=True)
class CostMeasurement:
    """Token usage and estimated cost for an AI function evaluation."""

    model: str
    num_rows: int
    total_prompt_tokens: float
    total_completion_tokens: float
    avg_prompt_tokens: float
    avg_completion_tokens: float
    estimated_cost_per_call: float


@dataclass(frozen=True)
class EvaluationResult:
    """Aggregate result returned by :func:`evaluate`.

    ``cost_measurement`` is populated only when the function is called
    directly via SQL (``executor is None``).  Optimizer callers that supply
    their own executor will always receive ``cost_measurement=None``.
    """

    score: float
    details: list[dict]
    cost_measurement: CostMeasurement | None = None
