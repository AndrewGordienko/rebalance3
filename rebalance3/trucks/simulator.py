from typing import Dict, List
from .policy import greedy_threshold_policy
from .types import TruckMove

def apply_truck_rebalancing(
    station_bikes: Dict[str, int],
    station_capacity: Dict[str, int],
    *,
    t_min: int,
    moves_available: int,
    **policy_kwargs,
) -> List[TruckMove]:
    return greedy_threshold_policy(
        station_bikes,
        station_capacity,
        t_min=t_min,
        moves_available=moves_available,
        **policy_kwargs,
    )
