---
name: biglake-setup-prerequisites
description: "Gather prerequisites for a Google Cloud BigLake Metastore catalog integration. Load when: collecting GCP project ID/number, GCS base location or bq:// warehouse, workload identity pool/provider, OAuth audience, and integration name before creating the integration. Triggers: biglake prerequisites, gather biglake config, set up biglake prerequisites, what do I need for biglake integration."
parent_skill: biglake-catalog-integration-setup
---

# Prerequisites Gathering

Collect all required information to create your BigLake Metastore catalog integration.

This skill focuses on **Snowflake-side setup**. The Google Cloud side (bucket, BigLake catalog, workload identity pool/provider, IAM) should be completed first — if it isn't, run the `gcp-setup/SKILL.md` workflow before this one.

## When to Load

From main skill Step 1: Prerequisites gathering phase

## Prerequisites

User should have:
- A Google Cloud project with the BigLake API enabled
- A BigLake catalog with Iceberg (V2/V3) tables, backed by a GCS location
- A workload identity pool + OIDC provider trusting the Snowflake issuer URL
- IAM roles ready to grant to the Snowflake federated subject
- Admin access to Snowflake to create catalog integrations (CREATE INTEGRATION)

> **Note**: If you need the Google Cloud side set up first, run `gcp-setup/SKILL.md` (main skill option A).

## Workflow

Collect prerequisites **one at a time** in the following order. Wait for the user's response before proceeding to the next question.

---

### Step 1.1: Confirm BigLake Setup (FIRST)

**Ask**:
```
Before we begin, let's confirm your Google Cloud setup:

Do you have:
✓ A Google Cloud project with the BigLake API enabled
✓ A BigLake catalog with Iceberg tables (backed by a GCS bucket)
✓ A workload identity pool + OIDC provider trusting Snowflake

(If not, I can run the GCP Setup workflow first — it provisions all of
the above with gcloud.)
```

**If Yes** → Continue to Step 1.2

**If No** →
```
Let's set up the Google Cloud side first.
Returning to the main skill → option A (GCP Setup).
```
Load `gcp-setup/SKILL.md` and run the GCP Setup Workflow, then return here.

**STOP** — Cannot proceed without the Google Cloud prerequisites.

---

### Step 1.2: Google Cloud Project ID

**Ask**:
```
What is your Google Cloud project ID?

(This is the billing/usage project. It becomes the required
"x-goog-user-project" header value. Find it with:
gcloud config get-value project)

Example: my-analytics-project
```

**Record**: `GCP_PROJECT_ID`

---

### Step 1.3: GCS Base Location (CATALOG_NAME)

**Ask**:
```
What is the GCS base location for your BigLake tables?

This is used as CATALOG_NAME. It's typically the Cloud Storage base
path where your BigLake Iceberg data lives.

Example: gs://my-bucket/iceberg-data
```

**Record**: `GCS_BASE_LOCATION`

> **Note**: This is the value returned/used when the BigLake catalog was created. If you ran GCP Setup, use the warehouse/base location from that step.

> **Pattern B (BigQuery federation)**: if BigQuery owns the tables and Snowflake only reads them, `CATALOG_NAME` is instead `bq://projects/<GCP_PROJECT_ID>` and an external volume is required (vending is not available). Follow [references/bigquery-federation.md](../references/bigquery-federation.md) rather than the vended-credentials path.

---

### Step 1.4: Workload Identity Pool and Provider

**Ask**:
```
What are your workload identity pool ID and OIDC provider ID?

(If you ran GCP Setup, these are the IDs you chose there. Otherwise
list them with:
gcloud iam workload-identity-pools list --location=global
gcloud iam workload-identity-pools providers list \
  --location=global --workload-identity-pool=<POOL_ID>)

Pool ID example:     snowflake-pool
Provider ID example: snowflake-oidc
```

**Record**: `POOL_ID`, `PROVIDER_ID`

**Also ask** (needed to build the audience resource name):
```
What is your Google Cloud project NUMBER? (not the ID)

Find it with:
gcloud projects describe <GCP_PROJECT_ID> --format='value(projectNumber)'
```

**Record**: `GCP_PROJECT_NUMBER`

**Derive** `OAUTH_AUDIENCE`:
```
//iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/providers/<PROVIDER_ID>
```

> **Note**: If the OIDC provider was created with a custom audience, use that value instead. The default audience is the provider resource name above.

---

### Step 1.5: OAuth Allowed Scopes

**Ask**:
```
What OAuth scopes should Snowflake request?

Default (recommended): https://www.googleapis.com/auth/bigquery

Use the scopes your organization requires for BigLake/BigQuery/Storage
access.
```

**Record**: `OAUTH_ALLOWED_SCOPES` (default `https://www.googleapis.com/auth/bigquery`)

---

### Step 1.5a: Access Delegation Mode

**Ask** (recommend vended credentials):
```
How should Snowflake access the Cloud Storage data files?

A: Vended credentials (RECOMMENDED) — BigLake vends short-lived storage
   credentials; no Snowflake external volume needed. Requires the BigLake
   catalog in credential-vending mode (set in GCP Setup).
B: External volume — Snowflake uses a GCS external volume; catalog stays in
   end-user mode. You'll also provide an external volume name.
```

**Record**: `ACCESS_DELEGATION_MODE` (`VENDED_CREDENTIALS` for A, `EXTERNAL_VOLUME_CREDENTIALS` for B). If B, also record `EXTERNAL_VOLUME_NAME`.

---

### Step 1.6: Integration Name

**Ask**:
```
What would you like to name your catalog integration?

Guidelines:
- Alphanumeric characters and underscores only
- Must be unique in your Snowflake account

Default suggestion: biglake_catalog_int
```

**Record**: `INTEGRATION_NAME`

---

### Step 1.7: Prerequisites Summary

**Present checklist**:
```
Prerequisites Checklist
═══════════════════════════════════════════════════════════

✓ GCP Project ID:        <GCP_PROJECT_ID>
✓ GCP Project Number:    <GCP_PROJECT_NUMBER>
✓ GCS Base Location:     <GCS_BASE_LOCATION>   (→ CATALOG_NAME)
✓ Workload Identity Pool: <POOL_ID>
✓ OIDC Provider:         <PROVIDER_ID>
✓ OAuth Audience:        //iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/providers/<PROVIDER_ID>
✓ OAuth Allowed Scopes:  <OAUTH_ALLOWED_SCOPES>
✓ Integration Name:      <INTEGRATION_NAME>

Auth model: Workload identity federation (TOKEN_EXCHANGE).
No client secret or long-lived key is needed. IAM roles are granted to
the Snowflake federated subject AFTER the integration is created.
═══════════════════════════════════════════════════════════
```

**⚠️ STOPPING POINT**: "Does everything look correct? Ready to proceed with creating the catalog integration?"

- If yes → Return to main skill → Step 2 (Create)
- If changes needed → Ask what to update

---

## Output

Complete validated prerequisites checklist ready for catalog integration creation.

## Next Steps

After the user confirms prerequisites:
- Return to main skill
- Proceed to Step 2: Configuration & Creation
- Load `create/SKILL.md`
