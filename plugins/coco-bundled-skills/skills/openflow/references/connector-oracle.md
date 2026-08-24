---
name: openflow-connector-oracle
description: Oracle CDC connector for Openflow. Covers licensing choice (Embedded vs BYOL), Oracle XStream prerequisites, connector configuration, DBA best practices, and troubleshooting. Use for Oracle database replication to Snowflake.
---

<!--
MAINTAINER NOTE:

This file is routed from two locations (added in the same PR):

1. connector-main.md — "Connectors with Specific Documentation" table:
   | Oracle, Oracle CDC, Oracle database replication | `oracle-embedded-license` or `oracle-independent-license` | `references/connector-oracle.md` |

2. SKILL.md — Reference Index under "Connector Operations":
   | `references/connector-oracle.md` | Oracle CDC connector (Embedded & BYOL licensing, XStream setup, troubleshooting) |

Sub-files live in references/connector-oracle/ and are loaded on demand via **Load** directives below.
Do NOT register the sub-files separately in SKILL.md or connector-main.md — this file is the only entry point.
-->

# Oracle CDC Connector

The Openflow Connector for Oracle replicates data from an Oracle database to Snowflake in near-real-time using Oracle XStream. It supports two licensing models: Embedded (Snowflake-provided) and Independent (Bring Your Own License).

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Common Tasks

| User intent | Go to |
|-------------|-------|
| "Which license do I need?" / "Do I qualify for Embedded?" | [Licensing Decision](#licensing-decision-resolve-first) → **Load** `connector-oracle/connector-oracle-licensing.md` |
| "How do I set up the ORGADMIN commercial terms / start the trial?" | **Load** [`connector-oracle/connector-oracle-licensing.md`](connector-oracle/connector-oracle-licensing.md) |
| "What do I need to configure on the Oracle database?" | **Load** [`connector-oracle/connector-oracle-database-setup.md`](connector-oracle/connector-oracle-database-setup.md) |
| "DBA best practices / is XStream safe on my production DB?" | **Load** [`connector-oracle/connector-oracle-database-setup.md`](connector-oracle/connector-oracle-database-setup.md) |
| "Walk me through deploying the connector" | [Deployment Workflow](#deployment-workflow) |
| "What parameters do I need to set?" | [Oracle Source Parameters](#oracle-source-parameters), [Oracle Ingestion Parameters](#oracle-ingestion-parameters) |
| "It's not working / XStream errors / table not appearing" | **Load** [`connector-oracle/connector-oracle-troubleshooting.md`](connector-oracle/connector-oracle-troubleshooting.md) |
| "How do I verify data is flowing?" | [Validate Data Flow](#validate-data-flow) |
| "Can I skip the initial snapshot?" | [Incremental Replication Without Snapshots](#incremental-replication-without-snapshots) |

## Scope

This reference covers:
- Licensing decision (Embedded vs BYOL) and ORGADMIN commercial activation
- Oracle database XStream prerequisites (the primary setup complexity)
- DBA best practices for safe XStream deployment
- Connector parameter configuration
- Troubleshooting XStream and replication issues

For other connectors, see `references/connector-main.md`.

## Workflow Summary

Complete ALL steps before starting the flow:

0. **Commercial Terms** — ORGADMIN enables Oracle Connector Terms; start trial (Embedded only)
1. **Network Access** — EAI attached to runtime (SPCS only)
2. **Network Validate** — Test connectivity to Oracle database endpoint
3. **Deploy** — Deploy the connector flow (`oracle-embedded-license` or `oracle-independent-license`)
4. **Parameters** — Configure source, destination, and ingestion parameters
5. **Asset Uploads** — None required (OCI driver is bundled)
6. **Verify Controllers** — Run `verify_config` before enabling
7. **Enable Controllers** — Enable after verification passes
8. **Verify Processors** — Run `verify_config` after controllers enabled
9. **Verify XStream Connectivity** — Single-processor verification on CaptureChangeOracle confirms XStream server is reachable and healthy
10. **Start** — Start the flow
11. **Validate** — Confirm data is flowing

**Common failure:** Skipping Oracle database prerequisites (Steps 1-8 in [Oracle Database Prerequisites](connector-oracle/connector-oracle-database-setup.md#oracle-database-prerequisites)) causes XStream connection errors at controller enable time.

See [Deployment Workflow](#deployment-workflow) for detailed instructions.

---

## Licensing Decision (Resolve First)

Unlike other CDC connectors, Oracle requires a licensing decision **before** any technical work. The wrong choice can cause deployment failure or unintended financial commitments.

Ask the user:

> "Does your organization already have an Oracle GoldenGate license (or another Oracle license that includes XStream entitlements)?"
>
> - **Yes** → Independent License (BYOL)
> - **No** → Check eligibility for Embedded License

For eligibility rules, licensing comparison (cost, core factor, commitment), Embedded lifecycle and auto-conversion risk, and ORGADMIN steps to enable Oracle Connector Terms and start the trial:

**Load** [`connector-oracle/connector-oracle-licensing.md`](connector-oracle/connector-oracle-licensing.md)

---

## Collect Checklist

Gather this information from the user **before** proceeding with deployment.

### Licensing & Commercial (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| License type | Embedded or Independent (BYOL) | [ ] |
| ORGADMIN enabled terms | Admin >> Terms >> Oracle Connector Terms accepted | [ ] |
| Trial started (Embedded only) | Admin >> Terms >> Openflow for Oracle >> Start Trial | [ ] |

### Oracle Source Configuration (Required)

| Item | Example | Collected |
|------|---------|-----------|
| Oracle version | 19c, 21c, 23c (must be 12cR1+) | [ ] |
| Platform | On-premises, Exadata, OCI, AWS RDS Custom, AWS RDS Standard Single-tenant | [ ] |
| Connection URL | `jdbc:oracle:thin:@//host:1521/YOUR_PDB_NAME` (points to the **PDB** containing data; for non-CDB, use the database service name) | [ ] |
| XStream Out Server URL | `jdbc:oracle:oci:@host:1521/CDB_SERVICE` (points to the **CDB root** service — XStream Outbound Servers are registered at CDB$ROOT; for **non-CDB**, use the same database service name as the Connection URL) | [ ] |
| XStream Out Server Name | User-defined during Oracle prerequisite Step 6 (no default — must ask user) | [ ] |
| Connect username | e.g., `c##connectuser` | [ ] |
| Connect password | (sensitive) | [ ] |
| Tables to replicate | Always three-part `DATABASE_NAME.SCHEMA.TABLE`. The `DATABASE_NAME` is the Oracle `GLOBAL_DB_NAME` (for CDB this is the PDB name, e.g., `FREEPDB1.PROCUREMENT.ORDERS`; for non-CDB it is the database name, e.g., `ORCL.PROCUREMENT.ORDERS`). Query `SELECT property_value FROM database_properties WHERE property_name = 'GLOBAL_DB_NAME';` to obtain it. | [ ] |
| Core count (Embedded only) | Physical processor cores on source Oracle DB | [ ] |
| Core factor (Embedded only) | Oracle Processor Core Factor (e.g., 0.5 for Intel) | [ ] |

### Snowflake Configuration (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| Destination Database | Database for replicated data (must already exist — see [Snowflake Account Prerequisites](#snowflake-account-prerequisites)) | [ ] |
| Snowflake Role | Role with CREATE SCHEMA privileges on destination database | [ ] |
| Snowflake Warehouse | Warehouse for processing | [ ] |

### Snowflake Prerequisites (User Must Complete)

| Prerequisite | Status |
|--------------|--------|
| Destination database created | [ ] |
| Role created with USAGE + CREATE SCHEMA on destination database | [ ] |
| Warehouse granted to role | [ ] |
| Role granted to service user (BYOC) or service role configured (SPCS) | [ ] |

See [Snowflake Account Prerequisites](#snowflake-account-prerequisites) for setup SQL.

### Oracle Prerequisites (User Must Complete)

| Prerequisite | Status |
|--------------|--------|
| ARCHIVELOG mode enabled | [ ] |
| XStream replication enabled (`enable_goldengate_replication=TRUE`) | [ ] |
| Supplemental logging enabled (on target tables) | [ ] |
| XStream administrator user created | [ ] |
| XStream connect user created with required privileges | [ ] |
| XStream Outbound Server created | [ ] |
| Tables have primary keys | [ ] |

**Do not proceed until all required items are collected and prerequisites confirmed.**

---

## Supported Platforms and Limitations

### Supported Oracle Versions & Platforms

- Oracle database versions **12cR1 and later** (including 23ai and 23ai Free)
- On-premises servers
- Oracle Exadata
- OCI VM/Bare Metal
- AWS Custom RDS for Oracle
- AWS Standard Single-tenant RDS for Oracle

**Note:** Oracle 23ai Free includes XStream support. Do not tell users that 23ai Free lacks XStream — it does.

### Unsupported

- AWS Standard **Multi-tenant** RDS for Oracle
- Oracle Autonomous Databases (ATP/ADW)
- Oracle SaaS (Fusion Cloud Applications, NetSuite)

### Limitations

- Only tables containing **primary keys** can be replicated.
- The connector works within a **single database/container** (PDB or CDB). To replicate tables from multiple containers, configure separate connector instances.
- The connector does **not** support re-adding a column after it is dropped.
- Runtime size must be at least **Medium**. Use larger for high data volumes.
- Multi-node runtimes are **not** supported. Set Min nodes and Max nodes to **1**.
- Requires Openflow deployment version **0.55.0 or later** for BYOC.

**Resilience Warning:** The connector relies on the specific SCN state of the source database. **Do not** perform RMAN DUPLICATE or database restores on a database actively connected to Openflow. Doing so will break the replication stream and may require a new license generation (and associated costs) to resolve.

---

## Official Documentation

Refer to the official Snowflake documentation for current requirements. These pages are the authoritative source; this skill reference provides operational guidance and troubleshooting beyond what the docs cover.

- **Oracle Connector Overview & Prerequisites:** [Set up the Openflow Connector for Oracle](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/about)

---

## Oracle Database Prerequisites

These steps must be completed by the **Oracle database administrator** before the connector can be configured. They cover ARCHIVELOG mode, XStream + supplemental logging, the XStream administrator and connect users, and Outbound Server creation (Steps 1-8).

**Load** [`connector-oracle/connector-oracle-database-setup.md`](connector-oracle/connector-oracle-database-setup.md)

---

## Snowflake Account Prerequisites

These steps must be completed in Snowflake **before** configuring the connector's destination parameters.

### Step 1: Create Destination Database

The connector writes replicated data into this database. It must already exist — the connector does **not** create it.

```sql
CREATE DATABASE IF NOT EXISTS <destination_database>;
```

### Step 2: Create a Role for the Connector

Create a dedicated role with the minimum privileges needed. The connector creates schemas and tables within the destination database automatically.

```sql
-- Create a dedicated role
CREATE ROLE IF NOT EXISTS OPENFLOW_ORACLE_ROLE;

-- Grant database-level privileges
GRANT USAGE ON DATABASE <destination_database> TO ROLE OPENFLOW_ORACLE_ROLE;
GRANT CREATE SCHEMA ON DATABASE <destination_database> TO ROLE OPENFLOW_ORACLE_ROLE;

-- Grant warehouse usage
GRANT USAGE ON WAREHOUSE <warehouse_name> TO ROLE OPENFLOW_ORACLE_ROLE;
```

**On SPCS:** The runtime's service role needs these grants. The connector runs as the service role associated with the Openflow runtime compute pool. **Load** `references/ops-snowflake-auth.md` for details on SPCS authentication.

**On BYOC:** Grant the role to the service user that holds the key-pair credentials:

```sql
GRANT ROLE OPENFLOW_ORACLE_ROLE TO USER <service_user>;
```

### Step 3: Verify Permissions

Confirm the role can create schemas in the destination database:

```sql
USE ROLE OPENFLOW_ORACLE_ROLE;
USE DATABASE <destination_database>;
CREATE SCHEMA IF NOT EXISTS _openflow_test;
DROP SCHEMA _openflow_test;
```

If either statement fails, check the grants above.

For full Snowflake authentication configuration (key-pair, session token, account identifier), **Load** `references/ops-snowflake-auth.md`.

---

## DBA Best Practices

For production safety guidance — I/O headroom checks, redo log sizing, STREAMS_POOL_SIZE configuration, surgical vs database-wide supplemental logging, XStream health monitoring views, and downstream capture for extreme-scale workloads:

**Load** [`connector-oracle/connector-oracle-database-setup.md`](connector-oracle/connector-oracle-database-setup.md#dba-best-practices)

---

## Flow Names

| Licensing Model | Flow Name |
|-----------------|-----------|
| Embedded (Snowflake-provided) | `oracle-embedded-license` |
| Independent (BYOL) | `oracle-independent-license` |

---

## Deployment Workflow

Follow the main workflow in `references/connector-main.md`. This section provides Oracle-specific details for each step.

### 0. Enable Commercial Terms (Unique to Oracle)

**Before any technical work**, the ORGADMIN must enable commercial terms and (for Embedded) start the trial. **Load** [`connector-oracle/connector-oracle-licensing.md`](connector-oracle/connector-oracle-licensing.md) for the full ORGADMIN procedure.

### 1. Network Access (SPCS Only)

**Load** `references/platform-eai.md` for EAI setup.

### 2. Network Validate (SPCS Only)

**Load** `references/ops-network-testing.md` and test connectivity to the Oracle database endpoint.

Test targets (replace with actual values):

```python
targets = [
    {"host": "oracle-host.example.com", "port": 1521, "type": "JDBC/Oracle"},
]
```

**Important:** Network rules are host:port specific. A `SocketTimeoutException` after DNS success indicates the port is not in the network rule.

### 3. Deploy

**Load** `references/ops-flow-deploy.md`. Flow names: `oracle-embedded-license` or `oracle-independent-license`.

### 4. Handle Parameters

Configure parameters in order:

1. **Source Parameters** — See [Oracle Source Parameters](#oracle-source-parameters) below
2. **Destination Parameters** — **Load** `references/ops-snowflake-auth.md`
3. **Ingestion Parameters** — See [Oracle Ingestion Parameters](#oracle-ingestion-parameters) below

Use `references/ops-parameters-main.md` for configuration commands.

### 5. Asset Uploads

No JDBC driver upload is required for Oracle. The connector uses the Oracle OCI driver which is bundled.

### 6. Verify Controllers

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_processors=false
```

**If verification fails:** Fix parameter configuration (connection URL, credentials) before proceeding.

### 7. Enable Controllers

**Load** `references/ops-flow-lifecycle.md` (Enable Controllers Only section).

After enabling, check for errors:
- All controllers show `ENABLED`
- Check bulletins for Oracle connection or authentication errors

### 8. Verify Processors

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_controllers=false
```

### 9. Verify XStream Connectivity (Oracle-Specific)

After processor verification passes, run a targeted single-processor verification on the CaptureChangeOracle processor. This triggers the processor's internal XStream health checks — it queries `dba_capture`, `V$LOGMNR_SESSION`, and `V$XSTREAM_CAPTURE` to confirm the XStream Outbound Server is reachable and healthy **before** starting the flow. See `references/ops-config-verification.md` for background on single-component verification.

```python
import nipyapi
nipyapi.profiles.switch()

# Find the CaptureChangeOracle processor
processors = nipyapi.canvas.list_all_processors("<pg-id>")
capture_proc = [p for p in processors if "CaptureChangeOracle" in p.component.type][0]

# Run single-processor verification (processor must be STOPPED)
results = nipyapi.canvas.verify_processor(capture_proc)

# Check results
for r in results:
    print(f"{r.verification_step_name}: {r.outcome}")
    if r.outcome == "FAILED":
        print(f"  Reason: {r.explanation}")
```

**If verification fails**, the XStream server is not reachable or not configured correctly. Common causes:
- XStream Outbound Server not started — run `SELECT STATUS FROM dba_capture WHERE CLIENT_NAME = '<xstream_server_name>';` on the Oracle database
- LogMiner session not active — check `V$LOGMNR_SESSION`
- Network connectivity — the SPCS container cannot reach the Oracle host on the OCI port
- Wrong XStream Out Server Name parameter — verify it matches the actual server name in Oracle

Do not proceed to Start until this verification passes.

### 10. Start

**Load** `references/ops-flow-lifecycle.md` for starting the flow.

### 11. Validate

After starting, validate data is flowing. See [Validate Data Flow](#validate-data-flow) below.

---

## Oracle Source Parameters

**Sensitive values:** Passwords are marked (sensitive). Ask user to provide directly. Never display these values — use `[REDACTED]` in confirmations.

| Parameter | Required | Description |
|-----------|----------|-------------|
| Oracle Connection URL | Yes | JDBC URL to the PDB holding the data. Example: `jdbc:oracle:thin:@//host:1521/YOUR_PDB_NAME`. Must point to the **PDB** (not the CDB root). For **non-CDB**, use the database service name (e.g., `jdbc:oracle:thin:@//host:1521/ORCL`). |
| Oracle Username | Yes | Username of the connect user with XStream Server access (e.g., `c##connectuser`). |
| Oracle Password | Yes | Password of the connect user (sensitive). |
| XStream Out Server Name | Yes | Name of the XStream Outbound Server created in Oracle prerequisite Step 6. **There is no default — always ask the user.** The examples in this file use `XOUT1` as a placeholder; do not assume this is the actual name. |
| XStream Out Server URL | Yes | JDBC URL for the XStream connection. Must use OCI driver. **CDB architecture:** must point to the **CDB root service** (not the PDB) — XStream Outbound Servers are registered at CDB$ROOT, so connecting to a PDB causes ORA-26701. Example: `jdbc:oracle:oci:@host:1521/CDB_SERVICE_NAME`. For Oracle 23ai Free the CDB service is typically `FREE`; for other editions check `SELECT NAME FROM V$SERVICES WHERE CON_ID = 1`. **Non-CDB architecture:** use the same database service name as the Oracle Connection URL (e.g., `jdbc:oracle:oci:@host:1521/ORCL`). |
| Oracle Database Processor Cores | Embedded only | Number of physical processor cores on the source Oracle database. |
| Oracle Database Processor Multiplier | Embedded only | Oracle Processor Core Factor (e.g., `0.5` for Intel). See Oracle Processor Core Factor Table. |
| XStream Billing Acknowledgement | Embedded only | Confirmation of the licensing agreement. |

---

## Oracle Ingestion Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| Included Table Names | No* | Comma-separated fully-qualified table paths. Always uses three-part format: `DATABASE_NAME.SCHEMA.TABLE`. The `DATABASE_NAME` is the Oracle `GLOBAL_DB_NAME` — for CDB this is the PDB name, for non-CDB it is the database name. Example: `FREEPDB1.SALES.CUSTOMERS, FREEPDB1.SALES.ORDERS` |
| Included Table Regex | No* | Regex to match fully-qualified table paths (three-part format). Example: `FREEPDB1\.SALES\..*` to match all tables in the SALES schema within the FREEPDB1 database. |
| Filter JSON | No | JSON array to include specific columns based on regex for given tables. |
| Merge Task Schedule CRON | No | CRON expression for merge operations. Example: `* * * * * ?` for continuous merge. |
| Object Identifier Resolution | No | `Default, case-insensitive` (recommended — uppercases all identifiers) or `case-sensitive` (preserves case, requires double quotes in SQL). **Do not change after ingestion has begun.** |
| Snapshot Fetching Strategy | No | `SEQUENTIAL_BY_PRIMARY_KEY` (default) or `CONCURRENT_BY_ROWID` (parallel fetching for large tables). |
| Ingestion Type | No | `full` (default — snapshot then incremental) or `incremental` (skip snapshot, useful for reinstalling over existing data). |

*One of Included Table Names or Included Table Regex is required.

**CRITICAL — Table Name Format:** Oracle tables must always be specified using the **three-part** fully-qualified format: `DATABASE_NAME.SCHEMA_NAME.TABLE_NAME`. This differs from other CDC connectors which use two-part names. The `DATABASE_NAME` is determined by Oracle's `GLOBAL_DB_NAME` property:

```sql
SELECT property_value FROM database_properties WHERE property_name = 'GLOBAL_DB_NAME';
```

- **CDB (multi-tenant):** The `DATABASE_NAME` is the **PDB name** (e.g., `FREEPDB1`). Run the query from within the PDB.
- **Non-CDB (single-tenant):** The `DATABASE_NAME` is the **database name** (e.g., `ORCL`). The same three-part format applies.

**Gotcha:** Some databases return a name with a domain suffix (e.g., `FOO.EXAMPLE.COM` instead of just `FOO`). If this happens, the full domain-qualified name must be used and **double-quoted** in the table name specification because it contains dots.

**Snowflake schema naming:** The connector maps the three-part name to a Snowflake schema by joining the database name and schema with an underscore. For example, tables in `FREEPDB1.PROCUREMENT` land in Snowflake schema `FREEPDB1_PROCUREMENT`.

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
-- Check schema exists
SHOW SCHEMAS IN DATABASE <destination_database>;

-- Check tables exist
SHOW TABLES IN SCHEMA <destination_database>.<schema>;

-- Validate rows appearing
SELECT COUNT(*) FROM <destination_database>.<schema>.<table>;
```

### Step 3: Check Table Replication State

In the Openflow runtime canvas, right-click a processor group >> **Controller Services** >> find **Table State Store** >> click **More** >> **View State**.

| State | Meaning |
|-------|---------|
| `NEW` | Scheduled for replication, not started |
| `SNAPSHOT_REPLICATION` | Copying initial data |
| `INCREMENTAL_REPLICATION` | Streaming real-time changes |
| `FAILED` | Permanent failure (see Troubleshooting) |

State changes are logged: `Replication state for table <db>.<schema>.<table> changed from <old> to <new>`

---

## Troubleshooting

For symptom-based fixes — table not appearing in Snowflake, no changes in incremental load, XStream errors (`ORA-26701`, `ORA-26812`, `ORA-21560`, `ORA-01722`), SCN diagnostics, restarting failed table replication, and the `StandardPrivateKeyService` INVALID known issue:

**Load** [`connector-oracle/connector-oracle-troubleshooting.md`](connector-oracle/connector-oracle-troubleshooting.md)

---

## Incremental Replication Without Snapshots

For reinstalling the connector over previously replicated data, you can skip the snapshot phase.

**On a new connector:** Set `Ingestion Type` to `incremental` in Oracle Ingestion Parameters before adding tables.

**On an existing connector:** Change `Ingestion Type` from `full` to `incremental`, then add new tables. Existing in-progress tables are not affected.

**Important:**
- Return `Ingestion Type` to `full` once incremental-only needs are satisfied, to ensure future tables get full snapshots.
- In incremental mode, the connector creates the destination table via `CREATE TABLE IF NOT EXISTS` only if no destination table exists.

---

## Next Step

After deployment and configuration, return to `references/connector-main.md` or the calling workflow.

## See Also

- [Set up the Openflow Connector for Oracle](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/oracle/about) — Official Snowflake documentation
- [`connector-oracle/connector-oracle-licensing.md`](connector-oracle/connector-oracle-licensing.md) — Licensing eligibility, comparison, lifecycle, and ORGADMIN commercial terms
- [`connector-oracle/connector-oracle-database-setup.md`](connector-oracle/connector-oracle-database-setup.md) — Oracle database prerequisites (Steps 1-8) and DBA best practices
- [`connector-oracle/connector-oracle-troubleshooting.md`](connector-oracle/connector-oracle-troubleshooting.md) — Symptom-based troubleshooting, XStream errors, SCN diagnostics
- `references/connector-main.md` — Connector workflow overview
- `references/ops-parameters-main.md` — Parameter configuration
- `references/ops-snowflake-auth.md` — Snowflake destination authentication
- `references/platform-eai.md` — Network access for database connectivity
- `references/ops-component-state.md` — Inspect and clear table replication state
- `references/ops-flow-lifecycle.md` — Start, stop, monitor
- `references/ops-config-verification.md` — Configuration verification (single-component and batch)
