# Data Movement Reference

pg_lake supports COPY TO/FROM S3, foreign tables for querying S3 files directly, and various file formats.

**⚠️ Safety: COPY TO with OVERWRITE and DROP FOREIGN TABLE are destructive. Never execute these without the user explicitly requesting it.** Read operations (COPY FROM, SELECT, CREATE FOREIGN TABLE, LIST) are safe.

## COPY TO S3 (Export)

```sql
-- Parquet (default snappy compression)
COPY events TO 's3://bucket/events.parquet';

-- CSV
COPY events TO 's3://bucket/events.csv';

-- CSV with gzip compression
COPY events TO 's3://bucket/events.csv.gz';

-- JSON with zstd compression
COPY events TO 's3://bucket/events.json.zst';

-- Query result to S3
COPY (SELECT * FROM events WHERE region = 'US')
  TO 's3://bucket/us_events.parquet';
```

## COPY FROM S3 (Import)

```sql
-- Parquet (auto-detected from extension)
COPY events FROM 's3://bucket/data.parquet';

-- CSV with options
COPY events FROM 's3://bucket/data.csv' WITH (FORMAT csv, HEADER true, DELIMITER ',');

-- JSON with compression
COPY events FROM 's3://bucket/data.json.gz' WITH (FORMAT json);

-- Create table + load in one step (auto-detect schema)
CREATE TABLE imported () WITH (load_from = 's3://bucket/data.parquet');

-- Create table with schema from file, load separately
CREATE TABLE imported () WITH (definition_from = 's3://bucket/data.parquet');
COPY imported FROM 's3://bucket/data.parquet';
```

## Supported Formats and Compression

| Format | gzip | zstd | snappy |
|--------|------|------|--------|
| CSV | yes | yes | |
| JSON | yes | yes | |
| Parquet | yes | yes | yes |

Format is auto-detected from file extension. If extension is ambiguous, specify explicitly:

```sql
COPY events FROM 's3://bucket/data_file' WITH (FORMAT parquet);
CREATE FOREIGN TABLE ft () SERVER pg_lake
  OPTIONS (path 's3://bucket/data_file', format 'parquet', compression 'gzip');
```

## Foreign Tables (Query S3 Directly)

Foreign tables let you query S3 files without loading them into Postgres.

```sql
-- Create foreign table pointing to S3
CREATE FOREIGN TABLE s3_logs ()
  SERVER pg_lake
  OPTIONS (path 's3://bucket/logs/');

-- Query it like a regular table
SELECT * FROM s3_logs WHERE event_date > '2024-01-01' LIMIT 100;

-- Specify format explicitly
CREATE FOREIGN TABLE csv_data ()
  SERVER pg_lake
  OPTIONS (path 's3://bucket/data.csv', format 'csv');

-- Public URL (no credentials needed)
CREATE FOREIGN TABLE public_data ()
  SERVER pg_lake
  OPTIONS (path 'https://example.com/data.parquet');
```

### Wildcards and Multiple Files

```sql
-- All parquet files in a directory
CREATE FOREIGN TABLE all_logs ()
  SERVER pg_lake
  OPTIONS (path 's3://bucket/logs/*.parquet');

-- Include filename as a column
CREATE FOREIGN TABLE ft_with_filename ()
  SERVER pg_lake
  OPTIONS (path 's3://bucket/logs/', filename 'true');
```

## lake_file.list() — Browse S3

```sql
-- List files at a path
SELECT * FROM lake_file.list('s3://bucket/logs/');

-- Useful for verifying S3 access and exploring bucket contents
SELECT file_name, file_size
FROM lake_file.list('s3://bucket/data/')
ORDER BY file_size DESC
LIMIT 20;
```

## psql \copy (Local Files)

```sql
-- Import compressed JSON from local disk
\copy data FROM '/tmp/data.json.gz' WITH (FORMAT 'json', compression 'gzip');

-- Export Parquet to local disk
\copy data TO '/tmp/data.parquet' WITH (FORMAT 'parquet');
```

Always specify format and compression with `\copy` — the server cannot detect from local file extensions.

## CSV to Parquet Conversion

Convert CSV/JSON to Parquet for better query performance:

```sql
-- Load CSV into a regular table
CREATE TABLE staging () WITH (load_from = 's3://bucket/data.csv');

-- Export as Parquet
COPY staging TO 's3://bucket/data.parquet';

-- Create foreign table for fast queries
CREATE FOREIGN TABLE data_fast ()
  SERVER pg_lake
  OPTIONS (path 's3://bucket/data.parquet');
```

## PG → Snowflake Data Flow

Two disjoint paths. Pick based on where pg_lake stores data:

| PG storage mode | Recommended path | What it gives you |
|-----------------|------------------|-------------------|
| **Managed storage** (no `STORAGE_INTEGRATION` attached) | **Catalog Integration** (preferred) | Native Snowflake Iceberg tables that read PG's Iceberg metadata directly — no Parquet copy, no staging |
| **Customer S3** (with `STORAGE_INTEGRATION`) | **External stage** (alternative below) | Parquet files staged in your bucket, loaded via `COPY INTO` on the SF side |

`pg_lake_storage.py verify --instance <name>` surfaces the `storage_integration` field — use it to detect which path the instance is on.

> **Keeping the PG-side Iceberg table in sync with an operational source:** either path assumes PG already has an Iceberg table to expose. For continuous operational-table → Iceberg sync with exactly-once semantics (time-windowed, sequence-bounded, or file-list pipelines), see `incremental-sync.md`. The catalog integration / external-stage paths below then expose the synced Iceberg table to Snowflake.

### Preferred: PG → Snowflake via Catalog Integration (managed storage)

Uses `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` on Snowflake to query PG's Iceberg tables in-place. Cloud-platform support varies — `pg_lake_storage.py verify` detects unsupported configurations and the skill falls back to the external-stage flow when needed. For the current support matrix, see Snowflake docs (`cortex search docs "snowflake_postgres catalog integration"`). Full workflow + error translation + cost model in `references/snowflake-catalog-integration.md`. Summary:

```bash
# Pre-flight (read-only)
pg_lake_catalog.py check-account-params --snowflake-connection <conn> --json
pg_lake_catalog.py list-pg-iceberg --connection-name <pg-conn> --json

# Per-table exposure (good for 1 specific table)
pg_lake_catalog.py create-integration --name my_ci \
  --postgres-instance <inst> --database <pg-db> \
  --snowflake-connection <conn> --json
pg_lake_catalog.py create-iceberg-table --name sensor_readings \
  --catalog my_ci --catalog-table-name sensor_readings \
  --catalog-namespace public --snowflake-connection <conn> --json

# OR CLD exposure (recommended for 2+ tables — all auto-surface)
pg_lake_catalog.py create-cld --name my_cld --catalog my_ci \
  --snowflake-connection <conn> --json
```

Query from Snowflake:
```sql
SELECT * FROM sensor_readings;                  -- per-table
SELECT * FROM my_cld.public.sensor_readings;    -- CLD-qualified
```

The catalog integration refreshes automatically (`REFRESH_INTERVAL_SECONDS = 30` default, integration-level, range [30, 86400]). For ≥ 10 tables consider raising to 300s via `set-refresh-interval` to reduce Snowpipe cost.

### Alternative: PG → Snowflake via External Stage (customer-S3, Release 1)

Use when the PG instance has `STORAGE_INTEGRATION` attached (customer bucket) or the catalog integration path is not available for the instance's cloud platform. pg_lake writes Parquet to your S3 bucket; Snowflake reads the files via a stage that shares the same storage integration.

#### Step 1: Write from Postgres

```sql
-- Option A: Write to Iceberg table (data lands in S3 as Parquet)
INSERT INTO events SELECT * FROM application_events;

-- Option B: COPY query results directly to S3 as Parquet
COPY (SELECT * FROM events WHERE region = 'US')
  TO 's3://bucket/exports/us_events.parquet';
```

#### Step 2: Read from Snowflake

Create a stage pointing to the same S3 bucket, using the same storage integration:

```sql
-- In Snowflake:
CREATE OR REPLACE FILE FORMAT parquet_format TYPE = PARQUET;

CREATE OR REPLACE STAGE pg_lake_stage
  URL = 's3://bucket/prefix/'
  STORAGE_INTEGRATION = <integration_name>
  FILE_FORMAT = parquet_format;

-- List files pg_lake wrote
LIST @pg_lake_stage;

-- Query the Parquet files
SELECT $1 FROM @pg_lake_stage;

-- Or load into a Snowflake table
COPY INTO my_db.my_schema.events_table
FROM @pg_lake_stage
FILE_FORMAT = parquet_format;
```

The storage integration used for the Snowflake stage is the same `POSTGRES_EXTERNAL_STORAGE` integration created during pg_lake setup.

> **Related Snowflake skills:** For managed-storage instances, prefer `snowflake-catalog-integration.md` (lives in this same directory). If the user needs to create an external volume or hits IAM/access errors on the Snowflake side, check whether `data-engineering/iceberg/external-volume/SKILL.md` is available — it has detailed IAM debugging for S3, Azure, and GCS. For auto-discovery of PG's Iceberg tables via catalog-linked databases (when available), see `data-engineering/iceberg/catalog-linked-database/SKILL.md`.

## Snowflake → PG Data Flow

Write data from Snowflake to S3 as Parquet, then read from Postgres. This direction uses **Parquet files**. If read-only Iceberg tables from Snowflake are supported (`catalog='rest'` or `catalog='object_store'` with `read_only=True`), that path avoids the Parquet export step — try it if available.

### Step 1: Write from Snowflake

```sql
-- In Snowflake: export to the shared S3 bucket via stage
COPY INTO @pg_lake_stage/from_snowflake/
FROM my_database.my_schema.my_table
FILE_FORMAT = (TYPE = PARQUET)
OVERWRITE = TRUE
SINGLE = FALSE
MAX_FILE_SIZE = 50000000;
```

### Step 2: Read from Postgres

```sql
-- Option A: Query Parquet files directly (no import)
CREATE FOREIGN TABLE sf_data ()
  SERVER pg_lake
  OPTIONS (path 's3://bucket/prefix/from_snowflake/*.parquet');

SELECT * FROM sf_data;

-- Option B: Load into a Postgres table
COPY pg_table FROM 's3://bucket/prefix/from_snowflake/*.parquet';

-- Option C: Auto-detect schema and load in one step
CREATE TABLE from_snowflake ()
  USING iceberg
  WITH (load_from = 's3://bucket/prefix/from_snowflake/');
```
