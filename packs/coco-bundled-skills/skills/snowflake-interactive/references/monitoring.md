# Monitoring Queries

SQL queries for monitoring interactive tables and warehouses.

---

## Warehouse Monitoring

### Check Warehouse State

```sql
SHOW WAREHOUSES;
SHOW WAREHOUSES LIKE '%iwh%';
```

### Warehouse Details

```sql
SELECT 
  "name" AS warehouse_name,
  "state" AS current_state,
  "type" AS warehouse_type,
  "size" AS warehouse_size,
  "min_cluster_count",
  "max_cluster_count",
  "running" AS queries_running,
  "queued" AS queries_queued
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
ORDER BY "name";
```

---

## Table Monitoring

### Check Tables

```sql
SHOW TABLES;
SHOW TABLES LIKE 'my_table%';
```

### Table Metadata

```sql
SELECT 
  table_catalog,
  table_schema,
  table_name,
  table_type,
  row_count,
  bytes,
  clustering_key
FROM INFORMATION_SCHEMA.TABLES
WHERE table_schema = 'MY_SCHEMA'
ORDER BY created DESC;
```

---

## Pipe Monitoring (Streaming)

### Check Pipes

```sql
SHOW PIPES IN SCHEMA my_schema;
DESC PIPE my_streaming_table;
```

---

## Credit Usage (Account Usage)

### Warehouse Credits (Last 7 Days)

```sql
SELECT 
  warehouse_name,
  DATE(start_time) AS usage_date,
  SUM(credits_used) AS total_credits,
  COUNT(*) AS num_queries
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name LIKE '%IWH%'
  AND start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
GROUP BY warehouse_name, DATE(start_time)
ORDER BY warehouse_name, usage_date DESC;
```

---

## Query Performance

### Recent Queries

```sql
SELECT 
  query_id,
  LEFT(query_text, 100) AS query_preview,
  warehouse_name,
  total_elapsed_time AS duration_ms,
  execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name LIKE '%IWH%'
  AND start_time >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
ORDER BY start_time DESC
LIMIT 100;
```

### Timeout Analysis

```sql
SELECT 
  query_id,
  LEFT(query_text, 100) AS query_preview,
  warehouse_name,
  error_message
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name LIKE '%IWH%'
  AND execution_status = 'FAILED'
  AND error_message LIKE '%timeout%'
  AND start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
ORDER BY start_time DESC;
```

### Average Query Duration

```sql
SELECT 
  warehouse_name,
  COUNT(*) AS query_count,
  AVG(total_elapsed_time) AS avg_duration_ms,
  MAX(total_elapsed_time) AS max_duration_ms
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name LIKE '%IWH%'
  AND execution_status = 'SUCCESS'
  AND start_time >= DATEADD(day, -7, CURRENT_TIMESTAMP())
GROUP BY warehouse_name;
```

---

## Data Freshness Check

### Compare Source vs Interactive

```sql
SELECT 
  'Source' AS table_type,
  COUNT(*) AS row_count
FROM source_table

UNION ALL

SELECT 
  'Interactive' AS table_type,
  COUNT(*) AS row_count
FROM interactive_table;
```

### Check Sync Percentage

```sql
SELECT 
  s.row_count AS source_rows,
  i.row_count AS interactive_rows,
  s.row_count - i.row_count AS row_difference,
  ROUND((i.row_count::FLOAT / s.row_count) * 100, 2) AS sync_percentage
FROM 
  (SELECT COUNT(*) AS row_count FROM source_table) s,
  (SELECT COUNT(*) AS row_count FROM interactive_table) i;
```

---

## Health Check Summary

```sql
-- Overall health check
SELECT 'Interactive Warehouses' AS category, COUNT(*) AS count
FROM INFORMATION_SCHEMA.WAREHOUSES
WHERE warehouse_name LIKE '%IWH%'

UNION ALL

SELECT 'Interactive Tables' AS category, COUNT(*) AS count
FROM INFORMATION_SCHEMA.TABLES
WHERE table_type = 'BASE TABLE'
  AND table_name LIKE '%INTERACTIVE%';
```

---

## Alerting Queries

### Suspended Warehouses (Business Hours)

```sql
SELECT 
  "name" AS warehouse_name,
  "state"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))  -- After SHOW WAREHOUSES
WHERE "state" = 'SUSPENDED'
  AND HOUR(CURRENT_TIME()) BETWEEN 8 AND 18;
```

### High Credit Usage Alert

```sql
SELECT 
  warehouse_name,
  DATE(start_time) AS date,
  SUM(credits_used) AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name LIKE '%IWH%'
  AND start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP())
GROUP BY warehouse_name, DATE(start_time)
HAVING total_credits > 10  -- Adjust threshold
ORDER BY total_credits DESC;
```

### Frequent Timeouts Alert

```sql
SELECT 
  warehouse_name,
  COUNT(*) AS timeout_count
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name LIKE '%IWH%'
  AND execution_status = 'FAILED'
  AND error_message LIKE '%timeout%'
  AND start_time >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP BY warehouse_name
HAVING timeout_count > 5;  -- Alert if >5 timeouts in hour
```
