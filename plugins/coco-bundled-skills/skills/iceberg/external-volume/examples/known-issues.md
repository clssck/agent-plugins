# Known Issues and Limitations

## Azure: Storage Blob Data Contributor Required Even for Read-Only

**Issue:** Snowflake requires `Storage Blob Data Contributor` role even when `ALLOW_WRITES=FALSE`.

**Impact:** Violates least-privilege security practices. `Storage Blob Data Reader` does NOT work.

**Errors with Reader role:**
```
AuthorizationPermissionMismatch
This request is not authorized to perform this operation using this permission
Access denied during SYSTEM$VERIFY_EXTERNAL_VOLUME
```

**Workarounds:**
1. **Container-level scope** - Grant Contributor on specific container only:
   ```bash
   az role assignment create \
       --assignee "<service_principal_app_id>" \
       --role "Storage Blob Data Contributor" \
       --scope "/subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>/blobServices/default/containers/<container>"
   ```
2. **Dedicated storage account** - Isolate Snowflake data in separate account

**Status:** Current limitation - may be addressed in future releases.

---

## AWS: S3 vs S3GOV URI Scheme in Government Regions

**Issue:** Using `S3` instead of `S3GOV` in government regions causes cryptic "unsupported feature" errors.

| Snowflake Region | Required STORAGE_PROVIDER |
|------------------|---------------------------|
| Commercial (us-east-1, etc.) | `S3` |
| GovCloud (us-gov-west-1, etc.) | `S3GOV` |

**Check your region:**
```sql
SELECT CURRENT_REGION();
-- If contains 'GOV', use S3GOV
```

**GovCloud also requires different ARN format:**
- Commercial: `arn:aws:iam::...`
- GovCloud: `arn:aws-us-gov:iam::...`

**Status:** UX improvement needed - errors should indicate wrong storage provider.

---

## Cloning Iceberg Tables Without External Volume USAGE Permission

**Issue:** Users can clone Iceberg tables and write metadata files even without USAGE permission on the external volume.

**Behavior:**
- `CREATE TABLE ... CLONE` → Succeeds (unexpected)
- `SELECT * FROM cloned_table` → Fails (expected)
- `DROP TABLE cloned_table` → Fails (orphaned metadata)

**Workaround:** Restrict CREATE TABLE privileges on schemas with Iceberg tables.

**Status:** Known bug - CLONE should validate external volume permissions first.

---

## GRANT CALLER USAGE Internal Error

**Issue:** `GRANT CALLER USAGE ON EXTERNAL VOLUME` fails with internal error, while `GRANT USAGE` works.

```sql
-- Fails with internal error:
GRANT CALLER USAGE ON EXTERNAL VOLUME my_volume TO ROLE my_role;

-- Works:
GRANT USAGE ON EXTERNAL VOLUME my_volume TO ROLE my_role;
```

**Workaround:** Use `GRANT USAGE` instead of `GRANT CALLER USAGE`.

**Status:** Known bug.

---

## AWS Glue Catalog: Null Metadata Location

**Error:** `AWS Glue response returned null metadata location for the table <table> in namespace <db>.`

**Cause:** Known Apache Iceberg bug: https://github.com/apache/iceberg/issues/7151

**Diagnose via GUI:**
AWS Glue → Data Catalog Tables → Find Table → Advanced properties → Check `metadata_location`

**Diagnose via CLI:**
```bash
# 1. Assume the Glue catalog role
aws sts assume-role --role-arn <glue_role_arn> --external-id <external_id> --role-session-name debugSession

# 2. Export credentials from response
export AWS_ACCESS_KEY_ID=<AccessKeyId>
export AWS_SECRET_ACCESS_KEY=<SecretAccessKey>
export AWS_SESSION_TOKEN=<SessionToken>

# 3. Verify identity
aws sts get-caller-identity

# 4. Check table metadata location
aws glue get-table --database-name <db> --name <table>
# Look for Parameters.metadata_location in output
```

**Recovery:** Set `metadata_location` to `previous_metadata_location` via UpdateTable API:
```bash
aws glue update-table --catalog-id <account_id> --database-name <db> --table-input '{
  "Name": "<table>",
  "Parameters": {
    "metadata_location": "s3://<bucket>/<path>/previous.metadata.json",
    "table_type": "ICEBERG"
  }
}'
```

**Status:** Upstream Iceberg bug.
