# Troubleshooting BigLake Metastore Catalog Integration

Guide for diagnosing and fixing issues with Google Cloud BigLake Metastore catalog integrations (workload identity federation).

## When to Load

Load this reference when:
- `SYSTEM$VERIFY_CATALOG_INTEGRATION()` returns failure
- Namespace or table discovery fails
- Token exchange / OAuth errors occur
- IAM permission errors occur
- Unexpected behavior during verification

## Important: ALTER CATALOG INTEGRATION Limitations

**`REST_CONFIG` cannot be altered.** Changing `CATALOG_URI`, `CATALOG_NAME`, or `ADDITIONAL_HEADERS` requires `CREATE OR REPLACE`.

For BigLake, `REST_AUTHENTICATION` uses token exchange with no client secret, so there is **no secret to rotate**. If you need to change `OAUTH_AUDIENCE`, `OAUTH_TOKEN_URI`, `OAUTH_GRANT_TYPE`, or scopes, recreate the integration:
```sql
CREATE OR REPLACE CATALOG INTEGRATION <integration_name> ... ;
```

---

## Common Issues

### 1. Token Exchange Failure (Issuer / Audience Mismatch)

**Error Pattern**:
```
Failed to exchange token
invalid_grant / invalid_target
STS token exchange failed
SYSTEM$VERIFY_CATALOG_INTEGRATION returns success:false with an STS/OAuth error
```

**Cause**: The GCP workload identity OIDC provider's **issuer URI** does not match the Snowflake issuer URL, or the `OAUTH_AUDIENCE` in the integration does not exactly match the provider's audience resource name. This is the most common BigLake failure.

**Debug Steps**:

1. Get the Snowflake issuer URL:
   ```sql
   SELECT SYSTEM$GET_WORKLOAD_IDENTITY_ISSUER_URL();
   ```

2. Compare it against the OIDC provider's issuer:
   ```bash
   gcloud iam workload-identity-pools providers describe <PROVIDER_ID> \
     --location=global --workload-identity-pool=<POOL_ID> \
     --project=<GCP_PROJECT_ID> \
     --format='value(oidc.issuerUri)'
   ```
   They must be **identical**.

3. Check the integration's `OAUTH_AUDIENCE`:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   It must be the provider's full audience resource name:
   `//iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/providers/<PROVIDER_ID>`
   Note it uses the project **number**, not the project ID.

**Solutions**:
- If the issuer differs: recreate the OIDC provider with the correct `--issuer-uri`, or create a new provider and update the integration's `OAUTH_AUDIENCE` to point at it (`CREATE OR REPLACE`).
- If the audience is wrong (e.g., used project ID instead of number): recreate the integration with the correct `OAUTH_AUDIENCE`.

---

### 2. IAM Permission Denied (Federated Subject Not Granted)

**Error Pattern**:
```
PERMISSION_DENIED
caller does not have permission
Permission 'biglake.tables.list' denied
403 when listing namespaces or tables
```

**Cause**: Token exchange succeeded, but the Snowflake federated subject lacks the BigLake / Cloud Storage IAM roles.

**Debug Steps**:

1. Get the federated subject:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Note `WORKLOAD_IDENTITY_FEDERATION_SUBJECT`.

2. Check the IAM policy for that principal:
   ```bash
   gcloud projects get-iam-policy <GCP_PROJECT_ID> \
     --flatten='bindings[].members' \
     --filter='bindings.members:workloadIdentityPools' \
     --format='table(bindings.role, bindings.members)'
   ```

**Solutions**:
- Always grant `roles/serviceusage.serviceUsageConsumer` + `roles/biglake.viewer` to the subject:
  ```bash
  gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
    --role='roles/biglake.viewer' \
    --member='principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<subject_id>' \
    --condition=None

  # External-volume mode ONLY — skip in vended-credentials mode.
  # (In vended mode the BigLake service account handles storage; if you see storage
  #  errors in vended mode, grant that SA roles/storage.objectUser — see gcp-setup Phase 4a.)
  gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
    --role='roles/storage.objectViewer' \
    --member='principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<subject_id>'
  ```
- Role reference: read = `roles/biglake.viewer` (+ `roles/storage.objectViewer` on the subject **only in external-volume mode**); write = `roles/biglake.editor` (+ `roles/storage.objectUser`); admin = `roles/biglake.admin` (+ `roles/storage.admin`). Always: `roles/serviceusage.serviceUsageConsumer` on the subject.
- IAM changes can take a minute or two to propagate — wait and retry before assuming failure.

---

### 3. Missing or Wrong `x-goog-user-project` Header

**Error Pattern**:
```
PERMISSION_DENIED: ... requires a user project
The request is missing a valid billing/user project
USER_PROJECT_DENIED
```

**Cause**: BigLake requires the `x-goog-user-project` header so Google can attribute usage to a billing project. It's missing, or set to a project the caller can't use for billing.

**Debug Steps**:
1. Check the integration:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
   Confirm `ADDITIONAL_HEADERS` includes `"x-goog-user-project" = '<project_id>'`.

**Solutions**:
- Recreate the integration with the header set to a valid GCP project ID that the federated identity can bill against (typically the same project hosting BigLake).
- Ensure the federated subject has `roles/serviceusage.serviceUsageConsumer` on the project. This permission (`serviceusage.services.use`) is **NOT** included in `roles/biglake.viewer` or `roles/biglake.editor` — grant it explicitly.

---

### 4. BigLake API Not Enabled

**Error Pattern**:
```
SERVICE_DISABLED
BigLake API has not been used in project ... before or it is disabled
403 accessNotConfigured
```

**Cause**: The `biglake.googleapis.com` API is not enabled in the billing/user project.

**Solution**:
```bash
gcloud services enable biglake.googleapis.com --project=<GCP_PROJECT_ID>
```

---

### 5. Catalog / GCS Base Location Not Found (Wrong CATALOG_NAME)

**Error Pattern**:
```
404 Not Found
NoSuchNamespace / catalog not found
CATALOG_NAME does not resolve to a warehouse
```

**Cause**: `CATALOG_NAME` doesn't match the GCS base location / warehouse path of your BigLake catalog.

**Debug Steps**:
1. Check the integration's `CATALOG_NAME`:
   ```sql
   DESC CATALOG INTEGRATION <integration_name>;
   ```
2. Confirm it matches the warehouse/base path used when the BigLake catalog was created (e.g. `gs://my-bucket/iceberg-data`).

**Solution**: Recreate the integration with the correct GCS base location as `CATALOG_NAME`.

---

### 6. Empty Namespace / Table List

**Error Pattern**:
```
SYSTEM$LIST_NAMESPACES_FROM_CATALOG returns []
SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG returns []
```

**Cause**: No tables exist yet, the namespace name is wrong, or the federated subject lacks read access.

**Debug Steps**:
1. Confirm tables exist in BigLake (via Spark/console).
2. List namespaces to confirm spelling/case:
   ```sql
   SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
   ```
3. Confirm `roles/biglake.viewer` is granted to the federated subject (Issue #2).

**Solution**: Create tables (see `gcp-setup/SKILL.md` Phase 5 Spark snippet), correct the namespace, or grant read roles.

---

### 7. BigLake Iceberg REST Read Rate Limit Exceeded

**Error Pattern**:
```
429 Too Many Requests
RESOURCE_EXHAUSTED
Quota exceeded for Iceberg REST Catalog read requests per minute
```

**Cause**: Google enforces a default per-minute quota on BigLake Iceberg REST read requests; a busy Snowflake workload can exceed it.

**Solution**:
- In the Google Cloud console: **IAM & Admin → Quotas & System Limits**, filter by the **BigLake API**, find **Iceberg REST Catalog read requests per minute**, and raise the limit.
- If the max allowed value is still too low, open a Google Cloud support ticket to request a higher maximum.

---

### 8. Iceberg V1 Tables Not Supported

**Error Pattern**:
```
Unsupported Iceberg format version
Table is V1; V2/V3 required
```

**Cause**: The BigLake Iceberg REST catalog endpoint supports Iceberg V2 (GA) and V3 (preview), not V1.

**Solution**: Upgrade V1 tables to V2 before use — see [Upgrade Iceberg V1 tables to V2](https://docs.cloud.google.com/lakehouse/docs/update-tables).

---

---

### 9. Cannot Create Workload Identity Pool / Provider (setup-time)

**Error Pattern**:
```
IAM_PERMISSION_DENIED
permission: iam.workloadIdentityPools.create
Policy update access denied  (when self-granting the role)
```

**Cause**: The active gcloud account lacks `roles/iam.workloadIdentityPoolAdmin` (or Owner) on the project. A self-grant via `add-iam-policy-binding` additionally fails if the account lacks `resourcemanager.projects.setIamPolicy`.

**Resolution**:
- Ask a project admin to grant `roles/iam.workloadIdentityPoolAdmin` (create pool/provider) and, for the federated-subject IAM grant, `roles/resourcemanager.projectIamAdmin` (or Owner).
- Or switch to a project where you already have these roles — recreate the bucket, catalog, namespace, and table there too, then continue.
- Confirm the active account with `gcloud config get-value account`; switch with `gcloud config set account <email>` (run `gcloud auth login <email>` first if the account isn't credentialed).

---

### 10. serviceusage.services.use Denied (billing project)

**Error Pattern**:
```
Forbidden: Caller does not have required permission to use project <project>.
Grant the caller the roles/serviceusage.serviceUsageConsumer role, or a custom
role with the serviceusage.services.use permission
```

**Cause**: The `x-goog-user-project` header names a billing project the federated subject isn't allowed to use. `roles/biglake.viewer` does not include `serviceusage.services.use`.

**Resolution**: Grant `roles/serviceusage.serviceUsageConsumer` to the federated subject principal on the project, then wait ~75s and re-verify:
```bash
gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
  --role='roles/serviceusage.serviceUsageConsumer' \
  --member='principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<subject_id>' \
  --condition=None
```

---

### 11. CLD Creation Fails: "credential vending not enabled … specify EXTERNAL_VOLUME"

**Error Pattern**:
```
Failed to validate option 'LINKED_CATALOG.CATALOG': Catalog integration '<name>'
did not have credential vending enabled. If you did not provide an external
volume, please specify an external volume via the EXTERNAL_VOLUME option.
```

**Cause**: `CREATE DATABASE … LINKED_CATALOG` needs a data-access path. The integration is in `EXTERNAL_VOLUME_CREDENTIALS` mode (default) but no external volume was given, and the BigLake catalog is not in credential-vending mode.

**Resolution — pick one**:
- **Vended (recommended)**: switch the BigLake catalog to vended mode (`gcloud biglake iceberg catalogs update <BUCKET> --credential-mode=vended-credentials`), grant the BigLake service account `roles/storage.objectUser` on the bucket, recreate the integration with `ACCESS_DELEGATION_MODE = VENDED_CREDENTIALS` (re-grant the new subject!), then `CREATE DATABASE … LINKED_CATALOG = (CATALOG='<int>')` with no external volume.
- **External volume**: create a Snowflake GCS external volume over the same `gs://` bucket and add `EXTERNAL_VOLUME = '<vol>'` to the `CREATE DATABASE … LINKED_CATALOG` statement.

---

### 12. After CREATE OR REPLACE, Verification Suddenly Fails

**Cause**: `CREATE OR REPLACE CATALOG INTEGRATION` generates a **new** `WORKLOAD_IDENTITY_FEDERATION_SUBJECT`. The IAM grants still point at the old subject.

**Resolution**: Re-run `DESC CATALOG INTEGRATION <name>`, take the new `WORKLOAD_IDENTITY_FEDERATION_SUBJECT`, and re-apply all federated-subject grants (`serviceusage.serviceUsageConsumer`, `biglake.viewer`, and `storage.objectViewer` if external-volume mode). Wait ~75s for propagation.

---

### 13. "Query needs to be retried to setup external volume" loop (Pattern B / `bq://`)

**Error Pattern**:
```
Query needs to be retried to setup external volume for Iceberg table
```
(persists for several minutes on the first `CREATE ICEBERG TABLE` over a `bq://` federated BigLake managed table), or later:
```
Resource on the REST endpoint ... storage.objects.get denied on .../metadata/vN.metadata.json
```

**Cause**: reading a BigQuery-managed table via `bq://` federation needs storage access for **two** distinct Snowflake principals, and each has a non-obvious requirement:
1. The **external-volume service account** (`STORAGE_GCP_SERVICE_ACCOUNT` from `DESC EXTERNAL VOLUME`) must be able to **activate** the volume, which needs `storage.buckets.get` — this is **not** included in `roles/storage.objectViewer` or `roles/storage.objectUser`. Missing it causes the perpetual "retry to setup external volume" loop.
2. The **federated subject** reads `metadata.json` through the REST endpoint under its own identity (not vended) — missing `storage.objectViewer` gives the `storage.objects.get denied on .../metadata.json` error.

**Resolution**:
```bash
# external-volume SA: add bucket-get + object-read
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --member='serviceAccount:<EXTVOL_SA>' --role='roles/storage.legacyBucketReader' --condition=None
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --member='serviceAccount:<EXTVOL_SA>' --role='roles/storage.objectViewer' --condition=None

# federated subject: add object-read on the DATA BUCKET (not project-wide), in
# addition to project-level biglake.viewer / bigquery.dataViewer / serviceUsageConsumer
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --member='principal://iam.googleapis.com/projects/<NUM>/locations/global/workloadIdentityPools/<POOL>/subject/<SUBJECT>' \
  --role='roles/storage.objectViewer' --condition=None
```
Then wait ~75s and retry. Full Pattern B setup: [bigquery-federation.md](bigquery-federation.md).

---

## Diagnostic Commands

**Check integration status**:
```sql
SHOW CATALOG INTEGRATIONS LIKE '<integration_name>';
DESC CATALOG INTEGRATION <integration_name>;   -- includes WORKLOAD_IDENTITY_FEDERATION_SUBJECT
```

**Test connection**:
```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<integration_name>');
```

**Browse the catalog**:
```sql
SELECT SYSTEM$LIST_NAMESPACES_FROM_CATALOG('<integration_name>');
SELECT SYSTEM$LIST_ICEBERG_TABLES_FROM_CATALOG('<integration_name>', '<namespace>');
```

**Get the Snowflake issuer URL** (for the OIDC provider):
```sql
SELECT SYSTEM$GET_WORKLOAD_IDENTITY_ISSUER_URL();
```

**GCP-side checks**:
```bash
# OIDC provider issuer
gcloud iam workload-identity-pools providers describe <PROVIDER_ID> \
  --location=global --workload-identity-pool=<POOL_ID> --project=<GCP_PROJECT_ID>

# IAM bindings referencing the pool
gcloud projects get-iam-policy <GCP_PROJECT_ID> \
  --flatten='bindings[].members' \
  --filter='bindings.members:workloadIdentityPools' \
  --format='table(bindings.role, bindings.members)'
```

## General Troubleshooting Tips

1. **Start with the issuer + audience** — issuer/audience mismatch is the #1 cause of verify failures.
2. **Use the project NUMBER** (not the ID) in `OAUTH_AUDIENCE` and the federated principal.
3. **Grant IAM to the exact subject** — read = `biglake.viewer` + `storage.objectViewer`; scope to the subject, not the whole pool, for least privilege.
4. **Keep the `x-goog-user-project` header** — BigLake requires a billing/user project.
5. **Enable `biglake.googleapis.com`** in the billing project.
6. **Recreate for config changes** — there's no secret to rotate; `REST_CONFIG`/`REST_AUTHENTICATION` changes need `CREATE OR REPLACE`.
7. **Wait for IAM propagation** before assuming a permission grant failed.
8. **Tables need V2/V3** and Parquet data files.

## Documentation

- [Configure a catalog integration for Google Cloud BigLake Metastore](https://docs.snowflake.com/en/user-guide/tables-iceberg-configure-catalog-integration-rest-biglake)
- [Set up the Lakehouse (BigLake) Iceberg REST catalog](https://docs.cloud.google.com/lakehouse/docs/lakehouse-iceberg-rest-catalog)
- [Configure Workload Identity Federation with other providers](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-other-providers)
- [Troubleshoot Workload Identity Federation](https://docs.cloud.google.com/iam/docs/troubleshooting-workload-identity-federation)
