"""
[ANALYSIS]
    python analyze_study.py ./logs/study_sessions.csv \
        --questionnaire ./logs/questionnaires.xlsx --seat-map seat_map.csv --out ./logs/results

Input: study_sessions.csv from build_sessions.py (one row per attempt; a re-run round has several).
Speech labels (labels/<stem>.csv) are needed for H1/H2; everything else works without them.

Sections of the printout (and CSVs in --out):
  A  Data check         every attempt: complete?, labels?, offset, same prompt audio + code everywhere
  B  Robot behaviour    per round: duration, questions asked, who was addressed, how listening ended
                        -> manipulation check: did balancing address people differently from random?
  C  Robot's estimate   speaking time per seat as the robot measured it live (NOT ground truth)
  D  H1 / H0            Gini of annotated speaking time per round, paired by group, one-sided Wilcoxon
                        signed-rank (exact), rank-biserial r, groups improved, order A vs B (carryover);
                        secondary: Gini of turns only (>= 1 s), Micbot unevenness, quiet member's share
  E  H2                 share of annotated speech time the live robot assigned to the right seat,
                        overall / per seat / per condition / per room, confusion matrix
  F  Mechanism          after each question: share of the following talk by the person addressed
  G  Validity           robot's estimated share vs annotated share per person (Spearman)
  H  Questionnaire      perceived fairness: per participant (n = 21) and per group (n = 7, independent)

Choices built in:
  * speaking time is counted from the robot's intro to the end of its outro (the "I'm in seat k"
    introductions before the intro are excluded - onyl present for for manual annotations);
  * a round with several included attempts adds up the attempts (include = 0 in study_sessions.csv
    leaves an attempt out; --only-complete keeps only attempts that asked all 6 questions);
  * ticks are weighted by their real duration (~0.12 s, capped at 0.5 s), not counted;
  * H2: ticks with overlapping labelled speech and ticks while the robot speaks are left out;
    "nobody" from the robot on labelled speech counts as wrong.
"""

import argparse
import csv
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from facilitator.study_data import (N_SEATS, audio_offset, clip, gini, micbot_unevenness, read_labels, read_log,
                                    read_sessions, rounds_of, speakers_at, speaking_time, tick_rows)


# ----------------------------------------------------------------------------- statistics helpers
def wilcoxon(diffs: List[float], alternative: str):
    """Paired Wilcoxon signed-rank on differences + matched-pairs rank-biserial r.

    Differences are rounded to 6 decimals first, so equal Likert differences tie exactly
    (floating-point noise would otherwise break ties and change the ranks).
    r = (sum of positive ranks - sum of negative ranks) / total: r < 0 = balancing lower than random."""
    nz = [round(d, 6) for d in diffs if round(d, 6) != 0]
    if len(nz) < 2:
        return None
    from scipy.stats import rankdata
    from scipy.stats import wilcoxon as w

    res = w(nz, alternative=alternative)
    ranks = rankdata([abs(d) for d in nz])
    pos = sum(r for r, d in zip(ranks, nz) if d > 0)
    neg = sum(r for r, d in zip(ranks, nz) if d < 0)
    return res.statistic, res.pvalue, (pos - neg) / (pos + neg), len(nz)


def fmt_test(t, label: str) -> str:
    if t is None:
        return f"   {label}: too few non-zero differences for a test"
    stat, p, r, n = t
    return (f"   {label}: W = {stat:.1f}, p = {p:.4f} (n = {n} non-zero), rank-biserial r = {r:+.2f} "
            f"(r < 0: balancing lower)")


def spearman(x, y):
    from scipy.stats import spearmanr

    if len(x) < 3:
        return None
    res = spearmanr(x, y)
    return res.statistic if hasattr(res, "statistic") else res.correlation, res.pvalue


def write_csv(path: Path, rows: List[dict]) -> None:
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


# ----------------------------------------------------------------------------- questionnaire
def read_questionnaire(path: str) -> List[dict]:
    """Rows: participant, group, order, condition (baseline|adaptive), fairness, items...

    Accepts the merged workbook (sheet "Long") or a CSV group,condition,participant,fairness."""
    out = []
    if path.lower().endswith((".xlsx", ".xlsm")):
        import openpyxl

        ws = openpyxl.load_workbook(path, data_only=True)["Long"]
        rows = list(ws.iter_rows(values_only=True))
        head = [str(h) for h in rows[0]]
        for r in rows[1:]:
            if not r or r[0] is None:
                continue
            d = dict(zip(head, r))
            cond = {"Random": "baseline", "Balancing": "adaptive"}.get(str(d["Condition"]), str(d["Condition"]))
            out.append({"participant": d["ID"], "group": f"G{int(d['Group']):02d}", "order": d.get("Order"),
                        "condition": cond, "fairness": float(d["Fairness score"]),
                        "share_thoughts": d.get("Share thoughts"), "fair_chance": d.get("Fair chance"),
                        "included": d.get("Included")})
    else:
        with open(path, newline="") as f:
            for d in csv.DictReader(f):
                out.append({"participant": d["participant"], "group": d["group"], "order": d.get("order"),
                            "condition": d["condition"], "fairness": float(d["fairness"])})
    return out


def read_seat_map(path: Optional[str]) -> Dict[tuple, str]:
    """seat_map.csv: group,seat,participant -> {(group, seat 1-based): participant}."""
    if not path:
        return {}
    with open(path, newline="") as f:
        return {(r["group"].strip(), int(r["seat"])): r["participant"].strip() for r in csv.DictReader(f)
                if (r.get("participant") or "").strip()}


# ----------------------------------------------------------------------------- main
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("sessions")
    p.add_argument("--questionnaire", help="questionnaires.xlsx (sheet 'Long') or questionnaire.csv")
    p.add_argument("--seat-map", help="seat_map.csv: group,seat,participant (links people to seats)")
    p.add_argument("--out", help="folder for result CSVs and figures")
    p.add_argument("--only-complete", action="store_true",
                   help="sensitivity check: leave out attempts that did not ask all 6 questions")
    args = p.parse_args()
    out = Path(args.out).expanduser() if args.out else None
    if out:
        out.mkdir(parents=True, exist_ok=True)

    attempts = read_sessions(args.sessions)
    seat_map = read_seat_map(args.seat_map)
    logs = {a.log: read_log(a.log) for a in attempts if a.log and Path(a.log).exists()}
    if args.only_complete:
        for a in attempts:
            if a.log in logs and not logs[a.log].all_questions:
                a.include = False

    # ================================================================ A  data check
    print("=" * 100 + "\nA  DATA CHECK (every attempt)\n" + "=" * 100)
    print("done = reached the end of the script; dec = questions asked (6 = all; --only-complete keeps those)")
    print(f"{'group':6s} {'rnd':>3s} {'att':>3s} {'condition':9s} {'incl':>4s} {'done':>4s} {'dec':>3s} "
          f"{'min':>5s} {'labels':>6s} {'offset':>8s}  code / prompt audio")
    codes, audio_hashes = Counter(), Counter()
    has_labels = {}
    for a in attempts:
        li = logs.get(a.log)
        off = audio_offset(a)
        lab = bool(a.labels) and Path(a.labels).exists()
        has_labels[a.log] = lab
        dur = (li.end - li.start) / 60 if li and li.start and li.end else float("nan")
        if li:
            codes[li.code] += 1
            audio_hashes[li.prompt_audio] += 1
        print(f"{a.group:6s} {a.round:3d} {a.attempt:3d} {a.condition:9s} {int(a.include):4d} "
              f"{int(bool(li and li.completed)):4d} {len(li.decisions) if li else 0:3d} {dur:5.1f} "
              f"{'yes' if lab else 'NO':>6s} {'' if off is None else f'{off:.1f}':>8s}  "
              f"{li.code if li else '?'} / {li.prompt_audio if li else '?'}")
    print(f"\nPrompt audio fingerprints: {dict(audio_hashes)}"
          + ("  -> identical in every attempt (controlled variable OK)" if len(audio_hashes) == 1 else
             "  -> NOT identical: say so in the report"))
    print(f"Code versions: {dict(codes)}" + ("  ('-dirty' = uncommitted changes when it ran)"
                                             if any('dirty' in c for c in codes) else ""))
    missing = [Path(a.log).stem for a in attempts if a.include and not has_labels.get(a.log)]
    if missing:
        print(f"Labels missing for {len(missing)} included attempt(s): H1, H2, F and G skip those rounds.")

    rounds = rounds_of(attempts)
    groups = sorted({k[0] for k in rounds})

    # ================================================================ B  robot behaviour
    print("\n" + "=" * 100 + "\nB  ROBOT BEHAVIOUR per round (manipulation check)\n" + "=" * 100)
    print(f"{'group':6s} {'ord':3s} {'rnd':>3s} {'condition':9s} {'att':>3s} {'min':>5s} {'questions':>9s} "
          f"{'addressed 1/2/3':>15s} {'quiet':>5s} {'quiet addr':>10s}  listening ended by")
    round_rows = {}
    for (g, rn), atts in rounds.items():
        a0 = atts[0]
        lis = [logs[a.log] for a in atts if a.log in logs]
        addressed = [0] * N_SEATS
        reasons = Counter()
        for li in lis:
            for _, s, _ in li.decisions:
                addressed[s] += 1
            reasons.update(r for r, _, _ in li.listen_ends)
        minutes = sum((li.end - li.start) / 60 for li in lis if li.start and li.end)
        q = a0.quiet_seat
        row = {"group": g, "order": a0.order, "round": rn, "topic": a0.topic, "condition": a0.condition,
               "attempts": len(atts), "minutes": round(minutes, 2), "questions": sum(addressed),
               "addr_1": addressed[0], "addr_2": addressed[1], "addr_3": addressed[2], "quiet_seat": q,
               "quiet_addressed": addressed[q - 1] if q else "",
               "listen_end": " ".join(f"{k}:{v}" for k, v in sorted(reasons.items()))}
        round_rows[(g, rn)] = row
        print(f"{g:6s} {a0.order:3s} {rn:3d} {a0.condition:9s} {len(atts):3d} {minutes:5.1f} {sum(addressed):9d} "
              f"{'/'.join(map(str, addressed)):>15s} {q or '-':>5} {row['quiet_addressed']:>10}  {row['listen_end']}")
    for cond in ("baseline", "adaptive"):
        rr = [r for r in round_rows.values() if r["condition"] == cond]
        if rr:
            mins = [r["minutes"] for r in rr]
            qa = [r["quiet_addressed"] for r in rr if r["quiet_addressed"] != ""]
            print(f"   {cond:9s}: {len(rr)} rounds, {st.mean(mins):.1f} min on average (range {min(mins):.1f}-"
                  f"{max(mins):.1f}); quiet member addressed {st.mean(qa) if qa else float('nan'):.2f} of 6 on average")
    print("   Balanced random addresses everyone exactly twice. If balancing rounds also show 2/2/2, the robot\n"
          "   behaved the same in both conditions in that group and no difference in participation is expected.")

    # ================================================================ C  robot's own estimate
    print("\n" + "=" * 100 + "\nC  ROBOT'S OWN ESTIMATE (live attribution, tick-duration weighted) - NOT ground truth\n"
          + "=" * 100)
    robot_est = {}
    for key, atts in rounds.items():
        tot = [0.0] * N_SEATS
        for a in atts:
            if not a.ticks or not Path(a.ticks).exists():
                continue
            for r in tick_rows(a.ticks):
                if r["robot_speaking"] == "0" and r["seat"]:
                    tot[int(r["seat"]) - 1] += r["dt"]
        robot_est[key] = tot
        rr = round_rows[key]
        rr.update({"robot_s1": round(tot[0], 1), "robot_s2": round(tot[1], 1), "robot_s3": round(tot[2], 1),
                   "robot_gini": round(gini(tot), 4)})
        print(f"{key[0]:6s} R{key[1]} {rr['condition']:9s} robot-estimated speaking s 1/2/3 = "
              f"{tot[0]:6.1f} / {tot[1]:6.1f} / {tot[2]:6.1f}   Gini {gini(tot):.3f}")

    # ================================================================ D  H1
    print("\n" + "=" * 100 + "\nD  H1 / H0: evenness of ANNOTATED speaking time\n" + "=" * 100)
    labels_by_round: Dict[tuple, list] = {}   # key -> list of (attempt, labels on session clock, clipped)
    for key, atts in rounds.items():
        if not all(has_labels.get(a.log) for a in atts):
            continue
        per = []
        for a in atts:
            off = audio_offset(a)
            li = logs.get(a.log)
            per.append((a, clip(read_labels(a.labels, off or 0.0), li.start if li else None, li.end if li else None)))
        labels_by_round[key] = per
    for key, per in labels_by_round.items():
        allv = [sum(x) for x in zip(*[speaking_time(lab) for _, lab in per])]
        turns = [sum(x) for x in zip(*[speaking_time(lab, "turns") for _, lab in per])]
        rr = round_rows[key]
        q = rr["quiet_seat"]
        rr.update({"s1": round(allv[0], 1), "s2": round(allv[1], 1), "s3": round(allv[2], 1),
                   "gini": round(gini(allv), 4), "gini_turns": round(gini(turns), 4),
                   "micbot_unevenness": round(micbot_unevenness(allv), 2),
                   "quiet_share": round(allv[q - 1] / sum(allv), 4) if q and sum(allv) else ""})
    if labels_by_round:
        print(f"{'group':6s} {'ord':3s} {'rnd':>3s} {'condition':9s} {'Gini':>6s} {'Gini turns':>10s} "
              f"{'unevenness':>10s} {'speaking s 1/2/3':>22s} {'quiet share':>11s}")
        for key in labels_by_round:
            r = round_rows[key]
            print(f"{r['group']:6s} {r['order']:3s} {r['round']:3d} {r['condition']:9s} {r['gini']:6.3f} "
                  f"{r['gini_turns']:10.3f} {r['micbot_unevenness']:10.1f} "
                  f"{r['s1']:6.1f} /{r['s2']:6.1f} /{r['s3']:6.1f} {r['quiet_share']:>11}")
    group_rows = []
    for g in groups:
        b, ad = round_rows.get(next((k for k in round_rows if k[0] == g and round_rows[k]["condition"] == "baseline"),
                                    None)), \
            round_rows.get(next((k for k in round_rows if k[0] == g and round_rows[k]["condition"] == "adaptive"), None))
        if not b or not ad:
            continue
        row = {"group": g, "order": b["order"]}
        for m in ("gini", "gini_turns", "micbot_unevenness", "quiet_share", "robot_gini"):
            if b.get(m, "") != "" and ad.get(m, "") != "":
                row[f"{m}_random"], row[f"{m}_balancing"] = b[m], ad[m]
                row[f"{m}_diff"] = round(ad[m] - b[m], 4)
        group_rows.append(row)

    def paired_report(metric: str, label: str, alternative: str):
        rows = [r for r in group_rows if f"{metric}_diff" in r]
        if not rows:
            return
        diffs = [r[f"{metric}_diff"] for r in rows]
        better = sum((d < 0) if alternative == "less" else (d > 0) for d in diffs)
        print(f"\n{label} (balancing - random per group; {'negative' if alternative == 'less' else 'positive'}"
              f" = in the hypothesised direction)")
        for r in rows:
            print(f"   {r['group']:6s} order {r['order']}: random {r[f'{metric}_random']:.3f}  balancing "
                  f"{r[f'{metric}_balancing']:.3f}  diff {r[f'{metric}_diff']:+.3f}")
        print(f"   median difference {st.median(diffs):+.3f}, mean {st.mean(diffs):+.3f}; "
              f"{better}/{len(diffs)} groups in the hypothesised direction")
        print(fmt_test(wilcoxon(diffs, alternative), f"one-sided Wilcoxon ({alternative})"))
        for order in ("A", "B"):
            sub = [r[f"{metric}_diff"] for r in rows if r["order"] == order]
            if sub:
                print(f"   order {order}: median {st.median(sub):+.3f} (n = {len(sub)})   <- carryover check")

    if labels_by_round:
        paired_report("gini", "H1 PRIMARY - Gini of all annotated speech", "less")
        paired_report("gini_turns", "Secondary - Gini of speaking turns only (stretches >= 1 s)", "less")
        paired_report("micbot_unevenness", "Secondary - Micbot unevenness (% points)", "less")
        paired_report("quiet_share", "Secondary - quiet member's share of speaking time", "greater")
        print("\n   With 7 groups the smallest possible one-sided exact p is 1/128 = 0.008 (all 7 in the same"
              " direction);\n   report the per-group differences and r, not only p.")
    else:
        print("No round has labels yet. Robot-estimate version below is PRELIMINARY (the robot measuring itself).")
    paired_report("robot_gini", "Robot-estimated Gini (instrument, not ground truth; for a first look only)", "less")

    # ================================================================ E  H2
    print("\n" + "=" * 100 + "\nE  H2: live speaker attribution vs annotation (speech-time weighted)\n" + "=" * 100)
    conf = defaultdict(float)            # (truth seat, predicted) -> seconds; predicted 0 = nobody
    by = defaultdict(lambda: [0.0, 0.0])  # (dimension, value) -> [speech s, correct s]
    silence = defaultdict(lambda: [0.0, 0.0])  # condition -> [unlabelled listening s, s the robot gave to a seat]
    per_round_h2 = {}
    for key, per in labels_by_round.items():
        cond = round_rows[key]["condition"]
        ok_r = n_r = 0.0
        for a, lab in per:
            if not a.ticks or not Path(a.ticks).exists():
                continue
            room = Path(a.params).stem if a.params else "?"
            for r in tick_rows(a.ticks):
                if r["robot_speaking"] == "1":
                    continue
                who = speakers_at(lab, r["t"])
                if not who and (not lab or lab[0][0] <= r["t"] <= max(b for _, b, _ in lab)):
                    silence[cond][0] += r["dt"]
                    silence[cond][1] += r["dt"] if r["seat"] else 0.0
                if len(who) != 1:
                    continue
                s = next(iter(who))
                pred = int(r["seat"]) if r["seat"] else 0
                conf[(s + 1, pred)] += r["dt"]
                ok = r["dt"] if pred == s + 1 else 0.0
                for dim in (("all", "all"), ("seat", s + 1), ("condition", cond), ("room", room), ("group", key[0])):
                    by[dim][0] += r["dt"]
                    by[dim][1] += ok
                n_r += r["dt"]
                ok_r += ok
        per_round_h2[key] = ok_r / n_r if n_r else None
        round_rows[key]["h2"] = round(ok_r / n_r, 4) if n_r else ""
    if by[("all", "all")][0]:
        n, ok = by[("all", "all")]
        print(f"Overall: {ok / n:.3f} of {n / 60:.1f} min of single-speaker annotated speech "
              f"({'meets' if ok / n >= 0.80 else 'BELOW'} the 0.80 target)")
        for dim in ("seat", "condition", "room", "group"):
            vals = sorted((k[1], v) for k, v in by.items() if k[0] == dim)
            print(f"   per {dim:9s}: " + ", ".join(f"{name} {v[1] / v[0]:.3f}" for name, v in vals if v[0]))
        print("   confusion (rows = annotated seat, columns = robot said; seconds):")
        print("        " + "".join(f"{h:>9s}" for h in ("nobody", "seat 1", "seat 2", "seat 3")))
        for s in range(1, N_SEATS + 1):
            print(f"   seat {s}" + "".join(f"{conf[(s, pcol)]:9.1f}" for pcol in range(0, N_SEATS + 1)))
        print("   A large 'nobody' column = the robot was unsure (speech flag off or belief < 0.55), not wrong-seat.")
        tot = [sum(v[0] for v in silence.values()), sum(v[1] for v in silence.values())]
        if tot[0]:
            print(f"   FALSE SPEECH: in {tot[0] / 60:.1f} min of listening where nobody was labelled, the robot still credited "
                  f"a seat {tot[1] / tot[0]:.2f} of the time (" + ", ".join(f"{c} {v[1] / v[0]:.2f}" for c, v in
                                                                        sorted(silence.items()) if v[0]) + ").")
            print("   H2 only measures labelled speech; this is the other side (precision). High = speaking time is")
            print("   over-counted, which can make the robot misjudge who is least active.")
        if out:
            write_csv(out / "h2_confusion.csv", [{"annotated_seat": s, **{f"robot_{'nobody' if c == 0 else c}":
                                                 round(conf[(s, c)], 2) for c in range(N_SEATS + 1)}}
                                                for s in range(1, N_SEATS + 1)])
    else:
        print("No labels yet.")

    # ================================================================ F  mechanism
    print("\n" + "=" * 100 + "\nF  MECHANISM: did the person addressed take the floor?\n" + "=" * 100)
    dec_rows = []
    for key, per in labels_by_round.items():
        cond = round_rows[key]["condition"]
        for a, lab in per:
            li = logs.get(a.log)
            if li is None:
                continue
            times = [d[0] for d in li.decisions] + [li.end]
            for i, (t, seat, act) in enumerate(li.decisions):
                window = speaking_time(clip(lab, t, times[i + 1]))
                tot = sum(window)
                dec_rows.append({"group": key[0], "round": key[1], "attempt": a.attempt, "condition": cond,
                                 "question": i + 1, "addressed": seat + 1, "talk_s": round(tot, 1),
                                 "addressee_share": round(window[seat] / tot, 3) if tot else "",
                                 "addressee_spoke": int(window[seat] >= 1.0),
                                 "quiet_addressed": int(seat + 1 == a.quiet_seat) if a.quiet_seat else ""})
    if dec_rows:
        for cond in ("baseline", "adaptive"):
            d = [r for r in dec_rows if r["condition"] == cond and r["addressee_share"] != ""]
            if d:
                print(f"   {cond:9s}: {len(d)} questions; addressee produced {st.mean(r['addressee_share'] for r in d):.2f}"
                      f" of the following talk (chance 0.33); addressee spoke >= 1 s after "
                      f"{st.mean(r['addressee_spoke'] for r in d):.2f} of questions")
        print("   High shares in BOTH conditions = being addressed works; balancing can only help if it addresses"
              " the right people.")
    else:
        print("No labels yet.")

    # ================================================================ G  validity
    print("\n" + "=" * 100 + "\nG  VALIDITY: robot's estimated share vs annotated share (per person and round)\n"
          + "=" * 100)
    xs, ys = [], []
    for key in labels_by_round:
        r, est = round_rows[key], robot_est[key]
        ann = [r["s1"], r["s2"], r["s3"]]
        if sum(ann) and sum(est):
            xs += [v / sum(est) for v in est]
            ys += [v / sum(ann) for v in ann]
    sp = spearman(xs, ys) if xs else None
    if sp:
        print(f"   Spearman rho = {sp[0]:.2f} (p = {sp[1]:.4f}) over {len(xs)} person-rounds; mean absolute share "
              f"error {st.mean(abs(a - b) for a, b in zip(xs, ys)):.3f}")
    else:
        print("No labels yet.")

    # ================================================================ H  questionnaire
    q_rows = read_questionnaire(args.questionnaire) if args.questionnaire else []
    if q_rows:
        print("\n" + "=" * 100 + "\nH  PERCEIVED FAIRNESS (1-5; mean of share thoughts, fair chance, included)\n"
              + "=" * 100)
        by_p = defaultdict(dict)
        for r in q_rows:
            by_p[(r["group"], r["participant"])][r["condition"]] = r["fairness"]
        diffs = [d["adaptive"] - d["baseline"] for d in by_p.values() if "adaptive" in d and "baseline" in d]
        print(f"   per participant (n = {len(diffs)}): mean random "
              f"{st.mean(d['baseline'] for d in by_p.values() if 'baseline' in d):.2f}, mean balancing "
              f"{st.mean(d['adaptive'] for d in by_p.values() if 'adaptive' in d):.2f}, median diff "
              f"{st.median(diffs):+.2f}")
        print(fmt_test(wilcoxon(diffs, "two-sided"), "two-sided Wilcoxon, participants (not independent: 3 per group)"))
        g_means = defaultdict(lambda: defaultdict(list))
        orders = {}
        for r in q_rows:
            g_means[r["group"]][r["condition"]].append(r["fairness"])
            orders[r["group"]] = r["order"]
        g_diffs = {g: st.mean(v["adaptive"]) - st.mean(v["baseline"]) for g, v in g_means.items()
                   if v["adaptive"] and v["baseline"]}
        print(fmt_test(wilcoxon(list(g_diffs.values()), "two-sided"), "two-sided Wilcoxon, group means (n = 7)"))
        for order in ("A", "B"):
            sub = [d for g, d in g_diffs.items() if orders.get(g) == order]
            if sub:
                print(f"   order {order}: mean group diff {st.mean(sub):+.2f} (n = {len(sub)})   <- carryover check")
        for row in group_rows:
            if row["group"] in g_diffs:
                row["fairness_diff"] = round(g_diffs[row["group"]], 3)
        if seat_map:
            print("   quiet member (seat from the logs, person from seat_map.csv):")
            for (g, rn), r in sorted(round_rows.items()):
                pid = seat_map.get((g, r["quiet_seat"]))
                f = by_p.get((g, pid), {}).get(r["condition"]) if pid else None
                r["quiet_participant"], r["quiet_fairness"] = pid or "", "" if f is None else round(f, 3)
            for g in groups:
                rr = [r for k, r in round_rows.items() if k[0] == g]
                if rr and rr[0].get("quiet_participant"):
                    txt = ", ".join(f"{r['condition']} fairness {r['quiet_fairness']} share {r.get('quiet_share', '')}"
                                    for r in rr)
                    print(f"      {g} {rr[0]['quiet_participant']} (seat {rr[0]['quiet_seat']}): {txt}")

    # ================================================================ outputs
    if out:
        write_csv(out / "rounds.csv", list(round_rows.values()))
        write_csv(out / "groups.csv", group_rows)
        write_csv(out / "decisions.csv", dec_rows)
        make_figures(out, group_rows, dec_rows)
        print(f"\nSaved rounds.csv, groups.csv, decisions.csv, h2_confusion.csv and figures in {out}")


def make_figures(out: Path, group_rows: List[dict], dec_rows: List[dict]) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("(matplotlib not installed: no figures)")
        return
    metric = "gini" if any("gini_diff" in r for r in group_rows) else "robot_gini"
    rows = [r for r in group_rows if f"{metric}_diff" in r]
    if rows:
        fig, ax = plt.subplots(figsize=(4.2, 3.6))
        for r in rows:
            c = "#2b6cb0" if r[f"{metric}_diff"] < 0 else "#c05621"
            ax.plot([0, 1], [r[f"{metric}_random"], r[f"{metric}_balancing"]], "-o", color=c, alpha=0.85)
            ax.annotate(r["group"], (1.03, r[f"{metric}_balancing"]), fontsize=8, va="center")
        ax.set_xticks([0, 1], ["Random", "Balancing"])
        ax.set_xlim(-0.2, 1.3)
        ax.set_ylabel("Gini of speaking time" + (" (robot estimate)" if metric == "robot_gini" else ""))
        ax.set_title("Per group: lower = more even", fontsize=10)
        fig.tight_layout()
        fig.savefig(out / f"fig_{metric}_pairs.png", dpi=200)
        plt.close(fig)
    if dec_rows:
        fig, ax = plt.subplots(figsize=(4.2, 3.2))
        for i, cond in enumerate(("baseline", "adaptive")):
            v = [r["addressee_share"] for r in dec_rows if r["condition"] == cond and r["addressee_share"] != ""]
            if v:
                ax.bar(i, st.mean(v), color="#a0aec0" if i == 0 else "#2b6cb0")
                ax.errorbar(i, st.mean(v), yerr=(st.stdev(v) / len(v) ** 0.5) if len(v) > 1 else 0, color="k")
        ax.axhline(1 / 3, ls="--", color="grey", lw=1)
        ax.set_xticks([0, 1], ["Random", "Balancing"])
        ax.set_ylabel("Addressee's share of following talk")
        fig.tight_layout()
        fig.savefig(out / "fig_addressee_share.png", dpi=200)
        plt.close(fig)


if __name__ == "__main__":
    main()
