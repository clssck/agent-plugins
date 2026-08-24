---
name: cluster-compute-cost
description: "Optimize Databricks cluster compute costs. Triggers: job compute, all-purpose, autoscaling, auto termination, compute policy, instance type, right-size cluster, Photon cost, spot instances, fleet, cluster cost, expensive cluster, job vs all-purpose, compute policies, T-shirt sizing, cluster pools."
parent_skill: databricks-cost-optimization
---

# Cluster Compute Cost Optimization

## When to Load

Parent skill routes here when the user wants to:
- Reduce cluster compute spend
- Migrate workloads from all-purpose to job compute
- Right-size clusters or choose better instance types
- Evaluate Photon cost-benefit
- Implement autoscaling, auto-termination, or spot instances
- Create compute policies for cost control

## Prerequisites

- Databricks CLI authenticated
- Workspace admin for compute policies; cluster access for auditing
- Run `cost-monitoring-governance/SKILL.md` first if you need spend context

## Workflow

### Step 1: Audit Current Cluster Usage

**1.1** — Identify all-purpose compute spend:

```sql
SELECT
  workspace_id,
  usage_metadata.cluster_id,
  sku_name,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
  AND sku_name LIKE '%ALL_PURPOSE%'
GROUP BY 1, 2, 3
ORDER BY total_dbus DESC
LIMIT 20
```

**1.2** — Cross-reference with cluster details:

```bash
databricks clusters list --output json | jq '.[] | {cluster_name, cluster_id, cluster_source, state, autoscale, num_workers, autotermination_minutes, node_type_id, spark_version, runtime_engine}'
```

**1.3** — Identify clusters used for scheduled jobs (candidates for job compute):

```bash
databricks jobs list --all --output json | jq '.[] | select(.settings.existing_cluster_id != null) | {job_id: .job_id, job_name: .settings.name, cluster_id: .settings.existing_cluster_id}'
```

Any job pinned to an existing all-purpose cluster should migrate to job compute.

> **⚠️ MANDATORY STOPPING POINT**: Present the audit findings and confirm which
> clusters to optimize before making changes.

### Step 2: Job Compute vs All-Purpose

All-purpose compute costs ~60-70% more per DBU than job compute. Migrate all
non-interactive workloads.

**Migration recommendation format:**

```
Cluster: <name> (<cluster-id>)
Current: ALL_PURPOSE, <N> DBUs/30 days
Usage: Runs scheduled job "<job-name>" daily
Recommendation: Migrate to JOB_COMPUTE
Action: Update job to use new_cluster instead of existing_cluster_id
Estimated savings: ~60-70% DBU reduction on this workload
```

**Implementation** — update the job definition:

```bash
databricks jobs get <job-id> --output json > job_backup.json
```

Change from `existing_cluster_id` to `new_cluster` in the job spec.
Use the `databricks-automation-bundles` skill for DAB-based configuration.

### Step 3: Right-Size Compute

**Instance type selection guide:**

| Workload Type | Recommended Family | Why |
|---|---|---|
| ML, heavy shuffle/spill | Memory optimized (r-series) | Reduces spill to disk |
| Structured streaming, maintenance | Compute optimized (c-series) | CPU-bound, less memory needed |
| Ad-hoc/interactive analysis | Storage optimized (i-series) | Benefits from local SSD caching |
| General / unknown | General purpose (m-series) | Balanced default |

Prefer the latest generation (e.g., Graviton-based on AWS for better
price-performance).

**T-shirt sizing guide:**

| Workload | Workers | Instance Type | Autoscaling |
|---|---|---|---|
| Development/testing | 0 (single node) or 2-4 | General purpose | Yes |
| Batch ETL | 8-16 | Memory optimized | Yes |
| Streaming | 4-8 | Compute optimized | Yes |
| Large-scale ETL | 16-32 | Memory optimized | Yes |

**Check for oversized clusters:**

Look for clusters where:
- Average CPU utilization < 30% (visible in Ganglia/cluster metrics)
- `num_workers` is fixed (no autoscaling) and consistently underutilized
- Instance type is larger than workload needs

### Step 4: Autoscaling

**Find clusters without autoscaling:**

```bash
databricks clusters list --output json | jq '.[] | select(.autoscale == null) | {cluster_name, cluster_id, num_workers, state}'
```

Enable autoscaling with appropriate bounds:

```json
{
  "autoscale": {
    "min_workers": 1,
    "max_workers": 8
  }
}
```

**For streaming workloads:** Standard autoscaling has limitations scaling down.
Use Lakeflow Declarative Pipelines with enhanced autoscaling instead. See
`streaming-workloads/SKILL.md`.

### Step 5: Auto Termination

**Find clusters without auto termination:**

```bash
databricks clusters list --output json | jq '.[] | select(.autotermination_minutes == null or .autotermination_minutes == 0) | {cluster_name, cluster_id, autotermination_minutes, state}'
```

Recommended values:
- **Dev clusters**: 30-60 minutes
- **Interactive analytics**: 60-120 minutes
- **Job compute**: handled automatically (terminates after job completes)

For workloads needing fast restart after termination:
- **Cluster pools** — pre-warm instances, no DBU charge while idle (only cloud
  VM costs). Reduces startup from minutes to seconds.
- **Prewarming** — schedule a process to start clusters before business hours,
  optionally with `CACHE SELECT` to warm data.

### Step 6: Spot Instances

Spot instances provide 60-90% savings over on-demand but can be evicted.

**Rules:**
- Driver: **always on-demand** (eviction kills the entire job)
- Workers: spot for fault-tolerant workloads

**Good for spot:** Batch ETL, ML training with checkpointing, dev/test
**Bad for spot:** Latency-sensitive streaming, short-running jobs, no retry logic

**Fleet instances (AWS):** Databricks auto-selects the best price/availability
across matching instance types. Prefer Fleet for spot workers.

**Check current spot usage:**

```bash
databricks clusters list --output json | jq '.[] | {cluster_name, aws_attributes: .aws_attributes.availability}'
```

### Step 7: Photon Cost-Benefit

Photon uses 2x DBU rate but can deliver >2x speedup for:
- Scan-heavy SQL and DataFrame operations
- Aggregations and joins
- String operations

**When Photon is worth it:**
- Wall-clock time drops >50% → net cost reduction despite 2x DBU rate
- Cluster can be downsized due to faster execution

**When Photon is NOT worth it:**
- Python UDF-heavy workloads (UDFs bypass Photon)
- Streaming micro-batches with minimal per-batch data
- Workloads already bottlenecked on shuffle I/O

**Evaluate:** Run the same job on Photon vs Standard, compare `total_dbus`
(DBU rate × wall-clock time). Use `databricks-spark-performance` skill for
detailed benchmarking.

**Check current Photon usage:**

```bash
databricks clusters list --output json | jq '.[] | {cluster_name, runtime_engine, spark_version}'
```

### Step 8: Runtime Version Check

Newer runtimes include performance improvements that reduce compute time.

```bash
databricks clusters list --output json | jq '.[].spark_version' | sort | uniq -c | sort -rn
```

Flag clusters on runtimes older than 2 major versions behind current LTS.
Upgrade to latest LTS for free performance gains.

### Step 9: Compute Policies

> **⚠️ MANDATORY STOPPING POINT**: Confirm policy definitions with the user
> before creating them.

**Check existing policies:**

```bash
databricks cluster-policies list --output json | jq '.[].name'
```

**Recommended T-shirt size policies:**

Small (dev/test):
```json
{
  "num_workers": { "type": "range", "minValue": 0, "maxValue": 4 },
  "autotermination_minutes": { "type": "range", "minValue": 30, "maxValue": 120 },
  "custom_tags.Environment": { "type": "fixed", "value": "dev" }
}
```

Medium (standard workloads):
```json
{
  "autoscale.min_workers": { "type": "range", "minValue": 1, "maxValue": 4 },
  "autoscale.max_workers": { "type": "range", "minValue": 4, "maxValue": 16 },
  "autotermination_minutes": { "type": "range", "minValue": 30, "maxValue": 120 }
}
```

Large (heavy workloads — requires approval):
```json
{
  "autoscale.min_workers": { "type": "range", "minValue": 4, "maxValue": 16 },
  "autoscale.max_workers": { "type": "range", "minValue": 16, "maxValue": 64 },
  "autotermination_minutes": { "type": "range", "minValue": 30, "maxValue": 60 }
}
```

Policies can also restrict instance types, enforce spot usage, and require tags.

## Stopping Points

- ✋ After Step 1: present audit, confirm which clusters to optimize
- ✋ After Step 9: confirm policy definitions before creation

## Cross-References

- **`databricks-spark-performance`** — detailed Spark tuning and Photon benchmarking
- **`databricks-automation-bundles`** — job compute configuration via DAB
- **`ml-gpu-compute/SKILL.md`** — GPU-specific instance selection
- **`streaming-workloads/SKILL.md`** — streaming autoscaling specifics

## Output

1. **Cluster audit report** — all clusters with cost, sizing, and config issues
2. **Migration plan** — all-purpose → job compute candidates with savings estimates
3. **Sizing recommendations** — per-cluster instance type and worker count changes
4. **Policy definitions** — T-shirt size policies ready to deploy
