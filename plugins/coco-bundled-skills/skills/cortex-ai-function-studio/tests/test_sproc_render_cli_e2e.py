# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""E2e test for SPROC creation and anonymous evaluation.

This test uploads required source files to a stage, creates both EVALUATE_AI_FUNCTION
and OPTIMIZE_AI_FUNCTION, then validates they can be called.

Run:
  uv run --group test pytest tests/test_create_sproc_cli_e2e.py -v --connection <conn>
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys

import pytest
from _paths import SCRIPTS_DIR, resolve_module_path

from snowflake_ai_optimize.core.sproc_render import render_sproc_sql

pytestmark = pytest.mark.e2e


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
    "snowflake_ai_optimize.gepa.adapter",
    "snowflake_ai_optimize.gepa.engine",
    "snowflake_ai_optimize.gepa.engine_registry",
    "snowflake_ai_optimize.core.optimize_registry",
    "snowflake_ai_optimize.gepa.experiment",
    "snowflake_ai_optimize.gepa.optimize",
    "snowflake_ai_optimize.gepa.optimize_body",
    "snowflake_ai_optimize.gepa._registry",
]


@pytest.fixture(scope="module")
def env(session, cleanup_stale, run_key, request):
    """Provision stage, UDF, test table, then create SPROCs via CLI."""
    conn_name = request.config.getoption("--connection", default="snowhouse")
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')
    stage = f"TEST_CLI_E2E_STAGE_{run_key}"

    cleanup_stale(
        session,
        db,
        schema,
        stages=["TEST_CLI_E2E_STAGE"],
        tables=["TEST_CLI_CLASSIFY_DATA"],
        functions=["TEST_CLI_CLASSIFY"],
    )
    func_name = f"TEST_CLI_CLASSIFY_{run_key}"
    table_name = f"TEST_CLI_CLASSIFY_DATA_{run_key}"

    fq = lambda name: f"{db}.{schema}.{name}"

    # --- stage + file upload ------------------------------------------------
    session.sql(f"CREATE STAGE IF NOT EXISTS {stage}").collect()

    for module in STAGE_MODULES:
        file_path = resolve_module_path(module)
        session.file.put(
            f"file://{file_path}",
            f"@{stage}",
            auto_compress=False,
            overwrite=True,
        )

    # --- create UDF via CLI (so sprocs have a target function) --------------
    udf_script_path = SCRIPTS_DIR / "create_udf.py"

    coco_session_id = os.environ.get("CORTEX_SESSION_ID") or f"pytest_cli_{run_key}"

    subprocess.run(
        [
            sys.executable,
            str(udf_script_path),
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
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "CORTEX_SESSION_ID": coco_session_id},
    )

    # --- test data ----------------------------------------------------------
    session.sql(
        f"""
        CREATE TABLE {fq(table_name)} (
            TEXT VARCHAR,
            EXPECTED_LABEL VARCHAR
        )
        """
    ).collect()
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

    yield {
        "db": db,
        "schema": schema,
        "stage": stage,
        "func": fq(func_name),
        "table": fq(table_name),
        "fq": fq,
    }

    # --- teardown -----------------------------------------------------------
    session.sql(f"DROP FUNCTION IF EXISTS {fq(func_name)}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {fq(table_name)}").collect()
    session.sql(f"DROP STAGE IF EXISTS {stage}").collect()
    session.sql(f"DROP TAG IF EXISTS {fq('CUSTOM_AI_FUNCTION_UDF_TAG')}").collect()


# ---------------------------------------------------------------------------
# Anonymous SPROC tests
# ---------------------------------------------------------------------------


def _generate_anonymous_sproc(sproc_type: str, db: str, schema: str, stage: str) -> str:
    """Generate anonymous SPROC SQL with --anonymous --inline flags."""
    return render_sproc_sql(sproc_type, db, schema, stage, anonymous=True, inline=True)


def test_anonymous_evaluate_returns_score(session, env):
    """Execute an anonymous SPROC for evaluation and verify it returns a valid score."""
    anon_sql = _generate_anonymous_sproc(
        "evaluate", env["db"], env["schema"], env["stage"]
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
    assert payload["experiment_name"], "experiment_name should be auto-generated"
    # Cleanup the auto-generated experiment.
    with contextlib.suppress(Exception):
        session.sql(
            f"DROP EXPERIMENT IF EXISTS {env['db']}.{env['schema']}.{payload['experiment_name'].split('.')[-1]}"
        ).collect()
