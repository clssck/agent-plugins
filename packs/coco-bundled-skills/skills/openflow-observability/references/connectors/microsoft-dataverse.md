---
name: openflow-observability-connector-microsoft-dataverse
description: Microsoft Dataverse connector troubleshooting and SPCS domain allowlist.
---

# Microsoft Dataverse

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/dataverse/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/dataverse/setup)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
|--------|-------|
| `<org-id>.crm.dynamics.com` | Customer-specific Dataverse instance |
| `login.microsoftonline.com` | OAuth authentication |

## Troubleshooting

### Connectivity Check

Run the `List Dataverse Tables` processor once (right-click > Run Once). If credentials are invalid, an error appears on the processor. If successful, the output queue will contain a non-empty list of tables.

### Entity Set Names vs Table Names

The Dataverse OData API uses **entity set names**, not logical table names. Entity set names are usually the logical name with an "s" suffix, but not always.

**How the customer finds the correct entity set name:**
1. Open PowerApps > Tables > select the table
2. Go to Advanced > Tools
3. Select "Copy set name"

Use this entity set name in the connector configuration.

### Ingestion Status

Check the `Fetch Dataverse Table` processor state. The state format is: `<STATUS>;<DELTA_TOKEN>;<SKIP_TOKEN>`

| Status | Meaning |
|--------|---------|
| `DONE` | Fetch cycle completed, waiting for next schedule |
| `PROCESSING` | Processing fetched records |
| `FETCHING` | Actively fetching from Dataverse API |

### Restart Ingestion

To restart ingestion from scratch, the `Fetch Dataverse Table` processor state needs to be cleared (all processors stopped, queues emptied, state cleared, then processors restarted). This is a customer-owned runtime action.

### Log Query


```sql
SELECT
  timestamp,
  TRY_PARSE_JSON(value):"level"::STRING AS log_level,
  TRY_PARSE_JSON(value):"loggerName"::STRING AS logger,
  TRY_PARSE_JSON(value):"formattedMessage"::STRING AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND TRY_PARSE_JSON(value):"level"::STRING IN ('WARN', 'ERROR')
  AND (
    TRY_PARSE_JSON(value):"loggerName"::STRING ILIKE '%Dataverse%'
    OR TRY_PARSE_JSON(value):"loggerName"::STRING ILIKE '%microsoft%'
  )
ORDER BY timestamp DESC
LIMIT 100;
```

### Processor Log Levels

Per-processor log levels can be changed for more detail. Right-click the processor > Configure > Settings > Bulletin Level.

| Processor | Default useful logs |
|-----------|-------------------|
| `ListMicrosoftDataverseTables` | Only errors (no debug/info output) |
| `FetchMicrosoftDataverseTable` | INFO: processing finished; DEBUG: delta/skip tokens, row counts; WARN: retryable errors; ERROR: non-retryable errors |

---

For shared SaaS patterns (OAuth failures, rate limiting, API versioning), load `references/connectors/saas-connectors.md`. For Snowflake-side destination failures or controller-service issues, also load `connector-shared-generic.md`.
