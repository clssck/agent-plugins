---
name: feature-store-tecton-sfv
description: "Generate a standalone Python script for a Snowflake Feature Store stream feature view (SFV) from a Tecton @stream_feature_view spec or natural language."
parent_skill: feature-store-tecton
path: machine-learning/feature-store/migrate/tecton/sfv
---
# SFV Script Generation

## When to Load

Main skill (`../SKILL.md`) Step 1 classifies the artifact as a **Stream Feature View**.

## Prerequisites

- Main skill's Step 2 field extraction is complete (entity, timestamp, stream source, backfill table, aggregations known)
- Main skill's Step 4 smart defaults computed (`FEATURE_GRANULARITY`, `refresh_freq`)

---

## Stream Source Check

An SFV requires a registered `StreamSource`. Ask the user whether the source already
exists:

```
Does the stream source '{X}' already exist in your Feature Store?
- Yes, it's already registered (I'll reference it by name)
- No, generate a create_{X}.py stream-source script first
```

If it must be created, **Load** `../stream-source/SKILL.md` and generate the stream-source
script first. The stream-source name must be **≤ 32 characters** (SDK limit).

---

## SFV-Specific Defaults

### `feature_aggregation_method`

- Tecton `StreamProcessingMode.CONTINUOUS` → `FeatureAggregationMethod.CONTINUOUS`
- Otherwise → `FeatureAggregationMethod.TILES` (SDK default; may be omitted)

### `OnlineConfig`

SFV via `stream_config`: online storage is always enabled with the Postgres store type,
so `online_config` is optional; include `OnlineConfig(enable=True, store_type=OnlineStoreType.POSTGRES)`
only when you want it explicit.

### `_transform` column names

Snowflake stores unquoted identifiers as uppercase — use uppercase column names in the transform:
- `OriginVehicleId` → `"ORIGINVEHICLEID"`, `EventTimestamp` → `"EVENTTIMESTAMP"`
- The transform selects `[ENTITY_COL.upper(), TIMESTAMP_COL.upper(), *{source_col.upper()}]`
  after applying the filters.

---

## Critical Constraints

### Transform placement

See main skill's "Transform Rules" section — the transform must be a module-level named `def`
(not nested in `main()`), no lambda/nested def, importing only from `numpy`, `pandas`, `re`, `copy`, `dataclasses`.

### Backfill DataFrame

> **`backfill_df` is required by the SDK** (`StreamConfig` raises `ValueError: backfill_df is required.` if it is `None`). There is no way to create an SFV without one.
>
> It must also contain **at least one row** — registration does a `.limit(10).to_pandas()` probe to infer the output schema from `transformation_fn`, and raises `ValueError: Backfill probe returned zero rows.` if the table is empty.

**Ask the user which situation applies before generating:**

```
Do you have a historical table with past event data to backfill from?
- Yes — provide the fully-qualified table name (MY_DB.MY_SCHEMA.MY_TABLE)
- No — I want to register the SFV now and only accumulate live data going forward (use a stub backfill)
```

**Never invent or hallucinate a table name.**

> **⚠️ The SDK validates that `backfill_df` contains every column declared in the
> StreamSource schema** — not just the columns the `_transform` uses or the FV aggregates.
> This applies to both paths below. Missing any StreamSource column raises:
> `ValueError: streaming feature view: backfill_df is missing column 'X' declared by StreamSource 'Y'.`

#### Path A — Historical table (preferred)

`backfill_df` is built from a permanent Snowflake table. `backfill_df` is only used during
`register_feature_view()` — it is not stored afterward — but using a permanent table keeps
the registration script safely re-runnable.

```python
BACKFILL_TABLE = "MY_DB.MY_SCHEMA.MY_HISTORICAL_EVENTS"  # fully-qualified, user-supplied
backfill_df = session.table(BACKFILL_TABLE)
```

Cast the entity join-key to unbounded `StringType()` to prevent length-bounded `VARCHAR(N)`
join-key validation failures:

```python
from snowflake.snowpark.functions import col
from snowflake.snowpark.types import StringType

entity_col_upper = ENTITY_JOIN_KEYS[0].upper()
for field in backfill_df.schema.fields:
    if field.name.upper() == entity_col_upper:
        backfill_df = backfill_df.with_column(field.name, col(field.name).cast(StringType()))
        break
```

#### Path B — Stub backfill (no historical data yet)

When the user has no historical table, generate a minimal in-memory stub that satisfies the
schema probe. `session.create_dataframe()` re-creates the data on every run, so the script
remains re-runnable. The SFV registers with no historical features backfilled and starts
accumulating live data from registration onwards.

**The stub schema must be a complete mirror of the StreamSource's `StructType`** (see
column-completeness warning above). Use a zero-value stub for each type: `""` for strings,
`0.0` for doubles, `0` for longs, `False` for booleans, `datetime(2020, 1, 1)` for timestamps.

```python
from datetime import datetime
from snowflake.snowpark.types import (
    BooleanType, DoubleType, LongType, StringType,
    StructField, StructType, TimestampType, TimestampTimeZone,
)

# IMPORTANT: include ALL columns from the StreamSource schema, not just the
# ones used by _transform or the aggregations. The SDK validates backfill_df
# against the full StreamSource schema.
_STUB_SCHEMA = StructType([
    StructField("{COL_1}", StringType()),      # e.g. entity column
    StructField("{COL_2}", TimestampType(TimestampTimeZone.NTZ)),  # e.g. timestamp column
    StructField("{COL_3}", StringType()),      # e.g. filter/agg column
    # ... one StructField per StreamSource column, matching name and type exactly ...
])
_STUB_DATA = [("{stub_val}", datetime(2020, 1, 1), "", ...)]  # one zero/empty value per column

backfill_df = session.create_dataframe(_STUB_DATA, schema=_STUB_SCHEMA)
```

Generate one `StructField` per StreamSource column — copy the exact field names and types
from `STREAM_SOURCE_SCHEMA`. Use zero-value stubs: `""` for strings, `0` for longs, `0.0`
for doubles, `False` for booleans, `datetime(2020, 1, 1)` for timestamps. No cast loop is
needed for the stub path since `StringType()` is already unbounded.

---

## Generate the Script

**⚠️ MANDATORY STOPPING POINT**: Before writing, present a summary for approval:

```
I'll generate create_{fv_name}.py with these settings:
- FV name:           {FV_NAME}
- Entity:            {entity_name} (join key: {entity_col})
- Stream source:     {STREAM_SOURCE}
- Backfill:          {MY_DB.MY_SCHEMA.MY_TABLE  |  stub (no historical data)}
- Timestamp col:     {timestamp_col}
- Granularity:       {granularity}
- Refresh freq:      {refresh_freq}
- Aggregation mode:  CONTINUOUS / TILES
- Features:          {list of Feature.<fn>(col, window) calls}
- Transform:         {brief description of filter + select logic}

Shall I write the file?
```

Wait for explicit approval before proceeding.

Write the file with `Write`. Default location: the user's current directory (or wherever they indicate).

### Template: SFV script

```python
#!/usr/bin/env python3
"""Create stream feature view: {FV_NAME}
Translated from Tecton @stream_feature_view: {original_fn_name}  (if applicable)

Prerequisites:
    pip install snowflake-ml-python
    Stream source {STREAM_SOURCE} must already be registered (see create_{stream_source}.py).
    A historical backfill table/view ({backfill_table}) containing the entity, timestamp, and
    all aggregated/filter columns.

Run:
    python {filename}.py
"""

import pandas as pd
from snowflake.ml.feature_store import (
    CreationMode,
    Entity,
    Feature,
    FeatureAggregationMethod,
    FeatureStore,
    FeatureView,
)
from snowflake.ml.feature_store.stream_config import StreamConfig
from snowflake.snowpark import Session
from snowflake.snowpark.functions import col
from snowflake.snowpark.types import StringType

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------
CONNECTION_NAME = "{connection_name}"
DATABASE        = "{database}"
SCHEMA          = "{schema}"
WAREHOUSE       = "{warehouse}"

FV_NAME        = "{FV_NAME}"             # name + version ≤ 45 chars combined (max 43 with V1)
FV_VERSION     = "V1"
STREAM_SOURCE  = "{STREAM_SOURCE}"      # must already be registered; name ≤ 32 chars
BACKFILL_TABLE = "{backfill_table}"     # fully-qualified permanent table with historical data

ENTITY_NAME      = "{entity_name}"       # ≤ 32 chars
ENTITY_JOIN_KEYS = ["{entity_col}"]
TIMESTAMP_COL    = "{timestamp_col}"

FEATURE_GRANULARITY = "{granularity}"
REFRESH_FREQ        = "{refresh_freq}"


# ---------------------------------------------------------------------------
# Transform — must be a module-level named function for inspect.getsource().
# Mirrors the Tecton inline filter+select. Column names are ALL-CAPS because
# Snowflake stores unquoted identifiers uppercase.
# ---------------------------------------------------------------------------
def _transform(df: pd.DataFrame) -> pd.DataFrame:
{transform_body}


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

    # Path A: backfill from a permanent table.
    # For Path B (stub backfill), replace this block — see "Backfill DataFrame" section above.
    backfill_df = session.table(BACKFILL_TABLE)

    # Cast entity join-key to unbounded VARCHAR to prevent length-bounded type mismatches.
    entity_col_upper = ENTITY_JOIN_KEYS[0].upper()
    for field in backfill_df.schema.fields:
        if field.name.upper() == entity_col_upper:
            backfill_df = backfill_df.with_column(field.name, col(field.name).cast(StringType()))
            break

    entity = Entity(name=ENTITY_NAME, join_keys=ENTITY_JOIN_KEYS)
    fs.register_entity(entity)

    stream_config = StreamConfig(
        stream_source=STREAM_SOURCE,
        transformation_fn=_transform,
        backfill_df=backfill_df,
    )

    draft_fv = FeatureView(
        name=FV_NAME,
        entities=[entity],
        stream_config=stream_config,
        timestamp_col=TIMESTAMP_COL,
        refresh_freq=REFRESH_FREQ,
        feature_granularity=FEATURE_GRANULARITY,
        features=[
{agg_feature_lines}
        ],
        feature_aggregation_method=FeatureAggregationMethod.{CONTINUOUS_or_TILES},
        desc="Generated from a Tecton stream_feature_view",
    )
    registered = fs.register_feature_view(draft_fv, FV_VERSION)
    print(f"Registered {registered.name}/{registered.version} (status={registered.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Path B template substitutions

When generating for Path B (stub backfill), apply these changes to the template above:

**1. Imports** — add `datetime` and expanded Snowpark types; remove `col` (unused in Path B):

```python
from datetime import datetime
# (keep all other imports unchanged)
from snowflake.snowpark.types import (
    BooleanType, DoubleType, LongType, StringType,
    StructField, StructType, TimestampType, TimestampTimeZone,
)
```

Remove `from snowflake.snowpark.functions import col`.

**2. Config** — remove `BACKFILL_TABLE`. Update the docstring prerequisites to say
"No historical backfill table required; a stub schema is used."

**3. Module-level constants** — add after the config block, before `_transform`:

```python
# Stub backfill — mirrors ALL columns from STREAM_SOURCE_SCHEMA.
# The SDK validates backfill_df against the full StreamSource schema.
_STUB_SCHEMA = StructType([
    StructField("{COL_1}", StringType()),
    StructField("{COL_2}", TimestampType(TimestampTimeZone.NTZ)),
    StructField("{COL_3}", StringType()),
    # ... one StructField per StreamSource column, matching name and type exactly ...
])
_STUB_DATA = [("{stub}", datetime(2020, 1, 1), "", ...)]  # one zero/empty value per column
```

**4. Backfill block in `main()`** — replace the `# Path A` block (from `backfill_df = session.table(...)` through the cast loop) with:

```python
    # Path B: stub backfill — no historical data; live data accumulates from registration.
    backfill_df = session.create_dataframe(_STUB_DATA, schema=_STUB_SCHEMA)
```

No entity join-key cast needed — `StringType()` in the stub schema is already unbounded.

---

**Fill in `{CONTINUOUS_or_TILES}`** — use `CONTINUOUS` when the Tecton spec has
`stream_processing_mode=StreamProcessingMode.CONTINUOUS`; use `TILES` (or omit the parameter
entirely, since `TILES` is the SDK default) otherwise.

**Fill in `{transform_body}`** — `transformation_fn` is required by `StreamConfig` (cannot be omitted).
Use ALL-CAPS column names throughout (Snowflake uppercases unquoted identifiers), indented 4 spaces.

**If the Tecton spec has inline filter/select logic**, translate it:

```python
    # Example: traffic spec filters on direction/type, selects entity + timestamp + agg columns
    df = df[
        (df["ROADZONEREGION"] != "")
        & (df["ORIGINVEHICLEID"] != "")
        & (df["TRIPDIRECTION"] == "outbound")
        & (df["TRIPTYPE"] == "highway")
    ]
    return df[["ORIGINVEHICLEID", "EVENTTIMESTAMP", "ROADZONEREGION"]]
```

**If no filter logic is provided** (natural language request or the Tecton spec has no function body),
default to selecting only the columns the FV needs:

```python
    return df[["ENTITY_COL", "TIMESTAMP_COL", "AGG_SOURCE_COL_1", "AGG_SOURCE_COL_2"]]
```

If the user's intent is unclear, ask with `AskQuestion`:

```
The stream feature view needs a transform function. Does your data need any
filtering before aggregation (e.g. exclude empty values, filter by status)?
- No filtering — just select the relevant columns
- Yes — [describe the filter conditions]
```

Fill in `{agg_feature_lines}` per the main skill's "Filling in `{agg_feature_lines}`" section.

---

## Run Commands

```bash
pip install snowflake-ml-python

# Register the stream source first (if not already registered)
python create_{stream_source}.py

# Then create the feature view
python create_{fv_name}.py
```

If the stream source was newly generated in this session, show both commands in order and
emphasize the prerequisite.

## Output

One or two files:
- `create_{stream_source}.py` (if stream source was generated — see `../stream-source/SKILL.md`)
- `create_{fv_name}.py` (the SFV script)
