# Selectors, State, and CI

Scoped execution is the Sanofi default: select the smallest meaningful set of nodes, and in
CI let a prior production manifest decide what changed. Adapted in part from dbt Labs'
`running-dbt-commands` skill (see `licenses/sanofi/dbt/ATTRIBUTION`).

## Selectors

Do not default to global runs. Select the smallest meaningful scope with upstream
(`+model_name`), downstream (`model_name+`), both directions (`+model_name+`), folder, tag,
or `state:modified+` selectors, and apply the same scoped selector to `run`, `test`, and
`build`.

- `N+model` / `model+N` limit the depth: `1+fct_orders` is the model and its direct parents
  (use with `--exclude fct_orders` to get parents only).
- Space = union, comma = intersection, `--exclude` subtracts:
  `--select "tag:daily,config.materialized:incremental" --exclude "tag:heavy_compute"`.
- Preview before running: `dbt ls --select "<selector>" --resource-type model`.
- `-m` / `--model` / `--models` are deprecated; use `-s` / `--select`.
- Catch selector typos: `--warn-error-options '{"error": ["NoNodesForSelectionCriteria"]}'`
  turns "no nodes selected" into a failure instead of a green no-op.
- With the legacy `--selector <name>` flag, `--select` and `--exclude` are **ignored**
  (dbt 1.12 warns with `SelectExcludeIgnoredWithSelectorWarning`; older versions do not), so a
  safety `--exclude` is dropped. Reference the named selector inside the selection instead:
  `--select "selector:<name> <extra>" --exclude "<x>"` (1.12+).
- Orchestrators select by tag, not file path, so renames do not silently break schedules
  (see Tags in [general-dbt-guide.md](general-dbt-guide.md#tags)).

## `state:` Selection

`state:` compares the project to a previous `manifest.json` passed with `--state <dir>`
(`DBT_ENGINE_STATE` from 1.11).

| Selector | Selects |
|---|---|
| `state:new` | Nodes absent from the comparison manifest |
| `state:modified` | New nodes plus any changed node |
| `state:old` / `state:unmodified` | The inverse sets |

Narrow `state:modified` with sub-selectors: `state:modified.body` (SQL or seed values),
`.configs` (configs except `database`/`schema`/`alias`/`tags`/`meta`), `.relation`
(`database`/`schema`/`alias`), `.persisted_descriptions` (descriptions, only when
`persist_docs` is on), `.macros` (upstream macros, direct or indirect), `.contract`.

Behavior that surprises people:

- `tags` and `meta` changes are NOT modifications. Any other config change is. `description`
  counts only with `persist_docs`.
- A changed macro marks every node that depends on it, directly or through another macro.
- A changed `var()` or `env_var()` value is not tracked as a change by itself.
- Seeds under 1 MiB compare by content; larger seeds compare by path only.
- `state:modified` sees code and config, not data. A scheduled production job that must
  build regardless of code changes MUST NOT use it; reserve it for CI and merge jobs.
- Environment-aware Jinja (`target.name` in configs) causes false positives. Set
  `flags: state_modified_compare_more_unrendered_values: true` (default `true` from 1.12; the
  state directory must be built with a version and flag that match).
- dbt overwrites `target/manifest.json` while parsing. NEVER point `--state` at the same
  directory as `--target-path`; copy the production manifest to a dedicated `state/` folder.
- `dbt test -s state:modified` includes tests that are themselves new or modified. A new
  test on an unmodified model may need the model to exist, so use `--defer`.

Useful CI sets: `state:modified+` (changed nodes and descendants), and after a failed run
`state:modified+ result:error+ result:fail+` to retry only what broke.

## Defer

`--defer --state <dir>` resolves `ref()` to the state manifest's relation, but only when
the node is not selected **and** does not exist in the current target (`--favor-state`
drops the existence condition: the manifest wins even if a local copy exists). Ephemeral
models are never deferred. `--defer-state <dir>` uses a different manifest for deferral than
for `state:` comparison; without it, `--state` serves both.

```bash
dbt build --select "state:modified+" --defer --state prod-artifacts
```

Use state-based selection in CI/CD when a prior successful `manifest.json` is available.
Pass `--state` unless the orchestration environment already supplies the prior manifest
location (`DBT_ENGINE_STATE` from 1.11). Add `--defer` only when intentionally resolving
unchanged refs to the prior state; plain `--state` with `state:modified+` does not defer.

Pitfalls:

- Deferred reads hit production data. Environment-specific limits (dev data limits gated by
  `target.name`) then select more or less than expected.
- A `relationships` test with one built parent and one deferred parent compares data across
  environments, which is meaningless with sampled data. Exclude it in CI:
  `--exclude "test_name:relationships"`.
- `--defer` needs a manifest from a prior run; no manifest, no deferral.

## `dbt clone`

`dbt clone --state <dir> [--select ...]` copies selected nodes from the state's relations
into the target schema. On Snowflake, a table in state becomes a **zero-copy clone**; views
become pointer views (`select * from` the source). It does not recreate relations that
already exist unless `--full-refresh` is passed; raise `--threads`, since each clone is
independent. Use it instead of deferral when you need real objects:

- Seed a CI schema with the current production incrementals so CI does not full-refresh them.
- Test downstream consumers outside dbt (BI tools) against changed models.

Deferral is cheaper and simpler when the run only needs to read unbuilt upstream models.

## Per-PR Schemas on Snowflake

- Give each PR its own schema, for example `CI_PR_<number>`, through an env-var-driven
  `schema` in the CI profile target (see Profile patterns in
  [project-setup.md](project-setup.md#profiles-and-secrets)); keep `generate_schema_name`
  overrides consistent so layer schemas become `CI_PR_<number>_<layer>` or collapse to one.
- dbt may create objects inside a schema but, at Sanofi, does not own schemas and grants
  ([general-dbt-guide.md](general-dbt-guide.md#schemas-sources-and-lineage)). Confirm the CI
  role may create schemas in the approved CI database, or provision them through the repo's
  approved path.
- dbt never drops what it created. Clean up explicitly:
  1. a job on PR close (and on merge) that drops that PR's schema;
  2. a scheduled sweep for stale schemas matching **only** the CI prefix pattern.
  `DROP SCHEMA` defaults to `CASCADE` and removes every object inside; a dropped schema can
  be restored with `UNDROP SCHEMA` only within Time Travel retention. Build the name from the
  CI variables, assert it matches the prefix, and NEVER derive a drop target from user input,
  `target.schema` of a shared profile, or a wildcard that could match dev or prod schemas.
- Per-PR schemas also stop concurrent runs from overwriting each other's objects, including
  `tmp_relation_type: transient` staging relations
  ([snowflake-materializations.md](snowflake-materializations.md#incremental-strategies-on-snowflake)).

## Gates

Order cheap checks first and stop at the first failure:

1. `dbt parse` (add `--no-partial-parse --show-all-deprecations` on 1.10+). It needs no
   warehouse resources, and every other command runs it implicitly, so run it explicitly
   when the change is project configuration.
2. Lint (`sqlfluff`, `ruff`, pre-commit) when configured.
3. `dbt build --select "state:modified+" --defer --state <prod-artifacts>` into the PR
   schema (this also runs tests and unit tests; see
   [unit-tests.md](unit-tests.md#running-unit-tests) for the parent prerequisite).
4. Optional `dbt_project_evaluator` where the repo has approved it.

For orchestration, pick one consistent gate pattern per DAG: `dbt build` for
dependency-ordered run/test behavior, or explicit per-layer `dbt run` plus `dbt test` tasks
when downstream layers must wait for intermediate test feedback. Do not mix both patterns
inside one pipeline without a documented reason. PR checks commonly combine scoped
`dbt compile`, scoped `dbt test`, SQLFluff over `transformation/`, and optional
dbt_project_evaluator. For authoring the Airflow/MWAA DAGs that run dbt (`BashOperator` +
`dbt_run.sh` or a typed `DbtClient`, scheduling, parse-time safety, deployment), use the
sanofi-airflow skill. Use `dbt snapshot --select state:modified` for state-based snapshot
runs when the state manifest is available.

## Checklist

- Every `dbt build|run|test|seed|snapshot` in CI has a selector (or a documented reason).
- `--state` points to a copied production manifest, NEVER to `target/`.
- Deferred or cloned runs account for cross-environment reads; `relationships` tests excluded.
- PR schemas are created through an approved path, named per PR, and dropped on close with a
  prefix-guarded cleanup.
- `dbt parse` gate runs before warehouse-touching steps.

## Sources

- [State selection methods](https://docs.getdbt.com/reference/node-selection/methods#state), [state comparison caveats](https://docs.getdbt.com/reference/node-selection/state-comparison-caveats), [defer](https://docs.getdbt.com/reference/node-selection/defer), [`dbt clone`](https://docs.getdbt.com/reference/commands/clone), [YAML selectors](https://docs.getdbt.com/reference/node-selection/yaml-selectors), [graph operators](https://docs.getdbt.com/reference/node-selection/graph-operators), [warn-error options](https://docs.getdbt.com/reference/global-configs/warnings).
- [`DROP SCHEMA`](https://docs.snowflake.com/en/sql-reference/sql/drop-schema): `CASCADE` default, `UNDROP`.
- dbt Labs `running-dbt-commands` skill (Apache-2.0).
