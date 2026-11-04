"""See what a session looks like: a SHORT round with a simulated 3-person group.

    python sim_scenario.py --no-robot --fast             # no simulator needed, finishes in seconds
    python sim_scenario.py                               # watch it in the MuJoCo simulator (real time)
    python sim_scenario.py --condition adaptive          # only one condition (default: both)
    python sim_scenario.py --no-robot                    # real time with voices, no simulator
    python sim_scenario.py --mute                        # real time, text only

Before the simulator run, start it in another terminal:
    mjpython run_sim.py        # macOS   (Windows/Linux: python run_sim.py)
    (or start the simulator from Reachy Mini Control)

What is real and what is simulated
  REAL       the study code: run_session() (the fixed script), the listener (HMM attribution +
             turn-decay estimate), the policies, the event log and the tick log.
  SIMULATED  the people. Alex (seat 1) talks a lot, Ben (seat 2) is average, Chloe (seat 3) is quiet.
             They react to the robot: whoever the robot addresses answers, then Alex often jumps in.
             The robot is NOT told who speaks: it gets simulated head-mounted microphone readings
             (noise, outliers, missed speech, front/back mirroring, the array turning with the head)
             and has to work it out with the real detection code.
  SHORTENED  3 addressed questions instead of 6, 1.5 s of silence ends a turn instead of 3 s.
  VOICES     in real time (not --fast, not --mute) everything is spoken on this computer:
             the robot plays prompts/<id>.wav (the study audio, from make_prompts.py; generated
             into a temporary folder if missing) and each person has their own computer voice.
             macOS: built in. Windows: pyttsx3 (in requirements.txt). Linux: sudo apt install
             espeak-ng. If no voice or audio player is found it falls back to text only.

Logs go to logs/scenario/ (same format as a real round). This file is a demo; it is not used
by the study.
"""

import argparse
import hashlib
import math
import platform
import random
import shutil
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from facilitator.config import Config
from facilitator.detection_config import DetectionConfig
from facilitator.listener import ParticipationListener
from facilitator.logger import SessionLog
from facilitator.policies import make_policy
from facilitator.seats import load_seat_azimuths
from facilitator.session import run_session
from facilitator.sim_sources import MicModel
from facilitator.simulation import gini
from facilitator.sources import Reading, SpeakerSource
from facilitator.ticklog import TickLog

# ----------------------------------------------------------------------------- the simulated people
NAMES = ["Alex", "Ben", "Chloe"]
WORDS_PER_S = 2.6
OPEN_FLOOR = [  # after the warm-up question to everyone
    (0, "Oh, easy. Personal finance. Nobody teaches you how taxes, rent or credit cards work, and then "
        "suddenly you are expected to know all of it."),
    (1, "Yeah, I agree with that."),
    (0, "And it would save people so much stress later. Honestly it should be compulsory."),
]
ANSWERS = {  # what each person says when addressed (in order, then repeated)
    0: ["Well, as I said, money skills. Cooking too, because most students live on pasta and toast.",
        "School is far too theoretical, in my opinion. Practical subjects in general.",
        "Coding, definitely. Everything runs on software now."],
    1: ["I would say first aid. It is short to teach and it can save a life.",
        "Maybe something about dealing with stress before exams.",
        "Debating, because it teaches you to listen to the other side."],
    2: ["Um, maybe sign language?",
        "I think learning how to disagree respectfully would help a lot.",
        "Honestly, a class on how to study properly."],
}
JUMP_INS = [(0, "Sure, but realistically there is no time in the timetable for everything."),
            (0, "Exactly, and you could combine that with money skills in one practical class."),
            (1, "Oh, I had not thought of that."),
            (0, "Okay, but if we had to pick just one, I still say finance.")]
ANSWER_PROB = [0.95, 0.9, 0.75]   # chance of answering when addressed
JUMP_IN_PROB = 0.7                # chance someone (mostly Alex) adds a comment afterwards


PEOPLE_VOICES = [  # first installed name is used: macOS `say` voices, Windows SAPI name parts, espeak variants
    ["Daniel", "Alex", "Fred", "David", "en+m3"],
    ["Tom", "Ralph", "Mark", "en+m7"],
    ["Karen", "Moira", "Samantha", "Zira", "en+f3"],
]


# ----------------------------------------------------------------------------- audio (optional)
class Voices:
    """Text -> wav (facilitator/tts.py) and playback on this computer. Every failure = silent fallback."""

    def __init__(self, enabled: bool):
        self.system = platform.system()
        self.player = self._find_player() if enabled else None
        self.enabled = self.player is not None
        self.cache = Path(".scenario_voices")  # kept between runs (git-ignored), so only the first run waits
        self.cache.mkdir(exist_ok=True)
        self.people = [self._pick(c) for c in PEOPLE_VOICES] if self.enabled else ["", "", ""]
        if enabled and not self.enabled:
            print("(no audio player found - text only)")

    def _find_player(self) -> Optional[str]:
        if self.system == "Windows":
            return "winsound"
        if self.system == "Darwin":
            return shutil.which("afplay")
        return shutil.which("paplay") or shutil.which("aplay")

    def _pick(self, candidates: List[str]) -> str:
        try:
            if self.system == "Darwin":
                out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
                names = {ln.split()[0] for ln in out.splitlines() if ln.strip()}
                return next((v for v in candidates if v in names), "")
            if self.system == "Windows":
                import pyttsx3

                names = [v.name for v in pyttsx3.init().getProperty("voices")]
                return next((c for c in candidates if any(c.lower() in n.lower() for n in names)), "")
            return next((v for v in candidates if v.startswith("en+")), "")
        except Exception:  # noqa: BLE001
            return ""

    def wav(self, text: str, voice: str = "") -> Optional[Path]:
        if not self.enabled:
            return None
        out = self.cache / self._name(text, voice)
        if not out.exists():
            try:
                from facilitator.tts import synthesize

                synthesize(text, out, voice)
            except (Exception, SystemExit) as exc:  # noqa: BLE001 - no TTS engine, unknown voice
                print(f"(could not synthesise speech: {exc} - text only from here)")
                self.enabled = False
                return None
        return out if out.exists() else None

    def prepare(self, items) -> None:
        """Synthesise all (text, voice) pairs up front, with progress, so nothing lags during a round."""
        todo = [(t, v) for t, v in items if not (self.cache / self._name(t, v)).exists()]
        for i, (text, voice) in enumerate(todo, 1):
            print(f"\rPreparing voices {i}/{len(todo)} (first run only; --mute skips this) ...", end="", flush=True)
            if self.wav(text, voice) is None:
                break
        if todo:
            print()

    @staticmethod
    def _name(text: str, voice: str) -> str:
        return hashlib.sha1(f"{voice}|{text}".encode()).hexdigest()[:16] + ".wav"

    def play(self, path: Path, block: bool) -> None:
        try:
            if self.player == "winsound":
                import winsound

                winsound.PlaySound(str(path), winsound.SND_FILENAME | (0 if block else winsound.SND_ASYNC))
            elif block:
                subprocess.run([self.player, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen([self.player, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:  # noqa: BLE001 - no sound device: keep going silently
            pass


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


@dataclass
class Line:
    seat: int
    text: str
    start: float
    end: float
    shown: bool = False
    audio: Optional[Path] = None


class SimulatedGroup(SpeakerSource):
    """Three simulated people, heard through a simulated head-mounted microphone array."""

    def __init__(self, seats: List[float], clock, head_yaw, robot_speaking, seed: int, voices: Voices):
        self.seats, self.clock, self.head_yaw, self.robot_speaking = list(seats), clock, head_yaw, robot_speaking
        self.voices = voices
        self.rng = random.Random(seed)
        self.mic = MicModel()
        self.timeline: List[Line] = []
        self.answer_i = [0, 0, 0]
        self.jump_i = 0
        self.true_s = [0.0, 0.0, 0.0]

    def _schedule(self, lines) -> None:
        t = max(self.clock() + 0.8, self.timeline[-1].end if self.timeline else 0.0)
        for seat, text in lines:
            t += self.rng.uniform(0.3, 0.8)
            audio = self.voices.wav(text, self.voices.people[seat])
            dur = wav_seconds(audio) if audio else max(1.0, len(text.split()) / WORDS_PER_S)
            self.timeline.append(Line(seat, text, t, t + dur, audio=audio))
            self.true_s[seat] += dur
            t += dur

    def open_floor(self) -> None:
        self._schedule(OPEN_FLOOR)

    def addressed(self, seat: int) -> None:
        lines = []
        if self.rng.random() < ANSWER_PROB[seat]:
            pool = ANSWERS[seat]
            lines.append((seat, pool[self.answer_i[seat] % len(pool)]))
            self.answer_i[seat] += 1
        if self.rng.random() < JUMP_IN_PROB:
            jumper, text = JUMP_INS[self.jump_i % len(JUMP_INS)]
            self.jump_i += 1
            if not lines or lines[0][0] != jumper:
                lines.append((jumper, text))
        self._schedule(lines)

    def read(self) -> Optional[Reading]:
        if self.robot_speaking():
            return Reading(math.pi / 2, True)  # the robot hears its own voice (detection ignores it)
        now = self.clock()
        line = next((ln for ln in self.timeline if ln.start <= now < ln.end), None)
        if line is not None and not line.shown:
            line.shown = True
            print(f"      {NAMES[line.seat]:>5s} (seat {line.seat + 1}): {line.text}")
            if line.audio is not None:
                self.voices.play(line.audio, block=False)
        world = None if line is None else self.seats[line.seat]
        return self.mic.observe(world, self.head_yaw(), self.rng)


# ----------------------------------------------------------------------------- the robot side
class VirtualClock:
    """--fast: time only moves when something sleeps, so a round takes seconds."""

    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


class RobotVoice:
    """The robot's speech: plays prompts/<id>.wav when voices are on (otherwise just waits as long
    as saying it would take); same echo margin as speech.py."""

    ECHO_MARGIN_S = 0.5

    def __init__(self, texts, clock, sleep, voices: Voices):
        self.texts, self.clock, self.sleep, self.voices = texts, clock, sleep, voices
        self._until = -1.0
        self.audio = {}
        if voices.enabled:
            for pid, text in texts.items():
                study_wav = Path("prompts") / f"{pid}.wav"
                self.audio[pid] = study_wav if study_wav.exists() else voices.wav(text)

    def say(self, prompt_id: str) -> float:
        path = self.audio.get(prompt_id)
        duration = wav_seconds(path) if path else max(1.5, len(self.texts[prompt_id].split()) / 2.8)
        self._until = self.clock() + duration + self.ECHO_MARGIN_S
        start = self.clock()
        if path:
            self.voices.play(path, block=True)
        self.sleep(max(0.0, duration - (self.clock() - start)))  # same timing even if playback failed
        return duration

    def is_speaking(self) -> bool:
        return self.clock() < self._until


class FakeBody:
    """--no-robot: remembers where the head points."""

    target = "none"

    def __init__(self, sleep, move_s: float):
        self.yaw, self.sleep, self.move_s = 0.0, sleep, move_s

    def turn_to(self, azimuth_deg: float, antennas_deg=(0.0, 0.0)) -> None:
        self.sleep(self.move_s)
        self.yaw = azimuth_deg

    def face_group(self) -> None:
        self.turn_to(0.0)

    def head_yaw_deg(self) -> float:
        return self.yaw

    def close(self) -> None:
        pass


class ScenarioRobot:
    """What run_session() talks to: a body (simulator or fake) + speech + tells the group what happened."""

    def __init__(self, body, speaker: RobotVoice, seats, cfg: Config):
        self.body, self.speaker, self.seats, self.cfg = body, speaker, list(seats), cfg
        self.target = getattr(body, "target", "sim")
        self.group: Optional[SimulatedGroup] = None
        self.facing: Optional[int] = None

    def face_group(self) -> None:
        self.facing = None
        self.body.face_group()

    def turn_to(self, azimuth_deg, antennas_deg=(0.0, 0.0)) -> None:
        self.facing = min(range(len(self.seats)), key=lambda k: abs(self.seats[k] - azimuth_deg))
        print(f"\n   [robot turns to seat {self.facing + 1} - {NAMES[self.facing]}, {azimuth_deg:+.0f} deg]")
        self.body.turn_to(azimuth_deg, antennas_deg)

    def say(self, prompt_id: str) -> float:
        who = "everyone" if self.facing is None else NAMES[self.facing]
        print(f"   ROBOT -> {who}: \"{self.speaker.texts[prompt_id]}\"")
        duration = self.speaker.say(prompt_id)
        warmup, questions = self.cfg.topic_prompts[self.cfg.topic]
        if prompt_id == warmup:
            self.group.open_floor()
        elif prompt_id in questions and self.facing is not None:
            self.group.addressed(self.facing)
        return duration

    def is_speaking(self) -> bool:
        return self.speaker.is_speaking()

    def head_yaw_deg(self) -> float:
        return self.body.head_yaw_deg()


# ----------------------------------------------------------------------------- one round
def all_people_lines():
    return OPEN_FLOOR + JUMP_INS + [(k, t) for k, ts in ANSWERS.items() for t in ts]


def simulator_reachable(base_url: str = "http://localhost:8000") -> bool:
    """The simulator's daemon answers on port 8000 (otherwise connecting would just wait)."""
    import requests

    try:
        requests.get(f"{base_url}/api/daemon/status", timeout=3)
        return True
    except requests.RequestException:
        return False


def run_round(condition: str, args, seed: int, voices: "Voices", texts: dict, real_robot=None) -> dict:

    cfg = Config()
    cfg.seat_azimuths_deg, _ = load_seat_azimuths()
    cfg.n_turns, cfg.topic = args.turns, 1
    cfg.silence_s, cfg.no_response_s, cfg.max_listen_s = 1.5, 6.0, 40.0
    det = DetectionConfig.load()
    policy = make_policy(condition, len(cfg.seat_azimuths_deg), True, seed, det, baseline=cfg.baseline)

    if args.fast:
        vclock = VirtualClock()
        clock, sleep = vclock.now, vclock.sleep
    else:
        clock, sleep = time.monotonic, time.sleep
    speaker = RobotVoice(texts, clock, sleep, voices)
    body = real_robot if real_robot is not None else FakeBody(sleep, cfg.move_duration_s)
    robot = ScenarioRobot(body, speaker, cfg.seat_azimuths_deg, cfg)
    group = SimulatedGroup(cfg.seat_azimuths_deg, clock, robot.head_yaw_deg, robot.is_speaking, seed, voices)
    robot.group = group

    title = ("BASELINE - balanced random order (ignores who talks)" if condition == "baseline"
             else "ADAPTIVE - addresses whoever the robot detects as least active")
    print("\n" + "=" * 78 + f"\n {title}\n Alex (seat 1) talks a lot, Ben (seat 2) is average, "
          "Chloe (seat 3) is quiet.\n" + "=" * 78)
    log = SessionLog("SCENARIO", condition, "logs/scenario", clock=clock)
    ticklog = TickLog(log.path)
    listener = ParticipationListener.from_config(cfg.seat_azimuths_deg, det)
    try:
        tracker = run_session(robot, policy, group, cfg, log, listener=listener, ticklog=ticklog,
                              clock=clock, sleep=sleep)
    finally:
        log.close()
        ticklog.close()

    est = listener.activity()
    print("\n" + "-" * 78)
    print(f" {'':26s}" + "".join(f"{n:>10s}" for n in NAMES))
    print(f" {'times addressed':26s}" + "".join(f"{v:>10d}" for v in tracker.times_addressed))
    print(f" {'really spoke (s)':26s}" + "".join(f"{v:>10.1f}" for v in group.true_s))
    print(f" {'robot estimate (score)':26s}" + "".join(f"{v:>10.1f}" for v in est))
    print(f" Gini of real speaking time: {gini(group.true_s):.3f}  (0 = perfectly even)")
    print(f" Logs: {log.path} (+ _ticks.csv)")
    print("-" * 78)
    return {"condition": condition, "gini": gini(group.true_s), "addressed": tracker.times_addressed}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--condition", choices=("baseline", "adaptive", "both"), default="both")
    p.add_argument("--turns", type=int, default=3, help="addressed questions (the study uses 6)")
    p.add_argument("--no-robot", action="store_true", help="no simulator: a fake head that just remembers its angle")
    p.add_argument("--fast", action="store_true", help="virtual clock, finishes in seconds (needs --no-robot; silent)")
    p.add_argument("--mute", action="store_true", help="real time but text only (no voices)")
    p.add_argument("--seed", type=int, default=7, help="same seed = the same people's behaviour in both conditions")
    args = p.parse_args()
    if args.fast and not args.no_robot:
        p.error("--fast needs --no-robot (the simulator moves in real time)")
    import json

    texts = {k: v for k, v in json.loads(Path("prompts/script.json").read_text()).items() if not k.startswith("_")}

    # 1) voices (once, cached on disk)
    voices = Voices(enabled=not (args.fast or args.mute))
    if voices.enabled:
        voices.prepare([(t, "") for pid, t in texts.items() if not (Path("prompts") / f"{pid}.wav").exists()]
                       + [(t, voices.people[seat]) for seat, t in all_people_lines()])

    # 2) the simulator (once, reused for both rounds)
    real_robot = None
    if not args.no_robot:
        from facilitator.robot_io import Robot

        cfg = Config()
        print("Checking the simulator on http://localhost:8000 ...")
        if not simulator_reachable():
            raise SystemExit("The simulator is not running (nothing answers on localhost:8000).\n"
                             "Start it first in another terminal (mjpython run_sim.py on macOS, or Reachy Mini "
                             "Control), wait until the robot appears, then run this again.\n"
                             "Or run without it: python sim_scenario.py --no-robot")
        print("Connecting to the simulated robot ...")
        real_robot = Robot("sim", cfg.host, cfg.move_duration_s, cfg.body_share)
        real_robot.connect()
        print("Connected.")
    try:
        results = [run_round(c, args, args.seed, voices, texts, real_robot) for c in
                   (["baseline", "adaptive"] if args.condition == "both" else [args.condition])]
    finally:
        if real_robot is not None:
            real_robot.close()
    if len(results) == 2:
        print("\nSUMMARY (one simulated group, so this is an illustration, not evidence):")
        for r in results:
            print(f"   {r['condition']:9s} Gini {r['gini']:.3f}  addressed (seat 1/2/3) {r['addressed']}")


if __name__ == "__main__":
    main()