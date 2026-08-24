---
name: dynamic-tables
description: "**[REQUIRED]** Use for **ALL** Snowflake Dynamic Table operations: creating, optimizing, monitoring, troubleshooting, and pipeline diagnostics. This is the required entry point for any dynamic table related tasks (DT is an acronym for dynamic table). Triggers: dynamic table, data pipeline, incremental pipeline, DT pipeline, incremental refresh, target lag, UPSTREAM_FAILED, refresh failing, full refresh instead of incremental, DT health, create DT, debug DT, pipeline timeline, Gantt chart, why was DT skipped, trace pipeline, critical path, why was DT skipped, dbt to DT, convert dbt to dynamic table, dbt dynamic table, dbt materialized dynamic_table."
---

# Dynamic Tables

## Mandatory Rules

**Before writing AI function SQL, read `../sql-author/SKILL.md`.**

Expert guidance for Snowflake Dynamic Tables: creating pipelines, configuring refreshes, monitoring health, troubleshooting issues, and optimizing performance.

## When to Use

Use this skill when users ask about:
- Creating dynamic tables with appropriate refresh modes
- Setting up dynamic table pipelines with proper target lag configuration
- Monitoring dynamic table health and refresh history
- Troubleshooting refresh failures or performance issues
- Optimizing refresh modes and query patterns
- Breaking large dynamic tables into smaller, more efficient ones

## Dynamic Tables vs Streams+Tasks

**Dynamic Tables are the default choice for Snowflake data pipelines.** For multi-step transformations, chain multiple DTs together—each DT handles one transformation step, and Snowflake manages the dependency graph and refresh order automatically.

```
raw_table → dt_bronze → dt_silver → dt_gold
            (DOWNSTREAM)  (DOWNSTREAM)  (5 min lag)
```

**Only use Streams+Tasks when a specific blocker prevents DT usage:**

| Blocker | Why DTs Can't Handle It |
|---------|------------------------|
| Append-only stream semantics | DTs track all changes (insert/update/delete), can't isolate inserts only. **First check:** can we add FROZEN WHERE on the DT? Consult [optimize/SKILL.md](optimize/SKILL.md). **Or:** use a CI DT with `CHANGES(INFORMATION => APPEND_ONLY)` — see [custom-incrementalization/SKILL.md](custom-incrementalization/SKILL.md). |
| External/directory table sources | Not supported as DT sources |
| Sub-minute latency requirement | DT minimum TARGET_LAG is 1 minute |
| DT → View → DT dependency | Not supported (view cannot sit between two DTs) |
| Stream with static dimension join | ~~DTs recompute full join on any base table change.~~ **Solved by CI DTs**: use `CHANGES()` on the stream side + regular JOIN on static side. See [custom-incrementalization/SKILL.md](custom-incrementalization/SKILL.md). |
| Procedural logic (IF/ELSE, loops) | DTs are declarative SELECT statements only. **Note:** simple conditional MERGE (different actions per INSERT/UPDATE/DELETE) is now supported via CI DTs — see [custom-incrementalization/SKILL.md](custom-incrementalization/SKILL.md). Multi-statement transactions, IF/ELSE blocks, and loops remain blockers. |
| Side effects (API calls, notifications) | DTs cannot call external functions with side effects |
| Write to multiple targets from one source | One DT = one target table |

**Decision tree:**
```
Is there a blocker from the table above?
    │
    ├─ NO  → Use Dynamic Tables (chain multiple for complexity)
    │
    └─ YES → Use Streams+Tasks (or hybrid pattern)
```

For migrating existing Streams+Tasks pipelines to DTs, see [task-to-dt/SKILL.md](task-to-dt/SKILL.md).

## ⚠️ MANDATORY INITIALIZATION

Before any workflow, you MUST:

### Step 1: Load Core References

**Load** the following reference documents:

1. **Load**: [references/sql-syntax.md](references/sql-syntax.md) - SQL command syntax
2. **Load**: [references/monitoring-functions.md](references/monitoring-functions.md) - monitoring function router (database context rules + links to state, refresh analysis, and graph references)
3. **Load** (if writing AI function SQL): [../sql-author/SKILL.md](../sql-author/SKILL.md) - AI function naming rules

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until you have loaded these references.

### Step 2: Establish Session Context

**Goal:** Confirm which Snowflake account, region, user, and role this session is running under so subsequent queries land on the right objects.

Run a single SQL probe before any other DT work:

```sql
SELECT CURRENT_ACCOUNT() AS account,
       CURRENT_REGION()  AS region,
       CURRENT_USER()    AS username,
       CURRENT_ROLE()    AS active_role;
```

If `active_role` cannot see the dynamic tables the user is asking about, ask the user which role they expect to use and re-run with `USE ROLE <role>;`.

**⚠️ MANDATORY STOPPING POINT**: Do NOT proceed until session context is confirmed.

---

## Intent Detection

When a user makes a request, detect their intent and route to the appropriate sub-skill:

### CREATE Intent

**Trigger phrases**: "create dynamic table", "set up DT", "new dynamic table", "define pipeline", "build DT"

**Note**: For tables that may already exist, or when deploying idempotently, prefer the CREATE-OR-ALTER intent.

**→ Load**: [create/SKILL.md](create/SKILL.md)

### CREATE-OR-ALTER Intent

**Trigger phrases**: "create or alter", "update DT definition", "modify dynamic table", "change DT query", "add column to DT", "change refresh mode", "evolve schema", "update dynamic table", "idempotent deploy DT", "schema evolution", "propagate column", "pipeline schema change", "redeploy DT", "update pipeline DT", "change warehouse", "swap warehouse", "alter DT", "modify DT", "DT already exists", "change target lag", "update target lag", "change lag", "update lag", "change property", "update property", "set target lag", "remove frozen region", "remove frozen where", "drop frozen region", "remove immutability", "remove immutable where", "add frozen region", "add frozen where", "shrink frozen region", "update frozen where"

**→ Load**: [create-or-alter/SKILL.md](create-or-alter/SKILL.md)

### MONITOR Intent

**Trigger phrases**: "check status", "refresh history", "is it healthy", "target lag", "how is my DT", "DT state", "trend", "drift", "week over week", "month over month", "compare before and after", "baseline", "historical refresh performance"

**→ Load**: [monitor/SKILL.md](monitor/SKILL.md)

For **written** health reports (files, runbooks, “every DT in the schema”), use monitor’s **Present Health Report** guidance: cite Snowflake literals such as **`UPSTREAM_FAILED`**, **suspended** / **`SUSPENDED`**, and **`FULL`** refresh mode when those states appear.

### TROUBLESHOOT Intent

**Trigger phrases**: "failing refresh", "not refreshing", "suspended", "full refresh instead of incremental", "refresh_mode_reason", "why is it failing", "DT broken", "errors"

**→ Load**: [troubleshoot/SKILL.md](troubleshoot/SKILL.md)

### OPTIMIZE Intent

**Trigger phrases**: "slow refresh", "make incremental", "improve performance", "immutability", "break into smaller", "decompose", "speed up", "reduce cost"

**Recommendations check before optimizing (feature-gated).** When this intent fires for a **specific** dynamic table AND the file [`../dynamic-tables-apply-recommendations/SKILL.md`](../dynamic-tables-apply-recommendations/SKILL.md) exists, first check whether Snowflake has already emitted recommendations for that exact DT — run this read-only query before loading the optimize sub-skill:

```sql
SELECT rec.value:"code"::STRING AS code, rec.value:"info"::STRING AS info
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(NAME => '<DB>.<SCHEMA>.<DT>')) dt,
     LATERAL FLATTEN(INPUT => dt.recommendations:recommendations) rec;
```

- **If it returns one or more recommendations**, do **not** reroute silently — **ask the user first.** Tell them Snowflake has specific recommendations for this dynamic table (list the codes) and ask whether they'd like to apply those through the recommendations workflow instead of a general optimization pass. **Only if they agree**, load [`../dynamic-tables-apply-recommendations/SKILL.md`](../dynamic-tables-apply-recommendations/SKILL.md). If they decline, continue with general optimization below.
  - **⚠️ MANDATORY STOPPING POINT:** wait for the user's answer before rerouting.
- **If it returns no recommendations** (or no specific DT was named, or the recommendations skill file does not exist), proceed straight to general optimization — do not ask.

**→ Load**: [optimize/SKILL.md](optimize/SKILL.md)

### ALERTING Intent

**Trigger phrases**: "set up alerts", "alert on failure", "notify on refresh failure", "DT alerting", "event table alerts", "monitor failures", "email when DT fails"

**→ Load**: [dt-alerting/SKILL.md](dt-alerting/SKILL.md)

### PERMISSIONS Intent

**Trigger phrases**: "insufficient privileges", "permission denied", "privilege error", "DT permissions", "ownership transfer", "can't refresh", "access denied", "masking policy error"

**→ Load**: [permissions/SKILL.md](permissions/SKILL.md)

### TASK-TO-DT Intent

**Trigger phrases**: "convert tasks", "migrate from tasks", "replace stream and task", "task to DT", "streams and tasks to dynamic table", "modernize pipeline"

**Disambiguation:** If the user's pipeline uses MERGE with conditional logic by change type (different handling for inserts vs deletes), or uses a stream-static join pattern, route to CUSTOM-INCREMENTALIZATION instead.

**→ Load**: [task-to-dt/SKILL.md](task-to-dt/SKILL.md)

### CUSTOM-INCREMENTALIZATION Intent

**Trigger phrases**: "custom incrementalization", "CI DT", "REFRESH USING", "MERGE DT", "INSERT INTO SELF", "stream-static join", "append-only log DT", "audit trail DT", "shape of changes", "imperative DT refresh", "different logic for inserts and deletes", "accumulate history in DT", "schema evolution without reinit", "DT only inserts from base table", "DT has only inserts"

**→ Load**: [custom-incrementalization/SKILL.md](custom-incrementalization/SKILL.md)

**Note:** Route here when user needs imperative DML logic in a dynamic table, or when a standard DT can't express their pattern (stream-static joins, conditional INSERT/UPDATE/DELETE handling, append-only accumulation). For general streams+tasks migration where the logic CAN be expressed as a SELECT, route to TASK-TO-DT instead.

### DBT-TO-DT Intent

**Trigger phrases**: "convert dbt to dynamic table", "dbt to DT", "migrate dbt models to DT", "add DT support to dbt", "dbt materialized dynamic_table", "replace dbt table with dynamic table", "dbt dynamic table conversion", "convert dbt pipeline to DT", "upgrade to incremental", "make incremental", "which models can be incremental", "FULL to INC", "upgrade FULL DTs", "check which DTs can be incremental", "migrate to dynamic tables", "migration to DT", "migrate my pipeline", "move to dynamic tables", "migrate models"

**→ Load**: [dbt-to-dt/SKILL.md](dbt-to-dt/SKILL.md)

### PIPELINE-DIAGNOSTICS Intent

**Trigger phrases**: "pipeline timeline", "Gantt chart", "why was DT skipped", "UPSTREAM_FAILED", "trace pipeline", "critical path", "execution timeline", "pipeline execution", "what happened in pipeline", "pipeline visualization", "what was affected by failure", "slowest DT", "pipeline bottleneck", "pipeline trace"

**→ Load**: [pipeline-diagnostics/SKILL.md](pipeline-diagnostics/SKILL.md)

**Note:** This skill handles both pipeline-wide visualization and upstream failure diagnosis using OTel traces. For non-upstream DT issues (e.g., "my DT refresh is failing", "why is it doing full refresh"), route to TROUBLESHOOT instead.

---

## Workflow Decision Tree

```
Start Session
    ↓
MANDATORY: Load reference documents (sql-syntax.md, monitoring-functions.md router)
    ↓
MANDATORY: Confirm session context (CURRENT_ACCOUNT/REGION/USER/ROLE)
    ↓
Detect User Intent
    ↓
    ├─→ CREATE → Load create/SKILL.md
    │   (Triggers: "create dynamic table", "new DT", "set up pipeline")
    │
    ├─→ CREATE-OR-ALTER → Load create-or-alter/SKILL.md
    │   (Triggers: "create or alter", "modify DT", "change query", "add column",
    │    "change refresh mode", "schema evolution", "idempotent deploy", "alter DT",
    │    "change target lag", "change lag", "change warehouse", "change property")
    │
    ├─→ MONITOR → Load monitor/SKILL.md
    │   (Triggers: "check status", "is it healthy", "refresh history", "trend", "drift", "week over week")
    │
    ├─→ TROUBLESHOOT → Load troubleshoot/SKILL.md
    │   (Triggers: "failing", "not refreshing", "suspended")
    │
    ├─→ OPTIMIZE → if recommendations skill is shipped AND recs exist for the named DT,
    │   │          ASK the user; on yes → ../dynamic-tables-apply-recommendations/SKILL.md
    │   └─→ otherwise Load optimize/SKILL.md
    │   (Triggers: "slow", "improve", "decompose", "make incremental")
    │
    ├─→ ALERTING → Load dt-alerting/SKILL.md
    │   (Triggers: "set up alerts", "notify on failure", "event table alerts")
    │
    ├─→ PERMISSIONS → Load permissions/SKILL.md
    │   (Triggers: "insufficient privileges", "permission denied", "ownership")
    │
    ├─→ TASK-TO-DT → Load task-to-dt/SKILL.md
    │   (Triggers: "convert tasks", "migrate tasks", "replace stream and task")
    │
    ├─→ CUSTOM-INCREMENTALIZATION → Load custom-incrementalization/SKILL.md
    │   (Triggers: "CI DT", "REFRESH USING", "stream-static join",
    │    "shape of changes", "append-only log", "MERGE INTO SELF")
    │
    ├─→ DBT-TO-DT → Load dbt-to-dt/SKILL.md
    │   (Triggers: "convert dbt to DT", "dbt dynamic table", "dbt to DT")
    │
    └─→ PIPELINE-DIAGNOSTICS → Load pipeline-diagnostics/SKILL.md
        (Triggers: "pipeline timeline", "Gantt chart", "UPSTREAM_FAILED",
         "why was DT skipped", "trace pipeline", "critical path")
```

---

## Sub-Skills

| Sub-Skill | Purpose | When to Load |
|-----------|---------|--------------|
| [create/SKILL.md](create/SKILL.md) | Create new dynamic tables | CREATE intent |
| [create-or-alter/SKILL.md](create-or-alter/SKILL.md) | Create or modify DTs idempotently; schema evolution; property changes | CREATE-OR-ALTER intent |
| [monitor/SKILL.md](monitor/SKILL.md) | Health checks and status monitoring | MONITOR intent |
| [troubleshoot/SKILL.md](troubleshoot/SKILL.md) | Diagnose and fix issues | TROUBLESHOOT intent |
| [optimize/SKILL.md](optimize/SKILL.md) | Performance improvements | OPTIMIZE intent |
| [dt-alerting/SKILL.md](dt-alerting/SKILL.md) | Set up alerts for refresh failures | ALERTING intent |
| [permissions/SKILL.md](permissions/SKILL.md) | Troubleshoot privilege/permission issues | PERMISSIONS intent |
| [task-to-dt/SKILL.md](task-to-dt/SKILL.md) | Convert streams+tasks pipelines to DTs | TASK-TO-DT intent |
| [custom-incrementalization/SKILL.md](custom-incrementalization/SKILL.md) | CI DTs: stream-static joins, shape-of-changes, append-only logs, stateful MERGE | CUSTOM-INCREMENTALIZATION intent |
| [dbt-to-dt/SKILL.md](dbt-to-dt/SKILL.md) | Convert dbt `table` models to Dynamic Tables | DBT-TO-DT intent |
| [pipeline-diagnostics/SKILL.md](pipeline-diagnostics/SKILL.md) | UPSTREAM_FAILED diagnosis, pipeline timeline, Gantt charts, root cause analysis via OTel traces | PIPELINE-DIAGNOSTICS intent |

> **Sibling skill (feature-gated):** [`../dynamic-tables-apply-recommendations/SKILL.md`](../dynamic-tables-apply-recommendations/SKILL.md) applies Snowflake-emitted recommendations to a specific DT. It is shipped separately — route to it only when the file exists. From the **OPTIMIZE** intent, reroute there only when recommendations actually exist for the named DT **and the user agrees** (see the OPTIMIZE intent).

---

## Quick Diagnostic Queries

For immediate assessment before routing:

```sql
-- Quick health check for all DTs in schema
SHOW DYNAMIC TABLES IN SCHEMA <database>.<schema>;
-- Check scheduling_state, refresh_mode, refresh_mode_reason columns

-- Check for any errors
SELECT name, state, state_message, refresh_action
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME_PREFIX => '<database>.<schema>', ERROR_ONLY => TRUE
))
ORDER BY refresh_start_time DESC
LIMIT 5;
```

---

## Important Constraints

### 1. Incremental DTs cannot depend on Full refresh DTs

Dynamic tables in incremental mode cannot depend on full refresh mode dynamic tables.

```sql
-- ❌ BREAKS: dt_final is INCREMENTAL but depends on dt_upstream which is FULL
CREATE DYNAMIC TABLE dt_upstream
  TARGET_LAG = DOWNSTREAM
  REFRESH_MODE = FULL  -- This DT uses FULL refresh
  AS SELECT * FROM source_table;

CREATE DYNAMIC TABLE dt_final
  TARGET_LAG = '5 minutes'
  REFRESH_MODE = INCREMENTAL  -- ERROR: Cannot be INCREMENTAL if upstream is FULL
  AS SELECT * FROM dt_upstream;
```

### 2. Target lag cannot be shorter than upstream's lag

```sql
-- ❌ BREAKS: dt_final has 1 minute lag but dt_upstream has 10 minutes
CREATE DYNAMIC TABLE dt_upstream
  TARGET_LAG = '10 minutes'  -- 10 minute lag
  AS SELECT * FROM source_table;

CREATE DYNAMIC TABLE dt_final
  TARGET_LAG = '1 minute'  -- ERROR: Cannot be fresher than upstream (10 min)
  AS SELECT * FROM dt_upstream;
```

### 3. Change tracking must remain enabled on base objects

```sql
-- ❌ BREAKS: Disabling change tracking after DT creation
CREATE DYNAMIC TABLE my_dt AS SELECT * FROM base_table;

-- Later...
ALTER TABLE base_table SET CHANGE_TRACKING = FALSE;  -- ERROR: DT refreshes will fail
```

### 4. FROZEN WHERE restrictions

> `FROZEN WHERE` was formerly `IMMUTABLE WHERE`; legacy DTs may still show the old keyword.

```sql
-- ❌ BREAKS: Subquery in FROZEN WHERE
CREATE DYNAMIC TABLE my_dt
  FROZEN WHERE (id IN (SELECT id FROM archived_ids))  -- ERROR: No subqueries
  AS SELECT * FROM source_table;

-- ❌ BREAKS: UDF in FROZEN WHERE
CREATE DYNAMIC TABLE my_dt
  FROZEN WHERE (my_custom_udf(status) = TRUE)  -- ERROR: No UDFs
  AS SELECT * FROM source_table;

-- ❌ BREAKS: Non-deterministic function (except timestamps)
CREATE DYNAMIC TABLE my_dt
  FROZEN WHERE (RANDOM() < 0.5)  -- ERROR: Non-deterministic
  AS SELECT * FROM source_table;

-- ✅ OK: Timestamp functions are allowed
CREATE DYNAMIC TABLE my_dt
  FROZEN WHERE (created_at < CURRENT_TIMESTAMP() - INTERVAL '7 days')
  AS SELECT * FROM source_table;
```

---

## Stopping Points Summary

All sub-skills follow this philosophy: **NO changes without explicit user approval.**

- **READ-ONLY queries**: Can run freely (diagnostics, monitoring)
- **ANY mutation**: Requires stopping point and user approval

See individual sub-skills for specific stopping points.

---

## Refresh and performance context

This skill does not persist local state between sessions. Use the `monitoring-functions.md` router (loaded in Step 1) to select the right reference for your scenario.
