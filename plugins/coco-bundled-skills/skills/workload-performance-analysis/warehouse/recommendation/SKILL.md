# Warehouse Recommendations

**This is a Phase 3 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Provide actionable warehouse-level recommendations based on cross-dimensional detection findings.

## Workflow

### Step 1: Generate Recommendations

Based on the warehouse detection findings, provide targeted recommendations:

| Finding | Recommendations |
|---|---|
| **Spilling + low local disk cache hit** | The warehouse is likely undersized. Recommend upsizing — this addresses both spilling (more memory) and local disk cache (more SSD cache). |
| **Spilling only** | Upsize the warehouse or reduce concurrency. See `spilling/recommendation/SKILL.md` for detailed guidance. |
| **Low local disk cache hit only** | Review auto-suspend settings and workload mix. See `cache/recommendation/SKILL.md` for detailed guidance. |
| **QAS opportunity** | Enable QAS on this warehouse. See `qas/recommendation/SKILL.md` for detailed guidance. |
| **Mixed workloads causing issues** | Consider splitting into multiple dedicated warehouses (e.g., one for ETL, one for analytics, one for ad-hoc). |
| **High concurrency + performance issues** | Consider multi-cluster warehouse configuration or reducing `MAX_CONCURRENCY_LEVEL`. |
| **High queue times (overload-dominated)** | Warehouse compute is fully utilized — consider upsizing or multi-cluster. If multi-cluster: Standard scaling policy for speed-priority workloads (scales out immediately), Economy for cost-priority (scales out only after sustained queuing). |
| **High queue times (provisioning-dominated)** | Warehouse frequently suspending/resuming — consider adjusting auto-suspend timeout. |

### Step 1B: Frame Recommendations by SLA Priority

Before presenting specific recommendations, explain how the workload's speed-vs-cost priority affects the guidance:

- **Queuing detected**: "Small amounts of queuing may be acceptable for cost-optimized workloads. For speed-critical workloads, any queuing should be addressed."
- **Multi-cluster recommended**: "Standard scaling policy adds clusters proactively (speed-first). Economy policy waits until queuing is sustained (cost-first)."
- **Cache improvements**: "Increasing auto-suspend keeps cache warm but increases idle credits. This is a cost-benefit tradeoff — high cache hit rates matter most for reporting warehouses that repeatedly scan the same tables."
- **Sizing changes**: "Upsizing reduces spilling and execution time but doubles credit cost per size step."

Present this context, then ask: "Is this warehouse used for speed-critical workloads (e.g., interactive dashboards, real-time analytics) or cost-optimized workloads (e.g., batch ETL, scheduled reports)?" Tailor the specific recommendations to their answer.

### Step 2: Present Recommendations

```
### Warehouse Recommendations: <WAREHOUSE_NAME> (<SIZE>)

1. **<First recommendation>**
   - Why: <evidence — e.g., "85GB spilling + 15% local disk cache hit suggests undersized">
   - How: <specific action>
   - Trade-off: <cost implication>

2. **<Second recommendation>**
   - Why: <evidence>
   - How: <action>
   - Trade-off: <implication>
```

### Step 3: Offer Query-Level Drill-Down

After presenting infrastructure recommendations, inform the user that the queries contributing to the detected issues (spilling, low cache, queue time) may benefit from SQL-level optimization — which can reduce or eliminate the bottleneck without infrastructure changes.

```
Some of these issues may be caused by specific queries that could be optimized at the SQL level. Want me to:
- Drill into the top spilling/slow queries on this warehouse?
- Check if Query Insights are available for those queries?
```

If the user says yes, route the top contributing queries to `query/summary/SKILL.md` → `query/detection/SKILL.md` → `query/recommendation/SKILL.md`.

**[STOP]** Wait for user follow-up.
