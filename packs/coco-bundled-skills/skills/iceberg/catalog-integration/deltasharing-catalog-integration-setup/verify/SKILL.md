---
name: deltasharing-verify
description: "Verify Delta Sharing catalog integration"
parent_skill: deltasharing-catalog-integration-setup
---

# Delta Sharing Verification

## REQUIRED: Load Shared Verification Workflow

**STOP.** Before proceeding with any verification steps, you **MUST** load and execute the shared verification workflow:

**Path**: `../../shared/verify/SKILL.md`

DO NOT attempt to verify the integration without loading the shared skill first.

## Workflow

Follow these steps in order:

1. **FIRST**: Load `shared/verify/SKILL.md` (path: `../../shared/verify/SKILL.md`) and execute ALL steps in that workflow
2. **DURING**: Apply Delta Sharing-specific context below when interpreting results or errors
3. **IF FAILURES**: Load `references/troubleshooting.md` for Delta Sharing-specific diagnosis

## Delta Sharing-Specific Context

Use this information while executing the shared verification workflow:

**Hierarchy**: Delta Sharing uses Shares → Schemas → Tables
- `SYSTEM$LIST_CATALOGS` returns **all shares** the bearer token has access to — use this to confirm `CATALOG_NAME` is valid and accessible
- `SYSTEM$LIST_NAMESPACES_FROM_CATALOG` returns **schemas** within the configured share (`CATALOG_NAME`)
- `SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG` returns **tables** within a schema

**Expected configuration values**:
- `catalog_source`: `DELTA_SHARING`
- `table_format`: `DELTA`

**Common Delta Sharing-specific issues**:

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `SYSTEM$VERIFY_CATALOG_INTEGRATION` fails with auth error | Invalid or expired bearer token | Try `ALTER CATALOG INTEGRATION ... SET REST_AUTHENTICATION` to rotate the token first; recreate the integration only if the endpoint or share name also changed |
| Connection succeeds but no schemas found | Share has no schemas, or wrong share name | Verify the share name (`CATALOG_NAME`) with the provider; check the share has data |
| Schemas visible but no tables | Schema has no tables, or tables not yet shared | Verify with the provider that tables are shared within the schema |
| `Feature not enabled` error | Delta Sharing catalog integration not enabled | Contact Snowflake Support |

## Output

After completing the shared verification workflow, report results using the format defined in `shared/verify/SKILL.md`.

## Next Steps (On Success)

**If all verification checks passed**:

**Load** `shared/next-steps/SKILL.md` (path: `../../shared/next-steps/SKILL.md`)

Guide user through options for accessing catalog tables. DO NOT skip this step after successful verification.

**Important for Delta Sharing — apply these rules when presenting options from the shared skill**:
- This is a **Delta Sharing** integration — CLDs are **always read-only**
- For CLD (Option B): only present the **read-only** variants (`ALLOWED_WRITE_OPERATIONS = NONE`). Do NOT show the non-read-only CLD variants to the user
- If `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` was configured → use the **"With read-only mode"** variant (no external volume needed)
- If `ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS` (default) → use the **"With read-only mode + external volume"** variant
