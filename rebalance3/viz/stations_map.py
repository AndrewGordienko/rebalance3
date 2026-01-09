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
    graphs=True,
    title=None,
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

        # ---- sidebar + timebar ----
        m.get_root().html.add_child(
            build_sidebar(mode=mode, t_current=t_cur)
        )

        if valid_times:
            m.get_root().html.add_child(
                build_time_bar(
                    state,
                    stations,
                    valid_times,
                    t_cur,
                    mode,
                )
            )

        # ---- layout + DOM wiring ----
        m.get_root().html.add_child(folium.Element(f"""
<style>
html, body {{
  margin: 0;
  padding: 0;
  background: white;
}}

#map-wrap {{
  position: relative;
  margin: 24px auto;
  width: calc(100% - 48px);
  max-width: 1600px;
  height: {"90vh" if not graphs else "75vh"};
  min-height: 500px;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,0.15);
}}

#map-wrap .leaflet-container {{
  width: 100% !important;
  height: 100% !important;
}}

/* ===== TITLE ===== */
#map-title {{
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255,255,255,0.95);
  padding: 6px 16px;
  border-radius: 999px;
  font-family: sans-serif;
  font-size: 14px;
  font-weight: 600;
  z-index: 1100;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}}

/* ===== MOVE ZOOM CONTROLS TO RIGHT ===== */
#map-wrap .leaflet-top.leaflet-left {{
  left: auto !important;
  right: 12px;
}}

#map-wrap .leaflet-control-zoom {{
  margin-top: 12px;
}}

/* ===== GRAPHS ===== */
#graphs {{
  max-width: 1600px;
  margin: 0 auto 80px auto;
  padding: 0 24px;
}}

#graphs-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}}

#graphs-grid canvas {{
  width: 100% !important;
  height: 360px !important;
}}

@media (max-width: 900px) {{
  #graphs-grid {{
    grid-template-columns: 1fr;
  }}
}}
</style>

<script>
document.addEventListener("DOMContentLoaded", () => {{
  const map = document.querySelector(".leaflet-container");
  if (!map) return;

  // ---- wrap map ----
  const wrap = document.createElement("div");
  wrap.id = "map-wrap";
  map.parentNode.insertBefore(wrap, map);
  wrap.appendChild(map);

  // ---- title ----
  {"if (" + repr(bool(title)).lower() + ") {" if title else ""}
  const title = document.createElement("div");
  title.id = "map-title";
  title.textContent = {repr(title)};
  wrap.appendChild(title);
  {"}" if title else ""}

  // ---- sidebar ----
  const sidebar = document.querySelector('div[style*="top:15px"][style*="left:15px"]');
  if (sidebar) {{
    wrap.appendChild(sidebar);
    sidebar.style.position = "absolute";
    sidebar.style.top = "48px";
    sidebar.style.left = "15px";
  }}

  // ---- timebar ----
  const timebar = document.getElementById("timebar");
  if (timebar) {{
    wrap.appendChild(timebar);
    timebar.style.position = "absolute";
    timebar.style.left = "0";
    timebar.style.right = "0";
    timebar.style.bottom = "0";
  }}

  // ---- graphs after map ----
  const graphs = document.getElementById("graphs");
  if (graphs) {{
    wrap.parentNode.insertBefore(graphs, wrap.nextSibling);
  }}
}});
</script>
"""))

        # ---- graphs BELOW map ----
        if graphs and valid_times:
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
