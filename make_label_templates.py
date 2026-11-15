"""
[ANALYSIS]
starting label track for each recording - partial automation for manual labeling in Audacity

    python make_label_templates.py ./logs/study_sessions.csv

For every attempt it writes <labels dir>/<stem>_template.txt (Audacity label format) with:
    INTRO   the "I'm in seat k" introductions (before the robot's intro): listen here to learn the voices
    R       every robot prompt, from the event log (exact): do not change; it also shows the sync is right
            (the R labels must sit exactly on the robot's voice)
    ?       stretches where the room audio is loud while the robot is silent = probably someone speaking
    END     after the robot's outro
Speech is only counted between the robot's intro and the end of the outro.
"""

import argparse
import wave
from pathlib import Path

import numpy as np

from facilitator.study_data import audio_offset, read_log, read_sessions

FRAME_S = 0.02
START_DB, KEEP_DB = 10.0, 6.0      # above the noise floor: start / keep a stretch 
MERGE_GAP_S, MIN_LEN_S = 0.35, 0.3  # bridge short pauses; drop blips (labelling rule: >= 0.3 s)
ROBOT_PAD_S = 0.3                   # ignore loudness this close to a robot prompt (echo)


def speech_stretches(wav_path: str):
    with wave.open(wav_path) as w:
        sr, n = w.getframerate(), w.getnframes()
        x = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float64) / 32768.0
    hop = int(FRAME_S * sr)
    m = len(x) // hop
    db = 20 * np.log10(np.sqrt(np.mean(x[:m * hop].reshape(m, hop) ** 2, axis=1)) + 1e-9)
    floor = np.percentile(db, 20)
    out, on, start = [], False, 0
    for i, v in enumerate(db):
        if not on and v > floor + START_DB:
            on, start = True, i
        elif on and v < floor + KEEP_DB:
            on = False
            out.append([start * FRAME_S, i * FRAME_S])
    if on:
        out.append([start * FRAME_S, m * FRAME_S])
    merged = []
    for a, b in out:
        if merged and a - merged[-1][1] < MERGE_GAP_S:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged if b - a >= MIN_LEN_S], m * FRAME_S, floor


def subtract(segs, holes):
    out = []
    for a, b in segs:
        parts = [(a, b)]
        for ha, hb in holes:
            nxt = []
            for pa, pb in parts:
                if hb <= pa or ha >= pb:
                    nxt.append((pa, pb))
                    continue
                if pa < ha:
                    nxt.append((pa, ha))
                if hb < pb:
                    nxt.append((hb, pb))
            parts = nxt
        out += [(pa, pb) for pa, pb in parts if pb - pa >= MIN_LEN_S]
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sessions", help="study_sessions.csv from build_sessions.py")
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args()
    for a in read_sessions(args.sessions):
        stem = Path(a.log).stem
        out = Path(a.labels).with_name(stem + "_template.txt")
        if not a.audio or not Path(a.audio).exists():
            print(f"SKIP {stem}: no audio")
            continue
        off = audio_offset(a)
        if off is None:
            print(f"SKIP {stem}: no audio offset (_audio.json)")
            continue
        if out.exists() and not args.overwrite:
            print(f"exists {out.name} (use --overwrite)")
            continue
        li = read_log(a.log)
        robot = [(s - off, e - off) for s, e in li.robot_speech]
        stretches, length, floor = speech_stretches(a.audio)
        start = None if li.start is None else li.start - off
        end = None if li.end is None else li.end - off
        holes = [(s - ROBOT_PAD_S, e + ROBOT_PAD_S) for s, e in robot]
        if start is not None:
            holes.append((-1.0, start))
        if end is not None:
            holes.append((end, length + 1.0))
        rows = []
        if start is not None and start > 0.5:
            rows.append((0.0, start, "INTRO"))
        rows += [(s, e, "R") for s, e in robot]
        rows += [(s, e, "?") for s, e in subtract(stretches, holes)]
        if end is not None and end < length:
            rows.append((end, length, "END"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(f"{s:.3f}\t{e:.3f}\t{lab}\n" for s, e, lab in sorted(rows)))
        n_q = sum(r[2] == "?" for r in rows)
        print(f"wrote {out}  ({n_q} '?' stretches, {len(robot)} robot prompts, noise floor {floor:.0f} dB)")


if __name__ == "__main__":
    main()
