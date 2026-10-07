---
name: preprocessing
description: "ML data preprocessing and feature transformation. Use when: preprocessing, scaling, encoding, imputation, normalize, handle missing values, StandardScaler, OneHotEncoder, LabelEncoder, MinMaxScaler, OrdinalEncoder, ray.data.preprocessors, transform data before training, preprocessing pipeline, Chain, map_batches, transform_batch, RayPreprocessorAdapter, from_fitted_chain, ext_modules."
parent_skill: machine-learning
path: machine-learning/preprocessing
---

# ML Preprocessing

## When to Load

- User asks about preprocessing, scaling, encoding, imputation, or feature transformation
- User is setting up distributed training and needs to prepare data
- User asks which preprocessing approach to use on Snowflake
- User mentions RayPreprocessorAdapter, from_fitted_chain, or wants to log Ray preprocessing to registry
- User asks how to use Ray preprocessing without CustomModel or ray-data dependency at inference

## Routing

Determine the user's execution environment, then route:

| Environment | Route |
|-------------|-------|
| Container runtime (Snowflake Notebooks with CR, ML Jobs) | [Ray Data Preprocessors](#ray-data-preprocessors-container-runtime) |
| Local Python / single-node prototyping | [OSS Preprocessing](#oss-preprocessing-local) |

**⚠️ If the user is doing distributed training** (XGBEstimator, LightGBMEstimator, PyTorchDistributor, MMT, DPF) → **always route to Ray Data Preprocessors**. They keep the entire pipeline on the same Ray cluster and distribute both fit and transform.

**⚠️ Do not recommend `snowflake.ml.modeling.preprocessing`** for container runtime workflows. Those preprocessors run on the warehouse, not the runtime — this creates a split execution model. They also lack SPCS inference support and can OOM on high cardinality columns.

**⚠️ Do not recommend sklearn + `map_batches`** as a preprocessing strategy. Transform is distributed but fit is single-node — if the dataset exceeds one node's memory, fit fails.

---

## OSS Preprocessing (Local)

For local/single-node work, use standard open source preprocessing (e.g., sklearn `Pipeline`, `ColumnTransformer`):

```python
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer

preprocessor = ColumnTransformer([
    ("num", StandardScaler(), num_cols),
    ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
])
pipeline = Pipeline([("prep", preprocessor), ("model", model)])
pipeline.fit(X_train, y_train)
```

Many OSS pipelines (e.g., sklearn) log natively to the registry — no `CustomModel` needed. When ready to register, load `../model-registry/SKILL.md`.

---

## Ray Data Preprocessors (Container Runtime)

Distributed preprocessing using `ray.data.preprocessors`. Both fit and transform run across the Ray cluster. Feeds directly into `DataConnector` for distributed training.

Available: `SimpleImputer`, `StandardScaler`, `MinMaxScaler`, `MaxAbsScaler`, `RobustScaler`, `OrdinalEncoder`, `LabelEncoder`, `OneHotEncoder`, `Normalizer`, `PowerTransformer`, and more. Full list: [Ray Data Preprocessors API](https://docs.ray.io/en/latest/data/api/preprocessor.html).

### Step 1: Determine Preprocessing Plan

**If the user already specified their transformations** (e.g. "scale these columns, encode those, impute nulls with median") → skip ahead to Step 2 and build the Chain to match.

**If the user has a data source but hasn't specified transformations**, inspect the data to inform your recommendations:

```python
desc = snowpark_df.describe().to_pandas()
dtypes = snowpark_df.dtypes
null_counts = snowpark_df.select(
    [F.sum(F.iff(F.col(c).is_null(), 1, 0)).alias(c) for c in snowpark_df.columns]
).to_pandas().iloc[0]
```

Use the results to suggest a preprocessing plan — which columns to scale, encode, or impute and why — then confirm with the user before generating code.

**If neither a data source nor a plan is clear**, ask what table or DataFrame they're working with, then inspect as above.

### Step 2: Load Data into Ray Dataset

```python
from snowflake.ml.data.data_connector import DataConnector

dc = DataConnector.from_dataframe(snowpark_df)
ray_ds = dc.to_ray_dataset()
```

### Step 3: Build and Fit a Chain

`Chain` composes multiple preprocessors into a single object — one `fit_transform()` call, one artifact to save.

```python
from ray.data.preprocessors import Chain, SimpleImputer, OrdinalEncoder, MinMaxScaler

chain = Chain(
    SimpleImputer(columns=[<COLS_WITH_NULLS>], strategy="mean"),
    OrdinalEncoder(columns=[<CAT_COLS>]),
    MinMaxScaler(columns=[<NUM_COLS>]),
)
ray_ds = chain.fit_transform(ray_ds)
```

Adapt the Chain to the user's needs. Only include preprocessors they need.

**Serialization note:** The fitted Chain should be serialized with `pickle` and bundled as an artifact when logging to the model registry. At inference, convert Arrow-backed string columns to `object` dtype before calling `chain.transform_batch()` — see Common Issues. `transform_batch()` is pure pandas — no running Ray cluster needed — but `ray-data` must be listed as a conda dependency for unpickling. Any custom `map_batches` transforms (Step 4) must be replicated in the `predict()` method since they aren't captured by the Chain.

**Train/eval split:** If the user needs a validation set, fit on training data only:

```python
train_ds, eval_ds = ray_ds.train_test_split(test_size=0.2)
train_ds = chain.fit_transform(train_ds)
eval_ds = chain.transform(eval_ds)  # same fitted stats, no refit
```

### Step 4: Custom Transforms via `map_batches` (If Needed)

For transforms not covered by built-in preprocessors (feature crosses, log transforms, business logic):

```python
def add_features(batch: pd.DataFrame) -> pd.DataFrame:
    batch["FEAT_1X2"] = batch["FEAT_1"] * batch["FEAT_2"]
    batch["FEAT_4_LOG"] = np.log1p(batch["FEAT_4"].clip(lower=0))
    return batch

ray_ds = ray_ds.map_batches(add_features, batch_format="pandas")
```

**⚠️ `map_batches` is stateless.** Each batch is processed independently — no global statistics. Use `ray.data.preprocessors` (not `map_batches`) for anything needing fitted stats (mean, min/max, category mappings). `map_batches` is for row-level or batch-level transforms only.

### Step 5: Hand Off to Training

**Distributed training (container runtime)** → Load `../distributed-training/estimators/SKILL.md` and pass along:
- A `DataConnector` wrapping the preprocessed dataset: `DataConnector.from_ray_dataset(ray_ds)`
- The list of input columns (including any custom features added)
- The label column name

**OSS / local training** → The user can train directly with their framework of choice (sklearn, XGBoost, LightGBM, AutoGluon, etc.) using the preprocessed data.

### Step 6: Logging to Model Registry (Ray Path)

**Scope note:** This step shows how to log Ray preprocessing to the registry. It includes minimal training examples because RayPreprocessorAdapter requires combining the preprocessing adapter with a trained model into an sklearn Pipeline. For comprehensive training guidance, see `../distributed-training/SKILL.md`.

**Recommended: RayPreprocessorAdapter** — Converts Ray preprocessing to sklearn Pipeline, no `CustomModel` wrapper, no `ray-data` inference dependency.

#### Option A: RayPreprocessorAdapter (Recommended)

Extract fitted Chain statistics into an sklearn-compatible transformer, combine with your trained model in a Pipeline, and log natively to the registry.

**Extract adapter from fitted Chain:**

```python
from snowflake.ml.data.preprocessor import RayPreprocessorAdapter

adapter = RayPreprocessorAdapter.from_fitted_chain(chain)
```

**Train model on transformed data:**

```python
import xgboost

train_pd = ray_ds.to_pandas()
feature_cols = [<FEATURE_COLUMNS>]

model = xgboost.XGBClassifier(n_estimators=100, max_depth=5, random_state=42)
model.fit(train_pd[feature_cols], train_pd["LABEL"])
```

**For XGBEstimator (distributed training):**

```python
from snowflake.ml.modeling.distributors.xgboost import XGBEstimator, XGBScalingConfig
from implementations.ray_data_ingester import RayDataIngester

estimator = XGBEstimator(
    n_estimators=100,
    objective="multi:softmax",
    params={"num_class": 3},
    scaling_config=XGBScalingConfig(use_gpu=False),
)
transformed_dc = DataConnector.from_ray_dataset(ray_ds, ingestor_class=RayDataIngester)
estimator.fit(transformed_dc, input_cols=feature_cols, label_col="LABEL")

# Convert to sklearn estimator for pipeline
y_labels = ray_ds.to_pandas()["LABEL"]
model = estimator._to_sklearn_estimator(y=y_labels)
```

**Build sklearn Pipeline:**

```python
from sklearn.pipeline import Pipeline

pipeline = Pipeline([
    ("preprocessing", adapter),
    ("model", model),
])
```

**Log to registry:**

Before logging, confirm with the user:
- Database and schema (format: `DATABASE.SCHEMA`)
- Model name
- Version name
- Target platforms (`["WAREHOUSE"]` recommended in Container Runtime)

```python
from snowflake.ml.registry import Registry
import snowflake.ml.data.preprocessor as preprocessor_mod

reg = Registry(session=session, database_name="<DB>", schema_name="<SCHEMA>")

mv = reg.log_model(
    pipeline,
    model_name="<MODEL_NAME>",
    version_name="v1",
    ext_modules=[preprocessor_mod],  # Required: embeds adapter class in pickle
    sample_input_data=snowpark_df.drop("LABEL").limit(5),
    target_platforms=["WAREHOUSE"],
)
```

**Requirements:**
- **mlruntimes >= 2.7.0** — RayPreprocessorAdapter was introduced in mlruntimes 2.7.0 (available in Container Runtime: Snowflake Notebooks, ML Jobs)
- **ext_modules=[preprocessor_mod] is required** — Without this parameter, inference will fail with `ModuleNotFoundError: No module named 'snowflake.ml.data.preprocessor'`

**Recommendations:**
- Use `target_platforms=["WAREHOUSE"]` in Container Runtime to ensure warehouse inference (avoids defaulting to SPCS)

**Benefits:**
- No `ray-data` dependency at inference time
- Supports 19 Ray preprocessors: all scalers, encoders, imputers, normalizers, discretizers, text vectorizers, and `Chain`

**Limitations:**
- `map_batches` transforms are NOT captured — replicate in a separate sklearn transformer if needed
- Unsupported: `TorchVisionPreprocessor` (requires torchvision at inference)

**Inference (no Ray needed):**

```python
predictions = mv.run(test_df, function_name="predict")
```

---

#### Option B: CustomModel Wrapper (Fallback)

Use this when RayPreprocessorAdapter doesn't support your preprocessor or you need custom inference logic beyond what sklearn Pipelines offer.

Load `../model-registry/SKILL.md` for full `CustomModel` and `log_model` details — below is the preprocessing-specific pattern:

```python
import pickle

# Serialize the fitted Chain
with open("/tmp/chain.pkl", "wb") as f:
    pickle.dump(chain, f)
```

In the `CustomModel.predict()` method, replay preprocessing before calling the model:

```python
@custom_model.inference_api
def predict(self, input_df: pd.DataFrame) -> pd.DataFrame:
    import pickle
    with open(self.context.path("chain"), "rb") as f:
        chain = pickle.load(f)

    df = input_df.copy()
    # Convert Arrow-backed strings to object dtype (Ray encoders expect numpy object)
    for col in df.select_dtypes(include=["string"]).columns:
        df[col] = df[col].astype("object")

    df = chain.transform_batch(df)

    # Replicate any custom map_batches transforms from Step 4 here
    # df["FEAT_1X2"] = df["FEAT_1"] * df["FEAT_2"]

    preds = self.context.model_ref("my_model").predict(...)
    return pd.DataFrame({"PREDICTION": preds})
```

When logging, bundle the Chain pickle as an artifact alongside the trained model:

Before logging, confirm with the user:
- Database and schema (format: `DATABASE.SCHEMA`)
- Model name
- Version name
- Target platforms

```python
model_context = custom_model.ModelContext(
    artifacts={"chain": "/tmp/chain.pkl"},
    models={"my_model": trained_model},
)

reg = Registry(session=session, database_name="<DB>", schema_name="<SCHEMA>")
mv = reg.log_model(
    MyCustomModel(model_context),
    model_name="my_model_with_preprocessing",
    version_name="v1",
    conda_dependencies=["<model-framework>", "ray-data"],  # ray-data required for Chain unpickling
    sample_input_data=snowpark_df.drop("LABEL").limit(5),
    target_platforms=["WAREHOUSE", "SNOWPARK_CONTAINER_SERVICES"],
)
```

- `ray-data` in `conda_dependencies` is required to unpickle the Chain at inference, even though no Ray cluster runs
- `map_batches` transforms are not captured by the Chain — replicate them in `predict()`
- Load `../model-registry/SKILL.md` for full `CustomModel` class structure and registry details

---

## Stopping Points

- ✋ Step 1: Confirm preprocessing plan before generating code
- ✋ Step 5: Before training — hand off to distributed-training skill or let user proceed with OSS
- ✋ Step 6: Confirm model name, version, database, schema, and target platforms before logging to registry

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| Column name mismatch (`ValueError`, `KeyError`, `Column 'col' does not exist`) | Preprocessors are case-sensitive and lock in column names at fit time. Snowflake tables default to UPPERCASE; non-UPPERCASE names (e.g. from pandas) become double-quoted identifiers in Snowpark (`"Age"` instead of `AGE`), causing mismatches at inference | Check `pdf.columns` or `ray_ds.schema()` and match column names to the actual data. UPPERCASE column names are the safest default for compatibility across sources |
| Global stats wrong with `map_batches` | `map_batches` is stateless — computes per-batch, not global | Use `ray.data.preprocessors` for anything needing fitted stats |
| `transform_batch()` fails on string columns (CustomModel path) | Arrow-backed `StringDtype`; Ray encoders expect numpy `object` | `df[col] = df[col].astype("object")` for string columns |
| Warehouse OOM with SF ML Preprocessors | High cardinality vocabulary temp tables | Use Ray preprocessors instead |
| `ModuleNotFoundError: No module named 'snowflake.ml.data.preprocessor'` at inference (RayPreprocessorAdapter) | `ext_modules` not passed to `log_model()` | Add `ext_modules=[preprocessor_mod]` where `import snowflake.ml.data.preprocessor as preprocessor_mod` |
| `TypeError: Expected a fitted Chain or a supported Ray preprocessor` (RayPreprocessorAdapter) | Passed an unsupported object to `from_fitted_chain()` | Verify preprocessor is one of the 19 supported types (StandardScaler, MinMaxScaler, SimpleImputer, OrdinalEncoder, OneHotEncoder, etc.) |
| `ValueError: Preprocessor 'X' has not been fitted` (RayPreprocessorAdapter) | Chain or preprocessor wasn't fitted before extraction | Call `chain.fit(ray_ds)` or `chain.fit_transform(ray_ds)` first |
| `_sklearn_estimator` is None after `XGBEstimator.fit(DataConnector)` | The DataConnector fit path doesn't populate `_sklearn_estimator` | Call `estimator._to_sklearn_estimator(y=labels)` manually after fit |

## Next Steps

- **Distributed training** → Load `../distributed-training/estimators/SKILL.md`
- **Model registry details** → Load `../model-registry/SKILL.md`
- **Deploy SPCS service** → Load `../spcs-inference/SKILL.md`
