# Trends Queries

Period comparison and cost trend analysis queries to understand how spending changes over time and investigate cost increases.

**Semantic keywords:** trends, week over week, month over month, comparison, change, increase, spike, WoW, MoM, period, cost increase, why costs increased, service comparison, historical

---

### Week-over-Week Credit Usage

**Triggered by:** "How did my Snowflake spend change compared to the previous week?", "week over week", "WoW comparison"

```sql
SELECT 'current_week' AS period, 
    ROUND(IFNULL(SUM(credits_used), 0), 2) AS credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
UNION ALL 
SELECT 'previous_week' AS period, 
    ROUND(IFNULL(SUM(credits_used), 0), 2) AS credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATEADD(DAY, -14, CURRENT_DATE()) 
    AND start_time < DATEADD(DAY, -7, CURRENT_DATE());
```

---

### Month-over-Month Credit Usage

**Triggered by:** "How did my Snowflake spend change compared to last month?", "month over month", "MoM comparison"

```sql
SELECT 'current_month' AS period, 
    ROUND(IFNULL(SUM(credits_used), 0), 2) AS credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATE_TRUNC('MONTH', CURRENT_DATE()) 
    AND start_time < DATE_TRUNC('MONTH', DATEADD(MONTH, 1, CURRENT_DATE())) 
UNION ALL 
SELECT 'previous_month' AS period, 
    ROUND(IFNULL(SUM(credits_used), 0), 2) AS credits_used 
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
WHERE start_time >= DATE_TRUNC('MONTH', DATEADD(MONTH, -1, CURRENT_DATE())) 
    AND start_time < DATE_TRUNC('MONTH', CURRENT_DATE());
```

---

### Why Has My Cost Increased? (Comprehensive)

**Triggered by:** "Why has my cost increased?", "What's causing my cost spike?", "Why is my bill higher?", "cost increase analysis"

```sql
WITH monthly_service_costs AS (
    SELECT DATE_TRUNC('month', start_time) AS cost_month, service_type, SUM(credits_used) AS total_credits 
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY 
    WHERE start_time >= DATE_TRUNC('month', DATEADD('month', -2, CURRENT_DATE())) 
    GROUP BY DATE_TRUNC('month', start_time), service_type
), 
service_comparison AS (
    SELECT service_type, 
        SUM(CASE WHEN cost_month = DATE_TRUNC('month', CURRENT_DATE()) THEN total_credits ELSE 0 END) AS current_month_credits, 
        SUM(CASE WHEN cost_month = DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE())) THEN total_credits ELSE 0 END) AS previous_month_credits 
    FROM monthly_service_costs 
    GROUP BY service_type
), 
service_increases AS (
    SELECT service_type, current_month_credits, previous_month_credits, 
        current_month_credits - previous_month_credits AS credit_increase, 
        CASE WHEN previous_month_credits > 0 
            THEN ROUND(((current_month_credits - previous_month_credits) / previous_month_credits) * 100, 2) 
            ELSE NULL END AS percentage_increase 
    FROM service_comparison 
    WHERE current_month_credits > previous_month_credits
)
SELECT * FROM service_increases ORDER BY credit_increase DESC;
```

---

### Service Type Comparison - Last 14 Days vs Prior 14 Days

**Triggered by:** "Service costs change", "which services increased?", "14 day comparison"

```sql
WITH recent AS (
    SELECT service_type, SUM(credits_used) AS credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
    WHERE start_time >= DATEADD(day, -14, CURRENT_DATE())
    GROUP BY service_type
),
prior AS (
    SELECT service_type, SUM(credits_used) AS credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
    WHERE start_time >= DATEADD(day, -28, CURRENT_DATE())
        AND start_time < DATEADD(day, -14, CURRENT_DATE())
    GROUP BY service_type
)
SELECT
    COALESCE(r.service_type, p.service_type) AS service_type,
    ROUND(COALESCE(p.credits, 0), 2) AS prior_14_days,
    ROUND(COALESCE(r.credits, 0), 2) AS recent_14_days,
    ROUND(COALESCE(r.credits, 0) - COALESCE(p.credits, 0), 2) AS change,
    ROUND(((COALESCE(r.credits, 0) - COALESCE(p.credits, 0)) / NULLIF(p.credits, 0)) * 100, 1) AS pct_change
FROM recent r
FULL OUTER JOIN prior p ON r.service_type = p.service_type
ORDER BY ABS(COALESCE(r.credits, 0) - COALESCE(p.credits, 0)) DESC;
```
