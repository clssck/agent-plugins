---
name: openflow-observability-connector-sharepoint
description: SharePoint unstructured connector troubleshooting and SPCS domain allowlist.
---

# SharePoint (Unstructured)

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sharepoint/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sharepoint/setup)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
|--------|-------|
| `<company>.sharepoint.com` | Customer-specific SharePoint site (or `*.sharepoint.com`) |
| `graph.microsoft.com:80` | Microsoft Graph API |
| `graph.microsoft.com:443` | Microsoft Graph API |
| `login.microsoftonline.com` | OAuth authentication |
| `excelcs.officeapps.live.com` | Office Online document conversion used by some SharePoint file workflows |

## Root Processor

| Source | Root Processor | Controller Service Verification |
|--------|---------------|-------------------------------|
| SharePoint | `CaptureSharepointChanges` | Not supported |

## Troubleshooting

### SharePoint Resync Required

**Pattern:** `CaptureSharepointChanges` reports `Resync required`.

**Likely Cause:** The SharePoint delta link expired or was invalidated, so the connector can no longer continue incremental change tracking from its saved token.

**Recommended Action:**
1. Note that this is a source-side SharePoint state issue, separate from any Snowflake-side warehouse or role error
2. Have the customer restart the connector first
3. If the error persists, the customer may need to clear the saved state for the change-capture processor and re-establish the sync baseline from scratch

### Office Online Conversion Errors

**Pattern:** SharePoint file-processing errors from `FetchSharepointFile`, including `UnsupportedMediaType` during Office document conversion.

**Likely Cause:** The file type is not supported by the Office Online conversion path, or the document content cannot be converted cleanly.

**Recommended Action:** Treat this as a file-specific issue. Confirm the file type is supported, note the file path or object name, and continue troubleshooting the primary connector issue separately if other files are still ingesting.

### Single File Not Ingested

1. **File not under specified folder:** Only the configured folder and its subfolders are discovered.
2. **File extension filtered:** Check `File Extensions To Ingest` parameter. Use Data Provenance (right-click on canvas > Data Provenance) and filter for `DROP` events from filter processors.
3. **Cortex Search only -- document parsing failed:** Check the `PerformSnowflakeCortexOCR` processor logs for parsing errors.

### Error Log Query


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
  AND TRY_PARSE_JSON(value):"level"::STRING IN ('WARN', 'ERROR', 'FATAL')
ORDER BY timestamp DESC
LIMIT 100;
```

---

For shared SaaS patterns (OAuth failures, rate limiting, API versioning), load `references/connectors/saas-connectors.md`. For shared Snowflake-side destination failures and customer state inspection queries for unstructured connectors, see [Unstructured Connector Shared Patterns](saas-connectors.md#unstructured-connector-shared-patterns), and load `connector-shared-generic.md` for the destination-side diagnosis itself.
