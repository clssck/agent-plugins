# Cortex REST API Usage Queries

Queries for analyzing token usage for Cortex REST API calls.

**Semantic keywords:** Cortex REST API, REST API usage, Cortex REST calls, Cortex REST tokens, REST inference, inference region

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY`

> **Note:** This view includes request metadata and token counts, but it does not expose a `TOKEN_CREDITS` column. Use these queries for usage analysis in tokens. If the user asks for credits or currency, explain that credit usage is based on tokens according to the Snowflake Service Consumption Table and avoid inventing a credit calculation unless the current pricing table is available and the user approves using it.

---

### Cortex REST API Total Usage Summary

**Triggered by:** "What's my total Cortex REST API usage?", "summarize Cortex REST API tokens", "how many REST API tokens did I use this period?"

> **Note:** Keep the time window to at most one month for interactive analysis. This view does not expose `TOKEN_CREDITS`, so this summary is in tokens, not credits.

```sql
SELECT
    COALESCE(SUM(TOKENS), 0) AS total_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:input::NUMBER, 0)) AS input_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:output::NUMBER, 0)) AS output_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_ID) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>';
```

---

### Cortex REST API Token Usage by User

**Triggered by:** "Which users are calling the Cortex REST API?", "REST API usage by user", "Cortex REST tokens by user"

> **Note:** Keep the time window to at most one month for interactive analysis. Join through `USERS` to display user names instead of numeric IDs.

```sql
SELECT
    COALESCE(u.NAME, h.USER_ID::VARCHAR) AS user_name,
    COALESCE(SUM(h.TOKENS), 0) AS total_tokens,
    SUM(COALESCE(h.TOKENS_GRANULAR:input::NUMBER, 0)) AS input_tokens,
    SUM(COALESCE(h.TOKENS_GRANULAR:cache_read_input::NUMBER, 0)) AS cache_read_input_tokens,
    SUM(COALESCE(h.TOKENS_GRANULAR:cache_write_input::NUMBER, 0)) AS cache_write_input_tokens,
    SUM(COALESCE(h.TOKENS_GRANULAR:output::NUMBER, 0)) AS output_tokens,
    COUNT(DISTINCT h.REQUEST_ID) AS request_count,
    MIN(h.START_TIME) AS first_request_time,
    MAX(h.END_TIME) AS last_request_time
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY h
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u
    ON h.USER_ID = u.USER_ID
WHERE h.START_TIME >= '<START_TIME>'
  AND h.START_TIME < '<END_TIME>'
GROUP BY COALESCE(u.NAME, h.USER_ID::VARCHAR)
ORDER BY total_tokens DESC;
```

---

### Cortex REST API Token Usage by Model

**Triggered by:** "Which models are used through the Cortex REST API?", "REST API tokens by model", "Cortex REST model usage"

> **Note:** Keep the time window to at most one month to avoid query timeouts. Preserve `MODEL_NAME` values as recorded by the view.

```sql
SELECT
    MODEL_NAME,
    COALESCE(SUM(TOKENS), 0) AS total_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:input::NUMBER, 0)) AS input_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:cache_read_input::NUMBER, 0)) AS cache_read_input_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:cache_write_input::NUMBER, 0)) AS cache_write_input_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:output::NUMBER, 0)) AS output_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_ID) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY MODEL_NAME
ORDER BY total_tokens DESC;
```

---

### Cortex REST API Token Usage by Inference Region

**Triggered by:** "Which inference regions are handling Cortex REST API calls?", "REST API usage by region", "tokens by inference region"

> **Note:** Keep the time window to at most one month to avoid query timeouts. Use `COALESCE` so records with missing region metadata remain visible.

```sql
SELECT
    COALESCE(INFERENCE_REGION, 'unknown') AS inference_region,
    COALESCE(SUM(TOKENS), 0) AS total_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:input::NUMBER, 0)) AS input_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:cache_read_input::NUMBER, 0)) AS cache_read_input_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:cache_write_input::NUMBER, 0)) AS cache_write_input_tokens,
    SUM(COALESCE(TOKENS_GRANULAR:output::NUMBER, 0)) AS output_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_ID) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY COALESCE(INFERENCE_REGION, 'unknown')
ORDER BY total_tokens DESC;
```

---

### Cortex REST API Daily Token Trend

**Triggered by:** "Show Cortex REST API usage over time", "REST API daily tokens", "trend Cortex REST calls"

> **Note:** Keep the time window to at most one month to avoid query timeouts. This query reads seven extra days to compute week-over-week token change.

```sql
WITH daily AS (
    SELECT
        DATE(START_TIME) AS usage_date,
        COALESCE(SUM(TOKENS), 0) AS daily_tokens,
        SUM(COALESCE(TOKENS_GRANULAR:input::NUMBER, 0)) AS daily_input_tokens,
        SUM(COALESCE(TOKENS_GRANULAR:cache_read_input::NUMBER, 0)) AS daily_cache_read_input_tokens,
        SUM(COALESCE(TOKENS_GRANULAR:cache_write_input::NUMBER, 0)) AS daily_cache_write_input_tokens,
        SUM(COALESCE(TOKENS_GRANULAR:output::NUMBER, 0)) AS daily_output_tokens,
        COUNT(DISTINCT REQUEST_ID) AS daily_requests
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY
    WHERE START_TIME >= DATEADD('day', -7, '<START_TIME>')
      AND START_TIME < '<END_TIME>'
    GROUP BY DATE(START_TIME)
),
with_prev AS (
    SELECT
        usage_date,
        daily_tokens,
        daily_input_tokens,
        daily_cache_read_input_tokens,
        daily_cache_write_input_tokens,
        daily_output_tokens,
        daily_requests,
        LAG(daily_tokens, 7) OVER (ORDER BY usage_date) AS prev_week_tokens
    FROM daily
)
SELECT
    usage_date,
    daily_tokens,
    daily_input_tokens,
    daily_cache_read_input_tokens,
    daily_cache_write_input_tokens,
    daily_output_tokens,
    daily_requests,
    CASE
        WHEN daily_tokens >= prev_week_tokens
            THEN '+' || ROUND((daily_tokens - prev_week_tokens) / NULLIF(prev_week_tokens, 0) * 100, 1)::VARCHAR || '%'
        ELSE ROUND((daily_tokens - prev_week_tokens) / NULLIF(prev_week_tokens, 0) * 100, 1)::VARCHAR || '%'
    END AS wow_change_pct
FROM with_prev
WHERE usage_date >= '<START_TIME>'
ORDER BY usage_date ASC;
```

---

### Most Active Cortex REST API Requests

**Triggered by:** "Which Cortex REST API requests used the most tokens?", "REST API request drill-down", "largest REST inference requests"

> **Note:** Keep the time window to at most one month to avoid query timeouts. This is a request-level token drill-down, not a credit drill-down.

```sql
SELECT
    h.REQUEST_ID,
    COALESCE(u.NAME, h.USER_ID::VARCHAR) AS user_name,
    h.MODEL_NAME,
    COALESCE(h.INFERENCE_REGION, 'unknown') AS inference_region,
    COALESCE(h.TOKENS, 0) AS total_tokens,
    COALESCE(h.TOKENS_GRANULAR:input::NUMBER, 0) AS input_tokens,
    COALESCE(h.TOKENS_GRANULAR:cache_read_input::NUMBER, 0) AS cache_read_input_tokens,
    COALESCE(h.TOKENS_GRANULAR:cache_write_input::NUMBER, 0) AS cache_write_input_tokens,
    COALESCE(h.TOKENS_GRANULAR:output::NUMBER, 0) AS output_tokens,
    h.START_TIME,
    h.END_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_USAGE_HISTORY h
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u
    ON h.USER_ID = u.USER_ID
WHERE h.START_TIME >= '<START_TIME>'
  AND h.START_TIME < '<END_TIME>'
ORDER BY total_tokens DESC
LIMIT 25;
```
