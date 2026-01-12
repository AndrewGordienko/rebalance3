# Midnight optimization

The midnight scenario computes an **optimized initial bike distribution** before the day begins.

Instead of starting from a uniform fill ratio, bikes are redistributed at midnight to reduce expected empties and full stations throughout the day.

This is a *planning-time* optimization — no trucks move during the day.

---

## Core idea

Trips induce predictable net flows at each station over the day.

If a station is expected to:
- lose bikes → start with more
- gain bikes → start with fewer

Then the system can reduce operational pain *without any daytime intervention*.

Midnight optimization formalizes this intuition.

---

## Optimization model

Each station has:
- capacity `C`
- initial bikes `x₀`
- a per-bucket net flow series `Δ(t)`

Bike count over time:
```
x(t) = clamp(x₀ + ΣΔ(t), 0, C)
```

The optimizer chooses `x₀` to minimize total penalty over the day.

---

## Cost function

Two soft thresholds define undesirable states:

- **empty threshold**: `empty_thr * capacity`
- **full threshold**: `full_thr * capacity`

Penalties accumulate when:
- bikes fall below the empty threshold
- bikes rise above the full threshold

Weighted cost:
```
cost = w_empty * empty_depth + w_full * full_depth
```

This produces smooth gradients and avoids hard constraints.

---

## Greedy optimizer

The solver uses a **1-bike greedy swap algorithm**:

1. Start from a proportional capacity allocation
2. For each station, compute marginal gain of:
   - adding one bike
   - removing one bike
3. Move a bike from the best donor to the best receiver
4. Update only affected stations
5. Repeat until no improvement remains

Key properties:
- fast (linear per move)
- deterministic
- respects capacity constraints
- preserves total bike count

---

## Multi-day optimization

The optimizer can operate on:
- a single day
- multiple days averaged together

For multi-day mode:
- per-station deltas are averaged bucket-wise
- optimization minimizes *mean daily cost*
- resulting distribution is more robust to day-to-day noise

---

## From optimization to simulation

Once the optimal midnight bikes are found:

1. Bikes are fixed at midnight
2. The **baseline simulator** is run normally
3. No trucks are dispatched
4. The only difference is the starting state

This makes midnight scenarios fully compatible with:
- maps
- graphs
- scenario comparison

---

## Output metrics

The optimizer reports:

- `initial_cost`
- `final_cost`
- number of greedy moves
- chosen thresholds and weights

These are stored in `Scenario.meta` for later inspection.

---

## API

### `midnight_scenario(...)`

```python
midnight = midnight_scenario(
    trips_csv="Bike share ridership 2024-09.csv",
    visualization_day="2024-09-01",
    days=["2024-08-25", "2024-08-26", "2024-08-27"],
    bucket_minutes=15,
    total_bikes_ratio=0.60,
)
```

#### Parameters

- `trips_csv`  
  Trip data source

- `visualization_day`  
  Day used for simulation and visualization

- `days` (optional)  
  List of days used for optimization

- `bucket_minutes`  
  Time resolution

- `total_bikes_ratio`  
  Fraction of total capacity available system-wide

---

## When to use

Use midnight optimization when:
- trucks are expensive or limited
- demand patterns are stable
- you want a low-effort improvement
- planning decisions happen once per day

It pairs naturally with truck scenarios, which then handle residual imbalance.

---
