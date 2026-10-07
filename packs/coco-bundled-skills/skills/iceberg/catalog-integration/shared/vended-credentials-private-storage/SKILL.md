---
name: catalog-integration-vended-credentials-private-storage
description: "Catalog-agnostic workflow for routing Snowflake-to-storage traffic through PrivateLink while using catalog-vended credentials. Apply when a catalog integration with ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS needs DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE). Triggers: vended credentials privatelink, vended creds private storage, USE_PRIVATELINK_ENDPOINT, DEFAULT_STORAGE_CONFIG, vended credentials private connectivity, catalog vended credentials privatelink storage."
---

# Enable private connectivity to storage with vended credentials

This is the catalog-agnostic workflow for routing **Snowflake-to-storage** traffic through PrivateLink while still using catalog-vended credentials. Any catalog integration that supports `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` can opt in by setting `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`.

For vendor-specific Step 1 prep (catalog side), see the per-vendor catalog-integration sub-skill (Open Catalog, Unity Catalog, Glue, etc.). The cross-vendor steps below are identical across vendors.

## Applicability

- Catalog integration uses `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`.
- Storage providers: Amazon S3, Azure Blob Storage, Azure Data Lake Storage Gen2 (ADLS Gen2). **Not GCP.**
- Cloud routing: AWS PrivateLink and Azure Private Link only.
- AWS: storage bucket region must match the Snowflake account region.
- Independent of catalog-server PrivateLink (`CATALOG_API_TYPE = PRIVATE` or `AWS_PRIVATE_GLUE`); you can enable either or both.

> **⚠️ Lockout warning**: Configure and verify catalog-side private storage access (Step 1) **before** blocking public storage access (Step 2). Otherwise, your catalog server may lose the ability to read metadata from your bucket.

## Step 1: Confirm catalog-side private storage access (vendor-specific)

Before blocking public access to storage, ensure the catalog server itself can reach the bucket through private connectivity. Vendor specifics:

- **Snowflake Open Catalog (POLARIS)** — Provision a private connectivity endpoint in your Open Catalog account and enable the PrivateLink toggle on the catalog. See the corresponding Manage private connectivity endpoints for Snowflake Open Catalog doc for AWS or Azure.
- **Databricks Unity Catalog** — Classic compute (customer-managed VPC/VNet): configure an S3 Gateway/Interface endpoint or Azure VNet `Microsoft.Storage` service endpoint. Serverless: networking is Databricks-managed; allowlist Databricks control-plane VPC IDs / NAT IPs on your storage.
- **AWS Glue** — Glue accesses S3 within AWS by default; ensure Lake Formation permissions and the IAM role used by `SIGV4_IAM_ROLE` allow reads on the bucket(s).
- **Generic Iceberg REST (self-hosted / other vendor)** — Follow your catalog vendor's documentation to give the catalog server private access to the storage bucket.

## Step 2: Block public access to storage (storage side)

After Step 1 is verified, restrict storage to private traffic only.

**AWS S3 bucket policy** — use `StringNotEqualsIfExists` so multiple VPC endpoints / VPCs are evaluated independently (NOR semantics). Add Snowflake's VPCE (collected in Step 4) and the catalog's VPC endpoints / VPC IDs:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyIfNotFromApprovedVpcsOrVpces",
      "Effect": "Deny",
      "Principal": "*",
      "Action": [
        "s3:PutObject", "s3:GetObject", "s3:GetObjectVersion",
        "s3:DeleteObject", "s3:DeleteObjectVersion",
        "s3:ListBucket", "s3:GetBucketLocation"
      ],
      "Resource": [
        "arn:aws:s3:::<your-bucket-name>",
        "arn:aws:s3:::<your-bucket-name>/*"
      ],
      "Condition": {
        "StringNotEqualsIfExists": {
          "aws:SourceVpce": ["<snowflake-vpce-id>", "<catalog-vpce-id>"],
          "aws:SourceVpc":  ["<catalog-vpc-id>"]
        }
      }
    }
  ]
}
```

**Azure** — On the storage account, disable public access or restrict to allowlisted virtual networks / IPs. Approve the Snowflake private endpoint connection (Step 4).

## Step 3: Provision the storage PrivateLink endpoint

> **⚠️ MANDATORY CHECKPOINT**: `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT` creates a persistent private endpoint in the Snowflake VPC (and may incur cost). Present the exact command(s) to the user and wait for explicit approval before executing.

```sql
USE ROLE ACCOUNTADMIN;

-- AWS S3 (one endpoint covers all S3 buckets in the same region;
-- only buckets used by integrations with USE_PRIVATELINK_ENDPOINT = TRUE
-- traverse the endpoint).
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.s3',
  '*.<region>.s3.amazonaws.com'
);

-- Azure Blob Storage
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '/subscriptions/<subscription_id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>',
  '<account>.blob.core.windows.net',
  'blob'
);

-- Azure ADLS Gen2 (REQUIRED in addition to blob endpoint when catalog uses dfs hostnames)
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '/subscriptions/<subscription_id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>',
  '<account>.dfs.core.windows.net',
  'dfs'
);
```

## Step 4: Allowlist Snowflake on the storage side

```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

- **AWS** — copy `snowflake_endpoint_name` (e.g. `vpce-01c31eb5f4a1e817d`) and add it to the `aws:SourceVpce` list in the bucket policy from Step 2.
- **Azure** — in the portal, navigate to the storage account → **Networking → Private endpoint connections**, find the pending Snowflake connection and click **Approve**.

## Step 5: Set USE_PRIVATELINK_ENDPOINT on the catalog integration

For a new integration, include in `DEFAULT_STORAGE_CONFIG`. For an existing integration, alter:

> **⚠️ MANDATORY CHECKPOINT**: The following statement modifies a live catalog integration. Present it to the user and wait for explicit approval (a clear "yes" / "proceed") **before** executing. Do not run it automatically.

```sql
USE ROLE ACCOUNTADMIN;

ALTER CATALOG INTEGRATION <integration_name>
  SET DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE);
```

The vendor-specific CREATE example with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` and `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` is in the per-vendor catalog-integration sub-skill.

## Step 6: Verify end-to-end

```sql
-- 1. Endpoint is ready (status: available on AWS, APPROVED on Azure)
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();

-- 2. Catalog integration carries the property
DESC CATALOG INTEGRATION <integration_name>;
-- Expect a default_storage_config row containing USE_PRIVATELINK_ENDPOINT=true

-- 3. Catalog integration is healthy
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

**4. End-to-end probe** — register a table backed by this integration and read from it.

> Because the integration uses `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`, register the probe table **without** `EXTERNAL_VOLUME`. The catalog vends storage credentials; there is no external volume. Do **not** invent one — `EXTERNAL_VOLUME = 'VENDED'` (or any name) references a non-existent volume and fails. Use `CATALOG_NAMESPACE` + `CATALOG_TABLE_NAME` instead:

```sql
CREATE ICEBERG TABLE <database>.<schema>.<iceberg_table>
  CATALOG = '<integration_name>'
  CATALOG_NAMESPACE = '<namespace>'
  CATALOG_TABLE_NAME = '<catalog_table_name>';

-- Read over the storage PrivateLink path
SELECT * FROM <database>.<schema>.<iceberg_table> LIMIT 1;
```

If the probe fails after Step 2 was applied, the most common causes are: bucket policy missing the Snowflake VPCE, Azure private endpoint still in `Pending` state, region mismatch (storage region ≠ Snowflake account region), or — for ADLS Gen2 — a missing `dfs` endpoint when the catalog vends `dfs.core.windows.net` URLs. See [references/troubleshooting.md](references/troubleshooting.md) for these catalog-agnostic storage-PrivateLink issues (and the per-vendor skill for vendor-specific ones).

## Stopping Points

- ✋ After Step 1 — verify catalog-side private storage access works **before** Step 2.
- ✋ After Step 2 — confirm the catalog can still read/write before continuing.
- ✋ After Step 5 — review the `ALTER` / `CREATE` SQL with the user before executing.

## Output

A catalog integration with `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` and a verified storage PrivateLink endpoint (`available` on AWS / `APPROVED` on Azure). Iceberg tables backed by the integration read from cloud storage over PrivateLink.

## Documentation

- [SYSTEM$PROVISION_PRIVATELINK_ENDPOINT](https://docs.snowflake.com/en/sql-reference/functions/system_provision_privatelink_endpoint)
- [SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO](https://docs.snowflake.com/en/sql-reference/functions/system_get_privatelink_endpoints_info)
- [Use catalog-vended credentials for Apache Iceberg™ tables](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-vended-credentials)
- [Configure an Apache Iceberg™ REST catalog integration with outbound private connectivity](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-private)
- [Private connectivity for outbound network traffic](https://docs.snowflake.com/en/user-guide/private-connectivity-outbound)
