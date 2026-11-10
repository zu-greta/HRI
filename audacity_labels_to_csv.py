"""Convert an Audacity label export into the label CSV the analysis expects.

In Audacity: select a stretch where one person speaks, press Cmd+B (Ctrl+B on Windows),
type the seat number (1, 2 or 3), press Enter. When done: File > Export > Export Labels...

    python audacity_labels_to_csv.py G01_R1_labels.txt labels/G01_R1.csv

Output: start_s,end_s,seat   (times in seconds from the start of the WAV file)
Labels that are not 1, 2 or 3 (e.g. "robot", "?") are skipped and listed.
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
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    convert(sys.argv[1], sys.argv[2])
