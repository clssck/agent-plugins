---
name: openflow-observability-connector-oracle
description: Oracle connector troubleshooting and SPCS domain allowlist.
---

# Oracle CDC

> **Limited Access:** The Oracle CDC connector is a Limited Access feature and may not be available in all accounts. Contact your Snowflake account team for access.

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/about)
- [Setup tasks](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-tasks)
- [Commercial terms](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/manage-commercial-terms)
- [Data mapping](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/data-mapping)
- [Configure the connector](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-connector)
- [Set up Snowflake](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-snowflake)
- [Configure the Oracle database](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-oracledb)
- [Incremental replication](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/incremental-replication)Maintenance](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/maintenance) | [Troubleshoot](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/troubleshoot)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
|--------|-------|
| `<customer-db-host>:<port>` | Customer-specific. Default port: 1521. |

## Parameters & Required Assets

The Oracle connector uses three parameter contexts. Key parameters from the [official setup documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-connector):

### Prerequisites

> **ORGADMIN required:** To enable the Oracle connector, a user with the ORGADMIN role must accept the Oracle XStream licensing terms. This is a one-time step performed during connector installation.

> **One connector per runtime:** The Oracle connector requires exclusive use of a runtime. Do not install other connectors on the same runtime.

### Source Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Database Hostname` | Oracle server host | Required |
| `Database Port` | Oracle server port | Default: `1521` |
| `Database User` | Connection username | Must have XStream and flashback privileges |
| `Database Password` | Connection password | Required |
| `Oracle JDBC Driver` | JDBC driver JAR | **Must upload as Reference asset** (see below) |
| `XStream Outbound Server Name` | Name of XStream outbound server | Must match the server created on the source DB |
| `Database SSL Connection` | Enable SSL | Optional |
| `Database Root Certificate` | SSL root certificate | Required only when SSL is enabled |

### Destination Parameters

See [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters).

### Ingestion Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Included Table Names` | Tables to replicate | Format: `<database>.<schema>.<table>` (use GLOBAL_DB_NAME as database prefix) |
| `Object Identifier Resolution` | Case sensitivity | `CASE_SENSITIVE` or `CASE_INSENSITIVE` |

### JDBC Driver Asset Upload

The Oracle JDBC driver (`ojdbc8.jar` or `ojdbc11.jar`) must be uploaded as a parameter context asset. See [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) for upload steps, diagnosis queries, and resolution.

### Licensing & Enablement

The Oracle connector requires acceptance of XStream licensing terms:
1. A user with the **ORGADMIN** role must enable the connector in the Snowflake account
2. This involves accepting the Oracle XStream terms of use
3. After enablement, the connector appears in the Openflow connector catalog

Refer to [Configure the Openflow Connector for Oracle](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-connector) for the step-by-step enablement procedure.

## Troubleshooting

Oracle CDC uses XStream for change capture. Use the issue blocks below as the primary entry points for source-specific customer guidance; shared recovery and destination-side guidance stays in `connector-shared-cdc.md` and `connector-shared-generic.md`.

### XStream Outbound Server Stopped

Check capture process status:
```sql
-- Run on the source Oracle database
SELECT CLIENT_NAME, STATUS, ERROR_MESSAGE FROM ALL_CAPTURE;
```
Status should be `ENABLED`. If `DISABLED`, the XStream outbound server needs to be started on the source database. This is a customer DBA action.

### Redo Logs Deleted

If the logminer session shows `UNKNOWN` state or the capture is `WAITING FOR REDO`, required redo logs have been deleted.

**Diagnosis (run on source Oracle database):**
```sql
-- Check logminer session state
SELECT SESSION_STATE FROM V$LOGMNR_SESSION;
-- Expected: ACTIVE. UNKNOWN = archived logs deleted.

-- Check capture state
SELECT STATE FROM V$XSTREAM_CAPTURE;
-- Expected: CAPTURING CHANGES or WAITING FOR TRANSACTION.
-- WAITING FOR REDO: FILE NA, THREAD 1, SEQUENCE X = redo log deleted.
```

**Recommended Action:** The customer DBA must recreate the XStream outbound server after restoring the required redo-log availability. Restarting the connector or upgrading will not resolve this. Redo log loss invalidates the entire replication position, so **all tables** require restart, not just those that have individually entered FAILED state. Treat this as a [Connector-Wide Recovery Case](connector-shared-cdc.md#connector-wide-recovery-cases): after the Oracle-side fix, use the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure for every table in the connector. Do not summarize or improvise the restart steps. The customer should expect re-snapshot time/cost across all tables.

### XStream Rule Verification

When tables are not appearing in Snowflake despite the connector running, verify the XStream rules include the expected tables:
```sql
-- Run on the source Oracle database
SELECT STREAMS_NAME, SCHEMA_NAME, OBJECT_NAME, RULE_TYPE
FROM DBA_XSTREAM_RULES
WHERE STREAMS_NAME = '<xstream_outbound_server_name>';
-- Replace with the actual XStream outbound server name from the connector's Source Parameters
```

### SCN Bottleneck Diagnosis

When replication is slow or stalled, compare SCN positions across components to identify the bottleneck:
```sql
-- Run on the source Oracle database
SELECT
  c.CAPTURE_NAME,
  c.STATUS AS capture_status,
  c.CAPTURED_SCN,
  c.APPLIED_SCN,
  o.COMMITTED_POSITION AS outbound_scn,
  DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER() AS current_db_scn
FROM ALL_CAPTURE c
JOIN ALL_XSTREAM_OUTBOUND o ON c.CAPTURE_NAME = o.CAPTURE_NAME;
```

Large gaps between `CAPTURED_SCN` and `current_db_scn` indicate the capture process is falling behind. Large gaps between `CAPTURED_SCN` and `APPLIED_SCN` indicate the apply process is the bottleneck.

### Table FQN Format

The Included Table Names parameter requires `<database_name>.<schema_name>.<table_name>` format (note the database prefix). Verify the database name:
```sql
-- Run on the source Oracle database
SELECT property_value FROM database_properties WHERE property_name = 'GLOBAL_DB_NAME';
```

> **Gotcha:** Some Oracle instances return `GLOBAL_DB_NAME` with a domain suffix (e.g., `MYDB.EXAMPLE.COM` instead of `MYDB`). If the name contains dots, it must be **double-quoted** in the Included Table Names parameter: `"MYDB.EXAMPLE.COM".SCHEMA.TABLE`. Data must reside in the same database referenced by `Oracle Connection URL`.

### Missing Supplemental Logging

Error messages containing `ORA-01284` or `ORA-26948`, or CDC processor errors about missing column data.
```sql
-- Verify supplemental logging on the source Oracle database
SELECT SUPPLEMENTAL_LOG_DATA_ALL FROM V$DATABASE;
```
If `NO`, supplemental logging needs to be enabled on the source database. This is a customer DBA action.

### Oracle User Privilege Issues

Errors containing `ORA-01031` (insufficient privileges) or `ORA-00942` (table or view does not exist).

Verify current grants for the connector user on the source Oracle database:
```sql
SELECT * FROM DBA_SYS_PRIVS WHERE GRANTEE = '<CONNECTOR_USER>';
SELECT * FROM DBA_TAB_PRIVS WHERE GRANTEE = '<CONNECTOR_USER>';
```

The connector user requires: `CREATE SESSION`, `SELECT` and `FLASHBACK` on target tables, and `EXECUTE_CATALOG_ROLE` for XStream. If grants are missing, this is a customer DBA action.

### XStream Configuration Errors

Errors containing `ORA-01291` or `ORA-26945`. The XStream outbound server may not be properly configured for the tables being replicated.
```sql
-- Check XStream outbound server configuration
SELECT SERVER_NAME, CONNECT_USER, CAPTURE_NAME, STATUS FROM ALL_XSTREAM_OUTBOUND;
```
Verify the capture process includes the intended tables.

### Large Transaction / Archive Log Gaps

Performance degradation or stalled replication due to very large transactions. Check LogMiner session status:
```sql
SELECT SID, SERIAL#, STATUS FROM V$LOGMNR_SESSION;
```
If the session shows WAITING FOR DICTIONARY or similar, required archive logs may have been deleted. This typically requires recreating the XStream configuration.

### PLS-00201: DBMS_XSTREAM_AUTH_IVK

**Error:** `PLS-00201: identifier 'DBMS_XSTREAM_AUTH_IVK' must be declared`

**Likely Cause:** Using `container => 'ALL'` parameter in `CREATE_OUTBOUND` on a **single-tenant** (non-CDB) database. This parameter is only valid for Container Databases (CDBs).

**Recommended Action:** Omit the `container => 'ALL'` parameter from the `DBMS_XSTREAM_ADM.CREATE_OUTBOUND` call. Recreating the outbound server is a customer DBA action.

### ORA-01722: Invalid Number (during CREATE_OUTBOUND)

**Error:** `ORA-01722: invalid number` when running `DBMS_XSTREAM_ADM.CREATE_OUTBOUND`.

**Likely Cause:** This misleading error typically means an outbound server with the same name **already exists**. Oracle does not provide a clear "already exists" message for this case.

**Recommended Action:** Check existing outbound servers: `SELECT SERVER_NAME FROM ALL_XSTREAM_OUTBOUND;`. If a duplicate exists, the customer DBA must drop and recreate it or choose a different server name.

### ORA-26696: No XStream Data Dictionary

**Error:** `ORA-26696: no XStream data dictionary for ...`

**Likely Cause:** This is a known Oracle bug with no known workaround. It affects the XStream data dictionary and prevents the capture process from reading changes.

**Recommended Action:** Escalate to Oracle support. This is not an Openflow connector issue.

---

For detailed Oracle CDC troubleshooting, refer to the published Oracle connector docs linked at the top of this file, especially [Configure the connector](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-connector), [Set up Snowflake](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-snowflake), and [Configure the Oracle database](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/setup-oracledb). Escalate to Snowflake support only when the evidence points to an Openflow product defect or a platform-side issue rather than Oracle/XStream configuration.
