import folium
from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from .state_loader import load_station_state, snap_time
from .map_layer import add_station_markers
from .time_bar import build_time_bar

CENTER_LAT = 43.6532
CENTER_LON = -79.3832

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def _build_map_document(stations, state, mode, valid_times, t_cur, title=None):
    m = folium.Map(
        location=[CENTER_LAT, CENTER_LON],
        zoom_start=12,
        tiles="cartodbpositron",
        prefer_canvas=True,
    )

    add_station_markers(m, stations, state, t_cur, mode)

    if valid_times:
        m.get_root().html.add_child(
            build_time_bar(state, stations, valid_times, t_cur, mode)
        )

    m.get_root().html.add_child(folium.Element(f"""
<style>
/* Invisible positioning wrapper only */
#map-wrap {{
  position: relative;
  width: 100%;
}}

/* Let Leaflet fully control height */
#map-wrap .leaflet-container {{
  width: 100% !important;
  height: 75vh !important;
  min-height: 520px;
}}

/* Title */
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
  z-index: 1300;
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
}}

/* Legend */
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

.legend-dot {{
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
  margin-right: 6px;
}}
</style>

<script>
document.addEventListener("DOMContentLoaded", () => {{
  const mapEl = document.querySelector(".leaflet-container");
  if (!mapEl) return;

  // Wrap map ONLY for overlay positioning
  const wrap = document.createElement("div");
  wrap.id = "map-wrap";
  mapEl.parentNode.insertBefore(wrap, mapEl);
  wrap.appendChild(mapEl);

  // Title
  {"const title=document.createElement('div'); title.id='map-title'; title.textContent=%r; wrap.appendChild(title);" % title if title else ""}

  // Legend
  const legend = document.createElement("div");
  legend.id = "map-legend";
  legend.innerHTML = `
    <div><span class="legend-dot" style="background:#d73027"></span> empty</div>
    <div><span class="legend-dot" style="background:#4575b4"></span> full</div>
    <div><span class="legend-dot" style="background:#666"></span> ok</div>
  `;
  wrap.appendChild(legend);

  // Timebar onto map
  const timebar = document.getElementById("timebar");
  if (timebar) {{
    wrap.appendChild(timebar);
  }}
}});
</script>
"""))

    return m.get_root().render()


def serve_stations_map(
    host="127.0.0.1",
    port=8080,
    debug=False,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
    state_by_hour_csv=None,
    title=None,
):
    stations = load_stations(stations_file)
    state, mode, valid_times = load_station_state(state_by_hour_csv)

    app = Flask(__name__)

    @app.route("/")
    def _view():
        key = "t" if mode == "t_min" else "hour"
        t_req = request.args.get(key, valid_times[0], type=int)
        t_cur = snap_time(t_req, valid_times)

        return _build_map_document(
            stations,
            state,
            mode,
            valid_times,
            t_cur,
            title,
        )

    app.run(host=host, port=port, debug=debug)
