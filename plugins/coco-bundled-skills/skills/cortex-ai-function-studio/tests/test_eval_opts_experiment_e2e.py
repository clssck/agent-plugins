# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""End-to-end coverage for spec-driven evaluation across many YAML input types.

Drives ``EXECUTE_AI_FUNCTION_EVAL_OPTS`` with 10 different evaluation SPEC
YAMLs (a matrix over metric, named vs positional ``$N`` argument mapping,
``metrics`` as list vs mapping, and ``num_eval_runs``), reads each generated
experiment back into a ``{experiment: {run: {metrics, parameters, metadata}}}``
tree, displays it (volatile values redacted), and asserts the tree's structure
and invariants — including that ``num_eval_runs`` > 1 yields EVAL_1..EVAL_N.

Run::

    uv run --group test pytest tests/test_eval_opts_experiment_e2e.py \
        -v -m e2e --connection sfctest-udaif
"""

from __future__ import annotations

import contextlib
import json

import pytest
import yaml

from handlers.execute_eval_opts_handler import (
    _EVAL_RUN_NAME_PREFIX,
    execute_ai_function_eval_opts,
)
from snowflake_ai_optimize.core.experiment import create_experiment
from snowflake_ai_optimize.core.udf_ddl import generate_sql
from snowflake_ai_optimize.core.udf_types import InputParam, OutputField, UDFSpec

_INPUT_COLUMN = "TEXT"
_GROUND_TRUTH_COLUMN = "EXPECTED_LABEL"

# ---------------------------------------------------------------------------
# The 10 evaluation SPEC input types
# ---------------------------------------------------------------------------
# Each config is one distinct YAML shape. ``metric`` is the spec metric name;
# ``metric_engine`` is the canonical name recorded as the run's ``metric_name``
# parameter (``llm-judge`` normalizes to ``llm_judge``).
EVAL_SPEC_CONFIGS: list[dict] = [
    {
        "label": "exact_match / named / list / single",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "exact_match / named / mapping / 2 runs",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "named",
        "metrics_as_mapping": True,
        "num_eval_runs": 2,
    },
    {
        "label": "fuzzy_match / named / list / single",
        "metric": "fuzzy_match",
        "metric_engine": "fuzzy_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "fuzzy_match / positional / list / 3 runs",
        "metric": "fuzzy_match",
        "metric_engine": "fuzzy_match",
        "arg_kind": "positional",
        "metrics_as_mapping": False,
        "num_eval_runs": 3,
    },
    {
        "label": "contains_match / named / list / single",
        "metric": "contains_match",
        "metric_engine": "contains_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "contains_match / named / list / 2 runs",
        "metric": "contains_match",
        "metric_engine": "contains_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 2,
    },
    {
        "label": "exact_match / positional / list / 5 runs",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "positional",
        "metrics_as_mapping": False,
        # 5 > max parallelism (3): exercises the bounded thread pool live.
        "num_eval_runs": 5,
    },
    {
        "label": "exact_match / positional / mapping / single",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "positional",
        "metrics_as_mapping": True,
        "num_eval_runs": 1,
    },
    {
        "label": "llm-judge / named / list / judge_model / single",
        "metric": "llm-judge",
        "metric_engine": "llm_judge",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "judge_model": "llama3.1-8b",
        "num_eval_runs": 1,
    },
    {
        "label": "llm-judge / named / mapping / judge_model / 2 runs",
        "metric": "llm-judge",
        "metric_engine": "llm_judge",
        "arg_kind": "named",
        "metrics_as_mapping": True,
        "judge_model": "llama3.1-8b",
        "num_eval_runs": 2,
    },
]

# Single-run specs record this run name (multi-run specs use EVAL_1..EVAL_N).
# Run names are engine-assigned; a single run is EVAL_1 (never caller-supplied).
_SINGLE_RUN_NAME = f"{_EVAL_RUN_NAME_PREFIX}_1"


def _argument_mapping(arg_kind: str) -> dict[str, str]:
    """Build the dataset argument_mapping for a named or positional spec."""
    if arg_kind == "positional":
        return {"$1": _INPUT_COLUMN}
    return {_INPUT_COLUMN: _INPUT_COLUMN}


def build_eval_spec(config: dict, *, function_signature: str, table: str) -> str:
    """Render one evaluation SPEC config to inline YAML text."""
    metric_entry: dict = {"name": config["metric"]}
    if config.get("judge_model") is not None:
        metric_entry["judge_model"] = config["judge_model"]

    spec = {
        "function": {"function_name": function_signature},
        "metrics": metric_entry if config["metrics_as_mapping"] else [metric_entry],
        "dataset": {
            "name": table,
            "column_mapping": {
                "argument_mapping": _argument_mapping(config["arg_kind"]),
                "ground_truth": _GROUND_TRUTH_COLUMN,
            },
        },
        "evaluation": {"num_eval_runs": config["num_eval_runs"]},
    }
    return yaml.safe_dump(spec, sort_keys=False)


def expected_run_names(config: dict) -> list[str]:
    """Return the run names a spec should produce, in deterministic order."""
    num_eval_runs = config["num_eval_runs"]
    if num_eval_runs <= 1:
        return [_SINGLE_RUN_NAME]
    return [f"{_EVAL_RUN_NAME_PREFIX}_{i}" for i in range(1, num_eval_runs + 1)]


# ---------------------------------------------------------------------------
# The builtin (query_text) evaluation SPEC input types
# ---------------------------------------------------------------------------
# Mirror of EVAL_SPEC_CONFIGS for a **builtin** AI function: the SPEC carries
# ``function.query_text`` (an inline AI_COMPLETE expression that references the
# dataset's TEXT column directly) instead of ``function.function_name``. The
# matrix additionally covers the builtin-only ``with_argument_mapping`` axis —
# for a builtin the mapping is optional (the expression references columns
# directly), so both shapes must round-trip.
_QUERY_TEXT_SENTIMENT = (
    f"AI_COMPLETE('llama3.1-8b', "
    f"'Classify the sentiment as positive or negative. Reply with one word: ' "
    f"|| {_INPUT_COLUMN})"
)
# The builtin function name the handler records for the above expression.
_QUERY_TEXT_FUNCTION_NAME = "AI_COMPLETE"

QUERY_TEXT_EVAL_SPEC_CONFIGS: list[dict] = [
    {
        "label": "query_text exact_match / list / single / arg_mapping",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "metrics_as_mapping": False,
        "with_argument_mapping": True,
        "num_eval_runs": 1,
    },
    {
        "label": "query_text contains_match / list / single / no arg_mapping",
        "metric": "contains_match",
        "metric_engine": "contains_match",
        "metrics_as_mapping": False,
        "with_argument_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "query_text contains_match / mapping / 2 runs / arg_mapping",
        "metric": "contains_match",
        "metric_engine": "contains_match",
        "metrics_as_mapping": True,
        "with_argument_mapping": True,
        "num_eval_runs": 2,
    },
    {
        "label": "query_text fuzzy_match / list / single / no arg_mapping",
        "metric": "fuzzy_match",
        "metric_engine": "fuzzy_match",
        "metrics_as_mapping": False,
        "with_argument_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "query_text exact_match / list / 3 runs / no arg_mapping",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "metrics_as_mapping": False,
        "with_argument_mapping": False,
        "num_eval_runs": 3,
    },
    {
        "label": "query_text llm-judge / mapping / single / judge_model / arg_mapping",
        "metric": "llm-judge",
        "metric_engine": "llm_judge",
        "metrics_as_mapping": True,
        "with_argument_mapping": True,
        "judge_model": "llama3.1-8b",
        "num_eval_runs": 1,
    },
]


def build_query_text_eval_spec(config: dict, *, query_text: str, table: str) -> str:
    """Render one builtin (query_text) evaluation SPEC config to inline YAML.

    Unlike :func:`build_eval_spec`, the ``function`` carries ``query_text`` and
    ``argument_mapping`` is optional (governed by ``config['with_argument_mapping']``).
    """
    metric_entry: dict = {"name": config["metric"]}
    if config.get("judge_model") is not None:
        metric_entry["judge_model"] = config["judge_model"]

    column_mapping: dict = {"ground_truth": _GROUND_TRUTH_COLUMN}
    if config["with_argument_mapping"]:
        column_mapping["argument_mapping"] = {_INPUT_COLUMN: _INPUT_COLUMN}

    spec = {
        "function": {"query_text": query_text},
        "metrics": metric_entry if config["metrics_as_mapping"] else [metric_entry],
        "dataset": {"name": table, "column_mapping": column_mapping},
        "evaluation": {"num_eval_runs": config["num_eval_runs"]},
    }
    return yaml.safe_dump(spec, sort_keys=False)


def build_experiment_tree(session, experiment_name: str) -> dict:
    """Read an experiment's runs into a per-run metrics/parameters/metadata map."""

    def to_number(value: object) -> float | str | None:
        if value is None:
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(value)

    tree: dict = {}
    runs = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
    for run in runs:
        run_name = run["name"]
        # SHOW RUNS metadata is external data; tolerate a malformed field.
        try:
            metadata = json.loads(run["metadata"]) if run["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        metric_rows = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        metrics = {m["name"]: to_number(m["value"]) for m in metric_rows}

        param_rows = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        parameters = {
            p["name"]: (None if p["value"] is None else str(p["value"]))
            for p in param_rows
        }

        tree[run_name] = {
            "metrics": metrics,
            "parameters": parameters,
            "metadata": metadata,
        }
    return tree


# ---------------------------------------------------------------------------
# Display normalization (redact nondeterministic values to stable tokens)
# ---------------------------------------------------------------------------
_NUMBER_TOKEN = "<number>"
_REDACTED_TOKEN = "<redacted>"
_STABLE_METADATA_KEYS = {"status"}
# Parameter names whose values vary run-to-run (timings, token/char counts).
_VOLATILE_PARAM_SUFFIXES = (
    "_seconds",
    "_tokens",
    "_chars",
    "_dollars",
    "_calls",
    "_count",
)


def normalize_tree_for_display(tree: dict) -> dict:
    """Return a copy of the tree with nondeterministic values redacted.

    Metric values become ``<number>``, volatile parameters and non-status
    metadata become ``<redacted>``. The result depends only on the tree's
    *shape and deterministic fields*, so it is identical across runs that
    differ solely in scores/timings/timestamps.
    """
    display: dict = {}
    for experiment_name, runs in tree.items():
        display[experiment_name] = {}
        for run_name, body in runs.items():
            metrics = dict.fromkeys(body.get("metrics", {}), _NUMBER_TOKEN)
            parameters = {
                name: (
                    _REDACTED_TOKEN
                    if name.endswith(_VOLATILE_PARAM_SUFFIXES)
                    else value
                )
                for name, value in body.get("parameters", {}).items()
            }
            metadata = {
                key: (value if key in _STABLE_METADATA_KEYS else _REDACTED_TOKEN)
                for key, value in body.get("metadata", {}).items()
            }
            display[experiment_name][run_name] = {
                "metrics": metrics,
                "parameters": parameters,
                "metadata": metadata,
            }
    return display


# ---------------------------------------------------------------------------
# Deterministic (offline) tests for the config matrix + display normalizer
# ---------------------------------------------------------------------------


def _fake_run_body(
    *,
    score: float,
    elapsed: float,
    created_on: str = "2026-07-10T00:00:00Z",
    estimated_cost: float | None = None,
) -> dict:
    """Build a run body matching what the eval path records (for offline tests)."""
    metrics: dict = {"score": score}
    if estimated_cost is not None:
        metrics["estimated_cost"] = estimated_cost
    return {
        "metrics": metrics,
        "parameters": {
            "function_impl": "",
            "model": "llama3.1-8b",
            "iteration": "0",
            "is_full_eval": "true",
            "status": "completed",
            "function_name": "db.sch.f(VARCHAR)",
            "metric_name": "exact_match",
            "custom_metric_udf": "",
            "num_examples": "4",
            "elapsed_seconds": str(elapsed),
        },
        "metadata": {"status": "FINISHED", "created_on": created_on},
    }


def _fake_tree(score: float, elapsed: float, created_on: str, cost: float) -> dict:
    """A representative two-experiment tree (single-run + multi-run)."""
    return {
        "db.sch.EXP_1": {
            "EVAL": _fake_run_body(score=score, elapsed=elapsed, created_on=created_on)
        },
        "db.sch.EXP_2": {
            "EVAL_1": _fake_run_body(
                score=score, elapsed=elapsed, created_on=created_on, estimated_cost=cost
            ),
            "EVAL_2": _fake_run_body(
                score=score, elapsed=elapsed, created_on=created_on, estimated_cost=cost
            ),
        },
    }


class TestTreeHelpers:
    """Offline checks for the config matrix and the display normalizer."""

    def test_configs_cover_ten_input_types(self):
        assert len(EVAL_SPEC_CONFIGS) == 10
        # Every config renders to parseable YAML with the required sections.
        for config in EVAL_SPEC_CONFIGS:
            spec_text = build_eval_spec(
                config, function_signature="db.sch.f(VARCHAR)", table="db.sch.t"
            )
            spec = yaml.safe_load(spec_text)
            assert "evaluation" in spec and "function" in spec and "dataset" in spec
            assert spec["evaluation"]["num_eval_runs"] == config["num_eval_runs"]

    def test_query_text_configs_render_builtin_specs(self):
        # Every builtin (query_text) config renders parseable YAML that carries
        # function.query_text (never function_name), and honors the optional
        # argument_mapping axis.
        for config in QUERY_TEXT_EVAL_SPEC_CONFIGS:
            spec_text = build_query_text_eval_spec(
                config, query_text=_QUERY_TEXT_SENTIMENT, table="db.sch.t"
            )
            spec = yaml.safe_load(spec_text)
            assert spec["function"]["query_text"] == _QUERY_TEXT_SENTIMENT
            assert "function_name" not in spec["function"]
            assert spec["dataset"]["column_mapping"]["ground_truth"]
            has_mapping = "argument_mapping" in spec["dataset"]["column_mapping"]
            assert has_mapping == config["with_argument_mapping"]
            assert spec["evaluation"]["num_eval_runs"] == config["num_eval_runs"]

    def test_normalizer_stable_across_nondeterministic_values(self):
        # Two trees differing ONLY in nondeterministic values normalize to the
        # identical display — the robustness guarantee.
        tree_a = _fake_tree(0.5, 1.23, "2026-07-10T00:00:00Z", 0.001)
        tree_b = _fake_tree(0.875, 42.9, "2026-12-31T23:59:59Z", 0.99)
        assert normalize_tree_for_display(tree_a) == normalize_tree_for_display(tree_b)

    def test_normalizer_redacts_volatile_but_keeps_deterministic(self):
        display = normalize_tree_for_display(
            _fake_tree(0.5, 1.23, "2026-07-10T00:00:00Z", 0.001)
        )
        run = display["db.sch.EXP_1"]["EVAL"]
        assert run["metrics"]["score"] == _NUMBER_TOKEN
        assert run["parameters"]["elapsed_seconds"] == _REDACTED_TOKEN
        # deterministic fields survive redaction
        assert run["parameters"]["metric_name"] == "exact_match"
        assert run["parameters"]["model"] == "llama3.1-8b"
        assert run["parameters"]["num_examples"] == "4"
        assert run["metadata"]["status"] == "FINISHED"
        assert run["metadata"]["created_on"] == _REDACTED_TOKEN


# ---------------------------------------------------------------------------
# Live end-to-end test
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def eval_env(session, cleanup_stale, run_key):
    """Provision a classifier UDF + labeled dataset; drop everything after."""
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')

    def fq(name: str) -> str:
        return f"{db}.{schema}.{name}"

    cleanup_stale(
        session,
        db,
        schema,
        tables=["TEST_EVALOPTS_DATA"],
        functions=["TEST_EVALOPTS_CLASSIFY"],
        experiments=["TEST_EVALOPTS_EXP"],
    )

    func = f"TEST_EVALOPTS_CLASSIFY_{run_key}"
    table = f"TEST_EVALOPTS_DATA_{run_key}"
    func_fqn = fq(func)
    table_fqn = fq(table)

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
    rows = [
        ("I love this product!", "positive"),
        ("Great experience overall", "positive"),
        ("Terrible, worst purchase ever", "negative"),
        ("Awful quality and bad service", "negative"),
    ]
    values = ", ".join(f"('{text}', '{label}')" for text, label in rows)
    session.sql(f"INSERT INTO {table_fqn} VALUES {values}").collect()

    experiment_names = [
        fq(f"TEST_EVALOPTS_EXP_{run_key}_{i}")
        for i in range(1, len(EVAL_SPEC_CONFIGS) + 1)
    ]

    yield {
        "function_signature": f"{func_fqn}(VARCHAR)",
        "table": table_fqn,
        "row_count": len(rows),
        "experiment_names": experiment_names,
    }

    session.sql(f"DROP FUNCTION IF EXISTS {func_fqn}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {table_fqn}").collect()
    for experiment_name in experiment_names:
        session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()


@pytest.mark.e2e
class TestEvalOptsExperimentsE2E:
    """Run 10 eval SPEC types, build the experiment tree, and validate it."""

    def test_ten_eval_specs_build_valid_experiment_tree(self, session, eval_env):
        function_signature = eval_env["function_signature"]
        table = eval_env["table"]
        row_count = eval_env["row_count"]
        experiment_names = eval_env["experiment_names"]

        tree: dict = {}
        for config, experiment_name in zip(
            EVAL_SPEC_CONFIGS, experiment_names, strict=True
        ):
            spec_text = build_eval_spec(
                config, function_signature=function_signature, table=table
            )
            # The DDL layer (EXECUTE EXPERIMENT) creates the experiment before
            # the SPROC runs; the handler never creates it, so simulate that here.
            create_experiment(session, experiment_name)
            params: dict = {"experiment_name": experiment_name}

            result = execute_ai_function_eval_opts(session, params, spec_text)
            assert result["status"] == "SUCCEEDED", (
                f"{config['label']} did not succeed: {result}"
            )

            # The handler's own report of which runs it created.
            if config["num_eval_runs"] <= 1:
                assert result["run"] == _SINGLE_RUN_NAME
            else:
                assert result["runs"] == expected_run_names(config), (
                    f"{config['label']} run names mismatch: {result.get('runs')}"
                )

            tree[experiment_name] = build_experiment_tree(session, experiment_name)

        # ---- Display the generated experiment tree (stable / redacted) ----
        print(
            "\nGenerated experiment tree (nondeterministic values redacted):\n"
            + json.dumps(normalize_tree_for_display(tree), indent=2, sort_keys=True)
        )

        # ---- Per-spec structural + invariant assertions ----
        assert len(tree) == len(EVAL_SPEC_CONFIGS)
        for config, experiment_name in zip(
            EVAL_SPEC_CONFIGS, experiment_names, strict=True
        ):
            runs = tree[experiment_name]
            assert set(runs) == set(expected_run_names(config)), (
                f"{config['label']} produced runs {sorted(runs)}, "
                f"expected {expected_run_names(config)}"
            )
            for run_name, body in runs.items():
                params = body["parameters"]
                assert body["metadata"]["status"] == "FINISHED", (
                    f"{config['label']} run {run_name} not committed"
                )
                assert params["status"] == "completed"
                assert params["metric_name"] == config["metric_engine"]
                assert params["num_examples"] == str(row_count)
                assert params["model"], (
                    f"{config['label']} run {run_name} missing model"
                )
                assert params["function_name"] == function_signature
                assert "iteration" in params
                score = body["metrics"]["score"]
                assert score is not None and 0.0 <= float(score) <= 1.0, (
                    f"{config['label']} run {run_name} score out of range: {score}"
                )


# ---------------------------------------------------------------------------
# Builtin AI function (query_text) end-to-end
# ---------------------------------------------------------------------------


def _query_text_experiment_name(table_fqn: str, suffix: str) -> str:
    """Derive a fully-qualified experiment name in the dataset's db.schema."""
    db, schema, _rest = table_fqn.split(".", 2)
    return f"{db}.{schema}.TEST_EVALOPTS_QT_{suffix}"


@pytest.mark.e2e
class TestQueryTextEvalOptsE2E:
    """Builtin AI function (``query_text``) evaluation + optimization, live.

    Reuses the ``eval_env`` sentiment dataset (``TEXT`` + ``EXPECTED_LABEL``)
    but drives the handler with a ``function.query_text`` inline ``AI_COMPLETE``
    expression instead of a user ``function_name`` — the builtin path. Each test
    provisions and drops its own experiment.
    """

    def test_query_text_evaluation(self, session, eval_env, run_key):
        """A builtin query_text eval scores every row and persists one run.

        Exercises the cost path (the expression is ``AI_COMPLETE``, so
        ``show_details`` token capture applies) with ``argument_mapping``
        omitted — the expression references ``TEXT`` directly.
        """
        table = eval_env["table"]
        row_count = eval_env["row_count"]
        experiment_name = _query_text_experiment_name(table, f"EVAL_{run_key}")
        query_text = (
            "AI_COMPLETE('llama3.1-8b', "
            "'Classify the sentiment as positive or negative. Reply with one word: ' "
            f"|| {_INPUT_COLUMN})"
        )
        spec = yaml.safe_dump(
            {
                "function": {"query_text": query_text},
                "metrics": [{"name": "contains_match"}],
                "dataset": {
                    "name": table,
                    "column_mapping": {"ground_truth": _GROUND_TRUTH_COLUMN},
                },
                "evaluation": {"num_eval_runs": 1},
            },
            sort_keys=False,
        )
        try:
            # Simulate the DDL layer creating the experiment up front.
            create_experiment(session, experiment_name)
            result = execute_ai_function_eval_opts(
                session,
                {"experiment_name": experiment_name},
                spec,
            )
            assert result["status"] == "SUCCEEDED", result
            assert result["run"] == _SINGLE_RUN_NAME
            assert result["num_examples"] == row_count
            score = result["metrics"]["contains_match"]
            assert 0.0 <= float(score) <= 1.0, f"score out of range: {score}"

            tree = build_experiment_tree(session, experiment_name)
            assert set(tree) == {_SINGLE_RUN_NAME}, f"unexpected runs: {sorted(tree)}"
            params = tree[_SINGLE_RUN_NAME]["parameters"]
            assert tree[_SINGLE_RUN_NAME]["metadata"]["status"] == "FINISHED"
            assert params["status"] == "completed"
            assert params["metric_name"] == "contains_match"
            assert params["num_examples"] == str(row_count)
            # The builtin expression is recorded as the run's function_name.
            assert "AI_COMPLETE" in params["function_name"], params["function_name"]
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_query_text_optimization_body_mode(self, session, eval_env, run_key):
        """A builtin query_text body-mode optimize completes and writes runs.

        Threads ``query_text`` through the optimizer: the seed candidate is the
        expression itself (no ``DESCRIBE FUNCTION``), candidates are evaluated
        via the inline executor, and results persist to the experiment. Uses
        ``budget: ultra-light`` (2 proposals) to stay fast. (The legacy ``demo``
        alias was removed from the accepted spec budgets in #127; the spec path
        accepts only the canonical preset names.)
        """
        # Register the production body/prompt optimize modes. The deployed SPROC
        # does this via the bundled _registry.py; the package/test path registers
        # by importing the gepa package (its __init__ calls register_all()).
        import snowflake_ai_optimize.gepa  # noqa: F401

        table = eval_env["table"]
        experiment_name = _query_text_experiment_name(table, f"OPT_{run_key}")
        query_text = (
            "AI_COMPLETE('llama3.1-8b', "
            "'Classify sentiment as positive or negative: ' "
            f"|| {_INPUT_COLUMN})"
        )
        spec = yaml.safe_dump(
            {
                "function": {"query_text": query_text},
                "metrics": [{"name": "contains_match"}],
                "dataset": {
                    "name": table,
                    "column_mapping": {
                        "argument_mapping": {_INPUT_COLUMN: _INPUT_COLUMN},
                        "ground_truth": _GROUND_TRUTH_COLUMN,
                    },
                    "holdout_data": table,
                },
                "optimization": {
                    "models": ["llama3.1-8b"],
                    "budget": "ultra-light",
                    "optimize_mode": "body",
                    "validation_fraction": 0.5,
                },
            },
            sort_keys=False,
        )
        try:
            # Simulate the DDL layer creating the experiment up front; the
            # optimizer attaches SEED / ITER_<N> runs but never creates it.
            create_experiment(session, experiment_name)
            result = execute_ai_function_eval_opts(
                session,
                {"experiment_name": experiment_name},
                spec,
            )
            assert result["status"] == "SUCCEEDED", result
            assert result.get("experiment") == experiment_name
            assert "error" not in result, f"optimization surfaced an error: {result}"

            # The optimizer reports a best score for the seeded query_text.
            best = result.get("overall_best_score")
            if best is None:
                best = result.get("overall_best_val_score")
            assert best is not None and 0.0 <= float(best) <= 1.0, (
                f"overall best score out of range: {best!r}"
            )

            # Optimization persisted the SEED run with a numeric validation score
            # (opt runs record valset_score/test_score, not a bare 'score').
            tree = build_experiment_tree(session, experiment_name)
            assert "SEED" in tree, f"expected a SEED run; got {sorted(tree)}"
            seed_metrics = tree["SEED"]["metrics"]
            val = seed_metrics.get("valset_score")
            if val is None:
                val = seed_metrics.get("test_score")
            assert val is not None and 0.0 <= float(val) <= 1.0, (
                f"SEED run missing a numeric validation score: {seed_metrics}"
            )
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_query_text_eval_error_commits_failed_run(self, session, eval_env, run_key):
        """A broken query_text surfaces as a FAILED EVAL_1 with an error param.

        The query_text references a column that does not exist on the dataset,
        so the up-front compile probe (``SELECT (query_text) ... WHERE FALSE``)
        fails with zero AI cost — no ``AI_COMPLETE`` executes. The handler must
        NOT raise: it records the reason in EVAL_1's ``error_message`` PARAMETER
        and commits EVAL_1 ``FAILED``, returning ``status="FAILED"``.

        Asserts BOTH channels: SHOW RUNS metadata shows status FAILED (metadata
        has no error field), and SHOW RUN PARAMETERS carries error_message.
        """
        table = eval_env["table"]
        experiment_name = _query_text_experiment_name(table, f"FAIL_{run_key}")
        # NO_SUCH_COLUMN is absent from the dataset → the compile probe fails.
        query_text = "AI_COMPLETE('llama3.1-8b', 'Classify: ' || NO_SUCH_COLUMN_XYZ)"
        spec = yaml.safe_dump(
            {
                "function": {"query_text": query_text},
                "metrics": [{"name": "contains_match"}],
                "dataset": {
                    "name": table,
                    "column_mapping": {"ground_truth": _GROUND_TRUTH_COLUMN},
                },
                "evaluation": {"num_eval_runs": 1},
            },
            sort_keys=False,
        )
        try:
            # The handler never creates the experiment, so the DDL layer's
            # creation must be simulated here first.
            create_experiment(session, experiment_name)
            result = execute_ai_function_eval_opts(
                session,
                {"experiment_name": experiment_name},
                spec,
            )
            # Returned normally (no raise) with a FAILED status + error_message.
            assert result["status"] == "FAILED", result
            assert result["run"] == _SINGLE_RUN_NAME
            assert result["error_message"]

            # SHOW RUNS metadata: EVAL_1 exists and is committed FAILED.
            tree = build_experiment_tree(session, experiment_name)
            assert set(tree) == {_SINGLE_RUN_NAME}, f"unexpected runs: {sorted(tree)}"
            assert tree[_SINGLE_RUN_NAME]["metadata"]["status"] == "FAILED"
            # SHOW RUN PARAMETERS: the reason is recorded as a run parameter
            # (metadata has no error field), plus status=failed.
            params = tree[_SINGLE_RUN_NAME]["parameters"]
            assert params.get("error_message"), (
                f"EVAL_1 missing error_message parameter: {params}"
            )
            assert params.get("status") == "failed"
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_query_text_eval_specs_build_valid_experiment_tree(
        self, session, eval_env, run_key
    ):
        """Run the builtin query_text eval SPEC matrix and validate each run.

        The builtin analogue of ``test_ten_eval_specs_build_valid_experiment_tree``:
        drives ``EXECUTE_AI_FUNCTION_EVAL_OPTS`` with the builtin query_text SPEC
        shapes (metric x list/mapping x with/without argument_mapping), reads each
        experiment back, and asserts structure + invariants — including that the
        run records function_name = the builtin name (AI_COMPLETE) and
        function_impl = the query_text.

        Live coverage is limited to the single-run configs to keep this test's
        concurrent AI_COMPLETE load modest — under xdist LoadFileScheduling it
        runs in parallel with other AI_COMPLETE-heavy e2e files, and the
        num_eval_runs>1 fan-out (a ThreadPoolExecutor of parallel calls) would
        add contention on the shared warehouse. The full matrix (including the
        multi-run configs) is exercised offline by
        ``TestTreeHelpers.test_query_text_configs_render_builtin_specs``, and
        num_eval_runs>1 fan-out is covered live by the user-function matrix
        (``TestEvalOptsExperimentsE2E``) and by the handler unit tests.
        """
        table = eval_env["table"]
        row_count = eval_env["row_count"]
        live_configs = [
            c for c in QUERY_TEXT_EVAL_SPEC_CONFIGS if c["num_eval_runs"] == 1
        ]
        experiment_names = [
            _query_text_experiment_name(table, f"MATRIX_{run_key}_{i}")
            for i in range(len(live_configs))
        ]
        try:
            tree: dict = {}
            for config, experiment_name in zip(
                live_configs, experiment_names, strict=True
            ):
                spec_text = build_query_text_eval_spec(
                    config, query_text=_QUERY_TEXT_SENTIMENT, table=table
                )
                params: dict = {"experiment_name": experiment_name}
                # Simulate the DDL layer creating the experiment up front.
                create_experiment(session, experiment_name)

                result = execute_ai_function_eval_opts(session, params, spec_text)
                assert result["status"] == "SUCCEEDED", (
                    f"{config['label']} did not succeed: {result}"
                )
                if config["num_eval_runs"] <= 1:
                    assert result["run"] == _SINGLE_RUN_NAME
                else:
                    assert result["runs"] == expected_run_names(config), (
                        f"{config['label']} run names mismatch: {result.get('runs')}"
                    )
                tree[experiment_name] = build_experiment_tree(session, experiment_name)

            print(
                "\nGenerated query_text experiment tree (redacted):\n"
                + json.dumps(normalize_tree_for_display(tree), indent=2, sort_keys=True)
            )

            assert len(tree) == len(live_configs)
            for config, experiment_name in zip(
                live_configs, experiment_names, strict=True
            ):
                runs = tree[experiment_name]
                assert set(runs) == set(expected_run_names(config)), (
                    f"{config['label']} produced runs {sorted(runs)}, "
                    f"expected {expected_run_names(config)}"
                )
                for run_name, body in runs.items():
                    p = body["parameters"]
                    assert body["metadata"]["status"] == "FINISHED", (
                        f"{config['label']} run {run_name} not committed"
                    )
                    assert p["status"] == "completed"
                    assert p["metric_name"] == config["metric_engine"]
                    assert p["num_examples"] == str(row_count)
                    # Shared protocol: builtin records function_name = the builtin
                    # name and function_impl = the query_text.
                    assert p["function_name"] == _QUERY_TEXT_FUNCTION_NAME
                    assert p["function_impl"] == _QUERY_TEXT_SENTIMENT
                    score = body["metrics"]["score"]
                    assert score is not None and 0.0 <= float(score) <= 1.0, (
                        f"{config['label']} run {run_name} score out of range: {score}"
                    )
        finally:
            for experiment_name in experiment_names:
                session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()


# ---------------------------------------------------------------------------
# Snowflake DATASET object as dataset.name (SNOW-3802299) — live end-to-end
# ---------------------------------------------------------------------------
# A DATASET is a versioned container that is NOT queryable via a bare
# ``FROM``/``DESCRIBE TABLE``. Resolution is version-gated: when a
# ``dataset.version`` is supplied, the handler reads ``dataset.name`` as a
# DATASET (via the snowflake.ml Dataset API) at that version and materializes it
# to a session temp view; with no version it is treated as a plain table/view.
# The version is forwarded verbatim (no default/latest resolution). These tests
# create a REAL DATASET with multiple versions and exercise the corner cases
# end-to-end.

_DATASET_INPUT_COLUMN = "TEXT"
_DATASET_GT_COLUMN = "EXPECTED_LABEL"
# A varied-type column carried alongside the text so the materialized view is
# verified to preserve non-VARCHAR columns (argument_mapping only maps TEXT).
_DATASET_SCORE_COLUMN = "SCORE"


def _dataset_experiment_name(dataset_fqn: str, suffix: str) -> str:
    """Derive a fully-qualified experiment name in the dataset's db.schema."""
    db, schema, _rest = dataset_fqn.split(".", 2)
    return f"{db}.{schema}.TEST_EVALOPTS_DS_EXP_{suffix}"


@pytest.fixture(scope="module")
def dataset_env(session, cleanup_stale, run_key):
    """Provision a classifier UDF + a real DATASET with two versions; drop after.

    The DATASET is built with pure SQL (``CREATE DATASET`` +
    ``ALTER DATASET ... ADD VERSION ... FROM (<query>)``) so no snowflake.ml
    import is needed for setup. Two versions are created (``V1``, ``V2``): the
    explicit-version test reads ``V2`` (correct labels), and having a second
    version present confirms the handler forwards the caller's chosen version
    verbatim rather than guessing. ``V1`` intentionally has wrong labels so
    selecting the wrong version would be observable via the score.
    """
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')

    def fq(name: str) -> str:
        return f"{db}.{schema}.{name}"

    cleanup_stale(
        session,
        db,
        schema,
        tables=[
            "TEST_EVALOPTS_DS_TABLE",
            "TEST_EVALOPTS_DS_V1SRC",
            "TEST_EVALOPTS_DS_V2SRC",
        ],
        functions=["TEST_EVALOPTS_DS_CLASSIFY"],
        experiments=["TEST_EVALOPTS_DS_EXP"],
    )

    func = f"TEST_EVALOPTS_DS_CLASSIFY_{run_key}"
    dataset = f"TEST_EVALOPTS_DS_{run_key}"
    func_fqn = fq(func)
    dataset_fqn = fq(dataset)

    # Best-effort drop of a stale dataset from a prior run of this branch (the
    # shared cleanup helper does not know about DATASET objects).
    for row in session.sql(
        f"SHOW DATASETS LIKE 'TEST_EVALOPTS_DS_%' IN SCHEMA {db}.{schema}"
    ).collect():
        with contextlib.suppress(Exception):
            session.sql(f"DROP DATASET IF EXISTS {fq(row['name'])}").collect()

    udf_spec = UDFSpec(
        database=db,
        schema=schema,
        function_name=func,
        model="llama3.1-8b",
        function_intention="Classify text sentiment as positive or negative",
        inputs=[InputParam(name=_DATASET_INPUT_COLUMN, sql_type="VARCHAR")],
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

    # Correct-label rows (used for V2).
    correct_rows = [
        ("I love this product!", "positive", 0.95),
        ("Great experience overall", "positive", 0.90),
        ("Terrible, worst purchase ever", "negative", 0.10),
        ("Awful quality and bad service", "negative", 0.05),
    ]
    # V1 flips two labels so its exact_match score is measurably lower than V2 —
    # selecting the wrong version would be observable via the score.
    v1_rows = [
        ("I love this product!", "negative", 0.95),
        ("Great experience overall", "negative", 0.90),
        ("Terrible, worst purchase ever", "negative", 0.10),
        ("Awful quality and bad service", "negative", 0.05),
    ]

    def _values(rows):
        return ", ".join(f"('{t}', '{lbl}', {score})" for (t, lbl, score) in rows)

    cols_ddl = (
        f"{_DATASET_INPUT_COLUMN} VARCHAR, "
        f"{_DATASET_GT_COLUMN} VARCHAR, "
        f"{_DATASET_SCORE_COLUMN} FLOAT"
    )

    # Source tables feeding each dataset version (ADD VERSION FROM (<query>)).
    v1_src = fq(f"TEST_EVALOPTS_DS_V1SRC_{run_key}")
    v2_src = fq(f"TEST_EVALOPTS_DS_V2SRC_{run_key}")
    session.sql(f"CREATE OR REPLACE TABLE {v1_src} ({cols_ddl})").collect()
    session.sql(f"INSERT INTO {v1_src} VALUES {_values(v1_rows)}").collect()
    session.sql(f"CREATE OR REPLACE TABLE {v2_src} ({cols_ddl})").collect()
    session.sql(f"INSERT INTO {v2_src} VALUES {_values(correct_rows)}").collect()

    # Build the DATASET with two versions (V1 older, V2 newer/latest).
    session.sql(f"CREATE DATASET IF NOT EXISTS {dataset_fqn}").collect()
    session.sql(
        f"ALTER DATASET {dataset_fqn} ADD VERSION 'V1' FROM (SELECT * FROM {v1_src})"
    ).collect()
    session.sql(
        f"ALTER DATASET {dataset_fqn} ADD VERSION 'V2' FROM (SELECT * FROM {v2_src})"
    ).collect()

    yield {
        "function_signature": f"{func_fqn}(VARCHAR)",
        "dataset": dataset_fqn,
        "row_count": len(correct_rows),
    }

    session.sql(f"DROP FUNCTION IF EXISTS {func_fqn}(VARCHAR)").collect()
    session.sql(f"DROP DATASET IF EXISTS {dataset_fqn}").collect()
    session.sql(f"DROP TABLE IF EXISTS {v1_src}").collect()
    session.sql(f"DROP TABLE IF EXISTS {v2_src}").collect()


def _build_eval_spec_for_source(
    *, function_signature: str, source: str, version: str | None = None
) -> str:
    """Render an exact_match eval SPEC over a DATASET source."""
    dataset_block: dict = {
        "name": source,
        "column_mapping": {
            "argument_mapping": {_DATASET_INPUT_COLUMN: _DATASET_INPUT_COLUMN},
            "ground_truth": _DATASET_GT_COLUMN,
        },
    }
    if version is not None:
        dataset_block["version"] = version
    spec = {
        "function": {"function_name": function_signature},
        "metrics": [{"name": "exact_match"}],
        "dataset": dataset_block,
        "evaluation": {"num_eval_runs": 1},
    }
    return yaml.safe_dump(spec, sort_keys=False)


@pytest.mark.e2e
class TestDatasetObjectE2E:
    """Live coverage for a Snowflake DATASET object as ``dataset.name``.

    Creates a real ``SNOWFLAKE.ML.DATASET`` with two versions and exercises the
    corner cases: an explicit ``dataset.version`` (the DATASET read path), a
    DATASET name with no version (treated as a table → fails to query), an
    unknown version (the ``snowflake.ml`` API raises — we no longer pre-validate),
    holdout dataset + ``holdout_version``, dataset on both eval and optimization
    paths, varied column types preserved through the materialized view, and the
    builtin ``query_text``-over-dataset path.

    Resolution is version-gated: a ``dataset.version`` (and ``holdout_version``
    for a DATASET holdout) opts into the DATASET read path; the ``snowflake.ml``
    API selects that concrete version with no default/latest resolution.
    """

    def _run_eval(self, session, experiment_name, spec_text):
        create_experiment(session, experiment_name)
        return execute_ai_function_eval_opts(
            session, {"experiment_name": experiment_name}, spec_text
        )

    def test_dataset_explicit_version(self, session, dataset_env, run_key):
        # dataset.version: V2 (correct labels) resolves + scores every row.
        experiment_name = _dataset_experiment_name(
            dataset_env["dataset"], f"EXPLICIT_{run_key}"
        )
        spec = _build_eval_spec_for_source(
            function_signature=dataset_env["function_signature"],
            source=dataset_env["dataset"],
            version="V2",
        )
        try:
            result = self._run_eval(session, experiment_name, spec)
            assert result["status"] == "SUCCEEDED", result
            assert result["run"] == _SINGLE_RUN_NAME
            assert result["num_examples"] == dataset_env["row_count"]
            tree = build_experiment_tree(session, experiment_name)
            params = tree[_SINGLE_RUN_NAME]["parameters"]
            assert params["num_examples"] == str(dataset_env["row_count"])
            assert params["function_name"] == dataset_env["function_signature"]
            score = tree[_SINGLE_RUN_NAME]["metrics"]["score"]
            assert score is not None and 0.0 <= float(score) <= 1.0
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_dataset_without_version_treated_as_table_fails(
        self, session, dataset_env, run_key
    ):
        # Version-gated: a DATASET name with NO version is treated as a plain
        # table/view and queried directly. A DATASET is not queryable via a bare
        # FROM/DESCRIBE, so the run fails cleanly (FAILED EVAL_1 with an
        # error_message) rather than raising — the version is what opts into the
        # DATASET read path.
        experiment_name = _dataset_experiment_name(
            dataset_env["dataset"], f"NOVER_{run_key}"
        )
        spec = _build_eval_spec_for_source(
            function_signature=dataset_env["function_signature"],
            source=dataset_env["dataset"],
            version=None,  # no version -> treated as a table, not a DATASET
        )
        try:
            result = self._run_eval(session, experiment_name, spec)
            assert result["status"] == "FAILED", result
            assert result["run"] == _SINGLE_RUN_NAME
            # Snowflake's own error for querying a DATASET as a table; just
            # assert it surfaced (message text is Snowflake's, not ours).
            assert result["error_message"]
            tree = build_experiment_tree(session, experiment_name)
            assert tree[_SINGLE_RUN_NAME]["metadata"]["status"] == "FAILED"
            assert tree[_SINGLE_RUN_NAME]["parameters"].get("error_message")
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_dataset_unknown_version_fails_cleanly(self, session, dataset_env, run_key):
        # An unknown version is forwarded verbatim to the snowflake.ml API (we no
        # longer pre-validate/enumerate versions); the API's own "version does
        # not exist" error surfaces as a FAILED EVAL_1 — the handler never raises.
        experiment_name = _dataset_experiment_name(
            dataset_env["dataset"], f"BADVER_{run_key}"
        )
        spec = _build_eval_spec_for_source(
            function_signature=dataset_env["function_signature"],
            source=dataset_env["dataset"],
            version="NOPE_V999",
        )
        try:
            result = self._run_eval(session, experiment_name, spec)
            assert result["status"] == "FAILED", result
            assert result["run"] == _SINGLE_RUN_NAME
            # The message is the ML API's, not our own; just assert it is present
            # and references the bad version.
            assert result["error_message"]
            assert "NOPE_V999" in result["error_message"]
            tree = build_experiment_tree(session, experiment_name)
            assert tree[_SINGLE_RUN_NAME]["metadata"]["status"] == "FAILED"
            assert tree[_SINGLE_RUN_NAME]["parameters"].get("error_message")
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_dataset_varied_column_types_preserved(self, session, dataset_env, run_key):
        # The dataset carries a FLOAT SCORE column alongside the VARCHAR text +
        # label. After materialization the view must expose all columns with
        # their types; DESCRIBE the resolved source is exercised indirectly by
        # the successful eval, and here we assert the extra typed column is
        # queryable through a builtin query_text that references it.
        experiment_name = _dataset_experiment_name(
            dataset_env["dataset"], f"TYPES_{run_key}"
        )
        # query_text references BOTH the VARCHAR TEXT and the FLOAT SCORE column,
        # proving the materialized view preserved the non-mapped typed column.
        query_text = (
            "AI_COMPLETE('llama3.1-8b', "
            "'Classify sentiment (score ' || TO_VARCHAR(SCORE) || '): ' "
            f"|| {_DATASET_INPUT_COLUMN})"
        )
        spec = yaml.safe_dump(
            {
                "function": {"query_text": query_text},
                "metrics": [{"name": "contains_match"}],
                "dataset": {
                    "name": dataset_env["dataset"],
                    "version": "V2",
                    "column_mapping": {"ground_truth": _DATASET_GT_COLUMN},
                },
                "evaluation": {"num_eval_runs": 1},
            },
            sort_keys=False,
        )
        try:
            result = self._run_eval(session, experiment_name, spec)
            assert result["status"] == "SUCCEEDED", result
            assert result["num_examples"] == dataset_env["row_count"]
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()

    def test_dataset_optimization_with_holdout_dataset(
        self, session, dataset_env, run_key
    ):
        # The optimization path resolves BOTH a DATASET training source and a
        # DATASET holdout (with holdout_version) to temp views, then optimizes.
        import snowflake_ai_optimize.gepa  # noqa: F401  (register optimize modes)

        experiment_name = _dataset_experiment_name(
            dataset_env["dataset"], f"OPT_{run_key}"
        )
        query_text = (
            "AI_COMPLETE('llama3.1-8b', 'Classify sentiment as "
            f"positive or negative: ' || {_DATASET_INPUT_COLUMN})"
        )
        spec = yaml.safe_dump(
            {
                "function": {"query_text": query_text},
                "metrics": [{"name": "contains_match"}],
                "dataset": {
                    "name": dataset_env["dataset"],
                    "version": "V2",
                    "column_mapping": {
                        "argument_mapping": {
                            _DATASET_INPUT_COLUMN: _DATASET_INPUT_COLUMN
                        },
                        "ground_truth": _DATASET_GT_COLUMN,
                    },
                    # Holdout is the SAME dataset, explicit version → its own
                    # materialized temp view.
                    "holdout_data": dataset_env["dataset"],
                    "holdout_version": "V2",
                },
                "optimization": {
                    "models": ["llama3.1-8b"],
                    "budget": "ultra-light",
                    "optimize_mode": "body",
                    "validation_fraction": 0.5,
                },
            },
            sort_keys=False,
        )
        try:
            create_experiment(session, experiment_name)
            result = execute_ai_function_eval_opts(
                session, {"experiment_name": experiment_name}, spec
            )
            assert result["status"] == "SUCCEEDED", result
            assert result.get("experiment") == experiment_name
            tree = build_experiment_tree(session, experiment_name)
            assert "SEED" in tree, f"expected a SEED run; got {sorted(tree)}"
        finally:
            session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()
