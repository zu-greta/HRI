"""
[ANALYSIS]
Reading the recorded study data 
Used by build_sessions.py, make_label_templates.py, analyze_study.py and evaluate_offline.py.

One ATTEMPT = one run of run_session.py = four files with the same stem:
    <stem>.csv            event log        (mono_s = session clock)
    <stem>_ticks.csv      tick log         (t = session clock)
    <stem>_audio.wav      room audio
    <stem>_audio.json     offset_s: session-clock time of the first audio sample
A ROUND (group x round) is one or more attempts (crashed round - reruns)

Clocks: everything is put on the session clock (time.monotonic() of the laptop).
    session time = offset_s + time in the WAV        (labels are made on the WAV)
"""

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

N_SEATS = 3
TICK_CAP_S = 0.5            # same cap as the live listener: gaps (robot speaking) are not counted as speech
BACKCHANNEL_MAX_S = 1.0     # same threshold as the estimator: shorter labelled stretches = backchannels

Label = Tuple[float, float, int]   # (start, end, seat 0-based) on the session clock


# ----------------------------------------------------------------------------- sessions table
@dataclass
class Attempt:
    group: str
    order: str
    round: int
    topic: int
    condition: str          # baseline | adaptive
    quiet_seat: int         # 1-based, 0 = unknown
    attempt: int
    include: bool
    log: str
    ticks: str
    audio: str
    labels: str
    params: str             # detection_params json used live (room calibration)
    offset: Optional[float] = None

    @property
    def key(self) -> Tuple[str, int]:
        return self.group, self.round


SESSION_FIELDS = ["group", "order", "round", "topic", "condition", "quiet_seat", "attempt", "include",
                  "log", "ticks", "audio", "labels", "params", "offset"]


def read_sessions(path: str) -> List[Attempt]:
    """study_sessions.csv; relative paths are relative to the CSV's folder."""
    base = Path(path).resolve().parent

    def p(v: str) -> str:
        v = (v or "").strip()
        return "" if not v else str(Path(v) if Path(v).is_absolute() else (base / v).resolve())

    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if not (r.get("group") or "").strip() or r["group"].startswith("#"):
                continue
            out.append(Attempt(
                group=r["group"].strip(), order=(r.get("order") or "-").strip(), round=int(r["round"]),
                topic=int(r.get("topic") or 0), condition=r["condition"].strip(),
                quiet_seat=int(r.get("quiet_seat") or 0), attempt=int(r.get("attempt") or 1),
                include=(r.get("include") or "1").strip() not in ("0", "no", "false", "False"),
                log=p(r.get("log")), ticks=p(r.get("ticks")), audio=p(r.get("audio")), labels=p(r.get("labels")),
                params=p(r.get("params")), offset=float(r["offset"]) if (r.get("offset") or "").strip() else None))
    return out


REPO = Path(__file__).resolve().parent.parent


def params_path(attempt: "Attempt") -> Path:
    """The room calibration file used live"""
    if not attempt.params:
        raise SystemExit(f"No params file for {attempt.group} R{attempt.round} attempt {attempt.attempt}: fill the "
                         "params column of study_sessions.csv (detection_params.json or detection_params_g1.json).")
    p = Path(attempt.params)
    if p.exists():
        return p
    alt = REPO / p.name
    if alt.exists():
        return alt
    raise SystemExit(f"Params file {p} not found (also not in {REPO}).")


def rounds_of(attempts: Sequence[Attempt], only_included: bool = True) -> Dict[Tuple[str, int], List[Attempt]]:
    out: Dict[Tuple[str, int], List[Attempt]] = {}
    for a in attempts:
        if a.include or not only_included:
            out.setdefault(a.key, []).append(a)
    for v in out.values():
        v.sort(key=lambda a: a.attempt)
    return dict(sorted(out.items()))


# ----------------------------------------------------------------------------- event log
@dataclass
class LogInfo:
    info: Dict[str, str] = field(default_factory=dict)        # study_info key=values
    seats: List[float] = field(default_factory=list)           # seat azimuths used live
    code: str = ""
    prompt_audio: str = ""
    start: Optional[float] = None                              # first robot_say_start (intro) = discussion start
    end: Optional[float] = None                                # session_end, or last event if crashed
    completed: bool = False
    decisions: List[Tuple[float, int, List[float]]] = field(default_factory=list)   # (mono, seat 0-based, activity)
    listen_ends: List[Tuple[str, float, float]] = field(default_factory=list)       # (reason, waited_s, speech_s)
    robot_speech: List[Tuple[float, float]] = field(default_factory=list)           # robot prompt intervals
    events: int = 0

    @property
    def all_questions(self) -> bool:
        """NOTES: we ran into network issues while conducting the study - some rounds did not finish officially but we got the results
        All 6 addressed questions were asked (the round's content is complete, even if the program
        crashed afterwards, e.g. during the outro or while closing)."""
        return self.completed or len(self.decisions) >= 6


def _kv(detail: str) -> Dict[str, str]:
    return dict(re.findall(r"(\w+)=(\S+)", detail or ""))


def read_log(path: str) -> LogInfo:
    li = LogInfo()
    say_start = None
    last = None
    with open(path, newline="") as f:
        for e in csv.DictReader(f):
            li.events += 1
            t = float(e["mono_s"]) if e.get("mono_s") else None
            last = t if t is not None else last
            ev, d = e["event"], e.get("detail", "")
            if ev == "study_info":
                li.info = _kv(d)
            elif ev == "versions":
                kv = _kv(d)
                li.code, li.prompt_audio = kv.get("code", ""), kv.get("prompt_audio", "")
            elif ev == "detection_setup":
                m = re.search(r"seats=\[([^\]]*)\]", d)
                if m:
                    li.seats = [float(x) for x in m.group(1).split(",")]
            elif ev == "robot_say_start":
                say_start = t
                if li.start is None:
                    li.start = t
            elif ev == "robot_say_end" and say_start is not None:
                li.robot_speech.append((say_start, t))
                say_start = None
            elif ev == "decision":
                act = [float(x) for x in re.findall(r"-?\d+\.?\d*", d.split("=", 1)[1])] if "=" in d else []
                li.decisions.append((t, int(e["seat"]) - 1, act))
            elif ev == "listen_end":
                kv = _kv(d)
                li.listen_ends.append((kv.get("reason", "?"), float(kv.get("waited_s", 0)), float(kv.get("speech_s", 0))))
            elif ev == "session_end":
                li.completed = True
                li.end = t
    if li.end is None:
        li.end = last
    return li


def audio_offset(attempt: Attempt) -> Optional[float]:
    """offset column if given, else offset_s from <audio>.json (exact, written while recording)."""
    if attempt.offset is not None:
        return attempt.offset
    if attempt.audio:
        meta = Path(attempt.audio).with_suffix(".json")
        if meta.exists():
            v = json.loads(meta.read_text()).get("offset_s")
            return None if v is None else float(v)
    return None


# ----------------------------------------------------------------------------- labels
def read_labels(path: str, offset: float = 0.0) -> List[Label]:
    """Label CSV start_s,end_s,seat (seat 1-based, from audacity_labels_to_csv.py) -> session clock."""
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            seat = (r.get("seat") or "").strip()
            if seat not in ("1", "2", "3"):
                continue
            a, b = float(r["start_s"]) + offset, float(r["end_s"]) + offset
            if b > a:
                out.append((a, b, int(seat) - 1))
    return sorted(out)


def clip(labels: Sequence[Label], start: Optional[float], end: Optional[float]) -> List[Label]:
    lo = -float("inf") if start is None else start
    hi = float("inf") if end is None else end
    return [(max(a, lo), min(b, hi), s) for a, b, s in labels if min(b, hi) > max(a, lo)]


def speaking_time(labels: Sequence[Label], kind: str = "all") -> List[float]:
    """Seconds per seat. kind: all | turns (stretches >= 1 s) | backchannels (< 1 s)."""
    out = [0.0] * N_SEATS
    for a, b, s in labels:
        d = b - a
        if kind == "all" or (kind == "turns" and d >= BACKCHANNEL_MAX_S) or (kind == "backchannels" and d < BACKCHANNEL_MAX_S):
            out[s] += d
    return out


def speakers_at(labels: Sequence[Label], t: float) -> set:
    return {s for a, b, s in labels if a <= t < b}


# ----------------------------------------------------------------------------- ticks
def tick_rows(path: str) -> List[dict]:
    """Tick log rows with a duration `dt` (time to the next tick, capped like the live listener)."""
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for i, r in enumerate(rows):
        r["t"] = float(r["t"])
    for i, r in enumerate(rows):
        nxt = rows[i + 1]["t"] if i + 1 < len(rows) else r["t"] + 0.1
        r["dt"] = min(max(nxt - r["t"], 0.0), TICK_CAP_S)
    return rows


# ----------------------------------------------------------------------------- measures
def gini(values: Sequence[float]) -> float:
    """0 = everyone equal, 1 = one person has everything."""
    v = sorted(max(x, 0.0) for x in values)
    n, total = len(v), sum(v)
    if n == 0 or total == 0:
        return 0.0
    return sum((2 * (i + 1) - n - 1) * x for i, x in enumerate(v)) / (n * total)


def micbot_unevenness(values: Sequence[float]) -> float:
    """Micbot's evenness measure: sum over people of |share - mean share|, in % points (0 = even)."""
    total = sum(values)
    if total == 0:
        return 0.0
    shares = [100.0 * v / total for v in values]
    m = sum(shares) / len(shares)
    return sum(abs(s - m) for s in shares)


def find_params_for_seats(seats: Sequence[float], repo: Path) -> str:
    """The detection_params*.json whose seats*.json matches the seats in the log (room calibration)."""
    for sf in sorted(repo.glob("seats*.json")):
        try:
            got = json.loads(sf.read_text())["seat_azimuths_deg"]
        except Exception:  # noqa: BLE001
            continue
        if len(got) == len(seats) and all(abs(a - b) < 0.05 for a, b in zip(got, seats)):
            pf = repo / sf.name.replace("seats", "detection_params", 1)
            return str(pf) if pf.exists() else ""
    return ""
