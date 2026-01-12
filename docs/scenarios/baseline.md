# Baseline scenario

The baseline scenario simulates a full bike-share day **without any intervention**.
No trucks are used, no optimization is applied, and bikes move only according to observed trip data.

This scenario is the reference point against which all interventions (midnight optimization, trucks, etc.) are compared.

---

## Purpose

The baseline answers a simple question:

> *What happens if we do nothing?*

It provides:
- a realistic time-evolving station state
- a control distribution to compare costs, empties, and full stations
- an input for downstream scenarios (e.g. trucks start from the baseline midnight state)

---

## High-level behavior

1. Initialize bikes at midnight using a global fill ratio
2. Replay all trip departures and arrivals during the day
3. Track station bike counts in fixed time buckets
4. Write a station-state time series to CSV
5. Return a `Scenario` object usable by the visualization layer

No rebalancing actions occur.

---

## Initialization

At midnight, each station is initialized independently:

```
initial_bikes[station] = round(capacity * initial_fill_ratio)
```

This ensures:
- bikes never exceed station capacity
- all stations start with the same relative fullness
- total bikes scale naturally with system size

The default fill ratio is typically **0.60**, matching common operational targets.

---

## Time discretization

Time is discretized into fixed buckets of length `bucket_minutes`.

Common choices:
- 60 minutes (hourly)
- 15 minutes (default)
- 5 minutes (high-resolution)

Constraints:
- `bucket_minutes` must evenly divide 1440
- all state snapshots align to bucket boundaries

Internally, time is represented as:
- `t_min` = minutes since midnight
- `hour` = `t_min // 60` (for hourly output)

---

## Trip replay model

Trips are processed as **atomic events**:

- departure → remove 1 bike from start station (if available)
- arrival → add 1 bike to end station (if space available)

Rules:
- trips outside the target day are ignored
- stations not in the registry are ignored
- bike counts are clamped to `[0, capacity]`

Trips are replayed strictly in chronological order.

---

## Output format

The baseline writes a CSV containing one row per station per time bucket.

### Hourly output (`bucket_minutes == 60`)

```
station_id, hour, bikes, empty_docks, capacity
```

### Sub-hour output

```
station_id, t_min, bikes, empty_docks, capacity
```

This file is the **canonical input** for:
- map visualization
- time-series plots
- scenario comparison

---

## API

### `baseline_scenario(...)`

```python
baseline = baseline_scenario(
    trips_csv="Bike share ridership 2024-09.csv",
    day="2024-09-01",
    initial_fill_ratio=0.60,
    bucket_minutes=15,
    out_csv="baseline_state.csv",
)
```

#### Parameters

- `trips_csv`  
  CSV containing trip records

- `day`  
  Simulation day (`YYYY-MM-DD`)

- `initial_fill_ratio`  
  Fraction of capacity filled at midnight

- `bucket_minutes`  
  Time resolution

- `out_csv`  
  Output path for station state

#### Returns

A `Scenario` object with:
- `state_csv`
- `bucket_minutes`
- metadata identifying it as baseline

---

## When to use

Use the baseline when:
- validating data quality
- debugging visualization
- benchmarking interventions
- building comparative graphs

Every other scenario assumes the baseline exists.

---
