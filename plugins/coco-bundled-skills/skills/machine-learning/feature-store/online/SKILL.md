---
name: feature-store-online
description: "Enable and use Snowflake Feature Store online serving for low-latency feature retrieval, with production application patterns."
parent_skill: feature-store
path: machine-learning/feature-store/online
---

# Online Feature Serving

## When to Load

Parent skill routes here for ONLINE intent: "online features", "online serving", "low latency", "real-time features", "OnlineConfig", "StoreType.ONLINE", "production serving", "online feature table".

## Prerequisites

- `../references/api-reference.md` loaded
- Feature store (`fs`) initialized with registered feature views
- `snowflake-ml-python >= 1.18.0` for online features
- **Note:** The `online_config` API has been in private preview since `snowflake-ml-python 1.12.0`. Behavior and availability may change.

---

## Core Concepts

- **Online store**: Low-latency key-value store for serving features in production
- **Offline store**: Standard Dynamic Table / view for batch operations (training, batch inference)
- Both stores are kept in sync automatically — same feature definitions, no training/serving skew
- Online serving is enabled per feature view via `OnlineConfig` or `.with_online_store()`
- Online Feature Tables (OFTs) store **only latest values** (no history). Backed by Hybrid Tables.

---

## Workflow

### Step 1: Identify Feature Views for Online Serving

**Ask user:**
```
Which feature view(s) do you want to enable for online (low-latency) serving?
Note: Online serving adds infrastructure cost. Only enable for feature views
needed on the real-time inference path.
```

**⚠️ STOP**: Wait for user response.

**Retrieve the feature view:**
```python
fv = fs.get_feature_view("<FV_NAME>", "<VERSION>")
print(f"Online enabled: {fv.online}")
```

---

### Step 2: Enable Online Serving

There are two approaches:

**Approach A: OnlineConfig (update existing FV)**
```python
from snowflake.ml.feature_store import OnlineConfig

config = OnlineConfig(enable=True, target_lag="15s")

updated_fv = fs.update_feature_view(
    name="<FV_NAME>",
    version="<VERSION>",
    online_config=config,
)

print(f"Online enabled: {updated_fv.online}")
```

**Approach B: with_online_store (at creation time)**
```python
fv = FeatureView(
    name="<ENTITY>_REALTIME_FV",
    entities=[entity],
    feature_df=features_df,
    refresh_freq="5 minutes",
    desc="Low-latency features for real-time serving",
).with_online_store(enabled=True)
```

**⚠️ MANDATORY CHECKPOINT**: Confirm before enabling.

```
I will enable online serving for:
- Feature View: <FV_NAME> v<VERSION>
- Target lag: <lag> (how fresh online data should be)

This will create an online feature table with additional infrastructure cost.
Approve? (Yes/No/Modify)
```

> **⚠️ Provisioning delay:** After enabling, the online feature table needs time to provision and complete its initial refresh. This can take **30 seconds to several minutes**. Poll with a lightweight `read_feature_view(..., store_type=StoreType.ONLINE)` call in a retry loop.

**Target lag options and guidance:**

| Use Case | Target Lag | Refresh Freq |
|----------|-----------|--------------|
| Fraud detection | `"15s"` | `"1 minute"` |
| Recommendations | `"1m"` | `"5 minutes"` |
| Marketing | `"5m"` | `"15 minutes"` |

---

### Step 3: Read from Online Store

```python
from snowflake.ml.feature_store.feature_view import StoreType

result = fs.read_feature_view(
    "<FV_NAME>", "<VERSION>",
    keys=[[key_value_1], [key_value_2]],
    feature_names=["FEATURE_A", "FEATURE_B"],
    store_type=StoreType.ONLINE,
)
result.show()
```

**Key differences: ONLINE vs OFFLINE:**

| Aspect | OFFLINE (default) | ONLINE |
|--------|-------------------|--------|
| Latency | Seconds to minutes | Milliseconds |
| Use case | Training, batch inference | Real-time inference |
| Keys parameter | Optional | Recommended (key-based lookup) |
| Full table scan | Supported | Not recommended |
| Point-in-time | Supported via spine | Returns latest values only |

---

### Step 4: Production Application Pattern

**Flask/FastAPI serving example:**

```python
import os
from concurrent.futures import ThreadPoolExecutor
from snowflake.snowpark import Session
from snowflake.ml.feature_store import FeatureStore, CreationMode
from snowflake.ml.feature_store.feature_view import StoreType

session = Session.builder.configs(connection_params).create()

feature_store = FeatureStore(
    session=session,
    database="<DATABASE>",
    name="<SCHEMA>",
    default_warehouse="",
    creation_mode=CreationMode.FAIL_IF_NOT_EXIST,
)

fv_1 = feature_store.get_feature_view("FV_FEATURES_1", "V01")
fv_2 = feature_store.get_feature_view("FV_FEATURES_2", "V01")

executor = ThreadPoolExecutor(max_workers=os.cpu_count() * 2)

def retrieve_features(fv, keys, feature_names):
    return feature_store.read_feature_view(
        fv, keys=[keys],
        feature_names=feature_names,
        store_type=StoreType.ONLINE,
    ).collect()

def predict(entity_key):
    future_1 = executor.submit(retrieve_features, fv_1, [entity_key], ["F1", "F2"])
    future_2 = executor.submit(retrieve_features, fv_2, [entity_key], ["F3", "F4"])

    features_1 = future_1.result()
    features_2 = future_2.result()

    feature_vector = list(features_1[0][1:]) + list(features_2[0][1:])
    prediction = model.predict(feature_vector)
    return prediction
```

**Authentication for production:**
- Use Programmatic Access Tokens (PAT) or key-pair authentication
- Do not use password-based auth in production services

**Use batch lookups** (not individual calls) and a **dedicated warehouse** for OFT refresh.

---

### Step 5: Benchmarking & Performance

**Expected latency** for single-point lookup (~10 features):

| Percentile | Latency | Condition |
|-----------|---------|-----------|
| p50 | ~30ms | |
| p95 | ~50ms | |
| p99 | <100ms | <2000 QPS |

**If latency is high, check in this order:**

1. **API**: Are you using `read_feature_view(..., store_type=StoreType.ONLINE)`? Using `retrieve_feature_values()` (batch join API) is the most common benchmarking mistake.
2. **Config**: Is `online_config` set to `enable=True` on the feature view?
3. **Location**: Is your client running on an EC2 or SPCS instance in the **same region** as Snowflake? Local laptops, VPNs, or cross-region instances add 100ms+ of network jitter.
4. **Warm-up**: Has the warehouse been running lookups for at least 3-5 minutes? Hybrid Tables use a memory cache that must be primed.

**Hybrid Table warm-up:**
- Small datasets: ~3 minutes of queries before benchmarking
- Large datasets: 10-15 minutes before benchmarking
- Set `AUTO_SUSPEND` to 300-600 seconds to prevent cache loss. If the warehouse suspends, the next query reverts to ~500ms+ while data re-caches.

**Parallel feature retrieval:** If your application needs features from multiple feature views, use `ThreadPoolExecutor` (see Step 4 example) to fire requests in parallel. Sequential calls across 4 FVs = ~150-200ms; parallel = ~30-50ms (slowest call only).

---

### Step 6: Disable Online Serving

**⚠️ MANDATORY CHECKPOINT** — Disabling drops the online feature table.

```
I will disable online serving for:
- Feature View: <FV_NAME> v<VERSION>

This will DROP the online feature table. Any applications reading from
the online store for this feature view will stop working.
Approve? (Yes/No)
```

```python
disable_config = OnlineConfig(enable=False)

fs.update_feature_view(
    name="<FV_NAME>",
    version="<VERSION>",
    online_config=disable_config,
)
```

---

## Stopping Points

- ✋ Step 1: Feature view selection for online serving
- ✋ Step 2: Before enabling online serving (mandatory approval — cost implications)
- ✋ Step 6: Before disabling online serving (mandatory approval — drops online table)

## Output

- Feature view(s) with online serving enabled
- Code pattern for production application integration

## Next Skill

- If user wants monitoring → **Load** `monitor/SKILL.md`
- If user needs production deployment guidance → **Load** `../../spcs-inference/SKILL.md`
- If user wants lineage/inference FV → **Load** `lineage/SKILL.md`
