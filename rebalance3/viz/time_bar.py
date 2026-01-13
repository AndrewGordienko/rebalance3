# rebalance3/viz/time_bar.py
import folium

FULL_THRESHOLD = 0.9


def build_time_bar(state, stations, valid_times, t_current, mode, *, truck_moves=None):
    """
    Time bar:
      - bars = number of "full" stations at each time bucket
      - ticks = truck move times (vertical markers on top of bars)

    IMPORTANT FIX:
      - Clicking a bar now works in BOTH:
          * iframe compare mode (postMessage)
          * single-map mode (updates window.location + reload)
    """

    # ----------------------------
    # Full-station bars
    # ----------------------------
    full_counts = {}

    for t in valid_times:
        cnt = 0
        for s in stations:
            sid = str(s["station_id"])
            st = state.get((sid, t))
            if not st:
                continue
            cap = st.get("capacity", 0)
            if cap > 0 and st["bikes"] / cap >= FULL_THRESHOLD:
                cnt += 1
        full_counts[t] = cnt

    max_count = max(full_counts.values(), default=0)

    bars = []
    for t in valid_times:
        if max_count > 0:
            height = int((full_counts[t] / max_count) * 72)
        else:
            height = 0

        label = (
            f"{t // 60:02d}:{t % 60:02d}"
            if mode == "t_min"
            else f"{t:02d}:00"
        )

        bars.append(
            f"""
            <div class="timebar-item"
                 onclick="setTime({t})"
                 data-label="{label}"
                 data-tmin="{t}">
              <div class="timebar-bar"
                   style="height:{height}px; opacity:{'1.0' if t == t_current else '0.55'};">
              </div>
            </div>
            """
        )

    # ----------------------------
    # Truck move ticks
    # ----------------------------
    move_counts = {}
    if truck_moves:
        for m in truck_moves:
            if getattr(m, "t_min", None) is None:
                continue
            tm = int(m.t_min)
            move_counts[tm] = move_counts.get(tm, 0) + 1

    move_ticks_html = []
    for t in valid_times:
        c = move_counts.get(int(t), 0)
        if c <= 0:
            continue

        tick_w = min(2 + 2 * (c - 1), 6)
        op = 0.70 if c == 1 else (0.85 if c == 2 else 0.95)

        move_ticks_html.append(
            f"""
            <div class="move-tick"
                 title="{c} truck move{'s' if c != 1 else ''}"
                 data-tmin="{t}"
                 style="width:{tick_w}px; opacity:{op};">
            </div>
            """
        )

    key = "t" if mode == "t_min" else "hour"

    return folium.Element(
        f"""
<style>
#timebar {{
  position: absolute;
  left: 0;
  right: 0;
  bottom: 14px;
  height: 110px;
  z-index: 1200;
  pointer-events: auto;
  background: linear-gradient(
    to top,
    rgba(255,255,255,0.92),
    rgba(255,255,255,0.55),
    rgba(255,255,255,0)
  );
}}

#timebar-scroll {{
  position: absolute;
  bottom: 14px;
  left: 0;
  right: 0;
  padding: 0 16px;
  overflow-x: auto;
  white-space: nowrap;
  cursor: grab;
}}

.timebar-item {{
  display: inline-flex;
  align-items: flex-end;
  width: 10px;
  height: 84px;
  margin-right: 6px;
  cursor: pointer;
  position: relative;
}}

.timebar-bar {{
  width: 100%;
  background: #d73027;
  border-radius: 2px;
}}

#timebar-label {{
  position: absolute;
  bottom: 92px;
  transform: translateX(-50%);
  background: rgba(120,200,200,0.85);
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  display: none;
}}

#move-ticks-layer {{
  position: absolute;
  left: 16px;
  right: 16px;
  bottom: 14px;
  height: 84px;
  pointer-events: none;
  z-index: 1250;
}}

.move-tick {{
  position: absolute;
  bottom: 0px;
  height: 84px;
  background: #111111;
  border-radius: 2px;
}}
</style>

<div id="timebar">
  <div id="timebar-label"></div>

  <div id="timebar-scroll"
       onmousemove="timebarMove(event)"
       onmouseleave="timebarHide()">
    {''.join(bars)}
  </div>

  <div id="move-ticks-layer">
    {''.join(move_ticks_html)}
  </div>
</div>

<script>
// ---------------------------------------------------------
// FIX: clicking timebar works in iframe OR single-map mode
// ---------------------------------------------------------
function setTime(t) {{
  try {{
    if (window.parent && window.parent !== window) {{
      // compare mode (iframe)
      window.parent.postMessage({{ type: "set-time", value: t }}, "*");
      return;
    }}
  }} catch (e) {{}}

  // single-map mode (no iframe) => reload this page with updated query param
  const url = new URL(window.location.href);
  url.searchParams.set("{key}", String(t));
  window.location.href = url.toString();
}}

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

function layoutMoveTicks() {{
  const scroll = document.getElementById("timebar-scroll");
  const layer = document.getElementById("move-ticks-layer");
  if (!scroll || !layer) return;

  const items = scroll.querySelectorAll(".timebar-item");
  const itemByT = {{}};

  items.forEach((it) => {{
    const t = it.dataset.tmin;
    if (t !== undefined) itemByT[t] = it;
  }});

  layer.querySelectorAll(".move-tick").forEach((tick) => {{
    const t = tick.dataset.tmin;
    const it = itemByT[t];
    if (!it) return;

    const r1 = scroll.getBoundingClientRect();
    const r2 = it.getBoundingClientRect();

    const centerX = (r2.left - r1.left) + (r2.width / 2);
    tick.style.left = (centerX - (tick.offsetWidth / 2)) + "px";
  }});
}}

document.addEventListener("DOMContentLoaded", () => {{
  layoutMoveTicks();

  const scroll = document.getElementById("timebar-scroll");
  if (scroll) {{
    scroll.addEventListener("scroll", () => {{
      layoutMoveTicks();
    }});
  }}

  window.addEventListener("resize", () => {{
    layoutMoveTicks();
  }});
}});
</script>
"""
    )
