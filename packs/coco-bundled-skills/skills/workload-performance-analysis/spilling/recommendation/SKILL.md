# Spilling Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide actionable recommendations to reduce spilling based on detection findings.

## Workflow

### Step 1: Generate Recommendations

Based on the spilling detection findings, provide targeted recommendations:

| Finding | Recommendations |
|---|---|
| **Remote spilling on any warehouse** | Critical — but first check if QAS is enabled: if `query_acceleration_bytes_scanned ≈ bytes_spilled_to_remote_storage`, the remote spilling is QAS overhead, not memory pressure — no action needed. Otherwise, upsize the warehouse immediately. Remote spilling means data is being written to cloud storage (e.g., S3), causing severe performance degradation. |
| **Local-only spilling, small volume** | Moderate — the warehouse is slightly undersized for some queries, or this may indicate memory pressure from concurrency (multiple queries competing for the same memory). Local spilling writes to SSD which is slower than memory but much faster than remote storage. Consider upsizing by one step (e.g., MEDIUM → LARGE) or reducing concurrency. |
| **Spilling concentrated on few queries** | Target those specific queries — they may benefit from running on a dedicated, larger warehouse rather than upsizing the shared warehouse. |
| **Spilling spread across many queries** | The warehouse is generally undersized for its workload. Upsize the warehouse or reduce concurrency (`MAX_CONCURRENCY_LEVEL`). |
| **Spilling during specific time windows** | Consider scheduling heavy queries during off-peak hours, or use a separate warehouse for batch workloads. |
| **High concurrency + spilling** | Each concurrent query shares warehouse memory. Reduce `MAX_CONCURRENCY_LEVEL` or enable multi-cluster warehouses to spread the load (Enterprise Edition and above). |

### Step 2: Present Recommendations

```
### Spilling Recommendations

1. **<First recommendation>**
   - Why: <evidence — e.g., "ANALYTICS_WH (MEDIUM) has 85GB remote spilling from 12 queries">
   - How: <specific action — e.g., "ALTER WAREHOUSE ANALYTICS_WH SET WAREHOUSE_SIZE = 'LARGE';">
   - Trade-off: <cost implication — e.g., "LARGE costs 2x MEDIUM credits per hour">

2. **<Second recommendation>**
   - Why: <evidence>
   - How: <action>
   - Trade-off: <implication>
```

**[IMPORTANT]:**
- **DO provide specific warehouse size guidance** based on spill volume
- **DO explain credit cost trade-offs** when recommending upsizing

**SLA note:** For cost-priority workloads, local-only spilling with acceptable execution times may not require upsizing — the credit savings from a smaller warehouse may outweigh the spilling overhead. For speed-priority workloads, any spilling should be addressed to minimize execution time.

### Step 3: Offer Query-Level Drill-Down

After presenting infrastructure recommendations, inform the user that spilling can also be caused by inefficient SQL (e.g., unnecessary cross joins, missing filters, large intermediate results) — optimizing the query may reduce or eliminate spilling without infrastructure changes.

```
Some of these queries may benefit from SQL-level optimization that could reduce spilling. Want me to drill into the top spilling queries?
```

If the user says yes, route the top spilling queries to `query/summary/SKILL.md` → `query/detection/SKILL.md` → `query/recommendation/SKILL.md`.

**[STOP]** Wait for user follow-up.
