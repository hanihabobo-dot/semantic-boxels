# BF#59 implementation report: carry_hold_check

Written 2026-10-31 by the implementing agent, filled as the work goes.
Worktree `C:\Users\HaniAlassiriAlhabbou\git\sb-slip-carry_hold_check`,
branch `slip/carry_hold_check`, from tampura-bridge f060429 (code identical
to 05dcaf3).

## Status

DONE 20:35. Both checks green; six laptop episodes with the switch on
(seed 1 once, seed 6 four times), no carry loss among them, so the loss
path is tested at the unit level only.

## Branch and commits

- 85618e2 `BF#59 carry_hold_check: the hold postcondition after every
  holding move, the shared pad helper, the per-carry width line`
  (execution.py +110 -4, test_full_pipeline.py +59,
  tests/test_slip_carry_hold_check.py new, 216 lines). Not pushed.

## Where the check lives, and why

The check is split: the senses and the verdict live in `execution.py`
(`held_pad_contacts`, `carry_hold_begin`, `carry_hold_end`), and the call
and the failure handling live in the dispatcher's move action
(`test_full_pipeline.py` main). Why:

- execution.py has no move primitive. A move is the dispatcher streaming
  waypoints through `robot_utils.move_robot_smooth`, which the pick's
  descent, the lift and the place also use and which does not know what
  is held. A check inside `move_robot_smooth` would run on every pick
  descent and lift too, which is not the postcondition the review asks
  for.
- The failure handling is dispatcher state: `held_body_id`, the transit
  strike counter, the giveup sets, `dispatch_end`, the belief refresh.
  The existing empty-hand path (place and stack entry) has the same
  split: `_assert_held_contact` in execution.py detects, the dispatcher's
  `except EmptyHandError` handles.
- The review calls it an executor postcondition like the post-lift
  re-verify: the verdict function sits next to that re-verify, uses the
  same helper, and opens the gripper on a loss as the place entry assert
  does, so the move fails the way an executor primitive fails (a return
  value, as M10's pick returns), and the dispatcher reacts to the return.

## Files and functions changed

(line numbers at the commit)

- `execution.py`
  - 55: `import slip_fixes`; 61 to 72: the narration and
    `slip_fixes.register('carry_hold_check', ...)` at import.
  - 567 `held_pad_contacts(robot_id, body_id)`: the shared tactile helper,
    `getContactPoints(bodyA=robot, bodyB=held)` and returns (pad links,
    summed normal force, pad contact points). It applies no rule.
  - 584 `CarryStart`, `CarryHold` namedtuples; `_finger_readback`,
    `_wrist_readback` (joint readback of both fingers and of joint 7).
  - 597 `carry_hold_begin(robot_id, held_body_id)`: the readback at the
    move's start; None when the switch is off or the hand is empty.
  - 606 `carry_hold_end(robot_id, held_body_id, start, obj_name, dest,
    gui)`: None when start is None; otherwise the readback at the end, the
    helper, the per-carry log line, and on a loss the loss line and
    `open_gripper`; returns `CarryHold(held, pads, force, points,
    growth_mm)`.
  - 1434 to 1438 `execute_pick`, the post-lift re-verify: the inline
    `getContactPoints` and the set comprehension replaced by
    `lift_pads, lift_nf, _ = held_pad_contacts(robot_id, obj_id)`; the
    rule (`lift_pads != set(_fingers)`), the print (the allowlisted
    obj_z line untouched), `open_gripper` and `_failed()` unchanged, no
    switch, no force floor.
- `test_full_pipeline.py`
  - 115 to 116: `from execution import carry_hold_begin, carry_hold_end`.
  - 1886 to 1889, the move action after the runtime re-solve and before
    the waypoint loop: `_carry0 = carry_hold_begin(robot_id,
    held_body_id)`.
  - 1982 to 2033, the move action after the at-home test, the collision
    detection and the home_not_reached check, before `_integrity_after`:
    `_carry = carry_hold_end(...)`; on `not _carry.held` the place entry
    assert's empty-hand handling, copied: the transit strike with the
    giveup at 3, `held_body_id = None`, `held_object_boxel_id = None`,
    `audit_robot_held_state`, `env.update_object_positions()`,
    `pose_belief.mark_pose_unknown`, `refresh_object_aabbs(check_lost=
    True)`, `retire_lost_objects`, `dispatch_end('empty_hand')`, break.
- `tests/test_slip_carry_hold_check.py` (new, 10 tests).

## What the switch does, on and off

- Off (default): `carry_hold_begin` returns None at once, `carry_hold_end`
  returns None at once: no pybullet read, no print, no motor command;
  the dispatcher's `if _carry is not None` is never true. The post-lift
  re-verify calls the helper with the switch off too, with the same
  query, the same rule and the same print.
- On: every move that starts with `held_body_id` set reads both fingers
  and joint 7 before the first waypoint; after the move (after the home
  hold and the at-home test for a move to q_home) it reads them again and
  asks the helper. Both pads on the held body: held, the move goes on as
  today. Otherwise: the loss line, the gripper opened, and the move action
  ends as `empty_hand` (a G3 status that exists) through the empty-hand
  path; `_loop_done` sees an empty hand and the loop replans.

## Log lines

On every move made while holding (held or not), one line:

    carry_hold_check: move to <dest> holding <body>: fingers <a0>/<b0> mm at the start, <a1>/<b1> mm at the end, width growth <+x.xxx> mm, wrist travel <deg> deg, pads at the end [<links>] (<n> points, <f> N), <position|force_hold> hold: <held|LOST>

The finger values are the two finger joint readbacks; the growth is
(a1 + b1) - (a0 + b0); the wrist travel is |joint 7 end - start| (the
review's added variable); the hold names force_hold when that switch is
on (the review: under the force hold a widening is not a loss signal).
A metric, never a trigger.

On a loss, the line the eval counts (exact text, with the die):

    ERROR: grip lost in the carry for dice: pad contacts=none (need both [12, 13]), pad_normal_force=0.00N after the move to view__q_home. Opening gripper and replanning (BF#59 carry_hold_check).

(the pad links are their Panda's 12 and 13 on the bridge, 9 and 10 on
pybullet_data's Panda in our scenes; the destination is the move's boxel
name, `view__q_home` for the carry home in the episodes below)

A held carry as logged (laptop seed 6, the carry home):

    carry_hold_check: move to view__q_home holding dice: fingers 9.585/9.580 mm at the start, 9.526/9.526 mm at the end, width growth -0.113 mm, wrist travel 197.0 deg, pads at the end [12, 13] (4 points, 1.13 N), position hold: held

Regex for slip_eval: `grip lost in the carry for dice`. Then the
dispatcher's existing `transit loss k/3 for dice (review-fix strike
counter)`. The eval's lines ("firm grip on dice", "grip lost after
post-pick lift for dice", "PHYSICAL_FAILURE (goal): (holding dice)",
"Picking dice") are unchanged. tools/slip_eval.py counts losses as the
post-lift losses plus at most one goal-check loss; under this switch a
mid-carry loss no longer reaches the goal check, so slip_eval needs the
new regex added to its loss count (not edited here: it is a campaign
tool on tampura-bridge, the orchestrator's).

## Tests

`tests/test_slip_carry_hold_check.py`, stubs for `getContactPoints`,
`getJointState` and `open_gripper`, the registry restored after each test:

1. registered, off by default, `--slip-fixes` defaults to ''.
2. off: a holding move (begin, then end with a lost body) makes no contact
   call, no gripper command and prints no carry_hold_check line.
3. on with an empty hand: nothing.
4. on, held: held=True, the growth +0.100 mm, the force, the line's
   fields, no loss line, no gripper command.
5. on, lost: held=False (the return the dispatcher acts on), the gripper
   opened once, the LOST line and the loss line; none of the eval's lines.
6. one pad is a loss; two pads at 0.10 N summed are held (no force floor).
7. the line names force_hold when it is on.
8. the helper applies no rule (non-pad contacts not counted).
9. the post-lift re-verify: calls the helper, contact-only rule, no force
   floor, no switch, its eval line intact.
10. the dispatcher: begin before the waypoint loop, end after the
    home_not_reached check and before `_integrity_after`, every step of
    the empty-hand path present, `empty_hand` in G3_STATUSES.

Result: 10 passed (6.5 s).

## Checks

The main checkout's tools/slip_check.sh, seed 0, outputs under the
worktree's `archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/checks/`:

| run | unit tests | bridge tests | static gates | episode | slip_fixes | wall / planning / plans / steps |
|---|---|---|---|---|---|---|
| on, `2026-10-31_19-43-52_s0_carry_hold_check` | 63 passed | 89 passed, 3 skipped | PASS (rc 0, every gate PASS or INFO) | success, 1 die carry | "carry_hold_check" | 48.5 s / 17.1 s / 3 / 10 |
| off, `2026-10-31_20-05-44_s0` | 63 passed | 89 passed, 3 skipped | PASS | success, 1 die carry | "" | 15.0 s / 5.9 s / 3 / 11 |

The on run logged two carry lines (the cup to free_003, the die home,
both held, +0.002 and +0.018 mm); the off run's logs hold no
carry_hold_check line. The wall difference is planning on a shared laptop
(17.1 against 5.9 s of planning; the plans differ, 10 against 11 steps);
the check itself is two joint readbacks and one contact query per holding
move, no simulation step. The step count is unchanged by the switch on a
held carry (it adds a gripper open only on a loss).

## Episodes with the switch on (laptop seeds 1 and 6)

`--allow-g19-mismatch 1`, under the lock, a 900 s `timeout` around the
driver; outputs under the worktree's `.../BF59_slip/episodes/`.

| run | outcome | die carries | carry lines | plans | planning / wall in all (the driver's summary) |
|---|---|---|---|---|---|
| s1 `2026-10-31_20-06-27` | killed by the 900 s timeout (rc 124) | 0 | 3 cup carries, all held | 131 | 681.8 s / 900 s |
| s6 `2026-10-31_20-23-09` | held at home, reward 1.0 (gate_failed for G19 only) | 1 | 4, all held | 5 | 34.3 s / 88.8 s |
| s6 `2026-10-31_20-27-04` | held, reward 1.0 (G19 only) | 1 | 4, all held | 5 | 22.5 s / 59.6 s |
| s6 `2026-10-31_20-28-24` | held, reward 1.0 (G19 only) | 1 | 4, all held | 5 | 41.2 s / 96.0 s |
| s6 `2026-10-31_20-30-30` | held, reward 1.0 (G19 only) | 1 | 4, all held | 5 | 29.0 s / 75.9 s |

- Seed 1 never reached the die: the cup loop of loss_dynamics 1.6 (64
  observes of d_cups_ud, 63 "pose_radius 5.49 mm is outside its commit
  margin" refusals), pose_radius_keep's mechanism, not this switch's.
- Seed 6: the brief asks for one episode; three repeats were added to get
  one real loss through the dispatcher's path. None came: the die carry
  home logged "held" four times, and the four runs form two bit-identical
  pairs (runs 1 and 3: -0.113 mm, 4 points, 1.13 N; runs 2 and 4:
  +0.002 mm, 8 points, 3.62 N), so this scene gave two distinct carries,
  not four draws. The cup carries showed -0.031 to -0.070 mm (the
  fingers close a little on a held cup).
- So no episode exercised the loss path (the loss line, the strike, the
  refresh, the replan); it is covered by the unit tests (the verdict and
  the gripper command) and by a source test of the dispatcher's block.
  The eval's arm C will be the first to run it.

## Deviations from the proposal, and the review's requirements

- The rule is contact presence on both pads, no 0.5 N floor (the review:
  the post-lift check has no floor and the shared helper must not add
  one; the eval's losses were "links none" in 35 of 36). The force is a
  logged number. The proposal said the floor of `_verify_holding`.
- No truth read: the post-lift print's `getBasePositionAndOrientation`
  (allowlisted, print-only) was not copied; no allowlist line is added.
- The predictor line logs the finger readback at the move's start and end
  (the brief's form), not the proposal's widen_max over the carry, nf_min
  or single-point steps: those need a per-step poll in the waypoint
  stream, which carry_trapezoid edits; the wrist travel and the hold name
  were added (the review's predictor section).
- One addition to the copied empty-hand path: after a loss the current
  configuration is rebuilt by `_readback_config` with the hand now empty
  (the same readback, without the lost body as cargo). The place entry
  path does not do this; at the move's end the readback was just built
  with the held body as plan_motion cargo, and the next plan would start
  from a configuration that carries a body no longer held.
- The giveup print of the copied path says "times, giving up" (a comma)
  where the original has an em dash (prose rule).

## Open questions for the implementation reviewer

- The check runs after the home_not_reached check, so a move that ends
  the episode as home_not_reached is not checked (the episode ends
  anyway); a move that ends in `motion_resolve_failed` streams nothing
  and is not checked.
- Should slip_eval count "grip lost in the carry for dice" as a loss
  (yes, in my reading), and count a re-pick after it as a second carry
  (the review: carries per pick, not per episode)? "firm grip on dice"
  already counts each verified pick.
- The transit strike counter now also counts mid-carry losses of a body
  in a holding goal, where nothing clears it (no place delivers); three
  losses of the target give it up (pick_giveup), as for three place
  entry losses.

- The loss path has not run in an episode (see above). A reviewer who
  wants it seen before the eval could replay a recorded losing carry
  (loss_dynamics' s1_r2) with the switch on; I did not, as it needs a
  probe outside this branch.
- Seed 6's four runs repeated two carries exactly: on an idle enough
  laptop the planner's timing seems to settle into one of a few plans.
  That is a note for the eval's replication design, not for this fix.

## Data generated and deleted

All in the worktree (untracked), under
`C:\Users\HaniAlassiriAlhabbou\git\sb-slip-carry_hold_check\archive\tampura_bridge_plan_2026-10-25\bf\BF59_slip\`:

- `checks/2026-10-31_19-43-52_s0_carry_hold_check` 326,614 B and
  `checks/2026-10-31_20-05-44_s0` 339,307 B: the two check runs; garbage
  once this report is reviewed.
- `episodes/run_ep.sh` 986 B (the episode script); the five episode
  folders: `2026-10-31_20-06-27_s1_carry_hold_check` 5,716,848 B (the
  cup loop, killed at 900 s), `2026-10-31_20-23-09_s6_...` 802,113 B,
  `2026-10-31_20-27-04_s6_...` 801,155 B, `2026-10-31_20-28-24_s6_...`
  802,143 B, `2026-10-31_20-30-30_s6_...` 801,157 B; garbage once this
  report is reviewed (the numbers are in the tables above).
- Total kept for review: about 9.6 MB.

Deleted by path: `episodes/gates.sh` 665 B, `episodes/metrics.sh` 355 B,
`episodes/repeat6.sh` 425 B (one-off helpers, done); in the main checkout
`probes/carry_hold_check/pytest.sh` (the first unit-test runner, about
0.4 kB) and its then empty folder `probes/carry_hold_check/`. No
DATA_LEDGER.md row was written (the main checkout is the orchestrator's;
the rows above are for its ledger).
