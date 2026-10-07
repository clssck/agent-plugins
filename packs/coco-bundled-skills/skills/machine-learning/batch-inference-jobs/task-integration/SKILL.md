---
name: batch-inference-task-integration
description: "Compose batch inference jobs inside a Snowflake Task DAG using BatchInferenceTask. Use for scheduled/recurring batch inference, multi-step DAGs that include batch inference, and downstream tasks that read the inference output. Triggers: schedule batch inference, batch inference task, BatchInferenceTask, batch inference DAG, run_batch in a DAG, downstream task on inference output, nightly batch inference."
parent_skill: batch-inference-jobs
---

# Batch Inference in Task DAGs

`BatchInferenceTask` runs a batch inference job inside a Snowflake Task DAG. Construct it inside a `with DAG(...)` block (or pass `dag=` explicitly) and chain it with other tasks using `>>`. Each scheduled run submits a new SPCS batch inference job and writes results to a per-run output subdirectory.

> Requires `snowflake-ml-python>=1.39.0` and the `snowflake.core` package.

## When to Use

- **Scheduled / recurring** batch inference (cron-style via the DAG's `schedule`)
- A task chain like `data_preparation >> batch_inference >> post_process`
- A downstream task that needs to read the inference output and act on it
- Multi-step ML workflows where batch inference is one step

For one-shot batch inference (no DAG), call `mv.run_batch()` directly — see `../SKILL.md`.

## Quick Reference

```python
from datetime import timedelta
from snowflake.core import Root
from snowflake.core.task.dagv1 import DAG, DAGOperation, DAGTask
from snowflake.ml.model.batch import BatchInferenceTask, JobSpec, OutputSpec

api_root = Root(session)
schema_ref = api_root.databases["<DATABASE>"].schemas["<SCHEMA>"]

dag = DAG(
    "<DAG_NAME>",
    schedule=timedelta(days=1),                 # Or any Snowflake task schedule
    stage_location="@<DATABASE>.<SCHEMA>.<STAGE>",  # DAG metadata stage
)

with dag:
    data_prep = DAGTask("data_preparation", definition="<PREP_SQL>")
    batch_inf = BatchInferenceTask(
        "batch_inference",
        model_version=mv,                       # Same as mv.run_batch's mv
        X=input_df,                             # Same as mv.run_batch's X
        compute_pool="<COMPUTE_POOL>",
        output_spec=OutputSpec(
            base_stage_location="@<DATABASE>.<SCHEMA>.<STAGE>/base/path/",
        ),
        job_spec=JobSpec(
            function_name="predict",            # Required if multiple methods
        ),
    )
    post = DAGTask("post_process", definition="<POST_SQL>")
    data_prep >> batch_inf >> post
```

> **⚠️ Confirm before deploying.** `DAGOperation.run()` triggers immediate execution of the DAG. Present the planned DAG name, schedule, task chain, and stage location to the user and get explicit approval (Yes/No) before running:

```python
DAGOperation(schema_ref).deploy(dag)
DAGOperation(schema_ref).run(dag)
```

## Key Differences from Direct `mv.run_batch()`

| Aspect | `mv.run_batch()` (direct) | `BatchInferenceTask` (DAG) |
|--------|---------------------------|----------------------------|
| `OutputSpec` field | `stage_location=...` (exact dir) | Same; or `base_stage_location=...` (per-run subdir, recommended for scheduled / repeated runs) |
| Return | Job handle (`job.wait()`, `job.status`, `job.cancel()`) | A task in the DAG (chained via `>>`); output dir surfaced to successors via `SYSTEM$GET_PREDECESSOR_RETURN_VALUE()` |
| Identity | One submission | Each DAG run creates a new SPCS job |
| Lifecycle | Caller-controlled | Driven by DAG schedule + `DAGOperation.run()` |

The `base_stage_location` semantics matter: each run writes to its own subdirectory under the base path. The subdir name is per-run (default form `BATCH_INFERENCE_<UUID>/`; override with `JobSpec(job_name_prefix=...)` to get `<prefix>_<UUID>/`, or with `JobSpec(job_name=...)` for an exact name), so repeated runs don't clobber each other.

## Reading the Output in a Successor Task

`BatchInferenceTask` returns a JSON value containing the actual output directory. A successor task reads it via `SYSTEM$GET_PREDECESSOR_RETURN_VALUE()`:

```sql
-- Inside a successor DAGTask's definition
SELECT PARSE_JSON(SYSTEM$GET_PREDECESSOR_RETURN_VALUE()):output_stage_location::VARCHAR
```

The JSON looks like:
```json
{"output_stage_location": "@DATABASE.SCHEMA.STAGE/base/path/<job-name>_<UUID>/"}
```

Use that path with `LIST`, `session.read.option("pattern", ".*\\.parquet").parquet(...)`, or further SQL to consume the parquet output.

## Pattern: Inference + Post-Processing

```python
result_table = "<DB>.<SCHEMA>.INFERENCE_AUDIT"
session.sql(f"CREATE TABLE IF NOT EXISTS {result_table} (run_ts TIMESTAMP, output_loc VARCHAR)").collect()

post_sql = f"""
INSERT INTO {result_table} (run_ts, output_loc)
SELECT
    CURRENT_TIMESTAMP(),
    PARSE_JSON(SYSTEM$GET_PREDECESSOR_RETURN_VALUE()):output_stage_location::VARCHAR
"""

with dag:
    batch_inf = BatchInferenceTask("batch_inference", model_version=mv, X=input_df,
                                   compute_pool=COMPUTE_POOL,
                                   output_spec=OutputSpec(base_stage_location=base),
                                   job_spec=JobSpec(function_name="predict"))
    post = DAGTask("post_process", definition=post_sql)
    batch_inf >> post
```

## Pattern: Date-stamped output folders

`BatchInferenceTask` writes each run to `<base_stage_location>/<job-name>_<UUID>/` — UUID-suffixed, not date-named (the `<job-name>` defaults to `BATCH_INFERENCE` and can be overridden via `JobSpec(job_name_prefix=...)` or `JobSpec(job_name=...)`). **Don't bypass `BatchInferenceTask` for this** (e.g., wrapping `mv.run_batch()` in a custom Python task). Instead, chain a successor SQL task that reads the predecessor's path via `SYSTEM$GET_PREDECESSOR_RETURN_VALUE()` and `COPY FILES` into a date-stamped folder:

```python
rename_sql = """
DECLARE
    src VARCHAR DEFAULT PARSE_JSON(SYSTEM$GET_PREDECESSOR_RETURN_VALUE()):output_stage_location::VARCHAR;
    today VARCHAR DEFAULT TO_VARCHAR(CURRENT_DATE(), 'YYYY-MM-DD');
    dst VARCHAR DEFAULT '@<DATABASE>.<SCHEMA>.<STAGE>/' || today || '/';
BEGIN
    EXECUTE IMMEDIATE 'COPY FILES INTO ' || dst || ' FROM ' || src;
    EXECUTE IMMEDIATE 'REMOVE ' || src;
    RETURN dst;
END;
"""

with dag:
    batch_inf = BatchInferenceTask(
        "batch_inference",
        model_version=mv,
        X=input_df,
        compute_pool="<COMPUTE_POOL>",
        output_spec=OutputSpec(base_stage_location="@<DATABASE>.<SCHEMA>.<STAGE>/runs/"),
        job_spec=JobSpec(function_name="predict"),
    )
    rename = DAGTask("rename_to_date", definition=rename_sql)
    batch_inf >> rename
```

`COPY FILES` is server-side, so the move is fast. `CURRENT_DATE()` is evaluated at the task's execution time, so each daily run lands at the correct date folder. After the run, output is at `@<DATABASE>.<SCHEMA>.<STAGE>/<YYYY-MM-DD>/`. Same approach works for any runtime-derived path (per-customer, per-region, etc.) — change the `dst` expression accordingly.

## Constraints

- `BatchInferenceTask` shares all `mv.run_batch()` prerequisites: registered model with SPCS target, compute pool, internal output stage. See `../SKILL.md` for the full setup.
- Each scheduled run starts a fresh SPCS job — the DAG is the orchestrator, not the inference runtime.
- DAG-level operations (scheduling, polling, cancellation, retry, suspend/resume) are standard Snowflake Task features. See [Snowflake Task documentation](https://docs.snowflake.com/en/user-guide/tasks-intro) and [`snowflake.core.task.dagv1`](https://docs.snowflake.com/en/developer-guide/snowpark/python/managing-tasks-with-python-api) for orchestration details.
