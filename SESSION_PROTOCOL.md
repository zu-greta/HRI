# Session protocol for experiment running

Session step by step guide:

- One group = 3 participants and two rounds of about 8 minutes: **random** and **balancing**, in the order given by the schedule. 
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

1. Switch the robot on (plug in the charger if the battery is low). follow instructions to connect the robot with phone hotspot over wifi connection.
2. Open **Reachy Mini Control**: select the Wireless robot → **Connect** → wait until it's ready → **wake** the robot. Make sure **no app is running** on the robot, and **close any camera view**.
3. In Terminal (after the two lines from section A):
   ```bash
   python check_setup.py --target wireless
   ```
   Every line should be `[ OK ]`, including **"microphone direction available"**.
   - A version warning: tell the team (the SDK version must match the robot's).
   - "no daemon": check the hotspot, or use `--host <ROBOT_IP>`.

---

## C. calibration

### C1. room layout
1. Put the robot on the table, facing the middle chair. Mark its position and facing direction with tape
2. Put three chairs about 1 m from the robot: **seat 1 on the robot's left (+50°)**, **seat 2 straight ahead**, **seat 3 on the robot's right (−50°)**. Mark each chair with tape. While facing the robot, Seat 1 is the rightmost chair, Seat 2 is the middle, and Seat 3 is the leftmost.
3. Check that the robot faces each chair:
   ```bash
   python check_turns.py --target wireless
   ```
   Watch the robot: its face should point at seat 1, then seat 3, then back to the middle. If not, adjust the chairs (not the robot), re-mark them, and run it again.

### C2. calibration 
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
   - **Seats:** about **+50, 0, −50** (within ~15°). The **first must be positive** (seat 1 = robot's left) and the last negative. If the signs are reversed or a seat is far off, check the chairs and run the calibration again.
   - **Microphone model:** `angle_sigma_deg` roughly 5–25; `vad_false_alarm_rate` below about 0.15. A high false-alarm rate means the room was noisy or someone spoke during a silent part, so run it again.
5. If the numbers look right, run the same command **without `--dry-run`**. This writes `seats.json` and `detection_params.json` into `<REPO>`.
6. **Save the calibration:** push the `seats.json detection_params.json` files to GitHub
   Keep the two `CALIB_calibration_*` files too: copy them to `/logs/CALIB/`.
7. Check with `python check_turns.py --target wireless`: the robot should face each chair. `run_session.py` no longer prints the "PLACEHOLDER seat angles" warning.

### C4. Test round and pilot
1. A test round with 3 colleagues:
   ```bash
   caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir /Users/gretazu/Documents/ICL_fall/70101_hri/cw/gp1/HRI/logs/analysis_data/ \
     --group TEST --round 1 --topic 1 --condition adaptive --quiet-seat 3
   ```

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

## D. study commands

### checks
python check_turns.py --target wireless
python check_setup.py --target wireless
python run_session.py --target wireless --source none --group CHECK --turns 1 --no-response 2

### schedule
rishi(2), will(3), mona (1 - Q) 13:00
declan(1), iva(3), danial(2 - Q) 13:20 
jennyfer(1), johnny(2), teim(3 - Q) 15:10 
jin(1 - Q), rodrigo(3), alexandre(2) 15:30 
fernando(3), tiago(2 - Q), & emilie(1) 16:00 
yasir(1), gavin(3 - Q), omar(2) 16:20
gaby(3), rodrigue(2), yuliia(1 - Q) 16:40

**G01** (quiet person: seat 1)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G01 --group G01 --order A --round 1 --topic 1 --condition baseline --quiet-seat 1
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G01 --group G01 --order A --round 2 --topic 2 --condition adaptive --quiet-seat 1
```
**G02** (quiet person: seat 2)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G02 --group G02 --order A --round 1 --topic 2 --condition baseline --quiet-seat 2
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G02 --group G02 --order A --round 2 --topic 1 --condition adaptive --quiet-seat 2
```
**G03** (quiet person: seat 3) 
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G03 --group G03 --order A --round 1 --topic 1 --condition baseline --quiet-seat 3
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G03 --group G03 --order A --round 2 --topic 2 --condition adaptive --quiet-seat 3
```
**G04** (quiet person: seat 1)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G04 --group G04 --order A --round 1 --topic 2 --condition baseline --quiet-seat 1
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G04 --group G04 --order A --round 2 --topic 1 --condition adaptive --quiet-seat 1
```
**G05** (quiet person: seat 2)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G05 --group G05 --order B --round 1 --topic 1 --condition adaptive --quiet-seat 2
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G05 --group G05 --order B --round 2 --topic 2 --condition baseline --quiet-seat 2
```
**G06** (quiet person: seat 3)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G06 --group G06 --order B --round 1 --topic 2 --condition adaptive --quiet-seat 3
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G06 --group G06 --order B --round 2 --topic 1 --condition baseline --quiet-seat 3
```
**G07** (quiet person: seat 1)
```bash
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G07 --group G07 --order B --round 1 --topic 1 --condition adaptive --quiet-seat 1
caffeinate -dis python run_session.py --target wireless --source robot --record --record-dir logs/analysis_data/G07 --group G07 --order B --round 2 --topic 2 --condition baseline --quiet-seat 1
```

---