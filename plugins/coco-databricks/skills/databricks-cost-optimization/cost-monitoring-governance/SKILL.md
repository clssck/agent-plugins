---
name: cost-monitoring-governance
description: "Databricks cost monitoring, tagging, budgets, dashboards, and governance. Triggers: billing, tagging, budget, chargeback, cost dashboard, cost audit, system.billing.usage, untagged resources, cost attribution, spending alerts."
parent_skill: databricks-cost-optimization
---

# Cost Monitoring & Governance

## When to Load

Parent skill routes here when the user wants to:
- Understand current Databricks spending
- Set up or audit tagging for cost attribution
- Configure budgets and spending alerts
- Build cost monitoring dashboards
- Run a full cost audit (this is the starting point)

## Prerequisites

- Account admin or workspace admin role
- Unity Catalog enabled (for `system.billing.usage`)
- Databricks CLI authenticated

## Workflow

### Step 1: Assess Current Spend

> **⚠️ MANDATORY STOPPING POINT**: Present findings and confirm scope before
> proceeding to recommendations.

**1.1** — 30-day billing breakdown by SKU:

```sql
SELECT
  usage_date,
  sku_name,
  usage_unit,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
GROUP BY 1, 2, 3
ORDER BY total_dbus DESC
```

**1.2** — Top cost drivers by workspace and tag:

```sql
SELECT
  workspace_id,
  sku_name,
  custom_tags,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
GROUP BY 1, 2, 3
ORDER BY total_dbus DESC
LIMIT 20
```

**1.3** — Untagged resource spend:

```sql
SELECT
  workspace_id,
  sku_name,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
  AND (custom_tags IS NULL OR custom_tags = map())
GROUP BY 1, 2
ORDER BY total_dbus DESC
```

**1.4** — Daily spend trend (detect anomalies):

```sql
SELECT
  usage_date,
  SUM(usage_quantity) AS daily_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
GROUP BY 1
ORDER BY 1
```

Present a summary table and highlight:
- Top 5 SKUs by DBU consumption
- Any untagged resource spend
- Spend anomalies (days with >2x average)

### Step 2: Tagging Strategy

Tags propagate to `system.billing.usage` and cloud provider billing. Missing
tags cannot be retroactively applied to past billing events.

**Minimum recommended tags:**

| Tag | Purpose | Apply To |
|---|---|---|
| `BusinessUnit` | Chargeback attribution | Workspaces, clusters, warehouses, pools |
| `Project` | Project-level cost tracking | Clusters, warehouses, pools |
| `Environment` | Dev/QA/Prod cost separation | Workspaces, clusters |
| `Owner` | Individual accountability | Clusters, warehouses |
| `CostCenter` | Finance alignment | Workspaces |

**Audit existing tags:**

```bash
databricks clusters list --output json | jq '.[] | {cluster_name, custom_tags}'
```

```bash
databricks warehouses list --output json | jq '.[] | {name, tags}'
```

**Enforce tags via compute policies:**

```json
{
  "custom_tags.BusinessUnit": { "type": "fixed", "value": "engineering" },
  "custom_tags.Project": { "type": "regex", "pattern": "^[a-z][a-z0-9-]+$", "isOptional": false },
  "custom_tags.Environment": { "type": "allowlist", "values": ["dev", "qa", "prod"] }
}
```

For serverless compute, use **budget policies** to attribute usage to users,
groups, or projects (tags don't apply to serverless the same way).

### Step 3: Budget Alerts

> **⚠️ MANDATORY STOPPING POINT**: Confirm budget thresholds with the user
> before creating budgets.

**Check existing budgets:**

```bash
databricks account budgets list
```

**Recommended budget structure:**
- One account-level budget for total monthly spend
- Per-workspace budgets for team-level accountability
- Per-project budgets using tag filters

Set email notifications at 80% and 100% of budget thresholds to catch
overspend early.

For serverless, create **budget policies** that apply tags to serverless
compute activity by user/group assignment.

### Step 4: Cost Monitoring Dashboards

**Option A — Built-in dashboards:**

Databricks provides cost management AI/BI dashboards in the account console.
Import into any Unity Catalog-enabled workspace for:
- Account-wide or workspace-level usage monitoring
- SKU-level cost breakdown
- Trend analysis and anomaly detection

**Option B — Custom dashboards via SQL:**

Build on `system.billing.usage` for custom views:

```sql
-- Weekly spend by SKU with week-over-week change
WITH weekly AS (
  SELECT
    DATE_TRUNC('WEEK', usage_date) AS week_start,
    sku_name,
    SUM(usage_quantity) AS weekly_dbus
  FROM system.billing.usage
  WHERE usage_date >= DATEADD(DAY, -90, CURRENT_DATE())
  GROUP BY 1, 2
)
SELECT
  week_start,
  sku_name,
  weekly_dbus,
  LAG(weekly_dbus) OVER (PARTITION BY sku_name ORDER BY week_start) AS prev_week,
  ROUND((weekly_dbus - LAG(weekly_dbus) OVER (PARTITION BY sku_name ORDER BY week_start))
    / NULLIF(LAG(weekly_dbus) OVER (PARTITION BY sku_name ORDER BY week_start), 0) * 100, 1) AS pct_change
FROM weekly
ORDER BY week_start DESC, weekly_dbus DESC
```

### Step 5: Ongoing Cost Governance

Recommend these operational practices:

- **Housekeeping job** — Schedule weekly to audit and enforce tags, log changes
- **Monthly cost reviews** — Share reports with team leads, review anomalies
- **Compute policies** — Enforce via `cluster-compute/SKILL.md` recommendations
- **Quarterly strategy review** — Revisit on scaling events, new projects, or
  cost spikes

Download billable usage via the Account REST API for offline analysis if needed.

## Stopping Points

- ✋ After Step 1: present spend assessment, confirm scope
- ✋ After Step 3: confirm budget thresholds before creation
- ✋ After Step 5: confirm governance practices

## Output

1. **Spend assessment** — 30-day breakdown by SKU, workspace, tag with anomalies
2. **Tagging plan** — recommended tags, enforcement via policies
3. **Budget configuration** — thresholds and notification setup
4. **Dashboard** — built-in or custom SQL-based monitoring
5. **Governance runbook** — ongoing practices and review cadence

## Next Steps

Based on the spend assessment, route to:
- Cluster costs high → Load `cluster-compute/SKILL.md`
- SQL warehouse costs high → Load `sql-warehouses/SKILL.md`
- Streaming costs high → Load `streaming-workloads/SKILL.md`
- ML/GPU costs high → Load `ml-gpu-compute/SKILL.md`
