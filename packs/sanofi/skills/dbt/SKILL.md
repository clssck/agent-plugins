---
name: dbt
description: "Build, review, test, and run Sanofi dbt Core projects on Snowflake. Use when working with models, sources, snapshots, seeds, incremental design, data and unit tests, docs and meta, contracts and versions, selectors, state:modified CI, upgrades and deprecations, failed-run triage, Elementary, WAP, feature flags, or native snow dbt. Not for generic dbt-on-Snowflake mechanics — dbt-projects-on-snowflake; ODCS contracts — datacontract-writing; DAGs — sanofi-airflow."
---

# Sanofi dbt

Sanofi conventions for dbt project structure, model development, documentation, testing (data and unit), incremental design, snapshots, contracts and versions, state/CI, upgrades, Elementary/DQ, WAP, and approval-gated Snowflake-native execution. The real project is the specification: names, layout, grain keys, columns, aliases, materializations, tags, sources, and test scope come from its files and manifests, never from examples here. Generic review and security stay with `/review` and `/security`.

Every command that writes to Snowflake rebuilds whatever it selects, so scope precedes execution and the narrowest proving command precedes any broad one.

## Ground Rules

- **Inspect first.** MUST read the real dbt project before writing; derive every name and setting from files and manifests.
- **Examples are patterns.** NEVER copy example names verbatim.
- **Standards precedence, high → low:** target repo's documented contract, config, conventions › applicable approved/current team standard › cross-space standards › Draft/WIP guidance (advisory only). NEVER let a lower rank override a higher one. Applicability, approval, currency, or conflict unclear → ask first; surface conflicts, never resolve them silently.
- **Modern syntax.** A legacy-style file is no reason to write legacy syntax. Write the form the resolved dbt version accepts without warning; old form only where that version requires it (table below).
- **Incremental change signals.** Every joined parent MUST have one: lookback, affected-key re-derivation, `on_schema_change`, periodic refresh. Design it before writing the filter → [snowflake-materializations.md](references/snowflake-materializations.md#late-arriving-and-multi-parent-changes). Strategy MUST be valid on Snowflake; `full_refresh` behavior understood.
- **Grain key.** Documented, tested (`unique` + `not_null`), matching the model SQL.
- **Native execution.** Native-project steps need authorization; NEVER force deploy, drop, or change a schedule without approval.

## Routing

| Request | `read` first |
|---|---|
| Explicit `snow dbt`, `EXECUTE DBT PROJECT`, deployed `DBT PROJECT` object, native migration, native `env.yml`, `semantic_view`/`dbt_semantic_view` | [snowflake-native-dbt.md](references/snowflake-native-dbt.md) |
| Structure, placement, naming, layer defaults, sources/snapshots/seeds/exposures, tags, development practice | [general-dbt-guide.md](references/general-dbt-guide.md) |
| Setup, uv, profiles and secrets, `dbt_project.yml` baseline, packages, deprecations (1.10+) | [project-setup.md](references/project-setup.md) |
| Elementary, query comment, feature flags, WAP | [operations.md](references/operations.md) |
| Materialization choice, incremental design, late-arriving data, merge errors, `copy_grants`, transient, dynamic tables | [snowflake-materializations.md](references/snowflake-materializations.md) |
| Unit tests, `--empty`, mocking inputs, `is_incremental` overrides | [unit-tests.md](references/unit-tests.md) |
| Selectors, `state:modified`, `--defer`, `dbt clone`, CI jobs, PR schemas | [state-and-ci.md](references/state-and-ci.md) |
| Contracts, constraints, model versions, `access`, `group`, `deprecation_date` | [contracts-and-versions.md](references/contracts-and-versions.md) |
| Upgrading dbt, deprecations, behavior flags | [upgrading.md](references/upgrading.md) |
| Failed run, error triage, exit codes, `run_results.json`, flaky test | [troubleshooting.md](references/troubleshooting.md) |
| Model/column descriptions, source metadata, tags, `meta` | [writing-documentation.md](references/writing-documentation.md) |
| Adding or auditing data tests, coverage vs cost, DQ report triage | [writing-data-tests.md](references/writing-data-tests.md) |

- **Adapter ≠ native.** NEVER route ordinary dbt Core work to the native reference just because the adapter is Snowflake.
- **Docs/tests plus placement, Elementary, orchestration, or package change** → add `general-dbt-guide.md` (and `project-setup.md` or `operations.md` as routed).
- **Scope splits:** ODCS data contracts → datacontract-writing. DAG authoring → sanofi-airflow. Generic dbt-on-Snowflake mechanics → dbt-projects-on-snowflake.
- **Multi-area order:** placement and naming → SQL and materialization → docs and properties → tests → selectors, CI, run commands.
- **Docs before tests** when both requested. Docs exist → check documented grain matches the model, then tests.

## Version-Sensitive Rules

Confirm engine and version with `dbt --version` before applying any row.

| Rule | Check before applying |
|---|---|
| Test params under `arguments:` | dbt >= 1.10.8: nest (flag defaults `true`, top-level warns). 1.10.5-1.10.7: nest only if `require_generic_test_arguments_property: true` is set, else the nested form warns (`ArgumentsPropertyInGenericTestDeprecation`); older: top-level |
| Engine and install | The bare `dbt` PyPI package is dbt v2 (since 2026-09-14), so a 1.x project installs `dbt-core` + `dbt-snowflake` with uv ([project-setup.md](references/project-setup.md#setup-and-environment)). Run `dbt --version` before trusting parse or test output; upgrade steps in [upgrading.md](references/upgrading.md) |
| Custom keys, `meta`, `tags`, `freshness`, `docs`, `group`, `access` | dbt >= 1.10: under `config:` (custom keys only in `config.meta`); top-level forms warn |
| `microbatch` incremental | dbt >= 1.9; needs `event_time` on model and filtered parents, `begin`, `batch_size`; NEVER add `is_incremental()` |
| Snapshot deletes | dbt >= 1.9: `hard_deletes: invalidate\|new_record` replaces `invalidate_hard_deletes` |
| `dbt-snowflake` < 1.10.6 | Can break incrementals with `sync_all_columns` and collated strings after Snowflake's column-size change; upgrade |
| `insert_overwrite` on Snowflake | Truncates and reloads the whole table; NEVER use as partition replace on history-bearing models |
| `latest_version_pointer` | dbt >= 1.12; collides (`dbt1005`) with a latest version aliased to the model name |
| `dbt_semantic_view` | Verify its required dbt range against the project's resolved version before using it |
| `DBT_ENV_SECRET_*` | Only in `profiles.yml` and `packages.yml`; NEVER in sources, macros, vars, SQL |
| `--full-refresh` vs `full_refresh: false` | Config wins; the flag does not override `false` |
| Unit test YAML | Under `model-paths`, NEVER `tests/` |
| Native `snow dbt` | Re-verify CLI minimums, flags, and the `DBT_VERSION` pin against current Snowflake docs |
| Deprecation warnings | None new; fix, never silence as the fix |

## Command Scope

- **Select every mutation.** MUST select every `dbt build|run|test|seed|snapshot|clone` with `--select`/`-s`, `--selector`, or `state:modified+ --state <dir>`. Bare invocation only when the user explicitly asked for a full build; say so when running it. `-m`/`--models` deprecated; where ignored, the whole DAG builds.
- **Preview non-trivial selectors.** `dbt ls --select "<selector>" --resource-type model --warn-error-options '{"error": ["NoNodesForSelectionCriteria"]}'` → a typo fails instead of building nothing.
- **`--empty` blast radius.** Refs and sources read zero rows; selected tables and views rebuild empty; an existing incremental gets a zero-row incremental run. Only on the target model or its parents, or explicitly scoped incremental models, and only in a fresh or disposable CI schema (parents: `--select "1+<model>" --exclude "<model>"`). NEVER aim it at data-bearing relations or pair it with an unchecked `+` upstream selector.
- **Prod or `--full-refresh`.** Confirm explicit user approval for that target and selection first. Read the `on-run-start`/`on-run-end` hooks in `dbt_project.yml` (they run on `build`, `run`, `test`, `seed`, `snapshot`) and the model's `full_refresh` config. Afterwards verify row counts against a pre-run count (or Time Travel) and run the model's tests.
- **Prefer `dbt build`** (models + tests + unit tests, lineage order) over `dbt run`. Exception: the documented per-layer `dbt run` + `dbt test` orchestration pattern ([state-and-ci.md](references/state-and-ci.md#gates)); NEVER mix patterns in one pipeline.
- **Inspect data with `dbt show`**, not ad-hoc Python:

```bash
dbt show --select <model> --limit 10
dbt show --inline "select ... from {{ ref('x') }}" --limit 10
```

`--limit`, not SQL `LIMIT`; `--select` takes one node. `--inline` runs any SQL → read-only role.
- **uv projects:** `uv run dbt ...`; one untracked `uv.lock` is not part of the task.

## Verification

Smallest command that proves the change. Prefer README, Makefile, CI, or project scripts; else this ladder.

| Change | Command |
|---|---|
| YAML, source, package, project config | `dbt parse` |
| Model SQL | `dbt compile --select <model_name>` |
| Data tests | `dbt test --select <model_name>` or the changed test; add `+` only for downstream |
| Unit tests | `dbt test --select "test_type:unit"`; in a fresh or disposable schema, parents MUST exist (`dbt run --select <parents> --empty`, no `+`), plus an incremental model's own `--empty` shell; exclude from production builds ([unit-tests.md](references/unit-tests.md)) |
| Deprecations (1.10+) | `dbt parse --no-partial-parse --show-all-deprecations`; fix with `uvx dbt-autofix deprecations --dry-run` first |
| CI-style | `state:modified+ --state <manifest-dir>` when a prior manifest exists ([state-and-ci.md](references/state-and-ci.md)) |
| Docs artifacts or catalog | `dbt docs generate`, only when it matters |
| Format/lint | `sqlfluff`, `ruff`, pre-commit, repo scripts, only when configured; `uv run` them in uv projects |

- **Tools:** `grep`, `glob`, `read` for files; `bash` only for dbt and other real CLIs.
- **Blocked:** validation cannot run locally → state the exact command and missing prerequisite; report profile, credential, or Snowflake blockers exactly.
