# Participation-Balancing Robot (Reachy Mini): Project Overview

> **Read this first.** Handoff document for the team (Alyssa: session / robot / study logistics;
> Greta: detection / evaluation) **and for AI coding agents**. It explains what the study is, how
> every file fits together, the conventions the code depends on, what is done, and what is left.
> Status 4 Nov 2026: complete pipeline runs in the simulator and on a virtual clock; all 15 tests
> pass; **not yet run on the physical robot**; seat angles and microphone parameters are placeholders.

---

## 1. The project

A Reachy Mini robot sits in front of **three participants**, one of whom self-reports being
usually quiet in groups. The robot runs a **fixed discussion script**:

1. Intro, to everyone.
2. A warm-up question, to everyone.
3. **Six questions**, each addressed to one person: the robot turns head and body to them and asks.
   After each question the robot listens until the group goes quiet.
4. Outro.

The **only** thing that differs between conditions is **whom the robot addresses**.

| Condition | Policy | Uses sensing to decide? |
|---|---|---|
| `baseline` | *balanced random*: shuffled round-robin, so everyone is addressed exactly 2 of 6 times in a random order | No. Detection still runs and is logged. |
| `adaptive` | address the **least active** person: lowest decayed speaking-turn score | Yes |

Course option: **Computational Focus**. "Improve some aspect of robot decision-making and evaluate
it against an appropriate baseline." Our computational contribution is the pipeline that decides
who is quiet:
- who is speaking now (an HMM attribution that knows the head pose);
- how active each person is (speaking turns only, recency-weighted);
- whom to address.

It is evaluated at two levels:

| Level | Question | Baseline | Data |
|---|---|---|---|
| **Computational** (H2, H3) | Does our pipeline detect speakers and pick the truly quiet person better? | **Micbot-style method**: nearest seat per reading + cumulative speaking time + "least cumulative" | Recorded robot data, replayed offline; simulation |
| **Behavioural** (H1) | Does the robot's choice make participation more even? | **Random** (balanced) addressing | Participant study, 7 groups, annotated video |

### Research question (design report)
Can a Reachy Mini that tracks each person's speaking time and turns toward the least active
participant make participation in a small group discussion more even than one that addresses
participants at random?

### Hypotheses
- **H0**: the policy makes no difference. Median paired difference in Gini (balancing − random) across the 7 groups = 0.
- **H1**: balancing gives a lower Gini coefficient of speaking time per group (from annotated video).
- **H2**: the seat-assignment method identifies the current speaker correctly for ≥ 80 % of annotated speech time.
- **H3 (to add to the report)**: on the same recordings, our method beats the Micbot-style method.
  - **(a)** It assigns more annotated speech to the right seat.
  - **(b)** Its decisions pick the truly least active participant more often.

### Design
- Within-subjects: 7 groups × 3 = 21 participants, two rounds per group.
- Each round is ~8 min with 6 addressed questions; a questionnaire follows each round.
- Order A (4 groups): R1 random (topic 1), R2 balancing (topic 2).
- Order B (3 groups): R1 balancing (topic 1), R2 random (topic 2).
- Topic is tied to round: a stated limitation.

---

## 2. Runtime flow

```
run_session.py   (CLI; builds everything, logs versions + study info)
 ├─ Config, seats (seats.json | placeholders), DetectionConfig (detection_params.json | defaults)
 ├─ Policy    = make_policy(condition)                       policies.py
 ├─ Robot     = Robot(target) + Speaker(prompts/*.wav)       robot_io.py, speech.py
 ├─ Source    = make_source(--source)                        sources.py / sim_sources.py
 ├─ Listener  = ParticipationListener(attributor, estimator) listener.py → attribution.py, estimator.py
 ├─ SessionLog (events) + TickLog (10 rows/s)                logger.py, ticklog.py
 └─ run_session(...)                                          session.py
      face_group; say(intro)  ← VIDEO SYNC POINT; say(warm-up)     (say/turn block: no ticks meanwhile)
      repeat 6×:
          wait_for_silence()            every 0.1 s: source.read() → listener.update() → ticklog
          activity = listener.activity()            one score per seat, lower = quieter
          seat = policy.choose(activity, history)   ← THE ONLY CONDITION-DEPENDENT STEP
          turn_to(seat); say(question)
      wait_for_silence(); face_group; say(outro)
```

`wait_for_silence` ends with one of four reasons. The rule uses the raw speech flag, identically in
both conditions.

| Reason | When |
|---|---|
| `silence` | someone spoke, then nobody spoke for `silence_s` = 3 s |
| `no_response` | nobody spoke for `no_response_s` = 10 s |
| `no_data` | as `no_response`, but the source never returned a reading |
| `max_listen` | `max_listen_s` = 60 s reached |

---

## 3. Conventions (the code silently depends on these)

| Quantity | Convention |
|---|---|
| Seat index | **0-based in code**, **1-based** in logs, CLI, labels and printouts |
| Room azimuth (seats, head yaw) | degrees; 0 = robot's neutral forward, **+ = robot's LEFT** |
| Mic angle `Reading.angle_rad` | radians, **head frame**: 0 = head's left, π/2 = front, π = right |
| Head-frame degrees | `90 − deg(angle_rad)`: +90 left … −90 right |
| Detection clock | `time.monotonic()`: tick `t`, listener `now`, and **`mono_s` in the event log** |
| Robot speaking | `Speaker.is_speaking()` = playback + `ECHO_MARGIN_S` (0.5 s), monotonic |
| Tick rate | 10 Hz |

**Front/back mirroring.** The array resolves only left/right. A source behind it is reported
mirrored, so head-frame 100° is reported as 80°.
- With the placeholder seats (±50°) the mirrored angle is only 20° off. The naive nearest-seat
  rule still mostly copes, so at ±50° the HMM's advantage comes mainly from **smoothing and outlier
  handling**.
- With wider seats (e.g. ±70°) mirroring alone breaks the nearest-seat rule
  (`tests/test_detection.py::test_mirroring_matters_for_wide_seats`).
- Report this honestly. It depends on the calibrated chair angles.

**The microphones turn with the head.** World direction = head-frame direction + head yaw.
Micbot's Kinect array was fixed behind the robot; ours moves.

---

## 4. Detection pipeline (the computational contribution)

```
Reading ─► Attributor.assign() ─► seat|None ─► Estimator.update() ─► scores() ─► Policy.choose()
```

| Stage | Ours | Micbot-style baseline |
|---|---|---|
| Who is speaking (`attribution.py`) | `HMMAttributor` (see below) | `NearestSeatAttributor`: each reading independently; world angle → nearest seat within 25° |
| How active (`estimator.py`) | `TurnDecayEstimator` (see below) | `CumulativeEstimator`: total attributed seconds since the start |
| Whom to address (`policies.py`) | `LeastActivePolicy` (see below) | `MicbotPolicy`: minimum cumulative (offline only) |

**`HMMAttributor`**: an online HMM forward filter over {silence, seat 1..3}.
- **Emission:** the expected head-frame angle per seat for the current head yaw, *including mirroring*. A Gaussian (`angle_sigma_deg`) is mixed with outliers (`outlier_rate`), plus VAD miss and false-alarm rates.
- **Transitions:** speakers persist, with `stay_speaking` 0.95 and `stay_silent` 0.90 per tick.
- **Output:** a seat only if its belief is ≥ `min_confidence` (0.55).
- **While the robot speaks:** predict only, output None.

**`TurnDecayEstimator`**:
- Utterances are merged across gaps shorter than `merge_gap_s` = 0.6 s.
- Utterances under `min_turn_s` = 1 s are **backchannels**: counted, but not scored.
- Finished turns decay with half-life `half_life_s` = 120 s (τ = 120 / ln 2 ≈ 173 s). Use one term consistently in the report.
- A long utterance in progress already counts.

**`LeastActivePolicy`**:
- Candidates are the seats within `margin_s` = 0.5 of the lowest score.
- Ties go to whoever was addressed longest ago, then lowest score, then lowest seat.
- `repeat_margin_s` and `max_consecutive` are optional social safeguards, OFF by default (they lowered the hit rate in simulation).

`ParticipationListener` (`listener.py`) glues these together:
- It computes `dt` (capped at 0.5 s) and returns a `Tick`.
- It keeps 120 s of ticks for the optional `add_transcript`. There is no speech-to-text; words are logged only.

**Parameters** live in `detection_config.py`. `detection_params.json` overrides them: `fit` writes the
four mic values, and the tuned `half_life_s`/`margin_s` are written by hand after `tune`.
**Seat angles** come from `seats.py` placeholders `[50, 0, −50]`, overridden by `seats.json`.
Both JSON files are **frozen before the first participant group.**

**Simulation results** (placeholder mic model, `evaluate_offline.py sim`, 40 sessions):

| Measure | HMM (ours) | nearest (Micbot-style) |
|---|---|---|
| Speech-time accuracy | 0.95 | 0.73 |

| Picks the truly least active | ours | Micbot-style | round-robin |
|---|---|---|---|
| Hit rate | 0.87–0.91 | 0.67–0.76 | 0.34–0.40 |

These are a sanity check, not evidence: the group model is simple.

---

## 5. File map

**CORE** = needed in the study · **EVAL** = needed for calibration/analysis · **DEV** = development only.

| File | Purpose | Status |
|---|---|---|
| `run_session.py` | CLI for one study round; picks source and speech output; logs study info, code version and prompt-audio hash | CORE |
| `run_calibration.py` | Records the calibration session on the real robot and **writes the labels itself** | CORE (before study) |
| `facilitator/session.py` | The fixed script + `wait_for_silence` (hooks 0–2); takes `clock`/`sleep` | CORE |
| `facilitator/config.py` | Timings, prompts per topic, motion, baseline type, seed | CORE |
| `facilitator/robot_io.py` | Reachy Mini SDK: connect, `turn_to`, `face_group`, `say`, `is_speaking`, `head_yaw_deg` | CORE |
| `facilitator/speech.py` | Plays `prompts/<id>.wav` on the robot or laptop; echo margin; audio fingerprint; no auto-TTS on real robot | CORE |
| `facilitator/tts.py` | Text → wav: Piper neural voice (study), or macOS `say` / Windows pyttsx3 / Linux espeak-ng; used by `make_prompts.py` | CORE (prompt prep) |
| `facilitator/animation.py` | Talking gestures (head sway, antennas) while the robot speaks; same in both conditions; `--no-animate` turns off | CORE |
| `make_prompts.py`, `prompts/script.json` | Prompt texts → wavs + `manifest.json` (wavs must be committed) | CORE |
| `facilitator/logger.py` | Event CSV incl. `mono_s` (same clock as ticks) | CORE |
| `facilitator/ticklog.py` | Per-tick CSV with raw readings → offline replay | CORE + EVAL |
| `facilitator/sources.py` | `RobotDoASource` (study), `NullSource`; `LaptopMicSource`, `KeyboardSource` | CORE (+DEV classes) |
| `facilitator/listener.py` | The hook (`ParticipationListener`, `Tick`) | CORE |
| `facilitator/attribution.py` | Geometry, `NearestSeatAttributor`, `HMMAttributor` | CORE |
| `facilitator/estimator.py` | `CumulativeEstimator`, `TurnDecayEstimator` | CORE |
| `facilitator/policies.py` | `RoundRobinPolicy`, `UniformRandomPolicy`, `LeastActivePolicy`, `MicbotPolicy` | CORE |
| `facilitator/detection_config.py` | Detection/policy parameters + JSON override | CORE |
| `facilitator/seats.py` | Seat angles: placeholder / `seats.json` | CORE |
| `facilitator/tracker.py` | What the robot did: `times_addressed`, last activity | CORE |
| `facilitator/sim_sources.py` | `MicModel`, `ScriptedSource` (DEV); `iter_ticks`, `ReplaySource`, `load_labels`, `truth_at`, `is_overlap` (EVAL) | DEV + EVAL |
| `facilitator/simulation.py` | Simulated groups, `METHODS`, `gini()` | EVAL |
| `evaluate_offline.py` | `sim`, `tune`, `fit`, `offset`, `replay`, `study` (H2 + H3) | EVAL |
| `analyze_study.py` | H1/H0, H2, Micbot unevenness, turn-only Gini, quiet share, robot behaviour, fairness | EVAL |
| `sim_scenario.py` | Single-file demo of a short session with simulated people (`--no-robot --fast` or the MuJoCo sim); in real time the robot and each person speak with computer voices (`--mute` = text only) | DEV |
| `templates/*.csv` | Formats for `study_sessions.csv`, labels, questionnaire | EVAL |
| `tests/` | `test_detection.py`, `test_study.py`, `test_pipeline.py` (calibration → fit → rounds → offset → analysis) | DEV |
| `requirements.txt` | Includes `sounddevice` (needed by `--source laptop`; was missing) | — |

**Deleted:**
- `demo_conversation.py`, `facilitator/demo_group.py` and `tests/test_demo_group.py`. They are replaced by `sim_scenario.py`, and nothing in the study imported them.
- The unused prompts `invite` and `question_1`.

`run_sim.py` (starts the MuJoCo simulator), `DETECTION.md` and `STUDY_ALIGNMENT.md` were not reviewed; keep `run_sim.py`. This document supersedes the two .md files: delete them,
or check them for contradictions.

**`facilitator/__init__.py`** must exist (it may be empty).

---

## 6. Data files

**Event log** `logs/<group>_R<round>_T<topic>_<condition>_<stamp>.csv`
- Columns: `time_iso, t_s, mono_s, group, condition, event, seat, detail`.
- Events:
  - `study_info` (group, round, topic, order, condition, quiet seat, baseline, seed)
  - `detection_setup`, `versions` (git commit, prompt-audio hash)
  - `session_start`, `robot_say_start/end`, `listen_start`, `listen_end` (reason, waited_s, speech_s)
  - `decision` (seat, activity), `robot_turn`, `session_end` (times addressed)

**Tick log** `…_ticks.csv`
- Written at 10 Hz while listening, plus the 0.5 s echo margin. No rows while a prompt plays or the robot turns.
- Columns: `t, angle_rad, speech, head_yaw_deg, robot_speaking, world_az_deg, seat, confidence, activity`.
- The raw columns are enough to re-run any method.

**Labels** `start_s,end_s,seat[,kind]`
- `seat` is 1-based. `kind` is `turn` (the default) or `backchannel`; backchannels are recommended to label, as Micbot did.
- Gaps mean silence. Overlapping speech is allowed: those ticks are excluded from accuracy.
- Times are in **video seconds**; the per-round `offset` maps them to the tick clock.

**Clock sync**
- `offset = mono_s(first robot_say_start) − video time when the intro starts`.
- Compute it with `python evaluate_offline.py offset --log <round log> --video-s <t>`.

**`study_sessions.csv`** (`templates/`): one row per round: `group,order,round,topic,condition,quiet_seat,labels,offset,ticks,log`.

**Calibration:** `seats.json`, `detection_params.json` (commit both).

---

## 7. How to run

```bash
pip install -r requirements.txt
python -m pytest -q tests

# see a short session (no robot needed / or in the MuJoCo simulator)
python sim_scenario.py --no-robot --fast
python sim_scenario.py                       # simulator running in another terminal; with voices
python sim_scenario.py --no-robot            # real time with voices, no simulator

# prompts: once, on one computer, one voice; then commit prompts/*.wav + manifest.json
python make_prompts.py                       # Piper en_US-lessac-medium (pip install piper-tts + download, see requirements.txt)

# simulator sessions
python run_session.py --condition adaptive --source scripted    # simulated mic array
python run_session.py --condition adaptive --source keyboard    # press 1/2/3

# real robot: calibration, then study rounds
python run_calibration.py --target lite
python evaluate_offline.py fit --ticks logs/CALIB_..._ticks.csv --labels logs/CALIB_..._labels.csv --dry-run
python run_session.py --target lite --group G01 --round 1 --topic 1 --order A --condition baseline --quiet-seat 2

# before the study: tuning; after the study: analysis
python evaluate_offline.py sim --sessions 100
python evaluate_offline.py tune
python evaluate_offline.py offset --log logs/G01_R1_..._baseline_....csv --video-s 12.4
python analyze_study.py study_sessions.csv --questionnaire questionnaire.csv --out results/study.csv
python evaluate_offline.py study study_sessions.csv --out results/h3.csv
```

---

## 8. Team split and the hook

**Alyssa: session / robot / study.**
- Code: `session.py`, `robot_io.py`, `speech.py`, `tts.py`, prompts, `run_session.py`, `run_calibration.py`.
- Physical-robot checks, room, video, questionnaires, running groups.

**Greta: detection / evaluation.**
- Code: `listener.py`, `attribution.py`, `estimator.py`, `policies.py`, `detection_config.py`, `seats.py`, `sim_sources.py`, `simulation.py`, `evaluate_offline.py`, `analyze_study.py`.
- Calibration fit, tuning, analysis.

The interface between them. **Change it only together.**

| Hook | Session side calls | Detection side implements | Contract |
|---|---|---|---|
| 0 | `ParticipationListener.from_config(seats, det)` | listener factory | runs in **both** conditions |
| 1 | `listener.update(reading, now, robot_speaking, head_yaw_deg)` every 0.1 s | returns `Tick` | `now` monotonic; `head_yaw_deg` room frame, + left; `robot_speaking = robot.is_speaking()` |
| 2 | `listener.activity()` before each decision | one score per seat | lower = quieter |
| decision | `policy.choose(activity, history)` | policies | returns 0-based seat |
| files | session writes event + tick logs (`mono_s` = tick `t`) | detection reads them; writes `seats.json`, `detection_params.json` | formats in §6 |
| optional | `listener.add_transcript(TranscriptSegment)` | logged only | monotonic times |

---

## 9. Decisions and known limitations

1. **Baseline = balanced random.** The code default is `balanced`. The report currently says "uniformly at random" and must be changed (§11). Reason: uniform random leaves someone never addressed in ~26 % of rounds, which confounds robot attention with the policy.
2. **Gini on all speech**, as the report states. Turn-only Gini and Micbot's unevenness measure are secondary.
3. **No ticks while the robot speaks or turns.** `say()` and `goto_target` block. This is harmless for decisions; use event-log times for the robot's speech.
4. **Laptop microphone** (`--source laptop`) has no direction. All speech is credited to the seat being faced, so use `scripted` or `keyboard` to test balancing.
5. **The end-of-turn rule** uses the raw speech flag; anyone, or noise, keeps the turn open. It is identical in both conditions.
6. **Power.**
   - With 7 groups the smallest one-sided exact Wilcoxon p is 1/128 ≈ 0.008, so H1 needs a consistent effect in nearly every group.
   - Micbot found **no effect on speaking time** (§10).
   - Report effect sizes, per-group differences and the computational results (H2/H3), not just p.
7. **Still to verify on hardware:**
   - DoA angle convention (0 = left?)
   - sign of `head_yaw_deg()` after `turn_to(+50)`
   - whether `goto_target` blocks for its duration
   - whether motor noise trips `speech_detected`
   - whether the 0.5 s echo margin is enough
   - DoA latency (0.5 s timeout)

   `ALYSSA_TASKS.md` §B has the procedure.

---

## 10. Micbot (Tennent, Shen & Jung, HRI 2019): what it was and how we use it

**The robot.**
- A *peripheral* robotic object: a gutted Blue Yeti microphone with two stepper motors (pan and tilt), driven by an Arduino.
- Speaker tracking came from the **microphone array of a Kinect fixed behind the robot**, logged by a C++ program.

**The behaviours.**
- *Follow*: turn to whoever is speaking, after a 150 ms delay chosen in pilots.
- *Encourage*: every **3 minutes**, turn to the person who had **cumulatively spoken the least**, tilt toward them for 15 s, straighten, wait 15 s, then resume follow.
- Purely non-verbal: it never spoke.

**The study.**
- Between-subjects, 36 groups of 3 (N = 108).
- Three conditions: **no movement / engagement / random movement**. In random movement, the same behaviours went in random directions.
- Tasks: an 8-min Droodle warm-up (not analysed), then the Desert Survival problem.

**Measures.**
- Team score against the expert ranking.
- Video coding of **speaking vs backchanneling utterances** (two coders, ICC .76–.84).
- Evenness = sum over members of |individual − group mean|, for turns and for time-percentages.

**Results.**
- **Only backchannel-turn evenness** differed: engagement was more even than no movement (p = .004), but **not significantly more than random movement** (p = .091).
- Speaking time and speaking turns: **no effect**.
- More even backchannel turns predicted better performance (R² ≈ .12).

**What this means for us.**
1. **We do not replicate Micbot.** Its study answered an HRI question: whether a peripheral robot helps at all. Ours is computational: a better way of deciding whom to address, plus a test of whether that changes participation.
2. **Micbot gives us the baseline *method*.** Its encourage rule (least cumulative speaking, from per-reading array directions) is re-implemented on our hardware as nearest seat + cumulative + `MicbotPolicy`. Micbot never reported how accurate its speaker tracking was. Measuring and improving that accuracy (H2/H3) is the gap we fill.
3. **Our hardware creates problems Micbot did not have.** Our array turns with the head (left/right only, with front/back mirroring) and the robot's own voice reaches it. That motivates the head-aware HMM and the echo handling.
4. **Our manipulation is stronger.** The robot asks the person directly, rather than nudging non-verbally. Micbot's null result on speaking time is the main argument that H1 is a real, open question rather than a given.
5. **Borrowed measures for comparability.** `analyze_study.py` reports Micbot's unevenness measure, and a turn-only Gini when backchannels are labelled.

---

## 11. Report alignment (edits to the design report)

- **§1.3 Conditions:** replace "uniformly at random select who it will talk to" with: "addresses participants in a random order that is balanced, so that each participant is addressed twice in the six questions (shuffled round-robin, seeded per group and round)."
- **§1.1–1.2:** add the computational comparison.
  - Extend the RQ, e.g. "…and does a head-aware, recency-weighted speaker-tracking method identify the least active participant more reliably than a Micbot-style cumulative tracker?"
  - Add **H3** (§1).
- **Table 2:** "Decay time τ" → "half-life of the activity score (120 s), fixed after offline tuning (`evaluate_offline.py tune`)". Also add: seat angles and microphone parameters calibrated once before the study (`run_calibration.py`, `fit`).
- **§1.4 Dependent variables:** add the quiet participant's share of speaking time and the robot-behaviour log (times addressed per seat).
- **§2 Implementation** can follow §2–§4 of this document. **§3 Measures & Analyses** can follow `analyze_study.py`/`evaluate_offline.py study`:
  - paired one-sided Wilcoxon, n = 7 groups, rank-biserial r;
  - H2 against 0.80 per seat;
  - H3a paired Wilcoxon per group;
  - H3b hit rates with an exact McNemar test on discordant decisions;
  - order A/B descriptives for carryover.
- **Table 3:** the "Asymmetric carryover" row needs no change.

---

## 12. Work plan

### Phase 1: before the physical robot
| Task | Owner | Status |
|---|---|---|
| Code fixes in `CHANGES.md` (sync column, keyboard yaw, auto-TTS guard, overlap, calibration, H3, demo) | Greta | **done** |
| Replace placeholder questions; generate + commit wavs with one voice | Alyssa | todo |
| Report edits in §11 | both | todo |
| `evaluate_offline.py tune` → write `half_life_s`, `margin_s` to `detection_params.json` | Greta | todo |
| Run `sim_scenario.py` and `run_session.py --source keyboard/scripted` in the MuJoCo sim | Alyssa | todo |

### Phase 2: on the physical robot, before participants
| Task | Owner |
|---|---|
| Connection, DoA, conventions and timing checks (`ALYSSA_TASKS.md` §B) | Alyssa |
| Mark chairs; `run_calibration.py`; send logs to Greta | Alyssa |
| `fit` → check → commit `seats.json`, `detection_params.json`; `replay` on calibration data | Greta |
| Camera + sync point; consent, questionnaires, run sheet, experimenter script | Alyssa (Greta reviews) |
| Dry run of both conditions with team members; pilot group; check logs and durations | both |
| Freeze: `git tag study-v1`; the `versions` log line must show this commit without `-dirty` | both |

### Phase 3: after data collection
| Task | Owner |
|---|---|
| Annotate videos (`templates/labels_template.csv`), incl. backchannels; second coder on ≥ 3 rounds | both |
| Offsets per round (`evaluate_offline.py offset`); fill `study_sessions.csv` | Alyssa |
| `analyze_study.py` (H1, H2, secondary, fairness) | Greta |
| `evaluate_offline.py study` (H3a/b) + figures | Greta |
| Report: Implementation, Measures & Analyses, results, limitations | both |

---

## 13. Rules for anyone (human or AI) changing this code

- Keep sessions identical across conditions. Only `policy.choose` may differ.
- Do not change the §8 hook, the tick-log columns or the event-log columns without updating `iter_ticks`, `read_events`, `analyze_study.py`, `evaluate_offline.py` and this file.
- Seats are 0-based in code and 1-based in anything human-facing.
- Seed everything random. Real-robot runs use `--source auto` (robot microphones).
- Detection must never crash a session: sources return `None` on errors.
- After calibration and tuning, parameters live only in `seats.json` / `detection_params.json`. No code-default changes during the study.
- Run `python -m pytest -q tests` before every commit.