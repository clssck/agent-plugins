# Troubleshooting AWS Glue IRC Catalog Integration

Comprehensive guide for diagnosing and fixing issues with AWS Glue Iceberg REST catalog integrations.

## When to Load

Load this reference when:
- `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns failure
- Namespace or table discovery fails
- Trust relationship or IAM authentication errors occur
- Unexpected behavior during verification

## Important: ALTER CATALOG INTEGRATION Limitations

**Only these parameters can be altered:**
```sql
ALTER CATALOG INTEGRATION <name> SET
  REFRESH_INTERVAL_SECONDS = <seconds>;
```

**REST_CONFIG cannot be altered.**

**REST_AUTHENTICATION** can only be altered for **secret rotation** — specifically, the OAuth secret or bearer token. Other REST_AUTHENTICATION parameters (e.g., `SIGV4_IAM_ROLE`, `SIGV4_SIGNING_REGION`) cannot be changed via ALTER.

> Note: For Glue IRC (SigV4 authentication), there is no secret to rotate via ALTER.
> The IAM role credentials are managed through AWS trust relationships.

If you need to change IAM role, region, catalog URI, or access delegation mode, you must **recreate the integration**:
```sql
DROP CATALOG INTEGRATION <integration_name>;
CREATE CATALOG INTEGRATION <integration_name> ...;
```

> **Note**: Recreating the integration generates a new auto-generated external ID (requiring AWS trust policy update) unless you specify your own `SIGV4_EXTERNAL_ID` — in which case the external ID remains the same.

---

## Common Issues

### 1. Trust Relationship Not Configured

**Error Pattern**: 
```
User: <arn> is not authorized to perform: sts:AssumeRole on resource: <role_arn>
Failed to assume role
```

**Example** (from `SYSTEM$VERIFY_CATALOG_INTEGRATION`):
```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```
```
Error assuming AWS_ROLE:
User: arn:aws:iam::<snowflake_account_num>:user/<snowflake_user> is not authorized
to perform: sts:AssumeRole on resource: arn:aws:iam::<aws_account_id>:role/<role_name>
```

**Cause**: AWS IAM role trust policy doesn't allow Snowflake IAM user to assume the role.

**Debug Steps**:

1. Retrieve the Snowflake IAM user ARN from the integration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Extract: `GLUE_AWS_IAM_USER_ARN` and `GLUE_AWS_EXTERNAL_ID`

2. Verify trust policy exists:
   - AWS Console → IAM → Roles → Your Role → Trust relationships

3. Update the trust policy to allow Snowflake's IAM user to assume the role:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "AWS": [
              "<GLUE_AWS_IAM_USER_ARN>"
           ]
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
   ```

4. Verify trust policy matches:
   - Principal.AWS includes the `GLUE_AWS_IAM_USER_ARN` value (exact match)
   - Condition.StringEquals.sts:ExternalId = `GLUE_AWS_EXTERNAL_ID` (exact match)

> **Note**: If the integration uses multiple IAM roles (e.g., one for catalog access and one for SigV4 API signing), ensure the trust policy is updated on **each** role referenced in the integration.

**Solutions**:
- Add trust policy if missing
- Update values if mismatched
- Check for typos, extra spaces, or line breaks
- Ensure editing correct IAM role (matches SIGV4_IAM_ROLE in integration)

---

### 2. External ID Mismatch

**Error Pattern**:
```
ExternalId in the request does not match the expected value
Access denied
```

**Cause**: External ID in AWS trust policy doesn't match the external ID associated with the catalog integration.

**Common Scenarios**:
- Integration was recreated with `CREATE OR REPLACE` without specifying `SIGV4_EXTERNAL_ID`, causing Snowflake to generate a new external ID
- Trust policy copied from old integration
- Manual typo in trust policy
- Customer-provided `SIGV4_EXTERNAL_ID` doesn't match the value in the trust policy

**Solution**:

1. Get current external ID:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   
2. Update AWS trust policy with the `GLUE_AWS_EXTERNAL_ID` value from the output

3. Verify update in AWS Console

**Tip**: To avoid this issue when frequently recreating integrations (e.g., during testing), specify your own `SIGV4_EXTERNAL_ID` in the `CREATE CATALOG INTEGRATION` statement. This keeps the external ID stable across recreations, so the trust policy does not need to be updated each time.

**Security Note**: By default, each catalog integration gets a unique auto-generated external ID. `CREATE OR REPLACE` generates a new external ID and breaks the trust relationship until updated. Using a custom `SIGV4_EXTERNAL_ID` avoids this but means the same external ID may be shared across integrations.

---

### 3. IAM Policy Missing Permissions

**Error Pattern**:
```
Access Denied
User: <arn> is not authorized to perform: glue:GetDatabase
```

**Cause**: IAM role lacks required Glue permissions.

**Required Permissions** (minimum for read-only):
```json
{
  "Effect": "Allow",
  "Action": [
    "glue:GetCatalog",
    "glue:GetDatabase",
    "glue:GetDatabases",
    "glue:GetTable",
    "glue:GetTables"
  ],
  "Resource": [
    "arn:aws:glue:*:<account_id>:catalog",
    "arn:aws:glue:*:<account_id>:database/*",
    "arn:aws:glue:*:<account_id>:table/*/*"
  ]
}
```

**Debug Steps**:

1. Check IAM role policies:
   - AWS Console → IAM → Roles → Your Role → Permissions
   
2. Verify policy includes required actions

3. Check resource restrictions (wildcards vs specific databases)

**Solutions**:
- Add missing permissions to IAM policy
- Broaden resource scope if too restrictive
- For write access, add: `CreateTable`, `UpdateTable`, `DeleteTable`, `CreateDatabase`, `DeleteDatabase`
- For S3 data access (read-write), add: `s3:GetObject`, `s3:PutObject` on table locations

---

### 4. Lake Formation Access Denied

**Error Pattern**:
```
Access denied by Lake Formation
Insufficient permissions to access database/table
```

**Cause**: AWS Lake Formation is enabled and IAM role lacks Lake Formation data permissions.

**Debug Steps**:

1. Check if Lake Formation is enabled:
   - AWS Console → Lake Formation → Data catalog settings
   
2. Verify IAM role has `lakeformation:GetDataAccess` permission:
   ```json
   {
     "Effect": "Allow",
     "Action": "lakeformation:GetDataAccess",
     "Resource": "*"
   }
   ```

3. Check Lake Formation data permissions:
   - AWS Console → Lake Formation → Permissions → Data permissions
   - Verify IAM role has grants for databases, tables, columns

**Solutions**:
- Add `lakeformation:GetDataAccess` to IAM policy
- Grant Lake Formation data permissions to IAM role:
  - Database-level: Describe database
  - Table-level: Select, Describe table
  - Column-level: Select on specific columns (if using column-level security)
- Use AWS CLI:
  ```bash
  aws lakeformation grant-permissions \
    --principal DataLakePrincipalIdentifier=<iam_role_arn> \
    --resource '{"Table":{"DatabaseName":"<db>","Name":"<table>"}}' \
    --permissions SELECT DESCRIBE
  ```

**Note**: Lake Formation takes precedence over IAM policies. Both must grant access.

**For Lake Formation setup help**: See [Snowflake + AWS Glue Guide](https://www.snowflake.com/en/developers/guides/data-lake-using-apache-iceberg-with-snowflake-and-aws-glue/)

---

### 5. Database/Table Not Found

**Error Pattern**:
```
Database '<name>' not found
Table '<name>' not found
```

**Causes**:
- Database/table name is case-sensitive
- IAM policy resource scope excludes the database/table
- Database/table doesn't exist in Glue Data Catalog

**Debug Steps**:

1. Check exact database name in Glue:
   - AWS Console → Glue → Databases
   
2. Verify case-sensitive match:
   ```sql
   SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
   ```

3. Check IAM policy resource scope:
   ```json
   "Resource": [
     "arn:aws:glue:*:<account>:database/<specific_db>",  // Too restrictive?
     "arn:aws:glue:*:<account>:database/*"                // Better for discovery
   ]
   ```

**Solutions**:
- Use exact casing from Glue Data Catalog
- Broaden IAM policy resource scope for discovery
- Verify database/table exists in Glue Console

---

### 6. Region Mismatch

**Error Pattern**:
```
Connection timeout
Unable to reach catalog endpoint
SignatureDoesNotMatch
```

**Cause**: SIGV4_SIGNING_REGION doesn't match the region where Glue Data Catalog resides.

**Debug Steps**:

1. Check integration configuration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Look for: `SIGV4_SIGNING_REGION` in REST_AUTHENTICATION

2. Verify Glue region:
   - Check CATALOG_URI: `https://glue.<region>.amazonaws.com/iceberg`
   - Ensure regions match

**Solution**:

Since REST_AUTHENTICATION cannot be altered, you must **recreate the integration** with the correct region:

```sql
DROP CATALOG INTEGRATION <integration_name>;

CREATE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://glue.<correct_region>.amazonaws.com/iceberg'
    CATALOG_API_TYPE = AWS_GLUE
    CATALOG_NAME = '<glue_catalog_name>'
    ACCESS_DELEGATION_MODE = <VENDED_CREDENTIALS|EXTERNAL_VOLUME_CREDENTIALS>
  )
  REST_AUTHENTICATION = (
    TYPE = SIGV4
    SIGV4_IAM_ROLE = '<iam_role_arn>'
    SIGV4_SIGNING_REGION = '<correct_region>'
  )
  ENABLED = TRUE;
```

> **Note**: After recreating, update AWS trust policy with the new external ID.

---

### 7. PrivateLink Endpoint Not Available

**Error Pattern**:
```
Execution Error: Private endpoint corresponding to service name ... does not exist.
```

**Cause**: PrivateLink endpoint was not provisioned or is not yet available.

**Debug Steps**:

1. Check PrivateLink endpoint status:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   ```
   Look for:
   - `"endpoint_state": "CREATED"`
   - `"status": "available"` for host `glue.<region>.amazonaws.com`

2. If endpoint doesn't exist:
   ```sql
   USE ROLE ACCOUNTADMIN;
   SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
     'com.amazonaws.<region>.glue',
     'glue.<region>.amazonaws.com'
   );
   ```

**Solutions**:
- Provision endpoint if missing
- Wait a few minutes for status to transition to "available"
- Verify ACCOUNTADMIN role was used for provisioning

---

### 8. PrivateLink Endpoint Limit Exceeded

**Error Pattern**:
```
The account cannot create more than 5 private endpoints. Please contact Snowflake support for help.
```

**Cause**: Snowflake accounts are limited to a **maximum of 5 private endpoints**. Deprovisioned endpoints still count toward this limit for 7 days after removal.

**Debug Steps**:

1. Check current endpoints:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   ```

2. Count active and recently deprovisioned endpoints

**Solutions**:
- Remove unused PrivateLink endpoints to free up slots (note: deprovisioned endpoints count toward the limit for 7 days)
- You only need **one** Glue PrivateLink endpoint per region — it serves all Glue catalogs in that region. Do not create duplicate endpoints for the same service.
- You cannot have more than one endpoint to the same AWS service (e.g., one Glue endpoint per account)
- To increase the 5-endpoint limit, contact [Snowflake Support](https://community.snowflake.com/s/article/How-To-Submit-a-Support-Case-in-Snowflake-Lodge)

> **Reference**: [Private connectivity for outbound network traffic — Scaling considerations](https://docs.snowflake.com/en/user-guide/private-connectivity-outbound)

---

### 9. PrivateLink Endpoint Already Exists

**Error Pattern**:
```
Error executing SQL: Private endpoint for resource com.amazonaws.<region>.glue already exists
```

Example (us-west-2):
```
Error executing SQL: Private endpoint for resource com.amazonaws.us-west-2.glue already exists
```

**Cause**: A PrivateLink endpoint for the Glue service in this region has already been provisioned. You only need **one** Glue PrivateLink endpoint per region — it serves all Glue catalogs in that region.

**Debug Steps**:

1. Confirm the existing endpoint is available:
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   ```
   Look for an entry with:
   - `"host"` matching `glue.<region>.amazonaws.com`
   - `"status": "available"`

2. If the endpoint exists and status is "available", **no action needed** — proceed with creating the catalog integration.

**Solutions**:
- This is **not an error that needs fixing**. The endpoint already exists and is ready to use.
- Run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` to verify the endpoint is healthy, then continue with the catalog integration creation step.
- If the endpoint shows a non-healthy status (e.g., not "available"), see [Issue #7: PrivateLink Endpoint Not Available](#7-privatelink-endpoint-not-available).

---

### 10. Existing Workloads Fail After Provisioning PrivateLink Endpoint

**Applies to** `CATALOG_API_TYPE = AWS_PRIVATE_API_GATEWAY` only. This issue does not affect other catalog integration types.

**Error Pattern**:
Queries against Iceberg tables that previously worked with an existing `AWS_PRIVATE_API_GATEWAY` catalog integration begin failing after `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT()` is called. Errors may include access denied, timeout, or connectivity failures from the Glue API.

**Cause**: Before a PrivateLink endpoint is explicitly provisioned, Snowflake uses a default VPC endpoint to reach AWS services. Calling `SYSTEM$PROVISION_PRIVATELINK_ENDPOINT()` creates a new, dedicated endpoint that **overrides** the default. If the customer followed the [AWS documentation for REST API resource policies](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-resource-policies-create-attach.html#apigateway-resource-policies-create-attach-console) and configured a resource policy that restricts access based on the original default VPC endpoint — such as an `aws:sourceVpc` condition — then the new provisioned endpoint will not match that condition, causing requests to be denied.

**Debug Steps**:

1. Retrieve the default Snowflake platform VPC information:
   ```sql
   SELECT SYSTEM$GET_SNOWFLAKE_PLATFORM_INFO();
   ```
   This returns the default Snowflake VPC ID — the shared VPC endpoint that was in use before a dedicated PrivateLink endpoint was provisioned.

2. Check if a PrivateLink endpoint was recently provisioned (this is the new endpoint that overrides the default):
   ```sql
   SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();
   ```

3. Check if the customer's AWS API Gateway resource policy contains a VPC-based condition. Look for a policy with:
   ```json
   "Condition": {
     "StringEquals": {
       "aws:sourceVpc": "<snowflake_vpc_id>"
     }
   }
   ```
   If the `<snowflake_vpc_id>` value matches the default VPC from Step 1 (not the newly provisioned endpoint from Step 2), this is the cause of the failure.

4. Confirm the catalog integration uses `AWS_PRIVATE_API_GATEWAY`:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```

**Solutions**:
- Update the AWS API Gateway resource policy to accept the **newly provisioned private endpoint** instead of (or in addition to) the old default VPC endpoint. The new endpoint information can be found in the output of `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()`.
- Review and update all relevant policies (API Gateway resource policies, IAM policies, S3 bucket policies) that reference `aws:sourceVpc` or `aws:sourceVpce` to include the new endpoint.
- Refer to the API Gateway catalog integration documentation for the full configuration guidance, including how to set up resource policies correctly.

> **References**:
> - [Configure a catalog integration for AWS Glue with API Gateway](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-api-gateway)
> - [AWS: Create and attach API Gateway resource policies](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-resource-policies-create-attach.html#apigateway-resource-policies-create-attach-console)

### 11. Cross-Region PrivateLink Not Supported

**Error Pattern**:
```
Invalid service name "com.amazonaws.<region_a>.glue" and hostname "glue.<region_b>.amazonaws.com".
```

**Cause**: AWS does not support cross-region PrivateLink provisioning for the Glue service. The Snowflake account and the Glue Data Catalog must be in the **same AWS region** when using PrivateLink connectivity. This is an AWS-side limitation, not a Snowflake limitation.

**Debug Steps**:

1. Confirm Snowflake account region:
   ```sql
   SELECT CURRENT_REGION();
   ```

2. Compare with the target Glue Data Catalog region (from the `CATALOG_URI` or `SIGV4_SIGNING_REGION`).

3. If regions differ, PrivateLink cannot be used.

**Solutions**:
- **Option A**: Use **Public connectivity** (`CATALOG_API_TYPE = AWS_GLUE`) instead of PrivateLink. Public connectivity works across regions.
- **Option B**: Use a Snowflake account that is in the **same AWS region** as the Glue Data Catalog.
- **Option C**: Create a Glue Data Catalog in the **same region** as the Snowflake account.

> **Reference**: [AWS services that support cross-region PrivateLink](https://docs.aws.amazon.com/vpc/latest/privatelink/aws-services-cross-region-privatelink-support.html) — Glue is not listed as supporting cross-region PrivateLink.

---

## Diagnostic Commands

**Check integration status**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';
DESC CATALOG INTEGRATION <integration_name>;
```

**Test connection**:
```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

**List namespaces**:
```sql
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
```

**List tables**:
```sql
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<database_name>');
```

**PrivateLink diagnostics**:
```sql
-- Check all PrivateLink endpoints
SELECT SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO();

-- Alternative: query the Account Usage view
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS;

-- Provision a new PrivateLink endpoint (ACCOUNTADMIN required)
USE ROLE ACCOUNTADMIN;
SELECT SYSTEM$PROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.glue',
  'glue.<region>.amazonaws.com'
);
```

**PrivateLink endpoint management** (ACCOUNTADMIN required):
```sql
-- Remove a PrivateLink endpoint (queued for deletion after 7 days)
SELECT SYSTEM$DEPROVISION_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.glue'
);

-- Restore a recently removed endpoint (within 7-day deletion queue)
SELECT SYSTEM$RESTORE_PRIVATELINK_ENDPOINT(
  'com.amazonaws.<region>.glue'
);

-- Change the host name of an existing endpoint (without changing its network resource)
SELECT SYSTEM$SET_PRIVATELINK_ENDPOINT_HOSTNAME(
  'com.amazonaws.<region>.glue',
  '<new_host_name>'
);
```

> **Reference**: [Manage private connectivity endpoints: AWS](https://docs.snowflake.com/en/user-guide/private-manage-endpoints-aws)

**AWS CLI diagnostics**:
```bash
# Verify IAM role trust policy
aws iam get-role --role-name <role_name>

# List Glue databases
aws glue get-databases --catalog-id <account_id> --region <region>

# List tables in database
aws glue get-tables --database-name <db_name> --region <region>

# Test assume role
aws sts assume-role --role-arn <role_arn> --role-session-name test --external-id <external_id>
```

## General Troubleshooting Tips

1. **Start with trust relationship**: Most issues are trust policy or external ID mismatches
2. **Check IAM permissions**: Verify both IAM policies and Lake Formation grants
3. **Verify regions match**: Signing region = Glue region
4. **Use exact casing**: Glue database/table names are case-sensitive
5. **Check AWS CloudTrail**: See detailed logs of AssumeRole and Glue API calls
6. **Test with AWS CLI**: Validate IAM role can access Glue independently
7. **Recreate if config changes needed**: `REST_CONFIG` cannot be altered; `REST_AUTHENTICATION` can only be altered for OAuth secret or bearer token rotation
8. **PrivateLink**: Verify endpoint is "available" via `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` before creating the integration

---

## Storage PrivateLink troubleshooting (vended credentials)

> Applies only when `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` and `DEFAULT_STORAGE_CONFIG = (USE_PRIVATELINK_ENDPOINT = TRUE)` are set.

### Glue loses access after locking down the bucket

**Symptom**: After applying an S3 bucket policy that denies non-Snowflake-VPCE traffic, Glue metadata operations or CLD initialization begin failing with access-denied errors.

**Cause**: An S3 bucket policy was applied that denies non-Snowflake-VPCE traffic, which also blocks the AWS Glue catalog's own access to the bucket. Unlike Unity Catalog (where you can allowlist the catalog's control-plane VPC), there is currently no reliable way to distinguish and allowlist AWS Glue's traffic to S3 via a bucket policy.

**Solution**: Remove the deny-by-default bucket policy. With Glue, enabling `USE_PRIVATELINK_ENDPOINT = TRUE` routes Snowflake's S3 data reads over PrivateLink, but you should NOT lock down the bucket to private-only the way you would for other catalogs. See [setup/SKILL.md Step 1.8a](../setup/SKILL.md) for the Glue-specific guidance.

---

### ADLS Gen2 not applicable

**Note**: AWS Glue is an AWS-only service. ADLS Gen2 `dfs.core.windows.net` endpoint guidance from the shared vended-credentials-private-storage skill does not apply to Glue-backed catalog integrations.

---

### Shared storage-PrivateLink issues (region mismatch, endpoint pending)

For catalog-agnostic storage-PrivateLink issues — **region mismatch** (S3 bucket must be in the same AWS region as the Snowflake account) and **storage endpoint pending / not available** — see the shared troubleshooting reference: [shared/vended-credentials-private-storage/references/troubleshooting.md](../../shared/vended-credentials-private-storage/references/troubleshooting.md).
