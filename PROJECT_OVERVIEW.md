# Participation-Balancing Robot (Reachy Mini): Project Overview

---

## 1. The project

A Reachy Mini sits in front of **three participants**, one of whom self-reports being usually
quiet in groups. It runs a **fixed script**:

1. Intro and a warm-up question, both to everyone.
2. **Six addressed questions.** For each, the robot turns to one person, says their participant number, and asks.
3. After each question it listens until the group goes quiet.
4. Outro.

The **only** thing that differs between conditions is **whom the robot addresses**:

| Condition | CLI | Policy | Uses sensing to decide? |
|---|---|---|---|
| random | `--condition baseline` | *balanced random*: shuffled round-robin, each person addressed exactly 2 of 6 times | No (detection still runs and is logged) |
| balancing | `--condition adaptive` | address the **least active** person (lowest decayed speaking-turn score) | Yes |

Course option: **Computational Focus**. The contribution is the pipeline that decides who is quiet:
- who is speaking (a head-aware HMM);
- how active each person is (speaking turns only, recency-weighted);
- whom to address.

It is evaluated at two levels:

| Level | Question | Baseline | Data |
|---|---|---|---|
| **Computational** (H2, H3) | Does our pipeline detect speakers and pick the truly quiet person better? | **Micbot-style**: nearest seat per reading + cumulative time + "least cumulative" OR random round robin | recorded robot data replayed offline |
| **Behavioural** (H1) | Does the robot's choice make participation more even? | **random** (balanced) addressing | participant study, annotated room audio |

**Hypotheses.**
- **H0**: no difference in Gini (balancing − random) across the 7 groups.
- **H1**: balancing gives a lower Gini coefficient of speaking time.
- **H2**: speaker attribution is correct for ≥ 80 % of annotated speech time.
- **H3** (add to report): on the same recordings, our method beats the Micbot-style method.
  - (a) It assigns more speech to the correct seat.
  - (b) It picks the truly least active person more often.

**Design.**
- Within-subjects, 7 groups × 3 = 21 participants, two rounds per group.
- G01–G04 are order A (random first); G05–G07 are order B (balancing first).
- Topic alternates with group (`SESSION_PROTOCOL.md`, schedule).
  - Topic 1: working and studying.
  - Topic 2: travel.
  - 1 warm-up + 6 questions each, all addressed questions start "What do you think: …" (`prompts/script.json`).
- The quiet participant sits in seat 1, 2 or 3, rotating across groups.

---

## 2. Runtime flow

```
run_session.py   (CLI; builds everything; logs study info, versions, gesture settings)
 ├─ Config, seats.json, detection_params.json
 ├─ Policy    = make_policy(condition)                       policies.py
 ├─ Robot     = Robot(target, animate) + Speaker(prompts)    robot_io.py, speech.py, animation.py
 ├─ Recorder  = AudioRecorder (--record)                     recorder.py
 ├─ Source    = RobotDoASource (/api/state/doa, 10 Hz)       sources.py
 ├─ Listener  = ParticipationListener(HMM, TurnDecay)        listener.py → attribution.py, estimator.py
 ├─ SessionLog (events) + TickLog (10 rows/s)                logger.py, ticklog.py
 └─ run_session(...)                                          session.py
      [recording starts → "I'm in seat k" introductions → Enter]
      face group; intro; warm-up                     (say/turn block: no ticks meanwhile)
      repeat 6×:
          wait_for_silence()     every 0.1 s: source.read() → listener.update() → ticklog
          seat = policy.choose(listener.activity(), history)   ← ONLY CONDITION-DEPENDENT STEP
          turn_to(seat); say("Participant k."); say(question)
      wait_for_silence(); face group; outro
```

`wait_for_silence` uses the raw speech flag, identically in both conditions:

| Reason | Trigger |
|---|---|
| `silence` | 3 s with no speech flag after someone spoke |
| `no_response` | nobody spoke for 10 s |
| `no_data` | as `no_response`, but no readings arrived |
| `max_listen` | 60 s cap |

Round length varies (up to 7 × 60 s of listening plus robot speech).

---

## 3. Conventions

| Quantity | Convention |
|---|---|
| Seat index | 0-based in code, **1-based** in logs, CLI, labels, printouts; seat k = participant k |
| Room azimuth | degrees, 0 = robot's neutral forward, **+ = robot's left** |
| Mic angle | radians, **head frame**: 0 = head's left, π/2 = front, π = right; head deg = 90 − deg(angle) |
| Clock | `time.monotonic()` everywhere: tick `t`, event `mono_s`, audio `offset_s` |
| Robot speaking | playback + 0.5 s echo margin; readings ignored |
| Tick rate | 10 Hz |

**Front/back mirroring.**
- When the robot faces a side seat, the opposite side seat is reported mirrored: at 67° in the main room, 77° in G01's room.
- The naive nearest-seat rule then gives that seat's speech to the **middle seat** (or to nobody in G01, facing seat 3).
- The HMM models the mirroring. In that pose its two candidates are 12.6° apart (σ 6.0°) in the main room and 24.9° apart (σ 10.3°) in G01's room.
- Full table: implementation notes section 2.3.

---

## 4. Detection pipeline (the computational contribution)

| Stage | Ours | Micbot-style baseline (offline only) |
|---|---|---|
| Who speaks (`attribution.py`) | `HMMAttributor`: forward filter over {silence, seats}; emission uses the mirroring-aware expected angle for the current head yaw | `NearestSeatAttributor`: room angle → nearest seat within 25° |
| How active (`estimator.py`) | `TurnDecayEstimator`: utterances (0.6 s merge), backchannels < 1 s excluded, half-life 120 s | `CumulativeEstimator` |
| Whom (`policies.py`) | `LeastActivePolicy`: within 0.5 s of the minimum, then addressed longest ago | `MicbotPolicy` |

**HMM parameters.**
- Transitions: stay speaking 0.95, stay silent 0.90.
- Output: a seat only if its belief ≥ 0.55.
- While the robot speaks, the filter runs the predict step only.

Equations and rationale: implementation notes section 2.4.

### 4.5 Calibration (frozen per room)

Data were collected in **two rooms**, each with its own calibration from `run_calibration.py` + `evaluate_offline.py fit`. Chairs were placed at the calibrated angles and checked with `check_turns.py`.

| Group(s) | Files | Recording | Seats (1, 2, 3) | σ | outlier | miss | false alarm |
|---|---|---|---|---|---|---|---|
| G01 | `seats_g1.json`, `detection_params_g1.json` | `CALIB_calibration_20261110_151627` | +54.6°, +2.5°, −48.4° | 10.28° | 0.077 | 0.671 | 0.348 |
| G02–G07 | `seats.json`, `detection_params.json` | `CALIB_calibration_20261112_133633` | +55.5°, −3.1°, −57.5° | 6.0° | 0.054 | 0.340 | 0.362 |

- **Defaults that applied in both rooms:** half-life 120 s and tie margin 0.5 s, the code defaults; neither params file sets them.
- **Speech-flag false-alarm rate is high in both rooms** (0.35–0.36, above the protocol's 0.15 check). Part of it is a fit artefact: trimmed edges and settle time count as "silence".
- **Calibration is good enough, not exact.** Human-study details (chair placement, posture, acoustics) cannot be fully controlled, so it may sometimes be a little off. The results are assumed valid; state this as a limitation in the report.
- **Pre-study simulation per room** (simple group model, illustration only):

| Room | Share of speech correctly attributed, HMM / nearest seat | Picks the truly least active, ours / Micbot-style / round-robin |
|---|---|---|
| G02–G07 | 0.89 / 0.53 | 0.83–0.89 / 0.49–0.59 / 0.36–0.38 |
| G01 | 0.81 / 0.28 | 0.76–0.86 / 0.54–0.64 / 0.36–0.40 |

---

## 5. File map

**CORE** = used in the study · **EVAL** = analysis/calibration · **DEV** = development.
**[TBD]** = test, run or analysis file still being updated; its description will be revised.

| File | Purpose | Status |
|---|---|---|
| `facilitator/session.py` | Fixed script + `wait_for_silence`; says "Participant k." (`addr_k`) then the question; each prompt logged | CORE |
| `facilitator/config.py` | Timings, prompts, `address_prompts`, `body_share = 1.0`, `animate = True`, baseline type | CORE |
| `facilitator/robot_io.py` | SDK connection (Wireless via IPv4 lookup), turns, gestures during speech, reconnect/recover wrapper, never-raising `close()` | CORE |
| `facilitator/animation.py` | Deterministic talking gestures (head roll/pitch, antennas) while speaking; never changes yaw; returns to listening pose | CORE |
| `facilitator/speech.py` | Uploads committed `prompts/*.wav` to the robot and plays them; `start()`/`wait()` so gestures run during playback; 0.5 s echo margin; SHA-1 audio fingerprint | CORE |
| `facilitator/tts.py` | Piper `en_US-lessac-medium` (study voice; length 1.0, noise 0.8, noise-w 0.95; models in `voices/`, not committed) or system voices for tests | CORE |
| `prompts/script.json` + `prompts/*.wav` | intro, outro, `addr_1..3`, 2 topics × (warm-up + 6 questions) | CORE |
| `make_prompts.py` | Generates the wavs + `manifest.json` | [TBD] |
| `facilitator/recorder.py` | Room audio (16 kHz mono) on a background thread, crash-safe header, `_audio.json` with `offset_s` | CORE |
| `facilitator/logger.py` | Event CSV incl. `mono_s` | CORE |
| `facilitator/ticklog.py` | Per-tick CSV with raw readings | CORE + EVAL |
| `facilitator/sources.py` | `RobotDoASource` (study); `NullSource`, `LaptopMicSource`, `KeyboardSource` (dev) | CORE |
| `facilitator/listener.py` | The hook: `ParticipationListener` | CORE |
| `facilitator/attribution.py` | Geometry, mirroring, `NearestSeatAttributor`, `HMMAttributor` | CORE |
| `facilitator/estimator.py` | `CumulativeEstimator`, `TurnDecayEstimator` | CORE |
| `facilitator/policies.py` | `RoundRobinPolicy`, `UniformRandomPolicy`, `LeastActivePolicy`, `MicbotPolicy` | CORE |
| `facilitator/detection_config.py` | Detection parameters + `detection_params.json` override | CORE |
| `facilitator/seats.py` | Seat angles / `seats.json` | CORE |
| `facilitator/tracker.py` | Times addressed per seat | CORE |
| `facilitator/sim_sources.py` | `MicModel`, `ScriptedSource`; `iter_ticks`, `ReplaySource`, `load_labels`, `truth_at`, `is_overlap` | DEV + EVAL |
| `facilitator/simulation.py` | Simulated groups, `METHODS`, `gini()` | EVAL |
| `seats.json`, `detection_params.json` | Frozen calibration for G02–G07 (§4.5) | CORE |
| `seats_g1.json`, `detection_params_g1.json` | Frozen calibration for G01 (other room) | CORE |
| `run_session.py` | One study round (`--record`, `--record-dir`, `--no-animate`, `--no-pause`) | [TBD] |
| `run_calibration.py` | Calibration recording with automatic labels | [TBD] |
| `check_setup.py` | Python/SDK versions, daemon reachable + same version, microphone direction available | [TBD] |
| `check_turns.py` | Turns to each seat; prints commanded vs reached head and body yaw (`/api/state/full`) | [TBD] |
| `check_recording.py` | 5 s test recording; flags silent (peak < 0.02) or clipping (> 0.98) | [TBD] |
| `setup.sh` | Creates `.venv` and installs | [TBD] |
| `sim_scenario.py` | Demo of a short session with simulated people | [TBD] |
| `audacity_labels_to_csv.py` | Audacity label export → `start_s,end_s,seat` CSV | [TBD] |
| `evaluate_offline.py` | `sim`, `tune`, `fit`, `offset`, `replay`, `study` (H2/H3) | [TBD] |
| `analyze_study.py` | H1/H0, H2, secondary measures, fairness | [TBD] |
| `templates/*.csv` | Formats for `study_sessions.csv`, labels, questionnaire | [TBD] |
| `tests/` | Unit and pipeline tests | [TBD] |
| `SESSION_PROTOCOL.md` | Step-by-step session guide used for data collection | doc |

---

## 6. Data

Each **attempt** (one run of `run_session.py`) writes four files:

| File | Contents |
|---|---|
| `<group>_R<r>_T<t>_<condition>_<time>.csv` | event log: `time_iso, t_s, mono_s, group, condition, event, seat, detail`; events `study_info`, `versions`, `animation`, `recording_start`, `participants_introduced`, `detection_setup`, `session_start`, `robot_say_start/end`, `listen_start/end`, `decision`, `robot_turn`, `session_end`, `recording_end` |
| `..._ticks.csv` | `t, angle_rad, speech, head_yaw_deg, robot_speaking, world_az_deg, seat, confidence, activity` |
| `..._audio.wav` | room audio, 16 kHz mono |
| `..._audio.json` | `offset_s` (tick time = `offset_s` + WAV time), peak, problems |

- **Labels.** Made in Audacity per WAV: every speech stretch ≥ 0.3 s, overlaps labelled for both people, no `kind` column. Converted by `audacity_labels_to_csv.py` [TBD].
- **Re-runs.** A crashed round was re-run with the same command.
  - Each attempt restarts the script and resets the robot's estimate.
  - The random order is identical on re-runs (seed = crc32 of group and round).
  - Attempts on the same laptop without a reboot share the monotonic clock.
  - How attempts are stitched or excluded: [TBD].
- **Not in the event log.** Connection losses are only printed: `run_session.py` does not set `robot.on_event`

---

## 7. Team split and the hook

- **Session / robot / study:** `session.py`, `robot_io.py`, `animation.py`, `speech.py`, `recorder.py`, prompts, run and check scripts, data collection.
- **Detection / evaluation:** `listener.py`, `attribution.py`, `estimator.py`, `policies.py`, `detection_config.py`, `seats.py`, `sim_sources.py`, `simulation.py`, calibration fit, analysis.

| Hook | Contract |
|---|---|
| `ParticipationListener.from_config(seats, det)` | runs in both conditions |
| `listener.update(reading, now, robot_speaking, head_yaw_deg)` every 0.1 s | monotonic `now`; yaw in room frame, + left |
| `listener.activity()` before each decision | one score per seat, lower = quieter |
| `policy.choose(activity, history)` | returns 0-based seat |

---

## 8. Known limitations

**General:** Real-world details (chair placement, posture, voices, acoustics) are not fully controlled, so the calibration may sometimes be slightly off. It is treated as good enough for this study; say so in the report. Two rooms were used, with separate calibrations (section 4.5).

1. Mirroring makes the opposite side seat and the middle seat hard to separate when the robot faces a side seat (section 3).
2. The speech flag is weak (section 4.5). The end-of-listening rule may often hit the 60 s cap; check the `listen_end` reasons [TBD].
3. No sensing while the robot speaks or turns (calls block).
4. Head-pose read failure → yaw 0° for that tick (`session._head_yaw_deg`).
5. Connection events are not logged to CSV (section 6).
6. Re-runs reset the robot's memory of the group.
7. n = 7 groups: the smallest one-sided exact Wilcoxon p is 1/128. Report effect sizes and per-group results.
8. The design report section 1.3 currently says "uniformly at random" -> should be "balanced random".

---

## 10. Micbot (Tennent, Shen & Jung, HRI 2019)

**What it was.**
- A peripheral robotic microphone, purely non-verbal.
- A Kinect microphone array fixed behind it tracked who spoke.
- *Encourage* behaviour: every 3 min it turned to whoever had cumulatively spoken least.
- 36 groups of 3: no movement vs engagement vs random movement.

**What it found.**
- Only the evenness of backchannels improved, and only against no movement (p = .004), not against random movement (p = .091).
- No effect on speaking time.
- No tracking accuracy was reported.

**Our use.**
- Its rule is our offline computational baseline (H3).
- Its null result on speaking time is why H1 is an open question.
- Our hardware adds problems Micbot did not have: an array that turns with the head, mirroring, and the robot hearing itself.

---