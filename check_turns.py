"""Check how far the robot really turns towards each seat (simulator or real robot).

    python check_turns.py --target wireless                      # seats from seats.json / placeholders
    python check_turns.py --target wireless --angles 50 -50 70 -70
    python check_turns.py --target wireless --body-share 1.0      # whole body faces the person

For each angle it prints what was asked and what the robot reached:
    head (room) = where the face points, in the room;  body = how far the base rotated.
Watch the robot while it runs: does the face point at each person's chair?
"""

import argparse
import math
import time

import requests

from facilitator.config import Config
from facilitator.robot_io import TARGETS, Robot
from facilitator.seats import load_seat_azimuths


def measured(base_url: str):
    state = requests.get(f"{base_url}/api/state/full", timeout=3).json()
    return math.degrees(state["head_pose"]["yaw"]), math.degrees(state["body_yaw"])


def main() -> None:
    cfg = Config()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", choices=TARGETS, default="sim")
    p.add_argument("--host", default=cfg.host)
    p.add_argument("--angles", type=float, nargs="*", help="directions to test (deg, + = robot's left)")
    p.add_argument("--body-share", type=float, default=cfg.body_share,
                   help=f"part of the turn done by the body (config: {cfg.body_share})")
    args = p.parse_args()

    angles = args.angles
    if not angles:
        seats, placeholder = load_seat_azimuths()
        angles = seats
        print(f"Seat angles {'(PLACEHOLDERS) ' if placeholder else ''}{seats}")

    robot = Robot(args.target, args.host, move_duration_s=1.0, body_share=args.body_share)
    robot.connect()
    try:
        print(f"{'asked':>7s} {'head (room)':>12s} {'body':>7s} {'head vs body':>13s}")
        for a in list(angles) + [0.0]:
            robot.turn_to(a)
            time.sleep(0.6)
            head, body = measured(robot.base_url)
            print(f"{a:+7.0f} {head:+12.1f} {body:+7.1f} {head - body:+13.1f}")
            time.sleep(1.0)
    finally:
        robot.close()


if __name__ == "__main__":
    main()