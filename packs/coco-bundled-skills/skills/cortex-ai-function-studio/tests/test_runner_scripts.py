# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for the unified runner (run.py).

Tests the SQL builder functions, nullable CLI type converters, and SQL
formatting helpers used by the anonymous SPROC runner.
"""

import argparse

import pytest
from run import (
    _eval_build_call,
    _opt_build_call,
    _sql_array,
    _sql_int,
    _sql_varchar,
    _sql_variant_json,
    _synth_build_call,
    eval_build_async_sql,
    eval_build_sync_sql,
    nullable_int,
    nullable_str,
    opt_build_async_sql,
    opt_build_sync_sql,
    synth_build_sync_sql,
)

# ---------------------------------------------------------------------------
# Nullable CLI type converters
# ---------------------------------------------------------------------------


class TestNullableTypes:
    def test_nullable_str_none(self):
        assert nullable_str("none") is None

    def test_nullable_str_null(self):
        assert nullable_str("null") is None

    def test_nullable_str_case_insensitive(self):
        assert nullable_str("None") is None
        assert nullable_str("NONE") is None
        assert nullable_str("NULL") is None

    def test_nullable_str_value(self):
        assert nullable_str("DB.PUBLIC.TABLE") == "DB.PUBLIC.TABLE"

    def test_nullable_int_none(self):
        assert nullable_int("none") is None

    def test_nullable_int_value(self):
        assert nullable_int("100") == 100

    def test_nullable_int_invalid_raises(self):
        with pytest.raises(ValueError):
            nullable_int("abc")


# ---------------------------------------------------------------------------
# SQL formatting helpers
# ---------------------------------------------------------------------------


class TestSqlFormatters:
    def test_sql_varchar_value(self):
        assert _sql_varchar("hello") == "'hello'"

    def test_sql_varchar_none(self):
        assert _sql_varchar(None) == "NULL"

    def test_sql_varchar_escapes_quotes(self):
        assert _sql_varchar("it's") == "'it''s'"

    def test_sql_array(self):
        assert _sql_array(["A", "B"]) == "ARRAY_CONSTRUCT('A', 'B')"

    def test_sql_int_value(self):
        assert _sql_int(42) == "42"

    def test_sql_int_none(self):
        assert _sql_int(None) == "NULL"

    def test_sql_variant_json_none(self):
        assert _sql_variant_json(None) == "NULL"

    def test_sql_variant_json_value(self):
        result = _sql_variant_json('{"threshold": 0.9}')
        assert result == "PARSE_JSON('{\"threshold\": 0.9}')"


# ---------------------------------------------------------------------------
# evaluate SQL builders
# ---------------------------------------------------------------------------


class TestRunEvaluateSqlBuilder:
    @pytest.fixture
    def eval_args(self):
        return argparse.Namespace(
            database="DB",
            schema="PUBLIC",
            stage="AI_FUNCTIONS",
            connection="CONN",
            function_name="DB.PUBLIC.MY_FUNC",
            test_table="DB.PUBLIC.TEST",
            input_columns=["COL_A", "COL_B"],
            label_column="LABEL",
            metric_name="exact_match",
            model_name="claude-sonnet-4-5",
            sample_size=None,
            experiment_name=None,
            metric_options=None,
            max_length=500,
            custom_metric_udf=None,
            run_id=None,
            inline=True,
            async_mode=False,
            warehouse=None,
            timeout_minutes=240,
        )

    def test_build_call_contains_function_name(self, eval_args):
        sql = _eval_build_call(eval_args)
        assert "CALL EVALUATE_AI_FUNCTION(" in sql
        assert "'DB.PUBLIC.MY_FUNC'" in sql

    def test_build_call_formats_array(self, eval_args):
        sql = _eval_build_call(eval_args)
        assert "ARRAY_CONSTRUCT('COL_A', 'COL_B')" in sql

    def test_build_call_null_defaults(self, eval_args):
        sql = _eval_build_call(eval_args)
        assert sql.count("NULL") >= 3

    def test_build_sync_sql_has_with_and_call(self, eval_args):
        sql = eval_build_sync_sql(eval_args)
        assert "WITH EVALUATE_AI_FUNCTION AS PROCEDURE" in sql
        assert "CALL EVALUATE_AI_FUNCTION(" in sql
        assert sql.rstrip().endswith(";")

    def test_build_async_sql_creates_task(self, eval_args):
        eval_args.async_mode = True
        eval_args.warehouse = "WH"
        eval_args.run_id = None
        create, execute, run_id = eval_build_async_sql(eval_args)
        assert "CREATE TASK" in create
        assert "EXECUTE TASK" in execute
        assert run_id.startswith("ai_func_eval_MY_FUNC_")
        assert "USER_TASK_TIMEOUT_MS" in create


# ---------------------------------------------------------------------------
# optimize SQL builders
# ---------------------------------------------------------------------------


class TestRunOptimizeSqlBuilder:
    @pytest.fixture
    def opt_args(self):
        return argparse.Namespace(
            database="DB",
            schema="PUBLIC",
            stage="AI_FUNCTIONS",
            connection="CONN",
            function_name="DB.PUBLIC.MY_FUNC",
            training_table="DB.PUBLIC.TRAIN",
            label_column="LABEL",
            input_columns=["COL_A"],
            metric_name="exact_match",
            models=["claude-sonnet-4-5", "claude-haiku-4-5"],
            reflection_model="claude-sonnet-4-6",
            test_table=None,
            auto_budget="light",
            validation_fraction=0.5,
            temperature=0.7,
            max_tokens=8192,
            metric_options=None,
            custom_metric_udf=None,
            run_id=None,
            experiment_name=None,
            aggregation_metric=None,
            optimize_mode="body",
            engine="default",
            inline=True,
            async_mode=False,
            warehouse=None,
            timeout_minutes=240,
        )

    def test_build_call_contains_function_name(self, opt_args):
        sql = _opt_build_call(opt_args)
        assert "CALL OPTIMIZE_AI_FUNCTION(" in sql
        assert "'DB.PUBLIC.MY_FUNC'" in sql

    def test_build_call_formats_models_array(self, opt_args):
        sql = _opt_build_call(opt_args)
        assert "ARRAY_CONSTRUCT('claude-sonnet-4-5', 'claude-haiku-4-5')" in sql

    def test_build_sync_sql_has_with_and_call(self, opt_args):
        sql = opt_build_sync_sql(opt_args)
        assert "WITH OPTIMIZE_AI_FUNCTION AS PROCEDURE" in sql
        assert "CALL OPTIMIZE_AI_FUNCTION(" in sql

    def test_build_async_sql_creates_task(self, opt_args):
        opt_args.async_mode = True
        opt_args.warehouse = "WH"
        create, execute, run_id = opt_build_async_sql(opt_args)
        assert "CREATE TASK" in create
        assert "EXECUTE TASK" in execute
        assert run_id.startswith("ai_func_opt_MY_FUNC_")
        assert "USER_TASK_TIMEOUT_MS" in create

    def test_build_call_with_optional_params(self, opt_args):
        opt_args.experiment_name = "GEPA_OPT_TEST"
        opt_args.aggregation_metric = "f1-score"
        opt_args.engine = "semantic_sampling"
        sql = _opt_build_call(opt_args)
        assert "'GEPA_OPT_TEST'" in sql
        assert "'f1-score'" in sql
        assert "'semantic_sampling'" in sql


# ---------------------------------------------------------------------------
# synthetic SQL builders
# ---------------------------------------------------------------------------


class TestRunSyntheticDataSqlBuilder:
    @pytest.fixture
    def synth_args(self):
        return argparse.Namespace(
            database="DB",
            schema="PUBLIC",
            stage="AI_FUNCTIONS",
            connection="CONN",
            task_description="Classify customer tickets",
            output_table="DB.PUBLIC.SYNTHETIC_DATA",
            input_columns=["TEXT"],
            model="claude-opus-4-6",
            num_examples=50,
            source_table=None,
            function_name="DB.PUBLIC.MY_FUNC",
            output_schema=None,
            max_source_rows=None,
            inline=True,
        )

    def test_build_call_contains_procedure_name(self, synth_args):
        sql = _synth_build_call(synth_args)
        assert "CALL GENERATE_SYNTHETIC_DATA(" in sql

    def test_build_call_contains_task_description(self, synth_args):
        sql = _synth_build_call(synth_args)
        assert "'Classify customer tickets'" in sql

    def test_build_call_formats_input_columns_array(self, synth_args):
        synth_args.input_columns = ["CLAIM", "DOCUMENTS"]
        sql = _synth_build_call(synth_args)
        assert "ARRAY_CONSTRUCT('CLAIM', 'DOCUMENTS')" in sql

    def test_build_call_null_optional_params(self, synth_args):
        sql = _synth_build_call(synth_args)
        assert sql.count("NULL") >= 2

    def test_build_call_includes_num_examples(self, synth_args):
        sql = _synth_build_call(synth_args)
        assert "50" in sql

    def test_build_sync_sql_has_with_and_call(self, synth_args):
        sql = synth_build_sync_sql(synth_args)
        assert "WITH GENERATE_SYNTHETIC_DATA AS PROCEDURE" in sql
        assert "CALL GENERATE_SYNTHETIC_DATA(" in sql
        assert sql.rstrip().endswith(";")

    def test_build_call_pseudo_label_mode(self, synth_args):
        synth_args.source_table = "DB.PUBLIC.INPUT_TABLE"
        synth_args.max_source_rows = 20
        synth_args.model = None
        sql = _synth_build_call(synth_args)
        assert "'DB.PUBLIC.INPUT_TABLE'" in sql
        assert "20" in sql

    def test_build_call_with_output_schema(self, synth_args):
        synth_args.output_schema = '{"properties":{"LABEL":{"type":"string"}}}'
        synth_args.function_name = None
        sql = _synth_build_call(synth_args)
        assert "PARSE_JSON(" in sql
        assert "LABEL" in sql

    def test_build_call_escapes_quotes_in_description(self, synth_args):
        synth_args.task_description = "It's a classification task"
        sql = _synth_build_call(synth_args)
        assert "It''s a classification task" in sql
