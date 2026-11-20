# [PROJECT TITLE]

---

## 1. The project

A Reachy Mini sits in front of **three participants**, one of whom self-reports being usually quiet in groups. It runs a **fixed script**:

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

It is evaluated at two levels, each against its own baseline:

| Level | Question | Baseline | Data |
|---|---|---|---|
| **Computational** (H2, H3) | Does our pipeline detect speakers and pick the truly quiet person better? | **Micbot-style**: nearest seat per reading + cumulative time + "least cumulative" | Recorded robot data from all 14 rounds, replayed offline |
| **Behavioural** (H1, fairness) | Does the robot's choice make participation more even? | **Random** (balanced) addressing | Participant study: annotated room audio + questionnaires |

Random is only the live control; it is not part of the H3 comparison. Micbot-style was never run live (section 4).

**Hypotheses.**
- **H0**: no difference in Gini (balancing − random) across the 7 groups.
- **H1**: balancing gives a lower Gini coefficient of speaking time.
- **H2**: speaker attribution is correct for ≥ 80 % of annotated speech time.
- **H3**: on the same recordings, our method beats the Micbot-style method.
  - (a) It assigns more speech to the correct seat.
  - (b) It picks the truly least active person more often.

**Design.**
- Within-subjects, 7 groups × 3 = 21 participants, two rounds per group.
- G01–G04 are order A (random first); G05–G07 are order B (balancing first).
- Topic alternates with round (`SESSION_PROTOCOL.md`, schedule).
  - Topic 1: working and studying.
  - Topic 2: travel.
  - 1 warm-up + 6 questions each; all addressed questions start "What do you think: …" (`prompts/script.json`).
- The quiet participant sits in seat 1, 2 or 3, rotating across groups.

---

## 2. Runtime flow

```
run_session.py   (CLI; builds everything; logs study info, versions, gesture settings)
 ├─ Config, seats(.json/_g1.json), detection_params(.json/_g1.json)
 ├─ Policy    = make_policy(condition)                       policies.py
 ├─ Robot     = Robot(target, animate) + Speaker(prompts)    robot_io.py, speech.py, animation.py
 ├─ Recorder  = AudioRecorder (--record)                     recorder.py
 ├─ Source    = RobotDoASource (/api/state/doa)              sources.py
 ├─ Listener  = ParticipationListener(HMM, TurnDecay)        listener.py → attribution.py, estimator.py
 ├─ SessionLog (events) + TickLog (one row per reading)      logger.py, ticklog.py
 └─ run_session(...)                                          session.py
      [recording starts → "I'm in seat k" introductions → Enter]
      face group; intro; warm-up                     (say/turn block: no readings meanwhile)
      repeat 6×:
          wait_for_silence()     each loop: source.read() → listener.update() → ticklog
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

**In the study, every listening phase ended on `silence`.** Rounds took about 3 min (random 3.1, balancing 3.0), much shorter than the ~8 min planned.

**Running the tests:**

```bash
python -m pytest -q tests       
```

---

## 3. Conventions

| Quantity | Convention |
|---|---|
| Seat index | 0-based in code, **1-based** in logs, CLI, labels, printouts; seat k = participant k |
| Room azimuth | degrees, 0 = robot's neutral forward, **+ = robot's left** |
| Mic angle | radians, **head frame**: 0 = head's left, π/2 = front, π = right; head deg = 90 − deg(angle) |
| Clock | `time.monotonic()` everywhere: tick `t`, event `mono_s`, audio `offset_s` |
| Session time of a WAV sample | `offset_s` + time in the WAV |
| Robot speaking | playback + 0.5 s echo margin; readings ignored |
| Reading rate | polled every 0.1 s; with request latency, one reading every ~0.12 s. Analysis weights each reading by its real duration (capped at 0.5 s). |

**Front/back mirroring.**
- When the robot faces a side seat, the opposite side seat is reported mirrored: at 67° in the main room, 77° in G01's room.
- The naive nearest-seat rule then gives that seat's speech to the **middle seat** (or to nobody in G01, facing seat 3).
- This is common: the robot faced a side seat after 28/42 questions in random rounds and 33/42 in balancing rounds.
- The HMM models the mirroring. In that pose its two candidates are 12.6° apart (σ 6.0°) in the main room and 24.9° apart (σ 10.3°) in G01's room.

---

## 4. Detection pipeline (the computational contribution)

| Stage | Ours | Micbot-style baseline (offline only) |
|---|---|---|
| Who speaks (`attribution.py`) | `HMMAttributor`: forward filter over {silence, seats}; emission uses the mirroring-aware expected angle for the current head yaw | `NearestSeatAttributor`: room angle → nearest seat within 25° |
| How active (`estimator.py`) | `TurnDecayEstimator`: utterances (0.6 s merge), backchannels < 1 s excluded, half-life 120 s | `CumulativeEstimator`: total attributed time since the start |
| Whom (`policies.py`) | `LeastActivePolicy`: within 0.5 s of the minimum, then addressed longest ago | `MicbotPolicy`: lowest total |

**HMM parameters.**
- Transitions: stay speaking 0.95, stay silent 0.90.
- Output: a seat only if its belief ≥ 0.55.
- While the robot speaks, the filter runs the predict step only.

**Offline replay.** Every raw reading, head yaw and robot-speaking flag is in the tick log. So any method can be replayed on exactly the sensor stream the live robot had (`evaluate_offline.py study`, section 7).
- Replaying our HMM reproduced the live attribution on 100 % of readings.
- It also reproduced all 46 live balancing decisions.
- That is why the Micbot comparison is fair without a third live condition.

### 4.1 Calibration (frozen per room)

Data were collected in **two rooms**, each with its own calibration from `run_calibration.py` + `evaluate_offline.py fit`. Chairs were placed at the calibrated angles and checked with `check_turns.py`.

| Group(s) | Files | Recording | Seats (1, 2, 3) | σ | outlier | miss | false alarm |
|---|---|---|---|---|---|---|---|
| G01 | `seats_g1.json`, `detection_params_g1.json` | `CALIB_calibration_20261110_151627` | +54.6°, +2.5°, −48.4° | 10.28° | 0.077 | 0.671 | 0.348 |
| G02–G07 | `seats.json`, `detection_params.json` | `CALIB_calibration_20261112_133633` | +55.5°, −3.1°, −57.5° | 6.0° | 0.054 | 0.340 | 0.362 |

- **Defaults that applied in both rooms:** half-life 120 s and tie margin 0.5 s, the code defaults; neither params file sets them.
- **Speech-flag false-alarm rate is high in both rooms** (0.35–0.36, above the protocol's 0.15 check). Part of it is a fit artefact: trimmed edges and settle time count as "silence".
  - It did not keep listening phases open: all of them ended on silence.
  - It did matter for attribution: together with the HMM's persistence it causes false speech in pauses (section 8).
  - G01's fit has a miss rate (0.671) above 1 − false alarm (0.652). That makes "no speech flag" carry no evidence for silence, so G01 is the worst case.
- **Calibration is good enough, not exact.** Human-study details (chair placement, posture, acoustics) cannot be fully controlled, so it may sometimes be a little off. State this as a limitation in the report.
- **Pre-study simulation per room** (simple group model, illustration only):

| Room | Share of speech correctly attributed, HMM / nearest seat | Picks the truly least active, ours / Micbot-style / round-robin |
|---|---|---|
| G02–G07 | 0.89 / 0.53 | 0.83–0.89 / 0.49–0.59 / 0.36–0.38 |
| G01 | 0.81 / 0.28 | 0.76–0.86 / 0.54–0.64 / 0.36–0.40 |

The real data confirmed the attribution advantage but not the decision advantage (section 8). The simulator did not model false speech in pauses.

---

## 5. File map

**CORE** = used live in the study · **PREP** = setup and checks before or on the day · **ANALYSIS** = after data collection · **DEV** = development and demo.

**Robot session (CORE)**

| File | Purpose |
|---|---|
| `run_session.py` | One study round. `--group --round --order --topic --condition --quiet-seat --target --record --record-dir`; `--no-animate`, `--no-pause` for testing; `--attributor`, `--estimator`, `--baseline` exist but kept their defaults in the study |
| `facilitator/session.py` | Fixed script + `wait_for_silence`; says "Participant k." (`addr_k`) then the question; each prompt logged |
| `facilitator/config.py` | Timings, prompts, `address_prompts`, `body_share = 1.0`, `animate = True`, baseline type |
| `facilitator/robot_io.py` | SDK connection (Wireless via IPv4 lookup), turns, gestures during speech, reconnect/recover wrapper, never-raising `close()` |
| `facilitator/animation.py` | Deterministic talking gestures (head roll/pitch, antennas) while speaking; never changes yaw; returns to the listening pose |
| `facilitator/speech.py` | Uploads committed `prompts/*.wav` to the robot and plays them; `start()`/`wait()` so gestures run during playback; 0.5 s echo margin; SHA-1 audio fingerprint |
| `facilitator/tts.py` | Piper `en_US-lessac-medium` (study voice; length 1.0, noise 0.8, noise-w 0.95; models in `voices/`, not committed), or system voices for tests |
| `prompts/script.json` + `prompts/*.wav` | intro, outro, `addr_1..3`, 2 topics × (warm-up + 6 questions); identical audio in all 20 attempts |
| `facilitator/recorder.py` | Room audio (16 kHz mono) on a background thread, crash-safe header, `_audio.json` with `offset_s` |
| `facilitator/logger.py`, `facilitator/ticklog.py` | Event CSV (with `mono_s`) and one row per reading with raw values (also the input for all offline analysis) |
| `facilitator/sources.py` | `RobotDoASource` (study; failed request = no reading; retry added after G04); `NullSource`, `LaptopMicSource`, `KeyboardSource` (dev) |
| `facilitator/tracker.py` | Times addressed per seat |

**Detection (CORE: the computational contribution)**

| File | Purpose |
|---|---|
| `facilitator/listener.py` | The hook: `ParticipationListener` (section 9) |
| `facilitator/attribution.py` | Geometry, mirroring (`fold`), `NearestSeatAttributor`, `HMMAttributor` |
| `facilitator/estimator.py` | `CumulativeEstimator`, `TurnDecayEstimator` |
| `facilitator/policies.py` | `RoundRobinPolicy` (balanced random, seeded `crc32("<group>-R<round>")`), `UniformRandomPolicy` (not used), `LeastActivePolicy`, `MicbotPolicy` |
| `facilitator/detection_config.py`, `facilitator/seats.py` | Detection parameters and seat angles, overridden from the JSON files |
| `seats.json`, `detection_params.json` | Frozen calibration for G02–G07 (§4.1) |
| `seats_g1.json`, `detection_params_g1.json` | Frozen calibration for G01 (other room) |

**Preparation and checks (PREP)**

| File | Purpose |
|---|---|
| `setup.sh` / `setup.ps1` / `requirements.txt` | Creates `.venv` and installs dependencies (macOS/Linux / Windows) |
| `make_prompts.py` | Generates the prompt wavs + `manifest.json` once; the wavs are committed |
| `check_setup.py` | Python/SDK versions, daemon reachable + same version, microphone direction available |
| `check_turns.py` | Turns to each seat; prints commanded vs reached head and body yaw (`/api/state/full`) |
| `check_recording.py` | 5 s test recording; flags silent (peak < 0.02) or clipping (> 0.98) |
| `run_calibration.py` | ~6 min calibration recording; the schedule writes the labels automatically |
| `evaluate_offline.py fit` | Fits seat angles + microphone model from a calibration recording → the frozen JSON files |

**Analysis (ANALYSIS; workflow in section 7)**

| File | Purpose |
|---|---|
| `facilitator/study_data.py` | Shared loading for all analysis scripts: attempts, rounds, event/tick logs, audio offset, labels (clipped to the intro–outro window), speaking time, Gini, Micbot unevenness, matching params to seats |
| `build_sessions.py` | Scans the data folder, finds every attempt and its four files, reads group/round/condition/quiet seat from the log, numbers attempts, matches each to its room's calibration → `study_sessions.csv` |
| `make_label_templates.py` | Audacity starting track per recording: robot prompts from the log, seat introductions, loud stretches marked "?"; **no robot guess** of who spoke |
| `audacity_labels_to_csv.py` | Audacity export → `start_s,end_s,seat`; warns about any "?" left |
| `check_labels.py` | Label checks: format, duplicates, overlap with robot speech, long overlaps, coverage, H2 with edges shrunk by 0.25 s |
| `analyze_study.py` | Participant study, sections A–H (section 7). `--only-complete` = primary analysis; `--questionnaire`, `--seat-map` add fairness |
| `evaluate_offline.py study` | Offline comparison: replay check, H3a (accuracy, side vs middle, false speech), H3b (three "truly least active" definitions, McNemar) |
| `evaluate_offline.py sim` / `replay` | Pre-study simulation per room; replay of one recording against its labels |
| `seat_map.csv` | `group,seat,participant`: links questionnaire answers to seats |
| `templates/*.csv` | Formats for `study_sessions.csv`, label CSVs and the questionnaire (CSV alternative to the workbook) |

**Development, demo and tests (DEV)**

| File | Purpose |
|---|---|
| `facilitator/sim_sources.py` | `MicModel`, `ScriptedSource`; `iter_ticks`, `ReplaySource`, `load_labels`, `truth_at` |
| `facilitator/simulation.py` | Simulated groups, `METHODS`, `gini()` |
| `run_sim.py` | Starts the Reachy Mini MuJoCo simulator in a light mode (no media, no wake-up animation) |
| `sim_scenario.py` | Short demo session with simulated people in the Reachy Mini simulator (checks the simulator on :8000 first; caches voices) |
| `tests/test_detection.py` | Geometry, mirroring, HMM, estimators, policies |
| `tests/test_estimator.py` | Micbot-style cumulative vs our turn-based decayed estimate |
| `tests/test_policies.py` | Balanced random baseline and the adaptive policy |
| `tests/test_session.py` | A whole session with a fake robot |
| `tests/test_sources.py` | Speech sources (robot direction, laptop mic, keyboard) without hardware |
| `tests/test_speech.py`, `tests/test_animation.py`, `tests/test_recorder.py` | Prompt playback, talking gestures, room recording without sound hardware |
| `tests/test_offline.py` | Tick log → replay → fit, and the simulation comparison |
| `tests/test_pipeline.py` | End-to-end on fake rounds: logs + labels → `build_sessions` → `analyze_study` → `evaluate_offline study` |
| `tests/test_audacity_labels.py` | Label conversion |

---

## 6. Data

Each **attempt** (one run of `run_session.py`) writes four files:

| File | Contents |
|---|---|
| `<group>_R<r>_T<t>_<condition>_<time>.csv` | event log: `time_iso, t_s, mono_s, group, condition, event, seat, detail`; events `study_info`, `versions`, `animation`, `recording_start`, `participants_introduced`, `detection_setup`, `session_start`, `robot_say_start/end`, `listen_start/end`, `decision`, `robot_turn`, `session_end`, `recording_end` |
| `..._ticks.csv` | `t, angle_rad, speech, head_yaw_deg, robot_speaking, world_az_deg, seat, confidence, activity` |
| `..._audio.wav` | room audio, 16 kHz mono |
| `..._audio.json` | `offset_s` (session time = `offset_s` + WAV time), peak, problems |

Plus, per study: `questionnaires.xlsx` (workbook with Participants / Long / Groups / Results / Charts tabs) and `seat_map.csv`.

- **Labels (ground truth).**
  - Made in Audacity on each WAV, starting from the template.
  - Every speech stretch ≥ 0.3 s is labelled with its seat; overlaps are labelled for both people; the robot is not labelled.
  - Converted by `audacity_labels_to_csv.py` to `labels/<stem>.csv`. One annotator labelled all recordings.
  - Labels < 1.0 s count as backchannels in the analysis.
  - Speech is counted from the intro to the end of the outro.
- **Re-runs.** A crashed round was re-run with the same command.
  - Each attempt restarts the script and resets the robot's estimate.
  - The random order is identical on re-runs (seed = crc32 of group and round).
  - 20 attempts for 14 rounds: G02 R1 (3 attempts), G02 R2 (4), G04 R1 (2); G04 R2 crashed after its last question.
  - **Rule:** each round uses the attempt that asked all 6 questions; crashes after the last question count as complete. This is the primary analysis (`--only-complete`, `complete_*` outputs).
  - Sensitivity check: all labelled attempts added up. It gives the same conclusions.
- **Not in the event log.** Connection losses are only printed, because `run_session.py` does not set `robot.on_event`; they are on the paper notes sheets.
- **Privacy.** Participant data (audio, logs, questionnaires) stay out of the repository.

---

## 7. Analysis workflow

The full commands and explanations are in `ANALYSIS_GUIDE.md`. In order:

```bash
python -m pytest -q tests                                    # 1. code check
python build_sessions.py DATA --out DATA/study_sessions.csv  # 2. find attempts, match calibration
python make_label_templates.py DATA/study_sessions.csv       # 3. Audacity templates
#   ... label in Audacity, export ...
python audacity_labels_to_csv.py DATA/labels/<stem>_labels.txt DATA/labels/<stem>.csv
python build_sessions.py DATA --out DATA/study_sessions.csv  # 4. re-run: picks up labels
python check_labels.py DATA/study_sessions.csv               # 5. label checks
python analyze_study.py DATA/study_sessions.csv --only-complete \
    --questionnaire DATA/questionnaires.xlsx --seat-map DATA/seat_map.csv --out DATA/results   # 6. primary
python analyze_study.py DATA/study_sessions.csv --out DATA/results_all_attempts                 #    sensitivity
python evaluate_offline.py study DATA/study_sessions.csv --out DATA/results                     # 7. H3
```

**What `analyze_study.py` reports** (sections in its printout):

| Section | Content |
|---|---|
| A | Attempts used, prompt-audio fingerprint, code version |
| B | Round durations, how listening phases ended |
| C | Manipulation check: times each seat / the quiet member was addressed; whether decisions picked the truly least active |
| D | H1: Gini per round, paired balancing − random, one-sided exact Wilcoxon, rank-biserial r; secondary measures (turns-only Gini, Micbot unevenness, quiet member's share); order A vs B |
| E | H2: live attribution accuracy (overall, per seat, per condition, per room), confusion matrix, false speech |
| F | Mechanism: the addressee's share of the talk after each question |
| G | Validity: robot-estimated vs annotated share (Spearman ρ); robot-estimated Gini |
| H | Fairness: per participant and per group mean, two-sided Wilcoxon, order A vs B |

**Outputs:**
- `complete_rounds.csv`, `complete_groups.csv`, `complete_decisions.csv`, `complete_h2_confusion.csv`;
- figures `complete_fig_gini_pairs.png`, `complete_fig_addressee_share.png`, `fig_robot_gini_pairs.png`;
- `h3_attribution.csv`, `h3_decisions.csv`.

**Statistics choices:**
- exact Wilcoxon signed-rank, n = 7, so the smallest one-sided p is 1/128;
- rank-biserial r = (pos − neg) / total;
- exact McNemar on the decisions where only one method was right.

The scripts read the questionnaire workbook but do not write to it.

---

## 8. Results summary

| Hypothesis | Result | Verdict |
|---|---|---|
| H1: balancing lowers the Gini of speaking time | 4/7 groups, median −0.014, p = 0.23, r = −0.36 | Not supported (non-significant trend) |
| H2: live attribution ≥ 80 % | 0.836; 98 % precision when a seat is named | Supported |
| H3a: our attribution beats Micbot-style | 0.837 vs 0.677, 7/7 groups, p = 0.008; facing a side seat 0.87 vs 0.68 | Supported |
| False speech in silence | 0.38 vs 0.15, worse in 7/7 groups | Weakness of our method |
| H3b: our decisions pick the least active more often | 0.64–0.67 vs 0.74–0.79; Micbot-style significantly better under our own definition (p = 0.03) | Not supported (reverse tendency) |
| Fairness differs | 4.19 vs 3.97, p = 0.16 | No difference |

**Key messages for the discussion:**
- **Better per-reading accuracy did not give better decisions.** False speech in pauses accumulated into the activity scores and hurt more than the baseline's seat confusions did.
- **The manipulation was weak by design.** Balanced random already gives everyone 2 questions; balancing moved at most one question per person, and none in G01 and G02.
- **Being addressed works almost perfectly but sets only who speaks, not how much:** the addressee produced 96–99 % of the following talk.
- **Self-evaluation is misleading.** The robot's own estimate "confirms" H1 (6/7 groups, p = 0.039); the annotated truth does not (4/7, p = 0.23).

---

## 9. Team split and the hook

- **Session / robot / study:** `session.py`, `robot_io.py`, `animation.py`, `speech.py`, `recorder.py`, prompts, run and check scripts, data collection.
- **Detection / evaluation:** `listener.py`, `attribution.py`, `estimator.py`, `policies.py`, `detection_config.py`, `seats.py`, `sim_sources.py`, `simulation.py`, calibration fit, analysis scripts.

| Hook | Contract |
|---|---|
| `ParticipationListener.from_config(seats, det)` | runs in both conditions |
| `listener.update(reading, now, robot_speaking, head_yaw_deg)` on every reading | monotonic `now`; yaw in room frame, + left |
| `listener.activity()` before each decision | one score per seat, lower = quieter |
| `policy.choose(activity, history)` | returns 0-based seat |

---

## 10. Known limitations

**General:** Real-world details (chair placement, posture, voices, acoustics) are not fully controlled, so the calibration may sometimes be slightly off. It is treated as good enough for this study; say so in the report. Two rooms were used, with separate calibrations (section 4.1).

1. **Small sample:** n = 7 groups and ~3 min rounds with 6 decisions each. The smallest one-sided exact Wilcoxon p is 1/128. Report effect sizes and per-group results.
2. **False speech in pauses:** the HMM's persistence plus the weak speech flag credits a seat in 38 % of silent listening time. This is the main reason for the H3b result, and worst in G01.
3. **Mirroring** makes the opposite side seat and the middle seat harder to separate when the robot faces a side seat (section 3).
4. **The speech flag is weak** (section 4.1), but it did not affect turn-taking: every listening phase ended on silence.
5. **No sensing while the robot speaks or turns** (those calls block).
6. **Head-pose read failure** gives yaw 0° for that reading (`session._head_yaw_deg`).
7. **Connection events** are not logged to CSV (section 6).
8. **Crashes and re-runs:** 6 of 20 attempts crashed before the last question; re-runs reset the robot's memory of the group. Covered by the one-attempt rule plus a sensitivity check.
9. **Ground truth:** single annotator, not blind to condition (file names show it), one laptop microphone.
10. **Topic tied to round;** order A/B unbalanced (4/3).
11. **Same code version, uncommitted changes:** every round ran commit `4cd489e`, marked `-dirty` in the logs.

---

## 11. Micbot (Tennent, Shen & Jung, HRI 2019)

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
- Its rule is our offline computational baseline (H3). We re-implement only the decision rule on our hardware; we do not replicate its study.
- Its null result on speaking time is why H1 was an open question, and our H1 result is consistent with it.
- Our hardware adds problems Micbot did not have: an array that turns with the head, mirroring, and the robot hearing itself.

---