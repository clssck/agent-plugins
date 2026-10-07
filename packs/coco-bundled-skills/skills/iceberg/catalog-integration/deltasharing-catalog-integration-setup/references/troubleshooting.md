# Troubleshooting Delta Sharing Catalog Integration

Comprehensive guide for diagnosing and fixing issues with Delta Sharing catalog integrations.

## When to Load

Load this reference when:
- `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns failure
- Schema or table discovery fails
- Connection or authentication errors occur
- Unexpected behavior during verification

## Important: ALTER CATALOG INTEGRATION Limitations

**REST_CONFIG cannot be altered.** If you need to change `CATALOG_URI`, `CATALOG_NAME`, or `ACCESS_DELEGATION_MODE`, you must **recreate the integration**:
```sql
DROP CATALOG INTEGRATION <integration_name>;
CREATE CATALOG INTEGRATION <integration_name> ...;
```

**BEARER_TOKEN can be rotated** (when bearer token rotation is enabled):
```sql
ALTER CATALOG INTEGRATION <integration_name> SET
  REST_AUTHENTICATION = (
    TYPE = BEARER
    BEARER_TOKEN = '<new_bearer_token>'
  );
```

---

## Common Issues

### 1. Invalid or Expired Bearer Token

**Error Pattern**:
```
Failed to connect to Delta Sharing server
Authentication failed
401 Unauthorized
Invalid bearer token
```

**Cause**: The bearer token is malformed, expired, or has been revoked by the provider.

**Debug Steps**:

1. Check the integration configuration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```

2. Test the connection:
   ```sql
   SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
   ```

**Solutions**:
- If only the token needs updating (endpoint and share name remain the same), use ALTER:
  ```sql
  ALTER CATALOG INTEGRATION <integration_name> SET
    REST_AUTHENTICATION = (
      TYPE = BEARER
      BEARER_TOKEN = '<new_bearer_token>'
    );
  ```
- If the endpoint or share name also changed, obtain a new credential file and recreate:
  ```sql
  CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
    CATALOG_SOURCE = DELTA_SHARING
    TABLE_FORMAT = DELTA
    REST_CONFIG = (
      CATALOG_URI = '<endpoint>'
      CATALOG_NAME = '<share_name>'
    )
    REST_AUTHENTICATION = (
      TYPE = BEARER
      BEARER_TOKEN = '<new_bearer_token>'
    )
    ENABLED = TRUE;
  ```

---

### 2. Insufficient Privileges

**Error Pattern**:
```
Insufficient privileges to operate on integration
SQL access control error
```

**Cause**: The role being used lacks the `CREATE INTEGRATION` privilege.

**Debug Steps**:

1. Check your current role:
   ```sql
   SELECT CURRENT_ROLE();
   ```

**Solutions**:
- Switch to ACCOUNTADMIN:
  ```sql
  USE ROLE ACCOUNTADMIN;
  ```
- Or grant the privilege to your role:
  ```sql
  GRANT CREATE INTEGRATION ON ACCOUNT TO ROLE <your_role>;
  ```

---

### 3. Schema / Table Discovery Issues

**Error Pattern**:
```
No schemas returned
Empty schema list
Schema '<name>' not found
No tables found in schema
```

**Causes**:
- Wrong share name in `CATALOG_NAME`
- Share has no schemas yet
- Schema or table names are case-sensitive
- Tables have not been added to the share on the provider side

**Debug Steps**:

1. List all schemas in the configured share:
   ```sql
   SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
   ```

2. List tables in a specific schema:
   ```sql
   SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<schema>');
   ```

3. If empty — verify with the provider:
   - Confirm the share name is correct
   - Confirm the share contains schemas and tables
   - Confirm your recipient/token has access to the share

**Solutions**:
- Correct `CATALOG_NAME` if the share name is wrong (requires recreating the integration)
- Verify with the provider that data has been shared and is accessible with your token
- Use exact casing when referencing schema and table names (case-sensitive)

---

### 4. Invalid CATALOG_URI

**Error Pattern**:
```
Invalid catalog URI
Malformed URL
Failed to connect: <url>
```

**Cause**: The endpoint URL from the credential file is malformed or incorrect.

**Validation**:
- Must start with `https://`
- Must be a valid URL (no spaces, valid protocol)
- Examples of valid URI:
  - `https://{recipient-id}.delta-sharing.{region}.{cloud-provider-specific-domain}/api/2.0/delta-sharing/metastores/<metastore-id>`

**Solution**: Verify the endpoint URL from the credential file. Recreate the integration with the correct URL.

---

### 5. Access Delegation Mode Error

**Error Pattern**:
```
Invalid ACCESS_DELEGATION_MODE
Vended credentials not available
```

**Cause**: Attempting to use `VENDED_CREDENTIALS` when credential vending is not supported or not enabled for this account.

**Solution**:
- Check if credential vending is enabled for your account
- If not, use `EXTERNAL_VOLUME_CREDENTIALS` (or omit `ACCESS_DELEGATION_MODE`, which defaults to `EXTERNAL_VOLUME_CREDENTIALS`)
- Recreate the integration without `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`:
  ```sql
  CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
    CATALOG_SOURCE = DELTA_SHARING
    TABLE_FORMAT = DELTA
    REST_CONFIG = (
      CATALOG_URI = '<endpoint>'
      CATALOG_NAME = '<share_name>'
      -- ACCESS_DELEGATION_MODE omitted, defaults to EXTERNAL_VOLUME_CREDENTIALS
    )
    REST_AUTHENTICATION = (
      TYPE = BEARER
      BEARER_TOKEN = '<bearer_token>'
    )
    ENABLED = TRUE;
  ```

---

### 6. Feature Not Enabled

**Error Pattern**:
```
Feature not enabled
DELTA_SHARING catalog source is not supported
```

**Cause**: The Delta Sharing catalog integration feature is not enabled for your Snowflake account.

**Solution**: Contact Snowflake Support to enable the Delta Sharing catalog integration feature for your account.

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

**List schemas in the share**:
```sql
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
```

**List tables in a schema**:
```sql
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<schema>');
```

---

## General Troubleshooting Tips

1. **Start with the bearer token**: Most connection failures trace back to an invalid or expired token
2. **Check privileges**: Ensure ACCOUNTADMIN or a role with `CREATE INTEGRATION` is used
3. **Verify the share name**: `CATALOG_NAME` must match the exact share name from the provider
4. **Remember REST_CONFIG is immutable**: `CATALOG_URI`, `CATALOG_NAME`, and `ACCESS_DELEGATION_MODE` cannot be altered — recreate the integration if these need to change
5. **Use exact casing**: Schema and table names are case-sensitive
6. **Confirm provider side**: If connection succeeds but no data is visible, the issue is likely on the provider side — verify the share has been set up and your token has access
