# rebalance3/cluster groups/profiles/build_station_clusters.py

from pathlib import Path

from station_hourly import (
    load_trip_csv,
    compute_station_hourly_counts,
    build_station_signature,
)
from cluster_stations import (
    cluster_station_signatures,
    write_station_clusters_csv,
    summarize_clusters,
)

TRIPS_CSV = Path("Bike share ridership 2024-09.csv")
OUT_CSV = Path("data/profiles/station_clusters.csv")

K = 8
SEED = 0

df = load_trip_csv(TRIPS_CSV)

hourly = compute_station_hourly_counts(df)
sig = build_station_signature(hourly.dep_counts, hourly.arr_counts)

station_clusters = cluster_station_signatures(sig, k=K, seed=SEED, standardize=True)
out_path = write_station_clusters_csv(station_clusters, OUT_CSV)

print(f"Wrote: {out_path}")
print(station_clusters.clusters_df.head(10))

summary = summarize_clusters(sig, station_clusters.clusters_df)
print("\nCluster summary:")
print(summary.to_string(index=False))
