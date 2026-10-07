# Adaptive Warehouse Billing and Monitoring

## Billing Model

Adaptive warehouses use a **query-based billing model**. Charges are attributed per query based on the compute and software resources it uses (including QAS). Charges start when the **first query runs**; creating a warehouse incurs no charges.

- **QAS included** — QAS usage is attributed in compute credits; there is no separate QAS charge
- Adaptive warehouse usage is reported as **COMPUTE** in usage statements using virtual warehouse credits
- Per-query credit visibility is available via `SNOWFLAKE.ACCOUNT_USAGE.QUERY_METERING_HISTORY`
- Track aggregated spend via `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` — same view as standard warehouses

## Supported ACCOUNT_USAGE Views

| View | Notes |
|------|-------|
| `QUERY_METERING_HISTORY` | **Per-query** credit usage for adaptive warehouses (last 365 days, up to 1h latency) |
| `WAREHOUSE_METERING_HISTORY` | Aggregated warehouse-level billing; use for rollups and resource monitor context |
| `QUERY_HISTORY` | Identify adaptive warehouses via `warehouse_size = 'ADAPTIVE'` |
| `WAREHOUSE_LOAD_HISTORY` | Monitor queuing behavior; use to tune `MAX_QUERY_PERFORMANCE_LEVEL` / `QUERY_THROUGHPUT_MULTIPLIER` |
| `WAREHOUSE_EVENTS_HISTORY` | Use `EVENT_NAME = 'CONVERT_WAREHOUSE'` to audit conversion history |

For adaptive warehouses, QAS usage is included in compute credits and does not appear as a separate column. Use `WAREHOUSE_LOAD_HISTORY` to monitor queuing behavior.

## Tracking Conversions

To audit when a warehouse was converted to or from adaptive:

```sql
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_EVENTS_HISTORY
WHERE WAREHOUSE_NAME = '{{warehouse_name}}'
  AND EVENT_NAME = 'CONVERT_WAREHOUSE'
ORDER BY TIMESTAMP DESC;
```

`EVENT_REASON` will be either `CONVERT_TO_ADAPTIVE` or `CONVERT_TO_STANDARD`.

## Tracking Spend

### Per-Query Credits — QUERY_METERING_HISTORY

`SNOWFLAKE.ACCOUNT_USAGE.QUERY_METERING_HISTORY` provides per-query credit attribution for adaptive warehouses (last 365 days, up to 1 hour latency). Requires the `USAGE_VIEWER` or `GOVERNANCE_VIEWER` database role.

> **Latency note:** While a query is running, its metering row is refreshed in-place with current credit usage — charges are visible throughout the hour, not just after the query completes. This is a significant improvement over older per-query cost attribution methods that had 6+ hour lag.

**Key columns:**

| Column | Description |
|--------|-------------|
| `QUERY_ID` | Unique query identifier |
| `WAREHOUSE_NAME` | Warehouse the query ran on |
| `QUERY_METERING_HOUR` | Start of the metering hour window for this row |
| `QUERY_START_TIME` / `QUERY_END_TIME` | Query execution window |
| `CREDITS_USED_COMPUTE` | Compute credits for this query in this metering hour |
| `CREDITS_USED_CLOUD_SERVICES` | Cloud services credits |
| `CREDITS_USED` | Total credits (compute + cloud services) |

**Important:** A single long-running query produces one row per metering hour. Use `GROUP BY query_id` with `SUM(credits_used)` to get the total cost per query.

**Example — top queries by cost over the last 7 days:**

```sql
SELECT
    query_id,
    SUM(credits_used)               AS total_credits_used,
    SUM(credits_used_compute)       AS total_credits_used_compute,
    SUM(credits_used_cloud_services) AS total_credits_used_cloud_services
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_METERING_HISTORY
WHERE warehouse_name = '{{warehouse_name}}'
  AND query_start_time >= DATEADD(day, -7, CURRENT_DATE())
GROUP BY query_id
ORDER BY total_credits_used DESC;
```

> **Note:** `WAREHOUSE_NAME`, `QUERY_START_TIME`, and several other columns are NULL while a query is still running. Filter on `query_start_time IS NOT NULL` to exclude in-progress rows.

### Aggregated Warehouse-Level Spend — WAREHOUSE_METERING_HISTORY

```sql
SELECT
    warehouse_name,
    start_time,
    end_time,
    credits_used_compute,
    credits_used_cloud_services,
    credits_used
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE warehouse_name = '{{warehouse_name}}'
ORDER BY start_time DESC
LIMIT 48;
```

Use resource monitors and budgets to set spending limits — they work the same as with standard warehouses.