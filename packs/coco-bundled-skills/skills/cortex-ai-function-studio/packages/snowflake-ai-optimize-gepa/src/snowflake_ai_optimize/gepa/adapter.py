# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Snowflake adapter for GEPA optimization.

This module provides the adapter classes that connect GEPA's optimization
engine to Snowflake AI functions. During optimization, temporary functions
are created with candidate model/prompt combinations baked in, rather than
overriding parameters at call time.
"""

import hashlib
import json
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypedDict

from snowflake.snowpark import Session

from gepa.core.adapter import EvaluationBatch, GEPAAdapter
from snowflake_ai_optimize.core.constants import STAGE_KEY_PREFIX
from snowflake_ai_optimize.core.evaluation import build_eval_detail_record
from snowflake_ai_optimize.core.metrics.utils import (
    build_object_construct_expr,
    get_table_column_names,
    resolve_expected_column,
    resolve_multi_output_columns,
    to_text,
    validate_input_columns,
)
from snowflake_ai_optimize.core.session import RobustAIComplete
from snowflake_ai_optimize.core.sql_utils import FunctionDefinition, quote_identifier
from snowflake_ai_optimize.core.stage import (
    file_type_param_names,
    parse_file_value,
    stage_key,
)
from snowflake_ai_optimize.core.temp_ai_function import TempAIFunction
from snowflake_ai_optimize.core.timing import (
    _get_evaluate_hooks,
    get_active_tracker,
)
from snowflake_ai_optimize.core.types import SnowflakeDataInst

logger = logging.getLogger(__name__)

# Base backoff (seconds) between reflection AI_COMPLETE retries. The nth retry
# waits ``REFLECTION_RETRY_BACKOFF_SECONDS * n`` so transient throttling has a
# moment to clear before the next attempt. Only used when a caller opts into
# reflection retries by setting ``SnowflakeLLM.max_attempts > 1``.
REFLECTION_RETRY_BACKOFF_SECONDS = 2.0


class SnowflakeTrajectory(TypedDict):
    """Trajectory capturing execution details for reflection."""

    data: SnowflakeDataInst
    full_assistant_response: str
    feedback: str


class SnowflakeRolloutOutput(TypedDict):
    """Output from evaluating a candidate."""

    full_assistant_response: str


SnowflakeReflectiveRecord = TypedDict(
    "SnowflakeReflectiveRecord",
    {
        "Inputs": str,
        "Generated Outputs": str,
        "Feedback": str,
    },
)


# Truncation cap for captured per-row detail fields (matches core evaluate()).
_EVAL_DETAIL_MAX_LENGTH = 500


def candidate_detail_key(candidate_text: str) -> str:
    """Stable key linking an adapter eval to the run the tracker persists.

    Both sides hash the *pre-swap* candidate text (the GEPA program body /
    system prompt), so a captured eval can be looked up by the same text the
    ``ProgressiveExperimentTracker`` stores as ``function_impl``.
    """
    return hashlib.sha256((candidate_text or "").encode("utf-8")).hexdigest()


@dataclass
class _CapturedEval:
    """The most recent per-row eval detail captured for one candidate.

    ``subsample`` is True when the candidate was scored on a minibatch smaller
    than the full valset (e.g. a rejected reflective proposal), so a reader can
    tell partial-coverage detail files apart from full-valset ones.
    """

    records: list[dict] = field(default_factory=list)
    subsample: bool = False


class SnowflakeLLM:
    """LLM wrapper using Snowflake AI_COMPLETE.

    Implements the gepa LanguageModel protocol for reflection calls.
    """

    def __init__(
        self,
        session: Session,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> None:
        self.session = session
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.call_count: int = 0
        # Retry / error-capture knobs. Defaults reproduce the original
        # behavior exactly: a single attempt, and a failed reflection call
        # re-raises without being recorded anywhere (GEPA then swallows it and
        # continues). Callers that want a failed reflection to be fatal — the
        # spec-driven EXECUTE EXPERIMENT path — bump ``max_attempts`` and attach
        # an ``error_sink`` list so the final error is observable after the loop.
        self.max_attempts: int = 1
        self.error_sink: list[Exception] | None = None

    def __call__(self, prompt: str | list[dict[str, Any]]) -> str:
        self.call_count += 1
        tracker = get_active_tracker()
        start = time.perf_counter()
        responses = None
        if isinstance(prompt, list):
            system_parts = [m["content"] for m in prompt if m.get("role") == "system"]
            user_parts = [m["content"] for m in prompt if m.get("role") != "system"]
            system_prompt: str | None = "\n".join(system_parts) or None
            user_prompt = "\n".join(user_parts)
        else:
            system_prompt = None
            user_prompt = prompt
        try:
            # Reflection is the engine of optimization: when a reflection call
            # fails there is no candidate for the next iteration. Retry a few
            # times (``max_attempts``) to ride out transient AI_COMPLETE errors
            # before giving up. ``max_attempts`` defaults to 1, so every caller
            # that does not opt in behaves exactly as before (one attempt).
            attempts = max(1, self.max_attempts)
            last_exc: Exception | None = None
            for attempt in range(1, attempts + 1):
                try:
                    responses = RobustAIComplete.call_ai_complete(
                        self.session,
                        model=self.model,
                        user_prompts=[user_prompt],
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                        response_schema=None,
                        system_prompt=system_prompt,
                    )
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "Reflection AI_COMPLETE call failed (attempt %d/%d): %s",
                        attempt,
                        attempts,
                        exc,
                    )
                    if attempt < attempts:
                        time.sleep(REFLECTION_RETRY_BACKOFF_SECONDS * attempt)
            if last_exc is not None:
                # Every attempt failed. Log the full stacktrace once here (the
                # per-attempt warnings above are message-only), record the error
                # for a caller that opted in (the spec-driven path drains
                # ``error_sink`` after the GEPA loop and fails the run with this
                # message instead of finishing SUCCEEDED with the error
                # swallowed), then re-raise so GEPA's own handling — skip this
                # proposal, no candidate — is unchanged.
                logger.error(
                    "Reflection AI_COMPLETE call failed after %d attempt(s)",
                    attempts,
                    exc_info=last_exc,
                )
                if self.error_sink is not None:
                    self.error_sink.append(last_exc)
                raise last_exc
        finally:
            if tracker is not None:
                # Char-based token estimate for the reflection LLM
                # call.  Input = full prompt; output = whatever the
                # model returned (may be empty on error / refusal).
                resp_text = ""
                if responses:
                    r0 = responses[0]
                    resp_text = "" if r0 is None else str(r0)
                in_chars = len(user_prompt) + len(system_prompt or "")
                out_chars = len(resp_text)
                tracker.add_chars(self.model, "reflection", in_chars, out_chars)
                # Pass the same char-based token estimate (chars // 4)
                # to ``add_reflection`` so the per-call timeline event
                # carries token info for the new token Gantt chart.
                # Reflection AI_COMPLETE is invoked with
                # ``show_details=False`` so we cannot surface real
                # token counts here — chars/4 is consistent with the
                # proxy used by ``_estimate_iter_credits``.
                tracker.add_reflection(
                    time.perf_counter() - start,
                    prompt_tokens=in_chars // 4,
                    completion_tokens=out_chars // 4,
                    input_chars=in_chars,
                    output_chars=out_chars,
                    model=self.model,
                )
        response = responses[0] if responses else None
        return "" if response is None else str(response)


# ---------------------------------------------------------------------------
# Reflection-backend registry
# ---------------------------------------------------------------------------
# Maps backend name -> (lm_factory, label_fn).
# src registers "ai_complete" (-> SnowflakeLLM, identity label).
# The "agent_run" and "agent_run_single_session" backends are registered
# from dev/modes/snow_gepa_agent_lm.py (imported by the benchmark).

_REFLECTION_REGISTRY: dict[str, tuple[Callable, Callable]] = {}


def register_reflection_backend(
    name: str, lm_factory: Callable, label_fn: Callable
) -> None:
    """Register a reflection LM backend by name.

    Args:
        name: Backend identifier (e.g., ``"ai_complete"``, ``"agent_run"``).
        lm_factory: Callable invoked as
            ``lm_factory(session, model, temperature, max_tokens, **kw)``
            returning an LM object implementing the GEPA LanguageModel
            protocol (``__call__(prompt: str) -> str``).
        label_fn: Callable ``(model: str) -> str`` that formats the
            reflection-model name for experiment params / reports
            (e.g., prefixes ``coco_agent@``).

    """
    _REFLECTION_REGISTRY[name] = (lm_factory, label_fn)


def resolve_reflection_lm(
    reflection_backend: str,
    *,
    session: Any,
    model: str,
    temperature: float,
    max_tokens: int,
    **kwargs: Any,
) -> Any:
    """Instantiate a reflection LM for the given backend.

    Falls back to ``"ai_complete"`` (SnowflakeLLM) for unregistered backends.
    """
    if reflection_backend not in _REFLECTION_REGISTRY:
        return SnowflakeLLM(
            session=session, model=model, temperature=temperature, max_tokens=max_tokens
        )
    lm_factory, _ = _REFLECTION_REGISTRY[reflection_backend]
    return lm_factory(
        session=session,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def label_reflection_model(reflection_model: str, reflection_backend: str) -> str:
    """Format the reflection-model identifier with a backend prefix.

    Prefixes the model name with a backend tag so the benchmark summary /
    experiment params can distinguish reflection backends at a glance.
    The prefix is defined by each backend's registered ``label_fn``; the
    built-in ``ai_complete`` backend returns the model name unchanged.
    """
    if reflection_backend in _REFLECTION_REGISTRY:
        _, label_fn = _REFLECTION_REGISTRY[reflection_backend]
        return str(label_fn(reflection_model))
    return reflection_model


# Register the built-in "ai_complete" backend (SnowflakeLLM, identity label)
# so production SPROCs always have it available without any dev imports.
register_reflection_backend(
    "ai_complete",
    lambda session, model, temperature, max_tokens, **_: SnowflakeLLM(
        session=session, model=model, temperature=temperature, max_tokens=max_tokens
    ),
    lambda model: model,  # identity label
)


class SnowflakeAdapter(
    GEPAAdapter[SnowflakeDataInst, SnowflakeTrajectory, SnowflakeRolloutOutput]
):
    """GEPA adapter for Snowflake AI functions.

    This adapter evaluates candidates by creating temporary functions with
    the candidate model/prompt baked in, then calling the temp function and
    scoring responses using a user-provided evaluator function.
    """

    def __init__(
        self,
        session: Any,
        evaluator: Any,
        function_name: str,
        input_columns: list[str],
        model: str,
        function_def: FunctionDefinition,
        temp_function_name: str,
        file_type_params: list[str] | None = None,
        stage_name: str | None = None,
        full_valset_size: int | None = None,
        eval_detail_buffer: dict[str, _CapturedEval] | None = None,
    ) -> None:
        self.session = session
        self.evaluator = evaluator
        self.function_name = function_name
        self.input_columns = input_columns
        self.model = model
        self.function_def = function_def
        self.temp_function_name = temp_function_name

        if file_type_params is None:
            file_type_params = file_type_param_names(function_def.args) or []
        self._file_type_params = {p.upper() for p in file_type_params}
        self._stage_name = stage_name

        # Per-row eval detail captured from GEPA's *own* evaluations, keyed by
        # candidate_detail_key(system_prompt). No extra Snowflake round-trips —
        # populated from data already computed in ``evaluate``. One instance per
        # model worker thread, so the buffer needs no locking. The experiment
        # tracker drains it to write ``eval_detail.json``; the caller
        # may pass in a shared dict so the tracker (built earlier) reads it.
        self._full_valset_size = full_valset_size
        self._eval_detail_buffer: dict[str, _CapturedEval] = (
            eval_detail_buffer if eval_detail_buffer is not None else {}
        )

    def cleanup(self) -> None:
        """Release resources after optimization.

        Temporary functions are ``TEMPORARY`` and auto-drop at session end,
        so this is a no-op.  The method exists because ``run_gepa_optimize``
        calls ``adapter.cleanup()`` in its ``finally`` block.
        """

    def _format_inputs_for_display(self, inputs: dict[str, str]) -> str:
        """Format inputs dict as string for tracking/reflection."""
        return "\n".join(f"{k}: {v}" for k, v in inputs.items())

    def _call_udf_batch(
        self,
        system_prompt: str,
        batch: list[SnowflakeDataInst],
    ) -> list[str]:
        """Call a temp function for all inputs in a single query.

        Creates (or replaces) a temporary function with the candidate
        model and prompt baked in, then calls it without overrides.

        For FILE-type parameters, TempAIFunction wraps the VARCHAR
        values with ``TO_FILE(stage, value)`` at call time.
        """
        if not batch:
            return []

        # Time the CREATE TEMPORARY FUNCTION DDL round-trip.
        # ``TempAIFunction.__init__`` issues the ``session.sql(ddl).collect()``.
        tracker = get_active_tracker()
        _compile_t0 = time.perf_counter()
        try:
            inst = TempAIFunction(
                session=self.session,
                function_def=self.function_def,
                temp_function_name=self.temp_function_name,
                candidate_model=self.model,
                candidate_prompt=system_prompt,
                file_type_params=self._file_type_params,
                stage_name=self._stage_name,
            )
        finally:
            if tracker is not None:
                tracker.add_udf_compile(time.perf_counter() - _compile_t0)

        inputRows = []
        for data in batch:
            row = {c: data["inputs"].get(c, "") for c in self.input_columns}
            for k, v in data["inputs"].items():
                if k.startswith(STAGE_KEY_PREFIX):
                    row[k] = v
            inputRows.append(row)

        # Snapshot real token usage for THIS model BEFORE the call so we
        # can attribute the per-call token delta to this udf_exec event.
        # ``call_rows`` itself feeds the absolute tracker totals via
        # ``add_tokens`` (one call per SQL round-trip after the retry
        # loop).  Diffing against the snapshot taken here gives the
        # per-call (prompt, completion) tuple we stamp on the timeline
        # event so the new token Gantt can size each segment.
        prev_pt = 0
        prev_ct = 0
        if tracker is not None:
            prev_bucket = tracker.token_usage_snapshot.get((self.model, "udf"), {})
            prev_pt = int(prev_bucket.get("prompt_tokens", 0) or 0)
            prev_ct = int(prev_bucket.get("completion_tokens", 0) or 0)

        # Time the actual function execution (one collect() across the batch).
        _exec_t0 = time.perf_counter()
        responses: list[str] = []
        try:
            responses = inst.call_rows(inputRows)
            return responses
        finally:
            if tracker is not None:
                exec_dur = time.perf_counter() - _exec_t0
                # Char-based input/output estimate for the UDF.
                # ``input`` = system_prompt (sent once per UDF call,
                # but applied to every row) + the concatenated row
                # values × len(batch).  ``output`` = sum of response
                # text lengths.  This is a coarse but useful proxy
                # for the actual token traffic.
                in_chars = len(system_prompt or "") * max(1, len(batch))
                for row in inputRows:
                    in_chars += sum(len(str(v) or "") for v in row.values())
                out_chars = sum(len(str(r) or "") for r in responses)
                tracker.add_chars(self.model, "udf", in_chars, out_chars)
                # Real per-call token delta — diff against the pre-call
                # snapshot.  ``call_rows`` only calls ``add_tokens``
                # when the SQL response carried a non-zero ``usage``
                # block, so a delta of ``(0, 0)`` legitimately means
                # "no tokens reported for this batch" (e.g. all rows
                # failed before AI_COMPLETE could surface usage).
                new_bucket = tracker.token_usage_snapshot.get((self.model, "udf"), {})
                d_pt = int(new_bucket.get("prompt_tokens", 0) or 0) - prev_pt
                d_ct = int(new_bucket.get("completion_tokens", 0) or 0) - prev_ct
                tracker.add_udf_exec(
                    exec_dur,
                    prompt_tokens=max(0, d_pt),
                    completion_tokens=max(0, d_ct),
                    input_chars=in_chars,
                    output_chars=out_chars,
                    model=self.model,
                )

    def evaluate(
        self,
        batch: list[SnowflakeDataInst],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch[SnowflakeTrajectory, SnowflakeRolloutOutput]:
        # Thread-local pre/post hooks let the optimizer measure
        # inter-evaluate "gepa_thinking" gaps without monkey-patching
        # this method at the class level.  Hooks are per-thread so
        # concurrent ``ThreadPoolExecutor`` workers cannot clobber each
        # other.  See ``set_evaluate_hooks`` for the contract.
        pre_hook, post_hook = _get_evaluate_hooks()
        if pre_hook is not None:
            pre_hook()
        try:
            outputs: list[SnowflakeRolloutOutput] = []
            scores: list[float] = []
            objective_scores: list[dict[str, float] | None] = []
            trajectories: list[SnowflakeTrajectory] | None = (
                [] if capture_traces else None
            )

            system_prompt = next(iter(candidate.values()))

            responses = self._call_udf_batch(system_prompt, batch)

            # Single code path - evaluator handles batching internally
            items = list(zip(batch, responses, strict=True))
            eval_results = self.evaluator.evaluate_batch(items)

            # Capture per-row detail for THIS candidate so the experiment
            # tracker can persist a ``eval_detail.json``. A batch
            # smaller than the full valset (e.g. a rejected proposal's
            # minibatch gate) is flagged ``subsample`` and split-tagged so the
            # partial coverage is visible to a reader.
            subsample = (
                self._full_valset_size is not None
                and len(batch) < self._full_valset_size
            )
            split_tag = "val_subsample" if subsample else "val_full"
            metric_name = getattr(self.evaluator, "metric_name", "")
            detail_records: list[dict] = []

            for row_id, (data, response, eval_result) in enumerate(
                zip(batch, responses, eval_results, strict=True)
            ):
                output: SnowflakeRolloutOutput = {"full_assistant_response": response}
                outputs.append(output)
                scores.append(eval_result.score)
                objective_scores.append(getattr(eval_result, "objective_scores", None))

                detail_records.append(
                    build_eval_detail_record(
                        row_id=row_id,
                        input_text=self._format_inputs_for_display(data["inputs"]),
                        expected=data["answer"],
                        predicted=response,
                        metric_score=eval_result.score,
                        metric_feedback=eval_result.feedback,
                        metric_name=metric_name,
                        model_name=self.model,
                        split=split_tag,
                        max_length=_EVAL_DETAIL_MAX_LENGTH,
                    )
                )

                if trajectories is not None:
                    trajectories.append(
                        {
                            "data": data,
                            "full_assistant_response": response,
                            "feedback": eval_result.feedback,
                        }
                    )

            # Latest-eval-wins: an accepted candidate's final pre-accept eval is
            # the full valset, so it overwrites any earlier minibatch entry.
            self._eval_detail_buffer[candidate_detail_key(system_prompt)] = (
                _CapturedEval(records=detail_records, subsample=subsample)
            )

            return EvaluationBatch(
                outputs=outputs,
                scores=scores,
                trajectories=trajectories,
                objective_scores=[o for o in objective_scores if o is not None]
                if any(o is not None for o in objective_scores)
                else None,
            )
        finally:
            if post_hook is not None:
                post_hook()

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch[SnowflakeTrajectory, SnowflakeRolloutOutput],
        components_to_update: list[str],
    ) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        ret_d: dict[str, list[SnowflakeReflectiveRecord]] = {}

        assert len(components_to_update) == 1
        comp = components_to_update[0]

        trajectories = eval_batch.trajectories
        assert trajectories is not None

        items: list[SnowflakeReflectiveRecord] = []
        for traj in trajectories:
            formatted_inputs = self._format_inputs_for_display(traj["data"]["inputs"])
            d: SnowflakeReflectiveRecord = {
                "Inputs": formatted_inputs,
                "Generated Outputs": traj["full_assistant_response"],
                "Feedback": traj["feedback"],
            }
            items.append(d)

        ret_d[comp] = items

        if len(items) == 0:
            raise ValueError("No valid predictions found for reflection.")

        return ret_d


class DatasetResult:
    """Result of loading a dataset, including auto-detected FILE stage info."""

    def __init__(
        self,
        dataset: list[SnowflakeDataInst],
        file_stage_name: str | None = None,
        file_columns: list[str] | None = None,
    ):
        self.dataset = dataset
        self.file_stage_name = file_stage_name
        self.file_columns = file_columns or []

    def __bool__(self) -> bool:
        return bool(self.dataset)

    def __len__(self) -> int:
        return len(self.dataset)


def load_dataset(
    session: Session,
    table_name: str,
    input_columns: list[str],
    label_column: str,
    expected_columns: list[str] | None = None,
    input_arg_names: list[str] | None = None,
) -> DatasetResult:
    """Load data from a Snowflake table into SnowflakeDataInst format.

    Args:
        session: Snowpark session
        table_name: Fully qualified table name
        input_columns: List of column names to use as inputs
        label_column: Column containing expected outputs
        expected_columns: Optional list of expected output columns. When multiple
            columns are provided, they are combined into a single OBJECT for
            object-level evaluation (used by multi-output llm_judge).
        input_arg_names: Optional AI-function parameter name for each entry in
            ``input_columns`` (same length/order, already resolved from any
            ``$N`` markers). When provided, each column is projected under its
            parameter name and each row's ``inputs`` dict is keyed by parameter
            name, so candidates bind by name. ``None`` keeps the legacy behavior
            (inputs keyed by column name).

    Returns:
        DatasetResult with the dataset, auto-detected FILE stage name (from
        the first FILE value), and the list of FILE-typed columns.  Each
        row's ``inputs`` dict contains ``__STAGE_{col}`` keys so that
        downstream callers can build per-row ``TO_FILE()`` expressions.

    Raises:
        ValueError: If any input column is not found in the table

    """
    table_columns = get_table_column_names(session, table_name)
    validate_input_columns(table_columns, input_columns, table_name)

    # Name under which each input column is presented to candidates. With
    # argument binding it is the function's parameter name (already resolved);
    # otherwise the column name itself.
    present_as = input_arg_names or input_columns
    if input_arg_names:
        columns = ", ".join(
            f"{quote_identifier(col)} AS {quote_identifier(param)}"
            for col, param in zip(input_columns, present_as, strict=True)
        )
    else:
        columns = ", ".join([quote_identifier(col) for col in input_columns])

    label_col_name = resolve_expected_column(table_columns, label_column)

    answer_expr = f"{quote_identifier(label_col_name)} AS answer"
    if isinstance(expected_columns, list) and len(expected_columns) > 1:
        resolved_pairs = resolve_multi_output_columns(table_columns, expected_columns)
        if resolved_pairs:
            answer_expr = build_object_construct_expr(resolved_pairs, "answer")
    query = f"SELECT {columns}, {answer_expr} FROM {table_name}"

    rows = session.sql(query).collect()

    file_stage_name: str | None = None
    detected_file_cols: set[str] = set()
    dataset = []
    for row in rows:
        inputs = {}
        for col in present_as:
            val = row[col]
            if val is None:
                inputs[col] = ""
                continue

            # FILE-typed columns are collected as dicts with STAGE and
            # RELATIVE_PATH keys.  Extract the relative path and store
            # the stage in a companion __STAGE_{col} key so call_rows()
            # can build per-row TO_FILE() expressions.
            parsed = parse_file_value(val)
            if parsed:
                row_stage, rel_path = parsed
                inputs[col] = rel_path
                inputs[stage_key(col)] = row_stage
                detected_file_cols.add(col)
                if file_stage_name is None:
                    file_stage_name = row_stage
            elif isinstance(val, str) and val.strip()[:1] in ("[", "{"):
                try:
                    inputs[col] = json.loads(val)
                except json.JSONDecodeError:
                    inputs[col] = val
            else:
                inputs[col] = val
        answer = to_text(row["ANSWER"])
        dataset.append(SnowflakeDataInst(inputs=inputs, answer=answer))

    return DatasetResult(
        dataset=dataset,
        file_stage_name=file_stage_name,
        file_columns=sorted(detected_file_cols),
    )
