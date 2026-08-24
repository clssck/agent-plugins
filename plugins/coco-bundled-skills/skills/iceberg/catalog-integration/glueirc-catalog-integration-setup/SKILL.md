---
name: glueirc-catalog-integration-setup
description: "Setup and verify catalog integration for AWS Glue Iceberg REST Catalog (public and PrivateLink) and direct Amazon S3 Tables Iceberg REST endpoint. Triggers: create glue catalog integration, connect snowflake to glue, setup glue irc, configure glue iceberg rest, glue data catalog integration, AWS glue iceberg, sigv4 authentication glue, glue lake formation snowflake, query glue tables from snowflake, iceberg rest api glue, troubleshoot glue integration, verify glue catalog integration, glue vended credentials, glue external volume credentials, fix glue connection, debug glue iceberg, glue privatelink, glue private link, private connectivity glue, aws private glue, privatelink glue iceberg, aws glue setup, glue crawler, athena CTAS, parquet to iceberg, S3 to iceberg, glue database, athena iceberg conversion, aws iceberg setup, vended credentials privatelink, USE_PRIVATELINK_ENDPOINT, DEFAULT_STORAGE_CONFIG, private storage with vended credentials, glue vended credentials private storage, glue irc vended creds privatelink, s3 tables catalog integration, aws s3tables iceberg, direct s3 tables connection, s3tables iceberg rest, AWS_S3TABLES, AWS_PRIVATE_S3TABLES."
---

# AWS Glue / S3 Tables Iceberg REST Catalog Integration

Setup, verify, or troubleshoot a Snowflake catalog integration for AWS Glue Data Catalog, or directly for the Amazon S3 Tables Iceberg REST endpoint.

## Intent Routing (FIRST)

**Ask the user**:
```
What would you like to do?

A: Set up AWS Glue infrastructure (S3, crawler, Iceberg conversion)
   → AWS auth, S3 discovery, Glue DB + crawler, Athena CTAS to Iceberg

B: Create a new catalog integration (Glue IRC or S3 Tables direct)
   → Glue IRC: connect via AWS Glue Data Catalog (public or PrivateLink)
   → S3 Tables direct: connect via AWS_S3TABLES / AWS_PRIVATE_S3TABLES (bypasses Glue)

C: Verify an existing catalog integration
   → Test connection and list namespaces/tables

D: Troubleshoot a catalog integration
   → Diagnose and fix connection issues
```

**Route based on response**:
- **A (AWS Glue Setup)** → **Load** `aws-setup/SKILL.md` then follow [AWS Glue Setup Workflow](#aws-glue-setup-workflow)
- **B (Create)** → **Load** `setup/SKILL.md` then follow [Create Workflow](#create-workflow)
- **C (Verify)** → **Load** `verify/SKILL.md` then follow [Verify Workflow](#verify-workflow)
- **D (Troubleshoot)** → **Load** `references/troubleshooting.md` then follow [Troubleshoot Workflow](#troubleshoot-workflow)

---

## Create Workflow

> **⚠️ REQUIRED**: Load `setup/SKILL.md` FIRST before proceeding with this workflow.

Create a new catalog integration to connect Snowflake to AWS Glue Data Catalog.

### Step 1: Prerequisites

Follow `setup/SKILL.md` to collect:

Collect one-by-one:
1. Confirm AWS Glue setup exists
2. Access delegation mode (vended credentials vs external volume)
3. Lake Formation setup (if vended credentials)
4. AWS Account ID
5. AWS Region
6. Glue Database (optional)
6a. Glue Catalog Name
7. IAM Role ARN
8. Connectivity type (Public or PrivateLink)
9. Integration name
9a. Custom external ID (optional — Snowflake auto-generates if not provided)

**⚠️ STOP**: Confirm prerequisites before proceeding

### Step 2: Create Integration

**Load** `create/SKILL.md` and follow its workflow:

1. **If PrivateLink**: Provision PrivateLink endpoint, verify status
2. Generate CREATE CATALOG INTEGRATION SQL
3. **⚠️ STOP**: Review SQL with user
4. Execute creation
5. Retrieve Snowflake IAM user ARN and external ID
6. **⚠️ STOP**: Guide user to update AWS trust policy
7. Confirm trust policy updated

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

-- List namespaces (Glue databases)
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');

-- List tables in a namespace
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<database>');
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
- Access denied errors

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
1. Trust relationship not configured
2. External ID mismatch
3. IAM permissions missing
4. Lake Formation access denied
5. Database/table not found
6. Region mismatch
7. PrivateLink endpoint not available
8. PrivateLink endpoint limit exceeded (max 5 per account)
9. PrivateLink endpoint already exists (safe to proceed)
10. Existing workloads fail after provisioning PrivateLink endpoint (AWS policy update needed)
11. Cross-region PrivateLink not supported (AWS limitation)

**⚠️ STOP**: Present diagnosis and wait for user direction before applying fixes.

---

## AWS Glue Setup Workflow

> **⚠️ REQUIRED**: Load `aws-setup/SKILL.md` FIRST before proceeding with this workflow.

Set up AWS Glue infrastructure as a prerequisite for the Snowflake catalog integration.

This covers:
1. AWS authentication verification
2. S3 data discovery
3. Glue database and crawler creation
4. Schema discovery and validation
5. Parquet-to-Iceberg conversion via Athena CTAS

After AWS setup completes, continue to [Create Workflow](#create-workflow) to set up the Snowflake-side catalog integration.

---

## Scope

This skill covers **end-to-end Glue and S3 Tables Iceberg setup**:

**Snowflake-side** (setup/, verify/, create/, references/):
- ✅ Creating catalog integrations for Glue IRC (public and PrivateLink)
- ✅ Creating catalog integrations for S3 Tables direct path (`AWS_S3TABLES` / `AWS_PRIVATE_S3TABLES`)
- ✅ PrivateLink endpoint provisioning and verification
- ✅ IAM role and policy configuration
- ✅ AWS trust relationship establishment
- ✅ Verification
- ✅ Troubleshooting

**AWS-side** (aws-setup/):
- ✅ AWS CLI authentication verification
- ✅ S3 data discovery and inventory
- ✅ Glue database and crawler setup
- ✅ Schema discovery and type validation
- ✅ Parquet-to-Iceberg conversion via Athena CTAS

**Out of scope** (separate resources):
- ❌ Lake Formation setup → [Snowflake + AWS Glue Guide](https://www.snowflake.com/en/developers/guides/data-lake-using-apache-iceberg-with-snowflake-and-aws-glue/)
- ❌ External volume creation
- ❌ Creating tables or catalog-linked databases (use shared `next-steps` skill)

---

## Quick Reference

**Catalog Integration SQL (Public)**:
```sql
CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://glue.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_GLUE
    CATALOG_NAME = '<glue_catalog_name>'  -- See CATALOG_NAME note below
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

**Catalog Integration SQL (PrivateLink)**:
```sql
-- Step 1: Check if endpoint already exists (skip provisioning if available)
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: query the Account Usage view
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;

-- Step 2: Provision PrivateLink endpoint (one-time per region, skip if already exists)
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.glue',
  'glue.<region>.amazonaws.com'
);

-- Step 3: Verify endpoint is available
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();

-- Step 4: Create catalog integration
CREATE OR REPLACE CATALOG INTEGRATION <name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI      = 'https://glue.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_PRIVATE_GLUE
    CATALOG_NAME     = '<glue_catalog_name>'  -- See CATALOG_NAME note below
  )
  REST_AUTHENTICATION = (
    TYPE               = SIGV4
    SIGV4_IAM_ROLE     = '<iam_role_arn>'
    SIGV4_SIGNING_REGION = '<region>'
    -- SIGV4_EXTERNAL_ID = '<external_id>'  -- Optional: omit to let Snowflake auto-generate
  )
  ENABLED = TRUE;
```

> **⚠️ PrivateLink notes (AWS Glue)**:
> - Requires **Business Critical Edition (or higher)**. To inquire about upgrading, please contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge).
> - `CATALOG_API_TYPE = AWS_PRIVATE_GLUE` (not `AWS_GLUE`)
> - `ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>` — selects how Snowflake accesses S3 (catalog-vended credentials vs an external volume), not a connectivity setting. Both modes can use outbound PrivateLink to S3: external volumes already support it; for vended credentials, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. Independent of catalog-server PrivateLink (`CATALOG_API_TYPE`).
> - Requires same cloud provider and region as Snowflake
> - **Cross-region PrivateLink is NOT supported for AWS Glue.** The Snowflake account and the Glue Data Catalog must be in the same AWS region. This is an AWS-side limitation — AWS does not support cross-region PrivateLink provisioning for the Glue service. See: [AWS cross-region PrivateLink support](https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-cross-region-privatelink-support.html)
>
> **Exception for Amazon S3 Tables direct path** (`AWS_PRIVATE_S3TABLES`): vended credentials ARE supported with PrivateLink. Two PrivateLink endpoints are required — one for `s3tables` and one for `s3` storage. See the S3 Tables section below.

> **⚠️ CATALOG_NAME**: This is the **Glue catalog name**, which varies by catalog type:
> - **AWS Glue Data Catalog (default)**: The 12-digit AWS Account ID (e.g., `'123456789012'`)
> - **Amazon S3 Tables through Glue**: Format is `'<aws_account_id>:s3tablescatalog/<s3_table_bucket>'`
> - **Federated Glue catalog**: The custom catalog name provided when the catalog was created
>
> Confirm the exact catalog name in the [AWS Lake Formation console](https://console.aws.amazon.com/lakeformation/). Each catalog integration maps to one Glue catalog.
>
> See: [Catalog-vended credentials documentation](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials)

**Diagnostic Commands**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<name>';
DESC CATALOG INTEGRATION <name>;
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<name>');
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<name>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<name>', '<database>');
```

---

## Vended credentials with private connectivity to storage

Any Glue catalog integration with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` can route Snowflake-to-storage (S3) traffic through AWS PrivateLink by setting `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. This is independent of catalog-server PrivateLink (`CATALOG_API_TYPE = AWS_PRIVATE_GLUE`): storage PrivateLink can be enabled with public or private catalog connectivity.

### Glue-specific prerequisites

1. **Lake Formation access control**: Ensure the IAM role used as `SIGV4_IAM_ROLE` has Lake Formation permissions on the Glue database, tables, and the underlying S3 bucket. See: [Configure Lake Formation access control](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials).
2. **Same-region requirement**: The S3 bucket(s) holding Iceberg table data must be in the same AWS region as the Snowflake account. AWS PrivateLink for S3 is regional; cross-region storage PrivateLink is not supported.

For the cross-vendor steps (block public storage, provision Snowflake-side storage endpoint, allowlist, verify), see [shared/vended-credentials-private-storage/SKILL.md](../shared/vended-credentials-private-storage/SKILL.md).

### Example: AWS Glue Data Catalog with storage PrivateLink

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI      = 'https://glue.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_PRIVATE_GLUE
    CATALOG_NAME     = '<aws_account_id>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE                 = SIGV4
    SIGV4_IAM_ROLE       = 'arn:aws:iam::<aws_account_id>:role/<role_name>'
    SIGV4_SIGNING_REGION = '<region>'
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

### Example: S3 Tables through Glue (Lake Formation)

```sql
USE ROLE ACCOUNTADMIN;

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI      = 'https://glue.<region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_PRIVATE_GLUE
    CATALOG_NAME     = '<aws_account_id>:s3tablescatalog/<bucket>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE                 = SIGV4
    SIGV4_IAM_ROLE       = 'arn:aws:iam::<aws_account_id>:role/<role_name>'
    SIGV4_SIGNING_REGION = '<region>'
  )
  DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)
  ENABLED = TRUE;
```

> **Note**: The S3 Tables bucket policy / Lake Formation configuration differs from standard S3 buckets and has not been fully validated for the storage-PrivateLink path. Confirm S3 Tables vended-credential access over PrivateLink in a test account before relying on it in production.

### Enable on an existing integration

> **⚠️ MANDATORY CHECKPOINT**: This `ALTER` modifies a live catalog integration. Present it to the user and wait for explicit approval before executing.

```sql
ALTER CATALOG INTEGRATION <name> SET DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE);
```

### Verification

- `DESC CATALOG INTEGRATION <name>` should show `default_storage_config` with `USE_PRIVATELINK_ENDPOINT=true`.
- `SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` should confirm the S3 storage endpoint is available.
- Probe: `SELECT * FROM <iceberg_table_via_integration> LIMIT 1;`

---

**Catalog Integration SQL (S3 Tables — Direct / Public)**:

Connect directly to the S3 Tables Iceberg REST endpoint without going through Glue. `CATALOG_NAME` is the S3 Tables bucket ARN. `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` is required.

```sql
CREATE OR REPLACE CATALOG INTEGRATION <name>
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
  )
  ENABLED = TRUE;
```

**Catalog Integration SQL (S3 Tables — Private / PrivateLink)**:

`AWS_PRIVATE_S3TABLES` requires vended credentials and two PrivateLink endpoints: one for `s3tables` and one for `s3` storage.

```sql
-- Step 1: Provision s3tables service endpoint
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.s3tables',
  's3tables.<region>.amazonaws.com'
);

-- Step 2: Provision S3 storage endpoint
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.s3',
  '*.<region>.s3.amazonaws.com'
);

-- Step 3: Create catalog integration
CREATE OR REPLACE CATALOG INTEGRATION <name>
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
  )
  DEFAULT_STORAGE_CONFIG = (
    USE_PRIVATELINK_ENDPOINT = TRUE
  )
  ENABLED = TRUE;
```

> **S3 Tables bucket policy** (required for private connectivity): Configure the bucket to deny access unless the request originates from the allowlisted VPC endpoints OR is mediated by the S3 Tables service via `aws:CalledVia = s3tables.amazonaws.com`. For the full bucket policy template, see the [S3 Tables private connectivity guide](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-s3tables).
>
> **S3 Tables limitations**: CTAS (`CREATE TABLE ... AS SELECT`) is not supported for the S3 Tables Iceberg REST endpoint.

---

## Success Criteria

- ✅ Integration shows `ENABLED=TRUE`
- ✅ AWS trust policy configured with Snowflake IAM user and external ID
- ✅ `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns success
- ✅ Namespaces discoverable
- ✅ Tables visible

---

## Documentation

- [Configure Catalog Integration for AWS Glue IRC](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-glue)
- [Configure Catalog Integration for Amazon S3 Tables](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-s3tables)
- [Configure Catalog Integration with Outbound Private Connectivity (PrivateLink)](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-private)
- [Catalog-vended credentials](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials)
- [Snowflake Iceberg Tables](https://docs.snowflake.com/user-guide/tables-iceberg)
- [AWS Glue Data Catalog](https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html)
- [Lake Formation + Glue Setup Guide](https://www.snowflake.com/en/developers/guides/data-lake-using-apache-iceberg-with-snowflake-and-aws-glue/) (for vended credentials)
