# Session protocol: participation-balancing study (Reachy Mini Wireless)

Session step by step guide.

- One group = 3 participants and two rounds of about 8 minutes (NOTE: rounds are not necessarily 8min so we should note it down in the report!): **random** and **balancing**, in the order given by the schedule. Allow **about 20 minutes per group**.
- In the commands: *random* = `--condition baseline`, *balancing* = `--condition adaptive`.

---

## A. first-time setup

1. **Python 3.12.** On a Mac, open Terminal and run `brew install python@3.12` (install Homebrew from https://brew.sh first if needed).
2. **Get the code and install it:**
   ```bash
   git clone https://github.com/zu-greta/HRI.git ~/Documents/HRI
   cd ~/Documents/HRI
   bash setup.sh
   ```
   This creates `.venv` and installs everything. It ends with a check; "no daemon" at this point is fine.
3. **Microphone permission** (macOS): System Settings → Privacy & Security → **Microphone** → switch **Terminal** on. Restart Terminal.
4. **Install Reachy Mini Control** (the robot's desktop app) and **Audacity** (free, https://www.audacityteam.org), used for labelling.
5. run `git pull` to make sure you are up to date

Every time, start with:
```bash
cd ~/Documents/HRI
source .venv/bin/activate
```

---

## B. connecting the robot (every time)

1. Switch the robot on (plug in the charger if the battery is low).
2. Turn on the **phone hotspot**, and connect **both the robot and the laptop** to it. Don't use university Wi-Fi: it blocks the connection.
3. On the laptop: plug in the charger, switch off **Low Power Mode**, switch off **AirDrop and Handoff**, and close other apps (browser, Zoom…).
4. Open **Reachy Mini Control**: select the Wireless robot → **Connect** → wait until it's ready → **wake** the robot. Make sure **no app is running** on the robot, and **close any camera view**.
5. In Terminal (after the two lines from section A):
   ```bash
   python check_setup.py --target wireless
   ```
   Every line should be `[ OK ]`, including **"microphone direction available"**.
   - A version warning: tell the team (the SDK version must match the robot's).
   - "no daemon": check the hotspot, or use `--host <ROBOT_IP>`.

---

## C. calibration

### C1. room layout (~10 min)
1. Put the robot on the table, facing the middle chair. **Mark its position and facing direction with tape.**
2. Put three chairs about 1 m from the robot: **seat 1 on the robot's left (+70°)**, **seat 2 straight ahead**, **seat 3 on the robot's right (−70°)**. Mark each chair with tape. While facing the robot, Seat 1 is the rightmost chair, Seat 2 is the middle, and Seat 3 is the leftmost.
3. Check that the robot faces each chair:
   ```bash
   python check_turns.py --target wireless
   ```
   Watch the robot: its face should point at seat 1, then seat 3, then back to the middle. If not, adjust the chairs (not the robot), re-mark them, and run it again.

### C2. calibration (~15 min, 3 people needed)
Calibrate once before the first group, don't move the chairs afterwards.

1. Three people sit in seats 1, 2 and 3.
2. Run:
   ```bash
   python run_calibration.py --target wireless
   ```
3. Follow the screen (about 6 minutes). The robot faces the group, then each seat in turn. At each position:
   - "Everyone **SILENT** for 5 s": nobody talks.
   - "**SEAT 1: speak now**" (20 s): only seat 1 reads aloud, in a normal voice. Then seat 2, then seat 3.
   - **If anyone speaks out of turn, or there is a noise, press Ctrl+C and start again.**
4. At the end it prints two file names (`logs/CALIB_calibration_<time>_ticks.csv` and `..._labels.csv`) and the next command. Run it with `--dry-run` first, which only shows the result:
   ```bash
   python evaluate_offline.py fit --ticks logs/CALIB_calibration_<time>_ticks.csv \
     --labels logs/CALIB_calibration_<time>_labels.csv --dry-run
   ```
   **Check the numbers:**
   - **Seats:** about **+70, 0, −70** (within ~15°). The **first must be positive** (seat 1 = robot's left) and the last negative. If the signs are reversed or a seat is far off, check the chairs and run the calibration again.
   - **Microphone model:** `angle_sigma_deg` roughly 5–25; `vad_false_alarm_rate` below about 0.15. A high false-alarm rate means the room was noisy or someone spoke during a silent part, so run it again.
5. If the numbers look right, run the same command **without `--dry-run`**. This writes `seats.json` and `detection_params.json` into `<REPO>`.
6. **Save the calibration:** push the `seats.json detection_params.json` files to GitHub
   Keep the two `CALIB_calibration_*` files too: copy them to `~/study_data/CALIB/`.
7. Check with `python check_turns.py --target wireless`: the robot should face each chair. `run_session.py` no longer prints the "PLACEHOLDER seat angles" warning.

### C4. Test round and pilot
1. A test round with 3 colleagues:
   ```bash
   caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir /Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/ \
     --group TEST --round 1 --topic 1 --condition adaptive --quiet-seat 3
   ```
2. Prepare: consent forms (including **audio recording**), pre-questionnaire, post-round questionnaire (the same one after each round), debrief text, and a notes sheet per group.

### Schedule (which round is which)

| Group | Round 1 | Round 2 | Quiet person sits in |
|---|---|---|---|
| G01 | random, topic 1 | balancing, topic 2 | seat 1 |
| G02 | random, topic 2 | balancing, topic 1 | seat 2 |
| G03 | random, topic 1 | balancing, topic 2 | seat 3 |
| G04 | random, topic 2 | balancing, topic 1 | seat 1 |
| G05 | balancing, topic 1 | random, topic 2 | seat 2 |
| G06 | balancing, topic 2 | random, topic 1 | seat 3 |
| G07 | balancing, topic 1 | random, topic 2 | seat 1 |

G01–G04 are order A (random first); G05–G07 are order B (balancing first).

---

## D. Before each group (~15 min, before participants arrive)

- [ ] Robot and chairs **exactly on the tape marks**.
- [ ] Section B (connecting the robot) done; `check_setup.py` all OK.
- [ ] `python check_turns.py --target wireless`: the face points at each chair.
- [ ] `python check_recording.py`: OK.
- [ ] **Robot microphone check:** open `http://reachy-mini.local:8000/api/state/doa` in a browser (or `http://<ROBOT_IP>:8000/api/state/doa`). Have someone talk from each chair, and refresh. The `angle` should be clearly different for left, middle and right, with `speech_detected` `true`.
- [ ] Find the group's two commands in section G, and keep them ready to copy.

---

## E. Running a group

### E1. Participants arrive 
1. Consent form, then the pre-questionnaire. Give IDs `G01-P1`, `G01-P2`, `G01-P3`.
2. Place quiet person in the seat the schedule gives. On the notes sheet, write: seat 1 = …, seat 2 = …, seat 3 = … (participant IDs).
3. Read out the **same instructions for every group**, and **don't mention conditions, "balancing" or "random"**:
   > "The robot will lead two short discussions of about 8 minutes each. It will ask questions, sometimes to a specific person. Please talk naturally with each other and with the robot. There are no right or wrong answers. After each discussion there's a short questionnaire."

### E2. Round 1 (~8 min)
1. Paste the group's **round 1 command** from section G and press Enter.
2. When it asks, each person says **"I'm in seat 1"** (2, 3). Then press **Enter**.
3. **Move out of sight** and don't intervene, unless something goes wrong (section H).
4. Wait until it prints **"Done"**, **"Audio saved"** and **"Log saved"**. Write any "connection lost" lines or warnings on the notes sheet.

### E3. Between the rounds (~5 min)
1. The post-round questionnaire (participants use their IDs).
2. Copy the round's logs into the group folder (use the group's number):
   ```bash
   cp logs/G01_R1_* Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G01_R1/
   ```
3. Notes: the start time, anything unusual. **Don't move anything or change any settings.**

### E4. Round 2 (~8 min)
The same as E2, with the group's **round 2 command**. Afterwards:
```bash
cp logs/G01_R2_* Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G01_R2/
```

### E5. End (~5 min)
1. The post-round questionnaire again, plus: *"Did you notice any difference between the two discussions? If so, what?"*
2. **Debrief:** explain that the robot either chose people at random, or chose whoever it heard least. Answer questions and thank them.
3. **Check the folder.** `ls ~/study_data/G01` should show, for **both** rounds: `….csv`, `…_ticks.csv`, `…_audio.wav`, `…_audio.json`. Save the notes sheet there as `notes.txt`.
4. **Back it up** to the agreed secure storage, and **never** to GitHub.

### E6. The next group

---

## F. After all groups: labelling and analysis

### F1. Label who spoke when (for every round)
For each `…_audio.wav` in `~/study_data/G0X/`:
1. Open it in Audacity and label **every stretch of speech** with the seat number (Cmd+B, type 1/2/3, Enter). Use the "I'm in seat …" introductions at the start to recognise the voices. Don't label the robot.
   - **Agreed rules:** label all speech of about 0.3 s or longer, including short "yeah"s. When two people talk at once, label both stretches.
2. File → Export → Export Labels… → `~/study_data/G01/G01_R1_labels.txt`.
3. Convert:
   ```bash
   python audacity_labels_to_csv.py ~/study_data/G01/G01_R1_labels.txt ~/study_data/labels/G01_R1.csv
   ```
4. **Quality check:** two people each label the **same 2 rounds** separately, saving them as `…_labels_B.txt`, so the team can report their agreement.

### F2. Fill in the study table
Create `~/study_data/study_sessions.csv` with one row per round (14 rows). Paths are relative to `~/study_data`; **leave `offset` empty** (it's read from the `_audio.json`):
```
group,order,round,topic,condition,quiet_seat,labels,offset,ticks,log,audio
G01,A,1,1,baseline,1,labels/G01_R1.csv,,G01/G01_R1_T1_baseline_<time>_ticks.csv,G01/G01_R1_T1_baseline_<time>.csv,G01/G01_R1_T1_baseline_<time>_audio.wav
G01,A,2,2,adaptive,1,labels/G01_R2.csv,,G01/G01_R2_T2_adaptive_<time>_ticks.csv,G01/G01_R2_T2_adaptive_<time>.csv,G01/G01_R2_T2_adaptive_<time>_audio.wav
```

### F3. Questionnaire table
Export the questionnaire answers as `~/study_data/questionnaire.csv` (fairness = the mean of the fairness items):
```
group,condition,participant,fairness
G01,baseline,G01-P1,4.2
G01,adaptive,G01-P1,4.6
```

### F4. Run the analysis
```bash
cd ~/Documents/HRI && source .venv/bin/activate
python analyze_study.py ~/study_data/study_sessions.csv --questionnaire ~/study_data/questionnaire.csv \
  --out ~/study_data/results/study.csv
```
This prints the evenness (Gini) per round, the comparison of random vs balancing per group with the statistical test, the check by order A/B, how often the robot recognised the right speaker (per seat), and the fairness ratings. Share the printout and `results/study.csv` with the team.

---

## G. All commands, ready to copy

Each command is one line, or continues on the next line after the `\`. Add `--host <ROBOT_IP>` if needed, and `--record-device "USB"` for a USB microphone.

**G01** (quiet person: seat 1)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G01 --group G01 --order A --round 1 --topic 1 --condition baseline --quiet-seat 1
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G01 --group G01 --order A --round 2 --topic 2 --condition adaptive --quiet-seat 1
```
**G02** (quiet person: seat 2)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G02 --group G02 --order A --round 1 --topic 2 --condition baseline --quiet-seat 2
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G02 --group G02 --order A --round 2 --topic 1 --condition adaptive --quiet-seat 2
```
**G03** (quiet person: seat 3)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G03 --group G03 --order A --round 1 --topic 1 --condition baseline --quiet-seat 3
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G03 --group G03 --order A --round 2 --topic 2 --condition adaptive --quiet-seat 3
```
**G04** (quiet person: seat 1)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G04 --group G04 --order A --round 1 --topic 2 --condition baseline --quiet-seat 1
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G04 --group G04 --order A --round 2 --topic 1 --condition adaptive --quiet-seat 1
```
**G05** (quiet person: seat 2)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G05 --group G05 --order B --round 1 --topic 1 --condition adaptive --quiet-seat 2
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G05 --group G05 --order B --round 2 --topic 2 --condition baseline --quiet-seat 2
```
**G06** (quiet person: seat 3)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G06 --group G06 --order B --round 1 --topic 2 --condition adaptive --quiet-seat 3
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G06 --group G06 --order B --round 2 --topic 1 --condition baseline --quiet-seat 3
```
**G07** (quiet person: seat 1)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G07 --group G07 --order B --round 1 --topic 1 --condition adaptive --quiet-seat 1
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/G07 --group G07 --order B --round 2 --topic 2 --condition baseline --quiet-seat 1
```

---

## H. If something goes wrong

| What you see | What to do |
|---|---|
| `(.venv)` missing at the start of the line | `cd ~/Documents/HRI` then `source .venv/bin/activate` |
| `check_setup` can't reach the robot | Is the robot on and awake, and are both devices on the hotspot? Try `--host <ROBOT_IP>` |
| "No microphone readings from …/api/state/doa" | In Reachy Mini Control, check the robot is awake and its audio/media is on. Tell the team (the microphone firmware must be ≥ 2.1.0) |
| "Could not start the recording" | Microphone permission for Terminal (section A step 3); check with `python check_recording.py`. **The round doesn't start until this is fixed.** |
| "WARNING: the recording is almost silent" | Wrong or muted microphone. The robot data is still valid; check with `check_recording.py` before the next round, and note it |
| "WARNING: using PLACEHOLDER seat angles" | Calibration is missing (`seats.json`). Don't run study groups: do section C3, or `git pull` to get it |
| "connection lost … recovered" | Nothing to do; note it on the sheet. The round continues |
| The round stops with a connection error | Check the hotspot and the robot, then **repeat the round** with the same command, and note it. The team decides later whether to use or exclude repeated rounds |
| The robot turns to between people | Is the robot or a chair off its tape mark? Put it back. **Don't** re-calibrate during a group |
| A participant wants to stop | Stop with **Ctrl+C**, thank them, and note it. Their data is removed if they withdraw consent |
| Anything else | Press **Ctrl+C** to stop the round, note what happened and the time, and ask the team |