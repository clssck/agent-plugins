---
name: openflow-observability-connector-google-bigquery
description: Google BigQuery connector troubleshooting -- architecture, prerequisites, common errors, and operational procedures. BigQuery is currently in public preview and is not yet SQL-action managed.
---

# Google BigQuery

> BigQuery connector is currently in public preview. It is not SQL-action managed; all configuration changes are made through the Openflow UI.

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-bigquery/about)

---

## Architecture Overview

The BigQuery connector uses the **BigQuery Storage Read API** for efficient parallel data reads, not the standard BigQuery query API. This distinction matters for quota and permission troubleshooting.

**Processor pipeline (customer-visible on the NiFi canvas):**

| Processor | Role |
|-----------|------|
| `ListBigQueryTables` | Discovers tables across configured regions via `INFORMATION_SCHEMA` |
| `PickBigQueryTablesForReplication` | Routes tables to new, existing, or stale replication paths |
| `CreateReadSession` | Creates a BigQuery Storage API `ReadSession` for parallel ingestion |
| `GetAllStreams` | Splits the session into individual streams for parallel processing |
| `FetchBigQueryStream` | Fetches data from individual streams in batches |
| `TriggerBigQueryCdcOnState` | Triggers incremental sync using change windows |
| `BigQueryExecuteSQL` | Executes DDL/DML for CDC operations using the BigQuery `CHANGES` function |
| `MergeBigQueryJournalTable` | Merges CDC journal data from Snowflake journal table to destination |
| `UpdateBigQueryTableState` / `CheckBigQueryTableState` | Manages the table replication lifecycle |

**Controller services (visible under Controller Services on the canvas):**

- `StandardBigQueryClientService` -- provides BigQuery SQL and Storage Read API client pool
- `StandardBigQueryTableStateService` -- persists table replication state in NiFi cluster scope
- `GCPCredentialsControllerService` -- manages GCP service account authentication

**Table replication lifecycle:**

```
NEW -> SNAPSHOT_REPLICATION -> INCREMENTAL_REPLICATION -> INCREMENTAL_IN_PROGRESS -> INCREMENTAL_REPLICATION (loop)

Any state -> FAILED  (unrecoverable error, manual intervention required)
Any state -> REMOVED (table removed from configuration)
```

`FAILED` is terminal. A table in `FAILED` state requires the customer to remove and re-add it; source-side fixes alone are not sufficient. See [Remove and Re-add a Table](#remove-and-re-add-a-table) and the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure.

**Error routing on most processors:**

- `success` / `bigquery.data` -- normal operation
- `failure` -- non-retryable error (configuration, permissions, schema)
- `comms.failure` -- retryable/transient error (network, quota, temporary API errors); processor yields and retries automatically

---

## Prerequisites Checklist

Verify the following before troubleshooting. Most initial failures trace back to one of these items being misconfigured.

### GCP Side

- Service account created with **BigQuery User** (`roles/bigquery.user`) and **BigQuery Data Editor** (`roles/bigquery.dataEditor`) roles at the **project level** (not dataset level)
- JSON key file generated for the service account and correctly pasted into the connector configuration (complete JSON, no truncation)
- Change history enabled on each replicated table:
  ```sql
  -- Run on the source BigQuery project
  ALTER TABLE `project.dataset.table` SET OPTIONS (enable_change_history = TRUE);
  ```
- BigQuery API and BigQuery Storage API both enabled in the GCP project

### Required GCP Permissions (Minimum)

The service account must have the following IAM permissions at project level:

| Permission | Purpose |
|------------|---------|
| `bigquery.datasets.get` | Discover datasets |
| `bigquery.tables.get` | Read table metadata |
| `bigquery.tables.getData` | Read table data via Storage Read API |
| `bigquery.tables.list` | List tables in datasets |
| `bigquery.jobs.create` | Execute CHANGES queries and view ingestion |
| `bigquery.tables.create` | Create temporary tables for view ingestion |
| `bigquery.tables.delete` | Clean up temporary tables after view ingestion |

### Required Network Endpoints (SPCS)

For SPCS deployments, the External Access Integration must include these endpoints:

| Endpoint | Purpose |
|----------|---------|
| `bigquery.googleapis.com:443` | BigQuery API |
| `bigquerystorage.googleapis.com:443` | BigQuery Storage Read API |
| `oauth2.googleapis.com:443` | GCP service account authentication |

### Snowflake Side

- Destination database created with `USAGE` and `CREATE SCHEMA` granted to the connector role
- Warehouse created and granted to the connector service user (`USAGE`, `OPERATE`)
- **SPCS:** External Access Integration configured with a network rule covering all three Google API endpoints above
- **BYOC:** Key-pair authentication configured for the Openflow service user

For standard destination parameter requirements, see [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters).

---

## Checking Table Replication State

The connector tracks each table in the `BigQuery Table State Service` controller service.

**To view table states from the NiFi canvas:**

1. Open the BigQuery connector process group on the canvas
2. Right-click > Controller Services
3. Find **BigQuery Table State Service** (or "Table State Store")
4. Click the three-dot menu > View State

**State reference:**

| State | Meaning |
|-------|---------|
| `NEW` | Table discovered but replication not yet started |
| `SNAPSHOT_REPLICATION` | Initial full load in progress |
| `INCREMENTAL_REPLICATION` | CDC active, waiting for next sync window |
| `INCREMENTAL_IN_PROGRESS` | CDC sync currently running |
| `FAILED` | Permanent failure -- manual intervention required |
| `REMOVED` | Table removed from replication configuration |

The raw state value format is: `{STATUS},{WATERMARK_EPOCH_MILLIS}`

---

## Getting Error Logs

**From the NiFi canvas:** Look for red bulletin notes on processor groups; click through to find the failing processor. Check the Bulletin Board (hamburger menu, top right corner). Use Data Provenance (hamburger menu) and filter by component name for detailed flow history.

**From the Openflow Connectors Dashboard (Snowsight):** Navigate to Openflow in Snowsight. Unhealthy connectors appear with error status. Select the connector > View Details > Issues tab for errors and stack traces. Requires Runtime Server 2025.10.23.16+ and Runtime Extensions 2025.10.23.11+.

**From the customer's event table:** The customer can query their Snowflake event table directly for BigQuery-specific log entries.

---

## Common Errors and Resolutions

### 1. Authentication and Permissions Errors

**Symptom:** Processor shows `BigQueryClientServiceException` on the `failure` relationship. Error messages contain `403 Forbidden`, `401 Unauthorized`, or `Access Denied`. `GCPCredentialsControllerService` fails to enable.

**Example error:**
```
BigQueryClientServiceException: BigQuery API error - Access Denied: Table <project>:<dataset>.<table>.
```

**Resolution:**
1. Verify the Service Account JSON is correctly pasted (complete JSON, no truncation)
2. Confirm roles are assigned at the **project level** -- dataset-level roles are insufficient:
   - `roles/bigquery.user`
   - `roles/bigquery.dataEditor`
3. Verify the BigQuery API and BigQuery Storage API are enabled in GCP Console > APIs & Services
4. Test the service account credentials independently using the Google Cloud Console or `bq` CLI before re-uploading
5. For SPCS: verify the External Access Integration includes all three required endpoints (see Prerequisites Checklist)

---

### 2. Session Expiration (Large Tables)

**Symptom:** `FetchBigQueryStream` routes to `failure`. Error: `Session {streamName} expired at {expireTime}. Ingestion was terminated.` Table state changes to `FAILED`.

**Cause:** The BigQuery Storage Read API data streams are valid for approximately 6 hours. Tables too large to ingest within that window on the current runtime will fail.

**Resolution:**
- Scale up the runtime -- use a larger runtime size or add more nodes for parallel processing
- Adjust the Max/Min Stream Count parameters on `CreateReadSession` to tune parallelism
- After resolving the runtime sizing, remove and re-add the affected table to restart ingestion from a clean state (see [Remove and Re-add a Table](#remove-and-re-add-a-table))

**Sizing guidance:**

| Table Size | Recommended Runtime |
|------------|-------------------|
| < 10 GB | Single Medium |
| 10 -- 100 GB | Single Large, or multi-node Medium |
| > 100 GB | Multi-node Large |

Medium is the minimum supported runtime size for this connector.

---

### 3. Time-Travel Timestamp Invalid (Transient, Auto-Recovering)

**Symptom:** `CreateReadSession` routes to `comms.failure`. Error: `INVALID_ARGUMENT: request failed: Invalid time travel timestamp <timestamp> for table <project>:<dataset>.<table>@<timestamp>. Cannot read before <timestamp>`.

**Cause:** A race condition between session creation time and BigQuery's internal timestamp resolution. The connector requests a snapshot at the current instant, but BigQuery may not have that exact millisecond timestamp available yet. The difference is typically a few milliseconds.

**Resolution:** This is a retryable error. The connector automatically routes to `comms.failure` and retries. No manual intervention is needed in most cases. If it recurs persistently, check for underlying network or clock-skew issues on the runtime.

---

### 4. CDC Window Exceeded 24 Hours

**Symptom:** Log message: `CDC window for {table} exceeds 24h. Data changes prior to {trimmedStart} will be skipped`. Data gaps in the destination table after a long replication pause. `TriggerBigQueryCdcOnState` trims the change window to 24 hours.

**Cause:** The BigQuery `CHANGES` function supports a maximum 24-hour lookback window. If the connector is stopped or paused for more than 24 hours, changes outside the window are permanently unavailable.

**Resolution:**

- **If data loss is acceptable:** Allow the connector to continue. It will resume from the trimmed window and proceed normally.
- **If data loss is not acceptable:**
  1. Remove the affected table from replication
  2. Drop the destination table in Snowflake
  3. Re-add the table to trigger a fresh full snapshot followed by incremental sync
  See [Remove and Re-add a Table](#remove-and-re-add-a-table)

**Prevention:** Keep the connector running continuously. The connector enforces a 10-minute safety offset as the minimum CDC lag due to the BigQuery `CHANGES` function's internal journal behavior. This means new changes appear in Snowflake with at least a 10-minute delay under normal operation.

---

### 5. Table State Inconsistencies

**Symptom:** `Table {FQN} does not exist in state service; cannot change state`. FlowFiles routed to `removed` relationship unexpectedly. Table stuck in `FAILED` state. `Table {FQN} is marked as FAILED in the connector-state store. Skipping ingestion`.

**Cause:** Table removed from configuration while ingestion was in progress; state service lost synchronization; or concurrent state updates conflicting.

**Resolution:**
1. Check the BigQuery Table State Service (Controller Services > BigQuery Table State Service > View State)
2. If a table is in `FAILED` state, follow [Remove and Re-add a Table](#remove-and-re-add-a-table)
3. If a table is missing from state but should be present: remove it from the configuration parameters, wait for cleanup, then re-add it

---

### 6. Schema and Data Type Errors

**Symptom:** `CreateReadSession` or `FetchBigQueryStream` routes to `failure`. Errors about unsupported data types or schema conversion failures. BIGNUMERIC precision errors.

**Cause:** BigQuery BIGNUMERIC supports up to 76 digits; Snowflake NUMBER supports a maximum of 38 digits. Narrowing type changes (for example, changing a column from `STRING` to `INT64`) are not supported and cause `FAILED` state.

**Data type mapping:**

| BigQuery Type | Snowflake Type | Notes |
|---------------|---------------|-------|
| `BIGNUMERIC` | `NUMBER` | Max 38 digits -- precision loss possible for values > 38 digits |
| `NUMERIC` | `NUMBER` | |
| `GEOGRAPHY` | `VARCHAR` | Stored as text representation |
| `DATETIME` | `TIMESTAMP_NTZ` | |
| `JSON` | `OBJECT` | |
| `STRUCT` | `OBJECT` | |
| `TIMESTAMP` | `TIMESTAMP_NTZ` | |
| `INT64` | `NUMBER` | |
| `FLOAT64` | `FLOAT` | |
| `STRING` | `VARCHAR` | |
| `BYTES` | `BINARY` | See binary encoding section below |
| `ARRAY` | `ARRAY` | |

**Resolution:**
- For `BIGNUMERIC` precision issues: inform the customer that values exceeding 38 significant digits will lose precision in Snowflake. If full precision is required, the column must be excluded or pre-cast in BigQuery.
- For schema evolution: only widening type changes are supported. A narrowing type change puts the table into `FAILED` state and requires a re-snapshot via [Remove and Re-add a Table](#remove-and-re-add-a-table).
- For unsupported types: check whether the column can be excluded from replication via connector configuration, or cast to a compatible type in BigQuery before ingestion.

---

### 7. Binary Encoding Issues (BYTES Columns)

**Symptom:** `StreamingChannelStatusException: Streaming Channel Status [INVALID]`. `Failed to cast variant value <redacted> to <redacted>`. Binary or `BYTES` columns cause ingestion failures.

**Cause:** Snowflake's `BINARY_INPUT_FORMAT` account parameter defaults to `HEX`, but BigQuery returns raw binary data. When the connector writes raw bytes and Snowflake expects hex-encoded input, the cast fails.

**Resolution:**
1. Check the Snowflake account parameter:
   ```sql
   SHOW PARAMETERS LIKE 'BINARY_INPUT_FORMAT' IN ACCOUNT;
   ```
2. The connector has a **Bytes Field Encoding** property on the `FetchBigQueryStream` processor (`RAW` or `BASE64`). Match this to what Snowflake expects.
3. If using Snowpipe Streaming, set `BINARY_INPUT_FORMAT` at the User level to match the connector's encoding:
   ```sql
   ALTER USER <openflow_user> SET BINARY_INPUT_FORMAT = 'BASE64';
   ```

---

### 8. View Ingestion Failures

**Symptom:** Views are not being replicated. View ingestion errors about missing permissions. Parameter context issues after a connector upgrade.

**Cause:** Views use a truncate-and-load strategy (not CDC) and require a different set of permissions from table replication. The service account needs write access to a configured temporary dataset. The `Temporary Table Dataset` parameter must be set.

**Resolution:**
1. Verify the **Temporary Table Dataset** parameter is configured and the service account has write access to it
2. Confirm the service account has `bigquery.tables.create` and `bigquery.tables.delete` permissions (included in `roles/bigquery.dataEditor` at project level)
3. If parameter context is missing after a connector upgrade (view ingestion group shows empty parameters), see [Parameter Context Mismatch After Upgrade](#9-parameter-context-mismatch-after-upgrade)

**Known limitations for views:**
- View replication uses truncate-and-load only -- no CDC support
- Views cannot be read directly via the Storage Read API; the connector creates temporary tables from view query results
- Overlapping view sync runs are prevented by the connector automatically

---

### 9. Parameter Context Mismatch After Upgrade

**Symptom:** After upgrading the BigQuery connector, the view ingestion process group has missing or empty parameters. A second ingestion parameter context was created (without the `(1)` suffix). View ingestion fails because parameters are not populated.

**Cause:** The NiFi upgrade mechanism creates a new parameter context instead of reusing the existing one for new process groups added during the upgrade.

**Resolution:**
1. Open the NiFi canvas and navigate to the BigQuery connector process group
2. Identify the correct parameter context: it has the `(1)` suffix and contains all populated parameters
3. Right-click on the view ingestion process group > Configure > General tab
4. Change the Process Group Parameter Context to the correct `(1)` context
5. Restart the affected processors

---

### 10. No Data Ingested, No Errors Visible

**Symptom:** Connector appears to be running (no error bulletins). No data appearing in destination tables.

**Diagnostic steps:**

1. **Check table discovery:** In Data Provenance for `ListBigQueryTables`, verify the `bq.table.count` attribute is greater than 0. Verify the BigQuery Regions parameter matches the region where the target datasets actually reside.

2. **Check table filtering:** Verify `Included Dataset Names` / `Included Dataset Names Regex` and `Included Table Names` / `Included Table Names Regex` match the target datasets and tables. Both a dataset filter and a table filter must match for the connector to ingest a table -- if either is missing or does not match, no tables are ingested and no error is raised.

3. **Check table state:** View the BigQuery Table State Service state. Tables should progress `NEW -> SNAPSHOT_REPLICATION -> INCREMENTAL_REPLICATION`. If stuck in `NEW`, check whether `CreateReadSession` is processing FlowFiles.

4. **Check controller services:** All controller services must be enabled (green checkmark). `GCPCredentialsControllerService` and `BigQuery Client Service` must both show enabled status. See [Controller Service State](connector-shared-generic.md#controller-service-state) for enable/disable troubleshooting.

5. **Check processor scheduling:** Verify all processors in the main group are started. Check if any processors are in a yielded state (which is normal during backoff -- wait a few minutes and check again).

6. **Check queues:** Look for FlowFiles stuck in queues between processors. A persistent backlog in front of a specific processor indicates that processor is the bottleneck.

---

### 11. Snowflake Merge Failures (CDC)

**Symptom:** `MergeBigQueryJournalTable` routes to `comms.failure` or `failure`. `SQLException` errors in logs. CDC changes not appearing in destination tables. Stale Snowflake streams on journal tables.

**Cause:**
- Transient Snowflake connection pool issues (routes to `comms.failure` -- automatic retry)
- Journal table or destination table was dropped or modified externally
- Snowflake stream on the journal table became stale (more than 14 days without consumption)
- MERGE query failures due to schema mismatch or constraint violations

**Resolution:**
- For `comms.failure` (transient `SQLException`): the connector retries automatically. If the error is intermittent, monitor for recovery.
- For stale streams: BigQuery journal tables are named `<sourceTableName>_<incrementalNumber>_<hash>_journal` (e.g. `orders_0_9f86d081884c7d65_journal`), where `<sourceTableName>` is the BigQuery source table name used verbatim, `<incrementalNumber>` distinguishes successive journals of the same source table, and `<hash>` is the first 16 hex characters of a SHA-256 of the BigQuery source FQN (`project.dataset.table`). This convention is specific to the BigQuery connector and differs from the DB CDC connectors' `<TABLE>_JOURNAL_<series>_<generation>` format (see [Journal Table Does Not Exist](connector-shared-cdc.md#journal-table-does-not-exist)); locate the current journal with `SHOW TABLES LIKE '<sourceTableName>_%_journal'` rather than assuming a fixed name. If the Snowflake stream on a journal table becomes stale, the MERGE cannot proceed. Remove and re-add the affected table for replication (see [Remove and Re-add a Table](#remove-and-re-add-a-table)).
- For persistent `failure` relationship: check Snowflake warehouse availability and that the connector role still has the required grants on the destination database and journal tables.

---

### 12. Storage API Throttling

**Symptom:** Slow data ingestion. Intermittent `comms.failure` routing. Log messages containing `BigQuery reports > 0% throttling`.

**Cause:** BigQuery Storage Read API has per-project quota limits. Too many concurrent streams from the same project can exceed these limits.

**Resolution:**
1. Check BigQuery quotas in Google Cloud Console > APIs & Services > BigQuery Storage API
2. Reduce the number of concurrent streams by adjusting **Max Stream Count** in `CreateReadSession`
3. Reduce the **Read Client Pool Size** in `StandardBigQueryClientService` (default is 5)
4. Consider scheduling large table ingestions during off-peak hours to stay within quota

Throttling errors route to `comms.failure` and are retried automatically. Persistent throttling requires quota adjustments on the GCP project side.

---

## Known Limitations

| Limitation | Details |
|------------|---------|
| Data stream lifetime | BigQuery Storage Read API streams are valid for approximately 6 hours. Large tables require multi-node runtime. |
| `BIGNUMERIC` precision | BigQuery supports up to 76 digits; Snowflake NUMBER supports maximum 38 digits. Precision loss is possible. |
| External tables | External table replication is not supported. |
| View replication | Uses truncate-and-load only. No CDC for views. |
| Primary keys for CDC | Incremental syncs require primary keys for update/delete handling. Tables without primary keys are failed immediately. Inserts-only tables without PKs are not supported for CDC. |
| Minimum CDC lag | 10-minute minimum lag due to the BigQuery `CHANGES` function safety offset. |
| Maximum change window | 24-hour maximum lookback. If replication falls behind by more than 24 hours, data changes in that gap are permanently lost. |
| Schema evolution | Only widening data type changes are supported. Narrowing type changes cause replication failure. |
| Minimum runtime size | Medium runtime is the minimum recommendation. |
| Storage Read API quotas | Subject to BigQuery Storage Read API per-project quotas and rate limits. |

---

## Operational Procedures

### Remove and Re-add a Table

This procedure is required when a table is in `FAILED` state, when recovering from session expiration or stale journal streams, or when you need to trigger a fresh full snapshot.

> For the canonical remove/re-add steps as documented in the shared CDC guidance, see [Restart Table Replication](connector-shared-cdc.md#restart-table-replication). The steps below cover the BigQuery-specific considerations that differ from that procedure.

**BigQuery-specific notes:**

- **Before removing a table that is in `INCREMENTAL_IN_PROGRESS` state:** Stop the **Trigger BigQuery CDC On Incremental** processor first. Wait for the table state to change to `INCREMENTAL_REPLICATION` before removing the table from configuration. This avoids leaving orphaned FlowFiles in queues.

- **Before re-adding a table:** Drop the destination table in Snowflake. The connector will not re-replicate a table if the destination already exists.
  ```sql
  DROP TABLE <destination_database>.<schema>.<table_name>;
  ```

- After the destination table is dropped and the table is re-added to the Included Table Names parameter, the connector creates a `NEW` state entry and proceeds through `SNAPSHOT_REPLICATION` to `INCREMENTAL_REPLICATION` automatically.

---

### Restart Failed CDC Ingestion

If CDC (incremental sync) is failing but the initial snapshot completed successfully:

1. Check the current watermark in the Table State Store
2. If the watermark is more than 24 hours behind:
   - Data loss is expected. The BigQuery `CHANGES` function cannot look back beyond 24 hours.
   - Option A: Accept the data loss and let the connector continue from the trimmed window
   - Option B: Remove and re-add the table for a full re-snapshot (see [Remove and Re-add a Table](#remove-and-re-add-a-table))
3. If the watermark is within the 24-hour window:
   - Check the error logs for the specific failure cause (permissions, schema changes, warehouse issues, stale stream)
   - Resolve the underlying issue first
   - The connector will resume automatically on the next CDC trigger cycle once the root cause is fixed

---

### Full Connector Reset (Last Resort)

If the connector is in a state where normal recovery procedures are not working and you need to start fresh:

1. Remove all tables from replication: clear `Included Table Names`, `Included Table Names Regex`, `Included Dataset Names`, and `Included Dataset Names Regex`
2. Stop all processors in the connector process group
3. Empty all queues (right-click on the process group > Empty queues)
4. Wait for the BigQuery Table State Service to clear all entries

> **Step 5 is destructive and irreversible.** It drops all destination tables and schemas, deleting their data in Snowflake. List what will be dropped, show it to the customer, and get explicit confirmation before proceeding.

5. Drop all destination tables and schemas from the Snowflake destination database
6. Re-add the datasets and tables to the configuration parameters
7. Start all processors

This procedure causes a full re-snapshot of all configured tables and may take hours or days for large datasets.

---

For shared SaaS/API patterns (OAuth, rate limiting, GCPCredentialsControllerService delegation), load `references/connectors/saas-connectors.md`. For destination-side diagnosis (Snowpipe Streaming, SnowflakeConnectionService, missing grants), load `references/connectors/connector-shared-generic.md`. For shared CDC state machine guidance and the canonical Restart Table Replication procedure, load `references/connectors/connector-shared-cdc.md`. This file is routed from `references/connectors/connector-router-cdc.md`.
