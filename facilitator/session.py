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
        # ---- listening phase (TODO: attribute speech to a seat, update tracker)
        wait_for_silence(robot, source, cfg, log)

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

    # ---- give the group a chance to answer the last invitation
    wait_for_silence(robot, source, cfg, log)

    robot.face_group()
    log.log("robot_say_start", detail=cfg.outro_prompt)
    robot.say(cfg.outro_prompt)
    log.log("robot_say_end", detail=cfg.outro_prompt)
    log.log("session_end", detail=f"times_addressed={tracker.times_addressed}")
    return tracker


def wait_for_silence(robot, source: SpeakerSource, cfg: Config, log: SessionLog,
                     clock=time.monotonic, sleep=time.sleep, tick_s: float = 0.1) -> str:
    """Listen until the group has finished talking, and return why listening ended.

        "silence"      someone spoke, then nobody spoke for cfg.silence_s
        "no_response"  the microphones worked, but nobody spoke for cfg.no_response_s
        "no_data"      as above, but the source never returned a reading
        "max_listen"   cfg.max_listen_s was reached (even if someone is still talking)
    """
    while robot.is_speaking():  # the robot's own voice and echo must not count as speech
        source.read()
        sleep(tick_s)

    log.log("listen_start")
    start = last_speech = previous = clock()
    heard_speech = got_data = False
    speech_s = 0.0

    while True:
        now = clock()
        reading = source.read()
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
