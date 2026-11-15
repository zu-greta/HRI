"""
[ANALYSIS]
find every recorded attempt and write study_sessions.csv

    python build_sessions.py ~/study_data --out ~/study_data/study_sessions.csv

Scans for *_ticks.csv, and for each finds its event log, room audio and audio offset.
Group, round, topic, order, condition and quiet seat are read from the log itself (study_info line)
The calibration file used live is found by matching the seat angles in the log to seats*.json.

Re-runs: several attempts of the same group + round get attempt = 1, 2, ... in time order, all
with include = 1. Set include = 0 by hand for attempts to exclude
Rows with completed = 0 are attempts that did not reach the end (crash).

The labels column points to the attempt's converted labels: <stem>_labels.csv anywhere in the
data folder, else labels/<stem>.csv (python audacity_labels_to_csv.py <export>.txt labels/<stem>.csv).

Check groups and prefixes like "TEST", "CHECK", "PILOT", "CALIB" are skipped (--keep-all keeps them).
"""

import argparse
import csv
import os
from pathlib import Path

from facilitator.study_data import SESSION_FIELDS, find_params_for_seats, read_log

REPO = Path(__file__).resolve().parent
SKIP = ("TEST", "CHECK", "PILOT", "CALIB", "SCENARIO", "DEMO")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("data_dir", help="folder with all study files (searched recursively)")
    p.add_argument("--out", help="output CSV (default: <data_dir>/study_sessions.csv)")
    p.add_argument("--labels-dir", default="labels", help="where label CSVs go, relative to the output CSV")
    p.add_argument("--keep-all", action="store_true", help="also keep TEST/CHECK/PILOT/... runs")
    args = p.parse_args()

    data = Path(args.data_dir).expanduser().resolve()
    out = Path(args.out).expanduser().resolve() if args.out else data / "study_sessions.csv"
    rel = lambda path: os.path.relpath(path, out.parent) if path else ""  

    by_name = {}
    for f in data.rglob("*"):
        if f.is_file():
            by_name.setdefault(f.name, f)  # first copy wins if the same file was copied twice

    def find_labels(stem: str) -> Path:
        """<stem>_labels.csv anywhere in the data folder, else labels/<stem>.csv (where it is expected)."""
        found = by_name.get(stem + "_labels.csv")
        return found if found is not None else out.parent / args.labels_dir / (stem + ".csv")

    attempts = []
    for ticks in sorted(data.rglob("*_ticks.csv")):
        stem = ticks.name[:-len("_ticks.csv")]
        if not args.keep_all and stem.upper().startswith(SKIP):
            continue
        log = by_name.get(stem + ".csv")
        if log is None:
            print(f"SKIP {stem}: no event log {stem}.csv found")
            continue
        li = read_log(str(log))
        info = li.info
        if "group" not in info:
            print(f"SKIP {stem}: no study_info line in the log")
            continue
        audio = by_name.get(stem + "_audio.wav")
        params = find_params_for_seats(li.seats, REPO)
        if not params:
            print(f"WARNING {stem}: seats {li.seats} match no seats*.json here - fill the params column by hand")
        attempts.append({
            "group": info["group"], "order": info.get("order", "-"), "round": int(info.get("round", 0)),
            "topic": int(info.get("topic", 0)), "condition": info.get("condition", "?"),
            "quiet_seat": int(info.get("quiet_seat", 0)), "include": 1,
            "log": rel(log), "ticks": rel(ticks), "audio": rel(audio) if audio else "",
            "labels": rel(find_labels(stem)),
            "params": rel(params) if params else "", "offset": "",
            "_start": li.start or 0.0, "_stem": stem, "_completed": int(li.completed),
            "_decisions": len(li.decisions)})
        if audio is None:
            print(f"WARNING {stem}: no {stem}_audio.wav found (H1/H2 need the audio labels)")

    attempts.sort(key=lambda r: (r["group"], r["round"], r["_start"]))
    counter = {}
    for r in attempts:
        k = (r["group"], r["round"])
        counter[k] = counter.get(k, 0) + 1
        r["attempt"] = counter[k]

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(SESSION_FIELDS + ["completed", "decisions", "stem"])
        for r in attempts:
            w.writerow([r[k] for k in SESSION_FIELDS] + [r["_completed"], r["_decisions"], r["_stem"]])

    print(f"\nWrote {out} with {len(attempts)} attempts:")
    print(f"   {'group':6s} {'rnd':>3s} {'att':>3s} {'condition':9s} {'done':>4s} {'dec':>3s}  stem")
    for r in attempts:
        print(f"   {r['group']:6s} {r['round']:3d} {r['attempt']:3d} {r['condition']:9s} {r['_completed']:4d} "
              f"{r['_decisions']:3d}  {r['_stem']}")
    rounds = {(r["group"], r["round"]) for r in attempts}
    groups = sorted({r["group"] for r in attempts})
    print(f"\n{len(groups)} groups, {len(rounds)} rounds. Check: every group should have round 1 and round 2.")
    for g in groups:
        missing = [n for n in (1, 2) if (g, n) not in rounds]
        if missing:
            print(f"   {g}: missing round(s) {missing}")


if __name__ == "__main__":
    main()
