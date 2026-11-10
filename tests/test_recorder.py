"""Recorder with a fake microphone (no audio hardware needed)."""

import json
import threading
import time
import wave

import numpy as np
import pytest

from facilitator.recorder import BLOCK, SAMPLE_RATE, AudioRecorder, read_offset


class FakeStream:
    """Calls the recorder's callback with 100 ms blocks of a 440 Hz tone, like sounddevice would."""

    def __init__(self, callback, blocks=10, amplitude=0.3):
        self.cb, self.blocks, self.amp = callback, blocks, amplitude
        self._thread = None

    def start(self):
        def run():
            t = np.arange(BLOCK) / SAMPLE_RATE
            for i in range(self.blocks):
                tone = (self.amp * 32767 * np.sin(2 * np.pi * 440 * (t + i * BLOCK / SAMPLE_RATE))).astype(np.int16)
                self.cb(tone.reshape(-1, 1), BLOCK, None, None)
        self._thread = threading.Thread(target=run)
        self._thread.start()

    def stop(self):
        self._thread.join()

    def close(self):
        pass


def test_recording_writes_wav_and_sync_offset(tmp_path):
    clock = iter([123.456]).__next__
    rec = AudioRecorder(tmp_path / "G01_R1_T1_baseline_x.csv", clock=clock, stream_factory=lambda cb: FakeStream(cb, 20))
    rec.start()
    time.sleep(0.2)
    rec.stop()
    with wave.open(str(rec.wav_path)) as w:
        assert w.getframerate() == SAMPLE_RATE and w.getnchannels() == 1
        assert w.getnframes() == 20 * BLOCK  # 2.0 s
    meta = json.loads(rec.meta_path.read_text())
    assert meta["finished"] and meta["seconds"] == pytest.approx(2.0)
    assert read_offset(rec.meta_path) == pytest.approx(123.456)
    assert 0.25 < rec.peak < 0.35
    assert rec.wav_path.name == "G01_R1_T1_baseline_x_audio.wav"


def test_microphone_failure_is_reported_before_the_round(tmp_path):
    def broken(cb):
        raise OSError("no input device")
    rec = AudioRecorder(tmp_path / "x.csv", stream_factory=broken)
    with pytest.raises(OSError):
        rec.start()
