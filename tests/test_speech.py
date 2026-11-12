"""Speech without sound hardware: uses a temporary prompts folder with a tiny .wav."""

import json
import wave

import pytest

from facilitator.speech import Speaker


def make_prompts(folder, seconds=0.2):
    (folder / "script.json").write_text(json.dumps({"_comment": "x", "hello": "Hello"}))
    with wave.open(str(folder / "hello.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))


def test_say_blocks_for_clip_length_and_flags_speaking(tmp_path):
    make_prompts(tmp_path)
    sp = Speaker("silent", prompts_dir=tmp_path)
    sp.prepare()
    assert sp.durations["hello"] == pytest.approx(0.2)
    assert sp.say("hello") == pytest.approx(0.2)
    assert sp.is_speaking()  # echo margin still running


def test_start_returns_immediately_and_wait_blocks(tmp_path):
    import time

    make_prompts(tmp_path, seconds=0.3)
    sp = Speaker("silent", prompts_dir=tmp_path)
    sp.prepare()
    t0 = time.monotonic()
    assert sp.start("hello") == pytest.approx(0.3)
    assert time.monotonic() - t0 < 0.1  # robot can move while the prompt plays
    assert sp.is_speaking()
    sp.wait()
    assert time.monotonic() - t0 >= 0.29
    assert sp.is_speaking()  # echo margin still running


def test_missing_wav_is_reported(tmp_path):
    (tmp_path / "script.json").write_text(json.dumps({"bye": "Bye"}))
    with pytest.raises(FileNotFoundError):
        Speaker("silent", prompts_dir=tmp_path, auto_generate=False).prepare()


def test_unknown_prompt(tmp_path):
    make_prompts(tmp_path)
    sp = Speaker("silent", prompts_dir=tmp_path)
    sp.prepare()
    with pytest.raises(KeyError):
        sp.say("nope")
