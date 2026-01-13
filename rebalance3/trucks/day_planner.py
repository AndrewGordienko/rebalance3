# rebalance3/trucks/day_planner.py
"""
Global (whole-day) truck-move planner with a cost function.

Goal:
  Choose up to K moves over the day to minimize:
    sum over stations and buckets of
      w_empty * max(0, empty_thr*cap - bikes_t)
    + w_full  * max(0, bikes_t - full_thr*cap)

This is the "midnight optimizer" idea extended across time.

Notes / design:
- Uses bucketized trips (arrivals - departures) to simulate station trajectories.
- Picks moves greedily, but with GLOBAL objective:
    at each step, select the single move that yields the largest total cost drop.
- Fast evaluation: when testing a move at time bucket b0, only recompute cost
  for the two affected stations (src, snk) from b0 onward.
- No pacing hacks, no hard caps by hour. If evening moves help more, it will pick them.

Typical usage (in your scenario wrapper):
  moves = plan_truck_moves_for_day(
      trips_csv_path=TRIPS,
      day=DAY,
      initial_bikes=initial_bikes,
      bucket_minutes=15,
      moves_budget=10,
  )

Then, to produce a "state CSV with trucks", replay those moves inside your
event-based simulator (apply them at their t_min buckets).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Iterable

from rebalance3.trucks.types import TruckMove


TIME_FMT = "%m/%d/%Y %H:%M"

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


# -----------------------------
# Trip parsing + bucketing
# -----------------------------
def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, TIME_FMT)


def load_station_info(
    stations_file: str | Path = DEFAULT_TORONTO_STATIONS_FILE,
) -> Tuple[Dict[str, int], Dict[str, Tuple[float, float]]]:
    with open(stations_file) as f:
        stations = json.load(f)["data"]["stations"]

    cap: Dict[str, int] = {}
    latlon: Dict[str, Tuple[float, float]] = {}
    for s in stations:
        sid = str(s.get("station_id"))
        c = s.get("capacity")
        if sid and c is not None:
            try:
                cap[sid] = int(c)
                latlon[sid] = (float(s["lat"]), float(s["lon"]))
            except Exception:
                continue
    return cap, latlon


@dataclass
class BucketedTrips:
    # net change per bucket: arrivals - departures
    delta_by_station: Dict[str, List[int]]
    pickups_by_station: Dict[str, List[int]]
    dropoffs_by_station: Dict[str, List[int]]
    touch_totals: Dict[str, int]
    bucket_minutes: int
    bucket_count: int


def bucketize_trips(
    *,
    trips_csv_path: str | Path,
    day: str,  # YYYY-MM-DD
    capacity_by_station: Dict[str, int],
    bucket_minutes: int = 15,
    encoding: str = "utf-8-sig",
) -> BucketedTrips:
    bucket_minutes = int(bucket_minutes)
    if bucket_minutes <= 0 or 1440 % bucket_minutes != 0:
        raise ValueError("bucket_minutes must be > 0 and divide 1440")

    day_start = datetime.fromisoformat(f"{day}T00:00:00")
    day_end = day_start + timedelta(days=1)
    bucket_count = 1440 // bucket_minutes

    sids = list(capacity_by_station.keys())

    delta_by_station: Dict[str, List[int]] = {sid: [0] * bucket_count for sid in sids}
    pickups_by_station: Dict[str, List[int]] = {sid: [0] * bucket_count for sid in sids}
    dropoffs_by_station: Dict[str, List[int]] = {sid: [0] * bucket_count for sid in sids}
    touch_totals: Dict[str, int] = {sid: 0 for sid in sids}

    with open(trips_csv_path, newline="", encoding=encoding, errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                start_dt = _parse_dt(row["Start Time"])
                end_dt = _parse_dt(row["End Time"])
            except Exception:
                continue

            if not (day_start <= start_dt < day_end):
                continue

            s0 = str(row.get("Start Station Id", "")).strip()
            s1 = str(row.get("End Station Id", "")).strip()
            if not s0 or not s1 or s0 == s1:
                continue
            if s0 not in capacity_by_station or s1 not in capacity_by_station:
                continue

            start_min = int((start_dt - day_start).total_seconds() // 60)
            b_dep = min(bucket_count - 1, max(0, start_min // bucket_minutes))
            delta_by_station[s0][b_dep] -= 1
            pickups_by_station[s0][b_dep] += 1
            touch_totals[s0] += 1

            if day_start <= end_dt < day_end:
                end_min = int((end_dt - day_start).total_seconds() // 60)
                b_arr = min(bucket_count - 1, max(0, end_min // bucket_minutes))
                delta_by_station[s1][b_arr] += 1
                dropoffs_by_station[s1][b_arr] += 1
                touch_totals[s1] += 1

    return BucketedTrips(
        delta_by_station=delta_by_station,
        pickups_by_station=pickups_by_station,
        dropoffs_by_station=dropoffs_by_station,
        touch_totals=touch_totals,
        bucket_minutes=bucket_minutes,
        bucket_count=bucket_count,
    )


# -----------------------------
# Cost + trajectory
# -----------------------------
def _simulate_series(
    *,
    x0: int,
    cap: int,
    delta: List[int],
) -> List[int]:
    """
    Returns bikes-at-start-of-bucket series (length = len(delta)).
    We store bikes at the START of each bucket b.

    Update rule:
      x[b+1] = clamp(x[b] + delta[b], 0..cap)
    """
    if cap <= 0:
        return [0 for _ in delta]

    out = [0] * len(delta)
    x = int(max(0, min(cap, x0)))
    for b in range(len(delta)):
        out[b] = x
        x = x + int(delta[b])
        if x < 0:
            x = 0
        elif x > cap:
            x = cap
    return out


def _cost_from_bucket(
    *,
    start_b: int,
    x_start: int,
    cap: int,
    delta: List[int],
    empty_thr: float,
    full_thr: float,
    w_empty: float,
    w_full: float,
) -> float:
    """
    Cost from bucket start_b to end-of-day, assuming bikes at START of start_b is x_start.
    Uses bikes-at-start-of-bucket for penalty (consistent and fast).
    """
    if cap <= 0:
        return 0.0

    empty_level = float(empty_thr) * cap
    full_level = float(full_thr) * cap

    x = int(max(0, min(cap, x_start)))
    cost = 0.0

    for b in range(start_b, len(delta)):
        # penalty at start of bucket b
        if x < empty_level:
            cost += w_empty * (empty_level - x)
        if x > full_level:
            cost += w_full * (x - full_level)

        # evolve to next bucket start
        x = x + int(delta[b])
        if x < 0:
            x = 0
        elif x > cap:
            x = cap

    return float(cost)


def _future_sum(series: List[int], start_b: int, lookahead_b: int) -> int:
    if not series:
        return 0
    end = min(len(series), start_b + lookahead_b)
    s = 0
    for i in range(start_b, end):
        s += int(series[i])
    return int(s)


def _priority(touches: int) -> float:
    return float(math.log1p(max(0, int(touches))))


def _sink_risk(
    *,
    sid: str,
    bikes_now: int,
    cap: int,
    b: int,
    pickups: List[int],
    lookahead_b: int,
    empty_thr: float,
    touches: int,
) -> float:
    if cap <= 0:
        return 0.0
    empty_level = int(round(empty_thr * cap))
    empty_now = max(0, empty_level - bikes_now)

    fut_pickups = _future_sum(pickups, b + 1, lookahead_b)
    shortage = max(0, fut_pickups - bikes_now)

    base = float(empty_now) + float(shortage)
    if base <= 0:
        return 0.0
    return base * _priority(touches)


def _source_risk(
    *,
    sid: str,
    bikes_now: int,
    cap: int,
    b: int,
    dropoffs: List[int],
    lookahead_b: int,
    full_thr: float,
    touches: int,
) -> float:
    if cap <= 0:
        return 0.0
    full_level = int(round(full_thr * cap))
    full_now = max(0, bikes_now - full_level)

    empty_now = cap - bikes_now
    fut_dropoffs = _future_sum(dropoffs, b + 1, lookahead_b)
    overflow = max(0, fut_dropoffs - empty_now)

    base = float(full_now) + float(overflow)
    if base <= 0:
        return 0.0
    return base * _priority(touches)


# -----------------------------
# Planner
# -----------------------------
def plan_truck_moves_for_day(
    *,
    trips_csv_path: str | Path,
    day: str,
    initial_bikes: Dict[str, int],
    bucket_minutes: int = 15,
    moves_budget: int = 10,
    truck_cap: int = 20,
    donor_min_bikes_left: int = 3,
    receiver_min_empty_docks_left: int = 2,
    lookahead_minutes: int = 180,
    empty_thr: float = 0.10,
    full_thr: float = 0.90,
    w_empty: float = 1.0,
    w_full: float = 1.0,
    candidate_time_top_k: int = 24,
    top_k_sources: int = 25,
    top_k_sinks: int = 25,
    stations_file: str | Path = DEFAULT_TORONTO_STATIONS_FILE,
    encoding: str = "utf-8-sig",
) -> List[TruckMove]:
    """
    Returns a list of TruckMove with chosen t_min over the day.
    """
    moves_budget = int(moves_budget)
    if moves_budget <= 0:
        return []

    cap, _latlon = load_station_info(stations_file)
    sids = list(cap.keys())
    if not sids:
        return []

    trips = bucketize_trips(
        trips_csv_path=trips_csv_path,
        day=day,
        capacity_by_station=cap,
        bucket_minutes=bucket_minutes,
        encoding=encoding,
    )

    B = trips.bucket_count
    lookahead_b = max(1, int(lookahead_minutes // bucket_minutes))

    # clamp initial bikes
    x0: Dict[str, int] = {}
    for sid in sids:
        c = cap[sid]
        x0[sid] = int(max(0, min(c, int(initial_bikes.get(sid, 0)))))

    # baseline series for all stations (bikes at start of each bucket)
    series: Dict[str, List[int]] = {}
    for sid in sids:
        series[sid] = _simulate_series(x0=x0[sid], cap=cap[sid], delta=trips.delta_by_station[sid])

    # baseline total cost per station (from bucket 0)
    cost_station: Dict[str, float] = {}
    for sid in sids:
        cost_station[sid] = _cost_from_bucket(
            start_b=0,
            x_start=series[sid][0] if B > 0 else x0[sid],
            cap=cap[sid],
            delta=trips.delta_by_station[sid],
            empty_thr=empty_thr,
            full_thr=full_thr,
            w_empty=w_empty,
            w_full=w_full,
        )

    def total_cost() -> float:
        return float(sum(cost_station.values()))

    # pick candidate times: data-driven, where the system is "most bad"
    # badness(b) = total empty-depth + full-depth across stations at bucket b
    empty_levels = {sid: empty_thr * cap[sid] for sid in sids}
    full_levels = {sid: full_thr * cap[sid] for sid in sids}

    badness: List[Tuple[float, int]] = []
    for b in range(B):
        s = 0.0
        for sid in sids:
            x = series[sid][b]
            el = empty_levels[sid]
            fl = full_levels[sid]
            if x < el:
                s += (el - x)
            if x > fl:
                s += (x - fl)
        badness.append((s, b))

    badness.sort(reverse=True)
    candidate_buckets = sorted(set(b for _, b in badness[: max(8, candidate_time_top_k)]))

    # also add a coarse grid so we don't miss good times if badness is noisy
    step = max(1, int((60 // bucket_minutes)))  # ~hourly
    for b in range(0, B, step):
        candidate_buckets.append(b)
    candidate_buckets = sorted(set(candidate_buckets))

    planned: List[TruckMove] = []

    # Greedy K-step planning (global cost drop)
    for _ in range(moves_budget):
        best_improvement = 0.0
        best_choice = None  # (b0, src, snk, moved)

        current_total_cost = total_cost()

        for b0 in candidate_buckets:
            # choose top sinks/sources at this time (risk-based, data-driven)
            sinks = sorted(
                sids,
                key=lambda sid: _sink_risk(
                    sid=sid,
                    bikes_now=series[sid][b0],
                    cap=cap[sid],
                    b=b0,
                    pickups=trips.pickups_by_station[sid],
                    lookahead_b=lookahead_b,
                    empty_thr=empty_thr,
                    touches=trips.touch_totals.get(sid, 0),
                ),
                reverse=True,
            )[:top_k_sinks]

            sources = sorted(
                sids,
                key=lambda sid: _source_risk(
                    sid=sid,
                    bikes_now=series[sid][b0],
                    cap=cap[sid],
                    b=b0,
                    dropoffs=trips.dropoffs_by_station[sid],
                    lookahead_b=lookahead_b,
                    full_thr=full_thr,
                    touches=trips.touch_totals.get(sid, 0),
                ),
                reverse=True,
            )[:top_k_sources]

            if not sinks or not sources:
                continue

            for src in sources:
                bikes_src = series[src][b0]
                if bikes_src <= donor_min_bikes_left:
                    continue

                for snk in sinks:
                    if snk == src:
                        continue

                    bikes_snk = series[snk][b0]
                    empty_snk = cap[snk] - bikes_snk
                    if empty_snk <= receiver_min_empty_docks_left:
                        continue

                    moved = min(
                        int(truck_cap),
                        int(bikes_src - donor_min_bikes_left),
                        int(empty_snk - receiver_min_empty_docks_left),
                    )
                    if moved <= 0:
                        continue

                    # compute local cost change (only src + snk from b0 onward)
                    # baseline local cost from b0:
                    base_src = _cost_from_bucket(
                        start_b=b0,
                        x_start=series[src][b0],
                        cap=cap[src],
                        delta=trips.delta_by_station[src],
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                    )
                    base_snk = _cost_from_bucket(
                        start_b=b0,
                        x_start=series[snk][b0],
                        cap=cap[snk],
                        delta=trips.delta_by_station[snk],
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                    )

                    # after applying move at start of b0
                    new_src = _cost_from_bucket(
                        start_b=b0,
                        x_start=series[src][b0] - moved,
                        cap=cap[src],
                        delta=trips.delta_by_station[src],
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                    )
                    new_snk = _cost_from_bucket(
                        start_b=b0,
                        x_start=series[snk][b0] + moved,
                        cap=cap[snk],
                        delta=trips.delta_by_station[snk],
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                    )

                    improvement = (base_src + base_snk) - (new_src + new_snk)
                    if improvement > best_improvement + 1e-9:
                        best_improvement = improvement
                        best_choice = (b0, src, snk, moved)

        if best_choice is None or best_improvement <= 1e-9:
            break

        # Commit best move: update trajectories + cached costs for src/snk
        b0, src, snk, moved = best_choice

        # Update series for src and snk from b0 onward by re-simulating only those two
        # Need the bikes-at-start-of-b0 after all previous moves: that's current series[src][b0], etc.
        # Apply move at start of b0, then re-sim forward.
        def resim_from_b0(sid: str, new_x_b0: int):
            # rebuild bikes-at-start series from b0 onward, keeping prefix unchanged
            prefix = series[sid][:b0]
            tail = _simulate_series(
                x0=new_x_b0,
                cap=cap[sid],
                delta=trips.delta_by_station[sid][b0:],
            )
            series[sid] = prefix + tail

            # refresh full-day cost cache for that station (cheap: 96 buckets)
            cost_station[sid] = _cost_from_bucket(
                start_b=0,
                x_start=series[sid][0] if B > 0 else new_x_b0,
                cap=cap[sid],
                delta=trips.delta_by_station[sid],
                empty_thr=empty_thr,
                full_thr=full_thr,
                w_empty=w_empty,
                w_full=w_full,
            )

        resim_from_b0(src, series[src][b0] - moved)
        resim_from_b0(snk, series[snk][b0] + moved)

        planned.append(
            TruckMove(
                from_station=str(src),
                to_station=str(snk),
                bikes=int(moved),
                t_min=int(b0 * bucket_minutes),
            )
        )

        # (Optional) if you want to keep candidate_buckets adaptive, you can recompute badness here.
        # For now, keep fixed set for speed.

        _ = current_total_cost  # silence linters

    # Sort by time (nice for replay)
    planned.sort(key=lambda m: (m.t_min if m.t_min is not None else 0))
    return planned
