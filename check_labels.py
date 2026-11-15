"""
[ANALYSIS]
check finished labels before running the analysis

    python check_labels.py ~/study_data/study_sessions.csv

For every attempt that has a labels file it reports:
  * format problems (seat not 1/2/3, end before start, labels past the end of the audio)
  * labels outside the discussion (before the robot's intro / after the outro): ignored by the analysis
  * labels on top of the robot's own prompts (> 0.5 s): usually a mislabel of the robot's voice,
    sometimes real (someone talking over the robot)
  * the same seat labelled twice at once (duplicate), and overlap between people (real, but check long ones)
  * coverage: how much of the loud, non-robot audio is labelled (low = speech missed), and how much
    labelled time is quiet in the recording (high = labels in silence / wrong times)
  * timing sensitivity: H2 with the labels as they are vs shrunk by 0.25 s at both ends.
    If the two are close, imprecise label edges do not matter for the results.
"""

import argparse
from pathlib import Path

from facilitator.study_data import audio_offset, clip, read_labels, read_log, read_sessions, speakers_at, tick_rows
from make_label_templates import speech_stretches

EDGE_S = 0.25


def overlap(a, b, c, d):
    return max(0.0, min(b, d) - max(a, c))


def h2(rows, labels):
    n = ok = 0.0
    for r in rows:
        if r["robot_speaking"] == "1":
            continue
        who = speakers_at(labels, r["t"])
        if len(who) != 1:
            continue
        s = next(iter(who))
        n += r["dt"]
        ok += r["dt"] if r["seat"] and int(r["seat"]) - 1 == s else 0.0
    return ok / n if n else float("nan"), n


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sessions")
    args = p.parse_args()
    problems = 0
    for a in read_sessions(args.sessions):
        stem = Path(a.log).stem
        if not a.labels or not Path(a.labels).exists():
            print(f"\n{stem}: NO LABELS ({a.labels})")
            continue
        li = read_log(a.log)
        off = audio_offset(a)
        print(f"\n{stem}  ({a.condition}, attempt {a.attempt}{'' if li.completed else ', DID NOT FINISH'})")
        if off is None:
            print("   PROBLEM: no audio offset (_audio.json missing) - labels cannot be placed on the robot's clock")
            problems += 1
            continue
        raw = [ln.split(",") for ln in Path(a.labels).read_text().splitlines()[1:] if ln.strip()]
        bad = [r for r in raw if len(r) < 3 or r[2].strip() not in ("1", "2", "3") or float(r[1]) <= float(r[0])]
        wav_s = None
        if a.audio and Path(a.audio).exists():
            import wave
            with wave.open(a.audio) as w:
                wav_s = w.getnframes() / w.getframerate()
        past = [r for r in raw if wav_s and float(r[1]) > wav_s + 0.5]
        if bad or past:
            problems += 1
            print(f"   PROBLEM: {len(bad)} malformed rows, {len(past)} past the end of the audio ({wav_s:.0f} s)")
        labels = read_labels(a.labels, off)            # session clock
        inside = clip(labels, li.start, li.end)
        outside = sum(b - x for x, b, _ in labels) - sum(b - x for x, b, _ in inside)
        per = [sum(b - x for x, b, s in inside if s == k) for k in range(3)]
        print(f"   {len(labels)} labels; speaking s seat 1/2/3 = {per[0]:.1f} / {per[1]:.1f} / {per[2]:.1f}"
              + (f"; {outside:.1f} s outside the discussion (ignored)" if outside > 0.05 else ""))

        on_robot = [(x, b, s) for x, b, s in inside
                    if sum(overlap(x, b, rs, re) for rs, re in li.robot_speech) > 0.5]
        if on_robot:
            print(f"   CHECK: {len(on_robot)} label(s) overlap the robot's prompts by > 0.5 s, at WAV time "
                  + ", ".join(f"{x - off:.1f}" for x, _, _ in on_robot[:6]))
        dup = cross = 0.0
        longest = (0.0, None)
        for i, (x, b, s) in enumerate(inside):
            for y, c, t in inside[i + 1:]:
                o = overlap(x, b, y, c)
                if o <= 0:
                    continue
                if s == t:
                    dup += o
                else:
                    cross += o
                    if o > longest[0]:
                        longest = (o, x - off)
        if dup > 0:
            problems += 1
            print(f"   PROBLEM: the same seat is labelled twice at once for {dup:.1f} s (duplicate labels)")
        if cross > 0:
            print(f"   overlap between people: {cross:.1f} s ({100 * cross / max(sum(per), 1e-9):.0f}% of speech); "
                  f"longest {longest[0]:.1f} s at WAV {longest[1]:.1f} s"
                  + ("  <- listen again: long overlaps are rare" if longest[0] > 3 else ""))

        if wav_s:
            loud, _, _ = speech_stretches(a.audio)
            loud = [(x + off, b + off) for x, b in loud]
            loud = [(x, b) for x, b, _ in clip([(x, b, 0) for x, b in loud], li.start, li.end)]
            free = []
            for x, b in loud:     # loud audio while the robot is silent
                if not any(overlap(x, b, rs - 0.3, re + 0.3) > 0 for rs, re in li.robot_speech):
                    free.append((x, b))
            loud_s = sum(b - x for x, b in free)
            covered = sum(overlap(x, b, y, c) for x, b in free for y, c, _ in inside)
            lab_s = sum(b - x for x, b, _ in inside)
            lab_loud = sum(overlap(y, c, x, b) for y, c, _ in inside for x, b in loud)
            cov = min(1.0, covered / loud_s) if loud_s else float("nan")
            quiet = 1 - min(1.0, lab_loud / lab_s) if lab_s else float("nan")
            print(f"   coverage: {100 * cov:.0f}% of loud non-robot audio is labelled; "
                  f"{100 * quiet:.0f}% of labelled time is quiet in the recording")
            if cov < 0.6:
                print("   CHECK: low coverage - speech may be missing (or the room was noisy: listen to the gaps)")

        if a.ticks and Path(a.ticks).exists():
            rows = tick_rows(a.ticks)
            exact, n = h2(rows, inside)
            shrunk = [(x + EDGE_S, b - EDGE_S, s) for x, b, s in inside if b - x > 2 * EDGE_S]
            tight, _ = h2(rows, shrunk)
            print(f"   H2 on this attempt: {exact:.3f} as labelled, {tight:.3f} with edges shrunk by {EDGE_S} s "
                  f"({n:.0f} s of single-speaker speech)")
    print(f"\n{'No blocking problems.' if problems == 0 else f'{problems} PROBLEM(S) above: fix them, then re-run.'}")


if __name__ == "__main__":
    main()
