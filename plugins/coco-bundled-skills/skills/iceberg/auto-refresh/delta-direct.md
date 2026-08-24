---
name: delta-direct-auto-refresh
description: "Debug auto-refresh for Delta Direct tables (Iceberg from Delta Lake). Sub-skill of auto-refresh."
parent_skill: auto-refresh
---

# Delta Direct Auto-Refresh Debugging

Debug auto-refresh for Delta Direct tables (Iceberg tables created from Delta Lake files).

[← Back to main skill](SKILL.md)

## What is Delta Direct?

- Creates Iceberg tables from Delta Lake files in object storage (S3, GCS, Azure)
- Uses `TABLE_FORMAT = DELTA` in catalog integration
- Auto-refresh polls Delta Lake `_delta_log`

---

## Step 1: Validate Table

Ask: **What is the fully qualified table name?**

```sql
SHOW ICEBERG TABLES LIKE '<table_part>' IN <DATABASE>.<SCHEMA>;
```

| Result | Action |
|--------|--------|
| `invalid = false` | Confirm Delta source → Step 1B |
| `invalid = true` | Table invalid - ask user to recreate |
| No rows | Check if regular table exists |

### Step 1B: Confirm Delta Source

```sql
DESCRIBE CATALOG INTEGRATION <catalog_name>;
```

Verify `TABLE_FORMAT = DELTA`. If not Delta-based → use main SKILL.md instead.

---

## Step 2: Check Auto-Refresh Status

```sql
SELECT SYSTEM$AUTO_REFRESH_STATUS('<TABLE_NAME>');
```

**Key fields:** `executionState`, `pendingSnapshotCount`, `oldestSnapshotTime`

| executionState | Go to |
|----------------|-------|
| RUNNING | Step 3A |
| STALLED | Step 3B |
| STOPPED | Step 3C |
| NULL/error | Step 3D |

---

## Step 3A: Status RUNNING

| Issue | Go to |
|-------|-------|
| Data stale | Step 4 |
| Refresh slow | Step 5 |
| High costs | Step 6 |
| Delta-specific errors | Step 7 |
| Stuck/hanging | Step 3E |

---

## Step 3B: Status STALLED

Wait 5 minutes, re-check status.
- RUNNING → Resolved
- STOPPED → Step 3C
- Still STALLED → Step 8

---

## Step 3C: Status STOPPED

**⚠️ MANDATORY CHECKPOINT**: Ask user approval before recovery.

Recovery:
1. `ALTER ICEBERG TABLE <TABLE_NAME> SET AUTO_REFRESH = FALSE;`
2. `ALTER ICEBERG TABLE <TABLE_NAME> REFRESH;`
3. `ALTER ICEBERG TABLE <TABLE_NAME> SET AUTO_REFRESH = TRUE;`
4. Verify status

If still not RUNNING → Step 8

---

## Step 3D: Status NULL

```sql
SHOW ICEBERG TABLES LIKE '<table_part>';
```

- AUTO_REFRESH = FALSE → Enable it
- AUTO_REFRESH = TRUE but NULL → Step 9

---

## Step 3E: Refresh Stuck

**⚠️ CHECKPOINT**: Ask before manual refresh test.

```sql
ALTER ICEBERG TABLE <TABLE_NAME> REFRESH;
```

| Result | Action |
|--------|--------|
| Succeeds | Reset pipe: toggle AUTO_REFRESH off/on |
| Fails | Check Step 7 for Delta-specific errors |

If still stuck → Step 8

---

## Step 4: Data Staleness

```sql
SELECT * FROM TABLE(INFORMATION_SCHEMA.ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY(
  TABLE_NAME => '<TABLE_NAME>'
)) ORDER BY REFRESH_START_TIME DESC LIMIT 10;
```

Check pending:
```sql
SELECT PARSE_JSON(SYSTEM$AUTO_REFRESH_STATUS('<TABLE_NAME>')):pendingSnapshotCount;
```

| pendingSnapshotCount | Action |
|---------------------|--------|
| 0 | Source may have no new commits in `_delta_log` |
| 1-50 | Wait for processing |
| >50 | **⚠️ CHECKPOINT** - Offer manual refresh |

---

## Step 5: Refresh Interval

```sql
DESCRIBE CATALOG INTEGRATION <catalog_name>;
ALTER CATALOG INTEGRATION <catalog_name> SET REFRESH_INTERVAL_SECONDS = <value>;
```

> For integrations created before v9.2, must manually set REFRESH_INTERVAL_SECONDS.

---

## Step 6: Cost Investigation

```sql
SELECT pipe_name, credits_used, bytes_inserted
FROM SNOWFLAKE.ACCOUNT_USAGE.PIPE_USAGE_HISTORY
WHERE start_time > DATEADD(day, -7, CURRENT_TIMESTAMP());
```

> Delta-based tables show NULL pipe_name.

High costs → Increase REFRESH_INTERVAL_SECONDS.

---

## Step 7: Delta-Specific Issues

### Unsupported Features

These Delta Lake features are NOT supported:
- Row tracking
- Deletion vector files
- Change data files / CDC
- Protocol evolution

### Partition Streams

- With partition columns → Streams NOT supported
- Without partitions → Insert-only streams supported

---

## Step 8: Escalation - Event Logs

Enable logging:
```sql
ALTER ICEBERG TABLE <TABLE_NAME> SET LOG_LEVEL = DEBUG;
```

Query events:
```sql
SELECT timestamp, parse_json(value):snapshot_state AS state,
       parse_json(value):error_message AS error
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.table.name" = '<TABLE_NAME>'
  AND record:"name" = 'iceberg_auto_refresh_snapshot_lifecycle'
ORDER BY timestamp DESC LIMIT 20;
```

**Common errors:**
- "Unable to read Delta log" → Check `_delta_log` access
- "Unsupported Delta feature" → See Step 7
- "Schema mismatch" → Delta schema evolved incompatibly

---

## Step 9: Catalog Integration Check

```sql
DESCRIBE CATALOG INTEGRATION <catalog_name>;
```

Verify:
- `TABLE_FORMAT = DELTA`
- `ENABLED = TRUE`
- `REFRESH_INTERVAL_SECONDS` is set

Fix if needed:
```sql
ALTER CATALOG INTEGRATION <catalog_name> SET REFRESH_INTERVAL_SECONDS = 30;
```

Return to Step 2 after fixes.

---

## Limitations Summary

- Supports Delta reader version 2 (Delta Lake 2.2.0)
- Streams NOT supported for partitioned tables
- NOT supported in dynamic tables (pre-2024_04)
- Cannot use AWS Glue Data Catalog

---

## Stopping Points

- ✋ Step 1: Confirm table name
- ✋ Step 3C: Approval before recovery
- ✋ Step 3E: Approval before manual refresh
- ✋ Step 4: Approval before backlog clear
- ✋ Step 8: Confirm event table name

## Output

- Diagnosed Delta Direct auto-refresh issue
- Applied fix or escalation path
