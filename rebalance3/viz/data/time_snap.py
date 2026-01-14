# rebalance3/viz/data/time_snap.py

def snap_time(requested: int, valid_times: list[int]) -> int:
    """
    Snap requested time to nearest available snapshot time.

    valid_times example:
      - hour mode: [0,1,2,...,23]
      - t_min mode: [0,15,30,...,1425]
    """
    if requested is None:
        return valid_times[0] if valid_times else 0

    if not valid_times:
        return int(requested)

    req = int(requested)
    return min(valid_times, key=lambda t: abs(int(t) - req))
