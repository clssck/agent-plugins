# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

r"""Golden-file (snapshot) helpers for the YAML-handler e2e tests.

The YAML handler (``execute_ai_function_eval_opts``) takes a SPEC YAML as input
and writes a Snowflake Experiment.  The e2e tests drive it with many eval/opt
SPECs and verify each resulting Experiment against a committed *golden* YAML
"output ref".  Because the runs are produced by live AI calls, the raw result is
nondeterministic (scores, timings, token counts, GEPA iteration count, and the
run-key-tainted db/schema/object names all vary run to run).  This module turns
a Snowflake experiment tree + the handler's return dict into a **deterministic**
representation so a golden comparison is stable:

* **Tokenize** — env-specific substrings (db, schema, run key, and the fully
  qualified function / table / experiment names) are replaced with stable
  tokens (``__DB__`` / ``__FUNCTION__`` / ``__TABLE__`` / ``__EXP__`` / ...), so
  the golden does not embed a particular run's object names.
* **Redact** — volatile *values* (scores, timings, token counts, cost, GEPA
  bookkeeping) are dropped; only a curated set of deterministic parameters keep
  their value.  Metric/parameter **key sets** are retained (curated) because the
  set of keys a run records is part of the handler's contract even though the
  values are not.
* **Split by determinism** — an evaluation writes a deterministic run set
  (``EVAL_1``, or ``EVAL_1..N`` for ``num_eval_runs`` > 1), so every run is
  snapshotted by its exact name.  An optimization writes one ``SEED`` run plus a
  *nondeterministic* number of ``ITER_<N>`` runs (an ultra-light run can commit
  zero), so only the deterministic ``SEED`` is snapshotted; the iteration runs
  are verified *structurally* (name / run_type / status) via
  :func:`summarize_iteration_runs` rather than pinned in the golden. Their
  metric/param key sets are therefore NOT snapshotted for optimization.

The offline unit tests in ``tests/test_experiment_golden.py`` exercise every
function here against fake trees (no Snowflake); the live e2e driver in
``tests/test_yaml_handler_golden_e2e.py`` records / verifies the goldens.

Recording: set ``UPDATE_EXPERIMENT_GOLDEN=1`` when running the e2e suite to
(re)write the golden files instead of comparing against them.
"""

from __future__ import annotations

import difflib
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

# Environment variable that switches the helpers from *verify* to *record*.
UPDATE_ENV = "UPDATE_EXPERIMENT_GOLDEN"

# Tokens for collapsed values.
VARIES_TOKEN = "<varies>"
NONE_TOKEN = "<none>"

# The single deterministic optimization run name (the seed candidate).
SEED_RUN_NAME = "SEED"

# Copyright header prepended to every golden file (the repo's copyright-check
# gate requires it on all shipped files, including generated goldens). It is a
# YAML comment, so it is ignored on parse. dump_golden emits it and the goldens
# are recorded through dump_golden, so the recorded and verified text match.
_GOLDEN_HEADER = (
    "# Copyright (c) 2026 Snowflake Inc. All rights reserved.\n"
    "# Licensed under the Snowflake Skills License.\n"
    "# Refer to the LICENSE file in the root of this repository for full terms.\n"
)

# ---------------------------------------------------------------------------
# Curated deterministic view
# ---------------------------------------------------------------------------
# Parameters whose *value* is deterministic (given the SPEC + dataset) after
# tokenization — recorded verbatim in the golden.
_STABLE_VALUE_PARAMS = frozenset(
    {
        "run_type",
        "model",
        "iteration",
        "is_full_eval",
        "status",
        "metric_name",
        "custom_metric_udf",
        "function_name",
        "experiment_schema_version",
    }
)
# Parameters whose *presence* is a stable part of the contract but whose value
# is volatile (a GEPA-rewritten body, summed bookkeeping, a JSON blob, the
# global iteration counter, or a per-run example count that depends on the
# optimizer's val/train split). We keep the KEY (in ``param_keys``) but never
# the value. Deliberately excludes conditionally-populated fields
# (reflection_model, rejection_*, parent_candidate, ...) so the key set stays
# deterministic. The deterministic eval row count is still asserted via the
# handler result's ``num_examples`` (see :func:`_normalize_result`).
_KEY_ONLY_PARAMS = frozenset(
    {
        "function_impl",
        "global_iteration",
        "per_model_stats",
        "total_candidates",
        "num_examples",
    }
)
_CURATED_PARAM_KEYS = _STABLE_VALUE_PARAMS | _KEY_ONLY_PARAMS

# Metric keys that are a stable part of the contract (values always redacted).
# ``is_frontier`` and ``test_score`` are deliberately excluded — they are
# frontier-contingent (``test_score`` is only stamped on the final-frontier
# candidate, and ``is_frontier`` may be retroactively cleared when a better
# iteration run supersedes SEED) and would flake on an otherwise-correct run.
_CURATED_METRIC_KEYS = frozenset(
    {
        "score",
        "estimated_cost",
        "avg_prompt_tokens",
        "avg_completion_tokens",
        "valset_score",
    }
)


# ---------------------------------------------------------------------------
# Tokenization
# ---------------------------------------------------------------------------
Tokenizer = Callable[[Any], Any]


def make_tokenizer(replacements: dict[str, str]) -> Tokenizer:
    """Build a callable that rewrites env-specific substrings to stable tokens.

    ``replacements`` maps a concrete substring (a db name, a fully qualified
    object name, the run key, ...) to its stable token. Longer substrings are
    applied first so a fully qualified name is tokenized before its bare db /
    schema components, and matching is case-insensitive (Snowflake upper-cases
    identifiers, but SPEC text may not). Non-string values pass through
    unchanged.
    """
    items = sorted(
        ((src, tok) for src, tok in replacements.items() if src),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    # Guard against double-substitution: replacements are applied sequentially,
    # so if one entry's token contained *another* entry's source string, that
    # already-substituted token could be re-matched and corrupted. Tokens are
    # ``__X__`` and sources are real object names, so this never holds in
    # practice — assert it so a future naming choice can't silently break
    # goldens. (A source appearing in its OWN token is fine — it is not
    # re-matched after its single pass.)
    for i, (_src_i, tok_i) in enumerate(items):
        for j, (src_j, _tok_j) in enumerate(items):
            if i != j and src_j.lower() in tok_i.lower():
                raise ValueError(
                    f"tokenizer source {src_j!r} is a substring of a different "
                    f"replacement's token {tok_i!r}; this risks double-substitution"
                )
    compiled = [(re.compile(re.escape(src), re.IGNORECASE), tok) for src, tok in items]

    def tokenize(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        out = value
        for pattern, tok in compiled:
            out = pattern.sub(tok, out)
        return out

    return tokenize


# ---------------------------------------------------------------------------
# Per-run / per-group normalization
# ---------------------------------------------------------------------------


def _normalize_run(
    body: dict[str, Any],
    tokenize: Tokenizer,
    stable_value_params: frozenset[str],
) -> dict[str, Any]:
    """Reduce a single run body to its curated, deterministic golden entry.

    ``stable_value_params`` is the subset of curated params whose *value* is
    kept (tokenized); the rest of the curated params contribute only their key
    (see :data:`_CURATED_PARAM_KEYS`). It varies by job kind — see
    :func:`build_golden`.
    """
    parameters = body.get("parameters", {}) or {}
    metrics = body.get("metrics", {}) or {}
    metadata = body.get("metadata", {}) or {}

    params = {
        key: tokenize(str(parameters[key]))
        for key in parameters
        if key in stable_value_params
    }
    param_keys = sorted(k for k in parameters if k in _CURATED_PARAM_KEYS)
    metric_keys = sorted(k for k in metrics if k in _CURATED_METRIC_KEYS)
    run_type = parameters.get("run_type")
    status = metadata.get("status")
    return {
        "count": 1,
        "run_types": [run_type if run_type is not None else NONE_TOKEN],
        "statuses": [status if status is not None else NONE_TOKEN],
        "params": dict(sorted(params.items())),
        "param_keys": param_keys,
        "metric_keys": metric_keys,
    }


_ITER_NAME_RE = re.compile(r"^ITER_\d+$")
_ITER_RUN_TYPES = frozenset({"iteration", "rejected"})
# An accepted / frontier candidate is committed (FINISHED); a rejected
# candidate's run is left uncommitted (RUNNING). Both are expected; any other
# state (FAILED, ABORTED, ...) is a contract violation.
_ITER_ALLOWED_STATUSES = frozenset({"FINISHED", "RUNNING"})


def summarize_iteration_runs(
    tree: dict[str, Any], experiment_name: str
) -> dict[str, Any]:
    """Summarize + contract-check an optimization's non-SEED (``ITER_<N>``) runs.

    An optimization writes one ``SEED`` run plus a *nondeterministic* number of
    ``ITER_<N>`` runs (an ultra-light run can commit zero of them), so the
    iteration runs are NOT snapshotted in the golden — pinning their count /
    presence would flake. Instead the e2e test asserts they are all well-formed
    against this summary: every non-SEED run must be named ``ITER_<n>``, carry a
    ``run_type`` of ``iteration`` or ``rejected``, and be in an expected state
    (``FINISHED`` for an accepted/frontier candidate, ``RUNNING`` for a rejected
    one that is never committed).

    Returns ``{count, run_types, statuses, violations}``; ``violations`` is
    empty when every non-SEED run satisfies the contract (a count of zero — a
    run whose seed was never beaten — is allowed).
    """
    runs = tree.get(experiment_name, {})
    names = [name for name in runs if name != SEED_RUN_NAME]
    run_types: set[str] = set()
    statuses: set[str] = set()
    violations: list[str] = []
    for name in names:
        body = runs[name]
        parameters = body.get("parameters", {}) or {}
        metadata = body.get("metadata", {}) or {}
        if not _ITER_NAME_RE.match(name):
            violations.append(f"non-SEED run {name!r} is not named ITER_<n>")
        run_type = parameters.get("run_type")
        if run_type is not None:
            run_types.add(str(run_type))
        if run_type not in _ITER_RUN_TYPES:
            violations.append(
                f"run {name!r} run_type={run_type!r} not in {sorted(_ITER_RUN_TYPES)}"
            )
        status = metadata.get("status")
        if status is not None:
            statuses.add(str(status))
        if status not in _ITER_ALLOWED_STATUSES:
            violations.append(
                f"run {name!r} status={status!r} not in {sorted(_ITER_ALLOWED_STATUSES)}"
            )
    return {
        "count": len(names),
        "run_types": sorted(run_types),
        "statuses": sorted(statuses),
        "violations": violations,
    }


# ---------------------------------------------------------------------------
# Handler-result normalization
# ---------------------------------------------------------------------------


def _normalize_result(
    job_kind: str, result: dict[str, Any], tokenize: Tokenizer
) -> dict[str, Any]:
    """Reduce the handler's return dict to its deterministic fields.

    Both paths keep ``status`` and the tokenized ``experiment``. Evaluation
    additionally keeps the run name(s), ``num_examples`` and the metric key set
    (scores redacted); optimization keeps only whether a best score was
    reported (the score value itself is nondeterministic).
    """
    out: dict[str, Any] = {"status": result.get("status")}
    if result.get("experiment") is not None:
        out["experiment"] = tokenize(str(result["experiment"]))

    if job_kind == "evaluation":
        if "run" in result:
            out["run"] = tokenize(str(result["run"]))
        if "runs" in result:
            out["runs"] = sorted(tokenize(str(r)) for r in result["runs"])
        if "num_examples" in result:
            out["num_examples"] = result["num_examples"]
        metrics = result.get("metrics")
        if isinstance(metrics, dict):
            # Single-run evals return a flat ``{metric_name: score}``; multi-run
            # evals nest by run name ``{run_name: {metric_name: score}}``. Use
            # the presence of ``"runs"`` in the result (not value-type inspection)
            # to distinguish, so dict-valued metrics on a single-run eval cannot
            # corrupt metric_keys.
            if "runs" in result:
                names = {
                    mk
                    for inner in metrics.values()
                    if isinstance(inner, dict)
                    for mk in inner
                }
            else:
                names = set(metrics)
            out["metric_keys"] = sorted(str(k) for k in names)
    else:  # optimization
        best = result.get("overall_best_score")
        if best is None:
            best = result.get("overall_best_val_score")
        out["best_score_present"] = best is not None
    return out


# ---------------------------------------------------------------------------
# Golden document
# ---------------------------------------------------------------------------


def build_golden(
    *,
    job_kind: str,
    result: dict[str, Any],
    tree: dict[str, Any],
    experiment_name: str,
    tokenize: Tokenizer,
    spec_judge_model: str | None = None,
) -> dict[str, Any]:
    """Assemble the deterministic golden document for one handler run.

    ``job_kind`` is ``"evaluation"`` or ``"optimization"`` (dispatch mirrors the
    handler's own SPEC dispatch).

    ``spec_judge_model`` — when the SPEC explicitly sets ``judge_model``, pass
    the value here so the golden asserts it (the value is SPEC-determined and
    therefore stable). When omitted the eval path records
    ``LLM_JUDGE_DEFAULT_MODEL`` (an external constant) whose value is redacted
    (key retained).

    * **evaluation** — every run is snapshotted by its exact name (the run set
      is deterministic: ``EVAL_1`` for a single run, ``EVAL_1..N`` for
      ``num_eval_runs`` > 1).
    * **optimization** — only the deterministic ``SEED`` run is snapshotted. The
      ``ITER_<N>`` runs have a nondeterministic count (an ultra-light run can
      commit zero) and so are verified structurally via
      :func:`summarize_iteration_runs` rather than pinned here.
    """
    if job_kind not in ("evaluation", "optimization"):
        raise ValueError(f"unknown job_kind {job_kind!r}")
    runs = tree.get(experiment_name, {})
    # The eval path records the run's ``model`` param as the resolved
    # ``LLM_JUDGE_DEFAULT_MODEL`` (an external constant) whenever the SPEC omits
    # ``judge_model`` — so its *value* is not SPEC-determined and is redacted
    # (key retained). When the SPEC explicitly sets ``judge_model`` the value IS
    # stable and should be asserted.
    # For optimization ``model`` is always the SPEC's own optimize model.
    if job_kind == "evaluation" and spec_judge_model is None:
        stable_value_params = _STABLE_VALUE_PARAMS - {"model"}
    else:
        stable_value_params = _STABLE_VALUE_PARAMS
    if job_kind == "evaluation":
        norm_runs = {
            name: _normalize_run(body, tokenize, stable_value_params)
            for name, body in runs.items()
        }
    else:  # optimization: snapshot only the deterministic SEED run
        norm_runs = {}
        if SEED_RUN_NAME in runs:
            norm_runs[SEED_RUN_NAME] = _normalize_run(
                runs[SEED_RUN_NAME], tokenize, stable_value_params
            )
    return {
        "job_kind": job_kind,
        "result": _normalize_result(job_kind, result, tokenize),
        "runs": dict(sorted(norm_runs.items())),
    }


def dump_golden(golden: dict[str, Any]) -> str:
    """Serialize a golden document to canonical (sorted-key) YAML text.

    Prepends the repo copyright header (a YAML comment, ignored on parse) so the
    recorded golden files satisfy the copyright-check gate.
    """
    body = yaml.safe_dump(golden, sort_keys=True, default_flow_style=False)
    return f"{_GOLDEN_HEADER}\n{body}"


def verify_or_record(golden_path: Path, produced: dict[str, Any]) -> None:
    """Compare ``produced`` against the golden file, or record it.

    With ``UPDATE_EXPERIMENT_GOLDEN`` set in the environment the golden file is
    (re)written and the call returns. Otherwise the produced document is
    compared against the committed golden and an :class:`AssertionError` with a
    unified diff is raised on any mismatch (or when the golden is missing).
    """
    text = dump_golden(produced)
    if os.environ.get(UPDATE_ENV):
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(text, encoding="utf-8")
        return
    if not golden_path.exists():
        raise AssertionError(
            f"golden ref {golden_path} does not exist; rerun with "
            f"{UPDATE_ENV}=1 to record it.\n--- produced ---\n{text}"
        )
    expected = golden_path.read_text(encoding="utf-8")
    if expected != text:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"{golden_path.name} (golden)",
                tofile="produced",
            )
        )
        raise AssertionError(
            f"experiment golden mismatch for {golden_path.name}:\n{diff}\n"
            f"If this change is expected, rerun with {UPDATE_ENV}=1 to update."
        )
