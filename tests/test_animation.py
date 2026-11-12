"""Talking gestures: start/end at rest, deterministic per prompt, bounded."""

import pytest

from facilitator.animation import (ANT_FAST_DEG, ANT_SLOW_DEG, HEAD_PITCH_DEG, HEAD_ROLL_DEG, envelope,
                                   prompt_seed, speech_gesture)


def test_gesture_is_zero_at_start_and_end():
    seed = prompt_seed("t1_q1")
    assert speech_gesture(0.0, 3.0, seed) == (0.0, 0.0, 0.0, 0.0)
    assert speech_gesture(3.0, 3.0, seed) == (0.0, 0.0, 0.0, 0.0)
    assert speech_gesture(5.0, 3.0, seed) == (0.0, 0.0, 0.0, 0.0)
    assert all(abs(v) < 0.5 for v in speech_gesture(0.01, 3.0, seed))  # ramps in smoothly


def test_same_prompt_same_motion_in_every_round():
    a = [speech_gesture(t / 10, 4.0, prompt_seed("intro")) for t in range(40)]
    b = [speech_gesture(t / 10, 4.0, prompt_seed("intro")) for t in range(40)]
    assert a == b
    assert a != [speech_gesture(t / 10, 4.0, prompt_seed("outro")) for t in range(40)]  # prompts differ


def test_gesture_is_bounded_and_scales():
    seed = prompt_seed("t2_q4")
    for k in range(200):
        roll, pitch, ar, al = speech_gesture(k / 20, 10.0, seed)
        assert abs(roll) <= HEAD_ROLL_DEG + 1e-9
        assert abs(pitch) <= HEAD_PITCH_DEG + 1e-9
        assert abs(ar) <= ANT_SLOW_DEG + ANT_FAST_DEG + 1e-9
        assert abs(al) <= ANT_SLOW_DEG + ANT_FAST_DEG + 1e-9
    assert speech_gesture(5.0, 10.0, seed, scale=0.0) == (0.0, 0.0, 0.0, 0.0)
    full, half = speech_gesture(5.0, 10.0, seed), speech_gesture(5.0, 10.0, seed, scale=0.5)
    assert half == pytest.approx(tuple(v / 2 for v in full))


def test_envelope_short_prompt():
    assert envelope(0.25, 0.5) == pytest.approx(1.0)
    assert 0.0 < envelope(0.1, 0.5) < 1.0
