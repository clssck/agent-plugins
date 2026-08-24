---
name: openflow-observability-connector-saas
description: Shared SaaS connector patterns (OAuth, rate limiting, API versioning), Google Workspace delegation, and small SaaS connectors (Jira, Confluence, Slack, Workday, HubSpot, Google Sheets). Unstructured connector shared patterns.
---

# SaaS Connectors (Shared)

## Official Docs

- [About Openflow connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/about-openflow-connectors)

## SPCS Domain Allowlists -- Small Connectors

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

For LinkedIn Ads, Meta Ads, Amazon Ads, and Google Ads domain allowlists, see `references/connectors/ads-connectors.md`.

### Google Sheets

| Domain | Notes |
|--------|-------|
| `sheets.googleapis.com` | Sheets API |

### Jira Cloud

| Domain | Notes |
|--------|-------|
| `<company>.atlassian.net` | Customer-specific Jira instance |
| `api.atlassian.com` | Atlassian API |

### Confluence

| Domain | Notes |
|--------|-------|
| `<company>.atlassian.net` | Customer-specific Confluence instance |
| `api.atlassian.com` | Atlassian API (OAuth, shared with Jira) |

### HubSpot

| Domain | Notes |
|--------|-------|
| `api.hubapi.com` | HubSpot API |

### Slack

| Domain | Notes |
|--------|-------|
| `slack.com` | Slack |
| `api.slack.com` | Slack API |
| `hooks.slack.com` | Slack webhooks |
| `files.slack.com` | Slack files |
| `wss-primary.slack.com` | Slack WebSocket |
| `wss-backup.slack.com` | Slack WebSocket (backup) |

### Workday

| Domain | Notes |
|--------|-------|
| `<company>.myworkday.com` | Customer-specific Workday tenant |

### AWS Secrets Manager

| Domain | Notes |
|--------|-------|
| `secretsmanager.<region>.amazonaws.com` | Secrets Manager endpoint |
| `sts.<region>.amazonaws.com` | AWS STS |

## Parameters & Required Assets

Most SaaS connectors require customer-managed source credentials or OAuth app configuration, plus the standard Openflow destination parameters in `references/connectors/connector-shared-generic.md`.

Public connector setup pages exist in the production docs for [Google Drive](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-drive/about), [Google Sheets](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-sheets/about), [SharePoint](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sharepoint/about), [Box](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/box/about), [Jira Cloud](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/jira-cloud/about), [Microsoft Dataverse](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/dataverse/about), [Amazon Ads](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/amazon-ads/about), [LinkedIn Ads](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/linkedin-ads/about), [Meta Ads](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/meta-ads/about), [Slack](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/slack/about), [Workday](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/workday/about), [Google Ads](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-ads/about). Use those connector-specific pages when linking customers.

If the routed connector does not have a connector-specific public Openflow page in the production docs tree, for example HubSpot or Confluence, use the generic troubleshooting guidance in this file and customer-owned Openflow UI checks rather than citing unpublished or internal material.

## Common Troubleshooting

### OAuth / API Authentication Failures

**Pattern:** Errors from source processors (`CaptureSharepointChanges`, `CaptureGoogleDriveChanges`, `Consume File Events`, etc.) indicating authentication failures.

**Common causes:**
- OAuth access token expired and refresh token is also expired
- API scope or permissions changed on the source system
- Service account credentials rotated
- Connected app / API key revoked

**Snowsight Checks:**


```sql
SELECT
  timestamp,
  TRY_PARSE_JSON(value):"formattedMessage"::STRING AS message,
  TRY_PARSE_JSON(value):"throwable":"message"::STRING AS error_message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND TRY_PARSE_JSON(value):"level"::STRING = 'ERROR'
  AND (value ILIKE '%unauthorized%'
       OR value ILIKE '%401%'
       OR value ILIKE '%403%'
       OR value ILIKE '%token%expired%'
       OR value ILIKE '%authentication%'
       OR value ILIKE '%InvalidAuthenticationToken%')
ORDER BY timestamp DESC
LIMIT 50;
```

**Recommended Action:**
1. Guide the customer to verify their source system credentials are still valid
2. For OAuth-based connectors: if the token has expired, the connector's controller service needs to be re-authenticated. This is a customer-owned credential update.
3. For service account connectors: verify the service account key has not expired or been rotated
4. Verify API access scopes have not been reduced on the source system

### Google Workspace Delegation User

**Pattern:** `GCPCredentialsControllerService` errors such as `'Delegation User' is invalid because Delegation User is required`.

**Likely Cause:** The connector is configured for Google Workspace domain-wide delegation, but the delegated user email is missing or invalid.

**Recommended Action:** Guide the customer to set the `Delegation User` parameter to the Google Workspace admin or delegated user email associated with their domain-wide delegation setup.

### Rate Limiting

**Pattern:** Errors containing HTTP 429, "Too Many Requests", "rate limit", or "throttled".

**Snowsight Checks:**


```sql
SELECT timestamp, TRY_PARSE_JSON(value):"formattedMessage"::STRING AS message
FROM {event_table}
WHERE record_type = 'LOG'
  AND timestamp >= COALESCE(TRY_TO_TIMESTAMP_TZ('{start_time}')::TIMESTAMP_NTZ, DATEADD(hour, -{hours_back}, CURRENT_TIMESTAMP()))
  AND timestamp <= COALESCE(TRY_TO_TIMESTAMP_TZ('{end_time}')::TIMESTAMP_NTZ, CURRENT_TIMESTAMP())
  AND resource_attributes:"k8s.namespace.name"::STRING = '{namespace}'
  AND (value ILIKE '%429%' OR value ILIKE '%rate limit%' OR value ILIKE '%throttl%')
ORDER BY timestamp DESC
LIMIT 50;
```

**Recommended Action:**
- Rate limiting is typically transient and self-resolving. The connector will retry automatically.
- If rate limiting is persistent, the customer may need to:
  - Request a higher API rate limit from the source system provider
  - Spread ingestion across off-peak hours
  - Reduce the volume or frequency of requests if the connector exposes that control in a documented setting

### Connector-Specific Notes

**Workday:**
- RAAS report URLs must use the exact format: `https://<tenant>.myworkday.com/ccx/service/<tenant>/<report_owner>/<report_name>?format=json`
- Incorrect tenant name or report path results in 404 errors, not authentication errors.

**HubSpot:**
- HubSpot has migrated from API keys to OAuth (private apps). API key-based connectors will stop working. The customer needs to create a Private App and reconfigure the connector with OAuth credentials.
- Rate limit: 100 calls per 10 seconds per private app. Burst above this causes 429 errors with a `Retry-After` header.

### API Version Compatibility

**Pattern:** Errors mentioning unsupported API version, deprecated endpoints, or unexpected response formats.

**Recommended Action:**
1. Check if the connector version is current -- run Connector Versions from `references/core-queries-resource.md`
2. If the connector is outdated, it needs to be upgraded to the latest version via the Openflow UI connector gallery. This is a customer-owned upgrade step.
3. If already on the latest version and the error persists, this may be a product defect. Escalate with the API error details and connector version.

---

## Google Sheets

### Delegation and Credential Checks

If Google Sheets is using Google Workspace delegation, also check the `Google Workspace Delegation User` section above. Missing delegation is a separate setup issue from sheet-content or destination SQL failures.

---

## Unstructured Connector Shared Patterns

Applies to SharePoint, Google Drive, and Box unstructured connectors. For connector-specific troubleshooting, load:
- SharePoint: `references/connectors/sharepoint.md`
- Google Drive: `references/connectors/google-drive.md`
- Box: `references/connectors/box.md`

### Snowflake-Side Destination Failures

If the failing processor is `SnowflakeDetectDuplicate`, `UpdateSnowflakeDatabase`, `ExecuteSQL`, or another Snowflake-side processor:
- Treat this as a shared destination issue first, not a source API issue
- Common causes: missing warehouse, invalid role, missing destination table, or insufficient privileges
- Load `references/connectors/connector-shared-generic.md` for `Destination Configuration Errors` or `Destination SQL Errors`

`SnowflakeDetectDuplicate` is used to check and persist file deduplication state in Snowflake. It depends on a working `SnowflakeConnectionService` and an active warehouse.

**Customer-run.** The queries below target the connector's destination tables in the customer's Snowflake account, not the event table. Replace `doc_metadata` and `docs_chunks` with the actual destination table names, qualified with the customer's destination database and schema.

### Customer State Inspection Queries

**Files ingested (stage destination):**
```sql
SELECT file_name FROM doc_metadata;
```

**Files ingested (Cortex Search destination):**
```sql
SELECT DISTINCT metadata:fullName::STRING AS file_name FROM docs_chunks;
```
