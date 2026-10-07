# Warehouse Queries

Queries for analyzing virtual warehouse costs, usage patterns, and changes over time.

**Semantic keywords:** warehouse, compute, virtual warehouse, top warehouses, warehouse spending, warehouse change, MoM, resize, query acceleration, QAS, warehouse comparison, expensive warehouses

---

### Top Warehouses by Credit Usage - Last Week

**Triggered by:** "Which warehouses consumed the most credits last week?", "top warehouses", "warehouse spending", "most expensive warehouses"

```sql
SELECT 
    warehouse_name, 
    warehouse_id, 
    ROUND(SUM(credits_used), 2) AS credits 
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
GROUP BY warehouse_name, warehouse_id 
ORDER BY credits DESC 
LIMIT 100;
```

---

### Warehouse Comparison - Last 14 Days vs Prior 14 Days

**Triggered by:** "Which warehouses increased?", "warehouse change", "warehouse comparison"

```sql
WITH recent AS (
    SELECT warehouse_name, SUM(credits_used) AS credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE start_time >= DATEADD(day, -14, CURRENT_DATE())
    GROUP BY warehouse_name
),
prior AS (
    SELECT warehouse_name, SUM(credits_used) AS credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE start_time >= DATEADD(day, -28, CURRENT_DATE())
        AND start_time < DATEADD(day, -14, CURRENT_DATE())
    GROUP BY warehouse_name
)
SELECT
    COALESCE(r.warehouse_name, p.warehouse_name) AS warehouse_name,
    ROUND(COALESCE(p.credits, 0), 2) AS prior_14_days,
    ROUND(COALESCE(r.credits, 0), 2) AS recent_14_days,
    ROUND(COALESCE(r.credits, 0) - COALESCE(p.credits, 0), 2) AS change,
    ROUND(((COALESCE(r.credits, 0) - COALESCE(p.credits, 0)) / NULLIF(p.credits, 0)) * 100, 1) AS pct_change
FROM recent r
FULL OUTER JOIN prior p ON r.warehouse_name = p.warehouse_name
ORDER BY ABS(COALESCE(r.credits, 0) - COALESCE(p.credits, 0)) DESC
LIMIT 15;
```

---

### Which Warehouses Saw the Largest Month-over-Month Change?

**Triggered by:** "Which warehouses saw the largest change in month cost?", "warehouse MoM change", "warehouse cost trend"

```sql
WITH monthly_warehouse_spend AS (
    SELECT warehouse_name, warehouse_id, DATE_TRUNC('month', start_time) AS spend_month, SUM(credits_used) AS total_credits 
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY 
    WHERE start_time >= DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE())) 
        AND start_time < DATE_TRUNC('month', DATEADD('month', 1, CURRENT_DATE())) 
    GROUP BY warehouse_name, warehouse_id, DATE_TRUNC('month', start_time)
), 
warehouse_comparison AS (
    SELECT warehouse_name, warehouse_id, 
        SUM(CASE WHEN spend_month = DATE_TRUNC('month', CURRENT_DATE()) THEN total_credits ELSE 0 END) AS current_month_credits, 
        SUM(CASE WHEN spend_month = DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE())) THEN total_credits ELSE 0 END) AS previous_month_credits 
    FROM monthly_warehouse_spend 
    GROUP BY warehouse_name, warehouse_id
) 
SELECT warehouse_name, 
    ROUND(current_month_credits, 2) AS current_month_credits, 
    ROUND(previous_month_credits, 2) AS previous_month_credits, 
    ROUND(current_month_credits - previous_month_credits, 2) AS credit_difference, 
    CASE WHEN previous_month_credits > 0 
        THEN ROUND(((current_month_credits - previous_month_credits) / previous_month_credits) * 100, 2) 
        ELSE NULL END AS percentage_change, 
    CASE 
        WHEN current_month_credits > previous_month_credits THEN 'INCREASED' 
        WHEN current_month_credits < previous_month_credits THEN 'DECREASED' 
        WHEN current_month_credits = previous_month_credits THEN 'UNCHANGED' 
        ELSE 'NEW_WAREHOUSE' 
    END AS trend_direction 
FROM warehouse_comparison 
WHERE current_month_credits > 0 OR previous_month_credits > 0 
ORDER BY ABS(current_month_credits - previous_month_credits) DESC;
```

---

### Warehouse Resize Events

**Triggered by:** "Have any warehouses been resized recently?", "warehouse resize history", "size changes"

```sql
WITH warehouse_states AS (
    SELECT warehouse_name, timestamp, size, 
        LAG(size) OVER (PARTITION BY warehouse_name ORDER BY timestamp) as previous_size 
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_EVENTS_HISTORY 
    WHERE event_name = 'WAREHOUSE_CONSISTENT' 
        AND timestamp >= CURRENT_DATE - 7
) 
SELECT warehouse_name, timestamp, previous_size, size as new_size 
FROM warehouse_states 
WHERE previous_size IS NOT NULL AND previous_size != size 
ORDER BY timestamp DESC;
```

---

### Query Acceleration Credits by Warehouse - Month to Date

**Triggered by:** "Which warehouses used the most query acceleration service credits this month?", "QAS costs"

```sql
SELECT 
    warehouse_name, 
    ROUND(SUM(credits_used), 2) AS total_credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ACCELERATION_HISTORY 
WHERE start_time >= DATE_TRUNC('month', CURRENT_DATE) 
GROUP BY warehouse_name 
ORDER BY total_credits_used DESC;
```
