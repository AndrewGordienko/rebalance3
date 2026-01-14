# rebalance3/viz/sidebar.py
import folium

def build_sidebar(mode: str, t_current: int | None = None):
    links = []

    for h in range(24):
        if mode == "t_min":
            t_val = h * 60
            href = f"/?t={t_val}"
            active = t_current == t_val
        else:
            href = f"/?hour={h}"
            active = t_current == h

        links.append(f"""
        <a href="{href}"
           class="snapshot-hour {'active' if active else ''}">
           {h:02d}
        </a>
        """)

    hour_links = "".join(links)

    return folium.Element(f"""
<style>
.snapshot-hour {{
  display:inline-block;
  padding:6px 8px;
  border-radius:6px;
  font-size:12px;
  text-decoration:none;
  color:#333;
  background:#f2f2f2;
}}

.snapshot-hour:hover {{
  background:#e0e0e0;
}}

.snapshot-hour.active {{
  background:#0b4f8a;
  color:white;
  font-weight:700;
}}
</style>

<div style="
    position:fixed;
    top:15px;
    left:15px;
    z-index:1100;
    background:white;
    padding:14px;
    border-radius:8px;
    box-shadow:0 1px 4px rgba(0,0,0,0.25);
    font-family:sans-serif;
    font-size:12px;
    width:260px;
    max-width:calc(100vw - 30px);
">
  <div style="font-weight:700;">Toronto Bike Share</div>

  <div style="margin-top:12px;">
    <b>Snapshots (hour)</b><br>
    <div style="
        display:flex;
        flex-wrap:wrap;
        gap:6px;
        margin-top:6px;
    ">
      {hour_links}
    </div>
  </div>

  <div style="margin-top:12px;">
    <b>Legend</b><br>
    <div><span style="color:#d73027;">●</span> empty</div>
    <div><span style="color:#4575b4;">●</span> full</div>
    <div><span style="color:#666666;">●</span> ok</div>
  </div>
</div>
""")