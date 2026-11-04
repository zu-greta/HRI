"""The fixed session script. Identical in both conditions except for the policy."""

import time
from typing import Optional

from .config import Config
from .detection_config import DetectionConfig  
from .listener import Listener, ParticipationListener  
from .logger import SessionLog
from .policies import Policy
from .sources import SpeakerSource
from .tracker import SpeakingTracker


def run_session(robot, policy: Policy, source: SpeakerSource, cfg: Config, log: SessionLog,
                listener: Optional[Listener] = None, ticklog=None) -> SpeakingTracker:
    tracker = SpeakingTracker(len(cfg.seat_azimuths_deg))
    history = []
    # [GRETA] HOOK 0: who-speaks / who-is-quiet detection. runs in both conditions (robot's estimate logged for baseline sessions too; only adaptive policy uses it to decide)
    if listener is None:
        listener = ParticipationListener.from_config(cfg.seat_azimuths_deg, DetectionConfig.load())

    # round = intro, warm-up question to everyone, then n_turns questions, each addressed to the participant the policy chooses 
    warmup, questions = cfg.topic_prompts[cfg.topic]
    questions = questions[:cfg.n_turns]
    log.log("session_start", detail=f"policy={policy.name} target={getattr(robot, 'target', '?')} "
                                    f"topic={cfg.topic} questions={len(questions)}")
    robot.face_group()
    for prompt in (cfg.intro_prompt, warmup):
        log.log("robot_say_start", detail=prompt)
        robot.say(prompt)
        log.log("robot_say_end", detail=prompt)

    for turn, question in enumerate(questions, start=1):
        # ---- listening phase: the group talks until it goes quiet (detection runs here)
        wait_for_silence(robot, source, cfg, log, listener=listener, ticklog=ticklog)

        # ---- decision: the only thing that differs between conditions
        activity = listener.activity()  # [GRETA] HOOK 2: one activity score per seat
        tracker.speaking_time_s = list(activity)
        seat = policy.choose(activity, history)
        history.append(seat)
        tracker.note_addressed(seat)
        print(f"Turn {turn}/{len(questions)}: addressing seat {seat + 1} "
              f"({cfg.seat_azimuths_deg[seat]:+.0f} deg)  activity={[round(a, 1) for a in activity]}")
        log.log("decision", seat=seat + 1, detail=f"activity={[round(a, 2) for a in activity]}")

        robot.turn_to(cfg.seat_azimuths_deg[seat], antennas_deg=(20, -20))
        log.log("robot_turn", seat=seat + 1)
        log.log("robot_say_start", seat=seat + 1, detail=question)
        robot.say(question)  # [GRETA] the question itself is addressed to the chosen person
        log.log("robot_say_end", seat=seat + 1, detail=question)

    # ---- give the group a chance to answer the last question
    wait_for_silence(robot, source, cfg, log, listener=listener, ticklog=ticklog)

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
    """
    def hear(now: float):
        """[GRETA] HOOK 1: read the microphones once and pass the reading on."""
        reading = source.read()
        if listener is not None:
            tick = listener.update(reading, now, robot.is_speaking(), _head_yaw_deg(robot))
            if ticklog is not None:
                ticklog.write(tick, listener.activity())
        return reading

    while robot.is_speaking():  # the robot's own voice and echo must not count as speech
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
    """Head direction in the room.Microphones turn with the head."""
    try:
        return float(robot.head_yaw_deg())
    except Exception:  # fake robots in tests, or a dropped connection
        return 0.0
