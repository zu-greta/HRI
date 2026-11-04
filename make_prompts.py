"""Turn the robot's script (prompts/script.json) into .wav files with text-to-speech.

    python make_prompts.py                  # uses the computer's default voice
    python make_prompts.py --voice Samantha # macOS voice (list them: say -v '?')
    python make_prompts.py --only t1_q3     # regenerate one sentence

Pre-recorded prompts are a controlled variable (same content, same voice in all conditions):
generate them ONCE on ONE computer with ONE --voice, then commit prompts/*.wav and
prompts/manifest.json. Never regenerate during data collection.
Voices: macOS `say`, Windows pyttsx3, Linux espeak-ng (see facilitator/tts.py).
"""

import argparse
import json
import platform
from pathlib import Path

from facilitator.tts import synthesize, wav_duration

PROMPTS = Path(__file__).resolve().parent / "prompts"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--voice", default="", help="voice name (optional)")
    p.add_argument("--only", nargs="*", help="only these prompt ids")
    args = p.parse_args()

    script = {k: v for k, v in json.loads((PROMPTS / "script.json").read_text()).items() if not k.startswith("_")}
    manifest_path = PROMPTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}

    for pid, text in script.items():
        if args.only and pid not in args.only:
            continue
        out = PROMPTS / f"{pid}.wav"
        synthesize(text, out, args.voice)
        manifest[pid] = {"text": text, "duration_s": round(wav_duration(out), 2),
                         "voice": args.voice or "default", "os": platform.system()}
        print(f"[ok] {out.name:16s} {manifest[pid]['duration_s']:5.2f} s  \"{text}\"")

    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nWrote {manifest_path.name}. Commit prompts/*.wav so everyone uses identical audio.")


if __name__ == "__main__":
    main()
