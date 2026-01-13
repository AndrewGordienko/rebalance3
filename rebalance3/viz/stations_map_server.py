# rebalance3/viz/stations_map_server.py
from __future__ import annotations

from flask import Flask, request
from pathlib import Path

from rebalance3.util.stations import load_stations
from rebalance3.viz.state_loader import load_station_state, snap_time
from rebalance3.viz.stations_map import _build_map_document


_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def serve_stations_map(
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
    stations_file: Path = DEFAULT_TORONTO_STATIONS_FILE,
    state_by_hour_csv: str | Path | None = None,
    truck_moves=None,
    title: str | None = None,
):
    if state_by_hour_csv is None:
        raise ValueError("state_by_hour_csv is required")

    stations = load_stations(stations_file)
    state, mode, valid_times = load_station_state(state_by_hour_csv)

    app = Flask(__name__)

    @app.route("/")
    def index():
        t_raw = request.args.get("t", None)

        if t_raw is None:
            t_cur = valid_times[0] if valid_times else 0
        else:
            try:
                t_cur = int(float(t_raw))
            except Exception:
                t_cur = valid_times[0] if valid_times else 0

        t_cur = snap_time(t_cur, valid_times)

        html = _build_map_document(
            stations=stations,
            state=state,
            mode=mode,
            valid_times=valid_times,
            t_cur=t_cur,
            title=title,
            truck_moves=truck_moves,
        )
        return html

    app.run(host=host, port=int(port), debug=debug)
