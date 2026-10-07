---
name: feature-store-create
description: "Create Snowflake Feature Store, register entities, create feature views, temporal features, and aggregation API."
parent_skill: feature-store
path: machine-learning/feature-store/create
---

# Create Feature Store, Entities & Feature Views

## When to Load

Parent skill routes here for CREATE intent: "create feature store", "register entity", "create feature view", "set up feature store", "add features from a table", "temporal features", "aggregation API".

## Prerequisites

- `../references/api-reference.md` loaded (mandatory init from parent)
- User has confirmed database, schema, warehouse
- Snowpark session established

---

## Workflow

### Step 1: Create or Connect to Feature Store

**Ask user:**
```
Should I create a new feature store or connect to an existing one?
1. Create new (will create schema if it doesn't exist)
2. Connect to existing
```

**⚠️ STOP**: Wait for user response.

**If creating new:**
```python
from snowflake.ml.feature_store import FeatureStore, CreationMode

fs = FeatureStore(
    session=session,
    database="<DATABASE>",
    name="<SCHEMA>",
    default_warehouse="<WAREHOUSE>",
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
)
```

**If connecting to existing:**
```python
fs = FeatureStore(
    session=session,
    database="<DATABASE>",
    name="<SCHEMA>",
    default_warehouse="<WAREHOUSE>",
    creation_mode=CreationMode.FAIL_IF_NOT_EXIST,
)
```

**Environment organization** (recommended starting point — schema-based):
```
ML_FEATURES_DB
├── DEV_FEATURE_STORE      (dev experiments)
├── TEST_FEATURE_STORE     (integration testing)
└── PROD_FEATURE_STORE     (production serving)
```

**⚠️ STOP**: Confirm database/schema exist. Load `../references/design-guide.md` for full RBAC/org setup if creating new.

---

### Step 2: Explore Source Data

If adding features from a table:

1. **Identify** the source table
2. **Describe** the table:
   ```sql
   DESCRIBE TABLE <database>.<schema>.<table>;
   SELECT * FROM <table> LIMIT 5;
   ```
3. **Identify** the entity key (unique identifier column)
4. **Classify** columns using the Transformation Taxonomy (see `../references/design-guide.md`):
   - Feature columns (MIT) → go into FeatureView
   - Label columns → go into spine DataFrame
   - Preprocessing candidates (MDT) → go into Model Registry Pipeline
5. **Check** if a `timestamp_col` is available for PIT correctness
6. **Flag temporal columns** — identify any date, timestamp, or YYYYMM-encoded numeric columns that could support temporal feature derivation (→ Step 6)

---

### Step 3: Register Entities

**Rules:**
- Join keys are immutable after registration — plan carefully
- Use **consistent key naming** everywhere (always `USER_ID`, never mix `CUSTOMER_ID`/`USR_ID`)
- Entity name is a **business object** (CUSTOMER, ORDER, PRODUCT, ROUTE)

**Ask user:**
```
What entities do your features describe? For each entity, I need:
- Entity name (e.g., CUSTOMER, PRODUCT, ORDER)
- Join key column(s) (e.g., CUSTOMER_ID, [ORDER_ID, LINE_ID])
- Optional description

Note: Join keys are immutable after registration — choose carefully.
```

**⚠️ STOP**: Wait for user response.

```python
from snowflake.ml.feature_store import Entity

entity = Entity(
    name="<ENTITY_NAME>",
    join_keys=["<KEY_COL>"],
    desc="<description>"
)
fs.register_entity(entity)
```

**Verify:**
```python
fs.list_entities().show()
```

**Entity types:**
- **Simple**: Single join key (`USER_ID`)
- **Compound**: Multiple keys for M:N relationships (`[PRODUCT_ID, SUPPLIER_ID]`)
- **Hierarchical**: HOUSEHOLD → USER → SESSION (spine must include all FK levels)

---

### Step 4: Create Feature View

**Ask user:**
```
For your feature view, I need:
1. Feature view name
2. Which entity(ies) it relates to
3. Source table or query for feature logic
4. Is refreshing Snowflake-managed (auto-refresh) or externally managed (you manage refreshing)?
5. If managed: refresh frequency (e.g., "5 minutes", "1 hour", "1 day")
6. Does it include time-series features? If so, which column is the timestamp?
```

**⚠️ STOP**: Wait for user response.

**Build the feature DataFrame:**
```python
features_df = session.sql("""
    SELECT
        <KEY_COLUMN>,
        <FEATURE_COLUMNS>
    FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
    WHERE <data_quality_filters>
""")
```

For common transformation patterns, load `../references/feature-patterns.md`.

**Create the FeatureView:**
```python
from snowflake.ml.feature_store import FeatureView

fv = FeatureView(
    name="<ENTITY>_<DOMAIN>_FV",
    entities=[entity],
    feature_df=features_df,
    timestamp_col="<TS_COL>",
    refresh_freq="<FREQ>",
    refresh_mode="INCREMENTAL",
    desc="<description>",
)
```

**Attach feature descriptions:**
```python
fv = fv.attach_feature_desc({
    "<FEATURE1>": "<description>",
    "<FEATURE2>": "<description>",
})
```

**⚠️ MANDATORY CHECKPOINT**: Present the feature view configuration to user for approval before registering.

```
I will register this feature view:
- Name: <FV_NAME>
- Version: V01
- Entity: <ENTITY_NAME> (join keys: <KEYS>)
- Type: Managed / External
- Refresh: <FREQ> (<INCREMENTAL|FULL>)
- Features: <list of feature columns>

Approve? (Yes/No/Modify)
```

**Register:**
```python
registered_fv = fs.register_feature_view(
    feature_view=fv,
    version="V01",
    block=True,
)
```

**Verify:**
```python
fs.list_feature_views().select("NAME", "VERSION", "SCHEDULING_STATE").show()
```

**Feature View types:**
| Type | `refresh_freq` | Backed By | Use Case |
|------|---------------|-----------|----------|
| Managed (DT) | `"1 day"`, `"1 hour"`, etc. | Dynamic Table | Pre-computed, auto-refresh |
| External | `None` | View | DBT-managed or external pipelines |

**Decide refresh_freq**: Match to source update frequency. Source updates daily → don't refresh every 5 minutes (wasteful).

**⚠️ STOP**: If registration fails with "Database not authorized", use `refresh_freq=None` for external feature view.

---

### Step 5: Aggregation API (Feature Class)

**Requires**: `snowflake-ml-python >= 1.21.0`

For declarative time-windowed aggregations with tiling:

```python
from snowflake.ml.feature_store import Feature

purchase_amount = Feature("PURCHASE_AMOUNT", "Amount of each purchase")

features = [
    purchase_amount.sum(windows=["7d", "30d"]).alias("TOTAL_SPEND"),
    purchase_amount.avg(windows=["7d", "30d"]).alias("AVG_SPEND"),
    purchase_amount.count(windows=["7d", "30d"]).alias("PURCHASE_CNT"),
    purchase_amount.std(windows=["30d"]).alias("SPEND_STD"),
]

fv = FeatureView(
    name="USER_PURCHASE_FV",
    entities=[user_entity],
    feature_df=transactions_df,
    feature_granularity="1 day",
    features=features,
    refresh_freq="1 day",
    desc="User purchase aggregations over 7d and 30d windows",
)
```

**Tile size guidance:** see [Choosing `feature_granularity`](../references/feature-patterns.md#choosing-feature_granularity-tile-size) for the data-type table and the window-divisibility rules.

---

### Step 6: Temporal Feature Discovery

After registering the primary feature view, check if the source data supports derived temporal features. If it does, create a **separate** `<ENTITY>_TEMPORAL_FV` to keep feature views focused and composable.

#### When to Apply

Apply when source table contains **any** of:
- DATE or TIMESTAMP columns (e.g., `CREATED_AT`, `ORDER_DATE`, `EVENT_TS`)
- YYYYMM or YYYYMMDD encoded numeric columns (e.g., `FIRSTPAYMENTDATE = 202301`)
- Duration/term columns (e.g., `LOAN_TERM`, `CONTRACT_MONTHS`)
- Pairs of date columns that define a time span (e.g., start/end, origination/maturity)

If none exist, skip to Step 7.

#### Temporal Feature Catalog

| Category | Features | SQL Pattern | When to Use |
|----------|----------|-------------|-------------|
| **Calendar extraction** | `ORIG_MONTH`, `ORIG_QUARTER`, `ORIG_YEAR` | `MOD(YYYYMM_COL, 100)`, `CEIL(MOD()/3.0)::INT`, `FLOOR(YYYYMM_COL/100)` | Any date/YYYYMM column |
| **Seasonality flags** | `IS_WINTER_ORIG`, `IS_Q4_ORIG`, `IS_WEEKEND` | `CASE WHEN month IN (...) THEN 1 ELSE 0 END` | Seasonal patterns expected |
| **Duration / span** | `LOAN_DURATION_YEARS`, `CONTRACT_MONTHS` | `DATEDIFF(...)` on static date pairs | Two date columns define a span |
| **Cyclical encoding** | `MONTH_SIN`, `MONTH_COS`, `DOW_SIN`, `DOW_COS` | `SIN(2 * PI() * val / period)`, `COS(...)` | Month/day-of-week should wrap |
| **Epoch / vintage** | `DAYS_SINCE_EPOCH`, `ORIG_YEAR_BUCKET` | `DATEDIFF('day', '1970-01-01', date_col)`, `FLOOR(YEAR/5)*5` | Absolute time position matters |
| **Relative position** | `MONTH_IN_QUARTER`, `WEEK_IN_YEAR` | `MOD(month-1, 3)+1`, `WEEKOFYEAR(...)` | Position within cycle matters |

#### Leakage Guard

Before including a temporal feature, classify it:

| Classification | Safe? | Example | Action |
|---------------|-------|---------|--------|
| **Known at prediction time** | Yes | Origination month, loan term | Include |
| **Post-event / outcome-adjacent** | No | Months delinquent, months in repayment | Exclude — or include only with explicit user confirmation |
| **Requires CURRENT_TIMESTAMP** | No | Age of loan, days since origination | Compute at query/inference time (ODT) |

**⚠️ STOP**: Ask the user whether to include post-event columns. Explain the leakage risk.

#### Implementation Pattern

```python
temporal_df = session.sql("""
    SELECT
        <ENTITY_KEY>,
        MOD(<YYYYMM_COL>, 100) AS ORIG_MONTH,
        CEIL(MOD(<YYYYMM_COL>, 100) / 3.0)::INT AS ORIG_QUARTER,
        FLOOR(<YYYYMM_COL> / 100) AS ORIG_YEAR,
        (FLOOR(<END_YYYYMM> / 100) - FLOOR(<START_YYYYMM> / 100)) AS DURATION_YEARS,
        CASE
            WHEN MOD(<YYYYMM_COL>, 100) IN (1, 2, 3, 10, 11, 12) THEN 1
            ELSE 0
        END AS IS_WINTER_ORIG
    FROM <DATABASE>.<SCHEMA>.<SOURCE_TABLE>
    WHERE <same_data_quality_filters>
    QUALIFY ROW_NUMBER() OVER (PARTITION BY <ENTITY_KEY> ORDER BY <tiebreaker>) = 1
""")

temporal_fv = FeatureView(
    name="<ENTITY>_TEMPORAL_FV",
    entities=[entity],
    feature_df=temporal_df,
    refresh_freq="1 day",
    desc="Temporal features derived from <source_date_columns>",
)

temporal_fv = temporal_fv.attach_feature_desc({
    "ORIG_MONTH": "Origination month (1-12)",
    "ORIG_QUARTER": "Origination quarter (1-4)",
    "ORIG_YEAR": "Origination year",
    "DURATION_YEARS": "Duration in years between <start> and <end>",
    "IS_WINTER_ORIG": "Winter origination flag (Oct-Mar = 1, Apr-Sep = 0)",
})

registered_temporal_fv = fs.register_feature_view(
    feature_view=temporal_fv,
    version="V01",
    block=True,
)
```

All temporal features must be **deterministic and static** — derived only from source columns, not from `CURRENT_DATE()` or `CURRENT_TIMESTAMP()`. This ensures incremental refresh compatibility.

---

### Step 7: Verify Registration

```python
print(fs.list_entities().to_pandas())
print(fs.list_feature_views().to_pandas())
```

Check refresh mode is INCREMENTAL (not FULL). If FULL, check `../references/troubleshooting.md` for incremental refresh blockers.

---

### Step 8: Next Steps

**Ask user:**
```
Feature view registered successfully. Would you like to:
1. Create another feature view
2. Set up a feature pipeline (→ pipelines/SKILL.md)
3. Generate a training dataset (→ training/SKILL.md)
4. Audit/validate the feature view (→ monitor/SKILL.md)
5. Done for now
```

---

## Stopping Points

- ✋ Step 1: Before creating/connecting to feature store
- ✋ Step 3: Before registering each entity
- ✋ Step 4: Before registering feature view (mandatory approval)
- ✋ Step 6: Before including post-event temporal columns (leakage check)
- ✋ Step 8: Next action selection

## Output

- Initialized `fs` FeatureStore object
- Registered entities
- Registered feature view(s) with materialized data
- Temporal feature view (if applicable)

## Next Skill

- If user wants pipelines → **Load** `pipelines/SKILL.md`
- If user wants training data → **Load** `training/SKILL.md`
- If user wants to audit → **Load** `monitor/SKILL.md`
