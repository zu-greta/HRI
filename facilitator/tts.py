"""Text-to-speech: turn one sentence into a .wav file with the computer's built-in voice.

    macOS   -> `say` (built in)
    Windows -> pyttsx3 (SAPI voices)
    Linux   -> espeak-ng   (sudo apt install espeak-ng)
"""

import platform
import shutil
import subprocess
import sys
import wave
from pathlib import Path


def synthesize(text: str, out: Path, voice: str = "") -> None:
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
