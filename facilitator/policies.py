"""Who should the robot turn to next?  (The only thing that differs between conditions.)

A policy sees the current speaking times and the history of who was addressed,
and returns a seat index. Policies are pure Python (no robot), so they are easy
to unit test.
"""

import random
from typing import List, Sequence


class Policy:
    name = "base"

    def choose(self, speaking_time_s: Sequence[float], history: List[int]) -> int:
        raise NotImplementedError


class RoundRobinPolicy(Policy):
    """BASELINE: everyone is addressed equally often, ignoring who actually speaks.

    Turns are grouped in rounds; each round addresses every seat exactly once.
    With shuffle=True the order inside each round is random (seeded, so the
    same sequence is produced every run), and the same person is never
    addressed twice in a row across round boundaries.
    """

    name = "baseline_round_robin"

    def __init__(self, n_seats: int, shuffle: bool = True, seed: int = 0):
        if n_seats < 2:
            raise ValueError("need at least 2 seats")
        self.n_seats = n_seats
        self.shuffle = shuffle
        self._rng = random.Random(seed)
        self._queue: List[int] = []

    def _new_round(self, last: int) -> List[int]:
        order = list(range(self.n_seats))
        if self.shuffle:
            self._rng.shuffle(order)
            if order[0] == last:  # avoid addressing the same person twice in a row
                order[0], order[-1] = order[-1], order[0]
        return order

    def choose(self, speaking_time_s: Sequence[float], history: List[int]) -> int:
        if not self._queue:
            last = history[-1] if history else -1
            self._queue = self._new_round(last)
        return self._queue.pop(0)


class LeastActivePolicy(Policy):
    """ADAPTIVE (to be implemented): turn to the seat with the lowest speaking time.

    TODO:
      - decide the window: cumulative, or recent activity only
      - deterministic tie-break (e.g. addressed longest ago)
      - decide whether the same person may be addressed twice in a row
    """

    name = "adaptive_least_active"

    def __init__(self, n_seats: int):
        self.n_seats = n_seats

    def choose(self, speaking_time_s: Sequence[float], history: List[int]) -> int:
        raise NotImplementedError("LeastActivePolicy is not implemented yet")


def make_policy(condition: str, n_seats: int, shuffle: bool, seed: int) -> Policy:
    if condition == "baseline":
        return RoundRobinPolicy(n_seats, shuffle=shuffle, seed=seed)
    if condition == "adaptive":
        return LeastActivePolicy(n_seats)
    raise ValueError(f"unknown condition {condition!r} (use 'baseline' or 'adaptive')")
