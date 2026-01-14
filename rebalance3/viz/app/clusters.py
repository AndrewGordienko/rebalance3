# rebalance3/viz/app/clusters.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import pandas as pd
import numpy as np

import folium
from flask import Flask

from rebalance3.cluster.station_hourly import (
    load_trip_csv,
    compute_station_hourly_counts,
    build_station_signature,
)
from rebalance3.cluster.cluster_stations import (
    cluster_station_signatures,
    summarize_clusters,
)


CENTER_LAT = 43.6532
CENTER_LON = -79.3832


# Works well visually up to ~10 clusters (cycles if k > len(colors))
CLUSTER_COLORS = [
    "red",
    "blue",
    "green",
    "purple",
    "orange",
    "darkred",
    "cadetblue",
    "darkgreen",
    "black",
    "darkblue",
]


@dataclass
class ClusterViewerResult:
    stations_df: pd.DataFrame        # station_id, name, lat, lon, capacity, cluster_id
    cluster_summary_df: pd.DataFrame # interpretability stats


def _load_station_information_json(stations_json: str | Path) -> pd.DataFrame:
    """
    Reads Bike Share Toronto station_information.json format:
      {"data":{"stations":[{station_id, lat, lon, name, capacity, ...}, ...]}}
    """
    stations_json = Path(stations_json)

    with open(stations_json, "r") as f:
        data = json.load(f)

    stations = pd.DataFrame(data["data"]["stations"])
    stations["station_id"] = stations["station_id"].astype(int)
    return stations


def build_station_clusters_view(
    trips_csv: str | Path,
    day: str,
    stations_json: str | Path,
    k: int = 8,
    seed: int = 0,
) -> ClusterViewerResult:
    """
    Builds clusters for a single day worth of trips (or you can pass a full-month CSV,
    and the day just filters the trips used).
    """

    trips = load_trip_csv(trips_csv)

    # Filter to day for stable clustering display in UI
    # (your load_trip_csv parses datetimes already)
    trips["date"] = trips["start_time"].dt.strftime("%Y-%m-%d")
    trips_day = trips[trips["date"] == day].copy()

    # Build hourly dep/arr and signature
    hourly = compute_station_hourly_counts(trips_day)
    sig = build_station_signature(hourly.dep_counts, hourly.arr_counts)

    # Cluster
    station_clusters = cluster_station_signatures(sig, k=k, seed=seed, standardize=True)

    # Load station registry (coords, names, capacity)
    stations = _load_station_information_json(stations_json)

    # Merge
    clusters_df = station_clusters.clusters_df
    merged = stations.merge(clusters_df, on="station_id", how="left")

    # Fill missing cluster assignments (stations with no activity that day)
    merged["cluster_id"] = merged["cluster_id"].fillna(-1).astype(int)

    # Summary for debugging / labeling
    summary = summarize_clusters(sig, clusters_df)

    return ClusterViewerResult(stations_df=merged, cluster_summary_df=summary)


def build_clusters_map_html(
    stations_with_clusters: pd.DataFrame,
    title: str = "Station Clusters",
) -> str:
    """
    Returns standalone HTML string for a folium map.
    """

    m = folium.Map(
        location=[CENTER_LAT, CENTER_LON],
        zoom_start=12,
        tiles="CartoDB positron",
    )

    # FeatureGroups: one layer per cluster so you can toggle them
    cluster_ids = sorted(stations_with_clusters["cluster_id"].unique().tolist())
    layers: dict[int, folium.FeatureGroup] = {}

    for cid in cluster_ids:
        name = f"Cluster {cid}" if cid >= 0 else "Unclustered"
        layers[cid] = folium.FeatureGroup(name=name, show=True)

    for _, row in stations_with_clusters.iterrows():
        cid = int(row["cluster_id"])
        lat = float(row["lat"])
        lon = float(row["lon"])
        sid = int(row["station_id"])
        name = str(row.get("name", ""))
        cap = row.get("capacity", None)

        if cid >= 0:
            color = CLUSTER_COLORS[cid % len(CLUSTER_COLORS)]
        else:
            color = "gray"

        cap_str = f", cap={int(cap)}" if pd.notna(cap) else ""
        popup = f"{sid} — {name} (cluster {cid}{cap_str})"

        folium.CircleMarker(
            location=[lat, lon],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.85,
            weight=1,
            popup=popup,
        ).add_to(layers[cid])

    for layer in layers.values():
        layer.add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Add a top title overlay
    title_html = f"""
    <div style="
        position: fixed;
        top: 10px;
        left: 50px;
        z-index: 9999;
        background: rgba(255,255,255,0.92);
        padding: 8px 12px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.15);
        font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;
        font-size: 16px;
        font-weight: 700;">
        {title}
    </div>
    """
    m.get_root().html.add_child(folium.Element(title_html))

    return m.get_root().render()


def serve_clusters(
    trips_csv: str | Path,
    day: str,
    stations_json: str | Path,
    k: int = 8,
    seed: int = 0,
    host: str = "127.0.0.1",
    port: int = 8090,
    debug: bool = False,
    title: str | None = None,
):
    """
    Library entry point: start a small web server that displays the cluster map.
    """
    if title is None:
        title = f"Station Clusters (k={k}) — {day}"

    result = build_station_clusters_view(
        trips_csv=trips_csv,
        day=day,
        stations_json=stations_json,
        k=k,
        seed=seed,
    )

    app = Flask(__name__)

    # Print summary to console (useful)
    print("\nCluster summary:")
    print(result.cluster_summary_df.to_string(index=False))

    @app.get("/")
    def index():
        html_map = build_clusters_map_html(result.stations_df, title=title)

        # Also show summary table under map
        summary_html = result.cluster_summary_df.to_html(index=False, float_format=lambda x: f"{x:.3f}")

        full = f"""
        <html>
          <head>
            <meta charset="utf-8"/>
            <meta name="viewport" content="width=device-width, initial-scale=1"/>
            <title>{title}</title>
          </head>
          <body style="margin:0; padding:0;">
            {html_map}
            <div style="padding: 14px 16px; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial;">
              <h2 style="margin: 8px 0;">Cluster Summary</h2>
              {summary_html}
            </div>
          </body>
        </html>
        """
        return full

    app.run(host=host, port=port, debug=debug)
