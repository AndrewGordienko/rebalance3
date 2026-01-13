# rebalance3/main.py
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

# ---- baseline + trucks (global budget: trucks_per_day total moves/day) ----
baseline_trucks = truck_scenario(
    name="Baseline + trucks",
    base_scenario=baseline,
    trips_csv=TRIPS,
    day=DAY,
    trucks_per_day=10,  # <- TOTAL moves/day budget
    out_csv="baseline_trucks_state.csv",
)

moves = baseline_trucks.meta["truck_moves"]

print(f"\nTruck moves for {baseline_trucks.name}:\n")

for i, m in enumerate(moves, 1):
    dist = f"{m.distance_km:.2f}km" if getattr(m, "distance_km", None) is not None else "?"
    tid = getattr(m, "truck_id", None)
    tid_str = f"truck={tid}" if tid is not None else "truck=?"

    print(
        f"{i:02d}. "
        f"t={m.t_min:4d} min | "
        f"{m.from_station} → {m.to_station} "
        f"({m.bikes} bikes) | {tid_str} | dist={dist}"
    )

print("\nFirst few dispatch times (t_min):")
print(sorted(set(m.t_min for m in moves if m.t_min is not None))[:10])

serve_comparison(
    scenarios=[baseline, baseline_trucks],
    port=8080,
    graphs=True,
)
