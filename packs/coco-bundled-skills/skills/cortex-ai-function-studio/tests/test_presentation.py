# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for scripts/presentation.py.

Runs locally without a Snowflake connection. ``scripts/`` is on the test
``sys.path`` (see other ``scripts/`` unit tests), so the module imports by name.
"""

from __future__ import annotations

import pytest
from presentation import (  # type: ignore[import-not-found]
    _pareto_optimal_on,
    fetch_experiment_results,
    format_results_table,
)


class _Row(dict):
    """dict that also supports row["name"] access used by the script."""


class _FakeShowSession:
    """Fake Snowpark session that answers SHOW RUNS / METRICS / PARAMETERS.

    ``runs`` maps run_name -> {"params": {...}, "metrics": {...}}.
    """

    def __init__(self, runs: dict[str, dict]):
        self._runs = runs

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def collect(self):
            return self._rows

    def sql(self, sql: str):
        s = sql.strip()
        if s.startswith("SHOW RUNS IN EXPERIMENT"):
            return self._Result([_Row(name=n) for n in self._runs])
        if s.startswith("SHOW RUN PARAMETERS"):
            run = s.split(" RUN ")[-1].strip()
            params = self._runs.get(run, {}).get("params", {})
            return self._Result([_Row(name=k, value=v) for k, v in params.items()])
        if s.startswith("SHOW RUN METRICS"):
            run = s.split(" RUN ")[-1].strip()
            metrics = self._runs.get(run, {}).get("metrics", {})
            return self._Result([_Row(name=k, value=v) for k, v in metrics.items()])
        raise AssertionError(f"unexpected SQL: {sql}")


def _fc_run(model, cost, val, test=None, impl="BODY", is_frontier=True):
    """Build a SEED/ITER run dict.

    Frontier runs carry the ``is_frontier`` flag the presentation layer reads;
    ``is_pareto_optimal`` is the within-model flag and is orthogonal.
    """
    metrics = {"valset_score": val, "estimated_cost": cost, "is_pareto_optimal": 1}
    if is_frontier:
        metrics["is_frontier"] = 1
    if test is not None:
        metrics["test_score"] = test
    return {"params": {"model": model, "function_impl": impl}, "metrics": metrics}


class TestPareto:
    def test_drops_dominated_on_field(self):
        rows = [
            {"model": "a", "relative_cost": 1.0, "test_score": 0.7},
            {"model": "b", "relative_cost": 2.0, "test_score": 0.6},  # dominated
            {"model": "c", "relative_cost": 3.0, "test_score": 0.9},
        ]
        out = _pareto_optimal_on(rows, "test_score")
        models = {r["model"] for r in out}
        assert models == {"a", "c"}


class TestFetchExperimentResults:
    def test_no_frontier_runs_raises(self):
        # A SEED run with no is_frontier flag is not part of the frontier.
        session = _FakeShowSession(
            {"M1_SEED": _fc_run("m1", 0.001, 0.8, is_frontier=False)}
        )
        with pytest.raises(ValueError, match="No is_frontier runs"):
            fetch_experiment_results(session, "DB.SC.EXP")

    def test_val_domain_when_no_test(self):
        runs = {
            # SEED is on the frontier and doubles as the seed baseline.
            "M1_SEED": _fc_run("m1", 0.001, 0.80),
            "M1_ITER_2": _fc_run("m1", 0.004, 0.91),
            # A rejected run is never a frontier candidate.
            "M1_REJECTED_1": _fc_run("m1", 0.002, 0.5, is_frontier=False),
        }
        fetched = fetch_experiment_results(_FakeShowSession(runs), "DB.SC.EXP")
        results = fetched["results"]
        assert len(results) == 2
        # No test scores anywhere → val domain, seed baseline from SEED.
        assert all(r["test_score"] is None for r in results)
        assert fetched["seed_score"] == pytest.approx(0.80)
        # cost-sorted ascending
        assert results[0]["relative_cost"] <= results[1]["relative_cost"]
        assert results[0]["run_name"].endswith("_SEED")

    def test_test_domain_and_prune_when_test_present(self):
        runs = {
            # cheapest, decent test score — also the seed baseline
            "M1_SEED": _fc_run("m1", 0.001, 0.80, test=0.78),
            # pricier but WORSE on test → dominated, should be pruned
            "M1_ITER_1": _fc_run("m1", 0.003, 0.85, test=0.70),
            # priciest, best on test → kept
            "M2_ITER_2": _fc_run("m2", 0.005, 0.91, test=0.90),
        }
        fetched = fetch_experiment_results(_FakeShowSession(runs), "DB.SC.EXP")
        results = fetched["results"]
        # Test domain: every result exposes a test score; val also retained.
        assert all(r["test_score"] is not None for r in results)
        # The test-dominated candidate (cost 0.003 / test 0.70) is dropped.
        kept_costs = sorted(r["relative_cost"] for r in results)
        assert kept_costs == pytest.approx([0.001, 0.005])
        assert fetched["seed_score"] == pytest.approx(0.78)


class TestFormatResultsTable:
    def test_run_and_test_columns_present(self):
        results = [
            {
                "model": "m1",
                "score": 0.78,
                "valset_score": 0.80,
                "test_score": 0.78,
                "relative_cost": 0.001,
                "run_name": "M1_SEED",
            }
        ]
        table = format_results_table(results, seed_score=0.70, cost_in_credits=True)
        # Run column precedes Model; Test Score precedes Val Score; credits/1K cost.
        header = table.splitlines()[0]
        assert header.index("Run") < header.index("Model")
        assert header.index("Test Score") < header.index("Val Score")
        assert "Est. Credits/1K calls" in header
        assert "M1_SEED" in table

    def test_val_only_table_omits_test_column(self):
        results = [
            {
                "model": "m1",
                "score": 0.80,
                "valset_score": 0.80,
                "test_score": None,
                "relative_cost": 0.001,
                "run_name": "M1_ITER_2",
            }
        ]
        table = format_results_table(results, seed_score=0.70, cost_in_credits=True)
        header = table.splitlines()[0]
        assert "Val Score" in header
        assert "Test Score" not in header
