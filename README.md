# Semantic Boxels for Task and Motion Planning

A PyBullet-based system for generating **semantic boxels**: task-relevant 3D regions used for belief representation in Task and Motion Planning (TAMP) under partial observability. A Franka Panda robot searches for hidden objects by relocating occluders, sensing shadow regions, and retrieving targets, all planned via PDDLStream.

The pipeline runs on its own scenes (`test_full_pipeline.py`) and inside TAMPURA's `find_dice` environment (`tampura_bridge/`).

## Quick Start

### Installation (Linux and WSL)

Requirements: [uv](https://docs.astral.sh/uv/getting-started/installation/), git, cmake, make and a C++ compiler; for TAMPURA also autoconf, automake and libtool.

```bash
./scripts/setup.sh              # Python environment and PDDLStream (with FastDownward)
./scripts/setup.sh --tampura    # also TAMPURA and its find_dice environment
```

The script is idempotent. It creates the Python environment from `uv.lock` (Python 3.11, every package pinned) under the folder below, with `.venv` a link to it, clones PDDLStream at a pinned commit into `~/.local/share/semantic-boxels/` (`$XDG_DATA_HOME` is respected), builds its FastDownward and links it to `pddlstream_lib`. With `--tampura` it also clones TAMPURA and `tampura_environments` at the commits used for the paper's runs into `~/.local/share/semantic-boxels/tampura-work`, applies the one declared import fix (`tampura_bridge/patches/`) and installs TAMPURA into the environment through uv, which builds its SymK planner (CPU-only torch). `SB_DEPS_DIR`, `SB_TAMPURA` and `UV_PROJECT_ENVIRONMENT` move the checkouts, the TAMPURA workspace and the environment elsewhere; the checkouts and the environment (which holds TAMPURA) must stay outside the repository, because the bridge's gate G13 counts every file under it as our code. `PDDLSTREAM_PATH` points the pipeline at another PDDLStream checkout. For the GUI under WSL, `export DISPLAY=:0 LIBGL_ALWAYS_SOFTWARE=1`.

```bash
./run.sh boxels --headless                       # one episode on our own scene
./run.sh tampura --seed 113 --gen --headless     # one episode on a TAMPURA find_dice scene (needs --tampura)
uv run pytest                                    # the unit tests
```

Or directly: `uv run python -u test_full_pipeline.py --no-gui --scene random-pairs --seed 0 --goal holding --n-occluders 2`. Without `--no-gui` it opens the PyBullet GUI.

The pinned versions live in `uv.lock`; for a pip-style list, run `uv export --format requirements-txt --no-hashes --group tampura`.

### Linux without Windows

`run.sh` is the same launcher in bash, for a plain Linux machine (it also works inside WSL). It starts the same commands as `run.ps1`, takes the same words and flags, in Linux spelling or in `run.ps1`'s (`--seed 7` and `-Seed 7` both work), and finds the checkout from its own place. Three environment variables tell it about the machine, each with a default: `SB_PYTHON` (the Python that has the packages above; default `.venv/bin/python` in the checkout, then `python3`), `SB_TAMPURA` (the TAMPURA workspace holding `tampura/` and `tampura_environments/`, needed for `run tampura` only; default `~/.local/share/semantic-boxels/tampura-work` as `scripts/setup.sh --tampura` makes it, then `~/tampura-work`) and `SB_LOCK` (the lock file that keeps episodes one at a time; default under `$XDG_RUNTIME_DIR` or `/tmp`). It needs `flock` (util-linux) and, to notice a closed GUI window, `xwininfo` (x11-utils).

```bash
./run.sh                           # the bridge episode on TAMPURA's find_dice, seed 0, in the GUI
./run.sh tampura --seed 118,102 --gen --headless   # several seeds, one run after another
./run.sh boxels --seed 3 --headless
./run.sh boxels --look boxel --eye arm
./run.sh wumpus --seed 3 --size 10
./run.sh ps                        # the pipeline processes alive;  ./run.sh kill  ends the ones run started
./run.sh help                      # the usage header of run.sh;  --dry-run prints the command instead
```

Two things of `run.ps1` are Windows only: the separate camera window of `-Draw cameras` (the pictures are still saved into the run's `cameras` folder, and the GUI still draws the view volumes) and the sounds of `--music`, `--sfx` and `--voice` (played by Windows PowerShell through WSL; elsewhere the run is silent).
### Windows

`run.ps1` starts the pipeline inside WSL in one word, from PowerShell 7 (`pwsh`). Two short pointer scripts, `run.ps1` and `boxels.ps1`, kept outside the repository in a folder on the PATH, call the repository's script, so `run` and `boxels` work from anywhere; without them, `.\run.ps1` and `.\run.ps1 boxels` from the repository root do the same. The paths at the top of `run.ps1` (the checkout as WSL sees it, the Python interpreter) and the TAMPURA workspace path in its `tampura` command are those of the development machine; set them for another one.

```powershell
run                          # the bridge episode on TAMPURA's find_dice, seed 0, in the GUI
run tampura -Seed 7          # another seed
run tampura -Seed [118, 102, 103] -Gen   # several seeds, one run after another (also 118,102,103 or 118 102 103)
run tampura -Headless        # no GUI, the console only; a diagnostic run, never scored
run tampura -Seed 118 -Gen   # a scene from TAMPURA's own generator (seeds 100 to 339 are committed)
run tampura -Draw boxels     # the GUI also draws the boxels, as lines and labels that follow the registry
run tampura -Draw cameras    # its own window: what each of our cameras saw at its latest render
boxels                       # our own random-pairs scene, seed 0, in the GUI (same as: run boxels)
run boxels -Seed 3 -Headless
run boxels -Scene stack -Goal stack -Occluders 0
run boxels -Args '--n-extra-distractors 1'   # more pipeline flags, one quoted string, as is
run ps                       # the pipeline processes alive in WSL
run kill                     # end every one of them
run help                     # the usage header of run.ps1
```

`boxels` runs `test_full_pipeline.py --scene random-pairs --seed 0 --goal holding --n-occluders 2`; `-Scene`, `-Seed`, `-Goal` and `-Occluders` change those values, and a run's files land in `logs/run_<timestamp>/`. `run tampura` runs the bridge driver (below), with its files under `archive/tampura_bridge_plan_2026-10-25/bf/gui_runs/`. With several seeds the runs go one after another and end with one line per seed (its outcome, wall time and, for `run tampura`, its folder); closing a GUI window goes on with the next seed, Ctrl-C stops the list, and so does another pipeline run still going when the next seed is due.

| Switch | Effect |
|--------|--------|
| `-Off` | Without the model tweaks M8 to M10 and the aperture rule |
| `-Squeeze MM` | The pick squeeze in mm (`--grip-squeeze-mm`) |
| `-Screenshots` | Also save the eye PNGs (`--save-screenshots on`) |
| `-Draw boxels` | `run tampura` in the GUI also draws the registry's boxels (`--draw boxels`): wireframes and labels by kind (shadows grey, occluders red, other objects blue), redrawn as the registry changes. Debug lines only, so the run, its world and its camera images are the same with and without it; `-Headless` ignores it (and says so), and `run boxels` draws its boxels without it |
| `-Draw cameras` | `run tampura` in the GUI also opens its own window (`tools/camera_view.ps1`: flush right on the primary screen, at low priority, free to move; it closes 20 s after the run ends, and in a seed list the window of the seed before closes when the next starts) with what each of our cameras saw at its latest render: the eye and the wrist camera, each as its image, its depth (near bright) and its segmentation (one colour per body), captioned with the render count and the plan, step and action it belongs to. The GUI also shows each camera's view volume (eight debug lines and a label). The run reads what each render returns and writes the pictures under its `cameras/` folder (`--draw cameras`); it renders nothing and changes no body, random number or result, so the run, its world and its images are the same with and without it (a planner that decides by wall clock can still answer differently from one run to the next, with or without it). The plan twin's test renders are not shown. `-Draw boxels,cameras` (or a space between the two) does both; `-Headless` ignores it |
| `-Gen` | `run tampura` on a find_dice scene from TAMPURA's own generator (`tampura_bridge/gen_scenes/`, seeds 100 to 339), started in a directory that holds only that scene |
| `-Music` / `-Sfx` / `-Voice` | Sound that follows the run: music and effects, the effects only, and Windows' voice reading the narration as well |
| `-DryRun` | Print the command instead of running it |

The sound (quiet retro synth music and effects) is opt-in through the environment variables `SB_AUDIO` (`on`, `sfx`, `music`) and `SB_VOICE` (`on`). The pipeline synthesizes it and Windows plays it through WSL's interop (`tools/console_speaker.ps1`).

`run` refuses to start while another pipeline run is alive, because two runs would race on PDDLStream's `temp/` directory. Closing the GUI window or pressing Ctrl-C ends the run. A closed PyBullet window would leave the process spinning at full CPU, so the launcher watches the window and ends what is left (`tools/run_procs.sh`), and the console makes Ctrl-C end the process at once. `run ps` flags a ghost run (its window closed) and `run kill` ends every pipeline process.

`tools/boxels.ico`, drawn by `tools/make_icon.py` (deleted in the readable migration, phase P1; its last commit is a66d95e), is the icon for a desktop shortcut to `pwsh -NoExit -File run.ps1 tampura`.

### The console and the run directory

`--log-level smart`, the default, shows a curated console: a banner, then the robot narrating its episode in the first person (what it is starting, what it sees, what it is thinking about before each plan and what the plan intends), one line per step with how the step went, the notable observations under it, warnings, and a closing verdict with one stats line. While the robot is busy, a colour pictogram of the action animates beside the status line and is erased when the activity ends. A terminal of at least 48 columns and 12 rows gets the pictogram, a smaller one gets a one-line status, and a captured console (a file or a pipe) gets plain text without colour or animation. `NO_COLOR` and `FORCE_COLOR` set the colour; `SB_CONSOLE_ASCII=1` swaps the glyphs for ASCII. The pictograms are data in `console/console_art.py`, generated by `tools/sprite_tool.py` from `tools/sprites/*.txt`.

The console reads events from the run logger and the narration; nothing in it feeds a decision. The raw stdout and stderr of the whole process (PyBullet, PDDLStream, FastDownward) go to `<run_dir>/console_debug.log`. `normal`, `quiet` and `verbose` leave the terminal raw. A script that reads the pipeline's stdout (`SUCCESS!`, the planning times) passes `--log-level normal`; under `smart` those lines are in the run's files.

Each run writes `logs/run_<timestamp>/`, which holds, among others:

| File | Content |
|------|---------|
| `run_<timestamp>.log` | Everything the run logged |
| `console_debug.log` | The raw stdout and stderr (`--log-level smart`) |
| `ledger.jsonl` | The event stream: plan results, dispatched steps with how they ended, belief changes of shadow fragments |
| `timing_summary.json` | Outcome, exit reason, plan count, planning times and the run's configuration |
| `eye.log`, `eye.jsonl` | Textual snapshots of the world, the belief and the camera view, queried with `tools/eye.py` |
| `telemetry.log`, `telemetry.jsonl` | Frame-level poses, velocities, contacts and physical events |
| `boxel_data.json`, `problem_initial.pddl` | The boxel registry and the exported PDDL problem |

The eye PNGs (`eye_<k>_camera.png`, and `eye_<k>_gui.png` under the GUI) are written only with `--save-screenshots on`. `tools/prune_runs.ps1` compacts run data after 1 day and deletes run directories that hold no git-tracked file after 14 days; `tools/prune_screenshots.ps1` deletes eye PNGs after 7 days. Both only report what they would do unless run with `-Apply`.

### Flags

`parse_pipeline_args` in `console/run_logger.py` defines the flags; the defaults below are the values in effect when a flag is absent.

**Scene and goal**

| Flag | Default | Description |
|------|---------|-------------|
| `--scene default\|mixed\|scalability\|stack\|random-pairs` | `default` | Scene preset: the hand-placed scene (3 occluders, 4 targets, all boxes); diverse shapes; random placement with the counts below; N identical cubes without occluders; a fixed occluder count with a hidden-target count drawn per seed from 1 to `--n-occluders` |
| `--goal holding\|stack\|find-and-tray-stack` | `holding` | Hold the target, hidden or visible; build a tower of `--stack-height` cubes; a two-cube tower on a tray (a visible cube on the tray, a hidden cube found by sensing on top of it) |
| `--n-occluders N` | `3` | Occluders (scalability and random-pairs scenes) |
| `--n-targets N` | `4` | Targets (scalability scene) |
| `--n-hidden N` | `0` | Targets that must be hidden from the camera at spawn (scalability scene with `--goal holding` or `find-and-tray-stack`; needs `--n-occluders >= 1`; capped at `--n-targets`; 0 leaves it to the RNG) |
| `--n-extra-distractors N` | `0` | Visible distractor targets added to the hidden ones (random-pairs scene; `find-and-tray-stack` raises 0 to 1) |
| `--n-objects N` / `--stack-height N` | `3` / `2` | Cubes in the stack scene (at least the tower height) / tower height in cubes (at least 2; `--goal stack`) |
| `--seed N` | `0` | RNG seed for scene placement and for the global `random` and `numpy.random` generators. The random-pairs scene draws a fresh seed, and prints it, when the flag is absent. Seeds are pinned: a seed whose scene cannot be built fails the pre-flight (`[pre-flight] seed N rejected`) before the GUI opens |
| `--allow-unwinnable` | off | Inspection only: the pre-flight's rejection of a `find-and-tray-stack` scene without a visible or without a hidden target becomes a warning. A scene that cannot be built aborts regardless. Never for sweeps |

With `--goal holding`, an explicit `--n-occluders` or `--n-targets`, or a positive `--n-hidden`, selects the scalability scene when `--scene` is left at `default`; `--goal stack` selects the stack scene. The random-pairs scene takes `--goal holding` or `find-and-tray-stack`, at least one occluder, and neither `--n-hidden` nor `--n-targets`.

**Planning**

| Flag | Default | Description |
|------|---------|-------------|
| `--planner ff-astar2\|ff-astar1\|ff-astar\|ff-wastar1\|ff-wastar2\|dijkstra` | `ff-astar2` | The FastDownward search PDDLStream runs for every action-plan search. `ff-astar2` is PDDLStream's own (eager weighted A* with the FF heuristic doubled, f = g + 2h); `ff-astar1` has f = g + h; `ff-astar` is plain A* with FF and no preferred operators; `dijkstra` is blind and cost-optimal. Plans execute as the planner returns them |
| `--max-plan-time F` | `1800` | Per-call PDDLStream budget in seconds |
| `--unit-costs` | off | Give every action cost 1 instead of the domain's costs (`place_hiding` 2, `stack` 3, all others 1) |
| `--search-sample-ratio F` | `0.25` | Sampling-to-search budget ratio of PDDLStream's adaptive loop (the library's own is 1.0) |
| `--search-effort-weight W\|off` | `1` | Weigh the effort of a stream result against action cost in the optimistic search, so the search prefers results already refined; `off` is PDDLStream's own, no weighting |
| `--search-initial-complexity N` | `3` | Stream complexity level the adaptive loop starts at; 0 is PDDLStream's own |
| `--sense-gate off\|strict` | `off` | What `(boxel_fits ?o ?shadow)` means for the sense action: `off`, every view-clear fragment is sensable; `strict`, only fragments in which a target-class box can rest fully occluded |
| `--corridor-test cell+object\|object` | `cell+object` | How placement-blocking corridor facts are tested: against the free cell's own bounding box and per-object virtual boxes, or against the per-object virtual boxes only |
| `--path-check-step F` | `0` | Resolution of every motion-plan collision check, in radians of the largest-moving joint between samples; 0 is a fixed 8 samples per edge, 0.0286 is what an RRT edge already gets |
| `--path-check-diag` | off | Report, for every trajectory the motion stream yields, how many interior segments pass only with the gripper relaxed |

**Discretization**

| Flag | Default | Description |
|------|---------|-------------|
| `--baseline semantic\|uniform` | `semantic` | Free-space discretization: octree with cell merging, or a static uniform 3D grid (`world/uniform_grid.py`) whose lattice stays fixed across replans while only the cell labels change |
| `--uniform-cell-size F` | `0.05` | Uniform-grid cell edge in metres; raised to the largest object extent plus 1 cm so `place` can fit |
| `--min-boxel-size F` | auto | Smallest free-space octree leaf for the semantic baseline, in metres. Auto is the largest object extent plus 1 cm; an explicit value is used as given, also below that, for the anytime resolution sweep. Object and shadow boxels are unaffected |

**Model tweaks**

| Flag | Default | Description |
|------|---------|-------------|
| `--m8 off\|on` | `on` | M8: pose-gated pick, view-clear sense configurations and the wrist-camera observe action (loads the generated domain `pddl/domain_pddlstream_m8.pddl`) |
| `--m9 off\|on` | `on` | M9: object-fitted grasps (yaw and extents of the top-face rectangle) instead of the bounding-box grasp candidates |
| `--m10 off\|on` | `on` | M10: a failed pick that touched the target makes its pose unknown, with no in-action retry |
| `--pick-aperture-from-pose off\|on` | `on` | M8's aperture rule: open the pads to the pinch half-width plus the pose radius plus 8 mm, capped at the finger limit |
| `--sense-over-region off\|on` | `on` | With M8: sense a region from the target's pick configuration over it when the arm there keeps out of the eye's view, then pick from there; `off` returns the arm to a static view spot before every sense |
| `--grip-squeeze-mm F` | `0.5` | How far inside the measured width the pick's close holds the pads, in mm |

**Output and logging**

| Flag | Default | Description |
|------|---------|-------------|
| `--no-gui` | off | Headless: no PyBullet window |
| `--no-boxel-viz` | off | Keep the GUI but skip drawing the boxel boxes and labels |
| `--show-free` | off | Include free-space boxels in the overlay |
| `--log-level smart\|normal\|quiet\|verbose` | `smart` | Console style (see above). `normal`, `quiet` and `verbose` leave stdout raw and set the console log level to INFO, WARNING and DEBUG. The run log always captures everything |
| `--save-screenshots off\|on` | `off` | Save the robot camera's `eye_<k>_camera.png` and, under the GUI, `eye_<k>_gui.png` at the initial observation, after each sense, place and stack, and at the end of the run; debugging only. `BOXEL_EYE_IMAGES=0` vetoes them |
| `--telemetry` / `--no-telemetry` | on headless, off under the GUI | The world telemetry recorder: every body pose, velocity, tilt and contact at frame resolution, plus physical events (fling, grip loss, topple, off-support, joint jump). Nothing it writes reaches the console |
| `--telemetry-period F` | `0.05` | Telemetry frame cadence in simulated seconds |
| `--telemetry-heartbeat F` | `0.5` | Cadence in simulated seconds of the where-is-everything dump in the run log |

### TAMPURA bridge

`tampura_bridge/` runs this pipeline inside TAMPURA's `find_dice` environment, seed for seed. TAMPURA's rollout, environment and reward run untouched: the bridge's policy returns one action, `boxel_episode`, whose execution runs a whole episode of this pipeline in TAMPURA's executing world, and the terminal observation comes from physical readback. The driver runs from TAMPURA's `tampura_environments` directory:

```bash
PYTHONPATH=<repo>:<pddlstream_lib>:<their tampura>:<their envs> \
  <python> <repo>/tampura_bridge/run_bridge_on_finddice.py --global-seed 0 --vis 0
```

`--global-seed` is required, `--vis 1` opens the GUI, `--save-dir` names the episode directory (`bridge_episode.json`, with the pipeline's run directory under `ours/`) and `--max-plan-time` defaults to 900. The flags `--m8`, `--m9`, `--m10`, `--pick-aperture-from-pose`, `--sense-over-region`, `--grip-squeeze-mm`, `--search-effort-weight`, `--search-initial-complexity` and `--save-screenshots` are passed through under the same names and defaults. A headless run stops when TAMPURA loads a scene other than the one pinned for the seed (G19) unless `--allow-g19-mismatch 1` is given; a GUI run goes on and is never scored. The exit code is 0 exactly when the outcome field is success; the field combines TAMPURA's last reward, any error and the ledger gates.

`tools/bridge_gates.py` checks the runs against the gates that keep the comparison honest (no welds, no teleports, no ground-truth reads feeding a decision), and `tampura_bridge/gate_hooks.py` holds the runtime gates. `tools/_bridge_campaign.py` and `tools/_bridge_report.py` run and report a campaign of both arms, TAMPURA and ours, on seeds 0 to 19; `tools/cluster/` holds the Slurm scripts. The plan, the records and the evidence are in `docs/PAPER_AUDIT.txt` and `archive/tampura_bridge_plan_2026-10-25/`.

## Documentation

**[Project wiki (home)](https://git.rwth-aachen.de/hani.alassiri.alhabboub/pybullet/-/wikis/home)**, or open the **Wiki** tab in the repository.

Detailed documentation lives there, including:

| Page | What it covers |
|------|---------------|
| Architecture Overview | Module dependencies, data flow diagrams, file structure |
| Scene Environment | PyBullet setup, camera model, scene presets, object detection |
| Spatial Reasoning | Shadow calculation, free-space octree, cell merging, uniform-grid baseline |
| Planning System | PDDLStream integration, problem construction, replanning |
| Robot Control and Streams | IK, RRT-Connect motion planning, grasp sampling |
| Execution Pipeline | End-to-end walkthrough, goal modes, action handlers, the full CLI reference, logging and reporting, a concrete scenario |
| Core Data Structures | All types, dataclasses, and enums |
| PDDL Domain Reference | Predicates, actions, streams, PDDL/Python alignment |
| Evaluation Framework | `evaluation/eval_runner.py` matrix sweeps, `evaluation/eval_plotter.py` figures and tables, the pre-vetted seed corpus, baselines, A/B evaluation between code states, the TAMPURA bridge campaigns, run data retention, a typical workflow |
| Design Decisions | Rationale for key choices and proposal deviations |
| Known Issues and Roadmap | Audit status, open issues, future work |

## License

MIT
