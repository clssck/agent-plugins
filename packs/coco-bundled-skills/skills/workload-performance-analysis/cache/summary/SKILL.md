# Cache Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Present a high-level overview of local disk cache (warehouse cache) utilization across warehouses. This sub-skill analyzes `percentage_scanned_from_cache` — the local disk cache on compute node SSD/memory. It does NOT cover the query result cache or metadata cache.

**Terminology**: Mirror the user's term. If the user says "local disk cache", use that. If "warehouse cache", use that. Both refer to the same cache.

## Workflow

### Step 1: Warehouse Cache Hit Rates

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Warehouses with bad cache hit rates and significant scan and query volume` in the semantic model. Do NOT rewrite or regenerate this query.

Present results:

```
## Warehouse Cache Hit Rates (Last 7 Days)

| Warehouse | Size | Query Count | Avg Cache Hit % | Avg Execution (s) | Avg GB Scanned |
```

Results are ordered by `avg_cache_hit_pct ASC` — worst cache utilization first.

**[STOP]** Present results. Ask: "Want me to analyze cache patterns in detail, or provide recommendations?"
