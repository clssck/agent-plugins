---
name: create-storage-integration
description: >
  Create a storage integration for external cloud storage (Amazon S3, Google Cloud Storage,
  Microsoft Azure, Microsoft Fabric OneLake). Guides through provider selection, IAM trust setup,
  and access verification. Triggers: CREATE STORAGE INTEGRATION, connect S3, connect GCS,
  connect Azure, connect OneLake, external stage setup, storage integration, IAM role,
  STORAGE_ALLOWED_LOCATIONS, STORAGE_AWS_ROLE_ARN, AZURE_TENANT_ID, USE_PRIVATELINK_ENDPOINT.
---

# Create Storage Integration

Create a Snowflake storage integration that provides secure, credential-free access to external cloud storage for data loading and unloading.

## When to Use

Use this skill when the user wants to:
- Connect Snowflake to an S3 bucket, GCS bucket, Azure container, or OneLake lakehouse
- Set up credential-free access for external stages
- Create a new storage integration for data loading/unloading pipelines

## Key Concepts

- **Storage integration**: A Snowflake object that stores a generated IAM entity for external cloud storage. Stages that reference an integration don't need inline credentials.
- **One integration, many stages**: A single integration can back multiple external stages, as long as each stage URL falls within `STORAGE_ALLOWED_LOCATIONS`.
- **IAM trust is a two-step process**: (1) Create the integration in Snowflake to generate an IAM entity, then (2) grant that entity permissions in your cloud provider.
- **`CREATE OR REPLACE` breaks stages**: It generates a new hidden ID, breaking all stages that reference the old integration. Prefer creating new integrations or use ALTER for changes.

## Workflow

### Step 1: Determine the Cloud Provider

| Provider | `STORAGE_PROVIDER` | URL prefix | Required params |
|---|---|---|---|
| Amazon S3 | `'S3'` | `s3://` | `STORAGE_AWS_ROLE_ARN` |
| AWS China | `'S3CHINA'` | `s3china://` | `STORAGE_AWS_ROLE_ARN` |
| AWS GovCloud | `'S3GOV'` | `s3gov://` | `STORAGE_AWS_ROLE_ARN` |
| Google Cloud Storage | `'GCS'` | `gcs://` | (none) |
| Microsoft Azure | `'AZURE'` | `azure://<account>.blob.core.windows.net/` | `AZURE_TENANT_ID` |
| Microsoft Fabric OneLake | `'AZURE'` | `azure://onelake.blob.fabric.microsoft.com/` | `AZURE_TENANT_ID` |

### Step 2: Gather Required Information

**All providers:**
- Integration name
- Bucket/container URLs to allow (and optionally block)
- Whether to enable immediately

**S3-specific (optional):**
- `STORAGE_AWS_EXTERNAL_ID` — custom external ID for trust policy (auto-generated if omitted)
- `STORAGE_AWS_OBJECT_ACL = 'bucket-owner-full-control'` — for cross-account bucket access
- `USE_PRIVATELINK_ENDPOINT = TRUE` — for private connectivity

**Azure-specific (optional):**
- `USE_PRIVATELINK_ENDPOINT = TRUE` — for private connectivity (not supported for OneLake)

### Step 3: Create the Integration

**Amazon S3:**

```sql
CREATE STORAGE INTEGRATION <name>
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  STORAGE_AWS_ROLE_ARN = '<arn:aws:iam::123456789012:role/my-role>'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('s3://<bucket>/<path>/');
```

**Google Cloud Storage:**

```sql
CREATE STORAGE INTEGRATION <name>
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'GCS'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('gcs://<bucket>/<path>/');
```

**Microsoft Azure:**

```sql
CREATE STORAGE INTEGRATION <name>
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'AZURE'
  AZURE_TENANT_ID = '<tenant-id>'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('azure://<account>.blob.core.windows.net/<container>/<path>/');
```

**Microsoft Fabric OneLake:**

```sql
CREATE STORAGE INTEGRATION <name>
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'AZURE'
  AZURE_TENANT_ID = '<tenant-id>'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('azure://onelake.blob.fabric.microsoft.com/<workspace_id>/<item_id>/Files/<path>/');
```

**Wildcard with blocked locations** (allow all except specific paths):

```sql
CREATE STORAGE INTEGRATION <name>
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'S3'
  STORAGE_AWS_ROLE_ARN = '<role-arn>'
  ENABLED = TRUE
  STORAGE_ALLOWED_LOCATIONS = ('*')
  STORAGE_BLOCKED_LOCATIONS = ('s3://<sensitive-bucket>/');
```

### Step 4: Complete the IAM Trust Relationship

After creating the integration, retrieve the generated IAM entity:

```sql
DESCRIBE STORAGE INTEGRATION <name>;
```

Then tell the user what to do next based on provider:

- **S3**: Copy `STORAGE_AWS_IAM_USER_ARN` and `STORAGE_AWS_EXTERNAL_ID` from the output. Update the IAM role's trust policy to allow `sts:AssumeRole` from this ARN with the external ID as a condition.
- **GCS**: Copy `STORAGE_GCP_SERVICE_ACCOUNT` from the output. Grant this service account the `storage.objectViewer` role (or `storage.objectAdmin` for unloading) on the GCS bucket.
- **Azure / OneLake**: Copy `AZURE_CONSENT_URL` from the output. Open the URL in a browser to grant consent, then assign the Snowflake app the `Storage Blob Data Reader` (or `Contributor`) role on the container.

### Step 5: Verify Access

Create a test stage and list its contents:

```sql
CREATE STAGE <test_stage>
  URL = '<cloud-url>'
  STORAGE_INTEGRATION = <name>;

LIST @<test_stage>;
```

If `LIST` returns results, the integration is working.

## Access Control

| Privilege | Object | Notes |
|---|---|---|
| CREATE INTEGRATION | Account | Only ACCOUNTADMIN has this by default. Can be granted to other roles. |

## Important Constraints

- `CREATE OR REPLACE` and `IF NOT EXISTS` are mutually exclusive — cannot use both.
- `CREATE OR REPLACE` breaks all stages referencing the integration. If you must recreate, re-link every affected stage with `ALTER STAGE <stage> SET STORAGE_INTEGRATION = <name>`.
- Gov/China region storage requires a Snowflake account in the same region. Use `S3GOV` or `S3CHINA` for `STORAGE_PROVIDER`, not `S3`.
- Cross-cloud/cross-region storage incurs per-byte transfer fees.
- `USE_PRIVATELINK_ENDPOINT` is not supported for OneLake.
- Each `STORAGE_BLOCKED_LOCATIONS` URL must be individually quoted inside the parentheses.

## Stopping Points

- Before `CREATE OR REPLACE` on an existing integration: Warn user about stage breakage and recommend ALTER instead.
