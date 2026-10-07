# Warehouse Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Perform deeper analysis on a warehouse by routing to bottleneck-specific detection sub-skills based on Phase 1 findings.

## Prerequisites

- Warehouse summary data already presented by `warehouse/summary/SKILL.md`

## Workflow

### Step 1: Route to Bottleneck-Specific Detections

Based on the issues flagged in the warehouse summary, load the appropriate detection sub-skills **scoped to this warehouse** (add `WHERE warehouse_name = 'WAREHOUSE_NAME'` to all queries — always uppercase the warehouse name value, e.g. `= 'ANALYTICS_WH'`).

**The initial data-gathering queries for each bottleneck are independent — execute them in parallel where possible.** Then process each bottleneck's results sequentially for insights.

| Issue Found in Summary | Load |
|---|---|
| Spilling detected | `spilling/detection/SKILL.md` — but scope queries to this warehouse only |
| Low local disk cache hit rate | `cache/detection/SKILL.md` — but scope queries to this warehouse only |
| QAS-eligible queries found | `qas/detection/SKILL.md` — but scope queries to this warehouse only |
| High queue times | Run queue contention analysis (Step 1B below) |

### Step 1B: Queue Contention Analysis (if queue times flagged)

If the warehouse summary shows significant queue times, **[MANDATORY]** fetch and execute the exact SQL from verified query `Queued queries for a warehouse` in the semantic model, scoped to this warehouse. Do NOT rewrite or regenerate this query.

Classify the queue pattern:
- **Overload-dominated**: Warehouse compute is fully utilized — consider upsizing or utilize multi-cluster warehouses (Enterprise Edition and above). If multi-cluster: Standard scaling policy favors speed (scales out immediately when queries queue), Economy favors cost (scales out only after sustained queuing).
- **Provisioning-dominated**: Warehouse frequently suspending/resuming — consider adjusting auto-suspend timeout or consolidating with other similar workload warehouses
- **Mixed**: Both overload and provisioning — consider a multi-cluster warehouse with `MAX_CLUSTER_COUNT > 1` to scale for concurrency while reducing suspension delays (Enterprise Edition and above). Standard scaling policy favors speed, Economy favors cost.

### Step 2: Cross-Dimensional Insights

After running relevant detections, provide cross-dimensional insights:

1. **Query mix** — Are different bottlenecks caused by the same queries or different workloads?
2. **Sizing assessment** — Based on spilling volume and query patterns, is the warehouse appropriately sized?

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.
