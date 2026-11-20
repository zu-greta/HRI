"""THE HOOK between the session (Alyssa) and detection (Greta)

    session.py (Alyssa)                             detection (Greta)
    ─────────────────────                           ───────────────────────
    every 0.1 s while listening (incl. the 0.5 s echo margin after the robot speaks;
    nothing is read while say()/turn_to() block):
        tick = listener.update(reading, now,       ─> attribution.py  who is speaking?
                               robot_speaking,     estimator.py    how active is everyone?
                               head_yaw_deg)       ─> Tick (written to *_ticks.csv)
    before each turn:
        policy.choose(listener.activity(), history)   <─ one score per seat

rules:
  * `now` uses time.monotonic() (the session clock);
  * head_yaw_deg = robot.head_yaw_deg() (room frame, + = robot's left);
  * robot_speaking = robot.is_speaking(); readings during the robot's own voice are ignored but still logged.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence

from .attribution import Attributor, head_to_world_deg, make_attributor
from .detection_config import DetectionConfig
from .estimator import ActivityEstimator, make_estimator
from .sources import Reading


@dataclass
class Tick:
    """Everything known about one 0.1 s moment (one row of *_ticks.csv)."""

    t: float
    angle_rad: Optional[float]
    speech: bool
    head_yaw_deg: float
    robot_speaking: bool
    world_az_deg: Optional[float]   # naive room direction (for plots/calibration)
    seat: Optional[int]             # attributed speaker, 0-based; None = nobody/unsure
    confidence: float


class Listener:
    def update(self, reading: Optional[Reading], now: float, robot_speaking: bool, head_yaw_deg: float) -> Tick:
        raise NotImplementedError

    def activity(self) -> List[float]:
        raise NotImplementedError


class ParticipationListener(Listener):
    def __init__(self, attributor: Attributor, estimator: ActivityEstimator,
                 ignore_while_robot_speaks: bool = True):
        self.attributor, self.estimator = attributor, estimator
        self.ignore_while_robot_speaks = ignore_while_robot_speaks
        self._last_t: Optional[float] = None
        self._now = 0.0

    @classmethod
    def from_config(cls, seat_azimuths_deg: Sequence[float], det: DetectionConfig) -> "ParticipationListener":
        return cls(make_attributor(det.attributor, seat_azimuths_deg, det),
                   make_estimator(det.estimator, len(seat_azimuths_deg), det),
                   det.ignore_while_robot_speaks)

    def update(self, reading, now, robot_speaking, head_yaw_deg):
        dt = 0.0 if self._last_t is None else min(max(now - self._last_t, 0.0), 0.5)  # cap gaps (robot moving)
        self._last_t, self._now = now, now
        usable = not (robot_speaking and self.ignore_while_robot_speaks)
        angle = reading.angle_rad if reading is not None else None
        speech = bool(reading is not None and reading.speech_detected)

        seat, conf = self.attributor.assign(angle, speech, head_yaw_deg, usable)
        self.estimator.update(seat, dt, now)

        return Tick(now, angle, speech, head_yaw_deg, robot_speaking,
                    head_to_world_deg(angle, head_yaw_deg) if angle is not None else None, seat, conf)

    def activity(self):
        return self.estimator.scores(self._now)
