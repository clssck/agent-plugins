# Serverless Queries

Queries for analyzing serverless task costs and activity.

**Semantic keywords:** serverless, tasks, serverless tasks, task credits, task costs, task activity, database tasks, scheduled tasks, task spending

---

### Serverless Task Credits - Last Week

**Triggered by:** "How many credits did serverless tasks consume last week?", "serverless task costs"

```sql
SELECT 
    task_name, 
    database_name, 
    schema_name, 
    ROUND(SUM(credits_used), 2) AS total_credits 
FROM SNOWFLAKE.ACCOUNT_USAGE.SERVERLESS_TASK_HISTORY 
WHERE start_time >= DATEADD('D', -7, CURRENT_DATE) 
    AND start_time < CURRENT_DATE 
GROUP BY task_name, database_name, schema_name 
ORDER BY total_credits DESC;
```

---

### Top Serverless Tasks by Database

**Triggered by:** "Which databases have the highest serverless task credit usage?", "task costs by database"

```sql
SELECT 
    database_name, 
    COUNT(DISTINCT task_name) AS task_count, 
    ROUND(SUM(credits_used), 2) AS total_credits 
FROM SNOWFLAKE.ACCOUNT_USAGE.SERVERLESS_TASK_HISTORY 
WHERE start_time >= DATEADD('D', -30, CURRENT_DATE) 
GROUP BY database_name 
ORDER BY total_credits DESC 
LIMIT 10;
```

---

### Serverless Task Activity - Last 12 Hours

**Triggered by:** "What serverless task activity happened in the last 12 hours?", "recent task activity"

```sql
SELECT 
    task_name, 
    database_name, 
    schema_name, 
    start_time, 
    end_time, 
    ROUND(credits_used, 2) AS credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.SERVERLESS_TASK_HISTORY 
WHERE start_time >= DATEADD('H', -12, CURRENT_TIMESTAMP) 
ORDER BY start_time DESC;
```
