---
name: iceberg-external-volume
description: "Use for **ALL** requests related to debugging, troubleshooting, or diagnosing Iceberg external volume issues. This skill provides systematic workflows for diagnosing storage access failures, IAM/permission issues, trust policy misconfigurations, and connectivity problems across AWS S3, Azure Blob Storage, and Google Cloud Storage. Invoke this skill when users report errors creating Iceberg tables, external volume verification failures, or storage access denied errors. Triggers: external volume, iceberg volume, storage access, S3 storage, Azure storage, GCS storage, write errors, ALLOW_WRITES, cannot write, writes not allowed, storage permissions, IAM role, trust policy, Access Denied, 403 error, create iceberg table error, external volume verification, iceberg write failure, storage location."
---

# Iceberg External Volume Debugging

## Setup Intent Guard

**This guard fires ONLY on setup intent** — when a user arrives wanting to *create* a new external volume. It does NOT fire on troubleshooting (user names an existing volume, reports 403/Access Denied, write errors, or any error from the Error Quick Reference below).

**When the user wants to create an external volume**, ask:

> Do you need your data in your **own** cloud storage (data residency requirements, customer-managed encryption keys, or an existing data lake you want Snowflake to read from)?
>
> Or do you just want to **create an Iceberg table** and let Snowflake handle storage?

- If **own cloud storage** → continue with the setup flow below (the user has a genuine BYO storage need).
- If **just create an Iceberg table** → Snowflake-managed storage needs no external volume. Route to `../snowflake-managed-storage/SKILL.md` — it creates the table with `CATALOG='SNOWFLAKE'` + `EXTERNAL_VOLUME='SNOWFLAKE_MANAGED'` (zero IAM/trust-policy setup).

**Do NOT fire this guard when:**
- The user names an **existing** external volume (e.g. "my volume MY_VOL gives Access Denied")
- The user reports errors: 403, Access Denied, cannot write, trust policy issues
- The request matches any row in the Error Quick Reference table below

In those cases, proceed directly to the troubleshooting/diagnostic flow.

---

## Error Quick Reference
| Error Contains | Section |
|----------------|---------|
| `Access Denied`, `403`, `assuming AWS_ROLE` | AWS S3 |
| `Consent not granted`, `scoped credentials` | Azure |
| `Permission Denied` (GCS) | GCS |
| `cannot be dropped`, `cannot be undropped` | Recreating External Volumes |
| `null metadata location` | known-issues.md |
| `STORAGE_LOCATION defined in the local region` | Key Behaviors (Region Matching) |

## Quick Diagnostic Commands

```sql
SHOW EXTERNAL VOLUMES;
DESC EXTERNAL VOLUME <volume_name>;
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('<volume_name>');
```

From `DESC EXTERNAL VOLUME`, check `STORAGE_PROVIDER` to identify cloud platform:
- `S3` / `S3GOV` → AWS S3
- `AZURE` → Azure Blob Storage
- `GCS` → Google Cloud Storage
- `S3COMPAT` → S3-compatible storage

## Key Behaviors

- **Requires ACCOUNTADMIN**: Error: `Insufficient privileges to operate on external_volume '<name>'` → Use ACCOUNTADMIN role or get CREATE EXTERNAL VOLUME privilege.
- **Active Location**: Not set at volume creation. Assigned on **first Iceberg table creation** to the first `STORAGE_LOCATIONS` entry matching the Snowflake deployment region.
- **Region Matching**: External volume location **must match** Snowflake deployment region. Error: `External volume <name> must have a STORAGE_LOCATION defined in the local region <region>.`
- **Multiple Locations**: An external volume can have multiple `STORAGE_LOCATIONS`. Only the region-matched one becomes active.
- **First Use Validation**: On first use, Snowflake tests read/list access. Error: `A test file read on the external volume <name> active storage location <loc> failed with the message 'Access Denied (Status Code: 403; Error Code: AccessDenied)'.` → Fix IAM/permissions per provider section below.
- **Write Test Failures**: Error: `A test file creation on the external volume <name> active storage location <loc> failed with the message 'Access Denied'.` → Fix write permissions or use `ALLOW_WRITES = FALSE` if read-only intended.

## Error Solutions by Cloud Provider

### AWS S3: "Access Denied" or "Error assuming AWS_ROLE"

**Get Snowflake's credentials:**
```sql
DESC EXTERNAL VOLUME <volume_name>;
-- Note: STORAGE_AWS_IAM_USER_ARN and STORAGE_AWS_EXTERNAL_ID
```

**Required Trust Policy** (in AWS IAM Role → Trust Relationships):
```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": { "AWS": "<STORAGE_AWS_IAM_USER_ARN>" },
        "Action": "sts:AssumeRole",
        "Condition": {
            "StringEquals": { "sts:ExternalId": "<STORAGE_AWS_EXTERNAL_ID>" }
        }
    }]
}
```

**Required IAM Policy:**
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["s3:PutObject", "s3:GetObject", "s3:GetObjectVersion", "s3:DeleteObject", "s3:DeleteObjectVersion"],
            "Resource": "arn:aws:s3:::<bucket>/*"
        },
        {
            "Effect": "Allow",
            "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
            "Resource": "arn:aws:s3:::<bucket>"
        }
    ]
}
```

**Common Issues:**
- STS not activated → AWS IAM → Account settings → Activate STS in Snowflake's region
- Bucket names with dots (e.g., `my.bucket.name`) are NOT supported
- External ID mismatch between Snowflake and trust policy
- S3 Object Ownership ACL → Bucket may require object creator ownership. Check S3 bucket → Permissions → Object Ownership; set to "Bucket owner enforced"
- Bucket policy deny rules → Check bucket policy for explicit Deny on certain prefixes: `aws s3api get-bucket-policy --bucket <bucket>`
- Missing `s3:ListBucket` → Without this, S3 returns 403 (not 404) on missing files. Error: `The parquet file '<file>' for table '<table>' was inaccessible.`

---

### Azure: "Consent not granted" or Access Denied

**Get Snowflake's credentials:**
```sql
DESC EXTERNAL VOLUME <volume_name>;
-- Note: AZURE_CONSENT_URL and AZURE_MULTI_TENANT_APP_NAME
```

**Fix Steps:**
1. Navigate to `AZURE_CONSENT_URL` → Click **Accept**
2. Azure Portal → Storage Account → **Access Control (IAM)** → Add role assignment
3. Role: `Storage Blob Data Contributor`
4. Search for service principal: use string **BEFORE underscore** in `AZURE_MULTI_TENANT_APP_NAME`

**Common Issues:**
- Service principal not found → Wait 1+ hour after consent
- Still denied after role assignment → Wait 10+ minutes for propagation
- Permissions must be at storage **ACCOUNT** level, not container level
- `AccessDeniedException` / `Failed trying to acquire scoped credentials in Azure` → Grant `Storage Blob Delegator` role (for GetUserDelegationKey) to service principal at storage account level

---

### GCS: Permission Denied

**Get Snowflake's credentials:**
```sql
DESC EXTERNAL VOLUME <volume_name>;
-- Note: STORAGE_GCP_SERVICE_ACCOUNT
```

**Fix Steps:**
1. Google Cloud Console → Cloud Storage → Select bucket → **Permissions**
2. Grant Access → Add `STORAGE_GCP_SERVICE_ACCOUNT` as principal
3. Assign `Storage Object Admin` role (or custom role with: `storage.buckets.get`, `storage.objects.create`, `storage.objects.delete`, `storage.objects.get`, `storage.objects.list`)

**KMS Encryption:** Add service account to `Cloud KMS CryptoKey Encrypter/Decrypter` role on key ring

---

### S3-Compatible Storage

**Check:**
- `STORAGE_ENDPOINT` is correct (without bucket name)
- Credentials (`AWS_KEY_ID`, `AWS_SECRET_KEY`) are valid
- Endpoint is reachable from Snowflake

## Property Reference Tables

### AWS S3
| Property | What to Verify |
|----------|---------------|
| `STORAGE_BASE_URL` | Valid `s3://bucket/path/` format |
| `STORAGE_AWS_ROLE_ARN` | Matches your IAM role ARN exactly |
| `STORAGE_AWS_IAM_USER_ARN` | Use this in trust policy Principal |
| `STORAGE_AWS_EXTERNAL_ID` | Must match trust policy external ID |
| `ALLOW_WRITES` | `TRUE` for Snowflake-managed tables |

### Azure
| Property | What to Verify |
|----------|---------------|
| `STORAGE_BASE_URL` | Format: `azure://account.blob.core.windows.net/container/` |
| `AZURE_TENANT_ID` | Correct Office 365 tenant ID |
| `AZURE_CONSENT_URL` | URL to grant consent |
| `AZURE_MULTI_TENANT_APP_NAME` | Snowflake's app name (search before underscore) |

### GCS
| Property | What to Verify |
|----------|---------------|
| `STORAGE_BASE_URL` | Format: `gcs://bucket/path/` |
| `STORAGE_GCP_SERVICE_ACCOUNT` | Grant this account bucket permissions |

## Recreating External Volumes

**Cannot drop/replace if in use:** Error `External volume <name> cannot be dropped because the active table(s) ["DB.SCHEMA.TABLE"] are using it.` → Drop dependent Iceberg tables first.

**Cannot UNDROP table after volume dropped:** Error `Iceberg table <name> cannot be undropped because the external volume it uses has been dropped.` → Recreate volume first, then UNDROP.

**WARNING:** `CREATE OR REPLACE EXTERNAL VOLUME` generates a new external ID unless you specify one. You MUST update the cloud provider's trust policy with the new ID.

**Safe pattern - preserve external ID:**
```sql
DESC EXTERNAL VOLUME my_volume;  -- Record STORAGE_AWS_EXTERNAL_ID

CREATE OR REPLACE EXTERNAL VOLUME my_volume
    STORAGE_LOCATIONS = ((
        NAME = 'my-location'
        STORAGE_PROVIDER = 'S3'
        STORAGE_BASE_URL = 's3://my-bucket/'
        STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/myrole'
        STORAGE_AWS_EXTERNAL_ID = '<same_external_id>'
    ));
```
