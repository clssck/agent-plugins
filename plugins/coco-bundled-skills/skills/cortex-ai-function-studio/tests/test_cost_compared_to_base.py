# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""The ``cost_compared_to_base`` optimize metric (``build_run_metrics``)."""

from __future__ import annotations

from snowflake_ai_optimize.core.experiment import build_run_metrics


def _by_name(metrics):
    return {m["name"]: m["value"] for m in (metrics or [])}


def test_ratio_computed_from_base():
    # run cost 2.5, base seed cost 5.0 -> 0.5
    m = _by_name(build_run_metrics(estimated_cost=2.5, base_cost=5.0))
    assert m["estimated_cost"] == 2.5
    assert m["cost_compared_to_base"] == 0.5


def test_seed_is_one():
    m = _by_name(build_run_metrics(estimated_cost=5.0, base_cost=5.0))
    assert m["cost_compared_to_base"] == 1.0


def test_absent_without_base():
    # estimated_cost but no base -> only estimated_cost, no ratio
    m = _by_name(build_run_metrics(estimated_cost=2.5))
    assert "estimated_cost" in m
    assert "cost_compared_to_base" not in m


def test_zero_base_skipped():
    # base_cost 0 must not divide-by-zero
    m = _by_name(build_run_metrics(estimated_cost=2.5, base_cost=0.0))
    assert "cost_compared_to_base" not in m


def test_absent_without_estimated_cost():
    m = _by_name(build_run_metrics(valset_score=0.9, base_cost=5.0))
    assert "cost_compared_to_base" not in m


if __name__ == "__main__":
    test_ratio_computed_from_base()
    test_seed_is_one()
    test_absent_without_base()
    test_zero_base_skipped()
    test_absent_without_estimated_cost()
    print("ok")
