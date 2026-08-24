---
name: dt-alerting
description: "Set up monitoring and alerting for dynamic table refreshes using event tables. Use when: monitoring DT health, alerting on refresh failures, tracking upstream failures. Triggers: DT alerts, dynamic table monitoring, refresh failures, event table for DTs."
parent_skill: dynamic-tables
---

# Dynamic Table Alerting with Event Tables

Expert guidance to set up monitoring and alerting for dynamic table refresh operations using Snowflake event tables.

## When to Load

Main skill routes here when user wants to:
- Set up alerts for dynamic table refresh failures
- Configure event table monitoring for DT pipelines
- Get notified when DTs fail or have upstream failures
- Build observability for data pipelines

---

## Workflow

## Key Concepts

| Concept | Description |
|---------|-------------|
| **Event Table** | System table that captures telemetry events (logs, traces) from Snowflake objects |
| **LOG_LEVEL** | Parameter controlling which events are captured: ERROR, WARN, INFO |
| **Alert on New Data** | Alert type that triggers when new rows matching a condition are inserted |
| **Refresh States** | `FAILED` (DT error), `UPSTREAM_FAILURE` (upstream DT failed), `SUCCEEDED` |

### Step 1: Configure Event Logging

**Goal:** Enable refresh event capture for dynamic tables

**Log Levels:**
| Level | Events Captured |
|-------|-----------------|
| `ERROR` | Refresh failures only |
| `WARN` | Refresh failures + upstream failures |
| `INFO` | All refresh events (success + failures) |

**Actions:**

1. **Set LOG_LEVEL** at appropriate scope:

   ```sql
   -- For a specific dynamic table (recommended - most targeted)
   ALTER DYNAMIC TABLE my_dt SET LOG_LEVEL = WARN;
   
   -- For all objects in a schema (affects DTs, UDFs, procedures, tasks)
   ALTER SCHEMA my_schema SET LOG_LEVEL = WARN;
   
   -- For all objects in a database (affects DTs, UDFs, procedures, tasks)
   ALTER DATABASE my_db SET LOG_LEVEL = WARN;
   
   -- Account-wide (affects ALL objects - use with caution)
   ALTER ACCOUNT SET LOG_LEVEL = WARN;
   ```

   > ⚠️ **Note:** Setting LOG_LEVEL at schema/database/account level affects **all** object types that support logging (UDFs, stored procedures, tasks, DTs), not just dynamic tables. For DT-only logging, set LOG_LEVEL on individual dynamic tables.

2. **Verify** the setting:
   ```sql
   SHOW PARAMETERS LIKE 'LOG_LEVEL' IN TABLE my_db.my_schema.my_dt;
   ```

### Step 2: Set Up Event Table

**Goal:** Ensure events are being captured

**First, check your account's event table setting:**
```sql
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
```

> ⚠️ **Important:** Many accounts use a custom event table instead of the default `SNOWFLAKE.TELEMETRY.EVENTS`. If a custom table is set, use that table name in your queries. You may also need SELECT privileges on that table.

**Options:**

1. **Default event table** (if no custom table is configured):
   ```sql
   -- Use the built-in telemetry table
   SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS 
   WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
   LIMIT 10;
   ```

2. **Custom event table** (for isolation, retention control, or when you lack access to the account event table):
   ```sql
   -- Create custom event table
   CREATE EVENT TABLE my_db.my_schema.dt_events;
   
   -- Associate with database (requires ALTER DATABASE privilege)
   ALTER DATABASE my_db SET EVENT_TABLE = my_db.my_schema.dt_events;
   ```
   
   > ⚠️ **Important:** The `EVENT_TABLE` parameter can only be set at **Account** or **Database** level - NOT at schema or object level. You need appropriate privileges (typically OWNERSHIP or MODIFY on the database, or ACCOUNTADMIN for account-level) to associate a custom event table.

### Step 3: Query Refresh Events

**Goal:** Understand event structure and test queries

**Query failed refreshes:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    resource_attributes:"snow.database.name"::VARCHAR AS database_name,
    resource_attributes:"snow.schema.name"::VARCHAR AS schema_name,
    resource_attributes:"snow.query.id"::VARCHAR AS query_id,
    value:message::VARCHAR AS error_message
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND value:state = 'FAILED'
ORDER BY timestamp DESC;
```

**Query upstream failures:**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    value:state::VARCHAR AS state
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND value:state = 'UPSTREAM_FAILURE'
ORDER BY timestamp DESC;
```

**Query all refresh events (requires INFO level):**
```sql
SELECT 
    timestamp,
    resource_attributes:"snow.executable.name"::VARCHAR AS dt_name,
    value:state::VARCHAR AS state,
    record:"severity_text"::VARCHAR AS severity
FROM SNOWFLAKE.TELEMETRY.EVENTS
WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
  AND record:"name" = 'refresh.status'
ORDER BY timestamp DESC;
```

### Step 4: Create Alert

**Goal:** Set up automated alerting for refresh failures

**Prerequisites:**
- Role with privileges to query the event table
- Notification integration (email, Slack webhook, etc.)
- **For Alert on New Data:** Change tracking must be enabled on the event table (`ALTER TABLE ... SET CHANGE_TRACKING = TRUE`). This requires MODIFY privilege on the table. If you lack this privilege, use a **Scheduled Alert** instead.

**Create alert for failures in a database (Alert on New Data):**

> ℹ️ **Note:** This is an "Alert on New Data" - no SCHEDULE parameter. It triggers only when new rows are inserted and automatically evaluates only the new rows.

```sql
CREATE OR REPLACE ALERT dt_refresh_failure_alert
  WAREHOUSE = my_wh
  IF (EXISTS (
    SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS
    WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
      AND resource_attributes:"snow.database.name" = 'MY_DB'
      AND record:"name" = 'refresh.status'
      AND record:"severity_text" = 'ERROR'
      AND value:state = 'FAILED'
  ))
  THEN
    BEGIN
      LET failed_dts VARCHAR;
      SELECT ARRAY_TO_STRING(ARRAY_AGG(dt_name), ', ') INTO :failed_dts
      FROM (
        SELECT resource_attributes:"snow.executable.name"::VARCHAR AS dt_name
        FROM TABLE(RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()))
        LIMIT 10
      );
      
      CALL SYSTEM$SEND_EMAIL(
        'my_email_integration',
        'alerts@company.com',
        'Dynamic Table Refresh Failed',
        'The following dynamic tables failed to refresh: ' || :failed_dts
      );
    END;
```

**Alternative: Scheduled Alert (when change tracking cannot be enabled):**

> ℹ️ **Note:** Use this approach if you lack MODIFY privilege on the event table. The SCHEDULE parameter makes this a polling-based alert. You MUST include a timestamp filter to avoid re-alerting on historical failures.

```sql
CREATE OR REPLACE ALERT dt_refresh_failure_alert
  WAREHOUSE = my_wh
  SCHEDULE = '5 MINUTE'
  IF (EXISTS (
    SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS
    WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
      AND resource_attributes:"snow.database.name" = 'MY_DB'
      AND record:"name" = 'refresh.status'
      AND record:"severity_text" = 'ERROR'
      AND value:state = 'FAILED'
      AND timestamp > DATEADD('minute', -5, CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP()))
  ))
  THEN
    BEGIN
      LET failed_dts VARCHAR;
      SELECT ARRAY_TO_STRING(ARRAY_AGG(dt_name), ', ') INTO :failed_dts
      FROM (
        SELECT resource_attributes:"snow.executable.name"::VARCHAR AS dt_name
        FROM TABLE(RESULT_SCAN(SNOWFLAKE.ALERT.GET_CONDITION_QUERY_UUID()))
        LIMIT 10
      );
      
      CALL SYSTEM$SEND_EMAIL(
        'my_email_integration',
        'alerts@company.com',
        'Dynamic Table Refresh Failed',
        'The following dynamic tables failed to refresh: ' || :failed_dts
      );
    END;
```

**Create alert for upstream failures:**
```sql
CREATE OR REPLACE ALERT dt_upstream_failure_alert
  WAREHOUSE = my_wh
  IF (EXISTS (
    SELECT * FROM SNOWFLAKE.TELEMETRY.EVENTS
    WHERE resource_attributes:"snow.executable.type" = 'DYNAMIC_TABLE'
      AND resource_attributes:"snow.database.name" = 'MY_DB'
      AND value:state = 'UPSTREAM_FAILURE'
  ))
  THEN
    CALL SYSTEM$SEND_SNOWFLAKE_NOTIFICATION(
      SNOWFLAKE.NOTIFICATION.TEXT_PLAIN('Upstream DT failure detected'),
      '{"my_slack_webhook": {}}'
    );
```

**Resume the alert:**
```sql
ALTER ALERT dt_refresh_failure_alert RESUME;
```

### Step 5: Verify and Test

**Goal:** Confirm alerting works

**Actions:**

1. **Check alert status:**
   ```sql
   SHOW ALERTS LIKE 'dt_%';
   ```

2. **View alert history:**
   ```sql
   SELECT * FROM TABLE(INFORMATION_SCHEMA.ALERT_HISTORY())
   WHERE name = 'DT_REFRESH_FAILURE_ALERT'
   ORDER BY scheduled_time DESC
   LIMIT 10;
   ```

3. **Test by forcing a failure** (in non-prod):
   ```sql
   -- Drop a column used by the DT to trigger a failure
   -- Or reference a non-existent object
   ```

## Event Table Schema Reference

Key columns for DT events in `SNOWFLAKE.TELEMETRY.EVENTS`:

| Column | Path | Description |
|--------|------|-------------|
| `timestamp` | - | When the event occurred |
| `resource_attributes` | `:"snow.executable.type"` | `'DYNAMIC_TABLE'` for DT events |
| `resource_attributes` | `:"snow.executable.name"` | Dynamic table name |
| `resource_attributes` | `:"snow.database.name"` | Database name |
| `resource_attributes` | `:"snow.schema.name"` | Schema name |
| `resource_attributes` | `:"snow.query.id"` | Query ID of the refresh |
| `record` | `:"severity_text"` | `ERROR`, `WARN`, or `INFO` |
| `record` | `:"name"` | `'refresh.status'` for refresh events |
| `value` | `:state` | `FAILED`, `UPSTREAM_FAILURE`, `SUCCEEDED` |
| `value` | `:message` | Error message (for failures) |

## Alternative: DYNAMIC_TABLE_REFRESH_HISTORY (Not Recommended)

> ⚠️ **Recommendation:** Always prefer **Event Table + Alert on New Data** for DT alerting. Event table alerting is significantly more cost-effective than polling `INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY`. Only use REFRESH_HISTORY if:
> - The user explicitly requests it
> - You need data not available in event tables (e.g., refresh duration, bytes added)
>
> For detailed guidance on event table alerting, see: https://docs.snowflake.com/en/user-guide/dynamic-tables-monitor-event-table-alerts

If event table alerting is not feasible, use the information schema function as a fallback:

```sql
CREATE OR REPLACE ALERT dt_failure_alert_simple
  WAREHOUSE = my_wh
  SCHEDULE = '5 MINUTE'
  IF (EXISTS (
    SELECT 1 FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
    WHERE name = 'MY_DT'
      AND state = 'FAILED'
      AND refresh_end_time > DATEADD('minute', -5, CURRENT_TIMESTAMP())
  ))
  THEN CALL SYSTEM$SEND_EMAIL(...);
```

---

## Output

- LOG_LEVEL configured for target DTs
- Event table queries for monitoring
- Alerts on new data for automated notifications

## Troubleshooting

| Issue | Solution |
|-------|----------|
| No events in event table | Verify LOG_LEVEL is set: `SHOW PARAMETERS LIKE 'LOG_LEVEL' IN TABLE <db.schema.dt_name>;` |
| Alert not triggering | Check alert is resumed: `SHOW ALERTS;` and verify condition query returns rows. For scheduled alerts, ensure timestamp comparison uses UTC: `CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())` |
| Missing columns in query | Ensure correct JSON path syntax with double quotes: `resource_attributes:"snow.executable.type"` |
| Permission denied on event table | Grant SELECT on `SNOWFLAKE.TELEMETRY.EVENTS` or use EVENTS_VIEW |

## Cost Considerations

- Event logging incurs storage costs for captured events
- Use targeted LOG_LEVEL (per-DT or per-schema) rather than account-wide to minimize volume
- Consider retention policies on custom event tables
