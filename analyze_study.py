"""Analyse the study (report sections 1.2 and 1.4). No robot needed.

    python analyze_study.py study_sessions.csv [--questionnaire questionnaire.csv] [--out results/study.csv]

study_sessions.csv - one row per round (14 rows for 7 groups), see study_sessions_template.csv:
    group,order,round,topic,condition,quiet_seat,labels,offset,ticks,log,audio
      condition   baseline | adaptive
      labels      annotated video: start_s,end_s,seat  (who spoke when; the ground truth)
      offset      seconds added to label times to reach the tick-log clock (only needed for H2).
                  Leave EMPTY when the labels were made on the --record audio: it is then read
                  automatically from <audio>.json (exact, no clap needed)
      audio       the round's *_audio.wav from run_session.py --record (optional)
      ticks       the round's *_ticks.csv (optional; needed for H2)
      log         the round's session log .csv (optional; checks equal robot behaviour)
      quiet_seat  seat of the self-reported quiet participant (optional, 0 = unknown)

questionnaire.csv (optional) - perceived fairness, one row per participant per round:
    group,condition,participant,fairness      (fairness = mean of the Likert items)

What it reports
    H1/H0  Gini of speaking time per round (lower = more even), paired difference
           (balancing - random) per group, one-sided Wilcoxon signed-rank test, rank-biserial
           effect size, and the same split by order A/B (carryover check, report Table 3).
    H2     share of annotated speech time the robot assigned to the correct seat (live, from
           the tick logs), overall and per seat (uneven-sensing check, report Table 3).
    Also   quiet participant's share of speaking time; decisions per round and per seat
           (equal robot behaviour); perceived fairness (Wilcoxon, paired per participant).
"""

import argparse
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from facilitator.recorder import read_offset
from facilitator.sim_sources import load_labels, truth_at
from facilitator.simulation import gini

N_SEATS = 3


def speaking_time(labels_path: str) -> List[float]:
    out = [0.0] * N_SEATS
    for a, b, seat in load_labels(labels_path):
        out[seat] += b - a
    return out


def h2_counts(ticks_path: str, labels_path: str, offset: float) -> List[List[int]]:
    """Per seat: [ticks of annotated speech, ticks the robot assigned to that same seat]."""
    labels = load_labels(labels_path, offset)
    counts = [[0, 0] for _ in range(N_SEATS)]
    with open(ticks_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["robot_speaking"] == "1":
                continue
            truth = truth_at(labels, float(row["t"]))
            if truth is None:
                continue
            counts[truth][0] += 1
            counts[truth][1] += int(row["seat"] != "" and int(row["seat"]) - 1 == truth)
    return counts


def robot_behaviour(log_path: str) -> List[int]:
    addressed = [0] * N_SEATS
    with open(log_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["event"] == "decision" and row["seat"]:
                addressed[int(row["seat"]) - 1] += 1
    return addressed


def wilcoxon_less(diffs: List[float]) -> Optional[tuple]:
    """One-sided Wilcoxon signed-rank (H1: balancing - random < 0) + rank-biserial effect size."""
    nonzero = [d for d in diffs if d != 0]
    if len(nonzero) < 2:
        return None
    from scipy.stats import rankdata, wilcoxon

    res = wilcoxon(nonzero, alternative="less")
    ranks = rankdata([abs(d) for d in nonzero])
    pos = sum(r for r, d in zip(ranks, nonzero) if d > 0)
    neg = sum(r for r, d in zip(ranks, nonzero) if d < 0)
    effect = (neg - pos) / (pos + neg)  # +1 = every group more even with balancing
    return res.statistic, res.pvalue, effect


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sessions")
    p.add_argument("--questionnaire")
    p.add_argument("--out")
    args = p.parse_args()
    base = Path(args.sessions).resolve().parent
    rows = list(csv.DictReader(open(args.sessions, newline="")))

    def path(value: str) -> str:
        return str((base / value).resolve()) if value and not Path(value).is_absolute() else value

    per_round, h2 = [], [[0, 0] for _ in range(N_SEATS)]
    print(f"{'group':6s} {'ord':3s} {'rnd':3s} {'topic':5s} {'condition':9s} {'Gini':>6s} "
          f"{'speaking s (seat 1/2/3)':>26s} {'quiet share':>11s} {'addressed':>10s}")
    for r in rows:
        times = speaking_time(path(r["labels"]))
        g = gini(times)
        quiet = int(r.get("quiet_seat") or 0)
        quiet_share = times[quiet - 1] / sum(times) if quiet and sum(times) else None
        addressed = robot_behaviour(path(r["log"])) if r.get("log") else None
        if r.get("ticks"):
            if r.get("offset"):
                offset = float(r["offset"])
            elif r.get("audio"):  # labels made on the --record audio: exact offset from its sidecar
                offset = read_offset(Path(path(r["audio"])).with_suffix(".json"))
            else:
                offset = 0.0
            for k, (n, ok) in enumerate(h2_counts(path(r["ticks"]), path(r["labels"]), offset)):
                h2[k][0] += n
                h2[k][1] += ok
        per_round.append({**r, "gini": g, "speaking_s": times, "quiet_share": quiet_share, "addressed": addressed})
        print(f"{r['group']:6s} {r['order']:3s} {r['round']:3s} {r['topic']:5s} {r['condition']:9s} {g:6.3f} "
              f"{' / '.join(f'{t:6.1f}' for t in times):>26s} "
              f"{'' if quiet_share is None else f'{quiet_share:.2f}':>11s} {'' if addressed is None else str(addressed):>10s}")

    # ---------------- H1 / H0: paired by group
    by_group: Dict[str, Dict[str, dict]] = defaultdict(dict)
    for r in per_round:
        by_group[r["group"]][r["condition"]] = r
    pairs = {gname: d["adaptive"]["gini"] - d["baseline"]["gini"] for gname, d in by_group.items()
             if "adaptive" in d and "baseline" in d}
    print("\nH1/H0 - Gini difference (balancing - random) per group, negative = balancing more even:")
    for gname, diff in pairs.items():
        print(f"   {gname:6s} order {by_group[gname]['adaptive']['order']}: {diff:+.3f}")
    if pairs:
        diffs = list(pairs.values())
        print(f"   median difference {st.median(diffs):+.3f} over {len(diffs)} groups; "
              f"{sum(d < 0 for d in diffs)}/{len(diffs)} groups more even with balancing")
        test = wilcoxon_less(diffs)
        if test:
            stat, pval, eff = test
            print(f"   Wilcoxon signed-rank (one-sided): W = {stat:.1f}, p = {pval:.4f}; rank-biserial r = {eff:+.2f}")
        for order in ("A", "B"):
            sub = [d for g, d in pairs.items() if by_group[g]["adaptive"]["order"] == order]
            if sub:
                print(f"   order {order}: median {st.median(sub):+.3f} (n = {len(sub)})  <- carryover check")

    # ---------------- H2
    if any(n for n, _ in h2):
        total, ok = sum(n for n, _ in h2), sum(o for _, o in h2)
        print(f"\nH2 - annotated speech time assigned to the correct seat (live robot decisions): "
              f"{ok / total:.3f} ({'meets' if ok / total >= 0.80 else 'BELOW'} 0.80)")
        print("   per seat: " + ", ".join(f"seat {k + 1} {o / n:.3f} (n={n})" for k, (n, o) in enumerate(h2) if n))

    # ---------------- perceived fairness
    if args.questionnaire:
        q = defaultdict(dict)
        for row in csv.DictReader(open(args.questionnaire, newline="")):
            q[(row["group"], row["participant"])][row["condition"]] = float(row["fairness"])
        diffs = [d["adaptive"] - d["baseline"] for d in q.values() if "adaptive" in d and "baseline" in d]
        if diffs:
            from scipy.stats import wilcoxon

            nz = [d for d in diffs if d != 0]
            p_two = wilcoxon(nz).pvalue if len(nz) >= 2 else float("nan")
            print(f"\nPerceived fairness (balancing - random), {len(diffs)} participants: "
                  f"median {st.median(diffs):+.2f}, Wilcoxon two-sided p = {p_two:.4f}")

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["group", "order", "round", "topic", "condition", "gini", "s_seat1", "s_seat2", "s_seat3",
                        "quiet_share"])
            for r in per_round:
                w.writerow([r["group"], r["order"], r["round"], r["topic"], r["condition"], f"{r['gini']:.4f}",
                            *[f"{t:.2f}" for t in r["speaking_s"]],
                            "" if r["quiet_share"] is None else f"{r['quiet_share']:.4f}"])
        print(f"\nSaved {args.out}")


if __name__ == "__main__":
    main()
