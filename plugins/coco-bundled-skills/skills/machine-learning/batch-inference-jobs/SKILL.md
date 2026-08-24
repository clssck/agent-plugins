---
name: batch-inference-jobs
description: "Run batch inference on models in Snowflake Model Registry. Covers BOTH approaches: (1) Native SQL batch using run() on warehouses for SQL pipelines/dbt, and (2) Job-based batch using run_batch() on SPCS compute pools for large-scale/unstructured data. Triggers: batch inference, bulk predictions, run_batch, run(), offline scoring, score dataset, batch predictions on table, image inference, audio transcription, multimodal."
parent_skill: machine-learning
---

# Batch Inference Jobs

Run inference on registered models for batch workloads. Snowflake offers **two batch inference approaches**:

| Approach | API | Compute | Best For |
|----------|-----|---------|----------|
| **Native SQL Batch** | `mv.run()` | Virtual Warehouse | SQL pipelines, dbt, Dynamic Tables, Snowpark |
| **Job-based Batch** | `mv.run_batch()` | SPCS Compute Pool | Large-scale processing, unstructured data (images/audio/video) |

> **Documentation**: [Model Inference in Snowflake](https://docs.snowflake.com/en/developer-guide/snowflake-ml/inference/inference-overview)

---

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

## Step 0: Choose Inference Approach

**MANDATORY:** Before proceeding, ask the user which batch inference approach they need:

```
For batch inference, there are two approaches:

1. **Warehouse-based** (`mv.run()`) - Runs on virtual warehouses
   - Best for: SQL pipelines, dbt models, Dynamic Tables, Snowpark DataFrames
   - Simpler setup, no compute pool required
   - Ideal for tabular data and lightweight models

2. **SPCS Job-based** (`mv.run_batch()`) - Runs on SPCS compute pools
   - Best for: Large-scale processing, GPU models, unstructured data (images/audio/video)
   - Requires compute pool setup
   - Supports parallel replicas for high throughput

Which approach do you need?
```

**⚠️ STOP**: Wait for user response.

**Routing based on response:**

- **Warehouse-based** → Refer user to the **model-registry** skill which covers `mv.run()` inference in detail. Do NOT continue with this skill.
- **SPCS Job-based** → Continue to Step 1 below.

---

## Job-based Batch Inference (`run_batch()`)

Run large-scale inference jobs on SPCS compute pools. Best for unstructured data (images/audio/video), GPU models, large-scale backfills.

> Requires `snowflake-ml-python>=1.28.0`.

**For unstructured data** (images, audio, video, multimodal LLMs):
→ Load `template/SKILL.md`

**For scheduled / DAG-composed batch inference** (`BatchInferenceTask` inside a Snowflake Task DAG):
→ Load `task-integration/SKILL.md`

## Prerequisites

- `snowflake-ml-python>=1.28.0`
- Model registered in Snowflake Model Registry
- Compute pool (CPU or GPU depending on model)
- Stage for output files (internal, any encryption)

## Workflow

### Step 1: Identify Model and Version

**Ask user:**
```
To run batch inference, I need:

1. **Model name**: What model do you want to use? (from Model Registry)
2. **Database/Schema**: Where is the model registered?
```

**⚠️ STOP**: Wait for user response.

**After user responds, verify model exists:**
If multiple versions exist, ask user which version to use. Otherwise, use the latest.

**Get available functions:**

```python
mv.show_functions()
```

Note the function names (e.g., `predict`, `encode`, `__call__`). If the model has **multiple functions**, you'll need to specify which one to use in JobSpec. If the model has only **one function**, you can omit `function_name` from JobSpec.

### Step 1a: Per-Partition Execution?

Per-partition execution runs the model independently on each partition group of the input — useful for per-store, per-customer, or per-segment processing. The model must support partitioned table-function semantics; see `../model-registry/partitioned-inference/SKILL.md` → Choosing the Decorator.

**Detect from model functions:**
```python
mv.show_functions()
# Methods registered as TABLE_FUNCTION can support per-partition execution.
```

**Ask user:**
```
Do you want to run per-partition (one inference per partition group)? (Yes/No)
If yes, which input column should partition the data? (e.g., STORE_NUMBER, CUSTOMER_ID)
```

**⚠️ STOP**: Wait for user response.

**Routing:**
- **Per-partition** → continue Steps 2–6 normally; in Step 7 use the [Partitioned Model Inference](#template-partitioned-model-inference) template.
- **Standard** → continue with the standard flow below.

### Step 2: Identify Input Data

**Ask user:**
```
What data do you want to run inference on?

1. **Snowflake table** - Tabular data (e.g., MY_DB.SCHEMA.INPUT_TABLE)
2. **Inline data** - Small dataset to create as DataFrame
3. **Unstructured data (non-template)** - Images/audio/video for models expecting raw bytes
   - Use with: Whisper, ViT, ResNet, YOLO, custom image/audio models
   - Best for: Focused tasks like image classification, audio transcription, object detection
4. **Unstructured data (template/LLM)** - Multimodal LLMs with OpenAI chat format
   - Use with: Qwen-VL, LLaVA, MedGemma, other vision-language LLMs
   - Best for: Image captioning, visual Q&A, multimodal reasoning
```

**⚠️ STOP**: Wait for user response.

**Routing based on response:**
- **Option 3 (non-template)** → Load `non-template/SKILL.md`
- **Option 4 (template/LLM)** → Load `template/SKILL.md`

**For Snowflake table:**
```python
input_df = session.table("<DATABASE>.<SCHEMA>.<TABLE_NAME>")
```

**For inline data:**
```python
input_df = session.create_dataframe([
    (5.1, 3.5, 1.4, 0.2),
    (4.9, 3.0, 1.4, 0.2),
], schema=["feature_1", "feature_2", "feature_3", "feature_4"])
```

### Step 3: Configure Output Stage

Batch inference writes results as Parquet files to a Snowflake stage. The user must provide an output stage location.

**Ask user:**
```
Where should I write the inference results?

Provide a stage location (e.g., @MY_DB.MY_SCHEMA.OUTPUT_STAGE/results/)
```

**⚠️ STOP**: Wait for user response.

**If user doesn't have a stage, create one:**

**⚠️ IMPORTANT**: The output stage **must** be an **internal** stage. Either server-side (`SNOWFLAKE_SSE`) or client-side encryption is supported. External stages are not supported for output, but they can still be used for **input** (AWS S3 with SSE only) — see `non-template/SKILL.md` → External Stages.

**Output location format:**
```
@<DATABASE>.<SCHEMA>.<STAGE_NAME>/<optional_path>/
```

Examples:
- `@MY_DB.ML_SCHEMA.INFERENCE_STAGE/predictions/`
- `@MY_DB.ML_SCHEMA.OUTPUT_STAGE/batch_2024_01/`

### Step 4: Configure Compute Pool

**Query available compute pools:**

You can view available compute pool families at `https://docs.snowflake.com/en/sql-reference/sql/create-compute-pools` if needed.
**Recommend compute pool based on model type:**

**Ask user to confirm or create compute pool:**
```
Based on your model, I recommend:
- **Compute Pool**: <`POOL_NAME`> (<INSTANCE_FAMILY>)

Do you want to use this pool, or specify a different one?
```

**If user needs a new compute pool:**
Offer to create a new compute pool with appropriate instance family (CPU vs GPU)

### Step 4a: Select Inference Engine

**Ask the user:**

```
Which inference engine should be used for this batch job?

1. **Python Generic** (default) — for sklearn, XGBoost, LightGBM, HuggingFace non-LLM, and custom models
2. **vLLM** — for HuggingFace text-generation and image-text-to-text models

Based on your model (<MODEL_NAME>/<TYPE>), I recommend: <RECOMMENDATION>
```

**⚠️ STOP**: Wait for user response.

> **If vLLM:** Auto-Capture is not supported — flag this if the user requested it.

**Tip:** If the model type is unclear, inspect `mv.show_functions()` — vLLM-compatible models typically expose a single `__call__` with a `messages` input column.

| Choice | `inference_engine_options` in Step 7 |
|--------|--------------------------------------|
| Python Generic (default) | omit, or `{"engine": InferenceEngine.PYTHON_GENERIC}` |
| vLLM | `{"engine": InferenceEngine.VLLM}` |

---

### Step 5: Configure Job Parameters

**Configure JobSpec for scaling:**
```python
from snowflake.ml.model.batch import JobSpec

# Basic (single replica, model has only one function)
job_spec = JobSpec()

# Basic (single replica, model has multiple functions - must specify which one)
job_spec = JobSpec(function_name="<FUNCTION_NAME>")

# Scaled (multiple replicas)
job_spec = JobSpec(
    function_name="<FUNCTION_NAME>",  # Optional if model has only one function
    replicas=2,           # Number of replicas / instances
    num_workers=2,        # Workers per replica
)
```

> **Note**: `function_name` is only required when the model has multiple functions. If the model has a single function, it will be used automatically.

### Step 6: Present Configuration Summary

**⚠️ MANDATORY CHECKPOINT**: Before submitting, present summary:

```
I will submit a batch inference job with these settings:

- **Model**: <DATABASE>.<SCHEMA>.<MODEL_NAME> (version: <VERSION>)
- **Function**: <FUNCTION_NAME or "default (only one function)">
- **Input**: <INPUT_SOURCE> (<ROW_COUNT> rows)
- **Compute Pool**: <POOL_NAME>
- **Output**: @<DATABASE>.<SCHEMA>.<STAGE>/output/
- **Replicas**: <N>

Ready to submit? (Yes/No)
```

**⚠️ STOP**: Wait for explicit user approval.

### Step 7: Generate and Execute Batch Inference Code

Set up the session following your loaded environment guide, then generate the batch inference code.

**Template: Basic Tabular Inference**

```python
from snowflake.ml.registry import Registry
from snowflake.ml.model.batch import JobSpec, OutputSpec, SaveMode

# Session setup per environment guide
# e.g., create_snowpark_session() or get_active_session()
session = <SESSION_SETUP>
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")

reg = Registry(session=session)
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

input_df = session.table("<INPUT_TABLE>")
output_location = "@<DATABASE>.<SCHEMA>.<STAGE>/output/"

job = mv.run_batch(
    X=input_df,
    compute_pool="<COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location=output_location,
        mode=SaveMode.OVERWRITE,
    ),
    job_spec=JobSpec(),  # Omit function_name if model has only one function
)

print(f"Job submitted. Waiting for completion...")
job.wait()
print(f"Job completed with status: {job.status}")
```

**Template: Scaled Inference with Multiple Replicas**

```python
job = mv.run_batch(
    X=input_df,
    compute_pool="<COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location=output_location,
        mode=SaveMode.OVERWRITE,
    ),
    job_spec=JobSpec(
        function_name="<FUNCTION_NAME>",  # Optional if model has only one function
        replicas=<N>,
        num_workers=2,
    ),
)
```

**Template: LLM / Vision-Language Model (vLLM Engine)**

Use this template when the user confirmed vLLM in Step 4a. Input must be a DataFrame with a `messages` column containing OpenAI-compatible chat format (JSON string). `inference_engine_options` is a top-level `run_batch` argument — do **not** include it inside `JobSpec`.

```python
import json
from snowflake.ml.registry import Registry
from snowflake.ml.model.batch import InferenceEngine, OutputSpec, SaveMode

session = <SESSION_SETUP>
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")

reg = Registry(session=session)
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

# Build input: messages column with OpenAI chat format
messages = [
    [
        {"role": "system", "content": [{"type": "text", "text": "<SYSTEM_PROMPT>"}]},
        {"role": "user", "content": [{"type": "text", "text": "<USER_PROMPT>"}]},
    ]
]
data = [json.dumps(m) for m in messages]
input_df = session.create_dataframe(data, schema=["messages"])

output_location = "@<DATABASE>.<SCHEMA>.<STAGE>/output/"

job = mv.run_batch(
    X=input_df,
    compute_pool="<COMPUTE_POOL>",
    output_spec=OutputSpec(
        stage_location=output_location,
        mode=SaveMode.OVERWRITE,
    ),
    inference_engine_options={"engine": InferenceEngine.VLLM},
)

print("Job submitted. Waiting for completion...")
job.wait()
print(f"Job completed with status: {job.status}")
```

> **Notes:**
> - `InferenceEngine` is imported from `snowflake.ml.model.batch`
> - For vision-language models (image-text-to-text), add `{"type": "image_url", "image_url": {"url": "@db.schema.stage/path/image.jpg"}}` entries in the `content` list; vLLM downloads and converts stage-referenced files automatically
> - Auto-Capture is **not** supported when using vLLM

---

**Template: Partitioned Model Inference**

For per-partition execution, pass `InputSpec(partition_column=...)`. Each partition is processed independently; output preserves the partition column. The model must support partitioned table-function semantics — see `../model-registry/partitioned-inference/SKILL.md` → Choosing the Decorator.

> Requires `snowflake-ml-python>=1.39.0`. The model must be registered with `target_platforms` that include `SNOWPARK_CONTAINER_SERVICES` (use `target_platform.SNOWPARK_CONTAINER_SERVICES_ONLY` for SPCS-only, or include both warehouse and SPCS targets).

```python
from snowflake.ml.model.batch import InputSpec

job = mv.run_batch(
    X=input_df,
    compute_pool="<COMPUTE_POOL>",
    input_spec=InputSpec(partition_column="<PARTITION_COL>"),
    output_spec=output_spec,  # See Step 3
    job_spec=job_spec,        # See Step 5
)
```

**Notes:**
- The partition column must be one of the input columns in the model's signature.
- `NULL` values in the partition column form their own partition.
- High-cardinality partitions (many small groups) parallelize well across `replicas`. Low-cardinality partitions (few large groups) are bottlenecked by per-partition work — replicas help less.

### Step 8: Retrieve and Present Results

**After job completes, show output location:**
```sql
LS @<DATABASE>.<SCHEMA>.<STAGE>/output/;
```

**Read results as DataFrame:**
```python
results_df = session.read.option("pattern", ".*\\.parquet").parquet(output_location)
results_df.show(10)
```

**Save results to table (optional):**
```python
output_table = "<OUTPUT_TABLE_NAME>"
results_df.write.mode("overwrite").save_as_table(output_table)
print(f"Results saved to {output_table}")
```

**Present to user:**
```
Batch inference completed!

- **Status**: DONE
- **Output Location**: @<DATABASE>.<SCHEMA>.<STAGE>/output/
- **Files**: <N> parquet files

Would you like me to:
1. Show sample results
2. Save results to a table
3. Clean up resources
```

## Common Use Cases

### Classification/Regression (sklearn, xgboost, lightgbm)

```python
# Input: DataFrame with feature columns matching model signature
input_df = session.table("MY_DB.MY_SCHEMA.FEATURES_TABLE")

job = mv.run_batch(
    X=input_df,
    compute_pool="CPU_POOL",
    output_spec=OutputSpec(stage_location=output_location, mode=SaveMode.OVERWRITE),
    job_spec=JobSpec(),
)
```

### Text Embeddings (SentenceTransformer)

```python
# Input: DataFrame with text column
input_df = session.create_dataframe([
    ("The quick brown fox",),
    ("Snowflake is great",),
], schema=["input_feature_0"])

job = mv.run_batch(
    X=input_df,
    compute_pool="CPU_POOL",
    output_spec=OutputSpec(stage_location=output_location, mode=SaveMode.OVERWRITE),
    job_spec=JobSpec(function_name="encode"),  # SentenceTransformer uses encode
)
```

## Reading Output

Batch inference writes results as **Parquet files** to the specified output stage location.

### Handling Partial Output

A job can fail midway, leaving partial data. Batch inference writes a `_SUCCESS` sentinel file upon completion.

**Best practices:**
- Only read output after `_SUCCESS` file exists
- Use an empty output directory
- Use `SaveMode.ERROR` to fail if directory not empty (safer for production)

```python
# Safe production pattern
output_spec=OutputSpec(
    stage_location=output_location,
    mode=SaveMode.ERROR,  # Fail if output exists (prevents overwriting)
)
```

| SaveMode | Behavior |
|----------|----------|
| `OVERWRITE` | Replace existing output |
| `ERROR` | Fail if output directory not empty |

### Output Structure

The output contains:
- **All original input columns** - Your input data is preserved
- **Prediction column(s)** - Model outputs appended with names like `output_feature_0`, `predictions`, etc.

The exact output column name depends on the model's signature. Common patterns:

| Model Type | Output Column | Format |
|------------|---------------|--------|
| XGBoost/sklearn classifiers | `output_feature_0` | Integer (class label) |
| XGBoost/sklearn regressors | `output_feature_0` | Float (predicted value) |
| SentenceTransformer | `output_feature_0` | Array of floats (embedding vector) |

### Reading Results

```python
# List output files
session.sql(f"LS {output_location}").show()

# Read all parquet files
results_df = session.read.option("pattern", ".*\\.parquet").parquet(output_location)
results_df.show()

# Save to table for easier access
results_df.write.mode("overwrite").save_as_table("PREDICTION_RESULTS")
```

## Troubleshooting

### Job Management

```python
from snowflake.ml.jobs import list_jobs, delete_job, get_job

# View logs to troubleshoot
job.get_logs()

# Cancel a running job
job.cancel()

# List all jobs
list_jobs().show()

# Get handle to existing job by name
job = get_job("my_db.my_schema.job_name")

# Delete a job
delete_job(job)
```

> **Note**: The `result()` function from ML Job APIs is **not supported** for Batch Inference Jobs.

### Job Status

Check job status programmatically:
```python
print(f"Status: {job.status}")
print(f"Job ID: {job.id}")
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `Model not found` | Wrong model name or schema | Verify with `SHOW MODELS IN SCHEMA` |
| `Compute pool not ready` | Pool is starting/suspended | Wait or run `ALTER COMPUTE POOL ... RESUME` |
| `Permission denied` | Missing grants | Grant usage on compute pool and stage |
| `Column mismatch` | Input doesn't match model signature | Check `mv.show_functions()` for expected inputs |

### Checking Model Signature

```python
# View model functions and their signatures
mv.show_functions()
```

## Stopping Points

- ✋ Step 0: After asking warehouse vs SPCS approach
- ✋ Step 1: After asking for model name/database
- ✋ Step 1a: After asking whether the user wants per-partition execution (and partition column if so)
- ✋ Step 2: After asking for input data source
- ✋ Step 3: After asking for output stage location
