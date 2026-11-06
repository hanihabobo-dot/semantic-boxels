# Brief: a friendly page on TAMPURA's other tasks (API agent, 2026-11-04)

A Claude Code session of Hani's (repo Semantic Boxels, session "Project status") started you to do the token-heavy part of one task. Work alone from start to finish, then stop. That session reviews your files, publishes the page and commits it.

HERE = C:\Users\HaniAlassiriAlhabbou\AppData\Local\Temp\claude\daf52595754199fd\51cd96d5-10bf-427e-8447-fd89558bdaa4\scratchpad\task_page
WSL sees HERE as /mnt/c/Users/HaniAlassiriAlhabbou/AppData/Local/Temp/claude/daf52595754199fd/51cd96d5-10bf-427e-8447-fd89558bdaa4/scratchpad/task_page
Always write HERE in this long form (never the C:\Users\HANIAL~1 short form): the runner only lets you write freely inside HERE as spelled.

## 1. The task

Hani asked (verbatim): "make an html where you explain with screenshots why what each other task is in greate dtail and what the ai said about its fitness. make the file look freindly and nice".

Context. Hani (PhD student; ICAPS 2027 paper due 2026-12-04) built Semantic Boxels: a Panda arm in PyBullet that perceives a table scene, splits it into semantic regions (including "shadows" that hidden objects may sit in) and plans with PDDLStream to find and fetch hidden objects. He compares it with TAMPURA (Curtis et al., https://arxiv.org/abs/2403.10454, a belief-space planner that learns outcome models and plans with LAO*) on TAMPURA's own find_dice task: a die hidden under one of several upside-down cups. The question behind this page: could his pipeline also run on TAMPURA's OTHER tasks?

- The other tasks, with the paper's ids: class_uncertain (A, class uncertainty), tool_use (B, pose uncertainty), puck_slide (D, physical uncertainty), slam_collect (E-M, SLAM with manipulation; plus a manipulation-free variant E-MF; which repo variant E-MF is, is unverified). find_dice (C, partial observability) is the reference: the task already bridged and being compared. find_dice_simple (one visible die, not in the paper) is a footnote.
- "What the AI said" means two earlier AI reports, copied into HERE\sources\:
  - TAMPURA_TASKS_SURVEY.md: a survey agent read their code and the paper. Per task: goal, objects, hidden variable, actions, observations, reward, scenes and seeds, config, paper numbers, and a fit verdict (class_uncertain PARTIAL; tool_use, puck_slide, slam_collect NONE; find_dice_simple good only as a smoke test). Section 8 is a summary table, 9 a ranked shortlist, 10 the unverified list.
  - no_fit_case.md: a second agent was asked to convince Hani that tool_use, puck_slide and slam_collect are no fit. Per task: what the task is, the case on three tests (RUN, METHOD, TIME; section 0 defines them and Hani's constraints), the strongest counterargument, whether it survives, the cheapest path to a fit with its cost, and what that would show. Section 4 compares the three: tool_use is the closest call, slam_collect the clearest no fit. It measured with a small PyBullet probe that tool_use's cubes fall through each other under their collision filters.
- class_uncertain now: a separate session is writing an implementation plan from the survey's partial fit (no plan exists yet; say "a plan is being written", nothing more).

The page explains each task in detail with screenshots of its scene, and shows what the two reports concluded about its fit for Hani's pipeline.

## 2. Hard rules

- Create and change files only inside HERE.
- TAMPURA's code is in WSL at /root/tampura-work. It is READ ONLY for you: never create, change or delete anything under it (no edits, no pip, no .pyc: always set PYTHONDONTWRITEBYTECODE=1). Read it freely (sed -n, grep, ls, cat).
- In WSL you may create one scratch folder, /root/task_shots, holding only the folders and symlinks of 3.1. Nothing else outside HERE.
- Never delete anything, not even your own files: list leftovers in REPORT.md. The session that started you deletes them.
- Never touch anything under C:\O\ (company documents). Do not read PowerShell's $PROFILE: it lives there.
- The Windows shell is PowerShell; reach Linux with wsl -e bash -c "...". Nested quotes break easily: write any Python or multi-line shell into a file in HERE and run that file, e.g. wsl -e bash -c "bash /mnt/c/Users/.../task_page/shots.sh".
- No git commands, no web fetches or searches, no publishing anywhere.
- Prose rules from Hani: no em dashes and no en dashes anywhere on the page (use commas, colons, parentheses or new sentences; hyphens inside names such as find_dice or pick-and-place are fine). Never the word "faithful". Plain, measured, friendly wording: no marketing language, no hype, no emoji.
- Facts: everything on the page comes from sources/ or from what you see in their code or your renders. Keep the reports' UNVERIFIED marks: put a small "unverified" tag on every such item (implied success rates, effort estimates, the E-MF variant, DROPABILITY 0.85 or 0.35, and so on). Put a "measured" tag on the probe's results. Never invent a number. Summarise in your own words, shorter than the sources; no long quotes.
- Cost: the runner caps this session at $20; aim for well under. Read each source once, do not re-read big files, do not view an image twice unless you changed it.

## 3. Step 1: screenshots of each scene

### 3.1 Setup (WSL)

    mkdir -p /root/task_shots/tampura_environments/class_uncertain /root/task_shots/tampura_environments/find_dice
    ln -s /root/tampura-work/tampura_environments/env_configs /root/task_shots/env_configs
    ln -s /root/tampura-work/tampura_environments/tampura_environments/class_uncertain/problems /root/task_shots/tampura_environments/class_uncertain/problems
    ln -s /root/tampura-work/tampura_environments/tampura_environments/find_dice/problems /root/task_shots/tampura_environments/find_dice/problems

Their loaders use paths relative to the cwd (./env_configs/<task>.yml, tampura_environments/<task>/problems), so run with cwd /root/task_shots. Python: /root/tampura-work/.venv/bin/python with PYTHONPATH=/root/tampura-work/tampura:/root/tampura-work/tampura_environments and PYTHONDONTWRITEBYTECODE=1. Keep your scripts in HERE (not in /root/task_shots), so the cwd is not on sys.path. The venv has pybullet, numpy 1.24, PIL 12.2 and matplotlib 3.10; DejaVu fonts are in /usr/share/fonts/truetype/dejavu/.

### 3.2 Build each scene exactly as their runner does

    import random, numpy as np
    from tampura.config import config as tconfig
    import tampura_environments  # registers the tasks
    cfg = f'./env_configs/{task}.yml'
    config = tconfig.load_config(config_file=cfg, arg_dict={'config': cfg, 'global_seed': 0, 'vis': False, 'save_dir': SAVE_DIR})
    random.seed(0); np.random.seed(0)
    env = tconfig.get_env(config['task'])(config=config)
    env.initialize()

This is what their run_planner.py and Hani's tools/run_tampura_timed.py do. Use seed 0 (their default global_seed) for every task and say "seed 0" in the captions. SAVE_DIR goes inside HERE, e.g. HERE/shots/run_<task> (slam_collect writes its frames there). Their env files are /root/tampura-work/tampura_environments/tampura_environments/<task>/env.py.

### 3.3 Where each scene lives

- class_uncertain: render env.state.world (a SceneState's World); world.client is its PyBullet client. world.objects are the 3 movable YCB objects; world.categories are the scene's categories, "bowl" among them (pair the movable objects with the non-bowl categories in order); the bowl's body is world.regions[1]. Fruit classes: apple, lemon, strawberry; ball classes: tennis_ball, racquetball, baseball (env.py:30-31). Objects lie in x 0.3 to 0.7, y -0.4 to 0.4; setup already ran gravity and 2000 settle steps (env.py:286-400).
- tool_use: render env.world (a HookWorld). world.objects = [cube0, cube1, cube2, hook]; world.ghosts = {cube_id: [cube_id and its 9 particle ids]}, where the first id of each list is the real cube. All ten copies of a cube are orange with alpha 0.2 and scatter about 2 cm around one mean. The hook lies at (0.1, -0.35, 0.02), yaw -30 deg; the table is lengthened by 0.5 m in x; cube means lie in x 0.4 to 0.7, y -0.3 to 0.3 (env.py:28-75, 180-320, 577-600).
- puck_slide: render env.state.world (a PuckState). world.objects are 20 pucks on one start pose: index 0 is the real puck (alpha 1), the other 19 are particles (alpha 0.2) on the same spot. The robot stands at the origin on a stool; the slab spans x 0.3 to 1.4, y -0.35 to 0.35, top at z 0.05; the reach ("ik") region is x 0.3 to 0.9; the goal is x 1.2 to 1.4 (black lines and number marks; only goal0 counts); the puck starts at x 0.39 (env.py:28-120, 232-385, 676-700). A fully transparent "surface" box (rgba alpha 0) spans x -0.3 to 1.4 at z 0.045 to 0.055. TinyRenderer may ignore alpha and draw it black over the lines: if so, find the bodies whose visual alpha is 0 (getVisualShapeData) and move them far away in your own in-process copy before rendering.
- find_dice (reference): render env.world; world.objects and world.categories: the die's category contains "dice", the cups are *_cups_ud. Seed 0 picks one of the 3 shipped layouts in find_dice/problems. Ring the die, which sits hidden under a cup. sources/overview_views.py is working camera code for find_dice (oblique eye (1.45, -0.35, 1.25) to target (0.40, 0, 0.15), up (0, 0, 1); top eye (0.45, 0.01, 0.94) to (0.45, 0.01, 0), up (1, 0, 0); fov 55, near 0.05). It ran in another venv and seed; adapt it.
- slam_collect: no PyBullet, a 2D numpy and matplotlib world of 10 m by 10 m. env.initialize() itself calls their plot_trajectories([[state]], save_dir), which writes SAVE_DIR/frames/frame_000.png: their own drawing (green goal circle, grey obstacles, yellow targets, blue beacons, purple robot). Set matplotlib.rcParams['savefig.dpi'] = 200 before initialize() for a sharper copy. Then draw your own labelled map from env.state (a SlamState: robot, obstacles, beacons, targets, corners, goal; each a Region with .pose (x, y, theta) and .shape (width, height); a beacon's Region shape is its 2 m vision square around a 0.4 m beacon; targets are 0.5 m squares; the goal is a 0.8 m square at (8, 8); the robot a 0.3 by 0.6 m box at (1, 1), heading 1 rad; the corners are the four map corners), with a legend and a few labels such as "beacon: drive into its square to learn your exact position" and "goal: bring all three targets here". Also build slam_collect_simple (20 obstacles; the goal is only to reach the goal square) at seed 0 and keep their own frame of it (slam_collect/env.py:28-60, 443-465, 938-1062, 1214-1372, 1536-1604).

### 3.4 Rendering

- getCameraImage at 2048x1536 with renderer=p.ER_TINY_RENDERER (try shadow=1 with a lightDirection; drop the shadows if they look bad), then downsample to 1024x768 with Image.LANCZOS for smooth edges. View matrix p.computeViewMatrix(eye, target, up); projection p.computeProjectionMatrixFOV(fov=55, aspect=4/3, nearVal=0.05, farVal=10).
- Two views per 3D task: an oblique overview that shows the robot and the whole workspace, and a top view of the workspace. Choose the cameras per task (puck_slide's slab is long in x: a top view with up (0, 1, 0) puts x to the right).
- tool_use: TinyRenderer probably draws the alpha 0.2 copies solid (check). Show the real cube solid and its nine particles see-through: render once with everything (keep the segmentation buffer: by default each pixel holds its body id), once with the 27 particle bodies moved away (z -5), then blend the particle pixels of the first render over the second at about 35 % opacity. Say so in the caption: in their own viewer all ten copies are see-through; here the real cube is drawn solid.
- Labels go into the PNG with PIL: DejaVuSans-Bold at about 20 px, dark text on a white rounded box with a thin outline, and a dot or short leader line at the object. Project a world point with V = np.asarray(view).reshape(4, 4).T, P = np.asarray(proj).reshape(4, 4).T, clip = P @ V @ [x, y, z, 1], px = (clip[0]/clip[3] + 1)/2*W, py = (1 - clip[1]/clip[3])/2*H (as in sources/overview_views.py). Shade regions (puck_slide's reach region and goal; class_uncertain's bowl if it helps) with a translucent polygon from projected corners. 2 to 5 labels per image; a label never covers the thing it names.
  - class_uncertain: each object's true class, e.g. "strawberry (fruit)", "baseball (ball)", and "bowl". Caption: the robot does not know these labels; each object starts with a uniform belief over all six classes.
  - tool_use: "cube 0 and 9 guesses" (and so on), "hook (pose known)".
  - puck_slide: "puck (friction unknown)", "reach region", "goal".
  - find_dice: a red ring and "die (hidden under this cup)".
- Look at every PNG yourself (the Read tool shows images) before you use it; fix cameras or labels that crop, occlude or mislabel. Keep about two images per task, plus the slam_collect_simple frame. The page's images go in HERE/img/, named <task>_<view>.png. Leave rejected renders where they are and list them in REPORT.md.
- Write HERE/img/MANIFEST.md: per image the task, seed, camera (eye, target, up, fov), labels and the command that made it, so it can be regenerated. Keep the render scripts in HERE.

## 4. Step 2: the page

Files: HERE/index.html, with its images in HERE/img/ (src="img/<name>.png"). It will be published as a claude.ai artifact, which allows one HTML document with inline CSS (no JavaScript needed); fonts only from Google Fonts (a fonts.googleapis.com stylesheet); images only from its own files by relative path or data: URIs; nothing else external loads. Links to other sites are fine as plain <a href> (link the paper).

Content, in this order:
1. Header: a short name as both <title> and h1 (2 to 4 words, e.g. "TAMPURA's other tasks"; no colon or dash followed by an explanation), then 2 to 3 sentences: what TAMPURA is, what the page covers, what "fit" means here (no_fit_case.md section 0: RUN, METHOD and TIME, in plain words).
2. At a glance: a summary table, one row per task: task, paper id, what is hidden, scenes and seeds, TAMPURA's published return (with its standard error) and the implied success (tagged unverified), verdict badge. Then the bottom line in one or two sentences (none of the three no-fit tasks hides anything in space; only find_dice renders images; class_uncertain is the partial fit being planned).
3. One section per task: find_dice first as the reference, then A class_uncertain, B tool_use, D puck_slide, E slam_collect (with slam_collect_simple inside it). Each section has:
   - its name, paper id, a verdict badge (Reference / Partial fit / No fit; add "closest call" for tool_use and "clearest no fit" for slam_collect) and one plain sentence on what the task is;
   - the screenshots with captions (what you see, seed 0, rendered from their code);
   - "The task in detail": the goal and how success is scored (on the belief or on the physical world), the objects, what is hidden, the actions, what the robot observes, scenes and seeds, notable config;
   - "In the paper": TAMPURA's return and standard error, the strongest other method, seconds per step, executed steps, implied success (unverified);
   - "What the AI said": for class_uncertain, the survey's partial-fit reasoning (what fits, what is missing, effort, limits) and that a plan is being written; for tool_use, puck_slide and slam_collect, the no-fit case on RUN, METHOD and TIME, the strongest counterargument, whether it survives and why, the cheapest path to a fit with its cost and what it would show, and the survey's verdict in one line; for find_dice, what it is used for (the comparison already running; give no result numbers).
4. Side by side: no_fit_case.md section 4's table of the three no-fit tasks.
5. Bottom line and next steps: the survey's section 9 shortlist in plain words (class_uncertain; more find_dice layouts from their own generator; find_dice_simple only as a smoke test).
6. Footer: the sources (the two reports' file names), "screenshots rendered at seed 0 from TAMPURA's own environment code, read-only", date 2026-11-04.

Design: friendly and nice, calm and readable, not flashy.
- Begin the <style> with a :root block: 4 to 6 named color tokens, font tokens (display, body) and a one-line comment on the layout idea. The light palette is complete in :root; redefine the tokens for dark under @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } } and again under :root[data-theme="dark"]; set color-scheme in each; give body an explicit background from a token; style everything through the tokens.
- Pick a display face and a body face from Google Fonts, with real fallback stacks. Avoid Inter and Space Grotesk; avoid cream with serif and terracotta, purple-to-blue gradients, and near-black with acid green.
- Running text about 65 characters wide, one type scale, headings with text-wrap: balance, tabular-nums in tables.
- Verdict badges in semantic colors that also carry the word (reference, partial fit, no fit); small "unverified" and "measured" tags.
- Sections with consistent padding and edges; screenshots as figures with captions (max-width: 100%, rounded corners, a light border); two images side by side on wide screens, stacked on phones.
- Works at phone width (about 400 px): at least 16 px side gutters, every table inside an overflow-x: auto wrapper, no sideways scrolling of the page.
- Everything readable without clicking (details and summary only for optional extra depth). Visible keyboard focus on links. A short table of contents linking to each task section is welcome.

Self-check before you finish: the HTML parses (for example with Python's html.parser in WSL and a tag-balance check), every img src exists in HERE/img, there is no em dash (U+2014) or en dash (U+2013) anywhere (search for both), no "faithful", every number on the page matches sources/, and every unverified item carries its tag. Note the total size of img/.

## 5. Step 3: report and stop

Write HERE/REPORT.md last: the session that started you waits for this file. List the files you made, one line per image, what you could not do or are unsure about, facts you could not confirm, the leftovers to delete (rejected renders, /root/task_shots), and the cost the runner shows if you can see it. Then end your turn with a 3 to 5 line summary. Do not wait for more instructions.
