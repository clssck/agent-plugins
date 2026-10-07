---
name: feature-store-tecton-feature-group
description: "Generate a standalone Python script to register a Snowflake Feature Store Feature Group (FeatureGroup). Feature Groups combine multiple online-enabled FeatureViews into a single Postgres Online Feature Table for co-located low-latency reads. Use when the user says: 'feature group', 'group feature views', 'combine FVs into one OFT', 'co-located online features', or wants to serve multiple FVs from a single low-latency table."
parent_skill: feature-store-tecton
path: machine-learning/feature-store/migrate/tecton/feature-group
---
# Feature Group Script Generation

A Feature Group combines multiple registered, online-enabled FeatureViews into one
Postgres Online Feature Table (OFT). The OFT's primary key is the ordered union of
the source FVs' join keys, so sources may join at different grains (coarser sources
broadcast over the wider key).

## When to Load

Main skill (`../SKILL.md`) Step 1 classifies the artifact as a **Feature Group**:
user says "feature group", "group feature views", "combine FVs into one OFT",
"co-located online features", or wants to serve multiple FVs from a single
low-latency table.

## Prerequisites

- All source FeatureViews must be:
  - Already registered in the Feature Store
  - Online-enabled (SFVs are online by default via `stream_config`; RTFVs are always
    online; BFVs require explicit `OnlineConfig(enable=True)`)
  - Using Postgres store type
- Source FVs and their join keys known

---

## Extract Required Fields

Ask with `AskQuestion` for any missing fields (all in one call):

- **Feature Group name**: Identifier for the group (max 255 chars, no `$` delimiter)
- **Source feature views**: List of registered FV names + versions to include
- **Auto-prefix**: Whether to prefix output columns with `<FV_NAME>_<FV_VERSION>_`
  (default: `True` — prevents column name collisions across FVs)

---

## Constraints

See `../reference.md` § "FeatureGroup" for constraints (RTFV-source restriction,
Postgres store requirement, `auto_prefix` default).

- **`auto_prefix` override**: Use `fv.with_name("custom_prefix")` on individual FVs to
  override specific prefixes. Set `auto_prefix=False` only when you're certain there are
  no column name collisions across source FVs.

---

## Generate the Script

**⚠️ MANDATORY STOPPING POINT**: Before writing, present a summary for approval:

```
I'll generate create_{fg_name}.py with these settings:
- FG name:       {FG_NAME}
- Version:       V1
- Source FVs:    {list of (fv_name, version) tuples}
- Auto-prefix:   True/False
- Description:   {desc}

Shall I write the file?
```

Wait for explicit approval before proceeding.

Write the file with `Write`. Default location: the user's current directory (or wherever they indicate).

### Template: Feature Group script

```python
#!/usr/bin/env python3
"""Create feature group: {FG_NAME}

Prerequisites:
    pip install snowflake-ml-python
    All source feature views must already be registered and online-enabled
    with Postgres store type.

Run:
    python {filename}.py
"""

from snowflake.ml.feature_store import (
    CreationMode,
    FeatureStore,
)
from snowflake.ml.feature_store.feature_group import FeatureGroup
from snowflake.snowpark import Session

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------
CONNECTION_NAME = "{connection_name}"
DATABASE        = "{database}"
SCHEMA          = "{schema}"
WAREHOUSE       = "{warehouse}"

FG_NAME    = "{FG_NAME}"                # ≤ 255 chars
FG_VERSION = "V1"

# Source feature views (must be registered + online-enabled + Postgres store)
SOURCE_FVS = [
{source_fv_lines}
]

AUTO_PREFIX = True   # prefix output columns with "<FV_NAME>_<FV_VERSION>_"
DESC        = "{desc}"


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

    # Retrieve source feature views
    features = []
    for fv_name, fv_version in SOURCE_FVS:
        features.append(fs.get_feature_view(fv_name, fv_version))

    fg = FeatureGroup(
        name=FG_NAME,
        features=features,
        desc=DESC,
        auto_prefix=AUTO_PREFIX,
    )
    registered = fs.register_feature_group(fg, FG_VERSION)
    print(f"Registered FeatureGroup: {registered.name}/{registered.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Filling in `{source_fv_lines}`

One `(name, version)` tuple per source FV, indented 4 spaces:

```python
    ("USER_TRANSACTION_FV", "V1"),
    ("USER_PROFILE_FV", "V2"),
    ("MERCHANT_RISK_FV", "V1"),
```

---

## Run Command

```bash
pip install snowflake-ml-python
python create_{fg_name}.py
```

## Output

A single `create_{fg_name}.py` file the customer edits (constants block) and runs directly.
