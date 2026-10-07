# Troubleshooting OneLake REST Catalog Integration

Comprehensive guide for diagnosing and fixing issues with OneLake REST catalog integrations.

## When to Load

Load this reference when:
- `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns failure
- Namespace or table discovery fails
- OAuth authentication errors occur
- Azure consent or Fabric workspace access issues
- Unexpected behavior during verification

## Important: ALTER CATALOG INTEGRATION Limitations

**REST_CONFIG cannot be altered.**

**REST_AUTHENTICATION** can only be altered for **secret rotation** — specifically, the OAuth client secret. Other REST_AUTHENTICATION parameters (e.g., `OAUTH_TOKEN_URI`, `OAUTH_CLIENT_ID`) cannot be changed via ALTER.

To rotate the OAuth client secret:
```sql
ALTER CATALOG INTEGRATION <name> SET
  REST_AUTHENTICATION = (
    OAUTH_CLIENT_SECRET = '<new_client_secret>'
  );
```

If you need to change the catalog URI, catalog name, client ID, or token URI, you must **recreate the integration**:
```sql
DROP CATALOG INTEGRATION <integration_name>;
CREATE CATALOG INTEGRATION <integration_name> ...;
```

---

## Common Issues

### 1. OAuth Authentication Failure

**Error Pattern**:
```
Failed to perform OAuth client credential flow
Invalid client credentials
AADSTS7000215: Invalid client secret provided
AADSTS7000222: The provided client secret keys are expired
```

**Cause**: Azure Entra OAuth client ID or OAuth client secret is invalid or expired.

**Debug Steps**:

1. Check integration configuration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Verify `OAUTH_CLIENT_ID` matches the OAuth client ID (Application (client) ID) in Azure Entra.

2. Verify client secret has not expired:
   - Azure portal → App registrations → Your app → Certificates & secrets
   - Check the expiration date of the client secret

3. Verify the OAuth client ID:
   - Azure portal → App registrations → Your app → Overview
   - Confirm the Application (client) ID matches the OAuth client ID used in the integration

**Solutions**:
- If client secret expired: Create a new client secret in Azure Entra and use `ALTER CATALOG INTEGRATION` to update it:
  ```sql
  ALTER CATALOG INTEGRATION <integration_name> SET
    REST_AUTHENTICATION = (
      OAUTH_CLIENT_SECRET = '<new_client_secret>'
    );
  ```
  > **Note**: `REST_AUTHENTICATION` can be altered for OAuth client secret rotation. `REST_CONFIG` cannot be altered — you must recreate the integration to change REST_CONFIG parameters.
- If OAuth client ID is wrong: Recreate the catalog integration with the correct OAuth client ID (REST_AUTHENTICATION parameter change beyond secret rotation requires recreation)

---

### 2. Invalid Token Endpoint URL

**Error Pattern**:
```
Failed to obtain OAuth token
Unable to reach token endpoint
Connection refused
```

**Cause**: The `OAUTH_TOKEN_URI` is malformed or uses the wrong tenant ID.

**Debug Steps**:

1. Check integration configuration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Look for `OAUTH_TOKEN_URI` value.

2. Verify the format matches:
   `https://login.microsoftonline.com/<entra_tenant_id>/oauth2/v2.0/token`

3. Verify the tenant ID:
   - Azure portal → Microsoft Entra ID → Overview → Tenant ID
   - Must match the `<entra_tenant_id>` in the token URI

**Solution**: Recreate the catalog integration with the correct token endpoint URL. REST_AUTHENTICATION parameters other than the secret cannot be altered.

---

### 3. Azure Consent Not Granted or Snowflake Multi-Tenant App Not in Fabric Workspace

**Error Pattern**:
```
Access denied
Insufficient privileges to complete the operation
Authorization failed
Connection succeeds but no namespaces found
Access denied when listing tables
Catalog verification passes but table discovery fails
```

**Cause**: The Azure consent for the Snowflake multi-tenant app has not been granted or was revoked, and/or the Snowflake multi-tenant app (AZURE_MULTI_TENANT_APP_NAME) has not been added to the Fabric workspace with sufficient access.

**Debug Steps**:

1. Retrieve the consent URL and multi-tenant app name:
   ```sql
   DESC EXTERNAL VOLUME <extvol_name>;
   ```
   Extract these values from output:

   | Property | Description |
   |----------|-------------|
   | `AZURE_CONSENT_URL` | URL to the Microsoft permissions request page |
   | `AZURE_MULTI_TENANT_APP_NAME` | Name of the Snowflake client application created for your account |

   The `AZURE_MULTI_TENANT_APP_NAME` value has the format `<app_name>_<numeric_suffix>`. To get the actual app name:
   - Take the full value (e.g., `abc12tsnowflakepacint_1234567890123`)
   - **Strip the underscore and numeric suffix** (e.g., `abc12tsnowflakepacint`)
   - Use ONLY the stripped name everywhere: Azure consent, Fabric workspace search, and any user-facing instructions
   - The numeric suffix is an internal identifier and must be omitted

2. Check if Azure consent has been granted:
   - Navigate to the `AZURE_CONSENT_URL` in a web browser
   - If consent was previously granted, check enterprise applications:
     - Azure portal → Enterprise applications → Search for the Snowflake app name (without numeric suffix)
     - Verify it exists and permissions are granted

3. Check Fabric workspace access:
   - Navigate to your Fabric workspace
   - Select "Manage access"
   - Search for the app name (without the numeric suffix)
   - Verify access level is Contributor or higher

**Solutions**:
- **If consent not granted**: Navigate to the AZURE_CONSENT_URL and click "Accept". Ensure you sign in with an account that has permission to consent (Azure AD admin or user with consent permissions).
- **If consent was revoked**: Re-consent by visiting the AZURE_CONSENT_URL again.
- **If multi-tenant app not in workspace**: Add it:
  1. Navigate to Microsoft Fabric → Your workspace
  2. Select "Manage access"
  3. Select "+ Add people or groups"
  4. Search for the app name (without the numeric suffix)
  5. Select "Contributor" or higher
  6. Select "Add"
- **If app has insufficient permissions** (e.g., Viewer): Upgrade to Contributor or higher.

---

### 4. Missing user_impersonation Permission

**Error Pattern**:
```
AADSTS65001: The user or administrator has not consented to use the application
Scope 'https://storage.azure.com/.default' is not valid
```

**Cause**: The Azure Entra application registration is missing the `user_impersonation` permission for Azure Storage.

**Debug Steps**:

1. Check application permissions:
   - Azure portal → App registrations → Your app → API permissions
   - Look for "Azure Storage" → "user_impersonation" (Delegated)

2. If the permission is listed but not granted, check if admin consent is required:
   - Look for "Admin consent required: Yes" in the permissions list
   - If so, an admin must grant consent

**Solutions**:
- Add the `user_impersonation` permission:
  1. Azure portal → App registrations → Your app → API permissions
  2. Add a permission → Microsoft APIs tab → Azure Storage
  3. Select "user_impersonation" (Delegated)
  4. If admin consent is required, click "Grant admin consent for [tenant]"

**IMPORTANT**: Use the "Microsoft APIs" tab, NOT the "APIs my organization uses" tab when adding the permission.

---

### 5. Invalid Workspace ID or Data Item ID

**Error Pattern**:
```
Catalog not found
Invalid catalog name
Resource not found
404 Not Found
```

**Cause**: The workspace ID or data item ID (lakehouse ID) in CATALOG_NAME or STORAGE_BASE_URL is incorrect.

**Debug Steps**:

1. Check the catalog integration configuration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Look for `CATALOG_NAME` — should be `<workspaceID>/<dataItemID>`.

2. Verify workspace ID:
   - Navigate to any item in your Fabric workspace
   - Check the URL for the workspace ID (GUID after `/groups/`)
   - Example: `https://app.fabric.microsoft.com/groups/<workspaceID>/...`

3. Verify data item ID:
   - Open your lakehouse in Fabric
   - Check the URL for the data item ID (GUID after `/lakehouses/`)
   - Example: `https://app.fabric.microsoft.com/.../lakehouses/<dataItemID>/...`

**Solution**: Recreate the catalog integration and/or external volume with the correct IDs. REST_CONFIG cannot be altered.

---

### 6. OAuth Scopes Mismatch

**Error Pattern**:
```
Invalid scope
AADSTS70011: The provided request must include a 'scope' input parameter
Token request failed
```

**Cause**: The `OAUTH_ALLOWED_SCOPES` parameter is incorrect.

**Debug Steps**:

1. Check integration configuration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Verify `OAUTH_ALLOWED_SCOPES` is `('https://storage.azure.com/.default')`.

**Solution**: Recreate the catalog integration with the correct scopes:
```sql
OAUTH_ALLOWED_SCOPES = ('https://storage.azure.com/.default')
```

---

### 7. External Volume Consent URL Not Working

**Error Pattern**:
```
AZURE_CONSENT_URL returns error page
Cannot grant consent
Redirect loop or blank page
```

**Cause**: The external volume may not have been created correctly, or the Azure tenant configuration has issues.

**Debug Steps**:

1. Verify external volume exists:
   ```sql
   DESC EXTERNAL VOLUME <extvol_name>;
   ```

2. Confirm AZURE_CONSENT_URL is present in the output.

3. Try opening the URL in an incognito/private browser window.

4. Ensure you're signed in with an account that has permissions to grant consent in the Azure tenant.

**Solutions**:
- Use an incognito browser window to avoid cached credentials
- Sign in with a Global Administrator or Application Administrator role in Azure AD
- If the consent URL is not present, recreate the external volume
- Verify AZURE_TENANT_ID is correct in the external volume definition

---

### 8. Fabric Tenant Settings Not Enabled

**Error Pattern**:
```
Access denied even after consent is granted
Service principal cannot access OneLake
Authentication succeeds but API calls fail
403 Forbidden when listing namespaces or tables
```

**Cause**: Microsoft Fabric requires specific tenant-level settings to be enabled for service principals (including Snowflake's multi-tenant app) to access OneLake APIs. These settings are disabled by default in some tenants.

**Debug Steps**:

1. Confirm that Azure consent and Fabric workspace access are properly configured (Issue #3 above).

2. Ask a Fabric admin to check tenant settings:
   - Go to Fabric **Admin Portal** → **Tenant settings**
   - Search for "Service principals"

3. Verify the following settings are **enabled**:
   - **"Service principals can use Fabric APIs"** — allows service principals to call Fabric REST APIs
   - **"Users can access data stored in OneLake with apps external to the Fabric environment"** — allows external apps (like Snowflake) to read OneLake data

**Solutions**:
- Ask a Fabric administrator to enable both settings in the Admin Portal → Tenant settings
- These settings can be scoped to specific security groups if the admin prefers not to enable them tenant-wide
- After enabling, wait a few minutes for the change to propagate, then retry the operation

> **Reference**: [Microsoft Fabric tenant settings](https://learn.microsoft.com/en-us/fabric/admin/tenant-settings-index)

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
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<namespace>');
```

**External volume diagnostics**:
```sql
-- Check external volume details and consent URL
DESC EXTERNAL VOLUME <extvol_name>;

-- Show all external volumes
SHOW EXTERNAL VOLUMES;
```

**Catalog-linked database diagnostics** (if created):
```sql
-- Check sync status
SELECT SYSTEM$CATALOG_LINK_STATUS('<database_name>');

-- List schemas
SHOW SCHEMAS IN DATABASE <database_name>;

-- List tables
SHOW TABLES IN SCHEMA <database_name>.<schema_name>;
```

## General Troubleshooting Tips

1. **Start with OAuth credentials**: Most issues stem from incorrect client ID, secret, or tenant ID
2. **Check Azure consent**: Ensure both the application and the Snowflake multi-tenant app have proper access
3. **Verify IDs from URLs**: Workspace ID and data item ID must match exactly — copy them from the Fabric URL
4. **Use correct scopes**: Must be `https://storage.azure.com/.default`
5. **Check secret expiration**: Azure Entra client secrets expire — verify yours is still valid
6. **Verify Fabric workspace access**: Both your application registration AND the Snowflake multi-tenant app need Contributor access
7. **Recreate if config changes needed**: REST_CONFIG cannot be altered; REST_AUTHENTICATION can only be altered for secret rotation
8. **Read-only**: Snowflake only supports read operations for OneLake tables — write operations are not supported
9. **Fabric tenant settings**: Ensure "Service principals can use Fabric APIs" and "Users can access data stored in OneLake with apps external to the Fabric environment" are enabled in Admin Portal → Tenant settings
