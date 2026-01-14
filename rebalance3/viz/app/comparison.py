# rebalance3/viz/comparison.py
from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from rebalance3.viz.data.state_loader import load_station_state
from rebalance3.viz.data.time_snap import snap_time
from rebalance3.viz.maps.render import render_map_document
from rebalance3.viz.charts.graphs import build_comparison_graphs

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def serve_comparison(
    scenarios,
    host="127.0.0.1",
    port=8080,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
    graphs=True,
    title="Bike Share Rebalancing — Viewer",
):
    """
    Scenarios: list[Scenario]
      Scenario fields expected:
        - .name
        - .state_csv (Path)
        - .bucket_minutes (int)  (optional but preferred)
        - .meta dict with optional "truck_moves"
    """

    stations = load_stations(stations_file)

    scenario_states = []
    mode = None
    valid_times = None

    # Load all scenario states
    for s in scenarios:
        state, s_mode, s_times = load_station_state(s.state_csv)
        scenario_states.append(state)

        # all states should share the same time index
        mode = s_mode
        valid_times = s_times

    if mode is None:
        mode = "t_min"
    if valid_times is None:
        valid_times = []

    app = Flask(__name__)

    def _resolve_time():
        if not valid_times:
            return 0
        key = "t" if mode == "t_min" else "hour"
        t_req = request.args.get(key, valid_times[0], type=int)
        return snap_time(t_req, valid_times)

    def _time_qp(t_cur: int) -> str:
        return f"t={t_cur}" if mode == "t_min" else f"hour={t_cur}"

    @app.route("/")
    def _index():
        t_cur = _resolve_time()

        # which scenario to show in single-map mode
        s_idx = request.args.get("s", 0, type=int)
        if s_idx < 0 or s_idx >= len(scenarios):
            s_idx = 0

        compare = request.args.get("compare", 0, type=int)
        compare = 1 if compare else 0

        # compare selection
        a_idx = request.args.get("a", 0, type=int)
        b_idx = request.args.get("b", 1, type=int)

        if a_idx < 0 or a_idx >= len(scenarios):
            a_idx = 0
        if b_idx < 0 or b_idx >= len(scenarios):
            b_idx = min(1, len(scenarios) - 1)

        qp_time = _time_qp(t_cur)

        # single map URL
        single_url = f"/map/{s_idx}?{qp_time}"

        # compare URLs
        map_a_url = f"/map/{a_idx}?{qp_time}"
        map_b_url = f"/map/{b_idx}?{qp_time}"

        graphs_html = ""
        if graphs and compare and len(scenarios) >= 2:
            graphs_html = build_comparison_graphs(
                states=[scenario_states[a_idx], scenario_states[b_idx]],
                stations=stations,
                valid_times=valid_times,
                mode=mode,
                scenario_names=[scenarios[a_idx].name, scenarios[b_idx].name],
            ).render()

        # build dropdown options
        scenario_opts = "\n".join(
            [
                f'<option value="{i}" {"selected" if i == s_idx else ""}>{scenarios[i].name}</option>'
                for i in range(len(scenarios))
            ]
        )

        a_opts = "\n".join(
            [
                f'<option value="{i}" {"selected" if i == a_idx else ""}>{scenarios[i].name}</option>'
                for i in range(len(scenarios))
            ]
        )

        b_opts = "\n".join(
            [
                f'<option value="{i}" {"selected" if i == b_idx else ""}>{scenarios[i].name}</option>'
                for i in range(len(scenarios))
            ]
        )

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

#topbar {{
  max-width: 1800px;
  margin: 16px auto 10px auto;
  padding: 0 24px;
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}}

#topbar-left {{
  display: flex;
  flex-direction: column;
  gap: 6px;
}}

#topbar h1 {{
  font-size: 18px;
  font-weight: 800;
  margin: 0;
}}

#controls {{
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}}

.ctrl {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: #f6f6f6;
  border: 1px solid #e6e6e6;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 13px;
}}

select {{
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 13px;
  background: white;
}}

label {{
  user-select: none;
}}

#maps {{
  max-width: 1800px;
  margin: 0 auto;
  padding: 0 24px 18px 24px;
}}

#single-map {{
  width: 100%;
}}

#compare-maps {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}}

.map-frame {{
  width: 100%;
  height: 75vh;
  min-height: 520px;
  border: 0;
  background: transparent;
}}

@media (max-width: 1100px) {{
  #compare-maps {{
    grid-template-columns: 1fr;
  }}
}}

#graphs-root {{
  max-width: 1800px;
  margin: 0 auto;
  padding: 0 24px 24px 24px;
}}
</style>

<script>
// ---------------------------------------------------------
// When a map timebar in an iframe sends set-time,
// update iframe URLs to the same time.
// ---------------------------------------------------------
window.addEventListener("message", (e) => {{
  if (!e.data || e.data.type !== "set-time") return;

  const t = e.data.value;

  document.querySelectorAll(".map-frame").forEach((iframe) => {{
    const url = new URL(iframe.src);
    const key = url.searchParams.has("t") ? "t" : "hour";
    url.searchParams.set(key, t);
    iframe.src = url.toString();
  }});
}});

function applyControls() {{
  const compare = document.getElementById("compare-toggle").checked ? 1 : 0;

  const url = new URL(window.location.href);
  url.searchParams.set("compare", String(compare));

  if (!compare) {{
    const s = document.getElementById("scenario-single").value;
    url.searchParams.set("s", s);
  }} else {{
    const a = document.getElementById("scenario-a").value;
    const b = document.getElementById("scenario-b").value;
    url.searchParams.set("a", a);
    url.searchParams.set("b", b);
  }}

  window.location.href = url.toString();
}}
</script>
</head>

<body>

<div id="topbar">
  <div id="topbar-left">
    <h1>{title}</h1>

    <div id="controls">

      <div class="ctrl">
        <label>
          <input id="compare-toggle" type="checkbox" onchange="applyControls()" {"checked" if compare else ""}/>
          Compare
        </label>
      </div>

      <div class="ctrl" id="single-controls" style="display:{'none' if compare else 'inline-flex'};">
        <span>Scenario</span>
        <select id="scenario-single" onchange="applyControls()">
          {scenario_opts}
        </select>
      </div>

      <div class="ctrl" id="compare-controls" style="display:{'inline-flex' if compare else 'none'};">
        <span>A</span>
        <select id="scenario-a" onchange="applyControls()">
          {a_opts}
        </select>

        <span style="margin-left:8px;">B</span>
        <select id="scenario-b" onchange="applyControls()">
          {b_opts}
        </select>
      </div>

    </div>
  </div>
</div>

<div id="maps">

  <div id="single-map" style="display:{'none' if compare else 'block'};">
    <iframe class="map-frame" src="{single_url}"></iframe>
  </div>

  <div id="compare-maps" style="display:{'grid' if compare else 'none'};">
    <iframe class="map-frame" src="{map_a_url}"></iframe>
    <iframe class="map-frame" src="{map_b_url}"></iframe>
  </div>

</div>

<div id="graphs-root" style="display:{'block' if (compare and graphs_html) else 'none'};">
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
        scenario = scenarios[i]

        bucket_minutes = getattr(scenario, "bucket_minutes", 15) or 15

        return render_map_document(
            stations=stations,
            state=scenario_states[i],
            mode=mode,
            valid_times=valid_times,
            t_cur=t_cur,
            title=scenario.name,
            truck_moves=scenario.meta.get("truck_moves"),
            bucket_minutes=bucket_minutes,
        )

    app.run(host=host, port=port)
