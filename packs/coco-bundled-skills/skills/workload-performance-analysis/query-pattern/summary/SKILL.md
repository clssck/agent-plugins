# Query Pattern Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Identify a query pattern by its `query_parameterized_hash`, aggregate execution statistics, and present a high-level overview.

## Background

The `query_parameterized_hash` column in `QUERY_HISTORY` contains a hash computed after parameterizing all literals in comparison predicates (=, !=, >=, <=, >, <). Queries with identical structure but different literal values will share the same hash.

Example — these have the same `query_parameterized_hash`:
```sql
SELECT * FROM orders WHERE customer_id = 'TIM'
SELECT * FROM orders WHERE customer_id = 'AIHUA'
```

Also available in: `AGGREGATE_QUERY_HISTORY`, `TABLE_QUERY_PRUNING_HISTORY`, `COLUMN_QUERY_PRUNING_HISTORY`.

## Prerequisites

- A `query_parameterized_hash` value (provided by user, or extracted from a query ID)
- Access to `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`

## Workflow

### Step 1: Aggregate Pattern Statistics

```sql
SELECT
    query_parameterized_hash,
    COUNT(*) AS execution_count,
    COUNT(DISTINCT user_name) AS distinct_users,
    COUNT(DISTINCT warehouse_name) AS distinct_warehouses,
    MAX_BY(warehouse_name, start_time) AS latest_warehouse,
    MAX_BY(warehouse_size, start_time) AS latest_warehouse_size,
    MAX_BY(user_name, start_time) AS latest_user,
    ROUND(AVG(execution_time) / 1000.0, 2) AS avg_execution_seconds,
    ROUND(MEDIAN(execution_time) / 1000.0, 2) AS median_execution_seconds,
    ROUND(MAX(execution_time) / 1000.0, 2) AS max_execution_seconds,
    ROUND(MIN(execution_time) / 1000.0, 2) AS min_execution_seconds,
    ROUND(STDDEV(execution_time) / 1000.0, 2) AS stddev_execution_seconds,
    ROUND(AVG(total_elapsed_time) / 1000.0, 2) AS avg_elapsed_seconds,
    ROUND(SUM(COALESCE(bytes_spilled_to_local_storage, 0)) / 1024.0 / 1024 / 1024, 2) AS total_local_spill_gb,
    ROUND(SUM(COALESCE(bytes_spilled_to_remote_storage, 0)) / 1024.0 / 1024 / 1024, 2) AS total_remote_spill_gb,
    ROUND(AVG(percentage_scanned_from_cache) * 100, 1) AS avg_cache_hit_pct,
    ROUND(AVG(bytes_scanned) / 1024.0 / 1024 / 1024, 2) AS avg_gb_scanned,
    MIN(start_time) AS first_seen,
    MAX(start_time) AS last_seen,
    LEFT(MAX_BY(query_text, start_time), 200) AS sample_query_text
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_parameterized_hash = '<HASH>'
  AND start_time >= DATEADD('day', -7, CURRENT_DATE())
GROUP BY query_parameterized_hash;
```

### Step 2: Present Pattern Summary

```
## Query Pattern Analysis

**Pattern Hash:** <hash>
**Sample Query:** <truncated SQL>

### Execution Profile (Last 7 Days)

| Metric | Value |
|---|---|
| Execution Count | X |
| Distinct Users | X |
| Distinct Warehouses | X |
| Latest Warehouse | NAME (SIZE) |
| First Seen | <timestamp> |
| Last Seen | <timestamp> |

### Performance Distribution

| Metric | Avg | Median | Min | Max | StdDev |
|---|---|---|---|---|---|
| Execution Time (s) | X | X | X | X | X |

### Resource Usage (Totals)

| Metric | Value |
|---|---|
| Avg GB Scanned | X |
| Avg Cache Hit | X% |
| Total Local Spilling | X GB |
| Total Remote Spilling | X GB |
```

**[STOP]** Present the pattern summary. Ask: "Want me to identify outliers and performance trends, or provide recommendations?"
