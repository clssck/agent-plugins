---
name: task-to-dt
description: "Convert streams and tasks pipelines to dynamic tables. Use when: replacing stream+task patterns, simplifying ETL orchestration, migrating from imperative to declarative data pipelines. Triggers: convert tasks to dynamic tables, migrate tasks, replace tasks with DTs."
parent_skill: dynamic-tables
---

# Convert Streams & Tasks to Dynamic Tables

Expert guidance to migrate existing streams and tasks pipelines to use dynamic tables.

## When to Use

- Replacing imperative stream+task pipelines with declarative dynamic tables
- Simplifying orchestration of data transformation pipelines
- Reducing maintenance overhead of task scheduling and stream management

**Note:** If the task uses MERGE/INSERT with conditional logic based on change type (different handling for inserts vs deletes vs updates), or uses a stream-static join pattern, consider using a **custom incremental dynamic table** instead of a standard DT. See [custom-incrementalization/SKILL.md](../custom-incrementalization/SKILL.md).

## Key Concepts

| Streams & Tasks | Dynamic Tables |
|-----------------|----------------|
| Imperative: procedural code | Declarative: specify result query |
| Manual scheduling (CRON/interval) | Automatic refresh based on TARGET_LAG |
| MERGE/INSERT logic required | Automatic change propagation |
| Stream tracks changes explicitly | Change tracking automatic |
| Task graphs for dependencies | DAG inferred from table references |

## Workflow

### Step 1: Analyze Existing Pipeline

**Goal:** Understand current stream+task architecture

**Actions:**

1. **Identify** all tasks in the pipeline:
   ```sql
   SHOW TASKS IN SCHEMA <schema>;
   ```

2. **Find** root tasks (tasks with no predecessors):
   ```sql
   SELECT name FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
   WHERE "predecessors" = '[]';
   ```

3. **Document** the task graph structure for each root task:
   ```sql
   SELECT name, predecessors, schedule, warehouse, definition
   FROM TABLE(INFORMATION_SCHEMA.TASK_DEPENDENTS('<root_task>', TRUE));
   ```

4. **Extract** transformation logic from each task's SQL

**Output:** List of tasks, streams, their dependencies, and transformation SQL

### Step 2: Assess Migration Feasibility

**Goal:** Determine which tasks can convert to dynamic tables

#### 2a. Check for Blocking Issues

These issues **prevent** migration to dynamic tables:

| Blocker | How to Detect | Why It Blocks |
|---------|---------------|---------------|
| **Append-only streams** | For each stream referenced in task definitions: `DESCRIBE STREAM <stream_name>;` and check the `mode` property for `APPEND_ONLY` | DTs track all changes (insert/update/delete), not just inserts. Append-only semantics cannot be replicated. **However:** CI DTs with `CHANGES(INFORMATION => APPEND_ONLY)` can handle this — see [custom-incrementalization/SKILL.md](../custom-incrementalization/SKILL.md). |
| **Unsupported source objects** | For each stream in task definitions: `DESCRIBE STREAM <stream_name>;` and check `source_type` for `directory table` or `external table`. Also inspect task SQL for direct reads from materialized views. | DTs don't support directory tables, external tables, streams, or materialized views as sources |
| **Sub-minute latency requirements** | `SELECT name, schedule FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) WHERE schedule LIKE '%SECOND%' OR schedule LIKE '% 1 MINUTE%';` (after SHOW TASKS) | DT minimum TARGET_LAG is 1 minute |
| **DT → View → DT pattern** | See detailed check below in section 2a.1 | Not supported: "You can't create dynamic tables that read from views that query other dynamic tables" |
| **Stream with static dimension join** | Task SQL joins stream changes with a static lookup table where only stream side changes | ~~Hard blocker for standard DTs.~~ **Solved by CI DTs**: use `CHANGES()` on the stream side + regular JOIN on static side. Route to [custom-incrementalization/SKILL.md](../custom-incrementalization/SKILL.md). |
| **Multi-statement stored procedures** | Task calls a stored procedure with multi-statement transactions doing work beyond consuming the stream | CI DTs execute a single DML statement only. If the proc does more than MERGE/INSERT (e.g., conditional branching, DDL, API calls, multi-table writes), it cannot be expressed as a CI DT. |

#### 2a.1 Deep Check for DT → View → DT Pattern

**CRITICAL:** Views can query other views, which can query other views, etc. You MUST trace the full dependency chain to base tables to ensure no dynamic tables exist in the lineage.

**Procedure:**

1. **Identify all source objects** in task SQL (tables, views referenced in FROM/JOIN clauses)

2. **For each source object**, check its type:
   ```sql
   SHOW OBJECTS LIKE '<object_name>' IN SCHEMA <database>.<schema>;
   -- Check the 'kind' and 'is_dynamic' columns
   ```

3. **If the object is a VIEW**, get its definition and recurse:
   ```sql
   SELECT GET_DDL('VIEW', '<database>.<schema>.<view_name>');
   ```
   - Parse the DDL to find all referenced objects
   - Repeat steps 2-3 for each referenced object

4. **Continue until you reach**:
   - Base tables (`kind=TABLE`, `is_dynamic=N`) ✅
   - Dynamic tables (`is_dynamic=Y`) ❌ **BLOCKER**
   - External tables, materialized views ❌ **BLOCKER** (unsupported sources)
   - Objects you cannot access (note as ⚠️ **UNKNOWN - requires verification**)

**Warning signs to watch for:**
- Object or schema names containing "DT", "DYNAMIC", or similar hints
- References to schemas you don't have access to (cannot verify)
- Deep view hierarchies (3+ layers)

**Example dependency trace:**
```
PROD.MY_VIEW (VIEW)
  └── STAGING.INTERMEDIATE_VIEW (VIEW)
        └── RAW.BASE_TABLE (TABLE, is_dynamic=N) ✅

PROD.ANOTHER_VIEW (VIEW)
  └── ANALYTICS.METRICS_VIEW (VIEW)
        └── ANALYTICS.DAILY_METRICS (is_dynamic=Y) ❌ BLOCKER!
```

**If you cannot access an object to verify its type:**
- Flag it as ⚠️ UNKNOWN in your assessment
- Ask the user to verify with appropriate privileges:
  ```sql
  -- User should run with elevated privileges:
  SHOW OBJECTS LIKE '<object_name>' IN SCHEMA <database>.<schema>;
  ```
- Do NOT proceed with migration until all source lineage is verified

#### 2b. Check Query Compatibility

| Supported | Not Supported |
|-----------|---------------|
| SELECT, JOIN (inner/outer/cross), UNION ALL | Stored procedures |
| Aggregations, window functions | External functions |
| Deterministic UDFs | PIVOT, UNPIVOT, SAMPLE |
| CTEs, subqueries in FROM | Subqueries in WHERE (EXISTS, IN) |
| LATERAL FLATTEN | LATERAL JOIN (except with FLATTEN) |
| DISTINCT, GROUP BY | Sequences (SEQ1, SEQ2) |

#### 2c. Check Incremental Refresh Compatibility

If incremental refresh is desired:
- No VOLATILE UDFs
- No SQL UDFs with subqueries
- Outer joins must be equi-joins
- No UDTFs written in SQL
- UNION (without ALL) becomes UNION ALL + DISTINCT

#### 2d. Summary Checklist

Present findings:
```
Migration Feasibility for: <pipeline_name>

BLOCKING ISSUES:
[ ] Uses append-only streams: <yes/no>
[ ] Reads from external/directory tables: <yes/no>
[ ] Sub-minute scheduling required: <yes/no>
[ ] Would create DT→View→DT pattern: <yes/no/unknown>
    - Unverified objects (permission errors): <list any>
[ ] Uses stream static join pattern: <yes/no>

QUERY COMPATIBILITY:
[ ] Contains unsupported constructs: <list any>
[ ] Incremental refresh possible: <yes/no/partial>

RECOMMENDATION: <proceed / proceed with caveats / do not migrate / requires verification>
```

If a DT→View→DT pattern is found, present it to the user in graph form:
```
SOURCE LINEAGE (❌ BLOCKER FOUND):
<task_source_object> (VIEW)
  └── <intermediate_object> (VIEW)
        └── <base_object> (DYNAMIC TABLE) ❌
```

**⚠️ STOP:** Present feasibility assessment. If blocking issues exist, discuss alternatives with user (e.g., keep as tasks, hybrid approach).

### Step 3: Design Dynamic Table Graph

**Goal:** Map task graph to dynamic table dependencies

**Principles:**
- Each task → one dynamic table (typically)
- Task predecessors → dynamic table reads from predecessor DT
- Root task source table → base table for first DT
- Use TARGET_LAG = 'DOWNSTREAM' for intermediate tables
- Set time-based TARGET_LAG only on leaf tables
- Use incremental dynamic tables where possible, with the caveat that an incremental dynamic table cannot have a full refresh dynamic table as input

**Example mapping:**
```
TASK GRAPH                    DYNAMIC TABLE GRAPH
─────────────────            ─────────────────────
raw_table                    raw_table (base)
    │                             │
    ▼                             ▼
task_stage1 (stream1)  →     dt_stage1 (TARGET_LAG='DOWNSTREAM')
    │                             │
    ▼                             ▼
task_stage2 (stream2)  →     dt_stage2 (TARGET_LAG='DOWNSTREAM')
    │                             │
    ▼                             ▼
task_final              →     dt_final (TARGET_LAG='10 minutes')
```

**⚠️ STOP:** Present proposed dynamic table graph for approval.

### Step 4: Convert Task SQL to Dynamic Table Definitions

**Goal:** Transform imperative task SQL to declarative DT queries

**Pattern: MERGE from stream → Simple SELECT**

Before (Task with Stream):
```sql
CREATE STREAM my_stream ON TABLE source_table;

CREATE TASK my_task
  WAREHOUSE = mywh
  SCHEDULE = '5 minute'
  WHEN SYSTEM$STREAM_HAS_DATA('my_stream')
AS
  MERGE INTO target_table t
  USING (SELECT * FROM my_stream) s
  ON t.id = s.id
  WHEN MATCHED THEN UPDATE SET t.col = s.col
  WHEN NOT MATCHED THEN INSERT (id, col) VALUES (s.id, s.col);
```

After (Dynamic Table):
```sql
CREATE OR REPLACE DYNAMIC TABLE target_dt
  TARGET_LAG = '5 minutes'
  WAREHOUSE = mywh
AS
  SELECT id, col FROM source_table;
```

**Pattern: Multi-stage pipeline**

Before:
```sql
CREATE TASK stage1 AS INSERT INTO stage1_table SELECT transform1(col) FROM raw;
CREATE TASK stage2 AFTER stage1 AS INSERT INTO stage2_table SELECT transform2(col) FROM stage1_table;
```

After:
```sql
CREATE DYNAMIC TABLE dt_stage1 TARGET_LAG = 'DOWNSTREAM' WAREHOUSE = mywh
  AS SELECT transform1(col) FROM raw;

CREATE DYNAMIC TABLE dt_stage2 TARGET_LAG = '10 minutes' WAREHOUSE = mywh
  AS SELECT transform2(col) FROM dt_stage1;
```

**Output:** Draft CREATE DYNAMIC TABLE statements

### Step 5: Create Dynamic Tables

**Goal:** Deploy dynamic tables in dependency order

**Actions:**

1. **Create** tables from root to leaf (upstream to downstream):
   ```sql
   CREATE OR REPLACE DYNAMIC TABLE <name>
     TARGET_LAG = '<lag>'
     WAREHOUSE = <warehouse>
     REFRESH_MODE = AUTO
     INITIALIZE = ON_CREATE
   AS
     <transformed_query>;
   ```

2. **Verify** creation and initial refresh:
   ```sql
   SHOW DYNAMIC TABLES LIKE '<name>';
   SELECT * FROM <name> LIMIT 10;
   ```

3. **Check** refresh mode assigned:
   ```sql
   SHOW DYNAMIC TABLES LIKE '<name>';
   -- Check refresh_mode and refresh_mode_reason columns in output
   ```

### Step 6: Validate and Compare

**Goal:** Ensure dynamic tables produce equivalent results

**Actions:**

1. **Compare** row counts:
   ```sql
   SELECT 
     (SELECT COUNT(*) FROM old_target_table) AS task_count,
     (SELECT COUNT(*) FROM new_dynamic_table) AS dt_count;
   ```

2. **Compare** sample data:
   ```sql
   SELECT * FROM old_target_table EXCEPT SELECT * FROM new_dynamic_table;
   SELECT * FROM new_dynamic_table EXCEPT SELECT * FROM old_target_table;
   ```

3. **Monitor** refresh behavior:
   ```sql
   SELECT * FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
   WHERE name = '<NAME>'
   ORDER BY refresh_end_time DESC LIMIT 10;
   ```

**⚠️ STOP:** Present validation results. Ask user: **"Would you like to decommission the old task pipeline?"**

- If **yes** → Proceed to Step 7
- If **no** → Migration complete. Both pipelines can run in parallel if needed.

### Step 7: Decommission Old Pipeline (Optional)

**Goal:** Clean up streams and tasks after successful migration

**Prerequisites:** User has approved decommissioning after validation.

**Actions:**

1. **Suspend** tasks (don't drop yet):
   ```sql
   ALTER TASK <task_name> SUSPEND;
   ```

2. **After** monitoring period (recommended: 1-2 weeks), drop tasks and streams:
   ```sql
   DROP TASK IF EXISTS <task_name>;
   DROP STREAM IF EXISTS <stream_name>;
   ```

3. **Optionally** drop old target tables if replaced by DTs

## Stopping Points

- ✋ Step 2: After feasibility assessment (blocking issues? unsupported constructs?)
- ✋ Step 3: After graph design (approve DT structure)
- ✋ Step 6: After validation (ask if user wants to decommission old pipeline)

## Common Conversion Patterns

### Aggregation Task
```sql
-- Task
INSERT INTO daily_sales SELECT date, SUM(amount) FROM sales GROUP BY date;

-- Dynamic Table
CREATE DYNAMIC TABLE daily_sales_dt TARGET_LAG = '1 hour' WAREHOUSE = mywh
AS SELECT date, SUM(amount) FROM sales GROUP BY date;
```

### JSON Parsing Task
```sql
-- Task  
INSERT INTO parsed SELECT var:id::int, var:name::string FROM raw_json;

-- Dynamic Table
CREATE DYNAMIC TABLE parsed_dt TARGET_LAG = '5 minutes' WAREHOUSE = mywh
AS SELECT var:id::int AS id, var:name::string AS name FROM raw_json;
```

### Dimension Join Task
```sql
-- Task
MERGE INTO enriched USING (SELECT f.*, d.region FROM facts f JOIN dims d ON f.dim_id = d.id) ...

-- Dynamic Table (explicitly list columns - SELECT * not recommended for DTs)
CREATE DYNAMIC TABLE enriched_dt TARGET_LAG = '10 minutes' WAREHOUSE = mywh
AS SELECT f.id, f.amount, f.created_at, d.region 
   FROM facts f JOIN dims d ON f.dim_id = d.id;
```

### Deduplication Task

MERGE-based deduplication is common in task pipelines. Dynamic tables handle this declaratively using `QUALIFY` with window functions.

```sql
-- Task (MERGE to deduplicate by keeping latest per key)
MERGE INTO target t
USING (
  SELECT * FROM source_stream
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1
) s
ON t.id = s.id
WHEN MATCHED AND s.updated_at > t.updated_at THEN 
  UPDATE SET t.col = s.col, t.updated_at = s.updated_at
WHEN NOT MATCHED THEN 
  INSERT (id, col, updated_at) VALUES (s.id, s.col, s.updated_at);

-- Dynamic Table (declarative deduplication)
CREATE DYNAMIC TABLE target_dt TARGET_LAG = '5 minutes' WAREHOUSE = mywh
AS 
  SELECT id, col, updated_at
  FROM source_table
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) = 1;
```

**Alternative patterns for DT deduplication:**

```sql
-- Keep first occurrence
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY created_at ASC) = 1

-- Keep latest by version number
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY version DESC) = 1

-- Keep record with highest priority
QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY priority DESC, updated_at DESC) = 1

-- Aggregate to collapse duplicates (when you need combined values)
SELECT id, MAX(updated_at) AS updated_at, SUM(amount) AS total_amount
FROM source_table
GROUP BY id
```

## Workaround Patterns

For hybrid patterns combining dynamic tables with tasks (task-controlled refresh, post-refresh actions):

**Load** [references/advanced-patterns-with-tasks-and-dts.md](../references/advanced-patterns-with-tasks-and-dts.md)

## Output

- Dynamic table definitions replacing each task
- Validation queries confirming data equivalence
- Commands to decommission old pipeline

## Troubleshooting

| Issue | Solution |
|-------|----------|
| DT stuck in SUSPENDED | Check refresh errors: `SHOW DYNAMIC TABLES` |
| Incremental not used | Check `refresh_mode_reason`, may need query changes |
| Lag not met | Increase warehouse size or adjust TARGET_LAG |
| Creation fails | Verify change tracking on base tables |
