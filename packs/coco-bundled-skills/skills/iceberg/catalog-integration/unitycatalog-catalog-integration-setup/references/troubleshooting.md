# Troubleshooting Unity Catalog Catalog Integration

Comprehensive guide for diagnosing and fixing issues with Unity Catalog catalog integrations.

## When to Load

Load this reference when:
- `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns failure
- Namespace or table discovery fails
- Connection or authentication errors occur
- Unexpected behavior during verification

## Important: ALTER CATALOG INTEGRATION Limitations

**Only these parameters can be altered:**
```sql
-- For OAuth authentication
ALTER CATALOG INTEGRATION <name> SET
  OAUTH_CLIENT_SECRET = '<new_secret>';

-- For Bearer token authentication
ALTER CATALOG INTEGRATION <name> SET
  BEARER_TOKEN = '<new_token>';

-- Refresh interval
ALTER CATALOG INTEGRATION <name> SET
  REFRESH_INTERVAL_SECONDS = <seconds>;
```

**REST_CONFIG cannot be altered.** If you need to change catalog URI, catalog name, or access delegation mode, you must **recreate the integration**:
```sql
DROP CATALOG INTEGRATION <integration_name>;
CREATE CATALOG INTEGRATION <integration_name> ...;
```

---

## Common Issues

### 1. OAuth Authentication Failures

**Error Pattern**: 
```
Failed to perform OAuth client credential flow
OAuth token request failed
unauthorized_client
```

**Common Causes**:
- Incorrect OAuth Client ID or Secret
- Wrong OAuth Token URI
- Invalid OAuth scopes
- Service principal doesn't exist or is disabled in Databricks

#### Debug Step 1: Verify OAuth Credentials

**Check in Databricks**:
1. Navigate to Admin Console → Service Principals
2. Verify service principal exists and is active
3. Confirm OAuth secret is correct
4. Check Token URI format: `https://<databricks-host>/oidc/v1/token`

**Test OAuth Token Acquisition**:
```bash
curl -X POST https://<databricks-host>/oidc/v1/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "scope=all-apis" \
  -d "client_id=<client_id>" \
  -d "client_secret=<client_secret>"
```

**Expected Success Response**:
```json
{
  "access_token": "ey...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

**If Failure**:
- `invalid_client`: Client ID or Secret is incorrect
- `invalid_scope`: Scope not allowed for service principal

#### Fix OAuth Issues

**If only the client secret changed**, you can alter it:
```sql
ALTER CATALOG INTEGRATION <integration_name>
  SET OAUTH_CLIENT_SECRET = '<new_client_secret>';
```

**If client ID, token URI, or scopes need to change**, recreate the integration:
```sql
DROP CATALOG INTEGRATION <integration_name>;

CREATE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  CATALOG_NAMESPACE = '<namespace>'
  REST_CONFIG = (
    CATALOG_URI = 'https://<workspace>.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest'
    CATALOG_NAME = '<catalog_name>'
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_CLIENT_ID = '<corrected_client_id>'
    OAUTH_CLIENT_SECRET = '<client_secret>'
    OAUTH_TOKEN_URI = 'https://<workspace>.cloud.databricks.com/oidc/v1/token'
    OAUTH_ALLOWED_SCOPES = ('all-apis')
  )
  ENABLED = TRUE;
```

---

### 2. Bearer Token (PAT) Failures

**Error Pattern**:
```
Authentication failed
Invalid bearer token
Token expired
401 Unauthorized
```

**Common Causes**:
- Token expired (default 90-day lifetime)
- Token revoked or deleted in Databricks
- Incorrect token copied

#### Debug Bearer Token

**Check Token Validity**:
```bash
curl -H "Authorization: Bearer <token>" \
  https://<databricks-host>/api/2.0/clusters/list
```

**Expected**: 200 OK response (even if empty cluster list)
**If Failure**: 401 Unauthorized indicates invalid/expired token

#### Fix Bearer Token Issues

**Generate New Token**:
1. Databricks UI → Settings → User Settings → Access Tokens
2. Generate new token
3. Update integration:

```sql
ALTER CATALOG INTEGRATION <integration_name>
  SET BEARER_TOKEN = '<new_token>';
```

**Best Practice**: Set reminder to rotate token before expiration (e.g., every 60 days for 90-day tokens)

---

### 3. Unity Catalog Privilege Issues

**Error Pattern**:
```
Catalog not found
Permission denied
Forbidden
403 Forbidden
```

**Common Causes**:
- Service principal/user lacks Unity Catalog privileges
- Catalog doesn't exist
- Missing `USE CATALOG` or `USE SCHEMA` grants

#### Debug Privileges

**Check in Databricks SQL Editor**:
```sql
-- As admin, check grants for service principal
SHOW GRANTS ON CATALOG <catalog_name>;
SHOW GRANTS ON SCHEMA <catalog_name>.<schema_name>;
```

**Required Privileges**:
- `USE CATALOG` on catalog
- `USE SCHEMA` on schemas
- `SELECT` on tables

#### Fix Privilege Issues

**Grant Required Privileges** (as Unity Catalog admin):
```sql
-- Grant catalog access
GRANT USE CATALOG ON CATALOG <catalog_name> 
  TO SERVICE_PRINCIPAL `<service_principal_id>`;

-- Grant schema access
GRANT USE SCHEMA ON SCHEMA <catalog_name>.<schema_name>
  TO SERVICE_PRINCIPAL `<service_principal_id>`;

-- Grant table access
GRANT SELECT ON SCHEMA <catalog_name>.<schema_name>
  TO SERVICE_PRINCIPAL `<service_principal_id>`;
```

**For PAT/User**:
```sql
GRANT USE CATALOG ON CATALOG <catalog_name> TO `<user_email>`;
GRANT USE SCHEMA ON SCHEMA <catalog_name>.<schema_name> TO `<user_email>`;
GRANT SELECT ON SCHEMA <catalog_name>.<schema_name> TO `<user_email>`;
```

---

### 4. Catalog Not Found

**Error Pattern**:
```
Catalog '<catalog_name>' not found
Unable to access catalog
```

**Solutions**:

1. **Verify Catalog Exists in Unity Catalog**:
   ```sql
   -- In Databricks SQL Editor
   SHOW CATALOGS;
   ```

2. **Check Catalog Name Spelling**:
   - Case-sensitive in Unity Catalog
   - Common names: `main`, `hive_metastore` (legacy)

3. **Recreate Integration if Name Incorrect**:
   
   Since REST_CONFIG cannot be altered, recreate the integration:
   ```sql
   DROP CATALOG INTEGRATION <integration_name>;
   CREATE CATALOG INTEGRATION <integration_name> ...;
   ```

---

### 5. Network Connectivity Issues

**Error Pattern**:
```
Connection timeout
Failed to connect to catalog
Could not reach Unity Catalog endpoint
```

#### For Public Connectivity

**Verify URL Format**: 
```
Correct: https://<workspace-host>/api/2.1/unity-catalog/iceberg-rest
Example: https://dbc-b6a22903-2e25.cloud.databricks.com/api/2.1/unity-catalog/iceberg-rest
```

**Test Reachability**:
```bash
curl -I https://<databricks-host>/api/2.1/unity-catalog/iceberg-rest
```

**Solutions**:
1. Verify Databricks workspace host is correct
2. Check Snowflake network policies don't block Databricks domain
3. Ensure workspace is accessible from public internet

#### For Private Connectivity (PrivateLink)

**Requirements**:
- Snowflake Business Critical edition (or higher)
- AWS PrivateLink (for Databricks on AWS) or Azure Private Link (for Azure Databricks)
- PrivateLink endpoint provisioned in Snowflake and registered/approved in Databricks
- `CATALOG_API_TYPE = 'PRIVATE'` set in the catalog integration

**Verify PrivateLink Configuration**:

1. Check PrivateLink endpoint exists and is available:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```
   Look for an entry where the host matches your Databricks workspace host and status is `"available"`.

2. Verify the catalog integration uses `CATALOG_API_TYPE = 'PRIVATE'`:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```

3. **For AWS**: Verify the Snowflake VPC endpoint is registered in the Databricks account console and a private access setting is attached.

4. **For Azure**: Verify the private endpoint connection is approved in Azure Portal → Databricks workspace → Networking → Private endpoint connections.

**If connectivity type needs to change**, recreate the integration with correct settings (REST_CONFIG cannot be altered).

---

### 6. External Volume Issues

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

2. **Check Storage Location Matches Unity Catalog**:
   - Unity Catalog stores data in configured cloud storage
   - External volume must point to same location
   - Check metastore storage configuration in Unity Catalog

3. **Validate Cloud Permissions**:
   
   **AWS S3**:
   - IAM role needs `s3:GetObject`, `s3:GetObjectVersion`, `s3:ListBucket`
   - Trust relationship configured for Snowflake external ID
   - Bucket policy allows access
   
   **Azure ADLS**:
   - Storage account has read permissions
   - Proper role assignments configured
   
   **GCS**:
   - Service account has storage permissions
   - IAM bindings configured correctly

4. **Consider Vended Credentials** (Alternative):
   - Requires recreating integration with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`
   - Unity Catalog generates temporary credentials for Snowflake
   - Works with catalog-server PrivateLink; to also route storage over PrivateLink, set `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` (see the "Vended credentials with private connectivity to storage" section in SKILL.md)

---

### 7. Namespace/Table Discovery Issues

**Error Pattern**:
```
No namespaces found
Tables not visible
Empty result from LIST operations
```

**Solutions**:

1. **Verify Tables Exist in Unity Catalog**:
   ```sql
   -- In Databricks SQL Editor
   SHOW SCHEMAS IN CATALOG <catalog_name>;
   SHOW TABLES IN <catalog_name>.<schema_name>;
   ```

2. **Check Table Format**:
   - Unity Catalog must have **Iceberg tables**
   - Delta Lake tables won't be visible through Iceberg REST API
   - Check table type: `DESCRIBE TABLE EXTENDED <table_name>`

3. **Verify Privileges**:
   - Service principal needs `USE SCHEMA` on schema
   - Service principal needs `SELECT` on tables
   - Grant privileges as shown in section 3

4. **Case Sensitivity**:
   - Schema names are case-sensitive
   - Use exact spelling from Unity Catalog
   - List all namespaces first:
     ```sql
     SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
     ```

---

### 8. Table Query Failures

**Error Pattern**:
```
Table not found
Cannot read Iceberg metadata
Metadata file not accessible
```

**Solutions**:

1. **Verify Table is Iceberg Format**:
   ```sql
   -- In Databricks
   DESCRIBE TABLE EXTENDED <catalog>.<schema>.<table>;
   ```
   Look for `Provider: iceberg` or `Type: ICEBERG`

2. **Check Metadata Access**:
   - External volume must access metadata files
   - Metadata location in Unity Catalog storage
   - Verify IAM permissions for metadata paths

3. **Refresh Metadata** (for catalog-linked databases):
   ```sql
   ALTER DATABASE <database_name> REFRESH;
   ```

---

### 9. PrivateLink Endpoint Not Available

**Error Pattern**:
```
Execution Error: Private endpoint corresponding to service name ... does not exist.
```

**Cause**: PrivateLink endpoint was not provisioned or is not yet available.

**Debug Steps**:

1. Check PrivateLink endpoint status:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```
   Look for:
   - `"status": "available"` for your Databricks workspace host

2. If endpoint doesn't exist, provision it:

   **For AWS** (consider using `*.cloud.databricks.com` as hostname to cover multiple workspaces in the same region):
   ```sql
   USE ROLE ACCOUNTADMIN;
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
     '<vpc_endpoint_service_id>',
     '<databricks_workspace_host_name>'
   );
   ```

   **For Azure** (consider using `*.*.azuredatabricks.net` as hostname to cover multiple workspaces in the same region):
   ```sql
   USE ROLE ACCOUNTADMIN;
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
     '<databricks_workspace_resource_id>',
     '<databricks_workspace_host_name>',
     'databricks_ui_api'
   );
   ```

**Solutions**:
- Provision endpoint if missing
- Wait a few minutes for status to transition to "available"
- Verify ACCOUNTADMIN role was used for provisioning

---

### 10. PrivateLink Endpoint Limit Exceeded

**Error Pattern**:
```
The account cannot create more than 5 private endpoints. Please contact Snowflake support for help.
```

**Cause**: Snowflake accounts are limited to a **maximum of 5 private endpoints**. Deprovisioned endpoints still count toward this limit for 7 days after removal.

**Debug Steps**:

1. Check current endpoints:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```

2. Count active and recently deprovisioned endpoints

**Solutions**:
- Remove unused PrivateLink endpoints to free up slots (note: deprovisioned endpoints count toward the limit for 7 days)
- You cannot have more than one endpoint to the same service
- To increase the 5-endpoint limit, contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge)

> **Reference**: [Private connectivity for outbound network traffic — Scaling considerations](https://docs.snowflake.com/en/user-guide/private-connectivity-outbound)

---

### 11. PrivateLink Endpoint Already Exists

**Error Pattern**:
```
Error executing SQL: Private endpoint for resource ... already exists
```

**Cause**: A PrivateLink endpoint for this VPC endpoint service (AWS) or resource (Azure) has already been provisioned. This can mean one of two things — the endpoint is correct and ready to use, or it exists but is mapped to the wrong workspace hostname.

**Debug Steps**:

1. Check the existing endpoint:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```

2. Find the entry matching your `"provider_service_name"` (AWS) or `"provider_resource_id"` (Azure) and inspect the `"host"` value.

3. **Determine which case applies**:

#### Case A: Hostname matches your intended workspace

The endpoint already exists and is correctly configured. **No action needed.**

- Verify `"status"` is `"available"` (AWS) or `"APPROVED"` (Azure)
- If status is healthy, proceed with creating the catalog integration
- If status is not healthy, see [Issue #9: PrivateLink Endpoint Not Available](#9-privatelink-endpoint-not-available)

#### Case B: Hostname does NOT match your intended workspace

The endpoint exists but is mapped to a different Databricks workspace hostname. This commonly happens when:
- The workspace URL was entered incorrectly during initial provisioning
- A workspace was migrated or renamed

**Solution**: Use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME` to update the hostname on the existing endpoint **without deprovisioning**:

**For AWS**:
```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<vpc_endpoint_service_id>',           -- e.g. com.amazonaws.vpce.us-west-2.vpce-svc-0129f463fcfbc46c5
  '<correct_workspace_host_name>'        -- e.g. dbc-b6a22903-2e25.cloud.databricks.com
);
```

**For Azure**:
```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<databricks_workspace_resource_id>',  -- Azure resource ID of the Databricks workspace
  '<correct_workspace_host_name>'        -- e.g. adb-1234567890123456.12.azuredatabricks.net
);
```

**Verify** the hostname was updated:
```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

#### Case C: Hostname matches an existing workspace, but you need to add another workspace in the same region

The endpoint is already provisioned for one workspace, and now you're trying to provision a new endpoint for a second workspace in the same region. Since all Databricks workspaces in the same region share the same PrivateLink service, provisioning a second endpoint for the same service will hit this error.

**Solution**: Update the existing endpoint's hostname to a wildcard so it covers all workspaces in that region:

**For AWS**:
```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<vpc_endpoint_service_id>',
  '*.cloud.databricks.com'
);
```

**For Azure**:
```sql
USE ROLE ACCOUNTADMIN;

SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<databricks_workspace_resource_id>',
  '*.*.azuredatabricks.net'
);
```

**Verify** the hostname was updated:
```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

Once the wildcard is in place, the single endpoint serves all workspaces in that region — no additional endpoints needed.

> **Important**: Do NOT deprovision and re-provision the endpoint to fix a hostname mismatch. Deprovisioned endpoints count toward the 5-endpoint limit for 7 days. Use `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME` instead.

---

### 12. PrivateLink Endpoint Not Registered in Databricks (AWS)

**Error Pattern**:
```
Connection timeout via PrivateLink
Databricks rejecting connection from Snowflake
```

**Cause**: On AWS, after provisioning the PrivateLink endpoint in Snowflake, you must register the Snowflake VPC endpoint ID in the Databricks account console and configure a private access setting.

**Debug Steps**:

1. Verify the Snowflake VPC endpoint ID:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```
   Note the `"snowflake_endpoint_name"` value (e.g., `vpce-11111aaaa11aaaa11`).

2. Check in Databricks account console:
   - Go to Cloud Resources → VPC endpoint registrations
   - Verify the Snowflake VPC endpoint ID is registered
   - Verify a private access setting is attached with this endpoint

**Solutions**:
1. Register the Snowflake VPC endpoint in Databricks account console → VPC endpoint registrations
2. Create or update a private access setting to include the registered endpoint
3. Ensure the Databricks workspace is in a customer-managed VPC with enterprise subscription

> **Reference**: [Configure Front-end PrivateLink (Databricks)](https://docs.databricks.com/en/security/network/classic/privatelink.html)

---

### 13. PrivateLink Endpoint Not Approved in Azure Portal

**Error Pattern**:
```
Connection timeout via Private Link
Azure Databricks rejecting connection from Snowflake
Private endpoint connection pending approval
```

**Cause**: On Azure, after provisioning the private endpoint in Snowflake, you must approve the private endpoint connection in the Azure Portal for the Databricks workspace.

**Debug Steps**:

1. Verify the Snowflake private endpoint resource ID:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```
   Note the `"snowflake_resource_id"` value.

2. Check in Azure Portal:
   - Navigate to your Databricks workspace
   - Go to Networking → Private endpoint connections
   - Look for a pending connection matching the Snowflake resource ID

**Solutions**:
1. In Azure Portal → Databricks workspace → Networking → Private endpoint connections
2. Find the row matching the Snowflake `snowflake_resource_id` value
3. Select and click "Approve"
4. Wait for the connection state to change to "Approved"

---

### 14. Unity Catalog Classic: Storage Access Denied via Snowflake

**Symptom**: Queries via a vended-credentials integration with `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` fail with S3 `Access Denied` after blocking public storage access.

**Cause**: Databricks control-plane VPC IDs (Classic compute) are not included in the `aws:SourceVpc` allowlist in the S3 bucket policy. When public access is blocked, only traffic from explicitly allowlisted VPCs/VPCEs is permitted.

**Solution**:
1. Retrieve Databricks control-plane VPC IDs for your AWS region from the [Databricks IP addresses and domains](https://docs.databricks.com/en/resources/ip-domain-region.html) doc.
2. Add each VPC ID to the `aws:SourceVpc` condition in the S3 bucket policy alongside the Snowflake VPCE:
   ```json
   "aws:SourceVpc": ["<databricks-control-plane-vpc-id>"]
   ```
3. Re-run the end-to-end probe: `SELECT * FROM <iceberg_table> LIMIT 1;`

---

### 15. Unity Catalog Serverless: Storage Firewall Denying Databricks NAT IPs

**Symptom**: Queries via a vended-credentials integration on Azure fail after enabling `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` and restricting the storage firewall.

**Cause**: Azure Storage firewall is blocking Databricks control-plane NAT IPs used by Serverless compute. These NAT IPs are not within a VNet and cannot be covered by a service endpoint rule.

**Solution**:
1. Retrieve Databricks control-plane NAT IPs for your Azure region from the [Databricks IP addresses and domains](https://docs.databricks.com/en/resources/ip-domain-region.html) doc.
2. In Azure Portal → Storage account → **Networking → Firewalls and virtual networks**, add each NAT IP to the **Firewall** IP allowlist.
3. Re-run the end-to-end probe: `SELECT * FROM <iceberg_table> LIMIT 1;`

---

### 16. Shared storage-PrivateLink issues (ADLS Gen2 dfs, region mismatch, Azure pending)

For catalog-agnostic storage-PrivateLink issues — **ADLS Gen2 `dfs` endpoint unresolvable** (provision a separate `dfs` sub-resource endpoint in addition to `blob`), **region mismatch**, **storage endpoint pending**, and **Azure private endpoint approval** — see the shared troubleshooting reference: [shared/vended-credentials-private-storage/references/troubleshooting.md](../../shared/vended-credentials-private-storage/references/troubleshooting.md). Issues #14 and #15 above cover the Unity-Catalog-specific control-plane VPC / NAT allowlisting.

---

## Diagnostic Workflow

Follow this sequence when troubleshooting:

1. **Check Integration Status**:
   ```sql
   SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';
   DESC CATALOG INTEGRATION <integration_name>;
   ```

2. **Test Connection**:
   ```sql
   SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
   ```

3. **Check PrivateLink Status** (if using private connectivity):
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   -- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
   ```

4. **Review Snowflake Query History**:
   ```sql
   SELECT * FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY())
   WHERE QUERY_TEXT ILIKE '%<integration_name>%'
   ORDER BY START_TIME DESC LIMIT 10;
   ```

5. **Check Unity Catalog Audit Logs** (in Databricks):
   - System Tables → Audit Logs
   - Look for failed authentication or authorization events

6. **Test Authentication Separately** (OAuth or Bearer token methods above)

---

## PrivateLink Diagnostic Commands

**Check all PrivateLink endpoints**:
```sql
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
-- Alternative: SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;
```

**Provision a new PrivateLink endpoint** (ACCOUNTADMIN required):

For AWS (consider using `*.cloud.databricks.com` as hostname to cover multiple workspaces in the same region):
```sql
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<vpc_endpoint_service_id>',
  '<databricks_workspace_host_name>'
);
```

For Azure (consider using `*.*.azuredatabricks.net` as hostname to cover multiple workspaces in the same region):
```sql
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  '<databricks_workspace_resource_id>',
  '<databricks_workspace_host_name>',
  'databricks_ui_api'
);
```

**Remove a PrivateLink endpoint** (ACCOUNTADMIN required):
```sql
-- Queued for deletion after 7 days
SELECT SYSTEM$DEPROVISION_PRIVATELINK_ENDPOINT(
  '<provider_service_name_or_resource_id>'
);
```

**Update hostname on an existing PrivateLink endpoint** (ACCOUNTADMIN required):
```sql
-- Use this when an endpoint exists but is mapped to the wrong workspace hostname
-- This avoids deprovisioning (which counts toward the 5-endpoint limit for 7 days)
SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  '<provider_service_name_or_resource_id>',
  '<correct_host_name>'
);
```

**Restore a recently removed endpoint** (within 7-day deletion queue):
```sql
SELECT SYSTEM$RESTORE_PRIVATELINK_ENDPOINT(
  '<provider_service_name_or_resource_id>'
);
```

> **Reference**: [Manage private connectivity endpoints](https://docs.snowflake.com/en/user-guide/private-manage-endpoints-aws)

---

## Getting Additional Help

**Documentation Resources**:
- [Unity Catalog Integration](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-unity)
- [Configure Catalog Integration with Outbound Private Connectivity (PrivateLink)](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-private)
- [Iceberg REST Catalog Troubleshooting](https://docs.snowflake.com/user-guide/tables-iceberg-configure-catalog-integration-rest-check-config)
- [Unity Catalog Privileges](https://docs.databricks.com/en/data-governance/unity-catalog/manage-privileges/index.html)
- [Databricks Service Principals](https://docs.databricks.com/en/admin/users-groups/service-principals.html)
- [ALTER CATALOG INTEGRATION](https://docs.snowflake.com/en/sql-reference/sql/alter-catalog-integration)
- [Databricks PrivateLink (AWS)](https://docs.databricks.com/en/security/network/classic/privatelink.html)
- [Databricks PrivateLink VPC Endpoint Service IDs by Region (AWS)](https://docs.databricks.com/aws/en/resources/ip-domain-region#privatelink)
- [Azure Databricks Private Link](https://learn.microsoft.com/en-us/azure/databricks/security/network/classic/private-link-standard)

**Common Resolution Paths**:
- OAuth secret changed → Use ALTER to update secret
- Bearer token expired → Use ALTER to update token
- OAuth client ID or config changed → Recreate integration
- Privileges → Grant Unity Catalog access in Databricks
- Network → Check connectivity and URL format
- External volume → Validate cloud permissions and storage paths
- Discovery → Ensure tables are Iceberg format, check privileges
- PrivateLink endpoint missing → Provision via `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT()`
- PrivateLink not registered (AWS) → Register VPC endpoint in Databricks account console
- PrivateLink not approved (Azure) → Approve in Azure Portal → Databricks → Networking
- PrivateLink endpoint wrong hostname → Update via `SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME()` (do NOT deprovision)
