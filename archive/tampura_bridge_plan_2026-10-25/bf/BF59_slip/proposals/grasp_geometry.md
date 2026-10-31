# BF#59 proposal: grasp geometry and the samplers

Angle: where the pads land on the die, what the samplers offer and certify,
what the executor does with it, and which geometric property separates a
holding carry from a losing one. Written 2026-10-31 at 92d1e06 (branch
tampura-bridge). No tracked file was changed.

## 1. Diagnosis

### 1.1 What the code offers and certifies (code reading, 92d1e06)

- The die gets ONE top-down grasp family. `pose_belief.fitted_grasp_candidates`
  (pose_belief.py 177-197) gives a near-square fitted footprint a single grasp
  at grasp yaw = the fitted yaw (mod 90 deg): the pads close across a pair of
  faces ("face pinch"). The AABB path (streams.py 840-845) gives yaw 0. The
  stream certifies reach (the kin stream at the contact pose of streams.py
  1375-1401) and the commit margin (pose_belief.py 209-237, position only).
  Nothing in the grasp, the stream or the commit rule speaks about the yaw
  error between the pads and the die's faces, where the pads touch, or a hold.
- The die's fitted yaw comes from the eye: `YAW_NOISE['eye']` 9.475 deg (p95),
  and a fitted eye yaw within that of an axis is stored as 0 (pose_belief.py
  34-35, 274; BF#29 (a): the eye reads true 5/10/80/85 deg as 0). Only the
  wrist camera (0.2 deg) knows the die's yaw to better than a few degrees,
  and the die commits without a wrist look (BF#28 (c): margin 4.03 mm against
  a radius under 1 mm).
- Contact height: execute_pick 1064-1067 and the kin stream 1398 put the
  grasp target at max(top - 5 mm, table + PICK_CONTACT_FLOOR 13.2 mm); for the
  die the floor wins (target 13.2 to 14.1 mm, measured ee_z 14.1 to 15.2 mm,
  the die's COM at about 8.9 mm).
- The close (robot_utils.py 1135-1194): a pad counts as touching at
  contactDistance <= 0.5 mm; width = mean finger joint; hold target = width -
  GRIP_SQUEEZE 0.5 mm at 60 N.

### 1.2 Their die and their pads (read only, their tree)

- The die's collision shape is ONE convex hull of 64 vertices
  (`create_ycb(use_concave=True)` reads google_16k/textured_vhacd.obj,
  panda_env_utils.py 668-690), body frame at the mesh's centre of mass; hull
  17.6 x 17.3 x 17.8 mm. Only two of its six sides are flat facets; the other
  four are lumpy (the vertices within 0.8 mm of a side's extreme span only 11
  to 16 mm). Their generator gives every body a uniform random yaw, and the
  die Pose(cup_pose[0]) (yaw 0) when a cup was placed before it
  (env_generator.py 120-127).
- Their finger collision mesh's inner face is a five-vertex polygon at
  y = -0.02 to -0.13 mm of the finger frame: the finger joint equals the pad's
  offset from the hand's centre plane to 0.1 mm.

### 1.3 Measured: the probe

Probe: `probes/grasp_geometry/probe_grasp_geometry.py` (physics only, no
lock). Their empty table, their Panda, their die (dynamic, resting on the
table, D9 mass, inertia, frictions) and the pipeline's own pick: the
pre-grasp aperture, the vertical descent with `move_robot_smooth(settle=True)`
to the contact pose at the floor, `close_gripper_until_contact` (60 N, 0.5 mm
squeeze, table and plane ignored), the 10 cm lift, the post-lift re-verify,
the carry home and `hold_at_config(52)`. HELD = both pads, summed normal
force >= 0.5 N after the hold (the goal check). Factors: delta = the yaw
between the pads' closing direction and the die's face normal (0 = face
pinch; 45 = the pads on two opposite vertical edges, "edge pinch"), the face
pair (k90 0/1), 7 to 8 cells of W, hand yaw 0 (6.6 and +-30 deg at the
seed-1 die cell), lateral offset, contact height. Two carry modes: `single`
(one move_robot_smooth to DEFAULT_ARM_POS, as tools/_probe_q14_grip.py) and
`pipeline` (a direct linear path of 10 waypoints, every pair through
move_robot_smooth(steps=30), settle at the last, as the dispatcher streams a
"direct path clear" plan_motion result, test_full_pipeline.py 1877-1896).

Command (cwd /root/tampura-work/tampura_environments, S = the checkout):

    PYTHONHASHSEED=0 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$S:$S/tools:/root/tampura-work/tampura:. \
      /root/armO-venvA/bin/python $S/archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/grasp_geometry/probe_grasp_geometry.py \
      --out <json> --cells 8 --deltas 0,3,6,10,35,45,55 --k90 0,1 [--carry-mode pipeline] [--aperture-sized 1] \
      [--payload cube40] [--dx=-2,2 --dy=-2,2] [--floor-mm 15.0] [--hand-yaw-deg=30] [--cell-list x,y]

The cell (0.592, -0.242) has no seeded contact IK at hand yaw 0 and is
excluded from those runs; it was run separately at the hand yaws the
pipeline used there.

**(a) The measured half-width is the collision margin, not yaw.** An aligned
die (delta 0) reads 10.2 to 10.4 mm (hull half-width 8.6 to 8.9 mm), the same
1.3 to 1.5 mm excess the eval shows. Calibration: 10.2 to 10.4 mm for delta 0
to 6, 10.7 to 10.9 at 10, 11.2 to 11.3 at 15, 11.7 at 20, 12.2 to 13.0 at 30
to 57 deg. The eval's die picks read 10.0 to 11.3 mm and none 12 mm or more:
every eval carry was a face pinch within 0 to 15 deg.

**(b) The relative yaw decides the hold** (die, 0.5 mm squeeze, floor height):

| delta (deg) | single carry | pipeline carry |
|---|---|---|
| 0 to 0.5 (exact face) | 21/24 (88 %) | 46/58 (79 %) |
| 1 to 25 (near face) | 57/124 (46 %) | 63/124 (51 %) |
| 30 to 57 (edge) | 154/164 (94 %) | 148/184 (80 %) |

Fine structure (pipeline carry, 14 grips each): 0 deg 12, 0.2 deg 12,
0.5 deg 11, 1 deg 7, 2 deg 8, 3 deg 10, 6 deg 7, 10 deg 3; edge 38 to 52 deg
10 to 13 each. A face pinch is reliable only at exact alignment; one degree
off loses half the carries. The eye's yaw belief (9.5 deg, snapping) cannot
certify a face pinch; it can certify an edge pinch (the band is +-12 deg).

**(c) The eval's own width bins say the same.** Grouping the 174 eval die
picks (evidence/tc_4912db9_grip_lines.txt) by measured half-width (failure =
episode outcome failure, the rest of the non-success rows excluded): under
10.15 mm 11 failures in 21 (52 %), 10.15 to 10.45 mm 14 in 94 (15 %), 10.45
to 10.75 mm 6 in 24 (25 %), 10.75 mm or more 0 in 5. In the probe the narrow
reading (under 10.15 mm) occurs at delta 1 to 2 deg and holds 5/16
(pipeline carry) and 2/20 (single): the narrow eval picks are dice 1 to 2
deg off the pads.

**(d) What does NOT separate.** Contact height: grasp target 13.2 / 15.0 /
16.5 mm held 9/8/7 of 10 at 0 deg, 3/2/4 at 6 deg, 3/6/1 at 10 deg, 10/10/8
at 45 deg (single carry); raising the pinch does not help, and the floor
keeps it from going lower. Pad force at the close: face grips held 66, 62,
42, 50 % in the bins under 2, 2 to 3, 3 to 4, over 4 N (pipeline carry), no
trend (the eval's held and lost medians, 3.07 and 3.58 N, agree).

**(e) Lateral offset** (dx, dy +-2 mm, single carry): face 0 deg 13/40, face
6 deg 16/40, edge 45 deg 37/40. The edge pinch tolerates a pose error of the
size the belief carries; the face pinch does not.

**(f) The contact set.** getContactPoints reports one to a few points per pad,
always at the COM's height (-2.7 to +4.2 mm after the lift). For a face pinch
the two pads' force centres are offset across the pinch by a median 5 to
8.7 mm, for an edge pinch 1.6 mm. Every carry, held or lost, ends with the
die rotated in the hand (tilt 13 to 150 deg at home).

**(g) Our 40 mm cube** (box shape, 0.1 kg): face 0 and 3 deg 14/14 in both
carry modes, 6 deg 2/7 single and 0/7 pipeline, 10 and 20 deg 0/14 single;
edge 35 to 55 deg 21/21 single, but 45 deg 3/7 pipeline; dx, dy +-2 mm 56/56
single. The same yaw band exists for a flat box (it holds to 3 deg and loses
from 6 deg). Our scenes' cubes stand at yaw 0, where the eye is exact
(BF#29 (b)), so they are in the exact class. The edge pinch is NOT safe for
our cube under the pipeline's carry.

**(h) Three headless episodes** (`run_edge_pinch_episode.py`: the edge pinch
patched into `fitted_grasp_candidates`, under the lock). Seed 0: success, the
die at 12.6 mm, 4.37 N; 5 plans and 63.8 s against 3 plans in the eval,
because the patch also gave the 51 mm d_cups_ud a diagonal grasp, its commit
margin fell to about 2 mm, one pick was refused and one more observe ran.
Laptop seeds 1 and 2 load the SAME scene (1747173590; G19 mismatch, as BF#39
warns): both picked the die at an edge (fitted yaw -38.4 and 38.7 deg, grasp
yaw 6.6 and -6.3, measured 12.3 mm, 6.2 and 6.0 N; the die's true settle yaw
-35.6 deg, so the edge geometry was right), both passed the post-lift
re-verify (eye.jsonl: the die at z 0.095, tilt 1.4 deg, fingers 11.9 mm),
and both lost it on the direct linear move home. The probe at that cell, the
pipeline's hand yaw and the pipeline carry holds 9/10 edge grips; the two
losses are not reproduced. These two episodes are also confounded: my
margin-based scope rule failed (the face family's span is widened to the
cup's AABB, so the face margin was the smaller one) and the cups' 38 and
42 mm top faces got diagonal grasps; seed 2 then refused 50 cup picks for
pose uncertainty (108 plans). The scope must be a declared size bound, not
the margin comparison (fix 1).

### 1.4 Inferred mechanism

Measured: the hold depends on delta as in (b); the contacts are points at the
COM's height with a large across-pinch offset for a face pinch and a small
one for an edge pinch (f). Inferred: with point contacts and no torsional
friction (PyBullet's spinning friction defaults to 0) the pinch is a hinge
through the COM and the die turns in the hand during every swing. For a face
pinch at a small delta the extreme points of the two faces lie near
diagonally opposite vertical edges; the pads' normal forces form a couple
about the vertical whose friction use is tan(45 - delta) (0.9 at 3 deg
against mu 1.2), so the swing turns the die toward face alignment, which
narrows it across the pads by s/2 (cos delta + sin delta - 1) per side
(0.44 mm at 3 deg, 0.86 at 6, 1.37 at 10). Once that exceeds the 0.5 mm
squeeze the pads, held at width - 0.5 mm, lose it. At exact alignment there
is no turn to make; at an edge pinch the couple's friction use is 0 to 0.27.
The lumpy hull makes "exact" a sub degree matter for the die. This picture is
not proven: the 40 mm cube holds to 3 deg where the width rule would say
1.4 deg. What is left after the geometry (about 20 % lost in both the exact
face and the edge class under the pipeline carry, and the two episode losses)
belongs to the carry and the hold: the pipeline carry costs the die's edge
pinch 14 points and the cube's edge pinch 57 points against the single move.

On Hani's hypothesis: today the samplers certify grasps on a yaw belief that
cannot support them. Making the certified family match what the belief knows
(the edge pinch from the eye, the face pinch only after a wrist look) moves
the die's hold from about 51 % to about 80 % in the probe for dice that are
not at exact alignment. It does not make a certified grasp always hold: the
carry still loses about one in five.

## 2. Proposed fixes

### Fix 1: `edge_pinch`

- Mechanism: the yaw band of (b); the eye's 9.5 deg yaw belief certifies an
  edge pinch (+-12 deg band) and never a face pinch (sub degree).
- Change: `pose_belief.fitted_grasp_candidates` (177): with
  `slip_fixes.on('edge_pinch')`, a near-square fitted footprint (|e0 - e1| <=
  square_tol) whose larger side is at most `EDGE_PINCH_MAX_SIDE` = 0.025 m
  returns the single grasp (wrap(yaw + pi/4, pi/2), span), span =
  2 pinch_half_extent(pad_direction(gy), yaw, extents), widened to the AABB
  as Q-H (a) does. Everything downstream reads it: sample_grasp (836-839),
  believed_margin and pose_known (209-237; the die's margin rises from 4.4 to
  6.2 mm), execute_pick's sizing (1054-1057: `sized_pinch_half` along the
  diagonal, 12.4 mm; aperture 12.4 mm + pose radius + 8 mm; the width
  plausibility up to 20.4 mm against a 12.3 to 12.6 mm reading). No executor
  change. The AABB path (no valid yaw) is unchanged.
- Section 5: model side (the grasp family the sampler offers), switch off by
  default, no robot setting touched. The 25 mm bound is a declared constant
  below every class of our scenes (targets 30 to 40 mm cubes, boxel_env.py
  340-345; occluders 50 to 60 mm); its reason is measured on our class, not
  on find_dice: our 40 mm cube's edge pinch holds 3/7 under the pipeline
  carry (g). In practice it reaches only the die; the reviewers should judge
  whether a size-scoped family rule passes rule 2.
- Expected effect: per die carry, in the probe 51 % to 80 % held for dice not
  at exact alignment, unchanged (79 % to 80 %) for those at exact alignment.
  Eval estimate: the narrow and wide width bins (about 30 of the 144 scored
  picks, 17 failures) move to about 20 % loss, about 10 fewer losses in 174
  carries: the loss rate per carry from 21 % to about 15 %. Convincing on the
  campaign's seeds only if it falls below about 12 % with base's repeat
  spread in view; 15 % is marginal. Time: no extra plan or action (the margin
  grows); fewer re-picks in the slow tail if the effect is real.
- Falsifier: under the switch the die's measured half-width at the pick must
  read 12 mm or more (the edge geometry achieved); if it does and the loss
  rate per carry is not below base's on the paired seeds, the fix failed.
  The two lost laptop episodes (h) are a warning already.
- Risk to our scenes: none by construction (no class at or under 25 mm).
- Effort: 2 h (the function, the switch, tests in tests/test_m9_grasp.py for
  the diagonal span and the scope).

### Fix 2: `face_needs_wrist_yaw`

- Mechanism: the same band; the face pinch holds at 0 to 0.5 deg (79 to 88 %)
  and the wrist's yaw noise is 0.2 deg.
- Change: `pose_belief.pose_known` (233): with the switch, a near-square body
  whose larger side is at most EDGE_PINCH_MAX_SIDE and whose grasp is the
  face pinch (edge_pinch off) is pose_known only when its fused yaw came from
  the wrist (`_fuse`, pose_belief.py 274-279, records the producing camera);
  no valid yaw from any camera means unknown. The planner then plans M8's
  observe (the wrist look) before the pick, as it already does for an
  uncertain position. With fix 1 on, fix 2 is a no-op.
- Section 5: model side (the belief's commit rule, M8's own mechanism); same
  size scope and the same caveat as fix 1.
- Expected effect: every die pick in the exact-face class: 79 % (pipeline
  carry) to 88 % held, about the edge pinch's rate. Cost: one observe per die
  pick (about 0.15 s of execution in the eval's logs, and one more plan of 1
  to 3 s).
- Falsifier: picks after the wrist look must read 10.15 to 10.45 mm (the
  exact class); if the loss rate per carry is not below base's, it failed.
- Risk to our scenes: none (scope). Effort: 2 h.

### Fix 3: `pinch_band_certificate` (the general form, larger)

- Mechanism: a certified grasp should hold; today the grasp stream certifies
  reach only.
- Change: `streams.BoxelStreams.sample_grasp` yields a grasp only when the
  belief's yaw interval [yaw - noise, yaw + noise] lies inside the family's
  declared holding band (from this probe: face |delta| <= 0.5 deg; edge
  |delta - 45| <= 10 deg within fix 1's scope) and the pose radius is within
  the family's lateral tolerance (face 1 mm, edge 2 mm, (e)); otherwise no
  grasp, and M8 plans an observe. It needs a yaw noise per detection: the
  eye's 9.5 deg describes the die's 30-pixel top face, our boxes at hundreds
  of pixels read 0.007 deg (BF#29 (b)); with the per-camera constant every
  cube of our scenes would need a wrist look. A per-detection yaw noise from
  the top-face pixel count is part of the change.
- Section 5: model side (stream certificate and belief), pipeline-wide.
- Expected effect: as fixes 1 and 2 for the die, plus a stated certificate.
  Time: observes where the yaw belief is weak.
- Falsifier: the share of certified grasps that hold must reach the band's
  measured rate (about 80 %).
- Risk: our scenes' time if the per-detection noise is too pessimistic.
- Effort: 6 to 8 h (the band table, the per-detection yaw noise, tests).

## 3. With one more hour

The two lost laptop episodes (h) contradict the probe at the same cell (9/10
edge grips held under the pipeline carry). I would replay their move home
exactly: the post-lift readback and the plan_motion waypoints of the episode
(the ledger records neither; a print-only hook in a wrapper would) in the
probe, with the die at the pick's recorded pose, to learn whether the loss
lives in the trajectory (the per-pair restart from the lagging state, 30
steps a pair) or in the pick (6.0 to 6.2 N at the close against 3 to 4.4 N in
the probe). That separates fix 1's ceiling from the carry angle's share.

## 4. Data generated and deleted

All under `archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/probes/grasp_geometry/`,
untracked, 10.75 MB after the deletions. DATA_LEDGER.md is tracked and was
not edited in this phase (the brief's rule); the orchestrator should add the
rows.

- Scripts (keep): probe_grasp_geometry.py 16 KB, run_edge_pinch_episode.py
  3 KB, analyse.py, analyse_hand.py, show_rows.py, show_lost.py,
  die_track.py, narrow_rows.py, width_bins.py (0.4 to 3 KB each).
- Sweep outputs (cited above; json and log): sweep_yaw 198 KB,
  sweep_height_150 148 + 7 KB, sweep_height_165 138 + 7 KB, sweep_offset
  496 + 20 KB, sweep_edge_band 289 + 14 KB, sweep_fine_small 370 + 16 KB,
  die_edge_sized 147 + 7 KB, cube40_yaw 194 + 10 KB, cube40_offset 223 + 9 KB,
  cell2_hy6.6 46 KB, cell2_hy-30 50 KB, cell2_hy30 54 KB, pipecarry_main
  363 + 16 KB, pipecarry_cell2 65 + 3 KB, pipecarry_cube 97 + 5 KB,
  pipecarry_wrist 249 + 9 KB, pipecarry_edge2 293 + 14 KB, pipecarry_hy30
  402 + 16 KB. Garbage once the review phase is done (re-runnable in
  minutes).
- Episodes (keep for the review, garbage after it): ep_seed0/ 0.42 MB,
  ep_seed1/ 1.13 MB, ep_seed2/ 5.19 MB; ep_seed0.log 4 KB, ep_seed1.log
  8 KB, ep_seed2.log 38 KB.
- Deleted: smoke.json (6 KB, superseded by sweep_yaw), cell2_yaw.json
  (53 KB, every trial without a grip: the cell's contact IK at hand yaw 0
  fails).
