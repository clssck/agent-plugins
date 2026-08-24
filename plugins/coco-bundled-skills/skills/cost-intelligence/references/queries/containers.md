# Containers Queries

Queries for analyzing Snowpark Container Services (SPCS) costs including compute pools and applications.

**Semantic keywords:** containers, SPCS, Snowpark Container Services, compute pools, container costs, applications, under-utilized, idle pools, container credits

---

### Top Compute Pools by Spend - Last Week

**Triggered by:** "Which compute pools used the most credits over the past week?", "SPCS costs", "container costs"

```sql
SELECT 
    compute_pool_name, 
    ROUND(SUM(credits_used), 2) AS total_credits 
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPARK_CONTAINER_SERVICES_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
GROUP BY compute_pool_name 
ORDER BY total_credits DESC 
LIMIT 10;
```

---

### Total Snowpark Container Services Credits - Last Week

**Triggered by:** "How many total credits were used by Snowpark container services last week?", "total SPCS credits"

```sql
SELECT 
    ROUND(SUM(credits_used), 2) AS total_credits 
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPARK_CONTAINER_SERVICES_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE();
```

---

### Top Applications by Snowpark Container Spend

**Triggered by:** "Which applications used the most Snowpark container credits last week?", "SPCS by application"

```sql
SELECT 
    application_name, 
    application_id, 
    ROUND(SUM(credits_used), 2) AS total_credits 
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPARK_CONTAINER_SERVICES_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
    AND application_id IS NOT NULL AND application_id <> '' 
GROUP BY application_name, application_id 
ORDER BY total_credits DESC 
LIMIT 10;
```

---

### Under-Utilized Compute Pools

**Triggered by:** "Which compute pools are consuming the least number of credits (under utilized)?", "idle compute pools"

```sql
SELECT 
    compute_pool_name, 
    ROUND(SUM(credits_used), 2) AS total_credits_used, 
    COUNT(*) AS usage_hours, 
    ROUND(AVG(credits_used), 4) AS avg_credits_per_hour, 
    DATEDIFF('day', MIN(start_time), MAX(start_time)) + 1 AS days_active, 
    MAX(application_name) AS associated_application 
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPARK_CONTAINER_SERVICES_HISTORY 
WHERE start_time >= DATEADD('month', -1, CURRENT_DATE()) 
GROUP BY compute_pool_name 
ORDER BY total_credits_used ASC 
LIMIT 5;
```
