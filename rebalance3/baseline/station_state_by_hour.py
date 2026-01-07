import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from tqdm import tqdm
from colorama import Fore, Style, init

init(autoreset=True)

TIME_FMT = "%m/%d/%Y %H:%M"

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, TIME_FMT)


def build_station_state_by_hour(
    trips_csv_path: str,
    day: str,  # "YYYY-MM-DD"
    out_csv_path: str,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
    *,
    initial_fill_ratio: Optional[float] = 0.60,
    initial_bikes: Optional[Dict[str, int]] = None,
    bucket_minutes: int = 15,
):
    # ----------------------------
    # Sanitize inputs
    # ----------------------------
    if initial_bikes is None:
        initial_fill_ratio = float(initial_fill_ratio)
        if initial_fill_ratio < 0.0:
            initial_fill_ratio = 0.0
        if initial_fill_ratio > 1.0:
            initial_fill_ratio = 1.0

    bucket_minutes = int(bucket_minutes)
    if bucket_minutes <= 0:
        bucket_minutes = 15
    if 1440 % bucket_minutes != 0:
        raise ValueError(
            "bucket_minutes must divide 1440 "
            "(e.g. 60, 30, 15, 10, 5, 1)"
        )

    day_start = datetime.fromisoformat(f"{day}T00:00:00")
    day_end_exclusive = day_start + timedelta(days=1)

    print(f"{Fore.CYAN}Loading station registry…{Style.RESET_ALL}")
    with open(stations_file) as f:
        stations = json.load(f)["data"]["stations"]

    station_by_id = {
        str(s["station_id"]): int(s["capacity"])
        for s in stations
    }

    bikes: Dict[str, int] = {}

    if initial_bikes is not None:
        # Use optimized midnight allocation
        for sid, cap in station_by_id.items():
            b = int(initial_bikes.get(sid, 0))
            bikes[sid] = max(0, min(cap, b))
        print(f"{Fore.CYAN}Using optimized midnight allocation{Style.RESET_ALL}")
    else:
        # Baseline proportional fill
        for sid, cap in station_by_id.items():
            b = int(round(cap * initial_fill_ratio))
            bikes[sid] = max(0, min(cap, b))
        print(
            f"{Fore.CYAN}Using baseline fill ratio "
            f"{initial_fill_ratio:.2f}{Style.RESET_ALL}"
        )

    events = []

    with open(trips_csv_path) as f:
        total_rows = max(0, sum(1 for _ in f) - 1)

    print(
        f"{Fore.CYAN}Processing trips for {day}…{Style.RESET_ALL}"
    )

    with open(trips_csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, total=total_rows, desc="Reading trips"):
            try:
                start_dt = _parse_dt(row["Start Time"])
                end_dt = _parse_dt(row["End Time"])
            except Exception:
                continue

            if start_dt.date().isoformat() != day:
                continue

            start_sid = str(row["Start Station Id"])
            end_sid = str(row["End Station Id"])

            if start_sid in station_by_id:
                events.append((start_dt, "start", start_sid))
            if end_sid in station_by_id:
                events.append((end_dt, "end", end_sid))

    events.sort(key=lambda x: x[0])

    print(
        f"{Fore.CYAN}Simulating day "
        f"(bucket_minutes={bucket_minutes})…{Style.RESET_ALL}"
    )

    snapshots = {}
    idx = 0

    bucket_count = 1440 // bucket_minutes
    for b in range(bucket_count):
        bucket_end = day_start + timedelta(minutes=(b + 1) * bucket_minutes)
        if bucket_end > day_end_exclusive:
            bucket_end = day_end_exclusive

        while idx < len(events) and events[idx][0] < bucket_end:
            _, kind, sid = events[idx]
            cap = station_by_id[sid]

            if kind == "start":
                if bikes[sid] > 0:
                    bikes[sid] -= 1
            else:
                if bikes[sid] < cap:
                    bikes[sid] += 1

            idx += 1

        t_min = b * bucket_minutes
        snapshots[t_min] = bikes.copy()

    print(f"{Fore.CYAN}Writing {out_csv_path}…{Style.RESET_ALL}")
    with open(out_csv_path, "w", newline="") as f:
        writer = csv.writer(f)

        if bucket_minutes == 60:
            writer.writerow(
                ["station_id", "hour", "bikes", "empty_docks", "capacity"]
            )
            for t_min, state in snapshots.items():
                hour = t_min // 60
                for sid, b in state.items():
                    cap = station_by_id[sid]
                    writer.writerow([sid, hour, b, cap - b, cap])
        else:
            writer.writerow(
                ["station_id", "t_min", "bikes", "empty_docks", "capacity"]
            )
            for t_min, state in snapshots.items():
                for sid, b in state.items():
                    cap = station_by_id[sid]
                    writer.writerow([sid, t_min, b, cap - b, cap])

    print(f"{Fore.GREEN}Station state build complete.{Style.RESET_ALL}")