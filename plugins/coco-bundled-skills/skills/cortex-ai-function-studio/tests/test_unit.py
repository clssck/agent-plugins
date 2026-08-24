# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for custom AI function creation, DDL parsing, and temp functions.

These tests run locally without a Snowflake connection.

Run:
    uv run --group test pytest tests/test_unit.py -v
"""

from __future__ import annotations

import re
from typing import ClassVar

import pytest

import snowflake_ai_optimize.core.evaluation as core_evaluation
from snowflake_ai_optimize.core.ddl_rewrite import semi_structured_param_names
from snowflake_ai_optimize.core.sproc_render import render_sproc_sql
from snowflake_ai_optimize.core.sql_utils import (
    FunctionArg,
    FunctionDefinition,
    _extract_balanced_paren_content,
    parse_signature_args,
)
from snowflake_ai_optimize.core.stage import (
    apply_file_prompt_prefix_workaround,
    extract_to_file_refs,
)
from snowflake_ai_optimize.core.temp_ai_function import TempAIFunction
from snowflake_ai_optimize.core.udf_ddl import (
    _build_create_function_ddl,
    _build_multimodal_prompt_args,
    _generate_multimodal_sql,
    _resolve_output_schema,
    generate_sql,
    parse_config,
)
from snowflake_ai_optimize.core.udf_types import (
    InputParam,
    OutputField,
    UDFSpec,
)
from snowflake_ai_optimize.gepa.optimize import (
    extract_model_from_ddl_string,
    extract_prompt_from_ddl_string,
)
from snowflake_ai_optimize.synthetic.synthetic_data import (
    _extract_input_type_map,
    _generate_batch,
    _insert_examples,
    _parse_response_format_from_body,
)

SAMPLE_SPEC = UDFSpec(
    database="DB",
    schema="SCHEMA",
    function_name="CLASSIFY",
    model="claude-sonnet-4-5",
    function_intention="Classify text sentiment",
    inputs=[InputParam(name="TEXT", sql_type="VARCHAR")],
    outputs=[
        OutputField(
            name="label", json_type="string", description="positive or negative"
        )
    ],
    system_prompt="Classify the sentiment as positive or negative.",
    user_prompt_template="{TEXT}",
)

SAMPLE_DDL = generate_sql(SAMPLE_SPEC)


def _body_of(ddl: str) -> str:
    """Return the raw body of a ``$$``-delimited CREATE FUNCTION DDL.

    Mirrors what ``DESCRIBE FUNCTION`` returns for the ``body`` property:
    the un-escaped text between the ``$$`` markers.
    """
    start = ddl.index("$$") + 2
    end = ddl.rindex("$$")
    return ddl[start:end].strip()


def _sig_of(ddl: str) -> str:
    """Return the ``(name type, ...)`` signature from a CREATE FUNCTION DDL."""
    m = re.search(r"FUNCTION\s+\S+\s*(\([^)]*\))", ddl, re.IGNORECASE | re.DOTALL)
    assert m is not None, ddl
    return m.group(1)


def _fn_of(
    ddl: str, *, name: str = "DB.SCH.F", returns: str = "VARCHAR"
) -> FunctionDefinition:
    """Build a FunctionDefinition from a ``$$`` DDL, as describe_function would."""
    sig = _sig_of(ddl)
    return FunctionDefinition(
        name=name,
        args=parse_signature_args(sig),
        returns=returns,
        language="SQL",
        body=_body_of(ddl),
        properties={"signature": sig, "returns": returns, "language": "SQL"},
    )


def _temp_fn_ddl(
    ddl: str,
    *,
    temp_function_name: str,
    candidate_model: str,
    candidate_prompt: str,
) -> str:
    """Build the inspection ``self.ddl`` a TempAIFunction produces from *ddl*.

    Replaces the retired ``TempAIFunction._build_ddl`` classmethod: constructs
    a TempAIFunction (whose ``__init__`` issues no SQL) and returns its rendered
    ``self.ddl``.
    """
    from unittest.mock import MagicMock

    inst = TempAIFunction(
        session=MagicMock(),
        function_def=_fn_of(ddl),
        temp_function_name=temp_function_name,
        candidate_model=candidate_model,
        candidate_prompt=candidate_prompt,
    )
    return inst.ddl


# ---------------------------------------------------------------------------
# 1. generate_sql — no MODEL_NAME/SYSTEM_PROMPT params
# ---------------------------------------------------------------------------


class TestGenerateSQL:
    def test_no_model_name_param(self):
        """Generated SQL must not contain MODEL_NAME as a function parameter."""
        sig_match = re.search(r"FUNCTION\s+\S+\(([^)]*)\)", SAMPLE_DDL, re.DOTALL)
        assert sig_match, "Could not find function signature"
        params = sig_match.group(1)
        assert "MODEL_NAME" not in params

    def test_no_system_prompt_param(self):
        """Generated SQL must not contain SYSTEM_PROMPT as a function parameter."""
        sig_match = re.search(r"FUNCTION\s+\S+\(([^)]*)\)", SAMPLE_DDL, re.DOTALL)
        assert sig_match, "Could not find function signature"
        params = sig_match.group(1)
        assert "SYSTEM_PROMPT" not in params

    def test_hardcodes_model(self):
        """Model must appear as a string literal model=>'claude-sonnet-4-5'."""
        assert "model=>'claude-sonnet-4-5'" in SAMPLE_DDL

    def test_hardcodes_service_model_name(self):
        """Bring your own Model SPCS services are passed through as AI_COMPLETE model strings."""  # noqa: W505
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="DB.PUBLIC.GEMMA_SERVICE",
            inputs=[InputParam(name="TEXT", sql_type="VARCHAR")],
            outputs=[],
            system_prompt="Answer briefly.",
            user_prompt_template="{TEXT}",
        )
        ddl = generate_sql(spec)
        assert "model=>'DB.PUBLIC.GEMMA_SERVICE'" in ddl

    def test_hardcodes_prompt(self):
        """System prompt must be directly embedded, no COALESCE."""
        assert "COALESCE" not in SAMPLE_DDL
        assert "Classify the sentiment as positive or negative." in SAMPLE_DDL

    def test_only_user_params(self):
        """The function signature should contain only user-defined input params."""
        sig_match = re.search(r"FUNCTION\s+\S+\(([^)]*)\)", SAMPLE_DDL, re.DOTALL)
        assert sig_match
        params = sig_match.group(1).strip()
        assert params == "TEXT VARCHAR"

    def test_multiinput_params(self):
        """Multiple user inputs appear in order, no extra params."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[
                InputParam(name="A", sql_type="VARCHAR"),
                InputParam(name="B", sql_type="NUMBER"),
            ],
            outputs=[OutputField(name="x", json_type="string", description="")],
            system_prompt="p",
            user_prompt_template="{A} {B}",
        )
        sql = generate_sql(spec)
        sig_match = re.search(r"FUNCTION\s+\S+\(([^)]*)\)", sql, re.DOTALL)
        assert sig_match
        params = sig_match.group(1).strip()
        assert params == "A VARCHAR, B NUMBER"

    def test_prompt_with_single_quotes(self):
        """Single quotes in the prompt must be SQL-escaped (doubled)."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam(name="X", sql_type="VARCHAR")],
            outputs=[OutputField(name="y", json_type="string", description="")],
            system_prompt="It's a test's prompt",
            user_prompt_template="{X}",
        )
        sql = generate_sql(spec)
        assert "It''s a test''s prompt" in sql


# ---------------------------------------------------------------------------
# 2. Text-only DDL generation and config parsing
# ---------------------------------------------------------------------------


class TestTextOnlySingleOutput:
    """Single output text-only UDF should return the extracted field."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="SENTIMENT",
        model="claude-sonnet-4-5",
        function_intention="Detect sentiment",
        inputs=[InputParam("TEXT_INPUT", "VARCHAR")],
        outputs=[OutputField("sentiment", "string", "The detected sentiment")],
        system_prompt="You are a sentiment analysis engine.",
        user_prompt_template="Analyze the sentiment: {TEXT_INPUT}",
    )

    def test_uses_messages_array(self):
        sql = generate_sql(self.SPEC)
        assert "messages=>ARRAY_CONSTRUCT" in sql

    def test_uses_response_format(self):
        sql = generate_sql(self.SPEC)
        assert "response_format=>" in sql

    def test_returns_scalar_type(self):
        sql = generate_sql(self.SPEC)
        assert "RETURNS VARCHAR" in sql

    def test_extracts_field(self):
        sql = generate_sql(self.SPEC)
        assert ":sentiment::VARCHAR" in sql

    def test_no_to_file(self):
        sql = generate_sql(self.SPEC)
        assert "TO_FILE" not in sql

    def test_no_prompt_function(self):
        sql = generate_sql(self.SPEC)
        assert "PROMPT(" not in sql

    def test_not_multimodal(self):
        assert not self.SPEC.is_multimodal


class TestTextOnlyMultiOutput:
    """Multiple output text-only UDF should return VARIANT."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="ANALYZE",
        model="claude-sonnet-4-5",
        function_intention="Analyze text",
        inputs=[InputParam("TEXT", "VARCHAR")],
        outputs=[
            OutputField("sentiment", "string", "Sentiment label"),
            OutputField("confidence", "number", "Confidence score"),
        ],
        system_prompt="Analyze.",
        user_prompt_template="{TEXT}",
    )

    def test_returns_variant(self):
        sql = generate_sql(self.SPEC)
        assert "RETURNS VARIANT" in sql

    def test_no_field_accessor(self):
        """Multi-output should NOT have a :field::TYPE accessor."""
        sql = generate_sql(self.SPEC)
        assert ":sentiment::" not in sql


class TestTextOnlyNonVarcharInput:
    """Non-VARCHAR inputs should be cast appropriately."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="SCORE",
        model="claude-sonnet-4-5",
        function_intention="Score items",
        inputs=[
            InputParam("LABEL", "VARCHAR"),
            InputParam("VALUE", "NUMBER"),
        ],
        outputs=[OutputField("score", "number", "Score")],
        system_prompt="Score.",
        user_prompt_template="Label: {LABEL}\nValue: {VALUE}",
    )

    def test_number_input_cast(self):
        sql = generate_sql(self.SPEC)
        assert "TO_VARCHAR(VALUE)" in sql

    def test_varchar_input_no_cast(self):
        sql = generate_sql(self.SPEC)
        assert "TO_VARCHAR(LABEL)" not in sql


class TestParseConfigTextOnly:
    """parse_config for standard text-only configs."""

    BASE_CONFIG: ClassVar[dict] = {
        "database": "my_db",
        "schema": "my_schema",
        "function_name": "my_func",
        "model": "claude-sonnet-4-5",
        "inputs": [{"name": "text", "sql_type": "VARCHAR"}],
        "outputs": [{"name": "result", "json_type": "string", "description": "out"}],
        "system_prompt": "sys",
        "user_prompt_template": "Analyze: {text}",
    }

    def test_uppercases_identifiers(self):
        spec = parse_config(self.BASE_CONFIG)
        assert spec.database == "MY_DB"
        assert spec.schema == "MY_SCHEMA"
        assert spec.function_name == "MY_FUNC"
        assert spec.inputs[0].name == "TEXT"

    def test_not_multimodal(self):
        spec = parse_config(self.BASE_CONFIG)
        assert not spec.is_multimodal
        assert spec.stage_name is None

    def test_missing_model_rejected(self):
        config = {k: v for k, v in self.BASE_CONFIG.items() if k != "model"}
        with pytest.raises(ValueError, match="Missing required fields"):
            parse_config(config)

    def test_missing_sql_type_rejected(self):
        config = {
            **self.BASE_CONFIG,
            "inputs": [{"name": "text"}],
        }
        with pytest.raises(ValueError, match="sql_type"):
            parse_config(config)

    def test_missing_required_field(self):
        config = {k: v for k, v in self.BASE_CONFIG.items() if k != "system_prompt"}
        with pytest.raises(ValueError, match="Missing required fields"):
            parse_config(config)

    def test_empty_inputs_rejected(self):
        config = {**self.BASE_CONFIG, "inputs": []}
        with pytest.raises(ValueError, match="At least one input"):
            parse_config(config)

    def test_empty_outputs_rejected(self):
        config = {**self.BASE_CONFIG, "outputs": []}
        with pytest.raises(ValueError, match="At least one output"):
            parse_config(config)

    def test_input_missing_name_rejected(self):
        config = {**self.BASE_CONFIG, "inputs": [{"sql_type": "VARCHAR"}]}
        with pytest.raises(ValueError, match="name"):
            parse_config(config)


class TestRoutingTextVsMultimodal:
    """generate_sql routes to the correct path based on is_multimodal."""

    TEXT_SPEC = UDFSpec(
        database="D",
        schema="S",
        function_name="F",
        model="m",
        inputs=[InputParam("X", "VARCHAR")],
        outputs=[OutputField("o", "string", "d")],
        system_prompt="s",
        user_prompt_template="{X}",
    )
    MM_SPEC = UDFSpec(
        database="D",
        schema="S",
        function_name="F",
        model="m",
        inputs=[InputParam("X", "VARCHAR", is_file_path=True)],
        outputs=[OutputField("o", "string", "d")],
        system_prompt="s",
        user_prompt_template="analyze",
        stage_name="@D.S.ST",
    )

    def test_text_uses_messages(self):
        sql = generate_sql(self.TEXT_SPEC)
        assert "messages=>ARRAY_CONSTRUCT" in sql

    def test_multimodal_uses_to_file(self):
        sql = generate_sql(self.MM_SPEC)
        assert "TO_FILE" in sql

    def test_text_no_to_file(self):
        sql = generate_sql(self.TEXT_SPEC)
        assert "TO_FILE" not in sql

    def test_both_use_messages(self):
        """Both text-only and multimodal should use messages array."""
        text_sql = generate_sql(self.TEXT_SPEC)
        mm_sql = generate_sql(self.MM_SPEC)
        assert "messages=>ARRAY_CONSTRUCT" in text_sql
        assert "messages=>ARRAY_CONSTRUCT" in mm_sql

    def test_both_use_response_format(self):
        """Both text-only and multimodal should use response_format."""
        text_sql = generate_sql(self.TEXT_SPEC)
        mm_sql = generate_sql(self.MM_SPEC)
        assert "response_format=>" in text_sql
        assert "response_format=>" in mm_sql


# ---------------------------------------------------------------------------
# 3. Multimodal DDL generation
# ---------------------------------------------------------------------------


class TestMultimodalSingleFileWithOutputs:
    """Single file input with outputs should use PROMPT() + response_format."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="CLASSIFY_IMAGE",
        model="claude-sonnet-4-5",
        function_intention="Classify images",
        inputs=[InputParam("FILE_PATH", "VARCHAR", is_file_path=True)],
        outputs=[OutputField("category", "string", "Image category")],
        system_prompt="You are an image classifier.",
        user_prompt_template="Classify this image.",
        stage_name="@DB.SCH.AI_FUNCTIONS",
    )

    def test_uses_to_file(self):
        sql = generate_sql(self.SPEC)
        assert "TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)" in sql

    def test_uses_prompt_function(self):
        sql = generate_sql(self.SPEC)
        assert "PROMPT(" in sql

    def test_uses_response_format(self):
        sql = generate_sql(self.SPEC)
        assert "response_format=>" in sql
        assert '"category"' in sql

    def test_uses_messages_array(self):
        sql = generate_sql(self.SPEC)
        assert "messages=>ARRAY_CONSTRUCT" in sql

    def test_no_json_in_prompt_text(self):
        """JSON schema should be in response_format, not in the prompt text."""
        sql = generate_sql(self.SPEC)
        assert "Respond in JSON" not in sql

    def test_casts_to_varchar(self):
        sql = generate_sql(self.SPEC)
        assert "::VARCHAR" in sql

    def test_returns_varchar(self):
        sql = generate_sql(self.SPEC)
        assert "RETURNS VARCHAR" in sql

    def test_system_prompt_in_system_role(self):
        """System prompt should be in a separate system message, not embedded in PROMPT()."""  # noqa: W505
        sql = generate_sql(self.SPEC)
        assert "'role', 'system'" in sql
        assert "You are an image classifier." in sql


class TestApplyFilePromptPrefixWorkaround:
    def test_returns_original_when_first_arg_is_not_file(self):
        template = "{0} summarize this image."
        assert (
            apply_file_prompt_prefix_workaround(
                template,
                first_prompt_arg_is_file=False,
            )
            == template
        )

    def test_prefixes_file_first_template(self):
        assert (
            apply_file_prompt_prefix_workaround(
                "{0} {1}",
                first_prompt_arg_is_file=True,
            )
            == "file: {0} {1}"
        )

    def test_preserves_leading_whitespace_when_prefixing(self):
        assert (
            apply_file_prompt_prefix_workaround(
                "   {0} summarize this image.",
                first_prompt_arg_is_file=True,
            )
            == "   file: {0} summarize this image."
        )

    def test_does_not_double_prefix_existing_file_prefix(self):
        template = "  FILE: {0} summarize this image."
        assert (
            apply_file_prompt_prefix_workaround(
                template,
                first_prompt_arg_is_file=True,
            )
            == template
        )

    def test_does_not_prefix_when_placeholder_is_not_first_token(self):
        template = "Summarize {0} carefully."
        assert (
            apply_file_prompt_prefix_workaround(
                template,
                first_prompt_arg_is_file=True,
            )
            == template
        )


class TestMultimodalPromptPrefixModelAgnostic:
    """Temporary AI_COMPLETE workaround: file-first prompts get `file: {0}`."""

    MODELS: ClassVar[list[str]] = [
        "claude-sonnet-4-5",
        "gemini-2.5-flash",
        "llama4-scout",
        "mistral-large2",
    ]

    @pytest.mark.parametrize("model", MODELS)
    def test_file_prompt_template_prefixed_for_all_models(self, model):
        spec = UDFSpec(
            database="DB",
            schema="SCH",
            function_name="CLASSIFY_IMAGE",
            model=model,
            function_intention="Classify images",
            inputs=[InputParam("FILE_PATH", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("category", "string", "Image category")],
            system_prompt="You are an image classifier.",
            user_prompt_template="{FILE_PATH}",
            stage_name="@DB.SCH.AI_FUNCTIONS",
        )
        sql = _generate_multimodal_sql(spec)
        assert f"model=>'{model}'" in sql
        assert re.search(
            r"PROMPT\(\s*'file: \{0\}'\s*,\s*TO_FILE\('@DB\.SCH\.AI_FUNCTIONS', FILE_PATH\)",
            sql,
        )

    @pytest.mark.parametrize("model", MODELS)
    def test_no_placeholder_file_prompt_template_prefixed_for_all_models(self, model):
        spec = UDFSpec(
            database="DB",
            schema="SCH",
            function_name="CLASSIFY_IMAGE",
            model=model,
            function_intention="Classify images",
            inputs=[InputParam("FILE_PATH", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("category", "string", "Image category")],
            system_prompt="You are an image classifier.",
            user_prompt_template="Describe this filing image.",
            stage_name="@DB.SCH.AI_FUNCTIONS",
        )
        sql = _generate_multimodal_sql(spec)
        assert re.search(
            r"PROMPT\(\s*'file: \{0\} Describe this filing image\.'\s*,\s*TO_FILE\('@DB\.SCH\.AI_FUNCTIONS', FILE_PATH\)",
            sql,
        )

    @pytest.mark.parametrize("model", MODELS)
    def test_existing_file_prefix_is_not_duplicated(self, model):
        spec = UDFSpec(
            database="DB",
            schema="SCH",
            function_name="CLASSIFY_IMAGE",
            model=model,
            function_intention="Classify images",
            inputs=[InputParam("FILE_PATH", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("category", "string", "Image category")],
            system_prompt="You are an image classifier.",
            user_prompt_template="file: {FILE_PATH}",
            stage_name="@DB.SCH.AI_FUNCTIONS",
        )
        sql = _generate_multimodal_sql(spec)
        assert "file: file:" not in sql.lower()
        assert sql.count("file: {0}") == 1

    @pytest.mark.parametrize("model", MODELS)
    def test_file_and_text_prompt_template_prefixed_when_file_is_first(self, model):
        spec = UDFSpec(
            database="DB",
            schema="SCH",
            function_name="ANALYZE_IMAGE",
            model=model,
            function_intention="Analyze filing image",
            inputs=[
                InputParam("FILE_PATH", "VARCHAR", is_file_path=True),
                InputParam("QUESTION", "VARCHAR"),
            ],
            outputs=[OutputField("answer", "string", "The answer")],
            system_prompt="You are a visual analyst.",
            user_prompt_template="{FILE_PATH} {QUESTION}",
            stage_name="@DB.SCH.AI_FUNCTIONS",
        )
        sql = _generate_multimodal_sql(spec)
        assert re.search(
            r"PROMPT\(\s*'file: \{0\} \{1\}'\s*,\s*TO_FILE\('@DB\.SCH\.AI_FUNCTIONS', FILE_PATH\)\s*,\s*QUESTION",
            sql,
        )

    @pytest.mark.parametrize("model", MODELS)
    def test_no_placeholder_file_and_text_prompt_prefixed_when_file_is_first(
        self, model
    ):
        spec = UDFSpec(
            database="DB",
            schema="SCH",
            function_name="ANALYZE_IMAGE",
            model=model,
            function_intention="Analyze filing image",
            inputs=[
                InputParam("FILE_PATH", "VARCHAR", is_file_path=True),
                InputParam("QUESTION", "VARCHAR"),
            ],
            outputs=[OutputField("answer", "string", "The answer")],
            system_prompt="You are a visual analyst.",
            user_prompt_template="Analyze this filing image.",
            stage_name="@DB.SCH.AI_FUNCTIONS",
        )
        sql = _generate_multimodal_sql(spec)
        assert re.search(
            r"PROMPT\(\s*'file: \{0\} \{1\} Analyze this filing image\.'\s*,\s*TO_FILE\('@DB\.SCH\.AI_FUNCTIONS', FILE_PATH\)\s*,\s*QUESTION",
            sql,
        )

    @pytest.mark.parametrize("model", MODELS)
    def test_no_placeholder_prefix_not_forced_when_text_is_first_prompt_arg(
        self, model
    ):
        spec = UDFSpec(
            database="DB",
            schema="SCH",
            function_name="ANALYZE_IMAGE",
            model=model,
            function_intention="Analyze filing image",
            inputs=[
                InputParam("QUESTION", "VARCHAR"),
                InputParam("FILE_PATH", "VARCHAR", is_file_path=True),
            ],
            outputs=[OutputField("answer", "string", "The answer")],
            system_prompt="You are a visual analyst.",
            user_prompt_template="Analyze this filing image.",
            stage_name="@DB.SCH.AI_FUNCTIONS",
        )
        sql = _generate_multimodal_sql(spec)
        assert not re.search(r"PROMPT\(\s*'file:", sql)
        assert re.search(
            r"PROMPT\(\s*'\{0\} \{1\} Analyze this filing image\.'\s*,\s*QUESTION\s*,\s*TO_FILE\('@DB\.SCH\.AI_FUNCTIONS', FILE_PATH\)",
            sql,
        )

    @pytest.mark.parametrize("model", MODELS)
    def test_file_prefix_not_forced_when_text_is_first_prompt_arg(self, model):
        spec = UDFSpec(
            database="DB",
            schema="SCH",
            function_name="ANALYZE_IMAGE",
            model=model,
            function_intention="Analyze filing image",
            inputs=[
                InputParam("QUESTION", "VARCHAR"),
                InputParam("FILE_PATH", "VARCHAR", is_file_path=True),
            ],
            outputs=[OutputField("answer", "string", "The answer")],
            system_prompt="You are a visual analyst.",
            user_prompt_template="{QUESTION} {FILE_PATH}",
            stage_name="@DB.SCH.AI_FUNCTIONS",
        )
        sql = _generate_multimodal_sql(spec)
        assert not re.search(r"PROMPT\(\s*'file:\s*\{0\}'", sql)
        assert re.search(
            r"PROMPT\(\s*'\{0\} \{1\}'\s*,",
            sql,
        )
        assert "TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)" in sql


class TestMultimodalSingleFileNoOutputs:
    """Single file input without outputs should still use PROMPT() but no response_format."""  # noqa: W505

    SPEC_NO_OUTPUTS = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="DESCRIBE_IMAGE",
        model="claude-sonnet-4-5",
        function_intention="Describe images",
        inputs=[InputParam("FILE_PATH", "VARCHAR", is_file_path=True)],
        outputs=[],
        system_prompt="",
        user_prompt_template="Describe this image.",
        stage_name="@DB.SCH.AI_FUNCTIONS",
    )

    def test_uses_prompt_function(self):
        sql = _generate_multimodal_sql(self.SPEC_NO_OUTPUTS)
        assert "PROMPT(" in sql

    def test_no_response_format(self):
        sql = _generate_multimodal_sql(self.SPEC_NO_OUTPUTS)
        assert "response_format" not in sql

    def test_uses_to_file(self):
        sql = _generate_multimodal_sql(self.SPEC_NO_OUTPUTS)
        assert "TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)" in sql

    def test_casts_to_varchar(self):
        sql = _generate_multimodal_sql(self.SPEC_NO_OUTPUTS)
        assert "::VARCHAR" in sql

    def test_uses_messages_array(self):
        sql = _generate_multimodal_sql(self.SPEC_NO_OUTPUTS)
        assert "messages=>ARRAY_CONSTRUCT" in sql


class TestMultimodalFileAndText:
    """File + text input should use PROMPT() + response_format."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="ANALYZE_IMAGE",
        model="claude-sonnet-4-5",
        function_intention="Analyze images with questions",
        inputs=[
            InputParam("IMG_PATH", "VARCHAR", is_file_path=True),
            InputParam("QUESTION", "VARCHAR"),
        ],
        outputs=[OutputField("answer", "string", "The answer")],
        system_prompt="You are a visual analyst.",
        user_prompt_template="Analyze this image: {IMG_PATH}\nQuestion: {QUESTION}",
        stage_name="@DB.SCH.AI_FUNCTIONS",
    )

    def test_uses_prompt_function(self):
        sql = generate_sql(self.SPEC)
        assert "PROMPT(" in sql

    def test_uses_to_file(self):
        sql = generate_sql(self.SPEC)
        assert "TO_FILE('@DB.SCH.AI_FUNCTIONS', IMG_PATH)" in sql

    def test_uses_response_format(self):
        sql = generate_sql(self.SPEC)
        assert "response_format=>" in sql
        assert '"answer"' in sql

    def test_uses_messages_array(self):
        sql = generate_sql(self.SPEC)
        assert "messages=>ARRAY_CONSTRUCT" in sql

    def test_casts_to_varchar(self):
        sql = generate_sql(self.SPEC)
        assert "::VARCHAR" in sql

    def test_positional_placeholders(self):
        sql = generate_sql(self.SPEC)
        assert "{0}" in sql
        assert "{1}" in sql


class TestMultimodalMultipleFiles:
    """Multiple file inputs should use PROMPT() + response_format."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="COMPARE_IMAGES",
        model="claude-sonnet-4-5",
        function_intention="Compare two images",
        inputs=[
            InputParam("IMG1", "VARCHAR", is_file_path=True),
            InputParam("IMG2", "VARCHAR", is_file_path=True),
        ],
        outputs=[OutputField("comparison", "string", "Comparison result")],
        system_prompt="",
        user_prompt_template="Compare image {IMG1} and image {IMG2}.",
        stage_name="@DB.SCH.AI_FUNCTIONS",
    )

    def test_both_to_file_args(self):
        sql = generate_sql(self.SPEC)
        assert "TO_FILE('@DB.SCH.AI_FUNCTIONS', IMG1)" in sql
        assert "TO_FILE('@DB.SCH.AI_FUNCTIONS', IMG2)" in sql

    def test_uses_prompt_function(self):
        sql = generate_sql(self.SPEC)
        assert "PROMPT(" in sql

    def test_uses_response_format(self):
        sql = generate_sql(self.SPEC)
        assert "response_format=>" in sql
        assert '"comparison"' in sql

    def test_uses_messages_array(self):
        sql = generate_sql(self.SPEC)
        assert "messages=>ARRAY_CONSTRUCT" in sql


class TestMultimodalResponseFormatAndPromptArgs:
    """System prompt should be a PROMPT arg; JSON schema in response_format."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="CLASSIFY_DOC",
        model="claude-sonnet-4-5",
        function_intention="Classify documents",
        inputs=[
            InputParam("DOC_PATH", "VARCHAR", is_file_path=True),
            InputParam("HINT", "VARCHAR"),
        ],
        outputs=[
            OutputField("category", "string", "Document category"),
            OutputField("confidence", "number", "Confidence score"),
        ],
        system_prompt="You are a document classifier.",
        user_prompt_template="Classify: {DOC_PATH}\nHint: {HINT}",
        stage_name="@DB.SCH.AI_FUNCTIONS",
    )

    def test_json_schema_not_in_template(self):
        """JSON schema braces must not appear in the PROMPT template string."""
        sql = generate_sql(self.SPEC)
        prompt_match = re.search(r"PROMPT\(\s*'([^']*(?:''[^']*)*)'", sql)
        assert prompt_match, "Should contain PROMPT() call"
        template_str = prompt_match.group(1)
        assert '"type"' not in template_str

    def test_template_only_has_positional_braces(self):
        """PROMPT template must only contain {N} placeholders, no literal braces."""
        sql = generate_sql(self.SPEC)
        prompt_match = re.search(r"PROMPT\(\s*'([^']*(?:''[^']*)*)'", sql)
        assert prompt_match
        template_str = prompt_match.group(1)
        non_placeholder = re.findall(r"\{(?!\d+\})", template_str)
        assert not non_placeholder, f"Literal braces in template: {non_placeholder}"

    def test_json_schema_in_response_format(self):
        """JSON schema should be in response_format, not in prompt text."""
        sql = generate_sql(self.SPEC)
        assert "response_format=>" in sql
        assert '"category"' in sql
        assert "Respond in JSON" not in sql

    def test_system_prompt_still_in_sql(self):
        """System prompt should appear somewhere in the SQL (as a PROMPT arg value)."""
        sql = generate_sql(self.SPEC)
        assert "You are a document classifier." in sql

    def test_positional_indices_contiguous(self):
        """All positional indices {0}..{N} must be present with no gaps."""
        sql = generate_sql(self.SPEC)
        prompt_match = re.search(r"PROMPT\(\s*'([^']*(?:''[^']*)*)'", sql)
        assert prompt_match
        template_str = prompt_match.group(1)
        indices = sorted(int(m) for m in re.findall(r"\{(\d+)\}", template_str))
        assert indices == list(range(len(indices)))


class TestParseConfigMultimodal:
    """parse_config validation for multimodal configs."""

    BASE_CONFIG: ClassVar[dict] = {
        "database": "DB",
        "schema": "SCH",
        "function_name": "FUNC",
        "model": "claude-sonnet-4-5",
        "inputs": [
            {"name": "FILE_PATH", "sql_type": "VARCHAR", "is_file_path": True},
            {"name": "QUESTION", "sql_type": "VARCHAR"},
        ],
        "outputs": [{"name": "answer", "json_type": "string", "description": "ans"}],
        "system_prompt": "Helper.",
        "user_prompt_template": "Analyze: {FILE_PATH}\nQ: {QUESTION}",
    }

    def test_rejects_missing_stage_name(self):
        with pytest.raises(ValueError, match="stage_name"):
            parse_config(self.BASE_CONFIG)

    def test_accepts_with_stage_name(self):
        config = {**self.BASE_CONFIG, "stage_name": "@DB.SCH.AI_FUNCTIONS"}
        spec = parse_config(config)
        assert spec.is_multimodal
        assert spec.stage_name == "@DB.SCH.AI_FUNCTIONS"
        assert spec.inputs[0].is_file_path is True
        assert spec.inputs[1].is_file_path is False

    def test_text_only_config_no_stage_needed(self):
        config = {
            **self.BASE_CONFIG,
            "inputs": [{"name": "TEXT", "sql_type": "VARCHAR"}],
        }
        spec = parse_config(config)
        assert not spec.is_multimodal
        assert spec.stage_name is None


class TestBuildMultimodalPromptArgs:
    """_build_multimodal_prompt_args placeholder translation."""

    def test_basic_translation(self):
        inputs = [
            InputParam("IMG", "VARCHAR", is_file_path=True),
            InputParam("Q", "VARCHAR"),
        ]
        translated, args = _build_multimodal_prompt_args(
            "Look at {IMG} and answer {Q}", inputs, "@DB.SCH.STAGE"
        )
        assert translated == "Look at {0} and answer {1}"
        assert args[0] == "TO_FILE('@DB.SCH.STAGE', IMG)"
        assert args[1] == "Q"

    def test_multiple_files(self):
        inputs = [
            InputParam("IMG1", "VARCHAR", is_file_path=True),
            InputParam("IMG2", "VARCHAR", is_file_path=True),
        ]
        translated, args = _build_multimodal_prompt_args(
            "Compare {IMG1} vs {IMG2}", inputs, "@S"
        )
        assert translated == "Compare {0} vs {1}"
        assert "TO_FILE" in args[0] and "IMG1" in args[0]
        assert "TO_FILE" in args[1] and "IMG2" in args[1]

    def test_deduplication(self):
        """Repeated placeholder produces one arg, both occurrences use same index."""
        inputs = [InputParam("IMG", "VARCHAR", is_file_path=True)]
        translated, args = _build_multimodal_prompt_args(
            "First {IMG} then {IMG}", inputs, "@S"
        )
        assert translated == "First {0} then {0}"
        assert len(args) == 1

    def test_non_varchar_text_input_cast(self):
        """Non-VARCHAR text inputs should be cast via TO_VARCHAR."""
        inputs = [
            InputParam("IMG", "VARCHAR", is_file_path=True),
            InputParam("SCORE", "NUMBER"),
        ]
        _, args = _build_multimodal_prompt_args(
            "Image {IMG} score {SCORE}", inputs, "@S"
        )
        assert args[1] == "TO_VARCHAR(SCORE)"

    def test_unknown_placeholder_passed_through(self):
        """Placeholder not matching any input is passed through as uppercase."""
        inputs = [InputParam("IMG", "VARCHAR", is_file_path=True)]
        translated, args = _build_multimodal_prompt_args(
            "Image {IMG} extra {UNKNOWN}", inputs, "@S"
        )
        assert translated == "Image {0} extra {1}"
        assert args[1] == "UNKNOWN"

    def test_stage_name_with_single_quotes(self):
        """Single quotes in stage name are SQL-escaped."""
        inputs = [InputParam("F", "VARCHAR", is_file_path=True)]
        _, args = _build_multimodal_prompt_args("{F}", inputs, "@DB.IT'S.STAGE")
        assert "IT''S" in args[0]

    def test_array_input_cast(self):
        """ARRAY inputs should be cast via ARRAY_TO_STRING."""
        inputs = [
            InputParam("IMG", "VARCHAR", is_file_path=True),
            InputParam("TAGS", "ARRAY"),
        ]
        _, args = _build_multimodal_prompt_args("{IMG} {TAGS}", inputs, "@S")
        assert "ARRAY_TO_STRING(TAGS" in args[1]


# ---------------------------------------------------------------------------
# 4. No-placeholder fallback path in generate_multimodal_sql
# ---------------------------------------------------------------------------


class TestMultimodalNoPlaceholderFallback:
    """When template has no {PLACEHOLDER}s, all inputs are auto-referenced."""

    def test_multiple_files_no_placeholders(self):
        """Two file inputs with no placeholders should both appear as PROMPT args."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[
                InputParam("IMG1", "VARCHAR", is_file_path=True),
                InputParam("IMG2", "VARCHAR", is_file_path=True),
            ],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="Compare these images.",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "TO_FILE('@S', IMG1)" in sql
        assert "TO_FILE('@S', IMG2)" in sql
        assert "{0}" in sql
        assert "{1}" in sql

    def test_file_and_text_no_placeholders(self):
        """File + text without placeholders: both appear as PROMPT args."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[
                InputParam("IMG", "VARCHAR", is_file_path=True),
                InputParam("Q", "VARCHAR"),
            ],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="Analyze.",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "TO_FILE('@S', IMG)" in sql
        assert "{0}" in sql and "{1}" in sql

    def test_non_varchar_text_in_fallback(self):
        """Non-VARCHAR inputs in the fallback path should be cast."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[
                InputParam("IMG", "VARCHAR", is_file_path=True),
                InputParam("SCORE", "NUMBER"),
            ],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="Rate this.",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "TO_VARCHAR(SCORE)" in sql


# ---------------------------------------------------------------------------
# 5. Multimodal system prompt edge cases
# ---------------------------------------------------------------------------


class TestMultimodalSystemPromptEdgeCases:
    """System prompt handling in multimodal DDL — now uses messages array."""

    def test_empty_system_prompt_in_system_role(self):
        """Empty system prompt still appears in system role message."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="Classify: {IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "'role', 'system'" in sql
        prompt_match = re.search(r"PROMPT\(\s*'([^']*(?:''[^']*)*)'", sql)
        assert prompt_match
        template_str = prompt_match.group(1)
        indices = sorted(int(m) for m in re.findall(r"\{(\d+)\}", template_str))
        assert indices == [0]

    def test_whitespace_only_system_prompt(self):
        """Whitespace-only system prompt passed through to system role."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="   \n  ",
            user_prompt_template="Classify: {IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "'role', 'system'" in sql
        prompt_match = re.search(r"PROMPT\(\s*'([^']*(?:''[^']*)*)'", sql)
        assert prompt_match
        template_str = prompt_match.group(1)
        indices = sorted(int(m) for m in re.findall(r"\{(\d+)\}", template_str))
        assert indices == [0]

    def test_system_prompt_with_single_quotes(self):
        """Single quotes in system prompt must be SQL-escaped."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="You're a classifier. Don't hallucinate.",
            user_prompt_template="Classify: {IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "You''re a classifier. Don''t hallucinate." in sql


# ---------------------------------------------------------------------------
# 6. Multimodal SQL escaping and DDL structure
# ---------------------------------------------------------------------------


class TestMultimodalSQLEscaping:
    """SQL escaping and DDL structure for multimodal UDFs."""

    def test_stage_name_with_single_quotes(self):
        """Single quotes in stage name are properly escaped."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("F", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="Go: {F}",
            stage_name="@DB.IT'S.STAGE",
        )
        sql = _generate_multimodal_sql(spec)
        assert "IT''S" in sql

    def test_user_prompt_with_single_quotes(self):
        """Single quotes in user prompt template are SQL-escaped."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="What's in image {IMG}? It's important.",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "What''s" in sql
        assert "It''s" in sql

    def test_fqn_in_ddl(self):
        """Generated DDL should have fully qualified function name."""
        spec = UDFSpec(
            database="MY_DB",
            schema="MY_SCHEMA",
            function_name="MY_FUNC",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "MY_DB.MY_SCHEMA.MY_FUNC" in sql

    def test_comment_in_ddl(self):
        """Function intention should appear as COMMENT in DDL."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            function_intention="Classify images into categories",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert (
            "COMMENT = '[CORTEX AI FUNC STUDIO] Classify images into categories'" in sql
        )

    def test_missing_stage_name_asserts(self):
        """generate_multimodal_sql should assert when stage_name is None."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name=None,
        )
        with pytest.raises(AssertionError):
            _generate_multimodal_sql(spec)


# ---------------------------------------------------------------------------
# 7. response_format JSON schema structure
# ---------------------------------------------------------------------------


class TestMultimodalResponseFormatSchema:
    """Verify the response_format JSON schema has correct structure."""

    def test_schema_has_type_json(self):
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("label", "string", "Category label")],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert '"type": "json"' in sql
        assert '"schema"' in sql

    def test_schema_has_properties_and_required(self):
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[
                OutputField("category", "string", "Cat"),
                OutputField("score", "number", "Score"),
            ],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert '"category"' in sql
        assert '"score"' in sql
        assert '"required"' in sql
        assert '"additionalProperties": false' in sql

    def test_array_output_type(self):
        """Array output field should have items specification."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("tags", "array", "List of tags")],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert '"items"' in sql


# ---------------------------------------------------------------------------
# 8. parse_config additional edge cases
# ---------------------------------------------------------------------------


class TestParseConfigEdgeCases:
    """Additional parse_config validation."""

    BASE_CONFIG: ClassVar[dict] = {
        "database": "DB",
        "schema": "SCH",
        "function_name": "FUNC",
        "model": "claude-sonnet-4-5",
        "inputs": [{"name": "TEXT", "sql_type": "VARCHAR"}],
        "outputs": [{"name": "result", "json_type": "string", "description": "out"}],
        "system_prompt": "sys",
        "user_prompt_template": "{TEXT}",
    }

    def test_output_missing_name_rejected(self):
        config = {
            **self.BASE_CONFIG,
            "outputs": [{"json_type": "string", "description": "d"}],
        }
        with pytest.raises(ValueError, match="name"):
            parse_config(config)

    def test_multiple_file_inputs_parsed(self):
        config = {
            **self.BASE_CONFIG,
            "stage_name": "@S",
            "inputs": [
                {"name": "IMG1", "sql_type": "VARCHAR", "is_file_path": True},
                {"name": "IMG2", "sql_type": "VARCHAR", "is_file_path": True},
            ],
        }
        spec = parse_config(config)
        assert spec.is_multimodal
        assert all(inp.is_file_path for inp in spec.inputs)

    def test_missing_json_type_rejected(self):
        config = {
            **self.BASE_CONFIG,
            "outputs": [{"name": "result", "description": "out"}],
        }
        with pytest.raises(ValueError, match="json_type"):
            parse_config(config)

    def test_function_intention_defaults_to_empty(self):
        config = {
            k: v for k, v in self.BASE_CONFIG.items() if k != "function_intention"
        }
        spec = parse_config(config)
        assert spec.function_intention == ""

    def test_is_file_path_defaults_false(self):
        spec = parse_config(self.BASE_CONFIG)
        assert spec.inputs[0].is_file_path is False

    def test_mixed_file_and_text_inputs(self):
        config = {
            **self.BASE_CONFIG,
            "stage_name": "@DB.S.AI_FUNCTIONS",
            "inputs": [
                {"name": "DOC", "sql_type": "VARCHAR", "is_file_path": True},
                {"name": "QUESTION", "sql_type": "VARCHAR"},
                {"name": "PRIORITY", "sql_type": "NUMBER"},
            ],
        }
        spec = parse_config(config)
        assert spec.is_multimodal
        assert spec.inputs[0].is_file_path is True
        assert spec.inputs[1].is_file_path is False
        assert spec.inputs[2].sql_type == "NUMBER"


# ---------------------------------------------------------------------------
# 9. _resolve_output_schema helper
# ---------------------------------------------------------------------------


class TestResolveOutputSchemaNoOutputs:
    """No outputs → VARCHAR, ::VARCHAR cast, no response_format."""

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema([])
        assert return_type == "VARCHAR"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema([])
        assert result_suffix == "::VARCHAR"

    def test_no_response_format(self):
        _, _, response_format_expr = _resolve_output_schema([])
        assert response_format_expr is None


class TestResolveOutputSchemaSingleString:
    """Single string output → VARCHAR with field accessor."""

    OUTPUTS: ClassVar[list[OutputField]] = [OutputField("label", "string", "Category")]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "VARCHAR"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ":label::VARCHAR"

    def test_has_response_format(self):
        _, _, expr = _resolve_output_schema(self.OUTPUTS)
        assert expr is not None
        assert "PARSE_JSON" in expr
        assert '"label"' in expr


class TestResolveOutputSchemaSingleNumber:
    """Single number output → FLOAT with field accessor."""

    OUTPUTS: ClassVar[list[OutputField]] = [OutputField("score", "number", "Score")]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "FLOAT"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ":score::FLOAT"


class TestResolveOutputSchemaSingleInteger:
    """Single integer output → NUMBER with field accessor."""

    OUTPUTS: ClassVar[list[OutputField]] = [OutputField("count", "integer", "Count")]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "NUMBER"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ":count::NUMBER"


class TestResolveOutputSchemaSingleBoolean:
    """Single boolean output → BOOLEAN with field accessor."""

    OUTPUTS: ClassVar[list[OutputField]] = [
        OutputField("is_valid", "boolean", "Validity")
    ]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "BOOLEAN"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ":is_valid::BOOLEAN"


class TestResolveOutputSchemaSingleArray:
    """Single array output → VARIANT (mapped from array)."""

    OUTPUTS: ClassVar[list[OutputField]] = [OutputField("tags", "array", "Tags")]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "VARIANT"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ":tags::VARIANT"


class TestResolveOutputSchemaSingleObject:
    """Single object output → VARIANT (mapped from object)."""

    OUTPUTS: ClassVar[list[OutputField]] = [
        OutputField("metadata", "object", "Metadata")
    ]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "VARIANT"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ":metadata::VARIANT"


class TestResolveOutputSchemaSingleUnknownType:
    """Unknown json_type defaults to VARCHAR."""

    OUTPUTS: ClassVar[list[OutputField]] = [
        OutputField("data", "foobar", "Unknown type")
    ]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "VARCHAR"

    def test_result_suffix(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ":data::VARCHAR"


class TestResolveOutputSchemaMultiOutput:
    """Multiple outputs → VARIANT, no accessor, has response_format."""

    OUTPUTS: ClassVar[list[OutputField]] = [
        OutputField("category", "string", "Cat"),
        OutputField("confidence", "number", "Conf"),
    ]

    def test_return_type(self):
        return_type, _, _ = _resolve_output_schema(self.OUTPUTS)
        assert return_type == "VARIANT"

    def test_no_accessor(self):
        _, result_suffix, _ = _resolve_output_schema(self.OUTPUTS)
        assert result_suffix == ""

    def test_has_response_format(self):
        _, _, expr = _resolve_output_schema(self.OUTPUTS)
        assert expr is not None
        assert '"category"' in expr
        assert '"confidence"' in expr

    def test_response_format_has_json_type(self):
        _, _, expr = _resolve_output_schema(self.OUTPUTS)
        assert '"type": "json"' in expr


class TestResolveOutputSchemaResponseFormatEscaping:
    """Output field names with special chars are escaped in JSON schema."""

    OUTPUTS: ClassVar[list[OutputField]] = [
        OutputField("it's_ok", "string", "Has a quote")
    ]

    def test_single_quotes_escaped_in_expr(self):
        """PARSE_JSON wraps in single quotes, so inner quotes must be doubled."""
        _, _, expr = _resolve_output_schema(self.OUTPUTS)
        assert "it''s_ok" in expr


# ---------------------------------------------------------------------------
# 10. _build_create_function_ddl helper
# ---------------------------------------------------------------------------


class TestBuildCreateFunctionDDL:
    """Verify the DDL wrapper includes all structural elements."""

    DDL = _build_create_function_ddl(
        fqn="DB.SCH.MY_FUNC",
        input_params="X VARCHAR, Y NUMBER",
        return_type="VARIANT",
        escaped_comment="Test function",
        body_expr="AI_COMPLETE('m', 'p')",
    )

    def test_has_create_or_replace(self):
        assert "CREATE FUNCTION" in self.DDL

    def test_has_fqn(self):
        assert "DB.SCH.MY_FUNC" in self.DDL

    def test_has_params(self):
        assert "X VARCHAR, Y NUMBER" in self.DDL

    def test_has_returns(self):
        assert "RETURNS VARIANT" in self.DDL

    def test_has_language_sql(self):
        assert "LANGUAGE SQL" in self.DDL

    def test_has_comment(self):
        assert "COMMENT = '[CORTEX AI FUNC STUDIO] Test function'" in self.DDL

    def test_has_body(self):
        assert "AI_COMPLETE('m', 'p')" in self.DDL

    def test_has_dollar_delimiters(self):
        assert "$$" in self.DDL

    def test_ends_with_semicolon(self):
        assert self.DDL.rstrip().endswith(";")


class TestBuildCreateFunctionDDLCommentEscaping:
    """Comments with single quotes should be pre-escaped by the caller."""

    DDL = _build_create_function_ddl(
        fqn="D.S.F",
        input_params="X VARCHAR",
        return_type="VARCHAR",
        escaped_comment="It''s a function",
        body_expr="1",
    )

    def test_comment_preserved(self):
        assert "COMMENT = '[CORTEX AI FUNC STUDIO] It''s a function'" in self.DDL


# ---------------------------------------------------------------------------
# 11. Multimodal multi-output (VARIANT return)
# ---------------------------------------------------------------------------


class TestMultimodalMultiOutput:
    """Multimodal UDF with multiple outputs returns VARIANT."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="ANALYZE_DOC",
        model="claude-sonnet-4-5",
        function_intention="Analyze documents",
        inputs=[InputParam("DOC", "VARCHAR", is_file_path=True)],
        outputs=[
            OutputField("category", "string", "Category"),
            OutputField("summary", "string", "Summary"),
            OutputField("confidence", "number", "Confidence"),
        ],
        system_prompt="Analyze the document.",
        user_prompt_template="Analyze: {DOC}",
        stage_name="@DB.SCH.AI_FUNCTIONS",
    )

    def test_returns_variant(self):
        sql = generate_sql(self.SPEC)
        assert "RETURNS VARIANT" in sql

    def test_no_field_accessor(self):
        sql = generate_sql(self.SPEC)
        assert ":category::" not in sql
        assert ":summary::" not in sql

    def test_no_varchar_cast(self):
        """Multi-output should not have a blanket ::VARCHAR cast."""
        sql = generate_sql(self.SPEC)
        assert ")::VARCHAR" not in sql

    def test_uses_response_format(self):
        sql = generate_sql(self.SPEC)
        assert "response_format=>" in sql
        assert '"category"' in sql
        assert '"summary"' in sql
        assert '"confidence"' in sql

    def test_uses_prompt(self):
        sql = generate_sql(self.SPEC)
        assert "PROMPT(" in sql
        assert "TO_FILE" in sql


class TestMultimodalSingleNumberOutput:
    """Multimodal UDF with single number output returns FLOAT."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="SCORE_IMAGE",
        model="claude-sonnet-4-5",
        function_intention="Score images",
        inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
        outputs=[OutputField("score", "number", "Quality score 0-100")],
        system_prompt="Rate the image quality.",
        user_prompt_template="Rate: {IMG}",
        stage_name="@DB.SCH.AI_FUNCTIONS",
    )

    def test_returns_float(self):
        sql = generate_sql(self.SPEC)
        assert "RETURNS FLOAT" in sql

    def test_extracts_field(self):
        sql = generate_sql(self.SPEC)
        assert ":score::FLOAT" in sql

    def test_no_varchar_cast(self):
        sql = generate_sql(self.SPEC)
        assert ")::VARCHAR" not in sql


class TestMultimodalSingleBooleanOutput:
    """Multimodal UDF with single boolean output returns BOOLEAN."""

    SPEC = UDFSpec(
        database="DB",
        schema="SCH",
        function_name="IS_SAFE",
        model="claude-sonnet-4-5",
        function_intention="Safety check",
        inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
        outputs=[OutputField("is_safe", "boolean", "Whether image is safe")],
        system_prompt="",
        user_prompt_template="Is this safe? {IMG}",
        stage_name="@DB.SCH.STAGE",
    )

    def test_returns_boolean(self):
        sql = generate_sql(self.SPEC)
        assert "RETURNS BOOLEAN" in sql

    def test_extracts_field(self):
        sql = generate_sql(self.SPEC)
        assert ":is_safe::BOOLEAN" in sql


# ---------------------------------------------------------------------------
# 12. Text-only and multimodal return type parity
# ---------------------------------------------------------------------------


class TestReturnTypeParity:
    """Both paths produce the same return type / accessor for equivalent outputs."""

    OUTPUTS_SINGLE_STR: ClassVar[list[OutputField]] = [
        OutputField("label", "string", "d")
    ]
    OUTPUTS_SINGLE_NUM: ClassVar[list[OutputField]] = [
        OutputField("score", "number", "d")
    ]
    OUTPUTS_MULTI: ClassVar[list[OutputField]] = [
        OutputField("label", "string", "d"),
        OutputField("score", "number", "d"),
    ]

    def _text_spec(self, outputs):
        return UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=outputs,
            system_prompt="s",
            user_prompt_template="{X}",
        )

    def _mm_spec(self, outputs):
        return UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=outputs,
            system_prompt="s",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )

    def test_single_string_same_returns(self):
        text_sql = generate_sql(self._text_spec(self.OUTPUTS_SINGLE_STR))
        mm_sql = generate_sql(self._mm_spec(self.OUTPUTS_SINGLE_STR))
        assert "RETURNS VARCHAR" in text_sql
        assert "RETURNS VARCHAR" in mm_sql

    def test_single_number_same_returns(self):
        text_sql = generate_sql(self._text_spec(self.OUTPUTS_SINGLE_NUM))
        mm_sql = generate_sql(self._mm_spec(self.OUTPUTS_SINGLE_NUM))
        assert "RETURNS FLOAT" in text_sql
        assert "RETURNS FLOAT" in mm_sql

    def test_multi_output_same_returns(self):
        text_sql = generate_sql(self._text_spec(self.OUTPUTS_MULTI))
        mm_sql = generate_sql(self._mm_spec(self.OUTPUTS_MULTI))
        assert "RETURNS VARIANT" in text_sql
        assert "RETURNS VARIANT" in mm_sql

    def test_single_string_same_accessor(self):
        text_sql = generate_sql(self._text_spec(self.OUTPUTS_SINGLE_STR))
        mm_sql = generate_sql(self._mm_spec(self.OUTPUTS_SINGLE_STR))
        assert ":label::VARCHAR" in text_sql
        assert ":label::VARCHAR" in mm_sql

    def test_single_number_same_accessor(self):
        text_sql = generate_sql(self._text_spec(self.OUTPUTS_SINGLE_NUM))
        mm_sql = generate_sql(self._mm_spec(self.OUTPUTS_SINGLE_NUM))
        assert ":score::FLOAT" in text_sql
        assert ":score::FLOAT" in mm_sql

    def test_multi_output_no_accessor_both(self):
        text_sql = generate_sql(self._text_spec(self.OUTPUTS_MULTI))
        mm_sql = generate_sql(self._mm_spec(self.OUTPUTS_MULTI))
        assert ":label::" not in text_sql
        assert ":label::" not in mm_sql


# ---------------------------------------------------------------------------
# 13. Adversarial / injection tests
# ---------------------------------------------------------------------------


class TestSQLInjectionViaSystemPrompt:
    """System prompt containing SQL injection attempts."""

    def _make_spec(self, system_prompt, multimodal=False):
        if multimodal:
            return UDFSpec(
                database="D",
                schema="S",
                function_name="F",
                model="m",
                inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
                outputs=[OutputField("o", "string", "d")],
                system_prompt=system_prompt,
                user_prompt_template="{IMG}",
                stage_name="@S",
            )
        return UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt=system_prompt,
            user_prompt_template="{X}",
        )

    def test_single_quote_breakout_text(self):
        """Attempt to break out of single-quoted string in text-only."""
        sql = generate_sql(self._make_spec("'); DROP TABLE users; --"))
        assert "''); DROP TABLE users; --" in sql
        assert "DROP TABLE" not in sql.split("$$")[0]

    def test_single_quote_breakout_multimodal(self):
        """Attempt to break out of single-quoted string in multimodal."""
        sql = generate_sql(self._make_spec("'); DROP TABLE users; --", multimodal=True))
        assert "'')" in sql

    def test_dollar_quote_breakout_text(self):
        """$$ in system prompt must not break the DDL body delimiter."""
        sql = generate_sql(self._make_spec("end $$ ; DROP TABLE x; $$"))
        parts = sql.split("$$")
        assert "CREATE FUNCTION" in parts[0]
        assert len(parts) >= 3

    def test_dollar_quote_breakout_multimodal(self):
        """$$ in system prompt must not break multimodal DDL body."""
        sql = generate_sql(
            self._make_spec("end $$ ; DROP TABLE x; $$", multimodal=True)
        )
        assert "CREATE FUNCTION" in sql

    def test_backslash_sequences(self):
        """Backslashes should pass through without interpretation."""
        sql = generate_sql(self._make_spec("path\\to\\file\\n"))
        assert "path\\\\to\\\\file\\\\n" in sql or "path\\to\\file\\n" in sql


class TestSQLInjectionViaUserPrompt:
    """User prompt template containing injection attempts."""

    def test_single_quote_in_template_text(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="What's the {X} value? It's important.",
        )
        sql = generate_sql(spec)
        assert "What''s" in sql
        assert "It''s" in sql

    def test_single_quote_in_template_multimodal(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="What's in {IMG}? It's a test.",
            stage_name="@S",
        )
        sql = generate_sql(spec)
        assert "What''s" in sql
        assert "It''s" in sql

    def test_dollar_quotes_in_template(self):
        """$$ in user prompt should not break DDL."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="Use $$ for {X} $$",
        )
        sql = generate_sql(spec)
        assert sql.strip().endswith(";")


class TestSQLInjectionViaComment:
    """Function intention (COMMENT) containing injection attempts."""

    def test_single_quote_in_comment(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            function_intention="It's a user's function",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="{X}",
        )
        sql = generate_sql(spec)
        assert "COMMENT = '[CORTEX AI FUNC STUDIO] It''s a user''s function'" in sql

    def test_sql_in_comment(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            function_intention="'; DROP TABLE users; --",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="{X}",
        )
        sql = generate_sql(spec)
        assert "[CORTEX AI FUNC STUDIO]" in sql
        assert "'';" in sql  # single quote is escaped
        assert "DROP TABLE" in sql  # it's in the comment string, escaped

    def test_very_long_comment_truncated(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            function_intention="x" * 2000,
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="{X}",
        )
        sql = generate_sql(spec)
        comment_match = re.search(r"COMMENT = '([^']*(?:''[^']*)*)'", sql)
        assert comment_match
        assert len(comment_match.group(1)) <= 1000


class TestSQLInjectionViaStageName:
    """Stage name containing injection attempts."""

    def test_quote_in_stage_name(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@DB.'; DROP TABLE x; --.STAGE",
        )
        sql = _generate_multimodal_sql(spec)
        assert "''; DROP TABLE x; --" in sql

    def test_dollar_quote_in_stage_name(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@DB.$$BREAK$$.STAGE",
        )
        sql = _generate_multimodal_sql(spec)
        assert "CREATE FUNCTION" in sql


class TestSQLInjectionViaOutputFields:
    """Output field names/descriptions with injection attempts."""

    def test_quote_in_output_name(self):
        """Single quotes in output field name must be escaped in JSON schema."""
        outputs = [OutputField("it's_bad", "string", "desc")]
        _, _, expr = _resolve_output_schema(outputs)
        assert "it''s_bad" in expr

    def test_quote_in_output_description(self):
        outputs = [OutputField("label", "string", "user's description")]
        _, _, expr = _resolve_output_schema(outputs)
        assert "user''s description" in expr

    def test_braces_in_output_description(self):
        """JSON braces in description go through response_format, not PROMPT."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("label", "string", 'Format: {"key":"val"}')],
            system_prompt="",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )
        sql = generate_sql(spec)
        prompt_match = re.search(r"PROMPT\(\s*'([^']*(?:''[^']*)*)'", sql)
        assert prompt_match
        template_str = prompt_match.group(1)
        assert '"key"' not in template_str


class TestAdversarialPromptTemplates:
    """Edge cases in prompt template parsing."""

    def test_numeric_placeholder_in_text_template(self):
        """Templates with {0} should be treated as a literal placeholder name."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="Item {0}: {X}",
        )
        sql = generate_sql(spec)
        assert "X" in sql

    def test_nested_braces_multimodal(self):
        """Nested braces like {{IMG}} should not crash."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="{{IMG}}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "PROMPT(" in sql

    def test_empty_template_multimodal(self):
        """Empty user prompt template should still produce valid SQL."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[],
            system_prompt="",
            user_prompt_template="",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "CREATE FUNCTION" in sql
        assert "TO_FILE" in sql

    def test_only_whitespace_template_multimodal(self):
        """Whitespace-only template should still include file inputs."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[],
            system_prompt="",
            user_prompt_template="   ",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "TO_FILE" in sql

    def test_placeholder_case_mismatch(self):
        """Placeholder {img} vs input IMG — should still resolve (case-insensitive)."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="Look at {img}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "TO_FILE" in sql
        assert "{0}" in sql

    def test_many_placeholders_same_input(self):
        """Same placeholder repeated many times should produce one arg."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="{IMG} {IMG} {IMG} {IMG} {IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert sql.count("TO_FILE") == 1


class TestUnicodeInputs:
    """Unicode characters in various fields."""

    def test_unicode_system_prompt(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="分析情感。Analyze sentiment. Ñoño.",
            user_prompt_template="{X}",
        )
        sql = generate_sql(spec)
        assert "分析情感" in sql
        assert "Ñoño" in sql

    def test_unicode_function_intention(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            function_intention="Función de análisis 日本語テスト",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="{X}",
        )
        sql = generate_sql(spec)
        assert "Función de análisis" in sql
        assert "日本語テスト" in sql

    def test_unicode_output_description(self):
        r"""Unicode in a description round-trips through the SQL literal escaping.

        json.dumps JSON-escapes it to ``\uXXXX``, then escape_sql_string doubles
        the backslash so Snowflake's string-literal parser passes ``\uXXXX``
        through to PARSE_JSON intact instead of consuming the escape (the same
        doubling that keeps a description's ``\"`` from breaking PARSE_JSON).
        """
        outputs = [OutputField("sentiment", "string", "情感分析の結果")]
        _, _, expr = _resolve_output_schema(outputs)
        assert "\\\\u60c5\\\\u611f\\\\u5206\\\\u6790" in expr


class TestBoundaryConditions:
    """Boundary conditions and degenerate cases."""

    def test_single_char_input_name(self):
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("X", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="{X}",
        )
        sql = generate_sql(spec)
        assert "X VARCHAR" in sql

    def test_many_inputs(self):
        """10 inputs should all appear in the function signature."""
        inputs = [InputParam(f"P{i}", "VARCHAR") for i in range(10)]
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=inputs,
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template=" ".join(f"{{{inp.name}}}" for inp in inputs),
        )
        sql = generate_sql(spec)
        for i in range(10):
            assert f"P{i} VARCHAR" in sql

    def test_many_outputs(self):
        """10 outputs should produce VARIANT return with all fields in schema."""
        outputs = [OutputField(f"field_{i}", "string", f"desc {i}") for i in range(10)]
        return_type, result_suffix, expr = _resolve_output_schema(outputs)
        assert return_type == "VARIANT"
        assert result_suffix == ""
        for i in range(10):
            assert f"field_{i}" in expr

    def test_many_multimodal_inputs(self):
        """5 file + 5 text inputs with no placeholders."""
        inputs = [
            InputParam(f"IMG{i}", "VARCHAR", is_file_path=True) for i in range(5)
        ] + [InputParam(f"TXT{i}", "VARCHAR") for i in range(5)]
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=inputs,
            outputs=[OutputField("o", "string", "d")],
            system_prompt="",
            user_prompt_template="Analyze all.",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        for i in range(5):
            assert f"TO_FILE('@S', IMG{i})" in sql
            assert f"TXT{i}" in sql
        for i in range(10):
            assert f"{{{i}}}" in sql

    def test_output_name_matches_sql_keyword(self):
        """Output named 'SELECT' should still work (it's inside JSON schema)."""
        outputs = [OutputField("SELECT", "string", "A selection")]
        _, result_suffix, expr = _resolve_output_schema(outputs)
        assert ":SELECT::VARCHAR" in result_suffix
        assert '"SELECT"' in expr

    def test_input_named_like_sql_keyword(self):
        """Input named DROP should appear in function signature."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("DROP", "VARCHAR")],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="s",
            user_prompt_template="{DROP}",
        )
        sql = generate_sql(spec)
        assert "DROP VARCHAR" in sql

    def test_newlines_in_system_prompt_multimodal(self):
        """Newlines in system prompt should be preserved in system message."""
        spec = UDFSpec(
            database="D",
            schema="S",
            function_name="F",
            model="m",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("o", "string", "d")],
            system_prompt="Line one.\nLine two.\nLine three.",
            user_prompt_template="{IMG}",
            stage_name="@S",
        )
        sql = _generate_multimodal_sql(spec)
        assert "Line one." in sql
        assert "Line two." in sql


# ---------------------------------------------------------------------------
# 14. Reverse-parse DDL — edge cases not covered by e2e tests
# ---------------------------------------------------------------------------


class TestReverseParseDDLEdgeCases:
    def test_extract_model_case_insensitive(self):
        """model=> matching should be case-insensitive."""
        ddl = "MODEL=>'claude-4-sonnet'"
        model = extract_model_from_ddl_string(ddl)
        assert model == "claude-4-sonnet"

    def test_extract_prompt_missing_raises(self):
        """Raise ValueError if system prompt pattern not found."""
        with pytest.raises(ValueError, match="Could not extract system prompt"):
            extract_prompt_from_ddl_string("CREATE FUNCTION F(X VARCHAR) AS $$ 1 $$;")

    def test_extract_model_missing_raises(self):
        """Raise ValueError if model pattern not found."""
        with pytest.raises(ValueError, match="Could not extract model name"):
            extract_model_from_ddl_string("CREATE FUNCTION F(X VARCHAR) AS $$ 1 $$;")


class TestPromptExtractionWithQuotes:
    """System prompts containing single quotes should be fully extracted."""

    def _make_body(self, system_prompt: str) -> str:
        """Raw DESCRIBE body: the system prompt is a SQL literal with '' escapes."""
        escaped = system_prompt.replace("'", "''")
        return (
            f"    AI_COMPLETE(\n"
            f"        model=>'claude-sonnet-4-5',\n"
            f"        messages=>ARRAY_CONSTRUCT(\n"
            f"            OBJECT_CONSTRUCT(\n"
            f"                'role', 'system', 'content', '{escaped}'\n"
            f"            ),\n"
            f"            OBJECT_CONSTRUCT('role', 'user', 'content', X)\n"
            f"        )\n"
            f"    )::VARCHAR"
        )

    # Back-compat aliases: both the former "$$"-DDL and GET_DDL "'...'"-DDL
    # paths now resolve to the same raw DESCRIBE body.
    _make_dollar_ddl = _make_body
    _make_single_quote_ddl = _make_body

    def test_prompt_with_apostrophe_dollar_ddl(self):
        prompt = "You're an expert. Don't make mistakes."
        assert extract_prompt_from_ddl_string(self._make_body(prompt)) == prompt

    def test_prompt_with_apostrophe_single_quote_ddl(self):
        prompt = "You're an expert. Don't make mistakes."
        assert extract_prompt_from_ddl_string(self._make_body(prompt)) == prompt

    def test_prompt_without_quotes_dollar_ddl(self):
        prompt = "Classify the text into categories."
        assert extract_prompt_from_ddl_string(self._make_body(prompt)) == prompt

    def test_prompt_without_quotes_single_quote_ddl(self):
        prompt = "Classify the text into categories."
        assert extract_prompt_from_ddl_string(self._make_body(prompt)) == prompt

    def test_prompt_with_multiple_quotes(self):
        prompt = "It's the user's input. They'll say 'hello'."
        assert extract_prompt_from_ddl_string(self._make_body(prompt)) == prompt

    def test_prompt_with_multiple_quotes_single_quote_ddl(self):
        prompt = "It's the user's input. They'll say 'hello'."
        ddl = self._make_single_quote_ddl(prompt)
        assert extract_prompt_from_ddl_string(ddl) == prompt

    def test_model_from_dollar_ddl(self):
        ddl = self._make_dollar_ddl("sys")
        assert extract_model_from_ddl_string(ddl) == "claude-sonnet-4-5"

    def test_model_from_single_quote_ddl(self):
        ddl = self._make_single_quote_ddl("sys")
        assert extract_model_from_ddl_string(ddl) == "claude-sonnet-4-5"

    def test_round_trip_generated_ddl(self):
        """DDL from create_udf.py with quotes in prompt should parse."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="claude-sonnet-4-5",
            system_prompt="You're an expert. Don't guess.",
            user_prompt_template="Classify {TEXT}",
            inputs=[InputParam("TEXT", "VARCHAR")],
            outputs=[OutputField("label", "string", "Label")],
        )
        ddl = generate_sql(spec)
        assert extract_prompt_from_ddl_string(ddl) == "You're an expert. Don't guess."
        assert extract_model_from_ddl_string(ddl) == "claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# DDL response_format parsing (_parse_response_format_from_body)
# ---------------------------------------------------------------------------


class TestParseResponseFormatNamedParam:
    """Style 1: response_format=>PARSE_JSON('...')."""

    SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {"label": {"type": "string"}},
    }
    RF_JSON = '{"type": "json", "schema": {"type": "object", "properties": {"label": {"type": "string"}}}}'

    def _make_ddl(self, rf_json: str = RF_JSON) -> str:
        return (
            "CREATE FUNCTION DB.S.F(X VARCHAR)\n"
            "RETURNS VARCHAR LANGUAGE SQL AS $$\n"
            "    AI_COMPLETE(\n"
            "        model=>'claude-sonnet-4-5',\n"
            "        messages=>ARRAY_CONSTRUCT(...),\n"
            f"        response_format=>PARSE_JSON('{rf_json}')\n"
            "    )::VARCHAR\n$$;"
        )

    def test_basic_extraction(self):
        result = _parse_response_format_from_body(self._make_ddl())
        assert result["type"] == "json"
        assert result["schema"]["properties"]["label"]["type"] == "string"

    def test_case_insensitive_keywords(self):
        ddl = self._make_ddl().replace("PARSE_JSON", "parse_json")
        ddl = ddl.replace("response_format", "RESPONSE_FORMAT")
        result = _parse_response_format_from_body(ddl)
        assert result["type"] == "json"

    def test_whitespace_variations(self):
        ddl = "response_format =>  PARSE_JSON( '" + self.RF_JSON + "' )"
        result = _parse_response_format_from_body(ddl)
        assert result["schema"]["properties"]["label"]["type"] == "string"

    def test_sql_escaped_quotes_in_json(self):
        """SQL '' escaping within PARSE_JSON string is unescaped correctly."""
        rf_json = (
            '{"type": "json", "schema": {"type": "object", '
            '"properties": {"user\'s_note": {"type": "string"}}}}'
        )
        sql_escaped = rf_json.replace("'", "''")
        ddl = f"response_format=>PARSE_JSON('{sql_escaped}')"
        result = _parse_response_format_from_body(ddl)
        assert "user's_note" in result["schema"]["properties"]

    def test_multiple_outputs(self):
        rf_json = (
            '{"type": "json", "schema": {"type": "object", '
            '"properties": {"category": {"type": "string"}, '
            '"confidence": {"type": "number"}}}}'
        )
        result = _parse_response_format_from_body(
            f"response_format=>PARSE_JSON('{rf_json}')"
        )
        assert "category" in result["schema"]["properties"]
        assert "confidence" in result["schema"]["properties"]

    def test_malformed_json_raises(self):
        with pytest.raises(ValueError, match="Failed to parse response_format JSON"):
            _parse_response_format_from_body(
                "response_format=>PARSE_JSON('{not valid json}')"
            )


class TestParseResponseFormatDictLiteral:
    """Style 2: 'response_format': {...} inside options dict."""

    def test_basic_dict_literal(self):
        ddl = (
            "AI_COMPLETE('model', messages, "
            "{'response_format': {'type': 'json', 'schema': "
            "{'type': 'object', 'properties': {'a': {'type': 'string'}}}}})"
        )
        result = _parse_response_format_from_body(ddl)
        assert result["type"] == "json"
        assert "a" in result["schema"]["properties"]

    def test_double_quoted_key(self):
        ddl = (
            '{"response_format": {"type": "json", "schema": '
            '{"type": "object", "properties": {"b": {"type": "string"}}}}}'
        )
        result = _parse_response_format_from_body(ddl)
        assert "b" in result["schema"]["properties"]


class TestParseResponseFormatErrors:
    """Error cases for _parse_response_format_from_body."""

    def test_no_response_format_raises(self):
        ddl = "AI_COMPLETE(model=>'m', messages=>ARRAY_CONSTRUCT(...))"
        with pytest.raises(ValueError, match="no response_format"):
            _parse_response_format_from_body(ddl)

    def test_named_param_preferred_over_dict_literal(self):
        """When both styles present, named parameter wins."""
        ddl = (
            'response_format=>PARSE_JSON(\'{"type": "json", "schema": '
            '{"type": "object", "properties": {"from_named": {"type": "string"}}}}\')'
            " 'response_format': {'type': 'json', 'schema': "
            "{'type': 'object', 'properties': {'from_dict': {'type': 'string'}}}}"
        )
        result = _parse_response_format_from_body(ddl)
        assert "from_named" in result["schema"]["properties"]


class TestParseResponseFormatWithGeneratedDDL:
    """Round-trip: DDL from create_udf.py should be parseable."""

    def test_text_only_ddl_parses(self):
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            system_prompt="sys",
            user_prompt_template="Classify {TEXT}",
            inputs=[InputParam("TEXT", "VARCHAR")],
            outputs=[OutputField("label", "string", "The label")],
        )
        ddl = generate_sql(spec)
        result = _parse_response_format_from_body(ddl)
        assert result["type"] == "json"
        assert "label" in result["schema"]["properties"]

    def test_multimodal_ddl_parses(self):
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            system_prompt="sys",
            user_prompt_template="Describe {IMG}",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("desc", "string", "Description")],
            stage_name="@DB.S.STG",
        )
        ddl = generate_sql(spec)
        result = _parse_response_format_from_body(ddl)
        assert result["type"] == "json"
        assert "desc" in result["schema"]["properties"]

    def test_multimodal_multi_output_ddl_parses(self):
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            system_prompt="sys",
            user_prompt_template="Analyze {IMG}",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[
                OutputField("category", "string", "Category"),
                OutputField("confidence", "number", "Score"),
            ],
            stage_name="@DB.S.STG",
        )
        ddl = generate_sql(spec)
        result = _parse_response_format_from_body(ddl)
        assert "category" in result["schema"]["properties"]
        assert "confidence" in result["schema"]["properties"]

    def test_no_outputs_raises(self):
        """DDL without outputs has no response_format — should raise."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            system_prompt="sys",
            user_prompt_template="Summarize {TEXT}",
            inputs=[InputParam("TEXT", "VARCHAR")],
            outputs=[],
        )
        ddl = generate_sql(spec)
        with pytest.raises(ValueError, match="no response_format"):
            _parse_response_format_from_body(ddl)


# ---------------------------------------------------------------------------
# Adversarial & edge-case tests for _parse_response_format_from_body
# ---------------------------------------------------------------------------


class TestParseResponseFormatAdversarial:
    """Inputs designed to break, confuse, or exploit the parser."""

    RF_VALID = '{"type": "json", "schema": {"type": "object", "properties": {"x": {"type": "string"}}}}'

    def test_empty_ddl_raises(self):
        with pytest.raises(ValueError, match="no response_format"):
            _parse_response_format_from_body("")

    def test_whitespace_only_ddl_raises(self):
        with pytest.raises(ValueError, match="no response_format"):
            _parse_response_format_from_body("   \n\t  ")

    def test_response_format_as_substring_no_match(self):
        """'my_response_format' shouldn't match — but the regex is loose,
        so this documents the actual behavior.
        """  # noqa: D205
        ddl = "my_response_format=>PARSE_JSON('" + self.RF_VALID + "')"
        result = _parse_response_format_from_body(ddl)
        assert result["type"] == "json"

    def test_first_response_format_wins_even_in_comment(self):
        """Parser doesn't understand SQL comments — first match wins.
        In practice GET_DDL returns the body between $$ delimiters
        which doesn't contain SQL comments.
        """  # noqa: D205
        ddl = (
            "-- response_format=>PARSE_JSON('{\"bad\": true}')\n"
            f"response_format=>PARSE_JSON('{self.RF_VALID}')"
        )
        result = _parse_response_format_from_body(ddl)
        assert result == {"bad": True}

    def test_unterminated_parse_json_string(self):
        """PARSE_JSON string that never closes — should raise clear error."""
        ddl = 'response_format=>PARSE_JSON(\'{"type": "json"'
        with pytest.raises(ValueError, match="Unterminated PARSE_JSON string"):
            _parse_response_format_from_body(ddl)

    def test_empty_json_object_in_parse_json(self):
        """Empty JSON object — valid JSON but no 'schema' key."""
        ddl = "response_format=>PARSE_JSON('{}')"
        result = _parse_response_format_from_body(ddl)
        assert result == {}

    def test_json_with_only_type_no_schema(self):
        ddl = 'response_format=>PARSE_JSON(\'{"type": "json"}\')'
        result = _parse_response_format_from_body(ddl)
        assert result == {"type": "json"}
        assert "schema" not in result

    def test_backslash_sequences_in_json(self):
        r"""JSON with escape sequences (\n, \t, \\)."""
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"path": {"type": "string", "description": "like C:\\\\Users\\\\test"}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert "path" in result["schema"]["properties"]

    def test_unicode_property_names(self):
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"\\u5206\\u7c7b": {"type": "string"}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert "\u5206\u7c7b" in result["schema"]["properties"]

    def test_deeply_nested_schema(self):
        """Schema with multiple levels of nesting."""
        rf_json = (
            '{"type": "json", "schema": {"type": "object", "properties": '
            '{"outer": {"type": "object", "properties": '
            '{"inner": {"type": "object", "properties": '
            '{"deep": {"type": "string"}}}}}}}}'
        )
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        deep = result["schema"]["properties"]["outer"]["properties"]["inner"][
            "properties"
        ]
        assert "deep" in deep

    def test_json_with_array_types(self):
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"tags": {"type": "array", "items": {"type": "string"}}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert result["schema"]["properties"]["tags"]["type"] == "array"

    def test_many_properties(self):
        """Schema with a large number of output properties."""
        props = ", ".join(f'"f{i}": {{"type": "string"}}' for i in range(50))
        rf_json = f'{{"type": "json", "schema": {{"type": "object", "properties": {{{props}}}}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert len(result["schema"]["properties"]) == 50

    def test_consecutive_sql_escaped_quotes(self):
        """Multiple consecutive '' pairs — tricky for the walker."""
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"it\'s_a_user\'s_test": {"type": "string"}}}}'
        sql_escaped = rf_json.replace("'", "''")
        ddl = f"response_format=>PARSE_JSON('{sql_escaped}')"
        result = _parse_response_format_from_body(ddl)
        assert "it's_a_user's_test" in result["schema"]["properties"]

    def test_newlines_and_indentation_in_json(self):
        """Pretty-printed JSON inside PARSE_JSON."""
        rf_json = (
            "{\n"
            '    "type": "json",\n'
            '    "schema": {\n'
            '        "type": "object",\n'
            '        "properties": {\n'
            '            "result": {"type": "string"}\n'
            "        }\n"
            "    }\n"
            "}"
        )
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert "result" in result["schema"]["properties"]

    def test_sql_injection_attempt_in_property_name(self):
        """Property name trying to break out of the SQL string."""
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"x\\"); DROP TABLE users; --": {"type": "string"}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert 'x"); DROP TABLE users; --' in result["schema"]["properties"]

    def test_property_name_with_curly_braces(self):
        """Property name containing braces — should not confuse the parser."""
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"field_{0}": {"type": "string"}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert "field_{0}" in result["schema"]["properties"]

    def test_trailing_content_after_parse_json(self):
        """Extra SQL after PARSE_JSON(...) — should still parse correctly."""
        ddl = f"response_format=>PARSE_JSON('{self.RF_VALID}')\n    )::VARCHAR\n$$;"
        result = _parse_response_format_from_body(ddl)
        assert "x" in result["schema"]["properties"]

    def test_response_format_appears_in_system_prompt(self):
        """'response_format' inside a string constant shouldn't hijack the match
        when the real named-param version also exists.
        """  # noqa: D205
        ddl = (
            "'content', 'Always output response_format JSON'\n"
            f"response_format=>PARSE_JSON('{self.RF_VALID}')"
        )
        result = _parse_response_format_from_body(ddl)
        assert "x" in result["schema"]["properties"]

    def test_double_parse_json_first_wins(self):
        """Two PARSE_JSON calls — first match wins."""
        rf1 = '{"type": "json", "schema": {"type": "object", "properties": {"first": {"type": "string"}}}}'
        rf2 = '{"type": "json", "schema": {"type": "object", "properties": {"second": {"type": "string"}}}}'
        ddl = (
            f"response_format=>PARSE_JSON('{rf1}')\n"
            f"response_format=>PARSE_JSON('{rf2}')"
        )
        result = _parse_response_format_from_body(ddl)
        assert "first" in result["schema"]["properties"]

    def test_json_with_null_and_boolean_values(self):
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"flag": {"type": "boolean", "default": null}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert result["schema"]["properties"]["flag"]["default"] is None

    def test_json_with_numeric_values_in_schema(self):
        rf_json = '{"type": "json", "schema": {"type": "object", "properties": {"score": {"type": "number", "minimum": -1.5, "maximum": 100}}}}'
        ddl = f"response_format=>PARSE_JSON('{rf_json}')"
        result = _parse_response_format_from_body(ddl)
        assert result["schema"]["properties"]["score"]["minimum"] == -1.5


class TestParseResponseFormatDictLiteralEdgeCases:
    """Edge cases for style-2 (dict literal) parsing."""

    def test_unbalanced_braces_raises(self):
        ddl = "'response_format': {'type': 'json', 'schema': {"
        with pytest.raises(ValueError, match="Could not parse"):
            _parse_response_format_from_body(ddl)

    def test_value_not_a_dict_raises(self):
        """response_format value that is not a { — should raise."""
        ddl = "'response_format': 'not_a_dict'"
        with pytest.raises(ValueError, match="Could not parse response_format object"):
            _parse_response_format_from_body(ddl)

    def test_nested_quotes_in_dict_literal(self):
        ddl = (
            "{'response_format': {'type': 'json', 'schema': "
            "{'type': 'object', 'properties': {'note': {'type': 'string', "
            "'description': \"it's a 'test'\"}}}}}"
        )
        result = _parse_response_format_from_body(ddl)
        assert "note" in result["schema"]["properties"]

    def test_sql_double_quoted_strings_in_dict(self):
        ddl = (
            '"response_format": {"type": "json", "schema": '
            '{"type": "object", "properties": {"col": {"type": "string"}}}}'
        )
        result = _parse_response_format_from_body(ddl)
        assert "col" in result["schema"]["properties"]


class TestParseResponseFormatGetDDLEscaping:
    """DESCRIBE FUNCTION returns a raw body; response_format parses from it.

    Historically the optimizer parsed GET_DDL output (``AS '...'`` with doubled
    ``''`` quotes).  After the DESCRIBE migration the body is un-escaped and
    passed to ``_parse_response_format_from_body`` directly.  SQL string
    literals inside the body (e.g. ``PARSE_JSON('...')``) still use ``''``
    escaping, which the parser handles.
    """

    RF_JSON = '{"type": "json", "schema": {"type": "object", "properties": {"label": {"type": "string"}}}}'

    def _make_body(self, rf_json: str = RF_JSON) -> str:
        """Raw (un-escaped) function body as DESCRIBE FUNCTION returns it."""
        return (
            "    AI_COMPLETE(\n"
            "        model=>'claude-sonnet-4-5',\n"
            "        messages=>ARRAY_CONSTRUCT(\n"
            "            OBJECT_CONSTRUCT(\n"
            "                'role', 'system',\n"
            "                'content', 'Classify text'\n"
            "            ),\n"
            "            OBJECT_CONSTRUCT(\n"
            "                'role', 'user',\n"
            "                'content', TEXT\n"
            "            )\n"
            "        ),\n"
            f"        response_format=>PARSE_JSON('{rf_json}')\n"
            "    ):label::VARCHAR"
        )

    def test_raw_body_parses(self):
        """The DESCRIBE body parses response_format directly."""
        body = self._make_body()
        assert "$$" not in body
        result = _parse_response_format_from_body(body)
        assert result["type"] == "json"
        assert "label" in result["schema"]["properties"]

    def test_dollar_quote_ddl_still_parses(self):
        """A body embedded in a $$ DDL still parses (regex finds the pattern)."""
        body = (
            "    AI_COMPLETE(\n"
            "        model=>'claude-sonnet-4-5',\n"
            "        messages=>ARRAY_CONSTRUCT(...),\n"
            f"        response_format=>PARSE_JSON('{self.RF_JSON}')\n"
            "    ):label::VARCHAR"
        )
        ddl = (
            "CREATE FUNCTION DB.S.F(TEXT VARCHAR)\n"
            f"RETURNS VARCHAR LANGUAGE SQL AS $$\n{body}\n$$;"
        )
        result = _parse_response_format_from_body(ddl)
        assert "label" in result["schema"]["properties"]

    def test_body_with_system_prompt_quotes(self):
        """System prompt containing SQL-escaped single quotes ('')."""
        body = (
            "    AI_COMPLETE(\n"
            "        model=>'claude-sonnet-4-5',\n"
            "        messages=>ARRAY_CONSTRUCT(\n"
            "            OBJECT_CONSTRUCT('role', 'system', 'content',\n"
            "                'You''re an expert. Don''t make mistakes.'\n"
            "            ),\n"
            "            OBJECT_CONSTRUCT('role', 'user', 'content', TEXT)\n"
            "        ),\n"
            f"        response_format=>PARSE_JSON('{self.RF_JSON}')\n"
            "    ):label::VARCHAR"
        )
        result = _parse_response_format_from_body(body)
        assert "label" in result["schema"]["properties"]

    def test_body_multimodal(self):
        """Multimodal body with PROMPT() and TO_FILE()."""
        body = (
            "    AI_COMPLETE(\n"
            "        model=>'gemini-2.5-flash',\n"
            "        messages=>ARRAY_CONSTRUCT(\n"
            "            OBJECT_CONSTRUCT('role', 'system', 'content', 'Classify image'),\n"
            "            OBJECT_CONSTRUCT('role', 'user', 'content',\n"
            "                PROMPT('file: {0}', TO_FILE('@DB.S.STG', IMG_PATH))\n"
            "            )\n"
            "        ),\n"
            f"        response_format=>PARSE_JSON('{self.RF_JSON}')\n"
            "    ):label::VARCHAR"
        )
        result = _parse_response_format_from_body(body)
        assert "label" in result["schema"]["properties"]

    def test_body_multi_output(self):
        """Multi-output schema with VARIANT return."""
        rf_json = (
            '{"type": "json", "schema": {"type": "object", "properties": '
            '{"category": {"type": "string"}, "confidence": {"type": "number"}}}}'
        )
        body = self._make_body(rf_json)
        result = _parse_response_format_from_body(body)
        assert "category" in result["schema"]["properties"]
        assert "confidence" in result["schema"]["properties"]

    def test_body_with_description_containing_apostrophes(self):
        """Schema descriptions with apostrophes survive SQL '' escaping.

        Real chain: JSON has ' → SQL-escaped to '' in PARSE_JSON('...') inside
        the raw DESCRIBE body → walker undoes SQL '' level → json.loads gets
        valid JSON.
        """
        rf_json_sql_escaped = (
            '{"type": "json", "schema": {"type": "object", "properties": '
            '{"note": {"type": "string", "description": "The user\'\'s note"}}}}'
        )
        body = self._make_body(rf_json_sql_escaped)
        result = _parse_response_format_from_body(body)
        assert "note" in result["schema"]["properties"]

    def test_round_trip_text_only_from_body(self):
        """Generate DDL via create_udf, parse response_format from its raw body."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            system_prompt="You're an expert",
            user_prompt_template="Classify {TEXT}",
            inputs=[InputParam("TEXT", "VARCHAR")],
            outputs=[OutputField("label", "string", "The label")],
        )
        original_ddl = generate_sql(spec)
        # DESCRIBE FUNCTION returns the raw body between the $$ markers.
        body_start = original_ddl.index("$$") + 2
        body_end = original_ddl.rindex("$$")
        body = original_ddl[body_start:body_end]
        result = _parse_response_format_from_body(body)
        assert result["type"] == "json"
        assert "label" in result["schema"]["properties"]

    def test_round_trip_multimodal_from_body(self):
        """Generate multimodal DDL, parse response_format from its raw body."""
        spec = UDFSpec(
            database="DB",
            schema="S",
            function_name="F",
            model="m",
            system_prompt="Describe the image",
            user_prompt_template="What is in {IMG}?",
            inputs=[InputParam("IMG", "VARCHAR", is_file_path=True)],
            outputs=[OutputField("desc", "string", "Description")],
            stage_name="@DB.S.STG",
        )
        original_ddl = generate_sql(spec)
        body_start = original_ddl.index("$$") + 2
        body_end = original_ddl.rindex("$$")
        body = original_ddl[body_start:body_end]
        result = _parse_response_format_from_body(body)
        assert result["type"] == "json"
        assert "desc" in result["schema"]["properties"]


# ---------------------------------------------------------------------------
# FM1: Text-only DDL with no outputs should NOT emit response_format=>None
# ---------------------------------------------------------------------------


class TestTextOnlyNoOutputsDDL:
    """Verify text-only DDL without outputs produces valid SQL."""

    SPEC = UDFSpec(
        database="DB",
        schema="S",
        function_name="F",
        model="m",
        system_prompt="Summarize",
        user_prompt_template="Summarize {TEXT}",
        inputs=[InputParam("TEXT", "VARCHAR")],
        outputs=[],
    )

    def test_no_response_format_none_literal(self):
        """DDL must not contain the literal 'response_format=>None'."""
        ddl = generate_sql(self.SPEC)
        assert "response_format=>None" not in ddl

    def test_no_response_format_at_all(self):
        """DDL without outputs should omit response_format entirely."""
        ddl = generate_sql(self.SPEC)
        assert "response_format" not in ddl

    def test_returns_varchar(self):
        ddl = generate_sql(self.SPEC)
        assert "RETURNS VARCHAR" in ddl

    def test_has_varchar_cast(self):
        ddl = generate_sql(self.SPEC)
        assert "::VARCHAR" in ddl

    def test_valid_sql_structure(self):
        """DDL should still have proper AI_COMPLETE structure."""
        ddl = generate_sql(self.SPEC)
        assert "AI_COMPLETE(" in ddl
        assert "messages=>ARRAY_CONSTRUCT" in ddl
        assert ddl.strip().endswith("$$;")


class TestTextOnlyWithOutputsUnchanged:
    """Verify text-only DDL with outputs still emits response_format."""

    SPEC = UDFSpec(
        database="DB",
        schema="S",
        function_name="F",
        model="m",
        system_prompt="sys",
        user_prompt_template="Classify {TEXT}",
        inputs=[InputParam("TEXT", "VARCHAR")],
        outputs=[OutputField("label", "string", "Label")],
    )

    def test_still_has_response_format(self):
        ddl = generate_sql(self.SPEC)
        assert "response_format=>PARSE_JSON" in ddl

    def test_response_format_not_none(self):
        ddl = generate_sql(self.SPEC)
        assert "response_format=>None" not in ddl


# ---------------------------------------------------------------------------
# FM5: Unterminated PARSE_JSON string should raise a clear error
# ---------------------------------------------------------------------------


class TestUnterminatedParseJsonString:
    """Walker should raise a clear error when no closing quote is found."""

    def test_no_closing_quote_raises_clear_error(self):
        ddl = 'response_format=>PARSE_JSON(\'{"type": "json"'
        with pytest.raises(ValueError, match="Unterminated PARSE_JSON string"):
            _parse_response_format_from_body(ddl)

    def test_truncated_after_parse_json_paren(self):
        ddl = "response_format=>PARSE_JSON('"
        with pytest.raises(ValueError, match="Unterminated PARSE_JSON string"):
            _parse_response_format_from_body(ddl)

    def test_no_closing_quote_with_full_ddl_structure(self):
        ddl = (
            "CREATE FUNCTION F(X VARCHAR) RETURNS VARCHAR AS $$\n"
            "    AI_COMPLETE(model=>'m', messages=>ARRAY_CONSTRUCT(...),\n"
            '        response_format=>PARSE_JSON(\'{"type": "json"\n'
            "$$;"
        )
        with pytest.raises(ValueError, match="Unterminated PARSE_JSON string"):
            _parse_response_format_from_body(ddl)


# ---------------------------------------------------------------------------
# FM6: Balanced paren extraction for nested type signatures
# ---------------------------------------------------------------------------


class TestExtractBalancedParenContent:
    """_extract_balanced_paren_content should handle nested types."""

    def test_simple_signature(self):
        assert _extract_balanced_paren_content("FUNC(VARCHAR)") == "VARCHAR"

    def test_multiple_params(self):
        result = _extract_balanced_paren_content("FUNC(VARCHAR, NUMBER)")
        assert result == "VARCHAR, NUMBER"

    def test_nested_array_type(self):
        result = _extract_balanced_paren_content("FUNC(ARRAY(VARCHAR), NUMBER)")
        assert result == "ARRAY(VARCHAR), NUMBER"

    def test_deeply_nested(self):
        result = _extract_balanced_paren_content("FUNC(MAP(VARCHAR, ARRAY(NUMBER)))")
        assert result == "MAP(VARCHAR, ARRAY(NUMBER))"

    def test_no_parens_raises(self):
        with pytest.raises(ValueError, match="Could not parse function signature"):
            _extract_balanced_paren_content("FUNC_NO_PARENS")

    def test_unbalanced_parens_raises(self):
        with pytest.raises(ValueError, match="Could not parse function signature"):
            _extract_balanced_paren_content("FUNC(VARCHAR, ARRAY(NUMBER)")

    def test_empty_params(self):
        assert _extract_balanced_paren_content("FUNC()") == ""

    def test_with_prefix_text(self):
        """SHOW FUNCTIONS returns 'FUNC_NAME(types) RETURN type'."""
        result = _extract_balanced_paren_content(
            "MY_FUNC(VARCHAR, FLOAT) RETURN VARCHAR"
        )
        assert result == "VARCHAR, FLOAT"


# ---------------------------------------------------------------------------
# 15. Multimodal DDL reverse-parse and temp function creation
# ---------------------------------------------------------------------------

MULTIMODAL_DDL = """\
CREATE FUNCTION DB.SCH.ANALYZE(FILE_PATH VARCHAR, QUESTION VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Analyze images'
AS
$$
    AI_COMPLETE(
        model=>'claude-sonnet-4-5',
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'system', 'content', 'You are a visual analyst.'),
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                'Analyze {0} and answer: {1}',
                TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH),
                QUESTION
            ))
        ),
        response_format=>PARSE_JSON('{"type":"json"}')
    ):answer::VARCHAR
$$;"""


class TestMultimodalDDLParsing:
    """Optimizer body parsing works on multimodal UDFs."""

    def test_extract_system_prompt(self):
        assert (
            extract_prompt_from_ddl_string(_body_of(MULTIMODAL_DDL))
            == "You are a visual analyst."
        )

    def test_extract_model(self):
        assert (
            extract_model_from_ddl_string(_body_of(MULTIMODAL_DDL))
            == "claude-sonnet-4-5"
        )

    def test_prompt_does_not_capture_user_message(self):
        prompt = extract_prompt_from_ddl_string(_body_of(MULTIMODAL_DDL))
        assert "PROMPT(" not in prompt
        assert "TO_FILE" not in prompt


class TestExtractToFileRefs:
    def test_unescapes_quoted_stage_name(self):
        ddl = """\
CREATE FUNCTION DB.SCH.CLASSIFY_IMG(FILE_PATH VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
    AI_COMPLETE(
        model=>'claude-sonnet-4-5',
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                'file: {0}', TO_FILE('@DB.IT''S.STAGE', FILE_PATH)
            ))
        )
    )
$$;"""
        assert extract_to_file_refs(_body_of(ddl)) == ("@DB.IT'S.STAGE", ["FILE_PATH"])

    def test_deduplicates_columns_and_preserves_first_seen_order(self):
        ddl = """\
CREATE FUNCTION DB.SCH.CLASSIFY_IMG(FILE_PATH VARCHAR, THUMB_PATH VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
    AI_COMPLETE(
        model=>'claude-sonnet-4-5',
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                '{0} {1} {2}',
                TO_FILE('@DB.SCH.STAGE', FILE_PATH),
                TO_FILE('@DB.SCH.STAGE', THUMB_PATH),
                TO_FILE('@DB.SCH.STAGE', FILE_PATH)
            ))
        )
    )
$$;"""
        assert extract_to_file_refs(_body_of(ddl)) == (
            "@DB.SCH.STAGE",
            ["FILE_PATH", "THUMB_PATH"],
        )

    def test_parses_body_with_escaped_stage_quote(self):
        # DESCRIBE FUNCTION returns the raw body; a stage name with an embedded
        # single quote is still SQL-escaped as '' inside the string literal.
        # extract_to_file_refs un-escapes it to the logical stage name.
        body = (
            "    AI_COMPLETE(\n"
            "        model=>'claude-sonnet-4-5',\n"
            "        messages=>ARRAY_CONSTRUCT(\n"
            "            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(\n"
            "                'file: {0}', TO_FILE('@DB.IT''S.STAGE', FILE_PATH)\n"
            "            ))\n"
            "        )\n"
            "    )"
        )
        assert extract_to_file_refs(body) == ("@DB.IT'S.STAGE", ["FILE_PATH"])


class TestMultimodalTempFunction:
    """TempAIFunction renders self.ddl with name/model/prompt swapped, preserving multimodal user message."""  # noqa: W505

    def _make(self, **kwargs):
        defaults = dict(
            ddl=MULTIMODAL_DDL,
            temp_function_name="DB.SCH.TMP",
            candidate_model="claude-sonnet-4-5",
            candidate_prompt="New system prompt.",
        )
        defaults.update(kwargs)
        return _temp_fn_ddl(
            defaults.pop("ddl"),
            temp_function_name=defaults["temp_function_name"],
            candidate_model=defaults["candidate_model"],
            candidate_prompt=defaults["candidate_prompt"],
        )

    def test_replaces_name_model_prompt(self):
        result = self._make(
            temp_function_name="DB.SCH.TMP_F",
            candidate_model="gemini-2.5-flash",
            candidate_prompt="Optimized.",
        )
        assert "DB.SCH.TMP_F(" in result
        assert "DB.SCH.ANALYZE(" not in result
        assert "model=>'gemini-2.5-flash'" in result
        assert "'content', 'Optimized.'" in result

    def test_preserves_to_file_and_prompt(self):
        result = self._make()
        assert "TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)" in result
        assert "PROMPT(" in result
        assert "QUESTION" in result
        assert "Analyze {0} and answer: {1}" in result

    @pytest.mark.parametrize(
        "model",
        ["claude-sonnet-4-5", "gemini-2.5-flash", "llama4-scout", "mistral-large2"],
    )
    def test_prefix_is_added_for_file_only_prompt_on_rewrite(self, model):
        prompt_only_ddl = """\
CREATE FUNCTION DB.SCH.CLASSIFY_IMG(FILE_PATH VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Analyze image'
AS
$$
    AI_COMPLETE(
        model=>'claude-sonnet-4-5',
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'system', 'content', 'Legacy system prompt.'),
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                '{0}', TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)
            ))
        ),
        response_format=>PARSE_JSON('{"type":"json"}')
    ):answer::VARCHAR
$$;"""
        result = _temp_fn_ddl(
            prompt_only_ddl,
            temp_function_name="DB.SCH.TMP",
            candidate_model=model,
            candidate_prompt="Optimized.",
        )
        assert re.search(
            r"PROMPT\(\s*'file: \{0\}'\s*,\s*TO_FILE\('@DB\.SCH\.AI_FUNCTIONS', FILE_PATH\)",
            result,
        )
        assert f"model=>'{model}'" in result

    def test_prefix_is_added_when_stage_name_contains_escaped_quote(self):
        prompt_only_ddl = """\
CREATE FUNCTION DB.SCH.CLASSIFY_IMG(FILE_PATH VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Analyze image'
AS
$$
    AI_COMPLETE(
        model=>'claude-sonnet-4-5',
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'system', 'content', 'Legacy system prompt.'),
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                '{0}', TO_FILE('@DB.IT''S.STAGE', FILE_PATH)
            ))
        ),
        response_format=>PARSE_JSON('{"type":"json"}')
    ):answer::VARCHAR
$$;"""
        result = _temp_fn_ddl(
            prompt_only_ddl,
            temp_function_name="DB.SCH.TMP",
            candidate_model="gemini-2.5-flash",
            candidate_prompt="Optimized.",
        )
        assert "TO_FILE('@DB.IT''S.STAGE', FILE_PATH)" in result
        assert re.search(
            r"PROMPT\(\s*'file: \{0\}'\s*,\s*TO_FILE\('@DB\.IT''S\.STAGE', FILE_PATH\)",
            result,
        )

    def test_replaces_model_expression_with_literal(self):
        expression_model_ddl = """\
CREATE FUNCTION DB.SCH.CLASSIFY_IMG(FILE_PATH VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Analyze image'
AS
$$
    AI_COMPLETE(
        model=>IFNULL(MODEL_NAME, 'claude-sonnet-4-5'),
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'system', 'content', 'Legacy system prompt.'),
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                '{0}', TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)
            ))
        ),
        response_format=>PARSE_JSON('{"type":"json"}')
    ):answer::VARCHAR
$$;"""
        result = _temp_fn_ddl(
            expression_model_ddl,
            temp_function_name="DB.SCH.TMP",
            candidate_model="mistral-large2",
            candidate_prompt="Optimized.",
        )
        assert "model=>'mistral-large2'" in result
        assert "IFNULL(MODEL_NAME" not in result
        assert "mistral-large2" in result

    def test_replaces_late_model_expression_with_nested_commas(self):
        expression_model_ddl = """\
CREATE FUNCTION DB.SCH.CLASSIFY_IMG(FILE_PATH VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Analyze image'
AS
$$
    AI_COMPLETE(
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'system', 'content', 'Legacy system prompt.'),
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                '{0} Explain whether model=> sentinel, commas, and (parens) stay literal.',
                TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)
            ))
        ),
        model=>COALESCE(NULLIF(MODEL_NAME, 'legacy,model'), 'claude-sonnet-4-5'),
        response_format=>PARSE_JSON('{"type":"json"}')
    ):answer::VARCHAR
$$;"""
        result = _temp_fn_ddl(
            expression_model_ddl,
            temp_function_name="DB.SCH.TMP",
            candidate_model="mistral-large2",
            candidate_prompt="Optimized.",
        )
        assert "model=>'mistral-large2'" in result
        assert "COALESCE(NULLIF(MODEL_NAME" not in result
        assert (
            "file: {0} Explain whether model=> sentinel, commas, and (parens) stay literal."
            in result
        )

    def test_preserves_existing_file_prefix_on_rewrite(self):
        prompt_only_ddl = """\
CREATE FUNCTION DB.SCH.CLASSIFY_IMG(FILE_PATH VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
COMMENT = 'Analyze image'
AS
$$
    AI_COMPLETE(
        model=>'claude-sonnet-4-5',
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'system', 'content', 'Legacy system prompt.'),
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                'file: {0}', TO_FILE('@DB.SCH.AI_FUNCTIONS', FILE_PATH)
            ))
        ),
        response_format=>PARSE_JSON('{"type":"json"}')
    ):answer::VARCHAR
$$;"""
        result = _temp_fn_ddl(
            prompt_only_ddl,
            temp_function_name="DB.SCH.TMP",
            candidate_model="gemini-2.5-flash",
            candidate_prompt="Optimized.",
        )
        assert "file: file:" not in result.lower()
        assert result.count("file: {0}") == 1

    def test_preserves_response_format(self):
        result = self._make()
        assert "response_format=>PARSE_JSON" in result

    def test_escapes_quotes_in_candidate_prompt(self):
        result = self._make(candidate_prompt="You're an expert. Don't guess.")
        assert "You''re an expert. Don''t guess." in result

    def test_raw_body_preserved_in_rendered_ddl(self):
        # DESCRIBE FUNCTION returns a raw (un-escaped) body; the rendered temp
        # DDL emits it verbatim between $$ delimiters (no single-quote escaping).
        ddl = """\
CREATE FUNCTION DB.SCH.F(IMG VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
    AI_COMPLETE(
        model=>'claude-sonnet-4-5',
        messages=>ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('role', 'system', 'content', 'Classify.'),
            OBJECT_CONSTRUCT('role', 'user', 'content', PROMPT(
                '{0} Classify.', TO_FILE('@S', IMG)
            ))
        )
    )::VARCHAR
$$;"""
        result = _temp_fn_ddl(
            ddl,
            temp_function_name="DB.SCH.TMP",
            candidate_model="claude-sonnet-4-5",
            candidate_prompt="New.",
        )
        assert "$$" in result
        assert "TO_FILE('@S', IMG)" in result
        assert "'content', 'New.'" in result
        assert re.search(r"PROMPT\(\s*'file: \{0\} Classify\.'", result)


# ---------------------------------------------------------------------------
# 16. TempAIFunction._rewrite_ai_complete_for_error_details — nested parens
# ---------------------------------------------------------------------------


class TestRewriteAICompleteForErrorDetails:
    def test_rewrite_with_nested_parse_json(self):
        """Rewrite must handle PARSE_JSON(...) nested inside AI_COMPLETE(...)."""
        ddl = (
            "CREATE FUNCTION DB.S.F(TEXT VARCHAR)\n"
            "RETURNS VARCHAR\n"
            "LANGUAGE SQL\n"
            "AS\n"
            "$$\n"
            "    AI_COMPLETE(\n"
            "        model=>'llama3.1-8b',\n"
            "        messages=>ARRAY_CONSTRUCT(\n"
            "            OBJECT_CONSTRUCT('role', 'system', 'content', 'hello'),\n"
            "            OBJECT_CONSTRUCT('role', 'user', 'content', TEXT)\n"
            "        ),\n"
            '        response_format=>PARSE_JSON(\'{"type":"json"}\')\n'
            "    ):label::VARCHAR\n"
            "$$;"
        )
        result = TempAIFunction._rewrite_ai_complete_for_error_details(
            ddl, value_type="VARCHAR"
        )
        # Should contain the injected param
        assert "return_error_details=>TRUE" in result
        # Should have the OBJECT cast
        assert "OBJECT(value VARIANT, error STRING)" in result
        # Accessor should be stripped
        assert ":label::VARCHAR" not in result
        # PARSE_JSON should still be intact
        assert "PARSE_JSON(" in result
        # Should be valid structure (AI_COMPLETE not truncated)
        assert "response_format=>PARSE_JSON" in result

    def test_rewrite_forces_existing_return_error_details_to_true(self):
        """Force return_error_details to TRUE without duplicating the kwarg.

        ``return_error_details=>TRUE`` is required during evaluation so the
        inline-eval path (``call_rows``) can retry per-row errors and surface
        ``INFERENCE_ERROR: ...`` to the reflection LM.  A user-supplied
        ``FALSE`` (or ``TRUE``) MUST be force-replaced with ``TRUE`` while
        preserving the single occurrence of the kwarg.
        """
        ddl_true = (
            "$$\n"
            "    AI_COMPLETE(\n"
            "        model=>'m',\n"
            "        messages=>ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('role','user','content',X)),\n"
            "        return_error_details=>TRUE\n"
            "    )\n"
            "$$;"
        )
        result_true = TempAIFunction._rewrite_ai_complete_for_error_details(
            ddl_true, value_type="VARCHAR"
        )
        assert result_true.count("return_error_details") == 1
        assert "return_error_details=>TRUE" in result_true

        # User-supplied FALSE must be force-replaced with TRUE so per-row
        # error capture is not silently disabled during evaluation.
        ddl_false = (
            "$$\n"
            "    AI_COMPLETE(\n"
            "        model=>'m',\n"
            "        messages=>ARRAY_CONSTRUCT(OBJECT_CONSTRUCT('role','user','content',X)),\n"
            "        return_error_details=>FALSE\n"
            "    )\n"
            "$$;"
        )
        result_false = TempAIFunction._rewrite_ai_complete_for_error_details(
            ddl_false, value_type="VARCHAR"
        )
        assert result_false.count("return_error_details") == 1
        assert "return_error_details=>TRUE" in result_false
        assert "return_error_details=>FALSE" not in result_false


# ---------------------------------------------------------------------------
# 17. TempAIFunction.call_rows — local unit tests with stubs
# ---------------------------------------------------------------------------


class _FakeCol:
    def __init__(self, name: str):
        self.name = name

    def alias(self, alias_name: str):
        return _FakeAliased(self, alias_name)

    def __getitem__(self, key: str):
        return _FakeFieldAccess(self, key)

    def isin(self, values: list[int]):
        return _FakeIsInPredicate(self.name, set(values))


class _FakeFieldAccess:
    def __init__(self, base: _FakeCol, key: str):
        self.base = base
        self.key = key

    def alias(self, alias_name: str):
        return _FakeAliased(self, alias_name)


class _FakeCall:
    def __init__(self, func_name: str, args: list[_FakeCol]):
        self.func_name = func_name
        self.args = args

    def alias(self, alias_name: str):
        return _FakeAliased(self, alias_name)


class _FakeAliased:
    def __init__(self, expr, alias_name: str):
        self.expr = expr
        self.alias_name = alias_name


class _FakeIsInPredicate:
    def __init__(self, col_name: str, values: set[int]):
        self.col_name = col_name
        self.values = values


class _FakeDF:
    def __init__(self, rows: list[dict[str, object]], session: _FakeSession):
        self._rows = rows
        self._session = session

    def select(self, *exprs):
        out_rows: list[dict[str, object]] = []
        for row in self._rows:
            projected: dict[str, object] = {}
            for expr in exprs:
                if isinstance(expr, _FakeCol):
                    projected[expr.name] = row.get(expr.name)
                elif isinstance(expr, _FakeAliased):
                    projected[expr.alias_name] = self._eval_expr(expr.expr, row)
                else:
                    raise TypeError(f"Unsupported select expr: {type(expr)}")
            out_rows.append(projected)
        return _FakeDF(out_rows, self._session)

    def _eval_expr(self, expr, row: dict[str, object]):
        if isinstance(expr, _FakeCol):
            return row.get(expr.name)
        if isinstance(expr, _FakeFieldAccess):
            base = row.get(expr.base.name)
            return base.get(expr.key) if isinstance(base, dict) else None
        if isinstance(expr, _FakeCall):
            args_values = [row.get(c.name) for c in expr.args]
            return self._session._call_function(
                expr.func_name, row_id=int(row["__ROW_ID"]), args=args_values
            )
        raise TypeError(f"Unsupported eval expr: {type(expr)}")

    def filter(self, predicate: _FakeIsInPredicate):
        if not isinstance(predicate, _FakeIsInPredicate):
            raise TypeError(f"Unsupported filter predicate: {type(predicate)}")
        filtered = [
            r for r in self._rows if int(r[predicate.col_name]) in predicate.values
        ]
        return _FakeDF(filtered, self._session)

    def collect(self):
        return list(self._rows)


class _FakeSQL:
    def collect(self):
        return []


class _FakeSession:
    def __init__(
        self,
        *,
        fail_first_row_ids: set[int] | None = None,
        always_fail_row_ids: set[int] | None = None,
        return_value_as_dict: bool = False,
    ):
        self._fail_first = fail_first_row_ids or set()
        self._always_fail = always_fail_row_ids or set()
        self._return_value_as_dict = return_value_as_dict
        self.call_counts: dict[int, int] = {}

    def sql(self, *_args, **_kwargs):
        return _FakeSQL()

    def create_dataframe(self, rows: list[dict[str, object]], schema=None):
        self._last_created_rows = rows
        return _FakeDF(rows, self)

    def _call_function(self, _func_name: str, *, row_id: int, args: list[object]):
        self.call_counts[row_id] = self.call_counts.get(row_id, 0) + 1

        if row_id in self._always_fail:
            return {"value": None, "error": "boom"}
        if row_id in self._fail_first and self.call_counts[row_id] == 1:
            return {"value": None, "error": "transient"}

        text = str(args[0]) if args else ""
        value: object
        value = {"label": f"ok-{text}"} if self._return_value_as_dict else f"ok-{text}"
        return {"value": value, "error": ""}


def _make_temp_fn(session, accessor_field=None):
    temp_fn = TempAIFunction.__new__(TempAIFunction)
    temp_fn.session = session
    temp_fn.temp_function_name = "TEMP_FN"
    temp_fn.accessor_field = accessor_field
    temp_fn._file_type_params = set()
    temp_fn._semi_structured_params = set()
    temp_fn._stage_name = None
    return temp_fn


@pytest.mark.skip(
    reason=(
        "The legacy _FakeSession / _FakeDF / _FakeCall fixtures intercepted "
        "Snowpark's ``call_function(temp_fn, ...)`` path that the inline-eval "
        "migration retired.  ``TempAIFunction.call_rows`` now materialises "
        "the input batch via ``df.write.save_as_table(temporary)`` + raw "
        "``session.sql(cte)`` instead.  See TestTempAIFunctionInlineCallRows "
        "below for the equivalent coverage (retry loop, accessor "
        "application) against the new path."
    )
)
class TestTempAIFunctionCallRows:
    @pytest.fixture(autouse=True)
    def _patch_snowpark(self, monkeypatch):
        import snowflake_ai_optimize.core.temp_ai_function as utils

        monkeypatch.setattr(utils, "col", lambda name: _FakeCol(name))
        monkeypatch.setattr(
            utils, "call_function", lambda name, *args: _FakeCall(name, list(args))
        )

    def test_call_rows_preserves_order_and_retries_transient_errors(self):
        session = _FakeSession(fail_first_row_ids={1})
        temp_fn = _make_temp_fn(session)

        rows = [{"TEXT": "a"}, {"TEXT": "b"}, {"TEXT": "c"}]
        out = temp_fn.call_rows(rows)

        assert out == ["ok-a", "ok-b", "ok-c"]
        assert session.call_counts == {0: 1, 1: 2, 2: 1}

    def test_call_rows_applies_matched_accessor_to_dict_values(self):
        session = _FakeSession(return_value_as_dict=True)
        temp_fn = _make_temp_fn(session, accessor_field="LABEL")

        rows = [{"TEXT": "x"}, {"TEXT": "y"}]
        out = temp_fn.call_rows(rows)

        assert out == ["ok-x", "ok-y"]

    def test_call_rows_returns_inference_error_after_max_attempts(self, monkeypatch):
        import snowflake_ai_optimize.core.temp_ai_function as utils

        monkeypatch.setattr(utils, "TEMP_AI_FUNCTION_MAX_ATTEMPTS", 2)

        session = _FakeSession(always_fail_row_ids={0})
        temp_fn = _make_temp_fn(session)

        out = temp_fn.call_rows([{"TEXT": "a"}])
        assert isinstance(out[0], str)
        assert out[0].startswith("INFERENCE_ERROR:")


# ---------------------------------------------------------------------------
# 18. core_evaluation.evaluate — executor path unit tests
# ---------------------------------------------------------------------------


class _FakeRow(dict):
    """Row-like object supporting row['COL'] access."""


class _FakeSessionEvaluate:
    def __init__(self, rows: list[dict[str, object]]):
        self._rows = [_FakeRow(r) for r in rows]

    def sql(self, _query: str):
        class _SQL:
            def __init__(self, rows):
                self._rows = rows

            def collect(self):
                return self._rows

        return _SQL(self._rows)


class TestEvaluateWithExecutor:
    def test_executor_path_uses_only_input_columns_and_preserves_order(self):
        session = _FakeSessionEvaluate(
            [
                {"ROW_ID": 1, "TEXT": "a", "EXPECTED": "positive"},
                {"ROW_ID": 2, "TEXT": "b", "EXPECTED": "negative"},
            ]
        )

        seen_inputs: list[list[dict[str, object]]] = []

        def executor(rows: list[dict[str, object]]):
            seen_inputs.append(rows)
            return ["positive", "negative"]

        result = core_evaluation.evaluate(
            session,
            function_name="DB.SCHEMA.FUNC",
            test_table="DB.SCHEMA.T",
            input_columns=["TEXT"],
            label_column="EXPECTED",
            metric_name="exact_match",
            executor=executor,
        )

        assert result.score == 1.0
        assert seen_inputs == [[{"TEXT": "a"}, {"TEXT": "b"}]]
        assert len(result.details) == 2
        assert all(d["metric_score"] == 1.0 for d in result.details)

    def test_executor_inference_error_skips_metric_evaluation(self):
        session = _FakeSessionEvaluate(
            [
                {"ROW_ID": 1, "TEXT": "a", "EXPECTED": "positive"},
                {"ROW_ID": 2, "TEXT": "b", "EXPECTED": "negative"},
            ]
        )

        def executor(_rows: list[dict[str, object]]):
            return ["INFERENCE_ERROR: boom", "negative"]

        # Only 1 of 2 rows can score => avg = 0.5
        result = core_evaluation.evaluate(
            session,
            function_name="DB.SCHEMA.FUNC",
            test_table="DB.SCHEMA.T",
            input_columns=["TEXT"],
            label_column="EXPECTED",
            metric_name="exact_match",
            executor=executor,
        )
        assert result.score == 0.5
        assert len(result.details) == 2
        # Row 0 should have the inference error captured.
        assert result.details[0]["error_message"].startswith("INFERENCE_ERROR")


# ---------------------------------------------------------------------------
# 3. Anonymous SPROC conversion
# ---------------------------------------------------------------------------


class TestAnonymousSproc:
    def test_render_with_anonymous_flag(self):
        sql = render_sproc_sql("evaluate", "DB", "SCHEMA", "STAGE", anonymous=True)
        assert "WITH EVALUATE_AI_FUNCTION AS PROCEDURE" in sql
        assert "CREATE PROCEDURE" not in sql
        assert not sql.rstrip().endswith(";")

    def test_render_without_anonymous_flag(self):
        sql = render_sproc_sql("evaluate", "DB", "SCHEMA", "STAGE", anonymous=False)
        assert "CREATE OR REPLACE PROCEDURE" in sql
        assert "WITH EVALUATE_AI_FUNCTION AS PROCEDURE" not in sql

    def test_anonymous_optimize(self):
        sql = render_sproc_sql("optimize", "DB", "SCHEMA", "STAGE", anonymous=True)
        assert "WITH OPTIMIZE_AI_FUNCTION AS PROCEDURE" in sql

    def test_anonymous_synthetic(self):
        sql = render_sproc_sql("synthetic", "DB", "SCHEMA", "STAGE", anonymous=True)
        assert "WITH GENERATE_SYNTHETIC_DATA AS PROCEDURE" in sql

    def test_inline_evaluate_embeds_python(self):
        sql = render_sproc_sql("evaluate", "DB", "SCHEMA", inline=True, anonymous=True)
        assert "AS $$" in sql
        assert "IMPORTS" not in sql
        assert "HANDLER = 'evaluate_handler'" in sql

    def test_inline_optimize_embeds_python(self):
        sql = render_sproc_sql("optimize", "DB", "SCHEMA", inline=True, anonymous=True)
        assert "AS $$" in sql
        assert "IMPORTS" not in sql
        assert "HANDLER = 'run_optimization'" in sql

    def test_inline_synthetic_embeds_python(self):
        sql = render_sproc_sql("synthetic", "DB", "SCHEMA", inline=True, anonymous=True)
        assert "AS $$" in sql
        assert "IMPORTS" not in sql
        assert "HANDLER = 'generate_synthetic_data'" in sql

    def test_inline_contains_source_code(self):
        # The inline body is gzip+base64-compressed (see _compress_inline_body);
        # decompress the stub payload and confirm the real handler source is
        # what gets embedded.
        import base64
        import re
        import zlib

        sql = render_sproc_sql("evaluate", "DB", "SCHEMA", inline=True)
        m = re.search(r"b64decode\('([A-Za-z0-9+/=]+)'\)", sql)
        assert m, "inline SQL should embed a base64 bundle payload"
        source = zlib.decompress(base64.b64decode(m.group(1))).decode("utf-8")
        assert "def evaluate_handler(" in source

    def test_non_inline_does_not_embed(self):
        sql = render_sproc_sql("evaluate", "DB", "SCHEMA", "STAGE", inline=False)
        assert "IMPORTS" in sql
        assert "AS $$" not in sql


# ---------------------------------------------------------------------------
# 20. semi_structured_param_names — FunctionArg-based semi-structured detection
# ---------------------------------------------------------------------------


class TestExtractSemiStructuredParams:
    def _params(self, signature: str) -> set[str]:
        return semi_structured_param_names(parse_signature_args(signature))

    def test_single_array_param(self):
        assert self._params("(input VARCHAR, cats ARRAY)") == {"CATS"}

    def test_multiple_array_params(self):
        assert self._params("(text VARCHAR, tags ARRAY, ids ARRAY)") == {"TAGS", "IDS"}

    def test_no_structured_params(self):
        assert self._params("(text VARCHAR, num NUMBER)") == set()

    def test_quoted_param_names(self):
        assert self._params('("input_text" VARCHAR, "categories" ARRAY)') == {
            "CATEGORIES"
        }

    def test_case_insensitive_array_type(self):
        assert self._params("(text VARCHAR, cats array)") == {"CATS"}

    def test_no_args_returns_empty(self):
        assert self._params("()") == set()

    def test_mixed_types_with_array(self):
        assert self._params(
            "(text VARCHAR, cats ARRAY, score NUMBER, tags ARRAY, flag BOOLEAN)"
        ) == {"CATS", "TAGS"}

    def test_variant_param(self):
        assert self._params("(text VARCHAR, payload VARIANT)") == {"PAYLOAD"}

    def test_object_param(self):
        assert self._params("(text VARCHAR, metadata OBJECT)") == {"METADATA"}

    def test_mixed_semi_structured_types(self):
        assert self._params(
            "(text VARCHAR, cats ARRAY, data VARIANT, meta OBJECT)"
        ) == {"CATS", "DATA", "META"}

    def test_case_insensitive_variant(self):
        assert self._params("(text VARCHAR, data variant)") == {"DATA"}

    def test_direct_functionarg_input(self):
        # semi_structured_param_names operates directly on FunctionArg lists
        # (as describe_function produces), not just parsed signatures.
        args = [
            FunctionArg("t", "VARCHAR"),
            FunctionArg("a", "ARRAY"),
            FunctionArg("n", "NUMBER(38,0)"),
        ]
        assert semi_structured_param_names(args) == {"A"}


# ---------------------------------------------------------------------------
# 21. TempAIFunction.call_rows — semi-structured parameter handling
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "Tests assert ``session._last_created_rows`` shape produced by "
        "``call_rows``'s input normalization (json.dumps on lists/dicts).  "
        "That normalization step is preserved by the inline-eval refactor, "
        "but the surrounding _FakeSession fixture is tied to the old "
        "call_function(...) path.  Equivalent coverage moves to "
        "TestTempAIFunctionInlineSemiStructured below."
    )
)
class TestTempAIFunctionCallRowsSemiStructured:
    @pytest.fixture(autouse=True)
    def _patch_snowpark(self, monkeypatch):
        import snowflake_ai_optimize.core.temp_ai_function as utils

        def original_col(name):
            return _FakeCol(name)

        class _FakeParseJson:
            def __init__(self, inner):
                self.inner = inner
                self.name = f"PARSE_JSON({inner.name})"

        def fake_parse_json(expr):
            return _FakeParseJson(expr)

        monkeypatch.setattr(utils, "col", original_col)
        monkeypatch.setattr(utils, "parse_json", fake_parse_json)
        monkeypatch.setattr(
            utils, "call_function", lambda name, *args: _FakeCall(name, list(args))
        )

    def test_list_values_json_serialized_for_array_params(self):
        import json

        session = _FakeSession()
        temp_fn = _make_temp_fn(session)
        temp_fn._semi_structured_params = {"CATEGORIES"}

        rows = [{"TEXT": "hello", "CATEGORIES": ["A", "B", "C"]}]
        temp_fn.call_rows(rows)

        df_rows = session._last_created_rows
        assert df_rows[0]["CATEGORIES"] == json.dumps(["A", "B", "C"])
        assert df_rows[0]["TEXT"] == "hello"

    def test_string_values_not_double_serialized(self):
        session = _FakeSession()
        temp_fn = _make_temp_fn(session)
        temp_fn._semi_structured_params = {"CATEGORIES"}

        rows = [{"TEXT": "hello", "CATEGORIES": '["X","Y"]'}]
        temp_fn.call_rows(rows)

        df_rows = session._last_created_rows
        assert df_rows[0]["CATEGORIES"] == '["X","Y"]'

    def test_tuple_values_serialized_like_lists(self):
        import json

        session = _FakeSession()
        temp_fn = _make_temp_fn(session)
        temp_fn._semi_structured_params = {"TAGS"}

        rows = [{"TEXT": "test", "TAGS": ("a", "b")}]
        temp_fn.call_rows(rows)

        df_rows = session._last_created_rows
        assert df_rows[0]["TAGS"] == json.dumps(["a", "b"])

    def test_no_serialization_when_params_empty(self):
        session = _FakeSession()
        temp_fn = _make_temp_fn(session)

        rows = [{"TEXT": "hello", "ITEMS": ["A", "B"]}]
        temp_fn.call_rows(rows)

        df_rows = session._last_created_rows
        assert df_rows[0]["ITEMS"] == ["A", "B"]

    def test_dict_values_json_serialized_for_variant_params(self):
        import json

        session = _FakeSession()
        temp_fn = _make_temp_fn(session)
        temp_fn._semi_structured_params = {"PAYLOAD"}

        rows = [{"TEXT": "hello", "PAYLOAD": {"key": "value", "num": 42}}]
        temp_fn.call_rows(rows)

        df_rows = session._last_created_rows
        assert df_rows[0]["PAYLOAD"] == json.dumps({"key": "value", "num": 42})

    def test_dict_string_not_double_serialized(self):
        session = _FakeSession()
        temp_fn = _make_temp_fn(session)
        temp_fn._semi_structured_params = {"METADATA"}

        rows = [{"TEXT": "hi", "METADATA": '{"k": "v"}'}]
        temp_fn.call_rows(rows)

        df_rows = session._last_created_rows
        assert df_rows[0]["METADATA"] == '{"k": "v"}'

    def test_no_dict_serialization_when_params_empty(self):
        session = _FakeSession()
        temp_fn = _make_temp_fn(session)

        rows = [{"TEXT": "hello", "DATA": {"a": 1}}]
        temp_fn.call_rows(rows)

        df_rows = session._last_created_rows
        assert df_rows[0]["DATA"] == {"a": 1}


# ---------------------------------------------------------------------------
# 22. _extract_input_type_map — synthetic data type detection
# ---------------------------------------------------------------------------


class TestExtractInputTypeMap:
    def _make_session(self, arguments_str: str):
        from unittest.mock import MagicMock

        session = MagicMock()
        row = {"arguments": arguments_str}
        session.sql.return_value.collect.return_value = [row]
        return session

    def test_varchar_and_array(self):
        session = self._make_session("F(VARCHAR, ARRAY) RETURN VARCHAR")
        result = _extract_input_type_map(
            session, "DB.SCHEMA.F", ["INPUT", "CATEGORIES"]
        )
        assert result == {"INPUT": "VARCHAR", "CATEGORIES": "ARRAY"}

    def test_all_varchar(self):
        session = self._make_session("F(VARCHAR, VARCHAR) RETURN VARCHAR")
        result = _extract_input_type_map(session, "DB.SCHEMA.F", ["A", "B"])
        assert result == {"A": "VARCHAR", "B": "VARCHAR"}

    def test_empty_function_name(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        result = _extract_input_type_map(session, "", ["A"])
        assert result == {}
        session.sql.assert_not_called()

    def test_non_three_part_name(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        result = _extract_input_type_map(session, "F", ["A"])
        assert result == {}

    def test_more_cols_than_params_default_to_varchar(self):
        session = self._make_session("F(ARRAY) RETURN VARCHAR")
        result = _extract_input_type_map(session, "DB.SCHEMA.F", ["TAGS", "EXTRA"])
        assert result == {"TAGS": "ARRAY", "EXTRA": "VARCHAR"}

    def test_session_error_returns_empty(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        session.sql.return_value.collect.side_effect = RuntimeError("connection error")
        result = _extract_input_type_map(session, "DB.SCHEMA.F", ["A"])
        assert result == {}

    def test_no_rows_returns_empty(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        session.sql.return_value.collect.return_value = []
        result = _extract_input_type_map(session, "DB.SCHEMA.F", ["A"])
        assert result == {}

    def test_function_name_with_signature(self):
        session = self._make_session("F(VARCHAR, ARRAY) RETURN VARCHAR")
        result = _extract_input_type_map(
            session, "DB.SCHEMA.F(VARCHAR, ARRAY)", ["TEXT", "CATS"]
        )
        assert result == {"TEXT": "VARCHAR", "CATS": "ARRAY"}

    def test_named_params_in_arguments(self):
        session = self._make_session(
            'F("INPUT" VARCHAR, "CATEGORIES" ARRAY) RETURN VARCHAR'
        )
        result = _extract_input_type_map(
            session, "DB.SCHEMA.F", ["INPUT", "CATEGORIES"]
        )
        assert result == {"INPUT": "VARCHAR", "CATEGORIES": "ARRAY"}

    def test_parameterized_types_with_commas(self):
        session = self._make_session("F(NUMBER(10,2), VARCHAR) RETURN VARCHAR")
        result = _extract_input_type_map(session, "DB.SCHEMA.F", ["PRICE", "NAME"])
        assert result == {"PRICE": "NUMBER(10,2)", "NAME": "VARCHAR"}

    def test_named_parameterized_types_with_commas(self):
        session = self._make_session(
            'F("PRICE" NUMBER(10,2), "NAME" VARCHAR(100)) RETURN VARCHAR'
        )
        result = _extract_input_type_map(session, "DB.SCHEMA.F", ["PRICE", "NAME"])
        assert result == {"PRICE": "NUMBER(10,2)", "NAME": "VARCHAR(100)"}

    @pytest.mark.parametrize(
        "type_str",
        [
            # Simple types (no parameters)
            "VARCHAR",
            "TEXT",
            "STRING",
            "CHAR",
            "CHARACTER",
            "BINARY",
            "VARBINARY",
            "NUMBER",
            "DECIMAL",
            "NUMERIC",
            "INT",
            "INTEGER",
            "BIGINT",
            "SMALLINT",
            "TINYINT",
            "BYTEINT",
            "FLOAT",
            "FLOAT4",
            "FLOAT8",
            "DOUBLE",
            "REAL",
            "BOOLEAN",
            "DATE",
            "TIME",
            "TIMESTAMP",
            "TIMESTAMP_LTZ",
            "TIMESTAMP_NTZ",
            "TIMESTAMP_TZ",
            "VARIANT",
            "OBJECT",
            "ARRAY",
            "GEOGRAPHY",
            "GEOMETRY",
            # Single-parameter types
            "VARCHAR(100)",
            "CHAR(10)",
            "STRING(50)",
            "BINARY(256)",
            "VARBINARY(128)",
            "NUMBER(38)",
            "TIME(9)",
            "TIMESTAMP(9)",
            "TIMESTAMP_NTZ(9)",
            "TIMESTAMP_LTZ(9)",
            "TIMESTAMP_TZ(9)",
            # Multi-parameter types (commas inside parens)
            "NUMBER(38,0)",
            "NUMBER(10,2)",
            "DECIMAL(18,4)",
            "NUMERIC(5,3)",
            # VECTOR types (nested type name + comma)
            "VECTOR(FLOAT,256)",
            "VECTOR(INT,128)",
        ],
    )
    def test_all_snowflake_types(self, type_str):
        session = self._make_session(f"F({type_str}) RETURN VARCHAR")
        result = _extract_input_type_map(session, "DB.SCHEMA.F", ["COL"])
        assert result == {"COL": type_str.upper()}

    @pytest.mark.parametrize(
        "types, expected",
        [
            (
                "NUMBER(10,2), VARCHAR(100), ARRAY",
                {"A": "NUMBER(10,2)", "B": "VARCHAR(100)", "C": "ARRAY"},
            ),
            (
                "VECTOR(FLOAT,256), NUMBER(38,0), VARIANT",
                {"A": "VECTOR(FLOAT,256)", "B": "NUMBER(38,0)", "C": "VARIANT"},
            ),
            (
                "DECIMAL(18,4), DECIMAL(5,3)",
                {"A": "DECIMAL(18,4)", "B": "DECIMAL(5,3)"},
            ),
        ],
    )
    def test_mixed_parameterized_types(self, types, expected):
        cols = list(expected.keys())
        session = self._make_session(f"F({types}) RETURN VARCHAR")
        result = _extract_input_type_map(session, "DB.SCHEMA.F", cols)
        assert result == expected


# ---------------------------------------------------------------------------
# 23. _generate_batch — ARRAY-aware schema and prompt generation
# ---------------------------------------------------------------------------


class TestGenerateBatchArrayTypes:
    def test_array_type_produces_array_schema(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()
        input_types = {"TEXT": "VARCHAR", "CATEGORIES": "ARRAY"}

        fake_response = {
            "examples": [
                {
                    "inputs": {"TEXT": "hello", "CATEGORIES": ["A", "B"]},
                    "outputs": {"label": "A"},
                }
            ]
        }

        with patch(
            "snowflake_ai_optimize.synthetic.synthetic_data.RobustAIComplete.run_ai_complete_with_json_fallback",
            return_value=fake_response,
        ) as mock_llm:
            _generate_batch(
                session=session,
                task_description="Classify text",
                batch_size=1,
                batch_idx=0,
                model="test-model",
                input_columns=["TEXT", "CATEGORIES"],
                output_keys=["label"],
                input_types=input_types,
            )

            call_kwargs = mock_llm.call_args[1]
            schema = call_kwargs["response_schema"]

            input_props = schema["properties"]["examples"]["items"]["properties"][
                "inputs"
            ]["properties"]
            assert input_props["TEXT"] == {"type": "string"}
            assert input_props["CATEGORIES"] == {
                "type": "array",
                "items": {"type": "string"},
            }

    def _fake_response(self, input_cols, output_keys):
        """Build a minimal valid LLM response for _generate_batch."""
        inputs = dict.fromkeys(input_cols, "sample")
        outputs = dict.fromkeys(output_keys, "value")
        return {"examples": [{"inputs": inputs, "outputs": outputs}]}

    def test_array_type_adds_prompt_note(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()
        input_types = {"TEXT": "VARCHAR", "CATEGORIES": "ARRAY"}

        with patch(
            "snowflake_ai_optimize.synthetic.synthetic_data.RobustAIComplete.run_ai_complete_with_json_fallback",
            return_value=self._fake_response(["TEXT", "CATEGORIES"], ["label"]),
        ) as mock_llm:
            _generate_batch(
                session=session,
                task_description="Classify text",
                batch_size=1,
                batch_idx=0,
                model="test-model",
                input_columns=["TEXT", "CATEGORIES"],
                output_keys=["label"],
                input_types=input_types,
            )

            prompt = mock_llm.call_args[1]["primary_prompt"]
            assert "IMPORTANT" in prompt
            assert "structured JSON" in prompt
            assert "CATEGORIES" in prompt

    def test_no_structured_note_without_structured_types(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()

        with patch(
            "snowflake_ai_optimize.synthetic.synthetic_data.RobustAIComplete.run_ai_complete_with_json_fallback",
            return_value=self._fake_response(["TEXT"], ["label"]),
        ) as mock_llm:
            _generate_batch(
                session=session,
                task_description="Classify text",
                batch_size=1,
                batch_idx=0,
                model="test-model",
                input_columns=["TEXT"],
                output_keys=["label"],
                input_types={"TEXT": "VARCHAR"},
            )

            prompt = mock_llm.call_args[1]["primary_prompt"]
            assert "IMPORTANT" not in prompt

    def test_variant_type_produces_object_schema(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()
        input_types = {"TEXT": "VARCHAR", "PAYLOAD": "VARIANT"}

        with patch(
            "snowflake_ai_optimize.synthetic.synthetic_data.RobustAIComplete.run_ai_complete_with_json_fallback",
            return_value=self._fake_response(["TEXT", "PAYLOAD"], ["label"]),
        ) as mock_llm:
            _generate_batch(
                session=session,
                task_description="Process data",
                batch_size=1,
                batch_idx=0,
                model="test-model",
                input_columns=["TEXT", "PAYLOAD"],
                output_keys=["label"],
                input_types=input_types,
            )

            schema = mock_llm.call_args[1]["response_schema"]
            input_props = schema["properties"]["examples"]["items"]["properties"][
                "inputs"
            ]["properties"]
            assert input_props["PAYLOAD"] == {"type": "object"}

    def test_object_type_produces_object_schema(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()
        input_types = {"TEXT": "VARCHAR", "META": "OBJECT"}

        with patch(
            "snowflake_ai_optimize.synthetic.synthetic_data.RobustAIComplete.run_ai_complete_with_json_fallback",
            return_value=self._fake_response(["TEXT", "META"], ["label"]),
        ) as mock_llm:
            _generate_batch(
                session=session,
                task_description="Process data",
                batch_size=1,
                batch_idx=0,
                model="test-model",
                input_columns=["TEXT", "META"],
                output_keys=["label"],
                input_types=input_types,
            )

            schema = mock_llm.call_args[1]["response_schema"]
            input_props = schema["properties"]["examples"]["items"]["properties"][
                "inputs"
            ]["properties"]
            assert input_props["META"] == {"type": "object"}

    def test_no_input_types_defaults_to_string_schema(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()

        with patch(
            "snowflake_ai_optimize.synthetic.synthetic_data.RobustAIComplete.run_ai_complete_with_json_fallback",
            return_value=self._fake_response(["TEXT", "EXTRA"], ["label"]),
        ) as mock_llm:
            _generate_batch(
                session=session,
                task_description="Classify",
                batch_size=1,
                batch_idx=0,
                model="test-model",
                input_columns=["TEXT", "EXTRA"],
                output_keys=["label"],
                input_types=None,
            )

            schema = mock_llm.call_args[1]["response_schema"]
            input_props = schema["properties"]["examples"]["items"]["properties"][
                "inputs"
            ]["properties"]
            assert input_props["TEXT"] == {"type": "string"}
            assert input_props["EXTRA"] == {"type": "string"}

    def test_example_payload_shows_array_format(self):
        from unittest.mock import MagicMock, patch

        session = MagicMock()

        with patch(
            "snowflake_ai_optimize.synthetic.synthetic_data.RobustAIComplete.run_ai_complete_with_json_fallback",
            return_value=self._fake_response(["TEXT", "TAGS"], ["result"]),
        ) as mock_llm:
            _generate_batch(
                session=session,
                task_description="Tag content",
                batch_size=1,
                batch_idx=0,
                model="test-model",
                input_columns=["TEXT", "TAGS"],
                output_keys=["result"],
                input_types={"TEXT": "VARCHAR", "TAGS": "ARRAY"},
            )

            prompt = mock_llm.call_args[1]["fallback_prompt"]
            assert '["item1", "item2"]' in prompt


# ---------------------------------------------------------------------------
# 24. _insert_examples — list/tuple input serialization
# ---------------------------------------------------------------------------


class TestInsertExamplesArraySerialization:
    def test_list_values_serialized_to_json(self):
        import json
        from unittest.mock import MagicMock

        session = MagicMock()
        mock_df = MagicMock()
        session.create_dataframe.return_value = mock_df
        mock_df.select.return_value = mock_df
        mock_df.write.mode.return_value.save_as_table = MagicMock()

        examples = [
            {
                "inputs": {"TEXT": "hello", "CATEGORIES": ["A", "B", "C"]},
                "outputs": {"label": "A"},
            }
        ]

        _insert_examples(
            session, "DB.S.OUT", ["TEXT", "CATEGORIES"], ["label"], examples
        )

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0][0] == "hello"
        assert created_rows[0][1] == json.dumps(["A", "B", "C"])

    def test_string_values_unchanged(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        mock_df = MagicMock()
        session.create_dataframe.return_value = mock_df
        mock_df.select.return_value = mock_df
        mock_df.write.mode.return_value.save_as_table = MagicMock()

        examples = [
            {
                "inputs": {"TEXT": "hello", "EXTRA": "world"},
                "outputs": {"label": "ok"},
            }
        ]

        _insert_examples(session, "DB.S.OUT", ["TEXT", "EXTRA"], ["label"], examples)

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0][0] == "hello"
        assert created_rows[0][1] == "world"

    def test_tuple_values_serialized_like_lists(self):
        import json
        from unittest.mock import MagicMock

        session = MagicMock()
        mock_df = MagicMock()
        session.create_dataframe.return_value = mock_df
        mock_df.select.return_value = mock_df
        mock_df.write.mode.return_value.save_as_table = MagicMock()

        examples = [
            {
                "inputs": {"TEXT": "hi", "TAGS": ("x", "y")},
                "outputs": {"label": "ok"},
            }
        ]

        _insert_examples(session, "DB.S.OUT", ["TEXT", "TAGS"], ["label"], examples)

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0][1] == json.dumps(["x", "y"])

    def test_empty_list_serialized(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        mock_df = MagicMock()
        session.create_dataframe.return_value = mock_df
        mock_df.select.return_value = mock_df
        mock_df.write.mode.return_value.save_as_table = MagicMock()

        examples = [
            {
                "inputs": {"TEXT": "hi", "ITEMS": []},
                "outputs": {"label": "none"},
            }
        ]

        _insert_examples(session, "DB.S.OUT", ["TEXT", "ITEMS"], ["label"], examples)

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0][1] == "[]"

    def test_mixed_rows_with_and_without_lists(self):
        import json
        from unittest.mock import MagicMock

        session = MagicMock()
        mock_df = MagicMock()
        session.create_dataframe.return_value = mock_df
        mock_df.select.return_value = mock_df
        mock_df.write.mode.return_value.save_as_table = MagicMock()

        examples = [
            {
                "inputs": {"TEXT": "a", "CATS": ["X"]},
                "outputs": {"label": "X"},
            },
            {
                "inputs": {"TEXT": "b", "CATS": "already-string"},
                "outputs": {"label": "Y"},
            },
        ]

        _insert_examples(session, "DB.S.OUT", ["TEXT", "CATS"], ["label"], examples)

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0][1] == json.dumps(["X"])
        assert created_rows[1][1] == "already-string"

    def test_dict_values_serialized_to_json(self):
        import json
        from unittest.mock import MagicMock

        session = MagicMock()
        mock_df = MagicMock()
        session.create_dataframe.return_value = mock_df
        mock_df.select.return_value = mock_df
        mock_df.write.mode.return_value.save_as_table = MagicMock()

        examples = [
            {
                "inputs": {"TEXT": "hello", "PAYLOAD": {"key": "val"}},
                "outputs": {"label": "ok"},
            }
        ]

        _insert_examples(session, "DB.S.OUT", ["TEXT", "PAYLOAD"], ["label"], examples)

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0][1] == json.dumps({"key": "val"})

    def test_empty_examples_returns_zero(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        count = _insert_examples(session, "DB.S.OUT", ["TEXT"], ["label"], [])
        assert count == 0
        session.create_dataframe.assert_not_called()


# ---------------------------------------------------------------------------
# SnowflakeUserException wrapping tests
# ---------------------------------------------------------------------------


class TestSnowflakeUserExceptionWrapping:
    """Verify that handler functions re-raise exceptions as _snowflake.SnowflakeUserException
    when the _snowflake module is available (i.e., inside the Snowflake SP runtime).

    We inject a fake _snowflake module via sys.modules so that the ``import _snowflake``
    inside each handler's except block succeeds, then trigger a validation error and
    assert the raised exception is SnowflakeUserException with the original message.
    """  # noqa: D205, W505

    @pytest.fixture(autouse=True)
    def _install_fake_snowflake_module(self):
        """Install a fake _snowflake module with SnowflakeUserException for the duration of each test."""  # noqa: W505
        import sys
        import types

        fake_module = types.ModuleType("_snowflake")

        class SnowflakeUserException(Exception):
            pass

        fake_module.SnowflakeUserException = SnowflakeUserException
        self.SnowflakeUserException = SnowflakeUserException

        sys.modules["_snowflake"] = fake_module
        yield
        sys.modules.pop("_snowflake", None)

    def test_create_handler_wraps_validation_error(self):
        """create_handler raises SnowflakeUserException for a non-FQ function name."""
        from unittest.mock import MagicMock

        from create_udf import create_handler

        session = MagicMock()

        with pytest.raises(self.SnowflakeUserException, match="fully qualified"):
            create_handler(
                session,
                function_name="NOT_QUALIFIED",  # missing DB.SCHEMA prefix
                model="mistral-7b",
                system_prompt="test",
                user_prompt_template="{TEXT}",
                inputs=[{"name": "TEXT", "sql_type": "VARCHAR"}],
                outputs=[{"name": "label", "json_type": "string", "description": "x"}],
            )

    def test_evaluate_handler_wraps_validation_error(self):
        """evaluate_handler raises SnowflakeUserException for an empty custom_metric_udf."""  # noqa: W505
        from unittest.mock import MagicMock

        from handlers.evaluate_handler import evaluate_handler

        session = MagicMock()

        with pytest.raises(
            self.SnowflakeUserException, match="UDF name cannot be empty"
        ):
            evaluate_handler(
                session,
                function_name="DB.SCHEMA.FUNC",
                test_table="DB.SCHEMA.TABLE",
                input_columns=["TEXT"],
                label_column="EXPECTED",
                metric_name="exact_match",
                custom_metric_udf="",  # empty string triggers ValueError
            )

    def test_generate_synthetic_data_wraps_error(self):
        """generate_synthetic_data raises SnowflakeUserException when input_columns is None."""  # noqa: W505
        from unittest.mock import MagicMock

        from snowflake_ai_optimize.synthetic.synthetic_data import (
            generate_synthetic_data,
        )

        session = MagicMock()

        with pytest.raises(
            self.SnowflakeUserException,
            match="INPUT_COLUMNS is required and cannot be NULL",
        ):
            generate_synthetic_data(
                session,
                task_description="test",
                output_table="DB.SCHEMA.OUT",
                input_columns=None,  # triggers ValueError in _normalize_columns
                model="mistral-7b",
                num_examples=5,
            )

    def test_surface_errors_decorator_wraps_exception(self):
        """The @surface_sproc_error() decorator wraps exceptions."""
        from snowflake_ai_optimize.core.sproc_decorators import surface_sproc_error

        @surface_sproc_error()
        def failing_function():
            raise ValueError("boom")

        with pytest.raises(self.SnowflakeUserException, match="boom"):
            failing_function()

    def test_without_fake_module_original_exception_propagates(self):
        """Without _snowflake in sys.modules, the original exception propagates unchanged."""  # noqa: W505
        import sys

        # Remove the fake module installed by the fixture
        del sys.modules["_snowflake"]

        from snowflake_ai_optimize.core.sproc_decorators import surface_sproc_error

        @surface_sproc_error()
        def failing_function():
            raise ValueError("original error")

        with pytest.raises(ValueError, match="original error"):
            failing_function()


# ---------------------------------------------------------------------------
# 28. TempAIFunction inline-eval migration coverage (new helpers)
# ---------------------------------------------------------------------------
#
# After the inline-eval migration, TempAIFunction no longer issues a CREATE
# TEMPORARY FUNCTION at construction.  Instead it builds an inline SQL
# expression via _build_inline_expr (re-using all existing _build_ddl
# rewrites + injecting show_details=>TRUE) and call_rows evaluates it
# directly via session.create_or_replace_temp_view + session.sql(<CTE>).
#
# Coverage below:
#  * TestBuildInlineExpr — verifies _build_inline_expr's SQL output.
#  * TestTempAIFunctionConstructorNoFunction — asserts __init__ does NOT
#    issue any CREATE TEMPORARY FUNCTION SQL.
#  * TestTempAIFunctionInlineCallRows — exercises call_rows with a
#    MagicMock session; checks no CREATE FUNCTION, retry loop works,
#    token counts accumulate, accessor applies, error rows surface as
#    INFERENCE_ERROR.
#  * TestTempAIFunctionInlineSemiStructured — semi-structured input
#    normalization (json.dumps on lists/dicts before binding) survives
#    the refactor and is exposed via PARSE_JSON in the input projection.


SAMPLE_PROMPT_DDL = """\
CREATE FUNCTION DB.SCHEMA.CLASSIFY(input_text VARCHAR)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
AI_COMPLETE(
    model=>'mistral-large2',
    messages=>ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT('role','system','content','Classify the text.'),
        OBJECT_CONSTRUCT('role','user','content',input_text)
    )
):label::VARCHAR
$$;
"""


class TestBuildInlineExpr:
    """TempAIFunction.inline_expr — the executed AI_COMPLETE body expression."""

    def _expr(self, *, candidate_model: str, candidate_prompt: str) -> str:
        from unittest.mock import MagicMock

        inst = TempAIFunction(
            session=MagicMock(),
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="__INLINE",
            candidate_model=candidate_model,
            candidate_prompt=candidate_prompt,
        )
        return inst.inline_expr

    def test_injects_show_details_and_error_details(self):
        expr = self._expr(
            candidate_model="claude-haiku-4-5",
            candidate_prompt="Be concise.",
        )
        # show_details=>TRUE injected for token capture.
        assert "show_details=>TRUE" in expr
        # return_error_details=>TRUE preserved (existing prompt-mode contract).
        assert "return_error_details=>TRUE" in expr
        # AI_COMPLETE is wrapped in ::OBJECT(value VARIANT, error STRING).
        assert "OBJECT(value VARIANT, error STRING)" in expr

    def test_swaps_candidate_model(self):
        expr = self._expr(
            candidate_model="claude-haiku-4-5",
            candidate_prompt="Be concise.",
        )
        assert "claude-haiku-4-5" in expr
        assert "mistral-large2" not in expr

    def test_swaps_candidate_prompt(self):
        expr = self._expr(
            candidate_model="claude-haiku-4-5",
            candidate_prompt="You are an excellent classifier.",
        )
        assert "You are an excellent classifier." in expr
        assert "Classify the text." not in expr

    def test_no_create_function_shell(self):
        """The inline expression must NOT contain CREATE TEMPORARY FUNCTION."""
        expr = self._expr(
            candidate_model="claude-haiku-4-5",
            candidate_prompt="x",
        )
        upper = expr.upper()
        assert "CREATE TEMPORARY FUNCTION" not in upper
        assert "CREATE FUNCTION" not in upper
        assert "LANGUAGE SQL" not in upper


class TestTempAIFunctionConstructorNoFunction:
    """__init__ does NOT execute self.ddl after the inline-eval migration."""

    def test_init_does_not_issue_create_function(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        TempAIFunction(
            session=session,
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="DB.S.TMP",
            candidate_model="claude-haiku-4-5",
            candidate_prompt="Classify.",
        )

        # Confirm no SQL was issued at construction time.  ``self.ddl`` is
        # still built for inspection (back-compat with TestMultimodalTempFunction)
        # but never executed.
        assert session.sql.call_count == 0

    def test_init_sets_inline_expr_attribute(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        inst = TempAIFunction(
            session=session,
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="DB.S.TMP",
            candidate_model="claude-haiku-4-5",
            candidate_prompt="Classify.",
        )

        assert hasattr(inst, "inline_expr")
        assert "show_details=>TRUE" in inst.inline_expr

    def test_init_keeps_self_ddl_for_back_compat(self):
        """self.ddl is built (for test inspection) but never executed."""
        from unittest.mock import MagicMock

        session = MagicMock()
        inst = TempAIFunction(
            session=session,
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="DB.S.TMP",
            candidate_model="claude-haiku-4-5",
            candidate_prompt="Classify.",
        )
        assert hasattr(inst, "ddl")
        assert "CREATE" in inst.ddl.upper()  # full DDL shell present


def _build_inline_session_mock(
    *,
    attempts: list[list[dict[str, object]]],
):
    """Build a MagicMock session for inline-eval tests.

    *attempts* lists the per-retry collect() return values (each list of
    dicts represents the rows the SELECT would emit on that attempt).
    Successful rows have ``ERROR=None`` and contribute to the result;
    failed rows have ``ERROR!=None`` and trigger another retry attempt
    until exhausted.

    The mock wires up the post-migration ``df.write.save_as_table``
    path (the inline-eval batch is now materialised as a temp
    TABLE rather than a temp VIEW so long-text inputs don't blow past
    Snowflake's view-definition size limit).  ``DROP TABLE IF EXISTS``
    sweeps return empty lists.
    """
    from unittest.mock import MagicMock

    session = MagicMock()
    df = MagicMock()
    session.create_dataframe.return_value = df
    df.select.return_value = df
    # New path: df.write.save_as_table(name, mode='overwrite',
    # table_type='temporary').  Returns None; MagicMock auto-chains
    # df.write so we don't need to wire write explicitly.
    df.write.save_as_table.return_value = None

    # Each call to session.sql(...) returns a fresh _SqlCall whose
    # .collect() pops the next attempt off the list.  ``DROP TABLE IF
    # EXISTS`` SQL returns an empty list (and never raises).
    attempt_iter = iter(attempts)

    def _sql_side_effect(sql_text):
        sql_mock = MagicMock()
        text_upper = sql_text.upper() if isinstance(sql_text, str) else ""
        if "DROP TABLE" in text_upper or "DROP VIEW" in text_upper:
            sql_mock.collect.return_value = []
        else:
            try:
                rows = next(attempt_iter)
            except StopIteration:
                rows = []
            sql_mock.collect.return_value = rows
        return sql_mock

    session.sql.side_effect = _sql_side_effect
    return session


class TestTempAIFunctionInlineCallRows:
    """call_rows runs the inline CTE, retries failed rows, and tracks tokens."""

    def _make_inst(self, session):
        return TempAIFunction(
            session=session,
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="DB.S.TMP",
            candidate_model="claude-haiku-4-5",
            candidate_prompt="Classify.",
        )

    def test_no_create_function_sql_issued(self):
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "yes",
                        "ERROR": None,
                        "PROMPT_TOKENS": 10,
                        "COMPLETION_TOKENS": 3,
                    }
                ]
            ],
        )
        inst = self._make_inst(session)
        inst.call_rows([{"input_text": "hi"}])

        for call in session.sql.call_args_list:
            sql_text = call.args[0] if call.args else ""
            if isinstance(sql_text, str):
                assert "CREATE TEMPORARY FUNCTION" not in sql_text.upper()
                assert "CREATE FUNCTION" not in sql_text.upper()

    def test_preserves_row_order(self):
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "a-out",
                        "ERROR": None,
                        "PROMPT_TOKENS": 1,
                        "COMPLETION_TOKENS": 1,
                    },
                    {
                        "ROW_ID": 1,
                        "VALUE": "b-out",
                        "ERROR": None,
                        "PROMPT_TOKENS": 1,
                        "COMPLETION_TOKENS": 1,
                    },
                    {
                        "ROW_ID": 2,
                        "VALUE": "c-out",
                        "ERROR": None,
                        "PROMPT_TOKENS": 1,
                        "COMPLETION_TOKENS": 1,
                    },
                ]
            ]
        )
        inst = self._make_inst(session)
        out = inst.call_rows(
            [{"input_text": "a"}, {"input_text": "b"}, {"input_text": "c"}]
        )
        assert out == ["a-out", "b-out", "c-out"]

    def test_retries_transient_errors(self):
        # First attempt: row 1 errors transiently.  Second attempt: row 1 succeeds.
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "a-out",
                        "ERROR": None,
                        "PROMPT_TOKENS": 1,
                        "COMPLETION_TOKENS": 1,
                    },
                    {
                        "ROW_ID": 1,
                        "VALUE": None,
                        "ERROR": "transient",
                        "PROMPT_TOKENS": None,
                        "COMPLETION_TOKENS": None,
                    },
                ],
                [
                    {
                        "ROW_ID": 1,
                        "VALUE": "b-out",
                        "ERROR": None,
                        "PROMPT_TOKENS": 1,
                        "COMPLETION_TOKENS": 1,
                    }
                ],
            ]
        )
        inst = self._make_inst(session)
        out = inst.call_rows([{"input_text": "a"}, {"input_text": "b"}])
        assert out == ["a-out", "b-out"]

    def test_inference_error_after_max_attempts(self, monkeypatch):
        import snowflake_ai_optimize.core.temp_ai_function as utils

        monkeypatch.setattr(utils, "TEMP_AI_FUNCTION_MAX_ATTEMPTS", 2)

        # Both attempts fail.
        attempts: list[list[dict[str, object]]] = [
            [
                {
                    "ROW_ID": 0,
                    "VALUE": None,
                    "ERROR": "boom",
                    "PROMPT_TOKENS": None,
                    "COMPLETION_TOKENS": None,
                }
            ],
            [
                {
                    "ROW_ID": 0,
                    "VALUE": None,
                    "ERROR": "boom",
                    "PROMPT_TOKENS": None,
                    "COMPLETION_TOKENS": None,
                }
            ],
        ]
        session = _build_inline_session_mock(attempts=attempts)
        inst = self._make_inst(session)
        out = inst.call_rows([{"input_text": "a"}])
        assert isinstance(out[0], str)
        assert out[0].startswith("INFERENCE_ERROR:")

    def test_applies_dict_accessor(self):
        """When the original DDL has :label::VARCHAR accessor, dict
        results are unwrapped to the matching field.
        """  # noqa: D205
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": {"label": "positive"},
                        "ERROR": None,
                        "PROMPT_TOKENS": 4,
                        "COMPLETION_TOKENS": 2,
                    }
                ]
            ]
        )
        inst = self._make_inst(session)
        out = inst.call_rows([{"input_text": "great movie"}])
        assert out == ["positive"]

    def test_tokens_pushed_to_active_tracker(self):
        from snowflake_ai_optimize.core.timing import (
            TimingTracker,
            get_active_tracker,
            set_active_tracker,
        )

        tracker = TimingTracker()
        set_active_tracker(tracker)
        try:
            session = _build_inline_session_mock(
                attempts=[
                    [
                        {
                            "ROW_ID": 0,
                            "VALUE": "a",
                            "ERROR": None,
                            "PROMPT_TOKENS": 100,
                            "COMPLETION_TOKENS": 50,
                        },
                        {
                            "ROW_ID": 1,
                            "VALUE": "b",
                            "ERROR": None,
                            "PROMPT_TOKENS": 30,
                            "COMPLETION_TOKENS": 20,
                        },
                    ]
                ]
            )
            inst = self._make_inst(session)
            inst.call_rows([{"input_text": "x"}, {"input_text": "y"}])

            assert get_active_tracker() is tracker
            # Token sum: 100+30=130 prompt, 50+20=70 completion.
            assert tracker.total_udf_prompt_tokens == 130
            assert tracker.total_udf_completion_tokens == 70
        finally:
            set_active_tracker(None)

    def test_empty_rows_short_circuits(self):
        from unittest.mock import MagicMock

        session = MagicMock()
        inst = TempAIFunction(
            session=session,
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="DB.S.TMP",
            candidate_model="claude-haiku-4-5",
            candidate_prompt="Classify.",
        )
        # Reset call history from the construction (which builds inline_expr
        # but doesn't issue any session.sql).
        session.reset_mock()
        out = inst.call_rows([])
        assert out == []
        assert session.sql.call_count == 0


class TestTempAIFunctionInlineSemiStructured:
    """Input normalization (json.dumps on list/dict values for semi-structured
    params) is preserved by the inline-eval migration; PARSE_JSON wrapping
    moves into the CTE input projection.
    """  # noqa: D205

    def _make_inst(self, session, *, semi_structured_params=None):
        inst = TempAIFunction(
            session=session,
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="DB.S.TMP",
            candidate_model="m",
            candidate_prompt="p",
        )
        if semi_structured_params is not None:
            inst._semi_structured_params = semi_structured_params
        return inst

    def test_list_values_json_serialized_before_create_dataframe(self):
        import json

        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        inst = self._make_inst(session, semi_structured_params={"CATEGORIES"})
        inst.call_rows([{"TEXT": "hi", "CATEGORIES": ["A", "B"]}])

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0]["CATEGORIES"] == json.dumps(["A", "B"])
        assert created_rows[0]["TEXT"] == "hi"

    def test_dict_values_json_serialized(self):
        import json

        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        inst = self._make_inst(session, semi_structured_params={"PAYLOAD"})
        inst.call_rows([{"TEXT": "x", "PAYLOAD": {"k": "v"}}])

        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0]["PAYLOAD"] == json.dumps({"k": "v"})

    def test_parse_json_appears_in_cte_input_projection(self):
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        inst = self._make_inst(session, semi_structured_params={"PAYLOAD"})
        inst.call_rows([{"TEXT": "x", "PAYLOAD": '["a"]'}])

        # Find the main CTE SQL (skip the DROP VIEW cleanup at the end).
        cte_sql = None
        for call in session.sql.call_args_list:
            sql_text = call.args[0] if call.args else ""
            if isinstance(sql_text, str) and "WITH __ai_call AS" in sql_text:
                cte_sql = sql_text
                break

        assert cte_sql is not None, "expected to find the CTE SQL"
        assert "PARSE_JSON(PAYLOAD)" in cte_sql

    def test_no_parse_json_when_params_empty(self):
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        # No semi-structured params declared.
        inst = self._make_inst(session)
        inst.call_rows([{"TEXT": "hi", "CATEGORIES": ["A", "B"]}])

        cte_sql = None
        for call in session.sql.call_args_list:
            sql_text = call.args[0] if call.args else ""
            if isinstance(sql_text, str) and "WITH __ai_call AS" in sql_text:
                cte_sql = sql_text
                break
        assert cte_sql is not None
        assert "PARSE_JSON" not in cte_sql.upper()

        # Lists pass through unchanged when no semi-structured param is declared.
        created_rows = session.create_dataframe.call_args[0][0]
        assert created_rows[0]["CATEGORIES"] == ["A", "B"]

    def test_file_param_with_per_row_stage(self):
        """FILE params with a per-row __STAGE_<c> companion column get
        wrapped with ``TO_FILE(__STAGE_<c>, <c>) AS <c>`` in the CTE's
        input projection.  This is the multimodal path used when each
        row's file lives in a different stage (e.g. user-uploaded files).
        """  # noqa: D205
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        inst = self._make_inst(session)
        # No _file_type_params declared because the per-row __STAGE_<c>
        # companion-column path takes precedence over the static-stage
        # path in ``_build_input_view_projection_sql``.
        inst.call_rows(
            [
                {
                    "image_path": "img1.jpg",
                    "__STAGE_image_path": "@DB.S.STAGE",
                }
            ]
        )

        cte_sql = None
        for call in session.sql.call_args_list:
            sql_text = call.args[0] if call.args else ""
            if isinstance(sql_text, str) and "WITH __ai_call AS" in sql_text:
                cte_sql = sql_text
                break

        assert cte_sql is not None
        # Per-row stage column reference (no quotes around the stage name).
        assert "TO_FILE(__STAGE_image_path, image_path) AS image_path" in cte_sql
        # The __STAGE_<c> companion column itself is NOT projected into the
        # body's scope; it only feeds the TO_FILE wrap.
        # (Body's references to "image_path" resolve to the FILE-typed
        # projection above, not the raw VARCHAR path string.)

    def test_file_param_with_static_stage(self):
        """FILE params declared in the function signature AND with a static
        ``self._stage_name`` get wrapped with ``TO_FILE('<stage>', <c>) AS <c>``.
        This is the multimodal path used when all rows share one stage.
        """  # noqa: D205
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        inst = self._make_inst(session)
        inst._file_type_params = {"DOC"}
        inst._stage_name = "@DB.SCHEMA.AI_FUNCTIONS"
        inst.call_rows([{"doc": "doc1.pdf"}])

        cte_sql = None
        for call in session.sql.call_args_list:
            sql_text = call.args[0] if call.args else ""
            if isinstance(sql_text, str) and "WITH __ai_call AS" in sql_text:
                cte_sql = sql_text
                break

        assert cte_sql is not None
        assert "TO_FILE('@DB.SCHEMA.AI_FUNCTIONS', doc) AS doc" in cte_sql

    def test_file_param_show_details_still_injected(self):
        """Multimodal calls also get ``show_details=>TRUE`` injected so
        token tracking works regardless of FILE input vs scalar input.
        """  # noqa: D205
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        inst = self._make_inst(session)
        inst._file_type_params = {"DOC"}
        inst._stage_name = "@DB.SCHEMA.AI_FUNCTIONS"
        inst.call_rows([{"doc": "doc1.pdf"}])

        # The inline expression (used inside the CTE) carries
        # ``show_details=>TRUE`` for token capture even on multimodal
        # function bodies.
        assert "show_details=>TRUE" in inst.inline_expr

    def test_cte_coalesces_three_response_shapes(self):
        """Per the Snowflake AI_COMPLETE docs, the show_details=TRUE response
        shape varies based on whether response_format is set:

          * No response_format → ``choices[0]:messages``
          * With response_format → ``structured_output[0]:raw_message``

        Functions with ``response_format`` (structured JSON outputs) are
        common in production — they're how ``create_udf.py`` generates
        multi-field outputs.  The CTE's VALUE projection must COALESCE
        through both Snowflake-native paths plus the OpenAI-style fallback
        so a single SQL handles every documented response shape.

        Regression: pre-fix, only ``choices[0]:messages`` was projected,
        which is NULL for any function declaring response_format, leading
        to scores of 0 across all candidates.
        """  # noqa: D205, D415
        session = _build_inline_session_mock(
            attempts=[
                [
                    {
                        "ROW_ID": 0,
                        "VALUE": "ok",
                        "ERROR": None,
                        "PROMPT_TOKENS": 0,
                        "COMPLETION_TOKENS": 0,
                    }
                ]
            ]
        )
        inst = self._make_inst(session)
        inst.call_rows([{"TEXT": "hi"}])

        cte_sql = None
        for call in session.sql.call_args_list:
            sql_text = call.args[0] if call.args else ""
            if isinstance(sql_text, str) and "WITH __ai_call AS" in sql_text:
                cte_sql = sql_text
                break

        assert cte_sql is not None
        # All three documented response paths must appear in the SELECT.
        assert "__RES:value:choices[0]:messages" in cte_sql
        assert "__RES:value:choices[0]:message:content" in cte_sql
        assert "__RES:value:structured_output[0]:raw_message" in cte_sql
        assert "COALESCE(" in cte_sql


class TestPersistenceShowDetailsFreePrompt:
    """Persisted prompt-mode strings never contain show_details / __details / :choices[0].

    Prompt mode's user-facing output is a SYSTEM PROMPT string (returned
    as ``overall_best_prompt``).  There is NO reconstructed deploy DDL in
    prompt mode — the user re-runs their own CREATE FUNCTION with the
    optimized prompt substituted in.  The leakage risk is therefore
    near-zero, but we still verify that:

    * The candidate prompt passed in is preserved verbatim by TempAIFunction.
    * ``self.ddl`` and ``self.inline_expr`` MAY contain ``show_details``
      etc. — they are session-internal build artifacts, never persisted
      to experiments or returned to the SPROC caller.
    * The ``function_impl`` param written to experiments contains only
      the candidate prompt text, never inline-eval bookkeeping.
    """  # noqa: W505

    SAMPLE_PROMPT = "Be concise; classify the sentiment as positive or negative."

    def test_candidate_prompt_text_preserved(self):
        """The candidate_prompt argument is stored verbatim — show_details
        injection happens at the SQL-expression level, not on the prompt
        string itself.
        """  # noqa: D205
        from unittest.mock import MagicMock

        session = MagicMock()
        inst = TempAIFunction(
            session=session,
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="DB.S.TMP",
            candidate_model="claude-haiku-4-5",
            candidate_prompt=self.SAMPLE_PROMPT,
        )

        for forbidden in ("show_details", "__details", "__RES", ":choices[0]"):
            assert forbidden not in inst.candidate_prompt, (
                f"candidate_prompt leaked {forbidden!r}: {inst.candidate_prompt!r}"
            )
        # And the exact text survives unchanged.
        assert inst.candidate_prompt == self.SAMPLE_PROMPT

    def test_build_inline_expr_does_not_mutate_inputs(self):
        """Building a TempAIFunction leaves the input model/prompt strings
        unchanged (the transformation operates on copies of the body).
        """  # noqa: D205
        from unittest.mock import MagicMock

        model_in = "claude-haiku-4-5"
        prompt_in = self.SAMPLE_PROMPT
        model_before, prompt_before = model_in, prompt_in

        TempAIFunction(
            session=MagicMock(),
            function_def=_fn_of(SAMPLE_PROMPT_DDL),
            temp_function_name="__INLINE",
            candidate_model=model_in,
            candidate_prompt=prompt_in,
        )

        assert model_in == model_before
        assert prompt_in == prompt_before

    def test_build_run_params_filters_internal_artifacts(self):
        """build_run_params receives the candidate prompt as
        ``function_impl`` (a user-visible param).  None of the
        inline-eval bookkeeping leaks into this param.
        """  # noqa: D205
        from snowflake_ai_optimize.core.run_params import RunParams

        params = RunParams(
            function_impl=self.SAMPLE_PROMPT,
            model="claude-haiku-4-5",
            iteration="3",
            # Token totals come from the show_details-injected SQL but live
            # in a separate param, not in function_impl.
            total_udf_prompt_tokens=100,
            total_udf_completion_tokens=50,
        ).to_param_list()
        impl_param = next(p for p in params if p["name"] == "function_impl")

        for forbidden in ("show_details", "__details", "__RES", ":choices[0]"):
            assert forbidden not in impl_param["value"], (
                f"function_impl param leaked {forbidden!r}: {impl_param['value']!r}"
            )
        # Token params ARE present (only written when non-None) and carry
        # the numbers we passed in.
        token_p = next(p for p in params if p["name"] == "total_udf_prompt_tokens")
        token_c = next(p for p in params if p["name"] == "total_udf_completion_tokens")
        assert token_p["value"] == "100"
        assert token_c["value"] == "50"
