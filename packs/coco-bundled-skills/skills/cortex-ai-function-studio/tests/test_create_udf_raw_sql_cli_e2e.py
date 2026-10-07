# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""CLI end-to-end test for src/create_udf.py raw SQL mode.

This test executes create_udf.py via subprocess with --sql-body --execute,
validates the created UDF is callable, and verifies object tag values.

Run:
  uv run --group test pytest tests/test_create_udf_raw_sql_cli_e2e.py -v \
    --connection <conn>
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def env(session, cleanup_stale, run_key, request):
    """Create a test UDF via src/create_udf.py --sql-body and tear it down."""
    conn_name = request.config.getoption("--connection", default="snowhouse")
    db = session.get_current_database()
    schema = session.get_current_schema()
    if not db or not schema:
        pytest.skip(
            "Connection must define current database and schema for this e2e test."
        )

    db = db.strip('"')
    schema = schema.strip('"')

    func_name = f"TEST_CLI_CREATE_UDF_RAW_SQL_{run_key}"

    cleanup_stale(
        session,
        db,
        schema,
        functions=["TEST_CLI_CREATE_UDF_RAW_SQL"],
    )
    fq_func = f"{db}.{schema}.{func_name}"

    custom_ai_function_dir = Path(__file__).resolve().parents[1]
    script_path = custom_ai_function_dir / "scripts" / "create_udf.py"

    ddl = (
        f"CREATE FUNCTION {fq_func}(TEXT VARCHAR) "
        "RETURNS VARCHAR "
        "LANGUAGE SQL "
        "AS $$ TEXT $$;"
    )

    coco_session_id = (
        os.environ.get("CORTEX_SESSION_ID") or f"pytest_raw_sql_cli_{run_key}"
    )

    cmd = [
        sys.executable,
        str(script_path),
        "--sql-body",
        ddl,
        "--connection",
        conn_name,
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={**os.environ, "CORTEX_SESSION_ID": coco_session_id},
    )
    if result.returncode != 0:
        pytest.fail(
            f"create_udf.py exited with code {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    yield {
        "func": fq_func,
        "func_name": func_name,
        "coco_session_id": coco_session_id,
    }

    session.sql(f"DROP FUNCTION IF EXISTS {fq_func}(VARCHAR)").collect()


def test_raw_sql_udf_created_and_callable(session, env):
    result = session.sql(f"SELECT {env['func']}('echo text') AS prediction").collect()
    prediction = str(result[0]["PREDICTION"]).strip().lower()
    assert prediction == "echo text"


def test_raw_sql_udf_tag_is_set(session, env):
    # Re-create the tag if a sibling test module's teardown dropped it.
    session.sql("CREATE TAG IF NOT EXISTS CUSTOM_AI_FUNCTION_UDF_TAG").collect()

    rows = session.sql(
        "SELECT SYSTEM$GET_TAG(?, ?, 'FUNCTION') AS TAG_VALUE",
        params=["CUSTOM_AI_FUNCTION_UDF_TAG", f"{env['func']}(VARCHAR)"],
    ).collect()

    assert rows and rows[0]["TAG_VALUE"] == env["coco_session_id"]
