# BF#59 implementation: carry_trapezoid

Started 2026-10-31 by the implementing agent (round 2). Worktree
`C:\Users\HaniAlassiriAlhabbou\git\sb-slip-carry_trapezoid`, branch
`slip/carry_trapezoid`, base ae62b33 (tampura-bridge; code identical to
05dcaf3). Filled as the work goes; sections marked PENDING are not done yet.

## 1. Branch and commits

- `b1e2455` BF#59 carry_trapezoid: one acceleration-bounded schedule per
  move made while holding, behind the switch, with tests
  (test_full_pipeline.py +227 -26, tests/test_slip_carry_trapezoid.py new;
  two files, only this fix's hunks; nothing pushed).

## 2. Files and functions changed (line numbers on the branch)

- `test_full_pipeline.py`
  - 119 to 122: module-level `import logging`, `math`, `robot_utils`,
    `slip_fixes` (main's own local imports of robot_utils and slip_fixes
    stay as they were).
  - 124 to 152: the narration block (the junction kicks, 60 to 97 m/s^2
    today; the rest-at-a-bend rule and its via-path number; rule 1 and
    rule 2; no single-hop extension, no keep-speed-under-30-deg rule; never
    alone, 36 against 44 of 48 at 3 deg; 336 and 356 against about 454
    steps) and `slip_fixes.register('carry_trapezoid', ...)` at import.
  - 154 to 167: `_carry_log` (logger `test_full_pipeline`),
    `CARRY_TRAP_ACCEL_LIMITS` (Panda datasheet 15, 7.5, 10, 12.5, 15, 20,
    20 rad/s^2), `CARRY_TRAP_COLLINEAR_COS` 0.9999, `_TODAY_PAIR_STEPS` 30
    (log only).
  - 170 to 223 `carry_trapezoid_schedule(points, vmax, amax, dt)`: the
    schedule, ported line for line from carry_motion's tested
    `trap_schedule` (probes/carry_motion/episode_fix.py 73 to 110, the
    code the two episodes ran; the same as probe_carry_motion.py 228 to
    275 without the velocity output): collinear merge, zero-length pairs
    dropped, one trapezoid (or triangle) per segment in the path
    parameter, at rest at both ends of every segment.
  - 226 to 237 `_today_stream_steps(points)`: today's per-pair step count
    for the same polyline (log only).
  - 240 to 299 `_stream_carry_trapezoid(robot_id, waypoints, gui,
    on_step)`: the readback, the schedule, the F17 per-pair notes (from
    the planned waypoints, tagged `carry_trapezoid`), one
    `move_robot_smooth(q, steps=1, settle=False, velocity_bounded=False)`
    per scheduled step, then `move_robot_smooth(last waypoint, steps=1,
    settle=True)` (the settle, as episode_fix did), then the log line.
  - 302 to 338 `stream_move_waypoints(robot_id, waypoints, gui, holding,
    on_step)`: the switch point. On and holding: the trapezoid. Otherwise
    today's per-pair loop, moved here verbatim from main (its comments
    included) so a test can count its calls.
  - main's move action, 2104 to 2110 (was 1884 to 1909 at 05dcaf3): the
    loop replaced by `stream_move_waypoints(robot_id, traj.waypoints, gui,
    holding=held_body_id is not None)`. The re-solve before it and the
    home hold after it are untouched.
- `tests/test_slip_carry_trapezoid.py` (new, 14 tests).
- `robot_utils.py` untouched (`move_robot_smooth` is the primitive).

## 3. What the switch does, on and off

Off (or on with an empty hand): `stream_move_waypoints` runs today's loop,
the same calls in the same order (`move_robot_smooth(wp, gui, steps=30,
settle=last)` per pair, the F17 notes against the readback before each
pair). On, for a move made while `held_body_id is not None` (any body: the
die, a cup, our cubes): the joint readback, then `waypoints[1:]` as one
polyline; collinear pairs merge (the direct linear carry of 10 waypoints
is one segment), every other direction change becomes a rest; each
scheduled step is one call of `move_robot_smooth` with one step, so the
motor write (POSITION_CONTROL, 240 N m), `stepSimulation`,
`telemetry.tick()`, `on_step` and the GUI pacing are the primitive's own;
the settle at the last waypoint is `move_robot_smooth(..., settle=True)`
as today (120 steps, 2e-3 rad), then the home hold as today. Every planned
waypoint is a vertex of the commanded path (the merge only drops interior
points of a straight line). No pybullet write is added (the motor write
and the step are inside move_robot_smooth, and neither is a G1 name).

## 4. Logging

One line per move made while holding, after the move, through the logger
`test_full_pipeline` at INFO (the run log run_*.log and console_debug.log;
the curated console takes ERROR and above only):

    carry_trapezoid: 10 waypoints in (readback + 9), 1 segment(s) after
    merging, 0 rest(s) inserted, N schedule steps + M settle steps streamed
    (today's per-pair stream: at least K steps before its settle), peak
    commanded joint acceleration R of the datasheet bound

K is the lower bound today's stream would command for the same planned
waypoints (30-step floor and F14 stretch per pair, without the lag), R is
the largest commanded second difference over the bound (the carry_motion
falsifier (a) asks for at most 1.2; the schedule gives at most 1.0 by
construction, the test checks it). The telemetry's F17 waypoint notes are
kept (one per planned pair, before the stream, tagged `carry_trapezoid`).
The eval's counted lines are untouched.

## 5. Tests

`tests/test_slip_carry_trapezoid.py`, 14 tests, the registry's KNOWN and
ENABLED restored after each (fixture `switch`, the style of
tests/test_slip_fixes.py), move_robot_smooth, the readback and the robot
model stubbed by monkeypatch (fixture `stubbed`):

- registered at import, off by default, configurable;
- a straight three-waypoint path is one segment with no rest (the middle
  waypoint passed at cruise speed), ending exactly at the last waypoint;
  the 10 waypoints of a linear trajectory are one segment;
- a bent path is two segments, the bend commanded exactly once, at rest
  there (the neighbouring commands within half a step of the bound's
  acceleration);
- the acceleration and velocity bounds hold along the schedule, at rest
  before and after (five paths: one hop, straight, one bend, a short
  triangle hop, two bends): every second difference at most the datasheet
  bound times dt^2, every step at most the velocity limit times dt;
- the bound is reached on a long wrist carry (not slower than needed);
- off (holding or not) and on with an empty hand: 9 calls for 10
  waypoints, steps=30, velocity bounded, settle only at the last, the
  targets the waypoints;
- on and holding: one call per scheduled step (steps=1, no settle,
  velocity_bounded False), then one settle call at the last waypoint,
  on_step on every step, one `carry_trapezoid:` log line with the counts;
- main's move action calls `stream_move_waypoints(robot_id,
  traj.waypoints, gui, holding=held_body_id is not None)` and calls
  move_robot_smooth nowhere else.

Result: 14 passed (the new file alone, 27 s); the full suites in the
check (section 6).

## 6. Checks

Both `tools/slip_check.sh` runs (the main checkout's script) green, outputs
under the worktree's `archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/
checks/`:

| run | dir | unit tests | bridge tests | static gates | seed-0 episode | slip_fixes |
|---|---|---|---|---|---|---|
| fix on | 2026-10-31_19-26-36_s0_carry_trapezoid | 67 passed | 89 passed, 3 skipped | PASS (every row; run in full as well, no FAIL) | success, rc 0, 51 s | "carry_trapezoid" |
| fix off | 2026-10-31_19-39-46_s0 | 67 passed | 89 passed, 3 skipped | PASS | success, rc 0 | "" |

The two seed-0 episodes (tools/episode_metrics.py), not a clean
comparison: the plans differ (base sensed once more), the laptop ran the
probes beside them:

| metric | fix on | fix off |
|---|---|---|
| wall_s | 22.3 | 28.1 |
| planning_s (plan calls) | 9.6 (3) | 10.7 (3) |
| exec_s | 9.7 | 14.6 |
| move_s | 4.3 | 8.0 |
| dispatched steps | 10 | 12 |
| die carries | 1 | 1 |

With the fix on two moves were made while holding (the cup, then the
die home), each one segment, no rest: 75 + 21 and 340 + 18 simulation
steps (schedule + settle); today's stream would command at least 270
steps plus its settle for each (the 30-step floor of 9 pairs; carry_motion
measured about 454 for a die carry home with the lag and the 76-step
settle). Peak commanded acceleration 1.00 of the bound in both.

Seed 1 with the fix on (the brief's lost-die seed; laptop scene
1747173590, `--allow-g19-mismatch 1`, under the lock; checks/
seed1_carry_trapezoid): our goal held (the die at home, their reward 1.0;
the driver's outcome gate_failed is the expected G19 laptop mismatch,
rc 1), one die carry ("firm grip on dice" once, no loss line). But 865 s
wall, 118 plan calls, 697.6 s planning, 55 "pose is too uncertain"
lines: the cup radius loop (pose_radius_keep's mechanism), not this fix.
Five moves made while holding, all one segment, 0 rests, 66 to 319
schedule steps. One episode, a coin flip, and the fix alone is the
configuration the reviews say never to run.

## 7. The real-pick check (review requirement)

Probe: `reviews/carry_trapezoid_probe/probe_trap_realpick.py`, a copy of
grasp_geometry's real-pick probe (the die resting on their table, the
descent, the tactile close at the floor height, the 10 cm lift, the
re-verify, the carry to DEFAULT_ARM_POS along the 10 linear waypoints,
`hold_at_config(52)`; HELD = both pads, summed normal force >= 0.5 N) with
one added carry mode, `trapezoid`, which streams the same waypoints through
the branch's own `test_full_pipeline.stream_move_waypoints` (switch on,
holding), imported from the worktree. Command (`run.sh` beside it, both
cells in parallel, physics only, no lock, 106 and 161 s):

    cd /root/tampura-work/tampura_environments
    PYTHONPATH=<worktree>:<worktree>/tools:<pddlstream_lib>:/root/tampura-work/tampura:. \
      /root/armO-venvA/bin/python probe_trap_realpick.py --out hy180_<mode>.json \
      --hand-yaw-deg=180 --cells 8 --deltas 0,3,6,10 --k90 0,1 --aperture-sized 1 \
      --carry-mode pipeline|trapezoid

The carry_motion review's flip cell (hand yaw 180, the pad-swapped member
of the yaw-0 grasp), the same 64 trial configurations in both cells
(deterministic physics, so a configuration is the unit, not a draw).
`analyse.py` (Wilson 95 % intervals, exact McNemar paired on cell, face
pair and delta):

| delta (deg) | today's per-pair carry | carry_trapezoid | discordant (pipe only / trap only) |
|---|---|---|---|
| 0 | 16/16 [81, 100 %] | 16/16 [81, 100 %] | 0 / 0 |
| 3 | 16/16 [81, 100 %] | 16/16 [81, 100 %] | 0 / 0 |
| 6 | 16/16 [81, 100 %] | 16/16 [81, 100 %] | 0 / 0 |
| 10 | 14/16 [64, 97 %] | 14/16 [64, 97 %] | 0 / 0 |
| all | 62/64 [89, 99 %] | 62/64 [89, 99 %] | 0 / 0, p 1 |

- Today's cell reproduces the review's re-run exactly (16, 16, 16, 14 of
  16 at hand yaw 180).
- The trapezoid loses the same two configurations (10 deg, both in the
  carry) and no other: on top of the flip it adds nothing to the held
  count in this probe (the review's bound "at most about 3 points" is
  here 0 of 64).
- What it does change: the minimum summed pad force over the lift and
  carry, median 0.04 N today against 2.02 N (the zero-force junction
  steps are gone), and the steps from the lift to home, median 406
  [365, 437] today against 382 [339, 417]. Every move logged one
  segment, 0 rests, 262 to 340 schedule steps plus 16 or 17 settle steps,
  peak commanded acceleration 1.00 of the bound (64 of 64 lines).
An extra pair beyond the two named cells (the review's section 3 item 1,
"whether the trapezoid harms alone", about a minute each): the same
arguments at hand yaw 0, today's grasp member (`bash run.sh 0`; 56 of 64
configurations gripped in both, the other 8 found no IK or no grip, as in
grasp_geometry's pipecarry_main):

| delta (deg) | today's per-pair carry | carry_trapezoid | discordant (pipe only / trap only) |
|---|---|---|---|
| 0 | 12/14 [60, 96 %] | 11/14 [52, 92 %] | 1 / 0 |
| 3 | 10/14 [45, 88 %] | 1/14 [1, 31 %] | 9 / 0, p 0.004 |
| 6 | 7/14 [27, 73 %] | 4/14 [12, 55 %] | 4 / 1 |
| 10 | 3/14 [8, 48 %] | 5/14 [16, 61 %] | 1 / 3 |
| all | 32/56 [44, 69 %] | 21/56 [26, 51 %] | 15 / 4, p 0.019 |

- Today's cell reproduces the review's pipecarry_main (12, 10, 7, 3 of 14).
- Alone, under today's wrist unwind, the trapezoid HARMS the near-face
  pinch in the real pick too: 21 against 32 of 56 (p 0.019), 1 against 10
  of 14 at 3 deg (p 0.004), the same direction as the placed-die probe
  (36 against 44 of 48). Every loss in the carry; the minimum pad force
  median is 0.00 N in both (the die turns out regardless of the kicks).
  Steps from the lift to home 439 against 418.

So: the real-pick check does not show that the trapezoid adds to the flip
(62 against 62 of 64, the same configurations lost), and it confirms the
harm alone. By the review's rule (an arm with the flip only if a real-pick
run shows it adds) this is evidence against a cluster arm for it, beyond
what the pad-force dip removal and the shorter carry buy; and the switch
must never run without grasp_wrist_home. The orchestrator decides.

## 8. Deviations from the proposal and the review

From the proposal (2.2), as the reviews and the candidate list required:
no `robot_utils.move_robot_trajectory` (robot_utils untouched, the
primitive streams every step), no single-hop extension, no allowlist line
(none needed), the keep-speed-under-30-deg rule of carry_accel_limit not
taken. Beyond that:

1. The per-step calls pass `velocity_bounded=False`. The candidate list
   says each segment streams through move_robot_smooth "with its velocity
   limits"; the F14 stretch inside move_robot_smooth measures the hop from
   the readback, which lags the command by about v / 24, so a one-step
   call at cruise would be stretched over about ten steps and the per-call
   restart (the kick) would be back. The velocity limit is enforced on the
   command by the schedule itself (cruise ds/dt from
   JOINT_VELOCITY_LIMITS; the test checks every commanded step against
   the limit times dt). The final settle call keeps the default
   (velocity-bounded), as episode_fix did.
2. Today's per-pair loop moved verbatim (its comments, the F17 notes, the
   calls) from main into `stream_move_waypoints`, so the off path can be
   tested by counting calls. Behaviour with the switch off is the same
   code in the same order; main's move action is one call.
3. "While holding a body" is `held_body_id is not None`, independent of
   `held_cargo_resolve` (the re-solve flag): the bridge runs both, our own
   scenes may not re-solve, and the schedule then streams the planned
   trajectory as it stands.
4. The acceleration limits are a constant of test_full_pipeline
   (`CARRY_TRAP_ACCEL_LIMITS`), not `robot_utils.JOINT_ACCEL_LIMITS` (the
   proposal), because the candidate list keeps robot_utils untouched.
5. The log line: the orchestrator's four items, plus the review's two
   cheap ones (today's step count for the same waypoints, as a lower
   bound; the peak commanded acceleration against the bound). Not logged:
   the review's per-carry minimum summed pad force (a tactile read per
   step in the dispatcher; left to carry_hold_check's per-carry line or
   the eval's recorder, see section 9).
6. The F17 waypoint notes are made once, before the stream, from the
   planned waypoints (tagged `carry_trapezoid`); today's notes measure
   each pair from the readback just before it, which the one stream has
   no moment for.
7. The schedule starts at rest from the readback, as the tested code did
   (episode_fix), not from the last commanded target (see section 9).

## 9. Open questions for the implementation reviewer

1. The handover from the lift. The lift (`_apply_post_action_lift`,
   move_robot_smooth without a settle) ends with the arm lagging its last
   command; the schedule starts at rest from the readback, so the first
   steps of the carry still command a velocity drop. loss_dynamics' review
   (item 3) measured 51.3 and 51.8 m/s^2 at the first two steps of both
   trapezoid episodes and suggested starting from the last commanded
   target; the dispatcher does not know it (PyBullet does not report a
   motor's target), and the plan_motion re-solve between the lift and the
   carry does not step the world. Kept as tested; the real-pick probe (the
   same lift, then the carry) shows no loss from it (62 of 64 in both
   cells, zero discordant). A settle at the end of the lift would remove
   it but changes every pick.
2. The real-pick check shows no gain on top of the flip (62 against 62 of
   64, the same configurations lost). Does the trapezoid keep its place in
   job C, or only as the pad-force and step-count change it is?
3. "Never alone" is now measured in a real pick (section 7: 21 against 32
   of 56 at hand yaw 0). Should the switch refuse to run without
   grasp_wrist_home (as force_hold refuses without solver_iters)? Not done
   here: grasp_wrist_home lives on another branch, and the arm spec
   already pairs them.
4. Moves with cargo on our own scenes (place and stack transits, often
   RRT paths with several bends): the rest at every bend costs about 70
   steps per bend (carry_motion's via path); not measured here.
5. The per-carry minimum summed pad force (review section 3): where should
   it live (the dispatcher, through an on_step contact read, or
   carry_hold_check's line)?

## 10. Data generated and deleted

Kept (untracked; DATA_LEDGER.md not edited by this agent, which edits
only its worktree and this report; the orchestrator ledgers):

- Worktree `.../sb-slip-carry_trapezoid/archive/tampura_bridge_plan_2026-10-25/
  bf/BF59_slip/checks/`: `2026-10-31_19-26-36_s0_carry_trapezoid` 340 KB,
  `2026-10-31_19-39-46_s0` 368 KB, `seed1_carry_trapezoid` 5.4 MB.
  Garbage once the implementation review has read them (the numbers are
  in section 6).
- Main checkout `reviews/carry_trapezoid_probe/`: `probe_trap_realpick.py`
  17,383 B, `run.sh` 1,128 B, `analyse.py` 2,459 B (scripts, keep);
  `hy180_pipeline.log` 9,328 B, `hy180_trapezoid.log` 26,587 B,
  `hy0_pipeline.log` 9,298 B, `hy0_trapezoid.log` 24,415 B (the per-trial
  lines, the only record left of the trials; review, about 70 KB).

Deleted by path once the numbers were in section 7: `hy180_pipeline.json`
262,707 B, `hy180_trapezoid.json` 263,809 B, `hy0_pipeline.json` and
`hy0_trapezoid.json` (about 0.26 MB each). No __pycache__ (runs with
PYTHONDONTWRITEBYTECODE=1 and -B).
