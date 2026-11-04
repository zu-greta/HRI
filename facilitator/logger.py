"""Timestamped CSV event log: one row per event (the experimental record of a round).

Columns:
  time_iso   wall-clock time (for matching with notes / the run sheet)
  t_s        seconds since the log was opened (wall clock)
  mono_s     time.monotonic() at the event = the SAME clock as the tick log (*_ticks.csv)
             -> use it to line up events, ticks and video (see PROJECT_OVERVIEW.md, "Clock sync")
  group, condition, event, seat (1-based), detail
"""

import csv
import time
from datetime import datetime
from pathlib import Path


class SessionLog:
    FIELDS = ["time_iso", "t_s", "mono_s", "group", "condition", "event", "seat", "detail"]

    def __init__(self, group: str, condition: str, folder: str = "logs", clock=time.monotonic):
        Path(folder).mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = Path(folder) / f"{group}_{condition}_{stamp}.csv"
        self._f = open(self.path, "w", newline="")
        self._w = csv.writer(self._f)
        self._w.writerow(self.FIELDS)
        self._t0 = time.time()
        self._clock = clock
        self.group, self.condition = group, condition

    def log(self, event: str, seat: object = "", detail: str = "") -> None:
        self._w.writerow([datetime.now().isoformat(timespec="milliseconds"), f"{time.time() - self._t0:.3f}",
                          f"{self._clock():.3f}", self.group, self.condition, event, seat, detail])
        self._f.flush()  # data survives a crash

    def close(self) -> None:
        self._f.close()
