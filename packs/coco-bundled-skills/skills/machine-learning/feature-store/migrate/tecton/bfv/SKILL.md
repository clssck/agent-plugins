---
name: feature-store-tecton-bfv
description: "Generate a standalone Python script for a Snowflake Feature Store batch feature view (BFV) from a Tecton @batch_feature_view spec or natural language."
parent_skill: feature-store-tecton
path: machine-learning/feature-store/migrate/tecton/bfv
---
# BFV Script Generation

## When to Load

Main skill (`../SKILL.md`) Step 1 classifies the artifact as a **Batch Feature View**.

## Prerequisites

- Main skill's Step 2 field extraction is complete (entity, timestamp, source table, aggregations known)
- Main skill's Step 4 smart defaults computed (`FEATURE_GRANULARITY`, `refresh_freq`)

---

## BFV-Specific Defaults

### `OnlineConfig`

- Tecton `online=True` → include `online_config=OnlineConfig(enable=True)` (optionally `target_lag="..."`).
- Tecton `online=False` (or not set) → **omit `online_config` entirely** (the SDK default is offline-only).
  Also remove `OnlineConfig` from the imports if unused.

### Source columns (`feature_df`)

The customer's `SOURCE_TABLE` must already contain the entity column, timestamp column, and
every `source_column` referenced by the aggregations. Do not synthesize data.

---

## Generate the Script

**⚠️ MANDATORY STOPPING POINT**: Before writing, present a summary for approval:

```
I'll generate create_{fv_name}.py with these settings:
- FV name:        {FV_NAME}
- Entity:         {entity_name} (join key: {entity_col})
- Source table:    {source_table}
- Timestamp col:  {timestamp_col}
- Granularity:    {granularity}
- Refresh freq:   {refresh_freq}
- Features:       {list of Feature.<fn>(col, window) calls}

Shall I write the file?
```

Wait for explicit approval before proceeding.

Write the file with `Write`. Default location: the user's current directory (or wherever they indicate).

### Template: BFV script

```python
#!/usr/bin/env python3
"""Create batch feature view: {FV_NAME}
Translated from Tecton @batch_feature_view: {original_fn_name}  (if applicable)

Prerequisites:
    pip install snowflake-ml-python
    A source table/view ({source_table}) containing the entity, timestamp, and
    all aggregated columns.

Run:
    python {filename}.py
"""

from snowflake.ml.feature_store import (
    CreationMode,
    Entity,
    Feature,
    FeatureStore,
    FeatureView,
    OnlineConfig,
)
from snowflake.snowpark import Session

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------
CONNECTION_NAME = "{connection_name}"   # a connection defined in ~/.snowflake/connections.toml
DATABASE        = "{database}"
SCHEMA          = "{schema}"
WAREHOUSE       = "{warehouse}"

FV_NAME    = "{FV_NAME}"                # name + version ≤ 45 chars combined (max 43 with V1)
FV_VERSION = "V1"

SOURCE_TABLE  = "{source_table}"        # fully-qualified existing feature source table/view
ENTITY_NAME   = "{entity_name}"         # ≤ 32 chars
ENTITY_JOIN_KEYS = ["{entity_col}"]
TIMESTAMP_COL = "{timestamp_col}"

FEATURE_GRANULARITY = "{granularity}"   # tile size; divides every window, <= smallest window, >= 1m
REFRESH_FREQ        = "{refresh_freq}"  # offline refresh cadence (from Tecton batch_schedule)


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

    feature_df = session.table(SOURCE_TABLE)

    draft_fv = FeatureView(
        name=FV_NAME,
        entities=[entity],
        feature_df=feature_df,
        timestamp_col=TIMESTAMP_COL,
        refresh_freq=REFRESH_FREQ,
        feature_granularity=FEATURE_GRANULARITY,
        features=[
{agg_feature_lines}
        ],
        # Include online_config only when Tecton spec has online=True; omit for offline-only BFVs.
        online_config=OnlineConfig(enable=True),
        desc="Generated from a Tecton batch_feature_view",
    )
    registered = fs.register_feature_view(draft_fv, FV_VERSION)
    print(f"Registered {registered.name}/{registered.version} (status={registered.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Fill in `{agg_feature_lines}` per the main skill's "Filling in `{agg_feature_lines}`" section.

---

## Run Command

```bash
pip install snowflake-ml-python
python create_{fv_name}.py
```

## Output

A single `create_{fv_name}.py` file the customer edits (constants block) and runs directly.
