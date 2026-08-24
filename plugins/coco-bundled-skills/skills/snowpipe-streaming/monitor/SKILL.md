---
name: snowpipe-streaming-monitor
description: "Monitor Snowpipe Streaming High-Performance Architecture pipeline health, channels, and costs."
parent_skill: snowpipe-streaming
---

# Monitor Snowpipe Streaming (High-Performance Architecture)

## When to Load

Parent skill routes here for MONITOR intent.

## Workflow

### Step 1: Determine Monitoring Scope

**Ask** the user:
```
What do you want to monitor?

1. Channel health & status
2. Ingestion progress & throughput
3. Costs & billing
4. All of the above
```

### Step 2: Channel Health

**List active channels:**
```sql
SHOW CHANNELS IN TABLE <DATABASE>.<SCHEMA>.<TABLE>;
```

**Channel history (last 24h):**
```sql
SELECT
    CHANNEL_NAME,
    EVENT_TYPE,
    EVENT_TIMESTAMP,
    ERROR_MESSAGE
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPIPE_STREAMING_CHANNEL_HISTORY
WHERE PIPE_NAME ILIKE '%<TABLE>%'
  AND EVENT_TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP())
ORDER BY EVENT_TIMESTAMP DESC;
```

**Via Python SDK:**
```python
statuses = client.get_channel_statuses(["channel_1", "channel_2"])
for name, status in statuses.items():
    print(f"{name}: code={status.status_code}, errors={status.row_error_count}")
```

### Step 3: Ingestion Progress

**First, identify the timestamp column.** Ask the user:
```
Which column should I use for time-based queries?

Common options:
1. A column in the table (e.g., created_at, ingested_at, event_time)
2. METADATA$ROW_LAST_COMMIT_TIME (Snowflake row timestamps — measures when rows were committed)
```

If the user has `ROW_TIMESTAMP = TRUE` on their table, prefer `METADATA$ROW_LAST_COMMIT_TIME` — it provides the most accurate ingestion latency measurement. See "Row Timestamps" section below.

**Row count over time:**
```sql
SELECT
    DATE_TRUNC('minute', <TIMESTAMP_COLUMN>) AS minute,
    COUNT(*) AS rows_ingested
FROM <DATABASE>.<SCHEMA>.<TABLE>
WHERE <TIMESTAMP_COLUMN> > DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP BY minute
ORDER BY minute;
```

**Offset progress (if metadata columns exist):**
```sql
SELECT
    CHANNEL_ID,
    MAX(STREAM_OFFSET) AS latest_offset,
    MIN(STREAM_OFFSET) AS earliest_offset,
    COUNT(*) AS row_count
FROM <DATABASE>.<SCHEMA>.<TABLE>
WHERE <TIMESTAMP_COLUMN> > DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP BY CHANNEL_ID;
```

**Via Python SDK:**
```python
tokens = client.get_latest_committed_offset_tokens(["ch1", "ch2"])
for name, token in tokens.items():
    print(f"{name}: last_committed={token}")
```

### Step 4: Costs & Billing

**Streaming credits used:**
```sql
SELECT
    PIPE_NAME,
    DATE_TRUNC('day', START_TIME) AS day,
    SUM(CREDITS_USED) AS total_credits,
    SUM(BYTES_INSERTED) AS total_bytes
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE SERVICE_TYPE = 'SNOWPIPE_STREAMING'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP())
GROUP BY PIPE_NAME, day
ORDER BY day DESC;
```

**Cost per GB calculation:**
```sql
SELECT
    PIPE_NAME,
    SUM(CREDITS_USED) AS credits,
    SUM(BYTES_INSERTED) / POWER(1024, 3) AS gb_ingested,
    CASE WHEN SUM(BYTES_INSERTED) > 0
         THEN SUM(CREDITS_USED) / (SUM(BYTES_INSERTED) / POWER(1024, 3))
         ELSE 0 END AS credits_per_gb
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE SERVICE_TYPE = 'SNOWPIPE_STREAMING'
  AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP())
GROUP BY PIPE_NAME;
```

### Step 5: Prometheus Metrics (Optional)

If the application supports it, enable Prometheus metrics:

```bash
export SS_ENABLE_METRICS=true
# Scrape at http://<host>:50000/metrics
```

Prometheus scrape config:
```yaml
scrape_configs:
  - job_name: snowpipe_streaming_hp
    metrics_path: /metrics
    static_configs:
      - targets: ['127.0.0.1:50000']
```

### Step 6: Set Up Alerts

**Snowflake Alert for channel errors:**
```sql
CREATE OR REPLACE ALERT <DATABASE>.<SCHEMA>.STREAMING_CHANNEL_ERROR_ALERT
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE = '5 MINUTE'
    IF (EXISTS (
        SELECT 1
        FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPIPE_STREAMING_CHANNEL_HISTORY
        WHERE PIPE_NAME ILIKE '%<TABLE>%'
          AND ERROR_MESSAGE IS NOT NULL
          AND EVENT_TIMESTAMP > DATEADD(minute, -5, CURRENT_TIMESTAMP())
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'streaming_alerts',
            'team@example.com',
            'Snowpipe Streaming Channel Error',
            'Channel errors detected in the last 5 minutes. Check SNOWPIPE_STREAMING_CHANNEL_HISTORY.'
        );

ALTER ALERT <DATABASE>.<SCHEMA>.STREAMING_CHANNEL_ERROR_ALERT RESUME;
```

**Alert for ingestion lag (no rows in 10 minutes):**
```sql
CREATE OR REPLACE ALERT <DATABASE>.<SCHEMA>.STREAMING_LAG_ALERT
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE = '10 MINUTE'
    IF (EXISTS (
        SELECT 1
        FROM <DATABASE>.<SCHEMA>.<TABLE>
        HAVING MAX(<TIMESTAMP_COLUMN>) < DATEADD(minute, -10, CURRENT_TIMESTAMP())
           OR COUNT(*) = 0
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'streaming_alerts',
            'team@example.com',
            'Snowpipe Streaming Lag Detected',
            'No new rows ingested in the last 10 minutes.'
        );

ALTER ALERT <DATABASE>.<SCHEMA>.STREAMING_LAG_ALERT RESUME;
```

**Alert for cost spike:**
```sql
CREATE OR REPLACE ALERT <DATABASE>.<SCHEMA>.STREAMING_COST_ALERT
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE = '60 MINUTE'
    IF (EXISTS (
        SELECT 1
        FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
        WHERE SERVICE_TYPE = 'SNOWPIPE_STREAMING'
          AND START_TIME > DATEADD(hour, -1, CURRENT_TIMESTAMP())
        HAVING SUM(CREDITS_USED) > 10  -- Adjust threshold
    ))
    THEN
        CALL SYSTEM$SEND_EMAIL(
            'streaming_alerts',
            'team@example.com',
            'Snowpipe Streaming Cost Spike',
            'Streaming credits exceeded threshold in the last hour.'
        );

ALTER ALERT <DATABASE>.<SCHEMA>.STREAMING_COST_ALERT RESUME;
```

**Webhook notification (alternative to email):**
```sql
CREATE OR REPLACE NOTIFICATION INTEGRATION STREAMING_WEBHOOK
    TYPE = WEBHOOK
    ENABLED = TRUE
    WEBHOOK_URL = 'https://hooks.slack.com/services/...'
    WEBHOOK_SECRET = snowflake.secrets.streaming_webhook_secret;

-- Then use in alert:
CALL SYSTEM$SEND_NOTIFICATION('STREAMING_WEBHOOK', '{"text": "Channel error detected"}');
```

### Step 7: Run Health Check Script

For a comprehensive automated check:
```bash
uv run --project <SKILL_DIR>/scripts python <SKILL_DIR>/scripts/health_check.py \
  --database <DB> --schema <SCHEMA> --table <TABLE> \
  --connection <CONNECTION_NAME>
```

**⚠️ STOP**: Present monitoring results to user.

## Row Timestamps (METADATA$ROW_LAST_COMMIT_TIME)

Row timestamps provide the most accurate measure of ingestion latency — they record exactly when each row was committed to Snowflake, not when the client generated the event.

**Enable on a streaming target table:**
```sql
ALTER TABLE <DATABASE>.<SCHEMA>.<TABLE> SET ROW_TIMESTAMP = TRUE;
```

**Or enable by default for all new tables in a schema:**
```sql
ALTER SCHEMA <DATABASE>.<SCHEMA> SET ROW_TIMESTAMP_DEFAULT = TRUE;
```

**Measure ingestion latency** (requires a client-side timestamp column):
```sql
SELECT
    <CLIENT_TIMESTAMP_COLUMN>,
    METADATA$ROW_LAST_COMMIT_TIME AS commit_time,
    TIMESTAMPDIFF('ms', <CLIENT_TIMESTAMP_COLUMN>, METADATA$ROW_LAST_COMMIT_TIME) AS ingest_latency_ms
FROM <DATABASE>.<SCHEMA>.<TABLE>
ORDER BY commit_time DESC
LIMIT 20;
```

**Use as the timestamp column for monitoring queries** — replace `<TIMESTAMP_COLUMN>` with `METADATA$ROW_LAST_COMMIT_TIME` in all queries above.

**Limitations**:
- Rows inserted before enabling ROW_TIMESTAMP will have NULL commit times
- Not supported on Iceberg tables, external tables, or hybrid tables
- Timestamps reflect last update time, not creation time (relevant for tables with UPDATEs)

See: [Row Timestamps Documentation](https://docs.snowflake.com/en/user-guide/data-engineering/row-timestamps)

## Useful Views

| View | Purpose |
|------|---------|
| `ACCOUNT_USAGE.SNOWPIPE_STREAMING_CHANNEL_HISTORY` | Channel events and errors |
| `ACCOUNT_USAGE.METERING_HISTORY` | Streaming credits and bytes |
| `ACCOUNT_USAGE.PIPES` | Pipe metadata |
| `SHOW CHANNELS` | Active channel listing |
| `SHOW PIPES` | Pipe listing and status |

## Stopping Points

- ✋ Step 7: Results presented

## Output

Monitoring report with channel health, ingestion throughput, and cost analysis.
