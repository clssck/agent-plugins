---
name: dynamic-tables-optimize
description: "Optimize Snowflake dynamic table performance and cost"
parent_skill: dynamic-tables
---

# Optimize Dynamic Tables

Workflow for improving dynamic table performance, converting to incremental refresh, decomposing large DTs, and applying immutability constraints.

## When to Load

Main skill routes here when user wants to:
- Speed up slow refreshes
- Convert full refresh to incremental
- Break large DT into smaller ones
- Reduce compute costs
- Apply immutability constraints

---

## Data sources for analysis

**Load** [references/dt-refresh-analysis.md](../references/dt-refresh-analysis.md) before diagnosing slow or costly refreshes: refresh history, operator stats, warehouse and `ACCOUNT_USAGE` fallbacks, privileges, and optional account-level refresh history live there.

---

## Workflow

### Step 1: Analyze Current Configuration

**Goal:** Understand current DT setup

**Actions:**

1. **Get current configuration**:
   
   ```sql
   SHOW DYNAMIC TABLES LIKE '<dt_name>' IN SCHEMA <database>.<schema>;
   -- Key columns: refresh_mode, refresh_mode_reason, warehouse, scheduling_state, target_lag, rows, bytes
   ```
   
   > **Note:** `SHOW DYNAMIC TABLES` provides all config and state columns needed for optimization. Use `INFORMATION_SCHEMA.DYNAMIC_TABLES()` only when you need lag metrics (`mean_lag_sec`, `time_within_target_lag_ratio`), which are primarily useful for monitoring.

2. **Get DT definition**:
   ```sql
   SELECT GET_DDL('DYNAMIC_TABLE', '<fully_qualified_name>');
   ```

3. **Check current refresh statistics** (last 7 days): run the canonical **Refresh statistics** query in [references/dt-refresh-analysis.md — Example Queries](../references/dt-refresh-analysis.md#example-queries) with `NAME => '<database>.<schema>.<dt_name>'`. Record `avg_duration_sec`, `p95_duration_sec`, `max_duration_sec`, `avg_init_duration_sec`, and the action counts (`incremental_count`, `full_count`, `reinitialize_count`, `no_data_count`) as the baseline for Step 5 verification. For how to interpret the steady-state filter and `REINITIALIZE` / `CREATION` exclusions, see [Interpreting Refresh Categories](../references/dt-refresh-analysis.md#interpreting-refresh-categories).

**⚠️ MANDATORY STOPPING POINT**: Present current configuration analysis.

---

### Step 2: Analyze Query Performance

**Goal:** Identify expensive operations in refresh query

**Actions:**

1. **Get recent refresh query_id and statistics**:

   > **Short-circuit:** If the user already provided a `query_id`, skip this query and go directly to step 2. Only run this if you need the `query_id` or the DT-specific `statistics` metrics (rows inserted/deleted, partitions, compilation time).

   Run the **Example query extracting statistics** from [references/dt-refresh-analysis.md — `statistics` JSON Fields](../references/dt-refresh-analysis.md#statistics-json-fields) with `name => '<database>.<schema>.<dt_name>'`.

2. **Analyze query operators** (requires MONITOR or OPERATE privilege on the warehouse):
   
   > ⚠️ **Privilege note:** `GET_QUERY_OPERATOR_STATS()` requires MONITOR or OPERATE on the warehouse (or MONITOR/MANAGE WAREHOUSES at the account level). USAGE alone is insufficient. If this query fails with "Insufficient privileges", see the fallback options below.
   
   The function returns JSON columns — `OPERATOR_STATISTICS` contains row counts and I/O, `EXECUTION_TIME_BREAKDOWN` contains time percentages:
   ```sql
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

   **If `GET_QUERY_OPERATOR_STATS` fails with a privilege error**, walk the user through the options in [references/dt-refresh-analysis.md — Verify Warehouse Access](../references/dt-refresh-analysis.md#verify-warehouse-access-before-deep-diving) (warehouse **MONITOR** grant, **`ACCOUNT_USAGE.QUERY_HISTORY` probe and fallback** for a known `query_id`, or skip operator analysis and use refresh-history statistics only).

3. **Identify bottlenecks**:
   - If operator stats available: look for operators taking >20% of total time
   - Check for expensive JOINs, aggregations, or table scans
   - Note operators that could be split into intermediate DTs
   - If using ACCOUNT_USAGE fallback: focus on partition scan ratio (high % = poor pruning), spill metrics (indicates insufficient memory/warehouse size), and compilation vs execution time split

4. **Check warehouse utilization** (recent `DYNAMIC_TABLE_REFRESH` rows in `ACCOUNT_USAGE.QUERY_HISTORY` when you need several `query_id` samples without a known id): same **ACCOUNT_USAGE fallback** path and filters as [references/dt-refresh-analysis.md — Verify Warehouse Access](../references/dt-refresh-analysis.md#verify-warehouse-access-before-deep-diving) (see the sentence under option 2 about `query_type` / `query_text`).

**⚠️ MANDATORY STOPPING POINT**: Present query performance analysis.

---

### Step 3: Determine Optimization Strategy

**Goal:** Choose the best optimization approach

Based on analysis, determine which optimization(s) to apply:

| Issue | Optimization | Go To |
|-------|-------------|-------|
| Full refresh, query could be incremental | Convert to Incremental | Step 5A |
| Query too complex for single DT | Decompose DT | Step 5B |
| Historical data being reprocessed | Add Immutability Constraints | Step 5C |
| Warehouse too small | Increase Warehouse Size | Step 5D |
| Multiple optimizations needed | Apply in order: 5B → 5C → 5A → 5D |

**⚠️ MANDATORY STOPPING POINT**: Present optimization strategy for approval.

---

### Step 4A: Convert to Incremental Refresh

**Goal:** Restructure query to support incremental refresh

**Actions:**

1. **Load** [references/incremental-operators.md](../references/incremental-operators.md)

2. **Identify unsupported constructs** in current query:
   - Outer join with non-equality predicate (e.g., `ON a.id > b.id`) → Restructure or accept FULL
   - EXCEPT/INTERSECT → Rewrite with LEFT ANTI JOIN
   - Complex window functions → Consider materializing in intermediate DT

3. **Generate modified query** with supported constructs

4. **Generate new CREATE statement**:
   ```sql
   CREATE OR REPLACE DYNAMIC TABLE <dt_name>
     TARGET_LAG = '<same_lag>'
     WAREHOUSE = <same_warehouse>
     REFRESH_MODE = ADAPTIVE
     AS
       <modified_query>;
   ```

**⚠️ MANDATORY STOPPING POINT**: Present modified query before executing.

---

### Step 4B: Decompose Dynamic Table

**Goal:** Break large DT into smaller, more efficient DTs

**Load** [references/dt-decomposition.md](../references/dt-decomposition.md) for detailed guidance.

**Actions:**

1. **Identify decomposition points** from query analysis:
   - Expensive JOINs → Materialize as intermediate DT
   - Multi-stage aggregations → Split into stages
   - Complex transformations → Break into steps

2. **Design intermediate DT pipeline**:
   ```
   Original: SourceA + SourceB + SourceC → Complex Query → FinalDT
   
   Decomposed:
   SourceA → IntermediateDT_1 (expensive join)
                     ↓
   SourceB →────────┘
                     ↓
   IntermediateDT_1 + SourceC → FinalDT (simpler query)
   ```

3. **For each intermediate DT**:
   ```sql
   CREATE DYNAMIC TABLE <intermediate_dt_name>
     TARGET_LAG = DOWNSTREAM  -- Key: use DOWNSTREAM for intermediates
     WAREHOUSE = <warehouse>
     REFRESH_MODE = ADAPTIVE
     AS
       <portion_of_original_query>;
   ```

4. **Recreate final DT** referencing intermediates — **preserve the original DT's TARGET_LAG, WAREHOUSE, and INITIALIZE settings unless the user requests changes**:
   ```sql
   CREATE OR REPLACE DYNAMIC TABLE <final_dt_name>
     TARGET_LAG = '<original_lag>'   -- MUST match the original DT's lag exactly
     WAREHOUSE = <original_warehouse>
     REFRESH_MODE = ADAPTIVE
     AS
       SELECT ... FROM <intermediate_dt_name> ...;
   ```
   The final DT replaces the original, so it must preserve the same operational properties (lag, warehouse) and produce the same output schema.

**⚠️ MANDATORY STOPPING POINT**: Present decomposition plan before creating any DTs.

**⚠️ MANDATORY STOPPING POINT**: Before creating each intermediate DT.

**⚠️ MANDATORY STOPPING POINT**: Before recreating final DT.

---

### Step 4C: Add Immutability Constraints

**Goal:** Prevent reprocessing of historical data

**Actions:**

1. **Identify immutability boundary**:
   - Which rows are historical and shouldn't change?
   - What timestamp column defines "historical"?

2. **Add immutability constraint**:
   ```sql
   ALTER DYNAMIC TABLE <dt_name> 
   ADD FROZEN WHERE (timestamp_col < CURRENT_TIMESTAMP() - INTERVAL '1 day');
   ```

3. **For new DTs, include in CREATE**:
   ```sql
   CREATE DYNAMIC TABLE <dt_name>
     FROZEN WHERE (timestamp_col < CURRENT_TIMESTAMP() - INTERVAL '1 day')
     TARGET_LAG = '<lag>'
     WAREHOUSE = <warehouse>
     AS <query>;
   ```

**Constraints on FROZEN WHERE:** (formerly `IMMUTABLE WHERE`; legacy DTs may still show the old keyword)
- Cannot use subqueries
- Cannot use UDFs
- Can use timestamp functions (CURRENT_TIMESTAMP, etc.)

**⚠️ MANDATORY STOPPING POINT**: Present immutability constraint before applying.

---

### Step 4D: Increase Warehouse Size

**Goal:** Provide more compute for faster refreshes

**Actions:**

1. **Analyze current utilization**:
   - If query is CPU-bound, larger warehouse helps
   - If query is I/O-bound, may not help as much

2. **Recreate with larger warehouse**:
   ```sql
   CREATE OR REPLACE DYNAMIC TABLE <dt_name>
     TARGET_LAG = '<same_lag>'
     WAREHOUSE = <larger_warehouse>
     REFRESH_MODE = <same_mode>
     AS
       <same_query>;
   ```

**Alternative**: Use dedicated warehouse for DT refreshes to isolate costs.

**Alternative for initialization-only slowness**: If steady-state refreshes are fast but initial/reinitialization refreshes are slow, use `INITIALIZATION_WAREHOUSE` instead of permanently resizing:
```sql
ALTER DYNAMIC TABLE <dt_name> SET INITIALIZATION_WAREHOUSE = <larger_warehouse>;
```
This runs only initialization and reinitialization refreshes (`refresh_trigger = 'CREATION'` or `refresh_action = 'REINITIALIZE'`) on the larger warehouse, keeping the smaller warehouse for steady-state. Remove it after initialization is done:
```sql
ALTER DYNAMIC TABLE <dt_name> UNSET INITIALIZATION_WAREHOUSE;
```

**⚠️ MANDATORY STOPPING POINT**: Present warehouse change before executing.

---

### Step 5: Verify Optimization

**Goal:** Confirm optimization improved performance

**Actions:**

1. **Wait for several refresh cycles** (at least 3-5)

2. **Compare before/after metrics:** rerun the same canonical **Refresh statistics** query from [references/dt-refresh-analysis.md — Example Queries](../references/dt-refresh-analysis.md#example-queries), but narrow the window to the period after the change (for example `WHERE refresh_start_time > DATEADD('hour', -1, CURRENT_TIMESTAMP())`). Compare the same baseline columns recorded in Step 1.3.

3. **Check refresh mode**:
   ```sql
   SHOW DYNAMIC TABLES LIKE '<dt_name>' IN SCHEMA <database>.<schema>;
   -- Check refresh_mode and refresh_mode_reason columns
   ```

**⚠️ MANDATORY STOPPING POINT**: Present verification results.

**Tracking improvement after changes (optional):** Keep using [references/dt-refresh-analysis.md](../references/dt-refresh-analysis.md) — same data-source ordering, privilege checks, and refresh categorization; use [Account-level refresh history (optional)](../references/dt-refresh-analysis.md#account-level-refresh-history-optional) when you need account-scope refresh rows.

---

## DT Decomposition Workflow Summary

```
Analyze Query Profile
    ↓
Identify Expensive Operations (>20% of query time)
    ↓
Design Intermediate DTs
    ↓
    ├─→ Expensive JOIN → Create intermediate DT with join result
    ├─→ Heavy Aggregation → Create intermediate DT with pre-aggregation
    └─→ Complex Transform → Create intermediate DT with partial transform
    ↓
Create Intermediate DTs (TARGET_LAG = DOWNSTREAM)
    ↓
Recreate Final DT referencing intermediates
    ↓
Verify Performance Improvement
```

---

## Stopping Points Summary

1. ✋ After analyzing current configuration
2. ✋ After running query performance analysis
3. ✋ After proposing optimization strategy
4. ✋ Before creating ANY intermediate dynamic table
5. ✋ Before adding/modifying immutability constraints
6. ✋ Before changing refresh mode or recreating DT
7. ✋ Before changing warehouse
8. ✋ After verification - confirm improvement before closing

**Resume rule:** Only proceed after explicit user approval.
