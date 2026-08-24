# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for snowflake_ai_optimize.core.sql_utils.validate_dotted_identifier."""

import pytest

from snowflake_ai_optimize.core.sql_utils import (
    FunctionArg,
    FunctionDefinition,
    build_query_text_function_def,
    describe_function,
    parse_signature_args,
    parse_signature_param_names,
    resolve_param_name,
    validate_dotted_identifier,
)


class TestValidateDottedIdentifier:
    """Tests for validate_dotted_identifier."""

    # --- Valid bare identifiers ---

    def test_single_bare_identifier(self):
        result = validate_dotted_identifier("MY_FUNC")
        assert result == "MY_FUNC"

    def test_two_part_bare_identifier(self):
        result = validate_dotted_identifier("SCHEMA.FUNC")
        assert result == "SCHEMA.FUNC"

    def test_three_part_bare_identifier(self):
        result = validate_dotted_identifier("DB.SCHEMA.FUNC")
        assert result == "DB.SCHEMA.FUNC"

    def test_identifier_with_dollar(self):
        result = validate_dotted_identifier("MY$VAR")
        assert result == "MY$VAR"

    def test_identifier_starts_with_underscore(self):
        result = validate_dotted_identifier("_private.SCHEMA.FUNC")
        assert result == "_private.SCHEMA.FUNC"

    # --- Valid quoted identifiers ---

    def test_quoted_single_part(self):
        result = validate_dotted_identifier('"my-func"')
        assert result == '"my-func"'

    def test_quoted_with_spaces(self):
        result = validate_dotted_identifier('"my database"."my schema"."my func"')
        assert result == '"my database"."my schema"."my func"'

    def test_quoted_with_escaped_quotes(self):
        result = validate_dotted_identifier('"say ""hello"""')
        assert result == '"say ""hello"""'

    def test_mixed_bare_and_quoted(self):
        result = validate_dotted_identifier('DB."my-schema".FUNC')
        assert result == 'DB."my-schema".FUNC'

    # --- quote=True output ---

    def test_quote_bare_single(self):
        result = validate_dotted_identifier("FUNC", quote=True)
        assert result == '"FUNC"'

    def test_quote_bare_three_part(self):
        result = validate_dotted_identifier("DB.SCHEMA.FUNC", quote=True)
        assert result == '"DB"."SCHEMA"."FUNC"'

    def test_quote_already_quoted(self):
        result = validate_dotted_identifier('"my-db".SCHEMA.FUNC', quote=True)
        assert result == '"my-db"."SCHEMA"."FUNC"'

    def test_quote_escaped_inner_quotes(self):
        # Input: "say ""hi""" — inner logical value is: say "hi"
        # Output should double-quote that: "say ""hi"""
        result = validate_dotted_identifier('"say ""hi"""', quote=True)
        assert result == '"say ""hi"""'

    # --- max_parts enforcement ---

    def test_max_parts_1_accepts_single(self):
        result = validate_dotted_identifier("DB", max_parts=1)
        assert result == "DB"

    def test_max_parts_1_rejects_dotted(self):
        with pytest.raises(ValueError, match="1-1 part"):
            validate_dotted_identifier("DB.SCHEMA", max_parts=1)

    def test_min_parts_2_rejects_single(self):
        with pytest.raises(ValueError, match="2-3 part"):
            validate_dotted_identifier("FUNC", min_parts=2)

    def test_too_many_parts(self):
        with pytest.raises(ValueError, match="got 4 parts"):
            validate_dotted_identifier("A.B.C.D")

    # --- Invalid inputs ---

    def test_empty_string(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_dotted_identifier("")

    def test_whitespace_only(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_dotted_identifier("   ")

    def test_none_input(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_dotted_identifier(None)  # type: ignore[arg-type]

    def test_integer_input(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_dotted_identifier(123)  # type: ignore[arg-type]

    def test_invalid_bare_identifier_with_hyphen(self):
        with pytest.raises(ValueError, match="Invalid identifier"):
            validate_dotted_identifier("my-func")

    def test_invalid_bare_starts_with_number(self):
        with pytest.raises(ValueError, match="Invalid identifier"):
            validate_dotted_identifier("123abc")

    def test_empty_part_in_dotted(self):
        with pytest.raises(ValueError, match="Empty identifier part"):
            validate_dotted_identifier("DB..FUNC")

    def test_sql_injection_attempt(self):
        with pytest.raises(ValueError, match="Invalid identifier"):
            validate_dotted_identifier("FOO; DROP DATABASE PROD; --")

    # --- Unterminated quotes ---

    def test_unterminated_quote(self):
        with pytest.raises(ValueError, match="Unterminated quoted"):
            validate_dotted_identifier('"open_quote')

    def test_unterminated_quote_in_dotted(self):
        with pytest.raises(ValueError, match="Unterminated quoted"):
            validate_dotted_identifier('DB."open')

    # --- Unescaped interior quotes ---

    def test_unescaped_interior_quote(self):
        # Odd number of quotes means the parser sees it as unterminated
        with pytest.raises(ValueError, match="Unterminated quoted"):
            validate_dotted_identifier('"foo"bar"')

    def test_unescaped_interior_quote_even(self):
        # Even quotes but invalid escaping inside: "ab"cd" has inner ab"cd
        # which contains an unescaped quote
        with pytest.raises(ValueError, match="unescaped quote"):
            validate_dotted_identifier('"ab""cd"e"f"')

    # --- Whitespace handling ---

    def test_strips_outer_whitespace(self):
        result = validate_dotted_identifier("  MY_FUNC  ")
        assert result == "MY_FUNC"

    def test_strips_part_whitespace(self):
        result = validate_dotted_identifier("DB . SCHEMA . FUNC")
        assert result == "DB . SCHEMA . FUNC"

    # --- kind parameter in errors ---

    def test_kind_appears_in_error(self):
        with pytest.raises(ValueError, match="experiment_name cannot be empty"):
            validate_dotted_identifier("", kind="experiment_name")

    def test_kind_in_unterminated_error(self):
        with pytest.raises(ValueError, match="Unterminated quoted UDF name"):
            validate_dotted_identifier('"bad', kind="UDF name")


class TestParseSignatureParamNames:
    """Tests for parse_signature_param_names (DESCRIBE FUNCTION signature)."""

    def test_simple(self):
        # DESCRIBE FUNCTION returns the signature wrapped in parentheses.
        assert parse_signature_param_names("(ARG1 VARCHAR, ARG2 INT)") == [
            "ARG1",
            "ARG2",
        ]

    def test_type_with_comma(self):
        # NUMBER(38,0) has an inner comma that must not split the param list.
        assert parse_signature_param_names("(a NUMBER(38,0), b NUMBER(10,2))") == [
            "a",
            "b",
        ]

    def test_quoted_param_name(self):
        assert parse_signature_param_names('("My Arg" VARCHAR, ARG2 INT)') == [
            "My Arg",
            "ARG2",
        ]

    def test_no_params(self):
        assert parse_signature_param_names("()") == []

    def test_bare_list_without_parens(self):
        assert parse_signature_param_names("a NUMBER, b NUMBER") == ["a", "b"]


class TestResolveParamName:
    """Tests for resolve_param_name."""

    def test_positional_resolves(self):
        assert resolve_param_name("$1", ["arg1", "arg2"]) == "arg1"
        assert resolve_param_name("$2", ["arg1", "arg2"]) == "arg2"

    def test_named_resolves_case_insensitively_to_ddl_casing(self):
        # Exact match returns the DDL's casing...
        assert resolve_param_name("arg2", ["arg1", "arg2"]) == "arg2"
        # ...and a case-differing key resolves to the DDL parameter's casing so
        # a quoted alias (`col AS "TEXT"`) matches the inlined body's `TEXT`.
        assert resolve_param_name("text", ["TEXT", "LABEL"]) == "TEXT"
        assert resolve_param_name("QUESTION", ["question", "context"]) == "question"

    def test_named_without_match_falls_back(self):
        assert resolve_param_name("missing", ["arg1", "arg2"]) == "missing"

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            resolve_param_name("$3", ["arg1", "arg2"])

    def test_dollar_prefixed_name_is_not_positional(self):
        # A name that merely contains "$" (not "$<digits>") is a named arg.
        assert resolve_param_name("arg$1", ["arg1"]) == "arg$1"


class TestParseSignatureArgs:
    """Tests for parse_signature_args (DESCRIBE FUNCTION signature -> FunctionArg)."""

    def test_simple(self):
        args = parse_signature_args("(input_text VARCHAR, img FILE)")
        assert args == [
            FunctionArg("input_text", "VARCHAR"),
            FunctionArg("img", "FILE"),
        ]

    def test_type_with_comma(self):
        args = parse_signature_args("(a NUMBER(38,0), b NUMBER(10,2))")
        assert args == [
            FunctionArg("a", "NUMBER(38,0)"),
            FunctionArg("b", "NUMBER(10,2)"),
        ]

    def test_quoted_param_name(self):
        args = parse_signature_args('("My Arg" ARRAY)')
        assert args == [FunctionArg("My Arg", "ARRAY")]

    def test_no_params(self):
        assert parse_signature_args("()") == []


class _StubRow:
    """Mimics a Snowpark Row for DESCRIBE FUNCTION property rows (r[0], r[1])."""

    def __init__(self, key, value):
        self._vals = [key, value]

    def __getitem__(self, idx):
        return self._vals[idx]


class _StubSession:
    """Returns canned SHOW FUNCTIONS + DESCRIBE FUNCTION rows by query prefix."""

    def __init__(self, show_rows, describe_rows):
        self._show_rows = show_rows
        self._describe_rows = describe_rows

    def sql(self, query):
        self._last = query
        return self

    def collect(self):
        if self._last.upper().startswith("SHOW FUNCTIONS"):
            return self._show_rows
        return self._describe_rows


class _ShowRow(dict):
    """SHOW FUNCTIONS row supporting ["arguments"] subscript."""


class TestDescribeFunction:
    """Tests for describe_function (mock SHOW/DESCRIBE rows)."""

    def _session(self, *, arguments, describe_rows):
        show_rows = [_ShowRow(arguments=arguments)]
        return _StubSession(show_rows, describe_rows)

    def test_builds_definition(self):
        body = "AI_COMPLETE(model=>'m', prompt=>PROMPT('{0}', input_text))"
        session = self._session(
            arguments="F(VARCHAR) RETURN VARCHAR",
            describe_rows=[
                _StubRow("signature", "(input_text VARCHAR)"),
                _StubRow("returns", "VARCHAR"),
                _StubRow("language", "SQL"),
                _StubRow("body", body),
            ],
        )
        fn = describe_function(session, "DB.SCHEMA.F")
        assert fn.name == "DB.SCHEMA.F"
        assert fn.args == [FunctionArg("input_text", "VARCHAR")]
        assert fn.arg_names == ["input_text"]
        assert fn.returns == "VARCHAR"
        assert fn.language == "SQL"
        assert fn.body == body
        assert fn.signature == "(input_text VARCHAR)"
        assert fn.typed_signature == "DB.SCHEMA.F(VARCHAR)"

    def test_missing_body_raises(self):
        session = self._session(
            arguments="F(VARCHAR) RETURN VARCHAR",
            describe_rows=[
                _StubRow("signature", "(input_text VARCHAR)"),
                _StubRow("returns", "VARCHAR"),
                _StubRow("language", "SQL"),
                _StubRow("body", ""),
            ],
        )
        with pytest.raises(ValueError, match="readable body"):
            describe_function(session, "DB.SCHEMA.F")

    def test_function_not_found_raises(self):
        session = _StubSession([], [])
        with pytest.raises(ValueError, match="Function not found"):
            describe_function(session, "DB.SCHEMA.MISSING")


class TestRenderCreateDdl:
    """Tests for FunctionDefinition.render_create_ddl round-trips."""

    def _fn(self, **props):
        base = {
            "signature": "(input_text VARCHAR)",
            "returns": "VARCHAR",
            "language": "SQL",
        }
        base.update(props)
        return FunctionDefinition(
            name="DB.SCHEMA.F",
            args=parse_signature_args(base["signature"]),
            returns=base["returns"],
            language=base["language"],
            body="AI_COMPLETE(model=>'m', prompt=>'p')",
            properties=base,
        )

    def test_default_render(self):
        ddl = self._fn().render_create_ddl()
        assert ddl.startswith(
            "CREATE OR REPLACE FUNCTION DB.SCHEMA.F(input_text VARCHAR)"
        )
        assert "RETURNS VARCHAR" in ddl
        assert "LANGUAGE SQL" in ddl
        assert "$$\nAI_COMPLETE(model=>'m', prompt=>'p')\n$$" in ddl

    def test_body_override_is_literal(self):
        # A body with a backslash escape must be inserted literally (no re.sub
        # backslash-group interpretation).
        body = r"REGEXP_REPLACE(x, '\d+', '')"
        ddl = self._fn().render_create_ddl(body=body)
        assert body in ddl

    def test_temp_and_name_override(self):
        ddl = self._fn().render_create_ddl(
            name="DB.SCHEMA.__TMP", temporary=True, body="SELECT 1"
        )
        assert "CREATE OR REPLACE TEMPORARY FUNCTION DB.SCHEMA.__TMP" in ddl
        assert "$$\nSELECT 1\n$$" in ddl

    def test_returns_override(self):
        ddl = self._fn().render_create_ddl(
            returns="OBJECT(value VARIANT, error STRING)"
        )
        assert "RETURNS OBJECT(value VARIANT, error STRING)" in ddl

    def test_null_handling_and_volatility_reproduced(self):
        fn = self._fn(
            **{"null handling": "CALLED ON NULL INPUT", "volatility": "IMMUTABLE"}
        )
        ddl = fn.render_create_ddl()
        assert "CALLED ON NULL INPUT" in ddl
        assert "IMMUTABLE" in ddl


class TestBuildQueryTextFunctionDef:
    """Synthesizing a FunctionDefinition from a builtin ``query_text``."""

    def test_body_is_query_text_and_args_from_columns(self):
        qt = "AI_COMPLETE('llama3.1-70b', 'Answer: ' || question)"
        fd = build_query_text_function_def(
            qt, ["question", "context"], name="DB.SCH.__BUILTIN_QUERY_TEXT"
        )
        assert fd.body == qt
        assert fd.name == "DB.SCH.__BUILTIN_QUERY_TEXT"
        assert fd.arg_names == ["question", "context"]
        assert fd.arg_types == ["VARCHAR", "VARCHAR"]
        assert fd.returns == "VARIANT"
        # signature is derived from the synthesized args.
        assert fd.signature == "(question VARCHAR, context VARCHAR)"

    def test_strips_quotes_from_columns_and_drops_overload_signature(self):
        fd = build_query_text_function_def(
            "AI_FILTER(c)", ['"C1"', "'c2'"], name="DB.SCH.F(VARCHAR)"
        )
        # An overload signature in the name is dropped to the base name.
        assert fd.name == "DB.SCH.F"
        assert fd.arg_names == ["C1", "c2"]

    def test_empty_columns_yields_no_args(self):
        fd = build_query_text_function_def(
            "AI_CLASSIFY(x, ['a'])", [], name="DB.SCH.__BUILTIN_QUERY_TEXT"
        )
        assert fd.args == []
        assert fd.signature == "()"
