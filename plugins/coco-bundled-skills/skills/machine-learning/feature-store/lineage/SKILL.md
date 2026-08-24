---
name: feature-store-lineage
description: "Feature lineage analysis (which models consume which features) and creating inference feature views from model signatures."
parent_skill: feature-store
path: machine-learning/feature-store/lineage
---

# Feature Lineage & Inference Feature Views

## When to Load

Parent skill routes here for LINEAGE intent: "feature lineage", "which models use", "model consumers", "impact analysis", "inference feature view", "model inference", "serve features", "inference FV", "create inference view", "batch inference features", "model input features".

## Prerequisites

- `../references/api-reference.md` loaded
- Feature store (`fs`) initialized with registered feature views
- Model Registry access for lineage and inference FV creation

---

## Part A: Feature Lineage

### Purpose

Answer: **"Which models consume features from a given feature view?"**

This enables impact analysis before modifying a feature view — you can determine which models would be affected.

### Step 1: Identify the Feature View to Analyze

**Ask user:**
```
Which feature view do you want to analyze for model consumers?
(I'll check all models in the registry that use features from this view)
```

**⚠️ STOP**: Wait for user response.

```python
fv = fs.get_feature_view("<FV_NAME>", "<VERSION>")
fv_features = [str(f) for f in fv.feature_descs] if fv.feature_descs else fv.feature_names
```

### Step 2: Scan Model Registry

Enumerate all models and check their input signatures against feature view columns:

```python
from snowflake.ml.registry import Registry

registry = Registry(session=session)

def get_model_input_features(registry, model_name, version_name):
    """Extract input feature names from a model version's signature."""
    model = registry.get_model(model_name)
    mv = model.version(version_name)
    functions = mv.show_functions()
    input_features = set()
    for func_info in functions:
        sig = func_info['signature']
        for feat in sig.inputs:
            input_features.add(feat.name.upper())
    return input_features

# List all models
models_df = session.sql("SHOW MODELS IN SCHEMA <DATABASE>.<SCHEMA>").collect()

results = []
for row in models_df:
    model_name = row['name']
    versions_df = session.sql(f"SHOW VERSIONS IN MODEL {model_name}").collect()
    for ver_row in versions_df:
        version_name = ver_row['name']
        try:
            model_features = get_model_input_features(registry, model_name, version_name)
            fv_feature_set = set(f.upper() for f in fv_features)
            overlap = fv_feature_set & model_features
            coverage = len(overlap) / len(model_features) if model_features else 0
            if coverage > 0:
                results.append({
                    'model': model_name,
                    'version': version_name,
                    'coverage': f"{coverage:.0%}",
                    'matched_features': len(overlap),
                    'total_model_features': len(model_features),
                })
        except Exception:
            pass

# Display results
for r in results:
    print(f"  {r['model']} {r['version']}: {r['coverage']} coverage "
          f"({r['matched_features']}/{r['total_model_features']} features)")
```

**Coverage interpretation:**
| Coverage | Meaning | Impact Level |
|----------|---------|-------------|
| 100% | Model fully depends on this FV | **Critical** — model will break |
| 50-99% | Significant consumer | **High** — model performance will degrade |
| 1-49% | Partial consumer | **Medium** — some features affected |
| 0% | Not a consumer | **None** |

### Step 3: Feature-Level Reverse Lookup

For a specific feature column, find all models that consume it:

```python
def feature_consumers(registry, session, feature_name, model_schema):
    """Find all models that consume a specific feature."""
    models_df = session.sql(f"SHOW MODELS IN SCHEMA {model_schema}").collect()
    consumers = []
    for row in models_df:
        model_name = row['name']
        versions_df = session.sql(f"SHOW VERSIONS IN MODEL {model_name}").collect()
        for ver_row in versions_df:
            version_name = ver_row['name']
            try:
                model_features = get_model_input_features(registry, model_name, version_name)
                if feature_name.upper() in model_features:
                    consumers.append(f"{model_name} {version_name}")
            except Exception:
                pass
    return consumers

consumers = feature_consumers(registry, session, "CREDITSCORE", "<DATABASE>.<SCHEMA>")
print(f"Models consuming CREDITSCORE: {consumers}")
```

### Step 4: Lineage via Model Registry API

For models that were registered with feature store metadata, use the built-in lineage API:

```python
model = registry.get_model("<MODEL_NAME>")
mv = model.version("<VERSION>")

# Get upstream feature views
upstream_fvs = mv.lineage(direction='upstream', domain_filter={'feature_view'})
for fv_ref in upstream_fvs:
    print(f"Upstream FV: {fv_ref}")
```

> **Note:** `lineage()` only works if the model was logged with feature store integration. For models registered without FS metadata, use the signature-based scan from Step 2.

---

## Part B: Create Inference Feature View from Model Signature

### Purpose

Given a trained model, create a feature view that provides exactly the features the model needs for inference — enabling automated batch or online inference pipelines.

### Step 5: Extract Model Input Features

```python
model = registry.get_model("<MODEL_NAME>")
mv = model.version("<VERSION>")

functions = mv.show_functions()
predict_func = next(f for f in functions if f['name'] == 'PREDICT')
input_features = [feat.name for feat in predict_func['signature'].inputs]
print(f"Model requires {len(input_features)} features: {input_features}")
```

### Step 6: Map Features to Source Feature Views

**Approach A: Lineage-based (preferred)**
```python
upstream_fvs = mv.lineage(direction='upstream', domain_filter={'feature_view'})
```

**Approach B: Name-matching fallback**
```python
all_fvs = fs.list_feature_views().to_pandas()
feature_to_fv = {}
for _, row in all_fvs.iterrows():
    fv = fs.get_feature_view(row['NAME'], row['VERSION'])
    for feat_name in fv.feature_names:
        if feat_name.upper() in [f.upper() for f in input_features]:
            feature_to_fv[feat_name.upper()] = (row['NAME'], row['VERSION'])

# Check coverage
mapped = set(feature_to_fv.keys())
unmapped = set(f.upper() for f in input_features) - mapped
print(f"Mapped: {len(mapped)}/{len(input_features)}")
if unmapped:
    print(f"Unmapped (ODT candidates): {unmapped}")
```

**⚠️ STOP**: If unmapped features exist, ask user to classify them:
```
The following model input features were not found in any feature view:
<unmapped list>

These are likely:
1. On-Demand Transforms (ODT) — computed at inference time
2. Columns from a feature view not yet registered
3. Preprocessing outputs (MDT) — handled by the model pipeline

Please classify each unmapped feature.
```

### Step 7: Choose Inference Approach

**Ask user:**
```
How would you like to serve inference features?

1. Slice-based (recommended): Use fv.slice() + retrieve_feature_values()
   - No new FV created
   - Flexible, works for batch and online
   - Features come directly from source FVs

2. Materialized: Create a dedicated inference FV backed by a Dynamic Table
   - Joins source FV Dynamic Tables
   - Single-table access for production serving
   - Additional storage and compute cost
```

**⚠️ STOP**: Wait for user response.

### Step 8A: Slice-Based Inference (No New FV)

```python
# Get source feature views
fv1 = fs.get_feature_view("<SOURCE_FV_1>", "<VERSION>")
fv2 = fs.get_feature_view("<SOURCE_FV_2>", "<VERSION>")

# Build inference spine
inference_spine = session.create_dataframe(
    entity_keys,
    schema=["<ENTITY_KEY>"]
)

# Retrieve features from multiple FVs
inference_features = fs.retrieve_feature_values(
    spine_df=inference_spine,
    features=[
        fv1.slice(["FEATURE_A", "FEATURE_B"]),
        fv2.slice(["FEATURE_C", "FEATURE_D"]),
    ],
    spine_timestamp_col="<TIMESTAMP>" if needed else None,
)

# Run model
predictions = mv.run(inference_features, function_name="predict")
predictions.show()
```

### Step 8B: Materialized Inference FV

```python
# Build SQL joining source FV Dynamic Tables
source_fv_1_dt = f"<DATABASE>.<SCHEMA>.\"<FV_1_NAME>$<VERSION>\""
source_fv_2_dt = f"<DATABASE>.<SCHEMA>.\"<FV_2_NAME>$<VERSION>\""

inference_sql = f"""
    SELECT
        a.<ENTITY_KEY>,
        a.FEATURE_A, a.FEATURE_B,
        b.FEATURE_C, b.FEATURE_D
    FROM {source_fv_1_dt} a
    INNER JOIN {source_fv_2_dt} b
        ON a.<ENTITY_KEY> = b.<ENTITY_KEY>
"""

inference_df = session.sql(inference_sql)

inference_fv = FeatureView(
    name="<MODEL>_INFERENCE_FV",
    entities=[entity],
    feature_df=inference_df,
    refresh_freq="1 day",
    desc=f"Inference features for <MODEL_NAME>. Sources: <FV_1>, <FV_2>",
)

inference_fv = inference_fv.attach_feature_desc({
    "FEATURE_A": "From <FV_1>: <description>",
    "FEATURE_B": "From <FV_1>: <description>",
    "FEATURE_C": "From <FV_2>: <description>",
    "FEATURE_D": "From <FV_2>: <description>",
})
```

**⚠️ MANDATORY CHECKPOINT**: Present the inference FV configuration before registering.

```
I will register this inference feature view:
- Name: <MODEL>_INFERENCE_FV V01
- Entity: <ENTITY_NAME>
- Sources: <list of source FVs>
- Features: <count> features covering <coverage>% of model signature
- Refresh: <FREQ>
- Unmapped (ODT): <list or "none">

Approve? (Yes/No/Modify)
```

```python
registered_inference_fv = fs.register_feature_view(
    feature_view=inference_fv,
    version="V01",
    block=True,
)
```

> **RBAC Note:** The inference FV's Dynamic Table must be owned by the same role that owns the source DTs, or SELECT must be granted. Otherwise, DT refresh will fail with "not authorized".

### Step 9: Validate Inference FV

Run the inference FV checklist (I1–I6 from `monitor/SKILL.md`):

| # | Check | How to Verify |
|---|-------|---------------|
| I1 | Model signature coverage | Compare FV features against `mv.show_functions()` inputs |
| I2 | Source FV lineage documented | Check `desc` includes source FV names |
| I3 | ODT features identified | Unmapped features listed and classified |
| I4 | Preprocessing passthrough | If model has MDT, FV provides raw columns (not scaled/encoded) |
| I5 | Entity key alignment | Inference FV entity keys match all source FVs |
| I6 | Refresh frequency | Inference FV refresh ≥ fastest source FV |

```python
# I1: Signature coverage check
model_inputs = set(f.name.upper() for f in predict_func['signature'].inputs)
fv_features = set(f.upper() for f in registered_inference_fv.feature_names)
coverage = len(model_inputs & fv_features) / len(model_inputs)
print(f"I1 - Signature coverage: {coverage:.0%}")
assert coverage >= 0.9, f"Low coverage: {coverage:.0%}"
```

### Step 10: End-to-End Test

```python
# Build a small test spine
test_spine = session.sql(f"""
    SELECT DISTINCT <ENTITY_KEY>
    FROM <SOURCE_TABLE>
    LIMIT 5
""")

# Retrieve inference features
test_features = fs.retrieve_feature_values(
    spine_df=test_spine,
    features=[registered_inference_fv],
)

# Run model prediction
test_predictions = mv.run(test_features, function_name="predict")
test_predictions.show()
```

---

## Stopping Points

- ✋ Step 1: Feature view selection for lineage analysis
- ✋ Step 6: Classification of unmapped features
- ✋ Step 7: Inference approach selection
- ✋ Step 8B: Before registering materialized inference FV (mandatory approval)

## Output

**Part A:**
- Model consumer report for the analyzed feature view
- Feature-level reverse lookup results
- Impact assessment for planned changes

**Part B:**
- Inference feature view (slice-based or materialized)
- Validation report (I1–I6)
- End-to-end test confirming predictions work

## Next Skill

- If user wants to enable online serving for inference → **Load** `online/SKILL.md`
- If user wants to audit/validate → **Load** `monitor/SKILL.md`
- If user wants batch inference pipeline → **Load** `pipelines/SKILL.md`
