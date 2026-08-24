---
name: spcs-inference-online-feature-store
description: "Deploy a model to SPCS inference with automatic feature retrieval from a Postgres-backed online feature store. Use when: feature_sources_per_function, online feature store with inference service, automatic feature retrieval at inference time, entity ID only predictions, OnlineStoreType.POSTGRES with REST inference, feature store REST integration."
parent_skill: spcs-inference
path: machine-learning/spcs-inference/online-feature-store
---

# REST Inference with Online Feature Store Integration

Deploy a registered model to SPCS with `feature_sources_per_function`, so the inference service automatically fetches feature values from your Postgres-backed online feature store — callers only need to pass entity IDs.

## Prerequisites

- Model already registered in Snowflake Model Registry
- A registered `FeatureView` with `OnlineStoreType.POSTGRES` online serving enabled
- `snowflake-ml-python >= 1.43.0` (see Step 0 — check this before anything else)
- Access to a compute pool and `BIND SERVICE ENDPOINT` privilege

---

## Step 0: Version Check

**Run this first.** `feature_sources_per_function` is not available before 1.43.0, and on older versions the error surfaces late after significant setup work.

```python
from snowflake.ml import version
print(version.VERSION)  # must be >= 1.43.0
```

If the version is below 1.43.0, **stop and inform the user**:

```
feature_sources_per_function requires snowflake-ml-python >= 1.43.0.
Your current version is <VERSION>. Please upgrade before continuing:

  pip install "snowflake-ml-python>=1.43.0"

  # or via conda:
  conda install -c https://repo.anaconda.com/pkgs/snowflake "snowflake-ml-python>=1.43.0"
```

Do not proceed until the user confirms they have upgraded and re-run the version check.

---

## Step 1: Identify Your Feature View and Model

**Ask user:**
```
To wire up online feature retrieval, I need:

1. Feature store details:
   - Feature store database and schema
   - Feature view name and version

2. Model details (if not already known from this session):
   - Model name and version
   - Model database and schema

3. Service details:
   - Desired service name
   - Service database and schema
   - Compute pool
```

Ask all three questions and wait for the user's response before continuing.

### Verify the feature view is Postgres-backed

The feature view **must** have `OnlineStoreType.POSTGRES` configured — the default Hybrid Table store type does not work with `feature_sources_per_function`. Verify:

```python
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, CreationMode

session = <SESSION_SETUP>

fs = FeatureStore(
    session=session,
    database="<FS_DATABASE>",
    name="<FS_SCHEMA>",
    default_warehouse="<WAREHOUSE>",
    creation_mode=CreationMode.FAIL_IF_NOT_EXIST,
)

fv = fs.get_feature_view("<FV_NAME>", "<VERSION>")
print(fv.online_config)  # look for store_type=OnlineStoreType.POSTGRES
```

If the output does not show `OnlineStoreType.POSTGRES`, this integration path is not available. The feature view owner must update it before proceeding.

---

## Step 2: Register or Confirm the Model

If the model is already registered, skip to Step 3.

If the user needs to register the model now, **load `../../model-registry/SKILL.md`** and follow its Workflow A (Register Model). Before handing off, pass along this context:

- The user will return here after registration to deploy with `feature_sources_per_function`
- Do NOT proceed to `spcs-inference/SKILL.md` from model-registry — the deployment step is handled here in Step 3

**⚠️ CRITICAL**: When inside `model-registry/SKILL.md`, do NOT pass `feature_views=[registered_fv]` or any feature-related argument to `log_model()`. This parameter does not exist and will throw an error at registration time. Feature-to-model mapping is handled exclusively in `create_service()` in Step 3 of this skill.

Once registration is complete, return here with the registered model name and version, then continue to Step 3.

---

## Step 3: Deploy with feature_sources_per_function

**⚠️ MANDATORY**: Present summary and get user confirmation before executing.

```
Summary:
- Model: <MODEL_DATABASE>.<MODEL_SCHEMA>.<MODEL_NAME> (version <VERSION>)
- Service: <SERVICE_DATABASE>.<SERVICE_SCHEMA>.<SERVICE_NAME>
- Compute Pool: <COMPUTE_POOL>
- Feature View: <FS_DATABASE>.<FS_SCHEMA>.<FV_NAME> (version <FV_VERSION>)
- Function mapped: <FUNCTION_NAME> → <FV_NAME>

Proceed? (Yes/No)
```

Wait for the user's confirmation before executing.

Use `snowpark_session.py` from parent skill (`machine-learning/SKILL.md` → Session Setup Patterns). Write this to a separate script file and run it in background mode (service creation takes 5-15 minutes).

```python
from snowflake.ml.registry import Registry
from snowflake.ml.feature_store import FeatureStore, CreationMode

session = <SESSION_SETUP>
session.use_database("<SERVICE_DATABASE>")
session.use_schema("<SERVICE_SCHEMA>")

# Connect to the existing feature store
fs = FeatureStore(
    session=session,
    database="<FS_DATABASE>",
    name="<FS_SCHEMA>",
    default_warehouse="<WAREHOUSE>",
    creation_mode=CreationMode.FAIL_IF_NOT_EXIST,
)
registered_fv = fs.get_feature_view("<FV_NAME>", "<VERSION>")

# Get the model version
reg = Registry(session=session, database_name="<MODEL_DATABASE>", schema_name="<MODEL_SCHEMA>")
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

print("Creating service...")

mv.create_service(
    service_name="<SERVICE_NAME>",
    service_compute_pool="<COMPUTE_POOL>",
    ingress_enabled=True,
    max_instances=<MAX_INSTANCES>,
    feature_sources_per_function={"<FUNCTION_NAME>": [registered_fv]},
    # Note: currently only ONE feature view per function is supported
)

print("Service created successfully.")
```

> Use the actual function name from the model (e.g., `"predict"`, `"score"`). Discover it with `mv.show_functions()` if unsure.

Monitor service status and wait for `RUNNING` per the standard `spcs-inference/SKILL.md` Step 7 workflow.

---

## Step 4: Test with Entity-ID-Only Payload

The payload format for this integration is different from standard SPCS inference.

With `feature_sources_per_function`, callers send only entity key column(s). The service fetches all remaining features automatically from the online store.

Two supported formats:

**`dataframe_split` format (recommended):**
```python
payload = {
    "dataframe_split": {
        "index": [0, 1],
        "columns": ["<ENTITY_KEY_COLUMN>"],   # entity key column(s) only
        "data": [["<ENTITY_VALUE_1>"], ["<ENTITY_VALUE_2>"]]
    }
}
```

**`dataframe_records` format:**
```python
payload = {
    "dataframe_records": [
        {"<ENTITY_KEY_COLUMN>": "<ENTITY_VALUE_1>"},
        {"<ENTITY_KEY_COLUMN>": "<ENTITY_VALUE_2>"}
    ]
}
```

**The standard SPCS format does NOT work here:**
```python
# WRONG — do not use with feature_sources_per_function
payload = {"data": [[0, val1, val2, ...]]}
```

**Full test script (external REST call):**

```python
import requests
import json

url = "https://<endpoint-url>/<function-name>"  # e.g. /predict
headers = {
    "Authorization": 'Snowflake Token="<PAT>"',
    "Content-Type": "application/json",
}
payload = {
    "dataframe_split": {
        "index": [0],
        "columns": ["<ENTITY_KEY_COLUMN>"],
        "data": [["<ENTITY_VALUE>"]]
    }
}

response = requests.post(url, json=payload, headers=headers)
print(f"Status: {response.status_code}")
print(json.dumps(response.json(), indent=2))
```

If the user hasn't provided a PAT token yet, ask for it now — see `spcs-inference/SKILL.md` REST API Access Setup.

---

## Common Mistakes

| Mistake | What happens | Fix |
|---------|-------------|-----|
| `snowflake-ml-python < 1.43.0` | Parameter not recognized; error surfaces late | Upgrade to >= 1.43.0 (Step 0) |
| `log_model(feature_views=[fv])` | AttributeError/TypeError at registration | Remove; mapping belongs in `create_service()` only |
| Testing via `mv.run()` | Feature lookup silently ignored | Must call the REST endpoint |
| Testing via `!PREDICT` SQL | Not supported | Must call the REST endpoint |
| Standard `{"data": [[0, ...]]}` payload | 422 / unexpected errors | Use `dataframe_split` or `dataframe_records` |
| Feature view not Postgres-backed | Feature retrieval fails at runtime | FV must have `OnlineConfig(store_type=OnlineStoreType.POSTGRES)` |
| More than one FV per function | Error at service creation | Only one feature view per function is currently supported |

---

## Next Steps

- Set up REST API access → see `../SKILL.md` [REST API Access Setup](#rest-api-access-setup)
- Set up model version monitoring → load `../../model-monitor/SKILL.md`
- Debug inference errors → load `../../debug-inference/SKILL.md`
