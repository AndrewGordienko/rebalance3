from typing import Dict, List

from .policy import greedy_threshold_policy
from .types import TruckMove


def apply_truck_rebalancing(
    *,
    station_bikes: Dict[str, int],
    station_capacity: Dict[str, int],
    moves_available: int,
    empty_thr: float = 0.10,
    full_thr: float = 0.90,
    target_thr: float = 0.50,
    truck_cap: int = 20,
) -> List[TruckMove]:
    """
    Decide and apply up to `moves_available` truck moves.

    IMPORTANT:
    - This function is TIME-AGNOSTIC.
    - It mutates `station_bikes` immediately.
    - Caller is responsible for assigning t_min.
    """

    return greedy_threshold_policy(
        station_bikes=station_bikes,
        station_capacity=station_capacity,
        moves_available=moves_available,
        empty_thr=empty_thr,
        full_thr=full_thr,
        target_thr=target_thr,
        truck_cap=truck_cap,
    )
