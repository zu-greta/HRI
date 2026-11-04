"""What the robot DID in one round (for the log and the end-of-round summary).

The speaking-time estimate itself lives in listener.py / estimator.py; this only records
the robot's own behaviour, which must be comparable across conditions
("unequal robot behaviour" confound in the report).
"""

from typing import List, Sequence


class SpeakingTracker:
    def __init__(self, n_seats: int):
        self.times_addressed: List[int] = [0] * n_seats
        self.last_activity: List[float] = [0.0] * n_seats  # activity scores at the last decision

    def note_decision(self, seat: int, activity: Sequence[float]) -> None:
        self.times_addressed[seat] += 1
        self.last_activity = list(activity)
