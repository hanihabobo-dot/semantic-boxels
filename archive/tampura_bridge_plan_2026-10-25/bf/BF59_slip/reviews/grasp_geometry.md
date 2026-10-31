# BF#59 review: grasp_geometry

Adversarial review of proposals/grasp_geometry.md (phase 4), written
2026-10-31 at d021dad by the reviewer of this angle. Read: BRIEF.md,
STATE.md, REVIEW_BRIEF.md, the four proposals (hold_physics.md re-read at
16:51 with its sections 1 to 4), the code named below, every json and log
under probes/grasp_geometry/, evidence/tc_4912db9_grip_lines.txt, their
env_generator.py (read only). One probe re-run (section 4). Numbers are
counts with Wilson 95 % intervals in brackets.

## 0. Verdicts

| fix | mechanism supported | rules | detectable | own-scene risk | effort h | verdict |
|---|---|---|---|---|---|---|
| edge_pinch | in part: a yaw band beyond about 6 deg is in all three probes; the sub-degree band and the symmetric +-12 deg edge band are not | rule 2 fails (the 25 mm scope selects the die and nothing else); 1, 3, 4, 5 pass | no: its ceiling is about 13 % per carry, the eval needs at most 4 to 5 losses in 60 | with the scope: none on our scenes, but it also re-grasps the dice that hold today (one eval scene holds 48 of 48); without the scope: our cubes and the cups get worse | 2.5 | drop |
| face_needs_wrist_yaw | no: its target, the exact face pinch, holds 79 % in its own probe, which is base's hold rate in the eval | rule 2 as edge_pinch; 1, 3, 4, 5 pass | no | the die gets the cup loop: an overhead refresh re-fuses the eye's yaw and the pick is refused until the cap | 3 to 4 | drop |
| pinch_band_certificate | no: its band table is a property of the 0.5 mm position hold and today's carry, which force_hold and the carry_motion pair remove, and two other probes disagree with its face band | 1, 3, 4, 5 pass; rule 2 passes in form (a per-detection yaw noise, no size) | not as a loss arm | observes on our scenes wherever the per-detection noise is pessimistic; round bodies (cups) have no faces and need their own exclusion | 10 to 14 | drop |

## 1. Per fix

### edge_pinch

**1. Mechanism.**

What was measured (probe_grasp_geometry.py, physics only, their empty
table, their Panda, their die resting on the table, the pipeline's own
pick, close, lift and carry; command in the proposal's 1.3). I recomputed
every pooled number of the proposal's table (b) from the json files:

- Single carry: exact face (0 to 0.5 deg) 21/24 (88 %), near face (1 to
  25 deg) 57/124 (46 %), edge (30 to 57 deg) 154/164 (94 %). These match
  sweep_yaw + sweep_fine_small, and sweep_yaw + sweep_edge_band +
  die_edge_sized + the three cell2 files.
- Pipeline carry: exact 46/58 (79 % [67, 88]), near 63/124 (51 % [42, 59]),
  edge 148/184 (80 % [74, 86]). Small mismatch: the exact count leaves out
  pipecarry_cell2's 1/2 while near and edge include that file (47/60 if
  included). Immaterial.

What the numbers say against the proposal's reading:

(a) The edge pinch equals the exact face pinch under the pipeline carry
(80 % against 79 %). It gains only over the near-face class, so its whole
value depends on how many eval picks sit in that class, and on the shape
of the near-face band. Both are weaker than the proposal says.

(b) The sub-degree face band is this probe's alone. hold_physics' probe
(base, line carry, 113 grips, item 12) loses 3 of 33 dice at 0 to 3 deg
and 2 of 30 at 3 to 6 deg, 15 of 50 at 6 to 10 deg. carry_motion's probe
(wrap + pipe, 92 carries per cell) holds 85/92 (92 %) at 3 deg and 54/92
(59 %) at 10 deg. This probe holds 19/32 (59 %) at 3 deg and 19/32 at
6 deg under the pipeline carry. Two of the campaign's three probes find
the 0 to 6 deg range holding about 90 %; the band starts near 6 to 10 deg,
not at 1 deg. The probes differ in the hand yaw (this one fixes it at 0,
30, 6.6 deg, so joint 7 starts near its limit and the carry unwinds about
200 deg), the die's placement (here dynamic, resting) and the pre-grasp
aperture (here fixed per delta). The discrepancy is not explained, and the
proposal does not mention it.

(c) Inside this probe the near-face loss is partly the close's stopping
step, not the yaw. The close advances 0.5 mm per step and records the
width when both pads first report contact within 0.5 mm
(robot_utils.py 1164 to 1191); the hold target is that reading minus
0.5 mm. A reading that comes one step later is narrower and the hold digs
deeper. Within the same delta (1 to 4 deg): readings under 10.15 mm hold
0/17 [0, 18] (single, close force median 4.35 N) against 37/55
[54, 78] for the other readings (2.56 N); pipeline 5/16 [14, 56] (3.88 N)
against 29/44 [51, 78] (2.90 N). The narrow readings occur only at 1 to
4 deg in the single sweeps and only at 1 and 2 deg in the pipeline sweeps,
none at 0, 0.2, 0.5, 3 (pipeline) or 6 deg. So "one degree off loses half
the carries" mixes yaw with squeeze depth; without the narrow rows the
1 to 4 deg class holds about two thirds. That is hold_physics' mechanism
(item 2 and 3 of its 1.1: the hold's force is set by where the close
stopped, and a firmer grip is expelled at 50 solver iterations).

(d) The eval's width bins carry the same confound and a duplicate.
evidence/tc_4912db9_grip_lines.txt, 144 scored picks: under 10.15 mm 11/21
failed, 10.15 to 10.45 mm 14/94, 10.45 to 10.75 mm 6/24, 10.75 mm or more
0/5 (as the proposal says). But the close force rises as the reading
narrows (median 4.19 / 3.07 / 1.75 / 1.55 N over the four bins), the
signature of (c), and 48 of the 94 middle-bin rows are one identical pick
(10.2 mm read, 8.2 to 8.3 mm expected, 3.07 to 3.32 N, all held) from
seeds 0, 7, 9, 11, 12, 13, 16 and 23 across the 8 arms: apparently one
scene that always holds. Without those 48: middle bin 14/46 (30 % [19, 45])
failed, and by force under 2 N 7/28, 2 to 3 N 6/30, 3 to 4 N 7/18, 4 N or
more 11/20 (55 % [34, 74]). The narrow bin is better explained as the
close stopping deep (high force) than as dice 1 to 2 deg off: a die off
its face is wider across the pads, never narrower (hold_physics item 6:
support 8.78 mm at 0 deg, 10.01 at 15). The 0.5 mm stepping spreads the
reading of one die over about 0.5 mm in the eval, where the aperture
(pinch half + pose radius + 8 mm) varies per pick; the bins are 0.3 mm
wide and cannot resolve a yaw under about 10 deg.

(e) The edge band is not symmetric under the pipeline carry. The proposal
says the eye certifies an edge pinch because "the band is +-12 deg"; that
is the single carry (33 to 57 deg: 13/14 each). Under the pipeline carry,
pooled over hand yaws 0 and 30 (pipecarry_main, pipecarry_hy30, cell2) and
my re-run at hand yaw -15 (section 4: 35 deg 10/16, 45 deg 14/16, 55 deg
15/16): 35 deg 28/48 (58 % [44, 71]), 45 deg 39/48 (81 % [68, 90]),
55 deg 44/48 (92 % [80, 97]); edge2 38 to 42 deg 31/42, 48 to 52 deg 37/42.
One side of the band holds no better than the near face (51 %). This is
the sign effect of the wrist spin carry_motion measured (batches 3 and 4).
With the eye's yaw error (p95 9.475 deg, YAW_NOISE pose_belief.py 34, and
the deadband that stores any eye yaw under it as 0, pose_belief.py 274),
a random-yaw die lands anywhere in 35 to 55 deg, half of them on the weak
side.

(f) The episodes. Three headless runs with the edge pinch patched in
(run_edge_pinch_episode.py, the margin-based scope, not the proposed 25 mm
scope): seed 0 held; laptop seeds 1 and 2 (one scene, 1747173590) lost the
die on the move home, both at a measured 12.3 mm (the edge geometry was
achieved). 1 of 3 carries held [6, 79]. The probe at that cell held 9/10;
the proposal names the contradiction and leaves it open.

(g) The ceiling on the eval. The eval's informative carries are the 96
picks outside the duplicate scene, 31 lost (32 %). If every one of them
became an edge pinch holding at the probe's 80 %, the loss falls to 19 of
96 and, with the 48 that hold anyway, to about 13 % per carry. That is the
optimistic bound. Against it: the edge pinch also replaces the face pinch
of the dice that hold today. A die placed under a cup gets yaw 0
(env_generator.py 126 to 127, `pbu.Pose(cup_pose[0])`), the eye reads 0,
the edge grasp is at -45 deg, and that pick moves from the exact face
class (the duplicate scene: 48 of 48 held) to the 45 deg edge (81 % in the
pipeline probe). The net effect can be zero or negative.

Confounds: one laptop world, an empty table, no cups; the probe's carry is
a straight 10-waypoint line from the lift pose (the eval's carries are
re-solved 9-pair paths at the velocity limit, loss_dynamics 1.2, close
enough); a physics-only probe is deterministic, so its sample size is the
number of distinct cells and deltas, 7 cells x 2 face pairs, and repeated
deltas on the same cells are correlated (the edge losses cluster by cell:
(0.42, -0.10) at hand yaw 30 loses at carry step 2 to 3 for every delta,
(0.38, 0.12) at step 61 to 63). The per-cell clustering makes the
effective n smaller than the Wilson intervals assume.

Numbers that do not match their source:
- "the narrow and wide width bins (about 30 of the 144 scored picks, 17
  failures)": the bins under 10.15 mm and 10.45 to 10.75 mm hold 45 picks
  with 17 failures (50 with the bin over 10.75 mm).
- "sized_pinch_half along the diagonal, 12.4 mm" and "margin from 4.4 to
  6.2 mm": the episodes' own sizing read "I expected 11.1 mm" (seeds 0
  and 1) and 11.2 mm (seed 2): the fitted extents are about 15.7 mm, not
  17.5, so the span is 22.2 mm and the margin min(40 - 11.1 - 2,
  0.5 x 11.1) = 5.6 mm. The hull's real support at 45 deg is 10.93 mm
  (hold_physics item 6); the measured 12.3 to 12.6 mm is that plus the
  1.1 mm finger geometry and up to 0.5 mm of contact tolerance.
- "The eye's yaw belief can certify an edge pinch (the band is +-12 deg)":
  true for the single carry only, see (e).

**2. Rules.**

- Rule 1 (model side): passes. The grasp family the sampler offers
  (pose_belief.fitted_grasp_candidates 177), read by sample_grasp
  (streams.py 836 to 839), believed_margin and pose_known (209 to 237),
  execute_pick's sizing (execution.py 1054 to 1057). No plan is edited.
- Rule 2 (no bridge-only tuning): fails as written. The orchestrator's
  question first: is the 25 mm scope "the die" in disguise? Yes. The bound
  sits in the gap between the die (17.6 mm) and the smallest class of
  every scene the pipeline runs (targets 30 to 40 mm, occluders 50 to
  60 mm, the cups 51 to 70 mm); in find_dice and in our scenes it selects
  exactly one body class, and no measured mechanism changes at 25 mm. The
  proposal's reason (our 40 mm cube's edge pinch holds 3/7 under the
  pipeline carry, [16, 75]) is a reason to exclude the cube, not a reason
  for a size; it rests on 7 grips at one hand yaw (21/21 single carry).
  - A scope derived from the mechanism the proposal itself names would be
    the yaw belief's quality, not the size: the edge pinch where the yaw
    noise of the detection that set the yaw exceeds the face pinch's band.
    The eye's 9.475 deg is a property of the die's 30-pixel top face
    (BF#29: our boxes at hundreds of pixels read 0.007 deg), so a
    per-detection noise from the top-face pixel count selects the die
    for the right reason and leaves our cubes (exact yaw) on the face
    pinch. The rounded vertical edges (radius about 3 mm, hold_physics
    item 6) and the pad width are real parts of why the edge seats, but
    the belief cannot see an edge radius (the eye fits rectangles), so
    they cannot gate a rule. The squeeze gives a bound only under a force
    hold: a roll from edge to face narrows a sharp cube by
    (s/2)(sqrt 2 - 1) per side, which force_hold's 4 mm reach follows for
    s up to 19 mm and today's 0.5 mm hold follows for s up to 2.4 mm, so
    the squeeze argues against the edge pinch at every size under today's
    hold. A round footprint (a cup) has no edges and no faces; its fitted
    square's yaw is arbitrary (aabb_half_along's docstring, BF#46), so a
    mechanism-derived rule must also exclude round footprints, for example
    by how much of its fitted rectangle the segmentation fills (a square
    about 1, a disc 0.785). That rule is pinch_band_certificate's
    machinery.
  - Without the scope: our 40 mm cubes stand at yaw 0, where the eye is
    exact (BF#29 (b)); today they get the exact face pinch (pipeline 14/14,
    single 14/14 at 0 and 3 deg in this probe; hold_physics 0/19 lost
    within 3 deg). The edge rule would give them a 56.6 mm diagonal pinch
    that held 3/7 under the pipeline carry: worse, rule 2 broken. The
    cups get a square-root-of-two span on a round body (51 mm cup to
    72 mm), the commit margin falls to about 2 mm, and the seed-0 episode
    shows the cost (one refused pick, one more observe, 5 plans instead
    of 3); seed 2's 50 refused cup picks (108 plans) came from the
    margin-based scope letting the 38 and 42 mm cup tops through. The
    60 mm occluders' diagonal (85 mm) exceeds GRASP_MAX_SPAN 0.076 and the
    probe patch falls back to the face; the 50 mm ones get a 70.7 mm span
    and a 2.6 mm margin, so more observes.
- Rule 3: passes. Only the belief's fitted yaw and extents are read; no
  pybullet read, no allowlist line.
- Rule 4: one switch `edge_pinch`, registered at pose_belief's import
  (pose_belief.py is pure numpy; slip_fixes.py is plain Python, so the
  import is safe). The proposal does not say where it registers; it must
  not go into pose_belief.SWITCHES (the M8 to M10 dictionary).
- Rule 5: the proposal's prose has no em dash and none of the banned
  words (checked). Plain voice.
- Rules 6 and 7: no tracked file changed. Section 4's list matches the
  folder: 10,794,926 B in the folder against the stated 10.75 MB
  (within rounding); every file listed; the two deletions stated. The
  ledger rows are left to the orchestrator as the brief says.

**3. Testability and power.**

Metric: loss per die carry. With 3 reps x 20 seeds, about 60 die carries
per arm (fewer: 174 of 192 eval episodes reached the die) and base at
21 %, a Fisher test at 5 % two-sided needs the fix arm at 4 losses or
fewer in 60 (6.7 %) against base's 13/60, or 5 or fewer (8.3 %) if base is
pooled over four jobs (about 240 carries). Power for a true rate of 12 %
is 0.19 to 0.29, for 7 % 0.51 to 0.74. The proposal's own estimate (15 %)
and the ceiling of (g) (13 %) are below the eval's resolution; its
"convincing only if it falls below about 12 %" is optimistic: an observed
12 % is not significant either. About 21 of the 60 carries per arm come
from the scene of (d) that never loses, which a fix cannot improve and can
only make worse.

Falsifier as proposed (the measured half-width at 12 mm or more, and no
gain): sound as an implementation check. For a null to be informative the
switch must log per die carry: the family chosen (face or edge), the grasp
yaw minus the fitted yaw, the camera that set the yaw, the measured
half-width, the close force, and loss_dynamics' carry_grip line. Then the
eval's own arms give the loss by realised family and by the 35 deg and
55 deg sides of the band.

**4. Risk.**

- Our own scenes: none with the scope (no class at or under 25 mm); the
  proposal did not run one. Without the scope, worse (rule 2 above).
- The eval's scenes: the dice that hold today are re-grasped too, see (g).
- The bridge gates: no new pybullet write, no read of the executing world.
- The pick: the pre-grasp aperture grows from about 16 to 18 mm to about
  19.5 to 20.5 mm per finger (sized_pinch_half 11.1 mm + pose radius +
  8 mm, execution.py 1132) and the open fingers turn 45 deg: the descent
  sweeps 3 to 4 mm wider near cups set down at free spots. Unmeasured; M10
  sees a touch. The width plausibility (execution.py 1280: 5 mm to
  pinch half + 8 mm, about 19 mm) passes a 12.3 to 12.6 mm reading.
- The kin stream: it still certifies what it certified, no more. The
  contact target (streams.py 1375 to 1401) is the boxel centre plus the
  grasp xy at max(top - 5 mm, the floor), independent of the yaw; the IK
  runs at the new orientation. It never certified where the pads land,
  and with the edge grasp the model's span (11.1 to 12.4 mm, the sharp
  rectangle) overstates the body's 10.93 mm, which only widens the
  aperture and the plausibility bound; nothing rejects. The pick floor is
  unchanged (13.2 mm; contact height did not separate at 45 deg: 10, 10
  and 8 of 10 at 13.2, 15 and 16.5 mm). M9's AABB side (BF#46,
  aabb_half_along) at a 45 deg pad direction is a tie that takes x; for a
  die near yaw 0 it is below the fitted diagonal, so the fitted span wins;
  the max never rejects.
- The wrist spin: the edge yaw is the face yaw plus or minus 45 deg, so
  joint 7's carry travel changes by up to 45 deg either way: shorter for a
  die at fitted yaw 0 (edge yaw -45 deg, roughly 182 to 140 deg of unwind
  by carry_motion's joint 7 numbers), longer for seeds 1 and 2 (fitted
  -38.4 deg, edge yaw 6.6 deg, joint 7 near its -2.897 limit, about
  210 deg). See section 2 for the worst-case question.
- The time budget: no extra plan or action with the scope (the margin
  grows); without it the cup refusals of (f).

**5. Effort.** The proposal's 2 h is right for the function, the switch
and two tests in tests/test_m9_grasp.py (exists, 9 tests); add 0.5 h for
the per-carry log line of 3. Line numbers checked at d021dad: pose_belief
177, 209 to 237, 274; streams 836 to 839, 1375 to 1401; execution 1054 to
1057, 1132, 1280. All correct.

**6. Verdict: drop.** The gain is bounded by the near-face share of the
eval's picks and sits below what 60 carries per arm can resolve, while the
fix also re-grasps the dice that hold today (one scene, 48 of 48) into a
45 deg edge that holds 81 % in the probe, and one side of its band (35 deg,
58 %) is no better than the near face it replaces. The 25 mm scope selects
the die and nothing else, so it fails rule 2 as written; if a yaw-aware
family is ever needed it should come through a per-detection yaw noise
(pinch_band_certificate's form) after force_hold has been measured.

### face_needs_wrist_yaw

**1. Mechanism.** It targets the same band from the other side: make every
die pick an exact face pinch by requiring the wrist camera's yaw
(YAW_NOISE wrist 0.202 deg) before the commit. The class it produces holds
79 % [67, 88] in the pipeline probe and 88 % in the single carry. Base in
the eval holds 79 % per carry. By its own probe the fix moves the eval's
mix to the rate the eval already has; by hold_physics' and carry_motion's
probes the 0 to 6 deg picks it would correct already hold about 90 %, and
only the picks beyond about 6 deg gain. Measured: nothing of this fix
(no episode with it, no probe of the wrist look). Inferred: the gain is a
few points at most.

**2. Rules.** Rule 1 passes (the belief's commit rule, M8's observe).
Rule 2: the same 25 mm scope and the same failure as edge_pinch; with a
per-detection yaw noise instead of the size it would pass. Rule 3 passes.
Rule 4: one switch; the change needs `_fuse` (pose_belief.py 250 to 279)
to record which camera produced the yaw, which it does not today. Rule 5
passes.

**3. Testability.** Below the eval's resolution for the reasons of
edge_pinch (it needs 4 to 5 losses in 60). Falsifier as proposed (the
readings after the wrist look in 10.15 to 10.45 mm) does not hold up: the
reading spreads over about 0.5 mm by the close's stopping step whatever
the yaw (edge_pinch 1 (c), (d)), so it cannot certify the exact class.
Better: log the yaw's camera and the grasp yaw minus the wrist yaw.

**4. Risk.** The orchestrator's question: how many picks per episode would
it refuse, and does it feed the cup loop? The die is picked once per
episode (loss_dynamics 1.6: one firm grip on the die in every one of the
31 loss episodes). At plan time the planner reads pose_known
(pddlstream_planner.py 721 to 762, 910, 1019) and plans the observe
first, so the rule adds one observe per die pick (0.6 to 1.2 s in the
episode logs) and usually one plan (2.4 to 6 s on the laptop), not a
refusal. The refusal comes at the dispatcher's commit check
(test_full_pipeline.py 2103 to 2111), and the path to it is the cup
loop's: after the observe, the move over the die runs `_integrity_after`,
whose overhead refresh calls record_detection (execution.py
refresh_object_aabbs, loss_dynamics 1.6); a complete eye detection of the
die re-fuses its yaw (`_fuse` takes "yaw = latest", pose_belief.py 277),
the yaw's camera becomes the eye, pose_known turns false, the pick is
refused, the planner observes again. The episodes show the overhead seeing
the die complete at 184 to 191 px; whether it does with the hand 10 cm
above it is not measured. If it does, every die pick loops until the
600 s cap, on the target itself: the slow tail of seeds 5, 10, 17 and 19
(plan_calls up to 80 and 90) moved onto the die. The proposal's change
has no rule that keeps a wrist yaw against a consistent eye detection.
Our scenes: none by the scope.

**5. Effort.** 2 h claimed; 3 to 4 h with the camera record in `_fuse`,
the keep rule for a wrist yaw (pose_radius_keep's intersection rule
extended to the yaw source), and a test of the observe, refresh, pick
sequence.

**6. Verdict: drop.** The exact face pinch it guarantees holds no better
in its own probe than base does in the eval, so there is nothing for the
eval to measure. As designed it also opens the die to the overhead
refresh loop that costs the cups their slow tail.

### pinch_band_certificate

**1. Mechanism.** A grasp should be yielded only when the belief's yaw
interval lies inside the family's holding band and the pose radius inside
its lateral tolerance; the bands come from this probe (face |delta| <=
0.5 deg, edge |delta - 45| <= 10 deg, lateral 1 / 2 mm). The bands are not
robust: the face band is contradicted by hold_physics (0 to 6 deg: 5 of 63
lost) and carry_motion (3 deg: 7 of 92 lost), and part of this probe's
own band is the close's stopping step (edge_pinch 1 (c)); the edge band is
asymmetric under the pipeline carry (35 deg 58 %, 55 deg 92 %). More
important: the band is a property of today's hold and carry. Under
force_hold with finger_gear and solver_iters the die loses 0 of 113 at
yaw offsets of 0 to 10 deg and the 40 mm cubes 0 of 57 (hold_physics
1.1 item 6, 8); under grasp_wrist_home with carry_trapezoid it holds
96/96 at 3 deg and 95/96 at 10 deg (carry_motion 1.2). A certificate
calibrated today would refuse grasps that hold once either of those lands.

**2. Rules.** Rule 1 passes (the stream's certificate, the belief). Rule 2
passes in form: a per-detection yaw noise from the top-face pixel count
is pipeline-wide and needs no size scope. It still needs a round-footprint
exclusion (cups have no faces) that the proposal does not name. Rules 3 to
5 pass (perception's own outputs; no pybullet read).

**3. Testability.** Not as a loss arm: it changes the loss only through
the families of the other two fixes. Its proposed falsifier ("the share of
certified grasps that hold must reach the band's rate, about 80 %") is
already met by base (79 %).

**4. Risk.** Every body whose per-detection noise exceeds 0.5 deg needs a
wrist look before a face pinch: our cubes pass (0.007 deg) if the
per-detection noise is calibrated right, and any pessimism turns into
observes and plans on every random-pairs scene. The cup refusals and the
refresh loop of face_needs_wrist_yaw apply to every certified body.

**5. Effort.** 6 to 8 h claimed; 10 to 14 h realistic: the per-detection
yaw noise needs its own calibration against pixel count (BF#29's
tools/_calib_pose_noise.py), the band table per family, the round
footprint test, the stream change (no grasp yielded, M8 plans an observe),
tests in tests/test_m9_grasp.py and tests/test_pose_writers.py, and a
random-pairs check of commit timing.

**6. Verdict: drop.** It is the right form for a yaw-aware grasp rule (no
size, the belief's own noise), and the effort is not justified next to
two fixes in other angles that remove the band it would certify. It
should not be the only one implemented either; revisit only if the eval
shows a yaw dependence of the loss under force_hold.

## 2. Cross-proposal conflicts and combinations

- One symptom, four stories. The yaw band that all three fixes address is
  the same observation that hold_physics explains by the 0.5 mm position
  hold (its force collapses to 0 N when the die turns, item 2) and the
  50-iteration solver (item 3), that carry_motion explains by the wrist
  unwind walking an off-face die (1.2), and that loss_dynamics times at
  the waypoint junctions (1.3). force_hold (with finger_gear and
  solver_iters) removes it in the probe at 0 to 10 deg; grasp_wrist_home
  with carry_trapezoid removes it at 0 to 10 deg and cuts the loss at 20 deg from 84 to
  15 %.
  grasp_geometry's fixes avoid it by grasp choice and are the weakest of
  the three routes.
- edge_pinch under force_hold: redundant in the measured range, untested
  at 45 deg. hold_physics' draws are yaw offsets of +-10 deg (hp_probe.py
  205 to 206); no edge pinch was run. A roll from edge to face under
  force_hold's 4 mm reach would be followed (the hull narrows by 2.15 mm
  per side), so I expect it neutral, not harmful; that is an inference.
  force_hold's target (measured width - 4 mm, 8.3 to 8.6 mm at an edge)
  sits inside the face touch (q 9.88 mm), so the pads keep pressing after
  such a roll.
- edge_pinch and the wrist spin. The orchestrator asked whether a 45 deg
  offset is the worst case for carry_motion's mechanism. carry_motion's
  data says no: at delta 45 today's grasp and stream hold 84/92 (91 %),
  the worst cells are 10 and 20 deg (59 %, 16 %); under carry_trapezoid
  the edge holds 92/92 (wrap) and 96/96 (flip). But the realised edge
  pinch is not at 45: the eye's error puts it at 35 to 55 deg, and the
  35 deg side holds 58 % under today's stream at three hand yaws (my
  re-run included), which is the spin-sign effect. edge_pinch with
  grasp_wrist_home and today's stream is worse than with today's grasp
  (79/96 against 84/92); edge_pinch with carry_trapezoid alone (no flip)
  is carry_motion's best edge cell (92/92), but untested at 35 and 55 deg.
- face_needs_wrist_yaw needs pose_radius_keep and a yaw-keep rule of the
  same kind; it is a no-op with edge_pinch on; pinch_band_certificate
  subsumes both.
- edge_pinch and carry_grip_watch: the edge pinch reads 12.3 to 12.6 mm;
  the watch's threshold is relative, so it carries over, but its 0.05 mm
  value was measured on face pinches and must be re-measured under any
  hold change (hold_physics 2.3 says the same for force_hold).
- Order of implementation, one mechanism per arm: (1) force_hold with
  finger_gear and solver_iters, and pad_rolling as its own arm; (2)
  grasp_wrist_home with carry_trapezoid, run with pose_radius_keep on;
  (3) pose_radius_keep alone and carry_hold_check alone (they change the
  outcome and the time, not the loss per carry). None of grasp_geometry's
  three in the first eval round. If the force_hold arm still shows a loss
  that depends on the logged yaw class, re-probe edge_pinch under it at
  35 to 55 deg with a per-detection scope before giving it an arm.

## 3. Missed, and what to check first

Missed by the proposal:
1. The close's stopping step inside its own yaw table (1 (c)): within
   1 to 4 deg, narrow readings hold 0/17 and 5/16, the rest 37/55 and
   29/44; the eval's narrow bin has the same high-force signature. This
   is evidence for force_hold, which makes the hold independent of where
   the close stopped.
2. The disagreement with hold_physics' and carry_motion's probes at 0 to
   6 deg (about 90 % held there, 59 % here).
3. The duplicate scene in the eval: 48 of the 144 scored picks are one
   identical, always-held pick (seeds 0, 7, 9, 11, 12, 13, 16 and 23).
   It inflates the held side of every pick-time comparison (the brief's
   held median pad force, 3.07 N, falls inside that scene's 3.07 to
   3.32 N) and it leaves
   about 39 informative carries per arm in the campaign's eval. The
   orchestrator should check BF#39's scene map for the campaign seeds.
4. The edge pinch also re-grasps the aligned dice (the cup-placed die is
   at yaw 0 by env_generator.py 126 to 127).
5. The asymmetry of the edge band under the pipeline carry (1 (e)).
6. The face_needs_wrist_yaw refresh loop (its point 4).

One hour, before anything of this angle is implemented:
- 30 min: hp_probe.py's force_hold + finger_gear + solver_iters lever with
  the die's yaw offset drawn in 35 to 55 deg instead of +-10 (a new draw
  range, 120 trials, physics only, about 10 minutes on four cores). If it
  holds 0 of about 113 the edge pinch is redundant; if it loses, the edge
  pinch is harmful under the hold the campaign is most likely to keep.
- 30 min: probe_grasp_geometry.py with the pre-grasp aperture shifted by
  0, 0.125, 0.25 and 0.375 mm at deltas 0, 2 and 6 deg (single carry,
  8 cells, 2 face pairs, about 200 grips): the hold at a fixed yaw against
  the close's stopping step separates the yaw band from the squeeze depth.

## 4. Data generated and deleted

- reviews/grasp_geometry_probe/edge_band_hy-15.json (160,065 B) and
  edge_band_hy-15.log (7,159 B): one re-run of the proposal's probe with
  its documented flags (`--cells 8 --deltas 35,45,55 --k90 0,1
  --carry-mode pipeline --aperture-sized 1 --hand-yaw-deg=-15`, cwd
  /root/tampura-work/tampura_environments, PYTHONHASHSEED=0, physics only,
  no lock, about 20 s). Result: 35 deg 10/16, 45 deg 14/16, 55 deg 15/16
  held (half-width medians 12.35, 12.55, 12.80 mm). Deleted by path after
  the number was written here (167,224 B), and the empty folder removed.
- Scratch analysis scripts in my session scratchpad (outside the
  checkout): gg_tab.py, gg_eval.py, gg_narrow.py, gg_power.py, gg_band.py,
  gg_phase.py, gg_p2.py, gg_find.sh, gg_run.sh; deleted by path at the end
  of the review.
- Nothing else written; this review file is the deliverable.
