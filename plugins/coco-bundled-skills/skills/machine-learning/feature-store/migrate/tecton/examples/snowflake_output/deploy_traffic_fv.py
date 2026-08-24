#!/usr/bin/env python3
"""Deploy the example traffic stream feature view to Snowflake Feature Store.

Customer-facing output of translating two Tecton specs:
  - tecton_input/traffic_stream_source.py   (Tecton StreamSource)
  - tecton_input/traffic_feature_view.py    (Tecton @stream_feature_view)

It registers, in order: StreamSource -> Entity -> stream FeatureView, and points
the backfill DataFrame at a real historical table. No synthetic data is
generated; edit the CONFIG block, then run:

    pip install snowflake-ml-python
    python snowflake_output/deploy_traffic_fv.py

Feature view being deployed:
    ORIGIN_VEHICLE_LDN_ROAD_ZONE_OUTBOUND
    Entity:    OriginVehicleId
    Timestamp: EventTimestamp
    Feature:   last_distinct(8)(RoadZoneRegion, 24h) — outbound highway trips only
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
from snowflake.snowpark.types import (
    StringType,
    StructField,
    StructType,
    TimestampTimeZone,
    TimestampType,
)

# ===========================================================================
# CONFIG — edit before running
# ===========================================================================
CONNECTION_NAME = "<connection>"   # a connection defined in ~/.snowflake/connections.toml
DATABASE        = "<DATABASE>"
SCHEMA          = "<SCHEMA>"        # feature store schema (created if needed)
WAREHOUSE       = "<WAREHOUSE>"

STREAM_SOURCE_NAME = "EXAMPLE_TRAFFIC_SRC"   # <= 32 characters

FV_NAME    = "ORIGIN_VEHICLE_LDN_ROAD_ZONE_OUTBOUND"
FV_VERSION = "V1"
REFRESH_FREQ = "1 hour"  # Tecton spec has batch_schedule=1 day, but continuous SFVs benefit from a faster offline refresh

ENTITY_NAME      = "origin_vehicle_id_entity"
ENTITY_JOIN_KEYS = ["OriginVehicleId"]
TIMESTAMP_COL    = "EventTimestamp"
FEATURE_GRANULARITY = "16m"          # 24h / 90 = 16m; divides 24h evenly (90 tiles), >= 1m

# Fully-qualified permanent table with historical rows for the initial backfill.
# Must contain at least the entity, timestamp, and filter/aggregation columns;
# Must contain at least the columns referenced by the feature view.
BACKFILL_TABLE = "<DATABASE>.<SCHEMA>.HISTORICAL_TRAFFIC"


# ===========================================================================
# Transform — module-level named def (StreamConfig serializes it via
# inspect.getsource(); no lambda/nested def). Column names are ALL-CAPS because
# Snowflake stores unquoted identifiers as uppercase.
# ===========================================================================
def _transform(df: pd.DataFrame) -> pd.DataFrame:
    df = df[
        (df["ROADZONEREGION"] != "")
        & (df["ORIGINVEHICLEID"] != "")
        & (df["TRIPDIRECTION"] == "outbound")
        & (df["TRIPTYPE"] == "highway")
    ]
    return df[["ORIGINVEHICLEID", "EVENTTIMESTAMP", "ROADZONEREGION"]]


# Stream-source schema: only the columns referenced by this feature view
# (entity + timestamp + aggregation + filter columns). Add more only if other
# feature views on the same source need them.
STREAM_SOURCE_SCHEMA = StructType(
    [
        StructField("OriginVehicleId", StringType()),
        StructField("EventTimestamp", TimestampType(TimestampTimeZone.NTZ)),
        StructField("RoadZoneRegion", StringType()),
        StructField("TripDirection", StringType()),
        StructField("TripType", StringType()),
    ]
)


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

    # Register the stream source (idempotent for a fresh schema).
    from snowflake.ml.feature_store import StreamSource

    fs.register_stream_source(
        StreamSource(name=STREAM_SOURCE_NAME, schema=STREAM_SOURCE_SCHEMA, desc="Traffic events")
    )
    stream_source = fs.get_stream_source(STREAM_SOURCE_NAME)

    # Build the backfill DataFrame from a permanent table (must survive a fresh session).
    backfill_df = session.table(BACKFILL_TABLE)

    # Cast the entity join-key to unbounded VARCHAR to avoid length-bounded type mismatches.
    entity_col_upper = ENTITY_JOIN_KEYS[0].upper()
    for field in backfill_df.schema.fields:
        if field.name.upper() == entity_col_upper:
            backfill_df = backfill_df.with_column(field.name, col(field.name).cast(StringType()))
            break

    entity = Entity(name=ENTITY_NAME, join_keys=ENTITY_JOIN_KEYS)
    fs.register_entity(entity)

    stream_config = StreamConfig(
        stream_source=STREAM_SOURCE_NAME,
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
            Feature.last_distinct_n("RoadZoneRegion", "24h", n=8),
        ],
        feature_aggregation_method=FeatureAggregationMethod.CONTINUOUS,
        desc="Generated from a Tecton stream_feature_view",
    )
    registered = fs.register_feature_view(draft_fv, FV_VERSION)
    print(f"Registered {registered.name}/{registered.version} (status={registered.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
