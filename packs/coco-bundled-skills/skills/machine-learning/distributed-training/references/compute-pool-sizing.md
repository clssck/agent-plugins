# Compute Pool Sizing Guide

## Instance Families

Run `SHOW COMPUTE POOL INSTANCE FAMILIES IN ACCOUNT;` to check availability in your account.

**CPU (General Purpose):**

| Family | vCPUs | Memory (GiB) |
|--------|-------|--------------|
| `CPU_X64_XS` | 1 | 6 |
| `CPU_X64_S` | 3 | 13 |
| `CPU_X64_M` | 6 | 28 |
| `CPU_X64_SL` | 14 | 54 |
| `CPU_X64_L` | 28 | 116 |

**High Memory:**

| Family | vCPUs | Memory (GiB) | Availability |
|--------|-------|--------------|--------------|
| `HIGHMEM_X64_S` | 6 | 58 | All clouds |
| `HIGHMEM_X64_M` | 28 | 240-244 | All clouds |
| `HIGHMEM_X64_SL` | 92 | 654 | Azure, GCP |
| `HIGHMEM_X64_L` | 124 | 984 | AWS only |

**GPU (AWS):**

| Family | vCPUs | Memory (GiB) | GPUs |
|--------|-------|--------------|------|
| `GPU_NV_S` | 6 | 27 | 1x A10G (24 GB) |
| `GPU_NV_M` | 44 | 178 | 4x A10G (24 GB) |
| `GPU_NV_L` | 92 | 1112 | 8x A100 (40 GB) |

**GPU (Azure):**

| Family | vCPUs | Memory (GiB) | GPUs |
|--------|-------|--------------|------|
| `GPU_NV_XS` | 3 | 26 | 1x T4 (16 GB) |
| `GPU_NV_SM` | 32 | 424 | 1x A10 (24 GB) |
| `GPU_NV_2M` | 68 | 858 | 2x A10 (24 GB) |
| `GPU_NV_3M` | 44 | 424 | 2x A100 (80 GB) |
| `GPU_NV_SL` | 92 | 858 | 4x A100 (80 GB) |

---

## CPUs per Worker

The parameter name varies by API (`num_cpus_per_worker` in ExecutionOptions, `num_cpu_per_worker` in ScalingConfig).

```
workers_per_node = node_vCPUs / cpus_per_worker
memory_per_worker = node_memory / workers_per_node
```

| Scenario | CPUs per worker | Why |
|----------|----------------|-----|
| Few partitions or long-running tasks (minutes+) | Default (None) -- 1 worker per node | Each partition gets full node resources. Node wait time is amortized. |
| Many short tasks (seconds each) | Set to 1 -- pack workers onto nodes | Fewer nodes needed. Avoids waiting for a large cluster to provision. |
| Task needs multi-threaded CPU | Match to thread count (e.g., 4) | Gives each worker enough CPUs. Also increases memory per worker. |
| OOM errors | Increase CPUs per worker | Fewer workers = more memory each. Or switch to HIGHMEM instance. |

> **Rule of thumb**: Consider `node_availability_time + (function_time × partitions / total_workers)`. Packing more workers onto fewer nodes is often faster end-to-end than waiting for a large cluster to provision.

---

## Sizing by Workload Type

### DPF / MMT (partition-parallel)

- **Node count**: `max_nodes = ceil(num_partitions / workers_per_node)` gives full parallelism, but workers batch through partitions -- you rarely need this many. Start with fewer nodes and scale up if wall time is too long.
- **Instance family**: Pick so that `memory_per_worker` exceeds partition size. Rough estimate: `table_bytes / num_partitions`, multiplied by 2-5x for pandas overhead.
- **50 nodes is recommended as the maximum** for most workloads. See "Scaling Beyond Defaults" if you need more.

**Examples:**

| Workload | Partitions | Function time | Instance | CPUs/worker | Nodes | Why |
|----------|-----------|---------------|----------|-------------|-------|-----|
| Quick sklearn fits | 500 | ~5s each | CPU_X64_S (3 vCPU) | 1 | 3-5 | Pack workers. 3 workers/node × 5 nodes = 15 concurrent. Not worth waiting for more nodes. |
| Medium XGBoost per-store | 50 | ~2 min each | CPU_X64_M (6 vCPU) | 2 | 10 | 3 workers/node × 10 nodes = 30 concurrent. ~4 min total. |
| Heavy per-partition training | 10 | ~30 min each | CPU_X64_L (28 vCPU) | None (default) | 10 | 1 partition per node, full resources. Node wait time amortized over long run. |
| Large data per partition (OOM risk) | 20 | ~10 min each | HIGHMEM_X64_M (28 vCPU) | None (default) | 10-20 | Memory-bound. 1 worker per node = ~240 GiB each. |
| GPU deep learning per partition | 8 | ~20 min each | GPU_NV_S (1 GPU) | None (default) | 8 | 1 GPU task per node. |

### Estimators (XGBoost / LightGBM)

These train a single model across all workers. Ray auto-shards the data and coordinates gradient updates.

- Defaults auto-configure workers based on available CPUs/GPUs. More/bigger nodes = faster training.
- Override with `XGBScalingConfig(num_workers=N, num_cpu_per_worker=M)` or `LightGBMScalingConfig(...)` for explicit control.
- GPU mode: set `use_gpu=True`. Each GPU gets one worker.
- For large datasets, use `CPU_X64_L` or `HIGHMEM_X64_M` for more memory per node.

### PyTorch DDP

- GPU-based. Pick GPU instance family based on model size (weights + optimizer state + batch).
- 2-8 GPU nodes is typical. Scale nodes for training speed.

### HPO / Tuner

Same sizing as partitioned workloads -- each trial runs on a worker, trials batch when resources are full.

- Ensure compute pool has enough total resources for `max_concurrent_trials × resource_per_trial`.
- **GridSearch warning**: Evaluates every combination. 5 params × 5 values = 3,125 trials (5^5), not 25. Consider RandomSearch or BayesOpt for large search spaces.

---

## Scaling Beyond Defaults

- 50 nodes is recommended as the maximum for most workloads, but it is not a hard account limit.
- Some instance families (especially GPU) may have limited availability and take longer to provision.
- If you need more nodes, hit node limit errors, or encounter capacity constraints, contact your **Snowflake account representative or Snowflake Support**.

---

## Create Compute Pool Examples

```sql
-- DPF/MMT: CPU workload
CREATE COMPUTE POOL MY_DPF_POOL
    MIN_NODES = 1
    MAX_NODES = 50
    INSTANCE_FAMILY = CPU_X64_S
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 3600;

-- Deep learning: GPU workload
CREATE COMPUTE POOL MY_GPU_POOL
    MIN_NODES = 1
    MAX_NODES = 4
    INSTANCE_FAMILY = GPU_NV_M
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 3600;

-- Large data per partition: high memory
CREATE COMPUTE POOL MY_HIGHMEM_POOL
    MIN_NODES = 1
    MAX_NODES = 10
    INSTANCE_FAMILY = HIGHMEM_X64_M
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 3600;
```
