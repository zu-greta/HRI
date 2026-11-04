"""Study-alignment pieces: baselines, topics, and the analysis script."""

import csv
import subprocess
import sys
from collections import Counter
from pathlib import Path

from facilitator.config import Config
from facilitator.policies import RoundRobinPolicy, UniformRandomPolicy, make_policy

ROOT = Path(__file__).resolve().parent.parent


def test_both_topics_have_a_warmup_and_six_questions_with_audio_text():
    import json

    script = json.loads((ROOT / "prompts" / "script.json").read_text())
    for warmup, questions in Config().topic_prompts.values():
        assert len(questions) == 6
        assert all(pid in script for pid in [warmup, *questions])


def test_baseline_options():
    assert isinstance(make_policy("baseline", 3, True, 0), RoundRobinPolicy)
    assert isinstance(make_policy("baseline", 3, True, 0, baseline="uniform"), UniformRandomPolicy)


def test_balanced_baseline_addresses_everyone_twice_in_six():
    for seed in range(50):
        pol, h = RoundRobinPolicy(3, shuffle=True, seed=seed), []
        for _ in range(6):
            h.append(pol.choose([0, 0, 0], h))
        assert Counter(h) == {0: 2, 1: 2, 2: 2}


def test_uniform_baseline_can_leave_someone_out():
    left_out = 0
    for seed in range(400):
        pol, h = UniformRandomPolicy(3, seed=seed), []
        for _ in range(6):
            h.append(pol.choose([0, 0, 0], h))
        left_out += len(set(h)) < 3
    assert 0.18 < left_out / 400 < 0.34  # theory: 26%


def _labels(path, seconds):
    t, rows = 0.0, ["start_s,end_s,seat"]
    for seat, s in enumerate(seconds, start=1):
        rows.append(f"{t},{t + s},{seat}")
        t += s + 1
    path.write_text("\n".join(rows) + "\n")


def test_analysis_script_runs_on_synthetic_study(tmp_path):
    sessions = [["group", "order", "round", "topic", "condition", "quiet_seat", "labels", "offset", "ticks", "log"]]
    for g in range(1, 6):
        order = "A" if g <= 3 else "B"
        for rnd, cond, secs in ((1, "baseline", (300, 120, 30)), (2, "adaptive", (220, 140, 90))):
            if order == "B":
                cond = "adaptive" if rnd == 1 else "baseline"
                secs = (220, 140, 90) if cond == "adaptive" else (300, 120, 30)
            lab = tmp_path / f"G{g}_R{rnd}.csv"
            _labels(lab, secs)
            sessions.append([f"G{g}", order, rnd, rnd, cond, 3, lab.name, 0, "", ""])
    with open(tmp_path / "sessions.csv", "w", newline="") as f:
        csv.writer(f).writerows(sessions)
    out = subprocess.run([sys.executable, str(ROOT / "analyze_study.py"), str(tmp_path / "sessions.csv")],
                         capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr
    assert "5/5 groups more even with balancing" in out.stdout and "Wilcoxon" in out.stdout
