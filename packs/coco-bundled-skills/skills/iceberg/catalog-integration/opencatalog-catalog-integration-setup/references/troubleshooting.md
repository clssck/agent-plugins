# Troubleshooting OpenCatalog Catalog Integration

Comprehensive guide for diagnosing and fixing issues with OpenCatalog catalog integrations.

## When to Load

Load this reference when:
- `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns failure
- Namespace or table discovery fails
- Connection or authentication errors occur
- Unexpected behavior during verification

## Important: ALTER CATALOG INTEGRATION Limitations

**Only these parameters can be altered:**
```sql
-- To change OAuth secret:
ALTER CATALOG INTEGRATION <name> SET
  REST_AUTHENTICATION = (
    OAUTH_CLIENT_SECRET = '<new_secret>'
  );

-- To change refresh interval:
ALTER CATALOG INTEGRATION <name> SET
  REFRESH_INTERVAL_SECONDS = <seconds>;

-- To enable/disable:
ALTER CATALOG INTEGRATION <name> SET
  ENABLED = TRUE;  -- or FALSE
```

**REST_CONFIG cannot be altered.** You can alter `REST_AUTHENTICATION`, but only the `OAUTH_CLIENT_SECRET` value (for secret rotation). If you need to change catalog URI, catalog name, or access delegation mode, you must **recreate the integration**:
```sql
DROP CATALOG INTEGRATION <integration_name>;
CREATE CATALOG INTEGRATION <integration_name> ...;
```

---

## Common Issues

### 1. OAuth Authentication Failures

**Error Pattern**: 
```
OAuth2 Access token request failed with error 'unauthorized_client'
Failed to perform OAuth client credential flow
```

**Common Causes**:
- Incorrect OAuth Client ID or Secret
- Wrong OAuth scopes
- Service connection doesn't exist or is disabled

#### Debug Step 1: Test OAuth Token Acquisition

Test OAuth authentication directly with curl:

```bash
curl -X POST https://<account>/polaris/api/catalog/v1/oauth/tokens \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=PRINCIPAL_ROLE:ALL" \
  --data-urlencode "client_id=<client_id>" \
  --data-urlencode "client_secret=<client_secret>"
```

**Expected Success Response**:
```json
{
  "access_token": "ey...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**If Success**: OAuth credentials are valid. Issue may be with scopes or catalog access.

**If Failure**:
```json
{
  "error": "invalid_client",
  "error_description": "Client authentication failed"
}
```

**Solutions by Error Type**:

- **invalid_client**: Client ID or Secret is incorrect
  - Verify credentials from OpenCatalog service connection
  - Regenerate credentials if needed
  - Ensure no extra spaces or hidden characters

- **invalid_scope**: Scope is not allowed
  - Check service connection has proper principal role
  - Try `PRINCIPAL_ROLE:ALL` or specific role names
  - Verify principal role is attached to catalog role

#### Debug Step 2: Test Catalog Access

If OAuth token obtained successfully, test catalog access:

```bash
curl -X GET "https://<account>/polaris/api/catalog/v1/config?warehouse=<catalog_name>" \
  -H "Authorization: Bearer <access_token>"
```

**Expected Response**:
```json
{
  "defaults": {
    "default-base-location": "s3://my-bucket/path/"
  },
  "overrides": {
    "prefix": "my-catalog"
  }
}
```

**If Failure**:
- **403 Forbidden**: Service connection lacks catalog access
  - Check catalog role privileges in OpenCatalog
  - Verify principal role is attached to catalog role
  - Required privileges: `CATALOG_LIST_PROPERTIES`, `NAMESPACE_LIST`, `TABLE_LIST`

- **404 Not Found**: Catalog name doesn't exist
  - Verify `CATALOG_NAME` spelling (case-sensitive)
  - Check catalog exists in OpenCatalog UI

#### Fix OAuth Issues

**If only the client secret changed**, you can alter it:
```sql
ALTER CATALOG INTEGRATION <integration_name> SET
  REST_AUTHENTICATION = (
    OAUTH_CLIENT_SECRET = '<new_client_secret>'
  );
```

**If client ID or other config needs to change**, recreate the integration (confirm with user first — dropping may break dependent objects):
```sql
DROP CATALOG INTEGRATION <integration_name>;

-- Public connectivity:
CREATE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'
  REST_CONFIG = (
    CATALOG_URI = 'https://<orgname>-<account_name>.snowflakecomputing.com/polaris/api/catalog'
    CATALOG_API_TYPE = PUBLIC  -- Optional, PUBLIC is the default
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<corrected_client_id>'
    OAUTH_CLIENT_SECRET = '<client_secret>'
    OAUTH_ALLOWED_SCOPES = ('PRINCIPAL_ROLE:<principal_role>')
  )
  ENABLED = TRUE;

-- PrivateLink connectivity:
CREATE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = POLARIS
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'
  REST_CONFIG = (
    CATALOG_URI = 'https://<privatelink_account_url>/polaris/api/catalog'
    CATALOG_API_TYPE = PRIVATE
    CATALOG_NAME = '<catalog_name>'
    -- ACCESS_DELEGATION_MODE here defaults to EXTERNAL_VOLUME_CREDENTIALS. To use VENDED_CREDENTIALS with private storage, set DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE).
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<corrected_client_id>'
    OAUTH_CLIENT_SECRET = '<client_secret>'
    OAUTH_ALLOWED_SCOPES = ('PRINCIPAL_ROLE:<principal_role>')
    -- OAUTH_TOKEN_URI = '<token_uri>'        -- Optional: only needed if using an external IdP (e.g., Okta, Auth0)
    -- OAUTH_API_TYPE = PRIVATE               -- Optional: defaults to CATALOG_API_TYPE. Set to PUBLIC if external IdP doesn't support inbound PrivateLink.
  )
  ENABLED = TRUE;
```

---

### 2. Catalog Not Found

**Error Pattern**:
```
Catalog '<catalog_name>' not found
Unable to access catalog
```

**Solutions**:

1. **Verify Catalog Name**: 
   - Log into OpenCatalog UI
   - Confirm exact catalog name (case-sensitive)
   - Check for typos or extra characters

2. **Recreate Integration if Name Incorrect**:
   
   Since REST_CONFIG cannot be altered, recreate the integration:
   ```sql
   DROP CATALOG INTEGRATION <integration_name>;
   CREATE CATALOG INTEGRATION <integration_name> ...;
   ```

3. **Check Service Connection Access**:
   - Ensure service connection has a catalog role
   - Catalog role must have privileges on the catalog
   - Grant required privileges in OpenCatalog:
     - `CATALOG_LIST_PROPERTIES`
     - `NAMESPACE_LIST`
     - `TABLE_LIST`

4. **Verify Catalog Type**:
   - This skill is for **internal catalogs** in OpenCatalog
   - If you have an **external catalog**, different setup required

---

### 3. Network Connectivity Issues

**Error Pattern**:
```
Connection timeout
Failed to connect to catalog
Could not reach OpenCatalog endpoint
```

#### For Public Connectivity

**Verify URL Format**: 
```
Correct: https://<orgname>-<account_name>.snowflakecomputing.com/polaris/api/catalog
```

**Test URL Reachability**:
```bash
curl -I https://<opencatalog_url>/v1/config
```

**Solutions**:

1. **Check URL Spelling**: Verify organization name and account name
2. **Test Network Access**: Ensure Snowflake can reach public internet
3. **Check Network Policies**: Verify no Snowflake network policies block OpenCatalog domain
4. **Verify Account URL**: Confirm URL from OpenCatalog settings

#### For Private Connectivity (PrivateLink)

**Verify PrivateLink Configuration**:

1. **Confirm PrivateLink Setup in OpenCatalog**: Must be configured first in the OpenCatalog UI (Settings → Inbound PrivateLink). See:
   - AWS: [AWS PrivateLink and Snowflake Open Catalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-aws)
   - Azure: [Azure Private Link and Snowflake Open Catalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-azure)
   - GCS: Private Service Connect for OpenCatalog is not currently documented. If your OpenCatalog account is on GCP, check the [OpenCatalog documentation](https://other-docs.snowflake.com/en/opencatalog/overview) for the latest updates on GCP private connectivity support.

2. **Check CATALOG_API_TYPE**: Must be `PRIVATE` for PrivateLink:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Look for `catalog_api_type` = `PRIVATE`.

3. **Verify PrivateLink URL Format**: Must use the PrivateLink account URL:
   ```
   Correct: https://<open_catalog_privatelink_account_url>/polaris/api/catalog
   ```
   The PrivateLink account URL can be found in OpenCatalog Settings → Inbound PrivateLink section.

4. **Verify PrivateLink Endpoint is Provisioned (cross-deployment only)**: If OpenCatalog and Snowflake are in different deployments, check that the endpoint exists in Snowflake:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```
   Look for an entry matching your VPCE Service ID with status "available". If same deployment, endpoint provisioning is not needed — Snowflake routes traffic internally when `CATALOG_API_TYPE=PRIVATE` is specified.

5. **Same-deployment check**: If OpenCatalog and Snowflake are in the same deployment, endpoint provisioning is not required. Verify the PrivateLink account URL is correct and check for other connectivity issues (OAuth, network policies).

**If connectivity type needs to change**, recreate the integration with correct settings.

---

### 4. External Volume Issues

**Error Pattern**:
```
External volume not found
Access denied to storage location
Cannot read from external volume
```

**Solutions**:

1. **Verify External Volume Exists**:
   ```sql
   SHOW EXTERNAL VOLUMES LIKE '<volume_name>';
   DESC EXTERNAL VOLUME <volume_name>;
   ```

2. **Check Storage Location Match**:
   - External volume storage location must match where OpenCatalog stores table data
   - Review `STORAGE_LOCATIONS` in external volume description
   - Verify with OpenCatalog's `default-base-location`
   - Storage paths must align (same bucket/container)

3. **Validate Cloud Permissions**:
   
   **AWS S3**:
   - IAM role has `s3:GetObject`, `s3:GetObjectVersion`, `s3:ListBucket`
   - Trust relationship configured for Snowflake
   
   **Google Cloud Storage**:
   - Service account has `storage.objects.get`, `storage.objects.list`
   - Proper IAM bindings configured
   
   **Azure Blob Storage**:
   - Storage account has read permissions
   - SAS token valid (if used)

4. **Consider Vended Credentials** (Alternative):
   - If external volume setup is complex
   - Requires recreating integration with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`
   - Requires OpenCatalog catalog configured for credential vending
   - **Note**: Vended credentials work with PrivateLink. To also route storage traffic over PrivateLink, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` on the integration.

---

### 5. Namespace/Table Discovery Issues

**Error Pattern**:
```
No namespaces found
Tables not visible
Empty result from LIST operations
```

**Solutions**:

1. **Verify Tables Exist in OpenCatalog**:
   - Log into OpenCatalog UI
   - Navigate to your catalog
   - Confirm namespaces and tables are registered
   - Check that tables have data files

2. **Check Catalog Role Privileges**:
   - Principal role needs `NAMESPACE_LIST` privilege
   - Principal role needs `TABLE_LIST` privilege on namespace
   - Grant via OpenCatalog UI or API

3. **Case Sensitivity**:
   - Namespace names are case-sensitive
   - Use exact spelling from OpenCatalog
   - Try listing all namespaces first:
     ```sql
     SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
     ```

4. **Nested Namespaces**:
   - OpenCatalog supports nested namespaces (e.g., `parent.child`)
   - Use exact namespace path when listing tables
   - Check full namespace hierarchy in OpenCatalog

5. **Service Connection Privileges**:
   - Verify service connection's principal role
   - Check principal role is attached to catalog role
   - Confirm catalog role has grants on specific namespaces/tables

---

### 6. Table Query Failures

**Error Pattern**:
```
Table not found
Cannot read Iceberg metadata
Metadata file not accessible
Unsupported data type
Data type mismatch
```

**Solutions**:

1. **Verify Table Registration**:
   - Confirm table appears in `SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG()`
   - Check table exists in Snowflake: `SHOW TABLES LIKE '<table_name>';`

2. **Check Metadata Access**:
   - External volume must have access to metadata files
   - Metadata stored in same location as data
   - Verify IAM/permissions for metadata directory

3. **Validate Table Schema**:
   ```sql
   DESC TABLE <database>.<schema>.<table_name>;
   ```
   - Should show columns from Iceberg schema
   - If error, metadata may be corrupted or inaccessible

4. **Check Data Type Compatibility**:
   - Snowflake may not support all Iceberg data types
   - See [Iceberg Data Types](https://docs.snowflake.com/en/user-guide/tables-iceberg-data-types#other-data-types) for supported mappings

5. **Refresh Table Metadata** (for catalog-linked databases):
   ```sql
   ALTER DATABASE <database_name> REFRESH;
   ```

---

### 7. PrivateLink Endpoint Not Available

**Error Pattern**:
```
Execution Error: Private endpoint corresponding to service name ... does not exist.
Connection timeout (with CATALOG_API_TYPE = PRIVATE)
```

**Cause**: PrivateLink endpoint was not provisioned or is not yet available. Note: **endpoint provisioning is only required for cross-deployment setups** (OpenCatalog and Snowflake in different deployments). If same deployment, this error should not occur — Snowflake routes traffic internally when `CATALOG_API_TYPE=PRIVATE` is specified. Check other connectivity issues instead.

**Debug Steps**:

1. **Determine if provisioning is needed**: If OpenCatalog and Snowflake are in the same deployment, you do not need a provisioned endpoint. Skip to verifying the catalog integration directly.

2. **If cross-deployment**, check PrivateLink endpoint status:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```
   Look for:
   - An entry matching your VPCE Service ID
   - `"endpoint_state": "CREATED"`
   - `"status": "available"` for the OpenCatalog host

3. **If cross-deployment and endpoint doesn't exist**:
   ```sql
   USE ROLE ACCOUNTADMIN;
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
     '<vpce_service_id>',
     '<privatelink_host>'
   );
   ```
   > **Note**: If you have multiple OpenCatalog accounts in the same deployment, consider using a wildcard hostname (e.g., `*.us-west-2.privatelink.snowflakecomputing.com`) instead. Each deployment has a single PrivateLink service, so a wildcard endpoint can serve all accounts in that deployment through one endpoint.

**Solutions**:
- If same deployment, provisioning is not needed (Snowflake handles internal traffic routing when `CATALOG_API_TYPE=PRIVATE`) — investigate other connectivity issues (URL, OAuth, network policies)
- If cross-deployment, provision endpoint if missing
- Wait a few minutes for status to transition to "available"
- Verify ACCOUNTADMIN role was used for provisioning
- Confirm the VPCE Service ID is correct (found in OpenCatalog Settings → Inbound PrivateLink)

---

### 8. PrivateLink Endpoint Limit Exceeded

**Error Pattern**:
```
The account cannot create more than 5 private endpoints. Please contact Snowflake support for help.
```

**Cause**: Snowflake accounts are limited to a **maximum of 5 private endpoints**. Deprovisioned endpoints still count toward this limit for 7 days after removal. Note: endpoint provisioning is only needed for **cross-deployment** setups. If OpenCatalog and Snowflake are in the same deployment, you do not need to provision an endpoint at all — Snowflake handles internal traffic routing when `CATALOG_API_TYPE=PRIVATE` is specified.

**Debug Steps**:

1. Check current endpoints:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```

2. Count active and recently deprovisioned endpoints

**Solutions**:
- Remove unused PrivateLink endpoints to free up slots (note: deprovisioned endpoints count toward the limit for 7 days)
- You cannot have more than one endpoint to the same VPCE service
- To increase the 5-endpoint limit, contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge)

> **Reference**: [Private connectivity for outbound network traffic — Scaling considerations](https://docs.snowflake.com/en/user-guide/private-connectivity-outbound)

---

### 9. PrivateLink Endpoint Already Exists

**Error Pattern**:
```
Error executing SQL: Private endpoint for resource <vpce_service_id> already exists
```

**Cause**: A PrivateLink endpoint for this VPCE service has already been provisioned. This can mean one of three things — the endpoint is correct and ready to use, it exists but is mapped to the wrong hostname, or it was provisioned for a different OpenCatalog account in the same deployment.

**Debug Steps**:

1. Check the existing endpoint:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```

2. Find the entry matching your `"provider_service_name"` and inspect the `"host"` value.

3. **Determine which case applies**:

#### Case A: Hostname matches your intended OpenCatalog PrivateLink host

The endpoint already exists and is correctly configured. **No action needed.**

- Verify `"status"` is `"available"`
- If status is healthy, proceed with creating the catalog integration
- If status is not healthy, see [Issue #7: PrivateLink Endpoint Not Available](#7-privatelink-endpoint-not-available)

#### Case B: Hostname does NOT match your intended OpenCatalog PrivateLink host

The endpoint exists but is mapped to a different hostname. This commonly happens when:
- The PrivateLink account URL was entered incorrectly during initial provisioning
- An account was migrated or renamed

**Solution**: Use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME` to update the hostname on the existing endpoint **without deprovisioning**:

```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<vpce_service_id>',              -- VPCE Service ID from OpenCatalog Settings
  '<correct_privatelink_host>'      -- e.g. myorg-myaccount.privatelink.snowflakecomputing.com
);
```

**Verify** the hostname was updated:
```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

> **Important**: Do NOT deprovision and re-provision the endpoint to fix a hostname mismatch. Deprovisioned endpoints count toward the 5-endpoint limit for 7 days. Use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME` instead.

#### Case C: Endpoint was provisioned for a different OpenCatalog account in the same deployment

The endpoint is already provisioned with a specific hostname for another OpenCatalog account, and you are now trying to provision a second endpoint for a different OpenCatalog account in the same deployment. Since all OpenCatalog accounts in the same deployment share a single PrivateLink service, provisioning a second endpoint for the same service is not possible.

**Solution**: Update the existing endpoint to use a wildcard hostname so it can serve all OpenCatalog accounts in the deployment:

```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<vpce_service_id>',                                      -- VPCE Service ID (shared across accounts in the deployment)
  '*.<region>.privatelink.snowflakecomputing.com'            -- e.g. *.us-west-2.privatelink.snowflakecomputing.com
);
```

**Verify** the hostname was updated:
```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

Once the wildcard is in place, both the existing and the new OpenCatalog account (and any future accounts in the same deployment) will be reachable through this single endpoint.

---

### 10. PrivateLink VPCE Service Not Allowed (Principal Not Added)

**Error Pattern**:
```
The service "<vpce_service_id>" is invalid. If it is an endpoint service, please add Snowflake as an allowed principal of the service. Use the value of "privatelink-account-principal" of the output of `SYSTEM$GET_PRIVATELINK_CONFIG` as the principal to allow.
```

**Cause**: This error occurs when calling `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT`. However, **endpoint provisioning is only required for cross-deployment setups** (OpenCatalog and Snowflake in different deployments).

**If OpenCatalog and Snowflake are in the same deployment**: You do not need to provision a PrivateLink endpoint — Snowflake handles internal traffic routing when `CATALOG_API_TYPE=PRIVATE` is specified. Skip the provisioning step entirely and proceed directly to creating the catalog integration with `CATALOG_API_TYPE = PRIVATE`.

**If OpenCatalog and Snowflake are in different deployments (cross-deployment)**: Endpoint provisioning is required. This error means the OpenCatalog VPCE endpoint service has not added the Snowflake account as an allowed principal. Follow the steps in the [AWS PrivateLink setup for OpenCatalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-aws) or [Azure Private Link setup for OpenCatalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-azure) to configure the allowlisting, then retry provisioning.

---

### 11. Storage access denied after enabling DEFAULT_STORAGE_CONFIG

**Error Pattern**:
```
Access Denied
403 Forbidden (when reading Iceberg data files)
```

**Cause**: `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` tells Snowflake to route storage traffic through a PrivateLink endpoint, but the storage bucket/container policy does not allowlist the Snowflake VPC endpoint. For AWS S3, the bucket policy must include the Snowflake VPC endpoint ID in an `aws:SourceVpce` condition.

**Solution**:

1. Retrieve the Snowflake storage PrivateLink endpoint name:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   ```
   Find the entry for your S3 interface endpoint and note the `snowflake_endpoint_name` (VPC endpoint ID, e.g., `vpce-0abc1234def567890`).

2. Update the S3 bucket policy to allow access from the Snowflake VPC endpoint:
   ```json
   {
     "Effect": "Allow",
     "Principal": "*",
     "Action": "s3:*",
     "Resource": [
       "arn:aws:s3:::<your-bucket>",
       "arn:aws:s3:::<your-bucket>/*"
     ],
     "Condition": {
       "StringEquals": {
         "aws:SourceVpce": "<snowflake_endpoint_name>"
       }
     }
   }
   ```

3. For Azure ADLS Gen2, ensure the Snowflake managed identity or service principal has appropriate access on the storage account, and that the private endpoint connection is in `APPROVED` state.

---

### 12. ADLS Gen2 dfs hostname unresolvable / "no such host"

**Error Pattern**:
```
no such host
dial tcp: lookup <account>.dfs.core.windows.net: no such host
```

**Cause**: When OpenCatalog vends credentials for Azure ADLS Gen2, it returns `dfs.core.windows.net` URLs (Data Lake Storage endpoint). If only the `blob` private endpoint sub-resource was provisioned, the `dfs` hostname is not routable over PrivateLink.

**Solution**: Two separate configurations are required — one on the Snowflake side (query-engine → storage) and one on the OpenCatalog side (catalog → storage):

**Snowflake-side `dfs` endpoint** (query-engine → storage path):

1. Run `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT` for the `dfs` sub-resource. Snowflake creates the private endpoint in its own VPC — do not manually create a private endpoint in the Azure portal:

   ```sql
   USE ROLE ACCOUNTADMIN;
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
     '/subscriptions/<subscription_id>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>',
     '<account>.dfs.core.windows.net',
     'dfs'
   );
   ```

2. In the Azure portal, navigate to the storage account → **Networking** → **Private endpoint connections**, locate the pending Snowflake connection, and click **Approve**.

**OpenCatalog-side endpoints** (catalog → storage path):

In your Open Catalog account, provision private connectivity endpoints for the storage account for both the `blob` and `dfs` sub-resources, and enable the PrivateLink toggle on the catalog. This ensures the catalog→storage path also uses private connectivity.

After provisioning and approving, verify both endpoints appear in `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` with `"status": "APPROVED"`.

---

### 13. Shared storage-PrivateLink issues (region mismatch, Azure endpoint pending)

For catalog-agnostic storage-PrivateLink issues — **region mismatch** (S3 bucket must be in the same AWS region as the Snowflake account) and **Azure private endpoint stuck in `Pending`** (approve the Snowflake-provisioned connection in the Azure portal) — see the shared troubleshooting reference: [shared/vended-credentials-private-storage/references/troubleshooting.md](../../shared/vended-credentials-private-storage/references/troubleshooting.md). The OpenCatalog-specific catalog-side endpoint steps for ADLS Gen2 are in Issue #12 above.

---

## Diagnostic Workflow

When troubleshooting, follow this sequence:

1. **Check Integration Status**:
   ```sql
   SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';
   DESC CATALOG INTEGRATION <integration_name>;
   ```

2. **Test Connection**:
   ```sql
   SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
   ```

3. **Review Query History** for detailed errors:
   ```sql
   SELECT * FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY())
   WHERE QUERY_TEXT ILIKE '%<integration_name>%'
   ORDER BY START_TIME DESC LIMIT 10;
   ```

4. **Check OpenCatalog Logs**:
   - Access OpenCatalog UI
   - View service connection activity logs
   - Look for authentication or authorization failures

5. **Test OAuth Separately** (see OAuth section above)

6. **PrivateLink Diagnostics** (if using PRIVATE connectivity):
   ```sql
   -- Check all PrivateLink endpoints
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;

   -- Provision a new PrivateLink endpoint (ACCOUNTADMIN required, cross-deployment ONLY)
   USE ROLE ACCOUNTADMIN;
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
     '<vpce_service_id>',
     '<privatelink_host>'
   );
   -- Note: If you have multiple OpenCatalog accounts in the same deployment, consider using
   -- a wildcard hostname (e.g., '*.us-west-2.privatelink.snowflakecomputing.com'). Each deployment
   -- has a single PrivateLink service, so one wildcard endpoint can cover them all.
   ```
   > **Note**: Endpoint provisioning is only needed for cross-deployment setups. If OpenCatalog and Snowflake are in the same deployment, skip provisioning — Snowflake handles internal traffic routing when `CATALOG_API_TYPE=PRIVATE` is specified.

**PrivateLink endpoint management** (ACCOUNTADMIN required):
```sql
-- Remove a PrivateLink endpoint (queued for deletion after 7 days)
SELECT SYSTEM$DEPROVISION_PRIVATELINK_ENDPOINT(
  '<vpce_service_id>'
);

-- Restore a recently removed endpoint (within 7-day deletion queue)
SELECT SYSTEM$RESTORE_PRIVATELINK_ENDPOINT(
  '<vpce_service_id>'
);

-- Change the host name of an existing endpoint (without changing its network resource)
SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<vpce_service_id>',
  '<new_host_name>'
);
```

> **Reference**: [Manage private connectivity endpoints: AWS](https://docs.snowflake.com/en/user-guide/private-manage-endpoints-aws)

---

## Getting Additional Help

**Documentation Resources**:
- [Snowflake Iceberg REST Catalog Troubleshooting](https://docs.snowflake.com/user-guide/tables-iceberg-configure-catalog-integration-rest-check-config)
- [OpenCatalog Access Control](https://other-docs.snowflake.com/en/opencatalog/access-control)
- [OpenCatalog Service Connections](https://other-docs.snowflake.com/en/opencatalog/configure-service-connection)
- [ALTER CATALOG INTEGRATION](https://docs.snowflake.com/en/sql-reference/sql/alter-catalog-integration)
- [CREATE CATALOG INTEGRATION (Snowflake Open Catalog)](https://docs.snowflake.com/en/sql-reference/sql/create-catalog-integration-open-catalog)
- [AWS PrivateLink and Snowflake Open Catalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-aws)
- [Azure Private Link and Snowflake Open Catalog](https://docs.snowflake.com/user-guide/opencatalog/private-connectivity-inbound-configure-azure)

**Common Resolution Paths**:
- OAuth secret changed → Use ALTER to update secret
- OAuth client ID or config changed → Recreate integration
- Catalog not found → Verify catalog name, recreate if needed
- Network issues → Check connectivity type and URLs
- External volume → Validate cloud permissions and storage paths
- Discovery issues → Grant proper catalog role privileges
- PrivateLink endpoint missing → Provision via `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT` (cross-deployment only; same-deployment does not require provisioning because Snowflake handles internal traffic routing when `CATALOG_API_TYPE=PRIVATE`)
- PrivateLink endpoint hostname mismatch → Update via `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME`
- PrivateLink VPCE service invalid → Skip provisioning if same deployment (Snowflake routes traffic internally); configure allowlisting if cross-deployment setups
