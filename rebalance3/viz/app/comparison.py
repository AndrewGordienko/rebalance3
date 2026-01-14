# rebalance3/viz/comparison.py
from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from rebalance3.viz.data.state_loader import load_station_state
from rebalance3.viz.data.time_snap import snap_time
from rebalance3.viz.maps.render import render_map_document

from rebalance3.viz.charts.graphs import (
    build_comparison_graphs,
    build_single_graphs,
    build_multi_graphs,  # ✅ NEW
)

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def serve_comparison(
    scenarios,
    host="127.0.0.1",
    port=8080,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
    graphs=True,
    title="Bike Share Rebalancing — Viewer",
    layout: str | None = None,  # ✅ NEW: "grid4" or None
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

    def _initial_view_mode() -> str:
        """
        View modes:
          - "single": one map, 2 graphs
          - "compare": two maps, 4 graphs
          - "grid4": four maps, 8 graphs (first 4 scenarios by default)
        Priority:
          1) explicit query param view=...
          2) serve_comparison(layout="grid4")
          3) fallback old behavior
        """
        v = request.args.get("view", "", type=str).strip().lower()
        if v in {"single", "compare", "grid4"}:
            return v
        if layout and str(layout).lower() == "grid4":
            return "grid4"
        return "single"

    def _clamp_idx(i: int) -> int:
        if not scenarios:
            return 0
        return max(0, min(int(i), len(scenarios) - 1))

    @app.route("/")
    def _index():
        t_cur = _resolve_time()
        qp_time = _time_qp(t_cur)

        view = _initial_view_mode()

        # old selection params
        s_idx = _clamp_idx(request.args.get("s", 0, type=int))

        a_idx = _clamp_idx(request.args.get("a", 0, type=int))
        b_idx = _clamp_idx(request.args.get("b", 1, type=int))

        # grid indices (defaults: first 4)
        g0 = _clamp_idx(request.args.get("g0", 0, type=int))
        g1 = _clamp_idx(request.args.get("g1", 1, type=int))
        g2 = _clamp_idx(request.args.get("g2", 2, type=int))
        g3 = _clamp_idx(request.args.get("g3", 3, type=int))

        # avoid duplicates in grid: if user gave duplicates, we still render them,
        # but dropdowns will make it obvious.

        single_url = f"/map/{s_idx}?{qp_time}"
        map_a_url = f"/map/{a_idx}?{qp_time}"
        map_b_url = f"/map/{b_idx}?{qp_time}"

        grid_urls = [
            (g0, f"/map/{g0}?{qp_time}"),
            (g1, f"/map/{g1}?{qp_time}"),
            (g2, f"/map/{g2}?{qp_time}"),
            (g3, f"/map/{g3}?{qp_time}"),
        ]

        # ---------------------------------------------------------
        # ✅ Graphs:
        #   - grid4: 4 scenarios => 8 charts + 1 summary table
        #   - compare: A vs B => 4 charts + compare summary
        #   - single: 1 scenario => 2 charts + single summary
        # ---------------------------------------------------------
        graphs_html = ""
        if graphs:
            if view == "grid4":
                # Only render up to 4 maps/graph sets. If fewer scenarios exist, use what we have.
                idxs = [g0, g1, g2, g3]
                idxs = [i for i in idxs if 0 <= i < len(scenarios)]
                # if user has <4 scenarios, just use all
                if len(scenarios) <= 4:
                    idxs = list(range(len(scenarios)))

                states = [scenario_states[i] for i in idxs]
                names = [scenarios[i].name for i in idxs]

                graphs_html = build_multi_graphs(
                    states=states,
                    stations=stations,
                    valid_times=valid_times,
                    mode=mode,
                    scenario_names=names,
                ).render()

            elif view == "compare" and len(scenarios) >= 2:
                graphs_html = build_comparison_graphs(
                    states=[scenario_states[a_idx], scenario_states[b_idx]],
                    stations=stations,
                    valid_times=valid_times,
                    mode=mode,
                    scenario_names=[scenarios[a_idx].name, scenarios[b_idx].name],
                ).render()
            else:
                graphs_html = build_single_graphs(
                    state=scenario_states[s_idx],
                    stations=stations,
                    valid_times=valid_times,
                    mode=mode,
                    scenario_name=scenarios[s_idx].name,
                ).render()

        def _scenario_options(selected: int) -> str:
            return "\n".join(
                [
                    f'<option value="{i}" {"selected" if i == selected else ""}>{scenarios[i].name}</option>'
                    for i in range(len(scenarios))
                ]
            )

        scenario_opts_single = _scenario_options(s_idx)
        a_opts = _scenario_options(a_idx)
        b_opts = _scenario_options(b_idx)

        g0_opts = _scenario_options(g0)
        g1_opts = _scenario_options(g1)
        g2_opts = _scenario_options(g2)
        g3_opts = _scenario_options(g3)

        def _checked(v: str) -> str:
            return "checked" if view == v else ""

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

.ctrl .mini {{
  font-size: 12px;
  color: #333;
  font-weight: 700;
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

.map-frame {{
  width: 100%;
  height: 65vh;
  min-height: 480px;
  border: 0;
  background: transparent;
}}

#single-map {{
  width: 100%;
}}

#compare-maps {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}}

#grid4-maps {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 18px;
}}

@media (max-width: 1100px) {{
  #compare-maps {{
    grid-template-columns: 1fr;
  }}
  #grid4-maps {{
    grid-template-columns: 1fr;
  }}
  .map-frame {{
    height: 70vh;
    min-height: 520px;
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

function applyViewMode(mode) {{
  const url = new URL(window.location.href);
  url.searchParams.set("view", mode);

  // keep current time qp if present
  window.location.href = url.toString();
}}

function applyControls() {{
  const mode = document.querySelector('input[name="viewmode"]:checked').value;

  const url = new URL(window.location.href);
  url.searchParams.set("view", mode);

  if (mode === "single") {{
    const s = document.getElementById("scenario-single").value;
    url.searchParams.set("s", s);
  }} else if (mode === "compare") {{
    const a = document.getElementById("scenario-a").value;
    const b = document.getElementById("scenario-b").value;
    url.searchParams.set("a", a);
    url.searchParams.set("b", b);
  }} else if (mode === "grid4") {{
    url.searchParams.set("g0", document.getElementById("scenario-g0").value);
    url.searchParams.set("g1", document.getElementById("scenario-g1").value);
    url.searchParams.set("g2", document.getElementById("scenario-g2").value);
    url.searchParams.set("g3", document.getElementById("scenario-g3").value);
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
          <input type="radio" name="viewmode" value="single" onchange="applyControls()" {_checked("single")} />
          Single
        </label>
        <label style="margin-left:10px;">
          <input type="radio" name="viewmode" value="compare" onchange="applyControls()" {_checked("compare")} />
          Compare (2)
        </label>
        <label style="margin-left:10px;">
          <input type="radio" name="viewmode" value="grid4" onchange="applyControls()" {_checked("grid4")} />
          Grid (4)
        </label>
      </div>

      <div class="ctrl" id="single-controls" style="display:{'inline-flex' if view == 'single' else 'none'};">
        <span>Scenario</span>
        <select id="scenario-single" onchange="applyControls()">
          {scenario_opts_single}
        </select>
      </div>

      <div class="ctrl" id="compare-controls" style="display:{'inline-flex' if view == 'compare' else 'none'};">
        <span class="mini">A</span>
        <select id="scenario-a" onchange="applyControls()">
          {a_opts}
        </select>

        <span class="mini" style="margin-left:8px;">B</span>
        <select id="scenario-b" onchange="applyControls()">
          {b_opts}
        </select>
      </div>

      <div class="ctrl" id="grid-controls" style="display:{'inline-flex' if view == 'grid4' else 'none'};">
        <span class="mini">TL</span>
        <select id="scenario-g0" onchange="applyControls()">{g0_opts}</select>

        <span class="mini" style="margin-left:8px;">TR</span>
        <select id="scenario-g1" onchange="applyControls()">{g1_opts}</select>

        <span class="mini" style="margin-left:8px;">BL</span>
        <select id="scenario-g2" onchange="applyControls()">{g2_opts}</select>

        <span class="mini" style="margin-left:8px;">BR</span>
        <select id="scenario-g3" onchange="applyControls()">{g3_opts}</select>
      </div>

    </div>
  </div>
</div>

<div id="maps">

  <div id="single-map" style="display:{'block' if view == 'single' else 'none'};">
    <iframe class="map-frame" src="{single_url}"></iframe>
  </div>

  <div id="compare-maps" style="display:{'grid' if view == 'compare' else 'none'};">
    <iframe class="map-frame" src="{map_a_url}"></iframe>
    <iframe class="map-frame" src="{map_b_url}"></iframe>
  </div>

  <div id="grid4-maps" style="display:{'grid' if view == 'grid4' else 'none'};">
    <iframe class="map-frame" src="{grid_urls[0][1]}"></iframe>
    <iframe class="map-frame" src="{grid_urls[1][1]}"></iframe>
    <iframe class="map-frame" src="{grid_urls[2][1]}"></iframe>
    <iframe class="map-frame" src="{grid_urls[3][1]}"></iframe>
  </div>

</div>

<div id="graphs-root" style="display:{'block' if graphs_html else 'none'};">
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
