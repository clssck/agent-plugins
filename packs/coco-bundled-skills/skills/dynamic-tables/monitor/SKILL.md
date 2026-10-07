---
name: dynamic-tables-monitor
description: "Monitor health, status, and refresh performance of Snowflake dynamic tables. Use when: checking DT status, viewing refresh history, assessing target lag compliance, DT health check. Triggers: check status, refresh history, is it healthy, target lag, DT state, DT health, trend, drift, week over week, before after tuning."
parent_skill: dynamic-tables
---

# Monitor Dynamic Tables

Workflow for checking health, status, and performance of dynamic tables. This is a READ-ONLY workflow.

## When to Load

Main skill routes here when user wants to:
- Check dynamic table status or health
- View refresh history
- Understand pipeline dependencies
- Assess target lag compliance

---

## Workflow

⛔ **MANDATORY:** Before any `INFORMATION_SCHEMA` query, set database context:
```sql
USE DATABASE <database_name>;
```
Without this, `INFORMATION_SCHEMA` functions will fail with "Invalid identifier" errors.

### Step 1: Get Current State

**Goal:** Get current health status of dynamic table(s)

**Load** [references/dt-state.md](../references/dt-state.md) — `SHOW DYNAMIC TABLES` vs `INFORMATION_SCHEMA.DYNAMIC_TABLES()`, which columns each provides, and `scheduling_state` format differences.

**Actions:**

1. **Get configuration** via SHOW (for all DTs in a schema, or a specific DT):
   ```sql
   SHOW DYNAMIC TABLES IN SCHEMA <database>.<schema>;
   ```
   ```sql
   SHOW DYNAMIC TABLES LIKE '<dynamic_table_name>' IN SCHEMA <database>.<schema>;
   ```

   | Metric | Healthy | Concern |
   |--------|---------|---------|
   | `scheduling_state` | `ACTIVE` | `SUSPENDED` |
   | `refresh_mode` | `INCREMENTAL` | `FULL` = may need optimization |

2. **Get lag metrics** via INFORMATION_SCHEMA (for all DTs, or a specific DT):
   ```sql
   SELECT 
     name, 
     scheduling_state,
     last_completed_refresh_state,
     target_lag_sec,
     maximum_lag_sec,
     time_within_target_lag_ratio
   FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
   ORDER BY name;
   ```
   ```sql
   SELECT 
     name,
     scheduling_state,
     last_completed_refresh_state,
     target_lag_sec,
     maximum_lag_sec,
     time_within_target_lag_ratio
   FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES(name=>'<database>.<schema>.<dynamic_table_name>'));
   ```

   | Metric | Healthy | Concern |
   |--------|---------|---------|
   | `last_completed_refresh_state` | `SUCCEEDED` | `FAILED`, `UPSTREAM_FAILED` |
   | `time_within_target_lag_ratio` | > 0.95 | < 0.90 = not meeting freshness |

   **Written reports:** When you summarize for a file or runbook, **use the same literals Snowflake returns** for `last_completed_refresh_state` (for example write **`UPSTREAM_FAILED`** or **upstream failure** when that is the state — not only generic words like "error" or "blocked") and for scheduling (write **suspended** / **`SUSPENDED`** when `SHOW DYNAMIC TABLES` shows suspension — not only "inactive" or "stopped").

---

### Step 2: Check Refresh History

**Goal:** Understand recent refresh behavior

**Actions:**

1. **Get recent refresh details (last 20):** run the **Recent refresh details with statistics** query in [references/dt-refresh-analysis.md — Example Queries](../references/dt-refresh-analysis.md#example-queries) with `NAME_PREFIX => '<database>.<schema>'` (or `NAME => '<database>.<schema>.<dt_name>'` for a single DT). Returns per-refresh state, `refresh_action`, `refresh_trigger`, `query_id`, and the unpacked `statistics` JSON fields (compilation/execution times, row and partition counts).

2. **Check for errors only** (last 7 days):
   ```sql
   SELECT 
     name, 
     refresh_start_time,
     state, 
     state_code,
     state_message,
     refresh_action
   FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
     NAME_PREFIX => '<database>.<schema>',
     ERROR_ONLY => TRUE
   ))
   WHERE refresh_start_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
   ORDER BY refresh_start_time DESC
   LIMIT 20;
   ```

3. **Calculate refresh statistics** (last 7 days): run the canonical **Refresh statistics** query from [references/dt-refresh-analysis.md — Example Queries](../references/dt-refresh-analysis.md#example-queries) with `NAME => '<database>.<schema>.<dt_name>'`.

   **Interpreting refresh categories:** See [references/dt-refresh-analysis.md](../references/dt-refresh-analysis.md#interpreting-refresh-categories) for how to categorize CREATION/REINITIALIZE vs steady-state refreshes. Exclude both from steady-state performance trends.

   **Comparing across REINITIALIZE boundaries:** See [references/dt-refresh-analysis.md](../references/dt-refresh-analysis.md#comparing-performance-across-reinitialize-boundaries) for methodology. Always report pre-reinit and post-reinit steady-state metrics separately.

---

### Step 3: View Pipeline Dependencies

**Goal:** Understand DAG structure and upstream/downstream relationships

**Load** [references/dt-graph.md](../references/dt-graph.md) — `DYNAMIC_TABLE_GRAPH_HISTORY()` columns, parameters, and schema evolution tracking.

**Actions:**

1. **Get dependency graph**:
   ```sql
   SELECT 
     name,
     inputs,
     scheduling_state,
     target_lag_type,
     target_lag_sec
   FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY())
   WHERE name = '<dynamic_table_name>'
      OR ARRAY_CONTAINS('<dynamic_table_name>'::VARIANT, inputs);
   ```

2. **Interpret dependencies**:
   - `inputs` array shows upstream tables
   - Tables with `target_lag_type = 'DOWNSTREAM'` refresh when downstream needs them
   - Look for upstream tables with issues that could affect downstream

---

### Step 4: Analyze Refresh Query Performance

**Goal:** Understand compute usage and identify potential bottlenecks

**Actions:**

1. **Get refresh query details** (using query_id from refresh history):
   
   **Load** [references/dt-refresh-analysis.md](../references/dt-refresh-analysis.md) — covers which data source to use, when, and what privileges each requires.
   
   > **Short-circuit:** If the user already provided a `query_id`, skip the `DYNAMIC_TABLE_REFRESH_HISTORY` lookup in Step 2 and use the provided `query_id` directly.
   
   Use the data sources in this order:
   1. **`GET_QUERY_OPERATOR_STATS`** with the `query_id` — provides operator-level breakdowns for identifying bottlenecks. Verify warehouse access first (see reference doc).
   2. **`QUERY_HISTORY_BY_WAREHOUSE`** — if you need query-level I/O metrics (bytes scanned, partition pruning, spill). Use the warehouse name from Step 2 or `SHOW DYNAMIC TABLES`.
   3. **`SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`** — if the query is outside the 7-day INFORMATION_SCHEMA retention or warehouse privileges are unavailable. Verify access before committing to this fallback (see reference doc).

---

### Step 5: Historical comparison *(optional)*

**Goal:** Detect drift or regressions by comparing the Step 1–2 snapshot (lag, scheduling state, refresh aggregates) against a longer refresh-history window.

**Load** [references/dt-refresh-analysis.md](../references/dt-refresh-analysis.md) — [Interpreting refresh categories](../references/dt-refresh-analysis.md#interpreting-refresh-categories) (steady-state vs `CREATION` / `REINITIALIZE`) and [Account-level refresh history (optional)](../references/dt-refresh-analysis.md#account-level-refresh-history-optional) (`SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY`, privileges, latency).

**Prerequisite:** Role can read `SNOWFLAKE.ACCOUNT_USAGE` (see [Verify Warehouse Access](../references/dt-refresh-analysis.md#verify-warehouse-access-before-deep-diving)). If that probe or the account-level rollup query fails, skip this step and report from Steps 1–2 only.

**Actions:**

1. **Daily steady-state rollup:** use the SQL under [references/dt-refresh-analysis.md — Example: daily steady-state rollup](../references/dt-refresh-analysis.md#account-level-daily-rollup-example) (same steady-state filters as Step 2).

2. **Compare to Step 2:** highlight where the longer window disagrees with the last-7-day picture (avg duration trend, spikes in `full_count` or `failed_count`).

3. **Further patterns** (e.g. `LAG()`, BEFORE/AFTER cutoffs): keep the same steady-state rules from the reference doc; use the Snowflake view documentation linked under [Account-level refresh history (optional)](../references/dt-refresh-analysis.md#account-level-refresh-history-optional) for additional predicates and columns.

---

## Present Health Report

Summarize findings for the user (chat) or any file path they gave you.

### Template router

Pick the template that matches the **scope** of the request:

| Scope | Load | When |
|-------|------|------|
| Single dynamic table | [references/health-report-single-dt.md](../references/health-report-single-dt.md) | User named a specific DT, or scope resolves to one object. |
| Schema-wide / multi-pipeline | [references/health-report-pipeline.md](../references/health-report-pipeline.md) | Request covers every DT in a schema, or more than one pipeline (e.g. "audit our pipelines", "all DTs in MYDB.MYSCHEMA"). |

Each template has placeholders to fill from Steps 1–2 (and Step 5 if it ran). Do not invent data — skip sections you could not fetch and note any skipped probe in Recommendations.

### Output destination

Render in chat by default. Only write to a file (e.g. `pipeline_health_report.md`) when the user names a path or the calling environment exposes filesystem write tools — Snowsight worksheets do not, so default to chat there.

### Snowflake-accurate wording

Always echo **`UPSTREAM_FAILED`** or **upstream failure** when that refresh outcome appears; echo **suspended** / **`SUSPENDED`** when SHOW reports it; echo **`FULL`** refresh mode when `refresh_mode` is `FULL` (performance or cost signal). Match `INFORMATION_SCHEMA` / `SHOW` vocabulary so automated readers align with query results.

---

## Stopping Points

This is a READ-ONLY workflow. No mandatory stopping points.
- If issues found, offer to route to TROUBLESHOOT workflow
- If optimization opportunities found, offer to route to OPTIMIZE workflow

---

## Output

- Health report with key metrics
- Optional account-level trend from Step 5 (when `ACCOUNT_USAGE` is available)
- Recommendations for next steps (if issues found)
