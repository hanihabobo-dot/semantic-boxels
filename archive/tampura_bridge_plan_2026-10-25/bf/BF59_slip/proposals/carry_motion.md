# BF#59 proposal: the carry, the motion and the hold at home (carry_motion)

Angle: what the carry's kinematics (per-pair accelerations, junction kicks,
wrist rotation while holding, the settle and the hold at home) contribute
to the die turning out of the pinch, which executor schedule removes it,
whether BF#47's inflated transit check is needed, and what the hold at
home does. Written 2026-10-31 at 92d1e06 (branch tampura-bridge) by the
second agent on this angle (the first stopped on a service error); no
tracked file was changed. The work log is the appendix below; section
numbers "log N" point into it.

## 1. Diagnosis

### 1.1 Measured: the pipeline's carry unwinds the wrist by more than half a turn

- Every recorded die carry of the pipeline (loss_dynamics' five laptop
  episodes, read with `probes/carry_motion/episode_wrist.py`) streams a
  straight joint line of 9 pairs whose summed per-pair dq of joint 7 is
  +3.68 to +4.23 rad (211 to 242 deg; the sum is against the readback, so
  up to about 20 deg high from the per-pair lag): held s0_r1 211, s1_r1 227,
  lost s1_r2 227, s1_r3 220, s6_r1 242 deg (log 6).
- The cause is the grasp yaw convention, not the planner's path.
  `pose_belief.fitted_grasp_candidates` (pose_belief.py 177 to 197) wraps a
  near-square body's yaw into [-pi/4, pi/4) and a rectangle's into
  [-pi/2, pi/2) with the stated reason "each yaw is the smallest wrist
  rotation of its class"; `streams.sample_grasp` (836 to 845) gives the
  AABB path yaw 0 or pi/2; the orientation is
  `getQuaternionFromEuler([0, pi, yaw])` (streams.py 853). "Smallest" is
  measured against hand yaw 0 in the world, not against the arm. For their
  Panda and home (DEFAULT_ARM_POS, joint 7 = 0.785 rad) the probe's IK at
  the lift pose gives joint 7 = -2.87 to -1.95 rad (median -2.45) for
  believed yaw 0, down to the limit -2.8973 at 22.5 deg and +-2.897 at
  40 deg (log 9). The other member of the same pinch class (yaw + pi, the
  pads swapped, a physically identical pinch of any box) gives 0.13 to
  1.27 rad, a median travel to home of 22 deg instead of 182 deg.
- The home hold is TAMPURA's at-home test (allclose 1e-4 on joint 7 too),
  so the carry must end at 0.785: only the grasp choice changes the travel.

### 1.2 Measured: the wrist spin turns an off-face die out of the pinch

Probe `probes/carry_motion/probe_carry_motion.py` (physics only): their
empty table, their Panda, their die (D9 mass, inertia, frictions), the die
placed at the pick's contact height and pinched by the pipeline's own
`close_gripper_until_contact` (60 N, GRIP_SQUEEZE 0.5 mm), 60 settle
steps, then the carry from the lift pose to DEFAULT_ARM_POS along
`_linear_trajectory`'s 10 waypoints (or an RRT-like bent path) and
`hold_at_config(52)`; HELD = both pads, summed normal force >= 0.5 N at
the end of the hold (the goal check). Executors: `pipe` = the dispatcher
today (move_robot_smooth(steps=30) per pair, settle at the last), `cont` =
the same ramp started from the last commanded target (no per-pair restart,
no acceleration bound), `trap` = one trapezoid per straight segment at the
Panda datasheet accelerations (15, 7.5, 10, 12.5, 15, 20, 20 rad/s^2) and
today's velocity limits, rest at a direction change. Grasp rules: `wrap`
(today's M9) and `flip` (of g and g + pi the one whose top-down hand is the
smaller rotation from home's hand). The die sits delta deg off the believed
yaw (0 = exact face, 45 = edge pinch). 12 cells (seed 59), believed yaws 0,
+-22.5 and 40 deg, die tilt 0 and 3 deg, 92 to 96 carries per cell of the
table. Commands: `wsl -e bash -lc 'bash
archive/.../probes/carry_motion/batch5.sh'` and `batch6.sh` (4 runs at a
time), tables by `python table.py out/b5_` and `out/b6_` (log 9, 10).

| delta (deg) | wrap + pipe (today) | wrap + trap | flip + pipe | flip + cont | flip + trap |
|---|---|---|---|---|---|
| 0 | 86/92 (93 %) | 80/92 (87 %) | 96/96 | 96/96 | 96/96 |
| 3 | 85/92 (92 %) | 64/92 (70 %) | 96/96 | 96/96 | 96/96 |
| 10 | 54/92 (59 %) | 44/92 (48 %) | 43/96 (45 %) | 77/96 (80 %) | 95/96 (99 %) |
| 20 | 15/92 (16 %) | | | | 82/96 (85 %) |
| 45 (edge) | 84/92 (91 %) | 92/92 | 79/96 (82 %) | 96/96 | 96/96 |
| 10, bent path | 51/92 (55 %) | | 54/96 (56 %) | | 94/96 (98 %) |

The quarter-turn class (four equivalent face pinches of the cube) adds
nothing over the half turn: 42, 76, 95 of 96 at 10 deg against 43, 77, 95
(log 10). Batch 4 (exact face, tilts 0 and 8 deg, the unwrapped yaw):
same 133/162 under pipe and cont, 137/162 under trap; the hand-nearest
member 159, 166 and 168/168 (log 5).

What this says:
- For the face pinch (the eval's class: every eval die pick read a
  half-width of 10.0 to 11.3 mm, a face pinch within 0 to 15 deg,
  grasp_geometry 1.3 (a)) the long wrist unwind is the main cause: with
  the pads swapped the carry holds 100 % at 0 and 3 deg and 99 % at 10 deg
  under the trapezoid, where today's grasp and stream hold 93, 92 and 59 %.
- The junction kicks are the second cause and they decide once the wrist
  spin is gone: today's stream gives the hand 81 to 93 m/s^2 for a step or
  two at every pair start (median peak; 2.8 to 3.3 m/s^2 under the
  trapezoid). Under the flipped grasp they cost 55 % of the carries at
  10 deg (the die turns a median 116 deg) and 18 % of the edge pinches.
- The two act only together. Under today's grasp a smooth executor does
  not help the face pinch and is worse than today's stream at 3 and
  10 deg (70 and 48 % against 92 and 59 %; cont 73 and 39 %); I have no
  explanation for why the stream's stop-and-go holds better during a long
  wrist spin. The flipped grasp under today's stream is worse at 10 deg
  (45 against 59 %) and for the edge pinch (82 against 91 %).
- The edge pinch (grasp_geometry's `edge_pinch`) does not care about the
  wrist (wrap holds 100 % under cont and trap) and needs only the
  acceleration bound (pipe 82 to 91 %).
- Speed is not the variable: velocity limits halved (batch 1, `slow`)
  held 100/114 against 96/114; a pure 90 deg wrist spin at 20 and at
  120 deg/s held the same (log 4). The sign of the spin relative to the
  pinch matters (log 4, 5): a spin of -90 deg from yaw 90 deg loses most
  dice at either speed, +90 holds; today's unwind is in one sign for most
  of the window (inference: one reason the eval loses about one carry in
  five rather than most).
- Pitching the hand about the pinch axis to 60 deg (home's hand is
  38.8 deg off vertical) holds 32/32: the hand's orientation against
  gravity during the swing is not the cause (log 4).

INFERENCE (not measured): the pads hold the die on one to four points per
pad at opposite ends of the pad width (log 4; grasp_geometry 1.3 (f)) with
no torsional friction (hold_physics item 6: pad 0.1 x die 0); the wrist's
rotation about the approach axis walks the die around those points, and
the farther the wrist turns the farther the die creeps, until the pinch
reaches an edge (loss_dynamics 1.3: face to edge, width +0.16 to 0.23 mm)
and a junction kick or the decaying force releases it.

### 1.3 Measured: three episodes with both changes (laptop, under the lock)

`probes/carry_motion/episode_fix.py` runs the unchanged driver with the
flip patched into `pose_belief.fitted_grasp_candidates` and the trapezoid
patched over the dispatcher's `move_robot_smooth` name (waypoints buffered,
the whole polyline run at the settle=True call, then the original settle),
with loss_dynamics' `loss_recorder` installed. Command:
`CM_FLIP=1 CM_TRAP=1 bash probes/carry_motion/run_ep.sh <seed> <tag>`.

| seed (laptop scene) | base under the same defaults (loss_dynamics) | flip + trap |
|---|---|---|
| 1 (1747173590) | held, lost, lost | held: die rotation 9.7 deg in the move, 13.8 at home; pad force min 1.38 N; joint 7 travel 12 deg |
| 0 (1747173591, the pinned one) | held, rotation 26.8 deg | held: rotation 0.5 deg; pad force min 1.10 N; joint 7 travel 22 deg; wall 15.3 s (base 23.5), move time 3.2 s (6.9) |
| 6 (1747173593) | lost at wp 9 | no die pick: 34 cup pick refusals in loss_dynamics' radius loop ("e_cups_ud pose_radius 5.71 mm is outside its commit margin" after each 0.49 mm wrist observe), 600 s cap |

The two carries ran as one straight segment of 336 and 356 steps (base:
9 pairs of 39 to 42 steps plus a 76 step settle, about 454). Seed 6 is a
warning: base s6_r1 picked e_cups_ud after one observe; under the patch
the loop of loss_dynamics 1.6 never ended. The flip turns every M9 body's
hand by pi, cups included, so the arm's posture over a cup differs, and
the overhead refresh after the approach move may now see the cup whole
and loosen its radius. Not separated (the three episodes were the budget);
fix 1 should be evaluated with loss_dynamics' `pose_radius_keep` on.

### 1.4 Measured: the hold at home

- Within the pipeline's window it is harmless: in every probe carry the
  hold reaches the at-home test (19 to 28 steps, cap 52); one loss in 990
  carries of batch 4 started in the hold; the settle's stop ("the snap")
  starts 2 of the 25 losses of trap's batch 4 and none of pipe's.
- After it the die keeps turning at rest: 2 s more at home (--after 480)
  lose 6 of the 95 dice held at the end of the hold (flip + trap, 10 deg;
  rotation in the hand 6 to 32 deg at the end of the hold, 28 to 41 deg at
  the loss, 40 to 140 steps later; five of six at believed yaw 40 deg).
  wrap + pipe lost none extra (its weak grips were gone already). A creep
  under gravity in home's 38.8 deg tilted hand. The goal check runs at the
  end of the hold, so the eval does not see it; a goal that keeps the die
  longer would. This belongs to the hold physics angle (torsional
  friction), not to the motion.

### 1.5 BF#47: the inflated transit check is not needed for the slip

- The probe has no cups at all and loses dice at the eval's rate under
  today's grasp and stream.
- In all five recorded episodes the die touches no body but the pads from
  the post-lift to the first step without pad contact; after it only the
  table (`probes/carry_motion/episode_contacts.py`, log 7). The recorder
  does not list arm-on-cup contacts.
- The eval's curated console prints no integrity or collision line in the
  31 loss episodes; the cluster's console_debug logs would show
  "[integrity] disturbed" on the move home and are the orchestrator's to
  grep. BF#47's case (a cup mis-placed with a 36 mm radius) is a separate,
  rare transit risk; it is not a cause of the 21 %.

## 2. Proposed fixes

Both are pipeline-wide (every top-down grasp, every move of every scene),
model side (the grasp sampler; the executor's motion primitive), behind
`slip_fixes.on('<name>')`, default off. They are a pair: the probe says
each alone can make the face pinch worse, together they remove the loss.
The eval should run each alone and both together.

### 2.1 `grasp_wrist_home`: the pad-swapped grasp whose wrist is nearer home

- Mechanism: 1.1, 1.2. Today's grasp yaw puts the wrist at its limit and
  the carry unwinds it 180 to 240 deg while it holds the die.
- Change: `pose_belief.fitted_grasp_candidates` (177) gets an optional
  `ref_orn` (the hand's orientation at the planner's home configuration).
  With the switch on and `ref_orn` given, every candidate (gy, span) becomes
  (gy', span) with gy' the member of {gy, gy + pi} (wrapped to (-pi, pi])
  whose top-down orientation `[0, pi, gy']` is the smaller rotation from
  `ref_orn`; the span is unchanged (the pinch is the same). The AABB path of
  `streams.BoxelStreams.sample_grasp` (840 to 845) applies the same choice
  to its 0 and pi/2. `ref_orn` comes from FK of `planner.home_config` in the
  planning twin, computed once when the streams are built (a known
  configuration of our own robot model, not a read of the executing world).
  Downstream readers are sign-insensitive and need no change:
  `believed_margin` (221, `pad_direction`), `execute_pick`'s sizing
  (`pinch_direction`, `sized_pinch_half`), the kin stream (IK at the given
  orientation, seeded as today; the IK now lands joint 7 at 0.1 to 1.3 rad,
  inside its range). The docstring's "smallest wrist rotation of its class"
  becomes true of the arm.
- Section 5: model side (the sampler's choice inside a grasp class it
  already declares symmetric); every body and scene; no plan edited; no
  robot setting touched.
- Expected effect: with 2.2, the probe's per-carry loss falls from 7, 8 and
  41 % (0, 3, 10 deg) to 0, 0 and 1 %; from 84 to 15 % at 20 deg. Weighted
  by the eval's width bins (most picks 0 to 6 deg, 24 near 10 deg, 5
  beyond) that predicts a loss rate per die carry under 3 % against 21 %;
  to be real on the campaign's seeds it must fall below 10 % (base: 36 of
  174) with base's repeat spread in view. Alone (today's stream) the probe
  predicts a gain at 0 to 3 deg and a loss at 10 deg (45 against 59 %),
  so alone it may not move the rate. Time: the carry home is shorter
  (probe median 406 to 360 steps under pipe; joint 7 is the slowest joint
  of today's carry).
- Falsify: (a) the switch acts: in every die carry under the switch the
  joint 7 travel from the post-lift readback to home is under 90 deg (the
  telemetry's waypoint notes give it); if not, the implementation is wrong;
  (b) with 2.1 and 2.2 on, the loss rate per die carry is not below 10 % or
  not below base's on the paired seeds: the mechanism is wrong for the
  episodes; (c) the cup picks get worse (grip failures, refusals, the
  radius loop of 1.3) against base.
- Risk to our scenes: every grasp's hand turns by pi for about half the
  bodies. In this world our 40 mm 100 g cube and 60 mm 500 g block held
  79/88 and 82/90 under today's rule and stream and 96/96 with the flip
  (log 10); our scenes' own home and robot placement are not measured (in
  logs/run_2026-10-30_19-19-24 joint 7 is the largest mover of 240 of 744
  waypoint pairs, so long unwinds happen there too). The approach posture
  over a body changes, which changes what the overhead camera sees after
  the approach (seed 6, 1.3). Places: the place configuration's hand
  follows the grasp, also nearer home.
- Effort: 3 hours (the function and its reference, the AABB path, the FK at
  build time, tests in tests/test_m9_grasp.py: their home's reference
  turns yaw 0 into pi, a reference at top_down(0) keeps 0, spans unchanged).

### 2.2 `carry_trapezoid`: one acceleration-bounded schedule per move

- Mechanism: 1.2. Today every waypoint pair restarts from the lagging
  readback, so the commanded velocity collapses to a tenth at every
  junction and rebuilds: 81 to 93 m/s^2 at the hand, 500 to 560 rad/s^2 at
  the joints, at every pair start (log 2, 3); the last pair stops on the
  settle. This is the same change as loss_dynamics' `carry_accel_limit`
  (its 2.3); one switch should carry it, and its value rests on 2.1.
- Change: a new `robot_utils.move_robot_trajectory(robot_id, waypoints, gui,
  on_step=None)`: from the readback, merge collinear pairs (cosine
  > 0.9999), time each straight segment with a trapezoid in the path
  parameter under `JOINT_VELOCITY_LIMITS` and a new `JOINT_ACCEL_LIMITS`
  (Panda datasheet 15, 7.5, 10, 12.5, 15, 20, 20 rad/s^2, the source of
  F14's velocity limits), at rest at a direction change, POSITION_CONTROL
  at 240 N m per step with `telemetry.tick()` and `on_step` as today, then
  the existing settle (120 steps, 2e-3 rad). With the switch on, the
  dispatcher's move (test_full_pipeline.py 1877 to 1896) makes one call
  with the whole trajectory instead of the per-pair loop (the F17 per-pair
  telemetry notes stay), and `move_robot_smooth` runs its single hop as a
  one-segment trapezoid with its step count as the floor, so the pick and
  place descents and the lift get the same bound. The executed path is the
  certified polyline (lower acceleration, smaller tracking error). The new
  pybullet writes need their line in tools/bridge_gates_allowlist.txt.
- Section 5: an executor primitive, datasheet values like F14, every move
  of every scene; the plan's waypoints are executed as planned.
- Expected effect: with 2.1 as in 2.1. With grasp_geometry's `edge_pinch`
  (no 2.1 needed): edge pinches 91 to 100 % in the probe. Alone under
  today's grasp: no gain for the face pinch, possibly a loss (3 deg 70 %
  against 92 %). Time: a straight carry is faster (probe median 406 to 372
  steps under today's grasp, 360 to 334 under the flip; episodes 336 and
  356 against about 454); a bent path is slower (rest at each bend: the
  via path 405 against 311 steps), so RRT moves of many bends lose time.
- Falsify: (a) the telemetry's per-step joint acceleration exceeds 1.2 x
  the datasheet on any move under the switch (implementation); (b) with
  2.1 and 2.2 on, the loss rate per die carry is not below 2.1 alone on
  the paired seeds; (c) our scenes' places or stacks get worse (placement
  error, collisions on the bent transits).
- Risk to our scenes: wall time on transits with many bends; nothing for
  the grasp. A junction speed limited by the direction change (keep speed
  through gentle bends, rest at sharp ones) is the refinement if the time
  matters; it is not measured here.
- Effort: 4 hours (the profile, the dispatcher call, the gate line, a unit
  test on a two-segment polyline: acceleration bound, rest at the bend,
  endpoint reached).

### 2.3 Not proposed

- BF#47's transit check with the twin's bodies inflated by their pose
  radius: not a cause of the slip (1.5); it stays a separate item.
- A change to the hold at home: it is harmless inside the scored window
  (1.4); the creep after it belongs to the hold physics angle.
- The quarter-turn class for near-square bodies: no gain over the half
  turn (1.2), and the half turn holds for every box.

## 3. With one more hour

1. Seeds 1 and 6 on the laptop, three times each, under base, 2.1 alone,
   2.2 alone and both, with `pose_radius_keep` patched in to remove the
   cup loop of 1.3: the episode-level version of the table in 1.2 and the
   answer to whether the flip feeds the radius loop.
2. Our own random-pairs holding and stack scenes with the flip on and off:
   joint 7 at every pick and the wrist travel of every carry from the
   telemetry, and the held rate at place entry.
3. Why today's stop-and-go stream holds better than a smooth one during a
   long wrist spin (wrap + pipe 92 % against wrap + trap 70 % at 3 deg):
   the trace of a trial that one holds and the other loses.

## 4. Data generated and deleted

All under `archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/carry_motion/`
(115 MB in all, none of it tracked; DATA_LEDGER.md is tracked and was not
edited in this phase, the orchestrator adds the rows):

- Scripts (keep, about 45 KB): probe_carry_motion.py (28 KB), run.sh,
  batch1.sh to batch6.sh, compare.py, losses.py, axes.py, corr.py,
  trace.py, show.py, by_wrist.py, table.py, episode_wrist.py,
  episode_contacts.py, episode_fix.py, run_ep.sh.
- Probe outputs `out/` (110 MB: b1_* 15 MB, b2_* 4 MB, b3_* 8.8 MB, b4_*
  9.6 MB, b5_* and b6_* the rest, smoke.json 0.17 MB; one .json with the
  per-step traces of the lost trials and one .txt summary per run): cited
  above; garbage after the review phase except the .txt summaries and
  b5_*/b6_* (the tables of 1.2), which the review may thin to the
  summaries (re-runnable in about 15 minutes per batch).
- Episodes `episodes/` (4.3 MB): s0_fliptrap 0.8 MB, s1_fliptrap 1.5 MB,
  s6_fliptrap 2.0 MB (carry.jsonl, stdout.txt, save/). Keep for the
  review; then save/ is garbage except s6's console_debug.log (the cup loop
  of 1.3).
- Deleted: out/b5_smoke.json (the smoke of the batch 5 options, superseded
  by batch 5) and one __pycache__ folder made by a compile check.

## Appendix: work log


### 1. Code reading (92d1e06)

- `robot_utils.move_robot_smooth` 877 to 999: per waypoint pair a linear
  ramp of `steps` (30 minimum) position targets, stretched only when a joint
  would exceed `JOINT_VELOCITY_LIMITS` (2.175 / 2.610 rad/s). Every step
  issues POSITION_CONTROL with force 240 and PyBullet's default gains
  (positionGain 0.1, velocityGain 1, target velocity 0). No acceleration
  bound, no velocity blend between pairs. `settle=True` (the last pair
  only) then commands the final target for up to 120 steps until 2e-3 rad.
- `hold_at_config` 1001: the same command toward home until allclose 1e-4
  or `HOME_HOLD_STEP_CAP` 52 steps (task_spec 96).
- Dispatcher move 1795 to 1939: with cargo the move is re-solved from the
  readback (`plan_motion`), every pair through `move_robot_smooth(steps=30,
  settle=last)`, then the hold.
- `streams.plan_motion` 912: when the direct joint-space line is clear the
  result is `_linear_trajectory` 1136, 10 evenly spaced waypoints (9 pairs
  of equal size, so a constant commanded joint velocity); otherwise
  RRT-Connect plus shortcut smoothing (pairs of unequal size and direction).
- Telemetry of a laptop run (logs/run_2026-10-30_19-19-24/telemetry.log,
  our own scene) shows the arm's lag behind the ramp: the readback-to-next
  waypoint distance rises from the pair size (0.116 rad at waypoint 1) to a
  steady 0.162 rad by waypoint 4, i.e. a steady lag of about 0.046 rad at
  0.93 rad/s, a first-order lag of about 0.05 s. Inference: with the default
  gains the joint follows q' = 24 (q* - q) (0.1 / dt), so every velocity
  step of the command (start of the move, every change of pair size or
  direction, the stop at the last waypoint) gives a joint acceleration of
  about 24 x the velocity step in one simulation step (infinite jerk).

### 2. Probe smoke (probes/carry_motion/probe_carry_motion.py, out/smoke.json)

Command (WSL, physics only): `bash probes/carry_motion/run.sh smoke
--executor pipe --cells 1 --tilts 0 --trace`; trace printed with
`show.py out/smoke.json 1 15`. 5 carries (one cell, five yaws), all held at
home, but trial 1 (cell 0.475, -0.155, yaw 0) shows the mechanism:

- MEASURED: at the first step of EVERY waypoint pair (steps 39, 85, 132,
  178, 225, 271, 318, 364 of the carry) the largest joint speed falls from
  about 2.5 rad/s to about 0.5 rad/s in one simulation step: joint
  acceleration 540 to 560 rad/s^2, EE linear acceleration 56 to 66 m/s^2
  (6 g), EE angular acceleration 460 to 525 rad/s^2. Between those steps
  the accelerations are 0.5 to 10.
- MEASURED: at two of these pair starts (steps 318 and 364) one pad's normal
  force reads 0.00 N and the other 0.25 and 0.08 N (summed below the 0.5 N
  goal floor); the die's offset in the hand jumps to 1.07 mm at step 365,
  and its rotation in the hand reaches 10 deg during the carry (6.5 deg at
  home). The pads recover to 2.2 N at home in this trial.
- CODE (inference confirmed by the numbers): move_robot_smooth reads the
  arm's CURRENT position at the start of each pair (robot_utils.py 930) and
  ramps from there. Under the default position gain the arm runs a lag of
  v / 24 behind the ramp; the new pair's first target sits only v * dt
  ahead of the readback, so the commanded velocity collapses to a tenth of
  v in one step, then rebuilds over the pair. The executor therefore
  stop-starts the arm at every waypoint: nine decelerations of 0.9 v in one
  step per 10-waypoint carry. A single-hop carry (the Q14 and carry-watch
  probes, BF#38, BF#48) has none of them, which fits 93 of 96 held there
  against 21 % lost in the eval's multi-pair carries (to be tested next).

### 3. Batch 1: the executors side by side (probes/carry_motion/batch1.sh)

Same 114 gripped carries per executor (12 cells drawn with seed 59 from
W's 5 cm grid, yaws 0, pi/2, pi/4, -pi/4, pi/8, die tilt 0 and 8 deg),
squeeze 0.5 mm, 60 N, hold cap 52. Outputs out/b1_*.json, compared with
compare.py and losses.py.

| executor | path | held | median min summed pad force | median peak EE lin acc (m/s^2) | median peak joint acc (rad/s^2) | median steps |
|---|---|---|---|---|---|---|
| pipe (today) | linear 10 wp | 96/114 | 0.05 N | 86 | 530 | 373 |
| hop (one pair, the Q14 probe's motion) | direct | 93/114 | 0.91 | 17 | 62 | 300 |
| cont (ramp from the last command) | linear | 96/114 | 0.75 | 17 | 52 | 307 |
| trap, a_max 8 rad/s^2 | linear | 99/114 | 0.90 | 2.8 | 8 | 355 |
| slow, velocity limits x0.5 | linear | 100/114 | 0.06 | 58 | 254 | 633 |
| pipe | via (an RRT-like bend) | 89/114 | 0.08 | 117 | 560 | 346 |
| trap 8 | via | 88/114 | 0.73 | 4.6 | 8 | 441 |

MEASURED:
- The executor's acceleration spikes are real and the trapezoid removes
  them (joint acceleration 530 to 8 rad/s^2, the pad-force dips from 0.05
  to 0.9 N), but the held count barely moves (96 to 99 of 114). The motion's
  acceleration is NOT the main cause of the losses in this probe.
- The losses sit in the grasp geometry: by yaw (all executors pooled) yaw
  pi/2 and pi/4 carry nearly all of them, yaw 0 and -pi/4 almost none; die
  tilt 8 deg loses 8 to 20 per executor, tilt 0 loses 1 to 6.
- Two loss modes in the traces (losses.py):
  (A) pipe: with the tilted die at yaw pi/2 or pi/4 the pads lose the die
  within the first 6 to 8 steps of the first pair (hand pitch under 2 deg),
  while joint 7 starts unwinding the grasp yaw toward home's.
  (B) trap: the die turns in the hand gradually while BOTH pads still press
  at 1.5 to 7 N, starting when the hand's approach axis has tilted 15 to 30
  deg from vertical (home's hand is tilted 38.8 deg from straight down with
  the pinch axis horizontal), passing 45 deg near home, then the pads lose
  it, often in the settle or the hold.
- All held carries also turn the die in the hand: median peak rotation 12
  to 31 deg.

### 4. Batch 2 and 3: pure rotations of the hand (batch2.sh, batch3.sh)

The die pinched at the lift pose as before, then the hand only rotates at
the lift position (IK per degree before the die exists, streamed with the
continuous ramp, 12 steps per degree = 20 deg/s, or 2 to 3 steps = 80 to 120
deg/s). 6 cells, yaws 0, pi/2, pi/4, tilts 0 and 8.

| motion | held |
|---|---|
| pitch 60 deg about the pinch axis (hand y), 20 deg/s | 32/32 |
| pitch 60 deg across the pinch (hand x), 20 deg/s | 30/34 |
| spin 90 deg about the approach axis (hand z), 20 deg/s | 32/34 |
| spin 90 deg about hand z, 120 deg/s | 33/34 |
| pitch 35 about y then spin +90 about z (slow / fast) | 7/8, 8/8 |
| pitch 35 then spin -90 (slow / fast) | 2/6, 4/6 |
| spin +90 then pitch 35 (slow / fast) | 11/12, 12/12 |
| spin -90 then pitch 35 (slow / fast) | 4/14, 5/14 |
| the full carry, pipe / trap 8 (same 34 picks) | 28/34, 26/34 |

MEASURED:
- Turning the hand about the pinch axis to 60 deg (more than home's 38.8)
  keeps the die (rotation in the hand 0.3 to 24 deg at the end, mostly
  under 3). The pendulum about the pinch axis is not the loss.
- The losses follow the SIGN of the wrist spin from the pick's grasp yaw:
  spin -90 from yaw pi/2 (and pi/4) loses most dice at 20 deg/s and at 120
  deg/s alike, spin +90 holds. Speed is not the variable.
- A lost slow spin (b3_spinpitch_-90_slow, trial 3, yaw pi/2, tilt 0, hand
  exactly top-down, wrist at 0.3 rad/s, trace.py): the die creeps in the
  hand from step 300 (3.7 deg) to 24 deg at step 540 about a horizontal
  axis in the hand ([0.5, 0.86, 0], between the pinch axis and across it),
  the pad forces RISE from 0.9 to 4 N while it turns (the die wedges between
  the pads), then both pads lose it at step 721 (47 deg).
- The pinch at the start of that trial: pad 13 touches at (-4.7, -8.9,
  4.5) mm in the hand frame, pad 12 at (4.4, 8.9, 4.6) and (5.8, 8.9, 1.8):
  one or two contact points per pad, on OPPOSITE ends of the pad width, so
  the two normal forces do not act on one line (a couple about the approach
  axis of about 1 N x 9 mm), and the contacts sit 2 to 5 mm ABOVE the die's
  centre (COM at z 6.3 mm). Every trial shows 1 to 4 points per pad.
INFERENCE: the die is held on a few contact points whose positions are
set by the pinch's geometry; the wrist spin in one direction walks the die
around them (creep), the other direction does not. The motion's
acceleration is a secondary load; the wrist rotation while holding, and its
sign relative to the pinch, is the motion variable that matters.

### 5. Batch 4 (found finished on disk, logged by the second agent)

batch4.sh: the grasp-yaw rule. `same` = grasp yaw equal to the die's yaw
(unwrapped); `minturn` = of the four equivalent face pinches of the cube
(die yaw + k pi/2) the one whose lift-pose hand is the smallest rotation
from home's hand (FK of the planned configurations only). 12 cells, 7 die
yaws (0, +-22.5, +-45, 67.5, 90 deg), tilts 0 and 8, die exactly face
aligned (delta 0). by_wrist.py tabulates.

| executor | same | minturn |
|---|---|---|
| pipe | 133/162 | 159/168 |
| cont | 133/162 | 166/168 |
| trap 8 | 137/162 | 168/168 |

MEASURED:
- minturn makes joint 7's travel from the lift to home small (median -42
  to +30 deg, range -83 to +46) where `same` turns it 109 to 211 deg one
  way or 73 to 121 deg the other.
- Under `same`, the losses sit at the NEGATIVE wrist travel (dq7 -73 to
  -121 deg: die yaws 45 to 90 deg) and mostly with the tilted die
  (tilt 8: 1/12, 3/12, 5/11 held); a positive travel of 148 to 211 deg
  holds 24/24 at yaw 0. The sign effect of batch 3 again.
- minturn and the trapezoid together: 168/168. minturn alone under the
  pipeline's per-pair stream still loses 9 (all in pairs 1 to 3): with the
  wrist spin gone, the junction kicks are what is left.
- The hold at home is short and harmless in the probe: at_home reached in
  every carry, 19 to 28 hold steps, one loss of 498 starting in the hold.

### 6. The episodes' wrist travel (episode_wrist.py over loss_dynamics' runs)

`python carry_motion/episode_wrist.py loss_dynamics/runs` sums the
recorded waypoint dq of the move home (read only, the sibling's
carry.jsonl files):

| run | outcome | pairs | sum dq7 |
|---|---|---|---|
| s0_r1 | held | 9 | +3.68 rad (211 deg) |
| s1_r1 | held | 9 | +3.95 rad (227 deg) |
| s1_r2 | lost | 9 | +3.95 rad (227 deg) |
| s1_r3 | lost | 9 | +3.85 rad (220 deg) |
| s6_r1 | lost | 9 | +4.23 rad (242 deg) |

MEASURED: every recorded die carry of the pipeline unwinds the wrist by
211 to 242 deg (joint 7 from about -2.9 rad, its lower limit -2.8973, to
home's +0.785). The pipeline's grasp convention (`top_down(yaw)` with the
M9 yaw wrapped into [-pi/4, pi/4)) puts the pick's wrist at the far end of
its range for find_dice's window, and the carry home turns the hand more
than half a revolution about its approach axis while it holds the die. The
pinch at yaw g + pi is the same pinch (the pads swap) and would leave
joint 7 near 0.24 rad, 0.55 rad (31 deg) from home's.

### 7. BF#47's transit question on the recorded episodes (episode_contacts.py)

`python carry_motion/episode_contacts.py loss_dynamics/runs`: in all five
recorded carries the die touches no body but the pads from the post-lift
to the first step without a pad contact; after it, only body 1 (the
table, where it lands). The recorder does not list arm-on-cup contacts,
but the three losses are explained without one (the rotation out, in a
probe that has no cups at all and loses at the eval's rate). The eval's
curated console (evidence/tc_4912db9_loss_context.txt, 31 loss episodes)
prints no integrity or collision line; the full console_debug logs with
the "[integrity] disturbed" lines are on the cluster, which this agent
does not touch.

### 8. Code reading: why the wrist sits at its limit

`pose_belief.fitted_grasp_candidates` (177 to 197) wraps a near-square
body's yaw into [-pi/4, pi/4) and a rectangle's into [-pi/2, pi/2), with
the docstring's reason "each yaw is the smallest wrist rotation of its
class". `streams.sample_grasp` (836 to 845) does the same for the AABB
path (yaw 0, or 0 and pi/2). The orientation is
`getQuaternionFromEuler([0, pi, yaw])`. Smallest is measured against
hand yaw 0 in the world, not against the arm: for their Panda and home
(DEFAULT_ARM_POS, joint 7 = 0.785) top_down(0) needs joint 7 near -2.74
(the smoke of batch 5: the flipped grasp yaw pi gave q7 0.398 at the lift,
so yaw 0 sits at 0.398 - pi), and top_down(0.39) would need -3.16, past
the lower limit -2.8973. The class's other member (yaw + pi, the pads
swapped) leaves joint 7 within 0.4 to 0.8 rad of home's.
Our own scenes: the telemetry of logs/run_2026-10-30_19-19-24 names joint
7 (j6) the largest mover in 240 of 744 waypoint pairs, so long wrist
unwinds happen there too (not split by carry here).

### 9. Batch 5: the pipeline's grasp rule against the flipped one, off-face dice (batch5.sh, table.py)

Probe changes (probe_carry_motion.py): `--delta-deg` puts the die at the
believed yaw + delta (the pads' yaw error against the die's faces; 45 =
edge pinch); `--grasp-rule wrap` is the pipeline's M9 rule (believed yaw
wrapped into [-pi/4, pi/4)); `flip` takes the wrap and, of the two
pad-swapped equivalents g and g + pi (the same pinch of any box), the one
whose lift-pose hand is the smaller rotation from home's hand; `--amax ds`
gives the trapezoid the Panda datasheet accelerations (15, 7.5, 10, 12.5,
15, 20, 20 rad/s^2). 12 cells (seed 59), believed yaws 0, +-22.5, 40 deg,
die tilt 0 and 3 deg, squeeze 0.5 mm, 60 N, hold cap 52. Command:
`wsl -e bash -lc 'bash .../probes/carry_motion/batch5.sh'` (4 runs at a
time, physics only), table: `python table.py out/b5_`.

Lift joint 7 (q7_lift, rad; home 0.785): wrap at believed yaw 0: -2.87 to
-1.95 (median -2.45); at 22.5 deg: -2.897 (the limit) to +2.897; at 40 deg:
+-2.897. flip: 0.13 to 1.27 at every yaw. MEASURED: the pipeline's rule
puts the pick's wrist at or near its limit and the carry home unwinds it
by a median 182 deg; the flipped grasp unwinds it by a median 22 deg.

| delta | rule | pipe (today) | cont | trap (datasheet) |
|---|---|---|---|---|
| 3 | wrap (today) | 85/92 (92 %) | 67/92 (73 %) | 64/92 (70 %) |
| 3 | flip | 96/96 (100 %) | 96/96 | 96/96 |
| 10 | wrap (today) | 54/92 (59 %) | 36/92 (39 %) | 44/92 (48 %) |
| 10 | flip | 43/96 (45 %) | 77/96 (80 %) | 95/96 (99 %) |

Move steps (median): wrap pipe 406, cont 334, trap 372; flip pipe 360,
cont 305, trap 334. Peak hand acceleration (median): pipe 81 to 93 m/s^2,
cont 16 to 20, trap 3.1 to 3.3.

MEASURED:
- The wrist unwind is the main lever for the near-face pinch (the eval's
  class, 1 to 15 deg off): flip with the trapezoid holds 96/96 at 3 deg
  and 95/96 at 10 deg, where today's executor and rule hold 92 % and 59 %.
- The two changes only work together. A smooth executor under today's
  rule is WORSE than today's stream (3 deg: 70 to 73 % against 92 %;
  10 deg: 39 to 48 % against 59 %). The flipped grasp under today's stream
  is worse at 10 deg (45 % against 59 %; the die turns 116 deg median):
  with the long wrist spin gone, the junction kicks are the loss.
- A continuous stream without an acceleration bound (cont) is half way:
  80 % at 10 deg with flip.

Batch 5 complete (delta 0 and 45 added):

| delta | rule | pipe (today) | cont | trap (datasheet) |
|---|---|---|---|---|
| 0 | wrap (today) | 86/92 (93 %) | 81/92 (88 %) | 80/92 (87 %) |
| 0 | flip | 96/96 | 96/96 | 96/96 |
| 45 (edge) | wrap (today) | 84/92 (91 %) | 92/92 | 92/92 |
| 45 (edge) | flip | 79/96 (82 %) | 96/96 | 96/96 |

MEASURED: for the face pinch (0, 3, 10 deg) the wrist unwind decides and
the trapezoid is needed on top of the flip at 10 deg; for the edge pinch
the wrist does not matter (wrap holds 100 % under cont and trap) and the
junction kicks are the whole loss (pipe 82 to 91 %). Flip plus trap holds
383/384 carries over the four deltas; today's rule and stream hold
309/368 (84 %).

### 10. Batch 6 (batch6.sh, table.py out/b6_)

Probe change: `--payload` (dice, or tools/_probe_q14_grip.py's OURS:
cube100g 40 mm 0.1 kg, block500g 60 x 60 x 75 mm 0.5 kg, box shapes).
Same cells, yaws, tilts and close as batch 5.

| body / path | delta | rule | executor | held |
|---|---|---|---|---|
| die | 10 | minturn (quarter class) | pipe / cont / trap | 42/96, 76/96, 95/96 |
| die | 10 | flip (batch 5) | pipe / cont / trap | 43/96, 77/96, 95/96 |
| die | 20 | wrap / pipe (today) | | 15/92 (16 %) |
| die | 20 | flip / trap | | 82/96 (85 %) |
| die, via path (RRT-like bend) | 10 | wrap / pipe (today) | | 51/92 (55 %) |
| die, via | 10 | flip / pipe | | 54/96 (56 %) |
| die, via | 10 | flip / trap (rest at the bend) | | 94/96 (98 %) |
| die, 2 s more at home (--after 480) | 10 | wrap / pipe | | 54/92 (59 %, as without) |
| die, 2 s more at home | 10 | flip / trap | | 89/96 (93 %, 95/96 without) |
| cube100g | 0 | wrap / pipe, trap | | 79/88, 81/88 (90, 92 %) |
| cube100g | 0 | flip / pipe, trap | | 96/96, 96/96 |
| cube100g | 3 | wrap / pipe, trap | | 75/88, 73/88 (85, 83 %) |
| cube100g | 3 | flip / pipe, trap | | 78/96 (81 %), 96/96 |
| block500g | 0 | wrap / pipe, trap | | 82/90, 83/90 (91, 92 %) |
| block500g | 0 | flip / pipe, trap | | 96/96, 96/96 |

MEASURED:
- The quarter-turn class adds nothing over the half-turn flip (the same
  carries held): the half turn, valid for every box, is enough.
- The trapezoid with a rest at a direction change keeps the gain on a
  bent path (98 %); the via path costs it 71 more steps (405 against 334).
- Our own box bodies lose 8 to 15 % under today's rule and stream in THIS
  world (their Panda, their home, the window W) and hold 100 % with flip
  (and with flip and trap at 3 deg). Not measured: our scenes' own robot
  placement and home, where the wrist travel at the pick may differ.
- The hold at home: in the extra 2 s at rest, 6 of the 95 dice held at the
  end of the 52-step hold left the hand (flip / trap, 10 deg; trials 7,
  24, 64, 68, 88, 96: rotation in the hand 6 to 32 deg at the end of the
  hold, 28 to 41 deg at the loss, 40 to 140 steps after the hold, five of
  six at believed yaw 40 deg). The die keeps turning at rest in home's
  hand (approach axis 38.8 deg from vertical): a creep under gravity, not
  a motion effect. The pipeline's goal check runs at the end of the hold,
  so it does not see it; any later use of the held die would.

### 11. Episode 1 with both changes: laptop seed 1 (episode_fix.py, run_ep.sh)

`episode_fix.py` runs the unchanged driver with two patches (env
CM_FLIP=1, CM_TRAP=1) and loss_dynamics' loss_recorder installed (read
only use of the sibling's module): flip wraps
`pose_belief.fitted_grasp_candidates` (each candidate yaw g becomes the one
of g, g + pi whose top-down hand is nearer home's hand; every M9 body, cups
included), trap replaces the dispatcher's `move_robot_smooth` name: the
settle=False waypoints are buffered and the settle=True call runs the whole
polyline from the readback as trapezoids (datasheet accelerations, rest at
a direction change), then the original settle. Command, under the lock:
`CM_FLIP=1 CM_TRAP=1 bash probes/carry_motion/run_ep.sh 1 s1_fliptrap`.

Scene 1747173590.312597 (the laptop's seed 1; base under the same driver
defaults: held, lost, lost in loss_dynamics' s1_r1 to s1_r3). Result: their
reward 1.0, our goal check ok (the driver's gate_failed is the G19
mismatch). The die carry: one straight segment, 336 simulation steps
(base: 9 pairs of 42 steps plus a 76 step settle, 454), rotation of the
die in the hand 9.7 deg at the end of the move and 13.8 deg after the
19 step hold (base s1_r2: 100 deg and lost; s1_r1: 4.1 deg), smallest pad
force 1.38 / 1.49 N (base: 0.0 N on both pads at the junctions), first
pad break none. 10 plans and 247 s wall (s1_r1: 7 plans, 113 s); the
extra plans are loss_dynamics' cup radius loop ("e_cups_ud's pose is too
uncertain, I should look first"), not the patches, and the planning time
(148 s against 60 s) reflects the laptop's load (batch 6 ran beside it).
