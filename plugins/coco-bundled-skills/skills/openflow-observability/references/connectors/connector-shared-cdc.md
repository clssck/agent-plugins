---
name: openflow-observability-connector-shared-cdc
description: Shared CDC connector diagnostics -- decision tree, table state machine, restart/reset impact guidance, error aggregation.
---

# Shared CDC Diagnostics

**Critical rules:**
- `FAILED` is terminal. A table in `FAILED` requires the customer to run the [Restart Table Replication](#restart-table-replication) procedure; source-side fixes alone are not sufficient.
- There is no restart button in the Openflow UI for CDC tables. The customer must run the remove -> state cleared -> drop destination table -> re-add flow documented below.
- Fix the root cause first, then decide whether table restart is required.

> **FAILED is terminal — required customer-facing phrasing (BLOCKING).** Whenever the diagnosis involves a CDC table in `FAILED`, the customer-facing summary MUST use this exact framing: *"the table is in FAILED state; the customer must run the [Restart Table Replication](#restart-table-replication) procedure"*. State that the customer must perform the restart procedure before any data flows again. The procedure is always a deliberate customer action.

> **Minimum runtime size:** CDC connectors require a runtime size of at least Medium. Using a Small runtime will cause failures or severe performance issues.

---

## CDC Decision Tree

### Table FAILED Errors

Table failures typically appear in the `com.snowflake.openflow.runtime.processors.database.*` loggers.

> **STOP:** There is no restart button in the Openflow UI. When recommending restart, you MUST use the verbatim procedure from [Restart Table Replication](#restart-table-replication). Do not summarize, paraphrase, or describe a UI button that does not exist.

#### Missing Primary Key

**Error signal:** Table routed to "Mark Table Replication Failed" with no exception. The flow file was routed through the "no primary key" relationship.

**Root cause:** CDC connectors require every replicated table to have a primary key. Tables without a primary key are immediately failed.

**Resolution:**
- Customer action required: add a primary key to the source table. **This is fully customer-actionable** — do NOT suggest opening a Snowflake support case, contacting Snowflake support, or escalating to Snowflake. The fix is a source-side DDL change the customer owns.
- If the table is already in `FAILED`, surface the canonical FAILED phrasing in the diagnosis: the table is in FAILED state and the customer must run the [Restart Table Replication] procedure (see [Restart Table Replication](#restart-table-replication)). Removing a table from replication and re-adding it triggers a full re-snapshot from source, which can take hours or days for large tables. State this cost explicitly and confirm the customer wants to proceed before recommending removal. Once the source issue is fixed, guide the customer through the restart procedure for the affected table by removing it from replication and re-adding it. If a partial destination table already exists, include the connector-managed recovery path from [Restart Table Replication](#restart-table-replication).

PostgreSQL: the current `OPENFLOW_POSTGRES_CDC` connector version requires a primary key on the source table. **`REPLICA IDENTITY FULL` does NOT substitute for a primary key in this connector version** -- the connector explicitly rejects it. See [postgresql.md](postgresql.md#missing-primary-key) for the current accepted alternatives (PK + DEFAULT, or unique non-deferrable index + USING INDEX). `REPLICA IDENTITY FULL` is only relevant for the separate TOAST-unchanged-value problem documented in postgresql.md.

---

#### Precision Exceeds Snowflake Limit

**Error signal:** Error message containing "precision exceeds" or referencing data type limits.

**Root cause:** A source column has a numeric precision that exceeds Snowflake's maximum (38 digits for NUMBER).

**Resolution:**
- Customer action required: reduce the source precision, exclude the column with connector configuration, or stop replicating that table.
- If the table is already in `FAILED`, verify it remains in that state after the source fix. If it does, see [Restart Table Replication](#restart-table-replication) as a last resort for that affected table only.

---

#### Table Already Exists in Snowflake

**Error signal:** Error message containing "table already exists" or flow file routed through the "table exists" relationship.

**Root cause:** The destination table already exists when the connector attempts to create it during snapshot replication. The connector will **not** overwrite or merge into an existing table -- it expects to create the table from scratch.

**Resolution:**
- **Root cause:** Destination table `{destination_database}."{failed_schema}"."{failed_table}"` already exists. The connector expects to create the table from scratch and will not overwrite or merge.
- **Remediation required:** The existing destination table must be dropped before the connector can re-create it. Dropping the table deletes all data it contains. This is one case where [Restart Table Replication](#restart-table-replication) for that affected table is unavoidable -- guide the customer through the procedure, including the data-loss acknowledgment.

---

#### Row Too Large

**Error signal:** Error message referencing row size exceeding Snowflake limits.

**Root cause:** The combined size of all columns in a single row exceeds Snowflake's row size limit.

**Resolution:**
1. Use the Column Filter JSON parameter to exclude unnecessary large columns, or
2. Split the source table into smaller tables before replication.

---

#### Unsupported Schema Change

**Error signal:** Error referencing column type change or incompatible schema modification.

**Root cause:** A column type change occurred on the source that maps to a different Snowflake type.

**Resolution:**
- Customer action required: once the schema change is accepted, the affected table must be re-snapshotted.
- Verify the table is in `FAILED` state. If it is, a restart of that affected table is the only recovery path -- see [Restart Table Replication](#restart-table-replication) for the procedure and data-loss impact.

---

### Connector-Wide Recovery Cases

**When to use:** Multiple tables enter FAILED simultaneously, or a retention/position event invalidates the entire replication position (expired MySQL binlogs, dropped PostgreSQL replication slots, expired SQL Server Change Tracking retention, deleted Oracle redo logs, stale/purged Snowflake streams).

**Recommended action:**
1. Fix the underlying source or destination retention/configuration problem first.
2. Run **CDC Table Replication State** from `references/core-queries-resource.md` to enumerate how many tables are affected.
3. If the count of affected tables is large (more than ~10), state the total count explicitly and confirm the customer wants to proceed before detailing per-table steps. Each affected table must go through the customer-run restart-table-replication procedure. This is not a UI button and not a connector-wide reset.
4. Escalate only if tables continue to fail after the documented recovery path, or if the logs indicate a product defect rather than ordinary retention/state loss. See [When to Escalate Instead](#when-to-escalate-instead) for full criteria.

### Replication Lag

**Error signal:** No explicit errors, but data in Snowflake is significantly behind the source database.

**Diagnosis:** Check for CDC engine warnings or errors that indicate the change stream reader is falling behind:


```sql
SELECT
  timestamp,
  COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING) AS logger,
  COALESCE(TRY_PARSE_JSON(value):"formattedMessage"::STRING, TRY_PARSE_JSON(value):"message"::STRING, LEFT(value, 500)) AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING, '') ILIKE 'com.snowflake.openflow.runtime.processors.database.%'
  AND COALESCE(record_attributes:"severity_text"::STRING, record_attributes:"LogLevel"::STRING, TRY_PARSE_JSON(value):"level"::STRING) IN ('WARN', 'INFO')
ORDER BY timestamp DESC
LIMIT 100;
```

**SQL Server:** SQL Server uses Change Tracking, not binlog/WAL replication. **Load** `references/connectors/sql-server.md` directly for Change Tracking lag diagnosis. The Change Tracking lag query in `sql-server.md` already uses COALESCE patterns. Use the provided query directly; do not write an ad-hoc alternative.

**Resolution by database type:**

- PostgreSQL-specific resolution: **Load** `references/connectors/postgresql.md`
- MySQL-specific resolution: **Load** `references/connectors/mysql.md`
- SQL Server-specific resolution: **Load** `references/connectors/sql-server.md`

Also check resource utilization -- use CPU Utilization by Pod and Memory Utilization by Pod from `references/core-queries-resource.md`. If the runtime is resource-constrained, tell the customer that a larger runtime size or reduced source throughput may be required.

---

### Merge Schedule / Stale Destination Data

**Pattern:** No errors in the event logs, the source has confirmed changes, the journal table in Snowflake contains rows, but the destination table is not updating or updates are delayed by hours.

**Likely Cause:** The `Merge Task Schedule CRON` ingestion parameter is set to a schedule that fires infrequently or not at all. CDC events land in the journal staging table, but the MERGE job that applies them to the destination table only runs on the configured schedule. This creates silent data gaps — the destination appears stale even though replication is technically running.

**Diagnosis:**
1. Check the `Merge Task Schedule CRON` parameter value in the connector's ingestion parameters.
2. Verify when the merge processor last ran by checking the processor's last-run timestamp in the Openflow UI canvas.
3. Confirm rows are accumulating in the journal but not reaching the destination:
```sql
-- Journal tables are named <TABLE>_JOURNAL_<series>_<generation> (e.g. ORDERS_JOURNAL_1782136437_1),
-- so find the current journal table(s) for the source table first:
SHOW TABLES LIKE '<TABLE>_JOURNAL_%' IN SCHEMA <destination_database>."<schema>";
-- Then count rows in the most recent generation (highest <series>_<generation> suffix):
SELECT COUNT(*) FROM <destination_database>."<schema>"."<TABLE>_JOURNAL_<series>_<generation>";
```
If rows are present in the journal but absent from the destination table, the merge has not run recently.

**Recommended Action:**
- The `Merge Task Schedule CRON` parameter is primarily a **cost-control throttle** — it limits how often the MERGE job runs against the destination warehouse, so more frequent merges mean higher warehouse cost. Choose the least-frequent schedule that still meets the freshness requirement rather than defaulting to the most frequent. A schedule that fires every minute (`0 * * * * ?`) is a reasonable starting point for near-real-time needs; reserve very high frequencies (e.g., every second, `* * * * * ?`) for cases that genuinely require sub-minute latency and can absorb the added cost.
- Verify the CRON expression is valid using the Openflow UI's schedule preview. A common mistake is field misalignment that causes the schedule to fire less frequently than intended (e.g., using `0 */5 * * * ?` when `*/5 * * * * ?` was intended).
- If the CRON expression is correct but merges are not running, check for stuck FlowFiles in the merge processor queue or resource constraints on the runtime using `references/core-queries-resource.md`.

---

### Journal Table Does Not Exist

**Pattern:** The connector logs a continuous `JOURNAL does not exist` or equivalent error for a table. The destination table was created (snapshot completed), but no `<TABLE>_JOURNAL_<series>_<generation>` table is present in the destination schema.

**Likely Cause:** This is **expected behavior** — the journal staging table is created when the connector first needs to write change data for the table's current schema generation, not at snapshot time. If the source table has had zero changes since the snapshot completed, the journal legitimately does not exist yet. The continuous error is misleading in severity but does not indicate a product failure.

> **Journal table naming:** Journal tables are named `<TABLE>_JOURNAL_<series>_<generation>` (e.g. `ORDERS_JOURNAL_1782136437_1`). `<series>` is the epoch-second timestamp of when the table's replication state was created, and `<generation>` increments each time the source table's schema changes (or replication is restarted). A table can therefore have more than one journal table over its lifetime; the highest `<series>_<generation>` suffix is the current one. Always locate journal tables with `SHOW TABLES LIKE '<TABLE>_JOURNAL_%'` rather than assuming a plain `<TABLE>_JOURNAL` name.

**Recommended Action:**
1. Verify whether any DML changes have occurred on the source table since the snapshot completed.
2. To confirm the journal appears after a change: make a test DML change on the source table (a real INSERT, UPDATE, or DELETE — not a no-op). A `<TABLE>_JOURNAL_<series>_<generation>` table should appear in the destination schema within the next CDC polling cycle (check with `SHOW TABLES LIKE '<TABLE>_JOURNAL_%'`).
3. If changes have definitely occurred on the source but the journal still does not exist, check that the table is in `INCREMENTAL_REPLICATION` state (not stuck in `SNAPSHOT_REPLICATION`). Use the **Checking Table State via UI** steps in [Table Replication State Machine](#table-replication-state-machine).
4. The `JOURNAL does not exist` error only becomes a real issue if the journal fails to appear after confirmed source changes. In that case, check for a stuck snapshot state and — if the table is in `FAILED` — use [Restart Table Replication](#restart-table-replication).

---

### Stream Check Failures

These errors come from the Snowflake-side stream checks used by CDC connectors. They usually appear in `org.apache.nifi.processors.standard.ExecuteSQL` messages that reference `SYSTEM$STREAM_HAS_DATA(...)`, and sometimes as downstream `CaptureChange*` processor failures.

**Diagnostic query:**


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
    COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING) = 'org.apache.nifi.processors.standard.ExecuteSQL'
    OR COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING, '') ILIKE 'com.snowflake.openflow.runtime.processors.database.CaptureChange%'
  )
  AND (
    value ILIKE '%STREAM_HAS_DATA%'
    OR value ILIKE '%has become stale%'
    OR value ILIKE '%has been purged%'
    OR value ILIKE '%valid stream name%'
    OR value ILIKE '%Failed to process stream%'
  )
ORDER BY timestamp DESC
LIMIT 100;
```

**How to classify the result:**

| Error Pattern | Meaning | Recommended Action |
| --- | --- | --- |
| `has become stale` or `has been purged` | The connector's Snowflake stream offset aged past retention | Explain the connector-managed recovery path: remove the table from replication, drop the destination table, re-add it for a new snapshot, and review `DATA_RETENTION_TIME_IN_DAYS` with the Snowflake admin |
| `does not exist or not authorized` in `SYSTEM$STREAM_HAS_DATA` | The expected stream is missing, inaccessible, or the destination objects were changed outside the connector | If the stream name is fully qualified and the session role has access, verify with `SHOW STREAMS` in the destination database/schema. If the destination objects were changed manually, use the table restart path. If the stream should exist but does not and no manual changes were made, this may be a product defect -- escalate with the stream name and evidence |
| `must be a valid stream name` | Malformed stream reference; likely product defect in stream name construction | Collect the exact SQL from the log, affected table/stream names, `first_seen`, `last_seen`, and escalate -- this is a product defect |
| `CaptureChange*` + `Failed to process stream` | Often a downstream symptom of one of the stream errors above | Look for the paired `ExecuteSQL` stream-check failure first before treating it as a separate issue |

**CRITICAL: The connector manages its own streams. Never tell the customer to run `CREATE OR REPLACE STREAM` on connector-owned streams.** Manual stream recreation causes data loss and state corruption. The correct recovery path is always: remove the table from replication, drop the destination table, re-add it.

**Optional verification when a stream name is visible in the error and the session role has access:**

```sql
SHOW TERSE STREAMS IN DATABASE <destination_database>;
```

Use this only to confirm whether the named stream exists. If the stream name itself is malformed, the event logs are usually enough to treat it as a product defect.

---

### Replication Stuck in NEW State

**Error signal:** Table was added to replication but never transitions from NEW to SNAPSHOT_REPLICATION.

**Diagnosis steps:**

1. **Check processor run status** -- Run **Processor Run Status** from `references/core-queries-resource.md` scoped to `{namespace}`.
   If all processors show `running = 0`, the connector is stopped or has validation errors.

2. **Check for stuck FlowFiles** -- Run **Stuck FlowFiles** from `references/core-queries-resource.md` scoped to `{namespace}`.
   If FlowFiles are stuck for > 30 minutes, investigate the destination processor.

3. **Check resource utilization** -- CPU Utilization by Pod and Memory Utilization by Pod from `references/core-queries-resource.md`. High CPU (> 80%) or memory (> 85%) can prevent processing.

PostgreSQL-specific: if connecting to a hot standby replica and the CDC processor is not starting, **Load** `references/connectors/postgresql.md` for the `pg_log_standby_snapshot` workaround.

---

### Table Stuck in SNAPSHOT_REPLICATION or INCREMENTAL_REPLICATION

**Pattern:** A table is in `SNAPSHOT_REPLICATION` or `INCREMENTAL_REPLICATION` but appears stalled — no new rows at the destination despite time passing, no errors in the event log, and the table is not in `FAILED`.

#### Stuck in SNAPSHOT_REPLICATION (snapshot not completing)

**Likely Cause:** Very large source table (snapshot can take hours to days), resource contention on the runtime, or a long-running transaction/lock on the source preventing the snapshot SELECT from completing.

**Diagnosis:**
1. Check resource utilization — CPU Utilization by Pod and Memory Utilization by Pod from `references/core-queries-resource.md`. A constrained runtime may be processing the snapshot slowly without error.
2. Check for stuck FlowFiles using **Stuck FlowFiles** from `references/core-queries-resource.md`.
3. Ask the customer how many rows the source table contains. For very large tables (tens of millions of rows or more), set expectations: the snapshot may legitimately still be in progress.

**Recommended Action:** If the snapshot is genuinely stalled (FlowFiles stuck, no processor activity for more than an hour on a non-huge table) and the table has not entered `FAILED`, check runtime resources first. If the runtime is resource-constrained, guide the customer to resize to a larger runtime. A table in `SNAPSHOT_REPLICATION` should not be restarted unless it enters `FAILED` — interrupting a running snapshot without a `FAILED` state forces an unnecessary re-snapshot.

#### Stuck in INCREMENTAL_REPLICATION (no new changes reaching destination)

**Likely Causes:**
1. No new changes on the source table — confirm the source has recent DML activity.
2. Merge schedule is too infrequent — see [Merge Schedule / Stale Destination Data](#merge-schedule--stale-destination-data).
3. Replication lag — the change stream reader is falling behind. See [Replication Lag](#replication-lag).
4. Snowpipe Streaming errors preventing journal writes — check `net.snowflake.*` loggers in the CDC Error Log Scan.

**Recommended Action:** Follow the [Merge Schedule / Stale Destination Data](#merge-schedule--stale-destination-data) and [Replication Lag](#replication-lag) diagnostic paths before considering any table restart. A table in `INCREMENTAL_REPLICATION` (not in `FAILED`) should not trigger [Restart Table Replication](#restart-table-replication) — that procedure causes a full re-snapshot and should only be used for tables in `FAILED` state.

---

### Snapshot Failures

**Error signal:** Table transitions from NEW to SNAPSHOT_REPLICATION but then enters FAILED state.

**Diagnosis:** Run the CDC error log scan in `references/connectors/connector-router-cdc.md` and look for errors during the snapshot phase. Common causes:

- **Connection errors to source database:** Cross-reference with `references/troubleshoot-network.md`.
- **Permission issues:** The database user does not have SELECT permissions on the source table.
- **Source table was dropped:** The table was dropped while the snapshot was in progress.
- **Lock contention:** Long-running transactions on the source may block the snapshot query.
- **PostgreSQL TOASTed value:** Large column values stored out-of-line (TOASTed) may fail during snapshot or UPDATE if the unchanged TOAST datum is not in the WAL. The historical workaround was `REPLICA IDENTITY FULL`, but the current `OPENFLOW_POSTGRES_CDC` connector explicitly rejects FULL. There is no documented connector-side workaround in the SQL-managed connector at this time. **Load** `references/connectors/postgresql.md` for the current state and direct the customer to Snowflake support if they hit this pattern.

**Resolution:** Fix the underlying issue first. If the table is in `FAILED`, surface the canonical FAILED phrasing in the diagnosis: the table is in FAILED state and the customer must run the [Restart Table Replication] procedure (see [Restart Table Replication](#restart-table-replication)). Once the source issue is fixed, guide the customer to remove the table from replication and re-add it. If a partial destination table already exists, include the connector-managed recovery path from [Restart Table Replication](#restart-table-replication).

---

### Connection Failures to Source Database

**Error signal:** "Connection refused", "Connection timed out", "SocketTimeoutException", "Unable to connect", or JDBC connection errors.

**Diagnosis:**


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
  AND COALESCE(record_attributes:"severity_text"::STRING, record_attributes:"LogLevel"::STRING, TRY_PARSE_JSON(value):"level"::STRING) = 'ERROR'
  AND (
    value ILIKE '%connection%refused%'
    OR value ILIKE '%timed%out%'
    OR value ILIKE '%SocketTimeoutException%'
    OR value ILIKE '%unable to connect%'
  )
ORDER BY timestamp DESC
LIMIT 50;
```

**Resolution:** Cross-reference with `references/troubleshoot-network.md`. Key checks:
- For SPCS deployments: do not jump straight to "missing EAI". If the errors are timeouts / communications link failures, first verify source-side firewall allowlists, SPCS egress allowlists, and other network-path controls. Check EAI/network-rule coverage for the host and port, but only diagnose a missing EAI or missing host entry when the evidence supports that specifically.
- For BYOC deployments: verify cloud networking (security groups, NAT gateways, VPC peering) allows connectivity
- Verify the database endpoint is reachable and the credentials are correct
- If a table was previously replicating and then transitions from `INCREMENTAL_REPLICATION` to `FAILED` after connectivity errors, frame the root cause as a connectivity regression, not as a brand-new connector setup problem, unless stronger evidence proves the configuration was always missing

**If the root cause is a stale `Source Database Connection URL` (e.g., the source DB was moved to a new host, the customer changed ports, SSL was added/removed):** see [Openflow SQL Action Candidates for CDC Config Errors](#openflow-sql-action-candidates-for-cdc-config-errors) below. The wrong-URL case is a direct fit for `connector.config_set_property`.

---

## Openflow SQL Action Candidates for CDC Config Errors

When a CDC connector's failure root-causes to a wrong or missing value in `config.json` (NOT a source-side or network issue), the agent can update that single property via an Openflow SQL action after the customer confirms. This is the diagnostic-to-action loop for SQL-managed CDC connectors.

### Property fixes (STRING_LITERAL)

For any per-connector STRING_LITERAL property identified as wrong, propose `connector.config_set_property`. Look up the connector definition in the [Openflow SQL Connector Support Matrix](../openflow-sql/connector-support-matrix.md#connector-capability-matrix) for:

- Whether the connector is SQL-managed today (`Openflow SQL support` column). Only offer the candidate when the value is `GA`, `MVP`, or `PrPr`; for `Coming next` or `Not yet`, route to UI. For `PrPr`, you may optionally add a Private Preview note to the Confirmation Preview.
- The shortlist of common STRING_LITERAL fix-candidates (`Common STRING_LITERAL fix-candidates` column).
- The per-connector troubleshoot doc that owns source-side prerequisites (`Per-connector troubleshoot doc` column).

- Internal action ID (do not show to customer): `connector.config_set_property`
- Trigger phrase to offer the customer: "Looks like `{property_name}` on the connector is `{current_value}` but should be `{proposed_value}`. If you confirm, I can update just that property with one `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM`. Want me to preview the before/after diff?"
- On acceptance, hand off to **Openflow SQL Action Mode**: **Load** `references/openflow-sql/action-guidelines.md` and `references/openflow-sql/connector-config-edit.md`, then follow the [connector.config_set_property](../openflow-sql/connector-config-edit.md#connectorconfig_set_property----regex-targeted-property-edit) template. Every gate in [SKILL.md Openflow SQL Action Mode](../../SKILL.md#openflow-sql-action-mode) must pass first.
- Do **not** offer this candidate when:
  - The property's `valueType` is `SECRET_REFERENCE` (e.g., `Source Database Password`) -- route to the Openflow UI.
  - The uniqueness gate fails (`REGEXP_COUNT` of the property name returns 0 or >1) -- route to the Openflow UI wizard.
  - The connector is not SQL-managed (`SHOW OPENFLOW CONNECTORS` returns zero rows for it) -- guide via the parameter-context UI flow.
  - The failure is source-side (e.g., the publication does not exist on the source, the user lacks REPLICATION privilege) -- the wrong-config narrative does not apply; fix the source instead.
- CDC stop window: `connector.config_set_property` lands the connector in `STOPPED` via the brief UPDATING window. Surface the [CDC Retention Warning](../openflow-sql/action-guidelines.md#cdc-retention-warning-cross-cutting) at the **Standard** tier.
- After successful application: the connector lands in `STOPPED` with a new default version. Propose `connector.start` as a separately-confirmed next step (no auto-chain).

### Missing driver (ASSET_REFERENCE)

For `ClassNotFoundException` / driver-not-loaded / `Failed to invoke @OnEnabled` failures on CDC connectors, this is the stuck-driver case. Cross-reference to the shared wire:

- [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) -> `connector.config_set_asset` candidate
- [Stuck-Driver Fast-Path (assetIds is null)](../openflow-sql/connector-diagnostics.md#stuck-driver-fast-path-assetids-is-null)

The pre-stage requirement (JAR must be on a customer-named stage) and the BYOC carve-out apply to CDC the same way they do to non-CDC connectors.

---

## Table Replication State Machine

CDC connectors track each table through a state machine managed by the `StandardTableStateService`.

**Transitions:** NEW → SNAPSHOT_REPLICATION → INCREMENTAL_REPLICATION (continues indefinitely). Any state → FAILED on permanent error.

| State | Meaning | Transition Trigger | Expected Duration |
| --- | --- | --- | --- |
| `NEW` | Table registered for replication | Added to replication config | Seconds to minutes |
| `SNAPSHOT_REPLICATION` | Initial full snapshot loading into Snowflake | Automatic after NEW | Minutes to hours depending on table size |
| `INCREMENTAL_REPLICATION` | Streaming real-time changes from the source | Snapshot completes | Indefinite (healthy state) |
| `FAILED` | Permanent error. Requires customer-run [Restart Table Replication](#restart-table-replication) procedure | Any state on permanent error | N/A -- requires manual intervention |

### Checking Table State via UI

Guide the customer to check per-table state directly in the Openflow UI:
1. Right-click on the connector canvas > Controller Services
2. Find the `Table State Store` service
3. Select **View State**
4. Each table is listed with its current state (`NEW`, `SNAPSHOT_REPLICATION`, `INCREMENTAL_REPLICATION`, or `FAILED`)

### Using Data Provenance to Track Table Events

Data Provenance provides a detailed history of what happened to each table:

1. Right-click on the connector canvas > **Data Provenance**
2. Filter by provenance event type:
   - `Register New Tables For Replication` -- confirms a table was added to replication (look for `ATTRIBUTES_MODIFIED` events)
   - `Remove Table From Replication` -- confirms a table was removed
   - `Mark Table Replication Failed` -- shows why a table entered FAILED state (check the event details for the error message)

### Diagnosing State Issues

**Table stuck in NEW:** See [Replication Stuck in NEW State](#replication-stuck-in-new-state) above.

**Table in INCREMENTAL_REPLICATION but no new data:**
1. Verify the source table has new data being written.
2. Check the Merge Task Schedule CRON parameter -- if not set to continuous (`* * * * * ?`), merges only run during scheduled windows.
3. Check for Snowpipe Streaming errors in the `net.snowflake.*` loggers.

**Table in FAILED:** Run the entry point query to find the specific error, then follow the appropriate branch in the decision tree above.

### Checking Table State via Event Logs

**Quick check** -- recent transitions for a specific table or all tables:


```sql
SELECT
  timestamp,
  COALESCE(TRY_PARSE_JSON(value):"formattedMessage"::STRING, TRY_PARSE_JSON(value):"message"::STRING, LEFT(value, 500)) AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND value ILIKE '%Replication state for table%changed from%'
ORDER BY timestamp DESC
LIMIT 100;
```

**Full per-table state summary:** Use **CDC Table Replication State** from `references/core-queries-resource.md` to derive the latest known state per table, with FAILED tables sorted first. Add `AND value ILIKE '%to FAILED%'` to narrow to failed tables only.

---

## Table Status Metric (`db.table.status`)

DB Connector runtimes emit a `db.table.status` metric to the customer's Openflow event table for each replicated source table. The value is an integer status code that corresponds to the failure categories in the decision tree above. When the customer has access to their event table, this metric is the fastest way to enumerate which tables have failed and why.

### Status codes

The emitted `value` is the table's current state code. For a healthy table it is the `TableReplicationStatus` code (`1`/`2`/`3`); for a `FAILED` table it is the specific `TableStateChangeReason` code (`40xx`) when one was recorded, otherwise the generic `FAILED` code `4`. A value of `0` means the table is no longer tracked (removed from the replication state map). The internal transition reason codes `2001`/`3001` are never emitted as a metric value.

The reason codes through `4024` apply to every DB CDC connector. Codes `4025`-`4031` are general codes (destination re-snapshot failures, unsupported source object types, source expression errors, and key-configuration problems); `4032`/`4033`/`4034`/`4035` are SQL Server specific (change tracking and capture instances).

| Code | Meaning | Classification |
| --- | --- | --- |
| 0 | No longer tracked (removed from replication state) | Lifecycle (often expected) |
| 1 | NEW | Normal |
| 2 | SNAPSHOT_REPLICATION | Normal |
| 3 | INCREMENTAL_REPLICATION | Normal |
| 4 | FAILED (generic, no specific reason recorded) | Investigate |
| 4001 | Failed to communicate with the source database | Transient / infrastructure |
| 4002 | Failed to merge FlowFile content | Investigate (internal processing) |
| 4003 | Invalid or unsupported fetch strategy | Investigate (config / internal) |
| 4004 | Column value exceeds the configured Oversized Value Limit | Customer-caused (source data) |
| 4005 | Snowflake merge query failed after max retries | Persistent |
| 4006 | Snowflake merge query returned unknown / indeterminate status | Investigate |
| 4007 | Column value missing / unretrievable from source (TOAST / LOB) | Source DB issue |
| 4008 | Table has no primary key | Customer-caused |
| 4009 | FlowFile missing required attributes | Investigate (possible product defect) |
| 4010 | No ROWID range provided | Investigate (possible product defect) |
| 4011 | Source table has no columns | Customer-caused (source schema) |
| 4012 | No database schema name provided | Investigate (possible product defect) |
| 4013 | No table name provided | Investigate (possible product defect) |
| 4014 | Failed to enforce FlowFile ordering | Investigate |
| 4015 | Table removed from source / no longer matches pattern / terminal FAILED | Lifecycle (often expected) |
| 4016 | Table schema could not be converted to expected format | Data type issue |
| 4017 | Schema for the table could not be found | Customer-caused |
| 4018 | Snowflake object already exists and cannot be created | Possible product defect |
| 4019 | Failed to create / update / manage Snowflake object | Infrastructure / permissions |
| 4020 | Snowpipe Streaming upload failed | Persistent |
| 4021 | Value mapping error during data transformation | Data type issue |
| 4022 | FlowFile content could not be read or parsed | Investigate |
| 4023 | Failed to clear FlowFile content after processing | Investigate (internal processing) |
| 4024 | Snowpipe Streaming v2 rejected invalid record content | Data quality |
| 4025 | Destination schema reconciliation failed before re-snapshot (incompatible column type change rejected by Alter Column Type Strategy) | Investigate (re-snapshot) |
| 4026 | Failed to clone destination table to its archive before re-snapshot | Investigate (re-snapshot) |
| 4027 | Failed to clear destination table before re-snapshot | Investigate (re-snapshot) |
| 4028 | Source database object type not supported (e.g. non-materialized view) | Customer-caused (source object) |
| 4029 | Source DB deterministic expression error (overflow, divide-by-zero, truncation, bad date) | Source DB issue / Customer-caused |
| 4030 | Replication key column dropped or renamed (update key config, then remove and re-add the table) | Customer-caused (source schema) |
| 4031 | User-defined logical key configuration is invalid (review Table Key Configuration JSON) | Customer-caused (config) |
| 4032 | Change tracking version expired, retention elapsed (SQL Server); re-snapshot required | Customer-caused (retention) |
| 4033 | Change tracking not enabled on source table (SQL Server) | Customer-caused (config) |
| 4034 | CDC position below oldest capture instance start_lsn, data continuity gap (SQL Server); re-snapshot required | Lifecycle (re-snapshot) |
| 4035 | Capture instance limit exceeded during schema-change rotation (SQL Server); drop conflicting instance, then re-add | Customer-caused (out-of-band capture instance) |

### Checking table status codes via the event table

```sql
WITH latest_status AS (
    SELECT
        resource_attributes:"k8s.namespace.name"::string   AS runtime,
        record_attributes:"source.schema.name"::string      AS schema_name,
        record_attributes:"source.table.name"::string       AS table_name,
        value::int                                           AS status_code,
        timestamp                                            AS last_seen
    FROM {event_table}
    WHERE record_type = 'METRIC'
      AND record:metric:name::string = 'db.table.status'
      AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
      AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
      AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY resource_attributes:"k8s.namespace.name"::string,
                     record_attributes:"source.schema.name"::string,
                     record_attributes:"source.table.name"::string
        ORDER BY timestamp DESC
    ) = 1
)
SELECT runtime, schema_name, table_name, status_code, last_seen
FROM latest_status
WHERE status_code = 4 OR status_code >= 4000   -- current state is FAILED (generic code 4, or a specific 40xx reason)
ORDER BY status_code, schema_name, table_name
LIMIT 200;
```

Match the returned `status_code` to the table above to identify the failure category, then follow the matching branch in the decision tree. Once the root cause is fixed and the table is still in `FAILED`, use the [Restart Table Replication](#restart-table-replication) procedure.

---

## Restart Table Replication

> **USE THIS SECTION VERBATIM**
> Canonical restart procedure. All per-connector files defer to this section. The same procedure is mirrored in `SKILL.md` CDC Guardrails so it stays in always-loaded context; both copies must match. Do not improvise, shorten, or paraphrase these steps. Present them to the customer exactly as written, substituting only the table-specific values.

**This is a last resort for the affected table only.** Restarting table replication drops the destination table for that table and re-snapshots only that table from source. For production tables this can mean hours or days of re-ingestion depending on data volume. Exhaust all less destructive options before recommending this path. Do not generalize this procedure into a connector-wide reset.

**Step 3 is irreversible.** Dropping the destination table removes all its data. Time Travel `UNDROP TABLE` may recover it within the retention window (default 1 day) but is not a safety net -- confirm the correct table name and customer acceptance before step 3.

### Before Recommending a Restart

1. **Identify and fix the root cause** first (missing PK, permissions, schema issue, etc.) using the diagnostic queries above. Never recommend a restart before the root cause is addressed -- the table will just re-fail.

2. **Verify the table is still in FAILED state.** After the customer fixes the source issue, check the current table state using the [Checking Table State via Event Logs](#checking-table-state-via-event-logs) query. If the table is no longer in `FAILED` (e.g., it has transitioned back to `INCREMENTAL_REPLICATION` or `SNAPSHOT_REPLICATION`), confirm replication is progressing normally and skip the restart procedure.

3. **Check if fewer tables are affected than expected.** If only one table out of many is in FAILED, scope the restart to that single table. Do not restart tables that are replicating normally, and do not recommend restarting the whole connector from this workflow.

4. **Ask about data volume.** Before proceeding, ask the customer how large the affected table is. For tables with significant data volume, ensure the customer understands the re-snapshot duration and plans accordingly (e.g., off-peak window, downstream consumer impact).

### Restart Procedure (Customer-Run)

Present the warnings above together with the steps below in a single response so the customer sees the impact and the procedure at the same time. Do not withhold the steps pending a confirmation turn. Point the customer to the relevant connector maintenance documentation when available.

Only provide these steps after the root cause is fixed and the table is confirmed still in FAILED:

1. In the Openflow UI, update `Included Table Names` and `Included Table Regex` so the affected table is excluded from replication.
2. Verify the table state has been removed in the Openflow UI: right-click the connector canvas > Controller Services > `Table State Store` > **View State**. Do not continue until the affected table no longer appears there.
3. Drop the destination table in Snowflake for that table only (all existing data in that table is lost). The connector will NOT overwrite an existing destination table, so skipping this step causes immediate re-failure. **Note:** for tables that never completed their first snapshot (i.e., went directly from `NEW`/`SNAPSHOT_REPLICATION` to `FAILED`), no destination table was created -- the DROP is a no-op. Customer should still verify before skipping.
4. Update `Included Table Names` and `Included Table Regex` again so the affected table is included in replication.
5. Verify the table reappears in `Table State Store` and progresses through `NEW`, then `SNAPSHOT_REPLICATION`, and finally `INCREMENTAL_REPLICATION`.

> **For SQL-managed connectors: use the UI wizard for this procedure.** The Restart Table Replication procedure is destructive (drops destination tables, re-snapshots from source, can take hours/days for large tables). Even when a connector is managed primarily via Openflow SQL Action Mode, the agent should direct the customer to the UI wizard for this specific procedure rather than guiding them through equivalent SQL. Do not author a SQL action sequence that performs the steps above.

### When to Escalate Instead

Escalate only if: the root cause is unclear after full diagnostic, the table keeps re-failing after recovery, or the behavior suggests a product defect (e.g., table fails immediately on re-add with a new error, malformed stream name construction, inconsistent state after the documented recovery path). Connector-wide cases such as expired MySQL binlogs or a dropped PostgreSQL replication slot are still primarily customer-recoverable: fix retention/state first, then restart replication for each affected table. Do not recommend a full connector reset from this skill. Include the connector name, affected tables, approximate data volume, and diagnostic evidence.

---

## Error Pattern Summary Query

When the entry point query returns too many results, aggregate errors to find the dominant pattern:

Run **Error Pattern Summary** from `references/core-queries.md` scoped to `{namespace}`. If results are noisy, filter to CDC loggers: `com.snowflake.openflow.runtime.processors.database.%`, `net.snowflake.%`.

See [Frequency Interpretation](../core-guidelines.md#frequency-interpretation) for result interpretation.
