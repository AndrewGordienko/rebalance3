import folium

EMPTY_THRESHOLD = 0.10
FULL_THRESHOLD = 0.90


def _counts(state, stations, valid_times):
    empty, full = [], []
    for t in valid_times:
        e = f = 0
        for s in stations:
            sid = str(s["station_id"])
            st = state.get((sid, t))
            if not st or not st.get("capacity"):
                continue
            r = st["bikes"] / st["capacity"]
            if r <= EMPTY_THRESHOLD:
                e += 1
            elif r >= FULL_THRESHOLD:
                f += 1
        empty.append(e)
        full.append(f)
    return empty, full


def _labels(valid_times, mode):
    return [f"{t//60:02d}:{t%60:02d}" if mode == "t_min" else f"{t:02d}:00"
            for t in valid_times]


def build_comparison_graphs(states, stations, valid_times, mode, scenario_names):
    labels = _labels(valid_times, mode)

    a_empty, a_full = _counts(states[0], stations, valid_times)
    b_empty, b_full = _counts(states[1], stations, valid_times)

    return folium.Element(f"""
<style>
.chart-box {{
  height: 320px;
  position: relative;
}}
.chart-box canvas {{
  width: 100% !important;
  height: 100% !important;
}}
</style>

<div style="max-width:1600px; margin:40px auto 120px auto; padding:0 24px;">
  <h2 style="font-family:sans-serif; margin-bottom:24px;">
    System stress comparison
  </h2>

  <div style="display:grid; grid-template-columns:1fr 1fr; gap:24px;">
    <div><b>{scenario_names[0]} — Empty</b><div class="chart-box"><canvas id="a_empty"></canvas></div></div>
    <div><b>{scenario_names[0]} — Full</b><div class="chart-box"><canvas id="a_full"></canvas></div></div>
    <div><b>{scenario_names[1]} — Empty</b><div class="chart-box"><canvas id="b_empty"></canvas></div></div>
    <div><b>{scenario_names[1]} — Full</b><div class="chart-box"><canvas id="b_full"></canvas></div></div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
(function() {{
  const labels = {labels};

  function draw(id, label, data, color, fill) {{
    new Chart(document.getElementById(id), {{
      type: "line",
      data: {{
        labels,
        datasets: [{{
          label,
          data,
          borderColor: color,
          backgroundColor: fill,
          fill: true,
          tension: 0.25,
          pointRadius: 0
        }}]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        scales: {{ y: {{ beginAtZero: true }} }}
      }}
    }});
  }}

  draw("a_empty", "Empty", {a_empty}, "#d73027", "rgba(215,48,39,0.15)");
  draw("a_full",  "Full",  {a_full},  "#4575b4", "rgba(69,117,180,0.15)");
  draw("b_empty", "Empty", {b_empty}, "#d73027", "rgba(215,48,39,0.15)");
  draw("b_full",  "Full",  {b_full},  "#4575b4", "rgba(69,117,180,0.15)");
}})();
</script>
""")
