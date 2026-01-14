# rebalance3/viz/charts/graphs.py
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
    return [
        f"{t//60:02d}:{t%60:02d}" if mode == "t_min" else f"{t:02d}:00"
        for t in valid_times
    ]


def _auc(series):
    # Discrete "area under curve" = sum of counts per time bucket
    return int(sum(int(x) for x in series))


def _peak(series):
    return int(max(series)) if series else 0


def _pct_change(baseline, candidate):
    # negative means improvement (lower is better)
    if baseline <= 0:
        return 0.0
    return 100.0 * (candidate - baseline) / baseline


def _pct_reduction(baseline, candidate):
    # positive means improvement (lower is better)
    if baseline <= 0:
        return 0.0
    return 100.0 * (baseline - candidate) / baseline


def build_single_graphs(state, stations, valid_times, mode, scenario_name: str):
    """
    ✅ Single-scenario graphs:
    - one summary block
    - one set of charts (Empty + Full)
    """
    return build_comparison_graphs(
        states=[state, state],
        stations=stations,
        valid_times=valid_times,
        mode=mode,
        scenario_names=[scenario_name, ""],
    )


def build_comparison_graphs(states, stations, valid_times, mode, scenario_names):
    """
    Compare-mode:
      scenario_names=[A, B]

    Single-mode:
      scenario_names=[A, ""]
      (only renders one set of charts + one summary)
    """
    labels = _labels(valid_times, mode)

    # counts for A and B
    a_empty, a_full = _counts(states[0], stations, valid_times)
    b_empty, b_full = _counts(states[1], stations, valid_times)

    name_a = scenario_names[0] if scenario_names and scenario_names[0] else "Scenario A"
    name_b = ""
    if scenario_names and len(scenario_names) > 1 and scenario_names[1]:
        name_b = scenario_names[1]

    compare_mode = bool(name_b)

    # summary stats
    a_empty_auc = _auc(a_empty)
    a_full_auc = _auc(a_full)
    a_empty_peak = _peak(a_empty)
    a_full_peak = _peak(a_full)

    b_empty_auc = _auc(b_empty)
    b_full_auc = _auc(b_full)
    b_empty_peak = _peak(b_empty)
    b_full_peak = _peak(b_full)

    empty_reduction = _pct_reduction(a_empty_auc, b_empty_auc) if compare_mode else 0.0
    full_reduction = _pct_reduction(a_full_auc, b_full_auc) if compare_mode else 0.0

    empty_delta = _pct_change(a_empty_auc, b_empty_auc) if compare_mode else 0.0
    full_delta = _pct_change(a_full_auc, b_full_auc) if compare_mode else 0.0

    # Build summary HTML
    if compare_mode:
        summary_html = f"""
<div class="rk-summary">
  <div class="rk-summary-title">System stress summary (lower is better)</div>

  <div class="rk-summary-grid">
    <div class="rk-metric">
      <div class="rk-metric-name">Empty-station stress</div>
      <div class="rk-metric-sub">(stations ≤ {int(EMPTY_THRESHOLD*100)}% bikes)</div>

      <div class="rk-row"><span class="rk-k">AUC</span>
        <span class="rk-v">{name_a}: <b>{a_empty_auc}</b> → {name_b}: <b>{b_empty_auc}</b></span>
      </div>
      <div class="rk-row"><span class="rk-k">Reduction</span>
        <span class="rk-v"><b>{empty_reduction:.1f}%</b> (Δ {empty_delta:.1f}%)</span>
      </div>
      <div class="rk-row"><span class="rk-k">Peak</span>
        <span class="rk-v">{a_empty_peak} → {b_empty_peak}</span>
      </div>
    </div>

    <div class="rk-metric">
      <div class="rk-metric-name">Full-station stress</div>
      <div class="rk-metric-sub">(stations ≥ {int(FULL_THRESHOLD*100)}% bikes)</div>

      <div class="rk-row"><span class="rk-k">AUC</span>
        <span class="rk-v">{name_a}: <b>{a_full_auc}</b> → {name_b}: <b>{b_full_auc}</b></span>
      </div>
      <div class="rk-row"><span class="rk-k">Reduction</span>
        <span class="rk-v"><b>{full_reduction:.1f}%</b> (Δ {full_delta:.1f}%)</span>
      </div>
      <div class="rk-row"><span class="rk-k">Peak</span>
        <span class="rk-v">{a_full_peak} → {b_full_peak}</span>
      </div>
    </div>
  </div>

  <div class="rk-footnote">
    <b>AUC</b> = sum of “bad station counts” across all time buckets (so lower means fewer bad moments overall).
  </div>
</div>
"""
        charts_html = f"""
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:24px;">
    <div>
      <b>{name_a} — Empty</b>
      <div class="chart-box"><canvas id="a_empty"></canvas></div>
    </div>
    <div>
      <b>{name_a} — Full</b>
      <div class="chart-box"><canvas id="a_full"></canvas></div>
    </div>
    <div>
      <b>{name_b} — Empty</b>
      <div class="chart-box"><canvas id="b_empty"></canvas></div>
    </div>
    <div>
      <b>{name_b} — Full</b>
      <div class="chart-box"><canvas id="b_full"></canvas></div>
    </div>
  </div>
"""
    else:
        # Single-scenario mode: ONE summary + ONE set of charts
        summary_html = f"""
<div class="rk-summary">
  <div class="rk-summary-title">System stress summary (lower is better)</div>

  <div class="rk-summary-grid" style="grid-template-columns:1fr;">
    <div class="rk-metric">
      <div class="rk-metric-name">{name_a}</div>
      <div class="rk-metric-sub">
        Empty = stations ≤ {int(EMPTY_THRESHOLD*100)}% bikes &nbsp;|&nbsp;
        Full = stations ≥ {int(FULL_THRESHOLD*100)}% bikes
      </div>

      <div class="rk-row"><span class="rk-k">Empty AUC</span><span class="rk-v"><b>{a_empty_auc}</b></span></div>
      <div class="rk-row"><span class="rk-k">Full AUC</span><span class="rk-v"><b>{a_full_auc}</b></span></div>
      <div class="rk-row"><span class="rk-k">Empty peak</span><span class="rk-v">{a_empty_peak}</span></div>
      <div class="rk-row"><span class="rk-k">Full peak</span><span class="rk-v">{a_full_peak}</span></div>
    </div>
  </div>

  <div class="rk-footnote">
    <b>AUC</b> = sum of “bad station counts” across all time buckets.
  </div>
</div>
"""
        charts_html = f"""
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:24px;">
    <div>
      <b>{name_a} — Empty</b>
      <div class="chart-box"><canvas id="a_empty"></canvas></div>
    </div>
    <div>
      <b>{name_a} — Full</b>
      <div class="chart-box"><canvas id="a_full"></canvas></div>
    </div>
  </div>
"""

    return folium.Element(
        f"""
<style>
.chart-box {{
  height: 320px;
  position: relative;
}}
.chart-box canvas {{
  width: 100% !important;
  height: 100% !important;
}}

.rk-summary {{
  max-width: 1600px;
  margin: 32px auto 14px auto;
  padding: 0 24px;
  font-family: sans-serif;
}}

.rk-summary-title {{
  font-size: 16px;
  font-weight: 800;
  margin-bottom: 12px;
}}

.rk-summary-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}}

.rk-metric {{
  background: #f7f7f7;
  border: 1px solid #e5e5e5;
  border-radius: 12px;
  padding: 12px 14px;
}}

.rk-metric-name {{
  font-weight: 800;
  font-size: 14px;
  margin-bottom: 2px;
}}

.rk-metric-sub {{
  font-size: 12px;
  color: #444;
  margin-bottom: 10px;
}}

.rk-row {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
  padding: 2px 0;
}}

.rk-k {{
  color: #333;
  font-weight: 700;
}}

.rk-v {{
  color: #111;
}}

.rk-footnote {{
  margin-top: 10px;
  font-size: 12px;
  color: #333;
}}
</style>

<div style="max-width:1600px; margin:40px auto 120px auto; padding:0 24px;">
  <h2 style="font-family:sans-serif; margin-bottom:12px;">
    System stress comparison
  </h2>
</div>

{summary_html}

<div style="max-width:1600px; margin:14px auto 120px auto; padding:0 24px;">
  {charts_html}
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
(function() {{
  const labels = {labels};

  function draw(id, label, data, color, fill) {{
    const el = document.getElementById(id);
    if (!el) return;
    new Chart(el, {{
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
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{ enabled: true }}
        }},
        scales: {{
          y: {{
            beginAtZero: true,
            title: {{ display: true, text: "Station count (lower is better)" }}
          }},
          x: {{
            title: {{ display: true, text: "{'Time (HH:MM)' if mode == 't_min' else 'Hour'}" }}
          }}
        }}
      }}
    }});
  }}

  // Always draw A charts
  draw("a_empty", "Empty", {a_empty}, "#d73027", "rgba(215,48,39,0.15)");
  draw("a_full",  "Full",  {a_full},  "#4575b4", "rgba(69,117,180,0.15)");

  // Only draw B charts in compare mode
  const compareMode = {str(compare_mode).lower()};
  if (compareMode) {{
    draw("b_empty", "Empty", {b_empty}, "#d73027", "rgba(215,48,39,0.15)");
    draw("b_full",  "Full",  {b_full},  "#4575b4", "rgba(69,117,180,0.15)");
  }}
}})();
</script>
"""
    )
