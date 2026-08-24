# Spilling Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Analyze spilling patterns to identify root causes and highlight the most impacted warehouses/queries.

## Prerequisites

- Spilling summary data already presented by `spilling/summary/SKILL.md`

## Scope-Aware Mode (when invoked from QUERY_SET)

If the caller passed scope params (`<ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`), this sub-skill operates in **scope-aware mode** — restrict every spilling query to that scope:
- Replace the verified query `Which warehouses have the most spilling?` with `Which warehouses have the most spilling? — scoped to query set` (substituting `<ID_LIST>`, `<SCOPE_START>`, `<SCOPE_END>`).
- Replace the verified query `Which queries are causing the most spilling?` with `Which queries are causing the most spilling? — scoped to query set`.

**In scope-aware mode:**
- The "summary already presented" prerequisite is **relaxed** — the QUERY_SET scope card replaces this sub-skill's own Phase-1 summary. Do NOT require `spilling/summary/SKILL.md` to have run first.
- **Suppress the per-step `[STOP]`** at the end of the Workflow — orchestration belongs to QUERY_SET, which presents all four dimensions as one consolidated section before stopping.
- Skip re-presenting warehouse-level totals; focus on insights, severity, and drill-down within the set.

When invoked outside QUERY_SET (no scope params), behave exactly as before — use the unscoped verified queries and honor the per-step `[STOP]`.

## Workflow

### Step 1: Insights

After reviewing the summary data, provide:

1. **Key patterns** — which warehouses/users/time periods show the most local spilling and remote spilling
2. **Common causes:**
   - Warehouse too small for data volume (primary cause of both local and remote spilling)
   - High query concurrency competing for memory (exacerbates local spilling)
   - Complex joins/aggregations producing large intermediate results
3. **Severity assessment:**
   - **Remote spilling** (`bytes_spilled_to_remote_storage`) = severe memory pressure, significant performance impact — strong signal the warehouse is undersized
   - **Local-only spilling** (`bytes_spilled_to_local_storage` with no remote) = moderate, warehouse may be slightly undersized
   - **QAS check**: If a warehouse has QAS enabled and shows remote spilling, compare `query_acceleration_bytes_scanned` against `bytes_spilled_to_remote_storage`. If they are similar, the remote spilling is QAS overhead — not a memory pressure signal. Flag this: *"Remote spilling on <WAREHOUSE> appears to be QAS overhead, not memory pressure."*

### Step 2: Offer Drill-Down

If a specific query stands out (e.g. very high spilling), offer:
```
Query 01abc-123 has 85GB remote spilling. Want me to analyze this query in detail?
```

If user says yes, the parent skill will re-route to `query/summary/SKILL.md` for that query ID.

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.
