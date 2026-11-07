# Run TAMPURA's system, wire Semantic Boxels into it: the case and a design

Status: written 2026-11-06 for Hani by one agent on branch `tampura-bridge`; revised the same day after a fresh reviewer's REVIEW.md (this folder; its reruns in review_probe/). Section 11 answers the review point by point, numbered as REVIEW.md numbers its points; section 12, at the end, holds the final verdict and the decisions as they now stand. Read only over both trees: no code, audit, ledger, CLAUDE.md or branch touched, nothing written under /root/tampura-work, no run of our pipeline or of TAMPURA. Hani's request, verbatim: "i think we should try to amlost run their system enietrly . theor env and phiscs and what not. and basily amost just wiring as much of sb into their system as possible. make any agnet make a strong, review surrvied argument for thatand how that could look like."

## 0. Evidence and conventions

- Their code: `TP/x` is /root/tampura-work/tampura/tampura/x (the planner), `TE/x` is /root/tampura-work/tampura_environments/tampura_environments/x (the environments), `ENVCFG/x` is /root/tampura-work/tampura_environments/env_configs/x. Ours: paths relative to the repo. Two of our cited files carry other sessions' uncommitted hunks (test_full_pipeline.py: 13 lines removed near 826; tampura_bridge/env_adapter.py: BF#64's hunks near 92 to 105); for those two the line numbers are HEAD's (`HEAD :n`).
- READ: code read for this document, cited file:line.
- MEASURED: (a) the no-fit case's tool_use filter probe (class_uncertain/probe_tool_use_filters.py; its output in class_uncertain/no_fit_case.md section 6), not re-run; (b) read-only scripts in this folder over BF#63 run 2's committed records (bf/BF63_gen_scenes/eval2/5084*/results.jsonl, the counted final rows selected as bf63_tables.py:29-33 does): `bf63_step_equiv.py` (output `bf63_step_equiv.txt`) and `bf63_long_successes.py`, both rerun byte for byte by the reviewer (review_probe/), whose own recheck (review_probe/recheck_bf63.txt) adds the corrections used below; (c) `l2_power.py` (output `l2_power.txt`): exact McNemar arithmetic and the power of a paired campaign, under the assumptions it states.
- PAPER: TAMPURA's published numbers as the survey read them (class_uncertain/TAMPURA_TASKS_SURVEY.md section 0b); not re-read.
- ESTIMATE marks every effort figure, power figure and expected result. UNVERIFIED marks anything not checked.
- Names: arm T is TAMPURA's planner; arm O our pipeline as it runs today (L0 below); arm O' the step-wise arm this document proposes (L2). SB is Semantic Boxels. V1 to V16 are the deviations of arm O' from arm T (2.10). W1 to W13 are the decisions for Hani (section 12). "1.1" to "1.6" are the numbered points of section 1. R1 to R15 are this document's risks (section 7), except in 11.3, where R1 to R16 are REVIEW.md's rules rows.

## 1. The case in one page

**1. Their framework has a slot for exactly this, and their own baselines use it.** Their rollout asks a Policy for one action per step (TP/policies/policy.py:120), runs it with env.step, which calls that action schema's execute_fn (TP/environment.py:49-67), updates the belief with the observation (policy.py:130) and logs the reward of the abstract belief (policy.py:108, 138; TP/spec.py:140-143). The loop never stops early, so a policy returns no-op once it is done, as TampuraPolicy does (TP/policies/tampura_policy.py:77-80). Planners are registered by name (TP/config/config.py:47-52), and every alternative in their repository is one: random, UCT, tabular Q-learning, DQN, a symk contingent replanner (TP/policies/__init__.py:12-18). Their determinised rows MLO and WAO are decision strategies of TampuraPolicy on its own learned model (TP/solvers/mdp_solver.py:186-193, called at TP/policies/tampura_policy.py:154-160). SB as a Policy in that loop is therefore how their code runs every alternative planner; that the paper's Table I rows were produced this way is likely but UNVERIFIED. BF#35's "one environment, one success criterion" (PAPER_AUDIT.txt:7366-7369) then holds with one rollout, one env.step, one Belief.update and one success test for both arms. It does not hold that "only the decision maker differs": arm O' also brings its own perception, its own look configuration and placement poses, and its own kinematic filter. The full list is 2.10 (V1 to V16), repeated in short at the end of this section.

**2. It removes, by construction, the protocol asymmetries that cost the campaign most and that a reviewer can attack one by one.** Today arm O differs from arm T in:
- execution: our physical pick and carry against their kinematic attach (BF#35 measured their carry home: 0 physics steps, 741 die pose resets, PAPER_AUDIT.txt:7378-7384);
- physics: D9 writes their world before our episode (gravity -9.81 where find_dice sets none, our timestep, every task body's mass, inertia and friction, our pad friction, more solver iterations and a finger gear constraint; tampura_bridge/policy.py:65-113);
- the step clock: our whole episode is one of their steps, then no-ops (policy.py:312-325), against their budget of 20 (ENVCFG/find_dice.yml:6);
- observations: our pipeline renders after every action, theirs sees once at initialize (TE/find_dice/env.py:853) and then only at a look (:523-547);
- the score: a terminal observation built from our pad contacts and joint readback (tampura_bridge/scoring.py:47-69).

Each needed a disclosure, some a whole campaign (BF#38's grip, BF#59's die slip). Under L2 no code of ours writes or steps their world (the step count is asserted 0 by an existing hook, 2.3), both arms are carried by the same attach, bound by the same 20 steps, see through the same camera only when their own look or initialize has imaged (under W3 (a)), and are scored by the same world-state test, with their reward beside it (W6 (b)).

**3. It gives our arm the same metric as their Table I.** Table I reports discounted return at gamma 0.98 (survey 0b). Today's harness cannot give that number for us: a success reads 0.98 whatever happened inside the one step. Step-wise, both arms' returns count the same actions. The numbers would not be comparable with Table I's own: BF#63's scenes are newly generated, and how Table I computes the return is UNVERIFIED (survey 0b, section 7). Indicator (MEASURED: bf63_step_equiv.txt; review_probe/recheck_bf63.txt), BF#63 run 2 mapped onto their action vocabulary:
- our 57 successes took a median of 8 of their actions (4 to 69); TAMPURA's 46 a median of 5 (5 to 15);
- mean return over the 76 pairs: ours 0.592, TAMPURA's 0.530, where today's harness would credit ours with 0.709 (over each arm's counted episodes: 0.585 of 80, 0.530 of 76, 0.698).

This is a scale check, not a prediction (3.3 says why it can move both ways).

**4. What it would settle, and what it could not.** BF#63's claim is ours 57 of 80 against TAMPURA's 46 of 76, paired 18 to 9, p = 0.12, and the paper "does not call ours better on these scenes" (PAPER_AUDIT.txt:9123-9131). A step-wise run removes the asymmetries of point 2 from that comparison. At BF#63's size it cannot settle whether a lead survives them: each repetition alone gives p = 0.42 and 0.27 (:9000-9002), and run 2's two repetitions of a scene are close to one draw (:9032-9042). The first version of this point said "either reading is publishable"; at 40 scenes that is withdrawn. A decomposition needs more scenes first (1.7, W12). And BF#65 limits what any find_dice result may credit to the regions (:9266-9272): a difference that survives L2 belongs to SB's perception, belief and planner together, never to a model of where the die hides.

**5. The shell amortises; mode R does not.** The part of the harness that carries over to other tasks is the per-step policy shell: the contract, the logged store writer, the deviation ledger and the per-step world-state test. The slam_collect argument needs that shell ("The per-step harness it needs is the one class_uncertain's per-step bridge needs too", slam_collect/ARGUMENT.md:28). Mode R (main() in a worker thread, 2.3) is find_dice's alone, and each further task needs its own domain and translation table (ESTIMATE: 2 to 6 days per task once the shell exists).

**6. What it does to the items already on the books.**
- #P4 leaves native execution through their execute_fns open, to decide with the supervisors (PAPER_AUDIT.txt:3200-3203). L2 is that option, worked out.
- B9 (BF#36, :7418-7505) put our perception and planner on their execute layer behind our own primitives, and resolved three traps by keeping our motion planner, our finger rule at attach and identity by pinch (:7460-7470). L2 drops all three (section 4, the BF#36 row): it is not B9 generalised but B9's opposite on motion, attach and identity. It keeps B9's no-physics-step rule and its geometric checks (:7455-7459).
- #P5 asked to consider their controllers (:9354-9372). Its own analysis recommends their grasp SAMPLING with our physical execution and our runtime contact verification, and records that their kinematic executors conflict with #P1 (:9365-9370). L2 takes, on arm O' only and for a protocol reason, the half #P5 advised against. It does not answer #P5, which stays open for our pipeline with its recommendation unchanged.

**What it costs, up front.**
- On arm O', physical execution, our grasps, our motion planner, our finger rule and identity by pinch are not exercised (N1, N2). #P1's claims (PAPER_AUDIT.txt:129-146) do not cover the L2 runs: arm O' is carried by a per-waypoint pose reset, the class of mechanism #P1 removed from our pipeline (:138-143). Those results stay on our own scenes and in BF#63.
- tool_use and class_uncertain have no camera (survey section 7). There the part of SB that runs is its decision layer, fed by their belief, a declared relaxation of H1; on tool_use it sits next to their own contingent_policy (3.1).
- 14 to 18 working days to find_dice numbers (ESTIMATE, section 6), with 20 weekdays left before 2026-12-04.

**The deviations of arm O' from arm T, in short** (each in full in 2.10): V1 perception (theirs: the exact pose from any pixel; ours: 6 pixels and our estimate); V2 looks only from home, a configuration their sampler never yields; V3 placement xy chosen by SB; V4 the same five stored grasps per object, chosen by different deciders; V5 our kinematic filter on our geometry; V6 three domain deltas; V7 their IK chooses the executed configuration, for both; V8 in-episode random draws unpaired; V9 contract aborts end O''s episode; V10 O' excludes a failed binding, T may repeat it; V11 the per-step clocks hold different work; V12 the same initial view; V13 one world-state test, their reward beside; V14 aborts never drop a pair; V15 the same node, back to back; V16 (fallback only) our render after every step.

### 1.7 Why spend this time now? (the review's first objection, answered)

The review asks why L2 should take the next weeks, given that BF#63's lead is not significant, against BF#65's option 1, more generated scenes, and the class_uncertain plan whose route phase waits for this verdict (class_uncertain/STATE.md:30-36). The answer concedes the ordering.

- **What L2 buys that the others do not:** one protocol for execution, physics, step budget, sensing and score. **What the others buy that L2 does not:** BF#65's option 1 decides whether the paper may credit the regions on find_dice at all (PAPER_AUDIT.txt:9230-9242, 9266-9272); more scenes decide whether any find_dice lead is significant; the class_uncertain plan is a second TAMPURA task on objects we have no model of, which Hani commissioned.
- **L2's own payoff depends on the other two.** Without option 1, a find_dice L2 result decomposes a lead that comes from lifting cups to look behind them (:9166-9176). Without more scenes, it decomposes a lead that is not significant. Both come first in any order that wants L2 to say something.
- **Part of L2's question can be answered now, at no cost.** Recounted in their action vocabulary under their 20-step budget, 2 of our 57 successes exceed it, with or without our observes (s101 r1 and s139 r1; bf63_step_equiv.txt). TAMPURA succeeded on 101 in both repetitions and failed on 139 in both (eval2/REPORT.txt:19, 57), so the pairs move from 18 to 9 to 17 to 10, exact McNemar p = 0.25 (l2_power.txt). The 8 successes that dispatched no sense need one more look each and stay far under 20 (review_probe/recheck_bf63.txt, item 3). This is a re-count of what our arm did, not a prediction of what it would do under L2, and it bounds the step-budget asymmetry only. The execution asymmetry cost ours nothing measurable in run 2 (57 carries, 0 losses, :8992-8994), and their kinematic carry cannot fail. What stays open without L2 is the render channel (V16) and the registry paths it feeds (risk R2).
- **The ranking recommended:**
  1. Now, at no cost: the re-count as a sensitivity row in the paper's find_dice section.
  2. Hani decides BF#65's option 1 (and BF#64's stopped fix) first, since either changes arm O and so every later find_dice campaign. BF#65 gives no cost for it (ESTIMATE, mine and rough: 4 to 8 working days with its A/B).
  3. More generated scenes on the resulting pipeline: one repetition per arm (run 2's repetitions are near duplicates), a pre-registered exact McNemar, N fixed in advance. If run 2's discordance (27 of 76 pairs) and split (2 to 1) held, the power is 0.54 at 120 scenes, 0.78 at 200 and 0.93 at 300, against 0.17 at 40 (ESTIMATE, l2_power.txt). Run 2's wall, about 2 h for 164 runs on 10 nodes (PAPER_AUDIT.txt:8986-8991), scales to about 5 h for 200 scenes with both arms (ESTIMATE). That run needs Hani's approval of that question alone.
  4. The class_uncertain plan goes on now: it is a plan, not code, and nothing in this verdict decides its route (3.2). Its hold is released (section 12).
  5. L2 after the deadline, on the larger scene set, with this design. Before the deadline only if Hani ranks it above 2 and 3: from Monday 11-09, 14 to 18 working days end between 11-26 and 12-02 (ESTIMATE), with no buffer and nothing else done on find_dice.
- If Hani wants the shared shell (point 5) before the deadline, slam_collect is the cheaper place to build it: its argument prices its minimal version at about 5 working days, pure Python, no PyBullet (slam_collect/ARGUMENT.md:28). That ranking is the slam_collect argument's to make, not this one's.

**Verdict (revised).** Survives with changes (section 12): the direction and the find_dice design survive with the corrections of this revision; the first version's recommendation to build it now does not, and is withdrawn. L2 is an option for Hani, ranked after BF#65's option 1 and a larger scene campaign, which in practice puts it after 2026-12-04.

## 2. The architecture

### 2.1 Four levels; L2 is the proposal

| level | who chooses each action | who executes | physics | what scores | state |
|---|---|---|---|---|---|
| L0, today | our main() inside ONE of their steps (boxel_episode, policy.py:289-297, 312-325) | our physical primitives | D9 on their world (policy.py:65-113) | one terminal observation from our readback (scoring.py:47-69) | running (BF#63) |
| L1, B9 | the same, inside one step | their execute layer behind our primitives, with our motion planner, our finger rule and identity by pinch (BF#36, PAPER_AUDIT.txt:7460-7470) | theirs | a world-state test, their reward beside (:7471-7479) | designed, parked (BF#37) |
| **L2, proposed** | SB as a Policy in their loop, one of THEIR actions per step | their execute_fn through env.step: their motion planning, their attach, identity by symbol | theirs as shipped | BF#36's world-state test after every step and at the end, their reward beside (W6 (b)) | this document |
| L3, maximal | SB, but every continuous value from their samplers and SB's state = their abstract belief | theirs | theirs | theirs | mode S below: right for tasks without a camera, wrong for find_dice (it drops the regions) |

### 2.2 One step of their loop under L2

Their rollout (TP/policies/policy.py:105-153) is untouched. At each step:
1. Theirs: `s = deepcopy(env.state)`, `a_b = b.abstract(store)`, `reward = get_reward(a_b)` (:106-108).
2. Theirs calls ours: `action, info, store = policy.get_action(b, store)` (:120). SB then:
   1. perceives only when their arm has just imaged: at t = 0, after their initialize imaged the scene at DEFAULT_ARM_POS (TE/find_dice/env.py:853-857), and after a look of SB's whose motion ran, which SB knows from its own joint readback (the arm at q_home within their np.allclose). Every look SB issues is from home (3.3), so SB's render is the D4 eye, their camera at DEFAULT_ARM_POS (tampura_bridge/task_spec.py:66-75): the view their look has just imaged (TE/find_dice/env.py:528-547). After a pick, a place, a go-home or a failed look, SB gets no image (W3 (a));
   2. updates its registry and belief with its own perception (boxelization, shadow casting, register_new_detections, execution.py:2499);
   3. continues its current plan, or replans on its usual triggers, a failed binding among them (2.9 (b));
   4. translates the plan's next step into one of their actions over their symbols (3.3), adding its own placement and look values to their store (2.6);
   5. checks, read only, that the action is applicable under their preconditions (2.5) and logs the result;
   6. returns the action, or no-op once main() has returned, since their loop runs to max_steps (policy.py:105-153).
3. Theirs: `observation = env.step(action, b, store)` runs their execute_fn (TP/environment.py:62-65), `bp = b.update(...)` (policy.py:130), the reward of `bp` (:138), `history.add` (:136); after max_steps the final state (:153).

Success for both arms is BF#36's world-state test (PAPER_AUDIT.txt:7471-7479), applied read only after every step, so that a discounted return comes from it, and once after the rollout. For arm T it runs in its timed get_action (tampura_bridge/timed_policy.py:37), for arm O' in SB's get_action, outside the timed span in both and never passed to a planner (a G2 style leak test, as for the contract). Their own rewards[-1] == 1.0 (G12, :3434-3436) and their return are reported beside it (W6 (b)).

### 2.3 One policy, two modes

- **Mode R (registry; find_dice).** test_full_pipeline.main() (HEAD :692) runs in a worker thread, behind a bridge switch --executor theirs that is off by default, so L0 runs as today. With the switch on, for arm O' only:
  - The primitives main() imports into its namespace (HEAD :105-114) become stubs: execute_pick, execute_place, execute_stack and handle_observe_action, and the arm motion of the move branch (HEAD :2037-2056; robot_utils.move_robot_smooth, hooked by G3, PAPER_AUDIT.txt:3338-3342). A move stub records the pending motion and returns. A pick or place stub merges it with its own step into one of their actions, posts that to get_action and blocks until the rollout has executed it (the next get_action call). It then returns what main() expects, from our own sensors (2.5): execute_pick a PickResult(held_body_id, config, touched) (execution.py:77, 1457; touched is empty, since a failed kinematic pick touches nothing), execute_place a configuration or None (:1505-1506). execute_stack and handle_observe_action raise, since neither operator is in the L2 domain (3.3).
  - handle_sense_action (execution.py:2741) is wrapped, not replaced: the wrapper posts look(die, caster, q_home), and once the rollout has run it and the arm is at q_home, it runs our own sense on the render. Our perception stays ours.
  - Seven post-action renders are gated: world_integrity_check (HEAD :1600) and refresh_object_aabbs after a carry loss, a pick failure, a place and a stack (HEAD :2226, 2433, 2576, 2623, 2838, 2897). Each runs only on the image of a look that has just run, and otherwise returns no events and no lost objects. Without this, main() would see the scene after every action, which W3 (a) forbids.
  - Three contact checks, since a never-stepped world has no contact points: _verify_holding's 0.5 N in the goal check (HEAD :3048; the force test at :521-532) becomes BF#36's geometric pad test (both pads within 1 mm of one body, PAPER_AUDIT.txt:7447-7449, 7457-7459); the place-entry check inside execute_place (execution.py:563) goes with that primitive, and the place stub raises the same EmptyHandError (caught at HEAD :2541-2549) when the pad test finds the hand empty; carry_hold_end after a carry (HEAD :2194-2196) reads contact points (execution.py:575, 630) and is inert on arm O', since its switch is one of the slip switches that are off there (execution.py:601; 2.8).
  - No physics step from our code: D9 (policy.py:65-113) is not installed, and the adapter's env.step_simulation becomes a no-op, so main()'s unconditional 50-step settle (HEAD :916-917) moves nothing. The existing hook on pybullet.stepSimulation (tampura_bridge/gate_hooks.py:238-257, installed at :617) counts every call that reaches the executing client; that count must be 0 per episode, since their find_dice code issues none (2.8). The no-op's own call count is logged, not asserted.
  - That list is what reading found. The harness starts with BF#36's S1 (PAPER_AUDIT.txt:7494-7496): a read-only census of every render, force read, stepSimulation and finger command in one arm O episode, with counts, so that a site missed here is found before any run.

  The worker and the rollout never run at the same time, so their PyBullet clients see one caller at a time. This is the B9 seam (BF#36 S2, "installed by a bridge switch --executor theirs", :7497-7498), moved from their low-level execute layer to their action schemas.
- **Mode S (symbolic; tasks without a camera).** No perception. Each get_action builds the PDDL init from their abstract belief and store, plans with our PDDLStreamPlanner on a per-task domain in M8's form (a K-literal gate, an optimistic sense, replanning) and returns the first action, replanning every step. For tool_use that domain is a new domain shaped like their spec, not a small M8 delta: M8's pick(?o ?b ?g ?q) over boxels, configurations and kin_solution (pddl/domain_pddlstream_m8.pddl:242-256) has no counterpart there (section 4, H3). Continuous values come from their samplers, called once per episode as their RandomPolicy and ContingentPolicy call them (TP/policies/random_policy.py:18-22; TP/policies/contingent_policy.py:22-26). Their ContingentPolicy does nearly the same with symk on an all-outcome determinisation of their spec (TP/spec.py:453-492; contingent_policy.py:19-47), which is why any mode S claim needs it as the control (3.1). Mode S is not in the minimal version.

### 2.4 Interfaces, both sides

| interface | their side | our side | new |
|---|---|---|---|
| policy construction | TampuraPolicy built by their run_planner from (config, problem_spec) (tools/run_tampura_timed.py:142-144, their run_planner copied); register_planner / get_planner (TP/config/config.py:47-52) | today BoxelBridgePolicy, instantiated directly (tampura_bridge/policy.py:308-327; PAPER_AUDIT.txt:3443-3444) | tampura_bridge/sb_policy.py, instantiated directly under W11 (a): no registration, so G13 holds as written |
| one decision | Policy.get_action(belief, store) -> (Action, info, store) (TP/policies/policy.py:93-94) | dispatcher (test_full_pipeline.py HEAD :1998-2008; branches move :2037, sense :2242, observe :2278, pick :2323, stack :2778) | step_executor.py (mode R) |
| execution | TampuraEnv.step -> schema.execute_fn (TP/environment.py:49-67); SceneState.apply_sequence and the attach (TE/panda_utils/panda_env_utils.py:611-639); pick_execute (:927-978), place_execute (:981-1034) | execute_pick (execution.py:1011), execute_place (:1505), execute_stack (:1678), handle_observe_action (:2689): not used on arm O' | stubs in step_executor.py |
| action arguments | AliasStore symbols; their samplers add values and certified facts (TP/spec.py:130-137) | PDDLStream values (RobotConfig, grasps, boxel ids) | action_map.py: the translation table, the grasp-symbol stream, and the store writer (object-pose and looking-conf only), logged |
| applicability | applicable_actions(a_b, store) (TP/spec.py:176-191) | none today | contract.py, evaluation side |
| sensing (mode R) | their camera: robot.get_image at the camera link (TE/panda_utils/robot.py:96-104, 263-264); initial image at DEFAULT_ARM_POS (TE/find_dice/env.py:853-857); look images (:541-547) | BoxelTestEnv adopting their executing client (tampura_bridge/env_adapter.py HEAD :69-136); the D4 eye is their camera at DEFAULT_ARM_POS (tampura_bridge/task_spec.py:66-75) | renders gated to looks (2.3) |
| identity map | world.objects / world.categories and store.get (TE/find_dice/env.py:70-73) | G8(a) (PAPER_AUDIT.txt:3380-3384); env_adapter.py HEAD :128-136 | none |
| belief and reward | Belief.update (policy.py:130); get_reward (TP/spec.py:140-143), which reads the abstract belief and store.certified (:141) | their belief never read by SB on find_dice (2.5) | none |
| success, world-state | none in their code | BF#36's shared test (PAPER_AUDIT.txt:7471-7479), never built (S3 at :7499-7500) | tools/shared_success.py, per step and final |

### 2.5 The applicability contract and the outcome channel

**The contract.**
- Their rollout runs whatever action a policy returns: nothing checks preconditions between get_action and env.step (TP/policies/policy.py:120-130).
- TampuraPolicy itself falls back to a random applicable action when its solution is not applicable (TP/policies/tampura_policy.py:161-168).
- Their kinematic pick attaches the named body whatever the gripper touches: state.grasp is set unconditionally after the close (TE/panda_utils/panda_env_utils.py:963); this is BF#36's trap (ii) (PAPER_AUDIT.txt:7466-7468).

So the harness keeps SB inside their model. Every returned action must be in `problem_spec.applicable_actions(a_b, store)` (TP/spec.py:176-191). The check is evaluation side: it reads their abstract belief, writes its result to the ledger, and never feeds our planner (a G2 style leak test). An inapplicable choice ends the episode in H5's sense (abort, never work around; PAPER_AUDIT.txt:3274-3275): the policy returns no-op for the remaining steps, and their execute_fn never runs the inapplicable action. **An abort is an arm O' failure, never a gate failure** (2.9 (d)). Each abort is classed by the precondition that failed: a look refused because their belief already knows the die is a perception miss (2.9 (c)); any other refusal is a translation or model error. Both classes are counted and reported per campaign.

**The outcome channel**, that is, what tells SB whether its step worked:
- find_dice: our own sensors only. A pick is judged by the geometric pad test (both pads within 1 mm of one body, PAPER_AUDIT.txt:7447-7449, 7473-7475); tactile queries with bodyA = robot are legal under G8(b) (:3386-3391). A place is judged by the same test (the hand empty), a look by the joint readback (the arm at q_home) and then by our render. Their execute_fns fail silently, returning the old state, when IK or motion planning fails (TE/find_dice/env.py:377-379, 389-390, 447-448, 458-459, 535-536, 578-579), so these checks are how SB learns of a failure; 2.9 (b) says what follows. Disagreements with their belief's `holding` are counted, never read by the planner. They should be rare, because their pick plans the grasp at their belief's pose, the simulator's pose once seen (TE/find_dice/env.py:368-375 with :71-73 and World.poses, TE/panda_utils/panda_env_utils.py:585-587). That rate is UNVERIFIED.
- tool_use and class_uncertain: the outcome exists only in their belief. known-pose after a pull is their particle re-simulation (TE/tool_use/env.py:102-121, 153-154); the class is the simulator's label (TE/class_uncertain/env.py:175); the break is a random draw (:226-229). SB would read those literals from the abstract belief, each read declared and counted (section 4, H1).

### 2.6 Continuous parameters

Their actions take store symbols; their samplers add values with store.add_typed and certify facts with store.certified.append (TP/spec.py:130-137). At t = 0 arm O''s policy calls their flat sampling once with their flat_width (ENVCFG/find_dice.yml:9-10; one round per unit of width, TP/spec.py:110-137, so 5 samples per stream and object), as ContingentPolicy does (TP/policies/contingent_policy.py:22-26), and as TampuraPolicy samples once per episode (TP/policies/tampura_policy.py:109-115). Then, per kind of value:
- **Grasps: among their samples, chosen by our planner.** Our grasp stream returns, for each object, the grasp symbols their sampler stored (grasp-sample certifies object-grasp(o, g), TE/find_dice/env.py:903-911; saved grasps, :39, 756-769, from the per-mesh JSON library, TE/panda_utils/panda_env_utils.py:265-285). Our kinematic stream checks each on our perceived geometry (V5), and the plan's ?g is one of them, so the executed grasp is the planned grasp. That our kinematic stream accepts their grasp transforms is UNVERIFIED; if it does not, the certified object-grasp fact alone gates the pick, as a declared delta.
- **Placements: SB's.** p takes the xy of SB's chosen free-space boxel; its z and orientation are the object's own resting values as our registry estimated them before the pick (the table is flat, so the resting z does not depend on xy). A wrong z stays wrong, since nothing settles their world; the evaluator logs p against the object's true pre-pick pose, read only. SB adds p with object-pose(o, p), the fact their place-sample certifies (TE/find_dice/env.py:912-920).
- **Looks: from home, a value their sampler never yields.** Their look sampler puts the camera 0.2 to 0.3 m above the object (TE/find_dice/env.py:619-628), so it can never return DEFAULT_ARM_POS, whose eye sits at z 0.588 m (tampura_bridge/task_spec.py:70). SB adds looking-conf(caster, q_home) for each caster it may sense behind: a new value and fact, not one their stream would certify (V2).
- **The writer's limit.** The store writer may add object-pose and looking-conf entries only. Their reward reads store.certified as well as the abstract belief (TP/spec.py:141), but find_dice's reward reads only is-target, holding and at-home (TE/find_dice/env.py:993-1004); G6's positive control asserts that no entry the writer can add changes get_reward (section 4, G6).
- **The executed configuration is theirs.** Their pick and place take no configuration (TE/find_dice/env.py:925-961); their IK computes it inside the action (grasp_ik and ik, TE/panda_utils/panda_env_utils.py:862-886), with random restarts (:158-170). Our plan's ?q is a feasibility witness only (V7; section 4, H2).

W4 (b) would choose placements among their place-sample values as well (5 per object). W4 (a) is recommended: WHERE to place a cup is a decision SB is about.

### 2.7 Drivers

Arm T's driver is their run_planner.py plus one import (tools/run_tampura_timed.py:1-5, 107-145), and run_planner builds the policy from config and problem_spec only (:142-144). Today's arm O driver instantiates its policy itself (tampura_bridge/run_bridge_on_finddice.py:277) and reaches the env through the execute_fn's closure (:274; policy.py:165). Two options for arm O':
- (a) A bridge driver that instantiates SB's policy directly and hands it the env. Nothing is registered in their registries, so G13 holds as written: exactly two registrations (PAPER_AUDIT.txt:3442-3444) and no class of ours in their registries (tampura_bridge/g13_runtime.py:134-137).
- (b) The very same driver file as arm T with `--planner semantic_boxels`. The policy finds the executing client through their CLIENT_MAP (TE/panda_utils/panda_env_utils.py:589-591); every task registers its clients in build order and builds the executing world first (TE/find_dice/env.py:695-696, called for the executing world at :833-839 before the sim world at :842-848; TE/class_uncertain/env.py:314-315 with :373-375; TE/tool_use/env.py:244-245 with :588-589). This registers a class of ours, which G13 as built rejects (g13_runtime.py:134-137), so G13's text and check change first.

(b) is the stronger symmetry (one driver file); (a) keeps G13 as it is and is quicker (W11).

### 2.8 What stays theirs, what SB brings, what goes, what is new

- **Theirs:** env.initialize and its scene loading (with BF#63's one-scene working directory and manifest pinning, PAPER_AUDIT.txt:8897-8900); physics as shipped (find_dice never sets gravity or steps: neither TE/find_dice/env.py nor TE/panda_utils/panda_env_utils.py calls setGravity, and the only stepSimulation in the shared execute layer runs when sim_steps > 0, panda_env_utils.py:636-637, which find_dice never passes; tool_use and class_uncertain set gravity -10, TE/tool_use/env.py:308, TE/class_uncertain/env.py:334); motion planning, IK (with random restarts, panda_env_utils.py:158-170; BiRRT, :442-496), grasp samples and the attach inside their execute_fns; belief and update; reward; max_steps 20 and gamma 0.98 (ENVCFG/find_dice.yml:6, 15); seeds and scene files.
- **SB:** in mode R, perception on their camera, boxelization, shadows, the registry and its belief, the M8 domain (generated) with three deltas, PDDLStream with Fast Downward, the replanning loop, and every WHAT, WHERE and ORDER decision, including which of their grasp samples a pick uses. In mode S, the planner and a per-task domain in M8's form.
- **Goes on arm O'** (stays on our scenes): D9 (policy.py:65-113), the terminal observation (scoring.py), our physical primitives, force-based verification, our motion planner, our finger rule, BF#59/BF#62's slip switches.
- **New code for the minimal version** (sizes ESTIMATE, about 2,000 lines with tests):
  - tampura_bridge/sb_policy.py (about 150): the policy, the per-step world-state test call, G13 in __init__;
  - tampura_bridge/step_executor.py (about 500): worker thread, handoff, stubs, the sense wrapper, gated renders, geometric checks, the failed-binding set, release at max_steps (R12);
  - tampura_bridge/action_map.py (about 250): the find_dice translation table, the grasp-symbol stream, the logged store writer;
  - tampura_bridge/contract.py (about 100): applicability and abort classes;
  - tools/shared_success.py (about 200): the world-state test, per step and final, for both arms;
  - tools/census_probe.py (about 100): BF#36's S1 census;
  - gate changes in tools/bridge_gates.py, tampura_bridge/gate_hooks.py and g13_runtime.py (about 250);
  - tests (about 450).
  - Later, not minimal: symbolic_mode.py (about 300) and one domain per mode S task.

### 2.9 The seams where arm O' would fail first

(a) **Which grasp.** Their pick takes one of the five grasps their sampler stored per object (flat_width 5, ENVCFG/find_dice.yml:10; TE/find_dice/env.py:756-769). Our planner chooses it, through a grasp stream that returns those symbols (2.6). Nothing between planner and executor picks one.

(b) **Silent failures.** Their pick, place, look and go-home return the old state when IK or motion planning fails (TE/find_dice/env.py:377-379, 389-390, 447-448, 458-459, 535-536, 578-579). TAMPURA's own last three actions on scene 131 were one pick repeated, in both repetitions (eval2/REPORT.txt:49); that those picks failed in IK or motion is a reading, UNVERIFIED. Arm O''s rule:
- a failed pick of (o, g) excludes g for o at the next plan: the failed-binding set filters our grasp stream, the layer where F2 already marks an object ungraspable after three failed picks (HEAD :2396-2420); F2 stays;
- a failed place of (o, p) excludes that free-space boxel for o for the rest of the episode;
- a failed look leaves SB without an image, and main()'s sense-failure path runs as for a blocked view;
- a failed go-home leaves the arm away from home while their belief says at-home (the quirk, :563-581), so a second go-home is inapplicable (NOT at-home, :984) and the episode ends; the world-state test scores that a failure, for either arm;
- every silent failure is logged with the bodies in collision at the failing configuration, read only (R15; section 4, H1).

This is information from execution reaching SB's belief through its own sensors, as an IK failure does in our pipeline (one of G3's enumerated triggers, PAPER_AUDIT.txt:3334-3336); it edits no plan.

(c) **Their belief sees the die before ours does.** Their observation adds every body with at least one pixel in the segmentation (TE/find_dice/env.py:64-73); our registry needs 6 (perception.py:320). A die that shows 1 to 5 pixels is known to their belief and unknown to SB. Every further look(die, ...) is then inapplicable (NOT known-pose(?o1), :969), and SB, which still wants to sense, is aborted by the contract on a choice it cannot know is refused. That is a perception miss and is counted as one: an arm O' failure of class "perception miss", reported separately. SB's registry is never shown the die's pose. How often a die shows 1 to 5 pixels is UNVERIFIED; the smokes report it before any campaign (section 6).

(d) **How an abort counts.** As an arm O' failure, never as a gate failure. BF#63's validity rule reruns a gate failure once and then drops the scene's pair for both arms (PAPER_AUDIT.txt:8905-8909); counting aborts that way would drop the scenes SB handles worst. Gate failures stay what they are today: harness faults (our code stepping their world, a tree hash change, a crash), rerun once, then listed.

(e) **Placement height and orientation.** The object's own resting z and orientation from our registry, logged against the truth (2.6).

(f) **The look's ?o2.** The caster of the sensed region: our sense names a region (domain :176), and our shadow_occluder_map, which handle_sense_action already receives (execution.py:2753), names its caster. Their look needs known-pose(?o2) and looking-conf(?o2, ?q) (TE/find_dice/env.py:968-970), both of which hold for a caster SB perceives and has a looking-conf entry for, and their look_execute_fn reads only ?q (:528), so ?o2 changes nothing their look executes.

(g) **main()'s own goal check.** Geometric (2.3), since _verify_holding's force test (HEAD :521-532) cannot pass in a world that is never stepped (BF#36 item (6), PAPER_AUDIT.txt:7457-7459).

### 2.10 Deviations of arm O' from arm T on find_dice

One numbered list, in the form Hani asked for on class_uncertain (class_uncertain/BRIEF.md:86-112): what differs, whether it can be removed, which arm it favours, how it could move the result. The BF# entry and every report repeat it in full.

- **V1 Perception.** T's belief takes the exact simulator pose of any body with one pixel in the segmentation (TE/find_dice/env.py:64-73); O' estimates poses from its own boxelization of the same view and needs 6 pixels (perception.py:320). Cannot be removed: it is SB's part. Favours T. Ends some O' episodes as perception misses (2.9 (c)).
- **V2 Look configuration.** T looks from configurations its sampler draws 0.2 to 0.3 m above an object (:619-628); O' looks only from home (eye at z 0.588 m, tampura_bridge/task_spec.py:70), which T's sampler never yields. Removing it needs our perception to work from their sampled views (not built; ESTIMATE, more than a week). Favours O' on coverage (the whole table in one view), T near a cup: a close look may see behind an unmoved cup (the reviewer's reading of the geometry, UNVERIFIED), though never under it.
- **V3 Placement poses.** T places at its sampler's poses (:912-920); O' at its own free-space boxel's xy (2.6). W4 (b) would remove it. Favours O' if SB chooses where better; small either way.
- **V4 Grasps.** The same five stored grasps per object for both (ENVCFG/find_dice.yml:10), chosen by T's learned model and by our planner. No difference in the set.
- **V5 Kinematic filter.** O''s planner refuses picks that our reach gate rejects on our perceived geometry (BF#65 (c), PAPER_AUDIT.txt:9193-9203); T learns feasibility from their executor. Part of SB. Favours T: our gate may refuse a pick their executor would reach.
- **V6 Domain deltas.** O' plans with M8 without observe, with moved-once and with sensing from home only (3.3); T with their spec. One adopts their own rule (moved-once, W8), one their action set (no observe, W7), and one follows from our eye existing only at home. Neutral by design.
- **V7 Executed configuration.** Their IK chooses it for both arms (2.6). Neutral; it changes G3's text (section 4).
- **V8 Random draws.** Their IK restarts and BiRRT draw from Python's global random inside their execute_fns (TE/panda_utils/panda_env_utils.py:158-170, 488), for both arms but in different sequences, so in-episode draws are unpaired even on find_dice. Not removable without changing their run conditions. Neutral in expectation; noise in the pairs.
- **V9 Contract aborts.** An action outside their applicable set ends O''s episode as a failure (2.5); TampuraPolicy falls back to a random applicable action instead (TP/policies/tampura_policy.py:161-168). Favours T. Counted by class.
- **V10 Silent failures.** O' excludes a failed binding at its next plan (2.9 (b)); T repeats what its model prefers (scene 131, eval2/REPORT.txt:49). Favours O'.
- **V11 Per-step clocks.** O''s time per step holds our perception and replanning, T's its sampling, learning and LAO*. Both measured per step, as their Table II reports. Neutral; reported.
- **V12 Initial view.** Both start from the scene imaged at DEFAULT_ARM_POS (TE/find_dice/env.py:853-857); O' renders the same view itself. Neutral.
- **V13 Success.** One world-state test for both (W6 (b)), their reward beside, for both. Under their reward alone the at-home quirk (:563-581) and the attach by name (panda_env_utils.py:963) can score a success for either arm; under the world-state test they score a failure for either. Neutral by design.
- **V14 Validity.** Aborts never drop a pair (2.9 (d)); gate failures follow BF#63's rule for both arms. Neutral.
- **V15 Hardware and order.** As BF#63: per scene, both arms back to back on the same node (PAPER_AUDIT.txt:8900-8902). Neutral.
- **V16 Only under the W3 (b) fallback:** O' gets our render after every step, the channel through which each of our 57 BF#63 successes found the die (:9166-9176). Favours O' strongly; C2 is withdrawn if it is taken.

Shared by both arms, so not a deviation, but declared: their motion planning runs in their sim world, built from the scene's true poses (TE/find_dice/env.py:842-848), where set_sim moves only objects their belief has seen (:102, 129-130, 135-140). An unseen die stays an obstacle at its true pose for both arms (section 4, H1; R15).

## 3. Per task

### 3.1 tool_use, the worked example (not before the deadline)

**The task (READ).**
- Three 4 cm cubes of 0.1 kg (BLOCK_SIZE 0.02 is the half extent, TE/tool_use/env.py:35; TE/panda_utils/panda_env_utils.py:566) and a hook at a known pose (TE/tool_use/env.py:267-271).
- Each cube is ten bodies drawn with 2 cm std: the first is the task cube, the other nine its particles. Both worlds contain them (:182-219, 276-290, 588-589).
- known-pose holds when the particles' robust std is under 1 cm (:33, 129-136, 163-165).
- Reward: on(c0, c1) and on(c1, c2), computed on the belief from particle means (:167-173, 719-724).
- No sensing action and no camera exist.

**The trigger paragraph checked.** All of its structural claims hold in code:
- M8 gates pick on (obj_pose_known ?o) (pddl/domain_pddlstream_m8.pddl:254); TAMPURA gates pick on known-pose (TE/tool_use/env.py:658).
- M8's observe establishes the literal (domain :396-410); TAMPURA's pull-towards does the same as its one stochastic effect (TE/tool_use/env.py:703-715).
- M8 stacks with on and clear (domain :362-391).
- Our 100 g, 40 mm cube class matches their cubes (BF#38, PAPER_AUDIT.txt:7542-7543).
- A world-state version of their on() is the same formula on the real cubes' poses, read after the run (TE/tool_use/env.py:167-173).

**Mapping onto their actions (mode S, blind).** The table is a translation into a new domain shaped like their spec, in M8's form; it is not a small M8 delta (section 4, H3).

| their action | its preconditions | M8 operator | its preconditions | difference in the new domain (declared) |
|---|---|---|---|---|
| pick(o, g) (TE/tool_use/env.py:644-664) | nothing on o, o on nothing, hand empty, known-pose(o), object-grasp(o, g) (:648-660) | pick(o, b, g, q) (domain :242-273) | handempty, at_config, clear(o), obj_at_boxel_KIF, obj_at_boxel, obj_pose_known(o), kin_solution (:249-255) | add "o on nothing": their pick never unstacks, M8's may (:268-270) |
| place(o, p, g, r) (:665-679) | at-grasp(o, g), placement(o, p, r) | place (domain :284-314) | holding, free space, kin; gives obj_pose_known by commanded pose (:309) | none: both set pose-known on the commanded pose (their effect :675) |
| stack(o1, g1, o2) (:680-702) | neither is the hook, nothing on o2, at-grasp(o1), known-pose(o2) or o2 on something (:684-695) | stack (domain :362-391) | holding, clear(on_obj), stack_kin (:364-373) | add the support's pose gate: obj_pose_known(on_obj) or (on on_obj x); M8's stack has none |
| pull-towards(hook, g, o2) (:703-715) | hook in hand, not known-pose(o2); verify effect known-pose(o2) | observe(o, q) (domain :396-410) | handempty, look_config; gives obj_pose_known(o) | a "pull" operator in observe's form: precondition holding(hook) and not obj_pose_known(o2); optimistic effect obj_pose_known(o2); the outcome read from their belief, replan if it did not hold |
| reward (:719-724) | | tower goal (build_stack_goal, test_full_pipeline.py HEAD :598) | | goal pinned to exactly their conjunction (G10's goal pin, PAPER_AUDIT.txt:3413-3422, in mode S form) |

- **SB's state** each step: their abstract belief's known-pose, on and at-grasp literals (TE/tool_use/env.py:158-175) and the store's symbols. A declared H1 relaxation, and the only observation channel the task has.
- **Grasps and placements:** their streams (mesh grasps, their placement sampler; :620-641, 462-483). Neither stream has preconditions, so the t = 0 sampling covers every object, the hook included; and since stack excludes the hook (:685), every solved episode places it, so hook placements exist at least then (REVIEW.md, row B26).
- **Expected optimistic plan:** pick hook, pull each cube, place the hook, pick c1, stack on c2, pick c0, stack on c1: about 9 actions when every pull lands; TAMPURA executes 9.69 steps on average (Table III, survey section 2). The 20-step budget leaves room for a few failed pulls (ESTIMATE).

**What their kinematic executor and belief-based scoring do to the no-fit case's objections** (no_fit_case.md 1.4):
1. *"Sighted is not one environment; blind has no registry under H1."* Under L2 SB runs blind. Its state is their abstract belief and store, so it has no sensor TAMPURA lacks, and no registry is needed, because their execute_fns take symbols, not geometry. The objection's second half is answered by relaxing H1 for this task (W5): the belief literal is the task's own observation channel.
2. *"Their world cannot support his execution"* (towers fall through, MEASURED; particles in the gripper's way, MEASURED; the adapter cannot register the bodies). Void under L2:
   - Their place and stack run place_execute, which steps no physics. apply_sequence steps only when sim_steps > 0 while a grasp is held (TE/panda_utils/panda_env_utils.py:620-639, 981-1034), so a stacked cube stays at its commanded pose in the executing world.
   - The one action that steps physics is the pull, 5 steps per waypoint with the hook held (TE/tool_use/env.py:416).
   - Neither arm's score reads the executing world: stack writes the commanded pose, relative to a random particle of the support (belief.get_pose is random.choice, :177-179, used at :430-431), into the belief (:457-459), and on() is computed there (:167-173).
   - The measured fall-through (cubes in group 2, mask 4: z_upper 0.02 after 480 steps, 0 cube-cube contacts; no_fit_case.md section 6) can therefore only show in a world-state on() test, after a pull that follows a stack, and then for both arms alike.
   - Particles in the gripper's way do not matter to an arm moved by resetJointState. Mode S registers no bodies, so no adapter is needed.
3. *"Nothing about semantic regions."* This one stands. tool_use tests M8's decision layer (a pose-gated pick, an action that establishes the pose, stacking with on and clear), which is what the trigger paragraph calls closest. It tests no perception and no region; the paper must scope the claim (section 5).

The no-fit case's last point, that determinised planners already match TAMPURA on B (MLO 0.65, WAO 0.70 against 0.66, survey), stands next to the following. Their MLO and WAO determinise TAMPURA's learned model inside TampuraPolicy (TP/solvers/mdp_solver.py:186-193); ours has no learned outcome model and no outcome sampling. Where it lands against 0.66 is open (ESTIMATE: near the determinised rows), and its per-step time against their 21 ± 13 s (Table II, survey) is open too (ESTIMATE: seconds, UNVERIFIED).

**Their contingent_policy is already in this slot** (the review's objection 5, conceded). ContingentPolicy samples once (TP/policies/contingent_policy.py:22-26), writes their spec as PDDL in which every action is split into one deterministic action per outcome combination (TP/spec.py:453-492), plans with symk and executes the first action, replanning every step (contingent_policy.py:28-47). With the differences in the table above (no unstack, the support's pose gate, the pull as an optimistic sense), mode S would plan over their preconditions with an optimistic outcome, from their abstract belief: close to the same thing. What differs is Fast Downward instead of symk, our action costs (theirs are 0, :30) and the domain's form. A tool_use result therefore says something about SB only as the difference against contingent_policy, run as the control on the same seeds (it is registered, TP/policies/__init__.py:18, and symk ships with their planner, TP/solvers/symk.py:36, 58). Two cautions: ContingentPolicy has no goal test, unlike TampuraPolicy (tampura_policy.py:77-80), and when symk finds no plan it returns a random applicable action (contingent_policy.py:40-42), which after a finished tower could undo it (UNVERIFIED whether that occurs). C4 claims only that difference.

**The sensing contrast** ("sensing against non-prehensile funnelling") needs a camera the task withholds. Appending an observe schema for both arms would change their published task B and fail G13's arm T check, which rejects any schema of ours in arm T's spec (tampura_bridge/g13_runtime.py:158-159). The first version's sketch (an observe(o) that renders the wrist camera over the believed mean and collapses the particles, TE/tool_use/env.py:150-151; the alpha 0.2 particle bodies in both worlds, :198, 282, 588, whose rendering is UNVERIFIED) stays a later option, not before the deadline (W10 (b)).

**Effort, when it is in scope:** 4 to 6 days for blind tool_use with contingent_policy as the control, 20 seeds per arm locally (ESTIMATE). TAMPURA takes about 3.4 min per episode at the paper's per-step time (9.7 steps at 21 s; survey section 7), about 70 min serial per repetition. On this laptop the class_uncertain probe measured 66.5 to 139.8 s per step against the paper's 28 s (class_uncertain/STATE.md:52-58), so local tool_use runs may take 2 to 5 times as long (UNVERIFIED for tool_use).

### 3.2 class_uncertain (the active plan, under the no-object-model rule)

**Their system for this task (READ):**
- World: three YCB objects and a bowl, mass 0.1, gravity -10, 2000 settle steps (TE/class_uncertain/env.py:301-304, 334-337).
- inspect: moves the arm 0.1 m above the object and returns the simulator's label (:141-177).
- pick: grasp IK on the sim world's pose of the body and the kinematic pick, then a ball breaks with probability 0.85 (:180-229, 37).
- drop: 0.1 m above the bowl, opens, then steps 200 times (:232-264).
- Belief: uniform class prior, one-hot after an inspect, on(o, bowl) from drop's arguments, broken from the observation (:44-129).
- Reward: every possible fruit in the bowl and nothing broken (:466-472).

**SB in mode S.**
- A class extension in M8's style: (possible_fruit ?o) and (is_fruit ?o) as K-literals.
- inspect is a sense whose optimistic outcome is "not a fruit", the outcome that frees the object from the goal.
- pick is gated on a known class, as obj_pose_known gates a pick on a known pose: H3's pattern, M8's POD justification (PAPER_AUDIT.txt:4467-4469) with class for pose.
- drop goes to the bowl region.
- The literals come from their abstract belief (TE/class_uncertain/env.py:107-129), declared.

Expected policy: inspect each object, then pick and drop each fruit, so 3 + 2k steps for k fruits, also the best their model allows (skipping an inspection risks the 0.85 break, :37, 226-227, and broken is absorbing in the reward, :470-472). Success should then match TAMPURA's near-ceiling (ESTIMATE). The informative numbers are steps and per-step time against their 6.44 steps and 28 ± 26 s (survey section 1).

**The conflict with the no-object-model rule** (BRIEF.md, "No prior object models"). Their pick takes grasps from the saved library (grasp_mode "saved", TE/class_uncertain/env.py:272-284) and the object's pose from their sim world by body id (:153, 190). "Their controllers" therefore means object models in execution, for both arms, and the BRIEF's deviation in TAMPURA's favour turns symmetric, against the rule for our arm. Options are in W9.

**The route hold.** class_uncertain/STATE.md:30-36 holds that plan's Route phase until this document's final verdict. Nothing in that verdict decides the class_uncertain route. L2's per-step shell (1.5) is one candidate for a per-step route, and under the no-object-model rule their pick on our arm would carry their saved grasps and their sim-world poses by body id (above), which that plan's deviations D-1, D-2 and D-7 already weigh (class_uncertain/STATE.md:87-119). That judgement is the plan's, not this document's. The hold is released (section 12).

**Caveats (READ):**
- The break draw uses Python's global random (TE/class_uncertain/env.py:226), which both policies also consume (TampuraPolicy calls random.choice, TP/policies/tampura_policy.py:168). Seed for seed therefore pairs the scene, not the in-episode draws.
- A drop without an IK solution returns None as the state (TE/class_uncertain/env.py:265-269), so env.state becomes None (TP/environment.py:65). The next execute_fn that touches it would fail, on either arm (consequence UNVERIFIED).

### 3.3 find_dice (what changes against today's harness, and for BF#63)

**Mapping (mode R):**

| SB plan step (test_full_pipeline.py HEAD) | their action (TE/find_dice/env.py) | arguments | preconditions, theirs and M8's | note |
|---|---|---|---|---|
| move + pick(cup) (:2037, :2323) | pick(o, g) (:925-942) | o by the identity map; g = the plan's ?g, one of their stored grasp symbols (2.6) | theirs: not moved(o), not holding, known-pose(o), object-grasp(o, g) (:929-933). M8's: handempty, at_config, clear, obj_at_boxel_KIF, obj_at_boxel, obj_pose_known, kin_solution (domain :249-255) | their motion and IK replace ours; moved-once is a delta (W8) |
| move + place(cup, free boxel) (:2536) | place(o, g, p) (:943-961) | p from SB's boxel (2.6), added with object-pose(o, p) | theirs: holding(o), at-grasp(o, g), object-pose(o, p) (:947-951) | kinematic; their belief records p (:462-466) |
| move + place_hiding(cup, free boxel) | place(o, g, p) | as place | as place | our executor already treats place_hiding as place (domain :316-321) |
| stack(o, on_obj) (:2778) | none | | | excluded from the L2 domain, and its stub raises (whether holding-goal runs ever ground it is UNVERIFIED) |
| move to a sense view + sense(die, region, q) (:2242) | look(die, caster, q_home) (:962-977) | ?o2 = the region's caster (2.9 (f)); q_home, added with looking-conf(caster, q_home) (2.6) | theirs: looking-conf(?o2, ?q), not known-pose(?o1), known-pose(?o2), not holding (:967-971). M8's sense: handempty, at_config, sense_view, view_clear, not obj_at_boxel_KIF, boxel_fits (domain :177-191) | the hand-empty rules agree; a die their belief already knows makes the look inapplicable (2.9 (c)) |
| observe(o, q) (:2278) | none | | | W7 (a): no observe in the L2 domain; their look cannot stand in, since it needs an object of unknown pose as ?o1 (:969) |
| move + pick(die) | pick(die, g) | as pick | needs known-pose(die), set by the look that showed it | |
| move home | go-home (:978-989) | | holding, not at-home (:982-984) | the at-home quirk (:563-581) |

Three domain deltas come with it (H3, each with its entry):
- No observe (W7 (a)): a seen object's pose counts as known, since their pick plans on their belief's exact pose (:368-375).
- Moved-once: their pick requires not moved(o) (:930), so the same precondition goes into our pick (W8). In run 2, 3 of our 57 successes placed some cup twice (119 r0, 119 r1, 137 r1; review_probe/recheck_bf63.txt, item 4); W8 removes those second relocations, and how those plans change is unknown.
- Every sense is a look from home: our eye exists only with the arm at home, so each region's sense_view set (domain :56, 182) becomes {q_home}. q_home is already one of our sense views (view__q_home, tools/episode_metrics.py:34). The delta is the bridge's --sense-over-region off (tampura_bridge/run_bridge_on_finddice.py:168-173) plus a sense_view set restricted to that view.

**What passes from plan to execution.** The object, the grasp symbol and the placement pose are the plan's (2.6). Our planned motion and the planned arm configuration are not: their execute_fn plans its own motion and computes its own configuration by IK (TE/find_dice/env.py:368-388, 445-457). Our dispatcher re-plans motion at execution today too (HEAD :2044-2056), but G3 requires its goal configuration to equal the planned one (PAPER_AUDIT.txt:3336-3338). Under L2 that clause cannot hold, and G3 compares the executed action and arguments with the planned ones instead (section 4, H2 and G3). The first version of this paragraph said the grasp passed unchanged; it did not, since the grasp came from their stream. With the grasp-symbol stream it now does.

**Today against step-wise:**

| | L0 today (BF#63) | L2 |
|---|---|---|
| physics | D9: gravity -9.81, masses, inertias, frictions, solver iterations, a finger gear constraint, a settle (policy.py:65-113) | none of ours; their world is never stepped (the hook count, 2.3) |
| execution | our physical pick, carry and place | their kinematic pick and place (panda_env_utils.py:927-1034) |
| motion planning and IK | ours | theirs, inside each execute_fn |
| grasps | ours (M9, top-down) | their five stored grasps per object, chosen by our planner (2.6) |
| sensing | a render after every action; the die found by the refresh render after its cup is lifted, in 57 of 57 BF#63 successes (BF#65, PAPER_AUDIT.txt:9166-9176) | only their images: the initial one and each look; main()'s other renders gated (2.3) |
| step budget | the whole episode is one step | 20 actions, their vocabulary |
| score | terminal readback: pads >= 0.5 N, joints at home (scoring.py:23-69) | BF#36's world-state test after every step and at the end; their reward beside (W6 (b)) |
| their at-home quirk (home_execute_fn returns conf = DEFAULT_ARM_POS even when planning fails, TE/find_dice/env.py:563-581; BF#35 at PAPER_AUDIT.txt:7387-7393) | theirs only | both arms, caught by the world-state test |

**What it would mean for BF#63's results.**
- BF#63 stays as measured. It is the system-level comparison: our whole pipeline with its own physics against TAMPURA in its own environment. An L2 run is a second protocol beside it, on new scenes from the same generator and harness (tools/gen_scene_eval.py), with arm T re-run beside arm O' (W12).
- **Indicator** (MEASURED: bf63_step_equiv.txt, review_probe/recheck_bf63.txt; run 2's arm O counts mapped onto their vocabulary as picks + places + senses + observes + 1 go-home):
  - our successes need a median of 8 actions against TAMPURA's 5;
  - 2 of 57 need more than 20 (s101 r1: 54; s139 r1: 69), with or without our observes (without them 34 and 38), and 9 need more than 15; recounted under the budget, the pairs move from 18 to 9 to 17 to 10, p = 0.25 (1.7; l2_power.txt);
  - by cup count, ours against TAMPURA's medians: 1 cup 6 and 5, 2 cups 5 and 5, 3 cups 12 and 6, 4 cups 8 and 5, 5 cups 12 and 11;
  - mean return over the 76 pairs: ours 0.592, TAMPURA's 0.530 (over each arm's counted episodes 0.585 and 0.530);
  - 8 successes dispatched no sense (106 r0, 114 r0 and r1, 125 r0, 129 r1, 136 r0 and r1, 137 r0). Under W3 (a) each needs one more look, and the mean return becomes 0.583 (0.590 over the pairs);
  - 7 successes picked more than cups + 1 times, and 3 placed some cup twice (the moved-once delta above).
- **Why the indicator can move both ways:**
  - The two longest successes are not physical pick misses: both picked the die at the first try with one carry (pick_tries 1, carries 1 in their records; `bf63_long_successes.py`, this folder). Their extra dispatched picks come with as many observes and look moves:
    - s101 r1: 23 picks, 20 observes, 20 look moves, 43 plan calls;
    - s139 r1: 33 picks, 31 observes, 31 look moves, 64 plan calls.

    That is the pattern of M8's pose-gated pick turning into another look, which BF#65 (e) describes for scene 124 (PAPER_AUDIT.txt:9221-9226). That it is the mechanism here is UNVERIFIED, since the run logs were not read. Under their controllers and W7 (a), a seen object's pose counts as known and no commit margin applies, so such loops might not arise; that rests on the unverified mechanism, since the arithmetic alone leaves both above 20 without observes. Their kinematic pick also cannot miss once IK and a motion plan exist (TE/find_dice/env.py:368-397).
  - Observes have no counterpart (W7). Without them the maximum is 38 and the mean return 0.600 (0.608 over the pairs).
  - Our free refresh renders vanish, so the die must be seen by a look. In 49 of the 57 successes a planned sense ran after the cup was lifted (the planned sense of its shadow, BF#65, PAPER_AUDIT.txt:9166-9171), and register_new_detections registers a body seen outside the sensed region as a discovery, which G15 allows (:3472-3477). The other 8 need one more look each (above).
  - But the registry's other render-fed paths would then run only at looks: the full-registry sweep, sweep_all_fragments (execution.py:2423-2424, provenance channel sweep_render), and the lost-caster retirement, retire_lost_objects (:2322-2323, channel lost_caster_render), besides world_integrity_check (HEAD :1600). G5 lists both channels with line numbers that have since drifted (PAPER_AUDIT.txt:3349-3351). That is risk R2.
- **Our failure modes:**
  - BF#65's root cause, no hiding region under a cup (shadow_calculator.py:226-236 as BF#65 cites it, PAPER_AUDIT.txt:9155-9165), lives in our registry and stays, with its cases (a) to (c), unless option 1 is built (1.7).
  - Case (d), scene 104, came from D9's settle bringing the die into view (:9063-9066, 9204-9214). It cannot occur in that form, because their world never steps; a die that shows 1 to 5 pixels is now case 2.9 (c).
  - Case (e), M8's look strikes on a far cup (:9215-9226), depends on W7.
- **TAMPURA's side is the same in both protocols:** most of its failures are repeated looks at one object until the budget runs out (eval2/REPORT.txt, per-scene table); on scene 131 it repeated one pick (:49); its crash, a ZeroDivisionError in print_F (PAPER_AUDIT.txt:9076-9087), is its own.

### 3.4 puck_slide

The full argument is archive/tampura_bridge_plan_2026-10-25/puck_slide/ARGUMENT.md. Its design keeps our arm's push physical in their world ("ours would be physical throughout (BF#37)", its lines 61-68), so puck_slide is not an L2 task in this document's sense, and nothing here bears on its decisions.

### 3.5 slam_collect

The full argument is archive/tampura_bridge_plan_2026-10-25/slam_collect/ARGUMENT.md. It runs their environment, controllers, observations and reward, with our estimator, fluents, domain and planner choosing one of their actions per step (its line 15): the L2 shell in mode S, with no PyBullet. Its deviation D-6 makes a world-state test primary with their reward beside it (its line 36), as W6 (b) now does here. Its ranking and decisions are its own.

## 4. Hani's rules: what this direction relaxes and keeps

| rule (where) | under L2 | why the change is worth it | what it costs the claims |
|---|---|---|---|
| BF#35, one environment and one criterion (PAPER_AUDIT.txt:7364-7416) | KEPT: one rollout, executor, belief update and success test for both arms. Not "only the decision maker differs": O' brings its own perception, look configuration, placement poses and kinematic filter (V1 to V5) | it is the decision this direction serves | each difference declared (2.10) |
| BF#36, B9 (:7418-7505) | NOT generalised. L2 drops all three trap resolutions (:7460-7470): (i) their plan_motion runs inside their execute_fn, where B9 kept our motion planner; (ii) their attach by name (TE/panda_utils/panda_env_utils.py:963), where B9 attached only the pinched body; (iii) identity by our planner's symbol, which B9 ruled out. It keeps B9's no physics step (5) and geometric checks (6) (:7455-7459) | their action schemas take symbols, not paths or pinches; that is what lets their step budget and belief apply per step | our motion planner, finger rule and identity by pinch are not exercised (N2); trap (ii) is shared by both arms and caught by the world-state test (W6 (b)) |
| BF#37 item 1, our arm's execution physical (:7510-7517) | RELAXED on arm O'; kept on our scenes and in BF#63 | physical against kinematic is the largest asymmetry, and item 1's goal is met (BF#38; BF#63 run 2: 57 carries, 0 losses, :8992-8994) | no physical claim from the L2 runs (N1) |
| BF#37 item 2, one world-state test primary, their reward beside (:7518-7523) | KEPT under W6 (b), now recommended; W6 (a) would reverse it | | none under W6 (b) |
| H1, no welds or constraints (:3256) | KEPT for our code; D9's gear constraint (policy.py:99-113) leaves arm O' | | none |
| H1, no teleports of task objects or the robot (:3256) | RELAXED for their executor, on both arms (the attach resets the held body each waypoint; the arm moves by resetJointState; :7371-7378) | it is the execution model TAMPURA's numbers were measured with | "no teleports" does not describe arm O' (N3); see #P1 |
| H1, no ground-truth reads feeding planning, perception or belief update (:3256-3259) | KEPT for our code. Their executor reads true poses for both arms (TE/find_dice/env.py:71-73; TE/class_uncertain/env.py:153, 190). The sim-world channel, shared: their motion planning runs in their sim world, built from the scene's true poses (TE/find_dice/env.py:842-848), where set_sim moves only objects their belief has seen (:102, 129-130, 135-140), so an unseen die is an obstacle at its true pose and a pick or place can fail because of it; SB learns of the failure through its own sensors, never of its cause | it is their system, the same for both arms | declared; every silent failure logged with the bodies in collision (2.9 (b)); whether it occurs UNVERIFIED |
| H1, no ground-truth reads feeding success scoring (:3256-3259) | KEPT under W6 (b): the primary test reads the executing world by geometry and joint readback, not their belief; their reward, which their execute_fns fill from world.poses and the attach, is reported beside it. RELAXED under W6 (a) | | none under W6 (b) |
| H1, no reads of their belief or world internals feeding a decision | KEPT on find_dice (the contract and the disagreement counts are evaluation side). RELAXED on tool_use and class_uncertain when they are in scope, every read declared and counted | those tasks have no other observation channel (2.5) | "SB never reads TAMPURA's belief" holds on find_dice only (N3) |
| H2 and the no-post-processing rule (:3260-3264) | KEPT for the action and its arguments: the executed object, grasp and placement are the planned ones (2.6). CHANGED for the arm configuration: their pick and place take none (TE/find_dice/env.py:925-961) and their IK computes it, so the planned ?q is a witness only (V7) | the grasp-symbol stream removes the one substitution; the configuration is not an argument of their action | our IK and motion planner are not tested on their tasks (N2); G3's clause changes (below) |
| H3, small POD deltas (:3265-3269) | KEPT on find_dice: no observe (W7), moved-once (W8), sense from home only, each with its entry. NOT KEPT by mode S on tool_use: its domain would be new, in M8's form but not a small M8 delta (M8's pick(?o ?b ?g ?q), domain :242-256, has no counterpart) | each find_dice delta is a precondition in the POD pattern; one is TAMPURA's own rule, one its action set | a tool_use domain needs its own entry as a new domain (not in the minimal version) |
| H4, seed for seed, their files and criterion, never edit their tree (:3270-3273) | KEPT on find_dice. The tool_use camera variant would change their task B and fail G13's arm T check (g13_runtime.py:158-159): W10 (b) | | none |
| H5, H6 (:3274-3277) | KEPT; contract aborts are recorded as aborts and count as arm O' failures (2.9 (d)) | | none |
| G1, world writes only on the allowlist (:3285-3313) | KEPT for our import graph (tools/bridge_gates.py:77-78, 226-247). The allowlist shrinks only once L0 is retired: while BF#63's protocol runs, D9's code stays on the graph. Their execute layer writes the world during arm O' as during arm T, outside the graph | | none |
| G3 (:3332-3344) | CHANGED: their RolloutHistory's actions are the executed ledger; the step executor logs (plan id, step) per returned action; executed action and arguments must equal the planned ones; the clause "goal configuration equal to the planned one" (:3336-3338) is dropped for arm O', declared. Their arm moves by resetJointState, so the motor hook sees none of their motion, and our move_robot_smooth is a stub | | rewritten gate text, a BF# entry before code |
| G6 (:3361-3373) | CHANGED: no terminal observation. The store writer is our only writer of their action inputs and adds object-pose and looking-conf entries only; a positive control shows that no entry it can add changes get_reward, which reads store.certified (TP/spec.py:141). stepSimulation calls on the executing client are counted by the existing hook (tampura_bridge/gate_hooks.py:238-257) and asserted 0 for the whole episode | | as for G3 |
| G13 (:3437-3447) | KEPT as written under W11 (a): the policy is instantiated directly, as BoxelBridgePolicy is (:3443-3444), no registration is added, and the runtime check that rejects any class of ours in their registries (g13_runtime.py:134-137) passes. Arm T's timed get_action (tampura_bridge/timed_policy.py:37) also runs the read-only per-step world-state test, outside its timed span; its __dict__ still holds only __init__ and get_action. Under W11 (b) G13's text and check change first | | none under W11 (a) |
| G14 | CHANGED: the hooks guard our code while get_action runs, not their execute_fn | | gate text |
| G8, G10, G11, G12, G18 to G21 | KEPT. G10 and G11 pin main()'s planner in mode R and need a mode S form later (planner type, generated domain hash, goal equal to their reward). G12 stays as the reported reward criterion beside the world-state test. G18: our set-up runs inside the first get_action, as their stream sampling does (TP/policies/tampura_policy.py:109-115). G20 holds: every look SB issues is from home, so every render is the D4 eye's (their look renders from look_conf, TE/find_dice/env.py:528-541) | | none |
| #P1, no weld, physical grasp (:129-146) | NOT COVERED on arm O': it is carried by a per-waypoint pose reset of the held body (TE/panda_utils/panda_env_utils.py:611-639), the class of mechanism #P1 removed from our pipeline (the "telekinetic attachment", :138-143) | it is their executor, for both arms | the paper's #P1 claims are scoped away from the L2 runs (N1) |
| #P5, their controllers (:9354-9372) | NOT ANSWERED: #P5 recommends their grasp SAMPLING with our physical execution and our contact verification, and records that their kinematic executors conflict with #P1 (:9365-9370). L2 takes the kinematic half on arm O', for the protocol, and their grasp samples too (2.6). #P5 stays open for our pipeline, its recommendation unchanged | the protocol, not #P5, is the reason | none for #P5; stated in the BF# entry |
| no bridge-only tuning (Hani's rule) | KEPT: the deltas follow TAMPURA's action rules and vocabulary or our eye's one view, and are declared before any run; nothing is tuned after an eval; a perception-miss rate is reported, never tuned away for find_dice alone (R14) | | none |
| no prior object models on class_uncertain (BRIEF.md, 2026-11-06) | IN TENSION: their pick carries their models (W9) | | see W9 |

**The dial, said out loud.** Hani's request has two terms: "almost run their system entirely" and "wiring as much of sb into their system as possible". They pull apart on execution. B9 sat nearer the second: our motion paths, our finger rule and identity by pinch on their execute layer. L2 sits nearer the first: on arm O', SB keeps perception, registry, regions, domain, planner and every what, where and order decision, and gives up grasp generation, motion planning, the finger rule and identity by pinch. That split matches what Hani said on 2026-11-06 for slam_collect: "we get the same actions as they do and same env and perception. how we use their perception to come up with a world model and what luents we have and how we plan is our bussnis." (class_uncertain/STATE.md:204-206; slam_collect/ARGUMENT.md:9). Whether it carries over to find_dice is his call (W1).

## 5. What the paper could claim, and what it could not

**Could claim** (if the results support it):
- **C1.** On TAMPURA's find_dice, with TAMPURA's environment, physics, executor, belief update, step budget and success test shared, and the deviations V1 to V16 declared, SB scores X against TAMPURA's Y: success, discounted return (the same metric as their Table I, not numbers comparable with Table I's), and per-step time as their Table II reports it, paired on new scenes from their own generator.
- **C2.** With the executor, budget, sensor and score shared, the difference belongs to SB's perception, belief representation and planner together, our kinematic filter included (V5), against TAMPURA's learned model and planner. Not to the planner alone, since the perception differs too (V1, V2); not to a model of where the die hides (BF#65, PAPER_AUDIT.txt:9266-9272). Withdrawn if W3 (b) is taken (V16).
- **C3.** Withdrawn as a measurement. Beside BF#63, arm O against arm O' on the same scenes is described, not tested, unless a paired O against O' test is pre-registered with its own N and power, which BF#63's 40 scenes cannot give (1.4).
- **C4.** On tool_use, only as a difference against their contingent_policy on the same seeds (3.1); not before the deadline.
- **C5.** One per-step shell for any task with a registered env; mode R for find_dice only; each further task needs its own domain and translation table.

**Could no longer claim from these runs:**
- **N1.** Physical execution on TAMPURA's tasks; #P1's claims (no weld, physical grasp, PAPER_AUDIT.txt:129-146) do not cover arm O'. The carry results stay on our scenes and in BF#63.
- **N2.** Our grasping, force-based verification, motion planning, finger rule and identity by pinch on their tasks.
- **N3.** "No teleports" on arm O'; "no reads of TAMPURA's belief" on tool_use and class_uncertain.
- **N4.** Anything about perception or regions on tool_use and class_uncertain.
- **N5.** A no-object-model result on class_uncertain, unless W9 (b).
- **N6.** BF#63 as the protocol-identical comparison. It becomes the system-level one, beside L2.

## 6. Effort, order of work and campaign design (all ESTIMATES)

If Hani builds L2 (W1), the minimal version is mode R on find_dice with W3 (a), W4 (a), W6 (b), W7 (a), W8 (a), W11 (a), W12 (a) and W13 (a).

| step | work | working days |
|---|---|---|
| 1 | a BF# entry before code: the rules as section 4 states them, the deviation list V1 to V16, the campaign's pre-registration (below); BF#36's S1 census on one arm O episode (PAPER_AUDIT.txt:7494-7496) | 1 |
| 2 | the mode R harness (2.3, 2.6, 2.9): policy, step executor, sense wrapper, gated renders, geometric checks, action map with the grasp-symbol stream and the failed-binding set, store writer, contract with abort classes, the per-step world-state test for both arms; gate rewrites (G3, G6, G14; G13 as written under W11 (a)); smokes on find_dice_simple (one die in view, pick then go-home; survey section 5), then one generated scene headless and in the GUI | 7 to 9 |
| 3 | review pass 1, with the cheat, POD, comparison-validity and feasibility lenses of the #P4 review gates (PAPER_AUDIT.txt:3521-3528), on the diffs and the smokes; fixes | 1 |
| 4 | the find_dice deltas (W7, W8, sense from home); local runs on a handful of generated scenes under the pipeline lock; abort counts by class, silent failures and 1-to-5-pixel dies reported; fixes | 3 to 4 |
| 5 | the campaign: new generated scenes, one repetition per arm, both arms back to back on the same nodes (BF#63's design, P4_LOCAL=1), N and the test fixed in step 1; analysis. Needs Hani's approval of that run alone | 1 to 2 (cluster wall about 5 h for 200 scenes) |
| 6 | review pass 2 on the campaign report, before any number is quoted | 0.5 to 1 |

- **Total: 14 to 18 working days**, against 20 weekdays from Monday 11-09 to Friday 12-04. The first version's 9 to 13 assumed weekend work and left out steps 1, 3 and 6 and most of what 2.3 now lists.
- **Stop rules,** counted from L2's first working day S: if find_dice_simple and one generated scene do not run end to end headless by S + 5 working days, fall back to W3 (b) at once, with C2 withdrawn (V16); if not by S + 7, stop, and record why in the BF# entry.
- **Pre-registration (step 1):** primary test, the exact two-sided McNemar on (O', T) pairs by scene at alpha 0.05, success by the world-state test; N fixed beforehand (200 scenes give power 0.78 if run 2's discordance and split held, l2_power.txt); discounted return and per-step time described beside; aborts counted as O' failures and reported by class; arm O on the same scenes as description only (C3).
- **Not before the deadline, in any ranking:** class_uncertain under L2, tool_use with its control, the tool_use camera variant, and puck_slide and slam_collect under this harness (their own arguments rank those).

## 7. Risks

- **R1, inversion of control.** main() is a loop of over 2,000 lines with local state (HEAD :692 to beyond :2803). Running it in a worker thread with a strict handoff should keep one PyBullet caller at a time, but PyBullet across threads, and the GUI mode in particular, is UNVERIFIED. The stubs' return contracts are now read: execute_pick returns PickResult(held_body_id, config, touched) (execution.py:77, 1457; its annotation at :1011-1013 is stale), execute_place and execute_stack a configuration or None (:1505-1506, 1678-1680), handle_observe_action (status, lost) (:2689-2698); handle_sense_action (:2741) is wrapped, not stubbed. Mitigation: headless DIRECT runs for the campaign; a GUI run of one seed early.
- **R2, a registry fed by fewer renders.** Several registry paths assume a render after every action: the refresh render after a pick, the sweep (sweep_all_fragments, execution.py:2423-2424), the lost-caster retirement (retire_lost_objects, :2322-2323) and the integrity check (HEAD :1600). With images only at looks the registry can go stale between looks, and strikes or give-ups can misfire. Mitigation: W3 (b) as the declared fallback, which withdraws C2.
- **R3, their quirks become shared.** The at-home quirk (TE/find_dice/env.py:563-581); class_uncertain's None state after a failed drop (TE/class_uncertain/env.py:265-269); a find_dice pick on an object without a believed pose would pass None into grasp_ik (TE/find_dice/env.py:368-375). The contract catches the last before env.step, by aborting the episode (2.5).
- **R4, a leak from the contract or the per-step test.** Both read their side. Mitigation: neither result is ever visible to the planner, which a G2-style leak test asserts.
- **R5, the result.** The lead may shrink under L2 and weaken the headline, and at 200 scenes it may still not be significant (power 0.78 under run 2's rates, ESTIMATE). Mitigation: BF#63 stays, and L2 is declared before it runs as a second protocol with its own pre-registered test.
- **R6, tool_use read as "TAMPURA's contingent_policy with another planner."** Conceded (3.1); the control is the mitigation.
- **R7, time.** 20 weekdays to 12-04; L2's 14 to 18 would leave none for BF#65's option 1 or more scenes (1.7).
- **R8, the cluster.** Queue waits (BF#53 found 11 h) and the NFS volume (BF#63's slow hour, PAPER_AUDIT.txt:8946-8975). Mitigation: P4_LOCAL=1 and BF#63 run 2's stall probe.
- **R9, in-episode random draws are not paired, find_dice included.** Their IK restarts from random.uniform samples (TE/panda_utils/panda_env_utils.py:158-170, reached by grasp_ik and ik, :862-886), and BiRRT (:442-496) draws inside both arms' execute_fns; class_uncertain's break draw consumes the same global stream (3.2). The first version said find_dice's execute_fns draw nothing random after initialize; that was wrong. Mitigation: none without changing their run conditions; one repetition per arm on more scenes rather than repetitions of the same scenes.
- **R10, two find_dice protocols in one paper** can read as cherry-picking. Mitigation: both declared before their runs, reported side by side with what each holds equal.
- **R11, our code stepping their world by accident.** main() settles before its first render (HEAD :916-917), and other loops in the pipeline step the simulation (hold_at_config and the settle loops BF#36 lists, PAPER_AUDIT.txt:7455-7456). Mitigation: the adapter's no-op step, the existing hook's count of stepSimulation calls on the executing client asserted 0 per episode (2.3), and the S1 census.
- **R12, max_steps reached while main() is mid-plan.** The worker is then left blocked in a stub. It must be released and abandoned cleanly (a daemon thread whose run logger still closes), or the episode's records are lost.
- **R13, silent-failure loops.** Their execute_fns fail without a status (2.9 (b)). Mitigation: the failed-binding set plus F2's three-strike rule.
- **R14, perception misses more common than expected** (2.9 (c)). Mitigation: counted by the smokes before any campaign. If they dominate O''s failures, that is a result about our 6-pixel floor, reported as such and never tuned for find_dice alone.
- **R15, the sim-world channel.** Their execute_fns collide with objects their belief has not seen, at true poses (section 4, H1), for both arms. Mitigation: every silent failure logged with the bodies in collision; whether it occurs is UNVERIFIED.

## 8. Objections, with answers

1. **"This throws away half the system: physical execution."** Only on TAMPURA's tasks, and only in the L2 runs. The physical result stays on our scenes and in BF#63. ICAPS judges the decision layer, and #P6 records that a real robot is not needed for ICAPS (PAPER_AUDIT.txt:9375-9381).
2. **"On tool_use and class_uncertain this is Fast Downward on TAMPURA's belief, not SB."** Partly conceded. It is SB's decision layer (M8's form, POD semantics, optimistic determinisation, replanning), in the slot TAMPURA's own baselines occupy (TP/policies/__init__.py:12-18). Perception and regions are claimed only on find_dice (C4, N4), and on tool_use only the difference against their contingent_policy (3.1).
3. **"The paper already shows determinised planners match TAMPURA on B; one more adds nothing."** Their MLO and WAO determinise TAMPURA's own learned model inside TampuraPolicy (TP/solvers/mdp_solver.py:186-193). The closest of their own policies to ours is contingent_policy, which is why it is the control (3.1).
4. **"Reading their belief breaks H1."** H1 was written for a comparison in which our arm brought its own sensors. On tasks whose only observation channel is their belief, the literal is the observation. Every read is declared and counted, and on find_dice there is none.
5. **"Their executor attaches the named body even with the gripper off it (BF#36's trap (ii)); SB could exploit that."** Both arms share the executor, the contract keeps SB inside their preconditions, and the world-state test is primary for both (W6 (b)), so an attach without a pinch scores a failure for either arm.
6. **"Twenty steps penalise SB, which today runs unbounded inside one step."** That is the point: it removes an asymmetry in our favour. In BF#63 run 2, 2 of our 57 successes needed more than 20 of their actions, with or without our observes; recounted, the pairs move from 18 to 9 to 17 to 10 (1.7). Whether W7 (a) would remove those loops rests on a mechanism that is UNVERIFIED (3.3).
7. **"A look from home is not our fixed eye."** It is the same view (tampura_bridge/task_spec.py:66-75 measured the eye as their camera at DEFAULT_ARM_POS). It costs one step and an arm motion, as TAMPURA's sensing does. It is also a configuration arm T's sampler never produces (V2), declared, with its direction open.
8. **"Writing SB's values into their store is a write into their belief inputs."** The store is their action-argument interface, and their own samplers write it the same way (TP/spec.py:130-137). The writer may add object-pose and looking-conf entries only, each logged, and a positive control shows that none changes get_reward (section 4, G6). The stricter alternative is W4 (b).
9. **"Running main() in a thread is a hack."** It avoids refactoring a 2,000-line loop. The handoff is strict, the stubs sit at the seam B9 already chose, and BF#36's S1 census comes first. A step-function refactor is the clean version later (W13).
10. **"Two find_dice results look like cherry-picking."** Both are declared before they run, and each says what it holds equal. L2 is a second protocol beside BF#63, not its replacement.
11. **"Their look's observation uses true poses."** That is their belief, used for their own reward. SB estimates poses from its own perception for its decisions. Execution then uses their belief's (true) poses for both arms, declared (section 4, H1).
12. **"Why not run SB everywhere as a symbolic planner (mode S, L3), the cheapest option?"** On find_dice that would drop the semantic regions, the one thing the paper is about; mode S is for the tasks that have no camera.
13. **"Why now, with p = 0.12?"** Conceded: 1.7 ranks L2 after BF#65's option 1 and a larger scene campaign, which puts it after the deadline unless Hani ranks it first (W1).
14. **"On tool_use this is TAMPURA's contingent_policy with another planner."** Largely conceded (3.1): only the difference against it is claimed, and tool_use is out of the minimal scope.
15. **"L2 wires less of SB than B9 did."** Conceded (section 4, the dial): L2 follows the first half of Hani's request; B9 followed the second.

## 9. Decisions for Hani

Moved to section 12, at the end, as they stand after the review.

## 10. Files made by this agent, and what is left unverified

Files in this folder made by this agent:
- ARGUMENT.md: this document, revised in place after the review (the reviewed text is not kept separately: REVIEW.md quotes each claim it checked, and section 11 says what changed).
- bf63_step_equiv.py and bf63_step_equiv.txt: the indicator script and its output.
- bf63_long_successes.py: prints the two longest successes' record fields for 3.3 (run as `python3 -I -B bf63_long_successes.py <eval2 dir> 101:1 139:1`; output quoted in 3.3).
- l2_power.py and l2_power.txt (new in this revision): the exact McNemar values of the re-count and the power table of 1.7 and section 6.
- show.sh, grep.sh, outline.sh, grep_strategies.sh: read-only helpers for reading their tree, piped through `tr -d '\r'` into WSL bash.

The revision was drafted in this folder as ARGUMENT_rev.md and moved over ARGUMENT.md, so that file no longer exists. Outside this folder, three CR-stripped copies of the helpers (/tmp/wsb_show.sh, /tmp/wsb_grep.sh, /tmp/wsb_outline.sh in WSL) were written in the first session's first calls and were gone at the next call (WSL's /tmp does not persist here). Nothing else was written anywhere. In this folder but not this agent's: REVIEW.md and review_probe/ (the reviewer's), AUTHOR_BRIEF.md and REVIEW_BRIEF.md.

Ledger: DATA_LEDGER.md:13 (the coordinating session's row, uncommitted) covers this folder's documents and marks them never garbage. The helper scripts become garbage once this argument is final; the scripts with outputs that sections 1.7, 3.3 and 6 cite stay as evidence. Itemising these files and the reviewer's, and logging the helpers' deletion, is for the session that keeps them, since this agent may not edit the ledger.

UNVERIFIED:
- which code produced Table I's rows, and how the paper computes the return (gamma^t with t actions is the convention used here);
- PyBullet across threads and in GUI mode;
- the rate of pad-test disagreements;
- whether our kinematic stream accepts their grasp transforms (2.6);
- how often a die shows 1 to 5 pixels in their segmentation (2.9 (c));
- whether their motion planning fails on unseen objects at true poses (R15);
- whether scene 131's repeated picks were IK or motion failures (2.9 (b));
- the mechanism behind the two longest successes (3.3);
- whether ContingentPolicy undoes a finished tower (3.1);
- whether a close look can see behind an unmoved cup (V2);
- how TinyRenderer treats tool_use's alpha 0.2 particles;
- what follows a None state in class_uncertain;
- the cost of BF#65's option 1;
- the power figures' assumptions (run 2's discordance and split held on new scenes);
- every effort figure and expected result (ESTIMATES).

Settled since the first version, by the review's own reading: hook placements exist on tool_use (REVIEW.md row B26); find_dice's execute_fns do draw random numbers (row B43, now R9).

## 11. Review and answers

One entry per point of REVIEW.md, numbered as it numbers them: its verdict, its section 1 rows (the wrong claims W-1 to W-5, the misread entries M-1 and M-2, the partials, and the notes on confirmed rows), its section 2 numbers, its section 3 rules R1 to R16, its section 4 objections 1 to 9, its section 5 lists, its section 6 gaps 1 to 7 and its section 7.

### 11.0 REVIEW.md's verdict

"Survives with changes", for three reasons and one extension. Agreed on all four. The case for now: 1.7 answers it and concedes the ordering. The rules table: rewritten (section 4). The seams and main(): 2.9 and 2.3. The tool_use extension: 3.1, with contingent_policy as the control, and out of the minimal scope.

### 11.1 Citation table (REVIEW.md section 1)

Wrong claims about code:
- **W-1 (row C12).** Conceded: the execution.py numbers were copied from G5's text, which has drifted. The sweep is sweep_all_fragments (execution.py:2423-2424, channel sweep_render) and the retirement is retire_lost_objects (:2322-2323, channel lost_caster_render). Changed: 3.3, R2. G5's own text (PAPER_AUDIT.txt:3349-3351) is for the session that keeps the audit to correct.
- **W-2 (row B4).** Conceded: their look sampler puts the camera 0.2 to 0.3 m above the object (TE/find_dice/env.py:619-628), so looking-conf(cup, q_home) is a new value and fact, not one their stream would certify. Changed: 2.6, V2, the BF#35 row, objection 7.
- **W-3 (row C8).** Conceded: the grasp came from their stream, and our re-plan keeps the planned goal configuration (G3) while their pick computes its own. Changed: grasps are planned over their stored samples (2.6, 2.9 (a)); 3.3's paragraph rewritten; section 4's H2 and G3 rows. One part is held, with its reason: the configuration is not an argument of their pick or place (TE/find_dice/env.py:925-961), so no planned argument is replaced; what changes is G3's clause on the goal configuration (PAPER_AUDIT.txt:3336-3338), and that change is declared (V7).
- **W-4 (row B43).** Conceded: plan_workspace_motion restarts IK from random.uniform samples (TE/panda_utils/panda_env_utils.py:158-170), grasp_ik and ik call it (:862-886), and plan_motion reaches BiRRT (:442-496). Changed: R9, V8, 2.8.
- **W-5 (row C25).** Conceded: with only the listed stubs, main() still renders after actions at seven sites, and its goal check runs a force test that cannot pass in a never-stepped world. Changed: 2.3 gates the seven renders, makes the goal check geometric and neutralises the settle, behind --executor theirs and after BF#36's S1 census; 2.9 (g). Reading for the fix found two more contact-based sites the review did not list: carry_hold_end (HEAD :2194-2196), inert on arm O' with its slip switch off (execution.py:601), and the place-entry check inside execute_place (execution.py:563), which the place stub replaces (2.3).

Audit entries read against their own text:
- **M-1 (row D12, #P5).** Conceded: #P5 recommends their grasp sampling with our physical execution and contact verification, and says their kinematic executors conflict with #P1 (PAPER_AUDIT.txt:9365-9370); L2 takes the half it advised against. Changed: 1.6, the #P5 row.
- **M-2 (row D4, BF#36).** Conceded: L2 drops all three of B9's trap resolutions (:7460-7470). Changed: 1.6, the BF#36 row, the L1 and L2 rows of 2.1.

Partial:
- **B28.** Accepted: stack's believed pose is relative to a random particle of the support (TE/tool_use/env.py:177-179, 430-431). Changed: 3.1.
- **C14.** Accepted: M8's pick has seven preconditions. Changed: the tables of 3.1 and 3.3 list all seven (domain :249-255).
- **D6.** Accepted: BF#37 item 2 puts the world-state test first (PAPER_AUDIT.txt:7518-7523). Changed: W6 now recommends (b); the BF#37 rows; 2.2.

Notes on confirmed rows:
- **A4** (spec.py:141 adds store.certified to the reward's facts): the writer's limit and G6's positive control (2.6; section 4, G6).
- **A8** (the loop never stops early): SB returns no-op once main() has returned (2.2, step 2.6).
- **A16** (their PDDL is an all-outcome determinisation): 2.3's mode S and 3.1.
- **B3** (any pixel): V1 and 2.9 (c).
- **B9** (look needs NOT known-pose(?o1) and known-pose(?o2)): 3.3's table, 2.9 (c) and (f); W7 (b) dropped as infeasible.
- **B26** (hook placements exist): taken from the review and removed from the UNVERIFIED list (10).
- **C10** (the return contracts): 2.3 and R1.
- **C20** (G13 as built rejects any class of ours): 2.7, the G13 row, W11.
- **D10** (BF#63 does not call ours better): carried into 1.4.

### 11.2 Numbers (REVIEW.md section 2)

- **Unlike sets for the mean returns.** Accepted: the like-for-like values over the 76 pairs (ours 0.592, TAMPURA 0.530, today's harness 0.709) now lead in 1.3 and 3.3.
- **8 successes dispatched no sense.** Accepted: 3.3 (one more look each; 0.583, or 0.590 over the pairs) and 1.7, where they stay far under 20.
- **7 extra picks and 3 cups placed twice.** Accepted: 3.3, under the moved-once delta.
- **2 successes still above 20 without observes.** Accepted: 3.3 and objection 6 no longer say W7 (a) removes them, which rests on the unverified mechanism. The same fact gives 1.7's re-count: the pairs move to 17 to 10 whatever is assumed about observes.
- **9 to 13 days assumed weekend work.** Accepted: section 6 re-estimates 14 to 18 weekdays.
- **Local tool_use time.** Accepted: 3.1 now says 2 to 5 times the paper's, UNVERIFIED for tool_use.
- The other rows were confirmed and need no answer.

### 11.3 Rules check (REVIEW.md section 3)

- **R1 (BF#35).** Conceded: not "only the decision maker". Changed: 1.1, the BF#35 row, 2.10 (V1 to V5).
- **R2 (BF#36).** Conceded. Changed: the BF#36 row and 1.6; N2 now agrees with them.
- **R3 (BF#37).** Conceded. Changed: W6 (b) recommended; two BF#37 rows.
- **R4 (H1, no teleports).** Agreed; unchanged.
- **R5 (H1, scoring; the sim-world channel).** Conceded on both. Scoring: kept under W6 (b), relaxed only under W6 (a). The channel is real: SceneBelief's object_poses starts empty (TE/find_dice/env.py:102) and is filled only from observations (:129-130), set_sim walks only that dict (:135-140), and the sim world is built from the scene's true poses (:842-848). Changed: two H1 rows, 2.9 (b), R15, the note under 2.10.
- **R6 (H2, no post-processing).** Conceded for the grasp, which is now the planned one (2.6). For the goal configuration, partly held as under W-3: no planned argument is replaced, since their action takes none, but G3's clause changes and is declared (the H2 and G3 rows, V7).
- **R7 (H3, mode S).** Conceded: a tool_use domain would be new, not a small M8 delta. Changed: 2.3, 3.1, the H3 row.
- **R8 (G1).** Conceded: the allowlist shrinks only once L0 is retired. Changed: the G1 row.
- **R9 (G6, G13).** Conceded on both. G6 gets a positive control against get_reward; G13 holds as written under W11 (a), by direct instantiation. Changed: the G6 and G13 rows, 2.7, W11.
- **R10 (G20).** Agreed; unchanged.
- **R11 (H4, W10).** Conceded: the camera variant would change their task B and fail G13's arm T check. Changed: 3.1, the H4 row, W10's reason.
- **R12 (#P5).** Conceded (M-1).
- **R13 (#P1).** Conceded: a row added; N1 and section 1's costs name it.
- **R14 (no bridge-only tuning).** Agreed; the row now also covers a perception-miss rate (risk R14, section 7).
- **R15 (the request's own terms).** Conceded: L2 resolves the tension toward "their system entirely" and now says so (section 4, the dial), with Hani's slam_collect statement beside it; whether it carries over is his call.
- **R16 (no prior object models).** Agreed; W9 (c) kept, and the class_uncertain hold released (3.2).

### 11.4 Ranked objections (REVIEW.md section 4)

1. **The case for now.** Conceded in substance and answered in 1.7. L2's payoff needs BF#65's option 1 and more scenes first; the step-budget part of its question is answered now by the re-count (pairs 17 to 10, p = 0.25); a pre-registered design with a power statement is in section 6 (200 scenes, one repetition, power 0.78 under run 2's rates); the class_uncertain hold is released. The recommendation changes from "do it, minimal version first" to W1 (b). Changed: 1.4, 1.7, section 6, W1, W12.
2. **The rules table.** Conceded. Changed: section 4 (the rows of 11.3).
3. **The seams.** Conceded; each has a rule in 2.9: (a) grasps planned over their samples; (b) silent failures excluded at the next plan; (c) perception misses classed and counted; (d) aborts are arm O' failures, never gate failures; (e) placement z and orientation from our registry's pre-pick estimate, logged against the truth (the review proposed the held object's current pose; reading that pose from their world would feed a true pose into SB's choice, which H1 forbids); (f) ?o2 = the caster; (g) a geometric goal check. Abort counts from the smokes come before any campaign (section 6, step 4).
4. **The effort.** Conceded. Changed: section 6, 14 to 18 working days with the census, the gating, two review passes and no weekend work; stop rules at S + 5 and S + 7.
5. **tool_use against contingent_policy.** Conceded. Changed: 3.1, C4, W2 (b), objections 2, 3 and 14. Found while answering: ContingentPolicy has no goal test and falls back to a random applicable action (TP/policies/contingent_policy.py:40-42), a caution for its use as the control.
6. **C2 and C3.** Conceded. Changed: C2 restated with what is shared and what still differs; C3 withdrawn as a measurement (section 5).
7. **Comparability with Table I.** Conceded. Changed: 1.3 and C1 ("the same metric as their Table I").
8. **Undeclared deviations.** Conceded. Changed: 2.10, one numbered list V1 to V16, given in short in section 1, to be repeated in full in the BF# entry and every report.
9. **The indicator's corrections.** Accepted (11.2).

### 11.5 What fails, what survives (REVIEW.md section 5)

- **Does not survive as written:** the five rules rows and #P1 (section 4); 2.6 (a)'s look claim (2.6); 3.3's grasp claim, R9, R2's cites and 2.3's "unchanged" (3.3, R9, R2, 2.3); case point 4's "either reading is publishable" and C3 (1.4, section 5); case point 3's comparability (1.3); tool_use without its control (3.1); objection 6's "which W7 (a) removes" (objection 6, 3.3). Each is fixed or withdrawn where named.
- **Survives with changes:** each condition is met where named: the rules table (4); the seams (2.9); more scenes, one repetition and a pre-registered test with its power (1.7, 6, W12); a stop date (6); Hani's ranking before W1 (1.7, W1); mode R with gated renders and the geometric goal check (2.3); C1 and C5 narrowed (5); the effort re-estimated (6); the indicator corrected (1.3, 3.3); W4 (a) with grasps over their samples (2.6, W4).
- **Survives as written:** kept. R11 now says how the settle is neutralised and what is counted (2.3, R11), as the review asked; W7 (a) is argued as the review suggests, with (b) dropped.

### 11.6 Gaps against AUTHOR_BRIEF.md (REVIEW.md section 6)

1. No comparison with other uses of the days: 1.7.
2. No consolidated deviation list: 2.10.
3. No campaign design: section 6 (the pre-registration) and 2.9 (d).
4. No grasp rule and no silent-failure handling: 2.9 (a) and (b).
5. contingent_policy not discussed: 3.1.
6. Estimates and cites: no answer needed.
7. No DATA_LEDGER.md row: DATA_LEDGER.md:13 (the coordinating session's row, uncommitted) covers this folder's documents; itemising the helper and probe files, mine and the reviewer's, and logging the helpers' deletion once they are garbage, is for the session that keeps them (section 10).

### 11.7 Not checked by the reviewer (REVIEW.md section 7)

Still UNVERIFIED and listed in section 10. Two items of the first version's list are now settled by the review's own reading: hook placements exist (row B26), and find_dice's execute_fns draw random numbers (row B43).

## 12. Final verdict and the decisions as they now stand

**Final verdict: survives with changes.**

What survives: their framework runs any policy one action per step, and L2 removes the execution, physics, step-budget and scoring asymmetries that BF#63 must disclose (1.1, 1.2; kept as written by the review). The find_dice design survives in its corrected form: main()'s renders gated to looks, its contact checks made geometric or inert, the settle neutralised and the step count asserted 0, grasps chosen by our planner among their samples, and every seam of 2.9 given a rule. The rules are now stated as the audit states them: L2 relaxes BF#36's trap resolutions, BF#37 item 1 on arm O', H1's no-teleport clause, #P1's coverage and G3's configuration clause; it keeps BF#35, BF#37 item 2 and H1's scoring clause under W6 (b); it does not answer #P5.

What does not survive: the first version's recommendation to build it now. At BF#63's size it cannot tell a surviving lead from a shrinking one; BF#65 already bars crediting the regions with where the die hides; and its 14 to 18 working days would use the time that BF#65's option 1 and a larger scene campaign need, both of which its own payoff depends on. Also conceded: tool_use without contingent_policy as its control, C3 as a measurement, and comparability with Table I's numbers. L2 is an option for Hani, ranked after those two, which in practice puts it after 2026-12-04.

The class_uncertain plan's Route phase, held on this verdict (class_uncertain/STATE.md:30-36), is released: nothing here decides its route (3.2).

**Decisions for Hani.** If logged in the audit they take Q19 onward: the highest numbered question in PAPER_AUDIT.txt is Q18 (the lettered Q-A to Q-H are a separate series), and the class_uncertain plan also starts its questions at Q19 (class_uncertain/STATE.md:9-10), so whichever is logged second takes the next free numbers.

1. **W1, when to build L2.**
   - (a) Now: the minimal find_dice version from 11-09, 14 to 18 working days (ESTIMATE), before BF#65's option 1 and a larger scene campaign.
   - (b) After those two: report the re-count now (pairs 17 to 10 under their 20-step budget, p = 0.25); decide BF#65's option 1; run a larger pre-registered campaign on the resulting pipeline; build L2 after 2026-12-04, on the same scenes, as a declared second protocol beside BF#63.
   - (c) No.

   **Recommend (b).** Changed: the first version recommended building it now.
2. **W2, scope once L2 is built.**
   - (a) find_dice only.
   - (b) Plus tool_use, blind, with their contingent_policy as the control on the same seeds.
   - (c) Plus class_uncertain.

   **Recommend (a); (b) only with the control.** Changed: (b) now requires the control.
3. **W3, sensing on find_dice.**
   - (a) Their observation channel only: the initial image and the looks, with main()'s seven post-action renders gated to looks (2.3).
   - (b) Our render after every step, a declared deviation in our favour (V16), with C2 withdrawn.

   **Recommend (a); (b) only as the stop rule's fallback.**
4. **W4, continuous values.**
   - (a) Grasps chosen by our planner among their stored samples; placements at SB's free-space boxel's xy with the object's own resting z and orientation; looks from home (V2); all logged.
   - (b) As (a), with placements also chosen among their placement samples.

   **Recommend (a).** Changed: grasps are no longer picked by the translation layer.
5. **W5, reads of their belief.**
   - (a) None by SB on find_dice (outcomes from our sensors, disagreements counted); on tool_use and class_uncertain their literals, declared and counted, when those tasks are in scope.
   - (b) None anywhere, so those two tasks drop out.

   **Recommend (a).**
6. **W6, the primary success criterion.**
   - (a) Their reward on their belief for both arms, the world-state test beside it.
   - (b) BF#36's world-state test for both arms, after every step and at the end, so that it also gives a discounted return; their reward beside it (BF#37 item 2, PAPER_AUDIT.txt:7518-7523).

   **Recommend (b).** Changed: (a) would reverse BF#37 item 2 and relax H1's scoring clause.
7. **W7, M8 under their controllers on find_dice.**
   - (a) No observe operator in the L2 domain; a seen object's pose counts as known.
   - (c) M8 off.

   (b), observe mapped onto a look, is dropped: their look needs an object of unknown pose as ?o1 (TE/find_dice/env.py:969), and M8 observes objects already seen.

   **Recommend (a).**
8. **W8, their moved-once rule.**
   - (a) A declared domain delta (pick needs not moved).
   - (b) No delta; an inapplicable choice aborts as an arm O' failure.

   **Recommend (a).**
9. **W9, class_uncertain under the no-object-model rule.**
   - (a) Their grasps and poses through their pick: identical setup, models in execution for both arms, the no-model test confined to our perception.
   - (b) Our grasps from our renders, wrapped as their Grasp: no models for our arm, but their attach leaves grasp quality untested.
   - (c) Leave class_uncertain to the BRIEF's PLAN.md.

   **Recommend (c)**, with that plan's Route phase released now (3.2).
10. **W10, tool_use with a wrist camera** (an observe schema for both arms).
    - (a) After the blind variant, if time.
    - (b) Not before the deadline.

    **Recommend (b):** it would change their task B and fail G13's arm T check (tampura_bridge/g13_runtime.py:158-159).
11. **W11, arm O''s driver.**
    - (a) A bridge driver that instantiates the policy directly: no registration, G13 as written.
    - (b) Their run_planner.py with --planner semantic_boxels: G13's text and check change first.

    **Recommend (a).**
12. **W12, the L2 campaign's scenes and arm T.**
    - (a) New generated scenes, N fixed in advance (200 recommended: power 0.78 under run 2's rates, ESTIMATE), one repetition per arm, arm T re-run beside arm O' on the same nodes; about 5 h of cluster wall (ESTIMATE).
    - (b) BF#63's 40 scenes with two repetitions, as first proposed (power about 0.17, since the repetitions are near duplicates).

    **Recommend (a).** Changed. The run itself needs Hani's approval of that question alone.
13. **W13, inversion of control.**
    - (a) main() in a worker thread with a strict handoff, after BF#36's S1 census.
    - (b) Refactor main() into a resumable step function first.

    **Recommend (a).**
