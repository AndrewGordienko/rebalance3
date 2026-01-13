# rebalance3/scenarios/midnight.py
from pathlib import Path

from .base import Scenario
from rebalance3.midnight.midnight_optimizer import optimize_midnight_from_trips
from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour


def midnight_scenario(
    trips_csv: str,
    visualization_day: str,
    *,
    days=None,
    bucket_minutes: int = 15,
    total_bikes_ratio: float = 0.60,
    out_csv: str = "midnight_state.csv",
):
    """
    Build a scenario where only the midnight distribution is optimized,
    then we simulate the day normally with rider trips (no trucks).

    Args:
      trips_csv: path to trips csv
      visualization_day: YYYY-MM-DD day to simulate
      days: optional list of days to optimize against (week-average midnight)
      bucket_minutes: timestep used in simulation
      total_bikes_ratio: ratio of total system capacity to keep as bikes
      out_csv: output station_state csv
    """

    result = optimize_midnight_from_trips(
        trips_csv_path=trips_csv,
        day=visualization_day if days is None else None,
        days=days,
        bucket_minutes=bucket_minutes,
        total_bikes_ratio=total_bikes_ratio,
        empty_threshold=0.10,
        full_threshold=0.90,
        w_empty=1.0,
        w_full=1.0,
    )

    build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=visualization_day,
        out_csv_path=out_csv,
        initial_fill_ratio=None,
        bucket_minutes=result.bucket_minutes,
        initial_bikes=result.bikes_by_station,
    )

    return Scenario(
        name="Midnight optimization" if days is None else "Midnight optimization (week)",
        state_csv=Path(out_csv),
        bucket_minutes=result.bucket_minutes,
        meta={
            "type": "midnight",
            "initial_cost": result.initial_cost,
            "final_cost": result.final_cost,
            "moves": result.moves,
            "days": days,
        },
    )
