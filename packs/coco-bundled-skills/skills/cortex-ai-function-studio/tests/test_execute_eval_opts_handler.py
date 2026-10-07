# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for the EXECUTE_AI_FUNCTION_EVAL_OPTS SPROC handler.

Covers SPEC parsing / validation (pure helpers), top-level dispatch
(evaluation vs optimization vs neither), and the spec -> engine mapping for
both paths, with ``evaluate``, ``save_evaluation_to_experiment`` and
``run_optimization`` mocked out.
"""

from __future__ import annotations

import sys
import threading
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import handlers.execute_eval_opts_handler as handler
from handlers.execute_eval_opts_handler import (
    _DATASET_VIEW_PREFIX,
    _builtin_function_name,
    _find_ai_function_calls,
    _first_metric,
    _materialize_dataset_version,
    _parse_specification,
    _resolve_arg_param_names,
    _resolve_dataset,
    _resolve_dataset_source,
    _resolve_function,
    _resolve_metric,
    _resolve_num_eval_runs,
    _validate_query_text_ai_complete,
    _validate_query_text_compiles,
    execute_ai_function_eval_opts,
)

EVAL_SPEC = """
function:
  function_name: "db.sch.answer(VARCHAR, VARCHAR)"
metrics:
  - name: exact_match
dataset:
  name: db.sch.qa
  column_mapping:
    argument_mapping:
      question: question_col
      context: context_col
    ground_truth: expected_col
evaluation:
  num_eval_runs: 1
"""

OPT_SPEC = """
function:
  function_name: "db.sch.answer(VARCHAR)"
metrics:
  - name: exact_match
dataset:
  name: db.sch.train
  column_mapping:
    argument_mapping:
      q: q_col
    ground_truth: gt
  holdout_data: db.sch.holdout
optimization:
  models: [mistral-7b]
  budget: ultra-light
  optimize_mode: body
"""

# --- Builtin AI function (query_text) specs ---
BUILTIN_EVAL_SPEC = """
function:
  query_text: "AI_COMPLETE('llama3.1-70b', 'Answer: ' || question_col)"
metrics:
  - name: exact_match
dataset:
  name: db.sch.qa
  column_mapping:
    ground_truth: expected_col
evaluation:
  num_eval_runs: 1
"""

BUILTIN_OPT_SPEC = """
function:
  query_text: "AI_COMPLETE('llama3.1-70b', 'Answer: ' || q_col)"
metrics:
  - name: exact_match
dataset:
  name: db.sch.train
  column_mapping:
    argument_mapping:
      q: q_col
    ground_truth: gt
  holdout_data: db.sch.holdout
optimization:
  models: [mistral-7b]
  budget: ultra-light
  optimize_mode: body
"""


class TestSpecHelpers:
    """Pure helpers raise plain ValueError (undecorated)."""

    def test_parse_specification_empty(self):
        with pytest.raises(ValueError, match="required and cannot be empty"):
            _parse_specification("")

    def test_parse_specification_non_mapping(self):
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            _parse_specification("- a\n- b")

    def test_first_metric_list_and_mapping(self):
        assert (
            _first_metric({"metrics": [{"name": "fuzzy_match"}]})["name"]
            == "fuzzy_match"
        )
        assert (
            _first_metric({"metrics": {"name": "exact_match"}})["name"] == "exact_match"
        )

    def test_first_metric_missing(self):
        with pytest.raises(ValueError, match="metrics is required"):
            _first_metric({})

    def test_resolve_function_user(self):
        # A user AI function is identified by function_name.
        assert _resolve_function(
            {"function": {"function_name": "db.sch.answer(VARCHAR)"}}
        ) == ("db.sch.answer(VARCHAR)", None)

    def test_resolve_function_builtin_from_query_text(self):
        # A builtin is inferred purely from the presence of query_text.
        fn, qt = _resolve_function(
            {"function": {"query_text": "AI_COMPLETE('m', 'ask ' || q)"}}
        )
        assert fn is None
        assert qt == "AI_COMPLETE('m', 'ask ' || q)"

    def test_resolve_function_builtin_is_permissive(self):
        # _resolve_function does NOT restrict query_text (eval accepts anything
        # that runs). The AI_COMPLETE-only rule is enforced only for optimization.
        for qt in (
            "AI_CLASSIFY(x, ['a','b'])",
            "AI_COMPLETE('m', a) || AI_COMPLETE('m', b)",
            "UPPER(AI_COMPLETE('m', a))",
        ):
            assert _resolve_function({"function": {"query_text": qt}}) == (None, qt)

    def test_validate_query_text_ai_complete_accepts_single(self):
        # A single AI_COMPLETE passes, including when wrapped in a non-AI call.
        _validate_query_text_ai_complete("AI_COMPLETE('m', 'ask ' || q)")
        _validate_query_text_ai_complete("UPPER(AI_COMPLETE('m', a))")

    def test_validate_query_text_ai_complete_rejects_other_builtin(self):
        with pytest.raises(ValueError, match="supports only"):
            _validate_query_text_ai_complete("AI_CLASSIFY(x, ['a','b'])")

    def test_validate_query_text_ai_complete_rejects_no_ai_function(self):
        with pytest.raises(ValueError, match="no AI function call"):
            _validate_query_text_ai_complete("UPPER(some_col)")

    def test_validate_query_text_ai_complete_rejects_multiple(self):
        with pytest.raises(ValueError, match="exactly one AI function"):
            _validate_query_text_ai_complete(
                "AI_COMPLETE('m', a) || AI_COMPLETE('m', b)"
            )

    def test_validate_query_text_ai_complete_rejects_two_different(self):
        with pytest.raises(ValueError, match="exactly one AI function"):
            _validate_query_text_ai_complete("AI_CLASSIFY(AI_COMPLETE('m', a), ['x'])")

    def test_resolve_function_rejects_both(self):
        with pytest.raises(ValueError, match="exactly one of function_name"):
            _resolve_function(
                {"function": {"function_name": "db.sch.f(VARCHAR)", "query_text": "x"}}
            )

    def test_resolve_function_rejects_neither(self):
        with pytest.raises(ValueError, match="requires function_name"):
            _resolve_function({"function": {}})

    def test_resolve_function_rejects_blank_query_text(self):
        # A whitespace-only query_text with no function_name is not a function.
        with pytest.raises(ValueError, match="requires function_name"):
            _resolve_function({"function": {"query_text": "   "}})

    def test_find_ai_function_calls(self):
        assert _find_ai_function_calls("AI_COMPLETE('m', a)") == ["AI_COMPLETE"]
        # Detects the AI function even when wrapped in a non-AI call.
        assert _find_ai_function_calls("UPPER(AI_COMPLETE('m', a))") == ["AI_COMPLETE"]
        assert _find_ai_function_calls("AI_COMPLETE(x) || AI_CLASSIFY(y, ['a'])") == [
            "AI_COMPLETE",
            "AI_CLASSIFY",
        ]
        assert _find_ai_function_calls("UPPER(col)") == []

    def test_find_ai_function_calls_cortex_by_namespace(self):
        # Any function under [SNOWFLAKE.]CORTEX.* is detected by namespace —
        # the name is not enumerated, so an arbitrary Cortex function matches.
        assert _find_ai_function_calls("SNOWFLAKE.CORTEX.COMPLETE('m', p)") == [
            "COMPLETE"
        ]
        assert _find_ai_function_calls("CORTEX.SUMMARIZE(x)") == ["SUMMARIZE"]
        assert _find_ai_function_calls("SNOWFLAKE.CORTEX.FOO_BAR(x)") == ["FOO_BAR"]
        # Bare plain-English names are NOT AI functions (no false match).
        assert _find_ai_function_calls("COMPLETE(x)") == []
        assert _find_ai_function_calls("SUMMARIZE(x)") == []
        assert _find_ai_function_calls("TRANSLATE(x, 'en', 'fr')") == []
        # A qualified AI_* call is still detected, and a mix is fully counted.
        assert _find_ai_function_calls("SNOWFLAKE.CORTEX.AI_COMPLETE(p)") == [
            "AI_COMPLETE"
        ]
        assert _find_ai_function_calls(
            "AI_COMPLETE(x) || SNOWFLAKE.CORTEX.SUMMARIZE(y)"
        ) == ["AI_COMPLETE", "SUMMARIZE"]

    def test_builtin_function_name_detects_ai_function(self):
        # Reports the AI function used, not the outermost SQL token.
        assert _builtin_function_name("AI_COMPLETE('m', 'x' || q)") == "AI_COMPLETE"
        assert _builtin_function_name("  ai_classify(t, ['a'])") == "AI_CLASSIFY"
        # Wrapped call: still AI_COMPLETE, not UPPER (addresses PR review).
        assert _builtin_function_name("UPPER(AI_COMPLETE('m', a))") == "AI_COMPLETE"

    def test_builtin_function_name_fallback(self):
        # No known AI function present -> generic label.
        assert _builtin_function_name("UPPER(some_col)") == "BUILTIN_AI_FUNCTION"

    def test_validate_query_text_compiles_ok(self):
        # Probe runs `SELECT (query_text) ... WHERE FALSE`; success is silent.
        class _OkSession:
            def __init__(self):
                self.queries = []

            def sql(self, q):
                self.queries.append(q)
                return SimpleNamespace(collect=lambda: [])

        session = _OkSession()
        _validate_query_text_compiles(session, "AI_COMPLETE('m', c)", "db.sch.t")
        probe = session.queries[-1]
        assert "WHERE FALSE" in probe
        assert "(AI_COMPLETE('m', c))" in probe and "db.sch.t" in probe

    def test_validate_query_text_compiles_wraps_error(self):
        # A compile failure surfaces as a clear, attributable ValueError naming
        # the dataset — distinguishable from a failure in our own CTE construction.
        class _BoomSession:
            def sql(self, q):
                raise RuntimeError("SQL compilation error: invalid identifier 'NOPE'")

        with pytest.raises(
            ValueError, match="query_text is not a valid expression over dataset"
        ):
            _validate_query_text_compiles(
                _BoomSession(), "AI_COMPLETE('m', nope)", "db.sch.t"
            )

    def test_resolve_dataset_requires_ground_truth(self):
        spec = {
            "dataset": {"name": "t", "column_mapping": {"argument_mapping": {"a": "c"}}}
        }
        with pytest.raises(ValueError, match="ground_truth is required"):
            _resolve_dataset(spec)

    def test_resolve_dataset_ok(self):
        spec = {
            "dataset": {
                "name": "db.sch.t",
                "column_mapping": {
                    "argument_mapping": {"a": "c1", "b": "c2"},
                    "ground_truth": "gt",
                },
            }
        }
        table, cols, label, arg_keys = _resolve_dataset(spec)
        assert (table, cols, label) == ("db.sch.t", ["c1", "c2"], "gt")
        assert arg_keys == ["a", "b"]

    def test_resolve_dataset_rejects_non_mapping(self):
        # A bare-string dataset is accepted by the GS structural schema but not yet
        # by the engine, so the sproc requires a mapping with column_mapping.
        with pytest.raises(ValueError, match="dataset is required"):
            _resolve_dataset({"dataset": "db.sch.t"})

    def test_resolve_dataset_requires_name(self):
        spec = {
            "dataset": {
                "column_mapping": {"argument_mapping": {"a": "c"}, "ground_truth": "gt"}
            }
        }
        with pytest.raises(ValueError, match=r"dataset\.name is required"):
            _resolve_dataset(spec)

    def test_resolve_dataset_requires_argument_mapping(self):
        spec = {
            "dataset": {"name": "db.sch.t", "column_mapping": {"ground_truth": "gt"}}
        }
        with pytest.raises(ValueError, match="argument_mapping is required"):
            _resolve_dataset(spec)

    def test_resolve_dataset_builtin_argument_mapping_optional(self):
        # For a builtin query_text the mapping is optional (the expression
        # references dataset columns directly); ground_truth is still required.
        spec = {
            "dataset": {"name": "db.sch.t", "column_mapping": {"ground_truth": "gt"}}
        }
        table, cols, label, arg_keys = _resolve_dataset(
            spec, require_argument_mapping=False
        )
        assert (table, cols, label, arg_keys) == ("db.sch.t", [], "gt", [])

    def test_resolve_dataset_builtin_still_requires_ground_truth(self):
        spec = {"dataset": {"name": "db.sch.t", "column_mapping": {}}}
        with pytest.raises(ValueError, match="ground_truth is required"):
            _resolve_dataset(spec, require_argument_mapping=False)

    def test_resolve_metric_normalizes_llm_judge(self):
        assert _resolve_metric({"name": "llm-judge"})[0] == "llm_judge"

    def test_resolve_metric_custom_requires_udf(self):
        with pytest.raises(ValueError, match="custom_udf is required"):
            _resolve_metric({"name": "custom"})

    def test_resolve_metric_builds_options(self):
        _, _, _model, opts = _resolve_metric({"name": "llm-judge"})
        assert opts == {"model_name": _model}

    def test_resolve_metric_threads_judge_model_into_options(self):
        _, _, model, opts = _resolve_metric(
            {"name": "llm-judge", "judge_model": "claude-opus-4-7"}
        )
        assert model == "claude-opus-4-7"
        assert opts == {"model_name": "claude-opus-4-7"}

    def test_resolve_metric_non_llm_judge_has_no_model_name(self):
        _, _, _model, opts = _resolve_metric({"name": "exact_match"})
        assert opts == {}

    def test_resolve_metric_rejects_unknown_name(self):
        with pytest.raises(ValueError, match="unsupported metric"):
            _resolve_metric({"name": "bogus"})

    def test_resolve_metric_accepts_valid_name(self):
        assert _resolve_metric({"name": "fuzzy_match"})[0] == "fuzzy_match"

    def test_resolve_metric_rejects_unknown_judge_model(self):
        # llm_judge judge model is validated against the shipped models.json.
        with pytest.raises(ValueError, match="unsupported model"):
            _resolve_metric({"name": "llm_judge", "judge_model": "bogus-model"})

    def test_resolve_metric_accepts_known_judge_model(self):
        _, _, judge, _opts = _resolve_metric(
            {"name": "llm_judge", "judge_model": "claude-opus-4-7"}
        )
        assert judge == "claude-opus-4-7"

    def test_resolve_metric_non_judge_metric_skips_model_check(self):
        # A non-llm_judge metric never validates a judge model (none applies).
        assert _resolve_metric({"name": "exact_match"})[0] == "exact_match"

    def test_resolve_num_eval_runs_defaults_to_one(self):
        # Missing evaluation section, or an evaluation section without the key.
        assert _resolve_num_eval_runs({}) == 1
        assert _resolve_num_eval_runs({"evaluation": {}}) == 1
        assert _resolve_num_eval_runs({"evaluation": {"num_eval_runs": None}}) == 1

    def test_resolve_num_eval_runs_reads_positive_int(self):
        assert _resolve_num_eval_runs({"evaluation": {"num_eval_runs": 1}}) == 1
        assert _resolve_num_eval_runs({"evaluation": {"num_eval_runs": 5}}) == 5

    @pytest.mark.parametrize("bad", [0, -1, -5])
    def test_resolve_num_eval_runs_rejects_non_positive(self, bad):
        with pytest.raises(ValueError, match="positive integer"):
            _resolve_num_eval_runs({"evaluation": {"num_eval_runs": bad}})

    @pytest.mark.parametrize("bad", [True, 1.5, "3", "abc", [3]])
    def test_resolve_num_eval_runs_rejects_non_int(self, bad):
        # bool is an int subclass and floats/strings are never coerced silently.
        with pytest.raises(ValueError, match="positive integer"):
            _resolve_num_eval_runs({"evaluation": {"num_eval_runs": bad}})


class _FakeDataFrame:
    """Snowpark-``DataFrame``-like stub recording ``create_or_replace_temp_view``.

    The materialized view name is recorded on the session when it exposes a
    ``temp_views`` list (a ``_DatasetSession``); against a bare mock session the
    recording is silently skipped.
    """

    def __init__(self, session):
        self._session = session

    def create_or_replace_temp_view(self, view_name):
        views = getattr(self._session, "temp_views", None)
        if isinstance(views, list):
            views.append(view_name)


class _FakeDataset:
    """``snowflake.ml.dataset.Dataset``-like stub exposing ``.read``."""

    def __init__(self, session):
        # ``ds.read`` is a property returning a reader with to_snowpark_dataframe.
        self.read = SimpleNamespace(
            to_snowpark_dataframe=lambda: _FakeDataFrame(session)
        )


def _install_fake_load_dataset(monkeypatch):
    """Patch ``snowflake.ml.dataset.load_dataset`` for the handler's lazy import.

    ``_materialize_dataset_version`` does ``from snowflake.ml.dataset import
    load_dataset`` at call time, so patching the attribute on that module is what
    the import binds to. The fake records every ``(name, version)`` load on the
    session it is handed (when that session exposes a ``loaded_datasets`` list)
    and returns a dataset whose ``.read.to_snowpark_dataframe()`` yields a
    DataFrame that registers its temp-view name — mirroring the real
    ``load_dataset(session, name, version).read.to_snowpark_dataframe()
    .create_or_replace_temp_view(...)`` chain.
    """
    import snowflake.ml.dataset as ml_dataset

    def _fake_load_dataset(sess, name, version):
        loaded = getattr(sess, "loaded_datasets", None)
        if isinstance(loaded, list):
            loaded.append((name, version))
        return _FakeDataset(sess)

    monkeypatch.setattr(ml_dataset, "load_dataset", _fake_load_dataset)


class _DatasetSession:
    """Fake Snowpark session that records DATASET reads + answers SPROC SQL.

    ``dataset.name`` is always a Snowflake DATASET now, so there is no
    SHOW DATASETS detection: the dataset *read* goes through
    ``snowflake.ml.dataset.load_dataset`` (patched via
    :func:`_install_fake_load_dataset`), whose loads land in
    ``self.loaded_datasets`` and whose materialized temp views land in
    ``self.temp_views``. ``session.sql(...)`` only needs to answer the SPROC
    error decorator's ``SHOW PARAMETERS`` probe; every statement is captured in
    ``self.statements`` for assertions. No ``SHOW VERSIONS`` is ever issued.
    """

    def __init__(self):
        self.statements: list[str] = []
        # (name, version) tuples passed to the patched load_dataset.
        self.loaded_datasets: list[tuple[str, str]] = []
        # view names registered via DataFrame.create_or_replace_temp_view.
        self.temp_views: list[str] = []
        # Read/restored by with_custom_ai_function_query_tag.
        self.query_tag = ""

    def sql(self, statement: str):
        self.statements.append(statement)
        if statement.strip().upper().startswith("SHOW PARAMETERS"):
            # The SPROC error-handling decorator reads a session parameter via
            # `SHOW PARAMETERS ...`.collect()[0]; return one fake row so the
            # decorator (exercised on the FAILED-run path) does not blow up.
            rows = [SimpleNamespace(asDict=lambda: {"value": "TRUE"})]
        else:
            rows = []
        return SimpleNamespace(collect=lambda: rows)


class TestDatasetObjectResolution:
    """Version-gated dataset resolution.

    ``dataset.name`` is a plain table/view (returned verbatim) unless a
    ``version`` is supplied, in which case it is a Snowflake DATASET read at that
    version and materialized to a temp view. The version is forwarded verbatim to
    ``snowflake.ml.dataset.load_dataset``; the handler never enumerates versions
    (no ``SHOW VERSIONS``).
    """

    def test_materialize_builds_temp_view_via_ml_api(self, monkeypatch):
        # Loads the version through snowflake.ml.dataset.load_dataset and
        # registers a temp view from the resulting Snowpark DataFrame.
        session = _DatasetSession()
        _install_fake_load_dataset(monkeypatch)
        view = _materialize_dataset_version(session, "DB.SCH.QA", "V1")
        # Returned name is a session temp-view label with the reserved prefix.
        assert view.startswith(_DATASET_VIEW_PREFIX)
        # load_dataset was called with (name, version); the DataFrame's
        # create_or_replace_temp_view registered exactly that view name.
        assert session.loaded_datasets == [("DB.SCH.QA", "V1")]
        assert session.temp_views == [view]
        # No version enumeration is issued.
        assert not any("SHOW VERSIONS" in s for s in session.statements)

    def test_resolve_source_no_version_passes_through_table(self, monkeypatch):
        # No version -> a plain table/view name, returned UNCHANGED; nothing is
        # loaded or materialized.
        session = _DatasetSession()
        _install_fake_load_dataset(monkeypatch)
        assert _resolve_dataset_source(session, "db.sch.qa", None) == "db.sch.qa"
        assert session.loaded_datasets == []
        assert session.temp_views == []

    def test_resolve_source_blank_version_passes_through_table(self, monkeypatch):
        # A blank/whitespace version is treated as unset -> table pass-through.
        session = _DatasetSession()
        _install_fake_load_dataset(monkeypatch)
        assert _resolve_dataset_source(session, "db.sch.qa", "   ") == "db.sch.qa"
        assert session.loaded_datasets == []

    def test_resolve_source_with_version_materializes(self, monkeypatch):
        # A version -> the name is read as a DATASET at that version, forwarded
        # verbatim to load_dataset, and the DataFrame registered as a temp view.
        session = _DatasetSession()
        _install_fake_load_dataset(monkeypatch)
        view = _resolve_dataset_source(session, "DB.SCH.QA", "V1")
        assert view.startswith(_DATASET_VIEW_PREFIX)
        assert session.loaded_datasets == [("DB.SCH.QA", "V1")]
        assert session.temp_views == [view]
        assert not any("SHOW VERSIONS" in s for s in session.statements)


class TestResolveArgParamNames:
    """Argument-key -> parameter-name resolution (named + positional $N)."""

    def _patch_describe(self, monkeypatch, arg_names):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=list(arg_names)),
        )

    def test_named_keys_resolve_to_ddl_casing(self, monkeypatch):
        self._patch_describe(monkeypatch, ["TEXT", "LABEL"])
        # Lowercase spec keys resolve to the function's declared (upper) casing
        # so the eval alias `col AS "TEXT"` matches the inlined body's `TEXT`.
        result = _resolve_arg_param_names(MagicMock(), "db.sch.f", ["text", "label"])
        assert result == ["TEXT", "LABEL"]

    def test_named_key_without_match_falls_back(self, monkeypatch):
        self._patch_describe(monkeypatch, ["a", "b"])
        # A named key with no matching parameter is returned unchanged.
        result = _resolve_arg_param_names(MagicMock(), "db.sch.f", ["arg1", "arg2"])
        assert result == ["arg1", "arg2"]

    def test_positional_resolves_via_describe_function(self, monkeypatch):
        self._patch_describe(monkeypatch, ["a", "b"])
        result = _resolve_arg_param_names(MagicMock(), "db.sch.multiply", ["$1", "$2"])
        assert result == ["a", "b"]

    def test_mixed_positional_and_named(self, monkeypatch):
        self._patch_describe(monkeypatch, ["a", "b"])
        result = _resolve_arg_param_names(MagicMock(), "db.sch.f", ["$1", "b"])
        assert result == ["a", "b"]


class TestDispatchAndMapping:
    """End-to-end dispatch + mapping with the engine + optimizer mocked."""

    @pytest.fixture(autouse=True)
    def _install_fake_snowflake_module(self):
        fake_module = types.ModuleType("_snowflake")

        class SnowflakeUserException(Exception):
            pass

        fake_module.SnowflakeUserException = SnowflakeUserException
        self.SnowflakeUserException = SnowflakeUserException
        sys.modules["_snowflake"] = fake_module
        yield
        sys.modules.pop("_snowflake", None)

    @pytest.fixture
    def mocks(self, monkeypatch):
        calls: dict = {}

        def fake_evaluate(
            session,
            function_name,
            test_table,
            input_columns,
            label_column,
            metric_name,
            **kwargs,
        ):
            calls["evaluate"] = {
                "function_name": function_name,
                "test_table": test_table,
                "input_columns": input_columns,
                "label_column": label_column,
                "metric_name": metric_name,
                **kwargs,
            }
            return SimpleNamespace(score=0.5, details=[{}, {}], cost_measurement=None)

        def fake_save(session, experiment_name, **kwargs):
            calls["save"] = {"experiment_name": experiment_name, **kwargs}

        def fake_run_optimization(
            session,
            function_name,
            training_table,
            label_column,
            input_columns,
            metric_name,
            models,
            reflection_model,
            **kwargs,
        ):
            calls["run_optimization"] = {
                "function_name": function_name,
                "training_table": training_table,
                "label_column": label_column,
                "input_columns": input_columns,
                "metric_name": metric_name,
                "models": models,
                "reflection_model": reflection_model,
                **kwargs,
            }
            return {"best_model": models[0], "seed_run": "seed"}

        monkeypatch.setattr(handler, "evaluate", fake_evaluate)
        monkeypatch.setattr(handler, "save_evaluation_to_experiment", fake_save)
        monkeypatch.setattr(handler, "run_optimization", fake_run_optimization)
        return calls

    def test_dispatch_evaluation(self, mocks, monkeypatch):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["QUESTION", "CONTEXT"]
            ),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp", "run_name": "r1"}, EVAL_SPEC
        )
        assert result["status"] == "SUCCEEDED"
        assert result["experiment"] == "db.sch.exp"
        # Run name is engine-assigned (EVAL_1), never the caller-supplied
        # ``run_name`` in evaluation_params — that key is ignored.
        assert result["run"] == "EVAL_1"
        assert result["metrics"] == {"exact_match": 0.5}
        assert "evaluate" in mocks and "run_optimization" not in mocks
        ev = mocks["evaluate"]
        assert ev["run_id"] == "EVAL_1"
        assert ev["function_name"] == "db.sch.answer(VARCHAR, VARCHAR)"
        # No dataset.version -> dataset.name is a plain table/view, used verbatim.
        assert ev["test_table"] == "db.sch.qa"
        assert ev["input_columns"] == ["question_col", "context_col"]
        assert ev["label_column"] == "expected_col"
        # Lowercase argument_mapping keys resolve to the function's declared
        # (upper-cased) parameter names so the eval alias matches the inlined body.
        assert ev["input_arg_names"] == ["QUESTION", "CONTEXT"]
        # Eval path persists the per-row eval_detail.json to the run's stage.
        assert mocks["save"]["upload_details"] is True
        # The handler path never creates the experiment (the DDL layer did).
        assert mocks["save"]["create_experiment_if_missing"] is False

    def test_dispatch_optimization(self, mocks, monkeypatch):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp", "run_name": "r1"}, OPT_SPEC
        )
        assert result["status"] == "SUCCEEDED"
        assert result["experiment"] == "db.sch.exp"
        assert result["best_model"] == "mistral-7b"  # from run_optimization result
        assert "run_optimization" in mocks and "evaluate" not in mocks
        opt = mocks["run_optimization"]
        assert opt["function_name"] == "db.sch.answer(VARCHAR)"
        # No dataset.version -> training source is a plain table/view, verbatim.
        assert opt["training_table"] == "db.sch.train"
        assert opt["input_columns"] == ["q_col"]
        assert opt["label_column"] == "gt"
        # Lowercase key `q` resolves to the function's declared param `Q`.
        assert opt["input_arg_names"] == ["Q"]
        assert opt["metric_name"] == "exact_match"
        assert opt["models"] == ["mistral-7b"]
        assert opt["reflection_model"] == "claude-opus-4-7"  # default reflection model
        # Spec-driven path relies on run_optimization's default (upload_run_dir
        # defaults to False), so it does not upload GEPA run_dir status files.
        assert "upload_run_dir" not in opt
        assert opt["auto_budget"] == "ultra-light"
        # optimize_mode is not forwarded (handler ships body-only, the default).
        assert "optimize_mode" not in opt
        # No holdout_version -> holdout_data is a plain table/view, verbatim.
        assert opt["test_table"] == "db.sch.holdout"  # from dataset.holdout_data
        assert opt["experiment_name"] == "db.sch.exp"
        # The handler path never creates the experiment (the DDL layer did).
        assert opt["create_experiment_if_missing"] is False
        # A persistently failing reflection call must fail the run (with the
        # error on it) instead of finishing SUCCEEDED with the error swallowed.
        assert opt["fail_on_reflection_error"] is True
        # run_id is not caller-supplied: the handler leaves it unset so
        # run_optimization auto-generates an internal label (the persisted run
        # names are the engine's SEED / ITER_<N>).
        assert "run_id" not in opt

    @pytest.mark.parametrize("budget", ["fast", "banana", "demo"])
    def test_dispatch_optimization_rejects_bad_budget(self, budget, mocks, monkeypatch):
        # "fast"/"banana" are not presets; "demo" is the legacy alias, no longer
        # accepted on the spec path (only "auto" or the canonical preset names are
        # valid). A pre-SEED opt validation error is surfaced on a FAILED SEED run
        # (not raised).
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        bad_spec = OPT_SPEC.replace("budget: ultra-light", f"budget: {budget}")
        result = execute_ai_function_eval_opts(
            MagicMock(),
            {"experiment_name": "db.sch.exp", "run_name": "r1"},
            bad_spec,
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "SEED"
        assert "unsupported optimization budget" in result["error_message"]
        assert "run_optimization" not in mocks

    @pytest.mark.parametrize("budget", ["ultra-light", "light", "medium", "heavy"])
    def test_dispatch_optimization_accepts_valid_budget(
        self, budget, mocks, monkeypatch
    ):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        spec = OPT_SPEC.replace("budget: ultra-light", f"budget: {budget}")
        result = execute_ai_function_eval_opts(
            MagicMock(),
            {"experiment_name": "db.sch.exp", "run_name": "r1"},
            spec,
        )
        assert result["status"] == "SUCCEEDED"
        assert mocks["run_optimization"]["auto_budget"] == budget

    def test_dispatch_optimization_rejects_unknown_model(self, mocks, monkeypatch):
        # An optimize model absent from models.json is rejected up front. The
        # pre-SEED validation error surfaces on a FAILED SEED run (not raised).
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        spec = OPT_SPEC.replace("models: [mistral-7b]", "models: [bogus-model]")
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "SEED"
        assert "unsupported model" in result["error_message"]
        assert "run_optimization" not in mocks

    def test_dispatch_optimization_rejects_unknown_reflection_model(
        self, mocks, monkeypatch
    ):
        # A spec-provided reflection_model absent from models.json is rejected;
        # the pre-SEED validation error surfaces on a FAILED SEED run.
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        spec = OPT_SPEC.replace(
            "  optimize_mode: body\n",
            "  optimize_mode: body\n  reflection_model: bogus-model\n",
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "SEED"
        assert "unsupported model" in result["error_message"]
        assert "run_optimization" not in mocks

    def test_dispatch_optimization_returned_failure_not_masked(
        self, mocks, monkeypatch
    ):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        monkeypatch.setattr(
            handler,
            "run_optimization",
            lambda *a, **k: {"status": "failed", "error": "All 2 models failed"},
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, OPT_SPEC
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "SEED"
        assert "All 2 models failed" in result["error_message"]

    def test_dispatch_builtin_evaluation(self, mocks, monkeypatch):
        # A builtin AI function is evaluated via query_text: no describe_function
        # (patched to fail to prove it is never called), no input_arg_names, and
        # argument_mapping may be omitted (query_text references columns directly).
        def _boom(*a, **k):
            raise AssertionError("describe_function must not be called for builtin")

        monkeypatch.setattr(handler, "describe_function", _boom)
        result = execute_ai_function_eval_opts(
            MagicMock(),
            {"experiment_name": "db.sch.exp", "run_name": "r1"},
            BUILTIN_EVAL_SPEC,
        )
        assert result["status"] == "SUCCEEDED"
        assert result["metrics"] == {"exact_match": 0.5}
        ev = mocks["evaluate"]
        query_text = "AI_COMPLETE('llama3.1-70b', 'Answer: ' || question_col)"
        assert ev["query_text"] == query_text
        # Shared protocol: function_name = the builtin's name (not the query_text).
        assert ev["function_name"] == "AI_COMPLETE"
        # No argument_mapping -> empty input columns; no DDL param resolution.
        assert ev["input_columns"] == []
        assert ev["input_arg_names"] is None
        # The run records function_name = builtin name, function_impl = query_text.
        assert mocks["save"]["function_name"] == "AI_COMPLETE"
        assert mocks["save"]["function_impl"] == query_text
        assert mocks["save"]["upload_details"] is True

    def test_dispatch_builtin_optimization(self, mocks, monkeypatch):
        # A builtin AI function is optimized via query_text threaded to the mode
        # handler; the optimizer receives function_name = the builtin's name
        # (bare, e.g. AI_COMPLETE) and no input_arg_names.
        def _boom(*a, **k):
            raise AssertionError("describe_function must not be called for builtin")

        monkeypatch.setattr(handler, "describe_function", _boom)
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, BUILTIN_OPT_SPEC
        )
        assert result["status"] == "SUCCEEDED"
        opt = mocks["run_optimization"]
        assert opt["query_text"] == "AI_COMPLETE('llama3.1-70b', 'Answer: ' || q_col)"
        assert opt["function_name"] == "AI_COMPLETE"
        assert opt["input_columns"] == ["q_col"]
        assert opt["input_arg_names"] is None
        assert opt["models"] == ["mistral-7b"]
        # No holdout_version -> holdout_data is a plain table/view, verbatim.
        assert opt["test_table"] == "db.sch.holdout"

    def test_dispatch_optimization_positional_mapping(self, mocks, monkeypatch):
        """Positional ($N) argument_mapping resolves to parameter names through the
        full handler dispatch (not just the resolver unit): $1/$2 -> the function's
        params, via DESCRIBE FUNCTION, then handed to the optimizer.
        """  # noqa: D205
        spec = (
            "function:\n"
            '  function_name: "db.sch.answer(VARCHAR, VARCHAR)"\n'
            "metrics:\n"
            "  - name: exact_match\n"
            "dataset:\n"
            "  name: db.sch.train\n"
            "  column_mapping:\n"
            "    argument_mapping:\n"
            "      $1: text_col\n"
            "      $2: lang_col\n"
            "    ground_truth: gt\n"
            "optimization:\n"
            "  models: [mistral-7b]\n"
            "  budget: ultra-light\n"
            "  optimize_mode: body\n"
        )
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["sentence", "language"]
            ),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        opt = mocks["run_optimization"]
        # Columns preserve the mapping's values (index-aligned to the keys)...
        assert opt["input_columns"] == ["text_col", "lang_col"]
        # ...and the positional $1/$2 keys resolved to the function's params.
        assert opt["input_arg_names"] == ["sentence", "language"]

    def test_dispatch_optimization_mixed_positional_and_named(self, mocks, monkeypatch):
        """A mix of a named key and a positional $N key resolves correctly through
        dispatch, index-aligned with the mapped columns.
        """  # noqa: D205
        spec = (
            "function:\n"
            '  function_name: "db.sch.answer(VARCHAR, VARCHAR)"\n'
            "metrics:\n"
            "  - name: exact_match\n"
            "dataset:\n"
            "  name: db.sch.train\n"
            "  column_mapping:\n"
            "    argument_mapping:\n"
            "      sentence: text_col\n"
            "      $2: lang_col\n"
            "    ground_truth: gt\n"
            "optimization:\n"
            "  models: [mistral-7b]\n"
            "  budget: ultra-light\n"
        )
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["sentence", "language"]
            ),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        opt = mocks["run_optimization"]
        assert opt["input_columns"] == ["text_col", "lang_col"]
        assert opt["input_arg_names"] == ["sentence", "language"]

    def test_dispatch_evaluation_dataset_version_materializes(self, mocks, monkeypatch):
        # dataset.version present -> dataset.name is read as a DATASET at that
        # version (materialized temp view); evaluation runs against the view and
        # the version is forwarded verbatim to load_dataset. (No version -> a
        # plain table, covered by test_dispatch_evaluation.)
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["QUESTION", "CONTEXT"]
            ),
        )
        _install_fake_load_dataset(monkeypatch)
        session = _DatasetSession()
        spec = EVAL_SPEC.replace(
            "  name: db.sch.qa\n", "  name: db.sch.qa\n  version: V1\n"
        )
        result = execute_ai_function_eval_opts(
            session, {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        assert result["metrics"] == {"exact_match": 0.5}
        ev = mocks["evaluate"]
        assert ev["test_table"].startswith(_DATASET_VIEW_PREFIX)
        assert ev["test_table"] != "db.sch.qa"
        assert session.loaded_datasets == [("db.sch.qa", "V1")]
        assert ev["test_table"] in session.temp_views

    def test_dispatch_optimization_dataset_and_holdout_materialized(
        self, mocks, monkeypatch
    ):
        # With dataset.version + holdout_version, optimization materializes BOTH
        # the training DATASET and the DATASET holdout to temp views;
        # run_optimization receives the view names, not the raw dataset names.
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        _install_fake_load_dataset(monkeypatch)
        session = _DatasetSession()
        spec = OPT_SPEC.replace(
            "  name: db.sch.train\n", "  name: db.sch.train\n  version: V1\n"
        ).replace(
            "  holdout_data: db.sch.holdout\n",
            "  holdout_data: db.sch.holdout\n  holdout_version: V1\n",
        )
        result = execute_ai_function_eval_opts(
            session, {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        opt = mocks["run_optimization"]
        assert opt["training_table"].startswith(_DATASET_VIEW_PREFIX)
        assert opt["training_table"] != "db.sch.train"
        assert opt["test_table"].startswith(_DATASET_VIEW_PREFIX)
        assert opt["test_table"] != "db.sch.holdout"
        # Training then holdout are each read at their pinned version (V1),
        # forwarded verbatim to load_dataset in that order.
        assert session.loaded_datasets == [
            ("db.sch.train", "V1"),
            ("db.sch.holdout", "V1"),
        ]
        assert opt["training_table"] in session.temp_views
        assert opt["test_table"] in session.temp_views

    def test_dispatch_neither_raises(self, mocks):
        # Neither marker section is a spec-shape error with no known path: it
        # surfaces on the generic first run (EVAL_1) as FAILED, not raised.
        spec = "function:\n  function_name: db.sch.f(VARCHAR)\nmetrics:\n  - name: exact_match\ndataset:\n  name: t\n  column_mapping:\n    argument_mapping: {a: c}\n    ground_truth: gt\n"
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "e"}, spec
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "EVAL_1"
        assert "evaluation" in result["error_message"]

    def test_missing_experiment_name_raises(self, mocks):
        with pytest.raises(
            self.SnowflakeUserException, match="experiment_name is required"
        ):
            execute_ai_function_eval_opts(MagicMock(), {}, EVAL_SPEC)

    def test_session_setup_failure_records_failed_run(self, mocks, monkeypatch):
        # A failure setting up the session param / query tag (SHOW PARAMETERS /
        # ALTER SESSION / QUERY_TAG) must be recorded as a FAILED run, not escape
        # as an unrecorded task failure — invisible under EXECUTE EXPERIMENT.
        from contextlib import contextmanager

        @contextmanager
        def _boom_setup(session, tag_suffix, **kwargs):
            raise RuntimeError("ALTER SESSION SET QUERY_TAG failed")
            yield session  # pragma: no cover

        monkeypatch.setattr(handler, "custom_ai_query_tag_logging", _boom_setup)
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, OPT_SPEC
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "EVAL_1"
        assert "QUERY_TAG failed" in result["error_message"]

    def test_session_teardown_failure_does_not_mask_success(self, mocks, monkeypatch):
        # If restoring the session param / query tag fails AFTER dispatch produced
        # a result, the completed job must not be flipped to FAILED.
        from contextlib import contextmanager

        @contextmanager
        def _boom_teardown(session, tag_suffix, **kwargs):
            yield session
            raise RuntimeError("QUERY_TAG restore failed")

        monkeypatch.setattr(handler, "custom_ai_query_tag_logging", _boom_teardown)
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, OPT_SPEC
        )
        assert result["status"] == "SUCCEEDED"

    def test_optimization_requires_models(self, mocks):
        # A pre-SEED opt validation error surfaces on a FAILED SEED run.
        spec = OPT_SPEC.replace("  models: [mistral-7b]\n", "")
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "e"}, spec
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "SEED"
        assert "must be a non-empty list" in result["error_message"]

    def test_optimization_rejects_non_body_mode(self, mocks):
        # The yaml handler ships only body-mode optimization; prompt is rejected.
        # The pre-SEED validation error surfaces on a FAILED SEED run.
        spec = OPT_SPEC.replace("  optimize_mode: body\n", "  optimize_mode: prompt\n")
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "e"}, spec
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "SEED"
        assert "only supports 'body'" in result["error_message"]

    def test_optimization_omitted_budget_resolves_to_light(self, mocks, monkeypatch):
        # An omitted budget means "auto". "auto" resolves to the concrete preset
        # _AUTO_BUDGET_RESOLVES_TO, which is "light" as of today (matching the SQL
        # SPROC's DEFAULT 'light'), not run_optimization's "ultra-light".
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        spec = OPT_SPEC.replace("  budget: ultra-light\n", "")
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        assert (
            mocks["run_optimization"]["auto_budget"]
            == handler._AUTO_BUDGET_RESOLVES_TO
            == "light"
        )

    def test_optimization_explicit_auto_budget_resolves_to_light(
        self, mocks, monkeypatch
    ):
        # "auto" may also be requested explicitly; it resolves the same way as an
        # omitted budget (to the concrete preset _AUTO_BUDGET_RESOLVES_TO).
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        spec = OPT_SPEC.replace("budget: ultra-light", "budget: auto")
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        assert (
            mocks["run_optimization"]["auto_budget"]
            == handler._AUTO_BUDGET_RESOLVES_TO
            == "light"
        )


class TestMultiEvalRuns:
    """``evaluation.num_eval_runs`` > 1 -> N parallel EVAL_1..EVAL_N runs."""

    @pytest.fixture(autouse=True)
    def _install_fake_snowflake_module(self):
        fake_module = types.ModuleType("_snowflake")

        class SnowflakeUserException(Exception):
            pass

        fake_module.SnowflakeUserException = SnowflakeUserException
        self.SnowflakeUserException = SnowflakeUserException
        sys.modules["_snowflake"] = fake_module
        yield
        sys.modules.pop("_snowflake", None)

    def _record_fakes(self, monkeypatch, *, evaluate_hook=None):
        """Install thread-safe recording fakes for evaluate + save.

        ``evaluate_hook(run_id)`` (if given) runs inside each fake ``evaluate``
        so tests can observe/synchronize concurrent execution.
        """
        lock = threading.Lock()
        calls: dict = {"evaluate": [], "save": []}

        def fake_evaluate(
            session,
            function_name,
            test_table,
            input_columns,
            label_column,
            metric_name,
            **kwargs,
        ):
            if evaluate_hook is not None:
                evaluate_hook(kwargs.get("run_id"))
            with lock:
                calls["evaluate"].append(
                    {
                        "function_name": function_name,
                        "metric_name": metric_name,
                        **kwargs,
                    }
                )
            return SimpleNamespace(score=0.5, details=[{}, {}], cost_measurement=None)

        def fake_save(session, experiment_name, **kwargs):
            with lock:
                calls["save"].append({"experiment_name": experiment_name, **kwargs})

        monkeypatch.setattr(handler, "evaluate", fake_evaluate)
        monkeypatch.setattr(handler, "save_evaluation_to_experiment", fake_save)
        # Argument-name resolution DESCRIBEs the function; return the EVAL_SPEC
        # function's params so resolution succeeds against a mock session.
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["QUESTION", "CONTEXT"]
            ),
        )
        return calls

    def _spec(self, num_eval_runs: int) -> str:
        return EVAL_SPEC.replace(
            "  num_eval_runs: 1", f"  num_eval_runs: {num_eval_runs}"
        )

    def test_creates_eval_1_to_n_runs(self, monkeypatch):
        calls = self._record_fakes(monkeypatch)
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(4)
        )

        assert result["status"] == "SUCCEEDED"
        assert result["experiment"] == "db.sch.exp"
        # Runs are reported deterministically as EVAL_1..EVAL_N.
        assert result["runs"] == ["EVAL_1", "EVAL_2", "EVAL_3", "EVAL_4"]
        # Multi-run uses the "runs" list, not the single-run "run" key.
        assert "run" not in result
        assert result["metrics"] == {
            "EVAL_1": {"exact_match": 0.5},
            "EVAL_2": {"exact_match": 0.5},
            "EVAL_3": {"exact_match": 0.5},
            "EVAL_4": {"exact_match": 0.5},
        }
        assert result["num_examples"] == 2

        # One evaluate + one save per run, each carrying its own EVAL_i run name.
        assert len(calls["evaluate"]) == 4
        assert len(calls["save"]) == 4
        assert {c["run_id"] for c in calls["evaluate"]} == {
            "EVAL_1",
            "EVAL_2",
            "EVAL_3",
            "EVAL_4",
        }
        assert {c["run_name"] for c in calls["save"]} == {
            "EVAL_1",
            "EVAL_2",
            "EVAL_3",
            "EVAL_4",
        }
        # Each eval run persists its own per-row eval_detail.json.
        assert all(c["upload_details"] is True for c in calls["save"])

    @pytest.mark.parametrize("num_runs, expected_workers", [(5, 3), (2, 2)])
    def test_parallelism_worker_count(self, monkeypatch, num_runs, expected_workers):
        # Capture max_workers while still driving the real ThreadPoolExecutor:
        # capped at 3, but never more than the number of runs requested.
        captured: dict = {}
        real_tpe = handler.ThreadPoolExecutor

        def spy_tpe(*args, **kwargs):
            captured["max_workers"] = kwargs.get(
                "max_workers", args[0] if args else None
            )
            return real_tpe(*args, **kwargs)

        monkeypatch.setattr(handler, "ThreadPoolExecutor", spy_tpe)
        self._record_fakes(monkeypatch)

        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(num_runs)
        )
        assert captured["max_workers"] == expected_workers
        assert result["runs"] == [f"EVAL_{i}" for i in range(1, num_runs + 1)]

    def test_runs_execute_concurrently(self, monkeypatch):
        # Barrier of 3 only releases once three workers are in-flight together,
        # deterministically proving >=3 concurrent runs (and, with the worker
        # cap, exactly 3). 6 runs = two clean groups of 3.
        barrier = threading.Barrier(3)
        lock = threading.Lock()
        state = {"current": 0, "peak": 0}

        def hook(_run_id):
            with lock:
                state["current"] += 1
                state["peak"] = max(state["peak"], state["current"])
            barrier.wait(timeout=10)
            with lock:
                state["current"] -= 1

        self._record_fakes(monkeypatch, evaluate_hook=hook)
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(6)
        )
        assert result["runs"] == [f"EVAL_{i}" for i in range(1, 7)]
        # Peak concurrency reaches the cap but never exceeds it.
        assert state["peak"] == 3

    def test_num_eval_runs_one_is_single_run(self, monkeypatch):
        # Default (1) keeps the single-run (flat) return shape, and the run is
        # named EVAL_1 — the caller-supplied ``run_name`` is ignored.
        calls = self._record_fakes(monkeypatch)
        result = execute_ai_function_eval_opts(
            MagicMock(),
            {"experiment_name": "db.sch.exp", "run_name": "r1"},
            self._spec(1),
        )
        assert result["run"] == "EVAL_1"
        assert "runs" not in result
        assert result["metrics"] == {"exact_match": 0.5}
        assert len(calls["evaluate"]) == 1
        assert calls["evaluate"][0]["run_id"] == "EVAL_1"

    @pytest.mark.parametrize("bad", [0, -1])
    def test_invalid_num_eval_runs_surface_error(self, monkeypatch, bad):
        # A pre-fan-out eval error (bad num_eval_runs) surfaces on a FAILED
        # EVAL_1 run and returns normally rather than raising.
        self._record_fakes(monkeypatch)
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(bad)
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "EVAL_1"
        assert "positive integer" in result["error_message"]


class _RecordingSession:
    """Records every ALTER/COMMIT EXPERIMENT statement; never fails.

    ``session.sql(...).collect()`` appends the SQL and returns ``[]`` so the
    fail-path helpers (ADD RUN / MODIFY RUN ADD PARAMETERS / COMMIT RUN) can be
    asserted against the recorded statements without a live Snowflake. The
    SPROC-lifecycle decorators read a session parameter and the QUERY_TAG up
    front; those reads are stubbed so only the handler body under test matters.
    """

    def __init__(self) -> None:
        self.statements: list[str] = []
        # Read/restored by with_custom_ai_function_query_tag.
        self.query_tag = ""

    def sql(self, sql: str):
        self.statements.append(sql)
        # The error-handling decorator does `SHOW PARAMETERS ...`.collect()[0];
        # return one fake row so the decorator sees a value and does not blow up.
        if sql.startswith("SHOW PARAMETERS"):
            row = SimpleNamespace(asDict=lambda: {"value": "TRUE"})
            return SimpleNamespace(collect=lambda: [row])
        return SimpleNamespace(collect=lambda: [])


class TestHandlerErrorPaths:
    """Unhandled errors surface on the job's natural run (FAILED + error param).

    Verifies the contract: the reason is recorded in the run's ``error_message``
    parameter, the run is committed ``FAILED``, the handler returns normally, and
    the experiment is NEVER created on a failure path.
    """

    @pytest.fixture(autouse=True)
    def _install_fake_snowflake_module(self):
        fake_module = types.ModuleType("_snowflake")

        class SnowflakeUserException(Exception):
            pass

        fake_module.SnowflakeUserException = SnowflakeUserException
        self.SnowflakeUserException = SnowflakeUserException
        sys.modules["_snowflake"] = fake_module
        yield
        sys.modules.pop("_snowflake", None)

    @pytest.fixture
    def no_create_spy(self, monkeypatch):
        """Fail loudly if create_experiment is called on any failure path.

        create_experiment lives in the experiment module and is imported by
        name into both the handler-called helpers and the experiment helpers;
        patch it at the source module so every reference is covered.
        """
        import snowflake_ai_optimize.core.experiment as experiment_mod

        def _boom(*a, **k):
            raise AssertionError("create_experiment must not be called on failure")

        monkeypatch.setattr(experiment_mod, "create_experiment", _boom)

    def _params_added(self, session: _RecordingSession) -> str:
        """Return the concatenated MODIFY RUN ADD PARAMETERS statements."""
        return "\n".join(s for s in session.statements if "ADD PARAMETERS" in s)

    def _commits(self, session: _RecordingSession) -> list[str]:
        return [s for s in session.statements if "COMMIT RUN" in s]

    def test_eval_pre_fan_out_error_fails_eval_1(self, monkeypatch, no_create_spy):
        # An error resolving the function (before the single-run execution)
        # surfaces on a created+failed EVAL_1 with an error_message parameter.
        def _boom_evaluate(*a, **k):
            raise RuntimeError("evaluate blew up: bad column NOPE")

        monkeypatch.setattr(handler, "evaluate", _boom_evaluate)
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["QUESTION", "CONTEXT"]
            ),
        )
        session = _RecordingSession()
        result = execute_ai_function_eval_opts(
            session, {"experiment_name": "db.sch.exp"}, EVAL_SPEC
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "EVAL_1"
        assert "evaluate blew up" in result["error_message"]
        # EVAL_1 was created, its error recorded, and committed FAILED.
        assert any("ADD RUN EVAL_1" in s for s in session.statements)
        assert "error_message" in self._params_added(session)
        assert any(
            "COMMIT RUN EVAL_1 WITH STATUS='FAILED'" in s for s in session.statements
        )
        # No experiment creation ever issued.
        assert not any("CREATE EXPERIMENT" in s for s in session.statements)

    def test_eval_multi_run_one_slot_fails(self, monkeypatch, no_create_spy):
        # One of N eval slots fails: that EVAL_i is committed FAILED, the others
        # succeed, and the aggregate status is FAILED (never raises).
        lock = threading.Lock()
        saved: list[str] = []

        def fake_evaluate(
            session,
            function_name,
            test_table,
            input_columns,
            label_column,
            metric_name,
            **kwargs,
        ):
            if kwargs.get("run_id") == "EVAL_2":
                raise RuntimeError("slot 2 boom")
            return SimpleNamespace(score=0.5, details=[{}, {}], cost_measurement=None)

        def fake_save(session, experiment_name, **kwargs):
            with lock:
                saved.append(kwargs["run_name"])

        monkeypatch.setattr(handler, "evaluate", fake_evaluate)
        monkeypatch.setattr(handler, "save_evaluation_to_experiment", fake_save)
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["QUESTION", "CONTEXT"]
            ),
        )
        session = _RecordingSession()
        spec = EVAL_SPEC.replace("  num_eval_runs: 1", "  num_eval_runs: 3")
        result = execute_ai_function_eval_opts(
            session, {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "FAILED"
        assert result["runs"] == ["EVAL_1", "EVAL_2", "EVAL_3"]
        # The two passing slots recorded a score; the failing slot did not.
        assert result["metrics"]["EVAL_1"] == {"exact_match": 0.5}
        assert result["metrics"]["EVAL_3"] == {"exact_match": 0.5}
        assert result["metrics"]["EVAL_2"]["status"] == "FAILED"
        assert "slot 2 boom" in result["metrics"]["EVAL_2"]["error_message"]
        # Only the two passing slots were saved (EVAL_2 failed before save).
        assert set(saved) == {"EVAL_1", "EVAL_3"}
        # EVAL_2 committed FAILED; no experiment creation.
        assert any(
            "COMMIT RUN EVAL_2 WITH STATUS='FAILED'" in s for s in session.statements
        )
        assert not any("CREATE EXPERIMENT" in s for s in session.statements)

    def test_opt_pre_seed_error_fails_seed(self, monkeypatch, no_create_spy):
        # A pre-SEED opt error (unknown model) surfaces on a created+failed SEED
        # run — no run existed yet, so SEED is created.
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        session = _RecordingSession()
        spec = OPT_SPEC.replace("models: [mistral-7b]", "models: [bogus-model]")
        result = execute_ai_function_eval_opts(
            session, {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "SEED"
        assert "unsupported model" in result["error_message"]
        assert any("ADD RUN SEED" in s for s in session.statements)
        assert "error_message" in self._params_added(session)
        assert any(
            "COMMIT RUN SEED WITH STATUS='FAILED'" in s for s in session.statements
        )
        assert not any("CREATE EXPERIMENT" in s for s in session.statements)

    def test_spec_parse_error_fails_eval_1(self, monkeypatch, no_create_spy):
        # A YAML parse error has no known path → default to EVAL_1 (FAILED).
        session = _RecordingSession()
        result = execute_ai_function_eval_opts(
            session, {"experiment_name": "db.sch.exp"}, "not: [valid: yaml"
        )
        assert result["status"] == "FAILED"
        assert result["run"] == "EVAL_1"
        assert result["error_message"]
        assert any("ADD RUN EVAL_1" in s for s in session.statements)
        assert any(
            "COMMIT RUN EVAL_1 WITH STATUS='FAILED'" in s for s in session.statements
        )
        assert not any("CREATE EXPERIMENT" in s for s in session.statements)
