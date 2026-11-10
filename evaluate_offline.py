"""Evaluate and calibrate the detection methods without running a session.

1) Simulation: our method vs the Micbot-style baseline (no robot needed)
       python evaluate_offline.py sim                # default 100 sessions per group type
       python evaluate_offline.py sim --sessions 300 --out results/sim.csv

2) Replay a real recording against hand-made labels
       python evaluate_offline.py replay --ticks logs/G01_baseline_..._ticks.csv --labels labels/G01.csv [--offset 12.3]

3) Fit the placeholder values from a labelled recording (writes seats.json + detection_params.json)
       python evaluate_offline.py fit --ticks logs/CALIB_..._ticks.csv --labels labels/CALIB.csv [--offset 12.3]

Labels CSV: header start_s,end_s,seat  (seat 1-based; only real speech, gaps = silence).
--offset: seconds ADDED to label times to put them on the tick-log clock.
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
    args = p.parse_args()
    {"sim": cmd_sim, "replay": cmd_replay, "fit": cmd_fit}[args.cmd](args)


if __name__ == "__main__":
    main()