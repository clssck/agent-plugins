# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Core metrics sub-package.

Re-exports the built-in scoring functions and dispatch utilities.
"""

from snowflake_ai_optimize.core.metrics.aggregation import (
    compute_classification_objectives,
)
from snowflake_ai_optimize.core.metrics.builtin import (
    contains_match_core,
    exact_match_core,
    fuzzy_match_core,
    redaction_match_core,
)
from snowflake_ai_optimize.core.metrics.dispatch import (
    compute_metric,
    compute_metric_batch,
)

__all__ = [
    "compute_classification_objectives",
    "compute_metric",
    "compute_metric_batch",
    "contains_match_core",
    "exact_match_core",
    "fuzzy_match_core",
    "redaction_match_core",
]
