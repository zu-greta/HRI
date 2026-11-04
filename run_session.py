"""Run one facilitation session (one round of the study).

    python run_session.py                                  # baseline, simulator, laptop microphone
    python run_session.py --condition adaptive --source scripted   # simulator, simulated group
    python run_session.py --target lite --group G01 --round 1 --topic 1 --order A \
                          --condition baseline --quiet-seat 2       # a real study round (USB robot)

For a quick look at a whole session without any setup: python sim_scenario.py --no-robot --fast

The robot listens after each question and speaks again once the group goes quiet.
It hears through its own microphones on the real robot, and through this computer's
microphone in the simulator (which has none). --source overrides this.
"""

import argparse
import subprocess
import time
import zlib
from pathlib import Path

from facilitator.config import Config
from facilitator.detection_config import DetectionConfig  
from facilitator.listener import ParticipationListener  
from facilitator.seats import load_seat_azimuths  
from facilitator.sim_sources import MicModel, ScriptedSource  
from facilitator.ticklog import TickLog  
from facilitator.logger import SessionLog
from facilitator.policies import make_policy
from facilitator.robot_io import TARGETS, Robot
from facilitator.session import run_session
from facilitator.sources import KeyboardSource, LaptopMicSource, NullSource, RobotDoASource, SpeakerSource
from facilitator.speech import Speaker


def make_source(choice: str, target: str, base_url: str, cfg: Config, robot=None) -> SpeakerSource:
    """Create the source for --source, stopping with a clear message if it cannot work."""
    if choice == "auto":
        choice = "laptop" if target == "sim" else "robot"

    if choice == "robot":
        source = RobotDoASource(base_url)
        if not source.wait_until_ready():
            source.close()
            raise SystemExit(f"No microphone readings from {base_url}/api/state/doa. The simulator has no "
                             "microphones (use --source laptop). On a real robot: do not start the daemon with "
                             "--no-media, and check the microphone firmware is 2.1.0 or newer.")
        print("Speech input: robot microphones.")
        return source

    if choice == "laptop":
        print("Speech input: this computer's microphone. Stay quiet for a second while it measures the room ...")
        try:
            source = LaptopMicSource(cfg.mic_threshold_ratio, cfg.mic_min_level)
        except Exception as exc:  # noqa: BLE001 - missing package, no microphone, permission denied
            raise SystemExit(f"Could not open this computer's microphone: {exc}\n"
                             "Run pip install -r requirements.txt, check the microphone permission, "
                             "or use --source keyboard.") from exc
        print(f"Room level {source.noise_level:.4f}; louder than {source.threshold:.4f} counts as speech.")
        return source

    if choice == "scripted":  # simulated group, for testing detection in the simulator
        turns, t = [], 0.0
        for seat, length in [(0, 8), (1, 3), (2, 2), (0, 6), (1, 3), (0, 7), (2, 1.5), (1, 2)] * 10:
            turns.append((t, t + length, seat))
            t += length + 1.0
        print("Speech input: scripted group (seat 1 talks most, seat 3 least), simulated microphones.")
        head_yaw = robot.head_yaw_deg if robot is not None else (lambda: 0.0)  # mics turn with the head
        return ScriptedSource(turns, cfg.seat_azimuths_deg, time.monotonic, MicModel(), head_yaw_deg=head_yaw)

    if choice == "keyboard":
        print("Speech input: keyboard. Press or hold 1/2/3 in this terminal to act as that seat speaking.")
        head_yaw = robot.head_yaw_deg if robot is not None else (lambda: 0.0)  # mics turn with the head
        return KeyboardSource(cfg.seat_azimuths_deg, head_yaw_deg=head_yaw)

    print("Speech input: none. The robot cannot hear anyone.")
    return NullSource()


def code_version() -> str:
    """Short git commit of this code (+ '-dirty' if there are uncommitted changes), for the log."""
    root = Path(__file__).resolve().parent
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True,
                             timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=root,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return (rev or "unknown") + ("-dirty" if dirty else "")
    except Exception:  # noqa: BLE001 - git missing
        return "unknown"


def main() -> None:
    cfg = Config()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--group", default="TEST")
    p.add_argument("--condition", choices=("baseline", "adaptive"), default="baseline")
    p.add_argument("--target", choices=TARGETS, default="sim")
    p.add_argument("--host", default=cfg.host, help="Wireless robot hostname or IP")
    p.add_argument("--turns", type=int, default=cfg.n_turns)
    p.add_argument("--silence", type=float, default=cfg.silence_s,
                   help="seconds of silence after someone spoke before the next turn")
    p.add_argument("--no-response", type=float, default=cfg.no_response_s,
                   help="seconds to wait for anyone to start speaking before the next turn")
    p.add_argument("--max-listen", type=float, default=cfg.max_listen_s,
                   help="longest a turn can last, even if someone is still talking")
    p.add_argument("--source", choices=("auto", "robot", "laptop", "keyboard", "scripted", "none"), default="auto",
                   help="how the robot hears speech. auto: laptop microphone in the simulator, "
                        "robot microphones on the real robot")
    p.add_argument("--seed", type=int, default=None,
                   help="random seed for the baseline (default: derived from --group and --round, reproducible)")
    # study bookkeeping. Logged only.
    p.add_argument("--topic", type=int, choices=(1, 2), default=cfg.topic, help="question set for this round")
    p.add_argument("--round", type=int, choices=(1, 2), default=1, help="first or second round of this group")
    p.add_argument("--order", choices=("A", "B", "-"), default="-", help="A: random first; B: balancing first")
    p.add_argument("--quiet-seat", type=int, choices=(0, 1, 2, 3), default=0,
                   help="seat of the self-reported quiet participant (0 = not recorded). Logged only.")
    p.add_argument("--baseline", choices=("balanced", "uniform"), default=cfg.baseline,
                   help="baseline randomisation: balanced (default, study) or uniform (see PROJECT_OVERVIEW.md)")
    p.add_argument("--speech", choices=("auto", "robot", "laptop", "silent"), default="auto",
                   help="where the voice plays. auto: laptop in the simulator, robot speaker on the real robot")
    # choose detection methods (defaults: our method; the alternatives exist for comparison)
    p.add_argument("--attributor", choices=("hmm", "nearest"), help="who-is-speaking method (default: hmm)")
    p.add_argument("--estimator", choices=("turns_decay", "cumulative"), help="activity measure (default: turns_decay)")
    args = p.parse_args()
    cfg.n_turns, cfg.host, cfg.topic, cfg.baseline = args.turns, args.host, args.topic, args.baseline
    # a different but reproducible random order for every group and round
    cfg.seed = args.seed if args.seed is not None else zlib.crc32(f"{args.group}-R{args.round}".encode())
    cfg.silence_s, cfg.no_response_s, cfg.max_listen_s = args.silence, args.no_response, args.max_listen

    # seats: calibrated seats.json if present, otherwise placeholders
    cfg.seat_azimuths_deg, placeholder = load_seat_azimuths()
    if placeholder:
        print(f"WARNING: using PLACEHOLDER seat angles {cfg.seat_azimuths_deg} - calibrate before the study "
              "(run_calibration.py, see PROJECT_OVERVIEW.md).")
        if args.target != "sim":
            print("         A study round with placeholder seats is NOT valid data.")
    det = DetectionConfig.load()
    det.attributor = args.attributor or det.attributor
    det.estimator = args.estimator or det.estimator
    policy = make_policy(args.condition, len(cfg.seat_azimuths_deg), cfg.shuffle_each_round, cfg.seed, det,
                         baseline=cfg.baseline)
    robot = Robot(args.target, cfg.host, cfg.move_duration_s, cfg.body_share)
    output = args.speech if args.speech != "auto" else ("laptop" if args.target == "sim" else "robot")
    # real robot: never synthesise missing prompts on the fly (the voice is a controlled variable)
    robot.speaker = Speaker(output, robot.base_url, auto_generate=(args.target == "sim"))
    log = SessionLog(f"{args.group}_R{args.round}_T{args.topic}", args.condition, cfg.log_dir)  
    log.log("study_info", detail=f"group={args.group} round={args.round} topic={args.topic} order={args.order} "
                                 f"condition={args.condition} quiet_seat={args.quiet_seat} "
                                 f"baseline={cfg.baseline} seed={cfg.seed}")

    print(f"Connecting to {args.target} ...")
    robot.connect()
    robot.speaker.prepare()  # checks prompts/*.wav exist (and uploads them to a real robot)
    print(f"Voice output: {output}")
    log.log("versions", detail=f"code={code_version()} prompt_audio={robot.speaker.audio_hash}")

    source = NullSource()
    listener = ParticipationListener.from_config(cfg.seat_azimuths_deg, det)  
    ticklog = TickLog(log.path) if det.log_ticks else None  
    log.log("detection_setup", detail=f"attributor={det.attributor} estimator={det.estimator} "
                                      f"seats={cfg.seat_azimuths_deg} placeholder_seats={placeholder}")
    try:
        source = make_source(args.source, args.target, robot.base_url, cfg, robot)
        tracker = run_session(robot, policy, source, cfg, log, listener=listener, ticklog=ticklog)
        print(f"\nDone. Times addressed per seat: {tracker.times_addressed}")
        print(f"Robot's activity estimate per seat: {[round(a, 1) for a in listener.activity()]}")
    finally:
        robot.close()
        source.close()
        log.close()
        if ticklog is not None:
            ticklog.close()
        print(f"Log saved to {log.path}" + (f" (+ {ticklog.path.name})" if ticklog else ""))


if __name__ == "__main__":
    main()
