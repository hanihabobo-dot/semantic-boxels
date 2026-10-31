# BF#59 implementation report: force_hold

Implementer: the round-1 agent for `force_hold` (finger_gear folded in),
2026-10-31 17:55 to 19:25. Worktree
`C:\Users\HaniAlassiriAlhabbou\git\sb-slip-force_hold`, branch
`slip/force_hold` from tampura-bridge 05dcaf3. Nothing pushed, nothing
committed outside the branch, the main checkout untouched except this
report and its folder `reviews/impl_force_hold/`.

## Status

- [x] code, switch, hold law, gear in both worlds, allowlist (gates PASS)
- [x] tests: 9 new, all pass; suite 62 passed; bridge tests 89 passed
- [x] slip_check off: green (seed 0 success)
- [x] slip_check on (`force_hold` with the check-only escape, so 50
      iterations): NOT green, as predicted (die lost on the way home);
      one bridge test failed there and passed alone and in the off run
- [x] laptop episodes with 200 iterations (a stand-in wrapper, below):
      seed 1 held, seed 6 held, seed 0 one failure (cup release jam) and
      one success
- [x] orchestrator's note (19:05): the configure call before d9_setup and
      the `import slip_fixes` copied verbatim from slip/solver_iters (d3a0411)
- [x] jam probe (19:35 to 20:25): the release jam is not caused by the
      switch (section "Jam probe"); no code change, no new episodes

## Branch and commits

- b2cacd6 `BF#59 force_hold: the force-limited hold after the close and the finger gear in d9_setup and boxel_env, behind the switch`
- b7d08f5 `BF#59 force_hold: unit tests (switch, refusal, hold law, gear on both worlds, a held centred box)`
- d3a0411 `BF#59 force_hold: the configure call before d9_setup and the import as on slip/solver_iters, for a clean merge`

## Files and functions changed (line numbers at d3a0411)

- `robot_utils.py` 1135 to 1201: the block after GRIP_SQUEEZE: its own
  `import os as _os` and `import slip_fixes` (kept in the block so other
  branches' top-of-file imports do not conflict), `slip_fixes.register(
  'force_hold', ...)` at import, the constants FORCE_HOLD_REACH 0.004,
  FORCE_HOLD_BUDGET_N 10.0, FINGER_GEAR_RATIO -1, FINGER_GEAR_ERP 0.1,
  FINGER_GEAR_MAX_FORCE 50 (narration comments citing the proposal's
  numbers), FORCE_HOLD_NO_ITERS_ENV, and `force_hold_requires_solver_iters
  (where)` 1183.
- `robot_utils.close_gripper_until_contact` 1204: one block 1260 to 1289
  after the 60-step position hold, before `return width`.
- `tampura_bridge/policy.py`: `import slip_fixes` 37 (identical to
  solver_iters'); `d9_setup` block 81 to 101 after the finger loop;
  `make_execute_fn` 212 to 215, `slip_fixes.configure(cfg.switches.get(
  'slip_fixes', ''))` right before `d9_setup(world, model)`, text and
  comment copied verbatim from slip/solver_iters (policy.py 201 to 204
  there) so the merge sees two identical hunks.
- `boxel_env.py` `_setup_scene` 936 to 961: the gear block after the
  finger-opening loop, before `self.objects["robot"]` (function-level
  `import slip_fixes`, `import logging`).
- `tools/bridge_gates_allowlist.txt`: four G1 lines, two after
  `_setup_scene`'s plan-twin finger line (class "unreachable on the
  bridge path"), two after d9_setup's finger-opening line (class "D9
  set-up"). solver_iters appends its lines at the end of the file, so no
  overlap.
- `tests/test_slip_force_hold.py` (new).

## What the switch does

Off: nothing differs; the same code path, numbers and log lines (the only
new statement executed is the configure call, which main() makes anyway
with the same spec).

On:
1. The hold (`close_gripper_until_contact`): the close and its 60-step
   position hold (0.5 mm inside the measured width, 60 N) run as today;
   then both finger motors get target `max(0, width - 4 mm)` at 10 N, the
   behaviour of probes/hold_physics/ep_probe.py (its wrapper set exactly
   this after the close returned). The hold therefore starts where the
   probe and the three proposal episodes started it, not at the touch.
   The motor target persists through the lift and the carry. The returned
   width is the touch's, as today.
2. The gear: one JOINT_GEAR constraint between the two finger joints
   (jointAxis [1,0,0], frames at 0, then gearRatio -1, erp 0.1, maxForce
   50) on the bridge's executing client in d9_setup (phase 'setup', before
   any step; G14 lets it pass there) and on our physics client in
   `_setup_scene` at robot load; `reset()` runs resetSimulation (which
   drops constraints) then `_setup_scene` again, so a reset world gets it
   back (tested). The adopt path never runs `_setup_scene`, so the bridge
   gets exactly one gear (the logs show constraint 1 on client 0). The
   plan client gets none.
3. The refusal: `force_hold_requires_solver_iters` is called in d9_setup,
   in `_setup_scene` and at the hold; without `slip_fixes.on(
   'solver_iters')` it raises RuntimeError "slip fix 'force_hold' needs
   'solver_iters' on as well (<where>): run --slip-fixes
   solver_iters,force_hold ...". The check-only escape
   SLIP_FORCE_HOLD_NO_ITERS_CHECK=1 lets it pass and logs a WARNING line
   (logger and stdout) at every use. On the bridge the first refusal point
   is d9_setup, inside execute_fn's try, so the episode records the error.

Unchanged under the switch, confirmed in the code:
- grip verification `execution.py` 1235 to 1264: link identity of
  `getContactPoints(robot, obj)` on the pads, no force or distance
  threshold (logged pad force rises, 11 to 30 N on cups in the episodes);
- width plausibility 1276 to 1290: reads `measured_half`, the width the
  close returns at the touch (robot_utils 1250, `width = mean(finger_pos)`
  when both pads touch), before any hold;
- post-lift re-verify 1331 to 1344: link identity only;
- `_verify_holding` `test_full_pipeline.py` 298 to 311 (both pads, summed
  force >= 0.5 N at 308): the 10 N per finger hold sits far above it;
- place release: `open_gripper` robot_utils 1059 to 1065 commands both
  fingers to 0.04 m at 200 N, which replaces the 10 N target outright; the
  release verify `execution.py` 646 to 648 (fingers >= 0.038) and 655 to
  694 (no robot contact) are unchanged. Nothing else commands the fingers
  (grep: only open_gripper, close_gripper, close_gripper_until_contact).

## Logging

Through the run's logger (root file handler at DEBUG, RunLogger), prefix
`force_hold:`:
- per hold (robot_utils): `force_hold: measured half-width 10.04 mm,
  target 6.04 mm, budget 10 N per finger, pad forces 6.71/6.68 N at the end
  of the position hold, fingers 9.59/9.67 mm`. The pad forces are read
  where the force hold takes over (the end of the 60-step position hold);
  the primitive returns there, so a later "end of the hold" (at the open)
  would need a line in open_gripper, which the brief keeps unchanged.
- per world (policy, boxel_env): `force_hold: finger gear constraint 1 on
  client 0 (joints 12, 13, gearRatio -1, erp 0.1, maxForce 50 N)`.
- the escape's WARNING line when used.

## Tests (`tests/test_slip_force_hold.py`, 9 tests, 19 s)

The registry fixture restores KNOWN and ENABLED after each test; worlds
are client-0 DIRECT clients with pybullet_data's Panda (the close drives
the default client); 200 iterations on the test world stand in for
solver_iters; ENABLED is set by hand (registering 'solver_iters' in a
test would clash with that branch's line after the merge).
1. registered and off by default;
2. the refusal without solver_iters, the pass with it, the escape;
3. d9_setup refuses without solver_iters and creates no constraint;
4. off: the 60-step hold and the last finger commands are 0.5 mm inside at
   60 N; on: the same 60 steps, then the last two commands are 4 mm inside
   at 10 N (parametrised);
5. d9_setup's gear: finger 1 driven alone to 10 and 30 mm, |q1 - q2| <
   0.05 mm;
6. without the switch no gear and finger 2 stays (> 5 mm apart);
7. our world: BoxelTestEnv (random_pairs seed 1) has one constraint on the
   physics client and none on the plan client, coupled within 0.05 mm,
   and again after `reset()`;
8. a 17.8 mm, 5.2 g box 2 mm off the hand's centre on a pedestal: closed,
   pedestal removed, 200 steps: both pads in contact, summed force >=
   0.5 N, |q1 - q2| < 0.05 mm, the box within 0.5 mm of the hand's axis.

Not tested at unit level: the probe's die, 0.5 kg cube and cup rows
through the changed function (the proposal 2.3 asked for it; the episodes
below are the only run of the changed function on their bodies).

## Checks

- off (`slip_check.sh ... 0`), checks/2026-10-31_18-44-30_s0 in the
  worktree: tests 62 passed, bridge tests 89 passed 3 skipped, gates PASS
  (G1 80, G2 46 hits reviewed), seed 0 success, slip_fixes "", 1 die
  carry; wall 17.5 s, 12 steps, planning 6.7 s.
- on (`SLIP_FORCE_HOLD_NO_ITERS_CHECK=1 slip_check.sh ... 0 force_hold`),
  checks/2026-10-31_18-30-12_s0_force_hold: tests 62 passed; bridge tests
  1 failed (`test_b3_parameterisation.py::test_adopted_goal_at_home_episode`),
  88 passed; gates PASS; seed 0 FAILURE (physics_mismatch: the die picked,
  "links none" at the goal check), slip_fixes "force_hold". The die loss
  is the predicted 50-iteration expulsion (10 N at 50 iterations: 108 of
  113 lost); this run cannot be green by design. The d_cups_ud release
  there also failed its verify (link 12 at d -0.10 mm, 0.58 N after the
  open, three retries), see the cup finding. The bridge test passed when
  rerun alone under the lock (119.8 s) and in the off run; it does not
  turn the switch on, so I read it as a timing flake under load.
- episodes with both switches, 200 iterations from
  `reviews/impl_force_hold/ep_iters.py` (d9_setup wrapped to set
  numSolverIterations 200 after D9 as ep_probe.py did, 'solver_iters'
  registered there as a stand-in name so `--slip-fixes
  solver_iters,force_hold` passes the refusal with no escape; the hold and
  the gear are the branch's code), `ep.sh <seed> <tag>` under the lock,
  `--allow-g19-mismatch 1`; outputs in `reviews/impl_force_hold/runs/`.
  One episode is a coin flip:

  | run | outcome | wall s | plans | steps | planning s | exec s |
  |---|---|---|---|---|---|---|
  | base seed 0 (off check) | success | 17.5 | 3 | 12 | 6.7 | 7.9 |
  | s0, 50 it. (on check) | failure, die lost in carry | 59.2 | 3 | 10 | 26.0 | 21.7 |
  | s0_i200 | failure, pick_giveup | 52.6 | 8 | 19 | 21.9 | 26.7 |
  | s0_i200_rep2 | success | 16.8 | 3 | 10 | 6.6 | 7.3 |
  | s1_i200 | held at home, reward 1.0 | 129.0 | 14 | 45 | 77.4 | 46.6 |
  | s6_i200 | held at home, reward 1.0 | 77.4 | 5 | 22 | 37.0 | 35.6 |

  (tools/episode_metrics.py; "steps" are dispatched steps; seeds 1 and 6
  are gate_failed only by G19, the laptop's scene mismatch.) Die holds
  (force_hold lines): seed 1 half-width 10.37 mm, pads 3.39/3.04 N at the
  hand-over; seed 6 10.39 mm, 3.96/3.92 N; seed 0 rep2 10.04 mm,
  6.71/6.68 N.

## Finding: a cup release jam under force_hold (seed 0, s0_i200)

The plan placed d_cups_ud at free_000 (0.546, -0.128) after a "pose too
uncertain, look first" replan. After `open_gripper` the release verify
read `link12: d=-10.57mm, F=113.39N; link13: d=-0.82mm, F=108.94N`,
finger_pos 0.0391/0.0380: the pads ended deep inside the cup's collision
geometry and pressed it with 110 N; three retries did not free it, the cup
stayed on the hand (HELD-STATE ANOMALY on every later step), and the three
later die picks arrived 11 to 55 mm off and closed on nothing until
pick_giveup. The same cup released cleanly in base's two seed-0 runs and in
rep2 (placed at the other spot, 0.643, 0.066), and the four cups of seed 1
and the three of seed 6 released cleanly (seed 6's e_cups_ud failed the
observed release once, "moved 3.6 mm between two renders", a settle, then
the replan went on). The 50-iteration run had the same pick-and-place of
d_cups_ud fail its release with a light touch (d -0.10 mm, 0.58 N).
Mechanism not measured; the review's "unresolved contact" (s1_f20_i200,
the pads 3.4 mm per side inside the die during the lift) is the same
family: a force-limited finger with its target 4 mm inside keeps pushing
into a contact the solver does not resolve, here a hollow cup's mesh. The
probe never tested a place and release under the force hold; the review
listed places and stacks with a pressed body as untested. Suggested first
measurement: the hp_probe carry with a cup placed and released (pad
penetration per step during the place descent and the open), gear + 200
iterations + 10 N.

## Jam probe (the orchestrator's request of 19:30; 19:35 to 20:25)

Harness: `probes/force_hold/jam_probe.py` (main checkout, run through
`run.sh`, physics only, no lock). Their empty table; the seed-0 cup
d_cups_ud from their create_ycb (concave, 28 VHACD hulls) at the scene's
pose (1747173591.670785.json), D9's values and the gear through the
branch's own `policy.d9_setup`; the branch's close, hold and open
(`robot_utils`), iterations set after D9 as ep_iters.py does. The pick is
at the episode's grasp (top down, yaw 0, contact z 64.1 mm); then the 10 cm
lift, the straight joint line home (9 pairs, settle, the home hold), the
line to the place's approach configuration, the place descent to the same
contact z (execute_place's rule), and the release as
`_release_and_verify_drop` does it (open, 30 steps, verify fingers >=
0.038 and no robot contact, up to 3 attempts). Places: free_003 (the base
and rep2 spot) by IK, and `ep000`, the s0_i200 episode's own configurations
from its eye.jsonl records 18 and 19 (the hand over free_000 at z 351 mm,
the contact at z 65.5 mm, a joint-space descent of 0.76 rad on joint 1
and 0.86 rad on joint 3, the log's "stretching 60 -> 95 steps"). Each
step records the hand's z (commanded and actual), the cup's pose in the
hand frame, q1 and q2, per pad the normal force and the deepest distance
of its contacts with the cup, the other robot links' contacts, the
cup-table force and the cup's tilt. 8 trials per cell; the cup's position
jittered by up to 2 mm per trial (the episodes' pick arrival errors are 1
to 3 mm). Summary by `analyse.py` (out/b1_*.json):

| lever (200 it. unless named) | free_003 jams | ep000 jams | carry turn med (deg) | pad d in the descent, med (mm) |
|---|---|---|---|---|
| base (60 N position hold) | 3/8 (1 deep) | 2/8 | 3.2 / 7.4 | -0.91 / -1.08 |
| base, 50 it. | 3/8 | 0/8 | 4.1 / 3.3 | -1.22 / -1.11 |
| force_hold as implemented | 1/8 | 1/8 | 1.0 / 1.6 | -0.26 / -0.30 |
| force_hold, 50 it. | 2/8 | 1/8 | 4.6 / 3.1 | -0.31 / -0.53 |
| 10 N, 1 mm reach | 1/8 | 0/8 | 3.1 / 3.3 | -0.22 / -0.34 |
| 20 N | 1/8 | 0/8 | 2.5 / 1.5 | -0.34 / -0.40 |
| gear removed | 2/8 | 1/8 | 2.3 / 1.7 | -0.31 / -0.27 |

The jam happens under every hold law, base included: base 8 of 32 releases
(25 %), every force_hold variant 9 of 64 (14 %), force_hold as implemented
2 of 16. Fewer under force_hold, but not significantly (Fisher two-sided
p 0.26 for 8/32 against 9/64, p 0.46 for 8/32 against 2/16). 17 of the 18 jams are light (after the last open one pad still
touches the cup at d -0.01 to -0.91 mm and 0.02 to 7.7 N; the cup leans on
a finger), the kind of the 50-iteration on-check episode (d -0.10 mm,
0.58 N). One is deep, under base (free_003 trial 1: the cup slipped 8 to
11 mm and turned 15 deg in the hand during the carry; after the open a pad
sat 7.3 mm inside it at 143 N). The episode's deep jam under force_hold
(d -10.57 mm, 113 N) did not recur in the 64 force_hold trials, its own
place configurations included. The jammed trials turned more in the hand
during the carry than the released ones (median 4.3 deg, n 18, against
2.8 deg, n 94).

The same light jam is in base's own episodes: loss_dynamics' s14_base_r1
(no fix, 50 iterations) failed the release of e_cups_ud three times with
link13 at d -0.01 mm, 0.16 N, the cup tilted 10.6 deg. The episode tally:
base 1 jam in 19 places (loss_dynamics' six base runs, 17 places, plus my
two base seed-0 checks); force_hold 2 in 10 places (my six episodes).
Fisher's test cannot separate those (two-sided p about 0.27).

The hypotheses:
- (a) The cup moving in the hand under the 10 N hold: no. The cup is
  0.019 kg (CLASS_MASS_KG), so at 97 m/s^2 its inertial load is 1.8 N
  against a friction capacity of 2 x 1.2 x 10 = 24 N. Measured under
  force_hold: carry slip along the hand's z 0.09 to 0.15 mm median (max
  0.25), turn 1.0 to 1.6 deg median (max 4.2). Base's 60 N position hold
  lets it move more (turn 3.2 to 7.4 deg median, max 47; at 200
  iterations base dropped or nearly dropped the cup in 3 of 16 carries,
  slip up to 287 mm).
- (b) The place descent driving the pads in: no under force_hold. The
  deepest pad contact during the descent is -0.26 to -0.30 mm median
  (min -0.56) against base's -0.91 to -1.08 mm (min -7.27, the deep jam).
  The penetration does not grow during the descent beyond the contact
  softness; the episode's deep penetration has no counterpart in the
  harness.
- (c) The open cannot clear the cup: the geometry allows it when the cup
  is upright and centred. The ray profile (`cup_profile.py`,
  out/cup_profile.txt; heights above the cup's bottom): a lip of radius
  37.4 to 37.8 mm in the bottom 8 mm, the wall 32.3 to 33.1 mm from 12 to
  64 mm, 28.5 mm above 68 mm. The AABB's 49 mm half-width is a hull
  bounding box, not the surface (no ray reached past 37.8 mm). The pads
  grasp at the hand's z of 64.1 mm, where the wall is 32.4 mm (measured
  half-width 33.2 mm). At the full open the finger links' inner faces sit
  about 38.9 mm from the hand's axis (the finger gap 2q - 2.2 mm), 5.8 mm
  outside the wall, and the fingertips stay far above the lip. A pad
  touches after the open only if the cup's axis is 5.8 mm or more off the
  hand's axis, or the cup leans: 4 deg of lean over the 60 mm from the
  table contact to the pads moves the wall about 4 mm. In the episode the
  pads did not end lower on the cup than where they grasped it (the hand
  at 65.4 mm at the pick, 65.5 mm after the open). The cup's bottom was
  2.3 mm into the table and it leaned 2.8 deg. A pad 10.6 mm deep is
  inside the wall's hull, which the cup's geometry cannot produce from
  outside: the pad had passed into the hull during the place descent. The
  harness did not reproduce that.
- (d) The gear at the open: no. Its maxForce is 50 N against the open's
  200 N per finger, so it cannot hold a finger back. The episode's 1.1 mm
  asymmetry (39.1 and 38.0 mm) is the contact blocking finger 12 at 113 N.
  The gear-off lever jams as often (3/16 against 2/16).

Verdict: the cause is not in the switch. The jam is the release's: the
fingers open in place and `_release_and_verify_drop` reads any robot
contact as a failed drop. A cup that leans on a finger after the open stays
there through the three retries, because the hand does not move between
them. Base has it in the harness (25 %) and in its own episodes (s14). The
force hold reduces the lean and the penetration that feed it. No change
on slip/force_hold. What else must change is outside this fix's files:
the release (`execution._release_and_verify_drop`, `execute_place`,
`execute_stack`). One candidate: a retreat along the approach axis after
the open, before the contact verify. It is the physical inverse of the
pick's descent; audit #85's 15 mm pre-release lift was removed in #P1
for another reason, which execute_place's comment says to restore "with a
physical justification" if drop verification regresses. That would be
its own switch, and it is a model-side executor change. The episodes'
deep jam (1 in 10 force_hold places, 0 in 64 force_hold harness releases,
1 in 32 base harness releases) stays open. To catch it, run the
harness with the episode's exact pick state (the look and re-pose before
the pick, the grasp at the eye's estimate 1.4 mm off) and 30 or more
trials at ep000 under both holds.

No fix, so no new episodes (the orchestrator's three seed-0 runs were for
after a fix).

Data (main checkout, `probes/force_hold/`, untracked, 5,531,120 B in 34
files): jam_probe.py 15,602 B, run.sh 627 B, batch1.sh 679 B, analyse.py
1,804 B, cup_profile.py 2,338 B; out/ 5,510,070 B in 29 files (14
b1_*.json with trial 0's per-step trace each, 14 b1_*.txt per-trial
lines, cup_profile.txt). Deleted: out/smoke.json, smoke_fh.json and
smoke_base.json (11,839 B, the harness's first runs, superseded by
batch 1).

## Deviations

- The on-check ran with only `force_hold` and the escape, as the
  orchestrator instructed, so at 50 iterations; it is red by design. The
  real configuration ran through `ep_iters.py`, a wrapper outside the
  branch that sets 200 iterations as ep_probe.py did (not the
  solver_iters branch's code).
- A third seed-0 run beyond the asked seeds 1 and 6, twice, because seed 0
  failed with the fix on (the check scene).
- The pad forces are logged at the hand-over to the force hold (end of the
  60-step position hold), not at the open.
- The block's imports in robot_utils sit mid-file with the block (merge
  hygiene), with noqa E402.
- The refusal is checked at the hold point after the 60-step position hold
  (inside the hold block), not at the start of the close; in practice the
  gear's check (d9_setup, `_setup_scene`) fires first.
- No DATA_LEDGER.md row: the ledger is a tracked file of the main
  checkout, which the brief says not to edit; the rows are below for the
  orchestrator.

## Open questions for the implementation reviewer

1. The cup release jam above: is it the force hold (pads driven into a
   hollow mesh during the place descent) or a place-height issue the force
   hold only exposes? It decides whether force_hold can go to the cluster
   as is; on 1 of 2 seed-0 episodes it ended the episode.
2. Should the switch also stop the 60-step position hold (the proposal's
   wording) once the hold from the touch is probed? Today it keeps the
   tested start.
3. Merge: the configure hunk and `import slip_fixes` in policy.py are
   byte-identical to slip/solver_iters'; the orchestrator keeps one.
4. The per-carry fields the review asked for (|q1 - q2| max, the sink
   during the lift and the carry, zero-force steps) are not logged; only
   the per-hold line at the hand-over. They need a carry-time hook in the
   dispatcher, outside this fix's files.

## Data generated and deleted

Kept (untracked):
- worktree `archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/checks/`:
  `2026-10-31_18-30-12_s0_force_hold` 321,034 B in 21 files (on check),
  `2026-10-31_18-44-30_s0` 347,174 B in 21 files (off check); garbage
  once the orchestrator has recorded them (slip_check's rule).
- main checkout `reviews/impl_force_hold/`: ep_iters.py 1,861 B, ep.sh
  1,148 B; runs/s0_i200 468,174 B (18 files, the cup jam's evidence, keep
  until the implementation review), runs/s0_i200_rep2 326,433 B,
  runs/s1_i200 1,234,491 B, runs/s6_i200 784,197 B (18 files each).
  Total 3,484,512 B. The save/ folders (pickles, work/) become garbage
  after the implementation review; stdout.txt and the run logs are the
  evidence.

Deleted: nothing.
