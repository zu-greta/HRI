"""Make the robot speak by playing the pre-recorded prompts (prompts/<id>.wav).

Where the sound comes out:
    output="robot"  -> the robot's own speaker (real robot). Each file is uploaded
                       once to the daemon, then played with /api/media/play_sound.
    output="laptop" -> this computer's speakers 

say() blocks until the sentence has finished, so the session timing is the same
every time. is_speaking() lets the session ignore the microphones while the
robot hears its own voice.
"""

import json
import platform
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import Dict

import requests

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
ECHO_MARGIN_S = 0.5  # keep "speaking" a bit longer: room echo / audio latency


class Speaker:
    def __init__(self, output: str, base_url: str = "http://localhost:8000", prompts_dir: Path = PROMPTS,
                 auto_generate: bool = True):
        if output not in ("robot", "laptop", "silent"):
            raise ValueError("output must be 'robot', 'laptop' or 'silent'")
        self.output, self.base_url, self.dir = output, base_url, Path(prompts_dir)
        self.auto_generate = auto_generate
        self.texts: Dict[str, str] = {
            k: v for k, v in json.loads((self.dir / "script.json").read_text()).items() if not k.startswith("_")
        }
        self.durations: Dict[str, float] = {}
        self._speaking_until = 0.0
        self._http = requests.Session()

    # ------------------------------------------------------------------ setup
    def prepare(self) -> None:
        """Check every prompt has a .wav, measure durations, upload them to the robot."""
        missing = [pid for pid in self.texts if not (self.dir / f"{pid}.wav").exists()]
        if missing and self.auto_generate:
            from .tts import synthesize

            print(f"Creating missing voice files {missing} with this computer's voice "
                  "(for the study: generate once with make_prompts.py and commit them).")
            for pid in missing:
                synthesize(self.texts[pid], self.dir / f"{pid}.wav")
            missing = []
        if missing:
            raise FileNotFoundError(f"Missing audio for {missing}. Run:  python make_prompts.py")
        for pid in self.texts:
            with wave.open(str(self.dir / f"{pid}.wav")) as w:
                self.durations[pid] = w.getnframes() / w.getframerate()
        if self.output == "robot":
            for pid in self.texts:
                with open(self.dir / f"{pid}.wav", "rb") as f:
                    r = self._http.post(f"{self.base_url}/api/media/sounds/upload",
                                        files={"file": (f"{pid}.wav", f, "audio/wav")}, timeout=15)
                r.raise_for_status()

    # ----------------------------------------------------------------- speech
    def say(self, prompt_id: str) -> float:
        """Play one prompt and wait until it has finished. Returns its duration (s)."""
        if prompt_id not in self.texts:
            raise KeyError(f"unknown prompt {prompt_id!r}; add it to prompts/script.json")
        duration = self.durations.get(prompt_id, 0.0)
        print(f'   [robot says] "{self.texts[prompt_id]}"')
        self._speaking_until = time.time() + duration + ECHO_MARGIN_S

        if self.output == "robot":
            r = self._http.post(f"{self.base_url}/api/media/play_sound",
                                json={"file": f"{prompt_id}.wav"}, timeout=5)
            r.raise_for_status()
            time.sleep(duration)
        elif self.output == "laptop":
            _play_locally(self.dir / f"{prompt_id}.wav", duration)
        else:
            time.sleep(duration)
        return duration

    def is_speaking(self) -> bool:
        return time.time() < self._speaking_until


def _play_locally(path: Path, duration: float) -> None:
    """Play a .wav on this computer and block until it is done."""
    system = platform.system()
    if system == "Windows":
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)  # blocks
        return
    player = shutil.which("afplay") if system == "Darwin" else (shutil.which("paplay") or shutil.which("aplay"))
    if player is None:
        print("   (no audio player found - staying silent)")
        time.sleep(duration)
        return
    result = subprocess.run([player, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode != 0:  # e.g. no sound device: keep the timing anyway
        time.sleep(duration)
