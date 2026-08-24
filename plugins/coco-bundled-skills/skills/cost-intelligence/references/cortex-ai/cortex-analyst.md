# Cortex Analyst Cost Queries

Queries for analyzing credit and request cost for Cortex Analyst.

**Semantic keywords:** Cortex Analyst, analyst credits, semantic layer costs, NL to SQL, natural language query costs, analyst cost

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_ANALYST_USAGE_HISTORY`

> **Note:** This view does not expose model-level or token-level breakdowns. Credits are aggregated per user per hour.

---

### Cortex Analyst Total Cost Summary

**Triggered by:** "What's my total Cortex Analyst cost?", "summarize Cortex Analyst spend", "how much did Cortex Analyst cost this period?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    ROUND(SUM(CREDITS), 4) AS total_credits,
    SUM(REQUEST_COUNT) AS total_requests,
    COUNT(DISTINCT USERNAME) AS active_users
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_ANALYST_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>';
```

---

### Cortex Analyst Cost per User

**Triggered by:** "How many Cortex Analyst credits did each user consume?", "analyst credits by user", "which users used Cortex Analyst the most?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    USERNAME,
    ROUND(SUM(CREDITS), 4) AS total_credits,
    SUM(REQUEST_COUNT) AS request_count,
    ROUND(SUM(CREDITS) / NULLIF(SUM(REQUEST_COUNT), 0), 6) AS avg_credits_per_request
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_ANALYST_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY USERNAME
ORDER BY total_credits DESC;
```

---

### Cortex Analyst Daily Cost Trend (with Week-over-Week Change)

**Triggered by:** "Show me the daily trend of Cortex Analyst cost", "analyst cost over time", "how has analyst spend trended?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
WITH daily AS (
    SELECT
        DATE_TRUNC('DAY', START_TIME) AS usage_date,
        ROUND(SUM(CREDITS), 4) AS daily_credits,
        SUM(REQUEST_COUNT) AS daily_requests,
        COUNT(DISTINCT USERNAME) AS active_users
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_ANALYST_USAGE_HISTORY
    WHERE START_TIME >= DATEADD('day', -7, '<START_TIME>')
      AND START_TIME < '<END_TIME>'
    GROUP BY usage_date
),
with_prev AS (
    SELECT
        usage_date,
        daily_credits,
        daily_requests,
        active_users,
        LAG(daily_credits, 7) OVER (ORDER BY usage_date) AS prev_week_credits
    FROM daily
)
SELECT
    usage_date,
    daily_credits,
    daily_requests,
    active_users,
    CASE
        WHEN daily_credits >= prev_week_credits
            THEN '+' || ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
        ELSE ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
    END AS wow_change_pct
FROM with_prev
WHERE usage_date >= '<START_TIME>'
ORDER BY usage_date ASC;
```
