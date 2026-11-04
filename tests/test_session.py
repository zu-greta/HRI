"""Runs a whole session with a fake robot: no simulator needed."""

import csv

import pytest

from facilitator.config import Config
from facilitator.logger import SessionLog
from facilitator.policies import RoundRobinPolicy
from facilitator.session import run_session, wait_for_silence
from facilitator.sources import NullSource, Reading


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


def test_session_turns_to_every_seat_and_logs(tmp_path):
    cfg = Config(n_turns=6, no_response_s=0.0, log_dir=str(tmp_path))
    robot, log = FakeRobot(), SessionLog("G00", "baseline", cfg.log_dir)
    tracker = run_session(robot, RoundRobinPolicy(3, seed=0), NullSource(), cfg, log)
    log.close()

    assert tracker.times_addressed == [2, 2, 2]
    assert sorted(set(robot.turns)) == sorted(set(cfg.seat_azimuths_deg))
    with open(log.path) as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["event"] == "session_start" and rows[-1]["event"] == "session_end"
    assert sum(r["event"] == "decision" for r in rows) == 6
    assert robot.said == ["intro", "question_1"] + ["invite"] * 6 + ["outro"]


def test_session_listens_before_every_turn_and_before_the_outro(tmp_path):
    cfg = Config(n_turns=2, no_response_s=0.0, log_dir=str(tmp_path))
    log = SessionLog("G00", "baseline", cfg.log_dir)
    run_session(FakeRobot(), RoundRobinPolicy(3, seed=0), NullSource(), cfg, log)
    log.close()

    with open(log.path) as f:
        rows = [r for r in csv.DictReader(f)]
    events = [r["event"] for r in rows if r["event"] == "listen_end" or r["detail"] in ("invite", "outro")
              and r["event"] == "robot_say_start"]
    assert events == ["listen_end", "robot_say_start", "listen_end", "robot_say_start",
                      "listen_end", "robot_say_start"]


# ---------------------------------------------------------------- wait_for_silence
class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ScriptedSource:
    """Reports speech during the given (start, end) time spans."""

    def __init__(self, clock, spans=()):
        self.clock, self.spans = clock, spans

    def read(self):
        return Reading(1.57, any(a <= self.clock() < b for a, b in self.spans))


class FakeLog:
    def __init__(self):
        self.rows = []

    def log(self, event, seat="", detail=""):
        self.rows.append((event, detail))


CFG = Config(silence_s=3.0, no_response_s=10.0, max_listen_s=60.0)


def listen(spans=(), robot=None, source=None, cfg=CFG):
    clock = FakeClock()
    log = FakeLog()
    reason = wait_for_silence(robot or FakeRobot(), source or ScriptedSource(clock, spans), cfg, log,
                              clock=clock, sleep=clock.sleep)
    return reason, clock.now, log


def test_waits_for_silence_after_speech():
    reason, end, _ = listen([(2, 5)])
    assert reason == "silence"
    assert end == pytest.approx(8, abs=0.3)


def test_short_pause_does_not_end_the_turn():
    reason, end, _ = listen([(1, 3), (5, 7)])  # 2 s pause, shorter than silence_s
    assert reason == "silence"
    assert end == pytest.approx(10, abs=0.3)


def test_someone_can_start_late():
    reason, end, _ = listen([(9, 10)])  # just before no_response_s
    assert reason == "silence"
    assert end == pytest.approx(13, abs=0.3)


def test_moves_on_when_nobody_answers():
    reason, end, _ = listen()
    assert reason == "no_response"
    assert end == pytest.approx(10, abs=0.3)


def test_no_data_is_reported_separately_from_a_silent_group():
    reason, end, _ = listen(source=NullSource())
    assert reason == "no_data"
    assert end == pytest.approx(10, abs=0.3)


def test_nonstop_talking_hits_the_limit():
    reason, end, _ = listen([(0, 1000)])
    assert reason == "max_listen"
    assert end == pytest.approx(60, abs=0.3)


def test_robots_own_voice_is_not_counted_as_speech():
    clock = FakeClock()

    class EchoingRobot(FakeRobot):
        def is_speaking(self):
            return clock() < 0.5

    log = FakeLog()
    reason = wait_for_silence(EchoingRobot(), ScriptedSource(clock, [(0, 0.5)]), CFG, log,
                              clock=clock, sleep=clock.sleep)
    assert reason == "no_response"
    assert clock.now == pytest.approx(10.5, abs=0.3)  # timers start once the echo is over


def test_listen_result_is_logged():
    _, _, log = listen([(2, 5)])
    event, detail = log.rows[-1]
    assert log.rows[0][0] == "listen_start" and event == "listen_end"
    assert "reason=silence" in detail
    speech_s = float(detail.split("speech_s=")[1])
    assert speech_s == pytest.approx(3.0, abs=0.2)  # measured in 0.1 s ticks
