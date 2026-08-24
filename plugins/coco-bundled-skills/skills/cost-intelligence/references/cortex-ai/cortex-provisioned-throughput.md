# Cortex Provisioned Throughput Cost Queries

Queries for analyzing credit cost for Cortex Provisioned Throughput (PTUs).

**Semantic keywords:** provisioned throughput, PTU, PTU credits, dedicated capacity, reserved throughput, provisioned throughput cost

**Base View:** `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_PROVISIONED_THROUGHPUT_USAGE_HISTORY`

> Billing for dedicated provisioned throughput units (PTUs). No per-user attribution available.

---

### Total Cost Summary

**Triggered by:** "What's my total provisioned throughput cost?", "summarize PTU spend", "how much did provisioned throughput cost this period?"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    ROUND(SUM(PTU_CREDITS), 4) AS total_ptu_credits,
    SUM(PTU_COUNT) AS total_ptu_hours,
    COUNT(DISTINCT MODEL_NAME) AS active_models
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_PROVISIONED_THROUGHPUT_USAGE_HISTORY
WHERE INTERVAL_START_TIME >= '<START_TIME>'
  AND INTERVAL_START_TIME < '<END_TIME>';
```

---

### Cost by Model

**Triggered by:** "How much am I spending on provisioned throughput?", "PTU credits by model", "provisioned throughput cost breakdown"

> **Note:** Keep the time window to at most one month to avoid query timeouts.

```sql
SELECT
    MODEL_NAME,
    CLOUD_SERVICE_PROVIDER,
    ROUND(SUM(PTU_CREDITS), 4) AS total_ptu_credits,
    SUM(PTU_COUNT) AS total_ptu_hours
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_PROVISIONED_THROUGHPUT_USAGE_HISTORY
WHERE INTERVAL_START_TIME >= '<START_TIME>'
  AND INTERVAL_START_TIME < '<END_TIME>'
GROUP BY MODEL_NAME, CLOUD_SERVICE_PROVIDER
ORDER BY total_ptu_credits DESC;
```

---

### PTU Utilization Over Active Term

**Triggered by:** "Show me PTU cost over the active contract period", "provisioned throughput trend", "PTU spend over time"

> PTUs are billed continuously for the duration of the term regardless of cost; tracking this against actual query volume helps assess ROI.

```sql
SELECT
    DATE_TRUNC('DAY', INTERVAL_START_TIME) AS usage_date,
    MODEL_NAME,
    ROUND(SUM(PTU_CREDITS), 4) AS daily_ptu_credits,
    AVG(PTU_COUNT) AS avg_active_ptus
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_PROVISIONED_THROUGHPUT_USAGE_HISTORY
WHERE INTERVAL_START_TIME >= '<TERM_START_DATE>'
  AND INTERVAL_START_TIME <= '<TERM_END_DATE>'
GROUP BY usage_date, MODEL_NAME
ORDER BY usage_date DESC;
```
