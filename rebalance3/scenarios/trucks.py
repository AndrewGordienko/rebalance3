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
    out_csv: str,
    # -------------------------------------------------
    # YOUR RULE
    # -------------------------------------------------
    n_trucks: int = 10,
    moves_per_truck_total: int = 5,  # total per day per truck
    # -------------------------------------------------
    # service window (planner only)
    # -------------------------------------------------
    service_start_hour: int = 8,
    service_end_hour: int = 20,
    # optional override
    total_moves_per_day: int | None = None,
):
    """
    Truck scenario rule:

      - trucks are NOT fresh every hour
      - each truck is used at most once per day
      - each truck can do up to K moves TOTAL for the day

    So total daily capacity is:
        moves_budget = n_trucks * moves_per_truck_total
    """

    n_trucks = max(0, int(n_trucks))
    moves_per_truck_total = max(0, int(moves_per_truck_total))

    if total_moves_per_day is None:
        moves_budget = n_trucks * moves_per_truck_total
    else:
        moves_budget = max(0, int(total_moves_per_day))

    # ---- base midnight distribution ----
    initial_bikes = load_initial_bikes_from_csv(base_scenario.state_csv)

    # ---- plan globally optimal moves ----
    planned_moves = plan_truck_moves_for_day(
        trips_csv_path=trips_csv,
        day=day,
        initial_bikes=initial_bikes,
        bucket_minutes=base_scenario.bucket_minutes,
        moves_budget=int(moves_budget),
        truck_cap=20,
        service_start_hour=int(service_start_hour),
        service_end_hour=int(service_end_hour),
    )

    # ---- simulate day and replay planned moves ----
    #
    # NOTE:
    # your current build_station_state_by_hour() signature does NOT accept trucks_per_day anymore
    truck_moves = build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=day,
        out_csv_path=out_csv,
        initial_fill_ratio=None,
        initial_bikes=initial_bikes,
        bucket_minutes=base_scenario.bucket_minutes,
        planned_moves=planned_moves,
    )

    return Scenario(
        name=name,
        state_csv=Path(out_csv),
        bucket_minutes=base_scenario.bucket_minutes,
        meta={
            "type": "trucks_global_planner",
            "base": base_scenario.name,
            "n_trucks": int(n_trucks),
            "moves_per_truck_total": int(moves_per_truck_total),
            "moves_budget": int(moves_budget),
            "service_start_hour": int(service_start_hour),
            "service_end_hour": int(service_end_hour),
            "planned_moves": planned_moves,
            "truck_moves": truck_moves,
        },
    )
