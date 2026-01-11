from dataclasses import dataclass

@dataclass
class TruckMove:
    t_min: int
    from_station: str
    to_station: str
    bikes: int
