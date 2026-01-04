# rebalance3/viz/stations_map.py
import folium
from flask import Flask, request
from pathlib import Path
from rebalance3.util.stations import load_stations

from .state_loader import load_station_state, snap_time
from .map_layer import add_station_markers
from .sidebar import build_sidebar
from .time_bar import build_time_bar

CENTER_LAT = 43.6532
CENTER_LON = -79.3832

_LIB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TORONTO_STATIONS_FILE = _LIB_ROOT / "station_information.json"


def serve_stations_map(
    host="127.0.0.1",
    port=8080,
    debug=False,
    stations_file=DEFAULT_TORONTO_STATIONS_FILE,
    state_by_hour_csv=None,
):
    stations = load_stations(stations_file)
    state, mode, valid_times = load_station_state(state_by_hour_csv)

    app = Flask(__name__)

    @app.route("/")
    def _view():
        t_req = (
            request.args.get("t", valid_times[0], type=int)
            if mode == "t_min"
            else request.args.get("hour", valid_times[0], type=int)
        )
        t_cur = snap_time(t_req, valid_times)

        m = folium.Map(
            location=[CENTER_LAT, CENTER_LON],
            zoom_start=12,
            tiles="cartodbpositron",
            prefer_canvas=True,
        )

        add_station_markers(m, stations, state, t_cur, mode)
        m.get_root().html.add_child(build_sidebar())

        if valid_times:
            m.get_root().html.add_child(
                build_time_bar(state, stations, valid_times, t_cur, mode)
            )

        return m.get_root().render()

    app.run(host=host, port=port, debug=debug)
