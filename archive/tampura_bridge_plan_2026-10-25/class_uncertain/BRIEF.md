# BRIEF: plan our pipeline on TAMPURA's class_uncertain task

Written 2026-11-03 by the session "Project status" for a fresh session;
changed 2026-11-06 on Hani's word (the object-model assumption A1 is
withdrawn, see "No prior object models" below).
Start: Hani opens a new Claude Code session in this checkout (branch
`tampura-bridge`), model Opus 5.5, effort max, and types `go` (the project
CLAUDE.md points here). Hani's request of 2026-11-03, verbatim:

> i want an opus 5.5 max ultracode to solve this. solve is make a plan about
> what needs to be done exactly to to run our code on that other task at our
> current code level. we make this assumption as we did before. we have to
> have modles of these detected objects alreeady in the system.

His change of 2026-11-06, verbatim. It REPLACES the assumption in the last
two sentences above:

> i wanna you to tell whatever ai session is working on doing tampura class
> uncertain to scrap what i said about assuuimg we have a model. because that
> would go out agiasnt the setup of that experiment. if theres no no ai
> working on that yet than make sure that the docuement for for how to start
> to worek on that knows this. it would eb nice to test how would sb performe
> on objects for which wehave no modke, try to make the experment is
> identical as possile to their setup and make sure to report the devaitions
> mutiple times to me in case i miss them

"That other task" is TAMPURA's `class_uncertain` (paper task A, "Class
Uncertainty"), the one task the survey (TAMPURA_TASKS_SURVEY.md, this
folder) found a partial fit for our pipeline. A first session titled "Go"
(local_4f1f1cf6, 2026-11-03) read their class_uncertain env.py and was
interrupted by Hani before it wrote anything; it was told of the change on
2026-11-06.

## The job

A PLAN, not code: exactly what must be done to run our pipeline, at the
code level of `tampura-bridge` today, on their class_uncertain environment,
on objects our pipeline has NO prior model of, in an experiment as close to
TAMPURA's own setup as possible, so that our arm (O) and TAMPURA (T) run in
one environment under one success criterion and every remaining difference
is named. A later session implements it after Hani has answered the plan's
questions. Done means:

- `PLAN.md` in this folder, concrete enough that an implementation session
  can work through it item by item without re-deriving anything;
- every claim about their code or ours carries a file:line cite that a
  verification pass has checked;
- the DEVIATIONS list (below) complete, and reported as the section after
  next says;
- Hani's open decisions listed as numbered questions, each with options and
  a recommendation;
- one new BF# entry in PAPER_AUDIT.txt and a STATE.md in this folder.

## No prior object models (Hani, 2026-11-06; replaces A1)

The old assumption A1 ("we have to have models of these detected objects
already in the system", as for find_dice, where `tampura_bridge/task_spec.py`
carries the cups' and the die's categories, mesh extents, masses and
inertias, each cited to a BF# entry) is scrapped. In class_uncertain the
hidden variable is each object's CLASS (a uniform prior over six classes,
revealed only by their `inspect` action); a model of each object in our
system would give our arm what TAMPURA's arm has to find out, which goes
against the experiment.

What replaces it:

- Our arm gets no per-object model of the task objects: no category,
  class, mesh, extents, mass, inertia or grasp set for the YCB apple, lemon,
  strawberry, tennis ball, racquetball, baseball or the bowl, in
  task_spec.py or anywhere else. It works from what it perceives (its own
  renders) and from the task's own sensing (`inspect`). This is the test
  Hani wants: how Semantic Boxels performs on objects it has no model of.
- Task-level knowledge that TAMPURA's planner also has (the six class
  names, which are fruit and which are balls, the goal, the actions and
  their semantics) is not a per-object model and is given to our arm too.
  Where the line between the two is unclear, the plan says where it draws
  it and lists it as a deviation.
- The plan must show how each object's class stays exactly as uncertain
  for our arm as for theirs (uniform prior, revealed by `inspect`), or put
  the question to Hani with options. Do not decide it alone.
- The asymmetry this creates goes on the list: TAMPURA reads object poses
  from the simulator by body id and samples grasps from a saved grasp
  library (survey section 1; verify), so their planner has object models
  our arm will not have. That is a deviation in TAMPURA's favour.

## As identical to their setup as possible, every deviation reported

Hani: "try to make the experment is identical as possile to their setup and
make sure to report the devaitions mutiple times to me in case i miss
them".

- Default to their setup everywhere: their 20 saved scenes (pinned per
  episode as in BF#63), their seeds, their env code and physics (gravity
  -10, mass 0.1, settle steps), their max_steps 20 and config, their action
  semantics (`inspect` reveals the true class; `pick` breaks a ball with
  probability DROPABILITY; `drop` into the bowl), their success criterion.
- Anything our arm does differently is a deviation. Keep one numbered
  list, D-1, D-2, ...: what differs, why it cannot be avoided (or what
  removing it would cost), which arm it favours, and how it could move the
  result. List too where their code and their paper differ (3 objects and
  an exact reveal in the code, 2 to 10 objects and noisy labels in the
  paper; DROPABILITY 0.85 or 0.35) and which one the plan follows.
- Report the full list, in full and never as "see above", in each of these
  places:
  1. at the top of PLAN.md, before anything else;
  2. in its own DEVIATIONS section of PLAN.md;
  3. in STATE.md;
  4. in the BF# entry;
  5. in each phase-end report to Hani in chat;
  6. in the final report to Hani.

  Hani asked for the repetition on purpose, so that he cannot miss one.

## What is known (verify before relying on it)

Their task, from the survey (cites there; their tree is read-only at
`/root/tampura-work/tampura_environments/tampura_environments/class_uncertain/`):

- Goal: every object that may still be a fruit is on the bowl, and nothing
  is broken. The reward is 0 or 1 on their abstract BELIEF, not on the
  physical world.
- Scenes: 3 movable YCB objects and a bowl. 20 saved scenes in `problems/`
  (1, 2 or 3 fruits), picked by `random.choice(os.listdir(...))` after
  seeding: the same G19 trap as find_dice, solved there in BF#63 by giving
  each episode its own working directory and pinning seeds through
  `BRIDGE_SCENE_MANIFEST`. Their `env_generator.py` makes more scenes.
- Actions:
  - `inspect` returns the true class, noise free.
  - `pick` "breaks" a ball with probability DROPABILITY (0.85 in the code;
    a comment says 0.35 was used for risk experiments). This is a coin
    flip, not physics.
  - `drop` asserts on(o, bowl) wherever the object lands.
- Physics: gravity -10, mass 0.1, settle steps. No camera rendering at all.
- Config: max_steps 20.
- Paper: TAMPURA's return is 0.87 ± 0.01 against a 0.878 ceiling (about
  99 % implied success), at 28 ± 26 s per step over 6.44 steps.
- The paper's version differs from the code: 2 to 10 objects and noisy
  labels in the paper, 3 objects and an exact reveal in the code. Which
  version produced Table I is UNVERIFIED.
- Survey verdict: partial fit (same Panda, PyBullet, YCB assets and
  executor as find_dice; the uncertainty is class, not occlusion; TAMPURA
  at its ceiling); 1 to 2 weeks, an unverified estimate made under A1.

A separate agent argued the no-fit case for tool_use, puck_slide and
slam_collect (no_fit_case.md here). It is context only, not part of this
job. The page `tasks_page/` here shows the tasks with screenshots.

## Our side: read these

- The find_dice bridge, `tampura_bridge/`:
  - `run_bridge_on_finddice.py`: arm O's driver.
  - `policy.py`: BoxelBridgePolicy and the one-action `boxel_episode`
    schema; our whole pipeline runs inside one TAMPURA action.
  - `env_adapter.py`.
  - `scoring.py`: the one terminal observation their belief reads.
  - `task_spec.py`: the find_dice specifics, the only file G7 exempts.
  - `g13_runtime.py` and `gate_hooks.py`.
  - `timed_policy.py`: arm T's timing wrapper.
- Tools:
  - `tools/run_tampura_timed.py`: arm T's driver, their `run_planner.py`
    plus one import.
  - `tools/bridge_gates.py` with `tools/bridge_gates_allowlist.txt`: the
    G-gates. G2 allows only reviewed simulator reads; G7 bans scene
    literals outside task_spec.py.
  - `tools/_bridge_campaign.py`.
  - `tools/gen_scene_eval.py`: BF#63's two-arm harness, with the validity
    rule, the failure screenshots, Wilson and McNemar.
  - `tools/cluster/*.sbatch`.
- The pipeline:
  - `test_full_pipeline.py`: the main loop.
  - Perception and the region registry: `perception.py`,
    `shadow_calculator.py`, `boxel_data.py`, `boxel_types.py`, `belief.py`,
    `pose_belief.py`.
  - Planning: `m8_domain.py`, `domain_pddlstream_m8.pddl`, `streams.py`,
    `pddlstream_planner.py`.
  - Execution: `execution.py` (physical pick, place, sense, move) and
    `slip_fixes.py` (BF#62's defaults).
  - `world_eye.py`: logging of true and believed poses.
- Decisions that bind the plan (PAPER_AUDIT.txt):
  - #P4 (line ~3154) and its restart plan (~3206).
  - BF#35 (~7364): one environment, one success criterion.
  - BF#36 (~7418): B9, our perception and planner on THEIR execute layer,
    their files unedited (parked by BF#37).
  - BF#37 (~7507): our arm's execution stays physical; one success test
    read on each arm's final executing world, with their own reward
    reported beside it.
  - #P5 (~8885): consider adopting their controllers.
  - BF#59 and BF#62: the die-slip fixes, on by default.
  - BF#63: the generated-scene eval; its STATE.md is in `bf/BF63_gen_scenes/`.
- When present, `archive/tampura_bridge_plan_2026-10-25/wire_sb_into_tampura/`:
  a reviewed argument Hani asked for on 2026-11-06 for running their system
  almost entirely (their env, physics and controllers) with as much of
  Semantic Boxels wired into it as possible. Read it before answering Route.
- Your auto-loaded memory holds Hani's standing rules: no plan
  post-processing, no bridge-only tuning, no "faithful" naming,
  seed-for-seed evals, cluster only with his explicit approval, and the
  bridge gates read in full with their exit code.

## Questions the plan must answer

Each answer is backed by file:line in both trees.

1. **Route.**
   - The options: the one-episode harness (our pipeline inside one TAMPURA
     action, as for find_dice); a per-step B9-style bridge (our planner
     chooses inspect, pick and drop, and their execute functions run
     them); or a hybrid.
   - Which route keeps one environment and one criterion, which keeps the
     setup closest to theirs, and what each costs.
   - The survey says the one-episode harness cannot express this task's
     outcomes: their observation holds one detected object and one grasp,
     and on(o, bowl) is learned only from an action named `drop`. Check
     that.
2. **Class uncertainty with no object models** (see above): how our arm
   meets the same uniform prior and the same `inspect` reveal.
3. **The capabilities our pipeline lacks, one work item each.** Candidates:
   - a per-object class belief and an inspect (sense) action that returns
     a label;
   - the bowl as a place region, and drop into the bowl;
   - the break rule (how our arm meets the same coin flip);
   - the goal in our PDDL;
   - detection of objects we have no model of, and how the registry
     represents them;
   - grasps for these shapes planned from perception, with no grasp
     library;
   - scoring of several objects.

   For each item: what exists today (file and function), what is new, where
   it goes, how it is tested, which gates it touches (G1, G2, G7, G11, G13,
   G19 and the rest), its effort, and the deviations it creates.
4. **The one success criterion** (BF#35, BF#37): read on each arm's final
   executing world. Say how "in the bowl" and "broken" are decided for both
   arms; their reward is reported beside it.
5. **Scenes and seeds:**
   - their 20 scenes, pinned as in BF#63;
   - whether to generate more with their generator;
   - TAMPURA's cost per episode on our machines.
6. **Eval design:**
   - arms, repetitions, the wall cap, BF#63's validity rule, paired
     statistics;
   - where it runs (the cluster needs Hani's approval);
   - expected wall time.
7. **Feasibility before the ICAPS deadline (2026-12-04):**
   - the critical path, a minimal version and what to cut;
   - with TAMPURA near its ceiling, what result would be informative
     (success, steps, time), and what the no-model test can show on its own.
8. **Risks, and Hani's questions:** Q-numbers continue the audit's (grep
   for the highest).
9. **Deviations:** the complete D-list, reported as above.

## How to run it

Hani asked for ultracode, so orchestrate with workflows. His rules still
hold:

- justify each launch in chat first;
- the confirm-agent-launch hook asks him before each one;
- at most four top-tier agents at once, and Sonnet or Haiku for sweeps;
- every agent writes its results to a file as it goes.

Suggested phases, reading each result before the next:

1. Understand. Parallel readers, each returning a map with file:line:
   - their class_uncertain env, generator, scenes and config, and the
     planner pieces it uses;
   - our perception and registry (what it can do with no object model);
   - our planner and domain;
   - our execution and grasping;
   - our bridge, harness and gates.
2. Design. Two or three independent route designs, judged against one
   environment and one criterion, the no-model rule, closeness to their
   setup (the deviations each creates), effort and the deadline.
3. Adversarial verification of every claim in the chosen plan against the
   code.
4. A completeness critic, which also hunts for deviations nobody listed.
5. Write PLAN.md.

Allowed probes:

- read-only runs of their class_uncertain env in WSL from a scratch working
  directory, as in BF#63;
- the venvs: arm T `/root/tampura-work/.venv`, arm O `/root/armO-venvA`;
- `PYTHONPATH=<export>:/mnt/c/Users/HaniAlassiriAlhabbou/git/pddlstream_lib:/root/tampura-work/tampura:/root/tampura-work/tampura_environments`;
- under `flock /root/sb_pipeline.lock`.

Their tree stays untouched. Log any data you make in DATA_LEDGER.md and
delete it as soon as it is garbage. No cluster runs, no pipeline edits, no
implementation.

## Deliverables, then stop

- In this folder: `PLAN.md` and `STATE.md`. Update STATE.md at every phase
  end: Hani compacts with a plain /compact, so nothing a continuation needs
  may live only in chat.
- PAPER_AUDIT.txt: one new BF# entry before #P5. Grep the whole checkout
  for the number before you claim it. Stage only your own hunk: other
  sessions hold unstaged hunks there.
- Local commits with one-line subjects and no trailer. Never push.
- When the plan is delivered, delete the `go` section of CLAUDE.md, which
  points here.
- Report to Hani:
  - the full DEVIATIONS list, again, in full;
  - the recommended route;
  - the work items with their effort;
  - his questions;
  - feasibility against the deadline.

  Then stop.
