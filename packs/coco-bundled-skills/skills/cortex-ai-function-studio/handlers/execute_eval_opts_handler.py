# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""SPROC entry point for EXECUTE_AI_FUNCTION_EVAL_OPTS.

A single spec-driven entry point that runs **either** an evaluation **or** an
optimization job, dispatching on the input SPECIFICATION's top-level marker
section — matching the canonical experiment-spec JSON Schemas (both share
``function`` / ``metrics`` / ``dataset``; the eval spec adds a required
``evaluation`` section, the opt spec adds a required ``optimization`` section):

* ``evaluation`` present   -> evaluation  (score the function; run-level metrics)
* ``optimization`` present -> optimization (GEPA optimize the function)

The SPEC YAML text is passed in as ``specification`` (``EXECUTE EXPERIMENT``
supplies it; the procedure does not read the experiment object itself). Bundled
into the ``caifs_eval_opts`` module (built from the optimize source set, a
superset that includes the eval engine + GEPA), so the SPROC handler is
``caifs_eval_opts.execute_ai_function_eval_opts``.
"""

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yaml
from snowflake.snowpark import Session

# run_optimization lives in the same concatenated bundle (optimize source set).
from handlers.optimize_handler import run_optimization
from snowflake_ai_optimize.core.errors import classify
from snowflake_ai_optimize.core.evaluation import evaluate
from snowflake_ai_optimize.core.experiment import (
    fail_run,
    save_evaluation_to_experiment,
)
from snowflake_ai_optimize.core.metrics.llm_judge import LLM_JUDGE_DEFAULT_MODEL
from snowflake_ai_optimize.core.session import custom_ai_query_tag_logging
from snowflake_ai_optimize.core.sproc_decorators import (
    ai_sql_error_handling_use_fail_on_error_disabled_for_sproc,
    surface_sproc_error,
)
from snowflake_ai_optimize.core.sql_utils import (
    describe_function,
    resolve_param_name,
)

logger = logging.getLogger(__name__)

# Metric names whose spec key differs from the engine's canonical name.
_METRIC_NAME_NORMALIZE = {"llm-judge": "llm_judge"}

# Metric names accepted by the spec: the engine's built-in metrics plus
# ``custom`` (which requires custom_udf). Validated up front so a typo
# fails with a clear error instead of deep inside the eval engine.
_SUPPORTED_METRICS = {
    "exact_match",
    "fuzzy_match",
    "contains_match",
    "redaction_match",
    "llm_judge",
    "custom",
}

# Valid concrete auto-budget presets. The legacy ``demo`` alias for
# ``ultra-light`` is intentionally NOT accepted on the spec path — only the
# canonical preset names are valid. Validated up front so a bad value fails
# clearly here instead of downstream in run_optimization.
_VALID_BUDGETS = {"ultra-light", "light", "medium", "heavy"}

# The customer-facing sentinel budget. When ``optimization.budget`` is omitted
# (or explicitly set to ``"auto"``) the engine picks the concrete preset. This
# lets the auto→concrete mapping evolve without a spec change.
_AUTO_BUDGET = "auto"

# The concrete preset that ``auto`` resolves to *as of today*. This indirection
# is deliberate: the auto→concrete mapping is an engine decision that may change
# in the future (e.g. become input-size dependent), so callers should not rely
# on ``auto`` always meaning ``light``. Do NOT scatter the "light" literal —
# route every auto resolution through this constant.
#
# ``light`` matches the SQL OPTIMIZE_AI_FUNCTION SPROC default (DEFAULT 'light',
# n=6); without it the spec path would fall through to run_optimization's Python
# signature default ("ultra-light", n=2).
_AUTO_BUDGET_RESOLVES_TO = "light"

# Cap concurrent eval fan-out (num_eval_runs > 1) to protect the account.
_MAX_EVAL_PARALLELISM = 3

# Run-name prefix for the num_eval_runs > 1 fan-out: EVAL_1 .. EVAL_N.
_EVAL_RUN_NAME_PREFIX = "EVAL"

# The single-run eval / spec-parse-error default run name (EVAL_1).
_EVAL_FIRST_RUN_NAME = f"{_EVAL_RUN_NAME_PREFIX}_1"

# The optimization job's seed run name — where a pre-SEED opt error is recorded.
_SEED_RUN_NAME = "SEED"

# QUERY_TAG suffix for this SPROC's queries (was a decorator argument).
_EVAL_OPTS_QUERY_TAG = "SPROC_EXECUTE_AI_FUNCTION_EVAL_OPTS"


def _surface_error(exc: Exception) -> str:
    """Return the customer-facing message recorded in the run ``error_message``.

    Only the surfaced exception message goes on the run — NOT the Python
    traceback: ``error_message`` is visible to the customer via ``SHOW RUN
    PARAMETERS``, so it should read as an error message, not an internal stack
    trace. The full traceback is logged server-side instead (``exc_info=True``
    captures it when called inside an ``except`` block; it is a no-op for a
    synthesized, never-raised exception). ``fail_run`` / ``set_run_error_message``
    cap the length before persisting.
    """
    logger.warning(
        "execute_ai_function_eval_opts recording failure on run: %s",
        exc,
        exc_info=True,
    )
    return str(exc)


def _record_failure(
    session: Session,
    experiment_name: str,
    run_name: str,
    exc: Exception,
    *,
    function_name: str | None = None,
    function_impl: str = "",
) -> str:
    """Classify ``exc``, record it on the run, and commit the run FAILED.

    Records both the ``error_message`` and the classified ``error_type``
    (``"user"`` / ``"internal"``). Single chokepoint for run-level failure
    surfacing: every handler ``except`` routes here so classification happens in
    one place. Returns the classified ``error_type`` for the response payload.
    """
    error_type = classify(exc)
    fail_run(
        session,
        experiment_name,
        run_name,
        error_message=_surface_error(exc),
        error_type=error_type,
        function_name=function_name,
        function_impl=function_impl,
    )
    return error_type


def _parse_specification(specification: str) -> dict:
    """Parse the SPEC (inline YAML text) into a dict.

    Raises ValueError on empty / non-mapping specs so the SPROC surfaces a
    clear error instead of a downstream ``NoneType`` failure.
    """
    if not specification or not specification.strip():
        raise ValueError("specification is required and cannot be empty")
    try:
        spec = yaml.safe_load(specification)
    except yaml.YAMLError as exc:
        raise ValueError(f"specification is not valid YAML: {exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError("specification must be a YAML mapping")
    return spec


def _first_metric(spec: dict) -> dict:
    """Return the single eval/opt metric mapping from the SPEC.

    Accepts either a ``metrics:`` list with exactly one entry, or a single
    ``metrics:`` mapping. More than one metric is rejected: the engine scores
    and reports one metric per run, so extra entries would be silently dropped.
    """
    metrics = spec.get("metrics")
    if isinstance(metrics, dict):
        return metrics
    if isinstance(metrics, list) and metrics:
        if len(metrics) > 1:
            raise ValueError(
                "specification.metrics supports exactly one metric "
                f"(got {len(metrics)}); scoring multiple metrics is not supported"
            )
        first = metrics[0]
        if not isinstance(first, dict):
            raise ValueError("each metrics entry must be a mapping")
        return first
    raise ValueError("specification.metrics is required (a metric with a 'name')")


def _resolve_function(spec: dict) -> tuple[str | None, str | None]:
    """Resolve the AI function under evaluation/optimization from the SPEC.

    Returns ``(function_name, query_text)`` with exactly one populated:

    * a **user** AI function is identified by ``function.function_name``
      -> ``(function_name, None)``;
    * a **builtin** AI function is given as an inline ``function.query_text``
      scalar expression that references the dataset columns directly
      -> ``(None, query_text)``.

    The kind is inferred purely from which field is populated. Supplying both,
    or neither, is an error. Note: a builtin ``query_text`` is NOT restricted to
    AI_COMPLETE here — evaluation accepts any expression that runs and returns a
    result. The single-AI_COMPLETE restriction applies only to optimization
    (enforced in :func:`_run_optimization`).
    """
    function = spec.get("function")
    if not isinstance(function, dict):
        raise ValueError("specification.function is required")

    function_name = function.get("function_name")
    query_text = function.get("query_text")

    if function_name and query_text:
        raise ValueError(
            "specification.function must set exactly one of function_name "
            "(user AI function) or query_text (builtin AI function), not both"
        )
    if query_text is not None and str(query_text).strip():
        return None, str(query_text)
    if function_name:
        return str(function_name), None
    raise ValueError(
        "specification.function requires function_name (user AI function) "
        "or query_text (builtin AI function)"
    )


# Placeholder name recorded for a builtin whose AI function cannot be identified.
_BUILTIN_FUNCTION_FALLBACK_NAME = "BUILTIN_AI_FUNCTION"

# AI functions recognized inside a builtin ``query_text``. Detection keys off
# these names (not the outermost SQL token) so a wrapped call such as
# ``UPPER(AI_COMPLETE(...))`` is still identified as AI_COMPLETE, and so we can
# count AI-function calls to reject unsupported multi-function query_text.
#
# The system ``AI_*`` functions are callable unqualified and have distinctive
# names, so they are matched bare (or qualified) by explicit name. Everything
# under the ``[SNOWFLAKE.]CORTEX.`` schema is treated as an AI function by
# namespace — we do NOT enumerate the Cortex function names, so any
# ``SNOWFLAKE.CORTEX.<fn>(...)`` call is detected (and, for optimization,
# rejected unless it is AI_COMPLETE). Requiring the ``CORTEX.`` qualifier avoids
# false-matching plain identifiers like a bare ``COMPLETE`` / ``SUMMARIZE``.
_AI_FUNCTION_NAMES = (
    "AI_COMPLETE",
    "AI_CLASSIFY",
    "AI_FILTER",
    "AI_AGG",
    "AI_SUMMARIZE_AGG",
    "AI_SIMILARITY",
    "AI_EMBED",
    "AI_EXTRACT",
    "AI_SENTIMENT",
    "AI_TRANSCRIBE",
    "AI_PARSE_DOCUMENT",
)
# Longest names first so e.g. AI_SUMMARIZE_AGG matches before a shorter prefix;
# ``\b`` anchors to a word boundary so ``MY_AI_COMPLETE`` is not matched. The
# ``ai`` group captures a bare/qualified AI_* call; the ``cortex`` group captures
# the function name of ANY ``[SNOWFLAKE.]CORTEX.<fn>`` call (qualifier required).
_AI_FUNCTION_CALL_RE = re.compile(
    r"\b(?:"
    r"(?P<ai>" + "|".join(sorted(_AI_FUNCTION_NAMES, key=len, reverse=True)) + r")"
    r"|(?:SNOWFLAKE\s*\.\s*)?CORTEX\s*\.\s*(?P<cortex>[A-Za-z_]\w*)"
    r")\s*\(",
    re.IGNORECASE,
)


def _find_ai_function_calls(query_text: str | None) -> list[str]:
    """Return the uppercased names of known AI-function calls, in text order.

    System ``AI_*`` functions match whether bare or qualified; any function
    under the ``[SNOWFLAKE.]CORTEX.`` schema matches by namespace (its name is
    not enumerated).
    """
    calls: list[str] = []
    for m in _AI_FUNCTION_CALL_RE.finditer(query_text or ""):
        calls.append((m.group("ai") or m.group("cortex")).upper())
    return calls


def _validate_query_text_ai_complete(query_text: str) -> None:
    """Require an **optimization** query_text to call exactly one AI_COMPLETE.

    Optimization is scoped to ``AI_COMPLETE``: it is the only builtin whose
    prompt is well-defined to optimize and whose token/cost tracking (via
    ``show_details``) is single-valued. Detection keys off the known
    AI-function names (so ``UPPER(AI_COMPLETE(...))`` is recognized as one
    AI_COMPLETE, not the outer ``UPPER``), and rejects, with a clear error:

    * no AI function call at all;
    * a different AI function (``AI_CLASSIFY``, ``AI_FILTER``, ...);
    * more than one AI-function call (unsupported — ambiguous which is
      optimized/costed).

    Evaluation does NOT call this — there any expression that runs and returns a
    result is accepted.
    """
    calls = _find_ai_function_calls(query_text)
    if not calls:
        raise ValueError(
            "specification.function.query_text must call AI_COMPLETE for "
            "optimization; no AI function call was found."
        )
    if len(calls) > 1:
        raise ValueError(
            "specification.function.query_text must contain exactly one AI "
            f"function call for optimization (found {len(calls)}: {calls})."
        )
    if calls[0] != "AI_COMPLETE":
        raise ValueError(
            "specification.function.query_text optimization supports only "
            f"AI_COMPLETE (got {calls[0]})."
        )


def _validate_query_text_compiles(
    session: Session, query_text: str, dataset_table: str
) -> None:
    """Compile-check a builtin ``query_text`` against the dataset, no AI calls.

    Runs ``SELECT (query_text) FROM <table> WHERE FALSE`` — zero rows, so the
    expression is name/type-checked by Snowflake but no ``AI_COMPLETE`` actually
    executes (no model cost). A malformed expression or a bad column reference
    therefore fails HERE with a clear, attributable error — distinct from a
    later failure inside the handler's own CTE construction, which answers "is
    it the user's query_text or our SQL?". (Runtime-only errors, e.g. an invalid
    model name, are not exercised by the zero-row probe and still surface during
    the real run via the SPROC error decorators.)
    """
    probe = f"SELECT ({query_text}) AS __PROBE FROM {dataset_table} WHERE FALSE"
    try:
        session.sql(probe).collect()
    except Exception as exc:
        raise ValueError(
            f"function.query_text is not a valid expression over dataset "
            f"{dataset_table}: {exc}"
        ) from exc


def _builtin_function_name(query_text: str | None) -> str:
    """Return the AI function a builtin ``query_text`` calls (e.g. ``AI_COMPLETE``).

    Identifies the function by the known AI-function names present rather than
    the outermost SQL token, so a wrapped call such as ``UPPER(AI_COMPLETE(...))``
    is reported as ``AI_COMPLETE`` (the AI function being evaluated), which is
    recorded as the run's ``function_name`` (paired with ``function_impl`` = the
    full ``query_text``). Falls back to a generic label when none is found.
    """
    calls = _find_ai_function_calls(query_text)
    return calls[0] if calls else _BUILTIN_FUNCTION_FALLBACK_NAME


def _resolve_dataset(
    spec: dict, *, require_argument_mapping: bool = True
) -> tuple[str, list, str, list]:
    """Resolve (table, input_columns, label_column, arg_keys) from the dataset.

    ``input_columns`` are the dataset column names (the ``argument_mapping``
    values); ``arg_keys`` are the corresponding keys (a parameter name, or a
    positional marker ``$N``), aligned by index. The evaluation engine (incl.
    llm_judge, which grades predicted vs. expected) and the optimizer both
    require a ground-truth column, so ``ground_truth`` is required.

    ``require_argument_mapping`` is ``True`` for user AI functions (whose call
    binds dataset columns to declared parameters). For a builtin ``query_text``
    the mapping is optional — the expression references dataset columns
    directly, so ``argument_mapping`` only names the columns surfaced in the
    per-row input summary and may be omitted (yielding empty ``input_columns``
    / ``arg_keys``).

    ``name`` is a plain table/view, or a Snowflake **DATASET** object
    (``SNOWFLAKE.ML.DATASET``) when a ``dataset.version`` is supplied. This
    helper only extracts the raw name / mapping — resolving a DATASET to a
    queryable temp view is done separately by :func:`_resolve_dataset_source`,
    which needs a session.
    """
    dataset = spec.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("specification.dataset is required (a mapping with 'name')")
    table = dataset.get("name")
    if not table:
        raise ValueError("specification.dataset.name is required")
    column_mapping = dataset.get("column_mapping") or {}
    argument_mapping = column_mapping.get("argument_mapping") or {}
    if not argument_mapping and require_argument_mapping:
        raise ValueError(
            "specification.dataset.column_mapping.argument_mapping is required"
        )
    # Keys (parameter name or "$N") and values (columns) are index-aligned.
    arg_keys = list(argument_mapping.keys())
    input_columns = list(argument_mapping.values())
    ground_truth = column_mapping.get("ground_truth")
    if not ground_truth:
        raise ValueError(
            "specification.dataset.column_mapping.ground_truth is required "
            "(reference-free scoring is not yet supported)"
        )
    return str(table), input_columns, str(ground_truth), arg_keys


# Prefix for the session-scoped TEMPORARY VIEW that materializes a DATASET
# version. Named per worker-thread + call (like TempAIFunction's temp objects)
# so concurrent eval fan-out / multi-model optimization cannot collide, and
# TEMPORARY-scoped so it dies with the session even if an explicit DROP is
# skipped on a crash.
_DATASET_VIEW_PREFIX = "__EVAL_OPTS_DATASET"


def _materialize_dataset_version(session: Session, name: str, version: str) -> str:
    """Load a DATASET version as a Snowpark DataFrame; register it as a temp view.

    A Snowflake DATASET is a versioned *container*, not a directly-queryable
    relation — ``SELECT * FROM <dataset>`` is invalid. ``load_dataset(session,
    name, version)`` selects the version and ``.read.to_snowpark_dataframe()``
    yields a Snowpark DataFrame with the dataset's named + typed columns; we
    operate on that DataFrame directly, registering it as a session TEMPORARY
    VIEW via ``create_or_replace_temp_view``. The view name is returned so all
    downstream table-shaped SQL (``DESCRIBE TABLE {name}`` / ``FROM {name}``)
    runs against it unchanged.

    ``snowflake.ml`` is imported lazily (only when a DATASET is actually read)
    so a bundle missing the dependency surfaces a clear error here rather than
    at module import. ``version`` is forwarded verbatim to ``load_dataset`` (the
    API has no default/latest resolution), so an unknown version surfaces as the
    ML API's own error.
    """
    try:
        from snowflake.ml.dataset import load_dataset
    except ImportError as exc:  # pragma: no cover - bundle always ships the dep
        raise ValueError(
            "reading a Snowflake DATASET object requires the snowflake-ml-python "
            f"package, which is not available: {exc}"
        ) from exc
    dataset = load_dataset(session, name, version)
    dataframe = dataset.read.to_snowpark_dataframe()
    view_name = f"{_DATASET_VIEW_PREFIX}_{threading.get_ident()}_{time.time_ns()}"
    dataframe.create_or_replace_temp_view(view_name)
    return view_name


def _resolve_dataset_source(session: Session, name: str, version: str | None) -> str:
    """Resolve ``dataset.name`` to a relation the rest of the handler can query.

    The presence of a ``version`` selects the mode:

    * **no version** — ``name`` is a plain **table/view** and is returned
      UNCHANGED, so every existing ``FROM {name}`` / ``DESCRIBE TABLE {name}``
      path is unaffected (the pre-existing, backward-compatible behavior).
    * **version given** — ``name`` is a Snowflake **DATASET** object
      (``SNOWFLAKE.ML.DATASET``) read at that version and materialized to a
      session TEMPORARY VIEW (see :func:`_materialize_dataset_version`); the
      view name is returned. The version is forwarded verbatim to the
      ``snowflake.ml`` API (no default/latest resolution, no enumeration).

    A blank/whitespace version is treated as unset (table/view).
    """
    if version is None or str(version).strip() == "":
        return name
    return _materialize_dataset_version(session, name, str(version).strip())


def _resolve_arg_param_names(
    session: Session, function_name: str, arg_keys: list
) -> list[str]:
    """Map ``argument_mapping`` keys to AI-function parameter names.

    Each key is resolved against the function's actual parameters, read via
    ``describe_function`` (which resolves the name — with or without an overload
    signature — through ``SHOW FUNCTIONS``, so a bare ``DB.SCHEMA.FUNC`` works):
    a positional ``$N`` key resolves to the Nth parameter, and a named key is
    matched case-insensitively to a declared parameter and resolved to the DDL's
    exact casing. This matters because the eval engine aliases each dataset
    column to the resolved name (``col AS <name>``) while the inlined UDF body
    references parameters by their declared, typically upper-cased, names — a
    case mismatch (e.g. mapping key ``text`` vs. parameter ``TEXT``) would
    otherwise yield ``invalid identifier``. A named key with no matching
    parameter falls back to itself.
    """
    keys = [str(k) for k in arg_keys]
    param_names = describe_function(session, function_name).arg_names
    return [resolve_param_name(k, param_names) for k in keys]


def _known_models() -> set[str] | None:
    """Model names in the shipped ``models.json`` cost table (lowercased).

    Returns ``None`` if the table cannot be loaded, so model validation fails
    OPEN on an infrastructure problem rather than blocking an otherwise-valid
    run. ``_load_model_rates`` is lru-cached, so repeated calls are cheap.
    """
    try:
        from snowflake_ai_optimize.core.experiment import _load_model_rates

        return {str(m).lower() for m in _load_model_rates()}
    except Exception:
        return None


def _validate_model_known(model: str, *, field: str) -> None:
    """Reject a model absent from the shipped ``models.json`` (cheap allowlist).

    A cheap up-front guard against typos / obviously-wrong model names, using
    the same catalog that drives cost estimation. It is NOT authoritative about
    per-region availability or structured-output support (those can only be
    confirmed by actually calling the model), so it only rejects names the
    bundle has never heard of.
    """
    known = _known_models()
    if known is None:
        return
    if str(model).lower() not in known:
        raise ValueError(
            f"unsupported model {model!r} for {field}; known models: "
            f"{', '.join(sorted(known))}"
        )


def _resolve_metric(metric: dict) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve (metric_name, custom_udf, judge_model, metric_options)."""
    raw_metric_name = metric.get("name")
    if not raw_metric_name:
        raise ValueError("specification.metrics[].name is required")
    metric_name = _METRIC_NAME_NORMALIZE.get(raw_metric_name, raw_metric_name)

    if metric_name not in _SUPPORTED_METRICS:
        raise ValueError(
            f"unsupported metric name {raw_metric_name!r}; supported: "
            f"{', '.join(sorted(_SUPPORTED_METRICS))}"
        )

    custom_metric_udf = metric.get("custom_udf")
    if metric_name == "custom" and not custom_metric_udf:
        raise ValueError("metrics.custom_udf is required when metric name is 'custom'")

    judge_model = metric.get("judge_model") or LLM_JUDGE_DEFAULT_MODEL
    # Cheap up-front guard: reject a judge model the bundle has never heard of.
    if metric_name == "llm_judge":
        _validate_model_known(judge_model, field="metrics.judge_model")
    metric_options: dict[str, Any] = {}
    # Thread the judge model to the metric engine for llm_judge: the engine
    # (llm_judge_batch) reads ``model_name`` from the metric options
    # (**metric_opts), not from the metadata ``model_name`` channel. Without
    # this the spec's ``judge_model`` was recorded only as run metadata and
    # the judge always ran on LLM_JUDGE_DEFAULT_MODEL. Scoped to llm_judge so
    # no unexpected kwarg reaches metrics (e.g. fuzzy_match) that reject it.
    if metric_name == "llm_judge":
        metric_options["model_name"] = judge_model
    return metric_name, custom_metric_udf, judge_model, metric_options


def _resolve_num_eval_runs(spec: dict) -> int:
    """Resolve ``evaluation.num_eval_runs`` (how many eval runs to execute).

    Defaults to 1 when omitted. Must be a positive integer; anything else
    (including a boolean, a float, or a non-numeric string) is rejected with a
    clear error rather than silently coerced.
    """
    evaluation = spec.get("evaluation")
    raw = evaluation.get("num_eval_runs") if isinstance(evaluation, dict) else None
    if raw is None:
        return 1
    # bool is an int subclass, so reject it before the int check (True -> 1).
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(
            "specification.evaluation.num_eval_runs must be a positive integer"
        )
    return raw


@surface_sproc_error()
def execute_ai_function_eval_opts(
    session: Session,
    evaluation_params: dict,
    specification: str,
) -> dict:
    """SPROC entry point for ``EXECUTE_AI_FUNCTION_EVAL_OPTS``.

    Dispatches on the SPEC's top-level marker section: ``evaluation`` -> run an
    evaluation job; ``optimization`` -> run an optimization job.

    Args:
        session: Caller's-rights Snowpark session.
        evaluation_params: OBJECT carrying ``experiment_name`` (required). Run
            names are not caller-supplied: the eval/opt engines assign fixed
            names (eval: ``EVAL_1..EVAL_N``; optimization: ``SEED`` +
            ``ITER_<N>``). Any other keys are ignored.
        specification: eval or opt SPEC as inline YAML text.

    Returns:
        VARIANT with ``experiment`` + ``status`` plus the job's result
        (eval: ``run``/``metrics``; opt: the optimization result).

        On an unhandled error anywhere in the parse + dispatch path — including a
        failure setting up the session param / query tag — the error is NOT
        raised: it is recorded in the ``error_message`` PARAMETER of the job's
        natural run (eval: ``EVAL_1``; opt: ``SEED``) which is committed
        ``FAILED``, and a ``{experiment, run, status: "FAILED", error_message}``
        payload is returned. The sole still-raising case is a missing / non-dict
        ``evaluation_params`` (no experiment, so no run to attach to) — caught by
        the ``@surface_sproc_error()`` backstop.
    """
    # D1 guards: without a valid experiment_name there is no run to attach an
    # error to, so these still raise (surfaced by @surface_sproc_error). EXECUTE
    # EXPERIMENT always supplies experiment_name, so this is defensive.
    if not isinstance(evaluation_params, dict):
        raise ValueError("evaluation_params must be an OBJECT")
    experiment_name = evaluation_params.get("experiment_name")
    if not experiment_name or not str(experiment_name).strip():
        raise ValueError("evaluation_params.experiment_name is required")
    experiment_name = str(experiment_name)

    # Session-param + query-tag management run *inside* the guarded body rather
    # than as outer decorators: a failure setting them up (SHOW PARAMETERS /
    # ALTER SESSION / QUERY_TAG) must record a FAILED run, not escape as an
    # unrecorded task failure — invisible under EXECUTE EXPERIMENT, where the run
    # is the only surface the customer sees.
    result: dict | None = None
    try:
        with (
            ai_sql_error_handling_use_fail_on_error_disabled_for_sproc(session),
            custom_ai_query_tag_logging(session, _EVAL_OPTS_QUERY_TAG),
        ):
            result = _dispatch_eval_opts(session, experiment_name, specification)
    except Exception as exc:
        if result is None:
            # Setup failed before dispatch ran: record the failure on EVAL_1 so it
            # is visible instead of a black hole.
            fail_run(
                session,
                experiment_name,
                _EVAL_FIRST_RUN_NAME,
                error_message=_surface_error(exc),
            )
            return {
                "experiment": experiment_name,
                "run": _EVAL_FIRST_RUN_NAME,
                "status": "FAILED",
                "error_message": str(exc),
            }
        # Restoring the session param / query tag failed AFTER dispatch already
        # produced a result: log it, but do not mask the completed job.
        logger.error(
            "session/query-tag teardown failed after dispatch completed; "
            "returning the dispatch result",
            exc_info=True,
        )
    return result


def _dispatch_eval_opts(
    session: Session, experiment_name: str, specification: str
) -> dict:
    """Parse the SPEC and run the eval or opt job.

    Records any failure on the job's natural run (``EVAL_1`` for eval / spec
    errors, ``SEED`` for a pre-SEED opt error), commits it ``FAILED``, and returns
    a ``{experiment, run, status: "FAILED", error_message}`` payload rather than
    raising.
    """
    # Parse the spec first so we know which path (eval vs opt) an error should
    # attach its failed run to. A parse error is a spec-level error with no known
    # path — default to EVAL_1 (the generic first run). Never raises: records the
    # error on EVAL_1 and returns FAILED.
    try:
        spec = _parse_specification(specification)
    except Exception as exc:
        error_type = _record_failure(
            session, experiment_name, _EVAL_FIRST_RUN_NAME, exc
        )
        return {
            "experiment": experiment_name,
            "run": _EVAL_FIRST_RUN_NAME,
            "status": "FAILED",
            "error_message": str(exc),
            "error_type": error_type,
        }

    is_optimization = "optimization" in spec and "evaluation" not in spec
    if not is_optimization and "evaluation" not in spec:
        # Neither marker section: a spec-shape error with no known path. Treat as
        # a spec-parse-level error and fail the generic first run (EVAL_1).
        no_section_exc = ValueError(
            "specification must contain a top-level 'evaluation' or "
            "'optimization' section"
        )
        error_type = _record_failure(
            session, experiment_name, _EVAL_FIRST_RUN_NAME, no_section_exc
        )
        return {
            "experiment": experiment_name,
            "run": _EVAL_FIRST_RUN_NAME,
            "status": "FAILED",
            "error_message": str(no_section_exc),
            "error_type": error_type,
        }

    # Optimization: mid-optimization errors are already surfaced on the natural
    # SEED/ITER runs by the optimizer itself. An error that ESCAPES here is a
    # pre-SEED failure (validation / resolution before any run exists) → create
    # SEED, record the error, commit FAILED. Never raises.
    if is_optimization:
        try:
            return _run_optimization(session, experiment_name, spec)
        except Exception as exc:
            error_type = _record_failure(session, experiment_name, _SEED_RUN_NAME, exc)
            return {
                "experiment": experiment_name,
                "run": _SEED_RUN_NAME,
                "status": "FAILED",
                "error_message": str(exc),
                "error_type": error_type,
            }

    # Evaluation: _run_evaluation surfaces per-run failures on EVAL_i internally
    # and never raises. The try here is a backstop for any error that escapes
    # before/around the fan-out → fail EVAL_1.
    try:
        return _run_evaluation(session, experiment_name, spec)
    except Exception as exc:
        error_type = _record_failure(
            session, experiment_name, _EVAL_FIRST_RUN_NAME, exc
        )
        return {
            "experiment": experiment_name,
            "run": _EVAL_FIRST_RUN_NAME,
            "status": "FAILED",
            "error_message": str(exc),
            "error_type": error_type,
        }


def _run_evaluation(session: Session, experiment_name: str, spec: dict) -> dict:
    """Score the function; single run or EVAL_1..EVAL_N per ``num_eval_runs``."""
    function_name, query_text = _resolve_function(spec)
    test_table, input_columns, label_column, arg_keys = _resolve_dataset(
        spec, require_argument_mapping=function_name is not None
    )
    # ``dataset.name`` is a plain table/view (used verbatim), or a Snowflake
    # DATASET object materialized to a session temp view when a ``dataset.version``
    # is supplied. Resolve it up front so every downstream ``FROM {test_table}`` /
    # ``DESCRIBE TABLE`` path is unchanged.
    dataset_spec = spec.get("dataset") or {}
    test_table = _resolve_dataset_source(
        session, test_table, dataset_spec.get("version")
    )
    # Evaluation accepts any builtin query_text that runs; compile-check it up
    # front so a malformed expression fails with a clear, attributable error.
    if query_text is not None:
        _validate_query_text_compiles(session, query_text, test_table)
    # A builtin ``query_text`` references dataset columns directly, so there is
    # no function DDL to resolve parameter names against; user functions bind
    # columns to declared parameters.
    input_arg_names = (
        _resolve_arg_param_names(session, function_name, arg_keys)
        if function_name is not None
        else None
    )
    metric_name, custom_metric_udf, model_name, metric_options = _resolve_metric(
        _first_metric(spec)
    )
    num_eval_runs = _resolve_num_eval_runs(spec)

    # Shared eval/opt protocol: a builtin records function_name = the builtin's
    # name (e.g. AI_COMPLETE) and function_impl = the query_text; a user function
    # records its signature as function_name (function_impl stays empty, as the
    # impl is the introspected DDL, not carried here).
    record_function_name = (
        function_name
        if function_name is not None
        else _builtin_function_name(query_text)
    )
    function_impl = query_text or ""

    eval_kwargs: dict[str, Any] = {
        "function_name": record_function_name,
        "query_text": query_text,
        "function_impl": function_impl,
        "test_table": test_table,
        "input_columns": input_columns,
        "label_column": label_column,
        "metric_name": metric_name,
        "model_name": model_name,
        "metric_options": metric_options,
        "custom_metric_udf": custom_metric_udf,
        "input_arg_names": input_arg_names,
    }

    # Run names are engine-assigned (never caller-supplied): a single run is
    # ``EVAL_1`` and the fan-out is ``EVAL_1..EVAL_N``, so both branches share
    # one naming scheme. The single-run branch keeps the pre-existing (flat)
    # return shape that EXECUTE EXPERIMENT callers already depend on.
    #
    # Errors are surfaced on the run itself: a failing run has its reason
    # recorded in the ``error_message`` parameter and is committed FAILED (via
    # ``fail_run`` — create-or-attach, since a pre-execution failure means the
    # run may not exist yet). The handler never creates the experiment.
    if num_eval_runs <= 1:
        run_name = f"{_EVAL_RUN_NAME_PREFIX}_1"
        try:
            outcome = _evaluate_and_save(
                session, experiment_name, run_name, **eval_kwargs
            )
        except Exception as exc:
            error_type = _record_failure(
                session,
                experiment_name,
                run_name,
                exc,
                function_name=record_function_name,
                function_impl=function_impl,
            )
            return {
                "experiment": experiment_name,
                "run": run_name,
                "status": "FAILED",
                "error_message": str(exc),
                "error_type": error_type,
            }
        return {
            "experiment": experiment_name,
            "run": run_name,
            "status": "SUCCEEDED",
            "metrics": {metric_name: outcome["score"]},
            "num_examples": outcome["num_examples"],
        }

    run_names = [f"{_EVAL_RUN_NAME_PREFIX}_{i}" for i in range(1, num_eval_runs + 1)]
    outcomes: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    error_types: dict[str, str] = {}
    max_workers = min(_MAX_EVAL_PARALLELISM, num_eval_runs)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_run = {
            executor.submit(
                _evaluate_and_save, session, experiment_name, run_name, **eval_kwargs
            ): run_name
            for run_name in run_names
        }
        for future in as_completed(future_to_run):
            run_name = future_to_run[future]
            # Each slot is isolated: a per-slot failure records the error on that
            # EVAL_i (committed FAILED) and the remaining slots still finish. The
            # fan-out never raises; the aggregate status reflects any failure.
            try:
                outcomes[run_name] = future.result()
            except Exception as exc:
                errors[run_name] = str(exc)
                error_types[run_name] = _record_failure(
                    session,
                    experiment_name,
                    run_name,
                    exc,
                    function_name=record_function_name,
                    function_impl=function_impl,
                )

    status = "FAILED" if errors else "SUCCEEDED"
    metrics: dict[str, Any] = {}
    for rn in run_names:
        if rn in outcomes:
            metrics[rn] = {metric_name: outcomes[rn]["score"]}
        else:
            metrics[rn] = {
                "status": "FAILED",
                "error_message": errors.get(rn),
                "error_type": error_types.get(rn),
            }
    result: dict[str, Any] = {
        "experiment": experiment_name,
        "runs": run_names,
        "status": status,
        "metrics": metrics,
    }
    # num_examples comes from any successful run (all share the dataset); omit
    # when every slot failed.
    succeeded = [rn for rn in run_names if rn in outcomes]
    if succeeded:
        result["num_examples"] = outcomes[succeeded[0]]["num_examples"]
    return result


def _evaluate_and_save(
    session: Session,
    experiment_name: str,
    run_name: str,
    *,
    function_name: str,
    query_text: str | None,
    function_impl: str,
    test_table: str,
    input_columns: list,
    label_column: str,
    metric_name: str,
    model_name: str,
    metric_options: dict[str, Any],
    custom_metric_udf: str | None,
    input_arg_names: list[str] | None,
) -> dict[str, Any]:
    """Run one evaluation and persist it as a single experiment run.

    ``function_name`` is the recorded identifier (a user function signature, or a
    builtin's name such as ``AI_COMPLETE``); ``function_impl`` is its source (the
    ``query_text`` for a builtin, empty for a user function). ``query_text``, when
    set, routes the engine down the builtin evaluation path.
    """
    start_time = time.time()
    result = evaluate(
        session,
        function_name,
        test_table,
        input_columns,
        label_column,
        metric_name,
        model_name=model_name,
        metric_options=metric_options or None,
        custom_metric_udf=custom_metric_udf,
        run_id=run_name,
        input_arg_names=input_arg_names,
        query_text=query_text,
    )
    elapsed = time.time() - start_time

    save_evaluation_to_experiment(
        session,
        experiment_name,
        function_name=function_name,
        function_impl=function_impl,
        metric_name=metric_name,
        model_name=model_name,
        score=result.score,
        num_examples=len(result.details),
        eval_details=result.details,
        run_name=run_name,
        custom_metric_udf=custom_metric_udf or "",
        elapsed_seconds=elapsed,
        cost_info=result.cost_measurement,
        # Persist the per-row eval_detail.json artifact to the run's nested
        # stage (upload_details defaults to True) so the spec-driven eval path
        # stores results just like the optimization path — no more skipping.
        upload_details=True,
        # The YAML/EXECUTE EXPERIMENT path never creates the experiment: the
        # experiment object is created by the DDL layer before this SPROC runs,
        # so we only attach runs to it (an absent experiment surfaces as a run
        # add error rather than being silently created here).
        create_experiment_if_missing=False,
    )

    return {
        "run": run_name,
        "score": result.score,
        "num_examples": len(result.details),
    }


def _run_optimization(session: Session, experiment_name: str, spec: dict) -> dict:
    """Optimization path: GEPA-optimize the function against the dataset."""
    optimization = spec.get("optimization")
    if not isinstance(optimization, dict):
        raise ValueError("specification.optimization must be a mapping")
    models = optimization.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("specification.optimization.models must be a non-empty list")

    function_name, query_text = _resolve_function(spec)
    # Optimization is scoped to a single top-level AI_COMPLETE call: the prompt
    # it optimizes and the token/cost tracking are only well-defined for one
    # AI_COMPLETE. (Evaluation has no such restriction.)
    if query_text is not None:
        _validate_query_text_ai_complete(query_text)
    # The yaml experiment handler ships only body-mode optimization; prompt mode
    # is not in the deployed bundle. Reject any other mode with a clear error
    # rather than failing opaquely at mode dispatch.
    optimize_mode = optimization.get("optimize_mode")
    if optimize_mode is not None and str(optimize_mode).lower() != "body":
        raise ValueError(
            "specification.optimization.optimize_mode only supports 'body' "
            f"(got {optimize_mode!r})"
        )
    # Optimization always needs the input column set (candidate evaluation feeds
    # those columns to each candidate), so argument_mapping is required on both
    # the user-function and builtin ``query_text`` paths.
    training_table, input_columns, label_column, arg_keys = _resolve_dataset(spec)
    # ``dataset.name`` is a plain table/view, or a Snowflake DATASET object
    # materialized to a queryable temp view when a ``dataset.version`` is given.
    dataset = spec.get("dataset") or {}
    training_table = _resolve_dataset_source(
        session, training_table, dataset.get("version")
    )
    # Compile-check the builtin expression against the dataset (no AI calls) so a
    # malformed query_text fails with a clear, attributable error up front.
    if query_text is not None:
        _validate_query_text_compiles(session, query_text, training_table)
    input_arg_names = (
        _resolve_arg_param_names(session, function_name, arg_keys)
        if function_name is not None
        else None
    )
    metric_name, custom_metric_udf, _judge_model, metric_options = _resolve_metric(
        _first_metric(spec)
    )

    # Shared eval/opt protocol: a builtin optimizes under function_name = the
    # builtin's name (e.g. AI_COMPLETE); the optimizer records that name and
    # persists function_impl = each candidate's body (the query_text for the
    # seed). The name is also used for temp-object labels (advisory only).
    opt_function_name = function_name or _builtin_function_name(query_text)

    # reflection_model is required by run_optimization; default to a strong
    # Claude Opus model (independent of the models being optimized) so
    # reflection quality does not degrade when optimizing weak/cheap models.
    reflection_model = optimization.get("reflection_model") or "claude-opus-4-7"
    # Cheap up-front guard: reject optimize/reflection models unknown to the
    # shipped models.json (catches typos before the run starts).
    for _model in models:
        _validate_model_known(_model, field="optimization.models[]")
    _validate_model_known(reflection_model, field="optimization.reflection_model")
    # ``holdout_data`` is resolved identically to the training dataset: a plain
    # table/view verbatim, or a Snowflake DATASET materialized to a temp view
    # when a ``holdout_version`` is supplied. ``dataset`` was bound above when
    # resolving the training table.
    holdout = dataset.get("holdout_data")
    resolved_holdout = (
        _resolve_dataset_source(session, str(holdout), dataset.get("holdout_version"))
        if holdout
        else None
    )

    # Only pass optional knobs when present so run_optimization defaults apply.
    # (run_optimization already defaults upload_run_dir=False, so GEPA run_dir
    # status files are not persisted for the spec-driven path.) The run names
    # are engine-assigned (``SEED`` + ``ITER_<N>``); run_id is not caller-set,
    # so it is left unset and run_optimization auto-generates an internal label.
    # create_experiment_if_missing=False keeps this path from creating the
    # experiment — it must already exist (the DDL layer created it).
    opt_kwargs: dict[str, Any] = {
        "test_table": resolved_holdout,
        "metric_options": metric_options or None,
        "custom_metric_udf": custom_metric_udf,
        "experiment_name": experiment_name,
        "input_arg_names": input_arg_names,
        "create_experiment_if_missing": False,
        "fail_on_reflection_error": True,
    }
    # Thread the builtin expression so every optimize mode seeds its candidate
    # program from the query_text instead of introspecting a function DDL.
    if query_text is not None:
        opt_kwargs["query_text"] = query_text
    # Resolve the optimization budget. An omitted budget means ``auto``, and
    # ``auto`` may also be requested explicitly. ``auto`` is resolved to a
    # concrete preset via _AUTO_BUDGET_RESOLVES_TO (see its comment — the
    # mapping is an engine decision that may change). A concrete preset is
    # used as-is; anything else (including the legacy ``demo`` alias) is a
    # ValueError.
    budget = optimization.get("budget") or _AUTO_BUDGET
    if budget == _AUTO_BUDGET:
        resolved_budget = _AUTO_BUDGET_RESOLVES_TO
    elif budget in _VALID_BUDGETS:
        resolved_budget = budget
    else:
        raise ValueError(
            f"unsupported optimization budget {budget!r}; supported: "
            f"{_AUTO_BUDGET}, {', '.join(sorted(_VALID_BUDGETS))}"
        )
    opt_kwargs["auto_budget"] = resolved_budget
    # validation_fraction, temperature, max_tokens, and aggregation_metric are
    # intentionally not user-tweakable: run_optimization's defaults are always
    # used. optimize_mode is likewise not forwarded (only body mode is
    # supported, which is run_optimization's default).

    result = run_optimization(
        session,
        opt_function_name,
        training_table,
        label_column,
        input_columns,
        metric_name,
        models,
        reflection_model,
        **opt_kwargs,
    )

    # run_optimization returns {"status": "failed", ...} on total failure instead
    # of raising, so the try/except never fires. Check it explicitly and record a
    # FAILED SEED run rather than masking the failure as SUCCEEDED.
    if isinstance(result, dict) and str(result.get("status", "")).lower() in (
        "failed",
        "error",
    ):
        error_message = _surface_error(
            RuntimeError(str(result.get("error") or "optimization failed"))
        )
        fail_run(session, experiment_name, _SEED_RUN_NAME, error_message=error_message)
        return {
            "experiment": experiment_name,
            "run": _SEED_RUN_NAME,
            "status": "FAILED",
            "error_message": error_message,
        }

    out: dict[str, Any] = (
        dict(result) if isinstance(result, dict) else {"result": result}
    )
    out["experiment"] = experiment_name
    out["status"] = "SUCCEEDED"
    return out
