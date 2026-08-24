# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for notebook_manager.py — Snowsight notebook lifecycle.

Run:
    uv run --group test pytest tests/test_notebook_manager.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from notebook_manager import (
    NOTEBOOK_SKELETON,
    append_cells,
    create_preview,
    custom_metric,
    eval_results,
    init_notebook,
    make_cell,
    optimize_charts,
    optimize_progress,
    read_notebook,
    synth_data,
    write_notebook,
)


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture — no Snowflake connection needed for unit tests."""
    yield


# ---------------------------------------------------------------------------
# Primitives: make_cell
# ---------------------------------------------------------------------------


class TestMakeCell:
    def test_markdown_cell_structure(self):
        cell = make_cell("markdown", "# Hello")
        assert cell["cell_type"] == "markdown"
        assert cell["source"] == ["# Hello"]
        assert "outputs" not in cell

    def test_code_cell_structure(self):
        cell = make_cell("code", "print('hi')")
        assert cell["cell_type"] == "code"
        assert cell["outputs"] == []
        assert cell["execution_count"] is None

    def test_sql_cell_is_code_with_metadata(self):
        cell = make_cell("sql", "SELECT 1;")
        assert cell["cell_type"] == "code"
        assert cell["metadata"]["language"] == "sql"
        assert cell["outputs"] == []

    def test_multiline_source_split(self):
        cell = make_cell("markdown", "line1\nline2\nline3")
        assert cell["source"] == ["line1", "line2", "line3"]


# ---------------------------------------------------------------------------
# Primitives: read/write/append
# ---------------------------------------------------------------------------


class TestNotebookIO:
    def test_write_and_read_roundtrip(self, tmp_path: Path):
        nb_path = tmp_path / "test.ipynb"
        nb = json.loads(json.dumps(NOTEBOOK_SKELETON))
        write_notebook(nb_path, nb)
        loaded = read_notebook(nb_path)
        assert loaded["nbformat"] == 4
        assert loaded["cells"] == []

    def test_append_cells_adds_to_existing(self, tmp_path: Path):
        nb_path = tmp_path / "test.ipynb"
        write_notebook(nb_path, json.loads(json.dumps(NOTEBOOK_SKELETON)))

        cells = [make_cell("markdown", "# Section 1")]
        result = append_cells(nb_path, cells)

        assert result["cells_added"] == 1
        assert result["cell_types"] == ["markdown"]

        nb = read_notebook(nb_path)
        assert len(nb["cells"]) == 1

    def test_append_preserves_existing_cells(self, tmp_path: Path):
        nb_path = tmp_path / "test.ipynb"
        nb = json.loads(json.dumps(NOTEBOOK_SKELETON))
        nb["cells"].append(make_cell("markdown", "# Existing"))
        write_notebook(nb_path, nb)

        append_cells(nb_path, [make_cell("sql", "SELECT 1;")])

        loaded = read_notebook(nb_path)
        assert len(loaded["cells"]) == 2
        assert loaded["cells"][0]["source"] == ["# Existing"]

    def test_append_reports_correct_types(self, tmp_path: Path):
        nb_path = tmp_path / "test.ipynb"
        write_notebook(nb_path, json.loads(json.dumps(NOTEBOOK_SKELETON)))

        cells = [
            make_cell("markdown", "# Head"),
            make_cell("sql", "SELECT 1;"),
            make_cell("code", "print(1)"),
        ]
        result = append_cells(nb_path, cells)
        assert result["cell_types"] == ["markdown", "sql", "python"]


# ---------------------------------------------------------------------------
# Subcommand: init
# ---------------------------------------------------------------------------


class TestInit:
    def test_creates_valid_ipynb(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)

        nb = read_notebook(nb_path)
        assert nb["nbformat"] == 4
        assert nb["cells"] == []
        assert nb["metadata"]["kernelspec"]["name"] == "jupyter"

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["action"] == "created"

    def test_overwrites_existing(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        # Write a notebook with some cells
        nb = json.loads(json.dumps(NOTEBOOK_SKELETON))
        nb["cells"].append(make_cell("markdown", "# Old"))
        write_notebook(nb_path, nb)

        init_notebook(nb_path)

        fresh = read_notebook(nb_path)
        assert fresh["cells"] == []


# ---------------------------------------------------------------------------
# Subcommand: create-preview
# ---------------------------------------------------------------------------


class TestCreatePreview:
    def test_appends_two_cells(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()  # discard init output

        create_preview(
            notebook_path=nb_path,
            ddl_body="CREATE FUNCTION DB.S.F(X VARCHAR) RETURNS VARCHAR AS $$ 'hi' $$;",
            system_prompt="You are a classifier",
            user_prompt_template="{X}",
        )

        nb = read_notebook(nb_path)
        assert len(nb["cells"]) == 2
        assert nb["cells"][0]["cell_type"] == "markdown"
        assert nb["cells"][1]["cell_type"] == "code"
        assert nb["cells"][1]["metadata"]["language"] == "sql"

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["cells_added"] == 2

    def test_ddl_contains_set_variables(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        create_preview(
            notebook_path=nb_path,
            ddl_body="CREATE FUNCTION DB.S.F(X VARCHAR) RETURNS VARCHAR AS $$ 'hi' $$;",
            system_prompt="Classify sentiment",
            user_prompt_template="{TEXT}",
        )

        nb = read_notebook(nb_path)
        sql_source = "\n".join(nb["cells"][1]["source"])
        assert "SET system_prompt = 'Classify sentiment';" in sql_source
        assert "SET user_prompt_template = '{TEXT}';" in sql_source
        assert "CREATE FUNCTION" in sql_source

    def test_single_quotes_escaped_in_prompts(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        create_preview(
            notebook_path=nb_path,
            ddl_body="CREATE FUNCTION DB.S.F(X VARCHAR) RETURNS VARCHAR AS $$ 'hi' $$;",
            system_prompt="It's a test",
            user_prompt_template="Don't panic: {X}",
        )

        nb = read_notebook(nb_path)
        sql_source = "\n".join(nb["cells"][1]["source"])
        assert "It''s a test" in sql_source
        assert "Don''t panic" in sql_source


# ---------------------------------------------------------------------------
# Subcommand: eval-results
# ---------------------------------------------------------------------------


class TestEvalResults:
    def test_appends_six_cells(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        eval_results(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            metric_name="exact_match",
            score=0.87,
            test_size=150,
            run_id="ai_func_eval_xyz",
            experiment_name="DB.S.ai_func_eval_xyz",
        )

        nb = read_notebook(nb_path)
        assert len(nb["cells"]) == 6

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["cells_added"] == 6
        assert output["cell_types"] == [
            "markdown",
            "sql",
            "markdown",
            "sql",
            "markdown",
            "sql",
        ]

    def test_header_contains_score_and_metadata(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        eval_results(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            metric_name="exact_match",
            score=0.87,
            test_size=150,
            run_id="ai_func_eval_xyz",
            experiment_name="DB.S.ai_func_eval_xyz",
        )

        nb = read_notebook(nb_path)
        header = "\n".join(nb["cells"][0]["source"])
        assert "87.0%" in header
        assert "exact_match" in header
        assert "ai_func_eval_xyz" in header
        # Experiment is surfaced in the header so users can find the SnowURL.
        assert "DB.S.ai_func_eval_xyz" in header

    def test_sql_cells_use_snowurl_pattern(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        eval_results(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            metric_name="exact_match",
            score=0.87,
            test_size=150,
            run_id="ai_func_eval_xyz",
            experiment_name="DB.S.ai_func_eval_xyz",
        )

        nb = read_notebook(nb_path)

        # File format setup (cell index 1) — required for SnowURL reads.
        fmt_sql = "\n".join(nb["cells"][1]["source"])
        assert "CREATE OR REPLACE TEMPORARY FILE FORMAT" in fmt_sql
        assert "TYPE = JSON" in fmt_sql
        assert "STRIP_OUTER_ARRAY" in fmt_sql

        # Detailed results SQL (cell index 3)
        detailed_sql = "\n".join(nb["cells"][3]["source"])
        assert (
            "snow://experiment/DB.S.ai_func_eval_xyz/versions/EVAL/eval_detail.json"
            in detailed_sql
        )
        assert "FILE_FORMAT => eval_detail_json_fmt" in detailed_sql
        assert "$1:metric_score::FLOAT" in detailed_sql

        # Failure analysis SQL (cell index 5)
        failure_sql = "\n".join(nb["cells"][5]["source"])
        assert "$1:metric_score::FLOAT < 1" in failure_sql


# ---------------------------------------------------------------------------
# Subcommand: custom-metric
# ---------------------------------------------------------------------------


class TestCustomMetric:
    def test_appends_three_cells(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        custom_metric(
            notebook_path=nb_path,
            metric_name="MY_METRIC",
            metric_code="def score(e, p):\n    return 1.0 if e == p else 0.0",
            smoke_test_sql="SELECT MY_METRIC('a', 'a') AS result;",
        )

        nb = read_notebook(nb_path)
        assert len(nb["cells"]) == 3

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["cell_types"] == ["markdown", "python", "sql"]

    def test_metric_code_preserved_verbatim(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        code = "def score(e, p):\n    return 1.0 if e == p else 0.0"
        custom_metric(
            notebook_path=nb_path,
            metric_name="MY_METRIC",
            metric_code=code,
            smoke_test_sql="SELECT 1;",
        )

        nb = read_notebook(nb_path)
        reconstructed = "\n".join(nb["cells"][1]["source"])
        assert reconstructed == code


# ---------------------------------------------------------------------------
# Subcommand: synth-data
# ---------------------------------------------------------------------------


class TestSynthData:
    def test_appends_three_cells(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        synth_data(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            output_table="DB.S.SYNTH",
            total_generated=200,
            model="claude-opus-4",
            label_counts={"toxic": 100, "not_toxic": 100},
        )

        nb = read_notebook(nb_path)
        assert len(nb["cells"]) == 3

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["cell_types"] == ["markdown", "sql", "python"]

    def test_value_counts_embedded_in_python_cell(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        counts = {"toxic": 100, "not_toxic": 100}
        synth_data(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            output_table="DB.S.SYNTH",
            total_generated=200,
            model="claude-opus-4",
            label_counts=counts,
        )

        nb = read_notebook(nb_path)
        python_source = "\n".join(nb["cells"][2]["source"])
        assert '"toxic": 100' in python_source
        assert "matplotlib" in python_source
        assert "ax.barh" in python_source
        assert "[:15]" in python_source
        assert "display_label" in python_source
        assert "No values found" in python_source
        assert "ax.pie" not in python_source

    def test_sql_preview_references_table(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        synth_data(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            output_table="DB.S.SYNTH_TABLE",
            total_generated=50,
            model="m",
            label_counts={"a": 1},
        )

        nb = read_notebook(nb_path)
        sql_source = "\n".join(nb["cells"][1]["source"])
        assert "DB.S.SYNTH_TABLE" in sql_source


# ---------------------------------------------------------------------------
# Subcommand: optimize-progress
# ---------------------------------------------------------------------------


class TestOptimizeProgress:
    def test_appends_two_cells(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_progress(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            experiment="DB.S.EXP",
            models=["mistral-7b"],
            budget="demo",
            metric_name="exact_match",
            timeout=300,
        )

        nb = read_notebook(nb_path)
        assert len(nb["cells"]) == 2

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["cell_types"] == ["markdown", "python"]

    def test_all_variables_interpolated(self, tmp_path: Path, capsys):
        """Verify no template placeholders remain in the progress cell."""
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_progress(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            experiment="DB.S.MY_EXP",
            models=["mistral-7b", "claude-haiku-4-5"],
            budget="light",
            metric_name="exact_match",
            timeout=600,
        )

        nb = read_notebook(nb_path)
        python_source = "\n".join(nb["cells"][1]["source"])

        # Key variables must be present
        assert '"DB.S.MY_EXP"' in python_source
        assert '"mistral-7b"' in python_source
        assert '"claude-haiku-4-5"' in python_source
        assert "TIMEOUT = 600" in python_source
        assert '"light"' in python_source
        assert '"exact_match"' in python_source

    def test_budget_iterations_in_header(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_progress(
            notebook_path=nb_path,
            function_name="DB.S.F",
            experiment="DB.S.E",
            models=["m"],
            budget="demo",
            metric_name="exact_match",
            timeout=60,
        )

        nb = read_notebook(nb_path)
        header = "\n".join(nb["cells"][0]["source"])
        # demo budget: n=2, N=int(max(4*log2(2), 1.5*2)) = int(max(4, 3)) = 4
        assert "~4 iterations" in header

    def test_custom_metric_udf_in_progress_cell(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_progress(
            notebook_path=nb_path,
            function_name="DB.S.F",
            experiment="DB.S.E",
            models=["m"],
            budget="demo",
            metric_name="custom",
            timeout=60,
            custom_metric_udf="DB.S.MY_UDF",
        )

        nb = read_notebook(nb_path)
        python_source = "\n".join(nb["cells"][1]["source"])
        assert "DB.S.MY_UDF" in python_source

    def test_progress_cell_uses_only_snowsight_flush_escape(
        self, tmp_path: Path, capsys
    ):
        r"""Snowsight notebooks only recognize the exact byte sequence
        ``\r\u001b[2K`` for in-place line refresh; other ANSI cursor-movement
        escapes (``\u001b[nA`` cursor-up, etc.) render as literal text. The
        polling loop must use only the flush escape and must not emit a
        newline mid-iteration, or the output will stack instead of refresh.
        """  # noqa: D205
        import re

        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_progress(
            notebook_path=nb_path,
            function_name="DB.S.F",
            experiment="DB.S.E",
            models=["m1", "m2"],
            budget="demo",
            metric_name="exact_match",
            timeout=60,
        )

        src = "\n".join(read_notebook(nb_path)["cells"][1]["source"])

        # The refresh escape must appear exactly once — the single print per
        # polling iteration.
        assert src.count("\\r\\u001b[2K") == 1, (
            "Expected exactly one '\\\\r\\\\u001b[2K' flush in the progress cell; "
            f"found {src.count(chr(92) + 'r' + chr(92) + 'u001b[2K')}"
        )
        assert "\\r\\033[2K" not in src

        # No cursor-movement escapes — Snowsight drops anything that isn't
        # '\\r\\u001b[2K', so '\\u001b[nA' and friends would render as garbage.
        forbidden = re.findall(r"\\(?:033|u001b)\[[^\"\\]*[ABCDEFGHJST]\b", src)
        assert not forbidden, (
            f"Progress cell contains unsupported ANSI cursor escapes: {forbidden}"
        )

        # The in-loop refresh write must not contain a newline, otherwise each
        # tick advances to a fresh line and the output stacks.
        loop_match = re.search(r"while time\.time.*?time\.sleep\(8\)", src, re.DOTALL)
        assert loop_match, "Could not locate polling loop body"
        refresh_write = re.search(
            r'print\("\\r\\u001b\[2K".*?end="", flush=True\)',
            loop_match.group(0),
        )
        assert refresh_write, "Refresh print missing from polling loop"
        assert "\\n" not in refresh_write.group(0), (
            "In-loop refresh write contains a newline; output will stack "
            "instead of refreshing in place"
        )


# ---------------------------------------------------------------------------
# Subcommand: optimize-charts
# ---------------------------------------------------------------------------


class TestOptimizeCharts:
    def test_appends_three_cells(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_charts(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            metric_name="exact_match",
            models=["mistral-7b", "claude-haiku-4-5"],
            seed_scores=[0.65, 0.72],
            best_scores=[0.81, 0.88],
            pareto_models=["mistral-7b", "claude-haiku-4-5"],
            pareto_scores=[0.81, 0.88],
            pareto_costs=[0.3, 1.0],
            seed_test_score=0.72,
        )

        nb = read_notebook(nb_path)
        assert len(nb["cells"]) == 3

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["cell_types"] == ["markdown", "python", "python"]

    def test_bar_chart_contains_data(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_charts(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            metric_name="exact_match",
            models=["modelA"],
            seed_scores=[0.5],
            best_scores=[0.9],
            pareto_models=["modelA"],
            pareto_scores=[0.9],
            pareto_costs=[1.0],
            seed_test_score=0.5,
        )

        nb = read_notebook(nb_path)
        bar_source = "\n".join(nb["cells"][1]["source"])
        assert "0.5" in bar_source
        assert "0.9" in bar_source
        assert "modelA" in bar_source

    def test_pareto_chart_contains_data(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        optimize_charts(
            notebook_path=nb_path,
            function_name="DB.S.MY_FUNC",
            metric_name="exact_match",
            models=["m"],
            seed_scores=[0.5],
            best_scores=[0.9],
            pareto_models=["m"],
            pareto_scores=[0.85],
            pareto_costs=[0.3],
            seed_test_score=0.5,
        )

        nb = read_notebook(nb_path)
        pareto_source = "\n".join(nb["cells"][2]["source"])
        assert "0.3" in pareto_source
        assert "0.85" in pareto_source
        assert "Pareto Frontier" in pareto_source


# ---------------------------------------------------------------------------
# Integration: multi-stage appending
# ---------------------------------------------------------------------------


class TestMultiStageAppending:
    def test_create_then_eval_preserves_both(self, tmp_path: Path, capsys):
        nb_path = str(tmp_path / "func.ipynb")
        init_notebook(nb_path)
        capsys.readouterr()

        create_preview(
            notebook_path=nb_path,
            ddl_body="CREATE FUNCTION DB.S.F(X VARCHAR) RETURNS VARCHAR AS $$ 'hi' $$;",
            system_prompt="test",
            user_prompt_template="{X}",
        )
        capsys.readouterr()

        eval_results(
            notebook_path=nb_path,
            function_name="DB.S.F",
            metric_name="exact_match",
            score=0.9,
            test_size=100,
            run_id="run1",
            experiment_name="DB.S.run1",
        )

        nb = read_notebook(nb_path)
        # 2 from create + 6 from eval = 8
        assert len(nb["cells"]) == 8
        # First cell is the create markdown header
        assert "Create" in "\n".join(nb["cells"][0]["source"])
        # Third cell (index 2) is the eval markdown header
        assert "Evaluation" in "\n".join(nb["cells"][2]["source"])
