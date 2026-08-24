from feature_views.origin_vehicle_last_distinct_road_zone_outbound import (
    origin_vehicle_last_distinct_road_zone_outbound,
)
from tecton import Attribute, RequestSource, realtime_feature_view
from tecton.types import Bool, Field, String

# Request-time input: the road zone the vehicle is currently entering.
road_zone_check_request = RequestSource(
    schema=[
        Field("CurrentRoadZoneRegion", String),
    ]
)


@realtime_feature_view(
    sources=[road_zone_check_request, origin_vehicle_last_distinct_road_zone_outbound],
    mode="python",
    features=[
        Attribute("IsRoadZoneFamiliar", Bool),
    ],
)
def origin_vehicle_road_zone_familiarity(road_zone_check_request, origin_vehicle_last_distinct_road_zone_outbound):
    history = origin_vehicle_last_distinct_road_zone_outbound["RoadZoneRegion_last_distinct_8_24h"] or []
    current = road_zone_check_request["CurrentRoadZoneRegion"]
    return {"IsRoadZoneFamiliar": current in history}
