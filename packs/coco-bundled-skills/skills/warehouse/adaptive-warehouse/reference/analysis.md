# Adaptive Warehouse Analysis Queries

## Time-Series Performance by Warehouse Type

Produces a time series of warehouse-level performance data for any warehouse that ran at least one query in ADAPTIVE state within the last 7 days:

```sql
WITH adaptive_whs AS (
  SELECT DISTINCT warehouse_name
  FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q
  WHERE q.warehouse_size = 'ADAPTIVE'
    AND q.start_time >= DATEADD(day, -7, CURRENT_DATE())
)
SELECT
  q.end_time::DATE AS ds,
  q.warehouse_name,
  IFF(q.warehouse_size = 'ADAPTIVE', 'ADAPTIVE', 'STANDARD') AS warehouse_type,
  AVG(q.total_elapsed_time) AS avg_query_time,
  AVG(q.execution_time) AS avg_exec_time,
  AVG(q.queued_overload_time) AS avg_queued_overload_time,
  AVG(q.queued_provisioning_time) AS avg_queued_provisioning_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q
WHERE q.start_time >= DATEADD(day, -7, CURRENT_DATE())
  AND q.warehouse_name IN (SELECT warehouse_name FROM adaptive_whs)
GROUP BY ALL;
```

Use `avg_queued_overload_time` to assess whether to increase `QUERY_THROUGHPUT_MULTIPLIER`, and `avg_query_time` to assess whether to adjust `MAX_QUERY_PERFORMANCE_LEVEL`.