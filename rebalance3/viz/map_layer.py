# rebalance3/viz/map_layer.py
import folium
from folium import PolyLine

from rebalance3.trucks.types import TruckMove

EMPTY_THRESHOLD = 0.1
FULL_THRESHOLD = 0.9


# ============================================================
# STATIONS — KEEP EXACT DESIGN (UNCHANGED)
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
# TRUCK MOVES — VERY OBVIOUS VISUALIZATION
# ============================================================
def add_truck_moves(m, stations, truck_moves, t_cur):
    """
    Draw truck moves at time t_cur with:
      - thick black line (direction implied)
      - BIG pickup circle
      - BIG dropoff circle
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

        # -------- line (movement) --------
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

        # -------- pickup ring --------
        folium.CircleMarker(
            location=src,
            radius=10,
            color="#000000",
            weight=3,
            fill=False,
            tooltip=f"Pickup: {move.from_station}",
        ).add_to(m)

        # -------- dropoff ring --------
        folium.CircleMarker(
            location=dst,
            radius=10,
            color="#000000",
            weight=3,
            fill=False,
            dash_array="4,4",
            tooltip=f"Dropoff: {move.to_station}",
        ).add_to(m)
