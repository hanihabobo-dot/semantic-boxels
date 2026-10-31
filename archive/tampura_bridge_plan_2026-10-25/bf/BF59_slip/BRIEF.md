# BF#59: the die that slips out of the hand. Campaign brief

Written 2026-10-31 by the orchestrating session at commit 92d1e06 (branch
`tampura-bridge`). Every agent of the campaign reads this first. Line
numbers are as of 92d1e06; re-check before quoting.

## 0. What Hani asked for

"Tackle the problem of the slipping die once and for all. The grasp
samplers really just need to be that good." Phases: proposals, a review of
the proposals, implementation, a review of the implementation, an eval of
every fix on the same seeds (git branches, worktrees, the cluster, in
parallel), a table of every change and whether it performed, the best set
chosen and tested as one version, TAMPURA on the same seeds as the
comparison, times reported, and the variance of the same scene under the
same settings measured (replicated instances chosen at random or by an
entropy rule).

## 1. The problem, in numbers

The task is TAMPURA's find_dice: a Panda in PyBullet must find a 17.8 mm,
5.2 g die hidden under one of several upturned cups and bring it home
(arm at `DEFAULT_ARM_POS`, die between the finger pads). Our arm (arm O,
"the bridge") runs our perception, our PDDLStream planner and our
executor inside their environment, with a physical friction grasp: no
weld, no attachment, the pads hold the die by friction alone.

The per-fix eval of 2026-10-31 (BF#53, 24 seeds x 8 arms, cluster node
cn-102, evidence in `archive/tampura_bridge_plan_2026-10-25/bf/
BF53_eval_cluster/`) is the data set:

- 174 of the 192 episodes picked the die (the rest hit the 600 s cap or
  never reached it). The grip at the pick was verified in every one of
  them: both pads in contact, then a 10 cm lift, then both pads still in
  contact (the post-lift re-verify).
- 36 of those 174 carries (21 %) lost the die on the way home: at the goal
  check "finger-pad contact incomplete: links none", once "pads touch but
  squeeze force 0.42 N < 0.5 N". The die passes the lift and leaves
  during the planned move home or the hold at home. Not one loss happened
  at the pick or at the lift of the die.
- The pick-time numbers do not tell held from lost (evidence/
  tc_4912db9_grip_lines.txt): pad normal force at the pick, held median
  3.07 N (1.15 to 6.14), lost median 3.58 N (1.46 to 7.72); measured
  half-width 10.2 mm in both (the die's half-side is 8.9 mm; the tactile
  close stops 1.3 mm early by its contact threshold); arrival error of the
  end effector against the die under 1 mm in both.
- The outcome is not a function of the seed: seed 1 lost the die under
  arms base and 3 and kept it under the other six; seed 2 lost it under 1,
  2 and 12 and kept it under the rest (the arms differ in the planner's
  search settings and the sense fold, so the plans and the carry paths
  differ, but the pick is the same object in the same scene). Whether the
  SAME plan loses the die twice is unmeasured; the campaign measures it.
- The slow tail of the eval is the same loss: in seeds 5, 10, 17 and 19
  the pipeline picked the die 10 to 41 times, lost it, replanned, picked
  it again (plan_calls up to 80), until the cap.

Hani's own GUI runs tell the same story (BF#44, BF#47): the die picked
cleanly, carried, and gone at home.

## 2. What is already known (read these audit entries, PAPER_AUDIT.txt)

- F8 (line 944): the post-lift grip slip family on our own scenes, 2026-08.
- BF#35 (7364): their carry is kinematic (`enforce_grasp` resets the die's
  pose to the hand at every waypoint; "their die cannot slip"); our carry
  measured informally at 60 N / 3 mm squeeze: 0 of 4 held; 0.5 mm: 4 of 4.
- BF#37 (7507): Hani's decision: our carry stays physical. B9 (running our
  planner on their kinematic executor) is parked, not an option here.
- BF#38 (7528): Q14's pre-registered probe, 96 trials per level: the
  squeeze inside the measured width decides the hold: 3 mm 1/96, 1 mm
  18/96, 0.5 mm 93/96 for the die (the position overdrive at 3 mm drives
  the pads into the 5 g body until it is expelled). At 0.5 mm the grip is
  light: the pad force dips during the carry (median minimum 0.81 N) and
  three dice were lost. Cups and blocks held at every level.
- BF#44 (7781): the squeeze default is 0.5 mm since 2026-10-30
  (`robot_utils.GRIP_SQUEEZE`), pipeline-wide.
- BF#47 (7899): a lost die with two candidate causes not separated: the
  swing home brushed a mis-placed cup (the twin's motion check reads the
  believed pose and ignores the pose radius), or the light squeeze let the
  die slip on the swing.
- BF#48 (7925): the hold detector (both pads, >= 0.5 N) was checked against
  the truth and is right; `tools/_probe_carry_watch.py` carries a body
  home with the pipeline's own motion and prints the detector beside the
  truth every tenth of a second; at 0.5 mm the resting pad force is 1.6 to
  7.6 N and dips to 0.15 to 0.36 N mid-swing.
- BF#45, BF#46 (7806, 7855): the kin stream certifies the contact pose,
  the pinch span reads the box side along the nearest axis (M9 sizing).
- BF#53 (8200 onward): the per-fix eval; MEASURED and RESULT paragraphs.
- PLAN_P4_POSE_GRASP_SAMPLERS.md (repo root, untracked): the design of
  M8 (observation configurations, pose commit), M9 (fitted yaw and
  extents from the segmentation, grasps at the fitted yaw), M10 (pick
  returns). Section 1 holds the seed-0 evidence of the die pick.

Memory rules that bind every change (summarised in section 5).

## 3. The code map (92d1e06)

The pick (executor): `execution.py` `execute_pick` 908 to 1355. The
contact pose: the estimated box top minus 5 mm, never below the pick
floor (`tampura_bridge/task_spec.py` `PICK_CONTACT_FLOOR` 0.0132 m above
the table for their Panda; the die's top is at 17.8 mm, so the grasp
target sits 13.2 to 14 mm up); the horizontal re-aim at the approach
altitude, the vertical descent (`move_robot_smooth(..., settle=True)`),
the pre-grasp aperture (pinch half + pose radius + 8 mm, M8's aperture
rule), the tactile close `robot_utils.close_gripper_until_contact` 1135
(fingers advance 0.5 mm per step at 60 N until both pads report contact
within 0.5 mm, then hold `GRIP_SQUEEZE` = 0.5 mm inside the measured
width for 60 steps), the grip verification (both pads, the width
plausibility), the 10 cm lift `_apply_post_action_lift` 885, the post-lift
re-verify 1325. `PickResult.config` is the read-back configuration after
the lift.

The grasp sampler (planner): `streams.py` `BoxelStreams.sample_grasp` 762:
one top-down grasp per (pinch axis, approach altitude 0.10 / 0.06 m) over
the ESTIMATED box; with M9 (`pose_belief.fitted_grasp_candidates` 177) at
the fitted yaw. `GRASP_MAX_SPAN` 0.076. The kin stream
(`compute_kin_solution`, BF#45) certifies the approach and the contact IK.
The grasp carries no notion of where on the body the pads land, no
quality, no force.

The belief of the die: `pose_belief.py` (pose radius, the fitted yaw and
extents, the commit margin `believed_margin` 209, `pose_known` 233);
`perception.py` (the detections). The die is registered from the overhead
camera once its cup is moved; M8's observe (the wrist camera) refines the
pose.

The carry (dispatcher): `test_full_pipeline.py` main's dispatch loop, the
move action 1815 to 1915: with the held body as cargo the move is re-solved
from the readback (`plan_motion`, RRT-Connect with shortcut smoothing,
`streams.py` STREAM 3 from 893), then every waypoint pair streams through
`robot_utils.move_robot_smooth` 877 (30 steps minimum per pair, stretched
so no joint exceeds its datasheet velocity `JOINT_VELOCITY_LIMITS`, 240 N
m position control, settle only at the last waypoint), and a move to the
goal configuration ends with `hold_at_config` 1001 for up to
`HOME_HOLD_STEP_CAP` 52 steps (TAMPURA's at-home test, allclose 1e-4).
`SIM_TIMESTEP` 1/240 s. The goal check `_verify_holding` 242: the held
body is the die, both pads in contact, summed normal force >= 0.5 N.

The physics of the bridge world: `tampura_bridge/task_spec.py` (D9: class
masses from the YCB table, the die 5.2 g, every task body lateral friction
1.0, pad friction 1.2, finger opening 0.04, gravity and timestep ours) set
by `tampura_bridge/policy.py` `d9_setup` on their world. Their die: the
URDF under their `tampura_environments` tree (WSL `/root/tampura-work/
tampura_environments`), read only.

Probes that exist: `tools/_probe_q14_grip.py` (the 96-trial carry probe,
BF#38), `tools/_probe_carry_watch.py` (`tools/watch_carry.ps1`, the live
detector-against-truth carry), `tools/_probe_grip_transport.py` (BF#35's
informal probe), `tools/_probe_tampura_carry.py` (their carry counted).

Metrics: `tools/episode_metrics.py` reads a run directory (wall, planning,
execution, steps, picks, places, senses, observes, outcome).

## 4. Running things

Everything runs in WSL (Ubuntu) with arm O's venv; PowerShell on the
Windows side drives it:

    wsl -e bash -lc '<command>'

The pipeline from a checkout at `$S` (the main checkout is
`/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels`; a worktree is a
sibling folder under `/mnt/c/Users/HaniAlassiriAlhabbou/git/`, which
keeps `../pddlstream_lib` resolvable):

    S=/mnt/c/Users/HaniAlassiriAlhabbou/git/Semantic_Boxels
    TW=/root/tampura-work
    export PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 TAMPURA_WORK=$TW
    export PYTHONPATH=$S:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:$TW/tampura:$TW/tampura_environments
    PY=/root/armO-venvA/bin/python

Unit tests (cwd = the checkout, 45 to 47 tests, about a minute):

    cd $S && $PY -m pytest tests -q
    cd $TW/tampura_environments && $PY -m pytest -q $S/tampura_bridge/tests

The static gates (must stay PASS; a new pybullet write or a read of the
executing world needs a reviewed line in tools/bridge_gates_allowlist.txt):

    cd $S && $PY tools/bridge_gates.py static

One headless find_dice episode (cwd = their tampura_environments; the
scene a seed loads on the laptop differs from the cluster's for most
seeds, BF#39, so pass --allow-g19-mismatch 1; seed 0 is the same scene
everywhere and takes about 10 s):

    cd $TW/tampura_environments && $PY $S/tampura_bridge/run_bridge_on_finddice.py \
      --global-seed 0 --vis 0 --allow-g19-mismatch 1 --save-dir <out dir>

Episode runs share pddlstream's temp/ under that cwd, so two at once
corrupt each other: EVERY episode run (and every pytest run that plans)
goes through the lock:

    flock /root/sb_pipeline.lock -c '<the command>'

Physics-only probes (no planner, like _probe_q14_grip.py) need no lock.
The laptop has 16 cores and 15 GB; keep a probe under a few minutes and
write its outputs under `archive/tampura_bridge_plan_2026-10-25/bf/
BF59_slip/probes/<your angle>/` (never /tmp, which WSL wipes). Hani may
be running the GUI (tools/watch.ps1) at any time: never kill a process
that is not yours. The cluster is the orchestrator's alone.

## 5. The rules every proposal and every change must satisfy

1. Model side, not plan side. Nothing edits a plan between the planner
   and the executor ("this is cheating"). Fix plan quality in the search,
   the streams, the belief, the executor's primitives, or report as is.
2. No bridge-only tuning. Never raise grip force, squeeze, friction, mass
   or any robot setting only for find_dice after an eval failure.
   Pipeline-wide (every scene and goal), root-cause, or TAMPURA-matched
   (their value, cited) changes only. Our own scenes (random-pairs holding
   and stack goals, 40 mm cubes, cups, blocks) must not get worse.
3. The planner never reads the executing world's truth. Perception
   (cameras), proprioception (joint readback) and tactile contact
   (`getContactPoints` on the pads) are the robot's senses; a
   `getBasePositionAndOrientation` or `getAABB` of a task body that feeds
   control is a G2 violation. Print-only diagnostics are allowed and
   allowlisted.
4. Every behaviour lands behind a switch, default off, named in the
   campaign's registry (the orchestrator provides `slip_fixes.py`; a fix
   checks `slip_fixes.on('<name>')`). The eval switches them on per arm.
5. Honest naming and prose: never "faithful"; no em dashes in any text
   (commas, colons, sentences); keep the existing narration comments;
   plain confident voice; no marketing words.
6. Git: never commit or push in the proposal phase; in the implementation
   phase commit on your own branch only, one-line subjects, no trailers,
   no push. Never touch their tree under /root/tampura-work. Never stage
   another writer's hunks.
7. Data: everything you generate goes under the campaign folder, is
   listed in your report with sizes, and garbage (a failed probe's output
   once the finding is written) is deleted by you.

## 6. How a fix will be judged

Every candidate becomes one switch on one branch `slip/<name>`
(worktree `C:\Users\HaniAlassiriAlhabbou\git\sb-slip-<name>`), merged
into a campaign branch and evaluated on the cluster from one snapshot:

- arms: base (every switch off), each fix alone, later the chosen set
  together; TAMPURA (their planner as shipped) on the same seeds;
- seeds: TAMPURA's 0 to 19 (the campaign's pinned scene map), every seed
  under every arm, seeds the outer loop so one seed's arms run back to
  back;
- replication for variance: a subset of seeds runs three times per arm;
  the subset is chosen by an entropy rule from the per-fix eval (the seeds
  whose outcome was most mixed across arms) plus two drawn at random;
- the base arm runs in every cluster job, so a between-job comparison has
  a within-job control and base's repeats measure the node and time
  variance for free;
- per arm: success count, the loss rate per die carry, wall and planning
  medians, the plan and step counts, and the within-seed disagreement
  rate (variance). A fix "performed" when its loss rate per carry is below
  base's on the paired seeds with the replication's variance in view, and
  nothing else got worse.

So a proposal should say which metric it moves and by how much it would
have to move to be real.

## 7. What a proposal looks like

One markdown file per agent at `archive/tampura_bridge_plan_2026-10-25/
bf/BF59_slip/proposals/<angle>.md` with:

1. Diagnosis: what you established about WHY the die leaves the hand in
   the carry, with evidence (code reading with file:line, probe results
   with the exact command and the numbers, the eval's logs). Separate
   what you measured from what you infer.
2. Proposed fixes, two to four, each with: a short name (lowercase, the
   switch's name), the mechanism it addresses, the exact change (files,
   functions, what the code does with the switch on), why it satisfies
   section 5 (pipeline-wide or TAMPURA-matched; model side), the expected
   effect on the loss rate and on time, the test that would falsify it,
   the risk to our own scenes, and the effort (hours).
3. What you would measure first if you had one more hour.
4. The data you generated (paths, sizes) and what you deleted.

The return value of the agent is a summary: the diagnosis in five lines
and the fix names with one line each.
