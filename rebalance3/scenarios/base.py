from dataclasses import dataclass
from pathlib import Path

@dataclass
class Scenario:
    name: str
    state_csv: Path
    bucket_minutes: int
    meta: dict
