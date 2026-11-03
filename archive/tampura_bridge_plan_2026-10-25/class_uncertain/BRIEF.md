# BRIEF: plan our pipeline on TAMPURA's class_uncertain task

Written 2026-11-03 by the session "Project status" for a fresh session.
Start: Hani opens a new Claude Code session in this checkout (branch
`tampura-bridge`), model Opus 5.5, effort max, and types `go` (the project
CLAUDE.md points here). Hani's request, verbatim:

> i want an opus 5.5 max ultracode to solve this. solve is make a plan about
> what needs to be done exactly to to run our code on that other task at our
> current code level. we make this assumption as we did before. we have to
> have modles of these detected objects alreeady in the system.

"That other task" is TAMPURA's `class_uncertain` (paper task A, "Class
Uncertainty"), the one task the survey (TAMPURA_TASKS_SURVEY.md, this
folder) found a partial fit for our pipeline.

## The job

A PLAN, not code: exactly what must be done to run our pipeline, at the
code level of `tampura-bridge` today, on their class_uncertain environment,
so that our arm (O) and TAMPURA (T) run in one environment under one success
criterion and the comparison is valid. A later session implements it after
Hani has answered the plan's questions. Done means:

- `PLAN.md` in this folder, concrete enough that an implementation session
  can work through it item by item without re-deriving anything;
- every claim about their code or ours carries a file:line cite that a
  verification pass has checked;
- Hani's open decisions listed as numbered questions, each with options and
  a recommendation;
- one new BF# entry in PAPER_AUDIT.txt and a STATE.md in this folder.

## Assumption A1 (Hani): the object models are in our system

"we have to have models of these detected objects already in the system",
as for find_dice, where `tampura_bridge/task_spec.py` carries the cups' and
the die's categories, mesh extents, masses and inertias measured from their
assets, each cited to a BF# entry. For class_uncertain that means the YCB
apple, lemon, strawberry, tennis ball, racquetball, baseball and the bowl
(their assets under their `models/srl/ycb`). Take A1 as given and spell out
what it implies. One implication must be faced head on: in class_uncertain
the hidden variable is each object's CLASS (a uniform prior over six
classes, revealed only by their `inspect` action), not its location. If
models plus our perception identify each object's class on sight, the
uncertainty vanishes for our arm and the comparison stops being one to one.
The plan must show how the class stays exactly as uncertain for our arm as
for theirs, or put the question to Hani with options. Do not decide it
alone.

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
  at its ceiling); 1 to 2 weeks, an unverified estimate.

A separate agent argued the no-fit case for tool_use, puck_slide and
slam_collect (no_fit_case.md here when present). It is context only, not
part of this job.

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
   - Which route keeps one environment and one criterion, and what each
     costs.
   - The survey says the one-episode harness cannot express this task's
     outcomes: their observation holds one detected object and one grasp,
     and on(o, bowl) is learned only from an action named `drop`. Check
     that.
2. **Class uncertainty under A1** (see above).
3. **The capabilities our pipeline lacks, one work item each.** Candidates:
   - a per-object class belief and an inspect (sense) action that returns
     a label;
   - the bowl as a place region, and drop into the bowl;
   - the break rule (how our arm meets the same coin flip);
   - the goal in our PDDL;
   - detection of the YCB objects, and their models under A1;
   - grasps for these shapes;
   - scoring of several objects.

   For each item: what exists today (file and function), what is new, where
   it goes, how it is tested, which gates it touches (G1, G2, G7, G11, G13,
   G19 and the rest), and its effort.
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
     (success, steps, time).
8. **Risks, and Hani's questions:** Q-numbers continue the audit's (grep
   for the highest).

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
   - our perception and registry;
   - our planner and domain;
   - our execution and grasping;
   - our bridge, harness and gates.
2. Design. Two or three independent route designs, judged against one
   environment and one criterion, A1, effort and the deadline.
3. Adversarial verification of every claim in the chosen plan against the
   code.
4. A completeness critic.
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
  - the recommended route;
  - the work items with their effort;
  - his questions;
  - feasibility against the deadline.

  Then stop.
