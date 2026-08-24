---
name: unitycatalog-create-integration
description: "Create and execute catalog integration for Unity Catalog"
parent_skill: unitycatalog-catalog-integration-setup
---

# Configuration & Creation

Build and execute the SQL to create your Unity Catalog catalog integration.

## When to Load

From main skill Step 2: After prerequisites have been gathered and confirmed

## Prerequisites

Must have from setup phase:
- Authentication choice (OAuth or Bearer Token)
- If OAuth: Client ID, Secret, Token URI, Scopes
- If Bearer: Personal Access Token (PAT)
- Access delegation mode choice
- Connectivity type (Public/Private)
- If Private (AWS): VPC endpoint service ID, workspace host name
- If Private (Azure): Workspace resource ID, workspace host name
- Catalog name and REST endpoint
- Integration name

## Workflow

### Step 2.0: PrivateLink Provisioning (Private Connectivity Only)

> **Skip this step if connectivity type is Public.** Proceed directly to [Step 2.1](#step-21-generate-catalog-integration-sql).

> **PrivateLink constraints**:
> - Requires **Business Critical Edition (or higher)**. To inquire about upgrading, please contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge).
> - Catalog-vended credentials are supported with PrivateLink. To also route Snowflake-to-storage traffic through PrivateLink, add `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` — see **Option C** below.
> - Requires ACCOUNTADMIN role for PrivateLink provisioning.
> - **Limit**: Snowflake accounts can have a maximum of **5 private endpoints**. Deprovisioned endpoints count toward this limit for 7 days. To increase the limit, contact Snowflake Support.

**Suggest the user verify their account edition** (do NOT execute — user must have access to the ORGANIZATION_USAGE schema):
```sql
SELECT EDITION
  FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
  WHERE ACCOUNT_NAME = CURRENT_ACCOUNT();
```
Must return `BUSINESS_CRITICAL` or higher. See: [Find your current edition](https://docs.snowflake.com/en/user-guide/intro-editions#find-your-current-edition).

**Before generating the catalog integration SQL, you must first provision the PrivateLink endpoint.**

#### Step 2.0a: Check for Existing PrivateLink Endpoint

Before provisioning, check if a PrivateLink endpoint for this Databricks workspace already exists:

```sql
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

Parse the JSON output and look for an entry matching the Databricks workspace:

**For AWS**: Look for an entry where `"host"` matches the Databricks workspace host name (e.g., `dbc-a1a11111-1a11.cloud.databricks.com`).

**For Azure**: Look for an entry where `"host"` matches the Databricks per-workspace URL host name (e.g., `adb-1234567890123456.12.azuredatabricks.net`) and `"subresource"` is `"databricks_ui_api"`.

**If endpoint already exists, status is "available", AND host matches the target workspace**: Skip provisioning (Step 2.0b) and proceed to Step 2.0c (verify), then to Step 2.0d.

**If endpoint already exists but host does NOT match the target workspace**: The endpoint is mapped to a different workspace. Do NOT deprovision — deprovisioned endpoints still count toward the 5-endpoint limit for 7 days. Instead, update the hostname:

```sql
SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<vpc_endpoint_service_id_or_resource_id>',  -- same service ID used in original provisioning
  '<correct_databricks_workspace_host_name>'   -- the new/correct workspace host
);
```

Then re-run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or query `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`) to confirm the host is updated and status is "available".

**If endpoint does not exist**: Continue to Step 2.0b to provision it.

#### Step 2.0b: Provision PrivateLink Endpoint

##### For AWS (Databricks on AWS)

Run as ACCOUNTADMIN to create the AWS PrivateLink endpoint:

```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<vpc_endpoint_service_id>',        -- e.g. com.amazonaws.vpce.us-west-2.vpce-svc-0123456789abcdef0
  '<databricks_workspace_host_name>'  -- e.g. dbc-a1a11111-1a11.cloud.databricks.com
);
```

- `<vpc_endpoint_service_id>` is the PrivateLink VPC endpoint service ID for Workspace (including REST API) from Databricks docs.
- `<databricks_workspace_host_name>` is the workspace URL without `https://`. Note: if the customer has multiple workspaces in the same AWS region, consider using a wildcard hostname (e.g., `*.cloud.databricks.com`) — all workspaces in the same region share the same PrivateLink service, so a single wildcard endpoint can cover them all and helps stay within the 5-endpoint limit.
- Snowflake creates an AWS PrivateLink interface endpoint in its own VPC.

> **Note**: If provisioning fails with `Private endpoint for resource ... already exists`, the endpoint is already provisioned. Run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or query `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`) to confirm it is healthy and proceed. If the existing endpoint's host doesn't match the target workspace, use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME()` to update it (see Step 2.0a). Do NOT deprovision and re-provision — deprovisioned endpoints still count toward the 5-endpoint limit for 7 days.

##### For Azure (Azure Databricks)

Run as ACCOUNTADMIN to create the Azure Private Endpoint:

```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<databricks_workspace_resource_id>',  -- e.g. /subscriptions/1111-22-333-4444-55555/resourceGroups/my-rg/providers/Microsoft.Databricks/workspaces/my-databricks-workspace
  '<databricks_workspace_host_name>',    -- e.g. adb-1234567890123456.12.azuredatabricks.net
  'databricks_ui_api'                    -- fixed sub-resource for Azure Databricks
);
```

- `<databricks_workspace_resource_id>` is the full Azure Resource ID from Azure Portal → Databricks workspace → Overview → JSON View.
- `<databricks_workspace_host_name>` is the per-workspace URL without `https://`. Note: if the customer has multiple workspaces in the same Azure region, consider using a wildcard hostname (e.g., `*.*.azuredatabricks.net`) — all workspaces in the same region share the same PrivateLink service, so a single wildcard endpoint can cover them all.
- `databricks_ui_api` is the required sub-resource value for Azure Databricks.

#### Step 2.0c: Verify PrivateLink Endpoint Status

```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

The output is JSON. Look for:
- `"status": "available"` for the Databricks workspace host endpoint

**Example response** (from `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` or `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`):

For AWS:
```json
{
  "provider_service_name": "com.amazonaws.vpce.<region>.vpce-svc-<id>",
  "snowflake_endpoint_name": "vpce-<endpoint_id>",
  "endpoint_state": "CREATED",
  "host": "<databricks_workspace_host_name>",
  "status": "available"
}
```

For Azure:
```json
{
  "provider_resource_id": "/subscriptions/<subscription_id>/resourceGroups/<resource_group>/providers/Microsoft.Databricks/workspaces/<workspace_name>",
  "snowflake_resource_id": "/subscriptions/<snowflake_subscription_id>/resourceGroups/<snowflake_resource_group>/providers/Microsoft.Network/privateEndpoints/<endpoint_guid>",
  "endpoint_state": "CREATED",
  "host": "<databricks_workspace_host_name>",
  "subresource": "databricks_ui_api",
  "status": "APPROVED"
}
```

**If status is not yet "available"**, wait and re-check. Provisioning can take a few minutes.

**For AWS**: Note the value of `"snowflake_endpoint_name"` from the JSON response (e.g., `vpce-0123456789abcdef0`). This is the Snowflake VPC endpoint ID you will register in Databricks.

**For Azure**: Note the `"snowflake_resource_id"` value from the JSON response — this is the Azure private endpoint resource created in Snowflake's VNet/subscription. You'll need this to identify the pending connection in Azure Portal.

#### Step 2.0d: Register/Approve the PrivateLink Connection in Databricks

##### For AWS: Register Snowflake's VPC Endpoint in Databricks

**Present to user**:
```
Snowflake PrivateLink Endpoint Provisioned:
─────────────────────────────────────────
Snowflake VPC Endpoint ID: <snowflake_endpoint_name>
                           (e.g. vpce-11111aaaa11aaaa11)
─────────────────────────────────────────

You must now register this endpoint in Databricks so Databricks
accepts traffic from Snowflake through this PrivateLink.

Steps:
═══════════════════════════════════════════════════════════

1. Ensure your Databricks workspace meets these requirements:
   - Workspace is in a customer-managed VPC
   - Databricks account has enterprise subscription
   - Front-end PrivateLink is configured

2. Register the Snowflake VPC endpoint ID:
   - In the Databricks ACCOUNT console (not just workspace):
     → Go to VPC endpoint registrations (Cloud Resources section)
     → Click "Register VPC endpoint"
     → Paste the Snowflake endpoint ID: <snowflake_endpoint_name>

3. Create or update a private access setting:
   - In the Databricks account console:
     → Open "Private access settings"
     → Create (or edit) a private access setting
     → Attach the registered VPC endpoint to it

═══════════════════════════════════════════════════════════

References:
- Manage VPC endpoint registrations:
  https://docs.databricks.com/en/security/network/classic/privatelink.html
- Configure Front-end PrivateLink:
  https://docs.databricks.com/en/security/network/classic/privatelink.html
- PrivateLink VPC endpoint service IDs by region:
  https://docs.databricks.com/aws/en/resources/ip-domain-region#privatelink
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Have you registered the Snowflake VPC endpoint in Databricks and configured the private access setting?"

**Wait for confirmation** → Continue to Step 2.1

##### For Azure: Approve Private Endpoint Connections

**Present to user**:
```
Snowflake Private Endpoint Provisioned:
─────────────────────────────────────────
Snowflake Resource ID: <snowflake_resource_id>
─────────────────────────────────────────

You must now approve the private endpoint connection in Azure
so Databricks accepts traffic from Snowflake through Private Link.

Steps:
═══════════════════════════════════════════════════════════

1. In Azure Portal:
   → Open your Databricks workspace
   → In the left menu, select "Networking"
   → Click "Private endpoint connections"

2. In the list of private endpoint connections:
   → Find the row whose ID/name corresponds to the
     Snowflake Resource ID shown above
   → Select the matching row
   → Click "Approve"

═══════════════════════════════════════════════════════════

Once approved, Snowflake can reach your Databricks workspace
over this Azure Private Link.
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Have you approved the private endpoint connection in Azure Portal?"

**Wait for confirmation** → Continue to Step 2.1

---

### Step 2.1: Generate Catalog Integration SQL

Based on authentication method and connectivity type, generate appropriate SQL statement.

> **ALTER Limitation**: You can alter `REST_AUTHENTICATION`, but only the `OAUTH_CLIENT_SECRET` and `BEARER_TOKEN` values (for secret rotation). If the authentication type needs to change (e.g., switching from Bearer Token to OAuth), you must use `CREATE OR REPLACE` to recreate the integration. Only `OAUTH_CLIENT_SECRET`, `BEARER_TOKEN`, and `REFRESH_INTERVAL_SECONDS` can be altered after creation.

#### Option A: OAuth Authentication

**For Public Connectivity**:
```sql
CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional, omit if not provided
  REST_CONFIG = (
    CATALOG_URI = 'https://<databricks-host>/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_TOKEN_URI = 'https://<databricks-host>/oidc/v1/token'
    OAUTH_CLIENT_ID = '<client_id>'
    OAUTH_CLIENT_SECRET = '<client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  ENABLED = TRUE;
```

**For AWS Private Connectivity** (Business Critical Edition):
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_API_TYPE = 'PRIVATE'
    CATALOG_URI      = '<databricks_workspace_url>/api/2.1/unity-catalog/iceberg-rest'
                       -- e.g. https://dbc-a1a11111-1a11.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest
    CATALOG_NAME     = '<unity_catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE                = OAUTH
    OAUTH_TOKEN_URI     = '<databricks_workspace_url>/oidc/v1/token'
    OAUTH_CLIENT_ID     = '<your_databricks_client_id>'
    OAUTH_CLIENT_SECRET = '<your_databricks_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  ENABLED = TRUE;
```

**For Azure Private Connectivity** (Business Critical Edition):
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_API_TYPE = 'PRIVATE'
    CATALOG_URI      = '<databricks_per_workspace_url>/api/2.1/unity-catalog/iceberg-rest'
                       -- e.g. https://adb-1234567890123456.12.azuredatabricks.net/api/2.1/unity-catalog/iceberg-rest
    CATALOG_NAME     = '<unity_catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE                = OAUTH
    OAUTH_TOKEN_URI     = '<databricks_per_workspace_url>/oidc/v1/token'
    OAUTH_CLIENT_ID     = '<your_databricks_client_id>'
    OAUTH_CLIENT_SECRET = '<your_databricks_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  ENABLED = TRUE;
```

> **Key differences from public connectivity**:
> - `CATALOG_API_TYPE = 'PRIVATE'` — tells Snowflake to route through PrivateLink
> - `CATALOG_URI` still uses the **public workspace URL** — Snowflake resolves it over PrivateLink internally
> - AWS uses `<databricks_workspace_url>` (e.g. `https://dbc-...cloud.databricks.com`); Azure uses `<databricks_per_workspace_url>` (e.g. `https://adb-...azuredatabricks.net`)
> - `ACCESS_DELEGATION_MODE` selects how Snowflake accesses storage — `VENDED_CREDENTIALS` or `EXTERNAL_VOLUME_CREDENTIALS` — not a connectivity setting. Both can use outbound PrivateLink to storage (external volumes already support it; for vended credentials set `DEFAULT_STORAGE_CONFIG`). For the combined catalog-server PrivateLink + vended credentials + storage PrivateLink example, see **Option C** below.

#### Option B: Bearer Token Authentication

**For Public Connectivity**:
```sql
CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_URI = 'https://<databricks-host>/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<personal_access_token>'
  )
  ENABLED = TRUE;
```

**For AWS Private Connectivity**:
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_URI      = '<databricks_workspace_url>/api/2.1/unity-catalog/iceberg-rest'
                       -- e.g. https://dbc-a1a11111-1a11.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest
    CATALOG_NAME     = '<unity_catalog_name>'
    CATALOG_API_TYPE = 'PRIVATE'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE         = BEARER
    BEARER_TOKEN = '<databricks_pat_token>'
  )
  ENABLED = TRUE;
```

**For Azure Private Connectivity**:
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_URI      = '<databricks_per_workspace_url>/api/2.1/unity-catalog/iceberg-rest'
                       -- e.g. https://adb-1234567890123456.12.azuredatabricks.net/api/2.1/unity-catalog/iceberg-rest
    CATALOG_NAME     = '<unity_catalog_name>'
    CATALOG_API_TYPE = 'PRIVATE'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE         = BEARER
    BEARER_TOKEN = '<databricks_pat_token>'
  )
  ENABLED = TRUE;
```

> **Key differences from public connectivity**:
> - `CATALOG_API_TYPE = 'PRIVATE'` — tells Snowflake to route through PrivateLink
> - `CATALOG_URI` still uses the **public workspace URL** — Snowflake resolves it over PrivateLink internally
> - AWS uses `<databricks_workspace_url>` (e.g. `https://dbc-...cloud.databricks.com`); Azure uses `<databricks_per_workspace_url>` (e.g. `https://adb-...azuredatabricks.net`)
> - `ACCESS_DELEGATION_MODE` selects how Snowflake accesses storage — `VENDED_CREDENTIALS` or `EXTERNAL_VOLUME_CREDENTIALS` — not a connectivity setting. Both can use outbound PrivateLink to storage (see Option C for vended credentials + storage PrivateLink)

**Parameter Explanation**:
- `CATALOG_SOURCE = ICEBERG_REST`: Generic REST catalog (Unity Catalog uses standard Iceberg REST)
- `TABLE_FORMAT = ICEBERG`: Apache Iceberg table format
- `CATALOG_NAMESPACE`: Optional default namespace (Unity Catalog schema)
- `CATALOG_URI`: Unity Catalog Iceberg REST endpoint — always use the **public workspace URL** (Snowflake routes via PrivateLink automatically when `CATALOG_API_TYPE = 'PRIVATE'`)
- `CATALOG_API_TYPE`:
  - Omit for public connectivity (defaults to public)
  - `'PRIVATE'`: Route through PrivateLink (requires provisioned endpoint)
- `CATALOG_NAME`: Catalog name in Unity Catalog
- `ACCESS_DELEGATION_MODE`:
  - `VENDED_CREDENTIALS`: Unity Catalog generates temporary credentials. Compatible with PrivateLink; combine with `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` to also route storage traffic over PrivateLink (see Option C).
  - `EXTERNAL_VOLUME_CREDENTIALS`: Use external volume for data access (default when `ACCESS_DELEGATION_MODE` is omitted)
- **OAuth Parameters**:
  - `TYPE = OAUTH`: OAuth2 authentication
  - `OAUTH_TOKEN_URI`: Databricks OAuth token endpoint
  - `OAUTH_ALLOWED_SCOPES`: Permissions (e.g., `all-apis`, `sql`, `catalog`)
- **Bearer Parameters**:
  - `TYPE = BEARER`: Bearer token authentication
  - `BEARER_TOKEN`: Personal Access Token from Databricks

**INFO**: Unity Catalog uses `CATALOG_SOURCE = ICEBERG_REST` (generic REST), not `POLARIS` like OpenCatalog.

#### Option C: PrivateLink with vended credentials (storage routed via PrivateLink)

Combines catalog-server PrivateLink (`CATALOG_API_TYPE = PRIVATE`) with vended credentials and storage-side PrivateLink. **Prerequisite**: provision the storage endpoint first (see [shared/vended-credentials-private-storage/SKILL.md](../../shared/vended-credentials-private-storage/SKILL.md)).

**For AWS:**
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_API_TYPE       = 'PRIVATE'
    CATALOG_URI            = 'https://<databricks-host>/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME           = '<unity_catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE                 = OAUTH
    OAUTH_TOKEN_URI      = 'https://<databricks-host>/oidc/v1/token'
    OAUTH_CLIENT_ID      = '<client_id>'
    OAUTH_CLIENT_SECRET  = '<client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

**For Azure** (use the per-workspace `adb-*.azuredatabricks.net` URL):
```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_API_TYPE       = 'PRIVATE'
    CATALOG_URI            = 'https://adb-<workspace-id>.<region>.azuredatabricks.net/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME           = '<unity_catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE                 = OAUTH
    OAUTH_TOKEN_URI      = 'https://adb-<workspace-id>.<region>.azuredatabricks.net/oidc/v1/token'
    OAUTH_CLIENT_ID      = '<client_id>'
    OAUTH_CLIENT_SECRET  = '<client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

> **⚠️ All three of these must be present together — this is the most common mistake:**
> - `CATALOG_API_TYPE = 'PRIVATE'` — routes Unity Catalog API calls over catalog-server PrivateLink.
> - `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` **inside `REST_CONFIG`** — Unity Catalog generates temporary storage credentials. If you omit it, storage PrivateLink is rejected ("credential vending is not enabled").
> - `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` — routes Snowflake-to-storage data reads through storage PrivateLink. This line must appear **between `REST_AUTHENTICATION` and `ENABLED`**.
>
> Do **not** add `EXTERNAL_VOLUME` — vended credentials replace it.


---

### Step 2.2: Review & Approval

**Present generated SQL to user**:

```
Generated Catalog Integration SQL:
═══════════════════════════════════════════════════════════
[The complete SQL with actual values filled in]
═══════════════════════════════════════════════════════════

This will create a catalog integration named '<integration_name>' 
connecting to Unity Catalog '<catalog_name>' using <OAuth|Bearer Token> 
authentication via <Public|Private> connectivity.
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Please review the SQL above. Ready to execute and create the catalog integration?"

**Wait for explicit approval**:
- "Yes", "Approved", "Looks good", "Proceed" → Continue to Step 2.3
- "No" or "Wait" → Ask: "What changes would you like to make?"
- "Edit" → Ask for specific modifications

### Step 2.3: Execute Creation

**Execute approved SQL**:
```sql
[The approved CREATE CATALOG INTEGRATION statement]
```

**Expected Success Result**: 
```
Catalog integration <integration_name> successfully created.
```

**If Success**: Integration created → Return to main skill → Step 3

**If Error**: Present error → Load `references/troubleshooting.md` → Wait for direction

## Output

Successfully created catalog integration in Snowflake, ready for verification.

## Error Handling

**Common errors**:
- **OAuth authentication failure**: Check credentials, token URI, load troubleshooting
- **Bearer token invalid**: Check token is valid and not expired
- **Catalog name invalid**: Verify catalog name spelling with user
- **Permission denied**: Check Snowflake privileges for creating integrations
- **Network connectivity**: Verify Databricks workspace URL is accessible
- **PrivateLink endpoint not available**: Verify endpoint status via `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`)
- **PrivateLink endpoint not registered (AWS)**: Ensure Snowflake VPC endpoint is registered in Databricks account console
- **PrivateLink endpoint not approved (Azure)**: Ensure private endpoint connection is approved in Azure Portal

**For all errors**: Present error message clearly and load troubleshooting guide before attempting fixes.

## Next Steps

After successful creation:
- Return to main skill
- Proceed to Step 3: Verification
- Load `verify/SKILL.md`
