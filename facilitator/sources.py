"""Speech sources: where the 0.1 s microphone readings come from.

Every source returns, when asked, the latest reading:
    Reading(angle_rad, speech_detected)   or   None (no data)

angle convention (same as the robot's microphone array, which sits in the HEAD):
    0 = head's left,  pi/2 = straight ahead of the head,  pi = head's right
The angle is relative to where the head points, not to the room.

    RobotDoASource   STUDY: the real robot's microphone array (REST /api/state/doa)
    NullSource       no audio (the robot cannot hear anyone)
    LaptopMicSource  SIMULATOR TESTING: loudness from this computer's microphone. It has no
                     direction, so every sound is reported straight ahead = credited to the seat
                     the head currently faces. Tests the session flow, NOT the balancing.
    KeyboardSource   SIMULATOR TESTING: press 1/2/3 = that seat is speaking (direction is
                     simulated correctly for the current head yaw)
Simulated groups and replay of recordings live in sim_sources.py.
"""

import math
import os
import select
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

import numpy as np
import requests


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
    """No audio at all: the robot cannot hear anyone."""

    def read(self) -> Optional[Reading]:
        return None


class RobotDoASource(SpeakerSource):
    """The robot's microphone array, through http://<robot>:8000/api/state/doa.

    The daemon answers {"angle": float, "speech_detected": bool}, or null when
    there is no microphone (always in the simulator). Connection errors also
    count as no data, so a network glitch cannot crash a study session.
    """

    def __init__(self, base_url: str, timeout_s: float = 0.5):
        self.url = f"{base_url}/api/state/doa"
        self.timeout_s = timeout_s
        self._http = requests.Session()

    def read(self) -> Optional[Reading]:
        try:
            r = self._http.get(self.url, timeout=self.timeout_s)
            r.raise_for_status()
            data = r.json()
        except requests.RequestException:
            return None
        if data is None:
            return None
        return Reading(data["angle"], data["speech_detected"])

    def wait_until_ready(self, timeout_s: float = 2.0) -> bool:
        """True once the microphones give a reading (the first takes ~100 ms to arrive)."""
        end = time.monotonic() + timeout_s
        while True:
            if self.read() is not None:
                return True
            if time.monotonic() >= end:
                return False
            time.sleep(0.1)

    def close(self) -> None:
        self._http.close()


class LaptopMicSource(SpeakerSource):
    """SIMULATOR TESTING: this computer's microphone as a speech on/off detector (no direction).
    """

    SAMPLE_RATE = 16000
    BLOCK_SIZE = 800  # 50 ms

    def __init__(self, threshold_ratio: float = 3.0, min_level: float = 0.01, calibrate_s: float = 1.0):
        import sounddevice as sd

        self._lock = threading.Lock()
        self._level = 0.0  # loudest block since the last read
        self._stream = sd.InputStream(samplerate=self.SAMPLE_RATE, blocksize=self.BLOCK_SIZE, channels=1,
                                      callback=self._on_audio)
        self._stream.start()
        time.sleep(calibrate_s)
        self.noise_level = self._take_level()
        self.threshold = max(self.noise_level * threshold_ratio, min_level)

    def _on_audio(self, indata, frames, time_info, status) -> None:
        level = float(np.sqrt(np.mean(np.square(indata))))
        with self._lock:
            self._level = max(self._level, level)

    def _take_level(self) -> float:
        with self._lock:
            level, self._level = self._level, 0.0
        return level

    def read(self) -> Optional[Reading]:
        if not self._stream.active:  # e.g. the microphone was unplugged
            return None
        return Reading(math.pi / 2, self._take_level() >= self.threshold)

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


class KeyboardSource(SpeakerSource):
    """SIMULATOR TESTING: keyboard instead of a microphone.

    Press or hold 1/2/3 in the terminal: that seat counts as speaking until hold_s after the
    last key press. The reported angle is what the head-mounted array would measure for that
    seat at the CURRENT head yaw (incl. front/back mirroring), so attribution stays correct
    after the robot turns its head.
    """

    def __init__(self, seat_azimuths_deg: Sequence[float], hold_s: float = 0.6, clock=time.monotonic,
                 head_yaw_deg: Callable[[], float] = lambda: 0.0):
        self.seat_azimuths_deg = list(seat_azimuths_deg)
        self._head_yaw = head_yaw_deg
        self.hold_s = hold_s
        self._clock = clock
        self._seat = 0
        self._speaking_until = 0.0
        self._saved_tty = None
        if os.name != "nt" and sys.stdin.isatty():  # macOS/Linux: read keys without waiting for Enter
            import termios
            import tty

            self._saved_tty = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin)

    def _pressed_keys(self) -> str:
        if os.name == "nt":
            import msvcrt

            keys = ""
            while msvcrt.kbhit():
                keys += msvcrt.getwch()
            return keys
        if self._saved_tty is None or not select.select([sys.stdin], [], [], 0)[0]:
            return ""
        return os.read(sys.stdin.fileno(), 1024).decode(errors="ignore")

    def read(self) -> Optional[Reading]:
        now = self._clock()
        for key in self._pressed_keys():
            if key.isdecimal() and 1 <= int(key) <= len(self.seat_azimuths_deg):
                self._seat = int(key) - 1
                self._speaking_until = now + self.hold_s
        from .attribution import expected_mic_head_deg  # local import: attribution does not import sources

        try:
            yaw = float(self._head_yaw())
        except Exception:  # robot not connected yet
            yaw = 0.0
        head_deg = expected_mic_head_deg(self.seat_azimuths_deg[self._seat], yaw)
        return Reading(math.pi / 2 - math.radians(head_deg), now < self._speaking_until)

    def close(self) -> None:
        if self._saved_tty is not None:
            import termios

            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._saved_tty)
            self._saved_tty = None
