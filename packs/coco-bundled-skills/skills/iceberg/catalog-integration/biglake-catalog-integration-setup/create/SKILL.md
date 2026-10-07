---
name: biglake-create-integration
description: "Create and execute the catalog integration for Google Cloud BigLake Metastore, then grant IAM to the Snowflake federated subject. Load when: running the CREATE CATALOG INTEGRATION SQL and wiring up workload identity federation. Triggers: create biglake catalog integration, connect snowflake to biglake, set up biglake metastore integration, biglake workload identity federation."
parent_skill: biglake-catalog-integration-setup
---

# Configuration & Creation

Build and execute the SQL to create your BigLake Iceberg REST catalog integration, then grant Google Cloud IAM roles to the Snowflake federated subject so token exchange can access your data.

## When to Load

From main skill Step 2: After prerequisites have been gathered and confirmed.

## Prerequisites

Must have from the setup phase:
- `GCP_PROJECT_ID` and `GCP_PROJECT_NUMBER`
- `GCS_BASE_LOCATION` (→ `CATALOG_NAME`)
- `POOL_ID`, `PROVIDER_ID`, and derived `OAUTH_AUDIENCE`
- `OAUTH_ALLOWED_SCOPES`
- `INTEGRATION_NAME`
- A GCP OIDC provider that trusts the Snowflake issuer URL (created in GCP Setup)

## Workflow

### Step 2.1: Retrieve the Snowflake Workload Identity Issuer URL

Snowflake presents its own identity token to Google's Security Token Service. The GCP OIDC provider must trust the issuer of that token.

**Execute**:
```sql
SELECT SYSTEM$GET_WORKLOAD_IDENTITY_ISSUER_URL();
```

**Present to user**:
```
Snowflake workload identity issuer URL:
─────────────────────────────────────────
<issuer_url>
─────────────────────────────────────────

Your GCP workload identity OIDC provider MUST use this as its Issuer URL.
```

**⚠️ STOP**: Ask: "Was your GCP OIDC provider created with this exact issuer URL?"

- **Yes** → Continue to Step 2.2
- **No / not sure** → Run `gcp-setup/SKILL.md` (GCP Setup) to create the workload identity pool + OIDC provider with this issuer, then return here.

> **Why this matters**: If the OIDC provider's issuer doesn't match this URL, `SYSTEM$VERIFY_CATALOG_INTEGRATION` fails at the token-exchange step. This is the most common BigLake setup error.

### Step 2.2: Choose access delegation mode, then generate the SQL

BigLake supports **public connectivity only** and uses **workload identity federation** (no client secret). Choose how Snowflake accesses the underlying Cloud Storage data:

**Ask the user** (recommend vended credentials):
```
How should Snowflake access the data files in Cloud Storage?

A: Vended credentials (RECOMMENDED)
   ✓ No Snowflake external volume needed
   ✓ BigLake vends short-lived storage credentials
   ✓ Requires the BigLake catalog in credential-vending mode (GCP Setup Phase 4)

B: External volume credentials
   ✓ Snowflake uses a GCS external volume for data access
   ✓ Works with a catalog in end-user mode
   ✗ Requires creating + configuring a Snowflake GCS external volume
```

Set `ACCESS_DELEGATION_MODE` accordingly. **Vended (A):**

```sql
CREATE OR REPLACE CATALOG INTEGRATION <INTEGRATION_NAME>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://biglake.googleapis.com/iceberg/v1/restcatalog'
    CATALOG_NAME = '<GCS_BASE_LOCATION>'            -- e.g. gs://my-bucket
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS     -- omit / EXTERNAL_VOLUME_CREDENTIALS for mode B
    ADDITIONAL_HEADERS = (
      "x-goog-user-project" = '<GCP_PROJECT_ID>'    -- REQUIRED; key MUST be double-quoted
    )
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_GRANT_TYPE = TOKEN_EXCHANGE
    OAUTH_TOKEN_URI = 'https://sts.googleapis.com/v1/token'
    OAUTH_AUDIENCE = '<OAUTH_AUDIENCE>'
    OAUTH_ALLOWED_SCOPES = ('<OAUTH_ALLOWED_SCOPES>')
  )
  ENABLED = TRUE;
```

> **Mode B (external volume)**: set `ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS` (or omit it — it's the default), keep the BigLake catalog in end-user mode, and create a Snowflake GCS **external volume** over the same `gs://` bucket. You'll pass `EXTERNAL_VOLUME = '<vol>'` when creating the catalog-linked database (see shared next-steps). The BigLake catalog **must** be in `end-user` credential mode — a vended-credentials catalog rejects external-volume reads with `X-Iceberg-Access-Delegation header must ... contain vended-credentials`.

> **Pattern B — BigQuery federation (`bq://`)**: if BigQuery owns the tables and Snowflake only reads them, set `CATALOG_NAME = 'bq://projects/<GCP_PROJECT_ID>'` and `ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS` (vending is not supported on `bq://`). This path also needs an external volume and storage grants to **two** principals (external-volume SA + federated subject). Follow the full recipe in [references/bigquery-federation.md](../references/bigquery-federation.md).

**Parameter explanation**:
- `CATALOG_SOURCE = ICEBERG_REST` / `TABLE_FORMAT = ICEBERG`: generic Iceberg REST catalog
- `CATALOG_URI`: fixed BigLake endpoint `https://biglake.googleapis.com/iceberg/v1/restcatalog`
- `CATALOG_NAME`: the GCS base path for your BigLake tables
- `ADDITIONAL_HEADERS."x-goog-user-project"`: **required** — Google uses it to attribute usage/billing to the correct project
- `OAUTH_GRANT_TYPE = TOKEN_EXCHANGE`: enables workload identity federation
- `OAUTH_TOKEN_URI`: Google STS endpoint `https://sts.googleapis.com/v1/token`
- `OAUTH_AUDIENCE`: the OIDC provider's audience resource name
- `OAUTH_ALLOWED_SCOPES`: OAuth scopes (default `https://www.googleapis.com/auth/bigquery`)

> **ALTER limitation**: `REST_CONFIG` cannot be changed via `ALTER CATALOG INTEGRATION` — use `CREATE OR REPLACE`. **Important:** a `CREATE OR REPLACE` generates a NEW `WORKLOAD_IDENTITY_FEDERATION_SUBJECT`, so you must re-run `DESC` and re-grant the IAM roles (Steps 2.5–2.6) after every replace.

### Step 2.3: Review & Approval

**Present the generated SQL** with actual values filled in:
```
Generated Catalog Integration SQL:
═══════════════════════════════════════════════════════════
[The complete SQL with real values]
═══════════════════════════════════════════════════════════

This creates catalog integration '<INTEGRATION_NAME>' connecting to
Google Cloud BigLake Metastore in project '<GCP_PROJECT_ID>' using
workload identity federation (token exchange).

IMPORTANT: After creation, you'll grant Google Cloud IAM roles to the
Snowflake federated subject (retrieved via DESC).
```

**⚠️ MANDATORY STOPPING POINT**: "Please review the SQL above. Ready to execute and create the catalog integration?"

- "Yes" / "Approved" / "Proceed" → Continue to Step 2.4
- "No" / "Wait" → Ask what to change

### Step 2.4: Execute Creation

**Execute the approved SQL.**

**Expected success**: `Integration <INTEGRATION_NAME> successfully created.`

**If success** → Continue to Step 2.5

**If error** → Present error → Load `references/troubleshooting.md` → Wait for direction

### Step 2.5: Retrieve the Federated Subject

**Execute**:
```sql
DESC CATALOG INTEGRATION <INTEGRATION_NAME>;
```

Extract the value of the `WORKLOAD_IDENTITY_FEDERATION_SUBJECT` property.

**Present to user**:
```
Snowflake federated subject:
─────────────────────────────────────────
WORKLOAD_IDENTITY_FEDERATION_SUBJECT = <subject_id>
─────────────────────────────────────────

You'll grant Google Cloud IAM roles to this subject in the next step.
```

### Step 2.6: Grant Google Cloud IAM Roles

The Snowflake federated identity needs IAM roles to read (and, if writing, to write) BigLake tables and the underlying Cloud Storage.

**Present the principal and grant commands**:
```
The Snowflake federated principal is:

principal://iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<subject_id>
```

Grant roles to the federated subject. **`roles/serviceusage.serviceUsageConsumer` is required in both modes** (the `x-goog-user-project` billing header means the caller must be allowed to use the project):
```bash
# Always: allow the subject to use the billing project (x-goog-user-project header)
gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
  --role='roles/serviceusage.serviceUsageConsumer' \
  --member='principal://iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<subject_id>' \
  --condition=None

# Always: BigLake read (needed to call the catalog / request vended credentials)
gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
  --role='roles/biglake.viewer' \
  --member='principal://iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<subject_id>' \
  --condition=None

# External-volume mode ONLY: the subject also needs direct GCS read.
# (Vended-credentials mode: SKIP this — the BigLake service account vends storage access instead.)
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --role='roles/storage.objectViewer' \
  --member='principal://iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<subject_id>'
```

> In **vended-credentials** mode, storage access is granted to the BigLake service account (GCP Setup Phase 4), not to this subject — so the subject needs only `serviceusage.serviceUsageConsumer` + `biglake.viewer` (read) here.

> **Read vs write roles** (from Google's Lakehouse required-roles guidance):
> - **Read**: `roles/biglake.viewer` (+ `roles/storage.objectViewer` on the subject only in external-volume mode; on the BigLake SA in vended mode)
> - **Write / manage**: `roles/biglake.editor` (+ `roles/storage.objectUser`)
> - **Admin**: `roles/biglake.admin` (+ `roles/storage.admin`)
> - **Always**: `roles/serviceusage.serviceUsageConsumer` on the subject.
>
> **Requires** `resourcemanager.projects.setIamPolicy` (e.g. `roles/resourcemanager.projectIamAdmin` or Owner) to run these grants. If denied, ask a project admin.
> Apply least privilege — pick the narrowest roles that match how Snowflake will use the catalog.

**⚠️ MANDATORY STOPPING POINT**: "Have you granted the IAM roles to the federated subject?"

Wait for confirmation ("Yes", "Done", "Granted") → Continue to Step 2.7

> **Note**: IAM propagation can take **one to two minutes**. If `SYSTEM$VERIFY_CATALOG_INTEGRATION` returns a 403 / permission error right after granting, wait ~75s and retry before assuming a misconfiguration.

### Step 2.7: Proceed to Verification

**Output**: Catalog integration created and IAM granted to the federated subject.

**Next**: Return to main skill → Step 3 (Verification) → Load `verify/SKILL.md`.

## Error Handling

**Common errors during creation**:
- **Invalid `OAUTH_AUDIENCE`**: The audience resource name must exactly match the OIDC provider (`//iam.googleapis.com/projects/<num>/.../providers/<provider>`). A number-vs-ID mismatch (project number required, not ID) is a common cause.
- **`CREATE INTEGRATION` privilege denied**: The Snowflake role needs `CREATE INTEGRATION` on the account (typically ACCOUNTADMIN or a role with the privilege).
- **Missing `x-goog-user-project`**: BigLake rejects requests without the billing-project header. Ensure `ADDITIONAL_HEADERS` is present.

**Common errors during verification** (see `references/troubleshooting.md`):
- Token exchange failure → OIDC provider issuer doesn't match the Snowflake issuer URL, or audience mismatch
- IAM permission denied → federated subject lacks `roles/biglake.viewer` / storage roles

## Output

Successfully created catalog integration in Snowflake with the federated subject granted Google Cloud IAM roles, ready for verification.

## Next Steps

After successful creation and IAM grant:
- Return to main skill
- Proceed to Step 3: Verification
- Load `verify/SKILL.md`
