# rebalance3/baseline/station_state_by_hour.py
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from tqdm import tqdm
from colorama import Fore, Style, init

from rebalance3.trucks.types import TruckMove
from rebalance3.trucks.simulator import (
    initialize_trucks,
    dispatch_truck_fleet,
    DEFAULT_NUM_TRUCKS,
)

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
    planned_moves: List[TruckMove] | None = None,
):
    """
    Simulate a full day of station states.

    Supports two modes:

    1) Replay mode (GLOBAL planner):
        planned_moves=[TruckMove(...)]
        -> Applies moves at their exact t_min buckets during the day.

    2) Online dispatch mode (GREEDY):
        planned_moves=None and trucks_per_day>0
        -> Calls dispatch_truck_fleet(...) during the day until budget spent.
    """

    # -------------------------------------------------
    # Input checks
    # -------------------------------------------------
    bucket_minutes = int(bucket_minutes)
    if initial_bikes is None:
        initial_fill_ratio = max(0.0, min(1.0, float(initial_fill_ratio)))

    if 1440 % bucket_minutes != 0:
        raise ValueError("bucket_minutes must divide 1440")

    day_start = datetime.fromisoformat(f"{day}T00:00:00")
    day_end = day_start + timedelta(days=1)

    bucket_count = 1440 // bucket_minutes

    # -------------------------------------------------
    # Load stations
    # -------------------------------------------------
    print(f"{Fore.CYAN}Loading station registry…{Style.RESET_ALL}")
    with open(DEFAULT_TORONTO_STATIONS_FILE) as f:
        stations = json.load(f)["data"]["stations"]

    station_capacity: Dict[str, int] = {str(s["station_id"]): int(s["capacity"]) for s in stations}
    station_latlon: Dict[str, Tuple[float, float]] = {
        str(s["station_id"]): (float(s["lat"]), float(s["lon"])) for s in stations
    }

    station_ids = list(station_capacity.keys())

    # -------------------------------------------------
    # Initialize bikes
    # -------------------------------------------------
    bikes: Dict[str, int] = {}

    if initial_bikes is not None:
        for sid, cap in station_capacity.items():
            bikes[sid] = max(0, min(cap, int(initial_bikes.get(sid, 0))))
        print(f"{Fore.CYAN}Using optimized midnight allocation{Style.RESET_ALL}")
    else:
        for sid, cap in station_capacity.items():
            bikes[sid] = int(round(cap * initial_fill_ratio))
        print(f"{Fore.CYAN}Using baseline fill ratio {initial_fill_ratio:.2f}{Style.RESET_ALL}")

    # -------------------------------------------------
    # Load trip events + bucket pickup/dropoff counts
    # -------------------------------------------------
    events = []

    bucket_pickups: Dict[str, List[int]] = {sid: [0] * bucket_count for sid in station_ids}
    bucket_dropoffs: Dict[str, List[int]] = {sid: [0] * bucket_count for sid in station_ids}
    touch_totals: Dict[str, int] = {sid: 0 for sid in station_ids}

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

            s0 = str(row.get("Start Station Id", "")).strip()
            s1 = str(row.get("End Station Id", "")).strip()

            if not s0 or not s1:
                continue

            # only keep stations we know
            if s0 in station_capacity:
                events.append((start_dt, "start", s0))
            if s1 in station_capacity and (day_start <= end_dt < day_end):
                events.append((end_dt, "end", s1))

            # bucketized pickup/dropoff (lookahead features)
            if s0 in station_capacity:
                start_min = int((start_dt - day_start).total_seconds() // 60)
                b_dep = min(bucket_count - 1, max(0, start_min // bucket_minutes))
                bucket_pickups[s0][b_dep] += 1
                touch_totals[s0] += 1

            if s1 in station_capacity and (day_start <= end_dt < day_end):
                end_min = int((end_dt - day_start).total_seconds() // 60)
                b_arr = min(bucket_count - 1, max(0, end_min // bucket_minutes))
                bucket_dropoffs[s1][b_arr] += 1
                touch_totals[s1] += 1

    events.sort(key=lambda x: x[0])

    # -------------------------------------------------
    # Trucks / moves state
    # -------------------------------------------------
    all_truck_moves: List[TruckMove] = []

    # planned move replay mode
    planned_idx = 0
    planned_moves_sorted = None
    if planned_moves:
        planned_moves_sorted = sorted(planned_moves, key=lambda m: (m.t_min or 0))

    # online dispatch mode
    moves_budget_remaining = int(trucks_per_day)
    num_trucks = (
        min(DEFAULT_NUM_TRUCKS, max(1, moves_budget_remaining))
        if moves_budget_remaining > 0
        else 0
    )
    trucks = initialize_trucks(station_ids=station_ids, num_trucks=num_trucks, start_time_min=0)

    # -------------------------------------------------
    # Simulate day
    # -------------------------------------------------
    print(f"{Fore.CYAN}Simulating day (bucket_minutes={bucket_minutes})…{Style.RESET_ALL}")

    snapshots = {}
    idx = 0

    for b in range(bucket_count):
        t_min = b * bucket_minutes
        bucket_end = day_start + timedelta(minutes=(b + 1) * bucket_minutes)

        # ---- apply trip events in this bucket ----
        while idx < len(events) and events[idx][0] < bucket_end:
            _, kind, sid = events[idx]
            cap = station_capacity[sid]

            if kind == "start" and bikes[sid] > 0:
                bikes[sid] -= 1
            elif kind == "end" and bikes[sid] < cap:
                bikes[sid] += 1

            idx += 1

        # ============================================================
        # MODE A: Replay planned moves (global optimization)
        # ============================================================
        if planned_moves_sorted is not None:
            while planned_idx < len(planned_moves_sorted):
                m = planned_moves_sorted[planned_idx]
                mt = int(m.t_min or 0)
                if mt != t_min:
                    break

                src = str(m.from_station)
                snk = str(m.to_station)
                k = int(m.bikes)

                if src in station_capacity and snk in station_capacity and src != snk:
                    cap_src = station_capacity[src]
                    cap_snk = station_capacity[snk]

                    # safety clamp on replay
                    donor_min_left = 3
                    recv_min_empty_left = 2

                    k = min(
                        k,
                        max(0, bikes[src] - donor_min_left),
                        max(0, (cap_snk - bikes[snk]) - recv_min_empty_left),
                    )

                    if k > 0:
                        bikes[src] -= k
                        bikes[snk] += k

                        # record the *actual applied* move (bikes may clamp)
                        all_truck_moves.append(
                            TruckMove(
                                from_station=src,
                                to_station=snk,
                                bikes=int(k),
                                t_min=int(t_min),
                            )
                        )

                planned_idx += 1

        # ============================================================
        # MODE B: Online greedy dispatch (old behavior)
        # ============================================================
        else:
            if moves_budget_remaining > 0 and trucks:
                moves = dispatch_truck_fleet(
                    t_min=t_min,
                    bucket_minutes=bucket_minutes,
                    station_bikes=bikes,
                    station_capacity=station_capacity,
                    station_latlon=station_latlon,
                    bucket_pickups=bucket_pickups,
                    bucket_dropoffs=bucket_dropoffs,
                    touch_totals=touch_totals,
                    trucks=trucks,
                    moves_budget_remaining=moves_budget_remaining,
                    lookahead_minutes=180,
                    truck_cap=20,
                )

                if moves:
                    all_truck_moves.extend(moves)
                    moves_budget_remaining -= len(moves)

        snapshots[t_min] = bikes.copy()

    # -------------------------------------------------
    # Write CSV
    # -------------------------------------------------
    print(f"{Fore.CYAN}Writing {out_csv_path}…{Style.RESET_ALL}")
    with open(out_csv_path, "w", newline="") as f:
        writer = csv.writer(f)

        if bucket_minutes == 60:
            writer.writerow(["station_id", "hour", "bikes", "empty_docks", "capacity"])
            for t_min, state in snapshots.items():
                hour = t_min // 60
                for sid, bcount in state.items():
                    cap = station_capacity[sid]
                    writer.writerow([sid, hour, bcount, cap - bcount, cap])
        else:
            writer.writerow(["station_id", "t_min", "bikes", "empty_docks", "capacity"])
            for t_min, state in snapshots.items():
                for sid, bcount in state.items():
                    cap = station_capacity[sid]
                    writer.writerow([sid, t_min, bcount, cap - bcount, cap])

    print(f"{Fore.MAGENTA}Dispatched {len(all_truck_moves)} truck moves total{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Station state build complete.{Style.RESET_ALL}")

    return all_truck_moves
