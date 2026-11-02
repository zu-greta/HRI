"""Everything that talks to the robot: connect, turn to a seat, speak.

The same code runs on the simulator and the real robot; only --target changes.
"""

import math
from typing import Optional

TARGETS = ("sim", "lite", "wireless")


def _ensure_gi() -> None:
    """macOS fix for "No module named 'gi'" (GStreamer bindings) before importing the SDK."""
    try:
        import gi  # noqa: F401
    except ImportError:
        try:
            import gstreamer_libs

            gstreamer_libs.setup_python_environment()
        except ImportError:
            pass


class Robot:
    def __init__(self, target: str = "sim", host: str = "reachy-mini.local",
                 move_duration_s: float = 0.8, body_share: float = 0.6):
        if target not in TARGETS:
            raise ValueError(f"target must be one of {TARGETS}")
        self.target, self.host = target, host
        self.move_duration_s, self.body_share = move_duration_s, body_share
        self.mini = None
        self.speaker = None  # set by the caller: facilitator.speech.Speaker

    @property
    def base_url(self) -> str:
        """REST API of the daemon (used later for sound direction and playing sounds)."""
        return f"http://{self.host if self.target == 'wireless' else 'localhost'}:8000"

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        _ensure_gi()
        from reachy_mini import ReachyMini

        if self.target == "wireless":
            kwargs = dict(connection_mode="network", host=self.host)
        else:
            kwargs = dict(connection_mode="localhost_only")
        # no_media: our script does not grab cameras/microphones itself.
        self.mini = ReachyMini(media_backend="no_media", **kwargs)
        self.mini.__enter__()

    def close(self) -> None:
        if self.mini is not None:
            try:
                self.face_group()
            finally:
                self.mini.__exit__(None, None, None)
                self.mini = None

    # ------------------------------------------------------------- actions
    def turn_to(self, azimuth_deg: float, antennas_deg=(0.0, 0.0)) -> None:
        """Face a direction (+ = robot's left). Body does part of the turn, head the rest.

        The head pose is given in world coordinates, so yaw=azimuth makes the head
        face the seat while the body rotates body_share of the way (keeps the
        head-body difference small, max allowed is 65 deg).
        """
        from reachy_mini.utils import create_head_pose

        self.mini.goto_target(
            head=create_head_pose(yaw=azimuth_deg, degrees=True),
            antennas=[math.radians(a) for a in antennas_deg],
            body_yaw=math.radians(azimuth_deg * self.body_share),
            duration=self.move_duration_s,
        )

    def face_group(self) -> None:
        self.turn_to(0.0)

    def say(self, prompt_id: str) -> float:
        """Speak a pre-recorded prompt (see speech.py). Blocks until finished."""
        return self.speaker.say(prompt_id)

    def is_speaking(self) -> bool:
        return self.speaker.is_speaking()

    def head_yaw_deg(self) -> Optional[float]:
        """Current head yaw in world coordinates (for checks and later for DoA correction)."""
        pose = self.mini.get_current_head_pose()
        return math.degrees(math.atan2(pose[1, 0], pose[0, 0]))
