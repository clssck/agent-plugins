---
name: unitycatalog-verify
description: "Verify Unity Catalog integration"
parent_skill: unitycatalog-catalog-integration-setup
---

# Unity Catalog Verification

## ⚠️ REQUIRED: Load Shared Verification Workflow

**STOP.** Before proceeding with any verification steps, you **MUST** load and execute the shared verification workflow:

**Path**: `../../shared/verify/SKILL.md`

DO NOT attempt to verify the integration without loading the shared skill first.

## Workflow

Follow these steps in order:

1. **FIRST**: Load `shared/verify/SKILL.md` (path: `../../shared/verify/SKILL.md`) and execute ALL steps in that workflow
2. **DURING**: Apply Unity Catalog-specific context below when interpreting results or errors
3. **IF FAILURES**: Load `references/troubleshooting.md` for Unity Catalog-specific diagnosis

## Unity Catalog-Specific Context

Use this information while executing the shared verification workflow:

**Namespace format**: Schema names within the catalog (single-level)

**Expected configuration values**:
- `catalog_source`: `ICEBERG_REST`
- `catalog_uri`: `https://<databricks-workspace-url>/api/2.1/unity-catalog/iceberg-rest`

**Common Unity Catalog-specific issues**:
| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `SYSTEM$VERIFY_CATALOG_INTEGRATION` fails with OAuth error | Invalid credentials | Verify OAuth client ID, secret, and token URI are correct |
| Bearer token authentication fails | Token expired | Generate new PAT, update with `ALTER CATALOG INTEGRATION ... SET BEARER_TOKEN = '<new_token>'` |
| Connection succeeds but no namespaces found | Missing privileges | Grant `USE CATALOG` and `USE SCHEMA` to service principal |
| Namespaces visible but no tables | Missing table privileges | Grant `SELECT` privilege on tables to service principal |
| Tables visible but queries fail | External location access | Verify service principal has access to underlying storage location |

## Storage PrivateLink Verification (only when DEFAULT_STORAGE_CONFIG = USE_PRIVATELINK_ENDPOINT = TRUE was set)

**Storage PrivateLink verification** (only if storage connectivity was enabled): **Follow Step 6** in [../../shared/vended-credentials-private-storage/SKILL.md](../../shared/vended-credentials-private-storage/SKILL.md). Unity-specific caveat: confirm both `blob` and `dfs` endpoints show `APPROVED` for ADLS Gen2.

> **Registering the probe table — never use `EXTERNAL_VOLUME`.** This integration uses `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`, so the table needs no external volume. Do **not** write `EXTERNAL_VOLUME = 'VENDED'` (or any volume name) — "vended" is not a volume; that references a non-existent volume and fails. Register the table with `CATALOG_NAMESPACE` + `CATALOG_TABLE_NAME` only:
> ```sql
> CREATE ICEBERG TABLE <db>.<schema>.<table>
>   CATALOG = '<integration_name>'
>   CATALOG_NAMESPACE = '<namespace>'
>   CATALOG_TABLE_NAME = '<catalog_table_name>';
> ```

## Output

After completing the shared verification workflow, report results using the format defined in `shared/verify/SKILL.md`.

## Next Steps (On Success)

**If all verification checks passed**:

**Load** `shared/next-steps/SKILL.md` (path: `../../shared/next-steps/SKILL.md`)

Guide user through options for accessing catalog tables. DO NOT skip this step after successful verification.
