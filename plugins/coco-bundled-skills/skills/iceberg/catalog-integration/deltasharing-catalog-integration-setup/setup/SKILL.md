---
name: deltasharing-setup-prerequisites
description: "Gather prerequisites for Delta Sharing catalog integration setup"
parent_skill: deltasharing-catalog-integration-setup
---

# Prerequisites Gathering

Collect all required information to create your Delta Sharing catalog integration.

## When to Load

From main skill Step 1: Prerequisites gathering phase

## Prerequisites

User should have:
- A Delta Sharing server accessible over the internet (e.g., Databricks Unity Catalog with Delta Sharing enabled)
- A **credential file** from the Delta Sharing provider containing the endpoint URL and bearer token
- Admin access to Snowflake to create catalog integrations (`CREATE INTEGRATION` privilege on the account)

## Important: Delta Sharing Connectivity Model

Delta Sharing catalog integration is straightforward:
- **Public connectivity only** — no PrivateLink support
- **Bearer token authentication** — token obtained from the provider's credential file
- **Share-scoped** — each integration connects to a single Delta Sharing share (`CATALOG_NAME`)
- **Delta table format** — `TABLE_FORMAT = DELTA`
- **Vended credentials optional** — `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` enables credential vending for CLD; defaults to `EXTERNAL_VOLUME_CREDENTIALS`

## Workflow

Collect prerequisites **one at a time** in the following order. Wait for user response before proceeding to next question.

---

### Step 1.1: Confirm Delta Sharing Server Setup (FIRST)

**Ask**:
```
Before we begin, let's confirm your Delta Sharing setup:

Do you have:
- A Delta Sharing server with data available for sharing
- A credential file from the provider containing the endpoint URL and bearer token

(If you need to set up Delta Sharing on the provider side first, please do so
and obtain a credential file before continuing.)
```

**If Yes** → Continue to Step 1.2

**If No** →
```
This skill helps connect Snowflake to an EXISTING Delta Sharing server.

Please obtain the Delta Sharing credential file from your provider
(e.g., from Databricks Unity Catalog → Data → Delta Sharing → Recipients),
then return to create the catalog integration.

Resources:
- Delta Sharing Protocol: https://delta.io/sharing/
```

**STOP** - Cannot proceed without a credential file from the provider

---

### Step 1.2: Extract Credentials from Credential File

**Ask**:
```
Please share your Delta Sharing credential file in one of these ways:

A: Paste the file contents directly into the chat
B: Upload the credential file as an attachment
C: Provide the file path (e.g. /path/to/credential.json or ~/Downloads/config.json)
D: Enter the values manually
```

**Route based on response**:

**If A (file contents pasted)** — the credential file is JSON. Extract directly from the pasted text:
- `endpoint` field → Delta Sharing endpoint URL
- `bearerToken` field → Bearer token

Example credential file format:
```json
{
  "shareCredentialsVersion": 1,
  "bearerToken": "<token>",
  "endpoint": "https://<recipient-id>.delta-sharing.<region>.<domain>/api/2.0/delta-sharing/metastores/<id>",
  "expirationTime": "..."
}
```

**If B (file uploaded as attachment)** — read the uploaded file contents and extract both fields:
- `endpoint` field → Delta Sharing endpoint URL
- `bearerToken` field → Bearer token

**If C (file path provided)** — read the file and extract both fields:
```bash
cat <file_path>
```
Then parse `endpoint` and `bearerToken` from the JSON output.

**If D (manual entry)** — ask for each value separately:

*Endpoint URL*:
```
What is the Delta Sharing endpoint URL?
(found under the "endpoint" field in your credential file)

Example: https://{recipient-id}.delta-sharing.{region}.{domain}/api/2.0/delta-sharing/metastores/<id>
```

*Bearer token*:
```
What is the bearer token?
(found under the "bearerToken" field in your credential file)

Note: This token will be stored securely and masked in Snowflake.
```

**Record**: Delta Sharing endpoint URL and bearer token

---

### Step 1.3: Share Name (CATALOG_NAME)

**Ask**:
```
What is the name of the Delta Sharing share you want to connect to?

This is the share name from the provider. It must match the share name you created in Unity Catalog (or your Delta Sharing provider). You can specify it as:
- Bare name:  my_share
- With prefix: shares/my_share  (both formats are accepted)

If you are unsure, check with your Delta Sharing provider for the exact share name.
```

**If user doesn't know the share name** — create a temporary catalog integration with the endpoint and bearer token, then list all shares the endpoint has access to:

```sql
-- Create a temporary integration to discover available shares
CREATE OR REPLACE CATALOG INTEGRATION <temp_integration_name>
  CATALOG_SOURCE = DELTA_SHARING
  TABLE_FORMAT = DELTA
  REST_CONFIG = (
    CATALOG_URI = '<endpoint_url>'
    CATALOG_NAME = 'placeholder'
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<bearer_token>'
  )
  ENABLED = TRUE;

-- List all shares the endpoint has access to
SELECT SYSTEM$LIST_CATALOGS('<temp_integration_name>');
```

The result is a JSON array of share names. Use one of those as the `CATALOG_NAME`.

**Record**: Share name (CATALOG_NAME)

---

### Step 1.4: Access Delegation Mode

**Ask**:
```
How should Snowflake access the underlying table data files?

A: Vended Credentials (recommended for Catalog-Linked Databases)
   → Delta Sharing server provides temporary credentials for data access
   → No external volume needed

B: External Volume Credentials (default)
   → Snowflake uses an existing external volume for data access
   → Requires an external volume to be configured
```

**Record**: Access delegation mode (`VENDED_CREDENTIALS` or `EXTERNAL_VOLUME_CREDENTIALS`)

If user selects **B** and does not have an external volume, note that one will be needed when creating tables/CLDs.

---

### Step 1.5: Integration Name

**Ask**:
```
What would you like to name your catalog integration?

Guidelines:
- Alphanumeric characters and underscores only
- Must be unique in your Snowflake account

Default suggestion: delta_sharing_catalog_int
```

**Record**: Integration name

---

### Step 1.6: Prerequisites Summary

**Present complete checklist**:

```
Prerequisites Checklist
═══════════════════════════════════════════════════════════

 Catalog Source:          DELTA_SHARING
 Table Format:            DELTA
 Endpoint URL:            <endpoint_url>
 Bearer Token:            ******* (masked)
 Share Name:              <share_name>
 Access Delegation Mode:  <VENDED_CREDENTIALS | EXTERNAL_VOLUME_CREDENTIALS>
 Integration Name:        <integration_name>

═══════════════════════════════════════════════════════════
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
