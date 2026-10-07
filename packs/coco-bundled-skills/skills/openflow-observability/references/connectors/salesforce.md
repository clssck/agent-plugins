---
name: openflow-observability-connector-salesforce
description: Salesforce connector troubleshooting and SPCS domain allowlist.
---

# Salesforce

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/salesforce-bulk-api/about)
- [Setup (Salesforce)](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/salesforce-bulk-api/setup-salesforce)
- [Setup (Snowflake)](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/salesforce-bulk-api/setup-snowflake)
- [Configure connector](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/salesforce-bulk-api/configure-connector)
- [Troubleshoot](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/salesforce-bulk-api/troubleshoot)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
|--------|-------|
| `login.salesforce.com:443` | Authentication (production) |
| `test.salesforce.com:443` | Authentication (sandbox) |
| `<customer-instance>.my.salesforce.com:443` | Customer-specific Salesforce instance |

> **Note:** Custom Salesforce domains are not supported.

## Parameters & Required Assets

Key parameters from the official setup documentation: [Salesforce side](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/salesforce-bulk-api/setup-salesforce) | [Snowflake side](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/salesforce-bulk-api/setup-snowflake)

### Source Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Salesforce Instance URL` | Customer's Salesforce instance | e.g., `https://<instance>.my.salesforce.com` |
| `Salesforce Consumer Key` | Connected App consumer key | From the Salesforce Connected App settings |
| `Salesforce Consumer Secret` | Connected App consumer secret | From the Salesforce Connected App settings |
| `Salesforce Username` | API-enabled user | Must have API access enabled on the profile |
| `Salesforce Password` | User password | Append security token if IP not allowlisted |
| `Salesforce Security Token` | User security token | Reset via Salesforce user settings if needed |

### Destination Parameters

See [Standard Destination Parameters](connector-shared-generic.md#standard-destination-parameters).

> **Note:** Key pair authentication for the Snowflake service user is required for **BYOC deployments only**. SPCS deployments handle authentication automatically.

### Ingestion Parameters

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `Salesforce Object Types` | Salesforce objects to replicate | Comma-separated list (e.g., `Account,Contact,Opportunity`) |
| `Salesforce Query Mode` | Full or incremental | Controls whether to do full load or incremental based on SystemModstamp |
| `Run Schedule` | Polling frequency | Controls how often the connector polls Salesforce for changes |
| `Initial Load Chunking` | Split large initial snapshots | `NONE`, `MONTHLY`, `QUARTERLY`, `YEARLY` -- splits snapshot by time to reduce disk usage |
| `Object Fields Filter JSON` | Exclude specific fields per object | JSON map of object name to field exclusion list (see Blob Fields below) |

## Troubleshooting

### Monitoring Query

Run this query to track Salesforce connector activity:

```sql
SELECT
  timestamp,
  resource_attributes:"openflow.dataplane.id"::STRING AS deployment_id,
  resource_attributes:"k8s.namespace.name"::STRING AS runtime_key,
  TRY_PARSE_JSON(value):"level"::STRING AS log_level,
  TRY_PARSE_JSON(value):"loggerName"::STRING AS logger,
  LEFT(TRY_PARSE_JSON(value):"formattedMessage"::STRING, 800) AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND TRY_PARSE_JSON(value):"loggerName"::STRING = 'org.apache.nifi.processors.standard.LogMessage'
  AND TRY_PARSE_JSON(value):"formattedMessage"::STRING LIKE '%SALESFORCE_BULK_API%'
ORDER BY timestamp DESC
LIMIT 100;
```

### Stuck IN_PROGRESS Jobs

**Pattern:** A Salesforce object type's state is stuck in `IN_PROGRESS` status and no FlowFiles are being processed for that object.

**Likely Cause:** A FlowFile may have been manually deleted before it could update the state, or the bulk job query failed mid-process.

**Recommended Action:** The stuck object's state in the `Salesforce Bulk Jobs State` controller service needs to be cleared to force a full reload for that object. This requires stopping processors, clearing the specific object state (or all state), and restarting. This is a customer-owned runtime action.

**Warning:** Do not delete FlowFiles manually. This can cause a job to remain in `IN_PROGRESS` indefinitely because the state cannot be manually updated.

### Force Full Load Procedure

Same as the stuck IN_PROGRESS resolution above. Clearing the `Salesforce Bulk Jobs State` forces the connector to re-fetch all data for the cleared object types from Salesforce. This is a customer-owned runtime action.

### Controller Service State Issues

**Pattern:** Salesforce connector not starting or producing errors immediately after start.

**Snowsight Checks:** Guide the customer to check controller services:
1. Right-click on the connector canvas > Controller services
2. Look for services in DISABLED or INVALID state
3. Hover over any warning icon to see the missing property or configuration error

The `Salesforce Bulk Jobs State` controller service must be ENABLED for the connector to track job state. If it is DISABLED, it needs to be enabled. This is a customer-owned runtime action.

### OAuth / API Authentication Failures

**Pattern:** Recent Error Logs shows authentication errors from Salesforce-related loggers.

**Common errors:**
- `INVALID_SESSION_ID` -- session expired or token revoked
- `INVALID_GRANT` -- OAuth refresh token expired
- `API_CURRENTLY_DISABLED` -- API access not enabled for the Salesforce org
- `HTTP 400 invalid_grant` or `HTTP 404 Not Found` on OAuth -- could be an expired trial Salesforce instance

**Recommended Action:**
1. Verify the Salesforce Connected App credentials are still valid
2. Check that the Salesforce user's security token has not been reset
3. Verify API access is enabled for the Salesforce user profile
4. If using OAuth and the refresh token has expired, the connector needs to be reconfigured with fresh credentials. This is a customer-owned credential update.

For shared SaaS auth, rate-limit, and API-version patterns that are not unique to Salesforce object behavior, also load `saas-connectors.md`.

### Reserved Word Collision in Generated SQL

**Pattern:** `SQL compilation error` from Snowflake-side processors while the generated SQL references a Salesforce object name such as `ORDER`, `GROUP`, `CASE`, `USER`, or `TASK`.

**Likely Cause:** The connector generated destination SQL using an object name that collides with a Snowflake reserved word.

**Snowsight Checks:**
1. Inspect the exact failing SQL in the error message
2. Confirm the failing identifier matches the Salesforce object being replicated
3. Cross-check whether the runtime also has a generic destination-side SQL error in `UpdateSnowflakeDatabase`, `ExecuteSQL`, or related Snowflake processors

**Recommended Action:**
1. If the customer can safely exclude or rename the affected object in the connector configuration, guide that change
2. Otherwise escalate with the exact SQL text, object name, runtime name, and connector version because this is usually a connector SQL-generation defect

### No Space Left on Device

**Pattern:** Error `No space left on device` during initial snapshot of large Salesforce objects.

**Likely Cause:** Initial snapshots of large objects exceed the content repository disk. Runtime disk sizes: Small ~100GB, Medium ~200GB. **Scaling node count does NOT increase content repo size** -- only a larger runtime helps.

**Recommended Action:**
1. **Initial Load Chunking:** The `Initial Load Chunking` parameter can split the snapshot by time period (`MONTHLY`, `QUARTERLY`, `YEARLY`), reducing peak disk usage by processing smaller batches.
2. **Larger runtime:** If chunking is insufficient, a larger runtime size is needed (scaling node count does NOT increase content repo size). This is a customer-owned runtime sizing decision.

### Blob Fields Not Supported

Blob (binary) fields are not supported by the Salesforce Bulk API V2. Attempting to replicate objects with blob fields will cause errors.

**Recommended Action:** Use `Object Fields Filter JSON` to exclude blob fields:

```json
{
  "ContentVersion": ["VersionData"],
  "Attachment": ["Body"],
  "Document": ["Body"]
}
```

Set this JSON in the `Object Fields Filter JSON` parameter to exclude the binary fields for each affected object.

### Connector State Management

View per-object connector state:
1. Right-click on the canvas > Controller Services
2. Open the state of `Salesforce Bulk Jobs State`
3. Each object shows its status: `IN_PROGRESS`, `COMPLETED`, `FAILED`, or `ABORTED`

> **Critical:** Never manually delete FlowFiles in the Salesforce connector. Deleting a FlowFile causes the associated object to remain permanently stuck in `IN_PROGRESS` state because the state update callback is lost. If this happens, the only recovery is a force full load (see [Stuck IN_PROGRESS Jobs](#stuck-in_progress-jobs) above).

### Verify Jobs in Salesforce

To verify a Salesforce Bulk API job from the Salesforce side:
1. In Salesforce: Setup > search for "Bulk Data Load Jobs"
2. Find the job by its Job ID (visible in the connector logs)
3. Check the job status, records processed, and any errors
