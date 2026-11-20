"""Turn the robot's script (prompts/script.json) into .wav files with text-to-speech.

    python make_prompts.py                              # study voice: Piper en_US-lessac-medium
    python make_prompts.py --voice en_US-amy-medium     # another Piper voice (in voices/)
    python make_prompts.py --speed 1.1 --expressiveness 1.2   # livelier
    python make_prompts.py --only t1_q3                 # regenerate one sentence
    python make_prompts.py --engine system --voice Samantha   # computer's built-in voice (tests only)

First time:  pip install piper-tts
             python -m piper.download_voices --download-dir voices en_US-lessac-medium
Listen to the voices:  python make_prompts.py --sample   (writes voices/sample_<voice>.wav for each model)
"""

import argparse
import json
import platform
from pathlib import Path

from facilitator.tts import (DEFAULT_PIPER_VOICE, PIPER_LENGTH_SCALE, PIPER_NOISE_SCALE, PIPER_NOISE_W_SCALE,
                             VOICES_DIR, piper_model_path, synthesize, wav_duration)

PROMPTS = Path(__file__).resolve().parent / "prompts"
SAMPLE_TEXT = ("Hello everyone, I am Reachy. Participant two. "
               "What do you think: is it better to travel alone or with friends?")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--engine", choices=("piper", "system"), default=None,
                   help="default: piper, or system when --voice names a voice that is not in voices/ (e.g. Samantha)")
    p.add_argument("--voice", default="", help=f"voice name (piper default: {DEFAULT_PIPER_VOICE})")
    p.add_argument("--speed", type=float, default=1 / PIPER_LENGTH_SCALE,
                   help=f"piper: speaking speed (default {1 / PIPER_LENGTH_SCALE:.2f}; 1.0 = the voice's own pace)")
    p.add_argument("--expressiveness", type=float, default=1.0,
                   help="piper: scales intonation/rhythm variation (default 1.0 = study setting)")
    p.add_argument("--only", nargs="*", help="only these prompt ids")
    p.add_argument("--sample", action="store_true", help="write one sample sentence per downloaded voice and exit")
    args = p.parse_args()
    if args.engine is None:
        args.engine = "system" if args.voice and not piper_model_path(args.voice).exists() else "piper"
        if args.engine == "system":
            print(f"'{args.voice}' is not a Piper voice in voices/ -> using this computer's built-in voice.")

    style = dict(length_scale=round(1 / args.speed, 3),
                 noise_scale=round(PIPER_NOISE_SCALE * args.expressiveness, 3),
                 noise_w_scale=round(PIPER_NOISE_W_SCALE * args.expressiveness, 3))

    if args.sample:
        models = sorted(VOICES_DIR.glob("*.onnx"))
        if not models:
            raise SystemExit("No voices in voices/. Download one: "
                             f"python -m piper.download_voices --download-dir voices {DEFAULT_PIPER_VOICE}")
        for m in models:
            out = VOICES_DIR / f"sample_{m.stem}.wav"
            synthesize(SAMPLE_TEXT, out, m.stem, "piper", **style)
            print(f"[ok] {out}")
        return

    script = {k: v for k, v in json.loads((PROMPTS / "script.json").read_text()).items() if not k.startswith("_")}
    manifest_path = PROMPTS / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    voice = args.voice or (DEFAULT_PIPER_VOICE if args.engine == "piper" else "default")

    for pid, text in script.items():
        if args.only and pid not in args.only:
            continue
        out = PROMPTS / f"{pid}.wav"
        synthesize(text, out, args.voice, args.engine, **style)
        manifest[pid] = {"text": text, "duration_s": round(wav_duration(out), 2), "engine": args.engine,
                         "voice": voice, "os": platform.system()}
        if args.engine == "piper":
            manifest[pid]["style"] = style
        print(f"[ok] {out.name:16s} {manifest[pid]['duration_s']:5.2f} s  \"{text}\"")

    manifest_path.write_text(json.dumps(manifest, indent=2))
    voices = {m.get("engine", "system") + ":" + m.get("voice", "?") for m in manifest.values()}
    if len(voices) > 1:
        print(f"\nWARNING: the prompts now use more than one voice {sorted(voices)}. "
              "Regenerate all of them (no --only) before the study.")
    print(f"\nWrote {manifest_path.name}. Commit prompts/*.wav so everyone uses identical audio.")


if __name__ == "__main__":
    main()
