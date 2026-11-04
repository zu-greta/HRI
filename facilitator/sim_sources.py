"""simulation sources 

MicModel        - imitates the robot's microphone array: angle noise, outliers,
                  missed speech, false alarms, the array turning with the head,
                  and front/back mirroring. PLACEHOLDER noise values; fit them on
                  real recordings (evaluate_offline.py fit) and copy them here.
ScriptedSource  - a scripted group, e.g. "seat 1 talks a lot, seat 3 hardly", for
                  the simulator (--source scripted) and for tests.
iter_ticks()    - reads a *_ticks.csv recorded on the real robot (offline replay).
ReplaySource    - the same recording as a live SpeakerSource.
load_labels()   - hand-made ground truth: who spoke when.
"""

import csv
import math
import random
from dataclasses import dataclass
from typing import Callable, Iterator, List, Optional, Sequence, Tuple

from .attribution import fold_front_back
from .sources import Reading, SpeakerSource


@dataclass
class MicModel:
    noise_deg: float = 10.0        # PLACEHOLDER angle spread around the true speaker
    outlier_rate: float = 0.10     # PLACEHOLDER readings pointing anywhere
    miss_rate: float = 0.15        # PLACEHOLDER speech flag missed while someone talks
    false_alarm_rate: float = 0.05  # PLACEHOLDER speech flag while nobody talks

    def observe(self, speaker_world_deg: Optional[float], head_yaw_deg: float, rng: random.Random) -> Reading:
        """What the array reports for a speaker at speaker_world_deg (None = nobody talking)."""
        if speaker_world_deg is None:
            return Reading(rng.uniform(0.0, math.pi), rng.random() < self.false_alarm_rate)
        speech = rng.random() >= self.miss_rate
        if rng.random() < self.outlier_rate:
            return Reading(rng.uniform(0.0, math.pi), speech)
        head_deg = fold_front_back(speaker_world_deg + rng.gauss(0.0, self.noise_deg) - head_yaw_deg)
        angle = min(max(math.pi / 2 - math.radians(head_deg), 0.0), math.pi)
        return Reading(angle, speech)


class ScriptedSource(SpeakerSource):
    def __init__(self, turns: List[Tuple[float, float, int]], seat_azimuths_deg: Sequence[float], clock,
                 mic: Optional[MicModel] = None, seed: int = 0, head_yaw_deg: Callable[[], float] = lambda: 0.0):
        """turns: (start_s, end_s, seat) with seat 0-based; times relative to the first read()."""
        self.turns, self.seats, self.clock = turns, list(seat_azimuths_deg), clock
        self.mic = mic or MicModel()
        self._rng = random.Random(seed)
        self._t0: Optional[float] = None
        self._head_yaw = head_yaw_deg  # the simulated array turns with the robot's head

    def read(self) -> Optional[Reading]:
        now = self.clock()
        if self._t0 is None:
            self._t0 = now
        t = now - self._t0
        speaker = next((s for a, b, s in self.turns if a <= t < b), None)
        world = None if speaker is None else self.seats[speaker]
        return self.mic.observe(world, self._head_yaw(), self._rng)


@dataclass
class RecordedTick:
    t: float
    reading: Optional[Reading]
    head_yaw_deg: float
    robot_speaking: bool


def iter_ticks(path: str) -> Iterator[RecordedTick]:
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            reading = None
            if row["angle_rad"] != "":
                reading = Reading(float(row["angle_rad"]), row["speech"] == "1")
            yield RecordedTick(float(row["t"]), reading, float(row["head_yaw_deg"]), row["robot_speaking"] == "1")


class ReplaySource(SpeakerSource):
    """Plays a recorded *_ticks.csv back, one row per read(). Also exposes the
    recorded head_yaw_deg / robot_speaking of the current row."""

    def __init__(self, path: str):
        self._it = iter_ticks(path)
        self.current: Optional[RecordedTick] = None

    def read(self) -> Optional[Reading]:
        self.current = next(self._it, None)
        return None if self.current is None else self.current.reading

    def head_yaw_deg(self) -> float:
        return 0.0 if self.current is None else self.current.head_yaw_deg


def load_labels(path: str, offset_s: float = 0.0) -> List[Tuple[float, float, int]]:
    """Ground truth CSV with header start_s,end_s,seat (seat 1-based).

    offset_s is added to every time to move label time (e.g. video time) onto the
    tick-log clock: tick_t = label_t + offset_s.
    """
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            out.append((float(row["start_s"]) + offset_s, float(row["end_s"]) + offset_s, int(row["seat"]) - 1))
    return sorted(out)


def truth_at(labels: List[Tuple[float, float, int]], t: float) -> Optional[int]:
    for a, b, s in labels:
        if a <= t < b:
            return s
    return None
