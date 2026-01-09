from pathlib import Path
from .base import Scenario
from rebalance3.midnight.midnight_optimizer import optimize_midnight_from_trips
from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour

def midnight_scenario(
    trips_csv: str,
    day: str,
    bucket_minutes: int,
    total_bikes_ratio: float,
):
    result = optimize_midnight_from_trips(
        trips_csv_path=trips_csv,
        day=day,
        bucket_minutes=bucket_minutes,
        total_bikes_ratio=total_bikes_ratio,
        empty_threshold=0.10,
        full_threshold=0.90,
        w_empty=1.0,
        w_full=1.0,
    )

    out_csv = "midnight_state.csv"

    build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=day,
        out_csv_path=out_csv,
        initial_fill_ratio=None,
        bucket_minutes=result.bucket_minutes,
        initial_bikes=result.bikes_by_station,
    )

    return Scenario(
        name="Midnight optimization",
        state_csv=Path(out_csv),
        bucket_minutes=result.bucket_minutes,
        meta={
            "type": "midnight",
            "initial_cost": result.initial_cost,
            "final_cost": result.final_cost,
            "moves": result.moves,
        },
    )
