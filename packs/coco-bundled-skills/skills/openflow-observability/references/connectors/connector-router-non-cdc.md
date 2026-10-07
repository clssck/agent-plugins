---
name: openflow-observability-connector-router-non-cdc
description: Non-CDC connector diagnostics entry point, routing table, and initial triage steps.
---

# Non-CDC Connector Router

Entry point for non-CDC connector troubleshooting. Start here after the required non-CDC or SaaS/API bundle is loaded, then run runtime-scoped log and processor checks.

## Scope

- Non-CDC connector routing by type
- Initial runtime-scoped triage steps
- Cross-references to shared generic diagnostics and per-connector guidance

**Not covered:**
- CDC connector failures -> **Load** `references/connectors/connector-router-cdc.md`
- Network connectivity issues -> **Load** `references/troubleshoot-network.md`
- Runtime-level issues (OOM, crashes) -> **Load** `references/troubleshoot-runtime.md`

**Constraint:** All diagnostics are SQL-only via Snowsight. Use `{event_table}` for all event table queries.

---

## Routing Table

Once the required bundle is loaded, route to the per-connector file:

| connector_type | Route To |
| --- | --- |
| `kinesis` | `references/connectors/kinesis.md` |
| `kafka` | `references/connectors/kafka.md` |
| `salesforce_bulk_api` | `references/connectors/salesforce.md` |
| `microsoft_dataverse` | `references/connectors/microsoft-dataverse.md` |
| `sharepoint_unstructured` | `references/connectors/sharepoint.md` |
| `google_drive_unstructured` | `references/connectors/google-drive.md` |
| `box_unstructured` | `references/connectors/box.md` |
| `linkedin_ads`, `meta_ads`, `amazon_ads`, `google_ads` | `references/connectors/ads-connectors.md` |
| `google_drive`, `sharepoint`, `box`, `jira`, `hubspot`, `workday`, `confluence`, `slack`, `google_sheets` | `references/connectors/saas-connectors.md` |
| `excel` | `references/connectors/excel.md` |
| `shopify` | `references/connectors/shopify.md` |
| `veeva_vault` | `references/connectors/veeva-vault.md` |
| `snowflake_to_kafka` | [Snowflake to Kafka](kafka.md#snowflake-to-kafka) |
| Unknown or unlisted non-CDC connector | `references/connectors/connector-shared-generic.md` as the starting point. Note to the customer that per-connector guidance may be limited. |

**Load** the connector-specific file for domain allowlists, troubleshooting details, and source setup instructions.

---

## Error Signal Routing

> Direct signal matches let you skip the general non-CDC entry-point sequence. They do not let you skip the required bundle. If the bundle is not loaded, stop and load it before continuing.

Before running the general non-CDC entry point, check if the error matches a known signal that routes directly to a specific diagnostic section.

| Error Signal | Route To |
| --- | --- |
| `ClassNotFoundException` for JDBC driver class | [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) |
| `Failed to invoke @OnEnabled` on `DBCPConnectionPool` | [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) |
| `JDBC driver class...not found` | [Missing JDBC Driver / Parameter Context Assets](connector-shared-generic.md#missing-jdbc-driver--parameter-context-assets) |
| Controller service stuck in ENABLING/INVALID | [Controller Service State](connector-shared-generic.md#controller-service-state) |
| `SnowflakeConnectionService` validation failures, missing User/Account/Private Key, or destination credential cascades | [SnowflakeConnectionService Cascade](connector-shared-generic.md#snowflakeconnectionservice-cascade) |
| `PutSnowpipeStreaming`, `SnowflakeDetectDuplicate`, `UpdateSnowflakeDatabase`, or `ExecuteSQL` destination auth/role/warehouse failures | [Destination Configuration Errors](connector-shared-generic.md#destination-configuration-errors) |
| Destination-side `SQL compilation error`, `does not exist or not authorized`, or `schema does not exist` | [Destination SQL Errors](connector-shared-generic.md#destination-sql-errors) |
| `Failed to open a channel` or `Channel is invalidated` | [Snowpipe Streaming Channel Invalidation](connector-shared-generic.md#snowpipe-streaming-channel-invalidation) |
| `Relationship ... is not connected to any component and is not auto-terminated` | [Processor Validation Errors](connector-shared-generic.md#processor-validation-errors) |
| `AADSTS` or `MsalServiceException` (Azure AD auth) | Load the routed connector file (`references/connectors/sharepoint.md`, `references/connectors/microsoft-dataverse.md`, or `references/connectors/saas-connectors.md`) for Azure AD auth troubleshooting |
| `LIMIT_EXCEEDED` or `REQUEST_LIMIT_EXCEEDED` (Salesforce) | `references/connectors/salesforce.md` -- API rate limit |
| `Initialization failed for stream` (Kinesis) | `references/connectors/kinesis.md` -- stream configuration |
| `terminated during authentication` or `Authentication failed` (Kafka) | `references/connectors/kafka.md` -- SASL/auth configuration |
| `Broker may not be available` (Kafka) | `references/connectors/kafka.md` and `references/troubleshoot-network.md` -- network/broker connectivity |
| `Resync required` from `CaptureSharepointChanges` | [SharePoint Resync Required](sharepoint.md#sharepoint-resync-required) |
| `GCPCredentialsControllerService` + `Delegation User` | [Google Workspace Delegation User](saas-connectors.md#google-workspace-delegation-user) |
| `SALESFORCE_BULK_API - Error` or generated SQL errors for Salesforce objects | `references/connectors/salesforce.md` |
| `No space left on device` (Salesforce) | [No Space Left on Device](salesforce.md#no-space-left-on-device) |
| `UnresolvedAddressException` (Salesforce OAuth) | `references/troubleshoot-network.md` -- network rule / EAI not configured on runtime |
| `EncryptionException` or `Decryption error` | `references/troubleshoot-runtime.md` -- runtime encryption issue |
| `Flow version.*does not exist` or flow registry version mismatch | Escalate to Snowflake support -- flow registry state corruption |

If the error signal matches one of these patterns, **Load** the referenced file and section directly instead of following the general non-CDC entry point. Signal routing skips the entry-point sequence, not the required bundle.

---

## Entry Point

**Load** `references/core-queries-resource.md` if not already loaded (Steps 2 and 3 use queries from this file).

Start every non-CDC connector investigation with these steps.

### Step 1: Recent Error Logs

Run Recent Error Logs from `references/core-queries.md` filtered to the connector's runtime namespace:

```sql
AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
```

Look for connector-specific loggers:
- `com.snowflake.openflow.runtime.processors` -> connector processor errors
- `software.amazon.kinesis.*` -> KCL-level errors (Kinesis)
- `org.apache.kafka.*` -> Kafka client errors
- `org.apache.nifi.processors.standard.LogMessage` with `SALESFORCE_BULK_API` -> Salesforce connector

### Step 2: Processor Run Status

Run Processor Run Status from `references/core-queries-resource.md` to check if processors are running.

- All processors `running = 0` -> connector is stopped or has validation errors preventing startup
- Some processors `running = 0` -> may be normal, or a specific processor has failed
- All processors `running = 1` -> processors are active; issue may be upstream (source system) or downstream (Snowpipe Streaming)

### Step 3: Stuck FlowFiles

Run Stuck FlowFiles from `references/core-queries-resource.md` to check for queued data.

- Queued data in front of a specific processor -> that processor is the bottleneck
- No queued data + no errors -> source system may not be producing data
- Large queue duration (> 30 min) -> investigate the destination processor for errors

### Step 4: Branch

Based on results, use the [Routing Table](#routing-table) to load the connector-specific file. If errors are not connector-specific, **Load** `references/connectors/connector-shared-generic.md`.

