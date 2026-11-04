"""Per-tick log: 10 rows per second while the robot listens (and during the 0.5 s echo
margin after it speaks; there are no rows while a prompt plays or the robot turns).

Written next to the session log as <group>_<condition>_<time>_ticks.csv. It holds
the RAW microphone readings plus the head angle, so any detection method can be
re-run on a recorded session later (sim_sources.ReplaySource, evaluate_offline.py).

Columns:
  t               session clock (time.monotonic(), seconds) = mono_s in the event log
  angle_rad       raw microphone angle (0 = head's left, pi/2 = front, pi = right); empty = no reading
  speech          raw speech flag from the robot (1/0)
  head_yaw_deg    head direction in the room (+ = robot's left)
  robot_speaking  1 while the robot's own voice (+0.5 s echo) is playing
  world_az_deg    naive room direction (angle + head yaw), for plots and calibration
  seat            speaker chosen by the attributor (1-based; empty = nobody/unsure)
  confidence      attributor confidence 0..1
  activity        activity score per seat at this tick, space separated
"""

import csv
from pathlib import Path
from typing import List, Optional

from .listener import Tick

FIELDS = ["t", "angle_rad", "speech", "head_yaw_deg", "robot_speaking", "world_az_deg", "seat", "confidence",
          "activity"]


class TickLog:
    def __init__(self, session_log_path: Path):
        p = Path(session_log_path)
        self.path = p.with_name(p.stem + "_ticks.csv")
        self._f = open(self.path, "w", newline="")
        self._w = csv.writer(self._f)
        self._w.writerow(FIELDS)
        self._n = 0

    def write(self, tick: Tick, activity: List[float]) -> None:
        def fmt(x: Optional[float], digits: int = 4) -> str:
            return "" if x is None else f"{x:.{digits}f}"

        self._w.writerow([f"{tick.t:.3f}", fmt(tick.angle_rad), int(tick.speech), f"{tick.head_yaw_deg:.2f}",
                          int(tick.robot_speaking), fmt(tick.world_az_deg, 2),
                          "" if tick.seat is None else tick.seat + 1, f"{tick.confidence:.3f}",
                          " ".join(f"{a:.2f}" for a in activity)])
        self._n += 1
        if self._n % 50 == 0:
            self._f.flush()

    def close(self) -> None:
        self._f.close()
