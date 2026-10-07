---
name: feature-store-pipelines
description: "Build and manage Snowflake Feature Store pipelines — managed (Dynamic Table), external (dbt, custom), and inference."
parent_skill: feature-store
path: machine-learning/feature-store/pipelines
---

# Feature Pipelines

## When to Load

Parent skill routes here for PIPELINES intent: "feature pipeline", "refresh_freq", "managed feature view", "external feature view", "dbt features", "schedule features", "inference pipeline".

## Prerequisites

- `../references/api-reference.md` loaded
- Feature store (`fs`) and entities already created (via create/SKILL.md)

---

## Workflow

### Step 1: Determine Pipeline Type

**Ask user:**
```
What type of feature pipeline do you need?

1. Snowflake-managed — Automatic refresh via Dynamic Tables (recommended)
2. External — You maintain the feature table (e.g., via dbt, custom ETL)
3. Inference pipeline — Use a registered model to produce features
```

**⚠️ STOP**: Wait for user response.

---

### Step 2A: Snowflake-Managed Pipeline

A managed feature view uses a Dynamic Table that automatically refreshes from source data.

**Key decisions:**

| Decision | Options | Guidance |
|----------|---------|----------|
| Refresh frequency | Time delta or cron | Balance freshness vs cost. Minimum: 1 minute |
| Refresh mode | INCREMENTAL / FULL | INCREMENTAL preferred. Requires change tracking on sources |
| Clustering | Column list | Use join keys + frequently filtered columns |

**Change tracking requirement:**
```sql
SHOW TABLES LIKE '<SOURCE_TABLE>';
-- Look for change_tracking = 'ON'

ALTER TABLE <SOURCE_TABLE> SET CHANGE_TRACKING = TRUE;
```

If the user doesn't own the source table and can't enable change tracking, use `refresh_mode="FULL"`.

**Create the managed feature view:**
```python
feature_df = session.sql("""
    SELECT <join_key>, <timestamp_col>, <feature_columns>
    FROM <source_table>
    -- feature transformation logic here
""")

fv = FeatureView(
    name="<ENTITY>_<DOMAIN>_FV",
    entities=[entity],
    feature_df=feature_df,
    timestamp_col="<TS_COL>",
    refresh_freq="<FREQ>",
    refresh_mode="INCREMENTAL",
    desc="<description>",
)
```

**⚠️ MANDATORY CHECKPOINT** — Present the feature view configuration to user before registering:
```
I will register this managed feature view:
- Name: <FV_NAME> V01
- Source: <source_table>
- Refresh: <FREQ> (<INCREMENTAL|FULL>)
- Timestamp col: <TS_COL>

This creates a Dynamic Table with ongoing compute cost.
Approve? (Yes/No/Modify)
```

```python
registered_fv = fs.register_feature_view(fv, version="V01", block=True)
```

**Multi-stage pipelines:**
For complex transformations, chain multiple feature views where intermediate stages use `refresh_freq="DOWNSTREAM"`:

```python
clean_fv = FeatureView(
    name="FV_CLEAN", entities=[entity], feature_df=clean_df,
    refresh_freq="DOWNSTREAM",
)

agg_fv = FeatureView(
    name="FV_AGGREGATED", entities=[entity], feature_df=agg_df,
    refresh_freq="10 minutes",
    timestamp_col="EVENT_TS",
)
```

---

### Step 2B: External Pipeline

For features maintained outside the Feature Store (e.g., dbt).

**The user is responsible for:**
1. Creating and maintaining the feature table
2. Populating it with fresh data
3. The feature view is a read-only registration

```python
feature_df = session.table("MY_DB.MY_SCHEMA.MY_FEATURE_TABLE").select(
    "CUSTOMER_ID", "TX_DATETIME",
    "TX_AMOUNT_1D", "TX_AMOUNT_7D", "TX_COUNT_30D"
)

external_fv = FeatureView(
    name="<ENTITY>_<DOMAIN>_FV",
    entities=[customer_entity],
    feature_df=feature_df,
    timestamp_col="TX_DATETIME",
    refresh_freq=None,
    desc="Features maintained by dbt pipeline",
)

fs.register_feature_view(external_fv, version="V01", block=True)
```

**dbt integration pattern:**
1. Build feature table in dbt: `dbt run --select ft_customer_transactions`
2. Register the dbt-produced table as an external feature view
3. dbt handles scheduling; feature store provides discovery, versioning, and retrieval

---

### Step 2C: Inference Pipeline

Use a registered model to produce prediction features as a new feature view.

```python
input_df = fs.read_feature_view("FV_FEATURES", "V01")

from snowflake.ml.registry import Registry
reg = Registry(session, database="MY_DB", schema="MODEL_REGISTRY")
mv = reg.get_model("MY_MODEL").version("V01")

inference_df = mv.run(input_df, function_name="predict")

inference_fv = FeatureView(
    name="<MODEL>_INFERENCE_FV",
    entities=[entity],
    feature_df=inference_df,
    refresh_freq="60 minutes",
    desc="Ongoing inference from ML model",
)

fs.register_feature_view(inference_fv, version="V01", block=True)
```

For more advanced inference feature views mapped from model signatures → **Load** `lineage/SKILL.md`.

---

### Step 3: Verify Pipeline Health

```python
fs.list_feature_views().select("NAME", "VERSION", "SCHEDULING_STATE").show()

fs.get_refresh_history(registered_fv).show()
```

For deeper monitoring → **Load** `monitor/SKILL.md`

---

## Important Constraints

1. **Incremental DTs cannot depend on Full refresh DTs** — ensure upstream stages are also incremental
2. **Change tracking must stay enabled** on source tables for incremental refresh
3. **Avoid SELECT *** in feature DataFrames — use explicit column lists to prevent schema change failures
4. **Minimum refresh_freq is 1 minute**
5. **DOWNSTREAM target lag** only works for intermediate pipeline stages (not leaf nodes)
6. **Incremental refresh blockers** — see `../references/troubleshooting.md` for patterns that force FULL refresh

---

## Stopping Points

- ✋ Step 1: Pipeline type selection
- ✋ Before `register_feature_view` — present config for approval
- ✋ Step 3: After verification, offer next steps

## Output

- Registered feature view(s) backed by managed or external pipelines
- Verified refresh state

## Next Skill

- If user wants training data → **Load** `training/SKILL.md`
- If user wants online serving → **Load** `online/SKILL.md`
- If user wants monitoring → **Load** `monitor/SKILL.md`
- If user wants lineage/inference FV → **Load** `lineage/SKILL.md`
