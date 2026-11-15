"""
[ANALYSIS]
Evaluate and calibrate the detection methods

1) Simulation: our method vs the Micbot-style baseline
       python evaluate_offline.py sim                # default 100 sessions per group type
       python evaluate_offline.py sim --sessions 300 --out results/sim.csv

2) Replay a real recording against hand-made labels
       python evaluate_offline.py replay --ticks logs/G01_baseline_..._ticks.csv --labels labels/G01.csv [--offset 12.3]

3) Fit the placeholder values from a labelled recording (writes seats.json + detection_params.json)
       python evaluate_offline.py fit --ticks logs/CALIB_..._ticks.csv --labels labels/CALIB.csv [--offset 12.3]

4) The study recordings: our method vs the Micbot-style method on the same sensor data (H3)
       python evaluate_offline.py study ./logs/study_sessions.csv --out ./logs/results
   Uses each attempt's own calibration (params column). With labels it adds accuracy (H3a) and
   whether each method picks the truly least active person (H3b).

Labels CSV: header start_s,end_s,seat  (seat 1-based; only real speech, gaps = silence).
--offset: seconds added to label times to put them on the tick-log clock.
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
from facilitator.sim_sources import MicModel, iter_ticks, load_labels, truth_at
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


# ============================================================================ 2) replay
def cmd_replay(args) -> None:
    seats, placeholder = load_seat_azimuths()
    det = DetectionConfig.load()
    labels = load_labels(args.labels, args.offset)
    n_seats = len(seats)
    for name in ("nearest", "hmm"):
        att = make_attributor(name, seats, det)
        confusion = [[0] * (n_seats + 1) for _ in range(n_seats + 1)]  # rows truth, cols predicted; 0 = nobody
        for tk in iter_ticks(args.ticks):
            usable = not tk.robot_speaking
            angle = tk.reading.angle_rad if tk.reading else None
            speech = bool(tk.reading and tk.reading.speech_detected)
            seat, _ = att.assign(angle, speech, tk.head_yaw_deg, usable)
            if not usable:
                continue
            truth = truth_at(labels, tk.t)
            confusion[0 if truth is None else truth + 1][0 if seat is None else seat + 1] += 1
        total = sum(map(sum, confusion))
        correct = sum(confusion[i][i] for i in range(n_seats + 1))
        print(f"\n{name}: frame accuracy {correct / max(total, 1):.3f} over {total} ticks"
              f"{' (PLACEHOLDER seats!)' if placeholder else ''}")
        # H2 (report): share of ANNOTATED SPEECH time assigned to the correct seat, overall and per seat
        speech_total = sum(sum(confusion[i]) for i in range(1, n_seats + 1))
        speech_ok = sum(confusion[i][i] for i in range(1, n_seats + 1))
        h2 = speech_ok / max(speech_total, 1)
        per_seat = [confusion[i][i] / max(sum(confusion[i]), 1) for i in range(1, n_seats + 1)]
        print(f"   H2 speech-time accuracy {h2:.3f} ({'meets' if h2 >= 0.80 else 'BELOW'} the 0.80 target); "
              f"per seat: " + ", ".join(f"seat{k + 1} {a:.3f}" for k, a in enumerate(per_seat)))
        print("   truth \\ predicted   " + "  ".join(f"{h:>7s}" for h in ["nobody"] + [f"seat{k+1}" for k in range(n_seats)]))
        for i, row in enumerate(confusion):
            print(f"   {('nobody' if i == 0 else f'seat{i}'):18s}  " + "  ".join(f"{v:7d}" for v in row))


# ============================================================================ 4) study recordings (H3)
def _det_for(attempt) -> DetectionConfig:
    from facilitator.study_data import params_path

    return DetectionConfig.load(params_path(attempt))


def _least(values, choice) -> int:
    """1 if `choice` is (one of) the seat(s) with the least speaking time."""
    return int(values[choice] <= min(values) + 1e-9)


def cmd_study(args) -> None:
    from scipy.stats import binomtest, wilcoxon

    from facilitator.estimator import make_estimator
    from facilitator.listener import ParticipationListener
    from facilitator.policies import LeastActivePolicy, MicbotPolicy
    from facilitator.sources import Reading
    from facilitator.study_data import (audio_offset, clip, read_labels, read_log, read_sessions, speakers_at,
                                        speaking_time, tick_rows)

    attempts = [a for a in read_sessions(args.sessions) if a.include and a.ticks and Path(a.ticks).exists()]
    acc_rows, dec_rows = [], []
    print(f"{'attempt':40s} {'replay=live':>11s} {'acc HMM':>8s} {'acc nearest':>11s} {'side HMM':>9s} "
          f"{'side near':>9s} {'ours=Micbot':>11s}")
    for a in attempts:
        li = read_log(a.log)
        seats, det = li.seats, _det_for(a)
        rows = tick_rows(a.ticks)
        labels = None
        if a.labels and Path(a.labels).exists():
            labels = clip(read_labels(a.labels, audio_offset(a) or 0.0), li.start, li.end)

        # --- who is speaking: both attributors on the same stream
        atts = {n: make_attributor(n, seats, det) for n in ("hmm", "nearest")}
        same = total = 0
        acc = {(n, side): [0.0, 0.0] for n in atts for side in (False, True)}
        false_sp = {n: [0.0, 0.0] for n in atts}   # unlabelled listening time, time credited to a seat
        for r in rows:
            usable = r["robot_speaking"] == "0"
            angle = float(r["angle_rad"]) if r["angle_rad"] else None
            speech, yaw = r["speech"] == "1", float(r["head_yaw_deg"])
            out = {n: att.assign(angle, speech, yaw, usable)[0] for n, att in atts.items()}
            live = int(r["seat"]) - 1 if r["seat"] else None
            total += 1
            same += int(out["hmm"] == live)
            if labels is None or not usable:
                continue
            who = speakers_at(labels, r["t"])
            if not who:
                for n, seat in out.items():
                    false_sp[n][0] += r["dt"]
                    false_sp[n][1] += r["dt"] if seat is not None else 0.0
            if len(who) != 1:
                continue
            truth = next(iter(who))
            for n, seat in out.items():
                cell = acc[(n, abs(yaw) > 20.0)]
                cell[0] += r["dt"]
                cell[1] += r["dt"] if seat == truth else 0.0

        def rate(n, sides=(False, True)):
            tot = sum(acc[(n, s)][0] for s in sides)
            return sum(acc[(n, s)][1] for s in sides) / tot if tot else None

        # --- decisions: both full pipelines, at the robot's real decision times, real history
        pipes = {}
        for name, conf in (("ours", {"attributor": "hmm", "estimator": "turns_decay"}),
                           ("micbot", {"attributor": "nearest", "estimator": "cumulative"})):
            d = DetectionConfig(**{**det.__dict__, **conf})
            pol = LeastActivePolicy(len(seats), d.margin_s, d.repeat_margin_s, d.max_consecutive) \
                if name == "ours" else MicbotPolicy(len(seats))
            pipes[name] = (ParticipationListener(make_attributor(d.attributor, seats, d),
                                                 make_estimator(d.estimator, len(seats), d),
                                                 d.ignore_while_robot_speaks), pol)
        i, history, agree = 0, [], []
        for t_dec, actual, live_act in li.decisions:
            while i < len(rows) and rows[i]["t"] <= t_dec:
                r = rows[i]
                reading = None if not r["angle_rad"] else Reading(float(r["angle_rad"]), r["speech"] == "1")
                for lst, _ in pipes.values():
                    lst.update(reading, r["t"], r["robot_speaking"] == "1", float(r["head_yaw_deg"]))
                i += 1
            rec = {"group": a.group, "round": a.round, "attempt": a.attempt, "condition": a.condition,
                   "question": len(history) + 1, "live_choice": actual + 1}
            for name, (lst, pol) in pipes.items():
                rec[f"{name}_choice"] = pol.choose(lst.activity(), history) + 1
            rec["ours_activity_matches_live"] = int(all(abs(x - y) < 0.05 for x, y in
                                                        zip(pipes["ours"][0].activity(), live_act)))
            if labels is not None:
                before = clip(labels, li.start, t_dec)
                cum = speaking_time(before)
                recent = speaking_time(clip(labels, t_dec - 120.0, t_dec))
                # our method's own definition: annotated speaking TURNS (>= 1 s), each weighted by 2^(-age/half-life)
                decayed = [0.0] * len(seats)
                for x, b, sp in before:
                    if b - x >= 1.0:
                        decayed[sp] += (b - x) * 2 ** (-(t_dec - b) / det.half_life_s)
                for name in pipes:
                    c = rec[f"{name}_choice"] - 1
                    rec[f"{name}_hit_cumulative"], rec[f"{name}_hit_recent"] = _least(cum, c), _least(recent, c)
                    rec[f"{name}_hit_decayed"] = _least(decayed, c)
            agree.append(int(rec["ours_choice"] == rec["micbot_choice"]))
            dec_rows.append(rec)
            history.append(actual)
        acc_rows.append({"group": a.group, "round": a.round, "attempt": a.attempt, "condition": a.condition,
                         "replay_matches_live": round(same / max(total, 1), 4),
                         "acc_hmm": rate("hmm"), "acc_nearest": rate("nearest"),
                         "acc_hmm_side": rate("hmm", (True,)), "acc_nearest_side": rate("nearest", (True,)),
                         "acc_hmm_middle": rate("hmm", (False,)), "acc_nearest_middle": rate("nearest", (False,)),
                         "ours_eq_micbot": round(sum(agree) / len(agree), 3) if agree else None,
                         "false_hmm": false_sp["hmm"][1] / false_sp["hmm"][0] if false_sp["hmm"][0] else None,
                         "false_nearest": false_sp["nearest"][1] / false_sp["nearest"][0] if false_sp["nearest"][0] else None})
        r = acc_rows[-1]
        f = lambda v: "-" if v is None else f"{v:.3f}"  # noqa: E731
        print(f"{Path(a.log).stem:40s} {r['replay_matches_live']:11.3f} {f(r['acc_hmm']):>8s} "
              f"{f(r['acc_nearest']):>11s} {f(r['acc_hmm_side']):>9s} {f(r['acc_nearest_side']):>9s} "
              f"{f(r['ours_eq_micbot']):>11s}")

    print("\nreplay=live: the HMM replayed offline gives the same seat as the live robot on this share of ticks"
          " (should be ~1.000;\n   lower = wrong params file for that room). side = robot facing a side seat.")
    adaptive = [d for d in dec_rows if d["condition"] == "adaptive"]
    if adaptive:
        m = sum(d["ours_choice"] == d["live_choice"] for d in adaptive) / len(adaptive)
        print(f"Balancing rounds: replayed choice = live choice in {m:.2f} of {len(adaptive)} decisions (should be 1.00)")
    print(f"Ours and Micbot-style would choose the same person in "
          f"{sum(d['ours_choice'] == d['micbot_choice'] for d in dec_rows) / max(len(dec_rows), 1):.2f} of "
          f"{len(dec_rows)} decisions (label-free).")

    labelled = [r for r in acc_rows if r["acc_hmm"] is not None]
    if labelled:
        groups = {}
        for r in labelled:
            groups.setdefault(r["group"], []).append(r)
        hmm = [st.mean(x["acc_hmm"] for x in g) for g in groups.values()]
        near = [st.mean(x["acc_nearest"] for x in g) for g in groups.values()]
        print(f"\nH3a  speech time assigned to the right seat: HMM mean {st.mean(hmm):.3f}, nearest (Micbot-style) "
              f"mean {st.mean(near):.3f} over {len(groups)} groups")
        diffs = [round(h - n, 6) for h, n in zip(hmm, near) if round(h - n, 6) != 0]
        if len(diffs) >= 2:
            res = wilcoxon(diffs, alternative="greater")
            print(f"     HMM better in {sum(d > 0 for d in diffs)}/{len(diffs)} groups; one-sided Wilcoxon p = {res.pvalue:.4f}")
        side_h = [r["acc_hmm_side"] for r in labelled if r["acc_hmm_side"] is not None]
        side_n = [r["acc_nearest_side"] for r in labelled if r["acc_nearest_side"] is not None]
        if side_h:
            print(f"     while facing a side seat (mirroring): HMM {st.mean(side_h):.3f} vs nearest {st.mean(side_n):.3f}")
        fh = [r["false_hmm"] for r in labelled if r["false_hmm"] is not None]
        fn = [r["false_nearest"] for r in labelled if r["false_nearest"] is not None]
        if fh:
            print(f"     FALSE SPEECH (unlabelled listening time credited to a seat; lower is better): HMM {st.mean(fh):.3f}"
                  f" vs nearest {st.mean(fn):.3f}")
    scored = [d for d in dec_rows if "ours_hit_recent" in d]
    if scored:
        for truth in ("decayed", "recent", "cumulative"):
            o = sum(d[f"ours_hit_{truth}"] for d in scored) / len(scored)
            mb = sum(d[f"micbot_hit_{truth}"] for d in scored) / len(scored)
            b = sum(d[f"ours_hit_{truth}"] and not d[f"micbot_hit_{truth}"] for d in scored)
            c = sum(d[f"micbot_hit_{truth}"] and not d[f"ours_hit_{truth}"] for d in scored)
            p = binomtest(b, b + c, 0.5).pvalue if b + c else float("nan")
            label = {"decayed": "our definition: turns, 120 s half-life", "recent": "last 120 s, all speech",
                     "cumulative": "Micbot's definition: all speech since the start"}[truth]
            print(f"H3b  picks the truly least active ({label}): ours {o:.2f}, Micbot-style {mb:.2f} "
                  f"over {len(scored)} decisions; only-ours {b}, only-Micbot {c}, exact McNemar p = {p:.4f}")
        print("     chance level with 3 people is about 0.33.")
    if args.out:
        out = Path(args.out).expanduser()
        out.mkdir(parents=True, exist_ok=True)
        for name, rows_ in (("h3_attribution.csv", acc_rows), ("h3_decisions.csv", dec_rows)):
            if rows_:
                keys = list(dict.fromkeys(k for r in rows_ for k in r))
                with open(out / name, "w", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=keys)
                    w.writeheader()
                    w.writerows(rows_)
        print(f"\nSaved h3_attribution.csv and h3_decisions.csv in {out}")


# ============================================================================ 3) fit
SILENCE_GUARD_S = 1.5  # [CALIBRATION FIX] see cmd_fit


def cmd_fit(args) -> None:
    labels = load_labels(args.labels, args.offset)
    n_seats = max(s for _, _, s in labels) + 1
    world = {k: [] for k in range(n_seats)}
    speech_ticks = speech_flag_on = silent_ticks = silent_flag_on = 0
    ticks = list(iter_ticks(args.ticks))
    for tk in ticks:
        if tk.robot_speaking or tk.reading is None:
            continue
        truth = truth_at(labels, tk.t)
        if truth is None:
            # [CALIBRATION FIX] only count CLEAR silence for the false-alarm rate: ticks close to a label
            # edge are often still speech (run_calibration.py trims 1.0 s / 0.5 s off every reading, and
            # hand labels have imprecise edges); counting them as silence inflated the rate ~5x.
            if any(a - SILENCE_GUARD_S <= tk.t < b + SILENCE_GUARD_S for a, b, _ in labels):
                continue
            silent_ticks += 1
            silent_flag_on += int(tk.reading.speech_detected)
        else:
            speech_ticks += 1
            speech_flag_on += int(tk.reading.speech_detected)
            if tk.reading.speech_detected and abs(tk.head_yaw_deg) < 10.0:  # head facing the group: no mirroring
                world[truth].append(head_to_world_deg(tk.reading.angle_rad, tk.head_yaw_deg))
    missing = [k + 1 for k, v in world.items() if len(v) < 10]
    if missing:
        raise SystemExit(f"Not enough labelled speech with the head facing the group for seats {missing}.")
    seat_az = [st.median(world[k]) for k in range(n_seats)]

    residuals = []
    for tk in ticks:
        truth = None if tk.robot_speaking or tk.reading is None else truth_at(labels, tk.t)
        if truth is not None and tk.reading.speech_detected:
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
    for name in ("replay", "fit"):
        r = sub.add_parser(name)
        r.add_argument("--ticks", required=True)
        r.add_argument("--labels", required=True)
        r.add_argument("--offset", type=float, default=0.0)
        if name == "fit":
            r.add_argument("--dry-run", action="store_true", help="print, do not write files")
    y = sub.add_parser("study")
    y.add_argument("sessions", help="study_sessions.csv from build_sessions.py")
    y.add_argument("--out", help="folder for h3_*.csv")
    args = p.parse_args()
    {"sim": cmd_sim, "replay": cmd_replay, "fit": cmd_fit, "study": cmd_study}[args.cmd](args)


if __name__ == "__main__":
    main()