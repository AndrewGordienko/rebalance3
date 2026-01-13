# rebalance3/scenarios/trucks.py
from pathlib import Path

from .base import Scenario
from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour
from rebalance3.util.load_bikes import load_initial_bikes_from_csv

from rebalance3.trucks.day_planner import plan_truck_moves_for_day


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

    NEW behavior:
      - Plan moves globally over the full day with a cost function
      - Replay those timed moves inside the normal event-based simulator

    This avoids the greedy "spend all moves immediately" behavior.
    """

    # ---- load base midnight bikes ----
    initial_bikes = load_initial_bikes_from_csv(base_scenario.state_csv)

    # ---- plan globally optimal moves ----
    planned_moves = plan_truck_moves_for_day(
        trips_csv_path=trips_csv,
        day=day,
        initial_bikes=initial_bikes,
        bucket_minutes=base_scenario.bucket_minutes,
        moves_budget=int(trucks_per_day),
        truck_cap=20,
    )

    # ---- simulate day and replay planned moves ----
    truck_moves = build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=day,
        out_csv_path=out_csv,
        initial_fill_ratio=None,
        initial_bikes=initial_bikes,
        bucket_minutes=base_scenario.bucket_minutes,
        trucks_per_day=0,              # IMPORTANT: no online dispatch
        planned_moves=planned_moves,   # replay mode
    )

    return Scenario(
        name=name,
        state_csv=Path(out_csv),
        bucket_minutes=base_scenario.bucket_minutes,
        meta={
            "type": "trucks_global_planner",
            "trucks_per_day": int(trucks_per_day),
            "base": base_scenario.name,
            "planned_moves": planned_moves,  # raw planner output
            "truck_moves": truck_moves,      # what was actually applied (post-clamp)
        },
    )
