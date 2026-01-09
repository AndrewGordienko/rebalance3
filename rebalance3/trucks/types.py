# rebalance3/trucks/types.py
from dataclasses import dataclass

@dataclass
class TruckMove:
    from_station: str
    to_station: str
    bikes: int
