---
name: time-intelligence
description: Time intelligence reference — SPLY/SPLM/YoY/MoM via role-playing table aliases and computed-fact join keys that shift fact rows into the current period bucket.
parent_skill: sv-modeling-patterns
---

# Time Intelligence (SPLY, YoY, MoM)

## How it works

The pattern uses **role-playing logical table aliases** plus a **computed fact used as the join key** to shift fact rows into the current period bucket — no window functions, no `UNION ALL`, no pre-aggregated views.

Three parts:

1. **Role-playing alias** — the same physical fact table aliased as a new logical table (e.g. `sales_ly`).
2. **Computed fact used as the shifted join key** — a scalar expression on the physical date column: `expr: DATEADD('year', 1, SALE_MONTH)`.
3. **Relationship using the computed fact** as the join key — `left_column:` references the fact's logical name (not a raw column).

When a query filters `calendar.MONTH = '2024-03-01'`:

- `sales` returns rows where `SALE_MONTH = '2024-03-01'` (current period)
- `sales_ly` returns rows where `DATEADD('year',1, SALE_MONTH) = '2024-03-01'` → `SALE_MONTH = '2023-03-01'` (last year, aligned to the current bucket)

## Snippet

```yaml
tables:
  - name: calendar
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: DIM_CALENDAR }
    primary_key: { columns: [MONTH] }
    dimensions:
      - { name: month, expr: MONTH, data_type: DATE }
      - { name: year,  expr: YEAR,  data_type: NUMBER }

  - name: sales
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: FACT_SALES }
    primary_key: { columns: [ROW_ID] }
    facts:
      - { name: revenue, expr: REVENUE, data_type: NUMBER }
    metrics:
      - name: total_revenue
        expr: SUM(revenue)

  # Role-playing alias: same physical table as `sales`, joined via shifted date
  - name: sales_ly
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: FACT_SALES }
    primary_key: { columns: [ROW_ID] }
    facts:
      # Computed FK: shifts SALE_MONTH forward 1 year so 2023 rows
      # appear in 2024's calendar bucket. The fact's logical name
      # is what the relationship below references.
      - name: sale_month_shifted_ly
        expr: DATEADD('year', 1, SALE_MONTH)
        data_type: DATE
    metrics:
      - name: revenue_ly
        synonyms: [revenue last year, LY revenue, prior year revenue, SPLY]
        expr: SUM(REVENUE)

relationships:
  - name: sales_to_calendar
    left_table: sales
    right_table: calendar
    relationship_columns:
      - { left_column: SALE_MONTH, right_column: MONTH }

  # The computed fact's name appears here as left_column — the engine
  # evaluates DATEADD per row and uses the result to resolve the join.
  - name: sales_ly_to_calendar
    left_table: sales_ly
    right_table: calendar
    relationship_columns:
      - { left_column: sale_month_shifted_ly, right_column: MONTH }
```

## Gotchas

- **NULL for boundary periods.** `revenue_ly` is NULL for all rows in the earliest year of the dataset (no prior year to shift from). Wrap with `COALESCE(revenue_ly, 0)` if zero-fill is desired.
- **YTD / QTD / MTD are NOT supported by this pattern.** The shift is a fixed-period offset (1 month or 1 year), not a cumulative running total. For YTD use a window metric — see `window_metrics.md`.
- **Partial periods don't work.** "Q1 to date" mid-quarter requires additional calendar filtering — the shift is a full period.
- **Cross-entity derived metrics (`yoy_pct`, `mom_pct`) referencing metrics from both `sales` and `sales_ly`** are not supported by the SV engine. Compute the percentage at query time (in the SQL the agent issues, or downstream in the BI tool).
- **Cross-period region breakdowns work only when the breakdown dimension lives on the current-period entity** (e.g. `sales.region`). The SV applies it to `sales_ly` automatically because they share the same physical table. If a separate physical table or different join path is involved, define the dimension explicitly on the LY alias.

## Docs

- [Defining role-playing logical tables](https://docs.snowflake.com/en/user-guide/views-semantic/sql#defining-role-playing-logical-tables)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
