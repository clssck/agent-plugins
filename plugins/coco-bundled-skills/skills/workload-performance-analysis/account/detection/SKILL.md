# Account Detection

**This is a Phase 2 sub-skill. It is loaded by the parent `workload-performance-analysis` skill — do NOT invoke independently.**

## Purpose

Perform deeper analysis across all performance dimensions for the entire account, routing to bottleneck-specific detection sub-skills.

## Prerequisites

- Account summary data already presented by `account/summary/SKILL.md`

## Workflow

### Step 1: Route to Bottleneck-Specific Detections

Based on the issues found in the account summary, load the appropriate detection sub-skills:

| Issue Found in Summary | Load |
|---|---|
| Warehouses with spilling | `spilling/detection/SKILL.md` |
| Tables with poor pruning | `pruning/detection/SKILL.md` |
| Warehouses with low local disk cache hit | `cache/detection/SKILL.md` |
| Warehouses with QAS opportunity | `qas/detection/SKILL.md` |

**The data-gathering queries across different bottleneck types are independent — execute them in parallel where possible.** Then process each bottleneck's results for insights.

Present each bottleneck's findings, then move to cross-dimensional insights.

### Step 2: Cross-Dimensional Insights

After running relevant detections, provide account-level insights:

1. **Highest-impact areas** — Which bottleneck type affects the most queries/warehouses?
2. **Common root causes** — Are multiple bottlenecks pointing to the same issue (e.g., undersized warehouses causing both spilling and poor local disk cache hit rates)?
3. **Priority ranking** — Which issues should be addressed first for maximum benefit?

**[STOP]** Wait for user direction or continue to recommendations if depth = RECOMMENDATION.
