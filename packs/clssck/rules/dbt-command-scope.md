---
description: Scope dbt build/run commands, keep --empty off upstream tables, and check hooks before a prod full refresh
condition:
  - "\\bdbt\\s+(?:build|run|test|seed|snapshot|clone)(?![-\\w])"
scope: "tool:bash"
interruptMode: always
---

A dbt command's blast radius is its selection. An unselected build can touch every model in the target; `--empty` and `--full-refresh` can replace stored data.

## Select first

MUST pass `--select`, `-s`, or `--selector` to `build`, `run`, `test`, `seed`, `snapshot`, and `clone`. Run the whole project only when the user asked for it. Preview a selection with `dbt ls --select <x>`.

```bash
# Bad
dbt build
dbt run --select fct_orders

# Good
dbt ls --select fct_orders+
dbt build --select fct_orders+
```

## Graph direction

|Selector|Direction|Pulls in parents (only a leading `+` or `@`)|
|---|---|---|
|`x+`, `state:modified+`|downstream|no|
|`+x`, `2+x`|upstream|yes|
|`@x`|includes parents|yes|

## `--empty`

`--empty` reads refs and sources as zero-row inputs; the materialization determines what is written.

- MUST use it only on explicitly selected models in a fresh or disposable schema.
- NEVER empty-run relations holding data you need.
- An upstream selector (`+x`, `2+x`, `@x`) includes parents: exclude relations to keep and preview the remaining selection.

```bash
# Bad — +fct_orders also empty-runs every parent
dbt build --select +fct_orders --empty

# Good — exclude relations to keep, preview, then run
dbt ls --select +fct_orders --exclude stg_payments
dbt build --select +fct_orders --exclude stg_payments --empty
```

## `--full-refresh`

An approved `--full-refresh` (short form `-f`) on a prod-like target drops and recreates tables. Before running it:

1. Read the project's `on-run-start` and `on-run-end` hooks; they run against that target too.
2. Read each selected model's `full_refresh` config (`false` blocks the refresh, `true` forces it).
3. Name the models and target you are about to refresh.

Afterwards, compare row counts with what you recorded before, and run the tests on the same selection.

```bash
dbt build --select fct_orders --target prod --full-refresh
dbt test --select fct_orders --target prod
```

## Prefer

Prefer `dbt build` over `dbt run`: `run` skips tests. Keep `run` only for the project's documented per-layer pattern.

## Exceptions

- A command that already passes `--select`, `-s`, or `--selector` and uses neither `--empty` nor `--full-refresh` (`-f`) is compliant; no change or extra permission is needed.
- Read-only inspection such as `dbt ls`, and literal examples in echoed text or docs, need no correction. `dbt run-operation` executes a macro that can mutate the target and `dbt compile` can run introspective queries; they fall outside this trigger but are not automatically harmless, so judge them by what they actually do.
- A whole-project run the user explicitly requested is compliant.

This reminder can appear for compliant commands, and a missing reminder does not authorize an unscoped run. Apply these checks to every dbt execution, including ones started through wrappers.
