"""decision policies for the robot's turn-taking (NOTE: the only thing that differs between conditions)

A policy gets one activity score per seat (lower = quieter; from listener.activity())
and the history of who was addressed, and returns a seat index (0-based).

    RoundRobinPolicy   BASELINE condition, "balanced" random (default; ignores activity)
    UniformRandomPolicy BASELINE condition, "uniform" random (alternative; ignores activity)
    LeastActivePolicy  ADAPTIVE condition of the study (our method)
    MicbotPolicy       Micbot's rule, only for the offline comparison (evaluate_offline.py)
"""

import random
from typing import List, Optional, Sequence


class Policy:
    name = "base"

    def choose(self, speaking_time_s: Sequence[float], history: List[int]) -> int:
        raise NotImplementedError


class RoundRobinPolicy(Policy):
    """BASELINE: everyone is addressed equally often, ignoring who actually speaks.

    Turns are grouped in rounds; each round addresses every seat exactly once.
    if shuffle=True the order inside each round is random (seeded)
    and the same person is never addressed twice in a row across round boundaries.
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


class UniformRandomPolicy(Policy):
    """BASELINE alternative: each choice independently and uniformly at random (seeded).

    note: over 6 choices someone is never addressed in about 26% of rounds, so robot attention itself is unequal.
    """

    name = "baseline_uniform_random"

    def __init__(self, n_seats: int, seed: int = 0):
        self.n_seats = n_seats
        self._rng = random.Random(seed)

    def choose(self, speaking_time_s: Sequence[float], history: List[int]) -> int:
        return self._rng.randrange(self.n_seats)


def _last_addressed(history: List[int], seat: int) -> int:
    """Index in history of the last time `seat` was addressed (-1 = never)."""
    for i in range(len(history) - 1, -1, -1):
        if history[i] == seat:
            return i
    return -1


class LeastActivePolicy(Policy):
    """ADAPTIVE (our method): invite the person who has been least active.

    Deterministic rules, in order:
      1. Candidates = seats whose activity is within `margin` of the lowest (a tie; eg. at start all 0)
      2. Among tied candidates, prefer the one addressed longest ago (never-addressed first), then the lowest activity, then the lowest seat number.
      3. Optional (repeat_margin > 0, OFF by default): do not invite the same person
         twice in a row unless they are quieter than everyone else by repeat_margin.
         A social choice (not putting someone on the spot repeatedly)
      4. Optional (max_consecutive > 0, OFF by default): never invite the same person
         more than max_consecutive times in a row; then the next-quietest is invited.
    """

    name = "adaptive_least_active"

    def __init__(self, n_seats: int, margin: float = 0.5, repeat_margin: float = 0.0, max_consecutive: int = 0):
        self.n_seats, self.margin, self.repeat_margin = n_seats, margin, repeat_margin
        self.max_consecutive = max_consecutive

    def choose(self, speaking_time_s: Sequence[float], history: List[int]) -> int:
        scores = list(speaking_time_s)
        lowest = min(scores)
        candidates = [k for k in range(self.n_seats) if scores[k] - lowest <= self.margin]
        candidates.sort(key=lambda k: (_last_addressed(history, k), scores[k], k))
        choice = candidates[0]
        last = history[-1] if history else None
        if self.repeat_margin > 0 and choice == last:
            others = [k for k in range(self.n_seats) if k != last]
            clearly_quietest = all(scores[k] - scores[last] >= self.repeat_margin for k in others)
            if not clearly_quietest:
                choice = min(others, key=lambda k: (scores[k], _last_addressed(history, k), k))
        cap = self.max_consecutive
        if cap > 0 and len(history) >= cap and all(h == choice for h in history[-cap:]):
            others = [k for k in range(self.n_seats) if k != choice]
            choice = min(others, key=lambda k: (scores[k], _last_addressed(history, k), k))
        return choice


class MicbotPolicy(Policy):
    """Micbot (Tennent et al., HRI 2019): the person who has cumulatively spoken the least.

    NOTE: used as comparison for improvement - not in study.
    """

    name = "micbot_least_cumulative"

    def __init__(self, n_seats: int):
        self.n_seats = n_seats

    def choose(self, speaking_time_s: Sequence[float], history: List[int]) -> int:
        return min(range(self.n_seats), key=lambda k: (speaking_time_s[k], k))


def make_policy(condition: str, n_seats: int, shuffle: bool, seed: int, det: Optional[object] = None,
                baseline: str = "balanced") -> Policy:
    """condition: 'baseline' | 'adaptive' | 'micbot'. det: DetectionConfig (margins for 'adaptive').
    baseline: 'balanced' (shuffled round-robin) | 'uniform' (independent random choices)."""
    if condition == "baseline":
        if baseline == "uniform":
            return UniformRandomPolicy(n_seats, seed=seed)
        return RoundRobinPolicy(n_seats, shuffle=shuffle, seed=seed)
    if condition == "adaptive":
        if det is None:
            return LeastActivePolicy(n_seats)
        return LeastActivePolicy(n_seats, det.margin_s, det.repeat_margin_s, det.max_consecutive)
    if condition == "micbot":
        return MicbotPolicy(n_seats)
    raise ValueError(f"unknown condition {condition!r} (use 'baseline' or 'adaptive')")
