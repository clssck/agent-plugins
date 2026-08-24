---
name: openflow-connector-sharepoint
description: SharePoint connector for syncing document libraries to Snowflake. Covers all SharePoint variants including Stage and Cortex destinations.
---

# SharePoint Connector

Syncs files from SharePoint document libraries to Snowflake.

**Official Documentation:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sharepoint/setup

## Scope

This reference covers all SharePoint connector variants:

| Flow Name | Destination | ACL Support |
|-----------|-------------|-------------|
| `unstructured-sharepoint-to-stage-no-cortex` | Internal Stage | Yes |
| `unstructured-sharepoint-to-stage-no-cortex-no-acl` | Internal Stage | No |
| `unstructured-sharepoint-cdc` | Cortex Search | Yes |
| `unstructured-sharepoint-cdc-no-acl` | Cortex Search | No |

For other connectors, see `references/connector-main.md`.

---

## Collect Checklist

Gather this information **before** deployment. Refer to [official documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/sharepoint/setup) for current prerequisite requirements.

### SharePoint Configuration

| Item | How to Obtain |
|------|---------------|
| Site URL | Full URL: `https://<tenant>.sharepoint.com/sites/<sitename>` |
| Tenant ID | Entra Admin Center → Overview → Tenant ID |
| Client ID | App Registration → Application (client) ID |

### Sharepoint Authentication

| Item | Required |
|------|----------|
| Client Secret | Always |
| Certificate (PEM) + Private Key (PEM) | ACL connectors only |

### Optional Filtering

| Item | Description |
|------|-------------|
| Source Folder | Folder path to ingest (includes subfolders). Leave blank or `/` for root. |
| File Extensions | Comma-separated extensions (e.g., `pdf,docx`). Set empty string for all files. |
| Document Library Name | SharePoint library name to ingest from. |

### Snowflake Configuration

| Item | Description |
|------|-------------|
| Destination Database | Database for destination |
| Destination Schema | Schema within database |
| Role | Role with appropriate permissions |
| Warehouse | Warehouse for processing |

### Prerequisites Checklist

| Prerequisite | Status |
|--------------|--------|
| User has reviewed official Snowflake documentation | [ ] |
| App Registration created in Microsoft Entra ID | [ ] |
| API permissions granted and admin consent completed | [ ] |
| Authentication credentials ready (secret or certificate) | [ ] |

**Do not proceed until all items are collected.**

---

## Deployment Workflow

Follow `references/connector-main.md` for the standard workflow. This section provides SharePoint-specific details.

### Network Access (SPCS Only)

Required domains for EAI (see `references/platform-eai.md`):
- `<tenant>.sharepoint.com`
- `login.microsoftonline.com`
- `graph.microsoft.com`

Test connectivity using `references/ops-network-testing.md` with these targets:

```python
targets = [
    {"host": "<tenant>.sharepoint.com", "port": 443, "type": "HTTPS"},
    {"host": "login.microsoftonline.com", "port": 443, "type": "HTTPS"},
    {"host": "graph.microsoft.com", "port": 443, "type": "HTTPS"},
]
```

### Parameters

See `references/ops-parameters-main.md` for inspection and configuration process.

| Parameter | Required | Notes |
|-----------|----------|-------|
| Sharepoint Site URL | Always | |
| Sharepoint Tenant ID | Always | |
| Sharepoint Client ID | Always | |
| Sharepoint Client Secret | Always | Sensitive |
| Sharepoint Application Certificate | ACL connectors only | |
| Sharepoint Application Private Key | ACL connectors only | Sensitive |
| Sharepoint Source Folder | Optional | Folder and subfolders to ingest |
| File Extensions To Ingest | Optional | Empty String = all files |
| Sharepoint Document Library Name | Optional | Library to ingest from |
| Destination Database | Always | |
| Destination Schema | Always | |
| Snowflake Role | Always | SPCS: Use the execute-as role. BYOC: Service user role. |
| Snowflake Warehouse | Always | |
| Snowflake Authentication Strategy | Always | `SNOWFLAKE_MANAGED` (SPCS and BYOC runtime-role default) or `KEY_PAIR` (BYOC alternative). Legacy `SNOWFLAKE_SESSION_TOKEN` may be encountered on older SPCS deployments. |

**Sensitive values:** Ask user to provide directly. Cannot be read back once set. Never display these values - use `[REDACTED]` in confirmations.

### Asset Uploads

**None required.** This connector uses text parameters only.

### Processor Updates

**None required.** Use default configuration.

### Verify and Enable

Standard verification workflow applies. See `references/connector-main.md`.

**Known Issue:** `StandardPrivateKeyService` shows INVALID on managed-token deployments (expected — ignore). See `references/known-issues-common.md`.

---

## Validate Data Flow

After starting, verify data is flowing.

### Check Flow Status

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect: `running_processors` > 0, `invalid_processors` = 0, `bulletin_errors` = 0

### Check Destination

**For Stage connectors:**
```sql
LIST @<database>.<schema>.<stage_name>;
```

**For Cortex connectors:**
```sql
SELECT COUNT(*) FROM <database>.<schema>.DOCS_CHUNKS;
```

---

## Known Issues

### StandardPrivateKeyService INVALID on SPCS or BYOC with Managed Token

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID. Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| UnknownHostException | Missing EAI | Add Microsoft domains to network rule |
| Authentication failed | Invalid credentials | Verify secret/certificate, check Entra config |
| No files syncing | Wrong folder path | Verify `Source Folder` matches actual path |
| StandardPrivateKeyService INVALID | Expected on SPCS and BYOC with managed token | Ignore |
| Controller won't enable | Missing parameters | Check all auth parameters are set |

---

## See Also

- `references/connector-main.md` - Connector workflow
- `references/ops-parameters-main.md` - Parameter configuration
- `references/platform-eai.md` - Network access (SPCS)
- `references/ops-network-testing.md` - Network connectivity testing
