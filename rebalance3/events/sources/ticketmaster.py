# rebalance3/events/sources/ticketmaster.py
from __future__ import annotations

import csv
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# HARD-CODED KEY (as requested)
# ============================================================
# NOTE:
# This is very likely NOT a real Ticketmaster Discovery API key.
# It looks like an Apigee "Consumer Key" for some other gateway.
# Ticketmaster Discovery expects a key issued by Ticketmaster.
TICKETMASTER_API_KEY = "wpHHiIDlNP1tfqbTGAIbdLQ4qniGMe6f"


# ============================================================
# CONFIG
# ============================================================
BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"

# Toronto coordinates (fallback geo search)
TORONTO_LAT = 43.6532
TORONTO_LON = -79.3832

TIME_FMT_ISO = "%Y-%m-%d"
TIME_FMT_TICKETMASTER = "%Y-%m-%dT%H:%M:%SZ"


# ============================================================
# OUTPUT EVENT TYPE
# ============================================================
@dataclass
class PulledEvent:
    source: str
    provider: str
    id: str
    name: str
    start_utc: str | None
    url: str | None
    venue: str | None
    city: str | None
    lat: float | None
    lon: float | None
    classification: str | None  # e.g. "Sports / Hockey"


# ============================================================
# UTIL
# ============================================================
def _iso_utc(dt: datetime) -> str:
    # Ticketmaster expects UTC with trailing Z
    return dt.strftime(TIME_FMT_TICKETMASTER)


def _safe_get(d: Any, *keys: str) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _http_get_json(url: str, timeout: int = 30) -> Dict[str, Any]:
    """
    HTTP GET -> JSON with proper error-body printing (critical for debugging 401).
    """
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "rebalance3-events/1.0",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"__raw__": raw}

    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", errors="replace")
        except Exception:
            raw = ""

        print(f"\n[Ticketmaster] HTTP ERROR: {e.code} {e.reason}")
        if raw:
            print("[Ticketmaster] ERROR BODY (first 2000 chars):")
            print(raw[:2000])

        try:
            return json.loads(raw) if raw else {"__raw__": ""}
        except Exception:
            return {"__raw__": raw, "__http_status__": e.code}

    except Exception as e:
        print(f"\n[Ticketmaster] ERROR: {repr(e)}")
        return {"__raw__": str(e)}


def _build_url(params: Dict[str, Any]) -> str:
    q = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    return f"{BASE_URL}?{q}"


def _parse_classification(ev: Dict[str, Any]) -> str | None:
    """
    Try to pull a readable classification like:
      "Sports / Hockey"
      "Music / Rock"
    """
    cls = _safe_get(ev, "classifications")
    if not isinstance(cls, list) or not cls:
        return None

    c0 = cls[0]
    seg = _safe_get(c0, "segment", "name")
    gen = _safe_get(c0, "genre", "name")
    sub = _safe_get(c0, "subGenre", "name")

    parts = []
    if isinstance(seg, str) and seg.strip():
        parts.append(seg.strip())
    if isinstance(gen, str) and gen.strip() and gen.strip().lower() != "undefined":
        parts.append(gen.strip())
    if isinstance(sub, str) and sub.strip() and sub.strip().lower() != "undefined":
        parts.append(sub.strip())

    if not parts:
        return None
    return " / ".join(parts)


def _parse_venue(ev: Dict[str, Any]) -> Tuple[str | None, str | None, float | None, float | None]:
    emb = _safe_get(ev, "_embedded", "venues")
    if not isinstance(emb, list) or not emb:
        return None, None, None, None

    v = emb[0]
    venue_name = v.get("name") if isinstance(v.get("name"), str) else None

    city = _safe_get(v, "city", "name")
    if not isinstance(city, str):
        city = None

    lat = _safe_get(v, "location", "latitude")
    lon = _safe_get(v, "location", "longitude")

    try:
        lat_f = float(lat) if lat is not None else None
    except Exception:
        lat_f = None

    try:
        lon_f = float(lon) if lon is not None else None
    except Exception:
        lon_f = None

    return venue_name, city, lat_f, lon_f


def _parse_start_utc(ev: Dict[str, Any]) -> str | None:
    start = _safe_get(ev, "dates", "start", "dateTime")
    if isinstance(start, str) and start.strip():
        return start.strip()
    return None


def _extract_events(data: Dict[str, Any]) -> List[PulledEvent]:
    out: List[PulledEvent] = []

    evs = _safe_get(data, "_embedded", "events")
    if not isinstance(evs, list):
        return out

    for ev in evs:
        if not isinstance(ev, dict):
            continue

        eid = ev.get("id")
        if not isinstance(eid, str) or not eid:
            continue

        name = ev.get("name")
        if not isinstance(name, str) or not name:
            name = "Unknown"

        url = ev.get("url") if isinstance(ev.get("url"), str) else None

        start_utc = _parse_start_utc(ev)
        venue, city, lat, lon = _parse_venue(ev)
        classification = _parse_classification(ev)

        out.append(
            PulledEvent(
                source="ticketmaster",
                provider="ticketmaster_discovery",
                id=eid,
                name=name,
                start_utc=start_utc,
                url=url,
                venue=venue,
                city=city,
                lat=lat,
                lon=lon,
                classification=classification,
            )
        )

    return out


def _fetch_paged(params: Dict[str, Any], *, max_pages: int = 10) -> List[PulledEvent]:
    """
    Ticketmaster paging:
      page[number], page[size]
    """
    size = int(params.get("size") or 200)
    size = max(1, min(200, size))
    params["size"] = size

    all_events: List[PulledEvent] = []

    page = 0
    while True:
        params["page"] = page
        url = _build_url(params)

        data = _http_get_json(url)
        events = _extract_events(data)

        all_events.extend(events)

        # if unauthorized / invalid response, bail early
        if "__http_status__" in data and int(data["__http_status__"]) >= 400:
            break

        # determine if more pages exist
        p = data.get("page", {})
        if not isinstance(p, dict):
            break

        total_pages = p.get("totalPages")
        number = p.get("number")

        try:
            total_pages = int(total_pages)
            number = int(number)
        except Exception:
            break

        if number + 1 >= total_pages:
            break

        page += 1
        if page >= max_pages:
            break

    return all_events


# ============================================================
# PUBLIC PULL FUNCTIONS
# ============================================================
def pull_ticketmaster_week_city(
    *,
    start_day: str,
    end_day: str,
    city: str = "Toronto",
    country_code: str = "CA",
    apikey: str | None = None,
) -> List[PulledEvent]:
    """
    City-based search. This is usually the simplest.

    start_day inclusive, end_day exclusive.
    """
    key = apikey or TICKETMASTER_API_KEY

    start_dt = datetime.fromisoformat(f"{start_day}T00:00:00")
    end_dt = datetime.fromisoformat(f"{end_day}T00:00:00")

    params = {
        "apikey": key,
        "city": city,
        "countryCode": country_code,
        "startDateTime": _iso_utc(start_dt),
        "endDateTime": _iso_utc(end_dt),
        "size": 200,
        "sort": "date,asc",
    }
    return _fetch_paged(params)


def pull_ticketmaster_week_geo(
    *,
    start_day: str,
    end_day: str,
    lat: float = TORONTO_LAT,
    lon: float = TORONTO_LON,
    radius: int = 35,
    unit: str = "km",
    apikey: str | None = None,
) -> List[PulledEvent]:
    """
    Geo-based search. Useful if city string matching fails.
    """
    key = apikey or TICKETMASTER_API_KEY

    start_dt = datetime.fromisoformat(f"{start_day}T00:00:00")
    end_dt = datetime.fromisoformat(f"{end_day}T00:00:00")

    params = {
        "apikey": key,
        "latlong": f"{lat},{lon}",
        "radius": int(radius),
        "unit": unit,
        "startDateTime": _iso_utc(start_dt),
        "endDateTime": _iso_utc(end_dt),
        "size": 200,
        "sort": "date,asc",
    }
    return _fetch_paged(params)


def pull_ticketmaster_week_keyword(
    *,
    start_day: str,
    end_day: str,
    keyword: str,
    city: str = "Toronto",
    country_code: str = "CA",
    apikey: str | None = None,
) -> List[PulledEvent]:
    """
    Keyword search, narrowed by city.
    """
    key = apikey or TICKETMASTER_API_KEY

    start_dt = datetime.fromisoformat(f"{start_day}T00:00:00")
    end_dt = datetime.fromisoformat(f"{end_day}T00:00:00")

    params = {
        "apikey": key,
        "keyword": keyword,
        "city": city,
        "countryCode": country_code,
        "startDateTime": _iso_utc(start_dt),
        "endDateTime": _iso_utc(end_dt),
        "size": 200,
        "sort": "date,asc",
    }
    return _fetch_paged(params)


# ============================================================
# SAVE HELPERS
# ============================================================
def write_events_json(path: str | Path, events: List[PulledEvent]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([asdict(e) for e in events], f, indent=2, ensure_ascii=False)
    return path


def write_events_csv(path: str | Path, events: List[PulledEvent]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    cols = [
        "source",
        "provider",
        "id",
        "name",
        "start_utc",
        "url",
        "venue",
        "city",
        "lat",
        "lon",
        "classification",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for e in events:
            w.writerow(asdict(e))
    return path


# ============================================================
# MAIN (manual run / debugging)
# ============================================================
if __name__ == "__main__":
    # Pick literally any week you want
    start_day = "2026-01-01"
    end_day = "2026-01-08"  # end-exclusive

    print(f"Pulling Ticketmaster events for: {start_day} → {end_day} (end-exclusive)")
    print(f"Using API key prefix: {TICKETMASTER_API_KEY[:6]}...")

    print("\n=== TRY #1: city search ===")
    events_city = pull_ticketmaster_week_city(
        start_day=start_day,
        end_day=end_day,
        city="Toronto",
        country_code="CA",
    )
    print(f"Collected {len(events_city)} events via city search")

    print("\n=== TRY #2: geo search ===")
    events_geo = pull_ticketmaster_week_geo(
        start_day=start_day,
        end_day=end_day,
        lat=TORONTO_LAT,
        lon=TORONTO_LON,
        radius=35,
        unit="km",
    )
    print(f"Collected {len(events_geo)} events via geo search")

    print("\n=== TRY #3: keyword search (Raptors) ===")
    events_kw = pull_ticketmaster_week_keyword(
        start_day=start_day,
        end_day=end_day,
        keyword="Raptors",
        city="Toronto",
        country_code="CA",
    )
    print(f"Collected {len(events_kw)} events via keyword search")

    # Merge unique by id
    merged: Dict[str, PulledEvent] = {}
    for ev in (events_city + events_geo + events_kw):
        merged[ev.id] = ev
    events = list(merged.values())

    print(f"\n[TOTAL UNIQUE] {len(events)} events")

    out_json = write_events_json(
        f"data/events/events_{start_day}_to_{end_day}_ticketmaster.json",
        events,
    )
    out_csv = write_events_csv(
        f"data/events/events_{start_day}_to_{end_day}_ticketmaster.csv",
        events,
    )

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_csv}")

    # Preview first few
    print("\nPreview:")
    for e in events[:10]:
        print(f"- {e.start_utc} | {e.name} | {e.venue}")
