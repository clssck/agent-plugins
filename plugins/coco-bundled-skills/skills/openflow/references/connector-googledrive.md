---
name: openflow-connector-googledrive
description: Google Drive CDC connector for syncing Shared Drives to Snowflake with Cortex Search integration. Use for Google Drive unstructured data ingestion.
---

# Google Drive CDC Connector

Syncs files from Google Shared Drives to Snowflake with Cortex Search integration.

**Official Documentation:** https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-drive/setup

**Flow Name:** `unstructured-google-drive-cdc`

**Note:** These operations modify service state. Apply the Check-Act-Check pattern from `references/core-guidelines.md`.

## Scope

This reference covers:
- Google Drive CDC connector (`unstructured-google-drive-cdc`)
- Google Cloud prerequisites and configuration
- Cortex Search integration

For other connectors, see `references/connector-main.md`.

## Collect Checklist

Gather this information from the user **before** proceeding with deployment.

### Google Configuration (Required)

| Item | How to Obtain | Collected |
|------|---------------|-----------|
| Google Drive ID | From Shared Drive URL: `drive.google.com/drive/folders/<DRIVE-ID>` | [ ] |
| Google Folder Name | Folder to filter, or `""` for all files | [ ] |
| Google Delegation User | Email with access to Shared Drive | [ ] |
| Google Domain | Extract from delegation user email (e.g., `company.com`) | [ ] |
| GCP Service Account JSON | Download from Google Cloud Console (sensitive) | [ ] |

### Snowflake Configuration (Required)

| Item | Description | Collected |
|------|-------------|-----------|
| Destination Database | Database for chunks and search data | [ ] |
| Destination Schema | Schema within database | [ ] |
| Snowflake Role | Role with CREATE SCHEMA privileges | [ ] |
| Snowflake Warehouse | Warehouse for processing | [ ] |
| Cortex Search User Role | Role that can use the search service | [ ] |

### Prerequisites Checklist

| Prerequisite | Status |
|--------------|--------|
| User has reviewed [official Snowflake documentation](https://docs.snowflake.com/en/user-guide/data-integration/openflow/connectors/google-drive/setup) | [ ] |
| Service Account created with Domain-Wide Delegation | [ ] |
| OAuth scopes configured in Google Workspace Admin | [ ] |
| Delegation user has access to Shared Drive | [ ] |
| Confirmed target is a Shared Drive (not regular folder) | [ ] |

**Do not proceed until all items are collected and prerequisites confirmed.**

---

## Deployment Workflow

Follow the main workflow in `references/connector-main.md`. This section provides connector-specific details for each step.

### 1. Network Access (SPCS Only)

See `references/platform-eai.md` for EAI setup.

### 2. Network Validate (SPCS Only)

**Load** `references/ops-network-testing.md` and test connectivity to Google endpoints.

Test targets for this connector:
```python
targets = [
    {"host": "drive.google.com", "port": 443, "type": "HTTPS"},
    {"host": "www.googleapis.com", "port": 443, "type": "HTTPS"},
    {"host": "oauth2.googleapis.com", "port": 443, "type": "HTTPS"},
    {"host": "admin.googleapis.com", "port": 443, "type": "HTTPS"},
    {"host": "accounts.google.com", "port": 443, "type": "HTTPS"},
]
```

**If any tests fail:** Stop and resolve EAI configuration before proceeding.

### 3. Deploy

See `references/ops-flow-deploy.md`. Flow name: `unstructured-google-drive-cdc`

### 4. Handle Parameters

See [Parameters](#parameters) below, then `references/ops-parameters-main.md` for configuration commands.

### 5. Asset Uploads

**None required.** This connector uses text parameters only.

**Note on GCP Service Account JSON:** The user provides a `.json` file downloaded from Google Cloud Console. Read the file content and JSON-escape it when setting the parameter. Do not upload as an asset.

### 6. Processor Updates

See [Processor Configuration](#processor-configuration) below.

### 7. Verify Controllers

Verify controller configuration BEFORE enabling:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_processors=false
```

**If verification fails:** Fix parameter configuration before proceeding.

### 8. Enable Controllers

Enable controller services after verification passes.

See `references/ops-flow-lifecycle.md` (Enable Controllers Only section).

After enabling, check for errors:
- All controllers show `ENABLED`
- Check bulletins for authentication or connection errors

### 9. Verify Processors

Verify processor configuration AFTER controllers are enabled:

```bash
nipyapi --profile <profile> ci verify_config --process_group_id "<pg-id>" --verify_controllers=false
```

**If verification fails:** Check processor dependencies and parameter values.

### 10. Start

See `references/ops-flow-lifecycle.md` for starting the flow.

### 11. Validate

After starting, validate data is flowing. See [Validate Data Flow](#validate-data-flow) below.

---

## Parameters

### Google-Specific Parameters

| Parameter | Description | How to Obtain |
|-----------|-------------|---------------|
| Google Drive ID | Shared Drive ID (NOT a folder ID) | From URL: `drive.google.com/drive/folders/<DRIVE-ID>` |
| Google Folder Name | Filter to folder, or `""` for all | **Must always be set** (empty string for root) |
| Google Delegation User | Email with Shared Drive access | User's Google Workspace email |
| Google Domain | Google Workspace domain | Extract from delegation user email |
| GCP Service Account JSON | Full JSON key content (sensitive) | User downloads from Google Cloud Console |

**Important:** The Google Drive ID must be a Shared Drive (Team Drive), not a regular folder.

**Sensitive values:** Ask user to provide directly. Cannot be read back once set. Never display these values - use `[REDACTED]` in confirmations.

### Snowflake Parameters

| Parameter | Description |
|-----------|-------------|
| Destination Database | Database for chunks and search data |
| Destination Schema | Schema within database |
| Snowflake Role | Role with CREATE SCHEMA privileges |
| Snowflake Warehouse | Warehouse for processing |

For Snowflake authentication, see `references/ops-snowflake-auth.md`.

### Cortex Search Parameters

| Parameter | Description |
|-----------|-------------|
| Snowflake Cortex Search Service User Role | Role that can use the search service |

---

## Processor Configuration

**CRITICAL:** Two processors require concurrent task adjustments for performance:

1. **Update Chunks Table** - Set to 8 concurrent tasks
   - Path: `Google Drive (Cortex Connect)` → `Update Snowflake Cortex` → `Update Chunks and Permissions`

2. **Fetch Google Drive** - Set to 4 concurrent tasks
   - Path: `Google Drive (Cortex Connect)` → `Process Google Drive Metadata` → `Fetch Google Drive`

```python
import nipyapi

pg_id = "<process-group-id>"

# Find the processor
processors = nipyapi.canvas.list_all_processors(pg_id)
proc = next(p for p in processors if p.component.name == "Update Chunks Table")

# Update concurrent tasks
config = nipyapi.nifi.ProcessorConfigDTO(concurrently_schedulable_task_count=8)
nipyapi.canvas.update_processor(proc, update=config)

# Verify
updated = nipyapi.canvas.get_processor(proc.id, "id")
assert updated.component.config.concurrently_schedulable_task_count == 8
```

---

### Extracting from Google Drive URL

If user provides `https://drive.google.com/drive/folders/0ABCxyz123`:
- **Google Drive ID:** `0ABCxyz123` (path after `/folders/`)
- **Google Domain:** Extract from user email (e.g., `user@company.com` → `company.com`)

Must be a Shared Drive (Team Drive), not a regular folder.

---

## Validate Data Flow

After starting, validate data is actually flowing to Snowflake.

### Step 1: Check Flow Status

```bash
nipyapi --profile <profile> ci get_status --process_group_id "<pg-id>"
```

Expect:
- `running_processors` > 0
- `invalid_processors` = 0
- `bulletin_errors` = 0

### Step 2: Check Data Landing

```sql
SELECT COUNT(*) FROM <database>.<schema>.DOCS_CHUNKS;
```

May take a few minutes for data to appear with many files.

### Step 3: Validate Cortex Search

Once data appears, verify the Cortex Search service is functional:

```sql
SELECT * FROM TABLE(<database>.<schema>.CORTEX_SEARCH_SERVICE('test query'));
```

---

## Cortex Search Integration

The connector creates:
- `DOCS_CHUNKS` table - Document chunks for search
- Cortex Search Service with permissions

---

## Known Issues

### StandardPrivateKeyService INVALID on SPCS or BYOC with Managed Token

Expected — the `Snowflake Private Key Service` controller is unused unless you use `KEY_PAIR` auth, so it shows INVALID. Impact: none. See `references/known-issues-common.md`.

---

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| UnknownHostException | Missing EAI | Create network rule for Google domains |
| Authentication failed | Invalid service account | Verify JSON, check domain-wide delegation |
| No data landing | Wrong Drive ID | Ensure using Shared Drive ID, not folder |
| Slow performance | Concurrent tasks = 1 | Set "Update Chunks Table" to 8 |
| StandardPrivateKeyService INVALID | Expected on SPCS and BYOC with managed token | Ignore |

---

## Next Step

After deployment and configuration, return to `references/connector-main.md` or the calling workflow.

## See Also

- `references/connector-main.md` - Connector workflow overview
- `references/ops-snowflake-auth.md` - Snowflake destination configuration
- `references/platform-eai.md` - Network access
- `references/ops-parameters-main.md` - Parameter configuration
