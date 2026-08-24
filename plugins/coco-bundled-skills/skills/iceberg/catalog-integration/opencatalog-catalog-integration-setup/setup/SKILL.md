---
name: opencatalog-setup-prerequisites
description: "Gather prerequisites for OpenCatalog catalog integration setup (public and PrivateLink)"
parent_skill: opencatalog-catalog-integration-setup
---

# Prerequisites Gathering

Collect all required information to create your OpenCatalog catalog integration.

This skill focuses on **Snowflake-side setup** only. OpenCatalog account and catalog setup should be completed beforehand.

## When to Load

From main skill Step 1: Prerequisites gathering phase

## Prerequisites

User should have:
- Access to an OpenCatalog account with an internal catalog
- Iceberg tables registered in OpenCatalog
- Admin access to Snowflake to create catalog integrations

> **Note**: If you need help setting up OpenCatalog, see: [OpenCatalog Documentation](https://other-docs.snowflake.com/en/opencatalog/overview)

## Workflow

Collect prerequisites **one at a time** in the following order. Wait for user response before proceeding to next question.

---

### Step 1.1: Confirm OpenCatalog Setup (FIRST)

**Ask**:
```
Before we begin, let's confirm your OpenCatalog setup:

Do you have an OpenCatalog account with:
✓ An internal catalog configured
✓ Iceberg tables registered

(If you need to set up OpenCatalog first, see:
https://other-docs.snowflake.com/en/opencatalog/overview)
```

**If Yes** → Continue to Step 1.2

**If No** → 
```
This skill helps connect Snowflake to an EXISTING OpenCatalog catalog.

Please set up your OpenCatalog account and register Iceberg tables first,
then return to create the catalog integration.
```

**STOP** - Cannot proceed without existing OpenCatalog setup

---

### Step 1.2: Access Delegation Mode

**Ask**:
```
How should Snowflake access the Iceberg data files?

A: Vended Credentials (Recommended for public connectivity)
   ✓ OpenCatalog generates temporary credentials
   ✓ No external volume needed
   ✓ Simpler setup

B: External Volume Credentials
   ✓ Works with all configurations
   ✓ Use this when you need to keep credentials in a Snowflake-managed external volume
   ✗ Requires separate external volume setup
```

**Record user choice** → Continue to Step 1.3

---

### Step 1.3: Connectivity Type

**Ask**:
```
How should Snowflake connect to OpenCatalog?

A: Public (Default) - Connect over public internet
B: Private (PrivateLink) - Connect via PrivateLink
   ⚠ Requires Business Critical Edition (or higher)
   ℹ Vended credentials work with PrivateLink. To also route Snowflake-to-storage traffic via PrivateLink while using vended credentials, set DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE) on the catalog integration. See the main SKILL.md section "Vended credentials with private connectivity to storage".

Most users choose Public unless you have specific security requirements.
```

**If user selects Private (PrivateLink)**, note that Business Critical Edition (or higher) is required. The edition will be verified in the **create** step before proceeding.

**Record**: Connectivity type

**If Private (PrivateLink)**:

1. **Vended credentials are supported with PrivateLink**: If the user chose Vended Credentials in Step 1.2, keep that choice. If they also want Snowflake-to-storage traffic to traverse PrivateLink, ask whether they want to enable storage-side PrivateLink:
   ```
   You chose Vended Credentials. By default, Snowflake reaches your
   storage over the public internet using the catalog-vended token.
   Do you also want Snowflake-to-storage traffic to use PrivateLink?
   (If yes, you'll need to provision an S3 / Azure Storage PrivateLink
    endpoint and set DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT
     = TRUE) on the catalog integration. See ../../shared/next-steps/
    SKILL.md → "Enable private connectivity to storage with vended
    credentials" for the cross-vendor flow.)
   ```
   Record the answer as `enable_storage_privatelink: yes|no`.

2. Continue to Step 1.3a

**If Public** → Continue to Step 1.3a

---

### Step 1.3a: OpenCatalog Account Identifier

**Ask**:
```
What is your OpenCatalog account identifier?

There are two formats. Format 1 is preferred:

Format 1 (Preferred): Account name in your organization (regionless)
  <orgname>-<account_name>
  Example: myorg-myaccount

Format 2: Account locator
  <account_locator>.<deployment_name>.<region>
  Example: xy12345.us-west-2

How to find:
- OpenCatalog UI → Account settings
- Or see: https://other-docs.snowflake.com/en/opencatalog/find-account-name
- Account identifier formats: https://docs.snowflake.com/en/user-guide/admin-account-identifier

We recommend Format 1 (account name in your organization).
```

**Record**: OpenCatalog account identifier

**Validate format**: Check whether the input matches Format 1 or Format 2:
- **Format 1** (no dots): `<orgname>-<account_name>` (e.g., `myorg-myaccount`)
- **Format 2** (contains dots): `<account_locator>.<region>` (e.g., `xy12345.us-west-2`)

**Derive URLs based on connectivity type** (from Step 1.3):

- **If Public**:
  - Account URL = `https://<account_identifier>.snowflakecomputing.com`
  - Catalog URI = `https://<account_identifier>.snowflakecomputing.com/polaris/api/catalog`
- **If Private (PrivateLink)**:
  - Account URL = `https://<account_identifier>.privatelink.snowflakecomputing.com`
  - Catalog URI = `https://<account_identifier>.privatelink.snowflakecomputing.com/polaris/api/catalog`
  - PrivateLink host = `<account_identifier>.privatelink.snowflakecomputing.com`

> The rule is the same for both identifier formats: insert `.privatelink` before `.snowflakecomputing.com`. For example, `datalakecatalog-testpolaris` becomes `datalakecatalog-testpolaris.privatelink.snowflakecomputing.com`.

**Present derived URL to user for confirmation**:
```
Based on your input, the derived URLs are:

  Account URL: <derived_account_url>
  Catalog URI: <derived_catalog_uri>

Does this look correct?
```

**If user says the URL is wrong** → Ask them to provide the correct URL directly.

---

### Step 1.3b: VPCE Service ID (Cross-Deployment PrivateLink Only)

> **Skip this step if using Public connectivity.**
> **Skip this step if OpenCatalog and Snowflake are in the same deployment** — endpoint provisioning is not needed for same-deployment PrivateLink because Snowflake automatically handles internal traffic routing when `CATALOG_API_TYPE=PRIVATE` is specified.

**Ask**:
```
Is your OpenCatalog account in a different deployment than
your Snowflake account (cross-deployment)?

Hint: Accounts in the same deployment share the same region segment in
their account URL (e.g., both use *.us-west-2.snowflakecomputing.com).
You can compare the account URLs to check.

- If yes (cross-deployment): You'll need the VPCE Service ID to provision
  a PrivateLink endpoint.
- If no (same deployment): You can skip this — endpoint provisioning is
  not needed. Snowflake routes traffic internally when CATALOG_API_TYPE=PRIVATE.
- If unsure: You can skip for now. If connectivity fails later, you may
  need to come back and provision the endpoint.
```

**If same deployment or unsure** → Skip to Step 1.4 (Catalog Name), record VPCE Service ID as "N/A (same deployment)"

**If cross-deployment**, ask:
```
What is the VPCE Service ID for your OpenCatalog account?

This is used to provision the PrivateLink endpoint in Snowflake.

How to find:
- OpenCatalog UI → Settings → Inbound PrivateLink section
- Look for "VPCE Service ID"

Example: com.amazonaws.vpce.us-west-2.vpce-svc-1234567890abcdef0
```

**Record**: VPCE Service ID

Present to user:
```
PrivateLink Configuration:
─────────────────────────────────────────
VPCE Service ID:     <vpce_service_id>
PrivateLink Host:    <privatelink_host>
PrivateLink URL:     https://<privatelink_host>/polaris/api/catalog
─────────────────────────────────────────

These will be used to provision the PrivateLink endpoint
during the creation step (cross-deployment only).
```

---

### Step 1.4: Catalog Name

**Ask**:
```
What is the name of your OpenCatalog catalog?

(Find at: OpenCatalog UI → Catalogs)
This is case-sensitive.

Example: my_catalog
```

**Record**: Catalog name

---

### Step 1.5: Catalog Namespace (Optional)

**Ask**:
```
Would you like to set a default namespace?

- If yes: Provide the namespace name (case-sensitive)
- If no: Type "skip" (you can specify per-table later)

(Find namespaces at: OpenCatalog UI → Catalog → Namespaces)
```

**Record**: Namespace (or "skipped")

> **Note**: If skipped, omit the CATALOG_NAMESPACE parameter entirely from the SQL.
> Do NOT use an empty string '' - this will cause an error.

---

### Step 1.6: OAuth Credentials

**Ask**:
```
Do you have OAuth credentials from an OpenCatalog service connection?

You'll need:
- OAuth Client ID
- OAuth Client Secret
- One or more scopes (e.g., PRINCIPAL_ROLE:ALL or specific principal roles)

How to get credentials:
1. OpenCatalog UI → Service Connections
2. Create or select a service connection
3. Note the Client ID and Secret

The service connection must have a catalog role with privileges:
- CATALOG_LIST_PROPERTIES
- NAMESPACE_LIST  
- TABLE_LIST
```

**If Yes** → Ask for Client ID, Client Secret, and Scopes separately:

**Ask**: "What is your OAuth Client ID?"
**Record**: OAuth Client ID

**Ask**: "What is your OAuth Client Secret?"
**Record**: OAuth Client Secret

**Ask**: "What OAuth scopes should be allowed? (e.g., `PRINCIPAL_ROLE:ALL` for all roles, or a specific principal role like `PRINCIPAL_ROLE:myrole`)"
**Record**: OAuth Allowed Scopes

**If connectivity is Private (PrivateLink)** →

**Ask**: "Are you using an external Identity Provider (e.g., Okta, Auth0) for OAuth, or OpenCatalog's built-in IdP?"

- **If external IdP** →
  **Ask**: "What is your OAuth token endpoint URI? (e.g., `https://your-idp.example.com/oauth2/token`)"
  **Record**: OAuth Token URI
  **Ask**: "Does your external IdP support inbound PrivateLink connections?"
  **Record**: External IdP PrivateLink Support (Yes/No)

- **If OpenCatalog IdP (default)** → No additional info needed.

**If No** → 
```
You need a service connection with OAuth credentials to proceed.

Please create one in OpenCatalog:
1. OpenCatalog UI → Service Connections → Create
2. Assign a principal role with catalog access
3. Generate credentials

Then return with the Client ID and Secret.
```

**STOP** - Cannot proceed without OAuth credentials

---

### Step 1.7: Integration Name

**Ask**:
```
What would you like to name your catalog integration?

Guidelines:
- Alphanumeric characters and underscores only
- Do NOT use hyphens — names with hyphens become case-sensitive quoted
  identifiers, which causes system functions like
  SYSTEM$VERIFY_CATALOG_INTEGRATION to fail
- Must be unique in your Snowflake account

Default suggestion: opencatalog_int
```

**Record**: Integration name

---

### Step 1.8: Prerequisites Summary

**Present complete checklist**:

```
Prerequisites Checklist
═══════════════════════════════════════════════════════════

✓ OpenCatalog Account URL: <account_url>
✓ Catalog URI: <catalog_uri>
✓ Catalog Name: <catalog_name>
✓ Catalog Namespace: <namespace|Omitted>
✓ Access Delegation Mode: <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
✓ Connectivity: <Public|Private (PrivateLink)>
✓ OAuth Client ID: <client_id>
✓ OAuth Client Secret: ********
✓ OAuth Allowed Scopes: <scopes>
✓ Integration Name: <integration_name>

═══════════════════════════════════════════════════════════

Note: If using EXTERNAL_VOLUME_CREDENTIALS, you'll need an
external volume when creating tables or catalog-linked databases.
```

**If Private (PrivateLink)**, also include:
```
PrivateLink Details:
─────────────────────────────────────────
✓ Edition:              Business Critical (or higher)
✓ VPCE Service ID:      <vpce_service_id|N/A (same deployment)>
✓ PrivateLink Host:     <privatelink_host>
✓ PrivateLink URL:      https://<privatelink_host>/polaris/api/catalog
✓ OAuth IdP:            <OpenCatalog (default)|External (<idp_name>)>
✓ Storage-side PrivateLink:  <yes|no>
─────────────────────────────────────────

Note: PrivateLink endpoint provisioning is only required for
cross-deployment setups (OpenCatalog and Snowflake in different
deployments). If same deployment, provisioning is not needed —
Snowflake routes traffic internally when CATALOG_API_TYPE=PRIVATE.
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
