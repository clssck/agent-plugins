---
name: many-model-training
description: "Train and run inference on one model per data partition using ManyModelTraining and ManyModelInference. Auto-serialization, get_model(), and distributed inference."
parent_skill: distributed-training
path: machine-learning/distributed-training/mmt
---

# Many Model Training & Inference (MMT/MMI)

Train separate ML models for each data partition in parallel, then run distributed inference using those models. MMT/MMI handles distributed orchestration, model serialization, and automatic model loading.

## When to Load

Load this skill when:
- User wants one model per partition (region, store, customer segment, etc.)
- User mentions: "many model", "train per partition", "ManyModelTraining", "model per region/store"
- User wants to run inference using MMT-trained models
- User mentions: "ManyModelInference", "inference per partition", "predict per region/store"
- User wants built-in `get_model()` convenience

**For Model Registry**: If user wants to register models in the Model Registry (versioning, SQL access), see `../../model-registry/partitioned-inference/SKILL.md` for `@partitioned_api` approach.

## Workflow

### Step 1: Confirm Setup

**Ask user:**
```
I'll help you train models per partition. Please confirm:

1. Training data table?
2. Partition column? (e.g., REGION, STORE_ID)
3. Target/label column?
4. Feature columns?
5. Model type? (XGBoost / LightGBM / sklearn / custom)
6. Stage for storing models?
```

**⚠️ STOP**: Wait for user response.

### Step 2: Define Training Function

```python
from snowflake.ml.modeling.distributors.many_model import ManyModelTraining
from snowflake.ml.modeling.distributors.distributed_partition_function.entities import RunStatus

def train_model(data_connector, context):
    """
    Args:
        data_connector: Access partition data via .to_pandas()
        context: Partition info via context.partition_id
    Returns:
        Trained model (auto-serialized)
    """
    df = data_connector.to_pandas()
    print(f"Training for partition: {context.partition_id}")
    
    from xgboost import XGBRegressor
    model = XGBRegressor(n_estimators=100)
    model.fit(df[['feature1', 'feature2']], df['target'])
    return model  # Auto-serialized to stage
```

### Step 3: Run Training

```python
trainer = ManyModelTraining(train_model, "<STAGE_NAME>")

training_run = trainer.run(
    partition_by="<PARTITION_COLUMN>",
    snowpark_dataframe=session.table("<TABLE>"),
    run_id="<DESCRIPTIVE_RUN_ID>"
)

final_status = training_run.wait()
print(f"Training completed with status: {final_status}")
```

**⚠️ STOP**: After training completes, verify with user:
```
Training complete for [N] partitions.
Status: [SUCCESS/PARTIAL/FAILED]

Partition results:
- partition_1: SUCCESS
- partition_2: SUCCESS
...

Would you like to:
1. Retrieve models for use
2. Check failed partitions
3. Proceed to partitioned inference
```

### Step 4: Access Trained Models

```python
if final_status == RunStatus.SUCCESS:
    # Get models by partition
    for partition_id in training_run.partition_details:
        model = training_run.get_model(partition_id)
        print(f"Retrieved model for {partition_id}")
    
    # Or collect all into dict
    models = {
        pid: training_run.get_model(pid) 
        for pid in training_run.partition_details
    }
```

### Step 5: Restore Previous Runs

To restore a completed run later:

```python
from snowflake.ml.modeling.distributors.many_model import ManyModelRun

restored_run = ManyModelRun.restore_from("<RUN_ID>", "<STAGE_NAME>")
model = restored_run.get_model("<PARTITION_ID>")
```

---

## Many Model Inference (MMI)

After training with MMT, use `ManyModelInference` to run distributed inference across partitions. Models are automatically loaded from the training run.

### Step 6: Define Inference Function

```python
from snowflake.ml.modeling.distributors.many_model import ManyModelInference

def predict_with_model(data_connector, model, context):
    """
    Args:
        data_connector: Access partition data via .to_pandas()
        model: Pre-loaded model (auto-loaded from training run)
        context: Partition info via context.partition_id
    Returns:
        Prediction results
    """
    df = data_connector.to_pandas()
    print(f"Running inference for partition: {context.partition_id}")
    
    # Model is already loaded - just use it
    predictions = model.predict(df[['feature1', 'feature2']])
    
    results = df.copy()
    results['predictions'] = predictions
    
    # Save results to stage
    context.upload_to_stage(results, "predictions.csv",
        write_function=lambda df, path: df.to_csv(path, index=False))
    
    return results
```

### Step 7: Run Inference

```python
inference = ManyModelInference(
    predict_with_model,
    "<STAGE_NAME>",                    # Same stage as training
    training_run_id="<TRAINING_RUN_ID>"  # Run ID from Step 3
)

inference_run = inference.run(
    partition_by="<PARTITION_COLUMN>",  # Must match training
    snowpark_dataframe=session.table("<NEW_DATA_TABLE>"),
    run_id="<INFERENCE_RUN_ID>"
)

final_status = inference_run.wait()
print(f"Inference completed with status: {final_status}")
```

**⚠️ STOP**: After inference completes, verify with user:
```
Inference complete for [N] partitions.
Status: [SUCCESS/PARTIAL/FAILED]

Results stored in stage: @<STAGE_NAME>/<INFERENCE_RUN_ID>/

Would you like to:
1. Download prediction results
2. Check failed partitions
3. Run another inference batch
```

### Writing Results to Snowflake Tables

For large-scale inference, write results directly to a table:

```python
def predict_to_table(data_connector, model, context):
    df = data_connector.to_pandas()
    predictions = model.predict(df[['feature1', 'feature2']])
    
    results = df.copy()
    results['predictions'] = predictions
    results['partition_id'] = context.partition_id
    
    # Write to Snowflake table (uses bounded session pool)
    context.with_session(lambda session:
        session.create_dataframe(results)
            .write.mode("append")
            .save_as_table("MY_PREDICTIONS_TABLE")
    )
    
    return {"rows_written": len(results)}
```

### Framework-Specific Deserialization

Use the same `serde` from training:

```python
from snowflake.ml.modeling.distributors.many_model import (
    ManyModelInference, PickleSerde, TorchSerde, TensorFlowSerde
)

# Default (pickle) - XGBoost, sklearn, LightGBM
inference = ManyModelInference(predict_func, "stage", "train_run_v1")

# PyTorch models
inference = ManyModelInference(predict_func, "stage", "train_run_v1", serde=TorchSerde())

# TensorFlow models  
inference = ManyModelInference(predict_func, "stage", "train_run_v1", serde=TensorFlowSerde())

# Custom serde (must match training)
inference = ManyModelInference(predict_func, "stage", "train_run_v1", serde=CustomSerde())
```

---

## Stopping Points

- ✋ **Step 1**: After setup questions (wait for user input)
- ✋ **Step 3**: After training completes (verify results)
- ✋ **Step 7**: After inference completes (verify results)

## Output

**Training (MMT):**
- Trained models stored in stage per partition
- Access via `get_model(partition_id)` or `restore_from()`

**Inference (MMI):**
- Predictions stored in stage or Snowflake table
- Results per partition in `@<STAGE>/<RUN_ID>/<PARTITION_ID>/`

---

## Framework-Specific Serialization

Default serialization uses `PickleSerde` which works for most sklearn-compatible models. For specific frameworks:

```python
from snowflake.ml.modeling.distributors.many_model import (
    ManyModelTraining, PickleSerde, TorchSerde, TensorFlowSerde, ModelSerde
)

# Default (pickle) - works for XGBoost, sklearn, LightGBM
trainer = ManyModelTraining(train_func, "stage")  # Uses PickleSerde()

# PyTorch models
trainer = ManyModelTraining(train_func, "stage", serde=TorchSerde())

# TensorFlow/Keras models
trainer = ManyModelTraining(train_func, "stage", serde=TensorFlowSerde())

# Custom serialization
class CustomSerde(ModelSerde):
    @property
    def filename(self) -> str:
        return "model.joblib"
    
    def write(self, model, file_path: str) -> None:
        import joblib
        joblib.dump(model, file_path)
    
    def read(self, file_path: str):
        import joblib
        return joblib.load(file_path)

trainer = ManyModelTraining(train_func, "stage", serde=CustomSerde())
```

---

## Resource Sizing

See `../references/compute-pool-sizing.md` for instance families and node count sizing. For `ExecutionOptions`, see `../dpf/SKILL.md`. For monitoring and troubleshooting, see `../references/monitoring-troubleshooting.md`.

---

## API Notes

**ManyModelInference signature**: The inference function takes **3 arguments** (not 2 like MMT training):
```python
def predict_func(data_connector, model, context):  # model is auto-loaded and passed as 2nd arg
```

**ManyModelRun**: Extends `DPFRun` (see `../dpf/SKILL.md`) with `get_model(partition_id)` to load trained models.

---

## Next Steps

After MMT/MMI:
- **Register in Model Registry** → See `../../model-registry/partitioned-inference/SKILL.md` for `@partitioned_api`
- **Need custom processing** → Return to router, select DPF
- **Compute pool sizing** → See `../references/compute-pool-sizing.md`
- **Monitoring & troubleshooting** → See `../references/monitoring-troubleshooting.md`
