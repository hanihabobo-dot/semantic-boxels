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
4. IN PROGRESS review (started 16:42): the shared brief is
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
5. THEN implementation: one worktree and branch per fix, four Opus agents
   at a time (the house cap), each: the switch, unit tests, `tools/
   slip_check.sh` green, a commit on its slip/<name> branch only (one-line
   subject, no trailer, no push), a report file reviews/impl_<name>.md.
6. THEN implementation review (Opus or Sonnet per branch), fixes applied.
7. THEN the campaign branch `slip-campaign` = tampura-bridge + every fix
   branch merged (the orchestrator merges, fills `slip_fixes.KNOWN` lines
   if a branch forgot its register call), smoke, `tools/cluster/
   push_snapshot.ps1 -CodeOnly`, then on cn-04 one `slip_eval.sbatch` per
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
