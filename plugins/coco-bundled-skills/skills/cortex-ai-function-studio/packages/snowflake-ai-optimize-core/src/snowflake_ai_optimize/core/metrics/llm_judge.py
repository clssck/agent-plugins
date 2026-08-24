# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""LLM-judge metric implementation."""

from typing import Any

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.metrics.custom_udf import parse_metric_result
from snowflake_ai_optimize.core.session import RobustAIComplete

LLM_JUDGE_DEFAULT_MODEL = "claude-sonnet-4-5"
LLM_JUDGE_DEFAULT_TEMP = 0.0
LLM_JUDGE_DEFAULT_MAX_TOKENS = 8192
# System-message template: static instructions form a constant prefix the
# serving layer can prefix-cache.  ``task_description`` is the only system-side
# variable, so it goes LAST — the task-independent boilerplate above it can then
# be reused as a cached prefix across different functions/runs, not just across
# rows of one batch.  The per-row Expected/Predicted pair lives in the user
# message (see ``_LLM_JUDGE_USER_TEMPLATE``).
_LLM_JUDGE_BINARY_TEMPLATE = (
    "Evaluate if the prediction is semantically correct.\n\n"
    "You will be given an expected output and a predicted output. "
    "Score 1 if the prediction is correct, 0 if incorrect.\n\n"
    "Task: {task_description}"
)
# Per-row user-message template: only the varying Expected/Predicted pair.
_LLM_JUDGE_USER_TEMPLATE = "Expected: {expected}\nPredicted: {predicted}"
_LLM_JUDGE_BINARY_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "description": "1 if correct, 0 if incorrect",
        },
        "feedback": {
            "type": "string",
            "description": "Brief explanation for the score",
        },
    },
    "required": ["score", "feedback"],
    "additionalProperties": False,
}
_LLM_JUDGE_CONTINUOUS_TEMPLATE = (
    "You are a precise grading assistant. Evaluate how well the prediction "
    "matches the expected output for the given task.\n\n"
    "You will be given an expected output and a predicted output. "
    "Score from 0.0 to 1.0. Use the full range — assign any value that "
    "reflects the degree of correctness.\n\n"
    "Rubric:\n"
    "- 1.0: Semantically identical or fully correct.\n"
    "- 0.7-0.9: Mostly correct with minor differences that don't change meaning.\n"
    "- 0.4-0.6: Partially correct — captures some key information but misses important parts.\n"
    "- 0.1-0.3: Mostly wrong but contains a small relevant element.\n"
    "- 0.0: Completely wrong or unrelated.\n\n"
    "Use these as guidelines, not hard boundaries. "
    "Prioritize semantic meaning over surface-level wording.\n\n"
    "Task: {task_description}"
)
_LLM_JUDGE_CONTINUOUS_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "number",
            "description": "Score from 0.0 to 1.0",
        },
        "feedback": {
            "type": "string",
            "description": "Brief explanation for the score",
        },
    },
    "required": ["score", "feedback"],
    "additionalProperties": False,
}


def _parse_binary_result(raw: object) -> tuple[float, str]:
    """Parse a structured JSON judge response into a binary (0/1) score."""
    score, feedback = parse_metric_result(raw)
    return (1.0 if score >= 0.5 else 0.0), feedback


def _parse_continuous_result(raw: object) -> tuple[float, str]:
    """Parse a structured JSON judge response into (score, feedback).

    Reuses ``_parse_metric_result`` (shared with custom metric UDFs) and
    clamps the score to [0.0, 1.0].
    """
    score, feedback = parse_metric_result(raw)
    return max(0.0, min(1.0, score)), feedback


_LLM_JUDGE_FILE_ADDENDUM = (
    "\n\nThe attached file shows the actual input. Use it to verify the prediction."
)


def llm_judge_batch(
    items: list[tuple[str, str]],
    session: Session,
    task_description: str = "",
    model_name: str = LLM_JUDGE_DEFAULT_MODEL,
    temperature: float = LLM_JUDGE_DEFAULT_TEMP,
    max_tokens: int = LLM_JUDGE_DEFAULT_MAX_TOKENS,
    scoring_mode: str = "binary",
    file_paths: list[str] | None = None,
    stage_name: str | list[str] | None = None,
    **_kwargs: Any,
) -> list[tuple[float, str]]:
    """Batched LLM judge -- evaluates all items in a single SQL query.

    This is the core implementation that all llm_judge calls use.
    Even single-item calls go through this for consistency.

    Args:
        items: List of (expected, predicted) tuples to evaluate.
        session: Snowpark session for calling AI_COMPLETE.
        task_description: Description of the task for context.
        model_name: Model to use for evaluation.
        temperature: Temperature for model inference.
        max_tokens: Maximum tokens for response.
        scoring_mode: ``"binary"`` (default) returns 1.0/0.0.
            ``"continuous"`` returns 0.0--1.0, giving GEPA richer
            gradient for optimization.  Both modes use
            structured JSON output.
        file_paths: Optional list of stage-relative file paths,
            one per item.  When provided together with ``stage_name``,
            the judge receives the file via ``TO_FILE()`` for
            multimodal evaluation.
        stage_name: Snowflake stage for the files. Pass a ``str``
            for a single stage or ``list[str]`` for per-row stages.

    Returns:
        List of (score, feedback) tuples in the same order as input items.

    """
    if not items:
        return []

    continuous = scoring_mode == "continuous"
    system_template = (
        _LLM_JUDGE_CONTINUOUS_TEMPLATE if continuous else _LLM_JUDGE_BINARY_TEMPLATE
    )
    parser = _parse_continuous_result if continuous else _parse_binary_result

    multimodal = bool(file_paths and stage_name)
    if multimodal:
        assert file_paths is not None
        if len(file_paths) != len(items):
            raise ValueError(
                f"file_paths length ({len(file_paths)}) "
                f"must match items length ({len(items)})"
            )

    # Static instructions (task, rubric, scoring guidance, file note) go in the
    # system message so they form a constant prefix shared across every judged
    # row; only the per-row Expected/Predicted pair varies in the user message.
    system_prompt = system_template.format(task_description=task_description)
    if multimodal:
        system_prompt += _LLM_JUDGE_FILE_ADDENDUM

    judge_prompts = [
        _LLM_JUDGE_USER_TEMPLATE.format(expected=expected, predicted=predicted)
        for expected, predicted in items
    ]

    responses = RobustAIComplete.call_ai_complete(
        session,
        model=model_name,
        user_prompts=judge_prompts,
        temperature=temperature,
        max_tokens=max_tokens,
        response_schema=_LLM_JUDGE_CONTINUOUS_SCHEMA
        if continuous
        else _LLM_JUDGE_BINARY_SCHEMA,
        system_prompt=system_prompt,
        file_paths=file_paths if multimodal else None,
        stage_name=stage_name if multimodal else None,
    )

    outputs = [parser(r) for r in (responses or [])]

    if len(outputs) != len(items):
        raise RuntimeError(
            f"LLM judge returned {len(outputs)} responses for {len(items)} inputs"
        )

    return outputs


def llm_judge_core(
    expected: str,
    predicted: str,
    session: Session | None = None,
    *,
    task_description: str = "",
    model_name: str = LLM_JUDGE_DEFAULT_MODEL,
    temperature: float = LLM_JUDGE_DEFAULT_TEMP,
    max_tokens: int = LLM_JUDGE_DEFAULT_MAX_TOKENS,
    scoring_mode: str = "binary",
    **kwargs: Any,
) -> tuple[float, str]:
    """Use an LLM to evaluate semantic correctness.

    Internally uses batched evaluation for consistency (even for single items).
    Extra ``kwargs`` (e.g. ``file_paths``, ``stage_name``) are
    forwarded to :func:`llm_judge_batch`.
    """
    if session is None:
        raise ValueError("llm_judge requires a session")
    results = llm_judge_batch(
        [(expected, predicted)],
        session,
        task_description,
        model_name,
        temperature,
        max_tokens,
        scoring_mode=scoring_mode,
        **kwargs,
    )
    return results[0] if results else (0.0, "Evaluation failed")
