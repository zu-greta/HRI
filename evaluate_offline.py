"""Evaluate, tune and calibrate the detection methods without running a session.
(The computational evaluation of the project: our method vs the Micbot-style method.)

1) sim      Simulated groups: our method vs Micbot-style vs round-robin (no robot needed)
       python evaluate_offline.py sim                # default 100 sessions per group type
       python evaluate_offline.py sim --sessions 300 --out results/sim.csv

2) tune     Choose half_life_s and margin_s BEFORE the study (report: "fixed after offline tuning")
       python evaluate_offline.py tune --sessions 100 [--out results/tune.csv]

3) fit      Calibrate seats + microphone model from run_calibration.py output
       python evaluate_offline.py fit --ticks logs/CALIB_..._ticks.csv --labels logs/CALIB_..._labels.csv

4) offset   Video -> tick clock offset for one round (needed for labels made on the video)
       python evaluate_offline.py offset --log logs/G01_R1_T1_baseline_....csv --video-s 12.40
       (--video-s = time in the video when the robot starts the intro sentence)

5) replay   One recording against its labels: who-is-speaking accuracy, HMM vs nearest
       python evaluate_offline.py replay --ticks ..._ticks.csv --labels labels/G01_R1.csv --offset 1234.5

6) study    All recorded rounds (study_sessions.csv, same file as analyze_study.py):
            H2 for both attributors + paired test (H3a), and replayed DECISIONS:
            how often each full method (ours / Micbot-style) would have picked the truly
            least active person at the moments the robot actually decided (H3b)
       python evaluate_offline.py study study_sessions.csv [--out results/h3.csv]

Labels CSV: header start_s,end_s,seat[,kind]  (seat 1-based; kind = turn | backchannel;
only real speech, gaps = silence). --offset: seconds ADDED to label times to reach the tick clock.
Ticks with overlapping labelled speech or the robot's own voice are excluded from accuracy.
"""

import argparse
import csv
import json
import random
import statistics as st
from pathlib import Path
from typing import Dict, List

from facilitator.attribution import (expected_mic_head_deg, head_to_world_deg, make_attributor, mic_angle_to_head_deg,
                                     wrap_deg)
from facilitator.detection_config import PARAMS_FILE, DetectionConfig
from facilitator.seats import load_seat_azimuths, save_seat_azimuths
from facilitator.estimator import make_estimator
from facilitator.listener import ParticipationListener
from facilitator.policies import LeastActivePolicy, MicbotPolicy
from facilitator.sim_sources import MicModel, is_overlap, iter_ticks, load_labels, truth_at
from facilitator.simulation import METHODS, GroupModel, _talk_period, simulate_session

GROUPS = {
    "one_dominant": GroupModel(talkativeness=[0.6, 0.3, 0.1], responsiveness=[0.95, 0.9, 0.8]),
    "two_quiet": GroupModel(talkativeness=[0.7, 0.15, 0.15], responsiveness=[0.95, 0.75, 0.75]),
    "balanced": GroupModel(talkativeness=[0.34, 0.33, 0.33], responsiveness=[0.9, 0.9, 0.9]),
}


# ============================================================================ 1) simulation
def attribution_experiment(seats: List[float], mic: MicModel, det: DetectionConfig, n: int, seed: int) -> Dict:
    """Same simulated microphone stream through both attributors (paired comparison)."""
    rng = random.Random(seed)
    group = GROUPS["balanced"]
    stats = {name: {"ok": 0, "n": 0, "ok_side": 0, "n_side": 0, "ok_speech": 0, "n_speech": 0}
             for name in ("nearest", "hmm")}
    time_err = {name: [] for name in stats}
    for _ in range(n):
        atts = {name: make_attributor(name, seats, det) for name in stats}
        est = {name: [0.0] * len(seats) for name in stats}
        truth = [0.0] * len(seats)
        head = 0.0
        for _period in range(8):
            head = rng.choice(seats + [0.0])  # robot faces someone (or the group)
            side = abs(head) > 20.0
            for speaker, dur, _bc in _talk_period(group, rng.randrange(len(seats)), rng):
                for _ in range(max(1, round(dur / 0.1))):
                    reading = mic.observe(None if speaker is None else seats[speaker], head, rng)
                    if speaker is not None:
                        truth[speaker] += 0.1
                    for name, att in atts.items():
                        seat, _ = att.assign(reading.angle_rad, reading.speech_detected, head)
                        s = stats[name]
                        s["n"] += 1
                        s["ok"] += int(seat == speaker)
                        if speaker is not None:  # H2: annotated speech only
                            s["n_speech"] += 1
                            s["ok_speech"] += int(seat == speaker)
                        if side:
                            s["n_side"] += 1
                            s["ok_side"] += int(seat == speaker)
                        if seat is not None:
                            est[name][seat] += 0.1
        for name in stats:
            time_err[name].append(sum(abs(e - t) for e, t in zip(est[name], truth)) / max(sum(truth), 1e-9))
    return {name: {"frame_accuracy": s["ok"] / s["n"],
                   "speech_time_accuracy": s["ok_speech"] / max(s["n_speech"], 1),
                   "accuracy_head_turned_to_side": s["ok_side"] / max(s["n_side"], 1),
                   "speaking_time_error": st.mean(time_err[name])} for name, s in stats.items()}


def cmd_sim(args) -> None:
    seats, placeholder = load_seat_azimuths()
    det = DetectionConfig.load()
    mic = MicModel()
    print(f"Seats {seats}{' (PLACEHOLDER)' if placeholder else ''}; simulated mic {mic}\n")

    print("A) WHO IS SPEAKING - same simulated stream through both methods "
          f"({args.sessions} sessions, head turning between seats)")
    att = attribution_experiment(seats, mic, det, args.sessions, args.seed)
    print(f"   {'method':10s} {'accuracy':>9s} {'H2 speech-time acc.':>20s} {'acc. head to side':>18s} "
          f"{'speaking-time error':>20s}")
    for name, r in att.items():
        print(f"   {name:10s} {r['frame_accuracy']:9.3f} {r['speech_time_accuracy']:20.3f} "
              f"{r['accuracy_head_turned_to_side']:18.3f} {r['speaking_time_error']:20.3f}")

    print("\nB) FULL LOOP - simulated groups, robot invites someone after each silence (8 invitations)")
    print("   hit = invited the person with truly least speaking-turn time in the last 120 s")
    rows = []
    print(f"   {'group':13s} {'method':12s} {'Gini (lower=fairer)':>20s} {'hit rate':>9s} {'quiet share':>12s}")
    for gname, group in GROUPS.items():
        for method in METHODS:
            res = [simulate_session(method, seats, group, mic, seed=args.seed + i, det=det) for i in range(args.sessions)]
            g = st.mean(r.gini_speech for r in res)
            hit = sum(r.hit_recent for r in res) / max(sum(r.decisions for r in res), 1)
            quiet = st.mean(min(r.true_speech_s) / max(sum(r.true_speech_s), 1e-9) for r in res)
            rows.append({"group": gname, "method": method, "gini": g, "hit_recent": hit, "quietest_share": quiet,
                         "attribution_accuracy": sum(r.ticks_correct for r in res) / sum(r.ticks for r in res)})
            print(f"   {gname:13s} {method:12s} {g:20.3f} {hit:9.2f} {quiet:12.3f}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        with open(args.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        print(f"\nSaved {args.out}")
    print("\nNote: simulated groups are a simple model, used to compare methods under identical conditions.")


# ============================================================================ 2) tune
def cmd_tune(args) -> None:
    """Grid over half_life_s x margin_s for OUR method, averaged over the simulated group types."""
    seats, _ = load_seat_azimuths()
    base = DetectionConfig.load()
    mic = MicModel()
    rows = []
    print(f"{'half_life_s':>11s} {'margin_s':>8s} {'Gini':>7s} {'hit_recent':>10s} {'hit_cumul':>9s}")
    for half_life in args.half_lives:
        for margin in args.margins:
            det = DetectionConfig(**{**base.__dict__, "half_life_s": half_life, "margin_s": margin})
            res = [simulate_session("ours", seats, group, mic, seed=args.seed + i, det=det)
                   for group in GROUPS.values() for i in range(args.sessions)]
            n_dec = max(sum(r.decisions for r in res), 1)
            row = {"half_life_s": half_life, "margin_s": margin, "gini": st.mean(r.gini_speech for r in res),
                   "hit_recent": sum(r.hit_recent for r in res) / n_dec,
                   "hit_cumulative": sum(r.hit_cumulative for r in res) / n_dec}
            rows.append(row)
            print(f"{half_life:11.0f} {margin:8.2f} {row['gini']:7.3f} {row['hit_recent']:10.2f} "
                  f"{row['hit_cumulative']:9.2f}")
    best = min(rows, key=lambda r: (round(r["gini"], 3), -r["hit_recent"]))
    print(f"\nLowest simulated Gini: half_life_s={best['half_life_s']:.0f}, margin_s={best['margin_s']:.2f}. "
          "Decide, write the values into detection_params.json, commit, and do not change them during the study.")
    print("Caution: hit_recent defines 'truly least active' with a 120 s window, which favours half-lives near 120 s;"
          " Gini of the simulated true speaking time is the outcome that matters.")
    _save(args.out, rows)


# ============================================================================ replay helpers
def attribution_confusion(ticks_path: str, labels, attributor_name: str, seats, det) -> List[List[int]]:
    """Confusion matrix (rows truth, cols predicted; index 0 = nobody) of one attributor on one recording.

    Excludes ticks while the robot speaks and ticks with overlapping labelled speech."""
    n = len(seats)
    att = make_attributor(attributor_name, seats, det)
    confusion = [[0] * (n + 1) for _ in range(n + 1)]
    for tk in iter_ticks(ticks_path):
        usable = not tk.robot_speaking
        angle = tk.reading.angle_rad if tk.reading else None
        speech = bool(tk.reading and tk.reading.speech_detected)
        seat, _ = att.assign(angle, speech, tk.head_yaw_deg, usable)
        if not usable or is_overlap(labels, tk.t):
            continue
        truth = truth_at(labels, tk.t)
        confusion[0 if truth is None else truth + 1][0 if seat is None else seat + 1] += 1
    return confusion


def h2_from_confusion(confusion: List[List[int]]) -> float:
    """Share of annotated speech ticks assigned to the correct seat ('nobody' counts as wrong)."""
    n = len(confusion) - 1
    total = sum(sum(confusion[i]) for i in range(1, n + 1))
    return sum(confusion[i][i] for i in range(1, n + 1)) / total if total else float("nan")


# ============================================================================ 5) replay
def cmd_replay(args) -> None:
    seats, placeholder = load_seat_azimuths()
    det = DetectionConfig.load()
    labels = load_labels(args.labels, args.offset)
    n_seats = len(seats)
    for name in ("nearest", "hmm"):
        confusion = attribution_confusion(args.ticks, labels, name, seats, det)
        total = sum(map(sum, confusion))
        correct = sum(confusion[i][i] for i in range(n_seats + 1))
        print(f"\n{name}: frame accuracy {correct / max(total, 1):.3f} over {total} ticks"
              f"{' (PLACEHOLDER seats!)' if placeholder else ''}")
        h2 = h2_from_confusion(confusion)
        per_seat = [confusion[i][i] / max(sum(confusion[i]), 1) for i in range(1, n_seats + 1)]
        print(f"   H2 speech-time accuracy {h2:.3f} ({'meets' if h2 >= 0.80 else 'BELOW'} the 0.80 target); "
              f"per seat: " + ", ".join(f"seat{k + 1} {a:.3f}" for k, a in enumerate(per_seat)))
        print("   truth \\ predicted   " + "  ".join(f"{h:>7s}" for h in ["nobody"] + [f"seat{k+1}" for k in range(n_seats)]))
        for i, row in enumerate(confusion):
            print(f"   {('nobody' if i == 0 else f'seat{i}'):18s}  " + "  ".join(f"{v:7d}" for v in row))


# ============================================================================ 4) offset
def read_events(log_path: str) -> List[dict]:
    with open(log_path, newline="") as f:
        rows = list(csv.DictReader(f))
    if rows and "mono_s" not in rows[0]:
        raise SystemExit(f"{log_path} has no mono_s column (recorded before the clock-sync fix); "
                         "it cannot be aligned with the ticks automatically.")
    return rows


def cmd_offset(args) -> None:
    rows = read_events(args.log)
    intro = next((r for r in rows if r["event"] == "robot_say_start"), None)
    if intro is None:
        raise SystemExit("No robot_say_start event in the log.")
    offset = float(intro["mono_s"]) - args.video_s
    print(f"Intro starts at tick time {float(intro['mono_s']):.3f}; video time {args.video_s:.3f}.")
    print(f"offset = {offset:.3f}   (put this in the 'offset' column of study_sessions.csv)")


# ============================================================================ 6) study (H2 + H3)
def _truth_turn_time(labels_turns, t_end: float, n_seats: int, window_s: float = None) -> List[float]:
    """Annotated speaking-turn seconds per seat before t_end (optionally only the last window_s)."""
    out = [0.0] * n_seats
    t_start = -float("inf") if window_s is None else t_end - window_s
    for a, b, s in labels_turns:
        lo, hi = max(a, t_start), min(b, t_end)
        if hi > lo:
            out[s] += hi - lo
    return out


def replay_decisions(ticks_path: str, events: List[dict], labels_turns, seats, det) -> List[dict]:
    """Re-run both full methods on a recording and score them at the robot's real decision times.

    Uses the REAL history of who was addressed (the replayed choice is what the method would
    have chosen at that moment, given what actually happened before)."""
    decisions = [(float(r["mono_s"]), int(r["seat"]) - 1) for r in events if r["event"] == "decision" and r["seat"]]
    n = len(seats)
    pipes = {}
    for name in ("ours", "micbot"):
        d = DetectionConfig(**{**det.__dict__, **METHODS[name]["det"]})
        pipes[name] = (ParticipationListener(make_attributor(d.attributor, seats, d),
                                             make_estimator(d.estimator, n, d), d.ignore_while_robot_speaks),
                       LeastActivePolicy(n, d.margin_s, d.repeat_margin_s, d.max_consecutive)
                       if name == "ours" else MicbotPolicy(n))
    ticks = iter(iter_ticks(ticks_path))
    pending = next(ticks, None)
    out, history = [], []
    for t_dec, actual in decisions:
        while pending is not None and pending.t <= t_dec:
            for listener, _ in pipes.values():
                listener.update(pending.reading, pending.t, pending.robot_speaking, pending.head_yaw_deg)
            pending = next(ticks, None)
        cum = _truth_turn_time(labels_turns, t_dec, n)
        recent = _truth_turn_time(labels_turns, t_dec, n, 120.0)
        row = {"t": t_dec, "actual": actual}
        for name, (listener, policy) in pipes.items():
            choice = policy.choose(listener.estimator.scores(t_dec), history)
            row[f"{name}_choice"] = choice
            row[f"{name}_hit_cumulative"] = int(cum[choice] == min(cum))
            row[f"{name}_hit_recent"] = int(recent[choice] == min(recent))
        out.append(row)
        history.append(actual)
    return out


def cmd_study(args) -> None:
    from scipy.stats import wilcoxon

    seats, placeholder = load_seat_azimuths()
    det = DetectionConfig.load()
    base = Path(args.sessions).resolve().parent
    rows = list(csv.DictReader(open(args.sessions, newline="")))

    def path(v: str) -> str:
        return str((base / v).resolve()) if v and not Path(v).is_absolute() else v

    per_round, all_dec = [], []
    for r in rows:
        if not r.get("ticks"):
            continue
        labels = load_labels(path(r["labels"]), float(r.get("offset") or 0))
        acc = {name: h2_from_confusion(attribution_confusion(path(r["ticks"]), labels, name, seats, det))
               for name in ("nearest", "hmm")}
        rec = {"group": r["group"], "round": r["round"], "condition": r["condition"],
               "h2_nearest": acc["nearest"], "h2_hmm": acc["hmm"]}
        if r.get("log"):
            turns = load_labels(path(r["labels"]), float(r.get("offset") or 0), kinds=("turn",))
            dec = replay_decisions(path(r["ticks"]), read_events(path(r["log"])), turns, seats, det)
            for d in dec:
                d.update(group=r["group"], condition=r["condition"])
            all_dec += dec
            if r["condition"] == "adaptive" and dec:  # sanity check: replay reproduces the live robot
                rec["replay_matches_live"] = sum(d["ours_choice"] == d["actual"] for d in dec) / len(dec)
        per_round.append(rec)
        print(f"{r['group']:6s} R{r['round']} {r['condition']:9s} H2 nearest {acc['nearest']:.3f}  hmm {acc['hmm']:.3f}"
              + (f"  replay=live {rec['replay_matches_live']:.2f}" if "replay_matches_live" in rec else ""))
    if not per_round:
        raise SystemExit("No rows with a ticks file.")
    if placeholder:
        print("WARNING: placeholder seats - calibrate first, results are not meaningful.")

    # H2 / H3a: paired by group (mean of its rounds), one-sided: hmm more accurate than nearest
    groups = {}
    for rec in per_round:
        groups.setdefault(rec["group"], []).append(rec)
    hmm = [st.mean(x["h2_hmm"] for x in g) for g in groups.values()]
    near = [st.mean(x["h2_nearest"] for x in g) for g in groups.values()]
    print(f"\nH2  hmm: mean {st.mean(hmm):.3f} ({'meets' if st.mean(hmm) >= 0.8 else 'BELOW'} 0.80)   "
          f"nearest (Micbot-style): mean {st.mean(near):.3f}")
    diffs = [a - b for a, b in zip(hmm, near) if a != b]
    if len(diffs) >= 2:
        res = wilcoxon(diffs, alternative="greater")
        print(f"H3a hmm - nearest per group: median {st.median(diffs):+.3f}, "
              f"{sum(d > 0 for d in diffs)}/{len(diffs)} groups better, Wilcoxon one-sided p = {res.pvalue:.4f}")

    # H3b: decisions
    if all_dec:
        for truth in ("recent", "cumulative"):
            ours = st.mean(d[f"ours_hit_{truth}"] for d in all_dec)
            mic = st.mean(d[f"micbot_hit_{truth}"] for d in all_dec)
            print(f"H3b picks the truly least active ({truth} turn time): ours {ours:.2f}  Micbot-style {mic:.2f}"
                  f"  over {len(all_dec)} decisions")
        b = sum(d["ours_hit_recent"] and not d["micbot_hit_recent"] for d in all_dec)
        c = sum(d["micbot_hit_recent"] and not d["ours_hit_recent"] for d in all_dec)
        if b + c:
            from scipy.stats import binomtest
            print(f"    discordant decisions (recent): ours-only {b}, Micbot-only {c}; exact McNemar "
                  f"p = {binomtest(b, b + c, 0.5).pvalue:.4f} (two-sided)")
    _save(args.out, per_round)
    if args.out and all_dec:
        _save(str(Path(args.out).with_name(Path(args.out).stem + "_decisions.csv")), all_dec)


def _save(out, rows) -> None:
    if not out or not rows:
        return
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"Saved {out}")


# ============================================================================ 3) fit
def cmd_fit(args) -> None:
    labels = load_labels(args.labels, args.offset)
    n_seats = max(s for _, _, s in labels) + 1
    world = {k: [] for k in range(n_seats)}
    speech_ticks = speech_flag_on = silent_ticks = silent_flag_on = 0
    ticks = list(iter_ticks(args.ticks))
    for tk in ticks:
        if tk.robot_speaking or tk.reading is None:
            continue
        if is_overlap(labels, tk.t):
            continue
        truth = truth_at(labels, tk.t)
        if truth is None:
            silent_ticks += 1
            silent_flag_on += int(tk.reading.speech_detected)
        else:
            speech_ticks += 1
            speech_flag_on += int(tk.reading.speech_detected)
            if tk.reading.speech_detected and abs(tk.head_yaw_deg) < 10.0:  # head facing the group: no mirroring
                world[truth].append(head_to_world_deg(tk.reading.angle_rad, tk.head_yaw_deg))
    missing = [k + 1 for k, v in world.items() if len(v) < 10]
    if missing:
        raise SystemExit(f"Not enough labelled speech with the head facing the group for seats {missing} "
                         "(record with run_calibration.py, which includes a facing-the-group block).")
    seat_az = [st.median(world[k]) for k in range(n_seats)]

    residuals = []
    for tk in ticks:
        truth = None if tk.robot_speaking or tk.reading is None else truth_at(labels, tk.t)
        if truth is not None and tk.reading.speech_detected and not is_overlap(labels, tk.t):
            measured = mic_angle_to_head_deg(tk.reading.angle_rad)
            residuals.append(wrap_deg(measured - expected_mic_head_deg(seat_az[truth], tk.head_yaw_deg)))
    mad = st.median(abs(r) for r in residuals)
    sigma = max(1.4826 * mad, 3.0)
    fitted = {
        "angle_sigma_deg": round(sigma, 2),
        "outlier_rate": round(sum(abs(r) > 3 * sigma for r in residuals) / len(residuals), 3),
        "vad_miss_rate": round(1 - speech_flag_on / max(speech_ticks, 1), 3),
        "vad_false_alarm_rate": round(silent_flag_on / max(silent_ticks, 1), 3),
    }
    print(f"Seats (deg, + = robot's left): {[round(a, 1) for a in seat_az]}")
    print(f"Microphone model: {fitted}")
    if args.dry_run:
        return
    save_seat_azimuths(seat_az, note=f"fitted from {Path(args.ticks).name}")
    existing = json.loads(PARAMS_FILE.read_text()) if PARAMS_FILE.exists() else {}
    PARAMS_FILE.write_text(json.dumps({**existing, **fitted}, indent=2))
    print("Wrote seats.json and detection_params.json (commit both). Also copy the four numbers into "
          "MicModel in sim_sources.py so simulations match the real robot.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sim")
    s.add_argument("--sessions", type=int, default=100)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--out")
    t = sub.add_parser("tune")
    t.add_argument("--sessions", type=int, default=60, help="sessions per group type and grid cell")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--half-lives", type=float, nargs="+", default=[30, 60, 120, 240, 600])
    t.add_argument("--margins", type=float, nargs="+", default=[0.0, 0.5, 1.0, 2.0])
    t.add_argument("--out")
    o = sub.add_parser("offset")
    o.add_argument("--log", required=True, help="the round's session log (.csv, not _ticks)")
    o.add_argument("--video-s", type=float, required=True, help="video time (s) when the intro starts")
    y = sub.add_parser("study")
    y.add_argument("sessions", help="study_sessions.csv (see templates/study_sessions_template.csv)")
    y.add_argument("--out")
    for name in ("replay", "fit"):
        r = sub.add_parser(name)
        r.add_argument("--ticks", required=True)
        r.add_argument("--labels", required=True)
        r.add_argument("--offset", type=float, default=0.0)
        if name == "fit":
            r.add_argument("--dry-run", action="store_true", help="print, do not write files")
    args = p.parse_args()
    {"sim": cmd_sim, "tune": cmd_tune, "replay": cmd_replay, "fit": cmd_fit, "offset": cmd_offset,
     "study": cmd_study}[args.cmd](args)


if __name__ == "__main__":
    main()
