---
name: feature-store-training
description: "Generate training datasets from Snowflake Feature Store with point-in-time correct feature retrieval, preprocessing, and Model Registry integration."
parent_skill: feature-store
path: machine-learning/feature-store/training
---

# Training Datasets, Preprocessing & Model Registry

## When to Load

Parent skill routes here for TRAINING intent: "training dataset", "generate_dataset", "spine", "point-in-time", "retrieve features", "AsOf join", "backfill", "preprocessing", "encoding", "scaling".

## Prerequisites

- `../references/api-reference.md` loaded
- Feature store (`fs`) initialized with registered entities and feature views

---

## Core Concepts

### Spine
A DataFrame containing entity keys and (optionally) timestamps that define **which entities at which points in time** you need features for. The Feature Store joins features to the spine using AsOf joins for point-in-time correctness.

### Point-in-Time Correctness
When `spine_timestamp_col` is specified, the Feature Store retrieves feature values **as they existed at the spine timestamp** — preventing future data from leaking into training data.

### Transformation Taxonomy (MIT / MDT / ODT)
Before generating training data, classify transforms:
- **MIT** (Model-Independent): In FeatureView — reusable aggregations, joins, derived columns
- **MDT** (Model-Dependent): In Model Registry Pipeline — scaling, encoding, imputation (fit on training only)
- **ODT** (On-Demand): At inference time — time-since-last, distance, current context

---

## Workflow

### Step 1: Identify Feature Views

**List available feature views:**
```python
fs.list_feature_views().select("NAME", "VERSION", "DESC").show()
```

**Ask user:**
```
Which feature view(s) do you want to use for training?
(You can combine features from multiple feature views)
```

**⚠️ STOP**: Wait for user response.

**Retrieve the feature views:**
```python
fv1 = fs.get_feature_view("<FV_NAME_1>", "<VERSION>")
fv2 = fs.get_feature_view("<FV_NAME_2>", "<VERSION>")

# Optional: slice to use only specific features
fv1_slice = fv1.slice(["FEATURE_A", "FEATURE_B"])
```

---

### Step 2: Build the Spine

**Spine structure:**
| Use Case | Spine Columns |
|----------|---------------|
| Training | entity keys + timestamp + label |
| Batch inference | entity keys + timestamp |
| Online inference | entity keys only |

**Ask user:**
```
How would you like to define your training spine?
1. From an existing table (e.g., labeled events table)
2. From a SQL query
3. Build from feature view data (group by entity keys)
4. Manual construction
```

**⚠️ STOP**: Wait for user response.

**Option 1: From existing table**
```python
spine_df = session.table("<SPINE_TABLE>").select(
    "<ENTITY_KEY>",
    "<TIMESTAMP_COL>",
    "<LABEL_COL>",
)
```

**Option 2: From SQL**
```python
spine_df = session.sql("""
    SELECT customer_id, event_timestamp, label
    FROM training_events
    WHERE event_timestamp BETWEEN '2024-01-01' AND '2024-12-31'
""")
```

**Option 3: From feature view data**
```python
import snowflake.snowpark.functions as F

spine_df = fv1.feature_df.group_by("<ENTITY_KEY>").agg(
    F.max("<TIMESTAMP_COL>").alias("ASOF_DATE")
)
```

**Option 4: Manual construction**
```python
spine_df = session.create_dataframe(
    [("1", "3937", "2024-07-01 00:00"), ("2", "2", "2024-07-01 00:00")],
    schema=["INSTANCE_ID", "CUSTOMER_ID", "EVENT_TIMESTAMP"]
)
```

---

### Step 3: Generate Training Dataset

**⚠️ MANDATORY CHECKPOINT**: Present configuration before generating.

```
I will generate a training dataset with:
- Name: <DATASET_NAME>
- Spine: <description of spine>
- Feature views: <list>
- Timestamp column: <col> (for point-in-time correctness)
- Label columns: <cols> (if any)

Approve? (Yes/No/Modify)
```

**Option A: Versioned Dataset (immutable, for reproducible training)**
```python
dataset = fs.generate_dataset(
    name="<DATASET_NAME>",
    version="V01_20250115",
    spine_df=spine_df,
    features=[fv1, fv2],
    spine_timestamp_col="<TIMESTAMP_COL>",
    spine_label_cols=["<LABEL_COL>"],
    desc="Training dataset for <purpose>",
)

training_df = dataset.read.to_pandas()
```

**Option B: Training Set (returns DataFrame directly)**
```python
training_set = fs.generate_training_set(
    spine_df=spine_df,
    features=[
        fv1.slice(["FEATURE_A", "FEATURE_B"]),
        fv2,
    ],
    timestamp_col="<TIMESTAMP_COL>",
    spine_label_cols=["<LABEL>"],
)

training_df = training_set.to_pandas()
```

**Column prefixing** when joining multiple FVs:
- `auto_prefix=True` → columns become `USER_ORDERS_FV__TOTAL_SPEND_7D`
- `.with_name("ord")` → columns become `ord$TOTAL_SPEND_7D` (takes precedence)

**Important parameters:**
- `spine_timestamp_col`: Set whenever features are temporal. Omitting retrieves latest values only.
- `spine_label_cols`: Columns in spine that are labels/targets (excluded from features).
- `exclude_columns`: Columns to exclude from output.
- `include_feature_view_timestamp_col`: Set `True` to include the FV's timestamp in output.
- `output_type`: `"dataset"` (default, immutable) or `"table"` (returns DataFrame).

**⚠️ CRITICAL**: Always define `spine_timestamp_col` for temporal features — without it, PIT retrieval won't work and you risk data leakage.

---

### Step 4: Feature Retrieval for Inference

For batch inference (not training), use `retrieve_feature_values`:

```python
inference_spine = session.create_dataframe(
    [("1",), ("2",), ("3",)],
    schema=["CUSTOMER_ID"]
)

enriched_df = fs.retrieve_feature_values(
    spine_df=inference_spine,
    features=[fv1, fv2],
    spine_timestamp_col="EVENT_TIMESTAMP",
)
enriched_df.show()
```

**Difference from generate_dataset:**
- `generate_dataset` → Creates a persistent, immutable Dataset object (for reproducible training)
- `retrieve_feature_values` → Returns a transient DataFrame (for inference/exploration)

---

### Step 5: Preprocessing & Model Training

**Important:** Preprocessing (scaling, encoding, imputation) is **Model-Dependent (MDT)** — it belongs with the model, NOT in the FeatureView. After generating your training dataset:

- For preprocessing and model training → **Load** `../../ml-development/SKILL.md`
- For logging the trained model to the registry → **Load** `../../model-registry/SKILL.md`

Include feature store provenance in the model comment (e.g., "Trained using CUSTOMER_ORDER_FV V01, TRANSACTION_FV V03").

---

### Step 6: Use the Dataset

**Convert to Snowpark DataFrame:**
```python
training_df = dataset.read.to_snowpark_dataframe()
```

**Convert to Pandas:**
```python
training_pdf = dataset.read.to_pandas()
```

**Check dataset versions:**
```python
dataset.list_versions()
```

**Retrieve feature views used in dataset:**
```python
fvs = fs.load_feature_views_from_dataset(dataset)
```

**Temporal validation** (always validate PIT correctness before training):
```python
assert (training_df["FEATURE_TS"] <= training_df["EVENT_TIMESTAMP"]).all()
```

---

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| Missing `spine_timestamp_col` | Future data leaks into training | Always set for temporal features |
| Spine keys don't match entity join keys | Empty or misaligned results | Ensure spine columns match entity `join_keys` |
| Wrong timestamp column | Features retrieved at wrong point in time | Verify timestamp column exists in both spine and feature view |
| Using `generate_dataset` for inference | Unnecessary persistent storage | Use `retrieve_feature_values` for inference |
| MDT in FeatureView | Training/serving skew | Move scaling/encoding to Model Registry Pipeline |

---

## Stopping Points

- ✋ Step 1: Feature view selection
- ✋ Step 2: Spine definition approach
- ✋ Step 3: Before generating dataset (mandatory approval)

## Output

- Training Dataset object (immutable, versioned) or DataFrame
- Data ready for preprocessing and model training (via ml-development skill)

## Next Skill

- If user wants to train a model → **Load** `../../SKILL.md` (machine-learning parent skill)
- If user wants online serving → **Load** `online/SKILL.md`
- If user wants lineage/inference FV → **Load** `lineage/SKILL.md`
- If user wants to manage, version, or load the Dataset into PyTorch/TensorFlow → **Load** `../../datasets/SKILL.md`
- If user wants to trace lineage from datasets to models → **Load** `../../ml-lineage/SKILL.md`
