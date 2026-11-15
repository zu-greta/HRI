# Report decisions - suggestions for what to include in the report based on the analysis notes and implementation notes

---

## 1. Framing: two comparisons at two levels

The contribution is a **computational method** for deciding whom the robot addresses. It is evaluated twice:

| | **Random (balanced)** | **Ours (balancing)** | **Micbot-style** |
| --- | --- | --- | --- |
| Role in the paper | Control condition of the user study | **Our method** | Baseline *method* (prior work: Tennent, Shen & Jung, HRI 2019) |
| Who is speaking | Not used for the decision (our HMM still runs and is logged) | HMM, head-aware, models front/back mirroring | Each reading → nearest seat (within 25°) |
| How active each person is | Not used | Speaking turns ≥ 1 s, recent speech weighs more (half-life 120 s) | Total speech since the start |
| Whom it addresses | Shuffled order, everyone exactly 2 of 6 times | Lowest score (ties → addressed longest ago) | Lowest total |
| Where it was run | **Live**, random rounds | **Live**, balancing rounds | **Offline**, replayed on the same recordings |
| Compared on | H1 (evenness), fairness | H1, H2, H3, fairness | H2/H3 accuracy and decisions |

**How to write it.**
- **RQ:** does a head-aware, recency-weighted tracking method identify the least active participant more reliably than a Micbot-style cumulative tracker (computational part, **H2/H3**)? And does addressing participants with it make participation more even than random addressing (behavioural part, **H1** + fairness)?
- **Why random is the live control:** it keeps everything identical (same questions, voice, gestures, and the same total number of questions) and changes only whether the choice is informed.
- **Why Micbot only offline:** a third live condition needed more groups. The raw sensor stream is logged, so both methods can be replayed on exactly the input the robot had. The replay reproduces the live robot exactly (100 % of ticks, 6/6 decisions on G01): state this to show the comparison is fair.
- **We do not replicate Micbot's study.** Micbot was non-verbal, used a fixed Kinect array and turned every 3 min; we re-implement only its *decision rule* on our hardware.

## 2. Design facts to state

| Decision | Notes |
| --- | --- | --- |
| Baseline is **balanced** random, not uniform | Each person is addressed exactly twice in 6 questions, shuffled and seeded per group and round. Uniform random leaves someone never addressed in ~26 % of rounds, which would confound the policy with robot attention. **The last time i checked the design report §1.3, says "uniformly at random" - i think we should maybe switch to "balanced"?** |
| Two rooms, two calibrations | G01 in room 1 (`seats_g1.json`, `detection_params_g1.json`), G02–G07 in room 2. Seats were calibrated per room; chairs were placed at the calibrated angles. |
| Rounds were shorter than planned | Planned ~8 min; G01 took 3.2–3.4 min. Every listening phase ended on 3 s of silence, none hit the 60 s cap. Report the real durations from section B. |
| Same robot behaviour in both conditions | Identical prompt audio in every round (same SHA-1 fingerprint, section A). Deterministic gestures only while speaking. Same 6 questions per topic. |
| Topic tied to round | Topic and round order are confounded; state as a limitation. |
| Quiet member | **Rule:** the quiet seat entered at the start of each round (`quiet_seat` in the log), chosen from the pre-questionnaire quiet score. mention any tie (G01, G06, G07 had ties) and G02 was supposed to be Iva?? but we used Danial. |

## 3. Data and annotation decisions

| Decision | Notes |
| --- | --- | --- |
| **Ground truth** = who spoke when, labelled by hand on the room audio | A laptop microphone recorded each round; speech was labelled in Audacity (seat 1/2/3). Rule: every stretch ≥ 0.3 s including short "yeah"s; overlapping speech labelled for each person; robot not labelled. |
| Label templates | Robot prompts were marked automatically from the log (also a sync check), and loud stretches were marked as candidates. The annotator assigned every seat by listening. The template contains **no robot guess**, so the ground truth is independent of the method. |
| Synchronisation | Audio, event log and tick log share one clock: tick time = audio `offset_s` + WAV time (`_audio.json`). No manual alignment. |
| **One annotator** | Single annotator, stated as a limitation. |
| Annotator not blind to condition | File names contain the condition; state it as a limitation. |
| Speech window | Counted from the robot's intro to the end of its outro; the "I'm in seat k" introductions are excluded. |
| **Re-run rounds** (crashes) | **Primary analysis = `complete_*` outputs. Rule:** each round uses the attempt that asked all 6 questions (G02 R1 → attempt 3, G02 R2 → attempt 4, G04 R1 → attempt 2), so every round has the same 6 questions. Sensitivity: all labelled attempts added up. 20 attempts for 14 rounds; three attempts crashed after the last question (no outro) and count as complete. |
| Turn vs backchannel | Not labelled separately; a labelled stretch < 1.0 s counts as a backchannel (same threshold as the robot's estimator). |
| Tick weighting | The robot read the microphones every ~0.123 s, not 0.1 s (request latency). Times are weighted by real duration, capped at 0.5 s. |

## 4. Measures and statistics

| Measure | Definition | Test |
| --- | --- | --- |
| **H1 (primary)** | Gini of annotated speaking time per round (0 = perfectly even) | Paired by group: balancing − random. One-sided exact Wilcoxon signed-rank (n = 7), rank-biserial r, number of groups improved. Order A vs B medians as the carryover check. |
| H1 secondary | Gini of turns only (≥ 1 s); Micbot's unevenness (Σ\|share − mean\|); quiet member's share | Same test, direction stated |
| **H2** | Share of single-speaker annotated speech the live robot assigned to the right seat (speech-time weighted; robot "nobody" = wrong; overlap and robot speech excluded). Overall, per seat, per condition, per room; confusion matrix | Against the 0.80 target (descriptive) |
| **False speech** (new) | Share of listening time with nobody labelled that the robot still credited to a seat | Descriptive; per method in H3a |
| **H3a** | H2-style accuracy and false speech for HMM vs nearest seat, replayed on the same ticks; also while facing a side seat (mirroring) | Paired by group, one-sided Wilcoxon |
| **H3b** | At each real decision moment (real history), would each method address the truly least active person? Three definitions of "truly least active": (1) ours: annotated turns, 120 s half-life; (2) last 120 s, all speech; (3) Micbot's: all speech since the start | Hit rates, exact McNemar on decisions where only one method was right. **Report all three**: (1) favours ours and (3) favours Micbot by construction. |
| Mechanism | After each question, the addressee's share of the following talk | Descriptive by condition, chance = 0.33 |
| Manipulation check | Times each seat / the quiet member was addressed, per round | Descriptive. **G01's balancing robot addressed 2/2/2**, the same as random. |
| Validity | Robot's estimated share vs annotated share per person | Spearman ρ |
| Fairness | Mean of 3 Likert items (share thoughts, fair chance, included) | Two-sided Wilcoxon per participant (n = 21, not independent) **and** per group mean (n = 7). Order A vs B. |
| Power | n = 7 groups | Smallest possible one-sided exact p = 1/128 = 0.008. Lead with effect sizes and the per-group pattern. |

**Single source of numbers:** statistics come from the scripts. The workbook's Results tab has the same W (30.5) but a slightly different p (0.167 vs 0.161) because of tie handling, so report the script's. Demographics and per-item means can come from the workbook.


## 5. Limitations to list (and how much they matter)

| Limitation | Effect on results |
| --- | --- |
| **n = 7 groups**, rounds ~3.3 min, 6 decisions each | **Largest.** Low power for H1; a null H1 is likely and is still reportable. |
| Balancing robot sometimes addressed 2/2/2 (G01) | Where the robot behaved like random, H1 cannot differ. Report the manipulation check per group. |
| Speech-flag quality and G01's calibration | Affects decisions (section 5); explains H3b. Room-specific. |
| Single annotator, not blind | Moderate. Ideally kappa on 2 rounds. (GRETA: we did not do this, the annotation process is quite long, i did it and i think its enough?) |
| Label edges not precise | Small. G01: H2 0.924 → 0.971 with edges shrunk by 0.25 s, i.e. a few points on H2 only. Gini changes by seconds out of ~70 s per round, so negligible. Both methods are scored against the same labels, so H3 stays fair. |
| Uncontrolled details (seating, posture, acoustics), two rooms | Small to moderate; calibration may be slightly off at times. |
| Re-runs reset the robot's memory | Affects re-run rounds only; covered by the sensitivity check. |
| Topic tied to round; order A/B unbalanced (4/3) | Carryover check by order. |
| Laptop microphone for ground truth; overlaps harder to hear | Small; overlaps are excluded from H2. |
| Reduce Bias | - File names contain the condition, where possible, have each person annotate rounds they did not run, and annotate both rounds of a group in random order (GRETA: i ran everything and annotated we can either list this as limitations or pretend it never happened). <br> - Don't open the robot's tick logs while annotating. (GRETA: i did this) |

