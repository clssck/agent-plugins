# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""CLI end-to-end test for src/create_udf.py.

This test executes the create_udf.py script via subprocess using --execute,
then validates the created UDF is callable.

Run:
  uv run --group test pytest tests/test_create_udf_cli_e2e.py -v --connection <conn>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def env(session, cleanup_stale, run_key, request):
    """Create a test UDF via src/create_udf.py and tear it down."""
    conn_name = request.config.getoption("--connection", default="snowhouse")
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')

    func_name = f"TEST_CLI_CREATE_UDF_{run_key}"

    cleanup_stale(
        session,
        db,
        schema,
        functions=["TEST_CLI_CREATE_UDF"],
    )
    fq_func = f"{db}.{schema}.{func_name}"

    custom_ai_function_dir = Path(__file__).resolve().parents[1]
    script_path = custom_ai_function_dir / "scripts" / "create_udf.py"

    coco_session_id = os.environ.get("CORTEX_SESSION_ID") or f"pytest_cli_{run_key}"

    cmd = [
        sys.executable,
        str(script_path),
        "--database",
        db,
        "--schema",
        schema,
        "--function-name",
        func_name,
        "--function-intention",
        "Classify text as positive or negative",
        "--model",
        "llama3.1-8b",
        "--system-prompt",
        "Classify the sentiment of the text as positive or negative.",
        "--user-prompt-template",
        "{TEXT}",
        "--inputs",
        json.dumps([{"name": "TEXT", "sql_type": "VARCHAR"}]),
        "--outputs",
        json.dumps(
            [
                {
                    "name": "label",
                    "json_type": "string",
                    "description": "positive or negative",
                }
            ]
        ),
        "--connection",
        conn_name,
    ]
    subprocess.run(
        cmd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "CORTEX_SESSION_ID": coco_session_id},
    )

    yield {
        "db": db,
        "schema": schema,
        "func": fq_func,
        "func_name": func_name,
    }

    # create_udf.py generate_sql() produces signature with user params only,
    # e.g. (TEXT VARCHAR)
    session.sql(f"DROP FUNCTION IF EXISTS {fq_func}(VARCHAR)").collect()
    session.sql(
        f"DROP TAG IF EXISTS {db}.{schema}.CUSTOM_AI_FUNCTION_UDF_TAG"
    ).collect()


def test_udf_created_and_callable(session, env):
    result = session.sql(f"SELECT {env['func']}('I love this') AS prediction").collect()
    prediction = str(result[0]["PREDICTION"]).strip().lower()
    assert prediction, "UDF returned empty result"
