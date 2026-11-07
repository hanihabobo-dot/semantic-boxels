# class_uncertain plan: live state (hand-over for any session)

Session "Go" (started 2026-11-03 on Hani's `go`, BRIEF.md in this folder).
Read BRIEF.md first; this file says where the work stands.

- BF#67 is claimed for this plan's audit entry (grep of the whole checkout
  2026-11-06: BF#64 shadow table, BF#65 cup residuals and BF#66 attribute
  boxels are taken; 67 to 79 free).
- Q-numbers: the highest in the checkout is Q18 (grep 2026-11-06); this
  plan's questions start at Q19. Grep again before writing them.

## Status

- 2026-11-03: read the brief, the survey, their class_uncertain env.py,
  env_generator.py, config and the 20 scenes, our policy.py, scoring.py,
  task_spec.py and env_adapter.py, and BF#35 to BF#37. Interrupted by Hani
  before anything was written.
- 2026-11-06: assumption A1 withdrawn (BRIEF.md, commit d6a9715; Hani
  confirmed it in chat): our arm gets NO prior model of the task objects,
  the setup stays as close to TAMPURA's as possible, and the full deviation
  list is repeated in six places (BRIEF.md, "As identical to their setup as
  possible").
- 2026-11-06 12:10 to 12:55: phase 1 (Understand) DONE on Hani's "Yes,
  launch it": one workflow, seven Sonnet agents, no top-tier. Maps in
  `work/understand/` (01 theirs, 02 perception and registry, 03 planner
  and domain, 04 execution and grasping, 05 bridge, harness and gates, 06
  decisions and rules, 07 the TAMPURA cost probe). The probe's WSL folder
  (25 MB) was deleted at 12:58 after its text evidence went to
  `work/understand/07_probe_evidence/` (DATA_LEDGER.md, Kept and Deleted).
- 2026-11-06 13:40: Hani started the dev tracks
  (`../tracks/STATE.md`, BF#68): the session "Go" orchestrates four
  paths. This plan stays HELD and its phase 1 goes to path 2 (which
  TAMPURA tasks give SB a quick result) as input; whether the plan
  resumes when the argument below is final is Hani's call.
- 2026-11-06 14:14: the argument is final
  (`../wire_sb_into_tampura/ARGUMENT.md` section 12, "survives with
  changes"; REVIEW.md beside it) and releases this plan's Route hold
  (ARGUMENT.md:284, 600). Its inputs for Route:
  - section 3.2: SB "in mode S", with possible_fruit and is_fruit as
    K-literals, inspect as a sense whose optimistic outcome is "not a
    fruit", pick gated on a known class, drop to the bowl region, and the
    literals read from their abstract belief, declared; expected 3 + 2k
    steps for k fruits;
  - the conflict with the no-object-model rule: their pick takes saved
    grasps and sim-world poses by body id (ARGUMENT.md:282), which this
    plan's D-1, D-2 and D-7 weigh;
  - W9: (a) their pick, models in execution for both arms; (b) our
    grasps from our renders wrapped as their Grasp; (c) leave
    class_uncertain to this plan, recommended (ARGUMENT.md:648-653);
  - W5 (a): reads of their literals declared and counted;
  - W6 (b): the world-state test primary, their reward beside it.

  Its questions would also take Q19 onward if logged; whichever is logged
  second takes the next free numbers (ARGUMENT.md:602).
- NOW: phase 1 reported to Hani (the D-list below, in full). Phase 2
  (Route) waits for Hani's answer: resume now, or after path 2's ranking
  of TAMPURA's tasks (asked 14:15 and again 14:25; recommended: after
  path 2). Since 15:10 that is the default unless Hani says otherwise:
  resume when path 2 (`local_c0b7d721-3c95-4898-bf80-236b5f81d882`)
  reports its ranking.

## Phases (BRIEF.md, "How to run it")

1. Understand: DONE (above).
2. Design: two or three route designs, judged. HELD on Hani's answer (the
   argument is final since 14:14 and released its side of the hold).
3. Adversarial verification of every cite in the chosen plan.
4. Completeness critic, which also hunts for unlisted deviations.
5. PLAN.md, BF#67, the `go` section of CLAUDE.md deleted, local commit.

## Phase 1 results in short

- The survey's Route claim holds: their observation holds ONE detected
  object, class label, grasp and broken flag (their class_uncertain/env.py:
  132-138), and on(o, bowl) enters the belief only through an action named
  "drop" (env.py:94-95). One terminal observation cannot carry the task.
- TAMPURA on this laptop (probe, map 07; their code as shipped through our
  timed arm-T driver, G13 passed, global seeds 0, 1, 2, unpinned): scenes
  1700969399.5083039, 1700969395.955831 and 1700969396.9136949; wall 445,
  754 and 625 s; 66.5, 89.8 and 139.8 s of planning per real step (paper:
  28 +- 26); success 2 of 3. It picked UNINSPECTED objects in all three
  episodes; in seed 2 an uninspected racquetball broke (the 0.85 coin
  flip) and the episode was lost. 6, 8 and 4 real steps.
- The pipeline modules branch on no class: every class channel enters
  through the find_dice bridge (symbol = category, ObjectInfo.size =
  CLASS_EXTENTS, the plan twin = create_ycb(category), class masses and
  inertias in d9_setup, the target by category). Map 02 section 4.
- Grasping is the largest risk: our grasp is a top-down pinch over the
  perceived box, capped at 76 mm (streams.py:793). Mesh extents (map 04):
  strawberry 45, racquetball 56, lemon 61 x 59 x 53, tennis ball 67,
  baseball 74, apple 75 mm. By formula the planner's commit rule cannot be
  met for the apple and barely for the baseball. No sphere was ever
  grasped by our pipeline. Nothing was run on our side.
- No container exists in our pipeline (the tray is fixed and read by an
  oracle); stack takes one object per support. No class belief exists;
  no probabilities exist in our planner. No step budget exists in our
  loop.
- Gates: a per-step route on their execute functions trips G13, G14, G6,
  G8(b), G10, G19 and G12 as built; our physical execution per step needs
  G7, G9, G10, G13, G15, G16, G19, G20, G4, G3 extended (map 05 section 3).
- SCENE_MAP already pins seeds 0 to 19 to find_dice scenes; a
  class_uncertain manifest on those seeds stops bridge_gates at import
  (bridge_gates.py:133-134).

## Deviations (D-list, phase 1 version, 2026-11-06)

Candidates from phase 1; phase 2 confirms, drops or adds. "T" is TAMPURA,
"O" our arm. Their cites are relative to
/root/tampura-work/tampura_environments/tampura_environments/.

What each arm is given
- D-1 Object models. T's planner world is built from the same scene file
  (true meshes and poses, class_uncertain/env.py:373-375) and reads poses
  by body id at every inspect, pick and drop (env.py:153, 190, 237-240).
  O has no model and estimates poses from its own renders. Cannot be
  removed: it is the test. Favours T.
- D-2 Grasps. T samples 3 of 41 to 53 saved grasps per class
  (panda_utils/panda_env_utils.py:265-285; env.py:272-284). O plans a
  top-down pinch over its perceived box, capped at 76 mm (streams.py:793).
  Cannot be removed. Favours T; by formula O cannot commit to picking the
  apple (75.4 mm) and only barely the baseball (73.7 mm).
- D-3 Outcome model. T's planner learns outcomes by calling the execute
  functions without a state; they hold the uniform prior, the exact reveal
  and DROPABILITY (env.py:149, 197, 226). O is told the same task facts as
  rules. Same knowledge, other form; see D-14.
- D-4 Order leak. Every scene file lists fruits first
  (env_generator.py:70), so T's symbols o_ph_0, 1, 2 put fruits first. In
  the probe T picked o_ph_0 uninspected in 2 of 3 episodes, both fruit
  (a tie-break by symbol order is UNVERIFIED). O gets a class-free order.
  Built into their setup. Favours T.
- D-5 Camera. Their env renders nothing; O renders its fixed eye and wrist
  camera (task_spec.py:66-75). Needed: O has no other pose source. O's
  renders must not be used to guess a class (a question for Hani). Costs O
  time.
- D-6 The bowl's role. O is told which body is the bowl, as T is
  (is-bowl certified on regions[1], env.py:383). Equal; one per-object bit
  for both.

Physics and execution
- D-7 Executor. T moves kinematically and attaches the held object at the
  saved grasp pose: it cannot slip, and a pick cannot fail once IK and the
  motion plan succeed (panda_env_utils.py:611-639, 927-978). O executes
  physically (BF#37) and can miss, slip or drop. Route dependent (gone if
  O runs on their execute functions). Favours T.
- D-8 O's physics edits (tampura_bridge/policy.py:65-113, d9_setup). Their
  gravity -10 and mass 0.1 stay (our -9.81 and class masses and inertias
  go). Kept for O's grip: 200 solver iterations against their 50, the
  finger gear, object friction 1.0 against PyBullet's default, pad
  friction 1.2. Favours O.
- D-9 Collision checking. T plans pick motions with no obstacles and
  checks a grasp only against its target (env.py:192, 208;
  panda_env_utils.py:393-394); O checks every perceived object. Favours T.
- D-10 Planning geometry. O's collision twin must be boxes from its
  perceived boxes; a solid box hides the bowl's cavity. Favours T.
- D-11 Release height. T drops from 0.1 m above the bowl frame and then
  steps 200 times (env.py:237-262); O releases at the rim unless it copies
  their drop. Removable; small effect.
- D-12 Sleeps. T sleeps 2 s per drop and 5 ms per motion iteration
  (env.py:260-262; panda_env_utils.py:639). Favours O on wall time, about
  4 to 8 s per episode.

Risk and decisions
- D-13 Break rule. Their coin flip runs inside their pick, after the
  motion (env.py:226-229). O's physical pick must meet the same rule with
  the true class (an environment rule for both arms), or balls never break
  for O. The random streams differ, so breaks cannot match seed for seed.
  Hani's call.
- D-14 Decision rule. O would pick only a known fruit (a precondition
  added for this task); T plans with learned probabilities and picks
  uninspected objects (probe: all 3 episodes, one break). Favours O on
  success, T on steps.
- D-15 Step budget. T stops at max_steps 20; our loop has no step limit.
  Removable: count O's inspect, pick and drop and stop at 20. Rarely binds
  (5, 7 or 9 needed).

Scenes, seeds, scoring
- D-16 Seeds. Their seed-to-scene map depends on the folder's listing
  order (env.py:354-356), and seeds 0 to 19 do not cover all 20 scenes.
  Pinning each scene once (BF#63) changes the seed-scene pairs and the
  random stream; find_dice already owns seeds 0 to 19 in SCENE_MAP.
  Neutral between arms; a departure from "their seeds".
- D-17 Success. T's reward is read on its belief: a drop writes on(o, bowl)
  wherever the object lands, even when the drop's motion plan fails
  (env.py:85-95, 245-264). The one criterion reads the final world.
  Favours T under its own reward.
- D-18 Silent simulation. A drop whose IK fails sets T's executing state to
  None, and later actions run in simulation (env.py:265-269). T only.
  Favours T under its own reward.
- D-19 Broken ball in hand. A "broken" ball stays attached to T's hand and
  travels on (panda_env_utils.py:963). T only; the episode is lost anyway.
- D-20 Code against paper. Code: 3 objects, exact reveal, DROPABILITY 0.85
  (0.35 in a comment, env.py:33-37). Paper: 2 to 10 objects, noisy labels.
  The plan follows the code. Probe: T 2 of 3 at 66 to 140 s per step,
  against the paper's implied ~99 % at 28 s.
- D-21 Window W. find_dice's W (task_spec.py:81-82) leaves out 16 of 60
  object centres and 7 of 20 bowls of these scenes; re-derive from an
  empty-table probe (G9). Removable; disfavours O if kept.
- D-22 Calibrations. Squeeze, force hold, yaw noise and pose tolerance
  were fitted on a die, cups and cubes, never on 45 to 75 mm spheres of
  0.1 kg; no task-only retuning (Hani's rule). Direction unknown.
- D-23 Clocks. O's clock holds its set-up, twin and first render inside
  the rollout; T builds two worlds with 2000 settle steps each before its
  loop. Report wall and loop clocks for both.
- D-24 Repetitions. Same seed, same T outcome (BF#63: 38 of 38).
  Repetitions need other seeds. Neutral; changes the evidence.

## Questions taking shape (numbered Q19 on in PLAN.md; not yet put)

- Route: their execute functions for O (BF#36's B9, parked by BF#37) or
  our physical execution per step; held for the argument.
- The break rule for O (D-13), and its random stream.
- O's renders never used for class (D-5).
- Seeds: their native map or each of the 20 scenes once (D-16).
- Hani's statements on puck_slide (a branch per task) and slam_collect
  (same actions, env and perception; world model, fluents and planning are
  ours): do they carry over to class_uncertain?
- The world-state success criterion: every true fruit in the bowl and no
  break (D-17).
- Apple and baseball: accept that the pipeline-wide grasp limits may fail
  them, or a pipeline-wide change; no task-only tuning (D-2, D-22).

## Notes from the Project status session (2026-11-06)

- Hani said two things today about OTHER tasks that bear on Route; whether
  they carry over to class_uncertain is his call, so the plan asks:
  - puck_slide: "make sure that we would be working on another branch where
    we be building a version just for this task becuase it seems that this
    is what they in tamoura have done";
  - slam_collect: "we get the same actions as they do and same env and
    perception. how we use their perception to come up with a world model
    and what luents we have and how we plan is our bussnis."
- Other sessions' uncommitted hunks: tampura_bridge/env_adapter.py (BF#64's
  fix, see bf/BF64_shadow_table/STATE.md), eval_runner.py,
  test_full_pipeline.py (13 lines removed near 826: cites below that are 13
  lower than HEAD), PAPER_AUDIT.txt, and one DATA_LEDGER.md row (the three
  arguments). Never stage their hunks.
- Two more arguments are being written (`../puck_slide/`,
  `../slam_collect/`); this plan does not need them.
- BF#63 run 2 and BF#65's fix option are find_dice decisions and do not
  block this plan.
