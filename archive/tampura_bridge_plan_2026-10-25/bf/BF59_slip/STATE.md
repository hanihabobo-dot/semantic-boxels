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

## Rules that bind every change

BRIEF.md section 5 (model side, pipeline-wide or TAMPURA-matched, no
executing-world pose reads feeding control, a switch default off, honest
naming, no em dashes, narration comments kept); agents never commit on
tampura-bridge; nobody pushes; never edit their tree under
/root/tampura-work; never stage another writer's hunks
(test_full_pipeline.py holds another session's 13-line Phase-1 hunk,
unstaged); every episode run under the lock; data logged in
DATA_LEDGER.md and garbage deleted by the session that made it.
