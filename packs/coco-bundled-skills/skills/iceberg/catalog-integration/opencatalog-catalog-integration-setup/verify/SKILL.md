---
name: opencatalog-verify-integration
description: "Verify OpenCatalog (Polaris) catalog integration is configured correctly (public and PrivateLink). Triggers: check opencatalog integration, verify polaris integration, test opencatalog connection, is my polaris integration working, validate opencatalog catalog integration, confirm polaris catalog setup."
parent_skill: opencatalog-catalog-integration-setup
---

# OpenCatalog Verification

## ⚠️ REQUIRED: Load Shared Verification Workflow

**STOP.** Before proceeding with any verification steps, you **MUST** load and execute the shared verification workflow:

**Path**: `../../shared/verify/SKILL.md`

DO NOT attempt to verify the integration without loading the shared skill first.

## Workflow

Follow these steps in order:

1. **FIRST**: Load `shared/verify/SKILL.md` (path: `../../shared/verify/SKILL.md`) and execute ALL steps in that workflow
2. **DURING**: Apply OpenCatalog-specific context below when interpreting results or errors
3. **IF FAILURES**: Load `references/troubleshooting.md` for OpenCatalog-specific diagnosis

## OpenCatalog-Specific Context

Use this information while executing the shared verification workflow:

**Expected configuration values**:
- `catalog_source`: `POLARIS` or `ICEBERG_REST`
- `catalog_uri`: `https://<orgname>-<account_name>.snowflakecomputing.com/polaris/api/catalog` (public) or `https://<orgname>-<account_name>.privatelink.snowflakecomputing.com/polaris/api/catalog` (private — derived by inserting `.privatelink` before `.snowflakecomputing.com` in the account URL)
- `catalog_api_type`: `PUBLIC` or `PRIVATE`

**Common OpenCatalog-specific issues**:
| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `SYSTEM$VERIFY_CATALOG_INTEGRATION` fails with OAuth error | Invalid credentials | Verify Client ID and Client Secret are correct |
| OAuth error with correct credentials | Service connection disabled | Enable the service connection in OpenCatalog UI |
| Connection succeeds but no namespaces found | Missing catalog role | Assign catalog role to service principal in OpenCatalog |
| Namespaces visible but no tables | Missing table privileges | Grant `TABLE_LIST` on the namespace to the catalog role |
| Connection timeout with `CATALOG_API_TYPE = PRIVATE` | PrivateLink endpoint not provisioned (cross-deployment only) | If same deployment, provisioning is not needed — check other connectivity issues. If cross-deployment, run `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or query `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`) to check endpoint status; provision if missing |
| PrivateLink endpoint exists but connection fails | Hostname mismatch | Verify endpoint host matches PrivateLink account URL via `SYSTEM$GET_PRIVATELINK_ENDPOINTS_INFO()` (or `SNOWFLAKE.ACCOUNT_USAGE.OUTBOUND_PRIVATELINK_ENDPOINTS`) |

## Storage PrivateLink Verification (Conditional)

> **Only if `enable_storage_privatelink` was set to `yes` during setup.**

**Follow Step 6** in [../../shared/vended-credentials-private-storage/SKILL.md](../../shared/vended-credentials-private-storage/SKILL.md) to verify the `DEFAULT_STORAGE_CONFIG` property, the storage endpoint status (`available` on AWS, `APPROVED` on Azure — for ADLS Gen2 confirm both `blob` and `dfs`), and run the end-to-end query probe.

> **Registering the probe table — never use `EXTERNAL_VOLUME`.** This integration uses `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`, so the table needs no external volume. Do **not** write `EXTERNAL_VOLUME = 'VENDED'` (or any volume name) — "vended" is not a volume; that references a non-existent volume and fails. Register the table with `CATALOG_NAMESPACE` + `CATALOG_TABLE_NAME` only:
> ```sql
> CREATE ICEBERG TABLE <db>.<schema>.<table>
>   CATALOG = '<integration_name>'
>   CATALOG_NAMESPACE = '<namespace>'
>   CATALOG_TABLE_NAME = '<catalog_table_name>';
> ```

OpenCatalog-specific caveat: if the probe fails, see `references/troubleshooting.md` under "Storage access denied after enabling DEFAULT_STORAGE_CONFIG".

> If `DEFAULT_STORAGE_CONFIG` is missing and must be applied, the `ALTER CATALOG INTEGRATION` statement and its **mandatory approval checkpoint** are in Step 5 of the shared skill — do not run the ALTER without explicit user approval.

## Output

After completing the shared verification workflow, report results using the format defined in `shared/verify/SKILL.md`.

## Next Steps (On Success)

**If all verification checks passed**:

**Load** `shared/next-steps/SKILL.md` (path: `../../shared/next-steps/SKILL.md`)

Guide user through options for accessing catalog tables. DO NOT skip this step after successful verification.
