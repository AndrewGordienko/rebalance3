from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour
from rebalance3.viz.stations_map import serve_stations_map

build_station_state_by_hour(
    trips_csv_path="Bike share ridership 2024-09.csv",
    day="2024-09-01",
    out_csv_path="station_state_by_hour.csv",
    initial_fill_ratio=0.60,
)


serve_stations_map(port=8080, state_by_hour_csv="station_state_by_hour.csv")
