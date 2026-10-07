# Cortex Agents Cost Queries

Queries for analyzing credit and token cost for Cortex Agents interactions.

**Semantic keywords:** Cortex Agents, agent credits, agent costs, agent cost, cortex agent spend

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY`

> **Note:** This view does not include requests originating from Snowflake Intelligence. For SI cost, see `snowflake-intelligence.md`.

---

### Cortex Agent Total Cost Summary

**Triggered by:** "What's my total Cortex Agents cost?", "summarize Cortex Agent spend", "how much did Cortex Agents cost this period?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_NAME) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>';
```

---

### Cortex Agent Cost by User

**Triggered by:** "How many Cortex Agent credits did each user consume?", "agent cost by user", "which users used Cortex Agents the most?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    USER_NAME,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY USER_NAME
ORDER BY total_credits DESC;
```

---

### Cortex Agent Cost by Agent

**Triggered by:** "Which Cortex Agents are the most expensive?", "agent cost breakdown", "most expensive agents", "top agents by credit spend"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    AGENT_DATABASE_NAME,
    AGENT_SCHEMA_NAME,
    AGENT_NAME,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_NAME) AS unique_users,
    COUNT(DISTINCT COALESCE(PARENT_REQUEST_ID, REQUEST_ID)) AS conversation_count
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY AGENT_DATABASE_NAME, AGENT_SCHEMA_NAME, AGENT_NAME
ORDER BY total_credits DESC;
```

---

### Cortex Agent Daily Cost Trend (with Week-over-Week Change)

**Triggered by:** "Show me the daily trend of Cortex Agent cost", "agent cost over time", "how has Cortex Agent spend trended?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
WITH daily AS (
    SELECT
        DATE(START_TIME) AS usage_date,
        ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS daily_credits,
        SUM(TOKENS) AS daily_tokens,
        COUNT(DISTINCT REQUEST_ID) AS daily_requests
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
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

### Cortex Agent Cost by Model and Service Type

**Triggered by:** "Which models did Cortex Agents use the most?", "agent model cost breakdown", "credits by model for Cortex Agents", "What tools are my Cortex Agents calling?", "agent service type breakdown", "how much of agent cost is from Cortex Analyst vs the agent itself?", "Which models drove the most cortex agent credits and how much came from downstream services?", "show model and service-type breakdown together", "call out unknown models"

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
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY h,
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

### Cortex Agent Cost by Interaction Interface

**Triggered by:** "Where is Cortex Agent usage coming from?", "break down agent spend by interface", "how much cost came from sql_function vs agent_admin_ui vs external?"

> **Note:** Keep the time window to at most one month to avoid query timeouts. `METADATA:interaction_interface` can be NULL for older rows or unknown interfaces, so use `COALESCE(METADATA:interaction_interface::STRING, 'unknown')` exactly rather than returning the raw metadata field.

```sql
SELECT
    COALESCE(METADATA:interaction_interface::STRING, 'unknown') AS interaction_interface,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count,
    COUNT(DISTINCT USER_NAME) AS unique_users
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY interaction_interface
ORDER BY total_credits DESC;
```

---

### Most Expensive Cortex Agent Requests or Conversations

**Triggered by:** "Which Cortex Agent requests cost the most?", "show me the priciest conversations", "request drill-down for Cortex Agents"

> **Note:** Keep the time window to at most one month to avoid query timeouts. Use `COALESCE(PARENT_REQUEST_ID, REQUEST_ID) AS conversation_id` and `COALESCE(METADATA:interaction_interface::STRING, 'unknown') AS interaction_interface` exactly so null parent requests and null interfaces are handled consistently.

```sql
SELECT
    COALESCE(PARENT_REQUEST_ID, REQUEST_ID) AS conversation_id,
    PARENT_REQUEST_ID,
    REQUEST_ID,
    USER_NAME,
    AGENT_DATABASE_NAME,
    AGENT_SCHEMA_NAME,
    AGENT_NAME,
    COALESCE(METADATA:interaction_interface::STRING, 'unknown') AS interaction_interface,
    ROUND(COALESCE(METADATA:ai_functions_credits::FLOAT, 0), 4) AS ai_functions_credits,
    ROUND(COALESCE(TOKEN_CREDITS, 0), 4) AS total_credits,
    TOKENS AS total_tokens,
    START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
ORDER BY total_credits DESC
LIMIT 25;
```

---

### Cortex Agent Cost by User Tag or Agent Tag

**Triggered by:** "Attribute agent spend by cost center tag", "show Cortex Agent cost by user tags", "compare user-tag spend with agent-tag spend"

> **Note:** Keep the time window to at most one month to avoid query timeouts. Use `outer => TRUE` so untagged rows can still be represented as `untagged`.

```sql
WITH tag_attribution AS (
    SELECT
        'user_tag' AS tag_scope,
        COALESCE(ut.value:tag_name::STRING, 'untagged') AS tag_name,
        COALESCE(ut.value:tag_value::STRING, 'untagged') AS tag_value,
        TOKEN_CREDITS,
        TOKENS,
        REQUEST_ID
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY h,
         LATERAL FLATTEN(input => h.USER_TAGS, outer => TRUE) ut
    WHERE START_TIME >= '<START_TIME>'
      AND START_TIME < '<END_TIME>'

    UNION ALL

    SELECT
        'agent_tag' AS tag_scope,
        COALESCE(at.value:tag_name::STRING, 'untagged') AS tag_name,
        COALESCE(at.value:tag_value::STRING, 'untagged') AS tag_value,
        TOKEN_CREDITS,
        TOKENS,
        REQUEST_ID
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY h,
         LATERAL FLATTEN(input => h.AGENT_TAGS, outer => TRUE) at
    WHERE START_TIME >= '<START_TIME>'
      AND START_TIME < '<END_TIME>'
)
SELECT
    tag_scope,
    tag_name,
    tag_value,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT REQUEST_ID) AS request_count
FROM tag_attribution
GROUP BY tag_scope, tag_name, tag_value
ORDER BY total_credits DESC, tag_scope, tag_name, tag_value;
```

---

### Cortex Agent Requests With Related AI Function Credits

**Triggered by:** "Did any Cortex Agent requests include extra AI function spend?", "show ai function credits inside agent usage", "which agent requests had ai function credits?"

> **Note:** Keep the time window to at most one month to avoid query timeouts. `METADATA:ai_functions_credits` is NULL when no AI functions were used. Keep the aliases `AI_FUNCTIONS_CREDITS`, `AGENT_TOTAL_CREDITS`, and `COMBINED_TOTAL_CREDITS` exactly.

```sql
SELECT
    AGENT_DATABASE_NAME,
    AGENT_SCHEMA_NAME,
    AGENT_NAME,
    REQUEST_ID,
    PARENT_REQUEST_ID,
    COALESCE(PARENT_REQUEST_ID, REQUEST_ID) AS conversation_id,
    COALESCE(METADATA:interaction_interface::STRING, 'unknown') AS interaction_interface,
    ROUND(COALESCE(METADATA:ai_functions_credits::FLOAT, 0), 4) AS ai_functions_credits,
    ROUND(COALESCE(TOKEN_CREDITS, 0), 4) AS agent_total_credits,
    ROUND(
        COALESCE(TOKEN_CREDITS, 0) + COALESCE(METADATA:ai_functions_credits::FLOAT, 0),
        4
    ) AS combined_total_credits,
    START_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AGENT_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
ORDER BY ai_functions_credits DESC, agent_total_credits DESC
LIMIT 25;
```
