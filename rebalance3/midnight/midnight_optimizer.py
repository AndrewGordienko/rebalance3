# rebalance3/baseline/midnight_optimizer.py
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Tuple, Optional

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover
    tqdm = None


TIME_FMT = "%m/%d/%Y %H:%M"
_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"

@dataclass
class MidnightOptimizeResult:
    bikes_by_station: Dict[str, int]
    capacity_by_station: Dict[str, int]
    bucket_minutes: int
    total_bikes: int
    weights: Tuple[float, float]  # (w_empty, w_full)
    thresholds: Tuple[float, float]  # (empty_thr, full_thr)
    initial_cost: float
    final_cost: float
    moves: int


def _parse_dt(s: str) -> datetime:
    return datetime.strptime(s, TIME_FMT)


def load_capacity_from_station_information(stations_file: str | Path) -> Dict[str, int]:
    with open(stations_file) as f:
        stations = json.load(f)["data"]["stations"]

    cap = {}
    for s in stations:
        sid = str(s.get("station_id"))
        c = s.get("capacity")
        if sid and c is not None:
            try:
                cap[sid] = int(c)
            except Exception:
                continue
    return cap


def build_bucket_flows(
    trips_csv_path: str | Path,
    day: str,  # YYYY-MM-DD
    capacity_by_station: Dict[str, int],
    bucket_minutes: int = 15,
    encoding: str = "utf-8-sig",
) -> Tuple[Dict[str, List[int]], List[int]]:
    """
    Returns:
      delta_by_station[sid][b] = arrivals - departures in bucket b
      valid_times = list of t_min (minutes since midnight) for each bucket start
    """
    bucket_minutes = int(bucket_minutes)
    if bucket_minutes <= 0:
        raise ValueError("bucket_minutes must be > 0")
    if 1440 % bucket_minutes != 0:
        raise ValueError("bucket_minutes must divide 1440 (e.g., 60, 30, 15, 10, 5, 1)")

    day_start = datetime.fromisoformat(f"{day}T00:00:00")
    day_end = day_start + timedelta(days=1)

    bucket_count = 1440 // bucket_minutes
    valid_times = [b * bucket_minutes for b in range(bucket_count)]

    # init deltas
    delta_by_station: Dict[str, List[int]] = {
        sid: [0] * bucket_count for sid in capacity_by_station.keys()
    }

    # progress sizing (optional)
    total_rows = None
    try:
        with open(trips_csv_path, "r", encoding=encoding, errors="replace") as f:
            total_rows = max(0, sum(1 for _ in f) - 1)
    except Exception:
        total_rows = None

    reader_iter = None
    f = open(trips_csv_path, newline="", encoding=encoding, errors="replace")
    try:
        reader = csv.DictReader(f)
        reader_iter = reader
        if tqdm is not None and total_rows is not None:
            reader_iter = tqdm(reader, total=total_rows, desc="Aggregating bucket flows")

        for row in reader_iter:
            try:
                start_dt = _parse_dt(row["Start Time"])
                end_dt = _parse_dt(row["End Time"])
            except Exception:
                continue

            # Only model events occurring within [day_start, day_end)
            if not (day_start <= start_dt < day_end):
                continue

            start_sid = str(row.get("Start Station Id", "")).strip()
            end_sid = str(row.get("End Station Id", "")).strip()

            if not start_sid or not end_sid:
                continue
            if start_sid == end_sid:
                continue
            if start_sid not in capacity_by_station or end_sid not in capacity_by_station:
                continue

            # departure bucket based on start time
            start_min = int((start_dt - day_start).total_seconds() // 60)
            b_dep = min(bucket_count - 1, max(0, start_min // bucket_minutes))
            delta_by_station[start_sid][b_dep] -= 1

            # arrival bucket based on end time IF it lands same day; otherwise ignore
            if day_start <= end_dt < day_end:
                end_min = int((end_dt - day_start).total_seconds() // 60)
                b_arr = min(bucket_count - 1, max(0, end_min // bucket_minutes))
                delta_by_station[end_sid][b_arr] += 1

    finally:
        f.close()

    return delta_by_station, valid_times


def _station_cost(
    x0: int,
    cap: int,
    delta: List[int],
    empty_thr: float,
    full_thr: float,
    w_empty: float,
    w_full: float,
) -> float:
    """
    Cost for one station over the day, given initial x0 at midnight and per-bucket deltas.
    Uses a smooth-ish "depth" penalty around empty/full thresholds.
    """
    if cap <= 0:
        return 0.0

    empty_level = empty_thr * cap
    full_level = full_thr * cap

    bikes = x0
    cost = 0.0
    cum = 0

    for d in delta:
        cum += d
        bikes_t = bikes + cum
        if bikes_t < 0:
            bikes_t = 0
        elif bikes_t > cap:
            bikes_t = cap

        # depth penalties
        empty_depth = empty_level - bikes_t
        if empty_depth > 0:
            cost += w_empty * empty_depth

        full_depth = bikes_t - full_level
        if full_depth > 0:
            cost += w_full * full_depth

    return float(cost)


def _initialize_bikes_proportional(
    capacity_by_station: Dict[str, int],
    total_bikes: int,
) -> Dict[str, int]:
    """
    Start vector: proportional to capacity, clamped, exact sum=total_bikes (if feasible).
    """
    caps = capacity_by_station
    sids = list(caps.keys())
    total_cap = sum(max(0, caps[sid]) for sid in sids)
    if total_cap <= 0:
        return {sid: 0 for sid in sids}

    # If total_bikes exceeds total capacity, clamp to total cap.
    total_bikes = min(total_bikes, total_cap)
    total_bikes = max(total_bikes, 0)

    x = {}
    # initial rounding
    raw = []
    for sid in sids:
        cap = max(0, caps[sid])
        val = (cap / total_cap) * total_bikes
        base = int(val)
        frac = val - base
        x[sid] = min(cap, max(0, base))
        raw.append((frac, sid))

    # distribute remainder by largest fractional part
    cur_sum = sum(x.values())
    remaining = total_bikes - cur_sum

    if remaining > 0:
        raw.sort(reverse=True)
        i = 0
        while remaining > 0 and i < len(raw):
            sid = raw[i][1]
            if x[sid] < caps[sid]:
                x[sid] += 1
                remaining -= 1
            i += 1
            if i == len(raw) and remaining > 0:
                # another pass if needed
                i = 0

    elif remaining < 0:
        # remove bikes from largest x first
        donors = sorted(((x[sid], sid) for sid in sids), reverse=True)
        remaining = -remaining
        i = 0
        while remaining > 0 and i < len(donors):
            sid = donors[i][1]
            if x[sid] > 0:
                x[sid] -= 1
                remaining -= 1
            i += 1
            if i == len(donors) and remaining > 0:
                i = 0

    return x


def optimize_midnight_greedy(
    delta_by_station: Dict[str, List[int]],
    capacity_by_station: Dict[str, int],
    total_bikes: int,
    *,
    bucket_minutes: int = 15,
    empty_threshold: float = 0.10,
    full_threshold: float = 0.90,
    w_empty: float = 1.0,
    w_full: float = 1.0,
    max_moves: int | None = None,
) -> MidnightOptimizeResult:
    """
    Greedy 1-bike swap optimizer.

    Because each station’s trajectory depends only on its own x_i and its own delta_i,
    gains for a station depend only on that station’s x_i. That makes this greedy
    approach fast: update only donor+receiver gains each move.
    """
    if not delta_by_station:
        return MidnightOptimizeResult(
            bikes_by_station={},
            capacity_by_station=dict(capacity_by_station),
            bucket_minutes=bucket_minutes,
            total_bikes=0,
            weights=(w_empty, w_full),
            thresholds=(empty_threshold, full_threshold),
            initial_cost=0.0,
            final_cost=0.0,
            moves=0,
        )

    # Ensure all stations exist in both dicts
    sids = [sid for sid in capacity_by_station.keys() if sid in delta_by_station]
    if not sids:
        return MidnightOptimizeResult(
            bikes_by_station={},
            capacity_by_station=dict(capacity_by_station),
            bucket_minutes=bucket_minutes,
            total_bikes=0,
            weights=(w_empty, w_full),
            thresholds=(empty_threshold, full_threshold),
            initial_cost=0.0,
            final_cost=0.0,
            moves=0,
        )

    # clamp total bikes to feasible range
    total_cap = sum(max(0, capacity_by_station[sid]) for sid in sids)
    total_bikes = int(total_bikes)
    total_bikes = max(0, min(total_bikes, total_cap))

    # initial x
    x = _initialize_bikes_proportional(
        {sid: capacity_by_station[sid] for sid in sids},
        total_bikes,
    )

    # per-station cost cache
    cost = {}
    gain_plus = {}   # improvement if x += 1
    gain_minus = {}  # improvement if x -= 1

    def recompute_station(sid: str):
        cap = int(capacity_by_station[sid])
        d = delta_by_station[sid]
        xi = int(x[sid])

        c0 = _station_cost(xi, cap, d, empty_threshold, full_threshold, w_empty, w_full)
        cost[sid] = c0

        if xi < cap:
            c1 = _station_cost(xi + 1, cap, d, empty_threshold, full_threshold, w_empty, w_full)
            gain_plus[sid] = c0 - c1
        else:
            gain_plus[sid] = float("-inf")

        if xi > 0:
            c_1 = _station_cost(xi - 1, cap, d, empty_threshold, full_threshold, w_empty, w_full)
            gain_minus[sid] = c0 - c_1
        else:
            gain_minus[sid] = float("-inf")

    for sid in sids:
        recompute_station(sid)

    def total_cost() -> float:
        return float(sum(cost[sid] for sid in sids))

    initial_total = total_cost()

    # move limit
    if max_moves is None:
        # sensible default: allow up to 2 passes worth of bikes
        max_moves = max(1000, total_bikes)

    moves = 0
    for _ in range(int(max_moves)):
        # best receiver: max gain_plus
        receiver = max(sids, key=lambda sid: gain_plus[sid])
        best_plus = gain_plus[receiver]

        # best donor: max gain_minus
        donor = max(sids, key=lambda sid: gain_minus[sid])
        best_minus = gain_minus[donor]

        # avoid donor==receiver: pick next best by temporary suppression
        if donor == receiver:
            # try alternate receiver
            tmp = gain_plus[receiver]
            gain_plus[receiver] = float("-inf")
            receiver2 = max(sids, key=lambda sid: gain_plus[sid])
            best_plus2 = gain_plus[receiver2]
            gain_plus[receiver] = tmp

            # try alternate donor
            tmp2 = gain_minus[donor]
            gain_minus[donor] = float("-inf")
            donor2 = max(sids, key=lambda sid: gain_minus[sid])
            best_minus2 = gain_minus[donor2]
            gain_minus[donor] = tmp2

            # choose better combination
            if best_plus2 != float("-inf") and best_minus != float("-inf") and (best_plus2 + best_minus) >= (best_plus + best_minus2):
                receiver, best_plus = receiver2, best_plus2
            else:
                donor, best_minus = donor2, best_minus2

        improvement = best_plus + best_minus
        if not (improvement > 1e-9):
            break

        # apply move: donor -> receiver
        if x[donor] <= 0:
            break
        if x[receiver] >= capacity_by_station[receiver]:
            break

        x[donor] -= 1
        x[receiver] += 1

        # update only affected stations (true independence)
        recompute_station(donor)
        recompute_station(receiver)

        moves += 1

    final_total = total_cost()

    return MidnightOptimizeResult(
        bikes_by_station=dict(x),
        capacity_by_station={sid: int(capacity_by_station[sid]) for sid in sids},
        bucket_minutes=int(bucket_minutes),
        total_bikes=int(total_bikes),
        weights=(float(w_empty), float(w_full)),
        thresholds=(float(empty_threshold), float(full_threshold)),
        initial_cost=float(initial_total),
        final_cost=float(final_total),
        moves=int(moves),
    )


def optimize_midnight_from_trips(
    trips_csv_path: str | Path,
    day: str,
    *,
    bucket_minutes: int = 15,
    total_bikes: int | None = None,
    total_bikes_ratio: float | None = 0.60,
    empty_threshold: float = 0.10,
    full_threshold: float = 0.90,
    w_empty: float = 1.0,
    w_full: float = 1.0,
    max_moves: int | None = None,
) -> MidnightOptimizeResult:
    """
    Convenience wrapper:
      - loads capacities
      - builds bucket deltas from trips
      - sets total bikes (either explicit total_bikes or ratio*total_capacity)
      - runs greedy optimizer
    """
    cap = load_capacity_from_station_information(DEFAULT_TORONTO_STATIONS_FILE)
    delta, _valid_times = build_bucket_flows(
        trips_csv_path=trips_csv_path,
        day=day,
        capacity_by_station=cap,
        bucket_minutes=bucket_minutes,
    )

    # choose total bikes
    if total_bikes is None:
        ratio = 0.60 if total_bikes_ratio is None else float(total_bikes_ratio)
        ratio = max(0.0, min(1.0, ratio))
        total_capacity = sum(cap.values())
        total_bikes = int(round(total_capacity * ratio))

    return optimize_midnight_greedy(
        delta_by_station=delta,
        capacity_by_station=cap,
        total_bikes=int(total_bikes),
        bucket_minutes=bucket_minutes,
        empty_threshold=empty_threshold,
        full_threshold=full_threshold,
        w_empty=w_empty,
        w_full=w_full,
        max_moves=max_moves,
    )

def optimize_midnight_from_trips(
    trips_csv_path: str | Path,
    *,
    day: str | None = None,
    days: Iterable[str] | None = None,
    bucket_minutes: int = 15,
    total_bikes: int | None = None,
    total_bikes_ratio: float | None = 0.60,
    empty_threshold: float = 0.10,
    full_threshold: float = 0.90,
    w_empty: float = 1.0,
    w_full: float = 1.0,
    max_moves: int | None = None,
) -> MidnightOptimizeResult:
    """
    If `day` is provided → behaves exactly like before.
    If `days` is provided → optimizes against the average cost across days.
    """

    if (day is None) == (days is None):
        raise ValueError("Provide exactly one of `day` or `days`")

    cap = load_capacity_from_station_information(DEFAULT_TORONTO_STATIONS_FILE)

    # ---- collect per-day deltas ----
    day_list = [day] if day is not None else list(days)
    deltas = []

    for d in day_list:
        delta, _ = build_bucket_flows(
            trips_csv_path=trips_csv_path,
            day=d,
            capacity_by_station=cap,
            bucket_minutes=bucket_minutes,
        )
        deltas.append(delta)

    # ---- choose total bikes ----
    if total_bikes is None:
        ratio = 0.60 if total_bikes_ratio is None else float(total_bikes_ratio)
        total_bikes = int(round(sum(cap.values()) * max(0.0, min(1.0, ratio))))

    # ---- aggregate cost across days ----
    def averaged_delta():
        out = {}
        for sid in cap:
            series = [d[sid] for d in deltas if sid in d]
            if not series:
                continue
            out[sid] = [
                sum(vals) / len(vals) for vals in zip(*series)
            ]
        return out

    return optimize_midnight_greedy(
        delta_by_station=averaged_delta(),
        capacity_by_station=cap,
        total_bikes=total_bikes,
        bucket_minutes=bucket_minutes,
        empty_threshold=empty_threshold,
        full_threshold=full_threshold,
        w_empty=w_empty,
        w_full=w_full,
        max_moves=max_moves,
    )