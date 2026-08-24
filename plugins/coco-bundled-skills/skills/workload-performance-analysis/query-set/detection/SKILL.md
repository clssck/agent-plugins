# Query Set Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Run scoped dimensional analysis (spilling, pruning, cache, QAS) over a confirmed QUERY_SET. Delegates to existing dimension detection sub-skills with scope params; adds failed-query scan, duration-profile classification, scope-vs-account context, and concentration analysis.

## Prerequisites

- `query-set/summary/SKILL.md` already resolved the input, derived the scope, presented the scope card, and received user confirmation to proceed.
- Available context: `<ID_LIST>`, `<HASH_LIST>`, `<TABLE_ID_LIST>` (from scope tables), `<SCOPE_START>`, `<SCOPE_END>`, plus the duration roll-up totals from the scope card.

## Workflow

### Step 1: Delegate to Dimension Detection Sub-Skills

Load each dimension detection sub-skill **in scope-aware mode** by passing the scope params. The sub-skills detect that scope params are present and switch to the scoped verified queries (named `<base name> — scoped to query set` in the semantic model).

| Dimension | Sub-skill loaded | Params passed |
|---|---|---|
| Spilling | `spilling/detection/SKILL.md` | `<ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>` |
| Pruning  | `pruning/detection/SKILL.md`  | `<HASH_LIST>`, `<SCOPE_START>`, `<SCOPE_END>` |
| Cache    | `cache/detection/SKILL.md`    | `<ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>` |
| QAS      | `qas/detection/SKILL.md`      | `<ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>` |

**Orchestration contract:**
- Fetch the four scoped verified queries **in parallel**, then consume their results sequentially and present them in **one consolidated section** (per-dimension subsection).
- Do **NOT** invoke each dimension sub-skill's per-step `[STOP]`. Orchestration belongs to QUERY_SET. The dimension sub-skills' Scope-Aware Mode sections explicitly suppress their own STOPs when scope params are present.
- The QUERY_SET scope card already replaces each dimension's "summary already presented" prerequisite. Do not re-present per-dimension Phase-1 summaries.

### Step 2: Failed-Query Scan

For every query_id in the set with `error_code IS NOT NULL` (already captured in scope resolution), present:
- `query_id`, `query_type`, `warehouse_name (warehouse_size)`, `error_code`, first 100 chars of `error_message`, first 100 chars of `query_text`.
- Treat individual failures as evidence. Do **not** label the set Critical solely because one query failed.
- If `failure_count / query_count > 5%`, classify the failure pattern as **Critical** and flag it as a top-priority finding (same threshold used in Step 3 and `stored-procedure/detection/SKILL.md`).

### Step 3: Duration Profile (Set-Level)

Using the duration roll-up totals captured in the scope card (`total_elapsed_ms`, `total_compile_ms`, `total_execute_ms`, `total_queue_ms`, `total_blocked_ms`, `total_external_ms`, `total_other_ms`, `failure_count`, `query_count`), classify the set's runtime profile. The threshold table is the **single source of truth shared with `stored-procedure/detection/SKILL.md` Step 2**:

| Condition | Classification | Severity |
|---|---|---|
| `failure_count / query_count > 5%` | **Failed queries** | Critical |
| `total_execute_ms / total_elapsed_ms > 90%` | Compute-intensive | Info |
| `total_compile_ms / total_elapsed_ms > 30%` | Compilation-heavy | Medium |
| `total_queue_ms / total_elapsed_ms > 10%` | Queue / undersized warehouse | High |
| `total_blocked_ms / total_elapsed_ms > 5%` | Lock contention | High |
| `total_other_ms / total_elapsed_ms > 30%` | Unattributed overhead | Medium |

Multiple classifications can fire — list all that apply.

If reference details are needed (column meanings, threshold rationale), load `references/duration-columns.md` on demand.

### Step 4: Scope-vs-Account Context

For each dimension, compute the set's share of the account-wide total over the same time window:

```
Spilling: this set = A GB local / B GB remote → X% of account local, Y% of account remote
Pruning:  this set excess partitions = N → X% of account excess
Cache:    this set weighted-avg cache hit = P% vs account P'% (Δ = P − P')
QAS:      this set eligible seconds = E → X% of account eligible
Queue:    this set queue time = Q → X% of account queue
```

This contextualizes severity. A workload with 5% of the account's spilling but only 0.1% of the queries is a disproportionate contributor.

### Step 5: Concentration Analysis

Identify Pareto patterns within the set:
- Distinct `query_parameterized_hash` values that account for 80% of total elapsed time.
- Distinct warehouses that account for 80% of spilling (or the dimension flagged in Step 1).
- Distinct tables that account for 80% of excess scanned rows.

Surface "is it one bad query?" vs "is it spread out?" — different remediation strategies.

### Step 6: Cross-Dimensional Insights

After delegated detections return, summarize:
1. **Top time bucket** — which classification fires hardest (compute / compile / queue / blocked / other / failures)?
2. **Top offender by query_type** — which statement type accounts for > 50% of set elapsed time?
3. **Co-located bottlenecks** — same warehouse showing both spilling AND bad cache; same table dominating both poor pruning AND high scan volume.
4. **Priority ranking for the set** — order Critical → High → Medium based on impact within the set, not account-wide.

### Step 7: Present Findings

Present in this order:
1. Profile classification(s) and severities (Step 3).
2. Failed queries (Step 2; if any).
3. Per-dimension scoped results from delegated detection sub-skills (Step 1).
4. Scope-vs-account context (Step 4).
5. Concentration analysis (Step 5).
6. Cross-dimensional insights and priority ranking (Step 6).

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.

## Edge Cases

| Situation | Handling |
|---|---|
| Set is all CALLs | Note it; suggest STORED_PROCEDURE entity for tree analysis |
| One dimension returns 0 rows after scoping | Say so explicitly; the set is not a notable contributor to that dimension |
| All dimensions empty | The set has no detectable bottlenecks; profile classification still applies. Recommend the set is well-tuned |
| Set includes internal warehouses (COMPUTE_SERVICE_WH_*) | Skip warehouse-sizing recommendations on them; flag as internal |
| Hybrid tables touched | Pruning views have limited visibility; note in the pruning section |
| Scope-vs-account share < 1% in every dimension | Note that the set is not a significant account-wide contributor; deprioritize |

## References

- `references/duration-columns.md` — load when interpreting compute / compile / queue / blocked / other thresholds.
