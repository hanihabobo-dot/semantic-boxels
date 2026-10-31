# BF#59 review: hold_physics

Reviewer: the adversarial reviewer of proposals/hold_physics.md (44 kB,
sections 1 to 4 and the work log, items 1 to 23), written 2026-10-31 at
0c6b6e8 (code as 92d1e06 plus the campaign's plumbing). Read: BRIEF.md,
STATE.md, reviews/REVIEW_BRIEF.md, the four proposals, every out/*.json of
probes/hold_physics (summarised again with its own show.py, sink.py,
offcentre.py, fingers_trace.py), the three episode runs, BF#53's merged
results.jsonl, and the code named below. No episode was run, no tracked
file and no proposal was edited, nothing was committed. Numbers are
"lost/grips" from the probe files; brackets are Wilson 95 %; Fisher tests
are two-sided unless said.

## 0. Verdicts

| fix | mechanism supported | rules | detectable | own-scene risk | effort h | verdict |
|---|---|---|---|---|---|---|
| finger_gear | yes as kinematics (off-centre 4.0 mm median to 0.00 mm, 113 holds); no effect on any loss rate (die 15/113 alone, 0/113 with or without it inside the combination; 0.5 kg cube 0/57 against 2/57, p = 0.50) | pass (both URDFs declare the mimic: theirs line 356, pybullet_data's line 323); 4 allowlist lines, not 2 | not on loss; only kinematically (q1 - q2) | low; it is what keeps places and stacks centred under a force hold | 1.5 | merge with force_hold |
| solver_iters | yes: a firm grip on the 5.2 g body is expelled at 50 iterations and held at 100 to 500; cured equally by mass x10 or inertia x10; same on a sharp box | pass (no tracked code and nothing in their tree sets it; it becomes a declared D9 departure); misses boxel_env.reset() | null on loss alone (21/113 against 20/113); cost measurable on exec_s | medium: every contact of every scene, settle and pushes unmeasured; +0.9 ms per step | 1 (+0.5 for reset and the D9 note) | implement, own switch and arm; force_hold requires it |
| force_hold | yes, strongest probe effect of the campaign: die 0/113 [0, 3.3] against 20/113, cubes 0/57 against 33/57 and 26/57, cups 0/57 | pass: one pipeline-wide value set by our heaviest class, not by the die; model side; senses only | yes: needs at most 4 lost of about 60 carries (6.7 %) against base's 13/60 | medium, unmeasured where it matters: tall 0.5 kg occluders, stacks, the edge pinch, yaw beyond 10 deg, the hold from the touch | 3 | implement (with the gear folded in) |
| pad_rolling | yes at the light hold: 5/113 = 4.4 % [1.9, 9.9] against 20/113 (p = 0.002) | pass narrowly: pipeline-wide; only the number is theirs (their table, not their pads) | yes if it transfers (about 3 of 60) | low; no help for cubes (29/57 against 33/57) | 1 | implement as the fallback; arm only if force_hold fails |

## 1. Per fix

### finger_gear

1. Mechanism. Measured: with each finger force-limited on its own, the
   pair and the held body slide along the pinch axis until one finger
   reaches its target. sink.py on the probe files: off-centre at home
   |q1 - q2| / 2 median 4.00 mm (iters200_force20, die, 113 held) and
   3.86 mm (iters200_force10, 0.5 kg cube, 55 held); max 6.42 mm for the
   die at 20 N; with the gear 0.00 mm median, 0.14 mm max
   (gear_iters200_force10 and _force20, die and cube). Episode s1_f20_i200 (no gear, 20 N, 200
   iterations): off-centre 2.46 mm median, 5.32 mm max over 429 carry
   steps; the gear episodes s6 and s1: 0.006 and 0.008 mm max
   (offcentre.py, rerun by me, same numbers). gear_test.py: gearRatio -1
   holds q2 = q1 within 0.01 mm; my own check (reset_check.py, section 4)
   drove finger 1 alone at 10 N to 10 mm and read q2 = 9.999 mm. What the
   gear does NOT do: it changes no loss rate. Gear alone: die 15/113
   (13.3 %) against base 20/113 (p = 0.46),
   cubes 33/57 and 31/57 against 33/57 and 26/57, cup a 3/57 against 3/57.
   Inside the combination: die 0/113 with the gear and 0/113 without it
   (D_iters200_force10 and F_iters200_force10), 0.5 kg cube 0/57 against
   2/57 (p = 0.50), 0.1 kg cube and cups 0 either way. So the proposal's
   reason for the dependency, "force_hold is harmful alone (96 % lost at
   50 iterations without the gear)", is the solver's number, not the
   gear's: with the gear at 50 iterations the 10 N hold still loses
   103/113 (91.2 %). The gear's real job is geometric: a body held 4 mm
   off the hand's axis is placed 4 mm off (below).
2. Rules. Rule 1: the robot model of the executing world, model side.
   Rule 2: TAMPURA-matched in the only sense available, their URDF
   (`panda.urdf` line 356, `<mimic joint="panda_finger_joint1"/>`) and
   pybullet_data's (line 323, the same tag, read by reset_check.py), and
   the real hand drives both fingers from one motor; their kinematic carry
   never exercises it, so there is no measured TAMPURA behaviour to match,
   only the declared kinematics. Pipeline-wide: both worlds. Rule 3: no
   reads. Rule 4: one switch, but see the verdict. Gates: d9_setup runs in
   phase 'setup' (policy.py 189 to 192), where gate_hooks lets body writes
   and body-less writes pass (gate_hooks.py 211), so createConstraint and
   changeConstraint do not trip G14 at run time; after set_phase('main')
   they would, so the gear must never be created lazily. The static gate
   lists both names (bridge_gates.py 83): the change needs four reviewed
   allowlist lines (d9_setup's two, class "D9 set-up"; boxel_env's two,
   "unreachable on the bridge path"), the proposal says two. Scoring:
   scoring.held_body (scoring.py 39 to 43) refuses a held body that sits in
   a constraint; the gear's parent and child are the robot, so the die
   passes, and both gear episodes scored reward 1.0.
3. Testability. No loss effect to detect; its falsifier is kinematic
   (|q1 - q2| <= 0.05 mm in every carry) and belongs in a unit test and in
   the force_hold arm's per-carry log, not in its own cluster arm.
4. Risk. Our scenes: none measured alone (cubes and cups unchanged).
   Under a force hold it is the thing that keeps places centred:
   execute_stack places the hand, not the body (execution.py 1665 to 1669,
   contact_ee = the support centre + the grasp offset), so a body held
   4 mm off centre lands 4 mm off. The constraint's parameters: maxForce
   50 N is five times the 10 N hold budget, so the gear wins every
   imbalance of the hold; during the 60 N close it can be overpowered by
   10 N if one finger is blocked (both fingers get the same target, so
   this needs a body pinned on one side), erp 0.1 gives a soft correction,
   which measured 0.006 mm in the episodes. Lifetime: the bridge runs one
   episode per process (tools/slip_eval.py 161) and d9_setup per episode,
   so the gear exists once per world; our world builds it in _setup_scene
   after the robot load, so boxel_env.reset() (2000 to 2009, no caller
   today) rebuilds it with the robot. Which client: only the executing
   client steps (stepSimulation calls: boxel_env 959 and 1987 on
   client_id, robot_utils and execution on the executing client); the plan
   twin and the kin stream never step, and IK ignores constraints, so the
   plan client needs no gear. The seed-6 grip-verification miss the
   proposal leaves open (its section 3, item 2) is answered by its own
   log: console_debug.log of s6_gear_f10_i200 line 376, "pick arrival
   e_cups_ud: ee_xy_err=0.04mm ee_vs_obj_xy=105.18mm": the hand arrived
   105 mm from the cup, a pick aimed at a pose the cup no longer had; not
   the gear.
5. Effort. 1.5 h is right (d9_setup after the finger loop 74 to 79,
   boxel_env after 917 to 919, four allowlist lines, a unit test that
   drives finger 1 and reads q2).
6. Verdict: merge with force_hold. The gear has no effect of its own on
   any loss rate and no cost; its whole value is the centring of a
   force-limited pair, which exists only when force_hold is on, so one
   switch (the force-limited hold of coupled fingers, which is the real
   hand's grasp) carries both.

### solver_iters

1. Mechanism. Measured (sweeps A, C, D, F; 113 grips per row, the same
   draws): a 10 N force hold loses 108/113 at 50 iterations, 0/113 at 100,
   200, 300 and 500; 20 N loses 102/113 at 100 and 0/113 at 200; 60 N
   loses 111/113 at 200; the 10 N hold at 50 iterations loses 0/113 with
   the die's mass x10 and 0/113 with its inertia x10; a sharp box of the
   die's extents and mass loses 111/113 at 10 N (base 43/113). The cure by
   mass, by inertia and by iterations alike is good evidence for a
   projected Gauss-Seidel convergence problem of a light body between two
   heavy fingers; the solver itself was not inspected, as the proposal
   says. A second sign the operating point matters, not in the proposal:
   the held dice turn in the hand by a median 29.8 deg at 100 iterations
   and 10 N, 5.4 deg at 200 and 10 N, 19.3 deg at 200 and 20 N, 3.9 deg at
   500 and 10 N; at the edge of convergence the die is held but moves. The
   iterations alone do nothing for the light hold: 21/113 at 200 (18.6 %
   [12.5, 26.7]) and 18/113 at 500 against 20/113; the resting pad force
   rises from 2.9 to 11.4 and 27 N while the carries with a zero-force
   step stay at 106 of 113 (104 of 113 at base). Counts match the
   proposal. The proposal does not cite BF#35 (PAPER_AUDIT.txt 7398):
   that informal probe ran 200 iterations at 60 N and 3 mm and held about
   0 of 4, which agrees with "the iterations needed grow with the force"
   (iters500_sq3 lost 5/113) and should be cited.
2. Rules. Rule 1: a simulation setting of the executing world, like D9's
   timestep; no plan touched. Rule 2: root-cause (convergence) and
   pipeline-wide. Nothing else sets it: no tracked pipeline module calls
   setPhysicsEngineParameter (grep; only tools/_probe_q14_grip.py,
   tools/_probe_grip_transport.py and tools/_probe_b1_tampura.py do, as
   probe levers), and their tree sets nothing (read-only grep of
   /root/tampura-work/tampura and tampura_environments: no
   numSolverIterations, no setPhysicsEngineParameter), so their world and
   ours run PyBullet's 50. The planner's twin and the kin stream never
   step (above), so the executing client is the only place in the bridge
   and BoxelTestEnv.client_id the only place in our world. Gap: the
   proposal puts our world's setting after setGravity at 556, but
   boxel_env.reset() calls resetSimulation again (2001), and
   resetSimulation sets numSolverIterations back to 50 (measured,
   reset_check.py: 200 before, 50 after); put it in _setup_scene or after
   both setGravity calls (556 and 2002). It is a departure from their
   world that arm T does not share (arm T runs kinematically at 50), so
   the D9 disclosure and the paper's set-up text must name it. Rule 4:
   fine. Allowlist: two lines (d9_setup, boxel_env), three with reset().
3. Testability. Predicted null on the loss; the arm exists to measure the
   cost and the side effects. The cost, from the proposal's own T files:
   the same 28 picks and carries took 25.1 / 46.9 / 52.0 s at 50 / 200 /
   500 iterations, a factor 1.87 on the probe's stepping at 200; 500 costs
   only 11 % more than 200, so the solver stops before the cap on many
   steps and the episode's cost depends on its contact load (unknown). The
   eval does not record steps; exec_s does: seed 0 is the same scene on
   both machines, 3765 steps in dispatch on the laptop (s0_r1) and exec_s
   3.81 s on the cluster, about 1.0 ms per step, so the extra time is at
   most about 0.9 x exec_s. BF#53 (192 episodes): exec_s median 14.1 s,
   p90 84.9 s, max 203.5 s; mean 25.3 s (base arm 23.4 s); wall median
   53.8 s, mean 111.8 s. Upper bounds: +13 s on the median episode (+24 %
   of its wall, so the proposal's own falsifier "wall median more than
   20 % over base" can trip on the cost alone; it should be a budget
   instead: exec_s per seed at most 2x base's, and at most 2 of 60
   episodes newly capped), +76 s at the exec p90, +77 to +184 s of the
   600 s budget in the 18 capped episodes (exec 85 to 204 s: at about
   1 ms per step the capped episodes run roughly 85k to 204k steps, not
   the laptop's 43k, so the proposal's
   "+39 s" is low by a factor 2 to 5). Capped episodes fail either way;
   they lose plan cycles. Two BF#53 episodes finished within 40 s of the
   cap (base seed 19 at 560.5 s, exec 94 s; arm 2 seed 6 at 563.1 s, exec
   107 s) and would cross it: about 1 % of episodes, 0 or 1 per arm.
   Planning is untouched (the twin never steps). Per arm of 60 episodes:
   base about 2.0 h serial (BF#53 base mean wall 119 s), solver_iters
   about +21 min (2.3 h) at the upper bound.
4. Risk. Every contact of every scene converges further: the settle at
   main()'s start (D9 (5), the after_settle disclosure and
   settle_max_dxy_m), cup pushes, stacks. The proposal measured cups and
   cubes in the carry only; read settle_max_dxy_m and G4 on the arm.
5. Effort. 1 h plus 0.5 h for reset() and the D9 note; line numbers
   (policy.py 68, boxel_env 556) are right.
6. Verdict: implement, as its own switch with its own arm. It is the cost
   and the side-effect carrier of the hold fix, null on the loss by its
   own data, and the force_hold arm's effect is read against it; force_hold
   must refuse to run without it.

### force_hold

1. Mechanism. Measured: base's 0.5 mm position hold has a pad at 0.00 N
   at some step in 104 of 113 carries (the proposal's 33 of 38 came from a
   deleted 40-trial file; the 113-grip file agrees), and the summed force
   at home spreads 1 to 8 N. With the gear, 200 iterations and 10 N: die
   0/113 [0, 3.3], 0.5 kg cube 0/57 [0, 6.3], 0.1 kg cube 0/57, cup a
   0/57; without the gear 0/113, 2/57, 0/57, 0/57 and cup c 0/57. Every
   number in sections 1.1 and 2.3 matches its file. Two corrections. (a)
   The force hold does not remove the zero-force steps: 48 of the 113 held
   carries of gear_iters200_force10 still have a pad at 0.00 N at some
   step (43 of 113 without the gear), and the seed-6 episode dipped to
   0.0 N in three pairs. What changes is the recovery: a force-limited
   finger follows the body into the gap a junction kick opens, a
   position-held finger at its target does not. So "the force collapses to
   0 N" is the base's symptom, not the discriminator; the discriminator is
   whether the pads close back in. (b) The fingers follow the body: held
   carries widen by 0.76 mm median and 1.26 mm max (113), against 0.026 /
   0.121 mm at base. The claim "loss grows with the time in the hand"
   (speed0.5: 40/113 = 35.4 % [27.2, 44.6] against 20/113, p = 0.004) is
   measured in this probe, but carry_motion's batch 1 slowed the same way
   lost 14/114 against 18/114 (no rise), and with rolling resisted the
   speed stops mattering (droll0.01 4/113 at both speeds). The reconciled
   reading: the light hold loses dice by two routes, a time-proportional
   creep of the rounded hull in the low-force windows (this probe's
   off-face draws, the speed and rolling levers, carry_motion's 6 of 95
   extra losses in 2 s at home) and the wrist spin's walk around few
   contact points with the junction kick as release (carry_motion,
   loss_dynamics). Both need a hold that cannot close back in. The probe
   draws the grasp yaw uniform in +-90 deg (hp_probe.py 205), so its
   carries mix long and short wrist unwinds, and the force hold held all
   113: the wrist spin does not defeat a converged 10 N hold.
2. Rules. Rule 1: an executor primitive (the hold law of
   close_gripper_until_contact). Rule 3: the hold uses the close's tactile
   test and the joint readback only. Rule 4: one switch. Rule 2, the
   numbers against our own scenes:
   - It is not a raise of the grip for find_dice. The summed pad force at
     home goes from 2.9 to 19.8 N for the die but from 39.9 to 20.9 N for
     the 0.5 kg cube and from 22.1 to 20.3 N for the 0.1 kg cube (probe
     nf_home medians): the force hold replaces a force set by stiffness
     and the close's sub-millimetre stop with a set force, lower than
     today for our boxes.
   - What decides 10 N, without the die: the smallest tested force that
     carries the heaviest class of any scene through the pipeline's carry.
     The die does not need it (5 N with 200 iterations: 0/113); our
     0.5 kg class does (5 N: 13/57 with the gear, 27/57 without; 10 N:
     0/57 with the gear, 2/57 without; 20 N: 0/57). The upper side is the
     solver: 20 N is held but at the edge of convergence (100 iterations
     102/113 lost; 200 iterations held dice turned 18 to 19 deg median
     against 4 to 5 deg at 10 N; the episode below), 60 N fails at 200. So
     10 N is one pipeline-wide value, bracketed by our heaviest class
     below and by convergence above, and inside the Franka hand's 70 N.
     A class value (force by size or mass) would need a mass belief the
     pipeline does not have and a body-class reason; one value works for
     every body tested, so no class value. 20 N is not the better
     pipeline-wide value: it buys margin on the 0.5 kg class that 10 N
     already shows at 0/57, and spends the solver margin.
   - The 0/57 for the 0.5 kg class is thin: upper bound 6.3 %, 2/57
     without the gear, and the class in our scenes is not a 40 mm cube.
     boxel_env's 0.5 kg bodies are occluders 50 to 60 mm wide and 100 to
     150 mm tall (337 to 338, 194 to 199) and 60 to 70 mm cylinders (226
     to 231). A tall box pinched near its top under a hold that is half
     today's force (20.9 against 39.9 N summed) carries a gravity and
     swing torque about the pinch axis the cube never tested. Untested,
     and it is the case rule 2 is about.
   - Stacks: the descent goes to a contact height from the estimated boxes
     (execution.py 1662 to 1663); an estimate a millimetre low pushes the
     held cube into the tower until it slips in the pads, at 2 x 1.2 x
     10 = 24 N under force_hold against about 48 N (0.5 kg) and 26 N
     (0.1 kg) under today's hold: no harder than today. The release:
     open_gripper commands 0.04 m at 200 N per finger (robot_utils.py 1059
     to 1065), which replaces the 4 mm-inside target outright; nothing of
     the hold survives the open, and the release verify reads fingers
     >= 0.038 (execution.py 648) as now. Place precision: with the gear
     the body stays on the hand's axis (0.00 mm), without it 3.9 to 4.0 mm
     median off: the gear is part of this fix.
   - Narrow bodies: the target is max(0, w - 4 mm) and the width
     plausibility refuses half-widths under 5 mm (execution.py 1280), so
     every accepted hold has a target of 1 mm or more; the hold runs before
     that check (inside the close), so a phantom (tips on the top) gets the
     hold for its 60 steps at 10 N instead of 60 N, then the open. Nothing
     in our scenes is narrower than 30 mm; the die's target is 6.3 mm.
   The reads under the force hold, checked in the code:
   - the grip verification (execution.py 1235 to 1264): link identity of
     getContactPoints(robot, obj) on the pads, no distance or force
     threshold; it sees both pads, the logged pad_normal_force rises to
     about 20 N;
   - the width plausibility (1276 to 1290) reads measured_half, the width
     close_gripper_until_contact returns at the touch (1181), before the
     hold; unchanged; it only falls back to the finger readback when the
     close returned None, where no hold runs;
   - the post-lift re-verify (1331 to 1344): link identity only;
     unchanged;
   - _verify_holding (test_full_pipeline.py 299 to 310, the 0.5 N floor
     at 308): summed force at home 19.8 N median (113), so the
     0.42 N failure case of the eval cannot recur at rest; scoring's
     held_body uses the same rule (scoring.py 26 to 44);
   - a body that leaves the hand lets the fingers close to w - 4 mm:
     4 mm per finger of proprioceptive signal.
3. Testability. Against base's 13 of 60 carries (21.7 %), the force_hold
   arm must lose at most 4 of 60 (6.7 %, Fisher two-sided p = 0.034;
   5 of 60 gives 0.071) or 3 of 54 if only 54 episodes reach the die; one
   sided, 5 of 60. Pooled against the base arm of every job (36 of 174 in
   BF#53), 6 of 60 is enough one-sided (p = 0.043). The proposal's "under
   10 %, at most 17 of about 174 carries" counts carries the arm will not
   have: with 60 episodes, 6 of 60 (10 %) is not significant against a
   paired base (p = 0.13). The claimed effect (0/113 in the probe, 3 of 3
   episodes) clears the threshold by a wide margin if it transfers.
   Falsifier: more than 4 die carries of 60 lost with links none or a
   graze; or a grip-verification or post-lift failure rate per pick above
   base's; or a G4 place error or a stack failure on our scenes that base
   does not have. Log per carry so a null is readable: the hold mode and
   force, the measured width, the target, |q1 - q2| max, the sink
   2w - q1 - q2 max during the LIFT and during the carry (see the
   unexplained reading), the pad force minimum and at home, and the
   number of zero-force steps.
   The unexplained reading (s1_f20_i200, no gear, 20 N): fingers_trace.py
   shows it plainly. The 60-step position hold leaves the fingers at 9.88
   mm; at step 299 the 20 N hold starts and over the lift (steps 299 to
   350) both fingers close together to 6.51 / 6.51 mm (target 6.35 mm)
   while the pad contacts stay at x = +-9.3 mm in the die frame and the
   pads read 15 to 17 N, under the 20 N budget. The pads moved 3.4 mm per
   side into a body that did not get narrower: an unresolved contact, the
   pads inside the hull. In the carry the slosh then re-opens them to a
   23 to 24 mm sum. In the same scene with the gear and 10 N (s1_gear) the
   fingers instead open from 9.85 to 10.69 mm and the pads read 9.99 N
   each; s6_gear the same (10.26 to 10.67 mm, 9.6 / 10.0 N). So: (i) it
   does not touch the pick's measured-width logic, which reads the width
   at the touch before any hold, and every later check is contact-based;
   (ii) it does undermine the sink model's claim "the pads do not dig in",
   because sink.py reads the sink at home after the carry, and offcentre.py
   against the post-lift width, both of which hide a lift-phase sink;
   (iii) it supports the convergence diagnosis and the choice of 10 N:
   at 20 N and 200 iterations the probe's "held" (both pads, >= 0.5 N)
   accepts a die the pads have passed into, so a 0 % at 20 N is not
   evidence of a physical hold. Gear and force are confounded in this one
   episode (no gear + 10 N or gear + 20 N episode exists).
4. Risk. Our scenes: the probe improves cubes and cups, but only in the
   carry; untested: the 0.5 kg tall occluders and cylinders, stacks and
   places with a pressed body, yaw beyond +-10 deg, the edge pinch, and
   (implementation) the hold started at the touch: the probe and all three
   episodes applied the force hold after the close's 60-step 0.5 mm
   position hold at 60 N, and the proposed change replaces those 60 steps.
   Gates: new motor commands only, inside the dispatched pick (G3 passes;
   motor commands are not static G1 names). Replan loop: no new refusal
   (the verification rules are unchanged), so no push into the cup loop.
   Time: none of its own; it runs only with solver_iters' cost.
5. Effort. 2.5 h is low by half an hour once the gear (above), the guard
   that refuses force_hold without solver_iters, the run-header line and
   the per-carry log fields are in: 3 h. Line numbers check: robot_utils
   1135 to 1194, 1177, 1180 to 1191; execution 1235 to 1290, 1325 to
   1344, 553; test_full_pipeline 242 (the floor is at 308, not 310).
6. Verdict: implement, with the finger gear inside the same switch and a
   hard requirement on solver_iters. It is the one fix of the campaign
   whose probe removes the loss for every body tested (0/113 and 0/57),
   it passes rule 2 because the force is set by our heaviest class and
   lowers today's grip on our boxes, and the eval can detect it with 60
   carries.

### pad_rolling

1. Mechanism. Measured: pad rolling 0.001 / 0.01 / 0.1 lose 16 / 5 / 1 of
   113 (14.2, 4.4 [1.9, 9.9], 0.9 %); die rolling 0.003 / 0.01 / 0.1 lose
   11 / 4 / 4; their table's triple on the die 4/113; held carries' minimum
   pad force rises from 0.00 to 0.69 N median with die rolling 0.01. The
   combination rule (combine_test.py: a_rolling x b_lateral + a_lateral x
   b_rolling) is Bullet's btManifoldResult rule; with it today's combined
   rolling at the pads is 0. Speed no longer matters once rolling is
   resisted (4/113 at full and half speed). It does not help a firm or
   yawed grip: cubes 29/57 and 23/57 against 33/57 and 26/57; at 10 N and
   50 iterations 89/113.
2. Rules. Rule 1 and 3: fine. Rule 2: pipeline-wide (both worlds' pads);
   "TAMPURA-matched" is weaker than stated: their create_default_env sets
   rollingFriction 0.01 on the table only (panda_env_utils.py 734 to 741,
   read only), not on the pads, and their die has none; the number is
   theirs, the placement is ours. The defensible reason is root-cause: a
   point contact on a rounded hull has no rolling resistance, which a pad's
   contact patch has. It raises a friction after an eval failure, so it
   needs that reason written down, not the citation alone.
3. Testability. Predicted about 3 of 60 carries against 13 of 60: inside
   the 4 of 60 threshold if it transfers. With force_hold on it adds
   nothing (0/113 either way, item 14), so it is not a member of a
   combined set that holds force_hold.
4. Risk. Low: rolling resistance acts only on rolling relative motion at
   a pad; releases and closes unchanged; no cube gain.
5. Effort. 1 h (d9_setup 75 to 77, boxel_env 918 to 919, no new pybullet
   name: changeDynamics lines already allowlisted, their text changes).
6. Verdict: implement as the fallback. It is cheap and supported on the
   light hold, but force_hold covers it; run its arm only if the
   force_hold arm fails its acceptance.

## 2. Cross-proposal conflicts and combinations

Switches and arms for this proposal. Two switches, not three and not one:
`solver_iters` (the setting in d9_setup and boxel_env) and `force_hold`
(the hold law in close_gripper_until_contact plus the finger gear in
d9_setup and boxel_env). force_hold raises at configure time, or at the
run header, when solver_iters is off (10 N at 50 iterations loses 108/113:
a forgotten switch would waste an arm), and the arm spec spells both names
(`solver_iters,force_hold`) so slip_fixes.spec() records what ran; no
hidden implication in the registry. Not one switch, because the
iterations' cost and their side effects on every contact must be read on
their own arm against base, and the force_hold arm's effect is read
against that arm. Not a base with the gear and the iterations on, because
it changes the campaign's base (92d1e06) for every other proposal's arm,
whose probes all ran at 50 iterations. Cluster arms: base, solver_iters,
solver_iters+force_hold in one job: about 2.0 h, 2.3 h and 2.3 h serial
for 60 episodes each (BF#53 base mean wall 119 s; the iterations add at
most 0.9 x exec_s, mean 21 s; the 600 s cap costs capped seeds plan cycles,
not outcomes, and may push 0 or 1 near-cap episode per arm over). If the
orchestrator keeps three switches, the gear gets no cluster arm (null on
every loss, no cost), only a unit test and the per-carry |q1 - q2| log.

Same mechanism, or covered by force_hold if it lands:
- pad_rolling (this proposal): the light hold's low-force windows; covered.
- edge_pinch, face_needs_wrist_yaw, pinch_band_certificate
  (grasp_geometry): they move dice into the yaw band where the light hold
  survives; the force hold held 113/113 over +-10 deg off face, so they
  become redundant for the die. The force hold was not probed at the edge
  pinch (delta 45, measured half-width 12.3 mm, target 8.3 mm on two
  rounded vertical edges) nor at 15 to 20 deg: do not combine edge_pinch
  with force_hold without that row. edge_pinch's rule-2 problem (a size
  scope that reaches only the die) remains.
- grasp_wrist_home (carry_motion): the long wrist unwind walks a light
  pinch; this probe's carries mix long and short unwinds and the force
  hold held all of them. It becomes a time and joint-limit improvement
  (carry_motion: 406 to 360 steps per carry), not a loss fix, and it keeps
  its interplay with the cup radius loop (seed 6). Lower priority.

Complementary:
- carry_trapezoid (= carry_accel_limit, one switch): the junction kicks
  set the lower bound of the hold force (0.5 kg cube: 5 N 13/57 to 27/57
  lost; 48 of 113 held force-hold carries still dip to 0 N, most likely at
  junctions); removing them widens the 10 N margin for our heavy class and
  the place precision. Unknown and worth a probe row before the combined
  arm: under today's hold carry_motion found wrap + trap worse than wrap +
  pipe (64/92 against 85/92 at 3 deg), unexplained.
- carry_hold_check (loss_dynamics): the safety net for any residual loss;
  its rule (both pads, >= 0.5 N) works under the force hold (about 20 N at
  rest) provided it reads after the move and the home hold, as proposed,
  never per step (zero-force steps mid-carry are normal under both holds).
- pose_radius_keep (loss_dynamics): independent; it removes the cup-loop
  tail where the iterations' cost lands most; it belongs in the combined
  arm.

Interference:
- carry_grip_watch (loss_dynamics): its 0.05 mm widening threshold is
  exceeded by held carries under the force hold (0.76 mm median, 1.26 mm
  max, 113), so it would fire on nearly every carry; under the force hold
  a loss shows as the fingers closing toward w - 4 mm instead. Do not
  combine as written; if force_hold lands, drop it (the closure is
  carry_hold_check's signal).
- loss_dynamics' carry_grip predictor line: the widen field changes
  meaning under the force hold; log the hold mode with it.
- edge_pinch changes the width the hold measures (12.3 mm), and the target
  with it; see above.

Order of arms (each job is base plus two):
1. base, solver_iters, solver_iters+force_hold.
2. base, carry_trapezoid, pose_radius_keep.
3. base, grasp_wrist_home+carry_trapezoid (with pose_radius_keep, as
   carry_motion requires), carry_hold_check.
4. Only if force_hold fails its acceptance: base, pad_rolling, edge_pinch.
5. The combined arm solver_iters+force_hold+carry_trapezoid+
   pose_radius_keep+carry_hold_check, with TAMPURA on the same seeds.

## 3. Missed, and what to check first

Missed by the proposal:
- boxel_env.reset() (2000 to 2009) calls resetSimulation, which sets
  numSolverIterations back to 50 (measured); the proposal's 556 alone
  leaves a reset world at 50.
- The hold from the touch: the probe and the episodes ran the force hold
  after the 60-step position hold; the change replaces it. Not measured.
- Our 0.5 kg class is tall: 50 to 60 mm wide, 100 to 150 mm tall boxes and
  60 to 70 mm cylinders, held near the top at about half today's force.
- The lift-phase sink: only the at-home sink was measured; s1_f20_i200
  had 3.4 mm per side during the lift.
- The force hold at the edge pinch and beyond 10 deg off face.
- BF#35's 200-iteration row (PAPER_AUDIT.txt 7398) is consistent and
  uncited.
- The settle and pushes under 200 iterations (D9 (5), settle_max_dxy_m),
  and the D9 disclosure of the setting (arm T stays at 50).
- Allowlist counts: finger_gear four lines, solver_iters two or three.
- The time cost on the capped seeds is +77 to +184 s of their budget, not
  +39 s; the "under 10 % of about 174 carries" threshold uses carries the
  arm does not have.
- The seed-6 miss is answered by its own log (the hand 105 mm from the
  cup), not open.

One hour, physics only, hp_probe.py with its existing levers plus three
small additions (no episode):
1. (15 min) A `hold_at_touch` option: the force hold replaces the close's
   60-step position hold; rerun gear_iters200_force10 on the die (120
   trials) and the 0.5 kg cube (60).
2. (15 min) BODY rows for our real 0.5 kg occluders: a 60 x 60 x 150 mm
   box and a 60 mm cylinder, 0.5 kg, gear_iters200_force10 and base, 60
   trials each.
3. (10 min) The die at 20 deg off face and at the edge pinch (delta 45),
   gear_iters200_force10, 120 trials each.
4. (10 min) Log the sink 2w - q1 - q2 per step during the lift and take
   its maximum per trial; flag any trial over 2 mm in the rows above.
5. (10 min) force_hold with carry_motion's trap executor on the die and
   the 0.5 kg cube, 120 and 60 trials.

## 4. Data generated and deleted

Generated by this review under
`archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/reviews/hold_physics_probe/`:
check.py (3,982 B: summaries of the proposal's out/*.json and of BF#53's
merged results.jsonl, Fisher thresholds), reset_check.py (2,065 B: the
resetSimulation and gear check on a bare Panda, about 2 s), fisher.py
(740 B: two-sided Fisher tests): 3 files, 6,787 B, no outputs written to
disk (the numbers above are their console output). All three deleted by
path at the end of the review, with the folder; nothing else was created.
This file (reviews/hold_physics.md) is the deliverable and stays.

The proposal's own data (section 4) checks out: probes/hold_physics holds
241 files, 16,493,819 B; out/ 167 json files, 11,517,527 B; no .log left.
Recommendation for the ledger: keep the scripts, the three runs'
carry.jsonl and stdout.txt, and the out/*.json of sweeps A, D, E, F, Fc, G
and G_<body> until implementation review (they are the rows behind every
number here, most of the 11.5 MB of out/); the three runs' save/ folders
(about 3.4 MB: 1.21, 0.69 and 1.47 MB by the proposal's run totals less
carry.jsonl and stdout.txt) are garbage now that item 22 and this review
have read them, except s6_gear_f10_i200's console_debug.log, which holds
the seed-6 miss quoted in section 1.
