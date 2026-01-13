# rebalance3/viz/stations_map.py
import folium
from folium import PolyLine

CENTER_LAT = 43.6532
CENTER_LON = -79.3832

EMPTY_THRESHOLD = 0.1
FULL_THRESHOLD = 0.9


# ============================================================
# STATIONS — KEEP DESIGN
# ============================================================
def add_station_markers(m, stations, state, t_current, mode):
    for s in stations:
        sid = str(s["station_id"])
        st = state.get((sid, t_current))

        fill_color = "#333333"
        popup = [
            f"<b>{s['name']}</b>",
            f"Station ID: {sid}",
            f"Capacity: {s['capacity']}",
        ]

        if st:
            bikes = st["bikes"]
            cap = st["capacity"]
            ratio = bikes / cap if cap else 0

            if ratio <= EMPTY_THRESHOLD:
                fill_color = "#d73027"
            elif ratio >= FULL_THRESHOLD:
                fill_color = "#4575b4"
            else:
                fill_color = "#666666"

            if mode == "t_min":
                popup.insert(2, f"Time: {t_current//60:02d}:{t_current%60:02d}")
            else:
                popup.insert(2, f"Hour: {t_current:02d}:00")

            popup.insert(3, f"Bikes: {bikes} / {cap}")

        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=4,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.9,
            weight=0,
            popup="<br>".join(popup),
        ).add_to(m)


# ============================================================
# TRUCK MOVES — SIMPLE + CLEAR (NO TRIANGLES)
# ============================================================
def add_truck_moves(m, stations, truck_moves, t_cur):
    if not truck_moves:
        return

    station_pos = {str(s["station_id"]): (s["lat"], s["lon"]) for s in stations}

    for move in truck_moves:
        if move.t_min != t_cur:
            continue

        src = station_pos.get(move.from_station)
        dst = station_pos.get(move.to_station)
        if not src or not dst:
            continue

        PolyLine(
            locations=[src, dst],
            color="#000000",
            weight=4,
            opacity=0.95,
            tooltip=(
                f"Truck move<br>"
                f"{move.from_station} → {move.to_station}<br>"
                f"{move.bikes} bikes"
            ),
        ).add_to(m)

        folium.CircleMarker(
            location=src,
            radius=10,
            color="#d73027",
            weight=3,
            fill=False,
            tooltip=f"Pickup: {move.from_station}",
        ).add_to(m)

        folium.CircleMarker(
            location=dst,
            radius=10,
            color="#1a9850",
            weight=3,
            fill=False,
            tooltip=f"Dropoff: {move.to_station}",
        ).add_to(m)


# ============================================================
# MAP DOCUMENT
# ============================================================
def _build_map_document(
    stations,
    state,
    mode,
    valid_times,
    t_cur,
    *,
    title=None,
    truck_moves=None,
):
    m = folium.Map(
        location=[CENTER_LAT, CENTER_LON],
        zoom_start=12,
        tiles="cartodbpositron",
        prefer_canvas=False,
    )

    add_station_markers(m, stations, state, t_cur, mode)

    if truck_moves:
        add_truck_moves(m, stations, truck_moves, t_cur)

    if valid_times:
        from rebalance3.viz.time_bar import build_time_bar

        m.get_root().html.add_child(
            build_time_bar(
                state,
                stations,
                valid_times,
                t_cur,
                mode,
                truck_moves=truck_moves,
            )
        )

    m.get_root().html.add_child(
        folium.Element(
            f"""
<style>
#map-wrap {{
  position: relative;
  width: 100%;
}}

#map-wrap .leaflet-container {{
  width: 100% !important;
  height: 75vh !important;
  min-height: 520px;
}}

#map-title {{
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255,255,255,0.95);
  padding: 6px 16px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 600;
  z-index: 1300;
}}

#map-legend {{
  position: absolute;
  bottom: 140px;
  left: 16px;
  background: rgba(255,255,255,0.95);
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 12px;
  z-index: 1200;
}}
</style>

<script>
document.addEventListener("DOMContentLoaded", () => {{
  const mapEl = document.querySelector(".leaflet-container");
  if (!mapEl) return;

  const wrap = document.createElement("div");
  wrap.id = "map-wrap";
  mapEl.parentNode.insertBefore(wrap, mapEl);
  wrap.appendChild(mapEl);

  {"const t=document.createElement('div');t.id='map-title';t.textContent=%r;wrap.appendChild(t);" % title if title else ""}

  const legend = document.createElement("div");
  legend.id = "map-legend";
  legend.innerHTML = `
    <div><span style="color:#d73027">●</span> empty</div>
    <div><span style="color:#4575b4">●</span> full</div>
    <div><span style="color:#666">●</span> ok</div>
    <hr>
    <div><span style="color:#d73027">◯</span> pickup</div>
    <div><span style="color:#1a9850">◯</span> dropoff</div>
    <div>— truck move</div>
  `;
  wrap.appendChild(legend);

  const timebar = document.getElementById("timebar");
  if (timebar) wrap.appendChild(timebar);
}});
</script>
"""
        )
    )

    return m.get_root().render()
