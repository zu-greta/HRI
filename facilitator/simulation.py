"""Simulated groups

Simulated groups, used to evaluate detection methods before (and besides) the study.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .attribution import make_attributor
from .detection_config import DetectionConfig
from .estimator import make_estimator
from .listener import ParticipationListener
from .policies import Policy, make_policy
from .sim_sources import MicModel
from .sources import Reading

TICK_S = 0.1


def gini(values: Sequence[float]) -> float:
    """0 = everyone equal, 1 = one person has everything."""
    v = sorted(max(x, 0.0) for x in values)
    n, total = len(v), sum(v)
    if n == 0 or total == 0:
        return 0.0
    return sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(v)) / (n * total)


@dataclass
class GroupModel:
    talkativeness: List[float] = field(default_factory=lambda: [0.6, 0.3, 0.1])  # who takes the floor
    responsiveness: List[float] = field(default_factory=lambda: [0.95, 0.9, 0.8])  # answers when invited
    turn_mean_s: float = 4.0
    backchannel_rate: float = 0.35


def _turn_length(rng: random.Random, mean_s: float) -> float:
    return min(max(rng.lognormvariate(math.log(mean_s) - 0.18, 0.6), 1.2), 20.0)


def _talk_period(group: GroupModel, invitee: Optional[int], rng: random.Random) -> List[Tuple[Optional[int], float, bool]]:
    """One listening period as (speaker or None, duration_s, is_backchannel)."""
    n = len(group.talkativeness)
    events: List[Tuple[Optional[int], float, bool]] = [(None, rng.uniform(0.5, 1.5), False)]
    last = None
    if invitee is not None and rng.random() < group.responsiveness[invitee]:
        events.append((invitee, _turn_length(rng, group.turn_mean_s), False))
        last = invitee
    for _ in range(rng.randint(1, 4)):
        weights = [0.0 if k == last else group.talkativeness[k] for k in range(n)]
        speaker = rng.choices(range(n), weights=weights)[0]
        if rng.random() < group.backchannel_rate:  # someone else says "mm-hm" first
            other = rng.choice([k for k in range(n) if k != speaker])
            events += [(None, rng.uniform(0.2, 0.6), False), (other, rng.uniform(0.3, 0.8), True)]
        events += [(None, rng.uniform(0.3, 1.0), False), (speaker, _turn_length(rng, group.turn_mean_s), False)]
        last = speaker
    events.append((None, 3.0, False))  # the silence that ends listening
    return events


@dataclass
class SessionResult:
    true_turn_s: List[float]
    true_speech_s: List[float]
    gini_speech: float
    decisions: int
    hit_cumulative: int  # decisions that chose the truly least active (total turn time so far)
    hit_recent: int      # ... (turn time in the last 120 s)
    ticks: int
    ticks_correct: int   # attribution exactly right (incl. "nobody") on usable ticks


def simulate_session(method: str, seats: Sequence[float], group: GroupModel, mic: MicModel, seed: int,
                     n_turns: int = 8, det: Optional[DetectionConfig] = None) -> SessionResult:
    """method: 'round_robin' | 'micbot' | 'ours' (see METHODS)."""
    rng = random.Random(seed)
    base = det or DetectionConfig()
    d = DetectionConfig(**{**base.__dict__, **METHODS[method]["det"]})
    n = len(seats)
    listener = ParticipationListener(make_attributor(d.attributor, seats, d), make_estimator(d.estimator, n, d))
    policy: Policy = make_policy(METHODS[method]["condition"], n, True, seed, d)

    t, head_yaw, invitee, history = 0.0, 0.0, None, []
    true_turn = [0.0] * n
    true_speech = [0.0] * n
    turn_log: List[Tuple[float, int, float]] = []  # (end_t, seat, dur) of real speaking turns
    res = SessionResult([], [], 0.0, 0, 0, 0, 0, 0)

    def feed(speaker: Optional[int], duration: float, robot_voice: bool = False) -> None:
        nonlocal t
        for _ in range(max(1, round(duration / TICK_S))):
            if robot_voice:
                reading = Reading(math.pi / 2, rng.random() < 0.9)  # the robot hears itself (front)
            else:
                reading = mic.observe(None if speaker is None else seats[speaker], head_yaw, rng)
            tick = listener.update(reading, t, robot_voice, head_yaw)
            if not robot_voice:
                res.ticks += 1
                res.ticks_correct += int(tick.seat == speaker)
            t += TICK_S

    for _turn in range(n_turns + 1):
        for speaker, dur, is_bc in _talk_period(group, invitee, rng):
            feed(speaker, dur)
            if speaker is not None:
                true_speech[speaker] += dur
                if not is_bc:
                    true_turn[speaker] += dur
                    turn_log.append((t, speaker, dur))
        if _turn == n_turns:
            break
        # --- decision (same moment for every method)
        seat = policy.choose(listener.activity(), history)
        history.append(seat)
        recent = [sum(dur for end, s, dur in turn_log if s == k and end > t - 120.0) for k in range(n)]
        res.decisions += 1
        res.hit_cumulative += int(true_turn[seat] == min(true_turn))
        res.hit_recent += int(recent[seat] == min(recent))
        # --- robot turns to the seat (head + microphones move), then speaks
        head_yaw = seats[seat]
        t += 0.8  # move duration: no listening while moving
        feed(None, 1.7, robot_voice=True)  # "What do you think?" + echo margin
        invitee = seat

    res.true_turn_s, res.true_speech_s = true_turn, true_speech
    res.gini_speech = gini(true_speech)
    return res


METHODS: Dict[str, Dict] = {
    "round_robin": {"condition": "baseline", "det": {"attributor": "hmm", "estimator": "turns_decay"}},
    "micbot": {"condition": "micbot", "det": {"attributor": "nearest", "estimator": "cumulative"}},
    "ours": {"condition": "adaptive", "det": {"attributor": "hmm", "estimator": "turns_decay"}},
}
