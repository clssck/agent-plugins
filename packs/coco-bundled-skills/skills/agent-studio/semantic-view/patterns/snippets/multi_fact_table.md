---
name: multi-fact-table
description: Multi-fact-table reference — multiple independent facts (store_sales, web_sales, returns) joined via shared dimensions (product, date), with cross-fact derived metrics (gross, net).
parent_skill: sv-modeling-patterns
---

# Multi-Fact Table

## How it works

Multiple independent fact tables share common dimensions in one SV. Each fact has its own metrics; cross-fact derived metrics combine them (`total_gross = store + web`; `net = gross - returns`).

The pattern:

1. **Each fact is a separate entry in `tables:`.**
2. **Each fact joins to the shared dimensions** via its own relationships (`store_to_date`, `web_to_date`, `returns_to_date`, ...).
3. **Cross-fact derived metrics** live at the top-level `metrics:` block and reference metrics from multiple fact entities by their entity-prefixed names.

The engine is selective: querying only `store_revenue` does not join `channel_web_sales`. Querying `total_gross_revenue` triggers joins/aggregation across both. `SHOW SEMANTIC DIMENSIONS FOR METRIC store_revenue` returns only dims reachable via `store_sales`'s relationships.

## Snippet

```yaml
tables:
  - name: dim_product
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: DIM_PRODUCT }
    primary_key: { columns: [PRODUCT_ID] }

  - name: channel_dim_date
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: DIM_DATE }
    primary_key: { columns: [DATE_ID] }

  - name: channel_store_sales
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: STORE_SALES }
    metrics:
      - { name: store_revenue, expr: SUM(REVENUE) }

  - name: channel_web_sales
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: WEB_SALES }
    metrics:
      - { name: web_revenue, expr: SUM(REVENUE) }

  - name: channel_returns
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: RETURNS }
    metrics:
      - { name: total_returns, expr: SUM(AMOUNT) }

# Each fact joins to BOTH shared dimensions
relationships:
  - { name: store_to_date,    left_table: channel_store_sales, right_table: channel_dim_date,
      relationship_columns: [{ left_column: DATE_ID, right_column: DATE_ID }] }
  - { name: store_to_product, left_table: channel_store_sales, right_table: dim_product,
      relationship_columns: [{ left_column: PRODUCT_ID, right_column: PRODUCT_ID }] }
  - { name: web_to_date,      left_table: channel_web_sales,   right_table: channel_dim_date,
      relationship_columns: [{ left_column: DATE_ID, right_column: DATE_ID }] }
  - { name: web_to_product,   left_table: channel_web_sales,   right_table: dim_product,
      relationship_columns: [{ left_column: PRODUCT_ID, right_column: PRODUCT_ID }] }
  - { name: returns_to_date,    left_table: channel_returns,   right_table: channel_dim_date,
      relationship_columns: [{ left_column: DATE_ID, right_column: DATE_ID }] }
  - { name: returns_to_product, left_table: channel_returns,   right_table: dim_product,
      relationship_columns: [{ left_column: PRODUCT_ID, right_column: PRODUCT_ID }] }

# Cross-fact derived metrics — top-level, NOT nested inside any tables[].metrics
metrics:
  - name: total_gross_revenue
    expr: channel_store_sales.store_revenue + channel_web_sales.web_revenue
  - name: net_revenue
    expr: total_gross_revenue - channel_returns.total_returns
```

## Gotchas

- **The engine is selective about joins.** Don't worry that listing 3 facts means every query joins all 3 — querying `store_revenue` alone joins only `channel_store_sales` and the dims it actually uses.
- **Cross-fact derived metrics trigger joins across all referenced facts.** `total_gross_revenue` requires both `channel_store_sales` and `channel_web_sales` to be joined to a common dimension grain. Make sure both facts share the dimension you group by.
- **Each fact must join independently to shared dims.** You cannot rely on `store → web → product` transitively; declare `store → product` and `web → product` directly.
- **Beware fan traps.** If a metric is at a coarser grain than the dimension you group by, the engine will refuse the query. See `sv_diagnostics.md` (#2 Fan Trap).
- **`SHOW SEMANTIC DIMENSIONS FOR METRIC <m>`** is a useful diagnostic: it lists only the dimensions reachable from that metric's fact via the declared relationships.

## Docs

- [Using semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/sql)
- [Defining derived metrics (cross-fact totals)](https://docs.snowflake.com/en/user-guide/views-semantic/sql#defining-derived-metrics)
