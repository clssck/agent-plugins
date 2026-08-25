---
name: interactive-warehouse
description: "Create and manage Snowflake interactive warehouses. Triggers: create interactive warehouse, add tables to warehouse, remove tables, resume warehouse, suspend warehouse, manage interactive warehouse."
parent_skill: snowflake-interactive
---

# Interactive Warehouse Management

Workflow for creating, configuring, and managing interactive warehouses.

## When to Load

Main skill routes here when user wants to:
- Create a new interactive warehouse
- Add or remove tables from a warehouse
- Resume or suspend an interactive warehouse
- Check warehouse status

---

## Workflow

### Step 1: Determine Operation

**Ask** user:
```
What warehouse operation do you need?

1. **Create** - Create new interactive warehouse
2. **Add Tables** - Associate interactive tables with warehouse
3. **Remove Tables** - Disassociate tables from warehouse
4. **Resume** - Start suspended warehouse
5. **Suspend** - Suspend running warehouse
6. **Status** - Check warehouse state
7. **Set Fallback** - Configure a fallback warehouse for timeout handling
8. **Configure Auto-Suspend** - Set auto-suspend to reduce idle costs
```

**Route based on selection:**
- Option 1 → [Create Warehouse](#create-warehouse)
- Option 2 → [Add Tables](#add-tables-to-warehouse)
- Option 3 → [Remove Tables](#remove-tables-from-warehouse)
- Option 4 → [Resume Warehouse](#resume-warehouse)
- Option 5 → [Suspend Warehouse](#suspend-warehouse)
- Option 6 → [Check Status](#check-warehouse-status)
- Option 7 → [Set Fallback Warehouse](#set-fallback-warehouse)
- Option 8 → [Configure Auto-Suspend](#configure-auto-suspend)

---

## Create Warehouse

### Step 2: Gather Requirements

**Ask** user for:
- Warehouse name
- Warehouse size (XSMALL, SMALL, MEDIUM, LARGE, etc.)
- Tables to associate (optional)

### Step 3: Generate CREATE Statement

**SQL Pattern (with tables):**
```sql
CREATE OR REPLACE INTERACTIVE WAREHOUSE {{warehouse_name}}
TABLES ({{table_list}})
WAREHOUSE_SIZE = '{{warehouse_size}}';
```

**SQL Pattern (without tables):**
```sql
CREATE OR REPLACE INTERACTIVE WAREHOUSE {{warehouse_name}}
WAREHOUSE_SIZE = '{{warehouse_size}}';
```

**Sizing Guidelines:**

Based on working data set size (the portion of data frequently queried):

| Working Set Size | Recommended Warehouse Size |
|------------------|----------------------------|
| Less than 350 GB | XSMALL |
| 350 GB to 700 GB | SMALL |
| 700 GB to 1.4 TB | MEDIUM |
| 1.4 TB to 2.8 TB | LARGE |
| 2.8 TB to 5.6 TB | XLARGE |
| 5.6 TB to 11.2 TB | 2XLARGE |
| Greater than 11 TB | 3XLARGE |

**Note**: The working set is the portion of the table that is frequently queried (e.g., last 7 days of data), not the entire table size.

**Example:**
```sql
CREATE OR REPLACE INTERACTIVE WAREHOUSE dashboard_iwh
TABLES (db.schema.customers_interactive, db.schema.orders_interactive)
WAREHOUSE_SIZE = 'XSMALL';
```

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval.

### Step 4: Execute and Resume

1. **Execute** the approved CREATE statement
2. **Resume** the warehouse (created in SUSPENDED state):
   ```sql
   ALTER WAREHOUSE {{warehouse_name}} RESUME;
   ```
3. **Verify** state:
   ```sql
   SHOW WAREHOUSES LIKE '{{warehouse_name}}';
   ```

**Output:** Interactive warehouse created and running

---

## Add Tables to Warehouse

### Step 2: Identify Tables

**Ask** user for:
- Warehouse name
- Fully qualified table names to add

### Step 3: Validate Warehouse Access

Before generating the ALTER statement, verify the interactive warehouse exists and the user has USAGE permission:

```sql
-- Verify warehouse exists
SHOW WAREHOUSES LIKE '{{interactive_warehouse_name}}';

-- Verify current role has USAGE permission
SHOW GRANTS ON WAREHOUSE {{interactive_warehouse_name}};
```

If the warehouse does not exist or the user lacks USAGE privilege, inform the user and stop.

### Step 4: Generate ALTER Statement

**SQL Pattern:**
```sql
ALTER WAREHOUSE {{warehouse_name}}
ADD TABLES ({{fully.qualified.table_name}});
```

**Important:** Use fully qualified names: `DATABASE.SCHEMA.TABLE`

**Example:**
```sql
ALTER WAREHOUSE dashboard_iwh
ADD TABLES (mydb.myschema.products_interactive, mydb.myschema.regions_interactive);
```

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statement for approval.

### Step 5: Execute and Verify

1. **Execute** the approved ALTER statement
2. **Note:** No RESUME needed after ADD TABLES
3. **Verify** by querying from the warehouse

**Output:** Tables associated with warehouse

---

## Remove Tables from Warehouse

### Step 2: Identify Tables

**Ask** user for:
- Warehouse name
- Fully qualified table names to remove

### Step 3: Generate ALTER Statement

**SQL Pattern:**
```sql
ALTER WAREHOUSE {{warehouse_name}}
DROP TABLES ({{fully.qualified.table_name}});
```

**Note:** Use `DROP TABLES` (not `REMOVE TABLES`)

**Example:**
```sql
ALTER WAREHOUSE dashboard_iwh
DROP TABLES (mydb.myschema.old_table);
```

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statement for approval.

### Step 4: Execute

1. **Execute** the approved ALTER statement
2. **Verify** table removed

**Output:** Tables disassociated from warehouse

---

## Resume Warehouse

### Step 2: Generate RESUME Command

**SQL:**
```sql
ALTER WAREHOUSE {{warehouse_name}} RESUME;
```

**Idempotent version:**
```sql
ALTER WAREHOUSE {{warehouse_name}} RESUME IF SUSPENDED;
```

**Note:** Expect some latency when resuming - warehouse needs to start up.

### Step 3: Execute and Verify

1. **Execute** the RESUME command
2. **Verify** state:
   ```sql
   SHOW WAREHOUSES LIKE '{{warehouse_name}}';
   ```

**Output:** Warehouse running

---

## Suspend Warehouse

### Step 2: Generate SUSPEND Command

**SQL:**
```sql
ALTER WAREHOUSE {{warehouse_name}} SUSPEND;
```

**⚠️ Warning:** Queries will fail while suspended.

**⚠️ MANDATORY STOPPING POINT**: Confirm user wants to suspend (affects query availability).

### Step 3: Execute

1. **Execute** the SUSPEND command
2. **Verify** state

**Output:** Warehouse suspended

---

## Check Warehouse Status

### Diagnostic Queries

**Check specific warehouse:**
```sql
SHOW WAREHOUSES LIKE '{{warehouse_name}}';
```

**Check all interactive warehouses:**
```sql
SHOW WAREHOUSES;
```

**Key columns to check:**
- `state`: STARTED, SUSPENDED, RESUMING
- `size`: Warehouse size
- `running`: Queries currently running
- `queued`: Queries waiting

**Output:** Warehouse status report

---

## Key Notes

### Warehouse Behavior
- Created in **SUSPENDED state** - must RESUME after CREATE
- Supports auto-suspend — configure via `ALTER WAREHOUSE ... SET AUTO_SUSPEND = <seconds>`
- Supports auto-scale — MIN_CLUSTER_COUNT and MAX_CLUSTER_COUNT can differ
- **Can only query interactive tables** - cannot query standard tables

### Cost Considerations
- Configure `AUTO_SUSPEND` to reduce idle costs automatically (e.g., `SET AUTO_SUSPEND = 86400` for 24 hours)
- Or manually suspend during off-hours to save costs
- Consider smaller size and scale up if needed
- Consolidate related tables in same warehouse

---

## Set Fallback Warehouse

### When to Use

Configure a fallback warehouse when:
- A **small portion** of your queries occasionally exceed the 5-second timeout
- You have a mixed workload (fast dashboard queries + occasional ad-hoc analytics)
- You've already optimized clustering and query patterns but residual outliers remain

**Important:** Fallback warehouse is a safety net for occasional outlier queries, not a path for routing the bulk of your workload. If most queries are timing out, fix clustering/sizing first.

### Step 2: Gather Requirements

**Ask** user for:
- Interactive warehouse name (the primary warehouse)
- Fallback warehouse name (must be a **non-interactive** warehouse — standard, snowpark-optimized, etc. Must be **equal or larger** size than the interactive warehouse.)

### Step 3: Generate ALTER Statement

**SQL Pattern (set fallback):**
```sql
ALTER WAREHOUSE {{interactive_warehouse_name}}
SET FALLBACK_WAREHOUSE = {{fallback_warehouse_name}};
```

**SQL Pattern (remove fallback):**
```sql
ALTER WAREHOUSE {{interactive_warehouse_name}} UNSET FALLBACK_WAREHOUSE;
```

**Key Details:**
- The fallback warehouse can be any warehouse type **EXCEPT interactive**
- The fallback warehouse must be **equal or larger** in size than the interactive warehouse
- When a query exceeds 5 seconds on the interactive warehouse, it is transparently retried on the fallback warehouse 
- Zero overhead for queries that complete within the primary timeout
- Transparent to clients — the query succeeds instead of erroring, no application changes needed
- Self-reference (fallback = primary) is rejected

**Example:**
```sql
-- Create a standard warehouse as fallback
CREATE WAREHOUSE IF NOT EXISTS batch_fallback_wh
WAREHOUSE_SIZE = 'MEDIUM'
AUTO_SUSPEND = 60
AUTO_RESUME = TRUE;

-- Link fallback to interactive warehouse
ALTER WAREHOUSE dashboard_iwh
SET FALLBACK_WAREHOUSE = batch_fallback_wh;
```

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statement for approval.

### Step 4: Execute and Verify

1. **Execute** the approved ALTER statement
2. **Verify** configuration:
   ```sql
   SHOW WAREHOUSES LIKE '{{interactive_warehouse_name}}';
   ```

**Output:** Fallback warehouse configured

---

## Configure Auto-Suspend

### When to Use

Configure auto-suspend to automatically stop the warehouse during idle periods and reduce credits consumed overnight or on weekends.

### Step 2: Gather Requirements

**Ask** user for:
- Warehouse name
- Idle timeout in seconds (how long before suspending — e.g., 86400 = 24 hours minimum), or NULL to disable auto-suspend

### Step 3: Generate ALTER Statements

**If user provides a value below 86400:** Inform the user that the minimum is 86400 seconds (24 hours) and that Snowflake will silently use 86400 regardless. Confirm they want to proceed before generating SQL.

**If user wants to disable auto-suspend:** Use NULL instead of a number:
```sql
ALTER WAREHOUSE {{warehouse_name}} SET AUTO_SUSPEND = NULL;
```

**If user provides a valid value (>= 86400):** Generate the standard ALTER statements:

```sql
-- Suspend warehouse automatically after {{seconds}} seconds of inactivity
ALTER WAREHOUSE {{warehouse_name}} SET AUTO_SUSPEND = {{seconds}};

-- Auto-resume when a query is submitted (recommended alongside auto-suspend)
ALTER WAREHOUSE {{warehouse_name}} SET AUTO_RESUME = TRUE;
```

**Valid values for AUTO_SUSPEND (minimum is 86400 — 24 hours):**
- `86400` — 24 hours (minimum allowed)
- `172800` — 48 hours
- `NULL` — disable auto-suspend

**Note:** Set `AUTO_RESUME = TRUE` so the warehouse restarts automatically when a query arrives. Without it, users will get errors on a suspended warehouse.

**⚠️ MANDATORY STOPPING POINT**: Present ALTER statements for approval.

### Step 4: Execute and Verify

1. **Execute** the approved ALTER statements
2. **Verify** configuration:
   ```sql
   SHOW WAREHOUSES LIKE '{{warehouse_name}}';
   ```
   Check the `auto_suspend` and `auto_resume` columns in the output.

**Output:** Auto-suspend configured

---

## Stopping Points Summary

1. ✋ Before CREATE warehouse
2. ✋ Before ADD/DROP tables
3. ✋ Before SUSPEND (affects availability)
4. ✋ Before SET FALLBACK_WAREHOUSE
5. ✋ Before SET AUTO_SUSPEND

**Resume rule:** Only proceed after explicit user approval.

---

## Output

- Warehouse created/modified as specified
- Status verified
- Tables associated/disassociated as needed
