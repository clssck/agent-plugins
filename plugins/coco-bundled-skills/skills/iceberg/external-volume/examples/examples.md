# External Volume SQL Templates

## AWS S3
```sql
CREATE OR REPLACE EXTERNAL VOLUME iceberg_s3_vol
    STORAGE_LOCATIONS = ((
        NAME = 'primary-s3'
        STORAGE_PROVIDER = 'S3'
        STORAGE_BASE_URL = 's3://my-bucket/tables/'
        STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/snowflake-role'
    ))
    ALLOW_WRITES = TRUE;
```

### GovCloud
```sql
CREATE OR REPLACE EXTERNAL VOLUME iceberg_s3gov_vol
    STORAGE_LOCATIONS = ((
        NAME = 'govcloud-s3'
        STORAGE_PROVIDER = 'S3GOV'
        STORAGE_BASE_URL = 's3://my-govcloud-bucket/iceberg/'
        STORAGE_AWS_ROLE_ARN = 'arn:aws-us-gov:iam::123456789012:role/snowflake-role'
    ))
    ALLOW_WRITES = TRUE;
```

### SSE-KMS Encryption
```sql
CREATE OR REPLACE EXTERNAL VOLUME iceberg_s3_encrypted_vol
    STORAGE_LOCATIONS = ((
        NAME = 'encrypted-s3'
        STORAGE_PROVIDER = 'S3'
        STORAGE_BASE_URL = 's3://my-bucket/iceberg/'
        STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/snowflake-role'
        ENCRYPTION = (TYPE = 'AWS_SSE_KMS' KMS_KEY_ID = 'arn:aws:kms:us-east-1:123456789012:key/abc123')
    ))
    ALLOW_WRITES = TRUE;
```

## Azure Blob Storage
```sql
CREATE OR REPLACE EXTERNAL VOLUME iceberg_azure_vol
    STORAGE_LOCATIONS = ((
        NAME = 'primary-azure'
        STORAGE_PROVIDER = 'AZURE'
        STORAGE_BASE_URL = 'azure://mystorageaccount.blob.core.windows.net/container/tables/'
        AZURE_TENANT_ID = 'a123b4c5-1234-5678-9abc-123456789012'
    ))
    ALLOW_WRITES = TRUE;
```

## Google Cloud Storage
```sql
CREATE OR REPLACE EXTERNAL VOLUME iceberg_gcs_vol
    STORAGE_LOCATIONS = ((
        NAME = 'primary-gcs'
        STORAGE_PROVIDER = 'GCS'
        STORAGE_BASE_URL = 'gcs://my-bucket/tables/'
    ))
    ALLOW_WRITES = TRUE;
```

### CMEK Encryption
```sql
CREATE OR REPLACE EXTERNAL VOLUME iceberg_gcs_encrypted_vol
    STORAGE_LOCATIONS = ((
        NAME = 'gcs-encrypted'
        STORAGE_PROVIDER = 'GCS'
        STORAGE_BASE_URL = 'gcs://my-bucket/iceberg/'
        ENCRYPTION = (TYPE = 'GCS_SSE_KMS' KMS_KEY_ID = 'projects/my-project/locations/us-central1/keyRings/ring/cryptoKeys/key')
    ))
    ALLOW_WRITES = TRUE;
```

## Microsoft Fabric / OneLake
```sql
CREATE OR REPLACE EXTERNAL VOLUME onelake_vol
    STORAGE_LOCATIONS = ((
        NAME = 'onelake'
        STORAGE_PROVIDER = 'AZURE'
        STORAGE_BASE_URL = 'azure://onelake.dfs.fabric.microsoft.com/<workspace_id>/<lakehouse_id>/Files/iceberg/'
        AZURE_TENANT_ID = '<fabric_tenant_id>'
    ))
    ALLOW_WRITES = TRUE;
```

### Fabric Tenant Settings Required
1. Admin Portal → Developer Settings: Enable "Service Principals can call Fabric public APIs"
2. Admin Portal → OneLake Settings: Enable "Users can access data stored in OneLake with apps external to Fabric"

## CLI Verification Commands

### AWS
```bash
aws iam get-role --role-name snowflake-role --query 'Role.AssumeRolePolicyDocument'
aws iam list-attached-role-policies --role-name snowflake-role
aws s3api get-object-acl --bucket my-bucket --key path/to/object  # Check object ownership ACL
aws s3api get-bucket-ownership-controls --bucket my-bucket  # Check bucket ownership settings
```

### GCS
```bash
gcloud storage buckets get-iam-policy gs://my-bucket
gcloud kms keys add-iam-policy-binding my-key --keyring=ring --location=us-central1 \
    --member="serviceAccount:<STORAGE_GCP_SERVICE_ACCOUNT>" \
    --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
```

### Azure
```bash
az account show --query tenantId -o tsv
az role assignment list --assignee "<service_principal_id>" --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>"
```
