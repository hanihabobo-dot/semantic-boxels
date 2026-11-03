# The case against tool_use, puck_slide and slam_collect as comparison tasks

Written 2026-11-03 for Hani, read only (no edits to the repo or to /root/tampura-work, no runs of either planner). Written task by task; the closing comparison is last.

## 0. Ground rules of this argument

What "fit" means here (from the request):
1. RUN: his pipeline, at the code level of `tampura-bridge` today plus a bounded amount of new work, runs on the task in TAMPURA's environment under the same success criterion as TAMPURA.
2. METHOD: the task exercises what Semantic Boxels is for (finding and handling objects under partial observability and occlusion through semantic regions), so a result says something about the method.
3. TIME: the work fits before 2026-12-04 (31 days from today) next to what is already in flight: the die-slip follow-up (BF#59 is "DONE, decisions open", PAPER_AUDIT.txt:8512; BF#62 of 2026-11-02 at :8824), the BF#63 cluster re-run submitted today (commit 9ff6979), the class_uncertain plan started today (commit 03a180d) and the paper itself.

The constraints Hani set, which every "cheapest path" below must respect:
- One environment and one success criterion for both arms; TAMPURA's code untouched (BF#35, PAPER_AUDIT.txt:7364-7416; H4 at :3270-3273).
- H1 (:3256-3259): no welds, no teleports of task objects, no ground-truth reads and no reads of TAMPURA's belief or world internals feeding any decision. H2 (:3260-3264): the planner decides WHAT, WHERE and ORDER from the belief. H3 (:3265-3269): model tweaks only if small and expressible in the POD model (belief as literals over named regions, a sense action with a deterministic observation, hidden regions as belief volumes, discovery by relocation and sensing, optimistic determinisation, replanning).
- G1 (:3285-3313) lists setCollisionFilterGroupMask, changeDynamics and set_pose among the world writes the campaign import graph may not make outside the allowlist.
- Arm O keeps physical execution (BF#37, :7507-7526). B9, his perception and planner on THEIR kinematic execute layer, was designed (BF#36, :7418-7505, estimated 3 to 4 days at :7504) and then parked by BF#37.
- Assumption A1 as for find_dice: the object models (meshes, extents, masses, grasps) are already in his system.

Evidence classes used below:
- READ: code read in this session, cited file:line. Their files are relative to /root/tampura-work/tampura_environments/tampura_environments/ unless the path says otherwise.
- MEASURED: one read-only PyBullet probe written for this report, `probe_tool_use_filters.py` in this scratchpad folder, run in /root/armO-venvA with `python -B -I`. It imports nothing from their tree, reads their Panda URDF and prints to stdout.
- PAPER: arXiv 2403.10454 v2, HTML, read through a fetch tool that returns a digest. Paraphrased with the section named; one short quote at most.
- SURVEY: numbers taken from tampura_tasks_survey.md (Table I to III values; it read the tables in two passes that agreed). Not re-read here.
- UNVERIFIED: marked where used.

---

## 1. tool_use (paper task B, "Pose Uncertainty")

### 1.1 What the task is (READ)

- Scene: an extended table (their table lengthened by 0.5 m in x, env.py:228-238), a hook URDF at a fixed known pose (0.1, -0.35, 0.02), yaw -30 deg (env.py:267-271), and three 4 cm cubes (BLOCK_SIZE 0.02 is the half extent, env.py:35; mass 0.1 kg, panda_env_utils.py:548-572) whose means are drawn per seed in x [0.4, 0.7], y [-0.3, 0.3], at least 0.2 m apart (env.py:580-586). No saved scenes: the seed fixes the scene.
- Hidden variable: each cube's pose. For every cube, `add_gaussian_distributed_cubes` creates NUM_PARTICLES = 10 bodies drawn around the mean with std 0.02 m (env.py:32, 36, 182-219, 276-284); the first one is the task object, the other nine are particles (env.py:289-290). The executing world and the belief's sim world are built by the same function from the same means with independent draws (env.py:588-589), so the executing world contains 30 cubes plus the hook.
- Actions (env.py:643-717): pick needs known-pose (:658); place and stack write the commanded pose into the belief (:562-564, :457-459); pull-towards needs the hook in hand and NOT known-pose, and its one stochastic outcome is known-pose (:703-715). known-pose holds when the robust std of the particles drops below 0.01 m (:33, :129-136, :163-165). No sensing action exists.
- Reward: on(c0, c1) AND on(c1, c2) on the belief (:719-724), with on() computed from particle means (:167-173). The rollout scores the abstract belief only (tampura/tampura/policies/policy.py:107-108, 135-138; spec.py:140-143).
- The belief never reads the executing world. Every observation is computed from the belief or from a commanded pose: pull from belief.get_com (env.py:355-356, 418-420), stack from belief.get_pose (:430-431, 457-459), pick returns conf and grasp only (:523), place returns the commanded pose (:562-564). TampuraEnv.step only passes the execute_fn's observation on (tampura/tampura/environment.py:65).
- Their executor carries kinematically: pick_execute sets state.grasp (panda_env_utils.py:963), apply_sequence re-attaches the held body at every waypoint (:633-634), and GhostSceneState attaches the cube AND its nine particles (env.py:39-54). The cube jumps into the hand wherever it really was.
- PAPER: Sec. VI-A describes B as stacking objects under local pose uncertainty; App. C2 says "The goal is to stack the cubes with no wrist-mounted camera." and suggests the hook to bring cubes into reach. Sec. VI-B says determinised belief-space planning suffices for this domain. SURVEY: TAMPURA 0.66 +- 0.07, BayesOpt+WAO 0.70 +- 0.07, BayesOpt+MLO 0.65 +- 0.07 (Table I); 9.69 executed steps (Table III).
- `grep -c -i "getCameraImage|get_image|camera|segmentation|render"` gives 0 hits in tool_use/env.py (49 in find_dice/env.py).

### 1.2 The case for "no fit"

RUN. Their executing world is a picture of the belief, not a world his pipeline can perceive or manipulate as ground truth.
- Every cube, the task cube included, is created orange with alpha 0.2 (env.py:198, with alpha = 2/10 at :282). A camera would image 30 cubes of identical colour and alpha; only body ids say which one is the task cube. How his TinyRenderer path and shadow caster treat alpha 0.2 bodies in depth is UNVERIFIED; at best the identity map (world.objects) makes perception ignore the 27 particles, at worst they occlude, cast shadows and block placements.
- MEASURED: the cubes cannot hold each other up. With tool_use's filters (cubes group 2, mask 4; table group 4, mask 11; env.py:247-255, 263-265, 286-287), a 4 cm cube set on another 4 cm cube under gravity -10 ends at z 0.02 after 480 steps, inside the lower cube, with 0 cube-cube contacts; with default filters it stays at z 0.06 with 4 contacts. A physically executed tower cannot stand in their world. TAMPURA's towers stand in its executing world only while no pull follows the stack, because the pull is the one place where its executor steps physics (env.py:416; sim_steps defaults to 0 everywhere else, panda_env_utils.py:620-639).
- MEASURED: the fingers do touch the cubes. Under the same cube filter, a cube created at the centre of each finger link's AABB reports 1 contact with that link and 4 with the robot, and getClosestPoints at distance 0 returns a point. (Why the robot passes the filter while two cubes do not is my reading of PyBullet's default filter mode, UNVERIFIED; their tree never sets collisionFilterMode or setPhysicsEngineParameter, grep over /root/tampura-work/tampura and tampura_environments, so the probe ran in the same mode as their worlds.) So a physical top-down pick of the task cube also pushes into its nine particles, which carry the same filter and stand within a few centimetres.
- His physical arm (BF#37) would therefore fail every stack by construction: the released cube falls through its support, and execute_stack's release check compares the observed top with the support top plus the cube height within 2 cm (execution.py:1883-1904, 852), so it would report the failure. The only route left is B9's kinematic layer, which Hani parked.
- The bridge cannot adopt the world as written: HookWorld passes no categories (env.py:310-317; World.categories defaults to [], panda_env_utils.py:582), while env_adapter registers task bodies through zip(world.objects, world.categories) and builds the plan twin with create_ycb (tampura_bridge/env_adapter.py:127-136). The cubes are create_block boxes, the hook a URDF, the table extended. scoring.py builds a find_dice SceneObservation (tampura_bridge/scoring.py:47-69) and policy.py fixes the mission to holding the target at home (tampura_bridge/policy.py:218-219, 238-253).

METHOD. Nothing is hidden in space. Three cubes and a hook lie on an open table. His own stack mode is, in his code's words, the mode with no occluders, no shadows and no sensing (test_full_pipeline.py:1131-1134). The uncertainty is a 2 cm pose cloud that his cameras would measure directly (expected, UNVERIFIED on this scene), on a task that the paper defines as sensorless. There are only two ways to run him:
- Sighted (his fixed eye and wrist camera on their executing world): he solves an easier task than TAMPURA, because TAMPURA's environment gives TAMPURA no observation channel at all.
- Blind: his registry is built from detections (perception.py:299-312) and his free space is observed space (audit #67, PAPER_AUDIT.txt:4443-4444). Without a render he has no object boxels, no free space, nothing to plan over. Seeding the registry from their particle means or from the simulator's poses is exactly what H1 forbids.

TIME. Every version needs B9 (3 to 4 days for find_dice alone, BF#36 :7504), a new adapter, a new goal and a new scoring channel, inside a month already holding the die-slip follow-up, the BF#63 re-run, class_uncertain and the writing.

### 1.3 The strongest counterargument

tool_use is structurally the closest TAMPURA task to his current model, closer than the survey said:
- M8 already gates pick on a pose-known literal: (obj_pose_known ?o) is a pick precondition (pddl/domain_pddlstream_m8.pddl:254), emitted only when the pose radius is within the commit margin (PAPER_AUDIT.txt:4456-4460). TAMPURA's pick is gated the same way by known-pose (env.py:658).
- M8 has an action whose job is to establish that literal: observe(o, q) with the wrist camera (domain :396-410; PAPER_AUDIT.txt:4461-4463). TAMPURA's pull-towards has the same job (env.py:712).
- He stacks: a stack action with on and clear (domain :362-391), a tower goal builder (test_full_pipeline.py:598-643) and a physical execute_stack (execution.py:1678).
- His 100 g, 40 mm cube class (BF#38, PAPER_AUDIT.txt:7542-7543) has the size and mass of their cubes (4 cm, 0.1 kg).
- A world-state version of their criterion is easy to write: a terminal HookObservation whose poses are the cubes' readback collapses their belief onto the readback (env.py:150-151), so their own on() test runs on the real poses, the same pattern as find_dice's D3.

On this reading both arms solve one abstract problem, "stack three 4 cm cubes whose poses must be known before a pick", TAMPURA by funnelling them with a hook and Semantic Boxels by looking. Sensing against non-prehensile funnelling is a contrast a reader might find interesting.

### 1.4 Does the counterargument survive? No.

The counterargument is right about the abstract structure and wrong about fit, for three reasons in order of weight.
1. It is not one environment. The camera is part of the environment, and this task has none by design (App. C2; 0 rendering hits; observations are commanded poses). His own M8 entry argues that the wrist camera does not widen the comparison because their find_dice look action already images it (PAPER_AUDIT.txt:4471-4473). tool_use has no such action, so that argument does not carry over. A result would compare a sighted system with a blind one on a task built to be blind, and a reviewer would say so.
2. Their world cannot support his execution: towers fall through (MEASURED), particle cubes stand in the gripper's way (MEASURED contacts), and the adapter cannot register the bodies. Making it physical means changing their collision filters or removing their particle bodies, which edits their environment and trips G1.
3. Even with 1 and 2 granted, the result says nothing about semantic regions: no occluder, no shadow, no search.

The paper also already reports what a determinised planner does on B: it matches TAMPURA (WAO 0.70, MLO 0.65 against 0.66, SURVEY; Sec. VI-B).

### 1.5 The cheapest path to a fit, and what it would buy

"Sighted tool_use on B9": BF#36's S1 to S5 (their execute layer behind his primitives); a tool_use adapter (cube and hook classes in a task_spec, a box-and-hook plan twin, the identity map restricted to world.objects so perception ignores the 27 particles, after checking how his renderer treats them); a fixed-order goal on(c0, c1), on(c1, c2) (their reward has no on_table clause, env.py:719-724); a world-state on() test run on both arms' final executing worlds; TAMPURA re-run on the same 20 seeds. Effort: 1.5 to 3 weeks (my estimate, UNVERIFIED).

It would show that with a camera the hook is unnecessary: about four manipulation actions (two picks, two stacks) plus moves and observes, against TAMPURA's 9.69 steps (SURVEY). It would not show anything about hidden objects, shadows, the semantic partition or physical execution, and it gives one arm a sensor the task withholds. TAMPURA's own world-state score could also drop below its belief score, because its belief never reads the world (UNVERIFIED, not run).

A "blind" path costs more and is ruled out by H1: no camera means no registry unless it is seeded from their belief or the simulator.

### 1.6 Verdict on tool_use

No fit. It is the closest call of the three, because M8 already models pose-gated picks, an action that resolves them, and stacking, all on cubes like theirs. It fails because the task removes sensing by design (so a sighted run is not one environment and a blind run has no world model under H1), and because their executing world cannot hold a physical tower (MEASURED). The cheapest fit, sighted on B9, costs 1.5 to 3 weeks and would demonstrate a sensor advantage, not the method.

---

## 2. puck_slide (paper task D, "Physical Uncertainty")

### 2.1 What the task is (READ)

- Scene: a custom slab world, not their table scene: a 1.1 m by 0.7 m floor slab, a stool, a thin surface with lateral friction 0.1 and an "ik" region where the robot can reach the puck (env.py:39-82, 248-333). The puck is a cylinder of radius 0.06 m (12 cm across), height 0.04 m, mass 1 kg (env.py:33-34, 73, 236-245), starting at x 0.39 m (env.py:44-48). The one goal region, goal0, is the box x 1.2 to 1.4 m, y -0.35 to 0.35 m (GOAL_POSITIONS[0] and GOAL_AABB, env.py:49-56; GOAL_OBJECTS has one entry, :74). The ik region spans x 0.3 to 0.9 m (:58-62). One geometry for all seeds; the seed draws only the friction and the particles.
- Hidden variable: the puck's lateral friction, uniform in [0.05, 0.15] (env.py:63-64, 681). The belief is 20 particle pucks with frictions drawn uniformly in 1/friction (:353-356), reweighted by a Gaussian likelihood of each particle's simulated final xy against the observed xy and resampled with jitter (:156-196). known-friction holds when the weighted std is below 0.01 (:144-145).
- Actions (env.py:718-743): push-to(puck, goal0) needs the puck in the ik region, depends on known-friction, removes in(ik), and its verify effects are in(goal0) and known-friction. nudge(puck, d) needs in(ik) and its one outcome is known-friction; d is a sampled direction scaled to 0.2 m (:654-657) pushed with effort 0.005 (:622-630). Both actions need in(ik), so after the one push-to that leaves the ik region nothing but no-op applies: an episode is some nudges and one shot.
- The push controller (shoot_controller, env.py:422-512) plans a Cartesian push behind the puck, then runs pc_steps = 5 physical trials. Before each trial it resets the arm and EVERY puck, the real one included, to the start pose (:493-501), follows the joint path with a motor controller and 2000 settle steps (:384-415), and corrects the effort from the median final x of all 20 pucks (:505-509). push_execute_fn then sets all pucks to the real puck's final pose of the last trial (:540-541) and returns that pose as the observation (:543-545).
- Reward: in(puck, goal0) (env.py:745), true when a 2 cm box around the believed puck pose lies in the goal box (:660-672). The believed pose IS the observed pose of the real puck (:228, 543-545), so this is the one task of the three whose reward follows the physical world.
- The executing world holds the real puck (alpha 1.0, true friction) and 19 particle pucks (alpha 0.2) that do not collide with each other (env.py:335-361); after every push they sit on the real puck's pose (:540-541). World is built with objects=pucks and no categories (:378-380).
- PAPER: Sec. VI-A describes D as hitting a puck with unknown friction into a goal region; App. C4 describes one puck on a shuffleboard, friction drawn uniformly, a direct push or local pushes that keep the puck in reach; Sec. VI-B says optimal plans need 1 to 4 controller executions, which is why model-free baselines do relatively well. SURVEY: TAMPURA 0.52 +- 0.11, DQN 0.47 +- 0.09, eps-greedy 0.42, None 0.34, MLO 0.29, WAO 0.24 (Table I); 3.75 executed steps, 5.00 abstract beliefs visited (Table III).
- Rendering: 3 grep hits in puck_slide/env.py, all LockRenderer (:461, 494-495), no camera.

### 2.2 The case for "no fit"

RUN. None of his actions can act on this task.
- He cannot grasp the puck: 12 cm across against the Panda's 8 cm opening (finger joints 0 to 0.04 m each, their models/srl/franka_panda/panda.urdf:348, 355), and the puck lies flat on the slab.
- He cannot carry it to the goal either: goal0 starts 1.2 m from the robot base at the origin, beyond the Panda's reach (855 mm is Franka's published figure, not measured here).
- The only way to move the puck is a push, and his system removed push: "compute_push_displacement() removed (#53): push superseded by pick-and-place" (execution.py:1935-1937). His domain has sense, move, pick, place, place_hiding, stack and observe and nothing else (pddl/domain_pddlstream_m8.pddl:175-410).
- Their push controller is the only one in the environment, and it resets the real puck to its start pose five times per push (env.py:500-501), using the real puck's practice outcomes to set the effort of the next trial (:505-509). If his arm used it (the B9 pattern), H1's "no teleports of task objects" would be broken on his arm. If he wrote his own controller, the comparison would measure controllers.
- The bridge set-up would damage the task. D9 sets every task body's lateral friction to 1.0 (tampura_bridge/policy.py:81-85, task_spec.py:58), plus gravity -9.81 where they use -9.8 (policy.py:68, task_spec.py:61; their env.py:258) and, with BF#59's solver_iters on, more solver iterations (policy.py:74-80). As written D9 touches no puck, because the world has no categories (env.py:378-380); a port that registers the puck the find_dice way would overwrite the one quantity the task hides. In find_dice D9 could declare the physics because their world never stepped it (BF#35, PAPER_AUDIT.txt:7378-7383); here the physics is the task.

METHOD. Nothing is hidden in space. One puck in plain view whose pose the environment reports exactly after every push; two fixed boxes as regions (ik, goal0); no occluder, no shadow, no search, no pick or place. The hidden quantity is a dynamics parameter, and the sense that reveals it is not a render but a push whose outcome must be inverted through a physics model (their particle filter, env.py:209-229). His perception, boxelisation, shadow caster and executor would all stand idle; only the planner would act, choosing between two actions.

TIME. A push primitive, a friction estimator, a slab adapter and a two-action domain: 1 to 2 weeks (my estimate, UNVERIFIED) for a result off the paper's topic.

### 2.3 The strongest counterargument

- The success criterion is genuinely shareable, unlike tool_use's: their belief's puck pose is the real puck's observed pose (env.py:228, 543-545), so a world-state test "the real puck's pose passes test_in for goal0" equals their reward for both arms.
- The decision layer fits his model language. known-friction is a K-literal that only an observation (a nudge) can set, and push-to depends on it. M8's own POD justification, that a pick commits on a pose only within what the gripper tolerates and otherwise the planner must plan the observation that can guarantee it (PAPER_AUDIT.txt:4467-4469), reads unchanged as "a push commits only on a known friction, otherwise the planner must plan the nudge". That is H3's pattern applied to a physical parameter.
- A result would test whether his POD machinery generalises beyond geometry, which a reader could take as a strength claim.

### 2.4 Does the counterargument survive? No.

The decision layer is expressible, but everything that would make the arm his is missing or forbidden:
1. The observation function is not his. Turning a pushed pose into "friction known" needs an inverse-dynamics estimate. Reading their PuckSlideBelief would put TAMPURA's belief internals into his decisions (H1); writing his own filter is new work that has nothing to do with semantic regions.
2. The execution is not his. Pick, place, stack, sense and observe all stand idle (puck too wide, goal out of reach), push was removed from his system, and the only push controller in the environment teleports the task object between practice trials.
3. The policy space is tiny: nudge k times, push once. With "push needs known-friction" in the domain, an optimistic planner will always calibrate first and then shoot. That is one fixed rule against TAMPURA's learned outcome model over a 1 to 4 step horizon. The paper's determinised rows on D (MLO 0.29, WAO 0.24 against TAMPURA 0.52, SURVEY) are the closest published analogue of what such a port would measure; that it would land near them is my expectation, UNVERIFIED.

The shareable criterion is the one real point in favour. It settles the criterion half of point 1 and none of the rest: his actions, the method and the time.

### 2.5 The cheapest path to a fit, and what it would buy

"Two operators on their controllers": a generated domain with nudge and push-to over known-friction, their execute_fns as the execute layer (the B9 precedent, parked in BF#37), a slab adapter (no categories, their custom world, the puck exempted from D9's friction), the world-state goal test above, and TAMPURA on the same 20 seeds. Effort: about 1 week reading known-friction from their belief, which breaks H1; about 2 weeks with his own friction filter (both my estimates, UNVERIFIED).

It would show how a fixed "calibrate, then push" decision does against LAO* with a learned model on a one-shot physical task. It would not show anything about perception, regions, occlusion, search, or his physical pick and place, and with their controller it would not even show his execution.

### 2.6 Verdict on puck_slide

No fit. It has the most shareable success criterion of the three, but his system cannot touch the puck: too wide to grasp, goal out of reach, push removed (#53), and the only push controller resets the real puck between practice trials. The hidden variable is a friction coefficient, so his perception, regions and search are idle. The cheapest fit costs 1 to 2 weeks and would test a two-action decision rule.

---

## 3. slam_collect family (paper tasks E-M and E-MF, "SLAM")

### 3.1 What the task is (READ)

- World: a pure 2D Python simulation. The imports are numpy, matplotlib and imageio (slam_collect/env.py:1-27); a grep for pybullet or pb_utils finds nothing. A 10 m by 10 m plane (ENV_SIZE, :49), a 0.3 m by 0.6 m rectangular robot starting at (1, 1, 1 rad) (:47, :1335), a 0.8 m goal square at (8, 8) (:48, 1227-1231), positions clamped to the plane (:374-375).
- Variants (registered at :1607-1609; slam_collect_1p.yml names a task with no registered env):
  - slam_collect (E-M): 5 random rectangular obstacles, 5 beacons, 3 targets of 0.5 m by 0.5 m, 4 corner points (:1216-1219, 1245-1315). Goal: every target in the goal region in more than 80 % of particles, and no collision (:1525-1535, 56, 264-271).
  - slam_collect_simple: 20 obstacles; goal: the robot in the goal region without collision (:1538-1553).
  - slam_collect_custom: no obstacles, no targets, no corners, one beacon at (5, 5); same goal-only reward; gamma 0.95 in its yml (:1556-1604).
- Hidden variable: the robot's own pose. Each move adds Gaussian noise of std 0.04 m to the commanded x and y steps (:50, 640-687). The belief is 20 particles, each a deep copy of the initial state (:89-96, 1216): obstacles, beacons, targets and goal are known exactly, only the robot pose (and what it carries) spreads. known_pose holds when the x and y variances are below 0.05 (:53, 212-218).
- Sensing: move_look and move_corner return the exact true pose when the robot ends inside the beacon's 2 m square or the corner square (:43-46, 303-306, 365-367), and every particle snaps to it (:203-205). There is no line-of-sight test anywhere; obstacles never hide a beacon.
- "Manipulation": a target attaches when the robot rectangle overlaps it at the end of a move and detaches on place (:862-876, 1086, 1140). Paths come from an RRT on the mean particle with zero noise (:694, 1071-1141). Without visualisation, collision is checked only at the end state of each action (:849-852).
- Execution: the "executing state" is the same 2D simulator run on one noisy sample (:331-369).
- PAPER: Sec. VI-A describes E-M as a 2D version of a mobile manipulation task with ego-pose uncertainty that grows except at localisation beacons, and E-MF as moving to a goal without touching blocks; App. C5 says the initial state is fully known and that beacons stand in for AR tags; App. C5 and Sec. VI-B say the manipulation-free variant is there to verify the baselines' implementations. SURVEY: E-M TAMPURA 0.81 +- 0.02, eps-greedy 0.74, WAO 0.56, MLO 0.41, None, Q-learning and DQN 0.00, MCTS 0.03, 129 +- 55 s per step, 9.22 steps; E-MF TAMPURA, MLO, WAO and None 0.95, eps-greedy and Q-learning 0.93, MCTS 0.92, DQN 0.55, 31 +- 11 s per step, 1.20 steps. Which repo variant is E-MF is UNVERIFIED (survey).

### 3.2 The case for "no fit"

RUN. There is nothing for his pipeline to adopt. The bridge adopts their PyBullet client (tampura_bridge/env_adapter.py:84), his perception renders RGB, depth and instance segmentation from it (perception.py:299-312; boxel_env.py:1805-1890), and his executor drives a fixed-base Panda through PyBullet. slam_collect has no client, no 3D body, no camera, no arm and no physics. The success criterion (a particle fraction above 0.8 inside a region) is defined on their 2D particle belief and on nothing physical.

METHOD. Nothing is hidden in space: the map is given in full at t = 0 (App. C5; :89-96). The only uncertainty is where the robot itself is, a quantity his fixed-base arm always knows from its joint readback (the readback scoring already uses, tampura_bridge/scoring.py:53-54). Beacons reveal the pose without any visibility geometry, so his shadow machinery has no counterpart.

TIME. A port is a new domain and a new 2D harness. E-M costs TAMPURA about 20 minutes per episode (9.22 steps x 129 s, SURVEY), so about 6.6 hours for 20 seeds on the T arm alone (my arithmetic), on the chair's cloud and only with Hani's approval of that run.

### 3.3 The strongest counterargument

- Their abstract model is already a POD model in his sense. known_pose is a K-literal that only an observation in a named region (a beacon square or a corner) can set; the regions are named symbols; the goal is over region membership. That is H3's description almost word for word, and optimistic determinisation with replanning ("drive, localise when the literal is lost, continue") is the natural policy.
- It is the one task besides find_dice in which the robot must go somewhere to sense, like his sense configurations (sense_view, pddl/domain_pddlstream_m8.pddl:55-57, 182).
- A pure planner port keeps one environment and one criterion: their execute_fns, their reward.
- E-M is where the paper's determinised planners lag (MLO 0.41, WAO 0.56 against 0.81, SURVEY), so a strong result there would be striking, and E-MF would cost almost nothing as a sanity check.

### 3.4 Does the counterargument survive? No.

1. A port would test his planner on TAMPURA's model, not Semantic Boxels. Perception, boxelisation, shadows, free space, 3D geometry and physical execution all drop out, and the "regions" are given rectangles, not perceived ones. The system under test changes.
2. The planner's state would have to come from their particle belief (known_pose, in and target_in are all particle statistics, :212-279), which is TAMPURA's belief internals feeding decisions (H1), unless he writes a 2D particle filter of his own.
3. The published analogue already exists. The paper's MLO and WAO are determinised planners (maximum-likelihood observation and weighted outcomes, Sec. VI-B) paired with the same Bayes-optimistic learning row; whether they share TAMPURA's learned model is not stated (UNVERIFIED). An optimistic replanner on their model belongs to that family, and on E-M that family scores 0.41 to 0.56. Where his port would land is my expectation, UNVERIFIED.
4. E-MF cannot separate methods: all but DQN score 0.92 to 0.95, and the paper itself uses it to check implementations.

### 3.5 The cheapest path to a fit, and what it would buy

"Planner port on E-MF, then E-M": a generated PDDL domain for move_to and move_look (E-MF), then move_pick, move_place and move_corner (E-M), with known_pose as a K-literal and optimistic effects; their execute_fns as the execute layer; each step's PDDL init built from their abstract belief (H1 breach) or from a particle filter of his own. Effort: 3 to 5 days for E-MF, 1.5 to 2 weeks for E-M plus the 6.6 hours of TAMPURA runs (my estimates, UNVERIFIED).

It would show how an optimistic classical replanner does against LAO* on 2D localisation inside TAMPURA's model; on E-MF it would show nothing, since every working method reaches the ceiling. It would not show anything about his perception, regions, occlusion, search or execution.

### 3.6 Verdict on slam_collect

No fit, the clearest of the three. There is no PyBullet world for the pipeline to adopt and nothing to perceive; the uncertainty is about the robot's own position, an uncertainty a fixed-base arm never has. The only thing that can be ported is the planner, and the paper's determinised baselines already occupy the place where that port would most likely land.

---

## 4. The three side by side

| | tool_use (B) | puck_slide (D) | slam_collect (E-M, E-MF) |
|---|---|---|---|
| hidden quantity | a 2 cm cloud over each cube's pose, no sensor | the puck's friction | the robot's own 2D pose |
| anything hidden in space? | no | no | no (map fully known) |
| renders images? | no (0 hits) | no (LockRenderer only) | no (no PyBullet) |
| his actions usable | pick, stack, observe in form; a physical tower cannot stand (MEASURED) | none: puck too wide, goal out of reach, push removed | none: no arm, no 3D |
| shared criterion | possible via a pose readback | yes, their reward follows the real puck | only their particle belief |
| strongest counterargument | M8: pose-gated pick, observe, stack, same cubes | friction as a K-literal, nudge as sense | their model is already a POD model |
| survives? | no (sighted is not one environment; blind has no registry under H1) | no (observation, controller and policy not his) | no (only the planner ports; MLO and WAO already exist) |
| cheapest fit, cost (mine) | sighted on B9, 1.5 to 3 weeks | two operators on their controllers, 1 to 2 weeks | planner port, 0.5 to 2 weeks plus about 6.6 h of TAMPURA runs |
| what that would show | a camera beats no camera | a fixed calibrate-then-push rule against LAO* | Fast Downward on TAMPURA's 2D model |

All three fail the method test for the same reason: none of them hides anything in space. find_dice is the only TAMPURA task that renders images (49 grep hits against 0, 3 lock-renderer calls and 0) and so the only one where what the robot can see is part of the task. The three others hide a pose cloud from a robot that has no sensor, a friction coefficient, and the robot's own position. They fail the run test in different places. tool_use can only run Semantic Boxels sighted, which is not one environment, or blind, which leaves no registry under H1, and its world cannot hold a physical tower. puck_slide has the most shareable criterion but offers none of his actions. slam_collect has no PyBullet world at all. tool_use is the closest call, because M8 already gives him a pose-gated pick, an action that establishes the pose and a stack goal on cubes like theirs; it still fails, because the task withholds sensing by design. slam_collect is the clearest no-fit. Each cheapest fit would cost between half a week and three weeks of a month that is already full, and each would measure something other than Semantic Boxels: a sensor advantage, a two-action decision rule, or Fast Downward on someone else's model. The verdict would change only by relaxing a rule Hani has set or by building new capability: for tool_use, accepting a sighted arm on a sensorless task (against BF#35's one environment) together with kinematic execution (parked by BF#37); for puck_slide, a push primitive (removed under audit #53) and a friction estimator as pipeline features; for slam_collect, nothing short of a different system. The survey's two better uses of the month stand: class_uncertain, already being planned, and more find_dice layouts from their own generator.

## 5. UNVERIFIED items in this report

- Why the Panda's fingers pass tool_use's cube filter while two cubes do not (the contact itself is MEASURED; the mechanism, PyBullet's default filter mode, is my reading).
- How his TinyRenderer path, perception and shadow caster would treat tool_use's 27 particle cubes at alpha 0.2.
- Whether TAMPURA's world-state score on tool_use would fall below its belief score.
- The Panda's 855 mm reach (Franka's published figure, not measured).
- Whether the paper's MLO and WAO share TAMPURA's learned model (the paper pairs them with the same learning row but does not say so), and where a port of his planner would land relative to them.
- Which repo variant is E-MF (from the survey).
- All Table I to III numbers (SURVEY, not re-read here) and all effort estimates (mine).

## 6. What this session wrote

- This file and probe_tool_use_filters.py, both written in the session scratchpad and copied the same day by the session that started this agent into archive/tampura_bridge_plan_2026-10-25/class_uncertain/ (tracked), where both now live. Nothing under /root/tampura-work. The probe's full output:
  - FINGER x CUBE, default filters: panda_leftfinger and panda_rightfinger each 1 link contact, 4 robot contacts, 1 closest point at distance 0.
  - FINGER x CUBE, tool_use cube filter: the same numbers.
  - STACK, default filters: z_lower 0.02, z_upper 0.06, 4 cube-cube contacts.
  - STACK, tool_use filters: z_lower 0.02, z_upper 0.02, 0 cube-cube contacts.
