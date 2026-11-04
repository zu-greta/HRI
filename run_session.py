"""Run one facilitation session.

    python run_session.py                                  # baseline, simulator, short demo
    python run_session.py --group G01 --condition baseline --turns 6 --silence 3
    python run_session.py --target lite                    # later: real robot on USB

The robot listens after each question and speaks again once the group goes quiet.
It hears through its own microphones on the real robot, and through this computer's
microphone in the simulator (which has none). --source overrides this.
"""

import argparse

from facilitator.config import Config
from facilitator.logger import SessionLog
from facilitator.policies import make_policy
from facilitator.robot_io import TARGETS, Robot
from facilitator.session import run_session
from facilitator.sources import KeyboardSource, LaptopMicSource, NullSource, RobotDoASource, SpeakerSource
from facilitator.speech import Speaker


def make_source(choice: str, target: str, base_url: str, cfg: Config) -> SpeakerSource:
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

    if choice == "keyboard":
        print("Speech input: keyboard. Press or hold 1/2/3 in this terminal to act as that seat speaking.")
        return KeyboardSource(cfg.seat_azimuths_deg)

    print("Speech input: none. The robot cannot hear anyone.")
    return NullSource()


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
    p.add_argument("--source", choices=("auto", "robot", "laptop", "keyboard", "none"), default="auto",
                   help="how the robot hears speech. auto: laptop microphone in the simulator, "
                        "robot microphones on the real robot")
    p.add_argument("--seed", type=int, default=cfg.seed)
    p.add_argument("--speech", choices=("auto", "robot", "laptop", "silent"), default="auto",
                   help="where the voice plays. auto: laptop in the simulator, robot speaker on the real robot")
    args = p.parse_args()
    cfg.n_turns, cfg.seed, cfg.host = args.turns, args.seed, args.host
    cfg.silence_s, cfg.no_response_s, cfg.max_listen_s = args.silence, args.no_response, args.max_listen

    policy = make_policy(args.condition, len(cfg.seat_azimuths_deg), cfg.shuffle_each_round, cfg.seed)
    robot = Robot(args.target, cfg.host, cfg.move_duration_s, cfg.body_share)
    output = args.speech if args.speech != "auto" else ("laptop" if args.target == "sim" else "robot")
    robot.speaker = Speaker(output, robot.base_url)
    log = SessionLog(args.group, args.condition, cfg.log_dir)

    print(f"Connecting to {args.target} ...")
    robot.connect()
    robot.speaker.prepare()  # checks prompts/*.wav exist (and uploads them to a real robot)
    print(f"Voice output: {output}")

    source = NullSource()
    try:
        source = make_source(args.source, args.target, robot.base_url, cfg)
        tracker = run_session(robot, policy, source, cfg, log)
        print(f"\nDone. Times addressed per seat: {tracker.times_addressed}")
    finally:
        robot.close()
        source.close()
        log.close()
        print(f"Log saved to {log.path}")


if __name__ == "__main__":
    main()
