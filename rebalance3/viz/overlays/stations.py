import folium

EMPTY_THRESHOLD = 0.10
FULL_THRESHOLD = 0.90


def add_station_markers(m, stations, state, t_current, mode):
    """
    Draw station markers using your existing color logic.
    state: dict[(station_id, t)] -> {"bikes": int, "capacity": int}
    """
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
            bikes = int(st["bikes"])
            cap = int(st["capacity"])
            ratio = bikes / cap if cap else 0.0

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
            location=[float(s["lat"]), float(s["lon"])],
            radius=4,
            fill=True,
            fill_color=fill_color,
            fill_opacity=0.9,
            weight=0,
            popup="<br>".join(popup),
        ).add_to(m)