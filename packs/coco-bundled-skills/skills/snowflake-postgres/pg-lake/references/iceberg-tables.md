# Iceberg Tables Reference

pg_lake Iceberg tables are transactional, columnar tables stored in object storage (Parquet format), optimized for analytics.

**⚠️ Safety: Never execute destructive operations (DROP TABLE, DROP COLUMN, DELETE, TRUNCATE) without the user explicitly requesting it.** These operations are irreversible — DROP TABLE permanently deletes Parquet files from S3. Always confirm with the user before running any operation that destroys data.

## Storage Modes

pg_lake supports two storage modes for Iceberg tables:

| Mode | Setup required | When to use |
|------|---------------|-------------|
| **Customer-managed S3** | Storage integration + IAM | Production, shared data with Snowflake, control over bucket |
| **Managed storage** | Platform must provision internal bucket | No customer S3 needed, but may not be available on all instances |

With **customer-managed S3**, set a `default_location_prefix` or specify `location` per table:

```sql
SET pg_lake_iceberg.default_location_prefix = 's3://mybucket/iceberg';

CREATE TABLE measurements (
  station_name text NOT NULL,
  measurement double precision NOT NULL
) USING iceberg;
```

With **managed storage**, create tables without specifying a location:

```sql
CREATE TABLE measurements (
  station_name text NOT NULL,
  measurement double precision NOT NULL
) USING iceberg;
```

If managed storage is provisioned for the instance, data goes to a Snowflake-managed bucket. If it fails with a 403 on an internal S3 path, managed storage is not available — use customer-managed S3 instead.

**Without any storage**, you can still query public URLs via foreign tables and load data from HTTPS URLs using `load_from`.

### Reading Postgres Iceberg tables from Snowflake

Managed-storage instances can be queried from Snowflake directly via `CATALOG_SOURCE = SNOWFLAKE_POSTGRES` — no Parquet copy, no staging. Per-table or catalog-linked-database (CLD) exposure. Cloud-platform support varies — see Snowflake docs (`cortex search docs "snowflake_postgres catalog integration"`).

See **`references/snowflake-catalog-integration.md`** for the full flow — workflow, SQL shapes, auto-refresh cost model, and the translated error patterns.

Customer-S3 instances use the external-stage + `COPY INTO` path instead — see `references/data-movement.md`.

## Creating Iceberg Tables

```sql
-- Basic: uses default_location_prefix (or managed storage if provisioned)
CREATE TABLE measurements (
  station_name text NOT NULL,
  measurement double precision NOT NULL
) USING iceberg;

-- With explicit S3 location (customer-managed)
CREATE TABLE measurements (
  station_name text NOT NULL,
  measurement double precision NOT NULL
) USING iceberg WITH (location = 's3://mybucket/measurements/');

-- From query result
CREATE TABLE summary
USING iceberg
AS SELECT region, count(*) FROM events GROUP BY region;

-- From file (auto-detect schema + load data)
CREATE TABLE taxi ()
USING iceberg
WITH (load_from = 's3://bucket/yellow_tripdata.parquet');

-- From file (schema only, no data loaded)
CREATE TABLE taxi ()
USING iceberg
WITH (definition_from = 's3://bucket/yellow_tripdata.parquet');
```

### Table Options

| Option | Description |
|--------|-------------|
| `location` | S3 URL prefix for table storage |
| `format` | File format when loading from file |
| `definition_from` | Infer columns from a file URL |
| `load_from` | Infer columns and load data from a file URL |

## Loading Data

```sql
-- COPY from S3
COPY measurements FROM 's3://bucket/data.parquet';
COPY measurements FROM 's3://bucket/data.csv' WITH (FORMAT csv, HEADER true);

-- Insert from query
INSERT INTO measurements SELECT * FROM staging_table;

-- Batch insert (recommended over single-row inserts)
INSERT INTO measurements VALUES
  ('Station A', 18.5),
  ('Station B', 22.1);
```

**Best practice:** Load in batches. Single-row inserts create many small Parquet files. Use a staging table with pg_cron for streaming inserts:

```sql
CREATE TABLE measurements_staging (LIKE measurements);

-- pg_cron flushes staging → Iceberg every minute
SELECT cron.schedule('flush', '* * * * *', $$
  WITH new_rows AS (
    DELETE FROM measurements_staging RETURNING *
  )
  INSERT INTO measurements SELECT * FROM new_rows;
$$);
```

> For continuous sync from a separate operational table (rather than streaming inserts landing in a staging buffer), see `incremental-sync.md` — it covers pg_incremental's time-interval, sequence, and file-list pipelines with exactly-once state tracking across runs.

## Hidden Partitioning

Define partitioning at table creation — Iceberg handles the rest (no manual partition management).

```sql
CREATE TABLE events (
  event_time timestamptz NOT NULL,
  user_id bigint NOT NULL,
  region text NOT NULL,
  payload jsonb
) USING iceberg
WITH (partition_by = 'day(event_time), bucket(32, user_id)');
```

### Partition Transforms

| Transform | Description | Good for |
|-----------|-------------|----------|
| `col` | Identity (value as-is) | Low-cardinality: region, status |
| `year(col)` | Extract year | Coarse time partitioning |
| `month(col)` | Extract year+month | Monthly aggregates |
| `day(col)` | Extract full date | Time-series, logs |
| `hour(col)` | Extract hour | High-volume hourly events |
| `bucket(N, col)` | Hash into N buckets | High-cardinality: user_id |
| `truncate(N, col)` | Truncate to N chars/multiple | Prefix-based filtering |

### Evolving Partitions

```sql
-- Change partitioning (applies to new data only)
ALTER TABLE events OPTIONS (SET partition_by 'month(event_time), truncate(4, region)');

-- Add partitioning to unpartitioned table
ALTER TABLE events OPTIONS (ADD partition_by 'day(event_time)');

-- Remove partitioning
ALTER TABLE events OPTIONS (DROP partition_by);
```

### Best Practices

- Partition tables >10GB with predictable filter patterns
- Avoid high-cardinality partition keys — use `bucket(N, col)` instead
- Time-based data: `month(event_time)` or `day(event_time)`
- Fewer partitions = fewer small files = better read performance
- Run VACUUM regularly on partitioned tables

## ALTER TABLE

**⚠️ DROP COLUMN and destructive ALTER operations require explicit user approval.**

```sql
-- Add column
ALTER TABLE events ADD COLUMN source text;

-- Drop column (metadata-only, fast — but irreversible)
ALTER TABLE events DROP COLUMN source;

-- Rename
ALTER TABLE events RENAME COLUMN source TO event_source;

-- Change partition strategy
ALTER TABLE events OPTIONS (SET partition_by 'month(event_time)');
```

## VACUUM

Iceberg tables accumulate small files over time. VACUUM merges them into larger, optimized files.

```sql
-- Manual vacuum
VACUUM events;

-- Autovacuum is enabled by default (pg_lake_iceberg.autovacuum_enabled = on)
-- Tune thresholds per table:
ALTER TABLE events SET (
  autovacuum_vacuum_threshold = 50000,
  autovacuum_vacuum_cost_delay = 0
);
```

## Catalog Views

```sql
-- List all Iceberg tables
SELECT table_schema, table_name, location, format_version
FROM iceberg_tables;

-- List snapshots (version history)
SELECT * FROM iceberg_snapshots WHERE table_name = 'events';

-- Table metadata (file count, size, partitions)
SELECT * FROM pg_lake_iceberg.metadata('events');
```

## Query Pushdown (EXPLAIN)

pg_lake extends Postgres with a vectorized query engine that processes data in batches. Use EXPLAIN VERBOSE to verify pushdown and partition pruning:

```sql
-- Show execution plan with pushdown details
EXPLAIN VERBOSE SELECT * FROM events WHERE event_time > '2024-01-01';

-- Check partition pruning on filtered queries
EXPLAIN VERBOSE SELECT region, count(*) FROM events
  WHERE event_time BETWEEN '2024-06-01' AND '2024-06-30'
  GROUP BY region;
```

Look for `Custom Scan (Query Pushdown)` and `Vectorized SQL` in the output — these indicate computation is delegated to the vectorized engine. A `ForeignScan` means only part of the query was pushed down.

If the output includes `Not Vectorized Constructs`, those functions/operators fell back to row-by-row Postgres execution.

## DROP TABLE

**⚠️ DESTRUCTIVE — Requires explicit user approval before executing.**

```sql
DROP TABLE events;
DROP TABLE events CASCADE;
```

DROP TABLE deletes the Parquet files from S3 permanently — this is unrecoverable. CASCADE also drops dependent objects (views, foreign keys). Never run DROP TABLE without the user explicitly asking to delete the table.

## Limitations

- Numeric types without precision/scale become numeric(38,9)
- Numeric values cannot be NaN or infinite
- Intervals not supported as column types
- Geometry: only point, linestring, polygon, multi* types supported
- Custom base types stored as text representation (suboptimal performance)
