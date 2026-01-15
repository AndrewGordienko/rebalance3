# rebalance3/events/station_need_from_events.py
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional


# -----------------------------
# Config (keep it simple)
# -----------------------------
DEFAULT_BUCKET_MINUTES = 15

# Pre-event: people arrive -> more dropoffs -> need DOCKS
PRE_EVENT_WINDOW_MIN = 90

# Post-event: people leave -> more pickups -> need BIKES
POST_EVENT_WINDOW_MIN = 120

# Scaling: how many "bike trips" per event (rough proxy)
DEFAULT_EVENT_BIKE_TRIPS = 500

# Spread to nearest stations
TOP_N_STATIONS = 25
SIGMA_KM = 0.8
MAX_RADIUS_KM = 4.0


# -----------------------------
# Helpers
# -----------------------------
def _dt_from_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Ticketmaster gives UTC like "2026-01-01T00:30:00Z"
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bucket_index(day_start_utc: datetime, t_utc: datetime, bucket_minutes: int) -> int:
    m = int((t_utc - day_start_utc).total_seconds() // 60)
    return max(0, min((1440 // bucket_minutes) - 1, m // bucket_minutes))


def _normalize_weights(scored: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
    s = sum(w for _, w in scored)
    if s <= 0:
        return []
    return [(sid, w / s) for sid, w in scored]


def station_weights_near(
    *,
    stations: List[Dict[str, Any]],
    venue_lat: float,
    venue_lon: float,
    top_n: int = TOP_N_STATIONS,
    sigma_km: float = SIGMA_KM,
    max_radius_km: float = MAX_RADIUS_KM,
) -> List[Tuple[str, float]]:
    scored: List[Tuple[str, float]] = []
    for st in stations:
        try:
            sid = str(st["station_id"])
            lat = float(st["lat"])
            lon = float(st["lon"])
        except Exception:
            continue

        d = _haversine_km(lat, lon, venue_lat, venue_lon)
        if d > max_radius_km:
            continue

        w = math.exp(-d / max(1e-6, sigma_km))
        scored.append((sid, w))

    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[: max(1, int(top_n))]
    return _normalize_weights(scored)


def _triangle_weights(n: int) -> List[float]:
    """
    simple "peak in middle" weights
    """
    if n <= 0:
        return []
    if n == 1:
        return [1.0]
    mid = (n - 1) / 2.0
    raw = []
    for i in range(n):
        raw.append(1.0 - abs(i - mid) / (mid + 1e-9))
    s = sum(raw)
    return [x / s for x in raw]


# -----------------------------
# Core: build station need map
# -----------------------------
@dataclass
class StationNeed:
    # + means needs bikes (outbound spike)
    # - means needs docks (inbound spike)
    station_need_by_t: Dict[str, Dict[int, float]]


def build_station_need_from_ticketmaster_events(
    *,
    day: str,  # YYYY-MM-DD
    events: List[Dict[str, Any]],
    stations: List[Dict[str, Any]],
    bucket_minutes: int = DEFAULT_BUCKET_MINUTES,
    event_bike_trips: int = DEFAULT_EVENT_BIKE_TRIPS,
) -> StationNeed:
    """
    Returns:
      station_need_by_t[sid][t_min] = float need score

    Meaning:
      +N => more likely to run out of bikes (need bikes)
      -N => more likely to run out of docks (need docks)
    """
    bucket_minutes = int(bucket_minutes)
    bucket_count = 1440 // bucket_minutes

    day_start_utc = datetime.fromisoformat(f"{day}T00:00:00").replace(tzinfo=timezone.utc)
    day_end_utc = day_start_utc + timedelta(days=1)

    pre_b = max(1, int(round(PRE_EVENT_WINDOW_MIN / bucket_minutes)))
    post_b = max(1, int(round(POST_EVENT_WINDOW_MIN / bucket_minutes)))

    pre_w = _triangle_weights(pre_b)
    post_w = _triangle_weights(post_b)

    station_need_by_t: Dict[str, Dict[int, float]] = {}

    for e in events:
        # ---- pull start time ----
        start_s = e.get("start_utc") or e.get("start") or ""
        start_utc = _dt_from_iso(str(start_s))
        if start_utc is None:
            continue
        if not (day_start_utc <= start_utc < day_end_utc):
            continue

        # ---- pull venue ----
        try:
            vlat = float(e.get("venue_lat"))
            vlon = float(e.get("venue_lon"))
        except Exception:
            # if your event json isn't normalized, skip
            continue

        # ---- station weights ----
        sw = station_weights_near(
            stations=stations,
            venue_lat=vlat,
            venue_lon=vlon,
        )
        if not sw:
            continue

        # event "size"
        total_bike_trips = float(max(0, int(event_bike_trips)))

        # buckets
        b_start = _bucket_index(day_start_utc, start_utc, bucket_minutes)

        # -----------------------------
        # PRE-EVENT inbound:
        # people arrive -> dropoffs -> dock pressure
        # store as NEGATIVE need (need docks)
        # -----------------------------
        b0 = max(0, b_start - pre_b)
        n_pre = b_start - b0
        if n_pre > 0:
            w_slice = pre_w[-n_pre:]
            for sid, w_station in sw:
                station_need_by_t.setdefault(sid, {})
                for i in range(n_pre):
                    b = b0 + i
                    t_min = b * bucket_minutes
                    station_need_by_t[sid][t_min] = station_need_by_t[sid].get(t_min, 0.0) - (
                        total_bike_trips * w_station * w_slice[i]
                    )

        # -----------------------------
        # POST-EVENT outbound:
        # people leave -> pickups -> bike pressure
        # store as POSITIVE need (need bikes)
        # -----------------------------
        b1 = b_start
        b2 = min(bucket_count, b1 + post_b)
        n_post = b2 - b1
        if n_post > 0:
            w_slice = post_w[:n_post]
            for sid, w_station in sw:
                station_need_by_t.setdefault(sid, {})
                for i in range(n_post):
                    b = b1 + i
                    t_min = b * bucket_minutes
                    station_need_by_t[sid][t_min] = station_need_by_t[sid].get(t_min, 0.0) + (
                        total_bike_trips * w_station * w_slice[i]
                    )

    return StationNeed(station_need_by_t=station_need_by_t)


# -----------------------------
# IO: load stations + events
# -----------------------------
def load_stations_from_station_information(stations_file: str | Path) -> List[Dict[str, Any]]:
    with open(stations_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("data", {}).get("stations", []))


def load_events_json(events_file: str | Path) -> List[Dict[str, Any]]:
    with open(events_file, "r", encoding="utf-8") as f:
        return list(json.load(f))


def write_station_need_csv(
    out_csv: str | Path,
    need: StationNeed,
) -> None:
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for sid, tmap in need.station_need_by_t.items():
        for t_min, v in tmap.items():
            rows.append((sid, int(t_min), float(v)))

    rows.sort(key=lambda r: (r[1], r[0]))

    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("station_id,t_min,extra_need\n")
        for sid, t_min, v in rows:
            f.write(f"{sid},{t_min},{v:.6f}\n")


# -----------------------------
# CLI test
# -----------------------------
if __name__ == "__main__":
    # Example:
    #   python rebalance3/events/station_need_from_events.py
    repo_root = Path(__file__).resolve().parents[2]

    stations_file = Path("/Users/andrewgordienko/Documents/rebalance3/rebalance3/viz/station_information.json")

    # use the file you already successfully pulled
    events_file = repo_root / "data" / "events" / "events_2026-01-01_to_2026-01-08_ticketmaster.json"

    day = "2026-01-01"
    bucket_minutes = 15

    stations = load_stations_from_station_information(stations_file)
    events = load_events_json(events_file)

    need = build_station_need_from_ticketmaster_events(
        day=day,
        events=events,
        stations=stations,
        bucket_minutes=bucket_minutes,
        event_bike_trips=500,
    )

    out_csv = repo_root / "data" / "events" / f"station_need_{day}.csv"
    write_station_need_csv(out_csv, need)

    # quick preview
    nonzero = 0
    for _sid, tmap in need.station_need_by_t.items():
        nonzero += sum(1 for _t, v in tmap.items() if abs(v) > 1e-9)

    print(f"Wrote: {out_csv}")
    print(f"Nonzero station-time cells: {nonzero}")
