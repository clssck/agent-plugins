<!-- Copyright (c) 2026 Snowflake Inc. All rights reserved.
     Licensed under the Snowflake Skills License.
     Refer to the LICENSE file in the root of this repository for full terms. -->

# Cortex AI Function Studio — Code Conventions

These conventions apply to all Python code in `cortex-ai-function-studio/`. They were established after a systematic audit of 43 silent failure patterns found in the GEPA optimizer pipeline (June 2026). AI agents editing this codebase should follow them strictly.

---

## 1. Exception Handling

### Never swallow exceptions silently

```python
# BAD — hides bugs, produces empty results with no explanation
try:
    rates = load_model_rates()
except Exception:
    pass

# BAD — logs once but still returns as if nothing happened
try:
    rates = load_model_rates()
except Exception:
    logger.warning("failed")
    return {}

# GOOD — log with full context, then decide: re-raise or return sentinel
try:
    rates = load_model_rates()
except Exception:
    logger.error(
        "load_model_rates failed — all cost estimates will be None, frontier will be empty",
        exc_info=True,
    )
    return None  # None signals failure; {} looks like "no rates configured"
```

### Catch the narrowest exception type that applies

```python
# BAD
except Exception:
    ...

# GOOD
except (KeyError, ValueError):
    ...

except snowflake.connector.errors.ProgrammingError:
    ...
```

Broad `except Exception` is only acceptable when:
- It wraps a boundary you do not control (third-party SDK, SQL execution)
- You **log at ERROR with `exc_info=True`** and either re-raise or return a clearly-typed sentinel

### Broad catches at top-level boundaries must log at ERROR

```python
# BAD — outer try/except that eats every failure and returns [] looks like "no results"
try:
    return _compute_pareto(candidates, val_scores)
except Exception:
    return []

# GOOD
try:
    return _compute_pareto(candidates, val_scores)
except Exception:
    logger.error(
        "compute_pareto_candidates failed unexpectedly; returning None so callers can distinguish failure from empty",
        exc_info=True,
    )
    return None
```

---

## 2. Return Values: Distinguish Failure from Empty

`[]` and `{}` mean "successfully computed an empty result". They must **not** be used to signal failure.

| Situation | Return |
|-----------|--------|
| Computation succeeded, result is empty | `[]` / `{}` |
| Computation failed (exception, missing data) | `None` |
| Computation partially succeeded | Return what succeeded + set a status field |

Callers must check for `None` explicitly:

```python
pareto = compute_pareto_candidates(...)
if pareto is None:
    logger.error("Pareto computation failed; skipping frontier assembly")
    # do not silently replace pre-computed candidates with None
elif pareto:
    _pareto_candidates = pareto
# if pareto == [] — legitimately empty, log at INFO
```

---

## 3. Status Fields Must Reflect Reality

### SPROC / job output status

Never hardcode `"status": "completed"` or `"status": "success"`. Status must be derived from actual outcomes:

```python
# BAD
output["status"] = "completed"  # always

# GOOD
if all_models_failed:
    output["status"] = "failed"
elif not frontier_candidates:
    output["status"] = "partial"  # models ran but frontier is empty
else:
    output["status"] = "completed"
```

Allowed values: `"completed"` | `"partial"` | `"failed"`

### Wrapper layers must propagate inner status

```python
# BAD — run.py always says success regardless of SPROC output
return {"status": "success", "result": sproc_result}

# GOOD — check inner status, validate shape, propagate failures
inner = parse_sproc_result(sproc_result)
if inner is None or inner.get("status") == "failed":
    return {"status": "failed", "error": "SPROC returned failure", "result": inner}
if not inner.get("frontier_candidates"):
    return {"status": "partial", "result": inner}
return {"status": "completed", "result": inner}
```

---

## 4. Add Diagnostic Fields to Outputs

When a computation was attempted but produced no result, add a sibling field explaining why. Never leave the consumer to guess.

```python
# BAD — empty frontier with no explanation
output["frontier_candidates"] = []

# GOOD — empty frontier with machine-readable reason
output["frontier_candidates"] = []
output["frontier_status"] = "empty"
output["frontier_error"] = "load_model_rates returned None; cost estimation unavailable"
```

Fields to add at key boundaries:

| Boundary | Field | Values |
|----------|-------|--------|
| Per-model test-eval | `test_eval_status` | `"success"` / `"failed"` / `"skipped"` |
| Frontier assembly | `frontier_status` | `"ok"` / `"empty"` / `"cost_unavailable"` |
| Pareto computation | `pareto_status` | `"ok"` / `"failed"` / `"partial"` |
| Run wrapper | `status` | `"completed"` / `"partial"` / `"failed"` |

---

## 5. Validate Data Shape Before Indexing

Always validate that parallel arrays have matching lengths before indexing into them.

```python
# BAD — IndexError if val_scores is shorter than candidates
for i, candidate in enumerate(candidates):
    score = val_scores[i]

# GOOD
if len(val_scores) != len(candidates):
    logger.error(
        "val_scores length %d != candidates length %d; cannot assign scores",
        len(val_scores), len(candidates),
    )
    return None

for i, candidate in enumerate(candidates):
    score = val_scores[i]
```

---

## 6. None-Coercion: Treat Missing as Missing, Not Zero

```python
# BAD — missing cost looks like "free"
input_cost = rates.get("input_cost", 0)

# GOOD — missing cost surfaces as None; callers can decide
input_cost = rates.get("input_cost")
if input_cost is None:
    logger.error("input_cost missing from rates for model %s — cost will be None, candidate may be dropped from frontier", model_id)
```

When `None` propagates to a calculation that requires a number, fail explicitly rather than substituting `0` or `float("inf")` without logging.

---

## 7. Log at the Right Level

| Situation | Level |
|-----------|-------|
| Expected, recoverable (retry, fallback) | `WARNING` |
| Unexpected but contained (one candidate dropped) | `WARNING` |
| Unexpectedly empty result that looks like success | `ERROR` |
| Fatal to the pipeline (no frontier possible) | `ERROR` |
| Broad exception caught at a boundary | `ERROR` with `exc_info=True` |

Never use `WARNING` for conditions that silently cause empty or wrong outputs. If the user would be confused by the result, it's `ERROR`.

---

## 8. Run Name Format Consistency

Run names must use a single canonical format. Do not mix formats between write and read paths.

```python
# BAD — writer uses "ITER_5", reader checks for "_ITER_"
run_name = f"ITER_{iteration}"          # writer
if "_ITER_" in run_name: ...            # reader — never matches "ITER_5"

# GOOD — use make_run_name() everywhere, or define one format constant
RUN_NAME_RE = re.compile(r"(?:.*_)?ITER_(\d+)$")
```

---

## Cross-references

- Silent failures audit: `/.cursor/plans/pareto-frontier-silent-failures-audit.md` (repo root)
- Google Python Style Guide: https://google.github.io/styleguide/pyguide.html
