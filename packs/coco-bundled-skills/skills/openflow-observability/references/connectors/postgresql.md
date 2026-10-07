---
name: openflow-observability-connector-postgresql
description: PostgreSQL connector troubleshooting and SPCS domain allowlist.
---

# PostgreSQL CDC

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/postgres/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/postgres/setup)
- [Data mapping](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/postgres/data-mapping)
- [Incremental replication](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/postgres/incremental-replication)
- [Maintenance](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/postgres/maintenance)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
| --- | --- |
| `<customer-db-host>:<port>` | Customer-specific. Default port: 5432. |

## Parameters & Required Assets

The PostgreSQL connector uses three parameter contexts. Key parameters from the [official setup documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/postgres/setup):

### Source Parameters

| Parameter | Description | Notes |
| --- | --- | --- |
| `Database Hostname` | PostgreSQL server host | Required |
| `Database Port` | PostgreSQL server port | Default: `5432` |
| `Database User` | Connection username | Must have REPLICATION attribute and SELECT on tables |
| `Database Password` | Connection password | Required |
| `Database Name` | Source database name | Required |
| `PostgreSQL JDBC Driver` | JDBC driver JAR | **Must upload as Reference asset** (see below) |
| `Publication Name` | PostgreSQL publication name | Must match the publication created on the source DB |
| `Replication Slot Name` | Logical replication slot name | The connector creates this automatically if not existing |
| `Database SSL Connection` | Enable SSL | Optional; if enabled, upload root certificate |
| `Database Root Certificate` | SSL root certificate | Required only when SSL is enabled |

### Destination Parameters

See [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters).

### Ingestion Parameters

| Parameter | Description | Notes |
| --- | --- | --- |
| `Included Table Names` | Tables to replicate | Format: `<schema>.<table>` |
| `Included Table Regex` | Regex pattern for tables | Alternative to explicit table list |
| `Object Identifier Resolution` | Case sensitivity | `CASE_SENSITIVE` or `CASE_INSENSITIVE` |
| `Skip Snapshot` | Skip initial full load | Set to `true` to start from current WAL position (useful for reinstallation) |

### JDBC Driver Asset Upload

The PostgreSQL JDBC driver must be uploaded as a parameter context asset. See [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) for upload steps, diagnosis queries, and resolution.

### PostgreSQL 15+ Column Filtering Warning

> **Warning:** If using PostgreSQL 15 or later with column-filtered publications (e.g., `CREATE PUBLICATION ... FOR TABLE t (col1, col2)`), all columns included in the publication must also be covered by the table's REPLICA IDENTITY.
> If a column in the publication is not part of the REPLICA IDENTITY, UPDATE and DELETE operations may fail or produce incorrect results in the destination.

### SSL Configuration

For SSL configuration, see [SSL Configuration (Database Connectors)](connector-shared-generic.md#ssl-configuration-database-connectors).

> **Generalized: the `Cannot create PoolableConnectionFactory` wrapper.** This same wrapped error surfaces for ANY postgres JDBC connection failure -- DNS unknown-host, TCP refused, TLS handshake failure, auth rejected, all wrap into this same outer exception. The actual root cause is in the inner exception. **Always read `throwable.cause.className` and `throwable.cause.message` from the event-table log row** to diagnose. Common inner causes:
> - `java.net.UnknownHostException` -> bad hostname in `Source Database Connection URL` (DNS lookup failure)
> - `java.net.ConnectException: Connection refused` -> right host, wrong port, or postgres not listening / firewall blocking
> - `java.net.SocketTimeoutException` -> network path slow or blocked (egress / EAI / security group)
> - `javax.net.ssl.SSLHandshakeException` / `CertPathValidatorException` -> SSL certificate or trust failure; check the JDBC SSL mode before treating RDS CA trust as the root cause
> - `org.postgresql.util.PSQLException: FATAL: password authentication failed` -> wrong password or user
> - `org.postgresql.util.PSQLException: FATAL: no pg_hba.conf entry` -> postgres-side IP allowlist rejecting the runtime's egress IP
>
> Note: the `extendedStackTrace` field on the event-table row is frequently NULL for postgres JDBC wrapped exceptions -- `throwable.cause.className`/`throwable.cause.message` is the canonical drill-down path.

## Troubleshooting

### Missing Primary Key

**Pattern:** Table routed to "Mark Table Replication Failed" with no exception. The flow file was routed through the "no primary key" relationship.

**Likely Cause:** CDC connectors require every replicated table to have a primary key. Tables without a primary key are immediately failed.

**Recommended Action:** The customer needs to add a primary key to the source table. **Note:** earlier guidance suggested `REPLICA IDENTITY FULL` as a substitute for a PK, but **the current postgres CDC connector version explicitly REJECTS `REPLICA IDENTITY FULL`** with the warning:

> `Table "<schema>"."<table>" has REPLICA IDENTITY FULL which is not supported for CDC replication. No identity columns will be detected. Please set REPLICA IDENTITY to DEFAULT (with a primary key) or USING INDEX.`

The only valid identity options are:
- A primary key with `REPLICA IDENTITY DEFAULT` (the standard case)
- A unique non-deferrable index with `REPLICA IDENTITY USING INDEX <index_name>` (when adding a PK is impossible)

This is a customer DBA action -- the customer owns the source-side DDL fix. Do not suggest opening a Snowflake support case or escalating to Snowflake for a missing primary key. (The "Snowflake support" pointer further down applies only to the separate TOASTed-value problem.) Adding the PK does not resume the table on its own; it must go through the [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure.

If the table is already in `FAILED`, surface the canonical FAILED phrasing in the diagnosis: the table is in FAILED state and the customer must run the [Restart Table Replication] procedure. After adding the primary key, the table needs the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure. Do not summarize or improvise the restart steps.

---

### TOASTed Value Not Available

**Pattern:** Error message containing "TOASTed value" or "unchanged TOAST datum".

**Likely Cause:** PostgreSQL stores large column values in TOAST tables. With `REPLICA IDENTITY DEFAULT`, only the primary key columns are included in the WAL for UPDATE operations. When a non-key TOASTed column is not modified by an UPDATE, the connector cannot read its value.

**Recommended Action:** Earlier guidance recommended setting `REPLICA IDENTITY FULL` on the affected table so all columns are written to the WAL. **The current `OPENFLOW_POSTGRES_CDC` connector version explicitly rejects `REPLICA IDENTITY FULL`** (see [Missing Primary Key](#missing-primary-key) above for the rejection warning), so this workaround is not currently usable. There is no documented connector-side workaround for unchanged TOAST values in the SQL-managed connector at this time. If the customer is hitting this pattern, direct them to Snowflake support or the connector's official documentation for the current recommended path; do not propose `REPLICA IDENTITY FULL` from this skill.

After the source table is corrected, surface the canonical FAILED phrasing in the diagnosis: if the table is in `FAILED`, the customer must run the [Restart Table Replication] procedure. The table needs the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure. Do not summarize or improvise the restart steps.

---

### PostgreSQL Prerequisites

When a CDC connector is failing or not replicating data, verify that the source database prerequisites are correctly configured. Guide the customer through these checks.

Ask the customer to verify the following on their PostgreSQL server:

**1. WAL level must be `logical`:**
```sql
-- Run on the source PostgreSQL database
SHOW wal_level;
```
Expected: `logical`. If not, the customer must change this setting (requires a server restart). This is a customer DBA action.

**2. Publication exists and includes the target tables:**
```sql
-- Run on the source PostgreSQL database
SELECT * FROM pg_publication;
SELECT * FROM pg_publication_tables WHERE pubname = '<publication_name>';
```

If tables are missing from the publication, the customer needs to add them to the publication on their source database. This is a customer DBA action.

**If the publication exists but under a different name than the connector references:** the source side is fine; the connector's `Source Database Publication Name` is wrong. For SQL-managed connectors, the agent can update that single property via `connector.config_set_property` after confirmation -- see [Openflow SQL Action Candidates for CDC Config Errors](connector-shared-cdc.md#openflow-sql-action-candidates-for-cdc-config-errors). For BYOC or non-SQL-managed connectors, guide the customer to fix the value in the Openflow UI wizard.

**3. Replication slot is not lagging excessively:**
```sql
-- Run on the source PostgreSQL database
SELECT slot_name, active, restart_lsn, confirmed_flush_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)) AS lag
FROM pg_replication_slots;
```
A large lag value indicates the connector is not consuming changes fast enough, or has been stopped for too long. Unconsumed WAL grows until disk fills.

**4. REPLICA IDENTITY is set correctly:**
```sql
-- Run on the source PostgreSQL database
SELECT c.relname, c.relreplident
FROM pg_class c
JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = '<schema>' AND c.relname = '<table>';
```
- `d` = DEFAULT (primary key columns in WAL) -- **required** for SQL-managed `OPENFLOW_POSTGRES_CDC`. The table must also have a primary key (or unique non-deferrable index with `USING INDEX` set on it).
- `f` = FULL -- **rejected by the current SQL-managed connector** with `"has REPLICA IDENTITY FULL which is not supported for CDC replication"`. Tables on FULL must be rotated back to DEFAULT (with a PK or unique index) before they will replicate.
- `n` = NOTHING -- will not work with CDC.

**5. User has required privileges:**
```sql
-- Run on the source PostgreSQL database
SELECT rolname, rolreplication FROM pg_roles WHERE rolname = '<connector_user>';
```
The user must have the `REPLICATION` attribute and `SELECT` on all replicated tables.

If any of the above prerequisites are not met, describe the required configuration changes to the customer and make it clear that the fixes happen on the customer's PostgreSQL server. **Do NOT suggest restarting or reconfiguring the Openflow connector itself for prerequisite issues.** If a table has already entered `FAILED`, the source fix alone is not enough -- after the PostgreSQL prerequisite is corrected, use the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure for each affected failed table. A connector restart adds no value when the root cause is a missing source prerequisite.

---

### Binlog/WAL Lag

**Pattern:** No explicit errors, but data in Snowflake is significantly behind the source database.

**Snowsight Checks:** Check if the CDC engine is reading the change stream but falling behind:

Run the **Replication Lag** query from `references/connectors/connector-shared-cdc.md`.

**Recommended Action:** Check WAL size and replication slot lag on the source database. Ensure `max_wal_size` is appropriately configured. If WAL/slot position was lost and tables have fallen into `FAILED`, fix the PostgreSQL retention/state issue first.

High-traffic databases may also need a larger runtime.

Also check resource utilization -- use CPU Utilization by Pod and Memory Utilization by Pod from `references/core-queries-resource.md`. If the runtime is resource-constrained, guide the customer to resize the runtime to a larger size in the Openflow UI.

---

### Replication Slot WAL Pinning / Disk Fill

**Pattern:** Source PostgreSQL disk usage grows continuously. `pg_replication_slots` shows a slot with `active=false`, or `confirmed_flush_lsn` is not advancing despite the connector running. May also surface as connector errors such as `replication slot "..." does not exist` if the slot was dropped to recover disk space.

> **Production-critical risk:** An inactive or stalled replication slot pins WAL on the PostgreSQL server indefinitely. If unconsumed WAL fills the disk, the PostgreSQL instance shuts down. Act immediately when disk growth is reported and a slot shows `active=false`.

**Diagnostic queries (run on source PostgreSQL database):**

```sql
-- Check all replication slots: active status and WAL pinned
SELECT slot_name, active, restart_lsn, confirmed_flush_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS wal_pinned
FROM pg_replication_slots;

-- Check current WAL directory size
SELECT pg_size_pretty(sum(size)) FROM pg_ls_waldir();
```

Slots with `active=false` and a large `wal_pinned` value are the immediate risk. If `pg_ls_waldir()` is not available (e.g., on RDS), use the cloud provider's monitoring console for disk metrics.

**Root causes and recommended actions:**

**Orphaned slot (connector stopped or crashed):** A replication slot is *not* cleaned up automatically when a connector is stopped or removed; it must be dropped manually. **Drop it only when the connector is being permanently retired, or when disk pressure forces immediate action** -- dropping the slot discards the WAL position, so the connector can no longer resume and every table needs a full re-snapshot. If the connector is merely stopped, being reinstalled, or will otherwise be reused, do NOT drop the slot: prefer resuming/restarting the connector so it consumes the pinned WAL from where it left off (no re-snapshot). When dropping is the right call, auto-generated slots are prefixed `snowflake_connector_`:

```sql
-- Run on source PostgreSQL — only after confirming the connector is stopped
SELECT slot_name, active FROM pg_replication_slots;   -- identify the inactive slot
SELECT pg_drop_replication_slot('<slot_name>');       -- e.g. snowflake_connector_abc123
```

After dropping: restart the connector. All tables require [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) since the WAL position is lost.

**Slot active but `confirmed_flush_lsn` not advancing:** The connector is connected but not consuming WAL. Check resource utilization (CPU and memory via `references/core-queries-resource.md`). A resource-constrained runtime can stall consumption without dropping the connection. Guide the customer to resize to a larger runtime in the Openflow UI if constrained.

Setting `wal_receiver_timeout` on the source bounds how long an unresponsive replication connection can stay open before PostgreSQL closes it, which surfaces a stalled consumer rather than letting it silently pin WAL. The connector tolerates this: when it hits an error opening the replication stream it yields for ~90 seconds before retrying, so any `wal_receiver_timeout` under 90s (the `60s` default is fine) coexists with normal connector operation. This is a customer DBA setting; there is normally no need to change it, and it should be kept below 90s if adjusted.

**`max_wal_senders` exhausted:** If the source logs `FATAL: all replication slots are in use` or new replication connections fail, ask the customer DBA to check:

```sql
-- Run on source PostgreSQL database
SHOW max_wal_senders;
SELECT count(*) FROM pg_stat_replication;
```

If the active connection count is at or near the `max_wal_senders` limit, the customer DBA should increase the limit and set `wal_receiver_timeout` to reclaim stale connections faster.

**Slot lost after failover (RDS Multi-AZ, CloudNativePG, or other HA setups):** PostgreSQL logical replication slots are **not replicated to standbys**. After a primary failover, the slot does not exist on the new primary and the connector fails with `replication slot "..." does not exist`. Recovery:

1. If the primary endpoint changed, update `Source Database Connection URL` in the connector parameters.
2. All tables must go through [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) -- a full re-snapshot is unavoidable after slot loss.
3. **Prevention:** set an explicit `Replication Slot Name` in the connector parameters so the slot name is predictable. Note there is no hard "LSN mismatch" error: if a slot with the same name is recreated externally, the connector connects at a position on or after the slot, and a position earlier than the slot is silently adjusted forward, so replication resumes but **likely with a data gap**. Because that gap is silent, the safe recovery after an external slot recreation is to set a NEW `Replication Slot Name` (the connector creates a fresh slot and re-snapshots) rather than reusing the recreated slot.

**RDS: missing `rds_replication` role:** On Amazon RDS PostgreSQL, the connector user must have the `rds_replication` role to create and use logical replication slots:

```sql
-- Run on source RDS PostgreSQL database (DBA action)
GRANT rds_replication TO <connector_user>;
```

Without this grant, the connector cannot create or attach to the replication slot.

---

### Replication Stuck in NEW State (Hot Standby Replica)

If connecting to a hot standby replica and the `Read PostgreSQL CDC Stream` processor is not starting, the primary server may need to execute `pg_log_standby_snapshot()` to force the primary to send transaction information needed by the standby to create a replication slot.

**Likely Cause:** The standby does not have the transaction information needed to create a logical replication slot.

**Recommended Action:** The customer needs to run `SELECT pg_log_standby_snapshot();` on the primary PostgreSQL instance (not the standby). This is a customer DBA action.

---

### Canonical Restart Procedure

Restarting table replication is a last resort that drops the destination table and re-snapshots from source. For large production tables this can take hours or days. The canonical customer procedure lives only in [Restart Table Replication](connector-shared-cdc.md#restart-table-replication). Always fix the root cause, verify the table is still in `FAILED`, then use that shared procedure verbatim. Do not summarize, paraphrase, or improvise the restart steps from this file.
