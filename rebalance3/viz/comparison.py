from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from rebalance3.viz.state_loader import load_station_state, snap_time
from rebalance3.viz.stations_map import _build_map_document
from rebalance3.viz.graphs import build_comparison_graphs

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def serve_comparison(
    scenarios,
    host="127.0.0.1",
    port=8080,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
    graphs=True,
    title="Bike Share Rebalancing — Scenario Comparison",
):
    stations = load_stations(stations_file)

    scenario_states = []
    mode = None
    valid_times = None

    for s in scenarios:
        state, s_mode, s_times = load_station_state(s.state_csv)
        scenario_states.append(state)
        mode = s_mode
        valid_times = s_times

    app = Flask(__name__)

    def _resolve_time():
        if not valid_times:
            return 0
        key = "t" if mode == "t_min" else "hour"
        t_req = request.args.get(key, valid_times[0], type=int)
        return snap_time(t_req, valid_times)

    @app.route("/")
    def _index():
        t_cur = _resolve_time()
        qp = f"t={t_cur}" if mode == "t_min" else f"hour={t_cur}"

        graphs_html = ""
        if graphs and len(scenarios) >= 2:
            graphs_html = build_comparison_graphs(
                states=[scenario_states[0], scenario_states[1]],
                stations=stations,
                valid_times=valid_times,
                mode=mode,
                scenario_names=[scenarios[0].name, scenarios[1].name],
            ).render()

        return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>{title}</title>

<style>
html, body {{
  margin: 0;
  padding: 0;
  font-family: sans-serif;
  background: white;
}}

/* ===== PAGE TITLE ===== */
#page-title {{
  max-width: 1800px;
  margin: 16px auto 4px auto;
  padding: 0 24px;
}}

#page-title h1 {{
  font-size: 22px;
  font-weight: 700;
  margin: 0;
}}

/* ===== MAPS ===== */
#maps {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  padding: 16px 24px 0 24px;   /* 👈 ZERO bottom padding */
  max-width: 1800px;
  margin: 0 auto;
}}

.map-frame {{
  width: 100%;
  height: 75vh;
  min-height: 520px;
  border: 0;
  box-shadow: none;
  background: transparent;
}}

/* ===== GRAPHS HARD RESET ===== */
#graphs-root {{
  margin-top: 0 !important;
  padding-top: 0 !important;
}}

#graphs-root > * {{
  margin-top: 0 !important;
}}

/* ===== RESPONSIVE ===== */
@media (max-width: 1100px) {{
  #maps {{
    grid-template-columns: 1fr;
  }}
}}
</style>

<script>
window.addEventListener("message", (e) => {{
  if (!e.data || e.data.type !== "set-time") return;

  const url = new URL(window.location.href);
  const key = url.searchParams.has("t") ? "t" : "hour";
  url.searchParams.set(key, e.data.value);
  window.location.href = url.toString();
}});
</script>
</head>

<body>

<div id="page-title">
  <h1>{title}</h1>
</div>

<div id="maps">
  <iframe class="map-frame" src="/map/0?{qp}"></iframe>
  <iframe class="map-frame" src="/map/1?{qp}"></iframe>
</div>

<!-- FORCE GRAPH CONTAINER -->
<div id="graphs-root">
  {graphs_html}
</div>

</body>
</html>
"""

    @app.route("/map/<int:i>")
    def _map(i: int):
        if i < 0 or i >= len(scenarios):
            return "Scenario index out of range", 404

        t_cur = _resolve_time()

        return _build_map_document(
            stations=stations,
            state=scenario_states[i],
            mode=mode,
            valid_times=valid_times,
            t_cur=t_cur,
            title=scenarios[i].name,
        )

    app.run(host=host, port=port)
