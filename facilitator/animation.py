"""Talking gestures: head and antenna motion while the robot speaks.

Two layers, both active only while a prompt is playing:

1. Daemon "wobbling" (Reachy Mini SDK): the daemon analyses the sound it plays and adds
   small audio-driven head offsets (pitch/yaw/roll), so the head moves with the voice.
   Only works when the sound plays on the robot (speech output "robot").
2. speech_gesture() below: a slow head roll/pitch sway and antenna wiggles, sent by
   robot_io.Robot.say() at GESTURE_HZ.

STUDY RULES (controlled variable "same robot behaviour in both conditions"):
- Deterministic: the gesture depends only on the prompt id (seed) and the time since the
  prompt started, so the same prompt gets the same motion in every round and condition.
- Never touches yaw: the head keeps facing the seat it turned to, and the robot returns
  to exactly its listening pose (same yaw, roll = pitch = 0, base antennas) before the
  microphones are read again. Detection and calibration are therefore unaffected.
- Motion happens only while the robot is speaking, when detection ignores the
  microphones anyway (robot_speaking = 1), so motor noise cannot count as speech.
"""

import math
import zlib
from typing import Tuple

GESTURE_HZ = 25.0      # how often Robot.say() sends a new target while speaking
RAMP_S = 0.35          # fade the gesture in/out so it starts and ends at the rest pose

# amplitudes at gesture_scale = 1.0 (degrees) and frequencies (Hz)
HEAD_ROLL_DEG, HEAD_ROLL_HZ = 6.0, 0.35
HEAD_PITCH_DEG, HEAD_PITCH_HZ = 3.0, 0.7
ANT_SLOW_DEG, ANT_SLOW_HZ = 18.0, 1.1
ANT_FAST_DEG, ANT_FAST_HZ = 7.0, 2.3


def prompt_seed(prompt_id: str) -> int:
    """Stable seed per prompt (same on every computer and Python run)."""
    return zlib.crc32(prompt_id.encode("utf-8"))


def _phases(seed: int) -> Tuple[float, float, float, float]:
    """Four phases in [0, 2*pi) derived from the seed, so prompts differ but repeat exactly."""
    return tuple(((seed >> (8 * k)) & 0xFF) / 256.0 * 2 * math.pi for k in range(4))  


def envelope(t: float, duration: float, ramp_s: float = RAMP_S) -> float:
    """0 at the start and end of the prompt, 1 in the middle; smooth (raised cosine) ramps."""
    if duration <= 0 or t <= 0 or t >= duration:
        return 0.0
    ramp = min(ramp_s, duration / 2)
    edge = min(t, duration - t)
    if edge >= ramp:
        return 1.0
    return 0.5 - 0.5 * math.cos(math.pi * edge / ramp)


def speech_gesture(t: float, duration: float, seed: int, scale: float = 1.0
                   ) -> Tuple[float, float, float, float]:
    """Gesture offsets at time t (s) into a prompt of the given duration.

    Returns (head_roll_deg, head_pitch_deg, antenna_right_deg, antenna_left_deg),
    all offsets from the rest pose; all exactly 0 at t <= 0 and t >= duration.
    """
    e = envelope(t, duration) * scale
    if e == 0.0:
        return 0.0, 0.0, 0.0, 0.0
    p_roll, p_pitch, p_slow, p_fast = _phases(seed)
    roll = HEAD_ROLL_DEG * math.sin(2 * math.pi * HEAD_ROLL_HZ * t + p_roll)
    pitch = HEAD_PITCH_DEG * math.sin(2 * math.pi * HEAD_PITCH_HZ * t + p_pitch)
    slow = ANT_SLOW_DEG * math.sin(2 * math.pi * ANT_SLOW_HZ * t + p_slow)
    fast = ANT_FAST_DEG * math.sin(2 * math.pi * ANT_FAST_HZ * t + p_fast)
    # antennas mostly mirror each other (both swing outwards/inwards), with a little independent flutter
    return e * roll, e * pitch, e * (slow + fast), e * (-slow + fast)
