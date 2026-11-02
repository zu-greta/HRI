"""Check that everything is ready. Run it after setup and whenever something breaks.

    python check_setup.py                    # simulator / Lite on this computer
    python check_setup.py --target wireless  # Wireless robot on the network
"""

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version

OK, BAD, WARN = "[ OK ]", "[FAIL]", "[WARN]"
problems = 0


def report(ok: bool, msg: str, warn_only: bool = False) -> None:
    global problems
    print(f"{OK if ok else (WARN if warn_only else BAD)} {msg}")
    if not ok and not warn_only:
        problems += 1


p = argparse.ArgumentParser()
p.add_argument("--target", choices=("sim", "lite", "wireless"), default="sim")
p.add_argument("--host", default="reachy-mini.local")
args = p.parse_args()

# 1. Python version
v = sys.version_info
report((3, 11) <= (v.major, v.minor) <= (3, 13), f"Python {v.major}.{v.minor}.{v.micro} (need 3.11-3.13)")

# 2. Packages
try:
    sdk_version = version("reachy-mini")
    report(True, f"reachy-mini {sdk_version} installed")
except PackageNotFoundError:
    sdk_version = None
    report(False, "reachy-mini not installed -> run the setup script / pip install -r requirements.txt")
for pkg in ("requests", "numpy", "pytest"):
    try:
        report(True, f"{pkg} {version(pkg)}")
    except PackageNotFoundError:
        report(False, f"{pkg} missing -> pip install -r requirements.txt")

# 3. SDK imports (includes the macOS 'gi' fix)
try:
    from facilitator.robot_io import _ensure_gi

    _ensure_gi()
    from reachy_mini import ReachyMini  # noqa: F401

    report(True, "Reachy Mini SDK imports")
except Exception as exc:  # noqa: BLE001
    report(False, f"Reachy Mini SDK import failed: {exc}")

# 4. Daemon reachable + same version as the SDK
import requests  # noqa: E402

base = f"http://{args.host if args.target == 'wireless' else 'localhost'}:8000"
try:
    status = requests.get(f"{base}/api/daemon/status", timeout=3).json()
    daemon_version = status.get("version")
    report(True, f"daemon reachable at {base} (state: {status.get('state')})")
    report(daemon_version == sdk_version,
           f"daemon version {daemon_version} vs SDK {sdk_version}"
           + ("" if daemon_version == sdk_version else
              " -> set the SAME version in requirements.txt and re-run setup"),
           warn_only=True)
    doa = requests.get(f"{base}/api/state/doa", timeout=3).json()
    if doa is None:
        report(False, "microphone direction: not available (normal in the simulator; "
                      "on the robot check mic firmware >= 2.1.0)", warn_only=True)
    else:
        report(True, f"microphone direction available: {doa}")
except requests.RequestException:
    report(False, f"no daemon at {base} -> start the simulator in Reachy Mini Control "
                  "(Simulation -> Start), or `reachy-mini-daemon --sim`")

print("\nAll good!" if problems == 0 else f"\n{problems} problem(s) to fix (see [FAIL] lines).")
sys.exit(1 if problems else 0)
