---
name: machine-learning
description: "**[REQUIRED]** For **ALL** data science and machine learning tasks. This skill should ALWAYS be loaded in even if only a portion of the workflow is related to machine learning. Use when: analyzing data, training models, deploying models to Snowflake, registering models, working with ML workflows, running ML jobs on Snowflake compute, model registry, model service, model inference, log model, deploy pickle file, experiment tracking, model monitoring, gateway A/B testing, ML observability, tracking drift, model performance analysis, distributed training, XGBoost, LightGBM, PyTorch, DPF, distributed partition function, many model training, hyperparameter tuning, HPO, compute pools, train at scale, feature store, feature views, entities, training datasets, online features, pipeline orchestration, DAG, task graph, schedule training, datasets, dataset versioning, DataConnector, ML lineage, model lineage, GET_LINEAGE, trace lineage, forecast, forecasting, time series, anomaly detection, outlier, predict, predictions, backtest, classify, classification, regression, clustering, build a model, create a model, sklearn, scikit-learn, tensorflow, ML, mlops, ray, GPU, deep learning, neural network, explain model, SHAP, Shapley, feature importance, model explainability, interpret model, preprocessing, preprocessor, scaling, encoding, imputation, normalize, transform data before training, preprocessing pipeline. Routes to specialized sub-skills."
---

# Data Science & Machine Learning Skills

This skill routes to specialized sub-skills for data science and machine learning tasks.
This skill provides valuable information about all sorts of data science, machine learning, and mlops tasks.
It MUST be loaded in if any part of the user query relates to these topics❗❗❗

## Step 0: Load Environment Guide

**⚠️ CRITICAL: Before routing to any sub-skill, you MUST load the environment guide for your surface.**

Your system prompt indicates which surface you are operating on. Load the matching guide:

| Surface | Condition | Guide to Load |
|---------|-----------|---------------|
| **Snowsight** | You are operating inside the Snowflake Snowsight web interface | `guides/snowsight-environment.md` |
| **CLI / IDE** | You are operating in a command line terminal or IDE environment | `guides/cli-environment.md` |

The environment guide provides surface-specific instructions for **session setup, package management, and code execution** that apply to ALL sub-skills below. Sub-skills will reference these patterns rather than repeating them.

## Routing Behavior

**⚠️ CRITICAL: Route AUTOMATICALLY based on the user's request. Do NOT ask the user which sub-skill to use or how they want to deploy.**

**Routing means loading the matched guidance, not just naming it.** After selecting any route in this file:

- Read the environment guide from Step 0 if it is not already loaded.
- Read every `SKILL.md` named in the matched route chain before responding or acting.
- If a route says `ml-development/SKILL.md` -> another sub-skill, read both `ml-development/SKILL.md` and the final sub-skill `SKILL.md`.
- Do not satisfy routing by saying which skill you would load; actually load the referenced guidance.

**Re-evaluate routing on every new user message.** Do not keep using the previous sub-skill just because it was active earlier in the conversation. The latest user intent controls routing:

- If the user trained a model earlier and now says "log it", "register it", "deploy it", "explain it", or "save it to Snowflake", read `model-registry/SKILL.md` and pass along preserved training context.
- If the user asks for inference, monitoring, lineage, pipeline orchestration, feature store work, or an ML job after training, read the matching platform skill before responding.
- Preserve model context across the handoff instead of asking the user to repeat details.

When a user asks to "train a model", "build a model" or inquires about a similar task:

- **IMMEDIATELY** load `ml-development/SKILL.md` and start working
- Do NOT ask about deployment options upfront
- Do NOT ask "Local only vs Register in Snowflake vs End-to-end"
- Training and deployment are SEPARATE tasks - handle them sequentially if needed

## Intent Detection

### Dynamic Service Detection (Model Inference Services)

**⚠️ CRITICAL:** When a user mentions a **service name**, check if it's a model inference service:

1. Run `DESCRIBE SERVICE <DB>.<SCHEMA>.<SERVICE_NAME>`
2. If `managing_object_domain = 'Model'` → Route to `spcs-inference/SKILL.md`

This applies to ANY task involving the service (testing, REST API calls, latency profiling, benchmarking, debugging, management).

---

### Disambiguation: batch-inference vs spcs-inference (Online)

**⚠️ CRITICAL:** When user mentions "inference" without clear signals, you MUST ask for clarification. 
There is a decision matrix located in the public docs `https://docs.snowflake.com/en/developer-guide/snowflake-ml/inference/inference-overview`.

**Inference Disambiguation Workflow:**

When user says something like "run inference on my model" or "inference" without batch/online signals:

```
I can help you run inference on your model. There are three approaches:

1. **Native Batch Inference (SQL)** - Embed inference in SQL pipelines
   - <add decision points from docs matrix here>
   
2. **Job-Based Batch (SPCS)** - Run large-scale inference jobs
   - <add decision points from docs matrix here>

3. **Real-Time Inference (SPCS)** - Deploy a REST endpoint
   - <add decision points from docs matrix here>

Which approach fits your use case?
```

**⚠️ STOP**: Wait for user response before routing.

### Disambiguation: batch-inference vs ml-jobs

**⚠️ CRITICAL:** These two skills are commonly confused. Use this logic:

| User Intent | Key Signals | Route To |
|-------------|-------------|----------|
| Run inference on a **registered model** | "model registry" + ("inference", "predictions", "scoring", "run()", "run_batch()") | `batch-inference-jobs/SKILL.md` |
| Run a **Python script** on Snowflake compute | "script", "submit", "file", "directory", training code | `ml-jobs/SKILL.md` |

**Decision tree:**
1. Does the user want to run inference on an **existing model in the registry**?
   - **YES** → `batch-inference-jobs/SKILL.md` (covers both `mv.run()` and `mv.run_batch()`)
   - **NO** → Continue to step 2
2. Does the user want to run **custom Python code** (training, processing, or scripts) on Snowflake compute?
   - **YES** → `ml-jobs/SKILL.md` (uses `submit_file()` or `submit_directory()`)
   - **NO** → Continue to step 3
3. Does the user want to **orchestrate multiple steps** on a schedule (pipeline, DAG)?
   - **YES** → `ml-pipeline-orchestration/SKILL.md`
   - **NO** → Ask clarifying question

### Disambiguation: ml-jobs vs ml-pipeline-orchestration

| User Intent | Key Signals | Route To |
|-------------|-------------|----------|
| Run a **single ML job** | "submit", "run script", "compute pool", one-off execution | `ml-jobs/SKILL.md` |
| **Orchestrate multiple steps** on a schedule | "pipeline", "DAG", "schedule", "automate", "task graph", multi-step workflow | `ml-pipeline-orchestration/SKILL.md` |

### Disambiguation: Partitioned Modeling

When user says "partitioned modeling", "partitioned model", "model per partition", or "per-partition models" without saying whether they need training or inference, ask one clarification question before routing:

```markdown
Do you want to train one model per partition, run inference with already-trained per-partition models, or do the full train-to-inference workflow?
```

- Training or full workflow -> load `ml-development/SKILL.md`; it routes to distributed training / MMT.
- Existing trained models or inference -> load `model-registry/partitioned-inference/SKILL.md`.

### Disambiguation: gateway model monitor vs model version monitor

**⚠️ CRITICAL:** Snowflake has two distinct monitor types. Generic keywords (`track drift`, `model performance`, `monitor model`) often match the Platform table, but the wrong monitor type uses a different `CREATE MODEL MONITOR` syntax. Use this logic:

| Monitor type | CREATE syntax | Key signals | Route To |
|--------------|---------------|-------------|----------|
| **Gateway model monitor** | `GATEWAY = ...` | gateway, traffic split, champion-challenger, shadow testing, compare inference services, A/B or canary test across services | `gateway-ab-testing/SKILL.md` |
| **Model version monitor** | `VERSION = ...`, `SOURCE = ...` | one model version, source table, no gateway, batch/offline drift or performance | `model-monitor/SKILL.md` |

**Decision tree:**
1. Does the user want to monitor or compare **multiple inference services behind a gateway** (A/B, canary, shadow, champion-challenger)?
   - **YES** → `gateway-ab-testing/SKILL.md` (gateway model monitor)
   - **NO** → Continue to step 2
2. Does the user want to monitor **one model version** using a **source table** (no gateway)?
   - **YES** → `model-monitor/SKILL.md` (model version monitor)
   - **NO** → Ask clarifying question

## Sub-Skills by Category

### Training

Routes through ml-development, which guides the full development lifecycle and sub-routes to specialized training skills.

| User Says | Route To | Action |
|-----------|----------|--------|
| "automl", "auto ml", "auto-ml", "automated machine learning", "run automl", "best model", "find the best model", "best possible model", "highest score", "highest accuracy", "top model", "top performing model", "automated model selection" | `automl/SKILL.md` | Load immediately |
| "analyze data", "train model", "build model", "feature engineering", "predict", "classify", "regression" | `ml-development/SKILL.md` | Read `ml-development/SKILL.md`, then start training |
| "distributed training", "distributed XGBoost", "distributed LightGBM", "XGBEstimator", "LightGBMEstimator", "PyTorchDistributor", "multi-node training", "multi-GPU training", "train at scale", "DPF", "distributed partition function", "many model training", "MMT", "train per partition", "ManyModelTraining", "partition by", "hyperparameter tuning", "hyperparameter optimization", "HPO", "Tuner", "TunerConfig", "search space", "grid search", "random search", "bayesian optimization", "tune model", "tune hyperparameters", "num_trials", "search_alg" | `ml-development/SKILL.md` -> `distributed-training/SKILL.md` | Read both files before responding or working; use the specific distributed-training child guidance when applicable |
| "preprocessing", "scale data", "encode features", "handle missing values", "impute", "normalize", "StandardScaler", "OneHotEncoder", "LabelEncoder", "MinMaxScaler", "OrdinalEncoder", "ray.data.preprocessors", "preprocessing pipeline", "map_batches", "transform data before training" | `ml-development/SKILL.md` -> `preprocessing/SKILL.md` | Read both files before responding or working |
| "experiment tracking", "track experiment", "log metrics", "log parameters", "autolog", "training callback", "XGBoost callback", "LightGBM callback" | `ml-development/SKILL.md` -> `experiment-tracking/SKILL.md` | Read both files before responding or working |

### Inference

Direct routing to inference skills. For model explainability (SHAP, feature importance), see Platform section.

| User Says | Route To | Action |
|-----------|----------|--------|
| "batch inference", "bulk predictions", "run_batch", "run()", "offline scoring", "score dataset", "batch predictions", "inference on registered model", "run predictions on registry model", "score with registered model", "offline inference", "SQL inference", "dbt inference", "dynamic table inference" | `batch-inference-jobs/SKILL.md` | Load immediately, set up batch inference |
| "feature_sources_per_function", "REST inference with feature store", "automatic feature retrieval at inference", "online feature store inference", "entity ID prediction", "OnlineStoreType.POSTGRES" | `spcs-inference/SKILL.md` → `online-feature-store/SKILL.md` | Load both files; version check is the first step in sub-skill |
| "create inference service", "inference endpoint", "serve model", "snowpark container services", "model endpoint", "deploy in container", "deploy model service", "real-time inference", "online inference", "create gateway", "gateway", "stable endpoint gateway" | `spcs-inference/SKILL.md` | Load immediately, create SPCS service |
| "partitioned inference", "@partitioned_api", "inference per partition", "CustomModel partition" | `model-registry/partitioned-inference/SKILL.md` | Load immediately, partitioned inference |
| "inference error", "mv.run fails", "service failing", "OOM", "debug inference", "inference not working" | `debug-inference/SKILL.md` | Load immediately, diagnose issue |
| "inference logs", "inference table", "captured inference", "autocapture data", "view inference history", "INFERENCE_TABLE", "inference requests", "inference responses", "view captured predictions" | `inference-logs/SKILL.md` | Load immediately, query inference data |
| "gateway A/B testing", "online inference experiment", "champion challenger", "model upgrade", "shadow testing", "gateway model monitor", "compare inference services", "evaluate A/B test", "traffic split", "canary deployment", "route traffic between models" | `gateway-ab-testing/SKILL.md` | Load immediately, gateway A/B testing |
| **"inference", "run inference"** (ambiguous, no batch/online signals) | **ASK USER** | Use disambiguation workflow above to clarify batch vs online |

### Platform

Standalone tools for direct requests. ml-development also references these at the right workflow moments (model-registry in Step 2, feature-store/datasets in Data Access Patterns, ml-jobs in Step 7, monitoring/pipeline/lineage in Step 8). For ml-jobs vs pipeline-orchestration disambiguation, see the inline disambiguation section above.

| User Says | Route To | Action |
|-----------|----------|--------|
| "register model", "model registry", "log model", "pickle to snowflake", "save model to snowflake", "upload model", ".pkl file", ".ubj file" | `model-registry/SKILL.md` | Read `model-registry/SKILL.md`, then start registration (Workflow A) |
| "deploy model", "deploy model for inference", "deploy for inference" | `model-registry/SKILL.md` | Read `model-registry/SKILL.md`, then ask deployment target (Workflow B) |
| "explain model", "SHAP", "Shapley values", "feature importance", "why did it predict", "model explainability", "interpret model" | `model-registry/SKILL.md` | Read `model-registry/SKILL.md`, then route to Workflow C (Explainability) |
| "model monitor", "monitor model", "add monitoring", "enable monitoring", "ML observability", "track drift", "model performance", "monitor predictions", "observability" | `model-monitor/SKILL.md` | Load immediately, set up monitoring (see disambiguation: gateway model monitor vs model version monitor) |
| "feature store", "feature view", "entity", "training data", "generate_training_set", "generate_dataset", "online features", "point-in-time features", "ASOF join" | `feature-store/SKILL.md` | Load immediately, route to feature store sub-skill |
| "create dataset", "version dataset", "list datasets", "SHOW DATASETS", "load dataset", "DataConnector", "to_tf_dataset", "to_torch_dataset", "to_torch_datapipe", "snow://dataset", "dataset versioning", "immutable dataset" | `datasets/SKILL.md` | Load immediately, manage datasets |
| "what trained this model", "model lineage", "dataset lineage", "GET_LINEAGE", "trace lineage", "no lineage showing", "lineage not captured", "which models use this dataset", "upstream lineage", "downstream lineage", "ML lineage", "data provenance" | `ml-lineage/SKILL.md` | Load immediately, query or debug lineage |
| "pipeline", "DAG", "task graph", "schedule training", "schedule inference", "orchestrate", "productionize", "automate retraining", "convert notebook to pipeline" | `ml-pipeline-orchestration/SKILL.md` | Read `ml-pipeline-orchestration/SKILL.md`, then set up the DAG |
| "ml job", "ml jobs", "run on snowflake compute", "submit job", "submit script", "submit file", "remote execution", "GPU training", "run python script on snowflake" | `ml-jobs/SKILL.md` | Read `ml-jobs/SKILL.md`, then set up the job |

**MLOps on Snowflake:** When the user asks about MLOps, map the MLOps lifecycle to Snowflake ML tools:

| MLOps Concern | Snowflake Tool |
|---------------|----------------|
| Model versioning & governance | Model Registry |
| Model version drift & performance | Model Version Monitor |
| Scheduled training/inference | ML Pipeline Orchestration (DAGs) |
| Data provenance & compliance | ML Lineage |
| Remote execution on compute pools | ML Jobs |
| Reproducibility & run comparison | Experiment Tracking |
| A/B testing & version comparison | SPCS Inference (create gateway) + Inference Logs (analyse results) + Gateway A/B Testing (monitor and evaluate) |

**Champion-challenger / model promotion** spans multiple tools: Model Registry (manage versions, set aliases) → Inference (serve both versions via split serving) → Inference Logs (capture results for analysis) → Gateway A/B Testing (monitor and compare across versions) → Model Registry (promote winner). Route to the specific tool based on where the user is in this workflow.

**Sub-skill path aliases** (for routing resolution):

- `ml-job` → `ml-jobs/SKILL.md` (singular form routes to plural directory)
- `ml-jobs` → `ml-jobs/SKILL.md`
- `mljob` → `ml-jobs/SKILL.md`
- `mljobs` → `ml-jobs/SKILL.md`

## Workflow

```markdown
Each user message → Re-evaluate current intent → Load Environment Guide → Detect Intent → Load appropriate sub-skill → Execute

Examples:
- "Train a classifier" → Load ml-development → Train locally → Done
- "Predict churn from this data" → Load ml-development → Train locally → Done
- "Help me improve this model" → Load ml-development → Iterate → Done
- "Run automl on this churn dataset" → Load automl → Experiment protocol → Hand off to next skill → Done
- "Find the best model for churn" → Load automl → Experiment protocol → Hand off to next skill → Done
- "Deploy my model.pkl" → Load model-registry → Register to Snowflake → Done
- "Train AND deploy" → Load ml-development → Train → Ask about deployment → If yes, load model-registry WITH CONTEXT (file path, framework, schema)
```

**Key principle**: Complete ONE task at a time. Only ask about the next step after the current step is done.

## Context Preservation Between Skills

**⚠️ CRITICAL:** When transitioning from ml-development to model-registry:

**Information to preserve and pass along:**

- Model file path (absolute path to serialized model file)
- Framework used (sklearn, xgboost, lightgbm, pytorch, tensorflow, etc.)
- Sample input schema (columns and types from training data)
- Any other relevant training context

**Why this matters:**

- Avoids asking the user to repeat information they just provided
- Prevents accidental retraining of the model
- Prevents modification of the training script
- Improves user experience with seamless workflow

**How to do it:**

1. When ml-development saves a model, it reports all details
2. When loading model-registry, explicitly mention this context
3. Model-registry checks for this context before asking questions
4. Use the preserved context instead of asking user again

**Example handoff:**

```markdown
ml-development: "Model saved to /path/to/model.pkl (sklearn). Would you like to register it?"
User: "Yes"
[Load model-registry with context: path=/path/to/model.pkl, framework=sklearn, schema=[...]]
model-registry: "I see you just trained a sklearn model. What should I call it in Snowflake?"
```

### After Registration: Preserve Model Context

When a model has been registered and the user transitions to any skill that operates on registered models (batch-inference-jobs, spcs-inference, model-monitor, gateway-ab-testing, ml-lineage), pass along the registered model name, version, and database/schema. Do not re-ask the user for information that was just collected or produced during registration.

## Sub-Skills

### automl

Automated end-to-end ML workflow for classification, regression, time-series forecasting, and clustering. Runs the full pipeline: quality gates (leakage detection, baseline, fairness, imbalance, outliers), feature engineering (manual + OpenFE), AutoGluon and/or manual model search and tuning across multiple trials with per-trial experiment tracking, and a final report with champion model + suggested next steps (registration, deep research, training script, inference, monitoring).

**Key differentiator:** The agent drives the search across feature engineering and model families.

### ml-development

Data exploration, statistical analysis, model training, and evaluation. Covers the full ML development workflow from data loading to model evaluation.

### model-registry

Deploy serialized models to Snowflake Model Registry. Supports various model formats (`.pkl`, `.ubj`, `.json`, `.pt`, etc.) depending on framework. Routes to `spcs-inference` sub-skill for inference service creation. Includes `partitioned-inference` sub-skill for partition-aware model deployment.

### experiment-tracking

Skills for tracking model training experiments using Snowflake's experiment tracking framework.

### spcs-inference

Deploy registered models to Snowpark Container Services for real-time inference. Handles compute pool selection, GPU/CPU configuration, num_workers, and service creation.

### batch-inference-jobs

Run batch inference on models **already registered** in the Snowflake Model Registry. Covers **two approaches**:
- **Native SQL Batch** (`mv.run()`): Warehouse-based, integrates with SQL pipelines
- **Job-based Batch** (`mv.run_batch()`): SPCS compute pools, for large-scale and unstructured data

### ml-jobs

Transform local **Python scripts** into Snowflake ML Jobs that run on Snowflake compute pools. Uses `submit_file()` or `submit_directory()`. Also includes compute pool reference (instance families, sizing).

### ml-pipeline-orchestration

Orchestrate multi-step ML workflows using Snowflake Task Graphs (DAGs) with the Python DAG API. Covers DAG creation, scheduling (Cron/timedelta), inter-task data passing, and notebook-to-pipeline conversion. Uses `@remote` for ML tasks on compute pools and warehouse tasks for orchestration.

### model-monitor

Set up **model version monitors** for ML Observability on Snowflake Model Registry models. Track drift and performance from a **source table** for a single model version.

**Key differentiator:** User wants to monitor **one model version** from a **source table** (no gateway).

### distributed-training

**Consolidated skill** covering all distributed ML training, processing, and tuning:
- **Distributed Estimators**: `XGBEstimator`, `LightGBMEstimator`, `PyTorchDistributor` for training one large model across nodes/GPUs
- **Many Model Training (MMT)**: Train one model per partition with auto-serialization and `get_model()`
- **DPF (Distributed Partition Function)**: General-purpose distributed processing for custom workflows
- **Tuner API**: Distributed hyperparameter tuning (Ray Tune on SPCS) with RandomSearch, GridSearch, BayesOpt

> **Note**: These APIs run server-side — either inside ML Jobs (submitted via CLI) or in Snowflake Notebooks with Container Runtime (Snowsight). For CLI submission, see ml-jobs.

### partitioned-inference (under model-registry)

Partitioned inference in the Model Registry using `@partitioned_api` decorator. Run inference with different submodels per data partition. Located at `model-registry/partitioned-inference/SKILL.md`.

### feature-store
Centralized feature management for ML workflows. Create feature stores, define entities, build managed (Dynamic Table) and external (View) feature views, generate training datasets with point-in-time correctness, and enable online feature serving for low-latency inference. Includes sub-skills for create, pipelines, training, online, monitor, lineage, and migrate.

### inference-logs
Query and analyze captured inference data from model services with Auto-Capture enabled. View historical request/response data logged via `INFERENCE_TABLE()`. Useful for debugging unexpected predictions, building retraining datasets, and A/B testing model versions.

### gateway-ab-testing

Set up **gateway model monitors** for Gateway A/B tests — drift and performance comparison during champion-challenger, canary, or shadow deployments. Covers services with Auto Capture → traffic-split gateway → gateway model monitor → evaluate in Snowsight or SQL.

**Key differentiator:** User wants to monitor or compare **multiple inference services behind a gateway**.

### datasets
Create and manage versioned, immutable Datasets for ML workflows. Datasets provide reproducibility, lineage tracking, and efficient access for distributed training with PyTorch, TensorFlow, and Snowpark ML. Use for creating training data snapshots, version control, and framework integration via DataConnector.

**Key differentiator:** User wants to create, version, list, or load Datasets.

### ml-lineage
Query and debug ML Lineage relationships. Trace data flow from source tables → feature views → datasets → models → services. Use for compliance audits, impact analysis, debugging missing lineage, and understanding model provenance.

**Key differentiator:** User wants to know "what trained this model" or "what models use this data" (not create objects).

### preprocessing
Preprocessing decision guide and implementation patterns. Covers OSS sklearn (small scale), Snowflake ML Preprocessors (warehouse), and Ray Data Preprocessors (distributed on container runtime). Includes the recommended E2E pattern for distributed preprocessing + model registry logging via **RayPreprocessorAdapter** (no Ray dependency at inference, no CustomModel needed) and the fallback CustomModel pattern.

**Key differentiator:** User asks "how should I preprocess?", needs to combine preprocessing with distributed training or model registry, or mentions RayPreprocessorAdapter.

## Reminders & Common Mistakes

### ❌ Don't assume a database/schema — always ask

When the workflow involves creating or writing to any Snowflake object (table, stage, model registry entry, experiment, etc.), **never silently pick a database/schema**. Always confirm with the user first.

- If a `DATABASE.SCHEMA` has already been used in this session, offer it as the default:
  ```
  I'll need to create [object] in Snowflake. I see we've been working with `<DATABASE>.<SCHEMA>`.
  Should I use that, or would you prefer a different database/schema?
  ```
- If no database/schema has been used yet, ask explicitly:
  ```
  Which database and schema should I use for [object]? (format: DATABASE.SCHEMA)
  ```
- **Carry the confirmed choice forward** — reuse it for subsequent objects in the session, but still confirm each time.
- **⚠️ Personal databases (e.g. `USER$VINAY`) are not supported** for ML workflows. If the user picks a personal database, warn them:
  ```
  Personal databases like `USER$<USERNAME>` don't support creating tables, model registry operations, or inference services. Please provide a standard database/schema instead.
  ```
- **⚠️ STOP**: Wait for the user's response before proceeding with any object creation.
