# Time Window Filter

The time window filter for scheduled alerts ensures only new events are processed.

## Filter Pattern

```sql
AND timestamp >= GREATEST(
  TIMESTAMPADD('second', -60, COALESCE(
    CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.LAST_SUCCESSFUL_SCHEDULED_TIME())::TIMESTAMP_NTZ,
    TIMESTAMPADD('minute', -30, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.SCHEDULED_TIME())::TIMESTAMP_NTZ)
  )),
  TIMESTAMPADD('minute', -30, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.SCHEDULED_TIME())::TIMESTAMP_NTZ)
)
AND timestamp < TIMESTAMPADD('second', -60, CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.SCHEDULED_TIME())::TIMESTAMP_NTZ)
```

## Function Reference

| Function | Description |
|----------|-------------|
| `SNOWFLAKE.ALERT.LAST_SUCCESSFUL_SCHEDULED_TIME()` | When alert last ran successfully |
| `SNOWFLAKE.ALERT.SCHEDULED_TIME()` | Current scheduled execution time |
| `SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()` | Query UUID of condition results (for action block) |

## Why Each Part

### 60-second offset
```sql
TIMESTAMPADD('second', -60, ...)
```
Accounts for event table latency - events can take up to 2+ minutes to appear.

### COALESCE with 30-minute fallback
```sql
COALESCE(
  CONVERT_TIMEZONE('UTC', SNOWFLAKE.ALERT.LAST_SUCCESSFUL_SCHEDULED_TIME())::TIMESTAMP_NTZ,
  TIMESTAMPADD('minute', -30, ...)
)
```
Handles NULL when alert is newly created.

### GREATEST with 30-minute floor
```sql
GREATEST(..., TIMESTAMPADD('minute', -30, ...))
```
Prevents unbounded scans on:
- Newly created alerts
- Altered alerts with stale timestamps
- Long gaps between successful runs

## Not Used For

- **Alert on New Data** - Uses change tracking, not time filters
