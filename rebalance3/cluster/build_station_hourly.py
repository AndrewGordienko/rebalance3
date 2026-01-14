from pathlib import Path
from station_hourly import (
    load_trip_csv,
    compute_station_hourly_counts,
    build_station_signature,
)

TRIPS_CSV = Path("Bike share ridership 2024-09.csv")

df = load_trip_csv(TRIPS_CSV)

hourly = compute_station_hourly_counts(df)

sig = build_station_signature(hourly.dep_counts, hourly.arr_counts)

print("Stations:", len(hourly.station_ids))
print("dep matrix:", hourly.dep_counts.shape)
print("arr matrix:", hourly.arr_counts.shape)
print("signature:", sig.shape)

print(sig.head())
