# Alyssa: tasks, step by step

Everything you need to do for the session / robot / study side, in order. For background, read
`PROJECT_OVERVIEW.md` first: §2 is the runtime flow, §3 the conventions and §8 the hook to Greta's code.
---

## A. Before the physical robot (laptop + simulator)

### A1. Set up and check the code
- [ ] `pip install -r requirements.txt`. 
- [ ] `python -m pytest -q tests` → all tests pass.
- [ ] `python sim_scenario.py --no-robot --fast` → two short rounds print. In the adaptive round Chloe (seat 3) should be addressed more often.

### A2. Watch it in the simulator
- [ ] Start the simulator. Use Reachy Mini Control, or in a terminal: `mjpython run_sim.py` on macOS; `python run_sim.py` on Windows/Linux.
- [ ] `python sim_scenario.py` in a second terminal. The head and body should turn to the seat each question is addressed to. (or just run this file with the app open)
- [ ] `python run_session.py --condition adaptive --source keyboard --turns 3 --silence 2`. Press 1/2/3 to "speak" as a seat.
  - After the robot turns to another seat, the `seat` column of the new `logs/..._ticks.csv` must still show the key you press. 
- [ ] `python run_session.py --condition baseline --source scripted --turns 6`. Over 6 turns each seat must be addressed exactly 2 times: see `Times addressed per seat` at the end.

### A3. Final questions and prompt audio (controlled variable: same content, same voice)
**Where:** `prompts/script.json`.
- [ ] Replace the 12 placeholder questions `t1_q1…t1_q6`, `t2_q1…t2_q6` and the two warm-ups `t1_open`, `t2_open` with the piloted ones.
  - Keep the ids.
  - Keep the same form for all addressed questions: open, low-stakes, starting with "What do you think: …".
  - Aim for similar length across the two topics; the report says "topics piloted for similar amounts of talk".
- [ ] Check `intro` and `outro`. The intro is also the **video sync point**, so do not make it start with silence.
- [ ] On **one** computer, with **one** fixed voice: `python make_prompts.py --voice <name>`. On macOS, list voices with `say -v '?'`.
- [ ] Listen to every file in `prompts/`.
- [ ] Commit `prompts/*.wav` **and** `prompts/manifest.json`. Never regenerate them after the pilot.
- [ ] Run `python -m pytest -q tests`: `test_both_topics_have_a_warmup_and_six_questions_with_audio_text` checks the ids.

### A4. Study materials 
- [ ] **Consent form + information sheet.** Must state:
  - audio/video recording, how data is stored, anonymisation (group codes G01…, participant codes P01…), right to withdraw;
  - the robot "facilitates a discussion". Do **not** reveal the two policies (blinding, report Table 2).
- [ ] **Pre-questionnaire.**
  - Demographics.
  - **Quiet self-report**, e.g. "In group discussions I usually speak less than others" (1–7). This selects the quiet participant and gives `--quiet-seat`.
  - **Familiarity** with the other two members (report Table 3).
- [ ] **Post-round questionnaire** (after each round): perceived fairness Likert items. Example items:
  - "Everyone had an equal chance to speak."
  - "The robot included me in the discussion."
  - "The robot treated everyone fairly."

  Their **mean** is the `fairness` column in `templates/questionnaire_template.csv`.
- [ ] **End question**, after round 2: "Did you notice any difference in how the robot behaved between the two rounds? If so, what?" This is the demand-characteristics check.
- [ ] **Debrief text**, which reveals the conditions.

### A5. Run sheet and experimenter script
- [ ] Make a **run sheet**: one row per group with group code, order (A for 4 groups, B for 3), quiet seat, date/time, and the **exact two commands**. For example, group G01 with order A and the quiet participant in seat 2:
  ```
  python run_session.py --target lite --group G01 --round 1 --topic 1 --order A --condition baseline --quiet-seat 2
  python run_session.py --target lite --group G01 --round 2 --topic 2 --order A --condition adaptive --quiet-seat 2
  ```
  - Order B swaps the conditions: round 1 `adaptive`, round 2 `baseline`. Topic always follows the round.
  - Put the quiet participant in a seat decided in advance. Vary the seat across groups so that seat and quietness are not confounded.
- [ ] Write the **experimenter script**: the same words for every group. Say nothing during the rounds and stay out of view.
  - Order of events: consent → pre-questionnaire → seating → camera on → round 1 → post-questionnaire → round 2 → post-questionnaire + end question → debrief.

---

## B. On the physical robot (before any participant)
### B1. Versions and connection
- [ ] Open `http://<robot>:8000/api/daemon/status`. The `version` must match `requirements.txt` (`reachy-mini==1.13.0`). If not, change `requirements.txt`, reinstall and tell Greta.
- [ ] The daemon must run **with media**: not `--no-media`. The microphone firmware must be ≥ 2.1.0.
- [ ] `python run_session.py --target lite --source robot --turns 1 --group TEST` must print `Speech input: robot microphones.` and play the prompts from the robot's speaker.

### B2. Conventions 
Use `python run_session.py --target lite --turns 2 --group CONV --no-response 20` and talk from known positions. Then open the `_ticks.csv`.
- [ ] **Microphone angle.** Speak from the robot's **left** while it faces the group (`head_yaw_deg` ≈ 0).
  - `angle_rad` should be **below 1.57** and `world_az_deg` **positive**.
  - If the signs are reversed, **stop and tell Greta**: the conversion in `attribution.mic_angle_to_head_deg` would need a sign flip.
- [ ] **Head yaw.** After the robot turns to seat 1 (+50° placeholder, the robot's left), `head_yaw_deg` must read about **+50**. If it reads −50, tell Greta; the fix goes in `robot_io.head_yaw_deg`.
- [ ] **Turning blocks.** In the event log, `robot_turn` must come ≈ 0.8 s after `decision`. If it comes immediately, `goto_target` does not block. Then add `time.sleep(self.move_duration_s)` at the end of `Robot.turn_to` in `facilitator/robot_io.py`.
- [ ] **Echo margin.** Look at the ticks right after `robot_speaking` goes from 1 to 0 while nobody talks.
  - If `speech` is still 1 for more than ~0.3 s, increase `ECHO_MARGIN_S` in `facilitator/speech.py` (e.g. 0.8). Note the value for the report.
- [ ] **Motor noise.** During the first ticks after a turn, nobody talking, `speech` should be 0. If not, tell Greta; it affects the false-alarm rate.
- [ ] **Latency.** Ticks should be ~0.1 s apart (column `t`). If gaps are often > 0.3 s, the DoA request is slow. Tell Greta, and use the USB connection (`lite`) rather than wireless.

### B3. Room
- [ ] Fix the robot position and three chairs, and **mark the floor with tape**. Chairs at roughly −50°, 0° and +50° from the robot, about 1–1.5 m away. Nothing may move after calibration.
- [ ] Same room and lighting for every group. No fans, music or open doors.
- [ ] **Camera**: all three faces and the robot in frame, with good audio, started **before** the intro. The intro start is the sync point.

### B4. Calibration (needs 3 helpers in the chairs)
- [ ] `python run_calibration.py --target lite`.
  - The terminal says which seat speaks: "SEAT k: speak now". The person in that seat reads any text aloud in a normal voice.
  - You stay **silent** and just point.
  - The robot faces the group, then each seat in turn. Re-run if anyone spoke out of turn.
- [ ] It writes `logs/CALIB_calibration_<stamp>.csv`, `..._ticks.csv` and `..._labels.csv`. **Send all three to Greta.** She runs `fit` and commits `seats.json` and `detection_params.json`.
- [ ] After Greta commits them, `run_session.py` no longer prints `WARNING: using PLACEHOLDER seat angles`. **A study round with that warning is not valid data.**

### B5. Dry runs and pilot
- [ ] One full dry run per condition with team members, both topics, the real run-sheet commands and group code `PILOT`. Check:
  - rounds take ≤ ~8 min;
  - `listen_end` reasons look sensible (mostly `silence`);
  - the event log has `mono_s`, a `versions` line and 6 `decision` rows.
- [ ] Send the dry-run logs + video to Greta. She checks H2 with `evaluate_offline.py replay`.
- [ ] One **pilot group** of external people with the full procedure. Check that both topics produce similar amounts of talk, and that the questionnaires work.
- [ ] Freeze: after the last change, `git tag study-v1` and push. Every study log's `versions` line must show this commit **without `-dirty`**.

---

## C. During data collection (every group)
- [ ] Camera on → run the two commands from the run sheet exactly.
- [ ] After each round, note anything unusual (interruptions, someone leaving, robot errors) in the run sheet.
- [ ] Copy `logs/` and the video to the shared storage **the same day**. These are **not** in git: `.gitignore` excludes `logs/` and videos.

---

## D. After data collection 

### D1. Annotation (split the videos between you; ~3 rounds annotated by hand)
- [ ] For each round, create `labels/<group>_R<round>.csv` like `templates/labels_template.csv`: `start_s,end_s,seat,kind`.
  - Times are in video seconds.
  - `kind` = `turn`, or `backchannel` for short responses like "mm-hm", "yeah" or laughter.
  - Leave silence as gaps. Overlapping speech gets two rows.
  - Annotate from the start of the intro to the end of the outro.
  - ELAN or any video tool works; export to CSV.
- [ ] For each round, note the video time when the robot **starts the intro sentence**, then run:
  `python evaluate_offline.py offset --log logs/<round log>.csv --video-s <that time>`. Put the printed offset into `study_sessions.csv`.
- [ ] Fill `study_sessions.csv` (copy `templates/study_sessions_template.csv`): 14 rows (7 groups × 2 rounds).
  - `quiet_seat` comes from the run sheet.
  - Paths are relative to the CSV file.
- [ ] Fill `questionnaire.csv` (`templates/questionnaire_template.csv`): one row per participant per round, with `condition` = `baseline` or `adaptive`.

### D2. Analysis and report
- [ ] Greta runs `analyze_study.py` and `evaluate_offline.py study`. You check the "addressed" column: equal robot behaviour in baseline = 2/2/2.
- [ ] Report: you write the procedure, the materials and the "Implementation: session and robot" part (PROJECT_OVERVIEW §2, §6).
