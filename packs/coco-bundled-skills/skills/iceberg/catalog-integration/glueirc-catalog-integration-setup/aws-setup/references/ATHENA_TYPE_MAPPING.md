# Athena Type Mapping — Parquet to Iceberg to Snowflake

## When to use this reference

- **Proactively in Phase 4** — After the crawler finishes, cross-reference every column's Glue-inferred type against the official docs.
- **Reactively in Phase 5** — When a CTAS fails with HIVE_BAD_DATA, use the debugging steps below to identify and fix the mismatch.

## Official Documentation

For the full, authoritative type mapping tables, refer to these docs:

- **Parquet → Athena types**: [Athena Data Types](https://docs.aws.amazon.com/athena/latest/ug/data-types.html)
- **Athena → Iceberg types**: [Athena Iceberg Table Properties](https://docs.aws.amazon.com/athena/latest/ug/querying-iceberg-creating-tables.html)
- **Iceberg → Snowflake types**: [Snowflake Iceberg Data Types](https://docs.snowflake.com/en/user-guide/tables-iceberg-data-types)
- **Glue crawler type inference**: [AWS Glue Built-in Classifiers](https://docs.aws.amazon.com/glue/latest/dg/custom-classifier.html)

## Common Gotchas (not obvious from docs)

These are the type mismatches that frequently cause `HIVE_BAD_DATA` errors during Athena CTAS and aren't well-documented:

| Scenario | Symptom | Root Cause | Fix |
|----------|---------|------------|-----|
| BINARY column looks numeric | `HIVE_BAD_DATA: Failed to decode` | Parquet stores as raw BINARY bytes, but Glue declares as DOUBLE | Declare as STRING, then `CAST(col AS DOUBLE)` in CTAS |
| INT64 ID column | `HIVE_BAD_DATA` on ID/numeric columns | Parquet stores as INT64, but Glue infers as STRING | Declare as BIGINT |
| DOUBLE column looks like text | CTAS produces wrong values | Glue infers as STRING if sample values look textual | Declare as DOUBLE |
| Athena TIMESTAMP → Snowflake | Unexpected TIMESTAMP_NTZ behavior | Athena `TIMESTAMP` has no timezone → Iceberg `timestamp` → Snowflake `TIMESTAMP_NTZ(6)` | Use `TIMESTAMP WITH TIME ZONE` in Athena if TZ matters |
| STRUCT in Trino DML | `SYNTAX_ERROR` | Trino uses `ROW(...)` syntax, not `STRUCT<...>` | Use ROW syntax in CTAS SELECT |

## Debugging Type Mismatches

1. **Check actual parquet schema** (if pyarrow is available — `pip install pyarrow` first):
   ```python
   import pyarrow.parquet as pq
   schema = pq.read_schema('file.parquet')
   for field in schema:
       print(f"{field.name}: {field.type} (physical: {field.physical_type})")
   ```

2. **Check Glue catalog declaration**:
   ```bash
   aws glue get-table --database-name <DB> --name <TABLE> \
     --query 'Table.StorageDescriptor.Columns[].{Name:Name,Type:Type}'
   ```

3. **Compare and fix**: If Glue says `string` but parquet is `INT64`, create a new external table with the correct type, or use explicit CASTs in your CTAS.

## CTAS with Explicit Casts

When types don't match, use explicit casting in the SELECT:

```sql
CREATE TABLE db.table_iceberg
WITH (table_type='ICEBERG', location='s3://bucket/iceberg/table/', is_external=false)
AS SELECT
  CAST(id AS BIGINT) AS id,
  name,
  CAST(price AS DOUBLE) AS price,
  CAST(created_at AS TIMESTAMP) AS created_at
FROM db.table_source
```
