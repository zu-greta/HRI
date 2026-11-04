"""Record a calibration session on the real robot: ticks + automatic labels.

    python run_calibration.py --target lite                 # USB robot
    python run_calibration.py --target wireless --host reachy-mini.local
    python evaluate_offline.py fit --ticks <printed>_ticks.csv --labels <printed>_labels.csv

What happens (about 6 minutes with the defaults):
  for each head position  [facing the group (0 deg), then facing each seat]:
      the robot turns there and waits; 5 s of SILENCE (measures false alarms);
      then, seat by seat, the terminal shows "SEAT k: speak now" for --seconds;
      the person in that seat reads a text aloud (anything; keep a normal voice).
  The schedule itself is the ground truth, so the labels file is written automatically:
  start_s,end_s,seat on the tick clock, trimmed by 1.0 s at the start (reaction time)
  and 0.5 s at the end. No video annotation is needed for calibration.

Rules: chairs at their final, marked positions; only the person whose seat is shown speaks;
the experimenter stays silent (point at the person / let them read the screen); no music,
fans or other talking in the room. Re-run if anyone spoke out of turn.

The facing-the-group block gives the seat angles (seats.json); the facing-a-seat blocks
give the microphone noise model with the head turned, incl. front/back mirroring
(detection_params.json). Also use the recording to check the conventions:
  * a voice on the robot's LEFT must give world_az_deg > 0 in the tick log;
  * after the robot turns to a seat at +50 deg, head_yaw_deg must read about +50.
"""

import argparse
import csv
import time
from pathlib import Path
from typing import Callable, List, Sequence, Tuple

from facilitator.config import Config
from facilitator.detection_config import DetectionConfig
from facilitator.listener import ParticipationListener
from facilitator.logger import SessionLog
from facilitator.seats import load_seat_azimuths
from facilitator.session import _head_yaw_deg
from facilitator.ticklog import TickLog

START_TRIM_S, END_TRIM_S = 1.0, 0.5
SETTLE_S, SILENCE_S, GAP_S = 1.5, 5.0, 2.0


def _listen_for(seconds: float, robot, source, listener, ticklog, clock, sleep, tick_s: float = 0.1) -> None:
    end = clock() + seconds
    while clock() < end:
        now = clock()
        tick = listener.update(source.read(), now, False, _head_yaw_deg(robot))
        ticklog.write(tick, listener.activity())
        sleep(tick_s)


def record(robot, source, listener, ticklog, log, head_positions: Sequence[float], n_seats: int,
           seconds_per_seat: float, clock: Callable[[], float] = time.monotonic,
           sleep: Callable[[float], None] = time.sleep, announce: Callable[[str], None] = print
           ) -> List[Tuple[float, float, int]]:
    """Run the schedule; returns labels (start, end, seat 1-based) on the tick clock."""
    labels = []
    for yaw in head_positions:
        robot.turn_to(yaw)
        log.log("calib_head", detail=f"yaw={yaw:+.1f}")
        announce(f"\n=== Robot faces {yaw:+.0f} deg. Everyone SILENT for {SILENCE_S:.0f} s ===")
        _listen_for(SETTLE_S + SILENCE_S, robot, source, listener, ticklog, clock, sleep)
        for seat in range(1, n_seats + 1):
            announce(f">>> SEAT {seat}: speak now ({seconds_per_seat:.0f} s) <<<")
            start = clock()
            log.log("calib_speak_start", seat=seat)
            _listen_for(seconds_per_seat, robot, source, listener, ticklog, clock, sleep)
            end = clock()
            log.log("calib_speak_end", seat=seat)
            labels.append((start + START_TRIM_S, end - END_TRIM_S, seat))
            announce(f"    seat {seat}: stop.")
            _listen_for(GAP_S, robot, source, listener, ticklog, clock, sleep)
    robot.turn_to(0.0)
    return labels


def write_labels(path: Path, labels: Sequence[Tuple[float, float, int]]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["start_s", "end_s", "seat", "kind"])
        for a, b, s in labels:
            w.writerow([f"{a:.3f}", f"{b:.3f}", s, "turn"])


def main() -> None:
    from facilitator.robot_io import TARGETS, Robot
    from facilitator.sources import RobotDoASource

    cfg = Config()
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", choices=[t for t in TARGETS if t != "sim"], default="lite")
    p.add_argument("--host", default=cfg.host)
    p.add_argument("--seconds", type=float, default=20.0, help="speaking time per seat and head position")
    p.add_argument("--name", default="CALIB", help="label for the log files")
    args = p.parse_args()

    seats, placeholder = load_seat_azimuths()
    if placeholder:
        print(f"Seat angles are placeholders {seats}: the robot will look roughly there; "
              "the fit measures the real angles from the facing-the-group block.")
    robot = Robot(args.target, args.host, cfg.move_duration_s, cfg.body_share)
    robot.connect()
    source = RobotDoASource(robot.base_url)
    if not source.wait_until_ready():
        robot.close()
        raise SystemExit("No microphone readings from the robot (see run_session.py --source robot).")
    log = SessionLog(args.name, "calibration", cfg.log_dir)
    ticklog = TickLog(log.path)
    listener = ParticipationListener.from_config(seats, DetectionConfig.load())
    try:
        labels = record(robot, source, listener, ticklog, log, [0.0] + list(seats), len(seats), args.seconds)
    finally:
        robot.close()
        source.close()
        ticklog.close()
        log.close()
    labels_path = log.path.with_name(log.path.stem + "_labels.csv")
    write_labels(labels_path, labels)
    print(f"\nSaved {ticklog.path} and {labels_path}. Next:\n"
          f"  python evaluate_offline.py fit --ticks {ticklog.path} --labels {labels_path} --dry-run\n"
          f"  (check the numbers, then run again without --dry-run and commit seats.json + detection_params.json)")


if __name__ == "__main__":
    main()
