# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Offline checks for the YAML-handler golden harness (no Snowflake).

Exercises the tokenizer + normalizer in ``tests/_experiment_golden.py`` against
fake experiment trees, and validates the SPEC YAML corpus in
``tests/e2e_scenarios/yaml_handler/`` (every SPEC parses, fills its placeholders
into valid handler input, and the eval/opt coverage matrix is complete). These
run in the normal (non-e2e) suite so the golden harness is protected without a
live connection. The live recording / verification lives in
``tests/test_yaml_handler_golden_e2e.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from _experiment_golden import (
    NONE_TOKEN,
    build_golden,
    dump_golden,
    make_tokenizer,
    summarize_iteration_runs,
    verify_or_record,
)

_YAML_HANDLER_DIR = Path(__file__).parent / "e2e_scenarios" / "yaml_handler"
SPEC_DIR = _YAML_HANDLER_DIR / "specs"


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------


class TestTokenizer:
    def test_replaces_longest_first_and_case_insensitive(self):
        tok = make_tokenizer(
            {
                "DB.SCH.F_RUN(VARCHAR)": "__FUNCTION__",
                "DB": "__DB__",
                "SCH": "__SCHEMA__",
            }
        )
        # The full signature is rewritten as one token, not shredded into its
        # DB / SCH components, because longer sources are applied first.
        assert tok("DB.SCH.F_RUN(VARCHAR)") == "__FUNCTION__"
        # Case-insensitive: lower-case occurrences are still matched.
        assert tok("value db.sch.other") == "value __DB__.__SCHEMA__.other"

    def test_non_string_passthrough(self):
        tok = make_tokenizer({"DB": "__DB__"})
        assert tok(12) == 12
        assert tok(None) is None
        assert tok(True) is True


# ---------------------------------------------------------------------------
# Fake trees
# ---------------------------------------------------------------------------

_FUNC = "TEST_DB.PUBLIC.F_LOCAL_123(VARCHAR)"
_EXP = "TEST_DB.PUBLIC.EXP_LOCAL_123"


def _eval_tree(*, with_cost: bool = False) -> dict:
    metrics = {"score": 0.75}
    if with_cost:
        metrics |= {
            "estimated_cost": 0.001,
            "avg_prompt_tokens": 40.0,
            "avg_completion_tokens": 3.0,
        }
    return {
        _EXP: {
            "EVAL": {
                "metrics": metrics,
                "parameters": {
                    "function_impl": "",
                    "model": "llama3.1-8b",
                    "iteration": "0",
                    "is_full_eval": "true",
                    "status": "completed",
                    "function_name": _FUNC,
                    "metric_name": "exact_match",
                    "custom_metric_udf": "",
                    "num_examples": "12",
                    "elapsed_seconds": "1.23",
                },
                "metadata": {
                    "status": "FINISHED",
                    "created_on": "2026-07-27T00:00:00Z",
                },
            }
        }
    }


def _eval_result() -> dict:
    return {
        "experiment": _EXP,
        "run": "EVAL",
        "status": "SUCCEEDED",
        "metrics": {"exact_match": 0.75},
        "num_examples": 12,
    }


def _opt_tree() -> dict:
    seed = {
        "metrics": {
            "valset_score": 0.6,
            "test_score": 0.55,
            "is_frontier": 1,
            "estimated_cost": 0.001,
        },
        "parameters": {
            "run_type": "seed",
            "model": "llama3.1-8b",
            "iteration": "0",
            "is_full_eval": "true",
            "status": "completed",
            "metric_name": "exact_match",
            "function_name": _FUNC,
            "function_impl": "AI_COMPLETE(...)",
            "global_iteration": "0",
            "per_model_stats": "{}",
            "total_candidates": "3",
            "experiment_schema_version": "4",
            "num_examples": "6",
            "elapsed_seconds": "5.0",
        },
        "metadata": {"status": "FINISHED"},
    }
    iter1 = {
        "metrics": {"valset_score": 0.7, "is_frontier": 1},
        "parameters": {
            "run_type": "iteration",
            "model": "llama3.1-8b",
            "iteration": "1",
            "is_full_eval": "false",
            "status": "completed",
            "metric_name": "exact_match",
            "function_name": _FUNC,
            "function_impl": "AI_COMPLETE(v1)",
            "global_iteration": "1",
            "num_examples": "6",
        },
        "metadata": {"status": "FINISHED"},
    }
    iter2 = {
        "metrics": {"valset_score": 0.5},
        "parameters": {
            "run_type": "rejected",
            "model": "llama3.1-8b",
            "iteration": "2",
            "is_full_eval": "false",
            "status": "completed",
            "metric_name": "exact_match",
            "function_name": _FUNC,
            "function_impl": "AI_COMPLETE(v2)",
            "global_iteration": "2",
            "rejection_kind": "worse",
            "rejection_reason": "lower val score",
            "num_examples": "6",
        },
        # A rejected candidate's run is left uncommitted (RUNNING).
        "metadata": {"status": "RUNNING"},
    }
    return {_EXP: {"SEED": seed, "ITER_1": iter1, "ITER_2": iter2}}


def _tok():
    return make_tokenizer(
        {_FUNC: "__FUNCTION__", _EXP: "__EXP__", "LOCAL_123": "__RUNKEY__"}
    )


# ---------------------------------------------------------------------------
# build_golden — evaluation
# ---------------------------------------------------------------------------


class TestEvalGolden:
    def test_exact_run_snapshot(self):
        golden = build_golden(
            job_kind="evaluation",
            result=_eval_result(),
            tree=_eval_tree(),
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        assert golden["job_kind"] == "evaluation"
        # Result: run name kept, num_examples deterministic, metric keys only.
        assert golden["result"] == {
            "status": "SUCCEEDED",
            "experiment": "__EXP__",
            "run": "EVAL",
            "num_examples": 12,
            "metric_keys": ["exact_match"],
        }
        run = golden["runs"]["EVAL"]
        assert run["count"] == 1
        assert run["run_types"] == [NONE_TOKEN]  # eval runs record no run_type
        assert run["statuses"] == ["FINISHED"]
        # Deterministic param values kept; function name tokenized; volatile
        # elapsed_seconds dropped; num_examples kept as key only; and for EVAL
        # the ``model`` value is redacted (it is the external LLM_JUDGE default,
        # not SPEC-determined) — its KEY is still recorded in param_keys.
        assert run["params"] == {
            "custom_metric_udf": "",
            "function_name": "__FUNCTION__",
            "is_full_eval": "true",
            "iteration": "0",
            "metric_name": "exact_match",
            "status": "completed",
        }
        assert "model" not in run["params"]
        assert run["param_keys"] == [
            "custom_metric_udf",
            "function_impl",
            "function_name",
            "is_full_eval",
            "iteration",
            "metric_name",
            "model",
            "num_examples",
            "status",
        ]
        assert run["metric_keys"] == ["score"]
        assert "elapsed_seconds" not in run["param_keys"]

    def test_builtin_cost_metrics_captured_as_keys(self):
        golden = build_golden(
            job_kind="evaluation",
            result=_eval_result(),
            tree=_eval_tree(with_cost=True),
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        assert golden["runs"]["EVAL"]["metric_keys"] == [
            "avg_completion_tokens",
            "avg_prompt_tokens",
            "estimated_cost",
            "score",
        ]

    def test_multi_run_result_runs_sorted(self):
        tree = {
            _EXP: {
                "EVAL_1": _eval_tree()[_EXP]["EVAL"],
                "EVAL_2": _eval_tree()[_EXP]["EVAL"],
            }
        }
        result = {
            "experiment": _EXP,
            "runs": ["EVAL_2", "EVAL_1"],
            "status": "SUCCEEDED",
            "metrics": {"EVAL_1": {"exact_match": 0.5}, "EVAL_2": {"exact_match": 0.6}},
            "num_examples": 12,
        }
        golden = build_golden(
            job_kind="evaluation",
            result=result,
            tree=tree,
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        assert golden["result"]["runs"] == ["EVAL_1", "EVAL_2"]
        assert set(golden["runs"]) == {"EVAL_1", "EVAL_2"}
        # Multi-run eval nests metrics by run name; metric_keys must be the
        # metric NAME (exact_match), NOT the run names.
        assert golden["result"]["metric_keys"] == ["exact_match"]

    def test_judge_model_value_kept_when_spec_sets_it(self):
        # When the SPEC explicitly specifies judge_model the model value is
        # SPEC-determined — it should be asserted in the golden (not redacted).
        golden = build_golden(
            job_kind="evaluation",
            result=_eval_result(),
            tree=_eval_tree(),
            experiment_name=_EXP,
            tokenize=_tok(),
            spec_judge_model="llama3.1-8b",
        )
        run = golden["runs"]["EVAL"]
        assert run["params"].get("model") == "llama3.1-8b"

    def test_judge_model_value_redacted_when_spec_omits_it(self):
        # When judge_model is omitted from the SPEC the model value resolves to
        # LLM_JUDGE_DEFAULT_MODEL (an external constant) — redact the value but
        # keep the key so a change to the default is caught at the key level.
        golden = build_golden(
            job_kind="evaluation",
            result=_eval_result(),
            tree=_eval_tree(),
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        run = golden["runs"]["EVAL"]
        assert "model" not in run["params"]
        assert "model" in run["param_keys"]


# ---------------------------------------------------------------------------
# build_golden — optimization
# ---------------------------------------------------------------------------


class TestOptGolden:
    def test_only_deterministic_seed_is_snapshotted(self):
        golden = build_golden(
            job_kind="optimization",
            result={
                "status": "SUCCEEDED",
                "experiment": _EXP,
                "overall_best_val_score": 0.7,
            },
            tree=_opt_tree(),
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        assert golden["job_kind"] == "optimization"
        assert golden["result"] == {
            "status": "SUCCEEDED",
            "experiment": "__EXP__",
            "best_score_present": True,
        }
        # Only the deterministic SEED is pinned; the nondeterministic ITER_<N>
        # runs are NOT snapshotted (verified structurally instead).
        assert set(golden["runs"]) == {"SEED"}

        seed = golden["runs"]["SEED"]
        assert seed["count"] == 1
        assert seed["run_types"] == ["seed"]
        assert seed["params"]["run_type"] == "seed"
        assert seed["params"]["function_name"] == "__FUNCTION__"
        assert seed["params"]["experiment_schema_version"] == "4"
        assert seed["params"]["model"] == "llama3.1-8b"
        # SEED-only bookkeeping keys are part of its contract (values redacted).
        assert "per_model_stats" in seed["param_keys"]
        assert "total_candidates" in seed["param_keys"]
        # ``is_frontier`` and ``test_score`` are excluded from ``_CURATED_METRIC_KEYS``
        # (frontier-contingent) so they must NOT appear here.
        assert seed["metric_keys"] == ["estimated_cost", "valset_score"]

    def test_opt_seed_missing_yields_empty_runs(self):
        # A degenerate tree with no SEED yields an empty runs map (the e2e test
        # asserts SEED presence separately).
        golden = build_golden(
            job_kind="optimization",
            result={"status": "SUCCEEDED", "experiment": _EXP},
            tree={_EXP: {}},
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        assert golden["runs"] == {}
        assert golden["result"]["best_score_present"] is False


class TestSummarizeIterationRuns:
    def test_wellformed_iteration_and_rejected_runs(self):
        # FINISHED iteration run + RUNNING (uncommitted) rejected run: both are
        # expected states, so no violations.
        summary = summarize_iteration_runs(_opt_tree(), _EXP)
        assert summary["count"] == 2  # ITER_1 + ITER_2 (SEED excluded)
        assert summary["run_types"] == ["iteration", "rejected"]
        assert summary["statuses"] == ["FINISHED", "RUNNING"]
        assert summary["violations"] == []

    def test_zero_iterations_is_allowed(self):
        tree = {_EXP: {"SEED": _opt_tree()[_EXP]["SEED"]}}
        summary = summarize_iteration_runs(tree, _EXP)
        assert summary["count"] == 0
        assert summary["violations"] == []

    def test_malformed_non_seed_runs_flagged(self):
        tree = {
            _EXP: {
                "SEED": _opt_tree()[_EXP]["SEED"],
                "BEST": {  # bad name, bad run_type, bad status
                    "metrics": {},
                    "parameters": {"run_type": "final"},
                    "metadata": {"status": "FAILED"},
                },
            }
        }
        summary = summarize_iteration_runs(tree, _EXP)
        assert summary["count"] == 1
        violations = " ".join(summary["violations"])
        assert "not named ITER_<n>" in violations
        assert "run_type" in violations
        assert "status='FAILED'" in violations


# ---------------------------------------------------------------------------
# verify_or_record
# ---------------------------------------------------------------------------


class TestVerifyOrRecord:
    def test_record_then_verify_roundtrip(self, tmp_path, monkeypatch):
        golden = build_golden(
            job_kind="evaluation",
            result=_eval_result(),
            tree=_eval_tree(),
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        path = tmp_path / "eval.golden.yaml"

        # Record mode writes the file.
        monkeypatch.setenv("UPDATE_EXPERIMENT_GOLDEN", "1")
        verify_or_record(path, golden)
        assert path.exists()

        # Verify mode passes against the just-recorded golden.
        monkeypatch.delenv("UPDATE_EXPERIMENT_GOLDEN", raising=False)
        verify_or_record(path, golden)  # no raise

    def test_missing_golden_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("UPDATE_EXPERIMENT_GOLDEN", raising=False)
        with pytest.raises(AssertionError, match="does not exist"):
            verify_or_record(
                tmp_path / "missing.golden.yaml", {"job_kind": "evaluation"}
            )

    def test_mismatch_raises_with_diff(self, tmp_path, monkeypatch):
        path = tmp_path / "eval.golden.yaml"
        monkeypatch.setenv("UPDATE_EXPERIMENT_GOLDEN", "1")
        verify_or_record(path, {"job_kind": "evaluation", "runs": {}})
        monkeypatch.delenv("UPDATE_EXPERIMENT_GOLDEN", raising=False)
        with pytest.raises(AssertionError, match="golden mismatch"):
            verify_or_record(path, {"job_kind": "optimization", "runs": {}})

    def test_dump_is_sorted_and_stable(self):
        golden = build_golden(
            job_kind="evaluation",
            result=_eval_result(),
            tree=_eval_tree(),
            experiment_name=_EXP,
            tokenize=_tok(),
        )
        text = dump_golden(golden)
        assert dump_golden(golden) == text  # deterministic
        # Sorted keys: top-level job_kind before result before runs.
        assert text.index("job_kind") < text.index("result") < text.index("runs")


# ---------------------------------------------------------------------------
# SPEC corpus
# ---------------------------------------------------------------------------

_EVAL_SPECS = sorted(SPEC_DIR.glob("eval_*.yaml"))
_OPT_SPECS = sorted(SPEC_DIR.glob("opt_*.yaml"))
_ALL_SPECS = sorted(SPEC_DIR.glob("*.yaml"))
_INVALID_SPECS = sorted((_YAML_HANDLER_DIR / "invalid").glob("*.yaml"))


class TestSpecCorpus:
    def test_counts(self):
        assert len(_EVAL_SPECS) == 9, [p.name for p in _EVAL_SPECS]
        assert len(_OPT_SPECS) == 8, [p.name for p in _OPT_SPECS]
        assert len(_INVALID_SPECS) == 4, [p.name for p in _INVALID_SPECS]

    @pytest.mark.parametrize("path", _ALL_SPECS, ids=[p.stem for p in _ALL_SPECS])
    def test_spec_fills_to_valid_handler_input(self, path):
        text = path.read_text(encoding="utf-8")
        filled = (
            text.replace("__FUNCTION__", "DB.SCH.F(VARCHAR)")
            .replace("__METRIC_UDF__", "DB.SCH.M")
            .replace("__TABLE__", "DB.SCH.T")
        )
        spec = yaml.safe_load(filled)
        assert isinstance(spec, dict)
        assert "function" in spec and "metrics" in spec and "dataset" in spec
        assert ("evaluation" in spec) ^ ("optimization" in spec)
        assert spec["dataset"]["name"] == "DB.SCH.T"
        # No leftover placeholders anywhere in the filled text.
        for placeholder in ("__FUNCTION__", "__TABLE__", "__METRIC_UDF__"):
            assert placeholder not in filled
        func = spec["function"]
        # Exactly one of function_name / query_text (the handler's own rule).
        assert ("function_name" in func) ^ ("query_text" in func)
        if "function_name" in func:
            assert func["function_name"] == "DB.SCH.F(VARCHAR)"

    @pytest.mark.parametrize(
        "path", _INVALID_SPECS, ids=[p.stem for p in _INVALID_SPECS]
    )
    def test_invalid_spec_parses_but_is_malformed(self, path):
        """Invalid SPECs are well-formed YAML but violate a handler rule."""
        text = path.read_text(encoding="utf-8")
        filled = text.replace("__FUNCTION__", "DB.SCH.F(VARCHAR)").replace(
            "__TABLE__", "DB.SCH.T"
        )
        spec = yaml.safe_load(filled)
        assert isinstance(spec, dict)
        # Each names either an eval or opt job (so it reaches real validation).
        assert ("evaluation" in spec) ^ ("optimization" in spec)

    def test_metric_and_argmap_coverage(self):
        """The eval corpus spans the metric families and argmap/shape axes."""
        metrics: set[str] = set()
        saw_positional = saw_named = saw_mapping = saw_list = False
        saw_query_text = saw_function_name = False
        multi_run = False
        for path in _ALL_SPECS:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
            m = spec["metrics"]
            entry = m[0] if isinstance(m, list) else m
            metrics.add(entry["name"])
            if isinstance(m, list):
                saw_list = True
            else:
                saw_mapping = True
            argmap = (
                spec["dataset"].get("column_mapping", {}).get("argument_mapping", {})
            )
            if any(str(k).startswith("$") for k in argmap):
                saw_positional = True
            if any(not str(k).startswith("$") for k in argmap):
                saw_named = True
            if "query_text" in spec["function"]:
                saw_query_text = True
            if "function_name" in spec["function"]:
                saw_function_name = True
            if spec.get("evaluation", {}).get("num_eval_runs", 1) > 1:
                multi_run = True
        assert {
            "exact_match",
            "fuzzy_match",
            "contains_match",
            "llm-judge",
            "custom",
        } <= metrics
        assert saw_positional and saw_named
        assert saw_mapping and saw_list
        assert saw_query_text and saw_function_name
        assert multi_run

    def test_opt_specs_use_valid_budget(self):
        """Opt SPECs use a canonical budget (the spec path rejects 'demo')."""
        for path in _OPT_SPECS:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
            opt = spec["optimization"]
            assert opt["budget"] in {"ultra-light", "light", "medium", "heavy"}
            assert opt["models"], f"{path.name}: models must be non-empty"
