"""Timestamped CSV log: one row per event for experimental data"""

import csv
import time
from datetime import datetime
from pathlib import Path


class SessionLog:
    FIELDS = ["time_iso", "t_s", "group", "condition", "event", "seat", "detail"]

    def __init__(self, group: str, condition: str, folder: str = "logs"):
        Path(folder).mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = Path(folder) / f"{group}_{condition}_{stamp}.csv"
        self._f = open(self.path, "w", newline="")
        self._w = csv.writer(self._f)
        self._w.writerow(self.FIELDS)
        self._t0 = time.time()
        self.group, self.condition = group, condition

    def log(self, event: str, seat: object = "", detail: str = "") -> None:
        self._w.writerow([datetime.now().isoformat(timespec="milliseconds"),
                          f"{time.time() - self._t0:.3f}", self.group, self.condition, event, seat, detail])
        self._f.flush()  # data survives a crash

    def close(self) -> None:
        self._f.close()
