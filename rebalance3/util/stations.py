import json

def load_stations(path):
    """
    Load Bike Share stations from station_information.json
    Returns a list of dicts with only the fields we care about.
    """
    with open(path) as f:
        raw = json.load(f)["data"]["stations"]

    stations = []
    for s in raw:
        stations.append({
            "station_id": str(s["station_id"]),
            "name": s["name"],
            "lat": s["lat"],
            "lon": s["lon"],
            "capacity": int(s["capacity"]),
        })

    return stations
