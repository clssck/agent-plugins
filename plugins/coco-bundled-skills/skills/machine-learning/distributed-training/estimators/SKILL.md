---
name: distributed-estimators
description: "Distributed model training with XGBEstimator, LightGBMEstimator, and PyTorchDistributor. Train one large model across multiple nodes/GPUs."
parent_skill: distributed-training
path: machine-learning/distributed-training/estimators
---

# Distributed Estimators

Train a single model across multiple nodes/GPUs using Snowflake's distributed trainers.

## When to Load

Load this skill when:
- User wants to train XGBoost, LightGBM, or PyTorch at scale
- Dataset is too large for single-node training
- User mentions: "distributed XGBoost", "XGBEstimator", "LightGBMEstimator", "PyTorchDistributor", "multi-node training", "multi-GPU training"

## Workflow

### Step 1: Confirm Training Setup

**Ask user:**
```
I'll help you set up distributed training. Please confirm:

1. Which framework? (XGBoost / LightGBM / PyTorch)
2. Training data table name?
3. Target/label column?
4. Feature columns? (or "all except target")
5. GPU or CPU training?
```

**In Snowsight notebooks**: Instead of asking about GPU/CPU, auto-detect by running:
```python
import torch
print(f"GPU available: {torch.cuda.is_available()}, count: {torch.cuda.device_count()}")
```

**⚠️ STOP**: Wait for user response before proceeding.

### Step 2: Set Up Data Connectors

> **Preprocessing checkpoint:** If the request asks to preprocess, or the data has nulls, categorical columns, or scaling/encoding needs, read `../../preprocessing/SKILL.md` before creating `DataConnector`s or writing estimator code.

```python
from snowflake.ml.data.data_connector import DataConnector

train_connector = DataConnector.from_dataframe(session.table('<TRAIN_TABLE>'))
eval_connector = DataConnector.from_dataframe(session.table('<EVAL_TABLE>'))  # Optional
```

For PyTorch, use sharded connector:
```python
from snowflake.ml.data.sharded_data_connector import ShardedDataConnector
data_connector = ShardedDataConnector.from_dataframe(session.table('<TABLE>'))
```

### Step 3: Configure and Train

**If XGBoost:**
```python
from snowflake.ml.modeling.distributors.xgboost import XGBEstimator, XGBScalingConfig

label_col = '<TARGET_COLUMN>'
input_cols = [c for c in session.table('<TABLE>').columns if c != label_col]

params = {
    'objective': 'reg:squarederror',  # or 'binary:logistic', etc.
    'max_depth': 6,
    'learning_rate': 0.1
}

estimator = XGBEstimator(
    params=params,
    scaling_config=XGBScalingConfig(
        num_workers=-1,           # Auto-detect (default)
        num_cpu_per_worker=-1,    # Auto-detect (default)
        use_gpu=None              # None = auto-detect; set True for GPU
    )
)

booster = estimator.fit(
    dataset=train_connector,
    input_cols=input_cols,
    label_col=label_col,
    eval_set=eval_connector,
    verbose_eval=10
)
```

**If LightGBM:**
```python
from snowflake.ml.modeling.distributors.lightgbm import LightGBMEstimator, LightGBMScalingConfig

params = {
    'objective': 'regression',
    'metric': 'rmse',
    'boosting_type': 'gbdt',
    'num_leaves': 31,
    'learning_rate': 0.05
}

estimator = LightGBMEstimator(
    params=params,
    scaling_config=LightGBMScalingConfig(
        num_workers=-1,           # Auto-detect (default)
        num_cpu_per_worker=-1,    # Auto-detect (default)
        use_gpu=None              # None = auto-detect; set True for GPU
    )
)

booster = estimator.fit(
    dataset=train_connector,
    input_cols=input_cols,
    label_col=label_col,
    eval_set=eval_connector,
)
```

**If PyTorch:** See [PyTorch DDP](#pytorch-distributed-training-ddp) section below.

### Step 4: Verify Training Results

**⚠️ STOP**: After training completes, verify results with user:

```
Training complete. Here's what I found:

- Final eval metric: [value]
- Training mode: [single-node / distributed]
- Feature importance (top 5): [list]

Would you like to:
1. Register this model to the Model Registry
2. Inspect more model attributes
3. Retrain with different parameters
```

### Step 5: Access Model Attributes

Present relevant attributes based on user needs:

```python
# Get the trained booster
booster = estimator.get_booster()

# Get evaluation metrics history
eval_results = estimator.get_eval_results()
# Returns: {"train": {"rmse": [0.5, 0.4, ...]}, "eval": {"rmse": [0.6, 0.5, ...]}}

# Access final metric
final_metric = eval_results["eval"]["rmse"][-1]
```

**XGBoost-specific:**
```python
# Feature importance
importance = booster.get_score(importance_type='gain')
# Returns: {"feature1": 0.45, "feature2": 0.32, ...}

# Model config
config = booster.save_config()  # JSON string
```

**LightGBM-specific:**
```python
# Feature importance
importance = booster.feature_importance(importance_type='gain')
feature_names = booster.feature_name()
importance_dict = dict(zip(feature_names, importance))

# Number of trees
num_trees = booster.num_trees()

# Model structure
model_dict = booster.dump_model()
```

## Stopping Points

- ✋ **Step 1**: After asking for training setup (wait for user input)
- ✋ **Step 4**: After training completes (verify results with user)

## Output

- Trained booster object ready for Model Registry
- Evaluation metrics and feature importance
- Model ready for `reg.log_model()` (see `../../model-registry/SKILL.md`)

---

## Scaling Configuration

See `../references/compute-pool-sizing.md` for guidance on sizing nodes and workers for your workload.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `num_workers` | -1 | Worker processes (-1 = auto) |
| `num_cpu_per_worker` | -1 | CPUs per worker (-1 = auto) |
| `use_gpu` | None | Enable GPU training |

---

## PyTorch Distributed Training (DDP)

### Data Loading

```python
from snowflake.ml.data.sharded_data_connector import ShardedDataConnector
data_connector = ShardedDataConnector.from_dataframe(session.table("TRAINING_DATA"))
```

### Training Function

```python
import torch
import torch.nn as nn
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader
from snowflake.ml.modeling.distributors.pytorch import get_context

def train_func():
    import torch.distributed as dist
    
    context = get_context()
    rank = context.get_rank()
    local_rank = context.get_local_rank()
    world_size = context.get_world_size()
    
    dist.init_process_group(backend='gloo')  # or 'nccl' for GPU
    device = torch.device(f"cuda:{local_rank}" if torch.cuda.is_available() else "cpu")
    
    # Initialize model with DDP
    model = YourModel().to(device)
    if world_size > 1:
        model = DDP(model)
    
    # Get data shard for this worker
    dataset_map = context.get_dataset_map()
    torch_dataset = dataset_map['train'].get_shard().to_torch_dataset(batch_size=1024)
    dataloader = DataLoader(torch_dataset, batch_size=None)
    
    # Training loop
    for epoch in range(10):
        for batch in dataloader:
            # ... training logic ...
            pass
    
    # Save model (rank 0 only)
    if rank == 0:
        torch.save(model.module.state_dict(), 
                   os.path.join(context.get_model_dir(), "model.pt"))
```

### Running PyTorch Training

```python
from snowflake.ml.modeling.distributors.pytorch import (
    PyTorchDistributor, PyTorchScalingConfig, WorkerResourceConfig
)

pytorch_trainer = PyTorchDistributor(
    train_func=train_func,
    scaling_config=PyTorchScalingConfig(
        num_nodes=2,
        num_workers_per_node=1,
        resource_requirements_per_worker=WorkerResourceConfig(num_cpus=0, num_gpus=1)
    )
)

response = pytorch_trainer.run(dataset_map={'train': data_connector})

# Access results
model_dir = response.get_model_dir()              # Stage path to saved model
metrics = response.get_metrics()                   # Metrics reported by rank 0
checkpoint = response.get_checkpoint_location()    # Checkpoint location (if saved)
```

---

## Next Steps

After training:
- **Register model** → Load `../../model-registry/SKILL.md`
- **Create inference service** → Load `../../spcs-inference/SKILL.md`
- **Tune hyperparameters** → Return to router, select **Tuner** (`../tuner/SKILL.md`)
- **Compute pool sizing** → See `../references/compute-pool-sizing.md`
- **Monitoring & troubleshooting** → See `../references/monitoring-troubleshooting.md`
