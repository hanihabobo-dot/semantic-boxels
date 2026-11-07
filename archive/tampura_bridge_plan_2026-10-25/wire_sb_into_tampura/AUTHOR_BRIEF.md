You are writing the strongest honest argument FOR one strategic direction in a robotics research project, plus a concrete picture of how it would look. A fresh reviewer will attack your document afterwards and you will be asked to answer the review, so make every claim checkable.

## The request (Hani, the PhD student who owns the project, 2026-11-06, verbatim)

He quoted this paragraph from an earlier AI report about TAMPURA's tool_use task:
"Strongest counterargument. Structurally this is the closest task to his current model. M8 already gates pick on a "pose known" literal, has an observe action that establishes it, and supports stacking, on a 100 g, 40 mm cube class the size and mass of theirs. A world-state version of their "on" test would be easy to write. Sensing against non-prehensile funnelling could be an interesting contrast."

and wrote: "i think we should try to amlost run their system enietrly . theor env and phiscs and what not. and basily amost just wiring as much of sb into their system as possible. make any agnet make a strong, review surrvied argument for thatand how that could look like."

So: argue for running TAMPURA's system almost entirely (their environments, physics, controllers / execute functions, and their belief update and scoring where needed), with as much of Semantic Boxels (SB) wired into it as possible, and show concretely what that would look like.

## Background

Hani (ICAPS 2027 paper due 2026-12-04) built Semantic Boxels: a Panda arm in PyBullet that perceives a table scene, splits it into semantic regions (boxels, including shadows where hidden objects may be) and plans with PDDLStream (the M8 domain, pddl/domain_pddlstream_m8.pddl) to find and fetch hidden objects, executing physically. He compares SB with TAMPURA (Curtis et al., arXiv 2403.10454: belief-space planning with learned outcome models and LAO*) on TAMPURA's find_dice task through a bridge (tampura_bridge/, branch tampura-bridge): today our whole pipeline runs inside ONE TAMPURA action (policy.py, the boxel_episode schema) and scoring.py hands their belief one terminal observation. BF#63 compares both arms on 40 scenes from their generator.

Read first, in archive/tampura_bridge_plan_2026-10-25/class_uncertain/: TAMPURA_TASKS_SURVEY.md (each TAMPURA task, paper numbers, fit verdicts), no_fit_case.md (an agent's case that tool_use, puck_slide and slam_collect do not fit; section 0 lists Hani's constraints, section 1 is tool_use, section 4 compares) and BRIEF.md (the brief for a class_uncertain plan; on 2026-11-06 Hani withdrew its object-model assumption: our arm gets NO prior models of the task objects, the setup stays as identical to theirs as possible, and every deviation is reported). The binding decisions are in PAPER_AUDIT.txt (grep the headers; line numbers drift): #P4 (~3154) and its restart plan; H1 to H4 (~3256-3273; H1: no welds, no teleports of task objects, no ground-truth reads and no reads of TAMPURA's belief or world internals feeding any decision); G1 (~3285-3313, world writes allowed only on an allowlist); BF#35 (~7364, one environment and one success criterion); BF#36 (~7418, B9: our perception and planner on THEIR execute layer, their files unedited); BF#37 (~7507, B9 parked: our arm's execution stays physical); #P5 (~8885, consider adopting their controllers). TAMPURA's code is in WSL under /root/tampura-work (planner: tampura/tampura; envs: tampura_environments/tampura_environments/<task>/env.py; their policy and rollout loop: tampura/tampura/policies/).

## What the document must contain

Output: archive/tampura_bridge_plan_2026-10-25/wire_sb_into_tampura/ARGUMENT.md (create the folder). Sections:
1. The case in one page: why running their system and wiring SB into it is the right move for the paper, honestly argued.
2. The architecture: which SB parts plug in where (for example SB's perception, registry and M8 planner as a TAMPURA policy, or as the chooser of THEIR actions step by step, B9 generalised), what stays theirs (env, physics, controllers, belief, reward), the interfaces with file:line on both sides, and what would be new code.
3. Per task: tool_use as the worked example (Hani's trigger: how SB's pose-known gating, observe and stack would map onto their pick, place, stack and pull-towards; what their kinematic executor and belief-based scoring change about the no-fit case's objections, including the measured fact that their cubes fall through each other under their collision filters); class_uncertain (the active plan; under the no-object-model rule); find_dice (what changes against today's one-episode harness, and what that would mean for BF#63's results); puck_slide and slam_collect one short paragraph each (another agent writes the full puck_slide argument; do not duplicate it).
4. Which of Hani's rules the direction relaxes (BF#37, H1, G1, others) and keeps (BF#35), why each relaxation is worth it, and what it costs the paper's claims.
5. What the paper could claim with it, and what it could no longer claim.
6. Effort and order of work before 2026-12-04 (estimates, marked as such), and the minimal version.
7. Risks.
8. The strongest objections you can foresee, each with your answer.
9. Decisions Hani must make, numbered, each with options and your recommendation.

## Rules (Hani's; all binding)

- Windows repo C:\Users\HaniAlassiriAlhabbou\git\Semantic_Boxels. Shell: the PowerShell tool only (never the Bash tool: it crashes this machine). Linux via `wsl -e bash -c "..."`; put any multi-line Python or shell in a file inside your output folder and run that file. Read-only git commands only.
- Write only inside your output folder. Do not commit, stage, push, stash, or create or switch branches. Do not edit PAPER_AUDIT.txt, DATA_LEDGER.md, CLAUDE.md or any code. Delete nothing; list every file you made in your final reply.
- TAMPURA's tree is READ ONLY: never write under /root/tampura-work (PYTHONDONTWRITEBYTECODE=1 for any run). No cluster, no runs of our pipeline. Reading code is enough for this job.
- Never touch anything under C:\O\ (company documents) and never read PowerShell's $PROFILE.
- Do not start subagents or workflows.
- Prose: no em dashes or en dashes (use commas, colons, parentheses or new sentences); never the word "faithful"; plain, measured wording, no hype.
- Evidence: every claim about code carries file:line (ours relative to the repo; theirs as a path under /root/tampura-work). Mark anything you did not check UNVERIFIED and every estimate as an estimate.
- Write the document early and keep updating it as you go, so nothing is lost if you are interrupted.

When done, reply with at most 15 lines: the file path, the verdict in one line, the architecture in 3 to 5 lines, the effort, and Hani's decisions.