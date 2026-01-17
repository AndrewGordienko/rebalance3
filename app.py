import os

from rebalance3.viz.app.comparison import serve_comparison

from rebalance3.scenarios.baseline import baseline_scenario
from rebalance3.scenarios.midnight import midnight_scenario
from rebalance3.scenarios.trucks import truck_scenario
from rebalance3.scenarios.trucks_clustered import truck_clustered_scenario

TRIPS = os.environ.get("TRIPS_CSV", "Bike share ridership 2024-09.csv")
DAY = os.environ.get("DAY", "2024-09-01")


def build_scenarios():
  baseline = baseline_scenario(
      TRIPS,
      DAY,
      initial_fill_ratio=0.60,
      out_csv="baseline_state.csv",
  )

  midnight = midnight_scenario(
      TRIPS,
      DAY,
      bucket_minutes=baseline.bucket_minutes,
      total_bikes_ratio=0.60,
      out_csv="midnight_state.csv",
  )

  trucks = truck_scenario(
      name="Truck Rebalancing (old)",
      base_scenario=midnight,
      trips_csv=TRIPS,
      day=DAY,
      out_csv="truck_state.csv",
      n_trucks=10,
      moves_per_truck_total=5,
      service_start_hour=8,
      service_end_hour=20,
  )

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

  return [baseline, midnight, trucks, trucks_clustered]


def main():
  scenarios = build_scenarios()

  port = int(os.environ.get("PORT", "8080"))

  serve_comparison(
      scenarios=scenarios,
      port=port,
      graphs=True,
      title="Bike Share Rebalancing Viewer",
      layout="grid4",
      host="0.0.0.0",  # IMPORTANT for Render
  )


if __name__ == "__main__":
  main()
