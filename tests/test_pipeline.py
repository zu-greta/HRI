"""End to end on a virtual clock, with the real file formats:
calibration recording -> fit -> study rounds -> offset -> analyze_study + evaluate_offline study."""

import csv
import json
import random
import subprocess
import sys
from pathlib import Path

from facilitator.config import Config
from facilitator.detection_config import DetectionConfig
from facilitator.listener import ParticipationListener
from facilitator.logger import SessionLog
from facilitator.policies import make_policy
from facilitator.session import run_session
from facilitator.sim_sources import MicModel, ScriptedSource
from facilitator.sources import SpeakerSource
from facilitator.ticklog import TickLog

ROOT = Path(__file__).resolve().parent.parent
SEATS = [50.0, 0.0, -50.0]


class Clock:
    def __init__(self):
        self.t = 500.0

    def now(self):
        return self.t

    def sleep(self, dt):
        self.t += dt


class FakeRobot:
    target = "fake"

    def __init__(self, clock):
        self.clock, self.yaw, self.until = clock, 0.0, -1.0

    def turn_to(self, az, antennas_deg=(0, 0)):
        self.clock.sleep(0.8)
        self.yaw = az

    def face_group(self):
        self.turn_to(0.0)

    def say(self, prompt_id):
        self.clock.sleep(2.0)
        self.until = self.clock.now() + 0.5

    def is_speaking(self):
        return self.clock.now() < self.until

    def head_yaw_deg(self):
        return self.yaw


def run(*args):
    out = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout


def test_calibration_record_and_fit(tmp_path):
    from run_calibration import record, write_labels

    clock, robot = Clock(), None
    robot = FakeRobot(clock)
    speaking = {"seat": None}
    rng, mic = random.Random(0), MicModel()

    class Room(SpeakerSource):
        def read(self):
            s = speaking["seat"]
            return mic.observe(None if s is None else SEATS[s], robot.yaw, rng)

    def announce(msg):
        if "speak now" in msg:
            speaking["seat"] = int(msg.split("SEAT ")[1].split(":")[0]) - 1
        elif "stop" in msg:
            speaking["seat"] = None

    log = SessionLog("CALIB", "calibration", tmp_path, clock=clock.now)
    ticks = TickLog(log.path)
    listener = ParticipationListener.from_config(SEATS, DetectionConfig())
    labels = record(robot, Room(), listener, ticks, log, [0.0] + SEATS, 3, 8.0, clock.now, clock.sleep,
                    announce)
    ticks.close(); log.close()
    lab = tmp_path / "labels.csv"
    write_labels(lab, labels)
    assert len(labels) == 12
    out = run("evaluate_offline.py", "fit", "--ticks", ticks.path, "--labels", lab, "--dry-run")
    fitted = json.loads(out.split("Microphone model: ")[1].replace("'", '"'))
    seats = [float(x) for x in out.split("Seats (deg, + = robot's left): [")[1].split("]")[0].split(",")]
    assert all(abs(a - b) < 6 for a, b in zip(seats, SEATS))
    assert 5 < fitted["angle_sigma_deg"] < 16 and fitted["vad_miss_rate"] < 0.3


def _round(tmp_path, group, rnd, condition, seed):
    clock, cfg = Clock(), Config()
    cfg.seat_azimuths_deg, cfg.silence_s, cfg.no_response_s = SEATS, 1.5, 6.0
    robot = FakeRobot(clock)
    turns, t, rng = [], 0.0, random.Random(seed)
    while t < 900:
        seat = rng.choices([0, 1, 2], weights=[0.6, 0.3, 0.1])[0]
        length = rng.uniform(1.5, 6.0)
        turns.append((t, t + length, seat))
        t += length + (rng.uniform(1.8, 3.0) if rng.random() < 0.25 else rng.uniform(0.3, 0.9))
    src = ScriptedSource(turns, SEATS, clock.now, MicModel(), seed=seed, head_yaw_deg=robot.head_yaw_deg)
    log = SessionLog(f"{group}_R{rnd}", condition, tmp_path, clock=clock.now)
    ticks = TickLog(log.path)
    det = DetectionConfig()
    run_session(robot, make_policy(condition, 3, True, seed, det), src, cfg, log,
                ParticipationListener.from_config(SEATS, det), ticks, clock=clock.now, sleep=clock.sleep)
    ticks.close(); log.close()
    # ground truth on the TICK clock (as if the video offset were already applied)
    lab = tmp_path / f"{group}_R{rnd}_labels.csv"
    with open(lab, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["start_s", "end_s", "seat", "kind"])
        for a, b, s in turns:
            if src._t0 + a < clock.now():
                w.writerow([f"{src._t0 + a:.2f}", f"{src._t0 + b:.2f}", s + 1, "turn"])
    return log.path, ticks.path, lab


def test_full_study_pipeline(tmp_path):
    rows = [["group", "order", "round", "topic", "condition", "quiet_seat", "labels", "offset", "ticks", "log"]]
    for g in range(1, 4):
        for rnd, cond in ((1, "baseline"), (2, "adaptive")):
            log, ticks, lab = _round(tmp_path, f"G{g}", rnd, cond, seed=10 * g + rnd)
            rows.append([f"G{g}", "A", rnd, rnd, cond, 3, lab.name, 0, ticks.name, log.name])
    sessions = tmp_path / "study_sessions.csv"
    with open(sessions, "w", newline="") as f:
        csv.writer(f).writerows(rows)

    # event log has the sync column and the offset command works
    first_log = tmp_path / rows[1][9]
    events = list(csv.DictReader(open(first_log)))
    intro = next(e for e in events if e["event"] == "robot_say_start")
    out = run("evaluate_offline.py", "offset", "--log", first_log, "--video-s", "10")
    assert f"offset = {float(intro['mono_s']) - 10:.3f}" in out
    assert sum(e["event"] == "decision" for e in events) == 6

    out = run("analyze_study.py", sessions)
    assert "H2" in out and "Micbot unevenness" in out and "Wilcoxon" in out
    out = run("evaluate_offline.py", "study", sessions, "--out", tmp_path / "h3.csv")
    assert "H3b" in out and "replay=live 1.00" in out  # replay reproduces the live decisions exactly
