# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Evaluation orchestration — runs AI functions against test data and scores results.

Changes when the evaluation flow, SPROC interface, or experiment integration changes.
"""

import json
import logging
import re
import textwrap

from snowflake.snowpark import Row, Session

from snowflake_ai_optimize.core.ddl_rewrite import (
    find_ai_complete_call,
    inject_return_error_details,
    inject_show_details,
)
from snowflake_ai_optimize.core.errors import UserError
from snowflake_ai_optimize.core.experiment import estimate_candidate_cost
from snowflake_ai_optimize.core.metrics.dispatch import (
    METRIC_ERROR_PREFIX,
    PredictionExecutor,
    compute_metric_batch_resilient,
)
from snowflake_ai_optimize.core.metrics.llm_judge import LLM_JUDGE_DEFAULT_MODEL
from snowflake_ai_optimize.core.metrics.utils import (
    build_object_construct_expr,
    get_table_column_names,
    parse_metric_options,
    resolve_expected_column,
    resolve_multi_output_columns,
    to_text,
    validate_input_columns,
)
from snowflake_ai_optimize.core.sql_utils import (
    describe_function,
    quote_identifier,
)
from snowflake_ai_optimize.core.stage import validate_stage_file_access
from snowflake_ai_optimize.core.types import CostMeasurement, EvaluationResult

MODEL_MATCH_RE_PATTERN = r"AI_COMPLETE\s*\(\s*(?:model\s*=>)?\s*['\"]([^'\"]+)['\"]"

# Output column names the builtin query_text queries reserve (they SELECT the
# whole dataset via ``t.*`` and add these). A dataset column of the same name
# would collide, so ``_collect_query_text_rows`` rejects it with a clear error.
_QUERY_TEXT_RESERVED_COLUMNS = {
    "ROW_ID",
    "EXPECTED",
    "PREDICTED",
    "__ROW_ID",
    "__PROMPT_TOKENS",
    "__COMPLETION_TOKENS",
}

logger = logging.getLogger(__name__)


def build_eval_detail_record(
    *,
    row_id: object,
    input_text: str,
    expected: str,
    predicted: str,
    metric_score: float | None,
    metric_feedback: str | None,
    metric_name: str,
    model_name: str,
    split: str,
    error_message: str | None = None,
    max_length: int | None = None,
) -> dict:
    """Build one canonical per-row eval-detail record.

    Single source of truth for the ``eval_detail.json`` row shape so
    the core evaluator and the GEPA adapter's per-candidate capture cannot
    drift. When ``max_length`` is given, the free-text fields are truncated to
    that many characters (callers that already truncated pass ``None``).
    """

    def _clip(value: object) -> str:
        text = to_text(value)
        return text[:max_length] if max_length is not None else text

    return {
        "row_id": row_id,
        "input_text": _clip(input_text),
        "expected": _clip(expected),
        "predicted": _clip(predicted),
        "metric_score": metric_score,
        "metric_feedback": _clip(metric_feedback),
        "error_message": _clip(error_message),
        "metric_name": metric_name,
        "model_name": model_name,
        "split": split,
    }


def evaluate(
    session: Session,
    function_name: str,
    test_table: str,
    input_columns: list,
    label_column: str,
    metric_name: str,
    model_name: str = LLM_JUDGE_DEFAULT_MODEL,
    sample_size: int | None = None,
    metric_options: dict | None = None,
    max_length: int = 500,
    custom_metric_udf: str | None = None,
    run_id: str | None = None,
    executor: PredictionExecutor | None = None,
    split: str = "test",
    input_arg_names: list[str] | None = None,
    query_text: str | None = None,
) -> EvaluationResult:
    """Evaluate an AI function against a test dataset.

    The function is called directly without parameter overrides. The model
    and system prompt are baked into the function body. To evaluate with a
    different model or prompt, create a temporary function and pass its
    name as ``function_name``.

    A **builtin** AI function is evaluated by passing ``query_text`` instead of
    relying on ``function_name``: an inline scalar SQL expression that
    references the dataset columns directly (e.g.
    ``AI_COMPLETE('llama3.1-70b', 'Answer: ' || question)``). There is no
    function DDL to introspect — the expression is evaluated once per row
    against ``test_table``, so ``input_arg_names`` is not used on this path.

    Args:
        session: Snowpark session
        function_name: Fully qualified AI function name. On the ``query_text``
            path it is used only for run-cleanup/metadata, not for prediction.
        test_table: Fully qualified test data table
        input_columns: List of column names to pass to function
        label_column: Column containing expected outputs
        metric_name: Metric to use for evaluation
        model_name: Model name for results tracking metadata
        sample_size: Number of rows to evaluate (None = all)
        metric_options: Metric-specific options
        max_length: Max length for truncated fields (default 500)
        custom_metric_udf: Fully qualified name of a custom metric UDF.
        run_id: Optional external run ID for tracking (auto-generated if None).
        executor: Optional callable that produces predictions; when omitted,
            the function is invoked via SQL.
        split: Tag stored on each per-row detail record (e.g., ``"test"``,
            ``"validation"``). Useful when callers persist multiple eval
            artifacts side-by-side in the same experiment run.
        input_arg_names: Optional AI-function parameter name for each entry in
            ``input_columns`` (same length/order). When provided, each column is
            projected under its parameter name (``<col> AS <param>``) so the
            function binds by name; ``None`` preserves the legacy behavior where
            column names must already match the function's parameter names.
        query_text: Inline scalar SQL expression for a builtin AI function.
            When provided, the user-function DDL introspection path is bypassed
            and the expression is evaluated per row against ``test_table``.

    Returns:
        :class:`EvaluationResult` with ``score``, ``details`` (per-row
        dicts), and ``cost_measurement`` (token usage + estimated cost,
        populated only when ``executor`` is ``None``).

    """
    cost_info: CostMeasurement | None = None
    if query_text is not None:
        input_cols, output_field, metric_opts, results_data, cost_info = (
            _collect_query_text_rows(
                session,
                query_text=query_text,
                test_table=test_table,
                input_columns=input_columns,
                label_column=label_column,
                metric_name=metric_name,
                metric_options=metric_options,
                sample_size=sample_size,
            )
        )
    elif executor is None:
        input_cols, output_field, metric_opts, results_data, cost_info = (
            _collect_eval_rows_with_cost(
                session,
                function_name=function_name,
                test_table=test_table,
                input_columns=input_columns,
                label_column=label_column,
                metric_name=metric_name,
                metric_options=metric_options,
                sample_size=sample_size,
                input_arg_names=input_arg_names,
            )
        )
    else:
        input_cols, output_field, metric_opts, results_data = _collect_eval_rows(
            session,
            test_table=test_table,
            input_columns=input_columns,
            label_column=label_column,
            metric_name=metric_name,
            metric_options=metric_options,
            sample_size=sample_size,
            function_name=function_name,
            include_predicted=False,
            input_arg_names=input_arg_names,
        )

    validate_stage_file_access(
        session,
        stage_name=metric_opts.get("stage_name"),
        file_columns=metric_opts.get("file_columns"),
        table_name=test_table,
    )

    if not results_data:
        return EvaluationResult(score=0.0, details=[])

    if executor is None:
        predicted_raw_list = []
        for row in results_data:
            try:
                v = row["PREDICTED"]
            except Exception:
                v = None
            predicted_raw_list.append(v if v is not None else "")
    else:
        executor_rows: list[dict[str, object]] = []
        for row in results_data:
            d = {c: row[c] if c in row else None for c in input_cols}  # noqa: SIM401 — Row has no .get()
            executor_rows.append(d)
        predicted_raw_list = executor(executor_rows)

    if len(predicted_raw_list) != len(results_data):
        raise ValueError(
            f"Executor returned {len(predicted_raw_list)} predictions for {len(results_data)} rows"
        )

    results = []
    total_score = 0.0

    # Collect all row metadata and identify items for batch evaluation
    row_metadata = []
    batch_items = []  # (idx, expected, predicted)

    for idx, row in enumerate(results_data):
        row_id = row["ROW_ID"]
        expected = to_text(row["EXPECTED"])

        predicted_raw_obj = predicted_raw_list[idx]
        error_message = None
        if isinstance(predicted_raw_obj, str) and predicted_raw_obj.startswith(
            "INFERENCE_ERROR:"
        ):
            error_message = predicted_raw_obj
            predicted_raw = ""
        else:
            predicted_raw = predicted_raw_obj if predicted_raw_obj is not None else ""

        predicted = _extract_output_field(predicted_raw, output_field)

        input_summary = "; ".join(
            [f"{col}={str(row[col])[:max_length]}" for col in input_cols]
        )

        row_metadata.append(
            {
                "row_id": row_id,
                "expected": expected,
                "predicted": predicted,
                "input_summary": input_summary,
                "error_message": error_message,
            }
        )

        if expected and predicted:
            batch_items.append((idx, expected, predicted))

    # Batch evaluate all valid items
    if batch_items:
        items_for_batch = [(exp, pred) for _, exp, pred in batch_items]
        # output_field is consumed above to select the field from VARIANT outputs.
        # Do not pass it into metric functions (e.g., llm_judge_batch), which
        # only accept metric-specific options.
        batch_results = compute_metric_batch_resilient(
            metric_name, items_for_batch, session, custom_metric_udf, **metric_opts
        )
        batch_result_map = {
            batch_items[i][0]: batch_results[i] for i in range(len(batch_items))
        }
    else:
        batch_result_map = {}

    # Process results
    for idx, meta in enumerate(row_metadata):
        error_message = meta.get("error_message")
        if not meta["expected"]:
            score, feedback = 0.0, "Empty expected value"
        elif error_message:
            score, feedback = 0.0, error_message
        elif not meta["predicted"]:
            score, feedback = 0.0, "Empty predicted value"
        elif idx in batch_result_map:
            score, feedback = batch_result_map[idx]
            # A row whose metric scoring threw (batch fell back to per-row and
            # that row still failed) is a row-level failure, not a real score —
            # surface it in error_message too, alongside inference errors, so
            # it's visible even for metrics that leave metric_feedback empty.
            if feedback and feedback.startswith(METRIC_ERROR_PREFIX):
                error_message = feedback
        else:
            score, feedback = 0.0, "Evaluation error"

        total_score += score
        results.append(
            (
                meta["row_id"],
                meta["input_summary"][:max_length],
                meta["expected"][:max_length],
                meta["predicted"][:max_length],
                score,
                feedback[:max_length] if feedback else None,
                error_message,
            )
        )

    eval_details: list[dict] = [
        build_eval_detail_record(
            row_id=r[0],
            input_text=r[1] or "",
            expected=r[2] or "",
            predicted=r[3] or "",
            metric_score=r[4],
            metric_feedback=r[5] or "",
            error_message=r[6] or "",
            metric_name=metric_name,
            model_name=model_name,
            split=split,
        )
        for r in results
    ]

    avg_score = total_score / len(results_data) if results_data else 0

    # Clean up async task if this was called from one (run_id matches task name)
    if run_id and run_id.startswith("ai_func_eval_"):
        try:
            parts = function_name.split("(")[0].split(".")
            if len(parts) >= 3:
                task_fqn = f"{parts[0]}.{parts[1]}.{run_id}"
                session.sql(f"DROP TASK IF EXISTS {task_fqn}").collect()
        except Exception:
            pass  # Cleanup failure should not break the evaluation

    return EvaluationResult(
        score=avg_score, details=eval_details, cost_measurement=cost_info
    )


def _extract_output_field(predicted: object, output_field: str | None) -> str:
    """Extract a single output field from a JSON/VARIANT prediction."""
    if predicted is None:
        return ""
    if not output_field:
        return to_text(predicted)

    output_key = str(output_field).upper()
    if isinstance(predicted, dict):
        key_map = {str(k).upper(): k for k in predicted}
        key = key_map.get(output_key)
        if key is not None:
            return to_text(predicted.get(key, ""))
        # Backward-compatible fallback for single-output structured responses
        # when expected column and output key names differ.
        if len(predicted) == 1:
            return to_text(next(iter(predicted.values())))
        return to_text(predicted)

    if isinstance(predicted, str):
        try:
            parsed = json.loads(predicted)
            if isinstance(parsed, dict):
                key_map = {str(k).upper(): k for k in parsed}
                key = key_map.get(output_key)
                if key is not None:
                    return to_text(parsed.get(key, ""))
                if len(parsed) == 1:
                    return to_text(next(iter(parsed.values())))
                return to_text(parsed)
        except json.JSONDecodeError:
            return predicted

    return to_text(predicted)


def _collect_eval_rows(
    session: Session,
    *,
    test_table: str,
    input_columns: list,
    label_column: str,
    metric_name: str,
    metric_options: dict | None,
    sample_size: int | None,
    function_name: str | None = None,
    include_predicted: bool = False,
    input_arg_names: list[str] | None = None,
) -> tuple[list[str], str | None, dict, list[Row]]:
    metric_opts, output_field, multi_expected_cols = parse_metric_options(
        metric_options
    )

    input_cols = [col.strip('"').strip("'") for col in input_columns]
    table_columns = get_table_column_names(session, test_table)
    validate_input_columns(table_columns, input_cols, test_table)

    expected_col_name = resolve_expected_column(table_columns, label_column)

    # On this (executor) path `input_arg_names` are already-resolved parameter
    # names (there is no DDL here to resolve `$N` — the optimizer resolves it).
    # Alias each column to its parameter name so the executor's row dicts, and
    # the temp function it builds, bind by name.
    present_as = (
        [a.strip('"').strip("'") for a in input_arg_names]
        if input_arg_names
        else input_cols
    )
    if input_arg_names:
        columns = ", ".join(
            f"{quote_identifier(col)} AS {quote_identifier(param)}"
            for col, param in zip(input_cols, present_as, strict=True)
        )
    else:
        columns = ", ".join([quote_identifier(col) for col in input_cols])
    expected_expr = f"{quote_identifier(expected_col_name)} AS EXPECTED"

    if metric_name == "llm_judge" and len(multi_expected_cols) > 1:
        resolved_pairs = resolve_multi_output_columns(
            table_columns, multi_expected_cols
        )
        if resolved_pairs:
            output_field = None
            expected_expr = build_object_construct_expr(resolved_pairs, "EXPECTED")
        elif table_columns and expected_col_name.upper() not in table_columns:
            raise ValueError(
                "Expected output columns not found in test table. "
                f"Provided expected_columns={multi_expected_cols}, label_column={label_column}, "
                f"available_columns={sorted(table_columns)}"
            )

    predicted_expr = ""
    if include_predicted:
        if not function_name:
            raise ValueError("function_name is required when include_predicted=True")
        base_function_name = (
            function_name.split("(")[0] if "(" in function_name else function_name
        )
        # Positional direct call uses the bare columns (an aliased `col AS param`
        # would be invalid inside a call). This branch is unused by the SPROC
        # eval/opt paths (they set include_predicted=False), so v1 does not
        # render named args here.
        call_cols = ", ".join([quote_identifier(col) for col in input_cols])
        udf_call = f"{base_function_name}({call_cols})"
        predicted_expr = f",\n            {udf_call} AS PREDICTED"

    query = f"""
        SELECT
            ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS ROW_ID,
            {columns},
            {expected_expr}{predicted_expr}
        FROM {test_table}
    """
    if sample_size:
        query += f" LIMIT {sample_size}"

    results_data = session.sql(query).collect()
    return present_as, output_field, metric_opts, results_data


def _collect_eval_rows_with_cost(
    session: Session,
    *,
    function_name: str,
    test_table: str,
    input_columns: list,
    label_column: str,
    metric_name: str,
    metric_options: dict | None,
    sample_size: int | None,
    input_arg_names: list[str] | None = None,
) -> tuple[list[str], str | None, dict, list, "CostMeasurement"]:
    """Collect eval rows and measure cost in a single AI_COMPLETE execution.

    Injects ``show_details=>TRUE`` into the function's AI_COMPLETE call,
    then runs one CTE query that returns both predictions and per-row
    token counts.  Replaces the two-pass pattern of calling the UDF for
    predictions and then re-running with show_details for token counts.

    Returns the same ``(input_cols, output_field, metric_opts, results_data)``
    tuple as ``_collect_eval_rows`` with ``include_predicted=True``, plus a
    ``CostMeasurement``.  The ``results_data`` rows also carry
    ``__PROMPT_TOKENS`` and ``__COMPLETION_TOKENS`` columns (internal, not
    used by the caller).

    Raises:
        ValueError: If DDL cannot be retrieved, parsed, or lacks an
            AI_COMPLETE call, or if the model is not in the rate table.
        RuntimeError: If the combined query returns no data or no token rows.

    """
    # -- Column resolution (same logic as _collect_eval_rows) --
    metric_opts, output_field, multi_expected_cols = parse_metric_options(
        metric_options
    )
    output_field_explicitly_set = output_field is not None
    input_cols = [col.strip('"').strip("'") for col in input_columns]
    table_columns = get_table_column_names(session, test_table)
    validate_input_columns(table_columns, input_cols, test_table)
    expected_col_name = resolve_expected_column(table_columns, label_column)
    columns = ", ".join([quote_identifier(col) for col in input_cols])
    # Name under which each input column is presented to the inlined body. With
    # argument binding it is the function's parameter name (already resolved by
    # the caller — `$N` -> parameter name), so we alias `col AS param`; otherwise
    # the column name itself (legacy: column names must match parameter names).
    present_as = input_cols
    if input_arg_names:
        present_as = [a.strip('"').strip("'") for a in input_arg_names]
        columns = ", ".join(
            f"{quote_identifier(col)} AS {quote_identifier(param)}"
            for col, param in zip(input_cols, present_as, strict=True)
        )
    expected_expr = f"{quote_identifier(expected_col_name)} AS EXPECTED"

    if metric_name == "llm_judge" and len(multi_expected_cols) > 1:
        resolved_pairs = resolve_multi_output_columns(
            table_columns, multi_expected_cols
        )
        if resolved_pairs:
            output_field = None
            expected_expr = build_object_construct_expr(resolved_pairs, "EXPECTED")
        elif table_columns and expected_col_name.upper() not in table_columns:
            raise ValueError(
                "Expected output columns not found in test table. "
                f"Provided expected_columns={multi_expected_cols}, label_column={label_column}, "
                f"available_columns={sorted(table_columns)}"
            )

    # -- DDL rewriting (same logic as measure_function_cost) --
    # Introspect the function via DESCRIBE FUNCTION.  ``describe_function``
    # resolves overloads via SHOW FUNCTIONS and returns the raw (un-escaped)
    # body; the downstream body regexes (MODEL_MATCH_RE_PATTERN,
    # inject_show_details, inject_return_error_details, find_ai_complete_call,
    # response_format detection) operate on that body unchanged.
    fn = describe_function(session, function_name)
    body = fn.body

    model_match = re.search(MODEL_MATCH_RE_PATTERN, body, re.IGNORECASE)
    if not model_match:
        raise ValueError(
            f"Could not extract model name from AI_COMPLETE call in {function_name}"
        )
    model = model_match.group(1)

    rewrite = inject_show_details(body)
    if rewrite is None:
        raise ValueError(
            f"No AI_COMPLETE call found in function body for {function_name}"
        )
    rewritten_body, (ai_start, ai_end) = rewrite

    error_rewrite = inject_return_error_details(rewritten_body)
    has_error_details = error_rewrite is not None
    if error_rewrite is not None:
        rewritten_body = error_rewrite[0]

    rewritten_call = find_ai_complete_call(rewritten_body)
    if rewritten_call is not None:
        _, rw_start, rw_end = rewritten_call
        ai_call_span = rewritten_body[rw_start:rw_end]
    else:
        ai_call_span = rewritten_body[ai_start:ai_end]

    # -- Determine how to extract the prediction from show_details response --
    # Detect whether the function uses response_format (structured output).
    has_response_format = bool(re.search(r"response_format\s*=>", body, re.IGNORECASE))

    # Infer output_field from the DDL accessor (e.g., ":intent::VARCHAR" after
    # AI_COMPLETE(...)) when the caller hasn't explicitly specified one. This
    # lets _extract_output_field in the caller handle field extraction uniformly.
    if not output_field_explicitly_set and has_response_format:
        original_call = find_ai_complete_call(body)
        if original_call is not None:
            _, _, orig_end = original_call
            tail = body[orig_end:]
            accessor_match = re.match(r":([a-zA-Z_]\w*)", tail)
            if accessor_match:
                output_field = accessor_match.group(1)

    if has_response_format:
        predicted_expr = "a.__DETAILS:structured_output[0]:raw_message::VARCHAR"
    else:
        predicted_expr = "a.__DETAILS:choices[0]:messages::VARCHAR"

    # -- Combined CTE query: one AI_COMPLETE execution per row --
    limit_clause = f"LIMIT {sample_size}" if sample_size else ""
    src_cols_ref = ", ".join([f"s.{quote_identifier(col)}" for col in present_as])

    # When return_error_details is injected, AI_COMPLETE returns
    # OBJECT(value VARIANT, error VARCHAR). The show_details JSON is inside
    # the 'value' field as a string that needs PARSE_JSON.
    # Without return_error_details, AI_COMPLETE with show_details returns a
    # VARCHAR containing the JSON directly.
    if has_error_details:
        details_expr = f"PARSE_JSON(({ai_call_span}):value)"
    else:
        details_expr = f"PARSE_JSON({ai_call_span})"

    sql = textwrap.dedent(f"""\
        WITH __src AS (
            SELECT ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS __ROW_ID,
                   {columns},
                   {expected_expr}
            FROM {test_table} {limit_clause}
        ),
        __ai_call AS (
            SELECT __ROW_ID, {details_expr} AS __DETAILS
            FROM __src
        )
        SELECT
            s.__ROW_ID AS ROW_ID,
            {src_cols_ref},
            s.EXPECTED,
            {predicted_expr} AS PREDICTED,
            a.__DETAILS:usage:prompt_tokens::FLOAT AS __PROMPT_TOKENS,
            a.__DETAILS:usage:completion_tokens::FLOAT AS __COMPLETION_TOKENS
        FROM __src s
        JOIN __ai_call a ON s.__ROW_ID = a.__ROW_ID""")

    results_data = session.sql(sql).collect()
    if not results_data:
        # No rows out of the eval query means the test dataset is empty (or every
        # row was filtered out) — a caller-fixable data problem, not an internal
        # fault, so classify it as a user error.
        raise UserError(
            f"Evaluation produced no rows for {function_name}: the test dataset "
            "is empty or all rows were filtered out."
        )

    # -- Aggregate token counts for cost estimation --
    valid_rows = [r for r in results_data if r["__PROMPT_TOKENS"] is not None]
    num_rows = len(valid_rows)
    if num_rows == 0:
        raise RuntimeError(
            f"No token data returned from combined query for {function_name}"
        )
    total_pt = sum(float(r["__PROMPT_TOKENS"]) for r in valid_rows)
    total_ct = sum(float(r["__COMPLETION_TOKENS"] or 0) for r in valid_rows)
    avg_pt = total_pt / num_rows
    avg_ct = total_ct / num_rows

    cost_per_call = estimate_candidate_cost(model, avg_pt, avg_ct)

    cost_info = CostMeasurement(
        model=model,
        num_rows=num_rows,
        total_prompt_tokens=total_pt,
        total_completion_tokens=total_ct,
        avg_prompt_tokens=avg_pt,
        avg_completion_tokens=avg_ct,
        estimated_cost_per_call=cost_per_call,
    )
    return present_as, output_field, metric_opts, results_data, cost_info


def _query_text_is_single_bare_ai_complete(query_text: str) -> bool:
    """True when ``query_text`` is exactly one top-level ``AI_COMPLETE(...)`` call.

    Only then does the cost path's prediction — extracted from the AI_COMPLETE
    ``show_details`` response — equal the result of evaluating the whole
    expression, so token/cost capture is safe to attach. Any wrapping
    (``CONCAT(AI_COMPLETE(...), ...)``), trailing accessor
    (``AI_COMPLETE(...):x::VARCHAR``), additional call, or non-AI_COMPLETE
    expression returns ``False`` and takes the direct path, which evaluates the
    full expression as the prediction (always correct, no cost measured).
    """
    if len(re.findall(r"\bAI_COMPLETE\s*\(", query_text, re.IGNORECASE)) != 1:
        return False
    found = find_ai_complete_call(query_text)
    if found is None:
        return False
    _inner, start, end = found
    return query_text[start:end].strip() == query_text.strip()


def _collect_query_text_rows(
    session: Session,
    *,
    query_text: str,
    test_table: str,
    input_columns: list,
    label_column: str,
    metric_name: str,
    metric_options: dict | None,
    sample_size: int | None,
) -> tuple[list[str], str | None, dict, list[Row], CostMeasurement | None]:
    """Collect eval rows for a **builtin** AI function given as ``query_text``.

    Unlike the user-function path there is no DDL to introspect: ``query_text``
    is a scalar SQL expression that references the dataset columns directly
    (e.g. ``AI_COMPLETE('llama3.1-70b', 'Answer: ' || question)``). It is
    evaluated once per row against ``test_table``; every column of the table is
    in scope, so ``input_columns`` need only list the columns surfaced in the
    per-row ``input_summary`` (the mapping may even be empty).

    When the expression contains an ``AI_COMPLETE`` call, ``show_details=>TRUE``
    is injected so the response carries per-row token usage and a
    :class:`CostMeasurement` is returned (mirroring the user-function cost
    path). For other builtins (``AI_CLASSIFY``, ``AI_FILTER``, ``AI_EXTRACT``
    ...) the expression is evaluated directly and cost is not measured
    (``cost_info`` is ``None``).

    Returns the same ``(input_cols, output_field, metric_opts, results_data,
    cost_info)`` tuple shape as :func:`_collect_eval_rows_with_cost`.
    """
    metric_opts, output_field, multi_expected_cols = parse_metric_options(
        metric_options
    )
    output_field_explicitly_set = output_field is not None
    input_cols = [col.strip('"').strip("'") for col in input_columns]
    table_columns = get_table_column_names(session, test_table)
    if input_cols:
        validate_input_columns(table_columns, input_cols, test_table)
    # The generated query selects the whole table (``t.*``) so the expression can
    # reference any column, then adds ROW_ID / EXPECTED / PREDICTED (and token)
    # output columns. Reject a dataset that already uses one of those reserved
    # names up front, with a clear message instead of an opaque SQL error.
    reserved_collisions = sorted(table_columns & _QUERY_TEXT_RESERVED_COLUMNS)
    if reserved_collisions:
        raise ValueError(
            f"Test table {test_table} has column(s) {reserved_collisions} that "
            "collide with reserved output names for builtin query_text evaluation "
            f"({sorted(_QUERY_TEXT_RESERVED_COLUMNS)}). Rename or alias them in a "
            "view before evaluating."
        )
    expected_col_name = resolve_expected_column(table_columns, label_column)
    expected_expr = f"{quote_identifier(expected_col_name)} AS EXPECTED"

    if metric_name == "llm_judge" and len(multi_expected_cols) > 1:
        resolved_pairs = resolve_multi_output_columns(
            table_columns, multi_expected_cols
        )
        if resolved_pairs:
            output_field = None
            expected_expr = build_object_construct_expr(resolved_pairs, "EXPECTED")
        elif table_columns and expected_col_name.upper() not in table_columns:
            raise ValueError(
                "Expected output columns not found in test table. "
                f"Provided expected_columns={multi_expected_cols}, label_column={label_column}, "
                f"available_columns={sorted(table_columns)}"
            )

    limit_clause = f"LIMIT {sample_size}" if sample_size else ""
    # Display columns carried through for the per-row ``input_summary``; the
    # query_text itself resolves ANY column of test_table directly.
    display_sel = "".join(f"{quote_identifier(c)}, " for c in input_cols)
    display_sel_s = "".join(f"s.{quote_identifier(c)}, " for c in input_cols)

    # -- Direct path: anything that is not a single bare top-level AI_COMPLETE
    # (other builtins like AI_CLASSIFY, multiple calls, wrapped/accessed calls).
    # A single scan (no self-join) evaluates the whole expression once per row as
    # the prediction — always the true result of the formed query; there is no
    # single AI_COMPLETE usage block to recover, so no CostMeasurement.
    if not _query_text_is_single_bare_ai_complete(query_text):
        sql = textwrap.dedent(f"""\
            SELECT
                ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS ROW_ID,
                {display_sel}{expected_expr},
                ({query_text}) AS PREDICTED
            FROM {test_table} {limit_clause}""")
        results_data = session.sql(sql).collect()
        return input_cols, output_field, metric_opts, results_data, None

    # -- Cost path: inject show_details into the AI_COMPLETE call for tokens. --
    model_match = re.search(MODEL_MATCH_RE_PATTERN, query_text, re.IGNORECASE)
    model = model_match.group(1) if model_match else None

    rewrite = inject_show_details(query_text)
    rewritten = rewrite[0] if rewrite else query_text
    error_rewrite = inject_return_error_details(rewritten)
    has_error_details = error_rewrite is not None
    if error_rewrite is not None:
        rewritten = error_rewrite[0]

    rewritten_call = find_ai_complete_call(rewritten)
    if rewritten_call is not None:
        _, rw_start, rw_end = rewritten_call
        ai_call_span = rewritten[rw_start:rw_end]
    else:
        ai_call_span = rewritten

    has_response_format = bool(
        re.search(r"response_format\s*=>", query_text, re.IGNORECASE)
    )
    if not output_field_explicitly_set and has_response_format:
        original_call = find_ai_complete_call(query_text)
        if original_call is not None:
            _, _, orig_end = original_call
            accessor_match = re.match(r":([a-zA-Z_]\w*)", query_text[orig_end:])
            if accessor_match:
                output_field = accessor_match.group(1)

    if has_response_format:
        predicted_expr = "a.__DETAILS:structured_output[0]:raw_message::VARCHAR"
    else:
        predicted_expr = "a.__DETAILS:choices[0]:messages::VARCHAR"

    if has_error_details:
        details_expr = f"PARSE_JSON(({ai_call_span}):value)"
    else:
        details_expr = f"PARSE_JSON({ai_call_span})"

    # Mirror the user-function cost path: assign __ROW_ID once in __src (which
    # exposes every table column via ``t.*`` so the query_text resolves), derive
    # the single AI_COMPLETE evaluation in __ai_call FROM __src, then join so the
    # expensive call runs exactly once per row and inputs/prediction stay aligned.
    sql = textwrap.dedent(f"""\
        WITH __src AS (
            SELECT
                t.*,
                ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS __ROW_ID,
                {expected_expr}
            FROM {test_table} t {limit_clause}
        ),
        __ai_call AS (
            SELECT __ROW_ID, {details_expr} AS __DETAILS
            FROM __src
        )
        SELECT
            s.__ROW_ID AS ROW_ID,
            {display_sel_s}s.EXPECTED,
            {predicted_expr} AS PREDICTED,
            a.__DETAILS:usage:prompt_tokens::FLOAT AS __PROMPT_TOKENS,
            a.__DETAILS:usage:completion_tokens::FLOAT AS __COMPLETION_TOKENS
        FROM __src s
        JOIN __ai_call a ON s.__ROW_ID = a.__ROW_ID""")

    results_data = session.sql(sql).collect()
    if not results_data:
        return input_cols, output_field, metric_opts, [], None

    # Aggregate token counts; skip cost when the model literal or token usage
    # could not be recovered (e.g. a model expression rather than a literal).
    valid_rows = [r for r in results_data if r["__PROMPT_TOKENS"] is not None]
    if not valid_rows or model is None:
        return input_cols, output_field, metric_opts, results_data, None

    num_rows = len(valid_rows)
    total_pt = sum(float(r["__PROMPT_TOKENS"]) for r in valid_rows)
    total_ct = sum(float(r["__COMPLETION_TOKENS"] or 0) for r in valid_rows)
    avg_pt = total_pt / num_rows
    avg_ct = total_ct / num_rows

    cost_info = CostMeasurement(
        model=model,
        num_rows=num_rows,
        total_prompt_tokens=total_pt,
        total_completion_tokens=total_ct,
        avg_prompt_tokens=avg_pt,
        avg_completion_tokens=avg_ct,
        estimated_cost_per_call=estimate_candidate_cost(model, avg_pt, avg_ct),
    )
    return input_cols, output_field, metric_opts, results_data, cost_info
