---
name: workload-performance-analysis
description: "Snowflake SQL query execution analysis via ACCOUNT_USAGE views. Triggers: spilling, partition pruning, cache hit rates, clustering keys, search optimization (SOS) candidates, query acceleration (QAS) eligibility, predicate column analysis for clustering/SOS, per-warehouse spill/prune/cache metrics, slow SQL query diagnosis. Not for: cost/credits (cost-intelligence), access audit (data-governance), writing or debugging user SQL."
---

# Workload Performance Analysis

**You are using the workload-performance-analysis skill. Follow these instructions exactly.**

> **Warehouse-level questions**: If the user is asking about warehouse **types, conversion, or suitability** (e.g., "should I convert to adaptive?", "is adaptive good for spilling workloads?", "why didn't adaptive work for my warehouse?"), **defer to the warehouse skill**. This skill handles query-level performance diagnostics, not warehouse architecture decisions.

This is a **unified performance analysis skill** that handles all Snowflake performance questions through a single entry point. It detects the entity type and depth from the user's input, then routes to the appropriate sub-skill for each phase.

---

## Step 0: Source Detection

Before doing entity detection, **inspect the system-reminder content** of the current invocation for one of three specific markers. Source detection is **positive identification** — only the explicit presence of a marker counts. Do not infer source from any other signal.

| Signal in system-reminder | Source | Route to |
|---|---|---|
| `${queryHistoryListContext}` present | UI_QUERY_HISTORY | Load `ui-query-history/summary/SKILL.md` and follow it exactly. Do NOT continue with the entity-detection flow. |
| `${queryDetailsContext}` present | UI_QUERY_DETAILS | Load `ui-query-details/summary/SKILL.md` and follow it exactly. Do NOT continue with the entity-detection flow. |
| `${performanceExplorerContext}` present | UI_PERFORMANCE_EXPLORER | Load `ui-performance-explorer/summary/SKILL.md` and follow it exactly. Do NOT continue with the entity-detection flow. |
| No marker present | CLI | Continue to Step 0A (Entity Detection) below. |

**Important:** Treat the "no marker" case as CLI even when the invocation may originate from a UI surface (e.g., a user typing into Cortex Code from inside Snowsight without clicking "Analyze with CoCo"). Do NOT attempt to infer UI context from any other signal — only the explicit `${queryHistoryListContext}` / `${queryDetailsContext}` / `${performanceExplorerContext}` system-reminder markers route to the UI sub-skills. Everything else, including UI-without-button scenarios, follows the CLI flow.

UI sources hand control fully to their dedicated sub-skill — do not layer additional WPA behavior on top.

---

## Step 0A: Detect Entity + Depth + Acquire Data

**Before doing any analysis, determine three things:**

### 0A. Entity Detection

Inspect the user's input and classify the primary entity:

**UI context detection:** The UI surfaces structured context data via two mechanisms — either inlined into the prompt as `${...}` variables (e.g. `${warehouseContext}`), or registered as a `get_page_context` provider that the agent invokes lazily (e.g. for `${performanceExplorerContext}`). When any UI context is detected via either mechanism, the skill is in **UI mode** — parse the available data (invoking `get_page_context` if registered) and use it directly instead of running SQL queries.

| Signal in Input | Entity Type |
|---|---|
| Specific query ID (UUID-like format, e.g. `01b24bb0-0007-9627-0000-0001234abcde`) | **QUERY** |
| `query_parameterized_hash` value or "query pattern" / "recurring queries" / "repeated queries" | **QUERY_PATTERN** |
| Warehouse name (e.g. "ANALYTICS_WH") without query ID | **WAREHOUSE** |
| Table name (e.g. "DB.SCHEMA.ORDERS") | **TABLE** |
| "spilling", "spillage", "memory pressure", "spill to disk", "remote spilling" | **SPILLING** |
| "pruning", "partitions scanned", "scan volume", "worst pruning" | **PRUNING** |
| "clustering", "clustering keys", "cluster by", "tables for clustering" | **CLUSTERING** |
| "search optimization", "search index", "SOS", "search opt candidates" | **SEARCH_OPT** |
| "QAS", "query acceleration", "acceleration service", "QAS eligible" | **QAS** |
| "cache hit", "cache rate", "cache efficiency", "worst cache", "local disk cache", "warehouse cache" | **CACHE** |
| `${...}` context containing multiple queries | **MULTI_QUERY** |
| `${...}` context containing a single query | **QUERY** |
| "stored procedure", "procedure analysis", "child queries", "procedure breakdown", "CALL analysis", "nested calls", "stored procedure runtime", OR a query_id whose resolved `query_type = 'CALL'` | **STORED_PROCEDURE** |
| Multiple query_ids (2+ UUIDs), "these queries", "this set of queries", "analyze these N queries", "the workload", a SQL `WHERE` fragment over `QUERY_HISTORY` ("queries by user X", "queries on warehouse Y last week", "queries matching …"), or a list of `query_parameterized_hash` values ("all executions of pattern <hash>") | **QUERY_SET** |
| No specific entity identified | **UNKNOWN** |

**Entity Identifier Validation:** The following entity types require a concrete identifier. If detected but the identifier is missing or unresolvable, **stop and ask the user to provide it before proceeding.**

| Entity Type | Required Identifier |
|---|---|
| QUERY | `query_id` (UUID format) |
| QUERY_PATTERN | `query_parameterized_hash` |
| WAREHOUSE | `warehouse_name` |
| TABLE | Fully qualified table name (`database.schema.table`) |
| STORED_PROCEDURE | `query_id` of the parent CALL (UUID format) |
| QUERY_SET | One of (a) list of 2–1000 `query_id` values, (b) SQL `WHERE` fragment over `QUERY_HISTORY` with a time bound, (c) list of `query_parameterized_hash` values with a time bound |

**If entity is UNKNOWN:** Ask the user:
```
What would you like me to analyze?

1. A specific entity — provide a warehouse name, query ID, table name, or query pattern hash
2. A stored procedure run — provide the parent CALL query_id (analysis covers the parent + recursive child queries)
3. A named set of queries — provide a list of query_ids, a filter over query_history, or a list of pattern hashes
4. Account-level health check — scan across all performance dimensions (spilling, pruning, cache, QAS)
```

**MANDATORY STOPPING POINT:** Wait for the user's response.

- If the user provides a specific entity, re-classify and route accordingly.
- If the user picks option 2, route as **STORED_PROCEDURE** entity.
- If the user picks option 3, route as **QUERY_SET** entity.
- If the user picks option 4, proceed as **ACCOUNT** entity.

### 0A.1. Resolve query_id metadata before routing

The QUERY vs STORED_PROCEDURE choice cannot be made statically — it depends on `query_type`, which lives in `QUERY_HISTORY`. **For any input that resolves to a single `query_id`** (whether typed by the user or extracted from `${...}` UI context), perform a SQL round-trip first:

1. Fetch and execute the verified query: `Find stored procedure parent CALL` with `<QUERY_ID>` set to the user's id and `<DAYS>` = 7.
2. Inspect the resulting `query_type`:
   - `query_type = 'CALL'` → route to **STORED_PROCEDURE**. Reuse the fetched row as the parent CALL row inside `stored-procedure/summary/SKILL.md` Step 1 (do NOT re-fetch).
   - any other `query_type` → route to **QUERY**. Reuse the fetched row inside `query/summary/SKILL.md` Step 1 (do NOT re-fetch).
   - 0 rows returned → expand the time window per the QUERY/STORED_PROCEDURE summary's expand-window stop point.

This is intentionally a static round-trip; it ensures auto-routing on `query_type='CALL'` is deterministic across all input channels (CLI direct prompt, UI single-query context, `0A` static pattern match).

For input forms with **multiple ids, a SQL filter, or a hash list** (QUERY_SET), no resolve-then-route step is needed — those forms route unconditionally to QUERY_SET regardless of the resolved set's contents.

### 0B. Depth Detection

| Depth | Trigger Keywords | Phases to Load |
|---|---|---|
| **SUMMARY** | "summary", "overview", "quick look", "high-level", "brief", "health check" | `summary/` only |
| **DIAGNOSIS** | "what's wrong", "issues", "problems", "bottlenecks", "analyze", "why is X slow", "root cause", "performance issues", "concurrency issues", "statement timeout" | `summary/` + `detection/` |
| **RECOMMENDATION** | "recommend", "suggestion", "what should I do", "how to fix", "how to improve", "optimize", "best practice", "action items" | `summary/` + `detection/` + `recommendation/` |

**Default:** If depth is unclear, default to SUMMARY — load `summary/` only, then ask if user wants deeper analysis.

### 0C. Data Acquisition

- **If `${...}` context data is present (UI mode):** Parse the context data first. Use whatever fields are available as a starting point. However, the context may only contain partial information (e.g., query execution metrics but no pruning or spilling breakdown). **If the analysis requires data not present in the context, run supplementary SQL queries** using verified queries from the semantic model (see "SQL Query Construction" section below).
- **If no context data (CLI mode):** Construct SQL using verified queries from the semantic model to fetch data from ACCOUNT_USAGE views.

---

## Phase Routing

After detecting entity and depth, load the appropriate sub-skills:

### Entity → Sub-Skill Routing Table

| Entity | Summary (Phase 1) | Detection (Phase 2) | Recommendation (Phase 3) |
|---|---|---|---|
| **UI_QUERY_HISTORY** | `ui-query-history/summary/SKILL.md` | *(not applicable)* | *(not applicable)* |
| **UI_QUERY_DETAILS** | `ui-query-details/summary/SKILL.md` | *(not applicable)* | *(not applicable)* |
| **UI_PERFORMANCE_EXPLORER** | `ui-performance-explorer/summary/SKILL.md` | *(not applicable)* | *(not applicable)* |
| **QUERY** | `query/summary/SKILL.md` | `query/detection/SKILL.md` | `query/recommendation/SKILL.md` |
| **QUERY_PATTERN** | `query-pattern/summary/SKILL.md` | `query-pattern/detection/SKILL.md` | `query-pattern/recommendation/SKILL.md` |
| **WAREHOUSE** | `warehouse/summary/SKILL.md` | `warehouse/detection/SKILL.md` | `warehouse/recommendation/SKILL.md` |
| **TABLE** | `table/summary/SKILL.md` | `table/detection/SKILL.md` | `table/recommendation/SKILL.md` |
| **SPILLING** | `spilling/summary/SKILL.md` | `spilling/detection/SKILL.md` | `spilling/recommendation/SKILL.md` |
| **PRUNING** | `pruning/summary/SKILL.md` | `pruning/detection/SKILL.md` | `pruning/recommendation/SKILL.md` |
| **CLUSTERING** | `pruning/summary/SKILL.md` | `pruning/detection/SKILL.md` | `pruning/recommendation/SKILL.md` |
| **SEARCH_OPT** | `pruning/summary/SKILL.md` | `pruning/detection/SKILL.md` | `pruning/recommendation/SKILL.md` |
| **QAS** | `qas/summary/SKILL.md` | `qas/detection/SKILL.md` | `qas/recommendation/SKILL.md` |
| **CACHE** | `cache/summary/SKILL.md` | `cache/detection/SKILL.md` | `cache/recommendation/SKILL.md` |
| **ACCOUNT** | `account/summary/SKILL.md` | `account/detection/SKILL.md` | `account/recommendation/SKILL.md` |
| **STORED_PROCEDURE** | `stored-procedure/summary/SKILL.md` | `stored-procedure/detection/SKILL.md` | `stored-procedure/recommendation/SKILL.md` |
| **QUERY_SET** | `query-set/summary/SKILL.md` | `query-set/detection/SKILL.md` | `query-set/recommendation/SKILL.md` |
| **MULTI_QUERY** | Aggregate across queries in context, then route to relevant bottleneck entities based on findings |

### Phase Loading Rules

1. **SUMMARY depth:** Load `<entity>/summary/SKILL.md` only. After presenting results, ask: "Want me to identify root causes or provide recommendations?"
2. **DIAGNOSIS depth:** Load `<entity>/summary/SKILL.md` → then `<entity>/detection/SKILL.md`. After presenting results, ask: "Want me to provide recommendations for the issues found?"
3. **RECOMMENDATION depth:** Load `<entity>/summary/SKILL.md` → `<entity>/detection/SKILL.md` → `<entity>/recommendation/SKILL.md`. After presenting results, wait for user follow-up.

### Stopping Points

- **[STOP]** After Phase 1 summary (if SUMMARY depth) — offer deeper analysis or recommendations
- **[STOP]** After Phase 2 detection results (if DIAGNOSIS depth) — offer recommendations
- **[STOP]** After Phase 3 recommendations — wait for user follow-up
- **[STOP]** After hybrid table detection — explain limitations
- **[STOP]** If no data found — explain possible reasons (see Empty Results Handling)
- **[STOP]** If user asks a vague question — ask for clarification before proceeding

---

## SQL Query Construction

### Step 0: Load the Semantic Model

**[MANDATORY]** Before constructing or running any SQL, read the file `semantic_model/default.yaml` (relative to this skill's directory). This file contains:
- **Table definitions** with column names, types, and descriptions for each ACCOUNT_USAGE view
- **Relationships** between tables (e.g., join keys)
- **Verified queries** — pre-written, tested SQL queries indexed by name (e.g., "Which warehouses have the most spilling?")
- **Custom instructions** for consistent SQL output (required columns, formatting rules, aggregation patterns)

**Usage rules:**
1. When a sub-skill references a verified query by name, look up that exact name in the `verified_queries` section and use its SQL verbatim.
2. When constructing new SQL not covered by a verified query, use the table definitions and custom instructions from the semantic model to ensure correct column names and consistent output formatting.
3. Never fabricate column names or table structures — always cross-reference the semantic model.
4. All verified queries and inline SQL use `SNOWFLAKE.ACCOUNT_USAGE` views. If a query fails due to insufficient privileges, inform the user that their role needs the `SNOWFLAKE.USAGE_VIEWER` database role (or `SNOWFLAKE.OBJECT_VIEWER` / `SNOWFLAKE.GOVERNANCE_VIEWER` depending on the view). The ACCOUNTADMIN can grant this: `GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER TO ROLE <user_role>;`

### Step 1: Query Adaptation

When the user's question specifies a subset of a verified query's scope, adapt the WHERE filter and ORDER BY to match:

| User specifies | Adapt |
|---|---|
| "local spilling" / "spill to local" | Filter: `bytes_spilled_to_local_storage > 0` — Order by: `bytes_spilled_to_local_storage DESC` |
| "remote spilling" / "spill to remote" | Filter: `bytes_spilled_to_remote_storage > 0` — Order by: `bytes_spilled_to_remote_storage DESC` |
| "spilling" (generic) | Filter: `bytes_spilled_to_local_storage > 0 OR bytes_spilled_to_remote_storage > 0` — Order by: total (local + remote) DESC |
| Specific warehouse name | Add: `AND warehouse_name = '<NAME>'` |
| Specific user | Add: `AND user_name = '<NAME>'` |
| Custom time range ("last 3 days") | Replace the DATEADD interval |

**[CRITICAL]** Always keep the verified query's column list and structure — only adapt filters and ordering. NEVER add, remove, or rename columns from a verified query.

### Step 3: Execute and Present

Run the SQL and present results following the Output Format section below.

---

## Critical Rules

### 1. Internal Warehouses
- `COMPUTE_SERVICE_WH_*` warehouses are Snowflake-internal compute service warehouses
- They appear in `QUERY_HISTORY` and `QUERY_ACCELERATION_ELIGIBLE` but are **NOT visible via `SHOW WAREHOUSES`** and are **NOT user-configurable**
- When they appear in top-N results (spilling, QAS, cache), note them as internal and focus recommendations on user-owned warehouses

### 2. Stored Procedure Auto-Routing

When a user supplies a `query_id` and the row in `QUERY_HISTORY` resolves to `query_type = 'CALL'`, **auto-route to the STORED_PROCEDURE entity** instead of QUERY. The procedure analysis covers the parent CALL plus its child queries (linked via `session_id` + the parent's `[start_time, end_time]` window). The call tree query is hard-capped at **500 rows** to bound runtime; truncation is surfaced in the summary. If the user explicitly wants only the parent metrics, they can re-invoke with the QUERY entity.

### 3. Query-Set Routing Precedence

When the user supplies query identifiers without an explicit entity choice:
- **Exactly 1 `query_id`** → QUERY (or STORED_PROCEDURE if `query_type = 'CALL'`).
- **2+ `query_id` values** → QUERY_SET.
- **A SQL `WHERE` fragment over `QUERY_HISTORY`** → QUERY_SET (regardless of resulting set size).
- **A list of `query_parameterized_hash` values** → QUERY_SET (regardless of how many query_ids resolve, subject to the 1,000 cap).

QUERY_SET hard-caps at 1,000 query_ids; truncation is surfaced in the scope card.

### 4. Default Limits and Summarization

| Question Type | Default LIMIT | Summarize |
|---|---|---|
| Query-level (slowest, spilling, QAS eligible) | 20 | Yes — "Found X total, showing top 20" |
| Warehouse-level aggregations | 20 | Yes — highlight key patterns |
| Column analysis | 20 | Yes — group by table |

**[WARNING]**
- DO NOT use LIMIT 100 or higher unless user explicitly requests
- Always provide a summary before listing results

### 5. Empty Results Handling

| Scenario | Response |
|---|---|
| No spilling | "No queries with spilling in the last 7 days. Warehouses are adequately sized." |
| No pruning data | "No pruning data found. Possible reasons: (1) No recent queries, (2) Data latency up to 4 hours, (3) Hybrid table." |
| No search opt candidates | "No search optimization candidates. Queries may already be well-optimized." |

**When entities (warehouse, table, view, query) are not found via SHOW commands:**

Possible causes to mention:
1. **Name misspelled** — Ask user to verify the exact name
2. **Insufficient permissions** — User's role may not have access to view this object
3. **Object doesn't exist** — It may have been dropped or never created
4. **Wrong database/schema context** — The object exists in a different database or schema

---

## Terminology

| Abbreviation | Full Term |
|---|---|
| WH | Warehouse |
| QAS | Query Acceleration Service |
| SOS | Search Optimization Service |

---

## Output Format

**[IMPORTANT] Always provide summary + top results, not raw data dumps:**

1. **Summary statement**: "Found X queries with [issue]. Here are the top 20:"
2. **Top results**: Show top 10-20 results — use indented list for query-level results, tables for warehouse/table aggregations
3. **Key insights**: Highlight patterns (common warehouses, time periods, etc.)
4. **Common causes** of the issue (see detection sub-skills for details)
5. **Format shortcut**: After presenting results, include: "You can say **'show as table'** or **'show as list'** to switch format."

---

## Important Guidelines

### Workload SLA: Speed vs Cost

Performance findings must be interpreted relative to the workload's Service Level Agreement — the customer's prioritization of speed vs cost:

| Dimension | Speed Priority | Cost Priority |
|---|---|---|
| **Queuing** | No queuing acceptable — upsize or add clusters immediately | Small amounts of queuing acceptable — saves credit cost |
| **Execution time** | Minimize at all costs — larger warehouses, QAS enabled | Longer execution times acceptable if credits are saved |
| **Multi-cluster scaling** | Standard policy — adds clusters as soon as queries queue | Economy policy — adds clusters only after sustained queuing |
| **Local disk cache / auto-suspend** | Higher auto-suspend to keep local disk cache warm — cache hit rate is critical for reporting warehouses that repeatedly scan the same tables | Lower auto-suspend to reduce idle credits — accept lower local disk cache hit rates |
| **Warehouse sizing** | Favor larger sizes to avoid spilling and reduce execution time | Favor smaller sizes — accept local spilling if execution time is tolerable |

When presenting recommendations that involve these tradeoffs, first explain both interpretations so the customer understands the concepts, then ask which priority applies to this warehouse/workload to tailor the guidance.

## Limitations

- ACCOUNT_USAGE views have latency (up to 45 min for QUERY_HISTORY, up to 4 hours for pruning views)
- Analyzes historical patterns only — cannot predict future performance
- Cannot estimate actual benefits of clustering/search optimization
- Hybrid tables have limited visibility in these views
