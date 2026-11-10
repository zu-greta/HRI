"""Start the Reachy Mini daemon for the REAL robot (Lite, plugged in by USB).

Same as `reachy-mini-daemon`, but it first fixes the "No module named 'gi'" error
that can happen on macOS.

    python run_robot.py                      # find the robot's USB port automatically
    python run_robot.py --serialport /dev/tty.usbmodemXXXX   # if it is not found

Differences from run_sim.py (simulator):
  * no --sim, and plain `python` is fine (mjpython is only needed for the 3D window);
  * media stays ON. The microphone direction readings (/api/state/doa) come from
    the media/audio part of the daemon: with --no-media the robot cannot tell who
    is speaking. This launcher therefore refuses --no-media.

Not needed for a Reachy Mini Wireless: its daemon already runs on the robot.
"""

import sys

from facilitator.robot_io import _ensure_gi

_ensure_gi()  # must run before the SDK is imported

from reachy_mini.daemon.app.main import main  # noqa: E402

args = sys.argv[1:]
for forbidden in ("--sim", "--mockup-sim"):
    if forbidden in args:
        sys.exit(f"{forbidden} starts a simulator - use run_sim.py for that.")
if "--no-media" in args:
    sys.exit("--no-media would switch off the microphones (no speaker direction). Remove it for the study.")
print("[run_robot] starting:", "reachy-mini-daemon " + " ".join(args))
sys.argv = [sys.argv[0]] + args
main()