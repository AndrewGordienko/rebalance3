from pathlib import Path
from .base import Scenario
from rebalance3.baseline.station_state_by_hour import build_station_state_by_hour


def baseline_scenario(
    trips_csv: str,
    day: str,
    initial_fill_ratio: float,
    *,
    bucket_minutes: int = 15,
    out_csv: str = "baseline_state.csv",
):
    build_station_state_by_hour(
        trips_csv_path=trips_csv,
        day=day,
        out_csv_path=out_csv,
        initial_fill_ratio=initial_fill_ratio,
        bucket_minutes=bucket_minutes,
    )

    return Scenario(
        name=f"Baseline ({initial_fill_ratio*100:.0f}%)",
        state_csv=Path(out_csv),
        bucket_minutes=bucket_minutes,
        meta={
            "type": "baseline",
            "initial_fill_ratio": initial_fill_ratio,
        },
    )
