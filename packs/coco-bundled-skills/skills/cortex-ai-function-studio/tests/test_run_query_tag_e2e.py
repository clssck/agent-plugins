# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""E2e tests verifying that run.py evaluate and optimize inject the CoCo
session query tag into executed SQL.

When CORTEX_SESSION_ID is set, run.py's ``_exec()`` wrapper uses
``customai_query_tag_logging`` to set the session QUERY_TAG with key
``__CUSTOM_AI_FUNCTION_COCO_SESSION_ID_``.  These tests invoke run.py as
a subprocess (matching real usage) and check INFORMATION_SCHEMA.QUERY_HISTORY
for the expected tag.

Run:
  uv run --group test pytest tests/test_run_query_tag_e2e.py -v --connection <conn>
"""  # noqa: D205

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from snowflake.snowpark import Session

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
    "models.json",
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
    """Provision stage, UDF, and test table for run.py e2e tests."""
    conn_name = request.config.getoption("--connection", default="snowhouse")
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')
    stage = f"TEST_RUN_QT_STAGE_{run_key}"

    cleanup_stale(
        session,
        db,
        schema,
        stages=["TEST_RUN_QT_STAGE"],
        tables=["TEST_RUN_QT_DATA"],
        functions=["TEST_RUN_QT_CLASSIFY"],
    )
    func_name = f"TEST_RUN_QT_CLASSIFY_{run_key}"
    table_name = f"TEST_RUN_QT_DATA_{run_key}"

    fq = lambda name: f"{db}.{schema}.{name}"

    # --- stage + file upload ------------------------------------------------
    session.sql(f"CREATE STAGE IF NOT EXISTS {stage}").collect()

    from _paths import SCRIPTS_DIR, resolve_module_path

    for module in STAGE_MODULES:
        file_path = resolve_module_path(module)
        session.file.put(
            f"file://{file_path}",
            f"@{stage}",
            auto_compress=False,
            overwrite=True,
        )

    # --- pre-cleanup in case stale objects remain from a prior interrupted run
    session.sql(f"DROP FUNCTION IF EXISTS {fq(func_name)}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {fq(table_name)}").collect()

    # --- create UDF via CLI -------------------------------------------------
    udf_script_path = SCRIPTS_DIR / "create_udf.py"

    coco_session_id = os.environ.get("CORTEX_SESSION_ID") or f"pytest_run_qt_{run_key}"

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
        "conn_name": conn_name,
        "coco_session_id": coco_session_id,
        "fq": fq,
    }

    # --- teardown -----------------------------------------------------------
    session.sql(f"DROP FUNCTION IF EXISTS {fq(func_name)}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {fq(table_name)}").collect()
    session.sql(f"DROP STAGE IF EXISTS {stage}").collect()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RUN_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run.py"


def _sql_like_literal(s: str) -> str:
    return s.replace("'", "''")


def assert_query_history_has_coco_tag(
    session: Session,
    *,
    coco_session_id: str,
    expected_query_text_fragment: str,
    expected_ddl_prefix: str,
) -> None:
    """Assert INFORMATION_SCHEMA.QUERY_HISTORY contains a tagged query."""
    tag_prefix = "__CUSTOM_AI_FUNCTION_COCO_SESSION_ID_"
    frag = _sql_like_literal(expected_query_text_fragment)
    ddl = _sql_like_literal(expected_ddl_prefix)
    coco = _sql_like_literal(coco_session_id)
    db = session.get_current_database().strip('"')

    def _run_once():
        return session.sql(f"""
            SELECT QUERY_ID, START_TIME, QUERY_TAG, QUERY_TEXT
            FROM TABLE(
                {db}.INFORMATION_SCHEMA.QUERY_HISTORY(
                    END_TIME_RANGE_START=>DATEADD('minute', -30, CURRENT_TIMESTAMP()),
                    END_TIME_RANGE_END=>CURRENT_TIMESTAMP(),
                    RESULT_LIMIT=>1000
                )
            )
            WHERE QUERY_TAG ILIKE '%{tag_prefix}%'
              AND QUERY_TAG ILIKE '%{coco}%'
              AND QUERY_TEXT ILIKE '%{ddl}%'
              AND QUERY_TEXT ILIKE '%{frag}%'
            ORDER BY START_TIME DESC
            LIMIT 5
        """).collect()

    # INFORMATION_SCHEMA.QUERY_HISTORY has a replication lag that can exceed
    # 45s on preprod environments (observed 120-160s for freshly executed
    # anonymous SPROCs). Use a 3-minute deadline so we ride out the lag.
    deadline = time.monotonic() + 180
    delay = 2
    rows: list = []
    while True:
        rows = _run_once()
        if len(rows) >= 1:
            break
        if time.monotonic() + delay > deadline:
            break
        time.sleep(delay)
        delay = min(delay * 2, 15)

    if not rows:
        # Diagnostic: list any recent queries with the tag prefix OR the coco
        # session id OR the expected DDL fragment, to understand what's
        # actually in QUERY_HISTORY.
        diag = session.sql(f"""
            SELECT
                QUERY_ID,
                START_TIME,
                LEFT(QUERY_TAG, 300) AS QUERY_TAG_PREVIEW,
                LEFT(QUERY_TEXT, 300) AS QUERY_TEXT_PREVIEW
            FROM TABLE(
                {db}.INFORMATION_SCHEMA.QUERY_HISTORY(
                    END_TIME_RANGE_START=>DATEADD('minute', -30, CURRENT_TIMESTAMP()),
                    END_TIME_RANGE_END=>CURRENT_TIMESTAMP(),
                    RESULT_LIMIT=>1000
                )
            )
            WHERE (QUERY_TAG ILIKE '%{tag_prefix}%' OR QUERY_TAG ILIKE '%{coco}%'
                   OR QUERY_TEXT ILIKE '%{ddl}%')
            ORDER BY START_TIME DESC
            LIMIT 20
        """).collect()
        diag_lines = "\n".join(
            f"  {r['QUERY_ID']} @ {r['START_TIME']}\n"
            f"    TAG : {r['QUERY_TAG_PREVIEW']}\n"
            f"    TEXT: {r['QUERY_TEXT_PREVIEW']}"
            for r in diag
        )
        print(
            f"\n[diag] QUERY_HISTORY matches (tag_prefix OR coco OR ddl), "
            f"count={len(diag)}:\n{diag_lines or '  (none)'}"
        )

    assert len(rows) >= 1, (
        "Expected at least one query in INFORMATION_SCHEMA.QUERY_HISTORY with "
        f"QUERY_TAG containing '{tag_prefix}{coco_session_id}' (or merged JSON) "
        f"and QUERY_TEXT containing '{expected_ddl_prefix}' + '{expected_query_text_fragment}'."
    )


def _run_py(args: list[str], *, coco_session_id: str) -> subprocess.CompletedProcess:
    """Invoke run.py as a subprocess with CORTEX_SESSION_ID set.

    We intentionally do NOT set ``check=True`` because the SPROC may fail
    for reasons unrelated to query-tag injection (e.g. too few rows for
    optimize).  The query tag is applied by ``_exec()`` *before* the SPROC
    body runs, so even a failing execution will appear in QUERY_HISTORY
    with the expected tag.
    """
    return subprocess.run(
        [sys.executable, str(_RUN_SCRIPT), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "CORTEX_SESSION_ID": coco_session_id},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_optimize_query_tag(session, env):
    """run.py optimize should tag its SQL with the CoCo session ID."""
    proc = _run_py(
        [
            "optimize",
            "--database",
            env["db"],
            "--schema",
            env["schema"],
            "--stage",
            env["stage"],
            "--connection",
            env["conn_name"],
            "--function-name",
            env["func"],
            "--training-table",
            env["table"],
            "--label-column",
            "EXPECTED_LABEL",
            "--input-columns",
            "TEXT",
            "--metric-name",
            "exact_match",
            "--models",
            "llama3.1-8b",
            "--reflection-model",
            "llama3.1-8b",
            "--test-table",
            "none",
            "--auto-budget",
            "light",
            "--experiment-name",
            "none",
            "--validation-fraction",
            "0.5",
            "--temperature",
            "0.7",
            "--max-tokens",
            "8192",
            "--metric-options",
            "none",
            "--custom-metric-udf",
            "none",
            "--run-id",
            "none",
            "--aggregation-metric",
            "none",
        ],
        coco_session_id=env["coco_session_id"],
    )

    # Surface subprocess output only on failure — helps diagnose whether
    # run.py actually made it into the query-tagged _exec() call or exited
    # early (e.g. argparse / SQL error before the tag block).
    if proc.returncode != 0:
        print(f"\n[subprocess] returncode={proc.returncode}")
        print(f"[subprocess stdout]\n{proc.stdout}")
        print(f"[subprocess stderr]\n{proc.stderr}")

    assert_query_history_has_coco_tag(
        session,
        coco_session_id=env["coco_session_id"],
        expected_query_text_fragment="OPTIMIZE_AI_FUNCTION",
        expected_ddl_prefix="WITH OPTIMIZE_AI_FUNCTION AS PROCEDURE",
    )
