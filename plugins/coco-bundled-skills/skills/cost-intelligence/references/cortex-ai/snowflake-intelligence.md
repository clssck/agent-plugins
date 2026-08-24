# Snowflake Intelligence / CoWork Cost Queries

Queries for analyzing credit and token cost for Snowflake Intelligence (also known as Snowflake CoWork) interactions.

**Semantic keywords:** Snowflake CoWork, Snowflake Intelligence, SI, intelligence agent, SI credits, intelligence cost, intelligence costs, request drill-down, conversation cost, request_id, chargeback, tags, ai_functions_credits

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY`

> Use this view when the customer is asking about the Snowflake Intelligence experience itself, even if the request fans out into embedded agents, Analyst calls, or AI Functions underneath. Do not route those questions to the standalone product usage views unless the user explicitly asks for the standalone product.

---

### Snowflake Intelligence / CoWork Total Cost Summary

**Triggered by:** "What's my total Snowflake Intelligence cost?", "summarize SI spend", "how much did Snowflake Intelligence cost this period?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_NAME) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>';
```

---

### Snowflake Intelligence / CoWork Cost per User

**Triggered by:** "How many Snowflake Intelligence credits did each user consume?", "SI credits by user", "which users used the most Snowflake Intelligence?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    USER_NAME,
    SUM(COALESCE(TOKEN_CREDITS, 0)) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY USER_NAME
ORDER BY total_credits DESC;
```

---

### Snowflake Intelligence / CoWork Cost by Instance

**Triggered by:** "Which SI instance is consuming the most credits?", "credits by intelligence instance", "most expensive Snowflake Intelligence deployment"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    SNOWFLAKE_INTELLIGENCE_NAME,
    SUM(COALESCE(TOKEN_CREDITS, 0)) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_NAME) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY SNOWFLAKE_INTELLIGENCE_NAME
ORDER BY total_credits DESC;
```

---

### Snowflake Intelligence / CoWork Cost by Agent

**Triggered by:** "Which agents inside Snowflake Intelligence cost the most?", "SI agent cost breakdown", "most expensive agents"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    SNOWFLAKE_INTELLIGENCE_NAME,
    AGENT_NAME,
    SUM(COALESCE(TOKEN_CREDITS, 0)) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY SNOWFLAKE_INTELLIGENCE_NAME, AGENT_NAME
ORDER BY total_credits DESC;
```

---

### Snowflake Intelligence / CoWork Daily Cost Trend (with Week-over-Week Change)

**Triggered by:** "Show me the daily trend of Snowflake Intelligence cost", "SI cost over time", "how has SI spend trended?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
WITH daily AS (
    SELECT
        DATE(START_TIME) AS usage_date,
        ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS daily_credits,
        SUM(TOKENS) AS daily_tokens,
        COUNT(DISTINCT REQUEST_ID) AS daily_requests
    FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
    WHERE START_TIME >= DATEADD('day', -7, '<START_TIME>')
      AND START_TIME < '<END_TIME>'
    GROUP BY DATE(START_TIME)
),
with_prev AS (
    SELECT
        usage_date,
        daily_credits,
        daily_tokens,
        daily_requests,
        LAG(daily_credits, 7) OVER (ORDER BY usage_date) AS prev_week_credits
    FROM daily
)
SELECT
    usage_date,
    daily_credits,
    daily_tokens,
    daily_requests,
    CASE
        WHEN daily_credits >= prev_week_credits
            THEN '+' || ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
        ELSE ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
    END AS wow_change_pct
FROM with_prev
WHERE usage_date >= '<START_TIME>'
ORDER BY usage_date ASC;
```

---

### Snowflake Intelligence / CoWork Cost by Model and Underlying Service Type

**Triggered by:** "Which models consumed the most Snowflake Intelligence credits?", "SI model cost breakdown", "credits by model for Snowflake Intelligence", "How much of Snowflake Intelligence cost is from Cortex Analyst vs Cortex Agents?", "SI service type breakdown", "which tools are agents calling the most?", "Which models drove the most Snowflake Intelligence credits and how much came from each underlying service?", "show SI model and service-type breakdown together", "call out unknown models"

> **Note:** Keep the time window to at most one month to avoid query timeouts. Keep the exact aliases `MODEL_NAME`, `SERVICE_TYPE`, `TOTAL_CREDITS`, and `TOTAL_TOKENS`. Preserve `unknown` model rows rather than dropping them.

```sql
WITH flattened AS (
    SELECT
        COALESCE(NULLIF(cf4.key, ''), 'unknown') AS model_name,
        cf3.key AS service_type,
        COALESCE(cf4.value:input::FLOAT, 0) +
        COALESCE(cf4.value:output::FLOAT, 0) +
        COALESCE(cf4.value:cache_read_input::FLOAT, 0) +
        COALESCE(cf4.value:cache_write_input::FLOAT, 0) AS total_credits,
        COALESCE(tf4.value:input::FLOAT, 0) +
        COALESCE(tf4.value:output::FLOAT, 0) +
        COALESCE(tf4.value:cache_read_input::FLOAT, 0) +
        COALESCE(tf4.value:cache_write_input::FLOAT, 0) AS total_tokens,
        h.REQUEST_ID
    FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY h,
         LATERAL FLATTEN(input => h.CREDITS_GRANULAR) cf1,
         LATERAL FLATTEN(input => cf1.value) cf2,
         LATERAL FLATTEN(input => cf2.value) cf3,
         LATERAL FLATTEN(input => cf3.value) cf4,
         LATERAL FLATTEN(input => h.TOKENS_GRANULAR) tf1,
         LATERAL FLATTEN(input => tf1.value) tf2,
         LATERAL FLATTEN(input => tf2.value) tf3,
         LATERAL FLATTEN(input => tf3.value) tf4
    WHERE cf2.key != 'start_time'
      AND tf2.key != 'start_time'
      AND cf1.index = tf1.index
      AND cf2.key = tf2.key
      AND cf3.key = tf3.key
      AND cf4.key = tf4.key
      AND h.START_TIME >= '<START_TIME>'
      AND h.START_TIME < '<END_TIME>'
)
SELECT
    model_name,
    service_type,
    ROUND(SUM(total_credits), 4) AS total_credits,
    SUM(total_tokens) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count
FROM flattened
GROUP BY model_name, service_type
ORDER BY total_credits DESC, model_name, service_type;
```

---

### Snowflake Intelligence / CoWork Request Drill-Down

**Triggered by:** "Which Snowflake Intelligence requests were the most expensive?", "show me the request ids behind the spike", "drill into a specific Snowflake Intelligence conversation"

> Snowflake Intelligence usage is request-level in `ACCOUNT_USAGE`. If the customer says "conversation", start with the highest-cost requests for the user / instance / time window they care about, then narrow further by request id.

```sql
SELECT
    REQUEST_ID,
    START_TIME,
    USER_NAME,
    SNOWFLAKE_INTELLIGENCE_NAME,
    AGENT_NAME,
    ROUND(COALESCE(TOKEN_CREDITS, 0), 4) AS total_credits,
    TOKENS AS total_tokens,
    COALESCE(METADATA:ai_functions_credits::FLOAT, 0) AS ai_functions_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
ORDER BY total_credits DESC
LIMIT 25;
```

---

### Snowflake Intelligence / CoWork Cost by User Tag

**Triggered by:** "Attribute Snowflake Intelligence spend by cost center tag", "team chargeback for Snowflake Intelligence", "which user tags are driving SI cost?"

> `ACCOUNT_USAGE.TAG_REFERENCES` for user tags can lag by up to 2 hours. Use `TAG_NAME IN (...)` when the customer names specific tags like `COST_CENTER` or `TEAM`.

```sql
WITH user_tags AS (
    SELECT
        OBJECT_NAME AS user_name,
        TAG_NAME,
        TAG_VALUE
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
    WHERE DOMAIN = 'USER'
      AND TAG_NAME IN ('<TAG_NAME_1>', '<TAG_NAME_2>')
),
si_usage AS (
    SELECT
        USER_NAME,
        REQUEST_ID,
        TOKEN_CREDITS,
        TOKENS
    FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
    WHERE START_TIME >= '<START_TIME>'
      AND START_TIME < '<END_TIME>'
)
SELECT
    COALESCE(ut.TAG_NAME, 'UNTAGGED') AS tag_name,
    COALESCE(ut.TAG_VALUE, 'UNTAGGED') AS tag_value,
    ROUND(SUM(COALESCE(si.TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(si.TOKENS) AS total_tokens,
    COUNT(DISTINCT si.REQUEST_ID) AS request_count,
    COUNT(DISTINCT si.USER_NAME) AS unique_users
FROM si_usage si
LEFT JOIN user_tags ut
    ON si.USER_NAME = ut.user_name
GROUP BY tag_name, tag_value
ORDER BY total_credits DESC;
```

---

### Snowflake Intelligence / CoWork Related AI Functions Metadata Cost

**Triggered by:** "How much Snowflake Intelligence cost came from AI Functions?", "show me the ai_functions_credits metadata", "which SI agents are driving downstream AI Functions cost?"

```sql
SELECT
    SNOWFLAKE_INTELLIGENCE_NAME,
    AGENT_NAME,
    ROUND(SUM(COALESCE(METADATA:ai_functions_credits::FLOAT, 0)), 4) AS ai_functions_credits,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_si_credits,
    ROUND(
        SUM(COALESCE(METADATA:ai_functions_credits::FLOAT, 0))
        / NULLIF(SUM(COALESCE(TOKEN_CREDITS, 0)), 0) * 100,
        1
    ) AS ai_functions_credit_pct,
    COUNT(DISTINCT REQUEST_ID) AS request_count
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_INTELLIGENCE_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY SNOWFLAKE_INTELLIGENCE_NAME, AGENT_NAME
ORDER BY ai_functions_credits DESC;
```
