import folium

FULL_THRESHOLD = 0.9


def build_time_bar(state, stations, valid_times, t_current, mode):
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

    # ---- SAFE NORMALIZATION ----
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
                 onclick="parent.postMessage({{ type: 'set-time', value: {t} }}, '*')"
                 data-label="{label}">
              <div class="timebar-bar"
                   style="height:{height}px; opacity:{'1.0' if t == t_current else '0.55'};">
              </div>
            </div>
            """
        )

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
"""
    )
