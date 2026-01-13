# rebalance3/trucks/types.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class TruckMove:
    from_station: str
    to_station: str
    bikes: int
    t_min: int | None = None
    truck_id: int | None = None
    distance_km: float | None = None
