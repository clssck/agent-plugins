# Stored Procedure Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Analyze a stored procedure execution starting from its parent `CALL` `query_id`. Build the call tree (parent + all descendant queries, including nested CALLs) and present a duration breakdown.

## Background

A stored procedure execution is one `query_id` of `query_type = 'CALL'`. Its child statements are not directly linked by a parent_query_id column in `ACCOUNT_USAGE.QUERY_HISTORY`; instead they share the parent's `session_id` and execute within the parent's `[start_time, end_time]` window. A nested `CALL` follows the same rule recursively against the nested CALL's own time window.

Constraints when working from `ACCOUNT_USAGE.QUERY_HISTORY`:
- Up to 45 minutes data latency.
- 365-day retention.
- The 7 exposed duration columns leave a residual "other" bucket that captures GS/scheduling/gateway overheads — see `references/duration-columns.md`.

## Prerequisites

- Parent CALL `query_id` (UUID).
- Access to `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY`.
- Default analysis window is the last 7 days; expandable on request.

## Workflow

### Step 1: Find the Parent CALL

**[MANDATORY]** Fetch and execute the verified query: `Find stored procedure parent CALL` (with `<QUERY_ID>` and `<DAYS>=7`).

Validation:
- 0 rows → ask the user to expand window (14 / 30 / 90 days) or verify the query_id; remind of the 45-minute latency. **[STOP]**
- 1 row, `query_type != 'CALL'` → warn and ask whether to continue analysis as if it were a procedure (rare; usually the user should switch to QUERY entity).
- 1 row, `query_type = 'CALL'` → capture `session_id`, `start_time`, `end_time`, warehouse, user, status. Proceed.

### Step 2: Build the Call Tree

**[MANDATORY]** Fetch and execute the verified query: `Find stored procedure call tree` with:
- `<PARENT_QUERY_ID>` — the CALL row from Step 1
- `<PARENT_SESSION_ID>` — captured in Step 1
- `<PARENT_START_TIME>`, `<PARENT_END_TIME>` — captured in Step 1

The verified query uses a **flat session-window scan + containment self-join** (NOT a recursive CTE). Mechanism:
1. Materialize one CTE `_call_tree_candidates` with every row in the parent's session within `[parent.start_time, parent.end_time]`.
2. Build a direct-parent link for each non-root candidate by selecting the **minimum-width strictly-containing CALL interval** (`parent.is_call=TRUE`, `parent.start_time <= child.start_time`, `parent.end_time >= child.end_time`, and the parent interval is not identical to the child interval).
3. Derive `depth` from a bounded parent-chain walk over those direct-parent links. Depth is capped at 5 for display; rows deeper than that are reported at depth 5.
4. Return the parent (depth=0) plus every row with a non-NULL direct-parent link, ordered by `start_time`.

**[CRITICAL] Hard LIMIT 500.** The verified query is hard-capped at 500 rows. If the procedure has more than 500 descendants, results are truncated to the earliest 500 by `start_time`. **You MUST surface this to the user** — see Edge Cases below.

Each row carries: `depth`, `parent_query_id`, `query_id`, `query_type`, `is_call BOOLEAN`, the 7 duration columns + computed `other_time_ms`, `execution_status`, `error_code`, `error_message`, `bytes_scanned`, `rows_produced`, `partitions_scanned`, `partitions_total`, `warehouse_name`, `warehouse_size`, and `query_preview`.

Edge cases:
- 0 descendants → procedure ran a single statement; note this in output but still present the parent breakdown.
- Many descendants (> 100) → still show the tree but truncate per-row listing to the top 20 by duration; note the rest are summarized in the aggregate row.
- **500-row cap reached** → say so explicitly: "Call tree result hit the 500-row hard cap. Some descendants are not shown. Want me to (a) show only top-level CALLs, (b) filter by `query_type`, or (c) re-run with a tighter time window?" To detect: `COUNT(*) >= 500` in the result.

### Step 2b: Uncapped Descendant Aggregation

**[MANDATORY]** Fetch and execute the verified query: `Aggregate stored procedure descendants (uncapped totals)` with the same `<PARENT_QUERY_ID>`, `<PARENT_SESSION_ID>`, `<PARENT_START_TIME>`, `<PARENT_END_TIME>`. This returns one row of:
- `descendant_count`, `failure_count`
- `total_elapsed_ms`, `total_compile_ms`, `total_execute_ms`, `total_queue_ms`, `total_blocked_ms`, `total_external_ms`, `total_other_ms`

**Critically:** the duration breakdown table in Step 3 and the profile-classification thresholds in `stored-procedure/detection/SKILL.md` Step 2 are computed off **these uncapped totals**, NOT the 500-row tree result. Tree truncation does not affect duration accuracy.

### Step 3: Present the Tree Summary

```
## Stored Procedure Analysis: <parent_query_id>

| Field | Value |
|---|---|
| Warehouse | NAME (SIZE) |
| User | <user_name> |
| Total Elapsed | Xs |
| Status | SUCCESS / FAILED / INCIDENT |
| Direct Children | N |
| Nested CALLs | M |
| Total Descendants | K (from uncapped aggregation, Step 2b) |
| Tree truncated at 500-row cap | yes / no |

### Call Tree (top 20 by duration)
▾ <parent CALL> [Xs]
  ├ <child SELECT> [Xs]
  ├▾ <nested CALL> [Xs]
  │   ├ <grandchild INSERT> [Xs]
  │   └ <grandchild MERGE> [Xs]
  └ <child UPDATE> [Xs]

### Duration Breakdown (parent + all descendants — from Step 2b uncapped aggregation)
| Phase | Total (s) | % |
|---|---|---|
| Execution | … | … |
| Compilation | … | … |
| Queue (overload + provisioning + repair) | … | … |
| Transaction Blocked | … | … |
| List External Files | … | … |
| Other (computed) | … | … |
```

Format note: render the tree using indented bullets; `▾` = expanded CALL, `├`/`└` = sibling rows. Indent two spaces per depth level.

### Step 4: Stop and Offer Next Steps

**[STOP]** Ask:

1. "Want me to identify root causes / bottlenecks?" → Phase 2 (`stored-procedure/detection/SKILL.md`).
2. "Want a workload performance check (spilling / pruning / cache / QAS) over the procedure's child queries?" → if QUERY_SET entity is available in this skill version, delegate to `query-set/{summary,detection,recommendation}/SKILL.md` with the leaf descendants' `query_id` list. Otherwise, route the leaves through the relevant single-dimension entities (SPILLING, PRUNING, CACHE, QAS) one at a time.
3. "Want to drill into a specific nested CALL?" → re-invoke STORED_PROCEDURE with that CALL's `query_id`.
4. "Call tree result hit the 500-row hard cap — narrow scope?" — only ask if descendant count = 500.

## Edge Cases

| Situation | Handling |
|---|---|
| Parent not found in 7-day window | Offer 14 / 30 / 90 / custom; remind of 45-min latency |
| Parent `query_type != 'CALL'` | Warn; suggest QUERY entity unless user insists |
| 0 descendants | Note "single-statement procedure"; present parent breakdown only |
| 500-row cap reached | Surface in summary; offer "narrow scope" / "filter by query_type" / "show only top-level CALLs" |
| Cycle in `query_id` (theoretical) | The flat-scan + containment-join approach is cycle-free by construction (uses interval containment, not parent links) |
| Failed parent (`execution_status='FAIL'`) | Highlight `error_code` / `error_message` and proceed; descendants up to the failure point may still be present |
| Internal warehouses (`COMPUTE_SERVICE_WH_*`) | Flag as internal in the warehouse row; no sizing recommendations against them |

## References

Do **not** load these files in this Phase 1 sub-skill — they are loaded only by `stored-procedure/detection/SKILL.md` and `stored-procedure/recommendation/SKILL.md`:

- `references/duration-columns.md` — for interpreting the duration breakdown thresholds (loaded in Phase 2).
- `references/statement-types.md` — for interpreting `query_type` in the tree (loaded in Phase 2 if needed).
