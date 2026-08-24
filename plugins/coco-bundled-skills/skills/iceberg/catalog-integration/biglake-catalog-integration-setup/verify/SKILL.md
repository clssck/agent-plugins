---
name: biglake-verify
description: "Verify a Google Cloud BigLake Metastore catalog integration is configured correctly. Load when: confirming token exchange, namespace/table listing, and read access work. Triggers: check biglake integration, verify biglake integration, test biglake connection, is my biglake integration working, validate biglake catalog integration."
parent_skill: biglake-catalog-integration-setup
---

# BigLake Catalog Integration Verification

## Load the shared verification workflow

Before running any verification steps, load and execute the shared verification workflow at `../../shared/verify/SKILL.md`.

## Workflow

Follow these steps in order:

1. **FIRST**: Load `shared/verify/SKILL.md` (path: `../../shared/verify/SKILL.md`) and execute ALL steps in that workflow
2. **DURING**: Apply the BigLake-specific context below when interpreting results or errors
3. **IF FAILURES**: Load `references/troubleshooting.md` for BigLake-specific diagnosis

## BigLake-Specific Context

Use this information while executing the shared verification workflow:

**Namespace format**: BigLake namespaces (schemas) within the catalog.

**Expected configuration values**:
- `catalog_source`: `ICEBERG_REST`
- `catalog_uri`: `https://biglake.googleapis.com/iceberg/v1/restcatalog`
- `catalog_name`: your GCS base location (e.g. `gs://my-bucket/iceberg-data`)

**Common BigLake-specific issues**:
| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| `SYSTEM$VERIFY_CATALOG_INTEGRATION` fails at token exchange | OIDC provider issuer ≠ Snowflake issuer URL, or wrong `OAUTH_AUDIENCE` | Recreate the OIDC provider with the exact `SYSTEM$GET_WORKLOAD_IDENTITY_ISSUER_URL()` value; confirm audience uses the project **number** |
| Verify passes but listing namespaces/tables returns permission errors | Federated subject lacks BigLake/Storage roles | Grant `roles/biglake.viewer` to the subject. **External-volume mode**: also grant `roles/storage.objectViewer` on the bucket to the subject. **Vended-credentials mode** (default): storage access goes to the BigLake SA (`roles/storage.objectUser`), not the subject — see `references/troubleshooting.md` #2 |
| `PERMISSION_DENIED` mentioning billing/user project | Missing or wrong `x-goog-user-project` header | Ensure `ADDITIONAL_HEADERS."x-goog-user-project"` is set to your GCP project ID |
| Empty namespace/table list | No tables yet, or wrong namespace, or missing read role | Confirm tables exist (Spark), check namespace spelling, verify `roles/biglake.viewer` |
| 429 / rate limit on listing | BigLake Iceberg REST read-request-per-minute quota exceeded | Raise the quota (GCP console → IAM & Admin → Quotas → BigLake API) |

## Output

After completing the shared verification workflow, report results using the format defined in `shared/verify/SKILL.md`.

## Next Steps (On Success)

**If all verification checks passed**:

**Load** `shared/next-steps/SKILL.md` (path: `../../shared/next-steps/SKILL.md`)

After a successful verification, guide the user through options for accessing catalog tables.

> **BigLake note**: BigLake uses workload identity federation. If the user chose **vended-credentials** mode (recommended), present the no-external-volume path; if they chose **external-volume** mode, present the external-volume variant. PrivateLink is not applicable.
