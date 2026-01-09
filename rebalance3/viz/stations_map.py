# rebalance3/viz/stations_map.py

import folium
from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from .state_loader import load_station_state, snap_time
from .map_layer import add_station_markers
from .sidebar import build_sidebar
from .time_bar import build_time_bar
from .graphs import build_summary_graphs

CENTER_LAT = 43.6532
CENTER_LON = -79.3832

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def serve_stations_map(
    host="127.0.0.1",
    port=8080,
    debug=False,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
    state_by_hour_csv=None,
):
    stations = load_stations(stations_file)
    state, mode, valid_times = load_station_state(state_by_hour_csv)

    app = Flask(__name__)

    @app.route("/")
    def _view():
        # ---- resolve time ----
        if not valid_times:
            t_cur = 0
        else:
            t_req = (
                request.args.get("t", valid_times[0], type=int)
                if mode == "t_min"
                else request.args.get("hour", valid_times[0], type=int)
            )
            t_cur = snap_time(t_req, valid_times)

        # ---- MAP ----
        m = folium.Map(
            location=[CENTER_LAT, CENTER_LON],
            zoom_start=12,
            tiles="cartodbpositron",
            prefer_canvas=True,
        )

        add_station_markers(m, stations, state, t_cur, mode)

        # ---- sidebar + timebar (added normally, reparented later) ----
        m.get_root().html.add_child(
            build_sidebar(mode=mode, t_current=t_cur)
        )

        if valid_times:
            m.get_root().html.add_child(
                build_time_bar(state, stations, valid_times, t_cur, mode)
            )

        # ---- layout + DOM wiring ----
        m.get_root().html.add_child(folium.Element("""
<style>
html, body {
  margin: 0;
  padding: 0;
  background: white;
}

/* ================= MAP ================= */
#map-wrap {
  position: relative;
  margin: 24px auto;
  width: calc(100% - 48px);
  max-width: 1600px;
  height: 75vh;
  min-height: 500px;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15);
}

#map-wrap .leaflet-container {
  width: 100% !important;
  height: 100% !important;
}

/* ===== MOVE ZOOM CONTROLS TO RIGHT ===== */
#map-wrap .leaflet-top.leaflet-left {
  left: auto !important;
  right: 12px;
}

#map-wrap .leaflet-control-zoom {
  margin-top: 12px;
}

/* ================= GRAPHS ================= */
#graphs {
  max-width: 1600px;
  margin: 0 auto 80px auto;
  padding: 0 24px;
}

#graphs-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}

#graphs-grid canvas {
  width: 100% !important;
  height: 360px !important;
}

@media (max-width: 900px) {
  #graphs-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<script>
document.addEventListener("DOMContentLoaded", () => {
  // ---- wrap map ----
  const map = document.querySelector(".leaflet-container");
  if (!map) return;

  const wrap = document.createElement("div");
  wrap.id = "map-wrap";
  map.parentNode.insertBefore(wrap, map);
  wrap.appendChild(map);

  // ---- move sidebar into map ----
  const sidebar = document.querySelector('div[style*="top:15px"][style*="left:15px"]');
  if (sidebar) {
    wrap.appendChild(sidebar);
    sidebar.style.position = "absolute";
    sidebar.style.top = "15px";
    sidebar.style.left = "15px";
  }

  // ---- move timebar into map ----
  const timebar = document.getElementById("timebar");
  if (timebar) {
    wrap.appendChild(timebar);
    timebar.style.position = "absolute";
    timebar.style.left = "0";
    timebar.style.right = "0";
    timebar.style.bottom = "0";
  }

  // ---- MOVE GRAPHS AFTER MAP (CRITICAL FIX) ----
  const graphs = document.getElementById("graphs");
  if (graphs) {
    wrap.parentNode.insertBefore(graphs, wrap.nextSibling);
  }
});
</script>
"""))

        # ---- graphs (added normally, reordered in JS) ----
        if valid_times:
            m.get_root().html.add_child(
                build_summary_graphs(
                    state,
                    stations,
                    valid_times,
                    mode,
                )
            )

        return m.get_root().render()

    app.run(host=host, port=port, debug=debug)
