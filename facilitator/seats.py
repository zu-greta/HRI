"""participant seating from robot POV
[GRETA] - placeholder values to be replaced by calibration on the real robot 
    use: python evaluate_offline.py fit --ticks ... --labels ... 
    which writes seats.json. When seats.json exists it is used instead.

Angles are in degrees in the ROOM (world) frame, measured from the robot's
neutral forward direction: 0 = straight ahead, + = robot's LEFT, - = robot's RIGHT.
Seat 1 is index 0 in the code.
"""

import json
from pathlib import Path
from typing import List, Tuple

PLACEHOLDER_SEAT_AZIMUTHS_DEG: List[float] = [50.0, 0.0, -50.0]  # PLACEHOLDER - calibrate!

SEATS_FILE = Path(__file__).resolve().parent.parent / "seats.json"


def load_seat_azimuths(path: Path = SEATS_FILE) -> Tuple[List[float], bool]:
    """Return (seat angles, is_placeholder). Uses seats.json if it exists."""
    path = Path(path)
    if path.exists():
        data = json.loads(path.read_text())
        return [float(a) for a in data["seat_azimuths_deg"]], False
    return list(PLACEHOLDER_SEAT_AZIMUTHS_DEG), True


def save_seat_azimuths(angles: List[float], path: Path = SEATS_FILE, note: str = "") -> None:
    Path(path).write_text(json.dumps({"seat_azimuths_deg": [round(a, 1) for a in angles], "note": note}, indent=2))
