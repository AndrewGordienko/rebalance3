# rebalance3/viz/single.py
from __future__ import annotations

from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from rebalance3.viz.data.state_loader import load_station_state
from rebalance3.viz.data.time_snap import snap_time
from rebalance3.viz.maps.render import render_map_document

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def serve_single(
    *,
    scenario,
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
    stations_file: str | Path = DEFAULT_TORONTO_STATIONS_FILE,
    title: str | None = None,
):
    """
    Serve a single scenario map page.

    scenario expected:
      - .name
      - .state_csv
      - .bucket_minutes (optional)
      - .meta["truck_moves"] (optional)
    """
    if scenario is None:
        raise ValueError("serve_single requires a Scenario")

    stations = load_stations(stations_file)
    state, mode, valid_times = load_station_state(scenario.state_csv)

    bucket_minutes = getattr(scenario, "bucket_minutes", 15) or 15
    truck_moves = (scenario.meta or {}).get("truck_moves")

    app = Flask(__name__)

    @app.route("/")
    def _index():
        key = "t" if mode == "t_min" else "hour"
        t_req = request.args.get(key, valid_times[0] if valid_times else 0, type=int)
        t_cur = snap_time(t_req, valid_times)

        return render_map_document(
            stations=stations,
            state=state,
            mode=mode,
            valid_times=valid_times,
            t_cur=t_cur,
            title=title or scenario.name,
            truck_moves=truck_moves,
            bucket_minutes=bucket_minutes,
        )

    app.run(host=host, port=int(port), debug=bool(debug))
