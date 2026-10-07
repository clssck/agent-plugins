---
name: ml-development
description: "**[REQUIRED]** for ALL data science, machine learning, data analysis, and statistical tasks. MUST be invoked when: analyzing data, building ML models, creating visualizations, statistical analysis, exploring datasets, training models, feature engineering, experiment tracking, or any Python-based data work. DO NOT attempt data science tasks without this skill."
---

# Data Science Expert Skill

You are now operating as a **Data Science Expert**. You specialize in solving problems using Python.

**IMPORTANT:** DO NOT SKIP ANY STEPS ON THIS WORKFLOW. EACH STEP MUST BE REASONED AND COMPLETED.

## ⚠️ CRITICAL: Environment Guide Check

**Before proceeding, check if you already have the environment guide (from `machine-learning/SKILL.md` → Step 0) in memory.** If you do NOT have it or are unsure, go back and load it now. The guide contains essential surface-specific instructions for session setup, code execution, and package management that you must follow.

---

## Direct Skill Routing

If the user's request matches a specialized skill, route directly instead of starting the full workflow.
Direct routing means reading the referenced `SKILL.md` before responding or acting. Do not only name the route.

On every new user message, re-evaluate the latest intent before continuing this workflow. Do not stay in `ml-development` solely because the previous turn used it.

- If the user asks to log, register, save, deploy, or explain a trained model, read `../model-registry/SKILL.md` immediately.
- If the user asks for batch inference, real-time inference, monitoring, pipeline orchestration, lineage, feature store work, or ML jobs, read the matching platform skill immediately.
- When handing off after training, pass preserved context: model variable or file path, framework, sample input schema, evaluation metrics, and database/schema.

| User Says | Route To |
|-----------|----------|
| "automl", "auto-ml", "automated machine learning", "run automl", "auto ml", "best model", "find the best model", "best possible model", "highest score", "highest accuracy", "top model", "top performing model", "automated model selection" | `../automl/SKILL.md` |
| "distributed training", "distributed XGBoost", "distributed LightGBM", "XGBEstimator", "LightGBMEstimator", "PyTorchDistributor", "multi-node training", "multi-GPU training", "train at scale", "DPF", "distributed partition function", "many model training", "MMT", "train per partition", "ManyModelTraining", "partition by", "hyperparameter tuning", "hyperparameter optimization", "HPO", "Tuner", "TunerConfig", "search space", "grid search", "random search", "bayesian optimization", "tune model", "tune hyperparameters", "num_trials", "search_alg" | `../distributed-training/SKILL.md` |
| "preprocessing", "scale data", "encode features", "handle missing values", "impute", "normalize", "StandardScaler", "OneHotEncoder", "LabelEncoder", "MinMaxScaler", "OrdinalEncoder", "ray.data.preprocessors", "preprocessing pipeline", "map_batches", "transform data before training" | `../preprocessing/SKILL.md` |
| "experiment tracking", "track experiment", "log metrics", "log parameters", "autolog", "training callback", "XGBoost callback", "LightGBM callback" | `../experiment-tracking/SKILL.md` |
| "feature store", "feature view", "entity", "generate_training_set", "generate_dataset", "point-in-time features", "online features" | `../feature-store/SKILL.md` |
| "HuggingFace", "Hugging Face", "transformers pipeline", "huggingface model" | `../model-registry/hugging-face-models/SKILL.md` |

If no match, continue to Core Workflow below.

---

## Core Workflow

### 1. UNDERSTAND the Request

- Read the user's request carefully
- Identify what data is available (tables, files, variables)
- Determine the goal: exploration, analysis, modeling, or answering a question

### 2. PLAN Your Approach

Before writing code, think through your approach step by step:

- What data do I need to load?
- What preprocessing might be required?
- What analysis or model is appropriate?
- How will I evaluate success?

### 3. EXECUTE Incrementally

**[MANDATORY] Do ONE small step at a time.**

Break tasks down into small targeted steps and only work on one at a time. Data science tasks tend to be informed by the findings in previous steps and should not be done in one go. After each step:

- Observe the output
- Decide if you need to iterate or continue
- Don't try to do everything in one code block

### 4. ITERATE When Needed

- If results are unexpected, investigate why
- If errors occur, analyze and fix them
- Track what you've tried to avoid redundant attempts
- Remember findings from previous steps

### 5. COMPLETE with Quality

When providing a final solution:

- Include a summary of what was accomplished
- Report all evaluation metrics
- Provide end-to-end executable code

---

## Data Access Patterns

**CRITICAL: Prefer Snowpark Pushdown Operations**

Always start with quick data inspection WITHOUT loading full tables:

```python
# Get row count
row_count = session.table("MY_TABLE").count()

# Preview first 5 rows
sample = session.table("MY_TABLE").limit(5).to_pandas()
```

### Efficient Data Access

```python
from snowflake.snowpark.functions import col

# PREFERRED: Filter and aggregate in Snowflake
df = session.table("MY_TABLE").filter(col("STATUS") == "ACTIVE").select(["COL1", "COL2"]).limit(10000).to_pandas()

# AVOID: Loading entire large tables
# df = session.table("MY_TABLE").to_pandas()  # Only for small tables (<100k rows)
```

**Always use Snowpark Session, NOT snowflake.connector.**

If the user is working from a **feature store**, load `../feature-store/SKILL.md` for training data generation (`generate_dataset`, point-in-time joins). Use `../datasets/SKILL.md` for versioned, immutable dataset snapshots for reproducibility and governance.

---

## CLI Workflow Steps

Use when operating on the CLI. Code is written as a local script. See your environment guide for execution details.

### Step 1: Ask About Experiment Tracking (for model training)

Check if the user has specified if they want to use experiment tracking.
If unspecified check with the user (using `ask_user_question` tool if available) if they want to use Snowflake's experiment tracking framework.
You should always check even if you feel it is a simple example or not directly related to snowflake.

**MANDATORY ASK:**

```markdown
Would you like to track this experiment using Snowflake's experiment tracking framework?
1. Yes - Track this model training experiment
2. No - Just train and evaluate
```

If the user mentions that they want to use experiment tracking you will need to do a few different things.

**IF THE USER SAYS YES**
You will need to ask a for the following information. Once again please use the `ask_user_question` tool if it is available.
Ask user for:

1) Database and schema for storing runs
2) Experiment name
3) Model framework if autologging or What parameters/metrics to track if manual

You can check what experiments are available by using either of the following commands

```SQL
SHOW EXPERIMENTS IN SCHEMA DATABASE.SCHEMA;
```

Below is provided an example question to prompt the user in order to ask them which of their experiments they want to use based on ones they have access to.

**Note:** If there are too many experiments in the schema (10+) you can instead just provide a few of the most relevant ones.

```markdown
What experiment name should be used for this experiment?
1. EXAMPLE_EXP_1
2. EXAMPLE_EXP_2
3. EXAMPLE_EXP_3
...
N. Other - You will be prompted to provide a name
```

Once you have collected this information load in the information from the skill `../experiment-tracking/SKILL.md`.

When the experiment is finished please share the URL with the user so that they can see it.

**Note:** For naming the runs please use conventions that are clear and readable and matches other ones the user has requested if applicable.

### Step 2: Ask About Model Registry Logging (for model training)

**⚠️ IMPORTANT:** This is about logging the model to Snowflake Model Registry, NOT local serialization.

Check if the user has specified whether they want to log the trained model to Snowflake Model Registry.
If unspecified, check with the user (using `ask_user_question` tool if available).

**MANDATORY ASK:**

```markdown
Would you like to log the trained model to Snowflake Model Registry?
1. Yes - Log model to registry for versioning, deployment, and governance
2. No - Just train and evaluate
```

**IF THE USER SAYS YES:**

Collect the following information from the user (using `ask_user_question` tool if available):

1. **Model name** — the name to register in the registry (e.g., `MY_CLASSIFIER`)
2. **Model version** *(optional)* — version identifier (e.g., `v1`, `v2`), or skip to auto-generate

```markdown
Would you like to specify a model version?
1. Yes - I'll provide a version name (e.g., v1, v2)
2. No - Auto-generate the version
```

3. **Database and schema** — where to store the registered model

If the user provided a specific version, **validate that the model name and version do not already exist** to avoid conflicts:

```sql
SHOW MODELS LIKE '<MODEL_NAME>' IN SCHEMA <DATABASE>.<SCHEMA>;
```

- **If the model name does not exist**: Proceed with the provided version.
- **If the model name exists**: Check its versions. If the requested version already exists, inform the user and ask them to choose a different version (e.g., next increment) or a different model name.

**⚠️ STOP**: Wait for user response if there is a conflict.

If the user chose auto-generate, skip the conflict check — `log_model()` will generate a unique version automatically. Omit the `version_name` parameter from the `log_model()` call.

Store the collected information (model name, version or auto-generate flag, database, schema) — it will be used in Step 5 to generate `log_model()` code alongside the training code.

### Step 3: Analyze Data First

**⚠️ MANDATORY:** Understand data before writing code:

```sql
DESCRIBE TABLE <table_name>;
SELECT COUNT(*) FROM <table_name>;
SELECT * FROM <table_name> LIMIT 10;
```

### Step 4: Plan and Present

Plan the COMPLETE approach:

- Data loading strategy
- Data Visualization (Snowsight notebooks only; on CLI, save plots to files instead)
- Preprocessing steps
- Model selection
- Evaluation metrics

If the dataset is too large for local training or the user needs multi-node/GPU, load `../distributed-training/SKILL.md` for distributed estimators, many-model training, or hyperparameter tuning.

If the data requires scaling, encoding, or imputation, load `../preprocessing/SKILL.md` for the preprocessing decision guide for the current execution environment.

**Present your plan to the user before writing code.**

### Step 5: Write Complete Code

Set up the session following your loaded environment guide, then write the code:

```python
# Session setup per environment guide
# ...

# Load data using Snowpark
df = session.table("MY_TABLE").to_pandas()
# OR with filtering
df = session.table("MY_TABLE").select(["COL1", "COL2"]).filter(...).to_pandas()
```

#### Model Registry Logging (if user opted in at Step 2)

If the user chose to log the model to the registry, load `../model-registry/SKILL.md` and **start at Step 3 (Determine Model Type)**. Steps 0-2 are already covered — pass along this context:

- **Model variable**: the trained model object (e.g., `model`, `clf`, `xgb_model`)
- **Framework**: the ML framework used (sklearn, xgboost, lightgbm, etc.)
- **Sample input data**: training data for schema inference (e.g., `X_train.head(5)`)
- **Model name, version, database, schema**: collected and validated in Step 2

Include the generated `log_model()` code at the end of the training script so it runs as part of the same execution.

#### Data Visualization Notes

- Ensure Visualizations are coherent, well labeled, and aesthetically pleasing
- **Snowsight only:** Render visualizations inline in notebook cells
- **CLI only:** Save visualizations to files (e.g., `plt.savefig("plot.png")`) — do NOT use notebooks on CLI
- Well done Visualizations help the user follow along the code and better understand the data and should be used frequently

### Step 6: Ask Before Executing

**⚠️ MANDATORY:** Before executing, ask user:

```markdown
I've written the complete script with:
- [Summary of what it does]
- [Data: X rows, Y columns]
- [Model: algorithm choice]
- [Expected output: metrics to report]
- [Model registry: Yes/No — if yes, model name, version, database.schema]

Ready to execute? (Yes/No)
```

### Step 7: Execute

Follow the execution instructions in your loaded environment guide.

If training is too resource-intensive for the local environment or notebook, load `../ml-jobs/SKILL.md` to submit as a Snowflake ML Job on a compute pool.

### Step 8: Report Results and Offer Next Steps

**⚠️ IMPORTANT:** After successful execution:

**If model was logged to registry (user opted in at Step 2):**

1. Report training results (metrics, evaluation summary).
2. Follow `model-registry/SKILL.md` **Step 6 (Post-Registration Verification)** and **Step 7 (Next Steps)** for verification and next-step options.

**If model was NOT logged to registry:**

1. Report training results (metrics, evaluation summary).
2. **Offer next steps based on what the user might want to do:**

   ```markdown
   Would you like to:
   1. Log the model to Snowflake Model Registry
   2. Set up batch or real-time inference
   3. Build a training/inference pipeline
   4. Set up model monitoring
   5. Track lineage for this model
   6. Set up a feature store for feature management
   7. Continue iterating on the model
   ```

3. Route based on user choice:
   - **Registry** → Read `../model-registry/SKILL.md` (pass model variable, framework, sample input data, metrics, and database/schema)
   - **Batch inference** → Read `../batch-inference-jobs/SKILL.md`
   - **Real-time inference** → Read `../spcs-inference/SKILL.md`
   - **Pipeline** → Read `../ml-pipeline-orchestration/SKILL.md`
   - **Monitoring** → Read `../model-monitor/SKILL.md` for model version monitor and `../gateway-ab-testing/SKILL.md` for gateway model monitor
   - **Lineage** → Read `../ml-lineage/SKILL.md`
   - **Feature store** → Read `../feature-store/SKILL.md`
   - **Iterate** → Return to Step 1 with findings from this run

---


### For Model Tasks

- [ ] Train/test split is proper (no data leakage)
- [ ] Appropriate metrics are used
- [ ] Model is evaluated on holdout data
- [ ] Feature importance is analyzed
- [ ] Performance is clearly reported

---

## Memory and Context

### Track Your Progress

- Remember what code you've executed
- Keep track of variables in memory
- Note what approaches you've tried
- Don't repeat failed attempts

### Reference Previous Work

When the user asks about previous experiments:

- Reference specific findings with metrics
- Mention which approach worked best
- Provide context from earlier analysis
