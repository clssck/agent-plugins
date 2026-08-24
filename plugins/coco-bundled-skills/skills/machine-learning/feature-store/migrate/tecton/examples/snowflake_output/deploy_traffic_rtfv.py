#!/usr/bin/env python3
"""Deploy a RealtimeFeatureView to Snowflake Feature Store.

Customer-facing output of translating one more Tecton spec on top of the
``deploy_traffic_fv.py`` example:
  - tecton_input/traffic_realtime_feature_view.py  (Tecton @realtime_feature_view)

Concept mapping (Tecton -> Snowflake):
  RequestSource(schema=[Field(...)])            -> RequestSource(schema=StructType([StructField(...)]))
                                                     (snowflake.ml.feature_store.request_source.RequestSource)
  @realtime_feature_view(sources=[...],           -> RealtimeConfig(compute_fn=..., sources=[...],
    mode="python", features=[Attribute(...)])         output_schema=StructType([...]))
                                                     + FeatureView(realtime_config=..., entities=[...])
  def f(request_src, upstream_fv):                -> def compute_fn(req: pd.DataFrame, upstream: pd.DataFrame)
    (Tecton passes one dict-like row per source,      (Snowflake passes one pandas DataFrame per source, in the
     same positional order as `sources`)               same positional order as RealtimeConfig.sources; vectorized
                                                        over all requested keys, not row-by-row)
  Attribute("Name", Type)                         -> StructField("NAME", <SnowparkType>) in output_schema
                                                     (Snowflake normalizes column names to uppercase)

Prerequisite: ORIGIN_VEHICLE_LDN_ROAD_ZONE_OUTBOUND/V1 must already be
registered and online-enabled — run ``deploy_traffic_fv.py`` first.

Run:
    pip install snowflake-ml-python
    python snowflake_output/deploy_traffic_rtfv.py

    # Then combine it with the upstream SFV into a FeatureGroup:
    python snowflake_output/deploy_traffic_fg.py

Feature view being deployed:
    RTFV: ORIGIN_VEHICLE_ROAD_ZONE_FAMILIARITY/V1
        Request input:  CurrentRoadZoneRegion (string)
        Upstream FV:    ORIGIN_VEHICLE_LDN_ROAD_ZONE_OUTBOUND/V1
        Output:         IsRoadZoneFamiliar (boolean) — is CurrentRoadZoneRegion
                         in the vehicle's last-8-distinct outbound road zones?
"""

import pandas as pd

from snowflake.ml.feature_store import CreationMode, Entity, FeatureStore, FeatureView
from snowflake.ml.feature_store.realtime_config import RealtimeConfig
from snowflake.ml.feature_store.request_source import RequestSource
from snowflake.snowpark import Session
from snowflake.snowpark.types import BooleanType, StringType, StructField, StructType

# ===========================================================================
# CONFIG — edit before running
# ===========================================================================
CONNECTION_NAME = "<connection>"  # a connection defined in ~/.snowflake/connections.toml
DATABASE = "<DATABASE>"
SCHEMA = "<SCHEMA>"  # feature store schema (same one deploy_traffic_fv.py used)
WAREHOUSE = "<WAREHOUSE>"

UPSTREAM_FV_NAME = "ORIGIN_VEHICLE_LDN_ROAD_ZONE_OUTBOUND"
UPSTREAM_FV_VERSION = "V1"

ENTITY_NAME = "origin_vehicle_id_entity"  # must match deploy_traffic_fv.py's entity
ENTITY_JOIN_KEYS = ["OriginVehicleId"]

RTFV_NAME = "ORIGIN_VEHICLE_ROAD_ZONE_FAMILIARITY"
RTFV_VERSION = "V1"

# Request-time input schema (columns the caller supplies per request).
# Column names must be ALL-CAPS to match Snowflake's normalization.
REQUEST_SCHEMA = StructType(
    [
        StructField("CURRENTROADZONEREGION", StringType()),
    ]
)

# Output schema (columns compute_fn returns) — use ALL-CAPS names.
OUTPUT_SCHEMA = StructType(
    [
        StructField("ISROADZONEFAMILIAR", BooleanType()),
    ]
)


# compute_fn — must be a single module-level named def (see RealtimeConfig
# docstring for the full validation contract). Column names must be ALL-CAPS
# to match Snowflake's normalization. Available without importing: pd, np,
# re, copy. Same reference shape as `_rtfv_compute_fn` in
# tests/integ/snowflake/ml/feature_store/feature_store_realtime_bundled.py:
# one arg per RealtimeConfig source (request first, then each upstream FV),
# row-aligned pandas columns, `.fillna(...)` for nulls instead of branching.
def road_zone_familiarity(request_df: pd.DataFrame, history_df: pd.DataFrame) -> pd.DataFrame:
    """RTFV compute_fn: is CurrentRoadZoneRegion in the vehicle's recent history?

    Args:
        request_df: Request payload with CURRENTROADZONEREGION (RequestSource fields only).
        history_df: Upstream FV rows with ROADZONEREGION_LAST_DISTINCT_8_24H, row-aligned with request_df.

    Returns:
        DataFrame with ISROADZONEFAMILIAR, row-aligned.
    """
    current = request_df["CURRENTROADZONEREGION"].reset_index(drop=True)
    # A vehicle with no history yet gets NULL, not []; fillna("") + apply(list)
    # normalizes both NULL (-> []) and a real list (-> itself) to a list.
    history = history_df["ROADZONEREGION_LAST_DISTINCT_8_24H"].fillna("").apply(list).reset_index(drop=True)
    familiar = [zone in zones for zone, zones in zip(current, history)]
    output_df = pd.DataFrame({"ISROADZONEFAMILIAR": familiar})
    output_df.columns = [c.upper() for c in output_df.columns]
    return output_df


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

    upstream_fv = fs.get_feature_view(UPSTREAM_FV_NAME, UPSTREAM_FV_VERSION)

    realtime_config = RealtimeConfig(
        compute_fn=road_zone_familiarity,
        sources=[RequestSource(schema=REQUEST_SCHEMA), upstream_fv],
        output_schema=OUTPUT_SCHEMA,
    )
    draft_rtfv = FeatureView(
        name=RTFV_NAME,
        entities=[entity],
        realtime_config=realtime_config,
        desc="Generated from a Tecton realtime_feature_view: is CurrentRoadZoneRegion "
        "in the vehicle's last-8-distinct outbound road zones?",
    )
    registered = fs.register_feature_view(draft_rtfv, RTFV_VERSION)
    print(f"Registered {registered.name}/{registered.version} (status={registered.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
