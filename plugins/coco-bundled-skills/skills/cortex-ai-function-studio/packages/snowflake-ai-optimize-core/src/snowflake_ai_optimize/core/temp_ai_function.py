# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Inline AI_COMPLETE evaluation with per-row error capture and token tracking."""

import contextlib
import json
import re
import time
from typing import Any

from snowflake.snowpark import Session
from snowflake.snowpark.functions import col
from snowflake.snowpark.types import (
    BooleanType,
    DataType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)

from snowflake_ai_optimize.core.constants import (
    STAGE_KEY_PREFIX,
    TEMP_AI_FUNCTION_MAX_ATTEMPTS,
)
from snowflake_ai_optimize.core.ddl_rewrite import (
    apply_file_prompt_prefix_workaround_to_ddl,
    find_ai_complete_call,
    inject_return_error_details,
    inject_show_details,
    replace_ai_complete_named_arg,
    semi_structured_param_names,
)
from snowflake_ai_optimize.core.sql_utils import FunctionDefinition, escape_sql_string


def _inline_input_schema(
    indexed_rows: list[dict[str, object]], all_cols: list[str]
) -> StructType:
    """Build an explicit Snowpark schema for the inline-eval input rows.

    ``session.create_dataframe(rows)`` without a schema lets Snowpark infer
    each column's type from the first row's Python value.  On Snowpark 1.52.0
    a ``str`` value is inferred as ``StringType(1)`` (``VARCHAR(1)``); saving
    the dataframe to the temp eval table then fails with a truncation error on
    any multi-character input, and that failure is swallowed at DEBUG and
    silently zeroes out every metric call.  Pin text columns to an unbounded
    ``StringType()`` and ``__ROW_ID`` to ``LongType`` so inputs of any length
    round-trip intact.
    """
    fields: list[StructField] = []
    for column in all_cols:
        field_type: DataType = StringType()
        for row in indexed_rows:
            value = row.get(column)
            if value is None:
                continue
            if isinstance(value, bool):
                field_type = BooleanType()
            elif isinstance(value, int):
                field_type = LongType()
            elif isinstance(value, float):
                field_type = DoubleType()
            else:
                field_type = StringType()
            break
        fields.append(StructField(column, field_type))
    return StructType(fields)


class TempAIFunction:
    """Utility class for invoking an AI_COMPLETE-shaped function inline.

    Historically this class issued a ``CREATE TEMPORARY FUNCTION`` from the
    function's DDL and then called that function via
    ``call_function(self.temp_function_name, ...)``.  After the inline-eval
    migration there is NO ``CREATE FUNCTION`` round-trip: the constructor
    transforms the ``FunctionDefinition.body`` into a SQL expression
    (``self.inline_expr``, which augments AI_COMPLETE with
    ``show_details=>TRUE`` so the response carries per-row token usage), and
    :meth:`call_rows` evaluates that expression directly against a temp view
    created from the input rows.

    The class API (``__init__`` signature, ``call_rows`` contract,
    ``self.ddl`` attribute) is preserved for back-compat with callers and
    existing tests.  ``self.ddl`` is rendered via
    ``FunctionDefinition.render_create_ddl`` for inspection (used by
    ``test_unit.py::TestMultimodalTempFunction``) but NOT executed.
    ``self.temp_function_name`` is advisory / tracing only.
    """

    def __init__(
        self,
        session: Session,
        function_def: FunctionDefinition,
        temp_function_name: str,
        candidate_model: str,
        candidate_prompt: str,
        file_type_params: set[str] | None = None,
        stage_name: str | None = None,
    ) -> None:
        self.session = session
        self.function_def = function_def
        self.temp_function_name = temp_function_name
        self.candidate_model = candidate_model
        self.candidate_prompt = candidate_prompt
        self._file_type_params = (
            {p.upper() for p in file_type_params} if file_type_params else set()
        )
        self._stage_name = stage_name
        self._semi_structured_params = semi_structured_param_names(function_def.args)

        self.accessor_field = self._extract_output_accessor(function_def.body)

        # Build the transformed BODY expression the temp UDF would have
        # wrapped.  Every step operates on the function BODY (never on a
        # CREATE statement): model swap → system-prompt swap → file-prompt
        # prefix workaround → error-details cast.  ``show_details=>TRUE`` is
        # injected last to build the executed ``inline_expr`` so the response
        # carries per-row token usage.
        body = self._replace_ai_complete_model(function_def.body, candidate_model)

        escaped_prompt = escape_sql_string(candidate_prompt)
        body = re.sub(
            r"('role'\s*,\s*'system'\s*,\s*'content'\s*,\s*')(?:[^']|'')*(')",
            lambda m: m.group(1) + escaped_prompt + m.group(2),
            body,
            count=1,
            flags=re.DOTALL,
        )

        body = apply_file_prompt_prefix_workaround_to_ddl(body)
        body = self._rewrite_ai_complete_for_error_details(
            body, value_type=function_def.returns or "VARIANT"
        )

        # ``self.ddl`` is built for inspection / back-compat with tests that
        # read it (e.g. ``test_unit.py::TestMultimodalTempFunction``).  It is
        # NOT executed — the inline-eval path uses ``self.inline_expr``.
        self.ddl = function_def.render_create_ddl(
            name=temp_function_name,
            temporary=True,
            returns="OBJECT(value VARIANT, error STRING)",
            body=body,
        )

        # Inject ``show_details=>TRUE`` so the executed expression's response
        # carries an ``usage`` block (prompt_tokens / completion_tokens).
        # ``inject_show_details`` returns ``None`` when no AI_COMPLETE call is
        # present or when 5+ positional args already supplied — in those
        # degraded cases we proceed without the kwarg (token capture is zero).
        rewrite = inject_show_details(body)
        self.inline_expr = rewrite[0] if rewrite else body

    @staticmethod
    def _extract_output_accessor(raw_ddl: str) -> str | None:
        """Extract accessors from DDL (e.g. :field::TYPE)."""
        match = re.search(
            r"(:\s*\w+\s*::\s*[A-Z0-9_\(\), ]+)",
            raw_ddl,
            re.IGNORECASE,
        )

        matched_accessor = match.group(1) if match else None

        # Check for accessor field
        accessor_field = None
        if matched_accessor:
            m = re.search(r":\s*(\w+)\s*::", matched_accessor)
            if m:
                accessor_field = m.group(1)
                accessor_field = accessor_field.upper()

        return accessor_field

    # Delegate to module-level functions in core_ddl_rewrite for back-compat
    # with any code that still calls TempAIFunction._find_ai_complete_call
    # or TempAIFunction._replace_ai_complete_named_arg as static methods.
    _find_ai_complete_call = staticmethod(find_ai_complete_call)
    _replace_ai_complete_named_arg = staticmethod(replace_ai_complete_named_arg)

    @classmethod
    def _rewrite_ai_complete_for_error_details(
        cls, ddl: str, *, value_type: str
    ) -> str:
        """Prompt-mode wrapper that forces error-details capture on AI_COMPLETE.

        Composes :func:`_inject_return_error_details` (forces
        ``return_error_details=>TRUE`` so per-row inference errors surface
        as ``OBJECT(value, error)`` instead of bare ``NULL``) with two
        prompt-mode-specific rewrites:

        * Strip the user's output accessor (``:field::TYPE``) so the cast
          below operates on the raw OBJECT, not on a typed projection.
        * Wrap the call in
          ``::OBJECT(value VARIANT, error STRING)`` so ``call_rows`` can
          project ``__RES:value`` / ``__RES:error`` against a typed shape
          and surface ``"INFERENCE_ERROR: <msg>"`` for failed rows after
          the retry loop exhausts ``TEMP_AI_FUNCTION_MAX_ATTEMPTS``.

        The rewrite is invisible to GEPA experiment tracking (which records
        candidate prompt text, not the executed SQL) and to the reflection
        LM (which only sees ``Inputs`` / ``Generated Outputs`` /
        ``Feedback``).
        """
        rewrite = inject_return_error_details(ddl)
        if rewrite is not None:
            ddl, _ = rewrite

        # Remove output accessor like :field::TYPE
        ddl = re.sub(
            r":\s*\w+\s*::\s*[A-Z0-9_\(\), ]+",
            "",
            ddl,
            count=1,
            flags=re.IGNORECASE,
        )

        # Cast AI_COMPLETE to typed OBJECT(value VARIANT, error STRING)
        # Note this is always variant
        found = find_ai_complete_call(ddl)
        if found:
            inner, match_start, match_end = found
            replacement = f"(AI_COMPLETE({inner}))::OBJECT(value VARIANT, error STRING)"
            ddl = ddl[:match_start] + replacement + ddl[match_end:]

        return ddl

    @classmethod
    def _replace_ai_complete_model(cls, ddl: str, candidate_model: str) -> str:
        """Replace model argument in the first AI_COMPLETE(...) call with a literal."""
        found = find_ai_complete_call(ddl)
        if not found:
            return ddl

        inner, match_start, match_end = found
        escaped_model = escape_sql_string(candidate_model)
        replacement_expr = f"'{escaped_model}'"
        replaced_inner = replace_ai_complete_named_arg(
            inner,
            "model",
            replacement_expr,
        )
        if replaced_inner == inner:
            return ddl

        return ddl[:match_start] + f"AI_COMPLETE({replaced_inner})" + ddl[match_end:]

    def _build_input_view_projection_sql(self, all_cols: list[str]) -> str:
        """Render the SQL fragment for the CTE's input projection.

        Maps each Snowpark DataFrame column to a typed SQL expression with
        the SAME column name so the inline AI_COMPLETE expression's parameter
        references resolve correctly.  Mirrors today's ``arg_cols`` logic
        but emits SQL fragments instead of Snowpark Column objects:

        * ``__STAGE_<c>`` companion column → ``TO_FILE(__STAGE_<c>, <c>) AS <c>``
        * Static-stage FILE param → ``TO_FILE('<stage>', <c>) AS <c>``
        * Semi-structured (ARRAY/VARIANT/OBJECT) param → ``PARSE_JSON(<c>) AS <c>``
        * Pass-through → ``<c>``

        ``__ROW_ID`` always projects through unmodified.  Per-row stage
        companion columns (``__STAGE_<c>``) are dropped from the projection
        because they only participate in the ``TO_FILE`` wrapping.
        """
        # Build a fast lookup of which user-defined columns have a companion
        # ``__STAGE_<c>`` stage column in the input rows.
        seen = set(all_cols)

        fragments: list[str] = []
        for c in all_cols:
            if c == "__ROW_ID":
                fragments.append(c)
                continue
            if c.startswith(STAGE_KEY_PREFIX):
                # Stage companion columns are referenced in the TO_FILE call
                # for their sibling but are NOT exposed to the body.
                continue
            per_row_stage_col = f"{STAGE_KEY_PREFIX}{c}"
            if per_row_stage_col in seen:
                fragments.append(f"TO_FILE({per_row_stage_col}, {c}) AS {c}")
            elif (
                self._file_type_params
                and c.upper() in self._file_type_params
                and self._stage_name
            ):
                # Escape single-quotes in stage name (defensive — stage names
                # rarely contain them but ``self._stage_name`` is caller-supplied).
                escaped_stage = escape_sql_string(self._stage_name)
                fragments.append(f"TO_FILE('{escaped_stage}', {c}) AS {c}")
            elif (
                self._semi_structured_params
                and c.upper() in self._semi_structured_params
            ):
                fragments.append(f"PARSE_JSON({c}) AS {c}")
            else:
                fragments.append(c)
        return ", ".join(fragments)

    def call_rows(self, rows: list[dict[str, Any]]) -> list[Any]:
        """Evaluate the inline AI_COMPLETE expression against *rows*.

        Builds a CTE-shaped SELECT against a temp view of the input rows::

            WITH __ai_call AS (
                SELECT __ROW_ID, (<self.inline_expr>) AS __RES
                FROM (
                    SELECT __ROW_ID, <typed projections>
                    FROM <temp_view>
                    WHERE __ROW_ID IN (...)
                )
            )
            SELECT __ROW_ID                            AS ROW_ID,
                   __RES:value:choices[0]:messages     AS VALUE,
                   __RES:error                         AS ERROR,
                   __RES:value:usage:prompt_tokens     AS PROMPT_TOKENS,
                   __RES:value:usage:completion_tokens AS COMPLETION_TOKENS
            FROM __ai_call

        The projected ``VALUE`` is the model's text/structured output —
        i.e. the same scalar shape today's ``value`` had when
        ``show_details=FALSE`` — so the legacy Python-side accessor logic
        (JSON-parse + ``self.accessor_field`` lookup) operates unchanged.
        ``PROMPT_TOKENS`` / ``COMPLETION_TOKENS`` are summed across all
        SUCCESSFUL rows after the retry loop and pushed to the active
        :class:`TimingTracker` via ``add_tokens`` so cost-quality reports
        can render real token counts.

        Retries failed rows up to ``TEMP_AI_FUNCTION_MAX_ATTEMPTS`` times by
        re-running the same SELECT with the remaining-rows filter; surfaces
        the last attempt's error into the result as ``INFERENCE_ERROR: ...``.
        """
        if not rows:
            return []

        # Stable row id to preserve input order.
        # Normalize semi-structured values (ARRAY, VARIANT, OBJECT) to JSON
        # strings so the column is uniformly VARCHAR (avoids mixed-type
        # schema inference issues).
        indexed_rows = []
        for idx, row in enumerate(rows):
            r: dict[str, object] = {"__ROW_ID": idx}
            for k, v in (row or {}).items():
                if (
                    self._semi_structured_params
                    and k.upper() in self._semi_structured_params
                    and isinstance(v, list | tuple | dict)
                ):
                    r[k] = json.dumps(v)
                else:
                    r[k] = v
            indexed_rows.append(r)

        # Build column names — preserve insertion order across rows.
        all_cols: list[str] = ["__ROW_ID"]
        seen = {"__ROW_ID"}
        for row in rows:
            for k in row or {}:
                if k not in seen:
                    seen.add(k)
                    all_cols.append(k)

        # Sanity: reserved __ prefixes (other than __ROW_ID and __STAGE_*)
        # cannot collide with the inline-eval CTE's bookkeeping columns
        # (__RES, __ai_call, etc.).
        for c in all_cols:
            if (
                c.startswith("__")
                and c != "__ROW_ID"
                and not c.startswith(STAGE_KEY_PREFIX)
            ):
                raise ValueError(
                    f"Input column {c!r} starts with '__' which is reserved "
                    f"for inline-eval bookkeeping (__ROW_ID, __RES, __ai_call, "
                    f"{STAGE_KEY_PREFIX}<col>).  Rename the column before "
                    "passing to TempAIFunction.call_rows."
                )

        # Bind to a uniquely-named temp table per worker thread + call so
        # concurrent models in ThreadPoolExecutor cannot collide on object
        # names.  TEMPORARY tables die with the session even if our
        # explicit DROP in the finally block is skipped on a crash.
        #
        # Historical note: this used ``create_or_replace_temp_view`` until
        # the BENCHMARK_GEPA full-bench run on 2026-05-13 surfaced
        # Snowflake error 090222 ("View definition too large") on
        # scenarios with large-text inputs (content_moderation's
        # 200-row test partition with long text values).
        # ``create_dataframe(rows).create_or_replace_temp_view`` inlines
        # every row's value into the view DDL via a ``SELECT ... FROM
        # VALUES (...), (...)`` clause; with N rows of long text the
        # resulting DDL exceeds Snowflake's view-definition size budget
        # (~1 MB) and the CREATE fails — taking the whole
        # (scenario, mode) trial down with it.  Temporary TABLES have no
        # such limit because data lives in storage, not the catalog
        # definition.
        import threading

        tid = threading.get_ident()
        table_name = f"__INLINE_TEMP_AI_INPUT_{tid}_{time.time_ns()}"
        schema = _inline_input_schema(indexed_rows, all_cols)
        df = self.session.create_dataframe(indexed_rows, schema=schema)
        # First project all the columns by name so the table's schema
        # matches ``all_cols``; the typed wrapping (TO_FILE / PARSE_JSON)
        # happens downstream in the CTE's input projection SQL.
        df = df.select(*[col(c) for c in all_cols])

        attempt = 0
        remaining_ids = set(range(len(rows)))
        values_by_id: dict[int, object] = {}
        errors_by_id: dict[int, str] = {}
        sum_prompt_tokens = 0
        sum_completion_tokens = 0

        input_projection = self._build_input_view_projection_sql(all_cols)

        try:
            # ``mode="overwrite"`` so the unique-per-call ``table_name`` is
            # idempotent even on the rare collision; ``table_type="temporary"``
            # creates a session-scoped table that auto-drops on session end.
            df.write.save_as_table(table_name, mode="overwrite", table_type="temporary")

            while remaining_ids and attempt < TEMP_AI_FUNCTION_MAX_ATTEMPTS:
                attempt += 1
                # Materialize the IN-list as a SQL fragment.  ``remaining_ids``
                # is bounded by ``len(rows)`` (typically <= a few hundred for
                # GEPA minibatches) so a comma-joined IN-list is well within
                # Snowflake's expression-size limits.
                in_list = ", ".join(str(rid) for rid in sorted(remaining_ids))

                # AI_COMPLETE response shapes vary by config:
                #   * Default (no response_format): output text at
                #     ``choices[0]:messages``.
                #   * OpenAI-style providers: output text at
                #     ``choices[0]:message:content``.
                #   * With response_format (structured JSON output): output
                #     object at ``structured_output[0]:raw_message``.
                # COALESCE through all three paths so the projected VALUE
                # column matches the legacy ``value`` shape regardless of
                # whether the user's function declared a response_format.
                sql = (
                    f"WITH __ai_call AS (\n"
                    f"    SELECT __ROW_ID, ({self.inline_expr}) AS __RES\n"
                    f"    FROM (\n"
                    f"        SELECT {input_projection}\n"
                    f"        FROM {table_name}\n"
                    f"        WHERE __ROW_ID IN ({in_list})\n"
                    f"    )\n"
                    f")\n"
                    f"SELECT __ROW_ID                            AS ROW_ID,\n"
                    f"       COALESCE(\n"
                    f"           __RES:value:choices[0]:messages,\n"
                    f"           __RES:value:choices[0]:message:content,\n"
                    f"           __RES:value:structured_output[0]:raw_message\n"
                    f"       )                                   AS VALUE,\n"
                    f"       __RES:error                         AS ERROR,\n"
                    f"       __RES:value:usage:prompt_tokens     AS PROMPT_TOKENS,\n"
                    f"       __RES:value:usage:completion_tokens AS COMPLETION_TOKENS\n"
                    f"FROM __ai_call"
                )

                collected = self.session.sql(sql).collect()
                next_remaining: set[int] = set()
                for result_row in collected:
                    rid = int(result_row["ROW_ID"])
                    err = result_row["ERROR"]
                    if err is None or str(err).strip() == "":
                        values_by_id[rid] = result_row["VALUE"]
                        errors_by_id.pop(rid, None)
                        # Successful rows contribute to token totals.
                        pt = result_row["PROMPT_TOKENS"]
                        ct = result_row["COMPLETION_TOKENS"]
                        with contextlib.suppress(TypeError, ValueError):
                            sum_prompt_tokens += int(pt) if pt is not None else 0
                        with contextlib.suppress(TypeError, ValueError):
                            sum_completion_tokens += int(ct) if ct is not None else 0
                    else:
                        errors_by_id[rid] = str(err)
                        next_remaining.add(rid)

                remaining_ids = next_remaining
        finally:
            # Drop the temp table explicitly to keep the session catalog
            # tidy under heavy parallel use.  Failure to drop is non-fatal
            # because TEMPORARY tables auto-clean when the session ends.
            with contextlib.suppress(Exception):
                self.session.sql(f"DROP TABLE IF EXISTS {table_name}").collect()

        # Push token totals to the active TimingTracker (lazy import to
        # avoid a runtime dependency from this module on snow_gepa_adapter).
        if sum_prompt_tokens > 0 or sum_completion_tokens > 0:
            try:
                import importlib

                mod = importlib.import_module("snowflake_ai_optimize.gepa.adapter")
                getter = getattr(mod, "get_active_tracker", None)
                tracker = getter() if getter is not None else None
                if tracker is not None and hasattr(tracker, "add_tokens"):
                    tracker.add_tokens(
                        self.candidate_model,
                        "udf",
                        sum_prompt_tokens,
                        sum_completion_tokens,
                    )
            except Exception:
                pass

        # Populate final output (legacy semantics: error rows surface
        # ``INFERENCE_ERROR: ...``, successful rows get the model's
        # text/structured output with the accessor applied if present).
        out: list[Any] = [None] * len(rows)
        for i in range(len(rows)):
            # Error occurred, surface error into value
            if i in errors_by_id:
                err = errors_by_id.get(i, "Unknown error")
                out[i] = f"INFERENCE_ERROR: {err}"
                continue

            v = values_by_id[i]
            # Parse JSON string to dict if needed (Snowflake may return
            # VARIANT as string when collected to Python).
            if isinstance(v, str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    v = json.loads(v)
            # Apply accessor if exists (case-insensitive field lookup).
            if self.accessor_field and isinstance(v, dict):
                key_map = {str(k).upper(): k for k in v}
                key = key_map.get(self.accessor_field)
                v = v.get(key)
            out[i] = v
        return out
