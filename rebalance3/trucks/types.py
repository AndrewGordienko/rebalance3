from dataclasses import dataclass

@dataclass
class TruckMove:
    from_station: str
    to_station: str
    bikes: int
    t_min: int | None = None