# Writing Data Tests in dbt

Write high-value tests that catch real data issues without burning warehouse credits on low-signal checks. Testing should drive action, not accumulate alerts.

> **Column names in this file are illustrative only.** Every team has its own schema and naming conventions. Always read the actual model files (`.sql` plus dbt YAML/properties files) to derive real column names, grain keys, and nullability before writing any test.

## Before Writing Tests

**Understand the model before writing any test.** How you do this depends on the task:

- **Task is `tests` only**: inspect the existing dbt YAML/properties files and model
  `.sql` file to understand grain, column types, and nullability. Do not write or
  modify docs.
- **Task is `both`**: follow [`writing-documentation.md`](writing-documentation.md)
  first, then use that output as the basis for tests.

Check that `dbt_utils` is installed in your `packages.yml` before using any `dbt_utils.*`
tests. If it is not, obtain authorized package-review approval before adding it; follow
the package-governance rules in [`general-dbt-guide.md`](general-dbt-guide.md).

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.0.0", "<2.0.0"]
```

Prefer `data_tests` in YAML. Use legacy `tests` only when the target project is pinned
to an older dbt style or already standardizes on it.

Put generic data-test arguments under `arguments:` only when the project runs dbt
>= 1.10.8, or 1.10.5-1.10.7 with `require_generic_test_arguments_property: true` in
`dbt_project.yml` `flags:` (default `false` there, so the nested form raises
`ArgumentsPropertyInGenericTestDeprecation`); otherwise keep them as top-level
properties of the test. Config (`severity`, `where`, `store_failures`, `warn_if`) stays
under `config:`. From 1.10.8 the flag defaults to `true`, so top-level parameters warn;
check the resolved dbt version and flag before choosing the form. This applies to the
`test_name:` long form too (`name`,
`test_name`, `arguments`, `config`). Keep singular SQL data tests under the project's
configured `test-paths`. Unit test YAML definitions belong under `model-paths`, not in
`test-paths` or `tests/`; unit test fixture files can still live in a `fixtures`
subdirectory under configured test paths.

Run unit tests in CI for changed logic. Prefer scoped selectors over global test runs:
`dbt test --select "test_type:unit"`, `dbt test --select "test_type:data"`, and, when
a prior manifest is available, `dbt test --select state:modified+ --state ./prod-manifest`.

Before a PR is merge-ready, relevant scoped dbt tests should pass with zero
error-level failures. At minimum, cover the documented grain or primary key with
`unique`/`not_null`, foreign keys with `relationships`, and verified controlled
categorical fields in marts with `accepted_values`.

## Grain and Uniqueness

"No duplicates" means no duplicates on the **grain key**, not necessarily on the entity key. Always declare the grain in the model description.

| Model type                           | Grain key                  | Test to use                                          |
| ------------------------------------ | -------------------------- | ---------------------------------------------------- |
| Point-in-time (standard)             | `entity_id`                | `unique` on that column                              |
| Historized / SCD                     | `entity_id + valid_from`   | `unique_combination_of_columns`                      |
| dbt snapshot                         | `entity_id + dbt_scd_id`   | `unique` on `dbt_scd_id`                             |
| Multi-dimensional (fact / analytics) | `dim1 + dim2 + ... + date` | `unique_combination_of_columns` on all grain columns |

Use `dbt_utils.unique_combination_of_columns` at model level whenever the grain spans
more than one column. Where `arguments:` is allowed (see above) put the grain columns
under `arguments.combination_of_columns`; otherwise use top-level
`combination_of_columns`.

## Where Tests Belong

Layer names vary by team (`stg`, `psa`, `bronze`, `raw`, `dwh`, `int`, `intermediate`, `silver`, `marts`, `dmt`, `gold`). Apply the logic below based on what each layer **does**, not what it is called.

| Layer                                                   | Purpose                          | Focus                                                  |
| ------------------------------------------------------- | -------------------------------- | ------------------------------------------------------ |
| Ingestion (`stg`, `psa`, `bronze`, `raw`)               | First contact with source data   | Structural integrity: PKs, FKs, accepted values, nulls |
| Transformation (`int`, `intermediate`, `silver`, `dwh`) | Joins, grain changes, enrichment | New composite keys, post-join uniqueness               |
| Consumption (`marts`, `dmt`, `gold`, `reporting`)       | End-user facing                  | Business invariants, calculated field correctness      |

Do not duplicate tests for pass-through columns; test each column where it first appears.

## Priority Framework

Tests are defined either at column level, under a specific column in `columns:`, or at
model level, under `data_tests:` directly on the model.

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

By default every test has `severity: error`, so a failure stops the run. Use
`severity: warn` only when a failure is informational and should not block.

| Tier                            | Severity          | Rationale                                                                      |
| ------------------------------- | ----------------- | ------------------------------------------------------------------------------ |
| Tier 1 (PK, FK)                 | `error`           | Data is broken; never let it pass downstream                                   |
| Tier 2 (nulls, accepted values) | `error` or `warn` | Use `error` when used in joins or calculations, `warn` when informational only |
| Tier 3 (business logic)         | `warn`            | Flag anomalies without blocking; investigate async                             |

Set severity via `config:` on the test. Use `warn_if` and `error_if` thresholds when a
small number of failures is acceptable but a large number indicates a real problem.

Projects that explicitly adopt the Data Quality Framework — dbt + Elementary invert the
key/null policy: they run PK/uniqueness and `not_null` as `warn` with
`store_failures: true` (advisory, but every failing row is captured for triage) and
reserve `error` for control-total and row-count reconciliation that must block
promotion. Apply this exception only to a project that explicitly adopts that named
framework. Keep `relationships`/FK tests at `error` unless that adopted framework's
documented policy explicitly changes them. Otherwise retain Tier 1 `error` severity; if
the project policy is unclear, ask before downgrading a blocking test.

## Document Debugging Steps

For simple tests (`unique`, `not_null`, `relationships`) no description is needed. For
complex tests (`expression_is_true`, `accepted_range`, custom business logic), add a
`description` with the first debugging steps so the failure acts as an inline runbook.

## Cost-Conscious Testing

For large tables, use test `config.where` to limit scope when a rolling window is enough.

## Reconciliation and Control Totals

For marts and other published models, reconcile against the upstream source to catch
silent row loss, double-counting, or broken joins that column tests miss. Use
`dbt_utils.equal_rowcount` (or `dbt_utils.fewer_rows_than`) for row-count parity, and a
custom `control_total` generic test to reconcile a summed measure between the model and
its source. Reconciliation failures usually mean the numbers are wrong, so run them at
`severity: error` (blocking). These same comparisons — row counts, summed measures,
distinct grain-key counts, and null rates — are the fastest way to validate a refactor
against the legacy relation before cutover.

For migration or SIT-style QA, package the recurring checks as reusable generic tests
instead of hand-writing SQL per object: row-count parity with an optional tolerance,
bidirectional `MINUS` (source-minus-target and target-minus-source) on the key/compare
columns, audit-column completeness, column/type parity against the upstream layer via
`information_schema`, SCD2 integrity (no more than one open version per key), and a
KPI-reconciliation macro. Drive them from `schema.yml` and a model `meta.grain` so
onboarding a new object is a short YAML edit, not new SQL.

## Persisting Failing Rows (store_failures)

Set `store_failures: true` so each failing test materializes its offending rows into a
dedicated audit schema (for example a `*_dq_failures` schema) for triage instead of only
reporting a count. This applies to `warn` tests too — severity controls pipeline impact,
not whether rows are stored. Set it once at project level (`data_tests: +store_failures:
true` with a `+schema:`) and add an `alias` on individual tests for a stable,
discoverable failure-table name (a `dq_` prefix helps). Failure tables are replaced on
each run, so they always reflect the latest state; use Elementary result history for
longitudinal trends.

## Common Mistakes

### Over-testing business logic

Test data assumptions, not whether every SQL expression ran. Prefer one critical
business invariant over many low-signal `expression_is_true` checks.

### Assuming you know the contents of a table

Never write `accepted_values` without checking real values via `dbt show` or a direct
query. Guessed enums create noisy tests and hide real source behavior.
