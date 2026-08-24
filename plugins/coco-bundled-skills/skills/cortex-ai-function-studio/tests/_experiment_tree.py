# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Build a JSON tree of an optimization experiment for logging + assertions.

The tree mirrors the Snowflake experiment structure the optimizer writes::

    {
      "<experiment_name>": {
        "<run_name>": {
          "metrics":    {"valset_score": 0.6, "is_frontier": 1, ...},  # numbers
          "parameters": {"run_type": "seed", "model": "...", ...},  # strings
          "metadata":   {"status": "FINISHED", ...}  # from SHOW RUNS
        },
        ...
      }
    }

The e2e test builds this tree and makes specific per-scenario assertions on it
(SEED exists with the input model, non-SEED runs are ``ITER_<N>`` with a known
``run_type``, etc.) — those deterministic checks are the validation, so no
separate structural JSON-schema pass is needed.

Used by ``tests/test_optimize_input_types_e2e.py`` (live) and unit-tested by
``tests/test_experiment_tree.py`` (offline, with a fake session).
"""

from __future__ import annotations

import json
from typing import Any

# --------------------------------------------------------------------------- #
# Row helpers (duck-typed over Snowpark Row / plain dicts)
# --------------------------------------------------------------------------- #


def _row_as_dict(row: Any) -> dict[str, Any]:
    """Normalize a result row to a lower-cased-key plain dict."""
    if isinstance(row, dict):
        raw = row
    elif hasattr(row, "as_dict"):
        raw = row.as_dict()
    elif hasattr(row, "asDict"):
        raw = row.asDict()
    else:  # pragma: no cover - defensive
        raw = dict(row)
    return {str(k).lower(): v for k, v in raw.items()}


def _name_value_pairs(rows: list[Any]) -> dict[str, Any]:
    """Collapse SHOW RUN PARAMETERS / METRICS ``name``/``value`` rows to a dict."""
    out: dict[str, Any] = {}
    for row in rows:
        d = _row_as_dict(row)
        if "name" in d:
            out[str(d["name"])] = d.get("value")
    return out


def _coerce_number(value: Any) -> float | int | None:
    """Coerce a metric value to a number; return None if not numeric."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        text = str(value).strip()
        if text == "":
            return None
        num = float(text)
        return int(num) if num.is_integer() else num
    except (TypeError, ValueError):
        return None


def _json_safe_scalar(value: Any) -> Any:
    """Reduce a metadata value to a JSON-safe scalar (str/number/bool/None)."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _extract_metadata(run_row: dict[str, Any]) -> dict[str, Any]:
    """Build a run's metadata dict from its SHOW RUNS row.

    The SHOW RUNS ``metadata`` column is a JSON blob (e.g. ``{"status": ...}``);
    parse it when present.  Also surface a top-level ``status`` column if the
    server returns one.  Everything is reduced to JSON-safe scalars so the tree
    serializes cleanly and validates as an object.
    """
    metadata: dict[str, Any] = {}
    raw = run_row.get("metadata")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                metadata.update(
                    {str(k): _json_safe_scalar(v) for k, v in parsed.items()}
                )
        except json.JSONDecodeError:
            metadata["metadata"] = raw
    elif isinstance(raw, dict):
        metadata.update({str(k): _json_safe_scalar(v) for k, v in raw.items()})
    if "status" not in metadata and run_row.get("status") is not None:
        metadata["status"] = _json_safe_scalar(run_row["status"])
    return metadata


# --------------------------------------------------------------------------- #
# Tree builder + validation
# --------------------------------------------------------------------------- #


def build_experiment_tree(session: Any, experiment_name: str) -> dict[str, Any]:
    """Read a Snowflake experiment into the JSON tree described in the module docstring.

    Issues ``SHOW RUNS IN EXPERIMENT`` then, per run, ``SHOW RUN PARAMETERS`` and
    ``SHOW RUN METRICS``.  Metric values are coerced to numbers; parameter values
    to strings; metadata comes from the SHOW RUNS row.
    """
    tree: dict[str, Any] = {experiment_name: {}}
    runs = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
    for run in runs:
        run_row = _row_as_dict(run)
        run_name = str(run_row["name"])

        param_rows = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        parameters = {k: str(v) for k, v in _name_value_pairs(param_rows).items()}

        metric_rows = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        metrics = {
            k: num
            for k, v in _name_value_pairs(metric_rows).items()
            if (num := _coerce_number(v)) is not None
        }

        tree[experiment_name][run_name] = {
            "metrics": metrics,
            "parameters": parameters,
            "metadata": _extract_metadata(run_row),
        }
    return tree


def render_experiment_tree(tree: dict[str, Any]) -> str:
    """Pretty-print the tree as sorted, indented JSON for logging/display."""
    return json.dumps(tree, indent=2, sort_keys=True, default=str)
