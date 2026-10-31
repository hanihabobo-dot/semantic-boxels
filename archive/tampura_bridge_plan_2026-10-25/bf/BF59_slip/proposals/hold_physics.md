# BF#59 proposal: the physics of the hold

Angle: the contact solver during the pipeline's own carry. Commit 92d1e06
for the probes, line numbers below at d021dad (robot_utils.py,
execution.py, boxel_env.py, tampura_bridge/policy.py are unchanged between
the two; test_full_pipeline.py is quoted at d021dad). No tracked file was
edited. The probe is `probes/hold_physics/hp_probe.py`: their world on
their empty table with D9's values, the pipeline's own pick primitives
(`robot_utils.close_gripper`, `move_robot_smooth` with settle,
`close_gripper_until_contact` at 60 N with GRIP_SQUEEZE, the 10 cm lift)
and the pipeline's carry home as loss_dynamics recorded it (the straight
joint line from the post-lift readback to DEFAULT_ARM_POS in 9 equal
pairs, each streamed by `move_robot_smooth`, settle on the last, then the
home hold with HOME_HOLD_STEP_CAP and 120 more steps), with a per-step
record of the pad normal forces, the contact points and normals, the
body's pose in the hand frame and the finger joints. Each lever sees the
same trial draws (a cell of W, a grasp yaw, the body's yaw offset against
the pinch uniform in +-10 deg, its centre within +-2 mm). "Loss" is a grip
not held (both pads, >= 0.5 N summed, the `_verify_holding` rule) 120 steps
after the home hold; brackets are Wilson 95 % intervals. The work log
below (items 1 to 23) holds every command and number.

## 1. Diagnosis

### 1.1 Measured

1. **The probe reproduces the loss.** Base (the pipeline at 92d1e06):
   20 of 113 die carries lost, 17.7 % [11.8, 25.8] (the eval: 36 of 174,
   21 %). All 20 leave during the carry, none in the lift (item 9, 12).
2. **The 0.5 mm position hold has almost no force margin.** The fingers
   rest at their target (sink 0.89 mm in total, 0.45 mm per finger past
   the measured half-width) at 2.9 N median, and in 33 of 38 base carries
   a pad reads 0.00 N at some step (item 8). The hold's force is set by
   how far the target sits inside the TRUE surface, and that is between
   0 and 0.5 mm, because the close counts a pad point up to 0.5 mm away
   as contact (`robot_utils.py` 1177, `c[8] <= 0.0005`) and then holds
   0.5 mm inside that reading (1182). So the force collapses to 0 N
   whenever the die shifts or turns by a few hundredths of a millimetre.
   Two loss shapes at base: 8 of 20 a slip at low force (both pads under
   1 N, the die slides 4 to 6 mm along the pads), 12 of 20 under force
   (the die turns 16 to 33 deg, one pad on one point, the fingers pushed
   apart 0.14 mm) (item 8, 12).
3. **A firmer grip expels the die at 50 solver iterations, and that is a
   solver artefact.** Squeeze 1 / 2 mm: 80 / 99 % lost; force-limited
   holds of 5 / 10 / 20 N: 43 / 96 / 100 % lost, up to 92 of 113 already
   in the lift (item 9, 12). The same 10 N hold loses 0 of 113 with 500
   iterations, 0 of 113 with the die's mass x10, 0 of 113 with its inertia
   x10 (item 13). A sharp box primitive of the die's extents, mass and
   friction behaves the same way (10 N: 98 %; base 38.1 %, worse than the
   hull), so the hull's rounded edges are not the cause (item 13). The
   iteration count needed grows with the force: 10 N holds from 100
   iterations on (0 of 113 at 100, 200, 300), 20 N needs 200 (90 % lost at
   100, 0 % at 200 and 500), 60 N fails at 200 (98 %) (item 14, 19). With
   500 iterations even BF#38's 3 mm position squeeze loses only 4.4 %
   (88 to 100 % at 50) (item 14). PyBullet's default is 50 (their world
   and ours, item 6).
4. **The solver alone does not fix the 0.5 mm hold.** 200 / 500
   iterations with the 0.5 mm hold: 18.6 / 15.9 % lost (base 17.7 %); the
   resting force rises to 11 / 27 N but the zero-force steps stay (item 9,
   14).
5. **A force-limited hold needs the fingers coupled.** Without coupling,
   every force-limited hold leaves the fingers 3.7 to 4.3 mm off centre at
   home (median, 113 holds each; 0.00 mm at base) (item 19). The episode
   s1_f20_i200 shows the mechanism: each finger's motor is limited on its
   own, so the finger pair and the die slide along the pinch axis until
   one finger reaches its target, and during the swing the pair sloshes
   from side to side (one finger 6.6 to 15.9 mm while the other mirrors
   it; off centre 2.46 mm median, 5.32 mm max over 429 carry steps) (item
   18, 19, 22). Their URDF declares the coupling: `panda.urdf` line 356,
   `panda_finger_joint2` carries `<mimic joint="panda_finger_joint1"/>`
   (pybullet_data's URDF is the same file, item 2). PyBullet ignores
   `<mimic>`; a JOINT_GEAR constraint with gearRatio -1 realises it
   (q2 = q1 within 0.01 mm when only finger 1 is driven; +1 does not)
   (item 20). With the gear the off-centre shift is 0.00 mm for every
   force-limited hold (item 21) and 0.006 / 0.008 mm max in the two gear
   episodes (item 22).
6. **The combination that holds every body tested.** Coupled fingers +
   200 iterations + a 10 N force-limited hold: die 0 of 113 [0, 3.3],
   40 mm cube 0.5 kg 0 of 57 [0, 6.3], cube 0.1 kg 0 of 57, cup a 0 of 57;
   sink at home -0.38 mm median for the die (the pads do not dig in; the
   negative values are bodies turned to a wider support) (item 21). Under
   the lock, with the driver unchanged and the fix wrapped in
   (ep_probe.py): laptop seeds 6 and 1 held at home (their reward 1.0);
   the die turned at most 9.9 and 3.1 deg in the hand (s6_r1 at defaults:
   94 deg, lost); the minimum pad force per pair 5.6 to 8.4 N on seed 1,
   with three short dips to 0.0 to 0.24 N on seed 6 that the die survived
   (item 22). On these two scenes loss_dynamics recorded 1 of 4 held at
   defaults. Three episodes are an existence check, not a rate.
7. **Rolling friction is zero at the pads, and it matters at low force.**
   PyBullet combines rolling and spinning friction as a_x * b_lateral +
   a_lateral * b_x, not as a product (combine_test.py, a sphere on a
   plate: the sphere's value alone or the plate's alone give the same
   9.21 rad/s left of 10, both give 8.43, halving the other body's lateral
   friction halves the effect) (item 10). So today: spinning at the pads
   0.1 x 1.0 + 1.2 x 0 = 0.1 (torsion about the pinch axis is resisted;
   die spinning 0.1 / 1 / 10 changes nothing: 20 / 20 / 22 %), rolling
   0 x 1.0 + 1.2 x 0 = 0 (item 9, 10). Pad rolling 0.001 / 0.01 / 0.1:
   14.2 / 4.4 [1.9, 9.9] / 0.9 % lost; die rolling 0.003 / 0.01 / 0.1:
   9.7 / 3.5 / 3.5 %; their table's set_dynamics values on the die
   (rolling 0.01, spinning 1.0; `panda_env_utils.py` 735 to 741): 3.5 %
   [1.4, 8.7] (item 11). With rolling resisted, the held carries' minimum
   pad force rises from 0.00 to 0.69 N (median) (item 12). Rolling
   friction does not help the cubes (pad rolling 0.01: 50.9 / 40.4 %
   against 57.9 / 45.6 %) and cannot save a firm grip at 50 iterations
   (die rolling 0.01 with 10 N: 80.5 %) (item 11, 17).
8. **Our own 40 mm cubes lose to the 0.5 mm hold when the grasp yaw is
   off.** Base, 0.5 kg cube, losses by the cube's yaw against the grasp
   yaw 0 to 3 / 3 to 6 / 6 to 10 deg: 0 of 19, 10 of 15, 23 of 23 (0.1 kg:
   0 of 19, 6 of 15, 20 of 23); 29 of 33 are slips at low force with the
   pads on the cube's vertical edges (item 17). Cups a and c: 5.3 % and
   3.5 % at base. Q14's acceptance on our own scenes was never run
   (`robot_utils.py` 1131), and BF#38's blocks held in a gentler carry.
   With the coupled 10 N hold at 200 iterations the cubes lose 0 of 57 at
   every yaw tested (item 21).
9. **Loss grows with time in the hand, not with peak acceleration.** The
   carry at half speed loses 35.4 % (40 of 113, 36 under force), twice the
   base (item 9, 12).
10. **Levers that do not help:** finger kp 1 / 0.3, kd 0.3 (16 to 20 %);
   substeps 2 / 4 / 8 (12 / 11 / 29 %, no trend); pad contact stiffer or
   less damped (k 3e5, d 100, d 25, rigid: 98 % each); soft contact on the
   die (66 %); pad friction anchor off (76 %, so the URDF's anchor is
   protective and must stay); the close's contact tolerance at 0 (50 %,
   the hold then presses harder and the artefact of 3 expels the die)
   (item 9).

### 1.2 Inferred, not measured

- The mechanism behind 3: projected Gauss-Seidel at 50 iterations does
  not balance two opposing contact impulses on a 5.2 g, 2.3e-7 kg m^2 body
  between two 0.1 kg fingers with 4e-5 kg m^2 (mass ratio 19, inertia
  ratio about 180), and the residual spins the body out of the pinch. The
  evidence is the cure (iterations, mass, inertia each remove it), not a
  look inside the solver.
- The rotation-out that loss_dynamics recorded (the die turns 60 to 100
  deg, then a junction unloads the pads) is the same artefact at the light
  0.5 mm hold, plus the rolling of the hull on its rounded edges during
  the zero-force steps: both cures (iterations with a hold that keeps
  pressing, or rolling friction) cut the loss, and the die's inertia x10
  cuts the held carries' turn from about 9 deg to 2 deg (item 12).
- The "1.6 mm width offset" (item 4) is made of three parts: up to 0.5 mm
  of the contact tolerance, up to 0.44 mm of the close's 0.5 mm stepping
  (the measured half-widths are quantized at 10.32, 10.76, 11.19, 11.63
  mm, item 8), and about 1.1 mm per finger of finger geometry (the joint
  value at which a pad meets a surface 8.78 mm from the centre; derived
  from the closest-point distance between the two finger links, which may
  sit off the pad faces). One reading is not explained: in s1_f20_i200
  (no gear, 20 N) both fingers reached the 6.4 mm target during the lift
  while the pad contacts stayed at |x| 9.3 mm in the die frame (item 18,
  19); the gear episodes show no such sink (0.06 and 0.25 mm median).
- The die is not "rolled out because its hull is round": the sharp box
  loses more at base (38.1 against 17.7 %).

## 2. Proposed fixes

Four switches. The first three work together: `force_hold` is harmful
alone (10 N at 50 iterations: 96 % lost; without the coupling the fingers
slosh), so the registry should declare `force_hold` to imply
`finger_gear` and `solver_iters`, and the eval arm "force_hold" runs all
three. `finger_gear` and `solver_iters` alone are predicted to leave the
loss rate where it is; they get their own arms so the cost and the side
effects of each are measured. `pad_rolling` is independent.

### 2.1 `finger_gear`: couple the two fingers as their URDF declares

Mechanism: 1.1 item 5. The two finger joints are independent in PyBullet,
so any force-limited hold lets the pair and the held body slide along the
pinch axis, and the close pinches an off-centre body off centre.

Change: with the switch on, create one JOINT_GEAR constraint between the
two finger joints of the executing robot, gearRatio -1, erp 0.1,
maxForce 50 (the values gear_test.py checked):

    gc = p.createConstraint(robot, f1, robot, f2, jointType=p.JOINT_GEAR,
                            jointAxis=[1, 0, 0], parentFramePosition=[0, 0, 0],
                            childFramePosition=[0, 0, 0], physicsClientId=c)
    p.changeConstraint(gc, gearRatio=-1, erp=0.1, maxForce=50, physicsClientId=c)

- their world: `tampura_bridge/policy.py` `d9_setup` (64 to 79), after the
  finger loop (74 to 79, the pad friction and the reset to FINGER_OPEN),
  on the executing client `c`, so it exists before any step;
- our world: `boxel_env.py` after the pad friction loop (917 to 919) on
  `self.client_id`, the physics client, at robot load (900). The DIRECT
  plan client answers collision queries only and gets no constraint.
- Both pipeline call sites command both fingers to the same target
  already (close_gripper 1110 to 1118, close_gripper_until_contact 1167
  to 1169 and 1184 to 1186, open_gripper 1059 to 1065), so the gear
  agrees with every motor command; nothing else changes.
- Two new pybullet writes need reviewed lines in
  tools/bridge_gates_allowlist.txt (createConstraint, changeConstraint).

Section 5 rule 2: TAMPURA-matched (their URDF, `panda.urdf` line 356,
`<mimic joint="panda_finger_joint1"/>`; the real hand drives both fingers
from one motor) and pipeline-wide (our world gets the same constraint).

Expected effect alone: none on the loss rate (die 13.3 % [8.2, 20.8]
against 17.7 %, cubes 57.9 / 54.4 %, cup a 5.3 %, item 21). It is the
precondition of 2.3. Time: none measurable.

Falsify: with the switch on, q1 - q2 exceeds 0.05 mm in any carry of the
eval, or the grip-verification failure rate per pick (execution.py 1240
"pad contacts" and 1283 "width implausible") rises above base's on the
paired seeds.

Risk to our own scenes: the close now centres the body: the first pad to
touch pushes it toward the hand's centre until the second pad touches
(the real hand does the same). A light body near a neighbour can be
nudged; a pick whose arrival is off by more than the pre-grasp clearance
fails as now. One unexplained grip-verification miss happened in the
seed-6 gear episode (a second pick of e_cups_ud at its placed spot, pads
on nothing); whether the gear contributed is open (section 3).

Effort: 1.5 hours (two call sites, a unit test that drives finger 1 only
and reads q2, the allowlist lines).

### 2.2 `solver_iters`: 200 solver iterations on the executing world

Mechanism: 1.1 item 3. At PyBullet's default of 50 the solver does not
converge for a 5 g body squeezed between two 0.1 kg fingers, and any grip
firmer than a few newtons expels it.

Change: with the switch on, `p.setPhysicsEngineParameter(
numSolverIterations=200, physicsClientId=...)`:

- their world: `d9_setup`, right after `setTimeStep` (68), on `c`;
- our world: `boxel_env.py` right after `setGravity` on the physics
  client (556).
- A named constant SOLVER_ITERATIONS = 200 beside SIM_TIMESTEP in
  robot_utils.py, cited to this entry. One new pybullet write for the
  allowlist.

Section 5 rule 2: root-cause (solver convergence, not a robot setting) and
pipeline-wide (every scene's executing world). D9 already sets "our
gravity and timestep" on their world; the solver setting joins them.

Expected effect alone: no change of the loss rate with the 0.5 mm hold
(18.6 % at 200, 15.9 % at 500, item 9); it removes the firm-grip
expulsion (3 mm squeeze at 500 iterations 4.4 % against 88 to 100 %).
Time: the probe ran the same 28 picks and carries in 25.1 / 46.9 / 52.0 s
at 50 / 200 / 500 iterations, about 1.0 / 1.9 / 2.1 ms per step on a
shared machine (item 15): +0.9 ms per step at 200. An episode steps 3.8k
to 12.8k times in dispatch (the five loss_dynamics runs and my three), so
+3 to +12 s per episode; the 600 s capped tail (s1_r3: 43k steps) gains
about +39 s, which can push a borderline episode into the cap. Against
eval walls of 45 to 180 s per finished episode that is 5 to 15 %.

Falsify: the eval's wall median of the solver_iters arm exceeds base's by
more than 20 %, or any G gate changes, or our own scenes' place accuracy
(G4) or stack outcomes move.

Risk to our own scenes: every contact converges further; stacks and
pushed cups settle differently but not worse in any probe I ran (cups a
and c: 5.3 / 1.8 % against 5.3 / 3.5 %, cubes 45.6 % against 57.9 /
45.6 %, item 17, 60 trials each). Not measured: tower stacks and pushes.

Effort: 1 hour.

### 2.3 `force_hold`: a force-limited hold after the tactile close

Mechanism: 1.1 items 2 and 8. The 0.5 mm position hold's force is set by
an uncontrolled sub-millimetre penetration and collapses to 0 N whenever
the body shifts; the die and our yawed cubes leave in those windows.

Change (`robot_utils.close_gripper_until_contact`, 1135 to 1194): with
the switch on, when both pads report contact (1180), the measured
half-width is recorded and returned exactly as now (1181, 1191), but the
hold (1182 to 1190) targets `max(0.0, width - HOLD_REACH)` with
HOLD_REACH = 4 mm at a motor budget of HOLD_FORCE = 10 N per finger
instead of `width - squeeze` at the close's 60 N. The target sits far
enough inside that the motors stay saturated: each pad presses with its
10 N whatever the body's width does, and the fingers follow the body
instead of letting go. The motor target persists across steps, so the
hold lasts through the lift and the carry with no re-assertion, as now.
GRIP_SQUEEZE and --grip-squeeze-mm are ignored while the switch is on
(printed in the run header). The value: 10 N is the smallest tested force
that holds the heaviest body of our scenes, the 0.5 kg cube (5 N: 22.8 to
47.4 % lost; 10 N: 0 of 57 with the gear), at a friction capacity of
2 x 1.2 x 10 = 24 N against its 4.9 N weight, and well inside the Franka
hand's 70 N continuous; 20 N also holds everything at 200 iterations
(item 19, 21), 60 N does not (98 % for the die).

What else reads the hold and must still work:
- the grip verification (`execution.py` 1235 to 1264): both pad links in
  contact; unchanged, the pads press harder;
- the width plausibility (1276 to 1290) reads `measured_half`, the
  returned close width, unchanged;
- the post-lift re-verify (1325 to 1344, `lift_pads` 1333): both pads;
  unchanged;
- `_verify_holding` (`test_full_pipeline.py` 242, the 0.5 N floor at
  310): the summed force is about 20 N (probe nf_home median 19.8 N);
- the place: `open_gripper` (`robot_utils.py` 1033) commands both fingers
  to 0.04 m at 200 N, which overrides the hold; the release verify in
  `_release_and_verify_drop` (`execution.py` 553) reads fingers >= 0.038;
- a body that leaves the hand now lets the fingers close to the 4 mm
  target, a clean proprioceptive loss signal; loss_dynamics' proposed
  `carry_grip_watch` (finger widening > 0.05 mm) needs its threshold
  re-measured under this hold, because force-limited fingers follow the
  body's width (widening up to 0.7 mm without a loss, item 12).

The probe applied the force hold after the close's 60-step position hold
(hp_probe.py lines after the close); the change above replaces those 60
steps. The implementation's unit test must re-run the probe's die,
0.5 kg cube and cup rows through the changed function.

Section 5 rule 2: root-cause (the hold's control law) and pipeline-wide
(every pick of every scene goes through this function). It is not a raise
of the grip force for find_dice: the motor budget falls from 60 to 10 N
everywhere and the law changes from position to force. Their carry is
kinematic (`enforce_grasp`, BF#35), so they have no hold force to match.

Expected effect (with 2.1 and 2.2 on): the loss per die carry from 21 %
(36 of 174 in BF#53) to near zero: the probe 0 of 113 [0, 3.3], the
episodes 3 of 3 held. To be real against the replication's variance it
must bring the eval's loss per carry under 10 % (at most 17 of about 174
carries); 5 or fewer would be clearly significant. Time: none of its own;
the episodes that lost the die and failed now finish as successes.

Falsify: a carry loss with "links none" in more than 5 % of the eval's die
carries with all three switches on; or a grip-verification or
post-lift-re-verify failure rate per pick above base's; or any of our own
scenes' holding or stack seeds that base delivers failing.

Risk to our own scenes: in the probe the cubes and cups improve (0.5 kg
cube 57.9 to 0 %, 0.1 kg 45.6 to 0 %, cup a 5.3 to 0 %, 57 grips each,
item 21). Not measured: placing under a 10 N grip (the open is the same),
towers where a pressed cube must not be squeezed off its support, bodies
heavier than 0.5 kg (none in our scenes).

Effort: 2.5 hours (the change, the constants, a unit test with a box
between the pads checking the summed force and the centred fingers after
a swing, the run-header line).

### 2.4 `pad_rolling`: rolling friction at the pads, their table's value

Mechanism: 1.1 item 7. Nothing resists rolling at a pad contact (combined
rolling 0), so a body held on one to four points rolls on its rounded
edges in the zero-force windows of the light hold.

Change: with the switch on, the two finger links get
`rollingFriction=0.01` next to the pad lateral friction: `d9_setup` 75 to
77 and `boxel_env.py` 918 to 919. By the combination rule (item 10) every
pad contact then resists rolling with 0.01 x the body's lateral friction
(0.01 for every task body at lateral 1.0). The alternative with the same
citation is to give every task body their table's full set_dynamics
triple (lateral 1.0, spinning 1.0, rolling 0.01): 3.5 % [1.4, 8.7] for the
die, not run on cubes.

Section 5 rule 2: TAMPURA-matched value (their `create_default_env`,
`panda_env_utils.py` 735 to 741, sets rollingFriction=0.01 and
spinningFriction=1.0 on the bodies it configures; it sets them on the
table, not on the pads, so the value is theirs and its placement on the
pads is ours) and pipeline-wide (both worlds).

Expected effect alone: the die's loss per carry from 17.7 % to 4.4 %
[1.9, 9.9] in the probe (113 grips); with 2.1 to 2.3 on it adds nothing
measurable (0 of 113 either way, item 14). Time: none. It is the only
lever that helps the die without changing the hold, so it is the
fallback if 2.3 is rejected.

Falsify: the eval's loss per carry of the pad_rolling arm not below base's
on the paired seeds (it should land near 5 %, at least below 12 %).

Risk to our own scenes: none measured (cubes 50.9 / 40.4 % against 57.9 /
45.6 %, cups 5.3 / 3.5 % against 5.3 / 3.5 %, 57 grips each, item 17); it
does not save a yawed cube.

Effort: 1 hour.

## 3. What I would measure first with one more hour

1. The implementation path on our own world: the three switches 2.1 to
   2.3 in `boxel_env`'s robot with a random-pairs holding seed and a stack
   seed headless, to see a pressed cube placed on a tower and released,
   which no probe here covered.
2. Whether the gear's centring push caused the seed-6 grip-verification
   miss: replay that pick (e_cups_ud at its placed spot) with and without
   the gear and read the pad contacts during the close.
3. A clean per-step cost of 100 against 200 iterations on an idle machine,
   and the coupled 10 N hold at 100 iterations on the die (not run with
   the gear): if it holds, 100 halves the time cost.

## 4. Data generated and deleted

Under `archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/hold_physics/`,
none of it tracked, 16,493,819 B in 241 files after the deletion:

- scripts, 50,687 B: hp_probe.py (the probe), run.sh, py.sh, sweep.sh,
  own_scenes.sh, gear_sweep.sh, show.py, shapes.py, sink.py,
  offcentre.py, fingers_trace.py, peek.py, inspect_bodies.py,
  combine_test.py, gear_test.py, ep_probe.py, ep.sh;
- out/*.json, 11,517,527 B in 167 files: sweeps A (41 levers), B, C, Cbox,
  D, E_<body> (own scenes), F, Fc, G, G_<body> (gear) and T (timing), the
  per-trial rows behind every table in section 1; kept until the review
  phase has read them (the campaign ledger row says so), then the review
  decides which summaries become tracked evidence;
- runs/s1_f20_i200 (1,718,835 B), runs/s6_gear_f10_i200 (1,205,807 B),
  runs/s1_gear_f10_i200 (2,000,963 B): carry.jsonl, stdout.txt and save/
  of the three episodes under the lock; the carry.jsonl and stdout.txt of
  each stay with the out/ files, save/ becomes garbage once the review has
  read item 22.

Deleted (item 23): out/smoke.json (194,991 B, superseded by sweep A),
out/base_line.json (27,737 B, superseded by A_base), the 109 out/*.log
stderr captures of the sweeps (58,271 B): 111 files, 280,999 B.

## Appendix: work log

1. Read the brief, BF#38, BF#48, robot_utils.close_gripper_until_contact
   (1135), move_robot_smooth (877), hold_at_config (1001), the q14 and
   carry-watch probes, task_spec and policy.d9_setup.
2. Their Panda URDF (WSL /root/tampura-work/tampura_environments/models/
   srl/franka_panda/panda.urdf, lines 288 to 356, identical to
   pybullet_data's franka_panda): each finger link carries a `<contact>`
   block with `friction_anchor`, `stiffness 30000`, `damping 1000`,
   `spinning_friction 0.1`, `lateral_friction 1.0` (D9 overwrites lateral
   with 1.2 and nothing else), mass 0.1 kg and inertia 0.1 kg m^2 per
   finger. The pad contacts are therefore SOFT (Bullet turns k, d into
   erp = dt k / (dt k + d) = 0.111 and cfm = 1 / (dt k + d) = 8.9e-4 at
   240 Hz), and the damping is 40 times the critical damping of the die on
   that spring (2 sqrt(k m) = 25 N s/m).
3. Their die: create_ycb('dice') builds a mesh body from
   models/srl/ycb/062_dice/google_16k/textured_vhacd.obj (one convex hull,
   64 vertices, rounded edges), no contact block, so spinning and rolling
   friction 0, no anchor; D9 sets mass 5.2 g, the declared inertia and
   lateral friction 1.0.
4. The BF#38 0.5 mm level (archive/.../BF38_q14/sq0.5mm.json): the close
   measured the axis-aligned die at a half-width of 10.42 to 10.52 mm
   (median 10.5) against its 8.8 mm half extent, so the measured width
   carries a 1.6 mm offset that is not the die; median pad force at the
   close 27.8 N on the still massless body.
5. (resumed 2026-10-31 by the second agent on this angle) The smoke
   (out/smoke.json, lever base, direct carry, 3 trials): 2 held, 1 lost in
   the carry; at the loss the die had turned 16.9 deg about the pinch axis
   and 28.6 deg about the other axes while both pads still pressed 5.2 and
   6.3 N, so the die rotates out under a full grip; the held trial 0 also
   turned 34 deg. Read loss_dynamics.md: its three recorded pipeline
   losses are the same rotation out (pad contact on one to four points,
   force rising to 7 N while the pads are pushed apart 0.15 to 0.23 mm).
   Its carry.jsonl shows the pipeline's carry home is a straight joint line
   cut into 9 equal waypoints (dq per pair identical), joint 7 turning
   0.45 rad per pair, about 3.6 rad in all at 2.5 rad/s: the hand spins
   about its approach axis for the whole swing.
6. inspect_bodies.py (py.sh inspect_bodies.py, print only):
   - pads 12, 13: mass 0.1, lateral 1.2, rolling 0, spinning 0.1,
     stiffness 30000, damping 1000; collision mesh finger.obj.
   - die: mass 5.2 g, declared inertia 2.34e-7, 2.35e-7, 2.24e-7 kg m^2
     (a solid 17.6 mm cube of 5.2 g: 2.68e-7, so the declared value is
     right within 15 %), lateral 1.0, rolling 0, spinning 0, no stiffness
     or damping, margin 0.
   - hull: 64 vertices, extents 17.55 x 17.27 x 17.83 mm, centred on the
     base within 0.15 mm. Support distance from the centre along an xy
     direction at 0 / 15 / 30 / 45 deg from a face normal: 8.78 / 10.01 /
     10.84 / 10.93 mm (a sharp cube: 8.80 / 10.78 / 12.02 / 12.45): the
     vertical edges are rounded with a radius of roughly 3 mm. The +x face
     is not flat: only 4 hull vertices lie within 0.3 mm of the support
     plane, all in one corner (y 3.1 to 7.0 mm, z -2.8 to 7.0 mm), 9 within
     1 mm. So a pad on a face touches a small off-centre patch, not the
     face.
   - finger geometry: the gap between the two finger links is 2 q - 2.2 mm
     (q = 0: overlap 2.21 mm; q = 8.9 mm: 15.59 mm; q = 10.2 mm: 18.19 mm).
     A 17.55 mm die is touched at q = 9.88 mm. The close's contact test
     counts a pad point at a distance up to +0.5 mm (robot_utils.py 1177,
     c[8] <= 0.0005), so the measured half-width reads up to 0.5 mm early;
     the "1.6 mm offset" of item 4 is 1.1 mm of finger geometry plus up to
     0.5 mm of the contact tolerance, and GRIP_SQUEEZE = 0.5 mm then puts
     the hold target between 0 and 0.5 mm inside the true surface. That is
     why the resting force spreads from 1 to 8 N: it is set by where inside
     the 0.5 mm window the close happened to stop.
   - Bullet combines spinning friction as the product of the two bodies'
     values (btManifoldResult::calculateCombinedSpinningFriction): pad
     0.1 x die 0 = 0, so the pads exert no torsional friction on the die;
     rolling is 0 x 0 = 0. (Code knowledge of Bullet 3; checked by the
     lever diespin below.)
7. hp_probe.py extended (resumed agent): carry mode `line` (the default
   now), the pipeline's carry home as loss_dynamics recorded it, the
   straight joint line from the post-lift readback to DEFAULT_ARM_POS cut
   into 9 equal pairs, each streamed by robot_utils.move_robot_smooth
   (steps 30, velocity-stretched, settle on the last), then the home hold
   (HOME_HOLD_STEP_CAP) and 120 more steps; the die's rotation now in the
   hand frame per axis (x, y = pinch, z = approach), the peak pad force and
   the finger widening during the carry; new levers (die spinning 0.1 / 1
   / 10, rolling, pad anchor off, die mass x10 / x100, iterations 10 / 500,
   substeps 2 / 8, the close's contact tolerance 0 with squeeze 0.5 /
   0.25 / 0.1 mm, force-limited hold 2 N, soft contact on the die).
   Commands: `bash probes/hold_physics/run.sh --lever <l> --trials <n>
   --carry line --out <json>`; `sweep.sh <tag> <n> line <par> <levers..>`
   runs several in parallel and prints the summary (show.py --summary,
   loss = grips not held 120 steps after the home hold, Wilson 95 %).
8. Base, 40 trials, line carry (out/base_line.json): 38 grips, 32 held at
   home, 31 held after 120 more steps: loss 7/38 = 18 %, close to the
   eval's 21 % per carry. The measured half-width is quantized by the
   close's 0.5 mm stepping: 10.32 mm (die yaw within 4 deg of the pinch),
   10.76, 11.19, 11.63 mm (larger yaw offsets). With the true touch at
   q = 9.88 mm the hold target 9.82 mm sits 0.06 mm inside the die; the
   fingers rest at 9.87 mm. Every carry, held or lost, has steps with
   0.0 N on a pad (nf_min_carry 0 in 33 of 38). Two loss shapes:
   (a) slip at zero force: both pads near 0 N, rotation under 15 deg, the
   die slides 4 to 6 mm along the pad plane (hand x and z) and falls
   (trials 9, 12, 20, 34; recovered in 2, 6, 8, 30, 36); (b) rotation
   under full force: 5 to 6.6 N, the die turns 16 to 33 deg, one pad on one
   point, the fingers pushed apart 0.14 mm (trials 14, 29; 17 left after
   the hold, 33 turned 47 deg and stayed).
9. Sweep A (sweep.sh A 120 line 10 <41 levers>, out/A_<lever>.json, the
   same 120 trial draws per lever, 113 grips each; loss = not held 120
   steps after the home hold; Wilson 95 % in brackets):
   base 17.7 % [11.8, 25.8]; force-limited hold (target 4 mm inside the
   measured width, motor budget F): F 2 N 0.0 % [0, 3.3], 5 N 43 %,
   10 N 96 %, 20 and 40 N 100 %; squeeze 0 / 1 / 2 mm: 32 / 80 / 99 %;
   die rolling 0.01 with pad rolling 1.0 (roll0.01): 1.8 % [0.5, 6.2];
   die rolling 0.001 (dieroll): 15.0 %; die spinning 0.1 / 1 / 10: 20 / 20
   / 22 %; pad friction anchor off: 76 %; die anchor on: 13 %; pad contact
   stiffer or less damped (k 3e5, d 100, d 25, rigid): 98 % each; soft
   contact on the die too: 66 %; iterations 10 / 200 / 500: 51 / 19 / 16 %
   (the resting force rises to 11 and 27 N with the iterations, the loss
   does not move); substeps 2 / 4 / 8: 12 / 11 / 29 %; finger kp 1 / 0.3,
   kd 0.3: 20 / 20 / 16 %; carry at half speed: 35 %; die inertia x10:
   7.1 %; die mass x10 / x100: 12 / 31 %; the close's contact tolerance 0
   with squeeze 0.5 / 0.25 / 0.1 mm: 50 / 27 / 25 %.
10. Correction to item 6: Bullet's combination rule is not the product.
   combine_test.py (a sphere spun or rolled on a plate, values 2e-5 so the
   deceleration is partial) shows combined = a_x * b_lateral + a_lateral *
   b_x for both spinning and rolling (sphere-only and plate-only give the
   same 9.21 rad/s left of 10, both give 8.43, halving the other body's
   lateral friction halves the effect). So pad and die today: spinning
   0.1 x 1.0 + 1.2 x 0 = 0.1 (the pads DO resist torsion about the pinch
   axis, which is why the spinning levers do nothing), rolling 0 x 1.0 +
   1.2 x 0 = 0 (nothing resists rolling). roll0.01 above is combined
   1.0 x 1.0 + 1.2 x 0.01 = 1.01; dieroll is 1.2 x 0.001 = 0.0012.
11. Sweep B (sweep.sh B 120 line 9 ..., out/B_<lever>.json), rolling graded
   (combined value in brackets) and combinations, loss per grip, 113 grips:
   die rolling 0.003 (0.0036) 9.7 % [5.5, 16.6]; die rolling 0.01 (0.012)
   3.5 % [1.4, 8.7]; die rolling 0.1 (0.12) 3.5 %; pad rolling 0.001
   (0.001) 14.2 %; pad rolling 0.01 (0.01) 4.4 % [1.9, 9.9]; pad rolling
   0.1 (0.1) 0.9 % [0.2, 4.8]; their table's set_dynamics values on the
   die (rolling 0.01, spinning 1.0; panda_env_utils.py 735 to 741)
   3.5 %; die rolling 0.01 with squeeze 1 mm 9.7 %, with 3 mm 88.5 %; die
   rolling 0.01 with a force-limited hold of 5 / 10 / 20 / 60 N: 4.4 /
   80.5 / 98.2 / 98.2 %; pad rolling 0.01 with 10 N: 78.8 %; die rolling
   0.01 at half carry speed 3.5 %; force-limited hold alone 1 / 3 N:
   0.9 / 3.5 %.
12. shapes.py on A and B (loss shape, rotation per hand axis, the die's yaw
   offset): base: 20 lost, 8 as a slip at low force (both pads < 1 N at
   the event), 12 under force; held carries turn 3.6 / 8.6 / 7.3 deg
   about hand x / y (pinch) / z (approach) and their minimum pad force in
   the carry is 0.00 N (median); losses by the die's yaw offset 0 to 3 /
   3 to 6 / 6 to 10 deg: 3/33, 2/30, 15/50. Die rolling 0.01: the held
   carries' minimum pad force rises to 0.69 N (median; the zero-force
   steps disappear), 4 losses, all at yaw offsets over 6 deg. Pad rolling
   0.1: minimum 0.79 N, 1 loss. Die inertia x10: the held carries turn
   only 0.9 / 1.8 / 2.9 deg, 8 losses, all low-force slips. Force-limited
   hold at 10 N or squeeze 2 mm: every loss is under force, 39 and 92 of
   them already in the 10 cm lift (the die is expelled, not dropped).
   Half carry speed: 35 % (40 lost, 36 under force): a longer carry loses
   more, so the loss grows with the time in the hand, not with the peak
   acceleration.
13. Sweep C (out/C_<lever>.json; Cbox: BODY=boxdie, the die replaced by a
   sharp box primitive of its extents, mass and lateral friction):
   force-limited hold 10 N (78 to 98 % lost with default settings) loses
   0/113 [0, 3.3] with 500 solver iterations, 0/113 with the die's mass
   x10, 0/113 with its inertia x10; 13 % with 4 substeps; 77 % with pad
   rolling 0.1. Squeeze 3 mm with pad rolling 0.1 / 0.01: 91 / 89 %.
   The box die: base 38.1 % [29.6, 47.3] (worse than the hull's 17.7 %),
   force 10 N 98 %, squeeze 2 / 3 mm 96 / 100 %, pad rolling 0.01 25.7 %,
   force-limited 2 N 0/113. So the expulsion under a firm grip is not the
   hull's rounded edges: a sharp box of the same mass is expelled the same
   way, and it goes away when the solver converges (500 iterations) or
   the body is heavier or stiffer in rotation. It is a projected
   Gauss-Seidel convergence artefact of a 5.2 g, 2.3e-7 kg m^2 body
   squeezed between two 0.1 kg fingers (mass ratio 19, inertia ratio
   about 180 against the finger's 4e-5): at 50 iterations the two
   opposing contact impulses do not balance and the residual spins the
   body out of the pinch. Rolling friction helps the light hold (the
   hull rolls on its rounded edges) but cannot save a firm one.
14. Sweep D (out/D_<lever>.json): the force-limited hold with more solver
   iterations, 113 grips each: iterations 100 / 200 / 300 with 10 N: 0 / 0
   / 0 lost; 200 and 500 with 20 N: 0 / 0; 500 with 40 N: 0; 200 and 500
   with 5 N: 0 / 0; 200 and 500 with 10 N and pad rolling 0.01: 0 / 0
   (every one [0, 3.3]). The position hold with 500 iterations: squeeze
   3 mm 4.4 % (88 to 100 % at 50 iterations), 1 mm 39.8 %, 0.5 mm 15.9 %
   (sweep A). So two things are needed together: a converged solver
   (from 100 iterations on), and a hold that keeps pressing (a motor
   force limit below the 60 N budget with the target well inside); the
   0.5 mm position hold loses with any iteration count because its force
   collapses to 0 N whenever the die shifts by a few hundredths of a mm.
15. Timing (out/T_<lever>.json, 30 trials each, run one after another on a
   machine shared with other probes): base 25.1 s, 200 iterations 46.9 s,
   500 iterations 52.0 s for the same 28 picks and carries (about 1.0,
   1.9, 2.1 ms per step). A cleaner per-step figure is item 17.
16. Episode wrapper written (not yet run): ep_probe.py runs the unchanged
   driver with execution.close_gripper_until_contact wrapped (after the
   close, the fingers hold a target 4 mm inside the measured width at a
   motor budget of N newtons) and policy.d9_setup wrapped (numSolverIterations
   on the executing client), with loss_dynamics' recorder installed;
   ep.sh <seed> <tag> <N> <iters> runs one episode under
   /root/sb_pipeline.lock with a 600 s cap into probes/hold_physics/runs/<tag>.
   Own-scene sweep own_scenes.sh (40 mm cubes 0.1 and 0.5 kg, cups a and
   c, 60 trials per lever) running.
17. Own-scene bodies (own_scenes.sh, out/E_<body>_<lever>.json, 60 trials,
   57 grips each, the same draws: the body's yaw against the grasp yaw
   uniform in +-10 deg, its centre within +-2 mm, the pipeline's carry
   home). Loss per grip:
   | lever | cube 40 mm 0.5 kg | cube 0.1 kg | cup a | cup c |
   | base (0.5 mm position hold, 50 it.) | 57.9 % | 45.6 % | 5.3 % | 3.5 % |
   | 200 iterations | 45.6 % | 45.6 % | 5.3 % | 1.8 % |
   | pad rolling 0.01 | 50.9 % | 40.4 % | 5.3 % | 3.5 % |
   | force-limited 10 N (50 it.) | 3.5 % | 0 % | 0 % | 0 % |
   | 10 N, 100 it. | 3.5 % | 0 % | 0 % | 1.8 % |
   | 10 N, 200 it. | 3.5 % | 0 % | 0 % | 0 % |
   | 20 N, 200 it. | 0 % | 0 % | 0 % | 1.8 % |
   | 10 N, 200 it., pad rolling 0.01 | 3.5 % | 0 % | 0 % | 0 % |
   The cube losses at base are all yaw losses: 0/19 lost when the cube's
   yaw is within 3 deg of the grasp yaw, 10/15 at 3 to 6 deg, 23/23 at 6
   to 10 deg (0.5 kg; 0.1 kg 0/19, 6/15, 20/23); 29 of 33 are slips at
   low force (the pads touch the cube's vertical edges on one point each
   and the 0.5 mm position hold lets go). With 20 N and 200 iterations
   the 0.5 kg cube loses 0/57 at every yaw. So the 0.5 mm position hold
   (BF#44's default, pipeline-wide) holds our own cubes only when the
   grasp yaw is within about 3 deg, in this carry; Q14's acceptance on our
   own scenes was never run (robot_utils.py 1131). The force-limited hold
   makes cubes and cups hold at every yaw tested, and the die holds with
   it once the solver iterations are at 100 or more.
18. Episode 1 of 3 under the lock (ep.sh 1 s1_f20_i200 20 200; laptop seed
   1, scene 1747173590.312597, the scene where loss_dynamics recorded held,
   lost, lost at defaults): force-limited hold 20 N, 200 iterations.
   Outcome: "Done. I am holding dice at home", their reward 1.0 (G19 FAIL
   is the laptop scene mismatch, expected); 14 plans, 44 steps (41 done,
   3 failed: pose-commit refusals and a sense miss), 4 cup places at the
   planned centre (G4 PASS), planning 54.1 s, 124.9 s in all, 10534
   simulation steps. loss_dynamics/analyse.py on runs/s1_f20_i200/carry.jsonl:
   the die carry is the same 9-pair line (max |dq| 0.45 rad per pair, 2.54
   rad/s), the minimum pad force per pair 9.0 to 18.6 N (base runs: 0.0 N
   in most pairs), no pad break, but the die still turned 21 deg and
   drifted 7.3 mm in the hand over the carry while held; the fingers sat
   at 7.9 and 7.7 mm against the 10.4 mm measured half-width (item 19
   measures this sink).
19. Sweep F (out/F_*.json die 120 trials, Fc_*.json 0.5 kg cube 60 trials):
   die: force-limited 5 / 10 / 20 N at 200 iterations 0 / 0 / 0 lost;
   5 N at 100 iterations 0; 20 N at 100 iterations 90.3 %; 60 N at 200
   iterations 98.2 % (the iteration count needed grows with the force).
   Cube 0.5 kg: 5 N 47.4 % (100 or 200 it.; 5 N cannot carry 0.5 kg
   through the swing), 10 N 3.5 %, 20 N 0 %, 60 N 0 %.
   The sink (sink.py; 2 x measured half-width minus q1 + q2 at home, so
   positive = the pads closed past the measured width): base 0.89 mm;
   force-limited holds -0.3 to -2 mm median (the pads sit wider than the
   measured width, the body turned to a wider support), max 1.5 to 2.5 mm.
   But the two fingers no longer stay centred: the off-centre shift
   |q1 - q2| / 2 at home is 3.7 to 4.3 mm median for every force-limited
   hold (0.00 mm at base). The episode of item 18 shows why
   (fingers_trace.py on its carry.jsonl): with each finger force-limited
   on its own and both targets 4 mm inside, the finger pair and the die
   slide together along the pinch axis until one finger reaches its
   target (q 6.4 mm), the other then presses at the full budget (q up to
   16.6 mm), and during the swing the pair sloshes from side to side (one
   finger 6.6 to 15.9 mm while the other mirrors it). Nothing centres the
   pair because the two finger joints are independent in PyBullet.
20. Their URDF couples the fingers: panda.urdf line 356, panda_finger_joint2
   carries `<mimic joint="panda_finger_joint1"/>` (the real Franka hand
   drives both fingers from one motor). PyBullet ignores <mimic>. A
   JOINT_GEAR constraint between the two finger joints realises it:
   gear_test.py: gearRatio -1 (erp 0.1, maxForce 50) keeps q2 = q1
   within 0.01 mm when only finger 1 is driven (35.00 / 35.01 mm, 8.00 /
   8.01 mm); +1 does not. Lever `gear` added to hp_probe (the coupling in
   main after the robot setup); gear_sweep.sh runs the coupled levers on
   the die, the cubes and cup a (running).
21. Gear sweep (gear_sweep.sh; out/G_*.json die 120 trials, G_<body>_*.json
   60 trials). Loss per grip:
   | lever | die | cube 0.5 kg | cube 0.1 kg | cup a |
   | gear (0.5 mm position hold) | 13.3 % | 57.9 % | 54.4 % | 5.3 % |
   | gear, 200 it. | 17.7 % | 49.1 % | 49.1 % | 5.3 % |
   | gear, force 5 N | 3.5 % | 22.8 % | 0 % | 0 % |
   | gear, force 10 N | 91.2 % | 0 % | 0 % | 0 % |
   | gear, force 20 N | 100 % | 0 % | 0 % | 3.5 % |
   | gear, 200 it., force 5 N | 0 % | 22.8 % | 0 % | 0 % |
   | gear, 200 it., force 10 N | 0 % [0, 3.3] | 0 % [0, 6.3] | 0 % | 0 % |
   | gear, 200 it., force 20 N | 0 % | 0 % | 0 % | 0 % |
   | gear, squeeze 1 mm | 69.0 % | 35.1 % | 24.6 % | 1.8 % |
   | gear, 200 it., squeeze 1 mm | 75.2 % | 26.3 % | 22.8 % | 3.5 % |
   With the gear the off-centre shift at home is 0.00 mm median for every
   force-limited hold (3.7 to 4.3 mm without it, item 19). Sink at home,
   gear + 200 it. + 10 N: die -0.38 mm median (-1.42 to 1.61), cube 0.5 kg
   -0.40 mm (-3.56 to 3.83), cube 0.1 kg 0.15 mm, cup a -0.05 mm (the
   wider readings are bodies turned to a wider support; the 4 mm tails on
   the cubes are yawed cubes pinched on a vertical edge). The smallest
   combination that holds every body tested at every yaw tested is the
   coupled fingers + 200 solver iterations + a 10 N force-limited hold.
22. Episodes 2 and 3 of 3 under the lock, coupled fingers + 10 N
   force-limited hold + 200 iterations (HP_GEAR=1 ep.sh <seed> <tag> 10 200):
   seed 6 (laptop scene 1747173593.826745, lost at defaults in
   loss_dynamics s6_r1): held at home, their reward 1.0 (G19 FAIL is the
   laptop scene mismatch), 4 plans, 16 steps (15 done, 1 failed: a second
   pick of e_cups_ud at its placed spot whose pads touched nothing, the
   grip verification's "pad contacts=none" twice, then the replan picked
   the die), 2 cup places at the planned centre (G4 PASS), 6417 steps in
   dispatch, planning 40.1 s, 122.5 s in all; no pose-radius refusal (the
   cup loop of loss_dynamics 1.6 was not hit). Die carry (analyse.py on
   runs/s6_gear_f10_i200/carry.jsonl): 9 pairs of max |dq| 0.49 rad at
   2.54 rad/s; minimum pad force per pair 7.80/8.26, 0.16/0.00,
   7.56/6.81, 6.27/6.00, 6.09/6.61, 7.59/6.17, 3.34/3.03, 0.00/0.24,
   0.00/0.22 N, home hold 9.39/9.33 N; the die turned at most 9.9 deg
   (s6_r1 at defaults: 94 deg and lost) and drifted 1.36 mm in the hand;
   no pad break. offcentre.py: fingers off centre 0.000 mm median, 0.006
   mm max over 465 carry steps (without the gear, s1_f20_i200: 2.46 mm
   median, 5.32 mm max); sink against the post-lift width 0.06 mm median
   (-0.80 to 1.21 mm).
   Seed 1 (laptop scene 1747173590.312597): held at home, reward 1.0, 20
   plans, 56 steps (51 done, 5 failed: five "d_cups_ud's pose is too
   uncertain" refusals, the pose-radius loop of loss_dynamics 1.6), 4
   places at the planned centre, 12825 steps in dispatch, planning 92.9 s,
   172.1 s in all. Die carry: minimum pad force per pair 5.58 to 8.42 N in
   every pair (no zero), turn at most 3.1 deg, drift 0.41 mm max, off
   centre 0.008 mm max, sink 0.25 mm median (0 to 1.58 mm).
   Three episodes with a fix candidate on (s1_f20_i200, s6, s1): 3 of 3
   held; at defaults loss_dynamics recorded 1 of 4 held on these two
   scenes. Three episodes are not a rate; the probe tables are.
23. Deleted (garbage, findings in this log): out/smoke.json (194,991 B,
   item 5, superseded by sweep A), out/base_line.json (27,737 B, item 8,
   superseded by A_base), the 109 out/*.log files of the sweeps (58,271 B,
   stderr captures that repeat each json's summary line): 111 files,
   280,999 B. Remaining under probes/hold_physics: 16,493,819 B in 241
   files (out/*.json 11,517,527 B in 167 files; runs/s1_f20_i200
   1,718,835 B; runs/s6_gear_f10_i200 1,205,807 B; runs/s1_gear_f10_i200
   2,000,963 B; scripts 50,687 B).
