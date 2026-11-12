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
    """(head yaw, body yaw, target head yaw, target body yaw, head pitch), degrees."""
    state = requests.get(f"{base_url}/api/state/full",
                         params={"with_target_head_pose": "true", "with_target_body_yaw": "true"}, timeout=3).json()
    d = math.degrees
    target = state.get("target_head_pose") or {}
    return (d(state["head_pose"]["yaw"]), d(state["body_yaw"]), d(target.get("yaw", float("nan"))),
            d(state.get("target_body_yaw") or float("nan")), d(state["head_pose"]["pitch"]))


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
        print(f"{'asked':>7s} {'head (room)':>12s} {'body':>7s} {'head vs body':>13s}"
              f" {'| target head':>14s} {'target body':>12s} {'head pitch':>11s}")
        for a in list(angles) + [0.0]:
            robot.turn_to(a)
            time.sleep(0.6)
            head, body, t_head, t_body, pitch = measured(robot.base_url)
            print(f"{a:+7.0f} {head:+12.1f} {body:+7.1f} {head - body:+13.1f}"
                  f" {'|':>3s} {t_head:+10.1f} {t_body:+12.1f} {pitch:+11.1f}")
            time.sleep(1.0)
    finally:
        robot.close()


if __name__ == "__main__":
    main()