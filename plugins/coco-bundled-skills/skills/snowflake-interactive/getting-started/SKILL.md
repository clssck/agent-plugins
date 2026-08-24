---
name: interactive-getting-started
description: "Getting started with interactive tables - convert existing tables, estimate sizing, pick clustering keys. Triggers: getting started with interactive, convert to interactive, migrate to interactive, set up interactive, first time interactive."
parent_skill: snowflake-interactive
---

# Getting Started with Interactive Tables

Complete workflow for users setting up interactive tables for the first time or converting existing tables.

## When to Load

Main skill routes here when user wants to:
- Get started with interactive tables from scratch
- Convert existing standard tables to interactive
- Migrate tables to interactive warehouses
- Set up their first interactive environment

---

## Workflow

### Step 1: Identify Tables to Make Interactive

**Ask** user:
```
Which tables do you want to make interactive?

Please provide:
- Database name
- Schema name
- Table names (one or more)
```

**If user is unsure which tables to convert**, ask:
```
What are your use cases for interactive tables?

Examples:
- Low-latency dashboards querying specific tables
- Real-time analytics on recent data
- High-concurrency API endpoints

Which tables support these use cases?
```

---

### Step 2: Estimate Table Sizes

For each table identified, estimate the **working data set size** (not total table size):

```sql
-- Get total table size
SELECT 
  table_catalog,
  table_schema,
  table_name,
  ROUND(bytes / POWER(1024, 3), 2) AS size_gb,
  row_count
FROM {{database}}.INFORMATION_SCHEMA.TABLES
WHERE table_schema = '{{schema}}'
  AND table_name IN ('{{table1}}', '{{table2}}', ...)
ORDER BY bytes DESC;
```

**Ask** user about working data set:
```
Your table {{table_name}} is {{total_size_gb}} GB total.

What portion of this data do you typically query?
- Last 7 days of data
- Last 30 days of data
- Last year of data
- All data equally

This helps us recommend the right warehouse size.
```

**Calculate working set size:**
```sql
-- Example: Estimate size of last 7 days
SELECT 
  ROUND(SUM(bytes) / POWER(1024, 3), 2) AS working_set_gb
FROM {{database}}.INFORMATION_SCHEMA.TABLES
WHERE table_name = '{{table_name}}'
  AND created >= CURRENT_DATE() - 7;

-- If date-partitioned, estimate by filtering rows
SELECT 
  ROUND(COUNT(*) * AVG_ROW_SIZE_BYTES / POWER(1024, 3), 2) AS estimated_gb
FROM (
  SELECT COUNT(*) as row_count
  FROM {{table_name}}
  WHERE date_column >= CURRENT_DATE() - 7
) counts
CROSS JOIN (
  SELECT bytes / row_count AS avg_row_size_bytes
  FROM {{database}}.INFORMATION_SCHEMA.TABLES
  WHERE table_name = '{{table_name}}'
) sizes;
```

---

### Step 3: Recommend Warehouse Size

Based on working data set size, recommend warehouse:

| Working Set Size | Recommended Warehouse Size |
|------------------|----------------------------|
| Less than 500 GB | XSMALL |
| 500 GB to 1 TB | SMALL |
| 1 TB to 2 TB | MEDIUM |
| 2 TB to 4 TB | LARGE |
| 4 TB to 8 TB | XLARGE |
| 8 TB to 16 TB | 2XLARGE |
| Greater than 16 TB | 3XLARGE |

**Present recommendation:**
```
Based on your working data set of {{working_set_gb}} GB:

Recommended warehouse size: {{recommended_size}}

This will provide good cache coverage for your frequently queried data.
You can scale up later if needed.
```

**⚠️ MANDATORY STOPPING POINT**: Get user confirmation on warehouse size before proceeding.

---

### Step 4: Choose Clustering Keys

For each table, determine the best clustering key.

**Ask** user:
```
For table {{table_name}}, what columns do you typically filter on in WHERE clauses?

Examples:
- customer_id
- order_date
- region
- event_timestamp

List 1-3 columns you filter on most frequently.
```

**If user has existing query history**, analyze it:
```sql
-- Find most-filtered columns (if query history available)
SELECT 
  column_name,
  COUNT(*) AS filter_count
FROM (
  -- This is conceptual - actual implementation varies
  -- Use QUERY_HISTORY + parsing or user knowledge
  SELECT column_name
  FROM query_filter_analysis
  WHERE table_name = '{{table_name}}'
)
GROUP BY column_name
ORDER BY filter_count DESC
LIMIT 5;
```

**For uncertain cases**, **Load** [clustering/SKILL.md](../clustering/SKILL.md) for detailed clustering guidance.

**Default heuristic** when unsure:
- Pick the most frequently filtered columns in WHERE clauses
- For date/timestamp columns: **always truncate to day**
- Order: **lowest cardinality to highest cardinality**
- Maximum 3-4 columns

**Example clustering keys:**
```sql
-- Good for order data filtered by customer and date
CLUSTER BY (customer_id, TO_DATE(order_date))

-- Good for time-series events filtered by date range
CLUSTER BY (TRUNC(event_timestamp, 'day'))

-- Good for multi-dimensional analytics
CLUSTER BY (region, TO_DATE(sale_date), product_category)
```

**⚠️ MANDATORY STOPPING POINT**: Present clustering key recommendations for approval.

---

### Step 5: Create Interactive Tables

For each table, create the interactive table:

**First, ensure you have an appropriately sized standard warehouse for data loading:**

| Source Table Size | Recommended Standard Warehouse |
|-------------------|-------------------------------|
| < 1 GB | XSMALL |
| 1-10 GB | SMALL |
| 10-100 GB | MEDIUM |
| 100-500 GB | LARGE |
| 500 GB - 1 TB | XLARGE |
| > 1 TB | 2XLARGE or larger |

**Option A: Static (one-time copy):**
```sql
-- Use appropriately sized warehouse for fast initial load
USE WAREHOUSE {{standard_warehouse}};  -- Size based on table above

CREATE INTERACTIVE TABLE {{database}}.{{schema}}.{{table_name}}_interactive
CLUSTER BY ({{clustering_columns}})
AS SELECT * FROM {{database}}.{{schema}}.{{table_name}};
```

**Option B: Dynamic (auto-refresh with TARGET_LAG):**
```sql
CREATE INTERACTIVE TABLE {{database}}.{{schema}}.{{table_name}}_interactive
CLUSTER BY ({{clustering_columns}})
TARGET_LAG = '{{target_lag}}'  -- e.g., '5 minutes'
WAREHOUSE = {{standard_warehouse}}  -- Size based on table above
AS SELECT * FROM {{database}}.{{schema}}.{{table_name}};
```

**Why warehouse size matters:**
- **Too small**: Initial load/refresh takes too long, may exceed TARGET_LAG
- **Right size**: Fast ingestion, data stays fresh
- **Too large**: Wastes credits, but data loads quickly

**Ask** user which option:
```
Do you need automatic refresh from the source table?

1. Static - One-time copy (manual updates via INSERT OVERWRITE)
2. Dynamic - Auto-refresh every {{target_lag}} minutes

Choose 1 or 2:
```

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval before executing.

---

### Step 6: Create Interactive Warehouse

Create the interactive warehouse with recommended size:

```sql
CREATE OR REPLACE INTERACTIVE WAREHOUSE {{warehouse_name}}
WAREHOUSE_SIZE = '{{recommended_size}}';
```

**Example:**
```sql
CREATE OR REPLACE INTERACTIVE WAREHOUSE my_dashboard_iwh
WAREHOUSE_SIZE = 'SMALL';
```

**⚠️ MANDATORY STOPPING POINT**: Get approval before creating warehouse.

---

### Step 7: Resume and Add Tables

Resume the warehouse and add the interactive tables:

```sql
-- Resume warehouse
ALTER WAREHOUSE {{warehouse_name}} RESUME;

-- Add tables
ALTER WAREHOUSE {{warehouse_name}}
ADD TABLES (
  {{database}}.{{schema}}.{{table1}}_interactive,
  {{database}}.{{schema}}.{{table2}}_interactive
);
```

**Note:** Wait a few minutes for cache warm-up after adding tables.

---

### Step 7b (Optional): Configure Fallback Warehouse

If your workload includes occasional complex queries alongside fast dashboard queries, configure a fallback warehouse as a safety net for outlier queries:

```sql
-- Fallback must be a non-interactive warehouse
CREATE WAREHOUSE IF NOT EXISTS fallback_wh
WAREHOUSE_SIZE = 'MEDIUM'
AUTO_SUSPEND = 60
AUTO_RESUME = TRUE;

ALTER WAREHOUSE {{warehouse_name}} SET FALLBACK_WAREHOUSE = fallback_wh;
```

Queries exceeding the 5-second timeout are transparently retried on the fallback warehouse. No application changes needed. See [warehouse/SKILL.md](../warehouse/SKILL.md) for details.

**Note:** Only configure this if you expect mixed workloads. If all your queries are optimized dashboard queries, fallback is unnecessary.

---

### Step 8: Test Queries

Test queries on the interactive tables from the interactive warehouse:

```sql
USE WAREHOUSE {{warehouse_name}};

-- Simple count test
SELECT COUNT(*) FROM {{database}}.{{schema}}.{{table_name}}_interactive;

-- Test filtering on clustering columns
SELECT * FROM {{database}}.{{schema}}.{{table_name}}_interactive
WHERE {{clustering_column}} = {{test_value}}
LIMIT 100;
```

**Verify:**
- ✅ Queries complete in < 5 seconds
- ✅ Results match expectations
- ✅ No timeout errors

**If queries timeout or are slow**, **Load** [troubleshoot/SKILL.md](../troubleshoot/SKILL.md).

---

### Step 9: Monitor Performance

Set up basic monitoring:

```sql
-- Check warehouse state
SHOW WAREHOUSES LIKE '{{warehouse_name}}';

-- Check query performance (last hour)
SELECT 
  query_id,
  LEFT(query_text, 100) AS query_preview,
  total_elapsed_time AS duration_ms,
  execution_status
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE warehouse_name = '{{warehouse_name}}'
  AND start_time >= DATEADD(hour, -1, CURRENT_TIMESTAMP())
ORDER BY start_time DESC
LIMIT 20;
```

---

## Complete Setup Example

Here's a complete example for a sales dashboard:

```sql
-- 1. Check existing table size
SELECT 
  table_name,
  ROUND(bytes / POWER(1024, 3), 2) AS size_gb,
  row_count
FROM sales_db.INFORMATION_SCHEMA.TABLES
WHERE table_name = 'ORDERS';
-- Result: 2.5 TB total, but queries only last 30 days (~ 700 GB)

-- 2. Create appropriately sized standard warehouse for refresh
-- Table is 2.5 TB → use 2XLARGE for fast refresh
CREATE WAREHOUSE IF NOT EXISTS refresh_wh
WAREHOUSE_SIZE = '2XLARGE'
AUTO_SUSPEND = 60
AUTO_RESUME = TRUE;

-- 3. Create interactive table with clustering
CREATE INTERACTIVE TABLE sales_db.public.orders_interactive
CLUSTER BY (customer_id, TO_DATE(order_date))
TARGET_LAG = '10 minutes'
WAREHOUSE = refresh_wh  -- 2XLARGE for 2.5 TB table
AS SELECT * FROM sales_db.public.orders;

-- 4. Create interactive warehouse (SMALL for 700 GB working set)
CREATE OR REPLACE INTERACTIVE WAREHOUSE sales_dashboard_iwh
WAREHOUSE_SIZE = 'SMALL';

-- 4. Resume and add table
ALTER WAREHOUSE sales_dashboard_iwh RESUME;

ALTER WAREHOUSE sales_dashboard_iwh
ADD TABLES (sales_db.public.orders_interactive);

-- 5. Test query
USE WAREHOUSE sales_dashboard_iwh;

SELECT 
  customer_id,
  COUNT(*) AS order_count,
  SUM(total_amount) AS total_sales
FROM sales_db.public.orders_interactive
WHERE order_date >= CURRENT_DATE() - 30
GROUP BY customer_id
ORDER BY total_sales DESC
LIMIT 100;
```

---

## Next Steps

After initial setup:

1. **Optimize clustering** if needed → Load [clustering/SKILL.md](../clustering/SKILL.md)
2. **Set up UPDATE/DELETE pattern** if needed → Load [update-delete/SKILL.md](../update-delete/SKILL.md)
3. **Benchmark performance** → See query/SKILL.md
4. **Monitor costs** → Check warehouse credit usage

---

## Common Getting-Started Issues

### "Table too large for conversion"

If your table is > 10 TB:
- Start with a subset (recent data)
- Create interactive table with WHERE filter
- Test performance before converting entire table

```sql
-- Create with recent data only
CREATE INTERACTIVE TABLE large_table_interactive
CLUSTER BY (date_column)
AS SELECT * FROM large_table
WHERE date_column >= CURRENT_DATE() - 365;
```

### "Unsure about clustering columns"

When uncertain about clustering:
- Use the most-filtered column in WHERE clauses
- For time-series: always use `TO_DATE(timestamp)` or `TRUNC(timestamp, 'day')`
- Start with 1-2 columns, refine later

### "Queries still slow after setup"

If queries are slow (> 3 seconds):
1. Wait 5-10 minutes for cache warm-up
2. Verify clustering matches WHERE clauses
3. Check warehouse size matches working data set
4. Scale up warehouse if needed

---

## Stopping Points Summary

1. ✋ After identifying tables (get confirmation)
2. ✋ After sizing recommendation (get approval on warehouse size)
3. ✋ After clustering key selection (get approval)
4. ✋ Before CREATE TABLE (get approval on SQL)
5. ✋ Before CREATE WAREHOUSE (get approval)
6. ✋ After testing (verify performance is acceptable)

**Resume rule:** Only proceed after explicit user approval at each checkpoint.

---

## Output

- Interactive tables created with appropriate clustering
- Interactive warehouse created with right size
- Tables associated with warehouse
- Test queries executed successfully
- Monitoring queries provided
- User ready to build applications on interactive tables
