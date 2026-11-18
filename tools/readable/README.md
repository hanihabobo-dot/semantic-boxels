# tools/readable: the Phase 0 tools of the readable migration

These tools prove that the readable migration keeps behaviour identical
(PLAN.md sections 5, 8 and 24 in the trunk's
`archive/tampura_bridge_plan_2026-10-25/tracks/readable/`). Each build of
Phase 0 adds its own section below. Tests live in `tests/readable/`;
scratch output goes to `tests/readable/_scratch/` (ignored by git).

## move_check.py: the token checker

A checker, not a tool that applies a cut. It reads a cut spec (JSON) and,
for each entry, shows that the new body's tokens equal the old span's tokens
after a closed list of allowed rewrites. Everything else is printed as
residual for R.

Allowed rewrites (nothing else):

| # | Rewrite | Spec field |
|---|---|---|
| R1 | a name `x` becomes `st.<group>.x` (per name, one field per name, the field keeps the name; also inside f-strings) | `name_map` |
| R2 | a `break` whose loop is outside the cut span becomes `return <sentinel>` | `break_sentinel` |
| R3 | `return False` / `return None` of the old function in the span become `return <SENTINEL>` | `sentinel_returns` |
| R4 | `nonlocal` lines are dropped (their names must be in `name_map`) | `drop_nonlocal` |
| R5 | indentation, compared relative to the first statement | always |
| R6 | comments: may differ, but every removed, changed or added comment is printed as residual | always |

Other checks: a cut is a run of sibling statements of one block (no cut
through a `try`, `with`, `if` or loop); a def span carries its decorators;
the name map is one to one, keeps the name and puts a name in the group the
draft's table gives (`counts`, `hand`, `arm`, `strikes`, `ending`, open
`setup`); a return, `continue` or `yield` that would leave a cut is flagged;
free names (PLAN 24.3 (f)): every name the new function reads is a
parameter, a local bound before use, a mapped field, a builtin, or a global
the old code read too and the new module binds; `self.<attr>` reads a mixin
does not define are listed; a deletion leaves the rest of the file token
equal and no NAME token of the deleted function.

Spec (`spec_version` 1):

```json
{"spec_version": 1,
 "entries": [
  {"id": "P2-assert-xys", "kind": "move", "phase": "P2",
   "old": {"file": "boxel_env.py", "qualname": "BoxelTestEnv._assert_xys_in_reach"},
   "new": {"file": "world_placement.py", "qualname": "WorldPlacement._assert_xys_in_reach"}},
  {"id": "P1-tray-goal", "kind": "delete", "phase": "P1",
   "old": {"file": "test_full_pipeline.py", "qualname": "build_tray_stack_goal"},
   "reference_scan": ["tools/bridge_gates.py"]},
  {"id": "P6-loop", "kind": "cut", "phase": "P6",
   "old": {"file": "test_full_pipeline.py", "qualname": "main",
           "start_anchor": "text on the first line of the first statement",
           "end_anchor": "text on the first line of the last statement"},
   "new": {"file": "test_full_pipeline.py", "qualname": "run_one_plan"},
   "name_map": {"plan_count": "st.counts.plan_count"},
   "break_sentinel": "BREAK",
   "sentinel_returns": {"False": "EARLY_FALSE"},
   "drop_nonlocal": true}]}
```

`kind`: `move` compares the whole old def (with decorators) with the whole
new def; `cut` compares a statement run inside the old function with the
new function's body (the new header is listed, not compared);
`delete` compares the old file minus the def with the new file. Anchors are
text (they survive line shifts); `*_occurrence` picks one of several
matches; `start_line`/`end_line` (first lines of the first and last
statement) may replace anchors.

Run (any Python 3.11+; no pybullet, no pipeline import, no lock needed):

```
python tools/readable/move_check.py SPEC.json --old-root OLD --new-root NEW \
    [--map tools/readable/MIGRATION_MAP.tsv] [--line-map LINEMAP.tsv] [--json OUT.json]
python tools/readable/move_check.py SPEC.json --old-ref refactor-checkpoint-1 --repo . --new-root .
```

Exit codes: 0 clean; 3 only comment residual or warnings (R reads them);
1 a code residual or a failed rule; 2 the spec or a file could not be read.
`--map` writes or updates `MIGRATION_MAP.tsv` (old file, old qualname, new
file, new qualname, phase, kind, old lines, new lines, entry, status; a
re-run replaces its own entries' rows). `--line-map` writes old line to new
line for every matched logical line.

Limits: the identity check of cross-file moves (`new_mod.x is old_mod.x`,
draft 4.1) needs imports and belongs to a pin under the pipeline lock, not
here. Bound-before-use is a straight-line approximation: a read bound only
on some paths is a warning for R. An f-string is compared by prefix, quote
and `ast.dump`, so spaces inside `{...}` do not count.

Tests: `python -m pytest -q tests/readable/test_move_check.py` (Windows
Python 3.12 or `/root/armO-venvA/bin/python` 3.11 in WSL).

## pin_outputs.py: the pin generator (group `low`)

One generator for every pin group. A pin is a function, registered with
`@pin(group, pin_id, about)`, that calls today's code on fixed inputs and
writes what comes back as files. Later builds add their groups (`world`,
`episode`) with the same decorator.

```
python tools/readable/pin_outputs.py --group low --out DIR [--only p05_registry,p08_domain]
python tools/readable/pin_outputs.py --list [--group low]
python tools/readable/pin_outputs.py --compare DIR_A DIR_B     # exit 0 when every pin is equal
```

`--out DIR` gets `DIR/<pin id>/` per pin (JSON and text, plus `NOTES.txt`
with the Python version and every sorting or masking the pin does),
`DIR/MANIFEST.json` (status and file sha256 per pin) and `DIR/_logs/`.
Each pin runs in a child process of its own: a fresh interpreter, cwd and
HOME a fresh temporary folder, `PYTHONHASHSEED=0`, `COLUMNS=80`,
`LC_ALL=LANG=C.UTF-8`, no console switches inherited. Paths are masked as
`<REPO>`, `<WORK>`, `<OUT>`. Files named `INFO_*` (line numbers, file
lists) are information only: `--compare` and the test skip them.

R's rules as applied: no stored golden output before tag
refactor-checkpoint-2; two passes must be equal; exact comparison (floats
as `json.dumps` writes them, big float arrays as the sha256 of their
float64 bytes and the shape); a list that comes from a set is sorted and
the pin's NOTES say so (`plain()` refuses a set); run in WSL with
`/root/armO-venvA/bin/python` under `flock /root/sb_pipeline.lock`. No pin
starts a physics client or an episode, and none edits pipeline code; a few
replace a module attribute inside their own child process (the ledger
hooks of `boxel_data` and `belief`, `eval_runner.subprocess` and `.time`,
`console_ui.REPO`), as test code does.

Group `low` (31 pins, the index `phase0/index/pins_low.md`): R's 4, 5, 8,
11, 12, 17, 18, 19, 20, 22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 36,
37, 38 and the plan's AST pins 39, 40, 41, 42, 43, 44, 45, 48. Pin 32 needs
`pwsh.exe` through WSL interop; pins 20, 26, 33, 36, 38 read the tracked
BF45_46, BF38_q14, BF2_b0, BF59 and tb25_ab records under `archive/`. The
AST pins scan root `*.py`, `tampura_bridge/*.py` and `tools/*.py`. A whole
generation takes about three minutes.

Test: `tests/readable/test_pins_low.py` generates the group afresh and
compares it pin by pin with the folder named by `READABLE_GOLDEN`; without
it the pin tests skip with that message:

```
READABLE_GOLDEN=<folder> PYTHONHASHSEED=0 flock /root/sb_pipeline.lock \
    /root/armO-venvA/bin/python -m pytest -q tests/readable/test_pins_low.py
```

## pin_outputs.py: group `world` (the world and its sensing)

Group `world` (18 pins, the index `phase0/index/pins_world.md`): R's 1
(`p01_scene_presets`, `p01_scene_random_pairs`, `p01_scene_failures`), 1b
(`p01b_find_dice_scenes`), 2, 3, 6, 7, 9 (`p09_streams`, `p09_ik_tables`),
10, 13, 14, 15, 16, 21 and 35 (`p35_bridge_pure`, `p35b_bridge_table`).
These pins start physics clients, headless only (`BoxelTestEnv(gui=False)`
or `pybullet.DIRECT`): a scene must get client 0 (executing) and client 1
(plan twin), or the pin stops. Pins 1b and 35b need the bridge venv
(TAMPURA's tree at `/root/tampura-work`); without it they stop with "needs
the bridge venv". Pin 21 runs one scripted pick (contact physics); pin 10
and pin 21 wrap pybullet functions inside their own child (call through),
pin 7 wraps `random.shuffle` the same way.

Pins 13 to 16 read a stored eye render made by
`tests/readable/make_render_fixture.py` (four renders A, A2, B2, C of two
scenes, `FIXTURE.json` with the sha256 of every file). The folder comes
from `READABLE_RENDER_FIXTURE` (default `tests/readable/_scratch/render_fixture`).
On tag refactor-checkpoint-2, first the fixture, then the golden folder:

```
python tests/readable/make_render_fixture.py --out <fixture>
READABLE_RENDER_FIXTURE=<fixture> python tools/readable/pin_outputs.py --group world --out <folder>
READABLE_GOLDEN=<folder> READABLE_RENDER_FIXTURE=<fixture> PYTHONHASHSEED=0 \
    flock /root/sb_pipeline.lock /root/armO-venvA/bin/python -m pytest -q tests/readable/test_pins_world.py
```

`READABLE_WORLD_ONLY=<ids>` limits the test's generation to those pins. A
whole generation takes about 100 s in WSL (pin 1b about 35 s).

## record_episode.py, tests/readable/replay_stub.py and group `episode`

`record_episode.py` runs one whole episode (or an episode start) headless
in a child interpreter, with the cwd, environment and argv that
`run boxels -Headless` and `run tampura -Headless` build (run.ps1:149-171),
`--log-level normal` (no console takes over) and, for boxels,
`--no-telemetry` (as the eval runner passes it). It never takes the
pipeline lock: its caller runs it under `flock /root/sb_pipeline.lock`, and
whole episodes go through the health gate (`gate_run.ps1`).

```
python tools/readable/record_episode.py --episode rp0 --mode record --run-dir DIR
python tools/readable/record_episode.py --episode rp0 --mode replay --tape DIR/tape --run-dir DIR2 [--trace-main]
python tools/readable/record_episode.py --episode br0 --mode first-plan --run-dir DIR
python tools/readable/record_episode.py --record-set TAPES [--episodes rp0,rp1,rp1o3,stack0,br0,br5]
python tools/readable/record_episode.py --renorm DIR
python tools/readable/record_episode.py --coverage DIR/rec/main_lines.json [...]
```

Episodes: `rp0` to `rp4` (random-pairs, holding, 2 occluders: `run boxels`),
`rp1o3` (seed 1 with 3 occluders; seed 1 with 2 is a pre-flight rejection),
`stack0`, `br0`, `br1`, `br5` (shipped scenes, `--allow-g19-mismatch 1` as
`-Headless` passes it), `br100` (generated scene, its own directory as
`run tampura -Gen` builds it).

Modes, all patching inside the child only (an import hook sets them right
after the module has been executed, so the entry's import order is kept):

- `record`: `pddlstream_planner.solve` wrapped; each call writes, at call
  time, `tape/solution_k.pkl`, `text_k.json` (the chunks the solver printed
  into plan()'s `_StdoutTee` during this call), `rng_k.pkl` and a
  `calls.jsonl` row (init facts and goal as text, RNG digests before and
  after, kwargs).
- `replay`: `replay_stub.install` sets the stub before the gate hooks wrap
  `solve` (G11 still sees plan() as the caller). Call k returns a fresh
  unpickled solution k, prints its text into the tee (so a recorded no-plan
  with skeletons takes the binding-death branch) and, with `--rng restore`
  (default), sets the RNG states the live search left. A call beyond the
  tape raises `ReplayTapeError` (a BaseException). Each call writes
  `rec/calls.jsonl` with facts, goal and RNG equality against the tape.
- `first-plan`: `PDDLStreamPlanner.plan` replaced by a recorder (bound
  arguments, stage B module switches, RNG digest, gate counts) that raises
  `StopAtPlan`; main's parameters at entry from a `sys.setprofile` hook.

For boxels runs RunLogger's relative `log_dir` is made absolute against the
cwd inside the child: the export joins a relative run directory to the code
directory (pddlstream_planner.py:434-439), so a run outside the checkout
would stop there.

Each run folder gets `RESULT.json`, `stdout.txt`, `stderr.txt`, `rec/` and
`norm/`: the ledger without `t`, `wall`, `pid`, `plan_time_s`, the
bridge_timing and driver_clock times, with `plan_obj` and `Type@id` mapped
to their order of first use keyed by plan id (PLAN 24.3 (d)); `eye.jsonl`
without `t_wall` and `extra.plan_time_s`; `timing_summary.json` and
`world_counts.json` without time keys; the console with times masked; the
facts of every solver call; `bridge_episode.json` without `time_deltas`.
`compare_live` gives the differences of a replay from the live episode
(PLAN 24.3 (a)); `--coverage` the breaks, `dispatch_end` statuses, exit
reasons and dispatcher branches of `main` that a traced replay reached
(PLAN 24.3 (b)).

Group `episode` of `pin_outputs.py`: `p30_planner_failed` and
`p30_binding_death` (rp0 with a synthetic one-call tape), `p34_start_rp0`
to `rp4`, `p46_bridge_start_s0`, `s1`, `s5`, `s100` (need the bridge venv),
`p47_replay_<episode>` for rp0, rp1, rp1o3, stack0, br0, br5 (need
`READABLE_TAPES`, the folder of `--record-set`). On the checkpoint:

```
python tools/readable/record_episode.py --record-set <tapes>
READABLE_TAPES=<tapes> python tools/readable/pin_outputs.py --group episode --out <folder>
READABLE_TAPES=<tapes> READABLE_GOLDEN=<folder> PYTHONHASHSEED=0 flock /root/sb_pipeline.lock \
    /root/armO-venvA/bin/python -m pytest -q tests/readable/test_pin_replay.py
```

`tests/readable/test_pin_replay.py`: unit tests of the recorder, the stub
and the normalisation (no pipeline import; Windows too); with
`READABLE_TAPES`, each replay's step and step_end rows against the live
episode's and the per-call facts, goal and RNG checks; with
`READABLE_GOLDEN`, every pin against its golden copy.
`READABLE_EPISODE_ONLY=<ids>` limits the generation.