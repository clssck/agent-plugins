# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Per-run ``eval_detail.json`` capture + upload.

Covers the "every run stores its eval detail" behaviour:
- the shared record builder + candidate join key,
- the GEPA adapter capturing per-candidate rows from its own evaluations
  (no extra eval calls), with subsample vs full-valset labelling,
- the progressive tracker draining that buffer into ``eval_detail.json``,
- SEED/BEST artifacts routed to their own runs,
- the standalone eval path uploading its ``eval_detail.json``.

Run:
    uv run --group test pytest tests/test_eval_detail_capture.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from snowflake_ai_optimize.core.evaluation import build_eval_detail_record
from snowflake_ai_optimize.core.scorer import ScoredExample
from snowflake_ai_optimize.gepa.adapter import (
    SnowflakeAdapter,
    _CapturedEval,
    candidate_detail_key,
)


@pytest.fixture(scope="session", autouse=True)
def cleanup_stale_test_objects():
    """Override conftest fixture -- no Snowflake connection needed for unit tests."""
    yield


# ---------------------------------------------------------------------------
# build_eval_detail_record — canonical row shape + truncation
# ---------------------------------------------------------------------------


class TestBuildEvalDetailRecord:
    def test_all_fields_present(self):
        rec = build_eval_detail_record(
            row_id=3,
            input_text="in",
            expected="exp",
            predicted="pred",
            metric_score=0.5,
            metric_feedback="fb",
            metric_name="exact_match",
            model_name="mistral-large2",
            split="val_full",
        )
        assert rec == {
            "row_id": 3,
            "input_text": "in",
            "expected": "exp",
            "predicted": "pred",
            "metric_score": 0.5,
            "metric_feedback": "fb",
            "error_message": "",
            "metric_name": "exact_match",
            "model_name": "mistral-large2",
            "split": "val_full",
        }

    def test_none_text_becomes_empty_string(self):
        rec = build_eval_detail_record(
            row_id=0,
            input_text="i",
            expected="e",
            predicted="p",
            metric_score=None,
            metric_feedback=None,
            metric_name="m",
            model_name="mdl",
            split="s",
            error_message=None,
        )
        assert rec["metric_feedback"] == ""
        assert rec["error_message"] == ""
        assert rec["metric_score"] is None

    def test_max_length_truncates_text_fields(self):
        rec = build_eval_detail_record(
            row_id=0,
            input_text="x" * 100,
            expected="y" * 100,
            predicted="z" * 100,
            metric_score=1.0,
            metric_feedback="f" * 100,
            metric_name="m",
            model_name="mdl",
            split="s",
            max_length=10,
        )
        assert len(rec["input_text"]) == 10
        assert len(rec["expected"]) == 10
        assert len(rec["predicted"]) == 10
        assert len(rec["metric_feedback"]) == 10

    def test_non_str_predicted_is_serialized(self):
        rec = build_eval_detail_record(
            row_id=0,
            input_text="q",
            expected='{"a": 1}',
            predicted={"b": 2, "a": 1},
            metric_score=0.5,
            metric_feedback="ok",
            metric_name="m",
            model_name="mdl",
            split="s",
            max_length=None,
        )
        import json as _json

        parsed = _json.loads(rec["predicted"])
        assert parsed == {"a": 1, "b": 2}


# ---------------------------------------------------------------------------
# candidate_detail_key — the adapter<->tracker join key
# ---------------------------------------------------------------------------


class TestCandidateDetailKey:
    def test_same_text_same_key(self):
        assert candidate_detail_key("body A") == candidate_detail_key("body A")

    def test_different_text_different_key(self):
        assert candidate_detail_key("body A") != candidate_detail_key("body B")

    def test_none_safe(self):
        # A missing candidate text must not raise.
        assert candidate_detail_key("") == candidate_detail_key(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SnowflakeAdapter.evaluate — populates the per-candidate buffer
# ---------------------------------------------------------------------------


def _make_adapter(full_valset_size: int, buffer: dict | None = None):
    evaluator = MagicMock()
    evaluator.metric_name = "exact_match"
    adapter = SnowflakeAdapter(
        session=MagicMock(),
        evaluator=evaluator,
        function_name="db.s.fn",
        input_columns=["q"],
        model="mistral-large2",
        function_def=MagicMock(),
        temp_function_name="db.s.tmp",
        file_type_params=[],  # skip file_type_param_names(function_def.args)
        full_valset_size=full_valset_size,
        eval_detail_buffer=buffer,
    )
    return adapter, evaluator


class TestAdapterCapture:
    def _batch(self, n: int):
        return [{"inputs": {"q": f"q{i}"}, "answer": f"a{i}"} for i in range(n)]

    def test_full_valset_records_captured(self):
        adapter, evaluator = _make_adapter(full_valset_size=2)
        adapter._call_udf_batch = MagicMock(return_value=["p0", "p1"])
        evaluator.evaluate_batch = MagicMock(
            return_value=[
                ScoredExample(score=1.0, feedback="ok"),
                ScoredExample(score=0.0, feedback="bad"),
            ]
        )

        adapter.evaluate(self._batch(2), {"body": "PROMPT"})

        captured = adapter._eval_detail_buffer[candidate_detail_key("PROMPT")]
        assert captured.subsample is False
        assert [r["split"] for r in captured.records] == ["val_full", "val_full"]
        r0 = captured.records[0]
        assert r0["row_id"] == 0
        assert r0["input_text"] == "q: q0"
        assert r0["expected"] == "a0"
        assert r0["predicted"] == "p0"
        assert r0["metric_score"] == 1.0
        assert r0["metric_feedback"] == "ok"
        assert r0["metric_name"] == "exact_match"
        assert r0["model_name"] == "mistral-large2"

    def test_minibatch_flagged_subsample(self):
        # Batch smaller than the full valset (a rejection-gate minibatch).
        adapter, evaluator = _make_adapter(full_valset_size=10)
        adapter._call_udf_batch = MagicMock(return_value=["p0", "p1"])
        evaluator.evaluate_batch = MagicMock(
            return_value=[
                ScoredExample(score=1.0, feedback=""),
                ScoredExample(score=1.0, feedback=""),
            ]
        )

        adapter.evaluate(self._batch(2), {"body": "PROMPT"})

        captured = adapter._eval_detail_buffer[candidate_detail_key("PROMPT")]
        assert captured.subsample is True
        assert all(r["split"] == "val_subsample" for r in captured.records)

    def test_latest_eval_wins_per_candidate(self):
        # A candidate first minibatch-scored, then full-valset scored: the
        # full-valset capture must overwrite the earlier minibatch one.
        adapter, evaluator = _make_adapter(full_valset_size=2)
        adapter._call_udf_batch = MagicMock(return_value=["p0", "p1"])
        evaluator.evaluate_batch = MagicMock(
            return_value=[ScoredExample(1.0, ""), ScoredExample(1.0, "")]
        )
        # minibatch first (1 row), then full valset (2 rows)
        adapter._call_udf_batch = MagicMock(return_value=["p0"])
        evaluator.evaluate_batch = MagicMock(return_value=[ScoredExample(1.0, "")])
        adapter.evaluate(self._batch(1), {"body": "PROMPT"})
        assert (
            adapter._eval_detail_buffer[candidate_detail_key("PROMPT")].subsample
            is True
        )

        adapter._call_udf_batch = MagicMock(return_value=["p0", "p1"])
        evaluator.evaluate_batch = MagicMock(
            return_value=[ScoredExample(1.0, ""), ScoredExample(0.0, "")]
        )
        adapter.evaluate(self._batch(2), {"body": "PROMPT"})
        captured = adapter._eval_detail_buffer[candidate_detail_key("PROMPT")]
        assert captured.subsample is False
        assert len(captured.records) == 2

    def test_shared_buffer_used_when_provided(self):
        shared: dict = {}
        adapter, evaluator = _make_adapter(full_valset_size=1, buffer=shared)
        adapter._call_udf_batch = MagicMock(return_value=["p0"])
        evaluator.evaluate_batch = MagicMock(return_value=[ScoredExample(1.0, "")])

        adapter.evaluate(self._batch(1), {"body": "PROMPT"})
        # The externally-owned dict (shared with the tracker) is the one filled.
        assert candidate_detail_key("PROMPT") in shared
        assert adapter._eval_detail_buffer is shared


# ---------------------------------------------------------------------------
# ProgressiveExperimentTracker._upload_run_eval_detail — drains the buffer
# ---------------------------------------------------------------------------

import snowflake_ai_optimize.gepa.experiment as exp_mod  # noqa: E402
from snowflake_ai_optimize.core.experiment import GlobalRunCounter  # noqa: E402


def _make_tracker(buffer):
    return exp_mod.ProgressiveExperimentTracker(
        session=MagicMock(),
        experiment_name="db.s.exp",
        model="mistral-large2",
        function_name="db.s.fn",
        run_counter=GlobalRunCounter(),
        eval_detail_buffer=buffer,
    )


class TestTrackerUpload:
    def test_uploads_named_after_run(self):
        buffer = {
            candidate_detail_key("BODY"): _CapturedEval(
                records=[{"row_id": 0}], subsample=False
            )
        }
        tracker = _make_tracker(buffer)
        with (
            patch.object(exp_mod, "write_eval_detail_artifact") as mock_write,
            patch.object(exp_mod, "put_experiment_artifact") as mock_put,
        ):
            mock_write.return_value = "/tmp/eval_detail.json"
            tracker._upload_run_eval_detail("ITER_1", "BODY")

        # One eval_detail.json per run (default filename, no run-name prefix).
        mock_write.assert_called_once()
        assert "filename" not in mock_write.call_args.kwargs
        # Uploaded to that run's stage.
        assert mock_put.call_args.args[2] == "ITER_1"
        # Drained to bound memory.
        assert candidate_detail_key("BODY") not in buffer

    def test_no_upload_when_buffer_empty_for_candidate(self):
        tracker = _make_tracker({})
        with (
            patch.object(exp_mod, "write_eval_detail_artifact") as mock_write,
            patch.object(exp_mod, "put_experiment_artifact") as mock_put,
        ):
            tracker._upload_run_eval_detail("ITER_1", "MISSING")
        mock_write.assert_not_called()
        mock_put.assert_not_called()

    def test_no_source_is_noop(self):
        tracker = _make_tracker(None)
        with patch.object(exp_mod, "put_experiment_artifact") as mock_put:
            tracker._upload_run_eval_detail("ITER_1", "BODY")
        mock_put.assert_not_called()

    def test_upload_failure_does_not_propagate(self):
        buffer = {
            candidate_detail_key("BODY"): _CapturedEval(
                records=[{"row_id": 0}], subsample=False
            )
        }
        tracker = _make_tracker(buffer)
        with (
            patch.object(exp_mod, "write_eval_detail_artifact") as mock_write,
            patch.object(exp_mod, "put_experiment_artifact", side_effect=RuntimeError),
        ):
            mock_write.return_value = "/tmp/x.json"
            # Best-effort: must swallow the error.
            tracker._upload_run_eval_detail("ITER_1", "BODY")

    def test_accept_callback_uploads_iter_detail(self):
        # End-to-end wiring: firing the accept callbacks persists the run AND
        # drains the buffer entry for that candidate into eval_detail.json.
        buffer = {
            candidate_detail_key("improved"): _CapturedEval(
                records=[{"row_id": 0}], subsample=False
            )
        }
        tracker = _make_tracker(buffer)
        with (
            patch.object(exp_mod, "add_experiment_run"),
            patch.object(exp_mod, "write_eval_detail_artifact") as mock_write,
            patch.object(exp_mod, "put_experiment_artifact") as mock_put,
        ):
            mock_write.return_value = "/tmp/eval_detail.json"
            tracker.on_iteration_start({"iteration": 1})
            tracker.on_proposal_end(
                {"iteration": 1, "new_instructions": {"instruction": "improved"}}
            )
            tracker.on_candidate_accepted(
                {"iteration": 1, "new_candidate_idx": 1, "new_score": 1.7}
            )

        mock_write.assert_called_once()
        assert mock_put.call_args.args[2] == "ITER_1"


# ---------------------------------------------------------------------------
# upload_winning_artifacts — SEED detail on SEED run, BEST on winning run
# ---------------------------------------------------------------------------


class TestUploadWinningArtifacts:
    def test_seed_and_best_routed_to_their_runs(self):
        with (
            patch.object(exp_mod, "write_eval_detail_artifact") as mock_write,
            patch.object(exp_mod, "put_experiment_artifact") as mock_put,
        ):
            mock_write.side_effect = lambda details: "/tmp/eval_detail.json"
            exp_mod.upload_winning_artifacts(
                MagicMock(),
                "db.s.exp",
                "ITER_7",
                seed_eval_details=[{"row_id": 0}],
                best_eval_details=[{"row_id": 0}],
            )

        # Each run gets its own eval_detail.json (no prefix); SEED detail -> the
        # SEED run, BEST detail -> the winning ITER run.
        assert mock_write.call_count == 2
        target_runs = [c.args[2] for c in mock_put.call_args_list]
        assert target_runs == ["SEED", "ITER_7"]

    def test_missing_details_skipped(self):
        with (
            patch.object(exp_mod, "write_eval_detail_artifact") as mock_write,
            patch.object(exp_mod, "put_experiment_artifact") as mock_put,
        ):
            mock_write.side_effect = lambda details: "/tmp/eval_detail.json"
            exp_mod.upload_winning_artifacts(
                MagicMock(),
                "db.s.exp",
                "ITER_7",
                seed_eval_details=[{"row_id": 0}],
                best_eval_details=None,
            )
        assert mock_write.call_count == 1
        assert mock_put.call_args.args[2] == "SEED"

    def test_run_dir_uploaded_by_default(self, tmp_path):
        (tmp_path / "gepa_state.bin.gz").write_text("x")
        with (
            patch.object(exp_mod, "write_eval_detail_artifact"),
            patch.object(exp_mod, "put_experiment_artifact") as mock_put,
        ):
            exp_mod.upload_winning_artifacts(
                MagicMock(), "db.s.exp", "ITER_7", run_dir=str(tmp_path)
            )
        subdirs = [c.kwargs.get("subdir") for c in mock_put.call_args_list]
        assert "run_dir" in subdirs

    def test_run_dir_skipped_when_disabled(self, tmp_path):
        # The spec-driven (YAML) handler passes upload_run_dir=False.
        (tmp_path / "gepa_state.bin.gz").write_text("x")
        with (
            patch.object(exp_mod, "write_eval_detail_artifact"),
            patch.object(exp_mod, "put_experiment_artifact") as mock_put,
        ):
            exp_mod.upload_winning_artifacts(
                MagicMock(),
                "db.s.exp",
                "ITER_7",
                run_dir=str(tmp_path),
                upload_run_dir=False,
            )
        subdirs = [c.kwargs.get("subdir") for c in mock_put.call_args_list]
        assert "run_dir" not in subdirs


# ---------------------------------------------------------------------------
# save_evaluation_to_experiment — standalone/eval path artifact
# ---------------------------------------------------------------------------

import snowflake_ai_optimize.core.experiment as core_exp  # noqa: E402


class TestSaveEvaluationArtifact:
    def test_uploads_eval_detail_json(self):
        with (
            patch.object(core_exp, "create_experiment"),
            patch.object(core_exp, "add_experiment_run"),
            patch.object(core_exp, "commit_experiment_run"),
            patch.object(core_exp, "write_eval_detail_artifact") as mock_write,
            patch.object(core_exp, "put_experiment_artifact") as mock_put,
        ):
            mock_write.return_value = "/tmp/eval_detail.json"
            core_exp.save_evaluation_to_experiment(
                MagicMock(),
                "db.s.exp",
                function_name="db.s.fn",
                metric_name="exact_match",
                model_name="mistral-large2",
                score=0.9,
                num_examples=1,
                eval_details=[{"row_id": 0}],
                run_name="EVAL_3",
            )
        # Default filename (eval_detail.json) — the run's own stage, no prefix.
        mock_write.assert_called_once()
        assert "filename" not in mock_write.call_args.kwargs
        assert mock_put.call_args.args[2] == "EVAL_3"

    def test_create_experiment_if_missing_true_creates(self):
        # Default (standalone EVALUATE_AI_FUNCTION) path auto-creates.
        with (
            patch.object(core_exp, "create_experiment") as mock_create,
            patch.object(core_exp, "add_experiment_run"),
            patch.object(core_exp, "commit_experiment_run"),
            patch.object(core_exp, "write_eval_detail_artifact") as mock_write,
            patch.object(core_exp, "put_experiment_artifact"),
        ):
            mock_write.return_value = "/tmp/eval_detail.json"
            core_exp.save_evaluation_to_experiment(
                MagicMock(),
                "db.s.exp",
                function_name="db.s.fn",
                metric_name="exact_match",
                model_name="mistral-large2",
                score=0.9,
                num_examples=1,
                eval_details=[{"row_id": 0}],
                run_name="EVAL_1",
            )
        mock_create.assert_called_once()

    def test_create_experiment_if_missing_false_skips_creation(self):
        # Spec-driven / EXECUTE EXPERIMENT path never creates the experiment;
        # it only attaches the run to the already-existing experiment.
        with (
            patch.object(core_exp, "create_experiment") as mock_create,
            patch.object(core_exp, "add_experiment_run") as mock_add,
            patch.object(core_exp, "commit_experiment_run"),
            patch.object(core_exp, "write_eval_detail_artifact") as mock_write,
            patch.object(core_exp, "put_experiment_artifact"),
        ):
            mock_write.return_value = "/tmp/eval_detail.json"
            core_exp.save_evaluation_to_experiment(
                MagicMock(),
                "db.s.exp",
                function_name="db.s.fn",
                metric_name="exact_match",
                model_name="mistral-large2",
                score=0.9,
                num_examples=1,
                eval_details=[{"row_id": 0}],
                run_name="EVAL_1",
                create_experiment_if_missing=False,
            )
        mock_create.assert_not_called()
        # The run is still added to the (pre-existing) experiment.
        mock_add.assert_called_once()


# ---------------------------------------------------------------------------
# Body mode — the batched body adapter captures per-candidate detail too
# ---------------------------------------------------------------------------

import snowflake_ai_optimize.gepa.optimize_body as body_mod  # noqa: E402


class TestBodyAdapterCapture:
    def _ctx(self, full_valset_size: int):
        metric_evaluator = MagicMock()
        metric_evaluator.metric_name = "exact_match"
        return body_mod.BodyBatchEvalContext(
            session=MagicMock(),
            function_def=MagicMock(),
            temp_function_name="db.s.tmp",
            input_columns=["q"],
            metric_evaluator=metric_evaluator,
            pin_model="mistral-large2",
            full_valset_size=full_valset_size,
        )

    def _run(self, batch, raw_results, full_valset_size):
        adapter = object.__new__(body_mod._BatchedBodyOptimizeAnythingAdapter)
        adapter.refiner_config = None
        adapter._update_best_example_evals = MagicMock()
        adapter._sql_body_batched_raw_results = MagicMock(return_value=raw_results)
        ctx = self._ctx(full_valset_size)
        body_mod.oa_thread_local.body_batch_ctx = ctx
        try:
            adapter.evaluate(batch, {"body": "BODY"})
        finally:
            body_mod.oa_thread_local.body_batch_ctx = None
        return ctx

    def test_full_valset_capture(self):
        batch = [
            {"inputs": {"q": "q0"}, "answer": "a0"},
            {"inputs": {"q": "q1"}, "answer": "a1"},
        ]
        raw = [
            (1.0, None, {"Output": "p0", "Feedback": "ok"}),
            (0.0, None, {"Output": "p1", "Feedback": "bad"}),
        ]
        ctx = self._run(batch, raw, full_valset_size=2)
        captured = ctx.eval_detail_buffer[candidate_detail_key("BODY")]
        assert captured.subsample is False
        r0 = captured.records[0]
        assert r0["split"] == "val_full"
        assert r0["input_text"] == "q: q0"
        assert r0["expected"] == "a0"
        assert r0["predicted"] == "p0"
        assert r0["metric_score"] == 1.0
        assert r0["metric_feedback"] == "ok"
        assert r0["model_name"] == "mistral-large2"

    def test_minibatch_flagged_subsample(self):
        batch = [{"inputs": {"q": "q0"}, "answer": "a0"}]
        raw = [(1.0, None, {"Output": "p0", "Feedback": ""})]
        ctx = self._run(batch, raw, full_valset_size=10)
        captured = ctx.eval_detail_buffer[candidate_detail_key("BODY")]
        assert captured.subsample is True
        assert captured.records[0]["split"] == "val_subsample"

    def test_error_side_info_captured(self):
        batch = [{"inputs": {"q": "q0"}, "answer": "a0"}]
        raw = [(0.0, None, {"Error": "boom", "Feedback": "runtime error"})]
        ctx = self._run(batch, raw, full_valset_size=1)
        r0 = ctx.eval_detail_buffer[candidate_detail_key("BODY")].records[0]
        assert r0["error_message"] == "boom"
        assert r0["predicted"] == ""  # no Output on error
        assert r0["metric_feedback"] == "runtime error"
