---
name: unitycatalog-setup-prerequisites
description: "Gather prerequisites for Unity Catalog catalog integration setup"
parent_skill: unitycatalog-catalog-integration-setup
---

# Prerequisites Gathering

Collect all required information to create your Unity Catalog catalog integration.

This skill focuses on **Snowflake-side setup** only. Unity Catalog setup in Databricks should be completed beforehand.

## When to Load

From main skill Step 1: Prerequisites gathering phase

## Prerequisites

User should have:
- Access to a Databricks workspace with Unity Catalog enabled
- Iceberg tables registered in Unity Catalog
- Admin access to Snowflake to create catalog integrations
- Service principal or personal access token (PAT) for authentication

> **Note**: If you need help setting up Unity Catalog, see: [Unity Catalog Documentation](https://docs.databricks.com/en/data-governance/unity-catalog/index.html)

## Workflow

Collect prerequisites **one at a time** in the following order. Wait for user response before proceeding to next question.

---

### Step 1.1: Confirm Unity Catalog Setup (FIRST)

**Ask**:
```
Before we begin, let's confirm your Databricks setup:

Do you have a Databricks workspace with:
✓ Unity Catalog enabled
✓ Iceberg tables registered

(If you need to set up Unity Catalog first, see:
https://docs.databricks.com/en/data-governance/unity-catalog/index.html)
```

**If Yes** → Continue to Step 1.2

**If No** → 
```
This skill helps connect Snowflake to an EXISTING Unity Catalog.

Please set up Unity Catalog and register Iceberg tables first,
then return to create the catalog integration.
```

**STOP** - Cannot proceed without existing Unity Catalog setup

---

### Step 1.2: Authentication Method

**Ask**:
```
Which authentication method would you like to use?

A: OAuth (Recommended for Production)
   ✓ Service principal with OAuth credentials
   ✓ More secure, supports credential rotation
   ✓ No token expiration concerns

B: Bearer Token / PAT (Simpler for Testing)
   ✓ Quick setup with personal access token
   ✓ Good for development/testing
   ⚠ Token expires (default 90 days)
```

**Record user choice** → Continue based on selection

---

### Step 1.3: Access Delegation Mode

**Ask**:
```
How should Snowflake access the Iceberg data files?

A: Vended Credentials (Recommended)
   ✓ Unity Catalog generates temporary credentials
   ✓ No external volume needed
   ✓ Simpler setup

B: External Volume Credentials
   ✓ Works with all configurations
   ✗ Requires separate external volume setup
```

**Record user choice** → Continue to Step 1.4

---

### Step 1.4: Connectivity Type

**Ask**:
```
How should Snowflake connect to Databricks?

A: Public (Default) - Connect over public internet
B: Private (PrivateLink) - Connect via AWS PrivateLink or Azure Private Link
   ⚠ Requires Business Critical Edition (or higher)
```

**If user selects Private (PrivateLink)**, suggest they verify their account edition (do NOT execute — user must have access to the ORGANIZATION_USAGE schema):
```sql
SELECT EDITION
  FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
  WHERE ACCOUNT_NAME = CURRENT_ACCOUNT();
```
Must return `BUSINESS_CRITICAL` or higher. See: [Find your current edition](https://docs.snowflake.com/en/user-guide/intro-editions#find-your-current-edition).

**Record**: Connectivity type

**If Private (PrivateLink)**:

1. **Note for vended credentials users**: If user previously chose Vended Credentials in Step 1.3, inform them:
   ```
   ℹ️ Vended credentials are compatible with catalog-server PrivateLink
   (CATALOG_API_TYPE = PRIVATE). Snowflake can generate temporary credentials
   from Unity Catalog while routing catalog API calls through PrivateLink.

   Optionally, Snowflake-to-storage traffic can also traverse PrivateLink
   by setting DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE).
   You will be asked about this below.
   ```
   Keep `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` as chosen.

2. **Determine cloud provider**:

   **Ask**:
   ```
   Which cloud provider hosts your Databricks workspace?

   A: AWS (Databricks on AWS)
   B: Azure (Azure Databricks)
   ```

   **Record**: Cloud provider

3. **Gather PrivateLink-specific information based on cloud provider**:

   #### If AWS:

   **Ask**:
   ```
   For AWS PrivateLink, I need the following:

   1. PrivateLink VPC endpoint service ID for Unity Catalog front-end
      → Find this in Databricks docs: "PrivateLink VPC endpoint services" for your AWS region
      → Copy the "Workspace (including REST API)" service ID
       → Example: com.amazonaws.vpce.us-west-2.vpce-svc-0123456789abcdef0

   What is your VPC endpoint service ID?
   ```

   **Record**: VPC endpoint service ID

   > **Reference**: See [Configure Front-end PrivateLink (Databricks)](https://docs.databricks.com/en/security/network/classic/privatelink.html) and [PrivateLink VPC endpoint service IDs by region (Databricks)](https://docs.databricks.com/aws/en/resources/ip-domain-region#privatelink) in the Databricks documentation for the list of VPC endpoint service IDs per AWS region.

   #### If Azure:

   **Ask**:
   ```
   For Azure Private Link, I need the following:

   1. Databricks workspace Resource ID from Azure Portal
      → In Azure Portal, open your Databricks workspace
      → On the Overview page, in Essentials, click "JSON View"
      → Copy the "Resource ID" string
      → Example: /subscriptions/1111-22-333-4444-55555/resourceGroups/my-rg/providers/Microsoft.Databricks/workspaces/my-databricks-workspace

   What is your Databricks workspace Resource ID?
   ```

   **Record**: Databricks workspace resource ID

#### Storage-side PrivateLink (when using vended credentials)

When `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` was chosen in Step 1.3, Snowflake-to-storage traffic can also traverse PrivateLink. Before enabling this, ensure Unity Catalog can reach storage privately:

- **Classic compute** (customer-managed VPC/VNet):
  - **AWS**: Confirm an S3 Gateway or S3 Interface VPC endpoint is configured in the Databricks workspace VPC.
  - **Azure**: Confirm VNet `Microsoft.Storage` service endpoints are enabled on the workspace subnet.
- **Serverless compute** (Databricks-managed networking):
  - **AWS**: Allowlist Databricks control-plane VPC IDs (via `aws:SourceVpc`) on the S3 bucket policy.
  - **Azure**: Add Databricks control-plane NAT IPs per region to the storage account firewall rules.
  - Reference: [Databricks IP addresses and domains](https://docs.databricks.com/en/resources/ip-domain-region.html).

**Ask** (only when `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`):
```
Do you want Snowflake-to-storage traffic to also traverse PrivateLink?
(Uses DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE).
Requires a separate storage PrivateLink endpoint — see the cross-vendor
guide at shared/vended-credentials-private-storage/SKILL.md for provisioning steps.)

yes / no
```

**Record**: `enable_storage_privatelink` (yes/no)

For the full cross-vendor storage PrivateLink setup steps, see [shared/vended-credentials-private-storage/SKILL.md](../../shared/vended-credentials-private-storage/SKILL.md).

---

### Step 1.5: Databricks Workspace Host

**Ask**:
```
What is your Databricks workspace host?

(Find at: Your Databricks URL, e.g., the part after https://)

Example: dbc-b6a22903-2e25.cloud.databricks.com
```

**Record**: Databricks workspace host

**Derive**: Catalog URI = `https://<host>/api/2.1/unity-catalog/iceberg-rest`

---

### Step 1.6: Unity Catalog Name

**Ask**:
```
What is the name of your Unity Catalog?

(Find at: Databricks → Data → Catalogs, or run SHOW CATALOGS)
This is case-sensitive.

Common examples: main, unity_catalog, prod_catalog
```

**Record**: Catalog name

---

### Step 1.7: Catalog Namespace (Optional)

**Ask**:
```
Would you like to set a default namespace (schema)?

- If yes: Provide the schema name (case-sensitive)
- If no: Type "skip" (you can specify per-table later)

(Find schemas at: Databricks → Data → Your Catalog → Schemas)
```

**Record**: Namespace (or "skipped")

> **Note**: If skipped, omit the CATALOG_NAMESPACE parameter entirely from the SQL.
> Do NOT use an empty string '' - this will cause an error.

---

### Step 1.8A: OAuth Credentials (If OAuth selected)

**If user chose OAuth in Step 1.2**:

**Ask**:
```
Do you have OAuth credentials from a Databricks service principal?

You'll need:
- OAuth Client ID
- OAuth Client Secret
- OAuth Token URI

How to get credentials:
1. Databricks → User menu → Settings → Identity and Access → Service Principals
2. Create or select a service principal
3. Generate OAuth secret
4. Note Client ID and Secret

The service principal needs Unity Catalog privileges:
- USE CATALOG on the catalog
- USE SCHEMA on schemas
- SELECT on tables
```

**If Yes** → Ask for each credential:

**Ask**: "What is your OAuth Client ID?"
**Record**: OAuth Client ID

**Ask**: "What is your OAuth Client Secret?"
**Record**: OAuth Client Secret

**Derive**: OAuth Token URI = `https://<databricks_host>/oidc/v1/token`

> **Consistency Check**: Verify that the host in the OAuth Token URI matches the host in the Catalog URI (both derived from Step 1.5). If the user provided different workspace hosts at any point during the conversation, reconcile them now — CATALOG_URI and OAUTH_TOKEN_URI **must** use the same workspace host. A mismatch will cause `invalid_client` OAuth errors.

**If No** → 
```
You need a service principal with OAuth credentials to proceed.

Please create one in Databricks:
1. Admin Console → Service Principals → Add
2. Generate OAuth secret
3. Grant Unity Catalog privileges

Then return with the Client ID and Secret.
```

**STOP** - Cannot proceed without OAuth credentials

---

### Step 1.8C: OAuth Allowed Scopes (If OAuth selected)

**Ask**:
```
What OAuth scopes should be allowed?

For Databricks Unity Catalog, the common scope is:
- all-apis - Access all Databricks APIs (recommended)

You can also specify more restrictive scopes if needed.

Default: all-apis
```

**Record**: OAuth Allowed Scopes (default to `all-apis` if user accepts default)

---

### Step 1.8B: Bearer Token (If Bearer selected)

**If user chose Bearer Token in Step 1.2**:

**Ask**:
```
Do you have a Databricks Personal Access Token (PAT)?

How to get a PAT:
1. Databricks → Settings → User Settings → Access Tokens
2. Generate new token
3. Copy and securely store it

Note: Default token lifetime is 90 days. The user/service account
needs Unity Catalog privileges on the catalog/schemas/tables.
```

**If Yes** → 

**Ask**: "What is your Bearer Token (PAT)?"
**Record**: Bearer Token

**If No** → 
```
You need a Personal Access Token to proceed.

Please create one in Databricks:
1. Settings → User Settings → Access Tokens
2. Generate new token
3. Set appropriate lifetime

Then return with the token.
```

**STOP** - Cannot proceed without Bearer Token

---

### Step 1.9: Integration Name

**Ask**:
```
What would you like to name your catalog integration?

Guidelines:
- Alphanumeric characters and underscores only
- Must be unique in your Snowflake account

Default suggestion: unity_catalog_int
```

**Record**: Integration name

---

### Step 1.10: Prerequisites Summary

**Present complete checklist based on authentication method**:

**For OAuth**:
```
Prerequisites Checklist
═══════════════════════════════════════════════════════════

✓ Databricks Host: <databricks_host>
✓ Catalog URI: https://<host>/api/2.1/unity-catalog/iceberg-rest
✓ Catalog Name: <catalog_name>
✓ Catalog Namespace: <namespace|Omitted>
✓ Access Delegation Mode: <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
✓ Connectivity: <Public|Private>
✓ Authentication: OAuth
✓ OAuth Client ID: <client_id>
✓ OAuth Client Secret: ********
✓ OAuth Token URI: https://<host>/oidc/v1/token
✓ OAuth Allowed Scopes: <scopes>
✓ Integration Name: <integration_name>

═══════════════════════════════════════════════════════════
```

**For Bearer Token**:
```
Prerequisites Checklist
═══════════════════════════════════════════════════════════

✓ Databricks Host: <databricks_host>
✓ Catalog URI: https://<host>/api/2.1/unity-catalog/iceberg-rest
✓ Catalog Name: <catalog_name>
✓ Catalog Namespace: <namespace|Omitted>
✓ Access Delegation Mode: <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
✓ Connectivity: <Public|Private>
✓ Authentication: Bearer Token (PAT)
✓ Bearer Token: ********
✓ Integration Name: <integration_name>

═══════════════════════════════════════════════════════════
```

**If Private (PrivateLink)**, also include based on cloud provider:

**For AWS PrivateLink**:
```
PrivateLink Details (AWS):
─────────────────────────────────────────
✓ Cloud Provider:          AWS
✓ Edition:                 Business Critical (or higher)
✓ VPC Endpoint Service ID: <vpc_endpoint_service_id>
✓ Workspace Host Name:     <databricks_workspace_host_name>
✓ Access Delegation:       <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
✓ Storage PrivateLink:     <enable_storage_privatelink>
─────────────────────────────────────────

Note: PrivateLink endpoint will be provisioned in Snowflake
during the creation step (requires ACCOUNTADMIN). After
provisioning, you will need to register Snowflake's VPC endpoint
in the Databricks account console.
```

**For Azure Private Link**:
```
PrivateLink Details (Azure):
─────────────────────────────────────────
✓ Cloud Provider:              Azure
✓ Edition:                     Business Critical (or higher)
✓ Workspace Resource ID:       <databricks_workspace_resource_id>
✓ Workspace Host Name:         <databricks_workspace_host_name>
✓ Sub-resource:                databricks_ui_api
✓ Access Delegation:           <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
✓ Storage PrivateLink:         <enable_storage_privatelink>
─────────────────────────────────────────

Note: PrivateLink endpoint will be provisioned in Snowflake
during the creation step (requires ACCOUNTADMIN). After
provisioning, you will need to approve the private endpoint
connection in Azure Portal → Databricks workspace → Networking.
```

**Add note**:
```
Note: If using EXTERNAL_VOLUME_CREDENTIALS, you'll need an
external volume when creating tables or catalog-linked databases.
```

**⚠️ STOPPING POINT**: "Does everything look correct? Ready to proceed with creating the catalog integration?"

- If yes → Return to main skill → Step 2 (Create)
- If changes needed → Ask what to update

---

## Output

Complete validated prerequisites checklist ready for catalog integration creation.

## Next Steps

After user confirms prerequisites:
- Return to main skill
- Proceed to Step 2: Configuration & Creation
- Load `create/SKILL.md`
