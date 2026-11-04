"""all settings configs"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # --- Seats ---------------------------------------------------------------
    # Direction of each participant's chair, in degrees, from the robot's point
    # of view: 0 = straight ahead, + = robot's LEFT, - = robot's RIGHT.
    # (TODO: replaced by values measured in calibration.)
    seat_azimuths_deg: List[float] = field(default_factory=lambda: [50.0, 0.0, -50.0])

    # --- Facilitation schedule (identical in both conditions) ----------------
    n_turns: int = 6                  # number of times the robot addresses someone

    # --- Listening: when is it time for the next turn? ---------------------------
    silence_s: float = 3.0            # after someone spoke: this much silence ends the turn
    no_response_s: float = 10.0       # if nobody speaks at all: move on after this long
    max_listen_s: float = 60.0        # hard limit per turn, even if someone is still talking

    # --- Laptop microphone (simulator only) --------------------------------------
    mic_threshold_ratio: float = 3.0  # speech = this many times louder than the measured room
    mic_min_level: float = 0.01       # ... and never below this level (0-1 scale)

    # --- What the robot says: ids from prompts/script.json ----------------------
    intro_prompt: str = "intro"
    question_prompt: str = "question_1"
    invite_prompt: str = "invite"
    outro_prompt: str = "outro"

    # --- Robot motion ----------------------------------------------------------
    move_duration_s: float = 0.8
    body_share: float = 0.6           # part of the turn done by the body (rest by the head)

    # --- Baseline policy --------------------------------------------------------
    shuffle_each_round: bool = True   # True: random order each round (still equal turns)
    seed: int = 0                     # fixed seed -> the same sequence every run

    # --- Connection -------------------------------------------------------------
    host: str = "reachy-mini.local"   # only used for --target wireless
    log_dir: str = "logs"
