# rebalance3/trucks/day_planner.py
"""
Global (whole-day) truck-move planner with a cost function.

Upgraded:
- Adds CLUSTER + TIME-AWARE service objective using lookahead buffers:
    bike_buffer_needed  ~ future pickups (departures)
    dock_buffer_needed  ~ future dropoffs (arrivals)

This matches the real operational goal:
- keep bikes where upcoming departures need them
- keep docks where upcoming arrivals need them

Also keeps an optional light threshold-penalty (empty/full) as a background term.

Design:
- Bucketize trips.
- Maintain bikes-at-start-of-bucket series per station.
- Greedily pick the single move that yields the largest total cost drop.
- When evaluating a candidate move (src->snk at bucket b0), only recompute costs
  for the two affected stations from b0 onward (fast).

Service window:
- Restrict moves to [service_start_hour, service_end_hour).
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd

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


def load_station_clusters_csv(path: str | Path) -> Dict[str, int]:
    """
    Expects CSV:
      station_id,cluster_id
      7000,5
      ...

    Returns:
      station_cluster[sid_str] = cluster_id
    """
    df = pd.read_csv(Path(path))
    if "station_id" not in df.columns or "cluster_id" not in df.columns:
        raise ValueError(f"Clusters CSV missing required columns: {path}")

    out: Dict[str, int] = {}
    for _, r in df.iterrows():
        try:
            sid = str(int(r["station_id"]))
            cid = int(r["cluster_id"])
        except Exception:
            continue
        out[sid] = cid
    return out


@dataclass
class BucketedTrips:
    # net change per bucket: arrivals - departures
    delta_by_station: Dict[str, List[int]]
    pickups_by_station: Dict[str, List[int]]   # departures
    dropoffs_by_station: Dict[str, List[int]]  # arrivals
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
# Helpers
# -----------------------------
def _simulate_series(*, x0: int, cap: int, delta: List[int]) -> List[int]:
    """
    bikes at START of each bucket b. length = len(delta)
    x[b+1] = clamp(x[b] + delta[b])
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


def _future_sum(series: List[int], start_b: int, lookahead_b: int) -> int:
    end = min(len(series), start_b + lookahead_b)
    s = 0
    for i in range(start_b, end):
        s += int(series[i])
    return int(s)


def _priority(touches: int) -> float:
    # don’t let a tiny station dominate, but still prioritize high-use
    return float(math.log1p(max(0, int(touches))))


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    # fast enough for our candidate evaluations
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(max(0.0, min(1.0, x))))


# -----------------------------
# Cluster policy (edit these freely)
# -----------------------------
def get_cluster_hour_multipliers(cluster_id: int, hour: int) -> Tuple[float, float]:
    """
    Returns (bike_need_mult, dock_need_mult).

    Interpretation:
      - bike_need_mult scales penalty for NOT having enough bikes buffer
      - dock_need_mult scales penalty for NOT having enough docks buffer

    These are intentionally mild; turn them up later once stable.
    """
    bike_mult = 1.0
    dock_mult = 1.0

    # cluster 7 (from your notes): financial / inbound AM -> docks matter
    if cluster_id == 7 and 7 <= hour <= 10:
        dock_mult *= 2.5

    # cluster 5: residential outbound AM -> bikes matter
    if cluster_id == 5 and 6 <= hour <= 9:
        bike_mult *= 2.0

    # cluster 4: campus/nightlife late -> bikes matter
    if cluster_id == 4 and (hour >= 22 or hour <= 2):
        bike_mult *= 2.0

    return bike_mult, dock_mult


# -----------------------------
# Cost function (buffer objective + optional threshold background)
# -----------------------------
def _cost_from_bucket(
    *,
    sid: str,
    start_b: int,
    x_start: int,
    cap: int,
    delta: List[int],
    pickups: List[int],
    dropoffs: List[int],
    bucket_minutes: int,
    lookahead_b: int,
    # buffer params
    pickup_buffer_mult: float,
    dropoff_buffer_mult: float,
    w_bike_need: float,
    w_dock_need: float,
    # optional background threshold penalty
    use_threshold_penalty: bool,
    empty_thr: float,
    full_thr: float,
    w_empty: float,
    w_full: float,
    # clusters
    station_cluster: Dict[str, int],
) -> float:
    """
    Cost from bucket start_b to end-of-day, assuming bikes at START of start_b is x_start.

    Primary objective (buffer-based):
      bike_shortage = max(0, pickup_buffer_mult * future_pickups - bikes)
      dock_shortage = max(0, dropoff_buffer_mult * future_dropoffs - empty_docks)

    Optional background:
      threshold empty/full depth (like your old objective), kept light.

    Cluster/time multipliers apply to buffer terms only.
    """
    if cap <= 0:
        return 0.0

    cid = int(station_cluster.get(sid, -1))

    empty_level = float(empty_thr) * cap
    full_level = float(full_thr) * cap

    x = int(max(0, min(cap, x_start)))
    cost = 0.0

    B = len(delta)
    for b in range(start_b, B):
        hour = ((b * bucket_minutes) // 60) % 24

        # lookahead demand
        fut_pu = _future_sum(pickups, b, lookahead_b)
        fut_do = _future_sum(dropoffs, b, lookahead_b)

        bikes_needed = float(pickup_buffer_mult) * float(fut_pu)
        docks_needed = float(dropoff_buffer_mult) * float(fut_do)

        empty_docks = cap - x

        bike_short = max(0.0, bikes_needed - float(x))
        dock_short = max(0.0, docks_needed - float(empty_docks))

        bike_mult, dock_mult = (1.0, 1.0)
        if cid >= 0:
            bike_mult, dock_mult = get_cluster_hour_multipliers(cid, hour)

        # buffer penalties
        if bike_short > 0:
            cost += float(w_bike_need) * float(bike_mult) * bike_short
        if dock_short > 0:
            cost += float(w_dock_need) * float(dock_mult) * dock_short

        # optional threshold penalties (light background)
        if use_threshold_penalty:
            if x < empty_level:
                cost += float(w_empty) * (empty_level - x)
            if x > full_level:
                cost += float(w_full) * (x - full_level)

        # evolve to next bucket
        x = x + int(delta[b])
        if x < 0:
            x = 0
        elif x > cap:
            x = cap

    return float(cost)


def _sink_risk(
    *,
    sid: str,
    bikes_now: int,
    cap: int,
    b: int,
    pickups: List[int],
    lookahead_b: int,
    pickup_buffer_mult: float,
    touches: int,
) -> float:
    if cap <= 0:
        return 0.0
    fut_pickups = _future_sum(pickups, b, lookahead_b)
    need = float(pickup_buffer_mult) * float(fut_pickups)
    short = max(0.0, need - float(bikes_now))
    if short <= 0:
        return 0.0
    return short * _priority(touches)


def _source_risk(
    *,
    sid: str,
    bikes_now: int,
    cap: int,
    b: int,
    dropoffs: List[int],
    lookahead_b: int,
    dropoff_buffer_mult: float,
    touches: int,
) -> float:
    if cap <= 0:
        return 0.0
    fut_dropoffs = _future_sum(dropoffs, b, lookahead_b)
    need_docks = float(dropoff_buffer_mult) * float(fut_dropoffs)
    empty_now = float(cap - bikes_now)
    short = max(0.0, need_docks - empty_now)
    if short <= 0:
        return 0.0
    return short * _priority(touches)


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

    # --- buffer objective knobs ---
    pickup_buffer_mult: float = 1.0,   # bikes needed ~ future pickups * mult
    dropoff_buffer_mult: float = 1.0,  # docks needed ~ future dropoffs * mult
    w_bike_need: float = 1.0,
    w_dock_need: float = 1.4,  # docks usually more fragile in dense areas

    # --- optional background threshold penalty ---
    use_threshold_penalty: bool = True,
    empty_thr: float = 0.10,
    full_thr: float = 0.90,
    w_empty: float = 0.3,  # keep light; buffer objective is primary
    w_full: float = 0.6,   # keep light; buffer objective is primary

    # candidate selection
    candidate_time_top_k: int = 10,
    top_k_sources: int = 12,
    top_k_sinks: int = 12,

    # travel realism
    use_distance_penalty: bool = True,
    distance_penalty_per_km: float = 0.06,  # cost units per km (tune)
    max_pair_km: float | None = 10.0,       # reject src->snk if farther than this

    # clusters
    clusters_csv: str | Path | None = None,

    # io
    stations_file: str | Path = DEFAULT_TORONTO_STATIONS_FILE,
    encoding: str = "utf-8-sig",

    # service window
    service_start_hour: int = 8,
    service_end_hour: int = 20,  # exclusive
) -> List[TruckMove]:
    """
    Returns a list of TruckMove with chosen t_min over the day.

    Restricts chosen move times to [service_start_hour, service_end_hour).
    """
    moves_budget = int(moves_budget)
    if moves_budget <= 0:
        return []

    cap, latlon = load_station_info(stations_file)
    sids = list(cap.keys())
    if not sids:
        return []

    station_cluster: Dict[str, int] = {}
    if clusters_csv is not None:
        station_cluster = load_station_clusters_csv(clusters_csv)

    trips = bucketize_trips(
        trips_csv_path=trips_csv_path,
        day=day,
        capacity_by_station=cap,
        bucket_minutes=bucket_minutes,
        encoding=encoding,
    )

    B = trips.bucket_count
    if B <= 0:
        return []

    lookahead_b = max(1, int(lookahead_minutes // bucket_minutes))

    # ---- service window bucket range ----
    service_start_hour = int(service_start_hour)
    service_end_hour = int(service_end_hour)
    if not (0 <= service_start_hour <= 24 and 0 <= service_end_hour <= 24):
        raise ValueError("service_start_hour/service_end_hour must be within [0, 24]")
    if service_end_hour <= service_start_hour:
        raise ValueError("service_end_hour must be > service_start_hour")

    service_start_min = service_start_hour * 60
    service_end_min = service_end_hour * 60
    b_start = max(0, service_start_min // bucket_minutes)
    b_end = min(B, service_end_min // bucket_minutes)  # exclusive
    if b_start >= b_end:
        return []

    # clamp initial bikes
    x0: Dict[str, int] = {}
    for sid in sids:
        c = cap[sid]
        x0[sid] = int(max(0, min(c, int(initial_bikes.get(sid, 0)))))

    # baseline series for all stations (bikes at start of each bucket)
    series: Dict[str, List[int]] = {}
    for sid in sids:
        series[sid] = _simulate_series(
            x0=x0[sid],
            cap=cap[sid],
            delta=trips.delta_by_station[sid],
        )

    # baseline per-station cost from bucket 0
    cost_station: Dict[str, float] = {}
    for sid in sids:
        cost_station[sid] = _cost_from_bucket(
            sid=sid,
            start_b=0,
            x_start=series[sid][0],
            cap=cap[sid],
            delta=trips.delta_by_station[sid],
            pickups=trips.pickups_by_station[sid],
            dropoffs=trips.dropoffs_by_station[sid],
            bucket_minutes=bucket_minutes,
            lookahead_b=lookahead_b,
            pickup_buffer_mult=pickup_buffer_mult,
            dropoff_buffer_mult=dropoff_buffer_mult,
            w_bike_need=w_bike_need,
            w_dock_need=w_dock_need,
            use_threshold_penalty=use_threshold_penalty,
            empty_thr=empty_thr,
            full_thr=full_thr,
            w_empty=w_empty,
            w_full=w_full,
            station_cluster=station_cluster,
        )

    def total_cost() -> float:
        return float(sum(cost_station.values()))

    # -----------------------------
    # Candidate times: pick buckets where buffer-shortage is worst
    # -----------------------------
    badness: List[Tuple[float, int]] = []
    for b in range(b_start, b_end):
        s = 0.0
        for sid in sids:
            x = series[sid][b]
            c = cap[sid]
            if c <= 0:
                continue
            fut_pu = _future_sum(trips.pickups_by_station[sid], b, lookahead_b)
            fut_do = _future_sum(trips.dropoffs_by_station[sid], b, lookahead_b)
            need_bikes = pickup_buffer_mult * float(fut_pu)
            need_docks = dropoff_buffer_mult * float(fut_do)
            short_b = max(0.0, need_bikes - float(x))
            short_d = max(0.0, need_docks - float(c - x))
            s += short_b + short_d
        badness.append((s, b))

    badness.sort(reverse=True)
    candidate_buckets = sorted(set(b for _, b in badness[: max(8, int(candidate_time_top_k))]))

    # also add a coarse grid in the service window (~hourly)
    step = max(1, int((60 // bucket_minutes)))
    for b in range(b_start, b_end, step):
        candidate_buckets.append(b)
    candidate_buckets = sorted(set(b for b in candidate_buckets if b_start <= b < b_end))

    planned: List[TruckMove] = []

    # -----------------------------
    # Greedy move selection
    # -----------------------------
    for _ in range(moves_budget):
        best_improvement = 0.0
        best_choice = None  # (b0, src, snk, moved)

        for b0 in candidate_buckets:
            # sinks: stations with upcoming bike shortage
            sinks = sorted(
                sids,
                key=lambda sid: _sink_risk(
                    sid=sid,
                    bikes_now=series[sid][b0],
                    cap=cap[sid],
                    b=b0,
                    pickups=trips.pickups_by_station[sid],
                    lookahead_b=lookahead_b,
                    pickup_buffer_mult=pickup_buffer_mult,
                    touches=trips.touch_totals.get(sid, 0),
                ),
                reverse=True,
            )[:top_k_sinks]

            # sources: stations with upcoming dock shortage
            sources = sorted(
                sids,
                key=lambda sid: _source_risk(
                    sid=sid,
                    bikes_now=series[sid][b0],
                    cap=cap[sid],
                    b=b0,
                    dropoffs=trips.dropoffs_by_station[sid],
                    lookahead_b=lookahead_b,
                    dropoff_buffer_mult=dropoff_buffer_mult,
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

                    # optional distance constraints
                    if use_distance_penalty:
                        a = latlon.get(src)
                        b = latlon.get(snk)
                        if a is None or b is None:
                            continue
                        dkm = _haversine_km(a, b)
                        if max_pair_km is not None and dkm > float(max_pair_km):
                            continue
                    else:
                        dkm = 0.0

                    moved = min(
                        int(truck_cap),
                        int(bikes_src - donor_min_bikes_left),
                        int(empty_snk - receiver_min_empty_docks_left),
                    )
                    if moved <= 0:
                        continue

                    # cost from b0 onward (only src + snk affected)
                    base_src = _cost_from_bucket(
                        sid=src,
                        start_b=b0,
                        x_start=series[src][b0],
                        cap=cap[src],
                        delta=trips.delta_by_station[src],
                        pickups=trips.pickups_by_station[src],
                        dropoffs=trips.dropoffs_by_station[src],
                        bucket_minutes=bucket_minutes,
                        lookahead_b=lookahead_b,
                        pickup_buffer_mult=pickup_buffer_mult,
                        dropoff_buffer_mult=dropoff_buffer_mult,
                        w_bike_need=w_bike_need,
                        w_dock_need=w_dock_need,
                        use_threshold_penalty=use_threshold_penalty,
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                        station_cluster=station_cluster,
                    )
                    base_snk = _cost_from_bucket(
                        sid=snk,
                        start_b=b0,
                        x_start=series[snk][b0],
                        cap=cap[snk],
                        delta=trips.delta_by_station[snk],
                        pickups=trips.pickups_by_station[snk],
                        dropoffs=trips.dropoffs_by_station[snk],
                        bucket_minutes=bucket_minutes,
                        lookahead_b=lookahead_b,
                        pickup_buffer_mult=pickup_buffer_mult,
                        dropoff_buffer_mult=dropoff_buffer_mult,
                        w_bike_need=w_bike_need,
                        w_dock_need=w_dock_need,
                        use_threshold_penalty=use_threshold_penalty,
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                        station_cluster=station_cluster,
                    )

                    new_src = _cost_from_bucket(
                        sid=src,
                        start_b=b0,
                        x_start=series[src][b0] - moved,
                        cap=cap[src],
                        delta=trips.delta_by_station[src],
                        pickups=trips.pickups_by_station[src],
                        dropoffs=trips.dropoffs_by_station[src],
                        bucket_minutes=bucket_minutes,
                        lookahead_b=lookahead_b,
                        pickup_buffer_mult=pickup_buffer_mult,
                        dropoff_buffer_mult=dropoff_buffer_mult,
                        w_bike_need=w_bike_need,
                        w_dock_need=w_dock_need,
                        use_threshold_penalty=use_threshold_penalty,
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                        station_cluster=station_cluster,
                    )
                    new_snk = _cost_from_bucket(
                        sid=snk,
                        start_b=b0,
                        x_start=series[snk][b0] + moved,
                        cap=cap[snk],
                        delta=trips.delta_by_station[snk],
                        pickups=trips.pickups_by_station[snk],
                        dropoffs=trips.dropoffs_by_station[snk],
                        bucket_minutes=bucket_minutes,
                        lookahead_b=lookahead_b,
                        pickup_buffer_mult=pickup_buffer_mult,
                        dropoff_buffer_mult=dropoff_buffer_mult,
                        w_bike_need=w_bike_need,
                        w_dock_need=w_dock_need,
                        use_threshold_penalty=use_threshold_penalty,
                        empty_thr=empty_thr,
                        full_thr=full_thr,
                        w_empty=w_empty,
                        w_full=w_full,
                        station_cluster=station_cluster,
                    )

                    improvement = (base_src + base_snk) - (new_src + new_snk)

                    # distance penalty reduces attractiveness of long moves
                    if use_distance_penalty and dkm > 0:
                        improvement -= float(distance_penalty_per_km) * float(dkm)

                    if improvement > best_improvement + 1e-9:
                        best_improvement = improvement
                        best_choice = (b0, src, snk, moved)

        if best_choice is None or best_improvement <= 1e-9:
            break

        b0, src, snk, moved = best_choice

        # apply move by resimming only the tails of src and snk
        def resim_from_b0(sid: str, new_x_b0: int):
            prefix = series[sid][:b0]
            tail = _simulate_series(
                x0=new_x_b0,
                cap=cap[sid],
                delta=trips.delta_by_station[sid][b0:],
            )
            series[sid] = prefix + tail

            cost_station[sid] = _cost_from_bucket(
                sid=sid,
                start_b=0,
                x_start=series[sid][0],
                cap=cap[sid],
                delta=trips.delta_by_station[sid],
                pickups=trips.pickups_by_station[sid],
                dropoffs=trips.dropoffs_by_station[sid],
                bucket_minutes=bucket_minutes,
                lookahead_b=lookahead_b,
                pickup_buffer_mult=pickup_buffer_mult,
                dropoff_buffer_mult=dropoff_buffer_mult,
                w_bike_need=w_bike_need,
                w_dock_need=w_dock_need,
                use_threshold_penalty=use_threshold_penalty,
                empty_thr=empty_thr,
                full_thr=full_thr,
                w_empty=w_empty,
                w_full=w_full,
                station_cluster=station_cluster,
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

    planned.sort(key=lambda m: (m.t_min if m.t_min is not None else 0))
    return planned
