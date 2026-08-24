from datetime import datetime, timedelta

from entities.origin_vehicle import origin_vehicle
from stream_sources.example_traffic_stream import example_traffic_stream
from tecton.aggregation_functions import *


@stream_feature_view(
    source=example_traffic_stream,
    entities=[origin_vehicle],
    mode="pandas",
    stream_processing_mode=StreamProcessingMode.CONTINUOUS,
    features=[
        Aggregate(
            function=last_distinct(8), input_column=Field("RoadZoneRegion", String), time_window=timedelta(hours=24)
        ),
    ],
    online=True,
    offline=True,
    feature_start_time=datetime(2025, 4, 2),
    batch_schedule=timedelta(days=1),
    timestamp_field="EventTimestamp",
    max_backfill_interval=timedelta(days=2),
    batch_compute=RiftBatchConfig(
        instance_type="m6a.4xlarge",
    ),
)
def origin_vehicle_last_distinct_road_zone_outbound(example_traffic_stream):
    example_traffic_stream = example_traffic_stream[
        (example_traffic_stream["RoadZoneRegion"] != "")
        & (example_traffic_stream["OriginVehicleId"] != "")
        & (example_traffic_stream["TripDirection"] == "outbound")
        & (example_traffic_stream["TripType"] == "highway")
    ]
    return example_traffic_stream[["OriginVehicleId", "EventTimestamp", "RoadZoneRegion"]]
