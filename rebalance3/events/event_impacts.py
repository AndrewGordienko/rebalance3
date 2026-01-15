# rebalance3/events/event_impacts.py
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------------------
# Event -> station/time "delta_by_station" builder
#
# Output matches your trip bucketizer convention:
#   delta_by_station[sid][b] = arrivals - departures for bucket b
#
# Event effects:
#   - inbound (pre-start): more people arrive at venue -> MORE DROPOFFS -> delta += +k
#   - outbound (post-end): people leave venue -> MORE PICKUPS -> delta += -k
#
# This file is deterministic: no LLM needed.
# --------------------------------------------------------------------------------------


# -----------------------------
# Utilities
# -----------------------------
def _dt_from_iso_z(s: str) -> Optional[datetime]:
    """
    Parse ISO string, handling Z.
    Returns timezone-aware datetime in UTC if possible.
    """
    if not s:
        return None
    try:
        if s.endswith("Z"):
            return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            # assume UTC if tz missing (Ticketmaster dateTime is normally UTC)
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _date_range_utc(day_start_utc: datetime, day_end_utc: datetime, dt_utc: datetime) -> bool:
    return day_start_utc <= dt_utc < day_end_utc


def _clamp_int(x: float, lo: int, hi: int) -> int:
    return int(max(lo, min(hi, int(round(x)))))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # great-circle distance
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bucket_index(day_start_utc: datetime, t_utc: datetime, bucket_minutes: int, bucket_count: int) -> int:
    m = int((t_utc - day_start_utc).total_seconds() // 60)
    b = m // bucket_minutes
    if b < 0:
        return 0
    if b >= bucket_count:
        return bucket_count - 1
    return int(b)


def _triangular_pulse_weights(n: int) -> List[float]:
    """
    Simple triangular weights over n buckets: ramp up then down.
    Sums to 1.0.
    """
    if n <= 0:
        return []
    if n == 1:
        return [1.0]
    mid = (n - 1) / 2.0
    raw = []
    for i in range(n):
        # peak at mid
        raw.append(1.0 - abs(i - mid) / (mid + 1e-9))
    s = sum(raw)
    return [x / s for x in raw]


def _uniform_weights(n: int) -> List[float]:
    if n <= 0:
        return []
    return [1.0 / n for _ in range(n)]


# -----------------------------
# Attendance heuristics
# -----------------------------
def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def estimate_attendance(event: Dict[str, Any]) -> int:
    """
    Conservative heuristics. You can tune later.
    """
    name = _normalize(event.get("name", ""))
    venue = _normalize(event.get("venue_name", ""))
    seg = _normalize(event.get("segment", ""))
    cls = _normalize(event.get("classification", ""))

    # Big venues
    if "scotiabank" in venue:
        return 18000
    if "rogers centre" in venue or "rogers center" in venue:
        return 35000
    if "budweiser stage" in venue:
        return 16000
    if venue == "history":
        return 2500
    if "coca-cola coliseum" in venue:
        return 8000
    if "bmo field" in venue:
        return 28000

    # Sports (often medium/large)
    if "raptors" in name or "leafs" in name or seg == "sports":
        return 15000

    # Theatre / film
    if "tiff" in venue or "cinema" in venue or seg == "film":
        return 250

    # Music club-ish
    if seg == "music":
        return 1200

    # Default
    return 800


def estimate_bikeshare_rate(event: Dict[str, Any]) -> float:
    """
    Percent of attendees using bikeshare.
    Start simple. You can later condition on month/weather.
    """
    seg = _normalize(event.get("segment", ""))
    name = _normalize(event.get("name", ""))

    # sports crowd tends to use transit heavily; bikeshare moderate
    if seg == "sports" or ("raptors" in name) or ("leafs" in name):
        return 0.06

    # music events can be higher in warm months
    if seg == "music":
        return 0.08

    return 0.07


# -----------------------------
# Station weighting around venue
# -----------------------------
def station_weights_near_venue(
    *,
    stations: List[Dict[str, Any]],
    venue_lat: float,
    venue_lon: float,
    sigma_km: float = 0.8,
    top_n: int = 30,
    max_radius_km: float = 4.0,
) -> List[Tuple[str, float]]:
    """
    Returns list[(station_id, weight)] normalized to sum=1.
    Uses exp(-d/sigma), filtered by radius, takes top_n.
    """
    sigma_km = float(max(1e-6, sigma_km))
    max_radius_km = float(max(1e-6, max_radius_km))
    top_n = int(max(1, top_n))

    scored: List[Tuple[str, float]] = []
    for s in stations:
        try:
            sid = str(s["station_id"])
            lat = float(s["lat"])
            lon = float(s["lon"])
        except Exception:
            continue

        d = _haversine_km(lat, lon, float(venue_lat), float(venue_lon))
        if d > max_radius_km:
            continue

        w = math.exp(-d / sigma_km)
        if w > 0:
            scored.append((sid, w))

    if not scored:
        return []

    scored.sort(key=lambda x: x[1], reverse=True)
    scored = scored[:top_n]
    s = sum(w for _, w in scored)
    if s <= 0:
        return []
    return [(sid, w / s) for sid, w in scored]


# -----------------------------
# Event extraction (Ticketmaster-ish dicts)
# -----------------------------
@dataclass
class ParsedEvent:
    provider: str
    event_id: str
    name: str
    start_utc: datetime
    end_utc: Optional[datetime]
    venue_name: str
    venue_lat: float
    venue_lon: float
    segment: str
    classification: str
    url: str


def parse_ticketmaster_event(e: Dict[str, Any]) -> Optional[ParsedEvent]:
    """
    Accepts either:
      - your normalized fields from ticketmaster.py
      - or raw-ish Ticketmaster object with nested fields (best-effort)
    """
    provider = str(e.get("provider") or e.get("source") or "ticketmaster")

    # id/name
    event_id = str(e.get("id") or e.get("event_id") or "")
    name = str(e.get("name") or "")

    # start time: prefer normalized 'start_utc'
    start_utc = None
    if e.get("start_utc"):
        start_utc = _dt_from_iso_z(str(e.get("start_utc")))
    if start_utc is None and e.get("start"):
        start_utc = _dt_from_iso_z(str(e.get("start")))
    if start_utc is None:
        # try Ticketmaster raw
        try:
            start_utc = _dt_from_iso_z(str(e["dates"]["start"]["dateTime"]))
        except Exception:
            start_utc = None
    if start_utc is None:
        return None

    # end time: often missing; try normalized 'end_utc' or duration heuristics later
    end_utc = None
    if e.get("end_utc"):
        end_utc = _dt_from_iso_z(str(e.get("end_utc")))
    if end_utc is None and e.get("end"):
        end_utc = _dt_from_iso_z(str(e.get("end")))

    # venue
    venue_name = str(e.get("venue_name") or e.get("venue") or "")
    venue_lat = e.get("venue_lat")
    venue_lon = e.get("venue_lon")

    if venue_lat is None or venue_lon is None:
        # raw Ticketmaster fallback
        try:
            v = e["_embedded"]["venues"][0]
            venue_name = venue_name or str(v.get("name") or "")
            venue_lat = float(v["location"]["latitude"])
            venue_lon = float(v["location"]["longitude"])
        except Exception:
            return None

    # classification/segment
    segment = str(e.get("segment") or "")
    classification = str(e.get("classification") or "")
    if not segment or not classification:
        try:
            cls = e.get("classifications", [{}])[0]
            if not segment:
                segment = str(((cls.get("segment") or {}) or {}).get("name") or "")
            if not classification:
                parts = []
                for k in ("segment", "genre", "subGenre", "type", "subType"):
                    v = (cls.get(k) or {}).get("name")
                    if v:
                        parts.append(str(v))
                classification = " / ".join(parts)
        except Exception:
            pass

    url = str(e.get("url") or "")

    return ParsedEvent(
        provider=provider,
        event_id=event_id,
        name=name,
        start_utc=start_utc,
        end_utc=end_utc,
        venue_name=venue_name,
        venue_lat=float(venue_lat),
        venue_lon=float(venue_lon),
        segment=segment,
        classification=classification,
        url=url,
    )


# -----------------------------
# Core: build delta_by_station for a given day
# -----------------------------
def build_event_delta_by_station(
    *,
    day: str,  # YYYY-MM-DD
    stations: List[Dict[str, Any]],
    bucket_minutes: int,
    events: List[Dict[str, Any]],
    # pulse parameters
    inbound_minutes: int = 90,
    outbound_start_delay_minutes: int = 15,
    outbound_minutes: int = 120,
    inbound_share: float = 0.45,
    outbound_share: float = 0.55,
    # station weighting parameters
    sigma_km: float = 0.8,
    top_n_stations: int = 30,
    max_radius_km: float = 4.0,
    # demand scaling
    min_bike_trips_per_event: int = 10,
    max_bike_trips_per_event: int = 4000,
) -> Dict[str, List[int]]:
    """
    Returns delta_by_station_event[sid][b] for the given day (UTC-based day window).
    """
    bucket_minutes = int(bucket_minutes)
    if bucket_minutes <= 0 or 1440 % bucket_minutes != 0:
        raise ValueError("bucket_minutes must be > 0 and divide 1440")

    bucket_count = 1440 // bucket_minutes

    # Pre-init output
    out: Dict[str, List[int]] = {}
    for s in stations:
        try:
            sid = str(s["station_id"])
        except Exception:
            continue
        out[sid] = [0] * bucket_count

    # Day window in UTC
    day_start_utc = datetime.fromisoformat(f"{day}T00:00:00").replace(tzinfo=timezone.utc)
    day_end_utc = day_start_utc + timedelta(days=1)

    # pulse bucket lengths
    inbound_b = max(1, int(round(inbound_minutes / bucket_minutes)))
    outbound_b = max(1, int(round(outbound_minutes / bucket_minutes)))
    outbound_delay_b = max(0, int(round(outbound_start_delay_minutes / bucket_minutes)))

    inbound_share = float(inbound_share)
    outbound_share = float(outbound_share)
    tot_share = max(1e-9, inbound_share + outbound_share)
    inbound_share /= tot_share
    outbound_share /= tot_share

    # weights over time
    inbound_w = _triangular_pulse_weights(inbound_b)
    outbound_w = _triangular_pulse_weights(outbound_b)

    # Parse events and apply those that intersect the day window.
    for raw in events:
        pe = parse_ticketmaster_event(raw)
        if pe is None:
            continue

        # If start is not in this day, skip (simple first pass).
        # You can expand later to include events that begin previous evening.
        if not _date_range_utc(day_start_utc, day_end_utc, pe.start_utc):
            continue

        # Estimate bikes demand
        attendance = estimate_attendance(
            {
                "name": pe.name,
                "venue_name": pe.venue_name,
                "segment": pe.segment,
                "classification": pe.classification,
            }
        )
        rate = estimate_bikeshare_rate(
            {
                "name": pe.name,
                "segment": pe.segment,
                "venue_name": pe.venue_name,
            }
        )
        bike_trips = attendance * rate
        bike_trips = float(max(min_bike_trips_per_event, min(max_bike_trips_per_event, bike_trips)))

        inbound_total = bike_trips * inbound_share   # arrives -> dropoffs -> delta += +
        outbound_total = bike_trips * outbound_share # leaves -> pickups -> delta += -

        # Station weights around venue
        sw = station_weights_near_venue(
            stations=stations,
            venue_lat=pe.venue_lat,
            venue_lon=pe.venue_lon,
            sigma_km=sigma_km,
            top_n=top_n_stations,
            max_radius_km=max_radius_km,
        )
        if not sw:
            continue

        # Event start bucket
        b_start = _bucket_index(day_start_utc, pe.start_utc, bucket_minutes, bucket_count)

        # --- Inbound window: [start - inbound_minutes, start)
        b_in_start = max(0, b_start - inbound_b)
        # We align weights ending at b_start-1
        in_len = b_start - b_in_start
        if in_len > 0:
            # slice weights to match available buckets
            w_slice = inbound_w[-in_len:]
            # distribute inbound_total across buckets and stations
            for sid, w_station in sw:
                series = out.get(sid)
                if series is None:
                    continue
                for i in range(in_len):
                    b = b_in_start + i
                    add = inbound_total * w_station * w_slice[i]
                    # dropoffs -> delta += +add
                    series[b] += _clamp_int(add, 0, 10**9)

        # --- Outbound window: [start + delay, start + delay + outbound_minutes)
        b_out_start = min(bucket_count - 1, b_start + outbound_delay_b)
        b_out_end = min(bucket_count, b_out_start + outbound_b)
        out_len = b_out_end - b_out_start
        if out_len > 0:
            w_slice = outbound_w[:out_len]
            for sid, w_station in sw:
                series = out.get(sid)
                if series is None:
                    continue
                for i in range(out_len):
                    b = b_out_start + i
                    sub = outbound_total * w_station * w_slice[i]
                    # pickups -> delta += -sub
                    series[b] -= _clamp_int(sub, 0, 10**9)

    return out


# -----------------------------
# Convenience: load stations + events from files
# -----------------------------
def load_stations_from_station_information(stations_file: str | Path) -> List[Dict[str, Any]]:
    with open(stations_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("data", {}).get("stations", []))


def load_events_json(path: str | Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return list(json.load(f))


# -----------------------------
# Quick CLI test
# -----------------------------
if __name__ == "__main__":
    # Example:
    #   python -m rebalance3.events.event_impacts
    #
    # Expects:
    #   - station_information.json at repo root (same place as your other modules)
    #   - a Ticketmaster events JSON produced by your ticketmaster source script
    #
    # Adjust paths as needed.
    repo_root = Path(__file__).resolve().parents[2]
    stations_file = Path("/Users/andrewgordienko/Documents/rebalance3/rebalance3/viz/station_information.json")

    # pick any events json you generated
    events_json = repo_root / "data" / "events" / "events_2026-01-01_to_2026-01-08_ticketmaster.json"

    day = "2026-01-01"
    bucket_minutes = 15

    stations = load_stations_from_station_information(stations_file)
    events = load_events_json(events_json)

    delta_events = build_event_delta_by_station(
        day=day,
        stations=stations,
        bucket_minutes=bucket_minutes,
        events=events,
        sigma_km=0.8,
        top_n_stations=30,
        max_radius_km=4.0,
    )

    # Print a small sanity preview: top 10 stations by absolute event activity
    scored = []
    for sid, series in delta_events.items():
        mag = sum(abs(int(x)) for x in series)
        if mag > 0:
            scored.append((mag, sid))
    scored.sort(reverse=True)

    print(f"Day={day} bucket_minutes={bucket_minutes}")
    print(f"Stations impacted: {len(scored)}")
    for mag, sid in scored[:10]:
        print(f"- station {sid}: total_abs_delta={mag}")
