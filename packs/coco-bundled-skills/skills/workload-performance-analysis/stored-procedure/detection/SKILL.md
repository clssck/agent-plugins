# Stored Procedure Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Diagnose where time goes in a stored procedure: classify the runtime profile, surface failed children, detect structural patterns (many children, sequential vs parallel, recursion), and route deeper bottleneck analysis to the relevant scoped sub-skills.

## Prerequisites

- Phase 1 (`stored-procedure/summary/SKILL.md`) already presented the call tree and duration breakdown.
- Captured: parent metrics, descendant rows (with depth + the 7 duration columns + computed `other_time_ms`), parent `session_id`, parent time window.

## Workflow

### Step 1: Load the Duration Reference

**[MANDATORY]** Read `references/duration-columns.md`. Use the threshold table to classify the parent + aggregate-of-descendants profile.

### Step 2: Profile Classification

Compute ratios on the parent first, then on the **uncapped descendant aggregation totals** (from `Aggregate stored procedure descendants (uncapped totals)` in Phase 1 Step 2b — NOT the 500-row tree result). Classify by the highest-precedence rule that fires. The threshold table below is the single source of truth shared with `query-set/detection/SKILL.md` Step 3.

| Condition | Classification | Severity |
|---|---|---|
| `failure_count / descendant_count > 5%` (or any failed parent) | **Failed children** | Critical |
| `total_execute_ms / total_elapsed_ms > 90%` | Compute-intensive | Info |
| `total_compile_ms / total_elapsed_ms > 30%` | Compilation-heavy | Medium |
| `total_queue_ms / total_elapsed_ms > 10%` | Queue / undersized warehouse | High |
| `total_blocked_ms / total_elapsed_ms > 5%` | Lock contention | High |
| `total_other_ms / total_elapsed_ms > 30%` | Unattributed overhead | Medium |

Multiple classifications can apply — list all that fire.

### Step 3: Failed-Children Scan

If any descendant has `error_code IS NOT NULL`:
- Show every failed row with: depth, `query_id`, `query_type`, `error_code`, `error_message`, first 100 chars of `query_text`, parent `query_id` in the tree.
- Treat as **Critical** in Phase 3 recommendations.

### Step 4: Structural Pattern Detection

Run these checks against the tree captured in Phase 1:

| Pattern | Signal | Notes |
|---|---|---|
| Many children | `descendant_count > 10` | Consider batching |
| Excessive children | `descendant_count > 50` | Strongly recommend batching |
| Recursive procedure | `is_call` count > 1 in descendants | Expected for orchestrators; flag if unintended |
| Sequential execution | No overlap among descendants' `[start_time, end_time]` | Expected inside a single session; mention only if duration is dominated by it |
| Parallel attempts | Overlapping descendant time ranges | Rare in single-session procedures; usually only via async sub-jobs |
| Deep nesting | `MAX(depth) = 5` (saturated by the 5-hop walk) | Depth derivation caps at 5; deeper trees still render with `depth = 5` for the deepest rows. If the procedure may nest deeper, note that the depth column under-reports beyond 5. |
| Tree truncated | Tree result returned exactly 500 rows (the LIMIT 500 cap) | Surface explicitly; offer to filter by query_type or narrow the time window. The uncapped aggregation already gives accurate descendant_count. |
| Single-statement procedure | `descendant_count = 0` | Profile classification still applies to the parent |

### Step 5: Aggregate Descendants by Statement Type

**[MANDATORY]** Fetch and execute the verified query: `Aggregate stored procedure children by query type` with the same parent identifiers used in Phase 1. Present:

```
### Children by Statement Type
| query_type | count | total_elapsed_s | total_compile_s | total_execute_s | total_queue_s | total_blocked_s | % of total |
|---|---|---|---|---|---|---|---|
| INSERT | 12 | … | … | … | … | … | 42% |
| MERGE | 4  | … | … | … | … | … | 28% |
| SELECT | 30 | … | … | … | … | … | 18% |
…
```

If the user asks about specific `query_type` values, load `references/statement-types.md` for descriptions.

### Step 6: Delegate Scoped Bottleneck Analysis

For deeper performance analysis on the procedure body, **delegate to scoped bottleneck sub-skills** rather than reimplementing them here. Pass:
- The list of leaf descendant `query_id` values (exclude `is_call=true` container rows; their work is in their own children).
- The parent's `[start_time, end_time]` window.
- Distinct `query_parameterized_hash` values from the descendants (for joining `TABLE_QUERY_PRUNING_HISTORY` / `COLUMN_QUERY_PRUNING_HISTORY`, which lack `query_id`).

Delegation targets:

| Bottleneck dimension | Delegate to |
|---|---|
| Spilling | `spilling/detection/SKILL.md` (filter by leaf `query_id` IN list + parent time window) |
| Pruning | `pruning/detection/SKILL.md` (filter by `query_parameterized_hash` IN list + parent time window) |
| Cache | `cache/detection/SKILL.md` (filter by leaf `query_id` IN list + parent time window) |
| QAS | `qas/detection/SKILL.md` (filter by leaf `query_id` IN list + parent time window) |

If a `query-set/` entity is present in this skill version, prefer delegating once to `query-set/detection/SKILL.md` with the leaf list — it fans out to all four dimensions in parallel.

**Scope injection rule:** for every verified query used by the loaded sub-skill, add the scope predicate to its WHERE clause. Preserve the verified query's column list and ORDER BY untouched — scope is filter-only.

### Step 7: Cross-Dimensional Insights

After delegated detections return, summarize:
1. **Top time bucket** — which classification fires hardest (compute / compile / queue / blocked / other / failures)?
2. **Top offender by query_type** — which statement type accounts for > 50% of descendant time?
3. **Concentration** — do a small number of `query_parameterized_hash` values dominate? (Count distinct hashes covering 80% of total descendant elapsed time.)
4. **Co-located bottlenecks** — same warehouse spilling AND with bad cache? same table dominating both pruning and bytes_scanned?
5. **Priority ranking** for Phase 3.

### Step 8: Present Findings

Present in this order:
1. Profile classification(s) and severities.
2. Failed children (if any).
3. Structural patterns.
4. Children-by-type aggregation table.
5. Scoped bottleneck findings (from delegated sub-skills).
6. Cross-dimensional insights and priority ranking.

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.

## Edge Cases

| Situation | Handling |
|---|---|
| Parent failed but no descendants captured | Show only the parent's classification + error |
| All descendants succeeded but parent failed | Highlight failure as parent-side (likely procedure body raised after children completed) |
| Many small children with low individual duration | Note batching opportunity; do not flag every child |
| Bottleneck delegation returns empty | The procedure body is not a notable contributor to that dimension at the account level — say so explicitly |
| Hybrid tables involved | Note that pruning views have limited visibility for hybrid tables |
