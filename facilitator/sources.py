"""Where "who is speaking" comes from.  (PLACEHOLDERS - to be developed.)

Every source returns, when asked, the latest reading:
    Reading(angle_rad, speech_detected)   or   None (no data)

angle convention (same as the robot's microphone array):
    0 = robot's left,  pi/2 = straight ahead,  pi = robot's right
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Reading:
    angle_rad: float
    speech_detected: bool


class SpeakerSource:
    def read(self) -> Optional[Reading]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class NullSource(SpeakerSource):
    """No audio at all (works everywhere; used until the real sources exist)."""

    def read(self) -> Optional[Reading]:
        return None


class RobotDoASource(SpeakerSource):
    """TODO: poll http://<robot>:8000/api/state/doa (real robot only; null in the simulator).

    Response: {"angle": float, "speech_detected": bool} or null.
    Reuse one requests.Session(); poll at ~10 Hz.
    """

    def __init__(self, base_url: str):
        self.base_url = base_url

    def read(self) -> Optional[Reading]:
        raise NotImplementedError


class KeyboardSource(SpeakerSource):
    """TODO: simulate speakers in the simulator - key 1/2/3 = that seat is talking."""

    def read(self) -> Optional[Reading]:
        raise NotImplementedError
