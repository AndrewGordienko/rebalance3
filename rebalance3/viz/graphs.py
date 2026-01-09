# rebalance3/viz/graphs.py
import folium

EMPTY_THRESHOLD = 0.10
FULL_THRESHOLD = 0.90


def build_summary_graphs(state, stations, valid_times, mode):
    labels = []
    empty_counts = []
    full_counts = []

    for t in valid_times:
        empty = 0
        full = 0

        for s in stations:
            sid = str(s["station_id"])
            st = state.get((sid, t))
            if not st or not st["capacity"]:
                continue

            ratio = st["bikes"] / st["capacity"]
            if ratio <= EMPTY_THRESHOLD:
                empty += 1
            elif ratio >= FULL_THRESHOLD:
                full += 1

        empty_counts.append(empty)
        full_counts.append(full)

        labels.append(
            f"{t//60:02d}:{t%60:02d}" if mode == "t_min" else f"{t:02d}:00"
        )

    return folium.Element(f"""
<div id="graphs">
  <h2 style="font-family:sans-serif; margin-bottom:24px;">
    System stress over time
  </h2>

  <div id="graphs-grid">
    <canvas id="emptyChart"></canvas>
    <canvas id="fullChart"></canvas>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const labels = {labels};

new Chart(document.getElementById("emptyChart"), {{
  type: "line",
  data: {{
    labels,
    datasets: [{{
      label: "Empty stations",
      data: {empty_counts},
      borderColor: "#d73027",
      backgroundColor: "rgba(215,48,39,0.15)",
      fill: true,
      tension: 0.25
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    scales: {{
      y: {{ beginAtZero: true }}
    }}
  }}
}});

new Chart(document.getElementById("fullChart"), {{
  type: "line",
  data: {{
    labels,
    datasets: [{{
      label: "Full stations",
      data: {full_counts},
      borderColor: "#4575b4",
      backgroundColor: "rgba(69,117,180,0.15)",
      fill: true,
      tension: 0.25
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    scales: {{
      y: {{ beginAtZero: true }}
    }}
  }}
}});
</script>
""")
