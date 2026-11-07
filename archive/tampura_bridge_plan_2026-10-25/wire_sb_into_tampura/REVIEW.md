# Review of ARGUMENT.md (run TAMPURA's system, wire Semantic Boxels into it)

Status: written 2026-11-06 by one adversarial reviewer for Hani, on branch `tampura-bridge`. Read only over both trees: their tree read through `\\wsl.localhost\Ubuntu\root\tampura-work` and `wsl -e bash -c` with grep and sed only; nothing written under /root/tampura-work; no run of our pipeline or of TAMPURA. The author's two scripts and one script of mine were rerun read only (`python3 -I -B`, PYTHONDONTWRITEBYTECODE=1) with their outputs in `review_probe/`. Conventions as in ARGUMENT.md: `TP/x` is /root/tampura-work/tampura/tampura/x, `TE/x` is /root/tampura-work/tampura_environments/tampura_environments/x; ours relative to the repo; `HEAD :n` is test_full_pipeline.py at HEAD (the working copy carries another session's hunk).

## Verdict

**Survives with changes.** The direction is legitimate and most of its evidence holds: of the 108 citation rows checked below (about 230 file:line cites), five claims about code are wrong, two audit entries are read against their own text, and none is missing; every number of the author's BF#63 indicator reproduces exactly. TAMPURA's framework does run any registered policy step by step (TP/config/config.py:47-52, TP/policies/policy.py:105-153), and the L2 design would remove the execution, physics, step-budget and scoring asymmetries the argument lists. Three things keep it from surviving as written. First, the case for spending the next two to three weeks on it is not made: BF#63's lead is not significant (p = 0.12, and its two repetitions are close to one draw, PAPER_AUDIT.txt:9032-9042, 9123-9131), so a second protocol on the same 40 scenes cannot tell "the lead survives" from "the lead shrinks", BF#65 already bars crediting the regions with where the die hides (:9266-9272), and the document never weighs L2 against the other uses of those days (BF#65's option 1, more generated scenes, and the class_uncertain plan whose route phase is held on this verdict, class_uncertain/STATE.md:30-36). Second, the rules table misstates five binding items: #P5's own recommendation (:9365-9370), BF#36's trap resolutions (:7460-7470), H1's success-scoring clause under W6 (a) (:3256-3259), BF#37 item 2's criterion order (:7518-7523), and the no-post-processing rule where their grasp replaces the planned one. Third, the design leaves undefined the seams where arm O' would fail first: which of their grasp samples a pick uses, what happens on their silent IK or motion failures (TAMPURA's own last three actions on scene 131 were one repeated pick, REPORT.txt:49, cause UNVERIFIED), the contract abort when their belief knows the die before our perception does (any pixel, TE/find_dice/env.py:64-73, against our 6, perception.py:320), and how an aborted episode counts; and main() cannot run "unchanged" under W3 (a). The tool_use extension does not survive as written: in mode S it is close to TAMPURA's own contingent_policy (TP/policies/contingent_policy.py:19-47). With the corrections in section 5, the minimal find_dice version is a fair option for Hani to choose, not a default.

## 1. Citation table

Status: CONFIRMED (the code or record says what the document says), WRONG (what it says instead), NOT FOUND. Rows group cites that support one claim.

### A. TAMPURA's planner (TP)

| # | claim in ARGUMENT.md | cites | status |
|---|---|---|---|
| A1 | the rollout asks the policy for one action per step | TP/policies/policy.py:120 | CONFIRMED |
| A2 | env.step runs the schema's execute_fn | TP/environment.py:49-67, 62-65 | CONFIRMED |
| A3 | the belief is updated with the observation | TP/policies/policy.py:130 | CONFIRMED |
| A4 | the reward is computed on the abstract belief | TP/policies/policy.py:108, 138; TP/spec.py:140-143 | CONFIRMED. Note: spec.py:141 also adds store.certified to the facts the reward reads (matters for 2.6, see rules row R9) |
| A5 | planners are registered by name | TP/config/config.py:47-52 | CONFIRMED |
| A6 | every alternative in their repo is a registered planner | TP/policies/__init__.py:12-18 | CONFIRMED (seven, replay_policy included) |
| A7 | MLO and WAO are decision strategies of TampuraPolicy | TP/solvers/mdp_solver.py:186-193; TP/policies/tampura_policy.py:154-160 | CONFIRMED as code; that Table I used them is UNVERIFIED, as the author says |
| A8 | the rollout loop, its steps, the final add | TP/policies/policy.py:105-153, 106-108, 136, 153 | CONFIRMED; the loop never stops early, so a policy must return no-op after the goal (TampuraPolicy does, tampura_policy.py:77-80) |
| A9 | Policy.get_action signature | TP/policies/policy.py:93-94 | CONFIRMED |
| A10 | samplers add values and certified facts | TP/spec.py:130-137 | CONFIRMED |
| A11 | applicable_actions | TP/spec.py:176-191 | CONFIRMED |
| A12 | nothing checks preconditions between get_action and env.step | TP/policies/policy.py:120-130 | CONFIRMED |
| A13 | TampuraPolicy falls back to a random applicable action | TP/policies/tampura_policy.py:161-168, 168 | CONFIRMED |
| A14 | TampuraPolicy samples its streams once per episode | TP/policies/tampura_policy.py:109-115 | CONFIRMED |
| A15 | RandomPolicy samples once | TP/policies/random_policy.py:18-22 | CONFIRMED |
| A16 | ContingentPolicy samples once and replans with symk on their PDDL | TP/policies/contingent_policy.py:22-26, 19-47 | CONFIRMED. Their PDDL is an all-outcome determinisation (one action per outcome combination, TP/spec.py:453-492), which bears on objection 5 |

### B. TAMPURA's environments (TE) and configs

| # | claim | cites | status |
|---|---|---|---|
| B1 | initialize images the scene at DEFAULT_ARM_POS | TE/find_dice/env.py:853, 853-857 | CONFIRMED |
| B2 | their look moves, images, steps no physics | TE/find_dice/env.py:523-547, 528-547 | CONFIRMED (apply_sequence with sim_steps 0) |
| B3 | their pick plans on the belief pose, which is the simulator's pose once seen | TE/find_dice/env.py:368-375, 368-397, 71-73, 57-75, 70-73 | CONFIRMED. Also: obs_from_camera_image adds every body with at least one pixel in the segmentation (:64-73) |
| B4 | stream schemas; SB adds "the fact their stream would certify" (2.6 a) | TE/find_dice/env.py:893-921 | Block CONFIRMED. The claim for looks is WRONG in effect (W-2 below): looking-conf is the predicate (:900), but their sampler puts the camera 0.2 to 0.3 m above the object (:619-628), so it can never yield DEFAULT_ARM_POS, whose eye is at z 0.588 m (tampura_bridge/task_spec.py:70) |
| B5 | saved grasps | TE/find_dice/env.py:39, 756-769 | CONFIRMED |
| B6 | client registration order | TE/find_dice/env.py:695-696, 833-839, 842-848 | CONFIRMED |
| B7 | pick and its not-moved precondition | TE/find_dice/env.py:925-942, 930 | CONFIRMED |
| B8 | place; the belief records p | TE/find_dice/env.py:943-961, 462-466 | CONFIRMED |
| B9 | look(die, cup, q) | TE/find_dice/env.py:962-977 | CONFIRMED. Unstated in the document: look needs NOT known-pose(?o1) and known-pose(?o2) (:969-970), which drives objection 3 (c) and makes W7 (b) mostly infeasible |
| B10 | go-home needs holding and not at-home | TE/find_dice/env.py:978-989 | CONFIRMED |
| B11 | the at-home quirk | TE/find_dice/env.py:563-581 | CONFIRMED |
| B12 | the attach and apply_sequence; physics only with sim_steps > 0; no setGravity on the find_dice path | TE/panda_utils/panda_env_utils.py:611-639, 620-639, 636-637 | CONFIRMED (grep: no setGravity in find_dice/env.py or panda_env_utils.py; the only stepSimulation there is :637) |
| B13 | pick_execute; state.grasp set unconditionally | panda_env_utils.py:927-978, 963 | CONFIRMED |
| B14 | place_execute | panda_env_utils.py:981-1034 | CONFIRMED |
| B15 | per-mesh JSON grasp library | panda_env_utils.py:265-285 | CONFIRMED |
| B16 | World.poses, CLIENT_MAP, block mass | panda_env_utils.py:585-587, 589-591, 566 | CONFIRMED |
| B17 | their camera | TE/panda_utils/robot.py:96-104, 263-264 | CONFIRMED |
| B18 | tool_use cubes, hook, particles in both worlds | TE/tool_use/env.py:35, 267-271, 182-219, 276-290, 588-589 | CONFIRMED |
| B19 | known-pose by robust std | TE/tool_use/env.py:33, 129-136, 163-165 | CONFIRMED |
| B20 | on() from particle means; reward | TE/tool_use/env.py:167-173, 719-724 | CONFIRMED |
| B21 | pick preconditions | TE/tool_use/env.py:644-664, 648-660, 658 | CONFIRMED |
| B22 | place sets known-pose | TE/tool_use/env.py:665-679, 675 | CONFIRMED |
| B23 | stack preconditions | TE/tool_use/env.py:680-702, 684-695 | CONFIRMED |
| B24 | pull-towards | TE/tool_use/env.py:703-715 | CONFIRMED |
| B25 | abstract belief literals | TE/tool_use/env.py:158-175 | CONFIRMED |
| B26 | streams | TE/tool_use/env.py:620-641, 462-483 | CONFIRMED. Neither stream has preconditions, so t = 0 sampling covers every object, the hook included; and since pick needs no grasp held at all (:651-657) and stack excludes the hook (:685), every solved episode must place the hook, so hook placements exist at least then (resolves part of the author's UNVERIFIED item) |
| B27 | the pull steps 5 per waypoint | TE/tool_use/env.py:416 | CONFIRMED |
| B28 | stack writes the commanded pose into the belief | TE/tool_use/env.py:457-459 | CONFIRMED, partial: the pose is relative to a random particle of the support (belief.get_pose is random.choice, :177-179, used at :430-431), unstated |
| B29 | belief re-simulation; observed poses collapse particles | TE/tool_use/env.py:102-121, 153-154, 150-151 | CONFIRMED |
| B30 | alpha 0.2 particles in both worlds | TE/tool_use/env.py:198, 282, 588 | CONFIRMED |
| B31 | client registration; gravity | TE/tool_use/env.py:244-245, 308 | CONFIRMED |
| B32 | class_uncertain world | TE/class_uncertain/env.py:301-304, 334-337, 334 | CONFIRMED |
| B33 | inspect returns the simulator's label | TE/class_uncertain/env.py:141-177, 175 | CONFIRMED |
| B34 | pick and the break draw (global random) | TE/class_uncertain/env.py:180-229, 37, 226-229, 226 | CONFIRMED |
| B35 | drop; None state on IK failure | TE/class_uncertain/env.py:232-264, 265-269 | CONFIRMED |
| B36 | belief and abstract literals | TE/class_uncertain/env.py:44-129, 107-129 | CONFIRMED |
| B37 | reward | TE/class_uncertain/env.py:466-472 | CONFIRMED |
| B38 | saved grasps; poses by body id | TE/class_uncertain/env.py:272-284, 153, 190 | CONFIRMED |
| B39 | client registration order | TE/class_uncertain/env.py:314-315, 373-375 | CONFIRMED |
| B40 | puck_slide: observed pose; puck reset before each trial | TE/puck_slide/env.py:540-545, 493-509 | CONFIRMED |
| B41 | slam_collect has no PyBullet | TE/slam_collect/env.py:1-27 | CONFIRMED |
| B42 | max_steps 20, gamma 0.98 | env_configs/find_dice.yml:6, 15 | CONFIRMED |
| B43 | R9: find_dice's execute_fns "draw nothing random after initialize" | (no cite) | WRONG (W-4): plan_workspace_motion (panda_env_utils.py:134) restarts IK from random.uniform samples (:158-170), and grasp_ik and ik call it (:862-872, 875-886); plan_motion (:894) reaches plan_joint_motion (:442), which runs BiRRT (:488) |

### C. Our code

| # | claim | cites | status |
|---|---|---|---|
| C1 | D9's set-up, the gear constraint | tampura_bridge/policy.py:65-113, 99-113 | CONFIRMED |
| C2 | boxel_episode, BoxelBridgePolicy, the closure | tampura_bridge/policy.py:289-297, 308-327, 312-325, 165 | CONFIRMED |
| C3 | the terminal observation | tampura_bridge/scoring.py:47-69, 23-69 | CONFIRMED |
| C4 | the D4 eye is their camera at DEFAULT_ARM_POS | tampura_bridge/task_spec.py:66-75 | CONFIRMED |
| C5 | main() and its imported primitives | test_full_pipeline.py HEAD :692, 105-114 | CONFIRMED |
| C6 | main()'s settle | HEAD :914-918 | CONFIRMED |
| C7 | the dispatcher and its branches | HEAD :1998-2008, 2037, 2242, 2278, 2323, 2536, 2778 | CONFIRMED |
| C8 | our dispatcher re-plans motion at execution, "so which grasp passes unchanged" | HEAD :2037-2056, 2044-2056 | Code CONFIRMED; the conclusion is WRONG (W-3): the grasp comes from their stream (2.6), and our re-plan keeps the planned goal configuration (G3, PAPER_AUDIT.txt:3336-3338) while their pick computes its own (TE/find_dice/env.py:368-375) |
| C9 | build_stack_goal | HEAD :598 | CONFIRMED |
| C10 | primitive definitions | execution.py:1011, 1505, 1678, 2689, 2741 | CONFIRMED (return contracts: execute_pick returns (held id, config), :1011-1013; place and stack return a config, :1505-1506, 1678-1680; observe returns (status, lost), :2689-2698) |
| C11 | register_new_detections | execution.py:2499 | CONFIRMED |
| C12 | the full-registry sweep and the lost-caster retirement render | execution.py:2185-2201, 2105-2125 | WRONG (W-1): these lines are refresh_object_aabbs's lost check (:2186-2203) and the tail of the integrity check with detection_complete (:2100-2127). The sweep is sweep_all_fragments (:2423-2424, channel sweep_render) and the retirement is retire_lost_objects (:2322-2323, channel lost_caster_render). The numbers were copied from G5's text, which has drifted |
| C13 | M8 domain generated; pick gate; observe; stack | pddl/domain_pddlstream_m8.pddl:1-2, 254, 396-410, 362-391, 364-373 | CONFIRMED |
| C14 | M8 pick and its preconditions | domain :242-273, 244-256 | CONFIRMED, partial: five of seven preconditions listed (obj_at_boxel_KIF and obj_at_boxel omitted) |
| C15 | unstack; place; place_hiding; sense views | domain :268-270, 284-314, 309, 316-321, 56, 182 | CONFIRMED |
| C16 | the env adapter and identity map | tampura_bridge/env_adapter.py HEAD :69-136, 128-136 | CONFIRMED |
| C17 | the bridge driver | tampura_bridge/run_bridge_on_finddice.py:277, 274, 168-173 | CONFIRMED |
| C18 | arm T's driver | tools/run_tampura_timed.py:1-5, 107-145, 142-144 | CONFIRMED |
| C19 | G13 in arm T's __init__ | tampura_bridge/timed_policy.py:27-31 | CONFIRMED |
| C20 | G13's runtime half | tampura_bridge/g13_runtime.py:5-8, 122-161 | CONFIRMED (as built it fails on any class of ours in their registries, :134-137) |
| C21 | G1's import graph | tools/bridge_gates.py:77-78, 226-247 | CONFIRMED |
| C22 | view__q_home | tools/episode_metrics.py:34 | CONFIRMED |
| C23 | BF#65's cause | shadow_calculator.py:226-236 | CONFIRMED |
| C24 | counted final rows | bf/BF63_gen_scenes/eval/bf63_tables.py:29-33 | CONFIRMED (the author's scripts select the same way) |
| C25 | "test_full_pipeline.main() runs unchanged in a worker thread" with the listed stubs (2.3) | HEAD :692 | WRONG in effect (W-5): with only those stubs main() still renders after actions (world_integrity_check HEAD :1600; refresh_object_aabbs :2226, 2433, 2576, 2623, 2838, 2897), which W3 (a) forbids, and its goal check runs _verify_holding (:3048), a pad-contact force test (:521-530) that cannot pass in a world that is never stepped (BF#36 item (6), PAPER_AUDIT.txt:7457-7459) |

### D. PAPER_AUDIT.txt

| # | claim | cites | status |
|---|---|---|---|
| D1 | BF#35's decision | :7366-7369 | CONFIRMED |
| D2 | their carry measured; the attach and resetJointState | :7378-7384, 7371-7378 | CONFIRMED |
| D3 | the at-home quirk | :7387-7393 | CONFIRMED |
| D4 | BF#36, B9; "no cost beyond BF#36's own" | :7418-7505 | Entry CONFIRMED; the cost row misreads it (M-2): L2 drops all three trap resolutions (:7460-7470) |
| D5 | BF#36's pad test, item (5), trap (ii), shared test, S2, S3, effort | :7447-7449, 7473-7475, 7455-7456, 7467-7469, 7471-7479, 7497-7498, 7499-7500, 7504 | CONFIRMED (tools/shared_success.py does not exist: never built) |
| D6 | BF#37 | :7507-7526 | CONFIRMED; item 2 (world-state test primary, their reward beside, :7518-7523) is not carried into the rules table |
| D7 | 100 g cube class; 0.5 mm squeeze 93 of 96 | :7542-7543, 7555 | CONFIRMED |
| D8 | BF#63's design, slow hour, run 2 wall, carries | :8897-8900, 8946-8975, 8986-8988, 8992-8994 | CONFIRMED |
| D9 | scene 104 and D9's settle; the print_F crash | :9063-9066, 9204-9214, 9076-9087 | CONFIRMED |
| D10 | BF#63's claim | :9123-9131 | CONFIRMED; the same lines say the paper "does not call ours better on these scenes", which case point 4 does not carry |
| D11 | BF#65's cause, how the die is found, case (e) | :9155-9165, 9166-9176, 9166-9171, 9215-9226, 9221-9226 | CONFIRMED |
| D12 | #P5, "ANSWERED" by their controllers | :9354-9372 | Entry exists; used against its own text (M-1): it records that their kinematic executors conflict with #P1 and calls "their grasp SAMPLING while keeping our physical execution" the coherent combination, with our runtime contact verification kept (:9365-9370) |
| D13 | #P6 | :9375-9381 | CONFIRMED |
| D14 | #P4: native execution optional, with the supervisors | :3200-3203 | CONFIRMED |
| D15 | H1 to H5, G1 | :3256, 3260-3264, 3265-3269, 3270-3273, 3274-3275, 3285-3313 | CONFIRMED |
| D16 | G3's hook, G5's channels, G6's step count | :3338-3342, 3349-3351, 3369-3371 | CONFIRMED (G5's execution.py numbers have drifted, see C12) |
| D17 | G8 (a), G8 (b), G10's pin, G12, G15 | :3380-3384, 3386-3391, 3413-3422, 3434-3436, 3472-3477 | CONFIRMED |
| D18 | M8's POD justification | :4467-4469 | CONFIRMED |
| D19 | Q18 is the highest numbered question | grep `^Q\d+` | CONFIRMED (Q1 to Q18 at :4794-4888; Q-A to Q-H separate) |

### E. The author's inputs and outputs

| # | claim | cites | status |
|---|---|---|---|
| E1 | Table I to III values, 0.878 ceiling, 3.4 min per tool_use episode, no camera in tool_use and class_uncertain | TAMPURA_TASKS_SURVEY.md sections 0b, 1, 2, 5, 7 | CONFIRMED as the survey states them (the paper not re-read by me either) |
| E2 | the no-fit case's objections, probe output, prices | no_fit_case.md 1.4, 3.4, 4, 6 | CONFIRMED |
| E3 | no prior object models | class_uncertain/BRIEF.md:54-84 | CONFIRMED |
| E4 | TAMPURA's failures are mostly repeated looks | bf/BF63_gen_scenes/eval2/REPORT.txt:16-57 | CONFIRMED (scene 131: repeated pick, :49; 106: no-ops, :24) |
| E5 | the indicator | bf63_step_equiv.txt | Reproduced byte for byte (review_probe/bf63_step_equiv_rerun.txt; `diff` empty) |

**Tally.** 108 rows. Wrong claims about code: 5 (W-1 C12, W-2 B4, W-3 C8, W-4 B43, W-5 C25). Audit entries read against their own text: 2 (M-1 D12, M-2 D4). Partial: 3 (B28, C14, D6). NOT FOUND: 0. Everything else CONFIRMED.

## 2. Numbers check

Recomputed from the committed records with an independent script (review_probe/recheck_bf63.py, output review_probe/recheck_bf63.txt) and by rerunning the author's two scripts (outputs in review_probe/).

| number in ARGUMENT.md | recomputed | status |
|---|---|---|
| ours 57 of 80, TAMPURA 46 of 76, pairs 18 to 9, p = 0.12 | eval2/REPORT.txt:10-13; PAPER_AUDIT.txt:9123-9131 | CONFIRMED |
| our successes: median 8 of their actions (4 to 69) | 8 (4 to 69) | CONFIRMED |
| TAMPURA's successes: median 5 (5 to 15) | 5 (5 to 15); rec solve_step equals the first reward-1 index in all 46; no no-op precedes any success | CONFIRMED |
| mean return ours 0.585 (80), TAMPURA 0.530 (76), today's harness 0.698 | 0.585, 0.530, 0.698 (0.98 x 57 / 80) | CONFIRMED; but the two means are over different sets. Like for like over the 76 pairs: ours 0.592, TAMPURA 0.530, today's harness 0.709 |
| 2 of 57 above 20 (54, 69); 9 above 15 | same | CONFIRMED |
| per cup count medians 6/5, 5/5, 12/6, 8/5, 12/11 | same | CONFIRMED |
| without observes: max 38, mean return 0.600 | same | CONFIRMED; note that 2 successes still exceed 20 without observes, so objection 6's "which W7 (a) removes" rests on the unverified mechanism (the extra picks vanish too), not on this arithmetic |
| s101 r1: 23 picks, 20 observes, 20 look moves, 43 plan calls; s139 r1: 33, 31, 31, 64; pick_tries 1, carries 1 | same (review_probe/bf63_long_successes_rerun.txt) | CONFIRMED |
| NEW: successes that dispatched no sense | 8 of 57 (106 r0, 114 r0, 114 r1, 125 r0, 129 r1, 136 r0, 136 r1, 137 r0) | Under W3 (a) the die is seen only at a look, so each needs one more action than the indicator counts; mean return 0.585 becomes 0.583. Small, but "our plans already contain that look" (3.3) is true of the plans, not of the counted episodes |
| NEW: successes that picked more than cups + 1, or placed a cup twice | 7 of 57 picked more than cups + 1; 3 placed some cup twice (119 r0, 119 r1, 137 r1) | Their pick needs not moved(o) (TE/find_dice/env.py:930), so W8 (a) removes those second relocations; how those 3 plans change is unknown |
| 28 days to 2026-12-04 | 24 left in November plus 4 | CONFIRMED |
| about 2,500 new lines | 2,180 plus 100 per task: 2,380 with find_dice and tool_use | CONFIRMED (an estimate of an estimate) |
| minimal version 9 to 13 working days | 5+3+1 to 7+4+2 | CONFIRMED arithmetic. The windows 11-07 to 11-21 hold 10 weekdays (11-07 is a Saturday), so the upper end assumes weekend work |
| about 2 h of cluster wall | run 2 ran 14:22 to 16:21 (PAPER_AUDIT.txt:8988) | CONFIRMED |
| 9 actions for the optimistic tool_use plan; 9.69 executed by TAMPURA | pick hook, 3 pulls, place hook, pick, stack, pick, stack = 9 | CONFIRMED |
| 3.4 min per TAMPURA tool_use episode, 70 min per repetition | 9.7 x 21 s = 204 s; 20 x 3.4 = 68 min | Arithmetic CONFIRMED. The base is the paper's per-step time; on this laptop the class_uncertain probe measured 66.5 to 139.8 s per step against the paper's 28 s (class_uncertain/STATE.md:52-58), so local tool_use time may be 2 to 5 times higher (UNVERIFIED for tool_use) |
| class_uncertain 3 + 2k steps, "the best their model allows" | inspect each, then pick and drop each fruit; skipping an inspection risks the 0.85 break (TE/class_uncertain/env.py:37, 226-227) and broken is absorbing in the reward (:470-472) | CONFIRMED by my reading (not run) |
| 0.98^6.44 = 0.878 | 0.878 | CONFIRMED |

## 3. Rules check

| rule (where) | ARGUMENT.md says | finding | named, with its cost? |
|---|---|---|---|
| R1 BF#35, one environment and one criterion (PAPER_AUDIT.txt:7366-7369) | kept, strengthened; "only the decision maker differs" (1.1) | Holds in substance, but not "only": arm O' perceives with its own pipeline, looks only from home with a configuration their sampler can never produce (TE/find_dice/env.py:619-628 against task_spec.py:70), and writes its own placement poses into the store. Arm T's look action space is different (looks 0.2 to 0.3 m above an object, which by my reading of the geometry can see behind a cup without moving it, though never under it) | Not named as deviations |
| R2 BF#36, B9 (:7418-7505) | generalised; "none beyond BF#36's own" | L2 drops all three of B9's trap resolutions (:7460-7470): our motion planner (their plan_motion runs inside their execute_fn), our finger rule at attach (their attach by name, panda_env_utils.py:963), and identity by pinch rather than "a lookup from our planner's symbol to their body id" (:7469-7470; L2's pick passes the symbol). N2 in section 5 already says our grasping and motion planning drop out; the rules row contradicts it | Misstated |
| R3 BF#37 (:7507-7526) | relaxed on arm O', declared | Also item 2: the one success test is world-state, their reward beside it (:7518-7523). W6 (a) reverses that order. W6 offers the choice, the row does not say it | Partly named |
| R4 H1, no teleports (:3256) | relaxed for their executor on both arms | Correct and declared | Named |
| R5 H1, no ground-truth or belief reads feeding "planning, perception, belief update, success scoring" (:3256-3259) | kept on find_dice (the contract and pad test are evaluation side) | The scoring clause is relaxed under W6 (a): arm O' is scored on their belief, which their execute_fns fill from world.poses (TE/find_dice/env.py:71-73) and from the attach, not from our readback as today (scoring.py:47-69). Also, through their execute_fns' motion planning on their sim world, the still-hidden die sits at its true pose as an obstacle (the sim world is built from the scene's poses, :842-848, and set_sim moves only known objects, :135-140), so a placement over the hidden die can fail for a reason SB may not see; the same holds for arm T (UNVERIFIED whether it occurs) | Not named for scoring; the sim-world channel not mentioned |
| R6 H2 and Hani's no-post-processing rule (:3260-3264) | kept: "one planned step becomes one of their actions" | The executed grasp is a sample from their stream picked by the translation layer, not the plan's ?g (M8 pick takes ?g and ?q, domain :243), and the arm's goal configuration is their IK's, not the planned one, which G3 requires to be equal (:3336-3338). That is a substitution between planner and executor. It can be avoided for grasps: let our grasp stream return their stored grasp symbols, so the planner chooses among their samples (a form of W4 (b)) and the executed grasp is the planned one | Not named |
| R7 H3, small POD deltas (:3265-3269) | kept | find_dice's deltas (moved-once, sense from home, no observe) are small and each can take its entry. Mode S's "per-task domain generated from M8's operators plus a declared delta" cannot keep M8's signatures (pick(?o ?b ?g ?q) with boxels, configurations and kin_solution, domain :242-256, have no counterpart in tool_use), so the tool_use domain is a new domain shaped like theirs, not a small delta | Not named for mode S |
| R8 G1 (:3285-3313) | kept | Agree. "The allowlist shrinks" holds only if L0 is retired, since D9's code stays on the graph for BF#63 | Named |
| R9 G3, G6, G13, G14 | changed, declared | G6's rewrite ("the store writer is the only writer of their action inputs") misses that store.certified also feeds their reward (TP/spec.py:141); a positive control should show the writer cannot change get_reward. G13 as built rejects any class of ours in their registries (g13_runtime.py:134-137) and G13's text allows exactly two registrations (:3442-3444); under W11 (a) the policy can be instantiated directly, as BoxelBridgePolicy is (:3443-3444), with no registration at all | Named, incomplete |
| R10 G20 | unchanged | Holds: every arm O' look is at DEFAULT_ARM_POS; their look renders from look_conf (TE/find_dice/env.py:528-541), which for arm O' is q_home | Named |
| R11 H4 (:3270-3273) | kept | Holds for the minimal version. The W10 camera variant appends a schema to arm T's spec, which G13's arm T check rejects (g13_runtime.py:158-159) and which changes TAMPURA's published task B; W10 (b) avoids it | Partly named |
| R12 #P5 (:9354-9372) | "ANSWERED: their controllers on arm O'" | #P5's own analysis recommends their grasp sampling with our physical execution and our runtime contact verification, and says their kinematic executors conflict with #P1 (:9365-9370). L2 adopts the half #P5 advised against | Misstated |
| R13 #P1 (:129-146) | not mentioned | Arm O' runs on a per-waypoint pose reset of the held body, the class of mechanism #P1 removed from our pipeline (the "telekinetic attachment", :138-143). The paper's #P1 claims do not cover the L2 runs. N1 to N3 cover part of this; #P1 should be named | Not named |
| R14 no bridge-only tuning (Hani's rule) | kept | Agree: the deltas are declared before any run and none raises a robot setting after a failure. Home-only sensing is a protocol definition | Named |
| R15 the request's own terms ("almost run their system entirely ... wiring as much of sb into their system as possible") | L2 wires perception, registry and planner on find_dice | L2 wires less of SB than B9 did (B9 kept our motion paths, our grasps and our finger rule). The tension between "their system entirely" and "as much SB as possible" is real and the document resolves it toward their system without saying so | Not discussed |
| R16 no prior object models (class_uncertain/BRIEF.md) | in tension, W9 | Correct; W9 (c) is a sound recommendation | Named |

## 4. Ranked objections

Ranked by how much each would change the verdict.

**1. The case for doing this now is not made against the alternatives, and the experiment cannot deliver its stated payoff at this sample size.** Case point 4 says a lead that survives L2 "belongs to the belief representation and the planner" and a lead that shrinks "tells the paper where it came from", and that "either reading is publishable". But BF#63 has no significant lead to decompose: 18 to 9, p = 0.12, and each repetition alone p = 0.42 and 0.27 (PAPER_AUDIT.txt:9000-9002); TAMPURA's outcome repeated in both repetitions on 38 of 38 scenes and ours on 39 of 40, so "its 76 pairs carry about the information of 38" (:9032-9042). A second protocol on the same 40 scenes with two near-duplicate repetitions cannot separate a surviving lead from a shrinking one unless the shift is large, so C3 ("the gap ... measures what our own execution and sensing added or cost") would be a difference of two non-significant differences. Meanwhile BF#65 already limits what C2 may credit: the regions drive the search only because the space behind each cup is unknown, never by modelling where the die hides (:9166-9176, 9266-9272), so what L2 would isolate is our search policy over that registry. C2 carries BF#65's caveat; case point 4 does not. The document never weighs L2's 9 to 13 days against BF#65's option 1 (a hiding region under a cup, which changes what the paper can claim about regions on find_dice, :9230-9242), against more generated scenes (their generator is endless, survey section 7; 40 scenes with two repetitions took about 2 h on 10 nodes, PAPER_AUDIT.txt:8986-8988, so 120 new scenes with one repetition would take about 3 h, my estimate), or against the class_uncertain plan Hani commissioned, whose route phase is held on this verdict (class_uncertain/STATE.md:30-36). *Changes the verdict* from "do it, minimal version first" to "an option, after Hani ranks it against BF#65's option 1 and more scenes". *What would answer it:* a pre-registered L2 design with a power statement (for example 120 new scenes, one repetition, since repetitions are near duplicates); and an explicit ranking of L2 against BF#65's option 1 and the class_uncertain plan.

**2. The rules table misstates five binding items, so Hani would answer W1 on an incomplete account of what he relaxes** (rules rows R2, R3, R5, R6, R12, plus R13). #P5's own text advises the opposite combination; BF#36's trap resolutions all go; H1's scoring clause is relaxed under W6 (a); BF#37 item 2 is reversed by W6 (a); the executed grasp and goal configuration are substituted between planner and executor. *Changes the verdict* to "survives with changes". *What would answer it:* rewrite those rows with each relaxation and its claim cost, and name #P1.

**3. The design does not define the seams where arm O' would fail first.** (a) Grasp choice: their pick takes one of five sampled grasps per object (flat_width 5, env_configs/find_dice.yml:10; TE/find_dice/env.py:756-769); which one the translation picks is not specified. (b) Silent failures: their pick, place, look and go-home return the old state when IK or motion planning fails (TE/find_dice/env.py:377-390, 447-459, 535-536, 578-579), and TAMPURA's own last three actions on scene 131 were one repeated pick (REPORT.txt:49; that it was failing IK or motion is my reading, UNVERIFIED). A step executor that re-issues the same grasp after such a failure loops the same way; no retry or exclusion rule is given. (c) The contract abort: their belief learns any body with one pixel in the segmentation (TE/find_dice/env.py:64-73) while our registry needs 6 (perception.py:320). A die visible in 1 to 5 pixels makes every further look inapplicable (look needs NOT known-pose(die), :969) while SB still wants to sense, so the contract aborts the episode on a choice SB cannot know is inapplicable. In substance that is a perception miss, and it should count as one. (d) Counting: the document does not say whether an abort is an arm O' failure or a gate failure; under BF#63's validity rule a gate failure reruns and then drops the scene's pair for both arms (PAPER_AUDIT.txt:8905-8909), a selection effect in SB's favour. (e) Placement poses: "our free-space boxel's centre as a Pose" leaves the cup's height and orientation open in a world that is never stepped, so a wrong z stays wrong. (f) The look's ?o2 argument is not determined by our plan. (g) main()'s own force-based goal check fails in a never-stepped world (W-5). *Changes the verdict* only if these are left open; each has a direct fix. *What would answer it:* plan over their grasp samples (rules R6); map each silent failure to a status that excludes the failed (object, grasp) pair at the next replan; count every contract abort as an arm O' failure, never as a gate failure; take p's z and orientation from the held object's current pose; set ?o2 to the caster of the sensed region; make the goal check geometric; and report abort counts from the find_dice_simple and three-seed smokes before any campaign.

**4. The effort is underestimated.** W3 (a) needs main()'s post-action renders suppressed or rerouted at seven call sites (HEAD :1600, 2226, 2433, 2576, 2623, 2838, 2897) and its goal check changed (:3048), which is the "registry debugging" the fallback is priced against, but it is not in the 5 to 7 days of row 1; the four review gates the #P4 record requires before quoted numbers (PAPER_AUDIT.txt:3521-3528) are not in the plan; the stubs' return contracts were not read (R1); and the windows assume weekend work. There is no kill criterion for the harness itself. *Changes the verdict* modestly (the minimal version still fits before 12-04 at the upper end, but with no buffer for tool_use). *What would answer it:* a re-estimate with these items, and a stop date (for example, if find_dice_simple and one generated scene do not run end to end headless by 11-13, fall back to W3 (b) at once, and if not by 11-16, stop).

**5. On tool_use, mode S is close to TAMPURA's own contingent_policy, so C4 says little about SB.** Their ContingentPolicy samples once, builds an all-outcome determinisation of their domain (TP/spec.py:453-492), plans with symk and executes the first action (TP/policies/contingent_policy.py:19-47); with the deltas of the mapping table (no unstack, the support's pose gate, pull as an optimistic observe), mode S plans over exactly their preconditions with an optimistic outcome, from their abstract belief. What remains different is Fast Downward instead of symk and our action costs. The document cites ContingentPolicy (2.3) but answers objection 2 and C4 as if the slot were empty. *Changes W2 (b), not the minimal verdict.* *What would answer it:* run their registered contingent_policy (TP/policies/__init__.py:18) as the control on the same seeds at no cost, and claim only the difference; or drop tool_use before the deadline.

**6. C2 and C3 claim more than L2 holds equal.** "Execution, sensing and budget are identical" (C2): the executor and budget are shared, the sensor is shared, but the views differ (home only against their sampled close looks), the perception differs (exact poses for any visible pixel against our boxelization), our kinematic streams still filter our plans (BF#65 (c): our reach gate refuses picks their executor might reach, PAPER_AUDIT.txt:9193-9203), and in-episode random draws are not paired even on find_dice (W-4). Under the W3 (b) fallback our per-action renders return, the exact channel that produced all 57 successes (:9166-9176), so C2 cannot be claimed at all then. *What would answer it:* restate C2 as "with the executor, budget, sensor and score shared"; drop C3 as a measurement unless a paired O against O' test is pre-registered with enough scenes.

**7. Case point 3 overstates comparability with the published table.** The shipped find_dice layouts are dated seven months after the paper's v2 and BF#63's scenes are newly generated (survey section 7), and how Table I computes the return is UNVERIFIED (survey 0b; the author marks it too). L2 gives the same metric, not numbers comparable with Table I. *What would answer it:* say "the same metric as their Table I".

**8. Undeclared deviations in arm O''s favour or against it.** Looks from home use a configuration arm T can never get (B4); SB's placement poses enter their store and its certified facts, which their reward reads (TP/spec.py:141); the W3 (b) fallback is in our favour; looks from home cannot see behind an unmoved cup, which their close looks can by my reading of the geometry (against us). *What would answer it:* one numbered deviation list, as Hani asked for class_uncertain on 2026-11-06 (class_uncertain/BRIEF.md:86-112), repeated in the BF# entry and the report.

**9. The indicator needs three small corrections** (section 2: no-sense successes, second relocations, unlike sets). They do not change its use as a scale check.

## 5. What fails, what survives

**Does not survive as written**
- Section 4's rows for #P5, BF#36, H1 (scoring), BF#37 and H2 or no-post-processing (rules R2, R3, R5, R6, R12), and the missing #P1 row (R13).
- 2.6 (a)'s claim that SB's look entries are "the fact their stream would certify" (W-2).
- 3.3's "which grasp ... pass unchanged" (W-3), R9 (W-4), R2's execution.py cites (W-1), 2.3's "main() runs unchanged" (W-5).
- Case point 4's "either reading is publishable" at 40 scenes and two near-duplicate repetitions; C3 as a measurement.
- Case point 3's "comparable with their published table".
- The tool_use extension (W2 (b), C4) without contingent_policy as its control.
- Objection 6's answer "which W7 (a) removes" as stated (the arithmetic does not show it; the mechanism is UNVERIFIED, as 3.3 itself says).

**Survives with changes**
- The verdict (minimal version as a declared second protocol), if: the rules table is corrected; the seams of objection 3 are specified; the campaign uses more scenes and one repetition with a pre-registered test, or states its power; a stop date is set; and Hani ranks it against BF#65's option 1 and the class_uncertain plan before W1.
- The mode R architecture (2.2, 2.3), with W3 (a)'s render suppression and the geometric goal check designed into main(), or W3 (b) accepted up front with C2 withdrawn.
- C1 and C5 (C5 narrowed: mode R is find_dice only, the others need a domain and a translation table each).
- The effort table, re-estimated with objection 4's items.
- The indicator (1.3, 3.3), with section 2's corrections.
- W4 (a), with grasps planned over their samples rather than picked by the translation.

**Survives as written**
- Section 1 points 1 and 2 on how their framework runs alternative planners and the asymmetry list; 2.4's interface table (every cite confirmed); 2.5's contract principle; 2.7's drivers and W11 (a).
- The tool_use mapping table (every precondition cite confirmed) and the treatment of the no-fit case's execution objection: under their executor, the fall-through can show only in a world-state on() test after a pull that follows a stack (TE/tool_use/env.py:416; panda_env_utils.py:620-639).
- class_uncertain's section and W9 (c); its caveats on global random and the None state.
- find_dice's "today against step-wise" table, and the reading of cases (d) and (e).
- puck_slide and slam_collect paragraphs.
- Risks R1, R3, R4, R5, R7, R8, R10, R12; R11 once it says how the settle is switched off: the loop at HEAD :916-917 is unconditional, so either main() skips it (one more change to main()) or the no-op is called 50 times and "a counted no-op whose count must be 0" cannot mean the call count. Counting stepSimulation calls our code issues on the executing client, through the existing pybullet hook, would state it cleanly.
- W7 (a), which is stronger than argued: W7 (b) is mostly infeasible, because their look needs an object of unknown pose as ?o1 (TE/find_dice/env.py:969), so observe cannot map onto a look once the die is known, which is when M8 needs it. W8 (a), W12 (a), W13 (a).

## 6. Gaps against AUTHOR_BRIEF.md

1. Section 1 asks why this is "the right move for the paper". The document argues for the move but compares it with no alternative use of the same days (objection 1).
2. No consolidated deviation list for arm O' against arm T; the deviations are spread over 2.6, 3.3, 4 and 9, and several are missing (objection 8).
3. No campaign design: test, power, and how a contract abort counts under BF#63's validity rule (objection 3 (d)).
4. No rule for grasp choice and no handling of silent execution failures (objection 3 (a), (b)).
5. tool_use, the worked example, does not discuss their contingent_policy, the existing policy in the same slot (objection 5).
6. "Mark every estimate": done. "Every claim about code carries file:line": done, with the five wrong ones listed.
7. Process, not content: the author's files have no DATA_LEDGER.md row (the author was not allowed to write one), and neither do mine (same rule). The session that keeps these documents should add both.

## 7. Not checked by this reviewer (UNVERIFIED)

- Any run of L2, of find_dice_simple, or of PyBullet across threads and in GUI mode.
- Whether their saved grasps' closed_position passes the 1 mm pad test (the disagreement rate in 2.5).
- How often a die shows in 1 to 5 pixels in their segmentation (objection 3 (c)), and whether a placement over the hidden die fails through their sim world (rules R5).
- TinyRenderer's treatment of tool_use's alpha 0.2 particles.
- TAMPURA's local per-step time on tool_use.
- The paper's Table I computation and scenes (taken from the survey, as the author did).

## 8. Files made by this reviewer

All under archive/tampura_bridge_plan_2026-10-25/wire_sb_into_tampura/:
- REVIEW.md (this file).
- review_probe/recheck_bf63.py: my read-only recheck of the indicator.
- review_probe/recheck_bf63.txt: its output.
- review_probe/bf63_step_equiv_rerun.txt: the author's bf63_step_equiv.py rerun (identical to bf63_step_equiv.txt).
- review_probe/bf63_long_successes_rerun.txt: the author's bf63_long_successes.py rerun for 101:1 and 139:1.

Nothing else was written, in the repo or in WSL.
