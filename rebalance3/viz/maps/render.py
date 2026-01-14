# rebalance3/viz/maps/render.py
import folium

from rebalance3.viz.overlays.stations import add_station_markers
from rebalance3.viz.overlays.trucks import add_truck_moves
from rebalance3.viz.widgets.legend import build_legend_widget
from rebalance3.viz.widgets.time_bar import build_time_bar  # your existing file moved later if you want

CENTER_LAT = 43.6532
CENTER_LON = -79.3832


def render_map_document(
    *,
    stations,
    state,
    mode,
    valid_times,
    t_cur,
    title: str | None = None,
    truck_moves=None,
    bucket_minutes: int = 15,
):
    """
    Single place that assembles the full Folium map HTML document.
    """

    m = folium.Map(
        location=[CENTER_LAT, CENTER_LON],
        zoom_start=12,
        tiles="cartodbpositron",
        prefer_canvas=False,
    )

    # stations
    add_station_markers(m, stations, state, t_cur, mode)

    # trucks (overlay)
    if truck_moves:
        add_truck_moves(
            m,
            stations,
            truck_moves,
            mode=mode,
            t_cur=t_cur,
            bucket_minutes=bucket_minutes,
            show_bucket_window=True,   # key: makes 435 show moves at 420 etc
        )

    # timebar (widget)
    if valid_times:
        m.get_root().html.add_child(
            build_time_bar(
                state,
                stations,
                valid_times,
                t_cur,
                mode,
                truck_moves=truck_moves,
            )
        )

    # legend (widget)
    m.get_root().html.add_child(build_legend_widget(include_trucks=bool(truck_moves)))

    # title + wrap so widgets sit on-map
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
}}
</style>

<script>
document.addEventListener("DOMContentLoaded", () => {{
  const mapEl = document.querySelector(".leaflet-container");
  if (!mapEl) return;

  // Wrap map
  let wrap = document.getElementById("map-wrap");
  if (!wrap) {{
    wrap = document.createElement("div");
    wrap.id = "map-wrap";
    mapEl.parentNode.insertBefore(wrap, mapEl);
    wrap.appendChild(mapEl);
  }}

  // Title
  const existingTitle = document.getElementById("map-title");
  if (existingTitle) existingTitle.remove();

  {"const t=document.createElement('div');t.id='map-title';t.textContent=%r;wrap.appendChild(t);" % title if title else ""}

  // Put timebar inside map overlay
  const timebar = document.getElementById("timebar");
  if (timebar) wrap.appendChild(timebar);
}});
</script>
"""
        )
    )

    return m.get_root().render()
