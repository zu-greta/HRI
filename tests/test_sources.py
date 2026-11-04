"""Speech sources without a robot or a real keyboard."""

import math
import sys
import types

import numpy as np
import pytest
import requests

from facilitator.config import Config
from facilitator.sources import KeyboardSource, LaptopMicSource, NullSource, RobotDoASource
from run_session import make_source


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def doa_source(monkeypatch, answer):
    source = RobotDoASource("http://robot:8000")

    def get(url, timeout):
        assert url == "http://robot:8000/api/state/doa"
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)

    monkeypatch.setattr(source._http, "get", get)
    return source


def test_doa_reading(monkeypatch):
    reading = doa_source(monkeypatch, {"angle": 1.2, "speech_detected": True}).read()
    assert reading.angle_rad == 1.2 and reading.speech_detected is True


def test_doa_null_means_no_data(monkeypatch):
    assert doa_source(monkeypatch, None).read() is None


def test_doa_connection_error_means_no_data(monkeypatch):
    assert doa_source(monkeypatch, requests.ConnectionError()).read() is None


def test_doa_ready_once_a_reading_arrives(monkeypatch):
    source = RobotDoASource("http://robot:8000")
    answers = [None, None, {"angle": 1.0, "speech_detected": False}]
    monkeypatch.setattr(source._http, "get", lambda url, timeout: FakeResponse(answers.pop(0)))
    assert source.wait_until_ready(timeout_s=5) is True


def test_doa_not_ready_without_readings(monkeypatch):
    assert doa_source(monkeypatch, None).wait_until_ready(timeout_s=0) is False


# ------------------------------------------------------------------ laptop microphone
class FakeStream:
    """Stands in for sounddevice.InputStream: the test feeds it audio levels."""

    def __init__(self, callback, **kwargs):
        self.callback = callback
        self.active = False
        self.closed = False

    def start(self):
        self.active = True

    def feed(self, level):
        self.callback(np.full((800, 1), level, dtype=np.float32), 800, None, None)

    def stop(self):
        self.active = False

    def close(self):
        self.closed = True


@pytest.fixture
def fake_sounddevice(monkeypatch):
    module = types.SimpleNamespace(streams=[])

    def input_stream(**kwargs):
        module.streams.append(FakeStream(**kwargs))
        return module.streams[-1]

    module.InputStream = input_stream
    monkeypatch.setitem(sys.modules, "sounddevice", module)
    return module


def calibrated_mic(monkeypatch, fake_sounddevice, room_level, **kwargs):
    """A LaptopMicSource that hears room_level while it calibrates."""
    monkeypatch.setattr("facilitator.sources.time.sleep", lambda s: fake_sounddevice.streams[-1].feed(room_level))
    return LaptopMicSource(**kwargs), fake_sounddevice.streams[-1]


def test_mic_threshold_comes_from_the_room(monkeypatch, fake_sounddevice):
    source, _ = calibrated_mic(monkeypatch, fake_sounddevice, 0.02, threshold_ratio=3.0, min_level=0.01)
    assert source.threshold == pytest.approx(0.06)


def test_mic_threshold_has_a_minimum_in_a_silent_room(monkeypatch, fake_sounddevice):
    source, _ = calibrated_mic(monkeypatch, fake_sounddevice, 0.0, min_level=0.01)
    assert source.threshold == 0.01


def test_mic_detects_speech_only_above_the_threshold(monkeypatch, fake_sounddevice):
    source, stream = calibrated_mic(monkeypatch, fake_sounddevice, 0.02)
    stream.feed(0.03)
    assert source.read().speech_detected is False
    stream.feed(0.2)
    assert source.read().speech_detected is True


def test_mic_does_not_miss_a_loud_block_between_reads(monkeypatch, fake_sounddevice):
    source, stream = calibrated_mic(monkeypatch, fake_sounddevice, 0.02)
    stream.feed(0.2)
    stream.feed(0.0)
    assert source.read().speech_detected is True
    assert source.read().speech_detected is False  # each sound is only counted once


def test_mic_gives_no_data_if_the_stream_dies(monkeypatch, fake_sounddevice):
    source, stream = calibrated_mic(monkeypatch, fake_sounddevice, 0.02)
    stream.active = False
    assert source.read() is None


def test_mic_close_releases_the_stream(monkeypatch, fake_sounddevice):
    source, stream = calibrated_mic(monkeypatch, fake_sounddevice, 0.02)
    source.close()
    assert stream.closed and not stream.active


# ------------------------------------------------------------------ choosing a source
def test_auto_uses_the_laptop_mic_in_the_simulator(monkeypatch, fake_sounddevice):
    monkeypatch.setattr("facilitator.sources.time.sleep", lambda s: None)
    assert isinstance(make_source("auto", "sim", "http://localhost:8000", Config()), LaptopMicSource)


@pytest.mark.parametrize("target,base_url", [("lite", "http://localhost:8000"),
                                             ("wireless", "http://reachy-mini.local:8000")])
def test_auto_uses_the_robot_mics_on_a_real_robot(monkeypatch, target, base_url):
    calls = []

    def get(self, url, timeout):
        calls.append(url)
        return FakeResponse({"angle": 1.0, "speech_detected": False})

    monkeypatch.setattr(requests.Session, "get", get)
    source = make_source("auto", target, base_url, Config())
    assert isinstance(source, RobotDoASource)
    assert calls == [f"{base_url}/api/state/doa"]


def test_robot_source_stops_with_a_clear_message_without_readings(monkeypatch):
    monkeypatch.setattr(RobotDoASource, "wait_until_ready", lambda self: False)
    with pytest.raises(SystemExit, match="No microphone readings"):
        make_source("robot", "lite", "http://localhost:8000", Config())


def test_missing_laptop_mic_stops_with_a_clear_message(monkeypatch, fake_sounddevice):
    def no_device(**kwargs):
        raise OSError("no default input device")

    fake_sounddevice.InputStream = no_device
    with pytest.raises(SystemExit, match="no default input device"):
        make_source("laptop", "sim", "http://localhost:8000", Config())


@pytest.mark.parametrize("choice,expected", [("keyboard", KeyboardSource), ("none", NullSource)])
def test_explicit_source_choice(choice, expected):
    assert isinstance(make_source(choice, "sim", "http://localhost:8000", Config()), expected)


# ------------------------------------------------------------------ keyboard
def keyboard(presses):
    """A KeyboardSource whose clock and key presses are controlled by the test."""
    time_now = [0.0]
    source = KeyboardSource([50.0, 0.0, -50.0], hold_s=0.6, clock=lambda: time_now[0])
    source._pressed_keys = lambda: presses.pop(0) if presses else ""
    return source, time_now


def test_key_press_counts_as_speech_for_the_hold_time():
    source, time_now = keyboard(["2"])
    assert source.read().speech_detected is True
    time_now[0] = 0.5
    assert source.read().speech_detected is True
    time_now[0] = 0.7
    assert source.read().speech_detected is False


def test_no_key_is_silence():
    source, _ = keyboard([])
    assert source.read().speech_detected is False


@pytest.mark.parametrize("key", ["0", "4", "x", "\x00", "²"])
def test_other_keys_are_ignored(key):
    source, _ = keyboard([key])
    assert source.read().speech_detected is False


@pytest.mark.parametrize("key,expected", [("1", math.pi / 2 - math.radians(50)),
                                          ("2", math.pi / 2),
                                          ("3", math.pi / 2 + math.radians(50))])
def test_key_gives_the_seat_direction_in_microphone_convention(key, expected):
    source, _ = keyboard([key])
    assert source.read().angle_rad == pytest.approx(expected)
