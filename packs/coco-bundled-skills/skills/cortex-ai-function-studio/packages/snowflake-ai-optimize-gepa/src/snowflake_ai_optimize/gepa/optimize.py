# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Public GEPA optimization API for Snowflake.

This module provides ``run_optimization``, the SPROC handler that dispatches
to prompt-mode, body-mode, body_agent, or coco_one_shot optimization based
on the ``optimize_mode`` parameter.
"""

import logging
import random
from typing import Literal

from gepa.core.state import GEPAState
from snowflake_ai_optimize.core.metrics.llm_judge import (
    _LLM_JUDGE_CONTINUOUS_TEMPLATE,
    _LLM_JUDGE_FILE_ADDENDUM,
    _LLM_JUDGE_USER_TEMPLATE,
)
from snowflake_ai_optimize.core.types import SnowflakeDataInst
from snowflake_ai_optimize.gepa.adapter import (
    SnowflakeLLM,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default configuration values
# ---------------------------------------------------------------------------

DEFAULT_REFLECTION_MINIBATCH_SIZE = 10
DEFAULT_AUTO_BUDGET: Literal["ultra-light", "light", "medium", "heavy", "demo"] = (
    "ultra-light"
)
DEFAULT_VALIDATION_FRACTION = 0.5
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 8192
DEFAULT_PERFECT_SCORE = 1.0
DEFAULT_MAX_MERGE_INVOCATIONS = 5
DEFAULT_REFLECTION_CALL_WEIGHT = 1
DEFAULT_SPLIT_SEED = 42

# OPTIMIZE_AI_FUNCTION's ``OPTIMIZE_MODE`` argument.  The SPROC signature
# declares this as ``VARCHAR DEFAULT 'body'``; on the Python side we keep
# the closed set as a ``Literal`` so static checkers catch typos.  Mirror
# any new value into the doc-comment block on ``OPTIMIZE_MODE`` in
# ``src/optimize_sproc.sql.j2``.  Experiment modes live in
# ``dev/modes/register_all.py`` and are not part of the production type.
OptimizeMode = Literal["prompt", "body"]
DEFAULT_OPTIMIZE_MODE: OptimizeMode = "body"

AUTO_BUDGET_SETTINGS: dict[str, dict[str, int]] = {
    "ultra-light": {"n": 2},
    # "demo" is a back-compat alias for "ultra-light" (same n). Kept so existing
    # customer SQL / specs that pass 'demo' keep working after the rename.
    "demo": {"n": 2},
    "light": {"n": 6},
    "medium": {"n": 12},
    "heavy": {"n": 18},
}


class PythonLoggingAdapter:
    """Adapts Python logging to GEPA's LoggerProtocol.

    Args:
        py_logger: The Python logger instance to delegate to.
        prefix: Optional prefix prepended to each message (e.g. model name).
        level: Logging level for GEPA messages. Defaults to DEBUG since
            GEPA engine messages are verbose internal detail.

    """

    def __init__(
        self,
        py_logger: logging.Logger,
        prefix: str = "",
        level: int = logging.DEBUG,
    ) -> None:
        self._logger = py_logger
        self._prefix = prefix
        self._level = level

    def log(self, message: str) -> None:
        if self._prefix:
            self._logger.log(self._level, "[%s] %s", self._prefix, message)
        else:
            self._logger.log(self._level, "%s", message)


class MaxTotalBudgetStopper:
    """Budget-aware stopper that accounts for both metric and reflection calls.

    Stop criteria
    -------------
    The stopper is invoked by the GEPA engine at the top of every
    iteration via ``_should_stop(state)``.  It computes a *weighted total*
    of all work done so far and compares it to the budget::

        weighted_total = metric_calls + reflection_calls * W

    where:
    - ``metric_calls`` = ``gepa_state.total_num_evals`` — the number of
      individual metric/adapter evaluations (each row in a batched UDF
      call counts as one).
    - ``reflection_calls`` = ``reflection_lm.call_count`` — the number of
      reflection LLM invocations (one per proposal iteration).
    - ``W`` = ``reflection_call_weight`` — estimated dynamically via
      ``estimate_reflection_weight`` by comparing the character length of
      a representative reflection prompt to the average metric prompt.
      LLM inference cost scales roughly with input token count, so the
      prompt-length ratio is a good proxy for relative wall-clock cost.

    Optimization stops when ``weighted_total >= max_budget``.  A budget is
    always required — use ``resolve_budget`` to compute one from an auto
    preset before constructing the stopper.

    Budget calculation
    ------------------
    For auto presets ("light" / "medium" / "heavy"), the budget is computed
    as::

        budget = V + N * (2*M + V + W)

    where V = valset size, M = minibatch size, W = reflection weight,
    N = number of proposal iterations (derived from the preset).

    Each proposal iteration is budgeted at its maximum (all-accepted) cost
    so that total resource consumption is consistent regardless of the
    candidate acceptance rate:

    - All accepted (case 1): N iterations, each consuming ``2*M + V + W``
      weighted units.  Budget is exhausted in exactly N iterations.
    - All rejected (case 2): each iteration consumes only ``2*M + W``
      weighted units (no full eval).  The same budget funds
      ``N * (2*M + V + W) / (2*M + W)`` iterations — more iterations,
      but each is cheaper.

    In both cases the total weighted budget consumed is the same, which
    translates to similar wall-clock time and token usage (verified by
    ``test_budget_weight_end_to_end_latency``).
    """

    AUTO_BUDGET_SETTINGS = AUTO_BUDGET_SETTINGS

    def __init__(
        self,
        reflection_lm: "SnowflakeLLM",
        *,
        max_budget: int,
        reflection_call_weight: int = DEFAULT_REFLECTION_CALL_WEIGHT,
    ) -> None:
        self.reflection_lm = reflection_lm
        self.reflection_call_weight = reflection_call_weight
        self.max_budget = max_budget

    @classmethod
    def resolve_budget(
        cls,
        auto: Literal["ultra-light", "light", "medium", "heavy", "demo"],
        num_components: int,
        valset_size: int,
        reflection_minibatch_size: int = DEFAULT_REFLECTION_MINIBATCH_SIZE,
        reflection_call_weight: int = DEFAULT_REFLECTION_CALL_WEIGHT,
    ) -> int:
        """Compute a budget from an auto preset without a live ``reflection_lm``.

        Each proposal iteration costs (in weighted budget units):
          - ``2 * M``  metric calls  (current + new candidate on minibatch)
          - ``W``      weighted reflection cost  (LLM proposes new candidate)
          - ``V``      metric calls  (full valset eval, only if accepted)

        The budget is ``V + N * (2*M + V + W)`` so that N proposals are
        fully funded in the all-accepted case.  In the all-rejected case
        the same budget funds more iterations via cheaper reflection-only
        rounds.
        """
        import math

        if auto not in cls.AUTO_BUDGET_SETTINGS:
            raise ValueError(
                f"auto must be one of {list(cls.AUTO_BUDGET_SETTINGS.keys())}"
            )

        num_candidates = cls.AUTO_BUDGET_SETTINGS[auto]["n"]
        N = int(
            max(
                2 * (num_components * 2) * math.log2(num_candidates),
                1.5 * num_candidates,
            )
        )

        V = valset_size
        M = reflection_minibatch_size
        W = reflection_call_weight

        return V + N * (2 * M + V + W)

    # ------------------------------------------------------------------
    # Dynamic weight estimation
    # ------------------------------------------------------------------

    @staticmethod
    def estimate_reflection_weight(
        seed_candidate: dict[str, str],
        trainset: list["SnowflakeDataInst"],
        reflection_minibatch_size: int = DEFAULT_REFLECTION_MINIBATCH_SIZE,
        metric_name: str = "exact_match",
        metric_kwargs: dict | None = None,
    ) -> int:
        """Estimate reflection_call_weight from prompt-length ratio.

        Compares the character length of a representative reflection prompt
        (built with GEPA's real ``InstructionProposalSignature`` template)
        to the total prompt length of a single metric call.  LLM inference
        cost scales roughly with input token count, so the prompt-length
        ratio is a practical proxy for relative wall-clock cost without
        needing to call Snowflake.

        When ``metric_name`` is ``"llm_judge"`` (or a custom metric UDF),
        each metric call involves two LLM invocations — the task UDF plus
        the judge evaluation.  The judge prompt length is added to the
        per-metric-call cost so the weight correctly reflects the higher
        cost of judge-based metrics.

        Returns at least 1.
        """
        from gepa.strategies.instruction_proposal import InstructionProposalSignature

        instruction = next(iter(seed_candidate.values()))

        # --- Per-metric-call prompt cost ---
        # Task prompt: instruction + one user input
        if trainset:
            avg_input_len = sum(
                sum(len(str(v)) for v in item["inputs"].values()) for item in trainset
            ) / len(trainset)
            avg_answer_len = sum(
                len(str(item.get("answer", ""))) for item in trainset
            ) / len(trainset)
        else:
            avg_input_len = 0
            avg_answer_len = 0

        task_prompt_len = len(instruction) + avg_input_len

        # Judge prompt (only for llm_judge): adds a second LLM call per item
        judge_prompt_len: float = 0
        if metric_name == "llm_judge":
            task_desc = (metric_kwargs or {}).get("task_description", "")
            # System template + per-row user template are both sent every row.
            judge_template_overhead = len(_LLM_JUDGE_CONTINUOUS_TEMPLATE) + len(
                _LLM_JUDGE_USER_TEMPLATE
            )
            if (metric_kwargs or {}).get("file_columns"):
                judge_template_overhead += len(_LLM_JUDGE_FILE_ADDENDUM)
            judge_prompt_len = int(
                judge_template_overhead
                + len(task_desc)
                + avg_answer_len
                + avg_answer_len  # predicted ≈ answer length
            )

        metric_prompt_len = task_prompt_len + judge_prompt_len

        if metric_prompt_len == 0:
            return 1

        # --- Reflection prompt cost ---
        sample = trainset[:reflection_minibatch_size]
        dataset_with_feedback = [
            {
                "Inputs": "\n".join(f"{k}: {v}" for k, v in item["inputs"].items()),
                "Generated Outputs": item.get("answer", ""),
                "Feedback": "Needs improvement.",
            }
            for item in sample
        ]
        reflection_prompt = InstructionProposalSignature.prompt_renderer(
            {
                "current_instruction_doc": instruction,
                "dataset_with_feedback": dataset_with_feedback,
                "prompt_template": None,
            }
        )
        reflection_prompt_len = (
            len(reflection_prompt)
            if isinstance(reflection_prompt, str)
            else sum(len(str(part.get("content", ""))) for part in reflection_prompt)
        )

        return max(1, round(reflection_prompt_len / metric_prompt_len))

    # ------------------------------------------------------------------
    # Stop condition
    # ------------------------------------------------------------------

    def __call__(self, gepa_state: GEPAState) -> bool:
        total = (
            gepa_state.total_num_evals
            + self.reflection_lm.call_count * self.reflection_call_weight
        )
        return total >= self.max_budget


def split_dataset(
    dataset: list[SnowflakeDataInst],
    validation_fraction: float,
    seed: int = DEFAULT_SPLIT_SEED,
) -> tuple[list[SnowflakeDataInst], list[SnowflakeDataInst]]:
    """Split dataset into validation and training sets.

    Args:
        dataset: Full dataset to split
        validation_fraction: Fraction for validation (e.g., 0.667 = 2/3)
        seed: Random seed for reproducibility

    Returns:
        (valset, trainset) - validation set and training set

    """
    shuffled = dataset.copy()
    random.Random(seed).shuffle(shuffled)

    split_idx = int(len(shuffled) * validation_fraction)
    valset = shuffled[:split_idx]
    trainset = shuffled[split_idx:]

    if len(trainset) == 0:
        trainset = valset[: max(1, len(valset) // 3)]

    return valset, trainset


# ---------------------------------------------------------------------------
# Backwards-compatible re-exports from optimize_prompt.py
# These were originally defined here and are imported by tests and external
# consumers.  Uses importlib to avoid the inline bundler stripping the import.
# In inline SPROC mode these functions are present but never called (body mode
# uses its own extract_model_from_ddl_string defined in optimize_body.py).
# ---------------------------------------------------------------------------


def extract_prompt_from_ddl_string(ddl: str, function_name: str = "") -> str:
    """Re-export: see optimize_prompt.extract_prompt_from_ddl_string."""
    import importlib

    mod = importlib.import_module("snowflake_ai_optimize.gepa.optimize_prompt")
    return str(mod.extract_prompt_from_ddl_string(ddl, function_name))


def extract_model_from_ddl_string(ddl: str, function_name: str = "") -> str:
    """Re-export: see optimize_prompt.extract_model_from_ddl_string."""
    import importlib

    mod = importlib.import_module("snowflake_ai_optimize.gepa.optimize_prompt")
    return str(mod.extract_model_from_ddl_string(ddl, function_name))
