---
name: fact-as-relationship-key
description: Computed-FK reference — declare a fact as a scalar expression on row-level columns and reference its logical name as left_column in a relationship when no physical FK column exists on the source table.
parent_skill: sv-modeling-patterns
---

# Fact as Relationship Key

## How it works

When the join key you need does not exist as a physical column on the fact table, derive it as a **fact** (scalar expression on physical columns) and use that fact's logical name as the `left_column` in the relationship.

Example: `sales` has `sale_date` but no `fiscal_quarter_key`. Compute `fiscal_qtr_key = CONCAT(YEAR(sale_date), '-Q', QUARTER(sale_date))` as a fact, then reference it from the relationship. The engine evaluates the expression per row at query time.

Two pieces:

1. **Computed fact** — `expr: CONCAT(...)` — must be a scalar (row-level) expression, not an aggregation.
2. **Relationship referencing the fact's logical name** as `left_column` — the right side must point to a declared `primary_key` on the target.

## Snippet

```yaml
tables:
  - name: fiscal_quarters
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: FISCAL_QUARTERS }
    primary_key: { columns: [FISCAL_QUARTER_KEY] }
    dimensions:
      - { name: quarter_name, expr: QUARTER_NAME, data_type: VARCHAR }
      - { name: fiscal_year,  expr: FISCAL_YEAR,  data_type: NUMBER }
    metrics:
      - name: total_budget
        expr: SUM(BUDGET_AMOUNT)

  - name: sales
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: SALES }
    primary_key: { columns: [SALE_ID] }
    facts:
      # Computed FK fact: derives the join key from sale_date.
      # Must be a scalar (row-level) expression.
      - name: fiscal_qtr_key
        expr: "CONCAT(TO_VARCHAR(YEAR(sale_date)), '-Q', TO_VARCHAR(QUARTER(sale_date)))"
        data_type: VARCHAR
    metrics:
      - name: total_revenue
        expr: SUM(amount)

relationships:
  - name: sales_to_quarters
    left_table: sales
    right_table: fiscal_quarters
    relationship_columns:
      # The fact's logical name appears here — the engine evaluates
      # CONCAT(YEAR, '-Q', QUARTER) per row and uses the result.
      - left_column: fiscal_qtr_key
        right_column: FISCAL_QUARTER_KEY
```

## Gotchas

- **The computed fact is not queryable as a metric or dimension.** It exists only to power the join. Don't expose it to end users.
- **Aggregation expressions are not valid as join keys.** `SUM(...)`, `COUNT(...)`, etc. fail. The fact must be a row-level scalar.
- **The referenced table must have a matching `primary_key`** (or it must be implicit). The right-hand side of the relationship must resolve to a declared PK on the target.
- **Same mechanism powers `time_intelligence`'s shifted joins** (`DATEADD('year', 1, SALE_MONTH)` as a computed FK). If you understand this pattern, that one is just a date-shift application of the same idea.

## Docs

- [Defining facts, dimensions, and metrics](https://docs.snowflake.com/en/user-guide/views-semantic/sql#defining-facts-dimensions-and-metrics)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
