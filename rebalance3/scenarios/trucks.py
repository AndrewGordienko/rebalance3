from pathlib import Path

from .base import Scenario
from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour
from rebalance3.util.load_bikes import load_initial_bikes_from_csv


def truck_scenario(
    *,
    name: str,
    base_scenario: Scenario,
    trips_csv: str,
    day: str,
    trucks_per_day: int,
    out_csv: str,
):
    """
    Apply truck rebalancing on top of an existing scenario.

    Key idea:
      - start from base scenario's midnight bikes
      - simulate the day
      - dispatch trucks dynamically during the day
      - capture timed TruckMove list
    """

    # ---- load base midnight bikes ----
    initial_bikes = load_initial_bikes_from_csv(base_scenario.state_csv)

    # ---- simulate day WITH trucks ----
    truck_moves = build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=day,
        out_csv_path=out_csv,
        initial_fill_ratio=None,
        initial_bikes=initial_bikes,
        bucket_minutes=base_scenario.bucket_minutes,
        trucks_per_day=trucks_per_day,
    )

    return Scenario(
        name=name,
        state_csv=Path(out_csv),
        bucket_minutes=base_scenario.bucket_minutes,
        meta={
            "type": "trucks",
            "trucks_per_day": trucks_per_day,
            "base": base_scenario.name,
            "truck_moves": truck_moves,   # timed + ordered
        },
    )
