# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Evaluation infrastructure for AI function optimization.

Provides :class:`Evaluator` — a metric evaluation wrapper with optional batch
optimization and timing integration — and :class:`ScoredExample` — the per-row
score + feedback container returned by single-item evaluations.
"""

import time
from typing import Any

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.metrics.aggregation import (
    compute_classification_objectives,
)
from snowflake_ai_optimize.core.metrics.dispatch import (
    compute_metric,
    compute_metric_batch,
)
from snowflake_ai_optimize.core.stage import stage_key
from snowflake_ai_optimize.core.timing import get_active_tracker
from snowflake_ai_optimize.core.types import SnowflakeDataInst


class ScoredExample:
    """Result from evaluating a single example."""

    def __init__(
        self,
        score: float,
        feedback: str,
        objective_scores: dict[str, float] | None = None,
    ) -> None:
        self.score = score
        self.feedback = feedback
        self.objective_scores = objective_scores


class Evaluator:
    """Encapsulates metric evaluation with optional batch optimization.

    This class provides a clean interface for evaluating AI function outputs
    against expected values using various metrics.

    Args:
        metric_name: Name of the metric (exact_match, fuzzy_match, llm_judge, etc.)
        session: Snowpark session (required for llm_judge, optional for others)
        **kwargs: Metric-specific options (e.g., threshold for fuzzy_match,
            task_description for llm_judge)

    Example:
        evaluator = Evaluator("fuzzy_match", threshold=0.9)
        result = evaluator(data, response)

        evaluator = Evaluator("llm_judge", session, task_description="...")
        results = evaluator.evaluate_batch(items)

    """

    def __init__(
        self,
        metric_name: str,
        session: Session | None = None,
        custom_metric_udf: str | None = None,
        aggregation_metric: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.metric_name = metric_name
        self.session = session
        self.custom_metric_udf = custom_metric_udf
        self.aggregation_metric = aggregation_metric
        self.kwargs = kwargs

    def __call__(self, data: "SnowflakeDataInst", response: str) -> ScoredExample:
        """Single-item evaluation."""
        expected = data["answer"]
        tracker = get_active_tracker()
        start = time.perf_counter()
        try:
            score, feedback = compute_metric(
                self.metric_name,
                expected,
                response,
                self.session,
                self.custom_metric_udf,
                **self.kwargs,
            )
        finally:
            if tracker is not None:
                tracker.add_metric(time.perf_counter() - start)
        return ScoredExample(score=score, feedback=feedback)

    def evaluate_batch(
        self, items: list[tuple["SnowflakeDataInst", str]]
    ) -> list[ScoredExample]:
        """Batched evaluation with automatic optimization when available.

        Metrics with optimized batch implementations (e.g., llm_judge) are
        evaluated in a single call. Others fall back to sequential evaluation.

        When ``file_columns`` and ``stage_name`` are present in kwargs,
        file paths are extracted from the input data and forwarded to
        the metric so the LLM judge can see the actual files (images, PDFs, etc.).

        Args:
            items: List of (data, response) tuples to evaluate

        Returns:
            List of ScoredExample in the same order as input items

        """
        if not items:
            return []
        batch_items = [(data["answer"], response) for data, response in items]

        metric_kwargs = dict(self.kwargs)
        file_columns = metric_kwargs.pop("file_columns", None)
        has_files = file_columns and self.metric_name == "llm_judge"
        if has_files:
            fc = file_columns[0]
            sk = stage_key(fc)
            metric_kwargs["file_paths"] = [
                str(data["inputs"].get(fc, "")) for data, _ in items
            ]
            per_row_stages = [str(data["inputs"].get(sk, "")) for data, _ in items]
            if any(per_row_stages):
                metric_kwargs["stage_name"] = per_row_stages
        else:
            metric_kwargs.pop("stage_name", None)

        tracker = get_active_tracker()
        start = time.perf_counter()
        try:
            results = compute_metric_batch(
                self.metric_name,
                batch_items,
                self.session,
                self.custom_metric_udf,
                **metric_kwargs,
            )
        finally:
            if tracker is not None and batch_items:
                # Record ONE timeline event covering the actual SQL window
                # ``[start, end]`` (the previous loop pushed N events all
                # stamped at ``end``, collapsing the whole batch into a
                # single point on the Gantt chart).  ``add_metric_batch``
                # still appends N copies of ``per_item`` to
                # ``metric_durations`` so totals / averages / percentiles
                # remain identical to single-call mode.
                tracker.add_metric_batch(start, time.perf_counter(), len(batch_items))
        eval_results = [ScoredExample(score=s, feedback=f) for s, f in results]

        if self.aggregation_metric:
            label_pairs = [
                (expected, predicted)
                for (expected, predicted), _ in zip(batch_items, results, strict=True)
            ]
            # For classification tasks, always compute precision, recall, F1, and
            # accuracy across each evaluation batch.
            objectives = compute_classification_objectives(label_pairs)
            if objectives:
                for er in eval_results:
                    er.objective_scores = objectives

                # If aggregation_metric is requested, but not "accuracy", override model
                # scores to use requested aggregation metric to filter candidates
                if (
                    self.aggregation_metric != "accuracy"
                    and self.aggregation_metric in objectives
                ):
                    agg_score = objectives[self.aggregation_metric]
                    for er in eval_results:
                        er.score = agg_score

        return eval_results
