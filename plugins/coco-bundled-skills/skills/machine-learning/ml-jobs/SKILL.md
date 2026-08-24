---
name: ml-jobs
description: "Transform local Python scripts into Snowflake ML Jobs. Use when: running ML workloads on Snowflake compute pools, GPU training, submitting Python scripts to run remotely, converting local scripts to ML jobs, distributed training. Triggers: ml job, submit job, run on compute pool, remote execution, GPU training."
parent_skill: data-science-machine-learning
---

# Transform Python Script to Snowflake ML Job

Guide users step-by-step to convert a local Python script into a Snowflake ML Job that runs on Snowflake compute pools.

## When to Use

- User wants to run a Python script on Snowflake compute (GPU/high-memory)
- User wants to offload resource-intensive ML training to Snowflake
- User has a local script and wants it to run as an ML Job
- User mentions: "ml job", "compute pool", "remote execution", "GPU training"

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## Prerequisites

- `snowflake-ml-python>=1.9.2` (refers to the env guide in the parent skill to setup `snowflake-ml-python`) 
- Python 3.10 client environment
- Snowflake account with compute pool access

## Workflow

### Step 1: Understand the Script

**Ask user:**
```
To convert your Python script to a Snowflake ML Job, I need to understand it:

1. **Script location**: What is the path to your Python script?
2. **Script purpose**: What does the script do? (training, inference, data processing)
3. **Multiple files?**: Does your project have multiple Python files or just one?
```

**⚠️ STOP**: Wait for user response.

After user responds:
- **Read the script** to understand its structure
- Identify: imports, dependencies, data sources, outputs, return values
- Note any hardcoded paths or configurations that need modification
- **Infer GPU vs CPU requirements** (see below)

#### GPU/CPU Inference from Script

| Suggest GPU if ANY of these present | Suggest CPU if no GPU patterns |
|-------------------------------------|-------------------------------|
| `.cuda()`, `.to('cuda')`, `.to(device)` | `sklearn` only |
| `torch.cuda.is_available()` | `xgboost`, `lightgbm` (no GPU config) |
| `import cupy`, `cudf`, `cuml` (RAPIDS) | `pandas` processing |
| `device_map="auto"` or `"cuda"` | Pure numpy operations |
| `transformers` with large models | Traditional ML algorithms |
| `.half()`, `.bfloat16()` precision | |
| `DataParallel`, `DistributedDataParallel` | |

#### Training Package Selection

**Default to OSS (Open Source)**: Use standard open-source libraries (XGBoost, LightGBM, PyTorch, scikit-learn, etc.) directly.

**Only if user explicitly asks for distributed training**, use Snowflake's Container Runtime Distributed API with trainers from `snowflake.ml.modeling.distributors`:
- `XGBEstimator` / `XGBScalingConfig` for XGBoost
- `LightGBMEstimator` / `LightGBMScalingConfig` for LightGBM  
- `PyTorchDistributor` / `PyTorchScalingConfig` for PyTorch
- Reference: https://docs.snowflake.com/en/developer-guide/snowflake-ml/distributed-training

### Step 2: Identify Compute and Stage Requirements

#### 2a: Query Available Compute Pools

**Run this query to discover available compute pools:**
```sql
SHOW COMPUTE POOLS;
```

This returns columns including:
- `name`: Compute pool name
- `state`: ACTIVE, IDLE, STARTING, etc.
- `instance_family`: CPU_X64_S, GPU_NV_S, GPU_NV_M, HIGHMEM_X64_S, etc.
- `min_nodes`, `max_nodes`: Pool size limits
- `active_nodes`: Currently running nodes
- `idle_nodes`: Warm nodes ready for immediate use
- `auto_suspend_secs`: Auto-suspend configuration

#### 2b: Select Best Compute Pool

**Use this logic to suggest a compute pool:**

1. **Determine required type** from Step 1 inference:
   - If GPU needed → filter pools where `instance_family` contains "GPU"
   - If CPU needed → filter pools where `instance_family` contains "CPU" or "HIGHMEM"

2. **For generic workloads (no special requirements):**
   - CPU workloads → default to `SYSTEM_COMPUTE_POOL_CPU`
   - GPU workloads → default to `SYSTEM_COMPUTE_POOL_GPU`

3. **For optimized selection, rank pools by:**
   - **Idle nodes** (highest priority): Pools with `idle_nodes > 0` provide warm starts
   - **Free capacity**: Calculate `max_nodes - active_nodes` for headroom
   - **State**: Prefer `ACTIVE` over `IDLE` (already running), both over `SUSPENDED`
   - **Instance family match**: Match workload intensity to instance size

**Ranking formula:**
```
score = (idle_nodes * 10) + (max_nodes - active_nodes) + (3 if state == 'ACTIVE' else 1 if state == 'IDLE' else 0)
```

#### 2c: Ask User for Confirmation

**Use `ask_user_question` to confirm:**
1. **Instance type** (GPU/CPU) - include brief reasoning from script analysis
2. **Compute pool** - recommend best match, include system pools as fallback
3. **Stage** - ask if they have an existing stage or need to create one

**⚠️ STOP**: Wait for user response.

**Instance Family Reference:**

| Workload | Instance Family |
|----------|-----------------|
| General ML | CPU_X64_S |
| GPU Training | GPU_NV_S, GPU_NV_M |
| Large Data | HIGHMEM_X64_S |

**If user needs new resources:**
```sql
CREATE COMPUTE POOL IF NOT EXISTS <POOL_NAME>
  MIN_NODES = 1 MAX_NODES = 5 INSTANCE_FAMILY = <FAMILY>;

CREATE STAGE IF NOT EXISTS <DATABASE>.<SCHEMA>.<STAGE_NAME>;
```

### Step 3: Analyze Dependencies

**Automatically extract dependencies from the script you read in Step 1.**

1. **Check for existing requirements.txt** in the project directory
   - If found and using `submit_directory`: dependencies will be installed automatically—no need to specify `pip_requirements`
   - If found: review contents to understand what external packages are needed (for EAI detection in Step 4)

2. **Parse all import statements** from the script
3. **Map imports to pip packages** (e.g., `import sklearn` → `scikit-learn`, `import cv2` → `opencv-python`)
4. **Classify each package:**

| Category | Examples | Action |
|----------|----------|--------|
| Pre-installed in ML Runtime | pandas, numpy, scikit-learn, xgboost, torch, tensorflow, transformers | No pip_requirements needed |
| Standard library | os, sys, json, pathlib, typing | Ignore |
| Custom packages | Any not in above | Add to pip_requirements (unless requirements.txt exists) |

**Pre-installed packages in ML Runtime (do NOT add to pip_requirements):**
- pandas, numpy, scipy
- scikit-learn, xgboost, lightgbm
- torch, tensorflow, transformers
- snowflake-snowpark-python, snowflake-ml-python

**Present to user:**

**If requirements.txt exists:**
```
I found a requirements.txt in your project directory. When using submit_directory,
these dependencies will be installed automatically—no need to specify pip_requirements.

**requirements.txt contents:**
<list packages from file>

**Note:** Custom packages still require PyPI access via an External Access Integration.
```

**If NO requirements.txt:**
```
I analyzed your script and found these dependencies:

**Pre-installed (no action needed):**
- <list packages>

**Custom packages to install:**
- <list packages>

Any additional packages or specific versions needed?
```

**⚠️ STOP**: Wait for user confirmation or additions.

### Step 4: Detect External Network Access Requirements

ML Jobs run in an isolated environment. External network access requires an External Access Integration (EAI).

**⚠️ IMPORTANT**: Scripts often require MULTIPLE types of external access. Scan for ALL patterns below—don't stop at the first match.

#### 4a: Identify ALL External Access Patterns

Build a complete list by checking each category:

| Category | Indicators | Access Needed |
|----------|-----------|---------------|
| **Package Installation** | `requirements.txt`, `pip_requirements`, custom packages not in ML Runtime | PyPI |
| **Hugging Face** | `from_pretrained()`, `AutoModel`, `AutoTokenizer`, `SentenceTransformer()`, `pipeline()` | huggingface.co |
| **NLTK** | `nltk.download()` | nltk.org, github.com |
| **PyTorch Hub** | `torch.hub.load()`, `pretrained=True` in torchvision | pytorch.org, github.com |
| **TensorFlow Hub** | `hub.load()`, keras pretrained models | tfhub.dev |
| **Experiment Tracking** | `import wandb`, `import mlflow`, `import comet_ml` | wandb.ai, mlflow server, comet.ml |
| **LLM APIs** | `import openai`, `import anthropic` | api.openai.com, api.anthropic.com |
| **Cloud Storage** | `boto3`, `s3fs`, `google.cloud`, `azure` | AWS/GCP/Azure endpoints |
| **Generic HTTP** | `requests`, `httpx`, `urllib` with external URLs | Various (check URLs in code) |

**Example: A training script might need ALL of these:**
1. PyPI access - for custom packages
2. Hugging Face access - for `from_pretrained()` model downloads
3. W&B access - for `wandb.log()` experiment tracking

#### 4b: Query Available EAIs

```sql
SHOW EXTERNAL ACCESS INTEGRATIONS;
```

#### 4c: ALWAYS Confirm EAI Selection with User

**Use `ask_user_question` with `multiSelect: true`** to let user select all applicable EAIs.

Present:
1. ALL detected external access requirements (not just the first one)
2. Available EAIs from the query as options
3. Any suggested matches based on EAI names (but don't be overconfident—naming varies by account)

Example question:
```
**External Access Requirements Detected:**
1. Package installation (PyPI) - requirements.txt with custom packages
2. Model downloads (Hugging Face) - from_pretrained() calls detected
3. Experiment tracking (W&B) - import wandb detected

**Which EAI(s) cover these requirements?** (Select all that apply)
```

Options should include each available EAI from `SHOW EXTERNAL ACCESS INTEGRATIONS`, plus "None needed" if applicable.

**⚠️ STOP**: Wait for user to confirm EAI selection. Do not proceed without explicit confirmation.

#### 4d: Handle Missing EAIs

Creating EAIs requires **ACCOUNTADMIN** privileges. If needed EAIs don't exist:

**For PyPI access** (uses built-in network rule):
```sql
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION PYPI_EAI
  ALLOWED_NETWORK_RULES = (snowflake.external_access.pypi_rule)
  ENABLED = true;
GRANT USAGE ON INTEGRATION PYPI_EAI TO ROLE <USER_ROLE>;
```

**For other services** (requires custom network rule):
```sql
CREATE OR REPLACE NETWORK RULE <SERVICE>_RULE
  TYPE = HOST_PORT
  VALUE_LIST = ('<hostname1>', '<hostname2>')
  MODE = EGRESS;

CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION <SERVICE>_EAI
  ALLOWED_NETWORK_RULES = (<SERVICE>_RULE)
  ENABLED = true;
GRANT USAGE ON INTEGRATION <SERVICE>_EAI TO ROLE <USER_ROLE>;
```

**Common hostnames:**

| Service | Hostnames |
|---------|-----------|
| Hugging Face | `huggingface.co`, `cdn-lfs.huggingface.co` |
| Weights & Biases | `api.wandb.ai`, `wandb.ai` |
| OpenAI | `api.openai.com` |
| Anthropic | `api.anthropic.com` |

If user lacks privileges, provide the SQL for them to share with their admin.

### Step 5: Determine Submission Method

Based on gathered information, select the appropriate method:

| Scenario | Method | When to Use |
|----------|--------|-------------|
| Single file | `submit_file()` | One Python script, no local imports |
| Multi-file project | `submit_directory()` | Multiple modules, local imports |
| Already on stage | `submit_from_stage()` | Code already uploaded to Snowflake |
| Single function | `@remote` decorator | Quick test, simple function |

### Step 6: Generate the Job Submission Code

**Present to user before generating:**

```
I'll submit the ML Job with these settings:

- **Script**: <script_path>
- **Compute Pool**: <pool_name>
- **Instance Type**: <instance_family>
- **Dependencies**: <pip_requirements>
- **External Access**: <list of EAIs, or "None required">
- **Nodes**: <target_instances>
- **Method**: <submit_file|submit_directory|remote>

Ready to proceed? (Yes/No)
```

**⚠️ MANDATORY CHECKPOINT**: Wait for user approval.

**⚠️ CRITICAL**: The submission code must set database and schema context:
```python
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")
```

#### Template: submit_file (Single Script)

Use `snowpark_session.py` from parent skill (`machine-learning/SKILL.md` → Session Setup Patterns). Copy the helper script to the working directory and import it.

```python
from snowflake.ml.jobs import submit_file
from snowpark_session import create_snowpark_session

DATABASE = "<DATABASE>"
SCHEMA = "<SCHEMA>"

session = create_snowpark_session()
session.use_database(DATABASE)
session.use_schema(SCHEMA)

job = submit_file(
    "<SCRIPT_PATH>",
    "<COMPUTE_POOL>",
    stage_name="<PAYLOAD_STAGE>",
    args=["--arg1", "value1"],  # Command line args if needed
    pip_requirements=[<DEPS>],  # ["custom-package==1.0"]
    external_access_integrations=[<EAIS>],
    session=session,
)

print(f"Job submitted successfully!")
print(f"Job ID: {job.id}")
print(f"Status: {job.status}")
```

#### Template: submit_directory (Multi-File Project)

```python
from snowflake.ml.jobs import submit_directory
from snowpark_session import create_snowpark_session

DATABASE = "<DATABASE>"
SCHEMA = "<SCHEMA>"

session = create_snowpark_session()
session.use_database(DATABASE)
session.use_schema(SCHEMA)

job = submit_directory(
    "<PROJECT_DIR>",
    "<COMPUTE_POOL>",
    entrypoint="<MAIN_SCRIPT.py>",
    stage_name="<PAYLOAD_STAGE>",
    pip_requirements=[<DEPS>],  # Omit if requirements.txt exists in directory
    external_access_integrations=[<EAIS>],
    session=session,
)

print(f"Job submitted successfully!")
print(f"Job ID: {job.id}")
print(f"Status: {job.status}")
```

**Note:** If `requirements.txt` exists in the project directory, omit `pip_requirements`—dependencies install automatically.

#### Template: @remote Decorator (Function)

```python
from snowflake.ml.jobs import remote
from snowpark_session import create_snowpark_session

DATABASE = "<DATABASE>"
SCHEMA = "<SCHEMA>"

session = create_snowpark_session()
session.use_database(DATABASE)
session.use_schema(SCHEMA)

@remote(
    "<COMPUTE_POOL>",
    stage_name="<PAYLOAD_STAGE>",
    pip_requirements=[<DEPS>],
    external_access_integrations=[<EAIS>],
    session=session,
)
def train_model(data_table: str):
    # Your ML code here
    from snowflake.snowpark import Session
    session = Session.builder.getOrCreate()

    df = session.table(data_table).to_pandas()
    # ... training logic ...
    return model

job = train_model("<TABLE_NAME>")
print(f"Job submitted successfully!")
print(f"Job ID: {job.id}")
```

### Step 7: Script Modifications (If Needed)

**Common modifications for ML Jobs:**

1. **Snowpark Session Access** (inside job):
```python
from snowflake.snowpark import Session
session = Session.builder.getOrCreate()  # Auto-available in jobs
```

2. **Remove hardcoded paths** - use arguments or Snowflake data sources

#### 7a: Results and Artifacts

ML Jobs support two mechanisms for outputs:
- **Return values**: Retrieved via `job.result()` after job completion (assign to `__return__` variable)
- **Artifact files**: Saved to `MLRS_STAGE_RESULT_PATH` environment variable (e.g., model weights)

**Prefer minimal modifications.** Check if the user's script already supports the needed behavior before making changes.

**Step 1: Analyze existing script for output handling**

Look for:
- Existing CLI argument parsing (`argparse`, `click`, `typer`, etc.)
- Output path arguments (e.g., `--output-dir`, `--model-path`, `--save-path`)
- Existing artifact saving logic

**Step 2: Use `args` in job submission if possible**

If the script already accepts an output path argument, simply pass the stage result path via `args`:

```python
job = submit_file(
    "train.py",
    "MY_COMPUTE_POOL",
    args=["--output-dir", "$MLRS_STAGE_RESULT_PATH", "--epochs", "10"],
    # ... other params ...
)
```

Common output arguments to look for:
- `--output`, `--output-dir`, `--output-path`
- `--model-path`, `--model-dir`, `--save-path`
- `--checkpoint-dir`, `--results-dir`

**Step 3: Only modify script if necessary**

Modify the user's script only if:
1. It has no existing output path argument, AND
2. The user needs artifact persistence or return values

**Minimal modification pattern** (add to end of script):

```python
# For ML Jobs: capture return value
if __name__ == "__main__":
    result = main()  # or existing entry point
    import os
    if os.environ.get("MLRS_STAGE_RESULT_PATH"):
        __return__ = result
```

**For artifact saving** (if script has hardcoded paths):

```python
import os

# Use stage path if in ML Job, otherwise use local path
output_dir = os.environ.get("MLRS_STAGE_RESULT_PATH", "./output")
model_path = os.path.join(output_dir, "model.pkl")
```

#### 7b: Retrieving Results and Artifacts

**After job completes (status = DONE):**

```python
# Get return value (from __return__ assignment)
result = job.result()
print(f"Result: {result}")

# Artifacts saved to MLRS_STAGE_RESULT_PATH are stored in the job's result stage
```

### Step 8: Execute the Job Submission

Execute the submission code using inline Python. After successful submission, report:

1. **Job ID** - from `job.id`
2. **Job Status** - initial status (usually PENDING or RUNNING)

**Example success message:**
```
Job submitted successfully!

- **Job ID**: TRAIN_ABC123
- **Status**: PENDING

You can check job status later using the job ID.

### Step 9: Ask About Waiting for Job Completion

**Ask user:**
```
Would you like me to wait for the job to complete? (Yes/No)

- **Yes**: I'll wait for the job to finish and show you the results and logs.
- **No** [Default]: You can check job status later using the job ID.
```

**⚠️ STOP**: Wait for user response. Default to No if user is unsure.

#### If user says Yes: Wait for Job Completion

```python
from snowflake.ml.jobs import get_job
from snowpark_session import create_snowpark_session

session = create_snowpark_session()
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")

job = get_job("<JOB_ID>")
job.wait()
print(f"Job ID: {job.id}")
print(f"Status: {job.status}")  # FAILED, DONE

if job.status == "DONE":
    # Retrieve return value (from __return__ in script)
    result = job.result()
    print(f"\\n--- Result ---")
    print(result)

print("\\n--- Logs ---")
print(job.get_logs())
```

**Present job status and results to user.**

#### If user says No or checks later

**When user asks for job status or results later:**

```python
from snowflake.ml.jobs import get_job
from snowpark_session import create_snowpark_session

session = create_snowpark_session()
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")

job = get_job("<JOB_ID>")
print(f"Job ID: {job.id}")
print(f"Status: {job.status}")

if job.status == "DONE":
  print(f"\n--- Result ---")
  print(job.result())

print("\n--- Logs ---")
print(job.get_logs())

```

### Step 10: Troubleshooting

**If job fails:**

1. **Get full logs**:
```python
print(job.get_logs())
```

2. **Common issues:**

| Error | Cause | Fix |
|-------|-------|-----|
| ModuleNotFoundError | Missing dependency | Add to `pip_requirements` |
| Connection timeout | No EAI for pip | Create PYPI_EAI integration |
| PermissionError | Missing privileges | Grant USAGE on compute pool |
| FileNotFoundError | Wrong path | Use absolute paths in args |

3. **For multi-node jobs**, check specific instance logs:
```python
print(job.get_logs(instance_id=0))
print(job.get_logs(instance_id=1))
```

## Multi-Node Jobs (Distributed Training)

If user needs distributed training across multiple nodes:

```python
job = submit_file(
    "<SCRIPT_PATH>",
    "<COMPUTE_POOL>",
    stage_name="<PAYLOAD_STAGE>",
    target_instances=3,  # Number of nodes
    min_instances=2,     # Minimum to start (optional)
    session=session,
)
```

**Script must use distributed APIs:**
- Snowflake Distributed Modeling Classes (XGBEstimator, etc.)
- Ray for custom distribution

## Quick Reference

### Required Privileges

| Privilege | Object | Purpose |
|-----------|--------|---------|
| USAGE | Database | Access database |
| USAGE | Schema | Access schema |
| CREATE SERVICE | Schema | Create ML Jobs |
| USAGE | Compute Pool | Run on compute |
| USAGE | Stage | Upload payloads |

### Job Management

```python
from snowflake.ml.jobs import list_jobs, get_job, delete_job

jobs_df = list_jobs(limit=10)  # List recent jobs
job = get_job("<JOB_ID>")      # Get specific job
delete_job(job)                 # Delete job
```
