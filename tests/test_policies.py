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


def test_adaptive_is_a_placeholder():
    with pytest.raises(NotImplementedError):
        LeastActivePolicy(3).choose([1, 2, 3], [])


def test_make_policy():
    assert isinstance(make_policy("baseline", 3, True, 0), RoundRobinPolicy)
    with pytest.raises(ValueError):
        make_policy("other", 3, True, 0)
