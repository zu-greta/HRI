from collections import Counter

import pytest

from facilitator.policies import LeastActivePolicy, RoundRobinPolicy, make_policy


def run(policy, n):
    history = []
    for _ in range(n):
        history.append(policy.choose([0.0, 0.0, 0.0], history))
    return history


@pytest.mark.parametrize("shuffle", [False, True])
def test_every_seat_addressed_equally(shuffle):
    h = run(RoundRobinPolicy(3, shuffle=shuffle, seed=1), 30)
    assert Counter(h) == {0: 10, 1: 10, 2: 10}


@pytest.mark.parametrize("shuffle", [False, True])
def test_each_round_contains_every_seat(shuffle):
    h = run(RoundRobinPolicy(3, shuffle=shuffle, seed=2), 12)
    for i in range(0, 12, 3):
        assert sorted(h[i:i + 3]) == [0, 1, 2]


def test_fixed_order_is_1_2_3():
    assert run(RoundRobinPolicy(3, shuffle=False), 6) == [0, 1, 2, 0, 1, 2]


@pytest.mark.parametrize("seed", range(20))
def test_never_same_person_twice_in_a_row(seed):
    h = run(RoundRobinPolicy(3, shuffle=True, seed=seed), 60)
    assert all(a != b for a, b in zip(h, h[1:]))


def test_same_seed_same_sequence():
    assert run(RoundRobinPolicy(3, seed=7), 15) == run(RoundRobinPolicy(3, seed=7), 15)


def test_make_policy():
    assert isinstance(make_policy("baseline", 3, True, 0), RoundRobinPolicy)
    with pytest.raises(ValueError):
        make_policy("other", 3, True, 0)


# ------------------------------------------------------------------ adaptive + Micbot
from facilitator.detection_config import DetectionConfig  # noqa: E402
from facilitator.policies import MicbotPolicy  # noqa: E402


def test_least_active_picks_the_quietest():
    assert LeastActivePolicy(3).choose([30.0, 12.0, 4.0], []) == 2


def test_least_active_ties_go_to_longest_ago():
    pol = LeastActivePolicy(3, margin=0.5)
    assert pol.choose([0, 0, 0], []) == 0          # nobody addressed yet -> seat 1
    assert pol.choose([0, 0, 0], [0]) == 1          # seat 1 just addressed
    assert pol.choose([5.0, 5.2, 9.0], [1, 0]) == 1  # 5.0 vs 5.2 is a tie; seat 2 addressed longer ago


def test_least_active_may_repeat_by_default_but_option_prevents_it():
    assert LeastActivePolicy(3).choose([20.0, 15.0, 1.0], [2]) == 2
    strict = LeastActivePolicy(3, repeat_margin=20.0)
    assert strict.choose([20.0, 15.0, 1.0], [2]) == 1


def test_least_active_is_deterministic():
    pol = LeastActivePolicy(3)
    assert {pol.choose([3.0, 1.0, 1.0], [0, 2]) for _ in range(20)} == {1}


def test_micbot_rule():
    assert MicbotPolicy(3).choose([5.0, 5.0, 9.0], [0]) == 0  # strict minimum, repeats allowed


def test_make_policy_uses_detection_config():
    pol = make_policy("adaptive", 3, True, 0, DetectionConfig(margin_s=1.5, repeat_margin_s=3.0))
    assert isinstance(pol, LeastActivePolicy) and pol.margin == 1.5 and pol.repeat_margin == 3.0


def test_max_consecutive_cap_is_off_by_default_and_works_when_set():
    assert LeastActivePolicy(3).choose([20.0, 15.0, 1.0], [2, 2, 2]) == 2
    assert LeastActivePolicy(3, max_consecutive=2).choose([20.0, 15.0, 1.0], [0, 2, 2]) == 1
