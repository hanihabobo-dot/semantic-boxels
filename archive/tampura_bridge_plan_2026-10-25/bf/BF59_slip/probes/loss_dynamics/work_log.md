# BF#59 proposal: loss dynamics (when and how the die leaves, what the model does)

## Work log (replaced by the final sections at the end)

### 2026-10-31, code reading at 92d1e06

- The holding goal ends the loop on the dispatcher's own held state:
  `test_full_pipeline._loop_done` (1437 to 1447) returns True when
  `held_body_id` is the target body and the at-home test passed. Nothing
  between the pick and that test reads the pads again during a move: the
  move branch (1795 to 1960) streams the waypoints, holds at home, runs the
  at-home test and `detect_execution_collisions`, and the only tactile
  checks of a held body are the pick's own post-lift re-verify and
  `execute_place`'s empty-hand check at place entry (EmptyHandError,
  2261 to 2304). A die lost on the move home therefore leaves
  `held_body_id` set, `_loop_done` ends the loop, and the end-of-run
  scorer `_verify_holding` (242, called at 2768) is the first thing that
  notices: exit `physics_mismatch`. The model never learns of the loss and
  never replans after it.
- Measured from the evidence (BF59_slip/evidence/tc_4912db9_loss_context.txt,
  31 loss episodes listed): in every one the die is picked exactly once
  ("I have a firm grip on dice" appears once), carried once, and the
  episode ends at the goal check. The brief's "picked the die 10 to 41
  times" in seeds 5, 10, 17, 19 does not hold: the loop in those seeds is
  an observe and pick alternation on d_cups_ud ("look closer at d_cups_ud,
  pick it up" then "pick up d_cups_ud", repeated 10 to 41 times with no
  "firm grip" line in between), and the die is picked once after the cup
  finally moves. The metrics' `picks` counts every pick action, cups too.
  The slow tail is a cup pick loop (a separate failure), not a die loss loop.

### Episode 1: seed 0, run s0_r1 (held, success)

Command (WSL, under the lock): `bash probes/loss_dynamics/run_episode.sh 0 s0_r1`
(run_probe.py runs the unchanged driver with loss_recorder installed;
`--global-seed 0 --vis 0 --allow-g19-mismatch 1`). Scene 1747173591.670785.json
(the pinned one). Outcome success, goal check ok, 3 plans.

The carry: pick_done at recorder step 351 (post-lift), move(home) re-solved to
9 waypoints, every pair max|dq| 0.42 rad stretched to 39 steps (the arm at
2.54 rad/s, the joint limit, for the whole swing), then the 76-step settle
and a 23-step hold. Pad forces: 2.58 N per pad at the lift, dipping to
0.00 N on one pad (contact points present, force zero) in waypoints 6 and 8,
back to about 2 N at home. The die in the hand frame: translation drift
0.4 mm in wp 1 to 3, 3.9 mm at home; ROTATION 26.8 degrees at home, growing
every waypoint (wp1 1.7, wp3 6.4, wp5 16.7, wp7 20.7, wp9 26.7). The rotation
axis is first the approach axis (hand z, wp 1 to 3), then from wp 4 on the
pinch axis (hand y, axis about (-0.3, -0.95, 0.1)): the die turns like a
hinge between the two pads. The pad contact centroids walk across the die
faces (pad 12 from z -2.9 to +6.2 mm in the die frame). Hand acceleration
spikes of 60 to 97 m/s^2 for one or two steps at every waypoint junction
(the velocity direction changes stepwise; no acceleration limit), 1 to 3
m/s^2 inside a pair. First motion (drift > 0.5 mm or rot > 1 deg): step 372,
wp 1 (21 steps into the swing).

### Episode 2: seed 1, run s1_r1 (held on the laptop)

Same command with seed 1, the driver's current defaults (sense_over_region
on, search effort weight 1, initial complexity 3). The laptop loaded
1747173590.312597.json (the cluster pins 1747173593 for seed 1; the laptop's
listing swaps 1747173590 and 1747173593, tools/bridge_gates.py
SCENE_MAP_LAPTOP_2026_05_26), so this is NOT the cluster's seed 1 episode.
Outcome: their reward 1.0, the goal check ok (the driver reports
gate_failed for the G19 mismatch only). 7 plans, wall about 3 min with the
recorder. The carry: 9 waypoints of max|dq| 0.45 rad, 42 steps each, the
arm at 2.54 rad/s; pad force only 0.92 N per pad at the lift (one contact
point per pad), dips to 0.00 N on both pads in wp 4, 7 and 8 while the
contact points stay, 0.8 N at home; drift 1.6 mm, rotation 4.1 degrees.
Held, with no margin: a force of zero on both pads for single steps.

### Episode 3: seed 14, run s14_base_r1 (base switches, the cup loop)

`bash run_episode.sh 14 s14_base_r1 --sense-over-region off --search-effort-weight off --search-initial-complexity 0`
(the cluster base arm's switches from BF53 results.jsonl). The laptop loaded
the 1747173590 scene again (see episode 2). The die was never reached: by
plan 53 (11 min) the episode was in the slow-tail loop, and its log shows
the mechanism (console_debug.log of the run, plans 46 to 53):

- plan k: move to the look configuration, `observe(d_cups_ud)`: "[M8]
  observe d_cups_ud: wrist re-posed; d_cups_ud complete, pose_radius 0.39 mm";
- plan k+1: move to d_cups_ud's pick approach; the #P2 integrity check after
  that move re-reads the scene ("2/4 believed bodies observed where
  believed") and re-poses d_cups_ud from the overhead detection; then
  "[M8] d_cups_ud pose_radius 5.49 mm is outside its commit margin, the
  pick's obj_pose_known no longer holds; replanning" (stale_precondition);
- plan k+2: observe again (0.39 mm), and so on.

So the slow tail is a belief oscillation: the wrist observe tightens the
cup's pose radius to 0.39 mm, the overhead refresh after the very next move
loosens it to 5.49 mm although the body did not move, and the pick's
commit-margin check (test_full_pipeline 2095 to 2105) refuses. Nothing
counts these cycles, so only the 600 s cap ends them. This is the same
pattern as the cluster seeds 5, 10, 17, 19 (alternating "look closer at
d_cups_ud, pick it up" / "pick up d_cups_ud"). It is not a die loss.
I could not stop the episode myself (a kill of my own PID was refused by
the permission system), so it ran on under the lock.

### Episode 4: seed 1 again, run s1_r2 (LOST), same settings as s1_r1

Same command as s1_r1 (defaults; scene 1747173590.312597.json). Reward 0.0,
"PHYSICAL_FAILURE (goal): (holding dice), finger-pad contact incomplete:
links none". 7 plans, the same action skeletons as s1_r1, but the last cup
d_cups_ud went to free_017 instead of free_016 and the plan times differ
(plan 1: 10.7 s in r1, 7.0 s in r2; the laptop was shared with other agents'
probes), so the die's pose at the pick differs by 5 um and 0.06 degrees and
the pick's pad force differs (1.63 N in r1, 2.28 N in r2 by the pick's own
line). The carry home is the same path to 1e-4 rad (9 waypoints, 42 steps
each, the arm at 2.54 rad/s).

How the die left (recorder steps; pick_done at 359, the move from 360):
- wp 1 to 4 (360 to 518): normal, drift 0.8 to 1.3 mm, rotation 1 to 10 deg.
- wp 5 to 8 (519 to 686): the die YAWS in the hand about the approach axis
  (hand z, axis about (0.3, 0.2, 0.9)): 22 deg at the end of wp 5, 49 at
  wp 6, 74 at wp 7, 100 at wp 8. As it turns, the pinch goes from face to
  edge: pad 13 drops to ONE contact point (a corner) from step 548 on, the
  pads are pushed apart (finger width 10.19 mm at the lift, 10.36 mm at step
  590, +0.17 mm), the normal force rises to 6.9 N (wedging), the die's
  centre walks 15 mm in the hand.
- wp 8 to 9 junction (step 687, hand deceleration 74 m/s^2 for one step):
  both pad forces drop to 0.0 N at step 687 to 688, pad 12 loses contact at
  689, pad 13 at 692; the die falls (die z 0.537 m at 687, 0.014 m at the
  end of the hold) onto the table.
- First motion (drift > 0.5 mm or rot > 1 deg): step 381 (wp 1). Rotation
  past 10 deg: step about 527 (wp 5). Loss (no pad): step 692, 5 steps after
  the last junction. First motion to loss: 311 steps (1.30 s); 10 deg to
  loss: about 165 steps (0.69 s); first pad break to loss: 3 steps.
- So: the die rotates out (yaw about the approach axis, stick and slip),
  it is neither thrown nor slid along the pads; the last junction kick
  releases it. In s1_r1 the same carry stuck at 4 deg (the width grew only
  0.015 mm).

Determinism: the same seed under identical settings gave held (r1) and lost
(r2); the step rows differ from the first recorded step of the pick.

### Episode 5: seed 1 a third time, run s1_r3 (LOST after the cup loop)

Same command and settings as s1_r1 and s1_r2 (scene 1747173590.312597.json).
Reward 0.0, physics_mismatch, 90 plans, 426 s: 82 of the 90 plans ended
in the cup loop of episode 3 ("d_cups_ud pose_radius ... outside its commit
margin"), then the cups moved and the die was picked once.
The carry (pick_done 357, 9 waypoints of 0.44 rad, 41 steps each): rotation
4.4 deg (wp 2), 10.8 (wp 3), 26.3 (wp 4), 52.4 (wp 5), axis between the
pinch and the approach axes; wedging again (finger width 9.90 mm at the lift,
10.05 mm at step 532, +0.157 mm max; pad force up to 6.8 N; pad 12 on ONE
contact point from step 482); then the die reseats at about 60 deg, the
width falls back to 9.88 mm and the force decays to 0.7 to 0.9 N; the wp 6
to 7 junction (step 595, hand deceleration 86 m/s^2) unloads both pads
(0.0 and 0.38 N), and both contacts are gone at step 601 (6 steps later).
The die lands on the table (it touches body 1 from step 682 on, z 0.012 m).
First motion step 382 (25 steps into the swing); predictor (width growth
> 0.05 mm) fires at step 503 (wp 4), 98 steps (0.41 s) before the loss.

Determinism result, seed 1 run three times under identical settings: held,
lost, lost (after 82 extra plans). First motion at 22, 22 and 25 steps into
the swing in all three; the outcome and the episode length are not
reproducible. Cause of the divergence (r1 against r2): the planner's plans
differ (the same skeletons, another free spot for the last cup, plan times
that depend on the machine's load), which moves the die by micrometres and
changes the pick's pad force (1.63 against 2.28 N), and the carry then
amplifies that difference into held or lost.

Predictor over the four carries recorded so far (tools: predictor.py):
held carries widen by +0.002 and +0.013 mm; lost carries by +0.225 and
+0.157 mm, crossing 0.05 mm 139 and 98 steps before the first pad break.
Pad-force zero steps do not separate (2 and 5 in held carries, 3 and 5 in
lost ones).

### Episode 6: seed 6, run s6_r1 (LOST)

Defaults, scene 1747173593.826745.json, 5 plans, 45 s, physics_mismatch. Rotation 19.6 / 56.9 / 94.3 deg at the end of wp 6 / 7 / 8, width +0.198 mm (crosses 0.05 mm at step 627, wp 7), release inside wp 9 at 1.3 m/s^2, not at a junction: the force decays 5 N to 0.1 N (step 724), contacts gone at 731. Die on the table. Junction steps carry 6 % of the turning. Final proposal written to proposals/loss_dynamics.md.
