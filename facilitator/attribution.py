"""Determine which seat is speaking, given a stream of microphone readings and head yaw.
- robot's microphone array is in its head: reports (angle, speech_detected) every 0.1 s
    - angle 0 = head's left, pi/2 = head's front, pi = head's right
- notes: 
    - array turns with the head so the same person gives a different angle depending on where the robot looks
    - the array only resolves left-right:
    a voice 100 deg to the left (slightly behind) is reported as 80 deg to the left ("front/back mirroring"). 
    This happens in our study, because the robot faces one side seat (e.g. -50 deg) 
    while the opposite seat (+50 deg) is 100 deg away.


2 attributors (same interface):
NearestSeatAttributor  - BASELINE (Micbot-style; Micbot's Kinect array was fixed, ours turns with the head).
                         Each reading on its own:
                         room angle = mic angle + head yaw -> nearest seat.
HMMAttributor          - OUR METHOD. An online hidden Markov model (forward filter)
                         over the states {silence, seat 1..N}:
                           * emission: for each seat, the angle the array should
                             report given the current head yaw, including the
                             front/back mirroring -> compared with the measured angle;
                             plus models of missed speech, false alarms and outliers;
                           * transition: people keep talking for a while, so the
                             state rarely switches between consecutive 0.1 s ticks;
                           * output: the most probable state, only if confident.
"""

import math
from typing import List, Optional, Sequence, Tuple

from .detection_config import DetectionConfig


# ----------------------------------------------------------------------------- geometry
def wrap_deg(a: float) -> float:
    """Wrap an angle to (-180, 180]."""
    a = (a + 180.0) % 360.0 - 180.0
    return 180.0 if a == -180.0 else a


def angular_distance_deg(a: float, b: float) -> float:
    return abs(wrap_deg(a - b))


def mic_angle_to_head_deg(angle_rad: float) -> float:
    """Microphone angle (0..pi) -> head-frame direction in degrees (+90 left .. -90 right)."""
    return 90.0 - math.degrees(angle_rad)


def head_to_world_deg(angle_rad: float, head_yaw_deg: float) -> float:
    """Naive room direction: head-frame direction + head yaw (ignores mirroring)."""
    return mic_angle_to_head_deg(angle_rad) + head_yaw_deg


def fold_front_back(head_deg: float) -> float:
    """What a left-right-only array reports for a source at head_deg (head frame).

    Sources behind the array are mirrored to the front: 100 -> 80, -130 -> -50.
    """
    a = wrap_deg(head_deg)
    if a > 90.0:
        return 180.0 - a
    if a < -90.0:
        return -180.0 - a
    return a


def expected_mic_head_deg(seat_world_deg: float, head_yaw_deg: float) -> float:
    """Head-frame angle the array should report for a speaker at this seat."""
    return fold_front_back(seat_world_deg - head_yaw_deg)


# ----------------------------------------------------------------------------- interface
class Attributor:
    """assign() is called every tick. angle_rad is None when there is no reading.

    Returns (seat or None, confidence 0..1).
    """

    def assign(self, angle_rad: Optional[float], speech: bool, head_yaw_deg: float,
               usable: bool = True) -> Tuple[Optional[int], float]:
        raise NotImplementedError

    def reset(self) -> None:
        pass


# ----------------------------------------------------------------------------- baseline
class NearestSeatAttributor(Attributor):
    """BASELINE (Micbot-style): every reading independently -> nearest seat."""

    name = "nearest"

    def __init__(self, seat_azimuths_deg: Sequence[float], tolerance_deg: float = 25.0):
        self.seats: List[float] = list(seat_azimuths_deg)
        self.tolerance_deg = tolerance_deg

    def assign(self, angle_rad, speech, head_yaw_deg, usable=True):
        if not usable or not speech or angle_rad is None:
            return None, 1.0
        world = head_to_world_deg(angle_rad, head_yaw_deg)
        dists = [angular_distance_deg(world, s) for s in self.seats]
        best = min(range(len(dists)), key=dists.__getitem__)
        return (best, 1.0) if dists[best] <= self.tolerance_deg else (None, 1.0)


# ----------------------------------------------------------------------------- our method
class HMMAttributor(Attributor):
    """OUR METHOD: online HMM forward filter over {silence, seat 1..N}.

    State 0 = silence (or someone/something we do not track), state k = seat k-1.
    All probabilities are renormalised every tick, so no underflow.
    """

    name = "hmm"
    ANGLE_RANGE_DEG = 180.0  # the array reports directions over 180 deg

    def __init__(self, seat_azimuths_deg: Sequence[float], det: DetectionConfig):
        self.seats = list(seat_azimuths_deg)
        self.n = len(self.seats) + 1
        self.det = det
        self._trans = self._transition_matrix()
        self.reset()

    def reset(self) -> None:
        self.belief = [1.0] + [0.0] * (self.n - 1)  # start: silence

    def _transition_matrix(self) -> List[List[float]]:
        d, n_seats = self.det, self.n - 1
        T = [[0.0] * self.n for _ in range(self.n)]
        T[0][0] = d.stay_silent
        for k in range(1, self.n):
            T[0][k] = (1 - d.stay_silent) / n_seats          # silence -> someone starts
            T[k][k] = d.stay_speaking
            T[k][0] = (1 - d.stay_speaking) * 0.6            # speaker stops
            for j in range(1, self.n):                       # direct hand-over to another seat
                if j != k:
                    T[k][j] = (1 - d.stay_speaking) * 0.4 / max(n_seats - 1, 1)
        return T

    def _emission(self, angle_rad: Optional[float], speech: bool, head_yaw_deg: float) -> List[float]:
        d = self.det
        if angle_rad is None:
            return [1.0] * self.n  # no reading: no information
        if not speech:
            return [1.0 - d.vad_false_alarm_rate] + [d.vad_miss_rate] * (self.n - 1)
        uniform = 1.0 / self.ANGLE_RANGE_DEG
        measured = mic_angle_to_head_deg(angle_rad)
        e = [d.vad_false_alarm_rate * uniform]
        for seat in self.seats:
            diff = measured - expected_mic_head_deg(seat, head_yaw_deg)
            gauss = math.exp(-0.5 * (diff / d.angle_sigma_deg) ** 2) / (d.angle_sigma_deg * math.sqrt(2 * math.pi))
            e.append((1.0 - d.vad_miss_rate) * ((1.0 - d.outlier_rate) * gauss + d.outlier_rate * uniform))
        return e

    def assign(self, angle_rad, speech, head_yaw_deg, usable=True):
        # 1. predict: apply the transition model
        prior = [sum(self.belief[i] * self._trans[i][j] for i in range(self.n)) for j in range(self.n)]
        # 2. update with the reading (skipped while the robot itself is talking)
        if usable:
            e = self._emission(angle_rad, speech, head_yaw_deg)
            post = [p * x for p, x in zip(prior, e)]
        else:
            post = prior
        total = sum(post)
        self.belief = [p / total for p in post] if total > 0 else [1.0 / self.n] * self.n
        if not usable:
            return None, self.belief[0]
        # 3. decide
        best = max(range(self.n), key=self.belief.__getitem__)
        conf = self.belief[best]
        if best == 0 or conf < self.det.min_confidence:
            return None, conf
        return best - 1, conf


def make_attributor(name: str, seat_azimuths_deg: Sequence[float], det: DetectionConfig) -> Attributor:
    if name == "hmm":
        return HMMAttributor(seat_azimuths_deg, det)
    if name == "nearest":
        return NearestSeatAttributor(seat_azimuths_deg, det.seat_tolerance_deg)
    raise ValueError(f"unknown attributor {name!r} (use 'hmm' or 'nearest')")
