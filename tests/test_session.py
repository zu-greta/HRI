"""Runs a whole session with a fake robot: no simulator needed."""

import csv

from facilitator.config import Config
from facilitator.logger import SessionLog
from facilitator.policies import RoundRobinPolicy
from facilitator.session import run_session
from facilitator.sources import NullSource


class FakeRobot:
    target = "fake"

    def __init__(self):
        self.turns, self.said = [], []

    def face_group(self):
        self.turns.append(0.0)

    def turn_to(self, azimuth_deg, antennas_deg=(0, 0)):
        self.turns.append(azimuth_deg)

    def say(self, prompt_id):
        self.said.append(prompt_id)

    def is_speaking(self):
        return False

    def head_yaw_deg(self):
        return self.turns[-1] if self.turns else 0.0


def test_session_turns_to_every_seat_and_logs(tmp_path):
    cfg = Config(n_turns=6, no_response_s=0.0, max_listen_s=0.0, log_dir=str(tmp_path))
    robot, log = FakeRobot(), SessionLog("G00", "baseline", cfg.log_dir)
    tracker = run_session(robot, RoundRobinPolicy(3, seed=0), NullSource(), cfg, log)
    log.close()

    assert tracker.times_addressed == [2, 2, 2]
    assert sorted(set(robot.turns)) == sorted(set(cfg.seat_azimuths_deg))
    rows = list(csv.DictReader(open(log.path)))
    assert rows[0]["event"] == "session_start" and rows[-1]["event"] == "session_end"
    assert sum(r["event"] == "decision" for r in rows) == 6
    # [STUDY ALIGNMENT] intro, warm-up to everyone, 6 addressed questions of topic 1, outro
    assert robot.said == ["intro", "t1_open"] + [f"t1_q{i}" for i in range(1, 7)] + ["outro"]
