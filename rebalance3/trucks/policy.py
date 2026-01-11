from typing import Dict, List
from .types import TruckMove

def greedy_threshold_policy(
    station_bikes: Dict[str, int],
    station_capacity: Dict[str, int],
    *,
    t_min: int,
    moves_available: int,
    empty_thr: float = 0.10,
    full_thr: float = 0.90,
    target_thr: float = 0.50,
    truck_cap: int = 20,
) -> List[TruckMove]:
    moves: List[TruckMove] = []

    def ratio(sid: str) -> float:
        cap = station_capacity.get(sid, 0)
        if cap <= 0:
            return 0.0
        return station_bikes.get(sid, 0) / cap

    deficit = [sid for sid in station_bikes if ratio(sid) < empty_thr]
    surplus = [sid for sid in station_bikes if ratio(sid) > full_thr]

    deficit.sort(key=ratio)
    surplus.sort(key=ratio, reverse=True)

    for _ in range(moves_available):
        if not deficit or not surplus:
            break

        to_sid = deficit[0]
        from_sid = surplus[0]

        cap_from = station_capacity[from_sid]
        cap_to = station_capacity[to_sid]

        desired_to = int(target_thr * cap_to)
        available_from = station_bikes[from_sid] - int(target_thr * cap_from)

        bikes = min(
            truck_cap,
            max(0, available_from),
            max(0, desired_to - station_bikes[to_sid]),
        )
        if bikes <= 0:
            break

        station_bikes[from_sid] -= bikes
        station_bikes[to_sid] += bikes

        moves.append(
            TruckMove(
                t_min=t_min,
                from_station=from_sid,
                to_station=to_sid,
                bikes=bikes,
            )
        )

        # refresh lists
        deficit = [sid for sid in deficit if ratio(sid) < empty_thr]
        surplus = [sid for sid in surplus if ratio(sid) > full_thr]
        deficit.sort(key=ratio)
        surplus.sort(key=ratio, reverse=True)

    return moves
