# BF#59 review: loss_dynamics

Reviewer: adversarial review of proposals/loss_dynamics.md, written
2026-10-31 on tampura-bridge (HEAD 0c6b6e8 = d021dad plus the campaign's
documents; no code differs). Line numbers below are at HEAD; the proposal
quotes test_full_pipeline.py about 20 lines early (the slip_fixes
plumbing landed between 92d1e06 and d021dad): the move branch is 1815 to
1980, `_loop_done` 1457 to 1467, the disposal 1660 to 1704, the
EmptyHandError path 2281 to 2324, the pick's commit refusal 2116 to 2125.
execution.py (post-lift re-verify 1325 to 1344, `refresh_object_aabbs`
2033, its `record_detection` call 2139), pose_belief.py
(`record_detection` 282 to 299) and robot_utils.py (`move_robot_smooth`
877 to 999) match the proposal.

Everything below was read or computed from recordings that exist; no
episode or probe was run. The reviewer's scripts read the campaign's
carry.jsonl, eye.jsonl, console_debug.log and probe .json files and
printed to the console (section 4). Truth values quoted from eye.jsonl
and the recorder are print-only diagnostics read offline.

## 0. Verdicts

| fix | mechanism supported | rules | detectable | own-scene risk | effort h | verdict |
|---|---|---|---|---|---|---|
| carry_hold_check | half: the model never sees a carry loss (code, yes); the recovery premise fails (3 of 3 recorded dice end 0.08 to 0.23 m from the robot base, outside W, 0 px in the eye) | passes, if the shared helper keeps the post-lift check's contact-only rule | not on success at 60 episodes; its fire log is the test | low | 2.5 | implement, low priority, no solo arm |
| carry_grip_watch | no: at scale the 0.05 mm line catches 8 of 17 losses and flags 9 of 96 holds (hold_physics A_base, 113 grips) | rule 1 problem: the set-down needs a goal the mission planner would not choose | would need far more triggers than 60 carries give | high: flags 14 to 16 of 54 to 55 held cup carries and 21 to 27 of 24 to 31 held cube carries in the same probe | 4 to 6 | drop |
| carry_accel_limit | the kicks are real (largest per carry 67 to 98 m/s^2, at every junction, 5 of 5 episodes); as a loss cause alone contradicted by carry_motion's probe | passes | only with grasp_wrist_home or edge_pinch | low (bent paths slower) | 4 | merge with carry_trapezoid, carry_motion's implementation |
| pose_radius_keep | yes: code, 2 laptop loops, 18 of 192 BF#53 caps all in the observe and refuse alternation | rule 3 fine; the belief rule as written is unsound (a 0.39 mm radius around a centre measured 1.66 mm off) | caps 6/60 against 0/60 (Fisher p 0.027); refusals per episode | low with the honest rule below | 2.5 | implement, with the rule changed |
| loss predictor (metric) | 3 of 3 losses against 0 of 3 holds in the episodes; 8 of 17 against 9 of 96 in the 113-grip probe | senses only | a per-carry log line | none | 1 | implement as a log line, never as a trigger |

## 1. Per fix

### carry_hold_check

1. Mechanism. Measured by code reading and correct: after the die pick
   nothing reads the pads during or after a move; `_loop_done` (1457 to
   1467) ends a holding goal on the dispatcher's own `held_body_id` and
   the at-home test, and `_verify_holding` (242) is the first to look.
   The evidence file agrees: 31 loss episodes in
   evidence/tc_4912db9_loss_context.txt, one "firm grip on dice" each
   (reviewer's count, 31 of 31).
   The fix's value rests on a second claim that does not hold: "the die
   lies on the table in plain view (1.3)" and "if the die rests reachable
   on the table (it did in both measured losses)". The recordings say
   otherwise. At the end of each lost recording the die is still moving
   (|v| 0.18, 0.17, 0.39 m/s; angular speed 10 to 30 rad/s; s1_r2,
   s1_r3, s6_r1 carry.jsonl last row), so "z 0.014 m at the end" is a
   die in mid roll, not a rest. The eye's final record of each run
   (eye.jsonl, tag "final (FAILED: physics_mismatch)", print-only truth)
   puts the die at (0.083, 0.007), (0.226, -0.029) and (0.099, 0.039) m,
   0.08 to 0.23 m from the robot base, all outside the workspace window
   W (x 0.35 to 0.74, task_spec.py 81) and all with visible_px 0. That
   is geometry, not chance: the three losses happen at wp 7 to 9, near
   home, and the die falls about 0.5 m straight down from the home hand
   (ee at (0.178, 0.014, 0.528)) into the region below the fixed eye
   (EYE_POSITION (0.179, 0.049, 0.588), looking 51.5 deg below the
   horizon with a 49.1 deg vertical field, so its image starts about
   0.15 m in front of itself). So in 3 of 3 measured losses the check
   would fire, `refresh_object_aabbs(check_lost=True)` would find the
   die's believed region empty and retire it as lost, and the episode
   would end as target_lost (after re-searching any shadows still
   unknown) instead of physics_mismatch. The proposal's "about 80 % of
   the 36 lost episodes into successes" has no measured support; the
   measured rate is 0 of 3. Losses early in the swing (carry_motion's
   loss mode A, first 6 to 8 steps of pair 1) would land inside W and
   could be re-picked; how many eval losses are early is unmeasured.
2. Rules. Rule 1: an executor primitive checking its own postcondition,
   the same kind as the post-lift re-verify (execution.py 1325) and the
   place's EmptyHandError; the dispatch ends with a labelled status
   (`empty_hand` is in G3_STATUSES, tools/bridge_gates.py 137) and the
   planner replans; no plan is edited. Model side. Rule 2: pipeline-wide
   (every move made while holding). Rule 3: `getContactPoints(bodyA =
   robot, bodyB = held)` is tactile and passes G8(b) (gate_hooks.py 283);
   `env.update_object_positions()` is a counted no-op on the bridge
   (env_adapter.py 156, G16 info, no violation). Two defects: (a) the
   post-lift re-verify checks contact presence only (1331 to 1334), not
   the 0.5 N floor, so making it "the first caller, unchanged in
   behaviour" of a helper that also applies the 0.5 N floor is a
   contradiction; the helper needs the floor as an argument, or the
   post-lift check changes behaviour with the switch off; (b) the
   post-lift print reads `getBasePositionAndOrientation(obj_id)` (1337,
   allowlisted as print-only); a copy in the new helper needs its own
   reviewed allowlist line or must be left out. Rule 4: the switch is
   simple. Rule 5, 6, 7: the proposal's section 4 matches the probe
   folder (sizes within rounding: s1_r1 1.4 MB, s14_base_r1 4.1 MB).
3. Testability. The fix does not move loss per carry; it moves the
   success count and the exit reason. Base success in BF#53 is about
   72 % (174 of 192 reached the die, 79 % of those held). At 60 against
   60 episodes a true success of 85 % is detected with power 0.34, 90 %
   with 0.66 (reviewer's exact Fisher enumeration). With 0 of 3 measured
   conversions the arm would likely show nothing. The informative test
   is the fire log: per fire, the step, the pad contacts and force, the
   die's next detection (where, how many pixels), whether a re-pick was
   planned and whether it held. Falsifier: fewer than half of the fires
   end in a held re-pick (the proposal's (b)); the reviewer expects this
   to fire. Note also that "loss per carry" changes its denominator under
   this switch (a re-pick is a second carry); slip_eval.py must count
   carries per pick, not per episode.
4. Risk. A false loss at rest would clear `held_body_id` while the body
   is still pinched; the next pick then opens the gripper on it. The
   check runs after the settle and the home hold, where the resting force
   is 1.6 to 7.6 N (BF#48) and the probe's nf_home median 2.7 N, so the
   risk is small, but the criterion should be contact presence on both
   pads (the eval's losses were "links none" in 35 of 36), with the force
   floor only as a logged second number. The replan after a lost die
   re-searches the cups still unmoved, each exposed to the cup loop, so
   without pose_radius_keep it can lengthen a failing episode; it does
   not touch the 18 capped episodes (none had picked the die). TAMPURA's
   executor has nothing to do on a loss: `enforce_grasp` resets the die
   to the hand at every waypoint and the arm moves by resetJointState
   (PAPER_AUDIT.txt 7370 to 7431), so their die cannot leave. For the
   comparison this fix only relabels our failures (target_lost or a
   recovery that costs our wall); it narrows nothing in the gap, and the
   paper must report the per-carry loss rate, which this fix leaves
   untouched, beside any success count it changes.
5. Effort. 2.5 h (the helper with the floor as an argument, the call in
   the move branch after the at-home test and before `_integrity_after`
   at 1978, the EmptyHandError handling reused, a unit test with a fake
   contact list).
6. Verdict: implement, low priority, no solo arm. It is a correct and
   cheap postcondition check that makes our endings honest pipeline-wide,
   but it is not a slip fix, and the recordings say its recovery will
   rarely work for the late losses this campaign sees.

### carry_grip_watch

1. Mechanism. The episodes' numbers check out (reviewer's re-run of
   predictor.py logic: widening +0.225, +0.157, +0.198 mm in the losses,
   +0.002, +0.013 mm in two holds, +0.002 in s0_r1; crossing 0.05 mm 139,
   98 and 103 steps before the first pad break). That is 6 carries on 3
   scenes. The hold_physics probe has the same per-trial quantity
   (`widen_max_mm`, the mean finger joint over the carry minus its value
   after the close, until the loss) for 113 die grips under the same
   0.5 mm position hold and the same 9-pair line carry (out/A_base.json).
   There, at 0.05 mm: 8 of 17 losses caught, 9 of 96 holds flagged; at
   0.02 mm: 11 of 17 and 63 of 96; at 0.1 mm: 6 of 17 and 1 of 96. The
   probe's 8 of 20 low-force slips (hold_physics 1.1 item 2) do not widen
   at all, and a sharp box die (Cbox_base) is caught 1 of 44 times. The
   watch's premise ("the pads' wedging is visible to proprioception")
   holds for the wedge mode only, about half of the losses.
   Confound: the probe's reference is the finger position after the
   close, the proposal's the post-lift readback; under the position hold
   both are the same motor target, so the comparison stands for base.
2. Rules. Rule 3: the reads are the finger joint readback and
   `getContactPoints` on the pads, both senses; `move_robot_smooth`'s
   `on_step` hook (robot_utils.py 914) is read-only and fits. Rule 1 is
   the problem. The existing disposal (1660 to 1704) runs only when the
   MISSION has no plan while holding. After the watch aborts the move,
   the next loop iteration plans the mission with the die held, and the
   mission plan is "move home": the planner would re-plan the very carry
   the watch stopped. To get the set-down, the dispatcher must call
   `planner.plan(goal=('handempty',))` on its own initiative: a goal
   substitution decided between the planner and the executor, on a fact
   (a widening grip) the planner's model does not contain. It is not a
   plan edit, but it is not a planner's choice either. The model-side
   form is a primitive that fails with a return (the move ends early
   with a labelled status, like M10's pick returns) and a belief fact
   the domain reads (a held body whose grip is degraded does not satisfy
   the goal's holding, so the planner itself plans place and re-pick);
   that is a domain change, G10 checks the domain text, and a new
   dispatch status must enter G3_STATUSES (tools/bridge_gates.py 137).
   Where it would set the die down: at a free spot the disposal plan
   chooses, which is a second carry of a wedged die (the move to the spot
   and the descent), from mid-swing at 0.4 to 0.5 m height. How the
   belief learns the pose: the place's release refresh, then a re-pick
   at M9's fitted yaw, with the same wrist unwind and the same 21 %.
3. Testability. Each trigger costs a place, a pick and a carry (10 to
   20 s). With 13 losses expected in 60 base carries and half of them in
   the wedge mode, the arm would see 6 or 7 true triggers and, at 9 % of
   47 holds, 4 or 5 false ones: too few to measure (b) "the die leaves
   during the settle" or (c) "below carry_hold_check alone".
4. Risk. The settle the proposal uses (`move_robot_smooth(..., settle =
   True)` at the current readback) stops an arm moving at 2.5 rad/s
   within a few steps: a larger deceleration than the 0.9 v junction
   drops that released 2 of the 3 dice. Our bodies in the same probe
   (their world, our hold, the line carry): held cup carries flagged 14
   of 54 (cup a) and 16 of 55 (cup c), held 40 mm cube carries 21 of 24
   (0.5 kg) and 27 of 31 (0.1 kg) at 0.05 mm (E_*_base.json). Each flag
   is a set-down that base did not need. Under hold_physics'
   force_hold the signal means something else: the fingers follow the
   body under a constant force, so a widening is the body turned to a
   wider support, held. In the two geared 10 N episodes the post-lift
   reference gives +0.001 mm (s1_gear_f10_i200) and +0.397 mm at wp 6
   (s6_gear_f10_i200, held); without the gear (s1_f20_i200) the sloshing
   gives +4.49 mm from wp 1. With that hold the probe lost 0 of 113 dice,
   so the watch has nothing left to catch and only its false alarms
   remain.
5. Effort. 4 h as proposed; 6 h or more in the model-side form (the
   domain predicate, the G3 status, the G10 domain text).
6. Verdict: drop. The predictor does not separate at scale (8 of 17
   against 9 of 96), the set-down is not a choice the planner can make
   with today's domain, the stop is itself a kick, and the two mechanism
   fixes (grasp_wrist_home with carry_trapezoid, force_hold with its
   partners) remove what it watches for.

### carry_accel_limit

1. Mechanism. Measured: every waypoint junction of every recorded carry
   gives the hand one to two steps of high acceleration, the largest per
   carry 67 to 98 m/s^2 (s6_r1 67, s1_r1 and s1_r2 87, s1_r3 89, s0_r1 98;
   reviewer's listing of s1_r1: 74 to 87 m/s^2 at the first step of pairs
   2 to 9, 44 to 66 m/s^2 at the second; inside the pairs median 1.0 to
   2.0 m/s^2), and in s1_r1 the pads read 0.0 and 0.0 N at step 479 and
   0.0 and 0.03 N at step 604, right after two of them. Two of the three releases follow a junction; s6_r1's does
   not. The proposal itself measures that the junctions carry little of
   the turning (14.3, 10.1, 6.2 % of the turn in 7 to 9 % of the steps in
   s1_r2, s1_r3, s6_r1; the proposal's "10, 14 and 6 %" swaps the first
   two). What is inferred and contradicted: that removing the trigger
   lowers the loss. carry_motion's probe (92 to 96 carries per cell) shows
   the trapezoid alone under today's grasp worse than today's stream at 3
   and 10 deg off the face (70 % and 48 % held against 92 % and 59 %),
   equal at 0 deg (87 against 93 %), better only at the edge pinch (100
   against 91 %). The kick is the second cause once the wrist spin is
   gone, not a cause on its own. The proposal's time estimate ("a carry
   of 1.4 s grows by about 0.3 to 0.6 s") is contradicted by carry_motion's
   two episodes: 336 and 356 steps against about 454 for base, because
   today's per-pair restart builds a lag and a 76 to 79 step settle.
   One correction to 1.2: the carry home is not "a re-solved RRT path";
   the console says "direct path clear, linear trajectory" and the 9 pairs
   are equal (`streams._linear_trajectory`), so every pair is collinear.
2. Rules. Rule 1: an executor primitive, the plan's waypoints executed.
   Rule 2: datasheet-matched like F14, pipeline-wide. Rule 3: no reads of
   the world beyond the joint readback. The motor writes are not G1 names
   (tools/bridge_gates.py 82 to 91), and the runtime G3 hook only requires
   them inside a dispatched action; no allowlist line is needed for the
   motor commands themselves.
3. Which implementation is the one switch. Neither proposal puts the
   bound inside `move_robot_smooth`'s per-pair streaming, and it cannot
   live there: each call restarts from the lagging readback (930) with
   no memory of the previous command, which is the cause of the kick.
   Both are one schedule per move. They differ at corners: loss_dynamics
   keeps full speed through any direction change under 30 deg; carry_motion
   merges collinear pairs (cosine > 0.9999) and rests at every other
   direction change. A polyline corner taken at speed is a step change of
   the velocity vector (2 v sin(theta/2), half the speed at 30 deg) in one
   step, the junction kick again, unless the corner is blended, which
   leaves the certified polyline. Only carry_motion's rule keeps both the
   certified path and the bound. Both keep the F14 velocity limits (the
   trapezoid's cruise speed is the per-joint limit scaled along the path,
   which subsumes the step stretch) and the settle at the last waypoint
   and the home hold. Cost, carry_motion's numbers: straight carries 334
   to 372 steps against 360 to 406 under today's stream (probe medians),
   336 and 356 against about 454 in the episodes; one bend costs about 70
   steps (via path 405 against 334). At about 1 ms a step that is a few
   tenths of a second per move against a 31 s eval wall median: the time
   is not the issue. carry_motion also turns `move_robot_smooth`'s single
   hop into a one-segment trapezoid (pick and place descents, the lift);
   that changes every pick's descent and lift and should be measured
   (grip verification and post-lift failure rates per pick) or kept off
   in the first arm. A residual to check: both carry_motion trapezoid
   episodes still show 51.3 and 51.8 m/s^2 at the first two steps of the
   carry (s0_fliptrap and s1_fliptrap carry.jsonl, steps 352 to 353), the
   handover from the lift's settle; the schedule should start from the
   last commanded target, and carry_motion's falsifier (a) (joint
   acceleration over 1.2 times the datasheet) would catch it.
4. Risk. Our scenes' transits are RRT paths with bends (3 smoothed
   waypoints in the seed 14 log), so they slow down; nothing changes the
   grasp. The replan loop is untouched.
5. Effort. 4 h, once, in carry_motion's form (`move_robot_trajectory`, the
   dispatcher's single call, the gate tests, a two-segment unit test).
6. Verdict: merge with carry_trapezoid (one switch, carry_motion's
   implementation with rest at direction changes). Alone it removes a
   trigger and costs dice under today's wrist spin, so its arm must be
   grasp_wrist_home + carry_trapezoid (or edge_pinch + carry_trapezoid),
   never the trapezoid alone as a candidate.

### pose_radius_keep

1. Mechanism. Supported three ways. Code: `refresh_object_aabbs` re-poses
   every visible OBJECT boxel to the eye's centre after each move and
   calls `record_detection` (2139), which overwrites the radius with the
   eye's formula value (295), and the pick's commit check refuses
   (2116 to 2125). Laptop: s14_base_r1 and s1_r3 alternate "observe
   d_cups_ud, pose_radius 0.39 mm" and "pose_radius 5.49 mm is outside its
   commit margin" (s1_r3: 42 observes, 41 refusals, so 82 of its 90 plans
   in the loop; the proposal's "82 refusals in 90 plans" in 1.6 counts
   plans, not refusals). Cluster: the 18 of
   192 BF#53 episodes that hit the 600 s cap all show observes about
   equal to picks about equal to half the plans (for example seed 17
   base: 185 plans, 92 picks, 91 observes, 3 places); none picked the
   die. Two more successes ran 560 and 563 s the same way. The brief's
   "picked the die 10 to 41 times" is wrong, as the proposal says.
   What the radius hides: the eye's 5.49 mm for a 51 mm cup is mostly its
   yaw term (9.475 deg times the 25.5 mm half side, 4.2 mm), not its
   centre error. The reviewer read the believed centre against the
   cup's print-only AABB centre in s14_base_r1 (eye.jsonl #150 to #157):
   after the wrist observe 0.22 mm off (radius 0.39 mm), after the eye
   refresh 1.66 mm off (radius 5.49 mm); the two estimates differ by
   1.56 mm. In s1_r3 (#150 to #157) the same pair reads 2.75 mm (after a
   wrist observe from look 3) and 1.60 mm (eye). So the two sensors do
   not conflict; the radius bookkeeping replaces a finer estimate by a
   coarser one. One sample (s1_r3) also shows a wrist radius of 0.39 mm
   around a centre 2.75 mm off, a calibration question for M8 (section
   3), not for this fix.
2. Rules. Rules 1 to 3: the belief only, no reads. The rule itself, as
   written, is not sound pipeline-wide. `record_detection` sets the radius
   only; the caller then moves the box to the eye's centre (2146 to 2147)
   and `_fuse` sets yaw = the latest camera's (277). So `min(old, new)`
   keeps the wrist's 0.39 mm around the eye's centre and the eye's
   snapped yaw: the stated radius would be 4 times smaller than the
   measured error (0.39 against 1.66 mm). The bounded-error rule the
   proposal names gives, for the new centre, truth inside D(c_old, r_old)
   intersected with D(c_new, r_new), whose covering radius around c_new is
   at most min(r_new, r_old + |c_new - c_old|). For the measured case:
   min(5.49, 0.39 + 1.56) = 1.95 mm, honest against the 1.66 mm error,
   and below the cup's commit margin (refused at 5.49, committed at 0.39;
   by `believed_margin` with the 70 mm AABB span and the 40 mm half
   opening it is about 3 mm, the reviewer's estimate, not printed by the
   run). The alternative, keeping c_old and the
   wrist's yaw when the new detection is consistent and coarser, needs a
   change in `refresh_object_aabbs` too and lets a nudge of up to
   r_old + r_new (5.9 mm here, below the 15 mm INTEGRITY_DISTURB_M,
   execution.py 1864) pass with the old centre; the shift-grown radius
   tracks a nudge with the eye's centre and grows with it, so it is the
   safer of the two. A detection outside r_old + r_new keeps today's
   behaviour; a moved cup (mark_pose_commanded, mark_pose_unknown, M10's
   touched bodies) is unchanged.
3. Testability. Effect on success is small per arm: the caps are about 9
   % of episodes (18 of 192), so at 60 episodes about 5 or 6 caps against
   0; 6 of 60 against 0 of 60 is significant at p 0.027 (Fisher, two
   sided), 5 of 60 is not (0.057). The direct counts are better: the
   number of "outside its commit margin" refusals per episode (base: 0 to
   82 on the laptop; under the switch it must be 0 or 1 after an
   observe), plans per episode and the wall's upper quartile. Falsifier:
   the alternation recurs, or the picks that commit on a kept radius
   fail the grip check more often than base's picks of the same bodies
   (log the radius and both centres at each commit).
4. Risk. The pick's commit check commits after one observe; the
   pre-grasp aperture shrinks with the radius (`pinch_half + pose_radius
   + 8 mm`, execution.py 1132), which for the cups is capped at the
   40 mm opening anyway and for the die changes by under 1 mm. G15 is not
   affected: it only checks that every sense step has its classified
   outcome row (tools/bridge_gates.py 877 to 885), and the radius does not
   enter the classification. Our scenes: the same eye radius applies
   (YAW_NOISE['eye'] is one constant), so the same refusal loop can occur
   there with M8 on; the fix removes observes, never adds them.
   Cross-proposal: `_fuse` replaces the wrist's 0.2 deg yaw with the eye's
   snapped yaw at the same refresh, so grasp_geometry's
   face_needs_wrist_yaw (pose_known only when the yaw came from the
   wrist) would loop exactly like the cup unless this fix also keeps the
   finer camera's yaw when the coarser one is consistent within its
   noise; and carry_motion's seed-6 episode shows grasp_wrist_home
   feeding this loop.
5. Effort. 2.5 h (the rule in `record_detection` with the old centre and
   the camera of the stored yaw, the yaw keep, tests in
   tests/test_pose_writers.py: wrist then a consistent eye keeps a
   shift-grown radius below the eye's; an inconsistent eye takes the
   eye's; the yaw survives).
6. Verdict: implement, with the radius rule changed to min(r_new, r_old +
   centre shift) and the finer yaw kept. It removes the eval's whole slow
   tail at no physics cost and is a precondition for clean arms of
   grasp_wrist_home and face_needs_wrist_yaw.

### loss predictor (metric, not a switch)

1. Mechanism. As in carry_grip_watch point 1: 3 of 3 against 0 of 3 in
   the episodes, 8 of 17 against 9 of 96 in the 113-grip probe at base.
   The 6-carry separation is a small-sample artefact; the line marks the
   wedge mode, not the low-force slip.
2. Rules. Senses only; a print or ledger line needs no allowlist.
3. Testability. Logged on every carry of every arm it answers its own
   question cheaply. It should log, per carry: width0 and widen_max with
   the step and waypoint, nf_min, the steps with one contact point, the
   pads at the end, and the joint 7 travel of the move (carry_motion's
   variable); under force_hold the widening is not a loss signal and the
   line must say which hold was active.
4. Risk. None.
5. Effort. 1 h.
6. Verdict: implement as a log line; drop "predicts a loss" as a claim.

### The non-determinism finding (seed 1: held, lost, lost)

Evidence checked. The planner's solve is pddlstream's `adaptive`
algorithm with `search_sample_ratio` 0.25 (pddlstream_planner.py 50, 1309
to 1325), which allots sampling time as a fraction of the measured search
time: the number of stream calls per iteration, and so which samples
bind, depends on the wall clock. The runs show it at the plan level: the
plan-2 stream plans of s1_r1 and s1_r2 bind the same actions with the
compute-kin results in a different order; s1_r3 takes another skeleton at
plan 3 (b_cups_ud before e_cups_ud); the last cup goes to free_016 in r1
and free_017 in r2; plan 1 took 10.7, 7.0 and 7.1 s, and r1's start-up
took 64.1 s against 18.4 s (the laptop was loaded). Seed 0 diverges too:
s0_r1 and the slip_check episode of 12:47 have the same three plans but
pick the die at 5.00 against 3.28 N. Nothing in the recordings shows the
physics itself varying: PyBullet repeats bit for bit for an identical
command sequence (not tested here), and the carry acts as a chaotic
amplifier of micrometre differences (5 um and 0.06 deg before the pick,
1.63 against 2.28 N at the close, held against lost). So the source is
the planner's wall-clock dependence; "under load" is one cause of timing
variation, not shown to be the only one (an idle-machine repeat was not
run). The proposal's own phrase "the outcome of a carry close to an
independent draw" is the right model.

What it implies for the replication design:
- Three repetitions of all 20 seeds is the right shape (STATE.md phase 7
  already moved from the entropy subset to all seeds); per-seed
  differences between arms mean nothing, only rates do.
- Pairing by seed buys little when the within-seed outcome is a near
  coin flip; the comparison is two binomials. At 60 against 60 carries
  with base at 13 of 60, a fix must show 4 or fewer losses (6.7 %) to be
  significant at 95 % (two-sided Fisher); a true 5 % is detected with
  power 0.68, a true 10 % with 0.29. Pooling base over two or more jobs
  (120 to 240 base carries) moves the bar only to 5 of 60 (8.3 %). Only
  fixes that claim near-zero loss (hold_physics' 0 of 113, carry_motion's
  383 of 384) can be confirmed by this eval; edge_pinch's claimed 15 %
  cannot.
- Any fix that changes step time or step counts (200 solver iterations
  double the step time; the trapezoid changes every move's length)
  changes the planner's timing and so the plans: its arm is a
  re-randomisation as well as a fix, which is fine for rates.
- The 600 s cap is wall clock too, so cap counts depend on the node's
  load; base in every job is the right control; keep the node pinned and
  log the node's load.
- For debugging a single carry under two fixes, a replay of the recorded
  plan (the waypoints and the pick's grasp) is the only deterministic
  comparison; the run should log them.

## 2. Cross-proposal conflicts and combinations

Mechanisms and their switches:
- The die turning out of the pinch during the swing has three proposed
  root causes with probe support, not exclusive: the wrist unwind of 211
  to 242 deg (carry_motion's grasp_wrist_home), the light position hold
  and the unconverged solver (hold_physics' finger_gear, solver_iters,
  force_hold, and pad_rolling as the fallback), and the pinch geometry
  against a 9.5 deg yaw belief (grasp_geometry's edge_pinch,
  face_needs_wrist_yaw). The junction kick is the trigger
  (carry_accel_limit = carry_trapezoid, one switch).
- The slow tail is a separate mechanism with one switch:
  pose_radius_keep.
- Detection of a loss: carry_hold_check (keep, cheap); carry_grip_watch
  (drop).

Dependencies:
- grasp_wrist_home and carry_trapezoid only work together (carry_motion's
  table: each alone is worse than base at some delta); one arm with both.
- grasp_wrist_home turns cup grasps too and fed the cup loop in seed 6:
  its arm needs pose_radius_keep on.
- face_needs_wrist_yaw needs the wrist's yaw to survive the eye refresh,
  which only pose_radius_keep in the form above provides.
- force_hold needs finger_gear and solver_iters (hold_physics 2.3).
- edge_pinch needs carry_trapezoid per carry_motion (edge pinch: pipe 82
  to 91 %, trapezoid 100 %).

Interference:
- force_hold changes the finger-width signal: widening becomes a held
  body turned to a wider support (up to 0.7 mm without a loss); another
  reason carry_grip_watch goes, and the predictor's log line must name
  the hold.
- edge_pinch raises the measured half-width to 12.3 to 12.6 mm, so
  force_hold's target (4 mm inside the measured width) and the predictor's
  width0 change with it; no conflict, but the two must not be tuned on
  each other's arm.
- A hold that keeps the die (force_hold's 0 of 113, flip plus trapezoid's
  383 of 384) leaves carry_hold_check almost nothing to catch on the die;
  it stays useful on our scenes and as an honest ending.
- grasp_wrist_home and hold_physics both remove the turning; in a
  combined arm their effects cannot be separated, so each needs its own
  arm first.

Order of implementation and of the eval's arms:
1. pose_radius_keep first, then a base arm with it on (call it base+r)
   beside the plain base, so every slip arm runs without the cup loop
   and the cap count of base against base+r measures the fix itself.
2. On base+r: grasp_wrist_home + carry_trapezoid (one arm); finger_gear +
   solver_iters + force_hold (one arm, hold_physics' declaration);
   edge_pinch + carry_trapezoid (one arm); pad_rolling alone if
   force_hold is rejected.
3. carry_hold_check and the predictor line in every arm from step 2 on
   (they change no physics and their logs explain each loss).
4. The combined set (the best mechanism arm or two, with pose_radius_keep
   and carry_hold_check) last, with TAMPURA beside it.

## 3. Missed, and what to check first

Missed by the proposal:
- Where a lost die ends: outside W and out of the eye's image in 3 of 3
  recordings, which removes carry_hold_check's claimed benefit (1, point
  1).
- The turning's driver. turning.py correlates the die's rotation rate
  with the hand's angular ACCELERATION and finds little (+0.22, +0.13,
  -0.02 in the losses), then concludes "the squeeze itself turns the
  die". The recorded rotation axis is mostly the hand's approach axis
  ((0.3, 0.2, 0.9) in s1_r2), the axis joint 7 spins about at a constant
  rate inside every pair; the angular VELOCITY and the wrist travel were
  not tested, and carry_motion's batches 2 to 5 show the sign and extent
  of that spin decide.
- The post-lift re-verify has no force floor (1331 to 1334); the shared
  helper must not add one silently.
- The radius rule leaves the centre and the yaw to the coarser camera
  (1, pose_radius_keep point 2).
- The carry home is the linear trajectory, not RRT; carry_accel_limit's
  30 deg corner rule never acts on it.

What I would check first (one hour):
1. 15 min: in the cluster's 36 BF#53 loss episodes, the die's position in
   the eye's "final" record (print-only, eye.jsonl) and its visible_px:
   how many land inside W and in view. That is carry_hold_check's ceiling
   and decides whether it deserves any arm.
2. 20 min: across every observe and refresh in the five loss_dynamics runs
   and carry_motion's s6 episode, the believed centre against the
   print-only AABB centre per camera and look configuration, against the
   radius each detection set: whether r_old + shift covers the error
   everywhere (it does in the two cases read) and whether the wrist's
   0.39 mm is overconfident at some looks (s1_r3: 2.75 mm off).
3. 25 min: one of carry_motion's batch-5 cells rerun with the
   trapezoid starting from the last commanded target instead of the
   readback, to see the 51 m/s^2 start kick go (physics only, no lock).

## 4. Data generated and deleted

Nothing was written under the campaign folder except this file; no
reviews/loss_dynamics_probe/ folder was needed (no probe was re-run). The
reviewer's read-only scripts and one copy lived in the session
scratchpad (outside the repository) and are deleted by path at the end of
the review:
C:\Users\HaniAlassiriAlhabbou\AppData\Local\Temp\claude\C--Users-HaniAlassiriAlhabbou-git-Semantic-Boxels\9a4a4708-cb37-489d-9ce6-e4a83e48a8db\scratchpad\
ld_review.py, ld_spikes.py, ld_end.py, ld_pred_hp.py, ld_power.py,
ld_power2.py, ld_eye.py, ld_dieend.py, ld_evid.py, ld_bf53.py and
tfp_head.py (the HEAD copy of test_full_pipeline.py read for line
numbers). Deleted by path after this file was complete: ld_bf53.py 878 B,
ld_dieend.py 432 B, ld_end.py 692 B, ld_evid.py 987 B, ld_eye.py 925 B,
ld_power.py 2,009 B, ld_power2.py 507 B, ld_pred_hp.py 1,171 B,
ld_review.py 3,057 B, ld_spikes.py 1,209 B, tfp_head.py 171,265 B: 11
files, 183,132 B. The scratchpad's other files belong to the
orchestrating session and were not touched. All scripts ran with
PYTHONDONTWRITEBYTECODE=1, so no bytecode was written into the probe
folders (probes/loss_dynamics/__pycache__/analyse.cpython-311.pyc, 10,714
B, predates this review and is the proposal author's).
