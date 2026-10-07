from feature_views.origin_vehicle_last_distinct_road_zone_outbound import (
    origin_vehicle_last_distinct_road_zone_outbound,
)
from realtime_feature_views.origin_vehicle_road_zone_familiarity import (
    origin_vehicle_road_zone_familiarity,
)
from tecton import FeatureService

# Bundles the streaming aggregate and the realtime feature into a single
# retrieval unit — the Tecton analog of Snowflake's FeatureGroup (co-located
# online read of both features for one entity key + request-time inputs).
origin_vehicle_traffic_fs = FeatureService(
    name="origin_vehicle_traffic_fs",
    features=[
        origin_vehicle_last_distinct_road_zone_outbound,
        origin_vehicle_road_zone_familiarity,
    ],
)
