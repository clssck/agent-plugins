# RDS S3 Parquet Export + pg_lake Reference

AWS RDS can export snapshots directly to S3 as Apache Parquet files. Combined with `pg_lake`, this can be **significantly faster** than pg_dump/pg_restore for large databases.

## Why This Approach?

| Advantage | Explanation |
|-----------|-------------|
| **Parallel export** | RDS export runs in AWS background, doesn't impact production |
| **Columnar compression** | Parquet is 5-10x smaller than row-based dumps |
| **Direct S3 read** | pg_lake uses DuckDB's parallel engine to scan S3 |
| **No serialization** | Skip pg_dump text encoding/decoding overhead |

## Prerequisites

1. **Snowflake Postgres with pg_lake extension** (verify availability)
2. S3 bucket in same region as RDS
3. IAM role for RDS export
4. AWS credentials configured for pg_lake/DuckDB

## Workflow

### Step 1: Create and Export RDS Snapshot

```bash
# Create snapshot
aws rds create-db-snapshot \
    --db-instance-identifier <source-instance> \
    --db-snapshot-identifier migration-export-snapshot

# Start export to S3 (runs in background)
aws rds start-export-task \
    --export-task-identifier migration-export \
    --source-arn arn:aws:rds:<region>:<account>:snapshot:migration-export-snapshot \
    --s3-bucket-name <your-bucket> \
    --s3-prefix rds-export/ \
    --iam-role-arn arn:aws:iam::<account>:role/rds-s3-export-role \
    --kms-key-id <kms-key-id>

# Monitor export progress
aws rds describe-export-tasks \
    --export-task-identifier migration-export
```

### Step 2: Capture LSN for Logical Replication

```sql
-- On SOURCE: Note LSN at snapshot time
-- Run immediately after snapshot creation
SELECT pg_current_wal_lsn() AS snapshot_lsn;
```

### Step 3: Prepare Schema on Target

```bash
# Export schema-only from source
pg_dump --host=<source> --schema-only --no-owner --no-privileges \
    --file=schema.sql <database>

# Restore schema to Snowflake Postgres
psql --no-psqlrc --quiet --host=<snowflake_pg> -f schema.sql <database>
```

**⚠️ IMPORTANT**: Parquet export does NOT contain:
- Indexes (must recreate)
- Constraints (must recreate) 
- Sequences (capture current values separately)
- Functions/triggers (export separately)

### Step 4: Load Data via pg_lake

```sql
-- On Snowflake Postgres
CREATE EXTENSION pg_lake CASCADE;

-- Create foreign table pointing to exported Parquet files
-- RDS exports use format: <prefix>/<db>/<schema>.<table>/<partition>.parquet
CREATE FOREIGN TABLE orders_import()
SERVER pg_lake
OPTIONS (path 's3://<bucket>/rds-export/<db>/public.orders/*.parquet');

-- Verify schema was inferred correctly
\d orders_import

-- Load data (pg_lake uses DuckDB's parallel engine)
INSERT INTO orders SELECT * FROM orders_import;

-- Repeat for each table (can run in parallel sessions)
```

### Step 5: Handle Sequences

```sql
-- On SOURCE: Export sequence values
SELECT schemaname || '.' || sequencename AS seq_name, last_value
FROM pg_sequences;

-- On TARGET: Set sequence values
SELECT setval('public.orders_id_seq', <last_value>, true);
```

### Step 6: Rebuild Indexes and Constraints

```sql
-- Create indexes after data load (faster than loading with indexes)
CREATE INDEX CONCURRENTLY idx_orders_customer ON orders(customer_id);

-- Add constraints
ALTER TABLE orders ADD CONSTRAINT orders_pkey PRIMARY KEY (id);
ALTER TABLE order_items ADD CONSTRAINT fk_order 
    FOREIGN KEY (order_id) REFERENCES orders(id);
```

### Step 7: Position and Enable Logical Replication

```sql
-- On SOURCE: Advance slot to snapshot LSN
SELECT pg_replication_slot_advance('migration_sub', '<snapshot_lsn>');

-- On TARGET: Enable subscription to catch up
ALTER SUBSCRIPTION migration_sub ENABLE;
```

## Parquet Data Type Mapping

| PostgreSQL Type | Parquet Type | Notes |
|-----------------|--------------|-------|
| INTEGER | INT32 | Direct mapping |
| BIGINT | INT64 | Direct mapping |
| NUMERIC/DECIMAL | STRING | Precision preserved as string |
| TIMESTAMP | INT64 (micros) | Microseconds since epoch |
| TIMESTAMPTZ | INT64 (micros) | UTC normalized |
| JSON/JSONB | STRING | JSON as text |
| BYTEA | BINARY | Direct mapping |
| ARRAY types | LIST | Nested structure |
| UUID | STRING | 36-char string format |

## Performance Comparison

For a 500GB database:

| Method | Export Time | Transfer | Import Time | Total |
|--------|-------------|----------|-------------|-------|
| pg_dump/restore | 4-6 hrs | 2-3 hrs | 4-6 hrs | 10-15 hrs |
| RDS S3 Parquet + pg_lake | 2-4 hrs (background) | N/A (direct S3) | 2-4 hrs | 4-8 hrs |

## Limitations

1. **Schema recreation required** - Parquet doesn't include DDL
2. **No direct restore to RDS** - AWS limitation, but pg_lake bypasses this
3. **Data type conversions** - Some types converted to strings
4. **Partitioned tables** - May have naming variations
5. **pg_lake availability** - Verify extension is available in your Snowflake Postgres version

## When to Use This vs pg_dump

| Use RDS Parquet + pg_lake | Use pg_dump/restore |
|---------------------------|---------------------|
| Database > 200 GB | Database < 100 GB |
| Many large tables | Complex schema dependencies |
| Minimize source load critical | Need exact type fidelity |
| Parallel import beneficial | Simple, proven approach |

---

**See also:** [`pg-lake/SKILL.md`](../../../pg-lake/SKILL.md) — the Snowflake side of this flow, which registers the exported parquet as a pg_lake storage integration + Iceberg table for read access from Snowflake Postgres.
