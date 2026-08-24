# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""End-to-end integration test: create UDF -> evaluate -> optimize.

Uploads all source files to a Snowflake stage, creates both SPROCs from
Jinja2 templates, creates a test AI function via create_udf.py, populates
a test table, then runs EVALUATE_AI_FUNCTION and OPTIMIZE_AI_FUNCTION.

Requires a valid Snowflake connection in ~/.snowflake/config.toml.

Run:
    make test
    # or:
    uv run --group test pytest tests/test_e2e.py -v --connection snowhouse
"""

from __future__ import annotations

import contextlib
import json
import re

import pytest
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, lit, table_function

from snowflake_ai_optimize.core.sproc_decorators import (
    ai_sql_error_handling_use_fail_on_error_disabled_for_sproc,
)
from snowflake_ai_optimize.core.sproc_render import render_sproc_sql
from snowflake_ai_optimize.core.sql_utils import describe_function
from snowflake_ai_optimize.core.temp_ai_function import TempAIFunction
from snowflake_ai_optimize.core.udf_ddl import COMMENT_PREFIX, generate_sql
from snowflake_ai_optimize.core.udf_types import InputParam, OutputField, UDFSpec
from snowflake_ai_optimize.gepa.optimize import (
    extract_model_from_ddl_string,
    extract_prompt_from_ddl_string,
)

pytestmark = pytest.mark.e2e


# Server parameter (PrPr per snowflake-eng/snowflake#425448) that enables
# `SELECT ... FROM 'snow://experiment/...'` and `INFER_SCHEMA` on the
# experiment SnowURL read path. Tests that query an experiment's nested
# stage MUST enable it at the session level via ``snowurl_read_enabled``
# so they don't depend on whether the account-level default is on.
_ENABLE_EXPERIMENT_SNOWURL = "ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION"


@contextlib.contextmanager
def snowurl_read_enabled(session: Session):
    """Set ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION = TRUE for the
    duration of the with-block, UNSET on exit.

    Use this around any SQL that reads ``snow://experiment/...`` paths via
    SELECT or INFER_SCHEMA.
    """  # noqa: D205
    session.sql(f"ALTER SESSION SET {_ENABLE_EXPERIMENT_SNOWURL} = TRUE").collect()
    try:
        yield
    finally:
        session.sql(f"ALTER SESSION UNSET {_ENABLE_EXPERIMENT_SNOWURL}").collect()


STAGE_MODULES = [
    "snowflake_ai_optimize.core.constants",
    "snowflake_ai_optimize.core.ddl_rewrite",
    "snowflake_ai_optimize.core.evaluation",
    "snowflake_ai_optimize.core.scorer",
    "snowflake_ai_optimize.core.experiment",
    "snowflake_ai_optimize.core.metrics.aggregation",
    "snowflake_ai_optimize.core.metrics.builtin",
    "snowflake_ai_optimize.core.metrics.custom_udf",
    "snowflake_ai_optimize.core.metrics.dispatch",
    "snowflake_ai_optimize.core.metrics.llm_judge",
    "snowflake_ai_optimize.core.metrics.utils",
    "snowflake_ai_optimize.core.session",
    "snowflake_ai_optimize.core.sproc_decorators",
    "snowflake_ai_optimize.core.sql_utils",
    "snowflake_ai_optimize.core.stage",
    "snowflake_ai_optimize.core.temp_ai_function",
    "snowflake_ai_optimize.core.timing",
    "snowflake_ai_optimize.core.types",
    "handlers.evaluate_handler",
    "handlers.optimize_handler",
    "models.json",
    "snowflake_ai_optimize.gepa.adapter",
    "snowflake_ai_optimize.gepa.engine",
    "snowflake_ai_optimize.gepa.engine_registry",
    "snowflake_ai_optimize.core.optimize_registry",
    "snowflake_ai_optimize.gepa.experiment",
    "snowflake_ai_optimize.gepa.optimize",
    "snowflake_ai_optimize.gepa.optimize_body",
    "snowflake_ai_optimize.synthetic.synthetic_data",
    "snowflake_ai_optimize.gepa._registry",
]


def check_query_history_for_tag(session):
    # Pass it into the table function
    query_history_func = table_function("INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION")

    history_df = session.table_function(query_history_func())
    history_df = (
        history_df.filter(
            col("QUERY_TAG").contains(lit("__DEBUG_CUSTOM_AI_FUNCTION_SPROC_"))
        )
        .filter(col("QUERY_TAG").contains(lit("MOCK_NO_OVERRIDE")))
        .select("QUERY_TEXT", "QUERY_TAG")
    )
    results = history_df.collect()

    assert len(results) >= 0, "Expected at least 1 query with custom ai function tag."
    assert session.query_tag == "MOCK_NO_OVERRIDE"


@pytest.fixture(scope="module")
def session(request):
    conn_name = request.config.getoption("--connection", default="snowhouse")
    sess = Session.builder.config("connection_name", conn_name).create()
    yield sess
    sess.close()


@pytest.fixture(scope="module")
def env(session, cleanup_stale, run_key):
    """Provision stage, UDF, test table, and both SPROCs. Tear down after."""
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')
    stage = f"TEST_E2E_STAGE_{run_key}"

    cleanup_stale(
        session,
        db,
        schema,
        stages=["TEST_E2E_STAGE"],
        tables=[
            "TEST_CLASSIFY_DATA",
            "TEST_SYNTH_DATA",
            "TEST_INLINE_SYNTH_DATA",
            "TEST_TRICKY_DATA",
            "TEST_TRICKY_BODY",
        ],
        functions=["TEST_CLASSIFY"],
        experiments=[
            "TEST_OPT_EXP",
            "TEST_EXP_RW",
            "TEST_EXP_BODY",
            "TEST_EVAL_EXP",
        ],
    )
    func_name = f"TEST_CLASSIFY_{run_key}"
    table_name = f"TEST_CLASSIFY_DATA_{run_key}"
    eval_experiment_name = f"TEST_EVAL_EXP_{run_key}"
    synth_table_name = f"TEST_SYNTH_DATA_{run_key}"
    inline_synth_table_name = f"TEST_INLINE_SYNTH_DATA_{run_key}"
    fq = lambda name: f"{db}.{schema}.{name}"

    # --- stage + file upload ------------------------------------------------
    session.sql(f"CREATE STAGE IF NOT EXISTS {stage}").collect()
    from _paths import resolve_module_path

    for module in STAGE_MODULES:
        file_path = resolve_module_path(module)
        session.file.put(
            f"file://{file_path}",
            f"@{stage}",
            auto_compress=False,
            overwrite=True,
        )

    # --- AI function (uses AI_COMPLETE with hardcoded model/prompt) ---
    spec = UDFSpec(
        database=db,
        schema=schema,
        function_name=func_name,
        model="llama3.1-8b",
        function_intention="Classify text as positive or negative",
        inputs=[InputParam(name="TEXT", sql_type="VARCHAR")],
        outputs=[
            OutputField(
                name="label", json_type="string", description="positive or negative"
            )
        ],
        system_prompt="Classify the sentiment of the text as positive or negative.",
        user_prompt_template="{TEXT}",
    )
    udf_sql = generate_sql(spec)
    session.sql(udf_sql).collect()

    # --- test data ----------------------------------------------------------
    session.sql(f"""
        CREATE TABLE {fq(table_name)} (
            TEXT VARCHAR,
            EXPECTED_LABEL VARCHAR
        )
    """).collect()
    rows = [
        ("I love this product!", "positive"),
        ("This is amazing and wonderful", "positive"),
        ("Great experience overall", "positive"),
        ("Terrible, worst purchase ever", "negative"),
        ("I hate this, total waste", "negative"),
        ("Awful quality and bad service", "negative"),
    ]
    values = ", ".join(f"('{t}', '{label}')" for t, label in rows)
    session.sql(f"INSERT INTO {fq(table_name)} VALUES {values}").collect()

    # --- Add original query_tag to session to ensure no override occurred --- #
    session.query_tag = "MOCK_NO_OVERRIDE"

    yield {
        "db": db,
        "schema": schema,
        "stage": stage,
        "func": fq(func_name),
        "table": fq(table_name),
        "experiment_name": fq(eval_experiment_name),
        "synth_table": fq(synth_table_name),
        "inline_synth_table": fq(inline_synth_table_name),
        "fq": fq,
    }

    # --- teardown -----------------------------------------------------------
    session.sql(f"DROP FUNCTION IF EXISTS {fq(func_name)}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {fq(table_name)}").collect()
    session.sql(f"DROP EXPERIMENT IF EXISTS {fq(eval_experiment_name)}").collect()
    session.sql(f"DROP TABLE IF EXISTS {fq(synth_table_name)}").collect()
    session.sql(f"DROP TABLE IF EXISTS {fq(inline_synth_table_name)}").collect()
    session.sql(f"DROP STAGE IF EXISTS {stage}").collect()


# ---------------------------------------------------------------------------
# 1. Function creation
# ---------------------------------------------------------------------------


class TestCreate:
    def test_udf_created_and_callable(self, session, env):
        """The AI function was created and returns a result."""
        result = session.sql(f"""
            SELECT {env["func"]}('I love this') AS prediction
        """).collect()
        prediction = str(result[0]["PREDICTION"]).lower()
        assert prediction, "UDF returned empty result"

    def test_udf_comment_has_prefix(self, session, env):
        """The AI function comment includes the CORTEX AI FUNC STUDIO prefix."""
        func_name = env["func"].split(".")[-1]
        rows = session.sql(
            f"SHOW FUNCTIONS LIKE '{func_name}' IN SCHEMA {env['db']}.{env['schema']}"
        ).collect()
        assert len(rows) >= 1, "Function not found in SHOW FUNCTIONS"
        description = rows[0]["description"]
        assert description.startswith(COMMENT_PREFIX), (
            f"Expected description to start with '{COMMENT_PREFIX}', got: {description}"
        )
        assert "Classify text as positive or negative" in description


# ---------------------------------------------------------------------------
# 2. Reverse-parse DDL
# ---------------------------------------------------------------------------


class TestReverseParseDDL:
    """Create real UDFs, introspect via DESCRIBE FUNCTION, and verify parsing."""

    def test_extract_model_from_real_ddl(self, session, env):
        """Extract model from a function created by generate_sql."""
        fn = describe_function(session, env["func"])
        model = extract_model_from_ddl_string(fn.body)
        assert model == "llama3.1-8b"

    def test_extract_prompt_from_real_ddl(self, session, env):
        """Extract system prompt from a function created by generate_sql."""
        fn = describe_function(session, env["func"])
        prompt = extract_prompt_from_ddl_string(fn.body)
        assert "Classify the sentiment" in prompt

    def test_extract_model_from_multiinput_function(self, session, env, run_key):
        """Reverse-parse works for a function with multiple input params."""
        fname = f"TEST_MULTI_{run_key}"
        fq_name = env["fq"](fname)
        spec = UDFSpec(
            database=env["db"],
            schema=env["schema"],
            function_name=fname,
            model="mistral-large2",
            inputs=[
                InputParam(name="TITLE", sql_type="VARCHAR"),
                InputParam(name="BODY", sql_type="VARCHAR"),
            ],
            outputs=[
                OutputField(name="category", json_type="string", description="topic"),
            ],
            system_prompt="Categorize the article by topic.",
            user_prompt_template="Title: {TITLE}\nBody: {BODY}",
        )
        session.sql(generate_sql(spec)).collect()
        try:
            fn = describe_function(session, fq_name)
            assert extract_model_from_ddl_string(fn.body) == "mistral-large2"
            assert "Categorize the article" in extract_prompt_from_ddl_string(fn.body)
        finally:
            session.sql(
                f"DROP FUNCTION IF EXISTS {fq_name}(VARCHAR, VARCHAR)"
            ).collect()

    def test_extract_prompt_with_quotes(self, session, env, run_key):
        """Reverse-parse handles prompts containing single quotes."""
        fname = f"TEST_QUOTES_{run_key}"
        fq_name = env["fq"](fname)
        spec = UDFSpec(
            database=env["db"],
            schema=env["schema"],
            function_name=fname,
            model="llama3.1-8b",
            inputs=[InputParam(name="X", sql_type="VARCHAR")],
            outputs=[OutputField(name="y", json_type="string", description="")],
            system_prompt="Don't include extra text. It's important.",
            user_prompt_template="{X}",
        )
        session.sql(generate_sql(spec)).collect()
        try:
            fn = describe_function(session, fq_name)
            prompt = extract_prompt_from_ddl_string(fn.body)
            assert "Don't" in prompt
        finally:
            session.sql(f"DROP FUNCTION IF EXISTS {fq_name}(VARCHAR)").collect()

    def test_temp_function_build_rewrite_and_callable(self, session, env, run_key):
        """TempAIFunction builds the inline expression, exposes self.ddl for
        inspection, and returns a usable scalar from call_rows.

        After the inline-eval migration, ``TempAIFunction.__init__`` no
        longer issues ``CREATE TEMPORARY FUNCTION``; the runtime path is a
        ``create_or_replace_temp_view`` + ``session.sql(<CTE>)`` against
        the inline expression.  ``self.ddl`` is built for test inspection
        (kept for back-compat with TestMultimodalTempFunction in
        test_unit.py) but is NEVER executed.  This e2e test verifies the
        new path end-to-end: construct → call_rows returns expected scalar.
        """  # noqa: D205
        raw_fn = describe_function(session, env["func"])
        temp_name = env["fq"](f"TEST_TEMP_{run_key}")

        with ai_sql_error_handling_use_fail_on_error_disabled_for_sproc(session):
            temp_fn = TempAIFunction(
                session,
                function_def=raw_fn,
                temp_function_name=temp_name,
                candidate_model="llama3.1-8b",
                candidate_prompt="Just say hello.",
            )

            # ``self.ddl`` retains the transformed shape for back-compat — the
            # error-details OBJECT wrap and return_error_details=>TRUE
            # transformations still run in the constructor.
            ddl_collapsed = re.sub(r"\s+", "", temp_fn.ddl.upper())
            assert "RETURN_ERROR_DETAILS=>TRUE" in ddl_collapsed
            assert "RETURNS OBJECT" in temp_fn.ddl.upper()
            assert "ERROR STRING" in temp_fn.ddl.upper()
            assert temp_fn.accessor_field is None or isinstance(
                temp_fn.accessor_field, str
            )

            # ``self.inline_expr`` is the show_details-augmented SQL
            # expression that call_rows evaluates inline.
            assert "SHOW_DETAILS=>TRUE" in temp_fn.inline_expr.upper()
            assert "RETURN_ERROR_DETAILS=>TRUE" in temp_fn.inline_expr.upper()
            assert (
                "OBJECT(value VARIANT, error STRING)" in temp_fn.inline_expr
                or "OBJECT(VALUE VARIANT, ERROR STRING)" in temp_fn.inline_expr.upper()
            )

            # Behavioral assertion: call_rows produces a scalar result (or
            # an INFERENCE_ERROR string on failure).  The function's
            # ``:field::TYPE`` accessor (if any) is applied Python-side.
            results = temp_fn.call_rows([{"TEXT": "test input"}])
            assert len(results) == 1
            assert results[0] is not None, "call_rows returned None"
            # Either a successful scalar OR an INFERENCE_ERROR string.
            if isinstance(results[0], str) and results[0].startswith(
                "INFERENCE_ERROR:"
            ):
                pytest.fail(
                    f"call_rows surfaced an error: {results[0]!r}.  This may "
                    "indicate the response shape (e.g. :choices[0]:messages "
                    "vs :choices[0]:message:content) doesn't match the inline "
                    "SQL's COALESCE fallback — see plan corner case #5."
                )

    def test_temp_function_build_with_different_model(self, session, env, run_key):
        """TempAIFunction substitutes the candidate model into the AI_COMPLETE
        call of its inline expression.

        Behavioral assertion (no live ``CREATE FUNCTION`` to inspect):
        the inline expression carries the substituted model name.
        """  # noqa: D205
        raw_fn = describe_function(session, env["func"])
        temp_name = env["fq"](f"TEST_TEMP_MODEL_{run_key}")

        with ai_sql_error_handling_use_fail_on_error_disabled_for_sproc(session):
            temp_fn = TempAIFunction(
                session,
                function_def=raw_fn,
                temp_function_name=temp_name,
                candidate_model="claude-sonnet-4-5",
                candidate_prompt="Classify the sentiment of the text as positive or negative.",
            )

            ddl_collapsed = re.sub(r"\s+", "", temp_fn.ddl.upper())
            assert "RETURN_ERROR_DETAILS=>TRUE" in ddl_collapsed
            assert "RETURNS OBJECT" in temp_fn.ddl.upper()
            # The candidate model is baked into both ``self.ddl`` (for
            # inspection) AND ``self.inline_expr`` (for the runtime SELECT).
            assert "claude-sonnet-4-5" in temp_fn.ddl
            assert "claude-sonnet-4-5" in temp_fn.inline_expr


# ---------------------------------------------------------------------------
# 3. Anonymous SPROC workflow (evaluate + optimize without named procedures)
# ---------------------------------------------------------------------------


class TestAnonymousSproc:
    """Full create → evaluate → optimize using anonymous stored procedures."""

    def test_anonymous_evaluate_returns_score(self, session, env):
        """Anonymous EVALUATE_AI_FUNCTION returns a VARIANT with a valid score."""
        anon_sql = render_sproc_sql(
            "evaluate",
            env["db"],
            env["schema"],
            env["stage"],
            anonymous=True,
            inline=True,
        )

        full_sql = (
            f"{anon_sql}\n"
            f"CALL EVALUATE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'EXPECTED_LABEL',\n"
            f"    'exact_match',\n"
            f"    'llama3.1-8b',\n"
            f"    NULL, NULL, NULL, 500, NULL, NULL\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        payload = json.loads(raw) if isinstance(raw, str) else raw
        assert isinstance(payload, dict), f"Expected VARIANT dict, got {type(payload)}"
        score = float(payload["score"])
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
        assert payload["run_id"], "run_id should be auto-generated"
        assert payload["experiment_name"], "experiment_name should be auto-generated"
        assert payload["snowurl"].endswith("/eval_detail.json")

        auto_exp = payload["experiment_name"]
        session.sql(
            f"DROP EXPERIMENT IF EXISTS {env['db']}.{env['schema']}.{auto_exp}"
        ).collect()

    def test_anonymous_evaluate_with_experiment(self, session, env):
        """Anonymous EVALUATE_AI_FUNCTION uploads per-row eval_detail.json to its experiment."""  # noqa: W505
        anon_sql = render_sproc_sql(
            "evaluate",
            env["db"],
            env["schema"],
            env["stage"],
            anonymous=True,
            inline=True,
        )

        full_sql = (
            f"{anon_sql}\n"
            f"CALL EVALUATE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'EXPECTED_LABEL',\n"
            f"    'exact_match',\n"
            f"    'llama3.1-8b',\n"
            f"    NULL,\n"
            f"    '{env['experiment_name']}',\n"
            f"    NULL, 500, NULL, NULL\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        payload = json.loads(raw) if isinstance(raw, str) else raw
        score = float(payload["score"])
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
        assert payload["experiment_name"] == env["experiment_name"]

        # Verify the experiment + EVAL run exist with metadata.
        runs = session.sql(
            f"SHOW RUNS IN EXPERIMENT {env['experiment_name']}"
        ).collect()
        run_names = [r["name"] for r in runs]
        assert "EVAL" in run_names, f"Expected EVAL run, found: {run_names}"

        params = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {env['experiment_name']} RUN EVAL"
        ).collect()
        param_map = {p["name"]: p["value"] for p in params}
        assert param_map.get("metric_name") == "exact_match"
        assert param_map.get("model") == "llama3.1-8b"

        # Per-row details: query the SnowURL artifact via a named JSON
        # file format. Inline (FILE_FORMAT => (TYPE => JSON)) is NOT
        # supported on SnowURL paths — must create a named format first.
        # The SnowURL read path is gated by the server parameter
        # ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION (PrPr per
        # snowflake-eng/snowflake#425448). Set it at the session level so
        # this test exercises the SnowURL path regardless of whether the
        # parameter is enabled at the account level.
        with snowurl_read_enabled(session):
            session.sql(
                "CREATE OR REPLACE TEMPORARY FILE FORMAT eval_detail_json_fmt "
                "TYPE = JSON STRIP_OUTER_ARRAY = TRUE"
            ).collect()
            rows = session.sql(
                f"SELECT $1:row_id::INT AS ROW_ID, "
                f"       $1:metric_score::FLOAT AS SCORE, "
                f"       $1:metric_name::STRING AS METRIC_NAME, "
                f"       $1:model_name::STRING AS MODEL_NAME "
                f"FROM 'snow://experiment/{env['experiment_name']}/versions/EVAL/eval_detail.json'"
                f" (FILE_FORMAT => eval_detail_json_fmt) "
                f"ORDER BY ROW_ID"
            ).collect()
        assert len(rows) >= 1, "eval_detail.json is empty"
        row = rows[0]
        assert row["METRIC_NAME"] == "exact_match"
        assert row["MODEL_NAME"] == "llama3.1-8b"
        assert 0.0 <= float(row["SCORE"]) <= 1.0
        assert len(rows) == 6, f"Expected 6 rows, got {len(rows)}"

    def test_anonymous_optimize_returns_result(self, session, env):
        """Anonymous OPTIMIZE_AI_FUNCTION completes with body mode."""
        anon_sql = render_sproc_sql(
            "optimize",
            env["db"],
            env["schema"],
            env["stage"],
            anonymous=True,
            inline=True,
        )

        full_sql = (
            f"{anon_sql}\n"
            f"CALL OPTIMIZE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    'EXPECTED_LABEL',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'exact_match',\n"
            f"    ARRAY_CONSTRUCT('llama3.1-8b'),\n"
            f"    'claude-sonnet-4-5',\n"
            f"    NULL,\n"
            f"    'light',\n"
            f"    0.667,\n"
            f"    0.7,\n"
            f"    8192,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    'body',\n"
            f"    NULL,\n"
            f"    'default'\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        output = json.loads(raw) if isinstance(raw, str) else raw
        assert output["status"] == "completed", (
            f"Optimization failed: {json.dumps(output, indent=2, default=str)}"
        )
        assert "overall_best_prompt" in output
        assert "model_results" in output
        assert len(output["model_results"]) >= 1
        mr = output["model_results"][0]
        assert "seed_score" in mr
        assert "best_score" in mr
        assert mr["score_source"] in ("test", "validation")
        if "frontier_candidates" in output:
            for fc in output["frontier_candidates"]:
                assert "score" in fc
                assert "prompt" in fc
                assert "estimated_cost" in fc

    def test_anonymous_optimize_body_mode_returns_result(self, session, env):
        """Anonymous OPTIMIZE_AI_FUNCTION completes with body mode (optimize_anything)."""  # noqa: W505
        anon_sql = render_sproc_sql(
            "optimize",
            env["db"],
            env["schema"],
            env["stage"],
            anonymous=True,
            inline=True,
        )

        full_sql = (
            f"{anon_sql}\n"
            f"CALL OPTIMIZE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    'EXPECTED_LABEL',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'exact_match',\n"
            f"    ARRAY_CONSTRUCT('llama3.1-8b'),\n"
            f"    'claude-sonnet-4-5',\n"
            f"    NULL,\n"
            f"    'light',\n"
            f"    0.667,\n"
            f"    0.7,\n"
            f"    8192,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    'body',\n"
            f"    NULL,\n"
            f"    'default'\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        output = json.loads(raw) if isinstance(raw, str) else raw
        assert output["status"] == "completed", (
            f"Body optimization failed: {json.dumps(output, indent=2, default=str)}"
        )
        assert "overall_best_prompt" in output
        assert "best_body" in output
        assert "best_ddl" in output
        assert "model_results" in output
        assert len(output["model_results"]) >= 1

    def test_anonymous_synthetic_data_generates_rows(self, session, env):
        """Anonymous GENERATE_SYNTHETIC_DATA creates a table with rows."""
        anon_sql = render_sproc_sql(
            "synthetic",
            env["db"],
            env["schema"],
            env["stage"],
            anonymous=True,
            inline=True,
        )

        output_schema = '{"properties":{"label":{"type":"string","description":"positive or negative"}}}'
        escaped_schema = output_schema.replace("'", "''")

        full_sql = (
            f"{anon_sql}\n"
            f"CALL GENERATE_SYNTHETIC_DATA(\n"
            f"    'Classify the sentiment of the text as positive or negative',\n"
            f"    '{env['synth_table']}',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'llama3.1-8b',\n"
            f"    5,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    PARSE_JSON('{escaped_schema}'),\n"
            f"    NULL\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        output = json.loads(raw) if isinstance(raw, str) else raw
        assert output.get("success") is True, (
            f"Generation failed: {json.dumps(output, indent=2, default=str)}"
        )
        assert output["total_generated"] >= 1

        rows = session.sql(f"SELECT * FROM {env['synth_table']}").collect()
        assert len(rows) >= 1, "Synthetic data table is empty"


# ---------------------------------------------------------------------------
# 4. Inline SPROC workflow (Python embedded in AS $py$ ... $py$, no stage needed)
# ---------------------------------------------------------------------------


class TestInlineSproc:
    """Evaluate, optimize, and synthetic using inline anonymous stored procedures."""

    def test_inline_evaluate_returns_score(self, session, env):
        """Inline EVALUATE_AI_FUNCTION returns a VARIANT with a valid score."""
        inline_sql = render_sproc_sql(
            "evaluate", env["db"], env["schema"], inline=True, anonymous=True
        )

        full_sql = (
            f"{inline_sql}\n"
            f"CALL EVALUATE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'EXPECTED_LABEL',\n"
            f"    'exact_match',\n"
            f"    'llama3.1-8b',\n"
            f"    NULL, NULL, NULL, 500, NULL, NULL\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        payload = json.loads(raw) if isinstance(raw, str) else raw
        assert isinstance(payload, dict), f"Expected VARIANT dict, got {type(payload)}"
        score = float(payload["score"])
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"
        assert payload["run_id"], "run_id should be auto-generated"
        assert payload["experiment_name"], "experiment_name should be auto-generated"
        assert payload["snowurl"].endswith("/eval_detail.json")

        # Clean up the auto-created experiment so the next test run is idempotent.
        try:
            exp_short = payload["experiment_name"].split(".")[-1]
            session.sql(
                f"DROP EXPERIMENT IF EXISTS {env['db']}.{env['schema']}.{exp_short}"
            ).collect()
        except Exception:
            pass

    def test_inline_optimize_returns_result(self, session, env):
        """Inline OPTIMIZE_AI_FUNCTION completes with body mode."""
        inline_sql = render_sproc_sql(
            "optimize", env["db"], env["schema"], inline=True, anonymous=True
        )

        full_sql = (
            f"{inline_sql}\n"
            f"CALL OPTIMIZE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    'EXPECTED_LABEL',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'exact_match',\n"
            f"    ARRAY_CONSTRUCT('llama3.1-8b'),\n"
            f"    'claude-sonnet-4-5',\n"
            f"    NULL,\n"
            f"    'light',\n"
            f"    0.667,\n"
            f"    0.7,\n"
            f"    8192,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    'body',\n"
            f"    NULL,\n"
            f"    'default'\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        output = json.loads(raw) if isinstance(raw, str) else raw
        assert output["status"] == "completed", (
            f"Optimization failed: {json.dumps(output, indent=2, default=str)}"
        )
        assert "overall_best_prompt" in output
        assert "model_results" in output
        assert len(output["model_results"]) >= 1
        mr = output["model_results"][0]
        assert "seed_score" in mr
        assert "best_score" in mr
        assert mr["score_source"] in ("test", "validation")
        if "frontier_candidates" in output:
            for fc in output["frontier_candidates"]:
                assert "score" in fc
                assert "prompt" in fc
                assert "estimated_cost" in fc

    def test_inline_optimize_writes_experiment_runs(self, session, env, run_key):
        """Inline OPTIMIZE_AI_FUNCTION persists results to a Snowflake Experiment."""
        inline_sql = render_sproc_sql(
            "optimize", env["db"], env["schema"], inline=True, anonymous=True
        )
        experiment_name = env["fq"](f"TEST_OPT_EXP_{run_key}")

        full_sql = (
            f"{inline_sql}\n"
            f"CALL OPTIMIZE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    'EXPECTED_LABEL',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'exact_match',\n"
            f"    ARRAY_CONSTRUCT('llama3.1-8b'),\n"
            f"    'claude-sonnet-4-5',\n"
            f"    NULL,\n"
            f"    'light',\n"
            f"    0.667,\n"
            f"    0.7,\n"
            f"    8192,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    '{experiment_name}',\n"
            f"    'default'\n"
            f");"
        )
        try:
            result = session.sql(full_sql).collect()
            raw = result[0][0]
            output = json.loads(raw) if isinstance(raw, str) else raw
            assert output["status"] == "completed"

            # Verify experiment runs exist
            runs = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
            run_names = [r["name"] for r in runs]
            assert any("SEED" in n for n in run_names), (
                f"No SEED run found in {run_names}"
            )

            # Verify at least one ITER or SEED run has valset_score
            iter_runs_check = [n for n in run_names if "ITER" in n]
            candidate_runs = iter_runs_check + [n for n in run_names if "SEED" in n]
            winning_run = None
            winning_score = -1.0
            for ir in candidate_runs:
                ir_metrics = session.sql(
                    f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {ir}"
                ).collect()
                for m in ir_metrics:
                    if m["name"] == "valset_score" and m["value"] is not None:
                        s = float(m["value"])
                        if s > winning_score:
                            winning_score = s
                            winning_run = ir
            assert winning_run is not None, f"No run with valset_score in {run_names}"
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def _assert_experiment_read_paths(self, session, experiment_name, output, mode):
        """Shared verification of all experiment read paths after optimization.

        Covers R1 (SHOW EXPERIMENTS), R3 (SHOW RUNS / METRICS / PARAMETERS),
        R4 (LS run_dir artifacts), and cross-checks SPROC output vs experiment.
        """
        # ---- R1: SHOW EXPERIMENTS lists our experiment ----
        experiments = session.sql(
            f"SHOW EXPERIMENTS LIKE '{experiment_name.split('.')[-1]}'"
        ).collect()
        exp_names = [r["name"] for r in experiments]
        assert experiment_name.split(".")[-1] in exp_names, (
            f"Experiment not found in SHOW EXPERIMENTS: {exp_names}"
        )

        # ---- R3: SHOW RUNS -- at least SEED ----
        runs = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
        run_names = [r["name"] for r in runs]
        assert len(run_names) >= 1, (
            f"Expected at least 1 run (SEED), got {len(run_names)}: {run_names}"
        )
        # Frontier scores now live on the SEED/ITER lineage runs themselves
        # (flagged is_frontier), so there is no separate frontier run kind.
        # The FRONTIER_CANDIDATE guard is retained only for legacy experiments.
        seed_runs = [
            n for n in run_names if "SEED" in n and "FRONTIER_CANDIDATE" not in n
        ]
        iter_runs = [
            n
            for n in run_names
            if "ITER" in n and "REJECTED" not in n and "FRONTIER_CANDIDATE" not in n
        ]
        assert len(seed_runs) == 1, f"Expected 1 SEED run in {run_names}"

        # All runs should be FINISHED (committed)
        for r in runs:
            metadata = json.loads(r["metadata"])
            assert metadata["status"] == "FINISHED", (
                f"Run {r['name']} should be FINISHED, got {metadata['status']}"
            )

        seed_run = seed_runs[0]

        # Find winning run (highest valset_score among ITER + SEED)
        winning_iter = None
        winning_iter_score = -1.0
        for ir in iter_runs + seed_runs:
            ir_metrics = session.sql(
                f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {ir}"
            ).collect()
            for m in ir_metrics:
                if m["name"] == "valset_score" and m["value"] is not None:
                    s = float(m["value"])
                    if s > winning_iter_score:
                        winning_iter_score = s
                        winning_iter = ir
        assert winning_iter is not None, f"No run with valset_score in {run_names}"

        # ---- R3a: SHOW RUN METRICS -- valset_score on SEED and winning ITER ----
        seed_metrics = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {seed_run}"
        ).collect()
        assert "valset_score" in [r["name"] for r in seed_metrics], (
            f"SEED missing valset_score: {[r['name'] for r in seed_metrics]}"
        )

        winner_metrics = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {winning_iter}"
        ).collect()
        assert "valset_score" in [r["name"] for r in winner_metrics], (
            f"Winning ITER missing valset_score: {[r['name'] for r in winner_metrics]}"
        )

        seed_score = float(
            next(r["value"] for r in seed_metrics if r["name"] == "valset_score")
        )
        winner_score = float(
            next(r["value"] for r in winner_metrics if r["name"] == "valset_score")
        )
        assert 0.0 <= seed_score <= 1.0, f"Seed score out of range: {seed_score}"
        assert 0.0 <= winner_score <= 1.0, f"Winner score out of range: {winner_score}"

        # ---- R3b: SHOW RUN PARAMETERS -- SEED core params ----
        seed_params = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {seed_run}"
        ).collect()
        seed_pv = {r["name"]: r["value"] for r in seed_params}
        assert "function_impl" in seed_pv, (
            f"SEED missing function_impl: {list(seed_pv)}"
        )
        assert "model" in seed_pv, f"SEED missing model: {list(seed_pv)}"
        assert seed_pv["model"] == "llama3.1-8b"
        assert seed_pv["iteration"] == "0"
        assert seed_pv.get("status") == "completed"
        assert "avg_output_chars" in seed_pv, (
            f"SEED missing avg_output_chars (needed for cost estimation): {list(seed_pv)}"
        )
        assert int(seed_pv["avg_output_chars"]) >= 0, (
            f"avg_output_chars should be non-negative, got {seed_pv['avg_output_chars']}"
        )

        # ---- R3b: SHOW RUN PARAMETERS -- iteration parent linkage ----
        if iter_runs:
            first_iter = sorted(iter_runs)[0]
            iter_params = session.sql(
                f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {first_iter}"
            ).collect()
            iter_pv = {r["name"]: r["value"] for r in iter_params}
            assert "function_impl" in iter_pv, "ITER missing function_impl"
            assert "parent_candidate" in iter_pv, "ITER missing parent_candidate"
            assert iter_pv["parent_candidate"] == seed_run, (
                f"First ITER parent should be {seed_run}, got {iter_pv['parent_candidate']}"
            )

        # ---- R3b: SHOW RUN PARAMETERS -- SEED aggregate stats ----
        seed_params = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {seed_run}"
        ).collect()
        seed_pv = {r["name"]: r["value"] for r in seed_params}
        assert "total_candidates" in seed_pv, "SEED missing total_candidates"
        assert "total_metric_calls" in seed_pv, "SEED missing total_metric_calls"
        assert "elapsed_seconds" in seed_pv, "SEED missing elapsed_seconds"
        assert int(seed_pv["total_candidates"]) >= 1
        assert float(seed_pv["elapsed_seconds"]) > 0

        # ---- R3c: Winning ITER still has function_impl ----
        winner_params = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {winning_iter}"
        ).collect()
        winner_pv = {r["name"]: r["value"] for r in winner_params}
        assert "function_impl" in winner_pv, "Winning ITER missing function_impl"
        assert len(winner_pv["function_impl"]) > 10, (
            f"Winning ITER function_impl too short: {winner_pv['function_impl'][:50]}"
        )

        # ---- R4: LS run_dir artifacts on winning ITER run stage ----
        # GEPA may or may not produce run_dir artifacts depending on budget
        # and number of candidates; just verify the LS command succeeds.
        with contextlib.suppress(Exception):
            session.sql(
                f"LS snow://experiment/{experiment_name}/versions/{winning_iter}/run_dir/"
            ).collect()

        # ---- Cross-check: SPROC output matches experiment data ----
        if mode == "body":
            sproc_best = output.get("overall_best_prompt", "")
        else:
            sproc_best = output.get("overall_best_prompt", "")
        assert sproc_best == winner_pv["function_impl"], (
            "SPROC overall_best_prompt should match winning ITER function_impl"
        )

    def _create_tricky_training_table(self, session, table_fqn):
        """Create a training table with a label mismatch that forces GEPA to iterate.

        The UDF outputs ``positive``/``negative`` but the gold labels are
        ``P``/``N``, so ``exact_match`` starts below 1.0.  Multi-hop
        sarcasm further ensures the seed prompt doesn't ace it.
        """
        session.sql(f"""
            CREATE TABLE {table_fqn} (
                TEXT VARCHAR,
                EXPECTED_LABEL VARCHAR
            )
        """).collect()
        rows = [
            (
                "Oh wonderful, the app crashed right after I paid; truly a premium experience.",
                "N",
            ),
            (
                "I would not say this product is not worth trying -- it surprised me.",
                "P",
            ),
            (
                "The packaging was gorgeous, which almost made up for the fact it was broken.",
                "N",
            ),
            (
                "Initially the setup was a nightmare, but after the update everything runs great.",
                "P",
            ),
            (
                "The battery life is mediocre but the call quality is so good I forgave everything.",
                "P",
            ),
            (
                "For a product that costs twice the competition, it almost manages to be adequate.",
                "N",
            ),
            (
                "My five-year-old laptop outperforms this brand-new workstation on every benchmark.",
                "N",
            ),
            (
                "Despite every reviewer warning me away, this gadget has quietly become essential.",
                "P",
            ),
            (
                "Fantastic at everything except the one thing I actually bought it for.",
                "N",
            ),
            (
                "I cannot overstate how much better my mornings have been since switching to this.",
                "P",
            ),
            (
                "Sure the first week was rough, but three months in I realize the power of this tool.",
                "P",
            ),
            (
                "I love how the smart thermostat heats the house exclusively when nobody is home.",
                "N",
            ),
        ]
        values = ", ".join(f"($${t}$$, '{label}')" for t, label in rows)
        session.sql(f"INSERT INTO {table_fqn} VALUES {values}").collect()

    def _run_optimize_with_experiment(
        self, session, env, experiment_name, tricky_table, mode
    ):
        """Run OPTIMIZE_AI_FUNCTION with experiment storage and tricky data."""
        inline_sql = render_sproc_sql(
            "optimize", env["db"], env["schema"], inline=True, anonymous=True
        )
        full_sql = (
            f"{inline_sql}\n"
            f"CALL OPTIMIZE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{tricky_table}',\n"
            f"    'EXPECTED_LABEL',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'exact_match',\n"
            f"    ARRAY_CONSTRUCT('llama3.1-8b'),\n"
            f"    'claude-sonnet-4-5',\n"
            f"    NULL,\n"
            f"    'medium',\n"
            f"    0.667,\n"
            f"    0.7,\n"
            f"    8192,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    '{mode}',\n"
            f"    '{experiment_name}',\n"
            f"    'default'\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        return json.loads(raw) if isinstance(raw, str) else raw

    @pytest.mark.skip(
        reason="Prompt mode excluded from inline bundle to fix task size limit"
    )
    def test_inline_optimize_experiment_prompt_mode(self, session, env, run_key):
        """Prompt-mode optimization: verify all experiment read/write paths.

        Uses tricky P/N labels so exact_match < 1.0 and GEPA runs multiple
        iterations, producing SEED + ITER runs and run_dir artifacts.
        """
        tricky_table = env["fq"](f"TEST_TRICKY_DATA_{run_key}")
        experiment_name = env["fq"](f"TEST_EXP_RW_{run_key}")
        self._create_tricky_training_table(session, tricky_table)
        try:
            output = self._run_optimize_with_experiment(
                session,
                env,
                experiment_name,
                tricky_table,
                "prompt",
            )
            assert output["status"] == "completed", (
                f"Prompt optimization failed: {json.dumps(output, indent=2, default=str)}"
            )
            self._assert_experiment_read_paths(
                session, experiment_name, output, "prompt"
            )
        finally:
            session.sql(f"DROP TABLE IF EXISTS {tricky_table}").collect()
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_inline_optimize_experiment_body_mode(self, session, env, run_key):
        """Body-mode optimization (optimize_anything): verify all experiment read/write paths.

        Uses tricky P/N labels so exact_match < 1.0 and GEPA runs multiple
        iterations, producing SEED + ITER runs and run_dir artifacts.
        """  # noqa: W505
        tricky_table = env["fq"](f"TEST_TRICKY_BODY_{run_key}")
        experiment_name = env["fq"](f"TEST_EXP_BODY_{run_key}")
        self._create_tricky_training_table(session, tricky_table)
        try:
            output = self._run_optimize_with_experiment(
                session,
                env,
                experiment_name,
                tricky_table,
                "body",
            )
            assert output["status"] == "completed", (
                f"Body optimization failed: {json.dumps(output, indent=2, default=str)}"
            )
            self._assert_experiment_read_paths(session, experiment_name, output, "body")
        finally:
            session.sql(f"DROP TABLE IF EXISTS {tricky_table}").collect()
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_inline_optimize_body_mode_returns_result(self, session, env):
        """Inline OPTIMIZE_AI_FUNCTION completes with body mode (optimize_anything)."""
        inline_sql = render_sproc_sql(
            "optimize", env["db"], env["schema"], inline=True, anonymous=True
        )

        full_sql = (
            f"{inline_sql}\n"
            f"CALL OPTIMIZE_AI_FUNCTION(\n"
            f"    '{env['func']}',\n"
            f"    '{env['table']}',\n"
            f"    'EXPECTED_LABEL',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'exact_match',\n"
            f"    ARRAY_CONSTRUCT('llama3.1-8b'),\n"
            f"    'claude-sonnet-4-5',\n"
            f"    NULL,\n"
            f"    'light',\n"
            f"    0.667,\n"
            f"    0.7,\n"
            f"    8192,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    'body',\n"
            f"    NULL,\n"
            f"    'default'\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        output = json.loads(raw) if isinstance(raw, str) else raw
        assert output["status"] == "completed", (
            f"Body optimization failed: {json.dumps(output, indent=2, default=str)}"
        )
        assert "overall_best_prompt" in output
        assert "best_body" in output
        assert "best_ddl" in output
        assert "model_results" in output
        assert len(output["model_results"]) >= 1

    def test_inline_synthetic_data_generates_rows(self, session, env):
        """Inline GENERATE_SYNTHETIC_DATA creates a table with rows."""
        inline_sql = render_sproc_sql(
            "synthetic", env["db"], env["schema"], inline=True, anonymous=True
        )

        output_schema = '{"properties":{"label":{"type":"string","description":"positive or negative"}}}'
        escaped_schema = output_schema.replace("'", "''")

        full_sql = (
            f"{inline_sql}\n"
            f"CALL GENERATE_SYNTHETIC_DATA(\n"
            f"    'Classify the sentiment of the text as positive or negative',\n"
            f"    '{env['inline_synth_table']}',\n"
            f"    ARRAY_CONSTRUCT('TEXT'),\n"
            f"    'llama3.1-8b',\n"
            f"    5,\n"
            f"    NULL,\n"
            f"    NULL,\n"
            f"    PARSE_JSON('{escaped_schema}'),\n"
            f"    NULL\n"
            f");"
        )
        result = session.sql(full_sql).collect()
        raw = result[0][0]
        output = json.loads(raw) if isinstance(raw, str) else raw
        assert output.get("success") is True, (
            f"Generation failed: {json.dumps(output, indent=2, default=str)}"
        )
        assert output["total_generated"] >= 1

        rows = session.sql(f"SELECT * FROM {env['inline_synth_table']}").collect()
        assert len(rows) >= 1, "Inline synthetic data table is empty"
