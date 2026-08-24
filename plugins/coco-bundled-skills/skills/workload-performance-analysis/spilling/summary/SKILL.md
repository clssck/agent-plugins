# Spilling Summary

**This is a Phase 1 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Present a high-level overview of spilling across warehouses and queries.

## Workflow

### Step 1: Warehouse-Level Spilling

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Which warehouses have the most spilling?` in the semantic model. Do NOT rewrite or regenerate this query.

Present results:

```
## Spilling by Warehouse (Last 7 Days)

| Warehouse | Size | Query Count | Local Spilling (GB) | Remote Spilling (GB) | Queries with Spilling |
```

**[IMPORTANT] Always show local spilling and remote spilling separately** — never combine into a single "total spilling" number without the breakdown. Example: "224.87 GB total (224.82 GB local spilling, 0.05 GB remote spilling)"

- **Local spilling** = memory exceeded, data spilled to local SSD. Moderate performance impact.
- **Remote spilling** = both memory and local SSD exceeded, data spilled to cloud storage (e.g., S3). Severe performance impact.
- **QAS caveat**: If QAS is enabled on a warehouse, it contributes a small amount to remote spilling. To estimate true memory-pressure remote spilling, check `query_acceleration_bytes_scanned` — if remote spilling ≈ QAS bytes scanned, the remote spilling is QAS overhead, not a sizing issue.

### Step 2: Query-Level Spilling

**[MANDATORY]** Fetch and execute the exact SQL from verified query: `Which queries are causing the most spilling?` in the semantic model. Do NOT rewrite or regenerate this query.

Present results using indented list format:

```
## Top Queries by Spilling

1. **<query_id>**
   - Warehouse: <warehouse_name> (<warehouse_size>)
   - Local Spilling: <local_spill_gb> GB
   - Remote Spilling: <remote_spill_gb> GB
   - Execution: <execution_seconds>s
   - User: <user_name> | <start_time>
   - Preview: `<query_preview>`
```

**[STOP]** Present both warehouse table and query list. Ask: "Want me to analyze spilling patterns or provide recommendations?"
