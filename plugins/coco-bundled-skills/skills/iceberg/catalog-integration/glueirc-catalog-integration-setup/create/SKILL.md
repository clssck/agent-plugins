---
name: glueirc-create-integration
description: "Create and execute catalog integration for AWS Glue IRC"
parent_skill: glueirc-catalog-integration-setup
---

# Configuration & Creation

Build and execute the SQL to create your AWS Glue Iceberg REST catalog integration, then configure the AWS trust relationship.

## When to Load

From main skill Step 2: After prerequisites have been gathered and confirmed

## Prerequisites

Must have from setup phase:
- IAM role ARN with Glue permissions (for `VENDED_CREDENTIALS`: this is the catalog role — see Step 2.5a)
- Access delegation mode choice
- Connectivity type (Public/Private)
- AWS account ID and region
- Glue catalog name
- Glue database name (optional)
- Integration name
- Custom external ID (optional — Snowflake auto-generates if not provided)

> **For `VENDED_CREDENTIALS` only**: You will need a **second IAM role** (the data access role) in Step 2.5a. You can create it during that step if it doesn't already exist.

## Workflow

### Step 2.0: Provision PrivateLink Endpoint (PrivateLink Only)

> **Skip this step entirely if using Public connectivity.** Jump to [Step 2.1](#step-21-generate-catalog-integration-sql).

> **⚠️ PrivateLink constraints (AWS Glue)**:
> - Requires **Business Critical Edition (or higher)**. To inquire about upgrading, please contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge).
> - `ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>` — selects how Snowflake accesses S3: catalog-vended credentials, or an external volume. It is **not** a connectivity setting. Both modes can route Snowflake-to-S3 traffic over outbound PrivateLink — external volumes already support it; for vended credentials, also set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. Independent of catalog-server PrivateLink (`CATALOG_API_TYPE`).
> - Requires ACCOUNTADMIN role for PrivateLink provisioning.
> - **Cross-region PrivateLink is NOT supported.** The Snowflake account and the Glue Data Catalog must be in the same AWS region. This is an AWS-side limitation — AWS does not support cross-region PrivateLink provisioning for the Glue service. See: [AWS cross-region PrivateLink support](https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-cross-region-privatelink-support.html)
>
> **Exception — Amazon S3 Tables direct path** (`AWS_PRIVATE_S3TABLES`): Vended credentials ARE supported with PrivateLink. This requires two PrivateLink endpoints (one for `s3tables`, one for `s3`) and `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. See the S3 Tables sections below.

**Verify account edition** before proceeding:
> ⚠️ Do NOT execute this query directly. Ask the user to run it — they must have access to the ORGANIZATION_USAGE schema.
```sql
SELECT EDITION
  FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
  WHERE ACCOUNT_NAME = CURRENT_ACCOUNT();
```
Must return `BUSINESS_CRITICAL` or higher. See: [Find your current edition](https://docs.snowflake.com/en/user-guide/intro-editions#find-your-current-edition).

#### Step 2.0a: Check for Existing PrivateLink Endpoint

Before provisioning, check if a PrivateLink endpoint for Glue in this region already exists:

```sql
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();

-- Alternative: query the Account Usage view
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

Parse the JSON output and look for an entry where:
- The provider service name matches `com.amazonaws.<region>.glue`
- The host matches `glue.<region>.amazonaws.com`

**If endpoint already exists, status is "available", AND host matches `glue.<region>.amazonaws.com`**: Skip provisioning (Step 2.0b) and proceed directly to Step 2.0c (verify). You only need one Glue PrivateLink endpoint per region — it serves all catalogs in that region.

**If endpoint already exists but host does NOT match**: The endpoint's hostname has been changed. Do NOT deprovision — deprovisioned endpoints still count toward the 5-endpoint limit for 7 days. Instead, update the hostname:

```sql
SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  'com.amazonaws.<region>.glue',       -- provider service name
  'glue.<region>.amazonaws.com'        -- correct host name
);
```

Then re-run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` to confirm the host is updated and status is "available".

**If endpoint does not exist**: Continue to Step 2.0b to provision it.

#### Step 2.0b: Provision PrivateLink Endpoint

Run as ACCOUNTADMIN to create the PrivateLink endpoint from Snowflake to AWS Glue:

```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.glue',       -- provider service name
  'glue.<region>.amazonaws.com'         -- host name
);
```

Example for `us-west-2`:
```sql
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.us-west-2.glue',
  'glue.us-west-2.amazonaws.com'
);
```

- Snowflake creates an AWS PrivateLink interface endpoint in its own VPC.
- The function returns details including the AWS VPC endpoint ID (e.g., `vpce-0123456789abcdefg`).
- You only need **one** Glue PrivateLink endpoint per region; it serves all Glue catalogs in that region.
- **Limit**: Snowflake accounts can have a maximum of **5 private endpoints**. Deprovisioned endpoints count toward this limit for 7 days. To increase the limit, contact Snowflake Support.

> **Note**: If provisioning fails with `Private endpoint for resource com.amazonaws.<region>.glue already exists`, the endpoint is already provisioned. Run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` to confirm it is healthy and proceed. If the existing endpoint's host doesn't match the expected value, use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME()` to update it (see Step 2.0a). Do NOT deprovision and re-provision — deprovisioned endpoints still count toward the 5-endpoint limit for 7 days.

#### Step 2.0c: Verify PrivateLink Endpoint Status

```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
```

The output is JSON. Look for:
- `"endpoint_state": "CREATED"`
- `"status": "available"` for the Glue endpoint (host `glue.<region>.amazonaws.com`)

**If status is not yet "available"**, wait and re-check. Provisioning can take a few minutes.

---

### Step 2.1: Generate Catalog Integration SQL

> **Updating an existing integration**: `REST_CONFIG` and `REST_AUTHENTICATION` cannot be changed via `ALTER CATALOG INTEGRATION` — you must use `CREATE OR REPLACE`. When you do, Snowflake generates a new `GLUE_AWS_EXTERNAL_ID`, which invalidates your existing AWS trust policy. After recreating, re-run Step 2.4 to retrieve the new external ID and update the trust policy.

Based on connectivity type and access delegation mode, generate appropriate SQL statement.

> **ALTER Limitation**: `REST_CONFIG` cannot be altered on catalog integrations. `REST_AUTHENTICATION` can only be altered for secret rotation (OAuth secret or bearer token) — other parameters like `SIGV4_IAM_ROLE` and `SIGV4_SIGNING_REGION` cannot be changed via ALTER. If you need to change IAM role, region, catalog URI, or access delegation mode, you must recreate the integration with `CREATE OR REPLACE`. Note that recreating generates a new external ID, requiring an AWS trust policy update.

#### For Public Connectivity

```sql
CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<glue_database>'  -- Optional, omit if not provided
  REST_CONFIG = (
    CATALOG_URI = 'https://glue.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_GLUE
    CATALOG_NAME = '<glue_catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = SIGV4
    SIGV4_IAM_ROLE = '<iam_role_arn>'
    SIGV4_SIGNING_REGION = '<region>'
    -- SIGV4_EXTERNAL_ID = '<external_id>'  -- Optional: omit to let Snowflake auto-generate
  )
  ENABLED = TRUE;
```

#### For Private Connectivity (PrivateLink)

> **Prerequisite**: PrivateLink endpoint must be provisioned and "available" (Step 2.0).

```sql
CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<glue_database>'  -- Optional
  REST_CONFIG = (
    CATALOG_URI      = 'https://glue.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_PRIVATE_GLUE
    CATALOG_NAME     = '<glue_catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE               = SIGV4
    SIGV4_IAM_ROLE     = '<iam_role_arn>'
    SIGV4_SIGNING_REGION = '<region>'
    -- SIGV4_EXTERNAL_ID = '<external_id>'  -- Optional: omit to let Snowflake auto-generate
  )
  ENABLED = TRUE;
```

> **Key differences from public connectivity**:
> - `CATALOG_API_TYPE = AWS_PRIVATE_GLUE` (not `AWS_GLUE`) — tells Snowflake to route through PrivateLink
> - `CATALOG_URI` still uses the standard Glue endpoint (not a VPC endpoint DNS) — Snowflake resolves it over PrivateLink internally
> - `ACCESS_DELEGATION_MODE` selects how Snowflake accesses S3 — `VENDED_CREDENTIALS` (catalog vends temporary credentials) or `EXTERNAL_VOLUME_CREDENTIALS` (external volume) — not a connectivity setting, and independent of catalog-server PrivateLink. Both modes can route storage over PrivateLink: external volumes already support it; for vended credentials, see the variant below (sets `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`).

#### For PrivateLink with Vended Credentials (Storage Routed via PrivateLink)

> **Prerequisites**:
> - PrivateLink endpoint for Glue catalog must be provisioned and "available" (Step 2.0).
> - S3 PrivateLink endpoint must be provisioned: `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT('com.amazonaws.<region>.s3', '*.<region>.s3.amazonaws.com')`.
> - Lake Formation configured with two-role IAM pattern (Step 2.5a).
> - For full storage-endpoint provisioning steps, see [shared/vended-credentials-private-storage/SKILL.md](../../shared/vended-credentials-private-storage/SKILL.md).

```sql
CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<glue_database>'  -- Optional
  REST_CONFIG = (
    CATALOG_URI            = 'https://glue.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE       = AWS_PRIVATE_GLUE
    CATALOG_NAME           = '<glue_catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE                 = SIGV4
    SIGV4_IAM_ROLE       = '<catalog_iam_role_arn>'
    SIGV4_SIGNING_REGION = '<region>'
    -- SIGV4_EXTERNAL_ID = '<external_id>'  -- Optional: omit to let Snowflake auto-generate
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

> **⚠️ All three of these must be present together — this is the most common mistake:**
> - `CATALOG_API_TYPE = AWS_PRIVATE_GLUE` (not `AWS_GLUE`) — routes Glue catalog API calls over catalog-server PrivateLink.
> - `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` **inside `REST_CONFIG`** — this is what **enables credential vending**. If you omit it, Snowflake rejects `DEFAULT_STORAGE_CONFIG` with *"DEFAULT_STORAGE_CONFIG is not supported... credential vending is not enabled or not supported for this catalog source."*
> - `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` — routes Snowflake-to-S3 data reads through storage PrivateLink (independent of catalog-server PrivateLink).
>
> Do **not** add `EXTERNAL_VOLUME` anywhere — vended credentials replace it.

**Parameter Explanation**:
- `CATALOG_SOURCE = ICEBERG_REST`: Generic REST catalog (Glue uses Iceberg REST API)
- `TABLE_FORMAT = ICEBERG`: Apache Iceberg table format
- `CATALOG_NAMESPACE`: Optional default namespace (Glue database name)
- `CATALOG_URI`: Glue Iceberg REST endpoint
- `CATALOG_API_TYPE`:
  - `AWS_GLUE`: Public connectivity (over the internet)
  - `AWS_PRIVATE_GLUE`: Private connectivity via AWS PrivateLink
  - `AWS_S3TABLES`: Direct access to the S3 Tables Iceberg REST endpoint (public); requires `CATALOG_NAME` = bucket ARN and `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`
  - `AWS_PRIVATE_S3TABLES`: Direct access to S3 Tables via PrivateLink; requires `CATALOG_NAME` = bucket ARN, `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`, and `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`
- `ACCESS_DELEGATION_MODE`:
  - `VENDED_CREDENTIALS`: Glue/S3 Tables generates temporary credentials (no external volume needed; combine with `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` to route S3 reads through PrivateLink; required for `AWS_S3TABLES` / `AWS_PRIVATE_S3TABLES`)
  - `EXTERNAL_VOLUME_CREDENTIALS`: Use external volume for data access
- `TYPE = SIGV4`: AWS Signature Version 4 authentication
- `SIGV4_IAM_ROLE`: ARN of IAM role Snowflake should assume. For `VENDED_CREDENTIALS`, use the **catalog role** (the one with Glue API permissions). A separate data access role for S3 is configured in Step 2.5a.
- `SIGV4_SIGNING_REGION`: AWS region for signing (must match Glue region)
- `SIGV4_EXTERNAL_ID` (optional): Customer-provided external ID for the trust relationship. If omitted, Snowflake auto-generates a unique external ID. Providing your own lets you reuse the same IAM role across multiple catalog integrations without updating the trust policy, which is useful in testing scenarios where integrations are frequently recreated.

> **⚠️ IMPORTANT: CATALOG_NAME for Glue IRC**
> 
> **CATALOG_NAME is the Glue catalog name**, which varies by catalog type:
> - **AWS Glue Data Catalog (default)**: The 12-digit AWS Account ID (e.g., `'123456789012'`)
> - **Amazon S3 Tables through Glue**: Format is `'<aws_account_id>:s3tablescatalog/<s3_table_bucket>'`
> - **Federated Glue catalog**: The custom catalog name provided when the catalog was created
> 
> For **S3 Tables direct path** (`AWS_S3TABLES` / `AWS_PRIVATE_S3TABLES`), `CATALOG_NAME` is the S3 Tables **bucket ARN** (e.g., `'arn:aws:s3tables:us-west-2:123456789012:bucket/my_table_bucket'`).
> 
> Confirm the exact catalog name in the [AWS Lake Formation console](https://console.aws.amazon.com/lakeformation/). Each catalog integration maps to one Glue catalog.
> 
> See: [Catalog-vended credentials documentation](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials)

#### For S3 Tables Direct Access (Public)

Use `CATALOG_API_TYPE = AWS_S3TABLES` to connect directly to the S3 Tables Iceberg REST endpoint without going through Glue. `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` is required.

```sql
CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://s3tables.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_S3TABLES
    CATALOG_NAME = 'arn:aws:s3tables:<region>:<account_id>:bucket/<table_bucket_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = SIGV4
    SIGV4_IAM_ROLE = '<iam_role_arn>'
    SIGV4_SIGNING_REGION = '<region>'
    -- SIGV4_EXTERNAL_ID = '<external_id>'  -- Optional
  )
  ENABLED = TRUE;
```

#### For S3 Tables Direct Access (PrivateLink)

`AWS_PRIVATE_S3TABLES` supports vended credentials (unlike Glue PrivateLink). Two PrivateLink endpoints are required. The `DEFAULT_STORAGE_CONFIG` parameter must be set.

```sql
-- Provision s3tables service endpoint (Step 2.0 should already cover this)
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.s3tables',
  's3tables.<region>.amazonaws.com'
);

-- Provision S3 storage endpoint (separate from the s3tables endpoint)
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.s3',
  '*.<region>.s3.amazonaws.com'
);

-- Create catalog integration
CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://s3tables.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_PRIVATE_S3TABLES
    CATALOG_NAME = 'arn:aws:s3tables:<region>:<account_id>:bucket/<table_bucket_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = SIGV4
    SIGV4_IAM_ROLE = '<iam_role_arn>'
    SIGV4_SIGNING_REGION = '<region>'
    -- SIGV4_EXTERNAL_ID = '<external_id>'  -- Optional
  )
  DEFAULT_STORAGE_CONFIG = (
    USE_PRIVATELINK_ENDPOINT = TRUE
  )
  ENABLED = TRUE;
```

> **S3 Tables PrivateLink notes**:
> - Verify both endpoints (`s3tables` and `s3`) show `"status": "available"` before creating the integration.
> - Configure an S3 Tables bucket policy that uses `aws:CalledVia = s3tables.amazonaws.com` and allowlists both VPC endpoint IDs. See the [S3 Tables private connectivity guide](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-s3tables) for the full bucket policy template.
> - **Limitation**: CTAS is not supported for the S3 Tables Iceberg REST endpoint.

### Step 2.2: Review & Approval

**Present generated SQL to user**:

```
Generated Catalog Integration SQL:
═══════════════════════════════════════════════════════════
[The complete SQL with actual values filled in]
═══════════════════════════════════════════════════════════

This will create a catalog integration named '<integration_name>' 
connecting to AWS Glue Data Catalog in account '<aws_account_id>' 
and region '<region>' using SigV4 authentication.

IMPORTANT: After creation, you'll need to update the AWS IAM role 
trust policy with Snowflake-generated credentials.
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Please review the SQL above. Ready to execute and create the catalog integration?"

**Wait for explicit approval**:
- "Yes", "Approved", "Looks good", "Proceed" → Continue to Step 2.3
- "No" or "Wait" → Ask: "What changes would you like to make?"

### Step 2.3: Execute Creation

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

### Step 2.4: Retrieve Snowflake IAM Credentials

Now retrieve the Snowflake-generated IAM user ARN and the external ID needed for AWS trust policy.

**Execute**:
```sql
DESCRIBE CATALOG INTEGRATION <integration_name>;
```

**Extract these values from output**:

| Property | Description | Example |
|----------|-------------|---------|
| `GLUE_AWS_IAM_USER_ARN` | Snowflake IAM user ARN | `arn:aws:iam::123456789001:user/abc1-b-self1234` |
| `GLUE_AWS_EXTERNAL_ID` | External ID for trust relationship | `ABC12345_SFCRole=1_abcdefgh` |

> **Note**: If you specified `SIGV4_EXTERNAL_ID` when creating the integration, `GLUE_AWS_EXTERNAL_ID` will reflect your custom value. If you did not specify one, Snowflake auto-generated a unique external ID.

**Present to user**:
```
Snowflake IAM Credentials:
─────────────────────────────────────────
IAM User ARN: <GLUE_AWS_IAM_USER_ARN>
External ID:  <GLUE_AWS_EXTERNAL_ID>
─────────────────────────────────────────

These values are needed in the next step to configure the 
AWS IAM role trust policy.
```

**INFO**: Snowflake provisions a single IAM user for your entire Snowflake account. All Glue catalog integrations use the same IAM user but have unique external IDs (unless you provide the same custom `SIGV4_EXTERNAL_ID` across integrations).

### Step 2.5: Configure AWS Trust Policy

**Present trust policy template to user**:

```
AWS IAM Role Trust Policy Configuration:
═══════════════════════════════════════════════════════════

1. Go to AWS IAM Console → Roles → <your_iam_role>
2. Click "Trust relationships" tab
3. Click "Edit trust policy"
4. Add the following to the trust policy:

{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "<GLUE_AWS_IAM_USER_ARN>"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<GLUE_AWS_EXTERNAL_ID>"
        }
      }
    }
  ]
}

Replace:
- <GLUE_AWS_IAM_USER_ARN> with: <actual_value>
- <GLUE_AWS_EXTERNAL_ID> with: <actual_value>

5. Click "Update policy"

═══════════════════════════════════════════════════════════
```

> **Sharing one IAM role with an external volume**: If you'll use the same IAM role for both this catalog integration AND an external volume, each generates its own `EXTERNAL_ID`. The trust policy `StringEquals` condition must include **all external IDs as an array**, otherwise the second integration's `sts:AssumeRole` call will fail. After creating the external volume, run `DESCRIBE EXTERNAL VOLUME <name>` to get `STORAGE_AWS_EXTERNAL_ID`, then update the trust policy:
>
> ```json
> "Condition": {
>   "StringEquals": {
>     "sts:ExternalId": ["<GLUE_AWS_EXTERNAL_ID>", "<STORAGE_AWS_EXTERNAL_ID>"]
>   }
> }
> ```
>
> See `references/KNOWN_GOTCHAS.md` → #11 for the full pattern.

> **External volume validation requires S3 write access**: When you run `CREATE DATABASE ... LINKED_CATALOG` (CLD creation), Snowflake validates the external volume by writing and deleting a test object. Even for read-only Iceberg use cases, the IAM role attached to the external volume must have `s3:PutObject` and `s3:DeleteObject` on the target S3 path — not just `s3:GetObject`.

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Have you updated the AWS IAM role trust policy?"

**Wait for confirmation**: "Yes", "Done", "Updated" → Continue to Step 2.5a

---

### Step 2.5a: Vended Credentials — Two-Role IAM & Lake Formation Setup

> **Only applies when `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`**. Skip this step entirely for `EXTERNAL_VOLUME_CREDENTIALS` — go directly to Step 2.6.

Vended credentials use **two separate IAM roles** with distinct responsibilities:

| Role | Variable | Purpose |
|------|----------|---------|
| Catalog role | `<CATALOG_IAM_ROLE_ARN>` | Used in `SIGV4_IAM_ROLE`. Snowflake assumes this role to call Glue IRC APIs and request LF-vended credentials. |
| Data access role | `<DATA_ACCESS_ROLE_ARN>` | Registered with Lake Formation. LF assumes this role to access S3 and generate temporary credentials for Snowflake. |

Ask the user: "Do you have an existing data access role for Lake Formation, or should we create a new one?"

---

#### A. Add `lakeformation:GetDataAccess` to the catalog role

Add this statement to the **identity policy** of `<CATALOG_IAM_ROLE_ARN>` (the role in your catalog integration):

```json
{
  "Sid": "LakeFormationGetDataAccess",
  "Effect": "Allow",
  "Action": "lakeformation:GetDataAccess",
  "Resource": "*"
}
```

> **⚠️ `Resource: "*"` is required** — scoping to Glue ARNs does NOT work. `lakeformation:GetDataAccess` is an account-level permission. Narrower scoping causes CLD initialization to fail with `lakeformation:GetDataAccess denied`.

---

#### B. Configure the data access role

Create or update `<DATA_ACCESS_ROLE_ARN>` with:

**Identity policy** (S3 read access):

```json
{
  "Sid": "S3DataAccess",
  "Effect": "Allow",
  "Action": [
    "s3:GetObject",
    "s3:ListBucket",
    "s3:GetBucketLocation"
  ],
  "Resource": [
    "arn:aws:s3:::<BUCKET_NAME>",
    "arn:aws:s3:::<BUCKET_NAME>/*"
  ]
}
```

**Trust policy** (allow Lake Formation to assume this role):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lakeformation.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

> **⚠️ Without the LF service principal in the trust policy**, CLD initialization fails with: `Unable to assume role. Please verify Lake Formation has access to role.`

---

#### C. Register the data access role with Lake Formation

```bash
aws lakeformation register-resource \
  --resource-arn "arn:aws:s3:::<BUCKET_NAME>" \
  --role-arn "<DATA_ACCESS_ROLE_ARN>" \
  --profile <AWS_PROFILE>
```

> If the S3 path is already registered, you'll see `AlreadyExistsException` — safe to ignore. If you get `Must manually delete service-linked role to deregister last S3 location`, see `references/KNOWN_GOTCHAS.md` for the LF deregistration procedure.

---

#### D. Grant Lake Formation permissions to the catalog role

LF permissions are granted to `<CATALOG_IAM_ROLE_ARN>` — the role Snowflake uses when calling `lakeformation:GetDataAccess`:

```bash
# DESCRIBE on the Glue database
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="<CATALOG_IAM_ROLE_ARN>" \
  --permissions "DESCRIBE" \
  --resource '{"Database":{"Name":"<GLUE_DATABASE>"}}' \
  --profile <AWS_PROFILE>

# SELECT + DESCRIBE on all tables in the database
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="<CATALOG_IAM_ROLE_ARN>" \
  --permissions "SELECT" "DESCRIBE" \
  --resource '{"Table":{"DatabaseName":"<GLUE_DATABASE>","TableWildcard":{}}}' \
  --profile <AWS_PROFILE>

# DATA_LOCATION_ACCESS on the S3 path
aws lakeformation grant-permissions \
  --principal DataLakePrincipalIdentifier="<CATALOG_IAM_ROLE_ARN>" \
  --permissions "DATA_LOCATION_ACCESS" \
  --resource '{"DataLocation":{"ResourceArn":"arn:aws:s3:::<BUCKET_NAME>"}}' \
  --profile <AWS_PROFILE>
```

**⚠️ MANDATORY STOPPING POINT**: Ask user: "Have you applied all Lake Formation configuration (steps A–D)?"

**Wait for confirmation** → Continue to Step 2.6

### Step 2.6: Verify Trust Relationship

**Explain**:
```
The trust relationship is now configured. In the next step 
(Verification), we'll test the connection to ensure:
- Trust policy is correct
- IAM role has Glue permissions
- Connection is working
```

**Output**: Catalog integration created with trust relationship configured

**Next**: Return to main skill → Proceed to Step 3 (Verification)

## Error Handling

**Common errors during creation**:
- **Invalid IAM role ARN**: Check format and role exists
- **Invalid region**: Verify region name spelling
- **Permission denied**: Check Snowflake privileges for creating integrations

**Common errors during trust setup**:
- **Copy-paste errors**: Verify no extra spaces or line breaks in trust policy
- **Wrong role updated**: Ensure updating the same role specified in SIGV4_IAM_ROLE
- **JSON syntax errors**: Validate trust policy JSON format

**Common errors during vended credentials LF setup (Step 2.5a)**:
- **`lakeformation:GetDataAccess denied`**: `Resource` in `CATALOG_IAM_ROLE_ARN` identity policy is scoped too narrowly — must be `"*"`
- **`Unable to assume role. Please verify Lake Formation has access to role`**: `lakeformation.amazonaws.com` service principal missing from `DATA_ACCESS_ROLE_ARN` trust policy (Step 2.5a-B)
- **CLD stuck in INITIALIZING / `s3:GetObject forbidden`**: S3 read permissions missing from `DATA_ACCESS_ROLE_ARN` identity policy (Step 2.5a-B)
- **`AlreadyExistsException` on register-resource**: Safe to ignore — S3 resource already registered with LF
- **LF grants failing with `principal not found`**: Ensure `CATALOG_IAM_ROLE_ARN` is the exact ARN of the catalog role, not the data access role

**For all errors**: Present error message clearly and load troubleshooting guide if needed.

## Output

Successfully created catalog integration in Snowflake with AWS trust relationship configured, ready for verification.

## Next Steps

After successful creation and trust configuration:
- Return to main skill
- Proceed to Step 3: Verification
- Load `verify/SKILL.md`
