# Writing Data Tests in dbt

High-value tests that catch real data issues without burning warehouse credits on low-signal checks. Governing principle: a test exists to drive action; every test costs compute and alert attention, so place each where the risk first appears and set severity by consequence.

> **Column names in this file are illustrative only.** Read the actual model files (`.sql` plus dbt YAML/properties) to derive real column names, grain keys, and nullability before writing any test.

## Before Writing Tests

**Understand the model first.** By task:

- **`tests` only:** inspect existing dbt YAML/properties and model `.sql` for grain, column types, nullability. Do not write or modify docs.
- **`both`:** follow [`writing-documentation.md`](writing-documentation.md) first; use its output as the basis for tests.

**`dbt_utils` check.** Confirm it is installed in `packages.yml` before any `dbt_utils.*` test. Absent → obtain authorized package-review approval before adding; follow the package-governance rules in [`general-dbt-guide.md`](general-dbt-guide.md).

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.0.0", "<2.0.0"]
```

**Syntax form:**

- Prefer `data_tests` in YAML; legacy `tests` only when the project is pinned to an older dbt style or already standardizes on it.
- **`arguments:`** for generic data-test arguments only when the project runs dbt >= 1.10.8, or 1.10.5-1.10.7 with `require_generic_test_arguments_property: true` in `dbt_project.yml` `flags:` (default `false` there; the nested form raises `ArgumentsPropertyInGenericTestDeprecation`). Otherwise keep them as top-level properties of the test. From 1.10.8 the flag defaults to `true`, so top-level parameters warn → check the resolved dbt version and flag before choosing the form. Applies to the `test_name:` long form too (`name`, `test_name`, `arguments`, `config`).
- Config (`severity`, `where`, `store_failures`, `warn_if`) stays under `config:`.
- **Paths:** singular SQL data tests under the project's configured `test-paths`. Unit test YAML belongs under `model-paths`, not `test-paths` or `tests/`; unit test fixture files can live in a `fixtures` subdirectory under configured test paths.

**Running:** unit tests in CI for changed logic; scoped selectors over global runs: `dbt test --select "test_type:unit"`, `dbt test --select "test_type:data"`, and with a prior manifest `dbt test --select state:modified+ --state ./prod-manifest`.

**Merge-ready:** relevant scoped dbt tests SHOULD pass with zero error-level failures. Minimum coverage: documented grain or primary key with `unique`/`not_null`; foreign keys with `relationships`; verified controlled categorical fields in marts with `accepted_values`.

## Grain and Uniqueness

"No duplicates" = no duplicates on the **grain key**, not necessarily the entity key. Declare the grain in the model description.

| Model type                           | Grain key                  | Test to use                                          |
| ------------------------------------ | -------------------------- | ---------------------------------------------------- |
| Point-in-time (standard)             | `entity_id`                | `unique` on that column                              |
| Historized / SCD                     | `entity_id + valid_from`   | `unique_combination_of_columns`                      |
| dbt snapshot                         | `entity_id + dbt_scd_id`   | `unique` on `dbt_scd_id`                             |
| Multi-dimensional (fact / analytics) | `dim1 + dim2 + ... + date` | `unique_combination_of_columns` on all grain columns |

Grain spans more than one column → `dbt_utils.unique_combination_of_columns` at model level. Where `arguments:` is allowed (above) put the grain columns under `arguments.combination_of_columns`; otherwise top-level `combination_of_columns`.

## Where Tests Belong

Layer names vary by team (`stg`, `psa`, `bronze`, `raw`, `dwh`, `int`, `intermediate`, `silver`, `marts`, `dmt`, `gold`). Apply by what the layer **does**, not what it is called.

| Layer                                                   | Purpose                          | Focus                                                  |
| ------------------------------------------------------- | -------------------------------- | ------------------------------------------------------ |
| Ingestion (`stg`, `psa`, `bronze`, `raw`)               | First contact with source data   | Structural integrity: PKs, FKs, accepted values, nulls |
| Transformation (`int`, `intermediate`, `silver`, `dwh`) | Joins, grain changes, enrichment | New composite keys, post-join uniqueness               |
| Consumption (`marts`, `dmt`, `gold`, `reporting`)       | End-user facing                  | Business invariants, calculated field correctness      |

**No duplicate tests on pass-through columns;** test each column where it first appears.

## Priority Framework

Tests are defined at column level (under a column in `columns:`) or model level (`data_tests:` directly on the model).

| Tier                   | When                                                    | Test                                                | Level  | Why                                        |
| ---------------------- | ------------------------------------------------------- | --------------------------------------------------- | ------ | ------------------------------------------ |
| **1 - Always**         | Primary key column                                      | `unique` + `not_null`                               | column | Broken PKs break everything downstream     |
| **1 - Always**         | Foreign key column                                      | `relationships`                                     | column | Catches broken joins early                 |
| **1 - Always**         | Grain spans multiple columns                            | `unique_combination_of_columns`                     | model  | Single-column `unique` won't work          |
| **2 - When warranted** | Enum column with known values (verified via `dbt show`) | `accepted_values`                                   | column | Catches new invalid values                 |
| **2 - When warranted** | Non-PK column confirmed 0% nulls                        | `not_null`                                          | column | Catches regressions                        |
| **3 - Selective**      | Multi-column business invariant                         | `expression_is_true`                                | model  | Detects subtle logic bugs                  |
| **3 - Selective**      | Constrained numeric/date range                          | `accepted_range`                                    | column | Avoids illogical values                    |
| **3 - Selective**      | Row count / measure total vs source (marts)             | `dbt_utils.equal_rowcount` / custom `control_total` | model  | Catches silent row loss or double-counting |
| **4 - Avoid**          | `not_null` on every column                              | n/a                                                 | n/a    | Low signal, high cost                      |
| **4 - Avoid**          | Multiple `expression_is_true` per model                 | n/a                                                 | n/a    | Expensive, hard to maintain                |
| **4 - Avoid**          | `unique` on non-PK columns                              | n/a                                                 | n/a    | Unnecessary and likely wrong               |

## Test Severity

Default `severity: error` → failure stops the run. `severity: warn` only when failure is informational and must not block.

| Tier                            | Severity          | Rationale                                                                      |
| ------------------------------- | ----------------- | ------------------------------------------------------------------------------ |
| Tier 1 (PK, FK)                 | `error`           | Data is broken; NEVER let it pass downstream                                   |
| Tier 2 (nulls, accepted values) | `error` or `warn` | Use `error` when used in joins or calculations, `warn` when informational only |
| Tier 3 (business logic)         | `warn`            | Flag anomalies without blocking; investigate async                             |

Set severity via `config:` on the test. `warn_if` / `error_if` thresholds when a small number of failures is acceptable but a large number signals a real problem.

**Data Quality Framework exception.** Projects that explicitly adopt the Data Quality Framework (dbt + Elementary) invert the key/null policy: PK/uniqueness and `not_null` run as `warn` with `store_failures: true` (advisory, every failing row captured for triage); `error` is reserved for control-total and row-count reconciliation that MUST block promotion. Apply only to a project that explicitly adopts that named framework. `relationships`/FK tests stay `error` unless that framework's documented policy explicitly changes them. Otherwise retain Tier 1 `error`; project policy unclear → ask before downgrading a blocking test.

## Document Debugging Steps

Simple tests (`unique`, `not_null`, `relationships`): no description. Complex tests (`expression_is_true`, `accepted_range`, custom business logic): add a `description` with first debugging steps so the failure acts as an inline runbook.

## Cost-Conscious Testing

Large tables: test `config.where` limits scope when a rolling window suffices.

## Reconciliation and Control Totals

Marts and other published models reconcile against the upstream source to catch silent row loss, double-counting, or broken joins that column tests miss. `dbt_utils.equal_rowcount` (or `dbt_utils.fewer_rows_than`) for row-count parity; a custom `control_total` generic test for a summed measure between model and source. Reconciliation failures usually mean wrong numbers → `severity: error` (blocking). The same comparisons — row counts, summed measures, distinct grain-key counts, null rates — are the fastest validation of a refactor against the legacy relation before cutover.

**Migration / SIT-style QA:** package recurring checks as reusable generic tests, not hand-written SQL per object:

- Row-count parity with optional tolerance.
- Bidirectional `MINUS` (source-minus-target and target-minus-source) on key/compare columns.
- Audit-column completeness.
- Column/type parity against the upstream layer via `information_schema`.
- SCD2 integrity (no more than one open version per key).
- KPI-reconciliation macro.

Drive them from `schema.yml` and a model `meta.grain` so onboarding a new object is a short YAML edit, not new SQL.

## Persisting Failing Rows (store_failures)

`store_failures: true` materializes each failing test's offending rows into a dedicated audit schema (e.g. a `*_dq_failures` schema) for triage instead of only a count. Applies to `warn` tests too — severity controls pipeline impact, not whether rows are stored. Set once at project level (`data_tests: +store_failures: true` with a `+schema:`); add an `alias` on individual tests for a stable, discoverable failure-table name (a `dq_` prefix helps). Failure tables are replaced each run → always the latest state; use Elementary result history for longitudinal trends.

## Common Mistakes

- **Over-testing business logic.** Test data assumptions, not whether every SQL expression ran. One critical business invariant beats many low-signal `expression_is_true` checks.
- **Assuming table contents.** NEVER write `accepted_values` without checking real values via `dbt show` or a direct query; guessed enums create noisy tests and hide real source behavior.
