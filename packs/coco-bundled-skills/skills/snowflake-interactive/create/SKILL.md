---
name: interactive-create
description: "Create Snowflake interactive tables (static, dynamic). Triggers: create interactive table, make interactive, convert to interactive, static interactive, dynamic interactive."
parent_skill: snowflake-interactive
---

# Create Interactive Table

Workflow for creating interactive tables using static CTAS, dynamic TARGET_LAG

## When to Load

Main skill routes here when user wants to:
- Create a new interactive table
- Set up static data with CTAS
- Create auto-refreshing table with TARGET_LAG

---

## Workflow

### Step 1: Determine Table Type

**Goal:** Understand what type of interactive table the user needs

**Ask** user:
```
Which type of interactive table do you need?

1. **Static** - One-time load, manual updates via INSERT OVERWRITE
2. **Dynamic** - Auto-refreshes from source with TARGET_LAG
```

**Route based on selection:**
- Option 1 → Continue to [Static Table Workflow](#static-table-workflow)
- Option 2 → Continue to [Dynamic Table Workflow](#dynamic-table-workflow)

**⚠️ MANDATORY STOPPING POINT**: Get type selection before proceeding.

---

## Static Table Workflow

### Step 2a: Gather Static Table Requirements

**Ask** user for:
- Source table or SELECT query
- Cluster columns (columns used in WHERE clauses)
- Database and schema location

**For help choosing clustering columns**, **Load** [clustering/SKILL.md](../clustering/SKILL.md)

### Step 2a.1: Check Source Size and Select Warehouse

**CRITICAL: Before generating CREATE statement, check source table size:**

```sql
SELECT 
  ROUND(bytes / POWER(1024, 3), 2) AS size_gb,
  row_count
FROM {{source_database}}.INFORMATION_SCHEMA.TABLES
WHERE table_schema = '{{source_schema}}' AND table_name = '{{source_table}}';
```

**Warehouse sizing for CTAS operations:**

| Source Table Size | Minimum Warehouse | Estimated Time |
|-------------------|-------------------|----------------|
| < 1 GB            | XSMALL            | < 1 min        |
| 1-10 GB           | SMALL             | 1-5 min        |
| 10-50 GB          | MEDIUM            | 5-15 min       |
| 50-100 GB         | LARGE             | 10-30 min      |
| 100-500 GB        | XLARGE            | 20-60 min      |
| 500 GB - 1 TB     | 2XLARGE           | 30-90 min      |
| > 1 TB            | 3XLARGE or larger | 60+ min        |

**⚠️ MANDATORY: If current warehouse is undersized:**
1. Check user's current warehouse: `SELECT CURRENT_WAREHOUSE();`
2. If undersized, **ask user** whether to:
   - Use an existing larger warehouse (list available warehouses)
   - Create a temporary warehouse for this operation
   - Proceed with current warehouse (warn about long execution time)

**Example - Create temporary warehouse for large CTAS:**
```sql
-- Create temporary large warehouse for 147GB table
CREATE WAREHOUSE IF NOT EXISTS TEMP_LARGE_WH
  WAREHOUSE_SIZE = 'LARGE'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = FALSE;

USE WAREHOUSE TEMP_LARGE_WH;

-- After CTAS completes, drop or suspend:
-- DROP WAREHOUSE TEMP_LARGE_WH;
```

### Step 3a: Generate CREATE Statement

**SQL Pattern:**
```sql
CREATE INTERACTIVE TABLE IF NOT EXISTS {{database}}.{{schema}}.{{table_name}}
CLUSTER BY ({{cluster_columns}})
AS SELECT * FROM {{source_table}};
```

**Example:**
```sql
CREATE INTERACTIVE TABLE mydb.myschema.customers_interactive
CLUSTER BY (customer_id, region)
AS SELECT * FROM mydb.myschema.customers_source;
```

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval.

### Step 4a: Execute and Verify

1. **Execute** the approved CREATE statement
2. **Verify** creation:
   ```sql
   SHOW TABLES LIKE '{{table_name}}';
   ```
3. **Report** row count and clustering

**Output:** Interactive table created and verified

---

## Dynamic Table Workflow

### Step 2b: Gather Dynamic Table Requirements

**Ask** user for:
- Source table for auto-refresh
- Cluster columns
- Refresh frequency (TARGET_LAG minimum: 1 minute)
- Standard warehouse for refresh operations

**For help choosing clustering columns**, **Load** [clustering/SKILL.md](../clustering/SKILL.md)

**Standard warehouse sizing for refresh operations:**

Choose warehouse size based on source table size for fast ingestion:

| Source Table Size | Recommended Standard Warehouse |
|-------------------|-------------------------------|
| < 1 GB | XSMALL |
| 1-10 GB | SMALL |
| 10-100 GB | MEDIUM |
| 100-500 GB | LARGE |
| 500 GB - 1 TB | XLARGE |
| > 1 TB | 2XLARGE or larger |

**Why?** Larger warehouses process data faster during initial load and refresh operations.

### Step 3b: Generate CREATE Statement

REFRESH_MODE is not supported by interactive tables

**SQL Pattern:**
```sql
CREATE INTERACTIVE TABLE {{database}}.{{schema}}.{{table_name}}
CLUSTER BY ({{cluster_columns}})
TARGET_LAG = '{{target_lag}}'
WAREHOUSE = {{warehouse_name}}
AS {{select_query}};
```

**TARGET_LAG Guidelines:**

| Use Case | Recommended LAG |
|----------|-----------------|
| Real-time dashboards | 1-5 minutes |
| Hourly reports | 30-60 minutes |
| Daily summaries | 4-12 hours |

**Example:**
```sql
-- Source table is 50 GB → use MEDIUM warehouse for fast refresh
CREATE INTERACTIVE TABLE mydb.myschema.orders_interactive
CLUSTER BY (order_id, customer_id)
TARGET_LAG = '5 minutes'
WAREHOUSE = medium_standard_wh  -- MEDIUM for 50 GB table
AS SELECT * FROM mydb.myschema.orders_source;
```

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval.

### Step 4b: Execute and Verify

1. **Execute** the approved CREATE statement
2. **Verify** creation and refresh status:
   ```sql
   SHOW TABLES LIKE '{{table_name}}';
   SELECT COUNT(*) FROM {{table_name}};
   ```
3. **Note:** First refresh happens after TARGET_LAG interval

**Output:** Dynamic interactive table created


---

## Best Practices

### Warehouse Sizing for CTAS
- **Always check source size first**: Query INFORMATION_SCHEMA.TABLES before creating
- **Match warehouse to data size**: 10GB source needs MEDIUM, 100GB+ needs XLARGE
- **Use temporary warehouses**: Create AUTO_SUSPEND=60 warehouse for large one-time loads
- **Don't use XSMALL for large tables**: Will timeout or take hours

### Clustering Strategy
- **Match WHERE clauses**: Cluster on columns used in query filters
- **Low cardinality first**: Put lower-cardinality columns first in CLUSTER BY
- **2-4 columns**: Optimal number of cluster columns
- **Use expressions**: `CLUSTER BY (TRUNC(timestamp, 'day'))`

### Avoid Common Mistakes
- **Don't use `SELECT *`**: Schema changes will break refresh
- **Don't set TARGET_LAG < 1 minute**: Minimum is 60 seconds
- **Don't forget WAREHOUSE**: Required when using TARGET_LAG
- **Don't skip warehouse sizing**: Large CTAS on small warehouse will fail/timeout

---

## Stopping Points Summary

1. ✋ After determining table type
2. ✋ After checking source size (if warehouse undersized, ask user)
3. ✋ After generating CREATE statement (before execution)
4. ✋ After execution (verify success)

**Resume rule:** Only proceed after explicit user approval.

---

## Output

- Created interactive table with appropriate configuration
- Verified table exists and contains expected data
