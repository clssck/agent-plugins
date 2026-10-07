# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Offline unit tests for the experiment JSON-tree builder.

These run WITHOUT a live Snowflake connection (a fake session returns canned
SHOW RUNS / SHOW RUN PARAMETERS / SHOW RUN METRICS rows), so the deterministic
tree-building logic used by the input-types e2e test is verified in normal CI.
Not marked ``e2e``.
"""

from __future__ import annotations

import json

import pytest
from _experiment_tree import (
    build_experiment_tree,
    render_experiment_tree,
)

_EXP = "DB.SC.TEST_OPT_EXP"


class _FakeQuery:
    def __init__(self, sql: str, runs: dict):
        self._sql = sql
        self._runs = runs

    def _run_name(self) -> str:
        # The trailing " RUN <name>" — rsplit avoids matching the " RUN " inside
        # "SHOW RUN PARAMETERS" / "SHOW RUN METRICS".
        return self._sql.rsplit(" RUN ", 1)[1].strip()

    def collect(self) -> list[dict]:
        sql = self._sql
        if "SHOW RUNS IN EXPERIMENT" in sql:
            return [
                {"name": name, "metadata": json.dumps(spec.get("metadata", {}))}
                for name, spec in self._runs.items()
            ]
        if "SHOW RUN PARAMETERS" in sql:
            spec = self._runs[self._run_name()]
            return [{"name": k, "value": v} for k, v in spec["parameters"].items()]
        if "SHOW RUN METRICS" in sql:
            spec = self._runs[self._run_name()]
            return [{"name": k, "value": v} for k, v in spec["metrics"].items()]
        return []


class _FakeSession:
    """Duck-typed Snowpark session that serves a canned experiment."""

    def __init__(self, runs: dict):
        self._runs = runs

    def sql(self, sql: str) -> _FakeQuery:
        return _FakeQuery(sql, self._runs)


def _sample_runs(*, seed_score="0.60", iter_score="0.85", status="FINISHED") -> dict:
    """A realistic v4 experiment: one SEED, one accepted ITER, one rejected ITER.

    Metric/metadata values are parameterized so tests can vary them and confirm
    the schema is value-agnostic.  Metric values are intentionally a MIX of
    string and numeric to exercise coercion (as Snowflake may return either).
    """
    return {
        "SEED": {
            "parameters": {
                "run_type": "seed",
                "model": "llama3.1-8b",
                "iteration": "0",
                "global_iteration": "0",
                "total_candidates": "3",
            },
            "metrics": {
                "valset_score": seed_score,
                "estimated_cost": 0.001,
                "is_pareto_optimal": "1",
                "is_frontier": 1,
            },
            "metadata": {"status": status},
        },
        "ITER_1": {
            "parameters": {
                "run_type": "iteration",
                "model": "claude-haiku-4-5",
                "iteration": "1",
                "global_iteration": "1",
                "parent_candidate": "SEED",
            },
            "metrics": {
                "valset_score": iter_score,
                "estimated_cost": 0.004,
                "is_pareto_optimal": 1,
                "is_frontier": "1",
            },
            "metadata": {"status": status},
        },
        "ITER_2": {
            "parameters": {
                "run_type": "rejected",
                "model": "claude-haiku-4-5",
                "iteration": "1",
                "global_iteration": "2",
                "status": "rejected",
            },
            "metrics": {},  # rejected proposals carry no valset/frontier metrics
            "metadata": {"status": status},
        },
    }


def test_build_tree_shape_and_types():
    tree = build_experiment_tree(_FakeSession(_sample_runs()), _EXP)

    assert set(tree) == {_EXP}
    runs = tree[_EXP]
    assert set(runs) == {"SEED", "ITER_1", "ITER_2"}

    for run in runs.values():
        assert set(run) == {"metrics", "parameters", "metadata"}

    # Metric values are coerced to numbers (even the string "1" / "0.60").
    seed = runs["SEED"]
    assert seed["parameters"]["run_type"] == "seed"
    assert seed["parameters"]["model"] == "llama3.1-8b"
    assert seed["metrics"]["valset_score"] == pytest.approx(0.60)
    assert seed["metrics"]["is_pareto_optimal"] == 1
    assert all(isinstance(v, (int, float)) for v in runs["ITER_1"]["metrics"].values())
    # Parameter values are all strings.
    assert all(isinstance(v, str) for v in seed["parameters"].values())
    # Metadata is a dict carrying the run status.
    assert seed["metadata"]["status"] == "FINISHED"


def test_render_is_valid_json():
    tree = build_experiment_tree(_FakeSession(_sample_runs()), _EXP)
    rendered = render_experiment_tree(tree)
    assert json.loads(rendered) == tree
