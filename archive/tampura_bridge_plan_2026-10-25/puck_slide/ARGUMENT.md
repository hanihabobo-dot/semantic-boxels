# puck_slide: the case for running Semantic Boxels on it, with a design

Written 2026-11-06 by an agent for Hani, on branch `tampura-bridge` (HEAD
d6a9715 when written, f979e56 to 1b6fa2b while revised; the other sessions' uncommitted
hunks untouched). Read only, except this folder and the probe folder
/root/ps_probe in WSL: no code, audit, ledger, CLAUDE.md or branch was
changed. Every claim carries its evidence class.

Revised the same day after the adversarial review in this folder
(REVIEW.md, verdict "survives with changes"; its probes in review_probe/).
The design changed where the review holds: the friction is now read from
renders of the free slide (T3, 3.2 and 4.1), which needs neither the test
push's launch speed nor its separation point; the error budget has its
missing terms (4.3); the shot's launch calibration and a time-boxed spike
decide go or stop before anything is built (9.2); four stretched rules are
put to Hani by name (section 14). Section 13 answers every review point,
section 14 holds the final verdict and the revised decisions.

Evidence classes:
- READ: code read in this session. Ours cited relative to the repo. Theirs
  as a path under /root/tampura-work; `env.py` alone means
  /root/tampura-work/tampura_environments/tampura_environments/puck_slide/env.py.
  PAPER_AUDIT.txt (PA) lines, and those of the live STATE.md files, are
  the working tree's at 15:45 on 2026-11-06 (HEAD 1b6fa2b, with the other
  sessions' uncommitted hunks). Other sessions edit these files all day:
  if a cited line has moved, search for the quoted entry. (Since the first
  revision, commit bbbe2fa lengthened BF#68 by 11 lines, and
  tracks/STATE.md was rewritten; the cites below are updated to 15:45.)
- MEASURED: this session's read-only probes of their world (probes 1 to 4
  and an occlusion check, section 4.5; scripts, logs and JSON in this
  folder) and the review's two (RP = review_probe/: rp_launch.py,
  rp_damping.py).
- SURVEY, NO-FIT: taken from TAMPURA_TASKS_SURVEY.md or no_fit_case.md
  (both in ../class_uncertain/), not re-read at the source.
- UNVERIFIED: not checked. Every effort or run time is marked "estimate".

## 0. How the request is read

Hani's request of 2026-11-06 asks for six things:
1. A strong argument for puck_slide that survives review, as he had just
   asked for another direction ("the same"): sections 1 and 10.
2. "some of the input is unknown so we make a version of our model with the
   pick actions": read as PUSH actions. A pick cannot apply: the puck is
   12 cm across (PUCK_RADIUS 0.06, env.py:33) and their Panda's fingers
   open 0.04 m each (/root/tampura-work/tampura_environments/models/srl/franka_panda/panda.urdf:348, 355),
   8 cm in total. The "version of our model" is the friction literal of
   section 2 plus the push actions of section 3. If he did mean pick: no
   pick exists for this object, and the nearest reusable action is the
   relocation push of 3.4.
3. "an action that helps us test how slippery it is unless you have some
   other suggestions": section 3.2 compares six test actions, recommends one.
4. "how are we supposed to know how get it right": section 4 (estimator,
   validation, pre-registered acceptance).
5. "measure how much did adding it costs us ... on some of our envs tasks
   and tampuras tasks as well": section 7.
6. "another branch where we be building a version just for this task":
   section 6.

Binding rules applied throughout: H1 to H4 (PAPER_AUDIT.txt:3256-3273), G1
(:3285-3313), BF#35 (:7364-7416), BF#36 and BF#37 (:7418-7526), #P5
(:9418-9436; BF#68's entry has moved it down from :9354 since the first
version). D9's
physics set-up is not applied to this task (8.4). Where the design stretches
a rule (H1's success scoring, H3, BF#66's claim effect, arm O's reward
channel), it says so and section 14 puts it to Hani with its cost.

## 1. The case in one page

The no-fit case (no_fit_case.md 2.6) rejects puck_slide because Semantic
Boxels cannot touch the puck and its regions and search would stand idle.
Both are true of the system as it is today. The argument here is that
puck_slide is the one TAMPURA task on which a contained, reusable extension
(not small in H3's sense, claim 3) gives a comparison cleaner than
find_dice's, and that it tests a claim the paper cannot otherwise support.

1. One environment and one criterion with no scoring adapter. Their reward,
   in(puck, goal0) (env.py:745), is computed on the believed pose, and the
   believed pose is the observed pose of the real puck (env.py:228,
   540-545). Their own test_in (env.py:660-672) can therefore be applied by
   an evaluator to the real puck's final pose in both arms' worlds, and for
   TAMPURA it equals its reward by construction. find_dice needed BF#35 to
   BF#37 and the still open Q18 (PAPER_AUDIT.txt:7490-7492) to get there.
2. Both arms push physically. puck_slide is the only TAMPURA task whose
   stroke runs a motor controller and steps physics (follow_joint_path,
   env.py:384-415; SURVEY section 3). The kinematic carry that made
   find_dice asymmetric (their die cannot slip, BF#35 at
   PAPER_AUDIT.txt:7370-7384, the root of the BF#59 campaign) has no
   counterpart here. Their approach to the stroke is still kinematic and
   their practice trials reset the world (5.1); ours would be physical
   throughout (BF#37).
3. It tests the generality claim a reviewer will ask about. H3 admits
   model tweaks only if small and expressible in the thesis's POD model,
   which it lists: belief as literals over named regions, a sense action
   with a deterministic observation, hidden regions as belief volumes,
   discovery by relocation and sensing, optimistic determinisation,
   replanning (PAPER_AUDIT.txt:3265-3269). M8 added the commit margin and
   applies a K-literal set by observation to a continuous quantity, the
   pose radius (:4456-4469; pose_belief.py:327-331). Applied to friction:
   "a shot commits on a friction only within what the goal window
   tolerates; otherwise the planner must plan the test push that can
   guarantee it". Two parts of H3 do not hold, and section 14 puts them to
   Hani as a named relaxation (PS-Q13): friction is not a literal over a
   named region, and the extension is not small (two actions, two streams,
   a belief component, an estimator and a new physical primitive). The
   friction literal is also an instance of the recipe of Hani's attribute
   boxelization (PROPOSAL_ATTRIBUTE_BOXELS.md:235-237), but the proposal
   itself calls the commit-margin literal "already a two-level value
   boxelization; nothing to add" (:231-232), and BF#66 is logged with
   "CLAIM EFFECT: none for this paper" (PA:9275, 9350); this document
   claims nothing from BF#66 unless Hani grants it (PS-Q14).
4. It is the task on which the paper reports determinisation as weak: on D,
   BayesOpt+MLO 0.29 and BayesOpt+WAO 0.24 against TAMPURA 0.52 and DQN
   0.47 (SURVEY, Table I). Those rows determinise a learned outcome model
   (they share the Bayes-optimistic learning row; whether that is
   TAMPURA's own learned model is UNVERIFIED, no_fit_case.md 3.4). The
   design here determinises an explicit physical model whose error is
   bounded and checked. Which way that goes is the experiment's result,
   not an assumption of this document.
5. The slide is simple; the launch is not (revised after the review, N6).
   MEASURED (4.5): the free slide follows Coulomb friction plus PyBullet's
   default velocity damping, which is exactly 0.04 v + 0.04 v^2 (RP
   rp_damping.py); the law fits a whole slide to within 0.16 mm, at an
   effective friction 1.5 % below the product of the puck's and the slab's
   (slab 0.1, env.py:314), up to launches of 0.44 m/s, and departs by up to
   2.6 % in 3 of 5 cells at 0.47 to 0.55 m/s (probes 3 and 4). The launch
   is set by the contact solver: the puck leaves mid-stroke 7 to 58 %
   faster than the pusher (RP L1), and the test push, pinned near 0.2 m/s
   so that a slippery puck stays in reach, is the regime where it varies
   most with the friction (5.4 % across frictions at effort 0.010, mostly
   from a second contact at the highest friction). The first version's
   claim that "the launch speed is set by the stroke, not by the friction"
   used only the efforts of 0.015 and above. The design therefore reads the
   friction from renders of the free slide (T3), which needs no launch
   speed; the shot still needs its launch (4.3).
6. TAMPURA's controller, WITH its four reset practice shots, is not what
   limits it (MEASURED): with the friction exactly known, their five-trial
   controller lands all five probed frictions in the goal (x 1.262 to
   1.305). Without the practice, their first trial puts 1 of 5 in the goal
   (E4 trial 1: x 2.039, 1.236, 1.042, 0.937, 0.846). So what moves
   TAMPURA's success is the friction estimate, given its practice (my
   inference); our arm has no practice shots, so for us the controller's
   one-shot precision matters as much as the estimate (4.3).
7. It is cheap to run: one geometry; the seed draws the friction, the 19
   particle frictions and every nudge direction (env.py:681, 354, 655);
   TAMPURA needs about 1.4 min per episode (SURVEY arithmetic, 3.75 steps x
   23 s = 86 s; UNVERIFIED on our machines).
8. The new parts are reusable. A physical push whose target is a planner
   parameter is what the audit #53 discussion left open ("Push could still
   be used as the underlying motion primitive",
   archive/CODEBASE_AUDIT_DEFERRED.txt:465-467), and physics-based pushing
   "for heavy objects" is on the backlog (archive/CODEBASE_AUDIT_FINAL.txt:167-168).

What a result would show the paper's readers, and what it would rest on:
- It rests on a hand-built estimator, a new stroke and an analytic model
  of PyBullet's sliding law (Coulomb friction plus the engine's default
  damping, both MEASURED in this engine: the damping law exactly, RP
  rp_damping.py; the friction product within 1 to 2.5 %, F1). The paper
  sentence that has to survive "your arm got a model of the engine's
  sliding law" is: both arms are given a model of the dynamics; TAMPURA's
  is the simulator itself with an exact copy of the task world except the
  friction (env.py:685, 236-245), ours is the sliding law with the
  simulator's damping constants, measured once on an empty table (D-4).
- If arm O (ours) does at least as well as arm T (TAMPURA): a deterministic
  planner over a K-literal, with an explicit physical model and a
  set-membership estimate, solves TAMPURA's own physical-uncertainty task at
  least as often, and the executed-step and planning-time counts say at
  what price. The pattern of the POD model is then shown to cover a hidden
  physical attribute and not only hidden locations, and the paper's
  determinised rows on D are put in context. A gap could also come from
  TAMPURA's own quirks: the replay of the returned effort (C21 of the
  review: 3.6 cm at mu 0.125, E4), its 20 particles, and the band from x
  0.80 to 0.9 where its preconditions hold and its stroke finds no path
  (8.3). The read-only attribution log of 4.4 (V7) measures each per
  episode, so that a gap is not credited to the representation by default.
- If arm O does worse: a measured limit of one-shot commitment under a
  bounded-error estimate. The positive control of 4.4 says whether the
  estimate or the controller is at fault, so the limit is diagnosable.
- Either way, the cost study of section 7 says whether the added actions
  are free when unused: a statement about the modularity of the POD domain
  that an ICAPS reader can check.
- It does not show anything about occlusion, shadows, search or the
  semantic partition in space. Conceded (section 10).

## 2. Modelling the unknown friction

### 2.1 What is hidden, in our terms
The outcome depends on the combined coefficient mu_eff = mu_puck x mu_slab
(MEASURED: the product holds within 1 to 2.5 %, probe F1), with mu_puck
uniform in [0.05, 0.15] (env.py:63-64, 681) and mu_slab 0.1 (FRICTION_MID
on the surface, env.py:65, 314). Our arm never needs mu_puck or mu_slab
alone: it estimates mu_eff, which is what the slide depends on and what a
push reveals.

### 2.2 Options
| option | what it is | verdict |
|---|---|---|
| particle belief, as theirs | 20 particle pucks in an exact copy of the world, Gaussian likelihood on the final xy, resampling with jitter (env.py:108-229, 685) | rejected: the planner reads literals, so a particle set is compressed to a literal anyway, and their likelihood runs a copy of their world that our arm cannot build without reading it (H1) |
| discretised probabilistic belief | k friction bins with masses | possible, but no action cost or precondition of this task reads a probability; BF#60 parked probabilistic search order (PAPER_AUDIT.txt:8764) |
| interval belief with a K-literal (recommended) | the set of mu_eff values consistent with every observation so far under a declared error bound; (friction_known o) emitted iff the interval fits the shot's commit margin | exact under the bound; the planner sees one literal, as with obj_pose_known |

### 2.3 The recommended model
- Belief: an interval I = [lo, hi] on mu_eff per pushable object, kept
  beside the object's boxel.
- Prior (decision PS-Q4): [0.005, 0.015], their FRICTION_LOWER and
  FRICTION_UPPER times FRICTION_MID (env.py:63-65): constants in their
  source, allowed by G9 (PAPER_AUDIT.txt:3399-3405). Their planner has the
  same range: its particles are drawn from it, uniform in 1/friction
  (env.py:353-356); the interval carries no distribution, so the two arms'
  priors share their support, not their shape (D-5).
- Update (revised after the review): after a test push, the estimate
  mu_hat from our renders of its free slide (T3, 4.1), which needs no
  launch speed and no separation point, and the declared relative bound b
  of that estimate (the 99th percentile error of 4.3 at our perception's
  noise): I := I intersected with [mu_hat / (1 + b), mu_hat / (1 - b)].
  The result is again an interval, and the representation is exact under
  the declared bound: it contains the truth whenever the estimate's error
  is within b, the property PROPOSAL_ATTRIBUTE_BOXELS.md 3.3 shows for the
  hiding-spot belief under a perfect sensor. V2 (4.4) tests the bound.
- The literal: (friction_known o) iff a launch speed v exists with
  slide(v (1 - e), hi) (1 - m) >= W_near and
  slide(v (1 + e), lo) (1 + m) <= W_far, where [W_near, W_far] is the
  free-slide window from the object's believed pose to the goal region, e
  the shot's declared launch-speed error and m the declared relative error
  of the slide law over the shot's slide (the forward-model term the review
  found missing: 2.0 cm on a 0.88 m slide at a measured launch of 0.55 m/s,
  RP L1 against the model). m depends on the shot's speed (MEASURED, 4.3):
  about 1 % up to 0.44 m/s, at least 2.6 % at 0.47 to 0.55 m/s. The slide
  is monotone in both arguments, so the two endpoints decide it. With
  Coulomb alone it reads
  hi/lo <= (W_far/W_near) (1 - e)^2 (1 - m) / ((1 + e)^2 (1 + m)); 4.3 (C)
  checks it with the damped law.
- The window, from their constants (G9). The goal box spans x 1.2 to 1.4
  and test_in accepts a centre within 1 cm of it (env.py:49-56, 660-672);
  the slab ends at x 1.40 (surface centred at x 0.55, 1.7 m long,
  env.py:306-313, 329-333), beyond which the puck falls and off-table holds
  (z < 0, env.py:151-152). So the usable centre window is [1.19, 1.40].
  From the start (x 0.39) the slide window is [0.80, 1.01] m, ratio 1.262
  (a perfect shot tolerates mu_eff within a factor 1.124 of its aim). From
  where the recommended test push leaves the puck (x 0.53 to 0.77,
  MEASURED) the ratio is 1.32 to 1.50, a factor 1.148 to 1.224
  (probe_analysis_out.txt, D).
- Emitted in _build_init beside obj_pose_known (pddlstream_planner.py:721-763).

### 2.4 Attribute boxels: does it fit, and how
It fits, as PROPOSAL_ATTRIBUTE_BOXELS.md section 5 (values of fluents) and
its recipe "cut the range exactly where some precondition or stream answer
flips" (:235-237). The cut points on the friction axis are where one shot
stops covering the interval: from the start, ln 3 / ln 1.262 = 4.7, so about
five friction classes cover the prior; from x 0.77, ln 3 / ln 1.50 = 2.7, so
three (my arithmetic, perfect controller). The planner never needs the class
index, only whether the belief lies inside one class, which is the literal
of 2.3. The interval is the value boxel. None of the proposal's mass
machinery (its application A) is needed and none of its open options has to
be decided first. What it is not (corrected after the review): it is not a
new instance the paper can claim. The proposal says the pose-radius commit
margin "is already a two-level value boxelization; nothing to add"
(PROPOSAL_ATTRIBUTE_BOXELS.md:231-232), the friction literal has the same
two levels, and BF#66 is logged as far future work with "CLAIM EFFECT: none
for this paper" (PA:9275, 9346-9351). The fit is recorded here as design
consistency only; a claim needs Hani's grant (PS-Q14).

### 2.5 POD justification (draft for the model-tweak entry)
"A shot commits on a friction only within what the goal window tolerates;
when the belief cannot guarantee it, the planner must plan the test push
that can (a K-literal set by observation)." This is M8's sentence
(PAPER_AUDIT.txt:4467-4469) with friction in place of pose. H3 asks for an
audit entry with BEFORE, AFTER and CLAIM EFFECT lines; it would take the
next M number (a grep of PAPER_AUDIT.txt finds no M11; grep again before
claiming). The entry cannot say the tweak meets H3 as written: H3's
"small" and its "literals over named regions" do not hold (1, claim 3).
Its CLAIM EFFECT line would read: "extends the POD model by a K-literal
over a hidden scalar attribute of an object, outside H3's region-based
model; accepted by Hani as a named relaxation (PS-Q13)", or the work does
not start.

## 3. New actions

### 3.1 The actions
Generated as M8's delta is (m8_domain.py:39-113), behind a switch that is
off by default; off, the planner reads the live domain byte for byte
(m8_domain.py:127-136).
```
(:action probe_push                     ; the test push of 3.2 (T2's push, read by T3)
  :parameters (?o ?q ?s)
  :precondition (and (Obj ?o) (pushable ?o) (handempty) (at_config ?q)
                     (obj_pose_known ?o) (probe_stroke ?o ?q ?s)
                     (not (friction_known ?o)))
  :effect (and (friction_known ?o)        ; OPTIMISTIC, as sense's "assume found"
               (not (obj_pose_known ?o))  ; it moved; a disturbed pose is unknown (M8)
               (increase (total-cost) 1)))
(:action shoot                          ; push-to a region
  :parameters (?o ?r ?q ?s)
  :precondition (and (Obj ?o) (pushable ?o) (handempty) (at_config ?q)
                     (obj_pose_known ?o) (friction_known ?o)
                     (shot_stroke ?o ?r ?q ?s))
  :effect (and (obj_in_region ?o ?r) (not (obj_pose_known ?o))
               (increase (total-cost) 1)))
```
- The observation is part of the push action (revised after the review):
  the D4 eye is a fixed eye (tampura_bridge/task_spec.py:66-75), but the
  arm blocks it in the push posture (MEASURED, 4.2), so the action's
  stroke primitive ends with a retreat out of the eye's view (5.3), and
  the eye then renders the free slide at known simulation steps and the
  resting puck (T3, 4.1). The rest render re-poses the puck (pose_radius
  from a complete detection, as M8's pose writers do). The retreat is part
  of the planned action, so the arm makes no motion outside one (H2), and
  the next move starts from where the retreat ended. A render in which the
  puck is not seen whole is dropped.
- Streams: probe-stroke(?o) gives (?q ?s): the launch speed that keeps the
  object reachable after its slide for the interval's lowest friction, the
  direction toward the goal region's centre, ?q the pre-push configuration
  from IK on the plan twin. shot-stroke(?o ?r) gives (?q ?s): the speed
  from the interval and the window as in 2.3. Both evaluate the slide model
  of 4.1; neither reads the world.
- (pushable ?o): a static fact from perception under a pipeline-wide rule
  (decision PS-Q8): the perceived width on every grasp axis exceeds the
  opening, 0.08 m, less the pinch clearance (PINCH_CLEARANCE 0.002,
  pose_belief.py:73), so 0.078 m. In puck_slide it holds for the puck; on
  our tables for no current object (cubes of 3 to 5 cm; the mixed scene's
  widest is the 70 mm cylinder, boxel_env.py:228, 238). On find_dice,
  e_cups_ud (76.7 mm, tampura_bridge/task_spec.py:25) sits 1.3 mm under the
  threshold; whether its perceived widths cross it is UNVERIFIED, and the
  cost study checks it (7.3).
- Goal: (obj_in_region puck goal0). G10's goal pin (PAPER_AUDIT.txt:3413-3422)
  gains this form on the branch.
- (obj_pose_known ?o) for a pushable object needs its own margin (how far
  off the centre line a stroke may meet the puck), set from our own
  calibration as M8's commit margin is (pose_belief.py:303-331); a W3
  detail.
- The plan the planner should find from the start: move, probe_push,
  move, shoot. After probe_push's observation the literal is true or
  false, and the replan follows from it. Optimism and replanning work as
  for sense (domain :127-163).
- After the shot (made consistent after the review): the goal lies
  outside the D4 view (4.2), so our arm cannot confirm success and does not
  try; the shot's own observation re-poses the puck only if it rests
  inside the view. Then the loop replans once more. If the puck rests
  beyond the view or beyond reach, no stroke stream succeeds, the planner
  finds no plan, and the episode ends there; if a short shot leaves it in
  reach, a further shot may be planned. The evaluator scores the final
  pose (8.1).

### 3.2 The test action: six candidates
| | action | information | cost and risk | verdict |
|---|---|---|---|---|
| T1 | their nudge (corrected after the review): a push toward the ik region's centre (0.6, 0) plus a sampled 0.2 m offset that is mostly sideways (env.py:601-657, the offset at :654-657), so from the start pose the push runs about 44 degrees off the slab axis toward about (0.6, 0.2); five trials (env.py:622-630) that reset the arm and every puck before each and update the effort from the median x of the 20 pucks after each (env.py:509), starting at 0.005, so only trial 1 runs at 0.005 and only the last trial's outcome stays | what it gives TAMPURA: the final pose after the corrected stroke, compared in its belief with the particles' replays. Not measured as executed. E3 (one trial at 0.005) is not what their nudge executes; it shows only that a slow push at 0.005 tells mu 0.075 and 0.10 apart poorly (0.148 and 0.148 m), and at that speed the launch varies most with the friction (5 to 14 % across frictions, probe A; a dependence, not noise, since the engine is deterministic, RP L3) | its five trials need puck and arm resets (H1); the puck ends 38 to 40 degrees off the goal axis (E3's dx, dy) | not adopted |
| T2 | forward test push along the goal axis, at a launch speed that keeps the puck reachable for the interval's lowest friction, read from the launch speed and the rest pose | MEASURED at their effort 0.01 (launch about 0.19 m/s): end x 0.53 to 0.77 for mu 0.05 to 0.15, inside their geometry's reach of x 0.80 (E1, E5); mu_eff recovered within -1.5 to -1.9 % GIVEN the launch speed (C). The launch is the weak input (review N2, N4): on their stroke the puck leaves mid-stroke 7 to 15 % faster than the pusher at this speed, the last-contact source is 11 % off when the high friction makes a second contact (RP L1), the separation point must be inferred (67.4 to 69.8 mm from the tool tip, RP), and the test speed is pinned near 0.2 m/s by reach (N6) | one physical push, no reset; 2.1 times the launch error in mu (C) | the push is kept; its reading by launch speed is withdrawn |
| T3 | the same push, read from renders of its free slide: the deceleration, with the speed at the first render as a free parameter (recommended after the review) | MEASURED (probe 3 S1, 21 frictions x 100 draws, renders from 6 steps after the last contact at 60 Hz plus the rest pose): p95 and p99 of the relative error 3.0 and 3.8 % at 1 mm position noise, 4.4 and 6.4 % at 2 mm, 5.6 and 8.9 % at 3 mm; worst friction (0.15) 8.0 and 9.4 % at 2 mm; these include the engine's -1.5 % offset, which cancels in the shot (4.1). At 20 Hz: 6.0 and 8.5 % at 2 mm. From 24 steps after the stroke command ends: 8.3 and 12.6 %. Three renders: 18.5 and 25 % (not usable). No launch speed, no separation point, no mass | needs an eye that sees the early slide. MEASURED: the D4 fixed eye sees nothing of the puck while the arm holds the stroke's end pose (0 of 140 renders over three frictions, probe 3 S3), and the wrist camera looks straight down there (89 deg) and loses the puck at once; their joint-space retreat to DEFAULT_ARM_POS clears the D4 view 0.18 to 0.38 s after the stroke ends but sweeps the hand through the puck (probe 4 R). 0.2 to 0.6 s per 640 x 480 render (S3, V). A track is more than TAMPURA's channel (the final pose), which TAMPURA interprets through an exact world copy (D-2, D-4) | recommended, with the sensor decision PS-Q12 |
| T4 | slow in-contact push reading the contact force, mu = F / (m g) | needs the mass, of which our arm has no model; 0.05 to 0.15 N for 1 kg at mu_eff 0.005 to 0.015, against PyBullet's contact-force noise (UNVERIFIED) | weak | rejected |
| T5 | lift or tilt test | none: no grasp (section 0) | | impossible |
| T6 | no test, one blind shot | covers mu_eff within a factor 1.124 of the aim: about 23 % of the uniform prior when aimed at its centre, at most about 31 % with the best aim (near the high end) (my arithmetic, Coulomb form, 2.3) | | the negative control V6 |

Why the T2 push read by T3 (revised after the review). The first version
said T2 "carries the same information as TAMPURA's channel"; withdrawn
(N8): T2's estimate also needs the launch speed and the separation point,
which TAMPURA's channel does not carry, because TAMPURA replays the
commanded motion in an exact world copy (env.py:221-223, 685) and our arm
has no such copy (H1). Reading the same push by its track removes both
inputs. What stays: it is one physical push, and it serves the goal twice,
measuring the friction while bringing the puck forward, which widens the
shot's tolerance from a factor 1.124 to between 1.148 and 1.224 (2.3). A
second test push is planned only when the first leaves the literal false;
the likeliest case is a high friction with a short slide (S1's worst
errors are there) whose shot would need more than 0.44 m/s, the range in
which the slide law is measured to hold (4.3).

### 3.3 What could be reused in other SB tasks
- The stroke primitive (approach, Cartesian stroke with a speed profile,
  separation detection, retreat): any push of a body the gripper cannot
  span or should not lift. Our widest find_dice class, e_cups_ud, is
  76.7 mm across (tampura_bridge/task_spec.py:25), at the edge of the 80 mm
  opening.
- probe_push and the interval literal: any scalar hidden attribute with a
  monotone response to a test action (friction, or mass through a push).
- shoot: specific to goals reached by a free slide; the least reusable.

### 3.4 Optional third action
advance(?o ?b): a slow in-contact push to a reachable boxel that ends with
the gripper stopping, so little free slide follows. On our tables it is the
relocation push (an occluder too wide to grasp moved out of a view
corridor); on puck_slide it could take the puck to the reach limit, where
the shot's tolerance is widest. Not in the minimal version.

## 4. Estimation and validation

### 4.1 The estimator, within H1 (revised after the review)
- Inputs (T3): our own renders of the puck's free slide at known
  simulation steps, from the first step without any pad contact of the
  robot, and the render of the resting puck (4.2). The speed at the first
  render is a free parameter of the fit, so neither the launch speed nor
  the separation point is an input. "Without any pad contact" is read from
  the robot's side only: G8(b) keeps the executor's tactile queries with
  bodyA = robot legal (PAPER_AUDIT.txt:3384-3391), and G2's leak test
  forbids a body id from such a list reaching the belief (:3326-3329), so
  the rule is "no pad contact with anything but the support", never a
  contact filtered by the puck's id (added after the review). A pad
  contact after the first render voids that push's track: the interval
  stays as it was. Nothing else: not their PuckSlideBelief
  (env.py:108-229), not their sim world (env.py:685), not the puck's or the
  slab's dynamics.
- Model: dv/dt = -(mu_eff g + k1 v + k2 v^2), g = 9.8 (their gravity,
  env.py:258), k1 = k2 = 0.04, which is exactly PyBullet's default damping
  (MEASURED by the review: RP rp_damping.py, fit 0.0400 and 0.0400). Closed
  form and a least-squares fit of (s1, v1, mu_eff) to the along-track
  positions (probe_slide_track.py, functions slide and fit_track). It
  applies to the bodies of our own scenes too, so it is pipeline physics,
  not a puck_slide constant; it is re-measured on our own table before use
  (G9's "scene-independent probe on an empty table",
  PAPER_AUDIT.txt:3399-3405), and no trial on their slab sets a constant
  (G9; a commitment added after the review).
- What it measures (MEASURED, probe 3): the friction that governs free
  sliding in this engine, which lies 0.9 to 2.1 % below Bullet's product
  0.1 mu (median -1.5 %), at the test push's 0.17 to 0.2 m/s (S1) and at
  0.28 to 0.37 m/s alike (S2: -1.3 to -1.8 %). The law fits the whole free
  slide to within 0.16 mm (S1, no noise). The shot's slide follows the same
  effective friction, so the offset cancels in the shot; it shows only
  against the evaluator's 0.1 mu, and V1 reports it as an engine property.
- Mass-free (corrected after the review, N1): the free slide does not
  depend on mass, and T3 needs no launch, so the estimate needs no mass
  model (decision PS-Q9). Mass still enters the shot's launch: 0.5 to 2 kg
  moves the launch at effort 0.010 by 3.6 % and 1 to 2 kg by 2.3 % (F2);
  the design case, a calibration on a light body of ours applied to the
  1 kg puck, is +1.6 % at effort 0.010 and +1.4 % at 0.020 (RP L2); 4.3
  carries it as a term of e.
- Withdrawn after the review (N2): the first version took the launch speed
  from the contacting link's speed at the last pad contact through a
  calibration. On their stroke the puck leaves mid-stroke, 7 to 58 % faster
  than the pusher at that instant, and the ratio falls from about 1.14 to
  1.017 when a second contact occurs (RP L1: mu 0.15 at effort 0.010), an
  11 % error in exactly the tightest case.

### 4.2 Observation channel (decision PS-Q2)
TAMPURA observes the exact pose of the real puck after each push
(env.py:543-545). For our arm:
- (a) Our perception, recommended. The D4 eye is their camera_frame at
  DEFAULT_ARM_POS as measured for find_dice (tampura_bridge/task_spec.py:66-75),
  and setup_puck_world puts the arm at DEFAULT_ARM_POS (env.py:371-376), so
  the camera is their robot's own. MEASURED by render now (probe 4 V, arm
  at DEFAULT_ARM_POS, the puck at rest on y 0): the whole puck is seen from
  x 0.40 (12045 pixels) to 1.00 (3541); at 1.10 and 1.19 it touches the
  image border, at 1.30 it is out of view. So the eye covers all of the
  slab the arm can reach, not the goal (the first version's arithmetic said
  x 0.31 to 1.19). A stand-in centre estimate (the top face's extents,
  probe shortcut) is within 0.03 to 0.42 mm in x and 0.42 to 1.42 mm in y of
  the truth from x 0.40 to 1.00 (V). Our arm needs no view of the goal,
  since nothing remains to do after the shot. H1 holds as written,
  perception does real work, and the channel is noisier than theirs: a
  handicap, the reverse of tool_use's sighted against blind problem
  (no_fit_case.md 1.4).
- The arm blocks this eye (MEASURED after the review): with the arm at the
  stroke's start or end pose the render holds no puck pixel; the robot
  covers 202752 of the 307200 pixels at the end pose
  (probe_occlusion_check_log.txt), and 0 of 140 renders during three test
  pushes see the puck (probe 3 S3). The eye sits where the wrist camera is
  at home, in the space the arm's upper links pass through when it reaches
  down to push. The wrist camera at the stroke's end looks straight down
  (89 deg) and loses the puck at once (S3). Every render our arm uses, the
  rest render before a shot included, therefore needs the arm out of the
  eye's view first: a retreat inside the push action (5.3). Their
  joint-space path to DEFAULT_ARM_POS clears the view 0.18 to 0.38 s after
  the stroke ends, at peak joint speeds of 5.2 and 2.6 rad/s, but sweeps
  the hand through the puck in every trial (probe 4 R: contact after the
  stroke, the puck pushed 5 cm on or off the slab). The 0.38 s case peaked
  at 2.6 rad/s, above our limit of 2.175 rad/s for joint 1
  (robot_utils.py:160-162), so that path would take longer under our
  limits; whether a shorter Cartesian retreat, back then up, clears the
  view sooner is UNVERIFIED.
- (b) Their exact pose: identical to theirs, but a true-pose read, which
  H1 forbids (PAPER_AUDIT.txt:3256-3259) unless declared as G8(d) declares
  the identity map (:3396-3398). Useful as a labelled diagnostic arm,
  O-exact, to separate perception error from the rest.
- (c) An overhead fixed eye of our own over the slab, added after the
  probes: it would see the early slide with the arm in place, which T3
  needs most at high friction (4.3). It is a sensor neither TAMPURA's task
  nor the find_dice bridge has, so its pose is a new constant (G9 requires
  a BF# entry deriving it once from their slab's constants), G20 needs a
  puck_slide form, and it is a further deviation (D-2). Decision PS-Q12.
- Identity map: world.objects[0] is the real puck. Their store binds the
  puck symbol to objects[0] of the sim world (env.py:689), and the
  executing world creates the real puck first (env.py:346-351).

### 4.3 Error budget (rewritten after the review; MEASURED on their world unless marked)
The first version budgeted T2 with four rows and said the design "closes on
paper if the launch speed is known to 2 %". The review found three
measured terms missing (N4: the separation point, the shot's forward-model
error, the calibration body) and no measured path to the 2 % (N2, N6).
Conceded: with T2 the tightest case does not close (with the review's
terms the linear sum exceeds the 9.8 % allowance, and a second contact
alone costs 11 %). The rewrite splits what the shot depends on into the
friction estimate (A, now T3) and the shot itself (B), and checks the
literal exactly with the damped law (C, probe_closure.py).

(A) The friction estimate, T3 (probe 3):
| term | size | where |
|---|---|---|
| the engine's effective sliding friction against 0.1 mu | -0.9 to -2.1 %, median -1.5 %, at 0.17 to 0.2 m/s; -1.3 to -1.8 % at 0.28 to 0.37 m/s. It cancels in the shot (the shot slides under the same friction) and shows only in V1 | S1, S2 |
| the law's fit to a whole free slide, no noise | at most 0.16 mm | S1 |
| position noise, renders at 60 Hz from 6 steps after the last contact, plus the rest | p99 of the relative error over the prior: 3.8 % at 1 mm, 6.4 % at 2 mm, 8.9 % at 3 mm; at mu 0.15 (the shortest slide) 9.4 % at 2 mm | S1 |
| the same when the view clears only 24 steps after the stroke command ends | p99 12.6 % at 2 mm (late schedule); a real retreat clears it later still (4.2) | S1; probe 4 R |
| our perception's position error | a stand-in on D4 renders of the resting puck: 0.03 to 0.42 mm in x, 0.42 to 1.42 mm in y (V); ours, and on a moving puck: UNVERIFIED | probe 4 V |
| launch speed, separation point, mass | not inputs (4.1) | |

(B) The shot:
| term | size | where |
|---|---|---|
| e, the launch error at the shot's command | their stroke at effort 0.015 and above: at most 1 % across frictions (A); single contacts at 0.010: 0.1944 to 0.1990 m/s (B rows); the calibration body: +1.4 to +1.6 % for 0.1 kg against 1 kg, the same factor at both speeds (0.984 at 0.010, 0.986 at 0.020), so a per-object factor from the test push's own track could remove most of it (UNVERIFIED); the approach state: UNMEASURED (the spike, 9.2). No stroke without resets has been measured | probe_analysis_out.txt A, B; RP L2 |
| m, the slide law over the shot, given the friction T3 measured | launches 0.37 to 0.44 m/s (9 cells): with the true mu the law predicts the rest within 0.7 to 1.7 mm from the first clear state; the slide from the separation point is 0.6 to 0.9 % longer than the law with 0.1 mu says (the offset above), and 0.1 % shorter in one cell, so slides differ by about 1 % from each other. At 0.47 to 0.55 m/s, 3 of 5 on-slab cells depart: 17.7 to 20.2 mm shorter than the law (1.9 to 2.6 %; the review's 2 cm reproduced), a free fit 2.1 to 5.7 % high in mu, residuals 2.1 to 2.8 mm; the other two follow the law. No step without support contact in any cell; the cause is UNVERIFIED | probe 3 S2; probe 4 SL |
| the shot's separation point | 67.4 to 69.8 mm from the tool tip over 16 trials (RP), about 1.2 mm, 0.3 % of a 0.4 m shot | RP L1 |
| the pose before the shot | as (A), from the rest render | probe 4 V |

(C) The literal, exactly (probe_closure_out.txt): the largest interval
half-width b for which friction_known holds, with e = 2 % (e = 1 % adds
about 2 points, e = 3 % takes about 2 off):
| puck before the shot | mu_eff | shot launch | b with m = 1 % | b with m = 2.6 % | T3's p99 at 2 mm |
|---|---|---|---|---|---|
| x 0.53 (one test push, high friction) | 0.015 | 0.50 m/s, in the departing range, so m = 2.6 % applies | 10.1 % | 8.4 % | 9.4 % |
| x 0.60 (one test push, middle friction) | 0.010 | 0.39 m/s | 11.8 % | 10.1 % | 4.4 % |
| x 0.67 (two test pushes, high friction) | 0.015 | 0.45 m/s, at the edge of the measured range | 13.4 % | 11.7 % | 9.4 % (one track) |
| x 0.77 (high friction after advance, 3.4) | 0.015 | 0.41 m/s | 16.8 % | 15.1 % | 9.4 % |
| x 0.77 (one test push, low friction) | 0.005 | 0.24 m/s | 17.7 % | 15.9 % | about 2 to 3 % |

So, given T3 on early renders and e = 2 %, the literal holds after one test
push at low and middle friction, and at high friction after a second test
push, which the planner plans because the literal is false after the first
(the shot from x 0.53 would need 0.50 m/s, where m is at least 2.6 %, and
8.4 % is below 9.4 %). The first version's allowance of 9.8 % was the
Coulomb form; the damped law tolerates a little more (10.1 % for the same
case at m = 1 %).

What does not close today, conceded:
- The sensor. T3's numbers assume renders from 6 steps after the last
  contact. The D4 eye sees nothing while the arm is in the push posture,
  and the only retreat measured sweeps the hand through the puck (4.2). Its
  slower case cleared the view 0.38 s after the stroke at a peak above our
  joint limit (probe 4 R); by then, at mu 0.15, only about 40 % of the
  slide is left (my arithmetic from S1's slide times), so T3's
  high-friction precision on the D4 eye is worse than the late schedule's
  12.6 % and unmeasured. With that sensor the tightest case does not close
  on measured numbers. It closes with an eye that sees the early slide
  (4.2 (c), PS-Q12) or with a retreat that clears the view about as fast as
  the 0.18 s case without touching the puck, which is unbuilt.
- e at 2 % is not measured for any stroke run without resets, over
  approach states and bodies. That is the spike's question (9.2).
- m above 0.44 m/s: the departures are intermittent and unexplained; the
  literal must treat shots above 0.44 m/s with m of at least 2.6 % (the
  measured worst), which the table shows is what forces the second test
  push at high friction.

### 4.4 How we know we got it right
Evaluation-only reads after each episode, never fed back (the pattern of
G2's write-only set):
- V1 accuracy: the final estimate against the truth, 0.1 x mu_puck with
  mu_puck read by the evaluator through getDynamicsInfo; median and maximum
  relative error.
- V2 calibration: the interval contains the effective friction (the one
  the slide obeys, 4.1, which the evaluator fits to the true track of that
  slide, evaluation only) in at least 95 % of trials (count and Wilson
  interval, tools/gen_scene_eval.py:345). This accepts or refutes the
  "exact under the bound" claim of 2.3: a miss means the declared bound is
  wrong. Run on the test push alone, which needs no TAMPURA and no episode,
  on 200 friction draws from the prior with the approach varied (revised
  after the review, N10: 19 of 20 has a Wilson lower bound of 0.764 and
  cannot show 95 %; 197 of 200 gives 0.957 and 100 of 100 gives 0.963,
  probe_slide_track_out.json, wilson_lower).
- V3 controller: predicted against actual final x for every push; median
  and 95th percentile residual.
- V4 success: the shared criterion of 8.1, both arms.
- V5 positive control, labelled and never an arm (as G6's positive
  controls, PAPER_AUDIT.txt:3361-3366): the shot computed from the true
  mu_eff. It bounds what our controller can do; their controller's
  equivalent lands 5 of 5 (E4).
- V6 negative control: one blind shot with no test push; expected about
  23 % aimed at the prior's centre and at most about 31 % with the best aim
  (T6). The None row's return on D is 0.34 (SURVEY).
- V7 attribution log for arm T (added after the review, objection 3):
  read only, offline after each episode, from arm T's observations
  (joint_path and effort, env.py:544) and the evaluator's true friction,
  never fed back and nothing changed in their run (G13): per push, the
  replay mismatch, i.e. where the returned effort, replayed in a probe
  world at the true friction from the believed pose, lands against where
  the real puck landed (the effect of C21: 3.6 cm at mu 0.125 in E4); per
  episode, whether the puck ended in the band x 0.80 to 0.9 where push-to's
  preconditions hold and its stroke finds no path (an unchanged pose after
  a push, env.py:537-538, 631-632); and the number of pushes. A gap between
  the arms is credited to the representation only for the episodes this
  log does not explain; the paper reports the split.

Pre-registered before any comparison run, in the BF# entry: V1 median at
most 3 % against 0.1 mu (the engine's offset of about -1.5 % included and
reported), V2 at least 197 of 200, V5 at least 19 of 20 (a control, not a
coverage claim). A miss is fixed pipeline-wide or reported as is; no
constant is tuned on puck_slide outcomes (G9; Hani's rule against
bridge-only tuning).

### 4.5 The probes run for this document (MEASURED)
probe_puck_physics.py and probe_puck_physics2.py (probes 1 and 2), and
after the review probe_slide_track.py (probe 3, S1 to S3), probe_shot_law.py
(probe 4, SL, V, R), probe_occlusion_check.py and probe_closure.py
(arithmetic only), ran in their venv from /root/ps_probe (env_configs
symlinked to theirs), PYTHONDONTWRITEBYTECODE=1 (run_probe3.sh and
run_probe4.sh hold the run lines). They import their module, build worlds
with their setup_puck_world in DIRECT mode and replay their push trial line
for line (the joint path is their shoot_controller's, computed as the
review's rp_launch.py does); every reset and every pose write in them acts
on the probe's own worlds. Probe 3's first run ended in its render part
(an empty view, then a key error) and was rerun whole; its first version's
line-of-sight test used rayTest, which can never hit their real puck (it
is in GROUP_GHOST with GHOST_MASK, env.py:347-349), so that test was void
and replaced by renders (probe_occlusion_check.py shows both). Their
tracked files hash the same before and after every probe run, by two
methods (named after the review, C79): the shell form
`git ls-files -z | xargs -0 sha256sum | sha256sum` gives tampura_environments
b68dbf8ebfee50c0... and tampura 0e8267e1b90a9ccc...; tools/bridge_gates.py:
598-609's own method (sorted names, each followed by the sha256 digest of
its bytes, via RP/rp_tree_hash.py) gives e339e7b8... and fbc0cd06...
(run_probe3.sh and run_probe4.sh print both before and after probes 3 and
4). The modification of
tampura_environments/__init__.py that `git status` shows in their tree was
there before the probes and is unchanged (sha256 9a64bea0...).

| question | result | file |
|---|---|---|
| does the launch speed depend on the friction? | at effort 0.015 and above, little: across mu 0.05 to 0.15 the sd is at most 0.004 m/s (1 %), 18.2 to 18.9 m/s per unit effort (19.2 at 0.010); at effort 0.005 to 0.010 the sd is 5 to 14 %. At 0.010 most of it is one case: four frictions launch at 0.1944 to 0.1990 m/s, mu 0.15 makes a second contact and its last launch is 0.1713 (B rows; RP L1). A dependence, not noise: the engine is deterministic (RP L3) | probe_analysis_out.txt A, B |
| which slide model? | Coulomb alone: mean ratio 1.081, rms error 9.5 %; plus linear damping 0.0408: 2.0 %; plus linear and quadratic 0.04: 1.4 % (n = 23). The damping law is exactly PyBullet's default: a free 1 kg puck at zero gravity fits k1 = k2 = 0.0400, largest relative error 2e-8 (RP rp_damping.py) | B; RP |
| is the damping the cause? | yes: with the puck's damping set to 0, Coulomb alone recovers 0.975 to 0.991 of 0.1 mu on the in-bounds rows, against 1.020 to 1.173 with the default | probe_puck_physics2_log.txt F1 |
| does the mass matter? | mass 0.5, 1, 2 kg: launch 0.1986, 0.1961, 0.1916 m/s at effort 0.01 (3.6 % over 0.5 to 2 kg, 2.3 % over 1 to 2 kg); 0.3708, 0.3688, 0.3697 at 0.02. The design case, a light calibration body against the 1 kg puck: 0.1 kg launches 1.6 % faster at 0.010 and 1.4 % at 0.020 (RP L2) | F2; RP L2 |
| a single shot from the start | at most one effort of seven lands in the goal per friction (none for 0.05 and 0.125); overshoots fall off the slab | probe_analysis_out.txt G |
| their 5-trial correction with an exact friction | last trial in the goal 5 of 5 (x 1.262 to 1.305); trial 1 at mu 0.05 went off the slab (x 2.039); the returned effort is not the last one used, and replaying it lands 3.6 cm away at mu 0.125 | E |
| their 19 ghost pucks | the real puck stops 10.8 mm shorter at effort 0.01 and 3.7 mm at 0.02 when they are present (mu 0.10); the tool tip's peak speed is identical; the real puck's launch is 4.2 % lower with them at effort 0.01 (0.1973 m/s without, 0.1891 with) and 0.6 % at 0.02 (the review's reading of F) | F |
| reach of their push geometry | a push path is found 3 of 3 times for the puck at x 0.39 to 0.80 and 0 of 3 at 0.85, 0.90, 1.00 (y 0) | probe_puck_physics_log.txt, E5 lines |
| settle | every in-bounds slide had stopped within their 2000 settle steps | probe_puck_physics_out.json, E1 speed_at_end |
| can the friction be read from the free slide alone (T3)? | yes, given renders of the early slide: p99 6.4 % at 2 mm noise over the prior, 9.4 % at mu 0.15 (60 Hz from 6 steps after the last contact); the engine's effective friction is 1.5 % below 0.1 mu | probe_slide_track_out.json S1 (log: probe_slide_track_log.txt) |
| does the law hold at shot speeds? | at 0.28 to 0.44 m/s yes (rest within 1.7 mm with the true mu); at 0.47 to 0.55 m/s 3 of 5 on-slab cells slide 1.9 to 2.6 % short | S2; probe_shot_law_out.json SL |
| which eye sees the slide? | the D4 eye with the arm at home sees x 0.40 to 1.00 whole; with the arm in the push posture none (0 of 140 renders); the wrist camera looks straight down and loses the puck | S3; probe_shot_law_out.json V; probe_occlusion_check_log.txt |
| how soon can a retreat clear the view? | their joint-space path to home: 0.18 to 0.38 s after the stroke, but it hits the puck in 6 of 6 trials | probe_shot_law_out.json R |
| is a repeat in a fresh world identical? | yes: S3's run with renders reproduced a fresh run without renders bit for bit (3 of 3), so rendering does not disturb the physics | S3 deterministic_rerun |

Also measured: the puck rests at z 0.075 (their start pose has z 0.06,
1.5 cm inside the surface, env.py:44-48); time step 1/240; 50 solver
iterations; finger friction 1.0, hand 0.5 (their world as built).
Limits: reach only at y 0; the ghost load at one friction and two in-bounds
efforts; single trials per cell, which is enough for a fixed state because
one joint path in fresh worlds gives bit-identical results (RP L3). A
reused world launched 0.6 % differently from a fresh one (E1 against F1 at
mu 0.05, effort 0.01); the first version of this document blamed the arm's
prior motor state, but E1 and F1 used joint paths computed in different
worlds (probe_puck_physics.py:152, probe_puck_physics2.py:79), so the path
may be the cause (withdrawn after the review, N5). What does vary the
launch for arm O is the friction during contact and the arm's state when
the stroke starts (the approach, which differs per episode); the spike of
9.2 varies the approach. The launch speed in probes 1 and 2 is the puck's
own, read in the probe's world, which our arm cannot read; probe 3 reads
the friction from positions only (4.1).

## 5. The push controller

### 5.1 Theirs (READ, then MEASURED)
shoot_controller (env.py:422-512) plans a 5 cm Cartesian stroke from
behind the puck toward the target (env.py:433-458, 465-471), takes the arm
to its start with state.apply_sequence (env.py:490-491; their executor moves
the arm by resetJointState, BF#35 at PAPER_AUDIT.txt:7375-7377), then runs
pc_steps = 5 trials (env.py:418, 493). Each trial resets the arm to the
stroke's start (env.py:496-498) and every puck, the real one included, to
the believed pose (env.py:500-501), follows the path with a lead-time
position controller and 2000 settle steps (env.py:384-415; follow_joint_path
itself first sets the arm to joint_path[0], :388-393), and corrects the
effort from the median final x of all 20 pucks (env.py:505-509). The update
also runs after the last trial, so the effort returned (:512) and sent in
the observation (:544) is not the last one used, and their belief replays
the returned one (:221-223; MEASURED in E4: 3.6 cm off at mu 0.125).
push_execute_fn then sets every puck to the real puck's final pose
(env.py:540-541). "Effort" is the lead time of a moving position target
(waypoint_joint_controller,
/root/tampura-work/tampura_environments/tampura_environments/panda_utils/pb_utils.py:1312-1328),
so it sets the stroke's speed.
What the resets do (MEASURED): with an exact friction the correction
converges (5 of 5 in the goal, E4), but its first trial sent the real puck
off the slab at mu 0.05 (x 2.039), which only the reset undid. On a real
robot that practice trial would have ended the episode.
Their practice is model-based in effect: in the executing world 19 of the
20 pucks in the median carry the belief's frictions (env.py:525-530), so the
real puck's practice outcomes enter the effort with a weight of about 1/20
per trial.

### 5.2 Adopting theirs: what it costs
- As is: four resets of the task object per push and a robot reset per
  trial, both against H1 ("no teleports of task objects or of the robot",
  PAPER_AUDIT.txt:3256), a kinematic approach, and the 1/20 leak above.
  Excluded by H1.
- With pc_steps = 1: no puck reset remains, but the kinematic approach and
  the robot reset do. That is B9's execute layer, parked by BF#37
  (:7507-7526). The parallel agent's argument for running their system with
  Semantic Boxels wired in (../wire_sb_into_tampura/, still in progress
  when this was written) is where that route belongs; on puck_slide its
  cost is these two H1 items, and arm O would then not test our execution.

### 5.3 Ours (revised after the review)
1. Geometry: their pre-push pose formula (env.py:433-458) as a sampler,
   solved by our IK on the plan twin. This is #P5's combination, "adopting
   their grasp SAMPLING while keeping our physical execution"
   (PAPER_AUDIT.txt:9433-9434), applied to pushing; their geometry reaches
   the puck up to x 0.80 (E5). Our top-down geometry is the alternative
   (decision PS-Q6; its reach, and whether it keeps the arm out of the D4
   eye's view, are UNVERIFIED).
2. Approach: a planned move along the RRT path executed by
   move_robot_smooth (robot_utils.py:886-1007) with the endpoint settle on.
   A pad contact during the approach aborts the action and makes the pose
   unknown (M10's rule, PAPER_AUDIT.txt:4484-4491).
3. Stroke, two options (decision PS-Q5):
   (a) ours: dense IK waypoints along the push line under our position
       control (240 N m, robot_utils.py:969-970; joint speeds within
       JOINT_VELOCITY_LIMITS, :160-162). Its premise in the first version,
       a hard stop so that "the puck separates at the cruise speed", is
       withdrawn: on their stroke the puck separates mid-stroke, 7 to 58 %
       faster than the pusher at that instant (RP L1), so the contact
       solver sets the launch, not the stop (REVIEW N3: the gentle stop is
       not the cause at efforts of 0.010 and above). The same docstring
       records a 10 to 20 mm undershoot of streamed targets at awkward
       postures (robot_utils.py:979-980), which matters for a
       speed-critical stroke. Unbuilt and unmeasured.
   (d) theirs run physically, added after the review (objection 6): a port
       of their stroke shape (two IK configurations 5 cm apart, a lead-time
       position target, pb_utils.py:1312-1328) into our executor, run once
       after our own physical approach, without their resets and without
       follow_joint_path's set_joint_positions (env.py:388-393). H1-clean;
       its G1 and G3 wiring UNVERIFIED. It is the only stroke with measured
       launch properties: command-based spread at most 1 % across frictions
       at effort 0.015 and above, and 2.4 % for single contacts at 0.010
       (A, B). Recommended for the spike, since with T3 the slow test push
       no longer needs its launch (4.1).
   From the positions the puck rests at after the test push, a shot needs
   0.24 to 0.50 m/s (probe_closure_out.txt, VC lines); 0.5 m/s at about
   0.5 m from the shoulder is about 1 rad/s, half of joint 1's 2.175 rad/s
   (my arithmetic; UNVERIFIED for the stroke's joint profile).
4. Retreat (new after the probes): the stroke primitive ends with a planned
   retreat that clears the D4 eye's view, back along the push line and then
   up, never a joint-space path to home: theirs swept the hand through the
   puck in 6 of 6 trials (probe 4 R). How soon a Cartesian retreat clears
   the view is UNVERIFIED (the spike's first measurement); with an overhead
   eye (PS-Q12 (c)) the retreat is not on T3's critical path.
5. Look: the eye renders at known simulation steps from the first step
   without any pad contact and the view clear, every 4 steps (60 Hz),
   until two renders agree, then the rest render (4.1). The action ends
   there; the arm makes no unplanned motion (H2), and the next move is
   planned (3.1). Their 2000 settle steps (env.py:406) bound the wait.
6. One stroke per action; nothing reset, nothing teleported. The practice
   moves into the model: the stream evaluates the slide model before the
   one real stroke.

Precision: what the shot needs from the stroke is its launch at a given
command (e of 4.3), over the approach states an episode produces. Their
stroke's command-based launch varies by at most 1 % across frictions at
shot speeds, but only from a reset state (A); for a stroke run after a
physical approach it is UNMEASURED, and it is the second number, after the
sensor, that decides whether the design works (4.3, 9.2).

## 6. The branch
- Name `puck-slide`, cut from `tampura-bridge` at the commit current when
  work starts (1b6fa2b at 15:45), not created by this agent. Since BF#68
  the dev tracks work this way: each on its own branch `track/<name>` in a
  sibling worktree cut from the tag stable-2026-11-06, while the main
  checkout stays the trunk Hani runs from and only the orchestrator merges
  into it (tracks/STATE.md:111-119, 152-161). Hani's older rule against
  worktrees (memory note) and this newer practice conflict; the branch
  would follow whichever Hani names for it (PS-Q7).
- Why tampura-bridge: the gates (tools/bridge_gates.py), arm T's driver
  (tools/run_tampura_timed.py), the two-arm harness pattern
  (tools/gen_scene_eval.py) and the M8 to M10 defaults live there, and
  only there (main has neither, REVIEW C75).
- Generic layer, candidates to move into tampura-bridge (the trunk; "the
  main line" in the first version meant this branch, not `main`) behind a
  default-off switch once section 7 shows the switch free when off and
  cheap when on:
  - push_domain.py and pddl/domain_pddlstream_ps.pddl: the delta of 3.1,
    generated, with G10's regeneration check;
  - friction_belief.py: the interval, the slide model, the estimator, the
    commit-margin rule; unit tests with this folder's probe data as
    fixtures;
  - push_execution.py: the stroke primitive; the dispatch loop gains one
    branch delegating to it (dispatch in test_full_pipeline.py:2024-2765);
  - the two streams and the pushable rule.
- Task layer, stays on the branch (this is the "version just for this
  task", as their puck_slide/env.py carries its own belief, actions and
  controller):
  - tampura_bridge/puck_slide/: an adapter over their slab world (adopt
    the executing client, identity map objects[0], the ghosts removed as a
    declared set-up and dropped from the identity table, the D4 eye or the
    overhead eye of PS-Q12, no D9 on the puck or the robot);
  - task_spec_ps.py: the prior, the goal box, the slab's far edge, the
    settle floor, each cited to env.py;
  - run_bridge_on_puckslide.py (arm O); tools/puck_eval.py (both arms, the
    shared test, Wilson, McNemar); tools/push_cost_eval.py (section 7);
  - the gate allowlist entries for the set-up.
- Practical risk: the checkout is shared and holds other sessions'
  uncommitted hunks (CLAUDE.md). A branch switch in the main checkout
  moves every session's next commit onto puck-slide; the tracks' sibling
  worktrees avoid that. Stage own hunks only (decision PS-Q7).

## 7. The cost of the added modelling and actions

### 7.1 What is measured
Whether the switch is free when off, cheap when on with nothing pushable,
and what it does when objects are pushable; on our tasks and on TAMPURA's.

### 7.2 Arms
- C0: switch off. Byte-identical domain by construction, as M8 off; checks
  that the branch is neutral.
- C1: switch on with the declared pushable rule; on our tables no object
  qualifies. Free by construction apart from parsing (conceded after the
  review): with (pushable ?o) never true, the translator prunes both
  actions at grounding. C1 stays as the cheap check that this holds; it is
  not evidence of anything else. It stops being free on find_dice if a
  perceived e_cups_ud width crosses 0.078 m (3.1; the check below).
- C2: switch on, every movable object marked pushable with an unknown
  friction (a stress arm). probe_push becomes groundable everywhere. Its
  pushes can never serve our goals (no goal of ours reads obj_in_region or
  friction_known), so C2 measures the grounding and search overhead of
  live but useless options only. That is the measure Hani asked for ("how
  much did adding it cost us"), and it is all C2 claims.

### 7.3 Tasks (our modes from run_logger.py:697-739, test_full_pipeline.py:1130-1200, 3154-3172)
| task | scene and goal | seeds | why |
|---|---|---|---|
| ours, main | random-pairs, holding | 24 (BF#53's count) | the scene the evals use |
| ours | stack, stack | 10 | stacking init facts |
| ours | random-pairs, find-and-tray-stack (needs a visible and a hidden target, test_full_pipeline.py:1174-1181) | 10 | sense plus stack |
| ours | mixed, holding | 10 | other shapes; checks the pushable rule for false positives |
| theirs | find_dice through the bridge, C0 and C1 | their 20 seeds (pinned map) or BF#63's 40 generated scenes | the bridge task |
| theirs | class_uncertain, C0 and C1 | when its port exists | later |
| theirs | find_dice, perceived widths (added after the review) | the same runs | log every e_cups_ud detection's perceived width on each grasp axis; report the share above 0.078 m. Any share above 0 makes C1 live on find_dice and the pushable rule needs a margin (PS-Q8) |

Arm T is not run for the cost study: TAMPURA does not receive our actions.

### 7.4 Metrics
Planning time per plan call and per episode (pddlstream solve) and the
first call's; translator and grounding counts (operators, facts); init
fact count; plan length; replans; success; wall time. BF#13's distributional
plan-count test for C0 against C1 (expected equal) and C0 against C2 (record
every plan that uses a push).

### 7.5 Where, and how long
Serial (arms stay serial: contention doubles planning time, the eval
parallelism memory note), under the shared run lock the tracks use
(`flock /root/sb_pipeline.lock`, tracks/STATE.md:128-131). Laptop smoke
first, seeds 0 to 2 of each row. The full matrix is about 3 arms x 54 of
our episodes plus 2 x 20 find_dice episodes, about 200 episodes: 2 to 7 h
serial (estimate; 34.6 s per episode is BF#53's median wall for its base
arm on the cluster, PA:8310-8311, and 119 s the mean quoted at
archive/tampura_bridge_plan_2026-10-25/bf/BF59_slip/reviews/hold_physics.md:169,
which a few pathological episodes rule, PA:8308-8310; both are find_dice
figures, UNVERIFIED for these rows and this laptop). On
the cluster or the chair's cloud only with Hani's explicit approval of that
question alone.

### 7.6 Acceptance, declared before the runs
C0 equal to tampura-bridge HEAD on the plan-count test. C1 with equal plans
and a median planning-time ratio to C0 within 1.05 (bootstrap interval
reported). C2 is reported, not accepted or rejected: it is the price of the
capability when it is live.

## 8. The shared success criterion; reach and grasp

### 8.1 The criterion
Their reward is the atom in(puck, goal0) (env.py:745) on the abstract
belief: true when a corner of a 2 cm box around the believed centre lies in
goal0's box (test_in, env.py:660-672; goal0 at x 1.3, y 0 with half extents
0.1, 0.35, 0.1: env.py:49-56, 80-82). The believed pose is the real puck's
observed pose (env.py:228, 543-545).
Shared test, both arms, the same code, read only, after the rollout: their
test_in, imported from their module, applied to the real puck's final pose
in each arm's executing world. A fallen puck fails it (the goal box spans
z -0.05 to 0.15). For arm T it equals the reward by construction (READ;
checked on every run, any mismatch logged), and arm T's reward is reported
beside it, as BF#37 item 2 does for find_dice (PAPER_AUDIT.txt:7518-7523).
Two rules this stretches, named after the review: (i) H1 lists success
scoring among the decisions no ground-truth read may feed (PA:3259), and
the shared test reads the real puck's true pose; the precedent is BF#36
and BF#37's world-state test (PA:7471-7484, 7518-7523), which Hani
accepted for find_dice. (ii) Arm O has no TAMPURA reward: one would need a
writer of their belief (G6's scoring channel, PA:3361) whose observation
carries the true puck pose, and G12's rewards[-1] parity (PA:3434-3436)
has no puck_slide form. Proposed: drop arm O's reward column and report
the shared test for both arms (PS-Q15). Also reported: steps to success,
and both arms on their discounted-return convention (Table I is a return
with gamma 0.98, SURVEY).

### 8.2 Grasp
No grasp: 12 cm puck, 8 cm opening (section 0). Push only, for both arms.

### 8.3 Reach
Their push geometry acts for the puck at x 0.39 to 0.80 and not at 0.85 or
beyond (E5), although their in(ik) holds up to x 0.9 (env.py:58-62). Between
0.80 and 0.9 their preconditions hold, the controller finds no path and the
action returns the unchanged pose (env.py:537-538, 631-632). The goal starts
at x 1.19, so the last 0.39 m at least are a free slide for both arms.
Our reach: UNVERIFIED (the spike measures it on the plan twin, 9.2).

### 8.4 Physics set-up
None for this task. D9 sets every task body's friction to 1.0 and gravity
to -9.81 (tampura_bridge/policy.py:65-85; task_spec.py:58-62); here the
friction is the hidden variable and the physics is the task (no_fit_case.md
2.2). The branch's adapter writes nothing to the puck, the slab or the
robot: gravity -9.8 (env.py:258), time step and solver as their world has
them (MEASURED: 1/240, 50 iterations).

### 8.5 Deviations from their setup, listed for repetition in every report
Following Hani's rule for class_uncertain (report deviations repeatedly):
- D-1 Arm O's world drops TAMPURA's 19 ghost pucks (alpha 0.2, colliding
  with the robot and the slab only, env.py:335-361), which arm T's
  controller needs and arm O's does not. MEASURED effect on the real puck:
  3.7 to 10.8 mm shorter slides with them present (F), and a 4.2 % lower
  launch at effort 0.01. The removal is a world write before the first
  step (G1's D9 set-up class, PAPER_AUDIT.txt:3297-3303; G14's D9
  exception), arm O only (decision PS-Q3). Label corrected after the
  review: the ghosts are not "non-task bodies" in the bridge's terms;
  world.objects holds all 20 pucks (env.py:378-380) and the bridge's
  identity table is built from world.objects (G8(a), PA:3380-3383), so the
  set-up drops them from that table too, declared by name. Direction:
  unknown sign for success, small.
- D-2 Observation: our renders against their exact pose (4.2). Since the
  review, T3 also gives our arm a track of each free slide where TAMPURA
  gets one final pose, which it interprets through an exact world copy
  (D-4); with PS-Q12 (b) the track comes from an overhead eye neither
  system has. Mixed: theirs is exact, ours has more samples of a noisier
  channel.
- D-3 Controller: ours has no practice trials and no resets (5.3); theirs
  practises on the real puck four times per push. Favours T.
- D-4 Model knowledge: TAMPURA's belief is an exact copy of the world
  except the friction (same slab friction, same 1 kg puck, env.py:685,
  236-245); our arm has a two-constant slide model, no mass and no slab
  friction. Favours T.
- D-5 Prior: the same range as their planner's (2.3), but theirs is a
  distribution (uniform in 1/friction, env.py:353-356) and ours an
  interval with none. Neutral as far as the interval goes, since it reads
  only the support.
- D-6 Seeds 20 to 59, if PS-Q10 (b): beyond their 0 to 19, reported apart.
- D-7 Success channel for arm O (added after the review): the shared test
  reads the real puck's true final pose for both arms (8.1), a truth read
  in success scoring, which H1 lists (PA:3259); arm O has no TAMPURA
  reward of its own unless one is written (PS-Q15). Neutral between the
  arms; a departure from G12's rewards[-1] parity.
- No object model (Hani's withdrawal of A1 for class_uncertain,
  class_uncertain/BRIEF.md:54-84, applied here in spirit): the design needs
  none (mass-free, pushable from the perceived width); the friction prior
  and the goal box are task-level knowledge TAMPURA's planner also has
  (:73-77).

## 9. Effort, order of work, minimal version, risks

### 9.1 Work items (estimates, working days; revised after the review)
The first version's W0 (one day, before W2) could not produce its own
go or no-go number, because it needed W2's stroke (objection 7). The
spike S replaces W0 and the stroke part of W2, and comes first.
| id | item | estimate |
|---|---|---|
| S | the spike of 9.2 | 3 |
| W1 | friction_belief.py: the interval, the T3 fit (probe_slide_track.py's slide and fit_track), the literal with e and m; tests with this folder's probe data as fixtures | 1 |
| W2 | push_execution.py in our executor: the stroke chosen in S, the retreat, the pad-contact rule (G2-safe), the render schedule | 1.5 to 2 |
| W3 | domain delta, streams, init facts, dispatch, G10's goal form | 1.5 |
| W4 | adapter, arm O driver, shared success test, gate adaptations (G7; G8's identity table for a 20-body world; G10, G12, G13, G14, G18 to G20), a GUI run of seed 0 for Hani | 2.5 to 3.5 |
| W5 | validation: V2 on 200 test-push draws, V1, V3, V5, V6, V7 | 1 to 1.5 |
| W6 | comparison, arms T and O on seeds 0 to 59 (0 to 19 reported apart), with arm T's first local puck_slide run (R7) | 1, plus about 3 h of runs |
| W7 | cost study, reduced: C0 and C1 on random-pairs (24 seeds) and the find_dice widths | 0.5 to 1, plus 2 to 7 h of runs |
| W8 | records: the M entry and the BF# entries with their reviews, ledger rows, the paper text | 1.5 to 2.5 |

Minimal version after a GO: W1 to W8, about 10.5 to 14 working days
(estimate), so 13.5 to 17 with the spike. The first version's "6 to 8" did
not follow from its own items, which sum to about 8.5 to 10 before the
missing ones (REVIEW N9: conceded). The full design (T3 ablations, the
advance action, PS-Q4 (c)'s robustness row, the full cost matrix) adds
about 2 to 3 days.

### 9.2 Order, the deadline, and the spike
Time (corrected after the review): Friday 2026-11-06 to Friday 2026-12-04
is 21 working days, today's afternoon included. In flight on the same
days, from the records: the paper's writing; BF#64's fix (owned by path 3
since 15:10, to be rolled out after its checks, tracks/STATE.md:174-175,
275-281) and BF#65's open finding (PA:9143), both on find_dice; the B8
re-runs and CB#113 (PROPOSAL_ATTRIBUTE_BOXELS.md:253-254); the
class_uncertain plan (BF#67, held, its phase 1 handed to path 2,
class_uncertain/STATE.md:30-34); and since 14:07 today the dev tracks of
BF#68 (PA:9353-9415; five paths by 15:27, tracks/STATE.md:85-89), whose
orchestrator and three Opus tracks hold all four top-tier agent slots
(:136-139) and which share one run lock for every pipeline or TAMPURA
episode (:128-131). Path 2's job is exactly the question "which TAMPURA
tasks give SB a quick result" (:86), and by this document's own numbers
puck_slide is not quick: 13.5 to 17 days to a result after a GO.
So the minimal version does not fit before the deadline beside the
paper, and this document no longer recommends it (PS-Q1).

The review's alternative, weighed: a time-boxed spike that settles the
open physics first. It costs about 3 of the 21 days, produces a measured
statement either way, and stops the work cleanly if the numbers fail. Its
weakness: even a GO leaves 10.5 to 14 days of building that do not fit
before 2026-12-04, so before the deadline the spike buys a feasibility
number, not a result. That is worth 3 days only if Hani wants puck_slide
in the paper as an announced extension and accepts the relaxations of
section 14 (PS-Q13 to PS-Q15), without which no puck_slide result could be
claimed anyway. Otherwise everything here, the spike included, waits
until after the paper.

The spike, if Hani wants it (scope fixed in advance, about 3 working days,
estimate; probe worlds of their slab and plain tables of ours, read only
on their tree, no TAMPURA episode, no cluster):
- Day 1: the stroke without resets, PS-Q5 (d) (their stroke shape, ported,
  after a physical approach), and a Cartesian retreat. Measure: (i) when
  the D4 eye's view clears after the stroke, and whether the retreat ever
  touches the puck; (ii) e: the launch at a given command over at least 10
  approach states (start configurations and puck positions x 0.39 to 0.80,
  y -0.1 to 0.1), 3 frictions and 2 bodies of ours, on a plain table with
  the slab's FRICTION_MID (a constant in their source, G9), fixing the
  calibration there and only there.
- Day 2: end to end on their slab: test push, T3 from the D4 eye's renders
  (or the overhead eye if Hani allows it, PS-Q12), read by our perception
  or, if wiring it takes more than half a day, by probe 3's stand-in
  (labelled as such), the literal of 2.3 with the measured e and m, a
  second test push when the literal says so, then the shot. 100 trials,
  frictions drawn uniformly from the prior, approach states varied.
- Day 3: analysis, the BF# entry (BF#69 or later; grep first), ledger rows.
The number that decides, fixed now: the share of the 100 trials whose shot
lands in the goal by their test_in. GO at 95 or more, with a median of at
most 2 test pushes (TAMPURA's optimal plans need 1 to 4 controller
executions, SURVEY); STOP below 90; 90 to 94 goes to Hani with the
breakdown. Reported beside it, so that a STOP names its cause: the
view-clear time, T3's p99 at the measured noise, e's 95th percentile, m,
and how many trials the literal sent to a second push. A STOP is logged and
puck_slide becomes future work in the paper; slab trials set no constant
(G9).

### 9.3 Minimal version (after a GO; about 10.5 to 14 working days, estimate)
The T2 push read by T3, and shoot; the stroke and the eye chosen in the
spike; their geometry; the prior from their constants; seeds 0 to 19 with
V1, V2 (200 draws of the test push alone), V5 and V7; the cost study C0
and C1 on random-pairs only (24 seeds), plan-count test and timing, and the
find_dice widths.

### 9.4 Risks
- R1 (renamed after the review, N11: the engine is deterministic, so the
  issue is dependence, not repeatability) the shot's launch depends on the
  approach state, the body and the friction in ways no probe without
  resets has measured; with T3 the test push's launch no longer matters.
  Mitigation: the spike's e over approach states; the per-object factor
  from the test push's own track (4.3).
- R8 (added after the review) the engine's contact behaviour: the contact
  solver, not the pusher, sets the launch (mid-stroke separation, second
  contacts, RP L1), and the free slide departs from the law at 0.47 m/s
  and above in 3 of 5 cells for an unexplained reason (probe 4 SL).
  Mitigation: the literal's m of at least 2.6 % above 0.44 m/s, which
  sends fast shots to a second test push first.
- R9 (added after the probes) the sensor: the D4 eye is blocked in every
  push posture measured; a retreat that clears it early without touching
  the puck is unbuilt (4.2). Mitigation: the spike's day 1; else PS-Q12 (c).
- R2 our reach near the base (the pre-push pose for the start is at about
  x 0.32) or at the far end; UNVERIFIED. Mitigation: their geometry.
- R3 the perceived centre of the puck: T3 needs about 2 mm per render
  (4.3). A stand-in on D4 renders of the resting puck is within 1.4 mm
  from x 0.40 to 1.00 (probe 4 V); our perception on a moving puck is
  UNVERIFIED; M8's place tolerance of 3.6 mm (PAPER_AUDIT.txt:4464-4466) is
  the nearest number measured on our pipeline.
- R4 a reviewer calls the slide model hand-made. Answer: it is the generic
  sliding law plus the engine's damping, with no task constant except their
  own prior range, while TAMPURA's belief is an exact copy of the task
  world (env.py:685): more model than ours (D-4).
- R5 time: the work competes with the paper, the find_dice findings, the
  class_uncertain plan and the five dev tracks (9.2); the minimal version
  does not fit before 2026-12-04.
- R6 a deviation the reviewer finds and we did not list. Mitigation: 8.5 in
  the BF# entry and in every report.
- R7 arm T on our machines: no local puck_slide run exists (SURVEY 11). If
  its success is far from the published 0.52 the comparison needs its own
  explanation first.

## 10. The no-fit case's objections, answered

### 10.1 no_fit_case.md 2.2, RUN
1. "He cannot grasp the puck" (12 cm against 8 cm). Conceded; the design
   does not grasp.
2. "He cannot carry it to the goal either" (beyond reach). Conceded, and it
   binds both arms: TAMPURA's push-to leaves the ik region by construction
   (env.py:725), and its push geometry stops at x 0.80 (E5). At least the
   last 0.39 m (x 0.80 to 1.19) are a free slide for either arm with that
   geometry.
3. "His system removed push" (execution.py:1935-1937). True, but what was
   removed is not what is proposed. The removed function teleported
   occluders without the arm (execution.py:1936-1937), and push was dropped
   because its target was hard-coded in the PDDL ("the solution was almost
   modeled in the PDDL actions"); the supervisor's note was that push could
   return as the motion primitive with the target as an explicit parameter
   (archive/CODEBASE_AUDIT_DEFERRED.txt:450-467). The proposed push is
   physical (the arm strokes, nothing is teleported), and its region and
   speed are planner and stream parameters. The backlog lists
   physics-based pushing (archive/CODEBASE_AUDIT_FINAL.txt:167-168), and
   the live domain's header still names push among the robot's
   capabilities (pddl/domain_pddlstream_m8.pddl:7, 32).
4. "Their push controller resets the real puck; using it breaks H1, and
   writing his own measures controllers." The first half is accepted and
   MEASURED (5.1). The second half is partly conceded: the comparison
   measures whole systems, controllers included. Three things bound the
   confound: the positive controls on both sides (their controller with an
   exact friction, 5 of 5, E4; ours, V5), the controller residual V3, and
   the fact that TAMPURA's learned model is itself a model of its
   controller's outcomes (effects_fn runs shoot_controller in its belief
   world, env.py:548-583), so its controller is part of its method. What
   cannot be bounded before the spike (9.2) is whether a stroke run without
   resets launches as consistently as theirs does from a reset state.
5. "The bridge set-up would damage the task" (D9's friction 1.0 and
   gravity -9.81). Accepted; this design applies no D9 at all (8.4).

### 10.2 no_fit_case.md 2.2, METHOD
"Nothing is hidden in space ... perception, boxelisation, shadow caster and
executor would all stand idle; only the planner would act." Partly
conceded: shadows, search and the semantic partition stand idle, and that
is the honest scope. Not idle: perception (the puck's pose from our renders,
4.2), the executor (the new physical stroke, 5.3), and the belief, which
represents the hidden attribute the way the boxel model represents hidden
locations (an exact set under a bound, a K-literal at a commit margin; 2.3
and 2.4). The claim tested is the generality of that pattern, M8's
K-literal at a commit margin, which the paper can otherwise only assert;
whether the paper may state it outside H3's region-based model is Hani's
call (PS-Q13).

### 10.3 no_fit_case.md 2.2, TIME
"1 to 2 weeks for a result off the paper's topic." Revised after the
review: about 13.5 to 17 working days to a result for the minimal version
with the spike, 15.5 to 20 for the full design (9.1); the first version's 6
to 8 days were wrong (N9). The no-fit case's figure stands and is, if
anything, low. "Off topic" is half conceded: the result is adjacent
(generality), not core (occlusion).

### 10.4 no_fit_case.md 2.4
1. "The observation function is not his ... writing his own filter is new
   work that has nothing to do with semantic regions." The estimator is
   small and analytic (4.1), mass-free (F2), reads only our renders (since
   the review, not even our proprioception), and needs no copy of their
   world. It is new work. Its relation to the representation is the
   commit-margin literal of M8 (2.4), not the spatial regions of the
   thesis: conceded that it is not about space, and that BF#66 gives it no
   claim for this paper.
2. "The execution is not his." Answered by 5.3: our approach, stroke and
   observation, physical, no resets. Conceded that pick, place, stack and
   sense stand idle on this task.
3. "The policy space is tiny ... one fixed rule against TAMPURA's learned
   model", with MLO 0.29 and WAO 0.24 as the closest analogue. The size of
   the policy space is conceded; it is the task's (the paper says optimal
   plans need 1 to 4 controller executions, SURVEY). What the planner
   decides is whether, how often and how hard to test before committing,
   and that follows from the literal: a second test push appears exactly
   when the first leaves the literal false. The MLO and WAO analogue is not
   close: those rows pair a determinised planner with the Bayes-optimistic
   learning row, a learned model of the outcomes of their own controller
   (SURVEY; whether it is literally TAMPURA's learned model is UNVERIFIED,
   no_fit_case.md 3.4), whereas this design determinises an explicit
   physical model whose error is bounded and checked (V1, V2).
   Where arm O lands is unknown until W6. That it would land near MLO and
   WAO is the no-fit case's expectation; that it would land above TAMPURA
   is this document's; both UNVERIFIED.

The one objection that cannot be answered: a puck_slide result is not
evidence about semantic boxels in space. It is evidence about the POD
representation, about the system's reach beyond geometry and about its
modularity (section 7).

## 11. Decisions for Hani
Revised after the review: the list now stands at the end of the document,
in section 14.2 (PS-Q1 to PS-Q11 as revised, PS-Q12 to PS-Q15 added for the
sensor and the three rules the first version stretched without naming).
Numbered PS-Q to avoid the audit's Q numbers: Q18 is the highest in the
checkout and the class_uncertain plan's questions start at Q19
(class_uncertain/STATE.md:9-10).
Logging, once Hani decides (corrected after the review, C78): one BF# entry
for the decision. BF#67 (the class_uncertain plan, class_uncertain/STATE.md:6)
and BF#68 (the dev tracks, PA:9353; tracks/STATE.md:5) are claimed, so it
takes BF#69 or later; grep the whole checkout again first. If work starts,
the model-tweak M entry of 2.5 as well.

## 12. Files, leftovers, and what stays unverified
Made by this agent, all in this folder: ARGUMENT.md, probe_puck_physics.py,
probe_puck_physics_out.json, probe_puck_physics_log.txt (raw, with
PyBullet's URDF warnings), probe_puck_physics2.py,
probe_puck_physics2_out.json, probe_puck_physics2_log.txt (formatted from
its JSON), probe_analysis.py, probe_analysis_out.txt; after the review:
probe_slide_track.py, probe_slide_track_out.json, probe_slide_track_log.txt
(raw), run_probe3.sh, probe_occlusion_check.py,
probe_occlusion_check_log.txt (raw), probe_shot_law.py,
probe_shot_law_out.json, probe_shot_law_log.txt (raw), run_probe4.sh,
probe_closure.py, probe_closure_out.txt. The raw logs carry PyBullet's URDF
warnings without line breaks; the result lines are found with
`grep -aoE '(S1|S2|S3|SL|V|R) (mu|x)=.*'`. REVIEW.md and review_probe/
are the reviewer's and were not edited. In WSL: /root/ps_probe (one
symlink, env_configs), unchanged by every run. Nothing under
/root/tampura-work: both trees hash the same before and after probes 3 and
4 by both methods of 4.5. No DATA_LEDGER.md row was written (the brief
forbids the edit); the session that started this agent should add one:
this folder is the evidence of this document (keep while it stands);
/root/ps_probe is garbage once the document is accepted.

UNVERIFIED: our perception's error on a sliding puck (a stand-in only, at
rest); how soon a Cartesian retreat clears the D4 view, and whether our
top-down geometry blocks it; the shot's launch after a physical approach
(no stroke without resets was measured); why the slide departs from the
law in 3 of 5 cells above 0.47 m/s; our reach on the slab; contact-force
noise (T4); whether MLO and WAO share TAMPURA's learned model; arm T's
success on our machines; why TAMPURA, with an exact copy of the world,
implies only about 56 % success (SURVEY arithmetic). Candidate causes from
the probes, measured per episode only once V7 runs: its 20 particles, the
replay mismatch of E4, the unreachable band from x 0.80 to 0.9 of E5, and
the ghost coupling of F. Verified since the first version: the damping
constants (the review's rp_damping.py) and the D4 eye's coverage (probe 4
V). All effort and run-time figures are estimates.

## 13. Review and answers
One entry per point of REVIEW.md, numbered as there. "Changed" names the
sections of this document that now carry the answer.

### 13.1 Ranked objections (REVIEW 4)
1. The launch speed has no measured path to 2 %. Holds for the design as
   reviewed; conceded (4.3: with T2 the tightest case does not close).
   Answered in part by changing the design, with two new probes. (i) The
   friction is now read from renders of the free slide (T3), which needs
   neither the launch speed nor the separation point: p99 6.4 % at 2 mm
   noise over the prior, 9.4 % at mu 0.15, renders at 60 Hz from 6 steps
   after the last contact (probe 3 S1). (ii) The shot still needs its
   launch; on their stroke from a reset state the command-based spread is
   at most 1 % at shot speeds (A), the body term 1.4 to 1.6 % (RP L2), and
   no stroke without resets is measured. (iii) The forward-model term is
   measured: about 1 % up to 0.44 m/s, 1.9 to 2.6 % short in 3 of 5 cells
   at 0.47 to 0.55 m/s (probe 4 SL). (iv) With e = 2 % the exact literal
   closes at high friction after a second test push (4.3 (C)). Not
   answered, conceded: the sensor. The D4 eye sees nothing of the puck
   while the arm is in the push posture (0 of 140 renders, S3), the wrist
   camera looks straight down, and the only retreat measured hits the puck
   (probe 4 R); with the H1- and G9-clean sensor as built, the tightest
   case does not close on measured numbers. Where I disagree with the
   review: (a) the 5.4 % command spread at effort 0.010 is mostly one case,
   the second contact at mu 0.15; four frictions launch within 0.1944 to
   0.1990 m/s (probe_analysis_out.txt B rows), so the slow regime is a
   problem of second contacts more than of friction; (b) the 2 cm
   forward-model error is a high-speed effect (it is absent up to 0.44 m/s,
   where the separation-based error is +0.6 to +0.9 %, the effective
   friction's offset), not a property of every shot. Changed: 1 (claim 5),
   2.3, 3.1, 3.2 (T2, T3), 4.1 to 4.5, 5.3, 9.2 (the spike), 9.4 (R1, R8,
   R9), 14.2 (PS-Q5 (d), PS-Q12).
2. Time and what it displaces. Holds; conceded. 21 working days remain;
   the minimal version is 10.5 to 14 days after a 3-day spike (9.1), the
   review's 8.5 to 10 plus its 2 to 4 missing items, which 9.1 now lists
   (W4's gate adaptations, W6's first local arm T run, W8's records and
   paper text). It competes with the paper, BF#64's fix and BF#65, the B8
   re-runs and CB#113, the held class_uncertain plan, and, since 14:07
   today, the dev tracks of BF#68 (five paths by 15:27), which hold all
   four top-tier slots and share the one run lock (9.2). The review's
   alternative, the
   spike, is weighed in 9.2 and defined there (scope, 3 days, the number
   that decides: at least 95 of 100 end-to-end shots in the goal, a median
   of at most 2 test pushes). My conclusion is stricter than the review's:
   before the deadline the spike buys a feasibility number, not a result,
   so it is worth its 3 days only if Hani wants puck_slide named in the
   paper and accepts the relaxations first; otherwise all of it waits
   (PS-Q1). Changed: 9.1, 9.2, 9.3, 10.3, 14.2.
3. What the paper could claim. Holds; answered with the two things the
   review asked for. The paper sentence (section 1, first bullet): both
   arms get a model of the dynamics; TAMPURA's is the simulator with an
   exact copy of the task world except the friction (env.py:685, 236-245),
   ours the sliding law with the simulator's damping, measured once on an
   empty table (D-4). The attribution log V7 (4.4) measures per episode,
   offline and read only, the replay mismatch of the returned effort (C21),
   the no-path band from x 0.80 to 0.9 and the number of pushes, so that a
   gap is credited to the representation only where V7 does not explain
   it. Conceded: the spatial machinery stands idle, the planner's choice is
   fixed by the literal, and BF#66 gives no claim (2.4, PS-Q14). Changed:
   1, 2.4, 4.4 (V7), 10.2, 10.4, 14.2.
4. Incomplete error budget, weak acceptance. Holds; answered. The budget
   has every term the review named (separation point, forward model,
   calibration body) plus the engine's effective-friction offset and the
   sensor (4.3 (A), (B)); the literal has the model-error term m (2.3) and
   is checked exactly with the damped law (4.3 (C), probe_closure.py). V2
   runs on 200 draws of the test push alone and needs 197 of 200 (Wilson
   0.957; 19 of 20 gives 0.764). Changed: 2.3, 4.3, 4.4.
5. Rules stretched without a name. Holds; each is named with its cost and
   put to Hani: H3's "small" and region model (2.5, PS-Q13), BF#66's claim
   effect (2.4, PS-Q14), H1's success scoring and arm O's reward channel
   (8.1, D-7, PS-Q15), G2's body-id leak in separation detection (4.1: "no
   pad contact with anything but the support", never a contact filtered by
   the puck's id; with T3 separation is no longer an estimator input).
   Changed: 0, 1, 2.4, 2.5, 4.1, 8.1, 8.5, 14.2.
6. A controller option is missing. Holds; added as PS-Q5 (d), their stroke
   shape ported and run physically after our approach, and recommended for
   the spike, since with T3 its weak regime (the slow test push) no longer
   matters for the estimate. Changed: 5.3, 14.2.
7. Effort order. Holds; the spike replaces W0 and the stroke part of W2
   and comes first (9.1, 9.2).
8. Cost study. Holds; conceded and added: C1 is free by construction apart
   from parsing, C2 measures only the overhead of live but useless options,
   which is what Hani asked; the find_dice width check is a new row of 7.3
   (e_cups_ud 1.3 mm under 0.078 m). Changed: 3.1, 7.2, 7.3, 7.5.
9. T1 measured as something their nudge is not. Holds; the T1 row now
   describes their nudge as executed (44 degrees off the slab axis, five
   trials with resets and effort updates after each) and says E3 is not
   it. Changed: 3.2.

### 13.2 Numbers (REVIEW 2.3, and the minor items of 2.2)
- N1 mass wording. Conceded; the half-range wording is gone: 0.5 to 2 kg
  3.6 %, 1 to 2 kg 2.3 % (F2), the design case +1.6 % and +1.4 % (RP L2).
  With T3 the estimate is mass-free; mass stays a term of the shot's e.
  Changed: 4.1, 4.3 (B), 4.5.
- N2 the launch-speed source. Conceded; withdrawn and replaced by T3 (13.1
  item 1). Changed: 4.1, 5.3.
- N3 the gentle-stop diagnosis. Conceded (partly wrong): separation is
  mid-stroke at efforts of 0.010 and above; the hard-stop premise is
  withdrawn. Changed: 5.3.
- N4 three missing terms. Conceded; all three are in 4.3, measured, and
  the forward-model term is located by speed (probe 4 SL).
- N5 the motor-state attribution. Conceded; withdrawn (the paths differed,
  and one path in fresh worlds is bit-identical). Changed: 4.5.
- N6 selective use of probe A. Conceded; claim 5 of section 1 is rewritten
  to say the launch is not simple, and the 0.2 m/s pin is stated. Changed:
  1, 3.2.
- N7 the controller WITH its practice. Conceded; claim 6 says so, with E4's
  first trial (1 of 5 in the goal). Changed: 1.
- N8 "the same information as TAMPURA's channel". Conceded; withdrawn.
  Changed: 3.2.
- N9 the 6 to 8 days. Conceded; now 10.5 to 14 after the spike, 13.5 to 17
  with it. Changed: 9.1, 9.3, 10.3.
- N10 V2's power. Conceded; 200 draws, 197 needed. Changed: 4.4.
- N11 "repeatability". Conceded; the spread is a dependence on the
  friction and the approach, and the spike varies the approach. Changed:
  3.2 (T1), 4.5, 9.2, 9.4 (R1).
- 2.2 minor: "18.2 to 19.2 m/s per unit effort" is now 18.2 to 18.9 (19.2
  at 0.010), and the ghosts' 4.2 % launch effect is reported (4.5, D-1).
  The review's 86 s per TAMPURA episode, 21 working days and the cost-run
  hours are used (1, 7.5, 9.2).

### 13.3 Citation rows (REVIEW 1)
- C78 WRONG, "BF#66 is the latest". Corrected: BF#67 and BF#68 are
  claimed; BF#69 or later, grep first (11).
- C15 PARTLY, their nudge. Corrected (3.2, T1; 13.1 item 9).
- C40 PARTLY, the H3 paraphrase. Corrected: H3 is quoted in full, the
  commit margin is credited to M8, and the parts of H3 the design does not
  meet are named (1, claim 3; 2.5; PS-Q13).
- Caveats acted on: C6 (follow_joint_path resets the arm first, 5.1); C7
  (the seed also draws the particle frictions and the nudge directions, 1
  claim 7); C11 (particles uniform in 1/friction, 2.3, D-5); C21 (the
  returned effort is not the last one used, 5.1, V7); C39 (H1's success
  scoring, 8.1, PS-Q15); C44 (G2 bounds separation detection, 4.1); C69
  (the 10 to 20 mm undershoot of streamed targets, 5.3); C73 (119 s is a
  cluster mean ruled by outliers, the median 34.6 s, 7.5); C74 (the
  proposal's :231-232 and BF#66's claim effect, 1, 2.4).
- C79, the hash method. Named, both methods given, and run before and
  after probes 3 and 4 (4.5, run_probe3.sh, run_probe4.sh).
- C57, #P5's lines: moved by BF#68's insertion and its growth to
  PA:9418-9436 (15:45); the cites
  are updated (0, 5.3).
- C67, the view arithmetic: now rendered (4.2, probe 4 V).
- All other rows CONFIRMED: no change.

### 13.4 Rules (REVIEW 3)
- H1 core: unchanged, and T3 removes the last proprioceptive input the
  estimator had.
- H1, success scoring: named; the BF#36 and BF#37 precedent cited (8.1,
  D-7, PS-Q15).
- H1 with G6 and G12, arm O's reward: named; recommended to drop arm O's
  reward column (8.1, PS-Q15).
- G2 leak test: adopted as a constraint (4.1, 5.3).
- H2: unchanged; the push action's look and the retreat are inside the
  planned action (3.1, 5.3).
- H3: named as a relaxation with its cost (1, 2.5, PS-Q13).
- H4: unchanged.
- G1 and G14, D-1's label: corrected (8.5).
- G9, slab trials set no constant: committed (4.1, 9.2).
- G10 and G20: G20's text added; with an overhead eye G20 needs a
  puck_slide form (4.2 (c), PS-Q12).
- BF#35, BF#37 and #P5: unchanged.
- BF#66: no claim taken (2.4, PS-Q14).
- Nothing edits a plan; no one-task tuning: unchanged.
- The request (branch, cost on ours and theirs): unchanged, plus the
  BF#68 branch practice (6, PS-Q7).
- A1's withdrawal: one sentence added (8.5).

### 13.5 The review's lists (REVIEW 5)
Does not survive as written, and what happened to each: section 1 claim 5
(rewritten), 4.1's launch source (withdrawn, T3), 5.3's gentle-stop
diagnosis (withdrawn), the mass figures (corrected), 2.4's "smallest real
instance of BF#66" (withdrawn), 9.3's 6 to 8 days (corrected), "BF#66 is
the latest" (corrected), D-1's label (corrected), 4.5's motor-state
attribution (withdrawn). Survives with changes, each made: the interval
and the literal (2.3: the m term; the interval property holds under the
declared bound on the estimate), the test action (3.2: T2 against T3,
with the sensor's cost measured), the controller (5.3, PS-Q5 (d)), the
budget and the acceptance (4.3, 4.4), the effort (9.1), the decision list
(14.2), PS-Q1 (narrowed further, 14.2). Survives as written: kept.

### 13.6 Gaps against the brief (REVIEW 6)
- The go or no-go number had no statistic: it is now fixed (9.2).
- The design was not shown feasible in the engine: the estimate now is
  (probe 3), the shot's law up to 0.44 m/s is (probe 4), the sensor and
  the launch without resets are not (4.3, conceded).
- The contact behaviour as a named risk: R8 (9.4).
- Attribute boxels without BF#66's decision: added (2.4).
- 1.4 without UNVERIFIED: marked (1, claim 4).
- Section 1 over a page: still over; conceded as a form point, since the
  review's changes added to it.
- Internal consistency: 3.1's episode end and replan made consistent, the
  move to q_home inside the push action removed (3.1, 5.3), "the main line"
  defined as tampura-bridge (6).

### 13.7 What the review left unverified (REVIEW 7)
The hard-stop stroke: still unbuilt, its premise withdrawn (5.3). The
default collision group of static bodies: not checked; the real puck's own
group is now known (GROUP_GHOST, env.py:347-349). The perceived e_cups_ud
widths: a check in the cost study (7.3). The D4 view: rendered (4.2). Arm
T's success on our machines: still R7. The paper's numbers: still SURVEY.
The review's 2 to 4 days of missing items: adopted as an estimate (9.1).

## 14. Final verdict and the decisions as revised

### 14.1 Verdict: survives with changes
The case for the task survives: one environment and one criterion with no
scoring adapter (their test_in on the real pose equals their reward for
arm T), physical pushing for both arms, a hidden physical attribute
handled by M8's K-literal pattern, and a cost study that answers Hani's
question. The design survives with its weakest link replaced: the friction
is read from the free slide, which the probes show is accurate enough when
the early slide is seen, and the budget is complete and checked exactly.
Two physics questions stay open and are conceded: no eye of the current
set-up sees the early slide while the arm is in the push posture, and no
stroke without resets has a measured launch. What does not survive is the
first version's recommendation: the minimal version does not fit before
2026-12-04 (13.5 to 17 of 21 working days, beside the paper and five
running tracks), the friction literal is no claimable instance of BF#66,
and it does not meet H3 as written. Recommended now: everything after the
paper; before it, at most the 3-day spike with its GO number fixed in
advance, and only if Hani wants puck_slide named in the paper and accepts
PS-Q13 to PS-Q15 first.

### 14.2 Decisions for Hani (PS-Q1 to PS-Q11 revised, PS-Q12 to PS-Q15 added)
- PS-Q1 Do it, and how much: (a) the full design before 2026-12-04; (b) the
  minimal version before 2026-12-04; (b') the spike only (9.2), about 3
  working days, its GO number fixed in advance, any build after the paper;
  (c) all of it after the paper. Recommendation (changed): (c); (b') only
  if Hani wants puck_slide named in the paper and answers PS-Q13 (a), and
  then when a top-tier slot is free (BF#68's tracks hold all four). (a)
  and (b) do not fit (9.2).
- PS-Q2 Observation channel for arm O: (a) our perception; (b) their exact
  pose, needing a declared H1 exemption; (c) (a) as arm O and (b) as a
  labelled diagnostic, O-exact. Recommendation: (c), or (a) alone if no
  exemption is wanted (unchanged). Which eye serves (a) is PS-Q12.
- PS-Q3 The 19 ghost pucks in arm O's world: (a) removed as a declared
  set-up before the first step, and dropped by name from the identity
  table, since they are in world.objects (label corrected); (b) their robot
  collisions disabled (also a G1 write); (c) left in. Recommendation: (a).
- PS-Q4 Prior on the friction: (a) their range times the slab's friction,
  constants in their source (same support, not the same shape: theirs is
  uniform in 1/friction); (b) a wide pipeline-wide prior; (c) (a) for the
  comparison and (b) as a robustness row. Recommendation: (c) if time
  allows, else (a).
- PS-Q5 The stroke: (a) ours, unbuilt, its hard-stop premise withdrawn; (b)
  theirs with pc_steps = 1 (kinematic approach and robot reset, B9's
  execute layer, parked by BF#37); (c) theirs as is (excluded by H1); (d)
  added: their stroke shape ported and run physically after our approach,
  without resets. Recommendation (changed): (d) for the spike and any
  build; (a) only if (d)'s launch calibration fails.
- PS-Q6 Push geometry: (a) their pre-push pose formula as a sampler (#P5's
  pattern); (b) our top-down geometry. Recommendation: (a), unless the
  spike shows (b) reaches as far and keeps the D4 eye's view clear, which
  would remove the retreat.
- PS-Q7 The branch: (a) `puck-slide` cut from tampura-bridge in the main
  checkout when no other session commits there; (b) `track/puck-slide` in
  a sibling worktree cut from the tag stable-2026-11-06, as BF#68's tracks
  do. Recommendation: the one Hani names; (b) if BF#68's practice now
  replaces his older rule against worktrees, else (a).
- PS-Q8 The pushable rule: (a) perceived width above 0.078 m on every grasp
  axis; (b) a declared per-category flag (task knowledge). Recommendation:
  (a), pipeline-wide, with the find_dice width check of 7.3 deciding
  whether it needs a margin.
- PS-Q9 Mass: (a) no mass model (T3's estimate is mass-free; the shot's
  launch carries a body term of 1.4 to 1.6 % or a per-object factor from
  the test push's track); (b) their MASS of 1 kg (env.py:73) as task
  knowledge, a per-object model against the spirit of the A1 withdrawal.
  Recommendation: (a).
- PS-Q10 Seeds: (a) 0 to 19 (H4); (b) 0 to 59 with 0 to 19 reported apart.
  Recommendation: (b).
- PS-Q11 Cost study: (a) laptop, C0 and C1 on random-pairs plus the
  find_dice widths; (b) the full matrix of 7.3 on the cluster or the
  chair's cloud. Recommendation: (a) first; (b) only on Hani's explicit
  approval of that run. C1 is expected free by construction and stays as
  the check.
- PS-Q12 (new) The friction's source and its eye: (a) T3 from the D4 eye
  after a planned Cartesian retreat (H1- and G9-clean; whether the view
  clears early enough is the spike's day 1); (b) T3 from an overhead fixed
  eye of our own (sees the early slide with the arm in place; a new
  constant derived once in a BF# entry, a puck_slide form of G20, deviation
  D-2); (c) T2, the launch calibrated against the command of PS-Q5 (d)'s
  stroke (no new sensor; weak at the test push's 0.2 m/s). Recommendation:
  (a) if the spike shows the view clears early enough for T3's
  high-friction precision, else (b); not (c).
- PS-Q13 (new) H3: (a) accept the friction literal as a named relaxation
  of H3 (not small, not a literal over a named region), its M entry's
  CLAIM EFFECT saying so; (b) refuse, and puck_slide stays future work.
  Cost of (a): the paper cannot call the puck_slide arm H3-conforming and
  must present the extension as such. Recommendation: (a) if PS-Q1 is
  (b'); otherwise the question can wait until after the paper.
- PS-Q14 (new) BF#66: (a) no claim for this paper; the friction literal is
  presented as M8's commit-margin pattern applied to an attribute, which
  the proposal itself calls nothing new (:231-232); (b) grant BF#66 a claim
  effect for this paper. Cost of (a): the paper may not present puck_slide
  as evidence for attribute boxels, only as M8's pattern carried to a
  scalar attribute (which itself needs PS-Q13 (a)). Cost of (b): it
  overrides BF#66's logged "none for this paper" (PA:9346-9351) and needs
  its own audit entry before the paper. Recommendation: (a).
- PS-Q15 (new) Success scoring and arm O's reward: (a) the shared
  world-state test for both arms, a true-pose read in scoring that H1 lists
  (PA:3259) under BF#36 and BF#37's precedent, and no TAMPURA reward column
  for arm O; (b) the same plus an arm-O reward written through G6's channel
  with a true-pose observation, as an evaluation-only exemption. Cost of
  (a): both arms' success rests on a truth read in scoring that H1 lists,
  covered so far only by the find_dice precedent, and the table loses arm
  O's reward column (G12's rewards[-1] parity has no puck_slide form); arm
  T loses nothing, since its reward equals the shared test by
  construction (8.1). Cost of (b): a new writer of their belief fed the
  true pose, an exemption to H1 and G6 that must be shown never to reach
  arm O's decisions. Recommendation: (a).
