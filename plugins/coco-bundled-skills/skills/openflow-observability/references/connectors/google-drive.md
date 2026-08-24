---
name: openflow-observability-connector-google-drive
description: Google Drive unstructured connector troubleshooting and SPCS domain allowlist.
---

# Google Drive (Unstructured)

## Official Docs

- [About](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-drive/about)
- [Setup](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-drive/setup)

## SPCS Domain Allowlist

> **Note:** Verify against the latest [Configure allowed domains for connectors](https://docs.snowflake.com/en/user-guide/data-integration/openflow/setup-openflow-spcs-sf-allow-list) page if connector versions have been updated.

| Domain | Notes |
| --- | --- |
| `drive.google.com` | Drive access |
| `www.googleapis.com` | Google APIs |
| `oauth2.googleapis.com` | OAuth authentication |

## Root Processor

| Source | Root Processor | Controller Service Verification |
| --- | --- | --- |
| Google Drive | `CaptureGoogleDriveChanges` | Not supported |

## Troubleshooting

### Google Workspace Delegation User

If this connector uses Google Workspace domain-wide delegation, the `Delegation User` parameter must be set to the admin or delegated user email. See [Google Workspace Delegation User](saas-connectors.md#google-workspace-delegation-user) for full diagnostics.

### Single File Not Ingested

1. **File not under specified folder:** Only the configured folder and its subfolders are discovered.
2. **File extension filtered:** Check `File Extensions To Ingest` parameter. Use Data Provenance (right-click on canvas > Data Provenance) and filter for `DROP` events from filter processors.
3. **Cortex Search only -- document parsing failed:** Check the `PerformSnowflakeCortexOCR` processor logs for parsing errors.

---

For shared SaaS patterns (OAuth failures, rate limiting, API versioning), load `references/connectors/saas-connectors.md`. For shared Snowflake-side destination failures and customer state inspection queries for unstructured connectors, see [Unstructured Connector Shared Patterns](saas-connectors.md#unstructured-connector-shared-patterns), and load `connector-shared-generic.md` for the destination-side diagnosis itself.
