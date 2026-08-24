#!/usr/bin/env python3

# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

r"""Manage Snowsight notebook lifecycle for AI Function Studio.

Creates and appends cells to .ipynb notebooks for each workflow stage
(Create, Evaluate, Optimize, Custom Metric, Synthetic Data). The agent
calls subcommands via CLI instead of hand-constructing notebook JSON.

No Snowflake connection is required — this script only writes .ipynb files
to the local filesystem and prints JSON summaries to stdout for the agent.

Example usage:
    uv run python notebook_manager.py init \
        --notebook-path MY_FUNC.ipynb

    uv run python notebook_manager.py create-preview \
        --notebook-path MY_FUNC.ipynb \
        --ddl-body "CREATE FUNCTION ..." \
        --system-prompt "You are ..." \
        --user-prompt-template "{TEXT}"

    uv run python notebook_manager.py eval-results \
        --notebook-path MY_FUNC.ipynb \
        --function-name DB.SCHEMA.MY_FUNC \
        --metric-name exact_match --score 0.87 \
        --test-size 150 --run-id ai_func_eval_xyz \
        --experiment-name DB.SCHEMA.ai_func_eval_xyz
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from textwrap import dedent
from typing import Literal

# ---------------------------------------------------------------------------
# Notebook primitives
# ---------------------------------------------------------------------------

CellType = Literal["markdown", "code", "sql"]
Budget = Literal["demo", "light", "medium", "heavy"]

NOTEBOOK_SKELETON: dict = {
    "metadata": {
        "kernelspec": {
            "display_name": "Jupyter Notebook",
            "name": "jupyter",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
    "cells": [],
}


def make_cell(cell_type: CellType, source: str) -> dict:
    """Build a single notebook cell dict.

    Args:
        cell_type: One of "markdown", "code", or "sql". The "sql" type is
            stored as "code" with Snowsight-compatible metadata.
        source: The cell content as a single string (newlines included).

    Returns:
        A notebook cell dict ready for insertion into an .ipynb file.

    """
    effective_type = "code" if cell_type == "sql" else cell_type
    cell: dict = {
        "cell_type": effective_type,
        "metadata": {},
        "source": source.split("\n"),
    }
    if effective_type == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    if cell_type == "sql":
        cell["metadata"]["language"] = "sql"
    return cell


def read_notebook(path: str | Path) -> dict:
    """Read an .ipynb file and return the parsed JSON dict."""
    with open(path, encoding="utf-8") as f:
        result: dict = json.load(f)
    return result


def write_notebook(path: str | Path, nb: dict) -> None:
    """Write a notebook dict as a formatted .ipynb file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")


def append_cells(path: str | Path, cells: list[dict]) -> dict:
    """Append cells to an existing notebook and write it back.

    Args:
        path: Path to the .ipynb file.
        cells: List of cell dicts to append.

    Returns:
        A summary dict with cell count info, printed to stdout by callers.

    """
    nb = read_notebook(path)
    nb["cells"].extend(cells)
    write_notebook(path, nb)

    cell_types = []
    for c in cells:
        lang = c.get("metadata", {}).get("language")
        if lang == "sql":
            cell_types.append("sql")
        elif c["cell_type"] == "code":
            cell_types.append("python")
        else:
            cell_types.append(c["cell_type"])

    return {
        "notebook_path": str(path),
        "cells_added": len(cells),
        "cell_types": cell_types,
    }


# ---------------------------------------------------------------------------
# Subcommand: init
# ---------------------------------------------------------------------------


def init_notebook(notebook_path: str) -> None:
    """Create a fresh, empty .ipynb file (overwrites if exists)."""
    nb = json.loads(json.dumps(NOTEBOOK_SKELETON))
    write_notebook(notebook_path, nb)
    result = {
        "notebook_path": notebook_path,
        "action": "created",
    }
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# Subcommand: create-preview
# ---------------------------------------------------------------------------


def create_preview(
    notebook_path: str,
    ddl_body: str,
    system_prompt: str,
    user_prompt_template: str,
) -> None:
    """Append a Create section with DDL preview to the notebook.

    Adds a markdown header and a SQL cell containing SET variables for the
    prompts followed by the DDL body.
    """
    escaped_system = system_prompt.replace("'", "''")
    escaped_user = user_prompt_template.replace("'", "''")

    sql_source = dedent(f"""\
        SET system_prompt = '{escaped_system}';

        SET user_prompt_template = '{escaped_user}';

        {ddl_body}""")

    header_md = dedent("""\
        # 📋 Create
        Review and edit the DDL below. When ready, confirm to deploy.""")

    cells = [
        make_cell("markdown", header_md),
        make_cell("sql", sql_source),
    ]

    result = append_cells(notebook_path, cells)
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# Subcommand: eval-results
# ---------------------------------------------------------------------------


def eval_results(
    notebook_path: str,
    function_name: str,
    metric_name: str,
    score: float,
    test_size: int,
    run_id: str,
    experiment_name: str,
) -> None:
    """Append evaluation results section to the notebook.

    Adds 6 cells: header markdown, file format setup SQL (required because
    inline ``(FILE_FORMAT => (TYPE => JSON))`` isn't supported on SnowURL
    paths), results description, detailed results SQL, failure analysis
    description, failure analysis SQL.

    Per-row eval details are stored in the per-evaluation Snowflake
    Experiment ``{experiment_name}`` (default = the run_id) at
    ``snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json``.
    Reading the SnowURL requires server parameter
    ``ENABLE_EXPERIMENT_SNOWURL_READ_PATH_RESOLUTION = TRUE``.
    """
    header_md = dedent(f"""\
        # 📊 Evaluation: {function_name}
        **Metric:** {metric_name} | **Test Size:** {test_size} examples \
| **Score:** {score:.1%} | **Run ID:** {run_id} \
| **Experiment:** {experiment_name}""")

    file_format_sql = dedent("""\
        -- Required setup: SnowURL paths don't accept inline (TYPE => JSON).
        -- Run once per session.
        CREATE OR REPLACE TEMPORARY FILE FORMAT eval_detail_json_fmt
          TYPE = JSON
          STRIP_OUTER_ARRAY = TRUE;""")

    snowurl = f"snow://experiment/{experiment_name}/versions/EVAL/eval_detail.json"

    results_desc_md = dedent("""\
        ## Detailed Results
        Every row from the test set with its expected vs predicted output, \
sorted by score (worst first). Look for patterns in the low-scoring \
rows — do failures cluster around a specific input type or edge case?""")

    results_sql = dedent(f"""\
        SELECT
            $1:row_id::INT       AS ROW_ID,
            $1:input_text::STRING AS INPUT_TEXT,
            $1:expected::STRING  AS EXPECTED,
            $1:predicted::STRING AS PREDICTED,
            $1:metric_score::FLOAT AS SCORE,
            $1:metric_feedback::STRING AS FEEDBACK
        FROM '{snowurl}'
        (FILE_FORMAT => eval_detail_json_fmt)
        ORDER BY SCORE;""")

    failure_desc_md = dedent("""\
        ## Failure Analysis
        Only rows where the function scored below 1.0. Review these to \
understand *why* the function failed — is the prompt unclear for \
these cases? Are the expected labels ambiguous? This is the most \
actionable section for improving your function.""")

    failure_sql = dedent(f"""\
        SELECT
            $1:row_id::INT       AS ROW_ID,
            $1:input_text::STRING AS INPUT_TEXT,
            $1:expected::STRING  AS EXPECTED,
            $1:predicted::STRING AS PREDICTED,
            $1:metric_score::FLOAT AS SCORE,
            $1:metric_feedback::STRING AS FEEDBACK
        FROM '{snowurl}'
        (FILE_FORMAT => eval_detail_json_fmt)
        WHERE $1:metric_score::FLOAT < 1
        ORDER BY SCORE;""")

    cells = [
        make_cell("markdown", header_md),
        make_cell("sql", file_format_sql),
        make_cell("markdown", results_desc_md),
        make_cell("sql", results_sql),
        make_cell("markdown", failure_desc_md),
        make_cell("sql", failure_sql),
    ]

    result = append_cells(notebook_path, cells)
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# Subcommand: custom-metric
# ---------------------------------------------------------------------------


def custom_metric(
    notebook_path: str,
    metric_name: str,
    metric_code: str,
    smoke_test_sql: str,
) -> None:
    """Append a custom metric preview section to the notebook.

    Adds a markdown header, Python cell with the metric code, and a SQL cell
    with the smoke test query.
    """
    header_md = dedent(f"""\
        # 📏 Custom Metric: {metric_name}
        Review the scoring logic below — you can edit weights, thresholds, \
or field checks directly in the cell.""")

    cells = [
        make_cell("markdown", header_md),
        make_cell("code", metric_code),
        make_cell("sql", smoke_test_sql),
    ]

    result = append_cells(notebook_path, cells)
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# Subcommand: synth-data
# ---------------------------------------------------------------------------


def synth_data(
    notebook_path: str,
    function_name: str,
    output_table: str,
    total_generated: int,
    model: str,
    label_counts: dict,
) -> None:
    """Append a synthetic data preview section to the notebook.

    Adds a markdown header, SQL data preview cell, and a Python bar chart cell
    for categorical value distribution.
    """
    header_md = dedent(f"""\
        # 🧪 Synthetic Data: {function_name}
        **Output table:** `{output_table}` | **Examples generated:** \
{total_generated} | **Model:** {model}""")

    preview_sql = f"SELECT * FROM {output_table} LIMIT 10;"

    chart_code = dedent(f"""\
        import matplotlib.pyplot as plt

        counts = {json.dumps(label_counts)}

        def display_label(label, max_chars=48):
            text = str(label) if label not in (None, '') else '(empty)'
            return text if len(text) <= max_chars else text[: max_chars - 3] + '...'

        items = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:15]

        fig_height = max(4, min(9, 1.6 + 0.42 * max(len(items), 1)))
        fig, ax = plt.subplots(figsize=(9, fig_height))
        if not items:
            ax.text(
                0.5, 0.5, 'No values found',
                ha='center', va='center', transform=ax.transAxes, color='#64748B'
            )
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
        else:
            labels = [
                display_label(label)
                for label, _ in items
            ]
            values = [count for _, count in items]
            positions = list(range(len(labels)))
            bars = ax.barh(positions, values, color='#29B5E8')
            ax.set_yticks(positions, labels)
            ax.invert_yaxis()
            ax.set_xlabel('Rows')
            ax.grid(axis='x', color='#DDE6ED', linewidth=0.8, alpha=0.8)
            ax.set_axisbelow(True)
            ax.set_xlim(0, max(max(values) * 1.15, 1))
            for bar, value in zip(bars, values):
                ax.text(
                    value,
                    bar.get_y() + bar.get_height() / 2,
                    f' {{value}}',
                    va='center',
                    fontsize=9,
                )

        ax.set_title('Value Distribution', pad=12)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        plt.tight_layout()
        plt.show()""")

    cells = [
        make_cell("markdown", header_md),
        make_cell("sql", preview_sql),
        make_cell("code", chart_code),
    ]

    result = append_cells(notebook_path, cells)
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# Subcommand: optimize-progress
# ---------------------------------------------------------------------------


def _budget_to_iterations(budget: Budget) -> int:
    """Compute max iterations N from budget preset.

    Mirrors the ``resolve_budget`` formula in ``snow_gepa_optimize.py``.
    """
    budget_n = {"demo": 2, "light": 6, "medium": 12, "heavy": 18}
    n = budget_n.get(budget, 6)
    return int(max(2 * 2 * math.log2(n), 1.5 * n))


def optimize_progress(
    notebook_path: str,
    function_name: str,
    experiment: str,
    models: list[str],
    budget: Budget,
    metric_name: str,
    timeout: int,
    custom_metric_udf: str | None = None,
) -> None:
    """Append an optimization progress bar section to the notebook.

    Adds a markdown header and a Python cell that polls QUERY_HISTORY and
    experiment runs to display approximate optimization progress.
    """
    n_iterations = _budget_to_iterations(budget)

    models_repr = json.dumps(models)
    udf_repr = custom_metric_udf or "none"

    header_md = dedent(f"""\
        # 🔧 Optimization: {function_name}
        **Budget:** {budget} (~{n_iterations} iterations per model) | \
**Metric:** {metric_name} | **Experiment:** {experiment}""")

    # The progress cell is the most complex template. All variables are
    # interpolated here so the agent never hand-edits this Python code.
    #
    # Snowsight notebooks only honor the exact byte sequence `\r\u001b[2K`
    # as an in-place line flush; other ANSI cursor escapes (e.g. `\u001b[nA`
    # cursor-up) render as literal garbage. That rules out multi-line
    # in-place refresh, so the polling loop collapses overall + per-model
    # status into a single line that gets rewritten each tick. The banner
    # and terminal messages are the only lines that emit `\n`.
    progress_code = f"""\
import math, sys, time, re
from snowflake.snowpark.context import get_active_session

session = get_active_session()
EXPERIMENT = {json.dumps(experiment)}
MODELS = {models_repr}
TIMEOUT = {timeout}
AUTO_BUDGET = {json.dumps(budget)}
METRIC_NAME = {json.dumps(metric_name)}
CUSTOM_METRIC_UDF = {json.dumps(udf_repr)}

BUDGET_N = {{"demo": 2, "light": 6, "medium": 12, "heavy": 18}}
n = BUDGET_N.get(AUTO_BUDGET, 6)
N = int(max(2 * 2 * math.log2(n), 1.5 * n))

if METRIC_NAME == "llm_judge":
    QUERIES_PER_ITER = 7
elif CUSTOM_METRIC_UDF and CUSTOM_METRIC_UDF != "none":
    QUERIES_PER_ITER = 6
else:
    QUERIES_PER_ITER = 4
EXPECTED_TOTAL_QUERIES = N * QUERIES_PER_ITER * len(MODELS)

start_ts = session.sql("SELECT CURRENT_TIMESTAMP()::VARCHAR AS TS").collect()[0]["TS"]

def model_prefix(model):
    return re.sub(r"[^A-Za-z0-9]", "_", model).upper()

def bar(pct, width=12):
    filled = int(width * min(pct, 1.0))
    return "\\u2588" * filled + "\\u2591" * (width - filled)

db = session.get_current_database()
wh = session.get_current_warehouse()

def count_sproc_queries():
    try:
        rows = session.sql(
            f"SELECT COUNT(*) AS QC FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY("
            f"END_TIME_RANGE_START => '{{start_ts}}'::TIMESTAMP_LTZ, "
            f"RESULT_LIMIT => 10000)) "
            f"WHERE QUERY_TAG LIKE '%SPROC_OPTIMIZATION%'"
            f"  AND DATABASE_NAME = '{{db}}'"
            f"  AND WAREHOUSE_NAME = '{{wh}}'"
        ).collect()
        return rows[0]["QC"] if rows else 0
    except Exception:
        return 0

def check_done():
    done = {{}}
    try:
        all_runs = session.sql(f"SHOW RUNS IN EXPERIMENT {{EXPERIMENT}}").collect()
    except Exception:
        return done
    all_run_names = [r["name"] for r in all_runs]

    def run_params(run_name):
        try:
            rows = session.sql(
                f"SHOW RUN PARAMETERS IN EXPERIMENT {{EXPERIMENT}} RUN {{run_name}}"
            ).collect()
            return {{r["name"]: r["value"] for r in rows}}
        except Exception:
            return {{}}

    def run_valset_score(run_name):
        try:
            rows = session.sql(
                f"SHOW RUN METRICS IN EXPERIMENT {{EXPERIMENT}} RUN {{run_name}}"
            ).collect()
            for r in rows:
                if r["name"] == "valset_score" and r["value"] is not None:
                    return float(r["value"])
        except Exception:
            pass
        return None

    # v4 (global run structure): a single "SEED" run + a single global
    # "ITER_<N>" sequence. The producing model is the "model" PARAM (never the
    # name); the seed run is model-agnostic (model=""). Detect via
    # experiment_schema_version >= 4 (or the presence of an exact "SEED" run
    # carrying per_model_stats).
    seed_pv = run_params("SEED") if "SEED" in all_run_names else {{}}
    try:
        schema_version = int(seed_pv.get("experiment_schema_version") or 0)
    except (TypeError, ValueError):
        schema_version = 0
    is_v4 = schema_version >= 4 or bool(seed_pv.get("per_model_stats"))

    if is_v4:
        # Completion sentinel: the SEED run carries per_model_stats once the
        # optimization has finished writing its aggregate stats. Until then we
        # report nothing done (progress falls back to the query-count heuristic).
        if not seed_pv.get("per_model_stats"):
            return done
        # Best per model = highest valset_score across SEED + ITER_<N> runs,
        # grouped by the "model" run PARAM. The SEED run (model="") contributes
        # to every model's baseline.
        seed_score = run_valset_score("SEED")
        best_by_model = {{}}
        for run_name in all_run_names:
            if run_name == "SEED" or run_name.startswith("ITER_"):
                pv = run_params(run_name)
                # Skip rejected proposals — not accepted candidates.
                if pv.get("run_type") == "rejected":
                    continue
                s = run_valset_score(run_name)
                if s is None:
                    continue
                rm = pv.get("model") or ""
                if run_name == "SEED":
                    # Seed baseline applies to all requested models.
                    for m in MODELS:
                        if s > best_by_model.get(m, -1.0):
                            best_by_model[m] = s
                elif rm in MODELS and s > best_by_model.get(rm, -1.0):
                    best_by_model[rm] = s
        for m in MODELS:
            if m in best_by_model and best_by_model[m] >= 0:
                done[m] = best_by_model[m]
        return done

    # Legacy (v3/evolve): per-model runs, role encoded in the name prefix.
    for m in MODELS:
        try:
            # Check if any run for this model has aggregate stats stamped
            # (indicates optimization completed for this model).
            prefix = model_prefix(m)
            model_runs = [n for n in all_run_names if n.startswith(prefix)]
            # First try legacy BEST run (backward compat with older experiments)
            best_run = f"{{prefix}}_BEST"
            if best_run in model_runs:
                rows = session.sql(
                    f"SHOW RUN METRICS IN EXPERIMENT {{EXPERIMENT}} RUN {{best_run}}"
                ).collect()
                for r in rows:
                    if r["name"] == "valset_score" and r["value"] is not None:
                        done[m] = float(r["value"])
                continue
            # v3: aggregate stats on SEED run (completion sentinel)
            seed_run = f"{{prefix}}_SEED"
            if seed_run in model_runs:
                try:
                    pv = run_params(seed_run)
                    if pv.get("total_candidates"):
                        # Find best score across ITER + SEED runs
                        best_score = -1.0
                        for run_name in model_runs:
                            if "_ITER_" not in run_name and "_SEED" not in run_name:
                                continue
                            s = run_valset_score(run_name)
                            if s is not None and s > best_score:
                                best_score = s
                        if best_score >= 0:
                            done[m] = best_score
                except Exception:
                    pass
        except Exception:
            pass
    return done

start = time.time()
print(f"Optimization started \\u2014 {{len(MODELS)}} model(s), ~{{N}} iterations each")

while time.time() - start < TIMEOUT:
    done = check_done()
    qc = count_sproc_queries()
    remaining = len(MODELS) - len(done)
    remaining_qc = max(qc - len(done) * N * QUERIES_PER_ITER, 0)
    if remaining > 0:
        pct = min(remaining_qc / max(remaining * N * QUERIES_PER_ITER, 1), 0.99)
    else:
        pct = 1.0
    elapsed = int(time.time() - start)
    overall_pct = (len(done) + pct * remaining) / len(MODELS) if MODELS else 0

    parts = [f"[{{bar(overall_pct)}}] {{overall_pct:.0%}} ({{elapsed}}s)"]
    for m in MODELS:
        if m in done:
            parts.append(f"{{m}} \\u2705 {{done[m]:.1%}}")
        else:
            model_pct = min((remaining_qc / max(remaining, 1)) / max(N * QUERIES_PER_ITER, 1), 0.99)
            parts.append(f"{{m}} ~{{model_pct:.0%}}")
    print("\\r\\u001b[2K" + " \\u00b7 ".join(parts), end="", flush=True)

    if len(done) == len(MODELS):
        print(f"\\n\\u2705 All models complete ({{elapsed}}s)")
        break
    time.sleep(8)
else:
    print(f"\\n\\u23f1\\ufe0f Progress tracking timed out after {{TIMEOUT}}s. Check the following for more info on the optimization: SHOW RUNS IN EXPERIMENT {{EXPERIMENT}}")
"""

    cells = [
        make_cell("markdown", header_md),
        make_cell("code", progress_code),
    ]

    result = append_cells(notebook_path, cells)
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# Subcommand: optimize-charts
# ---------------------------------------------------------------------------


def optimize_charts(
    notebook_path: str,
    function_name: str,
    metric_name: str,
    models: list[str],
    seed_scores: list[float],
    best_scores: list[float],
    pareto_models: list[str],
    pareto_scores: list[float],
    pareto_costs: list[float],
    seed_test_score: float,
) -> None:
    """Append optimization result charts to the notebook.

    Adds a markdown header, a bar chart comparing seed vs optimized scores,
    and a Pareto frontier scatter plot.
    """
    if not (len(models) == len(seed_scores) == len(best_scores)):
        raise ValueError(
            "models, seed_scores, and best_scores must have equal length "
            f"(got {len(models)}, {len(seed_scores)}, {len(best_scores)})"
        )
    if not (len(pareto_models) == len(pareto_scores) == len(pareto_costs)):
        raise ValueError(
            "pareto_models, pareto_scores, and pareto_costs must have equal length "
            f"(got {len(pareto_models)}, {len(pareto_scores)}, {len(pareto_costs)})"
        )
    header_md = dedent(f"""\
        # 🔧 Optimization Results: {function_name}
        **Metric:** {metric_name}""")

    bar_chart_code = dedent(f"""\
        import matplotlib.pyplot as plt

        models = {json.dumps(models)}
        seed_scores = {json.dumps(seed_scores)}
        best_scores = {json.dumps(best_scores)}

        x = range(len(models))
        width = 0.35
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.bar([i - width/2 for i in x], seed_scores, width,
               label='Seed (Before)', color='#B0BEC5')
        ax.bar([i + width/2 for i in x], best_scores, width,
               label='Optimized (After)', color='#29B5E8')
        ax.set_ylabel({json.dumps(metric_name + " Score")})
        ax.set_title('Optimization Improvement by Model')
        ax.set_xticks(list(x))
        ax.set_xticklabels(models, rotation=45, ha='right')
        ax.legend()
        ax.set_ylim(0, 1.05)
        plt.tight_layout()
        plt.show()""")

    pareto_code = dedent(f"""\
        import matplotlib.pyplot as plt

        pareto_models = {json.dumps(pareto_models)}
        pareto_scores = {json.dumps(pareto_scores)}
        pareto_costs = {json.dumps(pareto_costs)}

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(pareto_costs, pareto_scores, s=120, c='#29B5E8',
                   edgecolors='#1A3E5C', linewidths=1.5, zorder=5)
        sorted_pairs = sorted(zip(pareto_costs, pareto_scores))
        ax.plot([p[0] for p in sorted_pairs], [p[1] for p in sorted_pairs],
                '--', color='#29B5E8', alpha=0.5, zorder=3)
        for model, cost, score in zip(pareto_models, pareto_costs, pareto_scores):
            ax.annotate(model, (cost, score), textcoords='offset points',
                        xytext=(8, 8), fontsize=9)
        ax.axhline(y={seed_test_score}, color='#B0BEC5', linestyle=':',
                   label=f'Seed score ({seed_test_score:.1%})')
        ax.set_xlabel('Relative Cost (1.0 = seed model)')
        ax.set_ylabel({json.dumps(metric_name + " Score")})
        ax.set_title('Pareto Frontier: Accuracy vs Cost')
        ax.legend()
        plt.tight_layout()
        plt.show()""")

    cells = [
        make_cell("markdown", header_md),
        make_cell("code", bar_chart_code),
        make_cell("code", pareto_code),
    ]

    result = append_cells(notebook_path, cells)
    print(json.dumps(result))


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser with all subcommands."""
    parser = argparse.ArgumentParser(
        description="Manage Snowsight notebooks for AI Function Studio.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- init --
    p_init = subparsers.add_parser("init", help="Create a fresh empty notebook")
    p_init.add_argument(
        "--notebook-path", required=True, help="Path for the .ipynb file"
    )

    # -- create-preview --
    p_create = subparsers.add_parser(
        "create-preview",
        help="Add Create DDL preview cells",
    )
    p_create.add_argument("--notebook-path", required=True)
    p_create.add_argument(
        "--ddl-body", required=True, help="The CREATE FUNCTION DDL statement"
    )
    p_create.add_argument("--system-prompt", required=True)
    p_create.add_argument("--user-prompt-template", required=True)

    # -- eval-results --
    p_eval = subparsers.add_parser(
        "eval-results",
        help="Add evaluation results cells",
    )
    p_eval.add_argument("--notebook-path", required=True)
    p_eval.add_argument("--function-name", required=True)
    p_eval.add_argument("--metric-name", required=True)
    p_eval.add_argument("--score", required=True, type=float)
    p_eval.add_argument("--test-size", required=True, type=int)
    p_eval.add_argument("--run-id", required=True)
    p_eval.add_argument(
        "--experiment-name",
        required=True,
        help="Per-evaluation Snowflake Experiment that holds "
        "eval_detail.json (default = the run_id).",
    )

    # -- custom-metric --
    p_metric = subparsers.add_parser(
        "custom-metric",
        help="Add custom metric preview cells",
    )
    p_metric.add_argument("--notebook-path", required=True)
    p_metric.add_argument("--metric-name", required=True)
    p_metric.add_argument(
        "--metric-code", required=True, help="Python source code for the metric"
    )
    p_metric.add_argument(
        "--smoke-test-sql", required=True, help="SQL smoke test query"
    )

    # -- synth-data --
    p_synth = subparsers.add_parser(
        "synth-data",
        help="Add synthetic data preview cells",
    )
    p_synth.add_argument("--notebook-path", required=True)
    p_synth.add_argument("--function-name", required=True)
    p_synth.add_argument("--output-table", required=True)
    p_synth.add_argument("--total-generated", required=True, type=int)
    p_synth.add_argument("--model", required=True)
    p_synth.add_argument(
        "--label-counts",
        required=True,
        help='JSON dict of categorical value->count, e.g. \'{"toxic": 100, "not_toxic": 100}\'',
    )

    # -- optimize-progress --
    p_opt_prog = subparsers.add_parser(
        "optimize-progress",
        help="Add optimization progress bar cells",
    )
    p_opt_prog.add_argument("--notebook-path", required=True)
    p_opt_prog.add_argument("--function-name", required=True)
    p_opt_prog.add_argument("--experiment", required=True)
    p_opt_prog.add_argument(
        "--models",
        required=True,
        help='JSON list of model names, e.g. \'["mistral-7b","claude-haiku-4-5"]\'',
    )
    p_opt_prog.add_argument(
        "--budget", required=True, choices=["demo", "light", "medium", "heavy"]
    )
    p_opt_prog.add_argument("--metric-name", required=True)
    p_opt_prog.add_argument("--timeout", required=True, type=int)
    p_opt_prog.add_argument("--custom-metric-udf", default=None)

    # -- optimize-charts --
    p_opt_charts = subparsers.add_parser(
        "optimize-charts",
        help="Add optimization result chart cells",
    )
    p_opt_charts.add_argument("--notebook-path", required=True)
    p_opt_charts.add_argument("--function-name", required=True)
    p_opt_charts.add_argument("--metric-name", required=True)
    p_opt_charts.add_argument(
        "--models", required=True, help="JSON list of model names"
    )
    p_opt_charts.add_argument(
        "--seed-scores", required=True, help="JSON list of seed scores"
    )
    p_opt_charts.add_argument(
        "--best-scores", required=True, help="JSON list of best scores"
    )
    p_opt_charts.add_argument(
        "--pareto-models", required=True, help="JSON list of Pareto model names"
    )
    p_opt_charts.add_argument(
        "--pareto-scores", required=True, help="JSON list of Pareto scores"
    )
    p_opt_charts.add_argument(
        "--pareto-costs", required=True, help="JSON list of Pareto costs"
    )
    p_opt_charts.add_argument("--seed-test-score", required=True, type=float)

    return parser


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate subcommand."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "init":
        init_notebook(args.notebook_path)

    elif args.command == "create-preview":
        create_preview(
            notebook_path=args.notebook_path,
            ddl_body=args.ddl_body,
            system_prompt=args.system_prompt,
            user_prompt_template=args.user_prompt_template,
        )

    elif args.command == "eval-results":
        eval_results(
            notebook_path=args.notebook_path,
            function_name=args.function_name,
            metric_name=args.metric_name,
            score=args.score,
            test_size=args.test_size,
            run_id=args.run_id,
            experiment_name=args.experiment_name,
        )

    elif args.command == "custom-metric":
        custom_metric(
            notebook_path=args.notebook_path,
            metric_name=args.metric_name,
            metric_code=args.metric_code,
            smoke_test_sql=args.smoke_test_sql,
        )

    elif args.command == "synth-data":
        try:
            label_counts = json.loads(args.label_counts)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --label-counts: {e}", file=sys.stderr)
            sys.exit(1)
        synth_data(
            notebook_path=args.notebook_path,
            function_name=args.function_name,
            output_table=args.output_table,
            total_generated=args.total_generated,
            model=args.model,
            label_counts=label_counts,
        )

    elif args.command == "optimize-progress":
        try:
            models = json.loads(args.models)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in --models: {e}", file=sys.stderr)
            sys.exit(1)
        optimize_progress(
            notebook_path=args.notebook_path,
            function_name=args.function_name,
            experiment=args.experiment,
            models=models,
            budget=args.budget,
            metric_name=args.metric_name,
            timeout=args.timeout,
            custom_metric_udf=args.custom_metric_udf,
        )

    elif args.command == "optimize-charts":
        try:
            models = json.loads(args.models)
            seed_scores = json.loads(args.seed_scores)
            best_scores = json.loads(args.best_scores)
            pareto_models = json.loads(args.pareto_models)
            pareto_scores = json.loads(args.pareto_scores)
            pareto_costs = json.loads(args.pareto_costs)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON argument: {e}", file=sys.stderr)
            sys.exit(1)
        optimize_charts(
            notebook_path=args.notebook_path,
            function_name=args.function_name,
            metric_name=args.metric_name,
            models=models,
            seed_scores=seed_scores,
            best_scores=best_scores,
            pareto_models=pareto_models,
            pareto_scores=pareto_scores,
            pareto_costs=pareto_costs,
            seed_test_score=args.seed_test_score,
        )


if __name__ == "__main__":
    main()
