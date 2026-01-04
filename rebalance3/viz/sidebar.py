# rebalance3/viz/sidebar.py
import folium

def build_sidebar():
    hour_links = "".join(
        f'<a href="/?hour={h}" style="margin:2px;text-decoration:none;color:#333;">{h:02d}</a>'
        for h in range(24)
    )

    return folium.Element(f"""
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
    ">
      <div style="font-weight:700;">Toronto Bike Share</div>

      <div style="margin-top:12px;">
        <b>Snapshots (hour)</b><br>
        <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;">
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
