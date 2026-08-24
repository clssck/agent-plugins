# Storage Queries

Queries for analyzing storage costs, database sizes, growth trends, and clustering expenses.

**Semantic keywords:** storage, database size, storage costs, storage usage, growth trend, storage growth, failsafe, hybrid table, clustering, auto-clustering, team storage, YTD storage, top databases, storage TB

---

### Top Databases by Storage Usage

**Triggered by:** "Which databases used the most storage on average?", "database storage costs", "top databases by storage"

```sql
WITH daily AS (
    SELECT database_name, usage_date, 
        MAX(database_id) AS object_id, 
        MAX(average_database_bytes + average_failsafe_bytes + average_hybrid_table_storage_bytes) AS database_storage_bytes 
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY 
    WHERE usage_date >= DATEADD(DAY, -7, CURRENT_DATE()) 
        AND usage_date < CURRENT_DATE() 
    GROUP BY ALL
) 
SELECT database_name, AVG(database_storage_bytes) AS database_storage_bytes 
FROM daily 
GROUP BY database_name 
ORDER BY database_storage_bytes DESC 
LIMIT 100;
```

---

### Top 5 Most Expensive Databases by Storage

**Triggered by:** "Which 5 databases are contributing the most to storage costs?", "top 5 storage databases"

```sql
SELECT 
    database_name, 
    database_id, 
    COUNT(*) as days_tracked, 
    AVG((average_database_bytes + average_failsafe_bytes + COALESCE(average_hybrid_table_storage_bytes, 0))) / (1024*1024*1024) AS avg_total_storage_gb, 
    AVG(average_database_bytes) / (1024*1024*1024) AS avg_database_storage_gb, 
    AVG(average_failsafe_bytes) / (1024*1024*1024) AS avg_failsafe_storage_gb, 
    MIN(usage_date) as first_date, 
    MAX(usage_date) as last_date 
FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY 
WHERE usage_date >= DATEADD(days, -30, CURRENT_DATE()) 
GROUP BY database_name, database_id 
ORDER BY avg_total_storage_gb DESC 
LIMIT 5;
```

---

### Storage Growth Trend Analysis

**Triggered by:** "How is storage usage trending across databases over time?", "storage growth trend"

```sql
SELECT 
    database_name, 
    usage_date, 
    ROUND(average_database_bytes / POW(1024, 4), 3) AS database_tb, 
    ROUND(average_failsafe_bytes / POW(1024, 4), 3) AS failsafe_tb, 
    ROUND((average_database_bytes + average_failsafe_bytes + COALESCE(average_hybrid_table_storage_bytes, 0)) / POW(1024, 4), 3) AS total_tb, 
    LAG(ROUND((average_database_bytes + average_failsafe_bytes + COALESCE(average_hybrid_table_storage_bytes, 0)) / POW(1024, 4), 3)) 
        OVER (PARTITION BY database_name ORDER BY usage_date) AS prev_day_tb 
FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY 
WHERE usage_date >= CURRENT_DATE - 30 
    AND database_name IN (
        SELECT database_name 
        FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY 
        WHERE usage_date = CURRENT_DATE - 1 
        ORDER BY (average_database_bytes + average_failsafe_bytes + COALESCE(average_hybrid_table_storage_bytes, 0)) DESC 
        LIMIT 10
    ) 
ORDER BY database_name, usage_date DESC;
```

---

### Storage YTD Spend

**Triggered by:** "How much have I spent so far this calendar year on database storage?", "YTD storage cost"

```sql
SELECT 
    SUM(m.credits_used) AS total_storage_credits, 
    COUNT(*) AS total_records, 
    AVG(m.credits_used) AS avg_hourly_storage_credits, 
    MIN(m.start_time) AS first_date, 
    MAX(m.start_time) AS last_date 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY m 
WHERE m.service_type = 'STORAGE' 
    AND m.start_time >= DATE_TRUNC('YEAR', CURRENT_DATE()) 
    AND m.start_time <= CURRENT_DATE();
```

---

### Which Teams Have Most Storage?

**Triggered by:** "Which teams are taking up the most storage over the past month?", "team storage usage"

```sql
SELECT 
    tr.tag_value AS team_name, 
    tr.tag_name AS tag_key, 
    SUM(ds.average_database_bytes + ds.average_failsafe_bytes + COALESCE(ds.average_hybrid_table_storage_bytes, 0)) / (1024 * 1024 * 1024 * 1024) AS total_storage_tb, 
    COUNT(DISTINCT ds.database_name) AS databases_owned 
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr 
JOIN SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY ds ON tr.object_name = ds.database_name 
WHERE tr.domain = 'DATABASE' 
    AND tr.tag_value IS NOT NULL 
    AND ds.usage_date >= DATEADD(month, -1, CURRENT_DATE()) 
GROUP BY tr.tag_value, tr.tag_name 
ORDER BY total_storage_tb DESC 
LIMIT 10;
```

---

### Which Tables Are Driving Clustering Expenses?

**Triggered by:** "Which tables are driving up our clustering expenses?", "auto-clustering costs", "clustering spending"

```sql
SELECT 
    database_name, 
    schema_name, 
    table_name, 
    ROUND(SUM(credits_used), 2) AS total_clustering_credits, 
    COUNT(*) AS clustering_events, 
    ROUND(AVG(credits_used), 4) AS avg_credits_per_event, 
    MIN(start_time) AS first_clustering, 
    MAX(start_time) AS last_clustering 
FROM SNOWFLAKE.ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY 
WHERE start_time >= DATEADD('month', -1, CURRENT_DATE()) 
GROUP BY database_name, schema_name, table_name 
ORDER BY total_clustering_credits DESC 
LIMIT 20;
```
