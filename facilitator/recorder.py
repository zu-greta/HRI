"""Record the room's audio during a round, in sync with the robot's logs.

Why the laptop microphone (or a USB microphone plugged into the laptop), not the
robot's? Streaming the robot's audio would add load to the same Wi-Fi link that
controls the robot. A laptop recording is just as good for annotation, and it is
started by the session script on the SAME clock as the tick log, so no clap or
manual offset is needed:

    tick-log time = sidecar "offset_s" + time in the WAV file

Files (in `folder`; default: next to the session log):
    <session>_audio.wav    16 kHz, mono, 16-bit  (~1.9 MB per minute)
    <session>_audio.json   start time on the session clock, device, sample rate ...

The WAV is written continuously by a background thread, and its header is
updated every few seconds, so a crash loses at most the last few seconds.
"""

import json
import queue
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 16000
BLOCK = 1600  # 100 ms


class AudioRecorder:
    def __init__(self, session_log_path: Path, device: Optional[str] = None, clock: Callable[[], float] = time.monotonic,
                 stream_factory=None, folder: Optional[Path] = None):
        p = Path(session_log_path)
        out = Path(folder) if folder is not None else p.parent
        out.mkdir(parents=True, exist_ok=True)
        self.wav_path = (out / (p.stem + "_audio.wav")).resolve()
        self.meta_path = (out / (p.stem + "_audio.json")).resolve()
        self.device, self.clock = device, clock
        self._stream_factory = stream_factory  # tests inject a fake stream
        self._queue: "queue.Queue[Optional[bytes]]" = queue.Queue()
        self._writer: Optional[threading.Thread] = None
        self._stream = None
        self.start_t: Optional[float] = None
        self.frames = 0
        self.peak = 0.0
        self.problems = 0

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        """Open the microphone and start writing. Raises if the microphone cannot be opened."""
        self._wav = wave.open(str(self.wav_path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(SAMPLE_RATE)
        self._writer = threading.Thread(target=self._write_loop, daemon=True)
        self._writer.start()
        if self._stream_factory is not None:
            self._stream = self._stream_factory(self._on_audio)
        else:
            import sounddevice as sd

            self._stream = sd.InputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK, channels=1, dtype="int16",
                                          device=self.device, callback=self._on_audio)
        self.start_t = self.clock()  # session clock at the first sample (within ~one block)
        self._stream.start()
        self._write_meta(finished=False)

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        if self._writer is not None:
            self._queue.put(None)
            self._writer.join(timeout=5.0)
            self._writer = None
            self._wav.close()
            self._write_meta(finished=True)

    @property
    def seconds(self) -> float:
        return self.frames / SAMPLE_RATE

    # ------------------------------------------------------------------ internals
    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            self.problems += 1  # e.g. input overflow
        data = np.asarray(indata, dtype=np.int16).reshape(-1)
        self.peak = max(self.peak, float(np.abs(data).max(initial=0)) / 32768.0)
        self._queue.put(data.tobytes())

    def _write_loop(self) -> None:
        last_flush = time.monotonic()
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            self._wav.writeframes(chunk)
            self.frames += len(chunk) // 2
            if time.monotonic() - last_flush > 5.0:  # keep the header valid if the program crashes
                self._wav._file.flush()  # noqa: SLF001
                self._wav._patchheader()  # noqa: SLF001
                last_flush = time.monotonic()

    def _write_meta(self, finished: bool) -> None:
        self.meta_path.write_text(json.dumps({
            "wav": self.wav_path.name,
            "offset_s": None if self.start_t is None else round(self.start_t, 3),
            "offset_note": "tick-log time = offset_s + time in the WAV (use as 'offset' in study_sessions.csv)",
            "started": datetime.now().isoformat(timespec="seconds"),
            "sample_rate": SAMPLE_RATE,
            "device": self.device or "default input",
            "seconds": round(self.seconds, 1),
            "peak_level": round(self.peak, 3),
            "stream_problems": self.problems,
            "finished": finished,
        }, indent=2))


def read_offset(audio_json: Path) -> float:
    """Offset to put WAV/label times on the tick-log clock."""
    return float(json.loads(Path(audio_json).read_text())["offset_s"])