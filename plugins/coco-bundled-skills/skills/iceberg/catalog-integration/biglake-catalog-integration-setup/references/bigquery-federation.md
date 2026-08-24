# Pattern B: BigQuery-Federation Flavour (`bq://`)

Snowflake **reads** BigQuery-owned Iceberg tables. This is the reverse of the default (Pattern A, `gs://`) flow. Load this reference when the user wants BigQuery to be the **writer** and Snowflake to be a reader.

## The two warehouse flavours

The BigLake Iceberg REST endpoint (`https://biglake.googleapis.com/iceberg/v1/restcatalog`) is the same in both patterns, but the catalog's **warehouse** determines who owns the tables:

| | Pattern A (`gs://<bucket>`) | Pattern B (`bq://projects/<project>`) |
|---|---|---|
| Table owner | The BigLake catalog (files in GCS) | BigQuery (Apache Iceberg *managed* tables) |
| Primary writer | Snowflake (catalog-linked DB) or Spark | BigQuery (DML / streaming / CDC) |
| Snowflake role | Reader **and** writer | Reader only |
| Credential vending | Supported (`VENDED_CREDENTIALS`) | **Not supported** -> external volume required |
| `ACCESS_DELEGATION_MODE` | `VENDED_CREDENTIALS` (recommended) | `EXTERNAL_VOLUME_CREDENTIALS` (mandatory) |
| Reader freshness | Live | Refresh after writer publishes metadata |

Do not confuse this with the delegation-mode choice in `create/SKILL.md` (vended vs external-volume): that axis is about *how* Snowflake reaches storage. The warehouse flavour (`gs://` vs `bq://`) is about *who owns the table*. On `bq://` the two collapse: vending is unavailable, so an external volume is always required.

## GCP side: create a BigQuery-managed Iceberg table

BigQuery-managed Iceberg tables need a BigQuery **cloud-resource connection** whose service account can write the bucket.

```bash
# 1. Connection
bq mk --connection --location=<GCP_REGION> --connection_type=CLOUD_RESOURCE <CONN_ID>
bq show --connection --location=<GCP_REGION> --format=json <GCP_PROJECT_ID>.<GCP_REGION>.<CONN_ID>
#   -> copy the serviceAccountId

# 2. Let the connection SA write the bucket
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --member='serviceAccount:<CONN_SA>' --role='roles/storage.objectUser'
```

In BigQuery (SQL):
```sql
CREATE SCHEMA IF NOT EXISTS <BQ_DATASET> OPTIONS (location = '<GCP_REGION>');

CREATE OR REPLACE TABLE `<BQ_DATASET>.<TABLE>` ( id INT64, name STRING )
WITH CONNECTION `<GCP_REGION>.<CONN_ID>`
OPTIONS (
  file_format = 'PARQUET',
  table_format = 'ICEBERG',
  storage_uri = 'gs://<BUCKET>/<path>/<TABLE>'
);

INSERT INTO `<BQ_DATASET>.<TABLE>` VALUES (10, 'BQ-Alice'), (20, 'BQ-Bob');

-- Publish the latest Iceberg metadata for external readers (required after writes)
EXPORT TABLE METADATA FROM `<BQ_DATASET>.<TABLE>`;
```

> Creating the connection/table needs `roles/bigquery.connectionAdmin` (or `connectionUser` with a delegate) plus dataset write on the user.

## Snowflake side: catalog integration (federation)

Same workload-identity-federation auth as Pattern A, but `CATALOG_NAME` points at `bq://` and vending is off.

```sql
CREATE OR REPLACE CATALOG INTEGRATION <INTEGRATION_NAME>
  CATALOG_SOURCE = ICEBERG_REST
  TABLE_FORMAT = ICEBERG
  REST_CONFIG = (
    CATALOG_URI = 'https://biglake.googleapis.com/iceberg/v1/restcatalog'
    CATALOG_NAME = 'bq://projects/<GCP_PROJECT_ID>'      -- optionally /locations/<GCP_REGION>
    ACCESS_DELEGATION_MODE = EXTERNAL_VOLUME_CREDENTIALS  -- vending NOT supported on bq://
    ADDITIONAL_HEADERS = ( "x-goog-user-project" = '<GCP_PROJECT_ID>' )
  )
  REST_AUTHENTICATION = (
    TYPE = OAUTH
    OAUTH_GRANT_TYPE = TOKEN_EXCHANGE
    OAUTH_TOKEN_URI = 'https://sts.googleapis.com/v1/token'
    OAUTH_AUDIENCE = '<OAUTH_AUDIENCE>'
    OAUTH_ALLOWED_SCOPES = ('https://www.googleapis.com/auth/bigquery')
  )
  ENABLED = TRUE;
```

### Create the external volume (read-only)

```sql
CREATE OR REPLACE EXTERNAL VOLUME <VOL>
  STORAGE_LOCATIONS = (
    ( NAME = 'gcs' STORAGE_PROVIDER = 'GCS' STORAGE_BASE_URL = 'gcs://<BUCKET>/' )
  )
  ALLOW_WRITES = FALSE;

DESC EXTERNAL VOLUME <VOL>;   -- copy STORAGE_GCP_SERVICE_ACCOUNT
```

### Grant IAM to BOTH Snowflake principals

Reading a BigQuery-managed table needs storage access for **two** identities:

1. **External-volume SA** (`STORAGE_GCP_SERVICE_ACCOUNT`) reads the data files and must activate the volume:
   - `roles/storage.legacyBucketReader` (provides `storage.buckets.get`, which `objectViewer`/`objectUser` do **not** include -> without it, table creation loops on "Query needs to be retried to setup external volume")
   - `roles/storage.objectViewer`
2. **Federated subject** (`DESC CATALOG INTEGRATION` -> `WORKLOAD_IDENTITY_FEDERATION_SUBJECT`) reads `metadata.json` through the REST endpoint under its own identity:
   - `roles/storage.objectViewer` (without it: "storage.objects.get denied on .../metadata/vN.metadata.json")
   - `roles/biglake.viewer`, `roles/bigquery.dataViewer`, `roles/serviceusage.serviceUsageConsumer`

```bash
# 1) external-volume SA
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --member='serviceAccount:<EXTVOL_SA>' --role='roles/storage.legacyBucketReader' --condition=None
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --member='serviceAccount:<EXTVOL_SA>' --role='roles/storage.objectViewer' --condition=None

# 2) federated subject (re-DESC and re-grant after any CREATE OR REPLACE)
SUBJECT_MEMBER='principal://iam.googleapis.com/projects/<GCP_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/<SUBJECT>'
# project-level roles (no bucket-scoped equivalent)
for ROLE in serviceusage.serviceUsageConsumer biglake.viewer bigquery.dataViewer; do
  gcloud projects add-iam-policy-binding <GCP_PROJECT_ID> \
    --member="$SUBJECT_MEMBER" --role="roles/$ROLE" --condition=None
done
# storage read: scope to the data bucket, NOT the whole project (least privilege)
gcloud storage buckets add-iam-policy-binding gs://<BUCKET> \
  --member="$SUBJECT_MEMBER" --role='roles/storage.objectViewer' --condition=None
```

### Verify and read

```sql
SELECT SYSTEM$VERIFY_CATALOG_INTEGRATION('<INTEGRATION_NAME>');
SELECT SYSTEM$VERIFY_EXTERNAL_VOLUME('<VOL>');

CREATE OR REPLACE ICEBERG TABLE <DB>.<SCHEMA>.<TABLE>
  CATALOG = '<INTEGRATION_NAME>'
  EXTERNAL_VOLUME = '<VOL>'
  CATALOG_NAMESPACE = '<BQ_DATASET>'
  CATALOG_TABLE_NAME = '<TABLE>';

SELECT * FROM <DB>.<SCHEMA>.<TABLE> ORDER BY 1;   -- returns the rows BigQuery wrote
```

## Freshness

Pattern B reads are **not live**. After a BigQuery write, BigQuery must publish metadata (`EXPORT TABLE METADATA`, or scheduled/auto-publish if enabled on the project), and Snowflake must pick it up:

```sql
-- one-off
ALTER ICEBERG TABLE <DB>.<SCHEMA>.<TABLE> REFRESH;

-- or keep it current automatically (polls the catalog for new metadata)
ALTER ICEBERG TABLE <DB>.<SCHEMA>.<TABLE> SET AUTO_REFRESH = TRUE;
```

(Pattern A reads from BigQuery are live and need no refresh.)
