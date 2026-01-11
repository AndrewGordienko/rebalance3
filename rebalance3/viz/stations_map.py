import folium
from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from rebalance3.viz.state_loader import load_station_state, snap_time
from rebalance3.viz.map_layer import add_station_markers, add_truck_moves
from rebalance3.viz.time_bar import build_time_bar

CENTER_LAT = 43.6532
CENTER_LON = -79.3832

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


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
        prefer_canvas=True,
    )

    # ---- stations ----
    add_station_markers(m, stations, state, t_cur, mode)

    # ---- truck moves (TIME FILTERED) ----
    if truck_moves:
        add_truck_moves(
            m=m,
            stations=stations,
            truck_moves=truck_moves,
            t_cur=t_cur,
        )

    # ---- time bar ----
    if valid_times:
        m.get_root().html.add_child(
            build_time_bar(state, stations, valid_times, t_cur, mode)
        )

    # ---- layout + overlays ----
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
  box-shadow: 0 1px 4px rgba(0,0,0,0.2);
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

  const wrap = document.createElement("div");
  wrap.id = "map-wrap";
  mapEl.parentNode.insertBefore(wrap, mapEl);
  wrap.appendChild(mapEl);

  {"const t=document.createElement('div');t.id='map-title';t.textContent=%r;wrap.appendChild(t);" % title if title else ""}

  const legend = document.createElement("div");
  legend.id = "map-legend";
  legend.innerHTML = `
    <div><span class="legend-dot" style="background:#d73027"></span> empty</div>
    <div><span class="legend-dot" style="background:#4575b4"></span> full</div>
    <div><span class="legend-dot" style="background:#666"></span> ok</div>
    <hr style="margin:6px 0">
    <div><strong>Truck move</strong>: arrow</div>
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


def serve_stations_map(
    *,
    scenario=None,
    host="127.0.0.1",
    port=8080,
    debug=False,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
):
    """
    Render a single scenario map.
    Scenario.meta may include:
      - truck_moves: List[TruckMove]
    """

    if scenario is None:
        raise ValueError("serve_stations_map requires a Scenario")

    stations = load_stations(stations_file)
    state, mode, valid_times = load_station_state(scenario.state_csv)

    truck_moves = scenario.meta.get("truck_moves")

    app = Flask(__name__)

    @app.route("/")
    def _view():
        key = "t" if mode == "t_min" else "hour"
        t_req = request.args.get(key, valid_times[0], type=int)
        t_cur = snap_time(t_req, valid_times)

        return _build_map_document(
            stations=stations,
            state=state,
            mode=mode,
            valid_times=valid_times,
            t_cur=t_cur,
            title=scenario.name,
            truck_moves=truck_moves,
        )

    app.run(host=host, port=port, debug=debug)
