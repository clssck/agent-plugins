# Cache Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Analyze local disk cache (warehouse cache) utilization patterns and surface insights about poor cache performance. This sub-skill covers the local disk cache on compute node SSD/memory only — NOT the query result cache or metadata cache.

**Terminology**: Mirror the user's term. If the user says "local disk cache", use that. If "warehouse cache", use that. Both refer to the same cache.

## Prerequisites

- Cache summary data already presented by `cache/summary/SKILL.md`

## Scope-Aware Mode (when invoked from QUERY_SET)

If the caller passed scope params (`<ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`), operate in **scope-aware mode** — restrict the cache analysis to the user's query set:
- Replace `Warehouses with bad cache hit rates and significant scan and query volume` with `Warehouses with bad cache hit rates and significant scan and query volume — scoped to query set`.
- The scoped variant adds a `HAVING COUNT(*) >= 5` noise floor for parity with the unscoped variant's "significant query volume" requirement.

**In scope-aware mode:**
- The "summary already presented" prerequisite is **relaxed** — the QUERY_SET scope card replaces this sub-skill's own Phase-1 summary. Do NOT require `cache/summary/SKILL.md` to have run first.
- **Suppress the per-step `[STOP]`** — orchestration belongs to QUERY_SET.
- Skip re-presenting Phase-1 warehouse-level cache totals; focus on insights about cold-cache patterns within the set.

When invoked outside QUERY_SET (no scope params), behave exactly as before.

## Workflow

### Step 1: Check Warehouse Configuration

For warehouses with low cache hit rates from the summary, check auto-suspend settings:

```sql
SHOW WAREHOUSES LIKE '<WAREHOUSE_NAME>';
```

Check the `auto_suspend` column (in seconds):

- **Low auto-suspend (60s or less)**: Warehouse suspends quickly, evicting the local disk cache. This is a common cause of low cache hit rates for warehouses with regular query patterns.
- **High auto-suspend (300s+)**: Auto-suspend is not the issue — look at query patterns or DML activity instead.

Present:
```
### Warehouse Configuration

| Warehouse | Size | Auto-Suspend (s) | Auto-Resume | State |
```

### Step 2: Query Arrival Pattern

For warehouses with low auto-suspend (from Step 1), measure how frequently queries arrive — this determines whether increasing auto-suspend would actually help:

```sql
WITH query_times AS (
    SELECT
        start_time,
        LAG(start_time) OVER (ORDER BY start_time) AS prev_start_time
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE warehouse_name = '<WAREHOUSE_NAME>'
      AND start_time >= DATEADD('day', -3, CURRENT_DATE())
      AND bytes_scanned > 0
)
SELECT
    COUNT(*) AS total_queries,
    ROUND(AVG(DATEDIFF('second', prev_start_time, start_time)), 0) AS avg_gap_seconds,
    ROUND(MEDIAN(DATEDIFF('second', prev_start_time, start_time)), 0) AS median_gap_seconds,
    ROUND(PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY DATEDIFF('second', prev_start_time, start_time)), 0) AS p90_gap_seconds,
    MIN(DATEDIFF('second', prev_start_time, start_time)) AS min_gap_seconds,
    MAX(DATEDIFF('second', prev_start_time, start_time)) AS max_gap_seconds
FROM query_times
WHERE prev_start_time IS NOT NULL;
```

Interpret results relative to the current `auto_suspend` value:

- **Median gap < auto_suspend**: Most queries arrive before the warehouse suspends — cache should already be warm. Low cache hit is likely due to different data being scanned, not auto-suspend.
- **Median gap > auto_suspend but < 10 min**: The warehouse is suspending between queries. Increasing auto-suspend to cover the median gap would keep cache warm.
- **Median gap >> auto_suspend (e.g., hours)**: Queries are too infrequent for cache to help. Increasing auto-suspend would just waste idle credits.

Present:
```
### Query Arrival Pattern

| Warehouse | Auto-Suspend (s) | Median Gap (s) | P90 Gap (s) | Avg Gap (s) | Verdict |
```

### Step 3: Insights

After reviewing the summary data, provide:

1. **Key patterns** — which warehouses have the lowest cache utilization
2. **Common causes of low cache hit rates:**
   - Irregular query patterns — queries access different data each time
   - Queries on frequently changing data — cache invalidated by DML operations
   - Insufficient query repetition — cache not warmed up
   - Large result sets exceeding cache capacity
   - Frequent DDL operations (ALTER TABLE, etc.) invalidating cache
3. **Severity assessment:**
   - Warehouses with < 20% cache hit and high GB scanned = high impact
   - Warehouses with low query count may just lack cache warmup opportunity

### Step 4: Offer Drill-Down

If a specific warehouse has notably poor cache, offer to:
- Show the query mix on that warehouse to understand access patterns
- Analyze specific queries at operator level for cache metrics

**Operator-level cache drill-down** (requires query ID, 14-day retention via `GET_QUERY_OPERATOR_STATS`):

```sql
SELECT
    operator_id,
    operator_type,
    operator_statistics:io.bytes_scanned::NUMBER AS bytes_scanned,
    ROUND(operator_statistics:io.percentage_scanned_from_cache::NUMBER * 100, 1) AS cache_hit_pct,
    operator_attributes:table_name::STRING AS table_name
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
WHERE operator_type = 'TableScan'
ORDER BY operator_statistics:io.bytes_scanned::NUMBER DESC;
```

Present:
```
### Operator-Level Cache Metrics: <QUERY_ID>

| Operator | Type | Bytes Scanned | Cache Hit % | Table |
|---|---|---|---|---|
| <id> | TableScan | <bytes> | <pct>% | <table_name> |
```

This reveals which specific table scans had cache hits vs. misses, helping identify whether the problem is a single large uncached table or a general cache warmup issue.

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.
