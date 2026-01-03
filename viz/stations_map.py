import folium
from flask import Flask
from util.stations import load_stations

CENTER_LAT = 43.6532
CENTER_LON = -79.3832

def build_stations_map(stations):
    m = folium.Map(
        location=[CENTER_LAT, CENTER_LON],
        zoom_start=12,
        tiles="cartodbpositron",
        prefer_canvas=True,
    )

    m.get_root().html.add_child(
        folium.Element(
            """
<style>
html, body {
  height: 100%;
  width: 100%;
  margin: 0;
}
.leaflet-container {
  height: 100vh !important;
  width: 100vw !important;
}
.leaflet-control-zoom {
  position: fixed !important;
  top: 15px !important;
  right: 15px !important;
  left: auto !important;
}
.leaflet-popup-content {
  margin: 10px 12px;
  font-family: sans-serif;
  font-size: 12px;
}
</style>
"""
        )
    )

    for s in stations:
        popup = f"""
        <div style="width:220px;">
          <b>{s["name"]}</b><br>
          Station ID: {s["station_id"]}<br>
          Capacity: {s["capacity"]}
        </div>
        """

        folium.CircleMarker(
            location=[s["lat"], s["lon"]],
            radius=4,
            fill=True,
            fill_color="#333333",
            fill_opacity=0.9,
            weight=0,
            popup=popup,
        ).add_to(m)

    header = """
    <div style="
        position:fixed;
        top:15px;
        left:15px;
        z-index:1000;
        background:rgba(255,255,255,0.95);
        padding:12px 14px;
        border-radius:8px;
        box-shadow:0 1px 4px rgba(0,0,0,0.25);
        font-family:sans-serif;
        font-size:12px;
    ">
      <div style="font-weight:700;">Toronto Bike Share</div>
      <div style="margin-top:4px;color:#444;">
        Station locations
      </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(header))

    return m


def serve_stations_map(stations_file, host="127.0.0.1", port=8080, debug=False):
    """
    Library entrypoint: call this and you get a running website.
    """
    app = Flask(__name__)

    @app.route("/")
    def _view():
        stations = load_stations(stations_file)
        m = build_stations_map(stations)
        return m.get_root().render()

    # run the server (blocking)
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    serve_stations_map("given data/station_information.json", port=8080, debug=False)
