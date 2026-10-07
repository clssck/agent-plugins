# Account Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Present a consolidated account-level performance health check across all dimensions.

## Workflow

### Step 1: Run Cross-Dimensional Health Check

**These 4 queries are independent — execute them all in parallel:**

1. **Spilling** — **[MANDATORY]** Fetch and execute the exact SQL from verified query: `Which warehouses have the most spilling?` in the semantic model. Do NOT rewrite or regenerate this query. Summarize: local spilling and remote spilling across account (always show both separately), top warehouses affected. If any warehouse shows remote spilling, note it as a severe signal.
2. **Pruning** — **[MANDATORY]** Fetch and execute the exact SQL from verified query: `Pruning opportunity, sorted by the potential to avoid partitions` in the semantic model. Do NOT rewrite or regenerate this query. Summarize: tables with worst pruning efficiency, total wasted rows.
3. **Local Disk Cache** — **[MANDATORY]** Fetch and execute the exact SQL from verified query: `Warehouses with bad cache hit rates and significant scan and query volume` in the semantic model. Do NOT rewrite or regenerate this query. Summarize: warehouses with lowest local disk cache utilization.
4. **QAS** — **[MANDATORY]** Fetch and execute the exact SQL from verified query: `Which warehouses have the most QAS eligible time?` in the semantic model. Do NOT rewrite or regenerate this query. Summarize: total eligible time savings, top warehouses.

### Step 2: Present Consolidated Summary

```
## Account Performance Health Check (Last 7 Days)

| Area | Status | Key Finding |
|---|---|---|
| Spilling | X warehouses with spilling | Top: WAREHOUSE_NAME (X GB local, X GB remote) |
| Pruning | X tables with <50% pruning | Top: DB.SCHEMA.TABLE (X% pruning) |
| Local Disk Cache | X warehouses below 50% cache hit | Top: WAREHOUSE_NAME (X% cache hit) |
| QAS | X eligible queries | Potential savings: Xs |
```

**[STOP]** Present results. Ask: "Want me to drill into any specific area, or provide recommendations across all dimensions?"
