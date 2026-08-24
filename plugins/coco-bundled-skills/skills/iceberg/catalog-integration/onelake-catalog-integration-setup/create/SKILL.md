---
name: onelake-create-integration
description: "Create and execute catalog integration and external volume for OneLake REST"
parent_skill: onelake-catalog-integration-setup
---

# Configuration & Creation

Build and execute the SQL to create your OneLake REST catalog integration and external volume, then configure Azure consent and Fabric workspace access for Snowflake.

## When to Load

From main skill Step 2: After prerequisites have been gathered and confirmed

## Prerequisites

Must have from setup phase:
- Workspace ID
- Data item ID (lakehouse ID)
- Azure Entra OAuth client ID
- Azure Entra tenant ID
- Azure Entra OAuth client secret
- Integration name
- External volume name

## Workflow

### Step 2.1: Generate Catalog Integration SQL

Based on the collected prerequisites, generate the CREATE CATALOG INTEGRATION statement.

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
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

**Parameter Explanation**:
- `CATALOG_SOURCE = ICEBERG_REST`: Generic REST catalog (OneLake uses Iceberg REST API)
- `TABLE_FORMAT = ICEBERG`: Apache Iceberg table format
- `CATALOG_URI`: Fixed OneLake table API endpoint (`https://onelake.table.fabric.microsoft.com/iceberg`)
- `CATALOG_NAME`: Fabric data item scope in the form `<workspaceID>/<dataItemID>`
- `TYPE = OAUTH`: OAuth 2.0 client credentials flow
- `OAUTH_TOKEN_URI`: Azure AD token endpoint using the Entra tenant ID
- `OAUTH_CLIENT_ID`: OAuth client ID from Azure Entra app registration (also known as Application (client) ID on the Overview page)
- `OAUTH_CLIENT_SECRET`: OAuth client secret from Azure Entra app registration
- `OAUTH_ALLOWED_SCOPES`: Must be `('https://storage.azure.com/.default')` — the storage token audience

> **⚠️ OneLake limitation**: Catalog-vended credentials are **not supported** for OneLake. Access delegation always uses external volume credentials (the default). Do not set `ACCESS_DELEGATION_MODE` — it is not applicable.

### Step 2.2: Review & Approval (Catalog Integration)

**Present generated SQL to user**:

```
Generated Catalog Integration SQL:
═══════════════════════════════════════════════════════════
[The complete SQL with actual values filled in]
═══════════════════════════════════════════════════════════

This will create a catalog integration named '<integration_name>'
connecting to Microsoft Fabric OneLake using the OneLake table API
with OAuth authentication via Azure Entra.

IMPORTANT: After this, we will also need to create an external volume
and configure Azure consent for Snowflake's multi-tenant app.
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Please review the SQL above. Ready to execute and create the catalog integration?"

**Wait for explicit approval**:
- "Yes", "Approved", "Looks good", "Proceed" → Continue to Step 2.3
- "No" or "Wait" → Ask: "What changes would you like to make?"

### Step 2.3: Execute Catalog Integration Creation

**Execute approved SQL**:
```sql
[The approved CREATE CATALOG INTEGRATION statement]
```

**Expected Success Result**:
```
Integration <integration_name> successfully created.
```

**If Success**: ✓ Integration created → Continue to Step 2.4

**If Error**: Present error → Load `references/troubleshooting.md` → Wait for direction

### Step 2.4: Generate External Volume SQL

The external volume provides Snowflake access to the OneLake storage location.

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE EXTERNAL VOLUME <extvol_name>
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

**Parameter Explanation**:
- `NAME`: A name for this storage location within the external volume (can be the same as or different from the external volume name). **Default to the external volume name** if the user does not specify a separate value — do not ask the user for this separately.
- `STORAGE_PROVIDER = 'AZURE'`: Microsoft Azure storage
- `STORAGE_BASE_URL`: OneLake DFS endpoint with workspace and data item IDs
- `AZURE_TENANT_ID`: Your Azure Entra tenant ID
- `ALLOW_WRITES = FALSE`: OneLake integration is read-only

### Step 2.5: Review & Approval (External Volume)

**Present generated SQL to user**:

```
Generated External Volume SQL:
═══════════════════════════════════════════════════════════
[The complete SQL with actual values filled in]
═══════════════════════════════════════════════════════════

This will create an external volume named '<extvol_name>'
pointing to your OneLake storage location.

After creation, we'll need to configure Azure consent.
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Please review the SQL above. Ready to execute and create the external volume?"

**Wait for explicit approval** before proceeding.

### Step 2.6: Execute External Volume Creation

**Execute approved SQL**:
```sql
[The approved CREATE EXTERNAL VOLUME statement]
```

**If Success**: ✓ External volume created → Continue to Step 2.7

**If Error**: Present error → Load `references/troubleshooting.md` → Wait for direction

### Step 2.7: Retrieve Azure Consent URL and Multi-Tenant App Name

Now retrieve the Azure consent URL and Snowflake multi-tenant app name needed to authorize Snowflake's access.

**Execute**:
```sql
DESC EXTERNAL VOLUME <extvol_name>;
```

**Extract these values from output**:

| Property | Description |
|----------|-------------|
| `AZURE_CONSENT_URL` | URL to the Microsoft permissions request page |
| `AZURE_MULTI_TENANT_APP_NAME` | Name of the Snowflake client application created for your account |

**Present to user**:

The `AZURE_MULTI_TENANT_APP_NAME` value returned by DESC has the format `<app_name>_<numeric_suffix>`. To get the actual app name:

1. Take the full value (e.g., `abc12tsnowflakepacint_1234567890123`)
2. **Strip the underscore and numeric suffix** (e.g., `abc12tsnowflakepacint`)
3. Use ONLY the stripped name everywhere: Azure consent, Fabric workspace search, and any user-facing instructions
4. The numeric suffix is an internal identifier and must be omitted

```
Azure Consent Configuration:
─────────────────────────────────────────
Consent URL:          <AZURE_CONSENT_URL>
Multi-Tenant App Name: <app_name WITHOUT numeric suffix>
                       (e.g., "abc12tsnowflakepacint",
                        NOT "abc12tsnowflakepacint_1234567890123")
─────────────────────────────────────────

These values are needed in the next steps to grant Azure consent
and add the Snowflake app to your Fabric workspace.
```

### Step 2.8: Grant Azure Consent

**Present instructions to user**:

```
Azure Consent Configuration:
═══════════════════════════════════════════════════════════

Step 1: Grant Azure Consent

1. Open the following URL in a web browser:
   <AZURE_CONSENT_URL>

2. Sign in with your Azure account

3. Click "Accept" to allow the Snowflake service principal
   to obtain access tokens for your storage

═══════════════════════════════════════════════════════════
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Have you navigated to the consent URL and clicked Accept?"

**Wait for confirmation** before proceeding.

### Step 2.9: Add Snowflake Multi-Tenant App to Fabric Workspace

**Present instructions to user**:

```
Fabric Workspace Access Configuration:
═══════════════════════════════════════════════════════════

Now grant the Snowflake multi-tenant app access to your
Fabric workspace:

1. Navigate to Microsoft Fabric (https://app.fabric.microsoft.com)
2. Sign in
3. Open your workspace
4. Select "Manage access"
5. Select "+ Add people or groups"
6. In the "Enter name or email" field, search for
   the Multi-Tenant App Name provided above
   (e.g., "abc12tsnowflakepacint")
7. From the drop-down menu, select "Contributor" access or higher
8. Select "Add"

═══════════════════════════════════════════════════════════
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Have you added the Snowflake multi-tenant app to your Fabric workspace with Contributor access?"

**Wait for confirmation** before proceeding.

### Step 2.10: Summary

**Present summary to user**:

```
Configuration Complete:
═══════════════════════════════════════════════════════════

Catalog Integration: <integration_name>
  - Connected to OneLake table API
  - OAuth authentication configured

External Volume: <extvol_name>
  - Storage location: azure://onelake.dfs.fabric.microsoft.com/<workspace_id>/<data_item_id>
  - Azure consent: Granted
  - Fabric workspace access: Granted

═══════════════════════════════════════════════════════════

Next step: Verifying the integration now...
```

### Step 2.11: Verify Catalog Integration (MANDATORY — DO NOT SKIP)

> **⚠️ CRITICAL: This step is MANDATORY and must ALWAYS be executed.** You MUST run `SYSTEM$VERIFY_CATALOG_INTEGRATION` immediately after creation and consent configuration. Do NOT end the workflow, summarize results, or present "next steps" until this verification has been executed and results confirmed. Skipping this step is a workflow violation.

**Execute**:
```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

**Expected Success Response**:
```json
{
  "success" : true,
  "errorCode" : "",
  "errorMessage" : ""
}
```

**If Success**: Present to user: "Catalog integration verified — end-to-end connectivity to OneLake is confirmed."

**Output**: Catalog integration and external volume created, consent configured, and connectivity verified. The skill ends here.

**If Failure**: Present the error message → Load `references/troubleshooting.md` → **⚠️ MANDATORY STOPPING POINT**: Wait for user direction before attempting fixes.

## Stopping Points

- ✋ **Step 2.2**: Review catalog integration SQL before execution
- ✋ **Step 2.5**: Review external volume SQL before execution
- ✋ **Step 2.8**: Wait for user to grant Azure consent
- ✋ **Step 2.9**: Wait for user to add multi-tenant app to Fabric workspace
- ✋ **Step 2.11 (failure)**: Wait for user direction before attempting fixes

**Resume rule:** Upon user confirmation, proceed directly to next step without re-asking.

## Error Handling

**Common errors during catalog integration creation**:
- **Invalid OAuth client ID or OAuth client secret**: Verify values from Azure Entra app registration
- **Invalid tenant ID**: Check the Directory (tenant) ID from app registration Overview page
- **Permission denied**: Check Snowflake privileges for creating integrations

**Common errors during external volume creation**:
- **Invalid storage URL**: Verify workspace ID and data item ID format
- **Invalid tenant ID**: Verify Azure Entra tenant ID

**Common errors during consent/access**:
- **Consent URL doesn't load**: Verify the external volume was created successfully and DESC returns the URL
- **Can't find multi-tenant app in Fabric**: Search by the app name WITHOUT the numeric suffix (strip the `_<numbers>` portion from AZURE_MULTI_TENANT_APP_NAME)
- **Permission denied in Fabric**: Ensure you have Contributor access or higher on the workspace to manage access

**For all errors**: Present error message clearly and load troubleshooting guide if needed.

## Output

Successfully created catalog integration and external volume with Azure consent configured and connectivity verified via `SYSTEM$VERIFY_CATALOG_INTEGRATION`.

## Next Steps

After successful creation, consent, and verification:
- Return to main skill
- The create workflow is complete — no further steps required
