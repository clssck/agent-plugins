---
name: openflow-observability-connector-sql-server
description: SQL Server connector troubleshooting and SPCS domain allowlist.
---

# SQL Server (Change Tracking)

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/setup)
- [Data mapping](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/data-mapping)
- [Incremental replication](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/incremental-replication)
- [Maintenance](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/maintenance)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
|--------|-------|
| `<customer-db-host>:<port>` | Customer-specific. Default port: 1433. |

## Parameters & Required Assets

The SQL Server connector uses three parameter contexts. Key parameters from the [official setup documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/setup):

### Source Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Database Hostname` | SQL Server host address | Required |
| `Database Port` | SQL Server port | Default: `1433` |
| `Database User` | Connection username | Required |
| `Database Password` | Connection password | Required |
| `SQLServer JDBC Driver` | JDBC driver JAR | **Must upload as Reference asset** (see below) |
| `Database SSL Connection` | Enable SSL | Optional; if enabled, upload root certificate as asset |
| `Database Root Certificate` | SSL root certificate | Required only when SSL is enabled |

### Destination Parameters

See [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters).

### Ingestion Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Included Databases` | Databases to replicate | Comma-separated list |
| `Included Table Names` | Tables to replicate | Format: `<database>.<schema>.<table>` |
| `Object Identifier Resolution` | Case sensitivity | `CASE_SENSITIVE` or `CASE_INSENSITIVE` |

### JDBC Driver Asset Upload

The SQL Server JDBC driver must be uploaded as a parameter context asset. See [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) for upload steps, diagnosis queries, and resolution.

### SSL Configuration

For SSL configuration, see [SSL Configuration (Database Connectors)](connector-shared-generic.md#ssl-configuration-database-connectors).

## Troubleshooting

### SQL Server Prerequisites

When the connector is failing or not replicating data, verify that the source database prerequisites are correctly configured. Guide the customer through these diagnostic checks.

Ask the customer to run the following verification queries on their SQL Server instance:

**1. Verify change tracking is enabled on the database:**
```sql
-- Run on the source SQL Server database
SELECT DB_NAME(database_id) AS database_name, is_auto_cleanup_on, retention_period, retention_period_units
FROM sys.change_tracking_databases;
```
If the database is not listed, change tracking needs to be enabled on the database with an appropriate retention period (minimum 2 days recommended). This is a customer DBA action.

**2. Verify change tracking is enabled on each replicated table:**
```sql
-- Run on the source SQL Server database
SELECT OBJECT_NAME(object_id) AS table_name, is_track_columns_updated_on
FROM sys.change_tracking_tables;
```
If a replicated table is missing from the results, change tracking must be enabled on that table. This is a customer DBA action.

**3. Verify SQL Server Agent is running** (for on-premise installations):
The SQL Server Agent manages the change tracking cleanup. If it is stopped, change tracking data accumulates and may cause performance issues. Ask the customer to verify its state:
```sql
-- Run on the source SQL Server database
EXEC xp_servicecontrol 'QueryState', 'SQLServerAgent';
```

**4. Verify user permissions:**
The connector user needs `SELECT` and `VIEW CHANGE TRACKING` on each replicated table. Ask the customer to check current permissions:
```sql
-- Run on the source SQL Server database
SELECT dp.name, p.permission_name, p.state_desc, OBJECT_NAME(p.major_id) AS object_name
FROM sys.database_permissions p
JOIN sys.database_principals dp ON p.grantee_principal_id = dp.principal_id
WHERE dp.name = '<connector_user>';
```
If required permissions are missing, the customer's DBA needs to grant `SELECT` and `VIEW CHANGE TRACKING` on each replicated table. If tables use User Defined Data Types (UDDT) owned by a different user, `VIEW DEFINITION` is also required -- without it, columns using UDDT are silently excluded from replication. This is a customer DBA action.

**5. Verify change retention is sufficient:**
The `CHANGE_RETENTION` value must be long enough that the connector can read changes before they are cleaned up. Check the current retention with the query in step 1. If the connector was paused or slow and tracked changes were lost, the retention period needs to be increased (minimum 2 days; the official setup example uses 5 days — choose a value that comfortably covers your maximum expected connector downtime). This is a customer DBA action.

If any of the above prerequisites are not met, describe the required configuration changes to the customer and make it clear that the fixes happen on the customer's SQL Server instance. **Do NOT suggest restarting or reconfiguring the Openflow connector itself for prerequisite issues.** If a table has already entered `FAILED`, the source fix alone is not enough -- after the SQL Server prerequisite is corrected, use the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure for each affected failed table. Do not summarize or improvise the restart steps. A connector restart adds no value when the root cause is a missing source prerequisite.

---

### Source Authentication Failures

**Pattern:** Errors such as `Login failed for user`, authentication failures from the SQL Server JDBC driver, or repeated connection attempts followed by `Administrative Yield`.

**Snowsight Checks:**


```sql
SELECT
  timestamp,
  COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING) AS logger,
  COALESCE(TRY_PARSE_JSON(value):"throwable":"message"::STRING, TRY_PARSE_JSON(value):"message"::STRING) AS error_message,
  COALESCE(TRY_PARSE_JSON(value):"formattedMessage"::STRING, TRY_PARSE_JSON(value):"message"::STRING, LEFT(value, 500)) AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND (
    value ILIKE '%Login failed for user%'
    OR value ILIKE '%Authentication failed%'
    OR value ILIKE '%Cannot open database requested by the login%'
    OR value ILIKE '%Administrative Yield%'
  )
ORDER BY timestamp DESC
LIMIT 100;
```

**Recommended Action:**
1. Verify the `Database User` and `Database Password` values in the connector's source parameters
2. Ask the customer DBA to confirm the login exists on the SQL Server instance and can access the configured database
3. If the login uses an auth mode outside the supported connector setup, reconfigure the connector to use the supported SQL authentication method from the public setup guide
4. Treat `Administrative Yield` as retry backoff after the authentication failure, not as the root cause

---

### SSL / TLS Configuration

**Pattern:** TLS-related errors on connection, including `SSL handshake failed`, `unexpected_message`, `No appropriate protocol`, `PKIX path building failed: unable to find valid certification path to requested target`, or connection failures that appear only when `Database SSL Connection` is enabled.

**Diagnostic query** (run in Snowsight to identify SSL/TLS errors):

```sql
SELECT
  timestamp,
  COALESCE(TRY_PARSE_JSON(value):"throwable":"message"::STRING, TRY_PARSE_JSON(value):"message"::STRING) AS error_message,
  COALESCE(TRY_PARSE_JSON(value):"formattedMessage"::STRING, TRY_PARSE_JSON(value):"message"::STRING, LEFT(value, 500)) AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND (
    value ILIKE '%SSL%'
    OR value ILIKE '%TLS%'
    OR value ILIKE '%certificate%'
    OR value ILIKE '%handshake%'
    OR value ILIKE '%PKIX%'
  )
ORDER BY timestamp DESC
LIMIT 50;
```

**Common causes and fixes:**

**1. Server certificate uses deprecated cryptographic algorithms:**
The connector uses Java 21, which rejects connections using deprecated algorithms including SHA-1 signature algorithms or RSA keys shorter than 2048 bits. This surfaces as `unexpected_message` or `No appropriate protocol` during the TLS handshake. The customer's DBA must replace the SQL Server SSL certificate with one using SHA-256 (or newer) and an RSA key of at least 2048 bits. Certificate replacement is a customer DBA action on the SQL Server host.

**2. Certificate chain validation fails (`trustServerCertificate=false`):**
When SSL is enabled and certificate validation is active, the connector must trust the SQL Server's CA certificate chain. Upload the SQL Server root CA certificate as the `Database Root Certificate` parameter context asset. This is the recommended approach for production use.

The key JDBC parameters for SSL behavior are:
- `encrypt=true` — enables TLS for the connection (set automatically when `Database SSL Connection` is enabled)
- `trustServerCertificate=true` — skips certificate validation; acceptable for dev/test only
- `trustServerCertificate=false` (default when encryption is enabled) — requires a valid, trusted CA chain via the `Database Root Certificate` asset

**3. Trust store reference via JDBC URL:**
If you need to reference a JKS trust store that is not handled by the `Database Root Certificate` asset parameter, upload the trust store as a named asset and reference it in the JDBC connection URL: `trustStore=<asset-path>&trustStorePassword=<password>`. Note that using `StandardSSLContextService` as an alternative may interfere with connector registry connectivity — prefer the `Database Root Certificate` parameter approach when available.

---

### Change Tracking Replication Lag

**Pattern:** No explicit errors, but data in Snowflake is significantly behind the source database.

**Snowsight Checks:** Check for connector processor errors or warnings that indicate the Change Tracking poller is falling behind:


```sql
SELECT
  timestamp,
  COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING) AS logger,
  COALESCE(record_attributes:"severity_text"::STRING, record_attributes:"LogLevel"::STRING, TRY_PARSE_JSON(value):"level"::STRING) AS log_level,
  COALESCE(TRY_PARSE_JSON(value):"formattedMessage"::STRING, TRY_PARSE_JSON(value):"message"::STRING, LEFT(value, 500)) AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING, '') ILIKE 'com.snowflake.openflow.runtime.processors.database.%'
  AND COALESCE(record_attributes:"severity_text"::STRING, record_attributes:"LogLevel"::STRING, TRY_PARSE_JSON(value):"level"::STRING) IN ('WARN', 'ERROR')
ORDER BY timestamp DESC
LIMIT 100;
```

**Note:** The SQL Server connector uses Change Tracking, not binlog/WAL replication. All connector-level diagnostics come from `com.snowflake.openflow.runtime.processors.database.*` loggers.

**Recommended Action:**
1. Check the Change Tracking retention period on the source database (use the diagnostic query from SQL Server Prerequisites step 1). If `CHANGE_RETENTION` is too short and the connector was paused or slow, tracked changes may have been cleaned up before the connector could read them. The retention period needs to be increased (minimum 2 days; the official setup example uses 5 days). This is a customer DBA action.
2. If tracked changes were lost (connector reports it cannot find changes for a version), first increase the retention period. If the table is in `FAILED`, surface the canonical FAILED phrasing in the diagnosis: the customer must run the [Restart Table Replication] procedure. After the retention fix, use the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure. Do not summarize or improvise the restart steps.
3. For large tables, make sure the customer understands the re-snapshot duration before proceeding.
4. Check resource utilization -- use CPU Utilization by Pod and Memory Utilization by Pod from `references/core-queries-resource.md`. If the runtime is resource-constrained, tell the customer that a larger runtime size may be required.

---

### Snowflake Stream Check Failures

**Pattern:** `ExecuteSQL` or `CaptureChangeSqlServer` errors mentioning `SYSTEM$STREAM_HAS_DATA`, a stale stream, `does not exist or not authorized`, `must be a valid stream name`, or `Failed to process stream`.

**Likely Cause:** This is usually a Snowflake-side CDC stream-state issue, not a SQL Server Change Tracking prerequisite issue.

**Recommended Action:** Load [Stream Check Failures](connector-shared-cdc.md#stream-check-failures) first. If the only SQL Server-side message is `Failed to process stream`, look for the paired `ExecuteSQL` stream-check error before treating it as a separate source problem.

---

### Change Tracking Version Invalidation

**Pattern:** Errors referencing an invalid or expired change tracking version, such as `The minimum valid version for table ... is ...`, or the connector repeatedly attempts to read a version that no longer exists in SQL Server's change tracking history. This typically follows a period when the connector was paused or lagged.

**Cause:** SQL Server change tracking maintains a minimum valid version per table (`CHANGE_TRACKING_MIN_VALID_VERSION`). When the connector is stopped or falls behind for longer than the `CHANGE_RETENTION` period, SQL Server automatically cleans up change tracking data for that window. The connector's saved version number falls below the minimum valid version, making it impossible to resume incremental replication from that position.

**Diagnosis (run on source SQL Server database):**

```sql
-- Check minimum valid version vs current version for all tracked tables
SELECT
    OBJECT_NAME(object_id) AS table_name,
    CHANGE_TRACKING_MIN_VALID_VERSION(object_id) AS min_valid_version,
    CHANGE_TRACKING_CURRENT_VERSION() AS current_version
FROM sys.change_tracking_tables;
```

Also check the retention configuration:

```sql
-- Check change tracking retention period on the source database
SELECT DB_NAME(database_id) AS database_name, retention_period, retention_period_units
FROM sys.change_tracking_databases;
```

If `min_valid_version` for any table is higher than the version the connector last read, the retention window has expired for that table's change history.

**Recommended Action:**
1. The customer DBA must increase the `CHANGE_RETENTION` period to prevent recurrence (minimum 2 days; the official setup example uses 5 days — pick a value that covers your maximum expected connector downtime):
```sql
-- Run on source SQL Server database (DBA action)
ALTER DATABASE <database_name>
SET CHANGE_TRACKING (CHANGE_RETENTION = 5 DAYS, AUTO_CLEANUP = ON);
```
2. After increasing retention, the connector cannot resume incremental replication from the expired position. Each affected table must go through [Restart Table Replication](connector-shared-cdc.md#restart-table-replication).
3. If multiple tables are simultaneously affected, treat this as a [Connector-Wide Recovery Case](connector-shared-cdc.md#connector-wide-recovery-cases) — fix retention first, then restart each affected table.
4. To prevent recurrence: ensure the runtime stays running and avoid pausing the connector for longer than the `CHANGE_RETENTION` window.

Do **not** attempt to manually reset the change tracking version, disable/re-enable change tracking on individual tables as a shortcut, or restart the entire connector. These actions do not restore the lost history and may introduce additional data gaps. The only reliable recovery is increasing retention and restarting the affected tables via the documented procedure.
