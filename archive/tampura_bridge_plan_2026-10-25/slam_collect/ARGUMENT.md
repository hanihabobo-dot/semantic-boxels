# slam_collect: the case for running Semantic Boxels on it, and a design

Status: revised 2026-11-06 after a fresh review (REVIEW.md, verdict "survives with changes"): sections 1, 2.1, 2.7, 3.1, 3.3 to 3.7, 4.3 to 4.8 and 5 to 9 changed, section 10 replaced, sections 11 (the pilot's rule), 12 (review and answers) and 13 (final verdict and decisions) added. Written by one agent for Hani, read only over both trees (no code, audit, ledger, branch or commit touched; the only files written are this one and `probe/`, plus scratch run folders under /root/sc_probe in WSL). For review: every claim carries a file:line, a probe file or one of the marks below.

Evidence classes. READ: code read in this session, cited file:line. MEASURED: the read-only probe in `probe/` (this folder), run in WSL with their venv from `/root/sc_probe`, outputs in `probe/out/`. PAPER: arXiv 2403.10454 as quoted by `../class_uncertain/TAMPURA_TASKS_SURVEY.md` (section 0b, lines 36-46). ESTIMATE: mine. UNVERIFIED: not checked.

Shorthand for their files: `E` = /root/tampura-work/tampura_environments/tampura_environments/slam_collect/env.py, `T/` = /root/tampura-work/tampura/tampura/, `C` = /root/tampura-work/tampura_environments/env_configs/slam_collect.yml. Ours are relative to the repo root.

Hani's request (2026-11-06, verbatim): "slam_collect i think this one can work as well, after avery move every new dot is a new know if fluent. we use ther dynamics and preception and everthing. im not sure if we can use boxels in thier setup to still reason about space to not get too many fluents even in this 2 d world. we get the same actions as they do and same env and perception. how we use their perception to come up with a world model and what luents we have and how we plan is our bussnis."

---

## 1. The case in one page (revised after REVIEW.md)

**Where it stands.** A fresh review (REVIEW.md, verdict "survives with changes") found every citation sound and every probe number reproducible, and the case for a week-long comparison weak. I accept its two main objections (O1, O2). The recommendation is now narrower: run only the arm T pilot, decided by a go or no-go rule written before it runs (section 11). Section 12 answers the review point by point; section 13 gives the final verdict and the decisions.

**What we would run.** TAMPURA's slam_collect exactly as shipped: their 2D environment, motion noise, controllers, observation function and reward, their seeds 0 to 19. Each step our side receives exactly what their agent receives (one `SlamObservation`, E:59-66, through `TampuraEnv.step`, T/environment.py:49-67) and returns one of their six actions with their argument types. Ours: the estimator built from those observations, the fluents, the domain and the planner (PDDLStream with Fast Downward's 'ff-astar2', as in our pipeline, pddlstream_planner.py:1130). It tests the planning half of Semantic Boxels (known-if literals over named regions, a sense action that sets them, optimistic determinisation, replanning after every observation; H3, PAPER_AUDIT.txt:3265-3269), not perception, occlusion, shadows or physical execution, none of which exist in this task (9).

**O1: what the probe predicts under the paper's criterion.** Fixed rules (scripted, not our planner) run in their environment score 0.51 to 0.60 under their reward on seeds 0 to 19 and 0.55 to 0.63 on held-out seeds (3.5, 3.6); the best of them 0.58 to 0.63, and the recommended gate with the design's estimator form 0.60 (S1y; S4y 0.54). That is the paper's WAO (0.56) within about a standard error and far below TAMPURA's published 0.81 (PAPER, Table I; MLO and WAO share TAMPURA's learned model in this repo, mdp_solver.py:186-195, UNVERIFIED for the paper's runs). The probe gives no reason to expect our planning layer to beat the paper's determinised baselines under the paper's criterion. Under the shared world-state test (primary by BF#35 and BF#37) the same structures win 52 to 56 of 60 episodes, a return of 0.69 to 0.75, but the paper has no TAMPURA number for that test, and 8 to 10 of those 60 wins come from our estimator reading observation fields their filter ignores (the true collision flag, the failed pick), not from planning: with the rule fixed, changing only the estimator moves S4 from 42 to 52 world wins (3.6). What our planner could show is decision time at about equal return, and only if TAMPURA's released code lands near the probe's level. Whether it reaches 0.81 on this code is itself open: three of the twenty maps were never won by any scripted rule acting on their own belief (3.5, 3.6, R6).

**O2: Hani's question, answered plainly.** Can boxels keep the fluent count small and still reason about space in this 2D world? The count, yes: the recommended model has 30 fluents at every step (place destinations restricted to the goal; 60 to 90 with their region argument kept whole, 4.5), against 40 (one dot per action) to about 720 (one dot per primitive) after 20 steps for a known-if fluent per new dot (4.3), and 49 atoms in TAMPURA's own abstraction. But it is small because their observation only ever names eleven regions (E:899-903), not because of boxels: all free space merges into one class that no action of theirs can name, so the design uses no boxels. Reasoning about space, no: the one spatial ingredient I had added, `tight` facts for where the pose spread meets an obstacle, has no measured effect (the review's S4n run: the same actions in 83 of 100 paired episodes, one world win against none, p = 1.0), and the predictive gate as a whole ties "look before every commit" within a standard error (3.6). On slam_collect boxels have nothing to do; the task tests the K-literal planning layer only.

**What I recommend now (SC1).** The review's alternative: the arm T pilot alone (seeds 0 to 2 and the tight seeds 5, 6, 10; one run each; up to about 4 hours on the chair's cloud after your approval of that run, SC7; about half a day of work, ESTIMATE), decided by the rule of section 11. It stops if TAMPURA wins two or more of the tight seeds under its own reward (no scripted structure did in most repetitions) or if its median decision time is under 30 s per step; otherwise it goes, and a go buys a comparison about decision time at about equal return. On a go, the minimal version (design (c) with the one-literal gate `(looked)`, 4.5 and 5; 7 to 9 working days, ESTIMATE) only after the find_dice numbers are frozen and if a working week is free. On a stop, nothing more before 2026-12-04.

**Cheap to run, as a task.** Pure Python, no PyBullet; their controllers take a median 0.05 s per call, scripted episodes a median 4 to 13 s (3.5, 3.6; 39 to 46 s with the 100-particle sketch). A TAMPURA E-M episode takes 20 to 27 minutes when it reaches its goal belief and up to about 58 when it does not (R1).

**Variants.** E-M is `slam_collect` (registered at E:1607; reward E:1525-1535), the one to run. E-MF is most likely `slam_collect_simple` (E:1538-1553), a harness check only (every working method scores 0.92 to 0.95 there); an inference from Table III, UNVERIFIED (D-5, which also covers `slam_collect_custom` and the unregistered `slam_collect_1p.yml`).

**Deviations from their setup (aim: none; details in 3.4 and 3.7, repeated here).**
1. D-1: the initial observation is read once, at t = 0, from the belief object `initialize()` returns (E:94-96, 1370-1371), its only recipient.
2. D-2: the belief passed to their `execute_fn` holds our estimate, so their controllers plan from our mean (E:1077-1080) and take goal poses from our particle 0 (E:1082).
3. D-3: only our arm has a scoring replica of their belief, replayed after the episode from the logged history with both global random streams saved and restored, so scoring cannot change our executed noise.
4. D-4: TAMPURA is re-run on our hardware (the chair's cloud); the paper's tables are quoted beside our numbers, never mixed in.
5. D-5: E-MF is identified by inference as `slam_collect_simple`.
6. D-6: the primary success test is on the final true world (BF#35, BF#37); their belief reward is reported beside it for both arms.
7. D-7 (only if SC5 excludes it): no `move_corner` in our domain.
8. D-8: arm O runs their environment in its own venv (package versions identical, MEASURED).
9. D-9: our `in_collision` literal is the observation's true collision flag, theirs "any particle collided"; it favours us under the world test (part of the 8 to 10 estimator wins above) and not measurably under their reward (SC11).
10. U-1 to U-4 (3.4): arm O inside their rollout (removed as a deviation), the final world only (removed), the random streams (fixed), BF#3's import fix (disclosed); and the named relaxations of binding records (3.7: H1's scoring clause, H2, H3, H4, BF#37, BF#66, #P5), each with its cost.

---

## 2. Their task exactly

### 2.1 State, map and seeds (READ, MEASURED)

- Pure 2D Python simulation: a 10 m by 10 m plane (ENV_SIZE, E:49), positions clamped to it (E:374-375, 664-672). No PyBullet.
- The robot is a 0.3 m by 0.6 m rectangle (E:47) starting at (1, 1, 1 rad) (E:1335).
- Map per seed (`generate_initial_state`, E:1224-1326): 5 obstacles with sides uniform in [0.3, 0.6] m (E:1217, 1245-1263); 5 beacons, each a 2 m by 2 m "vision" square at a random pose (VISION_SHAPE, E:45-46, 1265-1281); 3 targets of 0.5 m by 0.5 m (E:42, 1283-1299); 4 corner regions of 0.01 m at the map corners (E:1301-1315); the goal, a 0.8 m square at (8, 8) (E:48, 1227-1231); a 0.01 m start region at the start pose (E:1232-1236). Everything is drawn with np.random right after `np.random.seed(global_seed)` (run_planner.py:125-131), so the seed fixes the map. There are no saved scenes.
- The state (`SlamState`, E:442-486) holds the robot, obstacles, beacons, targets, corners, attachments, goal, start and an `in_collision` flag. Named regions are `beacons + corners + [goal] + [start]`, 11 per seed (E:454-456; MEASURED: `o_beacon_0..4, o_corner_5..8, o_goal_9, o_start_10` at every seed).
- MEASURED over seeds 0 to 19: targets lie a median 5.75 m from the start (0.67 to 12.25) and 6.31 m from the goal (0.92 to 10.67); the nearest beacon centre is a median 2.42 m from a target (0.56 to 6.69) and 3.06 m from the goal (1.64 to 5.10). In 13 of 20 seeds (0, 3, 4 and 9 to 18) at least one target already overlaps a beacon square at t = 0, 20 extra `target_in(target, beacon)` atoms in all in the initial abstractions (corrected after REVIEW.md 2.3, recompute2.txt; I had written 14). Targets can start there because a beacon is placed against the earlier regions with its 2 m vision square but stored for the later overlap checks with its core shape (`all_shapes.append(BEACON_SHAPE)`, E:1280; REVIEW.md 1.1).

### 2.2 The six actions (READ: `get_problem_spec`, E:1392-1523)

All five moves run a controller on the agent's belief and execute the resulting list of primitive steps (`SlamAction(delta_x, delta_y, attach, detach)`, E:428-433) on the true state. `depends=[known_pose]` on every move (E:1410, 1423, 1448, 1469, 1494) tells TAMPURA's learner that the outcome distribution depends on that atom; it is not a precondition.

| action | args | preconditions (their spec) | deterministic effects | learned outcomes (verify_effects) | controller |
|---|---|---|---|---|---|
| move_pick | ?t target | no target held (E:1411-1413) | not in(r) for all r (E:1414) | holding(?t), known_pose (E:1415) | RRT from the mean particle to the target's pose in particle 0, attach on the last primitive (E:1071-1087) |
| move_place | ?t target, ?r region | holding(?t), not in_collision (E:1424-1427) | not in(r2) for r2 != ?r, not holding(?t) (E:1428-1435) | in(?r), target_in(?t, ?r), in_collision (E:1436-1440) | RRT to the region's pose, detach on the last primitive; if the RRT fails, detach in place (E:1123-1141) |
| move_to | ?r region | not beacon, not corner, not in_collision (E:1449-1453) | not in(r2) for r2 != ?r (E:1454-1460) | in(?r), in_collision (E:1461) | RRT to the region's pose (E:1090-1103) |
| move_look | ?r region | is_beacon(?r), not in_collision (E:1470-1473) | as move_to (E:1474-1480) | in(?r), known_pose, in_collision (E:1481-1485) | RRT to the beacon's centre (E:1106-1120) |
| move_corner | ?c region | is_corner(?c), not in_collision (E:1493) | as move_to (E:1495-1501) | known_pose, in(?c), in_collision (E:1502-1506) | a loop that turns towards the corner and steps (E:1152-1212) |
| no-op | | | | | none (E:1510; the rollout skips `step`, T/policies/policy.py:125-127) |

The RRT (`rrt_with_action_noise`, E:694-791) grows from the mean particle with zero noise (std=0 at every call site, e.g. E:1081-1083), steps of at most 0.2 m per axis (STEP_SIZE, E:55, 733-734), at most 2000 iterations, collision checks of the robot rectangle against obstacles at each node (E:754-767), and stops within 0.01 m of the goal pose (E:773-776). Attach adds every target whose rectangle overlaps the robot at the last primitive (E:862-874); the observation reports the first (E:905-907).

**Noise.** Every primitive adds independent N(0, 0.04 m) to delta_x and delta_y (ACTION_STD, E:50, 647-652); the heading becomes the direction of the noisy step (E:658-662); carried targets follow (E:674-684). After k primitives from a known pose the per-axis variance is 0.0016 k m^2 (before clamping).

**A defect in move_corner (READ, MEASURED).** The corner controller computes a forward step and a turn but builds `SlamAction(forward_step, new_delta_theta)` (E:1203), which the motion model applies as a world-frame step in x and y (E:647-656). Forward steps only ever increase x, "turns" move the robot up to 0.52 m in y, the loop never meets its convergence threshold of 0.00 and stops after 101 primitives (E:1163, 1172, 1209-1210). MEASURED (`probe/out/ctrl.json`): from the start pose, at every seed 0 to 19, each of the 4 corners, 10 noisy runs each: 0 of 800 runs ended in the named corner region; the noise-free path ends at (1.0, 10.0), (1.2, 10.0), (1.0, 0.48) and (1.0, 0.79) for the corners (0, 0), (0, 10), (10, 0) and (10, 10). From 200 random known start poses per seed (seeds 0 to 4, `probe/out/corner.json`): 21 of 4,000 noisy runs (0.5 %) and 30 of 4,000 noise-free paths (0.75 %) ended in the named corner. The action exists in their spec but almost never localises; TAMPURA's sampled model can learn that, a fixed model has to be told (decision SC5).

### 2.3 The observation (READ)

`SlamObservation` (E:59-66), built for the true state at the end of every executed move (E:340-369, 898-915):
- `regions_in`: the names of the named regions the true robot rectangle overlaps at the end of the action (E:899-903; overlap test `collides`, E:612-627).
- `holding`: the true `Attachment` (target name and the target's pose in the robot frame), or None (E:905-907).
- `primitives`: the commanded primitive list the controller computed from the belief it was given (E:912).
- `robot_pose`: the exact true pose, only after `move_look` or `move_corner` whose argument region is in `regions_in` (E:365-367); otherwise None.
- `collision`: True if the true state is in collision at the end of the action or was before (E:909; without vis only the start and end states are checked, E:849-852; the true state's flag never resets, E:887 and `from_array` copies it, E:480-486).
- At t = 0, `initialize()` builds `SlamObservation(initial_state=self.state)`, the full map and the exact start pose, and gives it to `SlamBelief` (E:1370-1371). App. C5 of the paper says the initial state is fully known (no_fit_case.md:156).

### 2.4 Their belief and its update (READ)

- `SlamBelief` holds 20 particles, each a deep copy of the initial state (E:88-96, num_particles 20 at E:1216). Only the robot pose and what it carries can spread; the map is identical in every particle.
- `update` (E:119-210): re-simulates every particle through `observation.primitives` with the same noise (E:130-137); keeps the particles whose overlapped-region set equals `regions_in` and, if the robot holds a target, whose robot overlaps that target, and gives them the observed attachment (E:165-201); snaps every particle to `robot_pose` if one came (E:203-205); refills to 20 by copying survivors (E:98-114, 207-208). It never reads `observation.collision`; a particle is marked in collision only by its own re-simulation (E:135-137).
- `abstract` (E:212-279): `known_pose` iff the population variances of x and y are both below 0.05 m^2 (KNOWN_VAR_THRESH, E:53, 213-218); `in(r)` iff more than 80 % of particles overlap r (REGION_IN_THRESH, E:56, 235-266); `target_in(t, r)` likewise (E:250-271); `holding(t)` iff every particle holds (E:273-274); `in_collision` iff any particle is in collision (E:276-277). With in_collision true, every move except move_pick (which needs empty hands) is inapplicable in their spec.

### 2.5 Reward, termination, steps, seeds

- E-M reward (E:1525-1535): for every target t, target_in(t, goal), and not in_collision, evaluated on the abstract belief (T/spec.py:140-143). E-MF candidates (E:1538-1553, 1594-1604): in(goal) and not in_collision.
- The rollout runs exactly max_steps = 20 steps (C line 6; T/policies/policy.py:105) and never stops early; TAMPURA's policy plays no-op once its belief's reward is positive (T/policies/tampura_policy.py:77-80). The reward is logged per step (policy.py:107-108, 136-138). The paper reports a discounted return, gamma = 0.98 (C line 15), and says episodes end at the first goal belief (survey, lines 38-39); I read the return of an episode that first reaches the goal after n actions as 0.98^n (UNVERIFIED as the paper's exact computation).
- Seeds: `random.seed` and `np.random.seed(global_seed)` before the env is built (run_planner.py:125-126); the paper's N = 20 (survey line 38); H4 asks for seeds 0 to 19.

### 2.6 How TAMPURA plans it (READ)

At each step, with `from_scratch: true` (C line 22) it rebuilds its abstract model (it reuses the old one only when every transition of the executed envelope had probability 1, since `envelope_threshold` is 1, C line 13, tampura_policy.py:82-100): it samples controller outcomes through `effects_fn` (E:282-328: the same controller on the belief, every particle simulated with noise, one abstract belief per distinct observation) inside `policy_search`, in batches of 20 up to 200 samples (C lines 7, 14; tampura_policy.py:120-145), learns outcome probabilities with the Bayes-optimistic rule (C line 17), and solves the learned MDP with decision strategy `prob` (C line 18; tampura_policy.py:149-160; `solve_mdp`, T/solvers/mdp_solver.py:176-197). If the chosen action is not applicable, it takes a random applicable one (tampura_policy.py:161-168).

### 2.7 The paper's numbers (PAPER, via the survey)

| | E-M | E-MF |
|---|---|---|
| TAMPURA return (Table I) | 0.81 +- 0.02 | 0.95 +- 0.00 |
| BayesOpt + MLO | 0.41 | 0.95 |
| BayesOpt + WAO | 0.56 | 0.95 |
| eps-greedy + LAO* | 0.74 | 0.93 |
| None + LAO*, Q-learning, DQN, MCTS | 0.00, 0.00, 0.00, 0.03 | 0.95, 0.93, 0.55, 0.92 |
| TAMPURA s per step (Table II, includes controller execution) | 129 +- 55 | 31 +- 11 |
| MLO, WAO s per step | 90, 100 | 35, 34 |
| TAMPURA abstract beliefs visited, executed steps (Table III) | 68.67 +- 26.56, 9.22 +- 3.84 | 50.70 +- 9.26, 1.20 +- 0.51 |

0.98^9.22 = 0.83, so 0.81 implies at most about 98 % success (survey line 117, its arithmetic); since E[0.98^n] is at least 0.98^E[n] and the steps spread by 3.84, the implied success is somewhat lower, about 95 to 97 % by the review's estimate (REVIEW.md 2.3). If that holds on the released code, TAMPURA is near its ceiling on E-M too and the room for a difference is in steps and time. Section 3.5 gives reasons to doubt that it holds on these maps.

---

## 3. The interface, the scoring and the deviations

### 3.1 Who calls what

Arm O runs inside their own rollout, `Policy.rollout` (T/policies/policy.py:96-161), with two subclasses of ours: a `Belief` subclass that is our estimator, and a `Policy` subclass whose `get_action` is our abstraction plus planner. Their rollout takes any Belief, passes it to `step` and calls `b.update(action, observation, store)` (policy.py:120-130), so no loop of ours is needed. (Revised after REVIEW.md U-1: I had proposed a loop of ours that mirrors theirs, which is a deviation that can be avoided.)

1. Seed exactly as run_planner.py:125-126, build the env with their config (C), call `env.initialize()` (E:1328-1371): this draws the map and returns `(b0, store)`.
2. Our agent gets: the store (names and types of the 11 regions and 3 targets, and the certified `is_beacon`, `is_corner`, `is_goal`, `is_start` atoms, E:1352-1368) and the initial observation (D-1: read once from `b0.particles[0]`, which is a deep copy of `initial_state`, E:94-96); our Belief subclass is built from it.
3. Each step t < 20 their rollout calls our `get_action`, then `env.step(action, b, store)` (T/environment.py:49-67), which runs their `execute_fn` (E:331-371) and returns the `SlamObservation`, then our `b.update`. For no-op it does not call `step` (policy.py:125-127).
4. After the episode, the scorer replays their `SlamBelief` from the logged `RolloutHistory.actions` and `.observations` and reads the final world from `.states` (policy.py:59-63, 106, 153), one scorer for both arms (3.3). Their rollout also logs their reward evaluated on our belief's abstraction (policy.py:107-108), a self-graded number reported only as such.

Our Belief subclass exposes `particles` as `SlamState` copies (D-2). Our estimator and predictors draw only from their own generators (`np.random.default_rng`, `random.Random`); any call of their controllers for prediction (the hop predictor, the `localizes` prediction of SC5) saves and restores both global streams (U-3). Our belief object is `SlamBelief`-shaped: its `particles` are our estimator's particles. Their controllers read from it: the mean robot pose (move_pick, move_to, move_look, move_place: E:1077-1080, 1093-1096, 1111-1114, 1129-1132), `particles[0].targets` and `particles[0].regions` for goal poses (E:1082, 1098, 1116, 1134), and in move_corner every particle (E:1156-1212).

Arm T runs their own driver as for find_dice: `tools/run_tampura_timed.py` is their run_planner.py plus one import of the timing wrapper (tools/run_tampura_timed.py:1-6, 107-145), and the task comes from the config, so `--config=./env_configs/slam_collect.yml` needs no change (the wrapper, tampura_bridge/timed_policy.py:26-48, and its G13 check, tampura_bridge/g13_runtime.py:148-163, contain nothing find_dice specific; that they run unchanged on slam_collect is UNVERIFIED until check C0).

### 3.2 What our arm must not read

- `env.state` after t = 0 (the executing state: the true pose, the true attachments, the true collision flag). The true values reach our arm only through the observation fields above.
- Any TAMPURA belief: arm O has no TAMPURA agent. The scoring replica (3.3) is evaluation only and is never passed to our agent or to the controllers.
- The random state, the RRT trees and the controllers' internals beyond the returned primitives.
What our arm may use (H1: what their observation function returns to an agent is allowed): every field of every `SlamObservation`, including `holding.robot_T_target` and `primitives`; the store; and the published model (the motion model and the region-overlap test, E:612-687), which Hani's "we use their dynamics" covers.

A slam variant of gate G2 (PAPER_AUDIT.txt:3314-3319) should enforce this by grep over our decision code: no `env.state`, no `SlamBelief` import outside the scorer and the world test, no `RolloutHistory`.

### 3.3 How a run is scored

Two criteria, both arms, the same code, evaluation only:

1. **Shared world-state test (primary, BF#35 at PAPER_AUDIT.txt:7366-7369 and BF#37 item 2 at :7518-7523).** On the final executing world only: every target overlaps the goal region (`collides_regions(target, goal)`, E:630-637) and `state.in_collision` is False (E:452, 887), read after the rollout from `RolloutHistory.states` (policy.py:59, 153), for both arms. For a return in the paper's sense, n is the arm's own stop step (its first no-op, from its action log), not a world read: return 0.98^n if the final world passes and the arm stopped, else 0. (Revised after REVIEW.md U-2: I had read the world after every step to find n, which is more than BF#37 allows. On the probe's logs the two definitions differ by at most 0.013 in mean return: `p2_summarize.py stopreturn`.)
2. **Their reward, reported beside it.** Arm T: its own belief's reward per step (policy.py:107-108, 136-138). Arm O: a scoring replica, an instance of their `SlamBelief` created the way `initialize()` creates one (E:1370-1371) and replayed after the episode through `b.update(action, observation, store)` on the logged actions and observations, exactly the update their rollout makes (policy.py:129-130), then `spec.get_reward(b.abstract(store), store)` per step. This is the find_dice pattern of feeding their belief what the arm did and letting their reward read it (tampura_bridge/scoring.py:1-17, 47-69). The replica is their belief's update on our primitives; it is not what their belief would have computed had it acted, because the primitives were planned from our mean (D-2), so its cloud ends offset from the controller's goal by the difference of the two means: about 4 to 5 cm per axis after a 16 to 30 primitive hop when both track the same posterior (the review's arithmetic, ESTIMATE), more where the estimators part (a failed pick, a re-seed). (Corrected after REVIEW.md 2.3: I had written that it equals what TAMPURA's belief would have computed.) Replayed after the episode, its draws cannot touch our arm's execution; their update draws from both global streams, np.random (E:131-133, 647-652) and Python's `random` (E:110), so the replay runs on its own saved and restored states of both (D-3).

Reported per arm and seed: world-state success, their-reward success, the discounted return 0.98^n (their reward: the first step with reward 1; world test: the stop step, as above), steps executed before the agent's first no-op, decision time per step (our estimator plus abstraction plus planner, against TAMPURA's `get_action` span from the timing wrapper), the time of their controllers (both arms), number of looks, true collisions, and replica in_collision events.

Both reads of their objects (the final world of criterion 1, the replica of criterion 2) happen in one declared scoring module after the episode, and nothing from it reaches the agent or the controllers. H1 lists success scoring among the uses ground-truth reads may not feed ("planning, perception, belief update, success scoring", PAPER_AUDIT.txt:3256-3259), so this is a named relaxation of H1's scoring clause, resting on BF#37 item 2 (one test on each arm's final executing world, :7518-7523), G2's allowance for the scoring adapter's readback (:3317-3318) and the find_dice precedent of feeding their belief what the arm did (D3 there). (Corrected after REVIEW.md 1.4: I had paraphrased H1 as forbidding only reads that feed a decision.) It is listed with the other relaxations in 3.7.

Their reward is a particle statistic, so the two criteria can disagree: the replica can call a placement good with the true target outside the goal, and a single replica particle in collision zeroes the reward while the true robot is free (their update ignores `observation.collision`, 2.4). The probe measures how often (3.5, 3.6).

Measured caveat (3.6). Through the replica, their reward credits our arm for agreeing with their filter rather than for the task. When our estimator uses observation fields their filter discards (4.6), our arm stops once its own belief and, as the world test confirms, the world say the task is done, and the replica, which never used those fields, can still say no or sit with a particle in an obstacle: the scripted rules closest to design (c) won the world test without ever winning their reward in 10 to 16 of 60 episodes (S1o 12, S4o 10, S1y 10, S4y 16), the rule that never looks in 15 of 60 (S0o). TAMPURA does not pay this, since it is scored on the belief it acts on. For the "their reward" column this means: our arm's number through the replica tends to understate what their reward credits (for S4o, 10 world wins never rewarded against 2 rewards without a world win), and TAMPURA's carries no such handicap; the self-graded number of 3.1 step 4 (their reward on our own belief's abstraction) sits on the other side, inflated by D-9. Both are reported, and neither is the primary result. This is the main reason for SC2 (a).

### 3.4 Deviations from their setup (aim: none)

| id | what differs | why it cannot be avoided, or what removing it costs | favours | how it could move the result |
|---|---|---|---|---|
| D-1 | Our arm reads the initial observation from `b0.particles[0]` at t = 0, once | `initialize()` builds the observation and hands it only to `SlamBelief` (E:1370-1371); the alternative is reading `env.state` at t = 0, which is equal and a world read | neither | none: the content is identical by construction (E:94-96) |
| D-2 | The belief object in `env.step` holds our estimate | `step` takes the acting agent's belief by design (T/environment.py:49-65); the controllers read its mean, particle 0's targets and regions, and all particles in move_corner | the more accurate estimator | path start points and pick goals differ between arms by the estimators' difference |
| D-3 | Only arm O has a scoring replica; it is replayed after the episode from the logged actions and observations, on saved and restored states of both global streams, np.random and Python's `random` (their update draws from both: E:131-133, 647-652 and E:110) | replaying after the episode means scoring cannot change our executed noise at all; isolating only np.random during the episode, as I first wrote, would not have been enough (corrected after REVIEW.md section 3) | neither in distribution | per-seed noise realisations differ between arms (TAMPURA's planner draws from the same global streams; U-3) |
| D-4 | TAMPURA re-run on our hardware (the chair's cloud, SC7) | the paper's runs used a Xeon Gold 6248 (survey line 44) | neither if both arms run on one machine | absolute times (one step took 174 s on the laptop against the paper's 129 +- 55 s, R1); quoted paper numbers stay separate |
| D-5 | E-MF taken to be `slam_collect_simple` | inference from Table III and the paper's wording (section 1). `slam_collect_1p.yml` differs from slam_collect.yml only in its task name (line 1) and no package registers that name (`probe/read_1p.sh`, read after REVIEW.md O9), so it cannot run and does not bear on the choice; what Table III's "abstract beliefs visited" counts is UNVERIFIED | neither | if wrong, the E-MF check runs on another map; running `slam_collect_custom` too costs about 15 minutes of TAMPURA runs (ESTIMATE) |
| D-6 | Primary success test on the world state | BF#35 and BF#37 require one test on each arm's final executing world; the paper scores the belief | neither by construction; per arm it depends on how often belief and world disagree | reported beside their reward, so no number is lost |
| D-7 | (only if SC5 = exclude) our domain has no move_corner | the action essentially never localises (2.2) | TAMPURA, marginally (one more option) | negligible if MEASURED rates hold |
| D-8 | Arm O runs their environment in arm O's venv (`/root/armO-venvA`, where our planner lives), arm T in theirs | as for find_dice; MEASURED (`probe/venvs.sh`): numpy 1.24.4, matplotlib 3.10.9, imageio 2.37.3 and scipy 1.15.3 in both | neither | none expected; check C0 compares the seed maps with `probe/out/maps.json` |
| D-9 | Our `in_collision` literal is the observation's collision flag, theirs is "any of 20 particles collided" (E:276-277); their spec's "not in_collision" preconditions (2.2) therefore block our arm only after a true collision | the action set and the preconditions are the same; the literal is part of the world model, which is ours by your brief. Removing it means adopting their particle definition, under which our arm would be blocked by its own particle-only collisions as the rules of 3.5 were (decision SC11) | ours | under the world-state test, up to the gap between S4 and S4o (42 and 52 of 60 wins, 3.6, together with the failed-pick use); under their reward, none measured (0.58 and 0.60) |

Disclosures the review found missing (REVIEW.md section 3), with what I changed:

| id | what | change or cost |
|---|---|---|
| U-1 | Arm O ran in a loop of ours that mirrors their rollout | removed: arm O runs inside `Policy.rollout` with our Belief and Policy subclasses (3.1); C1 then compares like with like |
| U-2 | The world test was read after every step to find the return's n | removed: final world only, n from the arm's own stop step (3.3); mean returns move by at most 0.013 on the probe's logs |
| U-3 | The global random streams that drive their execution noise are consumed by our agent's code between steps | our estimator and predictors use their own generators; controller calls made for prediction save and restore both global streams (3.1). Execution noise still differs between arms, since TAMPURA's sampling draws from the same streams (D-3) |
| U-4 | Their `tampura_environments/__init__.py` carries BF#3's declared import fix (PAPER_AUDIT.txt:5505-5511, sha256 9a64bea0...7b8ec4), "the only change to their trees" | disclosed here as for find_dice; imports only, both arms; no effect on slam_collect's code |

Not deviations, recorded for completeness: our estimator, abstraction, domain, preconditions and planner are ours (that is the comparison); their `step` checks no precondition (T/environment.py:49-67), so each arm checks their spec's preconditions on its own belief (TAMPURA: tampura_policy.py:161-168; ours: check C4), and our arm can therefore move when the replica holds a particle-only collision (3.6); both arms play no-op once their own belief says the goal holds; vis is off for both (C line 3); max_steps 20 and gamma 0.98 for both; arm T's timing wrapper only times `get_action` (timed_policy.py:37-45).

### 3.5 What scripted policies score in their environment (MEASURED)

To learn what plan structure this task rewards, before anything of ours exists, I ran fixed action rules (scripted, not planned; H2 forbids such rules in our arm, this is a measurement of the task) through their `env.step`, with their `SlamBelief` as the estimator and their reward, 20 seeds x 3 noise repetitions each (`probe/p1_measure.py`, mode `policies`; logs in `probe/out/policies_<rule>.json`; summary by `probe/p2_summarize.py policies`). Every rule commits to the nearest target not yet in the goal, carries it to the goal, and before a commit may look at a beacon. Actions their spec marks inapplicable on their belief (2.2) are replaced by no-op, as their planner would never choose them. Return = 0.98^n at the first step n whose belief reward is 1.

| rule | when it looks | which beacon | success (their reward) | mean return +- se | world success | steps to success (median) | in_collision episodes (true / particle only) |
|---|---|---|---|---|---|---|---|
| S0 | never | | 24/60 (0.40) | 0.34 +- 0.05 | 18/60 | 7 | 27 (5 / 22) |
| S1 | before every commit | min distance via the beacon | 43/60 (0.72) | 0.56 +- 0.05 | 45/60 | 12 | 16 (5 / 11) |
| S2 | when known_pose is false | as S1 | 37/60 (0.62) | 0.52 +- 0.05 | 31/60 | 8 | 21 (5 / 16) |
| S3 | when the predicted end variance of the commit is >= 0.05 | as S1 | 43/60 (0.72) | 0.58 +- 0.05 | 40/60 | 10 | 17 (3 / 14) |
| S4 | as S3, or when the predicted 2-sigma spread at the destination reaches an obstacle | nearest to the destination | 43/60 (0.72) | 0.58 +- 0.05 | 42/60 | 10 | 17 (2 / 15) |
| S5 | as S2 | nearest to the destination | 36/60 (0.60) | 0.51 +- 0.05 | 30/60 | 8 | 22 (4 / 18) |
| S2, held-out seeds 100 to 119 (x 2) | as S2 | as S1 | 28/40 (0.70) | 0.58 +- 0.06 | 23/40 | 8.5 | 12 (1 / 11) |
| S4, held-out seeds 100 to 119 (x 2) | as S4 | as S4 | 31/40 (0.78) | 0.63 +- 0.05 | 32/40 | 10 | 8 (1 / 7) |
| S5, held-out seeds 100 to 119 (x 2) | as S2 | as S4 | 27/40 (0.68) | 0.56 +- 0.06 | 22/40 | 8 | 13 (1 / 12) |
| TAMPURA (PAPER, not re-run) | learned | learned | at most about 98 % implied (95 to 97 %, 2.7) | 0.81 +- 0.02 | not reported | 9.22 (mean) | not reported |

The rules that look land at 0.51 to 0.58 on seeds 0 to 19 and 0.56 to 0.63 on the held-out seeds, at the top of the band of the paper's determinised baselines on E-M (MLO 0.41, WAO 0.56) and well below TAMPURA's published 0.81. The predictive and risk-aware rules (S3, S4) beat the reactive ones (S2, S5) by about 0.06 on seeds 0 to 19 and S4 beats S2 by 0.04 on the held-out seeds, each within about one standard error, so under their reward the probe does not separate the gate structures firmly (under the world-state test it does, 3.6). Seeds 5, 6 and 10 never succeeded under any rule (0 of 18 episodes each); on the held-out set seeds 102, 106 and 112 play the same part (0 of 6 under S2, S4 and S5). The rules never try to clear an in_collision atom through a pick whose observation filters the colliding particles out; TAMPURA's search could find that route.

Three findings about their task that any design must face:
1. **Their belief ignores a failed pick.** When a pick ends with nothing held, their update keeps every region-consistent particle, including those whose robot overlaps the target (E:194-198). A drifted robot whose mean sits on the target then re-issues picks whose RRT path is 1 primitive long and never moves again (S0, seed 1 rep 0: fourteen picks of 1 primitive in a row, true error about 1 m; `p5_detail.py S0_none 1 0`; corrected from "twelve" after REVIEW.md 2.3). Our own estimator can use that observation: a pick that returned nothing says the robot did not overlap the target, so those particles go. This is the clearest case of "how we use their perception is our business".
2. **One particle in collision ends the episode under their reward.** `in_collision` holds when any of 20 particles is in collision (E:276-277); then their spec allows only move_pick (and only with empty hands) and no-op (2.2), and the reward needs `not in_collision` (E:1533). The atom clears only if a later observation filters the colliding particles out. In S0, 22 of the 27 episodes that got the atom got it from particles only, the true robot being free (S1: 11 of 16). Their update never reads the observation's true collision flag (2.4).
3. **Some maps are tight.** The goal of seed 6 lies 0.45 m from an obstacle (centre to rectangle), target 2 of seed 5 0.31 m and target 1 of seed 10 0.38 m, against a robot circumradius of 0.335 m (`p2_summarize.py clear`). Every commit ends with the robot at the centre of its target or of the goal (the RRT's goal pose, E:773-776, 1082, 1134), so on these maps even a short hop from the nearest beacon leaves some of 20 particles in the obstacle: in S4, seed 6's first place after a look and a 15-primitive hop gave in_collision with the true robot free (`p5_detail.py S4_risk 6 0`), and seed 8 rep 1 put all three targets in the goal, true robot free, and lost the reward to one particle on the last place.

Belief and world disagree in both directions (S0: 8 episodes belief only, 2 world only; S1: 2 and 4; S4: 3 and 2), so reporting both criteria (3.3) matters.

### 3.6 The same rules with a sketch of design (c)'s estimator, scored through a replica (MEASURED)

3.5 used their belief both to act and to score. Design (c) acts on an estimator of ours and is scored through a replica (3.3), so I ran the rules again in that arrangement. The acting belief is a sketch, not design (c)'s estimator: their SlamBelief code with 20 particles plus some of the uses of 4.6 (rows o and x); the rows y, added after the review (REVIEW.md O6), use 100 particles and all four uses, which is design (c)'s form (`probe/p6_two_beliefs.py`; logs `probe/out/twobelief_<rule>.json`; summaries `p2_summarize.py twobelief` and `twofail`; step logs `p7_twodetail.py`). Rules ending in o use the uses (i) and (ii) of 4.6, rules ending in x all four, both with 20 particles; the controllers get the acting belief (D-2); an unchanged SlamBelief, updated with the same actions and observations, its draws from both global streams saved and restored, gives their reward; the probe's evaluator reads `env.state` after each step for the world-state test only (the design reads only the final world, 3.3), and the rule reads only the acting belief and the initial map (D-1). Same seeds and noise seeds as 3.5, so for rows o and x only the estimator differs from 3.5. World return = 0.98^n for the first step n from which the world test holds to the end (the stop-step definition of 3.3 gives the same to within 0.013). The review reran S4o and S2o from copies and found all 120 episodes identical step for step (REVIEW.md 2.1), and recounted every row (2.2).

| rule | estimator uses (4.6) | their reward through the replica: success, return +- se | world-state test: success, return +- se | steps to world success (median) | true collisions | world only / replica only |
|---|---|---|---|---|---|---|
| S0o (never looks) | (i), (ii) | 16/60, 0.23 +- 0.05 | 26/60, 0.38 +- 0.06 | 6 | 6 | 15 / 2 |
| S1o (looks before every commit) | (i), (ii) | 43/60, 0.56 +- 0.05 | 53/60, 0.69 +- 0.03 | 12 | 5 | 12 / 2 |
| S2o (looks when the pose is unknown) | (i), (ii) | 37/60, 0.52 +- 0.05 | 40/60, 0.57 +- 0.05 | 8 | 6 | 9 / 6 |
| S2x | (i) to (iv) | 40/60, 0.56 +- 0.05 | 42/60, 0.59 +- 0.05 | 8 | 6 | 10 / 8 |
| S4o (predicts the end, keeps clear) | (i), (ii) | 44/60, 0.60 +- 0.05 | 52/60, 0.70 +- 0.04 | 10 | 5 | 10 / 2 |
| S4x | (i) to (iv) | 44/60, 0.60 +- 0.05 | 52/60, 0.70 +- 0.04 | 10 | 5 | 10 / 2 |
| S2o, held-out seeds 100 to 119 (x 2) | (i), (ii) | 28/40, 0.59 +- 0.06 | 31/40, 0.65 +- 0.06 | 8 | 2 | 9 / 6 |
| S2x, held-out (x 2) | (i) to (iv) | 26/40, 0.55 +- 0.06 | 31/40, 0.65 +- 0.06 | 8 | 2 | 9 / 3 |
| S4o, held-out (x 2) | (i), (ii) | 30/40, 0.61 +- 0.06 | 37/40, 0.75 +- 0.03 | 10 | 2 | 8 / 1 |
| S4x, held-out (x 2) | (i) to (iv) | 31/40, 0.63 +- 0.05 | 37/40, 0.75 +- 0.03 | 10 | 2 | 7 / 1 |
| S1y (after the review; 100 particles) | (i) to (iv) | 46/60, 0.60 +- 0.04 | 55/60, 0.71 +- 0.03 | 12 | 1 | 10 / 1 |
| S4y (after the review; 100 particles) | (i) to (iv) | 40/60, 0.54 +- 0.05 | 56/60, 0.75 +- 0.03 | 11 | 4 | 16 / 0 |

"World only / replica only" counts episodes in which the world test held at some step but the replica never gave the reward, and the reverse. Median seconds per episode 4 to 8 for rows o and x and 39 to 46 for rows y (MEASURED, laptop, four runs in parallel; the y rows ran while another session's TAMPURA run held the machine, and their 100 particles are deep copies of `SlamState`, so they bound from above what a vectorised estimator would take).

What this adds to 3.5:
1. **The estimator does not move their reward.** Through the replica the rules score what they scored on their own belief (S2o 0.52 and S4o 0.60 against S2 0.52 and S4 0.58; held-out 0.59 and 0.61 against 0.58 and 0.63). The replica's own particles still end in obstacles (S4o: 14 of 60 episodes end with the replica in in_collision, at most 5 of them true), and the replica, which discards the failed-pick information, often disagrees with an acting belief that keeps it ("world only": S0o 15 of 60, S4o 10 of 60). This is the measured caveat of 3.3.
2. **It moves the world-state test**: S4 42/60 to S4o 52/60, S1 45 to S1o 53, S2 31 to S2o 40 (held-out S4 32/40 to S4o 37/40). Under S4 with their belief, 15 episodes had been blocked by particle-only collisions (3.5); with use (ii) such a collision no longer blocks the agent, and use (i) cuts the stuck re-picking short whenever some particle did not overlap the target. The probe does not separate the two. Seeds 5, 6 and 10, never won under their reward, are won in the world in 2, 1 and 2 of 3 episodes under S4o. Uses (iii) and (iv) help the reactive rule a little (S2x 42 against S2o 40) and change nothing for S4 (S4x equals S4o); the predictive look avoids the situations they repair.
3. **What matters under the world test is predicting the end of a commit; the clearance clause does not matter, and looking before every commit does as well.** (Rewritten after REVIEW.md 2.3 and 2.4.)
   - S4o against S2o, paired by seed and repetition, world test at the end: 16 episodes won by S4o only and 4 by S2o only on seeds 0 to 19 (exact McNemar p = 0.012), 8 and 2 on the held-out seeds (p = 0.11); repetitions of one seed are not independent, so both p values flatter the evidence (REVIEW.md 2.4). S2o's extra losses are mostly false stops: a place that starts with the pose known and ends spread (37 and 40 primitives, end variance 0.10 and 0.12 m^2 in `p7_twodetail.py S2o 13 0` and `S2o 19 2`), after which the 80 % literal says the target is in the goal and the world says it is not. Such false stops (the agent's own goal belief held, the world test did not) are 10 of S2o's 20 world failures against 2 of S4o's 8, and 6 of 9 against 0 of 3 on the held-out seeds; S2x keeps 10 of its 18. That gain is odometry, the predicted variance at the end of a hop, not reasoning about space.
   - S4n, the review's run of S4o with its clearance clause removed and nothing else (`../review_probe/run_s4n.sh`, `s4n_compare.txt`): the same actions in 83 of 100 paired episodes; world at the end 52 against 52 on seeds 0 to 19 and 37 against 36 held out (p = 1.0); return differences +0.017 to +0.018 with standard errors of 0.02 to 0.05. The clearance clause, the one ingredient that looked at free-space geometry, has no measured effect.
   - S4o against S1o (look before every commit), paired, seeds 0 to 19 (`s1o_compare.txt`): world at the end 4 episodes S4o only and 5 S1o only (p = 1.0); return difference S4o minus S1o +0.038 +- 0.040 under their reward and +0.017 +- 0.040 under the world test. S4o saves about 2.5 looks per episode (285 against 433 in 60) but is not measurably better. I had written that S1o's return is lower; the difference is within one standard error.
4. **Our acting belief and the world agree when the agent stops**: under S4x the agent stopped on its own goal belief in 54 of 60 episodes and the world test held in 52 of them; the other 6 never stopped (5 of them after a true collision).
5. **With design (c)'s form of the estimator (100 particles, all four uses; rows S1y and S4y, run after REVIEW.md O6 asked for it; `p2_summarize.py tworow`)**: their reward through the replica still does not rise (0.60 and 0.54, inside the band of every other row), and the replica's disagreement grows as our estimator moves away from their 20-particle filter (world wins never rewarded: 10 and 16 of 60). The world test rises a little further: 55 and 56 of 60, returns 0.71 and 0.75, with 2 and 0 false stops. S4y against S1y is again within about one standard error. So the review's doubt is settled in the direction it expected: a better estimator helps the world test and not the replica.

So the best scripted structures reach 0.69 to 0.75 under the shared world-state test (0.75 held out) and 0.54 to 0.60 under their reward (0.61 to 0.63 held out), against TAMPURA's published 0.81 under its own belief's reward. The criteria differ; only arm T's re-run gives TAMPURA's world-state number. Under the paper's criterion the probe predicts parity with WAO (0.56), not with TAMPURA (section 1, O1).

**Does TAMPURA reach 0.81 on this code? UNVERIFIED, and doubtful on these maps.** If seeds 5, 6 and 10 are lost to particle collisions for TAMPURA too, its success is at most 17 of 20, and its mean return at most 0.85 x 0.98^6 = 0.75 even with no look at all (6 commits), about 0.85 x 0.98^9.22 = 0.70 at its published step count (my arithmetic, if Table I's N = 20 are seeds 0 to 19, which the paper does not say; survey line 38). Their source also carries `# ACTION_STD = 0.01 # Standard` beside the active 0.04 (E:50-52); at 0.01 the pose would stay known for about 500 primitives (0.05 / 0.0001), which would make the paper's 9.22 steps for 6 commits hard to explain, so 0.04 is probably the paper's setting, but the code version behind Table I is not known. Either way the comparison needs TAMPURA re-run on this code (D-4), and a pilot of arm T on a few seeds, tight ones included, is the cheapest way to learn what the bar is (decision SC1, section 11).

### 3.7 Relaxations of binding records, named (added after REVIEW.md section 3 and O4)

None of these lets a ground-truth read feed a decision of the arm or edits a plan; each changes what may be claimed, and each is yours to accept or refuse (decision SC12 in section 13).

| record | what this design does | cost to the claims | proposal |
|---|---|---|---|
| H1's success-scoring clause (PAPER_AUDIT.txt:3256-3259: no ground-truth reads feeding "planning, perception, belief update, success scoring") | the world test reads the final executing world; the replica runs their belief code on the logged history | none to decisions; the claim must say scoring reads the final world, as in find_dice | rest it on BF#37 item 2 (:7518-7523), G2's scoring allowance (:3317-3318) and the find_dice D3 precedent (3.3) |
| H2, "no domain swap outside a declared and generated delta" (:3261-3262) | the slam domain is new, not a delta of M8 | the system under test is "the POD modelling pattern and the planner", not M8's domain; the paper must say so (9, 3.4.1) | accept with that wording |
| H2, "no planner swap" (:3260-3261) | the search stays 'ff-astar2'; 'dijkstra' only as a fallback | none unless the fallback is used | the fallback is asked separately (SC4 (e)) |
| H3, "small ... own audit entry with BEFORE / AFTER / CLAIM EFFECT" (:3265-3269) | the whole model is new, so not "small" | as H2; it needs its own BF# entry | accept as a separate arm with its own entry |
| H4, "no decision rule fitted to the released layouts" (:3271-3272) | the gate structure and estimator uses (iii) and (iv) were chosen after reading failures on seeds 0 to 19 (p5 S4_risk 6 0, p7 S2o 2 2 and 4 2); C7 freezes constants only | the paper must say the model was developed with the evaluation seeds in view; the held-out support for the predictive structure is p = 0.11 (3.6) | freeze the structure now (this document), and run our arm also on a fresh seed set never looked at (200 to 219), cheap for our arm; TAMPURA stays on 0 to 19 |
| BF#37 (:7509, :7525): B9 parked, arm O kept physical | arm O on this task runs on their execute layer, the B9 pattern, because the task has no physical arm | a slam result says nothing about the physical pipeline; it is a separate arm, not the find_dice arm O | name it a separate arm in any table |
| BF#37 item 2 (:7518-7523): the final world only | I had read the world after every step for the return | removed (3.3, U-2) | none needed |
| BF#66's "CLAIM EFFECT: none for this paper" (:9350) | the refinement's levels would be a value cut in the BF#66 sense | none if the refinement is not built, or if the levels are presented as a model detail | keep BF#66 out of the paper unless you decide otherwise |
| #P5, "consider adopting TAMPURA's controllers" (:9418) | arm O executes through their controllers on this task | on this task it is not a choice (they are the task's only actuators), so it says nothing for #P5 | mention, no claim |
| U-1 to U-4 (3.4) | arm O inside their rollout; final-world scoring; random streams; BF#3's import fix | U-1 and U-2 removed; U-3 fixed for reproducibility; U-4 disclosed | as in 3.4 |

---

## 4. Our world model from their observations

### 4.1 What a "dot" is

Their own frames (`plot_trajectories`, E:938-1060, written when vis is on) draw, for every primitive step, the robot of every particle as a small purple triangle (E:1045-1056), beacons as blue dots of radius 0.2 m with a faint vision circle (E:1020-1043), the goal as a green dot (E:953-959). I rendered two actions at seed 0 with their code (`probe/out/vis_seed0/frames/`, 51 frames): during a move the robot is a tight cluster of 20 triangles that spreads as it goes (frame_010.png) and arrives as a visible cloud (frame_050.png, after the place). The beacon and goal dots never change; what is new after every move is the robot's new position, drawn as that cloud. So I take Hani's "dot" to be **the pose the robot reaches after a move**, with the known-if fluent asking "do we know whether the robot is there". Two other readings give larger counts and are carried along in the table: one dot per particle per move (the 20 triangles), and one dot per primitive step (one frame each). A grid cell is the fourth reading, the one that makes "too many fluents" literal.

### 4.2 The parameters the counts use (READ, MEASURED)

- Named places: 11 regions (5 beacon squares, 4 corners, goal, start) plus 3 target squares = 14 (MEASURED at every seed).
- At most 20 actions per episode (C line 6); TAMPURA uses 9.22 (PAPER).
- Primitives per move (MEASURED, `probe/out/ctrl.json`, 20 seeds): move_pick from the start median 30 (4 to 57), move_place from a target to the goal median 32 (4 to 45), move_look from the start median 33 (10 to 54, no RRT failure in 100 calls), move_to the goal from the start median 41 (35 to 55); primitives are a median 1.065 times the Chebyshev distance over 0.2 m (up to 2.15 with detours).
- Pose spread after k primitives from a fix (MEASURED, `probe/out/variance.json`, 400 runs of 20 particles with their motion model): P(known_pose) is at least 0.99 for k <= 15, 0.91 to 0.95 at k = 20, 0.70 at 25, 0.43 to 0.46 at 30, 0.20 to 0.23 at 35, 0.10 at 40. So one typical move from a fix keeps the pose known about half the time, and two moves almost never.

### 4.3 Design (a): Hani's, a known-if fluent per new dot

Estimator: needed anyway (a particle filter of ours, 4.6); a dot is the estimator's mean after each move.
Fluents: (robot_at d) and (robot_at_KIF d) per dot, plus static facts per dot (which of the 14 places it overlaps, whether it collides).

| reading of "dot" | dots after k steps | fluents after k = 20 | static facts after k = 20 |
|---|---|---|---|
| pose reached by an action | k | 40 | about 300 (14 place relations and 1 collision fact per dot) |
| one per particle per move (20 particles, E:1216) | 20 k | 800 | about 6,000 |
| one per primitive (their frames) | about 18 k (MEASURED: mean 18.1 primitives per executed move in the scripted episodes, n = 3,294; the 31 I first used is the median of moves from the start or a target) | about 720 | about 5,400 |
| grid cell (no growth in k) | 2,500 at 0.2 m (STEP_SIZE), 40,000 at 0.05 m, 62,500 at 0.04 m (ACTION_STD) | 5,000 to 125,000 | 14 per cell |

What the planner grounds: every action of theirs takes a target or a named region as its argument (2.2), so a dot can never be the destination of an action; the planner cannot name a future dot before the move that creates it, unless poses are sampled in advance (a pose stream, as configurations are in our domain, pddl/domain_pddlstream_m8.pddl:50, 61-63). A dot's known-if fluent becomes true only through an exact pose, which only a look or a corner move gives, and then `pose_known` already says it.
Planning-time risk: low at the "pose reached" reading (FD handles hundreds of facts; ESTIMATE), high with a pose stream (our pipeline's adaptive PDDLStream search over sampled values has taken from seconds to a 900 s cap, pddlstream_planner.py:1162-1166) or a fine grid.

### 4.4 Design (b): region boxels with free space split around the obstacles

Regions: the 14 named places, the obstacle footprints, and the free space split into boxes around them (today's merge rule: same label and an exactly aligned shared face, cell_merger.py:125-166 per PROPOSAL_ATTRIBUTE_BOXELS.md section 1). The pose belief is "which region is the robot in, known or not": for each region r, (robot_in r) and (robot_in_KIF r), true when at least 80 % of our estimator's mass puts the robot rectangle over r or off r (their REGION_IN_THRESH), unknown otherwise. Regions split where the pose mass straddles a boundary that matters, and merge back when no fact distinguishes them.

MEASURED (`probe/out/boxes.json`, `probe/out/maps.json`, seeds 0 to 19), two ways of drawing the regions:
- Axis-aligned boxes. Every rotated rectangle replaced by its bounding box (obstacles grown by the robot's circumradius 0.335 m, named places grown by its inscribed half extent 0.15 m), the plane cut along every box edge (840 to 1,056 arrangement cells), cells of equal signature merged greedily into maximal rectangles: 68 to 95 boxes per seed (median 77; I had written 76), of which 60 to 83 are free boxes (no obstacle) and 30 to 41 are plain free space (no obstacle, no place).
- Exact shapes on a 3.9 cm grid: 22 to 33 distinct signatures (which places the robot certainly overlaps, which obstacles it may touch), 23 to 37 connected regions of equal signature.

Fluents: robot_in and its known-if per region the robot can be in, plus pose_known (1), holding (3), target_in over 3 targets and 14 places (42) and in_collision (1), 47 in all: with the free boxes (60 to 83) that is 167 to 213; with the signature regions (23 to 37) 93 to 121. Constant in the number of steps.
What the planner grounds: their five moves over the 14 places as now, plus robot_in facts over the free boxes; the free boxes are never action arguments (2.2), so they only enter through facts.
Planning-time risk: low (no streams; FD on a few hundred facts; ESTIMATE).

### 4.5 Design (c), revised after the review: named places and a one-literal gate

BF#66's rule (PROPOSAL_ATTRIBUTE_BOXELS.md section 0: "a boxel is a maximal region over which the planner's predicates are constant") applied to this task. No action of theirs can take a free-space destination, and no predicate the planner reads tells two free-space points apart, so all free space merges into one class that the planner never names. Said plainly (REVIEW.md O2): what remains is their vocabulary, eleven named regions and three targets; the rule has nothing to merge except free space, and design (c) uses no boxels in any other sense. What remains:
- **Places**: the 14 named places, plus one place `here` for the current estimate at each replan (15).
- **The robot's location**: `(robot_at ?p)`, the place the last action sent it to, re-derived after every observation from our estimator (the place whose zone holds at least 80 % of our mass, else `here`).
- **The gate, recommended form (SC4 (c))**: one literal `(looked)`, "a look since the last commit", set by move_look (and by a localizing move_corner, SC5) and deleted by every other move (move_pick, move_place, move_to); every commit requires it. In the init it comes from the agent's own action log, not from the estimator, because a `pose_known` re-derived after a short commit would undo the deletion (REVIEW.md section 6). This is the structure of the rule S1, which ties the predictive rule within one standard error under both criteria (3.6 point 3) with no levels.
- **The end of the goal place (the O3 fix)**: `move_place` also requires the static `(EndKnown ?from ?r)`, true when the hop from ?from to ?r is predicted to end with an expected variance below their KNOWN_VAR_THRESH (0.0016 m^2 per primitive from ACTION_STD, E:50, 53; at least the Chebyshev distance over 0.2 m primitives, E:733-734; the geometric factor 1.0 under H4). A place predicted to end with the pose unknown is then inapplicable and cannot reach the goal in the model, whichever plan the search returns first (section 5).
- **The refinement, only if a go of section 11 needs fewer steps**: S1's six looks give 12 steps, which caps the return at 0.98^12 = 0.785, below TAMPURA's published 0.81 (R3), so a result against a TAMPURA near 0.81 would need the predictive gate. Its form: drift levels cut at the precondition flips, not at round numbers (PROPOSAL:235-237, which I first broke with cuts every 0.01 m^2): the cuts are the values 0.05 - 0.0016 k(p, q) of the start variance at which a hop from p to q would end at their KNOWN_VAR_THRESH, over the hops of the map, plus 0 after a look (map specific, computed once from the hop predictor; ESTIMATE 6 to 10 levels after equal cuts merge). The hop predictor uses the variance 0.0016 m^2 per primitive (READ) and at least distance / 0.2 m primitives (E:733-734); the measured factor of 1.065 comes from seeds 0 to 19, so H4 allows only the geometric 1.0 or a factor calibrated on seeds 100 to 119. There the end condition of the goal place becomes a conditional effect on the static table: `move_place` asserts `(target_in ?t ?r)` only when the predicted end level is below the threshold (section 5).
- **Targets**: `(target_at ?t ?p)` and the known-if goal literal `(target_in ?t ?goal)` at our 80 % mass; the threshold is ours to choose (REVIEW.md O9) and stays at their 0.8 so that our goal literal means what their reward means, with 0.95 as an ablation.
- **Collision**: `(in_collision)` from the observation's own flag (E:909), which their belief ignores (2.4; D-9, SC11).
- **Dropped: the `tight` facts.** They were the one ingredient that used the geometry of free space (where a predicted 2-sigma spread meets an obstacle). The review's S4n run removed the clause and nothing else: same actions in 83 of 100 paired episodes, 52 against 52 and 37 against 36 world wins (p = 1.0; 3.6 point 3). They are dropped unless a map is found where they change an outcome.

Fluent counts, corrected after REVIEW.md 2.3 (I had written about 35 fluents and 705 ground actions, which undercounts under the grounding I described):
- Their region argument kept whole (a place may target any of the 11 regions): robot_at 15, looked 1, holding 3, handempty 1, target_at 36 (each target at its spot or in one of 11 regions), target_in 3 (goal only) or 33 (every region), in_collision 1: 60 or 90 fluents. Ground actions before pruning: move_pick 3 x 15 x 12 = 540, move_place 3 x 15 x 11 = 495, move_look 75, move_corner 60, move_to 30: 1,200.
- Place destinations restricted to the goal in our model (a grounding choice of ours: their action keeps its argument, and no goal needs a target placed elsewhere): 15 + 1 + 3 + 1 + 6 + 3 + 1 = 30 fluents; 90 + 45 + 75 + 60 + 30 = 300 ground actions. Recommended.
- With the refinement's levels in place of `(looked)`: plus about 5 to 9 fluents, ground actions times the number of levels.
Constant in the steps in every case. TAMPURA's own abstraction has 49 atoms (known_pose, 11 in, 33 target_in, 3 holding, in_collision; E:212-279), also constant, for the same reason: their observation names eleven regions.
Planning-time risk: lowest. No streams. The search stays 'ff-astar2' as in our pipeline (H2; section 5), with 'dijkstra' only as a fallback; the reachable state space is about 15 x 2 x 27, under a thousand states, with goal-only places, and about 66,000 with every region (ESTIMATE), so either search is fast; the PDDLStream translate overhead per call is the larger term (ESTIMATE about 1 s; path 2 measured 1.2 to 1.6 s per call for its small mode S domains, tracks/tasks/STATE.md:59-65; check C3).

### 4.6 What our estimator keeps (all designs)

A particle filter of ours on the published model: N particles (N = 100 declared before any run, ESTIMATE of what is cheap; their 20 is not binding on our world model), each the robot pose and the carried target's offset; propagate through `observation.primitives` with N(0, 0.04 m) per axis and heading from the noisy step (E:640-687, written anew, not imported); attach and detach as their primitives say (E:862-876); weight 1 or 0 by whether the particle's overlapped-region set equals `regions_in` and, when holding, whether it overlaps the held target (E:194-201); snap to `robot_pose` when it comes; resample; if no particle survives, re-seed by inflating the motion noise (their filter keeps the old set instead, E:207-208). The planner never sees particles: the abstraction of 4.5 reads the mass fractions and the variances.

Four uses of the observation that their filter does not make, all allowed (they read only fields their observation function returns). Uses (i) and (ii) together are measured to matter (3.6); (iii) and (iv) repair failure cases the probe showed, with a small measured effect on the reactive rule (S2x against S2o) and none on the predictive one (S4x equals S4o):
- (i) A pick that returns nothing held removes the particles whose robot overlapped the target at the last primitive (theirs keeps them, E:194-198, and gets stuck re-picking with 1-primitive paths).
- (ii) `in_collision` in our model is the observation's own collision flag (E:909), the truth as reported; their belief marks a collision only when one of its own particles collides (E:135-137, 276-277). The spread of our particles near obstacles is still tracked, because the replica scoring their reward has about the same spread (finding 2 of 3.5).
- (iii) `holding` is the observation's own field (the true attachment with its exact offset, E:905-907), set on every particle; their belief takes it from the particles, and when no particle fits an observation it keeps the unfitted set with the attachments its own re-simulation made (E:194-208: attachments are set only on fitting particles, and the set is replaced only if one fits). In the sketch of 3.6 without this piece, a failed pick left the belief "holding" a target the robot never held, and the rule then "placed" it and stopped (`p7_twodetail.py S2o 2 2`).
- (iv) When no particle fits the observation, re-seed around the old set with a growing spread and keep what fits; their filter keeps the unfitted set (E:207-208). With 20 particles their filter also collapses to copies of one survivor (variance 0 with the mean 1.3 m off the truth after a place, `p7_twodetail.py S2o 4 2`), which makes `known_pose` true when it is false; N = 100 and a small jitter at resampling address that.

On the fields both filters use, this is the Bayes filter of the published model and tracks the same posterior as theirs; that is intended (both arms see the same uncertainty) and is conceded in section 9. Uses (i) to (iv) condition on more of the same observation, which is where our estimator differs (D-9 for the collision flag). An alternative that is more distinctly ours, the pose belief kept as one box (grow by the motion noise, intersect with the observed region's overlap zone, subtract the zones of regions the robot is observed not to overlap, collapse on an exact pose; the slab cut of shadow_calculator.py:375 per PROPOSAL section 3.4), is decision SC3; I would run it only as an ablation, because its calibration is a new risk.

### 4.7 Does BF#66 bear on a pose belief?

Less than I first wrote. I had called this task "a cleaner test bed" for BF#66 than find_dice; I withdraw that (REVIEW.md 2.3). The robot's pose belief is a 2D density of the kind PROPOSAL_ATTRIBUTE_BOXELS.md section 3 boxelizes, but the recommended design does not boxelize it: the gate is one literal, and the refinement cuts only a scalar, the variance, at the flips of section 5 of the proposal; the `tight` facts, the one use of the region rule, are dropped (4.5). Only the box filter of SC3 (b) would test BF#66's application A here, and I do not recommend building it before 2026-12-04. BF#66 is parked as far future work (PAPER_AUDIT.txt:9346-9347) and its claim effect is "none for this paper" (:9350), so if the levels are ever built they are a model detail of this domain, not a BF#66 result, unless you decide otherwise (3.7).

### 4.8 Recommendation

Revised after the review. Design (c) in its recommended form: the 14 named places and `here`, the one-literal gate `(looked)` before every commit (SC4 (c)), place destinations restricted to the goal with the static end condition `(EndKnown ?from ?r)`, the search 'ff-astar2' as in our pipeline (section 5), and our particle filter underneath with the four uses of the observation of 4.6 (SC3 (a)). About 30 fluents at every step (60 to 90 with their region argument kept whole), against 40 to about 720 for a known-if fluent per dot after 20 steps and 49 atoms in TAMPURA's own abstraction. Its scripted analogue (S1o) ties the best structure the probe found within one standard error (3.6). The predictive refinement with drift levels at the flips is built only if a go needs fewer steps (4.5). What this design does not do is reason about space: the small count comes from their vocabulary, and the one spatial ingredient I had added had no measured effect (O2, section 12).

---

## 5. The domain

Generated per task like M8's (tools/gen_bridge_domain.py, m8_domain.py), untyped with type predicates as in our domain (pddl/domain_pddlstream_m8.pddl:22-28), action costs as in ours (:96). One action per action of theirs, same names, same argument kinds; the extra `?from` argument is the robot's place, which their controllers take from the belief instead. The first block is the recommended form after the review (SC4 (c)); the refinement with drift levels follows it. (I had recommended the levels with the end of a commit steered by cost; REVIEW.md O3 showed why that is unsafe under our planner configuration, and the answer is below.)

```pddl
(define (domain slam-collect-sb)
  (:requirements :strips :equality :negative-preconditions :conditional-effects :action-costs)
  (:predicates
    (Place ?p) (Region ?p) (Target ?t) (Beacon ?p) (Corner ?p) (Goal ?p) (Start ?p)
    (robot_at ?p)          ; where the last action sent the robot (from our estimator after each observation)
    (looked)               ; a look since the last commit (from the agent's own action log at each replan)
    (handempty) (holding ?t)
    (target_at ?t ?p)      ; the target's place: its spot or the goal (goal-only places, 4.5)
    (target_in ?t ?r)      ; K-literal: >= 0.8 of our mass has ?t overlapping ?r (their REGION_IN_THRESH)
    (in_collision)         ; the observation's collision flag (D-9)
    (localizes ?p)         ; static: a look or corner move at ?p is predicted to end inside ?p
    (EndKnown ?from ?to))  ; static: a hop from ?from to ?to is predicted to end with the pose known (O3)
  (:functions (total-cost) (hop ?from ?to))   ; predicted primitives of the controller's path,
                                              ; emitted for every pair of objects (11.5)

  (:action move_pick                ; theirs: E:1406-1418
    :parameters (?t ?from ?to)
    :precondition (and (Target ?t) (robot_at ?from) (target_at ?t ?to) (handempty)
                       (looked))                           ; our commit gate, a hard precondition
    :effect (and (holding ?t) (not (handempty)) (not (target_at ?t ?to)) (not (looked))
                 (robot_at ?to) (not (robot_at ?from))
                 (increase (total-cost) (hop ?from ?to))))

  (:action move_place               ; theirs: E:1419-1443; ?r restricted to the goal in our grounding
    :parameters (?t ?from ?r)
    :precondition (and (holding ?t) (robot_at ?from) (Goal ?r) (not (in_collision))
                       (looked) (EndKnown ?from ?r))       ; our commit gate and end condition
    :effect (and (not (holding ?t)) (handempty) (target_at ?t ?r) (target_in ?t ?r)  ; optimistic
                 (not (looked)) (robot_at ?r) (not (robot_at ?from))
                 (increase (total-cost) (hop ?from ?r))))

  (:action move_look                ; theirs: E:1465-1488; the sense action
    :parameters (?b ?from)
    :precondition (and (Beacon ?b) (robot_at ?from) (localizes ?b) (not (in_collision)))
    :effect (and (looked) (robot_at ?b) (not (robot_at ?from))                        ; optimistic
                 (increase (total-cost) (hop ?from ?b))))

  ;; move_corner (E:1489-1509): as move_look with (Corner ?c), setting (looked); (localizes ?c) only
  ;; where the controller's noise-free path is predicted to end in the corner (decision SC5).
  ;; move_to (E:1444-1464): (Region ?r), (not (Beacon ?r)), (not (Corner ?r)), (not (in_collision));
  ;; effect robot_at ?r and (not (looked)), so a commit always starts where the last look ended.
  ;; Their move_pick has no in_collision precondition (E:1411-1413); ours neither.
)
```

Goal (E-M, mirroring E:1525-1535): `(and (target_in t0 goal) (target_in t1 goal) (target_in t2 goal) (not (in_collision)))`. E-MF: `(and (robot_at goal) (not (in_collision)))` with robot_at re-derived as "in(goal) at 80 % mass".

Sensing and known-if, M8's pattern. A commit needs a fresh fix, as pick needs `(obj_pose_known ?o)` in M8 (pddl/domain_pddlstream_m8.pddl:254; POD justification at PAPER_AUDIT.txt:4467-4469: "a pick commits on a pose only within what the gripper tolerates; when the belief cannot guarantee it, the planner must plan the observation that can"). The sense action sets the literal optimistically, as `sense` assumes the target found (pddl/domain_pddlstream_m8.pddl:193-198). Their `depends=[known_pose]` becomes our precondition: a determinisation by a rule of the model, not by most likely outcome (section 9, objection 3.4.3).

Replanning. After every executed action: the estimator takes the observation, the abstraction rewrites the init (robot_at, looked from the agent's own action log, holding, target_at, target_in, in_collision, the hop costs from `here`), and the planner plans from scratch; the agent executes the first action. When the goal literals hold, the agent plays no-op, as TAMPURA does (tampura_policy.py:77-80). The plan is never edited between planner and executor (H2, PAPER_AUDIT.txt:3260-3264; your standing rule).

Motion and regions. The planner chooses only the action and its place; their RRT (E:694-791) plans the path from our mean to the place's pose. Our regions are the RRT's goals; the geometry of free space enters only the hop predictor (predicted primitives, hence cost). Their RRT checks collisions at the mean with zero noise, with no clearance (E:750-767), so a destination close to an obstacle can put spread particles (theirs or the replica's), and with a wide spread the true robot too, in collision. I had added `tight` facts against that; the review's S4n run shows they changed nothing measurable (3.6), so they are dropped (4.5).

**REVIEW.md O3, and the fix.** The review is right about the form I had recommended: under 'ff-astar2', our pipeline's default (pddlstream_planner.py:1130), the docstring I cited records that the domain's action costs "barely order the plans" and that every call returns the first plan found, not a cost-optimal one (:1157-1162, 1171-1173), and my `move_place` asserted `target_in` whatever its predicted end level. A place predicted to end with the pose unknown could therefore reach the goal in the model, and the agent would then stop on an 80 % literal: S2o's false stops, the failure the gate was meant to remove. My fix is inside the model, not the search:
1. In the recommended form the gate is a hard precondition, `(looked)`, on every commit, deleted by every move other than a look, so no gate rests on cost: every plan, whichever the search returns first, looks before each commit. And the goal place needs the static `(EndKnown ?from ?r)` (4.5), so a place predicted to end with the pose unknown is not applicable and cannot reach the goal in the model; since a commit starts where the last look ended, the condition says from which beacons a place may start. This is the structure of S1o (2 false stops in 60, 3.6), with the case of a look at a beacon too far from the goal closed by a precondition instead of left to the search. There is no penalty to size. Cost: about 2.5 more looks per episode than the predictive rule (433 against 285 in 60 episodes), about two more steps, a return difference of 0.04 +- 0.04 under their reward and 0.02 +- 0.04 under the world test (REVIEW.md 2.4): within one standard error. A map where no beacon lets the goal's place end known has no plan and its episodes are lost and counted. With the geometric factor 1.0, a place from a fresh look ends known when the goal lies within 0.05 / 0.0016 x 0.2 = 6.25 m (Chebyshev) of the beacon; on seeds 0 to 19 the goal's nearest beacon is at most 5.10 m away (MEASURED, 2.1), so no map of the evaluation set is affected, and C7 checks seeds 100 to 119 and 200 to 219 the same way before any run.
2. In the refinement the same condition, with the start level as a third argument, becomes a conditional effect on the static hop table: `(when (EndKnown ?from ?r ?l1) (target_in ?t ?r))`, true when the hop from ?from to ?r started at level ?l1 is predicted to end below their KNOWN_VAR_THRESH. Fast Downward evaluates a static condition at grounding, so the effect costs nothing in search. A place predicted to end unknown then cannot reach the goal in the model, whichever plan the search returns first; the start gate stays a precondition. Cost: as in point 1.
3. The search stays 'ff-astar2', because H2 asks for "PDDLStream + Fast Downward exactly as in the main pipeline: no planner swap" (PAPER_AUDIT.txt:3260-3261). Costs then only choose which beacon to look at, among those point 1 allows; C4 logs whether the planner's beacon is the one with the shortest detour. If it often is not, the fallback is the blind cost-optimal 'dijkstra' (pddlstream_planner.py:1170-1171), a call argument with no change to pddlstream_planner.py, put to you as a named relaxation of H2 (decision SC4); its cost is search time, small for this state space (4.5; ESTIMATE under a second, checked in C3).

```pddl
  ;; the refinement (only on a go that needs fewer steps, 4.5): levels are objects cut at the
  ;; precondition flips; static (hop_end ?from ?to ?l1 ?l2) and (EndKnown ?from ?to ?l1) come
  ;; from the hop predictor; (Known ?l) marks the levels below their threshold
  (:action move_place
    :parameters (?t ?from ?r ?l1 ?l2)
    :precondition (and (holding ?t) (robot_at ?from) (Goal ?r) (not (in_collision))
                       (drift ?l1) (Known ?l1) (hop_end ?from ?r ?l1 ?l2))
    :effect (and (not (holding ?t)) (handempty) (target_at ?t ?r)
                 (when (EndKnown ?from ?r ?l1) (target_in ?t ?r))           ; the O3 fix
                 (robot_at ?r) (not (robot_at ?from)) (not (drift ?l1)) (drift ?l2)
                 (increase (total-cost) (hop ?from ?r))))
  (:action move_look
    :parameters (?b ?from ?l1)
    :precondition (and (Beacon ?b) (robot_at ?from) (localizes ?b) (not (in_collision)) (drift ?l1))
    :effect (and (not (drift ?l1)) (drift L0) (robot_at ?b) (not (robot_at ?from))
                 (increase (total-cost) (hop ?from ?b))))
  ;; move_pick as move_place, with (handempty) and (target_at ?t ?to), without target_in;
  ;; move_to advances the level by hop_end
```

The probe compares the reactive, the predictive and the look-before-every-commit structures as scripted rules (3.5, 3.6, 9).

---

## 6. How we know it works

Checks before any comparison (each a pass or fail line in the BF# entry):

- C0. Arm T's driver and G13 check start on slam_collect unchanged (tools/run_tampura_timed.py with `--config ./env_configs/slam_collect.yml`, one step, then stop; no full episode). Their env imports in arm O's venv and draws the same map per seed as in arm T's (compared with `probe/out/maps.json`, D-8).
- C1. Harness identity (revised after REVIEW.md O9: as first written it could not give identical observations, because the controllers plan from whichever belief is passed to `step`). Arm O now runs inside their rollout (3.1), so C1 is: a scripted Policy subclass with their own `SlamBelief` as the belief reproduces the logs of 3.5 step for step on seeds 0 to 2 (the review's reproduction shows the probe is deterministic given its seeds, REVIEW.md 2.1), and the after-episode replica, given those logs, reproduces their belief's rewards exactly.
- C1b. Gates for the new arm O (REVIEW.md O5): G1 and G2 variants for the slam decision code (no `env.state`, no `SlamBelief` outside the scorer, no `RolloutHistory` in decisions), and a slam G13 for arm O, since g13_runtime.py:122-145 is find_dice specific.
- C2. Estimator. On recorded (action, observation) sequences of seeds 0 to 19: our estimator against their `SlamBelief` (distance of means, variance ratio, agreement of pose_known, in(r) and target_in), and against the true pose read from `env.state` by the evaluator only (calibration: the fraction of steps where the true pose lies inside our 80 % zone should be near 0.8), and the false-stop rate (our goal literals true, the world test false; 2 of 60 for the scripted S4x, 3.6). Each of the four uses of 4.6 is switchable, so its effect can be shown as in 3.6. Evaluation only; nothing feeds back.
- C3. Fluent and grounding counts per replan, logged: constant over the steps (the claim of section 4), plus the planner's wall time split into translate and search.
- C4. Plan validity: every executed action satisfies their schema's preconditions evaluated on our abstraction (the mirror in section 5) and on the replica's (diagnostic only, logged when they disagree). For every look it also logs whether the planner chose the beacon with the shortest detour among those `EndKnown` allows, the condition for the 'dijkstra' fallback (SC4 (e)).
- C5. Frames: seeds 0 to 2 rendered with their own `plot_trajectories` (vis on, our particles) for a visual check.
- C6. H2: the agent loop calls only estimator, abstraction and planner (a grep gate like G1 and G2: no hard-coded sequences, no decision on anything but the init facts).
- C7. H4: every constant of our model (N, the 80 % threshold of our literals, the hop factor, and for the refinement the level cuts) and the gate structure of SC4 are frozen before any run on seeds 0 to 19, from seeds 100 to 119 only, and written into the BF# entry. The model was developed with seeds 0 to 19 in view (3.7, H4), so our arm also runs on a fresh set, seeds 200 to 219, that nobody has looked at, and both numbers are reported. The scripted rules' hop factor 1.07 was measured on seeds 0 to 19 (`p2_summarize.py ratio`); our arm must not reuse it (4.5). C7 also checks statically, on every seed set, that each goal has a beacon from which a place ends known (`EndKnown`, 4.5 and 5, the O3 fix), for the recommended form and the refinement alike.

Comparison:
- Task E-M (`slam_collect`), seeds 0 to 19 (H4); E-MF (`slam_collect_simple`) as the harness check, seeds 0 to 19.
- Arms: T, their driver with the timing wrapper; O, ours. Repetitions: O 5 per seed (cheap; ESTIMATE about 20 to 30 s per episode: the scripted loop's 4 to 8 s with a vectorised estimator, where the 100-particle sketch built on `SlamState` copies took 39 to 46 s (3.6), plus one planner call per step at the 1.2 to 1.6 s path 2 measured in a smoke run, tracks/tasks/STATE.md:59-65), T 1 per seed (ESTIMATE 20 to 27 minutes per E-M episode, from the paper's 9.22 x 129 s and the 174 s step MEASURED in R1; about 40 s per E-MF episode).
- Ablations of arm O (cheap, about 10 minutes each, ESTIMATE), in the main table, not beside it (REVIEW.md O1): the collision literal of SC11 (b), and the four estimator uses of 4.6 switched off, so the estimator's share of any difference is reported apart from the planner's (3.6 found the estimator alone worth 8 to 10 of 60 world-state wins for scripted rules).
- Metrics: world-state success and their-reward success (Wilson intervals), discounted return 0.98^n under each criterion (Table I's measure), steps (Table III), decision time per step and controller time (Table II includes controller execution), looks, collisions. Paired by seed: McNemar on per-seed success for one T run against O's first repetition, as BF#63's two-arm harness does (tools/gen_scene_eval.py).
- Power (REVIEW.md O7). With one arm T run per seed there are 20 pairs; a paired success comparison of that size resolves only differences of about 0.3 or more in success rate (my arithmetic: an exact McNemar test at the 5 % level has about 40 % power at a difference of 0.3 when the arms' outcomes are independent across seeds, for example 0.9 against 0.6, and about 60 % when they are strongly dependent; the review's ESTIMATE is that differences much below 0.25 cannot be resolved), so only decision time will separate the arms unless arm T gets 2 or 3 runs per seed (7 to 18 more hours on the cluster, ESTIMATE). The paper may claim decision time and, under the world test, at most "no worse within the comparison's resolution".
- Where: comparison runs go to the chair's cloud (the i6 cluster), as every comparison run does under your rule, both arms on the same machine, and only after your explicit approval of that run asked as its own question; arms serial, never two at once on one machine (contention doubles planning time). The laptop is for development, short probes and the checks C0 to C7 only, each run under `flock /root/sb_pipeline.lock` as the track rules require (tracks/STATE.md rule 7).

---

## 7. Where it lives

Revised after REVIEW.md O8: the dev-track rules, which postdate my first draft, decide where this lives. Code goes on a track branch `track/<name>` in a sibling worktree `..\sb-<name>`, made with `pwsh tools/track_worktree.ps1 -Name <name>` from the stable tag `stable-2026-11-06` (d6a9715), and only the orchestrator merges into tampura-bridge (CLAUDE.md:27-38; tracks/STATE.md rule 4, lines 111-119); briefs, state and evidence go to `archive/tampura_bridge_plan_2026-10-25/tracks/<name>/` in the main checkout (rule 5); every pipeline or TAMPURA episode runs under `flock /root/sb_pipeline.lock` (rule 7). Path 2's brief already asks which TAMPURA tasks give a quick result above 0 and above random and tells it to cite this document (tracks/tasks/BRIEF.md:13-17, 27-32), so the natural home is path 2's track, or a track of its own if the orchestrator starts one; the name, for example `track/slam-collect`, is the orchestrator's choice. Nothing is created here.

New files only, all under a new package and named for the task:
- `slam_bridge/agent.py` (our Belief and Policy subclasses for their rollout, 3.1), `slam_bridge/estimator.py` (4.6), `slam_bridge/abstraction.py` (4.5), `slam_bridge/domain_gen.py` and the generated `pddl/domain_slam_collect.pddl` (5), `slam_bridge/scoring.py` (after-episode replica and final-world test, 3.3), `tools/run_slam_eval.py`, a slam sbatch under `tools/cluster/`, `slam_bridge/tests/`.
- The planner is called through PDDLStream's solve with Fast Downward's `ff-astar2`, our pipeline's default (pddlstream_planner.py:1130, 1154-1173), without changing pddlstream_planner.py; 'dijkstra' only as the fallback of section 5, if you allow it (SC4 (e)).

Shared code changes: none planned. If one becomes necessary (for example factoring the replan loop out of test_full_pipeline.py so both versions share it), its cost on our own tasks is measured before it merges: BF#13's distributional plan-count test on our scenes and a seed-for-seed A/B with the eval skill.

What could move back to the main line later: the per-step TAMPURA harness (class_uncertain's per-step bridge needs the same loop, survey line 116); the known-if replanning loop as a reusable interface.

---

## 8. Effort, order of work, minimal version, risks

All durations are ESTIMATES (working days of one session with Hani's reviews). Revised after REVIEW.md O5, which found my first table short by two to three days.

| step | work | estimate |
|---|---|---|
| 0 | Arm T pilot: their driver on seeds 0 to 2 and 5, 6, 10, on the chair's cloud after your approval of that run (up to about 4 h: an episode that never reaches its goal belief keeps planning for all 20 steps, up to 20 x 174 s = 58 min; REVIEW.md 2.3); C0 first, a slam sbatch, and a read-only reader of their pickled rollouts (11.2); decided by the rule of section 11, which is fixed before it runs | 0.5 day of work |
| 1 | Only on a go: track worktree, our Belief and Policy subclasses inside their rollout, after-episode scorer; C0, C1, C1b (G1, G2 and G13 variants) | 1.5 days |
| 2 | Estimator and C2 | 1 day |
| 3 | Abstraction (`looked` from the action log, hop costs for every pair of objects, the static `EndKnown`), domain generator, planner call; C3, C4, C6; the planned arm against the scripted S1y on seeds 100 to 119 (11.4 item 6). First arm O number on a few seeds after this step, about 3.5 to 4 days in, which is what path 2 calls quick | 1 day |
| 4 | C7: constants and structure frozen on seeds 100 to 119; BF# entry before any run on 0 to 19 | 0.5 day |
| 5 | Arm O on E-MF (harness check), then E-M on seeds 0 to 19 and 200 to 219, with the ablations of section 6; C5 frames; failure classes | 1 day |
| 6 | Arm T: E-M 20 seeds (6.6 to 9 h wall, R1, more if episodes fail), E-MF 20 seeds; the pilot's slam sbatch; on the chair's cloud, with your approval of that run | 0.75 day of work |
| 7 | Analysis, BF# entries, review cycle, a table and a paragraph | 1 to 1.5 days |
| | total | 6.75 to 7.25 days for steps 1 to 7 (the review's realistic range: 7 to 9), plus the pilot's half day and TAMPURA's wall time |

Minimal version: E-M only; design (c) with `(looked)` (SC4 (c)), goal-only places; our particle filter with the four uses of 4.6; final-world test and after-episode replica; O 3 repetitions, T 1. About 7 days (ESTIMATE; the review's realistic range is 7 to 9). The refinement with levels (4.5) adds about 1 day and is built only on a go that needs fewer steps.

Order: the pilot first (section 11). Nothing else starts before its go. On a go: after the find_dice numbers are frozen, inside the dev-track rules (section 7), arm T's runs on the cluster in parallel with our arm's development.

Risks:
- R1. TAMPURA's E-M runtime. MEASURED once: its first planning step on seed 0 took 174 s on the laptop (WSL, no other probe running; `probe/p4_tampura_one_step.py`, `probe/out/tampura_one_step_slam_collect_0.json`), and it chose `move_pick(o_target_0)` from a learned model of 15 actions over 14 abstract beliefs. At that rate 20 episodes of 9.22 steps take about 9 h (ESTIMATE), not the 6.6 h the paper's 129 s implies; the cluster's rate is UNVERIFIED. Both figures assume episodes that reach the goal belief; one that never does keeps planning for 20 steps (policy.py:105; tampura_policy.py:77-80), up to about 58 min (REVIEW.md 2.3), so the pilot, which includes the three tight seeds on purpose, may take up to about 4 h.
- R2. Our literals and the replica disagree: our arm stops while the replica says not done (lost reward), or goes on while it says done. C2 measures it; the world test is unaffected.
- R3. The return punishes extra looks: a policy that looks before every commit is capped at 0.98^12 = 0.785, below TAMPURA's 0.81. The recommended gate (SC4 (c)) does exactly that; against a TAMPURA near 0.81 only the refinement could close the gap, and the pilot rule (section 11) stops before that case arises.
- R8. Power: one arm T run per seed resolves only success differences of about 0.3 (section 6, REVIEW.md O7).
- R4. Phantom collisions: a single particle in collision zeroes their reward until an observation filters it out (E:276-277) while the true robot is free. TAMPURA's belief also blocks its own moves then (2.2); our arm is not blocked (it reads the true flag) but is scored through a replica whose particles it cannot see (3.3, 3.6). Under their reward both arms lose episodes to it; under the world-state test only TAMPURA can, by their spec, unless its search finds a pick whose observation filters the particle out (how often it does is UNVERIFIED until the pilot).
- R5. Scope: the result would test the planning layer, not the space abstraction (REVIEW.md O2, section 12), and so does not serve #P10's framing "a space abstraction, demonstrated on TAMP" (PAPER_AUDIT.txt:9505-9508).
- R6. The paper's E-M numbers may come from another code version or setting (UNVERIFIED): the source keeps a commented `ACTION_STD = 0.01 # Standard` beside the active 0.04 (E:50-52), and on the released code every scripted rule stays at 0.51 to 0.63 with three of 20 seeds never won (3.5). If arm T also lands far below 0.81, the comparison is against our re-run, and the paper's number is quoted with that caveat. The arm T pilot (SC1) settles this before any work on our arm.
- R7. Time taken from find_dice and class_uncertain in a month that is already full.

---

## 9. The no-fit case's objections, answered

Quoted from no_fit_case.md section 3.2 (lines 158-164) and 3.4 (lines 173-178), each with my answer and what I concede.

**3.2 RUN: "There is nothing for his pipeline to adopt ... slam_collect has no client, no 3D body, no camera, no arm and no physics. The success criterion ... is defined on their 2D particle belief and on nothing physical."**
Conceded for the PyBullet half: rendering, segmentation, boxelization of observed depth, shadows and the physical executor have nothing to act on. Answered for the rest: the run is per step in their environment with their execute layer as the executor (BF#36's B9 pattern, PAPER_AUDIT.txt:7421-7424, on a task whose execute layer is all there is; BF#37 parked B9 for find_dice and kept arm O physical, :7509 and :7525, so this is a separate arm and is named as such in 3.7), and the criterion is not only their particle belief: their environment keeps a true state (the executing `SlamState`, E:331-369, with true targets and a true collision flag, E:442-452), so the world-state test of 3.3 is shared by both arms, with their belief reward beside it.

**3.2 METHOD: "Nothing is hidden in space ... The only uncertainty is where the robot itself is, a quantity his fixed-base arm always knows ... his shadow machinery has no counterpart."**
Conceded: no occlusion, no shadow, no search for a hidden object. Answered: the hidden quantity is the robot's position relative to named regions of the plane, and their observation reports it as region membership (E:899-903). The method's planning claim, a belief over named regions with known-if literals that only a sense action can set, is what this task tests; occlusion is one way to make a region fact unknown, motion noise is another. "His fixed-base arm always knows" is true of our robot, not of this task: here the agent is the robot their environment provides.

**3.2 TIME: "A port is a new domain and a new 2D harness ... about 6.6 hours for 20 seeds on the T arm alone."**
Conceded: the TAMPURA runs, 6.6 hours by the paper and about 9 by the one step timed here (R1). Our side is about 7 to 7.5 days (ESTIMATE, revised after REVIEW.md O5; the review's realistic range for the minimal version is 7 to 9), at the lower end of the no-fit case's own 1.5 to 2 weeks for E-M (no_fit_case.md:182), because the probe shows the harness is a loop around their own functions (the scripted two-belief runs of 3.6 are that loop with a rule in place of the planner, at a median 4 to 8 s per episode), the estimator is about a page, and the domain has five actions.

**3.4.1: "A port would test his planner on TAMPURA's model, not Semantic Boxels."**
Partly conceded. It is not TAMPURA's model: TAMPURA has no written outcome model; it learns one per step by sampling `effects_fn` (E:282-328; tampura_policy.py:120-145). Ours is written in our formalism (K-literals, a sense action with an optimistic deterministic effect, a commit gate, costs, replanning), H3's description (PAPER_AUDIT.txt:3265-3269) and M8's pattern (pddl/domain_pddlstream_m8.pddl:175-199, 242-256). What both share is the task's vocabulary, which is the observation's (any agent on this task must use it). Conceded: perception, boxelization from depth, shadows, 3D geometry and physical execution drop out, and the regions are given, not perceived. The paper's claim must say exactly that: "the planning layer of Semantic Boxels, with a region-level belief, on TAMPURA's ego-pose task".

**3.4.2: "The planner's state would have to come from their particle belief ... (H1), unless he writes a 2D particle filter of his own."**
He writes one (4.6; 1 day, ESTIMATE), fed only by what `step` returns. Conceded: a Bayes filter of the published model is not new, and on the fields both filters use it tracks the same posterior as theirs. That is intended: both arms then face the same uncertainty, and the comparison is about what each planner does with it. Where ours differs is that it also uses the failed pick, the true collision flag and the true holding field (4.6), and the probe shows that this change alone, under the same scripted rule, moves the world-state test by 8 to 10 of 60 episodes (3.6); a paper must report that split, which the switchable uses of check C2 allow. Their filter is part of the task module (E:88-279), not of TAMPURA's planner.

**3.4.3: "The published analogue already exists ... on E-M that family scores 0.41 to 0.56."** A direct answer in five parts.
1. What MLO and WAO are, from the code. They are TAMPURA's own learned model with another decision rule: the model F is learned the same way (tampura_policy.py:120-145) and only `solve_mdp`'s conversion changes (mdp_solver.py:186-195). MLO keeps, for each action and source belief, the single most likely abstract outcome (mdp_solver.py:89-98); WAO turns every outcome into a deterministic action with reward 10 R minus the penalty -log p (mdp_solver.py:136-161). This settles the no-fit case's UNVERIFIED item (no_fit_case.md:177, 214) for this repo: they share the learned model. Whether the paper's runs used this code is UNVERIFIED.
2. Why that family can go wrong on E-M (my reading of the mechanism, not run): an abstract outcome is a whole set of atoms, so one physical result splits over several abstract beliefs (a place that worked, with or without known_pose, with or without an in(beacon) or another target's target_in atom), and "the most likely single outcome" can be a failure while success is likely in sum, or the reverse; and the probabilities come from at most 200 samples per step in batches of 20 (C lines 7, 14) under optimistic priors for unseen outcomes.
3. Ours is not that family. It determinises by threshold, not by likelihood: `depends=[known_pose]` becomes a precondition with their own threshold, a commit never bets on a likely but uncertain outcome, only a sense action reaches the literal, and in the recommended form every commit needs a look since the last commit and the goal place a predicted known end, both as preconditions (4.5, 5). Scripted analogues of these structures, run in their environment (MEASURED, 3.5 and 3.6): under their reward 0.51 to 0.60 on seeds 0 to 19 and 0.55 to 0.63 on the held-out seeds, whichever belief acts, against MLO 0.41, WAO 0.56 and TAMPURA 0.81; never looking scores 0.34 (0.23 through the replica). So under their reward the threshold structure lands at the top of that family's band (WAO 0.56), at most a standard error above it, and I claim no more. Under the shared world-state test, with a sketch of design (c)'s estimator, the predictive structure wins 52 of 60 episodes for a return of 0.70 (37 of 40 and 0.75 on the held-out seeds), and with the design's own estimator form the always-look and predictive structures win 55 and 56 of 60 (S1y, S4y). The paper gives no world-state number for TAMPURA, MLO or WAO, so arm T's re-run is the only comparison for it.
4. What this does not show: that our planner produces those policies (checks C3, C4 and the comparison will), or that the world-state numbers hold up against TAMPURA's, which nobody has measured. Conceded: with a gate that is too loose our arm behaves like the no-look rule (world return 0.38), with the reactive gate alone like S2o (0.57); the always-look rule (0.69, and 0.71 with design (c)'s estimator form) ties the predictive one within a standard error, which is why it is now the recommended gate.
5. After the review (REVIEW.md O1), the plain conclusion: the no-fit case's objection 3.4.3 stands under the paper's criterion. Every structure the probe tried that looks, including the recommended one with design (c)'s estimator form, scores 0.51 to 0.63 under their reward, at WAO's 0.56 within about a standard error and far below TAMPURA's 0.81. The gain appears only under the world-state test we add, and 8 to 10 of 60 of those wins come from our estimator reading fields their filter ignores (D-9's collision flag, the failed pick), not from planning. I no longer claim that slam_collect answers 3.4.3; section 11 makes the pilot decide whether a comparison is worth running at all.

**3.4.4: "E-MF cannot separate methods ... the paper itself uses it to check implementations."**
Agreed. E-MF is our harness check, not a result: a return clearly below 0.95 means our harness or estimator is wrong.

**The verdict line: "for slam_collect, nothing short of a different system" (no_fit_case.md:206).**
It is a different system in perception and execution and the same system in its planning layer. After the review I add: and on this task the planning layer is not shown to do better than the paper's determinised baselines under the paper's criterion (3.4.3 part 5). Whether the planning layer's generality is worth a week before 2026-12-04 is decided by the pilot's rule (section 11) and then by you (SC1), not by fit.

---

## 10. Decisions for Hani

Replaced by section 13, which lists SC1 to SC12 as they stand after the review and says for each what changed from the first round.

---

## 11. The pilot and its go or no-go rule (added after REVIEW.md O1 and section 5)

### 11.1 The review's alternative, weighed

The review proposes to keep only the arm T pilot and to gate everything after it on a rule written before it runs. I accept it, for three reasons.
1. Under the paper's criterion the probe predicts parity with WAO, not a gain (O1, section 12). A comparison is worth its 7 to 9 working days (ESTIMATE, REVIEW.md O5) only if TAMPURA's released code also lands near the probe's level, and only arm T can say whether it does (3.6, the doubt about 0.81 on this code).
2. The pilot is cheap against the port: up to about 4 hours on the chair's cloud (R1) and about half a day of work (ESTIMATE: check C0, a slam sbatch and a read-only reader of their saved rollouts).
3. Its result is useful whatever it says: path 2 gets TAMPURA's measured bar on slam_collect, and the paper either learns that the published 0.81 holds on the released code or carries the caveat of R6.
What I give up: no arm O comparison before 2026-12-04 unless the pilot says go and a working week is free. Path 2's own probe of our planner on this task (11.5) is not affected.

### 11.2 What the pilot runs and reads

Arm T only: their driver with the timing wrapper (tools/run_tampura_timed.py, unchanged; check C0 first, one step on the laptop under `flock /root/sb_pipeline.lock`), task `slam_collect` (E-M), seeds 0, 1, 2 (ordinary maps) and 5, 6, 10 (the tight maps of 3.5 finding 3), one run each, on the chair's cloud after your explicit approval of that run (SC7). Their rollout pickles its whole history into the save folder at the end (`save_run_data`, T/policies/policy.py:73-77, 159), the true states included (policy.py:59), so the pilot changes neither their code nor the driver. A read-only reader takes from each run:
- whether their belief's reward reached 1 within the 20 steps, and at which step (policy.py:107-108, 136-138);
- the shared world test on the final true state, `history.states[-1]` (3.3);
- the decision time of every step from the timing wrapper (timed_policy.py:37-45);
- whether the run completed, and its wall time.

### 11.3 Reference numbers, fixed now (MEASURED, `p2_summarize.py pilotref`, 3 repetitions per seed)

| structure (3.5, 3.6) | their reward: wins on seeds 0, 1, 2 / 5, 6, 10 | seeds won in most repetitions | world test at the end: wins on seeds 0, 1, 2 / 5, 6, 10 | seeds won in most repetitions |
|---|---|---|---|---|
| S1, their belief acting | 3, 3, 2 / 0, 0, 0 | 3 | not computed here | |
| S4, their belief acting | 3, 3, 2 / 0, 0, 0 | 3 | not computed here | |
| S1o | 3, 3, 3 / 0, 0, 1 | 3 | 2, 3, 3 / 1, 1, 2 | 4 |
| S4o | 3, 2, 3 / 0, 0, 0 | 3 | 3, 2, 3 / 2, 1, 2 | 5 |
| S1y | 3, 3, 3 / 0, 0, 0 | 3 | 3, 3, 3 / 3, 1, 2 | 5 |
| S4y | 3, 3, 3 / 0, 0, 0 | 3 | 3, 3, 3 / 0, 3, 3 | 5 |

Under the paper's criterion every structure wins the three ordinary seeds and one tight-seed episode in 54 (S1o on seed 10); under the world test the structures with our estimator win 4 or 5 of the 6 seeds in most repetitions.

### 11.4 The rule

Counted over the six pilot seeds, one arm T run each:
- K_tight: the tight seeds (5, 6, 10) on which TAMPURA's own belief reward reaches 1 (the paper's criterion);
- K_ord: the same on seeds 0, 1, 2;
- W_T: the seeds on which TAMPURA's final true state passes the world test;
- t_T: TAMPURA's median decision time per step over all steps of the pilot.

1. **Void.** A run crashes, C0 fails, or the batch passes 5 hours of wall time. The pilot is reported as it stands, and a rerun is asked as its own question.
2. **Stop, TAMPURA above the probe's bar: K_tight >= 2.** No structure the probe tried won a tight seed under their reward in most repetitions (one win in 54 episodes, 11.3). A TAMPURA that wins two of the three is above that level on the paper's criterion and in line with its published 0.81, and our arm could show at best decision time at a lower return.
3. **Stop, no time headline: t_T < 30 s.** The one claim 20 pairs can carry is decision time (O7, section 6); 30 s is ten times my ESTIMATE of at most 3 s per step for our arm (a planner call, which path 2 measured at 1.2 to 1.6 s in a smoke run of our planner on its small mode S domains, tracks/tasks/STATE.md:59-65, plus the estimator). The paper's 129 s and the 174 s step timed on the laptop (R1) both clear it.
4. **Go: K_tight <= 1 and t_T >= 30 s.** TAMPURA's released code then sits at the probe's level on the paper's criterion on these seeds, at ten or more times our decision time. The comparison has one claim to test, decision time at about equal return, plus the world test with the estimator's share shown by the ablations (6); R6 applies to the published 0.81. W_T is reported and does not decide: with W_T >= 5 the world test cannot favour us (our structures reach at most 5 of 6, 11.3), and the headline is decision time alone.
5. **Read before a go counts: K_ord <= 2.** Every structure wins seeds 0, 1 and 2 in most repetitions, so an arm T loss there is read in its log (a planning failure, a phantom collision, a harness fault) before the go is declared. It is not a stop by itself.
6. **Our side, after a go (step 3 of section 8).** Our planned arm with gate (c) runs seeds 100 to 119 x 3 beside the scripted rule S1y on the same seeds (both cheap; H4 keeps seeds 0 to 19 out of it). If the planned arm falls more than two standard errors below S1y under either criterion, the work stops there and is reported.

How sharp the stop of item 2 is (binomial arithmetic, ESTIMATE): if TAMPURA won a tight seed with probability 0.8, in line with the implied 95 to 97 % overall (2.7), the rule would stop with probability 0.90; at the probe's rate of 1 in 54 it would go with probability above 0.99; at S1o's 1 in 3 on seed 10 it would go with probability 0.74.

What the rule does not do. Six seeds, three of them tight on purpose, give no return comparable with 0.81 (REVIEW.md O1), so the pilot decides go or stop and nothing else; its numbers are reported as a pilot, never as a result. The boundary between one and two tight wins rests on one run per seed: a run that crossed it narrowly (its reward reached on its last steps, or lost to one particle) is reported as such, and the decision stays yours.

After a go: the minimal version of section 8 (7 to 9 working days, ESTIMATE) starts only after the find_dice numbers are frozen and if a working week is free (SC1); arm T's 20-seed run is a separate cloud question (SC7). After a stop: nothing more on slam_collect before 2026-12-04; the pilot's numbers go into a BF# entry and to path 2, and this document stays as the design.

### 11.5 Path 2

Path 2 asks which TAMPURA tasks give Semantic Boxels a first number "clearly above 0 and clearly above a random or trivial policy" within a few working days (tracks/tasks/BRIEF.md:13-17). That question is separate from this rule: it needs a number of our planner, not arm T's. Path 2 has since measured their random policy on slam_collect at 0 of 60 under both criteria (tracks/tasks/STATE.md:56-57), is running a mode S probe of our planner with the reactive gate SC4 (a) (TRIAGE.md:338-345; its numbers were pending when I read it, TRIAGE.md:160), and already asks you whether the pilot with a rule fixed before it runs comes first (TRIAGE.md:598-604, its Q44). This section is that rule. One finding of path 2 bears on section 5: PDDLStream's translator needs a numeric cost function defined for every tuple of objects, places or not, or the grounding fails (TRIAGE.md:162-176); our domain generator must emit `hop` for all pairs.

---

## 12. Review and answers

Numbered as in REVIEW.md. "Changed" names the sections of this document that now carry the answer.

**Verdict ("survives with changes").** Accepted; my own final verdict is the same (13).

### 12.1 Citations (REVIEW.md 1: 208 distinct references opened; 0 WRONG, 0 NOT FOUND, 5 PARTLY)

- **1.1 Their environment.** All confirmed. Notes taken: Python's `random` draws at E:110, 714 and in the controllers' `random.choice` (E:1077, 1093, 1111, 1129) (changed: D-3, U-3, 3.1, 3.3); the beacons' later overlap checks use the core shape (`all_shapes.append(BEACON_SHAPE)`, E:1280, read again), which is why targets can start inside a beacon square (changed: 2.1).
- **1.2 Their planner and driver.** All confirmed, including that MLO and WAO share the learned model in this repo (9, 3.4.3 part 1). No change.
- **1.3 Ours.** PARTLY, pddlstream_planner.py:1154-1173: accepted; it is O3 (changed: 4.5, 5, 7). The find_dice-specific arm O G13 (g13_runtime.py:122-145): a slam G13 for arm O is now check C1b and costed (6, 8 step 1). The M8 domain's "only a precondition can force place-first" (:171-174) is the precedent the O3 fix follows.
- **1.4 Records.** Four PARTLY and one omission, all accepted.
  - H1 (PA:3256-3259): 3.3 now quotes the success-scoring clause, rests the scoring reads on BF#37 item 2 (:7518-7523), G2 (:3317-3318) and the find_dice D3 precedent, and names the relaxation (3.7).
  - BF#36's B9 (:7421-7424): 3.7 and 9 (3.2 RUN) now say that BF#37 parked B9 (:7509) and kept arm O physical (:7525), so the slam arm is a separate arm.
  - BF#37 item 2: the per-step world reads are removed (U-2; 3.3).
  - PROPOSAL section 5: the levels, if built, are cut at the precondition flips, not at round numbers (4.5).
  - BF#66's "CLAIM EFFECT: none for this paper" (:9350): now named (3.7, 4.7; SC10, SC12).

### 12.2 Numbers (REVIEW.md 2)

- **2.1 Reproduction.** No change needed; cited in 3.6.
- **2.2 Recomputed and confirmed.** No change needed. One addition: with the stop-step return of 3.3 (no per-step world reads), mean world returns move by at most 0.013 (`p2_summarize.py stopreturn`).
- **2.3 Wrong, overstated or unsupported.** The table has thirteen rows; all accepted.
  1. 13 seeds with a target inside a beacon square at t = 0, 20 atoms (2.1): corrected.
  2. Median 77 boxes per seed (4.4): corrected.
  3. Fourteen 1-primitive picks in a row (3.5 finding 1): corrected.
  4. Scripted episodes 4.1 to 12.8 s (1): corrected to "4 to 13 s"; the 100-particle rows of 3.6 take 39 to 46 s, also stated.
  5. One dot per primitive: about 18 primitives per executed move, about 720 fluents after 20 steps (4.3, 1): corrected; the growth with the steps stands.
  6. Design (c)'s counts (4.5): corrected. With their region argument kept whole, 60 or 90 fluents and about 1,200 ground actions; the review's 65 and 95 count six drift levels where the revised gate has one literal, `(looked)`. Recommended: place destinations restricted to the goal, 30 fluents and 300 ground actions.
  7. "With design (c)'s estimator" (1, 3.6): corrected to "a sketch"; the design's own form was run afterwards (S1y, S4y; O6).
  8. The gain "comes from spatial reasoning" (1, 4.5, 4.8): withdrawn (O2).
  9. "A cleaner test bed for BF#66" (4.7): withdrawn.
  10. The replica "equals" what their belief would have computed (3.3): corrected; it is their belief's update on our primitives, offset by the difference of the two means.
  11. The pilot's time (8, R1): up to about 4 hours, since an episode that never reaches its goal belief plans for all 20 steps; corrected (8 step 0, R1, 11).
  12. "The same learned model" (1): true in this repo, UNVERIFIED for the paper's runs; corrected (1, 9).
  13. "About 98 % success" (2.7): an upper end; 95 to 97 % by the review's estimate; corrected (2.7, 3.5's TAMPURA row).
- **2.4 Statistics.** Accepted, all four. S4o against S2o (p = 0.012 on seeds 0 to 19, 0.11 held out, both flattering): 3.6 point 3. S4n: 3.6 point 3, 4.5, O2. S4o against S1o: 3.6 point 3, and the reason the recommended gate is now S1's (4.5). Power: section 6 and R8. My arithmetic gives an exact McNemar test on 20 pairs about 40 % power (outcomes independent across arms) to 60 % (strongly dependent) at a success difference of 0.3, consistent with the review's estimate that differences much below 0.25 cannot be resolved.

### 12.3 Rules (REVIEW.md 3)

Every row accepted.
- H1 for decisions (PASS), D-1, H2's plan editing, H4's seeds and files, BF#35: no change.
- H1's success-scoring clause: named and rested on BF#37 item 2, G2 and find_dice D3 (3.3, 3.7). Cost: the claim says that scoring reads the final world and replays their belief.
- H1 and D-3, the random streams: fixed, not only named. The replica is replayed after the episode from the logged history, on saved and restored states of both np.random and Python's `random`; our estimator and predictors draw from their own generators; controller calls made for prediction (the hop predictor, SC5's `localizes`) save and restore both global streams (3.1, 3.3, D-3, U-3). Cost: none to the claims; execution noise still differs between the arms, because TAMPURA's sampler draws from the same streams.
- H2's domain swap and H3's "small": named (3.7). Cost: the system under test is "the POD modelling pattern and the planner", not M8's domain, and it gets its own BF# entry.
- H4, a structure developed with the evaluation seeds in view: named (3.7). The structure is frozen in this document, and our arm also runs on fresh seeds 200 to 219 (C7). Cost: the paper says so.
- BF#37 item 2: per-step reads removed (U-2). BF#37's parking of B9 and its physical arm O: named; the slam arm is a separate arm (3.7, 9).
- BF#66: named (3.7, 4.7). The levels, if ever built, are a model detail of this domain, and BF#66 stays out of the paper unless you decide otherwise (SC10, SC12).
- U-1 to U-4, with their costs (3.4): U-1 removed (arm O runs inside `Policy.rollout` with our Belief and Policy subclasses; cost: two subclasses, and C1 then compares like with like); U-2 removed (cost: none; returns move by at most 0.013); U-3 fixed as above; U-4 disclosed (BF#3's import fix, imports only, both arms; cost: one line in the deviation list).

### 12.4 Objections (REVIEW.md 4)

**O1. Parity under the paper's criterion; a gain only on the world test, mostly from the estimator.** Conceded in full. Under their reward the structures closest to design (c) score 0.58 to 0.63 (S4 0.58 and S4o 0.60 on seeds 0 to 19, 0.61 to 0.63 held out) and 0.60 and 0.54 with design (c)'s estimator form (S1y, S4y): WAO's 0.56 within about a standard error, and far below TAMPURA's 0.81. Nothing in the probe predicts that our planning layer beats the paper's determinised baselines under the paper's criterion, so the no-fit case's objection 3.4.3 stands under that criterion (9, part 5). The world-test gain is real but mostly not planning. With the rule fixed and only the estimator changed, the world wins rise by 8 to 10 of 60 (S1 45 to S1o 53, S2 31 to S2o 40, S4 42 to S4o 52), from fields their filter ignores (the true collision flag, the failed pick); with the design's full estimator they rise further (S1y 55, S4y 56) while their reward stays flat (0.60, 0.54) and the replica's disagreement grows (10 and 16 world wins never rewarded). What is left for our planner to show is decision time at about equal return, and only if TAMPURA's released code lands near the probe's level, which only arm T can tell. Neither outcome serves #P10's "a space abstraction, demonstrated on TAMP" (PA:9505-9508; O2). Changed: section 1 (rewritten), 3.6 point 5, 9 (3.4.3 part 5), section 11 (the gate), the ablations in the main table (6), SC1, SC2, SC10 and SC11 (13).

**O2. No boxels; the one spatial ingredient has no measured effect.** Conceded in full. Design (c)'s places are their eleven named regions and three targets, given by the store, not perceived; BF#66's merge rule has nothing to merge but free space, which no action of theirs can name; the `tight` facts had no measured effect (S4n: the same actions as S4o in 83 of 100 paired episodes, world wins 52 and 52 on seeds 0 to 19 and 37 and 36 held out, one win against none, p = 1.0); the predictive structure as a whole ties looking before every commit (S4o against S1o: 4 and 5 world wins only, p = 1.0; +0.017 +- 0.040 in world return); and the drift levels were cut at round numbers. What remains of the answer to Hani, with numbers:
- The fluent count stays small and constant: 30 fluents at every step with goal-only places, 60 to 90 with their region argument kept whole (4.5), against 40 (a dot per action) to about 720 (a dot per primitive) after 20 steps for a known-if fluent per dot (4.3), and 49 atoms in TAMPURA's own abstraction (E:212-279).
- It is small because their observation names only eleven regions (E:454-456, 899-903), not because of boxels. TAMPURA's abstraction is small for the same reason.
- Boxels proper (design (b), 4.4) would add free-space regions: 93 to 121 fluents with regions of equal signature, 167 to 213 with axis-aligned boxes, still constant in the steps. No action can take a free box as its argument (2.2), and the one use of free-space geometry the probe tried changed 1 world outcome in 100 (S4n). So on this task boxels cannot be shown to reason about space; it tests the K-literal planning layer only, the scope section 9 (3.4.1) already gives the claim.
- What would give boxels work here, a perceived map or actions with free-space destinations, is not in their task, and adding either would break your rule that their setup stays as it is.
Changed: section 1, 4.5 (`tight` dropped; the gate one literal; levels only on a go and cut at the flips), 4.7, 4.8, R5.

**O3. Cost steering under ff-astar2; the optimistic place reaches the goal without the gate.** Accepted. The fix is inside the model; nothing edits a plan between planner and executor.
1. The gate is a hard precondition, `(looked)`, on every commit, deleted by every move that is not a look (or a localizing corner move), so every commit starts from a fix, whatever plan the search returns first.
2. `move_place` also needs the static `(EndKnown ?from ?r)`: the hop from the place just looked at to the goal is predicted to end with an expected variance below their 0.05 (0.0016 m^2 per primitive, at least the Chebyshev distance over 0.2 m primitives; the geometric factor 1.0 under H4). A place predicted to end unknown is then not applicable and cannot reach the goal in the model.
3. In the refinement (only on a go that needs fewer steps), the same condition becomes a conditional effect, `(when (EndKnown ?from ?r ?l1) (target_in ?t ?r))`, with levels cut at the flips.
4. The search stays 'ff-astar2' (H2: no planner swap); costs choose only among plans that satisfy 1 and 2. 'dijkstra' (pddlstream_planner.py:1170-1171, blind and cost-optimal, a call argument) is a fallback only if C4 shows the planner taking long detours to its beacons, asked as a named H2 relaxation (SC4).
Cost: about 2.5 more looks per episode than the predictive rule (S1o 433 against S4o 285 looks in 60 episodes), a return within one standard error of it under both criteria (REVIEW.md 2.4), and a cap of 0.98^12 = 0.785 on a six-commit episode (R3). A map with no beacon from which the goal's place ends known has no plan and is lost; on seeds 0 to 19 the goal's nearest beacon is at most 5.10 m away, inside the 6.25 m bound, and C7 checks seeds 100 to 119 and 200 to 219 before any run. No penalty to size, no search change. Our own `target_in` threshold stays at their 0.8, with 0.95 as an ablation (O9, 4.5). Changed: 4.5, 4.8, 5 (the domain and "REVIEW.md O3, and the fix"), 6 (C4, C7), SC4.

**O4. Unnamed relaxations.** Accepted. All are named in 3.7 (H1's scoring clause, H2's domain swap and the planner fallback, H3, H4, BF#37's B9 and item 2, BF#66's claim effect, #P5) and 3.4 (U-1 to U-4), each with its cost; SC12 puts them to you.

**O5. Effort short by two to three days.** Accepted. Section 8 now includes C1b (G1, G2 and G13 variants), C7's calibration on seeds 100 to 119, the BF# entries, the slam sbatch and the review cycles: 7 to 7.5 days by my table, 7 to 9 by the review's; I quote 7 to 9 (ESTIMATE). On numeric per-pair costs through PDDLStream, path 2's probe found that grounding fails unless the cost function is defined for every pair of objects, places or not, and fixed its domain that way (TRIAGE.md:162-176; tracks/tasks/STATE.md:104-112); whether the fixed probe plans was pending when I read it, so the item stays with C3.

**O6. The replica scores primitives our arm planned; its draws are not isolated as written.** Accepted and measured. The design's estimator form was run (S1y and S4y: N = 100, uses (i) to (iv); `probe/p6_two_beliefs.py`, `p2_summarize.py tworow`): their reward through the replica does not rise (0.60 and 0.54), the world test does (55 and 56 of 60), and the replica's disagreement grows (10 and 16 world wins never rewarded), as the review expected. The "equals" sentence is corrected, and the replica is replayed after the episode from the logged history, both streams saved and restored (3.3, D-3, U-1). The offset itself (about 4 to 5 cm per axis in ordinary episodes, the review's ESTIMATE) is not measured here; C2 measures it on a go.

**O7. Little power on success.** Accepted. Section 6 states the resolution (about 0.3 in success with 20 pairs, at 40 to 60 % power), R8 names it, and on a go SC7 asks separately for 2 or 3 arm T runs per seed (7 to 18 more hours, ESTIMATE).

**O8. The context has moved.** Accepted. Section 7 follows the dev-track rules (a `track/<name>` branch in a sibling worktree from stable-2026-11-06, merged only by the orchestrator, the pipeline lock), section 8 orders the work after the pilot, and 11.5 separates path 2's question from the pilot's rule and cites path 2's random baseline (0 of 60 under both criteria).

**O9. Smaller points.**
- C1: revised. Arm O runs inside their rollout, so the identity check is a scripted Policy with their own SlamBelief reproducing the logs of 3.5, and the after-episode replica reproducing their rewards (6).
- Our K threshold: discussed (4.5): 0.8, so that our goal literal means what their reward means, with 0.95 as an ablation.
- `slam_collect_1p.yml`: read (`probe/read_1p.sh`). It differs from slam_collect.yml only in its task name (line 1), and no package registers that name, so it cannot run on the released code. It suggests the authors had one more slam variant; it does not change the E-MF inference (D-5, still UNVERIFIED; SC6).
- What Table III's "abstract beliefs visited" counts: open, UNVERIFIED (D-5).

### 12.5 What fails, what survives (REVIEW.md 5)

Accepted as listed. Each "fails as written" item is withdrawn or corrected above: the spatial attribution and the BF#66 test bed (O2; 2.3 rows 8 and 9), "its return is lower" for S1o (2.4), the cost-steered gate (O3), D-3's isolation (12.3), the replica sentence and the H1 paraphrase (2.3 row 10; 1.4), the counts (2.3), and the effort table (O5). Each "survives with changes" item is done: the pilot with a rule (11), design (c) with a hard gate and without `tight` (4.5, 5), scoring with the world test primary and the replica replayed after the episode (3.3), U-1 to U-4 and the relaxations (3.4, 3.7), the dev-track rules and the effort (7, 8), C1 (6), and the answer to Hani (1, O2). The "survives as written" items are unchanged.

### 12.6 Gaps against the author brief (REVIEW.md 6)

- Section 1's length: rewritten and shorter, about 1,180 words against 1,460, of which the deviation list it repeats takes about 300.
- "(c) anything better": the review's simplest domain (S1o's rule as a one-literal precondition taken from the action log) is now the recommended gate, with the end of the goal place gated by a precondition, not by cost (4.5, 5); our K thresholds are discussed (4.5).
- #P5 and BF#37's parking of B9: named (3.7, 9).
- Hani's question: answered in the review's terms (1, O2).
- `slam_collect_1p`: read and considered (O9; D-5).
- The fluent count of (c) under its own grounding: computed (4.5).
- The parallel drafts: not a gap; not cited.

### 12.7 Files made by the review (REVIEW.md 7)

Not mine to change; its ledger rows are for the session that launched it (REVIEW.md section 7, last paragraph). The files I made are listed in my reply to the coordinator, for the same reason.

---

## 13. Final verdict and the decisions as they now stand

**Verdict: survives with changes.**

What survives: the description of their task (section 2) with its three findings; the probe and its tables (3.5, 3.6), reproduced and recounted by the review; the interface and the scoring as revised (3.1 to 3.4: arm O inside their rollout, the world test on the final world only, the replica replayed after the episode); design (c) as a constant-size K-literal model with a hard one-literal gate and a hard end condition on the goal place (4.5, 5); and the first step, the arm T pilot.

What does not survive: the case for a week-long comparison as a paper result now. Under the paper's criterion the probe predicts parity with WAO (0.58 to 0.63 against 0.56), far below TAMPURA's published 0.81, and the world-test gain is mostly the estimator's (O1). The boxel framing does not survive either: design (c) uses no boxels, its one spatial ingredient had no measured effect, and on slam_collect the fluent count is small because of their vocabulary (O2).

So: the pilot, decided by the rule of section 11, written before it runs; nothing after it without a go; and a go buys a comparison about decision time at about equal return, scoped to the planning layer.

Decisions, SC1 to SC11 revised and SC12 new:

- **SC1. What to run, and when.** (a) The arm T pilot only (seeds 0 to 2 and 5, 6, 10, one run each, up to about 4 hours on the chair's cloud, about half a day of work), decided by the rule of section 11; on a go, the minimal version (7 to 9 working days, ESTIMATE) only after the find_dice numbers are frozen and if a working week is free; on a stop, nothing more before 2026-12-04. (b) Nothing before the deadline; this document stays as the design. (c) The port now, without the pilot. Recommendation: (a). Changed: the first round recommended the port after the pilot; now only the pilot, with its rule.
- **SC2. Primary success test.** (a) The world-state test, their reward beside it for both arms (BF#35, BF#37); (b) their reward primary. Recommendation: (a), unchanged, because BF#35 and BF#37 bind it; every table carries their reward in the next column as the paper's criterion, and the text says that under it the expected result is parity (O1).
- **SC3. Our estimator.** (a) A particle filter of ours, N = 100, with the four uses of 4.6, each switchable; (b) the pose belief as one box; (c) (a) with (b) as an ablation. Recommendation: (a), with the "uses off" ablation in the main table (O1).
- **SC4. The commit gate and the search.** (a) `pose_known` as a reactive precondition (S2's structure; path 2's probe uses it): not recommended for the comparison (10 of S2o's 20 world failures are false stops). (b) The first round's drift levels, with the end level and `tight` in the cost: withdrawn (O3; `tight` had no effect). (c) `(looked)` before every commit, from the agent's own action log, plus the static `(EndKnown ?from ?r)` on the goal place, under 'ff-astar2' (S1's structure, which ties the predictive rule within a standard error). (d) (c) plus the refinement (levels at the flips, the conditional `target_in`), only on a go that needs fewer steps (R3). (e) The 'dijkstra' fallback, a named H2 relaxation, only if C4 shows the planner taking long detours to its beacons. Recommendation: (c); (d) and (e) only under their conditions, each asked again then.
- **SC5. move_corner.** (a) Keep it, with `(localizes ?c)` only where the controller's noise-free path is predicted to end in the corner, the prediction saving and restoring both global streams (U-3); (b) leave it out (D-7). Recommendation: (a), unchanged.
- **SC6. E-MF.** (a) `slam_collect_simple` as E-MF; (b) also `slam_collect_custom` (about 15 minutes of TAMPURA runs, ESTIMATE); (c) ask the authors, now also about `slam_collect_1p.yml`. Recommendation: on a go only, (a) and (b); (c) cheap and optional.
- **SC7. Where the runs go.** (a) The chair's cloud, both arms on one machine, each run asked as its own question; (b) the laptop. Recommendation: (a). The first question would be the pilot: arm T, `slam_collect`, seeds 0, 1, 2, 5, 6, 10, one run each, partition rleap_cpu on cn-04, up to about 4 hours. On a go, 2 or 3 arm T runs per seed (O7) are a separate question.
- **SC8. Branch.** (a) A track branch `track/<name>` in a sibling worktree from `stable-2026-11-06` (d6a9715), made with tools/track_worktree.ps1 and merged only by the orchestrator (CLAUDE.md:27-38), its name the orchestrator's (path 2's track or its own); (b) the first round's `slam-collect-sb` off tampura-bridge: withdrawn, the dev-track rules postdate it. Recommendation: (a), for the pilot's sbatch and reader too.
- **SC9. D-1, the initial observation.** (a) From `b0` at t = 0; (b) from `env.state` at t = 0. Recommendation: (a), unchanged.
- **SC10. In the paper.** (a) A small secondary table and one paragraph scoped to the planning layer; (b) the paragraph only; (c) nothing. Recommendation changed: on a stop, (c), plus at most one sentence on the pilot if it bears on the published 0.81 (R6), yours to decide; on a go and a finished comparison, (a), with their reward beside the world test, the estimator ablation in the table, no boxel claim (O2), and BF#66 left out (3.7).
- **SC11. D-9, the collision literal.** (a) The observation's own flag; (b) their particle definition. Recommendation: (a), with the (b) ablation in the main table, not beside it (O1). Changed: where the ablation goes.
- **SC12. The named relaxations (new, REVIEW.md O4).** (a) Accept those of 3.7 and U-1 to U-4 as named, each with its cost written into the BF# entry, on a go; (b) refuse some, and the design changes as 3.7 says (without H1's scoring relaxation, for example, no world test can be read, and only their reward through the replica remains). Recommendation: (a). The pilot needs none of them beyond the final-world read that BF#37 item 2 already provides for both arms.
