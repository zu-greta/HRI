"""End to end on a virtual clock with the real file formats:
fake rounds (event log + ticks + audio + offset) -> build_sessions -> label templates ->
labels -> analyze_study -> evaluate_offline study."""

import csv
import json
import random
import subprocess
import sys
import wave

import numpy as np

from facilitator.config import Config
from facilitator.detection_config import DetectionConfig
from facilitator.listener import ParticipationListener
from facilitator.logger import SessionLog
from facilitator.policies import make_policy
from facilitator.seats import load_seat_azimuths
from facilitator.session import run_session
from facilitator.sim_sources import MicModel, ScriptedSource
from facilitator.ticklog import TickLog
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Clock:
    def __init__(self, t0):
        self.t = t0

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


def fake_round(folder: Path, group: str, rnd: int, condition: str, seed: int, t0: float):
    seats, _ = load_seat_azimuths()               # the repository's calibration -> matched by build_sessions
    det = DetectionConfig.load()
    clock, cfg = Clock(t0), Config()
    cfg.seat_azimuths_deg, cfg.silence_s, cfg.no_response_s = seats, 1.5, 6.0
    robot = FakeRobot(clock)
    turns, t, rng = [], 0.0, random.Random(seed)
    while t < 400:
        seat = rng.choices([0, 1, 2], weights=[0.6, 0.3, 0.1])[0]
        length = rng.uniform(1.5, 6.0)
        turns.append((t, t + length, seat))
        t += length + (rng.uniform(1.8, 3.0) if rng.random() < 0.25 else rng.uniform(0.3, 0.9))
    src = ScriptedSource(turns, seats, clock.now, MicModel(), seed=seed, head_yaw_deg=robot.head_yaw_deg)
    log = SessionLog(f"{group}_R{rnd}_T{rnd}", condition, folder, clock=clock.now)
    log.log("study_info", detail=f"group={group} round={rnd} topic={rnd} order=A condition={condition} "
                                 f"quiet_seat=3 baseline=balanced seed={seed}")
    log.log("versions", detail="code=test prompt_audio=abc")
    log.log("detection_setup", detail=f"attributor=hmm estimator=turns_decay seats={seats} placeholder_seats=False")
    ticks = TickLog(log.path)
    run_session(robot, make_policy(condition, 3, True, seed, det), src, cfg, log,
                ParticipationListener.from_config(seats, det), ticks, clock=clock.now, sleep=clock.sleep)
    ticks.close()
    log.close()
    stem = log.path.stem
    offset = t0 - 5.0                              # audio started 5 s before the session clock origin
    sr, length = 8000, clock.now() - offset + 1
    x = np.zeros(int(sr * length), dtype=np.int16)
    lab = folder / "labels" / f"{stem}.csv"
    lab.parent.mkdir(exist_ok=True)
    with open(lab, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["start_s", "end_s", "seat"])
        for a, b, s in turns:
            a_w, b_w = src._t0 + a - offset, src._t0 + b - offset
            if b_w < length - 1:
                w.writerow([f"{a_w:.2f}", f"{b_w:.2f}", s + 1])
                x[int(a_w * sr):int(b_w * sr)] = (8000 * np.sin(np.arange(int(b_w * sr) - int(a_w * sr)) * 0.2)).astype(np.int16)
    with wave.open(str(folder / f"{stem}_audio.wav"), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(x.tobytes())
    (folder / f"{stem}_audio.json").write_text(json.dumps({"offset_s": offset}))


def test_full_analysis_pipeline(tmp_path):
    t0 = 1000.0
    for g in range(1, 4):
        for rnd, cond in ((1, "baseline"), (2, "adaptive")):
            fake_round(tmp_path, f"G0{g}", rnd, cond, seed=10 * g + rnd, t0=t0)
            t0 += 2000
    out = run("build_sessions.py", tmp_path, "--out", tmp_path / "study_sessions.csv")
    assert "3 groups, 6 rounds" in out
    rows = list(csv.DictReader(open(tmp_path / "study_sessions.csv")))
    assert all(r["params"] for r in rows)            # calibration found by matching the seats

    out = run("make_label_templates.py", tmp_path / "study_sessions.csv")
    assert "'?' stretches" in out

    out = run("analyze_study.py", tmp_path / "study_sessions.csv", "--out", tmp_path / "results")
    assert "H1 PRIMARY" in out and "Overall:" in out and "addressee produced" in out
    assert (tmp_path / "results" / "rounds.csv").exists()

    out = run("evaluate_offline.py", "study", tmp_path / "study_sessions.csv")
    assert "H3a" in out and "H3b" in out
    # the virtual clock ticks exactly every 0.1 s, so an utterance can land exactly on the 1.0 s turn threshold
    # and 3-decimal logging can tip it either way; real recordings (irregular ticks) replay exactly (G01: 6/6)
    share = float(out.split("replayed choice = live choice in ")[1].split()[0])
    assert share >= 0.8
    for line in out.splitlines():
        if line.startswith("G0"):
            assert line.split()[1] == "1.000"        # offline replay reproduces the live robot exactly
