# rebalance3/trucks/simulator.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import math

from rebalance3.trucks.types import TruckMove


# ----------------------------
# Defaults / knobs
# ----------------------------
DEFAULT_NUM_TRUCKS = 8

TRUCK_CAPACITY = 20
MAX_STOPS_PER_TRUCK = 999999  # not used when we have a global budget

AVG_TRUCK_SPEED_KMPH = 25.0  # downtown-ish

LOOKAHEAD_MINUTES = 180  # 3h

DONOR_MIN_BIKES_LEFT = 3
RECEIVER_MIN_EMPTY_DOCKS_LEFT = 2

EMPTY_SOON_BIKES_THRESHOLD = 2
FULL_SOON_EMPTY_DOCKS_THRESHOLD = 2

# rush hour weighting
HOUR_WEIGHT = {
    7: 2.0, 8: 3.0, 9: 3.0,
    16: 2.5, 17: 3.0, 18: 2.5,
}
DEFAULT_HOUR_WEIGHT = 0.6

DISTANCE_PENALTY_PER_KM = 0.05
TOP_K_SINKS = 25
TOP_K_SOURCES = 25


@dataclass
class TruckState:
    id: int
    loc_station: str
    available_at_min: int


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p = math.pi / 180.0
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def _hour_weight(t_min: int) -> float:
    h = int(t_min // 60)
    return float(HOUR_WEIGHT.get(h, DEFAULT_HOUR_WEIGHT))


def _travel_minutes(dist_km: float) -> int:
    if AVG_TRUCK_SPEED_KMPH <= 1e-9:
        return 999999
    return int(round((dist_km / AVG_TRUCK_SPEED_KMPH) * 60.0))


def _future_sum(series: List[int], start_bucket: int, lookahead_buckets: int) -> int:
    if not series:
        return 0
    s = 0
    end = min(len(series), start_bucket + lookahead_buckets)
    for i in range(start_bucket, end):
        s += int(series[i])
    return int(s)


def _station_priority(touch_total: int) -> float:
    # same flavor as your original: log1p(touches)
    return float(math.log1p(max(0, int(touch_total))))


def _sink_score(
    *,
    sid: str,
    bikes_now: int,
    cap: int,
    bucket_now: int,
    lookahead_buckets: int,
    pickups_by_bucket: List[int],
    priority: float,
    t_min: int,
) -> float:
    """
    Sink = station at risk of running OUT of bikes.
    Combines:
      - "empty now" pressure
      - + "future pickups shortage" pressure
    """
    if cap <= 0:
        return 0.0

    # empty-now component (rescues stations that are already dying)
    empty_now = max(0, int(0.25 * cap) - bikes_now)  # tune 0.25
    empty_now_score = float(empty_now) * 1.2

    # future shortage component
    fut_pickups = _future_sum(pickups_by_bucket, bucket_now + 1, lookahead_buckets)
    shortage = max(0, fut_pickups - bikes_now)
    shortage_score = float(shortage)

    base = empty_now_score + shortage_score
    if base <= 0:
        return 0.0

    boost = 1.5 if bikes_now <= EMPTY_SOON_BIKES_THRESHOLD else 1.0
    return base * boost * _hour_weight(t_min) * priority


def _source_score(
    *,
    sid: str,
    bikes_now: int,
    cap: int,
    bucket_now: int,
    lookahead_buckets: int,
    dropoffs_by_bucket: List[int],
    priority: float,
    t_min: int,
) -> float:
    """
    Source = station at risk of running OUT of empty docks (overflow).
    Combines:
      - "full now" pressure
      - + "future dropoffs overflow" pressure

    IMPORTANT: no "+1" fake scoring.
    """
    if cap <= 0:
        return 0.0

    empty = cap - bikes_now

    # full-now component
    full_now = max(0, bikes_now - int(0.85 * cap))  # tune 0.85
    full_now_score = float(full_now) * 1.2

    # future overflow component
    fut_dropoffs = _future_sum(dropoffs_by_bucket, bucket_now + 1, lookahead_buckets)
    overflow = max(0, fut_dropoffs - empty)
    overflow_score = float(overflow)

    base = full_now_score + overflow_score
    if base <= 0:
        return 0.0

    boost = 1.5 if empty <= FULL_SOON_EMPTY_DOCKS_THRESHOLD else 1.0
    return base * boost * _hour_weight(t_min) * priority


def initialize_trucks(
    *,
    station_ids: List[str],
    num_trucks: int,
    start_time_min: int = 0,
) -> List[TruckState]:
    if not station_ids:
        return []
    n = max(0, int(num_trucks))
    if n <= 0:
        return []
    trucks: List[TruckState] = []
    for i in range(n):
        trucks.append(
            TruckState(
                id=i,
                loc_station=str(station_ids[i % len(station_ids)]),
                available_at_min=int(start_time_min),
            )
        )
    return trucks


def dispatch_truck_fleet(
    *,
    t_min: int,
    bucket_minutes: int,
    station_bikes: Dict[str, int],
    station_capacity: Dict[str, int],
    station_latlon: Dict[str, Tuple[float, float]],
    bucket_pickups: Dict[str, List[int]],
    bucket_dropoffs: Dict[str, List[int]],
    touch_totals: Dict[str, int],
    trucks: List[TruckState],
    moves_budget_remaining: int,
    lookahead_minutes: int = LOOKAHEAD_MINUTES,
    truck_cap: int = TRUCK_CAPACITY,
) -> List[TruckMove]:
    """
    Global-budget dispatch:
      - You can do at most `moves_budget_remaining` total moves this day.
      - Each move is assigned to the best currently-available truck.
      - Applies move immediately to station_bikes.

    Returns TruckMove list with t_min, truck_id, distance_km.
    """
    if moves_budget_remaining <= 0:
        return []
    if not trucks:
        return []

    bucket_now = int(t_min // bucket_minutes)
    lookahead_buckets = max(1, int(lookahead_minutes // bucket_minutes))

    priority: Dict[str, float] = {
        sid: _station_priority(touch_totals.get(sid, 0))
        for sid in station_capacity.keys()
    }

    station_ids = list(station_capacity.keys())

    # Only trucks that can act now
    available_trucks = [tr for tr in trucks if tr.available_at_min <= t_min]
    if not available_trucks:
        return []

    # rank sinks/sources once per dispatch moment
    sinks = sorted(
        station_ids,
        key=lambda s: _sink_score(
            sid=s,
            bikes_now=station_bikes.get(s, 0),
            cap=station_capacity.get(s, 0),
            bucket_now=bucket_now,
            lookahead_buckets=lookahead_buckets,
            pickups_by_bucket=bucket_pickups.get(s, []),
            priority=priority.get(s, 1.0),
            t_min=t_min,
        ),
        reverse=True,
    )[:TOP_K_SINKS]

    sources = sorted(
        station_ids,
        key=lambda s: _source_score(
            sid=s,
            bikes_now=station_bikes.get(s, 0),
            cap=station_capacity.get(s, 0),
            bucket_now=bucket_now,
            lookahead_buckets=lookahead_buckets,
            dropoffs_by_bucket=bucket_dropoffs.get(s, []),
            priority=priority.get(s, 1.0),
            t_min=t_min,
        ),
        reverse=True,
    )[:TOP_K_SOURCES]

    if not sinks or not sources:
        return []

    # Choose best move across all available trucks
    best: Optional[Tuple[float, TruckState, str, str, int, float]] = None

    for truck in available_trucks:
        truck_loc = truck.loc_station
        truck_ll = station_latlon.get(truck_loc)
        if truck_ll is None:
            continue

        for src in sources:
            cap_src = station_capacity.get(src, 0)
            if cap_src <= 0:
                continue
            bikes_src = station_bikes.get(src, 0)
            if bikes_src <= DONOR_MIN_BIKES_LEFT:
                continue

            ll_src = station_latlon.get(src)
            if ll_src is None:
                continue

            dist_truck_to_src = _haversine_km(truck_ll[0], truck_ll[1], ll_src[0], ll_src[1])

            for snk in sinks:
                if src == snk:
                    continue

                cap_snk = station_capacity.get(snk, 0)
                if cap_snk <= 0:
                    continue

                bikes_snk = station_bikes.get(snk, 0)
                empty_snk = cap_snk - bikes_snk
                if empty_snk <= RECEIVER_MIN_EMPTY_DOCKS_LEFT:
                    continue

                ll_snk = station_latlon.get(snk)
                if ll_snk is None:
                    continue

                max_move = min(
                    int(truck_cap),
                    int(bikes_src - DONOR_MIN_BIKES_LEFT),
                    int(empty_snk - RECEIVER_MIN_EMPTY_DOCKS_LEFT),
                )
                if max_move <= 0:
                    continue

                dist_src_to_snk = _haversine_km(ll_src[0], ll_src[1], ll_snk[0], ll_snk[1])

                src_score = _source_score(
                    sid=src,
                    bikes_now=bikes_src,
                    cap=cap_src,
                    bucket_now=bucket_now,
                    lookahead_buckets=lookahead_buckets,
                    dropoffs_by_bucket=bucket_dropoffs.get(src, []),
                    priority=priority.get(src, 1.0),
                    t_min=t_min,
                )

                snk_score = _sink_score(
                    sid=snk,
                    bikes_now=bikes_snk,
                    cap=cap_snk,
                    bucket_now=bucket_now,
                    lookahead_buckets=lookahead_buckets,
                    pickups_by_bucket=bucket_pickups.get(snk, []),
                    priority=priority.get(snk, 1.0),
                    t_min=t_min,
                )

                score = (
                    src_score
                    + snk_score
                    - DISTANCE_PENALTY_PER_KM * (dist_truck_to_src + dist_src_to_snk)
                )

                if best is None or score > best[0]:
                    best = (score, truck, src, snk, max_move, dist_truck_to_src + dist_src_to_snk)

    if best is None:
        return []

    _, chosen_truck, src, snk, moved, total_dist_km = best

    # apply move immediately
    station_bikes[src] -= int(moved)
    station_bikes[snk] += int(moved)

    # update truck state (travel time based on chosen route)
    chosen_truck.loc_station = str(snk)
    chosen_truck.available_at_min = int(t_min + _travel_minutes(total_dist_km))

    return [
        TruckMove(
            from_station=str(src),
            to_station=str(snk),
            bikes=int(moved),
            t_min=int(t_min),
            truck_id=int(chosen_truck.id),
            distance_km=float(total_dist_km),
        )
    ]
