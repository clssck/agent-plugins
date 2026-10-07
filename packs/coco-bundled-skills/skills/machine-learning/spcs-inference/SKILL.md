---
name: spcs-inference
description: "Deploy models from Snowflake Model Registry to Snowpark Container Services for real-time inference. Use when: creating inference services, SPCS deployment, REST endpoints for models, GPU inference. Triggers: create inference service, SPCS inference, inference endpoint, serve model, deploy to SPCS, model endpoint."
parent_skill: model-registry
---

# SPCS Inference Service Deployment

Deploy a registered model to Snowpark Container Services for real-time inference.

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## Prerequisites

- Model already registered in Snowflake Model Registry (see `../model-registry/SKILL.md`)
- Access to a compute pool (GPU or CPU)
- `BIND SERVICE ENDPOINT` privilege for HTTP endpoints

---

## Intent Detection

If the user's request includes any of the following signals, **load `online-feature-store/SKILL.md` and follow its workflow** instead of the standard service creation flow below:

- "feature_sources_per_function"
- "automatic feature retrieval" at inference time
- "online feature store" combined with inference / service / REST / deploy
- "postgres online store" or "OnlineStoreType.POSTGRES"
- "entity ID only" requests or predictions
- Feature store → inference service integration

---

## Workflow: Create Inference Service

### Step 1: Identify the Model

If coming from model registration, use that model reference. Otherwise ask for:
- Model name and version
- Database/Schema where the model is registered

**⚠️ STOP**: Wait for response if not already known.

### Step 2: Choose Service Database and Schema

**Ask user:**
```
Which database and schema would you like to deploy the inference service in?

Note: This can be different from where the model is registered.
```

**⚠️ STOP**: Wait for user response.

### Step 3: Select Compute Pool

```sql
SHOW COMPUTE POOLS;
```

Present available compute pools to the user, indicating GPU vs CPU, nodes, and services running:

**Ask user:**
```
Available compute pools:

| Pool Name | Instance Family | GPUs/Node | Min/Max Nodes | Active Nodes | State | Services |
|-----------|-----------------|-----------|---------------|--------------|-------|----------|
| POOL_A    | GPU_NV_M        | 4 x A10G  | 1 / 4         | 2            | ACTIVE | 2        |
| POOL_B    | CPU_X64_M       | None      | 1 / 2         | 0            | SUSPENDED | 0      |
| ...       | ...             | ...       | ...           | ...          | ... | ...      |

Which compute pool would you like to use?

Recommendation: Use a GPU compute pool for models that require GPU inference 
(e.g., deep learning, transformers, large embeddings).
```

**⚠️ STOP**: Wait for user response.

**GPU Reference:**

| Instance Family | GPUs per Node | GPU Type |
|-----------------|---------------|----------|
| GPU_NV_S        | 1             | A10G     |
| GPU_NV_M        | 4             | A10G     |
| GPU_NV_L        | 8             | A100     |

If no suitable pool exists, offer to create one:

```sql
CREATE COMPUTE POOL IF NOT EXISTS <POOL_NAME>
    MIN_NODES = 1 MAX_NODES = <N>
    INSTANCE_FAMILY = '<INSTANCE_FAMILY>'
    AUTO_RESUME = TRUE;
```

### Step 4: Configure Max Instances

**Ask user:**
```
How many max instances would you like for the service?

Max instances controls horizontal scaling - each instance is a separate container 
replica that can handle inference requests in parallel. More instances = higher 
throughput for concurrent requests.

- 1 instance: Suitable for development/testing or low traffic
- 2+ instances: Recommended for production workloads expecting higher concurrent load

The service will automatically scale between min_instances and max_instances based on demand.

Enter max_instances (default: 1):
```

**⚠️ STOP**: Wait for user response.

### Step 5: Check Existing Service

```sql
SHOW SERVICES LIKE '<SERVICE_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
```

If exists, ask user: rename, delete & recreate, or keep existing.

### Step 5b: Configure Auto-Capture (Inference Logging)

**Ask user:**
```
Would you like to enable Auto-Capture for this inference service?

Auto-Capture automatically logs every request and response processed by the service
into an inference table. This gives you:
- Historical inference data for debugging and analysis
- Real-world production data for retraining and improving models
- Data for A/B testing and shadow testing

Important notes:
- Auto-Capture is IMMUTABLE — you cannot enable or disable it on an existing service.
  You must recreate the service to change this setting.
- Not supported for vLLM or HuggingFace inference engines.

Enable Auto-Capture? (Yes/No, default: No):
```

**⚠️ STOP**: Wait for user response.

**If user wants autocapture on a legacy model** (service creation fails with inference table error), guide them to clone the model first:

```sql
CREATE MODEL <NEW_MODEL_NAME> WITH VERSION <VERSION_NAME> FROM MODEL <OLD_MODEL_NAME> VERSION <OLD_VERSION>;
```

Then use the new cloned model for service creation with `autocapture=True`.

### Step 5c: Select Inference Engine

**Ask the user:**

```
Which inference engine should be used for this service?

1. **Python Generic** (default) — for sklearn, XGBoost, LightGBM, HuggingFace non-LLM, and custom models
2. **vLLM** — for HuggingFace text-generation and image-text-to-text models

Based on your model (<MODEL_NAME>/<TYPE>), I recommend: <RECOMMENDATION>
```

**⚠️ STOP**: Wait for user response.

> **If vLLM:** Auto-Capture is not supported — skip Step 5b or warn the user if they already enabled it.

| Choice | `inference_engine_options` in Step 6 code |
|--------|-------------------------------------------|
| Python Generic (default) | omit, or `{"engine": InferenceEngine.PYTHON_GENERIC}` |
| vLLM | `{"engine": InferenceEngine.VLLM}` |

---

### Step 6: Create Service

**⚠️ MANDATORY:** Present summary and get user confirmation before executing:

```
Summary:
- Model: <MODEL_DATABASE>.<MODEL_SCHEMA>.<MODEL_NAME> (version <VERSION>)
- Service: <SERVICE_DATABASE>.<SERVICE_SCHEMA>.<SERVICE_NAME>
- Compute Pool: <COMPUTE_POOL> (GPU/CPU)
- Max Instances: <MAX_INSTANCES>
- Inference Engine: <ENGINE or default>
- Auto-Capture: <Enabled/Disabled>

Proceed? (Yes/No)
```

**⚠️ STOP**: Wait for user confirmation before proceeding.

---

#### Service Creation Code

Set up the session following your loaded environment guide, then generate the service creation code.Service creation takes 5-15 minutes. You MUST:

Use `snowpark_session.py` from parent skill (`machine-learning/SKILL.md` → Session Setup Patterns). Copy the helper script to the working directory and import it.

**DO NOT** combine service creation with model registration in the same script.
**DO NOT** run service creation inline - it will timeout.

**For GPU compute pool:**

```python
from snowflake.ml.registry import Registry

# Session setup per environment guide
session = <SESSION_SETUP>
session.use_database("<SERVICE_DATABASE>")
session.use_schema("<SERVICE_SCHEMA>")

reg = Registry(session=session, database_name="<MODEL_DATABASE>", schema_name="<MODEL_SCHEMA>")
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

print("Creating service...")

mv.create_service(
    service_name="<SERVICE_NAME>",
    service_compute_pool="<COMPUTE_POOL>",
    ingress_enabled=True,
    max_instances=<MAX_INSTANCES>,
    # gpu_requests: omitted — defaults to all GPUs available on the compute pool node.
    # Specify only if the user wants to use fewer GPUs (e.g., gpu_requests="1" on a 4-GPU node).
    inference_engine_options=<{"engine": InferenceEngine.VLLM} or {"engine": InferenceEngine.PYTHON_GENERIC} or omit>,
    autocapture=<True if user enabled Auto-Capture in Step 5b, otherwise omit this parameter>,
)

print("Service created successfully.")
```

**For CPU compute pool:**

```python
from snowflake.ml.registry import Registry

# Session setup per environment guide
session = <SESSION_SETUP>
session.use_database("<SERVICE_DATABASE>")
session.use_schema("<SERVICE_SCHEMA>")

reg = Registry(session=session, database_name="<MODEL_DATABASE>", schema_name="<MODEL_SCHEMA>")
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

print("Creating service...")

mv.create_service(
    service_name="<SERVICE_NAME>",
    service_compute_pool="<COMPUTE_POOL>",
    ingress_enabled=True,
    max_instances=<MAX_INSTANCES>,
    inference_engine_options=<{"engine": InferenceEngine.VLLM} or {"engine": InferenceEngine.PYTHON_GENERIC} or omit>,
    autocapture=<True if user enabled Auto-Capture in Step 5b, otherwise omit this parameter>,
)

print("Service created successfully.")
```

---

#### Execution: CLI

**⚠️ CRITICAL - MUST FOLLOW THIS PATTERN for CLI:**

Service creation takes 5-15 minutes. You MUST:
1. Write the code to a **separate Python script file** (e.g., `/path/to/create_service.py`)
2. Execute it in **background mode**
3. Monitor via **SQL** while it runs (Step 7)

**DO NOT** combine service creation with model registration in the same script.
**DO NOT** run service creation inline - it will timeout.

Execute the script using the Bash tool with `run_in_background=true`:

```
Tool: Bash
Command: SNOWFLAKE_CONNECTION_NAME=<connection> python /absolute/path/to/create_service.py
run_in_background: true
```

This returns a `shell_id` immediately. Use `bash_output` tool with that `shell_id` to check progress.

#### Execution: Snowsight (Notebook)

Run the service creation code in a notebook cell. Service creation takes 5-15 minutes. Wait for the cell execution to finish

---

### Step 7: Monitor Service Status (CLI Only)

**⚠️ CRITICAL:** While the service creation runs:

1. **Check script progress** (CLI: use `bash_output` tool with the `shell_id`)
2. **Monitor service status** using SQL

Service creation typically takes 5-15 minutes. Poll every 60 seconds.

---

**Check service status (SQL):**

```sql
DESCRIBE SERVICE <SERVICE_DATABASE>.<SERVICE_SCHEMA>.<SERVICE_NAME>;
```

**Or use pattern matching for multiple services:**

```sql
SHOW SERVICES LIKE '<SERVICE_NAME>' IN SCHEMA <SERVICE_DATABASE>.<SERVICE_SCHEMA>;
```

**Service Status Reference:**

| Status | Meaning | Action |
|--------|---------|--------|
| `PENDING` | Service registered, waiting for resources | Wait 60s, poll again |
| `STARTING` | Containers being pulled and started | Wait 60s, poll again |
| `RUNNING` | Service is ready for inference | Success - proceed to Step 8 |
| `FAILED` | Deployment failed | Fetch logs (see below) |
| `SUSPENDED` | Service suspended | Run `ALTER SERVICE <SERVICE_NAME> RESUME;` |

---

**When status is RUNNING, get endpoint URL:**

```sql
SHOW ENDPOINTS IN SERVICE <SERVICE_DATABASE>.<SERVICE_SCHEMA>.<SERVICE_NAME>;
```

Report the `ingress_url` to user.

---

**Check instance-level status (optional, more detail):**

```sql
SELECT SYSTEM$GET_SERVICE_STATUS('<SERVICE_DATABASE>.<SERVICE_SCHEMA>.<SERVICE_NAME>');
```

Returns JSON with each container's status. Look for `"status":"READY"` and `"message":"Running"` on all instances before testing.

---

**If status is FAILED, fetch logs for debugging:**

```sql
CALL SYSTEM$GET_SERVICE_LOGS('<SERVICE_DATABASE>.<SERVICE_SCHEMA>.<SERVICE_NAME>', 0, 'model-inference');
```

**⚠️ CRITICAL: Route to debug-inference on any error.** After fetching logs, if they contain ANY error (e.g., `AttributeError`, pickle/deserialization failures, `TypeError`, `ImportError`, `OOMKilled`, ufunc errors, or any other runtime exception), **immediately load `../debug-inference/SKILL.md`** and follow its diagnostic workflow. Do NOT attempt to fix the issue directly without loading the debug skill first.

---

**Timeout:** If service hasn't reached RUNNING after ~20 minutes, inform user and provide manual check command.

---

**Python polling template (use whenever writing a wait-for-service loop):**

```python
import time

MAX_WAIT_SECS = 1200  # 20 minutes
POLL_INTERVAL = 15
elapsed = 0

while elapsed < MAX_WAIT_SECS:
    rows = session.sql(
        "DESCRIBE SERVICE <SERVICE_DATABASE>.<SERVICE_SCHEMA>.<SERVICE_NAME>"
    ).collect()
    status = rows[0]["status"]
    print(f"Service status: {status}")

    if status == "RUNNING":
        break
    if status in ("FAILED", "DELETING", "SUSPENDED"):
        raise RuntimeError(f"Service reached terminal status: {status}")

    time.sleep(POLL_INTERVAL)
    elapsed += POLL_INTERVAL
else:
    raise TimeoutError(f"Service did not reach RUNNING after {MAX_WAIT_SECS}s")

print("Service is RUNNING and ready for inference!")
```

**CRITICAL — two distinct status levels:**
- **Service-level** (`DESCRIBE SERVICE` / `SHOW SERVICES` → `status` column): break on `"RUNNING"`. Valid values: `PENDING`, `STARTING`, `RUNNING`, `FAILED`, `SUSPENDING`, `SUSPENDED`, `DELETING`. There is **no** `"READY"` at this level.
- **Container-level** (`SYSTEM$GET_SERVICE_STATUS()` JSON → per-container `"status"` field): individual containers report `"READY"` when healthy. This is separate from service-level status.

Do **not** use `"READY"` as the break condition in a service-level polling loop — that loop will never exit.

### Step 8: Validate and Test Service

**⚠️ CRITICAL: Only test inference when service is fully ready**

Before testing or validating the inference endpoint:
1. Service status must be **RUNNING** (not PENDING or STARTING)
2. All instances must be ready - check with `SYSTEM$GET_SERVICE_STATUS()`:
   ```sql
   SELECT SYSTEM$GET_SERVICE_STATUS('<DATABASE>.<SCHEMA>.<SERVICE_NAME>');
   ```
   Verify all containers show `"status":"READY"` and `"message":"Running"`
3. If some instances show `"status":"PENDING"`, wait for them to become READY

**Why this matters:** Testing with partial instances can cause timeouts or inconsistent results. The service load balancer may route requests to instances that are still starting up.

---

#### Step 8a: Confirm Model Version and Functions

**If coming from a continuous workflow** (Steps 1-8 in this session):
- Model name, version, and functions are already known from earlier steps
- Skip to Step 8b using the known values

**If validating an existing service without prior context:**

First, identify which model version the service is using:
```sql
DESCRIBE SERVICE <DATABASE>.<SCHEMA>.<SERVICE_NAME>;
```

Look at `managing_object_name` column to find the model (e.g., `SSARDANA_DB.NEW_EXP.MY_MODEL`).

Then verify the model exists and discover available functions:

**SQL:**
```sql
-- 1. Verify model exists (returns empty list if not found — safe, never errors)
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;

-- 2. Discover available functions (only run after confirming model exists above — errors if model not found)
-- Include VERSION = '<VERSION>' if version is known; omit to use the default version
SHOW FUNCTIONS IN MODEL <DATABASE>.<SCHEMA>.<MODEL_NAME> VERSION '<VERSION>';
```

Look at the output from Step 2 for available function names (e.g., `PREDICT`, `PREDICT_PROBA`). Use one of these function names in all subsequent queries.

**Python:**
```python
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")
print(mv.show_functions())
```

This returns a list of available functions with their input/output signatures.

**Reference:** [ModelVersion API Documentation](https://docs.snowflake.com/en/developer-guide/snowpark-ml/reference/latest/api/model/snowflake.ml.model.ModelVersion) for additional methods like `mv.get_model_signature()`.

**⚠️ IMPORTANT:** Do NOT assume `PREDICT` exists. Different models expose different inference methods.

---

#### Step 8b: Test Inference

**Use the function name discovered in Step 8a for all paths:**

**SQL:**
```sql
-- Replace <FUNCTION_NAME> with actual function from Step 8a
SELECT <SERVICE_NAME>!<FUNCTION_NAME>(col1, col2, ...) FROM input_table;
```

**Python (mv.run):**
```python
# function_name must match one from show_functions() (lowercase)
result = mv.run(test_data, function_name="<function_name>", service_name="<SERVICE_NAME>")
```

**REST API:**

There are two ways to call the REST API depending on where you're calling from:

| Calling From | Endpoint Type | Authentication Required |
|--------------|---------------|------------------------|
| **Snowsight Notebook** | Internal endpoint | No (session context) |
| **External (CLI, apps)** | Public ingress URL | Yes (PAT token) |

---

**REST API from Snowsight Notebook (No Auth Required):**

When calling from a Snowsight Notebook, use the **internal endpoint** which requires no authentication.

First, get the internal endpoint using `mv.list_services()`:

```python
# Get all services for this model version
services_df = mv.list_services()
print(services_df)
```

**`list_services()` returns a DataFrame with these columns:**
- `name`: The name of the service
- `status`: The status of the service
- `inference_endpoint`: The public endpoint (gives privatelink endpoint if session uses privatelink connection)
- `internal_endpoint`: The internal endpoint of the service (use this from notebooks!)
- `autocapture_enabled`: Whether service has autocapture enabled

**Reference:** [ModelVersion.list_services() API Documentation](https://docs.snowflake.com/en/developer-guide/snowpark-ml/reference/latest/api/model/snowflake.ml.model.ModelVersion)

Then make REST calls using the `internal_endpoint`:

```python
import requests

# Get the internal endpoint from list_services() output
services_df = mv.list_services()
internal_endpoint = services_df[services_df['name'] == '<SERVICE_NAME>']['internal_endpoint'].iloc[0]

# Internal endpoint format: http://<service-name>.<namespace>.svc.spcs.internal:5000
# Call the endpoint - NO authorization header needed!
url = f"{internal_endpoint}/<function_name>"  # e.g., /predict or /predict-proba
payload = {"data": [[0, val1, val2, val3]]}

response = requests.post(url, json=payload)
print(response.json())
```

**Key points for Snowsight Notebook:**
- Use `mv.list_services()` to get the `internal_endpoint` column value
- Internal endpoints use HTTP (not HTTPS) on port 5000
- **No `Authorization` header needed** - the notebook session context handles authentication
- This only works from within Snowflake (notebooks, stored procedures, UDFs)

---

**REST API from External Clients (Auth Required):**

Requires: network policy allowing client IP, PAT token, service role grant.

See [REST API Access Setup](#rest-api-access-setup) for full setup instructions.

**⚠️ IMPORTANT: URL Path Transformation**

In REST URLs, underscores (`_`) in method names are replaced by dashes (`-`).

| Python Method | REST Endpoint |
|---------------|---------------|
| `predict()` | `/predict` |
| `predict_proba()` | `/predict-proba` |
| `predict_log_proba()` | `/predict-log-proba` |
| `my_custom_method()` | `/my-custom-method` |

```python
import requests

url = "https://<endpoint-url>/<function_name>"  # Use function from Step 8a (with dashes)
headers = {"Authorization": "Snowflake Token=\"<PAT>\""}
response = requests.post(url, json={"data": [[0, val1, val2]]}, headers=headers)
```

**Note:** When calling from within Snowflake (e.g., a Snowflake notebook), no authentication headers are needed — the request is already authenticated by the session context.

See [REST API Access Setup](#rest-api-access-setup) for details.

#### Step 8b-ii: View Captured Inference Data

**⚠️ This step only applies when the service has Auto-Capture enabled.**

After running test inference, check if the service has autocapture enabled:

```python
services_df = mv.list_services()
print(services_df[['name', 'autocapture_enabled']])
```

If `autocapture_enabled` is `True` for this service, **ask the user:**

```
Your service has Auto-Capture enabled. Inference requests and responses are being
automatically logged to the model's inference table.

Would you like to view the captured inference data? (Yes/No)
```

**⚠️ STOP**: Wait for user response.

**If yes:** Load `../inference-logs/SKILL.md` and pass along the model name, version, and service name from this workflow as context.

**If no:** Continue to Step 8c.

---

#### Step 8c: Handle Inference Errors

**⚠️ CRITICAL:** If any test inference call in Step 8b fails (SQL error, HTTP 500, TypeError, ufunc error, dtype error, or any other runtime exception), **immediately load `../debug-inference/SKILL.md`** and follow its diagnostic workflow. Do NOT attempt to fix the issue directly — the debug skill has specific diagnosis and resolution paths for common inference failures (nullable dtype issues, pickle errors, OOM, etc.).

### Step 9: Setup REST API Access

**Ask user:**
```
Would you like to set up REST API access to call this service from outside Snowflake?

This is needed if you want to call the inference endpoint from external apps, 
scripts, or services (not via SQL or Python SDK).
```

**⚠️ STOP**: Wait for user response.

**If yes:** Continue with the REST API Access Setup flow below.

**If no:** Deployment complete.

### Next Steps

Before presenting options, check whether another inference service exists in the same schema:

```sql
SHOW SERVICES LIKE '%' IN SCHEMA <SERVICE_DATABASE>.<SERVICE_SCHEMA>;
```

Filter results to services where `managing_object_domain = 'Model'`. If **two or more** model inference services are running, include the gateway option below.

**If one service exists (no other model services found):**

```
Your inference service is running! What would you like to do next?

1. Set up model version monitoring - Track drift and performance for a model version
2. Done - Finish here
```

If the user asks for a stable URL or mentions wanting to swap services without changing the endpoint URL in the future, also offer: "Create a gateway for this service — gives you a stable hostname you can later reroute to a new service version without changing the URL."

**If two or more model inference services exist:**

```
Your inference service is running! What would you like to do next?

1. Create an A/B gateway - Split traffic between <SERVICE_V1> and <SERVICE_V2>
2. Set up gateway monitoring - Monitor and compare services
3. Done - Finish here
```

**If gateway:** Jump to [A/B Testing: Creating a Gateway for Traffic Splitting](#ab-testing-creating-a-gateway-for-traffic-splitting).

**If monitoring (two or more model inference services, or a gateway exists in session):** Load `../gateway-ab-testing/SKILL.md`.

**If monitoring (single service, source-table monitoring):** Load `../model-monitor/SKILL.md`.

**If done:** Skip to Service Management Reference.

---

## REST API Access Setup

To access the inference endpoint from outside Snowflake (e.g., external apps, services, or local scripts), you need proper authentication and network access configured.

### Network Policy (Required)

**Ask user:**
```
Do you have a network policy that allows your client IP to access Snowflake?
```

**⚠️ STOP**: Wait for user response.

**If yes:** Skip to [Service Role Grant](#service-role-grant).

**If no or unsure:** Users calling the endpoint need a network policy allowing their client IP. If user has ACCOUNTADMIN/SECURITYADMIN, help them create one:

```sql
-- Create network rule for client IP
CREATE NETWORK RULE <RULE_NAME> MODE = INGRESS TYPE = IPV4 VALUE_LIST = ('<CLIENT_IP>/32');

-- Create and apply policy
CREATE NETWORK POLICY <POLICY_NAME> ALLOWED_NETWORK_RULE_LIST = ('<RULE_NAME>');
ALTER USER <USERNAME> SET NETWORK_POLICY = <POLICY_NAME>;
```

### Service Role Grant

```sql
GRANT SERVICE ROLE <SERVICE_NAME>!ALL_ENDPOINTS_USAGE TO ROLE <ROLE_NAME>;
```

### Authentication (CLI Only)

**⚠️ CRITICAL: Always use PAT (Programmatic Access Token) for REST API authentication from CLI. Snowsight Notebooks do not require PAT - use the internal endpoint instead (see Step 8b).**

PAT tokens are the standard authentication method for SPCS REST endpoints. Create one in Snowsight under User Menu > Settings > Authentication.

**Do NOT attempt other authentication methods** (JWT, session tokens, etc.) - always ask the user for their PAT token first.

### Test with PAT

**⚠️ MANDATORY: Always ask for PAT token FIRST before any REST endpoint testing.**

**Step 1: Get the endpoint URL:**
```sql
SHOW ENDPOINTS IN SERVICE <SERVICE_NAME>;
```

**Step 2: Understand the model signature:**

Before testing, check the model's input/output signature to understand expected columns and data types:

```python
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")
print(mv.show_functions())
```

This returns the function signatures showing input columns, output columns, and their data types. See [ModelVersion API Documentation](https://docs.snowflake.com/en/developer-guide/snowpark-ml/reference/latest/api/model/snowflake.ml.model.ModelVersion) for details.

**Step 3: Ask user for PAT token:**
```
To test the REST endpoint, I need a PAT (Programmatic Access Token).

Please provide your PAT token. If you don't have one:
1. Go to Snowsight
2. Click your username (bottom left)
3. Go to Settings > Authentication
4. Create a new Programmatic Access Token

Please paste your PAT token:
```

**⚠️ STOP**: Wait for user to provide PAT token. Do NOT proceed without it.

**Step 4: Generate test script:**

```python
import requests
import json

url = "<ENDPOINT_URL>/<FUNCTION_NAME>"
pat = "<PAT_TOKEN>"

headers = {
    "Authorization": f'Snowflake Token="{pat}"',
    "Content-Type": "application/json"
}
payload = {"data": [[0, <SAMPLE_INPUT>]]}

response = requests.post(url, json=payload, headers=headers)
print(f"Status: {response.status_code}")
print(f"Response: {json.dumps(response.json(), indent=2)}")
```

### REST API Request Format

**⚠️ CRITICAL: The request payload format is specific and must be followed exactly.**

The SPCS inference REST API follows Snowflake's [External Functions Data Format](https://docs.snowflake.com/en/sql-reference/external-functions-data-format).

Each row is a JSON array where the **first element** is the row number (0-based index within the batch). The remaining elements contain the input data, which can be in one of two formats:

**Flat format** - Arguments as separate array elements:
```python
# Single row with 3 input columns (e.g., integer, string, timestamp)
payload = {"data": [[0, 10, "Alex", "2024-01-01 16:00:00"]]}

# Multiple rows
payload = {"data": [
    [0, 10, "Alex", "2024-01-01 16:00:00"],
    [1, 20, "Steve", "2024-02-01 16:00:00"],
    [2, 30, "Alice", "2024-03-01 16:00:00"]
]}
```

**Wide format** - Arguments as a single dict object:
```python
# Single row with named columns
payload = {"data": [[0, {"col1": value1, "col2": value2, "col3": value3}]]}

# Multiple rows
payload = {"data": [
    [0, {"feature1": 5.1, "feature2": 3.5, "feature3": 1.4}],
    [1, {"feature1": 4.9, "feature2": 3.0, "feature3": 1.4}],
    [2, {"feature1": 4.7, "feature2": 3.2, "feature3": 1.3}]
]}
```

**Common mistakes to avoid:**
```python
# WRONG - missing row index
payload = {"data": [[value1, value2, value3]]}
# Error: row index missing

# WRONG - data as dict instead of array of arrays
payload = {"data": {"col1": value1, "col2": value2}}
# Error: various parsing errors

# CORRECT - flat format
payload = {"data": [[0, value1, value2, value3]]}

# CORRECT - wide format
payload = {"data": [[0, {"col1": value1, "col2": value2}]]}
```

The row index (first element) is returned in the response, allowing you to match requests with responses when sending batches.

### REST API Response Format

**⚠️ CRITICAL: Responses are always in wide format (dict), regardless of request format.**

The SPCS inference REST API always returns responses in wide format. Each row contains the row index followed by a dict with the output values. The output column names and types are determined by the model signature (use `mv.show_functions()` to inspect).

**Standard response structure (always wide format):**
```json
{
  "data": [
    [0, {"output_feature_0": <value>, "output_feature_1": <value>}],
    [1, {"output_feature_0": <value>, "output_feature_1": <value>}]
  ]
}
```

- `data[0][0]` = row index (matches the first element in your request)
- `data[0][1]` = dict containing output features

**Correct parsing pattern:**
```python
result = response.json()
data = result.get('data', [[]])[0]

# Output is always a dict at data[1]
if len(data) >= 2 and isinstance(data[1], dict):
    output = data[1]
    # Access specific output features based on model signature
    value_0 = output.get('output_feature_0', 0.0)
    value_1 = output.get('output_feature_1', 0.0)
```

**Common mistake to avoid:**
```python
# WRONG - data[1] is a dict, not a float!
result = float(data[1])  # TypeError: float() argument must be a string or real number, not 'dict'

# CORRECT - access the dict key
result = data[1].get('output_feature_0', 0.0)
```

**Debugging tip:** If you encounter parsing errors, first inspect the raw response:
```python
print(json.dumps(response.json(), indent=2))
```

**⚠️ STOP**: Wait for user response before proceeding.

---

## Debugging Issues

**⚠️ CRITICAL: Auto-route to debug-inference on ANY error encountered during this workflow.**

At any point in this workflow — service FAILED status, container crashes, inference test errors (500s, TypeErrors, ufunc errors, dtype issues, AttributeErrors, OOM, etc.) — you MUST:

1. **Immediately load `../debug-inference/SKILL.md`**
2. Follow its diagnostic workflow to identify the root cause
3. Apply the recommended fix from that skill

Do NOT attempt to diagnose or fix inference errors directly. The debug-inference skill has specific triage paths, known error patterns, and tested fixes (e.g., nullable signature re-registration for ufunc errors, pickle class resolution for AttributeErrors).

---

## Anti-Patterns to Avoid

**Do NOT use `CREATE SERVICE` SQL syntax for model inference** - always use the Python SDK:
```sql
-- WRONG - bypasses model registry integration
CREATE SERVICE my_service IN COMPUTE POOL my_pool ...
```

**Instead:** Use `mv.create_service()` from the model version object - this properly links the service to the registered model.

**Do NOT use `block=False` in `create_service()`** - run the script in background instead:
```python
# WRONG - async mode can cause issues with status tracking
mv.create_service(..., block=False)
```

**Instead:** Run the entire script as a background process and monitor via SQL.

**Do NOT use `RESULT_SCAN(LAST_QUERY_ID())` to filter SHOW results** - column name casing issues cause failures:
```sql
-- WRONG - fragile, causes "invalid identifier" errors
SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) WHERE name = 'X'
```

**Do NOT use SHOW as a subquery** - invalid SQL syntax:
```sql
-- WRONG - syntax error
SELECT * FROM (SHOW SERVICES) WHERE name = 'X'
```

**Instead:** Run `DESCRIBE SERVICE` or `SHOW` commands directly and read the output.

**Do NOT attempt JWT or session token authentication for REST endpoints** - these approaches waste time and don't work reliably:
```python
# WRONG - JWT requires keypair setup that users rarely have
token = snow_connection.generate_jwt()

# WRONG - session tokens are for internal Snowflake use
token = conn.rest.token
```

**Instead:** Always ask the user for their PAT (Programmatic Access Token) first. PAT is the standard, supported method for SPCS REST authentication.

---

## A/B Testing: Creating a Gateway for Traffic Splitting

Use `CREATE GATEWAY` to split inference traffic across two or more model services without any application-side routing logic. This is the official Snowflake SPCS primitive for champion-challenger, canary, and A/B deployments.

### Step 1: Discover the Endpoint Name

Each inference service exposes one or more HTTP endpoints. The endpoint name in the gateway spec must match exactly.

```sql
SHOW ENDPOINTS IN SERVICE <DB>.<SCHEMA>.<SERVICE_NAME>;
```

Look at the `name` column. Model Registry inference services typically expose an endpoint named `inference`. Confirm the name for **both** services before proceeding.

### Step 2: Check Required Privileges

**⚠️ DO NOT execute any GRANT statements.** Only check whether the current role already has the necessary privileges. If a privilege is missing, surface the exact grant the user needs to run manually — do not run it yourself.

```sql
-- Check current role
SELECT CURRENT_ROLE();

-- Check existing grants on the schema
SHOW GRANTS ON SCHEMA <DB>.<SCHEMA>;
```

If the current role is missing a required privilege, present the relevant statement(s) to the user with a clear message:

```
Your role is missing the following privilege(s). Please have an account admin run:

-- Required to create gateways
GRANT CREATE GATEWAY ON SCHEMA <DB>.<SCHEMA> TO ROLE <ROLE_NAME>;

-- Required to bind service endpoints (if not already granted)
GRANT BIND SERVICE ENDPOINT ON ACCOUNT TO ROLE <ROLE_NAME>;

-- Required for each target service
GRANT SERVICE ROLE <DB>.<SCHEMA>.<SERVICE_V1_NAME>!ALL_ENDPOINTS_USAGE TO ROLE <ROLE_NAME>;
GRANT SERVICE ROLE <DB>.<SCHEMA>.<SERVICE_V2_NAME>!ALL_ENDPOINTS_USAGE TO ROLE <ROLE_NAME>;
```

**⚠️ STOP**: Wait for the user to confirm the grants have been applied before continuing.

### Step 3: Create the Gateway

Weights must sum to 100. The `value` format is `db.schema.service!endpoint_name`.

Before executing, fill in all placeholders and present the exact DDL to the user:

```
Here is the gateway I will create:

CREATE OR REPLACE GATEWAY <DB>.<SCHEMA>.<GATEWAY_NAME>
  FROM SPECIFICATION $$
spec:
  type: traffic_split
  split_type: custom
  targets:
  - type: endpoint
    value: <DB>.<SCHEMA>.<SERVICE_V1_NAME>!<ENDPOINT_NAME>
    weight: 80
  - type: endpoint
    value: <DB>.<SCHEMA>.<SERVICE_V2_NAME>!<ENDPOINT_NAME>
    weight: 20
$$;

Shall I create this gateway? (yes/no)
```

**⚠️ STOP**: Do not execute until the user explicitly confirms. After confirmation, execute the SQL shown above.

### Step 4: Get the Gateway URL

```sql
SHOW GATEWAYS IN SCHEMA <DB>.<SCHEMA>;
-- or
DESCRIBE GATEWAY <DB>.<SCHEMA>.<GATEWAY_NAME>;
```

Look for the `ingress_url` or `url` column. This is the single endpoint callers hit — the gateway handles routing internally.

### Step 5: Test the Gateway

The gateway exposes the same REST interface as the underlying services. Use the same payload format as a direct service call (see [Step 8b](#step-8b-test-inference) above), but target the gateway URL instead.

```python
import requests

url = "https://<gateway-ingress-url>/<endpoint-path>"  # e.g. /predict or /predict-proba
headers = {"Authorization": "Snowflake Token=\"<PAT>\""}
payload = {"data": [[0, val1, val2, ...]]}

response = requests.post(url, json=payload, headers=headers)
print(response.json())
```

Call the gateway several times to verify both routes are being exercised according to the configured weights.

### Changing the Split Ratio

Use `CREATE OR REPLACE GATEWAY` with the same spec but updated weights.

## Service Management Reference

**Suspend/Resume:**
```sql
ALTER SERVICE <SERVICE_NAME> SUSPEND;
ALTER SERVICE <SERVICE_NAME> RESUME;
```

**Auto-suspend (default 30 min):**
```sql
ALTER SERVICE <SERVICE_NAME> SET AUTO_SUSPEND_SECS = <seconds>;
```

**Delete service:**
```sql
DROP SERVICE <SERVICE_NAME>;
```

**Scale service:**
```sql
ALTER SERVICE <SERVICE_NAME> SET MIN_INSTANCES = <N>, MAX_INSTANCES = <M>;
```
