# Snowpipe Streaming Monitoring Queries

> **`<TIMESTAMP_COLUMN>`** — Replace with the user's timestamp column (e.g., `created_at`, `ingested_at`) or `METADATA$ROW_LAST_COMMIT_TIME` if row timestamps are enabled.

## Channel Health

```sql
-- List active channels for a table
SHOW CHANNELS IN TABLE <DATABASE>.<SCHEMA>.<TABLE>;

-- Channel event history (last 24h)
SELECT
    CHANNEL_NAME,
    EVENT_TYPE,
    EVENT_TIMESTAMP,
    ERROR_MESSAGE
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPIPE_STREAMING_CHANNEL_HISTORY
WHERE PIPE_NAME ILIKE '%<TABLE>%'
  AND EVENT_TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP())
ORDER BY EVENT_TIMESTAMP DESC;

-- Pipe status
SHOW PIPES LIKE '%<TABLE>%' IN SCHEMA <DATABASE>.<SCHEMA>;
```

## Ingestion Throughput

```sql
-- Rows per minute (last hour)
SELECT
    DATE_TRUNC('minute', <TIMESTAMP_COLUMN>) AS minute,
    COUNT(*) AS rows_per_min
FROM <DATABASE>.<SCHEMA>.<TABLE>
WHERE <TIMESTAMP_COLUMN> > DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP BY minute
ORDER BY minute;

-- Rows by source/instance
SELECT
    instance_id,
    COUNT(*) AS row_count,
    MIN(<TIMESTAMP_COLUMN>) AS earliest,
    MAX(<TIMESTAMP_COLUMN>) AS latest
FROM <DATABASE>.<SCHEMA>.<TABLE>
WHERE <TIMESTAMP_COLUMN> > DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP BY instance_id
ORDER BY row_count DESC;
```

## Offset Gap Detection

```sql
-- Find gaps in offset sequence (requires STREAM_OFFSET column)
SELECT
    CHANNEL_ID,
    STREAM_OFFSET,
    LAG(STREAM_OFFSET) OVER (
        PARTITION BY CHANNEL_ID ORDER BY STREAM_OFFSET
    ) AS prev_offset,
    STREAM_OFFSET - prev_offset AS gap
FROM <DATABASE>.<SCHEMA>.<TABLE>
QUALIFY gap > 1
ORDER BY CHANNEL_ID, STREAM_OFFSET;

-- Missing record detection with PIPE_ID
SELECT
    PIPE_ID,
    CHANNEL_ID,
    STREAM_OFFSET,
    LAG(STREAM_OFFSET) OVER (
        PARTITION BY PIPE_ID, CHANNEL_ID
        ORDER BY STREAM_OFFSET
    ) AS previous_offset,
    (LAG(STREAM_OFFSET) OVER (
        PARTITION BY PIPE_ID, CHANNEL_ID
        ORDER BY STREAM_OFFSET
    ) + 1) AS expected_next
FROM <DATABASE>.<SCHEMA>.<TABLE>
QUALIFY STREAM_OFFSET != previous_offset + 1;
```

## Cost Analysis

```sql
-- Daily credits used (last 7 days)
SELECT
    PIPE_NAME,
    DATE_TRUNC('day', START_TIME) AS day,
    SUM(CREDITS_USED) AS total_credits,
    SUM(BYTES_INSERTED) / POWER(1024, 3) AS gb_ingested,
    CASE WHEN SUM(BYTES_INSERTED) > 0
         THEN SUM(CREDITS_USED) / (SUM(BYTES_INSERTED) / POWER(1024, 3))
         ELSE 0 END AS credits_per_gb
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE SERVICE_TYPE = 'SNOWPIPE_STREAMING'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP())
GROUP BY PIPE_NAME, day
ORDER BY day DESC;

-- Hourly cost trend (last 24h)
SELECT
    DATE_TRUNC('hour', START_TIME) AS hour,
    SUM(CREDITS_USED) AS credits,
    SUM(BYTES_INSERTED) / POWER(1024, 2) AS mb_ingested
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE SERVICE_TYPE = 'SNOWPIPE_STREAMING'
  AND START_TIME > DATEADD(day, -1, CURRENT_TIMESTAMP())
GROUP BY hour
ORDER BY hour;
```

## Data Verification

```sql
-- Row count
SELECT COUNT(*) FROM <DATABASE>.<SCHEMA>.<TABLE>;

-- Verify VARIANT columns stored correctly
SELECT col_name, TYPEOF(col_name) AS data_type
FROM <DATABASE>.<SCHEMA>.<TABLE>
LIMIT 10;

-- Recent rows
SELECT * FROM <DATABASE>.<SCHEMA>.<TABLE>
ORDER BY <TIMESTAMP_COLUMN> DESC
LIMIT 10;
```
