---
name: feature-store-tecton-stream-source
description: "Generate a standalone Python script to register a Snowflake Feature Store StreamSource from a Tecton StreamSource/BatchSource definition."
parent_skill: feature-store-tecton
path: machine-learning/feature-store/migrate/tecton/stream-source
---
# Stream Source Script Generation

## When to Load

- Main skill (`../SKILL.md`) Step 1 classifies the artifact as a **Stream Source**, or
- SFV sub-skill (`../sfv/SKILL.md`) determines a new stream source must be created before the SFV.

## Prerequisites

- Stream-source name known (≤ 32 characters, SDK limit)
- Column schema known (from Tecton `StreamSource` spec or user description)

---

## Generate the Script

**⚠️ MANDATORY STOPPING POINT**: Before writing, present a summary for approval:

```
I'll generate create_{source_name}.py with these settings:
- Source name:  {SOURCE_NAME} (≤ 32 chars)
- Columns:     {list of StructField(name, type) entries}
- Description: {desc}

Shall I write the file?
```

Wait for explicit approval before proceeding.

Write the file with `Write`. Default location: the user's current directory (or wherever they indicate).

### Template: Stream source script

```python
#!/usr/bin/env python3
"""Register stream source: {SOURCE_NAME}
Translated from Tecton StreamSource: {original_source_name}  (if applicable)

Prerequisites:
    pip install snowflake-ml-python

Run:
    python {filename}.py

Note: a StreamSource with active FeatureView references cannot be deleted. Delete all
referencing feature views first if you need to re-register it.
"""

from snowflake.ml.feature_store import CreationMode, FeatureStore, StreamSource
from snowflake.snowpark import Session
from snowflake.snowpark.types import (
    BooleanType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampTimeZone,
    TimestampType,
)

# ---------------------------------------------------------------------------
# Configuration — edit these before running
# ---------------------------------------------------------------------------
CONNECTION_NAME = "{connection_name}"
DATABASE        = "{database}"
SCHEMA          = "{schema}"
WAREHOUSE       = "{warehouse}"

SOURCE_NAME = "{SOURCE_NAME}"           # <= 32 characters
DESC        = "{desc}"

# Include only the columns actually referenced by feature views on this source
# (entity + timestamp + aggregated + filter columns). Types must be Feature Store
# supported: StringType, LongType, DoubleType, DecimalType, BooleanType, BinaryType,
# TimestampType (TIMESTAMP_NTZ only).
SCHEMA_FIELDS = StructType([
{schema_field_lines}
])


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

    stream_source = StreamSource(name=SOURCE_NAME, schema=SCHEMA_FIELDS, desc=DESC)
    fs.register_stream_source(stream_source)
    print(f"Registered StreamSource: {SOURCE_NAME} ({len(SCHEMA_FIELDS.fields)} columns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

### Filling in `{schema_field_lines}`

One `StructField` per column, indented 4 spaces:

```python
    StructField("OriginVehicleId", StringType()),
    StructField("EventTimestamp", TimestampType(TimestampTimeZone.NTZ)),
    StructField("RoadZoneRegion", StringType()),
    StructField("TripDirection", StringType()),
    StructField("TripType", StringType()),
```

### Tecton type → Snowpark type

See `../reference.md` § "Tecton type → Snowpark type" for the full type mapping table.
Only `TIMESTAMP_NTZ` is allowed in stream-source schemas; all timestamps are stored as UTC.

---

## Run Command

```bash
pip install snowflake-ml-python
python create_{source_name}.py
```

## Output

A single `create_{source_name}.py` file the customer edits (constants block) and runs directly.

## Next

If this stream source was generated as a prerequisite for an SFV, return to
`../sfv/SKILL.md` to generate the SFV script.
