"""Participant-study analysis (H1/H0, H2, secondary measures). Run after annotation.

    python analyze_study.py study_sessions.csv [--questionnaire questionnaire.csv] [--out results/study.csv]
The computational comparison with the Micbot-style method (H3) is: python evaluate_offline.py study study_sessions.csv

study_sessions.csv - one row per round (14 rows for 7 groups), see templates/study_sessions_template.csv:
    group,order,round,topic,condition,quiet_seat,labels,offset,ticks,log
      condition   baseline | adaptive
      labels      annotated video: start_s,end_s,seat[,kind]  (who spoke when; the ground truth;
                  kind = turn | backchannel, optional)
      offset      seconds added to label times to reach the tick-log clock (only needed for H2);
                  get it with: python evaluate_offline.py offset --log <round log> --video-s <intro start in video>
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
           Ticks with overlapping speech or the robot's own voice are excluded; "nobody" = wrong.
    Also   Micbot's evenness measure (sum of |share - mean share|, in % points), for comparability;
           Gini of speaking-TURN time only (if labels have a kind column);
           quiet participant's share of speaking time (paired Wilcoxon);
           decisions per round and per seat (equal robot behaviour);
           perceived fairness (Wilcoxon, paired per participant).
Gini uses ALL annotated speech (turns + backchannels), as stated in the report.
"""

import argparse
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from facilitator.sim_sources import is_overlap, load_labels, truth_at
from facilitator.simulation import gini

N_SEATS = 3


def speaking_time(labels_path: str, kinds=("turn", "backchannel")) -> List[float]:
    out = [0.0] * N_SEATS
    for a, b, seat in load_labels(labels_path, kinds=kinds):
        out[seat] += b - a
    return out


def has_backchannel_labels(labels_path: str) -> bool:
    with open(labels_path, newline="") as f:
        return any((row.get("kind") or "").strip().lower() == "backchannel" for row in csv.DictReader(f))


def micbot_unevenness(times: List[float]) -> float:
    """Micbot's time measure: sum over people of |share of speaking time - mean share|, in % points."""
    total = sum(times)
    if total == 0:
        return 0.0
    shares = [100.0 * t / total for t in times]
    mean = sum(shares) / len(shares)
    return sum(abs(x - mean) for x in shares)


def h2_counts(ticks_path: str, labels_path: str, offset: float) -> List[List[int]]:
    """Per seat: [ticks of annotated speech, ticks the robot assigned to that same seat]."""
    labels = load_labels(labels_path, offset)
    counts = [[0, 0] for _ in range(N_SEATS)]
    with open(ticks_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["robot_speaking"] == "1":
                continue
            t = float(row["t"])
            truth = truth_at(labels, t)
            if truth is None or is_overlap(labels, t):
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


def wilcoxon_less(diffs: List[float], alternative: str = "less") -> Optional[tuple]:
    """One-sided Wilcoxon signed-rank (H1: balancing - random < 0) + rank-biserial effect size.

    Effect size: +1 = every group changed in the hypothesised direction ("less" -> negative diffs)."""
    nonzero = [d for d in diffs if d != 0]
    if len(nonzero) < 2:
        return None
    from scipy.stats import rankdata, wilcoxon

    res = wilcoxon(nonzero, alternative=alternative)
    ranks = rankdata([abs(d) for d in nonzero])
    pos = sum(r for r, d in zip(ranks, nonzero) if d > 0)
    neg = sum(r for r, d in zip(ranks, nonzero) if d < 0)
    effect = (neg - pos) / (pos + neg)  # +1 = all differences negative
    if alternative == "greater":
        effect = -effect
    return res.statistic, res.pvalue, effect


def paired(by_group: Dict[str, Dict[str, dict]], key: str) -> Dict[str, float]:
    """balancing - random of per_round[key], per group with both rounds and a value."""
    return {g: d["adaptive"][key] - d["baseline"][key] for g, d in by_group.items()
            if "adaptive" in d and "baseline" in d and d["adaptive"][key] is not None
            and d["baseline"][key] is not None}


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
        turns_only = gini(speaking_time(path(r["labels"]), kinds=("turn",))) \
            if has_backchannel_labels(path(r["labels"])) else None
        quiet = int(r.get("quiet_seat") or 0)
        quiet_share = times[quiet - 1] / sum(times) if quiet and sum(times) else None
        addressed = robot_behaviour(path(r["log"])) if r.get("log") else None
        if r.get("ticks"):
            for k, (n, ok) in enumerate(h2_counts(path(r["ticks"]), path(r["labels"]), float(r.get("offset") or 0))):
                h2[k][0] += n
                h2[k][1] += ok
        per_round.append({**r, "gini": g, "gini_turns": turns_only, "unevenness": micbot_unevenness(times),
                          "speaking_s": times, "quiet_share": quiet_share, "addressed": addressed})
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

    # ---------------- secondary measures (same pairing)
    if pairs:
        print("\nSecondary (balancing - random per group):")
        for key, label, alt in (("unevenness", "Micbot unevenness (% points, lower = more even)", "less"),
                                ("gini_turns", "Gini of speaking-turn time only", "less"),
                                ("quiet_share", "quiet participant's share of speaking time", "greater")):
            d = paired(by_group, key)
            if not d:
                continue
            vals = list(d.values())
            test = wilcoxon_less(vals, alternative=alt)
            extra = f"; Wilcoxon one-sided p = {test[1]:.4f}, r = {test[2]:+.2f}" if test else ""
            print(f"   {label}: median {st.median(vals):+.3f} over {len(vals)} groups{extra}")

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
            w.writerow(["group", "order", "round", "topic", "condition", "gini", "gini_turns", "micbot_unevenness",
                        "s_seat1", "s_seat2", "s_seat3", "quiet_share", "addressed"])
            for r in per_round:
                w.writerow([r["group"], r["order"], r["round"], r["topic"], r["condition"], f"{r['gini']:.4f}",
                            "" if r["gini_turns"] is None else f"{r['gini_turns']:.4f}", f"{r['unevenness']:.2f}",
                            *[f"{t:.2f}" for t in r["speaking_s"]],
                            "" if r["quiet_share"] is None else f"{r['quiet_share']:.4f}",
                            "" if r["addressed"] is None else " ".join(map(str, r["addressed"]))])
        print(f"\nSaved {args.out}")


if __name__ == "__main__":
    main()
