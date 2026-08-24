# Feature Store Troubleshooting Reference

## Diagnostic Queries

### Check Failed Refreshes
```sql
SELECT name, refresh_version, state, state_message, refresh_start_time
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
WHERE schema_name = '<FEATURE_STORE_SCHEMA>'
    AND state = 'FAILED'
ORDER BY refresh_start_time DESC;
```

### Check Dynamic Table Lag
```sql
SELECT
    name,
    target_lag,
    actual_lag,
    CASE WHEN actual_lag > target_lag THEN 'LAGGING' ELSE 'ON_TARGET' END AS lag_status
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE schema_name = '<FEATURE_STORE_SCHEMA>';
```

### Health Dashboard
```sql
SELECT
    name,
    scheduling_state,
    CASE
        WHEN scheduling_state = 'ACTIVE'
            AND DATEDIFF('minute', last_refresh_time, CURRENT_TIMESTAMP()) < 60
        THEN 'HEALTHY'
        WHEN DATEDIFF('minute', last_refresh_time, CURRENT_TIMESTAMP()) >= 60
        THEN 'STALE'
        ELSE 'WARNING'
    END AS health_status,
    target_lag,
    actual_lag
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE schema_name = '<FEATURE_STORE_SCHEMA>';
```

### Verify Change Tracking
```sql
SHOW TABLES LIKE '<TABLE_NAME>' IN <DATABASE>.<SCHEMA>;
-- Check the change_tracking column in results
```

### Check Refresh Performance
```sql
SELECT
    name,
    state,
    DATEDIFF('second', refresh_start_time, refresh_end_time) AS duration_seconds,
    statistics:numInsertedRows::INT AS rows_inserted,
    statistics:numUpdatedRows::INT AS rows_updated
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
WHERE schema_name = '<FEATURE_STORE_SCHEMA>'
ORDER BY refresh_start_time DESC
LIMIT 50;
```

### Cost Monitoring
```sql
SELECT
    name,
    SUM(DATEDIFF('second', refresh_start_time, refresh_end_time)) / 3600.0 AS approx_compute_hours,
    COUNT(*) AS refresh_count,
    AVG(DATEDIFF('second', refresh_start_time, refresh_end_time)) AS avg_refresh_seconds
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
WHERE schema_name = '<FEATURE_STORE_SCHEMA>'
GROUP BY name
ORDER BY approx_compute_hours DESC;
```

### Warehouse Credit Usage
```sql
SELECT warehouse_name, SUM(credits_used) AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE start_time > DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY warehouse_name
ORDER BY total_credits DESC;
```

### Object Dependencies
```sql
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCED_OBJECT_NAME LIKE '%FEATURE%'
ORDER BY REFERENCING_OBJECT_NAME;
```

### Feature View Lineage (SQL)
```sql
SELECT *
FROM TABLE(INFORMATION_SCHEMA.OBJECT_LINEAGE(
    '<DATABASE>.<SCHEMA>.<FEATURE_VIEW_NAME>',
    'dynamic_table'
));
```

---

## Incremental Refresh Blockers

| Blocker | Fix |
|---------|-----|
| `MODE()` | Replace with `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY COUNT(*) DESC)` in a separate FV |
| `RANDOM()`, `UUID()` | Remove or compute outside the FV |
| `CURRENT_DATE()`, `CURRENT_TIMESTAMP()` | Remove — compute at query/inference time instead (ODT) |
| Float-typed aggregation + JOINs | Split into aggregate-only FV (no JOINs) and a separate FV for joined lookups |
| Float-typed aggregation + CASE comparison | Cast INPUT columns to `DECIMAL` before aggregation: `AVG(COL::DECIMAL(10,2))` |
| `STDDEV()` / `AVG()` on float columns | Cast input to DECIMAL: `STDDEV(COL::DECIMAL(10,2))::DECIMAL(10,2)` |

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Full refresh instead of incremental | `MODE()` in query | Replace with ROW_NUMBER() ranked subquery in separate FV |
| Full refresh instead of incremental | Float aggregation + JOINs | Split into aggregate-only FV (no JOINs) |
| Full refresh instead of incremental | Float aggregation + CASE | Cast inputs to DECIMAL: `AVG(COL::DECIMAL(10,2))` |
| Full refresh instead of incremental | `CURRENT_DATE()` | Remove — compute at query time (ODT) |
| Full refresh instead of incremental | `RANDOM()`, `UUID()` | Remove non-deterministic functions |
| High refresh latency | Complex joins or large data | Increase warehouse size, optimize query |
| Permission denied | Missing privileges | Grant required privileges (see design-guide.md RBAC) |
| Feature view not found | Wrong database/schema context | Use fully qualified names |
| Database not authorized | Role can't access source | Use external FV (`refresh_freq=None`) or grant access |
| No "latest version" | No built-in alias | Sort version strings lexicographically (use V01, V02 zero-padded) |
| PIT retrieval wrong | Missing `timestamp_col` | Always set `timestamp_col` on FeatureView |
| Data leakage | Features from future | Validate: feature timestamps <= spine timestamp |
| MDT in FeatureView | Scaling/encoding in FV | Move to Model Registry Pipeline |
| Timestamp column error | timestamp_col in attach_feature_desc | Don't include timestamp_col in feature descriptions |
| Entity already exists | Duplicate registration | Warning only, registration continues |
| `state.upper()` fails | FeatureViewStatus is enum, not string | Use `"ACTIVE" in str(fv.status).upper()` |
| DT refresh fails after inference FV | Owner role mismatch | Inference FV must be owned by same role as source DTs, or GRANT SELECT |
| `resume_feature_view()` no effect | API may not trigger resume | Use `ALTER DYNAMIC TABLE <name> RESUME` directly |

---

## Warehouse Sizing

See [`design-guide.md#warehouse-sizing`](design-guide.md#warehouse-sizing) for the
complexity→size heuristic and recommended per-environment warehouse tiers. For
high refresh latency specifically, increasing the refresh warehouse size is the
first lever (see the refresh-issues table above).

---

## Quick Commands

```sql
SHOW DYNAMIC TABLES IN SCHEMA <feature_store_schema>;
ALTER DYNAMIC TABLE <feature_view_name> REFRESH;
ALTER DYNAMIC TABLE <feature_view_name> SUSPEND;
ALTER DYNAMIC TABLE <feature_view_name> RESUME;

SHOW ONLINE FEATURE TABLES IN SCHEMA <feature_store_schema>;

SHOW DATASETS IN SCHEMA <feature_store_schema>;
DESCRIBE DATASET <dataset_name>;

SHOW MODELS IN SCHEMA <model_schema>;
SHOW FUNCTIONS IN MODEL <db>.<schema>.<model> VERSION <ver>;
```
