---
name: glueirc-setup-prerequisites
description: "Gather prerequisites for AWS Glue IRC catalog integration setup"
parent_skill: glueirc-catalog-integration-setup
---

# Prerequisites Gathering

Collect all required information to create your AWS Glue Iceberg REST catalog integration.

## When to Load

From main skill Step 1: Prerequisites gathering phase

## Prerequisites

User should have:
- AWS account with Glue Data Catalog configured
- Iceberg tables registered in Glue Data Catalog
- Snowflake **ACCOUNTADMIN** role — required for `CREATE CATALOG INTEGRATION` and `CREATE EXTERNAL VOLUME`. If you don't have ACCOUNTADMIN, these explicit grants are needed: `GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE <your_role>` and `GRANT CREATE EXTERNAL VOLUME ON ACCOUNT TO ROLE <your_role>`. Verify before starting:
  ```sql
  SELECT CURRENT_ROLE();  -- confirm ACCOUNTADMIN, or verify grants are in place
  ```
  > Missing this privilege causes a permissions error mid-workflow, not at the start. Check it now.
- AWS IAM permissions to create/modify roles and policies

## Workflow

Collect prerequisites **one at a time** in the following order. Wait for user response before proceeding to next question.

---

### Step 1.1: Confirm AWS Glue Setup (FIRST)

**Ask**:
```
Before we begin, let's confirm your AWS setup:

Do you have an AWS account with:
✓ Glue Data Catalog configured
✓ Iceberg tables registered in Glue

(If you need to set up Glue Data Catalog first, see: 
https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html)
```

**If Yes** → Continue to Step 1.2

**If No** → 
```
This skill helps connect Snowflake to an EXISTING Glue Data Catalog 
with Iceberg tables. 

Please set up your Glue Data Catalog and register Iceberg tables first, 
then return to create the catalog integration.

Resources:
- AWS Glue Data Catalog: https://docs.aws.amazon.com/glue/latest/dg/catalog-and-crawler.html
- Creating Iceberg tables in Glue: https://docs.aws.amazon.com/glue/latest/dg/aws-glue-programming-etl-format-iceberg.html
```

**STOP** - Cannot proceed without existing Glue setup

---

### Step 1.2: Access Delegation Mode

**Ask**:
```
How should Snowflake access the Iceberg data files in S3?

A: Vended Credentials ⭐ Recommended
   ✓ Glue/Lake Formation generates temporary S3 credentials
   ✓ No external volume needed
   ✓ Single access control plane across all query engines (Snowflake, EMR, Athena, etc.)
   ✓ Differentiating feature — other platforms (e.g. Databricks foreign tables) do not support catalog-vended credentials
   ⚠ Requires Lake Formation to be enabled and configured
   ℹ Works with catalog-server PrivateLink (AWS_PRIVATE_GLUE) and can also route storage over PrivateLink — see Storage Connectivity (Step 1.8a).

B: External Volume Credentials
   ✓ Works without Lake Formation
   ✓ Use when you don't need Glue/LF as the storage access-control plane
   ✓ Fallback if Lake Formation setup is not feasible
   ✗ Requires separate external volume setup
   ✗ S3 access managed outside Glue/LF — split access control
```

> **Guidance**: Choose **A (Vended Credentials)** unless Lake Formation setup is not feasible in your account. Vended credentials make Glue/LF the single source of access control for your Iceberg data — no need to separately provision S3 access per query engine. If Lake Formation is not yet enabled, see Step 1.3 for setup guidance.

> **Catalog traffic vs storage traffic are independent.** `CATALOG_API_TYPE = AWS_PRIVATE_GLUE` (Step 1.8) controls how Snowflake reaches the **Glue catalog API**. `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` is fully compatible with it. By default, storage (S3) access using vended credentials goes over the public internet; to route storage over PrivateLink as well, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` — see Storage Connectivity (Step 1.8a). You do NOT need to downgrade to `EXTERNAL_VOLUME_CREDENTIALS`.
>
> **S3 Tables direct path exception** (`AWS_S3TABLES` / `AWS_PRIVATE_S3TABLES`): connects to the S3 Tables Iceberg REST endpoint directly (not through Glue). This path always requires `VENDED_CREDENTIALS` and uses a different catalog URI and two PrivateLink endpoints.

**Record user choice** → Continue based on selection

---

### Step 1.3: Lake Formation Setup (VENDED_CREDENTIALS only)

> **Note**: Lake Formation configuration for credential vending is handled in **Step 2.5a** of the create workflow — this skill will guide you through it when you reach that step. You do not need LF fully configured before completing prerequisites here.

**If user chose Vended Credentials (A)**:

**Ask**:
```
Vended credentials require AWS Lake Formation to be enabled and configured.

Is Lake Formation already enabled in your AWS account for this Glue Data Catalog?

A: Yes, Lake Formation is enabled and configured
B: No / Not sure — I'll configure it during setup
C: Switch to External Volume Credentials instead
```

**If Yes (A)** → Continue to Step 1.4

**If No/Not sure (B)** → Reassure and continue:

```
No problem — Lake Formation setup is covered in Step 2.5a of the 
create workflow. We'll walk through the two-role IAM pattern and 
LF registration when we get there.

Continue here to finish collecting prerequisites.
```

→ Continue to Step 1.4

**If Switch (C)** → Record `EXTERNAL_VOLUME_CREDENTIALS` and continue to Step 1.4

---

### Step 1.4: AWS Account ID

**Ask**:
```
What is your AWS Account ID?

(12-digit number, find it at: AWS Console → Account menu → Account ID)
Example: 123456789012
```

**Record**: AWS Account ID

---

### Step 1.5: AWS Region

**Ask**:
```
What AWS region is your Glue Data Catalog in?

(Find at: AWS Console → top-right dropdown)
Example: us-east-1, us-west-2, eu-west-1
```

**Record**: AWS Region

**Derive**: Catalog URI = `https://glue.<region>.amazonaws.com/iceberg`

---

### Step 1.6: Glue Database (Optional)

**Ask**:
```
Would you like to set a default Glue database (namespace)?

- If yes: Provide the database name (case-sensitive)
- If no: Leave blank (you can specify per-table later)

(Find databases at: AWS Console → Glue → Databases)
```

**Record**: Glue database name (or blank)

---

### Step 1.6a: Glue Catalog Name

**Ask**:
```
What is your Glue catalog name?

This depends on your catalog type:
- AWS Glue Data Catalog (default): Your 12-digit AWS Account ID
  → Example: 123456789012
- Amazon S3 Tables through Glue: <account_id>:s3tablescatalog/<s3_table_bucket>
  → Example: 123456789012:s3tablescatalog/my-table-bucket
- Federated Glue catalog: The custom catalog name

(Check in: AWS Console → Lake Formation → Catalogs)

If using the default Glue Data Catalog, this is your AWS Account ID 
(provided in Step 1.4): <aws_account_id>
```

**If user confirms default catalog**: Record `CATALOG_NAME` = AWS Account ID from Step 1.4

**If user provides a different value**: Record the provided value

**Record**: Glue catalog name

---

### Step 1.7: IAM Role

**Ask**:
```
Do you have an existing IAM role for Snowflake to use, or should we help create one?

A: I have an existing IAM role
   → Provide the role ARN (format: arn:aws:iam::<account_id>:role/<role_name>)

B: I need to create a new IAM role
   → We'll guide you through creation
```

**If existing role (A)**:
- **Record**: IAM Role ARN
- **Ask**: "Does this role already have Glue permissions attached?"
  - If yes → Continue to Step 1.8
  - If no → Provide policy template (see below)

**If new role (B)** → Provide IAM role creation guidance:

```
IAM Role Creation Guide
═══════════════════════════════════════════════════════════

1. Go to AWS Console → IAM → Roles → Create role

2. Select trusted entity:
   - Type: AWS account
   - Account: Another AWS account
   - Account ID: (we'll provide Snowflake's after integration creation)
   - ✓ Check "Require external ID"
   - External ID: (we'll provide after integration creation)

   NOTE: For now, use your own account ID as placeholder.
   We'll update the trust policy after creating the integration.

3. Role name: snowflake-glue-access (or your preferred name)

4. Create the role, then note the ARN

═══════════════════════════════════════════════════════════
```

**Record**: IAM Role ARN after user creates it

**Required IAM Permissions**:

| Mode | Required Permissions |
|------|---------------------|
| **Vended Credentials** | `glue:GetCatalog`, `glue:GetDatabase`, `glue:GetDatabases`, `glue:GetTable`, `glue:GetTables`, `lakeformation:GetDataAccess` |
| **External Volume** | `glue:GetCatalog`, `glue:GetDatabase`, `glue:GetDatabases`, `glue:GetTable`, `glue:GetTables` |

**Resources**: `arn:aws:glue:*:<account_id>:catalog`, `arn:aws:glue:*:<account_id>:database/*`, `arn:aws:glue:*:<account_id>:table/*/*`

**Ask**: "Have you attached the IAM policy with these permissions to your role?"

---

### Step 1.8: Connectivity Type

**Ask**:
```
How should Snowflake connect to Glue?

A: Public (Default) - Connect over public internet
B: Private (PrivateLink) - Connect via AWS PrivateLink
   ⚠ Requires Business Critical Edition (or higher)
   ⚠ Requires same cloud provider AND region as Snowflake
   ⚠ Cross-region PrivateLink is NOT supported (AWS limitation)
   ℹ ACCESS_DELEGATION_MODE choice is independent — vended credentials work with catalog-server PrivateLink
     (For S3 Tables direct path, use AWS_PRIVATE_S3TABLES instead — requires two endpoints)
```

**If user selects Private (PrivateLink)**, first verify their account edition:
> ⚠️ Do NOT execute this query directly. Ask the user to run it — they must have access to the ORGANIZATION_USAGE schema.
```sql
SELECT EDITION
  FROM SNOWFLAKE.ORGANIZATION_USAGE.ACCOUNTS
  WHERE ACCOUNT_NAME = CURRENT_ACCOUNT();
```
If the result is not `BUSINESS_CRITICAL` or higher, inform the user that PrivateLink requires an upgrade. To inquire about upgrading, contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge). See: [Find your current edition](https://docs.snowflake.com/en/user-guide/intro-editions#find-your-current-edition).

**Record**: Connectivity type

**If Private (PrivateLink)**:

1. **Derive PrivateLink identifiers** from the region (collected in Step 1.5):
   - Provider service name: `com.amazonaws.<region>.glue`
   - Host name: `glue.<region>.amazonaws.com`

   Present to user:
   ```
   PrivateLink Configuration (derived from region <region>):
   ─────────────────────────────────────────
   Provider service name: com.amazonaws.<region>.glue
   Host name:             glue.<region>.amazonaws.com
   ─────────────────────────────────────────
   
   These will be used to provision the PrivateLink endpoint 
   during the creation step.
   ```

**Record**: Connectivity type + PrivateLink identifiers (if private)

---

### Step 1.8a: Storage Connectivity (VENDED_CREDENTIALS only)

> **Skip this step if `ACCESS_DELEGATION_MODE` is `EXTERNAL_VOLUME_CREDENTIALS`.**

**Ask**:
```
Do you want Snowflake-to-storage traffic to also traverse PrivateLink
(using vended credentials)?

This routes S3 data reads through AWS PrivateLink by setting
DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE).
It is independent of catalog-server PrivateLink (CATALOG_API_TYPE).

yes / no
```

**Record**: `enable_storage_privatelink` = yes | no

**If `enable_storage_privatelink = yes`**, collect and present the following storage-side prerequisites:

1. **Provision the Snowflake-side S3 PrivateLink endpoint** (one endpoint covers all S3 buckets in the region). **⚠️ MANDATORY CHECKPOINT**: this creates a persistent endpoint in the Snowflake VPC and may incur cost — present the command and wait for explicit user approval before executing:
   ```sql
   USE ROLE ACCOUNTADMIN;
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
     'com.amazonaws.<region>.s3',
     '*.<region>.s3.amazonaws.com'
   );
   ```

> **Note (Glue-specific)**: Do NOT apply an S3 bucket policy that denies public access for Glue-backed tables. Unlike Unity Catalog (where you can allowlist the catalog's control-plane VPC), there is currently no way to distinguish and allowlist the AWS Glue catalog's traffic to S3 via a bucket policy. A deny-by-default policy would block Glue's own access. With Glue, enabling `USE_PRIVATELINK_ENDPOINT = TRUE` routes Snowflake's storage reads over PrivateLink, but enforcing network lockdown on the bucket is **optional and currently not possible for Glue** — so leave the bucket reachable by Glue and do not add a restrictive bucket policy. This is a current Glue-side limitation; if Glue later supports distinguishing/allowlisting its traffic, the bucket can be locked down as with other catalogs.

2. **Lake Formation prerequisites**: Ensure `<DATA_ACCESS_ROLE_ARN>` (the role LF assumes to generate vended credentials) has `s3:GetObject`, `s3:ListBucket`, and `s3:GetBucketLocation` on the target S3 bucket and is registered with Lake Formation.

3. **Same-region requirement**: The S3 bucket(s) must be in the same AWS region as the Snowflake account — AWS PrivateLink for S3 is regional.

For the full cross-vendor endpoint provisioning workflow (allowlist, verify), see [shared/vended-credentials-private-storage/SKILL.md](../../shared/vended-credentials-private-storage/SKILL.md). **Note**: The shared skill's "Step 2: Block public access" does NOT apply to Glue — see the note above.

---

### Step 1.9: Integration Name

**Ask**:
```
What would you like to name your catalog integration?

Guidelines:
- Alphanumeric characters and underscores only
- Must be unique in your Snowflake account

Default suggestion: glue_catalog_int
```

**Record**: Integration name

---

### Step 1.9a: Custom External ID (Optional)

**Ask**:
```
Would you like to provide your own external ID for the trust relationship?

A: No (Default) — Snowflake will auto-generate a unique external ID
B: Yes — I want to specify my own external ID

Providing your own external ID (SIGV4_EXTERNAL_ID) lets you reuse the 
same IAM role across multiple catalog integrations without updating the 
trust policy each time. This is useful in testing scenarios where you 
recreate integrations frequently.
```

**If No (A)** → Record: External ID = auto-generated. Continue to Step 1.10.

**If Yes (B)** → **Ask**: "What external ID would you like to use?"
- **Record**: Custom external ID value
- Continue to Step 1.10

---

### Step 1.10: Prerequisites Summary

**Present complete checklist**:

```
Prerequisites Checklist
═══════════════════════════════════════════════════════════

✓ Access Delegation Mode: <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
✓ Lake Formation: <Enabled|Not required>
✓ AWS Account ID: <account_id>
✓ AWS Region: <region>
✓ Catalog URI: https://glue.<region>.amazonaws.com/iceberg
✓ Glue Database: <database_name|Not specified>
✓ Glue Catalog Name: <glue_catalog_name> (e.g., AWS Account ID for default catalog)
✓ IAM Role ARN: <iam_role_arn>
✓ IAM Policy: Attached to role
✓ Connectivity: <Public|Private (PrivateLink)>
✓ Integration Name: <integration_name>
✓ External ID: <custom_value|Auto-generated by Snowflake>
✓ Storage Connectivity: <enable_storage_privatelink> (VENDED_CREDENTIALS only)

═══════════════════════════════════════════════════════════

Note: Trust relationship will be configured AFTER integration 
creation when Snowflake provides IAM user ARN and external ID.
```

**If Private (PrivateLink)**, also include:
```
PrivateLink Details:
─────────────────────────────────────────
✓ Edition:              Business Critical (or higher)
✓ Provider service name: com.amazonaws.<region>.glue
✓ Host name:             glue.<region>.amazonaws.com
✓ Access Delegation:    <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
✓ Storage Connectivity: <enable_storage_privatelink>
─────────────────────────────────────────

Note: PrivateLink endpoint will be provisioned in Snowflake 
during the creation step (requires ACCOUNTADMIN).
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
