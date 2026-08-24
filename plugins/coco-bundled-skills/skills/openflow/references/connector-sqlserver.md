---
name: openflow-connector-sqlserver
description: SQL Server CDC connector for Openflow. Covers Change Tracking prerequisites, single and multi-database replication, connector parameters, DBA best practices, incremental replication, and troubleshooting. Use for SQL Server database replication to Snowflake.
---

<!--
MAINTAINER NOTE:

This file is routed from two locations:

1. connector-main.md — "Connectors with Specific Documentation" table:
   | SQL Server, MSSQL, CDC, database replication | `sqlserver-multidatabase` | `references/connector-sqlserver.md` |

2. SKILL.md — Reference Index under "Connector Operations":
   | `references/connector-sqlserver.md` | SQL Server CDC connector (Change Tracking setup, multi-DB replication, troubleshooting) |
-->

# SQL Server CDC Connector

The Openflow Connector for SQL Server replicates data from a SQL Server database instance to Snowflake in near-real-time using SQL Server Change Tracking (CT). A single connector instance can replicate tables from multiple databases within the same SQL Server instance.

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

This reference covers:
- SQL Server Change Tracking prerequisites (the primary setup complexity)
- DBA best practices for safe CT deployment
- Single-connector multi-database replication
- Connector parameter configuration (source, destination, ingestion)
- Incremental replication and maintenance workflows
- Schema evolution handling
- Troubleshooting CT and replication issues

For PostgreSQL or MySQL CDC, see `references/connector-cdc.md`. For other connectors, see `references/connector-main.md`.

## Workflow Summary

Complete ALL steps before starting the flow:

1. **Network Access** — EAI attached to runtime (SPCS only)
2. **Network Validate** — Test connectivity to SQL Server endpoint
3. **Deploy** — Deploy the connector flow (`sqlserver-multidatabase`)
4. **Parameters** — Configure source, destination, and ingestion parameters
5. **Asset Uploads** — Upload Microsoft JDBC driver (required, not bundled)
6. **Verify Controllers** — Run `verify_config` before enabling
7. **Enable Controllers** — Enable after verification passes
8. **Verify Processors** — Run `verify_config` after controllers enabled
9. **Start** — Start the flow
10. **Validate** — Confirm data is flowing

**Common failure:** Skipping Change Tracking enablement on source databases/tables causes capture processor errors at start time. Skipping JDBC driver upload causes controllers stuck in ENABLING state.

See [Deployment Workflow](#deployment-workflow) for detailed instructions.

---

## Change Tracking vs Native CDC — Important Distinction

The Openflow Connector for SQL Server uses **Change Tracking (CT)**, not SQL Server's native CDC feature. These are different technologies:

| Feature | Change Tracking (CT) | Native CDC |
|---------|---------------------|------------|
| Mechanism | Tracks which rows changed via version numbers | Captures full change history via transaction log |
| Data retained | Current version only (net changes) | Full change stream (every intermediate value) |
| Storage overhead | Minimal (internal tracking tables) | Higher (CDC tables in source DB) |
| Availability | SQL Server 2008+ | SQL Server 2008+ (Enterprise or Standard) |
| Openflow support | **Current** — GA connector | **Future** — FLOW-6645 (PuPr) |

**Do not confuse the two.** When guiding users through prerequisites, ensure they enable **Change Tracking**, not SQL Server CDC (`sys.sp_cdc_enable_db`).

**Exception — AWS RDS:** On AWS RDS for SQL Server, Change Tracking is enabled with standard T-SQL commands (same as on-premises). If a user mentions `rds_cdc_enable_db`, clarify that this is for native CDC, not Change Tracking, and is not required for the Openflow connector.

---

## Collect Checklist

Gather this information from the user **before** proceeding with deployment.

### Source Database Configuration (Required)

| Item | Example | Collected |
|------|---------|-----------|
| SQL Server version | 2019, 2022, 2025 (must be 2008+) | [ ] |
| Platform | On-premises, Azure SQL DB (single-DB only), Azure SQL MI, AWS RDS, GCP Cloud SQL | [ ] |
| Connection URL | `jdbc:sqlserver://host:1433;databaseName=db` | [ ] |
| Username | Database login | [ ] |
| Password | (sensitive) | [ ] |
| Databases to replicate | List of database names on the instance | [ ] |
| Tables to replicate | FQN format: `database.schema.table` | [ ] |
| SSL required? | Yes/No — if yes, obtain root certificate | [ ] |
| Read replica? | Yes/No — if yes, confirm transactional replication is healthy | [ ] |

### Snowflake Configuration (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| Destination Database | Database for replicated data (must already exist) | [ ] |
| Snowflake Role | Role with CREATE SCHEMA privileges on destination database | [ ] |
| Snowflake Warehouse | Warehouse for processing (start with XSMALL) | [ ] |
| Authentication Strategy | SNOWFLAKE_MANAGED (SPCS and BYOC execute-as roles) or KEY_PAIR (BYOC alternative) | [ ] |

### SQL Server Prerequisites (User Must Complete)

| Prerequisite | Status |
|--------------|--------|
| Change Tracking enabled on each database | [ ] |
| Change Tracking enabled on each table | [ ] |
| Login created for connector | [ ] |
| User created in each database | [ ] |
| SELECT granted on each table | [ ] |
| VIEW CHANGE TRACKING granted on each table | [ ] |
| Tables have primary keys | [ ] |

### Optional Items

| Item | When Required | Status |
|------|---------------|--------|
| VIEW DEFINITION grant | Tables use User Defined Data Types (UDDT) | [ ] |
| SSL root certificate | SSL connection to SQL Server | [ ] |
| Read replica validation | Connecting to a subscriber server | [ ] |

**Do not proceed until all required items are collected and prerequisites confirmed.**

---

## Supported Platforms and Limitations

### Supported SQL Server Versions & Platforms

- SQL Server **2008 and later** (Change Tracking was introduced in SQL Server 2008)
- On-premises servers
- Azure SQL Database (singleton — supports replicating a **single database** per connector instance only)
- Azure SQL Managed Instance (supports multi-database replication)
- AWS RDS for SQL Server
- GCP Cloud SQL for SQL Server

**Note:** The connector can ingest from a primary server or from a subscriber server using transactional replication. Before connecting to a replica, ensure replication between primary and replica nodes works correctly.

### Limitations

| Limitation | Detail |
|------------|--------|
| Primary keys required | Only tables with primary keys can be replicated. Tables without PKs enter FAILED state. |
| 16 MB value limit | Individual cell values larger than 16 MB are not replicated. See `Oversized Value Strategy` destination parameter. |
| Runtime size | Must be at least **Medium**. Use larger for high data volumes. |
| Multi-node runtimes | **Not** supported. Set Min nodes and Max nodes to **1**. |
| UNIQUEIDENTIFIER | Currently mapped to VARCHAR, not Snowflake UUID type. |
| JSON in VARIANT | PutSnowpipeStreaming may store JSON in VARIANT columns as strings. |
| UDDT columns | Columns using User Defined Data Types are silently excluded unless `VIEW DEFINITION` is granted. |

---

## Official Documentation

Refer to the official Snowflake documentation for current requirements. These pages are the authoritative source; this skill reference provides operational guidance and troubleshooting beyond what the docs cover.

- **About:** [About Openflow Connector for SQL Server](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/about)
- **Setup:** [Set up the Openflow Connector for SQL Server](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/setup)
- **Incremental Replication:** [Set up incremental replication](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/incremental-replication)
- **Maintenance:** [Maintenance](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/maintenance)
- **Supported Versions:** [Supported SQL Server versions](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sql-server/about#supported-sql-server-versions)

---

## SQL Server Prerequisites

These steps must be completed by the **SQL Server database administrator** before the connector can be configured.

### Step 1: Enable Change Tracking on Each Database

Change Tracking must be enabled at the database level for every database containing tables you want to replicate.

```sql
ALTER DATABASE <database_name>
  SET CHANGE_TRACKING = ON
  (CHANGE_RETENTION = 2 DAYS, AUTO_CLEANUP = ON);
```

**Retention guidance:**
- **Minimum:** 2 days (Snowflake default recommendation)
- **Recommended for production:** 3–5 days for high-volume environments
- **Why:** If the connector falls behind and the retention window closes, SQL Server purges change records, forcing a full re-snapshot of affected tables. Extra retention is cheap insurance.

Run this for **every database** containing tables to replicate.

### Step 2: Enable Change Tracking on Each Table

```sql
ALTER TABLE <schema>.<table>
  ENABLE CHANGE_TRACKING;
```

Run this for **every table** to replicate.

**Note:** The `TRACK_COLUMNS_UPDATED = ON` option is **not required**. The connector works correctly without it. This option provides additional metadata about which specific columns changed in an update (not just which rows), which may be useful for downstream processing but adds minor overhead. You can also enable CT on additional tables while the connector is running — the connector will discover them.

### Step 3: Create Login and Per-Database Users

Create a dedicated, low-privilege login for the connector:

```sql
-- Instance-level login
CREATE LOGIN <openflow_login> WITH PASSWORD = '<strong_password>';
```

Then create a user mapped to this login **in each database** you are replicating:

```sql
USE <source_database>;
CREATE USER <openflow_user> FOR LOGIN <openflow_login>;
```

### Step 4: Grant Required Permissions

Grant SELECT and VIEW CHANGE TRACKING on **each table** in **each database**:

```sql
GRANT SELECT ON <schema>.<table> TO <openflow_user>;
GRANT VIEW CHANGE TRACKING ON <schema>.<table> TO <openflow_user>;
```

### Step 5: (Optional) Grant VIEW DEFINITION for UDDT Columns

If your tables contain columns that use User Defined Data Types (UDDT), and the UDDT is owned by a different user than the connector user, you must grant this permission:

```sql
GRANT VIEW DEFINITION TO <openflow_user>;
```

**Without this permission, columns using UDDT are silently excluded from replication.** There is no error or warning — the column simply does not appear in the destination table.

### Step 6: (Optional) Configure SSL Connection

If you use an SSL connection to SQL Server, create the root certificate for your database server. You will upload this certificate when configuring the connector's source parameters.

---

## Snowflake Account Prerequisites

These steps must be completed in Snowflake **before** configuring the connector's destination parameters.

### Step 1: Create Destination Database

```sql
CREATE DATABASE IF NOT EXISTS <destination_database>;
```

### Step 2: Create a Role for the Connector

```sql
CREATE ROLE IF NOT EXISTS OPENFLOW_SQLSERVER_ROLE;

GRANT USAGE ON DATABASE <destination_database> TO ROLE OPENFLOW_SQLSERVER_ROLE;
GRANT CREATE SCHEMA ON DATABASE <destination_database> TO ROLE OPENFLOW_SQLSERVER_ROLE;

GRANT USAGE ON WAREHOUSE <warehouse_name> TO ROLE OPENFLOW_SQLSERVER_ROLE;
```

**On SPCS:** The runtime's service role needs these grants. **Load** `references/ops-snowflake-auth.md` for details.

**On BYOC:** Grant the role to the service user:

```sql
GRANT ROLE OPENFLOW_SQLSERVER_ROLE TO USER <service_user>;
```

### Step 3: Verify Permissions

```sql
USE ROLE OPENFLOW_SQLSERVER_ROLE;
USE DATABASE <destination_database>;
CREATE SCHEMA IF NOT EXISTS _openflow_test;
DROP SCHEMA _openflow_test;
```

If either statement fails, check the grants above.

For full Snowflake authentication configuration (key-pair, session token, account identifier), **Load** `references/ops-snowflake-auth.md`.

---

## DBA Best Practices

### 1. Size Your Retention Window Conservatively

The single most common failure mode is **Change Tracking retention expiry**. If the connector falls behind (due to restart, maintenance, network issue), and the retention window closes, SQL Server purges the change records. The connector must then perform a full re-snapshot.

- Set `CHANGE_RETENTION` to at least **2 days** (minimum), **3–5 days** for production.
- The storage overhead is minimal compared to the operational risk of forced re-snapshots.
- Set up SQL Server Agent alerts to monitor the gap between the connector's last processed change version and the current version.

### 2. Monitor Change Tracking Health

```sql
-- Check CT is enabled on the database
SELECT DB_NAME(database_id) AS database_name,
       is_auto_cleanup_on,
       retention_period,
       retention_period_units
FROM sys.change_tracking_databases;

-- Check CT is enabled on specific tables
SELECT OBJECT_NAME(object_id) AS table_name,
       is_track_columns_updated_on
FROM sys.change_tracking_tables;

-- Check current CT version vs minimum valid version
SELECT CHANGE_TRACKING_CURRENT_VERSION() AS current_version,
       CHANGE_TRACKING_MIN_VALID_VERSION(OBJECT_ID('<schema>.<table>')) AS min_valid_version;
```

**Key health indicator:** If `current_version - min_valid_version` is growing faster than the connector processes changes, you risk retention expiry.

### 3. Warehouse Sizing for Merge Operations

The connector uses a Snowflake warehouse to merge CDC data into destination tables. Snowflake recommends:

- Start with **XSMALL** warehouse
- Scale up based on table count and data volume
- Large numbers of tables scale better with **multi-cluster warehouses** rather than larger single warehouses
- Use the `Merge Task Schedule CRON` parameter to control when merges run (limits warehouse cost)

### 4. Read Replica Considerations

The connector supports connecting to a subscriber server using transactional replication. Before configuring:

- Verify replication between primary and replica is healthy and up-to-date
- When investigating missing data, first check that change tracking events are present in the replica server
- CT on a replica tracks changes applied by the replication agent, not changes on the primary

---

## Flow Names

| Flow Name | Status | Description |
|-----------|--------|-------------|
| `sqlserver-multidatabase` | **Current — use this** | Multi-database connector. The only SQL Server connector available in the connector catalogue. Supports single and multi-database replication. |

> **⚠️ WARNING:** A legacy `sqlserver` single-database connector exists but is **deprecated and not available in the connector catalogue**. Do not use it for any deployments. If you encounter references to `sqlserver` (without `-multidatabase`), they refer to the deprecated variant.

The `sqlserver-multidatabase` connector natively supports replicating tables from **multiple databases** within a single SQL Server instance. Simply specify tables from different databases in the `Included Table Names` parameter using the `database.schema.table` FQN format.

---

## Deployment Workflow

Follow the main workflow in `references/connector-main.md`. This section provides SQL Server-specific details for each step.

### 1. Network Access (SPCS Only)

**Load** `references/platform-eai.md` for EAI setup.

### 2. Network Validate (SPCS Only)

**Load** `references/ops-network-testing.md` and test connectivity to the SQL Server endpoint.

Test targets (replace with actual values):

```python
targets = [
    {"host": "sqlserver-host.example.com", "port": 1433, "type": "JDBC/SQLServer"},
]
```

**Important:** Network rules are host:port specific. A `SocketTimeoutException` after DNS success indicates the port is not in the network rule.

### 3. Deploy

**Load** `references/ops-flow-deploy.md`. Flow name: `sqlserver-multidatabase`

### 4. Handle Parameters

Configure parameters in order:
1. **Source Parameters** — See [SQL Server Source Parameters](#sql-server-source-parameters) below
2. **Destination Parameters** — **Load** `references/ops-snowflake-auth.md`
3. **Ingestion Parameters** — See [SQL Server Ingestion Parameters](#sql-server-ingestion-parameters) below

Use `references/ops-parameters-main.md` for configuration commands.

### 5. Asset Uploads

**JDBC Driver Required.** The user must upload the Microsoft JDBC Driver for SQL Server through the Snowsight UI. This is a manual step — the AI cannot upload files on the user's behalf.

| Parameter Name | Driver |
|---------------|--------|
| SQL Server JDBC Driver | Microsoft JDBC Driver for SQL Server |

**Instruct the user:**
1. Download the driver JAR from Maven Central
2. In the Snowsight connector parameters, find "SQL Server JDBC Driver" and check the **Reference asset** checkbox
3. Upload the downloaded JAR file

**Maven Central URL (recommended v12.10.0):**

```
https://repo1.maven.org/maven2/com/microsoft/sqlserver/mssql-jdbc/12.10.0.jre11/mssql-jdbc-12.10.0.jre11.jar
```

**Note:** JDBC driver v13.x is under validation ([FLOW-10139](https://snowflakecomputing.atlassian.net/browse/FLOW-10139)). Once confirmed, v13.x will be the recommended version due to security fixes and SQL Server 2025 readiness. If using v13.2+, be aware of changes to VECTOR data type handling — set `vectorTypeSupport=off` in the connection URL if needed.

See `references/ops-parameters-assets.md` for upload commands.

### 6. Verify Controllers

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_processors=false
```

### 7. Enable Controllers

**Load** `references/ops-flow-lifecycle.md` (Enable Controllers Only section).

### 8. Verify Processors

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_controllers=false
```

### 9. Start

**Load** `references/ops-flow-lifecycle.md` for starting the flow.

### 10. Validate

After starting, validate data is flowing. See [Validate Data Flow](#validate-data-flow) below.

---

## SQL Server Source Parameters

**Sensitive values:** Passwords are marked (sensitive). Ask user to provide directly. Never display these values — use `[REDACTED]` in confirmations.

| Parameter | Required | Description |
|-----------|----------|-------------|
| SQL Server Connection URL | Yes | `jdbc:sqlserver://host:1433;databaseName=db` |
| SQL Server Username | Yes | Database login username |
| SQL Server Password | Yes | Database login password (sensitive) |
| SQL Server SSL Root Certificate | No | Root certificate file for SSL connections. Upload as a reference asset. |

**Connection URL notes:**
- Standard: `jdbc:sqlserver://host:1433;databaseName=db`
- With encryption: `jdbc:sqlserver://host:1433;databaseName=db;encrypt=true;trustServerCertificate=false`
- Azure SQL: `jdbc:sqlserver://yourserver.database.windows.net:1433;databaseName=db;encrypt=true`
- The `databaseName` in the URL is used as the initial catalog. For multi-database replication, specify any one of the databases — the connector discovers tables across all databases via the `Included Table Names` parameter.

---

## SQL Server Ingestion Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| Included Table Names | No* | Comma-separated FQN list: `database.schema.table` (e.g., `db1.dbo.orders,db2.sales.customers`) |
| Included Table Regex | No* | Regex against `database.schema.table` paths (e.g., `my_db\\.dbo\\.auto_.*`) |
| Filter JSON | No | JSON specifying per-table column inclusion patterns |
| Ingestion Type | No | `full` (default) or `incremental` — see [Incremental Replication](#incremental-replication) |
| Starting Change Tracking Position | No | `Latest` (default) or `Earliest` — see [Incremental Replication](#incremental-replication) |
| Merge Task Schedule CRON | No | CRON expression controlling when journal→destination merges run |
| Concurrent Select Queries For Snapshot | No | Number of parallel SELECT queries during initial snapshot phase. Higher values speed up snapshots but increase source DB load. |
| Object Identifier Resolution | No | `CASE_SENSITIVE` (default) or `CASE_INSENSITIVE` — see below |

*One of Included Table Names or Included Table Regex is required.

### Key Destination Parameters

These are configured in the SQLServer Destination Parameters context (see `references/ops-snowflake-auth.md` for the full list). The following are especially relevant for SQL Server:

| Parameter | Description |
|-----------|-------------|
| Oversized Value Strategy | Controls behavior when a cell value exceeds 16 MB. Options: `FAIL_TABLE` (default — table enters FAILED state) or `SKIP_VALUE` (skip the oversized value, continue replication). Set to `SKIP_VALUE` if your source contains occasional large BLOBs that can be tolerated as missing. |

### Object Identifier Resolution

| Value | Behavior | Use When |
|-------|----------|----------|
| `CASE_SENSITIVE` (default) | Preserves source casing (e.g., `"dbo"."Orders"`) | You want exact match to source; requires quoted identifiers |
| `CASE_INSENSITIVE` | Uppercases all names (e.g., `DBO.ORDERS`) | You prefer Snowflake-native naming; no quoting needed |

**IMPORTANT: Ask the user before proceeding:**
> "Do you want to preserve the original casing from your SQL Server, or use Snowflake's default uppercase naming?
> - **Preserve casing** (CASE_SENSITIVE): Names stay as-is (e.g., `"dbo"."Orders"`). You must quote identifiers in SQL.
> - **Uppercase** (CASE_INSENSITIVE): Names are uppercased (e.g., `DBO.ORDERS`). Standard Snowflake convention."

**WARNING:** This setting cannot be changed after replication has started without performing a full connector reset (stop flow, clear state, drop destination tables, restart).

### Merge Task Schedule CRON

Controls when the connector triggers warehouse merge operations. Examples:

| Expression | Behavior |
|------------|----------|
| `* * * * * ?` | Continuous merging (every minute) — highest latency, highest cost |
| `* 0 * * * ?` | Merge at the top of every hour for one minute |
| `* 20 14 ? * MON-FRI` | Merge at 2:20 PM weekdays only |
| `0 5 * * ? *` | Once daily at 5:00 AM |

**Tip:** If no new changes exist, the warehouse auto-suspends. Scheduling merges to specific windows is the primary cost control lever.

---

## Multi-Database Replication

The `sqlserver-multidatabase` connector natively supports replicating tables from **multiple databases** within a single SQL Server instance. No special configuration is required beyond:

1. Enable CT on each database and each table (see [SQL Server Prerequisites](#sql-server-prerequisites))
2. Create a user **mapped to the same login** in each database with SELECT + VIEW CHANGE TRACKING — the connector requires a **single SQL Server login** that has a corresponding user with appropriate permissions in every database being replicated
3. List tables from multiple databases in `Included Table Names` using FQN: `database.schema.table`

**Platform note:** Azure SQL Database (singleton) only supports replicating a single database per connector instance. For multi-database replication, use Azure SQL Managed Instance or an on-premises SQL Server instance.

The connector creates separate schemas in the Snowflake destination database — one per source database — preserving the source structure.

**Example:**
- Source: `sales_db.dbo.orders`, `hr_db.employees.staff`
- Destination in Snowflake: `DEST_DB."dbo"."orders"`, `DEST_DB."employees"."staff"` (with separate schemas per source database)

### Schema Consolidation Mode

For multi-tenant databases where the same schema structure is repeated across databases (e.g., `tenant1.dbo.orders`, `tenant2.dbo.orders`), the connector supports a **Consolidation Mode** that merges tables from multiple databases into a single destination table with an added source-database column. This feature is currently being finalized (FLOW-7693).

---

## Incremental Replication

The connector supports two ingestion types:

### Full Mode (Default)

New tables go through: Schema Introspection → Snapshot Load → Incremental Load.

The snapshot phase copies all existing data before switching to real-time change capture.

### Incremental Mode

New tables skip the snapshot and immediately begin capturing changes from the current CT position.

**When to use incremental mode:**
- You've already bulk-loaded historical data via another method (e.g., `COPY INTO` from a staged export)
- You're adding tables to an existing replication set and don't want to disrupt throughput
- You're reinstalling or migrating the connector and want to resume where you left off

**To enable:**
Set `Ingestion Type` to `incremental` in the SQLServer Ingestion Parameters context.

**Important:** Return to `full` mode after your incremental catch-up is complete, so any future table additions get proper snapshots.

### Starting Change Tracking Position

| Value | Behavior | Use When |
|-------|----------|----------|
| `Latest` (default) | Start capturing from the current CT version | New deployments |
| `Earliest` | Start from the earliest available CT version | Reinstalling connector, catching up after maintenance |

**Warning:** Switching a running connector from `Latest` to `Earliest` causes CT tables to be re-read and re-processed. Destination tables may be temporarily out of sync until all events are re-merged.

### Connector Reinstallation Workflow

When reinstalling the connector (same or different runtime):

1. Review and note all parameter context values
2. Finish processing all in-flight FlowFiles, then stop the connector
3. Install the new connector instance
4. Configure parameters (reuse existing context if same runtime, re-enter if different)
5. Set `Ingestion Type` to `incremental`
6. Set `Starting Change Tracking Position` to `Earliest`
7. Start the new connector

The new connector reuses existing destination tables but creates new journal tables.

---

## Schema Evolution

The connector handles schema changes from the source database:

### Column Additions

New columns are automatically detected and added to the destination table. Existing rows will have `NULL` for the new column until updated.

### Column Renames

The connector treats renames as a drop + add:
- Original column is renamed with a `__SNOWFLAKE_DELETED` suffix (e.g., `A` becomes `A__SNOWFLAKE_DELETED`)
- New column (e.g., `B`) is added
- Pre-rename rows have data in `A__SNOWFLAKE_DELETED` and NULL in `B`
- Post-rename rows have NULL in `A__SNOWFLAKE_DELETED` and data in `B`

**To unify:** Create a view:

```sql
CREATE VIEW my_table_unified AS
SELECT
    *,
    COALESCE(B, A__SNOWFLAKE_DELETED) AS A_RENAMED_TO_B
FROM my_table;
```

**Do not** manually modify the destination table structure (dropping or renaming columns) — this may interfere with ongoing replication.

### Column Drops

Dropped columns are renamed with the `__SNOWFLAKE_DELETED` suffix. The connector does not automatically delete data — you maintain full ownership and control.

---

## Journal Tables

During incremental replication, changes are first written to **journal tables** before being merged into destination tables. Key facts:

- The connector does **not** automatically remove journal data (useful for auditing/debugging)
- Journal table naming: `<table>_<hash>_<generation>` (e.g., `orders_5678_2`)
- When a table is removed from replication, its journal tables can be manually dropped
- For actively replicated tables, keep only the latest generation journal table

---

## Validate Data Flow

### Step 1: Check Flow Status

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect:
- `running_processors` > 0
- `invalid_processors` = 0
- `bulletin_errors` = 0

### Step 2: Validate Target Objects Created

```sql
-- Check schemas exist
SHOW SCHEMAS IN DATABASE <destination_database>;

-- Check tables exist (quote lowercase names if CASE_SENSITIVE)
SHOW TABLES IN SCHEMA <destination_database>."<source_schema>";

-- Validate rows
SELECT COUNT(*) FROM <destination_database>."<source_schema>"."<source_table>";
```

### Step 3: Monitor Table Replication State

Check the Table State Store controller service for replication status:

| Status | Meaning |
|--------|---------|
| `NEW` | Table discovered, replication not started |
| `SNAPSHOT_REPLICATION` | Capturing initial snapshot |
| `INCREMENTAL_REPLICATION` | Streaming real-time changes |
| `FAILED` | Permanently stopped due to error |

---

## Recovering from FAILED State

If a table enters FAILED state, recovery requires removing the table, cleaning up, and re-adding.

**WARNING:** This process includes destructive operations. Confirm each step with the user.

### Step 1: Identify Failure Cause

Common causes:
- Table lacks a primary key
- Unsupported schema change
- Change Tracking retention expired
- Unsupported data type
- 16 MB value limit exceeded

### Step 2: Remove Table from Replication

Update `Included Table Names` or `Included Table Regex` to exclude the failed table.

### Step 3: Verify Table Removed from State

Check the Table State Store — the failed table should no longer appear.

### Step 4: Drop Destination Table in Snowflake

Ask the user: "This will DROP the table from Snowflake. This is irreversible. Proceed?"

```sql
DROP TABLE <destination_database>."<schema>"."<failed_table>";
```

**Note:** The connector will not overwrite an existing destination table during the snapshot phase. If the table still exists, re-adding it will fail.

### Step 5: Re-add Table to Replication

Ask the user: "Re-adding this table will trigger a full snapshot reload. Proceed?"

Update the inclusion parameters to add the table back.

---

## Known Issues

### Change Tracking Retention Expiry

**Symptom:** Tables move to FAILED state with "change tracking version" errors.

**Cause:** The connector fell behind and the CT retention window closed.

**Fix:** Increase `CHANGE_RETENTION` on the source database, then re-add the table (triggers full re-snapshot).

**Prevention:** Set retention to 3–5 days, monitor the gap between connector's last processed version and current version.

### UDDT Columns Silently Excluded

**Symptom:** Columns are missing from destination tables with no error.

**Cause:** Table uses User Defined Data Types and the connector user lacks VIEW DEFINITION.

**Fix:** `GRANT VIEW DEFINITION TO <openflow_user>;`

### BINARY Tables 8MB Limit

**Symptom:** Tables with BINARY/VARBINARY columns fail or produce truncated data.

**Cause:** Known limitation in destination table creation for binary types.

**Status:** Fix in progress (FLOW-9790).

### PrivateKeyService INVALID on SPCS

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID. Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

### Check Bulletins

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Check `bulletin_errors` and `bulletin_warnings` fields.

### Common Error Patterns

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| Controller stuck in ENABLING | JDBC driver not uploaded | Upload Microsoft JDBC driver (Step 5) |
| Connection refused / timeout | Network rule missing port 1433 | Update EAI network rule |
| Authentication failed | Wrong login/password or permissions | Verify SQL Server login and user setup |
| "Change tracking is not enabled" | CT not enabled on database or table | Run `ALTER DATABASE/TABLE` CT commands |
| Table enters FAILED immediately | Table lacks primary key | Add PK or remove table from replication |
| Columns missing in destination | UDDT without VIEW DEFINITION grant | Grant VIEW DEFINITION |

---

## Operational Notes for PM Reporting

These details are relevant for the morning report and metrics dashboards:

| Item | Detail |
|------|--------|
| Connector IDs (metrics) | `sqlserver-multidatabase` (current), `sqlserver` (legacy — include in historical queries only) |
| Display name | `SQLServer` (consolidated) |
| NiFi processors | `MultiDatabaseCaptureChangeSqlServer` |
| Credits/TB anomaly | Cap at 1000 for outlier days |
| Metrics export | Blocked (FLOW-8719) — SQL Server metrics are not yet in Snowhouse |

---

## Next Step

After deployment and configuration, return to `references/connector-main.md` or the calling workflow.

## See Also

- `references/connector-main.md` — Connector workflow overview
- `references/connector-cdc.md` — Shared CDC patterns (PostgreSQL, MySQL)
- `references/ops-component-state.md` — Inspect and clear table replication state
- `references/ops-snowflake-auth.md` — Snowflake destination configuration
- `references/platform-eai.md` — Network access for database connectivity
- `references/ops-parameters-main.md` — Parameter configuration
- `references/connector-upgrades.md` — Version management
