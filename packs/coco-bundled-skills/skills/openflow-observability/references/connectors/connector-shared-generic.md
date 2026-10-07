---
name: openflow-observability-connector-shared-generic
description: Generic connector diagnostics -- processor validation, bulletins, controller services, backpressure, dashboard, escalation criteria.
---

# Shared Generic Connector Diagnostics

---

## Standard Destination Parameters

All connectors share the same Snowflake destination parameters:

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Snowflake Account URL` | Snowflake account URL | `https://<account>.snowflakecomputing.com` |
| `Snowflake User` | Service user | Must have key pair auth configured |
| `Snowflake Private Key` | Private key (unencrypted) | PEM format, no passphrase |
| `Snowflake Role` | Role for ingestion | Needs warehouse usage plus the database, schema, and object grants required by the connector workflow |
| `Snowflake Warehouse` | Warehouse for ingestion | Required |
| `Snowflake Database` / `Snowflake Destination Database` | Destination database | Required. **Property name varies by connector definition.** Older gen-1 (NiFi parameter-context) connectors use `Snowflake Database`; newer SQL-managed connectors (e.g., `OPENFLOW_POSTGRES_CDC`) use `Snowflake Destination Database`. Consult the per-connector property catalog (e.g., [postgresql-sql-managed.md](postgresql-sql-managed.md)) for the exact property name before inspecting or editing the config. |

---

### Additional Privilege Requirements

Some connectors also use staging, deduplication, or lookup processors against Snowflake. Those flows may require more than `CREATE TABLE`, for example `USAGE` on the warehouse, `INSERT`, `TRUNCATE`, `SELECT`, or object ownership on customer-managed tables.

## SSL Configuration (Database Connectors)

To connect with SSL on any database CDC connector (PostgreSQL, MySQL, SQL Server, Oracle):
1. Set `Database SSL Connection` to `true` in Source Parameters
2. Upload the root certificate as a Reference asset in the `Database Root Certificate` parameter

---

## Destination Configuration Errors

**Pattern:** Shared Snowflake-side processors fail before or during writes. Common processor and service names include `PutSnowpipeStreaming` (and the Snowpipe Streaming v2 write processors `PublishSnowpipeStreaming` / `PublishChangeDataSnowpipeStreaming` present on the database CDC connectors), `SnowflakeConnectionService`, `SnowflakeDetectDuplicate`, `DatabaseLookup`, `MergeSnowflakeJournalTable`, and `UpdateSnowflakeDatabase`.

**Common error signals:**
- `Role '<role>' specified in the connect string is not granted to this user`
- `No active warehouse selected in the current session`
- `Failed to create a connection for <user>`
- `HTTP status=401` / `HTTP status=403`
- `Cannot perform SELECT. This session does not have a current database`
- Invalid or missing account identifier, user, private key, role, warehouse, database, or schema

**Snowsight Checks:** Use the user/role/warehouse/database names from the error message. If not present in the error, ask the customer for the connector's Snowflake destination parameters.

```sql
SHOW USERS LIKE '<snowflake_user>';
SHOW ROLES LIKE '<snowflake_role>';
SHOW WAREHOUSES LIKE '<warehouse_name>';
SHOW DATABASES LIKE '<database_name>';
SHOW GRANTS TO ROLE <snowflake_role>;
SHOW GRANTS TO USER <snowflake_user>;
```

When interpreting `SHOW GRANTS TO USER` results, focus only on grants relevant to the connector role. Do not enumerate unrelated roles in the response unless they directly explain the error.

**How to interpret the results:**
- Missing user / role / warehouse / database from the `SHOW` command = wrong parameter value or object was dropped
- Role exists but is not granted to the user = destination role misconfiguration
- Warehouse exists but the role lacks `USAGE`, or auto-resume is disabled on a suspended warehouse = warehouse error
- Database exists but grants are missing = downstream `current database`, `current schema`, or authorization failures

**Recommended Action:**
1. Verify destination parameters in the Openflow UI exactly match the existing Snowflake objects
2. Fix the root destination parameter or grant first; dependent processors and controller services usually recover afterward
3. If the runtime was previously healthy, compare the `first_seen` time of the error to recent Snowflake admin changes (role rename/drop, warehouse changes, key rotation)

---

## Destination SQL Errors

**Pattern:** Snowflake-side processors can connect, but SQL executed against destination schemas or tables fails.

**This is NOT a connection or authentication problem.** When the agent sees `SQL compilation error: ... does not exist or not authorized`, the connector's authentication and connection to Snowflake are healthy. The customer-facing diagnosis MUST distinguish destination object misconfiguration from connection failure. Use language like "the destination database/schema/table does not exist or is not accessible to the connector role", "this is a destination object misconfiguration, not a connection error", or "the connection is healthy — the missing object is the issue". Never tell the customer the connector cannot connect when the actual error is an object missing.

**Common error signals:**
- `SQL compilation error`
- `does not exist or not authorized`
- `schema does not exist`
- `Insufficient privileges to operate on table` / `SQL access control error`

**Snowsight Checks:** When the destination object is named in the error, verify existence and grants directly.

```sql
SHOW SCHEMAS LIKE '<schema_name>' IN DATABASE <database_name>;
SHOW TABLES LIKE '<table_name>' IN SCHEMA <database_name>.<schema_name>;
SHOW GRANTS ON TABLE <database_name>.<schema_name>.<table_name>;
SHOW GRANTS TO ROLE <snowflake_role>;
```

**Generated SQL caveat:** If the failing SQL is malformed, contains an empty column list, or uses an unquoted reserved word as an identifier, load the routed connector page for context. That usually points to either customer-owned source naming/filtering changes or a product defect that should be escalated with the exact SQL from the log.

**Recommended Action:**
1. Verify the destination schema and table exist where the connector expects them
2. Verify the destination role has the required object privileges for the workflow the connector is running
3. If parsed queries only show generic destination failures (`destination write errors`, `FlowFiles routed to failure`, broad `SQL access control error`) or `NULL` rows near the failure timestamp, run [Destination Raw Log Fallback](#destination-raw-log-fallback) before writing the diagnosis. Do not stop at "check destination permissions" if the raw log names the exact table, role, or privilege
4. If `PutSnowpipeStreaming` reports `INHERITED`, `channel invalidation`, or `Failed to reopen channel`, go to [Snowpipe Streaming Channel Invalidation](#snowpipe-streaming-channel-invalidation) instead of continuing with destination permission steps
5. If the error mentions `insufficient privileges` or `access control error`, the role is missing a required privilege (INSERT, SELECT, TRUNCATE, etc.) on the affected object. Name the exact privilege and object in the customer-facing summary instead of saying only "check permissions." Recommend: `GRANT <privilege> ON TABLE <database>.<schema>.<table> TO ROLE <role>;` with the specific privilege and object from the error message
6. If the error is on a newly introduced source object or sheet/tab, check whether the destination object creation or filtering rules need to be updated

---

## Row Rejection (Snowpipe Streaming v2)

**Pattern:** The Snowpipe Streaming v2 write processors (`PublishSnowpipeStreaming` / `PublishChangeDataSnowpipeStreaming`) route FlowFiles to the `invalid` relationship. Snowflake accepted the channel and the connection, but identified one or more invalid rows, resulting in partial transmission. The connection, role, and destination object are healthy; specific rows were rejected.

**This is NOT a connection, authentication, or object-existence problem.** The rest of the batch transmits; only the offending rows are rejected. Do not route the customer to connection or grant troubleshooting.

**Common error signals:**
- FlowFiles routed to the `invalid` relationship on `PublishSnowpipeStreaming` / `PublishChangeDataSnowpipeStreaming`
- Log text mentioning `invalid rows` or `partial transmission`

**Common causes:** a source value does not match the destination column type, exceeds the column length/precision, violates a non-null constraint, or is a malformed timestamp/numeric.

**Recommended Action:**
1. State that the root cause is row-level data rejection on the Snowflake side, not a connection or permission failure
2. Identify the rejected rows and columns from the log (use [Destination Raw Log Fallback](#destination-raw-log-fallback) if parsed rows are `NULL`)
3. Correct the source data or align the destination column type/precision with the source; the rejected rows are not retried automatically once the batch has partially transmitted

---

## Destination Raw Log Fallback

**Purpose:** Recover the exact object, privilege, SQL text, or Snowflake-side component from generic destination warnings.

**When to use:** Parsed queries return `NULL` logger/message fields, or the only visible signal is a generic destination warning such as `destination write errors`, `FlowFiles routed to failure`, or a broad `SQL access control error` without the exact object or privilege.

**Scope rule:** Apply the routed runtime namespace filter unless you have not yet identified the target runtime namespace (omit the namespace filter or use `LIKE 'runtime-%'` in that case).

```sql
SELECT
  timestamp,
  COALESCE(
    TRY_PARSE_JSON(value):"loggerName"::STRING,
    REGEXP_SUBSTR(value, '"loggerName":"([^"]+)"', 1, 1, 'e', 1)
  ) AS logger,
  LEFT(value, 1200) AS raw_log
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND (
    value ILIKE '%SnowpipeStreaming%'
    OR value ILIKE '%destination write errors%'
    OR value ILIKE '%insufficient privileges%'
    OR value ILIKE '%access control%'
    OR value ILIKE '%not authorized%'
    OR value ILIKE '%grant%'
  )
ORDER BY timestamp DESC
LIMIT 50;
```

**Interpretation:**
- Use `raw_log` to recover the exact table, schema, role, privilege, SQL text, or component name that parsed destination queries missed.
- If the raw log identifies a specific privilege or object, repeat that exact privilege and object in the customer-facing summary and recommendation.
- If `PutSnowpipeStreaming` is failing but parsed rows are `NULL` or generic, run this before concluding the root cause is still unknown.
- If the Destination Raw Log Fallback also returns only generic signals with no specific object, privilege, or SQL text, conclude with: "Logs do not contain sufficient detail to identify the exact object or privilege. Recommend customer-run `SHOW GRANTS TO ROLE <role>` and `SHOW TABLES IN SCHEMA <schema>` checks against the destination." Do not run additional query iterations.

---

## Snowpipe Streaming Channel Invalidation

**Pattern:** `PutSnowpipeStreaming` reports channel invalidation, `INHERITED` channel state, reopen failures, or invalid offsets while source-side CDC capture is still healthy.

**Common error signals:**
- `Channel is invalidated`
- `Channel state is INHERITED`
- `Failed to reopen channel`
- `The supplied offset ... is not valid`
- `FlowFiles routed to failure`

**Diagnosis:** Run Recent Error Logs (and [Destination Raw Log Fallback](#destination-raw-log-fallback) if parsed rows are `NULL`) filtering for `PutSnowpipeStreaming`, `Channel is invalidated`, `INHERITED`, and `Failed to reopen channel`. Confirm source CDC health via CDC-specific error logs or Error Pattern Summary before proceeding to the recommended action.

**Status code differentiation:** If the invalidation log includes a `status_code`, use it to determine the cause:

| Status Code | Meaning | Action |
|-------------|---------|--------|
| `40` | Schema change detected (e.g., column add/drop/rename on the destination table) | Check whether the customer or a migration script altered the destination table DDL. For **CDC connectors**, this can require table recovery: use the canonical [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) procedure. For **non-CDC connectors**, do **not** route to CDC restart guidance; treat this as destination schema drift, inspect the routed connector file for connector-specific resync/reload guidance, and escalate if no customer-safe recovery is documented there. |
| `89` | Internal Snowflake-side error | Escalate to Snowflake support with deployment ID, runtime name, affected tables, and exact error timestamps. |
| Other or absent | Unknown cause | Follow the general recommended action below. |

**How to interpret the results:**
- If source capture is still healthy and `SnowflakeConnectionService` is enabled, this is a Snowflake destination-side channel state problem, not a source outage
- When multiple tables enter `INHERITED` or invalidated channel state together, treat it as a systemic Snowflake-side issue rather than a single-table configuration mistake
- Invalid offset / reopen failures are not fixed by asking the customer to tune the source connector
- Do not present speculative causes such as duplicate writers, channel naming conflicts, or manual state drift as the primary diagnosis unless the logs explicitly show that evidence. `INHERITED` plus invalid offset errors alone should be treated as a Snowflake-side channel state failure

**Recommended Action:**
1. State clearly that the root cause is Snowpipe Streaming channel invalidation on the Snowflake side
2. Make Snowflake support escalation the first recommended action in the customer-facing summary. Include deployment ID, runtime name, affected tables, UTC timestamps, and the exact invalidation / offset errors in the support case
3. If the product UI exposes a customer-safe table reset or connector restart action, mention it only as an optional secondary step after recommending support escalation and documenting the evidence. Do not present it as the primary fix for invalidated / `INHERITED` channels
4. Do not recommend NiFi-internal remediation such as clearing component state, recreating channels manually, or calling `SYSTEM$DROP_STREAMING_INGEST_CHANNEL()` from the agent
5. Do not suggest source-side fixes when source CDC is still processing changes normally

---

## Processor Validation Errors

**Pattern:** All processors show `running = 0` in Processor Run Status, or the connector shows error bulletins in the Openflow UI.

**Cause:** One or more processors have invalid configuration preventing startup.

**Diagnosis:**
1. Check Recent Error Logs for validation error messages
2. Common causes:
   - Missing required parameter values in the connector's parameter context
   - Invalid parameter values (typos in boolean fields like "true"/"false", wrong format)
   - Controller service in INVALID state due to missing configuration
   - Relationships left unconnected on custom or partially configured flows
3. Guide the customer to:
   - Right-click on the connector canvas > Parameters -- verify all required values are filled
   - Right-click on the connector canvas > Controller services -- check for services in INVALID state
   - Hover over the warning icon on any INVALID service to see the specific missing property

---

## Bulletin Interpretation

Bulletins are warning and error messages generated by NiFi components. In Snowsight, bulletins are visible through the event table.

**How to find bulletin-like error messages:**

Run Error Pattern Summary from `references/core-queries.md` to aggregate error patterns with counts.

**Interpreting results:**
- `logger_name` identifies the component: processor-specific loggers start with the processor class name
- High `occurrence_count` + recent `last_seen` = ongoing systematic issue
- High `occurrence_count` + old `last_seen` = may have self-resolved
- Single occurrence is only truly transient when the message does not name a durable configuration, privilege, or object issue
- Loggers containing `com.snowflake.openflow.runtime.processors` = connector-specific processor errors
- `Administrative Yield` messages usually indicate retry backoff after another error. Treat them as supporting signal, not the root cause

---

## Controller Service State

Controller services provide shared resources to processors (database connections, authentication providers, etc.). They must be ENABLED for dependent processors to function.

**States:**

| State | Meaning |
|-------|---------|
| ENABLED | Service is active and available to processors |
| DISABLED | Service is deliberately stopped; dependent processors cannot run |
| ENABLING | Service is transitioning to ENABLED; wait briefly |
| INVALID | Service has configuration errors; hover over the warning icon in the UI |

**If a controller service is stuck in ENABLING:**
1. Wait 2-3 minutes -- this can happen during startup
2. If still stuck, customer-run: guide the customer to disable the service and re-enable it in the Openflow UI
3. If re-enable fails, check Recent Error Logs for the specific error preventing enablement

**If a controller service is INVALID:**
1. Customer-run: guide the customer to right-click canvas > Controller services
2. Find the INVALID service and hover over the warning icon
3. The tooltip shows the missing or invalid property
4. Common issues: missing credentials, incorrect URLs, referenced service not enabled

**"Enabling" in dependent service errors:** When a root controller service is INVALID, dependent services may report it as `state is Enabling` because NiFi keeps retrying the enable operation. Check the root service's own error message for the real validation failure.

**SQL-managed connectors: confirm with the [Connector Config Snapshot](../openflow-sql/connector-diagnostics.md#connector-config-snapshot-read-only).** If the connector is SQL-managed, **Load** [`references/openflow-sql/connector-diagnostics.md`](../openflow-sql/connector-diagnostics.md) and pull the connector's `config.json` into a temp stage. The snapshot exposes the same missing-property data the UI tooltip would surface (`"value": null`, `"assetIds": null`, `"fullyQualifiedSecretName": null`), but in machine-readable form. Pair with a Recent Error Logs scan scoped to the runtime namespace to see what actually broke when the controller service tried to enable. If the connector is `STOPPED` and the controller-service noise is actually a DRAFT or "Edits not applied" state, take the [DRAFT Connector Fast-Path](../openflow-sql/connector-diagnostics.md#draft-connector-fast-path) instead of routing into runtime/network branches.

#### Optional Openflow SQL action candidate (set STRING_LITERAL property)

If the [Connector Config Snapshot](../openflow-sql/connector-diagnostics.md#connector-config-snapshot-read-only) (paired with Recent Error Logs scoped to the runtime namespace) names a specific missing or wrong STRING_LITERAL property in `config.json` -- e.g., `Source.Source Database User`, `Source.Source Database Connection URL`, a hostname, a port, a publication / table list, a Snowflake destination database or warehouse -- the agent can update that single property via the stage-promote path (`ADD VERSION FROM '@stage'`) after confirmation.

- Internal action ID (do not show to customer): `connector.config_set_property`
- Trigger phrase to offer the customer: "The connector config has `{property_name}` set to `{current_value}` and the runtime is reporting errors that point at this field. If you'd like, I can update that single property in the connector config with one `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM` after you confirm. Want me to preview the before/after diff?"
- On acceptance, hand off to **Openflow SQL Action Mode**: **Load** `references/openflow-sql/action-guidelines.md` and `references/openflow-sql/connector-config-edit.md`, then follow the [connector.config_set_property](../openflow-sql/connector-config-edit.md#connectorconfig_set_property----regex-targeted-property-edit) template. Every gate in [SKILL.md Openflow SQL Action Mode](../../SKILL.md#openflow-sql-action-mode) must pass first.
- Do **not** offer this candidate when:
  - The property's `valueType` is `SECRET_REFERENCE` -- SECRET writes are out of MVP. Route the customer to the Openflow UI for secret setup.
  - The property's `valueType` is `ASSET_REFERENCE` -- use the [Missing JDBC Driver fast-path](#missing-jdbc-driver--parameter-context-assets) and `connector.config_set_asset` instead.
  - The uniqueness gate fails (`REGEXP_COUNT` of the property name returns 0 or >1) -- the agent cannot disambiguate from SQL alone; route to the Openflow UI wizard.
  - `SHOW OPENFLOW CONNECTORS` returns zero rows for the connector -- guide via the parameter-context UI flow.
- After successful application: the connector lands in `STOPPED` with a new default version. Propose `connector.start` as a separately-confirmed next step (no auto-chain).

### SnowflakeConnectionService Cascade

**For BYOC only.** The most common controller-service cascade on new or partially configured connectors is:

1. `StandardPrivateKeyService` or another credential service is INVALID
2. `SnowflakeConnectionService` cannot enable because it depends on the invalid credential service
3. Downstream services and processors (`DatabaseLookup`, `MergeSnowflakeJournalTable`, `PutSnowpipeStreaming`, `SnowflakeDetectDuplicate`) fail because `SnowflakeConnectionService` never becomes ENABLED

**BYOC Recommended Action:**
- Fix the root destination parameter first: private key, user, account URL, role, warehouse, or database
- Re-check the root credential service before troubleshooting the dependent services
- Once the root service enables, the downstream cascade usually clears on its next retry cycle

**SPCS SnowflakeConnectionService** does not depend on a separate credential service. SPCS uses session token authentication, so `StandardPrivateKeyService` being INVALID is expected noise on connectors that are correctly configured for session token auth and should be ignored. Continue investigating all other errors, especially destination write failures from `PutSnowpipeStreaming` (e.g., `insufficient privileges`, `access control error`, FlowFiles routed to failure). The PrivateKeyService false alarm is only one finding; the real root cause is often a separate issue such as missing grants or destination object problems.

**SPCS key pair auth is not supported.** If `SnowflakeConnectionService` logs `Cannot enable: dependent service StandardPrivateKeyService state is Enabling` and the connector is not functioning, the connector IS depending on key pair authentication. On SPCS, key pair auth does not work. The customer must reconfigure the connector to use session token authentication instead. Guide the customer to update the connector's destination parameters in the Openflow UI to use session token auth rather than key pair auth.

If the downstream signal is only a generic `destination write errors` warning, or parsed queries show `NULL` rows around the same timestamp, do not stop there. Run [Destination Raw Log Fallback](#destination-raw-log-fallback) against the same incident window. If the Destination Raw Log Fallback also returns only generic signals with no specific object, privilege, or SQL text, conclude with: "Logs do not contain sufficient detail to identify the exact object or privilege. Recommend customer-run `SHOW GRANTS TO ROLE <role>` and `SHOW TABLES IN SCHEMA <schema>` checks against the destination." Do not run additional query iterations.

When the downstream error names a specific missing privilege or object, repeat that exact finding in the customer-facing summary. Example: `OPENFLOW_ROLE` lacks `INSERT` on `OPENFLOW_DB.PUBLIC.ORDERS`; recommend `GRANT INSERT ON TABLE OPENFLOW_DB.PUBLIC.ORDERS TO ROLE OPENFLOW_ROLE;`. Do not leave the resolution at a generic "check destination permissions" if the logs already identify the missing privilege.

---

## Missing JDBC Driver / Parameter Context Assets

**Pattern:** Controller service (typically `DBCPConnectionPool`) fails during `@OnEnabled` with `ClassNotFoundException` for a JDBC driver class (e.g., `com.microsoft.sqlserver.jdbc.SQLServerDriver`, `org.mariadb.jdbc.Driver`, `org.postgresql.Driver`, `oracle.jdbc.OracleDriver`).

**Root cause:** Database connectors (SQL Server, MySQL, PostgreSQL, Oracle) require the user to upload the JDBC driver JAR as a **parameter context asset**. The driver is NOT bundled with the connector -- it must be downloaded separately and uploaded through the Openflow UI. If the JAR is missing, the `DBCPConnectionPool` controller service cannot load the driver class and fails to enable.

**Key distinction:** This is a configuration issue, not a runtime bug. Upgrading the connector or runtime will NOT resolve this. The customer must upload the correct driver JAR.

**Diagnosis:** Search for ClassNotFoundException or driver loading failures:


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
  AND (value ILIKE '%ClassNotFoundException%'
       OR value ILIKE '%Failed to invoke @OnEnabled%'
       OR value ILIKE '%JDBC driver class%not found%')
ORDER BY timestamp DESC
LIMIT 50;
```

**Also check if assets were synced to the runtime:**

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
  AND COALESCE(record_attributes:"LoggerName"::STRING, TRY_PARSE_JSON(value):"loggerName"::STRING, '') ILIKE '%AssetSynchronizer%'
ORDER BY timestamp DESC
LIMIT 20;
```

Look for `StandardAssetSynchronizer` messages confirming asset sync. If no messages appear, expand `{hours_back}` to 24. If messages appear but show zero assets synced, the driver JAR has not been uploaded.

**Required JDBC drivers by connector:**

| Connector | Driver Class | JAR Source | Parameter Name |
|-----------|-------------|------------|----------------|
| SQL Server | `com.microsoft.sqlserver.jdbc.SQLServerDriver` | [Microsoft JDBC Driver](https://learn.microsoft.com/en-us/sql/connect/jdbc/download-microsoft-jdbc-driver-for-sql-server) | `SQLServer JDBC Driver` |
| MySQL | `org.mariadb.jdbc.Driver` | [MariaDB Connector/J](https://mariadb.com/downloads/connectors/connectors-data-access/java8-connector/) | `MySQL JDBC Driver` |
| PostgreSQL | `org.postgresql.Driver` | [PostgreSQL JDBC](https://jdbc.postgresql.org/download/) | `PostgreSQL JDBC Driver` |
| Oracle | `oracle.jdbc.OracleDriver` | [Oracle JDBC](https://www.oracle.com/database/technologies/appdev/jdbc-downloads.html) | `Oracle JDBC Driver` |

**Resolution:**
1. Download the correct JDBC driver JAR from the source listed above
2. In the Openflow UI, navigate to the connector's parameter context (Source Parameters)
3. Find the JDBC Driver parameter (e.g., `SQLServer JDBC Driver`)
4. Select the **Reference asset** checkbox and upload the driver JAR file
5. Save the parameter context -- the asset will be synced to the runtime by the `StandardAssetSynchronizer`
6. Re-enable the controller service or restart the connector in the Openflow UI

#### Optional Openflow SQL action candidate (set ASSET_REFERENCE assetIds)

If the connector is SQL-managed AND the customer has already placed the driver JAR on a Snowflake-resident stage, the agent can wire the driver into `config.json` via a single `ADD VERSION FROM` after confirmation. This is the same fast-path as the [Stuck-Driver Fast-Path](../openflow-sql/connector-diagnostics.md#stuck-driver-fast-path-assetids-is-null) in the SQL diagnostics file.

- Internal action ID (do not show to customer): `connector.config_set_asset`
- Trigger phrase to offer the customer (always present BOTH paths so they can pick): "I see this connector is missing the `{driver_name}` JDBC driver. There are two ways to fix this:

  1. **Upload the JAR to a Snowflake stage and let me wire it in.** Run `PUT file://driver.jar @<DB>.<SCHEMA>.<STAGE>` from SnowSQL, then tell me the fully-qualified stage name (`<DB>.<SCHEMA>.<STAGE>`) and the JAR's exact basename. I'll set `assetIds` and promote a new connector version with one `ALTER OPENFLOW CONNECTOR ... ADD VERSION FROM` after you confirm.
  2. **Use the connector's guided install wizard in Snowsight.** This connector is SQL-managed, so the driver is uploaded directly inside the wizard (open the connector's configure page, follow the prompts, attach the JAR when asked). You do NOT need to touch a parameter context for SQL-managed connectors -- that path is for legacy non-SQL-managed connectors only (covered separately above in [Missing JDBC Driver / Parameter Context Assets](#missing-jdbc-driver--parameter-context-assets)).

  Which would you like? If you confirm option 1 and give me the fully-qualified stage and JAR basename, I'll preview the before/after diff and the exact SQL before doing anything."

  If the customer picks option 1 and confirms a fully-qualified stage path plus exact JAR basename, hand off to the [`connector.config_set_asset`](../openflow-sql/connector-config-edit.md#connectorconfig_set_asset----set-asset_reference-assetids) preflight. If they pick option 2 or cannot identify which JAR to use, stop and direct them to the guided install wizard; do not preview the action.
- On acceptance, hand off to **Openflow SQL Action Mode**: **Load** `references/openflow-sql/action-guidelines.md` and `references/openflow-sql/connector-config-edit.md`, then follow the [connector.config_set_asset](../openflow-sql/connector-config-edit.md#connectorconfig_set_asset----set-asset_reference-assetids) template. Every gate in [SKILL.md Openflow SQL Action Mode](../../SKILL.md#openflow-sql-action-mode) must pass first.
- Pre-stage requirement: confirm the JAR is present via `LIST '@{customer_stage}'` in preflight. If absent, fail closed -- the agent does NOT upload binaries.
- Do **not** offer this candidate when:
  - `SHOW OPENFLOW CONNECTORS` returns zero rows for the connector -- guide via the parameter-context UI flow above.
  - The connector is BYOC -- the parameter-context UI flow is the established path for BYOC asset uploads.
  - The customer cannot identify which JAR (vendor / version) is required -- fall back to the table above and the UI flow.
- After successful application: the connector lands in `STOPPED` with a new default version. Propose `connector.start` as a separately-confirmed next step (no auto-chain).

---

## Backpressure Detection

Backpressure occurs when a downstream processor cannot keep up, causing FlowFile queues to fill.

**Detection via Stuck FlowFiles** from `references/core-queries-resource.md`:
- `queued_minutes` > 30 for a connection = sustained backpressure
- Identify the `dest_processor` -- that processor is the bottleneck

**Decision tree when backpressure is detected:**

1. **Check for destination errors first.** Run Recent Error Logs filtered to the `dest_processor` logger or `PutSnowpipeStreaming`. If destination errors exist (auth failures, SQL errors, channel invalidation), fix those before considering sizing. Backpressure is the symptom, not the cause.

2. **Check for throttle/rate messages.** Search for `value ILIKE '%throttle%'` or `value ILIKE '%rate%'` in the event table. If present, the runtime is being rate-limited by the destination or source. For Salesforce, check API limits. For Kafka/Kinesis, check partition throughput.

3. **No errors, no throttling.** The runtime is likely undersized for the data volume. Check CPU and Memory utilization from `references/core-queries-resource.md`:
   - CPU > 80% sustained -> recommend larger runtime size
   - Memory > 85% -> recommend larger runtime size
   - Both normal -> check if source processors are stopped or the source system has paused production

4. **Source processor stopped or not producing.** If `source_processor` in the Stuck FlowFiles result has no recent data and no errors, the source system may not be producing changes. Confirm with the customer.

**Common bottleneck processors:**

| Processor | Cause | Resolution |
|-----------|-------|------------|
| `PutSnowpipeStreaming` | Snowflake ingestion slower than source | Customer may need a larger runtime size or lower source throughput |
| Source processors (e.g., `ConsumeKafka`, `ConsumeKinesis`) | Upstream producing faster than processing | Customer may need to slow the source or increase available runtime capacity |
| Transformation processors | Complex transformations on high volume | Customer may need a larger runtime or a simpler connector design |

Avoid prescribing NiFi-internal tuning values such as concurrent tasks unless a public connector document explicitly exposes that setting to customers.

If backpressure is sustained with large FlowFile queues and no clear processor error, also run **Disk Space per Runtime** from `references/core-queries-resource.md` to rule out disk exhaustion.

---

## Connectors Dashboard

The Connectors Dashboard in the Openflow UI provides a high-level view of all installed connectors without SQL queries. Guide customers to use it as a first-pass triage tool.

**Access:** Openflow in Snowsight, default view. Requires Runtime Server 2025.10.23.16+ and Runtime Extensions 2025.10.23.11+.

| Feature | Use For |
|---------|---------|
| Healthy / Unhealthy status | Quick identification of connectors with errors |
| Average throughput / Total data ingested | Comparing ingestion rates, identifying anomalies |
| Error distribution (View Details) | Understanding when a connector experienced issues |
| Table replication status and phase (View Details) | Checking Active/Failed, New/Snapshot Load/Incremental |

**Debugging from dashboard:** Filter to Unhealthy > View Details > Issues tab for errors and stack traces > View logs for full logs > Go to canvas for configuration.

**Limitations:** Data is event-table-based (not real-time). Detailed health monitoring is primarily for database connectors. Tables removed from config still appear on the details page.

---

## Escalation Criteria

Escalate to Snowflake support only after exhausting all customer-actionable guidance:

- Table stuck in FAILED state after the customer has completed the full recovery path from [Restart Table Replication](connector-shared-cdc.md#restart-table-replication) and it re-fails
- Data corruption indicators (duplicate rows, missing columns, incorrect values) with no customer-side cause
- Malformed SQL generated by the connector (product defect)
- Issue persists after following all guidance in the diagnostic path and the customer has verified their configuration

Include in the escalation:
1. Deployment ID
2. Runtime name and connector name
3. Error timestamps (UTC) from the queries above
4. Summary of errors found
5. Steps already attempted

Use the escalation template from `references/escalation.md` for the full format.

