---
name: openflow-observability-connector-mysql
description: MySQL connector troubleshooting and SPCS domain allowlist.
---

# MySQL CDC

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mysql/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mysql/setup)
- [Data mapping](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mysql/data-mapping)
- [Incremental replication](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mysql/incremental-replication)
- [Maintenance](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mysql/maintenance)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
|--------|-------|
| `<customer-db-host>:<port>` | Customer-specific. Default port: 3306. |

## Parameters & Required Assets

This file covers the gen-1 MySQL connector, configured through Apache NiFi parameter contexts. For the gen-2 first-class, SQL-managed connector (`OPENFLOW_MYSQL_CDC`) and its `connector.config_set_property` property forms, see [mysql-sql-managed.md](mysql-sql-managed.md).

The MySQL connector uses three parameter contexts. Key parameters from the [official setup documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/mysql/setup):

### Source Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Database Hostname` | MySQL server host | Required |
| `Database Port` | MySQL server port | Default: `3306` |
| `Database User` | Connection username | Needs SELECT, RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT |
| `Database Password` | Connection password | Required |
| `MySQL JDBC Driver` | JDBC driver JAR | **Must upload MariaDB JDBC driver as Reference asset** (see below) |
| `Database SSL Connection` | Enable SSL | Optional; if enabled, upload root certificate |
| `Database Root Certificate` | SSL root certificate | Required only when SSL is enabled |

### Destination Parameters

See [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters).

### Ingestion Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Included Databases` | Databases to replicate | Comma-separated list |
| `Included Table Names` | Tables to replicate | Format: `<database>.<table>` |
| `Included Table Regex` | Regex pattern for tables | Alternative to explicit table list |
| `Object Identifier Resolution` | Case sensitivity | `CASE_SENSITIVE` or `CASE_INSENSITIVE` |
| `Skip Snapshot` | Skip initial full load | Set to `true` to start from current binlog position (useful for reinstallation) |

### JDBC Driver Asset Upload (MariaDB)

> **Critical:** The MySQL connector uses the **MariaDB JDBC driver** (NOT the MySQL Connector/J driver). The connection URL uses the `jdbc:mariadb://` prefix.

Upload the MariaDB Connector/J JAR as a parameter context asset. See [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) for upload steps, diagnosis queries, and resolution.

> **Note:** When SSL is disabled, the connection URL must include `?allowPublicKeyRetrieval=true` to allow authentication. This is typically handled by the connector automatically.

### SSL Configuration

For SSL configuration, see [SSL Configuration (Database Connectors)](connector-shared-generic.md#ssl-configuration-database-connectors).

### Azure `binlog_row_metadata` Limitation

On Azure Database for MySQL, the `binlog_row_metadata` parameter is not user-modifiable. If the connector fails due to missing row metadata, the customer must raise a Microsoft support ticket to change `binlog_row_metadata` to `FULL`.

## Troubleshooting

### MySQL Prerequisites

When a CDC connector is failing or not replicating data, verify that the source database prerequisites are correctly configured. Guide the customer through these checks.

Ask the customer to verify the following on their MySQL server:

**1. Binary logging is enabled with correct format:**
```sql
-- Run on the source MySQL database
SHOW VARIABLES LIKE 'log_bin';
SHOW VARIABLES LIKE 'binlog_format';
SHOW VARIABLES LIKE 'binlog_row_image';
SHOW VARIABLES LIKE 'binlog_row_metadata';
SHOW VARIABLES LIKE 'binlog_row_value_options';
```

Required values:
| Variable | Required Value | Notes |
|----------|---------------|-------|
| `log_bin` | `ON` | Binary logging enabled |
| `binlog_format` | `ROW` | Row-based replication only |
| `binlog_row_image` | `FULL` | All columns in each row event |
| `binlog_row_metadata` | `FULL` | Column names and PK info in binlog |
| `binlog_row_value_options` | (empty) | Must not be set to `PARTIAL_JSON` |

**2. Binary log retention is sufficient:**
```sql
-- Run on the source MySQL database
SHOW VARIABLES LIKE 'binlog_expire_logs_seconds';
```
Recommended: at least a few hours. For scheduled replication, longer than the schedule interval.

**3. GTID mode (recommended):**
```sql
-- Run on the source MySQL database
SHOW VARIABLES LIKE 'gtid_mode';
```
`ON` is recommended for reliable replication. Not strictly required but improves recovery.

**4. User has required privileges:**
```sql
-- Run on the source MySQL database
SHOW GRANTS FOR '<connector_user>'@'%';
```
Required: `SELECT`, `RELOAD`, `SHOW DATABASES`, `REPLICATION SLAVE`, and `REPLICATION CLIENT` (`SELECT` on the replicated tables; the rest at the server level).

**5. Sort buffer size:**
```sql
-- Run on the source MySQL database
SHOW VARIABLES LIKE 'sort_buffer_size';
```
If the connector fails with "Out of sort memory", the sort buffer size needs to be increased to at least `4194304` (4 MB). This is a customer DBA action.

If any of the above prerequisites are not met, describe the required configuration changes to the customer and make it clear that the fixes happen on the customer's MySQL server. **Do NOT suggest restarting or reconfiguring the Openflow connector itself for prerequisite issues.** If a table has already entered `FAILED`, the source fix alone is not enough -- after the MySQL prerequisite is corrected, use [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) for each affected failed table. A connector restart adds no value when the root cause is a missing source prerequisite.

> **If the source side is fine but the connector references a wrong value** (wrong host/port in `Source Database Connection URL`, wrong `Source Database User`, a stale `Starting Binlog Position`, or a wrong `Re-read Tables in State` list): this is a connector-side config error, not a source DBA fix. `OPENFLOW_MYSQL_CDC` is SQL-managed; the live `SHOW` / `DESCRIBE OPENFLOW CONNECTOR` check (or the resolved connector ID) confirms the definition before any edit, so the agent can update that single property via `connector.config_set_property` after confirmation -- see [Openflow SQL Action Candidates for CDC Config Errors](connector-shared-cdc.md#openflow-sql-action-candidates-for-cdc-config-errors), and look up the exact property form in [mysql-sql-managed.md](mysql-sql-managed.md). You may optionally note that MySQL CDC is still in preview. For BYOC or legacy non-SQL-managed MySQL connectors, guide the customer to fix the value in the Openflow UI wizard instead.

---

### Binlog/WAL Lag

**Pattern:** No explicit errors, but data in Snowflake is significantly behind the source database. Or CDC engine warnings about connection or reading issues.

**Snowsight Checks:** Check if the CDC engine is reading the change stream but falling behind:

Run the **Replication Lag** query from `references/connectors/connector-shared-cdc.md`.

**Recommended Action:** Check binlog position. Ensure `binlog_expire_logs_seconds` is set to retain logs long enough. If the connector fell behind expired binlogs, treat this as a customer-recoverable position-loss event: fix retention first.

Do not recommend a connector-wide reset. Escalate only if tables continue to fail after the documented recovery path or the logs indicate a product defect.

Also check resource utilization -- use CPU Utilization by Pod and Memory Utilization by Pod from `references/core-queries-resource.md`. If the runtime is resource-constrained, tell the customer that a larger runtime size may be required.

---

### Unable to Connect to Binlog

**Pattern:** Errors containing `Unable to connect to binlog`, `Could not find first log file name`, or `The slave is connecting using CHANGE MASTER TO MASTER_AUTO_POSITION = 1, but the master has purged binary logs`.

**Likely Cause:** The connector cannot establish or resume a binlog connection. Common causes:
- Binary logging is disabled or not in `ROW` format on the source
- The binlog file or position the connector last read has been purged (retention window expired while the connector was paused)
- Network path to the MySQL source on the replication port is blocked

**Recommended Action:**
1. Verify binary logging prerequisites using the queries in [MySQL Prerequisites](#mysql-prerequisites): confirm `log_bin=ON`, `binlog_format=ROW`, and `binlog_expire_logs_seconds` is set to a value long enough for the connector to catch up.
2. If the connector was stopped longer than the `binlog_expire_logs_seconds` window, the required binlog files were purged. The customer DBA must increase the retention value before the connector can reconnect. This is a customer DBA action.
3. If GTID mode is enabled, verify the connector's GTID position is still within the available GTID set on the source:
```sql
-- Run on the source MySQL database
SHOW MASTER STATUS;
SHOW GLOBAL VARIABLES LIKE 'gtid_purged';
```
4. If binlog position is unrecoverable and tables are in `FAILED`, fix the binlog configuration first, then use [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) for each affected table.

---

### Host is Blocked

**Pattern:** Error containing `Host '<host>' is blocked because of many connection errors` or reference to `max_connect_errors`.

**Likely Cause:** MySQL blocks a source host after it accumulates `max_connect_errors` (default `100`) connection errors from that host without an intervening successful connection -- every successful connect resets the counter to zero. **Authentication failures do NOT count** toward this threshold. What counts are interrupted/aborted connections, mid-handshake drops, malformed-packet/protocol errors, and server-side DNS resolution failures for the host. So the trigger is connection-level instability from the connector's egress IP, not bad credentials.

**Recommended Action:**
1. **Identify and fix the root cause first** -- use the queries in [MySQL Prerequisites](#mysql-prerequisites) to confirm connectivity is stable (the counter is driven by aborted/dropped connections and DNS failures, not auth errors). Unblocking without fixing the underlying cause results in the block returning.
2. Once the root cause is fixed, ask the customer DBA to clear the host cache to unblock:
```sql
-- Run on the source MySQL database (DBA action)
-- MySQL 8.0.23+: FLUSH HOSTS is deprecated; use the host_cache truncate instead.
TRUNCATE TABLE performance_schema.host_cache;
-- Older MySQL (pre-8.0.23):
-- FLUSH HOSTS;
```
   The host cache is in-memory, so a blocked host stays blocked until the cache is cleared by the statement above or until the MySQL server restarts.
3. Verify the connector reconnects. If tables entered `FAILED` during the block period, use [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) after the source is fixed.
4. Raising `max_connect_errors` is rarely the right fix: the default of `100` is already high, the counter resets on every successful connection, and a healthy connector will not approach it. Removing the source of the connection errors is the durable fix.

---

### Access Denied

**Pattern:** Error containing `Access denied for user`, authentication failures from the MariaDB JDBC driver, or `Public Key Retrieval is not allowed`.

**Likely Cause:** The connector's database user has an incorrect password, is missing required replication privileges, or requires additional JDBC authentication configuration.

**Recommended Action:**
1. Verify the `Database User` and `Database Password` values in the connector's source parameters are correct.
2. Ask the customer DBA to check the grants for the connector user:
```sql
-- Run on the source MySQL database
SHOW GRANTS FOR '<connector_user>'@'%';
```
Required grants: `SELECT`, `RELOAD`, `SHOW DATABASES`, `REPLICATION SLAVE`, and `REPLICATION CLIENT` (`SELECT` on the replicated tables; the rest at server level). See [MySQL Prerequisites](#mysql-prerequisites). If grants are missing, this is a customer DBA action.
3. If the error is `Public Key Retrieval is not allowed`: the connection URL must include `?allowPublicKeyRetrieval=true` when SSL is disabled. Verify this is present in the JDBC URL, or enable SSL for the connection.
4. If authentication errors persist after verifying credentials and privileges, ask the customer DBA to reset the user password:
```sql
-- Run on the source MySQL database (DBA action)
ALTER USER '<connector_user>'@'%' IDENTIFIED BY '<new_password>';
FLUSH PRIVILEGES;
```

---

### Partial-JSON Binlog Rows

**Pattern:** CDC fails with errors about malformed or partial binlog events, or JSON column updates are missing or incorrect at the destination despite the source table having changes. The source MySQL variable `binlog_row_value_options` is set to `PARTIAL_JSON`.

**Likely Cause:** When `binlog_row_value_options=PARTIAL_JSON`, MySQL writes only the changed portions of JSON columns to the binlog as partial update events rather than full row images. The connector cannot reconstruct the full row from a partial JSON diff.

**Recommended Action:**
1. Verify the setting on the source:
```sql
-- Run on the source MySQL database
SHOW VARIABLES LIKE 'binlog_row_value_options';
```
2. If the value is `PARTIAL_JSON`, the customer DBA must clear it:
```sql
-- Run on the source MySQL database (DBA action)
SET GLOBAL binlog_row_value_options = '';
```
For managed services (AWS RDS, Azure Database for MySQL), this must be changed via the RDS parameter group or Azure server parameters UI — `SET GLOBAL` is not permitted for this variable on these platforms.
3. After fixing the variable, if tables are in `FAILED`, use [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) for each affected table.

> **Note:** `binlog_row_image=FULL` (required for the connector) does not override `binlog_row_value_options`. Both must be configured correctly. The [MySQL Prerequisites](#mysql-prerequisites) diagnostic block checks both.
