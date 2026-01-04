# rebalance3/viz/state_loader.py
import csv

def load_station_state(state_csv_path):
    if state_csv_path is None:
        return {}, "none", []

    state = {}
    mode = "hour"
    times = set()

    with open(state_csv_path, newline="") as f:
        reader = csv.DictReader(f)
        cols = reader.fieldnames or []

        if "t_min" in cols:
            mode = "t_min"

        for row in reader:
            sid = str(row["station_id"])
            bikes = int(row["bikes"])
            cap = int(row["capacity"])
            t = int(row["t_min"]) if mode == "t_min" else int(row["hour"])

            state[(sid, t)] = {"bikes": bikes, "capacity": cap}
            times.add(t)

    return state, mode, sorted(times)


def snap_time(requested, valid_times):
    if not valid_times:
        return requested
    return min(valid_times, key=lambda t: abs(t - requested))
