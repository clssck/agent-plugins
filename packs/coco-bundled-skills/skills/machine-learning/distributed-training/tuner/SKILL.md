---
name: distributed-tuner
description: "Distributed hyperparameter tuning with Ray Tune on Snowpark Container Services. Supports RandomSearch, GridSearch, and BayesOpt algorithms."
parent_skill: distributed-training
path: machine-learning/distributed-training/tuner
---

# Distributed Hyperparameter Tuning (Tuner API)

Distributed hyperparameter optimization using Ray Tune on Snowpark Container Services.

## When to Use

- **Find optimal hyperparameters** for ML models at scale
- **Compare search algorithms**: RandomSearch, GridSearch, BayesOpt
- **Tune distributed estimators** (XGBEstimator, LightGBMEstimator) with `uses_snowflake_trainer=True`
- **Scale HPO** across multiple workers in parallel

## Execution Environment

Tuner runs on Snowpark Container Services — via ML Jobs (CLI) or Snowflake Notebooks with Container Runtime (Snowsight). See `../../ml-jobs/SKILL.md` for CLI submission and `../references/compute-pool-sizing.md` for instance family selection.

**Minimum requirement**: 2 CPUs per node (HPO orchestration overhead).

---

# Workflow

## Step 1: Define Training Function

```python
from snowflake.ml.modeling.tune import get_tuner_context
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

def train_func():
    ctx = get_tuner_context()
    params = ctx.get_hyper_params()      # Sampled hyperparameters
    datasets = ctx.get_dataset_map()     # Data connectors
    
    # Load data
    train_df = datasets["train"].to_pandas()
    test_df = datasets["test"].to_pandas()
    
    X_train, y_train = train_df.drop("LABEL", axis=1), train_df["LABEL"]
    X_test, y_test = test_df.drop("LABEL", axis=1), test_df["LABEL"]
    
    # Train with sampled hyperparameters
    model = RandomForestClassifier(
        n_estimators=params["n_estimators"],
        max_depth=params["max_depth"],
        random_state=42
    )
    model.fit(X_train, y_train)
    
    # Evaluate and report (metric name must match TunerConfig.metric)
    accuracy = accuracy_score(y_test, model.predict(X_test))
    ctx.report(metrics={"accuracy": accuracy}, model=model)
```

**STOPPING POINT**: Confirm training function structure before proceeding.

---

## Step 2: Define Search Space

```python
from snowflake.ml.modeling.tune import uniform, loguniform, randint, choice

search_space = {
    "n_estimators": randint(50, 200),      # Integer [50, 200)
    "max_depth": randint(3, 15),            # Integer [3, 15)
    "learning_rate": loguniform(1e-5, 0.1), # Log-scale float
    "subsample": uniform(0.6, 1.0),         # Linear float
    "booster": choice(["gbtree", "dart"]),  # Categorical
}
```

### Search Space Functions

| Function | Use Case | Example |
|----------|----------|---------|
| `uniform(lower, upper)` | Continuous float | `uniform(0.001, 0.1)` |
| `loguniform(lower, upper)` | Exponentially-scaled | `loguniform(1e-5, 1e-1)` |
| `randint(lower, upper)` | Integer (upper exclusive) | `randint(50, 200)` |
| `choice([options])` | Categorical | `choice(['adam', 'sgd'])` |

---

## Step 3: Configure Tuner

```python
from snowflake.ml.modeling.tune import TunerConfig
from snowflake.ml.modeling.tune.search import RandomSearch

config = TunerConfig(
    metric="accuracy",           # Must match ctx.report() key
    mode="max",                  # "max" for accuracy, "min" for loss
    search_alg=RandomSearch(),   # Or GridSearch(), BayesOpt()
    num_trials=10,               # Max configurations to try
)
```

### Search Algorithms

**RandomSearch** (default): Randomly samples configurations. Good baseline.
```python
config = TunerConfig(metric="accuracy", mode="max", search_alg=RandomSearch(), num_trials=20)
```

**GridSearch**: Exhaustive search. Requires lists in search space (not sampling functions).
```python
search_space = {"learning_rate": [0.01, 0.05, 0.1], "max_depth": [3, 5, 7]}
config = TunerConfig(metric="accuracy", mode="max", search_alg=GridSearch())
```

**BayesOpt**: Bayesian optimization with Gaussian processes. Best when evaluations are expensive.
```python
config = TunerConfig(metric="accuracy", mode="max", search_alg=BayesOpt(), num_trials=15)
```
> **BayesOpt limitations**: Only works with continuous/numeric search spaces (`uniform`, `loguniform`). Does not support `choice()` or categorical parameters. Best with a small number of hyperparameters (<10). Sequential by nature — benefits less from high parallelism than RandomSearch.

### TunerConfig Parameters

| Parameter | Description |
|-----------|-------------|
| `metric` | Must match key in `ctx.report(metrics={...})` |
| `mode` | `"max"` for accuracy/f1/auc, `"min"` for loss/error |
| `num_trials` | Maximum configurations to evaluate |
| `uses_snowflake_trainer` | Set `True` for XGBEstimator/LightGBMEstimator |
| `resource_per_trial` | GPU allocation: `{"CPU": 2, "GPU": 1}` |
| `max_concurrent_trials` | Limit parallel trials |

**STOPPING POINT**: Confirm search space and algorithm choice before running.

---

## Step 4: Run Tuning

```python
from snowflake.ml.modeling.tune import Tuner
from snowflake.ml.data.data_connector import DataConnector

# Create data connectors
train_connector = DataConnector.from_dataframe(session.table("TRAIN_DATA"))
test_connector = DataConnector.from_dataframe(session.table("TEST_DATA"))

# Run distributed tuning
tuner = Tuner(train_func, search_space, config)
results = tuner.run(dataset_map={"train": train_connector, "test": test_connector})
```

---

## Step 5: Access Results

```python
# All trials as DataFrame
results.results
# Columns: config/learning_rate, config/n_estimators, accuracy, ...

# Best trial (single-row DataFrame)
results.best_result
best_lr = results.best_result["config/learning_rate"].iloc[0]
best_accuracy = results.best_result["accuracy"].iloc[0]

# Best trained model (if model= passed to ctx.report())
best_model = results.best_model
predictions = best_model.predict(X_test)

# Filter good trials
good_trials = results.results[results.results["accuracy"] > 0.9]

# Sort by metric
sorted_trials = results.results.sort_values("accuracy", ascending=False)
```

### TunerResults Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `results` | DataFrame | All trials with config columns + metric columns |
| `best_result` | DataFrame | Single row with best config + metrics |
| `best_model` | Model object | Trained model from best trial |

---

# HPO with Distributed Estimators

When tuning XGBEstimator or LightGBMEstimator, set `uses_snowflake_trainer=True`:

```python
from snowflake.ml.modeling.tune import Tuner, TunerConfig, get_tuner_context, loguniform, randint
from snowflake.ml.modeling.distributors.xgboost import XGBEstimator
from snowflake.ml.data.data_connector import DataConnector

def train_distributed_xgb():
    ctx = get_tuner_context()
    params = ctx.get_hyper_params()
    datasets = ctx.get_dataset_map()
    
    estimator = XGBEstimator(
        params={
            "objective": "binary:logistic",
            "learning_rate": params["learning_rate"],
            "max_depth": params["max_depth"],
        }
    )
    
    booster = estimator.fit(
        dataset=datasets["train"],
        input_cols=["FEATURE_1", "FEATURE_2"],
        label_col="LABEL",
        eval_set=datasets["test"]
    )
    
    # Get eval metric from training
    eval_results = estimator.get_eval_results()
    final_logloss = eval_results["eval"]["logloss"][-1]
    
    ctx.report(metrics={"logloss": final_logloss}, model=booster)

search_space = {
    "learning_rate": loguniform(0.01, 0.3),
    "max_depth": randint(3, 8),
}

config = TunerConfig(
    metric="logloss",
    mode="min",
    num_trials=10,
    uses_snowflake_trainer=True,  # REQUIRED for distributed estimators
)

tuner = Tuner(train_distributed_xgb, search_space, config)
results = tuner.run(dataset_map={
    "train": DataConnector.from_dataframe(session.table("TRAIN_DATA")),
    "test": DataConnector.from_dataframe(session.table("TEST_DATA")),
})

# Access best model and hyperparameters
best_booster = results.best_model
best_config = results.best_result
print(f"Best learning_rate: {best_config['config/learning_rate'].iloc[0]}")
print(f"Best max_depth: {best_config['config/max_depth'].iloc[0]}")
```

---

# Complete Imports

```python
from snowflake.ml.modeling.tune import (
    Tuner,
    TunerConfig,
    get_tuner_context,
    # Search space functions
    uniform,
    loguniform,
    randint,
    choice,
)
from snowflake.ml.modeling.tune.search import RandomSearch, GridSearch, BayesOpt
from snowflake.ml.data.data_connector import DataConnector
```

---

# Troubleshooting

| Issue | Solution |
|-------|----------|
| `RuntimeError: at least 2 CPUs` | HPO requires minimum 2 CPUs per node |
| Metric not found | Ensure `ctx.report(metrics={...})` includes exact metric name from TunerConfig |
| GridSearch with sampling functions | GridSearch requires lists: `[0.1, 0.2]` not `uniform(0.1, 0.2)` |
| GPU not used | Set `resource_per_trial={"GPU": 1}` in TunerConfig |
| Model not saved | Pass `model=` to `ctx.report()` to save for `results.best_model` |

---

# Next Steps

After finding optimal hyperparameters:
- **Train final model**: Use `distributed-estimators` with best config
- **Register model**: See `../../model-registry/SKILL.md`
- **Deploy for inference**: See `../../spcs-inference/SKILL.md`

---

# Output Checklist

- [ ] Training function defined with `get_tuner_context()`
- [ ] Search space uses appropriate sampling functions
- [ ] TunerConfig metric matches `ctx.report()` key
- [ ] `uses_snowflake_trainer=True` if using distributed estimators
- [ ] Results accessed via `results.best_result` and `results.best_model`
