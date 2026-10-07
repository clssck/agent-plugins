#!/usr/bin/env python3
"""
build_notebook.py — Builds a parameterized Snowsight notebook (.ipynb) for the AI Readiness Score.

Usage:
    python build_notebook.py --sample-pct 30 --output /tmp/ai_readiness_notebook.ipynb

Reads cell definitions from notebook_cells.py, injects parameters, and writes a valid .ipynb file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import notebook_cells as cells


def _md_cell(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def _code_cell(source: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {
            "language": "python",
            "name": "cell_py",
        },
        "source": source.splitlines(keepends=True),
        "outputs": [],
        "execution_count": None,
    }


def build_notebook(
    account_name: str = "UNKNOWN",
    sample_pct: int | None = None,
    warehouse: str = "COMPUTE_WH",
    use_cache: bool = True,
    cr_tables_sql: str = "",
    sv_quality_sql: str = "",
    scoring_py: str = "",
) -> dict:
    sample_label = f"{sample_pct}% sample" if sample_pct else "Full scan"
    sample_pct_val = str(sample_pct) if sample_pct else "None"
    use_cache_val = "True" if use_cache else "False"

    nb = {
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.9.0",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
        "cells": [],
    }

    md_title = cells.md_title()
    md_title = md_title.replace("__RUN_DATE__", date.today().strftime("%Y-%m-%d"))
    md_title = md_title.replace("__ACCOUNT_NAME__", account_name)
    md_title = md_title.replace("__SAMPLE_LABEL__", sample_label)
    md_title = md_title.replace("__WAREHOUSE__", warehouse)

    code_params = cells.code_parameters()
    code_params = code_params.replace("__SAMPLE_PCT__", sample_pct_val)
    code_params = code_params.replace("__USE_CACHE__", use_cache_val)

    code_cr_sql = cells.code_sql_cr_tables()
    code_cr_sql = code_cr_sql.replace("__CR_TABLES_SQL__", cr_tables_sql if cr_tables_sql else "")

    code_sv_sql = cells.code_sql_sv_quality()
    code_sv_sql = code_sv_sql.replace("__SV_QUALITY_SQL__", sv_quality_sql if sv_quality_sql else "")

    code_merge = cells.code_merge_and_score()
    code_merge = code_merge.replace("__SCORING_PY__", scoring_py if scoring_py else "")

    nb["cells"] = [
        _md_cell(md_title),                          # 0
        _code_cell(code_params),                      # 1
        _code_cell(cells.code_imports_and_session()),  # 2
        _code_cell(cells.code_cache_helpers()),        # 3
        _md_cell(cells.md_step1_scanning()),           # 4
        _code_cell(code_cr_sql),                       # 5
        _code_cell(code_sv_sql),                       # 6
        _code_cell(cells.code_scan_variables()),       # 7
        _md_cell(cells.md_cr_header()),                # 8
        _code_cell(cells.code_cr_scoring()),           # 9
        _md_cell(cells.md_sv_header()),                # 10
        _code_cell(cells.code_sv_scoring()),           # 11
        _md_cell(cells.md_step2_computing()),          # 12
        _code_cell(code_merge),                        # 13
        _md_cell(cells.md_results_header()),           # 14
        _code_cell(cells.code_display_results()),      # 15
        _md_cell(cells.md_footer()),                   # 16
    ]

    return nb


def main():
    p = argparse.ArgumentParser(description="Build AI Readiness notebook")
    p.add_argument("--account-name", default="UNKNOWN")
    p.add_argument("--sample-pct", type=int, default=None)
    p.add_argument("--warehouse", default="COMPUTE_WH")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--output", default="/tmp/ai_readiness_notebook.ipynb")
    args = p.parse_args()

    scripts_dir = Path(__file__).parent
    cr_sql = (scripts_dir / "cr_tables.sql").read_text(encoding="utf-8")
    sv_sql = (scripts_dir / "sv_quality.sql").read_text(encoding="utf-8")
    scoring_py = (scripts_dir / "scoring.py").read_text(encoding="utf-8")

    nb = build_notebook(
        account_name=args.account_name,
        sample_pct=args.sample_pct,
        warehouse=args.warehouse,
        use_cache=not args.no_cache,
        cr_tables_sql=cr_sql,
        sv_quality_sql=sv_sql,
        scoring_py=scoring_py,
    )

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
    print(f"Notebook written: {out}")


if __name__ == "__main__":
    main()
