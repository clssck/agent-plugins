# Single Query Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide actionable recommendations for a single query. The primary path is **SQL-level optimization** using Snowflake Query Insights. Infrastructure recommendations are the **fallback** when no SQL-actionable insights exist or the issue is purely resource-based.

## Workflow

### Step 1: Fetch Query Insights

Using the query ID from Phase 1 summary, check for Query Insights (see `references/query_insights.md` for full details):

```sql
SELECT 
    qi.INSIGHT_TYPE_ID, qi.INSIGHT_TOPIC, qi.MESSAGE, qi.SUGGESTIONS,
    qh.QUERY_TEXT, qh.USER_NAME, qh.WAREHOUSE_NAME,
    qh.DATABASE_NAME, qh.SCHEMA_NAME,
    qh.START_TIME, qh.TOTAL_ELAPSED_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_INSIGHTS qi
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY qh ON qi.QUERY_ID = qh.QUERY_ID
WHERE qi.QUERY_ID = '<QUERY_ID>'
  AND qi.START_TIME >= DATEADD('day', -14, CURRENT_DATE())
  AND qh.START_TIME >= DATEADD('day', -14, CURRENT_DATE())
```

**Branch on results:**

| Condition | Next Step |
|-----------|-----------|
| SQL-actionable insights exist (Table Scan, Join, Aggregation, Union types) | → **Step 2: SQL Optimization** (primary path) |
| ONLY resource insights (REMOTE_SPILLAGE, QUEUED_OVERLOAD) | → **Step 3: Infrastructure Recommendations** |
| Mixed (SQL-actionable + resource insights) | → **Step 2** for SQL issues, then **Step 3** for resource issues. Check for co-located spillage — if spillage shares `logical_node_id` with a SQL insight, fix the SQL issue first (spillage may resolve). |
| No insights, query < 2 hours old | Insights may not be processed yet. Offer general suggestions from operator stats (see `references/sql_optimization_strategies.md` — General Suggestions section). |
| No insights, query > 14 days old | `GET_QUERY_OPERATOR_STATS` expired. → **Step 3: Infrastructure Recommendations** based on bottleneck from detection phase. |
| No insights, 2h-14d old | Query likely efficient. Ask user: "No Query Insights were generated — this typically means no significant performance issues were detected. Would you like infrastructure recommendations based on the execution metrics?" If yes → **Step 3**. |
| Only positive insights (FILTER_WITH_CLUSTERING_KEY, SEARCH_OPTIMIZATION_USED, etc.) | Present as informational: query is already well-optimized. Offer infrastructure recs if bottleneck was detected in Phase 2. |

---

### Step 2: SQL Optimization (Primary Path)

**Reference docs for this step:**
- `references/query_insights.md` — insight types, operator mapping, co-located spillage
- `references/sql_optimization_strategies.md` — fix strategies, column inference, view expansion
- `references/sql_optimization_output.md` — output formatting, tags, EXPLAIN validation

#### 2A. Map Insights to SQL Location

Use `GET_QUERY_OPERATOR_STATS` to tie each insight to a specific operator:

```sql
SELECT 
    OPERATOR_ID, OPERATOR_TYPE, OPERATOR_ATTRIBUTES, OPERATOR_STATISTICS
FROM TABLE(GET_QUERY_OPERATOR_STATS('<QUERY_ID>'))
ORDER BY OPERATOR_ID
```

Match `table` (for TableScan insights), `join_id` (for Join insights), or `logical_node_id` (for Aggregation/Resource insights) from the insight MESSAGE to the corresponding operator.

#### 2B. Detect View Expansion

If an insight references a table not present in the SQL text, a view is being expanded. Resolve using `OBJECT_DEPENDENCIES` or `GET_DDL` (see `references/sql_optimization_strategies.md` — View Expansion section).

#### 2C. Gather Table Metadata

For tables flagged by insights:

```sql
-- Clustering key and search optimization status
SHOW TABLES LIKE '<TABLE_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>

-- FK relationships (for join insights)
SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = '<SCHEMA>'
```

#### 2D. Infer Column and Value Suggestions

When an insight indicates a missing or ineffective filter, use the 9-source inference priority (see `references/sql_optimization_strategies.md` — Column and Value Inference section). Mark inferred values with `[INFERRED]` tag. Use `[ACTION REQUIRED]` for confidence < 80.

#### 2E. Generate Updated SQL

Apply fix strategies from `references/sql_optimization_strategies.md` based on each insight type. Add inline comments with change tags (`[C1]`, `[C2]`, etc.).

**Set session context** — before validating, ensure the correct database/schema is active. Check the original query's `DATABASE_NAME` and `SCHEMA_NAME` from QUERY_HISTORY (already fetched in Step 1) and run:
```sql
USE SCHEMA <DATABASE_NAME>.<SCHEMA_NAME>
```

**Validate syntax (no execution):**
```sql
EXPLAIN <updated_sql_query>
```

**IMPORTANT:** Snowflake's EXPLAIN only works with SELECT statements. If the original query is DML (INSERT, MERGE, CREATE TABLE AS, etc.), extract the SELECT portion for EXPLAIN validation. For example:
- `INSERT INTO t SELECT ...` → `EXPLAIN SELECT ...`
- `CREATE TABLE t AS SELECT ...` → `EXPLAIN SELECT ...`
- `MERGE INTO t USING (SELECT ...) ...` → `EXPLAIN SELECT ...` (validate the USING subquery)

If EXPLAIN fails, attempt auto-fix and retry (max 3 attempts). If still fails, present SQL with `[WARNING] MANUAL REVIEW REQUIRED`.

#### 2F. Present to User

Present output in **exactly this order** (see `references/sql_optimization_output.md` for edge cases: spillage, view expansion, positive insights, queuing):

**Part 1 — Disclaimer (always first):**

```
[IMPORTANT] DISCLAIMER
════════════════════════════════════════════════════════════════════
The suggestions below are POTENTIAL PERFORMANCE IMPROVEMENTS based on 
Snowflake Query Insights. Snowflake's optimizer already maximizes 
execution performance automatically.

These SQL modifications may produce DIFFERENT RESULTS than the original.
Please review each change and verify output before production use.

Performance gains will depend on your workload and environment. Results
may vary based on data size, query patterns, concurrency, hardware, and
configuration.
════════════════════════════════════════════════════════════════════
```

**Part 2 — Original query** (full SQL text, unmodified)

**Part 3 — Updated query** with summary block at top and inline comments at each change:

```sql
-- ============================================================
-- QUERY INSIGHT CHANGES SUMMARY
-- ============================================================
-- [WARNING] These changes may produce different results.
-- ============================================================
-- C1: [<INSIGHT_TYPE>] <Description> - <STATUS>
-- C2: [<INSIGHT_TYPE>] <Description> - <STATUS>
-- ============================================================
-- To modify: "C1 - <your change>" or "Accept all"
-- ============================================================

<updated SQL with inline [C<N>][QUERY_INSIGHT_*] comments at each change>
```

**Part 4 — Validation status:** `[VALIDATED] Syntax validated via EXPLAIN (no execution)`

**Part 5 — Suggested changes list:**
```
SUGGESTED CHANGES:
- C1: [<INSIGHT_TYPE>] <Description> - <STATUS>
- C2: [<INSIGHT_TYPE>] <Description> - <STATUS>
```

**Part 6 — User confirmation prompt:**
```
Would you like me to execute this updated query?

Reply:
- "Yes" or "Execute" to run the updated query
- "No" to skip execution
- "C<N> - <modification>" to adjust a specific change
- "Accept all" to accept all changes as-is
```

**⚠️ MANDATORY STOPPING POINT — Do NOT proceed until user responds.**

Pre-presentation checklist (verify ALL before showing output):
- [ ] Disclaimer is shown FIRST
- [ ] Original query is shown in full
- [ ] Updated query has summary block at top
- [ ] Every change has inline `[C<N>]` + `[QUERY_INSIGHT_*]` tags
- [ ] EXPLAIN validation status is shown
- [ ] Suggested changes are listed
- [ ] User confirmation prompt is shown
- [ ] You have NOT executed the updated SQL

**Never execute updated SQL without explicit user approval.**

---

#### 2G. Post-Execution Comparison

Triggered when user accepts the updated SQL (replies "Yes", "Execute", or "Accept all").

**1. Confirm and advise on warehouse:**

Before executing, inform the user:

```
The updated query will now be executed. Note:
- The original query ran on warehouse <WAREHOUSE_NAME> (size <WAREHOUSE_SIZE>).
- Your current session may be using a different warehouse.
- For a fair comparison, use the same warehouse and size.

Proceed with execution?
```

**⚠️ MANDATORY STOPPING POINT — Wait for user to confirm.**

**2. Execute the updated query:**

- If the original was DML (INSERT, MERGE, CTAS), ask user whether to run as SELECT-only (to compare results without side effects) or as the full DML statement.
- After execution, capture the query ID via `LAST_QUERY_ID()`.

**3. Collect comparison stats:**

For the **optimized query** (just executed, too recent for ACCOUNT_USAGE):
```sql
SELECT QUERY_ID,
    ROUND(TOTAL_ELAPSED_TIME / 1000.0, 2) AS total_elapsed_seconds,
    ROUND(COMPILATION_TIME / 1000.0, 2) AS compilation_seconds,
    ROUND(EXECUTION_TIME / 1000.0, 2) AS execution_seconds,
    ROWS_PRODUCED
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION())
WHERE QUERY_ID = '<OPTIMIZED_QUERY_ID>'
```

**Note:** `QUERY_HISTORY_BY_SESSION` has limited columns — see `references/data_sources.md`. Do NOT reference `PERCENTAGE_SCANNED_FROM_CACHE`, `PARTITIONS_SCANNED`, or spill columns from this function.

For the **original query** (already in ACCOUNT_USAGE from Step 1):
Use the `total_elapsed_seconds`, `execution_seconds`, `rows_produced` already fetched in the summary phase.

**4. Operator-level comparison:**

Run `GET_QUERY_OPERATOR_STATS` on the optimized query ID. Compare operators at the logical nodes targeted by the insights against the original query's operator stats (fetched in Step 2A).

Match operators by `OPERATOR_TYPE` + `OPERATOR_ATTRIBUTES` — the optimizer may assign different operator IDs to the optimized plan.

**5. Present comparison** (see `references/sql_optimization_output.md` — Post-Execution Comparison Format):

- Runtime comparison table (total elapsed, execution time, rows produced)
- Operator-level comparison for insight-targeted nodes
- Caveats: warehouse caching, queue wait differences, underlying data changes may make results not directly comparable
- Offer: "Would you like me to re-run the original query now for a side-by-side comparison under the same conditions?"

**⚠️ MANDATORY STOPPING POINT — Wait for user response.**

If user requests re-running the original:
- Execute the original query (SELECT-only if the original was DML)
- Repeat the comparison using fresh stats for both queries

---

### Step 3: Infrastructure Recommendations (Fallback)

Used when no SQL-actionable Query Insights exist, or for resource-only issues (spillage without SQL root cause, queuing).

Based on the bottleneck classification from `query/detection/SKILL.md`:

| Bottleneck | Recommendations |
|---|---|
| **Spilling** | Consider running the query on a larger warehouse. If remote spilling is present, this is critical — the warehouse is severely undersized for this query's memory needs. Reduce concurrent queries on the same warehouse, or schedule this query during off-peak hours. |
| **Poor Pruning** | Review the tables accessed by this query. Check if frequently filtered columns align with clustering keys. Use `query/detection/SKILL.md`'s pruning analysis to identify candidate columns. If operator-level analysis showed a filter not pushed to TableScan, see `references/pruning_troubleshooting.md` for common causes (function applied to clustered column, filter/key mismatch, multi-column key order). |
| **Local Disk Cache Miss** | If this query runs repeatedly on the same data, local disk cache should improve over time. Check if the warehouse auto-suspends frequently (losing local disk cache). Consider separating this workload from workloads that thrash the cache. |
| **Queue Contention (Overload)** | The query spent significant time waiting because all warehouse compute resources were in use. Consider upsizing the warehouse, enabling multi-cluster warehouses, or distributing workloads across dedicated warehouses. |
| **Queue Contention (Provisioning)** | The query waited for the warehouse to resume from suspended state. If this query runs on a schedule, consider keeping the warehouse warm with a minimum cluster count or adjusting auto-suspend timeout. |
| **Compilation Heavy** | Unusual — compilation time exceeding execution time may indicate very complex SQL. Consider simplifying the query or breaking it into CTEs/temp tables. |

Present format:

```
### Recommendations for Query <query_id>

**Primary Bottleneck:** <TYPE>

1. **<First recommendation>**
   - Why: <evidence from metrics>
   - How: <specific action>

2. **<Second recommendation>**
   - Why: <evidence>
   - How: <action>
```

**[IMPORTANT]** Infrastructure recommendations:
- **DO NOT suggest SQL modifications** — focus on infrastructure and configuration
- **DO explain trade-offs** — e.g., larger warehouse = higher credit cost
- **DO provide specific warehouse size guidance** when spilling is detected (e.g., "Current: MEDIUM, consider: LARGE or X-LARGE based on spill volume")

---

### Step 4: Offer Follow-Up

- "Want me to analyze other queries on this warehouse?"
- "Want me to check if this query pattern has consistent issues across all executions?"

**[STOP]** Wait for user follow-up.
