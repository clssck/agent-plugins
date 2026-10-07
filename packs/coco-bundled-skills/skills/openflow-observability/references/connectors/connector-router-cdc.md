---
name: openflow-observability-connector-router-cdc
description: CDC connector diagnostics entry point, routing table, and initial triage query.
---

# CDC Connector Router

Entry point for CDC connector troubleshooting. Start here to route the investigation after the required CDC startup bundle is loaded. Unless direct signal routing applies, run the CDC error log scan first. Always pair the investigation with a CDC table-state check before concluding that a connector is healthy.

## Scope

- CDC connector routing by type
- CDC error log entry point query
- Cross-references to shared CDC diagnostics and per-database guidance

**Not covered:**
- Generic non-CDC processor failures -> **Load** `references/connectors/connector-router-non-cdc.md`
- Network connectivity issues -> **Load** `references/troubleshoot-network.md`
- Runtime-level issues (OOM, crashes) -> **Load** `references/troubleshoot-runtime.md`
- Deployment-level failures (DPS down, deployment not reporting) -> If BYOC with OAuth 403 / network signals, **Load** `references/troubleshoot-network.md`. In the customer-facing diagnosis, include both Snowflake account network policy allowlist checks and BYOC egress-path checks because the event logs usually prove a control-plane connectivity failure but do not prove which side is blocking it. Otherwise Snowflake-internal issue, escalate to Snowflake support

**Constraint:** All diagnostics are SQL-only via Snowsight. Use `{event_table}` for all event table queries.

---

## CDC Table State Reminder

Every CDC investigation must still run **CDC Table Replication State** from `references/core-queries-resource.md`. It is always required: fire it in the [Discovery Sequence](../../SKILL.md#discovery-sequence-high-level-troubleshoot) primary parallel batch alongside Recent Error Logs, not as a follow-up after the CDC Error Log Scan. Direct-signal routing below can skip the CDC Error Log Scan, but CDC Table Replication State still runs on every CDC investigation. In shared runtimes, only act on rows that tie back to the reported connector. Any FAILED-table recovery must use [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) from `connector-shared-cdc.md`.

---

## Routing Table

Once the CDC startup bundle is loaded, route to the per-connector file:

| connector_type | Route To |
| --- | --- |
| `postgresql` | `references/connectors/postgresql.md` |
| `mysql` | `references/connectors/mysql.md` |
| `sql_server` | `references/connectors/sql-server.md` |
| `oracle (Limited Access)` | `references/connectors/oracle.md` |
| `mongodb` | `references/connectors/mongodb.md` |
| `google_bigquery` | `references/connectors/google-bigquery.md` |
| Unknown or unlisted CDC connector | `references/connectors/connector-shared-cdc.md` as the starting point. Note to the customer that connector-specific guidance may be limited. |

The connector-specific file is already loaded as part of the startup bundle. Use it for source prerequisites, connector-specific failures, and recovery guidance.

---

## Error Signal Routing

> Direct signal matches let you skip the CDC Error Log Scan. They do not bypass the CDC startup bundle. They also do not bypass the **CDC Table Replication State** check -- fire it in the primary parallel batch regardless of which signal matches.

Before running the full CDC entry point, check if the error matches a known signal that routes directly to a specific diagnostic section.

| Error Signal | Route To |
| --- | --- |
| `ClassNotFoundException` for JDBC driver class | [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) |
| `Failed to invoke @OnEnabled` on `DBCPConnectionPool` | [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) |
| `JDBC driver class...not found` | [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) |
| `PutSnowpipeStreaming` / `PublishSnowpipeStreaming` / `PublishChangeDataSnowpipeStreaming` auth/role/warehouse errors, `No active warehouse selected`, `SnowflakeConnectionService` validation failures | [Destination Configuration Errors](connector-shared-generic.md#destination-configuration-errors) |
| Destination-side `SQL compilation error`, `does not exist or not authorized`, or `schema does not exist` | [Destination SQL Errors](connector-shared-generic.md#destination-sql-errors) |
| FlowFiles routed to `invalid` on `PublishSnowpipeStreaming` / `PublishChangeDataSnowpipeStreaming`, `invalid rows`, `partial transmission` | [Row Rejection (Snowpipe Streaming v2)](connector-shared-generic.md#row-rejection-snowpipe-streaming-v2) |
| `object already exists` (Snowflake destination) | [Destination SQL Errors](connector-shared-generic.md#destination-sql-errors) -- may also indicate a table needs restart via [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) |
| `Failed to open a channel` or `Channel is invalidated` | [Snowpipe Streaming Channel Invalidation](connector-shared-generic.md#snowpipe-streaming-channel-invalidation) |
| `ExecuteSQL` + `SYSTEM$STREAM_HAS_DATA` + stale / purged / invalid stream name / does not exist | [Stream Check Failures](connector-shared-cdc.md#stream-check-failures) |
| `CaptureChange*` + `Failed to process stream` | [Stream Check Failures](connector-shared-cdc.md#stream-check-failures) |
| `Login failed`, `password authentication failed`, or `ORA-01017` | Load the routed per-database connector file first for source authentication guidance. If `connector_type` is still unknown, start with `references/connectors/connector-shared-cdc.md` and identify the database from the logger or error text. |
| `Unable to connect to binlog` or `Could not find first log file name` | `references/connectors/mysql.md` -- Binlog connectivity/configuration |
| `Host is blocked` (MySQL `max_connect_errors`) | `references/connectors/mysql.md` -- source connection issue |
| `Access denied` (MySQL) | `references/connectors/mysql.md` -- source authentication |
| `ORA-17002` or `IO Error` (Oracle JDBC) | `references/connectors/oracle.md` and `references/troubleshoot-network.md` -- network/connectivity |
| `ORA-01284` (Oracle supplemental logging) | `references/connectors/oracle.md` -- supplemental logging configuration |
| `ORA-01031` (insufficient privileges, Oracle) | `references/connectors/oracle.md` -- privilege/grant issue |
| `wal_level` or `InvalidSourceDbConfig` (PostgreSQL) | `references/connectors/postgresql.md` -- WAL configuration |
| `replica identity` (PostgreSQL) | `references/connectors/postgresql.md` -- replica identity not set |
| `EncryptionException` or `Decryption error` | `references/troubleshoot-runtime.md` -- runtime encryption issue |
| `Flow version.*does not exist` or flow registry version mismatch | Escalate to Snowflake support -- flow registry state corruption |
| `PLS-00201: DBMS_XSTREAM_AUTH_IVK` | [PLS-00201](oracle.md#pls-00201-dbms_xstream_auth_ivk) -- omit `container => 'ALL'` on non-CDB |
| `ORA-26696: no XStream data dictionary` | [ORA-26696](oracle.md#ora-26696-no-xstream-data-dictionary) -- known Oracle bug, escalate to Oracle |

If the error signal matches one of these patterns, **Load** the referenced file and section directly instead of running the CDC Error Log Scan. Signal routing skips the entry-point query, not the CDC startup bundle.

---

## CDC Error Log Scan

Run this query first to surface CDC-specific errors. It filters for the logger families relevant to CDC connectors, plus `ExecuteSQL` stream check failures.

**Always use this exact query. Do not write an ad-hoc alternative.** The query handles schema variants via COALESCE; an ad-hoc query filtering only `record_attributes` fields will miss logs stored in parsed `value`.

```sql
WITH openflow_parsed_logs AS (
  SELECT *, TRY_PARSE_JSON(value) AS parsed_log
  FROM {event_table}
  WHERE record_type = 'LOG'
    AND resource_attributes:"k8s.container.name"::STRING NOT ILIKE '%-gateway'
    AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
    AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
    AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
)
SELECT
  timestamp,
  COALESCE(record_attributes:"LoggerName"::STRING, parsed_log:"loggerName"::STRING) AS logger,
  COALESCE(record_attributes:"severity_text"::STRING, record_attributes:"LogLevel"::STRING, parsed_log:"level"::STRING) AS log_level,
  COALESCE(parsed_log:"throwable":"message"::STRING, parsed_log:"message"::STRING) AS error_message,
  COALESCE(parsed_log:"formattedMessage"::STRING, parsed_log:"message"::STRING, LEFT(value, 500)) AS message
FROM openflow_parsed_logs
WHERE (
    -- WARN/ERROR from CDC loggers
    (COALESCE(record_attributes:"severity_text"::STRING, record_attributes:"LogLevel"::STRING, parsed_log:"level"::STRING, '') IN ('WARN', 'ERROR')
     AND (
       COALESCE(record_attributes:"LoggerName"::STRING, parsed_log:"loggerName"::STRING, '') ILIKE 'com.snowflake.openflow.runtime.processors.database.%'
       OR COALESCE(record_attributes:"LoggerName"::STRING, parsed_log:"loggerName"::STRING, '') ILIKE 'net.snowflake.%'
       OR (
         COALESCE(record_attributes:"LoggerName"::STRING, parsed_log:"loggerName"::STRING) = 'org.apache.nifi.processors.standard.ExecuteSQL'
         AND (
           value ILIKE '%STREAM_HAS_DATA%'
           OR value ILIKE '%has become stale%'
           OR value ILIKE '%has been purged%'
           OR value ILIKE '%valid stream name%'
         )
       )
     ))
    -- INFO from StandardTableStateService (logs the actual FAILED reason at INFO level)
    OR (COALESCE(record_attributes:"LoggerName"::STRING, parsed_log:"loggerName"::STRING, '') ILIKE '%StandardTableStateService%'
        AND value ILIKE '%FAILED%')
  )
ORDER BY timestamp DESC
LIMIT 100;
```

**Interpretation:**
- `com.snowflake.openflow.runtime.processors.database.*` -> connector processor errors (table failures, schema issues)
- `net.snowflake.*` -> Snowpipe Streaming or other general Snowflake errors (destination write failures)
- `StandardTableStateService` -> table state transitions including FAILED reason (logged at INFO level, captured here because it contains the actual failure cause that ERROR-level logs may not include)
- `org.apache.nifi.processors.standard.ExecuteSQL` + `SYSTEM$STREAM_HAS_DATA` -> Snowflake stream state checks used by CDC connectors

Use the error messages to branch: **Load** `references/connectors/connector-shared-cdc.md` for the shared CDC decision tree, then load the per-database file from the routing table if the source type is known.

**If zero results:** First run **Generic Raw Log Fallback** from `references/core-queries.md` to catch logs that only exist in raw `value` (the **Namespace + Shape Probe** already tells you if the table is in `raw_text` mode). Then run **Event Time Bounds Check** before expanding `{hours_back}` to 6, then 24. If still empty, verify the event table is configured (run Deployment Info from `references/core-queries-resource.md`). If the event table is set, the connector may not be generating error logs yet, or the issue may have aged out of the current time window.

---

## CDC Table State Check

After the CDC Error Log Scan, run **CDC Table Replication State** from `references/core-queries-resource.md` to get a per-table view of replication state. This surfaces FAILED tables proactively and shows which tables are in snapshot vs incremental replication.

> If the scan reveals ANY table tied to the reported connector in FAILED state, use [Restart Table Replication](connector-shared-cdc.md#restart-table-replication). Do not improvise or summarize the restart procedure from memory.

**If CDC Table Replication State returns zero rows:** Do **not** assume no tables are failed. State-transition logs may have aged out of the event-table window. Tell the customer to verify current state in the Openflow UI: right-click connector canvas -> Controller Services -> `Table State Store` -> **View State**. If the customer cannot access the Table State Store UI and event-table state data has aged out, treat table state as unknown and escalate with the available diagnostic evidence.

