# BF#59 die-slip campaign: live state (hand-over for any session)

Updated 2026-10-31 15:05 by the orchestrating session. Read BRIEF.md
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
3. IN PROGRESS proposals (four Opus agents, one angle each, files under
   proposals/): grasp_geometry DONE, loss_dynamics DONE, carry_motion DONE
   (15:40), hold_physics RUNNING (relaunched after an API safeguard error;
   resumes its work log; waiting on its own probe runs). Their probes and
   recordings are under probes/<angle>/ (about 170 MB, ledgered; garbage
   after the review except scripts, work logs, the .txt summaries,
   carry.jsonl and stdout.txt).
4. NEXT review: four Opus reviewers, one proposal each, adversarial, all
   four proposals as context, output reviews/<angle>.md (per fix: is the
   mechanism supported by the evidence, rule compliance with BRIEF.md
   section 5 including whether edge_pinch's 25 mm size scope passes rule 2,
   testability, risk to our scenes, effort, verdict implement / merge with
   X / drop; cross-proposal conflicts and combinations). Then the
   orchestrator writes the candidate list (6 to 8 fixes) into this file.
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

Fix names proposed: edge_pinch, face_needs_wrist_yaw,
pinch_band_certificate (grasp_geometry); carry_hold_check,
carry_grip_watch, carry_accel_limit, pose_radius_keep (loss_dynamics);
grasp_wrist_home, carry_trapezoid (= carry_accel_limit, one switch)
(carry_motion); hold_physics pending.

## Rules that bind every change

BRIEF.md section 5 (model side, pipeline-wide or TAMPURA-matched, no
executing-world pose reads feeding control, a switch default off, honest
naming, no em dashes, narration comments kept); agents never commit on
tampura-bridge; nobody pushes; never edit their tree under
/root/tampura-work; never stage another writer's hunks
(test_full_pipeline.py holds another session's 13-line Phase-1 hunk,
unstaged); every episode run under the lock; data logged in
DATA_LEDGER.md and garbage deleted by the session that made it.
