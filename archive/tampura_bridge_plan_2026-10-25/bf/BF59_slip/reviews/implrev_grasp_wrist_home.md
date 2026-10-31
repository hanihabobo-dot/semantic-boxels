# BF#59 implementation review: grasp_wrist_home (slip/grasp_wrist_home c659e64, b6a0b90)

Reviewed 2026-10-31 20:08 by the orchestrating session from the diff
against 05dcaf3 (pose_belief.py +83, streams.py +44, tests +195, the
probe's scripts and summaries) and the implementer's report
reviews/impl_grasp_wrist_home.md.

## Verdict: accept, no change requested

1. The switch. Registered at pose_belief's import (imported by streams,
   so on both paths); read once, in `BoxelStreams.sample_grasp` after the
   M9 and AABB candidates are built. Off: the `if` is the only new
   statement on the path, nothing else calls the new functions. On: each
   (yaw, span) becomes (the member of {yaw, yaw + pi} nearer home, span);
   count, spans, z offsets and order unchanged; the orientation line
   downstream takes the chosen yaw as it took today's; the kin stream
   certifies it as before.
2. The rule is the review's mechanism done without IK. With the hand
   pointing down, joint 7 turns the hand about the vertical against
   joint 1, so the hand's world yaw is bearing - q7 + C; at REST_POSES
   (q1 = 0, q7 = pi / 4) the hand is top_down(pi) on both URDFs (FK
   checked to 0.02 deg), so C = 5 pi / 4 and
   q7 = wrap(bearing - yaw + 5 pi / 4). The sign is right: for the die
   straight ahead at yaw 0 the formula gives q7 = -135 deg (180 deg from
   home's 45), the twin yaw pi gives 45 deg, and the recorded base carries
   unwound 167 to 199 deg while the flip episodes needed 12 to 22. The
   bearing is measured from the planner's own base (`_robot_base_xy`,
   cached at construction, streams.py 291), so the base joint's turn is
   in it, the review's objection to a world-frame angle. Home's joint 7
   is read at call time (`home_config.joint_positions[6]`), so
   set_home_joints is honoured without a hook. `_wrap(x, 2 pi)` maps to
   [-pi, pi) (pose_belief 142).
3. The validation carries the claim: against the kin stream's own IK on
   450 cells of both worlds the chosen member is the IK-nearer one in 362
   of 369 and never the farther; the prediction errs by a median 3.5 deg
   (p95 11 to 17) for the chosen member and more for today's far member
   (the null space absorbs part of a large wrist turn), which only
   matters near the split. The joint-7 clip of today's grasps (26 and 10
   limit cells) disappears. On the five recorded base carries the twin
   is taken; the flip episodes' yaw is kept.
4. The tie band. 5 deg stands on its measurement (0 deg flips 4 cells to
   a member up to 11 deg farther; 20 deg keeps today's member in 42
   cells where the twin is up to 39 deg nearer). The die's window sits
   140 deg or more past the split, so the band does not touch the
   campaign's carries either way.
5. Rules. Model side (the grasp sampler, before the planner binds it:
   no plan is edited). Pipeline-wide: every body, both candidate paths,
   both worlds, one rule. No truth read (the believed box centre, the
   robot's own base and home). No bridge-only value. Narration kept; the
   block states the derivation and the numbers.
6. Logging at DEBUG in the run log (one line per candidate), where
   tools/slip_eval.py reads; the counted lines untouched.
7. Tests (7): off path on six yaws, on path twins nearer home, the AABB
   path, a yaw already nearest home unchanged, the band at 4 and 6 deg,
   the formula against pybullet_data's Panda IK on nine cells.
8. Checks. Gates PASS, seed 0 success on and off (on: the twin for the
   die and the cup, wall 16.6 s). The bridge suite failed one and two
   goal-at-home episode tests under the laptop's load, with the switch
   off too, and they pass alone under the lock; force_hold's check hit
   the same test. Pre-existing flake family (planner wall clock under
   load); the campaign branch's smoke should run on a quiet laptop.
   Seed 1 on: held, reward 1.0, joint 2 the largest mover home instead
   of joint 7. Seed 6 on: the cup loop without pose_radius_keep, as the
   review predicted (job B pairs them).
9. Decisions on the open questions. (2) The analytic rule is enough: the
   IK alternative costs two solves per candidate per call and the
   grid shows the rule never picks the farther member. (3) A pre-sense
   object without a boxel keeps today's yaw until it is registered and
   re-sampled; a plan bound before that carries today's yaw: accepted,
   it is the rare first plan. (4) The place and stack poses in our own
   scenes follow the grasp's yaw; unmeasured, the eval's own-scene guard
   is the check (for the audit entry). (5) The flake family is in
   STATE.md.

## For the merge

- pose_belief.py: both pose_radius_keep and this branch add
  `import slip_fixes` at line 19 with their own register block after
  it: keep one import, both registers. The helper blocks do not overlap
  (record_detection and the _prk helpers against the block after
  fitted_grasp_candidates).
- The probe's scripts and summaries under probes/grasp_wrist_home/ come
  in with the branch (tracked there, b6a0b90).
