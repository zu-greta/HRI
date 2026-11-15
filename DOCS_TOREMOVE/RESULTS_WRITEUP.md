# Results - summary

Everything needed to write the Results and Discussion sections: 7 groups, 21 participants, all 14 rounds labelled. Read together with `REPORT_DECISIONS.md` (method choices) and `IMPLEMENTATION_NOTES.md` (system description).


**NOTE** the results_complete drops the attempts that crashed. the results folder includes all attempts. im not sure if this changes anything?

---

## 1. The results in short:

1. The robot ran the script reliably: 14 rounds, identical prompt audio in all 20 attempts, every listening phase ended on silence, and rounds took about 3 minutes.
2. **The computational method improved speaker attribution.**
   - The live robot assigned **84 %** of labelled speech to the right person (**H2 met**).
   - Replayed on the same recordings, our HMM beat the Micbot-style method in **all 7 groups** (0.84 vs 0.68, p = 0.008, **H3a supported**), most clearly when the robot faced a side seat (0.87 vs 0.68).
3. **But our method also credited speech during silences more often** (38 % vs 15 % of unlabelled listening time, worse in 7/7 groups). As a result, its decisions picked the truly least active person *less* often than the Micbot-style rule: 64–67 % vs 74–79 %. That difference is significant under our own definition of "least active" (p = 0.03). **H3b not supported; the opposite tendency.**
4. **Balancing did not significantly even out participation.** Gini was lower in 4 of 7 groups, median −0.014, p = 0.23, r = −0.36 (**H1 not supported**). The secondary measures lean the same way (turns-only Gini 5/7, quiet member's share 5/7), but none is significant. Perceived fairness did not differ (p = 0.16).
5. Two explanations:
   - The balanced-random baseline already gives everyone the same number of questions. The balancing robot changed this by at most one question per person, and in G01 and G02 not at all.
   - People spoke almost only when addressed (96–99 % of the talk after a question came from the person asked), so evenness was decided by how long each person answered.

-> so our computational method improved speaker attribution, but the behavioural effect was too small to show up in the Gini. The robot's decisions were not the only factor in how much each person spoke.
our hypothises were not completly supported but thats ok i think? as long as we state the limitations and what our results show - just talk about the computational method and behavioural effect, we dont have to be right about it.
-> i think one of our main limitations in the testing also comes from the fact that we only had 7 groups and only 6 questions per rounf which doesnt rlly give that much space for the differnece between balanced and random + whenever we have network issues etc, that also messed things up

## 2. Sample and procedure facts

| Fact | Value | Source |
| --- | --- | --- |
| Participants | 21 in 7 groups of 3; order A (random first): G01–G04, order B: G05–G07 | workbook Participants |
| Demographics | gender, age, English fluency, robot experience | workbook Participants tab (mean/SD/range) |
| Rooms | G01 in room 1, G02–G07 in room 2, each with its own calibration | REPORT_DECISIONS |
| Round duration | random 3.1 min (2.6–3.7), balancing 3.0 min (2.3–3.7) | complete_rounds.csv |
| How listening ended | every listening phase ended on 3 s of silence; none hit the 60 s cap | analysis.txt B |
| Crashes and re-runs | 20 attempts for 14 rounds. Used: G02 R1 attempt 3, G02 R2 attempt 4, G04 R1 attempt 2. G02 R2 att. 4, G04 R1 att. 2 and G04 R2 crashed *after* the last question (no outro) and count as complete. | analysis.txt A |
| Same robot behaviour | prompt audio fingerprint identical in all attempts (`be15c1082c`); same code version (`4cd489e`, run with uncommitted changes: state it) | analysis.txt A |
| Annotated speech | 17.8 min of single-speaker speech used for H2 | complete_h2_confusion.csv |

## 3. Manipulation check: did the balancing robot behave differently?

Questions addressed to seats 1/2/3 in the balancing round (random is always 2/2/2), and to the quiet member:

| Group | Balancing round | Quiet member addressed (random → balancing) |
| --- | --- | --- |
| G01 | **2/2/2** | 2 → 2 |
| G02 | **2/2/2** | 2 → 2 |
| G03 | 2/1/3 | 2 → 3 |
| G04 | 2/1/3 | 2 → 2 |
| G05 | 3/1/2 | 2 → **1** |
| G06 | 2/1/3 | 2 → 3 |
| G07 | 3/1/2 | 2 → 3 |

- On average the quiet member was addressed **2.29 times in balancing vs 2.00 in random**.
- In 2 of 7 groups the balancing robot behaved exactly like random; in G05 it addressed the quiet member *less*.
- **When it decided, the balancing robot chose the person who had truly spoken least so far in 25 of 42 decisions (60 %)**, about twice the chance level of one in three (67 % under the recency-weighted definition).

**What it means:** the manipulation was **weak by design**. A balanced-random baseline already equalises how often each person is addressed, so balancing could only move one question per person. State this plainly: it limits what H1 can show.

## 4. H1: evenness of speaking time (annotated)

| Group | Order | Gini random | Gini balancing | Difference |
| --- | --- | --- | --- | --- |
| G01 | A | 0.151 | 0.211 | +0.060 |
| G02 | A | 0.287 | 0.131 | −0.157 |
| G03 | A | 0.135 | 0.051 | −0.084 |
| G04 | A | 0.114 | 0.136 | +0.022 |
| G05 | B | 0.310 | 0.223 | −0.086 |
| G06 | B | 0.136 | 0.121 | −0.014 |
| G07 | B | 0.058 | 0.088 | +0.030 |

**Primary test:** 4/7 groups more even with balancing; median difference −0.014, mean −0.033. One-sided exact Wilcoxon W = 9, **p = 0.23**, rank-biserial r = −0.36. **H1 not supported; H0 retained.**

| Secondary measure | Groups in hypothesised direction | Median difference | p (one-sided) | r |
| --- | --- | --- | --- | --- |
| Gini of turns only (≥ 1 s) | 5/7 | −0.020 | 0.15 | −0.50 |
| Micbot unevenness (% points) | 4/7 | −5.1 | 0.15 | −0.50 |
| Quiet member's share of speech | 5/7 | +0.126 | 0.23 | +0.36 |

- **Sensitivity check** (all labelled attempts added up): the same counts and p-values (Gini p = 0.23; G02's difference −0.213 instead of −0.157). Conclusions unchanged.
- **Order (carryover):** Gini difference median −0.031 in order A, −0.014 in order B, so no sign of a carryover effect on evenness. The quiet member's share rose more in order B (median +0.126) than in order A (+0.012).
- **Figure:** `complete_fig_gini_pairs.png` (one line per group, blue = more even with balancing).

**What it means:**
- The data lean slightly towards balancing, with small-to-medium effect sizes (r = −0.36 to −0.50), but nothing is significant.
- Effects are small next to differences between groups: random-round Gini ranges 0.06–0.31.
- With 7 groups, significance needs a consistent effect in nearly every group (the smallest possible p is 0.008).
- Report it as "no reliable effect; a non-significant trend towards more even speaking, driven by a few groups (G02, G03, G05)".

## 5. H2: live speaker attribution

| | Value |
| --- | --- |
| **Overall** (speech-time weighted, primary set) | **0.836** → meets the 0.80 target |
| Per seat | seat 1 0.797, seat 2 0.888, seat 3 0.826 (side seats lower) |
| Per condition (mean of rounds) | random 0.86, balancing 0.82 |
| Per room | room 1 (G01) 0.96; room 2 (G02–G07) about 0.82 |
| Per round, lowest | G05 balancing round 0.58; all others 0.79–0.99 |
| Error types | correct 83.6 %, robot said "nobody" 14.9 %, **wrong seat 1.5 %** |
| Precision | when the robot named a speaker, it was right **98.3 %** of the time |

**What it means:**
- The live robot identified speakers reliably.
- Almost all misses are "nobody": it wasn't confident, or the speech flag was off. It rarely confused two people.
- G05's balancing round is the outlier, with low accuracy even when facing the middle. Possible causes are seating, posture or noise; mention it.

## 6. H3: our method vs the Micbot-style method (offline, same recordings)

**Fairness of the comparison.** The offline replay reproduced the live robot exactly: 100 % of ticks in every attempt, and all 46 live balancing decisions. Both methods saw identical sensor data.

**H3a: who is speaking** (mean per group)

| Group | Accuracy, ours / Micbot | Facing a side seat | Facing the middle | False speech in silence, ours / Micbot |
| --- | --- | --- | --- | --- |
| G01 | 0.955 / 0.753 | 0.959 / 0.787 | 0.944 / 0.665 | 0.67 / 0.17 |
| G02 | 0.830 / 0.717 | 0.851 / 0.668 | 0.814 / 0.764 | 0.27 / 0.13 |
| G03 | 0.850 / 0.715 | 0.882 / 0.712 | 0.814 / 0.710 | 0.38 / 0.18 |
| G04 | 0.799 / 0.611 | 0.783 / 0.591 | 0.818 / 0.627 | 0.32 / 0.12 |
| G05 | 0.737 / 0.601 | 0.806 / 0.597 | 0.640 / 0.510 | 0.36 / 0.14 |
| G06 | 0.861 / 0.706 | 0.930 / 0.733 | 0.776 / 0.666 | 0.35 / 0.14 |
| G07 | 0.823 / 0.637 | 0.855 / 0.668 | 0.772 / 0.585 | 0.31 / 0.15 |
| **Mean** | **0.837 / 0.677** | **0.867 / 0.680** | **0.797 / 0.647** | **0.38 / 0.15** |

- **Accuracy:** ours is better in **7/7 groups**, one-sided Wilcoxon **p = 0.008** (the smallest possible with 7 groups). **H3a supported.**
  - The gain is largest when facing a side seat (+0.19). There, front/back mirroring makes the naive rule credit the opposite side person to the middle seat, which is exactly what the HMM models.
  - Ours is also better facing the middle (+0.15), thanks to smoothing over time and the outlier model.
- **False speech (precision):** ours credits a seat in **38 %** of listening time where nobody was labelled, against 15 % for Micbot-style. That is worse in 7/7 groups (two-sided p = 0.016).
  - G01: 67 %, because that room's calibration made "no speech detected" no evidence of silence.
  - G02–G07: 33 %.
  - The trade-off: the HMM keeps a speaker "speaking" through short pauses. Its persistence and the speech flag's ~35 % false-alarm rate (in both rooms) make it fill silences, while the naive rule only counts flagged readings near a seat.

**H3b: whom to address** (84 decisions with labels; chance ≈ 0.33; the two methods chose the same person in 76 % of decisions)

| "Truly least active" defined as | Ours | Micbot-style | Only ours right / only Micbot right | Exact McNemar p (two-sided) |
| --- | --- | --- | --- | --- |
| Ours: turns, 120 s half-life | 0.67 | **0.79** | 4 / 14 | **0.031** |
| All speech in the last 120 s | 0.65 | 0.74 | 6 / 13 | 0.17 |
| Micbot's: all speech since the start | 0.64 | 0.75 | 5 / 14 | 0.064 |

**H3b not supported.** The Micbot-style rule picked the truly least active person more often under all three definitions, significantly under our own.

**What it means: better listening did not mean better choices.** Reasons for the discussion:
1. **False speech inflates scores.** Pauses after someone speaks are partly credited to them. Over a round this distorts the totals more than the Micbot rule's occasional seat confusions do, because the naive rule is *silent-biased*: it only counts flagged readings. Frame-level recall (H3a) improved; precision did not.
2. **Rounds were short** (about 3 min, 6 decisions), so recency weighting barely differs from a running total. Our method's design advantage had no room to show.
3. **Our method ignores utterances under 1 s and breaks ties** (within 0.5 s) by "addressed longest ago". Both sometimes override "lowest total".

**This is the central computational finding:** improving per-tick accuracy (H3a) is not the same as improving the downstream decision (H3b). The decision depends on how errors *accumulate*, and here false positives in silence accumulated worse than the baseline's seat confusions. Concrete fixes for future work:
- a better silence model, e.g. a lower `stay_speaking` or a higher confidence threshold during pauses;
- calibrating the speech flag in a quiet room;
- tuning parameters on decision quality rather than per-tick accuracy.

## 7. Mechanism: what happens after a question

| | Random | Balancing |
| --- | --- | --- |
| Questions with talk afterwards | 42 | 41 |
| Addressee's share of the following talk | 0.96 | 0.99 |
| Addressee spoke ≥ 1 s afterwards | 0.98 | 0.98 |

- **Being addressed works almost perfectly:** the person asked produced nearly all of the following talk. Figure: `complete_fig_addressee_share.png` (dashed line = chance, one third).
- But **how often someone was addressed did not predict their share of the round's speech** (Spearman ρ = 0.19, p = 0.23, 42 person-rounds). How long people answered mattered more.

**What it means:** the robot controls *who* speaks next, not *how much*. A policy that only counts questions has little leverage on evenness. Future policies could react to answer length, for example with follow-up questions to short answerers.

## 8. Validity of the robot's own estimate (and a warning)

- **Per person:** the robot's estimated share correlates well with the annotated share (Spearman ρ = 0.82, p < 0.001, mean absolute error 0.046; 42 person-rounds).
- **But its estimate "confirms" H1 when the ground truth does not:**

  | | Robot estimate | Annotated truth |
  | --- | --- | --- |
  | Groups more even with balancing | **6/7** | 4/7 |
  | One-sided Wilcoxon p | **0.039** | 0.23 |
  | Effect size r | −0.79 | −0.36 |

  - The robot judged random rounds less even than they were (+0.028 Gini on average) and balancing rounds more even (−0.031).
  - The robot-estimate figure belongs in the discussion or appendix only, clearly labelled.

**What it means:** **a system that evaluates itself with its own sensing reports success that independent ground truth does not support.** This justifies the hand annotation and is a strong methodological point.

A plausible cause (a hypothesis, untested): the robot faces the person it addressed, and false speech in pauses is credited to that person. In balancing rounds that is more often the quiet person, which inflates their estimate and makes the round look more even.

## 9. Questionnaire: perceived fairness

Fairness = mean of three items (share thoughts, fair chance, included), on a 1–5 scale.

| | Random | Balancing | Test |
| --- | --- | --- | --- |
| Per participant (n = 21) | 4.19 | 3.97 | W = 30.5, p = 0.16 (two-sided), r = −0.42 |
| Per group mean (n = 7, independent) | | | W = 5.5, p = 0.31, r = −0.48 |
| Group difference, order A (balancing second) | | −0.47 | n = 4 |
| Group difference, order B (balancing first) | | +0.11 | n = 3 |

- **No significant difference.** The small drop appears only when balancing came second, which points to a round, topic or fatigue effect rather than the robot.
- **Quiet members** (descriptive): fairness rose in 3/7 groups (G03, G05, G07) and fell in 4. Some rated fairness lower in the round where they spoke more (G04).
- **Per item and filler items:** use the workbook Results tab for means and SDs. The statistics come from the script; the workbook's p-value (0.167) differs slightly from the script's because of tie handling.
- **"Did you notice a difference?":** use the free text in the workbook Participants tab for a few quotes, e.g. "it asked me three times", "they ignored seat 2". Some participants noticed uneven addressing in balancing rounds, which may explain the slightly lower fairness.

## 10. Hypotheses at a glance

| Hypothesis | Result | Verdict |
| --- | --- | --- |
| H1: balancing lowers the Gini of speaking time | 4/7 groups, median −0.014, p = 0.23, r = −0.36 | **Not supported** (non-significant trend) |
| H2: live attribution ≥ 80 % of annotated speech | 0.836; 98 % precision when a seat is named | **Supported** (seat 1 at 0.797, one round at 0.58) |
| H3a: our attribution beats Micbot-style on the same data | 0.837 vs 0.677, 7/7 groups, p = 0.008 | **Supported** |
| (H3a) false speech in silence | 0.38 vs 0.15, worse in 7/7 groups | Weakness of our method |
| H3b: our decisions pick the least active more often | 0.64–0.67 vs 0.74–0.79; Micbot significantly better under our definition (p = 0.03) | **Not supported** (reverse tendency) |
| Fairness differs | 4.19 vs 3.97, p = 0.16 | No difference |

## 11. Discussion points (in order of importance)

1. **The method solved the problem it targeted** (H2, H3a). A head-aware HMM handles a microphone array that turns with the head and mirrors front/back. It beat the prior-work rule in every group, most clearly in the mirrored poses.
2. **It traded precision for recall, and the decision paid for it** (false speech, H3b). Per-tick accuracy is the wrong optimisation target for a decision that integrates speaking time over minutes. Discuss the fixes (section 6).
3. **No reliable behavioural effect** (H1), for four reasons:
   - a strong baseline (balanced random already equalises questions);
   - a weak manipulation (±1 question; none in 2 groups);
   - talk follows the addressee, but answer length decides evenness;
   - short rounds and n = 7.

   The secondary measures lean towards balancing (r ≈ −0.36 to −0.50), worth testing with longer sessions.
4. **Self-evaluation is misleading** (section 8): the robot's own estimate shows a significant effect; the ground truth does not.
5. **Relation to Micbot:** Micbot found no effect on speaking time, only on backchannels. We reach a similar behavioural conclusion with a stronger, verbal intervention. Our offline comparison also shows that Micbot's simple rule is a surprisingly robust decision rule, even though its attribution is worse.
6. **Future work:**
   - a silence-aware attribution model;
   - tuning on decision quality;
   - policies that use answer length;
   - more decisions per session;
   - a live Micbot condition;
   - a second annotator.

## 12. Limitations (with how much they matter)

| Limitation | Effect |
| --- | --- |
| n = 7 groups, ~3-min rounds, 6 decisions | Low power; only large, consistent effects are detectable |
| Weak manipulation (balanced baseline, ±1 question) | Limits H1 by design |
| Crashes and re-runs (20 attempts for 14 rounds); the robot's memory resets on a re-run | One attempt per round (all 6 questions); sensitivity check with all attempts gives the same results |
| Single annotator, not blind to condition | Supported by automatic checks (coverage, alignment with robot prompts); no kappa |
| Label edges imprecise | Small: a few points on H2, negligible for Gini; both methods judged on the same labels |
| Two rooms; room 1's calibration had poor speech-flag rates | G01 differs (H2 0.96 but false speech 0.67) |
| Topic tied to round; order 4/3 | Order pattern in fairness and quiet share |
| Laptop-microphone ground truth; overlaps excluded from H2 | Small |
| Code ran with uncommitted changes (`-dirty`) | Same version in every round; state it |

## 13. Figures and tables to use

| In the report | File | Notes |
| --- | --- | --- |
| **Fig: Gini per group** (H1) | `complete_fig_gini_pairs.png` | Main behavioural figure |
| **Table: ours vs Micbot** (H3a accuracy, side/middle, false speech; H3b three definitions) | section 6 tables | Main computational result |
| **Table: H2** (overall, per seat, error types) | section 5 | Can be merged with H3a |
| Fig: addressee share | `complete_fig_addressee_share.png` | Mechanism; optional |
| Manipulation check | section 3 | A sentence or small table |
| Fig: fairness | workbook Charts tab | Optional |
| Fig: robot-estimated Gini | `fig_robot_gini_pairs.png` | Discussion or appendix only, clearly labelled |
| Source tables | `complete_rounds.csv`, `complete_groups.csv`, `complete_decisions.csv`, `complete_h2_confusion.csv`, `h3_attribution.csv`, `h3_decisions.csv` | Every number traces back to these |
