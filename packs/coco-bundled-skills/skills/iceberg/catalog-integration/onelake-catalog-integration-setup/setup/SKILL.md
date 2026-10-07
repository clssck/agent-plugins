---
name: onelake-setup-prerequisites
description: "Gather prerequisites for OneLake REST catalog integration setup"
parent_skill: onelake-catalog-integration-setup
---

# Prerequisites Gathering

Collect all required information to create your OneLake REST catalog integration.

## When to Load

From main skill Step 1: Prerequisites gathering phase

## Prerequisites

User should have:
- A Microsoft Fabric workspace with Iceberg tables in a data item (e.g., lakehouse)
- Azure portal access to create/manage application registrations in Microsoft Entra ID
- Admin access to Snowflake to create catalog integrations and external volumes
- Contributor access (or higher) to the Fabric workspace

## Workflow

Collect prerequisites **one at a time** in the following order. Wait for user response before proceeding to next question.

---

### Step 1.1: Confirm Microsoft Fabric Setup (FIRST)

**Ask**:
```
Before we begin, let's confirm your Microsoft Fabric setup:

Do you have a Microsoft Fabric workspace with:
* A lakehouse (or other data item) containing Iceberg tables
* Access to the Azure portal to create application registrations

(If you need to set up Fabric first, see:
https://learn.microsoft.com/en-us/fabric/get-started/fabric-trial)
```

**If Yes** → Continue to Step 1.2

**If No** →
```
This skill helps connect Snowflake to an EXISTING Microsoft Fabric workspace
with Iceberg tables in OneLake.

Please set up your Fabric workspace and create Iceberg tables first,
then return to create the catalog integration.

Resources:
- Microsoft Fabric documentation: https://learn.microsoft.com/en-us/fabric/get-started/
- OneLake table APIs for Iceberg: https://learn.microsoft.com/en-us/fabric/onelake/onelake-table-api-iceberg
```

**STOP** - Cannot proceed without existing Fabric setup

---

### Step 1.2: Workspace ID

**Ask**:
```
What is your Microsoft Fabric workspace ID?

This is a GUID found in the URL when you navigate to any item in your Fabric workspace.
Example URL: https://app.fabric.microsoft.com/groups/<workspaceID>/...

Example workspace ID: 12345678-abcd-1abc-1a11-111111ab1111

For help finding it, see:
https://learn.microsoft.com/en-us/fabric/admin/portal-workspace#identify-your-workspace-id
```

**Validate**: Should be a GUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

**Record**: Workspace ID

---

### Step 1.3: Data Item ID (Lakehouse ID)

**Ask**:
```
What is your data item ID (lakehouse ID)?

Open your lakehouse in Fabric and look at the URL. The data item ID
is the GUID value after "lakehouses/" in the URL.
Example URL: https://app.fabric.microsoft.com/.../lakehouses/<dataItemID>/...

Example data item ID: 11111111-abcd-1111-1ab1-1111a1a1ab91

For help, see the "Connection" bullet point in:
https://learn.microsoft.com/en-us/fabric/data-factory/connector-lakehouse-overview
```

**Validate**: Should be a GUID format (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)

**Record**: Data item ID

**Derive**:
- Fabric data item scope (CATALOG_NAME): `<workspace_id>/<data_item_id>`
- OneLake storage URL: `azure://onelake.dfs.fabric.microsoft.com/<workspace_id>/<data_item_id>`

---

### Step 1.4: Azure Entra Application Registration

**Ask**:
```
Do you have an existing Azure Entra application registration for this integration,
or do you need to create one?

A: I have an existing application registration
   → Provide the OAuth client ID, Directory (tenant) ID, and OAuth client secret

B: I need to create a new application registration
   → We'll guide you through creation
```

**If existing application (A)**:

Collect the following values one at a time:

1. **Ask**: "What is the OAuth client ID? (This is the Application (client) ID from your Azure Entra app registration Overview page)"
   - **Record**: OAuth client ID

2. **Ask**: "What is the Directory (tenant) ID?"
   - **Record**: Tenant ID

3. **Ask**: "Do you have an OAuth client secret for this application? (You'll need one for OAuth authentication)"
   - If yes → **Record**: OAuth client secret (note: user should keep this secure). Note that the secret also has its own ID, but we want the client ID from the App registration Overview page, not the secret ID.
   - If no → Guide to create one: Azure portal → App registrations → Your app → Certificates & secrets → New client secret (or follow the Azure documentation link in Step 1.4B)

Continue to Step 1.5.

**If new application (B)** → Direct them to Azure documentation:

```
Azure Entra Application Registration
═══════════════════════════════════════════════════════════

Follow the Azure documentation to register a new application:
https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app

During registration, make sure to:
- Add the "user_impersonation" delegated permission for Azure Storage
  (API permissions → Microsoft APIs → Azure Storage)
- Create an OAuth client secret (Certificates & secrets → New client secret)
  ⚠ Copy the secret VALUE immediately — you cannot retrieve it later

When done, come back with these three values:
- OAuth client ID            (Application (client) ID from the Overview page)
- Directory (tenant) ID      (from the Overview page)
- OAuth client secret VALUE

═══════════════════════════════════════════════════════════
```

**STOP** - Wait for user to complete registration and provide values:
- OAuth client ID
- Directory (tenant) ID
- OAuth client secret

> **Can't create the app registration?** If you lack permissions in Azure Entra ID (e.g., your tenant restricts app registrations to admins), ask your Azure AD / Entra ID administrator to either:
> 1. Create the app registration on your behalf and provide the three values above, or
> 2. Grant you the **Application Developer** role in Entra ID so you can create it yourself.

**Record**: All three values. Continue to Step 1.5.

---

### Step 1.5: Verify user_impersonation Permission

**Ask**:
```
Has the "user_impersonation" permission for Azure Storage been added
to your application registration?

This is required for the OAuth flow. You can verify at:
Azure portal → App registrations → Your app → API permissions

You should see:
- Azure Storage → user_impersonation (Delegated)

IMPORTANT: Do NOT switch to the "APIs my organization uses" tab.
Use the "Microsoft APIs" tab and select "Azure Storage".
```

**If Yes** → Continue to Step 1.6
**If No** → Guide them through adding it: Azure portal → App registrations → Your app → API permissions → Add a permission → Microsoft APIs → Azure Storage → Delegated → `user_impersonation`

> **Admin consent**: If your Azure tenant requires admin consent for API permissions, an administrator must also click **"Grant admin consent for [tenant]"** on the API permissions page. Without this, the permission will show as "Not granted" and OAuth will fail at runtime.

---

### Step 1.6: Fabric Workspace Access for Your Azure Entra Application

> **Note**: This step is for **your own Azure Entra application registration** (the one you created/provided in Step 1.4). A separate Snowflake multi-tenant app will be added to the workspace later, after the external volume is created.

**Ask**:
```
Has your Azure Entra application registration (from Step 1.4) been
granted Contributor access (or higher) to your Fabric workspace?

This is YOUR application (OAuth client ID: <oauth_client_id from Step 1.4>),
NOT the Snowflake multi-tenant app (which comes later).

To grant access:
1. Navigate to Microsoft Fabric
2. Open your workspace
3. Select "Manage access"
4. Select "+ Add people or groups"
5. Search for your application's Display name
6. Select "Contributor" access or higher
7. Select "Add"

Has this been done?
```

**If Yes** → Continue to Step 1.7 (Integration Name)
**If No** → Wait for user to complete this step

---

### Step 1.7: Integration Name

> **⚠️ MANDATORY**: You MUST ask the user for the integration name. Do NOT auto-fill a default value or skip this step.

**Ask**:
```
What would you like to name your catalog integration?

Guidelines:
- Alphanumeric characters and underscores only
- Must be unique in your Snowflake account

Example: onelake_catalog_int
```

**Wait for user response.** Do NOT proceed until the user provides a name.

**Record**: Integration name

---

### Step 1.8: External Volume Name

> **⚠️ MANDATORY**: You MUST ask the user for the external volume name. Do NOT auto-fill a default value or skip this step.

**Ask**:
```
What would you like to name your external volume?

Guidelines:
- Alphanumeric characters and underscores only
- Must be unique in your Snowflake account

Example: onelake_extvol
```

**Wait for user response.** Do NOT proceed until the user provides a name.

**Record**: External volume name

---

### Step 1.9: Prerequisites Summary

**Present complete checklist**:

```
Prerequisites Checklist
═══════════════════════════════════════════════════════════

Fabric Configuration:
  ✓ Workspace ID:    <workspace_id>
  ✓ Data Item ID:    <data_item_id>
  ✓ Data Item Scope: <workspace_id>/<data_item_id>

Azure Entra Application:
  ✓ OAuth Client ID:       <oauth_client_id>
  ✓ Tenant ID:             <tenant_id>
  ✓ OAuth Client Secret:   [provided]
  ✓ user_impersonation permission: Configured
  ✓ Workspace Contributor access:  Granted

Derived Values:
  ✓ Catalog URI:     https://onelake.table.fabric.microsoft.com/iceberg
  ✓ Token URI:       https://login.microsoftonline.com/<tenant_id>/oauth2/v2.0/token
  ✓ Storage URL:     azure://onelake.dfs.fabric.microsoft.com/<workspace_id>/<data_item_id>
  ✓ OAuth Scopes:    https://storage.azure.com/.default

Snowflake Object Names:
  ✓ Integration Name:    <integration_name>
  ✓ External Volume:     <extvol_name>

═══════════════════════════════════════════════════════════

Note: After creating the external volume, you will need to:
1. Grant Azure consent for the Snowflake multi-tenant app
2. Add the Snowflake multi-tenant app to your Fabric workspace
```

**⚠️ STOPPING POINT**: "Does everything look correct? Ready to proceed with creating the catalog integration?"

- If yes → Return to main skill → Step 2 (Create)
- If changes needed → Ask what to update

---

## Output

Complete validated prerequisites checklist ready for catalog integration and external volume creation.

## Next Steps

After user confirms prerequisites:
- Return to main skill
- Proceed to Step 2: Configuration & Creation
- Load `create/SKILL.md`
