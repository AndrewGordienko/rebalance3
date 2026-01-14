# rebalance3/viz/widgets/legend.py
import folium


def build_legend_widget(*, include_trucks: bool = True):
    """
    Returns a Folium Element that injects a floating legend.
    """
    trucks_block = ""
    if include_trucks:
        trucks_block = """
          <hr>
          <div><span style="color:#d73027">◯</span> pickup</div>
          <div><span style="color:#1a9850">◯</span> dropoff</div>
          <div>— truck move</div>
        """

    return folium.Element(
        f"""
<style>
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
</style>

<script>
document.addEventListener("DOMContentLoaded", () => {{
  const mapEl = document.querySelector(".leaflet-container");
  if (!mapEl) return;

  // Ensure we have a wrapper (stations_map handles this too, but safe here)
  let wrap = document.getElementById("map-wrap");
  if (!wrap) {{
    wrap = document.createElement("div");
    wrap.id = "map-wrap";
    wrap.style.position = "relative";
    wrap.style.width = "100%";
    mapEl.parentNode.insertBefore(wrap, mapEl);
    wrap.appendChild(mapEl);
  }}

  // Avoid duplicates on reload
  const existing = document.getElementById("map-legend");
  if (existing) existing.remove();

  const legend = document.createElement("div");
  legend.id = "map-legend";
  legend.innerHTML = `
    <div><span style="color:#d73027">●</span> empty</div>
    <div><span style="color:#4575b4">●</span> full</div>
    <div><span style="color:#666">●</span> ok</div>
    {trucks_block}
  `;
  wrap.appendChild(legend);
}});
</script>
"""
    )