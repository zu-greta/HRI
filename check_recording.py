"""Test the recording microphone before participants arrive

    python check_recording.py                  # default input (the laptop microphone)
    python check_recording.py --list           # show all microphones
    python check_recording.py --device "USB"   # a specific microphone (part of its name)
"""

import argparse
import tempfile
import time
from pathlib import Path

from facilitator.recorder import AudioRecorder


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device", help="microphone name (or part of it); default: system input")
    p.add_argument("--list", action="store_true", help="list microphones and exit")
    p.add_argument("--seconds", type=float, default=5.0)
    args = p.parse_args()

    import sounddevice as sd

    if args.list:
        print(sd.query_devices())
        return
    folder = Path(tempfile.mkdtemp(prefix="rec_check_"))
    rec = AudioRecorder(folder / "check.csv", device=args.device)
    try:
        rec.start()
    except Exception as exc:  
        raise SystemExit(f"Could not open the microphone: {exc}\n"
                         "macOS: System Settings > Privacy & Security > Microphone -> allow your terminal.")
    print(f"Recording {args.seconds:.0f} s - speak from a participant's chair ...")
    time.sleep(args.seconds)
    rec.stop()
    print(f"Saved {rec.wav_path} ({rec.seconds:.1f} s), peak level {rec.peak:.2f}")
    if rec.seconds < args.seconds * 0.8:
        print("PROBLEM: less audio than expected - is the microphone working?")
    elif rec.peak < 0.02:
        print("PROBLEM: almost silent - wrong microphone, muted, or no permission?")
    elif rec.peak > 0.98:
        print("WARNING: very loud (clipping) - lower the input volume or move the laptop back.")
    else:
        print("OK - listen to the file once to be sure.")


if __name__ == "__main__":
    main()
