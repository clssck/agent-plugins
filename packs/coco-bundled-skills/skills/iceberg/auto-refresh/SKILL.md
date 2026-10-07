---
name: auto-refresh
description: "Debug auto-refresh issues for Iceberg and Delta Direct tables in Snowflake. Use when: auto-refresh stuck, stale data, refresh not working, iceberg table not syncing, delta direct issues. Triggers: auto-refresh, autorefresh, iceberg refresh, delta direct, catalog integration, stale data, refresh stuck."
---

# Auto-Refresh Debugging & Monitoring

Debug auto-refresh issues for Iceberg tables and Delta Direct tables in Snowflake.

## When to Use

- User reports Iceberg or Delta Direct table data is stale
- Auto-refresh status shows STOPPED or STALLED
- User wants to set up monitoring for auto-refresh
- Refresh interval tuning needed
- Cost investigation for auto-refresh

## Quick Routing

| Table Type | Action |
|------------|--------|
| Delta Direct (created from Delta Lake files) | **Load** `./delta-direct.md` |
| Standard Iceberg table - debug | Continue below |
| Monitoring/alerts setup | **Load** `./monitoring.md` |

---

# Iceberg Auto-Refresh Debugging

## Step 1: Validate Table

Ask: **What is the fully qualified Iceberg table name?** (e.g., `DATABASE.SCHEMA.TABLE_NAME`)

Store as `<TABLE_NAME>`.

```sql
SHOW ICEBERG TABLES LIKE '<table_part>' IN <DATABASE>.<SCHEMA>;
```

| Result | Action |
|--------|--------|
| `invalid = false` | Proceed to Step 2 |
| `invalid = true` | Table invalid - inform user |
| No rows | Check if regular table exists, return to Step 1 |

---

## Step 2: Check Auto-Refresh Status

```sql
SELECT SYSTEM$AUTO_REFRESH_STATUS('<TABLE_NAME>');
```

**Key fields:**
- `executionState`: RUNNING, STALLED, or STOPPED
- `pendingSnapshotCount`: Snapshots waiting to process
- `oldestSnapshotTime`: Compare to current time for staleness

| executionState | Go to |
|----------------|-------|
| RUNNING | Step 3A |
| STALLED | Step 3B |
| STOPPED | Step 3C |
| NULL/error | Step 3D |

---

## Step 3A: Status RUNNING

Ask: **What issue are you experiencing?**

| Issue | Go to |
|-------|-------|
| Data stale/not updating | Step 4 |
| Refresh too slow | Step 5 |
| High costs | Step 6 |
| Refresh stuck/hanging | Step 3E |

---

## Step 3B: Status STALLED

Snowflake is auto-recovering. Wait 5 minutes, then re-check status.

- Changed to RUNNING → Resolved
- Changed to STOPPED → Step 3C
- Still STALLED → Step 7

---

## Step 3C: Status STOPPED

**⚠️ MANDATORY CHECKPOINT**: Ask user approval before recovery procedure.

Recovery procedure:
1. `ALTER ICEBERG TABLE <TABLE_NAME> SET AUTO_REFRESH = FALSE;`
2. `ALTER ICEBERG TABLE <TABLE_NAME> REFRESH;`
3. `ALTER ICEBERG TABLE <TABLE_NAME> SET AUTO_REFRESH = TRUE;`
4. Verify: `SELECT SYSTEM$AUTO_REFRESH_STATUS('<TABLE_NAME>');`

If still not RUNNING → Step 7

---

## Step 3D: Status NULL

Check if auto-refresh enabled:
```sql
SHOW ICEBERG TABLES LIKE '<table_part>' IN <DATABASE>.<SCHEMA>;
```

- AUTO_REFRESH = FALSE → Enable it, return to Step 2
- AUTO_REFRESH = TRUE but NULL status → Step 8

---

## Step 3E: Refresh Stuck

Test manual refresh:
```sql
ALTER ICEBERG TABLE <TABLE_NAME> REFRESH;
```

| Result | Action |
|--------|--------|
| Manual succeeds | Reset pipe: toggle AUTO_REFRESH off/on |
| Manual fails | Share error - general refresh issue |

If still stuck after reset → Step 7

---

## Step 4: Data Staleness

Check refresh history:
```sql
SELECT * FROM TABLE(INFORMATION_SCHEMA.ICEBERG_TABLE_SNAPSHOT_REFRESH_HISTORY(
  TABLE_NAME => '<TABLE_NAME>'
)) ORDER BY REFRESH_START_TIME DESC LIMIT 10;
```

Check pending count:
```sql
SELECT PARSE_JSON(SYSTEM$AUTO_REFRESH_STATUS('<TABLE_NAME>')):pendingSnapshotCount::INT;
```

| pendingSnapshotCount | Action |
|---------------------|--------|
| 0 | Source may have no new data |
| 1-50 | Processing ongoing, wait |
| >50 | **⚠️ CHECKPOINT** - Offer manual refresh to clear backlog |

**Manual backlog clear:** Toggle AUTO_REFRESH off, REFRESH, toggle on.

---

## Step 5: Refresh Interval Tuning

Get catalog integration:
```sql
SHOW ICEBERG TABLES LIKE '<table_part>' IN <DATABASE>.<SCHEMA>;
DESCRIBE CATALOG INTEGRATION <catalog_name>;
```

Adjust:
```sql
ALTER CATALOG INTEGRATION <catalog_name> SET REFRESH_INTERVAL_SECONDS = <value>;
```

| Use Case | Interval |
|----------|----------|
| Real-time | 10-30s |
| Near real-time | 30-60s |
| Hourly reporting | 300-600s |

---

## Step 6: Cost Investigation

```sql
SELECT DATE_TRUNC('day', start_time) AS day,
       ROUND(SUM(credits_used), 4) AS total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.PIPE_USAGE_HISTORY
WHERE pipe_name ILIKE '%<table_part>%'
  AND start_time > DATEADD(day, -7, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY day DESC;
```

High costs → Consider increasing REFRESH_INTERVAL_SECONDS.

---

## Step 7: Escalation - Event Logs

Get event table:
```sql
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
```

Enable debug logging:
```sql
ALTER ICEBERG TABLE <TABLE_NAME> SET LOG_LEVEL = DEBUG;
```

Query events:
```sql
SELECT timestamp, parse_json(value):snapshot_state::STRING AS state,
       parse_json(value):error_message::STRING AS error
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.table.name"::STRING ILIKE '%<table_part>%'
  AND record:"name"::STRING = 'iceberg_auto_refresh_snapshot_lifecycle'
ORDER BY timestamp DESC LIMIT 20;
```

---

## Step 8: Catalog Integration Check

```sql
DESCRIBE CATALOG INTEGRATION <catalog_name>;
```

| Issue | Fix |
|-------|-----|
| ENABLED = FALSE | `ALTER CATALOG INTEGRATION ... SET ENABLED = TRUE;` |
| REFRESH_INTERVAL_SECONDS not set | `ALTER CATALOG INTEGRATION ... SET REFRESH_INTERVAL_SECONDS = 30;` |

Return to Step 2 after fixes.

---

## Stopping Points

- ✋ Step 1: Confirm table name before validation
- ✋ Step 3C: Approval before recovery procedure
- ✋ Step 4: Approval before manual backlog clear
- ✋ Step 7: Confirm event table name

## Output

- Diagnosed auto-refresh issue
- Applied fix or escalation path identified
- Optional: Monitoring setup via `./monitoring.md`
