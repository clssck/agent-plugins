---
name: databricks-spark-performance
description: >
  Diagnose and fix Spark job performance bottlenecks on Databricks. Use when:
  slow Spark job, shuffle optimization, data skew, spill to disk, broadcast join,
  AQE tuning, Adaptive Query Execution, Photon evaluation, partition tuning,
  Spark UI interpretation, stage bottleneck, OOM, out of memory, GC pressure,
  task duration skew, shuffle partition count, spark.sql.shuffle.partitions,
  autoBroadcastJoinThreshold, redundant shuffle, unnecessary repartition,
  double shuffle, why is my Spark job slow, optimize Spark,
  performance tuning Databricks, slow stage, slow query Databricks.
---

# Databricks Spark Performance Tuning

Diagnose and resolve Spark job performance issues on Databricks using a
metrics-driven workflow. Covers shuffle tuning, data skew, spill, broadcast
joins, redundant shuffles, AQE, and Photon. Works with both multi-node and
single-node clusters.

## Prerequisites

Before starting, confirm:

1. **Databricks CLI authenticated** — run `databricks auth describe` to verify.
   If auth fails, switch to the `databricks-cli-install` skill.
2. **Cluster access** — you need permission to view Spark UI for the target
   cluster. Confirm with `databricks clusters get <cluster-id>`.
3. **A slow job or query to diagnose** — you need a specific job run ID,
   notebook URL, or SQL query that exhibits poor performance.
4. **DBR version** — run `databricks clusters get <cluster-id> | grep spark_version`
   to determine runtime. AQE defaults and Photon availability vary by version:
    - DBR 12.2+ : AQE enabled by default
    - DBR 13.3+ : Photon available on all-purpose clusters
    - DBR 14.0+ : AQE skew join optimization enabled by default
    - DBR 15.0+ : Photon enabled by default on photon-capable instance types
    - DBR 16.0+ : Enhanced AQE with improved coalescing heuristics

## Core Concepts

### Quick Reference Table

| Bottleneck | Key Metric | Healthy Threshold | Fix Category |
|---|---|---|---|
| Shuffle-heavy | Shuffle Read + Write | < 1 GB per stage | Partition tuning |
| Data skew | Max task duration vs median | Max < 2× median | Salting / repartition |
| Spill | Spill (Disk) / Shuffle Read | Ratio < 0.1 | Memory tuning |
| Small-table join | Smaller side size | < 100 MB | Broadcast join |
| Serialization | GC Time / Task Time | < 10% | Kryo / object reduction |
| Redundant shuffle | Multiple shuffles in plan | Stages with same key | Remove repartition |
| I/O bound | Scan time dominance | Scan < 30% of stage | File sizing / Z-ORDER |

### Key Formulas

**Shuffle partition count:**

```
N = ceil(shuffle_data_MB / 128 / total_cores) × total_cores
```

Where:
- `shuffle_data_MB` = total shuffle data in the largest stage (from Spark UI)
- `total_cores` = total executor cores. For multi-node: `num_workers × cores_per_worker`.
  For single-node clusters (`spark.master = local[*, N]`): use N (the driver cores).
- `128` = target partition size in MB (sweet spot for most workloads)

**Example (multi-node):** 50 GB shuffle, 32 total cores →
`ceil(50000 / 128 / 32) × 32 = ceil(12.2) × 32 = 13 × 32 = 416 partitions`

**Example (single-node):** 500 MB shuffle, 4 cores →
`ceil(500 / 128 / 4) × 4 = ceil(0.98) × 4 = 1 × 4 = 4 partitions`

**Broadcast threshold:**

```python
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "100m")  # up to 8g max
```

Default is 10 MB. Safe to raise to 100 MB–1 GB if driver memory allows.

**Spill ratio:**

```
spill_ratio = spill_disk_bytes / shuffle_read_bytes
```

If > 0.1 (10%), executors need more memory or partitions need increasing.

## Workflow

### Phase 1: Triage — Identify the Slow Stage

> **⚠️ MANDATORY STOPPING POINT**: Confirm the job run ID or query with the
> user before pulling metrics. Do not guess which job to diagnose.

**Step 1.1** — Get job run details:

```bash
# For a job run
databricks jobs get-run <run-id> --output json

# For a recent run of a named job
databricks jobs list --output json | grep -i "<job-name>"
databricks jobs get-run <run-id> --output json
```

**Step 1.2** — Identify the Spark application ID from the run output. Look for
`spark_context_id` or navigate to the cluster's Spark UI.

**Step 1.3** — Get the cluster configuration:

```bash
databricks clusters get <cluster-id> --output json
```

Record:
- `num_workers` (or `autoscale.min_workers` / `max_workers`)
- `node_type_id` → look up cores and memory per node
- `spark_version` → determines AQE/Photon defaults
- `spark_conf` → any existing overrides
- `runtime_engine` → PHOTON or STANDARD
- **Single-node detection:** If `spark_conf` contains
  `"spark.databricks.cluster.profile": "singleNode"` or `num_workers` is 0,
  this is a single-node cluster. Read `total_cores` from the `spark.master`
  value (e.g., `local[*, 4]` → 4 cores). Do not use `num_workers × cores`
  as that yields zero.

**Step 1.4** — Direct the user to the Spark UI for the run:
- Workspace URL → Compute → Cluster → Spark UI → Completed Applications
- Or: Job Run → Click "View Spark UI" in the run output panel

Ask the user to share (screenshot or copy-paste):
- **Stages tab**: sorted by Duration (descending) — find the slowest stage(s)
- **Stage detail**: for the slowest stage, get the task metrics summary

### Phase 2: Diagnose — Read the Metrics

From the Spark UI stage detail, extract these metrics:

```
Stage ID:           ___
Duration:           ___
Tasks:              ___ total, ___ succeeded, ___ failed
Shuffle Read:       ___
Shuffle Write:      ___
Spill (Memory):     ___
Spill (Disk):       ___
Input Size:         ___
Output Size:        ___
```

**Task duration distribution** (from the stage's Task Metrics section):
```
Min:    ___
25th:   ___
Median: ___
75th:   ___
Max:    ___
```

**Key diagnostic signals:**

| Signal | What to look for |
|---|---|
| **Skew** | Max task >> 2× Median, or 75th percentile >> Median |
| **Spill** | Spill (Disk) > 0, especially if Spill/Shuffle Read > 0.1 |
| **Shuffle excess** | Shuffle Read > 5 GB with default 200 partitions |
| **Small file I/O** | Input Size small but many tasks (thousands of tiny tasks) |
| **GC pressure** | GC Time / Task Time > 10% (visible in executor tab) |
| **Redundant shuffle** | Multiple Exchange nodes in the query plan with the same or overlapping partition keys; or a `repartition()` immediately before a `groupBy`/`join` on the same key |

### Phase 3: Classify the Bottleneck

Based on Phase 2 metrics, classify into one or more categories:

**Decision tree:**

```
Are there multiple shuffle stages on the same key (or repartition before groupBy/join)?
├── YES → REDUNDANT SHUFFLE (go to Fix G)
└── NO  → Continue below

Is Shuffle Read > 1 GB?
├── YES → Are tasks skewed (Max > 2× Median)?
│   ├── YES → DATA SKEW (go to Fix A)
│   └── NO  → SHUFFLE PARTITION TUNING (go to Fix B)
└── NO  → Is Spill (Disk) > 0?
    ├── YES → MEMORY PRESSURE (go to Fix C)
    └── NO  → Is there a join with a small table (< 100 MB)?
        ├── YES → BROADCAST JOIN (go to Fix D)
        └── NO  → Check AQE settings (Fix E) and Photon (Fix F)
```

Multiple categories can apply simultaneously. Address them in order of impact
(largest time savings first).

### Phase 4: Apply Targeted Fixes

> **⚠️ MANDATORY STOPPING POINT**: Present the diagnosis and proposed fix(es)
> to the user before modifying any code or cluster configuration. Get explicit
> confirmation.

#### Fix A: Data Skew

**Symptoms:** One or a few tasks take 10×–100× longer than the median.

> **Before salting:** Check if the smaller side of the join is < 100 MB. If so,
> a broadcast join (Fix D) is simpler and more effective than salting. Only use
> salting when both sides are too large to broadcast.

**Option A1 — Salting (preferred for join skew when both sides are large):**

```python
from pyspark.sql import functions as F

salt_buckets = 16  # Start with 16, increase if skew persists

# Salt the skewed side
df_skewed = df_skewed.withColumn(
    "salt", (F.rand() * salt_buckets).cast("int")
)

# Explode the other side to match
df_other = df_other.crossJoin(
    spark.range(salt_buckets).withColumnRenamed("id", "salt")
)

# Join on original key + salt
result = df_skewed.join(df_other, ["join_key", "salt"]).drop("salt")
```

**Option A2 — Repartition before aggregation:**

```python
# If skew is in groupBy, repartition with more granularity
df = df.repartition(500, "skewed_key", "secondary_key")
result = df.groupBy("skewed_key").agg(...)
```

**Option A3 — AQE skew join (DBR 14.0+ default, enable on older):**

```python
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes", "256m")
spark.conf.set("spark.sql.adaptive.skewJoin.skewedPartitionFactor", "5")
```

#### Fix B: Shuffle Partition Tuning

**Symptoms:** Default 200 partitions with multi-GB shuffle data → either too
few partitions (large tasks, possible OOM) or too many (tiny tasks, overhead).

```python
# Calculate optimal partition count
shuffle_data_mb = <shuffle_read_mb_from_spark_ui>
# For single-node: use driver cores from spark.master (e.g., local[*, 4] → 4)
# For multi-node: num_workers * cores_per_worker
total_cores = <num_workers * cores_per_worker>  # or driver cores if single-node
target_partition_mb = 128

optimal = max(
    total_cores,
    int((shuffle_data_mb / target_partition_mb / total_cores) + 1) * total_cores
)

spark.conf.set("spark.sql.shuffle.partitions", str(optimal))
```

**With AQE (preferred on DBR 12.2+):**

```python
# Let AQE auto-coalesce, but set a reasonable upper bound
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.initialPartitionNum", "2048")
spark.conf.set("spark.sql.adaptive.advisoryPartitionSizeInBytes", "128m")
```

This sets a high initial count and lets AQE coalesce down to the right size.

#### Fix C: Spill / Memory Pressure

**Symptoms:** Spill (Disk) > 0, slow tasks due to disk I/O.

**Option C1 — Increase partitions (reduce data per task):**

```python
# More partitions = less data per task = less spill
current_partitions = spark.conf.get("spark.sql.shuffle.partitions")
spark.conf.set("spark.sql.shuffle.partitions", str(int(current_partitions) * 2))
```

**Option C2 — Increase executor memory:**

```python
# Cluster config: increase worker instance type or set:
spark.conf.set("spark.executor.memory", "8g")      # up from default
spark.conf.set("spark.executor.memoryOverhead", "2g")
```

**Option C3 — Reduce memory pressure in code:**

```python
# Avoid collect() on large datasets
# Use mapInPandas/applyInPandas with smaller batch sizes
# Cache only what you re-use (and unpersist when done)
df.cache()
# ... use df multiple times ...
df.unpersist()
```

#### Fix D: Broadcast Join

**Symptoms:** A join where one side is < 100 MB but Spark does a sort-merge join.

```python
from pyspark.sql import functions as F

# Option 1: Hint (most explicit)
result = large_df.join(F.broadcast(small_df), "join_key")

# Option 2: Raise the auto-threshold
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "100m")
```

**Check current plan:**

```python
large_df.join(small_df, "key").explain(True)
# Look for BroadcastHashJoin vs SortMergeJoin in the physical plan
```

**Caution:** Broadcasting tables > 1 GB can cause driver OOM. Stay under 1 GB
unless driver has 16+ GB memory.

#### Fix E: AQE Configuration

**Symptoms:** Generic slowness, suboptimal join strategies, inefficient partition
counts — and AQE is not enabled or misconfigured.

```python
# Full AQE configuration block
spark.conf.set("spark.sql.adaptive.enabled", "true")
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")
spark.conf.set("spark.sql.adaptive.skewJoin.enabled", "true")
spark.conf.set("spark.sql.adaptive.localShuffleReader.enabled", "true")

# Verify AQE is active
spark.conf.get("spark.sql.adaptive.enabled")
```

**Verify AQE is working** — in the query plan, look for `AdaptiveSparkPlan`
nodes. If you see `isFinalPlan=false`, the plan is still adaptive.

#### Fix F: Photon Evaluation

**Symptoms:** CPU-bound stages (low shuffle, low I/O wait, high computation
time) on a non-Photon runtime.

**Check current engine:**

```bash
databricks clusters get <cluster-id> | grep runtime_engine
```

**Enable Photon:**

```json
{
  "runtime_engine": "PHOTON",
  "spark_version": "15.4.x-photon-scala2.12"
}
```

**When Photon helps most:**
- Scan-heavy queries (Parquet/Delta reads)
- Aggregations and joins
- String operations

**When Photon doesn't help:**
- UDF-heavy workloads (Python UDFs bypass Photon)
- Streaming micro-batches with minimal per-batch data
- Workloads already bottlenecked on shuffle I/O

**Cost consideration:** Photon uses 2x DBU rate. The break-even point is a
50% wall-clock reduction (2x cost but half the time = same DBUs). Only enable
Photon when benchmarks show > 50% speedup, or when the faster runtime lets
you downsize the cluster (fewer/smaller nodes). See Phase 5b for the full
cost impact calculation after applying this fix.

#### Fix G: Redundant Shuffle

**Symptoms:** The query plan shows multiple Exchange (shuffle) nodes on the same
or overlapping keys. Common pattern: calling `repartition()` right before a
`groupBy()` or `join()` on the same column — Spark will shuffle twice when once
would suffice.

**How to detect:**

```python
# Check the physical plan for Exchange nodes
df.explain(True)
# Count Exchange nodes — more than one on the same key is suspicious
```

In the Spark UI, look for back-to-back shuffle stages where the partition key
is the same.

**Fix — remove the redundant repartition:**

```python
# BAD: double shuffle
df.repartition(500, "category").groupBy("category").agg(...)

# GOOD: let groupBy handle the shuffle
df.groupBy("category").agg(...)
```

**When repartition IS appropriate:**
- Before writing partitioned output: `df.repartition("date").write.partitionBy("date")`
- To fix skew before a `groupBy` — but use a secondary key (see Fix A, Option A2)
- To increase parallelism when input has too few partitions

**Rule of thumb:** If a `repartition()` is immediately followed by `groupBy()`
or `join()` on the same key, remove it. Spark will shuffle to the right layout
as part of the aggregation or join.

### Phase 5: Validate the Fix

After applying changes:

**Step 5.1** — Re-run the same job or query:

```bash
databricks jobs run-now <job-id>
# Or re-execute the notebook/query
```

**Step 5.2** — Compare before/after metrics:

```
Metric              Before      After       Δ
─────────────────────────────────────────────
Stage Duration      ___         ___         ___
Shuffle Read        ___         ___         ___
Spill (Disk)        ___         ___         ___
Max Task Duration   ___         ___         ___
Task Skew Ratio     ___         ___         ___
Total Job Time      ___         ___         ___
```

**Step 5.3** — Verify no regressions:
- Other stages didn't get slower
- No new OOM errors
- Output row counts match the original run

### Phase 5b: Estimate Cost Impact

You have the cluster ID from Phase 1.3 and the before/after durations from
Phase 5.2. Use those to compute actual DBU savings. Execute each step — do
not leave blanks for the user to fill in.

**Step 5b.1** — Get the job's run frequency. Run this to determine how often
the job executes:

```bash
# Get the last 10 runs to calculate average frequency
databricks jobs list-runs --job-id <job_id> --limit 10 --output json
```

From the output, extract `start_time` timestamps and calculate the average
interval between runs. Convert to `runs_per_month`. If the job is ad-hoc
(irregular schedule), ask the user how often it typically runs.

**Step 5b.2** — Query historical DBU consumption. Try `system.billing.usage`
first (requires Unity Catalog). Run this SQL via a SQL warehouse or ask the
user to execute it in a Databricks SQL notebook:

```sql
SELECT
    usage_date,
    sku_name,
    SUM(usage_quantity) AS total_dbus,
    COUNT(*)            AS record_count
FROM system.billing.usage
WHERE usage_metadata.cluster_id = '<cluster_id>'
  AND usage_date >= CURRENT_DATE - INTERVAL 30 DAYS
GROUP BY usage_date, sku_name
ORDER BY usage_date DESC
```

From the results, compute `avg_dbus_per_run` = total DBUs / number of runs
in the period.

**Fallback (if `system.billing.usage` is unavailable):** When UC is not
enabled or the user lacks access to billing tables, estimate DBUs from the
cluster configuration and job runtime:

```
total_nodes       = 1 (driver) + num_workers
dbu_rate_per_hour = total_nodes × <DBU rate for instance type>
run_hours         = run_duration_seconds / 3600
est_dbus_per_run  = dbu_rate_per_hour × run_hours
```

To find the DBU rate per node, run `databricks clusters list-node-types` and
look up the instance type, or ask the user. Common approximate rates for Jobs
Compute (Standard tier):
- General purpose (D-series): ~0.75–1.5 DBU/hour per node
- Memory optimized (E-series): ~1.0–2.0 DBU/hour per node
- Compute optimized (F-series): ~0.5–1.0 DBU/hour per node

Flag in the output that this is a runtime-based estimate, not actual billing
data. Recommend the user enable UC or check the Databricks account console
for precise numbers.

**Step 5b.3** — Compute the savings. Using the before/after Total Job Time
from the Phase 5.2 comparison table and `dbus_per_run` from Step 5b.2 (from
billing query or fallback estimate):

```
runtime_reduction_pct = (before_duration - after_duration) / before_duration
est_dbus_after        = dbus_per_run × (1 - runtime_reduction_pct)
dbu_saved_per_run     = dbus_per_run - est_dbus_after
monthly_dbu_saved     = dbu_saved_per_run × runs_per_month
annual_dbu_saved      = monthly_dbu_saved × 12
```

If the fix involved enabling Photon (Fix F), apply the 2x DBU rate adjustment:

```
photon_adjusted_dbu_after = est_dbus_after × 2
net_dbu_change = photon_adjusted_dbu_after - dbus_per_run
```

If `net_dbu_change > 0`, Photon is costing more DBUs than it saves. Flag this
to the user and recommend reverting to STANDARD runtime with the other fixes
applied instead.

> **Note:** The runtime-to-DBU relationship is linear for compute-bound
> workloads on fixed-size clusters. For autoscaling clusters or I/O-bound
> jobs, actual savings may differ. Recommend the user verify against real
> billing data after 3–5 post-fix runs.

**Step 5b.4** — Present the filled-in cost impact summary to the user:

```
Cost Impact Estimate
────────────────────────────────────────────────────────
Data source:             billing.usage / runtime estimate
Runtime reduction:       <calculated>% (<before>s → <after>s)
DBUs per run (before):   <from billing or estimate>
DBUs per run (after):    <calculated>
DBU savings per run:     <calculated>
Job frequency:           <N> runs/month
Monthly DBU savings:     <calculated>
Annual DBU savings:      <calculated>
Photon premium applied:  YES / NO
────────────────────────────────────────────────────────
```

> DBU savings are expressed in units, not dollars — actual dollar impact
> depends on pricing tier, commitment level, and cloud provider. For full
> cost analysis including instance right-sizing and budget governance, hand
> off to the `databricks-cost-optimization` skill.

### Phase 6: Harden the Fix

> **⚠️ MANDATORY STOPPING POINT**: Confirm with the user whether to persist
> settings at cluster level, job level, or notebook level before making changes.

**Option 1 — Notebook-level (most portable):**

```python
# Add to the top cell of the notebook
spark.conf.set("spark.sql.shuffle.partitions", "416")
spark.conf.set("spark.sql.adaptive.enabled", "true")
# ... other settings
```

**Option 2 — Job-level (via DAB or API):**

```yaml
# In databricks.yml (DAB)
resources:
  jobs:
    my_job:
      tasks:
        - task_key: etl
          new_cluster:
            spark_conf:
              spark.sql.shuffle.partitions: "416"
              spark.sql.adaptive.enabled: "true"
```

Use the `databricks-automation-bundles` skill for full DAB configuration.

**Option 3 — Cluster policy (admin-level):**

```bash
databricks cluster-policies create --json '{
  "name": "perf-tuned-policy",
  "definition": {
    "spark_conf.spark.sql.shuffle.partitions": { "type": "fixed", "value": "416" },
    "spark_conf.spark.sql.adaptive.enabled": { "type": "fixed", "value": "true" }
  }
}'
```

## Stopping Points

This skill includes mandatory stopping points at:

1. **Phase 1** — Before pulling metrics: confirm the correct job/run with the user
2. **Phase 4** — Before applying fixes: present diagnosis and get approval
3. **Phase 6** — Before hardening: confirm persistence scope (notebook/job/cluster)

Never apply Spark configuration changes or modify user code without explicit
user confirmation.

## Troubleshooting

| Problem | Likely Cause | Fix |
|---|---|---|
| `spark.sql.shuffle.partitions` ignored | AQE coalesce overriding | Set `coalescePartitions.minPartitionNum` to your target |
| Broadcast join OOM on driver | Table > driver memory | Lower `autoBroadcastJoinThreshold` or use sort-merge |
| Salting didn't help | Skew is in aggregation, not join | Use `repartition()` before `groupBy` instead |
| AQE not activating | Exchange reuse preventing re-optimization | Set `spark.sql.adaptive.forceApply=true` for testing |
| Photon slower than standard | UDF-heavy workload | Photon can't accelerate Python UDFs — keep STANDARD |
| Spill persists after partition increase | Executor memory too low for data volume | Upgrade instance type or add workers |
| Job slower after tuning | Over-partitioned — too many small tasks | Reduce partition count, aim for 128 MB per partition |
| `java.lang.OutOfMemoryError` | Executor memory exhausted | Increase `spark.executor.memory` + `memoryOverhead` |
| Skew join not triggered by AQE | Skew factor below threshold | Lower `skewedPartitionFactor` (default 5 → try 2) |
| Redundant repartition not obvious | Plan shows multiple Exchanges | Run `df.explain(True)` and count Exchange nodes on same key |

## Cross-References

- **`databricks-cost-optimization` skill** — for deeper cost analysis: billing audits, instance right-sizing, spot instance savings, and budget governance
- **`databricks-cli` skill** — for all `databricks` CLI commands used in this workflow
- **`databricks-etl-pyspark-notebooks` skill** — when the fix requires restructuring ETL pipeline code
- **`databricks-automation-bundles` skill** — when hardening fixes into DAB job definitions
- **`databricks-notebook-refactor` skill** — when performance fix requires extracting code into modules

## Output

After completing the workflow, you should have:

1. **Diagnosis report** — which stages are slow and why (with metrics)
2. **Applied fix** — specific configuration changes or code modifications
3. **Before/after comparison** — metric deltas proving the improvement
4. **Cost impact estimate** — DBU savings per run, monthly, and annual projections
5. **Hardened settings** — persisted at the appropriate scope

Format the diagnosis as a markdown summary the user can paste into a PR
description or Jira ticket.
