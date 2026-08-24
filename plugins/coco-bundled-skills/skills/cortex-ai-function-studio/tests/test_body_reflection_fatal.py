# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""A persistently failing reflection call fails the model (spec-driven path).

GEPA catches a reflection exception internally and produces no candidate, so a
failed reflection call is normally invisible to the outer loop — the model
finishes ``completed`` with the error swallowed. With
``fail_on_reflection_error=True`` (the spec-driven EXECUTE EXPERIMENT path) the
reflection LM records the exhausted-retry error in a sink; the body optimizer
then raises it into its existing failure path so the model ends ``failed`` with
the reflection error, which the caller surfaces on the run.

This drives ``_run_single_model_body_optimization`` with a faked
``optimize_anything`` that mimics GEPA calling the reflection LM (which raises,
under a patched AI_COMPLETE) and swallowing the exception. No Snowflake I/O.

Run:
    uv run --group test pytest tests/test_body_reflection_fatal.py -v
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace
from unittest.mock import MagicMock

from snowflake_ai_optimize.gepa import adapter, optimize_body


def _run(monkeypatch, *, fail_on_reflection_error: bool):
    """Drive one single-model body optimization with reflection AI_COMPLETE broken."""
    # Neutralize the two pure helpers that touch function_def so we can pass a
    # bare MagicMock function_def (the faked optimize_anything never evaluates).
    monkeypatch.setattr(
        optimize_body, "make_body_evaluator", lambda *a, **k: lambda *aa, **kk: []
    )
    monkeypatch.setattr(
        optimize_body, "build_objective_and_background", lambda *a, **k: ("obj", "bg")
    )
    # Every reflection AI_COMPLETE call fails.
    monkeypatch.setattr(
        adapter.RobustAIComplete,
        "call_ai_complete",
        MagicMock(side_effect=RuntimeError("reflection model unavailable")),
    )
    monkeypatch.setattr(adapter.time, "sleep", lambda *_a, **_k: None)

    def fake_optimize_anything(**kwargs):
        # Mimic GEPA: invoke the reflection LM, then swallow its exception
        # exactly as the reflective-mutation proposer does (returns no candidate).
        lm = kwargs["config"].reflection.reflection_lm
        with contextlib.suppress(Exception):
            lm("please reflect on these failures")
        return SimpleNamespace(best_candidate={"body": kwargs["seed_candidate"]})

    monkeypatch.setattr(optimize_body, "optimize_anything", fake_optimize_anything)

    return optimize_body._run_single_model_body_optimization(
        model="claude-haiku-4-5",
        session=MagicMock(),
        function_def=MagicMock(),
        seed_body="SELECT AI_COMPLETE('claude-haiku-4-5', PROMPT)",
        function_name="DB.S.FN",
        function_signature="DB.S.FN(VARCHAR)",
        trainset=[{"inputs": {"Q": "x"}, "answer": "y"}],
        valset=[{"inputs": {"Q": "x"}, "answer": "y"}],
        input_col_names=["Q"],
        input_columns=["Q"],
        metric_evaluator=MagicMock(),
        reflection_model="claude-opus-4-7",
        temperature=0.0,
        max_tokens=64,
        resolved_budget=100,
        reflection_weight=1,
        metric_name="exact_match",
        test_table=None,
        label_column="ANSWER",
        dataset_expected_columns=None,
        run_id="rid",
        aggregation_metric=None,
        experiment_name=None,  # skip run-commit plumbing; isolate the glue
        dataset_load_start_perf=None,
        dataset_load_end_perf=None,
        fail_on_reflection_error=fail_on_reflection_error,
    )


def test_persistent_reflection_failure_fails_the_model(monkeypatch):
    result = _run(monkeypatch, fail_on_reflection_error=True)
    assert result.status == "failed"
    # The reflection error is carried on the result (the caller records it on
    # the run's error_message and commits the run FAILED).
    assert "Reflection call failed after" in (result.error or "")
    assert "reflection model unavailable" in (result.error or "")
