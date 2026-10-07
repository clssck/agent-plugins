---
name: auto-refresh-monitoring
description: "Set up monitoring and alerts for Iceberg/Delta Direct auto-refresh. Sub-skill of auto-refresh."
parent_skill: auto-refresh
---

# Auto-Refresh Monitoring & Alerting

Set up proactive monitoring for Iceberg and Delta Direct auto-refresh.

[← Back to main skill](SKILL.md)

---

## Step 1: Check Event Table

```sql
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
```

| Result | Action |
|--------|--------|
| Event table configured | Note name → Step 2 |
| Empty/not configured | Step 1B |
| Permission denied | Ask user for event table name |

### Step 1B: Create Event Table

**⚠️ MANDATORY CHECKPOINT**: Ask user approval before creating objects.

```sql
CREATE DATABASE IF NOT EXISTS <DATABASE>;
CREATE SCHEMA IF NOT EXISTS <DATABASE>.<SCHEMA>;
CREATE EVENT TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.ACCOUNT_EVENTS;
ALTER ACCOUNT SET EVENT_TABLE = <DATABASE>.<SCHEMA>.ACCOUNT_EVENTS;
```

---

## Step 2: Verify Logging

Ask: **What scope to monitor?** (table/schema/database)

```sql
SHOW PARAMETERS LIKE 'LOG_LEVEL' IN TABLE <TABLE_NAME>;
```

| Result | Action |
|--------|--------|
| DEBUG/WARN/ERROR | Step 2B |
| Not set | Enable logging → Step 2A |

### Step 2A: Enable Logging

| Level | Use Case |
|-------|----------|
| DEBUG | Full visibility (higher cost) |
| WARN | Self-resolving issues |
| ERROR | Critical failures only |

```sql
ALTER ICEBERG TABLE <TABLE_NAME> SET LOG_LEVEL = <LEVEL>;
```

### Step 2B: Verify Events Captured

```sql
SELECT COUNT(*) FROM <EVENT_TABLE>
WHERE record:"name" = 'iceberg_auto_refresh_snapshot_lifecycle'
  AND timestamp > DATEADD(hour, -1, CURRENT_TIMESTAMP());
```

If 0 → Wait 5 minutes, re-check.

---

## Step 3: Choose Monitoring Type

| Type | Go to |
|------|-------|
| Failure alerts | Step 4 |
| Staleness alerts | Step 5 |
| Latency monitoring | Step 6 |
| Cost monitoring | Step 7 |
| Health check query | Step 8 |

---

## Step 4: Failure Alerts

Ask: **Warehouse, email, check interval (default 5 min)?**

**⚠️ MANDATORY CHECKPOINT**: Confirm before creating view and alert.

```sql
CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.ICEBERG_REFRESH_FAILURES AS
SELECT timestamp,
    resource_attributes:"snow.database.name"::STRING AS database_name,
    resource_attributes:"snow.schema.name"::STRING AS schema_name,
    resource_attributes:"snow.table.name"::STRING AS table_name,
    parse_json(value):error_message::STRING AS error_message
FROM <EVENT_TABLE>
WHERE record:"name" = 'iceberg_auto_refresh_snapshot_lifecycle'
  AND (record:"severity_text" = 'ERROR' 
       OR parse_json(value):snapshot_state::STRING = 'error');
```

```sql
CREATE OR REPLACE ALERT <DATABASE>.<SCHEMA>.ICEBERG_REFRESH_FAILURE_ALERT
  WAREHOUSE = <WAREHOUSE>
  SCHEDULE = '<INTERVAL> MINUTE'
  IF (EXISTS (
    SELECT 1 FROM <DATABASE>.<SCHEMA>.ICEBERG_REFRESH_FAILURES
    WHERE timestamp > DATEADD(minute, -<INTERVAL>, CURRENT_TIMESTAMP())
  ))
  THEN CALL SYSTEM$SEND_EMAIL('iceberg_alerts', '<EMAIL>',
    'Iceberg Auto-Refresh Failure', 'One or more tables failed auto-refresh.');

ALTER ALERT <DATABASE>.<SCHEMA>.ICEBERG_REFRESH_FAILURE_ALERT RESUME;
```

→ Step 9

---

## Step 5: Staleness Alerts

Ask: **Staleness threshold (minutes), warehouse, email?**

**⚠️ MANDATORY CHECKPOINT**: Confirm before creating objects.

```sql
CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.ICEBERG_STALE_TABLES AS
WITH last_refresh AS (
    SELECT resource_attributes:"snow.table.name"::STRING AS table_name,
           MAX(timestamp) AS last_success
    FROM <EVENT_TABLE>
    WHERE record:"name" = 'iceberg_auto_refresh_snapshot_lifecycle'
      AND parse_json(value):snapshot_state::STRING = 'completed'
    GROUP BY 1
)
SELECT table_name, last_success,
       DATEDIFF(minute, last_success, CURRENT_TIMESTAMP()) AS minutes_since_refresh
FROM last_refresh;
```

```sql
CREATE OR REPLACE ALERT <DATABASE>.<SCHEMA>.ICEBERG_STALE_TABLE_ALERT
  WAREHOUSE = <WAREHOUSE>
  SCHEDULE = '15 MINUTE'
  IF (EXISTS (
    SELECT 1 FROM <DATABASE>.<SCHEMA>.ICEBERG_STALE_TABLES
    WHERE minutes_since_refresh > <THRESHOLD>
  ))
  THEN CALL SYSTEM$SEND_EMAIL('iceberg_alerts', '<EMAIL>',
    'Stale Iceberg Tables', 'Tables not refreshed in <THRESHOLD> minutes.');

ALTER ALERT <DATABASE>.<SCHEMA>.ICEBERG_STALE_TABLE_ALERT RESUME;
```

→ Step 9

---

## Step 6: Latency Monitoring

**⚠️ CHECKPOINT**: Confirm before creating view.

```sql
CREATE OR REPLACE VIEW <DATABASE>.<SCHEMA>.ICEBERG_REFRESH_LATENCY AS
WITH events AS (
    SELECT resource_attributes:"snow.table.name"::STRING AS table_name,
           record_attributes:"snow.snapshot.id"::STRING AS snapshot_id,
           parse_json(value):snapshot_state::STRING AS state,
           timestamp
    FROM <EVENT_TABLE>
    WHERE record:"name" = 'iceberg_auto_refresh_snapshot_lifecycle'
),
started AS (SELECT table_name, snapshot_id, timestamp AS start_time FROM events WHERE state = 'started'),
completed AS (SELECT table_name, snapshot_id, timestamp AS end_time FROM events WHERE state = 'completed')
SELECT s.table_name, s.snapshot_id, s.start_time, c.end_time,
       DATEDIFF(second, s.start_time, c.end_time) AS latency_seconds
FROM started s JOIN completed c ON s.table_name = c.table_name AND s.snapshot_id = c.snapshot_id;
```

Review:
```sql
SELECT table_name, COUNT(*) AS refreshes,
       ROUND(AVG(latency_seconds), 2) AS avg_latency,
       MAX(latency_seconds) AS max_latency
FROM <DATABASE>.<SCHEMA>.ICEBERG_REFRESH_LATENCY
WHERE start_time > DATEADD(day, -7, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY avg_latency DESC;
```

Optional: Create high latency alert similar to Step 4/5.

→ Step 9

---

## Step 7: Cost Monitoring

```sql
SELECT DATE_TRUNC('day', start_time) AS day,
       COALESCE(pipe_name, 'Delta-based') AS source,
       ROUND(SUM(credits_used), 4) AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.PIPE_USAGE_HISTORY
WHERE start_time > DATEADD(day, -14, CURRENT_TIMESTAMP())
GROUP BY 1, 2 ORDER BY day DESC;
```

**⚠️ CHECKPOINT**: Ask before creating cost view/alert.

Optional: Create cost spike alert (2x average triggers).

→ Step 9

---

## Step 8: Health Check Procedure

**⚠️ CHECKPOINT**: Confirm before creating procedure.

```sql
CREATE OR REPLACE PROCEDURE <DATABASE>.<SCHEMA>.CHECK_ICEBERG_HEALTH(
  DB_NAME     STRING,
  SCHEMA_NAME STRING
)
RETURNS VARIANT
LANGUAGE JAVASCRIPT
EXECUTE AS CALLER
AS
$$
  var results = [];

  // 1) Get list of Iceberg tables in the target db.schema
  var tablesStmt = snowflake.createStatement({
    sqlText: `SHOW ICEBERG TABLES IN ${DB_NAME}.${SCHEMA_NAME}`
  });
  var tablesRs = tablesStmt.execute();

  while (tablesRs.next()) {
    var dbName    = tablesRs.getColumnValue('database_name');
    var schema    = tablesRs.getColumnValue('schema_name');
    var table     = tablesRs.getColumnValue('name');
    var fullName  = dbName + '.' + schema + '.' + table;

    var row = {
      table_name: fullName,
      auto_refresh_enabled: null,
      execution_state: null,
      pending_snapshots: null,
      error: null
    };

    // 2) Call SYSTEM$AUTO_REFRESH_STATUS for each table
    try {
      var statusStmt = snowflake.createStatement({
        sqlText: `SELECT SYSTEM$AUTO_REFRESH_STATUS('${fullName}')`
      });
      var statusRs = statusStmt.execute();
      if (statusRs.next()) {
        var statusJson = JSON.parse(statusRs.getColumnValue(1));
        row.execution_state      = statusJson.executionState || null;
        row.pending_snapshots    = statusJson.pendingSnapshotCount || 0;
        row.auto_refresh_enabled = true;  // if status works, auto refresh is effectively on
      }
    } catch (err) {
      row.execution_state      = 'ERROR';
      row.pending_snapshots    = null;
      row.auto_refresh_enabled = null;
      row.error                = err.message;
    }

    results.push(row);
  }

  return results;
$$;
```

Test: `CALL <DATABASE>.<SCHEMA>.CHECK_ICEBERG_HEALTH('MY_DATABASE', 'MY_SCHEMA');`

→ Step 9

---

## Step 9: Complete

Ask: **Set up another monitoring type?**
- Yes → Return to Step 3
- No → Step 10

---

## Step 10: Summary

Present objects created:
- Event table (if created)
- Views created
- Alerts created
- Procedures created

**Manage alerts:**
```sql
SHOW ALERTS IN SCHEMA <DATABASE>.<SCHEMA>;
ALTER ALERT <NAME> SUSPEND;
ALTER ALERT <NAME> RESUME;
```

---

## Stopping Points

- ✋ Step 1B: Approval before creating event table
- ✋ Step 4-8: Approval before creating each view/alert/procedure
- ✋ Step 9: Confirm if more monitoring needed

## Output

- Event table configured
- Monitoring views/alerts/procedures created
- Summary of objects created
