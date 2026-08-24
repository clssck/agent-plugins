---
name: distributed-partition-function
description: "General-purpose distributed processing with DPF. Custom distributed workloads, multiple outputs per partition, ML and other processing."
parent_skill: distributed-training
path: machine-learning/distributed-training/dpf
---

# Distributed Partition Function (DPF)

General-purpose distributed processing framework. Use when you need more control than MMT provides.

## ⚠️ CRITICAL: Server-Side Execution Only

**DPF runs SERVER-SIDE on Snowflake compute pools, NOT in local/client environments.**

The `snowflake.ml.modeling.distributors` module is ONLY available inside:
- Snowflake ML Jobs (submitted through CLI/local development, running on Snowflake compute)
- Snowflake Notebooks with Container Runtime (for interactive work in Snowsight)

**If working from a local/client environment**, submit your code via ML Jobs. See `../../ml-jobs/SKILL.md` for submission methods.

## When to Load

Load this skill when:
- Training models but only outputting results (not persisting the model)
- Multiple models or artifacts per partition
- Custom serialization formats
- Non-ML distributed processing (ETL, analytics)
- User mentions: "DPF", "distributed partition function", "custom distributed processing"

## Workflow

### Step 1: Clarify Use Case

**Ask user:**
```
I'll help you set up distributed processing with DPF. Which mode?

1. **SQL Mode** - Partition by column values in a DataFrame
2. **Stage Mode** - Process files from a stage

Also confirm:
- What processing do you need per partition?
- What outputs should be saved?
- Output stage name?
```

**⚠️ STOP**: Wait for user response.

### Step 2: Define Processing Function

```python
def my_function(data_connector, context):
    """
    Args:
        data_connector: Access partition data via .to_pandas(), .to_torch_dataset(), etc.
        context: Partition utilities
            - context.partition_id: Current partition identifier
            - context.upload_to_stage(obj, filename): Save artifacts
            - context.download_from_stage(filename): Load artifacts
            - context.with_session(func): Execute with Snowflake session
    """
    df = data_connector.to_pandas()
    
    # Process data
    results = {"count": len(df), "partition": context.partition_id}
    
    # Save outputs
    context.upload_to_stage(results, "results.pkl")
```

### Step 3: Configure and Run

**SQL Mode (partition by column):**
```python
from snowflake.ml.modeling.distributors.distributed_partition_function.dpf import DPF
from snowflake.ml.modeling.distributors.distributed_partition_function.entities import (
    ExecutionOptions, RunStatus
)

dpf = DPF(func=process_partition, stage_name="<OUTPUT_STAGE>")

dpf_run = dpf.run(
    partition_by="<PARTITION_COLUMN>",
    snowpark_dataframe=session.table("<TABLE>"),
    run_id="<DESCRIPTIVE_RUN_ID>",
    execution_options=ExecutionOptions(num_cpus_per_worker=1),
)

status = dpf_run.wait()
```

**Stage Mode (process files):**
```python
dpf = DPF(func=process_file, stage_name="<OUTPUT_STAGE>")

dpf_run = dpf.run_from_stage(
    stage_location="@db.schema.input_stage/",
    run_id="<RUN_ID>",
    file_pattern="*.parquet",
)

status = dpf_run.wait()
```

**⚠️ STOP**: After run completes, verify with user:
```
DPF run complete.
Status: [SUCCESS/PARTIAL/FAILED]
Partitions processed: [N]

Would you like to:
1. Query results from stage
2. Check failed partitions
3. Run another processing job
```

### Step 4: Retrieve Results

```python
# Check progress
dpf_run.get_progress()  # {"DONE": [...], "FAILED": [...]}

# Partition details
dpf_run.partition_details  # Dict[str, SinglePartitionDetails]

# Restore completed run later
from snowflake.ml.modeling.distributors.distributed_partition_function.dpf_run import DPFRun
restored = DPFRun.restore_from("<RUN_ID>", "<STAGE_NAME>")
```

**Query Parquet results from stage:**
```python
session.sql("CREATE FILE FORMAT IF NOT EXISTS parquet_format TYPE = 'PARQUET'").collect()

results_df = session.sql(f"""
    SELECT 
        $1:PARTITION_KEY::STRING AS PARTITION_KEY,
        $1:VALUE::INTEGER AS VALUE
    FROM @<STAGE>/<RUN_ID>/ 
    (FILE_FORMAT => parquet_format, PATTERN => '.*\\.parquet')
""")
```

## Stopping Points

- ✋ **Step 1**: After clarifying use case (wait for user input)
- ✋ **Step 3**: After run completes (verify results)

## Output

- Artifacts saved to stage (per partition)
- Results queryable via SQL
- Run metadata for restoration

---

## ExecutionOptions Reference

```python
from snowflake.ml.modeling.distributors.distributed_partition_function.entities import ExecutionOptions

ExecutionOptions(
    use_head_node=True,          # Head node participates in execution (default True)
    loading_wh=None,             # Warehouse for data loading (see below)
    num_cpus_per_worker=None,    # CPUs per worker (None = auto)
    num_gpus_per_worker=None,    # GPUs per worker (None = auto)
    max_retries=1,               # Retry failed partitions
    fail_fast=False,             # Stop on first failure
)
```

**`loading_wh`**: In SQL mode, a virtual warehouse loads partition data. A larger warehouse makes a difference for large partitions. For many partitions or large tables, consider **Stage mode** (`run_from_stage`) instead -- workers read files directly from a Snowflake stage in parallel, bypassing the warehouse entirely.

**`num_cpus_per_worker`**: See `../references/compute-pool-sizing.md` for how this controls parallelism and memory per worker.

## Resource Sizing

See `../references/compute-pool-sizing.md` for instance families, node count sizing, and the `num_cpus_per_worker` tradeoff. For monitoring and troubleshooting, see `../references/monitoring-troubleshooting.md`.

---

## Monitoring DPF Jobs

For general job monitoring (status, logs, killing jobs) via Python and SQL, see `../references/monitoring-troubleshooting.md`.

**DPF-specific: Checking output on stage:**
```sql
ALTER STAGE <STAGE_NAME> REFRESH;

SELECT RELATIVE_PATH, SIZE FROM DIRECTORY(@<STAGE_NAME>)
WHERE RELATIVE_PATH LIKE '%<run_id>%'
ORDER BY RELATIVE_PATH;
```

> **DPF-specific:** The DPF framework writes per-partition `train.log` files to the output stage alongside your result files. These contain the most detailed per-partition application logs and errors -- check them for debugging failed partitions.

---

## Common Patterns

### Multiple Models per Partition

```python
def train_ensemble(data_connector, context):
    df = data_connector.to_pandas()
    X, y = df[["f1", "f2"]], df["target"]
    
    from xgboost import XGBRegressor
    from sklearn.ensemble import RandomForestRegressor
    
    models = {
        "xgboost": XGBRegressor().fit(X, y),
        "rf": RandomForestRegressor().fit(X, y),
    }
    
    for name, model in models.items():
        context.upload_to_stage(model, f"{name}.pkl")
```

### Results Only (No Model Persistence)

```python
def score_partition(data_connector, context):
    df = data_connector.to_pandas()
    
    from xgboost import XGBClassifier
    model = XGBClassifier().fit(df[["f1", "f2"]], df["target"])
    
    predictions = model.predict(df[["f1", "f2"]])
    results_df = df.assign(prediction=predictions, partition=context.partition_id)
    
    # Write to Snowflake table
    context.with_session(lambda session:
        session.create_dataframe(results_df)
            .write.mode("append")
            .save_as_table("PREDICTIONS")
    )
```

### Write Parquet to Stage

```python
def process_partition(data_connector, context):
    import pyarrow as pa
    import pyarrow.parquet as pq
    
    df = data_connector.to_pandas()
    results = [{"PARTITION_KEY": context.partition_id, "VALUE": 123}]
    
    context.upload_to_stage(
        results,
        "results.parquet",
        write_function=lambda data, path: pq.write_table(
            pa.Table.from_pylist(data), path
        ),
    )
```

> **⚠️ Output filename must be a simple name (no paths).**
> The DPF framework organizes outputs into per-partition directories automatically. Use a flat filename like `"results.parquet"` or `"model.pkl"` -- never embed `context.partition_id` in the filename. The partition_id may contain slashes (e.g., `folder/file.parquet`) which creates nested directories that don't exist, causing `FileNotFoundError`.

---

## API Reference

### DPF

```python
from snowflake.ml.modeling.distributors.distributed_partition_function.dpf import DPF

dpf = DPF(func, stage_name)
```

- `func` (`Callable[[DataConnector, PartitionContext], None]`): Function executed per partition.
- `stage_name` (`str`): Output stage for run artifacts. Each run creates `@{stage_name}/{run_id}/`.

#### DPF.run()

```python
dpf_run = dpf.run(
    partition_by: str,
    snowpark_dataframe: snowpark.DataFrame,
    run_id: str,
    on_existing_artifacts: Literal["error", "overwrite"] = "error",
    execution_options: Optional[ExecutionOptions] = None,
) -> DPFRun
```

- `partition_by`: Column name to partition by. Each unique value = one partition.
- `snowpark_dataframe`: DataFrame to partition. Must contain a single query with no post-actions.
- `run_id`: Unique identifier. Creates `@{stage_name}/{run_id}/` directory.
- `on_existing_artifacts`: `"error"` (default) raises if artifacts exist; `"overwrite"` replaces them.
- `execution_options`: See ExecutionOptions Reference above.

#### DPF.run_from_stage()

```python
dpf_run = dpf.run_from_stage(
    stage_location: str,
    run_id: str,
    file_pattern: str = "*.parquet",
    partition_ids: Optional[List[str]] = None,
    on_existing_artifacts: Literal["error", "overwrite"] = "error",
    execution_options: Optional[ExecutionOptions] = None,
) -> DPFRun
```

- `stage_location`: **Input** stage path (e.g., `"@my_db.my_schema.my_stage/data/"`). Each matching file becomes a partition.
- `file_pattern`: Glob to filter files (default `"*.parquet"`).
- `partition_ids`: Optional list of specific file paths (relative to `stage_location`) to process. When provided, `file_pattern` is ignored. Useful for rerunning failed partitions:
  ```python
  failed = [p for p, d in run.partition_details.items() if d.status == "FAILED"]
  dpf.run_from_stage(..., partition_ids=failed)
  ```

---

## Next Steps

- **Need simpler per-partition models** → Use `../mmt/SKILL.md` instead
- **Run partitioned inference through model registry** → Load `../../model-registry/partitioned-inference/SKILL.md`
