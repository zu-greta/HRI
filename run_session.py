"""Run one facilitation session.

    python run_session.py                                  # baseline, simulator, short demo
    python run_session.py --group G01 --condition baseline --turns 6 --interval 5
    python run_session.py --target lite                    # later: real robot on USB
"""

import argparse

from facilitator.config import Config
from facilitator.logger import SessionLog
from facilitator.policies import make_policy
from facilitator.robot_io import TARGETS, Robot
from facilitator.session import run_session
from facilitator.sources import NullSource
from facilitator.speech import Speaker


def main() -> None:
    cfg = Config()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--group", default="TEST")
    p.add_argument("--condition", choices=("baseline", "adaptive"), default="baseline")
    p.add_argument("--target", choices=TARGETS, default="sim")
    p.add_argument("--host", default=cfg.host, help="Wireless robot hostname or IP")
    p.add_argument("--turns", type=int, default=cfg.n_turns)
    p.add_argument("--interval", type=float, default=cfg.turn_interval_s, help="seconds between turns")
    p.add_argument("--seed", type=int, default=cfg.seed)
    p.add_argument("--speech", choices=("auto", "robot", "laptop", "silent"), default="auto",
                   help="where the voice plays. auto: laptop in the simulator, robot speaker on the real robot")
    args = p.parse_args()
    cfg.n_turns, cfg.turn_interval_s, cfg.seed, cfg.host = args.turns, args.interval, args.seed, args.host

    policy = make_policy(args.condition, len(cfg.seat_azimuths_deg), cfg.shuffle_each_round, cfg.seed)
    robot = Robot(args.target, cfg.host, cfg.move_duration_s, cfg.body_share)
    output = args.speech if args.speech != "auto" else ("laptop" if args.target == "sim" else "robot")
    robot.speaker = Speaker(output, robot.base_url)
    log = SessionLog(args.group, args.condition, cfg.log_dir)
    source = NullSource()  # TODO: RobotDoASource on the robot, KeyboardSource in the simulator

    print(f"Connecting to {args.target} ...")
    robot.connect()
    robot.speaker.prepare()  # checks prompts/*.wav exist (and uploads them to a real robot)
    print(f"Voice output: {output}")
    try:
        tracker = run_session(robot, policy, source, cfg, log)
        print(f"\nDone. Times addressed per seat: {tracker.times_addressed}")
    finally:
        robot.close()
        source.close()
        log.close()
        print(f"Log saved to {log.path}")


if __name__ == "__main__":
    main()
