"""Activity estimators: Micbot-style cumulative vs ours (turns only, decayed)."""

import pytest

from facilitator.estimator import CumulativeEstimator, TurnDecayEstimator


def run(est, script, t=0.0, dt=0.1):
    """script: list of (seat or None, seconds)."""
    for seat, secs in script:
        for _ in range(round(secs / dt)):
            est.update(seat, dt, t)
            t += dt
    return t


def test_cumulative_counts_everything():
    est = CumulativeEstimator(3)
    run(est, [(0, 3.0), (None, 1.0), (1, 0.5)])
    assert est.scores(10) == pytest.approx([3.0, 0.5, 0.0], abs=0.11)


def test_backchannels_do_not_count_as_participation():
    est = TurnDecayEstimator(3, min_turn_s=1.0, half_life_s=1e9)
    t = run(est, [(0, 3.0), (None, 1.0), (1, 0.5), (None, 1.0), (1, 0.4), (None, 1.0)])
    s = est.scores(t)
    assert s[0] == pytest.approx(3.0, abs=0.11) and s[1] == 0.0
    assert est.backchannels[1] == 2 and est.turns[0] == 1


def test_short_pauses_stay_inside_one_turn():
    est = TurnDecayEstimator(3, merge_gap_s=0.6, min_turn_s=1.0, half_life_s=1e9)
    t = run(est, [(2, 0.6), (None, 0.3), (2, 0.6), (None, 2.0)])
    assert est.turns[2] == 1 and est.scores(t)[2] == pytest.approx(1.2, abs=0.11)


def test_recent_speech_weighs_more():
    est = TurnDecayEstimator(2, half_life_s=60.0)
    t = run(est, [(0, 10.0), (None, 120.0), (1, 5.0), (None, 1.0)])
    s = est.scores(t)
    assert s[0] == pytest.approx(10.0 * 0.5 ** ((t - 10.0) / 60.0), rel=0.03)  # halves every 60 s
    assert s[0] < 10.0 / 4  # more than two half-lives ago -> less than a quarter
    assert s[1] > s[0]  # recent speaker now counts as more active


def test_ongoing_long_utterance_counts_immediately():
    est = TurnDecayEstimator(2)
    t = run(est, [(1, 2.0)])
    assert est.scores(t)[1] == pytest.approx(2.0, abs=0.11)
