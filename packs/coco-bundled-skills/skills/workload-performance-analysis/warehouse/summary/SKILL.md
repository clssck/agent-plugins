# Warehouse Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Present a multi-dimensional performance overview for a specific warehouse.

## Workflow

### Step 1: Gather Warehouse Metrics

Run the following verified queries from the semantic model, scoped to the specified warehouse by adding `WHERE warehouse_name = '<UPPERCASE_NAME>'` (or `AND warehouse_name = '<UPPERCASE_NAME>'` if a WHERE clause already exists).

**[MANDATORY]** For each query below, fetch and execute the exact SQL from the semantic model. Do NOT rewrite or regenerate these queries.

**These queries are independent — execute them in parallel:**

1. **Query volume** — verified query: `Query volume by warehouse`
2. **Spilling summary** — verified query: `Which warehouses have the most spilling?`
3. **Cache summary** — verified query: `Cache hit rates by warehouse`
4. **QAS opportunity** — verified query: `Which warehouses have the most QAS eligible time?`
5. **Queue time summary** — verified query: `Queue time by warehouse`

### Step 2: Present Warehouse Summary

```
## Warehouse Performance: <WAREHOUSE_NAME> (<SIZE>) — Last 7 Days

| Dimension | Key Metric | Value |
|---|---|---|
| Query Volume | Total Queries | X |
| Query Volume | Avg Execution Time | Xs |
| Spilling | Local Spilling | X GB |
| Spilling | Remote Spilling | X GB |
| Cache | Avg Cache Hit | X% |
| QAS | Eligible Queries | X (potential savings: Xs) |
| Queue Time | Queries with Queue Time | X (overload: Xs, provisioning: Xs) |
```

### Step 3: Highlight Issues

Flag any dimensions that stand out:
- Local spilling > 0 → "This warehouse has local spilling — queries are exceeding available memory and spilling to local SSD"
- Remote spilling > 0 → "This warehouse has remote spilling — queries are exceeding both memory and local SSD, spilling to cloud storage (severe performance impact). Check if QAS is enabled — if so, some remote spilling may be QAS overhead, not memory pressure."
- Cache hit < 50% → "Cache utilization is low"
- QAS eligible > 0 → "Query acceleration could reduce execution time"
- Queries with queue time > 0 → "Queries are waiting for resources on this warehouse"

**[STOP]** Present the summary table. Ask: "Want me to drill into specific bottlenecks or provide recommendations?"
