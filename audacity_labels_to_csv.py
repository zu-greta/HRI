"""
[ANALYSIS]
Convert manually annotated Audacity label export into the label CSV the analysis expects

    python audacity_labels_to_csv.py G01_R1_labels.txt labels/G01_R1.csv

Output: start_s,end_s,seat   (times in seconds from the start of the WAV file)
Labels that are not 1, 2 or 3 (e.g. "R", "INTRO", "END" from make_label_templates.py) are skipped
and listed. A "?" left over means speech that was not assigned to a seat: it prints a WARNING.
"""

import csv
import sys
from pathlib import Path


def convert(src: str, dst: str) -> int:
    rows, skipped = [], []
    for line in Path(src).read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 3 or parts[0].startswith("\\"):  # Audacity frequency lines start with "\"
            continue
        start, end, label = float(parts[0]), float(parts[1]), parts[2].strip()
        if label in ("1", "2", "3") and end > start:
            rows.append((start, end, int(label)))
        else:
            skipped.append(label or "(empty)")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["start_s", "end_s", "seat"])
        for start, end, seat in sorted(rows):
            w.writerow([f"{start:.3f}", f"{end:.3f}", seat])
    print(f"Wrote {len(rows)} segments to {dst}")
    if skipped:
        print(f"Skipped {len(skipped)} labels that are not 1/2/3: {sorted(set(skipped))}")
    if "?" in skipped:
        print(f"WARNING: {skipped.count('?')} '?' labels left - assign them to a seat or delete them, then export again")
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    convert(sys.argv[1], sys.argv[2])
