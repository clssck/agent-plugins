---
name: feature-store
description: "**[REQUIRED]** Use for **ALL** Snowflake Feature Store operations: creating feature stores, registering entities/features, building feature views, feature pipelines, training dataset generation, online feature serving, preprocessing, inference feature views, feature lineage, auditing, monitoring, migration from other platforms, and CI/CD promotion. DO NOT attempt feature store work manually - invoke this skill first. Triggers: feature store, feature view, entity, feature pipeline, spine, point-in-time, online features, feature engineering, generate_dataset, retrieve_feature_values, FeatureStore, FeatureView, Entity, CreationMode, snowflake.ml.feature_store, feature freshness, feature serving, feature reuse, training/serving skew, audit feature view, validate features, feature lineage, which models use, inference feature view, model inference, preprocessing, aggregation API, promote features, migrate feature store, temporal features."
path: machine-learning/feature-store
---

# Snowflake Feature Store

Expert guidance for the full Snowflake Feature Store lifecycle: creating entities and feature views, building feature pipelines, generating training datasets with point-in-time correctness, enabling online serving, monitoring operations, tracing feature lineage, creating inference pipelines, and migrating from other platforms.

## When to Use

Use this skill when users ask about:
- Creating a feature store, entities, or feature views
- Building feature pipelines (managed or external)
- Generating training datasets with point-in-time correct feature retrieval
- Enabling and using online (low-latency) feature serving
- Feature transformation patterns (windowed aggregations, per-group, lag features)
- Using the Aggregation API (Feature class) for tiled time-windowed features
- Deriving temporal features from date/timestamp columns
- Preprocessing and encoding (MDT transforms)
- Monitoring feature freshness, pipeline health, or costs
- Auditing and validating feature views against best practices
- Tracing feature lineage — which models consume a feature view
- Creating inference feature views from model signatures
- Promoting features across environments (DEV → TEST → PROD)
- Migrating from Feast, Tecton, or other feature store platforms
- Integrating feature store with Snowflake Model Registry

## Mandatory Initialization

Before any workflow, you MUST:

### Step 1: Load API Reference

**Load**: `references/api-reference.md` — Python API quick reference for FeatureStore, Entity, FeatureView, Feature, OnlineConfig.

**DO NOT PROCEED until you have loaded this reference.**

### Step 2: Confirm Environment

**Ask user:**
```
To set up your feature store, I need:
1. Database name (must already exist)
2. Feature store schema name (will be created if needed)
3. Warehouse name
4. Are you working in a notebook, IDE, or CLI?
```

**⚠️ STOP**: Wait for user response before proceeding.

### Step 3: Establish Session

Confirm the user has a Snowpark session. If not, guide them:

```python
from snowflake.snowpark import Session

# Option A: Connection name (recommended for CLI/IDE)
session = Session.builder.config("connection_name", "<connection>").create()

# Option B: Explicit parameters
session = Session.builder.configs({
    "account": "<account>",
    "user": "<user>",
    "password": "<password>",
    "warehouse": "<warehouse>",
    "database": "<database>",
    "schema": "<schema>",
}).create()

session.sql_simplifier_enabled = True
```

---

## Intent Detection

When a user makes a request, detect their intent and route to the appropriate sub-skill:

### CREATE Intent

**Trigger phrases**: "create feature store", "register entity", "create feature view", "set up feature store", "new entity", "new feature view", "add features from a table", "temporal features", "aggregation API"

**→ Load**: `create/SKILL.md`

### PIPELINES Intent

**Trigger phrases**: "feature pipeline", "refresh_freq", "managed feature view", "external feature view", "dynamic table pipeline", "incremental refresh", "dbt features", "schedule features", "inference pipeline"

**→ Load**: `pipelines/SKILL.md`

### TRAINING Intent

**Trigger phrases**: "training dataset", "generate_dataset", "spine", "point-in-time", "training set", "retrieve features", "retrieve_feature_values", "AsOf join", "backfill", "preprocessing", "encoding", "scaling"

**→ Load**: `training/SKILL.md`

### ONLINE Intent

**Trigger phrases**: "online features", "online serving", "low latency", "real-time features", "OnlineConfig", "StoreType.ONLINE", "feature serving", "production serving", "online feature table"

**→ Load**: `online/SKILL.md`

### MONITOR Intent

**Trigger phrases**: "feature freshness", "refresh history", "pipeline health", "list feature views", "suspend feature view", "resume feature view", "feature store cost", "audit", "validate", "check feature store", "promote features", "DEV to PROD"

**→ Load**: `monitor/SKILL.md`

### LINEAGE Intent

**Trigger phrases**: "feature lineage", "which models use", "model consumers", "impact analysis", "inference feature view", "model inference", "serve features", "inference FV", "create inference view", "batch inference features", "model input features"

**→ Load**: `lineage/SKILL.md`

### MIGRATE Intent

**Trigger phrases**: "migrate from Feast", "migrate from Tecton", "migration", "convert feature store", "move to Snowflake feature store"

**→ Load**: `migrate/SKILL.md`

### TECTON Intent (executable Tecton spec → SDK script generation)

**Trigger phrases**: "translate this Tecton spec", "generate FV script from Tecton", "convert Tecton feature view", "@stream_feature_view", "@batch_feature_view", "StreamSource", "StreamConfig", "continuous aggregation", "generate stream feature view script", "backfill_df"

**→ Load**: `migrate/tecton/SKILL.md` (for planning/concept-level Tecton migration, use `migrate/SKILL.md` instead)

### PATTERNS Intent (no sub-skill — load reference directly)

**Trigger phrases**: "feature patterns", "windowed aggregation", "rolling average", "lag features", "cumulative features", "how to write features"

**→ Load**: `references/feature-patterns.md` and assist directly.

### DESIGN Intent (no sub-skill — load reference directly)

**Trigger phrases**: "naming conventions", "schema organization", "feature store design", "versioning strategy", "access control", "environment promotion", "RBAC", "MIT MDT ODT", "transformation taxonomy"

**→ Load**: `references/design-guide.md` and assist directly.

---

## Workflow Decision Tree

```
Start Session
    ↓
MANDATORY: Load references/api-reference.md
    ↓
MANDATORY: Confirm environment (database, schema, warehouse)
    ↓
MANDATORY: Establish Snowpark session
    ↓
Detect User Intent
    ↓
    ├─→ CREATE      → Load create/SKILL.md
    ├─→ PIPELINES   → Load pipelines/SKILL.md
    ├─→ TRAINING    → Load training/SKILL.md
    ├─→ ONLINE      → Load online/SKILL.md
    ├─→ MONITOR     → Load monitor/SKILL.md
    ├─→ LINEAGE     → Load lineage/SKILL.md
    ├─→ MIGRATE     → Load migrate/SKILL.md
    ├─→ TECTON      → Load migrate/tecton/SKILL.md
    ├─→ PATTERNS    → Load references/feature-patterns.md (assist directly)
    └─→ DESIGN      → Load references/design-guide.md (assist directly)
```

---

## Sub-Skills

| Sub-Skill | Purpose | When to Load |
|-----------|---------|--------------|
| [create/SKILL.md](create/SKILL.md) | Create feature store, entities, feature views, temporal features, aggregation API | CREATE intent |
| [pipelines/SKILL.md](pipelines/SKILL.md) | Build and manage feature pipelines (managed, external, inference) | PIPELINES intent |
| [training/SKILL.md](training/SKILL.md) | Generate training datasets, preprocessing, Model Registry integration | TRAINING intent |
| [online/SKILL.md](online/SKILL.md) | Enable and use online feature serving, production patterns | ONLINE intent |
| [monitor/SKILL.md](monitor/SKILL.md) | Monitor health, audit/validate, promote, suspend/resume, cost | MONITOR intent |
| [lineage/SKILL.md](lineage/SKILL.md) | Feature lineage, inference feature views from model signatures | LINEAGE intent |
| [migrate/SKILL.md](migrate/SKILL.md) | Migrate from Feast, Tecton, or other platforms | MIGRATE intent |
| [migrate/tecton/SKILL.md](migrate/tecton/SKILL.md) | Generate StreamSource/BFV/SFV Python scripts from Tecton specs (executable codegen) | TECTON intent |

## Related Skills

| User Intent | Route To |
|-------------|----------|
| Manage Datasets outside Feature Store context | `../datasets/SKILL.md` |
| Query ML Lineage (what trained my model?) | `../ml-lineage/SKILL.md` |
| Register trained model | `../model-registry/SKILL.md` |

**Datasets vs Training-Datasets:**
- Use `training-datasets/` for extracting features FROM Feature Store with point-in-time correctness
- Use `../datasets/` for general Dataset management (create, version, list, load into PyTorch/TensorFlow)

## References

| Reference | Content | When to Load |
|-----------|---------|--------------|
| [references/api-reference.md](references/api-reference.md) | Python API quick reference | Always (mandatory init) |
| [references/feature-patterns.md](references/feature-patterns.md) | Feature transformation patterns + Aggregation API | PATTERNS intent or when writing feature logic |
| [references/design-guide.md](references/design-guide.md) | Naming, taxonomy (MIT/MDT/ODT), schema org, versioning, RBAC | DESIGN intent or when planning structure |
| [references/troubleshooting.md](references/troubleshooting.md) | Diagnostic queries, common issues, incremental refresh blockers | When diagnosing issues |

---

## Important Constraints

### 1. Package Versions

| Package | Min Version | For |
|---------|-------------|-----|
| `snowflake-ml-python` | `>= 1.5.0` | Core Feature Store |
| `snowflake-ml-python` | `>= 1.18.0` | Online features (OnlineConfig) |
| `snowflake-ml-python` | `>= 1.21.0` | Aggregation API (Feature class) |
| `snowflake-snowpark-python` | `>= 1.25.0` | Snowpark session |

### 2. Feature Store = Schema

A feature store is simply a Snowflake schema. The database must already exist; the schema is created by the API.

### 3. Entities Are Tags

Entities are implemented as Snowflake tags. Subject to the limit of 10,000 tags per account and 50 unique tags per object.

### 4. Managed Feature Views = Dynamic Tables

Snowflake-managed feature views use Dynamic Tables under the hood. All Dynamic Table constraints apply (change tracking, incremental refresh rules).

### 5. Point-in-Time Correctness

Always use `spine_timestamp_col` when generating training datasets with temporal features to prevent data leakage.

### 6. Transformation Taxonomy

Classify every transformation before deciding where it belongs:

| Type | Full Name | Where | Reusable? | Examples |
|------|-----------|-------|-----------|----------|
| **MIT** | Model-Independent | FeatureView | Yes, across models | Aggregations, joins, derived columns |
| **MDT** | Model-Dependent | Model Registry (Pipeline) | No, tied to model | Scaling, encoding, imputation. **Fit on training data only** |
| **ODT** | On-Demand | Inference time | N/A | Time-since-last, distance, current weather |

---

## Stopping Points Summary

All sub-skills follow this philosophy: **NO Snowflake object creation without explicit user approval.**

- **READ-ONLY queries**: Can run freely (listing, monitoring)
- **ANY mutation** (register entity, register feature view, create dataset): Requires stopping point and user approval

---

## Context Preservation Between Skills

When transitioning between sub-skills (e.g., CREATE → PIPELINES → TRAINING):

**Information to preserve:**
- Feature store instance details (database, schema, warehouse)
- Registered entity names and join keys
- Registered feature view names and versions
- Session object reference

**How:** Carry forward the `fs` (FeatureStore) object and entity/feature view references across workflow steps.
