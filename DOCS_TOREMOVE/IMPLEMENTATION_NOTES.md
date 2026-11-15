# Implementation section notes

## How to use these notes

Raw material for report section 2, Implementation (Computational Focus, 30 points). It covers more than will fit; pick what serves the argument "our method vs a baseline, implemented robustly". Final results and their interpretation are in `RESULTS_WRITEUP.md`; method choices in `REPORT_DECISIONS.md`.

- Suggested structure for section 2: 2.1 System overview → 2.2 Interaction script → 2.3 Speaker attribution (HMM) → 2.4 Activity estimate and policy → 2.5 Baselines → 2.6 Calibration and parameters → 2.7 Logging, synchronisation and robustness.

## 2.1 System overview and platform

A Python program on a laptop drives a Reachy Mini Wireless. While the group talks, it reads the robot's own microphone array several times a second and decides who is speaking; before each question it picks whom to address. The only code path that differs between conditions is that final choice.

- **Robot:**
  - Reachy Mini Wireless, Reachy Mini SDK `1.13.0`.
  - Laptop and robot on a phone hotspot (university Wi-Fi blocked the connection). The robot's hostname is resolved to IPv4 before connecting (`robot_io._ipv4`).
- **Sensing input:**
  - The daemon's REST endpoint `/api/state/doa` returns `{angle, speech_detected}` from the head-mounted microphone array.
  - It is polled in a 0.1 s loop (`RobotDoASource`, 0.5 s timeout). Because each request takes time, readings actually arrived about every 0.12 s; all analysis weights each reading by its real duration.
  - A failed request counts as "no reading" and never stops a round. A retry mechanism was added after G04 (describe briefly what it retries).
- **Output:** pre-recorded prompt `.wav` files, uploaded once to the robot and played from its speaker; head + body turns via `goto_target`.
- **Code layout:** one package, `facilitator/`, split along a fixed interface:
  - *session side* (script, robot I/O, speech, logging): `session.py`, `robot_io.py`, `speech.py`, `animation.py`, `recorder.py`, `logger.py`, `ticklog.py`, `run_session.py`;
  - *detection side* (the computational contribution): `attribution.py` (who is speaking), `estimator.py` (how active everyone is), `policies.py` (whom to address), `listener.py` (glue), `detection_config.py`, `seats.py`.
- **Interface between the two** (three calls):
  - `listener.update(reading, now, robot_speaking, head_yaw_deg)` on every reading;
  - `listener.activity()` before each decision;
  - `policy.choose(activity, history)` returns the seat.
- **Detection runs in both conditions** and is logged in both; only the balancing policy uses it. This gave speaker-attribution data (H2) and offline replay data (H3) from all 14 rounds, not just the balancing ones.

**Figure: decision pipeline.** Only the policy step differs between conditions. The doc has this drawn as a diagram; redraw it in the report's style.

```
Mic array            Who speaks?          Activity score       Least active        Turn + ask
angle + speech  -->  HMM, head-aware, --> turns only,     -->  lowest score   -->  body faces seat,
flag, ~0.1 s         models mirroring     120 s half-life      (balancing)         address + question
                          ^                                                              |
                          +----------- head yaw: the microphones turn with the head -----+
                                                                                         ^
                                                         Random order -------------------+
                                                         balanced, seeded (random rounds)
Detection runs and is logged in both conditions (tick log).
```

In balancing rounds the least-active policy chooses the seat. In random rounds a seeded balanced order replaces it, while the same sensing still runs.

## 2.2 Interaction script (identical in both conditions)

Each round is a fixed script: 1 intro, 1 warm-up question to everyone, 6 addressed questions and 1 outro. Only the choice of addressee depends on the condition.

1. The robot faces the group (0°), plays the intro, then the warm-up question to everyone. The warm-up lets the robot hear everyone before its first decision.
2. **Listen** until the group goes quiet (rules below).
3. **Decide** whom to address: `policy.choose(activity, history)`. The decision is logged with all three activity scores.
4. **Turn** to that seat: `goto_target` over 0.8 s, with the antennas raised (+20°/−20°).
   - `body_share = 1.0`, so the body does the whole turn.
   - Why: on the lab robot the head added only ~3° on top of the body, so the planned 0.6 split stopped ~20° short of the side seats.
5. **Address** the person by number ("Participant one." / "two." / "three.", prompts `addr_1..3`), then ask the question (`t<topic>_q<n>`).
   - Seat k = participant k; at the start of the recording each person says "I'm in seat k".
   - These are two separate prompts, each logged with its start and end.
6. Repeat steps 2–5 six times. Then listen once more for the answer to the last question, face the group and play the outro.

**End-of-listening rule** (`session.wait_for_silence`). It is the same in both conditions and uses the raw speech flag, not the attributed seat:

| Reason | Trigger | Value |
| --- | --- | --- |
| silence | someone spoke, then no speech flag for | 3 s |
| no_response | nobody spoke at all for | 10 s |
| max_listen | hard cap per listening phase | 60 s |
| no_data | as no_response, but no readings arrived | 10 s |

- **Actual round length:** the design planned about 8 min, but rounds took about 3 min.
  - Random rounds averaged 3.1 min (range 2.6–3.7); balancing rounds 3.0 min (2.3–3.7).
  - **Every listening phase in the study ended on 3 s of silence**; none hit the 60 s cap or the no-response rule.
- **Questions** (`prompts/script.json`): open and low-stakes, all starting "What do you think: …" so every addressed question has the same form.
  - Topic 1, *working and studying*: warm-up "Where do you usually work or study best?"; then alone vs group study, music while concentrating, how often to take breaks, home vs library, to-do lists, studying with friends from other courses.
  - Topic 2, *travel*: warm-up "Where is one place in the world you would love to visit?"; then alone vs friends, planned vs spontaneous, city vs nature, learning the language first, relaxing vs busy holidays, what makes a place worth revisiting.
- **Talking gestures** (`animation.py`, `animate = True`, `gesture_scale = 1.0`). While a prompt plays:
  - slow head roll (6°, 0.35 Hz) and pitch (3°, 0.7 Hz) sway;
  - antenna motion (18° at 1.1 Hz + 7° at 2.3 Hz);
  - both sent at 25 Hz and faded in and out over 0.35 s;
  - plus the daemon's audio-driven head "wobbling".

  This controls the confound "unequal robot behaviour":
  - it is deterministic: the motion depends only on the prompt id (CRC32 seed) and time, so the same prompt moves the same way in every round;
  - it never changes yaw, and returns to the exact listening pose before the microphones are read again;
  - it happens only while the robot speaks, when detection ignores the microphones anyway;
  - mechanism: `Speaker.start()` begins playback without blocking, the gesture loop runs for the prompt's duration, then `Speaker.wait()`.
- **Voice: same audio in all rounds.**
  - Piper neural TTS, voice `en_US-lessac-medium`, offline and identical on any OS (`tts.py`).
  - Settings: length scale 1.0 (0.92 and 0.97 felt rushed), noise scale 0.8, noise-w scale 0.95. That gives slightly livelier intonation than Piper's defaults of 0.667 / 0.8.
  - Prompts are generated once and committed; each is uploaded to the robot at session start and played from its speaker.
  - The real robot never synthesises a missing prompt (`auto_generate` is off for non-simulator targets).
  - Each round logs a SHA-1 fingerprint of all prompt audio (`versions` event). It was identical (`be15c1082c`) in all 20 attempts.
- **Same randomness on re-runs:** the baseline order is seeded with `crc32("<group>-R<round>")`. It is reproducible, and a re-run of the same round replays the same order.

## 2.3 Sensing: what the microphone array gives and why it is hard

The robot reports one direction and one speech flag per reading, from an array that turns with the head and cannot tell front from back. These problems motivate our method.

- **Reading:** `angle` in radians in the *head* frame (0 = head's left, π/2 = straight ahead, π = head's right) and a binary `speech_detected` flag.
- **Conventions in code:** room azimuth in degrees, 0 = robot's neutral forward, + = robot's left; head-frame degrees = 90 − deg(angle). Seats are 1-based in logs and 0-based in code.
- **Problem 1, the array moves.** It sits in the head, so the same person gives a different angle after every turn. Room direction = head-frame direction + head yaw (`robot.head_yaw_deg()`, read on every reading).
- **Problem 2, front/back mirroring.** A left–right-only array reports a source behind it mirrored to the front: head-frame 113° is reported as 67°. With the calibrated seats this happens every time the robot faces a side seat, because the opposite side seat is 103–113° away (main room 113°, G01's room 103°).
- **Problem 3, noisy speech flag.** Calibration measured the flag missing 34 % of speech in the main room (67 % in G01's room) and firing on 35–36 % of silent readings in both (section 2.6). The direction is more informative than the flag.
- **Problem 4, the robot hears itself.** Its own voice arrives from the front; readings while it speaks (+0.5 s echo margin) are ignored.

The table gives the expected head-frame angle per seat for each calibration, and what a naive "room angle → nearest seat" rule (25° tolerance) does with it. Computed with `attribution.expected_mic_head_deg` and `NearestSeatAttributor`.

| Room (seats 1/2/3) | Robot faces | Seat 1 reported at | Seat 2 reported at | Seat 3 reported at | Naive rule gives seats 1/2/3 as |
| --- | --- | --- | --- | --- | --- |
| G02–G07 (+55.5°, −3.1°, −57.5°) | group (0°) | +55.5° | −3.1° | −57.5° | 1 / 2 / 3 |
| | seat 1 | 0° | −58.6° | −67.0° (mirrored) | 1 / 2 / **2** |
| | seat 2 | +58.6° | 0° | −54.4° | 1 / 2 / 3 |
| | seat 3 | +67.0° (mirrored) | +54.4° | 0° | **2** / 2 / 3 |
| G01 (+54.6°, +2.5°, −48.4°) | group (0°) | +54.6° | +2.5° | −48.4° | 1 / 2 / 3 |
| | seat 1 | 0° | −52.1° | −77.0° (mirrored) | 1 / 2 / **2** |
| | seat 2 | +52.1° | 0° | −50.9° | 1 / 2 / 3 |
| | seat 3 | +77.0° (mirrored) | +50.9° | 0° | **nobody** / 2 / 3 |

- **Reading:** when the robot faces one side seat, the naive rule credits speech from the **opposite side seat to the middle seat** (in G01 facing seat 3, to nobody).
- **How often it happens:** the robot faced a side seat after 4 of 6 questions in every random round (28/42), and after 4–5 of 6 in balancing rounds (33/42, 79 %). So this is a systematic error, not an occasional one.
- **Separation in that pose:** with mirroring modelled, the HMM's two competing candidates are:
  - 12.6° apart in the main room (67.0° vs 54.4°, against σ = 6.0°);
  - 24.9° apart in G01 (−77.0° vs −52.1°, against σ = 10.3°).

  They are separable, but less reliably than when the robot faces the middle. In the study, the HMM was still more accurate facing a side seat (0.87) than facing the middle (0.80).

## 2.4 Our method: attribution → activity estimate → policy

Three stages run in sequence:
1. an online HMM decides who is speaking on each reading;
2. a turn-based decaying score says how active each person has been;
3. the policy addresses the person with the lowest score.

### Stage 1: who is speaking (`attribution.HMMAttributor`)

- **States:** {silence, seat 1, seat 2, seat 3}. The belief over states is updated on every reading (forward filter) and renormalised each time.
- **Predict, then update:**

```latex
\bar b_t(j) = \sum_i b_{t-1}(i)\,T_{ij}, \qquad b_t(j) \propto \bar b_t(j)\, e_t(j)
```

- **Transitions** (per step):
  - stay silent 0.90; silence → a given seat 0.10 / 3;
  - a speaker continues 0.95, stops 0.03, or hands over directly to one other seat 0.01 each.

  People talk in stretches, so one stray reading cannot flip the speaker. The same persistence also carries a speaker through short pauses. This was the method's main weakness in the study: "false speech" in silences (section 2.8).
- **Emission** for a reading with angle θ (head frame) and speech flag v, given head yaw ψ and seat azimuth φ_k:

```latex
\mu_k(\psi) = \mathrm{fold}(\varphi_k - \psi), \qquad \mathrm{fold}(a) = \begin{cases} 180 - a & a > 90 \\ -180 - a & a < -90 \\ a & \text{otherwise} \end{cases}
```

```latex
e(k \mid v{=}1) = (1-p_{\text{miss}})\big[(1-\varepsilon)\,\mathcal N(\theta;\mu_k(\psi),\sigma^2) + \varepsilon/180\big], \qquad e(\text{silence} \mid v{=}1) = p_{\text{fa}}/180
```

```latex
e(k \mid v{=}0) = p_{\text{miss}}, \qquad e(\text{silence} \mid v{=}0) = 1 - p_{\text{fa}}
```

- The expected angle μ_k depends on where the head points and includes the mirroring (section 2.3), so the model knows that a speaker behind the array appears in front.
- **No reading at all** gives no information (all emissions 1).
- **While the robot speaks:** predict step only; output "nobody".
- **Output:** the most probable state, if it is a seat and its belief is at least 0.55; otherwise "nobody/unsure".

### Stage 2: how active everyone is (`estimator.TurnDecayEstimator`)

1. Attributed readings are merged into utterances; pauses shorter than 0.6 s are bridged.
2. Utterances shorter than 1.0 s are **backchannels** ("mm-hm", "yeah"): counted separately, not scored.
3. Each finished turn of length d_i, ending at time t_i, is added with exponential decay, half-life h = 120 s:

```latex
A_k(t) = \sum_{i \in \text{turns of } k} d_i \, 2^{-(t - t_i)/h} \; + \; (\text{current utterance of } k \text{ if } \geq 1\,\text{s})
```

- **Why decay:** with a running total, someone who dominated the first minutes and then went quiet is never invited. Likewise, a quiet person who has just started contributing keeps being targeted.
  - With ~3-min rounds, the decay changed scores only a little compared with a running total.
- **Why exclude backchannels:** they show listening, not taking the floor. Micbot's own video coding separated the two.
- **Terminology:** the equivalent decay constant is τ = h / ln 2 ≈ 173 s. The design report called it "decay time τ", so use one term consistently.

### Stage 3: whom to address (`policies.LeastActivePolicy`, balancing condition)

- **Candidates** = seats whose score is within 0.5 s of the lowest score (a tie, e.g. everyone at 0 at the start).
- **Tie-break:** pick the candidate addressed longest ago (never-addressed first), then the lower score, then the lower seat number. Fully deterministic.
- **Safeguards were off:** optional ones exist but were disabled in the study (`repeat_margin_s = 0`, `max_consecutive = 0`). In simulation, a cap of 2 consecutive picks lowered the hit rate from ~0.9 to ~0.75.
- **What it did in the study:**
  - Balancing rounds addressed seats 1/2/3 as 2/2/2 (G01, G02), 2/1/3 (G03, G04, G06) and 3/1/2 (G05, G07).
  - The quiet member was addressed 2.29 times on average, vs exactly 2 in random rounds.
  - The policy never addressed anyone more than 3 of 6 times.

## 2.5 Baselines

There are two baselines. Balanced random addressing is the live study condition; a re-implementation of Micbot's rule is compared offline on the same recordings.

| | Who is speaking | Activity measure | Whom to address | Where it runs |
| --- | --- | --- | --- | --- |
| **Ours (balancing)** | HMM, head-aware, mirroring modelled | speaking turns, 120 s half-life, backchannels excluded | lowest score | live, balancing rounds |
| **Random (balanced)** | (HMM still runs and is logged) | not used | shuffled round-robin | live, random rounds |
| **Micbot-style** | nearest seat per reading (room angle within 25°) | total attributed seconds since start | lowest total | offline replay only |

- **Random = balanced, not uniform** (`RoundRobinPolicy`).
  - Questions are grouped in blocks of 3, each block a seeded shuffle of the 3 seats, never the same person twice across a block boundary. Each person is addressed exactly 2 of 6 times.
  - Uniform random would leave someone never addressed in ~26 % of rounds (tested in `tests/test_study.py`). That would confound "who the robot attends to" with the policy.
  - **The design report §1.3 still says "uniformly at random" and must be changed.**
- **Micbot-style** (Tennent, Shen & Jung, HRI 2019).
  - Micbot turned to whoever had cumulatively spoken least, using a microphone array fixed behind the robot.
  - Ours re-implements that rule on our hardware: `NearestSeatAttributor` + `CumulativeEstimator` + `MicbotPolicy`.
  - The paper reports no tracking accuracy; ours is measured (H2) and compared (H3).
- **Why offline:** all raw readings, head yaws and robot-speaking flags are logged, so any method can be replayed on the exact sensor stream the live robot saw. A third live condition would have needed more groups.
- **The replay is exact:**
  - replaying our HMM offline reproduced the live robot's attribution on 100 % of readings in every attempt;
  - it reproduced all 46 live balancing decisions (`evaluate_offline.py study`).
- **Pre-study simulation per room**, using each room's calibrated seats and microphone model (`evaluate_offline.py sim`, 60 simulated sessions per group type; simple group model, illustration only):

| Measure (simulated) | Main room G02–G07: HMM | Main room: nearest | G01 room: HMM | G01 room: nearest |
| --- | --- | --- | --- | --- |
| Share of speech readings assigned to the right seat | 0.89 | 0.53 | 0.81 | 0.28 |
| Accuracy while the robot faces a side seat (all readings) | 0.86 | 0.54 | 0.78 | 0.40 |
| Speaking-time error (sum of absolute error / total) | 0.04 | 0.33 | 0.07 | 0.58 |
| Picks the truly least active (last 120 s), full pipeline | 0.83–0.89 | 0.49–0.59 (Micbot-style) | 0.76–0.86 | 0.54–0.64 (Micbot-style) |

- Round-robin picked the truly least active person in 36–40 % of simulated decisions, close to chance (1 in 3).
- Ranges are across the three simulated group types (one dominant, two quiet, balanced).
- **Simulation vs reality:**
  - The real study confirmed the attribution advantage: H2 = 0.836; HMM 0.84 vs nearest 0.68 on the recordings.
  - It did **not** confirm the decision advantage: on real data the Micbot-style rule picked the least active person more often (0.74–0.79 vs 0.64–0.67).
  - The simulated microphone did not reproduce false speech in pauses. That is the main lesson about the simulator.

## 2.6 Calibration and parameter values

Seat directions and the microphone model were measured on the robot and frozen per room. The study used two rooms, so there are two calibrations: one for G01 (`seats_g1.json`, `detection_params_g1.json`) and one for G02–G07 (`seats.json`, `detection_params.json`). The chairs were placed at the calibrated angles; the timing parameters are fixed design choices.

**Calibration procedure** (`run_calibration.py`, ~6 min, 3 people in the chairs):

1. The robot faces the group (0°), then each seat in turn (4 head positions).
2. At each position: 1.5 s settle + 5 s everyone silent, then each seat reads aloud alone for 20 s on an on-screen cue, with 2 s gaps.
3. The schedule is the ground truth, so labels are written automatically. Each speaking window is trimmed by 1.0 s at the start (reaction time) and 0.5 s at the end; no video annotation is needed.

**Fitting** (`evaluate_offline.py fit`):

- **Seat angle** = median room angle of labelled speech readings while the head faced the group (|yaw| < 10°, so no mirroring).
- **Angle spread σ** = 1.4826 × median absolute residual (robust; floor 3°). Residuals are taken against the mirroring-aware expected angle at every head position.
- **Outlier rate** = share of residuals beyond 3σ.
- **Miss rate** = share of labelled speech readings without the speech flag.
- **False-alarm rate** = share of clearly silent readings with the flag. Readings within 1.5 s of a label edge are skipped, because they are often still speech.
- Robot-speaking readings are excluded.

**All parameter values used in the study:**

| Parameter | G01 (room 1) | G02–G07 (room 2) | Source |
| --- | --- | --- | --- |
| Calibration recording | `CALIB_calibration_20261110_151627` | `CALIB_calibration_20261112_133633` | `run_calibration.py` |
| Seat azimuths (seats 1, 2, 3) | +54.6°, +2.5°, −48.4° | +55.5°, −3.1°, −57.5° | calibration (`seats_g1.json` / `seats.json`) |
| Angle spread σ | 10.28° | 6.0° | calibration |
| Outlier rate ε | 0.077 | 0.054 | calibration |
| Speech-flag miss rate | 0.671 | 0.340 | calibration |
| Speech-flag false-alarm rate | 0.348 | 0.362 | calibration |
| Stay speaking / stay silent (per step) | 0.95 / 0.90 | same | design choice |
| Minimum confidence to name a seat | 0.55 | same | design choice |
| Nearest-seat tolerance (baseline) | 25° | same | design choice |
| Utterance merge gap | 0.6 s | same | design choice |
| Backchannel threshold | 1.0 s | same | design choice |
| Score half-life | 120 s | same | code default (the params files do not set it) |
| Tie margin | 0.5 s | same | code default |
| Echo margin after robot speech | 0.5 s | same | design choice |
| Silence / no-response / max listen | 3 s / 10 s / 60 s | same | design choice |
| Turn duration; body share | 0.8 s; 1.0 | same | design choice; body share adjusted on the robot |

The two rooms ended up with similar layouts: side seats at about +55° and −48° to −58°, and the middle seat within 3° of straight ahead. The main room's array readings were tighter (σ 6.0° vs 10.3°), and its speech flag missed half as much speech.

Notes for the write-up:

- **Calibration checks** used on the day:
  - `check_turns.py` turns the robot to each calibrated seat and prints the commanded vs reached head and body yaw (from `/api/state/full`), while the team watches that the face points at each chair.
  - `check_setup.py` confirms the Python and SDK versions, that the daemon version matches the SDK, and that microphone-direction data is available.
- **Good enough for this study, not perfect.** Chair positions, how people sit and lean, and room acoustics cannot be fully controlled, so the calibration may sometimes be a little off. We treat it as adequate for a course-scale study and state it as a limitation.
- **Two rooms.** G01 ran in a different room with its own calibration.
  - **H2:** G01 had the best live attribution (0.96).
  - **False speech:** it was also the most affected (0.67 of silences credited to someone, vs 0.33 in G02–G07).
  - **H1:** its Gini difference (+0.060) points against balancing, but leaving G01 out leaves the conclusion unchanged (4/6 groups improved, not significant). Not an outlier in a way that changes results.
  - **Why G01 is so affected:** its fitted miss rate (0.671) is higher than one minus its false-alarm rate (0.652). With those values a "no speech" reading is not evidence for silence, so the filter keeps the last speaker talking through pauses.
- **High speech-flag false-alarm rate in both rooms** (0.35–0.36, against the protocol's sanity limit of ~0.15).
  - Despite this, **every listening phase ended on 3 s of silence**, so false alarms did not keep phases open in practice. They probably come in bursts rather than steadily.
  - The rate mainly matters for attribution: together with the HMM's persistence it causes false speech in pauses (section 2.8).

## 2.7 Logging, synchronisation, robustness and re-runs

Every run writes four synchronised files on one clock, so speech labels made on the room audio can be compared reading by reading with what the robot sensed and decided.

| File (per run) | Contents | Written |
| --- | --- | --- |
| `<group>_R<r>_T<t>_<condition>_<time>.csv` | event log: study info, code version + prompt-audio fingerprint, gesture settings, each prompt start/end, each listening phase start/end (reason, duration, speech seconds), each decision (seat + all three activity scores), each turn, times addressed | flushed after every event |
| `..._ticks.csv` | one row per reading while listening: raw angle, raw speech flag, head yaw, robot-speaking flag, naive room angle, attributed seat, confidence, activity scores | flushed every 50 rows |
| `..._audio.wav` | room audio from the laptop microphone, 16 kHz mono 16-bit (~1.9 MB/min) | background thread; header patched every 5 s |
| `..._audio.json` | `offset_s` = session-clock time of the first audio sample, device, peak level, stream problems | at start and end |

**Synchronisation:**

- All four use `time.monotonic()`: tick `t`, event `mono_s`, audio `offset_s`.
- Session time = `offset_s` + time in the WAV. Labels made in Audacity on the WAV move onto the robot's clock with that one number, with no manual alignment.
- `caffeinate -dis` kept the laptop awake, because on macOS the monotonic clock pauses during sleep.

**Ground truth (annotation):**

- **Labelling template.** `make_label_templates.py` writes a starting Audacity label track per recording:
  - every robot prompt, with exact times from the event log (it doubles as a sync check);
  - the "I'm in seat k" introductions;
  - loud stretches while the robot is silent, marked "?".

  The template contains **no robot guess of who spoke**, so the ground truth stays independent of the method it evaluates.
- **Labelling.** One annotator assigned a seat to every stretch of speech ≥ 0.3 s by listening. Overlaps were labelled for both people; the robot was not labelled. Seats were identified from the introductions.
- **Conversion.** `audacity_labels_to_csv.py` turns the Audacity export into `start_s,end_s,seat`. It skips non-seat labels and warns about any "?" left.
- **Checks.** `check_labels.py` checked every labelled recording for:
  - format problems and duplicates;
  - labels on top of the robot's prompts;
  - long overlaps;
  - coverage: loud audio left unlabelled, and labels in quiet audio;
  - timing sensitivity: H2 with every label edge shrunk by 0.25 s.

  A second annotator was not available, so there is no inter-rater agreement (stated as a limitation).
- **Backchannels** were not labelled separately. The analysis treats any labelled stretch under 1.0 s as a backchannel (the same threshold as the estimator); this is used for the secondary "turns-only" Gini.
- **Analysis window:** speech is counted from the robot's intro to the end of its outro, so the introductions are excluded.

**Robustness** (`robot_io.py`, `recorder.py`):

- **Lost connection:** robot commands go through a wrapper. It waits up to 3 s for the data stream to resume, then reconnects (up to 10 attempts, 2 s apart), then retries the command once.
- **Errors never stop data saving:** a gesture error never stops a round, and closing the robot never raises.
- **Audio:** stopped and saved in a `finally` block even when a round is aborted. A warning is printed if the recording is nearly silent (peak < 0.02).
- **Sensing:** a failed microphone-direction request returns "no reading" instead of an exception; a retry mechanism was added after G04.

**Crashes and re-runs:**

| Round | Attempts | Used in the analysis |
| --- | --- | --- |
| G02 R1 (random) | 3: two short crashed attempts (3 and 0 questions), then complete | attempt 3 |
| G02 R2 (balancing) | 4: 4, 1, 2 and 6 questions | attempt 4 (crashed after the last question, during the outro) |
| G04 R1 (random) | 2: 3 questions, then 6 | attempt 2 (crashed after the last question) |
| G04 R2 (balancing) | 1 | attempt 1 (crashed after the last question) |
| All other rounds | 1, complete | attempt 1 |

- In total: **20 attempts for 14 rounds**.
- **Rule:** each round uses the attempt that asked all 6 questions, so every round has the same 6 questions. Crashes after the last question don't matter, because the discussion was complete.
- **Sensitivity check:** adding up all labelled attempts gives the same conclusions.
- **What a re-run means:** a fresh process. The script restarts from the intro and the robot's activity estimate restarts at zero, so the balancing robot does not remember the crashed attempt.
- **Reproducible order:** the baseline order is seeded, so a re-run of a random round replays the same addressing sequence.
- **Finding attempts:** `build_sessions.py` finds every attempt and its four files, reads group, round, condition and quiet seat from the log, and matches each attempt to its room's calibration by the seat angles logged.

## 2.8 Implementation limitations and what to show

The main implementation limits are sensing quality, especially false speech in pauses, and a few gaps in what the logs record. None of them changes how the two conditions were run.

**Limitations to state:**

- **False speech in pauses (main weakness of our method).**
  - Replayed on all recordings, the HMM credited a seat in 38 % of listening time where nobody was labelled, vs 15 % for the nearest-seat rule (worse in 7/7 groups).
  - Cause: its persistence (stay speaking 0.95 per step) combined with the speech flag's ~35 % false-alarm rate. G01's calibration made it worse.
  - Consequence: activity scores were inflated, and the Micbot-style rule picked the least active person more often (see results).
  - Fix for future work: a silence-aware model (lower persistence or a higher confidence threshold during pauses), and tuning on decision quality instead of per-reading accuracy.
- **Uncontrolled real-world details.** Exact chair positions, people leaning or turning, voices and room acoustics vary between groups, so the calibration may sometimes be slightly off. We consider it good enough for a study of this scale, but say so.
- **Two rooms, two calibrations** (G01 vs G02–G07).
- **Mirroring:** mirrored seats are harder to separate when the robot faces a side seat. The two candidates are 12.6° apart in the head frame in the main room and 24.9° in G01's room (section 2.3).
- **Weak speech flag:** miss rate 0.34 in the main room and 0.67 in G01's room; false alarms 0.35–0.36. Attribution relies mainly on direction.
- **No sensing while the robot speaks or turns,** because `say()` and `goto_target` block. Detection and logging pause, so the tick log has gaps there; robot-speech times come from the event log.
- **Turn-end detection** uses the raw speech flag (identical in both conditions). In practice every phase ended on silence.
- **Head-pose fallback:** if reading the head pose fails mid-round, yaw falls back to 0° for that reading (`session._head_yaw_deg`).
- **Connection losses** are printed but not written to the event log (`run_session.py` does not set `robot.on_event`); they are on the paper notes sheets only.
- **Crashes:** 6 of 20 attempts crashed before the last question and were re-run (section 2.7).
- **Single laptop microphone and a single annotator** for the ground truth. Overlapping speech and quiet voices are harder to label; there is no inter-rater agreement.
- **Untuned parameters:** everything other than the microphone model was set by design or simulation, not tuned on real groups.
- **Code version:** every round ran the same commit (`4cd489e`) with uncommitted local changes (`-dirty` in the logs).

**Suggested figures and tables** for section 2 (pick 2–3; the report has 6 pages in total):

1. Pipeline diagram (section 2.1): microphone reading → HMM → activity score → policy → turn + question, with the random baseline as the bypass. Redraw it in the report's style.
2. Room layout from above: robot, three chairs at the calibrated angles, and the mirroring case drawn for one pose.
3. The mirroring table from section 2.3.
4. The method-comparison table from section 2.5 (ours / random / Micbot-style).
5. The parameter table from section 2.6 (appendix if space is short).
6. Optional, not produced: one example round as a timeline (attributed seat per reading vs labelled speaker, decisions marked). It would illustrate false speech in pauses; it could be made from one tick log and its labels if there is space.