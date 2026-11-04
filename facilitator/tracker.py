"""Speaking time per seat.  (Simple working version; attribution comes later.)

TODO:
  - convert microphone angle (head frame) -> world azimuth using the head pose
  - map world azimuth -> nearest seat within a tolerance (or None)
  - debounce, and ignore readings while the robot itself is speaking
"""

from typing import List


class SpeakingTracker:
    def __init__(self, n_seats: int):
        self.speaking_time_s: List[float] = [0.0] * n_seats
        self.times_addressed: List[int] = [0] * n_seats

    def add_speech(self, seat: int, seconds: float) -> None:
        self.speaking_time_s[seat] += seconds

    def note_addressed(self, seat: int) -> None:
        self.times_addressed[seat] += 1
