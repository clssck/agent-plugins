---
name: snowpipe-streaming-optimize
description: "Optimize Snowpipe Streaming High-Performance Architecture throughput, latency, and costs."
parent_skill: snowpipe-streaming
---

# Optimize Snowpipe Streaming (High-Performance Architecture)

## When to Load

Parent skill routes here for OPTIMIZE intent.

## Workflow

### Step 1: Assess Current State

**Ask** the user:
```
What are you looking to optimize?

1. Throughput (rows/sec or GB/s)
2. Latency (ingest-to-query time)
3. Cost (credits per GB)
4. All of the above
```

**Gather baseline metrics:**
```sql
-- Throughput: rows per minute (last hour)
SELECT
    DATE_TRUNC('minute', <TIMESTAMP_COLUMN>) AS minute,
    COUNT(*) AS rows_per_min
FROM <TABLE>
WHERE <TIMESTAMP_COLUMN> > DATEADD(hour, -1, CURRENT_TIMESTAMP())
GROUP BY minute
ORDER BY minute;

-- Cost: credits used (last 7 days)
SELECT
    PIPE_NAME,
    SUM(CREDITS_USED) AS total_credits,
    SUM(BYTES_INSERTED) / POWER(1024, 3) AS gb_ingested,
    CASE WHEN SUM(BYTES_INSERTED) > 0
         THEN SUM(CREDITS_USED) / (SUM(BYTES_INSERTED) / POWER(1024, 3))
         ELSE 0 END AS credits_per_gb
FROM SNOWFLAKE.ACCOUNT_USAGE.METERING_HISTORY
WHERE SERVICE_TYPE = 'SNOWPIPE_STREAMING'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP())
GROUP BY PIPE_NAME;
```

**⚠️ STOP**: Present baseline to user before recommending changes.

### Step 2: Throughput Optimization

**Scale out with multiple channels:**
- One channel per partition/tenant for ordered delivery
- More channels = higher aggregate throughput
- Benchmark reference: 4 channels per instance × 6 instances

**Use batch inserts:**
```python
# Instead of individual append_row calls:
channel.append_rows(
    rows=[row1, row2, row3, ...],
    start_offset_token="100",
    end_offset_token="199",
)
```

**Use native types for VARIANT:**
```python
# GOOD: Native dict → SDK handles serialization
row["event_data"] = {"key": "value", "count": 42}

# BAD: JSON string → stored as VARCHAR, not OBJECT
row["event_data"] = '{"key": "value", "count": 42}'
```

**REST API: Use compression:**
```bash
export SS_COMPRESSION=ZSTD  # or gzip
```
ZSTD recommended — fits more data per 4MB request limit.

### Step 3: Latency Optimization

**Minimize flush intervals:**
- Default auto-flush: ~1 second
- Force immediate: `channel.initiate_flush()`
- Wait for commit: `channel.wait_for_commit(token_checker, timeout_seconds=10)`

**Caution**: Calling `initiate_flush()` too frequently reduces throughput and increases cost.

**Enable pre-clustering at ingest time** (reduces query latency):
```sql
CREATE OR REPLACE PIPE <DATABASE>.<SCHEMA>.<PIPE_NAME>
AS COPY INTO <TABLE>
  FROM (SELECT $1, $1:c1, $1:ts FROM TABLE(DATA_SOURCE(TYPE => 'STREAMING')))
  MATCH_BY_COLUMN_NAME = CASE_SENSITIVE
  CLUSTER_AT_INGEST_TIME = TRUE;
```

Requires clustering keys on the target table:
```sql
ALTER TABLE <TABLE> CLUSTER BY (col1, col2);
```

### Step 4: Cost Optimization

**Use MATCH_BY_COLUMN_NAME:**
```sql
CREATE OR REPLACE PIPE <PIPE_NAME>
AS COPY INTO <TABLE>
  FROM (SELECT $1 FROM TABLE(DATA_SOURCE(TYPE => 'STREAMING')))
  MATCH_BY_COLUMN_NAME = CASE_SENSITIVE;
```
Bills only for ingested column values, not full JSON keys+values.

**Reduce channel count if over-provisioned:**
- Inactive channels are auto-deleted after 30 days
- Each channel has some overhead — consolidate where order doesn't matter

**Right-size batches:**
- Small batches = more overhead per row
- Aim for 1000+ rows per `append_rows` call when possible
- Balance batch size vs. latency requirements

**Monitor costs actively:**
```sql
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

### Step 5: Resilience Optimization

**Implement self-healing channels** (pattern from reference code):
```python
MAX_RECOVERY_ATTEMPTS = 3

for attempt in range(MAX_RECOVERY_ATTEMPTS):
    try:
        channel.append_row(row, offset_token)
        break
    except Exception as e:
        if is_recoverable(e) and attempt < MAX_RECOVERY_ATTEMPTS - 1:
            channel = reopen_channel(channel_name)
            continue
        raise
```

**Use load shedding** to prevent cascading failures:
```python
semaphore = asyncio.Semaphore(MAX_CONCURRENT_STREAMS)
if semaphore.locked():
    return 503  # Reject at capacity
```

**Add circuit breaker** to prevent thundering herd during outages:

See `references/python-sdk.md` → "Circuit Breaker Pattern" for full implementation.

Key parameters:
- `failure_threshold=5` — open circuit after 5 consecutive failures
- `recovery_timeout=30.0` — wait 30s before probing recovery
- `half_open_max_calls=3` — allow 3 test requests during recovery probe

```python
from circuit_breaker import CircuitBreaker, ResilientStreamingService

resilient = ResilientStreamingService(service, CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30.0,
))
```

### Step 6: Channel Lifecycle Best Practices

**Use deterministic channel names** — predictable names make monitoring, recovery, and debugging far easier:
```python
channel_name = f"kafka-prod-{partition_id}"
# NOT: channel_name = f"channel-{uuid.uuid4()}"
```

**Reopen, don't recreate** — on errors, reopen the same channel name. Creating new random names leaks inactive channels and loses offset tracking:
```python
# On error — reopen same name to resume from last committed offset
channel = client.open_channel(
    OpenChannelRequest(
        channel_name=channel_name,  # same deterministic name
        pipe_name=pipe_name,
        table_name=table_name,
    )
)
```

**Understand auto-expiry** — channels are automatically cleaned up after **30 days of inactivity**. Plan accordingly:
- For bursty workloads, accept that channels may expire between bursts
- On reconnect, always reopen by name — the SDK handles offset recovery
- Do not rely on channel existence for state tracking

**Avoid unnecessary drop/recreate cycles** — each drop/recreate incurs metadata overhead and resets offset tracking. Only drop channels when permanently decommissioning a data source.

**⚠️ STOP**: Present optimization recommendations with expected impact.

## Optimization Checklist

| Area | Technique | Impact |
|------|-----------|--------|
| Throughput | Multiple channels | High |
| Throughput | Batch append_rows | Medium |
| Throughput | Native types for VARIANT | Medium |
| Latency | Pre-clustering at ingest | High (query side) |
| Cost | MATCH_BY_COLUMN_NAME | High |
| Cost | Right-size batches | Medium |
| Cost | REST API compression (ZSTD) | Medium |
| Resilience | Auto channel recovery | High |
| Resilience | Load shedding | Medium |
| Resilience | Circuit breaker | High |
| Lifecycle | Deterministic channel names | High |
| Lifecycle | Reopen, don't recreate | High |

## Stopping Points

- ✋ Step 1: Baseline assessed
- ✋ Step 6: Recommendations presented

## Output

Optimized pipeline configuration with measurable improvements.
