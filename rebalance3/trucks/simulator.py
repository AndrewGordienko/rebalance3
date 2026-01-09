# rebalance3/trucks/simulator.py
from typing import Dict, List
from .policy import greedy_threshold_policy
from .types import TruckMove

def apply_truck_rebalancing(
    station_bikes: Dict[str, int],
    station_capacity: Dict[str, int],
    *,
    trucks_per_day: int,
    **policy_kwargs,
) -> List[TruckMove]:
    """
    Apply truck moves once during the day.
    Mutates station_bikes in-place.
    """
    return greedy_threshold_policy(
        station_bikes,
        station_capacity,
        moves_available=trucks_per_day,
        **policy_kwargs,
    )
