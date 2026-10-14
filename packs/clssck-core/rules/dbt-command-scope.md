---
description: Scope dbt build/run commands, keep --empty off upstream tables, and check hooks before a prod full refresh
condition:
  - '\bdbt\s+(?:build|run|test|seed|snapshot|clone)\b(?![^\n;&|]*\s(?:--select|-s|--selector)(?:[\s=]|$))'
  - '\bdbt\s+(?:build|run|seed|snapshot|clone)\b[^\n;&|]*\s--(?:empty|full-refresh)\b'
scope: "tool:bash"
interruptMode: always
---

A dbt command's blast radius is its selection. An unselected build can touch every model in the target; `--empty` and `--full-refresh` can replace stored data.

- MUST pass `--select`, `-s`, or `--selector` to `build`, `run`, `test`, `seed`, `snapshot`, and `clone`. Run the whole project only when the user asked for it. Preview a selection with `dbt ls --select <x>`.
- SHOULD use `dbt build` over `dbt run`: `run` skips tests. Keep `run` only for the project's documented per-layer pattern.
- `--empty` reads refs and sources as zero-row inputs; the materialization determines what is written. MUST use it only on explicitly selected models in a fresh or disposable schema. NEVER empty-run relations holding data you need. An upstream selector (`+x`, `2+x`, `@x`) includes parents: exclude relations to keep and preview the remaining selection.
- `x+` and `state:modified+` select downstream; only a leading `+` or `@` pulls in parents.
- An approved `--full-refresh` on a prod-like target drops and recreates tables. Before running it:
  - Read the project's `on-run-start` and `on-run-end` hooks; they run against that target too.
  - Read each selected model's `full_refresh` config (`false` blocks the refresh, `true` forces it).
  - Name the models and target you are about to refresh.
- After the refresh, compare row counts with what you recorded before, and run the tests on the same selection.
