#!/usr/bin/env python3
"""
gen_report.py — Generate the AI Readiness HTML report from scores JSON.

Usage:
    python gen_report.py --scores /path/to/scores.json --cache-date 2026_05_15
    python gen_report.py --scores /path/to/scores.json --cache-date 2026_05_15 --output ./report.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add scripts dir to path for local imports
sys.path.insert(0, str(Path(__file__).parent))

from report import render_html
from recommendations import build_recommendation


def main():
    parser = argparse.ArgumentParser(description="Generate AI Readiness HTML report")
    parser.add_argument("--scores", required=True,
                        help="Path to the scores JSON file (output of run_analysis.py).")
    parser.add_argument("--cache-date", required=True,
                        help="Date string for the report filename (YYYY_MM_DD format).")
    parser.add_argument("--output", default=None,
                        help="Output path for the HTML report. Defaults to ./ai_readiness_report_<cache-date>.html")
    args = parser.parse_args()

    scores = json.loads(Path(args.scores).read_text(encoding="utf-8"))

    rec = build_recommendation(
        account_name=scores["account_name"],
        composite=scores["ai_readiness"],
        gap=scores["gap"],
        pct_demand_coverage=scores.get("pct_demand_raw"),
        n_cr_tables=scores["n_cr_tables"],
        pct_sv_coverage=scores.get("pct_sv_coverage_raw", 0),
        n_sv_covered=scores.get("n_sv_covered", 0),
        avg_sv_quality=scores.get("avg_sv_quality_raw", 0),
        top_targets=scores.get("top_targets", []),
        missing_dims=scores.get("missing_dims", []),
    )

    html = render_html(
        account_name=scores["account_name"],
        org_name=scores.get("org_name", ""),
        role=scores.get("role", ""),
        run_date=scores.get("run_date", ""),
        ai_readiness=scores["ai_readiness"],
        demand_coverage=scores["demand_coverage"],
        sv_readiness=scores["sv_readiness"],
        sv_coverage=scores["sv_coverage"],
        sv_quality=scores["sv_quality"],
        n_cr_tables=scores["n_cr_tables"],
        gap=scores["gap"],
        recommendation=rec,
        improvement_items=scores.get("improvement_items", []),
        sample_pct=scores.get("sample_pct"),
    )

    filename = f"ai_readiness_report_{args.cache_date}.html"
    output_path = Path(args.output) if args.output else Path.cwd() / filename

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(str(output_path))


if __name__ == "__main__":
    main()
