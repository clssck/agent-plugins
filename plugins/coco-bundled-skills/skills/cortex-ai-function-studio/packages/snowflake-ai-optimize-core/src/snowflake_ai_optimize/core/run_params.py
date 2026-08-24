# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Pydantic model for experiment run parameters.

Replaces the procedural ``build_run_params`` function with a declarative
BaseModel whose fields are the canonical parameter schema.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel


class RunParams(BaseModel):
    """Typed experiment run parameters.

    Attributes:
        function_impl: The candidate function implementation source code.
        model: Model name used for this run.
        iteration: The per-model/population candidate index within a single
            model's optimization ("0" for the seed). Provenance for the
            algorithm — NOT the number encoded in the run name (see
            ``global_iteration``).
        run_type: The run's role: "seed", "iteration", or "rejected". A
            metadata label; run names no longer encode the role.
        global_iteration: The global, cross-model atomic counter value the
            run *name* encodes (``ITER_<global_iteration>``); 0 for the single
            ``SEED`` run.
        per_model_stats: JSON string of aggregate optimization totals keyed by
            model. Stamped on the single ``SEED`` run only.
        parent_candidate: The parent candidate's run name.

    """

    # Uniform precision for all float serialization. Presentation layer
    # decides display precision.
    FLOAT_PRECISION: ClassVar[int] = 6

    function_impl: str
    model: str
    iteration: str
    parent_candidate: str | None = None

    is_full_eval: bool = True
    status: str = "completed"
    run_type: Literal["seed", "iteration", "rejected"] | None = None

    function_name: str | None = None
    score_source: str | None = None
    reflection_model: str | None = None
    error_message: str | None = None
    error_type: Literal["user", "internal"] | None = None
    rejection_kind: str | None = None
    rejection_reason: str | None = None
    extra_metadata: str | None = None
    per_model_stats: str | None = None
    metric_name: str | None = None
    custom_metric_udf: str | None = None

    num_examples: int | None = None
    avg_output_chars: int | None = None
    sample_size: int | None = None
    total_candidates: int | None = None
    total_metric_calls: int | None = None
    total_reflection_calls: int | None = None
    metric_call_count: int | None = None
    reflection_call_count: int | None = None
    udf_compile_count: int | None = None
    udf_exec_count: int | None = None
    experiment_count: int | None = None
    artifact_count: int | None = None
    test_eval_metric_calls: int | None = None
    test_eval_reflection_calls: int | None = None
    test_eval_udf_compile_calls: int | None = None
    test_eval_udf_exec_calls: int | None = None
    total_udf_prompt_tokens: int | None = None
    total_udf_completion_tokens: int | None = None
    test_eval_udf_prompt_tokens: int | None = None
    test_eval_udf_completion_tokens: int | None = None
    total_udf_compile_calls: int | None = None
    total_udf_exec_calls: int | None = None
    total_experiment_calls: int | None = None
    total_artifact_calls: int | None = None
    experiment_schema_version: int | None = None
    subsample_size: int | None = None
    gepa_iteration: int | None = None
    global_iteration: int | None = None
    iter_input_chars: int | None = None
    iter_output_chars: int | None = None
    new_cand_eval_input_chars: int | None = None
    new_cand_eval_output_chars: int | None = None
    new_cand_eval_minibatch_size: int | None = None
    parent_eval_input_chars: int | None = None
    parent_eval_output_chars: int | None = None
    parent_eval_minibatch_size: int | None = None
    iter_eval_prompt_tokens: int | None = None
    iter_eval_completion_tokens: int | None = None
    iter_reflection_prompt_tokens_est: int | None = None
    iter_reflection_completion_tokens_est: int | None = None
    new_cand_eval_prompt_tokens: int | None = None
    new_cand_eval_completion_tokens: int | None = None
    parent_eval_prompt_tokens: int | None = None
    parent_eval_completion_tokens: int | None = None
    phase_reflection_prompt_tokens_est: int | None = None
    phase_reflection_completion_tokens_est: int | None = None
    total_reflection_prompt_tokens_est: int | None = None
    total_reflection_completion_tokens_est: int | None = None

    elapsed_seconds: float | None = None
    iter_seconds: float | None = None
    metric_seconds_total: float | None = None
    metric_seconds_avg: float | None = None
    metric_seconds_p95: float | None = None
    reflection_seconds_total: float | None = None
    reflection_seconds_avg: float | None = None
    udf_compile_seconds_total: float | None = None
    udf_exec_seconds_total: float | None = None
    experiment_seconds_total: float | None = None
    artifact_seconds_total: float | None = None
    total_metric_seconds: float | None = None
    total_reflection_seconds: float | None = None
    total_udf_compile_seconds: float | None = None
    total_udf_exec_seconds: float | None = None
    total_experiment_seconds: float | None = None
    total_artifact_seconds: float | None = None
    test_eval_metric_seconds: float | None = None
    test_eval_reflection_seconds: float | None = None
    test_eval_udf_compile_seconds: float | None = None
    test_eval_udf_exec_seconds: float | None = None
    subsample_score_old: float | None = None
    subsample_score_new: float | None = None
    subsample_score_new_mean: float | None = None
    parent_eval_seconds: float | None = None
    phase_reflection_seconds: float | None = None
    new_cand_eval_seconds: float | None = None
    iter_dollars: float | None = None

    def to_param_list(self) -> list[dict[str, str]]:
        """Serialize to the experiment run parameter list format.

        Iterates model fields and dispatches serialization based on runtime
        type. Skips None values.

        Returns:
            A list of ``{"name": ..., "value": ...}`` dicts suitable for
            passing to ``add_experiment_run``.

        """
        params: list[dict[str, str]] = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool):
                params.append({"name": name, "value": str(value).lower()})
            elif isinstance(value, float):
                params.append(
                    {"name": name, "value": str(round(value, self.FLOAT_PRECISION))}
                )
            else:
                params.append({"name": name, "value": str(value)})
        return params

    @classmethod
    def from_param_dict(cls, params: dict[str, str]) -> RunParams:
        """Deserializes from a flat string-keyed param dictionary.

        Args:
            params: A mapping of parameter names to string values, as stored
                in experiment run parameters.

        Returns:
            A ``RunParams`` instance with fields coerced to proper types.

        """
        known_fields = set(cls.model_fields.keys())
        filtered = {k: v for k, v in params.items() if k in known_fields}
        return cls.model_validate(filtered)
