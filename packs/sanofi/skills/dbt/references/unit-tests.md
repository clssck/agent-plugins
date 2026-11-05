# dbt Unit Tests

Unit tests validate transformation logic on static mock inputs before large tables are scanned; data tests check real Snowflake data. Use for business logic, calculations, currency/unit conversions, conditional mappings, regex, date math, window functions, edge cases. Skip warehouse built-ins such as `min()`. Unit tests require dbt-core >= 1.8. Adapted from dbt Labs' `adding-dbt-unit-test`
skill (see `licenses/sanofi/dbt/ATTRIBUTION`).

## Placement and Naming

- **YAML under `model-paths`** (default `models/`), next to the model; NEVER under `tests/` (reserved for data tests). Fixture files (`csv`/`sql`) live in a `fixtures` subdirectory of a `test-paths` entry, e.g. `tests/fixtures/<name>.sql`.
- **Names:** `scenario__expected`; YAML in `models/<domain>/`.
- **Mock every input.** Every `ref()` and `source()` the model reads is a `given` input, or compilation fails with "node not found". `rows: []` for an input whose values are irrelevant — beware a join on it dropping all rows.
- **Seeds:** a seed with no `given` entry uses its CSV as input; supplying one replaces it.

## Spec

Schematic, NOT copy-ready: `|` separates alternatives and `<...>` marks a value to fill; choose one alternative per key. The runnable example is under [Incremental Models](#incremental-models).

```yaml
unit_tests:
  - name: <scenario__expected>        # unique
    description: <string>             # optional
    model: <model_name>               # required
    versions:                         # optional, versioned models only
      include: [2]                    # or exclude: [1]
    config:
      enabled: true                   # dbt >= 1.9; false parks a failing test
      tags: [<tag>]
      meta: {}
    given:                            # required
      - input: ref('x') | source('s', 't') | this
        format: dict | csv | sql      # default dict
        rows: [...] | |-              # inline, or:
        fixture: <fixture_name>       # csv/sql only
    expect:
      format: dict | csv | sql
      rows: [...]
      fixture: <fixture_name>
    overrides:
      macros: {is_incremental: true, <macro_name>: <value>}
      vars: {<var>: <value>}
      env_vars: {<ENV_VAR>: <value>}
```

- `config:` holds `meta`, `tags`, `enabled` (keep keys under `config:`; version table in SKILL.md). `ref('m', v=2)` and `ref('project', 'm')` are valid inputs.
- **Formats:** `dict` default — start here, lists only relevant columns · `csv` for long fixtures or types `dict` cannot express · `sql` requires **every** column and is the only format that works for an **ephemeral** parent input (`dict`/`csv` fail). No format supports Jinja.
- `expect` = the model's result for the inputs, row form; column order irrelevant.

## Overrides

Overrides replace a macro, var, or env var **referenced directly in the tested model's SQL**. One referenced only inside another macro the model calls is not overridden.

- **`is_incremental`:** MUST be set `true` or `false` for an incremental model.
- **`dbt_utils.star`:** MUST be overridden with a comma-separated column list (`dbt_utils.star: col_a,col_b`); the mocked input replaces the `ref()`, so `star` cannot introspect a relation.
- **Nondeterministic functions** (`current_timestamp`, `invocation_id`, `run_started_at`): pin them (`macros: {invocation_id: 123}`; a macro such as `dbt_utils.current_timestamp` takes the literal) so expected rows are stable.
- **Environment-gated logic:** `overrides.vars` / `overrides.env_vars` flip it per test.

## Incremental Models

Expected output = **what the materialization will merge or insert**, not the final table. Two cases: `is_incremental: false` (full build) and `is_incremental: true` with the current target mocked as a `given` input of `this`.

```yaml
unit_tests:
  - name: incremental__late_payment_updates_order
    model: fct_orders
    overrides: {macros: {is_incremental: true}}
    given:
      - input: ref('stg_orders')
        rows: [{order_id: 1, updated_at: 2026-01-01}]
      - input: ref('stg_payments')
        rows: [{order_id: 1, amount: 5, loaded_at: 2026-01-03}]
      - input: this
        rows: [{order_id: 1, amount: 0, order_updated_at: 2026-01-01, payments_loaded_at: null}]
    expect:
      rows: [{order_id: 1, amount: 5}]
```

dbt cannot unit test whether the framework merged the rows correctly (dbt-labs/dbt-core issue 8664) → cover that with a data test or a dev diff against a full refresh ([snowflake-materializations.md](skill://dbt/references/snowflake-materializations.md#late-arriving-and-multi-parent-changes)). Cover same-day dedup, merge logic, and late child rows with the `true` case.

## Versioned Models

A unit test runs against **all** versions by default. Pin with `versions: {include: [2]}` or `exclude: [1]`. A new version with changed columns usually needs its own case with different `expect` rows → scope each case to the versions it describes. See [contracts-and-versions.md](skill://dbt/references/contracts-and-versions.md).

## Snowflake Value Gotchas

dbt casts literals to the type inferred from the input/output models → give values Snowflake can cast:

| Type | `dict` value |
|---|---|
| timestamp / timestamptz | `2013-11-03 00:00:00-0` (offset required for tz types) |
| escaped string | `"my,cool'string"` |
| variant | `3` |
| object | `{'Alberta':'Edmonton','Manitoba':'Winnipeg'}` |
| array | `['a','b','c']`, `[1, 2, 3]` |
| binary | hex string `19E1FFDCCB6CDEE788BF631C1C4905D1` |
| geography / geometry | `POINT(-122.35 37.55)` |

Unit tests assert values, not types. A literal that does not cast cleanly for a column type (see [Platform-specific data types](https://docs.getdbt.com/reference/resource-properties/data-types)) → switch that input or `expect` to `format: sql` with an explicit `cast(...)`.

## Running Unit Tests

- **Direct parents of `dict`/`csv` inputs MUST exist** so dbt can read column types: in the target schema, or on a production manifest through `--defer`. `format: sql` inputs read no columns, so their parents need not exist. Clean CI or dev schema with no prod manifest → build empty shells **for the parents only**: `dbt run --select "<parent_a> <parent_b>" --empty`.
- **`--defer` supplies fixture types:** `dbt test --select "<model>,test_type:unit" --defer --state <prod-manifest-dir>` reads a missing parent's columns from its production relation (`describe`; fixtures stay static), so no shell build. The target relation wins when it exists. It does not cover sources, parents absent from the state manifest (new or renamed → shell build), or a prod relation the role cannot describe (Snowflake returns no columns for "does not exist or not authorized" → the `Not able to get columns` error below). The manifest only names the relation; types come from the current production relation (table or view), so a prod schema change since the manifest was saved changes the fixture casts. Behavior comes from the `get_fixture_sql` macro; the docs do not describe it ([source](https://github.com/dbt-labs/dbt-adapters/blob/main/dbt-adapters/src/dbt/include/global_project/macros/unit_test_sql/get_fixture_sql.sql)).
- **Incremental model with an `is_incremental: true` case:** a `dict`/`csv` `this` fixture makes dbt read columns from the model's own relation; on a fresh schema `dbt build` runs the unit test before the model and fails with `Not able to get columns for unit test '<model>'` ([dbt-core#10844](https://github.com/dbt-labs/dbt-core/issues/10844)). With `--defer --state` and the model in the prod manifest, `this` resolves from the prod relation too. Otherwise, in CI and fresh dev schemas only, run `dbt run --select "<model>" --empty` (or an explicit list of affected incremental models) before the build; prove it by building once from an empty schema. A `format: sql` `this` fixture (with `format: sql` parents) skips that introspection: the test passes on an empty database with no shell, state, or defer.
- **`--empty` semantics:** refs and sources read zero rows; selected tables and views are rebuilt empty, an existing incremental gets a zero-row incremental run. Use only on the target model, its parents, or explicitly scoped incremental models in a fresh or disposable schema. NEVER aim it at data-bearing relations or combine it with an unchecked `+` upstream selector. All parents of one model: `--select "1+<model>" --exclude "<model>"`. `dbt build --select "+<model>"` builds parents for real instead, in lineage order with unit tests before the model — use when those builds are cheap.
- **Commands:**

  | Goal | Command |
  |---|---|
  | all unit tests | `dbt test --select "test_type:unit"` |
  | one model's | `dbt test --select "<model>,test_type:unit"` |
  | single case | `dbt test --select "<case>"` (or `unit_test:<case>`) |
  | generic data tests | `dbt test --select "test_type:generic"` |
  | by generic-test name | `dbt test --select "test_name:<name>"` |
  | list | `dbt list --select "unit_test:*"` |

- **Granularity:** a unit test is one case; passes (0) or fails (1) however many rows differ; a failed case prints an `actual differs from expected` diff.
- **Dev and CI only.** Inputs are static → production runs waste compute: `dbt build --exclude-resource-type unit_test` or `DBT_ENGINE_EXCLUDE_RESOURCE_TYPES=unit_test` (1.11+). For `dbt test`, `--select "test_type:data"` runs only data tests, or `--exclude-resource-type unit_test`.
- A disabled model disables its unit tests (1.11+).

## Limits

- Only SQL models of the **current** project; not Python models, snapshots, seeds, sources, analyses, or package models.
- Models using `materialized_view`, recursive SQL, or introspective queries cannot be unit tested.
- SQL `join` logic needs aliased tables.

## Verification

- YAML under `model-paths`, not `tests/`; every `ref`/`source` mocked.
- `is_incremental` (and `dbt_utils.star`) overridden where used; ephemeral parents use `format: sql`.
- Parents of `dict`/`csv` inputs exist: built with `--empty` without `+`, only in a fresh or disposable schema, or deferred to a prod manifest that holds them (not sources or new parents); `format: sql` inputs need no parent.
- Incremental unit tests pass from an empty schema (`dict`/`csv` `this`: model's own `--empty` shell pre-built, or `--defer` with the model in the prod manifest; `format: sql` `this`: nothing pre-built).
- Unit tests excluded from production builds.
- A deliberately broken expectation fails, proving the test can fail.

## Sources

- [Unit tests](https://docs.getdbt.com/docs/build/unit-tests), [unit tests property](https://docs.getdbt.com/reference/resource-properties/unit-tests), [overrides](https://docs.getdbt.com/reference/resource-properties/unit-test-overrides), [data types](https://docs.getdbt.com/reference/resource-properties/data-types), [`--empty`](https://docs.getdbt.com/reference/commands/build#the---empty-flag), [`unit_test` / `test_type` selectors](https://docs.getdbt.com/reference/node-selection/methods).
- dbt Labs `adding-dbt-unit-test` skill (Apache-2.0).
