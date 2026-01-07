import json
from typing import Dict, List, Tuple


def compute_station_health_timeseries(
    state: Dict[int, Dict[str, int]],
    stations: List[Dict],
    valid_times: List[int],
    *,
    low_bikes_threshold: int = 2,
    full_slack: int = 2,
) -> Tuple[List[int], List[int]]:
    """
    Returns:
      low_counts[t]  = count of stations with bikes <= low_bikes_threshold
      full_counts[t] = count of stations with bikes >= cap - full_slack
    """

    capacity_by_id = {
        str(s.get("station_id")): int(s.get("capacity", 0))
        for s in stations
        if s.get("station_id") is not None
    }

    low_counts: List[int] = []
    full_counts: List[int] = []

    for t in valid_times:
        snapshot = state.get(t, {}) or {}

        low = 0
        full = 0

        for sid, bikes in snapshot.items():
            sid = str(sid)
            cap = capacity_by_id.get(sid, 0)
            if cap <= 0:
                continue

            if bikes <= low_bikes_threshold:
                low += 1
            elif bikes >= (cap - full_slack):
                full += 1

        low_counts.append(low)
        full_counts.append(full)

    return low_counts, full_counts


def _format_time_labels(valid_times: List[int]) -> List[str]:
    labels: List[str] = []
    for t in valid_times:
        hh = int(t // 60)
        mm = int(t % 60)
        labels.append(f"{hh:02d}:{mm:02d}")
    return labels


def build_timeseries_block_html(
    valid_times: List[int],
    low_counts: List[int],
    full_counts: List[int],
) -> str:
    """
    Returns a FULL HTML + JS block to be appended to the page.
    No Folium / MacroElement usage.
    """

    payload = {
        "labels": _format_time_labels(valid_times),
        "low": low_counts,
        "full": full_counts,
    }

    payload_json = json.dumps(payload)

    return f"""
<div class="rk-charts-wrap">
  <div class="rk-charts-row">
    <div class="rk-card rk-chart-card">
      <h3 class="rk-h3">Low-bike stations (≤2 bikes)</h3>
      <div class="rk-canvas-wrap">
        <canvas id="rkLowChart"></canvas>
      </div>
    </div>

    <div class="rk-card rk-chart-card">
      <h3 class="rk-h3">High-fill stations (≥capacity − 2)</h3>
      <div class="rk-canvas-wrap">
        <canvas id="rkFullChart"></canvas>
      </div>
    </div>
  </div>
</div>

<script>
  window.__RB3_TS__ = {payload_json};
</script>

<script>
(function() {{
  function loadChart(cb) {{
    if (window.Chart) {{ cb(); return; }}
    var s = document.createElement("script");
    s.src = "https://cdn.jsdelivr.net/npm/chart.js";
    s.onload = cb;
    document.head.appendChild(s);
  }}

  function render() {{
    var DATA = window.__RB3_TS__;
    if (!DATA) return;

    function makeChart(id, series) {{
      var el = document.getElementById(id);
      if (!el) return;

      new Chart(el, {{
        type: "line",
        data: {{
          labels: DATA.labels,
          datasets: [{{ data: series, borderWidth: 2, tension: 0.25, pointRadius: 0 }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ title: {{ display: true, text: "Time" }} }},
            y: {{ beginAtZero: true, title: {{ display: true, text: "Station count" }} }}
          }}
        }}
      }});
    }}

    makeChart("rkLowChart", DATA.low);
    makeChart("rkFullChart", DATA.full);
  }}

  function onReady(fn) {{
    if (document.readyState === "loading") {{
      document.addEventListener("DOMContentLoaded", fn);
    }} else {{
      fn();
    }}
  }}

  onReady(function() {{
    loadChart(render);
  }});
}})();
</script>
"""
