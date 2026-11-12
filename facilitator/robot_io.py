"""Everything that talks to the robot: connect, turn to a seat, speak.

The same code runs on the simulator and the real robot; only --target changes.
"""

import math
import time
from typing import Optional

import requests

from .animation import GESTURE_HZ, prompt_seed, speech_gesture

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


def _ipv4(host: str) -> str:
    """IPv4 address for a hostname such as reachy-mini.local (the host itself if lookup fails).

    On Windows, reachy-mini.local also resolves to an IPv6 link-local address (fe80::...),
    which is tried first; the SDK's websocket then hangs until it times out, although plain
    HTTP to the same name works. Connecting by IPv4 avoids that (and is harmless on macOS).
    """
    import socket

    try:
        return socket.getaddrinfo(host, 8000, socket.AF_INET, socket.SOCK_STREAM)[0][4][0]
    except OSError:
        return host


class Robot:
    def __init__(self, target: str = "sim", host: str = "reachy-mini.local",
                 move_duration_s: float = 0.8, body_share: float = 0.6,
                 animate: bool = False, gesture_scale: float = 1.0):
        if target not in TARGETS:
            raise ValueError(f"target must be one of {TARGETS}")
        self.target, self.host = target, host
        self.move_duration_s, self.body_share = move_duration_s, body_share
        # talking gestures (animation.py); off by default so calibration/check scripts stay still
        self.animate, self.gesture_scale = animate, gesture_scale
        self.wobbling = False  # daemon's audio-driven head motion, switched on in connect()
        self.mini = None
        self.speaker = None  # set by the caller: facilitator.speech.Speaker
        # the listening pose the robot returns to after every gesture
        self._yaw_deg = 0.0
        self._antennas_deg = (0.0, 0.0)

    @property
    def base_url(self) -> str:
        """REST API of the daemon (microphone direction /api/state/doa, sound upload and playback)."""
        return f"http://{self.host if self.target == 'wireless' else 'localhost'}:8000"

    # ------------------------------------------------------------- lifecycle
    def connect(self) -> None:
        _ensure_gi()
        from reachy_mini import ReachyMini

        if self.target == "wireless":
            kwargs = dict(connection_mode="network", host=_ipv4(self.host))
        else:
            kwargs = dict(connection_mode="localhost_only")
        # no_media: our script does not grab cameras/microphones itself.
        self.mini = ReachyMini(media_backend="no_media", **kwargs)
        self.mini.__enter__()
        if self.animate:
            self.wobbling = self._set_wobbling(True)

    def _set_wobbling(self, on: bool) -> bool:
        """Daemon-side head wobbling while it plays a sound. Best effort: cosmetic only."""
        try:
            r = requests.post(f"{self.base_url}/api/media/wobbling/{'enable' if on else 'disable'}", timeout=3)
            r.raise_for_status()
            return on
        except Exception as exc:  # noqa: BLE001
            if on:
                print(f"NOTE: could not enable head wobbling ({exc}); antenna/head gestures still run.")
            return False

    def close(self) -> None:
        if self.mini is not None:
            try:
                self.face_group()
            finally:
                if self.wobbling:
                    self.wobbling = self._set_wobbling(False)
                self.mini.__exit__(None, None, None)
                self.mini = None

    # ------------------------------------------------------------- actions
    def turn_to(self, azimuth_deg: float, antennas_deg=(0.0, 0.0)) -> None:
        """Face a direction (+ = robot's left). Body does part of the turn, head the rest.

        The head pose is given in world coordinates, so yaw=azimuth makes the head
        face the seat while the body rotates body_share of the way (keeps the
        head-body difference small, max allowed is 65 deg).
        goto_target is expected to block for duration (verify on the real robot); the
        session does not read the microphones while the robot moves.
        """
        from reachy_mini.utils import create_head_pose

        self.mini.goto_target(
            head=create_head_pose(yaw=azimuth_deg, degrees=True),
            antennas=[math.radians(a) for a in antennas_deg],
            body_yaw=math.radians(azimuth_deg * self.body_share),
            duration=self.move_duration_s,
        )
        self._yaw_deg, self._antennas_deg = azimuth_deg, tuple(antennas_deg)

    def face_group(self) -> None:
        self.turn_to(0.0)

    def say(self, prompt_id: str) -> float:
        """Speak a pre-recorded prompt (see speech.py). Blocks until finished.

        With animate=True the head sways and the antennas move while the sound plays
        (animation.py), then the robot returns to exactly its listening pose.
        """
        if not self.animate or self.mini is None:
            return self.speaker.say(prompt_id)

        from reachy_mini.utils import create_head_pose

        duration = self.speaker.start(prompt_id)
        seed, t0, period = prompt_seed(prompt_id), time.monotonic(), 1.0 / GESTURE_HZ
        base_r, base_l = self._antennas_deg
        try:
            while (t := time.monotonic() - t0) < duration:
                roll, pitch, a_r, a_l = speech_gesture(t, duration, seed, self.gesture_scale)
                self.mini.set_target(
                    head=create_head_pose(roll=roll, pitch=pitch, yaw=self._yaw_deg, degrees=True),
                    antennas=[math.radians(base_r + a_r), math.radians(base_l + a_l)],
                )
                time.sleep(period)
        except Exception as exc:  # noqa: BLE001  a gesture must never stop the session
            print(f"   (gesture skipped: {exc})")
        finally:
            self.speaker.wait()
            self._back_to_listening_pose()
        return duration

    def _back_to_listening_pose(self) -> None:
        """Exactly the pose turn_to() left the robot in (same yaw, level head, base antennas)."""
        from reachy_mini.utils import create_head_pose

        try:
            self.mini.goto_target(
                head=create_head_pose(yaw=self._yaw_deg, degrees=True),
                antennas=[math.radians(a) for a in self._antennas_deg],
                body_yaw=math.radians(self._yaw_deg * self.body_share),
                duration=0.25,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"   (could not settle after gesture: {exc})")

    def is_speaking(self) -> bool:
        return self.speaker.is_speaking()

    def head_yaw_deg(self) -> Optional[float]:
        """Current head yaw in the room frame, degrees, + = robot's left.

        Used every tick to turn the head-relative microphone angle into a room direction.
        VERIFY ON THE REAL ROBOT: after turn_to(+50) this must read about +50.
        """
        pose = self.mini.get_current_head_pose()
        return math.degrees(math.atan2(pose[1, 0], pose[0, 0]))
