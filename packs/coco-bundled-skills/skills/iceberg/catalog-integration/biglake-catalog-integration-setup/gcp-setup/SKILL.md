---
name: biglake-gcp-setup
description: "Google Cloud-side setup for BigLake Iceberg: gcloud auth, enable APIs, GCS bucket, BigLake catalog + namespace, Iceberg tables (via gcloud, no Spark), workload identity pool + OIDC provider, IAM grants. Sub-skill of biglake-catalog-integration-setup."
parent_skill: biglake-catalog-integration-setup
---

# Google Cloud-Side BigLake Setup

> **Sub-skill of `biglake-catalog-integration-setup`** — provisions the Google Cloud prerequisites so Snowflake can connect to BigLake via workload identity federation.
>
> This skill is complete on its own if you only need the Google Cloud infrastructure. If you also want Snowflake to query these tables, it hands off to the parent skill at the end.

> **Naming note**: BigLake is now "Lakehouse for Apache Iceberg" (renamed 2026-04-20), but the `gcloud`/`bq` CLI, IAM role names, and the `biglake.googleapis.com` endpoint still say "BigLake". Commands below use the unchanged CLI names.

## Agent execution rules

> **Follow these rules in every phase:**
> 1. **Execute commands via bash.** Run each `gcloud`/`gcloud storage` command shown here with the bash tool so the user sees real output. Never silently substitute a text explanation for a command.
> 2. **Ask for object names before creating anything.** Collect the name for every resource (bucket, catalog, namespace, table, pool, provider) up front — do not auto-generate names. See the naming step below.
> 3. **Honor the "already exists?" stopping points.** Before creating a bucket, catalog, namespace, or tables, ask whether the user already has them. Skip creation when they do — reuse existing resources.
> 4. **Continue through benign errors.** `AlreadyExists`-type errors are safe to note and move past. Stop only on genuine blockers (auth failures, permission denied).
> 5. **Run gcloud non-interactively.** Set `CLOUDSDK_CORE_DISABLE_PROMPTS=1` in the environment (or pass `--quiet`) so component-install and confirmation prompts don't hang the session. For IAM bindings, pass `--condition=None` to avoid the interactive condition prompt.
> 6. **Tables CAN be created with gcloud.** Use `gcloud biglake iceberg tables create --create-from-file=<schema.json>` (Phase 5) — no Spark required to create the table. Spark/Dataproc is only needed to *load bulk data* into the table.

## When to invoke

- User wants to provision Google Cloud so Snowflake can query BigLake Iceberg tables
- User needs a workload identity pool + OIDC provider trusting Snowflake
- User asked to run "GCP Setup" (main skill option A)

## Workflow routing — ask this first

**Before running any phases, collect (0a) the target and (0b) the names.**

**0a. Account / project / region:**
```
Which gcloud account and project should I use, and which region?
   - Run `gcloud config list` / `gcloud auth list` if unsure.
   - Confirm the target PROJECT_ID and a REGION (e.g. us-west1).
```
Capture `GCP_PROJECT_ID` and `GCP_REGION`.

**0b. Object names — ASK the user for each, do NOT auto-generate:**
```
What names should I use for:
   - GCS bucket           (lowercase, hyphens ok, globally unique)
   - BigLake namespace    (schema; letters/numbers/underscores)
   - Iceberg table        (letters/numbers/underscores)
   - Workload identity pool ID     (lowercase, hyphens, 4-32 chars)
   - OIDC provider ID              (lowercase, hyphens, 4-32 chars)
```
> **Note on the catalog name:** for a `gcs-bucket` catalog (Phase 4), the catalog identifier **is the bucket name** — you don't choose a separate catalog name. Snowflake's `CATALOG_NAME` is the `gs://` base path, not the catalog id.

Also decide which phases apply:
```
1. Do you already have a GCS bucket for the Iceberg data?
   (Y) Yes → skip bucket creation (Phase 3), just capture the name
   (N) No  → create one in Phase 3

2. Do you already have a BigLake catalog + namespace?
   (Y) Yes → skip Phase 4, capture catalog + namespace
   (N) No  → create them in Phase 4

3. Do you already have BigLake Iceberg tables?
   (Y) Yes → skip Phase 5
   (N) No  → create a table with gcloud in Phase 5 (no Spark needed)

4. Do you want to connect this to Snowflake after setup?
   (Y) Yes → hand off to the parent skill's Create Workflow at the end
   (N) No  → this skill is the final step
```
Only run the phases that apply.

---

## Phase 1 — Authentication & Project

**Goal**: Verify gcloud access and set the working project.

```bash
# Run gcloud non-interactively so install/confirm prompts don't hang the session
export CLOUDSDK_CORE_DISABLE_PROMPTS=1

# Verify you're authenticated (and switch account if needed: gcloud config set account <email>)
gcloud auth list

# Set the working project
gcloud config set project <GCP_PROJECT_ID>

# Capture the project NUMBER (needed for the audience + federated principal)
gcloud projects describe <GCP_PROJECT_ID> --format='value(projectNumber)'
```

**Capture**: `GCP_PROJECT_NUMBER`.

### Error recovery
- No active account → `gcloud auth login`
- `PERMISSION_DENIED` on `projects describe` → the account lacks access to the project; confirm the correct project or ask an admin.

> **If gcloud is not installed**: Direct the user to [Install the gcloud CLI](https://docs.cloud.google.com/sdk/docs/install), then `gcloud init`.

Confirm auth works and `GCP_PROJECT_ID` / `GCP_PROJECT_NUMBER` are captured before continuing.

---

## Phase 2 — Enable APIs

**Goal**: Enable the services BigLake + workload identity federation require.

```bash
gcloud services enable \
  biglake.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudresourcemanager.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  --project=<GCP_PROJECT_ID>
```

> `biglake.googleapis.com` is the BigLake API. `sts.googleapis.com` and `iamcredentials.googleapis.com` are required for token exchange.

---

## Phase 3 — GCS Bucket

> **First, ask**: "Do you already have a GCS bucket for the Iceberg data? If so, give me the name and I'll skip creation."
>
> - **Existing** → capture `BUCKET` (e.g. `my-bucket`) and skip to Phase 4.
> - **Create new** → continue.

**Goal**: Create a Cloud Storage bucket to hold the Iceberg data and metadata.

```bash
gcloud storage buckets create gs://<BUCKET> \
  --project=<GCP_PROJECT_ID> \
  --location=<GCP_REGION> \
  --uniform-bucket-level-access
```

**Capture**: `BUCKET` and the base location `gs://<BUCKET>/<PREFIX>` (e.g. `gs://<BUCKET>/iceberg-data`). This base location is your `CATALOG_NAME` / warehouse path later.

> **Region requirement**: The bucket region and the BigLake catalog region must be compatible. See [location requirements](https://docs.cloud.google.com/lakehouse/docs/understand-catalog-types#bucket_and_catalog_regions). Keep the bucket and catalog in the same region for simplicity.

### Error recovery
- Bucket name already taken globally → choose a different, globally-unique name.
- `HierarchicalNamespace` buckets are not supported with credential vending — use a standard bucket.

---

## Phase 4 — BigLake Catalog & Namespace

> **First, ask**: "Do you already have a BigLake catalog and namespace? If so, tell me their names and I'll skip creation."
>
> - **Existing** → capture `CATALOG_ID` and `NAMESPACE`, skip to Phase 5.
> - **Create new** → continue.

**Goal**: Create a BigLake Iceberg REST catalog, then a namespace, using the `gcloud biglake iceberg` command group.

**Create the catalog** (simplest is a single-bucket `gcs-bucket` catalog — its catalog id **is the bucket name**):
```bash
gcloud biglake iceberg catalogs create <BUCKET> \
  --catalog-type=gcs-bucket \
  --credential-mode=vended-credentials \
  --project=<GCP_PROJECT_ID>
```

> Set `--credential-mode` **at create time** to avoid a follow-up `catalogs update`. Use `vended-credentials` for the recommended path; for end-user / external-volume mode omit the flag (it defaults to `end-user`).

> **Catalog type & credential mode** — ASK the user, and **recommend vended credentials**:
> - `--catalog-type=gcs-bucket` — single bucket; catalog id = bucket name. Use `--catalog-type=biglake` for a multi-bucket (`bl://`) catalog with its own id and `--default-location`.
>
> **`CATALOG_NAME` by catalog type**: for a `gcs-bucket` catalog, Snowflake's `CATALOG_NAME` is the `gs://` bucket path. For a `biglake` (multi-bucket) catalog it is the catalog **resource path** `bl://projects/<GCP_PROJECT_ID>/catalogs/<CATALOG_ID>` — passing the bare catalog id fails with `Unsupported warehouse name format`. The `biglake` type also requires `end-user` credential mode + a Snowflake external volume (a vended `biglake` catalog rejects both `gcloud` table writes and external-volume reads).
> - `--credential-mode=vended-credentials` (**RECOMMENDED**) — the BigLake catalog vends short-lived storage credentials; the Snowflake catalog-linked database then needs **no external volume**. Requires granting the BigLake service account storage access (step 4a below), and the Snowflake integration must set `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS`.
> - `--credential-mode=end-user` (default) — the caller's identity accesses storage directly. Use this with the **external-volume** path: the Snowflake federated subject needs `storage.objectViewer` and you create a Snowflake GCS external volume for the CLD.
>
> You can switch an existing catalog's mode with `gcloud biglake iceberg catalogs update <BUCKET> --credential-mode=vended-credentials`.

### 4a. Vended-credentials only — grant the BigLake service account storage access

Skip this if you chose end-user / external-volume mode.

When the catalog is in vended-credentials mode, `catalogs create`/`update` prints an auto-provisioned **BigLake service account** (also in `catalogs describe` as `biglake-service-account`, e.g. `blirc-<PROJECT_NUMBER>-xxxx@gcp-sa-biglakerestcatalog.iam.gserviceaccount.com`). Grant it storage access on the bucket so it can vend credentials:

```bash
BL_SA=$(gcloud biglake iceberg catalogs describe <BUCKET> --project=<GCP_PROJECT_ID> \
  --format='value(biglake-service-account)')
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --role='roles/storage.objectUser' \
  --member="serviceAccount:${BL_SA}"
```

> Use `roles/storage.objectViewer` for read-only, `roles/storage.objectUser` if the CLD will also write.

**Create the namespace**:
```bash
gcloud biglake iceberg namespaces create <NAMESPACE> \
  --catalog=<BUCKET> \
  --project=<GCP_PROJECT_ID>
```

**Capture**: `CATALOG` (= `<BUCKET>` for gcs-bucket), `NAMESPACE`, and the catalog's base location for Snowflake's `CATALOG_NAME`. For a `gcs-bucket` catalog this is the **bucket root** `gs://<BUCKET>` (confirm via `catalogs describe` → `default-location`); include a `/<PREFIX>` only if your catalog's default-location has one.

> **Verify**: `gcloud biglake iceberg catalogs list --project=<GCP_PROJECT_ID>` and `gcloud biglake iceberg namespaces list --catalog=<BUCKET> --project=<GCP_PROJECT_ID>`.
>
> **Reference**: [Set up the Lakehouse (BigLake) Iceberg REST catalog](https://docs.cloud.google.com/lakehouse/docs/lakehouse-iceberg-rest-catalog).

---

## Phase 5 — Create BigLake Iceberg Tables

> **First, ask**: "Do you already have BigLake Iceberg tables? If so, we can skip this and go straight to workload identity setup."
>
> - **Existing** → skip to Phase 6.
> - **Create a table** → continue.

**Goal**: Create at least one Iceberg table in the BigLake REST catalog so Snowflake has something to discover.

> **You do NOT need Spark to create a table.** `gcloud biglake iceberg tables create` registers the table directly from an Iceberg schema JSON. Spark/Dataproc is only needed to **load bulk data** into the table (and even then, the Snowflake catalog-linked database is writable, so you can `INSERT` from Snowflake instead — see the parent skill's next-steps).

### 5.1 Create the table with gcloud (no Spark)

Write an Iceberg table-creation JSON, then create the table:

```bash
cat > table_creation.json <<'JSON'
{
  "name": "<TABLE>",
  "location": "gs://<BUCKET>/<NAMESPACE>/<TABLE>",
  "schema": {
    "type": "struct",
    "schema-id": 0,
    "fields": [
      { "id": 1, "name": "id",           "required": true,  "type": "long" },
      { "id": 2, "name": "name",         "required": false, "type": "string" },
      { "id": 3, "name": "created_date", "required": false, "type": "date" }
    ]
  },
  "stage-create": false
}
JSON

gcloud biglake iceberg tables create \
  --catalog=<BUCKET> \
  --namespace=<NAMESPACE> \
  --create-from-file=table_creation.json \
  --project=<GCP_PROJECT_ID>
```

> **Notes**:
> - `name` and `schema.fields` are required. Field `type` uses Iceberg types (`long`, `string`, `date`, `timestamp`, `boolean`, `double`, `decimal(p,s)`, etc.).
> - `location` must be nested under the namespace path (`gs://<BUCKET>/<NAMESPACE>/<TABLE>`); BigLake may append a random suffix.
> - This creates the table **metadata** (an empty table). That is enough for Snowflake to discover it via verification and a catalog-linked database.
> - Verify: `gcloud biglake iceberg tables list --catalog=<BUCKET> --namespace=<NAMESPACE> --project=<GCP_PROJECT_ID>`.

### 5.2 (Optional) Load data with Spark

Creating the table with `gcloud` (above) is enough for Snowflake to discover it. If you also need a Google-side bulk data load before querying elsewhere, load it with Spark: see [references/spark-data-load.md](../references/spark-data-load.md). You can also load data later from Snowflake via a catalog-linked database.

Confirm the table exists (or the user already has tables) before continuing.

---

## Phase 6 — Workload Identity Pool & OIDC Provider

**Goal**: Create the trust between Snowflake and Google Cloud so Snowflake can exchange its identity token for a Google Cloud access token.

> **Required permission**: creating the pool/provider needs `roles/iam.workloadIdentityPoolAdmin` (or Owner) on the project. Granting IAM to the federated subject (Phase 7 / create step) additionally needs `resourcemanager.projects.setIamPolicy` (e.g. `roles/resourcemanager.projectIamAdmin` or Owner). If you lack these, ask a project admin to grant them or to run Phases 6–7 for you.

### 6.1 Get the Snowflake issuer URL

Ask the user to run this in Snowflake (or run it if you have a connection):
```sql
SELECT SYSTEM$GET_WORKLOAD_IDENTITY_ISSUER_URL();
```
**Capture**: `SNOWFLAKE_ISSUER_URL`.

> **This is the linchpin**: the OIDC provider's issuer MUST equal this URL, or token exchange fails later.

> **STOP — approve before creating IAM infrastructure.** Phases 6.2–6.3 create a **new workload identity pool and OIDC provider** in `<GCP_PROJECT_ID>` — persistent IAM trust configuration on the project. Show the user the pool ID, provider ID, and issuer URL you're about to use, then wait for confirmation ("Proceed") before running the commands.

### 6.2 Create the workload identity pool

```bash
gcloud iam workload-identity-pools create <POOL_ID> \
  --project=<GCP_PROJECT_ID> \
  --location=global \
  --display-name="Snowflake BigLake"
```

### 6.3 Create the OIDC provider

```bash
gcloud iam workload-identity-pools providers create-oidc <PROVIDER_ID> \
  --project=<GCP_PROJECT_ID> \
  --location=global \
  --workload-identity-pool=<POOL_ID> \
  --issuer-uri='<SNOWFLAKE_ISSUER_URL>' \
  --attribute-mapping='google.subject=assertion.sub'
```

> Use the **Default audience** (the provider's own resource name). If you set a custom `--allowed-audiences`, you must use that exact value as `OAUTH_AUDIENCE` in the Snowflake integration.

### 6.4 Record the audience resource name

```
//iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/providers/<PROVIDER_ID>
```
**Capture**: `OAUTH_AUDIENCE` (this exact string).

### Error recovery
- `ALREADY_EXISTS` → the pool/provider exists; list and reuse:
  ```bash
  gcloud iam workload-identity-pools list --location=global --project=<GCP_PROJECT_ID>
  gcloud iam workload-identity-pools providers list \
    --location=global --workload-identity-pool=<POOL_ID> --project=<GCP_PROJECT_ID>
  ```
- `PERMISSION_DENIED` / `IAM_PERMISSION_DENIED` with `permission: iam.workloadIdentityPools.create` → the active account lacks `roles/iam.workloadIdentityPoolAdmin` (or Owner) on the project. A self-grant will also fail if you don't have `resourcemanager.projects.setIamPolicy`. Resolution: ask a project admin to grant `roles/iam.workloadIdentityPoolAdmin`, or use a project where you have it (you'll recreate the bucket/catalog/namespace/table there too).

---

## Phase 7 — IAM Grants to the Federated Subject

> **STOP — approve before granting IAM.** The commands in this phase add **IAM policy bindings** on the project (and optionally the data bucket) — persistent authorization changes. Show the user the roles and members you intend to bind, then wait for confirmation ("Proceed") before running them.

> **Note**: The exact federated *subject* value comes from Snowflake AFTER the catalog integration is created (`DESC CATALOG INTEGRATION` → `WORKLOAD_IDENTITY_FEDERATION_SUBJECT`). So the final IAM grant happens in the parent `create/SKILL.md` Step 2.6. This phase pre-grants pool-wide access if you want it in place beforehand, or you can defer entirely to create/.

If you want to grant to the whole pool now (all identities from this pool), use a `principalSet`:
```bash
# Read-only example — BigLake viewer at project level
gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
  --role='roles/biglake.viewer' \
  --member='principalSet://iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/*' \
  --condition=None

# GCS object read on the data bucket
# (external-volume mode only; skip for vended-credentials mode)
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --role='roles/storage.objectViewer' \
  --member='principalSet://iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/*'
```

> **Least privilege**: `principalSet://.../*` grants to every identity in the pool. To grant to only the specific Snowflake subject, defer to `create/SKILL.md` Step 2.6, which uses `principal://.../subject/<subject_id>` after the subject is known.
>
> **Always required on the subject**: `roles/serviceusage.serviceUsageConsumer` (the `x-goog-user-project` billing header requires the caller to be allowed to use the project). Without it, verification fails with a `serviceusage.services.use` error.
>
> **Role reference** (Google Lakehouse required roles):
> - Read: `roles/biglake.viewer` (+ `roles/storage.objectViewer` — on the subject in external-volume mode, on the BigLake SA in vended mode)
> - Write: `roles/biglake.editor` + `roles/storage.objectUser`
> - Admin: `roles/biglake.admin` + `roles/storage.admin`
> - Always: `roles/serviceusage.serviceUsageConsumer`

---

## Handoff to Snowflake

> **STOP — Ask the user before proceeding.**
> "Your Google Cloud setup is complete. Do you want to connect this to Snowflake now (catalog integration + verification)?"
>
> - **No** → GCP setup is done. Summarize what was built and exit.
> - **Yes** → return to the parent `biglake-catalog-integration-setup` skill's **Create Workflow** with these collected variables.

| Variable needed by parent skill | Source |
|---------------------------------|--------|
| `GCP_PROJECT_ID` | Phase 1 |
| `GCP_PROJECT_NUMBER` | Phase 1 |
| `GCS_BASE_LOCATION` (→ `CATALOG_NAME`) | Phase 3 / 4 |
| `POOL_ID`, `PROVIDER_ID` | Phase 6 |
| `OAUTH_AUDIENCE` | Phase 6.4 |
| `NAMESPACE` (for verification) | Phase 4 / 5 |

Tell the user:
> Google Cloud side is ready. Your workload identity pool + OIDC provider trust the Snowflake issuer, and (optionally) BigLake Iceberg tables exist.
> Next: create the Snowflake catalog integration and grant IAM to the federated subject.
> Returning to the BigLake catalog integration setup workflow → Create Workflow (Step 2).

---

## Stopping points summary

| Phase | Gate | What to confirm |
|-------|------|-----------------|
| Phase 1 | Confirm | gcloud auth works; project ID + number captured |
| Phase 3 | Confirm | Bucket already exists? (skip) or create |
| Phase 4 | Confirm | Catalog + namespace exist? (skip) or create |
| Phase 5 | Confirm | Tables exist? (skip) or create with gcloud |
| Phase 6 | **STOP** | Approve creating the workload identity pool + OIDC provider (IAM infra) |
| Phase 7 | **STOP** | Approve IAM policy bindings on the project / bucket |
| Handoff | Confirm | Connect to Snowflake now? |

## Variables to collect

| Variable | Example | Phase |
|----------|---------|-------|
| `GCP_PROJECT_ID` | `my-analytics-project` | 1 |
| `GCP_PROJECT_NUMBER` | `123456789012` | 1 |
| `GCP_REGION` | `us-central1` | 0 / 3 |
| `BUCKET` | `my-iceberg-bucket` | 3 |
| `GCS_BASE_LOCATION` | `gs://my-iceberg-bucket/iceberg-data` | 3 / 4 |
| `CATALOG_ID` | `my_catalog` | 4 |
| `NAMESPACE` | `analytics` | 4 / 5 |
| `POOL_ID` | `snowflake-pool` | 6 |
| `PROVIDER_ID` | `snowflake-oidc` | 6 |
| `OAUTH_AUDIENCE` | `//iam.googleapis.com/projects/123456789012/locations/global/workloadIdentityPools/snowflake-pool/providers/snowflake-oidc` | 6.4 |

## Documentation

- [Set up the Lakehouse (BigLake) Iceberg REST catalog](https://docs.cloud.google.com/lakehouse/docs/lakehouse-iceberg-rest-catalog)
- [Query Iceberg tables with Spark and BigQuery](https://docs.cloud.google.com/lakehouse/docs/use-biglake-catalog-iceberg-rest-catalog)
- [Configure Workload Identity Federation with other providers](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers)
- [Configure a catalog integration for Google Cloud BigLake Metastore](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-biglake)
