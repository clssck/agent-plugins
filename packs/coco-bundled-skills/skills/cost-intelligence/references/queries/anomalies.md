# Anomalies Queries

Queries for detecting and analyzing cost anomalies - unusual spending patterns that deviate from expected forecasts.

**Semantic keywords:** anomalies, anomaly, unusual spending, cost spike, spend anomalies, variance, forecast, unexpected costs, anomaly days, contributors, anomaly trends, cost deviation

---

### Leading Contributors to Each Anomaly

**Triggered by:** "For each cost anomaly over the past 4 months, what resources contributed most to the excessive spending?", "anomaly contributors", "what caused anomalies?"

```sql
WITH anomaly_dates AS (
    SELECT DISTINCT
        date as anomaly_date,
        actual_value,
        forecasted_value,
        (actual_value - forecasted_value) as anomaly_impact
    FROM SNOWFLAKE.ACCOUNT_USAGE.ANOMALIES_DAILY 
    WHERE is_anomaly = TRUE
      AND date >= DATEADD('month', -4, CURRENT_DATE())
), 
anomaly_day_spending AS (
    SELECT
        DATE(m.start_time) as usage_date,
        m.service_type,
        m.name as resource_name,
        SUM(m.credits_used) as daily_credits,
        SUM(m.credits_used_compute) as daily_compute_credits,
        SUM(m.credits_used_cloud_services) as daily_cloud_credits
    FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY m 
    JOIN anomaly_dates ad
        ON DATE(m.start_time) = ad.anomaly_date
    WHERE m.start_time >= DATEADD('month', -4, CURRENT_DATE()) 
    GROUP BY DATE(m.start_time), m.service_type, m.name
), 
normal_day_baseline AS (
    SELECT
        service_type,
        name as resource_name,
        AVG(daily_credits) as avg_normal_credits
    FROM (
        SELECT
            DATE(m.start_time) as usage_date,
            m.service_type as service_type,
            m.name as name,
            SUM(m.credits_used) as daily_credits
        FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY m
        WHERE m.start_time >= DATEADD('month', -4, CURRENT_DATE())
          AND DATE(m.start_time) NOT IN (SELECT anomaly_date FROM anomaly_dates)
        GROUP BY DATE(m.start_time), m.service_type, m.name
    ) normal_days
    GROUP BY service_type, name
),
anomaly_contributors AS (
    SELECT
        ads.usage_date as anomaly_date,
        ads.service_type,
        ads.resource_name,
        ROUND(ads.daily_credits, 2) as anomaly_day_credits,
        ROUND(COALESCE(nb.avg_normal_credits, 0), 2) as avg_normal_day_credits,
        ROUND(ads.daily_credits - COALESCE(nb.avg_normal_credits, 0), 2) as credits_above_normal,
        CASE
            WHEN nb.avg_normal_credits > 0 THEN
                ROUND(((ads.daily_credits - nb.avg_normal_credits) / nb.avg_normal_credits) * 100, 2)
            ELSE NULL
        END as percent_above_normal,
        ROW_NUMBER() OVER (
            PARTITION BY ads.usage_date
            ORDER BY (ads.daily_credits - COALESCE(nb.avg_normal_credits, 0)) DESC
        ) as contributor_rank
    FROM anomaly_day_spending ads
    LEFT JOIN normal_day_baseline nb
        ON ads.service_type = nb.service_type
       AND ads.resource_name = nb.resource_name
    WHERE ads.daily_credits > 0
)
SELECT
    anomaly_date,
    contributor_rank,
    service_type,
    resource_name,
    anomaly_day_credits,
    avg_normal_day_credits,
    credits_above_normal,
    percent_above_normal,
    CASE
        WHEN percent_above_normal > 200 THEN 'Major Contributor'
        WHEN percent_above_normal > 100 THEN 'Significant Contributor'
        WHEN percent_above_normal > 50 THEN 'Moderate Contributor'
        WHEN credits_above_normal > 50 THEN 'High Cost Contributor'
        ELSE 'Minor Contributor'
    END as contribution_level
FROM anomaly_contributors
WHERE credits_above_normal > 0
  AND contributor_rank <= 5
ORDER BY anomaly_date DESC, contributor_rank ASC;
```

---

### Top Warehouses by Consumption

**Triggered by:** "which warehouses used the most credits on that day?", "top warehouses on anomaly date", "what warehouse caused the spike?"

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_TOP_WAREHOUSES_ON_DATE(
    '<target_date>',
    10,
    '<account_name>'
);
```
---

### Hourly Breakdown of Consumption

**Triggered by:** "when did the spike happen during the day?", "hourly spend on anomaly date", "what time did costs spike?"

> **Current-account only:** This procedure returns data for the **current account only**. It cannot return data for other accounts or the entire organization. Do NOT call it when investigating a different account or org-wide anomalies — inform the user that hourly breakdown by service type is unavailable for that scope and suggest the top warehouses drill-down as an alternative.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_HOURLY_CONSUMPTION_BY_SERVICE_TYPE('<target_date>', <num_of_entries>);
```

---

### Top Queries from Warehouse

**Triggered by:** "which queries ran on that warehouse?", "top queries from warehouse", "what queries caused the spike on that warehouse?"

> **Current-account only:** This procedure returns data for the **current account only**. It cannot return data for other accounts or the entire organization. Do NOT call it when investigating a different account or org-wide anomalies — inform the user that query-level drill-downs from a specific warehouse are unavailable for that scope.

```sql
CALL SNOWFLAKE.LOCAL.ANOMALY_INSIGHTS!GET_TOP_QUERIES_FROM_WAREHOUSE(<warehouse_id>, '<target_date>', <number_of_queries>);
```

---

### Fallback: ANOMALIES_DAILY View (Last Resort)

> **When to use:** Only when the user lacks access to `ANOMALY_INSIGHTS` procedures but has `APP_USAGE_VIEWER` or `APP_USAGE_ADMIN`. Account-level, credits only, up to 8 hours latency, no procedure-based drill-downs.

```sql
SELECT
    date,
    anomaly_id,
    actual_value AS consumption_credits,
    forecasted_value,
    upper_bound,
    lower_bound,
    ROUND(actual_value - forecasted_value, 2) AS variance_credits,
    ROUND(((actual_value - forecasted_value) / NULLIF(forecasted_value, 0)) * 100, 2) AS variance_pct
FROM SNOWFLAKE.ACCOUNT_USAGE.ANOMALIES_DAILY
WHERE is_anomaly = TRUE
  AND date >= DATEADD('day', -90, CURRENT_DATE())
ORDER BY variance_credits DESC;
```

> After fetching anomaly dates, use the "Leading Contributors to Each Anomaly" query (above) to drill into causes — it joins `ANOMALIES_DAILY` with `METERING_HISTORY` at the same access level.
