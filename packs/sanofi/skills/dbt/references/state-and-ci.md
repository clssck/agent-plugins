# Selectors, State, and CI

Scoped execution is the Sanofi default: select the smallest meaningful set of nodes, and in CI let a prior production manifest decide what changed. Adapted in part from dbt Labs'
`running-dbt-commands` skill (see `licenses/sanofi/dbt/ATTRIBUTION`).

## Selectors

**No global runs by default.** Select the smallest meaningful scope — upstream (`+model_name`), downstream (`model_name+`), both (`+model_name+`), folder, tag, or `state:modified+` — and apply the same scoped selector to `run`, `test`, and `build`.

- **Depth:** `N+model` / `model+N` limit it; `1+fct_orders` = model plus direct parents (add `--exclude fct_orders` for parents only).
- **Set algebra:** space = union, comma = intersection, `--exclude` subtracts: `--select "tag:daily,config.materialized:incremental" --exclude "tag:heavy_compute"`.
- **Preview:** `dbt ls --select "<selector>" --resource-type model`.
- **Deprecated:** `-m` / `--model` / `--models` → `-s` / `--select`.
- **Typo guard:** `--warn-error-options '{"error": ["NoNodesForSelectionCriteria"]}'` turns "no nodes selected" into a failure instead of a green no-op.
- **Legacy `--selector <name>` ignores `--select` and `--exclude`** (dbt 1.12 warns with `SelectExcludeIgnoredWithSelectorWarning`; older versions do not) → a safety `--exclude` is dropped. Reference the named selector inside the selection instead: `--select "selector:<name> <extra>" --exclude "<x>"` (1.12+).
- **Orchestrators select by tag, not file path**, so renames do not silently break schedules (Tags in [general-dbt-guide.md](general-dbt-guide.md#tags)).

## `state:` Selection

`state:` compares the project to a previous `manifest.json` passed with `--state <dir>` (`DBT_ENGINE_STATE` from 1.11).

| Selector | Selects |
|---|---|
| `state:new` | Nodes absent from the comparison manifest |
| `state:modified` | New nodes plus any changed node |
| `state:old` / `state:unmodified` | The inverse sets |

Narrow `state:modified` with sub-selectors: `state:modified.body` (SQL or seed values) · `.configs` (configs except `database`/`schema`/`alias`/`tags`/`meta`) · `.relation` (`database`/`schema`/`alias`) · `.persisted_descriptions` (descriptions, only when `persist_docs` is on) · `.macros` (upstream macros, direct or indirect) · `.contract`.

Behavior that surprises people:

- `tags` and `meta` changes are NOT modifications; any other config change is. `description` counts only with `persist_docs`.
- A changed macro marks every node depending on it, directly or through another macro.
- A changed `var()` or `env_var()` value is not tracked as a change by itself.
- Seeds under 1 MiB compare by content; larger seeds by path only.
- **`state:modified` sees code and config, not data.** A scheduled production job that must build regardless of code changes MUST NOT use it; reserve it for CI and merge jobs.
- Environment-aware Jinja (`target.name` in configs) → false positives. Set `flags: state_modified_compare_more_unrendered_values: true` (default `true` from 1.12; the state directory must be built with a version and flag that match).
- **dbt overwrites `target/manifest.json` while parsing.** NEVER point `--state` at the `--target-path` directory; copy the production manifest to a dedicated `state/` folder.
- `dbt test -s state:modified` includes tests that are themselves new or modified. A new test on an unmodified model may need the model to exist → `--defer`.

Useful CI sets: `state:modified+` (changed nodes and descendants); after a failed run `state:modified+ result:error+ result:fail+` retries only what broke.

## Defer

`--defer --state <dir>` resolves `ref()` to the state manifest's relation only when the node is not selected **and** does not exist in the current target. `--favor-state` drops the existence condition: manifest wins even if a local copy exists. Ephemeral models are never deferred. `--defer-state <dir>` uses a different manifest for deferral than for `state:` comparison; without it `--state` serves both.

```bash
dbt build --select "state:modified+" --defer --state prod-artifacts
```

Use state-based selection in CI/CD when a prior successful `manifest.json` is available. Pass `--state` unless the orchestration environment already supplies the prior manifest location (`DBT_ENGINE_STATE` from 1.11). Add `--defer` only when intentionally resolving unchanged refs to prior state; plain `--state` with `state:modified+` does not defer.

Pitfalls:

- Deferred reads hit production data → environment-specific limits (dev data limits gated by `target.name`) select more or less than expected.
- A `relationships` test with one built parent and one deferred parent compares data across environments — meaningless with sampled data. Exclude it in CI: `--exclude "test_name:relationships"`.
- `--defer` needs a manifest from a prior run; no manifest, no deferral.

## `dbt clone`

`dbt clone --state <dir> [--select ...]` copies selected nodes from the state's relations into the target schema. On Snowflake a table in state becomes a **zero-copy clone**; views become pointer views (`select * from` the source). Existing relations are not recreated unless `--full-refresh`; raise `--threads` since each clone is independent. Use instead of deferral when real objects are needed:

- Seed a CI schema with current production incrementals so CI does not full-refresh them.
- Test downstream consumers outside dbt (BI tools) against changed models.

Deferral is cheaper and simpler when the run only reads unbuilt upstream models.

## Per-PR Schemas on Snowflake

- **Naming:** one schema per PR, e.g. `CI_PR_<number>`, via an env-var-driven `schema` in the CI profile target (Profile patterns in [project-setup.md](project-setup.md#profiles-and-secrets)); keep `generate_schema_name` overrides consistent so layer schemas become `CI_PR_<number>_<layer>` or collapse to one.
- **Ownership:** dbt may create objects inside a schema but, at Sanofi, does not own schemas and grants ([general-dbt-guide.md](general-dbt-guide.md#schemas-sources-and-lineage)). Confirm the CI role may create schemas in the approved CI database, or provision them through the repo's approved path.
- **Cleanup is explicit; dbt never drops what it created:**
  1. Job on PR close (and on merge) drops that PR's schema.
  2. Scheduled sweep for stale schemas matching **only** the CI prefix pattern.

  `DROP SCHEMA` defaults to `CASCADE` and removes every object inside; `UNDROP SCHEMA` restores only within Time Travel retention. Build the name from CI variables, assert it matches the prefix, and NEVER derive a drop target from user input, `target.schema` of a shared profile, or a wildcard that could match dev or prod schemas.
- **Isolation:** per-PR schemas also stop concurrent runs overwriting each other's objects, including `tmp_relation_type: transient` staging relations ([snowflake-materializations.md](snowflake-materializations.md#incremental-strategies-on-snowflake)).

## Gates

Cheap checks first; stop at the first failure:

1. `dbt parse` (add `--no-partial-parse --show-all-deprecations` on 1.10+). Needs no warehouse resources; every other command runs it implicitly → run explicitly when the change is project configuration.
2. Lint (`sqlfluff`, `ruff`, pre-commit) when configured.
3. `dbt build --select "state:modified+" --defer --state <prod-artifacts>` into the PR schema (also runs tests and unit tests; parent prerequisite in [unit-tests.md](unit-tests.md#running-unit-tests)).
4. Optional `dbt_project_evaluator` where the repo has approved it.

**One gate pattern per DAG:** `dbt build` for dependency-ordered run/test, or explicit per-layer `dbt run` + `dbt test` tasks when downstream layers must wait for intermediate test feedback. Mixing both inside one pipeline needs a documented reason. PR checks commonly combine scoped `dbt compile`, scoped `dbt test`, SQLFluff over `transformation/`, and optional dbt_project_evaluator. Authoring the Airflow/MWAA DAGs that run dbt (`BashOperator` + `dbt_run.sh` or a typed `DbtClient`, scheduling, parse-time safety, deployment) → sanofi-airflow skill. State-based snapshot runs: `dbt snapshot --select state:modified` when the state manifest is available.

## Verification

- Every `dbt build|run|test|seed|snapshot` in CI has a selector (or a documented reason).
- `--state` points to a copied production manifest, NEVER `target/`.
- Deferred or cloned runs account for cross-environment reads; `relationships` tests excluded.
- PR schemas created through an approved path, named per PR, dropped on close with prefix-guarded cleanup.
- `dbt parse` gate runs before warehouse-touching steps.

## Sources

- [State selection methods](https://docs.getdbt.com/reference/node-selection/methods#state), [state comparison caveats](https://docs.getdbt.com/reference/node-selection/state-comparison-caveats), [defer](https://docs.getdbt.com/reference/node-selection/defer), [`dbt clone`](https://docs.getdbt.com/reference/commands/clone), [YAML selectors](https://docs.getdbt.com/reference/node-selection/yaml-selectors), [graph operators](https://docs.getdbt.com/reference/node-selection/graph-operators), [warn-error options](https://docs.getdbt.com/reference/global-configs/warnings).
- [`DROP SCHEMA`](https://docs.snowflake.com/en/sql-reference/sql/drop-schema): `CASCADE` default, `UNDROP`.
- dbt Labs `running-dbt-commands` skill (Apache-2.0).
