# rebalance3/main.py

from rebalance3.scenarios.baseline import baseline_scenario
from rebalance3.scenarios.midnight import midnight_scenario
from rebalance3.scenarios.trucks import truck_scenario
from rebalance3.scenarios.trucks_clustered import truck_clustered_scenario

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

    # ---- midnight optimizer (baseline objective) ----
    midnight = midnight_scenario(
        TRIPS,
        DAY,  # visualization_day
        bucket_minutes=baseline.bucket_minutes,
        total_bikes_ratio=0.60,
        out_csv="midnight_state.csv",
    )

    # ---- trucks (OLD) built on top of midnight ----
    trucks = truck_scenario(
        name="Truck Rebalancing (old)",
        base_scenario=midnight,
        trips_csv=TRIPS,
        day=DAY,
        out_csv="truck_state.csv",
        n_trucks=10,
        moves_per_truck_total=5,  # total cap = 50
        service_start_hour=8,
        service_end_hour=20,
    )

    # ---- trucks (NEW) cluster-aware day planner ----
    # NOTE: no clusters_csv param here because your current day_planner.py
    # does not take clusters yet.
    trucks_clustered = truck_clustered_scenario(
        name="Truck Rebalancing (clustered)",
        trips_csv=TRIPS,
        day=DAY,
        bucket_minutes=baseline.bucket_minutes,
        total_bikes_ratio=0.60,
        moves_budget=50,
        truck_cap=20,
        service_start_hour=8,
        service_end_hour=20,
        out_csv="truck_clustered_state.csv",
    )

    # ---- print clustered moves ----
    moves = trucks_clustered.meta.get("truck_moves", [])

    print(f"\nTruck moves for {trucks_clustered.name}:\n")
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
        scenarios=[baseline, midnight, trucks, trucks_clustered],
        port=8080,
        graphs=True,
        title="Bike Share Rebalancing Viewer",
        layout="grid4",  # ✅ start in 4-map + 8-graph dashboard mode
    )


if __name__ == "__main__":
    main()
