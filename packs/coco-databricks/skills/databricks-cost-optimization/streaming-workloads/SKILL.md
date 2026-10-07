---
name: streaming-workloads-cost
description: "Optimize Databricks streaming and workload design costs. Triggers: streaming cost, always-on, triggered streaming, availableNow, Delta optimization, OPTIMIZE, VACUUM, Z-ORDER, liquid clustering, runtime version, batch vs streaming, continuous vs triggered, 24/7 compute, streaming freshness."
parent_skill: databricks-cost-optimization
---

# Streaming & Workload Design Cost Optimization

## When to Load

Parent skill routes here when the user wants to:
- Reduce always-on streaming costs
- Choose between continuous, triggered, and batch processing
- Optimize Delta Lake table maintenance for cost savings
- Evaluate runtime versions for performance/cost improvements

## Prerequisites

- Databricks CLI authenticated
- Access to streaming job configurations
- Unity Catalog enabled for billing queries

## Workflow

### Step 1: Audit Streaming Spend

**1.1** — Identify always-on streaming jobs (high DBU consumers):

```sql
SELECT
  workspace_id,
  usage_metadata.cluster_id,
  usage_metadata.job_id,
  sku_name,
  SUM(usage_quantity) AS total_dbus,
  COUNT(DISTINCT usage_date) AS active_days
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
  AND (sku_name LIKE '%JOB%' OR sku_name LIKE '%ALL_PURPOSE%')
GROUP BY 1, 2, 3, 4
HAVING active_days >= 25
ORDER BY total_dbus DESC
LIMIT 20
```

Jobs active 25+ of 30 days are likely always-on streaming.

**1.2** — Get job details for top consumers:

```bash
databricks jobs get <job-id> --output json | jq '{name: .settings.name, schedule: .settings.schedule, trigger: .settings.trigger}'
```

> **⚠️ MANDATORY STOPPING POINT**: Present streaming jobs and their costs.
> Confirm which ones to evaluate for triggered processing.

### Step 2: Always-On vs Triggered Streaming

Not every streaming use case requires 24/7 compute.

**Decision guide:**

| Freshness Requirement | Approach | Cost Profile |
|---|---|---|
| Sub-minute (real-time dashboards, fraud) | Always-on streaming | 24/7 compute |
| Minutes to hours (reporting, analytics) | Triggered streaming (`availableNow`) | Pay per run |
| Hours to daily (batch reporting) | Scheduled batch job | Pay per run |

**Triggered streaming with `availableNow`:**

```python
(spark.readStream
  .format("delta")
  .table("source_table")
  .writeStream
  .trigger(availableNow=True)
  .format("delta")
  .option("checkpointLocation", "/checkpoints/my_pipeline")
  .toTable("target_table")
)
```

`availableNow=True` processes all accumulated data in one batch, then stops.
The checkpoint tracks progress, so the next run picks up where it left off.

**Schedule as a Databricks job** at the needed frequency (hourly, every 4 hours,
daily) instead of running 24/7.

**Cost example:**
- Always-on: 720 hours/month × cluster cost
- Triggered every 4 hours: ~6 runs/day × ~15 min each = ~45 hours/month
- Savings: ~94% compute reduction

**For Lakeflow Declarative Pipelines:** Use `triggered` execution mode instead
of `continuous` for the same benefit:

```json
{
  "continuous": false
}
```

### Step 3: Streaming Autoscaling

Standard cluster autoscaling has limitations scaling down for streaming.

**Recommendations:**
- For Structured Streaming on classic clusters: set conservative `max_workers`,
  accept limited scale-down behavior
- For Lakeflow Declarative Pipelines: use **enhanced autoscaling** which handles
  streaming scale-down properly
- For variable-throughput streams: consider triggered mode (Step 2) over
  autoscaling an always-on stream

### Step 4: Delta Lake Optimization

Faster reads = shorter compute time = lower cost. Delta maintenance is critical.

**4.1 — OPTIMIZE (file compaction):**

```sql
OPTIMIZE catalog.schema.my_table;
```

Compacts small files into larger ones for faster reads. Run after batch writes
or on a schedule.

**4.2 — Z-ORDER (co-locate data for filtering):**

```sql
OPTIMIZE catalog.schema.my_table
  ZORDER BY (frequently_filtered_column);
```

Dramatically speeds up queries with predicates on the Z-ORDERed columns.

**4.3 — Liquid Clustering (DBR 13.3+):**

```sql
ALTER TABLE catalog.schema.my_table
  CLUSTER BY (col1, col2);
```

Replaces Z-ORDER with automatic, incremental clustering. No manual OPTIMIZE
scheduling needed — clustering happens on writes.

**4.4 — VACUUM (remove old files):**

```sql
VACUUM catalog.schema.my_table RETAIN 168 HOURS;
```

Removes files older than retention period to reduce storage costs.

**Maintenance job pattern:**

Schedule OPTIMIZE and VACUUM as a daily/weekly job on a **compute-optimized**
instance (c-series) — these are CPU-bound operations.

```python
tables = ["catalog.schema.table1", "catalog.schema.table2"]
for table in tables:
    spark.sql(f"OPTIMIZE {table}")
    spark.sql(f"VACUUM {table} RETAIN 168 HOURS")
```

### Step 5: Runtime Version Optimization

Newer runtimes include performance improvements that reduce compute time at
no additional cost.

**Audit current runtimes:**

```bash
databricks clusters list --output json | jq '.[].spark_version' | sort | uniq -c | sort -rn
```

```bash
databricks jobs list --all --output json | jq '.[].settings.tasks[]?.new_cluster?.spark_version' | sort | uniq -c | sort -rn
```

Flag anything older than 2 major versions behind current LTS. Upgrade for
free performance gains.

### Step 6: Data Format Optimization

Delta Lake provides significant performance improvements over raw
Parquet/ORC/JSON. Ensure all workloads use Delta:

**Check for non-Delta reads:**

Look for jobs reading `format("parquet")`, `format("json")`, or `format("csv")`
that could be migrated to Delta tables. Delta provides:
- Predicate pushdown and data skipping
- Small file compaction (OPTIMIZE)
- Caching and Z-ORDER/clustering
- ACID transactions (fewer retries)

## Stopping Points

- ✋ After Step 1: present streaming costs, confirm which to evaluate
- ✋ Before Step 2 changes: confirm freshness requirements with stakeholders
- ✋ Before Step 4: confirm Delta maintenance schedule

## Cross-References

- **`databricks-etl-pyspark-notebooks`** — ETL pipeline patterns with Delta
- **`databricks-automation-bundles`** — scheduling triggered streaming jobs via DAB
- **`cluster-compute/SKILL.md`** — cluster sizing for streaming and maintenance jobs
- **`databricks-spark-performance`** — Spark-level tuning for streaming jobs

## Output

1. **Streaming audit** — always-on jobs with cost and freshness analysis
2. **Migration plan** — continuous → triggered conversions with savings estimates
3. **Delta maintenance schedule** — OPTIMIZE/VACUUM/clustering plan
4. **Runtime upgrade plan** — clusters/jobs to upgrade with expected gains
