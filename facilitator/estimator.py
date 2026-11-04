"""detect how active/passive each person is, for the robot's policy. 
one score per seat (lower = quieter)

functions:
    update(seat or None, dt, now) is called every tick with the attributed speaker

    CumulativeEstimator  - BASELINE (Micbot: the person who had cumulatively spoken the least). Every attributed tick counts, from the start.
    TurnDecayEstimator   - OUR METHOD, 2 changes:
    1. Speaking turns vs backchannels. Ticks grouped into utterances (pauses shorter than merge_gap_s are bridged). 
        Utterances shorter than min_turn_s ("mm-hm", "yeah", laughter, a cough) are backchannels: counted separately, not participation.
        Micbot's video analysis separated speaking turns from backchanneling, but its robot was
        driven by cumulative speaking time from the microphone array; no such distinction is described.
    2. Recent speech weighs more. Each finished turn is added with an exponential decay of half-life half_life_s. 
        With a cumulative total, someone who dominated the first minutes and then went quiet is never invited, and a
        quiet person who has just started contributing keeps being targeted.
    utterance in progress counts as soon as it is long enough, so a person who is talking right now is not treated as quiet.
"""

import math
from typing import List, Optional

from .detection_config import DetectionConfig


class ActivityEstimator:
    name = "base"

    def __init__(self, n_seats: int):
        self.n_seats = n_seats
        self.words = [0] * n_seats  # from speech-to-text (logged; not used in the score yet)

    def update(self, seat: Optional[int], dt: float, now: float) -> None:
        raise NotImplementedError

    def add_words(self, seat: int, n_words: int, now: float) -> None:
        self.words[seat] += n_words

    def scores(self, now: float) -> List[float]:
        raise NotImplementedError


class CumulativeEstimator(ActivityEstimator):
    """BASELINE (Micbot-style): total attributed speech since the start."""

    name = "cumulative"

    def __init__(self, n_seats: int):
        super().__init__(n_seats)
        self.speaking_s = [0.0] * n_seats

    def update(self, seat, dt, now):
        if seat is not None:
            self.speaking_s[seat] += dt

    def scores(self, now):
        return list(self.speaking_s)


class TurnDecayEstimator(ActivityEstimator):
    """OUR METHOD: decayed speaking-turn time, backchannels excluded."""

    name = "turns_decay"

    def __init__(self, n_seats: int, merge_gap_s: float = 0.6, min_turn_s: float = 1.0, half_life_s: float = 120.0):
        super().__init__(n_seats)
        self.merge_gap_s, self.min_turn_s = merge_gap_s, min_turn_s
        self._rate = math.log(2) / half_life_s
        self._score = [0.0] * n_seats          # decayed turn time, valid at self._score_t
        self._score_t = [0.0] * n_seats
        self._open: List[Optional[List[float]]] = [None] * n_seats  # [start, last_heard, speech_s]
        self.turns = [0] * n_seats
        self.backchannels = [0] * n_seats
        self.turn_s = [0.0] * n_seats

    def _decayed(self, k: int, now: float) -> float:
        return self._score[k] * math.exp(-self._rate * max(0.0, now - self._score_t[k]))

    def _close(self, k: int) -> None:
        start, last, speech_s = self._open[k]
        self._open[k] = None
        if speech_s >= self.min_turn_s:
            self._score[k] = self._decayed(k, last) + speech_s
            self._score_t[k] = last
            self.turns[k] += 1
            self.turn_s[k] += speech_s
        else:
            self.backchannels[k] += 1

    def update(self, seat, dt, now):
        for k in range(self.n_seats):  # close utterances that have gone quiet
            if self._open[k] is not None and k != seat and now - self._open[k][1] > self.merge_gap_s:
                self._close(k)
        if seat is None:
            return
        if self._open[seat] is not None and now - self._open[seat][1] > self.merge_gap_s:
            self._close(seat)  # same person again after a real pause = a new utterance
        if self._open[seat] is None:
            self._open[seat] = [now, now, 0.0]
        self._open[seat][1] = now
        self._open[seat][2] += dt

    def scores(self, now):
        out = []
        for k in range(self.n_seats):
            s = self._decayed(k, now)
            if self._open[k] is not None and self._open[k][2] >= self.min_turn_s:
                s += self._open[k][2]  # long utterance in progress counts already
            out.append(s)
        return out


def make_estimator(name: str, n_seats: int, det: DetectionConfig) -> ActivityEstimator:
    if name == "turns_decay":
        return TurnDecayEstimator(n_seats, det.merge_gap_s, det.min_turn_s, det.half_life_s)
    if name == "cumulative":
        return CumulativeEstimator(n_seats)
    raise ValueError(f"unknown estimator {name!r} (use 'turns_decay' or 'cumulative')")
