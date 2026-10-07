---
name: feature-store-tecton-rtfv
description: "Generate a standalone Python script for a Snowflake Feature Store real-time feature view (RTFV) using RealtimeConfig. RTFVs compute features at request time against live request data joined with upstream online feature views. Use when the user says: 'RTFV', 'real-time compute', 'request-time feature', 'RealtimeConfig', or describes a feature that derives from other feature views at inference time."
parent_skill: feature-store-tecton
path: machine-learning/feature-store/migrate/tecton/rtfv
---
# RTFV (Real-Time Feature View) Script Generation

An RTFV has no offline backing — `compute_fn` runs at request time against request
data + upstream online-enabled feature views. Online is always enabled (Postgres store).

## When to Load

Main skill (`../SKILL.md`) Step 1 classifies the artifact as a **Real-Time Feature View**:
user says "real-time compute", "request-time feature", "RTFV", "RealtimeConfig",
or describes a feature that derives from other feature views at inference time.

## Prerequisites

- Upstream feature view(s) already registered, online-enabled, and using Postgres store
- User has described what `compute_fn` should compute
- Output column names and types known

---

## Extract Required Fields

Ask with `AskQuestion` for any missing fields (all in one call):

- **`compute_fn` logic**: What computation to perform at request time
- **Request-time inputs** (if any): Columns the caller will supply per request
  (e.g. `transaction_amount`, `merchant_id`)
- **Upstream feature views** (at least one required): Which registered FVs to join against.
  `RealtimeConfig.sources` must contain 1+ `FeatureView`/`FeatureViewSlice` after the
  optional `RequestSource` — an RTFV with no upstream FVs fails registration
- **Output columns**: Name and type of each output column
- **Entity**: Join key connecting request data to upstream FVs

---

## `compute_fn` Rules

See main skill's "Transform Rules" section for the shared policy (module-level `def`,
allowed imports, ALL-CAPS columns). RTFV-specific additions:

- **Exactly one top-level `def`** in the source — no module-level helpers alongside it.
- Inline any helper logic; no nested `def` or `lambda` inside the function body.
- The function is exec'd into a runtime namespace that already contains `pd`, `np`, `re`, `copy` —
  these names are available without importing, but explicit `import pandas as pd` inside the body is also fine.
- **`compute_fn` output column names must be ALL-CAPS and must exactly match `output_schema`.**
  Snowflake normalizes `output_schema` field names to uppercase at registration. If
  `compute_fn` returns a DataFrame with mixed-case columns (e.g. `"IsBssidHabitual"` instead
  of `"ISBSSIDHABITUAL"`), the mismatch causes a runtime error at query time. Use the
  defensive one-liner `output_df.columns = [c.upper() for c in output_df.columns]` before
  every `return`.
- See `../reference.md` § "RealtimeConfig" for the full `compute_fn` API constraints (argument count, `*args`/`**kwargs` rules, etc.).

---

## Generate the Script

**⚠️ MANDATORY STOPPING POINT**: Before writing, present a summary for approval:

```
I'll generate create_{fv_name}.py with these settings:
- FV name:           {FV_NAME}
- Entity:            {entity_name} (join key: {entity_col})
- Request inputs:    {list of RequestSource columns, or "none"}
- Upstream FVs:      {list of upstream FV names}
- Output columns:    {list of output StructField(name, type)}
- compute_fn:        {brief description of the computation}

Shall I write the file?
```

Wait for explicit approval before proceeding.

Write the file with `Write`. Default location: the user's current directory (or wherever they indicate).

### Template: RTFV script

```python
#!/usr/bin/env python3
"""Create real-time feature view: {FV_NAME}

Prerequisites:
    pip install snowflake-ml-python
    Upstream feature view(s) must already be registered and online-enabled.

Run:
    python {filename}.py
"""

import pandas as pd
from snowflake.ml.feature_store import (
    CreationMode,
    Entity,
    FeatureStore,
    FeatureView,
)
from snowflake.ml.feature_store.realtime_config import RealtimeConfig
from snowflake.ml.feature_store.request_source import RequestSource
from snowflake.snowpark import Session
from snowflake.snowpark.types import (
    DoubleType,
    StringType,
    StructField,
    StructType,
)

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------
CONNECTION_NAME = "{connection_name}"
DATABASE        = "{database}"
SCHEMA          = "{schema}"
WAREHOUSE       = "{warehouse}"

FV_NAME    = "{FV_NAME}"                # name + version ≤ 45 chars combined (max 43 with V1)
FV_VERSION = "V1"

ENTITY_NAME      = "{entity_name}"       # ≤ 32 chars
ENTITY_JOIN_KEYS = ["{entity_col}"]

# Upstream feature views to join against (must be registered + online-enabled)
UPSTREAM_FV_NAMES = [("{upstream_fv_name}", "{upstream_fv_version}")]

# Request-time input schema (columns the caller supplies per request)
REQUEST_SCHEMA = StructType([
{request_schema_fields}
])

# Output schema (columns compute_fn returns) — use ALL-CAPS names
OUTPUT_SCHEMA = StructType([
{output_schema_fields}
])


# ---------------------------------------------------------------------------
# compute_fn — must be a single module-level named def.
# Column names must be ALL-CAPS to match Snowflake's normalization.
# Available without importing: pd, np, re, copy.
# ---------------------------------------------------------------------------
def {compute_fn_name}({param_names}) -> pd.DataFrame:
{compute_fn_body}


def main() -> int:
    session = Session.builder.configs({"connection_name": CONNECTION_NAME}).getOrCreate()
    session.sql(f"USE WAREHOUSE {WAREHOUSE}").collect()
    session.sql(f"USE DATABASE {DATABASE}").collect()
    session.sql(f"USE SCHEMA {SCHEMA}").collect()

    fs = FeatureStore(
        session=session,
        database=DATABASE,
        name=SCHEMA,
        default_warehouse=WAREHOUSE,
        creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
    )

    entity = Entity(name=ENTITY_NAME, join_keys=ENTITY_JOIN_KEYS)
    fs.register_entity(entity)

    # Retrieve upstream feature view(s)
    sources = []
    request_source = RequestSource(schema=REQUEST_SCHEMA)
    sources.append(request_source)
    for fv_name, fv_version in UPSTREAM_FV_NAMES:
        sources.append(fs.get_feature_view(fv_name, fv_version))

    realtime_config = RealtimeConfig(
        compute_fn={compute_fn_name},
        sources=sources,
        output_schema=OUTPUT_SCHEMA,
    )

    draft_fv = FeatureView(
        name=FV_NAME,
        entities=[entity],
        realtime_config=realtime_config,
        desc="Real-time computed feature view",
    )
    registered = fs.register_feature_view(draft_fv, FV_VERSION)
    print(f"Registered {registered.name}/{registered.version} (status={registered.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Filling in `{compute_fn_body}`

The function receives one positional argument per source (in `sources` order: `RequestSource`
first if present, then upstream FVs). Each argument is a `pd.DataFrame`. Return a
`pd.DataFrame` matching `OUTPUT_SCHEMA` with ALL-CAPS column names.

**If the user describes the computation**, translate it. Example:

```python
def risk_score(req, txn_features) -> pd.DataFrame:
    output_df = pd.DataFrame({
        "RISK_SCORE": req["AMOUNT"] / (txn_features["AVG_AMOUNT"] + 1),
        "RISK_BUCKET": ["high" if s > 0.8 else "low" for s in req["AMOUNT"] / (txn_features["AVG_AMOUNT"] + 1)],
    })
    output_df.columns = [c.upper() for c in output_df.columns]
    return output_df
```

**If no `RequestSource`** is needed, make three changes to the template:

1. Remove the `REQUEST_SCHEMA` constant entirely.
2. Change the sources setup to pass only the upstream FV(s) directly:

```python
    sources = []
    for fv_name, fv_version in UPSTREAM_FV_NAMES:
        sources.append(fs.get_feature_view(fv_name, fv_version))

    realtime_config = RealtimeConfig(
        compute_fn={compute_fn_name},
        sources=sources,
        output_schema=OUTPUT_SCHEMA,
    )
```

3. Drop the request parameter from `compute_fn` — one positional arg per upstream FV only:

```python
def {compute_fn_name}(upstream_fv: pd.DataFrame) -> pd.DataFrame:
    ...
```

Also remove `from snowflake.ml.feature_store.request_source import RequestSource` from the imports if it is no longer used.

If the user's computation logic is unclear, ask with `AskQuestion`:

```
What should the real-time feature view compute?
- Describe the input columns and the output calculation
- Example: "divide request amount by the user's average transaction amount from the upstream FV"
```

---

## Run Command

```bash
pip install snowflake-ml-python
python create_{fv_name}.py
```

## Output

A single `create_{fv_name}.py` file the customer edits (constants block) and runs directly.
