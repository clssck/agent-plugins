---
name: ml-lineage
description: "Query and manage ML Lineage in Snowflake. Use when: tracing model training data, finding downstream models, debugging missing lineage, capturing lineage for external models. Triggers: what trained this model, model lineage, dataset lineage, GET_LINEAGE, trace lineage, no lineage showing, lineage not captured, which models use this dataset."
parent_skill: machine-learning
---

# ML Lineage

ML Lineage traces the flow of data through your ML pipeline: from source tables → feature views → datasets → models → services.

## Why ML Lineage Matters

| Question | ML Lineage Answers |
|----------|-------------------|
| "What data trained this model?" | Trace upstream to find source datasets, feature views, tables |
| "What models use this dataset?" | Trace downstream to find dependent models |
| "Is this model safe to update?" | Check what depends on it before changing |
| "Why are predictions different?" | Compare training data between model versions |
| "Compliance audit" | Document full data provenance for regulators |

## Lineage Graph

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Source Table │────▶│ Feature View │────▶│   Dataset    │
│    /View     │     │              │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
                                                 │
                                                 ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│Model Service │◀────│    Model     │◀────│   (Train)    │
│              │     │   Version    │     │              │
└──────────────┘     └──────────────┘     └──────────────┘
```

## Supported Lineage Relationships

| Source → Target | Captured? | How |
|-----------------|-----------|-----|
| Table/View → Feature View | ✅ | Auto on Feature View creation |
| Table/View → Dataset | ✅ | Auto on `create_from_dataframe()` |
| Feature View → Dataset | ✅ | Auto on `fs.generate_dataset()` |
| Dataset → Model | ✅ | Auto when training with Snowpark DataFrame |
| Model → Model Service | ✅ | Auto on service deployment |
| Table/View → Model | ✅ | Via `sample_input_data` in `log_model()` |

## Prerequisites

### Required Privilege

Lineage queries require the VIEW LINEAGE privilege. Before attempting any GRANT, check if the current role already has access by running a lineage query. If it fails with a privilege error, ask the user to have their ACCOUNTADMIN run:

```sql
GRANT VIEW LINEAGE ON ACCOUNT TO ROLE <user_role>;
```

Do not switch to ACCOUNTADMIN yourself.

### Required Package Version

```python
# ML Lineage requires snowflake-ml-python >= 1.6.0
# Check version
from snowflake.ml import version

print(version.VERSION)
```

---

## Querying Lineage

### Method 1: Snowpark ML API (Recommended)

The `.lineage()` method is available on `ModelVersion`, `Dataset`, and `FeatureView` objects.

#### What trained this model?

```python
from snowflake.ml.registry import Registry

registry = Registry(session, database_name="MY_DB", schema_name="MY_SCHEMA")
model = registry.get_model("MY_MODEL")
mv = model.version("v1")

# Get upstream lineage (what data trained this model)
upstream = mv.lineage(direction="upstream")

for node in upstream:
    print(f"{node._lineage_node_domain}: {node._lineage_node_name}")
# Output:
# dataset: MY_DB.MY_SCHEMA.TRAINING_DATASET
# feature_view: MY_DB.FEATURE_STORE.CUSTOMER_FEATURES
# table: MY_DB.RAW.CUSTOMERS
```

#### Which models use this dataset?

```python
from snowflake.ml.dataset import load_dataset

dataset = load_dataset(session, "MY_DB.MY_SCHEMA.TRAINING_DATASET", "v1")

# Get downstream lineage (what models trained on this data)
downstream = dataset.lineage(direction="downstream", domain_filter={"model"})

for node in downstream:
    print(f"Model: {node._lineage_node_name}, Version: {node._lineage_node_version}")
```

#### Which feature views feed this dataset?

```python
# Filter to specific domain (must be a set)
upstream_fvs = dataset.lineage(
    direction="upstream", 
    domain_filter={"feature_view"}
)

for fv in upstream_fvs:
    print(f"Feature View: {fv._lineage_node_name}")
```

### Method 2: Session Lineage API

For more flexible queries across all object types, use `session.lineage.trace()`:

```python
# Trace upstream from a model
result_df = session.lineage.trace(
    "MY_DB.MY_SCHEMA.MY_MODEL",  # Fully qualified name
    "MODEL",                     # Domain (UPPERCASE)
    object_version="v1",         # Optional for versioned objects
    direction="upstream",        # or "downstream" or "both"
    distance=3                   # How many hops to trace
)

result_df.show()
```

**Key differences from `.lineage()` method:**
- Supports `direction="both"` to trace in both directions
- Supports variable `distance` (number of hops)
- Returns a Snowpark DataFrame with lineage edges
- Domain names must be UPPERCASE ("MODEL", "DATASET", "FEATURE_VIEW", "TABLE", "VIEW")

### Method 3: SQL API

```sql
-- Get upstream lineage for a model (with version)
SELECT * FROM TABLE(
    SNOWFLAKE.CORE.GET_LINEAGE(
        'MY_DB.MY_SCHEMA.MY_MODEL',
        'MODEL',
        'upstream',
        3,
        'v1'
    )
);

-- Get downstream lineage for a dataset
SELECT * FROM TABLE(
    SNOWFLAKE.CORE.GET_LINEAGE(
        'MY_DB.MY_SCHEMA.MY_TRAINING_DATASET',
        'DATASET',
        'downstream'
    )
);
```

> **Tip:** Lineage can also be explored visually in Snowsight under **AI & ML → Models** (or Datasets, Feature Store) → select the object → **Lineage** tab. Mention this to the user if they want a visual exploration option.

---

## Ensuring Lineage is Captured

### Automatic Lineage Capture

Lineage is captured automatically when you use Snowflake ML APIs correctly:

```python
# ✅ GOOD: Full lineage chain captured automatically

# 1. Create Dataset from table
from snowflake.ml.dataset import create_from_dataframe
df = session.table("MY_DB.RAW.TRAINING_DATA")
dataset = create_from_dataframe(session, "TRAINING_DATASET", "v1", df)
# Lineage: RAW.TRAINING_DATA → TRAINING_DATASET ✅

# 2. Train with Snowpark DataFrame from Dataset
training_df = dataset.read.to_snowpark_dataframe()
model = MyModel()
model.fit(training_df)

# 3. Log model to registry
from snowflake.ml.registry import Registry
registry = Registry(session, database_name="MY_DB", schema_name="MY_SCHEMA")
mv = registry.log_model(model, model_name="MY_MODEL", version_name="v1")
# Lineage: TRAINING_DATASET → MY_MODEL ✅
```

### When Lineage is NOT Captured

```python
# ❌ BAD: No lineage - trained from pandas without sample_input_data
pandas_df = dataset.read.to_pandas()
model.fit(pandas_df)
registry.log_model(model, model_name="MY_MODEL", version_name="v1")
# No lineage captured! ❌
```

### Manual Lineage Capture

For models trained outside Snowpark (pandas, external training), use `sample_input_data`:

```python
# ✅ FIX: Pass sample_input_data to capture lineage

# Training happened with pandas or externally
pandas_df = dataset.read.to_pandas()
model.fit(pandas_df)

# Create a Snowpark DataFrame pointing to the source
source_df = session.table("MY_DB.RAW.TRAINING_DATA")
# Or: source_df = dataset.read.to_snowpark_dataframe()

# Log with sample_input_data
mv = registry.log_model(
    model,
    model_name="MY_MODEL",
    version_name="v1",
    sample_input_data=source_df  # ✅ Captures lineage!
)
```

### External Model Lineage

For models trained completely outside Snowflake:

```python
import joblib

# Load externally trained model
external_model = joblib.load("model.pkl")

# Create DataFrame pointing to the training data source
training_source_df = session.table("MY_DB.STAGING.EXTERNAL_TRAINING_DATA")

# Log with lineage
mv = registry.log_model(
    external_model,
    model_name="EXTERNAL_MODEL",
    version_name="v1",
    sample_input_data=training_source_df,  # Links to source
    conda_dependencies=["scikit-learn"]
)
```

---

## Debugging Missing Lineage

### Problem: "Lineage tab is empty"

**Check 1: Object was created after ML Lineage was enabled**
```python
# Lineage only exists for objects created AFTER feature enablement
# Objects created before won't have lineage retroactively added
```

**Check 2: Verify you have VIEW LINEAGE privilege**
```sql
SHOW GRANTS TO ROLE my_role;
-- Look for: VIEW LINEAGE ON ACCOUNT
```

**Check 3: Verify lineage exists via SQL**
```sql
SELECT * FROM TABLE(
    SNOWFLAKE.CORE.GET_LINEAGE(
        'MY_DB.MY_SCHEMA.MY_MODEL',
        'MODEL',
        'upstream'
    )
);
-- If empty, lineage was never captured
```

### Problem: "Model shows no upstream data"

**Cause**: Model was trained from pandas/external data without `sample_input_data`

**Fix**: Re-log the model with `sample_input_data`:
```python
# Cannot add lineage to existing model version
# Must create new version with proper lineage

source_df = session.table("ORIGINAL_TRAINING_DATA")
mv = registry.log_model(
    model,
    model_name="MY_MODEL",
    version_name="v2_with_lineage",  # New version
    sample_input_data=source_df
)
```

### Problem: "Dataset → Model lineage missing"

**Cause**: Trained from `dataset.read.to_pandas()` instead of `to_snowpark_dataframe()`

**Fix**: Use Snowpark DataFrame for training:
```python
# ❌ This loses lineage
pandas_df = dataset.read.to_pandas()
model.fit(pandas_df)

# ✅ This preserves lineage
snowpark_df = dataset.read.to_snowpark_dataframe()
model.fit(snowpark_df)
```

### Problem: "Feature View → Dataset lineage missing"

**Cause**: Used `generate_training_set()` instead of `generate_dataset()`

```python
# ❌ generate_training_set returns DataFrame - no Dataset lineage
training_df = fs.generate_training_set(spine_df, features, ...)

# ✅ generate_dataset creates Dataset with full lineage
dataset = fs.generate_dataset(
    name="TRAINING_DATA",
    spine_df=spine_df,
    features=features,
    ...
)
```

---

## Common Lineage Queries

### Compare Training Data Between Model Versions

```python
model = registry.get_model("MY_MODEL")
v1 = model.version("v1")
v2 = model.version("v2")

# Get upstream datasets (domain_filter must be a set)
v1_data = v1.lineage(direction="upstream", domain_filter={"dataset"})
v2_data = v2.lineage(direction="upstream", domain_filter={"dataset"})

print(f"V1 trained on: {[d._lineage_node_name for d in v1_data]}")
print(f"V2 trained on: {[d._lineage_node_name for d in v2_data]}")
```

### Find All Models Trained on Sensitive Data

```sql
-- Find models that trace back to a sensitive table
SELECT DISTINCT 
    l.target_object_name AS model_name,
    l.target_object_version AS model_version
FROM TABLE(
    SNOWFLAKE.CORE.GET_LINEAGE(
        'MY_DB.PII.CUSTOMER_DATA',
        'TABLE',
        'downstream',
        5
    )
) l
WHERE l.target_object_domain = 'MODEL';
```

### Audit Trail for a Model

```python
def get_full_lineage_audit(model_version):
    """Get complete upstream lineage for compliance audit."""
    
    audit = {
        "model": model_version.fully_qualified_name,
        "version": model_version.version_name,
        "datasets": [],
        "feature_views": [],
        "source_tables": []
    }
    
    upstream = model_version.lineage(direction="upstream")
    
    for node in upstream:
        if node._lineage_node_domain == "dataset":
            audit["datasets"].append(node._lineage_node_name)
        elif node._lineage_node_domain == "feature_view":
            audit["feature_views"].append(node._lineage_node_name)
        elif node._lineage_node_domain in ["table", "view"]:
            audit["source_tables"].append(node._lineage_node_name)
    
    return audit

# Usage
audit = get_full_lineage_audit(mv)
print(audit)
```

### Impact Analysis Before Changing a Table

```python
def analyze_impact(session, table_name):
    """Find all ML artifacts that depend on a table."""
    
    downstream = session.lineage.trace(
        table_name,
        "TABLE",
        direction="downstream",
        distance=5
    )
    
    # Group by domain
    impacts = downstream.group_by("TARGET_OBJECT_DOMAIN").count()
    impacts.show()
    
    return downstream

# Before changing RAW.CUSTOMERS
impact_df = analyze_impact(session, "MY_DB.RAW.CUSTOMERS")
```

---

## Best Practices

### 1. Always Use Datasets for Training Data

```python
# ✅ Creates versioned, lineage-tracked training data
dataset = create_from_dataframe(session, "TRAINING_DATA", "v1", df)

# ❌ No versioning, no lineage
df.write.save_as_table("TRAINING_DATA")
```

### 2. Train from Snowpark DataFrames When Possible

```python
# ✅ Lineage captured automatically
training_df = dataset.read.to_snowpark_dataframe()
model.fit(training_df)

# ⚠️ Must use sample_input_data to capture lineage
pandas_df = dataset.read.to_pandas()
model.fit(pandas_df)
registry.log_model(model, sample_input_data=training_df, ...)
```

### 3. Use generate_dataset() for Feature Store

```python
# ✅ Full Feature View → Dataset lineage
dataset = fs.generate_dataset(name="DATA", ...)

# ⚠️ No Dataset object, lineage only to resulting table
df = fs.generate_training_set(...)
```

### 4. Document Lineage for Compliance

```python
# Add comments to datasets
dataset = create_from_dataframe(
    session, "TRAINING_DATA", "v1", df,
    comment="PII data included. Approved by compliance team on 2024-01-15."
)

# Add metadata to models
mv = registry.log_model(
    model,
    model_name="MY_MODEL",
    version_name="v1",
    metadata={
        "training_date": "2024-01-20",
        "approved_by": "data_governance_team",
        "pii_handling": "anonymized"
    }
)
```

---

## Stopping Points

- ✋ If lineage is empty: Check privileges and object creation date
- ✋ Before deleting upstream data: Run impact analysis first
- ✋ For compliance audits: Document full lineage chain before proceeding

## Output

- Lineage graph showing data flow
- List of upstream/downstream dependencies
- Impact analysis for proposed changes

## Related Skills

- `../datasets/SKILL.md` - Create and manage versioned datasets
- `../model-registry/SKILL.md` - Register models with lineage
- `../../data-governance/lineage/SKILL.md` - General data lineage (non-ML)
