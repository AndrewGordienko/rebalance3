from rebalance3.scenarios.baseline import baseline_scenario
from rebalance3.scenarios.midnight import midnight_scenario
from rebalance3.viz.comparison import serve_comparison

TRIPS = "Bike share ridership 2024-09.csv"
DAY = "2024-09-01"

baseline = baseline_scenario(
    TRIPS,
    DAY,
    initial_fill_ratio=0.60,
    out_csv="baseline_state.csv",
)

midnight = midnight_scenario(
    TRIPS,
    DAY,
    days=[
        "2024-09-01",
        "2024-09-02",
    ],
    bucket_minutes=15,
    total_bikes_ratio=0.60,
    out_csv="midnight_week_state.csv",
)


serve_comparison(
    scenarios=[baseline, midnight],
    port=8080,
    graphs=True,
)
