"""detection for passive/active - parameters
[GRETA] replace all the PLACEHOLDER configs with the calibrated values
"""

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

PARAMS_FILE = Path(__file__).resolve().parent.parent / "detection_params.json"


@dataclass
class DetectionConfig:
    # --- Which methods to use ------------------------------------------------------
    # "hmm"     = our method (smoothed, head-aware, front/back-aware)
    # "nearest" = Micbot-style baseline: each reading -> nearest seat
    attributor: str = "hmm"
    # "turns_decay" = our method (speaking turns only, recent speech weighs more)
    # "cumulative"  = Micbot-style baseline: total speech since the start
    estimator: str = "turns_decay"

    # --- Microphone model (used by the HMM) - PLACEHOLDERS, fit on recordings ------
    angle_sigma_deg: float = 12.0     # PLACEHOLDER spread of the measured angle around a speaker
    outlier_rate: float = 0.10        # PLACEHOLDER fraction of speech readings pointing anywhere (echo, noise)
    vad_miss_rate: float = 0.15       # PLACEHOLDER P(speech flag False | someone talking)
    vad_false_alarm_rate: float = 0.05  # PLACEHOLDER P(speech flag True | nobody talking)

    # --- Speaker dynamics (HMM transitions, per 0.1 s tick) --------------------------
    stay_speaking: float = 0.95       # a speaker usually keeps talking for the next 0.1 s
    stay_silent: float = 0.90
    min_confidence: float = 0.55      # report a seat only if the filter is at least this sure

    # --- Nearest-seat baseline ----------------------------------------------------------
    seat_tolerance_deg: float = 25.0  # further than this from every seat -> nobody

    # --- Activity estimate -----------------------------------------------------------------
    merge_gap_s: float = 0.6          # pauses shorter than this stay inside one utterance
    min_turn_s: float = 1.0           # utterances shorter than this = backchannel ("mm-hm", "yeah")
    half_life_s: float = 120.0        # speech from 2 minutes ago counts half as much as speech now

    # --- Adaptive policy -----------------------------------------------------------------
    margin_s: float = 0.5             # scores within this of the lowest count as a tie (ties -> whoever was addressed longest ago)
    repeat_margin_s: float = 0.0      # 0 = off (default - in sim, lowered how often quietest was chosen). 
                                      # If > 0: invite the same person twice in a row only if they are this much quieter than everyone else. 
    max_consecutive: int = 0          # 0 = off (default - in sim, cap of 2 lowered hit rate from ~0.9 to ~0.75).
                                      # If > 0: never invite the same person more than this many times in a row (social safeguard for someone who never answers)

    # --- Robot's own voice + logging -------------------------------------------------------
    ignore_while_robot_speaks: bool = True
    log_ticks: bool = True            # write every 0.1 s reading to *_ticks.csv (replay + evaluation)

    @classmethod
    def load(cls, path: Path = PARAMS_FILE) -> "DetectionConfig":
        """Defaults, overridden by detection_params.json if it exists."""
        cfg = cls()
        path = Path(path)
        if path.exists():
            known = {f.name for f in fields(cls)}
            for k, v in json.loads(path.read_text()).items():
                if k in known:
                    setattr(cfg, k, v)
        return cfg

    def save(self, path: Path = PARAMS_FILE) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))
