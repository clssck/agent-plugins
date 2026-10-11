# dbt Unit Tests

Use dbt unit tests for business logic, calculations, currency/unit conversions,
conditional mappings, regex, date math, window functions, and edge cases that should be
validated before scanning large tables. Skip them for warehouse built-ins such as `min()`.
Data tests check real Snowflake data; unit tests check transformation logic on static
mock inputs. Unit tests require dbt-core >= 1.8. Adapted from dbt Labs' `adding-dbt-unit-test`
skill (see `ATTRIBUTION`).

## Placement and Naming

- YAML definitions belong under `model-paths` (default `models/`), next to the model, NEVER
  under `tests/`, which is reserved for data tests. Fixture files (`csv`/`sql`) live in a
  `fixtures` subdirectory of a `test-paths` entry, for example `tests/fixtures/<name>.sql`.
- Name cases `scenario__expected`; keep their YAML in `models/<domain>/`.
- Include every `ref()` and `source()` the model reads as a `given` input, or compilation
  fails with "node not found". Use `rows: []` for an input whose values are irrelevant, but
  beware a join on it dropping all rows.
- A seed with no `given` entry uses its CSV as the input; supplying one replaces it.

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

- `config:` holds `meta`, `tags`, `enabled` (keep keys under `config:`, see the version
  table in SKILL.md). `ref('m', v=2)` and `ref('project', 'm')` are valid inputs.
- Start with `dict`; it is the default and lists only the relevant columns.
- `csv` suits fixtures that are long or need a type `dict` cannot express.
- `sql` requires **every** column and is the only format that works for an **ephemeral**
  parent input (`dict`/`csv` fail). No format supports Jinja.
- `expect` is the model's result for the inputs, in row form; column order is irrelevant.

## Overrides

Overrides replace the value of a macro, var, or env var **referenced directly in the tested
model's SQL**. One referenced only inside another macro the model calls is not overridden.

- **`is_incremental`**: MUST be set to `true` or `false` for an incremental model.
- **`dbt_utils.star`**: MUST be overridden with a comma-separated column list, for example
  `dbt_utils.star: col_a,col_b`; the mocked input replaces the `ref()`, so `star` cannot
  introspect a relation.
- Nondeterministic functions (`current_timestamp`, `invocation_id`, `run_started_at`): pin
  them (`macros: {invocation_id: 123}`; for a macro such as `dbt_utils.current_timestamp`
  give the literal) so expected rows are stable.
- Environment-gated logic: `overrides.vars` / `overrides.env_vars` flip it per test.

## Incremental Models

The expected output is **what the materialization will merge or insert**, not the final
table. Write two cases: `is_incremental: false` (full build) and `is_incremental: true`
with the current target mocked as a `given` input of `this`.

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

dbt cannot unit test whether the framework merged the rows correctly (dbt-labs/dbt-core
issue 8664); cover that with a data test or a dev diff against a full refresh
([snowflake-materializations.md](snowflake-materializations.md#late-arriving-and-multi-parent-changes)).
Cover same-day dedup, merge logic, and late child rows with the `true` case.

## Versioned Models

By default a unit test runs against **all** versions of the model. Pin with
`versions: {include: [2]}` or `exclude: [1]`. A new version with changed columns usually
needs its own case with different `expect` rows, so scope each case to the versions it
describes. See [contracts-and-versions.md](contracts-and-versions.md).

## Snowflake Value Gotchas

dbt casts your literal to the type inferred from the input/output models, so give values in
a form Snowflake can cast:

| Type | `dict` value |
|---|---|
| timestamp / timestamptz | `2013-11-03 00:00:00-0` (offset required for tz types) |
| escaped string | `"my,cool'string"` |
| variant | `3` |
| object | `{'Alberta':'Edmonton','Manitoba':'Winnipeg'}` |
| array | `['a','b','c']`, `[1, 2, 3]` |
| binary | hex string `19E1FFDCCB6CDEE788BF631C1C4905D1` |
| geography / geometry | `POINT(-122.35 37.55)` |

Unit tests assert values, not types. If a literal does not cast cleanly for a column type
(see [Platform-specific data types](https://docs.getdbt.com/reference/resource-properties/data-types)),
switch that input or `expect` to `format: sql` with an explicit `cast(...)`.

## Running Unit Tests

- Direct parents MUST already exist in the target schema so dbt can read column types. In a
  clean CI or dev schema, build empty shells **for the parents only**:
  `dbt run --select "<parent_a> <parent_b>" --empty`.
- **Incremental model with an `is_incremental: true` case:** dbt also reads columns from the
  model's own relation (`this`); on a fresh schema `dbt build` runs the unit test before the
  model and fails with `Not able to get columns for unit test '<model>'`
  ([dbt-core#10844](https://github.com/dbt-labs/dbt-core/issues/10844)). Make the first
  build pass: run `dbt run --select "<model>" --empty` (or
  `--select "config.materialized:incremental" --empty`) before the build in CI and fresh dev
  schemas, and prove it by building once from an empty schema.
- **`--empty` replaces the selected relations with zero-row versions.** NEVER combine it with
  a `+` upstream selector, and never aim it at a schema holding data you need. To cover all
  parents of one model use `--select "1+<model>" --exclude "<model>"` and only in a
  disposable schema. `dbt build --select "+<model>"` builds the parents for real instead,
  in lineage order with the unit tests before the model; use it when those builds are cheap.
- Commands: all unit tests `dbt test --select "test_type:unit"`; one model's
  `dbt test --select "<model>,test_type:unit"`; a single case `dbt test --select "<case>"`
  (or `unit_test:<case>`); generic data tests `dbt test --select "test_type:generic"`;
  by generic-test name `dbt test --select "test_name:<name>"`; list with
  `dbt list --select "unit_test:*"`.
- A unit test is one case: it passes (0) or fails (1) however many rows differ, and a failed
  case prints an `actual differs from expected` diff.
- Run them in development and CI only. Inputs are static, so production runs waste compute:
  `dbt build --exclude-resource-type unit_test` or `DBT_ENGINE_EXCLUDE_RESOURCE_TYPES=unit_test`
  (1.11+). For `dbt test`, `--select "test_type:data"` runs only data tests on both v1 and
  v2 (`--exclude-resource-type` works there on v1 only).
- A disabled model disables its unit tests (1.11+). On dbt v2, `dbt build` runs **all** unit
  tests first, before the rest of the DAG (v2 knows column types without existing parents).
  `compute: local` (v2, Snowflake/BigQuery, experimental, opt-in with
  `DBT_ENGINE_EXPERIMENTAL_LOCAL_UNIT_TESTS=true`) runs a test on DuckDB without warehouse
  compute; platform-specific functions can fail translation and a failed translation is a
  test failure.

## Limits

- Only SQL models of the **current** project; not Python models, snapshots, seeds, sources,
  analyses, or package models.
- Models using `materialized_view`, recursive SQL, or introspective queries cannot be unit
  tested.
- SQL `join` logic needs aliased tables.

## Checklist

- YAML under `model-paths`, not `tests/`; every `ref`/`source` mocked.
- `is_incremental` (and `dbt_utils.star`) overridden where used; ephemeral parents use `format: sql`.
- Parents built with `--empty` without `+`, never over data that matters.
- Incremental unit tests pass from an empty schema (model's own `--empty` shell pre-built).
- Unit tests excluded from production builds.
- A deliberately broken expectation fails, proving the test can fail.

## Sources

- [Unit tests](https://docs.getdbt.com/docs/build/unit-tests), [unit tests property](https://docs.getdbt.com/reference/resource-properties/unit-tests), [overrides](https://docs.getdbt.com/reference/resource-properties/unit-test-overrides), [data types](https://docs.getdbt.com/reference/resource-properties/data-types), [`--empty`](https://docs.getdbt.com/reference/commands/build#the---empty-flag), [`unit_test` / `test_type` selectors](https://docs.getdbt.com/reference/node-selection/methods).
- dbt Labs `adding-dbt-unit-test` skill (Apache-2.0).
