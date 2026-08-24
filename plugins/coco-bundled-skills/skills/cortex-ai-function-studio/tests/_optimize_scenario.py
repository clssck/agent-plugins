# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

r"""Loader for the optimize input-type e2e scenarios.

Each scenario is a YAML file under ``tests/e2e_scenarios/optimize_input_types/``
describing an AI function with a distinct SQL input type plus a minimal
optimization config.  The pure builders (``build_*_sql`` / ``build_udf_spec``)
produce SQL/specs offline and are unit-tested in
``tests/test_optimize_scenario_loader.py``; ``run_scenario_optimization`` drives
a real in-process ``run_body_optimization`` against a live Snowflake session and
is exercised by ``tests/test_optimize_input_types_e2e.py``.

YAML schema::

    name: single_text                 # identifier (alphanumeric + underscore)
    description: ...
    seed_model: llama3.1-8b           # the INPUT function's model
    inputs:                           # AI function input params (ordered)
      - {name: TEXT, sql_type: VARCHAR}
    output: {name: label, json_type: string, description: ...}
    system_prompt: ...
    user_prompt_template: "{TEXT}"    # {COL} substitution
    function_intention: ...           # optional
    metric_name: exact_match
    optimize_models: ["claude-haiku-4-5"]
    reflection_model: claude-sonnet-4-5   # optional
    auto_budget: demo                 # optional (default demo)
    label_column: EXPECTED_LABEL
    input_columns: ["TEXT"]           # optional (defaults to input names)
    rows:                             # small train/val data
      - {TEXT: "I love this", EXPECTED_LABEL: positive}
      # For non-VARCHAR columns the value is the raw SQL expression, e.g.
      #   {TAGS: "ARRAY_CONSTRUCT('a','b')", EXPECTED_LABEL: yes}
      #   {DOC: "PARSE_JSON('{\"amt\": 5}')", EXPECTED_LABEL: valid}

File-path (multimodal) inputs use ``sql_type: STAGE_FILE_PATH`` (or ``FILE``); the
function reads the file via ``TO_FILE('@stage', <col>)`` and the dataset column
holds the file's path relative to the stage root.  A scenario with a file input
must also list the fixture files to upload::

    seed_model: claude-sonnet-4-5
    inputs:
      - {name: IMG, sql_type: STAGE_FILE_PATH}
    stage_files: [red.png, green.png]   # fixtures under optimize_input_types/files/
    rows:
      - {IMG: "red.png", EXPECTED_COLOR: red}

``run_scenario_optimization`` creates a stage, PUTs the ``stage_files`` fixtures,
and drops the stage on teardown.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from snowflake_ai_optimize.core.udf_ddl import generate_sql
from snowflake_ai_optimize.core.udf_types import InputParam, OutputField, UDFSpec

SCENARIO_DIR = Path(__file__).parent / "e2e_scenarios" / "optimize_input_types"
FILES_DIR = SCENARIO_DIR / "files"

_VARCHAR_TYPES = {"VARCHAR", "STRING", "TEXT", "CHAR"}
# Declared input types that are file-path inputs: the AI function reads the file
# via ``TO_FILE('@stage', <col>)``.  The dataset column and the function argument
# are plain ``VARCHAR`` (holding the file's path relative to the stage root); the
# ``is_file_path`` flag drives the multimodal ``TO_FILE`` wrapping in the DDL.
_FILE_SQL_TYPES = {"STAGE_FILE_PATH", "FILE"}
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _is_file_input(inp: dict[str, Any]) -> bool:
    """Whether an input declares a file-path (stage-backed) type."""
    return str(inp.get("sql_type", "")).upper() in _FILE_SQL_TYPES


def _col_sql_type(inp: dict[str, Any]) -> str:
    """The concrete SQL column/argument type for an input (file types -> VARCHAR)."""
    return "VARCHAR" if _is_file_input(inp) else str(inp["sql_type"])


def has_file_inputs(scenario: dict[str, Any]) -> bool:
    """Whether the scenario has at least one file-path input (needs a stage)."""
    return any(_is_file_input(i) for i in scenario["inputs"])


def load_scenarios() -> list[dict[str, Any]]:
    """Load + lightly validate every scenario YAML (sorted by filename)."""
    scenarios: list[dict[str, Any]] = []
    for path in sorted(SCENARIO_DIR.glob("*.yaml")):
        with open(path, encoding="utf-8") as fh:
            scenario = yaml.safe_load(fh)
        _validate_scenario(scenario, path)
        scenario["_path"] = str(path)
        scenarios.append(scenario)
    return scenarios


def _validate_scenario(scenario: dict[str, Any], path: Path) -> None:
    required = (
        "name",
        "seed_model",
        "inputs",
        "output",
        "system_prompt",
        "user_prompt_template",
        "metric_name",
        "optimize_models",
        "label_column",
        "rows",
    )
    missing = [k for k in required if k not in scenario]
    if missing:
        raise ValueError(f"{path.name}: scenario missing required keys: {missing}")
    if not _NAME_RE.match(str(scenario["name"])):
        raise ValueError(f"{path.name}: invalid scenario name {scenario['name']!r}")
    for inp in scenario["inputs"]:
        if "name" not in inp or "sql_type" not in inp:
            raise ValueError(f"{path.name}: each input needs name + sql_type")
    if not scenario["rows"]:
        raise ValueError(f"{path.name}: scenario needs at least one data row")
    if any(_is_file_input(i) for i in scenario["inputs"]):
        stage_files = scenario.get("stage_files") or []
        if not stage_files:
            raise ValueError(
                f"{path.name}: a file-path input requires a non-empty 'stage_files' list"
            )
        for fname in stage_files:
            if not (FILES_DIR / fname).is_file():
                raise ValueError(
                    f"{path.name}: stage_files fixture not found: {FILES_DIR / fname}"
                )


def input_columns(scenario: dict[str, Any]) -> list[str]:
    return scenario.get("input_columns") or [i["name"] for i in scenario["inputs"]]


def _sql_value(value: Any, sql_type: str) -> str:
    """Render a Python value as a SQL literal for the given column type.

    VARCHAR-ish values are quoted/escaped; every other type is emitted verbatim
    so semi-structured columns can carry a SQL constructor expression
    (``ARRAY_CONSTRUCT(...)`` / ``OBJECT_CONSTRUCT(...)`` / ``PARSE_JSON(...)``)
    or a numeric/boolean literal.  Mirrors the benchmark harness's `_sql_value`.
    """
    if value is None:
        return "NULL"
    if sql_type.upper() in _VARCHAR_TYPES:
        return "'" + str(value).replace("'", "''") + "'"
    return str(value)


def build_create_table_sql(fq_table: str, scenario: dict[str, Any]) -> str:
    """CREATE OR REPLACE TABLE with the input columns + the VARCHAR label column.

    File-path inputs become ``VARCHAR`` columns holding the stage-relative path.
    """
    col_defs = [f"{inp['name']} {_col_sql_type(inp)}" for inp in scenario["inputs"]]
    col_defs.append(f"{scenario['label_column']} VARCHAR")
    body = ",\n  ".join(col_defs)
    return f"CREATE OR REPLACE TABLE {fq_table} (\n  {body}\n)"


def build_insert_sql(fq_table: str, scenario: dict[str, Any]) -> str:
    """INSERT ... SELECT ... UNION ALL for the scenario rows (type-aware literals).

    Uses ``SELECT`` rather than ``VALUES`` because Snowflake rejects function
    calls (``ARRAY_CONSTRUCT`` / ``OBJECT_CONSTRUCT`` / ``PARSE_JSON``) inside a
    ``VALUES`` clause ("Invalid expression ... in VALUES clause"), and the
    semi-structured input types carry exactly such constructor expressions.
    """
    inputs = scenario["inputs"]
    label = scenario["label_column"]
    columns = [inp["name"] for inp in inputs] + [label]
    types: dict[str, str] = {inp["name"]: _col_sql_type(inp) for inp in inputs}
    types[label] = "VARCHAR"
    selects = []
    for row in scenario["rows"]:
        exprs = ", ".join(_sql_value(row.get(c), types[c]) for c in columns)
        selects.append(f"  SELECT {exprs}")
    col_list = ", ".join(columns)
    return f"INSERT INTO {fq_table} ({col_list})\n" + "\n  UNION ALL\n".join(selects)


def build_udf_spec(
    db: str,
    schema: str,
    function_name: str,
    scenario: dict[str, Any],
    stage_name: str | None = None,
) -> UDFSpec:
    """Build the ``UDFSpec`` for the scenario's AI function.

    ``stage_name`` (e.g. ``@DB.SCH.STAGE``) is required when the scenario has a
    file-path input; it is baked into the ``TO_FILE('@stage', <col>)`` calls the
    multimodal DDL emits.
    """
    out = scenario["output"]
    if has_file_inputs(scenario) and not stage_name:
        raise ValueError("stage_name is required for a scenario with a file input")
    return UDFSpec(
        database=db,
        schema=schema,
        function_name=function_name,
        model=scenario["seed_model"],
        inputs=[
            InputParam(
                name=i["name"],
                sql_type=_col_sql_type(i),
                is_file_path=_is_file_input(i),
            )
            for i in scenario["inputs"]
        ],
        outputs=[
            OutputField(
                name=out["name"],
                json_type=out.get("json_type", "string"),
                description=out.get("description", ""),
            )
        ],
        system_prompt=scenario["system_prompt"],
        user_prompt_template=scenario["user_prompt_template"],
        function_intention=scenario.get("function_intention", ""),
        stage_name=stage_name,
    )


def build_udf_sql(
    db: str,
    schema: str,
    function_name: str,
    scenario: dict,
    stage_name: str | None = None,
) -> str:
    """Render the CREATE FUNCTION SQL for the scenario (pure)."""
    return generate_sql(build_udf_spec(db, schema, function_name, scenario, stage_name))


def _arg_types(scenario: dict[str, Any]) -> str:
    """Comma-joined SQL arg types for the AI function signature (for DROP)."""
    return ", ".join(_col_sql_type(inp) for inp in scenario["inputs"])


def run_scenario_optimization(
    session: Any,
    db: str,
    schema: str,
    scenario: dict[str, Any],
    run_key: str,
) -> dict[str, Any]:
    """Create the function + typed table + rows, then run body optimization in-process.

    Drives a REAL ``run_body_optimization`` against the live ``session`` (like the
    benchmark harness's local-optimize path), writing a Snowflake experiment.
    Returns the fully-qualified experiment name plus handles for teardown.

    ``run_body_optimization`` is imported lazily so the pure builders above can
    be unit-tested without importing the heavy optimizer stack.
    """
    from snowflake_ai_optimize.gepa.optimize_body import run_body_optimization

    suffix = f"{scenario['name']}_{run_key}".upper()
    func_name = f"OPT_IT_FN_{suffix}"
    table_name = f"OPT_IT_TBL_{suffix}"
    exp_name = f"OPT_IT_EXP_{suffix}"
    stage_name = f"OPT_IT_STG_{suffix}"

    def fq(name: str) -> str:
        return f"{db}.{schema}.{name}"

    # File-path scenarios need a stage with the fixture files uploaded before the
    # function (which reads them via TO_FILE('@stage', <col>)) is evaluated.
    stage_ref: str | None = None
    if has_file_inputs(scenario):
        stage_ref = f"@{fq(stage_name)}"
        # Server-side encryption is REQUIRED: AI_COMPLETE / TO_FILE cannot read
        # files from a client-side-encrypted stage (the internal-stage default),
        # which fails with "Input files from stages with Client Side Encryption
        # is not supported."  DIRECTORY enables stage file listing.
        session.sql(
            f"CREATE STAGE IF NOT EXISTS {fq(stage_name)} "
            "ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') DIRECTORY = (ENABLE = TRUE)"
        ).collect()
        for fname in scenario["stage_files"]:
            local = FILES_DIR / fname
            session.file.put(
                f"file://{local}",
                stage_ref,
                auto_compress=False,
                overwrite=True,
            )

    session.sql(build_udf_sql(db, schema, func_name, scenario, stage_ref)).collect()
    session.sql(build_create_table_sql(fq(table_name), scenario)).collect()
    session.sql(build_insert_sql(fq(table_name), scenario)).collect()
    # Idempotent: a stale experiment from a prior run would block ADD RUN.
    session.sql(f"DROP EXPERIMENT IF EXISTS {fq(exp_name)}").collect()

    run_body_optimization(
        session,
        function_name=fq(func_name),
        training_table=fq(table_name),
        label_column=scenario["label_column"],
        input_columns=input_columns(scenario),
        metric_name=scenario["metric_name"],
        models=list(scenario["optimize_models"]),
        reflection_model=scenario.get("reflection_model", "claude-sonnet-4-5"),
        auto_budget=scenario.get("auto_budget", "demo"),
        experiment_name=fq(exp_name),
        max_concurrency=1,
    )
    return {
        "experiment": fq(exp_name),
        "function": fq(func_name),
        "arg_types": _arg_types(scenario),
        "table": fq(table_name),
        "stage": fq(stage_name) if stage_ref else None,
    }


def drop_scenario_objects(session: Any, handles: dict[str, Any]) -> None:
    """Best-effort teardown of the function / table / experiment / stage created."""
    import contextlib

    with contextlib.suppress(Exception):
        session.sql(
            f"DROP FUNCTION IF EXISTS {handles['function']}({handles['arg_types']})"
        ).collect()
    with contextlib.suppress(Exception):
        session.sql(f"DROP TABLE IF EXISTS {handles['table']}").collect()
    with contextlib.suppress(Exception):
        session.sql(f"DROP EXPERIMENT IF EXISTS {handles['experiment']}").collect()
    if handles.get("stage"):
        with contextlib.suppress(Exception):
            session.sql(f"DROP STAGE IF EXISTS {handles['stage']}").collect()
