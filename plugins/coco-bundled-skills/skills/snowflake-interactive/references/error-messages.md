# Common Error Messages for Snowflake Interactive Tables and Warehouses

## Table of Contents
1. [DML Operation Errors](#dml-operation-errors)
2. [Query Execution Errors](#query-execution-errors)
3. [Table Creation Errors](#table-creation-errors)
4. [Warehouse Errors](#warehouse-errors)
5. [Streaming/Pipe Errors](#streamingpipe-errors)
6. [Schema/Metadata Errors](#schemametadata-errors)

---

## DML Operation Errors

### UPDATE Not Supported
**Error Message**:
```
SQL compilation error: UPDATE is not supported on interactive tables
```

**Cause**: Attempted to UPDATE an interactive table directly

**Solution**: Use Standard + Dynamic Table pattern
```sql
-- Create standard table
CREATE TABLE orders_standard (...);

-- Perform UPDATE on standard table
UPDATE orders_standard SET status = 'SHIPPED' WHERE id = 123;

-- Create dynamic interactive table that syncs
CREATE INTERACTIVE TABLE orders_interactive
CLUSTER BY (id)
TARGET_LAG = '1 minute'
WAREHOUSE = standard_wh
AS SELECT * FROM orders_standard;
```

---

### DELETE Not Supported
**Error Message**:
```
SQL compilation error: DELETE is not supported on interactive tables
```

**Cause**: Attempted to DELETE from an interactive table

**Solution**: Use Standard + Dynamic Table pattern (same as UPDATE)

---

### Direct INSERT Not Supported (Streaming Tables)
**Error Message**:
```
SQL compilation error: Cannot INSERT directly into streaming interactive table
```

**Cause**: Attempted SQL INSERT into streaming interactive table

**Solution**: Use streaming source (Kafka connector, Snowpipe Streaming SDK)
```
Streaming tables accept data through pipes, not SQL INSERT statements.
Configure Kafka connector or use Snowpipe Streaming SDK.
```

---

## Query Execution Errors

### Query Timeout
**Error Message**:
```
Query execution exceeded timeout limit of 5 seconds
```

**Cause**: Query took longer than 5-second interactive warehouse limit

**Solutions**:
1. **Simplify query**: Remove expensive operations (cartesian products, large joins)
2. **Add filtering**: Use WHERE clause on clustered columns
3. **Add LIMIT**: Restrict result set size
4. **Optimize clustering**: Match clustering to query patterns
5. **Scale warehouse**: Increase warehouse size

**Example**:
```sql
-- Instead of:
SELECT * FROM large_table;  -- Timeout!

-- Do:
SELECT * FROM large_table
WHERE date >= '2024-01-01'  -- Filter on clustered column
LIMIT 1000;  -- Limit results
```

**With Fallback Warehouse configured:**

This error is suppressed. Instead of returning error 630 to the client, the query is transparently retried on the designated fallback warehouse (must be non-interactive). The client sees a successful result.

```sql
-- Configure fallback to prevent this error for outlier queries
-- Fallback must be a non-interactive warehouse
ALTER WAREHOUSE interactive_wh SET FALLBACK_WAREHOUSE = batch_wh;
```

**Note:** This is a last-resort safety net. Optimize queries first (filtering, LIMIT, clustering, warehouse sizing) before relying on fallback.

---

### Cannot Query Standard Table
**Error Message**:
```
Cannot query standard Snowflake table from interactive warehouse
```

**Cause**: Attempted to query non-interactive table from interactive warehouse

**Solution**: Switch to standard warehouse
```sql
-- For standard tables
USE WAREHOUSE standard_wh;
SELECT * FROM standard_table;

-- For interactive tables
USE WAREHOUSE interactive_wh;
SELECT * FROM interactive_table;
```

---

## Table Creation Errors

### Missing CLUSTER BY
**Error Message**:
```
SQL compilation error: CLUSTER BY clause is required for interactive tables
```

**Cause**: Created interactive table without CLUSTER BY

**Solution**: Add CLUSTER BY clause
```sql
-- Wrong:
CREATE INTERACTIVE TABLE my_table
AS SELECT * FROM source;

-- Correct:
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (id, date)
AS SELECT * FROM source;
```

---

### TARGET_LAG Below Minimum
**Error Message**:
```
Invalid TARGET_LAG value. Minimum is 60 seconds or 1 minute
```

**Cause**: Set TARGET_LAG below 60 seconds

**Solution**: Use minimum of '1 minute' or '60 seconds'
```sql
-- Wrong:
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (id)
TARGET_LAG = '30 seconds'  -- Too low!
WAREHOUSE = wh
AS SELECT * FROM source;

-- Correct:
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (id)
TARGET_LAG = '1 minute'  -- Minimum allowed
WAREHOUSE = wh
AS SELECT * FROM source;
```

---

### Missing WAREHOUSE for Dynamic Table
**Error Message**:
```
WAREHOUSE clause is required when TARGET_LAG is specified
```

**Cause**: Specified TARGET_LAG without WAREHOUSE

**Solution**: Add WAREHOUSE clause
```sql
-- Wrong:
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (id)
TARGET_LAG = '5 minutes'
AS SELECT * FROM source;

-- Correct:
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (id)
TARGET_LAG = '5 minutes'
WAREHOUSE = my_standard_warehouse
AS SELECT * FROM source;
```

---

## Warehouse Errors

### Table Not Found for Association
**Error Message**:
```
Table 'my_table' does not exist or not authorized
```

**Cause**: Tried to add non-existent or non-interactive table to warehouse

**Solution**: Verify table exists and is interactive; use fully qualified name
```sql
-- Check table exists
SHOW TABLES LIKE 'my_table';

-- Use fully qualified name
ALTER INTERACTIVE WAREHOUSE iwh_name
ADD TABLES (DATABASE.SCHEMA.my_table);
```

---

### Warehouse Not Running
**Error Message**:
```
Warehouse 'iwh_name' is not running
```

**Cause**: Attempted to query from suspended warehouse

**Solution**: Resume warehouse first
```sql
ALTER WAREHOUSE iwh_name RESUME;

-- Then query
USE WAREHOUSE iwh_name;
SELECT * FROM my_table;
```

---

### Cannot Create Multi-Cluster with Auto-Scale
**Error Message**:
```
Interactive warehouses do not support auto-scaling
```

**Cause**: Tried to set MIN_CLUSTER_COUNT != MAX_CLUSTER_COUNT

**Solution**: Set both to same value
```sql
-- Wrong:
CREATE INTERACTIVE WAREHOUSE iwh_name
MIN_CLUSTER_COUNT = 1
MAX_CLUSTER_COUNT = 3  -- Auto-scale not supported
WAREHOUSE_SIZE = 'XSMALL';

-- Correct:
CREATE INTERACTIVE WAREHOUSE iwh_name
MIN_CLUSTER_COUNT = 2
MAX_CLUSTER_COUNT = 2  -- Same value
WAREHOUSE_SIZE = 'XSMALL';
```

---

## Streaming/Pipe Errors

### Pipe Already Exists
**Error Message**:
```
Pipe 'my_table' already exists
```

**Cause**: Snowflake auto-creates pipe with same name as streaming table

**Context**: This is expected behavior. When you create a streaming interactive table, a pipe with the same name is automatically created.

**Solution**: Use `CREATE OR REPLACE` if recreating table
```sql
CREATE OR REPLACE INTERACTIVE TABLE my_table (...)
CLUSTER BY (...)
AS (...);
```

---

### Authentication Failure (Streaming)
**Error Message**:
```
Authentication failed: Invalid key pair
```

**Cause**: Key-pair authentication issue with Kafka connector

**Solutions**:
1. Verify public key associated with user:
```sql
SHOW USERS LIKE 'streaming_user';
```

2. Regenerate key pair:
```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

3. Update user:
```sql
ALTER USER streaming_user SET RSA_PUBLIC_KEY='<formatted_public_key>';
```

---

## Schema/Metadata Errors

### Cannot Create Stream
**Error Message**:
```
Streams are not supported on interactive tables
```

**Cause**: Attempted to create stream on interactive table

**Solution**: Create stream on source table instead
```sql
-- Wrong:
CREATE STREAM my_stream ON TABLE interactive_table;

-- Correct:
CREATE STREAM my_stream ON TABLE source_table;
```

---

### Cannot Alter Table Structure
**Error Message**:
```
ALTER TABLE ADD COLUMN is not supported on interactive tables
```

**Cause**: Tried to add column to interactive table

**Solution**: Only RENAME is supported; otherwise recreate table
```sql
-- Supported:
ALTER TABLE my_interactive_table RENAME TO new_name;

-- Not supported:
-- ALTER TABLE my_interactive_table ADD COLUMN new_col INT;

-- Instead, recreate:
CREATE OR REPLACE INTERACTIVE TABLE my_interactive_table
CLUSTER BY (...)
AS SELECT *, NULL AS new_col FROM source;
```

---

### Cannot Apply Masking Policy
**Error Message**:
```
Data masking policies are not supported on interactive tables
```

**Cause**: Tried to apply masking policy

**Solution**: Apply masking to source table, not interactive table
```sql
-- Apply to source table
ALTER TABLE source_table 
MODIFY COLUMN sensitive_col SET MASKING POLICY mask_policy;

-- Interactive table will reflect masked data from source
CREATE INTERACTIVE TABLE secure_interactive
CLUSTER BY (id)
TARGET_LAG = '5 minutes'
WAREHOUSE = wh
AS SELECT * FROM source_table;
```

---

### Cannot Create Materialized View
**Error Message**:
```
Interactive tables cannot be used as source for materialized views
```

**Cause**: Tried to create materialized view from interactive table

**Solution**: Use source table or standard table
```sql
-- Wrong:
CREATE MATERIALIZED VIEW my_mv AS
SELECT * FROM interactive_table;

-- Correct:
CREATE MATERIALIZED VIEW my_mv AS
SELECT * FROM source_table;
```

---

### Cannot Create Dynamic Table from Interactive Base
**Error Message**:
```
Interactive tables cannot be used as base table for dynamic tables
```

**Cause**: Tried to create dynamic table with interactive table as source

**Solution**: Use standard table as base
```sql
-- Wrong:
CREATE DYNAMIC TABLE my_dt
TARGET_LAG = '1 hour'
WAREHOUSE = wh
AS SELECT * FROM interactive_table;

-- Correct:
CREATE DYNAMIC TABLE my_dt
TARGET_LAG = '1 hour'
WAREHOUSE = wh
AS SELECT * FROM standard_table;
```

---

### Pipe Operator Not Supported
**Error Message**:
```
Pipe operator (-\u003e>) is not supported in interactive warehouses
```

**Cause**: Used ->> operator in query

**Solution**: Use traditional SQL syntax
```sql
-- Wrong:
SELECT * FROM my_table ->> SELECT * FROM another_table;

-- Correct:
USE WAREHOUSE interactive_wh;
SELECT * FROM my_table WHERE ...;

-- Then separately:
SELECT * FROM another_table WHERE ...;
```

---

### Cannot Call Stored Procedure
**Error Message**:
```
CALL commands are not supported in interactive warehouses
```

**Cause**: Tried to execute stored procedure from interactive warehouse

**Solution**: Switch to standard warehouse
```sql
-- Switch to standard warehouse
USE WAREHOUSE standard_wh;

-- Call procedure
CALL my_procedure(param1, param2);

-- Switch back to interactive for queries
USE WAREHOUSE interactive_wh;
SELECT * FROM my_table;
```

---

## Error Diagnosis Checklist

When encountering an error:

1. **Read the full error message**: Often contains specific details
2. **Check object types**:
   - Is it an interactive table?
   - Is it an interactive warehouse?
   - Is it a streaming table?
3. **Verify privileges**: Do you have required permissions?
4. **Check warehouse state**: Is it running or suspended?
5. **Review SQL syntax**: Does it match documented patterns?
6. **Check constraints**:
   - CLUSTER BY present?
   - TARGET_LAG >= 1 minute?
   - WAREHOUSE specified with TARGET_LAG?
7. **Consult troubleshooting guide**: See `troubleshooting.md`

---

## Quick Reference: What's Supported vs. Not Supported

### ✅ Supported Operations
- SELECT queries
- WHERE, GROUP BY, ORDER BY, LIMIT
- Joins between interactive tables
- Aggregations (COUNT, SUM, AVG, etc.)
- INSERT OVERWRITE (static tables)
- CREATE, DROP, RENAME
- SHOW, DESCRIBE

### ❌ Not Supported Operations
- UPDATE
- DELETE
- ALTER TABLE (except RENAME)
- INSERT (for streaming tables)
- Streams
- Materialized views (as source)
- Dynamic tables (as base)
- Masking policies
- Row access policies
- Aggregation policies
- Join policies
- CALL (stored procedures)
- ->> pipe operator
- RESAMPLE clause

---

*This document will be updated with actual error messages encountered during testing.*
