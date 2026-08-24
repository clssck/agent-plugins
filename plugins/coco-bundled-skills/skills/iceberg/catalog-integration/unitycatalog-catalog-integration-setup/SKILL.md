---
name: unitycatalog-catalog-integration-setup
description: "Setup and verify catalog integration for Unity Catalog (public and PrivateLink). Triggers: create unity catalog integration, connect snowflake to databricks, setup unity catalog, configure databricks catalog integration, unity catalog iceberg, oauth unity catalog, bearer token unity catalog, PAT databricks snowflake, troubleshoot unity catalog integration, verify unity catalog connection, fix databricks connection, debug unity catalog iceberg, unity catalog privatelink, unity catalog private link, private connectivity unity catalog, databricks privatelink snowflake, unity catalog aws privatelink, unity catalog azure private link, databricks private endpoint, vended credentials privatelink, USE_PRIVATELINK_ENDPOINT, DEFAULT_STORAGE_CONFIG, private storage with vended credentials, unity catalog vended creds privatelink, databricks vended credentials private storage."
---

# Unity Catalog Catalog Integration

Setup, verify, or troubleshoot a Snowflake catalog integration for Databricks Unity Catalog.

## Intent Routing (FIRST)

**Ask the user**:
```
What would you like to do?

A: Create a new catalog integration for Unity Catalog
   → Setup Snowflake to connect to Databricks Unity Catalog

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

Create a new catalog integration to connect Snowflake to Unity Catalog.

### Step 1: Prerequisites

Follow `setup/SKILL.md` to collect:

Collect one-by-one:
1. Confirm Unity Catalog setup exists
2. Authentication method (OAuth vs Bearer token/PAT)
3. Access delegation mode
4. Connectivity type
5. Databricks workspace URL
6. Unity Catalog name
7. Catalog namespace (optional)
8. OAuth credentials OR Bearer token
9. OAuth allowed scopes (if OAuth)
10. Integration name

**⚠️ STOP**: Confirm prerequisites before proceeding

### Step 2: Create Integration

**Load** `create/SKILL.md` and follow its workflow:

1. **If PrivateLink**: Provision PrivateLink endpoint (AWS or Azure), verify status, register/approve endpoint in Databricks
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

-- List namespaces (Unity Catalog schemas)
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
- OAuth/authentication errors
- Token expired

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
2. Bearer token (PAT) failures
3. Unity Catalog privilege issues
4. Catalog not found
5. Network connectivity issues
6. External volume issues
7. Namespace/table discovery issues
8. Table query failures
9. PrivateLink endpoint not available
10. PrivateLink endpoint limit exceeded
11. PrivateLink endpoint already exists (includes hostname mismatch — use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME`)
12. PrivateLink endpoint not registered in Databricks (AWS)
13. PrivateLink endpoint not approved in Azure Portal (Azure)

**⚠️ STOP**: Present diagnosis and wait for user direction before applying fixes.

---

## Scope

This skill focuses on **Snowflake-side setup**:
- ✅ Creating catalog integrations for Unity Catalog (public and PrivateLink)
- ✅ PrivateLink endpoint provisioning and verification (AWS and Azure)
- ✅ PrivateLink endpoint registration (AWS) / approval (Azure) guidance
- ✅ OAuth and Bearer token authentication configuration
- ✅ Databricks service principal setup guidance
- ✅ Verification
- ✅ Troubleshooting

**Out of scope** (separate resources):
- ❌ Unity Catalog setup in Databricks → [Unity Catalog Documentation](https://docs.databricks.com/en/data-governance/unity-catalog/index.html)
- ❌ External volume creation
- ❌ Creating tables or catalog-linked databases (use shared `next-steps` skill)

---

## Quick Reference

**Catalog Integration SQL (OAuth, Public)**:
```sql
CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://<workspace>.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<client_id>'
    OAUTH_CLIENT_SECRET = '<client_secret>'
    OAUTH_TOKEN_URI = 'https://<workspace>.cloud.databricks.com/oidc/v1/token'
    OAUTH_ALLOWED_SCOPES = ('all-apis')
  )
  ENABLED = TRUE;
```

**Catalog Integration SQL (Bearer Token, Public)**:
```sql
CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://<workspace-host>/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<personal_access_token>'
  )
  ENABLED = TRUE;
```

**Catalog Integration SQL (PrivateLink — OAuth)**:
```sql
-- Step 1: Check if endpoint already exists (skip provisioning if available)
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;

-- Step 2: Provision PrivateLink endpoint (one-time, skip if already exists)
USE ROLE ACCOUNTADMIN;

-- For AWS (consider using *.cloud.databricks.com as hostname to cover multiple workspaces in the same region):
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<vpc_endpoint_service_id>',
  '<databricks_workspace_host_name>'
);
-- For Azure (consider using *.*.azuredatabricks.net as hostname to cover multiple workspaces in the same region):
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<databricks_workspace_resource_id>',
  '<databricks_workspace_host_name>',
  'databricks_ui_api'
);

-- Step 3: Verify endpoint is available
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;

-- Step 4: Register/approve endpoint in Databricks (see create/SKILL.md)

-- Step 5: Create catalog integration (AWS PrivateLink + OAuth example)
CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_API_TYPE = 'PRIVATE'
    CATALOG_URI      = '<databricks_workspace_url>/api/2.1/unity-catalog/iceberg-rest'
                       -- e.g. https://dbc-a1a11111-1a11.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest
    CATALOG_NAME     = '<unity_catalog_name>'
  )
  REST_AUTHENTICATION = (
    TYPE                = OAUTH
    OAUTH_TOKEN_URI     = '<databricks_workspace_url>/oidc/v1/token'
    OAUTH_CLIENT_ID     = '<your_databricks_client_id>'
    OAUTH_CLIENT_SECRET = '<your_databricks_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  ENABLED = TRUE;

-- Step 5 (alt): Create catalog integration (Azure PrivateLink + OAuth example)
CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'  -- Optional
  REST_CONFIG = (
    CATALOG_API_TYPE = 'PRIVATE'
    CATALOG_URI      = '<databricks_per_workspace_url>/api/2.1/unity-catalog/iceberg-rest'
                       -- e.g. https://adb-1234567890123456.12.azuredatabricks.net/api/2.1/unity-catalog/iceberg-rest
    CATALOG_NAME     = '<unity_catalog_name>'
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

> **PrivateLink notes**:
> - Requires **Business Critical Edition (or higher)**. To inquire about upgrading, please contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge).
> - `CATALOG_API_TYPE = 'PRIVATE'` tells Snowflake to route via PrivateLink
> - `CATALOG_URI` uses the **public workspace URL** — Snowflake routes over PrivateLink internally
> - AWS uses `<databricks_workspace_url>` (e.g. `https://dbc-...cloud.databricks.com`); Azure uses `<databricks_per_workspace_url>` (e.g. `https://adb-...azuredatabricks.net`)
> - `ACCESS_DELEGATION_MODE` selects how Snowflake accesses storage — `VENDED_CREDENTIALS` (catalog vends temporary credentials) or `EXTERNAL_VOLUME_CREDENTIALS` (external volume) — not a connectivity setting, and independent of catalog-server PrivateLink (`CATALOG_API_TYPE`). Both modes can use outbound PrivateLink to storage: external volumes already support it; for vended credentials, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. For the combined example, see the "Vended credentials with private connectivity to storage" section below.
> - AWS: Register Snowflake VPC endpoint in Databricks account console
> - Azure: Approve private endpoint connection in Azure Portal → Databricks workspace → Networking

**Diagnostic Commands**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<name>';
DESC CATALOG INTEGRATION <name>;
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<name>');
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<name>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<name>', '<namespace>');
```

---

## Vended credentials with private connectivity to storage

Any Unity Catalog integration with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` can route Snowflake-to-storage traffic through PrivateLink by setting `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. This setting is independent of catalog-server PrivateLink (`CATALOG_API_TYPE = PRIVATE`); you can enable either or both.

### Step 1: Prepare catalog-side private storage access

Before routing storage traffic through PrivateLink, ensure Unity Catalog itself can reach the storage bucket through private connectivity:

- **Classic compute** (customer-managed VPC/VNet):
  - **AWS**: Configure an S3 Gateway or S3 Interface VPC endpoint in the Databricks workspace VPC. Reference: [Databricks PrivateLink for classic compute (AWS)](https://docs.databricks.com/en/security/network/classic/privatelink.html).
  - **Azure**: Configure VNet `Microsoft.Storage` service endpoints on the workspace subnet. Reference: [Azure Databricks Private Link](https://learn.microsoft.com/en-us/azure/databricks/security/network/classic/private-link-standard).
- **Serverless compute** (Databricks-managed networking):
  - **AWS**: Allowlist Databricks control-plane VPC IDs (via `aws:SourceVpc`) on your S3 bucket policy. Reference: [Databricks IP addresses and domains](https://docs.databricks.com/en/resources/ip-domain-region.html).
  - **Azure**: Add Databricks control-plane NAT IPs per region to your storage account firewall rules. Reference: [Databricks IP addresses and domains](https://docs.databricks.com/en/resources/ip-domain-region.html).

For the cross-vendor steps (block public storage access, provision Snowflake-side storage endpoint, allowlist, verify), see [shared/vended-credentials-private-storage/SKILL.md](../shared/vended-credentials-private-storage/SKILL.md).

### CREATE CATALOG INTEGRATION example (catalog PrivateLink + vended credentials + storage PrivateLink)

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT   = ICEBERG
  REST_CONFIG = (
    CATALOG_API_TYPE = PRIVATE
    CATALOG_URI      = '<databricks_workspace_url>/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME     = '<catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE                = OAUTH
    OAUTH_TOKEN_URI     = '<databricks_workspace_url>/oidc/v1/token'
    OAUTH_CLIENT_ID     = '<your_databricks_client_id>'
    OAUTH_CLIENT_SECRET = '<your_databricks_client_secret>'
    OAUTH_ALLOWED_SCOPES = ('all-apis', 'sql')
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

> **Bearer token**: Also supported — replace the `REST_AUTHENTICATION` block with `TYPE = BEARER` / `BEARER_TOKEN = '<token>'`.

### Enable on an existing integration

> **⚠️ MANDATORY CHECKPOINT**: This `ALTER` modifies a live catalog integration. Present it to the user and wait for explicit approval before executing.

```sql
ALTER CATALOG INTEGRATION <name> SET DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE);
```

### Verify

- `DESC CATALOG INTEGRATION <name>` → `default_storage_config` row should contain `USE_PRIVATELINK_ENDPOINT=true`.
- `SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` → the storage endpoint should show `"status": "available"` (AWS) or `"status": "APPROVED"` (Azure).
- `SELECT * FROM <database>.<schema>.<iceberg_table> LIMIT 1` → end-to-end data probe.

---

## Success Criteria

- ✅ Integration shows `ENABLED=TRUE`
- ✅ `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns success
- ✅ Namespaces discoverable
- ✅ Tables visible

---

## Documentation

- [Configure Catalog Integration for Unity Catalog](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-unity)
- [Configure Catalog Integration with Outbound Private Connectivity (PrivateLink)](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-private)
- [Snowflake Iceberg Tables](https://docs.snowflake.com/user-guide/tables-iceberg)
- [Unity Catalog Documentation](https://docs.databricks.com/en/data-governance/unity-catalog/index.html)
- [Databricks PrivateLink (AWS)](https://docs.databricks.com/en/security/network/classic/privatelink.html)
- [Databricks PrivateLink VPC Endpoint Service IDs by Region (AWS)](https://docs.databricks.com/aws/en/resources/ip-domain-region#privatelink)
- [Azure Databricks Private Link](https://learn.microsoft.com/en-us/azure/databricks/security/network/classic/private-link-standard)
