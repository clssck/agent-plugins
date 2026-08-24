# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.
"""Generic Snowflake Experiment infrastructure.

This module provides the reusable building blocks for persisting AI-function
optimization results to Snowflake Experiment objects:

  * Experiment DDL helpers (create, add run, commit, put artifact)
  * Run naming conventions
  * Parameter / metric builders
  * Pareto frontier computation and hypervolume subset selection

Mode-specific orchestration (GEPA iteration tracking, rejected-candidate
capture, progressive persistence) lives in ``snow_gepa_experiment``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import threading
import time
from functools import lru_cache
from typing import Any, NamedTuple

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.errors import ErrorType
from snowflake_ai_optimize.core.run_params import RunParams
from snowflake_ai_optimize.core.sql_utils import (
    escape_sql_string,
    validate_dotted_identifier,
)
from snowflake_ai_optimize.core.timing import get_active_tracker
from snowflake_ai_optimize.core.types import CostMeasurement

# ``models.json`` is shipped alongside this module.  For the inline
# SPROC it's picked up via importlib.resources; for stage-based SPROCs
# it's uploaded to the stage and resolved via ``__file__`` sibling
# lookup or the Snowflake import directory.
_MODELS_JSON_NAME = "models.json"

logger = logging.getLogger(__name__)


class ParetoCandidateInfo(NamedTuple):
    """Per-run data needed to compute cross-model Pareto frontiers.

    Returned by ``save_optimization_to_experiment`` and collected across
    model workers.  The benchmark report computes the cross-model frontier
    client-side from the tracking table data.
    """

    run_name: str
    model: str
    estimated_cost: float | None
    score: float
    prompt_text: str = ""


class FrontierCandidate(NamedTuple):
    """Lightweight carrier for a candidate's cost/score and provenance.

    Used by ``select_frontier_candidates`` to collect candidates across
    models before computing the cross-model Pareto frontier.

    ``score`` is the validation score (the quality axis used for hypervolume
    selection).  ``test_score`` is attached after the post-frontier test-eval.
    Both scores are stamped back onto the candidate's source SEED/ITER run
    (identified by ``run_name``) via :func:`stamp_frontier_metrics_on_runs`,
    which also flags that run ``is_frontier`` — there is no separate
    frontier-candidate run kind.
    """

    model: str
    candidate_idx: int
    estimated_cost: float
    score: float
    prompt_text: str = ""
    run_name: str = ""
    test_score: float | None = None


@lru_cache(maxsize=1)
def _load_model_rates() -> dict[str, dict[str, float]]:
    """Load per-million-token rates from ``src/models.json``.

    Format: ``{"<model>": {"input_cost": <float>, "output_cost": <float>}}``.

    Resolution order:
    0. ``_INLINE_MODEL_RATES`` global — set by the inline SPROC bundler
       (sproc_render.py) which embeds models.json as a Python dict literal.
    1. ``importlib.resources`` — works inside the inline-SPROC bundle
       where source files are zipped onto the stage.
    2. ``__file__`` sibling — local development and stage-based SPROCs
       where ``models.json`` is imported alongside the ``.py`` files.
    3. Snowflake import directory (``sys._xoptions``) — fallback for
       stage-based SPROCs when ``__file__`` doesn't resolve.

    Raises RuntimeError if no source produces model rates.
    """
    # Check for inline-embedded constant (set by sproc_render._build_inline_body).
    # In the inline SPROC, _INLINE_MODEL_RATES is defined at module scope in the
    # concatenated Python body — visible via globals() from any function in that module.
    try:
        inline_rates = globals().get("_INLINE_MODEL_RATES")
        if inline_rates is not None:
            result: dict[str, dict[str, float]] = inline_rates
            return result
    except Exception:
        pass

    try:
        from importlib.resources import files

        traversable = (
            files(__package__).joinpath("models.json") if __package__ else None
        )
        if traversable is not None and traversable.is_file():
            result = json.loads(traversable.read_text(encoding="utf-8"))
            return result
    except Exception as e:
        logger.debug("load_model_rates: importlib.resources path failed: %s", e)
    # Filesystem fallback (local dev + stage-based SPROC).
    try:
        path = os.path.join(os.path.dirname(__file__), "models.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                result = json.load(f)
            return result
    except Exception as e:
        logger.debug("load_model_rates: __file__ sibling path failed: %s", e)
    # Snowflake import directory fallback (stage-based SPROCs).
    try:
        import sys

        import_dir = sys._xoptions.get("snowflake_import_directory", "")
        if import_dir:
            path = os.path.join(import_dir, "models.json")
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    result = json.load(f)
                return result
    except Exception as e:
        logger.debug("load_model_rates: Snowflake import directory failed: %s", e)
    raise RuntimeError(
        "Failed to load model rates from any source. "
        "models.json is required for Pareto cost estimation."
    )


def create_experiment(session: Session, experiment_name: str) -> None:
    """Create a Snowflake Experiment if it does not already exist."""
    validate_dotted_identifier(experiment_name, kind="experiment_name")
    timed_experiment_sql(
        session,
        f"CREATE EXPERIMENT IF NOT EXISTS {experiment_name} "
        f"TYPE='ai_function_optimization'",
    )


def get_experiment_run_names(session: Session, experiment_name: str) -> set[str]:
    """Return the set of run names present in an experiment.

    Uses ``SHOW RUNS IN EXPERIMENT`` which lists all runs regardless of
    status (RUNNING, FINISHED, etc.).  Returns an empty set if the
    experiment does not exist or the query fails.
    """
    validate_dotted_identifier(experiment_name, kind="experiment_name")
    try:
        rows = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
        return {r["name"] for r in rows}
    except Exception:
        return set()


def add_experiment_run(
    session: Session,
    experiment_name: str,
    run_name: str,
    params: RunParams | None = None,
    metrics: list[dict[str, float]] | None = None,
) -> None:
    """Add a run to an experiment, then attach parameters and metrics.

    Each statement is timed separately so the tracker count reflects the
    real number of round-trips (1 ADD RUN + up to 2 MODIFY RUN), not
    just the number of high-level helper calls.

    Args:
        session: Active Snowpark session.
        experiment_name: Fully qualified experiment identifier.
        run_name: Name for the new run.
        params: Optional RunParams instance to attach to the run.
        metrics: Optional list of metric dicts to attach to the run.

    """
    validate_dotted_identifier(experiment_name, kind="experiment_name")
    validate_dotted_identifier(run_name, kind="run_name")
    timed_experiment_sql(
        session, f"ALTER EXPERIMENT {experiment_name} ADD RUN {run_name}"
    )

    if params:
        params_json = escape_sql_string(json.dumps(params.to_param_list()))
        timed_experiment_sql(
            session,
            f"ALTER EXPERIMENT {experiment_name} MODIFY RUN {run_name} "
            f"ADD PARAMETERS = '{params_json}'",
        )

    if metrics:
        metrics_json = json.dumps(metrics)
        timed_experiment_sql(
            session,
            f"ALTER EXPERIMENT {experiment_name} MODIFY RUN {run_name} "
            f"ADD METRICS = '{metrics_json}'",
        )


# Terminal statuses accepted by ``COMMIT RUN ... WITH STATUS=``.  Allowlisted
# so the value can be interpolated into SQL without injection risk.
_COMMIT_RUN_STATUSES = {"FINISHED", "FAILED"}


def commit_experiment_run(
    session: Session,
    experiment_name: str,
    run_name: str,
    *,
    status: str | None = None,
) -> None:
    """Commit a run, transitioning its status to a terminal state.

    With no ``status`` the run transitions to ``FINISHED`` (the default
    ``COMMIT RUN`` behaviour).  Pass ``status='FAILED'`` to commit a run that
    represents a failed model optimization: in the global run structure a
    failed model has no separate ``<MODEL>_FAILED`` run — instead the runs it
    actually wrote (its ``SEED``/``ITER_<N>`` runs) are committed with
    ``STATUS='FAILED'`` so the failure is carried on the real runs.
    """
    validate_dotted_identifier(experiment_name, kind="experiment_name")
    validate_dotted_identifier(run_name, kind="run_name")
    sql = f"ALTER EXPERIMENT {experiment_name} COMMIT RUN {run_name}"
    if status is not None:
        status_up = status.strip().upper()
        if status_up not in _COMMIT_RUN_STATUSES:
            raise ValueError(
                f"Unsupported COMMIT RUN status {status!r}; expected one of "
                f"{sorted(_COMMIT_RUN_STATUSES)}"
            )
        sql += f" WITH STATUS='{status_up}'"
    timed_experiment_sql(session, sql)


def put_experiment_artifact(
    session: Session,
    experiment_name: str,
    run_name: str,
    local_path: str,
    subdir: str = "",
) -> None:
    """Upload a local file or directory to an experiment run's stage.

    Uses ``session.file.put`` (Snowpark file transfer API) which works
    both client-side and inside stored procedures, unlike ``PUT`` SQL
    which is unsupported in SPROCs.  Each individual PUT is timed via
    ``_timed_artifact_put`` so the tracker captures upload wall time
    separately from the rest of the experiment bookkeeping.
    """
    validate_dotted_identifier(experiment_name, kind="experiment_name")
    validate_dotted_identifier(run_name, kind="run_name")
    suffix = f"/{subdir}" if subdir else ""
    stage_path = f"snow://experiment/{experiment_name}/versions/{run_name}{suffix}"

    if os.path.isdir(local_path):
        for filename in os.listdir(local_path):
            filepath = os.path.join(local_path, filename)
            if os.path.isfile(filepath):
                _timed_artifact_put(session, filepath, stage_path)
    else:
        _timed_artifact_put(session, local_path, stage_path)


# ---------------------------------------------------------------------------
# Run naming helpers
# ---------------------------------------------------------------------------


def make_run_name(model: str, iteration: int, *, is_seed: bool = False) -> str:
    """Build a deterministic experiment run name.

    Convention:
        <MODEL>_SEED         -- seed candidate (iteration 0)
        <MODEL>_ITER_<N>     -- Nth iteration for a given model

    Run names are model-scoped so parallel per-model optimization does not
    create naming conflicts.
    """
    model_suffix = re.sub(r"[^A-Za-z0-9]", "_", model).upper()
    if is_seed:
        return f"{model_suffix}_SEED"
    return f"{model_suffix}_ITER_{iteration}"


def make_failed_run_name(model: str) -> str:
    """Build the run name for a failed model optimization."""
    model_suffix = re.sub(r"[^A-Za-z0-9]", "_", model).upper()
    return f"{model_suffix}_FAILED"


class GlobalRunCounter:
    """Thread-safe 1-based monotonic counter for global ``ITER_<N>`` run names.

    Shared by all model workers so iteration runs form one sequence regardless
    of which model produced them.  ``start`` resumes past runs already in the
    experiment (see :func:`seed_run_counter_from_experiment` — retry safety).
    """

    def __init__(self, start: int = 0) -> None:
        self._lock = threading.Lock()
        self._value = start

    def next_iter(self) -> int:
        """Atomically increment and return the next iteration number (1-based)."""
        with self._lock:
            self._value += 1
            return self._value


def seed_run_counter_from_experiment(
    session: Session, experiment_name: str
) -> GlobalRunCounter:
    """Return a ``GlobalRunCounter`` resuming past the highest existing ``ITER_<N>``.

    ``ALTER EXPERIMENT ... ADD RUN`` has no ``IF NOT EXISTS``, so a retry on the
    same ``experiment_name`` that restarted the counter at 1 would collide on
    ``ITER_1`` and crash mid-run.  Seeding from the runs already present makes a
    retry resume cleanly.  Best-effort: any read failure yields a fresh counter.
    """
    validate_dotted_identifier(experiment_name, kind="experiment_name")
    max_n = 0
    try:
        rows = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
    except Exception:
        return GlobalRunCounter()
    for row in rows:
        name = str(row["name"])
        if name.startswith("ITER_"):
            with contextlib.suppress(ValueError):
                max_n = max(max_n, int(name[len("ITER_") :]))
    return GlobalRunCounter(start=max_n)


# The single seed-candidate run name (schema v4): the eval of the input
# function, shared across all optimization models.
SEED_RUN_NAME = "SEED"


def make_iter_run_name(iteration: int) -> str:
    """Build a global (model-agnostic) ``ITER_<N>`` run name (schema v4).

    ``N`` is drawn from a shared :class:`GlobalRunCounter` so iteration runs
    across ALL models form one sequence.  The producing model is stored as the
    ``model`` run param, never in the name; the seed run is :data:`SEED_RUN_NAME`.
    Candidate role ("iteration"/"rejected") and Pareto membership are run
    *metadata*, not names.  Contrast :func:`make_run_name` (evolve, per-model).
    """
    return f"ITER_{iteration}"


def build_run_metrics(
    *,
    valset_score: float | None = None,
    test_score: float | None = None,
    estimated_cost: float | None = None,
    base_cost: float | None = None,
    is_frontier: bool | None = None,
) -> list[dict[str, Any]] | None:
    """Build the metrics list for an experiment run.

    ``is_frontier`` marks membership in the CROSS-model hypervolume frontier
    — the selected set that is test-evaluated and that the presentation
    layer reads.

    ``base_cost`` is the base (SEED) candidate's estimated cost. When both it
    and ``estimated_cost`` are present and ``base_cost`` is non-zero, a
    ``cost_compared_to_base`` metric is emitted: this run's cost as a multiple
    of the base seed's cost (SEED itself = 1.0; a run half as expensive = 0.5).

    Returns ``None`` if there are no metrics to set.
    """
    metrics: list[dict[str, Any]] = []
    if valset_score is not None:
        metrics.append({"name": "valset_score", "value": valset_score})
    if test_score is not None:
        metrics.append({"name": "test_score", "value": test_score})
    if estimated_cost is not None:
        metrics.append({"name": "estimated_cost", "value": round(estimated_cost, 6)})
        if base_cost:  # not None and non-zero
            metrics.append(
                {
                    "name": "cost_compared_to_base",
                    "value": round(estimated_cost / base_cost, 6),
                }
            )
    if is_frontier is not None:
        metrics.append(
            {
                "name": "is_frontier",
                "value": 1 if is_frontier else 0,
            }
        )
    return metrics or None


def stamp_frontier_metrics_on_runs(
    session: Session,
    experiment_name: str,
    *,
    frontier_selection: list[FrontierCandidate],
) -> None:
    """Stamp cross-model frontier metrics onto the source SEED/ITER runs.

    Each selected candidate carries the name of the SEED/ITER run it was
    derived from (``FrontierCandidate.run_name``).  Rather than writing a
    separate self-contained run per candidate, we ADD METRICS directly onto
    that lineage run: an ``is_frontier`` flag (always ``1``) plus the
    post-selection ``test_score`` when the candidate was test-evaluated.

    Called after :func:`select_frontier_candidates` (and the frontier
    test-eval), BEFORE the SEED/ITER runs are committed — Snowflake rejects
    ``ADD METRICS`` on a committed run, so the caller must defer the commit
    of these runs until after this stamp (see ``defer_commit`` in
    ``save_optimization_to_experiment``).

    ``valset_score`` and ``estimated_cost`` already live on the SEED/ITER run
    (written at creation / backfill), so they are not re-written here.
    """
    for fc in frontier_selection:
        if not fc.run_name:
            logger.warning(
                "Frontier candidate for model %s (idx %s) has no source "
                "run_name; cannot stamp frontier metrics.",
                fc.model,
                fc.candidate_idx,
            )
            continue
        metrics = build_run_metrics(test_score=fc.test_score, is_frontier=True)
        if not metrics:
            continue
        metrics_json = json.dumps(metrics)
        if "'" in metrics_json:
            # Metric values are numeric by design (scores, 0/1 flags), so the
            # JSON never contains a single quote.  A quote here means a string
            # value slipped in and would break the single-quoted SQL literal
            # below — fail loudly rather than emit malformed SQL.
            raise ValueError(
                f"Refusing to stamp frontier metrics containing a single "
                f"quote onto run {fc.run_name}: {metrics_json}"
            )
        timed_experiment_sql(
            session,
            f"ALTER EXPERIMENT {experiment_name} MODIFY RUN {fc.run_name} "
            f"ADD METRICS = '{metrics_json}'",
        )


def commit_runs(
    session: Session,
    experiment_name: str,
    run_names: list[str],
    *,
    status: str | None = None,
) -> None:
    """Commit a batch of runs, transitioning each to a terminal state.

    Used to finalise SEED/ITER runs whose commit was deferred so the
    cross-model frontier test-eval could stamp ``test_score`` /
    ``is_frontier`` onto them first.  Each commit is best-effort: a failure
    on one run is logged and the rest still commit (mirrors the
    fault-tolerance of the per-run persistence path).

    Pass ``status='FAILED'`` to commit a failed model's own runs as FAILED
    (the global-structure replacement for a separate ``<MODEL>_FAILED`` run).
    """
    for run_name in dict.fromkeys(run_names):
        try:
            commit_experiment_run(session, experiment_name, run_name, status=status)
        except Exception as exc:
            logger.warning(
                "Failed to commit deferred run %s in %s: %s",
                run_name,
                experiment_name,
                exc,
            )


# ---------------------------------------------------------------------------
# Eval-detail artifact
# ---------------------------------------------------------------------------


def write_eval_detail_artifact(
    details: list[dict[str, Any]],
    dest_dir: str | None = None,
    filename: str = "eval_detail.json",
) -> str:
    """Serialize per-row evaluation detail to a JSON file.

    Each element in *details* should contain keys like ``row_idx``,
    ``input_text``, ``expected``, ``predicted``, ``metric_score``,
    ``metric_feedback``, ``split``.

    Args:
        details: Per-row evaluation records.
        dest_dir: Output directory; a temp dir is created when omitted.
        filename: Output filename. Override to attach multiple artifacts
            (e.g., ``seed_eval_detail.json`` and ``best_eval_detail.json``)
            to the same experiment run.

    Returns the path to the written file.

    """
    if dest_dir is None:
        dest_dir = tempfile.mkdtemp(prefix="gepa_eval_")

    path = os.path.join(dest_dir, filename)
    with open(path, "w") as f:
        json.dump(details, f)
    return path


# ---------------------------------------------------------------------------
# High-level: persist a standalone evaluation
# ---------------------------------------------------------------------------


def save_evaluation_to_experiment(
    session: Session,
    experiment_name: str,
    *,
    function_name: str,
    metric_name: str,
    model_name: str,
    score: float,
    num_examples: int,
    eval_details: list[dict[str, Any]],
    run_name: str = "EVAL",
    sample_size: int | None = None,
    custom_metric_udf: str = "",
    elapsed_seconds: float | None = None,
    cost_info: CostMeasurement | None = None,
    upload_details: bool = True,
    function_impl: str = "",
    create_experiment_if_missing: bool = True,
) -> None:
    """Persist a standalone EVALUATE_AI_FUNCTION result to a Snowflake Experiment.

    Creates the experiment if needed, adds a single ``EVAL`` run with
    aggregate metrics + parameters, uploads ``eval_detail.json`` to the run's
    nested stage, then commits.

    When ``upload_details`` is False, the per-row ``eval_detail.json`` artifact
    is not uploaded — only run-level parameters and metrics are recorded. Both
    the standalone ``EVALUATE_AI_FUNCTION`` and the spec-driven eval path leave
    it at the default (True) so per-row results land on the run's nested stage.

    ``function_impl`` is the function's source recorded on the run: empty for a
    user function (its impl is the introspected DDL, not carried here), or the
    inline ``query_text`` expression for a builtin AI function.

    When ``create_experiment_if_missing`` is False the experiment is NOT created
    here — it must already exist, and the run is only attached to it. The
    spec-driven / EXECUTE EXPERIMENT path sets this False because the DDL layer
    creates the experiment before invoking the SPROC; the standalone
    ``EVALUATE_AI_FUNCTION`` path leaves it at the default (True) to keep
    auto-creating on first use.

    Persistence failures (DDL errors, missing privileges, stage upload
    failures) propagate to the caller so that ``evaluate_handler`` never
    returns a SnowURL that points at nothing.
    """
    if create_experiment_if_missing:
        create_experiment(session, experiment_name)

    params = RunParams(
        function_impl=function_impl,
        model=model_name,
        iteration="0",
        function_name=function_name,
        metric_name=metric_name,
        custom_metric_udf=custom_metric_udf,
        status="completed",
        num_examples=num_examples,
        sample_size=sample_size,
        elapsed_seconds=elapsed_seconds,
    )

    metrics: list[dict[str, Any]] = [{"name": "score", "value": score}]
    if cost_info is not None:
        metrics.append(
            {"name": "estimated_cost", "value": cost_info.estimated_cost_per_call}
        )
        metrics.append(
            {"name": "avg_prompt_tokens", "value": cost_info.avg_prompt_tokens}
        )
        metrics.append(
            {"name": "avg_completion_tokens", "value": cost_info.avg_completion_tokens}
        )

    add_experiment_run(
        session,
        experiment_name,
        run_name,
        params=params,
        metrics=metrics,
    )

    if upload_details and eval_details:
        # One ``eval_detail.json`` per run — each lives under its own run's
        # nested stage, so the filename needs no run-name prefix.
        detail_path = write_eval_detail_artifact(eval_details)
        put_experiment_artifact(
            session,
            experiment_name,
            run_name,
            local_path=detail_path,
        )

    commit_experiment_run(session, experiment_name, run_name)


def save_failed_run_to_experiment(
    session: Session,
    experiment_name: str,
    *,
    function_name: str,
    model: str,
    error_message: str,
    prompt_snippet: str = "",
    elapsed_seconds: float | None = None,
) -> None:
    """Record a failed model optimization as an experiment run.

    Replaces the old ``_log_tracking_error`` / ``_ERRORS`` table pattern.
    """
    try:
        run_name = make_failed_run_name(model)
        params = RunParams(
            function_impl=prompt_snippet[:500],
            model=model,
            iteration="0",
            function_name=function_name,
            status="failed",
            error_message=error_message[:16_777_000],
            elapsed_seconds=elapsed_seconds,
        )
        add_experiment_run(session, experiment_name, run_name, params=params)
        commit_experiment_run(session, experiment_name, run_name)
    except Exception:
        logger.exception(
            "Failed to log error run to experiment %s",
            experiment_name,
        )


# ---------------------------------------------------------------------------
# Error surfacing on natural runs (spec-driven eval/opt path)
# ---------------------------------------------------------------------------


def set_run_error_message(
    session: Session,
    experiment_name: str,
    run_name: str,
    error_message: str,
    error_type: ErrorType | None = None,
) -> None:
    """Attach an ``error_message`` (+ ``status='failed'``) parameter to a run.

    Issues ``ALTER EXPERIMENT ... MODIFY RUN <run> ADD PARAMETERS`` carrying a
    :class:`RunParams` with ``status='failed'``, the (capped) error text, and —
    when provided — the ``error_type`` (``"user"`` / ``"internal"``) so a
    consumer can tell "fix your input" from "retry / contact support". The run's
    terminal status is set separately via ``COMMIT RUN ... WITH STATUS='FAILED'``;
    this only records WHY it failed as run parameters, since the experiment
    metadata has no error field.

    Best-effort: any failure is logged and swallowed so recording the error can
    never itself crash the handler. The other :class:`RunParams` required fields
    (``function_impl`` / ``model`` / ``iteration``) are set to harmless defaults
    — this MODIFY only adds the parameters that matter for a failure.
    """
    try:
        params = RunParams(
            function_impl="",
            model="",
            iteration="0",
            status="failed",
            error_message=error_message[:16_777_000],
            error_type=error_type,
        )
        params_json = escape_sql_string(json.dumps(params.to_param_list()))
        timed_experiment_sql(
            session,
            f"ALTER EXPERIMENT {experiment_name} MODIFY RUN {run_name} "
            f"ADD PARAMETERS = '{params_json}'",
        )
    except Exception:
        logger.exception(
            "Failed to set error_message on run %s in experiment %s",
            run_name,
            experiment_name,
        )


def fail_run(
    session: Session,
    experiment_name: str,
    run_name: str,
    *,
    error_message: str,
    error_type: ErrorType | None = None,
    function_name: str | None = None,
    function_impl: str = "",
) -> None:
    """Create-or-attach a run, record the error, and commit it FAILED.

    Used by the spec-driven eval path (``EVAL_i`` / ``EVAL_1``) and the pre-SEED
    optimization path (``SEED``) to surface an unhandled error on the job's
    natural run rather than a dedicated throwaway ``<MODEL>_FAILED`` run.

    Attempts ``ADD RUN <run>`` (creating the run if it does not exist); if the
    run already exists (a partial run from a mid-execution failure) the ADD RUN
    error is swallowed and the flow continues to record the error on the
    existing run. Then writes the ``error_message`` (and ``error_type`` when
    provided — ``"user"`` / ``"internal"``) parameter and commits the run
    ``WITH STATUS='FAILED'``.

    Best-effort throughout: recording a failure must never itself raise. NEVER
    creates the experiment — an absent experiment simply means every step fails
    and is logged.
    """
    # Create the run if it is not already present. A pre-existing run (partial
    # run from a mid-execution failure) makes ADD RUN fail; swallow that and
    # fall through to record the error on the run that already exists.
    try:
        params = RunParams(
            function_impl=function_impl,
            model="",
            iteration="0",
            function_name=function_name,
            status="failed",
            error_message=error_message[:16_777_000],
            error_type=error_type,
        )
        add_experiment_run(session, experiment_name, run_name, params=params)
    except Exception:
        logger.warning(
            "fail_run: ADD RUN %s in %s failed (run may already exist); "
            "attaching error to the existing run.",
            run_name,
            experiment_name,
        )
        # The ADD RUN path could not attach parameters, so set them here on the
        # already-existing run.
        set_run_error_message(
            session, experiment_name, run_name, error_message, error_type
        )

    try:
        commit_experiment_run(session, experiment_name, run_name, status="FAILED")
    except Exception:
        logger.exception(
            "fail_run: failed to commit run %s in experiment %s as FAILED",
            run_name,
            experiment_name,
        )


def most_recent_running_run(run_names: set[str] | list[str]) -> str | None:
    """Pick the most-recently-created still-RUNNING run from ``run_names``.

    The optimizer's ``progressive_tracker.persisted_runs`` is an unordered set
    of RUNNING ``SEED`` / ``ITER_<N>`` names. "Most recent" is the highest
    ``ITER_<N>`` by parsed ``N``; if there is no ``ITER_<N>`` run, ``SEED`` when
    present; otherwise any remaining name, or ``None`` when empty. Pure helper —
    issues no SQL.
    """
    best_iter: tuple[int, str] | None = None
    for name in run_names:
        if name.startswith("ITER_"):
            with contextlib.suppress(ValueError):
                n = int(name[len("ITER_") :])
                if best_iter is None or n > best_iter[0]:
                    best_iter = (n, name)
    if best_iter is not None:
        return best_iter[1]
    if SEED_RUN_NAME in run_names:
        return SEED_RUN_NAME
    return next(iter(run_names), None)


# ---------------------------------------------------------------------------
# Pareto frontier helpers
# ---------------------------------------------------------------------------


def estimate_candidate_cost(
    model: str,
    avg_prompt_tokens: float,
    avg_completion_tokens: float,
) -> float:
    """Estimate per-call cost in Snowflake credits for a (model, candidate).

    Cost = ``(avg_prompt_tokens × input_rate + avg_completion_tokens ×
    output_rate) / 1_000_000``.

    Token counts must come from ``AI_COMPLETE``'s ``usage`` block (via
    :class:`IterationPhaseBreakdown` for optimize, or ``show_details=>TRUE``
    for evaluate).  Rates from ``models.json`` are credits per million tokens.

    Raises:
        ValueError: If ``model`` is absent from the rate table.  A missing
            model means the rate table is out of date — this is a
            configuration error, not a recoverable condition.

    """
    model_rates = _load_model_rates()
    rates = model_rates.get(model)
    if not rates:
        raise ValueError(
            f"Model {model!r} not found in models.json rate table "
            f"(available: {sorted(model_rates)})"
        )
    return (
        avg_prompt_tokens * rates.get("input_cost", 0)
        + avg_completion_tokens * rates.get("output_cost", 0)
    ) / 1_000_000


def compute_pareto_frontier(
    points: list[tuple[float, float]],
) -> set[int]:
    """Return indices of pareto-optimal points on (cost, score).

    A point is pareto-optimal if no other point has both lower-or-equal
    cost AND strictly higher score, or strictly lower cost AND
    higher-or-equal score.

    Uses a sweep-line algorithm: sort by cost ascending (score descending
    to break ties), then keep points that improve on the best score seen so far.
    """
    if not points:
        return set()
    indexed = sorted(enumerate(points), key=lambda t: (t[1][0], -t[1][1]))
    frontier: set[int] = set()
    max_score = float("-inf")
    for orig_idx, (_cost, score) in indexed:
        if score > max_score:
            frontier.add(orig_idx)
            max_score = score
    return frontier


def hypervolume_subset_selection(
    points: list[tuple[float, float]],
    k: int,
    *,
    reference: tuple[float, float] | None = None,
) -> list[int]:
    """Select k points from a 2D Pareto front that maximize hypervolume.

    The hypervolume indicator measures the area of objective space dominated
    by the selected subset relative to a reference point.  Maximising it
    picks the subset that best represents the full cost/quality tradeoff
    space — the standard approach in multi-objective optimization.

    **Normalisation** — Both axes are rescaled to [0, 1] before computing
    hypervolume so that neither axis dominates the area calculation due to
    scale differences.  Without this, an axis with a large numeric range
    (e.g. cost in dollars) would overpower one with a small range
    (e.g. score in [0.8, 0.95]), biasing selection toward that axis.

    After normalisation the reference point defaults to ``(1.1, -0.1)`` —
    a symmetric 10% margin beyond [0, 1] on each axis.  This is the
    "spread-maximising" configuration: no intentional bias toward cheap
    or high-quality candidates.  The margin ensures that even the extreme
    points (cheapest and most expensive) get a non-zero rectangle.

    If a caller-supplied ``reference`` is given it is used *before*
    normalisation (i.e. in original cost/score units) and then normalised
    together with the candidate points.

    In 2D the greedy algorithm (iteratively pick the point with the
    largest marginal hypervolume contribution) is optimal for k <= n
    and runs in O(k² * n) — each of k rounds scans n candidates,
    and each marginal contribution walks the k-sized selected set.

    Args:
        points: List of (cost, score) tuples.  Lower cost is better,
            higher score is better.
        k: Maximum number of points to select.  If ``len(points) <= k``
            all indices are returned.
        reference: Reference point (ref_cost, ref_score) in *original*
            (unnormalised) units.  Must be dominated by all points
            (higher cost, lower score).  If None, defaults to a
            symmetric 10% margin beyond the normalised [0, 1] range.

    Returns:
        List of original indices into *points*, ordered by selection
        round (first selected = index 0).

    """
    n = len(points)
    if n == 0:
        return []
    if n <= k:
        return list(range(n))

    # ------------------------------------------------------------------
    # Normalise both axes to [0, 1] so neither dominates the area calc.
    # ------------------------------------------------------------------
    costs = [c for c, _s in points]
    scores = [s for _c, s in points]
    min_cost, max_cost = min(costs), max(costs)
    min_score, max_score = min(scores), max(scores)

    cost_range = max_cost - min_cost if max_cost > min_cost else 1.0
    score_range = max_score - min_score if max_score > min_score else 1.0

    norm_points: list[tuple[float, float]] = [
        ((c - min_cost) / cost_range, (s - min_score) / score_range) for c, s in points
    ]

    if reference is not None:
        # Normalise the caller-supplied reference using the same scale.
        ref_cost = (reference[0] - min_cost) / cost_range
        ref_score = (reference[1] - min_score) / score_range
    else:
        # Symmetric 10% margin beyond [0, 1] — spread-maximising.
        ref_cost = 1.1
        ref_score = -0.1

    # ------------------------------------------------------------------
    # Greedy selection: each round picks the remaining point whose
    # rectangle (marginal hypervolume contribution) is largest.
    # ------------------------------------------------------------------
    selected: list[int] = []
    remaining = set(range(n))

    for _ in range(k):
        best_idx = -1
        best_contribution = -1.0

        for idx in remaining:
            cost_i, score_i = norm_points[idx]
            contribution = _marginal_hypervolume_2d(
                cost_i, score_i, selected, norm_points, ref_cost, ref_score
            )
            if contribution > best_contribution or (
                contribution == best_contribution
                and (best_idx == -1 or cost_i < norm_points[best_idx][0])
            ):
                best_contribution = contribution
                best_idx = idx

        if best_idx < 0:
            break
        selected.append(best_idx)
        remaining.discard(best_idx)

    return selected


def build_frontier_from_pareto(
    model_results: list[dict],
    *,
    logger: logging.Logger | None = None,
) -> tuple[list[FrontierCandidate], float | None]:
    """Convert ParetoCandidateInfo entries from model workers into FrontierCandidates.

    Filters out candidates where estimated_cost is None (indicating the candidate
    errored before producing output tokens, so token-based cost cannot be computed).

    Args:
        model_results: List of per-model result dicts, each potentially containing
            a ``_pareto_candidates`` key with ``ParetoCandidateInfo`` entries.
        logger: Optional logger for warnings about skipped candidates.

    Returns:
        Tuple of (frontier_candidates, seed_val_score) ready for
        ``select_frontier_candidates``.

    """

    def _pareto_to_frontier(pc: ParetoCandidateInfo) -> FrontierCandidate | None:
        if pc.estimated_cost is None:
            return None
        idx = 0
        if "_ITER_" in pc.run_name:
            with contextlib.suppress(ValueError, IndexError):
                idx = int(pc.run_name.rsplit("_ITER_", 1)[1])
        return FrontierCandidate(
            model=pc.model,
            candidate_idx=idx,
            estimated_cost=pc.estimated_cost,
            score=pc.score,
            prompt_text=pc.prompt_text,
            run_name=pc.run_name,
        )

    all_frontier_candidates: list[FrontierCandidate] = []
    skipped_none_cost = 0
    for mr in model_results:
        for pc in mr.pop("_pareto_candidates", []):
            fc = _pareto_to_frontier(pc)
            if fc is not None:
                all_frontier_candidates.append(fc)
            else:
                skipped_none_cost += 1
    if skipped_none_cost and logger:
        logger.warning(
            "Skipped %d candidates with no estimated_cost "
            "(models.json may be unavailable)",
            skipped_none_cost,
        )

    seed_val_score = None
    for mr in model_results:
        if mr.get("status") == "completed" and mr.get("seed_val_score") is not None:
            seed_val_score = mr["seed_val_score"]
            break

    return all_frontier_candidates, seed_val_score


def select_frontier_candidates(
    candidates: list[FrontierCandidate],
    *,
    max_candidates: int = 7,
    seed_score: float | None = None,
) -> list[FrontierCandidate]:
    """Pick the most representative candidates from a cross-model frontier.

    Steps:
      1. Compute the Pareto frontier on ``(estimated_cost, score)``.
      2. If the frontier has more than *max_candidates* points, use
         ``hypervolume_subset_selection`` to cap it.

    Args:
        candidates: All accepted candidates across all models.
        max_candidates: Budget for test-evaluation (excluding seeds).
        seed_score: If provided, builds a reference point where only the
            region improving over the seed baseline contributes to the
            hypervolume indicator.  The reference cost is set to
            ``max_cost * 1.1`` so it is dominated by all frontier points.

    Returns:
        Selected ``FrontierCandidate`` items in hypervolume-selection
        order (first = largest marginal contribution).

    """
    if not candidates:
        return []

    points = [(c.estimated_cost, c.score) for c in candidates]
    frontier_indices = compute_pareto_frontier(points)
    if not frontier_indices:
        return []

    frontier_points = [points[i] for i in sorted(frontier_indices)]
    frontier_candidates = [candidates[i] for i in sorted(frontier_indices)]

    if len(frontier_points) <= max_candidates:
        return frontier_candidates

    # Build an explicit reference only when seed_score is given — this
    # restricts volume to the region improving over the baseline.
    # Otherwise let hypervolume_subset_selection use its default
    # normalised (1.1, -0.1) spread-maximising reference.
    reference: tuple[float, float] | None = None
    if seed_score is not None:
        max_cost = max(c for c, _s in frontier_points)
        ref_cost = max_cost * 1.1 if max_cost > 0 else 1.0
        reference = (ref_cost, seed_score)

    selected_indices = hypervolume_subset_selection(
        frontier_points, k=max_candidates, reference=reference
    )
    return [frontier_candidates[i] for i in selected_indices]


def safe_float(value: Any) -> float | None:
    """Coerce to float, returning None on failure or NaN.

    The GEPA event dicts typed-dict floats but in practice can hold
    Python ``float('nan')`` or non-numeric strings under exotic
    error paths; we'd rather record None than blow up the entire
    save flow.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def timed_experiment_sql(session: Session, sql: str) -> None:
    """Run a single Experiment DDL/DML statement and record duration.

    Centralises the timing wrapper so every CREATE EXPERIMENT / ALTER
    EXPERIMENT round-trip lands on the active TimingTracker — surfaces
    bookkeeping cost separately from UDF compile / execute / metric /
    reflection.
    """
    tracker = get_active_tracker()
    _t0 = time.perf_counter()
    try:
        session.sql(sql).collect()
    finally:
        if tracker is not None:
            tracker.add_experiment(time.perf_counter() - _t0)


def _marginal_hypervolume_2d(
    cost: float,
    score: float,
    selected: list[int],
    points: list[tuple[float, float]],
    ref_cost: float,
    ref_score: float,
) -> float:
    """Marginal hypervolume contribution of a candidate in cost-score space.

    Our objectives are *mixed*: minimise cost, maximise score.  Standard
    hypervolume assumes both objectives are maximised.  The classic trick
    is to negate cost (c' = -c) so both axes point "up-and-right", then
    apply the usual formula.  Rather than actually flipping the axis, we
    get the same result by measuring each candidate's rectangle **to the
    right** (toward higher / worse cost) instead of to the left.

    Let *p* = ``(cost, score)``, the candidate point being evaluated:

        score ↑
          |
          |  p ·─────────┐
          |  │            │  width  = right_bound - cost
          |  │    ΔHV(p)  │  height = score - bottom_bound
          |  └────────────┘
          └──────────────────→ cost
                          ref_cost

    Bounds are tightened by already-selected neighbours:

    * ``right_bound`` — cost of the nearest selected point that is more
      expensive than *p*, falling back to ``ref_cost``.
    * ``bottom_bound`` — score of the nearest selected point that is
      cheaper than *p*, falling back to ``ref_score``.

    Equivalence to the negated-cost formulation::

        ΔHV = (c'_p − c'_left) × (q_p − q_bottom)
            = (−c_p − (−c_right)) × (q_p − q_bottom)
            =  (c_right − c_p)    × (q_p − q_bottom)   ← what we compute

    The reference point (``ref_cost``, ``ref_score``) must be strictly
    dominated by every frontier point (i.e. higher cost, lower score) so
    that every point contributes a non-zero rectangle.
    """
    if score <= ref_score or cost >= ref_cost:
        return 0.0

    right_bound = ref_cost
    bottom_bound = ref_score

    for idx in selected:
        sc, ss = points[idx]
        if sc > cost:
            right_bound = min(right_bound, sc)
        elif sc < cost:
            bottom_bound = max(bottom_bound, ss)

    width = right_bound - cost
    height = score - bottom_bound
    if width <= 0 or height <= 0:
        return 0.0
    return width * height


def _timed_artifact_put(session: Session, local_file: str, stage_path: str) -> None:
    """Upload a single file via ``session.file.put`` and record duration.

    Each individual PUT is timed so the tracker reports both the
    artifact count (≈ number of files) and total upload wall time.
    """
    tracker = get_active_tracker()
    _t0 = time.perf_counter()
    try:
        session.file.put(local_file, stage_path, auto_compress=True, overwrite=True)
    finally:
        if tracker is not None:
            tracker.add_artifact_upload(time.perf_counter() - _t0)
