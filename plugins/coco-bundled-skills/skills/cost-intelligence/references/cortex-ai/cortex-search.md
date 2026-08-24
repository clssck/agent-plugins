# Cortex Search Cost Queries

Queries for analyzing credit cost for Cortex Search services.

**Semantic keywords:** Cortex Search, search credits, vector search costs, search service cost, embedding costs, search serving

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_DAILY_USAGE_HISTORY`

> Daily credit breakdown by consumption type (`SERVING` or `EMBED_TEXT_TOKENS`). No user-level attribution — costs are tracked at the service level.

---

### Cortex Search Total Cost Summary

**Triggered by:** "What's my total Cortex Search cost?", "summarize Cortex Search spend", "how much did Cortex Search cost this period?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    ROUND(SUM(CREDITS), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT SERVICE_NAME) AS active_services
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_DAILY_USAGE_HISTORY
WHERE USAGE_DATE >= '<START_TIME>'
  AND USAGE_DATE < '<END_TIME>';
```

---

### Cortex Search Cost per Service

**Triggered by:** "How much did each Cortex Search service cost?", "search service credit breakdown", "which search services are the most expensive?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    DATABASE_NAME,
    SCHEMA_NAME,
    SERVICE_NAME,
    ROUND(SUM(CREDITS), 4) AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_DAILY_USAGE_HISTORY
WHERE USAGE_DATE >= '<START_TIME>'
  AND USAGE_DATE < '<END_TIME>'
GROUP BY DATABASE_NAME, SCHEMA_NAME, SERVICE_NAME
ORDER BY total_credits DESC;
```

---

### Cortex Search Cost by Consumption Type

**Triggered by:** "How much of my Cortex Search cost is from serving vs embedding?", "search serving vs embedding cost split", "search consumption type breakdown"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    SERVICE_NAME,
    CONSUMPTION_TYPE,
    ROUND(SUM(CREDITS), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_DAILY_USAGE_HISTORY
WHERE USAGE_DATE >= '<START_TIME>'
  AND USAGE_DATE < '<END_TIME>'
GROUP BY SERVICE_NAME, CONSUMPTION_TYPE
ORDER BY SERVICE_NAME, total_credits DESC;
```

---

### Cortex Search Cost by Embedding Model

**Triggered by:** "Which embedding model is driving the most search costs?", "search embedding model cost breakdown"

> `MODEL_NAME` is only populated for `EMBED_TEXT_TOKENS` rows, making this an easy way to understand embedding model cost per service.

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    SERVICE_NAME,
    MODEL_NAME,
    ROUND(SUM(CREDITS), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_DAILY_USAGE_HISTORY
WHERE USAGE_DATE >= '<START_TIME>'
  AND USAGE_DATE < '<END_TIME>'
  AND CONSUMPTION_TYPE = 'EMBED_TEXT_TOKENS'
  AND MODEL_NAME IS NOT NULL
GROUP BY SERVICE_NAME, MODEL_NAME
ORDER BY total_credits DESC;
```

---

### Cortex Search Daily Cost Trend (with Week-over-Week Change)

**Triggered by:** "How has Cortex Search cost trended over time?", "search daily trend", "daily cost trend", "week-over-week change", "is search getting more expensive?"

> Serving cost scales with indexed data size, not query volume — a spike often means a large re-index or a new service was added.

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
WITH daily AS (
    SELECT
        USAGE_DATE AS usage_date,
        ROUND(SUM(CREDITS), 4) AS daily_credits,
        SUM(TOKENS) AS daily_tokens
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_SEARCH_DAILY_USAGE_HISTORY
    WHERE USAGE_DATE >= DATEADD('day', -7, '<START_TIME>')
      AND USAGE_DATE < '<END_TIME>'
    GROUP BY USAGE_DATE
),
with_prev AS (
    SELECT
        usage_date,
        daily_credits,
        daily_tokens,
        LAG(daily_credits, 7) OVER (ORDER BY usage_date) AS prev_week_credits
    FROM daily
)
SELECT
    usage_date,
    daily_credits,
    daily_tokens,
    CASE
        WHEN daily_credits >= prev_week_credits
            THEN '+' || ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
        ELSE ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
    END AS wow_change_pct
FROM with_prev
WHERE usage_date >= '<START_TIME>'
ORDER BY usage_date ASC;
```
