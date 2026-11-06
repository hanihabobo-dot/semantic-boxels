# Review of puck_slide/ARGUMENT.md (adversarial reviewer, 2026-11-06)

**Verdict: survives with changes.** As a document it is careful and mostly right: of 83 load-bearing cite rows checked (about 110 file:line references), 80 hold, 2 hold only in part and 1 is wrong; the arithmetic of sections 2.3, 2.4, 3.2 (T6), 4.3 and 7.5 recomputes; the second physics probe and the analysis script reproduce byte for byte (the first probe was not rerun); the damping law it marked UNVERIFIED (k1 = k2 = 0.04) is exactly PyBullet's default (review probe); and the core design keeps H1 (one physical stroke, no resets, no reads of their belief, truth read only by the evaluator). It does not survive as a reason to commit 6 to 8 working days before 2026-12-04, because the design closes only if the test push's launch speed is known to about 2 %, and no measured path to that number exists. The source the document proposes is the contacting link's speed at the last contact, turned into a launch speed by a calibration made with our own bodies. On their stroke (review probe) the puck leaves the pusher mid-stroke, 7 to 58 % faster than the pusher moves at that instant, so the launch is set by the contact solver and not by the pusher's speed. At the test push's effort the ratio is stable for single-contact pushes (1.138 to 1.146), but it falls to 1.017 for the high-friction puck, whose push makes a second contact: an 11 % error in exactly the case the error budget calls tightest. And the test push must launch near 0.2 m/s to keep a slippery puck within reach, which is the regime where their stroke's launch also depends on the friction against the command (sd 5.4 % at effort 0.01). The go or no-go therefore needs the new stroke controller first: the stop rule's "by day 3" is realistic, but the one-day W0, placed before the W2 that builds the stroke, cannot produce the number. The error budget lacks three terms: the separation point, the shot's forward-model error (measured: up to 2 cm of the 21 cm window, 2.6 to 3.5 % in friction terms) and the calibration body. The minimal version's 6 to 8 days do not follow from the document's own work items (about 8.5 to 10, before gates, logging and arm T's first local run). And three binding records are stretched without being named: H3's "small" and region-based POD model, BF#66's "CLAIM EFFECT: none for this paper", and H1's listing of success scoring. It would survive with four changes: make the launch-speed source an explicit decision with a pass criterion fixed in advance and a fallback (renders of the early slide, or their stroke shape run physically after our own approach); add the missing error terms, and a model-error term, to the literal; re-derive the effort; and put the stretched records to Hani as named relaxations. On the strategic question, the document already concedes the no-fit case's time figure and grades its own result "adjacent, not core". I find no reason to rank it above class_uncertain or the open find_dice findings before the deadline, and would limit pre-deadline work to a time-boxed W0 spike that decides the launch-speed question.

Scope of this review. Read: AUTHOR_BRIEF.md, ARGUMENT.md, the three probe scripts and their outputs; class_uncertain/TAMPURA_TASKS_SURVEY.md, no_fit_case.md, BRIEF.md; PROPOSAL_ATTRIBUTE_BOXELS.md; the PAPER_AUDIT.txt entries named below; every cited file of ours; their puck_slide/env.py in full (757 lines) and the cited helpers. Run, read only, from /root/ps_probe with their venv (section 7): the author's probe_analysis.py and probe_puck_physics2.py again, two new probes (rp_damping.py, rp_launch.py, the latter a copy of the author's probe 2 trial with extra logging) and a tree-hash check. Nothing was written under /root/tampura-work or /root/ps_probe; their trees hash as before.

Abbreviations: env.py = /root/tampura-work/tampura_environments/tampura_environments/puck_slide/env.py; PA = PAPER_AUDIT.txt; RP = this folder's review_probe/.

## 1. Citation table

Result classes: CONFIRMED, PARTLY (the cite exists but the claim built on it is only partly right), WRONG, NOT FOUND. "Caveat" marks a confirmed cite whose context changes how it may be used.

### 1.1 Their code

| # | ARGUMENT section | cite | result |
|---|---|---|---|
| C1 | 0 | env.py:33 PUCK_RADIUS 0.06 | CONFIRMED |
| C2 | 0 | panda.urdf:348, 355 finger upper 0.04 | CONFIRMED |
| C3 | 1.1, 8.1 | env.py:745 reward in(puck, goal0) | CONFIRMED |
| C4 | 1.1, 8.1 | env.py:228, 540-545 believed pose = observed real pose | CONFIRMED |
| C5 | 1.1, 2.3, 8.1 | env.py:660-672 test_in, any corner of a 2 cm box | CONFIRMED |
| C6 | 1.2 | env.py:384-415 motor controller, 2000 settle steps | CONFIRMED; caveat: it also resets the arm to joint_path[0] first (env.py:388-393) |
| C7 | 1.7, 2.1 | env.py:681 friction per seed | CONFIRMED; caveat: the seed also draws the 19 particle frictions (env.py:354) and every nudge direction (env.py:655), so "the seed draws only the friction" is loose |
| C8 | 2.1, 2.3 | env.py:63-65 range and FRICTION_MID | CONFIRMED |
| C9 | 1.5, 2.1 | env.py:314 slab friction 0.1 | CONFIRMED |
| C10 | 2.2, 4.1 | env.py:108-229 belief; :685 sim world | CONFIRMED |
| C11 | 2.3 | env.py:353-356 particles from the same range | CONFIRMED; caveat: uniform in 1/friction, not in friction (the doc's D-5 "neutral" holds only because the interval carries no distribution) |
| C12 | 2.3 | env.py:49-56, 306-313, 329-333 goal box x 1.2 to 1.4; slab x -0.30 to 1.40 | CONFIRMED (FLOOR_OFFSET 0.85, surface 1.7 m centred at x 0.55) |
| C13 | 2.3 | env.py:151-152 off-table at z < 0 | CONFIRMED |
| C14 | 3.2 | env.py:101-105 PuckObservation | CONFIRMED |
| C15 | 3.2 T1 | env.py:601-657 their nudge, "mostly sideways" | PARTLY: the sampled OFFSET is mostly sideways (env.py:655), but the push runs from the puck toward (0.6, about 0.2): from the start pose the commanded direction is about 44 degrees off the slab axis and the puck travels 38 to 40 degrees off it (E3's dx, dy). Its five trials update the effort after each (env.py:509 inside shoot_controller, called at :622-630), so only the first trial runs at 0.005; the doc's E3 (one trial at 0.005) is not what their nudge executes |
| C16 | 3.2 T1 | env.py:622-630 five trials with resets | CONFIRMED |
| C17 | 5.1 | env.py:422-512, 433-458, 465-471 a 5 cm Cartesian stroke | CONFIRMED (DIST_MULT 0.05 at :433; plan_workspace_motion returns two configurations, probe JSON joint_path_len_goal 2) |
| C18 | 5.1 | env.py:490-491 apply_sequence approach | CONFIRMED |
| C19 | 5.1 | env.py:418, 493 pc_steps 5 | CONFIRMED |
| C20 | 5.1 | env.py:496-498, 500-501 arm and every puck reset per trial | CONFIRMED |
| C21 | 5.1 | env.py:505-509 median correction | CONFIRMED; caveat: the update also runs after the last trial, so the effort returned (:512) and sent in the observation (:544) is not the last one used, and the belief replays the returned one (:221-223) |
| C22 | 5.1 | env.py:540-541 all pucks set to the real final pose | CONFIRMED |
| C23 | 5.1 | env.py:525-530 19 ghosts carry the belief's frictions | CONFIRMED |
| C24 | 8.3 | env.py:537-538, 631-632 unchanged pose when no path | CONFIRMED |
| C25 | 10.1 | env.py:548-583 effects_fn runs shoot_controller in the belief world | CONFIRMED |
| C26 | 10.1 | env.py:725 push-to removes in(ik) | CONFIRMED |
| C27 | 8.5 | env.py:335-361 ghosts, alpha 0.2, robot and slab collisions only | CONFIRMED (ghost group 1 mask 2; robot and floor group 2 mask 3); that the slab is in group 2 rests on PyBullet's default group for static bodies, UNVERIFIED by me, consistent with the measured slides |
| C28 | 4.2 | env.py:346-351, 689 real puck first, store binds objects[0] | CONFIRMED |
| C29 | 4.2 | env.py:371-376 DEFAULT_ARM_POS | CONFIRMED |
| C30 | 4.1, 8.4 | env.py:258 gravity -9.8 | CONFIRMED |
| C31 | 4.5 | env.py:44-48 start z 0.06 | CONFIRMED |
| C32 | PS-Q9 | env.py:73 MASS 1 | CONFIRMED |
| C33 | 8.3 | env.py:58-62 ik x 0.3 to 0.9 | CONFIRMED |
| C34 | 8.1 | env.py:80-82 REGION_POSES | CONFIRMED |
| C35 | 8.5 | env.py:236-245 create_puck | CONFIRMED |
| C36 | 5.3 | env.py:406 2000 steps | CONFIRMED |
| C37 | 5.1 | pb_utils.py:1312-1328 effort is a lead time | CONFIRMED (panda_utils/primitives.py:106-113 passes time_step=lead_step) |

### 1.2 Ours and the records

| # | ARGUMENT section | cite | result |
|---|---|---|---|
| C38 | 0 | PA:3256-3273 H1 to H4 | CONFIRMED |
| C39 | 4.2, 5.2 | PA:3256-3259 H1 | CONFIRMED; caveat: H1's list of decisions that ground-truth reads must not feed includes "success scoring" (:3259) |
| C40 | 1.3 | PA:3265-3269 H3 | PARTLY: the cite is right, the paraphrase is selective. "A K-literal set only by an observation, a commit margin, optimistic determinisation and replanning" drops H3's "belief as literals over named regions" and "hidden regions as belief volumes" and its "small", and adds the commit margin, which is M8's (PA:4456-4460), not H3's |
| C41 | 0 | PA:3285-3313 G1 | CONFIRMED (removeBody :3290, changeDynamics :3296 on its list) |
| C42 | 8.5 | PA:3297-3303 D9 set-up class | CONFIRMED (classes at :3299-3301) |
| C43 | 4.4 | PA:3361-3366 G6 positive controls | CONFIRMED |
| C44 | 4.1 | PA:3384-3391 G8(b) tactile queries legal | CONFIRMED; caveat: G2's leak test (PA:3326-3329) forbids any body id from such a contact list reaching the belief, which bounds how separation may be detected (section 3) |
| C45 | 4.2 | PA:3396-3398 G8(d) | CONFIRMED |
| C46 | 2.3, 4.1 | PA:3399-3405 G9 | CONFIRMED |
| C47 | 3.1 | PA:3413-3422 G10 goal pin | CONFIRMED |
| C48 | 1.3 | PA:4456-4469 M8 | CONFIRMED |
| C49 | R3 | PA:4464-4466 PLACE_POSE_TOL 3.609 mm | CONFIRMED |
| C50 | 2.5 | PA:4467-4469 M8's POD sentence | CONFIRMED |
| C51 | 5.3 | PA:4484-4491 M10 | CONFIRMED |
| C52 | 0, 1.2, 5.1 | PA:7364-7416, 7370-7384, 7375-7377 BF#35 | CONFIRMED |
| C53 | 1.1 | PA:7490-7492 Q18 | CONFIRMED |
| C54 | 0, 5.2 | PA:7418-7526, 7507-7526 BF#36, BF#37 | CONFIRMED |
| C55 | 8.1 | PA:7518-7523 BF#37 item 2 | CONFIRMED |
| C56 | 2.2 | PA:8764 BF#60 | CONFIRMED |
| C57 | 0, 5.3 | PA:9354-9372, 9365-9370 #P5 | CONFIRMED (the quoted words at :9369-9370) |
| C58 | 10.1 | execution.py:1935-1937 push removed, occluders teleported | CONFIRMED |
| C59 | 1.8, 10.1 | archive/CODEBASE_AUDIT_DEFERRED.txt:450-467 (465-467) | CONFIRMED |
| C60 | 1.8, 10.1 | archive/CODEBASE_AUDIT_FINAL.txt:167-168 | CONFIRMED |
| C61 | 10.1 | pddl/domain_pddlstream_m8.pddl:7, 32 header names push | CONFIRMED |
| C62 | 3.1 | domain :396-410 observe; :127-163 optimistic sense | CONFIRMED |
| C63 | 1.3, 3.1 | pose_belief.py:303-331, 327-331 commit margin | CONFIRMED |
| C64 | 2.3 | pddlstream_planner.py:721-763 obj_pose_known emitted in _build_init | CONFIRMED (_build_init starts at :671) |
| C65 | 3.1 | m8_domain.py:39-113, 127-136 generated delta, off = live file | CONFIRMED |
| C66 | 3.3 | tampura_bridge/task_spec.py:25 e_cups_ud 76.7 mm | CONFIRMED |
| C67 | 4.2 | task_spec.py:66-75 the D4 eye | CONFIRMED (a FIXED eye at their camera_frame pose for DEFAULT_ARM_POS, 640 x 480, 49.13 deg); the view-extent arithmetic recomputes to x 0.306 to 1.188 at z 0.075 |
| C68 | 8.4 | task_spec.py:58-62; tampura_bridge/policy.py:65-85 D9 | CONFIRMED (D9 also sets the pad friction 1.2, policy.py:86-89) |
| C69 | 5.3 | robot_utils.py:886-1007, 969-970, 160-162 | CONFIRMED; caveat: the same docstring records a 10 to 20 mm undershoot of streamed targets at awkward postures (robot_utils.py:979-980), which matters for a speed-critical stroke |
| C70 | 6 | test_full_pipeline.py:2024-2765 dispatch | CONFIRMED (the loop starts at :1990) |
| C71 | 7.3 | test_full_pipeline.py:1130-1200, 3154-3172, 1174-1181; run_logger.py:697-739 | CONFIRMED |
| C72 | 4.4 | tools/gen_scene_eval.py:345 Wilson | CONFIRMED |
| C73 | 7.5 | archive/.../BF59_slip/reviews/hold_physics.md:169 "119 s" | CONFIRMED as quoted; caveat: it is BF#53's mean over find_dice episodes on the cluster, ruled by a few pathological episodes; the median was 34.6 s (PA:8308-8311). Used for our own scenes on the laptop it is a guess (the doc does mark it UNVERIFIED) |
| C74 | 1.3, 2.4 | PROPOSAL_ATTRIBUTE_BOXELS.md:218-237, 235-237, 3.3 | CONFIRMED; caveat: the same section says the pose-radius commit margin "is already a two-level value boxelization; nothing to add" (:231-232), and BF#66 is logged "FAR FUTURE WORK ... CLAIM EFFECT: none for this paper" (PA:9275, 9346-9351) |
| C75 | 6 | tools/bridge_gates.py, run_tampura_timed.py, gen_scene_eval.py live on tampura-bridge | CONFIRMED (git ls-tree: present on tampura-bridge, absent on main; m8_domain.py and pose_belief.py likewise) |
| C76 | 2.5 | "no M11" | CONFIRMED (0 hits) |
| C77 | 11 | "Q17 and Q18 are the highest" | CONFIRMED (case-sensitive: Q1 to Q18) |
| C78 | 11 | "BF#66 is the latest found here" | WRONG: BF#67 is already claimed by the class_uncertain plan (DATA_LEDGER.md:43, 48 in the working tree; class_uncertain/STATE.md:6). The decision entry would need BF#68 or later; grep again |
| C79 | 4.5 | tree hashes b68dbf8ebfee50c0..., 0e8267e1b90a9ccc... | CONFIRMED (RP/rp_tree_hash_variants_out.txt: they are `git ls-files -z \| xargs -0 sha256sum \| sha256sum`; tools/bridge_gates.py:598-609's own method gives e339e7b8... and fbc0cd06..., RP/rp_tree_hash_out.txt. The document should name its method) |
| C80 | 4.5 | tampura_environments/__init__.py sha256 9a64bea0... | CONFIRMED |
| C81 | 12 | /root/ps_probe holds one symlink | CONFIRMED |
| C82 | 1.4, 1.7, 4.4 | SURVEY Table I to III values (D 0.52, DQN 0.47, MLO 0.29, WAO 0.24, None 0.34; 3.75 steps; 23 s per step) | CONFIRMED against TAMPURA_TASKS_SURVEY.md:40-43, 81 (not re-read in the paper) |
| C83 | 1, 10 | no_fit_case.md 1.4, 2.2, 2.4, 2.6 | CONFIRMED (quotes and positions) |

Totals: 83 rows; 1 WRONG (C78), 2 PARTLY (C15, C40), 9 confirmed with a caveat that changes their use (C6, C7, C11, C21, C39, C44, C69, C73, C74), the rest CONFIRMED. NOT FOUND: none.

## 2. Numbers check

### 2.1 Reproduction
- probe_analysis.py rerun on the author's JSON: byte-identical to probe_analysis_out.txt (RP/probe_analysis_rerun_out.txt).
- probe_puck_physics2.py rerun: JSON byte-identical (RP/probe_puck_physics2_rerun_out.json); PyBullet DIRECT is deterministic here.
- Three fresh worlds running one joint path give bit-identical results (RP/rp_launch_out.json, L3: x 0.593262, v 0.196105 each time). My L1 rows reproduce the author's F1 default-damping rows exactly (all nine x and v_sep values).

### 2.2 Recomputed and confirmed
| item | ARGUMENT | recomputed |
|---|---|---|
| launch sd by effort (A) | 5 to 14 % at 0.005 to 0.010, at most 1 % at 0.015 and above | 13.7 %, 5.4 %; 0.78, 0.92, 0.46, 0.27, 0.54 %. Minor: "18.2 to 19.2 m/s per unit effort" at 0.015 and above is 18.2 to 18.9 (19.2 is at 0.010) |
| slide models (B) | Coulomb 1.081 and 9.5 %; linear 2.0 %; linear and quadratic 1.4 %; n = 23 | same |
| damping law (4.1, UNVERIFIED there) | k1 = k2 = 0.04, PyBullet's default | CONFIRMED by RP/rp_damping.py: least-squares fit 0.0400 and 0.0400 on a free 1 kg puck, the law's largest relative error 2e-8 |
| damping is the bias (F1) | zero damping: 0.975 to 0.991 | same |
| estimator (C) | -1.5 to -1.9 %; 3 mm: -0.9 to -3.1 %; 2 % speed: +4.1 to +4.3 % | -1.51 to -1.94; -0.91 to -3.08; +4.10 to +4.26 |
| windows (D, 2.3) | 1.262 and 1.124 from the start; 1.318 to 1.499 and 1.148 to 1.224 after T2 | same (sqrt(1.2625) = 1.1236) |
| classes (2.4) | 4.7 and 2.7 | 4.72 and 2.71 (perfect controller; with e = 2 % from the start it is 7.1) |
| blind shot (T6) | about 23 % and at most about 31 % | 23.4 % and 31.2 % |
| allowance (4.3) | 1.218, 9.8 %, sum 9.3 %; at e = 1 %: 11.8 % against 7.1 % | 1.2176, 9.81 %, 9.3 %; 11.76 %, 7.1 % |
| literal (2.3) | hi/lo <= (W_far/W_near)/(1+e)^4 | the exact Coulomb form is (1-e)^2/(1+e)^2; 0.9231 against 0.9239 at e = 2 %: fine |
| E4 | 5 of 5, x 1.262 to 1.305; trial 1 at mu 0.05 x 2.039; replay 3.6 cm at mu 0.125 | same |
| ghosts (F) | -10.8 and -3.7 mm, tool tip identical | same; not reported: the ghosts also lower the real puck's launch by 4.2 % at effort 0.01 (0.1973 to 0.1891 m/s) and 0.6 % at 0.02 |
| reach (E5) | 3 of 3 to x 0.80, 0 of 3 beyond | same |
| view (4.2) | x 0.31 to 1.19 | 0.306 to 1.188 (my arithmetic from task_spec.py:70-73; not rendered) |
| TAMPURA per episode (1.7) | about 1.4 min | 3.75 x 23 s = 86 s |
| cost runs (7.5) | about 7 h | 3 x 54 x 2 min = 5.4 h plus 40 x 2 min = 1.3 h |
| days (9.2) | 28 days | 28 calendar days, 21 working days inclusive (Friday 2026-11-06 to Friday 2026-12-04) |

### 2.3 Wrong, overstated or unsupported
- N1 (4.1, 4.3) Mass. "A factor of 4 in mass moves the launch speed by at most 1.8 % at the test push's speed" is the half-range: 0.5 to 2 kg moves it 3.6 % (F2: 0.1986 to 0.1916 m/s); 1 to 2 kg moves it 2.3 %, so 4.3's row "factor 2: at most 1.8 %" is WRONG. The design-relevant case is a calibration on our light bodies applied to the 1 kg puck: RP L2 gives +1.6 % (0.1 kg against 1 kg, effort 0.01) and +1.4 % (0.02), close to the doc's figure, so the practical number survives and the wording does not.
- N2 (4.1, 4.3, 5.3) The launch-speed source. The doc's figure "the puck leaves 5 to 10 % faster than the tool tip's PEAK speed" is right, but the estimator reads the link's speed at the LAST CONTACT, which no probe of the author's measured. RP/rp_launch.py measured it on their stroke: puck speed over contacting-link speed at the last separation is 1.146, 1.138, 1.017 at effort 0.010 (mu 0.05, 0.10, 0.15; the last is a second contact), 1.110, 1.101, 1.103 at 0.015, 1.096, 1.078, 1.072 at 0.020, and 1.575, 1.418, 1.419 at 0.030. The contacting link's own speed and its contact-point speed agree to 0.1 %, so arm rotation does not explain it. At efforts 0.010 and above the puck separates at 41 to 67 % of the controller's duration (author's E1 at mu 0.10: steps 13 to 26 of 24 to 64). At 0.010 to 0.020 the tool tip is then at 97 to 99 % of its peak speed and the puck leaves 7 to 15 % faster. At 0.030 the tool tip is still at 67 to 74 % of its peak and the puck leaves 42 to 58 % faster. The puck's peak speed exceeds the tool tip's at every effort of 0.010 and above. A calibration against the at-separation link speed fits one stroke profile at best. At the test push's effort it holds to 0.7 % for single-contact pushes, but it is 11 % off for the high-friction puck (a second contact), which is the tightest case of 4.3. A calibration against the command does better on this stroke at effort 0.015 and above (sd at most 1 %, probe A), but not at the test push's speed (5.4 % at 0.010).
- N3 (5.3) "Their lead-time controller's gentle stop makes the separation speed ill-defined at low speed": PARTLY WRONG. The last separation comes at the stop only at effort 0.005 and in the second-contact case (mu 0.15 at 0.010, step 61 of 64). At 0.010 and above it comes mid-stroke (N2), so a hard stop alone does not define the launch in this engine.
- N4 (4.3) The error budget omits three measured terms. (i) The separation point, which the probes read from the simulator (probe_puck_physics.py:91-94, 121-125) and arm O must infer: RP gives the puck-centre-to-tool-tip offset at separation as 67.4 to 69.8 mm over 16 trials, so about 1 to 2 mm after calibration, which is 1 to 2 % of mu at the short high-friction slide. (ii) The shot's forward-model error, which the literal of 2.3 has no term for: B already shows +3.5 % at mu 0.15 and launch 0.46 m/s (probe_analysis_out.txt:37). Two runs at the same friction and effort (mu 0.15, effort 0.03; the author's E1 in a reused world, my L1 in a fresh one; their joint paths differ slightly, as in N5) launched 0.35 % apart but slid 0.9012 and 0.8786 m. With the true mu_eff and the true launch, the model predicts 0.9045 and 0.8987 m: errors of 0.3 and 2.0 cm on a 21 cm window. (iii) The calibration body (N1, about 1.5 %). With (i) to (iii) the tightest case (x 0.53, allowance 9.8 % at e = 2 %) does not close. A second test push helps only against errors that are independent between pushes, and a calibration bias is not.
- N5 (4.5) "A reused world launched 0.6 % differently from a fresh one ..., so the arm's prior motor state matters": UNSUPPORTED. E1 and F1 used different joint paths, computed in different worlds (probe_puck_physics.py:152 against probe_puck_physics2.py:79), and one path in fresh worlds is bit-identical (2.1). The difference may come from the path and not from the motor state.
- N6 (1.5, 3.2) Selective use of probe A. Section 1 claim 5 ("launch speed set by the stroke, not by the friction, at most 1 % at effort 0.015 and above") supports the design, but T2 runs at effort 0.010, where the doc's own T1 row cites the variation (0.010 to 0.012 m/s, 5 to 14 %) against T1. The constraint is geometric, not a choice: to keep mu_eff 0.005 within x 0.80 from x 0.39, the test launch must be about 0.2 m/s (E1: effort 0.010 already ends at x 0.77).
- N7 (1.6) "TAMPURA's controller is not what limits it" holds for the controller WITH its four reset practice shots. Without them, their first trial puts 1 of 5 frictions in the goal (E4 trial 1: 2.039, 1.236, 1.042, 0.937, 0.846).
- N8 (3.2) "Why T2: it carries the same information as TAMPURA's channel". T2's estimator also needs the launch speed and the separation point (proprioception and contact timing), which TAMPURA's channel does not carry. TAMPURA instead replays the commanded motion in an exact world copy (env.py:221-223, 685). Overstated.
- N9 (9.3) "Minimal version, about 6 to 8 working days": not derivable from 9.1. The items it keeps (W0 1; W1 1; W2 2 to 3; W3 1.5; W4 without the eye, about 1.5 to 2.5; W5 for V1, V2 and V5, about 0.5 to 1; W6 on 20 seeds 0.5; a reduced W7, about 0.5) sum to about 8.5 to 10 (my arithmetic from the doc's own estimates). The full total "10 to 13" matches 10 to 12 days plus about 10 h of runs.
- N10 (4.4) Acceptance power. "V2 at least 19 of 20" is offered as a test of 95 % coverage, but 19 of 20 has a Wilson 95 % lower bound of 0.76 (the formula of gen_scene_eval.py:345). The pre-registered test cannot show 95 %. The test push alone is cheap (no TAMPURA), so V2 can run on 100 or more friction draws.
- N11 (3.2 T1, 4.5, R1) "Repeatability". In this engine, repeated trials from one state are bit-identical (2.1). The launch "sd" of probe A is a spread across frictions, not a repeat noise, so T1's "least repeatable" and R1's "launch speed less repeatable" name the wrong quantity. What can vary the launch for arm O is the friction during contact (measured, N2, N6) and the arm's state when the stroke starts (the approach, which differs per episode). W0 must therefore vary the approach rather than repeat one trial.

## 3. Rules check

| rule | finding | named in ARGUMENT? | cost to the paper's claims |
|---|---|---|---|
| H1 (PA:3256-3259) | The core design complies: one physical stroke, no resets, no reads of their belief or world, truth read only by the evaluator (V1, V2), mass-free. | the relaxations it offers are named: PS-Q2 (b) O-exact, PS-Q5 (b) and (c) | none for the core |
| H1, success scoring | H1 lists success scoring among the decisions no ground-truth read may feed (:3259). The shared test reads the real puck's true pose; the precedent is BF#36 and BF#37's world-state test (PA:7471-7484, 7518-7523). | BF#37 is cited, the H1 wording is not | none if Hani accepts the precedent; it should be named |
| H1 and G6/G12, arm O's reward | "Their reward reported beside it" needs, for arm O, a writer of their belief (G6, PA:3361) whose observation would carry a true puck pose. G12 (PA:3434-3436, rewards[-1]) has no puck_slide form. | no | either drop arm O's reward column or declare the true-pose observation as an evaluation-only exemption |
| G2 leak test (PA:3326-3329) | Separation detection must use "any pad contact", never contacts filtered by the puck's body id, or a body id reaches the belief. During the stroke the pads may also touch the slab. | no | a design constraint on push_execution.py |
| H2 (PA:3260-3264) | Moves, including the move to q_home, are planned; no plan editing. The planner's choice is fixed by the literal (probe until it holds, then shoot), which 10.4 concedes. | yes | none for H2; it weakens the "planner decides" claim |
| H3 (PA:3265-3269) | "Small" is not addressed: two actions, two streams, a belief component, an estimator and a new physical primitive. Friction is not a literal over named regions. The doc's paraphrase of H3 (C40) drops exactly these parts. | no | needs Hani's explicit acceptance as a relaxation of H3, with its M entry |
| H4 (PA:3270-3273) | Seeds 0 to 19, with 20 to 59 as an extension reported apart (D-6). Their tree is untouched: the hashes match (C79). | yes | none |
| G1 / G14 (PA:3285-3313, 3451-3471) | Ghost removal (removeBody) needs an allowlist entry and G14's D9 exception, which the doc invokes. Its label "non-task bodies" conflicts with the bridge's own table, which is built from world.objects (G8(a), PA:3380-3383), and world.objects holds all 20 pucks (env.py:378-380). | yes (PS-Q3, D-1), label wrong | small |
| G9 (PA:3399-3405) | Constants from their source and a re-measured engine damping: fine. W2 develops the stroke "on our table, then on their slab"; G9 forbids constants from instances and outcomes, so the doc should state that slab trials set no constant. | partly (4.4 says no constant is tuned on outcomes) | a commitment to add |
| G10, G20 | The goal pin gains obj_in_region (named). G20 (PA:3507-3510) compares every render's matrices with their shared pbu.get_image_at_pose at DEFAULT_ARM_POS. That path exists in their library and can be computed in the puck world, but puck_slide itself never renders, so the check would certify a sensor their task does not use (D-2). | G10 yes, G20 no | a sentence, not a gap |
| BF#35 (PA:7364-7416) | One environment: arm O's world drops the 19 ghosts (D-1) and adds the D4 eye (D-2). One criterion: test_in on the real pose, which equals their reward for arm T (C3 to C5). | yes | the deviations are honest and listed |
| BF#37, #P5 | Physical execution is kept; their geometry is used as a sampler (#P5's pattern). | yes | none |
| BF#66 (PA:9275-9351) | Logged as "far future work ... CLAIM EFFECT: none for this paper". The doc offers puck_slide as "the smallest real instance of BF#66 the paper could show". By the proposal's own words, M8's pose radius already is one (C74). | no | a claim effect Hani has not granted |
| Nothing edits a plan | Complies. | yes | none |
| No one-task tuning after a failure | Committed in 4.4. The push primitive is built for this task, so its pipeline-wide status rests on W0 and W2 on our own table. | yes | none if kept |
| Request: separate branch; cost on ours and theirs | Section 6 (`puck-slide` from tampura-bridge, generic and task layers) and section 7 (C0, C1, C2 on four of our rows, find_dice, class_uncertain later). | yes | none |
| A1 withdrawal (class_uncertain/BRIEF.md:54-84, 2026-11-06) | The design needs no object model (mass-free, pushable from perceived width). The friction prior and goal box are task-level knowledge TAMPURA's planner also has, which that brief allows (:73-77). | not discussed | none; worth one sentence |

## 4. Ranked objections (most verdict-changing first)

1. **The launch speed has no measured path to 2 %, and the evidence that exists points the wrong way.** The design closes only at about 2 % (4.3). The probes measured the launch from the simulator, which arm O cannot read. On the only stroke that exists, the proposed proprioceptive source fails where it matters: the high-friction test push (N2). The hard-stop stroke is unbuilt, and its premise ("the puck separates at the cruise speed") is contradicted on their stroke, where the puck leaves mid-stroke at 1.07 to 1.58 times the pusher's speed at that instant. The test push is pinned to about 0.2 m/s by geometry (N6), where even command-based calibration varies 5.4 % with friction. If W0 cannot fix this, nothing downstream matters, and W0 cannot measure "our stroke" before W2 has built it, so the go or no-go lands around day 3. What would answer it: a W0 spike with its pass criterion fixed in advance (for example, the 95th percentile of the launch-estimate error at most 2 %, over 3 frictions, a 1 kg 12 cm cylinder and our cubes, and at least 10 different approach configurations, since the engine is deterministic and only state differences vary the result); or a design that does not need the launch speed: renders of the early slide after the arm retreats (T3), which section 3.2 dismissed as "more information than TAMPURA's channel", although arm O's channel already differs (D-2) and TAMPURA replays the commanded motion in an exact world copy (D-4).
2. **Time and what it displaces.** 21 working days remain. The minimal version is at least 8.5 days by the document's own items (N9), plus what 9.1 leaves out: arm T's first local puck_slide run (R7, none exists), the gate adaptations (G7, G8's identity table for a 20-body world, G10, G12, G13, G14, G18 to G20), the M and BF# entries with their reviews, ledger rows, the GUI run for Hani and the paper text (about 2 to 4 more days, my estimate, UNVERIFIED). It competes with the class_uncertain plan and its implementation (the CLAUDE.md "go" section), BF#65's open finding (PA:9143), the pending B8 re-runs and CB#113 (PROPOSAL_ATTRIBUTE_BOXELS.md:253-254) and the writing. The document concedes the no-fit case's TIME figure (10.3). What would answer it: a dated schedule of every in-flight item that shows the spike's sunk cost (about 3 days to the go or no-go) and the remainder fit with slack.
3. **What the paper could claim.** Success would rest on a hand-built estimator, a new stroke and an analytic model of PyBullet's sliding law. The spatial machinery stands idle (conceded), and the planner's decision is fixed by the literal (conceded in 10.4). A win could come from TAMPURA's own quirks: the replay of the returned effort (C21; at mu 0.125 a 3.6 cm offset, E4), 20 particles, and the band from x 0.80 to 0.9 where its preconditions hold and its stroke finds no path (section 12 lists these as candidate causes). That would not count as evidence for the representation. BF#66 records no claim effect for this paper. What would answer it: one paper sentence that survives "your arm got a model of the engine's sliding law", plus a read-only per-episode log of the size of TAMPURA's replay mismatch, so that a gap between the arms can be attributed.
4. **Incomplete error budget, weak acceptance.** Three measured terms are missing (N4). The literal needs a forward-model error term, since shot landings scatter by up to 2 cm at a fixed launch. V2 at 19 of 20 cannot show 95 % (N10). What would answer it: the full budget, the literal with a model-error term, and V2 on 100 or more draws of the test push alone.
5. **Rules stretched without a name** (section 3): H3's "small" and region model; BF#66's claim effect; H1's success-scoring wording and arm O's reward channel (G6, G12); G2's body-id leak in separation detection. What would answer it: one PS-Q per item, each with options and its claim cost.
6. **A controller option is missing.** Their stroke shape (two IK configurations 5 cm apart, run by follow_path with a lead time, pb_utils.py:1312-1328) could be run physically after our own physical approach, without the resets and without follow_joint_path's set_joint_positions (env.py:388-393). It is H1-clean (its G1 and G3 wiring UNVERIFIED) and the only stroke with measured launch properties (command-based sd at most 1 % at effort 0.015 and above). PS-Q5 lists only ours, theirs at pc_steps 1, and theirs as is. What would answer it: add it as PS-Q5 (d); its weakness is the same slow regime (5.4 % at 0.010).
7. **Effort order and missing items** (N9, objection 2): W0 is placed before W2, but it needs W2's stroke.
8. **Cost study.** C1 is free by construction: with (pushable ?o) never true, the actions are pruned at grounding. On find_dice, e_cups_ud (76.7 mm, task_spec.py:25) sits 1.3 mm under the rule's threshold (0.08 minus PINCH_CLEARANCE 0.002, pose_belief.py:73). Whether perceived widths cross it is UNVERIFIED; on the mixed scene nothing qualifies (widest 70 mm, boxel_env.py:224-238). C2's pushes can never serve our goals, so C2 measures grounding and search overhead only. That is enough for Hani's question ("what did adding it cost") and should be said so; add a perceived-width check on find_dice.
9. **T1 is measured as something their nudge is not** (C15). It weighs little, since T1 is not adopted, but the comparison of test actions should describe what TAMPURA actually gets.

## 5. What fails, what survives with changes, what survives as written

Does not survive as written:
- Section 1 claim 5 as a basis for the design: the slide physics is simple (confirmed), but the launch, which the design depends on, is not (N2, N6).
- 4.1's launch-speed source (the link speed at the last contact through a calibration): it fails on their stroke (N2).
- 5.3's diagnosis that the gentle stop is the cause (N3).
- The mass figures of 4.1 and 4.3 (N1).
- 2.4's "smallest real instance of BF#66 the paper could show" (C74, section 3).
- 9.3's 6 to 8 days (N9).
- Section 11's "BF#66 is the latest" (C78).
- D-1's label "non-task bodies" (section 3).
- 4.5's motor-state attribution (N5).

Survives with changes:
- The interval belief and the literal (2.3): add a forward-model error term and the separation-point and calibration-body terms, and state that the interval property holds given a measured launch.
- The test action (3.2): re-compare T2 with T3, and with T2 plus visual launch estimation, on accuracy, arm occlusion after the stroke and render cost.
- The controller (5.3): add PS-Q5 (d) (their stroke shape, run physically).
- The error budget (4.3) and the acceptance (4.4): run V2 on 100 or more draws.
- The effort (9.1, 9.3): re-derive it and add the missing items.
- The decision list (11): add the launch-speed source with its pass criterion, H3, BF#66 and arm O's scoring channel; use BF#68 or later.
- PS-Q1: (b) narrowed to a W0 spike only, with a pass criterion fixed in advance; otherwise (c).

Survives as written:
- The reading of the request (push, not pick; section 0).
- The shared-criterion analysis: test_in on the real pose equals their reward for arm T (C3 to C5).
- The analysis of their controller: resets, model-based practice, kinematic approach, returned-effort mismatch (C17 to C25).
- Why adopting their controller breaks H1 (5.2).
- Deviations D-1 to D-6, apart from D-1's label.
- The branch plan: name, base, generic and task layers, and the shared-checkout risk (PS-Q7).
- The cost-study arms, metrics and acceptance (7.2 to 7.6), with objection 8's note.
- Reach and grasp (8.2, 8.3).
- No D9 for this task (8.4).
- The probe hygiene (their trees unchanged, C79, C80).
- The arithmetic listed in 2.2.

## 6. Gaps against AUTHOR_BRIEF.md

- Section 4 ("how we know we got it right") is present, but the go or no-go number has no statistic (2 % as a maximum? a 95th percentile? over which bodies and approaches?), and the acceptance it pre-registers cannot show the coverage it claims (N10).
- Section 5 ("design ours without that") is present, but the design is not shown feasible in the engine, and the only evidence (their stroke) contradicts its separation premise (N2, N3).
- Section 9 ("effort ... risks"): the missing items of objection 2. The risk list lacks the engine's contact behaviour (N2) as a named risk distinct from R1's "repeatability".
- Section 2 ("attribute boxels: say whether and how it fits"): answered, but without BF#66's logged decision and without the proposal's own statement that a commit-margin literal is nothing new (C74).
- "Mark ... UNVERIFIED": 1.4's statement that the MLO and WAO rows "determinise a learned outcome model (they share the Bayes-optimistic learning row)" carries no UNVERIFIED there, while 10.4 marks the same point UNVERIFIED.
- Section 1 runs well over a page (a form point only).
- Internal consistency: 3.1 says "after the shot the episode ends" and, two lines later, that a short shot leads to a replan; 5.3 step 5 moves the arm to q_home inside the push action, while 3.1 plans that move as its own step; 6 says "move back to the main line", but M8 to M10 and the gates live only on tampura-bridge (C75), so which branch is meant should be said.
- The brief's other requirements are met: all eleven sections exist; the probe folder is listed; the files are listed; the parallel wire_sb_into_tampura argument is pointed to, not duplicated (5.2); no dashes and no forbidden word (grep: 0 and 0).

## 7. Files made by this review, and what stays unverified

Made by this review (nothing else was written; nothing deleted):
- archive/tampura_bridge_plan_2026-10-25/puck_slide/REVIEW.md (this file)
- archive/tampura_bridge_plan_2026-10-25/puck_slide/review_probe/: run_review_probes.sh, rp_tree_hash.py, rp_tree_hash_out.txt, rp_tree_hash_variants.sh, rp_tree_hash_variants_out.txt, rp_damping.py, rp_damping_out.json, rp_damping_log.txt, rp_launch.py, rp_launch_out.json, rp_launch_log.txt, probe_analysis_rerun_out.txt, probe_puck_physics2_rerun_out.json, probe_puck_physics2_rerun_log.txt (about 110 kB in all).
- For DATA_LEDGER.md (not edited here, as instructed): review_probe/ is the evidence of this review (keep while the review stands). The two rerun outputs (probe_analysis_rerun_out.txt, probe_puck_physics2_rerun_*) are reproduction checks whose result is recorded in 2.1, and become garbage once this review is accepted. /root/ps_probe, the author's folder, was used as cwd only and is unchanged.

UNVERIFIED by this review:
- Whether a hard-stop stroke in PyBullet launches the puck at the pusher's speed (only their stroke was probed).
- PyBullet's default collision group for static bodies (C27).
- Whether perceived e_cups_ud widths cross the pushable threshold.
- The D4 view, by a render (arithmetic only).
- TAMPURA's success on our machines.
- The paper's numbers (taken from the survey).
- My estimate of 2 to 4 days of missing effort items.
