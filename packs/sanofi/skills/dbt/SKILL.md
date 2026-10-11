---
name: dbt
description: Sanofi dbt standards - layer taxonomies, model docs, data tests, unit tests, incremental design, snapshots, contracts and versions, state/CI, upgrades, Elementary/DQ, WAP, approval-gated Snowflake-native projects. Use when creating, reviewing, fixing, upgrading, or running dbt in a Sanofi repo. Not for generic dbt-on-Snowflake mechanics (dbt-projects-on-snowflake) or ODCS contracts (datacontract-writing).
---

# Sanofi dbt

Sanofi conventions for dbt project structure, model development, documentation, testing, CI, and Snowflake-native execution. Platform-specific overlay: generic dbt-on-Snowflake commands live in the dbt-projects-on-snowflake skill; generic review and security stay with `/review` and `/security`.

## Core Rules

- **MUST inspect the real dbt project first.** Derive names, layout, grain keys, columns, aliases, materializations, tags, sources, test scope from files and manifests.
- **Examples are patterns.** NEVER copy example names verbatim.
- **Standards precedence, high to low:**
  1. Target repo's documented contract, config, conventions.
  2. Applicable approved/current team standard.
  3. Cross-space standards.
  4. Draft/WIP guidance, advisory only.
- **NEVER let a lower-ranked source override a higher one.** Applicability, approval, currency, or conflict unclear? Ask first.
- **Verify with the narrowest repo-supported command.** Prefer README, Makefile, CI, or project scripts; else the ladder below. Report profile, credential, or Snowflake blockers exactly.
- **A legacy-style file is not a reason to write legacy syntax.** Write new code in the form the project's resolved dbt version accepts without warning; use the old form only where that version requires it (table below).
- **Incremental models MUST have a change signal for every joined parent** (lookback, affected-key re-derivation, `on_schema_change`, periodic refresh). Design before writing the filter: [snowflake-materializations.md](references/snowflake-materializations.md#late-arriving-and-multi-parent-changes).

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
| Upgrading dbt, deprecations, behavior flags, dbt v2 readiness, v2 error codes | [upgrading-and-v2.md](references/upgrading-and-v2.md) |
| Failed run, error triage, exit codes, `run_results.json`, flaky test | [troubleshooting.md](references/troubleshooting.md) |
| Model/column descriptions, source metadata, tags, `meta` | [writing-documentation.md](references/writing-documentation.md) |
| Adding or auditing data tests, coverage vs cost, DQ report triage | [writing-data-tests.md](references/writing-data-tests.md) |

- **NEVER route ordinary dbt Core work to the native reference** just because the adapter is Snowflake.
- Docs or tests task also needs layer placement, Elementary, orchestration, or a package change? Add `general-dbt-guide.md` (and `project-setup.md` or `operations.md` as routed).
- ODCS data contracts → datacontract-writing skill. DAG authoring → sanofi-airflow skill.
- Multi-area order: placement and naming → SQL and materialization → docs and properties → tests → selectors, CI, run commands.
- Docs before tests when both requested. Docs exist? Check documented grain matches the model, then go to tests.

## Version-Sensitive Rules

| Rule | Check before applying |
|---|---|
| Test params under `arguments:` | dbt >= 1.10.8: nest (flag defaults `true`, top-level warns). 1.10.5-1.10.7: nest only if `require_generic_test_arguments_property: true` is set, else the nested form warns (`ArgumentsPropertyInGenericTestDeprecation`); older: top-level |
| Engine and install | The bare `dbt` PyPI package is dbt v2 (since 2026-09-14); v1 projects install `dbt-core` + `dbt-snowflake` with uv ([project-setup.md](references/project-setup.md#setup-and-environment)). Run `dbt --version` before trusting parse or test output; upgrade and v2 steps in [upgrading-and-v2.md](references/upgrading-and-v2.md) |
| Custom keys, `meta`, `tags`, `freshness`, `docs`, `group`, `access` | dbt >= 1.10: under `config:` (custom keys only in `config.meta`); top-level forms warn, error on dbt v2 |
| `microbatch` incremental | dbt >= 1.9; needs `event_time` on model and filtered parents, `begin`, `batch_size`; NEVER add `is_incremental()` |
| Snapshot deletes | dbt >= 1.9: `hard_deletes: invalidate\|new_record` replaces `invalidate_hard_deletes` |
| `dbt-snowflake` < 1.10.6 | Can break incrementals with `sync_all_columns` and collated strings after Snowflake's column-size change; upgrade |
| `insert_overwrite` on Snowflake | Truncates and reloads the whole table; NEVER use as partition replace on history-bearing models |
| `latest_version_pointer` | dbt >= 1.12 (default on in dbt v2); collides (`dbt1005`) with a latest version aliased to the model name |
| `dbt_semantic_view` | dbt's Snowflake docs say dbt `<2.0.0`; verify before using it on dbt v2 or native `DBT_VERSION` 2.x |
| `DBT_ENV_SECRET_*` | Only in `profiles.yml` and `packages.yml`; NEVER in sources, macros, vars, SQL |
| `--full-refresh` vs `full_refresh: false` | Config wins; the flag does not override `false` |
| Unit test YAML | Under `model-paths`, NEVER `tests/` |
| Native `snow dbt` | Re-verify CLI minimums, flags, and the `DBT_VERSION` pin (1.x = Core, 2.x = dbt v2) against current Snowflake docs |

## Command Scope

A dbt command that writes to Snowflake rebuilds whatever it selects. Scope it before running it.

- **MUST select** every `dbt build|run|test|seed|snapshot` with `--select`/`-s`, `--selector`, or `state:modified+ --state <dir>`. A bare invocation is allowed only when the user explicitly asked for a full build; say so when running it. `-m`/`--models` is deprecated; where it is ignored, the whole DAG builds.
- **Preview first** when a selector is non-trivial: `dbt ls --select "<selector>" --resource-type model`. Add `--warn-error-options '{"error": ["NoNodesForSelectionCriteria"]}'` so a typo fails instead of building nothing.
- **`--empty` replaces every selected relation with a zero-row version** (refs and sources read zero rows). Use it only on the target model, or on parents in a disposable schema with the model itself excluded (`--select "1+<model>" --exclude "<model>"`). NEVER pair it with a `+` upstream selector when those relations hold data you need; if the selector must include upstream, add `--exclude` for every relation to keep.
- **Prod or `--full-refresh`:** confirm explicit user approval for that target and selection first. Read the `on-run-start`/`on-run-end` hooks in `dbt_project.yml` (they run on `build`, `run`, `test`, `seed`, `snapshot`) and the model's `full_refresh` config. Afterwards verify row counts against a count taken before the run (or Time Travel) and run the model's tests.
- **Prefer `dbt build`** (models + tests + unit tests, in lineage order) over `dbt run`. The exception is the documented per-layer `dbt run` + `dbt test` orchestration pattern ([state-and-ci.md](references/state-and-ci.md#gates)); do not mix patterns in one pipeline.
- **Inspect data with `dbt show`**, not ad-hoc Python: `dbt show --select <model> --limit 10` or `dbt show --inline "select ... from {{ ref('x') }}" --limit 10`. Use `--limit`, not a SQL `LIMIT`; `--select` takes one node. `--inline` can run any SQL, so use a read-only role.
- Use `uv run dbt ...` in uv projects; one `uv.lock` left untracked is not part of the task.

## Validation Ladder

Smallest command that proves the change.

| Change | Command |
|---|---|
| YAML, source, package, project config | `dbt parse` |
| Model SQL | `dbt compile --select <model_name>` |
| Data tests | `dbt test --select <model_name>` or the changed test; add `+` only for downstream |
| Unit tests | `dbt test --select "test_type:unit"`; parents must exist (`dbt run --select <parents> --empty`, no `+`), and an incremental model's own `--empty` shell on a fresh schema; exclude from production builds ([unit-tests.md](references/unit-tests.md)) |
| Deprecations (1.10+) | `dbt parse --no-partial-parse --show-all-deprecations`; fix with `uvx dbt-autofix deprecations --dry-run` first |
| CI-style | `state:modified+ --state <manifest-dir>` when a prior manifest exists ([state-and-ci.md](references/state-and-ci.md)) |
| Docs artifacts or catalog | `dbt docs generate`, only when it matters |
| Format/lint | `sqlfluff`, `ruff`, pre-commit, repo scripts, only when configured; `uv run` them in uv projects |

- Use the `grep`, `glob`, `read` tools to inspect files; `bash` only for dbt and other real CLIs.
- Validation cannot run locally? State the exact command and the missing prerequisite.

## Checklist

- Standards precedence applied; conflicts surfaced, not silently resolved.
- Grain key documented, tested (`unique` + `not_null`), matches model SQL.
- No secret env var outside `profiles.yml`/`packages.yml`.
- No new deprecation warnings; custom keys under `config.meta`; none silenced as the fix.
- Incremental strategy valid on Snowflake; every parent has a change signal; `full_refresh` behavior understood.
- Test `arguments:` syntax matches the project's dbt version; engine and version confirmed with `dbt --version`.
- Every mutating dbt command selected; `--empty` not aimed at data worth keeping; prod and `--full-refresh` approved, hooks read, counts checked.
- Native-project steps authorized; no forced deploy, drop, or schedule change without approval.
- Narrowest validation command run, or blocker stated.
