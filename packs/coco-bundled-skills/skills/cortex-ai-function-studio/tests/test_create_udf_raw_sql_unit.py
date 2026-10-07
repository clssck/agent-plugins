# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for create_udf.py raw SQL mode.

These tests run locally without a Snowflake connection.

Run:
    uv run --group test pytest tests/test_create_udf_raw_sql_unit.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from create_udf import _parse_fqn_from_ddl

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "create_udf.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
    )


class TestParseFqnFromDDL:
    def test_parses_fqn_and_param_types(self):
        ddl = """
        CREATE FUNCTION DB1.SCHEMA1.CLASSIFY(TEXT VARCHAR, SCORE NUMBER)
        RETURNS VARCHAR
        LANGUAGE SQL
        AS $$ TEXT $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == "DB1.SCHEMA1.CLASSIFY"
        assert param_types == "VARCHAR, NUMBER"

    def test_parses_empty_param_signature(self):
        ddl = """
        create function DB1.SCHEMA1.PING()
        returns varchar
        language sql
        as $$ 'ok' $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == "DB1.SCHEMA1.PING"
        assert param_types == ""

    def test_parses_param_types_with_nested_parentheses(self):
        ddl = """
        CREATE FUNCTION DB1.SCHEMA1.CLASSIFY(TEXT VARCHAR, SCORE NUMBER(10,2))
        RETURNS VARCHAR
        LANGUAGE SQL
        AS $$ TEXT $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == "DB1.SCHEMA1.CLASSIFY"
        assert param_types == "VARCHAR, NUMBER(10,2)"

    def test_parses_quoted_identifiers(self):
        ddl = """
        CREATE FUNCTION "DB1"."SCHEMA1"."Classify"("Input Text" VARCHAR)
        RETURNS VARCHAR
        LANGUAGE SQL
        AS $$ "Input Text" $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == '"DB1"."SCHEMA1"."Classify"'
        assert param_types == "VARCHAR"

    def test_parses_multiple_comma_containing_types(self):
        ddl = """
        CREATE FUNCTION DB1.SCHEMA1.SCORE(
            A NUMBER(10,2),
            B DECIMAL(38, 0),
            C VARCHAR
        )
        RETURNS VARCHAR
        LANGUAGE SQL
        AS $$ C $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == "DB1.SCHEMA1.SCORE"
        assert param_types == "NUMBER(10,2), DECIMAL(38, 0), VARCHAR"

    def test_parses_mixed_quoted_and_unquoted_fqn(self):
        ddl = """
        CREATE FUNCTION DB1."SCHEMA 1".SCORE(TEXT VARCHAR)
        RETURNS VARCHAR
        LANGUAGE SQL
        AS $$ TEXT $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == 'DB1."SCHEMA 1".SCORE'
        assert param_types == "VARCHAR"

    def test_parses_quoted_identifiers_with_escaped_quotes(self):
        ddl = """
        CREATE FUNCTION "DB1"."SCHEMA1"."A""B"("Input""Text" NUMBER(4,1))
        RETURNS NUMBER
        LANGUAGE SQL
        AS $$ 1 $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == '"DB1"."SCHEMA1"."A""B"'
        assert param_types == "NUMBER(4,1)"

    def test_parses_empty_signature_with_quoted_fqn(self):
        ddl = """
        CREATE FUNCTION "DB1"."SCHEMA1"."PING"()
        RETURNS VARCHAR
        LANGUAGE SQL
        AS $$ 'ok' $$;
        """

        fqn, param_types = _parse_fqn_from_ddl(ddl)

        assert fqn == '"DB1"."SCHEMA1"."PING"'
        assert param_types == ""

    def test_raises_on_unparseable_ddl(self):
        with pytest.raises(ValueError, match="Could not parse function name from DDL"):
            _parse_fqn_from_ddl("SELECT 1")


def test_non_fully_qualified_name_detected():
    """A non-FQ function name (missing DB.SCHEMA prefix) is caught."""
    ddl = """
    CREATE FUNCTION ONLY_FUNC(TEXT VARCHAR)
    RETURNS VARCHAR
    LANGUAGE SQL
    AS $$ TEXT $$;
    """

    fqn, _ = _parse_fqn_from_ddl(ddl)
    parts = fqn.rsplit(".", 2)
    assert len(parts) < 3, "Expected non-FQ name to have fewer than 3 parts"


def test_cli_connection_is_required():
    """--connection is required by argparse."""
    result = _run_cli(
        "--sql-body",
        "CREATE FUNCTION DB.S.F() RETURNS VARCHAR LANGUAGE SQL AS $$ 'x' $$;",
    )

    assert result.returncode != 0
    assert "connection" in result.stderr.lower()


# ---------------------------------------------------------------------------
# Harbor tests: flagged CLI arguments
#
# These guard against the agent hallucinating wrong flag names or swapping
# values between flags.  Each flag value uses a unique marker string so we
# can assert it lands in the correct structural position in the DDL.
# ---------------------------------------------------------------------------


def test_flagged_args_place_values_correctly():
    """Each flag value must appear in the correct structural position in the DDL."""
    from snowflake_ai_optimize.core.udf_ddl import generate_sql, parse_config

    config = {
        "database": "HARBOR_DB",
        "schema": "HARBOR_SCH",
        "function_name": "HARBOR_FUNC",
        "function_intention": "Harbor intention marker",
        "model": "harbor-model-x",
        "system_prompt": "You are the harbor system prompt.",
        "user_prompt_template": "Harbor user template: {REVIEW_TEXT}",
        "inputs": [{"name": "REVIEW_TEXT", "sql_type": "VARCHAR"}],
        "outputs": [
            {"name": "harbor_out", "json_type": "string", "description": "harbor desc"}
        ],
    }
    ddl = generate_sql(parse_config(config))

    # FQN: database.schema.function_name
    assert "HARBOR_DB.HARBOR_SCH.HARBOR_FUNC(" in ddl

    # Input param in signature
    assert "REVIEW_TEXT VARCHAR" in ddl

    # Model as literal in AI_COMPLETE call
    assert "model=>'harbor-model-x'" in ddl

    # System prompt inside the system role message, not the user role
    sys_idx = ddl.index("'role', 'system'")
    usr_idx = ddl.index("'role', 'user'")
    sp_idx = ddl.index("You are the harbor system prompt.")
    assert sys_idx < sp_idx < usr_idx, (
        "system prompt must be between system role and user role"
    )

    # User prompt template drives the user message content
    upt_idx = ddl.index("Harbor user template:")
    assert upt_idx > usr_idx, "user prompt template must appear after user role"

    # Output field appears in response_format schema
    assert '"harbor_out"' in ddl
    assert ":harbor_out::VARCHAR" in ddl

    # Comment carries the intention
    assert "Harbor intention marker" in ddl


def test_flagged_args_missing_required_flag():
    """Omitting a required field should raise ValueError naming the field."""
    from snowflake_ai_optimize.core.udf_ddl import parse_config

    config = {
        "database": "DB",
        # "schema" intentionally omitted
        "function_name": "F",
        "model": "m",
        "system_prompt": "sp",
        "user_prompt_template": "upt",
        "inputs": [{"name": "X", "sql_type": "VARCHAR"}],
        "outputs": [{"name": "y", "json_type": "string", "description": "d"}],
    }

    with pytest.raises(ValueError, match="schema"):
        parse_config(config)


def test_flagged_args_bad_inputs_json():
    """Malformed --inputs JSON should produce a clear error from argparse."""
    result = _run_cli(
        "--connection",
        "dummy",
        "--database",
        "DB",
        "--schema",
        "S",
        "--function-name",
        "F",
        "--model",
        "m",
        "--system-prompt",
        "sp",
        "--user-prompt-template",
        "upt",
        "--inputs",
        "not json",
        "--outputs",
        json.dumps([{"name": "y", "json_type": "string", "description": "d"}]),
    )

    assert result.returncode != 0
    assert "invalid" in result.stderr.lower()
