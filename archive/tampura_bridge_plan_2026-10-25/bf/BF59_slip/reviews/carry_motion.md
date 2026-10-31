# BF#59 review: carry_motion

Adversarial review of proposals/carry_motion.md (fixes `grasp_wrist_home`
and `carry_trapezoid`), 2026-10-31, checkout d021dad (branch
tampura-bridge). Read: BRIEF.md, STATE.md, the four proposals (hold_physics
in its finished form), the code at the lines below, the probe tables
(out/b5_*, out/b6_* re-analysed per trial and paired), the episodes'
carry.jsonl and console logs, hold_physics' and grasp_geometry's probe
outputs. One existing probe re-run (section 1, point 1; section 4). No
episode run, no edit outside reviews/, no git command that changes
anything.

## 0. Verdicts

| fix | mechanism supported | rules | detectable | own-scene risk | effort h | verdict |
|---|---|---|---|---|---|---|
| grasp_wrist_home | yes. The wrist unwind is real (168 to 199 deg in every recorded die carry). In the proposal's placed-die probe the flip alone is a null for the eval's class (wrist in range: 3 deg 44 vs 48 of 48, p 0.13; 10 deg 32 vs 26, p 0.31), but in grasp_geometry's real-pick probe, re-run by this review under today's stream, it holds 55 of 56 paired near-face grips against 32 (p 2e-7). Plus a second mechanism the proposal does not name: the joint-7 clip | 1, 3, 4, 5 pass; 2 passes if the reference is the declared home recomputed in set_home_joints; one plan-client G1 allowlist line | yes, alone: a near-face loss of 43 % to 3 % in the real-pick probe would take the eval's 21 % well under the 8 % line | medium: about half of all grasps turn by pi, the arm's posture over every body changes; seed 6 shows the overhead refresh then sees a cup it used to miss and the cup radius loop starts | 4 | implement; its own arm, with pose_radius_keep on |
| carry_trapezoid | the junction kicks are real (81 to 93 m/s^2 at every pair start, 3 m/s^2 under the trapezoid); in the placed-die probe alone it makes the near-face pinch WORSE (3 deg 44 vs 36 of 48, p 0.008) and with the flip it removes the rest of the loss; never run in a real-pick probe, where the flip alone leaves 2 of 64 | 1 to 5 pass (an executor call, every waypoint executed); no allowlist line needed; the single-hop extension is outside the evidence | alone no (a predicted harm too small to see at 60 carries); on top of the flip its margin (2 of 64 in the real-pick probe) is below what the eval can see | low for grasps; wall +0.4 s per bend on bent paths, a faster straight carry | 4 | merge with loss_dynamics' carry_accel_limit (one switch, rest at a bend, dispatcher moves only); no eval arm until a real-pick probe shows it adds to the flip or to edge_pinch |

## 1. Per fix

### grasp_wrist_home

**1. Mechanism.**

Where M9 chooses "the smallest wrist rotation" today (code, d021dad):

- `pose_belief._wrap` 131 to 132 wraps into [-period/2, period/2).
  `fitted_grasp_candidates` 177 to 197: a near-square footprint gets
  `_wrap(yaw, pi/2)`, in [-pi/4, pi/4); a rectangle `_wrap(yaw, pi)` and
  `_wrap(yaw + pi/2, pi)`, in [-pi/2, pi/2). The docstring (182 to 185):
  "Each yaw is the smallest wrist rotation of its class".
- `streams.BoxelStreams.sample_grasp`: the AABB path 840 to 845 (yaw 0, or
  0 and pi/2), the comment 825 to 832 calling yaw 0 "wrist-neutral", the
  orientation `getQuaternionFromEuler([0, pi, yaw])` at 869 (the proposal
  says 853).
- The kin stream does not choose; it certifies what it is given:
  `compute_kin_solution` 1409, IK at `grasp.orientation` from the seeds
  REST_POSES + `_IK_SEED_OFFSETS` (325 to 334, `_ik_seeds` 527 to 533;
  joint 7 seeded at 0.785 +- 0.8), the joint-limit gate (0.1 rad beyond a
  limit rejected, inside it clipped, 408 to 412), the FK gate of 10 mm and
  `IK_ORN_TOL_DEG` = 10 deg (robot_utils.py 38, checked at 449); BF#45's
  contact IK (1531 to 1540) through `robot_utils.solve_ik` seeded at the
  approach configuration, with the same gates (788 to 837). BF#46's span
  sizing (`aabb_half_along`, `pinch_half_extent`) and `believed_margin`
  (221) take absolute values and do not see the sign.

Why it was written that way: #P1 step (4) (2026-09-18) and M9 counted the
rotation from the Euler convention's yaw 0 and offered one member per class
for planning cost (the comment at 825: every extra grasp is another doomed
compute-kin candidate per cell; FastDownward past 30 s per search on seed
5). Nobody checked which joint 7 that orientation needs. On this Panda
top_down(0) is half a turn from the hand at REST_POSES and at
DEFAULT_ARM_POS (both have joint 7 = 0.785; inferred from the probe's IK,
where yaw 0 needs joint 7 of -2.87 to -1.95 rad and yaw pi 0.40 to 1.39 rad
over the same cells): "wrist-neutral" is false in
both worlds, so the defect is pipeline-wide and root-cause, not a find_dice
property.

Measured, the recorded carries (my re-read of the carry.jsonl `wp` rows):
all eight recorded die carries home (loss_dynamics s0_r1, s1_r1 to s1_r3,
s6_r1; hold_physics' three) are the direct linear path of plan_motion's
fast path (streams.py 1043 to 1054, `_linear_trajectory` 1136): a first
pair of 0.325 to 0.396 rad and eight equal pairs after it (the lag added),
joint 7 the largest mover in every pair. The proposal's 211 to 242 deg is
the sum of per-pair dq against the lagging readback. The planned travel is
nine times the first pair: 2.93 to 3.47 rad, **168 to 199 deg**; the sum is
37 to 44 deg high, not "up to about 20". Joint 7 at the pick is then 0.785
minus the travel: **-2.14 to -2.68 rad**, not "about -2.9, its lower limit"
(log 6). In every recorded episode the wrist sat inside its range.

Measured, the probe, re-analysed per trial (reviews/carry_motion_probe/
analyse.py, paired on cell, believed yaw and tilt, exact McNemar). The
table splits by where today's wrist sits. At believed yaws 0 and -22.5 deg
the wrap rule's joint 7 at the lift is -2.87 to -1.53 rad (inside the
range: the class of every recorded episode); at 22.5 and 40 deg it is
exactly -2.90 or +2.90, the clip, and there the close reads half-widths up
to 11.00 mm at delta 0 (10.49 to 10.57 elsewhere) and up to 11.43 mm at
delta 10 (10.92 to 10.99 elsewhere): the hand did not reach the believed
yaw, the pads sit several degrees further off the face than delta (the
10 deg orientation tolerance at work), and 4 of 96 trials found no IK (92
against 96 carries).

Held of 48 per cell, wrist in range (believed yaw 0 and -22.5 deg):

| delta (deg) | wrap + pipe (today) | flip + pipe | wrap + trap | flip + trap | wrap + cont | flip + cont |
|---|---|---|---|---|---|---|
| 0 | 48 | 48 | 48 | 48 | 48 | 48 |
| 3 | 44 | 48 | 36 | 48 | 39 | 48 |
| 10 | 32 | 26 | 24 | 48 | 19 | 42 |
| 20 | 9 | | | 48 | | |
| 45 (edge) | 43 | 40 | 48 | 48 | 48 | 48 |

At the clipped cells (22.5, 40 deg) wrap + pipe holds 38 of 44 at delta 0,
41 of 44 at 3, 22 of 44 at 10; flip + pipe 48, 48 and 17 of 48.

What that says:
- An exactly face-aligned die survives the 168 to 199 deg unwind under
  every executor (48 of 48). The pooled table's "93 % today, 100 % with
  the flip" at delta 0 comes entirely from the clipped cells: it is the
  pinch yaw error of a wrist at its limit, a second mechanism, not the
  spin.
- In this placed-die probe, under today's stream, the flip alone is inside
  the noise in the eval's class: 3 deg 44 vs 48 (0 vs 4 discordant, p
  0.13), 10 deg 32 vs 26 (15 vs 9, p 0.31), edge 43 vs 40 (p 0.55). The
  real-pick re-run below contradicts this.
- With a smooth executor the unwind decides: 10 deg wrap + trap 24, flip +
  trap 48 (p 3e-5 pooled against today); wrap + cont 19, flip + cont 42.
  In this probe the flip's value is conditional on the executor.
- Our bodies: the proposal's "79/88 and 82/90 today, 96/96 with the flip"
  for the 40 mm cube and the 60 mm block are the clipped cells too. In
  range both rules hold 48 of 48 at delta 0; the cube at 3 deg holds 40
  (wrap + pipe), 38 (flip + pipe), 40 (wrap + trap), 48 (flip + trap).

Confounds:
- The probe world. The die is put between open pads at the lift pose in
  free space, closed on, then given its mass; no descent onto a resting
  die, no lift. Its half-widths read 10.47 to 10.54 mm at 0 to 3 deg; the
  eval's bulk reads 10.15 to 10.45 mm and grasp_geometry's real-pick probe
  10.2 to 10.4. The probe's base in range (0 % at 0 deg, 8 % at 3, 33 % at
  10) weighted by the eval's width bins gives about 13 %, against the
  eval's 21 %, hold_physics' real-pick base 17.7 % and grasp_geometry's
  near-face 49 to 54 % lost. The placed-die world is milder and does not
  reproduce the eval's narrow bin (under 10.15 mm, 11 failures of 21), so
  the predicted "under 3 %" carries at least an 8-point model error.
- No proposal's real-pick probe drew the flipped member. hold_physics'
  A_base (grasp yaw uniform in [-90, 90] deg, so joint-7 travel 90 to 200
  deg in both signs): held 31 of 33 at grasp yaw -90 to -45 (travel about
  +100 deg), 14 of 17 at -15 to 15 (+180), 20 of 30 at 45 to 90 (about
  -120): the sign effect of batches 3 and 4, in a second probe.
- My re-run, the decisive number (section 4): grasp_geometry's probe (a
  real pick of the die resting on their table: the descent, the tactile
  close at the floor height, the 10 cm lift, then the pipeline carry with
  today's per-pair stream, the settle and `hold_at_config`), at hand yaw
  180 deg, the flipped member of its yaw-0 grasp (`--hand-yaw-deg=180
  --cells 8 --deltas 0,3,6,10 --k90 0,1 --carry-mode pipeline
  --aperture-sized 1`), against its own pipecarry_main at hand yaw 0 (the
  same arguments otherwise). Held: delta 0 12 of 14 against 16 of 16; 3 deg
  10 of 14 against 16 of 16; 6 deg 7 of 14 against 16 of 16; 10 deg 3 of
  14 against 14 of 16. Paired on cell, face pair and delta: 32 against 55
  of 56, discordant 0 against 23, exact McNemar p 2.4e-7. Every loss at
  either yaw is in the carry (24 at yaw 0, 2 at 180); the close reads
  10.24 to 10.28 mm at 0 to 6 deg, the eval's bulk. So in the world closest
  to the pipeline's pick, the flip ALONE under today's stream removes most
  of the near-face loss (43 % to 3 %); the proposal's "the two only work
  together" holds in its placed-die world only. One probe, 8 cells,
  deterministic: 64 configurations, not 64 draws of the eval.
- Determinism: the probe's physics is deterministic, the 92 to 96 carries
  per cell are 96 configurations, and the tests above treat the
  configuration as the unit. The eval's per-carry outcome is not
  deterministic (loss_dynamics 1.4).
- The episodes ran the flip only together with the trapezoid: seeds 0 and
  1 held (wrist travel 22 and 12 deg, die rotation 0.5 and 9.7 deg, minimum
  pad force 1.10 and 1.38 N; base on those scenes 2 of 4 held). P(2 of 2
  held | 79 %) = 0.62: they show the switches act, they carry no rate.

**2. Rules.**

- Rule 1: the choice is the sampler's: which member of a class it already
  declares symmetric it yields, one grasp per class as today. Nothing is
  reordered after the search and no plan is touched; the planner sees a
  different grasp fact. A preference by joint-7 distance (or by the home
  hand's orientation, its cheap proxy) is a sampler preference, model
  side. Yielding both members would also be model side but costs the
  search what the comment at 825 describes.
- Rule 2: pipeline-wide (every top-down grasp, the M9 and the AABB paths,
  both worlds) and root-cause (the false "wrist-neutral"). The reference
  must be our robot's declared home, and `set_home_joints` runs after the
  streams are built (test_full_pipeline.py 1133): computed "once when the
  streams are built" it would be REST_POSES' hand in the bridge, not
  DEFAULT_ARM_POS' (38.8 deg tilted). Recompute it in `set_home_joints`.
  Two refinements the proposal lacks: for a rectangle (period pi) both
  members can sit near 90 deg from the home hand, where the world-frame
  angle and joint 7 can disagree by the base joint's turn (up to about 40
  deg in W); keep today's member inside a tie band (say within 20 deg of
  the 90 deg split) or choose by joint 7 from the kin stream's own IK.
  Our scenes must not get worse: not measured (the own-body rows are their
  world and robot, and their gain is the clipped cells).
- Rule 3: FK of our robot model in the plan twin at a known configuration;
  no task body read. A new resetJointState on the plan client is a G1 name
  and needs a 'plan client' line in tools/bridge_gates_allowlist.txt (or
  the FK reuses `_pybullet_ik`'s save and restore).
- Rule 4: `slip_fixes.on('grasp_wrist_home')` in pose_belief and streams,
  registered at pose_belief's import. Rule 5: the name is plain.
- Rules 6 and 7: section 4 of the proposal matches the folder (out/
  114.9 MB, episodes 0.82, 1.54 and 1.97 MB, scripts 54 KB against "about
  45 KB"; no __pycache__ left); nothing tracked was edited; the episodes
  ran under the lock (run_ep.sh). Numbers that do not match their data:
  the wrist travel and joint 7 above; "34 cup pick refusals" in seed 6 are
  34 console lines for 17 refusals (stdout: 17 "pose is too uncertain",
  40 plans); streams.py 853 is 869.

**3. Testability and power.** The metric is the loss per die carry. With
about 60 carries per arm and base at 21 %, a two-sided 95 % test against a
within-job base of about 60 carries separates an observed rate of about
8 % or less (z 2.0 at 8 %, 1.9 at 8.5 %); for 80 % power the true rate
must be about 3 % (5 % gives about 75 %). Against base pooled over the
jobs (about 240 carries) the line moves to about 10 %. The proposal's
"below 10 %" is too loose against the within-job base. The two probes
disagree on the fix alone: the placed-die probe predicts a null, the
real-pick re-run a near-face loss of 43 % to 3 % under today's stream. The
eval settles it, so the fix alone gets its own arm: if the real-pick number
transfers, the loss per carry falls well under the 8 % line; with the
trapezoid added the placed-die probe predicts under 3 %. Falsifiers: the proposal's
(a) (joint-7 travel under 90 deg in every die carry) is right but must use
the planned waypoints, not the per-pair dq against the readback (that sum
reads 40 deg high); (b) and (c) as proposed. The switch must log, per
grasp sample, the believed yaw, both members, the chosen one and its angle
to the home hand; per pick, joint 7 of the readback; per carry, the planned
joint-7 travel; per episode, the kin stream's rejections
(`contact_ik_rejects`) and the "pose is too uncertain" refusals, so a null
says whether the switch acted and whether the cup loop ate the carries.

**4. Risk.**

- Our scenes: every top-down grasp whose wrapped yaw lies in the far half
  turns by pi, about half of all grasps; the arm's posture over every body,
  the wrist camera mount's position and the place configurations change
  (the place follows the grasp). In our scenes the hand keeps its world yaw
  from pick to place, so the long unwinds there are the moves to and from
  home; and today a far cell can push joint 7 past -2.8973 for yaw 0, so
  the flip can only widen the reachable set. Unmeasured.
- The cup loop (the question of the dependency). It is real in mechanism
  and not a laptop artefact. Base s6_r1 (console_debug.log), after the move
  over e_cups_ud: the cup was "partly behind the arm in this render" and
  its estimate kept, so the wrist observe's 0.49 mm survived and the pick
  ran. Under the flip, the same move: "4/4 believed bodies observed where
  believed", the cup re-posed by the overhead camera at 5.71 mm, the pick
  refused, 17 times in 40 plans, the cap. The flipped hand stopped
  occluding the cup and unmasked base's radius overwrite
  (`pose_belief.record_detection`, loss_dynamics 1.6). Laptop seed 6 loads
  1747173593.826745, the scene the cluster pins for seeds 1, 2, 3, 4, 8,
  14, 15 and 18 (loss_dynamics 1.7), so the exposure is 8 of the 20 eval
  seeds. The rate is unmeasured: one episode each, and the plans diverged
  before the cup (a_cups_ud set down at (0.684, 0.000) against (0.687,
  -0.204)); base itself loops in 2 of 6 laptop episodes (s1_r3 41
  refusals, s14_base_r1 42). Without pose_radius_keep the flip can raise
  the cap count on the cluster's cup-heavy scene and reduce the number of
  die carries, which biases the loss-per-carry comparison toward the
  scenes that finish.
- Gates: the one plan-client line. Time: a shorter carry (probe 406 to 360
  steps under today's stream).

**5. Effort.** 4 hours, not 3: the function and the AABB path, the
reference in `set_home_joints`, the tie band, the allowlist line, tests in
tests/test_m9_grasp.py (their home turns yaw 0 into pi, a reference at
top_down(0) keeps 0, spans unchanged, the tie band), the log line. Line
numbers checked against d021dad: pose_belief 177 to 197, streams 836 to
845 and 869.

**6. Verdict: implement**, with its own arm and pose_radius_keep on in that
arm. In the real-pick probe it alone, under today's stream, holds 55 of 56
paired near-face grips against 32, and it removes the joint-7 clip that
today certifies grasps up to 10 deg off their yaw; the seed-6 log shows it
can start the cup loop, which pose_radius_keep removes at its root.

### carry_trapezoid

**1. Mechanism.** Measured: under today's stream every pair restarts from
the lagging readback and the hand takes 81 to 93 m/s^2 (probe median peak)
for a step or two at every pair start, 3.1 to 3.3 m/s^2 under the
trapezoid (batch 5); batch 1: joint acceleration 530 to 8 rad/s^2, the
minimum summed pad force 0.05 to 0.90 N (median of 114). loss_dynamics
recorded 60 to 97 m/s^2 at every junction of every episode carry and two
of three releases 0 to 6 steps after a junction (the third, s6_r1, not at
one). The effect on the hold depends on the grasp (in range, 48 per cell):

- alone under today's grasp: 0 deg 48 vs 48; 3 deg 44 vs 36 (8 vs 0
  discordant, p 0.008; pooled 85 vs 64 of 92, p 6e-6); 10 deg 32 vs 24
  (p 0.17). Worse at 3 deg, a real effect in the probe and unexplained
  (proposal section 3, item 3);
- with the flip: 3 deg 48 vs 48 (flip + pipe), 10 deg 26 vs 48 (p 5e-7);
- the edge pinch: 43 vs 48 in range (p 0.06), pooled 84 vs 92 of 92
  (p 0.008).
- hold_physics' coupled 10 N hold at 200 iterations loses 0 of 113 under
  today's per-pair stream: the kicks do not release a pressed die, though
  they still drop one pad to 0.00 N for a step (its seed-6 episode, pairs
  2, 8 and 9).

The probe against the pipeline's carry: every recorded die carry home is
the direct linear path, and the probe's "linear" carry is the same
construction (10 waypoints from the lift readback to home), so for the die
carry the straight joint line is the pipeline's carry, not an
approximation of it. The RRT-Connect path with shortcut smoothing (streams
1056 to 1132) runs only when the direct path is blocked; no recorded die
carry took it. The via path (one bend, unequal pairs) stands in for that
case: flip + trap 94 of 96 on it. Untested: several bends (a rest at each),
the smoother's long single hops. The two episodes ran their carries as one
segment of 336 and 356 steps; they close the gap for the straight carry
at n = 2 and say nothing about RRT carries.

carry_trapezoid against loss_dynamics' carry_accel_limit: the same design.
Both make one call per move with the whole waypoint list, a trapezoid at
the datasheet accelerations under `JOINT_VELOCITY_LIMITS`, then the settle
of the last waypoint (120 steps, 2e-3 rad) and `hold_at_config` after; both
change the dispatcher's loop at test_full_pipeline.py 1877 to 1896, not
only the primitive. An acceleration bound inside the per-pair call of
`move_robot_smooth` (877) cannot do it: a pair knows neither the next
pair's velocity nor when to brake for the last waypoint; the probe's
"cont" (per pair from the last command, no bound) holds 42 against 48 at
10 deg with the flip. The difference is the junction: carry_trapezoid rests
at every direction change (tested on the via path), carry_accel_limit keeps
speed through bends under 30 deg (untested). On the straight carry the two
are the same schedule. Costs: a straight move gets faster (probe 406 to 372
steps under today's grasp, 360 to 334 under the flip; episodes 454 to 336
and 356 steps with the settle, about 0.5 s of simulated time per carry); a
bend costs a rest (via path 311 to 405 steps, +0.4 s). An episode has a few
tens of moves: a net change of about 2 s either way against wall medians of
34.6 s (base) and 23.2 s (arm 4) in BF#53 and the 600 s cap; with
hold_physics' 200 iterations a step costs about 1.9 ms instead of 1.0.

**2. Rules.** Rule 1: the dispatcher's executor call changes, the plan does
not: every planned waypoint is executed in order, the geometric path is the
certified polyline, and merging collinear pairs (cosine > 0.9999) retimes an
identical path. An executor primitive, model side. Rule 2: the Panda
datasheet accelerations (15, 7.5, 10, 12.5, 15, 20, 20 rad/s^2, the source
of F14's velocity limits), every move of every scene. Rule 3: the joint
readback only. Rule 4: `slip_fixes.on(...)` in the dispatcher's move and the
new robot_utils function. Rule 5: fine. Gates: `setJointMotorControl2` and
`stepSimulation` are not in tools/bridge_gates.py `G1_NAMES` (82 to 91): no
allowlist line is needed (the proposal says one is; harmless). The
proposal's extension "move_robot_smooth runs its single hop as a
one-segment trapezoid, so the pick and place descents and the lift get the
same bound" is outside the evidence: the probe has no descent or lift, the
eval lost 0 of 174 dice at the lift, and it changes the pick's arrival
timing before the tactile close and M10's `on_step` poll. Leave single hops
alone.

**3. Testability and power.** Alone: a predicted harm at 3 deg and no gain
for the face pinch; a rise from 21 % to about 30 % would not be visible at
60 carries, so no arm of its own. On top of grasp_wrist_home: in the
real-pick probe the flip alone leaves 2 of 64 near-face grips lost, so the
trapezoid's margin there is at most about 3 points, which 60 carries cannot
show; in the placed-die probe its margin is large (10 deg: 26 to 48 of 48)
but that world is not the pipeline's pick. Its case for an arm rests on a
real-pick run of the pair (section 3). Log per
move: the segment count, the step count against the step count today's
stream would have taken, the peak commanded joint acceleration against the
bound; per held carry the minimum summed pad force (the robot's tactile
sense), so the removal of the kicks is visible in every carry. Falsifiers:
the proposal's (a); (b) with grasp_wrist_home the loss per carry not below
the pose_radius_keep-only arm; (c) our places and stacks.

**4. Risk.** Low for the grasps; wall on transits with many bends; the
moves' timing changes the plan-to-plan timing (non-deterministic already).
Our cube in range at 3 deg: 40 (today) and 40 (trapezoid alone), 48 with
the flip. It helps carry_grip_watch: the junction zero-force steps its
"a pad lost contact" rule would trip on disappear.

**5. Effort.** 4 hours (the schedule, the dispatcher call keeping the F17
per-pair notes, the unit test on a two-segment polyline). Lines checked:
move_robot_smooth 877, hold_at_config 1001, the dispatcher loop 1877 to
1896.

**6. Verdict: merge with carry_accel_limit**: one switch, the tested
rest-at-a-bend rule, the dispatcher's moves only (no single hops); the
30-deg blend is a later refinement if the bent transits' wall shows it.
Never evaluate it alone (the placed-die probe says it harms the near-face
pinch), and give it a cluster arm (with grasp_wrist_home, or with
edge_pinch if that survives its review) only after a real-pick probe shows
it adds to them.

## 2. Cross-proposal conflicts and combinations

- One mechanism, one switch: carry_trapezoid = carry_accel_limit.
- Two mechanisms, not one: grasp_wrist_home (the wrist unwind, and the
  joint-7 clip) and carry_trapezoid (the junction kicks). The proposal's
  "they only work together" is an interaction seen in its placed-die probe;
  in the real-pick re-run the flip alone under today's stream holds 55 of
  56 paired near-face grips against 32. They live in two modules, the
  trapezoid also serves edge_pinch and carry_grip_watch, the flip also
  fixes the clip: two switches. The flip gets its own arm; the trapezoid
  no arm alone (a predicted harm), and an arm with the flip only if a
  real-pick run shows it adds.
- grasp_wrist_home needs pose_radius_keep in its arm (seed 6, section 1).
- grasp_wrist_home and edge_pinch both edit `fitted_grasp_candidates`;
  they compose (edge_pinch rotates by pi/4 first, the flip then chooses
  between g and g + pi), and the order must be fixed in the code. For the
  edge pinch the unwind does not matter (wrap + trap or cont 48 of 48 in
  range), so with edge_pinch the flip adds the clip fix and nothing for the
  hold.
- The hold. hold_physics' force_hold with finger_gear and solver_iters
  loses 0 of 113 dice under today's grasp and stream across joint-7 travels
  of 90 to 200 deg in both signs (G_gear_iters200_force10, by grasp yaw: 33,
  20, 17, 13 and 30 of the same). If it lands, the flip buys no hold there;
  what is left is the clip (a pinch up to 10 deg off at believed yaws above
  about 15 deg, no IK at some), a carry shorter by about 46 steps, and our
  scenes' reach. The two are rivals for the same loss: the flip changes one
  sampler choice and costs nothing per step; the hold needs three switches,
  a new constraint and a doubled step time (1.0 to 1.9 ms). Both should get
  an arm; if both work, the flip is the cheaper. The trapezoid then buys the removal of the zero-force
  junction steps and a faster straight carry, not a hold; its time cost is
  not the issue (net about 2 s per episode either way), so it is worth
  keeping only for carry_grip_watch or edge_pinch.
- "Time in the hand" against "the wrist spin". hold_physics' half speed
  holds 73 of 113 against 93 (27 vs 7 discordant, p 0.0008); carry_motion's
  half velocity holds 100 of 114 against 96 (11 vs 7, p 0.48), the other
  way. The two probe worlds disagree on speed; both predict that less wrist
  rotation and a shorter straight carry help (the flip with the
  trapezoid), and neither explains why the trapezoid alone hurts the
  near-face pinch.
- Interference: force_hold makes the fingers follow the body (widening up
  to 0.7 mm without a loss), so carry_grip_watch's 0.05 mm threshold must be
  re-measured under it; carry_hold_check re-picks a lost die, which turns
  one lost carry into two carries: an arm that measures the loss per carry
  must count carries before the re-pick or leave it off; edge_pinch reads
  12.3 to 12.6 mm, and force_hold's target 4 mm inside it is unaffected.
- Order of the arms, each testing one mechanism, every arm with
  pose_radius_keep on except base: (0) pose_radius_keep alone (the belief;
  it changes how many episodes reach a carry, not the carry); (1) the hold
  (force_hold with finger_gear and solver_iters); (2) grasp_wrist_home
  alone; (3) edge_pinch if it survives its review (carry_trapezoid added to
  (2) or (3) only after the real-pick check of section 3). carry_hold_check
  and carry_grip_watch come after (they change the outcome, not the rate
  per carry). The combination (1) + (2) only if each alone leaves a loss
  per carry above about 5 %.

## 3. Missed, and what to check first

Missed by the proposal:
1. The joint-7 clip. Today's M9 rule certifies a grasp at a believed yaw
   above about 15 deg (cell-dependent) with joint 7 clipped at its limit
   and the hand up to `IK_ORN_TOL_DEG` = 10 deg off the yaw, or finds no
   IK. That is a pipeline defect independent of the carry, the whole of the
   flip's gain at delta 0 in the pooled table, and the whole of the
   own-body gain. The eval's share of it is unknown: the recorded episodes
   sat in range.
2. The probe world is milder than a pick off the table (base about 13 % in
   the eval's width mix against 21 %), and the proposal never ran its fix
   in a real-pick probe, although grasp_geometry's takes the flip as one
   argument (`--hand-yaw-deg=180`). There the flip alone does what the
   proposal says it cannot.
3. The number corrections of section 1 (travel 168 to 199 deg, joint 7
   -2.14 to -2.68 rad at the pick, 17 refusals).
4. The home reference at stream construction is REST_POSES in the bridge.
5. The seed-6 log already shows the occlusion change; the proposal guessed
   it.
6. The rectangle's 90-deg ambiguity; the single-hop extension.

What I would check first (one hour):
1. carry_motion's `trap_schedule` ported into grasp_geometry's probe as a
   third carry mode (about 15 lines in a probe copy, a 10 minute run), at
   hand yaws 0 and 180, deltas 0, 1, 2, 3, 6, 10, 45, and the cube40
   payload: the trapezoid alone and with the flip in a real pick, and our
   cube. This decides whether the trapezoid harms alone (the placed-die
   probe: 3 deg 44 to 36 of 48), whether it adds anything to the flip's 62
   of 64, and whether it is what edge_pinch needs (grasp_geometry: the
   pipeline carry costs its edge pinch 14 points against a single move).
   Also hand yaw 180 at deltas 1 and 2, the eval's narrow bin (today 7 and
   8 of 14).
2. From BF#53's cluster console logs (the orchestrator's): the die pick's
   grasp yaw and the joint-7 readback for all 174 picks, to count the
   clipped picks and their loss rate against the in-range ones.

## 4. Data generated and deleted

Under reviews/carry_motion_probe/ (written by this review, deleted by path
when the numbers were in this file):

- analyse.py 5,392 B and analyse_out.txt 22,446 B: the per-trial and
  paired re-analysis of probes/carry_motion/out/b5_* and b6_* (Wilson
  intervals, held and half-width by believed yaw, exact McNemar on cell,
  yaw and tilt, the wrist-in-range subset);
- episodes_q7.py 1,863 B: the waypoint rows of the eight recorded die
  carries (planned travel, joint 7 at the pick);
- hp_by_yaw.py 1,094 B and speed_pairs.py 1,772 B: hold_physics' A_base,
  A_speed0.5 and G_gear_iters200_force10 by grasp yaw, and the paired speed
  comparisons in both probes;
- the one re-run of an existing probe: gg_flip.sh 820 B (the command of
  section 1), gg_hy180.json 262,698 B and gg_hy180.log 9,302 B (64 trials,
  a few minutes, physics only, no lock), gg_pair.py 2,020 B (the pairing
  against grasp_geometry's pipecarry_main).

9 files, 307,407 B, all deleted. Nothing else generated; no file outside
reviews/ written. The re-run is reproducible with gg_flip.sh's command as
quoted in section 1 (cwd /root/tampura-work/tampura_environments,
PYTHONPATH=$S:$S/tools:/root/tampura-work/tampura:.).
