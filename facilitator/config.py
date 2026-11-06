"""all settings configs"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .seats import PLACEHOLDER_SEAT_AZIMUTHS_DEG  # placeholder seats live in seats.py


@dataclass
class Config:
    # --- Seats ---------------------------------------------------------------
    # Direction of each participant's chair, in degrees, from the robot's point
    # of view: 0 = straight ahead, + = robot's LEFT, - = robot's RIGHT.
    # [GRETA] PLACEHOLDER until calibrated. run_session.py replaces this with seats.json when it exists.
    seat_azimuths_deg: List[float] = field(default_factory=lambda: list(PLACEHOLDER_SEAT_AZIMUTHS_DEG))

    # --- Facilitation schedule (identical in both conditions) ----------------
    # 2 rounds per group, one topic per round, 6 questions per topic; each question is
    # addressed to one participant chosen by the policy.
    # Each topic also has a warm-up question asked to the whole group first (same in both conditions), so the robot has heard everyone before its first decision.
    topic: int = 1
    n_turns: int = 6                  # number of addressed questions (= decisions) per round

    # --- Listening: when is it time for the next turn? ---------------------------
    silence_s: float = 3.0            # after someone spoke: this much silence ends the turn
    no_response_s: float = 10.0       # if nobody speaks at all: move on after this long
    max_listen_s: float = 60.0        # hard limit per turn, even if someone is still talking
                                      # NOTE: 7 listening phases x up to 60 s + robot speech <= ~8 min per round

    # --- Laptop microphone (simulator only) --------------------------------------
    mic_threshold_ratio: float = 3.0  # speech = this many times louder than the measured room
    mic_min_level: float = 0.01       # ... and never below this level (0-1 scale)

    # --- What the robot says: ids from prompts/script.json ----------------------
    intro_prompt: str = "intro"
    outro_prompt: str = "outro"

    # Said right before each addressed question, after the robot has turned to that seat
    # ("Participant two." -> "What do you think: ..."). One id per seat: seat k = participant k,
    # so participants are told their number = the number of their (labelled) chair.
    # Same in both conditions. Set to [] to address people by head direction only.
    address_prompts: List[str] = field(default_factory=lambda: ["addr_1", "addr_2", "addr_3"])

    # ids in prompts/script.json: (warm-up to everyone, [6 addressed questions])
    topic_prompts: Dict[int, Tuple[str, List[str]]] = field(default_factory=lambda: {
        1: ("t1_open", [f"t1_q{i}" for i in range(1, 7)]),
        2: ("t2_open", [f"t2_q{i}" for i in range(1, 7)]),
    })

    # --- Robot motion ----------------------------------------------------------
    move_duration_s: float = 0.8
    body_share: float = 0.6           # part of the turn done by the body (rest by the head)

    # --- Baseline policy --------------------------------------------------------
    # "balanced" (STUDY DEFAULT): random order, but everyone addressed equally often (2 of 6 each).
    # "uniform": every choice independently random - can leave someone never addressed
    #            (~26% of rounds with 6 choices). The design report must name the one used.
    baseline: str = "balanced"
    shuffle_each_round: bool = True   # True: random order each round (still equal turns)
    seed: int = 0                     # run_session.py derives it from group + round (reproducible)

    # --- Connection -------------------------------------------------------------
    host: str = "reachy-mini.local"   # only used for --target wireless
    log_dir: str = "logs"
