---
name: ml-pipeline-orchestration
description: "Create and deploy ML pipelines using Snowflake Task Graphs (DAGs). Use when: orchestrating ML workflows, scheduling training/inference, converting notebooks to production DAGs, automating model retraining, building task graphs. Triggers: pipeline, DAG, task graph, schedule training, orchestrate, productionize, automate retraining."
path: machine-learning/ml-pipeline-orchestration
parent_skill: machine-learning
---

# ML Pipeline Orchestration

Orchestrate ML workflows using Snowflake Task Graphs (DAGs). **Use `@remote` for ML tasks** (compute pool) — cheaper, ML dependencies included.

## When to Use

- User wants to **schedule** ML training or inference
- User wants to **orchestrate** multiple ML steps (prep → train → evaluate → deploy)
- User wants to **convert a notebook** into a production pipeline
- User mentions: "DAG", "task graph", "pipeline", "schedule training", "productionize"

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding**, verify you have the environment guide from `machine-learning/SKILL.md` → Step 0.

---

## Key Concepts

```python
from snowflake.core.task.dagv1 import DAG, DAGTask, DAGTaskBranch, DAGOperation
from snowflake.core.task.context import TaskContext
from snowflake.core.task import Cron
from snowflake.ml.jobs import remote
```

- **Compute pool tasks:** Run on compute pool via `@remote` or `MLJobDefinition` — cheaper, ML packages included
- **Warehouse tasks:** Run as stored procedures — use for lightweight orchestration, branching
- **`TaskContext`:** Pass data between tasks via `get_predecessor_return_value()` / `set_return_value()`
- **DAG `config`:** Pass shared settings via `config={"key": "value"}` on the DAG; tasks read via `TaskContext.get_task_graph_config()`
- **Dependencies:** `task_a >> task_b` (sequential), `task >> [a, b]` (fan-out)

---

## API Gotchas

| Wrong | Correct |
|-------|---------|
| `DAGTask("T", my_remote_fn, warehouse=WH)` | `DAGTask("T", definition=my_remote_fn)` — no warehouse for `@remote` |
| `DAG(database=X, schema=Y)` | `DAGOperation(schema_ref)` — database/schema set via DAGOperation |
| `schedule="0 * * * *"` | `schedule=Cron("0 * * * *", "UTC")` or `timedelta(hours=1)` |
| Branch returns `"deploy"` | Branch returns `"PROMOTE_MODEL"` — must match task name exactly |
| `return result` in `@remote` | `ctx.set_return_value(json.dumps(result))` — must use TaskContext |
| `TaskContext` fails with `ModuleNotFoundError` | Add `snowflake.core` to DAG `packages=[]` — `snowflake-ml-python >=1.29` no longer includes it |

---

## Pipeline Template

```python
import json
from datetime import timedelta
from snowflake.core import Root
from snowflake.core.task.dagv1 import DAG, DAGTask, DAGTaskBranch, DAGOperation
from snowflake.core.task.context import TaskContext
from snowflake.core.task import Cron
from snowflake.ml.jobs import remote
from snowflake.snowpark import Session

# Configuration
DATABASE = "<DATABASE>"
SCHEMA = "<SCHEMA>"
WAREHOUSE = "<WAREHOUSE>"
COMPUTE_POOL = "<COMPUTE_POOL>"
DAG_STAGE = f"@{DATABASE}.{SCHEMA}.DAG_STAGE"
JOB_STAGE = f"@{DATABASE}.{SCHEMA}.JOB_STAGE"

# --- Warehouse task: lightweight data prep ---
def prepare_data(session: Session) -> str:
    """Prepare datasets, return info as JSON for downstream tasks."""
    # ... data prep logic ...
    return json.dumps({"train_table": "TRAIN_DATA", "test_table": "TEST_DATA"})

# --- @remote task: heavy ML training on compute pool ---
@remote(COMPUTE_POOL, stage_name=JOB_STAGE, database=DATABASE, schema=SCHEMA)
def train_model() -> None:
    """Train model on compute pool. Access predecessor data via TaskContext."""
    session = Session.builder.getOrCreate()
    ctx = TaskContext(session)

    # Get data from predecessor task
    data_info = json.loads(ctx.get_predecessor_return_value("PREPARE_DATA"))

    # ... training logic using data_info ...
    model_metrics = {"accuracy": 0.95, "model_path": "models/v1.pkl"}

    # Pass results to successor tasks
    ctx.set_return_value(json.dumps(model_metrics))

# --- Warehouse task: branching logic ---
def check_quality(session: Session) -> str:
    """Check model quality, return next task name."""
    ctx = TaskContext(session)
    cfg = ctx.get_task_graph_config()
    metrics = json.loads(ctx.get_predecessor_return_value("TRAIN_MODEL"))

    if metrics["accuracy"] >= float(cfg["threshold"]):
        return "PROMOTE_MODEL"  # Must match task name exactly (case-sensitive)
    return "SEND_ALERT"

# --- Warehouse tasks: conditional paths ---
def promote_model(session: Session) -> str:
    ctx = TaskContext(session)
    metrics = json.loads(ctx.get_predecessor_return_value("TRAIN_MODEL"))
    # ... register model to registry ...
    return "Model promoted"

def send_alert(session: Session) -> None:
    # ... send notification ...
    pass

def cleanup(session: Session) -> None:
    """Finalizer: always runs regardless of success/failure."""
    # ... cleanup temp artifacts ...
    pass

# --- Build the DAG ---
with DAG(
    name="ML_TRAINING_PIPELINE",
    schedule=timedelta(days=1),
    stage_location=DAG_STAGE,
    use_func_return_value=True,
    config={"threshold": "0.90", "model_name": "MY_MODEL"},
) as dag:
    prep = DAGTask("PREPARE_DATA", prepare_data, warehouse=WAREHOUSE)
    train = DAGTask("TRAIN_MODEL", definition=train_model)  # @remote: no warehouse!
    check = DAGTaskBranch("CHECK_QUALITY", check_quality, warehouse=WAREHOUSE)
    promote = DAGTask("PROMOTE_MODEL", promote_model, warehouse=WAREHOUSE)
    alert = DAGTask("SEND_ALERT", send_alert, warehouse=WAREHOUSE)
    final = DAGTask("CLEANUP", cleanup, warehouse=WAREHOUSE, is_finalizer=True)  # runs automatically

    prep >> train >> check >> [promote, alert]

# --- Deploy (session setup per environment guide) ---
root = Root(session)
dag_op = DAGOperation(root.databases[DATABASE].schemas[SCHEMA])
dag_op.deploy(dag, mode="orReplace")
```

**Key patterns:**
- `@remote` runs on compute pool — use `definition=` parameter, no warehouse
- Warehouse tasks for orchestration, branching, lightweight ops
- `TaskContext` passes data between tasks via JSON
- `config={}` on DAG → tasks read via `ctx.get_task_graph_config()` (all values must be strings)
- Branch return values must match task names exactly

**Alternative:** For file-based payloads, use `MLJobDefinition.register()`:
```python
from snowflake.ml.jobs import MLJobDefinition
job_def = MLJobDefinition.register("/path/to/script.py", compute_pool=POOL, stage_name=STAGE, session=session)
train_task = DAGTask("TRAIN", definition=job_def)
```

---

## Workflows

### Workflow 1: Create Pipeline

1. **Gather requirements** — What does it do? How often? Which database.schema?
2. **Generate code** — Use Pipeline Template above
3. **Deploy** — `dag_op.deploy(dag, mode="orReplace")`
4. **Ask about execution** — Offer to run the DAG to test it — `dag_op.run(dag)`
5. **Verify** — Snowsight → Monitoring → Task History

**⚠️ MANDATORY STOPPING POINT**: Wait for user requirements before generating code.

### Workflow 2: Add Task to Existing DAG

1. **Get structure** — `SHOW TASKS LIKE '%DAG_NAME%' IN SCHEMA ...`
2. **Add to DAG definition:**
   ```python
   with DAG(...) as dag:
       # ... existing tasks ...
       new_ml_task = DAGTask("NEW_ML", definition=new_remote_fn)  # @remote
       new_orch_task = DAGTask("NEW_ORCH", new_warehouse_fn, warehouse=WH)  # warehouse
       existing >> new_ml_task >> new_orch_task
   ```
3. **Redeploy** — `dag_op.deploy(dag, mode="orReplace")`

**⚠️ MANDATORY STOPPING POINT**: Present changes and wait for approval before deploying.

### Workflow 3: Convert Notebook

1. **Identify notebook** — Confirm which notebook to convert
2. **Extract functions** — Each cell group becomes a function (`@remote` for ML, warehouse for orchestration)
3. **Deploy** — Follow Pipeline Template above

**⚠️ MANDATORY STOPPING POINT**: Wait for user confirmation.

---

## Quick Reference

| Pattern | Use Case |
|---------|----------|
| `@remote` + `definition=` | ML tasks on compute pool |
| `warehouse=` | Orchestration, branching |
| `config={"key": "val"}` on DAG | Shared settings (all values must be strings) |
| `ctx.set_return_value()` | Pass data from task |
| `ctx.get_predecessor_return_value("TASK")` | Read data from predecessor |
| `ctx.get_task_graph_config()` | Read DAG config |
| `DAGTaskBranch` | Conditional paths |
| `is_finalizer=True` | Cleanup (always runs) |

### Scheduling (in `DAG()`)

```python
DAG(name="MY_DAG", schedule=timedelta(days=1), ...)      # Daily
DAG(name="MY_DAG", schedule=Cron("0 9 * * *", "America/Los_Angeles"), ...)  # 9am PT
DAG(name="MY_DAG", schedule=None, ...)                   # Manual only
```

### Required Privileges

```sql
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <role>;
GRANT EXECUTE MANAGED TASK ON ACCOUNT TO ROLE <role>;  -- if using managed schedules
```

---

## Related Skills & References

- `ml-jobs/SKILL.md` — Compute pools, `@remote` details, EAI setup
- `model-registry/SKILL.md` — Model registration
- `references/operations.md` — Scheduling, monitoring, error handling

**External:** [Official e2e_task_graph sample](https://github.com/Snowflake-Labs/sf-samples/tree/main/samples/ml/ml_jobs/e2e_task_graph) | [Task Graph Docs](https://docs.snowflake.com/en/developer-guide/snowflake-python-api/snowflake-python-managing-tasks)
