# Dynamic Table Decomposition Guide

How to break large, complex dynamic tables into smaller, more efficient ones.

> **Note:** This guide uses INFORMATION_SCHEMA functions. See [monitoring-functions.md](monitoring-functions.md) for critical usage requirements (named parameters, database context).

---

## When to Decompose

Consider decomposing a dynamic table when:

| Indicator | Threshold | Action |
|-----------|-----------|--------|
| Refresh duration | > 50% of target lag | Decompose to reduce refresh time |
| Query complexity | > 5 JOINs | Split into intermediate stages |
| Refresh mode | FULL when INCREMENTAL expected | Isolate unsupported constructs |
| Query operators | Single operator > 30% of time | Extract expensive operation |
| Data volume | Refresh scans > 100GB | Materialize intermediate results |

---

## Decomposition Workflow

### Step 1: Analyze Current Query Performance

```sql
-- Get recent refresh query_id
SELECT query_id, 
       DATEDIFF('second', refresh_start_time, refresh_end_time) as duration_sec
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(name=>'MY_LARGE_DT'))
WHERE state = 'SUCCESS'
ORDER BY refresh_start_time DESC
LIMIT 1;
```

### Step 2: Profile Query Operators

```sql
-- Find expensive operators
SELECT 
  operator_id,
  operator_type,
  operator_statistics:"output_rows" as output_rows,
  operator_statistics:"input_rows" as input_rows,
  execution_time_breakdown:"overall_percentage" as pct_of_query_time,
  operator_statistics,
  operator_attributes
FROM TABLE(GET_QUERY_OPERATOR_STATS('<query_id>'))
ORDER BY execution_time_breakdown:"overall_percentage" DESC
LIMIT 15;
```

### Step 3: Identify Decomposition Points

Look for:
- **Expensive JOINs** (HashJoin, MergeJoin with high execution_time)
- **Large aggregations** (Aggregate operators with many input_rows)
- **Table scans** (TableScan with high bytes_scanned)
- **Sorting** (Sort operators on large datasets)

### Step 4: Design Intermediate DTs

```
Original Query:
┌─────────────────────────────────────────────────────────┐
│ SELECT ...                                              │
│ FROM large_table_a a                                    │
│ JOIN large_table_b b ON a.id = b.id  ← Expensive JOIN  │
│ JOIN dim_table c ON a.type = c.type                     │
│ GROUP BY ...  ← Heavy aggregation                       │
│ HAVING ...                                              │
└─────────────────────────────────────────────────────────┘

Decomposed:
┌─────────────────────────────────────────────────────────┐
│ Intermediate DT 1 (TARGET_LAG = DOWNSTREAM):            │
│ Materialize expensive JOIN                              │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ SELECT a.*, b.key_columns                           │ │
│ │ FROM large_table_a a                                │ │
│ │ JOIN large_table_b b ON a.id = b.id                 │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Final DT (TARGET_LAG = '5 minutes'):                    │
│ Uses intermediate DT, simpler query                      │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ SELECT ...                                          │ │
│ │ FROM intermediate_dt_1 i                            │ │
│ │ JOIN dim_table c ON i.type = c.type  ← Small join   │ │
│ │ GROUP BY ...                                        │ │
│ └─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Common Decomposition Patterns

### Pattern 1: Extract Expensive JOIN

**Before:**
```sql
CREATE DYNAMIC TABLE final_dt
  TARGET_LAG = '5 minutes'
  WAREHOUSE = compute_wh
  AS
    SELECT o.*, c.customer_name, p.product_name, s.store_name
    FROM orders o
    JOIN customers c ON o.customer_id = c.id     -- Large join
    JOIN products p ON o.product_id = p.id       -- Large join
    JOIN stores s ON o.store_id = s.id;
```

**After:**
```sql
-- Intermediate: Materialize largest join
CREATE DYNAMIC TABLE staging.orders_with_customer
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = compute_wh
  REFRESH_MODE = ADAPTIVE
  AS
    SELECT o.*, c.customer_name
    FROM orders o
    JOIN customers c ON o.customer_id = c.id;

-- Final: Simpler remaining joins
CREATE DYNAMIC TABLE final_dt
  TARGET_LAG = '5 minutes'
  WAREHOUSE = compute_wh
  REFRESH_MODE = ADAPTIVE
  AS
    SELECT oc.*, p.product_name, s.store_name
    FROM staging.orders_with_customer oc
    JOIN products p ON oc.product_id = p.id
    JOIN stores s ON oc.store_id = s.id;
```

### Pattern 2: Split Multi-Stage Aggregation

**Before:**
```sql
CREATE DYNAMIC TABLE final_summary
  TARGET_LAG = '10 minutes'
  AS
    SELECT 
      region,
      DATE_TRUNC('month', order_date) as month,
      SUM(amount) as total,
      COUNT(DISTINCT customer_id) as unique_customers,
      AVG(amount) as avg_order
    FROM raw.orders
    GROUP BY 1, 2;
```

**After:**
```sql
-- Intermediate: Daily pre-aggregation
CREATE DYNAMIC TABLE staging.daily_summary
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = compute_wh
  AS
    SELECT 
      region,
      DATE_TRUNC('day', order_date) as day,
      SUM(amount) as daily_total,
      COUNT(*) as order_count,
      ARRAY_AGG(DISTINCT customer_id) as customers
    FROM raw.orders
    GROUP BY 1, 2;

-- Final: Roll up to monthly
CREATE DYNAMIC TABLE final_summary
  TARGET_LAG = '10 minutes'
  WAREHOUSE = compute_wh
  AS
    SELECT 
      region,
      DATE_TRUNC('month', day) as month,
      SUM(daily_total) as total,
      ARRAY_SIZE(ARRAY_UNION_AGG(customers)) as unique_customers,
      SUM(daily_total) / SUM(order_count) as avg_order
    FROM staging.daily_summary
    GROUP BY 1, 2;
```

### Pattern 3: Isolate Full Refresh Logic

**Before:**
```sql
-- Entire DT uses FULL refresh due to EXCEPT
CREATE DYNAMIC TABLE final_dt
  TARGET_LAG = '5 minutes'
  REFRESH_MODE = FULL  -- Forced by EXCEPT
  AS
    SELECT * FROM active_customers
    EXCEPT
    SELECT * FROM blocked_customers;
```

**After:**
```sql
-- Intermediate: Anti-join pattern (supports ADAPTIVE)
CREATE DYNAMIC TABLE staging.valid_customers
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = compute_wh
  REFRESH_MODE = ADAPTIVE
  AS
    SELECT a.*
    FROM active_customers a
    LEFT JOIN blocked_customers b ON a.id = b.id
    WHERE b.id IS NULL;

-- Final: Uses pre-filtered data
CREATE DYNAMIC TABLE final_dt
  TARGET_LAG = '5 minutes'
  WAREHOUSE = compute_wh
  REFRESH_MODE = ADAPTIVE
  AS
    SELECT * FROM staging.valid_customers;
```

### Pattern 4: Flatten Before Transform

**Before:**
```sql
-- FLATTEN can prevent incremental
CREATE DYNAMIC TABLE final_dt AS
SELECT 
  id,
  f.value:name::STRING as item_name,
  f.value:qty::NUMBER as qty
FROM orders,
LATERAL FLATTEN(input => items) f;
```

**After:**
```sql
-- Intermediate: Flatten only (may need FULL)
CREATE DYNAMIC TABLE staging.flattened_items
  TARGET_LAG = DOWNSTREAM
  WAREHOUSE = compute_wh
  AS
    SELECT 
      id,
      f.value:name::STRING as item_name,
      f.value:qty::NUMBER as qty
    FROM orders,
    LATERAL FLATTEN(input => items) f;

-- Final: Simple transformation (ADAPTIVE)
CREATE DYNAMIC TABLE final_dt
  TARGET_LAG = '5 minutes'
  WAREHOUSE = compute_wh
  REFRESH_MODE = ADAPTIVE
  AS
    SELECT id, item_name, qty
    FROM staging.flattened_items
    WHERE qty > 0;
```

---

## Key Rules for Decomposition

### 1. Use DOWNSTREAM for Intermediates

```sql
-- Intermediate DTs always use DOWNSTREAM
CREATE DYNAMIC TABLE staging.intermediate
  TARGET_LAG = DOWNSTREAM  -- Refreshes only when needed
  ...
```

### 2. Final DT Preserves Original Properties Not Requested to Be Modified by the User

```sql
-- The final/leaf DT MUST use the same TARGET_LAG as the original
-- Read these from SHOW DYNAMIC TABLES before decomposing
CREATE DYNAMIC TABLE final
  TARGET_LAG = '<original_lag>'  -- e.g. '1 hour' if original was '1 hour'
  AS ...
```

The final DT replaces the original, so it must match the original's TARGET_LAG, output schema and other properties unless the user requested them to be modified.

### 3. Match Warehouse Across Pipeline

Use the same warehouse for the entire pipeline for consistent performance.

### 4. Enable Change Tracking on All Sources

Ensure all base tables (not DTs) have change tracking enabled.

---

## Verification Queries

### Compare Before/After Performance

```sql
-- Before decomposition (from prior INFORMATION_SCHEMA query or
-- SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY for windows >7 days)
-- Avg refresh time: X seconds

-- After decomposition
SELECT 
  name,
  AVG(DATEDIFF('second', refresh_start_time, refresh_end_time)) as avg_sec
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME_PREFIX => 'MY_DB.STAGING'  -- Include intermediate DTs
))
WHERE refresh_start_time > DATEADD('hour', -1, CURRENT_TIMESTAMP())
GROUP BY name;
```

### Verify Pipeline Structure

```sql
-- Check all DTs in pipeline
SELECT name, inputs, target_lag_type, scheduling_state
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY())
WHERE name LIKE '%my_pipeline%'
ORDER BY ARRAY_SIZE(inputs);  -- Base tables first
```

### Verify Refresh Mode

```sql
-- Confirm intermediate DTs are INCREMENTAL (refresh_mode is only in SHOW, not INFORMATION_SCHEMA)
SHOW DYNAMIC TABLES LIKE 'INTERMEDIATE_%' IN SCHEMA <database>.<schema>;
SELECT "name", "refresh_mode", "refresh_mode_reason"
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()));
```

---

## Rollback Plan

If decomposition doesn't improve performance:

1. Keep original DT definition saved
2. Drop intermediate DTs
3. Recreate original single DT

```sql
-- Rollback
DROP DYNAMIC TABLE staging.intermediate_1;
DROP DYNAMIC TABLE staging.intermediate_2;

CREATE OR REPLACE DYNAMIC TABLE final_dt
  TARGET_LAG = '5 minutes'
  WAREHOUSE = compute_wh
  AS <original_query>;
```

---

## Success Criteria

Decomposition is successful when:

- [ ] Total refresh time reduced (sum of all DT refreshes < original)
- [ ] Intermediate DTs use INCREMENTAL mode
- [ ] Final DT refresh time < target lag
- [ ] time_within_target_lag_ratio > 0.95
- [ ] No increase in error rate

