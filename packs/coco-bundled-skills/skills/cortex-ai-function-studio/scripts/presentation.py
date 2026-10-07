# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Present optimization results as a Pareto-optimal results table.

In experiment mode (``--experiment``) this reads the SEED/ITER runs the
optimizer flagged ``is_frontier`` — these ARE the cross-model hypervolume
frontier (the Pareto authority), each carrying ``estimated_cost``,
``valset_score``, ``test_score`` (when a test table was used) and
``function_impl``.  No client-side frontier re-derivation is performed; the
optimizer already selected and flagged the set.

Score domains are never mixed: when every frontier candidate was
test-evaluated, the table shows test scores (and drops any candidate another
beats on BOTH cost and held-out test score); otherwise it shows validation
scores for the full frontier.

In manual mode (``--json`` / stdin) — used for Bring your own Model/SPCS models that
never ran through the SPROC — cost is computed from prompt/output lengths and a simple
cost-Pareto filter is applied.

Example usage:
    # From a Snowflake experiment (reads is_frontier SEED/ITER runs):
    uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/presentation.py \
        --experiment MY_DB.MY_SCHEMA.MY_EXP --connection my_conn --format table

    # From explicit JSON (manual / Bring your own Model, non-experiment runs):
    uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/presentation.py \
        --json '[{"model": "llama3.1-8b", "score": 0.82}, ...]' \
        --prompt-chars 200 --avg-output-chars 10
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snowflake.snowpark import Session

# Load model costs from models.json in the core package (relative to llama3.1-8b = 1.0)
_MODELS_JSON_PATH = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "snowflake-ai-optimize-core"
    / "src"
    / "snowflake_ai_optimize"
    / "core"
    / "models.json"
)
with open(_MODELS_JSON_PATH) as f:
    MODELS = json.load(f)

# Metric flag (0/1) the optimizer stamps onto the SEED/ITER runs that make up
# the cross-model hypervolume frontier (see
# ``core.experiment.stamp_frontier_metrics_on_runs``).  These lineage runs —
# not a separate run kind — are the canonical Pareto set the presentation
# layer reads.
_IS_FRONTIER_METRIC = "is_frontier"

# Run-name substrings that can never be on the frontier; skipped to avoid
# extra SHOW RUN METRICS round-trips.
_NON_FRONTIER_RUN_MARKERS = ("_REJECTED_", "_FAILED")


def get_model_cost(
    model_name: str,
    prompt_chars: int,
    avg_output_chars: int,
    explicit_cost: float | int | str | None = None,
) -> float:
    """Calculate model cost based on prompt length and average output length.

    cost = input_price × prompt_chars + output_price × avg_output_chars.

    Args:
        model_name: Name of the model.
        prompt_chars: Character length of the system prompt.
        avg_output_chars: Average output character length from test data.
        explicit_cost: Optional caller-provided relative cost. Used for Bring your own
            Model/SPCS service models that are not present in models.json.

    Returns:
        Cost estimate (float).

    """
    if explicit_cost is not None:
        try:
            cost = float(explicit_cost)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Explicit cost for model {model_name} must be numeric."
            ) from exc
        if cost < 0:
            raise ValueError(
                f"Explicit cost for model {model_name} must be non-negative."
            )
        return cost

    if model_name not in MODELS:
        raise ValueError(
            f"Model {model_name} not supported, add to {_MODELS_JSON_PATH} or "
            "include a numeric relative_cost/estimated_cost in the result row."
        )
    model = MODELS[model_name]
    return float(
        prompt_chars * model["input_cost"] + avg_output_chars * model["output_cost"]
    )


def filter_pareto_optimal(
    results: list[dict], prompt_chars: int, avg_output_chars: int
) -> list[dict]:
    """Filter to pareto-optimal results based on cost and score.

    An option is pareto-optimal if no other option has:
    - Lower or equal cost AND strictly higher score, OR
    - Strictly lower cost AND higher or equal score

    Args:
        results: List of dicts with 'model' and 'score'.
        prompt_chars: Prompt character length for cost calculation.
        avg_output_chars: Average output character length for cost calculation.

    Returns:
        List of pareto-optimal results, sorted by relative_cost ascending.

    """
    if not results:
        raise ValueError("No results provided")

    if prompt_chars <= 0:
        raise ValueError("Prompt length must be greater than 0")

    if avg_output_chars < 0:
        raise ValueError("Average output length must be non-negative")

    # Calculate relative cost for each result without mutating the caller's
    # input rows. Bring your own Model/SPCS service models may not be in models.json;
    # allow callers to pass a measured or estimated cost on each result row instead.
    enriched_results: list[dict] = []
    for r in results:
        explicit_cost = r.get("relative_cost", r.get("estimated_cost"))
        enriched = dict(r)
        enriched["relative_cost"] = get_model_cost(
            enriched["model"], prompt_chars, avg_output_chars, explicit_cost
        )
        enriched_results.append(enriched)

    sorted_results = sorted(
        enriched_results, key=lambda x: (x["relative_cost"], -x["score"])
    )

    pareto_optimal = []
    max_score_so_far = -1

    for result in sorted_results:
        if result["score"] > max_score_so_far:
            pareto_optimal.append(result)
            max_score_so_far = result["score"]

    return pareto_optimal


def _pareto_optimal_on(candidates: list[dict], score_field: str) -> list[dict]:
    """Return the Pareto-optimal subset on ``(relative_cost, score_field)``.

    An option is dominated when another has lower-or-equal cost and a strictly
    higher score.  Used as a presentation-time prune: when held-out test
    scores are available, candidates that were frontier-worthy on validation
    may be dominated once re-scored on test data.
    """
    sorted_c = sorted(
        candidates, key=lambda c: (c["relative_cost"], -(c[score_field] or 0.0))
    )
    pareto: list[dict] = []
    best = -1.0
    for c in sorted_c:
        score = c[score_field] or 0.0
        if score > best:
            pareto.append(c)
            best = score
    return pareto


def _format_cost_label(cost_val: float, min_cost: float, in_credits: bool) -> str:
    """Render a candidate's cost for the results table.

    When ``in_credits`` (experiment mode), ``cost_val`` is the absolute
    per-call ``estimated_cost`` in Snowflake credits from the run metrics —
    display it as credits per 1K calls with a ``(cheapest)`` / ``(N.Nx)``
    relative marker.  Otherwise (manual mode) ``cost_val`` is a unitless
    relative-cost multiplier, shown as ``N.Nx``.
    """
    if in_credits:
        per_1k = cost_val * 1000
        cost_str = f"{per_1k:.6f}" if per_1k < 0.01 else f"{per_1k:.4f}"
        if min_cost > 0:
            ratio = cost_val / min_cost
            return (
                f"{cost_str} credits (cheapest)"
                if ratio <= 1.01
                else f"{cost_str} credits ({ratio:.1f}x)"
            )
        return f"{cost_str} credits"
    if cost_val == min_cost:
        return f"{cost_val:.1f}x (cheapest)"
    return f"{cost_val:.1f}x"


def format_results_table(
    results: list[dict],
    seed_score: float | None = None,
    cost_in_credits: bool = False,
) -> str:
    """Format pareto-optimal results as a markdown table.

    Includes a ``Run`` column when any result carries a ``run_name`` field so
    the deployment step can directly identify which experiment run to fetch
    ``function_impl`` from for the user's selected candidate.

    Args:
        results: Pareto-optimal results.
        seed_score: Original score to calculate improvement.
        cost_in_credits: When True, ``relative_cost`` holds the absolute
            per-call ``estimated_cost`` in Snowflake credits (experiment mode)
            and the cost column renders as credits per 1K calls. When False
            (manual mode), it is a unitless relative multiplier rendered as
            ``N.Nx``.

    Returns:
        Markdown table string.

    """
    if not results:
        return "No results to display."

    has_run_name = any(r.get("run_name") for r in results)
    # Experiment rows carry an explicit ``valset_score`` → show a dedicated
    # ``Val Score`` column (plus ``Test Score`` when a test table was used).
    # Manual/Bring your own Model rows carry only a generic ``score`` → single ``Score``
    # column.
    has_val = any(r.get("valset_score") is not None for r in results)
    has_test = any(r.get("test_score") is not None for r in results)
    cost_header = "Est. Credits/1K calls" if cost_in_credits else "Relative Cost"

    headers = ["#"]
    if has_run_name:
        headers.append("Run")
    headers.append("Model")
    if has_val:
        if has_test:
            headers.append("Test Score")
        headers.append("Val Score")
    else:
        headers.append("Score")
    headers += ["Improvement", cost_header]

    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]

    min_cost = min(r["relative_cost"] for r in results) if results else 1.0

    def _pct(value: float | None) -> str:
        return f"{value * 100:.1f}%" if value is not None else "-"

    for i, r in enumerate(results, 1):
        if seed_score is not None:
            improvement = f"{(r['score'] - seed_score) * 100:+.1f}%"
        else:
            improvement = "-"
        cost_label = _format_cost_label(r["relative_cost"], min_cost, cost_in_credits)

        row = [str(i)]
        if has_run_name:
            row.append(r.get("run_name", "-"))
        row.append(r["model"])
        if has_val:
            if has_test:
                row.append(_pct(r.get("test_score")))
            row.append(_pct(r.get("valset_score")))
        else:
            row.append(_pct(r["score"]))
        row += [improvement, cost_label]
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def _seed_baseline(
    session: Session, experiment_name: str
) -> tuple[float | None, float | None]:
    """Read the seed valset/test baseline from the first SEED run.

    Improvement is reported relative to the seed candidate.  The seed may or
    may not survive frontier selection, so its baseline is read from the
    always-present per-model SEED run rather than only the is_frontier set.
    """
    rows = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
    # v3/evolve seed runs are per-model (``<MODEL>_SEED``); v4 has a single
    # global, model-agnostic ``SEED`` run. Match both.
    seed_runs = [
        r["name"]
        for r in rows
        if str(r["name"]).endswith("_SEED") or r["name"] == "SEED"
    ]
    seed_val: float | None = None
    seed_test: float | None = None
    for run_name in seed_runs:
        metrics_rows = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        mv: dict[str, float] = {}
        for r in metrics_rows:
            with contextlib.suppress(TypeError, ValueError):
                mv[r["name"]] = float(r["value"])
        if seed_val is None:
            seed_val = mv.get("valset_score")
        if seed_test is None:
            seed_test = mv.get("test_score")
        if seed_val is not None:
            break
    return seed_val, seed_test


def fetch_experiment_results(session: Session, experiment_name: str) -> dict:
    """Fetch the frontier results from a Snowflake experiment.

    Reads the SEED/ITER runs the optimizer flagged ``is_frontier`` — the
    canonical cross-model hypervolume frontier.  Each such run carries an
    ``estimated_cost`` metric plus ``valset_score`` and (when a test table was
    used) ``test_score``.  No client-side frontier re-derivation is performed.

    Score domains are never mixed: when every frontier candidate has a
    ``test_score`` the table shows test scores (with a presentation-time
    test-Pareto prune); otherwise it shows validation scores for the full
    written frontier.

    Returns:
        Dict with keys:
            results:          list[dict] — frontier candidates in the chosen
                              score domain, cost-sorted, with keys 'model',
                              'score', 'valset_score', 'test_score',
                              'relative_cost', 'run_name'.
            seed_score:       float | None — seed baseline in the same domain.
            avg_output_chars: None — unused; cost comes from stored metrics.
            prompt_chars:     None — unused; cost comes from stored metrics.

    """
    rows = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
    run_names = [r["name"] for r in rows]

    # Candidate runs: any SEED/ITER run that isn't a rejected/failed run.
    # The is_frontier flag (read below from metrics) is the actual filter.
    candidate_run_names = [
        n
        for n in run_names
        if not any(marker in n for marker in _NON_FRONTIER_RUN_MARKERS)
    ]

    raw_candidates: list[dict] = []
    skipped_no_cost: list[str] = []
    found_frontier_run = False

    for run_name in candidate_run_names:
        metrics_rows = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        mv: dict[str, float] = {}
        for r in metrics_rows:
            with contextlib.suppress(TypeError, ValueError):
                mv[r["name"]] = float(r["value"])

        # Only runs the optimizer flagged is_frontier belong to the
        # cross-model hypervolume frontier.
        if mv.get(_IS_FRONTIER_METRIC) != 1:
            continue
        found_frontier_run = True

        params_rows = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        pv = {r["name"]: r["value"] for r in params_rows}

        # The producing model is a run PARAM (v4 global structure) — never the
        # run name. The single v4 SEED run is model-agnostic, so its ``model``
        # param is empty ""; fall back to a "seed" label rather than dropping
        # it, so a frontier-worthy seed candidate still appears in the table.
        model = pv.get("model")
        if not model:
            if pv.get("run_type") == "seed" or run_name == "SEED":
                model = "seed"
            else:
                continue

        estimated_cost = mv.get("estimated_cost")
        if estimated_cost is None:
            skipped_no_cost.append(f"{run_name} (model={model})")
            continue

        raw_candidates.append(
            {
                "model": model,
                "valset_score": mv.get("valset_score"),
                "test_score": mv.get("test_score"),
                # estimated_cost is the absolute per-call cost in credits;
                # carried as relative_cost so the table renders it directly.
                "relative_cost": estimated_cost,
                # run_name lets the deployment step fetch function_impl for the
                # exact candidate the user selects (not just the winner).
                "run_name": run_name,
            }
        )

    if not found_frontier_run:
        raise ValueError(
            f"No is_frontier runs found in experiment {experiment_name}. "
            "The optimization may still be running, was cancelled before the "
            "frontier was selected, or this experiment predates the "
            "is_frontier paradigm."
        )

    if skipped_no_cost:
        print(
            f"WARNING: {len(skipped_no_cost)} frontier run(s) skipped — "
            "no estimated_cost metric. This usually means models.json was not "
            "bundled in the inline SPROC, or the model is not in the rate table "
            "(Bring your own Model/SPCS). Affected runs:\n  "
            + "\n  ".join(skipped_no_cost),
            file=sys.stderr,
        )

    if not raw_candidates:
        raise ValueError(
            f"No is_frontier runs with estimated_cost found in "
            f"{experiment_name}. The cost computation may have failed "
            "(models.json unavailable or model not in rate table). "
            f"Runs missing estimated_cost: {skipped_no_cost or 'none'}."
        )

    seed_val_score, seed_test_score = _seed_baseline(session, experiment_name)

    # Show test scores only when EVERY frontier candidate was test-evaluated;
    # this avoids mixing domains if a candidate is ever missing a test score.
    has_test = all(c.get("test_score") is not None for c in raw_candidates)

    if has_test:
        # A test table was supplied: prune to the test-Pareto-optimal subset
        # and present test scores.
        selected = _pareto_optimal_on(raw_candidates, "test_score")
        score_field = "test_score"
        seed_score = seed_test_score
    else:
        # No test table: present the full written frontier on validation
        # scores (already validation-Pareto-optimal by construction).
        selected = raw_candidates
        score_field = "valset_score"
        seed_score = seed_val_score

    results = [
        {
            "model": c["model"],
            "score": c[score_field],
            "valset_score": c.get("valset_score"),
            "test_score": c.get("test_score") if has_test else None,
            "relative_cost": c["relative_cost"],
            "run_name": c["run_name"],
        }
        for c in selected
    ]
    results.sort(key=lambda r: r["relative_cost"])

    return {
        "results": results,
        "seed_score": seed_score,
        "avg_output_chars": None,
        "prompt_chars": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Present optimization results as a Pareto-optimal table"
    )

    # -- Experiment mode (reads is_frontier SEED/ITER runs from Snowflake) --
    parser.add_argument(
        "--experiment",
        type=str,
        help="Fully-qualified experiment name (DB.SCHEMA.EXP). "
        "When provided, all results and cost inputs are read automatically.",
    )
    parser.add_argument(
        "--connection",
        type=str,
        default="default",
        help="Named Snowflake connection from ~/.snowflake/connections.toml "
        "(default: 'default'). Only used with --experiment.",
    )

    # -- Manual / Bring your own Model mode --
    parser.add_argument("--json", type=str, help="JSON array of results")
    parser.add_argument(
        "--prompt-chars",
        type=int,
        help="Length of system prompt in characters (required without --experiment)",
    )
    parser.add_argument(
        "--avg-output-chars",
        type=int,
        help="Average length of expected output in characters (required without --experiment)",
    )

    parser.add_argument(
        "--seed-score",
        type=float,
        help="Original seed score for improvement calculation "
        "(auto-read when using --experiment)",
    )
    parser.add_argument(
        "--format", choices=["json", "table"], default="json", help="Output format"
    )
    args = parser.parse_args()

    seed_score = args.seed_score

    if args.experiment:
        # -- Experiment mode: read is_frontier SEED/ITER runs from Snowflake --
        from snowflake_ai_optimize.core.session import create_session_from_connection

        session = create_session_from_connection(args.connection)
        fetched = fetch_experiment_results(session, args.experiment)
        results = fetched["results"]
        if seed_score is None:
            seed_score = fetched["seed_score"]
        # Frontier candidates already carry the chosen score domain and cost,
        # are pruned, and cost-sorted — present as-is.
        pareto = results
    else:
        # -- Manual mode: require --json/stdin and explicit cost params --
        if args.prompt_chars is None:
            parser.error("--prompt-chars is required when --experiment is not provided")
        if args.avg_output_chars is None:
            parser.error(
                "--avg-output-chars is required when --experiment is not provided"
            )

        data = json.loads(args.json) if args.json else json.load(sys.stdin)

        results = [data] if isinstance(data, dict) else data
        pareto = filter_pareto_optimal(
            results, args.prompt_chars, args.avg_output_chars
        )

    if args.format == "table":
        # Experiment rows carry the absolute per-call ``estimated_cost`` →
        # render as credits per 1K calls.  Manual rows carry a unitless
        # relative multiplier → render as ``N.Nx``.
        print(
            format_results_table(
                pareto, seed_score, cost_in_credits=bool(args.experiment)
            )
        )
    else:
        print(json.dumps({"pareto_optimal": pareto}, indent=2))


if __name__ == "__main__":
    main()
