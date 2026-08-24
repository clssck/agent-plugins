---
name: openflow-connector-oracle-database-setup
description: Oracle database prerequisites for the Oracle CDC connector — ARCHIVELOG mode, XStream + supplemental logging, XStream administrator user and privileges, connect user, XStream Outbound Server creation and wiring. Also covers DBA best practices for safe XStream deployment under production OLTP workloads. Loaded from connector-oracle.md when performing Oracle-side setup or reviewing production deployment guidance.
---

# Oracle CDC Connector — Database Setup

Loaded from [`connector-oracle.md`](../connector-oracle.md) when performing Oracle-side prerequisites or reviewing DBA best practices.

## Scope

This reference covers:
- Determining CDB vs non-CDB architecture (drives all user and privilege decisions below)
- Steps 1-8: the complete Oracle database prerequisite sequence
- DBA best practices for safe XStream deployment under production OLTP workloads

For Snowflake-side prerequisites, connector parameters, and the deployment workflow, return to [`connector-oracle.md`](../connector-oracle.md).

---

## Oracle Database Prerequisites

These steps must be completed by the **Oracle database administrator** before the connector can be configured.

**Note:** How you set up your Oracle database depends on your organization's security policies and database architecture (CDB, PDB, or combination). The instructions below are examples. Modify as required for your environment.

**Before starting, determine your Oracle architecture:**

```sql
SELECT CDB FROM V$DATABASE;
```

- **YES** → Multi-tenant (CDB with PDBs). Follow the CDB instructions below. Users require the `C##` prefix and `CONTAINER=ALL`.
- **NO** → Single-tenant (non-CDB). Follow the non-CDB alternatives noted in each step. Users are regular database users (no `C##` prefix). Both `Oracle Connection URL` and `XStream Out Server URL` point to the same database service.

### Step 1: Configure Archived Redo Log Retention

You must enable ARCHIVELOG mode to ensure change data is available for replication.

**Verify ARCHIVELOG mode:**

```sql
SELECT LOG_MODE, FORCE_LOGGING FROM V$DATABASE;
```

**For AWS RDS (Standard):**

```sql
BEGIN
  rdsadmin.rdsadmin_util.set_configuration(
    name  => 'archivelog retention hours',
    value => '24'
  );
END;
/
COMMIT;
```

**For AWS RDS Custom:**

Create `/opt/aws/rdscustomagent/config/redo_logs_custom_configuration.json`:
```json
{"archivedLogRetentionHours": "24"}
```

Determine the retention period based on the volume of changes in your source database and your storage capacity.

### Step 2: Enable XStream and Supplemental Logging

XStream is included with Oracle Database and does not require additional software.

**Enable XStream replication:**

```sql
ALTER SYSTEM SET enable_goldengate_replication=TRUE SCOPE=BOTH;
ALTER SYSTEM SET STREAMS_POOL_SIZE = 2560M;
```

Snowflake recommends setting the streams pool size to **2.5 GB** (1 GB for Capture + 1 GB for Apply + 25% buffer).

**Enable supplemental logging:**

Snowflake recommends forcing logging on the database or tablespace level:

**CDB architecture:**

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
```

**Non-CDB architecture:**

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
```

Alternatively, enable logging only on specific tables (recommended for production — see [DBA Best Practices](#dba-best-practices)):

```sql
ALTER TABLE schema_name.table_name ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
```

### Step 3: Create the XStream Administrator User

An XStream administrator user is required to manage XStream components.

**CDB architecture:**

The following example creates a dedicated common user in the root container of a CDB with a PDB.

```sql
-- Switch to root container
ALTER SESSION SET CONTAINER = CDB$ROOT;

-- Create tablespace for XStream admin in CDB
CREATE TABLESPACE xstream_adm_tbs DATAFILE '/path/to/your/cdb/xstream_adm_tbs.dbf'
  SIZE 25M REUSE AUTOEXTEND ON MAXSIZE UNLIMITED;

-- Create tablespace in PDB
ALTER SESSION SET CONTAINER = YOUR_PDB_NAME;
CREATE TABLESPACE xstream_adm_tbs DATAFILE '/path/to/your/pdb/xstream_adm_tbs.dbf'
  SIZE 25M REUSE AUTOEXTEND ON MAXSIZE UNLIMITED;

-- Switch back to root and create common user
ALTER SESSION SET CONTAINER = CDB$ROOT;

CREATE USER c##xstreamadmin IDENTIFIED BY "YOUR_XSTREAM_ADMIN_PASSWORD"
  DEFAULT TABLESPACE xstream_adm_tbs
  QUOTA UNLIMITED ON xstream_adm_tbs
  CONTAINER=ALL;
```

Note: The `c##` prefix indicates a common user in a CDB environment. `CONTAINER=ALL` grants privileges across all containers.

**Non-CDB architecture:**

```sql
CREATE TABLESPACE xstream_adm_tbs DATAFILE '/path/to/your/xstream_adm_tbs.dbf'
  SIZE 25M REUSE AUTOEXTEND ON MAXSIZE UNLIMITED;

CREATE USER xstreamadmin IDENTIFIED BY "YOUR_XSTREAM_ADMIN_PASSWORD"
  DEFAULT TABLESPACE xstream_adm_tbs
  QUOTA UNLIMITED ON xstream_adm_tbs;
```

Note: No `C##` prefix or `CONTAINER=ALL` in a non-CDB environment.

### Step 4: Grant XStream Administrator Privileges

**CDB architecture — Oracle Database 19c and 21c:**

```sql
GRANT CREATE SESSION, SET CONTAINER, EXECUTE ANY PROCEDURE, LOGMINING
  TO c##xstreamadmin CONTAINER=ALL;

BEGIN
  DBMS_XSTREAM_AUTH.GRANT_ADMIN_PRIVILEGE(
    grantee                => 'c##xstreamadmin',
    privilege_type         => 'CAPTURE',
    grant_select_privileges => TRUE,
    container              => 'ALL'
  );
END;
/
```

**CDB architecture — Oracle Database 23c:**

```sql
GRANT CREATE SESSION, SET CONTAINER, EXECUTE ANY PROCEDURE, LOGMINING, XSTREAM_CAPTURE
  TO c##xstreamadmin CONTAINER=ALL;
```

**Non-CDB architecture — Oracle Database 19c and 21c:**

```sql
GRANT CREATE SESSION, EXECUTE ANY PROCEDURE, LOGMINING
  TO xstreamadmin;

BEGIN
  DBMS_XSTREAM_AUTH.GRANT_ADMIN_PRIVILEGE(
    grantee                => 'xstreamadmin',
    privilege_type         => 'CAPTURE',
    grant_select_privileges => TRUE
  );
END;
/
```

**Non-CDB architecture — Oracle Database 23c:**

```sql
GRANT CREATE SESSION, EXECUTE ANY PROCEDURE, LOGMINING, XSTREAM_CAPTURE
  TO xstreamadmin;
```

### Step 5: Configure XStream Server Connect User

The connect user establishes a connection to the XStream Outbound Server and receives change data. This user needs:

- Read from XStream Outbound Server
- SELECT on data dictionary views (`ALL_USERS`, `ALL_TABLES`, `ALL_TAB_COLS`, `ALL_CONS_COLUMNS`, `ALL_CONSTRAINTS`, `V$DATABASE`)
- SELECT on all source tables to be replicated

**CDB architecture:**

```sql
ALTER SESSION SET CONTAINER = CDB$ROOT;

CREATE USER c##connectuser IDENTIFIED BY "YOUR_CONNECT_USER_PASSWORD"
  CONTAINER=ALL;

GRANT CREATE SESSION, SELECT_CATALOG_ROLE TO c##connectuser CONTAINER=ALL;
GRANT SELECT ANY TABLE TO c##connectuser CONTAINER=ALL;
GRANT LOCK ANY TABLE TO c##connectuser CONTAINER=ALL;
```

**Non-CDB architecture:**

```sql
CREATE USER connectuser IDENTIFIED BY "YOUR_CONNECT_USER_PASSWORD";

GRANT CREATE SESSION, SELECT_CATALOG_ROLE TO connectuser;
GRANT SELECT ANY TABLE TO connectuser;
GRANT LOCK ANY TABLE TO connectuser;
```

For more granular control, grant SELECT on specific tables instead of `SELECT ANY TABLE`.

### Step 6: Create XStream Outbound Server

The XStream Outbound Server captures changes from redo logs. Define which schemas or tables to replicate.

**Important:**
- A table in the XStream filtering rules must **also** be listed in the connector's ingestion parameters to be replicated.
- You can include an entire schema here and later specify only certain tables in the connector parameters.
- In a CDB, the Outbound Server can only be created from the root container (except Oracle 23ai which supports PDB-level creation).
- The `CREATE_OUTBOUND` command is the same for both CDB and non-CDB architectures. The only CDB-specific parameter is `source_container_name` (used to scope capture to a specific PDB).
- **Be selective** in production. Capturing everything impacts CPU, network, and queue performance. Use `DBMS_XSTREAM_ADM.ADD_TABLE_RULES` for granular table selection.

**Example 1: Capture all tables from all schemas (CDB: root + all PDBs; non-CDB: entire database):**

```sql
SET SERVEROUTPUT ON;
DECLARE
  tables  DBMS_UTILITY.UNCL_ARRAY;
  schemas DBMS_UTILITY.UNCL_ARRAY;
BEGIN
  tables(1)  := NULL;
  schemas(1) := NULL;
  DBMS_XSTREAM_ADM.CREATE_OUTBOUND(
    server_name  => 'XOUT1',
    table_names  => tables,
    schema_names => schemas,
    include_ddl  => TRUE
  );
  DBMS_OUTPUT.PUT_LINE('XStream Outbound Server created.');
EXCEPTION
  WHEN OTHERS THEN
    DBMS_OUTPUT.PUT_LINE('Error: ' || SQLERRM);
    RAISE;
END;
/
```

**Example 2: Capture all tables from a single schema in a specific PDB (CDB only):**

```sql
SET SERVEROUTPUT ON;
DECLARE
  tables  DBMS_UTILITY.UNCL_ARRAY;
  schemas DBMS_UTILITY.UNCL_ARRAY;
BEGIN
  tables(1)  := NULL;
  schemas(1) := 'schema_name';
  DBMS_XSTREAM_ADM.CREATE_OUTBOUND(
    server_name            => 'XOUT1',
    table_names            => tables,
    schema_names           => schemas,
    include_ddl            => TRUE,
    source_container_name  => 'YOUR_PDB_NAME'
  );
  DBMS_OUTPUT.PUT_LINE('XStream Outbound Server created.');
EXCEPTION
  WHEN OTHERS THEN
    DBMS_OUTPUT.PUT_LINE('Error: ' || SQLERRM);
    RAISE;
END;
/
```

### Step 7: Set Up the XStream Outbound Server Connect User

Associate the connect user with the Outbound Server:

**CDB architecture:**

```sql
BEGIN
  DBMS_XSTREAM_ADM.ALTER_OUTBOUND(
    server_name  => 'XOUT1',
    connect_user => 'c##connectuser'
  );
END;
/
```

**Non-CDB architecture:**

```sql
BEGIN
  DBMS_XSTREAM_ADM.ALTER_OUTBOUND(
    server_name  => 'XOUT1',
    connect_user => 'connectuser'
  );
END;
/
```

Note: The connect user name must match exactly what was created in Step 5 — with `C##` prefix for CDB, without for non-CDB.

### Step 8: Set Up the XStream Outbound Server Capture User (Optional)

If you configured a separate capture user, associate it with the Outbound Server. Skip this step if you want data captured by the user who created the server (the administrator).

```sql
BEGIN
  DBMS_XSTREAM_ADM.ALTER_OUTBOUND(
    server_name  => 'XOUT1',
    capture_user => 'yourcaptureuser'
  );
END;
/
```

---

## DBA Best Practices

These recommendations are based on stress-testing Oracle XStream under high-throughput OLTP workloads. They help DBAs enable CDC safely without risking production stability.

### 1. Check I/O Headroom First

Before enabling CDC, check current `log_file_sync` waits:

- If you are already seeing **>5-10ms** waits regularly, **solve your storage I/O bottleneck first**.
- CDC adds redo volume (approximately 1.5x), not latency — but volume becomes latency if the pipe is full.
- The cost of CDC is primarily in **I/O, not CPU**. CPU overhead from XStream itself is negligible (~3%).

### 2. Resize Your Redo Logs

Legacy 500 MB Redo Log files will be insufficient.

- **Recommendation:** Increase Online Redo Log size to **4 GB - 8 GB**.
- **Why:** With increased redo volume from supplemental logging, small logs cause frequent log switching (checkpoints), which pauses the database.

### 3. Set STREAMS_POOL_SIZE (Safety Valve)

Do not let Oracle manage this automatically via the Shared Pool. Isolate XStream memory.

- **Recommendation:** Allocate a dedicated `STREAMS_POOL_SIZE` of **2.5 GB** (already set in Step 2 above).
- **Why:** This acts as a circuit breaker. If the replication pipeline slows or transaction volume spikes, the pool fills and XStream pauses. It will **not** eat into the Buffer Cache or crash the instance — it will simply lag. This prioritizes OLTP stability over replication latency.

### 4. Use Surgical Logging, Not Database-Wide

In production, do **not** run `ALTER DATABASE ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS` on the entire database.

- **Recommendation:** Enable supplemental logging only on specific tables being replicated:

```sql
ALTER TABLE schema_name.table_name ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
```

- **Why:** The connector requires ALL columns to be logged to fully reconstruct the payload, but this should be applied surgically to the tables in scope only.

### 5. Monitor XStream Health

Use these views to ensure XStream is healthy and respecting resource boundaries:

| View | What to Check | Healthy State |
|------|---------------|---------------|
| `V$XSTREAM_CAPTURE` | `STATE` and `LATENCY_SECONDS` | `CAPTURING CHANGES`, low latency |
| `V$STREAMS_POOL_STATISTICS` | `TOTAL_MEMORY_ALLOCATED` | Below `STREAMS_POOL_SIZE` cap |
| `V$XSTREAM_OUTBOUND_SERVER` | Connection state | `SENDING CHANGES` |

### 6. Consider Downstream Capture for Extreme Scale

If your production database runs at **>80% CPU** consistently or generates massive redo volumes (1 TB+ daily), running any additional process is a risk.

- **Recommendation:** Use the **Downstream Capture** model — ship redo logs to a secondary, passive Oracle instance where XStream runs.
- **Result:** Zero CPU or memory footprint on the production source. The only impact is network bandwidth for log shipping.

---

Return to [`connector-oracle.md`](../connector-oracle.md).
