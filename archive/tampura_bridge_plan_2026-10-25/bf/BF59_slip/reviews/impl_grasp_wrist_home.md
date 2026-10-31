# BF#59 implementation: grasp_wrist_home

Started 2026-10-31 by the implementing agent (round 1). Worktree
`C:\Users\HaniAlassiriAlhabbou\git\sb-slip-grasp_wrist_home`, branch
`slip/grasp_wrist_home`, base 05dcaf3 (tampura-bridge). Filled as the work
goes. Finished 2026-10-31 19:40.

## 1. Branch and commits

Branch `slip/grasp_wrist_home` (Windows git, staged by path, not pushed):

- c659e64 `BF#59 grasp_wrist_home: the sampler takes the pad-swapped grasp
  twin whose wrist is nearer home (switch, default off)`: pose_belief.py,
  streams.py, tests/test_slip_grasp_wrist_home.py.
- b6a0b90 `BF#59 grasp_wrist_home: the joint-7 formula probe against the
  kin stream's IK and the episodes, its scripts and summaries`:
  archive/.../BF59_slip/probes/grasp_wrist_home/ (scripts and .txt
  summaries; formula.json and the episode folders stay untracked).

## 2. Files and functions changed (line numbers on the branch)

- `pose_belief.py`
  - top (19 to 28): `import slip_fixes` and
    `slip_fixes.register('grasp_wrist_home', ...)` at import.
  - after `fitted_grasp_candidates` (211 to 285; the functions at 251
    and 262): the narration
    block (why today's yaw is half a turn from the wrist, the review's
    numbers), `PANDA_TOP_DOWN_Q7_OFFSET` (5 pi / 4), `PANDA_Q7_LIMIT`
    (2.8973), `WRIST_HOME_TIE_BAND` (5 deg, with the measurement),
    `wrist_joint7_top_down(target_xy, base_xy, grasp_yaw)` and
    `wrist_home_twin(grasp_yaw, target_xy, base_xy, q7_home, tie_band)`.
    Pure numpy, no pybullet, as the module's header says.
  - `_wrap` and `fitted_grasp_candidates` themselves are unchanged (the
    choice is applied after them, so `believed_margin`, which calls
    `fitted_grasp_candidates` and is sign-blind, sees today's list).
- `streams.py`
  - imports (84): `import slip_fixes`.
  - module function `_prefer_wrist_home(obj_id, obj_boxel, candidates,
    base_xy, q7_home)` (93 to 129): maps every candidate through
    `wrist_home_twin`, logs one line per candidate.
  - `BoxelStreams.sample_grasp` (882 to 889): after the M9 / AABB
    candidates are built, `if slip_fixes.on('grasp_wrist_home'):` the
    candidates go through `_prefer_wrist_home` with the robot base
    (`self._robot_base_xy`, cached at construction) and home joint 7
    (`self.home_config.joint_positions[6]`, read at call time, so
    `set_home_joints` is honoured: DEFAULT_ARM_POS in the bridge,
    REST_POSES in our scenes). The orientation at the old line 869
    (`getQuaternionFromEuler([0, pi, yaw])`) is unchanged and takes the
    chosen yaw.
- `tests/test_slip_grasp_wrist_home.py` (new, 7 tests).

## 3. What the switch does, on and off

Off: the code path is today's exactly (the `if` is the only new branch in
the sampler; nothing else reads the new functions). On: for every grasp
candidate the sampler would offer (M9's fitted candidates or the AABB
path's yaw 0 and pi/2), it yields the member of {yaw, yaw + pi} whose
predicted joint 7 is nearer home's; the span, the z offsets, the count and
the order are unchanged. Every body (rule 2), both worlds. The kin stream
certifies the chosen orientation as it certifies today's (no change
there). Not touched: `believed_margin` (sign-blind), the executor's
sizing (`pinch_direction`, `sized_pinch_half`, sign-blind), the place and
stack kin (they take the grasp's orientation as given).

## 4. How "nearer home" is computed (no IK in the sampler)

With the hand pointing down, joint 7 turns the hand about the vertical
against joint 1, so the hand's world yaw is `bearing - q7 + C`, with
`bearing = atan2(target - base)` (the base's own yaw cancels: joint 1 sits
at bearing - base yaw). C follows from one configuration: at REST_POSES
(q1 = 0, q7 = pi / 4) the hand is top_down(pi), so C = 5 pi / 4, and
`q7 = wrap(bearing - yaw + 5 pi / 4)` in [-pi, pi). The distance to home
is `|clip(q7, +-2.8973) - q7_home|` (a predicted joint 7 past the limit is
where the IK clips). The twin is taken when its distance is smaller by
more than twice the tie band (today's member more than the band past the
quarter-turn split).

Checked three ways:

1. FK: REST_POSES' hand is top_down(pi) within 0.02 deg on both URDFs
   (their PANDA_PATH and pybullet_data's).
2. The kin stream's own IK (`_pybullet_ik` over `_ik_seeds`, first
   certified seed) on a grid: their Panda over W (25 cells x 10 yaws, base
   at the origin, home DEFAULT_ARM_POS) and ours (20 cells x 10 yaws, base
   (-0.4, 0, 0), home REST_POSES); `probes/grasp_wrist_home/
   probe_wrist_formula.py`, `formula.json`, `analyse.py`. Prediction error
   against the IK's joint 7: the near (chosen) member median 3.5 deg, p95
   11 deg (find_dice) and 17 deg (ours); the far member median 5 deg but
   p95 25 to 38 deg (the IK's null space, joints 1, 3, 5, absorbs part of a
   large wrist turn, so today's far member sits nearer home than
   predicted). The choice with the 5 deg band picks the member the IK puts
   nearer home in 236 of 239 (find_dice) and 126 of 130 (ours) cells with
   IK for both; it never picks the IK-farther member (the misses keep
   today's member inside the band, where the two differ by 1 to 13 deg).
   The clip: today's member lands at the joint-7 limit in 26 of 250 cells
   (find_dice) and 10 of 200 (ours), the chosen one in 0; cells without IK
   11 and 70 today, 10 and 70 chosen. Median joint-7 distance to home of
   the IK solutions: today 132 and 123 deg, chosen 45 and 44 deg (over the
   whole grid, not the die's window).
3. The recorded episodes (`episodes_check.py`, `episodes_check.txt`): the
   die's believed centre before the pick, the grasp yaw of the last
   sample_grasp line, the recorded joint-7 travel home (base: nine times
   the first waypoint pair's dq7, the planned linear path, as the review
   reads it; flip: the proposal's 1.3 table):

   | episode | yaw | predicted q7 | predicted travel | recorded travel | switch's choice |
   |---|---|---|---|---|---|
   | s0_r1 held | 0.0 | -2.046 | 162 | 167 | twin (-180), 18 deg |
   | s1_r1 held | -38.4 | -2.075 | 164 | 183 | twin (141.6), 16 deg |
   | s1_r2 lost | -38.4 | -2.075 | 164 | 183 | twin (141.6), 16 deg |
   | s1_r3 lost | -43.5 | -1.985 | 159 | 177 | twin (136.5), 21 deg |
   | s6_r1 lost | -10.9 | -2.482 | 187 | 199 | twin (169.1), 7 deg |
   | s0 flip+trap | 179.9 | +1.098 | 18 | 22 | kept |
   | s1 flip+trap | 141.5 | +1.068 | 16 | 12 | kept |

   The predicted travel is within 4 to 19 deg of the recorded one (the
   far member errs most, as on the grid), and the switch takes the twin in
   all five base carries and keeps the flip episodes' yaw.

## 5. Logging

One line per grasp candidate per sample_grasp call, through the streams
logger at DEBUG (the run log `run_*.log`, which tools/slip_eval.py reads;
DEBUG like sample_grasp's own per-grasp lines, so the console is not
flooded): `grasp_wrist_home: <obj> yaw <deg> (joint 7 <rad>, <deg> from
home) or twin <deg> (joint 7 <rad>, <deg> from home): twin|today's`, and
`grasp_wrist_home: <obj> has no believed box ...: today's yaws kept` for
a pre-sense object without a boxel. The eval's counted lines are
untouched.

## 6. Tests

`tests/test_slip_grasp_wrist_home.py`, 7 tests, the registry's ENABLED and
KNOWN restored after each (fixture `switch`), M9 restored (`m9_on`):

- registered at import, off by default, configurable;
- off: the sampler's yaws are `fitted_grasp_candidates`' (today's wrap,
  in [-pi/4, pi/4)) on six yaws;
- on: the same six yaws, each yielded grasp is the twin (half a turn from
  today's), its predicted joint 7 nearer home and within 90 deg of it;
  count and z offsets unchanged;
- on, the AABB path (M9 off) of a rectangle: twins, spans kept;
- a yaw already nearest home (home set to today's joint 7) is unchanged,
  through the sampler and through `wrist_home_twin`;
- the tie band: a tie keeps today's yaw, 4 deg past the split keeps it,
  6 deg flips;
- the formula against the kin stream's IK on pybullet_data's Panda (9
  cells): the chosen member has IK, its joint 7 within 15 deg of the
  prediction, and nearer home than the other member's.

Result: 7 passed alone (5 s); the whole unit suite 60 passed in both
checks (53 before plus these 7).

## 7. Checks (outputs under the worktree's archive/.../BF59_slip/)

| run | unit tests | bridge tests | gates | episode |
|---|---|---|---|---|
| fix on: `checks/2026-10-31_18-42-39_s0_grasp_wrist_home` | 60 passed | 88 passed, 1 failed (test_gf9_gated_episode), 3 skipped | G7, G11(i), G17 PASS | seed 0 success, slip_fixes "grasp_wrist_home", 1 die carry; wall 16.6 s, 3 plan calls, planning 5.9 s, 12 steps, move_s 3.6 |
| fix off: `checks/2026-10-31_19-01-55_s0` | 60 passed | 87 passed, 2 failed (test_gf9_gated_episode, test_b3_parameterisation::test_adopted_goal_at_home_episode), 3 skipped | PASS | seed 0 success, slip_fixes "", 1 die carry; wall 122.2 s, 5 plan calls, planning 63.8 s, 18 steps, move_s 26.3 |

The bridge failures are the two goal-at-home episode tests (random-pairs
episodes, planner timing under load: the bridge suite took 60 and 127 s
against 55 s unloaded; the force_hold worktree's check failed
test_b3_parameterisation the same way and passed on its rerun). They fail
with the switch off too (tests never switch fixes on), and pass alone on
this branch under the lock: `probes/grasp_wrist_home/run_gf9.sh`, gf9 1
passed (32.6 s), then gf9 + test_b3_parameterisation 5 passed (111.8 s).
So: not caused by the change; the reviewer may want a third full run on an
idle machine.

The seed-0 times are not a step-time comparison (the change does not
touch the step): the two runs bound different plans (3 against 5 plan
calls; planner wall-clock non-determinism, loss_dynamics 1.4), and the
fix-on episode's die grasp was the twin (log: "dice yaw 0.0 deg (joint 7
-2.05 rad, 162 deg from home) or twin -180.0 deg (joint 7 +1.10 rad, 18 deg
from home): twin"), as was the cup's (d_cups_ud, the same numbers).

Laptop episodes with the switch on, one each, under the lock
(`probes/grasp_wrist_home/run_eps.sh 1 6`, `--allow-g19-mismatch 1`):

- seed 1 (laptop scene 1747173590): the die picked once and held at home,
  their reward 1.0 (outcome label gate_failed only from G19, the expected
  laptop scene mismatch; every other gate PASS); 8 plan calls, planning
  52.8 s, exec 32.2 s, wall 89.9 s, 33 steps, 5 picks (4 cups, the die),
  0 refused picks, 0 losses. The die grasp: "dice yaw -38.4 deg (joint 7
  -2.07 rad, 164 deg from home) or twin 141.6 deg (joint 7 +1.07 rad, 16
  deg from home): twin" (16 of 16 switch lines, 7 twins). The carry home
  (direct linear path, 9 pairs): joint 2 is the largest mover of every
  pair at 0.33 rad, where in every base carry joint 7 was the largest at
  0.32 to 0.39 rad per pair. Pad force at the pick 2.47 N, half-width
  10.4 mm. Base on this scene held 1 of 3 (loss_dynamics s1_r1 to r3);
  one episode carries no rate.
- seed 6 (laptop scene 1747173593): the cup loop the review expected
  without pose_radius_keep. 43 refusals "e_cups_ud's pose is too
  uncertain", 89 plan calls, 45 cup picks, no die pick, no die carry;
  stopped by my own 900 s timeout (rc 124; the driver has no cap of its
  own, the eval's is 600 s), so no outcome line. Not fixed here
  (pose_radius_keep's branch).

## 8. Deviations from the proposal and the review

- Where: the choice is applied in `streams.sample_grasp` after the
  candidates are built, not inside `fitted_grasp_candidates` with a
  `ref_orn` (the proposal). One point covers both the M9 and the AABB
  path, and `believed_margin` keeps calling the unchanged function.
- The reference: home's joint 7 and the base's bearing to the target,
  not FK of home's hand orientation (the proposal's `ref_orn`). No FK, no
  resetJointState on the plan client, so no G1 allowlist line (the review
  allowed either); joint 7 is what the carry unwinds, and the bearing
  removes the review's concern that a world-frame angle ignores the base
  joint's turn. Home's joint 7 is read at call time, which meets the
  review's "recompute it in set_home_joints" without a hook.
- The tie band: 5 deg, not the review's "say within 20 deg". Measured
  (section 4): 20 deg keeps today's member in 42 grid cells where the twin
  is up to 39 deg nearer; 5 deg never picks the IK-farther member; 0 deg
  picks it in 4 cells, by up to 11 deg. Applied to every candidate, not
  only rectangles (one rule; a square's split is at bearings near
  +-90 deg, which our scenes can reach).
- The quarter-turn members of a square are not offered (the proposal's
  log 10: they add nothing over the half turn), as the brief says.
- Logging at DEBUG, not INFO (section 5). Not done here: the review's
  per-pick joint-7 readback and per-carry planned travel lines (outside
  the sampler; the telemetry's waypoint notes and carry probes give them).

## 9. Open questions for the implementation reviewer

1. The tie band: 5 deg on the grid's evidence, against the review's
   "say 20". The grid is coarse (25 and 20 cells, 10 yaws); a denser grid
   over W would firm it up. Either value leaves the die's window alone
   (every die grasp there sits 140 deg or more past the split).
2. The prediction ignores joints 3 and 5. For today's far member it errs
   by up to 55 deg (the IK absorbs part of the wrist turn), which only
   matters near the split; choosing by the kin stream's own IK (the
   review's alternative) would cost two IK solves per candidate per
   sample_grasp call. Is the analytic rule enough?
3. A pre-sense object without a boxel keeps today's yaw (no bearing).
   Those grasps are re-sampled once the object is registered (seed 0:
   four "no believed box" lines for the die, then the twin), but a plan
   bound before that carries today's yaw. Acceptable?
4. The place and stack poses follow the grasp: in our scenes the hand
   keeps its world yaw from pick to place, so a place far from the pick's
   bearing can sit farther from home than today's. Unmeasured, as the
   review says; the eval's own-scene guard is the check.
5. The flaky goal-at-home bridge tests (section 7): pre-existing, but the
   campaign's check script counts them; worth a note in STATE.md.
6. The seed-6 cup loop: the arm for this switch must run with
   pose_radius_keep on (STATE.md's job B does).

## 10. Data generated and deleted

All under the worktree's `archive/tampura_bridge_plan_2026-10-25/bf/
BF59_slip/`, untracked except where marked (ledger row for the
orchestrator, who owns DATA_LEDGER.md in the main checkout):

| path | size | kept for | garbage when |
|---|---|---|---|
| probes/grasp_wrist_home/ scripts and .txt (tracked, b6a0b90) | 27 KB | this report, section 4 | never (evidence) |
| probes/grasp_wrist_home/formula.json | 177 KB | analyse.py's input (regenerable by run_probe.sh in about a minute) | after the implementation review |
| probes/grasp_wrist_home/episodes/s1 | 0.99 MB | section 7, seed 1 | after the implementation review (keep stdout.txt and the run log if cited) |
| probes/grasp_wrist_home/episodes/s6 | 4.26 MB | section 7, the cup loop | after the implementation review (a known cause, BF#59 loss_dynamics 1.6) |
| checks/2026-10-31_18-42-39_s0_grasp_wrist_home | 0.35 MB | section 7 | once this report is accepted |
| checks/2026-10-31_19-01-55_s0 | 0.42 MB | section 7 | once this report is accepted |

Deleted: nothing yet (every item above is cited here and waits for the
implementation review). No pytest cache was written (`-p no:cacheprovider`
in my scripts; slip_check.sh's own runs may leave .pytest_cache in the
worktree, untracked).
