# BF#59 implementation review: carry_hold_check (slip/carry_hold_check 85618e2)

Reviewed 2026-10-31 20:50 by the orchestrating session from the diff
against f060429 (execution.py +110 -4, test_full_pipeline.py +59, tests
+216) and the implementer's report reviews/impl_carry_hold_check.md.

## Verdict: accept, no change requested; the loss path gets an injected run

1. The switch. Registered at execution's import; `carry_hold_begin`
   returns None at once when the switch is off or the hand is empty, and
   `carry_hold_end` returns None when begin did: no read, no print, no
   motor command on the off path. The dispatcher's move action calls
   begin before the waypoint stream and end after the home hold, the
   at-home test and the home_not_reached check, before
   `_integrity_after`; its `if _carry is not None and not _carry.held`
   never fires off.
2. The off path's one change is a refactor: the post-lift re-verify's
   inline `getContactPoints` and set comprehension became the shared
   helper `held_pad_contacts` (the same query, the same pad filter, the
   same summed force; `lift_pads` is now a frozenset, and
   `frozenset != set` compares by value as before); the rule, the print
   and the abort are unchanged.
3. The rule is the review's: both pads in contact with the held body,
   no force floor (the eval's losses were "links none" in 35 of 36), the
   force a logged number. The verdict function is an executor
   postcondition like the post-lift re-verify: on a loss it prints the
   loss line, opens the gripper (the fingers are closed on nothing) and
   returns held=False; the dispatcher then takes the place entry's
   empty-hand path copied line by line (the transit strike with the
   giveup at 3, the held state cleared, `audit_robot_held_state`, the
   belief's pose unknown, the lost-region refresh, `retire_lost_objects`,
   `dispatch_end('empty_hand')`), plus one sound addition: the current
   configuration is rebuilt by `_readback_config` without the lost body
   as cargo (the same helper every other readback uses), so the next
   plan does not start from a configuration that carries a body no
   longer held.
4. The per-carry line (finger readback at the start and the end, the
   width growth, the wrist travel, the pads and force at the end, which
   hold pressed the pads, held or LOST) is a metric and never a trigger,
   as the review asked. The loss line's exact text is
   "ERROR: grip lost in the carry for dice: ..." and tools/slip_eval.py
   now counts it (`CARRY_LOSS_RE`), once per event (see 7).
5. Rules. Executor side (a postcondition and the existing empty-hand
   path); pipeline-wide (every held body, every move, both worlds); no
   truth read (joint readbacks and the robot's own contacts; the
   post-lift print's allowlisted pose read was not copied); no allowlist
   line; narration kept; the copied giveup print uses a comma.
6. Tests (10): the registry, the off path's silence, the empty hand, a
   held and a lost carry with the printed fields and the gripper
   command, one pad is a loss and two pads at 0.1 N are held, the hold's
   name under force_hold, the helper's filter, the post-lift re-verify's
   unchanged rule, the dispatcher's block by source. Checks green on and
   off (63 + 89, gates PASS, seed 0 success). Six laptop episodes with
   the switch on (seed 1 once, seed 6 four times): every carry held, so
   the loss path never ran in an episode; seed 6's four runs were two
   bit-identical pairs of carries (a note for the replication design:
   on a quiet laptop the planner settles into a few plans).
7. The harness, found while reading the logs: the pipeline's prints
   land in both console_debug.log and run_*.log, the curated console
   lines in stdout.txt and console_debug.log, and slip_eval.py joined
   the logs, so every lift loss and pick try was counted twice. Fixed on
   tampura-bridge (count_carries reads each line in one file:
   stdout.txt for the verified pick and the goal check, console_debug.log
   for the pipeline's prints, with fallbacks) with tests/test_slip_eval.py.
8. Decisions on the open questions. A move that ends the episode as
   home_not_reached or streams nothing is not checked: right, nothing to
   check. A re-pick after a loss counts as a second carry, since "firm
   grip" counts each verified pick: right, losses per carry is the
   metric. The transit strike counter now counts mid-carry losses of the
   target and gives it up at three: accepted, it is the existing rule
   for place-entry losses; under base the first loss ends the episode at
   the goal check instead, so the arm with the switch gets more carries
   per episode, which the per-carry metric absorbs.
9. The untested loss path runs once before the snapshot through
   reviews/impl_carry_hold_check/ep_loss_inject.py (the orchestrator's
   wrapper): one seed-0 episode of the campaign branch where the helper
   reports no pads the first time carry_hold_end asks about the die
   while both pads really hold it; the gripper then opens for real and
   the path (the loss line, the strike, the refresh, the replan) runs on
   the world as it is. Recorded in STATE.md.

## For the merge

- test_full_pipeline.py's move action: the begin hook sits before
  carry_trapezoid's `stream_move_waypoints` call (resolved by hand in
  slip/campaign 1f8faea); the end block merged clean.
- The source test of the dispatcher's block may look for the old
  waypoint loop; the merged unit tests say.
