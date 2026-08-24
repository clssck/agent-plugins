---
name: opencatalog-create-integration
description: "Create and execute catalog integration for OpenCatalog (public and PrivateLink)"
parent_skill: opencatalog-catalog-integration-setup
---

# Configuration & Creation

Build and execute the SQL to create your OpenCatalog catalog integration.

## When to Load

From main skill Step 2: After prerequisites have been gathered and confirmed

## Prerequisites

Must have from setup phase:
- OAuth credentials (Client ID, Secret, Scopes)
- Access delegation mode choice
- Connectivity type (Public/Private)
- Catalog name
- Catalog namespace (optional)
- OpenCatalog account identifier + VPCE Service ID (cross-deployment private only)
- Integration name

## Workflow

### PrivateLink Edition Check (All PrivateLink Setups)

> **Skip this check if using Public connectivity.**

PrivateLink requires **Business Critical Edition (or higher)** for both same-deployment and cross-deployment setups.

**Verify account edition** before proceeding. Try these methods in order:

**Method 1** — requires access to `ORGANIZATION_USAGE` schema (typically ORGADMIN):
```sql
SELECT EDITION
  FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
  WHERE ACCOUNT_NAME = CURRENT_ACCOUNT();
```

**Method 2 (manual)** — if the query above fails, ask the user:
```
Could you check your Snowflake edition? You can find it in:
  Snowsight → Admin → Accounts → look for the edition badge
```

Must be `BUSINESS_CRITICAL` or higher. See: [Find your current edition](https://docs.snowflake.com/en/user-guide/intro-editions#find-your-current-edition).

> **Note**: If the edition cannot be confirmed programmatically, proceed with the user's verbal confirmation and note that creation will fail if the edition is insufficient.

---

### Step 2.0: Provision PrivateLink Endpoint (Cross-Deployment PrivateLink Only)

> **Skip this step entirely if using Public connectivity.** Jump to [Step 2.1](#step-21-generate-catalog-integration-sql).

> **⚠️ Important: Same-deployment vs. cross-deployment**:
> - If your OpenCatalog account and Snowflake account are in the **same deployment**, PrivateLink endpoint provisioning is **NOT needed**. Snowflake automatically handles internal traffic routing when `CATALOG_API_TYPE=PRIVATE` is specified. Skip this step and go directly to [Step 2.1](#step-21-generate-catalog-integration-sql).
> - Provisioning via `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT` is **only required when OpenCatalog and Snowflake are in different deployments** (cross-deployment).
> - If you're unsure, try skipping provisioning and proceed to create the catalog integration. If connectivity fails, you may need to come back and provision the endpoint.

> **⚠️ PrivateLink constraints** (when provisioning is needed):
> - Requires ACCOUNTADMIN role for PrivateLink provisioning.

#### Step 2.0a: Check for Existing PrivateLink Endpoint

Before provisioning, check if a PrivateLink endpoint for the OpenCatalog VPCE service already exists:

```sql
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

Parse the JSON output and look for an entry where:
- The provider service name matches `<vpce_service_id>` (e.g., `com.amazonaws.vpce.us-west-2.vpce-svc-1234567890abcdef0`)
- The host matches `<privatelink_host>` (e.g., `myorg-myaccount.privatelink.snowflakecomputing.com`)

**If endpoint already exists, status is "available", AND host matches**: Skip provisioning (Step 2.0b) and proceed directly to Step 2.0c (verify).

**If endpoint already exists but host does NOT match**: The endpoint's hostname has been changed. Do NOT deprovision — deprovisioned endpoints still count toward the 5-endpoint limit for 7 days. Instead, update the hostname:

```sql
SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<vpce_service_id>',          -- VPCE Service ID
  '<privatelink_host>'          -- correct host name
);
```

Then re-run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or query `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`) to confirm the host is updated and status is "available".

**If endpoint does not exist**: Continue to Step 2.0b to provision it.

#### Step 2.0b: Provision PrivateLink Endpoint

Run as ACCOUNTADMIN to create the PrivateLink endpoint from Snowflake to OpenCatalog:

```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<vpce_service_id>',          -- VPCE Service ID from OpenCatalog Settings
  '<privatelink_host>'          -- PrivateLink account URL host
);
```

Example:
```sql
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.vpce.us-west-2.vpce-svc-1234567890abcdef0',
  '<myorg>-<myaccount>.privatelink.snowflakecomputing.com'
);
```

- Snowflake creates a PrivateLink interface endpoint in its own VPC.
- The function returns details including the endpoint ID.
- **Limit**: Snowflake accounts can have a maximum of **5 private endpoints**. Deprovisioned endpoints count toward this limit for 7 days. To increase the limit, contact Snowflake Support.

> **Note — Wildcard hostname**: If you have (or plan to have) multiple OpenCatalog accounts in the same deployment, consider using a wildcard hostname instead of a specific account hostname. Since each Snowflake deployment uses a single PrivateLink service, a wildcard endpoint can serve all OpenCatalog accounts in that deployment through one endpoint.
>
> ```sql
> SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
>   '<vpce_service_id>',
>   '*.<region>.privatelink.snowflakecomputing.com'
> );
> ```
>
> For example:
> ```sql
> SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
>   'com.amazonaws.vpce.us-west-2.vpce-svc-1234567890abcdef0',
>   '*.us-west-2.privatelink.snowflakecomputing.com'
> );
> ```

> **Note**: If provisioning fails with `Private endpoint for resource <vpce_service_id> already exists`, the endpoint is already provisioned. Run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or query `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`) to confirm it is healthy and proceed. If the existing endpoint's host doesn't match the expected value, use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME()` to update it (see Step 2.0a). Do NOT deprovision and re-provision — deprovisioned endpoints still count toward the 5-endpoint limit for 7 days.

#### Step 2.0c: Verify PrivateLink Endpoint Status

```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

The output is JSON. Look for:
- `"endpoint_state": "CREATED"`
- `"status": "available"` for the OpenCatalog endpoint (host matching `<privatelink_host>`)

**If status is not yet "available"**, wait and re-check. Provisioning can take a few minutes.

---

### Step 2.1: Generate Catalog Integration SQL

Based on connectivity type and access delegation mode, generate appropriate SQL statement.

> **CATALOG_NAMESPACE**: If the user did not provide a namespace in the prerequisites, **omit the `CATALOG_NAMESPACE` line entirely** from the generated SQL. Do not include it with an empty value.

> **Role guidance**: The SQL below uses `ACCOUNTADMIN` for simplicity. Any role with `CREATE INTEGRATION` privilege on the account can create catalog integrations. PrivateLink endpoint provisioning (Step 2.0) specifically requires `ACCOUNTADMIN`.

> **ALTER Limitation**: `REST_CONFIG` cannot be altered on catalog integrations. You can alter `REST_AUTHENTICATION`, but only the `OAUTH_CLIENT_SECRET` value (for secret rotation). If the catalog URI, catalog name, access delegation mode, or authentication type needs to change, you must recreate the integration with `CREATE OR REPLACE`.

#### For Public Connectivity

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Include ONLY if user provided a namespace; omit entire line otherwise
  REST_CONFIG = (
    CATALOG_URI = '<opencatalog_url>/polaris/api/catalog'
    CATALOG_API_TYPE = PUBLIC  -- Optional, PUBLIC is the default
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<client_id>'
    OAUTH_CLIENT_SECRET = '<client_secret>'
    OAUTH_ALLOWED_SCOPES = ('PRINCIPAL_ROLE:<principal_role>')
  )
  ENABLED = TRUE;
```

#### For Private Connectivity (PrivateLink)

> **Prerequisite**: For cross-deployment setups, the PrivateLink endpoint must be provisioned and "available" (Step 2.0). For same-deployment setups, no endpoint provisioning is needed — Snowflake routes traffic internally when `CATALOG_API_TYPE=PRIVATE` is specified.

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Include ONLY if user provided a namespace; omit entire line otherwise
  REST_CONFIG = (
    CATALOG_URI = 'https://<open_catalog_privatelink_account_url>/polaris/api/catalog'
    CATALOG_API_TYPE = PRIVATE
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<client_id>'
    OAUTH_CLIENT_SECRET = '<client_secret>'
    OAUTH_ALLOWED_SCOPES = ('PRINCIPAL_ROLE:<principal_role>')
    -- OAUTH_TOKEN_URI = '<token_uri>'        -- Optional: only needed if using an external IdP (e.g., Okta, Auth0)
    -- OAUTH_API_TYPE = PRIVATE               -- Optional: defaults to CATALOG_API_TYPE. Set to PUBLIC if external IdP doesn't support inbound PrivateLink.
  )
  ENABLED = TRUE;
```

> **External IdP considerations (PrivateLink only)**:
>
> By default, `OAUTH_API_TYPE` inherits the value of `CATALOG_API_TYPE`. When `CATALOG_API_TYPE = PRIVATE`, Snowflake will also attempt to reach the OAuth token endpoint over PrivateLink.
>
> - **Using OpenCatalog as the IdP (default)**: If you specify an `OAUTH_TOKEN_URI` pointing to the OpenCatalog token endpoint, no additional PrivateLink endpoint is needed — the OAuth service and the catalog service share the same PrivateLink service.
> - **Using an external IdP (e.g., Okta, Auth0)**: If you set `OAUTH_TOKEN_URI` to an external IdP's token endpoint, you must also provision a separate PrivateLink endpoint for that external OAuth service. Without it, Snowflake will fail to reach the token endpoint and return an error indicating the corresponding PrivateLink endpoint cannot be found.
> - **External IdP without inbound PrivateLink support**: If your external IdP does not support inbound PrivateLink, set `OAUTH_API_TYPE = PUBLIC` to have Snowflake reach the OAuth token endpoint over the public internet while still using PrivateLink for catalog API calls.

> **Key differences from public connectivity**:
> - `CATALOG_API_TYPE = PRIVATE` (not `PUBLIC`) — tells Snowflake to route through PrivateLink
> - `CATALOG_URI` uses the PrivateLink account URL (e.g., `https://<open_catalog_privatelink_account_url>/polaris/api/catalog`)
> - `ACCESS_DELEGATION_MODE` selects how Snowflake accesses storage — `VENDED_CREDENTIALS` (catalog vends temporary credentials) or `EXTERNAL_VOLUME_CREDENTIALS` (external volume) — not a connectivity setting. Both modes can use outbound PrivateLink to storage: external volumes already support it; for vended credentials, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` (see the "PrivateLink with vended credentials" variant below). Independent of catalog-server PrivateLink.

#### PrivateLink with vended credentials (storage routed via PrivateLink)

> **Prerequisite**: In addition to the catalog-server PrivateLink endpoint (Step 2.0), a storage-side PrivateLink endpoint must be provisioned. See [../../shared/vended-credentials-private-storage/SKILL.md](../../shared/vended-credentials-private-storage/SKILL.md) for the cross-vendor steps.

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Include ONLY if user provided a namespace; omit entire line otherwise
  REST_CONFIG = (
    CATALOG_URI = 'https://<open_catalog_privatelink_account_url>/polaris/api/catalog'
    CATALOG_API_TYPE = PRIVATE
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<oauth_client_id>'
    OAUTH_CLIENT_SECRET = '<oauth_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('PRINCIPAL_ROLE:ALL')
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

**Parameter Explanation**:
- `CATALOG_SOURCE = POLARIS`: Specifies OpenCatalog as catalog type
- `TABLE_FORMAT = ICEBERG`: Apache Iceberg table format
- `CATALOG_NAMESPACE`: Optional default namespace for tables
- `CATALOG_URI`: OpenCatalog API endpoint (public URL or PrivateLink URL)
- `CATALOG_API_TYPE`:
  - `PUBLIC` (default): Public connectivity (over the internet)
  - `PRIVATE`: Private connectivity via PrivateLink. For same-deployment setups, Snowflake handles internal traffic routing automatically; for cross-deployment, requires a provisioned PrivateLink endpoint.
- `CATALOG_NAME`: Catalog name in OpenCatalog
- `ACCESS_DELEGATION_MODE`:
  - `VENDED_CREDENTIALS`: OpenCatalog generates temporary credentials (no external volume needed for tables/CLDs)
  - `EXTERNAL_VOLUME_CREDENTIALS`: Use external volume for data access (default, requires external volume when creating tables/CLDs)
- `TYPE = OAUTH`: OAuth2 authentication
- `OAUTH_CLIENT_ID`: Client ID from the OpenCatalog service connection
- `OAUTH_CLIENT_SECRET`: Client secret from the OpenCatalog service connection
- `OAUTH_ALLOWED_SCOPES`: Permissions granted (e.g., `PRINCIPAL_ROLE:ALL` or specific principal roles)
- `OAUTH_TOKEN_URI`: (Optional) Custom OAuth token endpoint URL. Only needed when using an external IdP (e.g., Okta, Auth0) instead of the default OpenCatalog token endpoint.
- `OAUTH_API_TYPE`: (Optional) Controls how Snowflake reaches the OAuth token endpoint. Defaults to the value of `CATALOG_API_TYPE`. Set to `PUBLIC` if using an external IdP that does not support inbound PrivateLink.

**INFO**: Both `CATALOG_SOURCE = POLARIS` and `CATALOG_SOURCE = ICEBERG_REST` work for OpenCatalog. We use POLARIS as it's the OpenCatalog-specific option.

### Step 2.2: Review & Approval

**Present generated SQL to user**:

```
Generated Catalog Integration SQL:
═══════════════════════════════════════════════════════════
[The complete SQL with actual values filled in]
═══════════════════════════════════════════════════════════

This will create a catalog integration named '<integration_name>' 
connecting to OpenCatalog catalog '<catalog_name>' using OAuth 
authentication via <connectivity_type> connectivity.
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

**If Success**: ✓ Integration created → Return to main skill → Step 3

**If Error**: Present error → Load `references/troubleshooting.md` → Wait for direction

## Output

Successfully created catalog integration in Snowflake, ready for verification.

## Error Handling

**Common errors**:
- **OAuth authentication failure**: Check credentials, load troubleshooting
- **Catalog name invalid**: Verify catalog name spelling with user
- **Permission denied**: Check Snowflake privileges for creating integrations
- **PrivateLink endpoint not available**: Only applies to cross-deployment setups. Verify endpoint is provisioned and "available" via `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`). If same deployment, provisioning is not needed — Snowflake routes traffic internally when `CATALOG_API_TYPE=PRIVATE` is specified.

**For all errors**: Present error message clearly and load troubleshooting guide before attempting fixes.

## Next Steps

After successful creation:
- Return to main skill
- Proceed to Step 3: Verification
- Load `verify/SKILL.md`
