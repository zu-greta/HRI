"""Detection pieces: geometry, attribution, activity estimate, adaptive policy."""

import math
import random

from facilitator.attribution import (HMMAttributor, NearestSeatAttributor, expected_mic_head_deg, fold_front_back,
                                     head_to_world_deg)
from facilitator.detection_config import DetectionConfig
from facilitator.estimator import CumulativeEstimator, TurnDecayEstimator
from facilitator.policies import LeastActivePolicy, MicbotPolicy
from facilitator.sim_sources import MicModel
from facilitator.sources import KeyboardSource

SEATS = [50.0, 0.0, -50.0]


def mic(head_deg):
    return math.pi / 2 - math.radians(head_deg)


def test_front_back_mirroring():
    assert fold_front_back(100) == 80 and fold_front_back(-130) == -50 and fold_front_back(30) == 30
    # robot faces seat 3 (-50): seat 1 (+50) is 100 deg to the left and is reported at 80
    assert expected_mic_head_deg(50, -50) == 80


def test_mirroring_matters_for_wide_seats():
    """At +-50 deg seats the mirrored angle is only 20 deg off, so nearest-seat still copes; at +-70 deg
    (robot facing seat 3, seat 1 is 140 deg away -> reported at 40) nearest-seat fails, the HMM does not."""
    det = DetectionConfig()
    near50 = NearestSeatAttributor(SEATS)
    assert near50.assign(mic(expected_mic_head_deg(50, -50)), True, -50)[0] == 0
    wide = [70.0, 0.0, -70.0]
    hmm, near = HMMAttributor(wide, det), NearestSeatAttributor(wide)
    angle = mic(expected_mic_head_deg(70, -70))
    for _ in range(10):
        seat_h, _ = hmm.assign(angle, True, -70)
    assert seat_h == 0
    assert near.assign(angle, True, -70)[0] != 0


def test_hmm_accuracy_on_simulated_stream():
    rng, m = random.Random(1), MicModel()
    hmm = HMMAttributor(SEATS, DetectionConfig())
    ok = n = 0
    for head in (0.0, 50.0, -50.0):
        for speaker in (0, 1, 2):
            for _ in range(60):
                r = m.observe(SEATS[speaker], head, rng)
                seat, _ = hmm.assign(r.angle_rad, r.speech_detected, head)
                n += 1
                ok += seat == speaker
    assert ok / n > 0.8


def test_robot_voice_is_ignored():
    hmm = HMMAttributor(SEATS, DetectionConfig())
    assert hmm.assign(mic(0), True, 0, usable=False)[0] is None
    assert NearestSeatAttributor(SEATS).assign(mic(0), True, 0, usable=False)[0] is None


def test_backchannels_do_not_count_but_turns_do():
    est = TurnDecayEstimator(3, merge_gap_s=0.6, min_turn_s=1.0, half_life_s=120)
    t = 0.0
    for _ in range(5):            # 0.5 s "mm-hm" from seat 2
        est.update(1, 0.1, t); t += 0.1
    for _ in range(30):           # 3 s turn from seat 1
        est.update(0, 0.1, t); t += 0.1
    for _ in range(10):
        est.update(None, 0.1, t); t += 0.1
    s = est.scores(t)
    assert est.backchannels[1] == 1 and s[1] == 0.0
    assert 2.5 < s[0] < 3.1


def test_recent_speech_weighs_more():
    est = TurnDecayEstimator(3, half_life_s=60)
    for i in range(20):
        est.update(0, 0.1, i * 0.1)
    est.update(None, 0.1, 3.0)
    early = est.scores(3.0)[0]
    assert abs(est.scores(63.0)[0] - early / 2) < 0.05
    cum = CumulativeEstimator(3)
    cum.update(0, 2.0, 0.0)
    assert cum.scores(1000.0)[0] == 2.0  # never forgets


def test_least_active_policy():
    pol = LeastActivePolicy(3, margin=0.5)
    assert pol.choose([10, 5, 1], []) == 2
    assert pol.choose([0, 0, 0], [0, 2]) == 1           # tie -> never addressed first
    assert pol.choose([10, 0.2, 0.0], [2]) == 1         # tie within margin -> addressed longest ago
    assert MicbotPolicy(3).choose([10, 5, 1], []) == 2


def test_keyboard_source_follows_head_yaw():
    yaw = {"v": -50.0}
    src = KeyboardSource(SEATS, head_yaw_deg=lambda: yaw["v"])
    src._seat, src._speaking_until = 0, float("inf")
    r = src.read()
    hmm = HMMAttributor(SEATS, DetectionConfig())
    for _ in range(10):
        seat, _ = hmm.assign(r.angle_rad, r.speech_detected, yaw["v"])
    assert seat == 0
    assert round(head_to_world_deg(src.read().angle_rad, 0.0)) == 80  # mirrored, as the real array would report
