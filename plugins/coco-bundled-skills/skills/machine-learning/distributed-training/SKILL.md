---
name: distributed-training
description: "Distributed ML training on Snowpark Container Services. Routes to specialized sub-skills for estimators, many-model training, custom processing, and hyperparameter tuning."
path: machine-learning/distributed-training
---

# Distributed Training

Distributed machine learning on Snowpark Container Services via ML Jobs or Snowflake Notebooks.

## ⚠️ CRITICAL: Server-Side Execution Only

**All distributed training APIs run SERVER-SIDE on Snowflake compute pools, NOT in local/client environments.**

The `snowflake.ml.modeling.distributors` module is ONLY available inside:
- Snowflake ML Jobs (submitted through CLI/local development, running on Snowflake compute)
- Snowflake Notebooks with Container Runtime (for interactive work in Snowsight)

---

## Running Distributed Training

### Local Python Environment Setup

**⚠️ ML Jobs can ONLY be submitted via Python API** - there is no SQL command to submit ML Jobs.

To submit ML Jobs from a local/CLI environment, you need a Python environment with `snowflake-ml-python`. See `../guides/cli-environment.md` for setup instructions.

**Note:** The `snowflake.ml.modeling.distributors` module (DPF, MMT, etc.) is NOT available locally - it only runs server-side. The local environment is just for *submitting* jobs.

### From CLI / Local Python (Primary)

Write your training script using the distributed APIs below, then submit it via ML Jobs. **Load `../ml-jobs/SKILL.md`** for submission methods (`submit_file`, `submit_directory`), compute pool setup, and configuration details.

**Key for distributed training**: Set `target_instances=N` (N > 1) when submitting to distribute across multiple nodes.

### From Snowflake Notebooks (Interactive)

For interactive work in Snowsight, use a notebook with Container Runtime enabled. See `../guides/snowsight-environment.md` for detailed setup.

**Scale for distributed work:**
```python
from snowflake.ml.runtime_cluster import scale_cluster
scale_cluster(expected_cluster_size=3)  # Add worker nodes
```

**Installing Custom Wheel Files (Container Runtime Notebooks):**

If you need to install a custom `.whl` file in the notebook environment, initialize Ray with a `runtime_env` **before** calling `scale_cluster`:

```python
import ray
import os

whl_name = "my_custom_pkg-0.1.0-py3-none-any.whl"
whl_dir = os.getcwd()

ray.init(
    address="auto",
    ignore_reinit_error=True,
    runtime_env={
        "working_dir": whl_dir,
        "pip": ["${RAY_RUNTIME_ENV_CREATE_WORKING_DIR}/" + whl_name],
    }
)
```

This ensures the custom package is available on all worker nodes when the cluster scales.

> **For ML Jobs**: Include the `.whl` in your job directory with a `requirements.txt` that references it (e.g., `./my_custom_pkg-0.1.0-py3-none-any.whl`). See `../ml-jobs/SKILL.md`.

> **Advanced**: You can also submit ML Jobs from a notebook using the Python API (see `../ml-jobs/SKILL.md`). This is useful when you need to run on a different compute pool or kick off multiple independent jobs. Do not suggest this unless the user asks — running directly in the notebook is the standard path.

For detailed notebook guidance, see `../guides/snowsight-environment.md`.

## When to Use

Route to the appropriate sub-skill based on the user's goal:

| Goal | Sub-Skill |
|------|-----------|
| Train one large model on big data (XGBoost, LightGBM, PyTorch) | `estimators/SKILL.md` |
| Train one model per data partition | `mmt/SKILL.md` |
| Custom distributed processing, multiple outputs per partition | `dpf/SKILL.md` |
| Find optimal hyperparameters (distributed) | `tuner/SKILL.md` |

## Quick Decision Guide

**"I want to train a single model on large data"**
→ Use **Distributed Estimators** (`estimators/SKILL.md`)
- XGBEstimator, LightGBMEstimator for gradient boosting
- PyTorchDistributor for deep learning

**"I want to train separate models for each segment/partition"**
→ Use **Many Model Training** (`mmt/SKILL.md`)
- One model per partition (e.g., per store, per region)
- Built-in model storage with `get_model()`

**"I need custom processing or multiple outputs per partition"**
→ Use **Distributed Partition Function** (`dpf/SKILL.md`)
- Multiple models per partition
- Custom artifact formats
- Non-ML distributed workloads
- **Stage Mode** for many concurrent reads or large datasets (workers read files directly from stage, avoiding warehouse bottlenecks)

**"I want to find the best hyperparameters"**
→ Use **Tuner** (`tuner/SKILL.md`)
- RandomSearch, GridSearch, BayesOpt
- Works with sklearn, XGBEstimator, etc.

---

## Snowflake APIs vs Raw Ray

The Container Runtime includes a pre-configured Ray cluster. You can use raw Ray APIs (`ray.remote`, `ray.data`, etc.) directly:

```python
import ray
ray.init(address="auto", ignore_reinit_error=True)
```

However, multi-node OSS Ray requires you to handle distributed storage for checkpoints (no shared filesystem across nodes), custom data loading, and manual resource configuration to coordinate between data ingestion and compute.

The Snowflake distributed APIs (`XGBEstimator`, `LightGBMEstimator`, `PyTorchDistributor`, `DPF`, `ManyModelTraining`, `Tuner`) handle these automatically — Snowflake stage-based artifact storage, native DataConnector integration, and built-in resource allocation — all on the same underlying Ray cluster.

See [Snowflake docs: Scale an application using Ray](https://docs.snowflake.com/en/developer-guide/snowflake-ml/scale-application-ray) for details.

---

## Assess Workload Before Running

Before launching any distributed job, check the data scale and consider validating on a small scale first.

- **Profile the data**: Use table metadata (`INFORMATION_SCHEMA.TABLES`) for row count and size — this is free. For partitioned workloads (DPF/MMT), check partition count and distribution. Flag skew if the largest partition is significantly larger than the median.
- **Small workloads** (few partitions, small data, quick training): Just run it.
- **Large workloads** (50+ partitions, large datasets, expensive HPO searches): Recommend testing on a single partition or data sample first. Most distributed bugs are in I/O — wrong columns, bad serialization, invalid output paths — and are cheaper to catch on one partition than across all nodes.
- **HPO**: Consider the total number of trials before launching. A GridSearch grid of 5 parameters with 5 values each is 3,125 trials, not 25.

Use `references/compute-pool-sizing.md` to match resources to the profiled workload.

---

## Key API Classes

| Class | Import | Sub-Skill |
|-------|--------|-----------|
| `XGBEstimator` | `snowflake.ml.modeling.distributors.xgboost` | estimators |
| `LightGBMEstimator` | `snowflake.ml.modeling.distributors.lightgbm` | estimators |
| `PyTorchDistributor` | `snowflake.ml.modeling.distributors.pytorch` | estimators |
| `ManyModelTraining` | `snowflake.ml.modeling.distributors.many_model` | mmt |
| `DPF` | `snowflake.ml.modeling.distributors.distributed_partition_function.dpf` | dpf |
| `Tuner` | `snowflake.ml.modeling.tune` | tuner |

---

## Monitoring & Troubleshooting

**Load** `references/monitoring-troubleshooting.md` for:
- Notebook cluster management (`scale_cluster()`, monitoring APIs)
- Dashboard monitoring (Ray Dashboard, Grafana)
- ML Jobs monitoring and logs (Python and SQL)
- OOM troubleshooting (diagnosis, solutions, examples)
- Common errors table and debugging checklist

---

## After Training

- **Run inference on MMT models**: See `../model-registry/partitioned-inference/SKILL.md`
- **Register models**: See `../model-registry/SKILL.md`
- **Deploy models**: See `../spcs-inference/SKILL.md`

---

## Routing Instructions

When a user asks about distributed training, determine their goal and route to the appropriate sub-skill:

1. **Keywords**: "XGBoost", "LightGBM", "PyTorch", "single model", "large dataset" → `estimators/SKILL.md`
2. **Keywords**: "per partition", "per segment", "many models", "one model each" → `mmt/SKILL.md`
3. **Keywords**: "custom function", "multiple outputs", "artifacts", "parquet output" → `dpf/SKILL.md`
4. **Keywords**: "hyperparameter", "tuning", "HPO", "search space", "best parameters" → `tuner/SKILL.md`

If unclear, ask the user which pattern fits their use case.
