# rebalance3/baseline/station_state_by_hour.py
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from tqdm import tqdm
except Exception:
    tqdm = None


# Optional: pretty prints if you have colorama installed
try:
    from colorama import Fore, Style
except Exception:  # pragma: no cover
    class _Dummy:
        def __getattr__(self, k):  # noqa
            return ""
    Fore = _Dummy()
    Style = _Dummy()


from rebalance3.trucks.types import TruckMove

# If you still want online dispatch mode, keep this import.
# If you don't want it anymore, you can delete the whole "online dispatch" section below.
from rebalance3.trucks.simulator import apply_truck_rebalancing


TIME_FMT = "%m/%d/%Y %H:%M"

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, TIME_FMT)


def build_station_state_by_hour(
    *,
    trips_csv_path: str | Path,
    day: str,  # YYYY-MM-DD
    out_csv_path: str | Path,
    bucket_minutes: int = 15,

    # baseline init option
    initial_fill_ratio: float | None = 0.60,

    # exact midnight init override (used by midnight scenario + truck scenario)
    initial_bikes: Dict[str, int] | None = None,

    # ----------------------------
    # Online dispatch mode (old)
    # ----------------------------
    trucks_per_day: int = 0,

    # ----------------------------
    # Replay mode (NEW)
    # ----------------------------
    planned_moves: List[TruckMove] | None = None,

    # If provided, replay planned moves but cap how many can occur inside 1 hour.
    # Example: moves_per_hour=5 means we only apply up to 5 planned moves in hour 10.
    moves_per_hour: int | None = None,
) -> List[TruckMove]:
    """
    Builds a state CSV of station bikes over time (bucket_minutes).

    Supports 3 modes:
      1) baseline: no trucks at all
      2) online dispatch: trucks_per_day > 0 (greedy policy each bucket)
      3) replay planner: planned_moves is provided (apply those timed moves)

    Returns:
      List[TruckMove] that were actually applied.
      (These might differ slightly from planned if clamped by caps/availability.)
    """

    bucket_minutes = int(bucket_minutes)
    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be > 0")
    if 1440 % bucket_minutes != 0:
        raise ValueError("bucket_minutes must divide 1440 (e.g., 60, 30, 15, 10, 5, 1)")

    day_start = datetime.fromisoformat(f"{day}T00:00:00")
    day_end = day_start + timedelta(days=1)

    # -------------------------------------------------
    # Load stations (capacity map)
    # -------------------------------------------------
    print(f"{Fore.CYAN}Loading station registry…{Style.RESET_ALL}")
    with open(DEFAULT_TORONTO_STATIONS_FILE) as f:
        stations = json.load(f)["data"]["stations"]

    station_capacity: Dict[str, int] = {}
    for s in stations:
        sid = str(s.get("station_id"))
        cap = s.get("capacity", None)
        if sid and cap is not None:
            try:
                station_capacity[sid] = int(cap)
            except Exception:
                continue

    # -------------------------------------------------
    # Initialize bikes at midnight
    # -------------------------------------------------
    bikes: Dict[str, int] = {}
    if initial_bikes is not None:
        print(f"{Fore.CYAN}Using provided midnight bike distribution{Style.RESET_ALL}")
        for sid, cap in station_capacity.items():
            b0 = int(initial_bikes.get(sid, 0))
            if b0 < 0:
                b0 = 0
            if b0 > cap:
                b0 = cap
            bikes[sid] = b0
    else:
        # baseline proportional fill
        if initial_fill_ratio is None:
            initial_fill_ratio = 0.60

        r = float(initial_fill_ratio)
        r = max(0.0, min(1.0, r))

        print(f"{Fore.CYAN}Using baseline fill ratio {r:.2f}{Style.RESET_ALL}")
        for sid, cap in station_capacity.items():
            bikes[sid] = int(round(cap * r))

    # -------------------------------------------------
    # Load trip events
    # -------------------------------------------------
    print(f"{Fore.CYAN}Processing trips for {day}…{Style.RESET_ALL}")

    events: List[Tuple[datetime, str, str]] = []

    # progress sizing (optional)
    total_rows = None
    try:
        with open(trips_csv_path, "r", encoding="utf-8-sig", errors="replace") as f:
            total_rows = max(0, sum(1 for _ in f) - 1)
    except Exception:
        total_rows = None

    f = open(trips_csv_path, newline="", encoding="utf-8-sig", errors="replace")
    try:
        reader = csv.DictReader(f)
        it = reader
        if tqdm is not None and total_rows is not None:
            it = tqdm(reader, total=total_rows, desc="Reading trips")

        for row in it:
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
            if s0 == s1:
                continue
            if s0 not in station_capacity or s1 not in station_capacity:
                continue

            events.append((start_dt, "start", s0))
            if day_start <= end_dt < day_end:
                events.append((end_dt, "end", s1))
    finally:
        f.close()

    events.sort(key=lambda x: x[0])

    # -------------------------------------------------
    # Prepare planner replay table: moves_by_tmin
    # -------------------------------------------------
    moves_by_tmin: Dict[int, List[TruckMove]] = {}
    if planned_moves:
        for m in planned_moves:
            tm = getattr(m, "t_min", None)
            if tm is None:
                continue
            try:
                tm = int(tm)
            except Exception:
                continue
            moves_by_tmin.setdefault(tm, []).append(m)

    # Optional cap per hour for replay
    moves_per_hour = None if moves_per_hour is None else int(moves_per_hour)
    if moves_per_hour is not None and moves_per_hour < 0:
        moves_per_hour = 0
    applied_in_hour: Dict[int, int] = {}

    # -------------------------------------------------
    # Simulate day in buckets
    # -------------------------------------------------
    print(
        f"{Fore.CYAN}Simulating day (bucket_minutes={bucket_minutes})…{Style.RESET_ALL}"
    )

    snapshots: Dict[int, Dict[str, int]] = {}
    all_truck_moves: List[TruckMove] = []

    idx = 0
    for t_min in range(0, 1440, bucket_minutes):
        t0 = day_start + timedelta(minutes=t_min)
        t1 = t0 + timedelta(minutes=bucket_minutes)

        # ----------------------------
        # Apply all trip events in this bucket
        # ----------------------------
        while idx < len(events) and events[idx][0] < t1:
            _dt, kind, sid = events[idx]

            cap = station_capacity.get(sid, 0)
            if cap <= 0:
                idx += 1
                continue

            if kind == "start":
                # bike departs station
                if bikes.get(sid, 0) > 0:
                    bikes[sid] -= 1
            else:
                # bike arrives to station
                if bikes.get(sid, 0) < cap:
                    bikes[sid] += 1

            idx += 1

        # ----------------------------
        # (A) REPLAY planned moves at exactly this t_min
        # ----------------------------
        if planned_moves:
            hour = t_min // 60

            # hourly cap
            already = applied_in_hour.get(hour, 0)
            remaining_this_hour = None
            if moves_per_hour is not None:
                remaining_this_hour = max(0, moves_per_hour - already)

            moves_here = moves_by_tmin.get(int(t_min), [])

            for mv in moves_here:
                if remaining_this_hour is not None and remaining_this_hour <= 0:
                    break

                src = str(mv.from_station)
                dst = str(mv.to_station)

                if src not in station_capacity or dst not in station_capacity:
                    continue

                cap_src = station_capacity[src]
                cap_dst = station_capacity[dst]

                cur_src = bikes.get(src, 0)
                cur_dst = bikes.get(dst, 0)

                # clamp moved bikes to feasibility
                desired = int(mv.bikes)
                if desired <= 0:
                    continue

                can_take = cur_src
                can_put = cap_dst - cur_dst
                moved = min(desired, can_take, can_put)

                if moved <= 0:
                    continue

                bikes[src] = cur_src - moved
                bikes[dst] = cur_dst + moved

                all_truck_moves.append(
                    TruckMove(
                        t_min=int(t_min),
                        from_station=src,
                        to_station=dst,
                        bikes=int(moved),
                    )
                )

                applied_in_hour[hour] = applied_in_hour.get(hour, 0) + 1
                if remaining_this_hour is not None:
                    remaining_this_hour -= 1

        # ----------------------------
        # (B) ONLINE dispatch mode (optional legacy behavior)
        # ----------------------------
        # If you're replaying, you probably want this OFF.
        if (not planned_moves) and trucks_per_day > 0:
            # This older logic spends moves greedily.
            # If you still want it, keep it.
            moves = apply_truck_rebalancing(
                station_bikes=bikes,
                station_capacity=station_capacity,
                t_min=t_min,
                moves_available=1,
                empty_thr=0.20,
                full_thr=0.80,
                target_thr=0.50,
                truck_cap=20,
            )

            for m in moves:
                # force alignment with bucket start
                m.t_min = int(t_min)
                all_truck_moves.append(m)

            trucks_per_day -= len(moves)

        snapshots[t_min] = bikes.copy()

    # -------------------------------------------------
    # Write CSV
    # -------------------------------------------------
    print(f"{Fore.CYAN}Writing {out_csv_path}…{Style.RESET_ALL}")
    with open(out_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        if bucket_minutes == 60:
            writer.writerow(["station_id", "hour", "bikes", "empty_docks", "capacity"])
            for t_min, st in snapshots.items():
                hour = t_min // 60
                for sid, b in st.items():
                    cap = station_capacity[sid]
                    writer.writerow([sid, hour, b, cap - b, cap])
        else:
            writer.writerow(["station_id", "t_min", "bikes", "empty_docks", "capacity"])
            for t_min, st in snapshots.items():
                for sid, b in st.items():
                    cap = station_capacity[sid]
                    writer.writerow([sid, t_min, b, cap - b, cap])

    print(
        f"{Fore.MAGENTA}Dispatched {len(all_truck_moves)} truck moves total{Style.RESET_ALL}"
    )
    print(f"{Fore.GREEN}Station state build complete.{Style.RESET_ALL}")

    return all_truck_moves
