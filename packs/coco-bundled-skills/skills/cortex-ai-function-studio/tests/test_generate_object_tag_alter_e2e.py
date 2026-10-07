# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Tests for generate_object_tag_alter() and UDF object tagging.

This file includes:
- Unit tests for the generated ALTER FUNCTION ... SET TAG SQL.
- Integration test(s) that run run_create_udf() then query the tag value.

Requires a valid Snowflake connection configured for Snowpark.
"""

from __future__ import annotations

import pytest
from create_udf import main
from snowflake.snowpark import Session

from snowflake_ai_optimize.core.udf_ddl import (
    CUSTOM_AI_FUNCTION_OBJECT_TAG,
    generate_object_tag_alter,
    generate_sql,
)
from snowflake_ai_optimize.core.udf_types import (
    InputParam,
    OutputField,
    UDFSpec,
)

# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_generate_object_tag_alter_single_input_signature_and_tag_value():
    spec = UDFSpec(
        database="DB",
        schema="SCHEMA",
        function_name="MY_FUNC",
        model="llama3.1-8b",
        function_intention="",
        inputs=[InputParam(name="TEXT", sql_type="VARCHAR")],
        outputs=[OutputField(name="label", json_type="string", description="")],
        system_prompt="x",
        user_prompt_template="{TEXT}",
    )

    sql = generate_object_tag_alter(spec, "abc").strip()

    assert "ALTER FUNCTION DB.SCHEMA.MY_FUNC(VARCHAR)" in sql.upper()

    # Tag name is a constant (string) used in both CREATE TAG and ALTER FUNCTION.
    assert f"SET TAG {CUSTOM_AI_FUNCTION_OBJECT_TAG}='abc'".upper() in sql.upper()


def test_generate_object_tag_alter_multiple_inputs_signature_ordering():
    spec = UDFSpec(
        database="DB",
        schema="SCHEMA",
        function_name="MY_FUNC",
        model="llama3.1-8b",
        inputs=[
            InputParam(name="A", sql_type="VARCHAR"),
            InputParam(name="B", sql_type="NUMBER"),
        ],
        outputs=[OutputField(name="label", json_type="string", description="")],
        system_prompt="x",
        user_prompt_template="{A} {B}",
    )

    sql = generate_object_tag_alter(spec, "v").strip()
    assert "ALTER FUNCTION DB.SCHEMA.MY_FUNC(VARCHAR, NUMBER)" in sql.upper()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def connection_name(request) -> str:
    return str(request.config.getoption("--connection", default="snowhouse"))


@pytest.fixture(scope="module")
def session(connection_name: str):
    sess = Session.builder.config("connection_name", connection_name).create()
    yield sess
    sess.close()


@pytest.fixture(scope="module")
def udf_spec(session, cleanup_stale, run_key) -> UDFSpec:
    # Some connections may not set a default database/schema.
    # Pick the current values if present; otherwise create a temporary schema.
    db = session.get_current_database()
    schema = session.get_current_schema()

    if db:
        db = db.strip('"')
    if schema:
        schema = schema.strip('"')

    if not db or not schema:
        db = "AI_SQL_TEAM_DB"
        schema = f"CUSTOM_AI_FUNCTION_TEST_{run_key}"
        session.sql(f"CREATE SCHEMA IF NOT EXISTS {db}.{schema}").collect()

    cleanup_stale(
        session,
        db,
        schema,
        functions=["TEST_OBJECT_TAG"],
    )

    return UDFSpec(
        database=db,
        schema=schema,
        function_name=f"TEST_OBJECT_TAG_{run_key}",
        model="llama3.1-8b",
        function_intention="Tagging integration test",
        inputs=[InputParam(name="TEXT", sql_type="VARCHAR")],
        outputs=[OutputField(name="label", json_type="string", description="")],
        system_prompt="Classify sentiment as positive or negative.",
        user_prompt_template="{TEXT}",
    )


@pytest.fixture(scope="module")
def udf_fqn(udf_spec: UDFSpec) -> str:
    return f"{udf_spec.database}.{udf_spec.schema}.{udf_spec.function_name}"


@pytest.fixture(scope="module")
def udf_signature() -> str:
    # generate_sql() produces UDF with user params only (e.g. TEXT VARCHAR)
    return "(VARCHAR)"


@pytest.fixture(scope="module")
def cleanup(session, udf_spec: UDFSpec, udf_fqn: str, udf_signature: str):
    yield
    session.sql(f"DROP FUNCTION IF EXISTS {udf_fqn}{udf_signature}").collect()
    session.sql(
        f"DROP TAG IF EXISTS {udf_spec.database}.{udf_spec.schema}.{CUSTOM_AI_FUNCTION_OBJECT_TAG}"
    ).collect()
    # If we created a temp schema, clean it up too.
    if udf_spec.schema.startswith("CUSTOM_AI_FUNCTION_TEST_"):
        session.sql(
            f"DROP SCHEMA IF EXISTS {udf_spec.database}.{udf_spec.schema}"
        ).collect()


@pytest.mark.e2e
def test_run_create_udf_sets_tag_value(
    session, cleanup, udf_spec, udf_fqn, udf_signature, connection_name, monkeypatch
):
    expected = "TEST_SESSION_ID_123"
    monkeypatch.setenv("CORTEX_SESSION_ID", expected)

    # This should create the tag key (if needed), create the function, and set the
    # object tag.
    main(connection=connection_name, sql_body=generate_sql(udf_spec))

    # Verify tag is set on the function.
    session.use_database(udf_spec.database)
    session.use_schema(udf_spec.schema)

    fq_tag = f"{udf_spec.database}.{udf_spec.schema}.{CUSTOM_AI_FUNCTION_OBJECT_TAG}"
    rows = session.sql(
        "SELECT SYSTEM$GET_TAG(?, ?, 'FUNCTION') AS TAG_VALUE",
        params=[fq_tag, f"{udf_fqn}{udf_signature}"],
    ).collect()

    assert rows and rows[0]["TAG_VALUE"] == expected


@pytest.mark.e2e
def test_tag_value_changes_with_cortex_session_id(
    session, cleanup, udf_spec, udf_fqn, udf_signature, connection_name, monkeypatch
):
    expected = "TEST_SESSION_ID_456"
    monkeypatch.setenv("CORTEX_SESSION_ID", expected)

    # Drop first, then re-create with new session ID.
    session.sql(f"DROP FUNCTION IF EXISTS {udf_fqn}{udf_signature}").collect()
    main(connection=connection_name, sql_body=generate_sql(udf_spec))

    session.use_database(udf_spec.database)
    session.use_schema(udf_spec.schema)

    fq_tag = f"{udf_spec.database}.{udf_spec.schema}.{CUSTOM_AI_FUNCTION_OBJECT_TAG}"
    rows = session.sql(
        "SELECT SYSTEM$GET_TAG(?, ?, 'FUNCTION') AS TAG_VALUE",
        params=[fq_tag, f"{udf_fqn}{udf_signature}"],
    ).collect()

    assert rows and rows[0]["TAG_VALUE"] == expected
