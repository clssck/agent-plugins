---
name: onelake-verify
description: "Verify OneLake REST catalog integration"
parent_skill: onelake-catalog-integration-setup
---

# OneLake REST Verification

## REQUIRED: Load Shared Verification Workflow

**STOP.** Before proceeding with any verification steps, you **MUST** load and execute the shared verification workflow:

**Path**: `../../shared/verify/SKILL.md`

DO NOT attempt to verify the integration without loading the shared skill first.

## Workflow

Follow these steps in order:

1. **FIRST**: Load `shared/verify/SKILL.md` (path: `../../shared/verify/SKILL.md`) and execute ALL steps in that workflow
2. **DURING**: Apply OneLake-specific context below when interpreting results or errors
3. **IF FAILURES**: Load `references/troubleshooting.md` for OneLake-specific diagnosis

## OneLake-Specific Context

Use this information while executing the shared verification workflow:

**Namespace format**: OneLake schema names (e.g., `dbo`)

**Expected configuration values**:
- `catalog_source`: `ICEBERG_REST`
- Authentication type: `OAUTH`

**Common OneLake-specific issues**:
| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `SYSTEM$VERIFY_CATALOG_INTEGRATION` fails with OAuth error | Invalid client credentials or tenant ID | Verify OAuth client ID, OAuth client secret, and tenant ID in Azure Entra |
| `SYSTEM$VERIFY_CATALOG_INTEGRATION` fails with access denied | Azure consent not granted | Navigate to AZURE_CONSENT_URL from DESC EXTERNAL VOLUME and click Accept |
| Connection succeeds but no namespaces found | Snowflake multi-tenant app not added to Fabric workspace | Add AZURE_MULTI_TENANT_APP_NAME to workspace with Contributor access |
| Namespaces visible but no tables | No Iceberg tables in the lakehouse | Verify Iceberg tables exist in the Fabric lakehouse |
| Invalid CATALOG_NAME error | Incorrect workspace ID or data item ID | Verify workspace ID and data item ID from Fabric URLs |

## Output

After completing the shared verification workflow, report results using the format defined in `shared/verify/SKILL.md`.

## Next Steps (On Success)

**If all verification checks passed**:

**Load** `shared/next-steps/SKILL.md` (path: `../../shared/next-steps/SKILL.md`)

Guide user through options for accessing catalog tables. DO NOT skip this step after successful verification.
