# rebalance3/scenarios/trucks_clustered.py
from __future__ import annotations

from pathlib import Path

from .base import Scenario

from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour
from rebalance3.midnight.midnight_optimizer import optimize_midnight_from_trips
from rebalance3.trucks.day_planner import plan_truck_moves_for_day


def truck_clustered_scenario(
    *,
    name: str = "Truck Rebalancing (clustered)",
    trips_csv: str,
    day: str,
    bucket_minutes: int = 15,
    total_bikes_ratio: float = 0.60,

    # ---- planner controls ----
    moves_budget: int = 50,
    truck_cap: int = 20,
    donor_min_bikes_left: int = 3,
    receiver_min_empty_docks_left: int = 2,
    lookahead_minutes: int = 180,

    # ---- objective thresholds ----
    empty_thr: float = 0.10,
    full_thr: float = 0.90,
    w_empty: float = 1.0,
    w_full: float = 1.0,

    # ---- candidates ----
    candidate_time_top_k: int = 8,
    top_k_sources: int = 10,
    top_k_sinks: int = 10,

    # ---- service hours ----
    service_start_hour: int = 8,
    service_end_hour: int = 20,

    # ---- replay cap (optional) ----
    moves_per_hour: int | None = None,

    # ---- output ----
    out_csv: str = "truck_clustered_state.csv",
):
    """
    Cluster-aware day truck planner scenario.

    Pipeline:
      1) Midnight optimize initial bikes (baseline midnight optimizer)
      2) Plan up to moves_budget moves across the day using day_planner.py
      3) Replay planned moves using build_station_state_by_hour (deterministic)
    """

    # ----------------------------
    # Step 1) midnight initialization
    # ----------------------------
    midnight_result = optimize_midnight_from_trips(
        trips_csv_path=trips_csv,
        day=day,
        bucket_minutes=bucket_minutes,
        total_bikes_ratio=total_bikes_ratio,
        empty_threshold=empty_thr,
        full_threshold=full_thr,
        w_empty=1.0,
        w_full=1.0,
    )

    initial_bikes = midnight_result.bikes_by_station

    # ----------------------------
    # Step 2) plan moves for the day (cluster-aware inside planner)
    # ----------------------------
    planned_moves = plan_truck_moves_for_day(
        trips_csv_path=trips_csv,
        day=day,
        initial_bikes=initial_bikes,
        bucket_minutes=midnight_result.bucket_minutes,
        moves_budget=moves_budget,
        truck_cap=truck_cap,
        donor_min_bikes_left=donor_min_bikes_left,
        receiver_min_empty_docks_left=receiver_min_empty_docks_left,
        lookahead_minutes=lookahead_minutes,
        empty_thr=empty_thr,
        full_thr=full_thr,
        w_empty=w_empty,
        w_full=w_full,
        candidate_time_top_k=candidate_time_top_k,
        top_k_sources=top_k_sources,
        top_k_sinks=top_k_sinks,
        service_start_hour=service_start_hour,
        service_end_hour=service_end_hour,
    )

    # ----------------------------
    # Step 3) replay moves into the simulator
    # ----------------------------
    applied_moves = build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=day,
        out_csv_path=out_csv,
        bucket_minutes=midnight_result.bucket_minutes,
        initial_fill_ratio=None,
        initial_bikes=initial_bikes,
        planned_moves=planned_moves,
        moves_per_hour=moves_per_hour,
    )

    return Scenario(
        name=name,
        state_csv=Path(out_csv),
        bucket_minutes=midnight_result.bucket_minutes,
        meta={
            "type": "trucks_clustered",
            "day": day,
            "moves_budget": int(moves_budget),
            "truck_cap": int(truck_cap),
            "service_start_hour": int(service_start_hour),
            "service_end_hour": int(service_end_hour),
            "empty_thr": float(empty_thr),
            "full_thr": float(full_thr),
            "w_empty": float(w_empty),
            "w_full": float(w_full),
            "planned_moves": int(len(planned_moves)),
            "applied_moves": int(len(applied_moves)),
            "truck_moves": applied_moves,
            "midnight_initial_cost": midnight_result.initial_cost,
            "midnight_final_cost": midnight_result.final_cost,
            "midnight_moves": midnight_result.moves,
        },
    )
