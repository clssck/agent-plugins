# Stored Procedure Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide prioritized recommendations for a stored procedure based on the profile classifications, failed-child findings, structural patterns, and scoped bottleneck results from `stored-procedure/detection/SKILL.md`. Output is text + markdown only — **no HTML reports**.

## Prerequisites

- Phase 1 summary and Phase 2 detection results already presented.
- Available context: parent metrics, descendant tree (capped at LIMIT 500 rows; deeper structures flagged as truncated in summary), uncapped descendant aggregation totals (driving classification), profile classifications, failed-children list (if any), children-by-type aggregation, scoped bottleneck findings.

## Workflow

### Step 1: Load References (on demand)

Load only the references needed for the active classifications:
- `references/duration-columns.md` — already loaded by Phase 2; reuse.
- `references/statement-types.md` — load if recommendations reference batching strategies for specific `query_type` values (INSERT/MERGE/UPDATE).

### Step 2: Map Classifications to Recommendations

| Classification (from Phase 2) | Recommendation block | Default severity |
|---|---|---|
| Failed children | Surface every failure with `error_code` + `error_message` + offending statement; recommend rollback/retry strategy and (if recurring) procedure-level error handling | **Critical** |
| Compute-intensive | Optimize the dominant statement type — review query plan, indexing/clustering, partition pruning. If the same hash dominates, provide its `query_parameterized_hash` for separate QUERY_PATTERN analysis | Info–High |
| Compilation-heavy | Result caching where applicable; reduce session-level setup (`USE` / `SET` churn); enable persistent compilation results when supported; check for parameter sniffing (variant SQL per call) | Medium |
| Queue / undersized | Upsize warehouse OR add cluster (multi-cluster, max_cluster_count); reschedule the procedure off-peak; route the procedure to a dedicated warehouse if it competes with interactive work | High |
| Provisioning delays | Increase `MIN_CLUSTER_COUNT ≥ 1`, increase `AUTO_SUSPEND` to keep warehouse warm if the procedure runs frequently, or schedule a warm-up before the procedure | High |
| Lock contention | Reduce concurrent DML against the same tables; shorten transactions; convert separate INSERT/UPDATE into a single MERGE; review `transaction_blocked_time` ratio per child to find the offending statement | High |
| Unattributed "other" overhead | Note that GS/scheduling overheads are not exposed in `ACCOUNT_USAGE`; check for excessive metadata operations (many DDLs, SHOW commands, USE statements) inside the procedure body | Medium |
| Many / excessive children | Batch into bulk DML (multi-row INSERT, bulk MERGE), replace per-row CALL/SELECT with set-based statements, fold orchestration logic into single SQL via CTE/CASE | Medium–High |
| Sequential execution dominates total | If children are independent, consider running them in parallel sessions/tasks instead of within one CALL chain | Medium |
| Deep recursion / nested CALLs | Surface nesting depth; recommend flattening procedural calls when nested CALL adds wall-clock time without parallelism | Medium |

### Step 3: Cross-Reference Scoped Bottlenecks

Do **not** duplicate spilling / pruning / cache / QAS recommendations here. Instead, point at the delegated detection's recommendations:
- "See `spilling/recommendation/SKILL.md` for warehouse sizing guidance for the spilling children."
- "See `pruning/recommendation/SKILL.md` for clustering / search optimization guidance for the dominant scan tables."
- "See `cache/recommendation/SKILL.md` for cache-warming guidance for the warehouse running this procedure."
- "See `qas/recommendation/SKILL.md` for QAS enablement guidance for warehouses with eligible time."

If `query-set/recommendation/SKILL.md` exists in this skill version, delegate once to it with the leaf-descendant list — it consolidates all four dimensions.

### Step 4: Apply Speed-vs-Cost SLA Framing

Before finalizing sizing / multi-cluster / QAS / auto-suspend recommendations, apply the standard Speed-vs-Cost framing from the parent `SKILL.md`. Ask once:

> "Is this procedure a **speed-priority** workload (latency-sensitive — minimize wall-clock time at the expense of credits) or a **cost-priority** workload (batch/background — willing to accept longer runtime to save credits)?"

Tailor the recommendations to the chosen priority.

### Step 5: Cross-Workload Caution

Stored procedures often run on shared warehouses against shared tables. When recommending any of the following, emit an explicit caution:

| Action | Caution |
|---|---|
| `ALTER TABLE … CLUSTER BY …` | Re-clusters the entire table; affects every workload |
| `ALTER TABLE … ADD SEARCH OPTIMIZATION ON (…)` | Adds storage and write-amplification cost for all writes |
| `ALTER WAREHOUSE … SET WAREHOUSE_SIZE = …` | Affects every workload on the warehouse; consider a dedicated warehouse for procedure runs |
| `ALTER WAREHOUSE … SET ENABLE_QUERY_ACCELERATION = TRUE` | Charges QAS credits for all queries on the warehouse |
| Increasing `AUTO_SUSPEND` | Keeps warehouse warm for everyone; idle credit cost for non-procedure hours |

### Step 6: Present Recommendations

Output structure:

```
### Stored Procedure Recommendations: <parent_query_id>

**Workload context:** Warehouse <NAME (SIZE)> | Procedure runtime <Xs> | Children <K> | Profile: <classifications>

#### Critical
1. **<recommendation>** — <evidence (failed child query_id, error_code, etc.)>
   - Action: <concrete DDL or rewrite>
   - Caution: <if any cross-workload impact>

#### High Priority
2. **<recommendation>** — <evidence>
   - Action: …

#### Medium Priority
3. **<recommendation>** — <evidence>

#### Cross-Reference
- Spilling on <warehouse>: see `spilling/recommendation/SKILL.md`
- Pruning on <db.schema.table>: see `pruning/recommendation/SKILL.md`
- …
```

**[IMPORTANT]:**
- Prioritize by impact on **this procedure's** wall-clock time and credit cost.
- Group related recommendations — if the same warehouse / table appears under multiple classifications, present them together.
- **DO explain trade-offs** for every recommendation.
- **DO NOT** generate HTML, PDF, or any binary report artifacts.

**[STOP]** Wait for user follow-up.

## Edge Cases

| Situation | Handling |
|---|---|
| Procedure has no descendants | Recommend like a single QUERY: focus on parent's classification |
| All children succeeded, parent failed | Recommend procedure-body audit; note that ACCOUNT_USAGE lacks the procedure source — point at INFORMATION_SCHEMA.PROCEDURES |
| Recommendations would conflict (e.g. upsize for speed vs downsize for cost) | Show both; let the user pick the SLA priority in Step 4 |
| Internal warehouses (`COMPUTE_SERVICE_WH_*`) involved | Skip warehouse sizing recommendations on them; flag as internal, not user-configurable |
