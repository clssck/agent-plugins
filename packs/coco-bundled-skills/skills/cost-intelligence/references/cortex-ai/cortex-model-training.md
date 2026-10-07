# Cortex Model Training Cost Queries

Queries for analyzing credit cost for Cortex Model Training jobs.

**Semantic keywords:** model training, model training credits, fine-tuning, custom model, fine-tuned model cost

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FINE_TUNING_USAGE_HISTORY`

> Training credits only. Inference costs for the trained model are tracked separately in `CORTEX_AISQL_USAGE_HISTORY`.

---

### Cortex Model Training Total Cost Summary

**Triggered by:** "What's my total model training cost?", "summarize fine-tuning spend", "how much did model training cost this period?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    ROUND(SUM(TOKEN_CREDITS), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens,
    COUNT(*) AS job_count
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FINE_TUNING_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>';
```

---

### Cortex Model Training Cost by Model

**Triggered by:** "How much did I spend on model training?", "model training credits by model", "fine-tuning credits by model"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    MODEL_NAME,
    ROUND(SUM(TOKEN_CREDITS), 4) AS total_credits,
    SUM(TOKENS) AS total_tokens
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FINE_TUNING_USAGE_HISTORY
WHERE START_TIME >= '<START_TIME>'
  AND START_TIME < '<END_TIME>'
GROUP BY MODEL_NAME
ORDER BY total_credits DESC;
```

---

### Cortex Model Training Daily Cost Trend (with Week-over-Week Change)

**Triggered by:** "How has my model training spend changed over time?", "model training cost trend", "are training jobs increasing?"

> Training jobs are infrequent; many days will show 0 credits. The WoW column helps surface whether activity is increasing.

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
WITH daily AS (
    SELECT
        DATE(START_TIME) AS usage_date,
        ROUND(SUM(TOKEN_CREDITS), 4) AS daily_credits,
        SUM(TOKENS) AS daily_tokens,
        COUNT(*) AS job_count
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_FINE_TUNING_USAGE_HISTORY
    WHERE START_TIME >= DATEADD('day', -7, '<START_TIME>')
      AND START_TIME < '<END_TIME>'
    GROUP BY DATE(START_TIME)
),
with_prev AS (
    SELECT
        usage_date,
        daily_credits,
        daily_tokens,
        job_count,
        LAG(daily_credits, 7) OVER (ORDER BY usage_date) AS prev_week_credits
    FROM daily
)
SELECT
    usage_date,
    daily_credits,
    daily_tokens,
    job_count,
    CASE
        WHEN daily_credits >= prev_week_credits
            THEN '+' || ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
        ELSE ROUND((daily_credits - prev_week_credits) / NULLIF(prev_week_credits, 0) * 100, 1)::VARCHAR || '%'
    END AS wow_change_pct
FROM with_prev
WHERE usage_date >= '<START_TIME>'
ORDER BY usage_date ASC;
```
