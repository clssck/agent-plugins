---
name: debug-inference
description: "Debug model inference issues for both warehouse and SPCS. Covers dtype errors, nullable signature problems, service failures, OOM, container issues. Use when: inference error, mv.run fails, TypeError, np.radians error, service not starting, OOM, container crash."
parent_skill: machine-learning
---

# Debugging Model Inference

This skill helps diagnose and fix inference issues for models deployed via Snowflake Model Registry, whether running on warehouse or SPCS.

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## Step 0: Triage - Determine Inference Type

**Ask user or detect from context:**

If the user mentions `service_name` parameter, REST API, or SPCS compute pool, it's SPCS inference. If they mention `MODEL()` SQL function or `mv.run()` without `service_name`, it's warehouse inference.

**If unclear, ask:**

```
Where is your inference running?

1. **Warehouse** - Using `mv.run()` without service_name, or SQL `MODEL()` calls
2. **SPCS Service** - Using `mv.run()` with service_name parameter, or REST API calls to a deployed service
```

**⚠️ STOP**: Wait for user response if inference type is not clear from context.

**Routing:**

- **If SPCS** → Go to [Step 1: Check Service Status & Logs](#step-1-spcs---check-service-status--logs)
- **If Warehouse** → Go to [Step 2: Check Model Signature](#step-2-check-model-signature) (Note: NumPy/nullable dtype issues are SPCS-specific)

---

## Step 1: SPCS - Check Service Status & Logs

Before diagnosing model-level issues, verify the service is healthy and retrieve logs to identify the error:

```sql
-- Check service status
DESCRIBE SERVICE <DATABASE>.<SCHEMA>.<SERVICE_NAME>;

-- Get detailed instance status
SELECT SYSTEM$GET_SERVICE_STATUS('<DATABASE>.<SCHEMA>.<SERVICE_NAME>');

-- Get recent logs from model-inference container
CALL SYSTEM$GET_SERVICE_LOGS('<DATABASE>.<SCHEMA>.<SERVICE_NAME>', 0, 'model-inference');
```

**Route based on errors found in logs:**

| Error Pattern in Logs | Issue | Go To |
|----------------------|-------|-------|
| `TypeError: loop of ufunc does not support argument 0 of type float` | Nullable dtype issue | [Issue A](#issue-a-numpy-ufunc-errors-with-nullable-dtypes) |
| `'float' object has no attribute 'radians'` | Nullable dtype issue | [Issue A](#issue-a-numpy-ufunc-errors-with-nullable-dtypes) |
| `OOMKilled`, memory errors | Out of memory | [Issue C](#issue-c-oom-and-memory-issues) |
| Container restart, crash | Container issues | [Issue D](#issue-d-container-logs-and-crashes) |
| Service status PENDING/STARTING | Service not ready | [Issue B](#issue-b-service-not-ready) |

---

## Step 2: Check Model Signature

Retrieve the model version and inspect function signatures for potential issues:

```python
from snowflake.ml.registry import Registry

reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

# Inspect all functions and their signatures
for func in mv.show_functions():
    print(f"\nFunction: {func['name']}")
    print(f"  Target Method: {func['target_method']}")
    print("  Input Features:")
    for feat in func['signature'].inputs:
        print(f"    {feat.name}: dtype={feat._dtype}, nullable={feat._nullable}")
    print("  Output Features:")
    for feat in func['signature'].outputs:
        print(f"    {feat.name}: dtype={feat._dtype}, nullable={feat._nullable}")
```

**What to look for:**

- Features with `nullable=True` on numeric types (DOUBLE, FLOAT, INT) can cause NumPy ufunc errors
- Missing or incorrect feature names
- Type mismatches between expected and actual input data

---

## Issue A: NumPy Ufunc Errors with Nullable Dtypes (SPCS Only)

**Note:** This issue only occurs with SPCS inference, not warehouse inference. The SPCS inference server handles dtype conversion differently.

### Symptoms

Errors like:

```
TypeError: loop of ufunc does not support argument 0 of type float which has no callable radians method
```

or:

```
AttributeError: 'float' object has no attribute 'radians'
```

### Root Cause

When you register a model using `sample_input_data` in `log_model()`, the signature inference defaults `nullable=True` for all features. This causes the inference server to use Pandas nullable extension dtypes (`pd.Float64Dtype()` instead of `np.float64`).

When model code calls `.values.T` on a DataFrame with nullable dtypes, it produces a `dtype=object` array containing Python `float` objects instead of a native NumPy array. NumPy ufuncs like `np.radians()`, `np.sin()`, `np.cos()` cannot operate on these object arrays.

**Example of the problem:**

```python
# With nullable=True (default), inference server does:
df = df.astype({"col": pd.Float64Dtype()})  # Nullable extension dtype
arr = df[["col"]].values.T  # → dtype=object array with Python floats

# NumPy ufuncs fail on object arrays:
np.radians(arr)  # TypeError!
```

### Diagnosis

Check if your model signature has `nullable=True` on numeric features:

```python
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")
for func in mv.show_functions():
    for feat in func['signature'].inputs:
        if feat._nullable and feat._dtype.name in ['DOUBLE', 'FLOAT', 'INT64', 'INT32']:
            print(f"WARNING: {feat.name} has nullable=True - may cause NumPy issues")
```

### Fix

**⚠️ MANDATORY CHECKPOINT**: Before re-registering the model, present to user:

```
I've identified the issue. The model signature has nullable=True on numeric features,
causing NumPy ufunc errors in SPCS inference.

Proposed fix:
- Re-register the model with an explicit signature (nullable=False on all numeric features)
- Affected features: [list features with nullable=True]
- New version name: <NEW_VERSION>

This will create a new model version. The existing version will not be modified.

Do you approve? (Yes/No/Modify)
```

**⚠️ STOP**: Wait for explicit user approval before proceeding.

Re-register the model with an explicit signature that sets `nullable=False`:

```python
from snowflake.ml.registry import Registry
from snowflake.ml.model.model_signature import FeatureSpec, DataType, ModelSignature

# Define explicit signature with nullable=False
input_features = [
    FeatureSpec(name="FEATURE1", dtype=DataType.DOUBLE, nullable=False),
    FeatureSpec(name="FEATURE2", dtype=DataType.DOUBLE, nullable=False),
    # Add all your input features...
]
output_features = [
    FeatureSpec(name="OUTPUT", dtype=DataType.DOUBLE, nullable=False),
]
predict_signature = ModelSignature(inputs=input_features, outputs=output_features)

# Register with explicit signature (not sample_input_data)
reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")
mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    version_name="<NEW_VERSION>",
    signatures={"predict": predict_signature},  # Explicit signature
    conda_dependencies=["..."],
    comment="Fixed nullable=False for NumPy compatibility"
)
```

---

## Issue B: Service Not Ready

### Symptoms

- Service status shows `PENDING` or `STARTING`
- Inference requests timeout
- `mv.run()` hangs or fails

### Diagnosis

```sql
-- Check service status
DESCRIBE SERVICE <SERVICE_NAME>;

-- Check detailed instance status
SELECT SYSTEM$GET_SERVICE_STATUS('<DATABASE>.<SCHEMA>.<SERVICE_NAME>');
```

Look for:
- `status: PENDING` - service waiting for resources
- `status: STARTING` - containers being pulled/started
- `status: FAILED` - deployment failed

### Common Causes and Fixes

| Cause | Fix |
|-------|-----|
| **Testing before service ready** | Wait for status `RUNNING` and all instances showing `"status":"READY"` in `SYSTEM$GET_SERVICE_STATUS()` |
| **Compute pool not ready** | Check with `SHOW COMPUTE POOLS` - resuming a suspended pool takes a few minutes |
| **Missing privileges** | Need `USAGE` on compute pool, `BIND SERVICE ENDPOINT` for HTTP endpoints |
| **Service fails to start** | Check logs: `CALL SYSTEM$GET_SERVICE_LOGS('<SERVICE_NAME>', 0, 'model-inference')` |

---

## Issue C: OOM and Memory Issues

### Diagnosis

Check platform metrics for memory usage patterns:

```sql
-- Memory and CPU usage (look for OOM patterns)
SELECT timestamp, metric_name, value, unit, container_name
FROM TABLE(<SERVICE_NAME>!SPCS_GET_METRICS())
WHERE metric_name IN ('container.memory.usage', 'container.cpu.usage', 'container.memory.max_usage')
ORDER BY timestamp DESC
LIMIT 50;

-- GPU metrics (if applicable)
SELECT timestamp, metric_name, value, container_name
FROM TABLE(<SERVICE_NAME>!SPCS_GET_METRICS())
WHERE metric_name LIKE '%gpu%'
ORDER BY timestamp DESC;
```

### Common OOM Fixes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `container.memory.max_usage` near limit | Model too large | Use larger instance or reduce num_workers |
| Repeated container restarts | OOM kills | Check logs for "OOMKilled", reduce batch size |
| GPU memory errors in logs | Model doesn't fit | Reduce num_workers or use instance with more GPU memory |

---

## Issue D: Container Logs and Crashes

### Check Container Logs

**Model inference container:**

```sql
SELECT * FROM TABLE(<SERVICE_NAME>!SPCS_GET_LOGS())
WHERE container_name = 'model-inference'
ORDER BY timestamp DESC
LIMIT 100;
```

**Proxy container:**

```sql
SELECT * FROM TABLE(<SERVICE_NAME>!SPCS_GET_LOGS())
WHERE container_name = 'proxy'
ORDER BY timestamp DESC
LIMIT 100;
```

**Live logs (current container):**

```sql
CALL SYSTEM$GET_SERVICE_LOGS('<SERVICE_NAME>', 0, 'model-inference');
CALL SYSTEM$GET_SERVICE_LOGS('<SERVICE_NAME>', 0, 'proxy');
```

### Event Table (if service is terminated)

If the service is dead and logs are unavailable, query the event table directly:

```sql
-- Find your event table
SHOW PARAMETERS LIKE 'event_table' IN ACCOUNT;

-- Logs from event table
SELECT timestamp, value, resource_attributes
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.service.name" = '<SERVICE_NAME>'
  AND record_type = 'LOG'
ORDER BY timestamp DESC
LIMIT 100;

-- Metrics from event table
SELECT timestamp, record:metric_name::string as metric, record:value as value
FROM <EVENT_TABLE>
WHERE resource_attributes:"snow.service.name" = '<SERVICE_NAME>'
  AND record_type = 'METRIC'
ORDER BY timestamp DESC
LIMIT 100;
```

---

## Stopping Points

- ✋ Step 0: If inference type (warehouse vs SPCS) is unclear from context
- ✋ Issue A Fix: Before re-registering the model with a new signature — get explicit user approval

**Resume rule:** Upon user approval, proceed directly to the next step without re-asking.

---

## Quick Reference: Diagnostic Commands

| What to Check | Command |
|---------------|---------|
| Service status | `DESCRIBE SERVICE <SERVICE_NAME>` |
| Instance details | `SELECT SYSTEM$GET_SERVICE_STATUS('<SERVICE_NAME>')` |
| Container logs | `CALL SYSTEM$GET_SERVICE_LOGS('<SERVICE_NAME>', 0, 'model-inference')` |
| Platform metrics | `SELECT * FROM TABLE(<SERVICE_NAME>!SPCS_GET_METRICS())` |
| Model functions | `mv.show_functions()` |
| Model signature | `func['signature'].inputs` / `func['signature'].outputs` |

## Output

- Root cause identification for the inference failure
- Fix applied (re-registered model, service configuration change, etc.) or actionable remediation steps provided to user
