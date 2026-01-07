# rebalance3/viz/time_bar.py
import folium

FULL_THRESHOLD = 0.9


def build_time_bar(state, stations, valid_times, t_current, mode):
    # ---- count full stations per time ----
    full_counts = {}
    for t in valid_times:
        cnt = 0
        for s in stations:
            sid = str(s["station_id"])
            st = state.get((sid, t))
            if st and st["capacity"]:
                if st["bikes"] / st["capacity"] >= FULL_THRESHOLD:
                    cnt += 1
        full_counts[t] = cnt

    max_count = max(full_counts.values()) if full_counts else 1

    bars = []
    for t in valid_times:
        height = int((full_counts[t] / max_count) * 72)

        label = (
            f"{t//60:02d}:{t%60:02d}"
            if mode == "t_min"
            else f"{t:02d}:00"
        )
        href = f"/?t={t}" if mode == "t_min" else f"/?hour={t}"

        bars.append(f"""
        <a href="{href}"
           class="timebar-item"
           data-label="{label}">
          <div class="timebar-bar"
               style="
                 height:{height}px;
                 opacity:{'1.0' if t==t_current else '0.55'};
               ">
          </div>
        </a>
        """)

    return folium.Element(f"""
<style>
/* --- container --- */
#timebar {{
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 120px;
  z-index: 1200;
  pointer-events: auto;
  background: linear-gradient(
    to top,
    rgba(255,255,255,0.92),
    rgba(255,255,255,0.65),
    rgba(255,255,255,0.0)
  );
}}

/* --- scroll area --- */
#timebar-scroll {{
  position: absolute;
  bottom: 18px;
  left: 0;
  right: 0;
  padding: 0 16px;
  overflow-x: auto;
  overflow-y: hidden;
  white-space: nowrap;
  scrollbar-width: thin;
  -webkit-overflow-scrolling: touch;
  cursor: grab;
}}

#timebar-scroll:active {{
  cursor: grabbing;
}}

/* --- bar items --- */
.timebar-item {{
  display: inline-flex;
  align-items: flex-end;
  width: 10px;              /* thinner */
  height: 84px;
  margin-right: 6px;        /* spacing controls density */
  text-decoration: none;
  flex-shrink: 0;
}}

.timebar-bar {{
  width: 100%;
  background: #d73027;
  border-radius: 2px;
}}

/* --- floating label --- */
#timebar-label {{
  position: absolute;
  bottom: 96px;
  left: 0;
  transform: translateX(-50%);
  background: rgba(120, 200, 200, 0.85);
  color: #083b3b;
  padding: 4px 10px;
  border-radius: 999px;
  font-family: sans-serif;
  font-size: 12px;
  font-weight: 600;
  pointer-events: none;
  white-space: nowrap;
  display: none;
}}
</style>

<div id="timebar">
  <div id="timebar-label"></div>

  <div id="timebar-scroll"
       onmousemove="timebarMove(event)"
       onmouseleave="timebarHide()">
    {''.join(bars)}
  </div>
</div>

<script>
function timebarMove(evt) {{
  const label = document.getElementById("timebar-label");
  const item = evt.target.closest(".timebar-item");
  if (!item) {{
    label.style.display = "none";
    return;
  }}

  const rect = item.getBoundingClientRect();
  label.textContent = item.dataset.label;
  label.style.left = (rect.left + rect.width / 2) + "px";
  label.style.display = "block";
}}

function timebarHide() {{
  document.getElementById("timebar-label").style.display = "none";
}}
</script>
""")