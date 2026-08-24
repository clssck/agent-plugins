---
name: interactive-troubleshoot
description: "Troubleshoot errors and performance issues with interactive tables/warehouses. Triggers: interactive error, query timeout, table not found, warehouse issue, debug interactive, fix interactive."
parent_skill: snowflake-interactive
---

# Troubleshoot Interactive Tables & Warehouses

Diagnose and fix common issues with interactive tables and warehouses.

## When to Load

Main skill routes here when user reports:
- Query timeouts
- Error messages
- Performance issues
- Data not refreshing
- Streaming ingestion problems

---

## Quick Diagnosis

### Step 1: Identify the Issue

**Ask** user:
```
What issue are you experiencing?

1. **Query Timeout** - Queries failing after 5 seconds
2. **Error Message** - Getting a specific error
3. **Slow Performance** - Queries running but slow
4. **Refresh Not Working** - Dynamic table not syncing
5. **Streaming Not Working** - Data not flowing from Kafka
6. **Table Association** - Cannot add table to warehouse
7. **Benchmark/Test Performance** - Need to measure and compare query performance
```

**Route based on selection:**
- Option 1 → [Query Timeout](#query-timeout-issues)
- Option 2 → [Error Messages](#common-error-messages)
- Option 3 → [Performance Issues](#performance-issues)
- Option 4 → [Refresh Issues](#refresh-not-happening)
- Option 5 → [Streaming Issues](#streaming-ingestion-problems)
- Option 6 → [Association Issues](#table-association-errors)
- Option 7 → **Load** [query/SKILL.md](../query/SKILL.md) - See "Benchmarking Interactive Queries" section

---

## Query Timeout Issues

**Symptom:** Queries fail after 5 seconds with timeout error.

### Diagnosis

```sql
-- Test query complexity (run from standard warehouse)
SELECT CURRENT_TIMESTAMP() AS start_time;
-- Your query here
SELECT CURRENT_TIMESTAMP() AS end_time;
-- If > 5 seconds, will timeout on interactive warehouse
```

### Solutions

**1. Add Selective Filtering**
```sql
-- ❌ Timeout: Full table scan
SELECT * FROM large_table;

-- ✅ Fast: Filter on clustered columns
SELECT * FROM large_table
WHERE customer_id = 12345
  AND order_date >= '2024-01-01';
```

**2. Add LIMIT Clause**
```sql
SELECT * FROM orders
WHERE order_date >= '2024-01-01'
ORDER BY order_id
LIMIT 1000;  -- Prevents timeout
```

**3. Optimize Clustering**
```sql
-- Check current clustering
SHOW TABLES LIKE 'my_table';

-- Recreate with better clustering
DROP TABLE IF EXISTS my_table;
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (frequently_queried_column)
AS SELECT * FROM source;
```

**4. Scale Up Warehouse**
```sql
CREATE OR REPLACE INTERACTIVE WAREHOUSE iwh_name
TABLES (my_table)
WAREHOUSE_SIZE = 'MEDIUM';  -- Up from XSMALL
```

**5. Simplify Query**
- Remove CROSS JOINs
- Reduce subquery depth
- Avoid window functions

**6. Configure Fallback Warehouse**

If you've optimized queries but a small portion still occasionally exceed 5 seconds (e.g., ad-hoc analytics alongside dashboards), configure a fallback warehouse as a last-resort safety net:

```sql
-- Fallback can be any warehouse type EXCEPT interactive
CREATE WAREHOUSE IF NOT EXISTS interactive_fallback_wh
WAREHOUSE_SIZE = 'MEDIUM'
AUTO_SUSPEND = 60
AUTO_RESUME = TRUE;

ALTER WAREHOUSE interactive_wh SET FALLBACK_WAREHOUSE = interactive_fallback_wh;
```

Queries exceeding 5s are transparently retried on the fallback warehouse with a fresh timeout budget. No application changes needed.

**When to use this**: Dashboard queries are fast after optimization, but occasional complex queries still fail.

**When NOT to use this**: Most of your queries are timing out — that indicates a clustering/sizing problem that should be fixed first.

---

## Common Error Messages

### "UPDATE not supported on interactive tables"

**Solution:** Use Standard + Dynamic pattern

**→ Load** [update-delete/SKILL.md](../update-delete/SKILL.md)

### "DELETE not supported on interactive tables"

**Solution:** Use Standard + Dynamic pattern

**→ Load** [update-delete/SKILL.md](../update-delete/SKILL.md)

### "Cannot query standard table from interactive warehouse"

**Solution:** Switch to standard warehouse for standard tables:
```sql
USE WAREHOUSE standard_wh;
SELECT * FROM standard_table;
```

Or convert to interactive table:
**→ Load** [create/SKILL.md](../create/SKILL.md)

### "CLUSTER BY clause required"

**Solution:** Add CLUSTER BY when creating table:
```sql
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (id)  -- Required
AS SELECT * FROM source;
```

### "TARGET_LAG minimum is 60 seconds"

**Solution:** Use at least 1 minute:
```sql
CREATE INTERACTIVE TABLE my_table
CLUSTER BY (id)
TARGET_LAG = '1 minute'  -- Minimum
WAREHOUSE = wh
AS SELECT * FROM source;
```

### "Warehouse not running"

**Solution:** Resume warehouse:
```sql
ALTER WAREHOUSE iwh_name RESUME;
```

### "Table not found" (in ADD TABLES)

**Solution:** Use fully qualified name:
```sql
ALTER WAREHOUSE iwh_name
ADD TABLES (DATABASE.SCHEMA.table_name);  -- Fully qualified
```

### "Cannot create stream on interactive table"

**Solution:** Create stream on source table instead:
```sql
CREATE STREAM my_stream ON TABLE source_table;  -- Not interactive_table
```

---

## Performance Issues

**Symptom:** Queries complete but are slow (2-5 seconds).

### Checklist

1. **Check clustering matches query pattern**
   ```sql
   SHOW TABLES LIKE 'my_table';
   -- Verify cluster_by matches your WHERE clauses
   ```

2. **Add WHERE on clustered columns**
   ```sql
   -- ✅ Uses clustering
   WHERE customer_id = 12345 AND order_date >= '2024-01-01'
   ```

3. **Filter before JOIN**
   ```sql
   -- ✅ Filter early
   SELECT * FROM orders o
   JOIN customers c ON o.customer_id = c.customer_id
   WHERE o.order_date >= '2024-01-01'  -- Reduces data before join
   ```

4. **Scale warehouse if needed**
   ```sql
   CREATE OR REPLACE INTERACTIVE WAREHOUSE iwh_name
   WAREHOUSE_SIZE = 'SMALL';  -- Up from XSMALL
   ```

---

## Refresh Not Happening

**Symptom:** Dynamic interactive table not syncing from source.

### Diagnosis

```sql
-- Check table properties
SHOW TABLES LIKE 'dynamic_table';

-- Compare row counts
SELECT 'Source' AS table_type, COUNT(*) AS rows FROM source_table
UNION ALL
SELECT 'Interactive' AS table_type, COUNT(*) AS rows FROM dynamic_table;
```

### Solutions

**1. Wait for TARGET_LAG**
- If TARGET_LAG is 5 minutes, wait ~6 minutes
- Refresh happens on schedule, not immediately

**2. Verify refresh warehouse running**
```sql
SHOW WAREHOUSES LIKE 'refresh_wh';
ALTER WAREHOUSE refresh_wh RESUME;
```

**3. Check privileges**
```sql
SHOW GRANTS ON TABLE source_table;
SHOW GRANTS ON TABLE dynamic_table;
SHOW GRANTS ON WAREHOUSE refresh_wh;
```

**4. Verify source changed**
```sql
-- Check source has new data
SELECT COUNT(*), MAX(modified_timestamp) FROM source_table;
```

**5. Recreate if stuck**
```sql
CREATE OR REPLACE INTERACTIVE TABLE dynamic_table
CLUSTER BY (id)
TARGET_LAG = '1 minute'
WAREHOUSE = refresh_wh
AS SELECT * FROM source_table;
```

---

## Streaming Ingestion Problems

**Symptom:** Data not flowing from Kafka to streaming table.

### Diagnosis

```sql
-- Check table has data
SELECT COUNT(*) FROM streaming_table;

-- Check pipe exists
DESC PIPE streaming_table;
```

### Solutions

**1. Verify pipe status**
```sql
SHOW PIPES IN SCHEMA my_schema;
DESC PIPE streaming_table;
```
**Note:** Pipe may not appear until streaming client connects.

**2. Check Kafka connector config**
- Verify `snowflake.streaming.v2.enabled: true`
- Verify `snowflake.ingestion.method: SNOWPIPE_STREAMING`
- Verify `snowflake.topic2table.map` is correct

**3. Check authentication**
```sql
-- Verify public key set
SHOW USERS LIKE 'streaming_user';
```

**4. Check privileges**
```sql
GRANT ALL ON TABLE streaming_table TO ROLE streaming_role;
GRANT ALL ON PIPE streaming_table TO ROLE streaming_role;
```

**→ Load** [references/sql-syntax.md](../references/sql-syntax.md) for streaming setup details.

---

## Table Association Errors

**Symptom:** Cannot add table to interactive warehouse.

### Solutions

**1. Use fully qualified name**
```sql
ALTER WAREHOUSE iwh_name
ADD TABLES (DATABASE.SCHEMA.table_name);
```

**2. Verify table is interactive**
```sql
SHOW TABLES LIKE 'table_name';
-- Check it's an interactive table
```

**3. Ensure warehouse is running**
```sql
ALTER WAREHOUSE iwh_name RESUME;
```

**4. Check if already associated**
```sql
SHOW INTERACTIVE TABLES IN INTERACTIVE WAREHOUSE iwh_name;
```

---

## Diagnostic Flowchart

```
Issue?
│
├─ Queries timing out?
│  ├─ Check query complexity
│  ├─ Add WHERE/LIMIT
│  ├─ Optimize clustering
│  ├─ Scale warehouse
│  ├─ Simplify query
│  └─ Configure fallback warehouse (last resort for outliers)
│
├─ Data not refreshing?
│  ├─ Wait for TARGET_LAG
│  ├─ Check refresh warehouse
│  └─ Verify privileges
│
├─ Streaming not working?
│  ├─ Verify pipe exists
│  ├─ Check Kafka config
│  └─ Check authentication
│
├─ Error messages?
│  └─ See Common Error Messages section
│
└─ Can't add table?
   ├─ Use fully qualified name
   └─ Verify table is interactive
```

---

## Additional References

For detailed error messages: **Load** [references/error-messages.md](../references/error-messages.md)

For monitoring queries: **Load** [references/monitoring.md](../references/monitoring.md)

---

## Stopping Points Summary

Most troubleshooting is **diagnostic** (read-only). Only request approval for mutations.

- **Diagnostic queries**: Execute freely - no approval needed
- **CREATE OR REPLACE**: ⚠️ **MANDATORY** - Requires approval (destructive)
- **ALTER/DROP commands**: ⚠️ **MANDATORY** - Requires approval
- **Refresh operations**: ⚠️ **MANDATORY** - May impact data freshness

---

## Output

- Issue diagnosed
- Solution applied or recommended
- Verification performed
