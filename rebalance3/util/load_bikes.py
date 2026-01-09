import csv
from pathlib import Path
from typing import Dict


def load_initial_bikes_from_csv(state_csv: str | Path) -> Dict[str, int]:
    """
    Extract midnight (t_min == 0 or hour == 0) bike counts from a station_state CSV.
    """
    bikes: Dict[str, int] = {}

    with open(state_csv, newline="") as f:
        reader = csv.DictReader(f)

        if "t_min" in reader.fieldnames:
            time_key = "t_min"
            zero = "0"
        elif "hour" in reader.fieldnames:
            time_key = "hour"
            zero = "0"
        else:
            raise ValueError("CSV must contain t_min or hour column")

        for row in reader:
            if row[time_key] != zero:
                continue

            sid = str(row["station_id"])
            bikes[sid] = int(row["bikes"])

    if not bikes:
        raise ValueError("No midnight snapshot found in state CSV")

    return bikes
