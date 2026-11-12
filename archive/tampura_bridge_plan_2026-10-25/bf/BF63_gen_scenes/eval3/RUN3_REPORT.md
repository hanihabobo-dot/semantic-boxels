# BF#63's design, run 3: the 40 generated scenes with the BF#64 shadow fix

Cluster run of 2026-11-12, jobs 5248855 to 5248864. Report by worker A
(freeze) for the coordinator, written 2026-11-12 after 20:42 from the files
the coordinator pulled into this folder. No cluster access and no WSL run
went into it: every number comes from `<job>/results.jsonl`, `io_probe.tsv`,
the gate files and the job logs, read with Windows Python (and, for
`T_CRASHES.txt`, eight consoles out of the pulled tarballs). The declaration
it follows is in `tracks/meeting_2026-11-13/STATE.md`, "DECLARED BEFORE THE
RUN".

## The result

| | run 3 (tonight, ours from 51428d8) | run 2 (2026-11-04, ours from the tag d6a9715) |
|---|---|---|
| ours, counted runs | 69 of 80 = 0.86 [0.77, 0.92], 1 timeout | 57 of 80 = 0.71 [0.61, 0.80], 1 timeout |
| TAMPURA, counted runs | 46 of 76 = 0.61 [0.49, 0.71], no timeout, 4 not counted | 46 of 76 = 0.61 [0.49, 0.71], no timeout, 4 not counted |
| pairs, both arms counted | 76: both 40, only ours 25, only TAMPURA 6, neither 5; exact McNemar p = 0.00088 | 76: both 37, only ours 18, only TAMPURA 9, neither 12; p = 0.12 |
| each repetition alone (38 pairs) | 20 / 13 / 3 / 2, p = 0.021 and 20 / 12 / 3 / 3, p = 0.035 | 18 / 9 / 5 / 6, p = 0.42 and 19 / 9 / 4 / 6, p = 0.27 |
| a scene as the unit (38 scenes) | ours more in 13, TAMPURA more in 3, as many in 22; exact sign test p = 0.021 | 9, 5, 24; p = 0.42 |
| median wall of a success | ours 30.2 s, TAMPURA 103.4 s | ours 33.1 s, TAMPURA 111.7 s |

Brackets are Wilson 95 % intervals. In three sentences:

1. The fix does on the cluster what BF#64's local reruns said it would: the
   six scenes 102, 103, 107, 111, 118 and 127 turn from failures into
   successes in both repetitions, every scene solved in both repetitions
   before stays solved, and the six scenes that still fail are the ones BF#65
   explains by its causes (b) to (e).
2. TAMPURA, the same code as in run 2, ends every one of its 76 counted runs
   as it did in run 2, and crashes on the same two scenes. The whole
   difference between the two runs' tables is our arm's, in 8 scenes.
3. With the fix ours is ahead of TAMPURA on these 40 scenes (p about 0.02 to
   0.04 for one repetition). This is a check of the fix on the scenes the bug
   was found on and no fresh estimate; the measurement stays wave 2's 200
   fresh scenes.

## 1. What ran

- Approval: Hani, asked alone, about 17:00: "Yes, submit it".
- Code: a code-only snapshot of 51428d8 on `$W` (track/fixes: the tag
  d6a9715 plus TB-16 and TB-1, the BF#64 shadow fix). The job script, the
  harness and the gates are the tag's. TAMPURA's arm is the same code as in
  run 2.
- The same as run 2: scenes 100 to 139 from their own generator, 2
  repetitions, scenes the outer loop, TAMPURA then ours per scene on one
  node, the 900 s cap, BF#62's four switches (`metadata.json`: `arm_o`
  solver_iters+force_hold+pose_radius_keep+grasp_wrist_home), the validity
  rule, `--shots failures`, 10 jobs of 4 scenes, one per node, 8 CPUs and
  24 GB, `P4_LOCAL=1`, the same stall rule.
- Nodes: run 2's ten in run 2's order (cn-112, 111, 109, 115, 104, 103, 110,
  114, 113, 107; Xeon Platinum 8160).
- Times: submitted 17:02:46, the first episode ended 17:06:25, the last
  18:06:28. 164 episode runs, 160 final (arm, scene, repetition).
- Gates (`TABLES.txt`): every job's gates PASS before, the TAMPURA tree
  unchanged after, harness rc 0, GEN_DONE, in all ten jobs.

## 2. The harness report (`REPORT.txt`, as run 2 made it)

    arm   counted  success   rate    95 % Wilson timeouts not counted median wall s (successes)
    O          80       69   0.86 [0.77, 0.92]         1           0          30.8        30.2
    T          76       46   0.61 [0.49, 0.71]         0           4         142.7       103.4

    paired: 76 pairs; both succeed 40, only O 25, only T 6, neither 5; exact McNemar p = 0.000878
    left out of the pairs (an arm did not count twice): seed 127 rep 0 and 1, seed 138 rep 0 and 1

By cup count (`TABLES.txt`; successes of counted, ours against TAMPURA; pairs
both / only ours / only TAMPURA / neither):

    1 cup  (7 scenes)  14/14 vs 12/12   12 /  0 / 0 / 0
    2 cups (9 scenes)  16/18 vs 10/16    8 /  6 / 2 / 0
    3 cups (8 scenes)  12/16 vs 10/16    8 /  4 / 2 / 2
    4 cups (8 scenes)  16/16 vs  6/16    6 / 10 / 0 / 0
    5 cups (8 scenes)  11/16 vs  8/16    6 /  5 / 2 / 3

Our arm carried the die 69 times and lost it in the hand 0 times (the
pipeline's own noticed losses, see limit L2). TAMPURA's median time to
success on its own loop clock is 93.0 s. Failure screenshots: 49 runs kept
`failures/`, 98 images.

## 3. Ours here against ours in run 2 (the fix's effect; `COMPARE.txt`)

Per (scene, repetition), all 80 counted in both runs: success in both 56,
only in run 3 13, only in run 2 1, in neither 10; exact McNemar p = 0.0018.

- The 13 gained: scenes 102, 103, 107, 111, 118 and 127 in both repetitions,
  and 124 r0. Twelve were all_searched in run 2 and one planner_failed
  (103 r1).
- The 1 lost: 101 r1 (run 2 a success after 188 s, here planner_failed after
  60 s).
- No scene that run 2 solved in both repetitions fails here: 28 of 28 are
  solved in both again.
- A scene as the unit (its two repetitions are not independent): more
  successes in run 3 in 7 scenes, fewer in 1 (scene 101), as many in 32;
  exact sign test p = 0.07.

Of the 14 cells that differ, 12 are the six scenes BF#64's local reruns
turned into successes. The other two, 124 r0 (gained) and 101 r1 (lost), are
both scenes of BF#65's cause (e), whose loops hang on detections that shift
by millimetres between runs; under the tag 101 succeeded in 1 of its 4 runs
of run 1 and run 2. This run cannot say whether the fix plays a part in those
two cells.

Our failure classes, run 2 against run 3 (counted failures): all_searched 18
against 2, planner_failed 4 against 4, no_plan_binding_death 0 against 4,
timeout 1 against 1. The four no_plan_binding_death runs are scenes 128 and
135: all_searched in run 2, and with the shadow now registered they fail one
step later, as BF#65 (c) predicted.

## 4. TAMPURA here against TAMPURA in run 2 (run-to-run agreement)

Counted in both runs 76 of 80: success in both 46, only in one run 0, in
neither 30. Every counted run ends as it did in run 2, and within each run
both repetitions of a scene end the same way on 38 of 38 scenes. The four
runs that do not count are the same in both runs: scenes 127 and 138, both
repetitions, both attempts ("crashed: rc 1, no RolloutHistory").

Their code ran about 8 % faster tonight than in run 2 on the same nodes:
wall on the same (scene, repetition) 0.92 [0.90, 0.93] of run 2's, first
get_action 53.8 s against 58.6 s (medians).

## 5. Ours against TAMPURA, paired

By the declared validity rule the pairs are the 76 (scene, repetition) on
which both arms count: both 40, only ours 25, only TAMPURA 6, neither 5;
exact McNemar p = 0.00088 (run 2: 37 / 18 / 9 / 12, p = 0.12).

The two repetitions of a scene are close to one draw (TAMPURA's outcome is
the same in both on every scene, ours on 39 of 40), so the 76 pairs carry
about the information of 38 and the p over 76 pairs overstates the evidence.
BF#63 said the same of run 2. The fairer readings:

- each repetition alone (`REPS.txt`, 38 pairs): 20 / 13 / 3 / 2, p = 0.021;
  20 / 12 / 3 / 3, p = 0.035;
- a scene as the unit: ours more successes in 13 scenes, TAMPURA in 3, as
  many in 22; exact sign test p = 0.021.

On the 32 scenes in which our outcome is the same in both runs, the table is
the same in both runs to the cell (62 pairs: both 36, only ours 18, only
TAMPURA 4, neither 4). On the other 8 scenes (14 pairs) run 2 has 1 success
of ours against 6 of TAMPURA's, run 3 has 11 against 6.

The discordant cells, 25 to 6, are by chance the same two numbers as run 1's
(BF#63: 78 pairs, 30 / 25 / 6 / 17); the tables differ.

## 6. Failures

Ours, 11 counted failures in 6 scenes (`O_FAILURES.txt`), none with a die
carry:

| scene | repetitions | how it ends | BF#65's cause |
|---|---|---|---|
| 100 | both | all_searched; the die under b_cups_ud, which holds no shadow at the end | (b) the shadow seen empty before its cup is lifted |
| 101 | both | planner_failed; e's shadow still unknown | (e) the far cup, M8 and M9 |
| 104 | both | planner_failed; the die tilted 71 degrees, 6 px in view | (d) the die in view, but no look can see it |
| 124 | r1 only | the 900 s cap, four shadows still unknown | (e) the look and pick loop |
| 128 | both | no_plan_binding_death; b's shadow registered, unknown | (c) the plan through the shadow does not bind |
| 135 | both | no_plan_binding_death; c's shadow registered, unknown | (c) |

These are the outcomes BF#64's local reruns with the fix gave for the same
six scenes (its check 2), except that 124 r0 succeeds here.

TAMPURA, 30 counted failures in 15 scenes (100, 102, 104 to 108, 110, 116,
118, 124, 131, 132, 134, 139), none a timeout: all end below reward 1, most
after repeated looks at one object, 131 after repeated picks and 106 after
no-ops, as in run 2.

Not counted, 8 TAMPURA runs (the first run and its one repeat of 127 r0,
127 r1, 138 r0, 138 r1): rc 1, no RolloutHistory. The records show the same
picture as run 2's crashes on the same scenes: three get_action calls before
the crash on 127 (the last one `look(o_ph_2, o_ph_0, o_co_6)`), one on 138
(`look(o_ph_1, o_ph_0, o_co_2)`). All eight consoles, read out of the
coordinator's pulled tarballs, end on the line run 2's crashes ended on:
`ZeroDivisionError` in their `tampura/structs.py:257` (`ab_probs`, called
from `spec.py:98` `print_F`, called from `tampura_policy.py:147`
`get_action`); `T_CRASHES.txt` has each console from its Traceback to the
end. Ours succeeded on all four of these scene repetitions, so leaving them
out of the pairs, as the rule says, favours TAMPURA.

## 7. The stall rule (`IO.txt`, `eval2/bf63_io.py`)

The declared rule (two or more consecutive probe rows with the open on `$W`
at 1 s or more): **no stall, 0 of 76 pairs flagged.** The headline stands as
it is. The open on `$W` took a median 0.007 to 0.008 s and at most 0.030 s on
every node.

The check that is not the declared rule (any single row with the open or the
write at 1 s or more) does find something: the write with fsync on `$W`
stalled on all ten nodes at once at about 17:13:56 (5 to 10 s), 17:15:45 (1
to 5 s) and, on six nodes, between 17:18:46 and 17:19:54 (1 to 3 s). The
opens stayed fast and the episode folders are on the nodes' own disks
(`P4_LOCAL=1`). 27 of the 76 pairs overlap one of these rows. Without them:
49 pairs, both 27, only ours 13, only TAMPURA 4, neither 5, p = 0.049, the
same direction. No effect on an outcome is visible: TAMPURA ends all 76 runs
as in run 2, and its walls are a steady 0.92 of run 2's.

## 8. The coordinator's headline counts against these

| the coordinator's count | here | |
|---|---|---|
| ours 69 of 80 | 69 of 80 | equal |
| ours now against run 2: both 56, only now 13, only run 2 one (101 r1), neither 10 | the same | equal |
| the 13 are scenes 102, 103, 107, 111, 118, 127 (both) and 124 r0 | the same | equal |
| our 11 failures: 100, 101, 104, 128, 135 (both) and 124 r1 (the timeout) | the same | equal |
| TAMPURA 46 of 80 | 46 successes of **76 counted** | differs in the base |
| TAMPURA against run 2: both 46, neither 34 | of 76 counted in both: both 46, neither 30; 4 not counted in either run | equal once the 4 are named |
| ours against TAMPURA: both 40, only ours 29, only TAMPURA 6, neither 5 | 76 pairs: both 40, **only ours 25**, only TAMPURA 6, neither 5 | differs by the 4 |
| mean wall ours 52 s (run 2 63 s), TAMPURA 183 s (204 s) | 52.2 (63.0), 182.9 (203.6) over all 80 last attempts | equal |

The one difference: "46 of 80" and "only ours 29" count the four TAMPURA
runs that did not count (127 and 138, crashed on both attempts) as TAMPURA
failures. The validity rule declared for this run takes them out of the
pairs, as in run 2, which gives 46 of 76 and 25 to 6. Both counts are in
`COMPARE.txt`; over all 80 with a crash as no success the p is 0.00012. For
the meeting: TAMPURA 46 of 76 (0.61), pairs 25 to 6.

On the mean wall: the drop of ours from 63 s to 52 s is no speed-up of the
code. Two cells that failed late in run 2 and succeed early here (103 r1 from
400 s to 53 s, 124 r0 from 780 s to 52 s) account for more than the whole
drop, and tonight's nodes were about 8 % faster for both arms (section 4;
ours 0.93 per planning call on the same scene and repetition).

## 9. Limits

Declared before the run:

- L1. The fix was found on these 40 scenes. This run checks the fix where
  the bug was seen and is no fresh estimate; wave 2's 200 fresh scenes
  (seeds 140 to 339) stay the measurement.
- L2. No rule 18 fields: no record holds `drops`, `collisions` or
  `clean_success` (checked in every record). "0 of 69 carries lost" is the
  pipeline's own noticed losses.
- L3. Each arm is scored by its own end test: TAMPURA by its reward 1.0 on
  its belief with a kinematic carry, ours by the bridge outcome and the
  pipeline's goal check in the physics world.
- L4. Hani's rule 15 look at find_dice (ours against TAMPURA) is not on
  record; the run came before it, like run 2.
- L5. Not pooled with run 2.
- L6. The two repetitions of a scene are not independent (the 13 gained
  cells are 7 scenes).

Seen in the data:

- S1. The repetitions are close to one draw for both arms, so the p over 76
  pairs overstates the evidence; one repetition or a scene as the unit gives
  p = 0.021 to 0.035 (section 5).
- S2. TAMPURA's side of the table is the same as run 2's to the cell. The
  comparison moved because our arm moved, in 8 scenes.
- S3. Two of the 14 changed cells (124 r0 gained, 101 r1 lost) lie outside
  the fix's six scenes and cannot be attributed (section 3).
- S4. With a scene as the unit the fix's own effect is 7 scenes up and 1
  down, p = 0.07: the count of scenes is small.
- S5. Single-row write stalls on the shared volume at three moments, which
  the declared rule does not flag; no effect on an outcome is visible
  (section 7).
- S6. Walls of run 2 and run 3 differ by about 8 % on the same code and
  nodes, so walls are compared within a run only.
- S7. Leaving the four crashed TAMPURA scene repetitions out of the pairs
  favours TAMPURA (section 6).

## 10. Open, and not done here

- The tarballs on `$W` and the pull in the coordinator's scratchpad: the
  coordinator's to keep or delete. This report read eight console files out
  of the pulled tarballs of jobs 5248861 and 5248864 (read only, for
  `T_CRASHES.txt`) and needs nothing more from them.
- The job folders `eval3/5248855` to `5248864` and `jobs_bf64_run3.txt`
  were pulled by the coordinator and are untracked; this report's commit
  holds only the files listed below.
- `PAPER_AUDIT.txt`: not edited. The draft entry is
  `PAPER_AUDIT_DRAFT.txt`, numbered BF#71, which no file and no local branch
  uses (searched between 20:36 and 20:42: the checkout's working tree and
  all 32 local branches; the highest number in use is BF#70).

## 11. Files in this folder

| file | made with |
|---|---|
| `REPORT.txt` | `tools/gen_scene_eval.py --report <eval3>` |
| `TABLES.txt` | `../eval/bf63_tables.py <eval3> 52488*` |
| `REPS.txt` | `../eval/bf63_reps.py <eval3> 52488*` |
| `O_FAILURES.txt` | `../eval/bf63_why_o.py <eval3> 52488*` |
| `IO.txt` | `../eval2/bf63_io.py <eval3> 52488*` |
| `T_CRASHES.txt` | the eight crashed TAMPURA consoles from Traceback to the end, out of the pulled tarballs of jobs 5248861 and 5248864 |
| `COMPARE.txt` | `bf63_run3.py <eval2> <eval3>` (new, in this folder) |
| `bf63_run3.py` | run 3 beside run 2: the per-cell and per-scene tables, the pairs, the failure classes, walls and speed |
| `RUN3_REPORT.md` | this report |
| `PAPER_AUDIT_DRAFT.txt` | the draft of the audit entry |

Each script ran as `C:\Python312\python.exe -I -X utf8 -B <script> <args>`
from the trunk checkout; `tools/gen_scene_eval.py` is the same blob on the
trunk, in 51428d8 and at the tag.
