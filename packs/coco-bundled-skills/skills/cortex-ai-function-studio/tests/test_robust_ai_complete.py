# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for RobustAIComplete, customai_query_tag_logging, build_temp_function_name.

Run:
    uv run --group test pytest tests/test_robust_ai_complete.py -v
"""  # noqa: W505

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

import snowflake_ai_optimize.core.session as core_session
from snowflake_ai_optimize.core.session import (
    RobustAIComplete,
    custom_ai_query_tag_logging,
)
from snowflake_ai_optimize.core.sql_utils import build_temp_function_name


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed for unit tests."""
    yield


class _FakeExpr:
    def __init__(self, kind: str, *args: object):
        self.kind = kind
        self.args = args
        self.alias_name: str | None = None

    def alias(self, alias_name: str):
        aliased = _FakeExpr(self.kind, *self.args)
        aliased.alias_name = alias_name
        return aliased


class _FakeDataFrame:
    def __init__(self):
        self.select_calls: list[tuple[object, ...]] = []
        self.order_by_calls: list[tuple[object, ...]] = []

    def select(self, *args: object):
        self.select_calls.append(args)
        return self

    def order_by(self, *args: object):
        self.order_by_calls.append(args)
        return self

    def collect(self):
        return [{"RESPONSE": "{}"}]


# ---------------------------------------------------------------------------
# Phase 2.1 — RobustAIComplete
# ---------------------------------------------------------------------------


class TestParseJson:
    """Tests for RobustAIComplete._parse_json."""

    def test_valid_json_string(self):
        result = RobustAIComplete._parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_dict_passthrough(self):
        d = {"already": "parsed"}
        result = RobustAIComplete._parse_json(d)
        assert result is d

    def test_list_passthrough(self):
        lst = [1, 2, 3]
        result = RobustAIComplete._parse_json(lst)
        assert result is lst

    def test_empty_string_returns_none(self):
        assert RobustAIComplete._parse_json("") is None
        assert RobustAIComplete._parse_json("   ") is None

    def test_non_json_string_raises(self):
        with pytest.raises(json.JSONDecodeError):
            RobustAIComplete._parse_json("not json at all")

    def test_none_passthrough(self):
        assert RobustAIComplete._parse_json(None) is None

    def test_integer_passthrough(self):
        assert RobustAIComplete._parse_json(42) == 42


class TestParseAICompletePayload:
    """Tests for RobustAIComplete.parse_ai_complete_payload."""

    def test_plain_json_string(self):
        result = RobustAIComplete.parse_ai_complete_payload('{"answer": 42}')
        assert result == {"answer": 42}

    def test_none_input(self):
        # _parse_json returns None for None, then early return
        assert RobustAIComplete.parse_ai_complete_payload(None) is None

    def test_detail_wrapped_value(self):
        payload = json.dumps({"value": '{"answer": 42}', "error": None})
        result = RobustAIComplete.parse_ai_complete_payload(payload)
        assert result == {"answer": 42}

    def test_detail_wrapped_error_raises(self):
        payload = json.dumps({"value": None, "error": "Something went wrong"})
        with pytest.raises(RuntimeError, match="Something went wrong"):
            RobustAIComplete.parse_ai_complete_payload(payload)

    def test_dict_passthrough_no_value_key(self):
        d = {"answer": 42}
        result = RobustAIComplete.parse_ai_complete_payload(d)
        assert result == {"answer": 42}

    def test_detail_wrapped_empty_error_unwraps(self):
        """Error key present but empty string → treated as no error."""
        payload = json.dumps({"value": '{"data": 1}', "error": ""})
        result = RobustAIComplete.parse_ai_complete_payload(payload)
        assert result == {"data": 1}


class TestExtractBalancedSubstring:
    """Tests for RobustAIComplete._extract_balanced_substring."""

    def test_simple_braces(self):
        result = RobustAIComplete._extract_balanced_substring(
            'abc{"key": 1}def', "{", "}"
        )
        assert result == '{"key": 1}'

    def test_nested_braces(self):
        result = RobustAIComplete._extract_balanced_substring(
            'x{"a": {"b": 1}}y', "{", "}"
        )
        assert result == '{"a": {"b": 1}}'

    def test_no_opening_brace(self):
        assert (
            RobustAIComplete._extract_balanced_substring("no braces", "{", "}") is None
        )

    def test_unbalanced_braces(self):
        assert (
            RobustAIComplete._extract_balanced_substring("{unclosed", "{", "}") is None
        )

    def test_braces_inside_strings_ignored(self):
        text = '{"key": "val with { inside"}'
        result = RobustAIComplete._extract_balanced_substring(text, "{", "}")
        assert result == text

    def test_brackets(self):
        result = RobustAIComplete._extract_balanced_substring("pre[1, 2]post", "[", "]")
        assert result == "[1, 2]"


class TestIsJsonModeValidationError:
    """Tests for RobustAIComplete.is_json_mode_validation_error."""

    def test_known_marker_matches(self):
        assert RobustAIComplete.is_json_mode_validation_error(
            "JSON mode output validation error: bad schema"
        )

    def test_case_insensitive(self):
        assert RobustAIComplete.is_json_mode_validation_error("INVALID JSON response")

    def test_unrelated_message_no_match(self):
        assert not RobustAIComplete.is_json_mode_validation_error("Connection timeout")

    def test_eof_marker(self):
        assert RobustAIComplete.is_json_mode_validation_error(
            "Error: eof while parsing a value"
        )


class TestIsReturnDetailsNotAllowedError:
    """Tests for RobustAIComplete._is_return_details_not_allowed_error."""

    def test_both_markers_present(self):
        exc = Exception(
            "return details is not allowed when "
            "ai_sql_error_handling_use_fail_on_error is set"
        )
        assert RobustAIComplete._is_return_details_not_allowed_error(exc)

    def test_only_first_marker(self):
        exc = Exception("return details is not allowed")
        assert not RobustAIComplete._is_return_details_not_allowed_error(exc)

    def test_only_second_marker(self):
        exc = Exception("ai_sql_error_handling_use_fail_on_error is set")
        assert not RobustAIComplete._is_return_details_not_allowed_error(exc)

    def test_neither_marker(self):
        exc = Exception("Something else entirely")
        assert not RobustAIComplete._is_return_details_not_allowed_error(exc)


class TestCallAIComplete:
    """Tests for RobustAIComplete.call_ai_complete with mocked internals."""

    @pytest.fixture(autouse=True)
    def _reset_class_state(self):
        """Reset class-level state before each test."""
        RobustAIComplete._error_mode_init_attempted = False
        RobustAIComplete._can_use_error_details_mode = False
        yield
        RobustAIComplete._error_mode_init_attempted = False
        RobustAIComplete._can_use_error_details_mode = False

    @patch.object(RobustAIComplete, "_execute_ai_complete")
    @patch.object(RobustAIComplete, "_initialize_error_mode_once")
    def test_happy_path_no_error_details(self, mock_init, mock_exec):
        """Without error details mode, returns parsed JSON responses."""
        mock_exec.return_value = ['{"answer": 42}']
        session = MagicMock()

        result = RobustAIComplete.call_ai_complete(
            session, "model", ["prompt"], 0.0, 100, None
        )

        assert result == [{"answer": 42}]
        mock_exec.assert_called_once()

    @patch.object(RobustAIComplete, "_execute_ai_complete")
    @patch.object(RobustAIComplete, "_initialize_error_mode_once")
    def test_error_details_mode(self, mock_init, mock_exec):
        """With error details mode enabled, unwraps {value} from response."""
        RobustAIComplete._can_use_error_details_mode = True
        RobustAIComplete._error_mode_init_attempted = True
        mock_exec.return_value = [json.dumps({"value": {"answer": 42}, "error": None})]
        session = MagicMock()

        result = RobustAIComplete.call_ai_complete(
            session, "model", ["prompt"], 0.0, 100, None
        )

        assert result == [{"answer": 42}]

    @patch.object(RobustAIComplete, "_execute_ai_complete")
    @patch.object(RobustAIComplete, "_initialize_error_mode_once")
    def test_fallback_on_permission_error(self, mock_init, mock_exec):
        """Falls back to non-details mode on permission error."""
        RobustAIComplete._can_use_error_details_mode = True
        RobustAIComplete._error_mode_init_attempted = True

        permission_error = Exception(
            "return details is not allowed when "
            "ai_sql_error_handling_use_fail_on_error is set"
        )
        mock_exec.side_effect = [permission_error, ['{"answer": 1}']]
        session = MagicMock()

        result = RobustAIComplete.call_ai_complete(
            session, "model", ["prompt"], 0.0, 100, None
        )

        assert result == [{"answer": 1}]
        assert not RobustAIComplete._can_use_error_details_mode

    @patch.object(RobustAIComplete, "_execute_ai_complete")
    @patch.object(RobustAIComplete, "_initialize_error_mode_once")
    def test_empty_response_returns_none(self, mock_init, mock_exec):
        mock_exec.return_value = []
        session = MagicMock()

        result = RobustAIComplete.call_ai_complete(
            session, "model", ["prompt"], 0.0, 100, None
        )

        assert result is None


class TestExecuteAIComplete:
    def test_multimodal_requires_both_file_paths_and_stage_name(self):
        session = MagicMock()

        with pytest.raises(
            ValueError, match="file_paths and stage_name must be provided together"
        ):
            RobustAIComplete._execute_ai_complete(
                session=session,
                model="gemini-2.5-flash",
                user_prompts=["Judge the prediction"],
                temperature=0.0,
                max_tokens=256,
                response_schema=None,
                include_error_details=False,
                file_paths=["images/example.png"],
            )

        with pytest.raises(
            ValueError, match="file_paths and stage_name must be provided together"
        ):
            RobustAIComplete._execute_ai_complete(
                session=session,
                model="gemini-2.5-flash",
                user_prompts=["Judge the prediction"],
                temperature=0.0,
                max_tokens=256,
                response_schema=None,
                include_error_details=False,
                stage_name="@DB.SCH.STAGE",
            )

    def test_multimodal_rejects_file_path_length_mismatch(self):
        session = MagicMock()

        with pytest.raises(ValueError, match="file_paths length \\(1\\) must match"):
            RobustAIComplete._execute_ai_complete(
                session=session,
                model="gemini-2.5-flash",
                user_prompts=["Judge the prediction", "Judge the fallback"],
                temperature=0.0,
                max_tokens=256,
                response_schema=None,
                include_error_details=False,
                file_paths=["images/example.png"],
                stage_name="@DB.SCH.STAGE",
            )

    def test_multimodal_rejects_per_row_stage_length_mismatch(self):
        session = MagicMock()

        with pytest.raises(ValueError, match="stage_name length \\(1\\) must match"):
            RobustAIComplete._execute_ai_complete(
                session=session,
                model="gemini-2.5-flash",
                user_prompts=["Judge the prediction", "Judge the fallback"],
                temperature=0.0,
                max_tokens=256,
                response_schema=None,
                include_error_details=False,
                file_paths=["images/example.png", "images/fallback.png"],
                stage_name=["@DB.SCH.STAGE_A"],
            )

    def test_multimodal_uses_file_first_prompt_shape(self):
        session = MagicMock()
        fake_df = _FakeDataFrame()
        session.create_dataframe.return_value = fake_df

        def _fake_call_function(name: str, *args: object):
            return _FakeExpr("call_function", name, *args)

        with (
            patch.object(
                core_session,
                "call_function",
                side_effect=_fake_call_function,
            ) as mock_call_function,
            patch.object(
                core_session,
                "col",
                side_effect=lambda name: _FakeExpr("col", name),
            ),
            patch.object(
                core_session,
                "lit",
                side_effect=lambda value: _FakeExpr("lit", value),
            ),
            patch.object(
                core_session,
                "object_construct",
                side_effect=lambda *args: _FakeExpr("object_construct", *args),
            ),
            patch.object(
                core_session,
                "array_construct",
                side_effect=lambda *args: _FakeExpr("array_construct", *args),
            ),
            patch.object(
                core_session,
                "parse_json",
                side_effect=lambda value: _FakeExpr("parse_json", value),
            ),
        ):
            RobustAIComplete._execute_ai_complete(
                session=session,
                model="gemini-2.5-flash",
                user_prompts=["Judge the prediction"],
                temperature=0.0,
                max_tokens=256,
                response_schema=None,
                include_error_details=False,
                file_paths=["images/example.png"],
                stage_name="@DB.SCH.STAGE",
            )

        prompt_call = next(
            call
            for call in mock_call_function.call_args_list
            if call.args[0] == "PROMPT"
        )
        template_expr = prompt_call.args[1]
        file_expr = prompt_call.args[2]
        text_expr = prompt_call.args[3]

        assert template_expr.kind == "lit"
        assert template_expr.args == ("file: {0} {1}",)
        assert file_expr.kind == "call_function"
        assert file_expr.args[0] == "TO_FILE"
        assert file_expr.args[1].kind == "lit"
        assert file_expr.args[1].args == ("@DB.SCH.STAGE",)
        assert file_expr.args[2].kind == "col"
        assert file_expr.args[2].args == ("FILE_PATH_COL",)
        assert text_expr.kind == "col"
        assert text_expr.args == ("PROMPT_EXPR_COL",)

        create_df_call = session.create_dataframe.call_args
        assert create_df_call.args[0] == [
            [0, "Judge the prediction", "images/example.png"]
        ]
        assert create_df_call.kwargs["schema"] == [
            "IDX",
            "PROMPT_EXPR_COL",
            "FILE_PATH_COL",
        ]

    def test_multimodal_uses_per_row_stage_column(self):
        session = MagicMock()
        fake_df = _FakeDataFrame()
        session.create_dataframe.return_value = fake_df

        def _fake_call_function(name: str, *args: object):
            return _FakeExpr("call_function", name, *args)

        with (
            patch.object(
                core_session,
                "call_function",
                side_effect=_fake_call_function,
            ) as mock_call_function,
            patch.object(
                core_session,
                "col",
                side_effect=lambda name: _FakeExpr("col", name),
            ),
            patch.object(
                core_session,
                "lit",
                side_effect=lambda value: _FakeExpr("lit", value),
            ),
            patch.object(
                core_session,
                "object_construct",
                side_effect=lambda *args: _FakeExpr("object_construct", *args),
            ),
            patch.object(
                core_session,
                "array_construct",
                side_effect=lambda *args: _FakeExpr("array_construct", *args),
            ),
            patch.object(
                core_session,
                "parse_json",
                side_effect=lambda value: _FakeExpr("parse_json", value),
            ),
        ):
            RobustAIComplete._execute_ai_complete(
                session=session,
                model="gemini-2.5-flash",
                user_prompts=["Judge the prediction", "Judge the fallback"],
                temperature=0.0,
                max_tokens=256,
                response_schema=None,
                include_error_details=False,
                file_paths=["images/example.png", "images/fallback.png"],
                stage_name=["@DB.SCH.STAGE_A", "@DB.SCH.STAGE_B"],
            )

        prompt_call = next(
            call
            for call in mock_call_function.call_args_list
            if call.args[0] == "PROMPT"
        )
        template_expr = prompt_call.args[1]
        file_expr = prompt_call.args[2]
        text_expr = prompt_call.args[3]

        assert template_expr.kind == "lit"
        assert template_expr.args == ("file: {0} {1}",)
        assert file_expr.kind == "call_function"
        assert file_expr.args[0] == "TO_FILE"
        assert file_expr.args[1].kind == "col"
        assert file_expr.args[1].args == ("STAGE_COL",)
        assert file_expr.args[2].kind == "col"
        assert file_expr.args[2].args == ("FILE_PATH_COL",)
        assert text_expr.kind == "col"
        assert text_expr.args == ("PROMPT_EXPR_COL",)

        create_df_call = session.create_dataframe.call_args
        assert create_df_call.args[0] == [
            [0, "Judge the prediction", "images/example.png", "@DB.SCH.STAGE_A"],
            [1, "Judge the fallback", "images/fallback.png", "@DB.SCH.STAGE_B"],
        ]
        assert create_df_call.kwargs["schema"] == [
            "IDX",
            "PROMPT_EXPR_COL",
            "FILE_PATH_COL",
            "STAGE_COL",
        ]


class TestRunAICompleteWithJsonFallback:
    """Tests for RobustAIComplete.run_ai_complete_with_json_fallback."""

    @patch.object(RobustAIComplete, "call_ai_complete")
    def test_strict_succeeds(self, mock_call):
        mock_call.return_value = [{"answer": 42}]
        session = MagicMock()

        result = RobustAIComplete.run_ai_complete_with_json_fallback(
            session, "model", "primary", "fallback", {"type": "object"}, 0.0, 100
        )

        assert result == {"answer": 42}
        assert mock_call.call_count == 1

    @patch.object(RobustAIComplete, "call_ai_complete")
    @patch.object(RobustAIComplete, "_parse_json", side_effect=lambda v: v)
    def test_strict_returns_none_triggers_fallback(self, mock_parse, mock_call):
        mock_call.side_effect = [None, [{"answer": "fallback"}]]
        session = MagicMock()

        RobustAIComplete.run_ai_complete_with_json_fallback(
            session, "model", "primary", "fallback", {"type": "object"}, 0.0, 100
        )

        assert mock_call.call_count == 2
        # Fallback call should have response_schema=None
        fallback_call = mock_call.call_args_list[1]
        assert fallback_call.kwargs.get("response_schema") is None

    @patch.object(RobustAIComplete, "call_ai_complete")
    @patch.object(RobustAIComplete, "_parse_json", side_effect=lambda v: v)
    def test_json_error_triggers_fallback(self, mock_parse, mock_call):
        mock_call.side_effect = [
            json.JSONDecodeError("bad", "", 0),
            [{"answer": "recovered"}],
        ]
        session = MagicMock()

        RobustAIComplete.run_ai_complete_with_json_fallback(
            session, "model", "primary", "fallback", {"type": "object"}, 0.0, 100
        )

        assert mock_call.call_count == 2

    @patch.object(RobustAIComplete, "call_ai_complete")
    def test_non_json_error_propagates(self, mock_call):
        mock_call.side_effect = RuntimeError("Network error")
        session = MagicMock()

        with pytest.raises(RuntimeError, match="Network error"):
            RobustAIComplete.run_ai_complete_with_json_fallback(
                session, "model", "primary", "fallback", {"type": "object"}, 0.0, 100
            )


# ---------------------------------------------------------------------------
# Phase 2.5 — Query tag logging and build_temp_function_name
# ---------------------------------------------------------------------------


class TestQueryTagLogging:
    """Tests for customai_query_tag_logging context manager."""

    def test_no_existing_tag(self):
        session = MagicMock()
        session.query_tag = ""

        with custom_ai_query_tag_logging(session, "my_suffix") as s:
            tag = json.loads(s.query_tag)
            assert "__CUSTOM_AI_FUNCTION_LOG_" in tag
            assert tag["__CUSTOM_AI_FUNCTION_LOG_"] == "my_suffix"

        # Restored
        assert session.query_tag == ""

    def test_existing_json_dict_tag(self):
        session = MagicMock()
        session.query_tag = '{"existing": "value"}'

        with custom_ai_query_tag_logging(session, "suffix") as s:
            tag = json.loads(s.query_tag)
            assert tag["existing"] == "value"
            assert "__CUSTOM_AI_FUNCTION_LOG_" in tag

        assert session.query_tag == '{"existing": "value"}'

    def test_existing_plain_string_tag(self):
        session = MagicMock()
        session.query_tag = "plain-tag"

        with custom_ai_query_tag_logging(session, "suffix") as s:
            assert "|" in s.query_tag
            assert "plain-tag" in s.query_tag

        assert session.query_tag == "plain-tag"

    def test_restores_on_exception(self):
        session = MagicMock()
        session.query_tag = "original"

        with pytest.raises(ValueError), custom_ai_query_tag_logging(session, "suffix"):
            raise ValueError("boom")

        assert session.query_tag == "original"


class TestBuildTempFunctionName:
    """Tests for build_temp_function_name."""

    @patch("threading.current_thread")
    def test_basic_format(self, mock_thread):
        mock_thread.return_value.ident = 12345
        result = build_temp_function_name("DB.SCHEMA.MY_FUNC", "__OPT_TEMP")
        assert result == "DB.SCHEMA.__OPT_TEMP_MY_FUNC_12345"

    @patch("threading.current_thread")
    def test_different_prefix(self, mock_thread):
        mock_thread.return_value.ident = 99
        result = build_temp_function_name("DB.SCHEMA.FUNC", "__OPT_TEST")
        assert result == "DB.SCHEMA.__OPT_TEST_FUNC_99"

    @patch("threading.current_thread")
    def test_strips_signature(self, mock_thread):
        mock_thread.return_value.ident = 1
        result = build_temp_function_name(
            "DB.SCHEMA.MY_FUNC(VARCHAR, INTEGER)", "__OPT_TEMP"
        )
        assert result == "DB.SCHEMA.__OPT_TEMP_MY_FUNC_1"
