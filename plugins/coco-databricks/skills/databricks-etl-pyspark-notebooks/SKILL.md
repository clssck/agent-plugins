---
name: databricks-etl-pyspark-notebooks
description: "Build, deploy, and orchestrate ETL pipelines on Databricks using PySpark notebooks (.ipynb). Use when: creating ETL pipelines, building medallion architecture (silver/gold), writing PySpark transformations in notebooks, scheduling notebook-based data pipelines, deploying ETL jobs with Declarative Automation Bundles, configuring serverless or classic compute for ETL workloads, writing to Delta or Iceberg tables. Assumes source data already exists as tables in Unity Catalog. Triggers: ETL, ELT, extract transform load, PySpark, spark notebook, medallion, silver gold, data pipeline, transform, aggregate, data engineering, Delta Lake, Iceberg, data lakehouse, notebook job, ETL job, Delta merge, SCD."
---

# Databricks ETL with PySpark Notebooks

Workflow skill for building ETL pipelines on Databricks using PySpark notebooks (`.ipynb`), following the medallion lakehouse architecture, and deploying them as scheduled jobs via Declarative Automation Bundles.

**Scope:** This skill assumes source data already exists on the platform as tables in Unity Catalog. It focuses on transformation and aggregation (silver and gold layers). For data ingestion, see future ingestion-focused skills.

## Prerequisites

- Databricks CLI installed and authenticated (see `databricks-cli-install` skill)
- Unity Catalog enabled with source data already available as tables
- Familiarity with the `databricks-automation-bundles` skill (for deployment)
- Familiarity with the `databricks-unity-catalog` skill (for data discovery)

## Concepts

### Medallion Architecture

The medallion architecture organizes data into quality layers:

```
Source Tables (existing)  →  Silver (Validated)  →  Gold (Business-Ready)
```

| Layer | Purpose | Typical Operations |
|-------|---------|-------------------|
| **Source** | Raw data already on the platform | Read via `spark.read.table("catalog.schema.table")` |
| **Silver** | Cleaned, validated, deduplicated, conformed | Schema enforcement, null handling, deduplication, type casting, joins |
| **Gold** | Business-level aggregates and dimensional models | Aggregations, KPIs, dimensional modeling, materialized views |

### PySpark Notebooks as ETL Tasks

Databricks `.ipynb` notebooks are the primary authoring surface for PySpark ETL. Each notebook typically represents one transformation stage. Notebooks are orchestrated as tasks within a Databricks job, with dependencies defining the execution DAG.

**Notebook conventions:**
- Use `.ipynb` format (Jupyter notebook) — supported natively by Databricks
- Each logical step (read, transform, write) lives in its own cell
- **Parameters MUST use `dbutils.widgets`** — not `spark.conf.get()`. Serverless compute (Spark Connect) blocks `spark.conf.get()` for custom (non-`spark.*`) config keys with `CONFIG_NOT_AVAILABLE` error. `dbutils.widgets` works on both serverless and classic compute.
- The `spark` session is pre-configured and available globally in Databricks notebooks

### Target Table Formats

| Format | Write Method | When to Use |
|--------|-------------|-------------|
| **Delta** (default) | `.saveAsTable(table_name)` | Default for Databricks. Best for ACID, time travel, merge/upsert, streaming. |
| **Iceberg** | `.saveAsTable(table_name)` with table properties, or `CREATE TABLE ... USING iceberg` | Cross-platform interoperability (Snowflake, Spark OSS, Trino, etc.). Requires UniForm or native Iceberg. |

To write as Iceberg with UniForm (Delta table that also exposes Iceberg metadata):
```python
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {table_name} USING delta
    TBLPROPERTIES (
        'delta.universalFormat.enabledFormats' = 'iceberg',
        'delta.enableIcebergCompatV2' = 'true'
    )
""")
df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)
```

To write as native Iceberg:
```python
df.writeTo(table_name).using("iceberg").createOrReplace()
```

### Compute Options for ETL Jobs

| Option | Configuration | Best For |
|--------|--------------|----------|
| **Serverless** | Omit `job_clusters`; or use `environment_key` + `environments` | Fast startup, no cluster management, pay-per-use |
| **Classic job cluster** | Define `job_clusters` with `new_cluster` spec | Custom Spark config, GPUs, specific instance types, cost control |

## Workflow

### Step 1: Understand the Source Data and Targets

**⚠️ MANDATORY STOPPING POINT**: Ask the user about their data before writing any code.

Gather:
1. **Source tables**: Which existing tables are the inputs? (e.g., `catalog.schema.raw_orders`)
2. **Target table format**: Delta (default) or Iceberg?
3. **Silver target catalog and schema**: Where should silver (cleaned) tables live? (e.g., `catalog.silver_schema`)
4. **Gold target catalog and schema**: Where should gold (aggregate) tables live? (e.g., `catalog.gold_schema`) — may be the same as silver
5. **Transformation goals**: What cleaning, joining, or business logic is needed?
6. **Desired layers**: Silver only, gold only, or both?
7. **Write mode**: Full overwrite each run, or incremental merge/upsert?

Use the `databricks-unity-catalog` skill to discover and inspect source tables if needed.

### Step 2: Scaffold the Project

Create a bundle project structure for the ETL pipeline:

```
<project_name>/
├── databricks.yml
├── resources/
│   └── <project_name>_job.yml
├── src/
│   ├── 01_silver_transform.ipynb
│   └── 02_gold_aggregate.ipynb
└── tests/
    └── test_transforms.py
```

Initialize:

```bash
mkdir -p <project_name>/{resources,src,tests}
```

### Step 3: Write the Silver Notebook (Transformation)

The silver layer cleans, validates, deduplicates, and conforms source data.

Create `src/01_silver_transform.ipynb` with the following cells:

**Cell 1 — Configuration (using dbutils.widgets):**
```python
dbutils.widgets.text("catalog", "<CATALOG>")
dbutils.widgets.text("silver_schema", "<SILVER_SCHEMA>")

catalog = dbutils.widgets.get("catalog")
silver_schema = dbutils.widgets.get("silver_schema")

source_table = f"{catalog}.<SOURCE_SCHEMA>.<SOURCE_TABLE>"
silver_table = f"{catalog}.{silver_schema}.silver_<TABLE_NAME>"
```

**Cell 2 — Read source:**
```python
df_source = spark.read.table(source_table)
```

**Cell 3 — Data cleaning:**
```python
from pyspark.sql.functions import col, trim, lower, to_timestamp

df_cleaned = (df_source
    .filter(col("<PRIMARY_KEY>").isNotNull())
    .withColumn("<STRING_COL>", trim(lower(col("<STRING_COL>"))))
    .withColumn("<TIMESTAMP_COL>", to_timestamp(col("<TIMESTAMP_COL>")))
    .filter(col("<TIMESTAMP_COL>").isNotNull())
)
```

**Cell 4 — Deduplication:**
```python
from pyspark.sql.functions import row_number
from pyspark.sql.window import Window

window_spec = Window.partitionBy("<PRIMARY_KEY>").orderBy(col("<TIMESTAMP_COL>").desc())
df_deduped = (df_cleaned
    .withColumn("_row_num", row_number().over(window_spec))
    .filter(col("_row_num") == 1)
    .drop("_row_num")
)
```

**Cell 5 — Write (Delta — default):**
```python
df_deduped.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(silver_table)
print(f"Wrote {spark.read.table(silver_table).count()} rows to {silver_table}")
```

**Cell 5 — Write (Iceberg with UniForm):**
```python
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {silver_table} USING delta
    TBLPROPERTIES (
        'delta.universalFormat.enabledFormats' = 'iceberg',
        'delta.enableIcebergCompatV2' = 'true'
    )
""")
df_deduped.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(silver_table)
print(f"Wrote {spark.read.table(silver_table).count()} rows to {silver_table}")
```

**Common silver-layer operations:**

| Operation | PySpark Pattern |
|-----------|----------------|
| Drop nulls | `.filter(col("key").isNotNull())` or `.dropna(subset=["key"])` |
| Type casting | `.withColumn("amount", col("amount").cast("double"))` |
| String cleaning | `.withColumn("name", trim(lower(col("name"))))` |
| Deduplication | `row_number()` over a window partitioned by key, ordered by timestamp |
| Schema enforcement | Read with a defined schema: `spark.read.schema(my_schema).table(...)` |
| Joins | `df_a.join(df_b, on="key", how="left")` |
| Quarantine bad records | Write failed-validation rows to a separate quarantine table |
| Column selection | `.select("col_a", "col_b", col("nested.field").alias("field"))` |
| Derived columns | `.withColumn("full_name", concat_ws(" ", col("first"), col("last")))` |

### Step 4: Write the Gold Notebook (Aggregation)

The gold layer produces business-ready aggregates and dimensional models.

Create `src/02_gold_aggregate.ipynb` with the following cells:

**Cell 1 — Configuration (using dbutils.widgets):**
```python
dbutils.widgets.text("catalog", "<CATALOG>")
dbutils.widgets.text("silver_schema", "<SILVER_SCHEMA>")
dbutils.widgets.text("gold_schema", "<GOLD_SCHEMA>")

catalog = dbutils.widgets.get("catalog")
silver_schema = dbutils.widgets.get("silver_schema")
gold_schema = dbutils.widgets.get("gold_schema")

silver_table = f"{catalog}.{silver_schema}.silver_<TABLE_NAME>"
gold_table = f"{catalog}.{gold_schema}.gold_<SUMMARY_NAME>"
```

**Cell 2 — Read silver:**
```python
df_silver = spark.read.table(silver_table)
```

**Cell 3 — Aggregate:**
```python
from pyspark.sql.functions import col, count, sum as _sum, avg, date_trunc

df_gold = (df_silver
    .withColumn("event_date", date_trunc("day", col("<TIMESTAMP_COL>")))
    .groupBy("event_date", "<DIMENSION_COL>")
    .agg(
        count("*").alias("record_count"),
        _sum("<MEASURE_COL>").alias("total_<MEASURE>"),
        avg("<MEASURE_COL>").alias("avg_<MEASURE>"),
    )
    .orderBy("event_date", "<DIMENSION_COL>")
)
```

**Cell 4 — Write (Delta — default):**
```python
df_gold.write.mode("overwrite").saveAsTable(gold_table)
print(f"Wrote {spark.read.table(gold_table).count()} rows to {gold_table}")
```

**Cell 4 — Write (Iceberg with UniForm):**
```python
spark.sql(f"""
    CREATE TABLE IF NOT EXISTS {gold_table} USING delta
    TBLPROPERTIES (
        'delta.universalFormat.enabledFormats' = 'iceberg',
        'delta.enableIcebergCompatV2' = 'true'
    )
""")
df_gold.write.mode("overwrite").saveAsTable(gold_table)
print(f"Wrote {spark.read.table(gold_table).count()} rows to {gold_table}")
```

### Step 5: Configure the Bundle for Deployment

**⚠️ MANDATORY STOPPING POINT**: Ask the user which compute type they want.

Present options:
1. **Serverless compute** — No cluster config, fast startup, pay-per-use. Recommended for most ETL workloads.
2. **Classic job cluster** — Dedicated cluster with custom Spark config, instance types, init scripts. Use for GPU workloads, large shuffles, or specific runtime requirements.

#### Option 1: Serverless Compute (Recommended)

`databricks.yml`:
```yaml
bundle:
  name: <project_name>

include:
  - resources/*.yml

workspace:
  host: <WORKSPACE_URL>

variables:
  catalog:
    description: Target Unity Catalog catalog
    default: <CATALOG>
  silver_schema:
    description: Target schema for silver (cleaned) tables
    default: <SILVER_SCHEMA>
  gold_schema:
    description: Target schema for gold (aggregate) tables
    default: <GOLD_SCHEMA>

targets:
  dev:
    mode: development
    default: true
  prod:
    mode: production
    workspace:
      host: <WORKSPACE_URL>
      root_path: /Shared/.bundle/prod/${bundle.name}
    run_as:
      service_principal_name: <SP_NAME>
```

`resources/<project_name>_job.yml` (serverless):
```yaml
resources:
  jobs:
    etl_pipeline:
      name: ${bundle.name}_etl_pipeline

      tasks:
        - task_key: silver_transform
          notebook_task:
            notebook_path: ../src/01_silver_transform.ipynb
            base_parameters:
              catalog: ${var.catalog}
              silver_schema: ${var.silver_schema}

        - task_key: gold_aggregate
          depends_on:
            - task_key: silver_transform
          notebook_task:
            notebook_path: ../src/02_gold_aggregate.ipynb
            base_parameters:
              catalog: ${var.catalog}
              silver_schema: ${var.silver_schema}
              gold_schema: ${var.gold_schema}

      schedule:
        quartz_cron_expression: '0 0 6 * * ?'   # daily at 6am UTC
        timezone_id: UTC
        pause_status: UNPAUSED
```

With serverless, simply omit `job_clusters` and any `job_cluster_key` / `new_cluster` on tasks. Databricks automatically uses serverless compute.

**IMPORTANT:** The `base_parameters` keys must match the widget names defined with `dbutils.widgets.text()` in the notebooks. Do NOT use dotted keys (e.g., `pipeline.catalog`) — use simple names (e.g., `catalog`).

#### Option 2: Classic Job Cluster

`resources/<project_name>_job.yml` (classic):
```yaml
resources:
  jobs:
    etl_pipeline:
      name: ${bundle.name}_etl_pipeline

      job_clusters:
        - job_cluster_key: etl_cluster
          new_cluster:
            spark_version: 15.4.x-scala2.12
            node_type_id: m5d.xlarge        # AWS; adjust for Azure/GCP
            num_workers: 2
            spark_conf:
              spark.sql.shuffle.partitions: "200"
            autoscale:
              min_workers: 1
              max_workers: 4

      tasks:
        - task_key: silver_transform
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/01_silver_transform.ipynb
            base_parameters:
              catalog: ${var.catalog}
              silver_schema: ${var.silver_schema}

        - task_key: gold_aggregate
          depends_on:
            - task_key: silver_transform
          job_cluster_key: etl_cluster
          notebook_task:
            notebook_path: ../src/02_gold_aggregate.ipynb
            base_parameters:
              catalog: ${var.catalog}
              silver_schema: ${var.silver_schema}
              gold_schema: ${var.gold_schema}

      schedule:
        quartz_cron_expression: '0 0 6 * * ?'
        timezone_id: UTC
        pause_status: UNPAUSED
```

#### Serverless with Python Dependencies

If notebooks need extra Python packages (not pre-installed on serverless), install them in a notebook cell:

```python
%pip install great-expectations requests
```

Alternatively, for `.py` script tasks (not notebooks), use the `environments` spec in the job YAML:

```yaml
environments:
  - environment_key: etl_env
    spec:
      environment_version: "2"
      dependencies:
        - great-expectations
        - requests
```

**Note:** For `notebook_task`, `%pip install` in a cell is the standard approach. The `environment_key` + `environments` spec is used with `spark_python_task` (standalone `.py` files) on serverless.

### Step 6: Validate, Deploy, and Run

```bash
databricks bundle validate

databricks bundle deploy -t dev

databricks bundle run -t dev etl_pipeline

databricks bundle open etl_pipeline
```

For production:
```bash
databricks bundle deploy -t prod
databricks bundle run -t prod etl_pipeline
```

### Step 7: Add Data Quality Checks (Optional)

Add an assertion cell at the end of each notebook to validate results:

**Cell (in silver notebook) — Quality gate:**
```python
row_count = spark.read.table(silver_table).count()
null_count = spark.read.table(silver_table).filter(col("<PRIMARY_KEY>").isNull()).count()

assert row_count > 0, "Silver table is empty after transformation"
assert null_count == 0, f"Found {null_count} null key rows in silver table"

print(f"Quality checks passed. {row_count} rows in {silver_table}.")
```

For production-grade quality, consider using `expectations` with Lakeflow Declarative Pipelines or a library like Great Expectations.

## Patterns and Recipes

### Parameterized Notebooks via dbutils.widgets

Pass parameters through `base_parameters` in the job YAML and read them in notebook cells using `dbutils.widgets`:

**Cell:**
```python
dbutils.widgets.text("catalog", "default_catalog")
dbutils.widgets.text("silver_schema", "default_schema")
dbutils.widgets.text("run_date", "")

catalog = dbutils.widgets.get("catalog")
silver_schema = dbutils.widgets.get("silver_schema")
run_date = dbutils.widgets.get("run_date")
```

**⚠️ Do NOT use `spark.conf.get()` for custom config keys.** Serverless compute (Spark Connect) blocks reads of non-`spark.*` config keys with `CONFIG_NOT_AVAILABLE` error. Always use `dbutils.widgets` for notebook parameterization — it works on both serverless and classic compute.

This lets you reuse the same notebook across targets (dev, staging, prod) by overriding variables in each target.

### Multi-Source Joins

For pipelines that transform from multiple source tables, create parallel read tasks or join within a single notebook:

**Option A — Single notebook with multiple reads:**

**Cell 1:**
```python
df_orders = spark.read.table(f"{catalog}.{schema}.raw_orders")
df_customers = spark.read.table(f"{catalog}.{schema}.raw_customers")
```

**Cell 2:**
```python
df_joined = (df_orders
    .join(df_customers, on="customer_id", how="left")
    .select(
        df_orders["order_id"],
        df_orders["order_date"],
        df_orders["amount"],
        df_customers["customer_name"],
        df_customers["region"],
    )
)
```

**Option B — Parallel notebook tasks in the job DAG:**

```yaml
tasks:
  - task_key: silver_orders
    notebook_task:
      notebook_path: ../src/silver_orders.ipynb
  - task_key: silver_customers
    notebook_task:
      notebook_path: ../src/silver_customers.ipynb
  - task_key: gold_order_summary
    depends_on:
      - task_key: silver_orders
      - task_key: silver_customers
    notebook_task:
      notebook_path: ../src/gold_order_summary.ipynb
```

Both silver tasks run in parallel; the gold task waits for both to complete.

### Incremental Merge (SCD Type 1)

For tables that need upserts instead of full overwrite:

**Cell:**
```python
from delta.tables import DeltaTable

target_delta = DeltaTable.forName(spark, silver_table)

target_delta.alias("target").merge(
    df_new.alias("source"),
    "target.<PRIMARY_KEY> = source.<PRIMARY_KEY>"
).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
```

### SCD Type 2 (Slowly Changing Dimensions)

**Cell:**
```python
from pyspark.sql.functions import lit, current_timestamp
from delta.tables import DeltaTable

df_updates = (df_new
    .withColumn("_valid_from", current_timestamp())
    .withColumn("_valid_to", lit(None).cast("timestamp"))
    .withColumn("_is_current", lit(True))
)

target_delta = DeltaTable.forName(spark, silver_table)

target_delta.alias("target").merge(
    df_updates.alias("source"),
    "target.entity_id = source.entity_id AND target._is_current = true"
).whenMatchedUpdate(set={
    "_valid_to": "source._valid_from",
    "_is_current": "false",
}).whenNotMatchedInsertAll().execute()
```

### Incremental Read with Delta Change Data Feed

Read only new/changed rows from a source Delta table since the last run:

**Cell:**
```python
changes_df = (spark.read
    .format("delta")
    .option("readChangeFeed", "true")
    .option("startingVersion", last_processed_version)
    .table(source_table)
    .filter(col("_change_type").isin("insert", "update_postimage"))
)
```

Requires Change Data Feed enabled on the source table:
```sql
ALTER TABLE catalog.schema.table SET TBLPROPERTIES (delta.enableChangeDataFeed = true)
```

### Retry and Alerting

```yaml
tasks:
  - task_key: silver_transform
    notebook_task:
      notebook_path: ../src/01_silver_transform.ipynb
    retry_on_timeout: true
    max_retries: 2
    min_retry_interval_millis: 60000

email_notifications:
  on_failure:
    - team@example.com
  on_success:
    - team@example.com
```

## Stopping Points

- After Step 1: if source table details, target format, or target schemas are unclear (ask user)
- After Step 4: before deployment, confirm compute preference (serverless vs classic)
- After Step 6: if deployment or run fails (diagnose before retrying)

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `AnalysisException: Table not found` | Verify catalog/schema exist and user has `USE_CATALOG` + `USE_SCHEMA` privileges |
| `CONFIG_NOT_AVAILABLE` on `spark.conf.get()` | **Do not use `spark.conf.get()` for custom keys on serverless.** Switch to `dbutils.widgets.text()` / `dbutils.widgets.get()`. This is a Spark Connect limitation — only `spark.*` config keys are readable. |
| Serverless task fails with missing package | Add `%pip install <pkg>` cell at the top of the notebook |
| Merge conflicts on concurrent writes | Enable write conflict resolution: `spark.conf.set("spark.databricks.delta.merge.enableLowShuffle", "true")` |
| Job cluster startup too slow | Switch to serverless compute or use an instance pool |
| Permission denied writing to table | Grant `MODIFY` on the target schema: `GRANT MODIFY ON SCHEMA catalog.schema TO role` |
| Notebook fails with `NameError: spark` | Ensure notebook is running on a Databricks cluster (not local). `spark` is pre-configured. |
| `.ipynb` not recognized by bundle | Ensure Databricks CLI v0.218.0+. The `notebook_task.notebook_path` supports `.ipynb` natively. |
| Schema mismatch on overwrite | Add `.option("overwriteSchema", "true")` to the write, or use `mergeSchema` |
| Iceberg table not readable from external engines | Ensure UniForm is enabled: `delta.universalFormat.enabledFormats = 'iceberg'` and `delta.enableIcebergCompatV2 = 'true'` |

## References

- [Tutorial: Build an ETL pipeline with Apache Spark](https://docs.databricks.com/aws/en/getting-started/etl-quick-start)
- [Medallion lakehouse architecture](https://docs.databricks.com/aws/en/lakehouse/medallion)
- [Run jobs with serverless compute](https://docs.databricks.com/aws/en/jobs/run-serverless-jobs)
- [Bundle configuration examples](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/bundles/examples)
- [Databricks bundle-examples: serverless_job](https://github.com/databricks/bundle-examples/tree/main/knowledge_base/serverless_job)
- [Delta Lake merge](https://docs.databricks.com/aws/en/delta/merge)
- [Delta UniForm (Iceberg interop)](https://docs.databricks.com/aws/en/delta/uniform)

## Output

This skill produces:
- PySpark `.ipynb` notebook files for each ETL layer (silver transform, gold aggregate)
- Tables in Delta or Iceberg format as requested
- A Declarative Automation Bundle project with `databricks.yml` and job resource definitions
- A deployed and scheduled Databricks job orchestrating the full ETL pipeline
- Validated, deployed, and running ETL workflows on serverless or classic compute
