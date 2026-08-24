# Cortex AI Functions Cost Queries

Queries for analyzing credit and token cost for Cortex AI Functions (COMPLETE, TRANSLATE, etc.).

**Semantic keywords:** Cortex AI functions, COMPLETE, TRANSLATE, LLM functions, AI function costs, token credits

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY`

---

### Cortex AI Function Total Cost Summary

**Triggered by:** "What's my total Cortex AI Functions cost?", "summarize AI SQL function spend", "how much did AI functions cost this period?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT QUERY_ID) AS total_queries
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY
WHERE USAGE_TIME >= '<START_TIME>'
  AND USAGE_TIME < '<END_TIME>';
```

---

### Cortex AI Function Cost per User

**Triggered by:** "Show me AI SQL function credits by user", "who used COMPLETE the most?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    u.NAME AS user_name,
    ROUND(SUM(COALESCE(h.TOKEN_CREDITS_GRANULAR:input::FLOAT, 0)), 4) AS input_credits,
    ROUND(SUM(COALESCE(h.TOKEN_CREDITS_GRANULAR:output::FLOAT, 0)), 4) AS output_credits,
    ROUND(SUM(COALESCE(h.TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(h.TOKENS_GRANULAR:input::FLOAT) AS input_tokens,
    SUM(h.TOKENS_GRANULAR:output::FLOAT) AS output_tokens,
    SUM(h.TOKENS) AS total_tokens,
    COUNT(DISTINCT h.QUERY_ID) AS total_queries
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY h
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u
    ON TRY_CAST(h.USER_ID AS NUMBER) = u.USER_ID
WHERE h.USAGE_TIME >= '<START_TIME>'
  AND h.USAGE_TIME < '<END_TIME>'
GROUP BY user_name
ORDER BY total_credits DESC;
```

---

### Cortex AI Function Cost per Function

**Triggered by:** "Which Cortex AI functions cost the most?", "COMPLETE vs TRANSLATE cost breakdown", "credits by function"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    FUNCTION_NAME,
    ROUND(SUM(COALESCE(TOKEN_CREDITS_GRANULAR:input::FLOAT, 0)), 4) AS input_credits,
    ROUND(SUM(COALESCE(TOKEN_CREDITS_GRANULAR:output::FLOAT, 0)), 4) AS output_credits,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS_GRANULAR:input::FLOAT) AS input_tokens,
    SUM(TOKENS_GRANULAR:output::FLOAT) AS output_tokens,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT QUERY_ID) AS total_queries
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY
WHERE USAGE_TIME >= '<START_TIME>'
  AND USAGE_TIME < '<END_TIME>'
GROUP BY FUNCTION_NAME
ORDER BY total_credits DESC;
```

---

### Cortex AI Function Cost per Model

**Triggered by:** "Which models are consuming the most AI function credits?", "credits by model for AI functions", "most expensive model"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    MODEL_NAME,
    ROUND(SUM(COALESCE(TOKEN_CREDITS_GRANULAR:input::FLOAT, 0)), 4) AS input_credits,
    ROUND(SUM(COALESCE(TOKEN_CREDITS_GRANULAR:output::FLOAT, 0)), 4) AS output_credits,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS_GRANULAR:input::FLOAT) AS input_tokens,
    SUM(TOKENS_GRANULAR:output::FLOAT) AS output_tokens,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT QUERY_ID) AS total_queries
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY
WHERE USAGE_TIME >= '<START_TIME>'
  AND USAGE_TIME < '<END_TIME>'
GROUP BY MODEL_NAME
ORDER BY total_credits DESC;
```

---

### Cortex AI Function Daily Cost Trend (with Week-over-Week Change)

**Triggered by:** "Show me the daily trend of Cortex function cost and costs", "Cortex daily trend", "AI function cost this week"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
WITH daily AS (
    SELECT
        DATE(usage_time) AS usage_date,
        SUM(tokens) AS total_tokens,
        ROUND(SUM(COALESCE(token_credits, 0)), 4) AS total_credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY
    WHERE usage_time >= DATEADD('day', -7, '<START_TIME>')
      AND usage_time < '<END_TIME>'
    GROUP BY DATE(usage_time)
),
with_prev AS (
    SELECT
        usage_date,
        total_tokens,
        total_credits,
        LAG(total_credits, 7) OVER (ORDER BY usage_date) AS prev_week_credits
    FROM daily
)
SELECT
    usage_date,
    total_tokens,
    total_credits,
    CASE
        WHEN total_credits >= prev_week_credits
            THEN '+' || ROUND((total_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
        ELSE ROUND((total_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
    END AS wow_change_pct
FROM with_prev
WHERE usage_date >= '<START_TIME>'
ORDER BY usage_date ASC;
```

---

### Cortex AI Function Cost per Team (via Warehouse Tags)

**Triggered by:** "Which team consumed the most Cortex AI functions?", "team Cortex cost", "AI function chargeback by team"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
WITH warehouse_tags AS (
    SELECT DISTINCT wm.warehouse_id, wm.warehouse_name, tr.tag_name, tr.tag_value
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY wm
    JOIN SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES tr ON wm.warehouse_name = tr.object_name
    WHERE tr.domain = 'WAREHOUSE' AND tr.tag_value IS NOT NULL
),
cortex_functions_by_team AS (
    SELECT wt.tag_name AS tag_key, wt.tag_value AS team_name,
        SUM(COALESCE(cf.token_credits, 0)) AS total_credits,
        COUNT(DISTINCT cf.function_name) AS unique_functions,
        COUNT(DISTINCT cf.model_name) AS unique_models
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AISQL_USAGE_HISTORY cf
    JOIN warehouse_tags wt ON cf.warehouse_id = wt.warehouse_id::VARCHAR
    WHERE cf.usage_time >= '<START_TIME>'
      AND cf.usage_time < '<END_TIME>'
    GROUP BY wt.tag_name, wt.tag_value
)
SELECT tag_key, team_name, ROUND(total_credits, 4) AS total_cortex_credits, unique_functions, unique_models
FROM cortex_functions_by_team
ORDER BY total_credits DESC
LIMIT 10;
```
