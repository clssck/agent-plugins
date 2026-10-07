---
name: openflow-connector-oracle-troubleshooting
description: Symptom-based troubleshooting for the Oracle CDC connector — table not appearing in Snowflake, no changes in incremental load, XStream errors (ORA-26701, ORA-26812, ORA-21560, ORA-01722), SCN diagnostics, restarting failed table replication, and the StandardPrivateKeyService INVALID known issue. Loaded from connector-oracle.md when diagnosing a failure.
---

# Oracle CDC Connector — Troubleshooting

Loaded from [`connector-oracle.md`](../connector-oracle.md) when diagnosing an Oracle connector failure.

## Scope

This reference covers:
- Known issues specific to the Oracle connector
- Symptom-based troubleshooting: missing tables, no incremental changes, XStream errors
- SCN diagnostics for capture bottleneck analysis
- Restarting table replication after a `FAILED` state

For deployment workflow, parameters, and Oracle database setup, return to [`connector-oracle.md`](../connector-oracle.md).

---

## Known Issues

### StandardPrivateKeyService INVALID on SPCS or BYOC with Managed Token

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID. Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

### Table Added but Doesn't Appear in Snowflake

1. **Check FQN format** in Oracle Ingestion Parameters. It must be `DATABASE_NAME.SCHEMA_NAME.TABLE_NAME` (three-part with database prefix).

2. **Verify the database name.** The connector uses the value from:

```sql
SELECT property_value FROM database_properties WHERE property_name = 'GLOBAL_DB_NAME';
```

Some databases return a domain-suffixed name (e.g., `FOO.EXAMPLE.COM` instead of `FOO`). The full name must be used and double-quoted.

3. **Data must reside in the same database instance** as the one specified in Oracle Connection URL. Cross-database replication within a single connector instance is not supported.

### No Changes in Incremental Load

Walk through these checks in order:

**1. Check XStream capture process status:**

```sql
SELECT CLIENT_NAME, STATUS, ERROR_MESSAGE FROM ALL_CAPTURE;
```

The status should be `ENABLED`.

- **If `DISABLED`:** The capture was stopped manually or the database was restarted. Restart it:

```sql
BEGIN
  DBMS_XSTREAM_ADM.START_OUTBOUND('<xstream_server_name>');
END;
/
```

- **If `ABORTED` with `ORA-01031: insufficient privileges`:** Redo logs needed for capture have been deleted. Start the outbound server (same command as above).

**2. Check logminer session status:**

```sql
SELECT SESSION_STATE
FROM V$LOGMNR_SESSION
WHERE SESSION_NAME = (
  SELECT CAPTURE_NAME FROM ALL_CAPTURE WHERE CLIENT_NAME = '<xstream_server_name>'
);
```

Status should be `ACTIVE`. If `UNKNOWN`, archived logs that logminer depended on were deleted. Verify:

```sql
SELECT * FROM V$ARCHIVED_LOG ORDER BY RECID;
```

Check the `DELETED` column for value `YES`.

**3. Check XStream capture state:**

```sql
SELECT STATE
FROM V$XSTREAM_CAPTURE
WHERE CAPTURE_NAME = (
  SELECT CAPTURE_NAME FROM ALL_CAPTURE WHERE CLIENT_NAME = '<xstream_server_name>'
);
```

- `CAPTURING CHANGES` or `WAITING FOR TRANSACTION` — Normal. If large redo volume, logminer may take time to catch up.
- `WAITING FOR REDO: FILE NA, THREAD X, SEQUENCE Y, SCN Z` — Logminer is waiting for an archived log file that was deleted.

**4. Verify XStream rules include target schemas/tables:**

```sql
SELECT STREAMS_NAME, SCHEMA_NAME, OBJECT_NAME, RULE_TYPE
FROM DBA_XSTREAM_RULES
WHERE STREAMS_NAME = '<xstream_server_name>';
```

### XStream Errors

**`ORA-21560: argument last_position is null, invalid, or out of range`**
The connector attempted to connect to an SCN position for which redo logs are no longer available. Redo log retention must be increased.

**`ORA-26701: Streams process <name> does not exist`**
Verify that:
- **CDB architecture:** The `XStream Out Server URL` points to the **CDB root service** (e.g., `jdbc:oracle:oci:@host:1521/FREE`), **not** the PDB. XStream Outbound Servers are registered at CDB$ROOT; connecting to a PDB will fail with this error even if the Outbound Server exists. To find the CDB root service name: `SELECT NAME FROM V$SERVICES WHERE CON_ID = 1;`
- **Non-CDB architecture:** The `XStream Out Server URL` should use the same database service name as the `Oracle Connection URL`. Both URLs point to the same instance.
- The XStream Outbound Server has been created on this instance with the expected name. Verify: `SELECT SERVER_NAME, CONNECT_USER, CAPTURE_NAME, SOURCE_DATABASE FROM DBA_XSTREAM_OUTBOUND;`
- In a CDB, the `Oracle Connection URL` (thin driver) should still point to the **PDB** — only the XStream OCI URL needs to point to CDB root.

**`ORA-26812: An active session currently attached to XStream server "<name>"`**
XStream allows only one client attached to an Outbound Server at a time. This error occurs when:
- A previous connector instance was stopped but its Oracle session was not released cleanly (common with ungraceful shutdowns or network disconnects).
- Two connector instances are trying to use the same XStream Outbound Server simultaneously.

To resolve:
1. Identify the stale session:
   ```sql
   SELECT SID, SERIAL#, USERNAME, PROGRAM, STATUS
   FROM V$SESSION
   WHERE USERNAME = '<connect_user>';
   ```
2. Kill the stale session:
   ```sql
   ALTER SYSTEM KILL SESSION 'SID,SERIAL#' IMMEDIATE;
   ```
3. If the session persists, wait for Oracle's dead connection detection (DCD) timeout to expire, or restart the Oracle listener.

**`ORA-01722: invalid number` when executing `DBMS_XSTREAM_ADM.CREATE_OUTBOUND`**
This misleading error typically means the outbound server **already exists**. Check:

```sql
SELECT * FROM ALL_XSTREAM_OUTBOUND WHERE SERVER_NAME = '<xstream_server_name>';
```

### SCN Diagnostics

Use this query to compare SCN values across capture, logminer, and database. Large gaps between consecutive SCN values indicate where bottlenecks exist:

```sql
WITH scn_values AS (
  SELECT 'CAPTURE' AS source, scn_type, scn_value,
    CASE scn_type
      WHEN 'FIRST_SCN' THEN 'Lowest SCN for capture restart'
      WHEN 'START_SCN' THEN 'SCN from which capture starts'
      WHEN 'CAPTURED_SCN' THEN 'Last redo log record scanned'
      WHEN 'LAST_ENQUEUED_SCN' THEN 'Last enqueued SCN'
      WHEN 'APPLIED_SCN' THEN 'Most recent dequeued SCN'
      WHEN 'REQUIRED_CHECKPOINT_SCN' THEN 'Lowest checkpoint SCN needing redo'
      WHEN 'MAX_CHECKPOINT_SCN' THEN 'Last checkpoint SCN'
    END AS description
  FROM all_capture
  UNPIVOT (
    scn_value FOR scn_type IN (
      first_scn, start_scn, captured_scn, last_enqueued_scn,
      applied_scn, required_checkpoint_scn, max_checkpoint_scn
    )
  )
  UNION ALL
  SELECT 'LOGMINER', scn_type, scn_value,
    CASE scn_type
      WHEN 'RESET_SCN' THEN 'SCN when session started'
      WHEN 'PROCESSED_SCN' THEN 'Builder mined redo up to this SCN'
      WHEN 'PREPARED_SCN' THEN 'Preparers transformed redo to LCRs below this SCN'
      WHEN 'READ_SCN' THEN 'Reader read all redo below this SCN'
      WHEN 'LOW_MARK_SCN' THEN 'All committed txns below this SCN delivered'
      WHEN 'CONSUMED_SCN' THEN 'Client consumed all txns below this SCN'
      WHEN 'SPILL_SCN' THEN 'On restart, redo below this SCN skipped'
    END AS description
  FROM V$LOGMNR_SESSION
  UNPIVOT (
    scn_value FOR scn_type IN (
      RESET_SCN, PROCESSED_SCN, PREPARED_SCN, READ_SCN,
      LOW_MARK_SCN, CONSUMED_SCN, SPILL_SCN
    )
  )
  UNION ALL
  SELECT 'DB', 'CURRENT_SCN', CURRENT_SCN, 'Current system change number'
  FROM V$DATABASE
)
SELECT source, scn_type, scn_value,
       scn_value - LAG(scn_value) OVER (ORDER BY scn_value) AS diff,
       description
FROM scn_values
ORDER BY scn_value, scn_type;
```

### Restart Table Replication

If a table enters `FAILED` state:

1. **Remove the table** from Ingestion Parameters (Included Table Names or adjust regex).
2. **Wait** until the table's state is fully removed from the Table State Store. **Do not proceed until complete.**
3. **DROP the destination table** in Snowflake. The connector will not overwrite an existing table during snapshot.
4. **Optionally** remove the journal table and stream.
5. **Re-add the table** to Ingestion Parameters.
6. **Verify** the table appears with status `NEW` → `SNAPSHOT_REPLICATION` → `INCREMENTAL_REPLICATION`.

---

Return to [`connector-oracle.md`](../connector-oracle.md).
