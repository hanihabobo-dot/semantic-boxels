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
     harness when it reports. pad_rolling waits for the next free slot.
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
   - carry_trapezoid DONE 20:05: commit b1e2455 on slip/carry_trapezoid
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
     radius loop). IMPLEMENTATION REVIEW 20:15
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
     IMPLEMENTATION REVIEW 20:30 (reviews/implrev_grasp_wrist_home.md,
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
7. IN PROGRESS (from 20:45): the campaign branch is `slip/campaign` in
   the worktree `C:\Users\HaniAlassiriAlhabbou\git\sb-slip-campaign`
   (tools/slip_worktree.ps1 -Name campaign, from tampura-bridge fd36342).
   Merged with `git -c core.autocrlf=false merge --no-edit`:
   slip/solver_iters 5b09e6b, slip/pose_radius_keep 0f0ac8f,
   slip/grasp_wrist_home 506c369 (the one conflict, pose_belief.py's
   import block, resolved by hand: one `import slip_fixes`, both
   registers), slip/carry_trapezoid 7f30fd2; the configure call is in
   policy.py exactly once. The check with the four on (slip_check.sh,
   seed 0, fixes solver_iters,pose_radius_keep,grasp_wrist_home,
   carry_trapezoid; outputs in the worktree's checks/) started 20:47 on
   the loaded laptop (bridge-test flakes possible). Still to merge:
   force_hold (after its jam probe, and its configure hunk is identical
   to solver_iters', so it should merge as one), carry_hold_check (its
   move-action hunk may conflict with carry_trapezoid's call; its loss
   line goes into tools/slip_eval.py's counting). Then the off check,
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
