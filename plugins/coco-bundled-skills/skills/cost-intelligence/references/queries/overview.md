# Overview Queries

Overall spending and cost breakdown queries to understand where money is being spent across Snowflake services and accounts.

**Semantic keywords:** spending, costs, money, breakdown, total, credits, billing, service type, consumption, overall, summary, expensive, top resources, team attribution

---

### Where is my money going - Service Breakdown

**Triggered by:** "Where is my money going?", "What am I spending on?", "Show me my costs", "cost breakdown", "spending breakdown", "complete breakdown of spending"

```sql
SELECT 
    service_type, 
    ROUND(SUM(credits_used), 2) AS total_credits, 
    ROUND(SUM(credits_used) / SUM(SUM(credits_used)) OVER () * 100, 1) AS percentage_of_total 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
GROUP BY service_type 
ORDER BY total_credits DESC;
```

---

### Total Credits Used - Last Week

**Triggered by:** "How many credits were used last week?", "total credits", "weekly usage"

```sql
SELECT 
    'current_period' AS time, 
    ROUND(IFNULL(SUM(credits_used), 0), 2) AS credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE();
```

---

### Credits by Service Type - Last Week

**Triggered by:** "How much did I spend by service type last week?", "service type costs", "breakdown by service"

```sql
SELECT 
    service_type, 
    ROUND(SUM(credits_used), 2) AS credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
GROUP BY service_type 
ORDER BY credits_used DESC;
```

---

### Which Service is Consuming the Most?

**Triggered by:** "Which service is consuming the most money?", "top service by cost", "most expensive service"

```sql
SELECT 
    service_type, 
    ROUND(SUM(credits_used), 2) AS total_credits, 
    COUNT(*) AS usage_records, 
    ROUND(AVG(credits_used), 4) AS avg_credits_per_hour, 
    MIN(start_time) AS first_usage, 
    MAX(start_time) AS last_usage 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATEADD('month', -1, CURRENT_DATE()) 
GROUP BY service_type 
ORDER BY total_credits DESC 
LIMIT 10;
```

---

### Top 5 Most Expensive Resources Across All Categories

**Triggered by:** "Which are the 5 most expensive warehouses, compute pools, databases?", "top resources overall"

```sql
WITH warehouse_costs AS (
    SELECT 'WAREHOUSE' AS resource_type, warehouse_name AS resource_name, ROUND(SUM(credits_used), 2) AS total_credits 
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY 
    WHERE start_time >= DATEADD('month', -1, CURRENT_DATE()) 
    GROUP BY warehouse_name
), 
compute_pool_costs AS (
    SELECT 'COMPUTE_POOL' AS resource_type, compute_pool_name AS resource_name, ROUND(SUM(credits_used), 2) AS total_credits 
    FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPARK_CONTAINER_SERVICES_HISTORY 
    WHERE start_time >= DATEADD('month', -1, CURRENT_DATE()) 
    GROUP BY compute_pool_name
), 
all_resources AS (
    SELECT * FROM warehouse_costs 
    UNION ALL SELECT * FROM compute_pool_costs
) 
SELECT resource_type, resource_name, total_credits 
FROM all_resources 
ORDER BY total_credits DESC 
LIMIT 5;
```

---

### Team Attribution Across Major Cost Categories

**Triggered by:** "Which teams consumed the most across warehouse, cortex, and storage costs?", "team attribution comprehensive"

```sql
WITH team_warehouse_costs AS (
    SELECT tr.tag_name AS tag_key, tr.tag_value AS team_name, ROUND(SUM(wm.credits_used), 2) AS warehouse_credits 
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY wm 
    JOIN SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr ON wm.warehouse_name = tr.object_name 
    WHERE tr.domain = 'WAREHOUSE' AND tr.tag_value IS NOT NULL AND tr.tag_value != '' 
        AND wm.start_time >= DATEADD('month', -1, CURRENT_DATE()) 
    GROUP BY tr.tag_name, tr.tag_value
), 
team_storage_costs AS (
    SELECT tr.tag_name AS tag_key, tr.tag_value AS team_name, 
        ROUND(SUM(ds.average_database_bytes + ds.average_failsafe_bytes + COALESCE(ds.average_hybrid_table_storage_bytes, 0)) / (1024 * 1024 * 1024 * 1024), 4) AS storage_tb 
    FROM SNOWFLAKE.ACCOUNT_USAGE.DATABASE_STORAGE_USAGE_HISTORY ds 
    JOIN SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr ON ds.database_name = tr.object_name 
    WHERE tr.domain = 'DATABASE' AND tr.tag_value IS NOT NULL AND tr.tag_value != '' 
        AND ds.usage_date >= DATEADD('month', -1, CURRENT_DATE()) 
    GROUP BY tr.tag_name, tr.tag_value
) 
SELECT COALESCE(twc.tag_key, tsc.tag_key) AS tag_key, 
    COALESCE(twc.team_name, tsc.team_name) AS team_name, 
    COALESCE(twc.warehouse_credits, 0) AS warehouse_credits, 
    COALESCE(tsc.storage_tb, 0) AS storage_tb 
FROM team_warehouse_costs twc 
FULL OUTER JOIN team_storage_costs tsc ON twc.tag_key = tsc.tag_key AND twc.team_name = tsc.team_name 
ORDER BY warehouse_credits DESC;
```
