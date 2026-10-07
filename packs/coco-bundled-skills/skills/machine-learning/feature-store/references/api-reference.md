# Snowflake Feature Store — Python API Quick Reference

Package: `snowflake-ml-python` (>= 1.5.0, >= 1.18.0 for online features, >= 1.21.0 for Aggregation API)

```python
from snowflake.ml.feature_store import (
    FeatureStore,
    FeatureView,
    Entity,
    CreationMode,
    OnlineConfig,
    Feature,
)
from snowflake.ml.feature_store.feature_view import StoreType
```

---

## FeatureStore

### Constructor

```python
fs = FeatureStore(
    session=session,                              # Snowpark Session (required)
    database="MY_DB",                             # Database name (required, must exist)
    name="MY_FEATURE_STORE",                      # Schema name (required)
    default_warehouse="MY_WH",                    # Warehouse (required)
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST # or FAIL_IF_NOT_EXIST
)
```

- `CREATE_IF_NOT_EXIST`: Creates schema + tags if missing. Use for initial setup.
- `FAIL_IF_NOT_EXIST`: Connects to existing feature store. Use for subsequent connections.

### Entity Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_entity` | `(entity: Entity)` | Register entity in feature store |
| `get_entity` | `(name: str) → Entity` | Retrieve registered entity |
| `list_entities` | `() → DataFrame` | List all entities |
| `update_entity` | `(name: str, desc: str)` | Update entity description |
| `delete_entity` | `(name: str)` | Delete entity (fails if referenced by feature views) |

### Feature View Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `register_feature_view` | `(feature_view: FeatureView, version: str, block: bool=True, overwrite: bool=False) → FeatureView` | Materialize feature view |
| `get_feature_view` | `(name: str, version: str) → FeatureView` | Retrieve registered feature view |
| `list_feature_views` | `(entity_name=None, feature_view_name=None) → DataFrame` | List feature views |
| `update_feature_view` | `(name: str, version: str, desc=None, online_config=None, refresh_freq=None, warehouse=None) → FeatureView` | Update feature view properties |
| `delete_feature_view` | `(feature_view: FeatureView or str, version: str)` | Delete feature view |
| `suspend_feature_view` | `(feature_view or name: str, version: str)` | Suspend scheduling |
| `resume_feature_view` | `(feature_view or name: str, version: str)` | Resume scheduling |
| `read_feature_view` | `(feature_view, version=None, keys=None, feature_names=None, store_type=StoreType.OFFLINE) → DataFrame` | Read feature values |
| `get_refresh_history` | `(feature_view, version=None) → DataFrame` | Get refresh statistics |

### Dataset & Retrieval Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `generate_dataset` | `(name, spine_df, features, *, version=None, spine_timestamp_col=None, spine_label_cols=None, exclude_columns=None, include_feature_view_timestamp_col=False, desc="", output_type="dataset") → Dataset` | Generate training dataset with point-in-time joins |
| `generate_training_set` | `(spine_df, features, timestamp_col, spine_label_cols=None) → DataFrame` | Generate training set (returns DataFrame directly) |
| `retrieve_feature_values` | `(spine_df, features, spine_timestamp_col=None, exclude_columns=None, include_feature_view_timestamp_col=False) → DataFrame` | Enrich spine with features (for inference) |
| `load_feature_views_from_dataset` | `(ds: Dataset) → list[FeatureView]` | Get feature views used in a dataset |

### Other Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `update_default_warehouse` | `(warehouse_name: str)` | Change default warehouse |

---

## Entity

### Constructor

```python
entity = Entity(
    name="CUSTOMER",            # Entity name (required)
    join_keys=["CUSTOMER_ID"],  # List of join key column names (required)
    desc="Customer entity"      # Optional description
)
```

**Properties:** `name`, `join_keys`, `desc`, `owner`

**Notes:**
- Join keys are immutable after registration. To change, create a new entity.
- Entities referenced by feature views cannot be deleted.
- Composite entities use multiple join keys: `join_keys=["ORDER_ID", "LINE_ID"]`

---

## FeatureView

### Constructor

```python
fv = FeatureView(
    name="MY_FEATURE_VIEW",         # Name (required)
    entities=[entity],               # List of Entity objects (required)
    feature_df=my_df,                # Snowpark DataFrame with feature logic (required)
    timestamp_col="EVENT_TS",        # Timestamp column for temporal features (optional)
    refresh_freq="5 minutes",        # Refresh schedule (optional; None = external)
    desc="Description",              # Optional description
    refresh_mode="INCREMENTAL",      # "INCREMENTAL" or "FULL" (optional)
    cluster_by=["COL1"],             # Clustering columns (optional)
)
```

**Key parameters:**
- `refresh_freq`: Set to make it Snowflake-managed (Dynamic Table). Set `None` for external management (view). Accepts time deltas (`"5 minutes"`, `"1 hour"`) or cron (`"* * * * * America/Los_Angeles"`). Minimum: 1 minute.
- `refresh_mode`: `"INCREMENTAL"` (default, requires change tracking on sources) or `"FULL"`.
- `feature_df`: Must contain the join key columns from the associated entities.
- `timestamp_col`: Required for point-in-time correct retrieval.

### Key Methods

| Method | Description |
|--------|-------------|
| `attach_feature_desc(desc_dict)` | Attach descriptions to features: `{"COL": "description"}` |
| `slice(feature_names)` | Create a FeatureViewSlice with subset of features |
| `to_df()` | Convert feature view metadata to DataFrame |
| `feature_names` | List of feature column names |
| `feature_descs` | List of feature descriptions (SqlIdentifier objects — use `str()` to convert) |
| `status` | `DRAFT`, `ACTIVE`, `SUSPENDED` (FeatureViewStatus enum — use `str()` for comparison) |
| `version` | Version string |
| `query` | The underlying SQL query |
| `entities` | Linked entities list |
| `online` | Whether online serving is enabled |

### Online Store

```python
# Enable online store at creation time
fv = FeatureView(...).with_online_store(enabled=True)

# Or enable on existing feature view via OnlineConfig
from snowflake.ml.feature_store import OnlineConfig, OnlineStoreType
config = OnlineConfig(
    enable=True,
    target_lag="15s",
    store_type=OnlineStoreType.POSTGRES,  # Postgres-backed Online Feature Store; default is HYBRID_TABLE
)
fs.update_feature_view(name="MY_FV", version="v1", online_config=config)
```

---

## Feature (Aggregation API)

Requires `snowflake-ml-python >= 1.21.0`. Declarative time-windowed aggregations with tiling.

> **Online serving:** Time-windowed aggregations are supported on the Postgres-backed Online Feature Store (`OnlineStoreType.POSTGRES`). They are not supported on hybrid-table online serving. Some functions are offline-only (e.g. `last_distinct_n`); see the Snowflake docs for per-function online support.

```python
from snowflake.ml.feature_store import Feature

amount = Feature("PURCHASE_AMOUNT", "Amount of each purchase")

features = [
    amount.sum(windows=["7d", "30d"]).alias("TOTAL_SPEND"),
    amount.avg(windows=["7d", "30d"]).alias("AVG_SPEND"),
    amount.count(windows=["7d", "30d"]).alias("PURCHASE_CNT"),
    amount.std(windows=["30d"]).alias("SPEND_STD"),
]

fv = FeatureView(
    name="USER_PURCHASE_FV",
    entities=[user_entity],
    feature_df=transactions_df,
    feature_granularity="1 day",   # Tile size
    features=features,
    refresh_freq="1 day",
    desc="User purchase aggregations",
)
```

**Available functions:** `.sum()`, `.count()`, `.avg()`, `.min()`, `.max()`, `.std()`, `.var()`, `.approx_count_distinct()`, `.last_n()`, `.first_n()`

**Tile size guidance:** see [Choosing `feature_granularity`](feature-patterns.md#choosing-feature_granularity-tile-size) for the data-type table and the window-divisibility rules.

---

## OnlineConfig

```python
from snowflake.ml.feature_store import OnlineConfig

config = OnlineConfig(enable=True, target_lag="15s")

fs.update_feature_view(
    name="MY_FV", version="v1",
    online_config=config
)
```

**Target lag options:** `"15s"`, `"1m"`, `"5m"` — balance freshness vs cost.

---

## StoreType

```python
from snowflake.ml.feature_store.feature_view import StoreType

# Read from offline store (default)
fs.read_feature_view("MY_FV", "v1", store_type=StoreType.OFFLINE)

# Read from online store (low-latency)
fs.read_feature_view("MY_FV", "v1", keys=[[1], [2]], store_type=StoreType.ONLINE)
```

---

## CreationMode

| Mode | Behavior |
|------|----------|
| `CreationMode.CREATE_IF_NOT_EXIST` | Creates schema and tags if they don't exist |
| `CreationMode.FAIL_IF_NOT_EXIST` | Raises error if schema doesn't exist |

---

## Model Registry (for lineage and inference)

```python
from snowflake.ml.registry import Registry

registry = Registry(session=session)
model = registry.get_model("<MODEL_NAME>")
mv = model.version("<VERSION>")

mv.show_functions()                                              # Get model signature
mv.lineage(direction='upstream', domain_filter={'feature_view'}) # Get source FVs
mv.run(inference_df, function_name="predict")                    # Run model
```

**`show_functions()` returns** `List[dict]` with keys: `name`, `target_method`, `signature` (ModelSignature with `.inputs` list of FeatureSpec with `.name`, `.dtype`).
