import folium
from folium import PolyLine, RegularPolygonMarker

from rebalance3.trucks.types import TruckMove

EMPTY_THRESHOLD = 0.1
FULL_THRESHOLD = 0.9


# ============================================================
# STATIONS — KEEP DESIGN (UNCHANGED)
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
            [s["lat"], s["lon"]],
            radius=4,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.9,
            weight=0,
            popup="<br>".join(popup),
        ).add_to(m)


# ============================================================
# TRUCK MOVES — CLEAR + DIRECTIONAL
# ============================================================
def add_truck_moves(m, stations, truck_moves, t_cur):
    """
    Visual encoding:
      - RED ring: pickup station
      - GREEN ring: dropoff station
      - BLACK line: movement
      - GREEN triangle: direction arrow
      - Line thickness ~ bikes moved
    """

    if not truck_moves:
        return

    station_pos = {
        str(s["station_id"]): (s["lat"], s["lon"])
        for s in stations
    }

    for move in truck_moves:
        if move.t_min != t_cur:
            continue

        src = station_pos.get(move.from_station)
        dst = station_pos.get(move.to_station)
        if not src or not dst:
            continue

        bikes = move.bikes
        weight = min(2 + bikes / 4, 8)  # scale thickness, capped

        # ---- movement line ----
        PolyLine(
            locations=[src, dst],
            color="#111111",
            weight=weight,
            opacity=0.9,
            tooltip=(
                f"<b>Truck move</b><br>"
                f"Pickup: {move.from_station}<br>"
                f"Dropoff: {move.to_station}<br>"
                f"Bikes moved: {bikes}"
            ),
        ).add_to(m)

        # ---- pickup (RED ring) ----
        folium.CircleMarker(
            location=src,
            radius=10,
            color="#d73027",
            weight=3,
            fill=False,
            tooltip=f"Pickup station ({bikes} bikes removed)",
        ).add_to(m)

        # ---- dropoff (GREEN ring) ----
        folium.CircleMarker(
            location=dst,
            radius=10,
            color="#1a9850",
            weight=3,
            fill=False,
            tooltip=f"Dropoff station ({bikes} bikes added)",
        ).add_to(m)

        # ---- direction arrow (triangle at destination) ----
        RegularPolygonMarker(
            location=dst,
            number_of_sides=3,
            radius=6,
            rotation=0,
            color="#1a9850",
            fill_color="#1a9850",
            fill_opacity=0.9,
        ).add_to(m)
