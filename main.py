from rebalance3.scenarios.baseline import baseline_scenario
from rebalance3.scenarios.trucks import truck_scenario
from rebalance3.viz.comparison import serve_comparison

TRIPS = "Bike share ridership 2024-09.csv"
DAY = "2024-09-01"

# ---- baseline (no intervention) ----
baseline = baseline_scenario(
    TRIPS,
    DAY,
    initial_fill_ratio=0.60,
    out_csv="baseline_state.csv",
)


# ---- baseline + trucks ----
baseline_trucks = truck_scenario(
    name="Baseline + trucks",
    base_scenario=baseline,
    trips_csv=TRIPS,
    day=DAY,
    trucks_per_day=10,          # ← this is the control knob
    out_csv="baseline_trucks_state.csv",
)

moves = baseline_trucks.meta["truck_moves"]

print(f"\nTruck moves for {baseline_trucks.name}:\n")

for i, m in enumerate(moves, 1):
    print(
        f"{i:02d}. "
        f"t={m.t_min:4d} min | "
        f"{m.from_station} → {m.to_station} "
        f"({m.bikes} bikes)"
    )

print(sorted(set(m.t_min for m in baseline_trucks.meta["truck_moves"]))[:10])

serve_comparison(
    scenarios=[baseline, baseline_trucks],
    port=8080,
    graphs=True,
)
