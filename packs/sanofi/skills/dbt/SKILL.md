---
name: dbt
description: Sanofi dbt standards - layer taxonomies, model docs, data tests, incremental, snapshots, Elementary/DQ, WAP, scoped CI, approval-gated Snowflake-native projects. Use when creating, reviewing, fixing, or running dbt in a Sanofi repo. Not for generic dbt-on-Snowflake mechanics (dbt-projects-on-snowflake) or ODCS contracts (datacontract-writing).
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

## Routing

| Request | `read` first |
|---|---|
| Explicit `snow dbt`, `EXECUTE DBT PROJECT`, deployed `DBT PROJECT` object, native migration, native `env.yml`, `semantic_view`/`dbt_semantic_view` | [snowflake-native-dbt.md](references/snowflake-native-dbt.md) |
| Structure, placement, naming, materialization, setup, profiles, `dbt_project.yml`, packages, selectors, sources/snapshots/seeds/exposures, CI, Elementary, versioning, contracts, flags, WAP, troubleshooting | [general-dbt-guide.md](references/general-dbt-guide.md) |
| Model/column descriptions, source metadata, tags, `meta` | [writing-documentation.md](references/writing-documentation.md) |
| Adding or auditing data tests, coverage vs cost, DQ report triage | [writing-data-tests.md](references/writing-data-tests.md) |

- **NEVER route ordinary dbt Core work to the native reference** just because the adapter is Snowflake.
- Docs or tests task also needs layer placement, selectors, Elementary, orchestration, or a package change? Add `general-dbt-guide.md`.
- ODCS data contracts → datacontract-writing skill. DAG authoring → sanofi-airflow skill.
- Multi-area order: placement and naming → SQL and materialization → docs and properties → tests → selectors, CI, run commands.
- Docs before tests when both requested. Docs exist? Check documented grain matches the model, then go to tests.

## Version-Sensitive Rules

| Rule | Check before applying |
|---|---|
| Test params under `arguments:` | dbt >= 1.10.5; from 1.10.8 top-level params warn; older: top-level params |
| Engine and install | `pip install dbt` now installs dbt v2; v1 projects install `dbt-core` + `dbt-snowflake`. Run `dbt --version` before trusting parse or test output |
| Custom keys, `meta`, `tags`, `freshness`, `docs`, `group`, `access` | dbt >= 1.10: under `config:` (custom keys only in `config.meta`); top-level forms warn, error on dbt v2 |
| `microbatch` incremental | dbt >= 1.9; needs `event_time` on model and filtered parents, `begin`, `batch_size`; NEVER add `is_incremental()` |
| Snapshot deletes | dbt >= 1.9: `hard_deletes: invalidate\|new_record` replaces `invalidate_hard_deletes` |
| `dbt-snowflake` < 1.10.6 | Can break incrementals with `sync_all_columns` and collated strings after Snowflake's column-size change; upgrade |
| `insert_overwrite` on Snowflake | Truncates and reloads the whole table; NEVER use as partition replace on history-bearing models |
| `DBT_ENV_SECRET_*` | Only in `profiles.yml` and `packages.yml`; NEVER in sources, macros, vars, SQL |
| `--full-refresh` vs `full_refresh: false` | Config wins; the flag does not override `false` |
| Unit test YAML | Under `model-paths`, NEVER `tests/` |
| Native `snow dbt` | Re-verify CLI minimums, flags, and the `DBT_VERSION` pin (1.x = Core, 2.x = dbt v2) against current Snowflake docs |

## Validation Ladder

Smallest command that proves the change.

| Change | Command |
|---|---|
| YAML, source, package, project config | `dbt parse` |
| Model SQL | `dbt compile --select <model_name>` |
| Data tests | `dbt test --select <model_name>` or the changed test; add `+` only for downstream |
| Unit tests | `dbt test --select "test_type:unit"`; parents must exist (`dbt run --select <parents> --empty`); exclude from production builds |
| Deprecations (1.10+) | `dbt parse --no-partial-parse --show-all-deprecations`; fix with `uvx dbt-autofix deprecations --dry-run` first |
| CI-style | `state:modified+ --state <manifest-dir>` when a prior manifest exists |
| Docs artifacts or catalog | `dbt docs generate`, only when it matters |
| Format/lint | `sqlfluff`, `ruff`, pre-commit, repo scripts, only when configured |

- Use the `grep`, `glob`, `read` tools to inspect files; `bash` only for dbt and other real CLIs.
- Validation cannot run locally? State the exact command and the missing prerequisite.

## Checklist

- Standards precedence applied; conflicts surfaced, not silently resolved.
- Grain key documented, tested (`unique` + `not_null`), matches model SQL.
- No secret env var outside `profiles.yml`/`packages.yml`.
- No new deprecation warnings; custom keys under `config.meta`; none silenced as the fix.
- Incremental strategy valid on Snowflake; `full_refresh` behavior understood.
- Test `arguments:` syntax matches the project's dbt version; engine and version confirmed with `dbt --version`.
- Native-project steps authorized; no forced deploy, drop, or schedule change without approval.
- Narrowest validation command run, or blocker stated.
