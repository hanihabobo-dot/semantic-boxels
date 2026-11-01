# BF#59 die-slip campaign: live state (hand-over for any session)

Updated 2026-10-31 16:45 by the orchestrating session. Read BRIEF.md
first (the problem, the rules, the design), then this file (where the
campaign stands), then the proposals. Hani compacts his sessions with a
plain `/compact`, so everything a continuation needs is HERE, not in chat.

## Phases (Hani's request, 2026-10-31)

1. DONE recon and brief (BRIEF.md, evidence/).
2. DONE scaffolding, committed on tampura-bridge (db3f374, 95fe3dc,
   9616b6f, 0e4a5ea; none pushed, no push without Hani's word):
   `slip_fixes.py` (register/configure/on/spec; every fix behind
   `slip_fixes.on('<name>')`, default off, registered at its module's
   import), `--slip-fixes a,b` in run_logger / main() / the bridge driver,
   `tests/test_slip_fixes.py`, `tools/slip_eval.py` (arms = fix sets,
   seeds outer, --reps and --rep-seeds, carries and losses per episode,
   summary with loss per carry, medians, pairwise vs base, replication
   disagreement), `tools/cluster/slip_eval.sbatch` (shared node, 8 CPUs,
   24 GB, base arm in every job, pin with -w), `tools/cluster/slip_t.sbatch`
   and `_bridge_campaign.py --drop-t-history` (TAMPURA on the same seeds,
   their pickles deleted after reading), `tools/slip_worktree.ps1 -Name x`
   (worktree `C:\Users\HaniAlassiriAlhabbou\git\sb-slip-x` on branch
   `slip/x`, autocrlf off), `tools/slip_check.sh <wsl path> [seed] [fixes]`
   run from the MAIN checkout (tests, bridge tests, static gates, one
   episode under `flock /root/sb_pipeline.lock`), `.gitattributes` (LF for
   .sh/.sbatch). Validated: main checkout and a throwaway worktree both
   pass (53 tests, 89 bridge tests, gates PASS, seed 0 success).
3. DONE proposals (16:50): grasp_geometry, loss_dynamics, carry_motion
   (15:40), hold_physics (16:50, 44 kB: sections 1 to 4 on top, the work
   log of 23 items as the appendix; three laptop episodes with a fix on
   held the die at home: seed 1 at 20 N without the gear, seeds 6 and 1
   with the full combination). Their probes and recordings are under
   probes/<angle>/ (about 155 MB, ledgered; garbage after the review
   except scripts, work logs, the .txt summaries, carry.jsonl and
   stdout.txt).
4. DONE review (16:42 to 17:30; the verdicts under "Review results"
   below, the outcome under "Candidate list"): the shared brief is
   reviews/REVIEW_BRIEF.md (what to read, six points per fix: mechanism
   and evidence, the rules of BRIEF.md section 5 one by one, testability
   and the eval's power, risk, effort, verdict implement / merge with X /
   drop; then cross-proposal conflicts and combinations, then what was
   missed; the skeleton of reviews/<angle>.md; no episode runs, no edits,
   no commits). Three Opus reviewers run, one proposal each, writing
   reviews/<angle>.md as they go: grasp_geometry (session agent id
   a4fd95191a1d0260c), loss_dynamics (a976071984851032e), carry_motion
   (acffd73e6c251ee62), hold_physics (ac67440e6b14b7732, started 16:52;
   its orchestrator questions: rule 2 for the force-limited hold and the
   200 iterations, pipeline-wide for our own world too; the switch and arm
   structure since force_hold is harmful without the other two; the
   step-time cost against the 600 s cap; the gear constraint on both
   clients; what the grip verification, the post-lift re-verify and
   _verify_holding read under the new hold; which other fixes become
   redundant). The implementation brief for phase 5 is
   reviews/IMPL_BRIEF.md (written ahead). NEXT after the four reviews: the orchestrator writes the candidate list (6 to 8
   fixes, one mechanism per switch, the dependencies and the arm plan)
   into this file.
5. IN PROGRESS implementation (from 17:40): one worktree and branch per
   fix of the candidate list below, four Opus agents at a time (the house
   cap), each: the switch, unit tests, `tools/slip_check.sh` green, a
   commit on its slip/<name> branch only (one-line subject, no trailer,
   no push), a report file reviews/impl_<name>.md; the brief is
   reviews/IMPL_BRIEF.md. Worktrees are created by the orchestrator with
   tools/slip_worktree.ps1 from the tampura-bridge commit named in the
   round's line. Round 1 launched 17:45 from 05dcaf3: worktrees
   sb-slip-solver_iters (session agent id a056657232636bbcb),
   sb-slip-force_hold (acf1fc489c989fbef), sb-slip-pose_radius_keep
   (a5bb44a50345f551a), sb-slip-grasp_wrist_home (ae1274432c2c61abb);
   reports reviews/impl_<name>.md. force_hold's check runs use the
   check-only escape SLIP_FORCE_HOLD_NO_ITERS_CHECK=1 because its
   worktree has no solver_iters switch; the campaign branch runs both
   for real. Round 2 (carry_trapezoid, carry_hold_check, pad_rolling)
   starts as slots free, worktrees from the same base.
   - carry_trapezoid launched 18:45 in sb-slip-carry_trapezoid from
     ae62b33 (code identical to 05dcaf3; session agent id
     a1d5d4304abbc1b78); its check includes the real-pick probe cells the
     review required. pad_rolling and carry_hold_check get agents as
     slots free. Implementation reviews (phase 6): small diffs are read
     by the orchestrator (reviews/implrev_<name>.md), large ones by an
     Opus reviewer when a slot is free.
   - pose_radius_keep DONE 19:05: commit e0e81e1 on slip/pose_radius_keep
     (pose_belief.py: register at import 27, record_detection 297,
     _prk_centres/_prk_prior/_prk_apply 360 to 437, _fuse returns bool;
     11 tests). The camera is already passed by every caller ('eye' or
     'wrist'), no new parameter. Deviations: the reference is the measured
     detection whose own radius set the current bound (the brief's 2.05 mm
     for one refresh; repeated refreshes do not add their shifts up),
     counted only if the rule last wrote the radius and the box is within
     0.5 mm of that write's position (stands in for pose_known, which
     record_detection cannot call); the shift is the larger of the box
     centre's and the rectangle centre's; the yaw keep needs the eye's yaw
     within 9.68 deg of the wrist's. Checks green on and off (63 + 89
     tests, gates PASS, seed 0 success; off shows the cup loop twice).
     Laptop seed 6 on: held, 4 plans, no refusal, the rule never fired
     (the cup was behind the arm at the refresh); seed 1 on: held, 12
     plans, 1 refusal, the rule fired 30 times on three cups (d_cups_ud
     kept 2.63 mm against the eye's 5.49 mm and the pick committed), the
     yaw kept 5 times. Open: the wrist's centres from different look
     configurations disagree by 2 to 3 mm while it claims 0.39 to 0.68 mm
     (M8 calibration), so some refreshes still refuse. Report
     reviews/impl_pose_radius_keep.md; 2.7 MB of checks in the worktree.
     IMPLEMENTATION REVIEW 19:20 (reviews/implrev_pose_radius_keep.md,
     the orchestrator): ACCEPTED, no change; the call order (radius
     before the box write at both callers) and est_center = the AABB
     centre make the validity test sound.
   - carry_hold_check launched 19:12 in sb-slip-carry_hold_check from
     f060429 (code identical to 05dcaf3; session agent id
     ae3c955cf7beccf40); its loss line's exact text goes into the eval
     harness when it reports. pad_rolling waited for a free slot and was
     DROPPED at 20:25 (force_hold passed its jam probe; see its bullet).
     carry_hold_check DONE 20:35: commit 85618e2 on slip/carry_hold_check
     (execution.py: register at import 61 to 72, held_pad_contacts 567
     the shared tactile helper, carry_hold_begin 597 and carry_hold_end
     606 the postcondition with the per-carry line and the loss line,
     the post-lift re-verify 1434 to 1438 now calls the helper with the
     same rule; test_full_pipeline.py: the begin hook before the
     waypoint stream 1886 to 1889, the end check and the copied
     empty-hand path 1982 to 2033 with current_config rebuilt without
     the lost cargo; 10 tests). Rule: both pads on the held body, no
     force floor; a loss opens the gripper and ends the move as
     empty_hand (the transit strike, the pose unknown, the lost-region
     refresh, a replan). LOSS LINE for the eval: "grip lost in the carry
     for dice" (added to tools/slip_eval.py as CARRY_LOSS_RE). Checks
     green on and off (63 + 89, gates PASS, seed 0 success). Six laptop
     episodes on (seed 1: the cup loop, killed at 900 s; seed 6 four
     times: held, reward 1.0, two bit-identical pairs of carries): no
     loss occurred, so the loss path ran only in the unit tests.
     IMPLEMENTATION REVIEW 20:50 (reviews/implrev_carry_hold_check.md,
     the orchestrator): ACCEPTED, no change; the loss path gets one
     injected run on the campaign branch before the snapshot
     (reviews/impl_carry_hold_check/ep_loss_inject.py: the helper reports
     no pads once when carry_hold_end asks about the die). HARNESS BUG
     found and fixed meanwhile (tools/slip_eval.py count_carries,
     tests/test_slip_eval.py, 7 tests): the pipeline's prints are in
     both console_debug.log and run_*.log, so the joined logs counted
     every lift loss and pick try twice; now each line is read in one
     file (stdout.txt for "firm grip" and the goal check,
     console_debug.log for the pipeline's prints, fallbacks run_*.log
     then stdout). Worktree data 9.6 MB (two checks, five episodes),
     ledgered.
   - force_hold IMPLEMENTED 19:25, NOT READY: commits b2cacd6, b7d08f5,
     d3a0411 on slip/force_hold (robot_utils 1135 to 1201: the block
     with FORCE_HOLD_REACH 0.004, FORCE_HOLD_BUDGET_N 10, the gear
     constants, force_hold_requires_solver_iters and the check-only
     escape; close_gripper_until_contact 1260 to 1289: the hold after the
     60-step position hold, target width - 4 mm at 10 N per finger, one
     "force_hold:" line per hold; policy.py d9_setup 81 to 101: the gear
     (JOINT_GEAR, ratio -1, erp 0.1, maxForce 50) on the executing
     client, make_execute_fn 212 to 215: the configure call byte-identical
     to solver_iters'; boxel_env._setup_scene 936 to 961: the gear on our
     physics client, rebuilt by reset(); 4 G1 allowlist lines; 9 tests).
     Checks: off green (62 + 89 tests, gates PASS, seed 0 success); on
     with the escape red by design (50 iterations: the die lost in the
     carry; one bridge test flaked under load, passed alone). Episodes at
     200 iterations through reviews/impl_force_hold/ep_iters.py (a
     wrapper standing in for solver_iters): seed 1 held (129 s), seed 6
     held (77 s), seed 0 held once (16.8 s) and FAILED once with
     pick_giveup: after the place of d_cups_ud at free_000 the open left
     the pads inside the cup (link12 d -10.57 mm at 113 N, link13
     d -0.82 mm at 109 N, fingers 39.1/38.0 mm), three retries, the cup
     stayed on the hand, the later die picks closed on nothing. Base
     released that cup cleanly in both of its runs; the on-check at 50
     iterations failed the same release lightly (d -0.10 mm, 0.58 N).
     Mechanism not measured. Orchestrator's code read 19:45: the
     structure accepted (merge-clean hunks, the refusal on every world,
     the off path unchanged); the behaviour not. The agent
     (acf1fc489c989fbef) resumed 19:50 on the jam probe: a direct harness
     (pick, carry, place, open of d_cups_ud in scene 0; per step the hand
     z, the cup's pose in the hand, q1/q2, the pad contacts) over the
     arms base, 10 N/4 mm, 10 N/1 mm, 20 N, gear off, 50 iterations; the
     hypotheses: the cup moves in the hand under 10 N (24 N of friction
     capacity against the junction kicks), the descent drives the pads
     into the cup, the open cannot clear the cup's collision shape at the
     pads' final height (a radius of about 44 mm there, the cup's axis
     5.4 mm off the hand's), the gear at the open. A fix goes on the
     branch if it lives in the fix's files, then seed 0 three times.
     Report reviews/impl_force_hold.md (a "Jam probe" section to come);
     its ep_iters.py and ep.sh tracked, runs/ untracked (ledger). Kept for
     the review: the 60-step position hold stays as the tested start; the
     per-carry fields (|q1 - q2|, the sink) are not logged.
     JAM PROBE 20:20 (impl_force_hold.md "Jam probe", probes/force_hold/):
     the jam is NOT the switch's. jam_probe.py (pick, lift, carry, place
     descent, release as _release_and_verify_drop; 7 levers, 2 places, 8
     trials): base jams 8 of 32 releases (25 %), every force_hold variant
     9 of 64, force_hold as implemented 2 of 16 (Fisher p 0.26, 0.46);
     17 of 18 jams light (a pad still touching the cup after the open, up
     to 0.9 mm, 7.7 N: the cup leans on a finger and the hand does not
     move between the three retries), the one deep jam base's. Base's own
     episode s14_base_r1 has it. Under the force hold the cup turns less
     in the carry (1.0 to 1.6 deg median against base's 3.2 to 7.4) and
     the pads sit shallower in the descent (-0.26 to -0.30 mm against
     -0.91 to -1.08). The open clears an upright centred cup by 5.8 mm
     (wall 32 to 33 mm, lip 37.8 mm, finger faces at 38.9 mm); the gear's
     50 N cannot hold a finger against the 200 N open. The episode's deep
     jam (10.6 mm) did not recur in 64 releases: open, not attributable.
     IMPLEMENTATION REVIEW 20:25 (reviews/implrev_force_hold.md, the
     orchestrator): ACCEPTED, no change; arm `solver_iters+force_hold`
     only; the release jam is an OPEN FINDING for the audit (candidate
     fix outside this campaign: a retreat along the approach axis after
     the open before the contact verify, in execution.
     _release_and_verify_drop / execute_place / execute_stack, the
     physical justification execute_place's comment asks for before
     restoring audit #85's pre-release lift). pad_rolling DROPPED: the
     fallback condition (force_hold failing) never came.
   - carry_trapezoid DONE 19:57: commit b1e2455 on slip/carry_trapezoid
     (test_full_pipeline.py: register at import 124 to 152,
     carry_trapezoid_schedule 170 to 223 ported from carry_motion's
     trap_schedule, _stream_carry_trapezoid 240 to 299,
     stream_move_waypoints 302 to 338 with today's per-pair loop moved in
     verbatim, main's move action one call 2104 to 2110; robot_utils
     untouched; 14 tests). On and holding: one acceleration-bounded
     schedule per move (collinear pairs merged, a rest at every bend,
     one move_robot_smooth call of one step per scheduled step with
     velocity_bounded=False, the settle and the home hold as today), one
     "carry_trapezoid:" log line per move. Checks green on and off (67 +
     89 tests, gates PASS, seed 0 success). Real-pick probe
     (reviews/carry_trapezoid_probe/, tracked): at the flip (hand yaw
     180) 62 of 64 held with today's stream and 62 of 64 with the
     trapezoid, the same two lost, McNemar p 1, so NO GAIN on top of the
     flip; alone (hand yaw 0) 21 against 32 of 56 (p 0.019), 1 against
     10 of 14 at 3 deg (p 0.004): HARM ALONE confirmed in a real pick. It
     does remove the zero-force junction steps (minimum summed pad force
     median 0.04 N to 2.02 N) and shortens straight carries (406 to 382
     steps). Seed 1 on: held, but 865 s and 118 plan calls (the cup
     radius loop). IMPLEMENTATION REVIEW 20:00
     (reviews/implrev_carry_trapezoid.md, the orchestrator): ACCEPTED,
     no change; no refusal without grasp_wrist_home (the arm specs pair
     them); the lift handover stays; whether job C keeps its arm is a
     phase-7 decision with grasp_wrist_home's report in hand. Merge note:
     carry_hold_check also edits the move action.
   - grasp_wrist_home DONE 19:40: commits c659e64 (pose_belief.py:
     register at import 19 to 28, PANDA_TOP_DOWN_Q7_OFFSET 5 pi / 4,
     PANDA_Q7_LIMIT, WRIST_HOME_TIE_BAND 5 deg, wrist_joint7_top_down
     and wrist_home_twin 251 to 285; streams.py: _prefer_wrist_home 93
     to 129, sample_grasp 882 to 889 maps every candidate of both paths
     through it with the robot base and home's joint 7 read at call
     time; 7 tests) and b6a0b90 (probes/grasp_wrist_home/ scripts and
     summaries, tracked on the branch) on slip/grasp_wrist_home. The rule:
     joint 7 of a top-down grasp is wrap(bearing - yaw + 5 pi / 4), the
     member of {yaw, yaw + pi} nearer home's joint 7 (clipped at the
     limit) is taken unless within the 5 deg band; no IK, no FK, no
     allowlist line. Validated: against the kin stream's IK on 450 cells
     of both worlds the chosen member is the IK-nearer one in 362 of 369
     and never the farther (prediction error median 3.5 deg, p95 11 to
     17); the joint-7 clip disappears (26 and 10 limit cells today, 0);
     median wrist distance to home 132/123 deg to 45/44; on the five
     recorded base carries the twin is taken (predicted travel within 4
     to 19 deg of the recorded 167 to 199) and the flip episodes' yaw is
     kept. Checks: gates PASS, seed 0 success on and off (the twin taken
     for the die and the cup on); the bridge suite had 1 and 2 failures
     of the goal-at-home episode tests under load (gf9, b3 adopted
     goal), which pass alone and fail with the switch off too: the
     laptop-load flake family, pre-existing (force_hold's check hit it
     as well). Seed 1 on: held, reward 1.0, the twin, joint 2 the
     largest mover home; seed 6 on: the cup loop (43 refusals, 89 plans,
     stopped at 900 s), needs pose_radius_keep (job B pairs them).
     IMPLEMENTATION REVIEW 20:08 (reviews/implrev_grasp_wrist_home.md,
     the orchestrator): ACCEPTED, no change; the 5 deg band stands on
     its measurement; the analytic rule is enough (the IK alternative
     costs two solves per candidate); the pre-sense grasps keep today's
     yaw until the body is registered. Merge note: pose_belief.py's
     import block gets `import slip_fixes` from both pose_radius_keep
     and this branch (keep one, both registers).
   - solver_iters DONE 18:40: commit 2252af5 on slip/solver_iters (5
     files, only added lines): robot_utils.SOLVER_ITERATIONS = 200;
     registered at boxel_env's import; applied in policy.py d9_setup
     after setTimeStep (74 to 80), boxel_env __init__ (568 to 578) and
     reset() (2025 to 2035), the plan client stays at 50; 3 G1 allowlist
     lines; one log line per place with the value read back; 6 tests.
     Checks green (59 + 89 tests, gates PASS, seed 0 success on and off).
     DEVIATION every physics switch needs: d9_setup runs before main()
     configures the switches, so execute_fn now calls
     slip_fixes.configure(cfg.switches.get('slip_fixes', '')) right
     before d9_setup (policy.py 201 to 204); force_hold was told to copy
     the identical lines; the merge keeps the call exactly once. Cost:
     the check episodes are not a clean measure (different plans, the
     laptop under load: 3.43 against 1.24 ms of exec per step); a resting
     bench shows 0.118 against 0.133 ms; the proposal's +0.9 ms per step
     stands until the cluster arm measures it. Open for the
     implementation review: test_full_pipeline 2995's scene-acceptance
     probe env runs at 50 even with the switch on (our scenes only).
     Report reviews/impl_solver_iters.md. IMPLEMENTATION REVIEW 18:55
     (reviews/implrev_solver_iters.md, the orchestrator): ACCEPTED, no
     change; the allowlist is matched by (file, function, source text),
     so the merge cannot stale its line numbers; the configure call must
     exist once after the merge; every switch's module must be imported
     before execute_fn runs (all seven are).
6. THEN implementation review (Opus or Sonnet per branch), fixes applied.
7. IN PROGRESS (from 20:12): the campaign branch is `slip/campaign` in
   the worktree `C:\Users\HaniAlassiriAlhabbou\git\sb-slip-campaign`
   (tools/slip_worktree.ps1 -Name campaign, from tampura-bridge fd36342).
   Merged with `git -c core.autocrlf=false merge --no-edit`:
   slip/solver_iters 5b09e6b, slip/pose_radius_keep 0f0ac8f,
   slip/grasp_wrist_home 506c369 (the one conflict, pose_belief.py's
   import block, resolved by hand: one `import slip_fixes`, both
   registers), slip/carry_trapezoid 7f30fd2; the configure call is in
   policy.py exactly once. The check with the four on (slip_check.sh,
   seed 0, fixes solver_iters,pose_radius_keep,grasp_wrist_home,
   carry_trapezoid; outputs in the worktree's checks/) started 20:15 and
   came back GREEN 20:29: 90 unit tests, 89 bridge tests (3 skipped),
   gates PASS, seed 0 success in 85 s with the four on, 1 die carry
   (checks/2026-10-31_20-13-23_s0_solver_iters,pose_radius_keep,
   grasp_wrist_home,carry_trapezoid). force_hold merged 20:31 as
   dbaaba2, clean (its configure hunk and import folded into
   solver_iters' identical ones: one call, one import; five switches
   registered: boxel_env, pose_belief twice, robot_utils,
   test_full_pipeline). The check with all five on (the first run of
   force_hold at 200 iterations through the real solver_iters switch)
   started 20:32 and came back GREEN 20:35: 99 unit tests, 89 bridge
   tests, gates PASS, seed 0 success in 29 s, 1 die carry; the episode's
   log has "numSolverIterations 200 on the executing world", the gear
   constraint on client 0, and the force hold on the cup (half-width
   33.22 mm, pads 14.2/17.1 N at the hand-over) and on the die (10.00 mm,
   6.9/6.9 N) (checks/2026-10-31_20-30-05_s0_solver_iters,force_hold,
   pose_radius_keep,grasp_wrist_home,carry_trapezoid). The off check of
   the five-merged branch started 20:37 and came back 20:42: 99 unit
   tests, gates PASS, seed 0 success off in 26 s; the bridge suite had
   ONE failure, test_gf9_gated_episode::test_gated_goal_at_home_episode,
   the laptop-load flake family (it passed in the two checks before on
   the same merged code; the final checks re-run it). carry_hold_check
   merged 20:48 as 1f8faea (the one conflict, the move action's begin
   hook against carry_trapezoid's streaming call, resolved by hand: the
   hook first, then the call; the end block merged clean); its source
   test looked for the old waypoint loop and now accepts the call
   (f3d8cd1 on slip/campaign); the merged unit suite is 109 with that
   one fixed. tampura-bridge (74cffac: the harness fix, the records)
   merged 20:57 as 7563551: slip/campaign = tampura-bridge + the six
   fix branches, code diff 8 files +868 -35 against fd36342. FINAL
   CHECKS started 20:58 (scratchpad final_checks.sh: slip_check with all
   six on, slip_check off, then one seed-0 episode through
   reviews/impl_carry_hold_check/ep_loss_inject.py with all six on and
   one injected carry loss of the die; outputs in the worktree's
   checks/). FINAL CHECKS GREEN 20:53: all six on 116 unit tests, 89
   bridge tests, gates PASS, seed 0 success in 23 s; all off the same
   counts, success in 31 s (the gf9 flake passed both times); the
   injected loss ran the whole path (the LOST carry line, the loss line,
   "transit loss 1/3", the die retired as lost, the replan found no
   shadows, the goal check "no held object (gripper is empty)", outcome
   failure, no traceback; checks/2026-10-31_20-52-22_s0_inject). HARNESS
   BUG, round two (found by counting that episode: 3 losses for 1):
   console_debug.log echoes every ERROR and action print as a
   "[console]" line, and the goal check's "gripper is empty" matched the
   goal-loss regex. Fixed 21:05 (562db41 on tampura-bridge, merged into
   slip/campaign as cff9bc5): the pipeline's lines are read from
   run_*.log (each once; fallbacks console_debug.log without its
   "[console]" lines, then stdout.txt), the verified pick from
   stdout.txt (or the console log's curated lines), and the goal loss
   matches only the two physical reasons (finger-pad contact
   incomplete, a graze); 10 tests. Verified on four real episodes: the
   injected loss 1 carry 1 loss 1 try, the off success 1/0/1, the
   50-iteration goal-check loss 1/1/1, the seed-1 cup loop 0/0/0 (no die
   pick). SNAPSHOT: slip/campaign cff9bc5 = tampura-bridge 562db41 + the
   six branches, `sb_cff9bc5` (push_snapshot.ps1 -CodeOnly from the
   campaign worktree; the first upload timed out at the gateway, retried
   and unpacked 21:08, 46 entries). SUBMITTED 21:08 from cn-04 (every
   job's Slurm prolog stamps its start 21:08:31; an earlier "21:12" here
   ran ahead of the clock), the five nodes idle at submission, all five
   jobs pending on priority at first:
     A 5006486 cn-101  base,solver_iters,solver_iters+force_hold
     B 5006487 cn-102  base,pose_radius_keep,pose_radius_keep+grasp_wrist_home
     C 5006488 cn-103  base,pose_radius_keep+grasp_wrist_home+carry_trapezoid,carry_hold_check
     D 5006489 cn-105  base,solver_iters+force_hold+pose_radius_keep+grasp_wrist_home
     T 5006490 cn-106  TAMPURA, slip_t.sbatch, 3 reps, seeds 0-19
   (slip_eval.sbatch sb_cff9bc5 <arms> 0-19 3 0-19: 3 reps of every seed;
   results in $W/results/slip_cff9bc5/<job id>/ and
   $W/results/slipT_cff9bc5_5006490/; logs $W/logs/p4-slip_<id>.txt and
   p4-slipT_5006490.txt). To read them together: cat the four jobs'
   results.jsonl into one directory and run `tools/slip_eval.py --out
   <dir> --summary` with --arms listing every arm; per-scene tables by
   scene_file (the three-scene map in "Eval design notes"). Watch for:
   check_arms failing at a job's start (an unregistered name), the gates
   FAIL line, the 600 s caps on the cup-loop seeds, and the 12 h limit.
   STARTED 21:08:31, all five (checked at 21:16 by a delayed squeue and
   each log's first lines): gates G7, G11(i), G17 PASS in A, B, C and D;
   check_arms printed every arm's fixes (A: [] / ['solver_iters'] /
   ['force_hold', 'solver_iters']; B: [] / ['pose_radius_keep'] /
   ['grasp_wrist_home', 'pose_radius_keep']; C: [] / ['carry_trapezoid',
   'grasp_wrist_home', 'pose_radius_keep'] / ['carry_hold_check']; D: []
   / the four); 180 episodes to run in A, B and C, 120 in D; D's first
   episode (base, seed 0, rep 0) a success, wall 27.4 s, 1 carry, 0
   losses; T's log was still at its Slurm prolog. A background waiter on
   the laptop (a fresh ssh to cn-04 every 20 min, squeue) wakes the
   session when the first of the five ends; its summary is pulled then
   (phase 8 begins with T and D; the full table when A, B and C end,
   expected 04:00 to 06:00).
   Cluster at 20:40 (sinfo -p rleap_cpu):
   idle cn-101, 102, 103, 105, 106, 107, 108, 109, 113, 114, 115, 116;
   mixed cn-104, 110 (another user's array), 111, 112; long pending
   arrays of other users queued (%100), so the idle nodes may fill: pin
   jobs A, B, C, T to four distinct idle nodes (first choice cn-101,
   102, 103, 105) and re-check sinfo right before sbatch. $W/p4 is 14 GB
   on disk (the environment; prune_work's cap counts results and
   snapshots). SUBMISSION PLAN (drafted 21:00, before any result; the
   snapshot name sb_<sha> is slip/campaign's HEAD after the final checks
   pass, pushed with `Set-Location sb-slip-campaign; pwsh
   <main>/tools/cluster/push_snapshot.ps1 -CodeOnly`): on cn-04, with
   W=/work/rleap1/hani.alassiri.alhabboub/p4 and OUT=$W/results/slip_<sha>
   shared by the jobs (each writes OUT/<job id>):
     A: sbatch -w cn-101 $W/sb_<sha>/tools/cluster/slip_eval.sbatch sb_<sha> base,solver_iters,solver_iters+force_hold 0-19 3 0-19 $OUT
     B: sbatch -w cn-102 ... base,pose_radius_keep,pose_radius_keep+grasp_wrist_home 0-19 3 0-19 $OUT
     C: sbatch -w cn-103 ... base,pose_radius_keep+grasp_wrist_home+carry_trapezoid,carry_hold_check 0-19 3 0-19 $OUT
     D: sbatch -w cn-105 ... base,solver_iters+force_hold+pose_radius_keep+grasp_wrist_home 0-19 3 0-19 $OUT
     T: sbatch -w cn-106 $W/sb_<sha>/tools/cluster/slip_t.sbatch sb_<sha> 3 0-19
   Job D is a PRE-REGISTERED prediction, stated before any eval result:
   from the probes, the best set should be solver_iters+force_hold (the
   hold) with pose_radius_keep (the cup loop) and grasp_wrist_home (the
   wrist spin); carry_trapezoid (no gain on top of the flip in the
   real-pick probe) and carry_hold_check (an honest ending, not a
   safer carry) are judged by jobs B and C. Job E after the analysis
   tests the set the results pick if it differs from D, or adds reps.
   Expected wall per job: 180 episodes (A, B, C) at a median near 2 min
   plus the cup-loop caps (600 s) of base and the arms without
   pose_radius_keep, 7 to 9 h; D 120 episodes, about 5 h; T about 2 h.
   Then the off check,
   `tools/cluster/push_snapshot.ps1 -CodeOnly` FROM THE CAMPAIGN WORKTREE
   (it archives the cwd's HEAD), then on cn-04 one `slip_eval.sbatch` per
   arm group (always `base,<fix>,<fix>`), pinned to distinct nodes
   (`sinfo -p rleap_cpu`; never two of our pipelines on one node), 3 reps
   on ALL 20 seeds (the per-carry outcome is a near coin flip and
   non-deterministic, so about 60 carries per arm are needed; the entropy
   subset 1,2,3,6,11,15 is then a subset of that), plus `slip_t.sbatch`
   for TAMPURA (3 reps, seeds 0-19). Hani approved the cluster for this
   campaign in his request; the sbatch commands are still shown to him.
8. THEN analysis: the table of every fix (success, loss per carry,
   medians of wall and planning, replication disagreement), the best set,
   a combined arm (`a+b+c`) evaluated the same way with TAMPURA beside it,
   the BF#59 audit entry, DATA_LEDGER rows, garbage deleted.
   A SEVENTH CANDIDATE from the follow-up session (card "Cup release
   jam", done 21:52): `release_retreat` on branch slip/release_retreat
   (worktree sb-slip-release_retreat, from tampura-bridge cac0137; 6e225e7 the switch, dc2c5e2 nine tests,
   4516614 the probe, 9168b58 the BF#61 audit entry with ledger rows and
   reviews/impl_release_retreat.md; merge preview onto tampura-bridge
   clean; nothing pushed): inside `_release_and_verify_drop`, after the
   open and before the settle and the verify, the hand retreats 15 mm
   along the approach axis at every place and stack of every body (the
   emergency release at a replan break unchanged). Its probe (96 paired
   carries, today's hold): today's release jams 18 of 96, with the
   retreat 8 of 96 (freed 10, made 0, McNemar p 0.002); 30 and 50 mm buy
   nothing; the jams left are a cup riding up on one pad after the
   position hold pressed it 1.1 mm in, so release_retreat+force_hold is
   the arm to measure. Checks on and off green (seed 0, 72 tests, 89
   bridge tests, gates PASS). NOT in the running eval (its snapshot is
   cff9bc5). Its cluster eval needs Hani's approval of that question
   alone; the natural place is job E beside the chosen set.
   RESULTS (all five jobs in by 04:10 on 2026-11-01; the pulled records
   in eval/<job>/, tracked; the table script eval/slip_table.py reads
   every job's results.jsonl and T's campaign.jsonl and writes
   eval/TABLE.md, the full table; a Sonnet agent recomputed the numbers
   independently, see "second opinion" below):
   - Job D (5006489, cn-105, 21:08 to 23:57, 120 episodes): base 42/60
     successes, 9 timeouts (seeds 6, 17, 19 in all three reps, all on
     scene 1747173590: the cup loop), 9 losses in 51 carries (0.18;
     every failure a physics_mismatch, the die lost: seeds 1, 8, 14, 18
     in rep 0, 5 and 14 in rep 1, 5, 10 and 18 in rep 2), 6 of 20 seeds
     with disagreeing reps. The PRE-REGISTERED combined arm
     solver_iters+force_hold+pose_radius_keep+grasp_wrist_home: 60/60
     successes, 0 timeouts, 0 losses in 60 carries, 0 of 20 seeds mixed;
     medians (rep 0, the 17 seeds base ran to the close) wall 24.9 to
     16.6 s, planning 13.8 to 9.3 s, exec 8.0 to 5.5 s, plan calls 5 to
     3; per-seed ratios wall x1.08, planning x0.99 (a little slower where
     base is quick, much faster where base loops or loses).
   - Job T (5006490, cn-106, 21:10 to 23:57, 60 episodes): TAMPURA
     13/20, 14/20, 13/20 (one crash, seed 9 rep 3, rc 1 after 51 s,
     counted censored), 40/60 in all; per scene 1747173591 19 of 21,
     1747173593 14 of 24, 1747173590 7 of 15; loop times 47 to 415 s
     (the medians in the table). TAMPURA runs at its own 50 solver
     iterations (to disclose beside our solver_iters arms) and the M8
     calibration issue stays open.
   - Job A (5006486, cn-101, 21:08 to 02:27, 5 h 18 min, 180 episodes;
     pulled 02:50 after one gateway drop): base 44/60, 8 timeouts, 8
     losses in 52 carries (0.15), 8 of 20 seeds mixed. solver_iters
     ALONE 26/60, 4 timeouts, 31 losses in 57 carries (0.54, p 2e-5
     against its base): the firmer convergence with today's 0.5 mm
     position hold expels the die on every scene, 14 of 20 carries even
     on 1747173591 where base never loses, so solver_iters must never
     ship alone (force_hold already requires it; the reverse holds
     too). solver_iters+force_hold 54/60, 5 timeouts (the cup loop:
     seed 17 in all three reps, 5 and 6 once; no pose_radius_keep in
     this arm), one pick give-up (seed 13 rep 0, no carry), 0 losses in
     54 carries (p 0.0025 against its base, 0.0007 against the pooled
     base), 3 of 20 seeds mixed (5, 6, 13: the timeouts and the
     give-up); paired wall x1.06, exec x1.15 (the iterations), mean
     process wall 100 s vs 118 s. Base's losses sit on scene 1747173593
     (8 of 24 carries in A, 6 of 24 in D) and 1747173590 (3 of 6 in D);
     scene 1747173591 never loses in base (0 of 42 carries over A and
     D).
   - Job B (5006487, cn-102, 21:08 to 02:48, 5 h 40 min, 180 episodes;
     pulled 04:10): base 40/60, 8 timeouts, 11 losses in 51 carries
     (0.22), 7 of 20 seeds mixed. pose_radius_keep ALONE 39/60, 1
     timeout (the cup loop of scene 1747173590 cured: 11/15 there
     against base's 6/15), but 20 losses in 59 carries (0.34; p 0.20
     against its base, 0.02 against the pooled base): the seeds that
     used to loop now reach the carry and lose it there (4 of 15 on
     1747173590), and 1747173593 loses more too (14 of 24 against 9 of
     23), so the kept radius may also change the die's own pick (open,
     not significant alone). pose_radius_keep+grasp_wrist_home 49/60,
     1 loss in 50 carries (0.02; p 0.004 against its base), the
     cup-loop scene 15/15, BUT 10 timeouts, all on scene 1747173593
     (seed 1 three times, 4 twice, 14 twice, 3, 15, 18 once): a NEW
     LOOP, read in seed 1 rep 0's log: the plan wants e_cups_ud; the
     closer look gives the wrist detection's radius 0.49 mm; the
     overhead refresh after the next move gives the eye's 5.71 mm with
     a centre 2.56 mm from the wrist's, so pose_radius_keep's rule keeps
     min(5.71, 0.49 + 2.56) = 3.04 mm, "outside its commit margin", the
     pick is skipped ("pose is too uncertain, I should look first"),
     the plan is remade and the closer look repeats: 69 refusals, 93
     plans, 600 s. The same seed in base and in D's arm has no refusal
     (base never wants that cup; D's arm reaches it without the
     disagreement; WHY is OPEN, a hypothesis: the hold pair changes
     the cups' settled poses or the plan). The rule's centre-shift term
     is the mechanism: a cup whose eye and wrist centres disagree by
     more than the margin minus the wrist radius loops for ever under
     pose_radius_keep.
   - Job C (5006488, cn-103, 21:08 to 03:46, 6 h 38 min, 180 episodes;
     pulled 04:10): base 42/60, 6 timeouts, 12 losses in 54 carries
     (0.22), 5 of 20 seeds mixed. carry_hold_check 42/60, 10 timeouts,
     9 losses in 51 carries (0.18; p 0.63): no safer carry, as
     expected; the replans after a detected loss push four more
     cup-loop episodes past the cap (seeds 1, 5, 19); exec x1.05. An
     honest ending, not a fix: not in the final set (the switch stays
     for diagnosis). pose_radius_keep+grasp_wrist_home+carry_trapezoid
     54/60, 0 losses in 54 carries (p 0.0002 against its base), 5
     timeouts and six more episodes of 160 to 540 s, all on scene
     1747173593 (the same cup loop as B's arm), paired exec x1.22 and
     wall x1.07 (the trapezoid schedule is slower); against B's arm
     without it (1 loss in 50) no measurable gain. Not in the final
     set, as pre-registered.
   SECOND OPINION (a Sonnet agent, 05:00, its scripts deleted with the
   session's scratch): 623 cells of TABLE.md reproduced from the
   records, no numeric discrepancy; four readings adopted or noted: the
   planning and execution medians are now over finished episodes only
   (every timed-out episode carries a metrics object with partial
   planning_s and exec_s at the cap; the table and the entry say
   "finished"); the pooled base's 13 of 20 mixed seeds is over 12
   repetitions, like for like it is 26 of 80 job-seed triples; TAMPURA's
   crash and its censored episode are the same one (rep 3 seed 9);
   Fisher's and Clopper-Pearson's independence does not hold across
   three scenes and replicated seeds, so the p-values are descriptive.
   Sanity: 180/180/180/120/60 records, the full seed x rep grid in every
   arm, no duplicate keys, losses never above carries, one episode with
   two carries (A solver_iters seed 18 rep 0), the 66 timeouts all
   without an outcome.
   DECISION (the orchestrator's suggestion, 04:30): the final set is
   the pre-registered D set, solver_iters+force_hold+pose_radius_keep+
   grasp_wrist_home: 60/60, 0 losses in 60 carries, 0 timeouts, 0
   mixed seeds, the only arm free of both loops. The hold needs the
   pair (solver_iters alone 0.54 losses per carry; force_hold requires
   it), the cup loop needs pose_radius_keep, grasp_wrist_home brings
   the hold from 0 of 54 to 0 of 60 and the new loop of
   pose_radius_keep is avoided only in this combination (OPEN why).
   carry_trapezoid and carry_hold_check out. Job E: the chosen set
   equals D, so E is only needed for more reps or for release_retreat
   beside it (needs Hani's approval: base, the D set, the D set +
   release_retreat, 3 reps of seeds 0-19 on one node, about 6 h).
   Hani's decisions: merge slip/campaign into tampura-bridge (switch
   code, default off) and whether the four go on by default.
   PHASE 8 STATUS (04:50): the BF#59 entry is written into
   PAPER_AUDIT.txt between BF#58 and BF#60 (209 lines) and staged as its
   own hunk (the index blob built from HEAD plus the entry, so the other
   sessions' unstaged hunks in that file stay theirs); committed once
   the Sonnet second opinion on the numbers is in. GARBAGE DELETED (the
   ledger's log, 2026-11-01 04:50): the probes' sweep outputs and
   episodes 151 MB (the 71 scripts and summaries tracked first), the
   six fix worktrees and the campaign worktree (1.27 GB on disk; the
   branches stay), the cluster's loss_context duplicates. KEPT: the
   cluster's five episode trees (615 MB, retention), the snapshot
   sb_cff9bc5 until job E is decided, probes/force_hold/out (BF#61's
   comparison data, review), hold_physics/runs' carry.jsonl. The
   cluster is 1.4 GB against its 1 GiB cap by protected data (the B8 T
   trees are Hani's call).
   - Cluster cap: prune_work at T's end counted 1178 MiB of 1024 and
     found nothing it may delete (the two B8 campaigns' T episodes
     625 MiB cited by BF#54, the per-fix eval's 111 MiB behind the open
     replan-loop finding, D 62 MB, T 210 MB); A, B and C add about
     280 MB. Nothing of ours is garbage by the ledger's rules; whether
     the B8 T episodes may go is Hani's call.
   - release_retreat, the side session's final (11:00): branch
     slip/release_retreat at 958c965 (after 15cf540 and 9168b58; worktree
     sb-slip-release_retreat, the side session's; nothing pushed). Its
     BF#61 entry, on that branch, now counts the release jams in the
     finished jobs' logs over release attempts, the counted lines
     stated: base 18 jams in 536 attempts, the D set 0 in 141; why the
     zero-jam arms do not jam is marked open. Job E for release_retreat:
     declined by this session on Hani's "if parent agent says no, then
     no" to that session (no power against 0 of 141 under the chosen
     set, the cap exceeded); the switch stays default off. Whether
     slip/release_retreat merges into tampura-bridge is Hani's call,
     beside the merge of slip/campaign, the defaults, job E for more
     reps and the B8 T trees.

## Diagnosis so far (from the two finished proposals)

- The die ROTATES out of a near-face pinch during the swing home: the
  squeeze wedges it toward face alignment, the width narrows past the
  0.5 mm squeeze, waypoint-junction decelerations of 60 to 97 m/s^2 unload
  the pads; a die turned past about 100 deg leaves without a kick. Not at
  the pick, the lift or the home hold.
- The hold depends on the yaw between the pads and the die's faces: exact
  face pinch 79 to 88 %, 1 to 25 deg off 46 to 51 %, pads on two opposite
  edges 80 to 94 %. The eye's yaw noise (9.5 deg, snapping) cannot certify
  a face pinch; it can certify an edge pinch.
- Per-carry outcome is non-deterministic (seed 1 three times: held, lost,
  lost; the planner's timing diverges under load). Every eval number needs
  replication.
- The slow tail is a cup loop, not the die: the overhead refresh after a
  move overwrites the wrist observe's pose radius (0.39 mm to 5.49 mm) and
  the pick's commit check refuses; up to 90 plans until the cap.
- Pick-time pad force and half-width do not separate held from lost; the
  finger width growth over the carry (> 0.05 mm) predicts a loss with about
  100 steps of lead.

- carry_motion (15:40): every recorded carry home spins the wrist (joint 7)
  back 211 to 242 deg because the M9 yaw wrap picks the "smallest wrist
  rotation" in the world frame, not on the arm (joint 7 at -1.95 to -2.9
  rad at the pick, home +0.785); the pad-swapped grasp (yaw + pi) needs a
  median 22 deg. That spin turns a die that sits off its face out of the
  pinch; the junction kicks are the second cause. Probe (their world, our
  close, 92 to 96 carries per cell): today 93/92/59/16 % held at
  0/3/10/20 deg off the face; pad-swapped grasp plus an
  acceleration-bounded schedule 100/100/99/85 %, 98 % on an RRT-like bent
  path. The two only work TOGETHER (each alone is worse than base at some
  angles). The home hold is harmless; a transit inflation (BF#47) is not
  needed for the slip. Episodes with both patched in: seeds 0 and 1 held;
  seed 6 hit the cup pose-radius loop (the flip turns cup grasps too), so
  the flip must be evaluated with pose_radius_keep on.

- hold_physics (work log 16:34, proposal sections pending): the 0.5 mm
  position hold (BF#44's default, 60 N) lets the pad force collapse to
  0 N whenever the die shifts a few hundredths of a millimetre (every
  carry has zero-force steps, 33 of 38); the loss grows with the time in
  the hand, not with the peak acceleration (half carry speed 35 % lost
  against 17.7 %, 113 grips per lever). A hold that keeps pressing (the
  fingers' target 4 mm inside the measured width at a motor budget of
  10 N) expels the die under the default 50 solver iterations (96 %
  lost): a projected Gauss-Seidel convergence artefact of a 5.2 g body
  between two 0.1 kg fingers (a sharp box of the same mass is expelled
  the same way; 100 or more iterations, or a heavier body, remove it),
  and with 200 iterations loses 0 of 113. But PyBullet ignores their
  URDF's `<mimic>` on panda_finger_joint2, so force-limited fingers drift
  off-centre by 3.7 to 4.3 mm and slosh during the swing; a JOINT_GEAR
  constraint (gearRatio -1) couples them within 0.01 mm. The smallest
  combination that holds every body tested at every yaw tested: coupled
  fingers + 200 iterations + a 10 N force-limited hold (die 0/113, cubes
  0.5 and 0.1 kg 0/57, cup a 0/57; the position hold loses 46 to 58 % of
  our own 40 mm cubes at 3 to 10 deg of grasp yaw, a loss Q14 never
  measured). Rolling friction (their set_dynamics table: die rolling 0.01)
  helps the light hold (3.5 %) but not a firm one. The step time doubles
  at 200 iterations (1.0 to 1.9 ms). Episodes: laptop seeds 1 and 6 held
  the die at home.

Fix names proposed: edge_pinch, face_needs_wrist_yaw,
pinch_band_certificate (grasp_geometry); carry_hold_check,
carry_grip_watch, carry_accel_limit, pose_radius_keep (loss_dynamics);
grasp_wrist_home, carry_trapezoid (= carry_accel_limit, one switch)
(carry_motion); finger_gear (a JOINT_GEAR constraint, gearRatio -1,
between the finger joints on the executing client in d9_setup and on our
own world in boxel_env: their URDF's mimic), solver_iters (200 solver
iterations in both places, about +0.9 ms per step), force_hold (after
both pads touch, a target 4 mm inside the measured width at a 10 N motor
budget per finger instead of 0.5 mm at 60 N; harmful without the other
two: 96 % lost; expected to bring the loss per carry from 21 % to near 0,
real if under 10 %), pad_rolling (rollingFriction 0.01 on both pads,
their create_default_env value; 4.4 % alone, the fallback) (hold_physics).

## Review results (phase 4)

- grasp_geometry (reviews/grasp_geometry.md, 16:58): DROP all three.
  edge_pinch: at best about 13 % loss per carry on the eval's carries
  while the eval can only tell a fix from base at 4 to 5 losses in 60; it
  re-grasps the dice that hold today (the cup-placed die sits at yaw 0);
  the edge band is lopsided under the pipeline carry (35 deg 28/48, 55 deg
  44/48); the 25 mm scope is "the die" in disguise (rule 2) and without
  it our 40 mm cubes fall from 14/14 to 3/7. face_needs_wrist_yaw: the
  exact face pinch holds 79 % in its own probe, base's rate; the overhead
  refresh re-fuses the eye's yaw after the observe, so the commit check
  can refuse the die until the cap (the cup loop moved onto the die).
  pinch_band_certificate: the right form for rule 2 but its bands describe
  the 0.5 mm position hold that force_hold removes; 10 to 14 h. Missed by
  the proposal: within 1 to 4 deg the narrow width readings held 0/17 and
  5/16 against 37/55 and 29/44, the close's stopping step, which supports
  force_hold. Re-probe edge_pinch at 35 to 55 deg under force_hold only if
  that arm's losses depend on the logged yaw class.
- carry_motion (reviews/carry_motion.md, 17:12): grasp_wrist_home
  IMPLEMENT, its own arm with pose_radius_keep on. The reviewer re-ran
  grasp_geometry's real-pick probe (the die picked off the table, then
  the pipeline's per-pair carry) with the flip alone: 55 of 56 near-face
  grips held against 32 at hand yaw 0 (McNemar p 2e-7); "the two only
  work together" holds only in carry_motion's own probe, where the die is
  placed in the hand in mid-air. The wrap choice lives in
  pose_belief._wrap 131 and fitted_grasp_candidates 177 to 197,
  streams.sample_grasp 825 to 845 (orientation at 869); it was written
  for planning cost from Euler yaw 0, half a turn from the wrist at both
  homes; a sampler preference (model side) for every body; the kin stream
  certifies the flipped pose more easily (joint 7 between -0.35 and
  1.81 rad). A second mechanism the proposal missed: grasps at believed
  yaws above about 15 deg are clipped at the joint-7 limit and land up to
  10 deg off their yaw or find no IK (the flip's whole gain at 0 deg).
  Corrections: the recorded wrist travel is 168 to 199 deg, not 211 to
  242; every recorded die carry was the direct linear path, so the probe's
  straight line IS the pipeline's carry. The seed-6 cup loop is a real
  dependency (under the flip all four bodies are seen, the cup is re-posed
  at 5.71 mm and the pick refused; that scene is the cluster's scene of
  seeds 1, 2, 3, 4, 8, 14, 15, 18; rate unmeasured). carry_trapezoid:
  MERGE with carry_accel_limit as one switch, the tested rest-at-a-bend
  rule on the dispatcher's moves only (1877 to 1896), no single-hop
  extension, never alone (it harms the 3 deg pinch, 36 against 44 of 48,
  p 0.008); on top of the flip at most about 3 points are left, below
  what 60 carries can show; about 2 s per episode; add it only after a
  real-pick check (port trap_schedule into grasp_geometry's probe, about
  an hour). Power: against base's 21 % with 60 carries per arm an
  observed loss of about 8 % or less is significant, and 80 % power needs
  a true rate of about 3 %. If the hold set lands, the flip buys no extra
  hold, only the clip fix, reach and a shorter carry: the two compete for
  the same loss and the flip is far cheaper. The speed results disagree
  across probes (hold_physics' half speed worse, p 0.0008; carry_motion's
  slow run no effect, p 0.48). Recommended arms: pose_radius_keep alone;
  the hold set; grasp_wrist_home alone; every arm except base with
  pose_radius_keep on.
- loss_dynamics (reviews/loss_dynamics.md, 17:20; no probe run, every
  number re-read from the recordings): carry_hold_check IMPLEMENT, low
  priority, no solo arm: a model-side postcondition check like the
  post-lift re-verify, but in 3 of 3 recorded losses the die ends 0.08 to
  0.23 m from the base, outside W, 0 px in the eye and still rolling at
  the goal check, so a replan ends as target_lost, not a re-pick (the
  claimed 80 % recovery measured at 0 of 3); the shared helper must keep
  the post-lift check contact-only (no 0.5 N floor there today); TAMPURA's
  kinematic carry cannot lose, so the comparison must report loss per
  carry. carry_grip_watch DROP: on hold_physics' 113 base grips the
  0.05 mm widening line catches 8 of 17 losses and flags 9 of 96 holds,
  14 to 16 of about 55 held cup carries and 21 to 27 of 24 to 31 held cube
  carries; the set-down needs the dispatcher to swap the goal (rule 1);
  the stop is a bigger kick than the junctions; under the force-limited
  hold nothing is left to catch. carry_accel_limit MERGE into
  carry_trapezoid with carry_motion's implementation (one schedule per
  move, collinear pairs merged, rest at every direction change, settle
  and the F14 velocity limits kept; loss_dynamics' keep-speed-under-30-deg
  rule brings the kick back); alone it costs dice under today's wrist
  spin (70 and 48 % held against 92 and 59 % at 3 and 10 deg), so its arm
  pairs with grasp_wrist_home; on straight carries it uses fewer steps
  (336 and 356 against about 454). pose_radius_keep IMPLEMENT with the
  rule changed: the mechanism is confirmed (all 18 caps of the 192 BF#53
  episodes are the observe-then-refuse cup loop, none had picked the die),
  but min(old, new) keeps a 0.39 mm radius around the eye's re-posed
  centre measured 1.66 mm off; the rule is min(r_new, r_old + centre
  shift) (1.95 mm here, under the cup's commit margin of about 3 mm) and
  the wrist's yaw is kept too (without the yaw keep a yaw-needing grasp
  loops the same way); G15 unaffected. The loss predictor: a per-carry
  log line only, never a trigger (3 of 3 against 0 of 3 in the episodes
  becomes 8 of 17 against 9 of 96 at scale). Non-determinism: the
  planner's wall clock (pddlstream's adaptive solve allots sampling time
  by measured search time, so the seed-1 runs bind different plans; seed
  0 diverges too, pick force 5.00 against 3.28 N); the carry amplifies
  micrometre differences. Power: at 60 against 60 carries a fix must
  show 4 or fewer losses (6.7 %) against base's 13; a true 10 % has power
  0.29; only the near-zero claims are testable. Recommended arm order:
  pose_radius_keep first with a "base+r" arm beside the plain base; then
  on base+r: the flip (with the trapezoid), the hold set, edge_pinch with
  the trapezoid; carry_hold_check and the predictor line in every arm;
  the combined set last with TAMPURA beside it.
- hold_physics (reviews/hold_physics.md, 17:30): finger_gear MERGE into
  force_hold: it changes no loss rate alone or in the combination (die
  15/113 against 20/113, p 0.46; 0/113 with or without it under the hold)
  and the "96 % lost without the gear" is the solver's doing (103/113
  lost with the gear at 50 iterations); what it does is keep a
  force-limited pair centred (4.0 mm median off centre without it, 0.00
  with it), and execute_stack places the hand, not the body, so that
  offset would move every place and stack by up to 4 mm; only the
  executing client steps, so neither the planner's twin nor the kin
  stream needs it; created in d9_setup's setup phase (passes G14); four
  allowlist lines. solver_iters IMPLEMENT, own switch, own arm: the
  expulsion at 50 iterations is cured equally by 100 to 500 iterations,
  the die's mass x10 or its inertia x10, and a sharp box is expelled the
  same way; alone it is null on the loss (21/113); nothing else sets the
  iterations, the twin and the kin stream never step; GAP: boxel_env's
  reset() calls resetSimulation, which resets the iterations to 50
  (measured), so the switch must re-apply after every reset; cost at
  most about 0.9 x exec_s: on BF#53's 192 episodes +13 s at the median
  (+24 % of wall), +76 s at p90, +77 to +184 s of the 600 s budget in the
  18 capped episodes; a 60-episode arm about 2.3 h against 2.0 h.
  force_hold IMPLEMENT with the gear folded in and solver_iters required
  (refuse to run without it; the arm spec names both; no hidden
  implication and no base with the gear and the iterations on): die
  0/113 [0, 3.3] against 20/113, cubes 0/57 against 33/57 and 26/57,
  cups 0/57; rule 2 passes because the smallest force that carries our
  heaviest 0.5 kg class sets 10 N (5 N loses 13 to 27 of 57; the die
  alone would take 5 N); 20 N sits at the solver's edge (102/113 lost at
  100 iterations); for our boxes the summed pad force falls from 39.9 to
  20.9 N; the grip verification, the width plausibility (read at the
  touch), the post-lift re-verify, _verify_holding (19.8 N at home) and
  the place release all still work (checked in the code); the eval
  detects it at 4 or fewer losses in 60 carries. The unexplained reading
  is an unresolved contact (the pads 3.4 mm per side into the die during
  the lift at 20 N), not the measured-width logic. Untested: our tall
  0.5 kg occluders, the hold started at the touch instead of after the
  60-step position hold, the edge pinch, dice more than 10 deg off face.
  pad_rolling: fallback only (4.4 % against 17.7 % on the light hold,
  p 0.002; nothing once force_hold is on; no help for cubes; only the
  0.01 value is theirs, set on their table, not the pads). If force_hold
  lands, redundant: edge_pinch, face_needs_wrist_yaw,
  pinch_band_certificate, pad_rolling; grasp_wrist_home becomes a time
  gain, not a loss fix; complementary: carry_trapezoid (48 of 113 held
  carries still dip to 0 N), carry_hold_check, pose_radius_keep;
  carry_grip_watch's threshold fires on almost every carry under the
  force hold. The seed-6 grip miss the proposal left open: the hand
  arrived 105 mm from the cup (its own log), not the gear. The three
  episodes' save/ folders under probes/hold_physics/runs were deleted
  at 17:50 (3.3 MB, ledgered); the console_debug.log the review quotes
  went with them by the orchestrator's path mistake, so the quoted line
  (review lines 90 to 92) is the only record of it.

## Candidate list (phase 5), decided 17:35 from the four reviews

Seven switches. Dropped: edge_pinch, face_needs_wrist_yaw,
pinch_band_certificate (grasp_geometry: no measurable gain at the eval's
power, the size scope fails rule 2), carry_grip_watch (false alarms on
held cubes and cups, a goal swap). Merged: finger_gear into force_hold,
carry_accel_limit into carry_trapezoid. Every switch: default off,
`slip_fixes.register` at its module's import, `slip_fixes.on('<name>')`
at the point of difference, one branch `slip/<name>`, one worktree,
reviews/IMPL_BRIEF.md is the implementer's brief. Base commit of every
worktree: the tampura-bridge commit that carries this list (see the
phase 5 line).

1. `solver_iters` (hold_physics): numSolverIterations 200 on the bridge's
   executing client in `tampura_bridge/policy.py` d9_setup (after
   setTimeStep) and on our own world in `boxel_env.py` (after setGravity,
   AND again after every reset() because resetSimulation resets it to
   50); setPhysicsEngineParameter is a gated write (allowlist line with
   the reason). Logs the value once per world. Reports the step-time
   cost (wall and steps of the check episode against the base run).
   Review's requirement: the reset gap. Files: policy.py, boxel_env.py,
   tools/bridge_gates_allowlist.txt, tests/test_slip_solver_iters.py.
2. `force_hold` (hold_physics, finger_gear folded in): in
   `robot_utils.close_gripper_until_contact` (1135), once both pads
   touch, the fingers hold a target 4 mm inside the measured width at a
   10 N motor budget per finger instead of 0.5 mm inside at 60 N (the
   measured width, the grip verification and the width plausibility are
   read at the touch as today; the post-lift re-verify, _verify_holding
   and the place release unchanged); the JOINT_GEAR constraint
   (gearRatio -1, erp 0.1, maxForce 50) between the finger joints on the
   executing client, created in d9_setup's setup phase and in boxel_env
   at robot load (and after reset), allowlisted (four lines). The switch
   refuses to run without solver_iters on (a clear error at configure or
   at the first hold). Logs per hold: the measured width, the target, the
   budget, the force at the end of the hold. Files: robot_utils.py,
   policy.py, boxel_env.py, the allowlist, tests/test_slip_force_hold.py.
3. `pose_radius_keep` (loss_dynamics, rule changed by its review): in
   `pose_belief.record_detection`, a later detection of a body whose pose
   is already known does not loosen the radius beyond the old radius plus
   the centre shift: r = min(r_new, r_old + |c_new - c_old|), and the
   wrist observe's yaw is kept when the later detection comes from the
   overhead camera (the overhead refresh re-fuses "yaw = latest" today);
   pipeline-wide, every body. Logs each kept radius and yaw with both
   values. Files: pose_belief.py, tests/test_slip_pose_radius_keep.py.
4. `grasp_wrist_home` (carry_motion): the sampler prefers, between a
   grasp yaw and its pad-swapped twin (yaw + pi), the one whose wrist
   (joint 7) is nearer home, instead of the world-frame wrap measured
   from Euler yaw 0 (`pose_belief._wrap` 131, `fitted_grasp_candidates`
   177 to 197, `streams.sample_grasp` 825 to 845, orientation at 869);
   this also removes the joint-7 clip of grasps at believed yaws above
   about 15 deg (the review's second mechanism). Every body. The kin
   stream certifies as today. Logs per grasp: both candidates' joint-7
   distances and the choice. Files: pose_belief.py, streams.py,
   tests/test_slip_grasp_wrist_home.py.
5. `carry_trapezoid` (carry_motion, carry_accel_limit merged): one
   acceleration-bounded schedule per dispatcher move while holding
   (`test_full_pipeline.py` main's move action, 1877 to 1896): collinear
   waypoint pairs merged, a rest at every direction change (the tested
   rest-at-a-bend rule, no single-hop extension, no keep-speed-under-30-
   deg rule), move_robot_smooth's settle and the velocity limits kept;
   the primitive untouched. Never evaluated alone (its arm pairs with
   grasp_wrist_home). The implementer's check includes the real-pick
   probe (port its schedule into probes/grasp_geometry's real-pick probe,
   about an hour) and the step counts against base. Logs per move: the
   pairs merged, the rests inserted, the steps. Files:
   test_full_pipeline.py (the move action only), tests/test_slip_carry_
   trapezoid.py.
6. `carry_hold_check` (loss_dynamics): after every move made while
   holding, the executor verifies the hold with the shared helper (both
   pads in contact; the post-lift check stays contact-only, no 0.5 N
   floor there) and reports the loss as the action's failure so the
   dispatcher replans, instead of carrying an empty hand to the goal
   check; plus the per-carry log line of the finger-width growth over
   the carry (a metric, never a trigger). Model side (an executor
   postcondition, like the post-lift re-verify). Expected to move wall and
   the failure label, not the loss per carry. Files: execution.py or the
   dispatcher's move action (the implementer decides and says why),
   tests/test_slip_carry_hold_check.py.
7. `pad_rolling` (hold_physics, fallback): rollingFriction 0.01 on both
   finger pads in d9_setup and boxel_env (their create_default_env value;
   allowlisted if changeDynamics is gated). Implemented in round 2, its
   arm runs only if force_hold fails. Files: policy.py, boxel_env.py,
   tests/test_slip_pad_rolling.py.

Implementation rounds (four Opus at a time): round 1 solver_iters,
force_hold, pose_radius_keep, grasp_wrist_home; round 2 carry_trapezoid,
carry_hold_check, pad_rolling as slots free. Branches that touch the
same functions (d9_setup, boxel_env's setup, the allowlist): each adds
a self-contained block with its switch name in the comment, after the
existing code, no reordering or reformatting, so the campaign merge is
clean.

## Arm plan (phase 7), one job per node, base in every job, 3 reps x seeds 0 to 19

- job A: base, solver_iters, solver_iters+force_hold
- job B: base, pose_radius_keep, pose_radius_keep+grasp_wrist_home
- job C: base, pose_radius_keep+grasp_wrist_home+carry_trapezoid,
  carry_hold_check
- job T: TAMPURA, slip_t.sbatch, 3 reps, seeds 0 to 19
- after the analysis, job E: base and the combined arm (pose_radius_keep
  + solver_iters + force_hold + grasp_wrist_home, plus carry_trapezoid
  and carry_hold_check if their arms did not hurt), 5 reps on the 13
  seeds of scenes 93 and 90 if the budget allows; pad_rolling (and only
  then edge_pinch) if force_hold failed.
- Each job about 6.6 h serial (three arms of 60 episodes); base's four
  copies measure the node and time variance.

## Eval design notes

- The 20 campaign seeds load THREE scenes on the cluster (BF#39's pinned
  map, confirmed from BF53_eval_cluster/merged/results.jsonl, 16:58):
  1747173591 for seeds 0, 7, 9, 11, 12, 13, 16 (the die held in 55 of 56
  episodes of the per-fix eval: the always-held pick), 1747173593 for
  seeds 1, 2, 3, 4, 8, 14, 15, 18 (success 4 to 6 of 8 per seed, the
  losses), 1747173590 for seeds 5, 6, 10, 17, 19 (success 1 to 6 of 8, the
  cup loop and the losses). A seed is a planner RNG draw on its scene,
  not a scene. So per arm at 3 repetitions about 39 carries (the 13 seeds
  of scenes 93 and 90) carry the information, base's loss on them about
  32 % (31/96 in the per-fix eval), and a fix must bring that to about
  12 % or less to be told from base at 95 %; the 7 seeds of scene 91 are
  the regression guard. The analysis reports per scene group; the
  replication has two levels (the same seed three times: the timing
  non-determinism; the seeds of one scene: the planner's sampling
  variance). If the budget allows, the final combined arm and base get 5
  repetitions on the 13 seeds. TAMPURA's comparison stays on seeds 0 to
  19.

## Rules that bind every change

BRIEF.md section 5 (model side, pipeline-wide or TAMPURA-matched, no
executing-world pose reads feeding control, a switch default off, honest
naming, no em dashes, narration comments kept); agents never commit on
tampura-bridge; nobody pushes; never edit their tree under
/root/tampura-work; never stage another writer's hunks
(test_full_pipeline.py holds another session's 13-line Phase-1 hunk,
unstaged); every episode run under the lock; data logged in
DATA_LEDGER.md and garbage deleted by the session that made it.
