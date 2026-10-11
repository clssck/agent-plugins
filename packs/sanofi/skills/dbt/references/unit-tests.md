# dbt Unit Tests

Unit tests validate transformation logic on static mock inputs before large tables are scanned; data tests check real Snowflake data. Use for business logic, calculations, currency/unit conversions, conditional mappings, regex, date math, window functions, edge cases. Skip warehouse built-ins such as `min()`. Unit tests require dbt-core >= 1.8. Adapted from dbt Labs' `adding-dbt-unit-test`
skill (see `licenses/sanofi/dbt/ATTRIBUTION`).

## Placement and Naming

- **YAML under `model-paths`** (default `models/`), next to the model; NEVER under `tests/` (reserved for data tests). Fixture files (`csv`/`sql`) live in a `fixtures` subdirectory of a `test-paths` entry, e.g. `tests/fixtures/<name>.sql`.
- **Names:** `scenario__expected`; YAML in `models/<domain>/`.
- **Mock every input.** Every `ref()` and `source()` the model reads is a `given` input, or compilation fails with "node not found". `rows: []` for an input whose values are irrelevant — beware a join on it dropping all rows.
- **Seeds:** a seed with no `given` entry uses its CSV as input; supplying one replaces it.

## Spec

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

dbt cannot unit test whether the framework merged the rows correctly (dbt-labs/dbt-core issue 8664) → cover that with a data test or a dev diff against a full refresh ([snowflake-materializations.md](snowflake-materializations.md#late-arriving-and-multi-parent-changes)). Cover same-day dedup, merge logic, and late child rows with the `true` case.

## Versioned Models

A unit test runs against **all** versions by default. Pin with `versions: {include: [2]}` or `exclude: [1]`. A new version with changed columns usually needs its own case with different `expect` rows → scope each case to the versions it describes. See [contracts-and-versions.md](contracts-and-versions.md).

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

- **Direct parents MUST exist in the target schema** so dbt can read column types. Clean CI or dev schema → build empty shells **for the parents only**: `dbt run --select "<parent_a> <parent_b>" --empty`.
- **Incremental model with an `is_incremental: true` case:** dbt also reads columns from the model's own relation (`this`); on a fresh schema `dbt build` runs the unit test before the model and fails with `Not able to get columns for unit test '<model>'` ([dbt-core#10844](https://github.com/dbt-labs/dbt-core/issues/10844)). In CI and fresh dev schemas only, run `dbt run --select "<model>" --empty` (or an explicit list of affected incremental models) before the build; prove it by building once from an empty schema.
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
- Parents built with `--empty` without `+`, only in a fresh or disposable schema.
- Incremental unit tests pass from an empty schema (model's own `--empty` shell pre-built).
- Unit tests excluded from production builds.
- A deliberately broken expectation fails, proving the test can fail.

## Sources

- [Unit tests](https://docs.getdbt.com/docs/build/unit-tests), [unit tests property](https://docs.getdbt.com/reference/resource-properties/unit-tests), [overrides](https://docs.getdbt.com/reference/resource-properties/unit-test-overrides), [data types](https://docs.getdbt.com/reference/resource-properties/data-types), [`--empty`](https://docs.getdbt.com/reference/commands/build#the---empty-flag), [`unit_test` / `test_type` selectors](https://docs.getdbt.com/reference/node-selection/methods).
- dbt Labs `adding-dbt-unit-test` skill (Apache-2.0).
