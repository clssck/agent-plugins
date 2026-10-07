---
name: experiment-tracking
description: "Track ML experiments in Snowflake. Use when: logging metrics, logging parameters, tracking training runs, comparing model runs, or setting up experiment tracking for reproducibility."
---

# Experiment Tracking

## Intent Detection

Route based on user intent:

| User Says | Route To |
|-----------|----------|
| "set up experiment tracking", "create experiment", "start tracking" | [Workflow B](#workflow-b-autologging) if autologging supports the ML framework and autologging is adequate; otherwise [Workflow A](#workflow-a-manual-logging) |
| "log metrics", "log parameters", "log artifacts", "track hyperparameters", "log console/stdout/stderr" | [Workflow A](#workflow-a-manual-logging) |
| "autolog", "training callback", "XGBoost/Keras/LightGBM callback" | [Workflow B](#workflow-b-autologging) |

---

## When to Use

Load this skill when the user wants to:

- **Track ML experiments** — record hyperparameters, metrics, and model artifacts across training runs
- **Compare model runs** — organize multiple training iterations under a single experiment for side-by-side evaluation
- **Auto-log training metrics** — use framework callbacks (XGBoost, Keras, LightGBM) to capture metrics automatically
- **Log metrics/params or artifacts** — manually record training artifacts or metrics/params such as accuracy, F1, loss, or any custom values

---

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## Prerequisites

- `snowflake-ml-python >= 1.19.0` required
- Active Snowpark session with database/schema context
- For autologging: framework-specific package installed (xgboost, keras, lightgbm)
- For live logging: `snowflake-ml-python >= 1.33.0`, AND running on Snowflake Notebook, not Legacy Notebook

---

## Initialization (Both Workflows)

**⚠️ REQUIRED:** Initialize `ExperimentTracking` before any logging operations.

```python
from snowflake.ml.experiment import ExperimentTracking

# Initialize with session (uses session's current database/schema)
exp = ExperimentTracking(session=session)

# Or specify database/schema explicitly
exp = ExperimentTracking(
    session=session,
    database_name="<DATABASE>",  # optional, defaults to session's current database
    schema_name="<SCHEMA>"       # optional, defaults to session's current schema or PUBLIC
)

# Set experiment (optional - defaults to "DEFAULT")
exp.set_experiment("<EXPERIMENT_NAME>")
```

---

## Workflow A: Manual Logging

Use when you need fine-grained control over what gets logged such as custom metrics or artifacts, or when using frameworks without autolog support (e.g., sklearn, PyTorch custom training loops).

### Step 1: Gather Information

**⚠️ IMPORTANT:** Check conversation context first. If coming from `ml-development` or another skill, you may already have:
- Database/schema context
- Model framework
- Training data schema

**Only ask for what's not already known:**
- Experiment name (check if user mentioned one, or suggest based on task)
- Run name (optional - can auto-generate)
- What to log: params, metrics, model, artifacts (files), stdout and stderr outputs (live logs)

**If all context is available**, proceed directly to Step 2. Otherwise:

**⚠️ STOP**: Wait for user response on missing information.

### Step 2: Log Data Within the Run

**⚠️ IMPORTANT:** Steps 2a-2e below show individual logging operations. Combine them in a **single** `with exp.start_run()` block — do NOT create separate runs for each operation. See the [Complete Example](#complete-example-manual-logging) for the correct pattern.

### Step 2a: Log Parameters

Log hyperparameters and configuration values. **Note:** All parameter values are converted to strings.

```python
with exp.start_run("<RUN_NAME>"):
    # Log individual parameter
    exp.log_param("learning_rate", 0.01)
    
    # Log multiple parameters at once
    exp.log_params({
        "n_estimators": 100,
        "max_depth": 5,
        "random_state": 42
    })
```

### Step 2b: Log Metrics

Log evaluation metrics during or after training:

```python
with exp.start_run("<RUN_NAME>"):
    # Log individual metric
    exp.log_metric("accuracy", 0.95)
    
    # Log multiple metrics at once
    exp.log_metrics({
        "accuracy": accuracy,
        "f1_score": f1,
        "precision": precision,
        "recall": recall
    })
```

**For training loops with multiple epochs**, use the `step` argument (defaults to 0) to track metrics over time:

```python
with exp.start_run("<RUN_NAME>"):
    for epoch in range(num_epochs):
        # ... training code ...
        
        # Log metrics with step for epoch tracking
        exp.log_metric("loss", train_loss, step=epoch)
        exp.log_metrics({
            "val_loss": val_loss,
            "val_accuracy": val_acc
        }, step=epoch)
```

### Step 2c: Log Model

Log the trained model to the run:

```python
from snowflake.ml.model.model_signature import infer_signature

sig = infer_signature(X_train, y_train)

with exp.start_run("<RUN_NAME>"):
    # Train model
    model.fit(X_train, y_train)
    
    # Log model with signature
    # NOTE: Use `signatures` (dict mapping method name to signature), NOT `model_signature`
    exp.log_model(
        model,
        model_name="<MODEL_NAME>",
        signatures={"predict": sig}
    )
```

### Step 2d: Log Artifacts (Optional)

Log additional files or directories (plots, reports, configs):

```python
with exp.start_run("<RUN_NAME>"):
    # Log a single file to root of run's artifact directory
    exp.log_artifact("<LOCAL_FILE_PATH>")
    
    # Log to a specific subdirectory within the run
    exp.log_artifact("<LOCAL_FILE_PATH>", artifact_path="plots")
    
    # Log an entire directory
    exp.log_artifact("<LOCAL_DIRECTORY_PATH>", artifact_path="outputs")
```

**Retrieve artifacts later:**

```python
# List artifacts in a run
artifacts = exp.list_artifacts(run_name="<RUN_NAME>")

# Download artifacts to local directory
exp.download_artifacts(
    run_name="<RUN_NAME>",
    artifact_path="plots",      # optional: specific subdir
    target_path="./downloads"   # optional: local destination
)
```

### Step 2e: Live Logging (Optional)

Capture and persist console (stdout and stderr) outputs:

```python
exp.set_live_logging_status(True)

with exp.start_run("<RUN_NAME>"):
    # ... training and logging code ...
```

Snowflake will only capture stdout and stderr outputs while a run is active.

### Complete Example: Manual Logging

```python
from snowflake.ml.experiment import ExperimentTracking
from snowflake.ml.model.model_signature import infer_signature
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score

# Initialize
exp = ExperimentTracking(session=session)
exp.set_experiment("<EXPERIMENT_NAME>")

# Define hyperparameters
params = {"n_estimators": 100, "max_depth": 5, "random_state": 42}

# Train and log
with exp.start_run("<RUN_NAME>"):
    # Log parameters
    exp.log_params(params)
    
    # Train model
    model = RandomForestClassifier(**params)
    model.fit(X_train, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test)
    
    # Log metrics
    exp.log_metrics({
        "accuracy": accuracy_score(y_test, y_pred),
        "f1_score": f1_score(y_test, y_pred, average='weighted')
    })
    
    # Log model
    sig = infer_signature(X_train, y_train)
    exp.log_model(model, model_name="<MODEL_NAME>", signatures={"predict": sig})
```

---

## Workflow B: Autologging

Use when training with supported frameworks (XGBoost, Keras, LightGBM). Callbacks automatically log parameters, metrics per epoch/iteration, and the final model.

### Step 1: Identify Framework

| Framework | Callback Import |
|-----------|-----------------|
| XGBoost | `from snowflake.ml.experiment.callback.xgboost import SnowflakeXgboostCallback` |
| Keras | `from snowflake.ml.experiment.callback.keras import SnowflakeKerasCallback` |
| LightGBM | `from snowflake.ml.experiment.callback.lightgbm import SnowflakeLightgbmCallback` |

### Step 2: Gather Information

**⚠️ IMPORTANT:** Check conversation context first. If coming from `ml-development` or the user's code is visible, you may already know:
- Framework (from imports or model type)
- Model name
- Database/schema context

**Only ask for what's not already known:**
- Experiment name
- Run name
- Model name (for registry)
- Framework (if not evident from code/context)

**If all context is available**, proceed directly to Step 3. Otherwise:

**⚠️ STOP**: Wait for user response on missing information.

### Step 3: Create Callback

```python
from snowflake.ml.model.model_signature import infer_signature

# Infer signature from training data
sig = infer_signature(X_train, y_train)

# Create framework-specific callback
callback = <FRAMEWORK_CALLBACK>(
    exp,
    model_name="<MODEL_NAME>",
    model_signature=sig
)

# Or customize what gets logged
callback = <FRAMEWORK_CALLBACK>(
    exp,
    model_name="<MODEL_NAME>",
    model_signature=sig,
    log_model=True,           # default: True
    log_metrics=True,         # default: True
    log_params=True,          # default: True
    log_every_n_epochs=1,     # default: 1 (log every epoch)
    version_name="v1"         # optional: model version
)
```

### Step 4: Train with Callback

Pass the callback to the model's fit method:

```python
with exp.start_run("<RUN_NAME>"):
    model.fit(X_train, y_train, callbacks=[callback])
```

### XGBoost Example

```python
from xgboost import XGBClassifier
from snowflake.ml.experiment.callback.xgboost import SnowflakeXgboostCallback
from snowflake.ml.model.model_signature import infer_signature

sig = infer_signature(X_train, y_train)
callback = SnowflakeXgboostCallback(exp, model_name="<MODEL_NAME>", model_signature=sig)
model = XGBClassifier(callbacks=[callback])

with exp.start_run("<RUN_NAME>"):
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)])
```

### Keras Example

```python
import keras
from snowflake.ml.experiment.callback.keras import SnowflakeKerasCallback
from snowflake.ml.model.model_signature import infer_signature

sig = infer_signature(X_train, y_train)
callback = SnowflakeKerasCallback(exp, model_name="<MODEL_NAME>", model_signature=sig)

model = keras.Sequential([keras.layers.Dense(64, activation='relu'), keras.layers.Dense(1)])
model.compile(optimizer='adam', loss='mse', metrics=['mae'])

with exp.start_run("<RUN_NAME>"):
    model.fit(X_train, y_train, validation_split=0.2, callbacks=[callback])
```

### LightGBM Example

```python
from lightgbm import LGBMClassifier
from snowflake.ml.experiment.callback.lightgbm import SnowflakeLightgbmCallback
from snowflake.ml.model.model_signature import infer_signature

sig = infer_signature(X_train, y_train)
callback = SnowflakeLightgbmCallback(exp, model_name="<MODEL_NAME>", model_signature=sig)
model = LGBMClassifier()

with exp.start_run("<RUN_NAME>"):
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[callback])
```

---

## API Reference

### ExperimentTracking Constructor

```python
exp = ExperimentTracking(
    session,
    database_name=None,  # optional, uses session's current database
    schema_name=None     # optional, uses session's current schema or PUBLIC
)
```

**Note:** `ExperimentTracking` is a **singleton** — only one instance exists per session. Subsequent calls reuse the existing instance.

### ExperimentTracking Methods

| Method | Description | Parameters |
|--------|-------------|------------|
| `set_experiment(name, ...)` | Set active experiment (creates if not exists) | `name`: experiment identifier, `database_name`: optional, `schema_name`: optional |
| `start_run(name)` | Start or resume a run | `name`: run identifier (optional, auto-generated if None) |
| `end_run(name)` | End a run | `name`: run to end (optional, ends current run if None) |
| `log_param(key, value)` | Log single parameter | `key`: param name, `value`: any type (converted to string) |
| `log_params(params)` | Log multiple parameters | `params`: dict (values converted to string) |
| `log_metric(key, value, step)` | Log single metric | `key`: metric name, `value`: float, `step`: int (default 0) |
| `log_metrics(metrics, step)` | Log multiple metrics | `metrics`: dict of floats, `step`: int (default 0) |
| `log_model(model, ...)` | Log model to run | Wraps `Registry.log_model` — see model-registry skill |
| `log_artifact(path, artifact_path)` | Log file or directory | `path`: local path, `artifact_path`: destination dir (optional) |
| `list_artifacts(run_name, artifact_path)` | List artifacts in a run | `run_name`: run identifier, `artifact_path`: subdir (optional) |
| `download_artifacts(run_name, ...)` | Download artifacts locally | `run_name`: run identifier, `artifact_path`: optional, `target_path`: optional |
| `delete_experiment(name, ...)` | Delete experiment and all runs | `name`: experiment identifier, `database_name`: optional, `schema_name`: optional |
| `delete_run(name)` | Delete single run | `name`: run identifier |
| `set_live_logging_status(enabled)` | Enable or disable live logging | `enabled`: boolean |

**⚠️ Note:** `log_param`, `log_params`, `log_metric`, `log_metrics`, `log_model`, and `log_artifact` will **auto-start a new run** if no run is currently active.

### Callback Parameters (All Frameworks)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `experiment_tracking` | ExperimentTracking | — | Initialized experiment tracker (required) |
| `log_model` | bool | `True` | Whether to log the model |
| `log_metrics` | bool | `True` | Whether to log metrics |
| `log_params` | bool | `True` | Whether to log parameters |
| `log_every_n_epochs` | int | `1` | Log metrics every N epochs |
| `model_name` | str | `None` | Name for logged model (required if `log_model=True`) |
| `version_name` | str | `None` | Version name for the model |
| `model_signature` | ModelSignature | `None` | Input/output schema (recommended) |

---

## Managing Experiments

### View Existing Experiments and Runs

```sql
-- List all experiments in schema (returns empty list if none — safe)
SHOW EXPERIMENTS IN SCHEMA <DATABASE>.<SCHEMA>;

-- Or check for a specific experiment by name (returns empty list if not found — safe)
SHOW EXPERIMENTS LIKE '<EXPERIMENT_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;

-- List runs in an experiment (only run after confirming experiment exists above — errors if experiment not found)
SHOW RUNS IN EXPERIMENT <DATABASE>.<SCHEMA>.<EXPERIMENT>;
```

### End Run and View URLs

When a run ends (via `end_run()` or exiting the `with` block), URLs are printed:

```
🏃 View run <RUN_NAME> at: https://app.snowflake.com/...
🧪 View experiment at: https://app.snowflake.com/...
```

### Delete Experiment

```python
# Delete in current database/schema
exp.delete_experiment("<EXPERIMENT_NAME>")

# Delete in specific database/schema (both must be specified together)
exp.delete_experiment(
    "<EXPERIMENT_NAME>",
    database_name="<DATABASE>",
    schema_name="<SCHEMA>"
)
```

### Delete Single Run

```python
exp.set_experiment("<EXPERIMENT_NAME>")
exp.delete_run("<RUN_NAME>")
```

---

## Stopping Points

- ✋ After Step 1 (Gather Information) if context is missing — wait for user response

---

## Output

- Experiment with logged runs in Snowflake
- URLs printed when run ends for quick access
- View in Snowsight: **AI & ML → Experiments**
