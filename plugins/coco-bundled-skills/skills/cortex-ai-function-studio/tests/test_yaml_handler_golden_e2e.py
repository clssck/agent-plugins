# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

r"""Golden-file e2e coverage for the YAML handler (``execute_ai_function_eval_opts``).

Each scenario is a SPEC YAML under ``tests/e2e_scenarios/yaml_handler/`` — the
exact ``specification`` the handler parses, with two placeholders that the live
environment fills in:

* ``__FUNCTION__`` -> a provisioned user AI function's signature
  (``DB.SCH.F(VARCHAR)``);
* ``__TABLE__``    -> a provisioned labeled dataset table.

Builtin (``query_text``) SPECs carry an inline ``AI_COMPLETE`` expression and
only use ``__TABLE__``. For every SPEC the test drives the handler, reads the
resulting Snowflake Experiment into a run tree, reduces it (with the handler's
return dict) to a deterministic golden document (see ``tests/_experiment_golden.py``),
and compares it against a committed ``*.golden.yaml`` "output ref". Scores,
timings, token counts, GEPA iteration counts and object names are all redacted /
tokenized so the golden is stable across live runs.

Coverage:

* **eval** (``eval_*.yaml``): exact_match / fuzzy_match / contains_match /
  llm-judge, named vs positional ``$N`` argument_mapping, ``metrics`` as a list
  vs a single mapping, ``num_eval_runs`` 1 / 2 / 3 / 5, and user-function vs
  builtin ``query_text`` (with and without an argument_mapping).
* **opt** (``opt_*.yaml``): body-mode GEPA at ``ultra-light`` budget over
  {user function, builtin query_text} x {with holdout, without holdout} with
  varied metrics — asserting the ``SEED`` + ``ITER_<N>`` global run structure.

Recording / updating goldens (runs live, writes the ``golden/`` files)::

    UPDATE_EXPERIMENT_GOLDEN=1 uv run --group test pytest \
        tests/test_yaml_handler_golden_e2e.py -v -m e2e --connection sfctest-udaif

Verifying (the default; compares against the committed goldens)::

    uv run --group test pytest tests/test_yaml_handler_golden_e2e.py \
        -v -m e2e --connection sfctest-udaif

Gated by ``@pytest.mark.e2e`` (needs a live connection + the ``run-e2e-test`` PR
label). With the repo's ``--dist=loadfile`` xdist policy every scenario in this
file runs sequentially on one worker (in parallel with other e2e files).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from _experiment_golden import (
    SEED_RUN_NAME,
    build_golden,
    dump_golden,
    make_tokenizer,
    summarize_iteration_runs,
    verify_or_record,
)
from _experiment_tree import build_experiment_tree, render_experiment_tree

from handlers.execute_eval_opts_handler import execute_ai_function_eval_opts
from snowflake_ai_optimize.core.experiment import create_experiment
from snowflake_ai_optimize.core.udf_ddl import generate_sql
from snowflake_ai_optimize.core.udf_types import InputParam, OutputField, UDFSpec

_YAML_HANDLER_DIR = Path(__file__).parent / "e2e_scenarios" / "yaml_handler"
SPEC_DIR = _YAML_HANDLER_DIR / "specs"
GOLDEN_DIR = _YAML_HANDLER_DIR / "golden"

_INPUT_COLUMN = "TEXT"
_GROUND_TRUTH_COLUMN = "EXPECTED_LABEL"
_FUNCTION_TOKEN = "__FUNCTION__"
_TABLE_TOKEN = "__TABLE__"
_METRIC_UDF_TOKEN = "__METRIC_UDF__"

# Balanced sentiment dataset shared by every scenario (12 rows). Large enough
# for the optimizer's val/train split, small enough to keep live AI cost low.
_ROWS: list[tuple[str, str]] = [
    ("I absolutely love this, best purchase ever!", "positive"),
    ("Fantastic quality and great support.", "positive"),
    ("This made my whole week, wonderful.", "positive"),
    ("Delightful experience from start to finish.", "positive"),
    ("Highly recommend, exceeded expectations.", "positive"),
    ("Pretty good overall, would buy again.", "positive"),
    ("Terrible, the worst thing I have bought.", "negative"),
    ("Completely broken and useless.", "negative"),
    ("I hate it, total waste of money.", "negative"),
    ("Awful service and rude staff.", "negative"),
    ("Disappointing and overpriced.", "negative"),
    ("Do not buy, regret it deeply.", "negative"),
]


def _load_specs() -> list[dict]:
    """Discover + parse every SPEC YAML (sorted by filename)."""
    specs: list[dict] = []
    for path in sorted(SPEC_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        parsed = yaml.safe_load(text)
        if "evaluation" in parsed:
            job_kind = "evaluation"
        elif "optimization" in parsed:
            job_kind = "optimization"
        else:  # pragma: no cover - guarded by the offline loader test
            raise ValueError(
                f"{path.name}: SPEC has neither evaluation nor optimization"
            )
        specs.append(
            {
                "name": path.stem,
                "path": path,
                "text": text,
                "job_kind": job_kind,
                "uses_function_token": _FUNCTION_TOKEN in text,
            }
        )
    return specs


SPECS = _load_specs()
_SPEC_IDS = [s["name"] for s in SPECS]


@pytest.fixture(scope="module")
def handler_env(session, cleanup_stale, run_key):
    """Provision a shared classifier UDF + labeled dataset; drop it after."""
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')

    def fq(name: str) -> str:
        return f"{db}.{schema}.{name}"

    cleanup_stale(
        session,
        db,
        schema,
        tables=["YHG_DATA"],
        functions=["YHG_CLASSIFY", "YHG_METRIC"],
        experiments=["YHG_EXP"],
    )

    func = f"YHG_CLASSIFY_{run_key}"
    table = f"YHG_DATA_{run_key}"
    metric_udf = f"YHG_METRIC_{run_key}"
    func_fqn = fq(func)
    table_fqn = fq(table)
    metric_udf_fqn = fq(metric_udf)
    function_signature = f"{func_fqn}(VARCHAR)"

    udf_spec = UDFSpec(
        database=db,
        schema=schema,
        function_name=func,
        model="llama3.1-8b",
        function_intention="Classify text sentiment as positive or negative",
        inputs=[InputParam(name=_INPUT_COLUMN, sql_type="VARCHAR")],
        outputs=[
            OutputField(
                name="label", json_type="string", description="positive or negative"
            )
        ],
        system_prompt=(
            "Classify the sentiment of the text as positive or negative. "
            "Answer with exactly 'positive' or 'negative'."
        ),
        user_prompt_template="{TEXT}",
    )
    session.sql(generate_sql(udf_spec)).collect()

    session.sql(
        f"CREATE OR REPLACE TABLE {table_fqn} "
        f"({_INPUT_COLUMN} VARCHAR, {_GROUND_TRUTH_COLUMN} VARCHAR)"
    ).collect()
    values = ", ".join(
        f"('{text.replace(chr(39), chr(39) * 2)}', '{label}')" for text, label in _ROWS
    )
    session.sql(f"INSERT INTO {table_fqn} VALUES {values}").collect()

    # A custom metric UDF for the ``metric: custom`` spec: contract is
    # (EXPECTED, PREDICTED) VARCHAR -> VARIANT with score + feedback keys.
    session.sql(
        f"CREATE OR REPLACE FUNCTION {metric_udf_fqn}"
        "(EXPECTED VARCHAR, PREDICTED VARCHAR) RETURNS VARIANT LANGUAGE SQL AS $$ "
        "TO_VARIANT(OBJECT_CONSTRUCT("
        "'score', IFF(LOWER(TRIM(PREDICTED)) LIKE '%' || LOWER(TRIM(EXPECTED)) || '%', "
        "1.0, 0.0), 'feedback', 'custom substring scorer')) $$"
    ).collect()

    yield {
        "db": db,
        "schema": schema,
        "fq": fq,
        "function_signature": function_signature,
        "function_fqn": func_fqn,
        "table": table_fqn,
        "metric_udf": metric_udf_fqn,
        "run_key": run_key,
        "row_count": len(_ROWS),
    }

    session.sql(f"DROP FUNCTION IF EXISTS {func_fqn}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {table_fqn}").collect()
    session.sql(f"DROP FUNCTION IF EXISTS {metric_udf_fqn}(VARCHAR, VARCHAR)").collect()


def _tokenizer_for(env: dict, experiment_name: str):
    """Build the env->token rewriter for stable goldens.

    Longer, fully qualified names are registered first so a function signature
    or table name is tokenized before its bare db/schema components (the
    tokenizer also orders by length internally).
    """
    return make_tokenizer(
        {
            env["function_signature"]: _FUNCTION_TOKEN,
            env["function_fqn"]: _FUNCTION_TOKEN,
            env["metric_udf"]: _METRIC_UDF_TOKEN,
            env["table"]: _TABLE_TOKEN,
            experiment_name: "__EXP__",
            str(env["run_key"]): "__RUNKEY__",
            env["db"]: "__DB__",
            env["schema"]: "__SCHEMA__",
        }
    )


@pytest.mark.e2e
@pytest.mark.parametrize("spec", SPECS, ids=_SPEC_IDS)
def test_yaml_handler_golden(session, handler_env, spec):
    """Drive the handler for one SPEC and verify its Experiment golden ref."""
    # Register the production body/prompt optimize modes for the opt path (the
    # deployed SPROC does this via the bundled _registry.py; the package/test
    # path registers by importing the gepa package).
    if spec["job_kind"] == "optimization":
        import snowflake_ai_optimize.gepa  # noqa: F401

    experiment_name = handler_env["fq"](f"YHG_EXP_{spec['name'].upper()}")
    filled = (
        spec["text"]
        .replace(_FUNCTION_TOKEN, handler_env["function_signature"])
        .replace(_METRIC_UDF_TOKEN, handler_env["metric_udf"])
        .replace(_TABLE_TOKEN, handler_env["table"])
    )

    # The handler does NOT create the experiment (create_experiment_if_missing
    # is False on this path) — in production the EXECUTE EXPERIMENT DDL creates
    # the experiment object, then invokes the SPROC to add runs to it. Mirror
    # that here: (re)create a fresh experiment before driving the handler.
    session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()
    create_experiment(session, experiment_name)
    try:
        # run_name is ignored by this handler path (it assigns fixed run names:
        # EVAL_1..N for eval, SEED/ITER_<N> for opt); passed only to satisfy the
        # OBJECT contract.
        result = execute_ai_function_eval_opts(
            session,
            {"experiment_name": experiment_name, "run_name": "EVAL"},
            filled,
        )
        assert result.get("status") == "SUCCEEDED", (
            f"{spec['name']} did not succeed: {result}"
        )
        assert "error" not in result, f"{spec['name']} surfaced an error: {result}"

        tree = build_experiment_tree(session, experiment_name)
        print(
            f"\n[{spec['name']}] raw experiment tree:\n{render_experiment_tree(tree)}"
        )
        committed_runs = set(tree.get(experiment_name, {}))

        if spec["job_kind"] == "evaluation":
            # Guard against a silent partial failure: every run the handler
            # reported must actually be committed to the experiment (else the
            # golden would be built from an incomplete tree yet still pass).
            declared = set(result.get("runs") or [])
            if "run" in result:
                declared.add(result["run"])
            assert committed_runs == declared, (
                f"{spec['name']}: committed runs {sorted(committed_runs)} != "
                f"handler-declared runs {sorted(declared)}"
            )
        else:
            # Optimization commits one SEED run plus a nondeterministic number
            # of ITER_<N> runs. The golden pins only the deterministic SEED (see
            # build_golden); the iteration runs are verified structurally here.
            assert SEED_RUN_NAME in committed_runs, (
                f"{spec['name']}: optimization did not commit a SEED run"
            )
            iter_summary = summarize_iteration_runs(tree, experiment_name)
            print(f"[{spec['name']}] iteration runs: {iter_summary}")
            assert not iter_summary["violations"], (
                f"{spec['name']} ITER run violations: {iter_summary['violations']}"
            )
            # SEED must carry a non-trivial optimized function body.
            seed_params = (
                tree.get(experiment_name, {})
                .get(SEED_RUN_NAME, {})
                .get("parameters", {})
            )
            assert seed_params.get("function_impl"), (
                f"{spec['name']}: SEED function_impl is missing or empty"
            )

        tokenize = _tokenizer_for(handler_env, experiment_name)
        # When the SPEC explicitly sets judge_model the model value is
        # SPEC-determined (stable) and should be asserted in the golden.
        spec_judge_model: str | None = None
        if spec["job_kind"] == "evaluation":
            spec_parsed = yaml.safe_load(spec["text"])
            metrics = spec_parsed.get("metrics", [])
            if isinstance(metrics, list):
                spec_judge_model = metrics[0].get("judge_model") if metrics else None
            else:
                spec_judge_model = metrics.get("judge_model")
        golden = build_golden(
            job_kind=spec["job_kind"],
            result=result,
            tree=tree,
            experiment_name=experiment_name,
            tokenize=tokenize,
            spec_judge_model=spec_judge_model,
        )
        print(f"[{spec['name']}] golden output ref:\n{dump_golden(golden)}")

        verify_or_record(GOLDEN_DIR / f"{spec['name']}.golden.yaml", golden)
    finally:
        session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()


# ---------------------------------------------------------------------------
# Error path: invalid SPECs must be rejected (not SUCCEEDED)
# ---------------------------------------------------------------------------
# These live in a subdirectory so the non-recursive ``*.yaml`` glob above does
# not pick them up as golden scenarios. They are validation errors the handler
# rejects before any AI call, so they cost nothing and are not goldened (the
# error message text is volatile).
_INVALID_DIR = _YAML_HANDLER_DIR / "invalid"
_INVALID_SPECS = sorted(_INVALID_DIR.glob("*.yaml"))
_INVALID_IDS = [p.stem for p in _INVALID_SPECS]


@pytest.mark.e2e
@pytest.mark.parametrize("path", _INVALID_SPECS, ids=_INVALID_IDS)
def test_yaml_handler_rejects_invalid_spec(session, handler_env, path):
    """An invalid SPEC must return a non-SUCCEEDED result, not raise or pass."""
    experiment_name = handler_env["fq"](f"YHG_EXP_ERR_{path.stem.upper()}")
    filled = (
        path.read_text(encoding="utf-8")
        .replace(_FUNCTION_TOKEN, handler_env["function_signature"])
        .replace(_METRIC_UDF_TOKEN, handler_env["metric_udf"])
        .replace(_TABLE_TOKEN, handler_env["table"])
    )

    session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()
    create_experiment(session, experiment_name)
    try:
        result = execute_ai_function_eval_opts(
            session,
            {"experiment_name": experiment_name, "run_name": "EVAL"},
            filled,
        )
        print(f"[{path.stem}] handler result: {result}")
        assert isinstance(result, dict), f"{path.stem}: expected a dict result"
        assert result.get("status") != "SUCCEEDED", (
            f"{path.stem}: invalid SPEC unexpectedly SUCCEEDED: {result}"
        )
    finally:
        session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()
