# Monitoring & Troubleshooting

## Snowsight Notebook: Cluster Management

**These APIs ONLY work in Snowsight Container Runtime notebooks. Do NOT use in ML Jobs.**

ML Jobs automatically get compute resources from the compute pool - they don't need or support `scale_cluster()`.

### Dynamic Cluster Scaling (Notebooks Only)

```python
from snowflake.ml.runtime_cluster import scale_cluster

# Scale up before distributed workload
scale_cluster(expected_cluster_size=3)  # 1 head + 2 workers

# Run distributed job...
# ...

# Scale down when done
scale_cluster(expected_cluster_size=1)
```

**Advanced options:**
```python
scale_cluster(
    expected_cluster_size=5,
    is_async=False,  # True = return immediately without waiting for full cluster
    options={
        "rollback_after_seconds": 720,       # Auto-rollback if scaling doesn't complete
        "block_until_min_cluster_size": 3,   # Return when at least 3 nodes are ready
    }
)
```

### Cluster Monitoring APIs (Notebooks Only)

```python
from snowflake.ml.runtime_cluster.cluster_manager import (
    get_cluster_size,
    get_nodes,
    get_available_cpu,
    get_available_gpu,
    get_num_cpus_per_node,
    get_ray_dashboard_url,
    get_grafana_dashboard_url,
)

# Current cluster info
print(f"Cluster size: {get_cluster_size()}")       # Number of alive nodes
print(f"Nodes: {get_nodes()}")                     # List of node details
print(f"Available CPUs: {get_available_cpu()}")   # Free CPUs in cluster
print(f"Available GPUs: {get_available_gpu()}")   # Free GPUs in cluster
print(f"CPUs per node: {get_num_cpus_per_node()}") # CPUs on each node

# Dashboard URLs
print(f"Ray Dashboard: {get_ray_dashboard_url()}")
print(f"Grafana Dashboard: {get_grafana_dashboard_url()}")
```

---

## Notebooks (Container Runtime): Dashboard Monitoring

**Dashboards are ONLY available in Snowsight Notebooks with Container Runtime. ML Jobs do not have dashboard access.**

**Ray Dashboard** - Task-level monitoring:
```python
from snowflake.ml.runtime_cluster import get_ray_dashboard_url

# Get URL and open in browser
url = get_ray_dashboard_url()
print(f"Open: {url}")
```

**What to check in Ray Dashboard:**
| Tab | What It Shows | Use For |
|-----|---------------|---------|
| Jobs | Active/completed jobs | Overall job status |
| Actors | Worker actors, state, memory | Actor failures, memory per worker |
| Tasks | Individual task status, errors | Find which partition failed |
| Logs | Per-worker logs | Debug specific worker errors |
| Cluster | Node status, resources | Verify all nodes joined |

**Grafana Dashboard** - Resource utilization:
```python
from snowflake.ml.runtime_cluster.cluster_manager import get_grafana_dashboard_url

url = get_grafana_dashboard_url()
print(f"Open: {url}")
```

**What to check in Grafana:**
| Panel | What It Shows | Red Flags |
|-------|---------------|-----------|
| CPU Usage | Per-node CPU % | Sustained 100% = CPU bottleneck |
| Memory Usage | Per-node memory | Near 100% = OOM risk |
| Network I/O | Data transfer between nodes | High = data shuffle overhead |
| GPU Utilization | GPU % (if applicable) | Low % = GPU underutilized |

---

## ML Jobs: Monitoring and Logs

**Python:**
```python
from snowflake.ml.jobs import get_job

job = get_job("<JOB_ID>", session=session)
print(f"Status: {job.status}")  # PENDING, RUNNING, DONE, FAILED

# Application logs (filtered to stdout/stderr from your script)
print(job.get_logs())
print(job.get_logs(instance_id=0))    # Head node
print(job.get_logs(instance_id=1))    # Worker 1
```

**SQL:**
```sql
-- Check instance status across all nodes
CALL SYSTEM$GET_SERVICE_STATUS('<DB>.<SCHEMA>.<JOB_ID>');

-- Get logs from a specific instance (0 = head, 1+ = workers)
CALL SYSTEM$GET_SERVICE_LOGS('<DB>.<SCHEMA>.<JOB_ID>', <instance_id>, 'main', 500);

-- List all running jobs in schema
SHOW SERVICES IN SCHEMA <DB>.<SCHEMA>;

-- Kill a running/stuck job
DROP SERVICE <DB>.<SCHEMA>.<JOB_ID>;
```

> **Note:** `SYSTEM$GET_SERVICE_LOGS` may include infrastructure logs (Grafana, Ray) alongside application output. `job.get_logs()` filters to application output only. For DPF jobs, per-partition `train.log` files on the output stage contain the most detailed per-partition logs.

**Getting progress from ML Job logs:** When DPF/MMT runs inside an ML Job, `dpf_run.get_progress()` and `dpf_run.wait()` are only available inside the running script -- not from the outside. To monitor progress externally:
1. Your script should print progress to stdout (e.g., `print(dpf_run.get_progress())`), then read it via `job.get_logs()` or `SYSTEM$GET_SERVICE_LOGS`.
2. For DPF, you can restore a read-only run handle from the run ID to check progress and partition details:
   ```python
   from snowflake.ml.modeling.distributors.distributed_partition_function.dpf_run import DPFRun
   restored = DPFRun.restore_from("<RUN_ID>", "<STAGE_NAME>")
   restored.get_progress()        # {"DONE": [...], "FAILED": [...]}
   restored.partition_details     # Per-partition status
   ```

---

## OOM (Out of Memory) Troubleshooting

**Symptoms:**
- Job fails with status `FAILED` or `INTERNAL_ERROR`
- Logs show: `OutOfMemoryError`, `MemoryError`, `Killed`, or `signal 9`

**Diagnosis workflow:**

1. **Check logs for OOM indicators:**
   - **ML Jobs**: `job.get_logs()` — look for `OutOfMemoryError`, `MemoryError`, `Killed`, or `signal 9`
   - **Notebooks**: Check Grafana dashboard (see above) for memory spiking to 100%
   
   For partitioned workloads (DPF/MMT), check which partition failed by looking for partition identifiers before the error. For estimators, look for OOM during data loading or gradient computation. For HPO/Tuner, check which trial failed — larger hyperparameter values (e.g., more trees, deeper models) consume more memory.

2. **Check memory usage** (Notebooks only - use Grafana dashboard):
   - Memory spiking to 100% before failure = OOM confirmed
   - Identify which node(s) hit the limit

3. **Check partition data sizes:**
   ```python
   # Find the largest partitions
   session.sql("""
       SELECT STORE_ID, COUNT(*) as rows, 
              SUM(LENGTH(TO_VARCHAR(*))) / 1e6 as approx_mb
       FROM MY_TABLE
       GROUP BY STORE_ID
       ORDER BY rows DESC
       LIMIT 10
   """).show()
   ```

**Solutions (in order of preference):**

| Solution | When to Use | How |
|----------|-------------|-----|
| Increase CPUs per worker | Workers competing for memory | `num_cpus_per_worker=4` (fewer workers = more memory each) |
| Use larger instance | All workers need more memory | Switch to a high-memory instance family (see `../references/compute-pool-sizing.md`) |
| Filter/sample data | Data too large for any instance | Reduce rows per partition before training |
| Process in batches | Loading all data at once | Use chunked reading in your function |
| Exclude outlier partitions | One partition is much larger | Pre-filter extreme partitions |

**Example fix - increase memory per worker:**

Increase CPUs per worker/trial — fewer workers means more memory each. See the relevant sub-skill for the exact parameter: `num_cpus_per_worker` (DPF/MMT), `num_cpu_per_worker` (Estimators), `resource_per_trial` (Tuner).

**Example fix - upgrade instance family:**
```sql
ALTER COMPUTE POOL MY_POOL SET INSTANCE_FAMILY = HIGHMEM_X64_M;
```

---

## Common Errors and Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: snowflake.ml.modeling.distributors` | Running locally instead of server-side | Submit via ML Jobs or use Container Runtime notebook |
| `No active session` | Session not initialized in script | Use `get_active_session()` at start of script |
| `Compute pool busy` | Pool at max capacity | Wait, or increase `MAX_NODES` on pool |
| `PENDING` indefinitely | Pool suspended or no capacity | Check pool status: `SHOW COMPUTE POOLS` |
| `Task timed out` | Partition processing took too long | Increase timeout or reduce partition size |
| `Actor died unexpectedly` | OOM or unhandled exception | Check logs, increase memory, add error handling |
| `Connection reset` | Network issue between nodes | Retry job, or check compute pool health |
| `Ray cluster not found` | Container Runtime not enabled | Enable Container Runtime in notebook settings |
| Distributor missing, unexpected signature, or feature unavailable | Container Runtime image older than feature requires (image version is separate from `snowflake-ml-python`) | Check image version: `from snowflake.runtime._version import __version__; print(__version__)` and compare to feature requirements |

---

## Debugging Checklist

**Job stuck in PENDING:**
```sql
-- Check compute pool status
SHOW COMPUTE POOLS LIKE 'MY_POOL';
-- Look at: state (ACTIVE?), active_nodes, max_nodes
```

**Job fails immediately:**
```python
# Get verbose logs including startup
logs = job.get_logs(verbose=True)
# Look for: import errors, missing packages, auth issues
```

**Some partitions fail, others succeed:**
```python
# With fail_fast=False (default), job continues after failures
# Check which partitions failed:
run_result = dpf_run.wait()
# Examine logs for "failed" or "error" patterns
```

**Performance is slow:**
1. Check Grafana for CPU/memory bottlenecks (Notebooks only)
2. Check Ray Dashboard for task queuing (Notebooks only)
3. For ML Jobs: analyze logs for slow partitions
4. Consider: more nodes, larger instances, or fewer CPUs per worker (more parallelism)
