---
name: opencatalog-catalog-integration-setup
description: "Setup and verify catalog integration for OpenCatalog (Polaris) (public and PrivateLink). Triggers: create opencatalog integration, connect snowflake to opencatalog, setup polaris catalog, configure opencatalog integration, polaris iceberg, oauth opencatalog, troubleshoot opencatalog integration, verify opencatalog connection, fix polaris connection, debug opencatalog iceberg, snowflake open catalog, opencatalog privatelink, polaris private link, private connectivity opencatalog, polaris privatelink iceberg, private polaris catalog, vended credentials privatelink, USE_PRIVATELINK_ENDPOINT, DEFAULT_STORAGE_CONFIG, private storage with vended credentials, opencatalog vended creds privatelink, polaris vended credentials private storage."
---

# OpenCatalog Catalog Integration

Setup, verify, or troubleshoot a Snowflake catalog integration for OpenCatalog (formerly Polaris).

## Intent Routing (FIRST)

**Ask the user**:
```
What would you like to do?

A: Create a new catalog integration for OpenCatalog
   → Setup Snowflake to connect to OpenCatalog

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

Create a new catalog integration to connect Snowflake to OpenCatalog.

### Step 1: Prerequisites

Follow `setup/SKILL.md` to collect:

Collect one-by-one:
1. Confirm OpenCatalog setup exists
2. Access delegation mode
3. Connectivity type (Public or PrivateLink)
4. OpenCatalog account identifier + VPCE Service ID (if cross-deployment PrivateLink)
5. Catalog name
6. Catalog namespace (optional)
7. OAuth credentials (Client ID, Secret, Scopes)
8. Integration name

**⚠️ STOP**: Confirm prerequisites before proceeding

### Step 2: Create Integration

**Load** `create/SKILL.md` and follow its workflow:

1. **If PrivateLink (cross-deployment only)**: Provision PrivateLink endpoint, verify status. Skip if OpenCatalog and Snowflake are in the same deployment.
2. Generate CREATE CATALOG INTEGRATION SQL
3. **⚠️ STOP**: Review SQL with user
4. Execute creation

### Step 3: Verify

→ Continue to [Verify Workflow](#verify-workflow)

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
- PrivateLink connectivity issues

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
1. OAuth authentication failures
2. Catalog not found
3. Network connectivity issues (public and PrivateLink)
4. External volume issues
5. Namespace/table discovery issues
6. Table query failures
7. PrivateLink endpoint not available
8. PrivateLink endpoint limit exceeded (max 5 per account)
9. PrivateLink endpoint already exists (safe to proceed)
10. PrivateLink VPCE service not allowed (same-deployment skip or cross-deployment allowlisting)

**⚠️ STOP**: Present diagnosis and wait for user direction before applying fixes.

---

## Scope

This skill focuses on **Snowflake-side setup**:
- ✅ Creating catalog integrations for OpenCatalog (public and PrivateLink)
- ✅ PrivateLink endpoint provisioning and verification (cross-deployment only)
- ✅ OAuth authentication configuration
- ✅ Service connection setup guidance
- ✅ Verification
- ✅ Troubleshooting

**Out of scope** (separate resources):
- ❌ OpenCatalog account/catalog setup → [OpenCatalog Documentation](https://other-docs.snowflake.com/en/opencatalog/overview)
- ❌ OpenCatalog PrivateLink inbound setup (done in OpenCatalog UI) → [AWS](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-aws) | [Azure](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-azure)
- ❌ External volume creation
- ❌ Creating tables or catalog-linked databases (use shared `next-steps` skill)

---

## Quick Reference

> **Role guidance**: The examples below use `ACCOUNTADMIN` for simplicity. Any role with `CREATE INTEGRATION` privilege on the account can create catalog integrations. PrivateLink endpoint provisioning (`SYSTEM$PROVISION_PRIVATELINK_ENDPOINT`) specifically requires `ACCOUNTADMIN`.

**Catalog Integration SQL (Public)**:
```sql
USE ROLE ACCOUNTADMIN;
CREATE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  -- CATALOG_NAMESPACE = '<namespace>'  -- Optional: omit if not needed
  REST_CONFIG = (
    CATALOG_URI = 'https://<orgname>-<account_name>.snowflakecomputing.com/polaris/api/catalog'
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

**Catalog Integration SQL (PrivateLink)**:
```sql
-- Step 1 (cross-deployment ONLY): Check if endpoint already exists (skip if same deployment)
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;

-- Step 2 (cross-deployment ONLY): Provision PrivateLink endpoint (skip if same deployment)
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<vpce_service_id>',
  '<privatelink_host>'
);
-- Note: If you have multiple OpenCatalog accounts in the same deployment,
-- consider using a wildcard hostname (e.g., '*.us-west-2.privatelink.snowflakecomputing.com')
-- so one endpoint can serve them all. Each deployment has a single PrivateLink service,
-- so a wildcard avoids provisioning separate endpoints per account.

-- Step 3 (cross-deployment ONLY): Verify endpoint is available
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;

-- Step 4: Create catalog integration
USE ROLE ACCOUNTADMIN;
CREATE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'
  REST_CONFIG = (
    CATALOG_URI = 'https://<open_catalog_privatelink_account_url>/polaris/api/catalog'
    CATALOG_API_TYPE = PRIVATE
    CATALOG_NAME = '<catalog_name>'
    -- ACCESS_DELEGATION_MODE here defaults to EXTERNAL_VOLUME_CREDENTIALS. To use VENDED_CREDENTIALS with private storage routing, see "Vended credentials with private connectivity to storage" below.
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

> **⚠️ PrivateLink notes**:
> - Requires **Business Critical Edition (or higher)**. To inquire about upgrading, please contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge).
> - `CATALOG_API_TYPE = PRIVATE` (not `PUBLIC`)
> - `CATALOG_URI` uses the PrivateLink account URL
> - Catalog-vended credentials work with PrivateLink. To also route storage traffic over PrivateLink, see "Vended credentials with private connectivity to storage" below and set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. If you keep `EXTERNAL_VOLUME_CREDENTIALS` (the default), use a separate external volume for storage access.
> - **Endpoint provisioning** (Steps 1-3) is only needed for **cross-deployment** setups (OpenCatalog and Snowflake in different deployments). If same deployment, skip directly to Step 4.

## Vended credentials with private connectivity to storage

Any OpenCatalog integration with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` can route Snowflake-to-storage traffic through PrivateLink by setting `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. This is independent of (and combinable with) catalog-server PrivateLink (`CATALOG_API_TYPE = PRIVATE`).

### Step 1: OpenCatalog-specific preparation

Before configuring `DEFAULT_STORAGE_CONFIG` on the Snowflake side, provision a private connectivity endpoint in your Open Catalog account and enable the PrivateLink toggle on the catalog:

- **AWS**: [Manage outbound private connectivity endpoints (AWS)](https://docs.snowflake.com/en/user-guide/opencatalog/private-connectivity-outbound-manage-endpoints-aws)
- **Azure**: [Manage outbound private connectivity endpoints (Azure)](https://docs.snowflake.com/en/user-guide/opencatalog/private-connectivity-outbound-manage-endpoints-azure)
  - For Azure ADLS Gen2, both `blob` and `dfs` endpoints are required. The catalog vends `dfs.core.windows.net` URLs; without a `dfs` endpoint, storage access will fail.

### Step 2: Cross-vendor storage PrivateLink steps

For the remaining steps — block public storage access, provision a Snowflake-side storage PrivateLink endpoint, allowlist the endpoint, and verify connectivity — see the shared flow:

[shared/vended-credentials-private-storage/SKILL.md](../shared/vended-credentials-private-storage/SKILL.md)

### Example: OpenCatalog with vended credentials and storage PrivateLink

```sql
USE ROLE ACCOUNTADMIN;

CREATE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
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

To enable on an existing integration:

> **⚠️ MANDATORY CHECKPOINT**: This `ALTER` modifies a live catalog integration. Present it to the user and wait for explicit approval before executing.

```sql
ALTER CATALOG INTEGRATION <name> SET DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE);
```

### Self-hosted / generic Iceberg REST

The same pattern applies to any generic Iceberg REST vendor:

```sql
USE ROLE ACCOUNTADMIN;

CREATE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://<catalog_endpoint>'
    CATALOG_API_TYPE = PRIVATE
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<oauth_client_id>'
    OAUTH_CLIENT_SECRET = '<oauth_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

**Diagnostic Commands**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<name>';
DESC CATALOG INTEGRATION <name>;
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<name>');
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<name>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<name>', '<namespace>');
```

---

## Success Criteria

- ✅ Integration shows `ENABLED=TRUE`
- ✅ `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns success
- ✅ Namespaces discoverable
- ✅ Tables visible

---

## Documentation

- [Configure Catalog Integration for OpenCatalog](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-open-catalog)
- [CREATE CATALOG INTEGRATION (Snowflake Open Catalog)](https://docs.snowflake.com/en/sql-reference/sql/create-catalog-integration-open-catalog)
- [AWS PrivateLink and Snowflake Open Catalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-aws)
- [Azure Private Link and Snowflake Open Catalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-azure)
- GCS Private Service Connect: Not currently documented — check [OpenCatalog documentation](https://other-docs.snowflake.com/en/opencatalog/overview) for latest GCP private connectivity support
- [Snowflake Iceberg Tables](https://docs.snowflake.com/user-guide/tables-iceberg)
- [Iceberg Data Types](https://docs.snowflake.com/en/user-guide/tables-iceberg-data-types#other-data-types) - Supported data type mappings and limitations
- [OpenCatalog Documentation](https://other-docs.snowflake.com/en/openc