"""Start the Reachy Mini MuJoCo simulator (fixes "No module named 'gi'" on macOS).

    macOS:          mjpython run_sim.py
    Windows/Linux:  python run_sim.py

By default it starts in a light mode suited to this project:
    --no-media              no camera/mic/speaker pipeline (the simulator has no
                            microphone array anyway; avoids camera errors; less CPU)
    --no-wake-up-on-start   skip the start-up animation and sound (faster restarts)
Use --full to start the simulator exactly as the official command does.
Any other option is passed through, e.g.:  mjpython run_sim.py --scene minimal
"""

import sys

from facilitator.robot_io import _ensure_gi

_ensure_gi()  # must run before the SDK is imported

from reachy_mini.daemon.app.main import main  

args = sys.argv[1:]
if "--full" in args:
    args.remove("--full")
else:
    for flag in ("--no-media", "--no-wake-up-on-start"):
        if flag not in args:
            args.append(flag)
if "--sim" not in args:
    args.append("--sim")
print("[run_sim] starting:", "reachy-mini-daemon " + " ".join(args))
sys.argv = [sys.argv[0]] + args
main()
