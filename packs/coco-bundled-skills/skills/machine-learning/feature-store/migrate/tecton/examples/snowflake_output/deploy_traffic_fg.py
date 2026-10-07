#!/usr/bin/env python3
"""Deploy a FeatureGroup to Snowflake Feature Store.

Customer-facing output of translating one more Tecton spec on top of the
``deploy_traffic_fv.py`` and ``deploy_traffic_rtfv.py`` examples:
  - tecton_input/traffic_feature_service.py  (Tecton FeatureService)

Concept mapping (Tecton -> Snowflake):
  FeatureService(name=..., features=[fv1, fv2])   -> FeatureGroup(name=..., features=[fv1, fv2], auto_prefix=True)
                                                     + fs.register_feature_group(fg, version)
                                                     (materializes one co-located Postgres Online Feature Table)

Prerequisites: both source feature views must already be registered and
online-enabled with Postgres store type:
    python snowflake_output/deploy_traffic_fv.py
    python snowflake_output/deploy_traffic_rtfv.py

Run:
    pip install snowflake-ml-python
    python snowflake_output/deploy_traffic_fg.py

FeatureGroup being deployed:
    ORIGIN_VEHICLE_TRAFFIC_FG/V1
        Combines the SFV (streaming last_distinct aggregate) and the RTFV
        (request-time membership check) into one Postgres Online Feature
        Table for a single low-latency read.
"""

from snowflake.ml.feature_store import CreationMode, FeatureStore
from snowflake.ml.feature_store.feature_group import FeatureGroup
from snowflake.snowpark import Session

# ===========================================================================
# CONFIG — edit before running
# ===========================================================================
CONNECTION_NAME = "<connection>"  # a connection defined in ~/.snowflake/connections.toml
DATABASE = "<DATABASE>"
SCHEMA = "<SCHEMA>"  # feature store schema (same one used by the other deploy_traffic_* scripts)
WAREHOUSE = "<WAREHOUSE>"

FG_NAME = "ORIGIN_VEHICLE_TRAFFIC_FG"
FG_VERSION = "V1"
AUTO_PREFIX = True  # prefix output columns with "<FV_NAME>_<FV_VERSION>_"
DESC = (
    "Generated from a Tecton FeatureService: combines the streaming "
    "last_distinct road-zone history with the realtime familiarity check."
)

# Source feature views (must be registered + online-enabled + Postgres store)
SOURCE_FVS = [
    ("ORIGIN_VEHICLE_LDN_ROAD_ZONE_OUTBOUND", "V1"),
    ("ORIGIN_VEHICLE_ROAD_ZONE_FAMILIARITY", "V1"),
]


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

    features = [fs.get_feature_view(fv_name, fv_version) for fv_name, fv_version in SOURCE_FVS]

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
