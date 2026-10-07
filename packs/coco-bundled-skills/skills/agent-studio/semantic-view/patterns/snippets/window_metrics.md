---
name: window-metrics
description: Window metric reference — rolling averages, LAG (prior-period), and YTD cumulative totals via window functions inside metric expressions.
parent_skill: sv-modeling-patterns
---

# Window Metrics (LAG, Rolling Average, YTD)

## How it works

Window metrics use SQL window functions (`AVG OVER`, `LAG`, `SUM OVER`) inside metric expressions to span time. Three patterns:

1. **Rolling average** — `AVG(metric) OVER (... ORDER BY date RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW)` for a 7-day moving average.
2. **LAG** — `LAG(metric, n) OVER (... ORDER BY date)` returns the value `n` rows ago in the same partition. NULL for the first `n` rows.
3. **YTD cumulative sum** — `SUM(metric) OVER (PARTITION BY year ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`. The `PARTITION BY year` resets the running total at each year boundary.

Spell out the partition columns explicitly. If users may add new dimensions later, list them all in `PARTITION BY` so each combination gets its own window.

## Snippet

```yaml
tables:
  - name: daily_sales
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: DAILY_SALES }
    primary_key: { columns: [SALE_DATE, CHANNEL] }
    dimensions:
      - { name: sale_date, expr: SALE_DATE, data_type: DATE }
      - { name: channel,   expr: CHANNEL,   data_type: VARCHAR }
    metrics:
      - name: total_revenue
        expr: SUM(REVENUE)

      - name: rolling_7d_avg_revenue
        synonyms: [7 day rolling average, 7-day avg, weekly rolling average]
        expr: >
          AVG(SUM(REVENUE))
          OVER (PARTITION BY CHANNEL
                ORDER BY SALE_DATE
                RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW)

      - name: revenue_30d_ago
        synonyms: [revenue 30 days ago, lag 30 day revenue]
        expr: >
          LAG(SUM(REVENUE), 30)
          OVER (PARTITION BY CHANNEL
                ORDER BY SALE_DATE)

      - name: ytd_revenue
        synonyms: [year to date revenue, YTD revenue, cumulative revenue]
        expr: >
          SUM(SUM(REVENUE))
          OVER (PARTITION BY YEAR(SALE_DATE), CHANNEL
                ORDER BY SALE_DATE
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
```

## Gotchas

- **Window metrics require their `ORDER BY` dimension in the query's dimensions** — otherwise the engine has nothing to order by.
- **Always include `PARTITION BY`** with window metrics. Bare `OVER (ORDER BY ...)` with `ROWS BETWEEN n PRECEDING` fails: `Unsupported expression in the definition of derived metric.`
- **`LAG(n)` returns NULL for the first n rows** — expected behavior, but surfaces as missing data in the earliest period.
- **Spell out every partitioning dimension.** If you later add a new dimension (e.g. `region`) and want each region to have its own window, you must edit the metric to add it to `PARTITION BY`.
- **YTD vs `time_intelligence`**: this pattern is for cumulative running totals (YTD/QTD/MTD). For point-in-time period comparisons (SPLY, YoY%) use `time_intelligence.md` — different mechanism (role-playing alias + computed FK) and different output semantics.

## Docs

- [Defining and querying window function metrics](https://docs.snowflake.com/en/user-guide/views-semantic/querying#defining-and-querying-window-function-metrics)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
