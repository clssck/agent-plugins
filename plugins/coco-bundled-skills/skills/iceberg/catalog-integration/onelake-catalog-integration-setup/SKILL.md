---
name: onelake-catalog-integration-setup
description: "Setup and verify catalog integration for Microsoft Fabric OneLake REST (public connectivity only — PrivateLink is NOT supported). Triggers: create onelake catalog integration, connect snowflake to onelake, setup onelake irc, configure onelake iceberg rest, fabric lakehouse snowflake, oauth onelake, query onelake tables from snowflake, iceberg rest api onelake, troubleshoot onelake integration, verify onelake catalog integration, fix onelake connection, debug onelake iceberg, azure oauth onelake."
---

# Microsoft Fabric OneLake REST Catalog Integration

Setup, verify, or troubleshoot a Snowflake catalog integration for Microsoft Fabric OneLake.

> **⚠️ PrivateLink is NOT supported for OneLake catalog integrations.** This skill only supports public connectivity. If the user asks about PrivateLink or private connectivity for OneLake, inform them that PrivateLink is not supported for OneLake catalog integrations and proceed with public connectivity only.

## Intent Routing (FIRST)

**Ask the user**:
```
What would you like to do?

A: Create a new catalog integration for OneLake REST
   → Setup Snowflake to connect to Microsoft Fabric OneLake

B: Verify an existing catalog integration
   → Test connection and list namespaces/tables

C: Troubleshoot a catalog integration
   → Diagnose and fix connection issues
```

**Route based on response**:
- **A (Create)** → **Load** `setup/SKILL.md` then follow [Create Workflow](#create-workflow)
- **B (Verify)** → **Load** `verify/SKILL.md` then follow [Verify Workflow](#verify-workflow)
- **C (Troubleshoot)** → **Load** `references/troubleshooting.md` then follow [Troubleshoot Workflow](#troubleshoot-workflow)

---

## Create Workflow

> **⚠️ REQUIRED**: Load `setup/SKILL.md` FIRST before proceeding with this workflow.

Create a new catalog integration to connect Snowflake to Microsoft Fabric OneLake.

### Step 1: Prerequisites

Follow `setup/SKILL.md` to collect one-by-one:
1. Confirm Microsoft Fabric setup exists (workspace with Iceberg tables)
2. Workspace ID
3. Data item ID (lakehouse ID)
4. Azure Entra application registration (OAuth client ID, tenant ID, OAuth client secret)
5. Application has `user_impersonation` permission for Azure Storage
6. User's application has Contributor access to Fabric workspace (separate from Snowflake multi-tenant app added later)
7. Integration name
8. External volume name

**⚠️ STOP**: Confirm prerequisites before proceeding

### Step 2: Create Integration

**Load** `create/SKILL.md` and follow its workflow:

> **Note**: If any step below fails, `create/SKILL.md` will present the error and load `references/troubleshooting.md` for diagnosis. Wait for user direction before attempting fixes.

1. Generate CREATE CATALOG INTEGRATION SQL
2. **⚠️ STOP**: Review SQL with user
3. Execute creation
4. Generate CREATE EXTERNAL VOLUME SQL
5. **⚠️ STOP**: Review SQL with user
6. Execute external volume creation
7. Retrieve Azure consent URL and multi-tenant app name
8. **⚠️ STOP**: Guide user to grant Azure consent
9. Guide user to add Snowflake multi-tenant app to Fabric workspace
10. Confirm consent and workspace access granted

### Step 3: Verify (MANDATORY — ALWAYS Run After Create)

> **⚠️ CRITICAL**: You MUST ALWAYS execute `SYSTEM$VERIFY_CATALOG_INTEGRATION` after the catalog integration and external volume are created and consent is granted. This is NOT optional. Do NOT skip verification, do NOT end the workflow early, and do NOT present "next steps" until verification has been executed and results confirmed.

The create workflow (`create/SKILL.md`) includes a **mandatory** `SYSTEM$VERIFY_CATALOG_INTEGRATION` step (Step 2.11) that runs automatically after consent is granted. Verification is not a separate workflow — it is the final step of creation.

If verification fails during creation, the troubleshooting workflow is invoked from within `create/SKILL.md`.

---

## Verify Workflow

> **⚠️ REQUIRED**: Load `verify/SKILL.md` FIRST before proceeding with this workflow.

Verify an existing catalog integration is working correctly.

### Step V1: Get Integration Name

**Ask**: "What is the name of your catalog integration?"

If user doesn't know:
```sql
SHOW CATALOG INTEGRATIONS;
```

### Step V2: Check Integration Status

Follow `verify/SKILL.md` which loads the shared verification workflow.

Run verification checks:
```sql
-- Check integration exists and is enabled
SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';

-- Verify connection
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');

-- List namespaces
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');

-- List tables in a namespace
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<namespace>');
```

### Step V3: Report Results

**If all checks pass**:
```
✅ Integration verified successfully
- Status: ENABLED
- Connection: Working
- Namespaces: <count> discovered
- Tables: Accessible
```

**If any check fails** → Continue to [Troubleshoot Workflow](#troubleshoot-workflow)

### Step V4: Next Steps

**If verification succeeded**:

**Load** `shared/next-steps/SKILL.md` (path: `../shared/next-steps/SKILL.md`)

Guide user through options for accessing catalog tables:
- Option A: Create individual Iceberg tables
- Option B: Create catalog-linked database (recommended)

---

## Troubleshoot Workflow

> **⚠️ REQUIRED**: Load `references/troubleshooting.md` to have error patterns and solutions available.

Diagnose and fix issues with an existing catalog integration.

### Step T1: Get Integration Name

**Ask**: "What is the name of your catalog integration?"

### Step T2: Gather Error Information

**Ask**: "What error or issue are you experiencing?"

Common symptoms:
- Integration creation failed
- Verification returns error
- Cannot list namespaces
- Cannot see tables
- OAuth authentication errors
- Azure consent not granted

### Step T3: Diagnose

Use error patterns from `references/troubleshooting.md` to diagnose.

Run diagnostics:
```sql
-- Check integration details
DESC CATALOG INTEGRATION <integration_name>;

-- Test connection
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

### Step T4: Match Error Pattern

Common issues and solutions in `references/troubleshooting.md`:
1. OAuth authentication failure (invalid client ID/secret)
2. Invalid token endpoint URL
3. Azure consent not granted or Snowflake multi-tenant app not in Fabric workspace
4. Missing `user_impersonation` permission
5. Invalid workspace ID or data item ID
6. OAuth scopes mismatch
7. External volume consent URL not working
8. Fabric tenant settings not enabled

**⚠️ STOP**: Present diagnosis and wait for user direction before applying fixes.

---

## Scope

This skill focuses on **Snowflake-side setup**:
- ✅ Creating catalog integrations for OneLake REST (public connectivity only)
- ✅ OAuth authentication configuration with Azure Entra
- ✅ External volume creation for OneLake
- ✅ Azure consent and Fabric workspace access configuration
- ✅ Verification
- ✅ Troubleshooting

**Not supported**:
- ❌ PrivateLink / private connectivity for OneLake catalog integrations
- ❌ Microsoft Fabric workspace setup
- ❌ Creating Iceberg tables in Fabric/OneLake
- ❌ Writing Iceberg tables TO OneLake (uses Snowflake-managed catalog with `CATALOG = 'SNOWFLAKE'`, not a catalog integration — see [Microsoft Fabric documentation](https://learn.microsoft.com/en-us/fabric/onelake/onelake-iceberg-snowflake))
- ❌ Creating tables or catalog-linked databases (use shared `next-steps` skill)

---

## Quick Reference

<!-- Keep in sync with create/SKILL.md -->
**Catalog Integration SQL**:
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://onelake.table.fabric.microsoft.com/iceberg'
    CATALOG_NAME = '<workspace_id>/<data_item_id>'
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_TOKEN_URI = 'https://login.microsoftonline.com/<entra_tenant_id>/oauth2/v2.0/token'
    OAUTH_CLIENT_ID = '<entra_oauth_client_id>'
    OAUTH_CLIENT_SECRET = '<entra_oauth_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('https://storage.azure.com/.default')
  )
  ENABLED = TRUE;
```

<!-- Keep in sync with create/SKILL.md -->
**External Volume SQL**:
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE EXTERNAL VOLUME <name>
  STORAGE_LOCATIONS = (
    (
      NAME = '<storage_location_name>'
      STORAGE_PROVIDER = 'AZURE'
      STORAGE_BASE_URL = 'azure://onelake.dfs.fabric.microsoft.com/<workspace_id>/<data_item_id>'
      AZURE_TENANT_ID = '<entra_tenant_id>'
    )
  )
  ALLOW_WRITES = FALSE;
```

> **OneLake notes**:
> - `CATALOG_URI` is always `https://onelake.table.fabric.microsoft.com/iceberg` (fixed endpoint)
> - `CATALOG_NAME` is the Fabric data item scope: `<workspace_id>/<data_item_id>`
> - Authentication uses OAuth with Azure Entra application credentials
> - `OAUTH_ALLOWED_SCOPES` must be `('https://storage.azure.com/.default')`
> - External volume requires Azure consent (AZURE_CONSENT_URL) and Fabric workspace access for the Snowflake multi-tenant app
> - Snowflake only supports **read operations** for tables in OneLake
> - **Vended credentials are not supported** for OneLake. Access delegation always uses external volume credentials (the default).

**Diagnostic Commands**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<name>';
DESC CATALOG INTEGRATION <name>;
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<name>');
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<name>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<name>', '<namespace>');
DESC EXTERNAL VOLUME <name>;
```

---

## Success Criteria

- ✅ Catalog integration created and shows `ENABLED=TRUE`
- ✅ External volume created successfully
- ✅ Azure consent granted for Snowflake multi-tenant app
- ✅ Snowflake multi-tenant app added to Fabric workspace with Contributor access
- ✅ `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns success
- ✅ Namespaces discoverable
- ✅ Tables visible

---

## Documentation

- [Configure Catalog Integration for OneLake REST](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-onelake)
- [CREATE CATALOG INTEGRATION (Apache Iceberg REST)](https://docs.snowflake.com/en/sql-reference/sql/create-catalog-integration-apache-iceberg-rest)
- [Snowflake Iceberg Tables](https://docs.snowflake.com/user-guide/tables-iceberg)
- [CREATE DATABASE (catalog-linked)](https://docs.snowflake.com/sql-reference/sql/create-database-catalog-linked)
- [OneLake Table APIs for Iceberg](https://learn.microsoft.com/en-us/fabric/onelake/onelake-table-api-iceberg) (Microsoft documentation)
