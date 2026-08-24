---
name: semi-additive-metric
description: Semi-additive metric reference — non_additive_dimensions on a metric prevents summing snapshot facts (balances, headcount, inventory) across time so totals don't double-count.
parent_skill: sv-modeling-patterns
---

# Semi-Additive Metric

## How it works

A snapshot fact (account balance, headcount, inventory) records a value at a point in time. Summing across **accounts** on the same date is correct. Summing across **dates** double-counts: a balance of $1,000 on Monday and $1,000 on Tuesday is still $1,000, not $2,000.

`non_additive_dimensions` marks a metric as non-aggregatable across the named time dimension. When `balance_date` is in the query's dimensions, the metric sums across other dimensions for that date. When `balance_date` is absent, the engine refuses to sum across all dates — instead it returns the metric grouped by date internally.

You typically need **two metrics** with non-overlapping synonyms:

- One metric with `non_additive_dimensions` for point-in-time totals (e.g. `total_balance`).
- One plain `AVG` metric for trends (e.g. `avg_daily_balance`).

You cannot apply `AVG()` to a non-additive metric — they are separate operations on the underlying fact, not composable.

## Snippet

```yaml
tables:
  - name: balances
    base_table: { database: TARGET_DB, schema: TARGET_SCHEMA, table: ACCOUNT_BALANCES }
    primary_key: { columns: [ACCOUNT_ID, BALANCE_DATE] }
    dimensions:
      - { name: balance_date, expr: BALANCE_DATE, data_type: DATE }
    metrics:
      - name: total_balance
        synonyms:
          [current balance, balance as of date, snapshot balance,
           end of day balance, point in time balance, balance on hand]
        description: Sum across accounts at a point in time. Always group by balance_date.
        expr: SUM(BALANCE_USD)
        # Prevents the engine from summing across balance_date.
        # When balance_date is missing from the query, the engine
        # returns date-level rows internally rather than collapsing them.
        non_additive_dimensions:
          - table: balances
            dimension: balance_date
            sort_direction: ascending
            null_order: last

      - name: avg_daily_balance
        synonyms:
          [average balance, average daily balance, mean balance,
           typical balance, balance trend]
        description: Average balance across snapshot periods.
        expr: AVG(BALANCE_USD)
```

## Gotchas

- **Double-counting if you forget `non_additive_dimensions`.** A naive `SUM(balance)` across a snapshot table inflates by the number of snapshot dates. This is the silent failure the pattern prevents.
- **You need two metrics, not one.** `AVG()` cannot be applied to a non-additive metric. Define `total_balance` (with `non_additive_dimensions` + `SUM`) for point-in-time, and `avg_daily_balance` (`AVG`) for trends.
- **Synonym discipline matters.** If both metrics mention "balance" without intent qualifiers, the AI may pick the wrong one. Use intent-oriented synonyms: `total_balance` → "current balance", "snapshot balance", "balance as of"; `avg_daily_balance` → "average", "trend", "typical".
- **Always include the time dimension or filter on it** when querying the non-additive metric. Otherwise the engine returns date-level rows internally, which can surprise users expecting a single number.

## Docs

- [Identifying the dimensions that should be non-additive for a metric](https://docs.snowflake.com/en/user-guide/views-semantic/sql#identifying-the-dimensions-that-should-be-non-additive-for-a-metric)
- [YAML specification for semantic views](https://docs.snowflake.com/en/user-guide/views-semantic/semantic-view-yaml-spec)
