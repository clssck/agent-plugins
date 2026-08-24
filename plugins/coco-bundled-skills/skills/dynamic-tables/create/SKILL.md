---
name: dynamic-tables-create
description: "Create new Snowflake dynamic tables with proper configuration"
parent_skill: dynamic-tables
---

# Create Dynamic Table

## Mandatory Rules

**Before writing AI function SQL, read `../../../sql/references/sql-authoring-rules.md`.**

Workflow for creating new dynamic tables with appropriate refresh mode, target lag, and warehouse configuration.

## When to Load

Main skill routes here when user wants to:
- Create a new dynamic table (first-time creation)
- Set up a DT pipeline
- Define transformation as a dynamic table

**For modifying an existing DT** (changing query, adding columns, switching refresh mode, updating properties), route to [create-or-alter/SKILL.md](../create-or-alter/SKILL.md) instead — it handles schema evolution and property omission safely.

---

## Workflow

### Step 1: Gather Requirements

**Goal:** Understand what the user wants to build

**Actions:**

1. **Ask** user for:
   - Source table(s) or view(s) for the dynamic table
   - Transformation logic (SELECT query)
   - Freshness requirements (how often should data be updated?)
   - Whether this is a final table or intermediate in a pipeline

**⚠️ MANDATORY STOPPING POINT**: Get requirements before proceeding.

---

### Step 2: Verify Base Objects

**Goal:** Ensure base objects are ready for dynamic table

**Actions:**

1. **Check change tracking** on base tables:
   ```sql
   SHOW TABLES LIKE '<base_table_name>';
   -- Check change_tracking column is TRUE
   ```
   
   For views:
   ```sql
   SHOW VIEWS LIKE '<base_view_name>';
   ```

2. **If change tracking is FALSE**, prepare ALTER statement:
   ```sql
   ALTER TABLE <base_table> SET CHANGE_TRACKING = TRUE;
   ```

**⚠️ MANDATORY STOPPING POINT**: Present change tracking status. If ALTER needed, get approval before executing.

---

### Step 3: Determine Configuration

**Goal:** Select appropriate refresh mode and target lag

**Actions:**

1. **Determine refresh mode** based on query complexity:

   | Refresh Mode | When to Use |
   |--------------|-------------|
   | `AUTO` | Development/testing - let Snowflake decide |
   | `INCREMENTAL` | Simple queries, small data changes (<5% per refresh) |
   | `FULL` | Complex queries, non-deterministic functions, or when INCREMENTAL not supported |

   **Load** [references/incremental-operators.md](../references/incremental-operators.md) to check if query supports incremental.

2. **Determine target lag**:

   | Target Lag | When to Use |
   |------------|-------------|
   | `DOWNSTREAM` | Intermediate tables in pipelines |
   | `'X minutes'` | Final/leaf tables with specific freshness needs |

   **Load** [references/supported-queries.md](../references/supported-queries.md) to check query patterns and limitations.

3. **Determine initialization**:

   | Initialize | When to Use |
   |------------|-------------|
   | `ON_CREATE` (default) | Populate immediately |
   | `ON_SCHEDULE` | Defer until first scheduled refresh |

4. **Select warehouse**: Recommend dedicated warehouse for cost isolation

**⚠️ MANDATORY STOPPING POINT**: Present configuration recommendations and get approval.

---

### Step 4: Generate CREATE Statement

**Goal:** Build the CREATE DYNAMIC TABLE statement

If the SELECT query uses any AI or Cortex function, read `../../../sql/references/sql-authoring-rules.md` first.

**Actions:**

1. **Generate statement** using approved configuration:

   ```sql
   CREATE OR ALTER DYNAMIC TABLE <database>.<schema>.<name>
     TARGET_LAG = '<time>' | DOWNSTREAM
     WAREHOUSE = <warehouse_name>
     REFRESH_MODE = ADAPTIVE | INCREMENTAL | FULL | AUTO
     INITIALIZE = ON_CREATE | ON_SCHEDULE
     AS
       <SELECT query>;
   ```

   `CREATE OR ALTER` is idempotent: if the table already exists with the same definition it is a no-op. If you need to be certain the table is brand new, use `CREATE OR REPLACE` instead (but note it always reinitializes and cascades to downstream incremental DTs).

2. **Review best practices**:
   - Use explicit column names (avoid `SELECT *`)
   - Use fully qualified table names
   - For pipelines: intermediate tables use `DOWNSTREAM`, only final table has time-based lag

**⚠️ MANDATORY STOPPING POINT**: Present CREATE statement for approval before executing.

---

### Step 5: Execute and Verify

**Goal:** Create the dynamic table and verify it's working

**IMPORTANT:** **Load** [references/monitoring-functions.md](../references/monitoring-functions.md) for required database context, named parameter rules, and routing to the specific monitoring reference you need (state, refresh analysis, or graph).

**Actions:**

1. **Execute** the approved CREATE statement

2. **Verify creation** - Use `SHOW DYNAMIC TABLES` and `INFORMATION_SCHEMA.DYNAMIC_TABLES()` per the monitoring reference

3. **Waiting logic** (depends on initialization mode):

   **If INITIALIZE = ON_CREATE:**
   - No waiting needed - table is populated immediately
   - Proceed to Step 6

   **If INITIALIZE = ON_SCHEDULE:**
   - **Ask user** if they want to wait for the first refresh to complete. Tell the user how long they will likely wait (target_lag).
   - If user says NO: Proceed to Step 6 immediately
   - If user says YES: Wait for target_lag duration, then poll for completion

   **Polling Strategy (only if user chose to wait):**
   - Initial wait: Wait for the target_lag duration (e.g., if TARGET_LAG = '5 minutes', wait 5 minutes)
   - Poll interval: 1 minute
   - Backoff: Double interval after each poll (1 min → 2 min → 4 min)
   - Max wait: 15 minutes total after initial target_lag wait
   - Timeout action: Present current state and ask user how to proceed

   **Poll query:** Use `DYNAMIC_TABLE_REFRESH_HISTORY()` from the monitoring reference to check refresh state.

   **Interpret results:**
   - **Success criteria**: `state = 'SUCCESS'` → Proceed to next step
   - **Continue polling if**: No rows returned OR `state` is NULL/empty (refresh in progress)
   - **Stop and diagnose if**: `state = 'FAILED'` → Present error to user

**⚠️ MANDATORY STOPPING POINT**: Present creation results. Confirm success or diagnose issues.

---

## Best Practices to Share

- **Chain small DTs** instead of one large complex table
- **Use `TARGET_LAG = DOWNSTREAM`** for all intermediate tables in pipelines
- **Use time-based lag only** for final/leaf tables
- **Test with `REFRESH_MODE = AUTO`** first, then switch to explicit mode for production
- **Use explicit column names** instead of `SELECT *` to avoid schema change failures
- **Enable change tracking** on base tables before creating DT

---

## Stopping Points Summary

1. ✋ After gathering requirements
2. ✋ Before enabling change tracking on base tables
3. ✋ After determining configuration (before CREATE)
4. ✋ After generating CREATE statement (before execution)
5. ✋ After execution (verify success)

**Resume rule:** Only proceed after explicit user approval.

---

## Output

- Created dynamic table with appropriate configuration
- Verified initial refresh status
