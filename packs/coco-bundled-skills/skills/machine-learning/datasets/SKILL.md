---
name: datasets
description: "Snowflake Datasets for ML workflows. Use when: creating versioned datasets, listing datasets, loading data into PyTorch/TensorFlow, DataConnector, dataset management. Triggers: create dataset, version dataset, list datasets, load dataset, DataConnector, to_tf_dataset, to_torch_dataset, snow://dataset, SHOW DATASETS."
parent_skill: machine-learning
---

# Snowflake Datasets

Datasets are schema-level objects designed for machine learning workflows. They provide immutable, versioned snapshots of data with efficient access for distributed training.

## When to Use Datasets

| Use Case | Why Dataset? |
|----------|--------------|
| **Reproducible training** | Immutable snapshots ensure same data across runs |
| **Version control** | Track which data version trained which model |
| **ML Lineage** | Automatic lineage tracking to models and feature views |
| **Framework integration** | Native connectors for PyTorch, TensorFlow, Snowpark ML |
| **Large-scale training** | Efficient file-based access for distributed training |

**When NOT to use Datasets:**
- One-off analysis (just use DataFrames)
- Data that changes frequently (use tables/views)
- Small datasets where versioning isn't needed

## Core Concepts

A Dataset is a schema-level object that contains multiple immutable versions. Each version is stored as Parquet files. Versions are append-only — you create new versions but never modify existing ones.

- **Dataset**: Named container for versioned data snapshots
- **DatasetVersion**: Immutable point-in-time snapshot stored as Parquet files
- **DataConnector**: Efficient loader for training frameworks

## Step 1: Create a Dataset

### From a Snowpark DataFrame

```python
from snowflake.ml.dataset import create_from_dataframe

# Create DataFrame from any source
df = session.table("MY_DB.MY_SCHEMA.TRAINING_DATA")
# Or: df = session.sql("SELECT * FROM ...")

# Create Dataset with initial version
dataset = create_from_dataframe(
    session=session,
    name="MY_TRAINING_DATASET",      # Dataset name
    version="v1",                     # Version name
    input_dataframe=df,
    comment="Initial training data for churn model"  # Optional
)

print(f"Created: {dataset.fully_qualified_name}")
# Output: MY_DB.MY_SCHEMA.MY_TRAINING_DATASET
```

### From Feature Store (Recommended for ML)

```python
from snowflake.ml.feature_store import FeatureStore, CreationMode

fs = FeatureStore(
    session=session,
    database="MY_DB",
    name="MY_FEATURE_STORE",
    default_warehouse="MY_WH",
    creation_mode=CreationMode.FAIL_IF_NOT_EXIST
)

# Get feature views
customer_fv = fs.get_feature_view("CUSTOMER_FEATURES", "V1")

# Generate Dataset with point-in-time correctness
dataset = fs.generate_dataset(
    name="CHURN_TRAINING_DATA",
    spine_df=spine_df,
    features=[customer_fv],
    version="v1",
    spine_timestamp_col="EVENT_TIMESTAMP",
    desc="Q1 2024 training data"
)
```

**⚠️ Feature Store datasets automatically capture lineage** to source feature views.

## Step 2: Load an Existing Dataset

```python
from snowflake.ml.dataset import load_dataset

# Load specific version of dataset
dataset = load_dataset(
    session=session,
    name="MY_DB.MY_SCHEMA.MY_TRAINING_DATASET",
    version="v1"  # Version is required
)

# Check selected version
print(dataset.selected_version.name)  # "v1"
print(dataset.selected_version.created_on)  # Creation timestamp
```

**Alternative: Load then select version**
```python
from snowflake.ml.dataset import Dataset

# Load dataset without version, then select
dataset = Dataset.load(session, "MY_DB.MY_SCHEMA.MY_TRAINING_DATASET")
print(dataset.list_versions())  # ["v1", "v2", "v3"]
dataset = dataset.select_version("v1")
```

## Step 3: Work with Versions

### List Versions

```python
# Python
versions = dataset.list_versions()
print(versions)  # ["v1", "v2", "v3"]
```

```sql
-- SQL
SHOW VERSIONS IN DATASET MY_DB.MY_SCHEMA.MY_TRAINING_DATASET;
```

### Create a New Version

```python
# Add new data as a new version
new_df = session.table("UPDATED_TRAINING_DATA")
dataset_v2 = dataset.create_version("v2", input_dataframe=new_df)

print(dataset_v2.selected_version.name)  # "v2"
```

**With additional options:**
```python
dataset_v2 = dataset.create_version(
    version="v2",
    input_dataframe=new_df,
    shuffle=True,                    # Shuffle data globally
    label_cols=["TARGET"],           # Mark label columns
    exclude_cols=["TIMESTAMP"],      # Exclude from training
    comment="Added new customers"
)
```

### Switch Between Versions

```python
# select_version returns a NEW Dataset object (immutable)
dataset_v1 = dataset.select_version("v1")
dataset_v2 = dataset.select_version("v2")

# Original dataset unchanged
print(dataset.selected_version.name)  # Still "v1" if that was selected
```

## Step 4: Read Data from Dataset

### To Snowpark DataFrame

```python
# Convert to Snowpark DataFrame
df = dataset.read.to_snowpark_dataframe()

# Use for Snowpark ML training
from snowflake.ml.modeling.ensemble import RandomForestClassifier
model = RandomForestClassifier(...)
model.fit(df)
```

### To Pandas DataFrame

```python
# For small datasets or local analysis
pandas_df = dataset.read.to_pandas()

# With row limit
pandas_df = dataset.read.to_pandas(limit=10000)
```

### To PyTorch Dataset

```python
import torch

# Stream data in batches for PyTorch training
torch_dataset = dataset.read.to_torch_dataset(batch_size=32)

for batch in torch_dataset:
    input_tensor = torch.stack([torch.from_numpy(v) for v in batch.values()], dim=-1)
    # Training loop...
```

**Note:** `to_torch_datapipe()` is deprecated. Use `to_torch_dataset()` instead.

### To TensorFlow Dataset

```python
import tensorflow as tf

# Stream data in batches for TensorFlow training
tf_dataset = dataset.read.to_tf_dataset(batch_size=32)

for batch in tf_dataset:
    input_tensor = tf.stack(list(batch.values()), axis=-1)
    # Training loop...
```

### Using DataConnector (Recommended for ML Jobs)

```python
from snowflake.ml.data import DataConnector

# Create connector from Dataset
connector = DataConnector.from_dataset(dataset)

# Or from DataFrame directly
connector = DataConnector.from_dataframe(df)

# Or from SQL
connector = DataConnector.from_sql("SELECT * FROM my_table", session=session)

# PyTorch (recommended)
torch_dataset = connector.to_torch_dataset(batch_size=64, shuffle=True, drop_last_batch=True)

# TensorFlow
tf_dataset = connector.to_tf_dataset(batch_size=64, shuffle=True, drop_last_batch=True)

# Pandas
pandas_df = connector.to_pandas(limit=10000)

# Ray (for distributed processing)
ray_dataset = connector.to_ray_dataset()

# HuggingFace
hf_dataset = connector.to_huggingface_dataset()  # In-memory
hf_dataset = connector.to_huggingface_dataset(streaming=True, batch_size=1024)  # Streaming
```

## Step 5: List and Manage Datasets

### List All Datasets

```sql
-- All datasets in current schema
SHOW DATASETS;

-- Filter by pattern
SHOW DATASETS LIKE 'TRAINING%';

-- In specific schema
SHOW DATASETS IN SCHEMA MY_DB.ML_SCHEMA;

-- In database
SHOW DATASETS IN DATABASE MY_DB;
```

### Delete a Dataset Version

```python
# Python
dataset.delete_version("v1")
```

```sql
-- SQL
ALTER DATASET MY_TRAINING_DATASET DROP VERSION v1;
```

### Delete a Dataset

```sql
DROP DATASET MY_TRAINING_DATASET;
```

## SQL Access to Dataset Files

Datasets store data as Parquet files accessible via `snow://dataset/` URLs.

### List Files

```sql
LIST 'snow://dataset/MY_TRAINING_DATASET/versions/v1';
```

### Infer Schema

```sql
CREATE FILE FORMAT IF NOT EXISTS my_parquet_format TYPE = PARQUET;

SELECT * FROM TABLE(
    INFER_SCHEMA(
        LOCATION => 'snow://dataset/MY_TRAINING_DATASET/versions/v1',
        FILE_FORMAT => 'my_parquet_format'
    )
);
```

### Query Directly

```sql
SELECT $1 
FROM 'snow://dataset/MY_TRAINING_DATASET/versions/v1' 
    (FILE_FORMAT => 'my_parquet_format', PATTERN => '.*data.*') t;
```

## ML Lineage Integration

Datasets automatically capture lineage when created properly:

```python
# ✅ Lineage captured: Dataset → Model
dataset = create_from_dataframe(session, "TRAINING_DATA", "v1", df)
df_for_training = dataset.read.to_snowpark_dataframe()
model.fit(df_for_training)
registry.log_model(model, ...)  # Lineage: TRAINING_DATA → MODEL

# ✅ Lineage captured: FeatureView → Dataset → Model  
dataset = fs.generate_dataset(...)  # FeatureView lineage captured
df_for_training = dataset.read.to_snowpark_dataframe()
model.fit(df_for_training)
registry.log_model(model, ...)  # Full lineage chain

# ❌ No lineage: Training from pandas without sample_input_data
pandas_df = dataset.read.to_pandas()
model.fit(pandas_df)
registry.log_model(model, ...)  # No lineage!

# ✅ Fix: Pass sample_input_data to capture lineage
registry.log_model(
    model, 
    sample_input_data=dataset.read.to_snowpark_dataframe()
)
```

**See `ml-lineage/SKILL.md`** for detailed lineage querying and debugging.

## Required Privileges

| Action | Privilege | Object |
|--------|-----------|--------|
| Create Dataset | `CREATE DATASET` | Schema |
| Read Dataset | `USAGE` | Dataset |
| Modify Dataset | `OWNERSHIP` | Dataset |
| View Lineage | `VIEW LINEAGE` | Account |

```sql
-- Grant dataset creation
GRANT CREATE DATASET ON SCHEMA MY_DB.MY_SCHEMA TO ROLE data_scientist;

-- Grant read access
GRANT USAGE ON DATASET MY_DB.MY_SCHEMA.MY_TRAINING_DATASET TO ROLE analyst;

-- Grant lineage viewing
GRANT VIEW LINEAGE ON ACCOUNT TO ROLE data_scientist;
```

## Best Practices

### 1. Use Datasets for Training Data (Not Tables)

```python
# ❌ BAD: Save to table (no versioning, no lineage)
df.write.save_as_table("TRAINING_DATA")

# ✅ GOOD: Create Dataset (versioned, lineage-tracked)
dataset = create_from_dataframe(session, "TRAINING_DATA", "v1", df)
```

### 2. Version Meaningfully

```python
# Use descriptive version names
dataset.create_version("2024_q1_refresh", new_df)
dataset.create_version("added_new_features", new_df)
dataset.create_version("fixed_null_handling", new_df)
```

### 3. Use Feature Store for Point-in-Time Data

```python
# For training datasets with temporal features, use Feature Store
dataset = fs.generate_dataset(
    name="TRAINING_DATA",
    spine_df=spine_df,
    features=[feature_views],
    spine_timestamp_col="EVENT_TS"  # Point-in-time correctness
)
```

### 4. Document Your Datasets

```python
dataset = create_from_dataframe(
    session, 
    "TRAINING_DATA", 
    "v1", 
    df,
    comment="Churn prediction training data. Features: demographics, usage, billing."
)
```

## Common Issues

### "Dataset not found"

```python
from snowflake.ml.dataset import Dataset, load_dataset

# Use fully qualified name with version
dataset = load_dataset(session, "MY_DB.MY_SCHEMA.MY_DATASET", "v1")

# Or load without version first, then select
dataset = Dataset.load(session, "MY_DB.MY_SCHEMA.MY_DATASET")
dataset = dataset.select_version("v1")

# Or set context first
session.use_database("MY_DB")
session.use_schema("MY_SCHEMA")
dataset = load_dataset(session, "MY_DATASET", "v1")
```

### "Insufficient privileges"

```sql
-- Check current grants
SHOW GRANTS ON DATASET MY_DB.MY_SCHEMA.MY_DATASET;

-- Grant USAGE for read access
GRANT USAGE ON DATASET MY_DB.MY_SCHEMA.MY_DATASET TO ROLE my_role;
```

### Dataset Not Appearing in Snowsight

Datasets don't appear in the Snowsight database object explorer. Use:
- `SHOW DATASETS` SQL command
- Python `load_dataset()` API
- Lineage tab on Model Registry objects

## Stopping Points

- ✋ Before creating: Confirm database/schema location
- ✋ Before deleting: Confirm no models depend on this dataset (check lineage)

## Output

- Created/loaded Dataset object
- Data accessible via DataConnector or framework-specific loaders
- Automatic lineage tracking when used with Model Registry

## Next Steps

- `../ml-lineage/SKILL.md` - Query lineage relationships
- `../model-registry/SKILL.md` - Register trained models
- `../distributed-training/SKILL.md` - Use Datasets with distributed training (XGBEstimator, Tuner)
