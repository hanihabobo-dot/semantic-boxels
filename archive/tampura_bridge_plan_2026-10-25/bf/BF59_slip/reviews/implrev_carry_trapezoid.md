# BF#59 implementation review: carry_trapezoid (slip/carry_trapezoid b1e2455)

Reviewed 2026-10-31 20:00 by the orchestrating session from the diff
against ae62b33 (test_full_pipeline.py +227 -26, tests +180) and the
implementer's report reviews/impl_carry_trapezoid.md.

## Verdict: accept the code, no change requested; its arm is decided at phase 7

1. The off path is today's code. The removed block of main's move action
   (the comment on the endpoint hold, the F17 notes from the readback,
   `move_robot_smooth(wp.joint_positions, gui, steps=30, settle=last)`)
   reappears unchanged as the fallthrough of `stream_move_waypoints`;
   main calls it once with `holding=held_body_id is not None`. The
   switch is read only there. Off, or on with an empty hand, nothing
   else runs; the check's off episode is a success.
2. The on path is the reviewed schedule. `carry_trapezoid_schedule` is
   carry_motion's trap_schedule (the code the two episodes and the probe
   ran): collinear merge at cosine 0.9999, zero-length pairs dropped,
   one trapezoid or triangle per segment in the path parameter with the
   F14 velocity limits as the cruise bound and the datasheet
   accelerations as the ramp bound, at rest at both ends of every
   segment, the last command of a segment its vertex exactly. Every
   planned waypoint stays a vertex of the commanded path (rule 1: the
   plan is not edited; the merge drops only interior points of a
   straight line). Every held body (rule 2).
3. No pybullet write is added: each scheduled step is one
   `move_robot_smooth(q, steps=1, settle=False, velocity_bounded=False)`
   call, so the motor write, the step, the telemetry tick and the GUI
   pacing are the primitive's own; the settle is the primitive's settle
   at the last waypoint as today; the home hold after the move is
   untouched. The only new read is the arm's joint readback (the robot's
   own state, as the F17 notes read it today). Gates PASS on and off.
4. `velocity_bounded=False` on the per-step calls is right: the F14
   stretch measures the hop from the lagging readback, so a one-step
   command at cruise would be stretched and restarted per call, the
   junction kick again. The schedule bounds the command itself to the
   same limits (tested: every commanded step at most the limit times
   dt, every second difference at most the datasheet bound times dt^2).
5. Logging. One `carry_trapezoid:` line per move made while holding
   (waypoints, segments, rests, schedule and settle steps, today's
   lower bound, the peak commanded acceleration over the bound) through
   the run's logger; the eval's counted lines untouched.
6. Rules. Executor side (the streaming of a planned trajectory), not
   the plan; pipeline-wide (every held body, every scene); no truth
   read; no bridge-only value (the datasheet limits). Narration kept.
7. Tests (14): the off path counted call by call, the on path's calls
   and log line, the bounds on five path shapes, the bend commanded once
   at rest, main's single call site.
8. The real-pick check the review required was run, with the result the
   review's rule asked about: at the flip (hand yaw 180) the trapezoid
   holds the same 62 of 64 configurations as today's stream (zero
   discordant, McNemar p 1), so it adds nothing to the flip's hold in
   this probe; alone (hand yaw 0) it harms, 21 against 32 of 56
   (p 0.019), 1 against 10 of 14 at 3 deg (p 0.004), as the placed-die
   probe predicted. What it changes at the flip: the minimum summed pad
   force over the carry (median 0.04 N today, 2.02 N with it, the
   zero-force junction steps gone) and the steps from lift to home
   (median 406 against 382).
9. Decisions on the open questions. (1) The handover from the lift (the
   arm lagging its last command, about 51 m/s^2 for two steps) stays:
   the dispatcher cannot read the motor target, and the probe shows no
   loss from it; a settle after the lift would change every pick, base
   included, so it is not this fix's. (3) No refusal without
   grasp_wrist_home: the arm specs pair them, and a refusal would block
   the probe cells that measure the fix alone. (4) The rest cost on bent
   transits with cargo is measured by the cluster arm's wall time, not
   here. (5) The per-carry minimum pad force belongs to carry_hold_check's
   line or the eval's recorder, not to this fix.
10. The arm. The real-pick result is evidence against a loss gain on top
    of grasp_wrist_home; the margin gain (no zero-force step) and the
    time change are real and measurable. Whether job C keeps the arm
    pose_radius_keep+grasp_wrist_home+carry_trapezoid is decided at
    phase 7 with grasp_wrist_home's report in hand (STATE.md, "Arm
    plan"). Never alone, in every case.

## For the merge

- test_full_pipeline.py: the move action's block is replaced by one
  call; carry_hold_check also edits the move action (its carry check
  after the move), so that merge may conflict textually around the
  call site; keep this branch's call and carry_hold_check's check after
  it.
- The module-level `import robot_utils` and `import slip_fixes` after
  the streams import are harmless beside main's local ones.
