---
name: snowpipe-streaming-troubleshoot
description: "Troubleshoot Snowpipe Streaming High-Performance Architecture pipeline issues."
parent_skill: snowpipe-streaming
---

# Troubleshoot Snowpipe Streaming (High-Performance Architecture)

## When to Load

Parent skill routes here for TROUBLESHOOT intent.

## Workflow

### Step 1: Identify the Problem

**Ask** the user:
```
What issue are you seeing?

1. Channel errors (invalid state, token expired)
2. Data not appearing in table
3. Schema mismatch / row errors
4. Rate limiting (HTTP 429)
5. Authentication failures
6. Offset gaps / missing records
7. Other (describe)
```

**⚠️ STOP**: Confirm the problem before diagnosing.

### Step 2: Enable Error Tables (Recommended First Step)

Error Tables capture per-row ingestion failures with full context. **Enable this before deep-diving into specific issues** — it dramatically reduces diagnosis time.

```sql
ALTER TABLE <DATABASE>.<SCHEMA>.<TABLE> SET ERROR_LOGGING = TRUE;
```

Query failed rows:
```sql
SELECT ERROR_TIME, ERROR_CODE, ERROR_MESSAGE,
       CHANNEL_NAME, OFFSET_TOKEN, ERROR_DATA
FROM ERROR_TABLE(<DATABASE>.<SCHEMA>.<TABLE>)
ORDER BY ERROR_TIME DESC
LIMIT 50;
```

If the error table has rows, the `ERROR_CODE` and `ERROR_DATA` columns usually point directly to the root cause (schema mismatch, type coercion failure, NULL constraint violation, etc.) — skip to the matching section below.

If the error table is empty, continue with channel-level diagnosis.

### Step 3: Diagnose

#### Channel Errors (invalid state, token expired)

**Common cause**: Channel invalidated due to inactivity (30-day auto-cleanup) or server-side error.

**Check channel status:**
```sql
SHOW CHANNELS IN TABLE <DATABASE>.<SCHEMA>.<TABLE>;
```

**Check channel history:**
```sql
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWPIPE_STREAMING_CHANNEL_HISTORY
WHERE PIPE_NAME ILIKE '%<TABLE>%'
ORDER BY EVENT_TIMESTAMP DESC
LIMIT 20;
```

**Fix**: Reopen the channel with the same name. The SDK `open_channel()` call handles this. Implement auto-recovery:

```python
def _is_recoverable_error(self, error):
    error_str = str(error).lower()
    return any(kw in error_str for kw in [
        "token has expired",
        "invalid state",
        "invalidchannelerror",
        "unauthorized",
    ])
```

#### Data Not Appearing

1. **Check flush**: Data auto-flushes ~1s. Force with `channel.wait_for_flush(timeout_seconds=30)`
2. **Check offset progress**:
```python
token = channel.get_latest_committed_offset_token()
print(f"Last committed: {token}")
```
3. **Check pipe status**:
```sql
SHOW PIPES LIKE '%<TABLE>%' IN SCHEMA <DATABASE>.<SCHEMA>;
SELECT SYSTEM$PIPE_STATUS('<DATABASE>.<SCHEMA>.<PIPE_NAME>');
```

#### Schema Mismatch / Row Errors

**Check channel status for error counts:**
```python
status = channel.get_channel_status()
# Check status.row_error_count
```

**Common causes**:
- Column name case mismatch (use `MATCH_BY_COLUMN_NAME = CASE_SENSITIVE`)
- Passing JSON strings instead of native dicts for VARIANT columns
- Wrong data types (e.g., string where NUMBER expected)

**Verify VARIANT storage**:
```sql
SELECT TYPEOF(col_name) FROM <TABLE> LIMIT 1;
-- Should return 'OBJECT', not 'VARCHAR'
```

#### Rate Limiting (HTTP 429)

Error: `CHANNEL_HAS_HIGH_INGESTION_LAG`

**Causes**: Streaming faster than Snowflake can ingest.

**Fixes**:
1. Implement exponential backoff on 429 responses
2. Reduce event rate temporarily
3. Distribute across more channels
4. Use compression for REST API (`ZSTD` recommended)
5. Check account-level streaming limits

#### Authentication Failures

**Check key format**:
```bash
# Must be unencrypted PKCS#8
openssl pkcs8 -topk8 -nocrypt -in keys/rsa_key.p8 -out keys/rsa_key_fixed.p8
```

**Verify key assignment**:
```sql
DESC USER <USERNAME>;
-- Check RSA_PUBLIC_KEY is set
```

**Verify profile.json** has `private_key` (key content) not `private_key_file` (path) for the High-Performance Architecture SDK.

#### Offset Gaps / Missing Records

**Run gap detection query** (requires `STREAM_OFFSET` metadata column):
```sql
SELECT
  CHANNEL_ID,
  STREAM_OFFSET,
  LAG(STREAM_OFFSET) OVER (
    PARTITION BY CHANNEL_ID ORDER BY STREAM_OFFSET
  ) AS prev_offset,
  STREAM_OFFSET - prev_offset AS gap
FROM <TABLE>
QUALIFY gap > 1
ORDER BY CHANNEL_ID, STREAM_OFFSET;
```

**Also run** the health_check script:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/health_check.py \
  --database <DB> --schema <SCHEMA> --table <TABLE> \
  --connection <CONNECTION_NAME>
```

### Step 4: Apply Fix

Present the diagnosis and recommended fix to the user.

**⚠️ STOP**: Get approval before applying changes.

### Step 5: Verify Fix

After applying:
1. Check data flow resumed: `SELECT COUNT(*) FROM <TABLE>;`
2. Check channel health: `SHOW CHANNELS IN TABLE <TABLE>;`
3. Monitor for 5 minutes for recurrence

## Common Error Reference

| Error | Cause | Fix |
|-------|-------|-----|
| `Token has expired` | Channel auth token stale | Reopen channel |
| `CHANNEL_HAS_HIGH_INGESTION_LAG` | Ingesting too fast | Backoff, scale channels |
| `Failed to parse private key` | Wrong key format | Convert to unencrypted PKCS#8 |
| `TYPEOF returns VARCHAR` | Passing JSON string not dict | Use native Python dicts |
| `InvalidChannelError` | Channel invalidated | Reopen with same name |
| `409 Conflict` | Channel state conflict | Reopen channel, replay from last offset |
| Rows in `ERROR_TABLE()` | Per-row ingestion failure | Check `ERROR_CODE` / `ERROR_DATA` for root cause |

## Stopping Points

- ✋ Step 1: Problem identified
- ✋ Step 2: Error tables enabled
- ✋ Step 4: Fix approved
- ✋ Step 5: Fix verified

## Output

Diagnosed issue with applied and verified fix.
