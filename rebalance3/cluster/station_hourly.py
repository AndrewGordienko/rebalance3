# rebalance3/profiles/station_hourly.py

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd
import numpy as np


DEFAULT_TIME_FMT = "%m/%d/%Y %H:%M"


@dataclass
class StationHourlyCounts:
    """
    dep_counts: DataFrame (index=station_id, columns=0..23) int
    arr_counts: DataFrame (index=station_id, columns=0..23) int
    station_ids: sorted list of station ids included in the matrices
    """
    dep_counts: pd.DataFrame
    arr_counts: pd.DataFrame
    station_ids: list[int]


def _ensure_hour_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure DataFrame has all 24 hour columns [0..23], filling missing with 0,
    and ordered correctly.
    """
    df = df.copy()
    df = df.reindex(columns=list(range(24)), fill_value=0)
    return df


def load_trip_csv(trips_csv: str | Path) -> pd.DataFrame:
    """
    Loads Bike Share Toronto trips CSV with columns like:

      Trip Id, Trip  Duration, Start Station Id, Start Time, ...
      End Station Id, End Time, ...

    Returns cleaned DataFrame with:
      - start_station_id (int)
      - end_station_id (int)
      - start_time (datetime)
      - end_time (datetime)
      - start_hour (0..23)
      - end_hour (0..23)
    """
    trips_csv = Path(trips_csv)

    df = pd.read_csv(trips_csv)

    # Normalize column names (your sample has spaces and capitalization)
    colmap = {c.strip(): c for c in df.columns}
    # Required logical columns (strip spaces)
    start_station_col = colmap.get("Start Station Id")
    end_station_col = colmap.get("End Station Id")
    start_time_col = colmap.get("Start Time")
    end_time_col = colmap.get("End Time")

    if start_station_col is None or end_station_col is None:
        raise ValueError(
            "Trips CSV missing 'Start Station Id' or 'End Station Id' columns."
        )
    if start_time_col is None or end_time_col is None:
        raise ValueError("Trips CSV missing 'Start Time' or 'End Time' columns.")

    out = pd.DataFrame()
    out["start_station_id"] = df[start_station_col].astype(int)
    out["end_station_id"] = df[end_station_col].astype(int)

    # parse timestamps (your format is like "09/01/2024 00:00")
    out["start_time"] = pd.to_datetime(df[start_time_col], errors="coerce")
    out["end_time"] = pd.to_datetime(df[end_time_col], errors="coerce")

    # Drop malformed rows
    out = out.dropna(subset=["start_time", "end_time"])

    out["start_hour"] = out["start_time"].dt.hour.astype(int)
    out["end_hour"] = out["end_time"].dt.hour.astype(int)

    return out


def compute_station_hourly_counts(
    trips_df: pd.DataFrame,
    station_ids: list[int] | None = None,
) -> StationHourlyCounts:
    """
    Computes station-hour departure and arrival count matrices.

    trips_df must have:
      - start_station_id
      - end_station_id
      - start_hour
      - end_hour

    If station_ids is provided, we will reindex to include them all.
    If not, station_ids is derived from seen ids in trips data.
    """

    # Departures: start station id by start hour
    dep = (
        trips_df.groupby(["start_station_id", "start_hour"])
        .size()
        .unstack(fill_value=0)
    )
    dep = _ensure_hour_columns(dep)

    # Arrivals: end station id by end hour
    arr = (
        trips_df.groupby(["end_station_id", "end_hour"])
        .size()
        .unstack(fill_value=0)
    )
    arr = _ensure_hour_columns(arr)

    if station_ids is None:
        station_ids = sorted(set(dep.index.tolist()) | set(arr.index.tolist()))
    else:
        station_ids = sorted([int(x) for x in station_ids])

    dep = dep.reindex(index=station_ids, fill_value=0).astype(int)
    arr = arr.reindex(index=station_ids, fill_value=0).astype(int)

    return StationHourlyCounts(dep_counts=dep, arr_counts=arr, station_ids=station_ids)


def normalize_hourly_counts(counts_df: pd.DataFrame) -> pd.DataFrame:
    """
    Row-normalize an hourly counts matrix into a probability distribution.

    For stations with zero total count, returns all zeros.
    """
    x = counts_df.values.astype(np.float64)
    row_sum = x.sum(axis=1, keepdims=True)

    # avoid divide-by-zero
    row_sum[row_sum == 0.0] = 1.0

    x_norm = x / row_sum
    out = pd.DataFrame(x_norm, index=counts_df.index, columns=counts_df.columns)
    return out


def build_station_signature(
    dep_counts: pd.DataFrame,
    arr_counts: pd.DataFrame,
) -> pd.DataFrame:
    """
    Builds a station feature matrix with 48 columns:
      dep_0..dep_23, arr_0..arr_23

    Uses normalized distributions, not raw counts.
    """
    dep_norm = normalize_hourly_counts(dep_counts)
    arr_norm = normalize_hourly_counts(arr_counts)

    dep_cols = {h: f"dep_{h:02d}" for h in range(24)}
    arr_cols = {h: f"arr_{h:02d}" for h in range(24)}

    dep_norm = dep_norm.rename(columns=dep_cols)
    arr_norm = arr_norm.rename(columns=arr_cols)

    sig = pd.concat([dep_norm, arr_norm], axis=1)
    return sig


def write_hourly_counts_csv(
    hourly: StationHourlyCounts,
    out_dir: str | Path,
    prefix: str = "station_hourly",
) -> tuple[Path, Path]:
    """
    Writes:
      {prefix}_dep.csv
      {prefix}_arr.csv
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dep_path = out_dir / f"{prefix}_dep.csv"
    arr_path = out_dir / f"{prefix}_arr.csv"

    hourly.dep_counts.to_csv(dep_path, index=True)
    hourly.arr_counts.to_csv(arr_path, index=True)

    return dep_path, arr_path
