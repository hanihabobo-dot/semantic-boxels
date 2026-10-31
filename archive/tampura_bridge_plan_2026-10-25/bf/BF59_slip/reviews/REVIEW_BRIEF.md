# BF#59 review brief (phase 4): one adversarial reviewer per proposal

Written 2026-10-31 16:40 by the orchestrating session. Read in this order:
BRIEF.md (the problem, the rules in section 5, how a fix is judged in
section 6), STATE.md (where the campaign stands, the diagnosis so far),
YOUR proposal, then the other three proposals (the context for section 2
of your review). The evidence files are under evidence/, every agent's
probe scripts, work logs and outputs under probes/<angle>/ (read only).
The code is the checkout at d021dad: unchanged since 92d1e06 (the brief's
line numbers) except the campaign's own plumbing (slip_fixes.py, the
--slip-fixes flag in run_logger.py, main() and the bridge driver,
tools/slip_eval.py, tools/slip_check.sh).

## 1. Your task: review ONE proposal, adversarially

You are not the author's friend. The campaign will spend cluster time on
every fix that survives this review, so a fix that cannot work, cannot be
measured, or breaks a rule must fall here. For EVERY proposed fix answer
these six points, in this order:

1. Mechanism. Is the mechanism the fix addresses supported by the
   evidence? Name the probe, its command, the numbers, the sample sizes
   and the confidence intervals; separate what was measured from what is
   inferred; name the confounds (the probe's world against the pipeline's
   world, the laptop scene against the cluster's, the solver's
   non-determinism, a lever tested only together with another). Where a
   number in the proposal does not match its data file, say so with both
   numbers.
2. Rules. BRIEF.md section 5, rule by rule. Rule 1 (model side: the fix
   lives in the search, the streams, the belief or the executor's
   primitives, never between the planner and the executor). Rule 2 (no
   bridge-only tuning: pipeline-wide, root-cause, or TAMPURA-matched with
   their value cited; our own scenes must not get worse; a size scope or a
   body-class condition needs a reason that is not "the die"). Rule 3 (the
   planner and the executor never read the executing world's truth; the
   cameras, the joint readback and the pad contacts are the senses; a
   getBasePositionAndOrientation or getAABB of a task body that feeds
   control is a G2 violation, print-only diagnostics are allowlisted).
   Rule 4 (one switch, default off, `slip_fixes.on('<name>')`, registered
   at the module's import). Rule 5 (naming and prose). Rules 6 and 7 (git
   and data; check the proposal's section 4 against the probe folder).
3. Testability and power. Which metric the fix moves (loss per die carry,
   success count, wall, planning, plan and step counts) and by how much it
   must move to be real. The campaign's eval runs 3 repetitions of seeds 0
   to 19 per arm, about 60 die carries per arm, base's loss 21 % per carry:
   give the smallest loss rate the eval can tell from base's at 95 % with
   those counts, and say whether the proposal's claimed effect clears it.
   Name the test that would falsify the fix, and what the fix must log so
   that a null result is informative (which carries were affected, what
   the switch decided).
4. Risk. Our own scenes (random-pairs holding and stack goals, 40 mm
   cubes, cups, blocks: what the fix does there, whether the proposal
   measured it), the bridge's gates (`tools/bridge_gates.py static`: a new
   pybullet write or a read of the executing world needs a reviewed line
   in tools/bridge_gates_allowlist.txt), the time budget (the 600 s cap,
   the eval's wall medians), and the replan loop (a fix that refuses more
   picks or grasps can push a seed into the cup loop STATE.md describes).
5. Effort. Hours, and the files and functions it touches; check the line
   numbers against the checkout.
6. Verdict. One of: implement; merge with <fix> (one switch for one
   mechanism); drop. Two sentences of reason.

Then:

- Section 2, cross-proposal conflicts and combinations: which fixes
  address the same mechanism (one switch or two); which need each other
  (carry_motion says the pad-swapped grasp only works with the
  acceleration-bounded schedule, and the flip needs pose_radius_keep;
  hold_physics says the force-limited hold needs the finger coupling and
  the solver iterations); which interfere (a force-limited hold changes
  the finger-width signal that carry_grip_watch reads; an edge pinch
  changes the width the hold measures; a hold that keeps the die changes
  what carry_hold_check would catch); and the order of implementation that
  lets each arm of the eval test one mechanism.
- Section 3, what the proposal missed and what you would check before
  implementing (one hour of work, named).

## 2. How to work

- Write reviews/<angle>.md with the skeleton below at the START and fill
  it as you go; the file is the deliverable and must be complete when you
  stop. Your return value is a summary: one line per fix with its verdict,
  then the combinations you recommend, ten lines in all.
- Read, compute, compare. You may re-run an existing probe script with
  the command its proposal documents to check ONE number (physics-only
  probes need no lock; keep it under ten minutes; outputs under
  reviews/<angle>_probe/, listed with sizes in section 4 of your review,
  deleted by you by path once the number is in the review). No new
  episode runs (the pipeline's temp/ is shared, the lock serialises it,
  and one episode proves little: the per-carry outcome is a coin flip).
- No edits to the proposals, the code, or their tree under
  /root/tampura-work; no git command that changes anything; no commits,
  no pushes; never kill a process that is not yours (Hani may be running
  the GUI).
- Prose: no em dashes anywhere (commas, colons, sentences), never the
  word "faithful", plain confident voice, no marketing words, numbers
  with their sample sizes.
- The environment is BRIEF.md section 4 (WSL, arm O's venv, PYTHONPATH).
  PowerShell on the Windows side; inside `wsl -e bash -lc '...'` never put
  double quotes (they are stripped): write a script file and run it.

## 3. The skeleton of reviews/<angle>.md

    # BF#59 review: <angle>
    ## 0. Verdicts
    | fix | mechanism supported | rules | detectable | own-scene risk | effort h | verdict |
    ## 1. Per fix
    ### <name>  (points 1 to 6, in order)
    ## 2. Cross-proposal conflicts and combinations
    ## 3. Missed, and what to check first
    ## 4. Data generated and deleted

## 4. The state of the four proposals

grasp_geometry.md, loss_dynamics.md and carry_motion.md are complete.
hold_physics.md is being finished by its agent while you work: its work
log (items 1 to 22) holds the findings, and the sections per BRIEF.md
section 7 appear above the log when it is done; re-read the file before
writing your section 2. Its levers: a JOINT_GEAR constraint coupling the
two finger joints (their URDF's `<mimic>` on panda_finger_joint2, which
PyBullet ignores, so the fingers drift apart under a force-limited hold);
a force-limited hold (the fingers' target 4 mm inside the measured width
at a 10 N motor budget, instead of the 0.5 mm position hold at 60 N whose
force collapses to 0 N when the die shifts); 200 solver iterations
instead of 50 (the expulsion under a firm grip is a convergence artefact
of a 5.2 g body between 0.1 kg fingers; the step time doubles); the
rolling friction of their set_dynamics table. Its headline: coupled
fingers with 200 iterations and a 10 N hold lost 0 of 113 dice, 0 of 57
cubes of 0.5 kg and of 0.1 kg and 0 of 57 cups in its probe, and two
laptop episodes (seeds 1 and 6) held the die at home.
