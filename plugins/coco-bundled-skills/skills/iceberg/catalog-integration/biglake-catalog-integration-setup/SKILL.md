---
name: biglake-catalog-integration-setup
description: "Setup and verify catalog integration for Google Cloud BigLake Metastore (Lakehouse runtime catalog) using workload identity federation. Triggers: create biglake catalog integration, connect snowflake to biglake, connect snowflake to google cloud, biglake metastore, bigquery metastore, lakehouse iceberg rest catalog, google cloud iceberg, gcp iceberg, biglake iceberg rest, workload identity federation snowflake gcp, token exchange gcp catalog integration, query biglake tables from snowflake, troubleshoot biglake integration, verify biglake catalog integration, fix biglake connection, debug biglake iceberg, gcloud iceberg setup, biglake.googleapis.com."
---

# Google Cloud BigLake Metastore Catalog Integration

Setup, verify, or troubleshoot a Snowflake catalog integration for Google Cloud BigLake Metastore (the Iceberg REST catalog exposed at `https://biglake.googleapis.com/iceberg/v1/restcatalog`).

> **Naming note**: As of 2026-04-20, Google renamed **BigLake** to **Lakehouse for Apache Iceberg** and **BigLake metastore** to the **Lakehouse runtime catalog**. The APIs, `gcloud`/`bq` CLI commands, IAM role names, and the `biglake.googleapis.com` endpoint are unchanged and still say "BigLake". Snowflake documentation also still uses "BigLake Metastore". This skill uses "BigLake" to match the CLI and Snowflake surface.

## What makes BigLake different

Unlike Glue (SigV4/trust policy) or Unity Catalog (OAuth client secret), BigLake authenticates with **Google Cloud workload identity federation** using an OAuth **token exchange** grant. This means:
- **No long-lived keys or client secrets** — Snowflake presents its own identity token and exchanges it for a short-lived Google Cloud access token.
- **Two data-access modes** — **vended credentials (recommended)**: the BigLake catalog vends short-lived storage credentials and the catalog-linked database needs no external volume; or **external volume**: Snowflake uses a GCS external volume (catalog in end-user mode). Choose per the create step; the skill recommends vended credentials.
- **No PrivateLink** — public connectivity only (Google does not offer a private BigLake REST endpoint at this time).
- **BigLake catalog, namespace, and tables are all created with `gcloud biglake iceberg ...`** — no Spark required to create tables. The `gcp-setup` sub-skill provisions everything with `gcloud`; Spark/Dataproc is only needed to load bulk data (and the catalog-linked database is writable, so Snowflake can load data too).

## Two warehouse flavours — which direction?

The REST endpoint is the same, but the catalog's **warehouse** decides who owns the tables. Pick the pattern that matches who writes:

- **Pattern A — `gs://<bucket>` (default, this skill's main path):** the BigLake catalog owns the Iceberg tables (files in GCS). **Snowflake writes** via a catalog-linked database; **BigQuery reads them live** via `project.catalog.namespace.table`. Credential vending is supported (no external volume). BigQuery cannot DML these tables today (read-only; write interop is a Google preview).
- **Pattern B — `bq://projects/<project>` (BigQuery federation):** the tables are BigQuery-owned Apache Iceberg *managed* tables. **BigQuery writes**; **Snowflake reads** via a catalog integration + external volume (vending is not supported here). See [references/bigquery-federation.md](references/bigquery-federation.md).

## Intent Routing (FIRST)

**Ask the user**:
```
What would you like to do?

A: Set up Google Cloud infrastructure (bucket, BigLake catalog, namespace, workload identity)
   → gcloud provisioning of GCS + BigLake catalog + workload identity pool/provider + IAM
   → Creates the BigLake Iceberg table with gcloud (no Spark; Spark only for bulk data load)

B: Create a new catalog integration for BigLake
   → Set up Snowflake to connect to Google Cloud BigLake Metastore (workload identity federation)

C: Verify an existing catalog integration
   → Test connection and list namespaces/tables

D: Troubleshoot a catalog integration
   → Diagnose and fix connection issues
```

**Route based on response**:
- **A (GCP Setup)** → **Load** `gcp-setup/SKILL.md` then follow [GCP Setup Workflow](#gcp-setup-workflow)
- **B (Create)** → **Load** `setup/SKILL.md` then follow [Create Workflow](#create-workflow)
- **C (Verify)** → **Load** `verify/SKILL.md` then follow [Verify Workflow](#verify-workflow)
- **D (Troubleshoot)** → **Load** `references/troubleshooting.md` then follow [Troubleshoot Workflow](#troubleshoot-workflow)

---

## Create Workflow

Load `setup/SKILL.md` before proceeding with this workflow.

Create a new catalog integration connecting Snowflake to Google Cloud BigLake Metastore.

### Step 1: Prerequisites

Follow `setup/SKILL.md` to collect one-by-one:
1. Confirm BigLake setup exists (BigLake catalog + Iceberg tables, or run GCP Setup first)
2. Google Cloud project ID
3. GCS base location for your BigLake tables (e.g., `gs://my-bucket/iceberg-data`) → `CATALOG_NAME`
4. Workload identity pool ID and OIDC provider ID (or run GCP Setup to create them)
5. OIDC provider audience resource name → `OAUTH_AUDIENCE`
6. OAuth allowed scopes (default `https://www.googleapis.com/auth/bigquery`)
7. Integration name

Confirm prerequisites before proceeding. If the workload identity pool/provider and IAM grants don't exist yet, offer to run the [GCP Setup Workflow](#gcp-setup-workflow) first.

### Step 2: Create Integration

**Load** `create/SKILL.md` and follow its workflow:

1. Retrieve the Snowflake workload identity issuer URL (`SYSTEM$GET_WORKLOAD_IDENTITY_ISSUER_URL()`)
2. Confirm the GCP OIDC provider trusts that issuer (created in GCP Setup)
3. Generate the `CREATE CATALOG INTEGRATION` SQL
4. Review SQL with user before executing
5. Execute creation
6. `DESC CATALOG INTEGRATION` → retrieve `WORKLOAD_IDENTITY_FEDERATION_SUBJECT`
7. Guide user to grant Google Cloud IAM roles to the federated subject principal
8. Confirm IAM grant applied

(The mandatory review-before-execute and IAM-grant stopping points are enforced in `create/SKILL.md`.)

### Step 3: Verify

→ Continue to [Verify Workflow](#verify-workflow)

---

## Verify Workflow

Load `verify/SKILL.md` before proceeding with this workflow.

Verify an existing catalog integration is working correctly.

### Step V1: Get Integration Name

**Ask**: "What is the name of your catalog integration?"

If user doesn't know:
```sql
SHOW CATALOG INTEGRATIONS;
```

### Step V2: Check Integration Status

Follow `verify/SKILL.md`, which loads the shared verification workflow.

Run verification checks:
```sql
-- Check integration exists and is enabled
SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';

-- Verify connection (confirms token exchange + headers work)
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');

-- List namespaces
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');

-- List tables in a namespace
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<namespace>');
```

### Step V3: Report Results

**If all checks pass**:
```
✅ Integration verified successfully
- Status: ENABLED
- Connection: Working
- Namespaces: <count> discovered
- Tables: Accessible
```

**If any check fails** → Continue to [Troubleshoot Workflow](#troubleshoot-workflow)

### Step V4: Next Steps

**If verification succeeded**:

**Load** `shared/next-steps/SKILL.md` (path: `../shared/next-steps/SKILL.md`)

Guide user through options for accessing catalog tables:
- Option A: Create individual Iceberg tables
- Option B: Create catalog-linked database (recommended)

---

## Troubleshoot Workflow

Load `references/troubleshooting.md` to have error patterns and solutions available.

Diagnose and fix issues with an existing catalog integration.

### Step T1: Get Integration Name

**Ask**: "What is the name of your catalog integration?"

### Step T2: Gather Error Information

**Ask**: "What error or issue are you experiencing?"

Common symptoms:
- Integration creation failed
- Verification returns error
- Cannot list namespaces
- Cannot see tables
- Token exchange / OAuth errors
- IAM permission denied

### Step T3: Diagnose

Use error patterns from `references/troubleshooting.md` to diagnose.

Run diagnostics:
```sql
-- Check integration details (includes WORKLOAD_IDENTITY_FEDERATION_SUBJECT)
DESC CATALOG INTEGRATION <integration_name>;

-- Test connection
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

### Step T4: Match Error Pattern

Common issues and solutions in `references/troubleshooting.md`:
1. Token exchange failure (OIDC provider issuer/audience mismatch)
2. IAM permission denied (federated subject not granted required roles)
3. Missing `x-goog-user-project` header / billing project not set
4. BigLake API not enabled
5. Catalog / GCS base location not found or wrong `CATALOG_NAME`
6. Namespace/table discovery returns empty (roles or wrong namespace)
7. BigLake Iceberg REST read-request rate limit exceeded
8. Iceberg V1 tables not supported (must upgrade to V2/V3)

Present the diagnosis and wait for user direction before applying fixes.

---

## GCP Setup Workflow

Load `gcp-setup/SKILL.md` before proceeding with this workflow.

Provision the Google Cloud side as a prerequisite for the Snowflake catalog integration. This covers:
1. gcloud authentication and project selection
2. Enabling required APIs (BigLake, IAM, STS, Storage, BigQuery)
3. GCS bucket creation (with a stopping point to skip if it already exists)
4. BigLake catalog + namespace creation (with a stopping point to skip if they exist)
5. BigLake Iceberg table creation via `gcloud biglake iceberg tables create` (no Spark; a stopping point to skip if tables exist)
6. Workload identity pool + OIDC provider creation (trusting the Snowflake issuer URL)
7. IAM role grants to the Snowflake federated subject

After GCP setup completes, continue to the [Create Workflow](#create-workflow).

---

## Scope

This skill covers **end-to-end BigLake Iceberg setup**:

**Snowflake-side** (setup/, create/, verify/, references/):
- ✅ Creating catalog integrations for BigLake (workload identity federation / token exchange)
- ✅ Retrieving the workload identity issuer URL and federated subject
- ✅ Reading BigQuery-owned managed Iceberg tables via `bq://` federation + external volume (Pattern B → `references/bigquery-federation.md`)
- ✅ Verification
- ✅ Troubleshooting

**GCP-side** (gcp-setup/):
- ✅ gcloud auth, API enablement
- ✅ GCS bucket, BigLake catalog, and namespace creation
- ✅ Workload identity pool + OIDC provider + IAM grants
- ✅ BigLake Iceberg table creation with `gcloud` (Spark only for bulk data load)
- ✅ Cross-engine interop validation via native BigQuery query (`project.catalog.namespace.table`)

**Out of scope / not supported**:
- ❌ PrivateLink / private connectivity (not offered for BigLake)
- ➕ External volume — optional (only for external-volume delegation mode; vended-credentials mode needs none)
- ❌ Deep Dataproc/Spark cluster administration → [Set up the Lakehouse Iceberg REST catalog](https://docs.cloud.google.com/lakehouse/docs/lakehouse-iceberg-rest-catalog)
- ❌ Creating tables or catalog-linked databases in Snowflake (use shared `next-steps` skill)

---

## Quick Reference

**Catalog Integration SQL (workload identity federation)**:
```sql
-- Prerequisite: get the Snowflake issuer URL for the GCP OIDC provider
SELECT SYSTEM$GET_WORKLOAD_IDENTITY_ISSUER_URL();

CREATE OR REPLACE CATALOG INTEGRATION <integration_name>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://biglake.googleapis.com/iceberg/v1/restcatalog'
    CATALOG_NAME = '<gcs_base_location>'          -- e.g. gs://my-bucket/iceberg-data (Pattern A); or bq://projects/<project> (Pattern B)
    ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS   -- Pattern A recommended; use EXTERNAL_VOLUME_CREDENTIALS for external-volume mode and always for bq:// (Pattern B)
    ADDITIONAL_HEADERS = (
      "x-goog-user-project" = '<gcp_project_id>'  -- REQUIRED (billing project); key MUST be double-quoted
    )
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_GRANT_TYPE = TOKEN_EXCHANGE
    OAUTH_TOKEN_URI = 'https://sts.googleapis.com/v1/token'
    OAUTH_AUDIENCE = '<gcp_oidc_audience_url>'     -- //iam.googleapis.com/projects/<num>/locations/global/workloadIdentityPools/<pool>/providers/<provider>
    OAUTH_ALLOWED_SCOPES = ('https://www.googleapis.com/auth/bigquery')
  )
  ENABLED = TRUE;

-- Retrieve the federated subject to grant IAM roles in GCP
DESC CATALOG INTEGRATION <integration_name>;
```

> **BigLake notes**:
> - `CATALOG_URI` is fixed: `https://biglake.googleapis.com/iceberg/v1/restcatalog`
> - `CATALOG_NAME` is typically the GCS base path for your BigLake tables (e.g. `gs://my-bucket/iceberg-data`)
> - `ADDITIONAL_HEADERS` with `x-goog-user-project` is **required** — Google attributes usage/billing to this project
> - `OAUTH_GRANT_TYPE = TOKEN_EXCHANGE` + `OAUTH_TOKEN_URI = https://sts.googleapis.com/v1/token` enables workload identity federation (no keys/secrets)
> - `OAUTH_AUDIENCE` is the OIDC provider's full audience resource name (recorded when you create the provider in GCP)
> - After creating, `DESC CATALOG INTEGRATION` returns `WORKLOAD_IDENTITY_FEDERATION_SUBJECT` — grant IAM roles to `principal://.../subject/<that value>`

**Diagnostic Commands**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<name>';
DESC CATALOG INTEGRATION <name>;
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<name>');
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<name>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<name>', '<namespace>');
```

---

## Success Criteria

- ✅ GCP OIDC provider trusts the Snowflake issuer URL
- ✅ Integration shows `ENABLED = TRUE`
- ✅ Federated subject granted the required BigLake/Storage IAM roles
- ✅ `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns success
- ✅ Namespaces discoverable
- ✅ Tables visible

---

## Validate cross-engine interoperability (BigQuery)

Prove Snowflake and Google Cloud operate on the **same** Iceberg table (analogous to validating a Glue table from Athena). BigQuery can query Lakehouse/BigLake Iceberg REST catalog tables **natively** — no external table or BigQuery connection needed.

**Steps:**
1. Write data from Snowflake via the catalog-linked database (writes require `roles/biglake.editor` on the federated subject; see next-steps).
2. In BigQuery, query the same table using the four-part `project.catalog.namespace.table` syntax:
   ```bash
   bq --project_id=<GCP_PROJECT_ID> query --use_legacy_sql=false \
     "SELECT * FROM \`<GCP_PROJECT_ID>.<CATALOG>.<NAMESPACE>.<TABLE>\` ORDER BY 1;"
   ```
   - `<CATALOG>` is the BigLake catalog id (for a `gcs-bucket` catalog, that's the bucket name; quote hyphenated names inside the backtick-wrapped identifier).
   - The querying identity needs `roles/biglake.viewer` + `roles/serviceusage.serviceUsageConsumer` (and `roles/storage.objectViewer` unless using vended credentials) on the project.
3. Confirm BigQuery returns the same rows Snowflake wrote. Reads are **live** — a new Snowflake `INSERT` appears on BigQuery's next `SELECT` with no refresh.

> **Direction matters:** on a `gs://`-flavour catalog, BigQuery **reads** the shared table but **cannot run DML** against it today (`DML statements are only supported over tables that have data stored in BigQuery`). Read + write interop on these tables is a Google **preview**. For BigQuery-side **writes**, use Pattern B (`bq://` federation) — BigQuery owns and writes the table, Snowflake reads it. See [references/bigquery-federation.md](references/bigquery-federation.md).

> This native four-part-name read is the equivalent of Glue's "query the same Iceberg table from Athena" validation, and works for both `gcs-bucket` and multi-bucket `biglake` catalogs.

---

## Documentation

- [Configure a catalog integration for Google Cloud BigLake Metastore](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-biglake)
- [CREATE CATALOG INTEGRATION (Apache Iceberg REST)](https://docs.snowflake.com/en/sql-reference/sql/create-catalog-integration-rest)
- [Snowflake Iceberg Tables](https://docs.snowflake.com/user-guide/tables-iceberg)
- [CREATE DATABASE (catalog-linked)](https://docs.snowflake.com/sql-reference/sql/create-database-catalog-linked)
- [Set up the Lakehouse (BigLake) Iceberg REST catalog](https://docs.cloud.google.com/lakehouse/docs/lakehouse-iceberg-rest-catalog) (Google)
- [Configure Workload Identity Federation with other providers](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers) (Google)
