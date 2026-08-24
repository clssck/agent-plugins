---
name: ml-gpu-compute-cost
description: "Optimize Databricks ML and GPU compute costs. Triggers: GPU cost, unnecessary GPU, ML training cost, model serving cost, deep learning cost, GPU audit, GPU instance, model serving scaling, inference cost, ML compute, training cluster, GPU utilization, Mosaic AI serving."
parent_skill: databricks-cost-optimization
---

# ML & GPU Compute Cost Optimization

## When to Load

Parent skill routes here when the user wants to:
- Audit GPU usage and eliminate unnecessary GPU clusters
- Optimize ML training compute costs
- Right-size model serving endpoints
- Choose between GPU and CPU for ML workloads

## Prerequisites

- Databricks CLI authenticated
- Access to cluster and serving endpoint configurations
- Unity Catalog enabled for billing queries

## Workflow

### Step 1: Audit GPU & ML Spend

**1.1** — GPU and ML-related DBU consumption:

```sql
SELECT
  workspace_id,
  sku_name,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
  AND (sku_name LIKE '%GPU%' OR sku_name LIKE '%ML%' OR sku_name LIKE '%SERVING%')
GROUP BY 1, 2
ORDER BY total_dbus DESC
```

**1.2** — Identify all GPU clusters:

```bash
databricks clusters list --output json | jq '.[] | select(.node_type_id | test("gpu|g4|g5|g6|p3|p4|p5|a10|a100|h100|l4|l40|t4"; "i")) | {cluster_name, cluster_id, node_type_id, num_workers, autoscale, state, spark_version}'
```

**1.3** — Model serving endpoint costs:

```sql
SELECT
  workspace_id,
  usage_metadata.endpoint_id,
  sku_name,
  SUM(usage_quantity) AS total_dbus
FROM system.billing.usage
WHERE usage_date >= DATEADD(DAY, -30, CURRENT_DATE())
  AND sku_name LIKE '%SERVING%'
GROUP BY 1, 2, 3
ORDER BY total_dbus DESC
```

> **⚠️ MANDATORY STOPPING POINT**: Present GPU and ML spend breakdown.
> Confirm which areas to optimize.

### Step 2: GPU Usage Audit

Most workloads do NOT benefit from GPUs. Only these workload types need GPU
acceleration:
- Deep learning training (PyTorch, TensorFlow, Keras)
- GPU-accelerated inference
- Libraries explicitly using CUDA (Rapids, cuML, cuDF)
- LLM fine-tuning

**Workloads that do NOT need GPUs:**
- Spark ETL / SQL transformations
- Traditional ML (scikit-learn, XGBoost on CPU, LightGBM)
- Data exploration and visualization
- Feature engineering

**For each GPU cluster, verify:**

```bash
databricks clusters get <cluster-id> --output json | jq '{cluster_name, node_type_id, spark_version, init_scripts, libraries}'
```

Check installed libraries. If no GPU-accelerated libraries are present
(PyTorch, TensorFlow, Rapids, etc.), recommend switching to CPU instances.

**Recommendation format:**

```
Cluster: <name> (<cluster-id>)
Instance: <gpu-instance-type>
30-day DBUs: <N>
GPU Libraries Found: None / PyTorch / TensorFlow / etc.
Recommendation: Switch to CPU (<equivalent-cpu-instance>)
Estimated savings: 50-80% (GPU premium eliminated)
```

### Step 3: ML Training Optimization

**3.1 — Right-size training clusters:**

| Training Type | Recommended Setup |
|---|---|
| Traditional ML (sklearn, XGBoost) | CPU, memory-optimized, 2-8 workers |
| Single-GPU deep learning | 1 GPU node (single node cluster) |
| Distributed deep learning | Multi-GPU nodes, scale based on model size |
| Hyperparameter tuning | Autoscaling CPU/GPU, use Spark trials |
| LLM fine-tuning | Multi-GPU (A100/H100), sized to model parameters |

**3.2 — Use job compute for training:**

Training jobs should always use job compute, not all-purpose. See
`cluster-compute/SKILL.md` Step 2 for migration guidance.

**3.3 — Spot instances for training:**

ML training (especially hyperparameter tuning) is a good candidate for spot
instances when combined with checkpointing:

```python
# PyTorch checkpointing example
torch.save({
    'epoch': epoch,
    'model_state_dict': model.state_dict(),
    'optimizer_state_dict': optimizer.state_dict(),
    'loss': loss,
}, '/dbfs/checkpoints/model_checkpoint.pt')
```

If a spot instance is evicted, the job retries from the last checkpoint.

**3.4 — Auto termination for training:**

Training clusters should terminate immediately after the job completes.
If using job compute, this happens automatically.

### Step 4: Model Serving Optimization

Mosaic AI Model Serving uses serverless compute with automatic scaling.

**4.1 — Check serving endpoint configuration:**

```bash
databricks serving-endpoints list --output json | jq '.[] | {name, state, config: .config.served_entities[0] | {entity_name, workload_size, scale_to_zero_enabled, workload_type}}'
```

**4.2 — Enable scale-to-zero:**

For endpoints with bursty traffic, enable scale-to-zero to avoid paying for
idle serving capacity:

```json
{
  "scale_to_zero_enabled": true
}
```

**When NOT to scale to zero:**
- Latency-sensitive production endpoints (cold start adds seconds)
- High-frequency endpoints that rarely go idle

**4.3 — Workload sizing:**

| Traffic Pattern | Workload Size | Scale to Zero |
|---|---|---|
| Dev/test | Small | Yes |
| Low-traffic production | Small-Medium | Yes |
| Steady production | Medium-Large | No |
| High-traffic burst | Medium, autoscaling | Depends on latency SLA |

**4.4 — CPU vs GPU serving:**

Many models serve efficiently on CPU. Only use GPU serving for:
- Large deep learning models (transformers, LLMs)
- Models with GPU-specific inference optimizations
- High-throughput requirements that benefit from GPU batching

Traditional ML models (XGBoost, sklearn, LightGBM) should always use CPU
serving — GPU provides no benefit and costs significantly more.

### Step 5: ML Experiment Hygiene

Reduce waste from abandoned experiments and unused resources:

- **Clean up idle clusters** — dev/experiment clusters left running after
  training completes. Enforce auto termination via compute policies.
- **Archive old experiments** — MLflow experiments with no recent runs consume
  tracking server resources.
- **Right-size notebooks** — developers often use oversized clusters for
  exploration. Enforce T-shirt sizing policies (see `cluster-compute/SKILL.md`).
- **Use MLflow Model Registry** — centralize model management to avoid
  duplicate serving endpoints.

## Stopping Points

- ✋ After Step 1: present GPU/ML spend, confirm focus areas
- ✋ After Step 2: present GPU audit findings, confirm instance changes
- ✋ Before Step 4 changes: confirm serving endpoint modifications

## Cross-References

- **`cluster-compute/SKILL.md`** — general cluster sizing, spot instances, compute policies
- **`databricks-spark-performance`** — Spark-level performance tuning for ML pipelines
- **`databricks-automation-bundles`** — DAB-based training job configuration
- **`cost-monitoring-governance/SKILL.md`** — tagging ML resources for cost attribution

## Output

1. **GPU audit report** — all GPU clusters with library validation and recommendations
2. **Training optimization plan** — right-sized configs, spot usage, job compute migration
3. **Serving optimization plan** — endpoint sizing, scale-to-zero, CPU vs GPU recommendations
4. **Estimated savings** — per-cluster and per-endpoint projected cost reductions
