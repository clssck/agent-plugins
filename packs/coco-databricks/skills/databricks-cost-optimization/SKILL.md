---
name: databricks-cost-optimization
description: >
  Audit and optimize Databricks costs across compute, storage, and workloads.
  Use when: reduce Databricks cost, save money, cost optimization, expensive
  cluster, DBU usage, spot instances, autoscaling, auto termination, compute
  policy, right-size cluster, serverless vs classic, Photon cost-benefit,
  streaming cost, always-on streaming, tagging, cost attribution, chargeback,
  budget alerts, cost monitoring, system tables billing, billing usage,
  system.billing.usage, job compute vs all-purpose, SQL warehouse sizing,
  instance type selection, GPU cost, unnecessary GPU, compute policies,
  fleet instances, cost audit, cost dashboard, reduce spend Databricks,
  model serving cost, ML training cost, Delta optimization cost.
---

# Databricks Cost Optimization

Router skill — detects intent and loads the appropriate sub-skill.

## Prerequisites

1. **Databricks CLI authenticated** — run `databricks auth describe` to verify.
   If auth fails, switch to the `databricks-cli-install` skill.
2. **Account admin or workspace admin** — needed for billing system tables,
   compute policies, and budgets. Some steps work with lesser privileges.
3. **Unity Catalog enabled** — required for `system.billing.usage` queries.

## Intent Detection

| Intent | Triggers | Load |
|--------|----------|------|
| **Cost Monitoring & Governance** | billing, tagging, budget, chargeback, cost dashboard, cost audit, system.billing.usage, untagged resources, cost attribution, spending alerts | `cost-monitoring-governance/SKILL.md` |
| **Cluster Compute** | job compute, all-purpose, autoscaling, auto termination, compute policy, instance type, right-size, Photon cost, spot instances, fleet, cluster cost, expensive cluster | `cluster-compute/SKILL.md` |
| **SQL Warehouses** | SQL warehouse, warehouse sizing, serverless warehouse, classic warehouse, IWM, SQL cost, warehouse idle, warehouse scaling | `sql-warehouses/SKILL.md` |
| **Streaming & Workloads** | streaming cost, always-on, triggered streaming, availableNow, Delta optimization, OPTIMIZE, VACUUM, Z-ORDER, runtime version, batch vs streaming | `streaming-workloads/SKILL.md` |
| **ML & GPU Compute** | GPU cost, unnecessary GPU, ML training cost, model serving cost, deep learning cost, GPU audit, GPU instance | `ml-gpu-compute/SKILL.md` |
| **Full Audit** | full cost audit, reduce overall spend, cost optimization review | Load `cost-monitoring-governance/SKILL.md` first, then route to other sub-skills based on findings |

## Workflow

```
Start
  ↓
Ask user: What do you want to optimize?
  ↓
  ├─→ Cost monitoring / tagging / budgets → Load cost-monitoring-governance/SKILL.md
  ├─→ Cluster compute costs              → Load cluster-compute/SKILL.md
  ├─→ SQL warehouse costs                → Load sql-warehouses/SKILL.md
  ├─→ Streaming / workload costs         → Load streaming-workloads/SKILL.md
  ├─→ ML / GPU costs                     → Load ml-gpu-compute/SKILL.md
  └─→ Full audit                         → Load cost-monitoring-governance/SKILL.md
                                            then route based on findings
```

**⚠️ MANDATORY STOPPING POINT**: Ask the user which area to focus on before
loading any sub-skill. If the user wants a full audit, start with cost
monitoring to identify the biggest cost drivers, then route accordingly.

## Stopping Points

- ✋ Before loading any sub-skill: confirm focus area with user
- ✋ After full audit assessment: confirm which areas to optimize

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `system.billing.usage` not found | Unity Catalog not enabled or no access | Enable UC or request `system` catalog access from admin |
| Compute policy errors | Insufficient privileges | Need workspace admin role to create/edit policies |
| Missing tags on resources | Tags never applied | Start with `cost-monitoring-governance` sub-skill to set up tagging |
| Budget API errors | Account-level feature | Budgets require account admin; workspace admin is not enough |

## Output

Each sub-skill produces its own deliverables. For a full audit, the combined
output is:

1. **Cost assessment report** — 30-day spend breakdown by SKU, workspace, and tag
2. **Optimization recommendations** — prioritized list with estimated savings
3. **Implementation plan** — specific changes with before/after cost projections
4. **Monitoring setup** — tags, budgets, and dashboards for ongoing control
