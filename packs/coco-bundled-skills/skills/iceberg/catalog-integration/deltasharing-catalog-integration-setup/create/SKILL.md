---
name: deltasharing-create-integration
description: "Create and execute catalog integration for Delta Sharing"
parent_skill: deltasharing-catalog-integration-setup
---

# Configuration & Creation

Build and execute the SQL to create your Delta Sharing catalog integration.

## When to Load

From main skill Step 2: After prerequisites have been gathered and confirmed

## Prerequisites

Must have from setup phase:
- Delta Sharing endpoint URL
- Bearer token
- Share name (CATALOG_NAME)
- Access delegation mode
- Integration name

## Workflow

### Step 2.1: Generate Catalog Integration SQL

Generate the SQL based on the chosen access delegation mode.

#### With Vended Credentials

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = DELTA_SHARING
  TABLE_FORMAT = DELTA
  REST_CONFIG = (
    CATALOG_URI = '<delta_sharing_endpoint>'
    CATALOG_NAME = '<share_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<bearer_token>'
  )
  ENABLED = TRUE;
```

#### With External Volume Credentials (default)

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = DELTA_SHARING
  TABLE_FORMAT = DELTA
  REST_CONFIG = (
    CATALOG_URI = '<delta_sharing_endpoint>'
    CATALOG_NAME = '<share_name>'
  )
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<bearer_token>'
  )
  ENABLED = TRUE;
```

**Parameter Explanation**:
- `CATALOG_SOURCE = DELTA_SHARING`: Specifies Delta Sharing as the catalog source
- `TABLE_FORMAT = DELTA`: Delta table format used by Delta Sharing
- `CATALOG_URI`: The Delta Sharing server endpoint URL from the provider's credential file
- `CATALOG_NAME`: The share name to connect to — must match the share name you created in Unity Catalog (or your Delta Sharing provider). Accepts either `'my_share'` or `'shares/my_share'` — Snowflake normalizes both formats
- `ACCESS_DELEGATION_MODE`:
  - `VENDED_CREDENTIALS`: Delta Sharing server provides temporary credentials for data file access (no external volume needed)
  - `EXTERNAL_VOLUME_CREDENTIALS`: Use an external volume for data access (default when omitted)
- `TYPE = BEARER`: Bearer token authentication
- `BEARER_TOKEN`: The bearer token from the provider's credential file (stored securely and masked)
- `ENABLED = TRUE`: Makes the integration available for use immediately

> **Note on CATALOG_NAME**: Each catalog integration maps to a single Delta Sharing share.
> To access multiple shares, create separate catalog integrations — one per share.

> **Note on REST_CONFIG alterability**: `REST_CONFIG` (including `CATALOG_URI`, `CATALOG_NAME`,
> and `ACCESS_DELEGATION_MODE`) cannot be altered after creation. If these values need to change,
> recreate the integration with `CREATE OR REPLACE`.
> `BEARER_TOKEN` in `REST_AUTHENTICATION` can be rotated via `ALTER CATALOG INTEGRATION`.

### Step 2.2: Review & Approval

**Present generated SQL to user**:

```
Generated Catalog Integration SQL:
═══════════════════════════════════════════════════════════
[The complete SQL with actual values filled in]
═══════════════════════════════════════════════════════════

This will create a catalog integration named '<integration_name>'
connecting to Delta Sharing share '<share_name>' using bearer token authentication.
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Please review the SQL above. Ready to execute and create the catalog integration?"

**Wait for explicit approval**:
- "Yes", "Approved", "Looks good", "Proceed" → Continue to Step 2.3
- "No" or "Wait" → Ask: "What changes would you like to make?"

### Step 2.3: Execute Creation

**Important**: The user must have the `CREATE INTEGRATION` privilege on the account. Only the ACCOUNTADMIN role has this privilege by default.

**Execute approved SQL**:
```sql
[The approved CREATE CATALOG INTEGRATION statement]
```

**Expected Success Result**:
```
Integration <integration_name> successfully created.
```

**If Success**: Integration created → Continue to Step 2.4

**If Error**: Present error → Load `references/troubleshooting.md` → Wait for direction

### Step 2.4: Confirm Integration Created

**Execute**:
```sql
DESCRIBE CATALOG INTEGRATION <integration_name>;
```

**Key fields to verify**:

| Property | Expected Value |
|----------|---------------|
| `enabled` | `true` |
| `catalog_source` | `DELTA_SHARING` |
| `table_format` | `DELTA` |

**Present to user**:
```
Catalog Integration Created Successfully:
─────────────────────────────────────────
Name:             <integration_name>
Enabled:          TRUE
Catalog Source:   DELTA_SHARING
Table Format:     DELTA
─────────────────────────────────────────
```

**Output**: Catalog integration created and ready for verification.

**Next**: Return to main skill → Proceed to Step 3 (Verification)

## Error Handling

**Common errors during creation**:

| Error | Cause | Solution |
|-------|-------|----------|
| `Insufficient privileges` | Missing `CREATE INTEGRATION` privilege | Use ACCOUNTADMIN role or grant `CREATE INTEGRATION` to your role |
| `Invalid catalog URI` | Malformed endpoint URL | Verify the endpoint URL from the credential file; must start with `https://` |
| `Integration already exists` | Name collision | Use `CREATE OR REPLACE` or choose a different name |
| `Feature not enabled` | Delta Sharing catalog integration not enabled for account | Contact Snowflake Support to enable the feature |

**For all errors**: Present error message clearly and load troubleshooting guide if needed.

## Output

Successfully created catalog integration in Snowflake, ready for verification.

## Next Steps

After successful creation:
- Return to main skill
- Proceed to Step 3: Verification
- Load `verify/SKILL.md`
