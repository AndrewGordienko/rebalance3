# rebalance3/trucks/simulator.py
from typing import Dict, List

from rebalance3.trucks.policy import greedy_threshold_policy
from rebalance3.trucks.types import TruckMove


def apply_truck_rebalancing(
    *,
    station_bikes: Dict[str, int],
    station_capacity: Dict[str, int],
    t_min: int,
    moves_available: int,
    empty_thr: float = 0.10,
    full_thr: float = 0.90,
    target_thr: float = 0.50,
    truck_cap: int = 20,
) -> List[TruckMove]:
    """
    Backwards-compatible entry point used by station_state_by_hour.py

    Decide + apply up to `moves_available` truck moves immediately.
    Returns the moves that were applied.

    NOTE:
    - This mutates station_bikes in-place.
    - This is the "online dispatch" policy (greedy threshold).
    """
    return greedy_threshold_policy(
        station_bikes=station_bikes,
        station_capacity=station_capacity,
        t_min=int(t_min),
        moves_available=int(moves_available),
        empty_thr=float(empty_thr),
        full_thr=float(full_thr),
        target_thr=float(target_thr),
        truck_cap=int(truck_cap),
    )
