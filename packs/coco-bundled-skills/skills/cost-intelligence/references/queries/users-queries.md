# Users & Queries

Queries for analyzing costs at the user and individual query level, including expensive queries and user spending patterns.

**Semantic keywords:** users, queries, expensive queries, costly queries, top users, user costs, who is spending, query cost, parameterized, query patterns, user increase, biggest bills, query attribution, parameterized hash, grouped by hash

---

### Most Expensive Individual Queries - Last Week

**Triggered by:** "Which individual queries consumed the most compute credits last week?", "most expensive queries", "top costly queries"

```sql
SELECT 
   qa.query_id, 
   qa.warehouse_name, 
   qa.user_name, 
   ROUND(qa.credits_attributed_compute, 2) AS credits_compute, 
   ROUND(qa.credits_used_query_acceleration, 2) AS credits_qas,
   qa.start_time
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY qa 
WHERE qa.start_time >= CURRENT_DATE - 7 
  AND qa.credits_attributed_compute > 0 
ORDER BY qa.credits_attributed_compute DESC 
LIMIT 15;
```

---

### Top 5 Queries Grouped by Parameterized Hash

**Triggered by:** "Show me my top queries grouped by parameterized hash?", "What are the top 5 queries grouped by parameterized hash?", "query patterns by cost", "top queries by hash", "parameterized query costs", "Which parameterized queries were the most expensive last week?", "expensive query patterns", "query families"

```sql
SELECT
    query_parameterized_hash,
    ROUND(SUM(credits_attributed_compute), 2) AS total_credits,
    COUNT(query_id) AS execution_count,
    ROUND(SUM(credits_attributed_compute) / NULLIF(COUNT(query_id), 0), 4) AS avg_credits_per_execution,
    ANY_VALUE(query_id) AS example_query_id
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE())
  AND start_time < CURRENT_DATE()
  AND query_parameterized_hash IS NOT NULL
GROUP BY query_parameterized_hash
ORDER BY total_credits DESC
LIMIT 5
```

---

### Top Users by Query Costs

**Triggered by:** "What users are spending the most?", "Which users are spending the most?", "Who is spending the most?", "user costs"

```sql
SELECT 
    user_name, 
    COUNT(DISTINCT query_id) AS query_count, 
    ROUND(SUM(credits_attributed_compute + COALESCE(credits_used_query_acceleration, 0)), 2) AS total_credits 
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY 
WHERE start_time >= DATEADD(DAY, -7, CURRENT_DATE()) 
    AND start_time < CURRENT_DATE() 
GROUP BY user_name 
ORDER BY total_credits DESC 
LIMIT 20;
```

---

### Top 5 Users with Greatest Increase in Query Cost

**Triggered by:** "Who are the top-5 users with the greatest increase in query cost?", "user cost increase", "who increased spending?"

```sql
WITH monthly_user_spend AS (
    SELECT user_name, DATE_TRUNC('month', start_time) AS spend_month, SUM(credits_attributed_compute) AS total_credits 
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY 
    WHERE start_time >= DATE_TRUNC('month', DATEADD('month', -2, CURRENT_DATE())) 
        AND start_time < DATE_TRUNC('month', DATEADD('month', 1, CURRENT_DATE())) 
    GROUP BY user_name, DATE_TRUNC('month', start_time)
), 
user_comparison AS (
    SELECT user_name, 
        SUM(CASE WHEN spend_month = DATE_TRUNC('month', CURRENT_DATE()) THEN total_credits ELSE 0 END) AS current_month_credits, 
        SUM(CASE WHEN spend_month = DATE_TRUNC('month', DATEADD('month', -1, CURRENT_DATE())) THEN total_credits ELSE 0 END) AS previous_month_credits 
    FROM monthly_user_spend 
    GROUP BY user_name
) 
SELECT user_name, 
    ROUND(current_month_credits, 2) AS current_month_credits, 
    ROUND(previous_month_credits, 2) AS previous_month_credits, 
    ROUND(current_month_credits - previous_month_credits, 2) AS credit_increase, 
    CASE WHEN previous_month_credits > 0 
        THEN ROUND(((current_month_credits - previous_month_credits) / previous_month_credits) * 100, 2) 
        ELSE NULL END AS percentage_increase 
FROM user_comparison 
WHERE current_month_credits > previous_month_credits 
ORDER BY (current_month_credits - previous_month_credits) DESC 
LIMIT 5;
```

---

### Top 5 Users with Biggest Bills (Comprehensive)

**Triggered by:** "Which are the top 5 individuals who ran up the biggest bills?", "Who are the biggest spenders?", "user costs efficiently"

```sql
WITH user_direct_costs AS (
    SELECT qa.user_name, 
        ROUND(SUM(qa.credits_attributed_compute), 4) AS query_compute_credits, 
        ROUND(SUM(COALESCE(qa.credits_used_query_acceleration, 0)), 4) AS query_acceleration_credits, 
        COUNT(DISTINCT qa.query_id) AS total_queries, 
        COUNT(DISTINCT qa.warehouse_id) AS warehouses_used 
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY qa 
    WHERE qa.start_time >= DATEADD('month', -1, CURRENT_DATE()) 
    GROUP BY qa.user_name
)
SELECT udc.user_name AS user_name, 
    ROUND(COALESCE(udc.query_compute_credits, 0) + COALESCE(udc.query_acceleration_credits, 0), 4) AS total_user_bill, 
    COALESCE(udc.query_compute_credits, 0) AS query_compute_credits, 
    COALESCE(udc.total_queries, 0) AS total_queries 
FROM user_direct_costs udc 
ORDER BY total_user_bill DESC 
LIMIT 5;
```
