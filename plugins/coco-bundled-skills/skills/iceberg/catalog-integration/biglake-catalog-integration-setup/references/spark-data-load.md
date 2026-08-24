# Load Data into a BigLake Iceberg Table with Spark

Optional. Use this only if you need to **populate** a BigLake Iceberg table (`gs://`-flavour REST catalog) with data before querying it elsewhere. The `gcp-setup` workflow creates the table metadata (an empty table) with `gcloud` — no Spark required. You can also load data later from Snowflake via a catalog-linked database (Pattern A). Reach for Spark only when you want a Google-side bulk load and an empty table is not enough.

## When to Load

Load this reference when:
- The user explicitly wants to load data into the BigLake table from the Google side, and
- A catalog-linked database write from Snowflake is not the desired path.

## Spark session (Dataproc Serverless or any Spark with the Iceberg + GCS runtime)

```python
from pyspark.sql import SparkSession

catalog_name = "biglake"
project_id   = "<GCP_PROJECT_ID>"
warehouse    = "gs://<BUCKET>"   # or bl://projects/<GCP_PROJECT_ID>/catalogs/<CATALOG_ID>

spark = (
    SparkSession.builder.appName("biglake-iceberg-load")
    .config("spark.sql.defaultCatalog", catalog_name)
    .config(f"spark.sql.catalog.{catalog_name}", "org.apache.iceberg.spark.SparkCatalog")
    .config(f"spark.sql.catalog.{catalog_name}.type", "rest")
    .config(f"spark.sql.catalog.{catalog_name}.uri",
            "https://biglake.googleapis.com/iceberg/v1/restcatalog")
    .config(f"spark.sql.catalog.{catalog_name}.warehouse", warehouse)
    .config(f"spark.sql.catalog.{catalog_name}.header.x-goog-user-project", project_id)
    .config(f"spark.sql.catalog.{catalog_name}.rest.auth.type",
            "org.apache.iceberg.gcp.auth.GoogleAuthManager")
    .config(f"spark.sql.catalog.{catalog_name}.io-impl",
            "org.apache.iceberg.gcp.gcs.GCSFileIO")
    .config("spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
    .getOrCreate()
)

spark.sql("INSERT INTO <NAMESPACE>.<TABLE> VALUES (1, 'Ada', DATE '2024-01-02')")
spark.sql("SELECT * FROM <NAMESPACE>.<TABLE>").show()
```

## Run on Dataproc Serverless (billable)

```bash
gcloud dataproc batches submit pyspark <YOUR_SCRIPT>.py \
  --project=<GCP_PROJECT_ID> --region=<GCP_REGION> --version=2.3
```

## Data notes

- Only **Parquet** data files are supported; tables must be Iceberg **V2** (GA) or **V3** (preview).
- `io-impl = org.apache.iceberg.gcp.gcs.GCSFileIO` is required for credential vending.
- See [Query Iceberg tables with Spark and BigQuery](https://docs.cloud.google.com/lakehouse/docs/use-biglake-catalog-iceberg-rest-catalog).
