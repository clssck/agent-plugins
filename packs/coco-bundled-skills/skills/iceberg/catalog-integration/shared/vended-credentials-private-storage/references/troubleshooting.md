# Storage PrivateLink troubleshooting (vended credentials)

Catalog-agnostic troubleshooting for routing Snowflake-to-storage traffic over PrivateLink with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` and `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)`. Per-vendor catalog-integration skills link here for these shared issues and keep only vendor-specific entries (e.g., Glue bucket-policy limitation, Unity Catalog control-plane VPC/NAT allowlisting, Open Catalog catalog-side endpoints).

## Region mismatch (AWS)

**Error pattern**:
```
VPC endpoint not supported for cross-region requests
The specified bucket is not in the same AWS region as the VPC endpoint
```

**Cause**: AWS PrivateLink for S3 (Interface VPC Endpoint) requires the S3 bucket to be in the same AWS region as the Snowflake account's VPC endpoint. Cross-region S3 access is not supported over Interface VPC Endpoints.

**Solution**:
- Use an S3 bucket in the same AWS region as your Snowflake account.
- If the bucket must remain in a different region, do not set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` — let storage traffic use the public S3 endpoint while catalog traffic uses PrivateLink.

## Storage endpoint pending / not available (AWS)

**Symptom**: `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT` returns success but table reads do not route over PrivateLink, or verification shows the endpoint is not yet ready.

**Cause**: The S3 PrivateLink endpoint was provisioned but has not yet reached `available` status (provisioning can take a few minutes on AWS).

**Solution**: Check the endpoint status and wait until it is `available`:
```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
```
Look for an entry with provider service name `com.amazonaws.<region>.s3` and `"status": "available"`. Re-check if the status is still `pending` or `creating`.

## Azure private endpoint stuck in Pending

**Error pattern**:
```
Storage PrivateLink endpoint status: Pending
Connection refused / storage unreachable
```

**Cause**: When you run `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT`, Snowflake creates the private endpoint in the Snowflake VPC. The connection to your Azure Storage account must then be approved on the Azure side — Azure requires manual approval unless auto-approval is configured. You do **not** create a private endpoint manually in Azure.

**Solution**:
1. In the Azure portal, navigate to your storage account → **Networking → Private endpoint connections**.
2. Locate the pending connection from Snowflake and click **Approve**.
3. Verify the status changes to `APPROVED` in Snowflake:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   ```
   The storage endpoint entry should show `"status": "APPROVED"`.

## ADLS Gen2 `dfs` hostname unresolvable / "no such host"

**Error pattern**:
```
no such host
dial tcp: lookup <account>.dfs.core.windows.net: no such host
```

**Cause**: When the catalog vends credentials for Azure ADLS Gen2, it returns `dfs.core.windows.net` (Data Lake Storage) URLs. If only the `blob` private endpoint sub-resource was provisioned, the `dfs` hostname is not routable over PrivateLink.

**Solution**: Provision a separate endpoint for the `dfs` sub-resource (in addition to `blob`). Snowflake creates the endpoint in its own VPC — do not create it manually in the Azure portal:
```sql
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '/subscriptions/<subscription_id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>',
  '<account>.dfs.core.windows.net',
  'dfs'
);
```
Approve the connection in the Azure portal (see "Azure private endpoint stuck in Pending" above), then verify both `blob` and `dfs` endpoints show `"status": "APPROVED"` via `SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()`.

> Some catalogs (e.g., Snowflake Open Catalog) also require catalog-side private connectivity endpoints for the catalog→storage path. See the vendor's catalog-integration troubleshooting for those steps.
