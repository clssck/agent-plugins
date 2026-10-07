# Cortex Code / CoCo Cost Queries

Queries for analyzing credit and token cost for Cortex Code (also known as CoCo) using a single reference file for:

- **CLI only**
- **Desktop only**
- **Snowsight only**
- **any combination of surfaces together**

**Semantic keywords:** CoCo, Cortex Code, code assistant cost, coding assistant spend, code generation cost, Cortex Code CLI, Cortex Code Desktop, Cortex Code Snowsight, CoCo Desktop, Desktop app, CLI vs Desktop vs Snowsight, request drill-down, conversation cost, chargeback, tags

**Base Views:**
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY`

> Do not use `METERING_HISTORY`, `METERING_DAILY_HISTORY`, or `SERVICE_TYPE` for Cortex Code analysis. These usage views already provide the product-specific data, including model-level granular credits.

## Start Here: Pick The Surface

Before writing SQL, determine which Cortex Code surface the user wants:

- **CLI only** -> use `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY`
- **Desktop only** -> use `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY`
- **Snowsight only** -> use `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY`
- **two or all summed up together** -> use the `all_cortex_code_usage` `UNION ALL` CTE below
- **two or all reported separately** -> use respective views in seperate queries.

If the user says only **Cortex Code** and does not specify the surface, ask:

```text
Do you want Cortex Code / CoCo usage from the CLI, the Desktop app, or Snowsight? If you want more than one surface, do you want them summed up together or reported separately?
```

Stop immediately after asking. Do not run SQL until the user answers.

## Reusable Sources

After the user answers, set `CORTEX_CODE_SOURCE` to exactly one of the following:

### CLI only/separately

```sql
SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY
```

### Desktop only/separately

```sql
SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY
```

### Snowsight only/separately

```sql
SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY
```

### all together 

```sql
WITH all_cortex_code_usage AS (
    SELECT
        'CLI' AS surface,
        USER_ID,
        USER_TAGS,
        REQUEST_ID,
        PARENT_REQUEST_ID,
        USAGE_TIME,
        TOKEN_CREDITS,
        TOKENS,
        TOKENS_GRANULAR,
        CREDITS_GRANULAR
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY

    UNION ALL

    SELECT
        'DESKTOP' AS surface,
        USER_ID,
        USER_TAGS,
        REQUEST_ID,
        PARENT_REQUEST_ID,
        USAGE_TIME,
        TOKEN_CREDITS,
        TOKENS,
        TOKENS_GRANULAR,
        CREDITS_GRANULAR
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY

    UNION ALL

    SELECT
        'SNOWSIGHT' AS surface,
        USER_ID,
        USER_TAGS,
        REQUEST_ID,
        PARENT_REQUEST_ID,
        USAGE_TIME,
        TOKEN_CREDITS,
        TOKENS,
        TOKENS_GRANULAR,
        CREDITS_GRANULAR
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY
)
```

Then use:

```sql
FROM all_cortex_code_usage h
```

> When `CORTEX_CODE_SOURCE = all_cortex_code_usage`, use `surface || ':' || request_id` for distinct request or conversation counts so request IDs from different surfaces cannot collide.

---

### Cortex Code / CoCo Total Cost Summary

**Triggered by:** "What's my total Cortex Code cost?", "summarize CoCo spend", "how much did Cortex Code cost this period?"

> Replace `<CORTEX_CODE_SOURCE>` with:
> - `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY`
> - `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY`
> - `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY`
> - or `all_cortex_code_usage`

```sql
SELECT
    ROUND(SUM(COALESCE(h.TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(h.TOKENS) AS total_tokens,
    COUNT(DISTINCT h.REQUEST_ID) AS request_count
FROM <CORTEX_CODE_SOURCE> h
WHERE h.USAGE_TIME >= '<START_TIME>'
  AND h.USAGE_TIME < '<END_TIME>';
```

> If `<CORTEX_CODE_SOURCE> = all_cortex_code_usage`, change the request count expression to:
>
> ```sql
> COUNT(DISTINCT h.surface || ':' || h.REQUEST_ID) AS request_count
> ```

---

### Cortex Code / CoCo Cost by Surface

**Triggered by:** "How much of my Cortex Code spend is CLI vs Desktop vs Snowsight?", "which Cortex Code surface costs more?", "split Cortex Code cost by surface"

> Only use this query when the user explicitly wants **two or more surfaces together**. If the user only cares about a subset of surfaces, drop the `UNION ALL` branches for the surfaces they did not ask about.

```sql
WITH all_cortex_code_usage AS (
    SELECT
        'CLI' AS surface,
        USER_ID,
        USER_TAGS,
        REQUEST_ID,
        PARENT_REQUEST_ID,
        USAGE_TIME,
        TOKEN_CREDITS,
        TOKENS,
        TOKENS_GRANULAR,
        CREDITS_GRANULAR
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY

    UNION ALL

    SELECT
        'DESKTOP' AS surface,
        USER_ID,
        USER_TAGS,
        REQUEST_ID,
        PARENT_REQUEST_ID,
        USAGE_TIME,
        TOKEN_CREDITS,
        TOKENS,
        TOKENS_GRANULAR,
        CREDITS_GRANULAR
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY

    UNION ALL

    SELECT
        'SNOWSIGHT' AS surface,
        USER_ID,
        USER_TAGS,
        REQUEST_ID,
        PARENT_REQUEST_ID,
        USAGE_TIME,
        TOKEN_CREDITS,
        TOKENS,
        TOKENS_GRANULAR,
        CREDITS_GRANULAR
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY
)
SELECT
    surface,
    ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(DISTINCT surface || ':' || REQUEST_ID) AS request_count
FROM all_cortex_code_usage
WHERE USAGE_TIME >= '<START_TIME>'
  AND USAGE_TIME < '<END_TIME>'
GROUP BY surface
ORDER BY total_credits DESC;
```

---

### Cortex Code / CoCo Cost per User

**Triggered by:** "What's my Cortex Code spend looking like?", "which users are consuming the most Cortex Code credits?", "code assistant credits by user"

> Keep the time window to at most one month to avoid query timeouts. 
> Use `COALESCE(PARENT_REQUEST_ID, REQUEST_ID)` so null parent requests are handled consistently. 
> Replace `<CORTEX_CODE_SOURCE>` with the selected source.

```sql
SELECT
    u.NAME AS user_name,
    ROUND(SUM(COALESCE(h.TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(h.TOKENS) AS total_tokens,
    COUNT(DISTINCT h.REQUEST_ID) AS request_count
FROM <CORTEX_CODE_SOURCE> h
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u
    ON h.USER_ID = u.USER_ID
WHERE h.USAGE_TIME >= '<START_TIME>'
  AND h.USAGE_TIME < '<END_TIME>'
GROUP BY u.NAME
ORDER BY total_credits DESC;
```

> If `<CORTEX_CODE_SOURCE> = all_cortex_code_usage`, change the request count expression to:
>
> ```sql
> COUNT(DISTINCT h.surface || ':' || h.REQUEST_ID) AS request_count
> ```

---

### Cortex Code / CoCo Cost per Model

**Triggered by:** "Which models did Cortex Code use the most?", "code assistant model cost breakdown", "credits by model for Cortex Code"

> `CREDITS_GRANULAR` is keyed by model name for CLI, Desktop, and Snowsight. Replace `<CORTEX_CODE_SOURCE>` with the selected source.

```sql
SELECT
    f.key AS model_name,
    ROUND(SUM(COALESCE(f.value:input::FLOAT, 0)), 4) AS input_credits,
    ROUND(SUM(COALESCE(f.value:output::FLOAT, 0)), 4) AS output_credits,
    ROUND(SUM(COALESCE(f.value:cache_read_input::FLOAT, 0)), 4) AS cache_read_credits,
    ROUND(SUM(COALESCE(f.value:cache_write_input::FLOAT, 0)), 4) AS cache_write_credits,
    ROUND(SUM(
        COALESCE(f.value:input::FLOAT, 0) +
        COALESCE(f.value:output::FLOAT, 0) +
        COALESCE(f.value:cache_read_input::FLOAT, 0) +
        COALESCE(f.value:cache_write_input::FLOAT, 0)
    ), 4) AS total_credits
FROM <CORTEX_CODE_SOURCE> h,
     LATERAL FLATTEN(input => h.CREDITS_GRANULAR) f
WHERE h.USAGE_TIME >= '<START_TIME>'
  AND h.USAGE_TIME < '<END_TIME>'
GROUP BY f.key
ORDER BY total_credits DESC;
```

---

### Cortex Code / CoCo Daily Cost Trend (with Week-over-Week Change)

**Triggered by:** "Show me the daily trend of Cortex Code cost", "code assistant cost over time", "how has Cortex Code spend trended?"

> Keep the time window to at most one month to avoid query timeouts. Replace `<CORTEX_CODE_SOURCE>` with the selected source.

```sql
WITH daily AS (
    SELECT
        DATE(USAGE_TIME) AS usage_date,
        ROUND(SUM(COALESCE(TOKEN_CREDITS, 0)), 4) AS daily_credits,
        SUM(TOKENS) AS daily_tokens,
        COUNT(DISTINCT REQUEST_ID) AS daily_requests
    FROM <CORTEX_CODE_SOURCE>
    WHERE USAGE_TIME >= DATEADD('day', -7, '<START_TIME>')
      AND USAGE_TIME < '<END_TIME>'
    GROUP BY DATE(USAGE_TIME)
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

> If `<CORTEX_CODE_SOURCE> = all_cortex_code_usage`, change the daily request expression inside `daily` to:
>
> ```sql
> COUNT(DISTINCT surface || ':' || REQUEST_ID) AS daily_requests
> ```

---

### Most Expensive Cortex Code / CoCo Requests or Conversations

**Triggered by:** "Which Cortex Code requests cost the most?", "show me the priciest Cortex Code conversations", "request drill-down for Cortex Code"

> Keep the time window to at most one month to avoid query timeouts. 
> Use `COALESCE(PARENT_REQUEST_ID, REQUEST_ID)` so null parent requests are handled consistently. 
> Replace `<CORTEX_CODE_SOURCE>` with the selected source.

```sql
SELECT
    COALESCE(h.PARENT_REQUEST_ID, h.REQUEST_ID) AS conversation_id,
    h.PARENT_REQUEST_ID,
    h.REQUEST_ID,
    u.NAME AS user_name,
    ROUND(COALESCE(h.TOKEN_CREDITS, 0), 4) AS total_credits,
    h.TOKENS AS total_tokens,
    h.USAGE_TIME
FROM <CORTEX_CODE_SOURCE> h
LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u
    ON h.USER_ID = u.USER_ID
WHERE h.USAGE_TIME >= '<START_TIME>'
  AND h.USAGE_TIME < '<END_TIME>'
ORDER BY total_credits DESC
LIMIT 25;
```

> If `<CORTEX_CODE_SOURCE> = all_cortex_code_usage` and the user asked for a per-surface comparison in the drill-down, add `h.surface` to the `SELECT`.

---

### Cortex Code / CoCo Cost by User Tag

**Triggered by:** "Attribute Cortex Code spend by cost center tag", "team chargeback for Cortex Code", "which user tags are driving Cortex Code cost?"

> Use `outer => TRUE` so untagged rows can still be represented as `untagged`. Replace `<CORTEX_CODE_SOURCE>` with the selected source.

```sql
SELECT
    COALESCE(ut.value:tag_name::STRING, 'untagged') AS tag_name,
    COALESCE(ut.value:tag_value::STRING, 'untagged') AS tag_value,
    ROUND(SUM(COALESCE(h.TOKEN_CREDITS, 0)), 4) AS total_credits,
    SUM(h.TOKENS) AS total_tokens,
    COUNT(DISTINCT h.REQUEST_ID) AS request_count,
    COUNT(DISTINCT h.USER_ID) AS unique_users
FROM <CORTEX_CODE_SOURCE> h,
     LATERAL FLATTEN(input => h.USER_TAGS, outer => TRUE) ut
WHERE h.USAGE_TIME >= '<START_TIME>'
  AND h.USAGE_TIME < '<END_TIME>'
GROUP BY tag_name, tag_value
ORDER BY total_credits DESC, tag_name, tag_value;
```

> If `<CORTEX_CODE_SOURCE> = all_cortex_code_usage` and the user wants the tag breakdown split by surface, add `h.surface` to the `SELECT` and `GROUP BY`, and use:
>
> ```sql
> COUNT(DISTINCT h.surface || ':' || h.REQUEST_ID) AS request_count
> ```
