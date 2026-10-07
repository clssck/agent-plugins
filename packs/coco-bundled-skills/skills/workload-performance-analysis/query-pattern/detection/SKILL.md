# Query Pattern Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Identify outlier executions within a query pattern and surface insights about performance variability.

## Prerequisites

- Pattern statistics already fetched by `query-pattern/summary/SKILL.md`

## Workflow

### Step 1: Identify Outliers

Find executions that deviate significantly from the pattern:

```sql
SELECT
    query_id,
    user_name,
    warehouse_name,
    warehouse_size,
    ROUND(execution_time / 1000.0, 2) AS execution_seconds,
    ROUND(bytes_spilled_to_local_storage / 1024.0 / 1024 / 1024, 2) AS local_spill_gb,
    ROUND(bytes_spilled_to_remote_storage / 1024.0 / 1024 / 1024, 2) AS remote_spill_gb,
    ROUND(percentage_scanned_from_cache * 100, 1) AS cache_hit_pct,
    start_time,
    LEFT(query_text, 100) AS query_preview
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_parameterized_hash = '<HASH>'
  AND start_time >= DATEADD('day', -7, CURRENT_DATE())
ORDER BY execution_time DESC
LIMIT 10;
```

Present:
```
### Slowest Executions of This Pattern

| Query ID | User | Warehouse | Size | Execution (s) | Spill (GB) | Cache Hit | Start Time |
```

### Step 2: Historical Trend Analysis

```sql
SELECT
    COUNT(*) AS total_executions,
    SUM(CASE WHEN execution_status = 'SUCCESS' THEN 1 ELSE 0 END) AS success_count,
    SUM(CASE WHEN execution_status != 'SUCCESS' THEN 1 ELSE 0 END) AS failed_count,
    COUNT(DISTINCT warehouse_name) AS distinct_warehouses,
    MODE(error_code) AS most_common_error_code,
    MAX_BY(error_message, start_time) AS latest_error_message
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_parameterized_hash = '<HASH>'
  AND start_time >= DATEADD('day', -7, CURRENT_DATE());
```

Key patterns to surface:
- **Failure rate**: If `failed_count / total_executions > 5%`, highlight with most common error
- **Multiple warehouses**: Performance may vary by warehouse size — correlate with outliers

### Step 3: Insights

1. **Variability** — If stddev is high relative to avg, the pattern has inconsistent performance. Possible causes:
   - Different warehouse sizes across executions
   - Different data volumes (literal values hitting different partition ranges)
   - Concurrency effects (queue time differences)
2. **Frequency** — High execution count with poor performance = high-impact optimization target
3. **Spilling pattern** — If most executions spill, the pattern itself needs a larger warehouse

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.
