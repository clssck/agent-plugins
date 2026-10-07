---
name: interactive-update-delete
description: "UPDATE/DELETE operations for interactive tables via standard + dynamic pattern. Triggers: update interactive table, delete from interactive, modify interactive data, soft delete interactive."
parent_skill: snowflake-interactive
---

# UPDATE/DELETE Operations

Interactive tables do NOT support UPDATE or DELETE directly. Use the Standard + Dynamic pattern instead.

## When to Load

Main skill routes here when user wants to:
- UPDATE data in an interactive table
- DELETE data from an interactive table
- Modify existing records
- Set up a pattern for ongoing DML operations

---

## The Problem

```sql
-- ❌ These will FAIL on interactive tables:
UPDATE orders_interactive SET status = 'SHIPPED' WHERE id = 123;
DELETE FROM orders_interactive WHERE status = 'CANCELLED';
```

**Error:** `SQL compilation error: UPDATE/DELETE is not supported on interactive tables`

---

## The Solution: Standard + Dynamic Pattern

**Architecture:**
```
┌─────────────────────┐     ┌──────────────────────────┐     ┌─────────────────────┐
│  Standard Table     │     │  Dynamic Interactive     │     │  Interactive        │
│  (for DML)          │ ──► │  Table (auto-sync)       │ ◄── │  Warehouse          │
│                     │     │                          │     │  (for queries)      │
│  UPDATE ✓           │     │  TARGET_LAG refreshes    │     │                     │
│  DELETE ✓           │     │  from standard table     │     │  Low-latency        │
│  INSERT ✓           │     │                          │     │  queries            │
└─────────────────────┘     └──────────────────────────┘     └─────────────────────┘
```

---

## Workflow

### Step 1: Check If Pattern Already Exists

**Ask** user:
```
Do you already have a standard table backing this interactive table?

1. **Yes** - I have a standard table, just need to do DML
2. **No** - I need to set up the standard + dynamic pattern first
```

- If Yes → Skip to [Step 4: Perform DML](#step-4-perform-dml)
- If No → Continue to Step 2

---

### Step 2: Create Standard Table

**Option A - Create from existing interactive table:**
```sql
-- Copy data from interactive to standard table
CREATE TABLE {{database}}.{{schema}}.{{standard_table_name}} AS
SELECT * FROM {{database}}.{{schema}}.{{interactive_table_name}};
```

**Option B - Create new standard table:**
```sql
CREATE TABLE {{database}}.{{schema}}.{{standard_table_name}} (
  {{column_definitions}}
);
```

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval.

---

### Step 3: Create Dynamic Interactive Table

Replace the existing interactive table with a dynamic one that syncs from the standard table:

```sql
CREATE OR REPLACE INTERACTIVE TABLE {{database}}.{{schema}}.{{interactive_table_name}}
CLUSTER BY ({{cluster_columns}})
TARGET_LAG = '{{target_lag}}'
WAREHOUSE = {{standard_warehouse}}
AS SELECT * FROM {{database}}.{{schema}}.{{standard_table_name}};
```

**TARGET_LAG Selection:**

| Update Frequency | Recommended LAG |
|------------------|-----------------|
| Frequent (every few minutes) | 1-5 minutes |
| Moderate (hourly) | 10-30 minutes |
| Infrequent (daily) | 1 hour+ |

**Example:**
```sql
CREATE OR REPLACE INTERACTIVE TABLE mydb.myschema.orders_interactive
CLUSTER BY (order_id, customer_id)
TARGET_LAG = '1 minute'
WAREHOUSE = my_standard_wh
AS SELECT * FROM mydb.myschema.orders_standard;
```

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval.

---

### Step 4: Perform DML

Now perform UPDATE/DELETE on the **standard table**:

**UPDATE:**
```sql
UPDATE {{database}}.{{schema}}.{{standard_table_name}}
SET {{column}} = {{value}}
WHERE {{condition}};
```

**DELETE:**
```sql
DELETE FROM {{database}}.{{schema}}.{{standard_table_name}}
WHERE {{condition}};
```

**INSERT:**
```sql
INSERT INTO {{database}}.{{schema}}.{{standard_table_name}}
VALUES ({{values}});
```

**Examples:**
```sql
-- Update order status
UPDATE mydb.myschema.orders_standard
SET status = 'SHIPPED'
WHERE order_id = 12345;

-- Delete cancelled orders
DELETE FROM mydb.myschema.orders_standard
WHERE status = 'CANCELLED';

-- Insert new order
INSERT INTO mydb.myschema.orders_standard
VALUES (67890, 100, '2024-01-15', 150.00, 'PENDING');
```

---

### Step 5: Verify Sync

Changes propagate to interactive table after TARGET_LAG interval.

**Verify on standard table (immediate):**
```sql
USE WAREHOUSE standard_wh;
SELECT * FROM {{standard_table_name}} WHERE {{condition}};
```

**Verify on interactive table (after TARGET_LAG):**
```sql
USE WAREHOUSE {{interactive_warehouse}};
SELECT * FROM {{interactive_table_name}} WHERE {{condition}};
```

**Note:** If TARGET_LAG is 1 minute, wait ~70 seconds for sync.

---

## Complete Example

```sql
-- Step 1: Standard table for modifications
CREATE TABLE mydb.myschema.orders_standard (
  order_id INT,
  customer_id INT,
  order_date DATE,
  amount DECIMAL(10,2),
  status VARCHAR(20)
);

-- Step 2: Insert initial data
INSERT INTO mydb.myschema.orders_standard VALUES
  (1, 100, '2024-01-01', 150.00, 'PENDING'),
  (2, 101, '2024-01-02', 200.00, 'SHIPPED'),
  (3, 100, '2024-01-03', 75.00, 'PENDING');

-- Step 3: Create dynamic interactive table
CREATE INTERACTIVE TABLE mydb.myschema.orders_interactive
CLUSTER BY (order_id, customer_id)
TARGET_LAG = '1 minute'
WAREHOUSE = standard_wh
AS SELECT * FROM mydb.myschema.orders_standard;

-- Step 4: Perform DML on standard table
UPDATE mydb.myschema.orders_standard
SET status = 'SHIPPED'
WHERE order_id = 1;

DELETE FROM mydb.myschema.orders_standard
WHERE order_id = 3;

-- Step 5: Query interactive table (after TARGET_LAG)
USE WAREHOUSE dashboard_iwh;
SELECT * FROM mydb.myschema.orders_interactive;
-- Results reflect changes from standard table
```

---

## Alternative: INSERT OVERWRITE

For complete data replacement (not incremental updates):

```sql
INSERT OVERWRITE INTO {{interactive_table_name}}
SELECT * FROM {{source_query}};
```

**Use when:**
- Full refresh is acceptable
- Source data is authoritative
- Changes are batch-loaded

**Note:** `INTO` keyword is required for INSERT OVERWRITE syntax.

---

## Stopping Points Summary

1. ✋ Before creating standard table
2. ✋ Before creating/replacing dynamic interactive table
3. ✋ Verify changes synced correctly

**Resume rule:** Only proceed after explicit user approval.

---

## Output

- Standard + Dynamic pattern established
- DML operations performed on standard table
- Changes verified in interactive table after sync
