# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for MaxTotalBudgetStopper and split_dataset.

Run:
    uv run --group test pytest tests/test_budget_and_split.py -v
"""

from __future__ import annotations

import math
from typing import ClassVar
from unittest.mock import MagicMock, patch

import pytest

from snowflake_ai_optimize.gepa.optimize import (
    MaxTotalBudgetStopper,
    split_dataset,
)


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed for unit tests."""
    yield


# ---------------------------------------------------------------------------
# resolve_budget
# ---------------------------------------------------------------------------


class TestResolveBudget:
    """Verify budget = V + N * (2*M + V + W) for each auto preset."""

    NUM_COMPONENTS = 2
    VALSET_SIZE = 20
    MINIBATCH = 10
    WEIGHT = 1

    @staticmethod
    def _expected_budget(n: int, num_components: int, V: int, M: int, W: int) -> int:
        N = int(max(2 * (num_components * 2) * math.log2(n), 1.5 * n))
        return V + N * (2 * M + V + W)

    def test_light(self):
        budget = MaxTotalBudgetStopper.resolve_budget(
            auto="light",
            num_components=self.NUM_COMPONENTS,
            valset_size=self.VALSET_SIZE,
            reflection_minibatch_size=self.MINIBATCH,
            reflection_call_weight=self.WEIGHT,
        )
        expected = self._expected_budget(
            6, self.NUM_COMPONENTS, self.VALSET_SIZE, self.MINIBATCH, self.WEIGHT
        )
        assert budget == expected

    def test_medium(self):
        budget = MaxTotalBudgetStopper.resolve_budget(
            auto="medium",
            num_components=self.NUM_COMPONENTS,
            valset_size=self.VALSET_SIZE,
            reflection_minibatch_size=self.MINIBATCH,
            reflection_call_weight=self.WEIGHT,
        )
        expected = self._expected_budget(
            12, self.NUM_COMPONENTS, self.VALSET_SIZE, self.MINIBATCH, self.WEIGHT
        )
        assert budget == expected

    def test_heavy(self):
        budget = MaxTotalBudgetStopper.resolve_budget(
            auto="heavy",
            num_components=self.NUM_COMPONENTS,
            valset_size=self.VALSET_SIZE,
            reflection_minibatch_size=self.MINIBATCH,
            reflection_call_weight=self.WEIGHT,
        )
        expected = self._expected_budget(
            18, self.NUM_COMPONENTS, self.VALSET_SIZE, self.MINIBATCH, self.WEIGHT
        )
        assert budget == expected

    def test_invalid_auto_raises(self):
        with pytest.raises(ValueError, match="auto must be one of"):
            MaxTotalBudgetStopper.resolve_budget(
                auto="thorough",
                num_components=1,
                valset_size=10,
            )


# ---------------------------------------------------------------------------
# estimate_reflection_weight
# ---------------------------------------------------------------------------


class TestEstimateReflectionWeight:
    """Verify prompt-length-ratio weight estimation."""

    SEED_CANDIDATE: ClassVar[dict[str, str]] = {"instruction": "Classify sentiment."}
    TRAINSET: ClassVar[list[dict]] = [
        {"inputs": {"text": "Great product!"}, "answer": "positive"},
        {"inputs": {"text": "Terrible service."}, "answer": "negative"},
    ]

    @patch(
        "gepa.strategies.instruction_proposal.InstructionProposalSignature.prompt_renderer",
        return_value="x" * 500,
    )
    def test_empty_trainset_and_empty_instruction_returns_one(self, _mock_renderer):
        # metric_prompt_len == 0 when instruction is empty and trainset is empty
        weight = MaxTotalBudgetStopper.estimate_reflection_weight(
            seed_candidate={"instruction": ""},
            trainset=[],
        )
        assert weight == 1

    @patch(
        "gepa.strategies.instruction_proposal.InstructionProposalSignature.prompt_renderer",
    )
    def test_exact_match_weight(self, mock_renderer):
        # Reflection prompt = 600 chars; metric prompt = instruction + avg_input
        mock_renderer.return_value = "r" * 600
        instruction_len = len(self.SEED_CANDIDATE["instruction"])
        avg_input_len = (len("Great product!") + len("Terrible service.")) / 2
        metric_prompt_len = instruction_len + avg_input_len

        expected = max(1, round(600 / metric_prompt_len))

        weight = MaxTotalBudgetStopper.estimate_reflection_weight(
            seed_candidate=self.SEED_CANDIDATE,
            trainset=self.TRAINSET,
            metric_name="exact_match",
        )
        assert weight == expected

    @patch(
        "gepa.strategies.instruction_proposal.InstructionProposalSignature.prompt_renderer",
    )
    def test_llm_judge_includes_judge_overhead(self, mock_renderer):
        from snowflake_ai_optimize.core.metrics.llm_judge import (
            _LLM_JUDGE_CONTINUOUS_TEMPLATE,
            _LLM_JUDGE_USER_TEMPLATE,
        )

        mock_renderer.return_value = "r" * 1000
        instruction_len = len(self.SEED_CANDIDATE["instruction"])
        avg_input_len = (len("Great product!") + len("Terrible service.")) / 2
        avg_answer_len = (len("positive") + len("negative")) / 2

        task_prompt_len = instruction_len + avg_input_len
        judge_template_overhead = len(_LLM_JUDGE_CONTINUOUS_TEMPLATE) + len(
            _LLM_JUDGE_USER_TEMPLATE
        )
        task_desc = "classify"
        judge_prompt_len = (
            judge_template_overhead + len(task_desc) + avg_answer_len + avg_answer_len
        )
        metric_prompt_len = task_prompt_len + judge_prompt_len

        expected = max(1, round(1000 / metric_prompt_len))

        weight = MaxTotalBudgetStopper.estimate_reflection_weight(
            seed_candidate=self.SEED_CANDIDATE,
            trainset=self.TRAINSET,
            metric_name="llm_judge",
            metric_kwargs={"task_description": "classify"},
        )
        assert weight == expected

    @patch(
        "gepa.strategies.instruction_proposal.InstructionProposalSignature.prompt_renderer",
    )
    def test_llm_judge_with_file_columns(self, mock_renderer):
        from snowflake_ai_optimize.core.metrics.llm_judge import (
            _LLM_JUDGE_CONTINUOUS_TEMPLATE,
            _LLM_JUDGE_FILE_ADDENDUM,
            _LLM_JUDGE_USER_TEMPLATE,
        )

        mock_renderer.return_value = "r" * 1000
        instruction_len = len(self.SEED_CANDIDATE["instruction"])
        avg_input_len = (len("Great product!") + len("Terrible service.")) / 2
        avg_answer_len = (len("positive") + len("negative")) / 2

        task_prompt_len = instruction_len + avg_input_len
        judge_template_overhead = (
            len(_LLM_JUDGE_CONTINUOUS_TEMPLATE)
            + len(_LLM_JUDGE_USER_TEMPLATE)
            + len(_LLM_JUDGE_FILE_ADDENDUM)
        )
        judge_prompt_len = judge_template_overhead + avg_answer_len + avg_answer_len
        metric_prompt_len = task_prompt_len + judge_prompt_len

        expected = max(1, round(1000 / metric_prompt_len))

        weight = MaxTotalBudgetStopper.estimate_reflection_weight(
            seed_candidate=self.SEED_CANDIDATE,
            trainset=self.TRAINSET,
            metric_name="llm_judge",
            metric_kwargs={"file_columns": ["img"]},
        )
        assert weight == expected


# ---------------------------------------------------------------------------
# __call__ (stop condition)
# ---------------------------------------------------------------------------


class TestBudgetStopperCall:
    """Verify weighted total comparison against max_budget."""

    def _make_stopper(self, call_count: int, max_budget: int) -> MaxTotalBudgetStopper:
        lm = MagicMock()
        lm.call_count = call_count
        return MaxTotalBudgetStopper(
            reflection_lm=lm,
            max_budget=max_budget,
            reflection_call_weight=1,
        )

    def test_under_budget_returns_false(self):
        stopper = self._make_stopper(call_count=5, max_budget=100)
        state = MagicMock()
        state.total_num_evals = 90
        # 90 + 5*1 = 95 < 100
        assert stopper(state) is False

    def test_exact_boundary_returns_true(self):
        stopper = self._make_stopper(call_count=5, max_budget=100)
        state = MagicMock()
        state.total_num_evals = 95
        # 95 + 5*1 = 100 >= 100
        assert stopper(state) is True

    def test_over_budget_returns_true(self):
        stopper = self._make_stopper(call_count=5, max_budget=100)
        state = MagicMock()
        state.total_num_evals = 99
        # 99 + 5*1 = 104 >= 100
        assert stopper(state) is True


# ---------------------------------------------------------------------------
# split_dataset
# ---------------------------------------------------------------------------


class TestSplitDataset:
    """Verify validation/training split behaviour."""

    ITEMS: ClassVar[list[dict]] = [
        {"inputs": {"text": str(i)}, "answer": str(i)} for i in range(10)
    ]

    def test_half_split_sizes(self):
        valset, trainset = split_dataset(self.ITEMS, validation_fraction=0.5)
        assert len(valset) == 5
        assert len(trainset) == 5

    def test_deterministic_with_same_seed(self):
        v1, t1 = split_dataset(self.ITEMS, validation_fraction=0.5, seed=99)
        v2, t2 = split_dataset(self.ITEMS, validation_fraction=0.5, seed=99)
        assert v1 == v2
        assert t1 == t2

    def test_different_seed_different_split(self):
        v1, _ = split_dataset(self.ITEMS, validation_fraction=0.5, seed=1)
        v2, _ = split_dataset(self.ITEMS, validation_fraction=0.5, seed=2)
        assert v1 != v2

    def test_fraction_one_fallback_trainset(self):
        valset, trainset = split_dataset(self.ITEMS, validation_fraction=1.0)
        assert len(valset) == 10
        # trainset gets fallback: valset[:max(1, len(valset)//3)]
        assert len(trainset) == max(1, len(valset) // 3)

    def test_fraction_zero_all_train(self):
        valset, trainset = split_dataset(self.ITEMS, validation_fraction=0.0)
        assert len(valset) == 0
        assert len(trainset) == 10


# ---------------------------------------------------------------------------
# run_optimization — validation_fraction bounds
# ---------------------------------------------------------------------------


class TestRunOptimizationValidationFractionBounds:
    """Verify run_optimization rejects validation_fraction <= 0.0 or >= 1.0."""

    COMMON_KWARGS: ClassVar[dict] = dict(
        function_name="DB.SCHEMA.MY_FUNC",
        training_table="DB.SCHEMA.TRAIN",
        label_column="EXPECTED",
        input_columns=["TEXT"],
        metric_name="exact_match",
        models=["claude-sonnet-4-6"],
        reflection_model="claude-sonnet-4-6",
    )

    @pytest.mark.parametrize(
        "fraction, expected_snippet",
        [
            (0.0, "greater than 0.0"),
            (1.0, "less than 1.0"),
            (0.5, None),
        ],
    )
    def test_validation_fraction_bounds(self, fraction, expected_snippet):
        from handlers.optimize_handler import run_optimization

        session = MagicMock()
        try:
            result = run_optimization(
                session, **self.COMMON_KWARGS, validation_fraction=fraction
            )
        except Exception:
            # Valid fractions proceed past our guard into Snowflake-dependent
            # code that crashes with a mock session — that's fine.
            assert expected_snippet is None
            return

        if expected_snippet is not None:
            assert result["status"] == "failed"
            assert expected_snippet in result["error"]
        else:
            if isinstance(result, dict) and result.get("status") == "failed":
                assert "validation_fraction" not in result.get("error", "")
