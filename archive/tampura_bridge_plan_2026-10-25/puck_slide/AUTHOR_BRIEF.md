You are writing the strongest honest argument FOR running a robotics research system on one benchmark task that an earlier report judged a "no fit", plus a concrete design. A fresh reviewer will attack your document afterwards and you will be asked to answer the review, so make every claim checkable.

## The request (Hani, the PhD student who owns the project, 2026-11-06, verbatim)

"for puck_slide the same, let an aagent make a trong arument for it. so we need to do some modleing and new actions, but we we might use these actions later. but still make sure that we would be working on another branch where we be building a version just for this task becuase it seems that this is what they in tamoura have done. some of the input is unknown so we make a version of our model with the pick actions, we should measure how much did ading it costs us btw on some or our envs tasks and ttampuas taskas well. so we need to also come up with an action that helps us test how slipery it is unless you have some other suggtions and how are we suppoes to know how get it right."

("the same" = he had just asked for a strong, review-survived argument for another direction; "pick actions" most likely means the new push actions; say how you read it.)

## Background

Hani (ICAPS 2027 paper due 2026-12-04) built Semantic Boxels (SB): a Panda arm in PyBullet that perceives a table scene, splits it into semantic regions (boxels, including shadows where hidden objects may be) and plans with PDDLStream (the M8 domain, pddl/domain_pddlstream_m8.pddl; known-literals and sense actions in a POD model) to find and fetch hidden objects, executing physically (execution.py). He compares SB with TAMPURA (Curtis et al., arXiv 2403.10454) on TAMPURA's find_dice task through a bridge (tampura_bridge/, branch tampura-bridge).

TAMPURA's puck_slide (paper task D, "physical uncertainty"): push a 12 cm, 1 kg puck along a slab into a goal 1.2 to 1.4 m from the robot; the hidden variable is the puck's friction (uniform 0.05 to 0.15); TAMPURA uses push-to and nudge actions, a 20-particle friction belief, a push controller that runs five practice trials and resets the real puck between them, and a reward that follows the real puck's observed pose. Code in WSL: /root/tampura-work/tampura_environments/tampura_environments/puck_slide/env.py; config /root/tampura-work/tampura_environments/env_configs/puck_slide.yml.

Read first, in archive/tampura_bridge_plan_2026-10-25/class_uncertain/: TAMPURA_TASKS_SURVEY.md (section 3 is puck_slide), no_fit_case.md (section 0 lists Hani's constraints; section 2 is the case against puck_slide, its strongest counterargument and the cheapest fit; section 4 compares). Also PROPOSAL_ATTRIBUTE_BOXELS.md at the repo root (untracked; Hani's 2026-11-06 idea, BF#66, to boxelize distributions and attribute values: friction is such an attribute; say whether and how it fits). Binding decisions in PAPER_AUDIT.txt (grep the headers; line numbers drift): H1 to H4 (~3256-3273; H1: no welds, no teleports of task objects, no ground-truth reads and no reads of TAMPURA's belief or world internals feeding any decision); G1 (~3285-3313); BF#35 (~7364, one environment and one success criterion); BF#36 and BF#37 (~7418, ~7507: B9 on their execute layer, parked; our execution stays physical); #P5 (~8885, consider adopting their controllers); audit #53 (push removed from SB: grep "compute_push_displacement"). Another agent is writing, in parallel, a general argument for running TAMPURA's own system with SB wired into it; mention where that matters, do not duplicate it.

## What the document must contain

Output: archive/tampura_bridge_plan_2026-10-25/puck_slide/ARGUMENT.md (create the folder). Sections:
1. The case in one page, honestly argued, including what a result would show the paper's readers.
2. Modelling the unknown friction in SB's terms (a known-literal, a discretised belief, attribute boxels, or something else), and why.
3. New actions: push-to, and an action that tests how slippery the puck is (TAMPURA's nudge is one option; compare at least two others and recommend one). Which of them could be reused in other SB tasks later.
4. Estimation and validation: how an observation (for example the puck's displacement) becomes a friction estimate without reading their belief or the simulator's friction (H1), and how we know we got it right (accuracy against the simulator's true friction used for evaluation only, calibration, success rate). If a small read-only probe of their env would settle a number, you may run one: in WSL make /root/ps_probe with a symlink env_configs -> /root/tampura-work/tampura_environments/env_configs, run their venv /root/tampura-work/.venv/bin/python with PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments and PYTHONDONTWRITEBYTECODE=1 from that cwd, keep scripts and outputs in your output folder, and list /root/ps_probe in your final reply.
5. The push controller: theirs resets the real puck between practice trials (a teleport under H1); design ours without that, or argue for adopting theirs and what that costs.
6. The branch: Hani wants the implementation on its own branch, a puck_slide-specific version of SB, as TAMPURA has per-task environments. Say what goes on that branch, what could later move back to the main line, and the branch's name and base. Do not create it.
7. The cost of the added modelling and actions: a measurement design for how much they slow or change SB on our own tasks (find the task modes in test_full_pipeline.py) and on TAMPURA's tasks (find_dice; class_uncertain later): arms, seeds, metrics (planning time, success, plan length), where it runs (cluster runs need Hani's explicit approval).
8. The shared success criterion (their reward follows the real puck) and reach and grasp limits (puck wider than the gripper, goal beyond reach).
9. Effort and order of work before 2026-12-04 (estimates, marked as such), the minimal version, risks.
10. The no-fit case's objections (no_fit_case.md 2.2 and 2.4), each with your answer, conceding what you cannot answer.
11. Decisions Hani must make, numbered, each with options and your recommendation.

## Rules (Hani's; all binding)

- Windows repo C:\Users\HaniAlassiriAlhabbou\git\Semantic_Boxels. Shell: the PowerShell tool only (never the Bash tool: it crashes this machine). Linux via `wsl -e bash -c "..."`; put any multi-line Python or shell in a file inside your output folder and run that file. Read-only git commands only.
- Write only inside your output folder (and the probe folder above). Do not commit, stage, push, stash, or create or switch branches. Do not edit PAPER_AUDIT.txt, DATA_LEDGER.md, CLAUDE.md or any code. Delete nothing; list every file you made in your final reply.
- TAMPURA's tree is READ ONLY: never write under /root/tampura-work. No cluster, no runs of our pipeline.
- Never touch anything under C:\O\ (company documents) and never read PowerShell's $PROFILE.
- Do not start subagents or workflows.
- Prose: no em dashes or en dashes (use commas, colons, parentheses or new sentences); never the word "faithful"; plain, measured wording, no hype.
- Evidence: every claim about code carries file:line (ours relative to the repo; theirs as a path under /root/tampura-work). Mark anything you did not check UNVERIFIED and every estimate as an estimate.
- Write the document early and keep updating it as you go, so nothing is lost if you are interrupted.

When done, reply with at most 15 lines: the file path, the verdict in one line, the design in 3 to 5 lines (friction model, test action, estimator, controller), the effort, and Hani's decisions.