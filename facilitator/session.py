"""The fixed session script. Identical in both conditions except for the policy."""

import time

from .config import Config
from .logger import SessionLog
from .policies import Policy
from .sources import SpeakerSource
from .tracker import SpeakingTracker


def run_session(robot, policy: Policy, source: SpeakerSource, cfg: Config, log: SessionLog) -> SpeakingTracker:
    tracker = SpeakingTracker(len(cfg.seat_azimuths_deg))
    history = []

    log.log("session_start", detail=f"policy={policy.name} target={getattr(robot, 'target', '?')}")
    robot.face_group()
    for prompt in (cfg.intro_prompt, cfg.question_prompt):
        log.log("robot_say_start", detail=prompt)
        robot.say(prompt)
        log.log("robot_say_end", detail=prompt)

    for turn in range(1, cfg.n_turns + 1):
        # ---- listening phase (TODO: read `source`, attribute speech, update tracker)
        _wait(cfg.turn_interval_s, source, tracker)

        # ---- decision: the ONLY thing that differs between conditions
        seat = policy.choose(tracker.speaking_time_s, history)
        history.append(seat)
        tracker.note_addressed(seat)
        print(f"Turn {turn}/{cfg.n_turns}: addressing seat {seat + 1} "
              f"({cfg.seat_azimuths_deg[seat]:+.0f} deg)")
        log.log("decision", seat=seat + 1, detail=f"speaking_time_s={tracker.speaking_time_s}")

        robot.turn_to(cfg.seat_azimuths_deg[seat], antennas_deg=(20, -20))
        log.log("robot_turn", seat=seat + 1)
        log.log("robot_say_start", seat=seat + 1, detail=cfg.invite_prompt)
        robot.say(cfg.invite_prompt)
        log.log("robot_say_end", seat=seat + 1, detail=cfg.invite_prompt)

    robot.face_group()
    log.log("robot_say_start", detail=cfg.outro_prompt)
    robot.say(cfg.outro_prompt)
    log.log("robot_say_end", detail=cfg.outro_prompt)
    log.log("session_end", detail=f"times_addressed={tracker.times_addressed}")
    return tracker


def _wait(seconds: float, source: SpeakerSource, tracker: SpeakingTracker, tick_s: float = 0.1) -> None:
    """Wait for the listening phase while polling the speaker source.

    PLACEHOLDER: readings are ignored for now. Later: attribution.py turns each
    reading into a seat and calls tracker.add_speech(seat, tick_s).
    """
    end = time.time() + seconds
    while time.time() < end:
        source.read()
        time.sleep(min(tick_s, max(0.0, end - time.time())))
