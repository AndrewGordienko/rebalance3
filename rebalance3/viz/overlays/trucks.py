# rebalance3/viz/overlays/trucks.py
import folium
from folium import PolyLine


def _mv_get(m, key, default=None):
    """Support TruckMove dataclass OR dict."""
    if m is None:
        return default
    if isinstance(m, dict):
        return m.get(key, default)
    return getattr(m, key, default)


def _as_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default


def add_truck_moves(
    m,
    stations,
    truck_moves,
    *,
    mode: str,
    t_cur: int,
    bucket_minutes: int = 15,
    show_bucket_window: bool = True,
):
    """
    Draw truck moves for the current displayed time.

    Time matching:
      - mode == "hour":
          show moves where (t_min // 60) == t_cur
      - mode == "t_min":
          if show_bucket_window:
              show moves where t_cur <= t_min < t_cur + bucket_minutes
          else:
              show moves where t_min == t_cur

    Visual encoding:
      - black line between stations
      - red ring on pickup
      - green ring on dropoff
    """

    if not truck_moves:
        return

    station_pos = {
        str(s["station_id"]): (float(s["lat"]), float(s["lon"]))
        for s in stations
    }

    t_cur_i = _as_int(t_cur, 0)
    t0 = t_cur_i
    t1 = t_cur_i + int(bucket_minutes)

    for move in truck_moves:
        tm = _as_int(_mv_get(move, "t_min", None), None)
        if tm is None:
            continue

        # ---- time filter ----
        if mode == "hour":
            if (tm // 60) != int(t_cur_i):
                continue
        else:
            # mode == "t_min"
            if show_bucket_window:
                if not (t0 <= tm < t1):
                    continue
            else:
                if tm != int(t_cur_i):
                    continue

        src_id = _mv_get(move, "from_station", None)
        dst_id = _mv_get(move, "to_station", None)
        bikes = _as_int(_mv_get(move, "bikes", 0), 0)

        if src_id is None or dst_id is None:
            continue

        src_id = str(src_id)
        dst_id = str(dst_id)

        src = station_pos.get(src_id)
        dst = station_pos.get(dst_id)
        if not src or not dst:
            continue

        # ---- movement line ----
        PolyLine(
            locations=[src, dst],
            color="#000000",
            weight=4,
            opacity=0.95,
            tooltip=(
                f"Truck move<br>"
                f"{src_id} → {dst_id}<br>"
                f"{bikes} bikes<br>"
                f"t={tm} min"
            ),
        ).add_to(m)

        # ---- pickup ring (RED) ----
        folium.CircleMarker(
            location=src,
            radius=10,
            color="#d73027",
            weight=3,
            fill=False,
            tooltip=f"Pickup: {src_id}",
        ).add_to(m)

        # ---- dropoff ring (GREEN) ----
        folium.CircleMarker(
            location=dst,
            radius=10,
            color="#1a9850",
            weight=3,
            fill=False,
            tooltip=f"Dropoff: {dst_id}",
        ).add_to(m)