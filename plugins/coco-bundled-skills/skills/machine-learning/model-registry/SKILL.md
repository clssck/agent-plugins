---
name: model-registry
description: "Deploy models to Snowflake Model Registry and route to inference deployment. Use when: registering serialized models, deploying trained models, logging models, logging Hugging Face models, explaining model predictions, SHAP values, feature importance. Triggers: model registry, deploy model, register model, log model, model to snowflake, hugging face, huggingface, transformers pipeline, explain model, SHAP, Shapley, feature importance, model explainability, interpret model."
---

# Model Registry Operations

## Intent Detection

Route based on user intent:

| User Says | Route To |
|-----------|----------|
| "register model", "log model", "deploy pickle", "save model to registry" | [Workflow A: Register Model](#workflow-a-register-model) |
| "deploy model", "deploy model for inference", "deploy for inference" | [Workflow B: Deploy Model Decision Tree](#workflow-b-deploy-model-decision-tree) |
| "create inference service", "SPCS inference", "inference endpoint", "serve model", "snowpark container services" | `../spcs-inference/SKILL.md` |
| "partitioned inference", "@partitioned_api", "partition-aware model", "model per partition inference", "CustomModel partition" | `partitioned-inference/SKILL.md` |
| "explain model", "SHAP", "Shapley values", "feature importance", "why did it predict", "model explainability", "interpret model" | [Workflow C: Model Explainability](#workflow-c-model-explainability) |

---

## Workflow B: Deploy Model Decision Tree

Use this workflow when user says "deploy a model" or "deploy model for inference".

### Step 1: Choose Deployment Target

**Ask user:**
```
Where would you like to deploy your model for inference?

1. Warehouse - Run inference via SQL queries (simpler, no extra infrastructure)
2. Snowpark Container Services (SPCS) - REST endpoints, GPU support, scalable
```

**⚠️ STOP**: Wait for user response.

**If Warehouse:** Route to [Workflow A: Register Model](#workflow-a-register-model)

**If SPCS:** Load `../spcs-inference/SKILL.md` and follow its workflow.

---

## When to Use

**Register Model (Workflow A):**
- User has a model object in memory (just trained in the current session, snowsight only)
- User has a serialized model file (`.pkl`, `.ubj`, `.json`, `.pt`, `.h5`, etc.)
- User wants to register/log a model to Snowflake Model Registry

**SPCS Inference Service (`../spcs-inference/SKILL.md`):**
- User has a model already registered in the registry
- User wants to deploy the model for real-time inference via SPCS
- User wants to create an HTTP endpoint for model predictions

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

**⚠️ Conda Environment for WAREHOUSE Target:** When targeting WAREHOUSE, use a conda environment with `snowflake-ml-python` installed via conda (not pip). **Use the same Python version the model was trained with** to avoid pickle compatibility issues. Create with: `conda create -n snowml python=<VERSION> snowflake-ml-python -c https://repo.anaconda.com/pkgs/snowflake`

## API Reference

For understanding `ModelVersion` methods and their signatures (e.g., `show_functions()`, `get_metric()`, `run()`, `create_service()`), refer to the official documentation:

**ModelVersion API Reference:** https://docs.snowflake.com/en/developer-guide/snowpark-ml/reference/latest/api/model/snowflake.ml.model.ModelVersion

---

## Workflow A: Register Model

### Step 0: Check for Recent Model Context

**⚠️ IMPORTANT:** Check if you have context from a recent training session:
- Model variable name or file path
- Framework used (sklearn, xgboost, lightgbm, pytorch, tensorflow, huggingface/transformers)
- Training data that can be used as sample input

**If called from `ml-development/SKILL.md` with full context** (model variable, framework, sample input data, AND model name, version, database, schema already validated): Skip directly to **Step 3 (Determine Model Type)** — information gathering and conflict checking are already done.

**If model context exists but no registry details:** Skip to Step 2 — only ask for model name and database/schema.

**If no recent context:** Proceed to Step 1.

### Step 1: Gather Information

**If no recent context**, ask user for:
- Model file path (e.g., `.pkl`, `.ubj`, `.json`, `.pt`) OR confirm model variable in notebook kernel memory
- Model name for Snowflake
- Model version *(optional)* — user can provide a version (e.g., `v1`, `v2`) or skip to let `log_model()` auto-generate one
- Database and Schema to register this model (Do not use ask_user_question tool for this one, just stop and wait for user response)
- Framework (sklearn, xgboost, lightgbm, pytorch, tensorflow, huggingface/transformers, or other)
- Sample input data or schema description (if needed)
- Additional dependencies

**⚠️ STOP**: Wait for user response.

### Step 2: Check if Model Version Exists

**⚠️ CRITICAL:** The user's intent is to register a NEW model. Do NOT treat an existing model or version as the task being complete. Always proceed with registration — resolve any naming/version conflicts by proposing the next available version.

**If user provided a specific version:**

```sql
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
```

- **If version exists**: Ask user to choose new version (v2, v3...) or new model name
- **If "does not exist" error**: Proceed with the provided version

**⚠️ STOP**: Wait for user choice if model already exists.

**If user chose auto-generate:** Skip the conflict check — `log_model()` will generate a unique version automatically. Omit the `version_name` parameter from the `log_model()` call.

### Step 3: Determine Model Type

Based on the framework:

| Framework | Model Type | Approach |
|-----------|------------|----------|
| sklearn, xgboost, lightgbm, pytorch, tensorflow | Built-in | Direct `log_model()` |
| Hugging Face (transformers) | Built-in | `hugging-face-models/SKILL.md` |
| Other (pycaret, custom, etc.) | Custom | Requires `CustomModel` wrapper |

### Step 4: Generate Registration Code

Set up the session following your loaded environment guide, then generate the registration code.

**For in-memory model (model just trained in current session): only in snowsight/snowflake platform**

```python
import pandas as pd
from snowflake.ml.registry import Registry

# Session setup per environment guide
# e.g., get_active_session() or create_snowpark_session()
session = <SESSION_SETUP>

# setup database and schema
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")

reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")

# Use the model variable from the current session (e.g., model, clf, regressor)
# sample_input: feature columns only (no target)
sample_input = <SAMPLE_DATA_FROM_TRAINING>  # e.g., X_train.head(5)

mv = reg.log_model(
    <MODEL_VARIABLE>,  # e.g., model, clf, xgb_model
    model_name="<MODEL_NAME>",
    version_name="<VERSION_NAME>",  # e.g., "v1", "v2" - determined in Step 2
    sample_input_data=sample_input,
    conda_dependencies=["<FRAMEWORK>", "<OTHER_DEPS>"],  # Snowflake conda channel (warehouse) or conda-forge (SPCS)
    target_platforms=["WAREHOUSE", "SNOWPARK_CONTAINER_SERVICES"],
    comment="<DESCRIPTION>"
)

print(f"Model registered: {mv.model_name} version {mv.version_name}")
```

**For model loaded from file:**

```python
import pandas as pd
from snowflake.ml.registry import Registry

# Session setup per environment guide
session = <SESSION_SETUP>

# setup database and schema
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")

reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")

# Load model using framework-appropriate method
# sklearn/lightgbm (pickle): pickle.load() or joblib.load()
# xgboost (.ubj/.json): xgb.Booster(); booster.load_model()
# pytorch (.pt): torch.load()
# tensorflow (.h5): tf.keras.models.load_model()
model = <LOAD_MODEL_CODE>

sample_input = pd.DataFrame(<SAMPLE_DATA>)

mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    version_name="<VERSION_NAME>",  # e.g., "v1", "v2" - determined in Step 2
    sample_input_data=sample_input,
    conda_dependencies=["<FRAMEWORK>", "<OTHER_DEPS>"],  # Snowflake conda channel (warehouse) or conda-forge (SPCS)
    target_platforms=["WAREHOUSE", "SNOWPARK_CONTAINER_SERVICES"],
    comment="<DESCRIPTION>"
)

print(f"Model registered: {mv.model_name} version {mv.version_name}")
```

**For Custom/Unsupported Model Types:**

```python
import pandas as pd
from snowflake.ml.registry import Registry
from snowflake.ml.model import custom_model

# Session setup per environment guide
session = <SESSION_SETUP>

model_context = custom_model.ModelContext(
    model_file="<MODEL_FILE_PATH>"
)

class MyCustomModel(custom_model.CustomModel):
    def __init__(self, context: custom_model.ModelContext) -> None:
        super().__init__(context)
        # Load model using framework-appropriate method
        self.model = <LOAD_MODEL_CODE>

    @custom_model.inference_api
    def predict(self, input_df: pd.DataFrame) -> pd.DataFrame:
        predictions = self.model.predict(input_df)
        return pd.DataFrame({"prediction": predictions})

my_model = MyCustomModel(model_context)

sample_input = pd.DataFrame(<SAMPLE_DATA>)
output = my_model.predict(sample_input)

reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")

mv = reg.log_model(
    my_model,
    model_name="<MODEL_NAME>",
    version_name="<VERSION_NAME>",  # e.g., "v1", "v2" - determined in Step 2
    sample_input_data=sample_input,
    conda_dependencies=["<DEPS>"],  # Snowflake conda channel (warehouse) or conda-forge (SPCS)
    target_platforms=["WAREHOUSE", "SNOWPARK_CONTAINER_SERVICES"],
    comment="<DESCRIPTION>"
)

print(f"Model registered: {mv.model_name} version {mv.version_name}")
```

**Explainability (sklearn, XGBoost, LightGBM, CatBoost only):** Explainability is enabled automatically when the model is registered with `sample_input_data` and a warehouse `target_platform`. Ensure the generated code uses `sample_input_data` (not `signatures`) and includes `"WAREHOUSE"` in `target_platforms`. To disable, add `options={"enable_explainability": False}`. Explainability cannot be added after registration.

### Step 5: Execute and Verify

**Snowsight (Notebook)**: Test model loading → test prediction → run registration → verify with `reg.show_models()`

**CLI (Script)**: Write complete script, then ask user confirmation before executing.

**⚠️ MANDATORY:** Present summary and wait for user approval before executing.

Follow the execution instructions in your loaded environment guide. If execution fails, read complete error, fix, and ask user again before re-executing.

## log_model() Parameters

| Parameter | Description | Required |
|-----------|-------------|----------|
| `model` | Python model object | Yes |
| `model_name` | Name in registry | Yes |
| `version_name` | Version identifier. Optional — omit to auto-generate. | Optional |
| `sample_input_data` | DataFrame with feature columns only (exclude target/label). Used for schema inference and ML lineage. Use a Snowpark DataFrame (not pandas) to enable lineage tracking. | Yes* |
| `conda_dependencies` | List of conda packages (for warehouse) | See below |
| `pip_requirements` | List of pip packages (requires artifact_repository_map for warehouse) | See below |
| `target_platforms` | Target deployment platforms | See below |
| `artifact_repository_map` | Map of package indexes for non-conda packages | See below |

*Or provide `signatures` instead.

## Dependencies for Warehouse vs SPCS

**For WAREHOUSE target:**
- Use `conda_dependencies` for packages in Snowflake conda channel
- OR use `pip_requirements` + `artifact_repository_map` for PyPI packages

**For SPCS only:**
- Can use `pip_requirements` directly without `artifact_repository_map`
- `conda_dependencies` are loaded from conda-forge (not Snowflake conda channel)

## target_platforms Strategy

**Default approach:** Try `["WAREHOUSE", "SNOWPARK_CONTAINER_SERVICES"]` first to enable both warehouse inference and SPCS deployment.

**Fallback:** If `log_model()` fails with warehouse target (e.g., due to unsupported dependencies or model size), retry with `["SNOWPARK_CONTAINER_SERVICES"]` only.

```python
# First attempt: try both platforms (use conda_dependencies for warehouse compatibility)
try:
    mv = reg.log_model(
        model,
        model_name="<MODEL_NAME>",
        version_name="<VERSION>",
        sample_input_data=sample_input,
        conda_dependencies=["<DEPS>"],  # Snowflake conda channel (warehouse) or conda-forge (SPCS)
        target_platforms=["WAREHOUSE", "SNOWPARK_CONTAINER_SERVICES"],
    )
except Exception as e:
    # Fallback: SPCS only (can use pip_requirements directly)
    mv = reg.log_model(
        model,
        model_name="<MODEL_NAME>",
        version_name="<VERSION>",
        sample_input_data=sample_input,
        pip_requirements=["<DEPS>"],
        target_platforms=["SNOWPARK_CONTAINER_SERVICES"],
    )
```

## Using artifact_repository_map for Non-Conda Packages

When your model depends on packages **not available in the Snowflake conda channel**, use `artifact_repository_map` to specify PyPI as the package source.

Use the shared `pypi_shared_repository` for public PyPI packages:

```python
mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    version_name="<VERSION>",
    sample_input_data=sample_input,
    pip_requirements=["scikit-learn", "shap>=0.42.0"],
    target_platforms=["WAREHOUSE", "SNOWPARK_CONTAINER_SERVICES"],
    artifact_repository_map={
        "shap": "pypi_shared_repository"  # Map non-conda packages to PyPI
    },
)
```

- **Keys**: Package names (must also be listed in `pip_requirements`)
- **Values**: Use `pypi_shared_repository` for public PyPI packages

## Common Issues (Workflow A)

- **Version exists**: Use `SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>` to check if model and versions exist. Increment version or rename
- **Not serializable**: Ensure saved with `pickle.dump()` or `joblib.dump()`
- **Schema inference fails**: Provide explicit `signatures`
- **Package not found in Snowflake channel**: Use `artifact_repository_map` to specify PyPI or custom repository (see [Using artifact_repository_map](#using-artifact_repository_map-for-non-conda-packages))
- **Inference errors after registration**: For inference issues (dtype errors, TypeError, service failures, OOM), see `../debug-inference/SKILL.md`

### Step 6: Post-Registration Verification

**⚠️ MANDATORY:** After registration completes, verify the model was registered correctly before proceeding.

**Run verification checks:**

```sql
-- 1. Verify model and version exist
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;

-- 2. Check available functions/methods (only run after confirming model exists above — errors if model not found)
-- Include VERSION = '<VERSION>' to check a specific version; omit to use the default version
SHOW FUNCTIONS IN MODEL <DATABASE>.<SCHEMA>.<MODEL_NAME> VERSION '<VERSION>';
```

Confirm the model name and version appear in Step 1 output before running Step 2.

**Verification checklist:**

| Check | Expected Result |
|-------|-----------------|
| `SHOW MODELS LIKE` includes model | Model name and version listed in results (empty = not registered) |
| `SHOW FUNCTIONS IN MODEL` returns methods | At least one method (e.g., `PREDICT`, `PREDICT_PROBA`) |

**If verification fails:**
- Model not found: Check database/schema context, re-run registration
- Version not found: Registration may have failed silently, check for errors
- No functions: Sample input may have been invalid, re-register with correct schema

**⚠️ STOP**: Only proceed to next steps after all verification checks pass.

---

### Step 7: Next Steps

**If target_platforms includes WAREHOUSE:**

Ask user what they'd like to do:
1. **Test warehouse inference** - Run a sample prediction query
2. **Explain predictions** - Get SHAP-based feature explanations ([Workflow C](#workflow-c-model-explainability)) *(sklearn, XGBoost, LightGBM, CatBoost only)*
3. **Deploy to SPCS** - Create an inference service (Workflow B)
4. **Set up monitoring** — Monitor a version (load `../model-monitor/SKILL.md`) or services behind a gateway (load `../gateway-ab-testing/SKILL.md`)
5. **Done** - Finish here

**If target_platforms is SPCS only:**

Warehouse inference is not available. Ask user:
1. **Deploy to SPCS** - Create an inference service (Workflow B)
2. **Set up monitoring** — Monitor a version (load `../model-monitor/SKILL.md`) or services behind a gateway (load `../gateway-ab-testing/SKILL.md`)
3. **Done** - Finish here

**⚠️ STOP**: Wait for user response.

**If user chooses to test warehouse inference:**

**⚠️ Always specify the version explicitly.** Use the version from Step 2 (e.g., `V1`, `V2`)—do not rely on the default version.

Run a sample prediction using SQL or Python. Use the method name from the model (e.g., `PREDICT`, `PREDICT_PROBA`, `TRANSFORM`).

**SQL Syntax:**

Use `MODEL(model_name, version)!METHOD(...)` syntax. Version names are **unquoted identifiers**.

```sql
SELECT MODEL(<DATABASE>.<SCHEMA>.<MODEL_NAME>, <VERSION>)!<METHOD_NAME>(col1, col2, col3) AS result
FROM <INPUT_TABLE>
LIMIT 10;

-- Extract specific output field
SELECT MODEL(<DATABASE>.<SCHEMA>.<MODEL_NAME>, <VERSION>)!<METHOD_NAME>(col1, col2, col3):output_feature_0 AS result
FROM <INPUT_TABLE>;
```

**⚠️ Important:** Do NOT quote version names. Use `V2` not `'V2'`.

**Python:**
```python
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")
# Check available methods
print(mv.show_functions())
# Run inference
result = mv.run(test_data, function_name="<method_name>")
print(result)
```

**If user chooses SPCS deployment:** Proceed to Workflow B.

**When to use Warehouse vs SPCS Inference:**

| Use Case | Recommendation |
|----------|----------------|
| Ad-hoc queries, testing | Warehouse inference |
| Batch predictions | Warehouse inference |
| Real-time API endpoint | SPCS inference (Workflow B) |
| High-throughput, low-latency | SPCS inference (Workflow B) |

## Output

- Model registered in Snowflake Model Registry
- Model name and version for reference
- Ready for warehouse inference (SQL) or SPCS deployment (load `../spcs-inference/SKILL.md`)

---

## Workflow C: Model Explainability

SHAP-based model explainability for registered models. Automatically generates an `explain` method that returns Shapley values (per-feature contribution to each prediction).

**⚠️ Warehouse only.** Explainability is not supported for SPCS-only models.

**Supported frameworks:** sklearn (incl. pipelines), XGBoost, LightGBM, CatBoost. **Not supported:** PyTorch, TensorFlow, HuggingFace.

### Running Explanations

**Python:**
```python
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")
explanations = mv.run(input_data, function_name="explain")
```

**SQL (EXPLAIN is a table function — use lateral join syntax, not `MODEL()!METHOD()`):**
```sql
WITH MV_ALIAS AS MODEL <DATABASE>.<SCHEMA>.<MODEL_NAME> VERSION <VERSION>
SELECT t.*, e.*
FROM <INPUT_TABLE> t, TABLE(MV_ALIAS!EXPLAIN(t.col1, t.col2, ...)) e;
```

Output columns are named `<feature>_explanation` — each value is that feature's Shapley contribution to the prediction.

### Visualizing Explanations

Use `snowflake.ml.monitoring.explain_visualize` for built-in SHAP plots (Altair charts). Strip the `_explanation` suffix from explanation columns so they match feature column names before passing to plot functions.

**Snowflake Notebooks:** Call `alt.renderers.enable("mimetype")` before rendering any plots — this is required for Vega content to display.

```python
from snowflake.ml.monitoring.explain_visualize import plot_force, plot_influence_sensitivity, plot_violin

# Force plot — single-row explanation (accepts pandas Series or Snowpark Row)
plot_force(shap_row=shap_df.iloc[0], features_row=feature_df.iloc[0], base_value=predictions.mean())

# Influence sensitivity — pass a single feature's Series
plot_influence_sensitivity(shap_values=shap_df["<FEATURE>"], feature_values=feature_df["<FEATURE>"])

# Violin — SHAP distribution per feature (pandas, Snowpark, or numpy)
plot_violin(shap_df=shap_df, feature_df=feature_df)
```

### Common Issues

- **No `explain` method available**: Model was registered with `signatures` instead of `sample_input_data`, or with SPCS-only target, or explainability was explicitly disabled. Cannot be added to an existing version — **⚠️ STOP — confirm with the user before proceeding.** Re-log with a new `version_name`, `sample_input_data`, and a warehouse `target_platform`.

---

## Sub-Skills

### partitioned-inference

Partitioned inference using `@partitioned_api` decorator. Deploy models that run different submodels per data partition (store, region, etc.). Supports both stateless (train+predict together) and stateful (pre-trained models via `ModelContext`) workflows.

**When to route here:**
- User wants to run inference with different models per partition
- User mentions `@partitioned_api`, `partitioned_inference_api`, or `CustomModel` with partitions
- User has trained models per partition (via MMT) and wants to deploy for inference
