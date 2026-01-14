# rebalance3/profiles/cluster_stations.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


@dataclass
class StationClusters:
    """
    clusters_df columns:
      - station_id
      - cluster_id
    """
    clusters_df: pd.DataFrame
    k: int


def cluster_station_signatures(
    sig_df: pd.DataFrame,
    k: int = 8,
    seed: int = 0,
    standardize: bool = True,
) -> StationClusters:
    """
    sig_df: index=station_id, columns=[dep_00..dep_23, arr_00..arr_23] (float)

    Returns station_id -> cluster_id.
    """
    X = sig_df.values.astype(np.float64)

    if standardize:
        # not strictly required since rows sum to 1-ish per half,
        # but it helps prevent a few columns dominating if variance differs.
        scaler = StandardScaler()
        X = scaler.fit_transform(X)

    km = KMeans(
        n_clusters=k,
        random_state=seed,
        n_init="auto",
    )
    labels = km.fit_predict(X)

    clusters_df = pd.DataFrame(
        {
            "station_id": sig_df.index.astype(int),
            "cluster_id": labels.astype(int),
        }
    ).sort_values("station_id")

    return StationClusters(clusters_df=clusters_df, k=k)


def write_station_clusters_csv(
    station_clusters: StationClusters,
    out_csv: str | Path,
) -> Path:
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    station_clusters.clusters_df.to_csv(out_csv, index=False)
    return out_csv


def summarize_clusters(
    sig_df: pd.DataFrame,
    clusters_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Returns per-cluster summary features to help you interpret clusters.
    """
    df = sig_df.copy()
    df["cluster_id"] = clusters_df.set_index("station_id").loc[df.index, "cluster_id"].values

    def _mass(cols):
        return df[cols].sum(axis=1)

    # Heuristic “patterns” (useful for auto-tagging later)
    dep_night = _mass([f"dep_{h:02d}" for h in [22, 23, 0, 1, 2, 3]])
    dep_am = _mass([f"dep_{h:02d}" for h in range(6, 10)])
    dep_pm = _mass([f"dep_{h:02d}" for h in range(16, 20)])

    arr_am = _mass([f"arr_{h:02d}" for h in range(7, 11)])
    arr_pm = _mass([f"arr_{h:02d}" for h in range(16, 20)])

    tmp = pd.DataFrame(
        {
            "cluster_id": df["cluster_id"].values,
            "dep_night": dep_night.values,
            "dep_am": dep_am.values,
            "dep_pm": dep_pm.values,
            "arr_am": arr_am.values,
            "arr_pm": arr_pm.values,
        },
        index=df.index,
    )

    summary = (
        tmp.groupby("cluster_id")
        .agg(
            n=("cluster_id", "size"),
            dep_night_mean=("dep_night", "mean"),
            dep_am_mean=("dep_am", "mean"),
            dep_pm_mean=("dep_pm", "mean"),
            arr_am_mean=("arr_am", "mean"),
            arr_pm_mean=("arr_pm", "mean"),
        )
        .sort_values("n", ascending=False)
        .reset_index()
    )

    return summary
