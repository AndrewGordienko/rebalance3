from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour
from rebalance3.midnight.midnight_optimizer import optimize_midnight_from_trips
from rebalance3.viz.stations_map import serve_stations_map

TRIPS = "Bike share ridership 2024-09.csv"
DAY = "2024-09-01"
STATIONS = "station_information.json"

"""
# Baseline example for September 1, 2024
build_station_state_by_hour(
    trips_csv_path="Bike share ridership 2024-09.csv",
    day="2024-09-01",
    out_csv_path="station_state_by_hour.csv",
    initial_fill_ratio=0.60,
)

serve_stations_map(port=8080, state_by_hour_csv="station_state_by_hour.csv")
"""


# Midnight optimization example for September 1, 2024
result = optimize_midnight_from_trips(
        trips_csv_path=TRIPS,
        day=DAY,
        bucket_minutes=15,
        total_bikes_ratio=0.60,
        empty_threshold=0.10,
        full_threshold=0.90,
        w_empty=1.0,
        w_full=1.0,
    )

print(f"Initial cost: {result.initial_cost:.1f}")
print(f"Final cost:   {result.final_cost:.1f}")
print(f"Moves:        {result.moves}")

build_station_state_by_hour(
        trips_csv_path=TRIPS,
        day=DAY,
        out_csv_path="station_state_by_hour.csv",
        initial_fill_ratio=None,
        bucket_minutes=result.bucket_minutes,
        initial_bikes=result.bikes_by_station
    )

serve_stations_map(
    port=8080,
    state_by_hour_csv="station_state_by_hour.csv",
    title="Midnight optimization — September 1, 2024",
    graphs=False,
)
