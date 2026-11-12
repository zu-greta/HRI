"""Everything that talks to the robot: connect, turn to a seat, speak.

The same code runs on the simulator and the real robot; only --target changes.
"""

import math
import time
from typing import Callable, Optional

import requests

from .animation import GESTURE_HZ, prompt_seed, speech_gesture

TARGETS = ("sim", "lite", "wireless")


def _ensure_gi() -> None:
    """macOS fix for "No module named 'gi'" (GStreamer bindings) before importing the SDK."""
    try:
        import gi  
    except ImportError:
        try:
            import gstreamer_libs

            gstreamer_libs.setup_python_environment()
        except ImportError:
            pass


def _ipv4(host: str) -> str:
    """IPv4 address for a hostname such as reachy-mini.local (the host itself if lookup fails)
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
        # recovery settings and reporting
        self.recover_wait_s, self.reconnect_attempts, self.reconnect_pause_s = 3.0, 10, 2.0
        self.connection_problems = 0
        self.on_event: Callable[[str, str], None] = lambda event, detail: None  # e.g. log.log(event, detail=...)

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
        except Exception as exc:  
            if on:
                print(f"NOTE: could not enable head wobbling ({exc}); antenna/head gestures still run.")
            return False

    def close(self) -> None:
        """[ROBUSTNESS] Never raises: a failed clean-up must not hide the real error or stop saving data."""
        if self.mini is None:
            return
        try:
            self.face_group()
        except Exception as exc: 
            print(f"   (could not turn back to the group while closing: {exc})")
        if self.wobbling:
            self.wobbling = self._set_wobbling(False)
        try:
            self.mini.__exit__(None, None, None)
        except Exception:  
            pass
        self.mini = None

    # ------------------------------------------------------------- robustness
    def _send(self, method: str, *args, **kwargs):
        """Call a ReachyMini method; on a lost connection recover, then retry once."""
        try:
            return getattr(self.mini, method)(*args, **kwargs)
        except ConnectionError as exc:
            self.connection_problems += 1
            self.on_event("connection_lost", f"{method}: {exc}")
            print(f"   [connection lost: {exc} - trying to recover]")
            self._recover()
            return getattr(self.mini, method)(*args, **kwargs)

    def _stream_alive(self) -> bool:
        try:
            return bool(self.mini.client.is_connected())  # waits up to ~1 s for data from the robot
        except Exception: 
            return False

    def _recover(self) -> None:
        # 1) short Wi-Fi gap: the data stream usually resumes by itself
        end = time.monotonic() + self.recover_wait_s
        while time.monotonic() < end:
            if self._stream_alive():
                time.sleep(1.1)  # let the SDK's own 1 s liveness check see the data again
                self.on_event("connection_recovered", "stream resumed")
                print("   [connection recovered]")
                return
            time.sleep(0.2)
        # 2) the connection really closed: open a new one
        for attempt in range(1, self.reconnect_attempts + 1):
            try:
                try:
                    self.mini.__exit__(None, None, None)
                except Exception: 
                    pass
                self.connect()
                self.on_event("connection_recovered", f"reconnected (attempt {attempt})")
                print(f"   [reconnected after {attempt} attempt(s)]")
                return
            except Exception as exc: 
                print(f"   [reconnect attempt {attempt}/{self.reconnect_attempts} failed: {exc}]")
                time.sleep(self.reconnect_pause_s)
        self.on_event("connection_failed", "gave up")
        raise ConnectionError(f"Lost the robot and could not reconnect to {self.base_url}.")

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

        self._send(  # in case of fail
            "goto_target",
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
        except Exception as exc:  # a gesture must never stop the session
            print(f"   (gesture skipped: {exc})")
        finally:
            self.speaker.wait()
            self._back_to_listening_pose()
        return duration

    def _back_to_listening_pose(self) -> None:
        """Exactly the pose turn_to() left the robot in (same yaw, level head, base antennas)."""
        from reachy_mini.utils import create_head_pose

        try:
            self._send(  # recovers the link before the next turn
                "goto_target",
                head=create_head_pose(yaw=self._yaw_deg, degrees=True),
                antennas=[math.radians(a) for a in self._antennas_deg],
                body_yaw=math.radians(self._yaw_deg * self.body_share),
                duration=0.25,
            )
        except Exception as exc:  
            print(f"   (could not settle after gesture: {exc})")

    def is_speaking(self) -> bool:
        return self.speaker.is_speaking()

    def head_yaw_deg(self) -> Optional[float]:
        """Current head yaw in the room frame, degrees, + = robot's left.

        Used every tick to turn the head-relative microphone angle into a room direction.
        """
        pose = self.mini.get_current_head_pose()
        return math.degrees(math.atan2(pose[1, 0], pose[0, 0]))