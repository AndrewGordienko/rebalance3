# rebalance3/viz/maps/overlays/trucks.py
from __future__ import annotations

import folium
from folium import PolyLine


def _mv_get(m, key, default=None):
    """Support TruckMove dataclass OR dict."""
    if m is None:
        return default
    if isinstance(m, dict):
        return m.get(key, default)
    return getattr(m, key, default)


def add_truck_moves_overlay(
    m: folium.Map,
    *,
    stations,
    truck_moves,
    mode: str,
    t_cur: int,
    bucket_minutes: int = 15,
):
    """
    Draw truck moves on the map for the currently displayed time.

    Visual encoding:
      - BLACK line: movement
      - RED ring: pickup station
      - GREEN ring: dropoff station

    Time alignment rules:
      - mode == "t_min":
          show moves where t_min is inside [t_cur, t_cur + bucket_minutes)
          (because your state snapshots are bucketed)
      - mode == "hour":
          show moves where (t_min // 60) == t_cur
    """
    if not truck_moves:
        return

    # station_id -> (lat, lon)
    station_pos = {}
    for s in stations:
        sid = str(s.get("station_id"))
        if not sid:
            continue
        try:
            station_pos[sid] = (float(s["lat"]), float(s["lon"]))
        except Exception:
            continue

    # --- decide the active time window ---
    t_cur = int(t_cur)
    bucket_minutes = int(bucket_minutes)

    if mode == "hour":
        # whole hour
        t0 = t_cur * 60
        t1 = (t_cur + 1) * 60
    else:
        # snapshot bucket window
        t0 = t_cur
        t1 = t_cur + bucket_minutes

    for move in truck_moves:
        tm = _mv_get(move, "t_min", None)
        if tm is None:
            continue

        try:
            tm = int(tm)
        except Exception:
            continue

        # filter to the active window
        if not (t0 <= tm < t1):
            continue

        src_id = _mv_get(move, "from_station", None)
        dst_id = _mv_get(move, "to_station", None)
        bikes = _mv_get(move, "bikes", 0)

        if src_id is None or dst_id is None:
            continue

        src_id = str(src_id)
        dst_id = str(dst_id)

        try:
            bikes = int(bikes)
        except Exception:
            bikes = 0

        src = station_pos.get(src_id)
        dst = station_pos.get(dst_id)
        if not src or not dst:
            continue

        # --------------------------
        # 1) Movement line (BLACK)
        # --------------------------
        PolyLine(
            locations=[src, dst],
            color="#111111",
            weight=5,
            opacity=0.95,
            tooltip=(
                f"<b>Truck move</b><br>"
                f"{src_id} → {dst_id}<br>"
                f"{bikes} bikes<br>"
                f"t={tm} min"
            ),
        ).add_to(m)

        # --------------------------
        # 2) Pickup ring (RED)
        # --------------------------
        folium.CircleMarker(
            location=src,
            radius=11,
            color="#d73027",
            weight=4,
            fill=False,
            opacity=1.0,
            tooltip=f"Pickup: {src_id} ({bikes} bikes)",
        ).add_to(m)

        # --------------------------
        # 3) Dropoff ring (GREEN)
        # --------------------------
        folium.CircleMarker(
            location=dst,
            radius=11,
            color="#1a9850",
            weight=4,
            fill=False,
            opacity=1.0,
            tooltip=f"Dropoff: {dst_id} ({bikes} bikes)",
        ).add_to(m)
