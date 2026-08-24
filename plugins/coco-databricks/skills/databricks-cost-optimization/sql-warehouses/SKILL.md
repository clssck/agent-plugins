---
name: sql-warehouse-cost
description: "Optimize Databricks SQL warehouse costs. Triggers: SQL warehouse, warehouse sizing, serverless warehouse, classic warehouse, pro warehouse, IWM, intelligent workload management, SQL cost, warehouse idle, warehouse scaling, warehouse auto stop, SQL serverless, warehouse type."
parent_skill: databricks-cost-optimization
---

# SQL Warehouse Cost Optimization

## When to Load

Parent skill routes here when the user wants to:
- Right-size SQL warehouses
- Choose between serverless, pro, and classic warehouse types
- Reduce SQL warehouse idle costs
- Optimize warehouse scaling and concurrency

## Prerequisites

- Databricks CLI authenticated
- Workspace admin for warehouse configuration
- Unity Catalog enabled for billing queries

## Workflow

### Step 1: Audit Current SQL Warehouse Spend

**1.1** — SQL warehouse DBU consumption (30 days):

```sql
SELECT
  workspace_id,
  usage_metadata.warehouse_id,
  sku_name,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
  AND sku_name LIKE '%SQL%'
GROUP BY 1, 2, 3
ORDER BY total_dbus DESC
```

**1.2** — List all warehouses with configuration:

```bash
databricks warehouses list --output json | jq '.[] | {id, name, cluster_size, warehouse_type, auto_stop_mins, min_num_clusters, max_num_clusters, num_clusters, state, enable_serverless_compute}'
```

**1.3** — Identify idle warehouses (running but not serving queries):

```sql
SELECT
  warehouse_id,
  COUNT(*) AS query_count,
  SUM(total_duration_ms) / 1000 / 3600 AS total_query_hours
FROM system.query.history
WHERE start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
  AND warehouse_id IS NOT NULL
GROUP BY 1
ORDER BY query_count ASC
```

Cross-reference low-query warehouses with their DBU spend from Step 1.1.

> **⚠️ MANDATORY STOPPING POINT**: Present findings before recommending changes.

### Step 2: Warehouse Type Selection

| Type | Pricing | Startup Time | Best For |
|---|---|---|---|
| **Serverless** | Highest DBU rate, includes VM cost | Seconds | Bursty BI, variable workloads, instant availability |
| **Pro** | Mid DBU rate + cloud VM cost | Minutes | Steady workloads, advanced security features |
| **Classic** | Lowest DBU rate + cloud VM cost | Minutes | Predictable, always-on workloads |

**When Serverless saves money despite higher DBU rate:**
- Bursty usage patterns (BI dashboards, ad-hoc queries)
- Short idle periods followed by bursts — serverless scales down faster
- Users unwilling to wait for cold start → classic warehouses stay running idle
- Intelligent Workload Management (IWM) optimizes concurrent query scheduling

**When Classic/Pro is cheaper:**
- Sustained high-throughput workloads (ETL, scheduled reports)
- Predictable, consistent usage with minimal idle time
- Large teams using warehouses continuously during business hours

### Step 3: Warehouse Sizing

Start small and scale up based on actual need.

**Sizing guide:**

| Concurrent Users | Query Complexity | Recommended Size | Clusters |
|---|---|---|---|
| 1-5 | Simple dashboards | X-Small or Small | 1 |
| 5-20 | Mixed BI + ad-hoc | Small or Medium | 1-2 (autoscaling) |
| 20-50 | Heavy BI + complex queries | Medium or Large | 2-4 (autoscaling) |
| 50+ | Enterprise BI platform | Large | 4+ (autoscaling) |

**Key principle:** Prefer scaling out (more clusters via autoscaling) over
scaling up (larger cluster size). Autoscaling clusters handle concurrency
spikes more cost-effectively.

**Check current sizing efficiency:**

```sql
SELECT
  warehouse_id,
  DATE_TRUNC('HOUR', start_time) AS hour,
  COUNT(*) AS queries,
  AVG(total_duration_ms) AS avg_duration_ms,
  MAX(total_duration_ms) AS max_duration_ms,
  SUM(CASE WHEN status = 'QUEUED' THEN 1 ELSE 0 END) AS queued_count
FROM system.query.history
WHERE start_time >= DATEADD(DAY, -7, CURRENT_TIMESTAMP())
  AND warehouse_id IS NOT NULL
GROUP BY 1, 2
ORDER BY queued_count DESC
```

If `queued_count` is consistently high → increase max clusters or warehouse size.
If queries are fast and no queueing → consider downsizing.

### Step 4: Auto Stop Configuration

Every warehouse should have auto stop configured. Serverless warehouses scale
down in seconds, so aggressive auto stop values are safe.

> **KEY INSIGHT — 1-minute auto stop via API:**
> The Databricks UI defaults auto stop to **10 minutes** and enforces a **minimum of
> 5 minutes**. However, the **API allows setting `auto_stop_mins` as low as 1 minute**.
> For serverless warehouses (which restart in seconds), this is a significant cost
> saving — 9 minutes of idle time per session adds up quickly across many warehouses
> and usage bursts.
> **Always check for and recommend 1-minute auto stop on serverless warehouses.**

**Recommended auto stop values:**

| Warehouse Type | UI Minimum | API Minimum | Recommended |
|---|---|---|---|
| Serverless | 5 min | **1 min** | **1 min** (via API) — instant restart makes this safe |
| Pro/Classic (interactive) | 5 min | **1 min** | 5-10 min (cold start penalty applies) |
| Pro/Classic (scheduled-only) | 5 min | **1 min** | **1-2 min** (via API) — no user waiting |

**4.1 — Flag warehouses that can benefit from sub-5-minute auto stop:**

This is the highest-impact quick win. Any serverless warehouse still at the UI
default of 10 minutes (or even the UI minimum of 5) is leaving money on the table.

```bash
databricks warehouses list --output json | jq '.[] | select(.auto_stop_mins >= 5) | {name, id, auto_stop_mins, warehouse_type, state}'
```

For each warehouse returned, evaluate:
- **Serverless** -> set to 1 min (no user-facing impact, restarts in seconds)
- **Pro/Classic used for scheduled jobs only** -> set to 1-2 min
- **Pro/Classic used interactively** -> keep at 5-10 min (cold start takes minutes)

**4.2 — Check warehouses with excessive or no auto stop:**

```bash
databricks warehouses list --output json | jq '.[] | select(.auto_stop_mins == null or .auto_stop_mins > 60) | {name, id, auto_stop_mins, warehouse_type}'
```

**4.3 — Update auto stop to 1 minute (API only):**

```bash
databricks warehouses edit <warehouse-id> --json '{"auto_stop_mins": 1}'
```

> **NOTE:** After setting via API, the UI will display the value correctly but
> will reset it to 5 minutes minimum if the warehouse is edited through the UI.
> Always use the API for sub-5-minute values. Document which warehouses use API-set
> auto stop so they aren't accidentally overridden by UI edits.

### Step 5: Scaling Configuration

**Autoscaling clusters (multi-cluster warehouses):**

```bash
databricks warehouses list --output json | jq '.[] | {name, min_num_clusters, max_num_clusters, warehouse_type}'
```

- Set `min_num_clusters` to 0 (serverless) or 1 (classic/pro if cold start is
  acceptable) to avoid paying for idle capacity
- Set `max_num_clusters` based on peak concurrent query load from Step 3

**Scaling policies:**

| Pattern | min_clusters | max_clusters |
|---|---|---|
| Cost-first (bursty BI) | 0-1 | 2-4 |
| Balance (standard BI) | 1 | 4-8 |
| Performance-first (enterprise BI) | 2 | 8+ |

### Step 6: Query Optimization for Cost

Faster queries = less warehouse uptime = lower cost. Key quick wins:

- **Photon** — enabled by default on all SQL warehouses. Verify it's not disabled.
- **Result caching** — SQL warehouse caches results for identical queries
  within a 24-hour window. BI tools benefit heavily from this.
- **Predicate pushdown** — ensure queries filter early (`WHERE` clauses on
  partitioned/clustered columns).
- **Avoid SELECT *** — read only needed columns to reduce scan volume.
- **Delta OPTIMIZE** — compacted Delta tables read faster. Schedule maintenance
  via `streaming-workloads/SKILL.md`.

## Stopping Points

- ✋ After Step 1: present spend and idle warehouse audit
- ✋ Before Step 4-5 changes: confirm auto stop and scaling values

## Cross-References

- **`databricks-dbsql`** — SQL warehouse features, SQL scripting, and best practices
- **`cluster-compute/SKILL.md`** — if SQL workloads are running on all-purpose clusters
- **`streaming-workloads/SKILL.md`** — Delta maintenance to speed up warehouse queries
- **`cost-monitoring-governance/SKILL.md`** — tagging warehouses for cost attribution

## Output

1. **Warehouse audit** — all warehouses with spend, sizing, and idle analysis
2. **Type recommendations** — serverless vs pro vs classic per warehouse
3. **Sizing changes** — right-sized configurations with scaling policies
4. **Auto stop updates** — per-warehouse auto stop values
