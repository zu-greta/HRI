"""The fixed session script. Identical in both conditions except for the policy.

One round:
    intro (to everyone) -> warm-up question (to everyone)
    6 x [ listen until quiet -> decide whom to address -> turn to them
          -> say their number ("Participant two.") -> ask the question ]
    listen until quiet (answer to the last question) -> outro

Detection (the listener) runs in BOTH conditions, so the robot's estimate is logged for
baseline rounds too; only the adaptive policy uses it to decide.

Clocks: `clock` must be the same clock the listener, the tick log and the event log's
mono_s column use (time.monotonic() in real sessions; a virtual clock in tests and in
sim_scenario.py --fast).
"""

import time
from typing import Callable, Optional

from .config import Config
from .detection_config import DetectionConfig
from .listener import Listener, ParticipationListener
from .logger import SessionLog
from .policies import Policy
from .sources import SpeakerSource
from .tracker import SpeakingTracker


def run_session(robot, policy: Policy, source: SpeakerSource, cfg: Config, log: SessionLog,
                listener: Optional[Listener] = None, ticklog=None,
                clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep
                ) -> SpeakingTracker:
    tracker = SpeakingTracker(len(cfg.seat_azimuths_deg))
    history = []
    # HOOK 0 (detection): created here if the caller did not pass one
    if listener is None:
        listener = ParticipationListener.from_config(cfg.seat_azimuths_deg, DetectionConfig.load())

    warmup, questions = cfg.topic_prompts[cfg.topic]
    questions = questions[:cfg.n_turns]
    log.log("session_start", detail=f"policy={policy.name} target={getattr(robot, 'target', '?')} "
                                    f"topic={cfg.topic} questions={len(questions)}")
    robot.face_group()
    for prompt in (cfg.intro_prompt, warmup):
        # the start of the intro is the VIDEO SYNC POINT: its mono_s in the event log = the moment the robot starts speaking on the video
        log.log("robot_say_start", detail=prompt)
        robot.say(prompt)
        log.log("robot_say_end", detail=prompt)

    for turn, question in enumerate(questions, start=1):
        # ---- listening phase: the group talks until it goes quiet (detection runs here)
        wait_for_silence(robot, source, cfg, log, clock=clock, sleep=sleep, listener=listener, ticklog=ticklog)

        # ---- decision: the only thing that differs between conditions
        activity = listener.activity()  # HOOK 2: one activity score per seat (lower = quieter)
        seat = policy.choose(activity, history)
        history.append(seat)
        tracker.note_decision(seat, activity)
        print(f"Turn {turn}/{len(questions)}: addressing seat {seat + 1} "
              f"({cfg.seat_azimuths_deg[seat]:+.0f} deg)  activity={[round(a, 1) for a in activity]}")
        log.log("decision", seat=seat + 1, detail=f"activity={[round(a, 2) for a in activity]}")

        robot.turn_to(cfg.seat_azimuths_deg[seat], antennas_deg=(20, -20))
        log.log("robot_turn", seat=seat + 1)
        if cfg.address_prompts:  # say the participant's number first, e.g. "Participant two."
            name = cfg.address_prompts[seat]
            log.log("robot_say_start", seat=seat + 1, detail=name)
            robot.say(name)
            log.log("robot_say_end", seat=seat + 1, detail=name)
        log.log("robot_say_start", seat=seat + 1, detail=question)
        robot.say(question)  # the question is addressed to the chosen person (the robot is facing them)
        log.log("robot_say_end", seat=seat + 1, detail=question)

    # ---- give the group a chance to answer the last question
    wait_for_silence(robot, source, cfg, log, clock=clock, sleep=sleep, listener=listener, ticklog=ticklog)

    robot.face_group()
    log.log("robot_say_start", detail=cfg.outro_prompt)
    robot.say(cfg.outro_prompt)
    log.log("robot_say_end", detail=cfg.outro_prompt)
    log.log("session_end", detail=f"times_addressed={tracker.times_addressed}")
    return tracker


def wait_for_silence(robot, source: SpeakerSource, cfg: Config, log: SessionLog,
                     clock=time.monotonic, sleep=time.sleep, tick_s: float = 0.1,
                     listener: Optional[Listener] = None, ticklog=None) -> str:
    """Listen until the group has finished talking, and return why listening ended.

        "silence"      someone spoke, then nobody spoke for cfg.silence_s
        "no_response"  the microphones worked, but nobody spoke for cfg.no_response_s
        "no_data"      as above, but the source never returned a reading
        "max_listen"   cfg.max_listen_s was reached (even if someone is still talking)

    Note: the end-of-turn rule uses the RAW speech flag (any voice; the robot's own echo
    margin is waited out first), not the attributed seat. It is identical in both
    conditions, so it cannot bias the comparison.
    """
    def hear(now: float):
        """HOOK 1: read the microphones once and pass the reading to the listener."""
        reading = source.read()
        if listener is not None:
            tick = listener.update(reading, now, robot.is_speaking(), _head_yaw_deg(robot))
            if ticklog is not None:
                ticklog.write(tick, listener.activity())
        return reading

    while robot.is_speaking():  # echo margin after the robot's voice: logged, but ignored by detection
        hear(clock())
        sleep(tick_s)

    log.log("listen_start")
    start = last_speech = previous = clock()
    heard_speech = got_data = False
    speech_s = 0.0

    while True:
        now = clock()
        reading = hear(now)
        got_data = got_data or reading is not None
        if reading is not None and reading.speech_detected:
            heard_speech = True
            last_speech = now
            speech_s += now - previous
        previous = now

        if now - start >= cfg.max_listen_s:
            reason = "max_listen"
        elif heard_speech and now - last_speech >= cfg.silence_s:
            reason = "silence"
        elif not heard_speech and now - start >= cfg.no_response_s:
            reason = "no_response" if got_data else "no_data"
        else:
            sleep(tick_s)
            continue

        log.log("listen_end", detail=f"reason={reason} waited_s={now - start:.1f} speech_s={speech_s:.1f}")
        print(f"   [listening ended] {reason} after {now - start:.1f} s ({speech_s:.1f} s of speech)")
        return reason


def _head_yaw_deg(robot) -> float:
    """Head direction in the room (+ = robot's left). The microphones turn with the head."""
    try:
        return float(robot.head_yaw_deg())
    except Exception:  # fake robots in tests, or a dropped connection
        return 0.0
