"""Text-to-speech: turn one sentence into a .wav file.

Engines:
    piper  -> Piper neural TTS (STUDY VOICE): offline, same voice on every OS.
              pip install piper-tts; voice models (.onnx + .onnx.json, ~60 MB) live in voices/
              and are NOT committed:  python -m piper.download_voices --download-dir voices en_US-lessac-medium
    system -> the computer's built-in voice (quick tests only):
              macOS `say`, Windows pyttsx3 (SAPI), Linux espeak-ng
"""

import platform
import shutil
import subprocess
import sys
import wave
from functools import lru_cache
from pathlib import Path

VOICES_DIR = Path(__file__).resolve().parent.parent / "voices"
DEFAULT_PIPER_VOICE = "en_US-lessac-medium"

# Piper style at the study defaults (see make_prompts.py --speed/--expressiveness).
# noise_scale / noise_w_scale above Piper's defaults (0.667 / 0.8) = more varied intonation and rhythm.
PIPER_LENGTH_SCALE = 1.0      # the voice's own pace (< 1 = faster; 0.92 and 0.97 felt rushed)
PIPER_NOISE_SCALE = 0.8
PIPER_NOISE_W_SCALE = 0.95


def synthesize(text: str, out: Path, voice: str = "", engine: str = "system",
               length_scale: float = PIPER_LENGTH_SCALE, noise_scale: float = PIPER_NOISE_SCALE,
               noise_w_scale: float = PIPER_NOISE_W_SCALE) -> None:
    if engine == "piper":
        _piper(text, Path(out), voice or DEFAULT_PIPER_VOICE, length_scale, noise_scale, noise_w_scale)
    elif engine == "system":
        _system(text, Path(out), voice)
    else:
        raise ValueError("engine must be 'piper' or 'system'")


# ----------------------------------------------------------------------------- piper
def piper_model_path(voice: str) -> Path:
    """A voice name (looked up in voices/) or a path to an .onnx model."""
    p = Path(voice)
    if p.suffix == ".onnx":
        return p
    return VOICES_DIR / f"{voice}.onnx"


@lru_cache(maxsize=4)
def _load_piper(model: str):
    try:
        from piper import PiperVoice
    except ImportError:
        sys.exit("Piper is not installed:  pip install piper-tts")
    if not Path(model).exists():
        sys.exit(f"Voice model {model} not found. Download it once:\n"
                 f"  python -m piper.download_voices --download-dir voices {Path(model).stem}")
    return PiperVoice.load(model)


def _piper(text: str, out: Path, voice: str, length_scale: float, noise_scale: float,
           noise_w_scale: float) -> None:
    from piper import SynthesisConfig

    model = _load_piper(str(piper_model_path(voice)))
    cfg = SynthesisConfig(length_scale=length_scale, noise_scale=noise_scale, noise_w_scale=noise_w_scale)
    with wave.open(str(out), "wb") as wf:
        model.synthesize_wav(text, wf, syn_config=cfg)


# ----------------------------------------------------------------------------- system voices
def _system(text: str, out: Path, voice: str) -> None:
    system = platform.system()
    if system == "Darwin":
        cmd = ["say", "--file-format=WAVE", "--data-format=LEI16@22050", "-o", str(out)]
        if voice:
            cmd += ["-v", voice]
        subprocess.run(cmd + [text], check=True)
    elif system == "Windows":
        import pyttsx3

        engine = pyttsx3.init()
        if voice:
            for v in engine.getProperty("voices"):
                if voice.lower() in v.name.lower():
                    engine.setProperty("voice", v.id)
        engine.save_to_file(text, str(out))
        engine.runAndWait()
    else:
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if exe is None:
            sys.exit("Install a voice first:  sudo apt install espeak-ng")
        subprocess.run([exe, "-w", str(out)] + (["-v", voice] if voice else []) + [text], check=True)


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()
