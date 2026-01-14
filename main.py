# rebalance3/main.py
from rebalance3.scenarios.baseline import baseline_scenario
from rebalance3.scenarios.midnight import midnight_scenario
from rebalance3.scenarios.trucks import truck_scenario

from rebalance3.viz.app.comparison import serve_comparison


TRIPS = "Bike share ridership 2024-09.csv"
DAY = "2024-09-01"


def main():
    # ---- baseline ----
    baseline = baseline_scenario(
        TRIPS,
        DAY,
        initial_fill_ratio=0.60,
        out_csv="baseline_state.csv",
    )

    # ---- midnight optimizer ----
    midnight = midnight_scenario(
        TRIPS,
        DAY,  # visualization_day
        bucket_minutes=baseline.bucket_minutes,
        total_bikes_ratio=0.60,
        out_csv="midnight_state.csv",
    )

    # ---- trucks (10 total moves/day) ----
    trucks = truck_scenario(
        name="Truck Rebalancing",
        base_scenario=midnight,
        trips_csv=TRIPS,
        day=DAY,
        out_csv="truck_state.csv",
        n_trucks=10,
        moves_per_truck_total=5,  # ✅ total cap = 50
        service_start_hour=8,
        service_end_hour=20,
    )

    # ---- print moves ----
    moves = trucks.meta.get("truck_moves", [])

    print(f"\nTruck moves for {trucks.name}:\n")
    for i, m in enumerate(moves, 1):
        print(
            f"{i:02d}. "
            f"t={m.t_min:4d} min | "
            f"{m.from_station} → {m.to_station} "
            f"({m.bikes} bikes)"
        )

    print("\nMove times (t_min):")
    print(sorted(set(m.t_min for m in moves if m.t_min is not None)))

    # ---- UI ----
    serve_comparison(
        scenarios=[baseline, midnight, trucks],
        port=8080,
        graphs=True,
        title="Bike Share Rebalancing Viewer",
    )


if __name__ == "__main__":
    main()
