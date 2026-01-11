import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from tqdm import tqdm
from colorama import Fore, Style, init

from rebalance3.trucks.simulator import apply_truck_rebalancing
from rebalance3.trucks.types import TruckMove

init(autoreset=True)

TIME_FMT = "%m/%d/%Y %H:%M"

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, TIME_FMT)


def build_station_state_by_hour(
    trips_csv_path: str,
    day: str,
    out_csv_path: str,
    *,
    initial_fill_ratio: float | None,
    bucket_minutes: int = 15,
    initial_bikes: dict | None = None,
    trucks_per_day: int = 0,
):
    # ----------------------------
    # Sanitize inputs
    # ----------------------------
    if initial_bikes is None:
        initial_fill_ratio = float(initial_fill_ratio)
        initial_fill_ratio = max(0.0, min(1.0, initial_fill_ratio))

    if 1440 % bucket_minutes != 0:
        raise ValueError("bucket_minutes must divide 1440")

    day_start = datetime.fromisoformat(f"{day}T00:00:00")
    day_end = day_start + timedelta(days=1)

    # ----------------------------
    # Load stations
    # ----------------------------
    print(f"{Fore.CYAN}Loading station registry…{Style.RESET_ALL}")
    with open(DEFAULT_TORONTO_STATIONS_FILE) as f:
        stations = json.load(f)["data"]["stations"]

    station_capacity: Dict[str, int] = {
        str(s["station_id"]): int(s["capacity"])
        for s in stations
    }

    # ----------------------------
    # Initialize bikes
    # ----------------------------
    bikes: Dict[str, int] = {}

    if initial_bikes is not None:
        for sid, cap in station_capacity.items():
            bikes[sid] = max(0, min(cap, int(initial_bikes.get(sid, 0))))
        print(f"{Fore.CYAN}Using optimized midnight allocation{Style.RESET_ALL}")
    else:
        for sid, cap in station_capacity.items():
            bikes[sid] = int(round(cap * initial_fill_ratio))
        print(
            f"{Fore.CYAN}Using baseline fill ratio "
            f"{initial_fill_ratio:.2f}{Style.RESET_ALL}"
        )

    # ----------------------------
    # Load trip events
    # ----------------------------
    events = []

    with open(trips_csv_path) as f:
        total_rows = max(0, sum(1 for _ in f) - 1)

    print(f"{Fore.CYAN}Processing trips for {day}…{Style.RESET_ALL}")

    with open(trips_csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in tqdm(reader, total=total_rows, desc="Reading trips"):
            try:
                start_dt = _parse_dt(row["Start Time"])
                end_dt = _parse_dt(row["End Time"])
            except Exception:
                continue

            if not (day_start <= start_dt < day_end):
                continue

            start_sid = str(row.get("Start Station Id", ""))
            end_sid = str(row.get("End Station Id", ""))

            if start_sid in station_capacity:
                events.append((start_dt, "start", start_sid))
            if end_sid in station_capacity:
                events.append((end_dt, "end", end_sid))

    events.sort(key=lambda x: x[0])

    # ----------------------------
    # Simulate day
    # ----------------------------
    print(
        f"{Fore.CYAN}Simulating day "
        f"(bucket_minutes={bucket_minutes})…{Style.RESET_ALL}"
    )

    snapshots = {}
    idx = 0
    bucket_count = 1440 // bucket_minutes

    trucks_remaining = trucks_per_day
    all_truck_moves: List[TruckMove] = []

    for b in range(bucket_count):
        t_min = b * bucket_minutes
        bucket_end = day_start + timedelta(minutes=(b + 1) * bucket_minutes)

        # ---- apply trip events ----
        while idx < len(events) and events[idx][0] < bucket_end:
            _, kind, sid = events[idx]
            cap = station_capacity[sid]

            if kind == "start" and bikes[sid] > 0:
                bikes[sid] -= 1
            elif kind == "end" and bikes[sid] < cap:
                bikes[sid] += 1

            idx += 1

        # ---- 🚚 TRUCK INTERVENTION (AT MOST 1 MOVE PER BUCKET) ----
        if trucks_remaining > 0:
            moves = apply_truck_rebalancing(
                station_bikes=bikes,
                station_capacity=station_capacity,
                t_min=t_min,
                moves_available=1,     # key: spread trucks over the day
                empty_thr=0.20,
                full_thr=0.80,
                target_thr=0.50,
                truck_cap=20,
            )

            if moves:
                trucks_remaining -= len(moves)
                all_truck_moves.extend(moves)

        snapshots[t_min] = bikes.copy()

    # ----------------------------
    # Write CSV
    # ----------------------------
    print(f"{Fore.CYAN}Writing {out_csv_path}…{Style.RESET_ALL}")
    with open(out_csv_path, "w", newline="") as f:
        writer = csv.writer(f)

        if bucket_minutes == 60:
            writer.writerow(["station_id", "hour", "bikes", "empty_docks", "capacity"])
            for t_min, state in snapshots.items():
                hour = t_min // 60
                for sid, b in state.items():
                    cap = station_capacity[sid]
                    writer.writerow([sid, hour, b, cap - b, cap])
        else:
            writer.writerow(["station_id", "t_min", "bikes", "empty_docks", "capacity"])
            for t_min, state in snapshots.items():
                for sid, b in state.items():
                    cap = station_capacity[sid]
                    writer.writerow([sid, t_min, b, cap - b, cap])

    print(
        f"{Fore.MAGENTA}Dispatched {len(all_truck_moves)} truck moves total{Style.RESET_ALL}"
    )
    print(f"{Fore.GREEN}Station state build complete.{Style.RESET_ALL}")

    return all_truck_moves
