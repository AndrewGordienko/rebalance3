from pathlib import Path
from copy import deepcopy

from .base import Scenario
from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour
from rebalance3.util.load_bikes import load_initial_bikes_from_csv
from rebalance3.trucks.simulator import apply_truck_rebalancing
from rebalance3.midnight.midnight_optimizer import load_capacity_from_station_information
from rebalance3.midnight.midnight_optimizer import DEFAULT_TORONTO_STATIONS_FILE


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
    """

    # ---- load base state ----
    initial_bikes = load_initial_bikes_from_csv(base_scenario.state_csv)

    # ---- load capacities (REQUIRED) ----
    station_capacity = load_capacity_from_station_information(
        DEFAULT_TORONTO_STATIONS_FILE
    )

    # ---- copy mutable state for trucks ----
    station_bikes = deepcopy(initial_bikes)

    # ---- run truck policy explicitly ----
    truck_moves = apply_truck_rebalancing(
        station_bikes=station_bikes,
        station_capacity=station_capacity,
        trucks_per_day=trucks_per_day,
        empty_thr=0.10,
        full_thr=0.90,
        target_thr=0.50,
        truck_cap=20,
    )

    # ---- simulate the day with truck-adjusted bikes ----
    build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=day,
        out_csv_path=out_csv,
        initial_fill_ratio=None,
        initial_bikes=station_bikes,
    )

    return Scenario(
        name=name,
        state_csv=Path(out_csv),
        bucket_minutes=base_scenario.bucket_minutes,
        meta={
            "type": "trucks",
            "trucks_per_day": trucks_per_day,
            "base": base_scenario.name,
            "truck_moves": truck_moves,
        },
    )
