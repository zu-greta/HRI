"""Tick log -> replay -> fit, and the simulation comparison, on synthetic data."""

import random
import subprocess
import sys
from pathlib import Path

from facilitator.detection_config import DetectionConfig
from facilitator.listener import ParticipationListener
from facilitator.sim_sources import MicModel, ReplaySource, iter_ticks
from facilitator.simulation import GroupModel, gini, simulate_session
from facilitator.ticklog import TickLog

ROOT = Path(__file__).resolve().parent.parent
TRUE_SEATS = [40.0, -5.0, -45.0]  # deliberately not the placeholders


def record(tmp_path):
    """A fake calibration recording: each seat speaks 10 s in turn, head facing the group."""
    log_path = tmp_path / "CAL_baseline_x.csv"
    ticks = TickLog(log_path)
    lis = ParticipationListener.from_config([50.0, 0.0, -50.0], DetectionConfig())
    rng, m, t = random.Random(0), MicModel(noise_deg=8), 0.0
    labels = ["start_s,end_s,seat"]
    for seat in range(3):
        labels.append(f"{t:.1f},{t + 10:.1f},{seat + 1}")
        for _ in range(100):
            ticks.write(lis.update(m.observe(TRUE_SEATS[seat], 0.0, rng), t, False, 0.0), lis.activity())
            t += 0.1
        for _ in range(20):  # silence
            ticks.write(lis.update(m.observe(None, 0.0, rng), t, False, 0.0), lis.activity())
            t += 0.1
    ticks.close()
    label_file = tmp_path / "labels.csv"
    label_file.write_text("\n".join(labels) + "\n")
    return ticks.path, label_file


def test_ticklog_roundtrip_and_replay(tmp_path):
    path, _ = record(tmp_path)
    rows = list(iter_ticks(str(path)))
    assert len(rows) == 360 and rows[0].head_yaw_deg == 0.0
    src = ReplaySource(str(path))
    assert src.read() is not None


def test_fit_recovers_seats(tmp_path):
    path, labels = record(tmp_path)
    out = subprocess.run([sys.executable, str(ROOT / "evaluate_offline.py"), "fit", "--ticks", str(path),
                          "--labels", str(labels), "--dry-run"], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    seats = eval(out.stdout.split("robot's left): ")[1].splitlines()[0])
    assert all(abs(a - b) < 4 for a, b in zip(seats, TRUE_SEATS))


def test_gini():
    assert gini([1, 1, 1]) == 0 and gini([0, 0, 3]) > 0.6


def test_ours_picks_the_quietest_more_often_than_micbot():
    seats, mic = [50.0, 0.0, -50.0], MicModel()
    hits = {}
    for method in ("micbot", "ours"):
        res = [simulate_session(method, seats, GroupModel(), mic, seed=s) for s in range(15)]
        hits[method] = sum(r.hit_recent for r in res) / sum(r.decisions for r in res)
    assert hits["ours"] > hits["micbot"]
