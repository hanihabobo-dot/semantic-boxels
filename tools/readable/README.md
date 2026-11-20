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
| R3 | `return False` / `return None` of the old function in the span become `return <SENTINEL>` (the code also takes the key `"True"`: a `return True` with a declared sentinel, the same rewrite) | `sentinel_returns` |
| R4 | `nonlocal` lines are dropped (their names must be in `name_map`) | `drop_nonlocal` |
| R5 | indentation, compared relative to the first statement | always |
| R6 | comments: may differ, but every removed, changed or added comment is printed as residual; the contiguous comment block directly above a cut span or a moved def (up to the first blank or code line) is diffed with the span, so dropping it is residual, and keeping it directly above the new def or inside the new function is clean | always |

Two tolerances of the compare, not on the list, both keep the value (R_PHASE0
1.1, C9): (i) the layout inside one logical line does not count (line
breaks inside brackets, backslash continuations, spaces between tokens),
because the compare is by tokens of a logical line; (ii) an f-string is
compared by its syntax tree, so its spelling does not count when the tree is
equal (prefix case and order, spaces inside `{}`, the spelling of an
escape).

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

R's conditions M1 to M8 (R_PHASE0 section 6; build record
`phase0/build/move_check_M1_M8.md` in the trunk's tracks folder):

| | check | fails as |
|---|---|---|
| M1 | one account per touched file (the entries' files, the state class file, `account_files`): old lines minus all old spans against new lines minus all new functions, by tokens, no rewrite; each difference is printed `OUTSIDE outside the entries` (status review, exit 3). A correct cut exits 3: its call is outside the entries | `outside-the-entries` |
| M2 | every comment is owned by one entry (inside the span, the block directly above it, the block that ends it, for a move the block at the def's indentation above it across blank lines; the same around the new function) or diffed by the account | comment residual |
| M3 | old spans pairwise disjoint; one new function, one entry | `spans-overlap`, `new-home-shared` |
| M4 | a mapped name is a local of the old container or a nonlocal of a closure in it; one field from one owning scope | `map-not-local`, `map-field-two-scopes` |
| M5 | a spec with a name map names `state_classes` (file, groups, optional root); the group's class declares the field | `state-classes-not-named`, `state-class-missing`, `map-field-not-declared` |
| M7 | a cut: no unmapped name the span binds is read after it, before it inside a loop around it, or in a nested scope; none is declared global or nonlocal outside it; sentinels pairwise different; the header is `def name(params):` only, or the old header's own parts for a cut of a whole body | `live-out-local`, `span-binds-global`, `sentinels-not-distinct`, `cut-header` |
| M8 | `__x`, bare `super()` and `__class__` in code whose class changes; the globals the old span read are its Name loads | `class-bound-name`, `free-name` |

M6 (rebound names) is global_identity's, below.

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
new function's body (the new header is compared by M7, below);
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

Exit codes: 0 clean; 3 only comment residual, warnings or lines outside the
entries (R reads them); 1 a code residual or a failed rule; 2 the spec or a
file could not be read.
`--map` writes or updates `MIGRATION_MAP.tsv` (old file, old qualname, new
file, new qualname, phase, kind, old lines, new lines, entry, status; a
re-run replaces its own entries' rows). `--line-map` writes old line to new
line for every matched logical line.

Limits: the identity check of cross-file moves (`new_mod.x is old_mod.x`,
draft 4.1) needs imports and is done by `global_identity.py` (below), not
here. A comment near a span that the entry does not own (M2) is listed as
INFO and diffed by the file account; a cut whose header comment stays above
the call site in the old function reads as removed in the entry and added
in the account (R reads both). Bound-before-use is a straight-line approximation: a read bound only
on some paths is a warning for R. An f-string is compared by prefix, quote
and `ast.dump`, so spaces inside `{...}` do not count.

Tests: `python -m pytest -q tests/readable/test_move_check.py` (Windows
Python 3.12 or `/root/armO-venvA/bin/python` 3.11 in WSL).

## global_identity.py: the identity half of pin 44 (and M6)

Pin 44 (`p44_loggers_globals`) describes every global a function reads by
type and name; a description cannot tell two instances apart. For each
cross-file `move` or `cut` row of `MIGRATION_MAP.tsv` (the new file is not
the old file), `global_identity.py` takes the globals the new function and
its nested scopes read (symtable of the new file) and, in one child
interpreter (cwd the checkout, `PYTHONHASHSEED=0`) that imports the old and
the new module, checks `new.__dict__[g] is old.__dict__[g]` (builtins
resolved as at run time). A lock, registry or cache re-created in the new
module instead of imported fails, and so do a global only one module binds,
a name the function declares `global`, and a row whose module or function
is not found.

```
PYTHONHASHSEED=0 flock /root/sb_pipeline.lock /root/armO-venvA/bin/python \
    tools/readable/global_identity.py --map tools/readable/MIGRATION_MAP.tsv --root . [--json OUT]
```

Exit 0 every global the same object (or no cross-file row), 1 a failure, 2
the map could not be read. Run it after every cut with a cross-file row,
from P2 on. Limits: `is` on a small int or interned string holds even when
the constant was written twice (pin 48 holds the twin constants);
decorators, defaults and annotations are read at module level and are not
listed. Tests: `tests/readable/test_global_identity.py` (synthetic old and
new module pairs; Windows and WSL).

M6 (R_PHASE0 section 6): a global the moved function reads bare fails as
"rebound at run time" when the tree under `--root` rebinds it in the old
module: a `global g` with a binding in a function of the old module;
`<alias>.g = ...`, `+=` or `del` in any file; `setattr`, `delattr` or
`patch.object` on an alias of the old module (a computed name counts as
every name); a string `"old.g"` given to `setattr`, `patch` or `delattr`;
a call with the strings `"old"` and `"g"` first (the gates' `_rebind`); and
pin 42's `_REBOUND` list (read from pin_outputs.py as text). So `from old
import g` fails for exactly those names. The read through the module
(`import old` and `old.g`, or an alias) is accepted: a global whose value is
the old module itself is "same", and each attribute read on it must exist
in the old module. The scan reads source only and skips `archive`,
`_scratch`, `__pycache__`, `node_modules`, `site-packages` and hidden
folders; a rebinding through a computed module (a loop over
`sys.modules`) is seen only through pin 42's list. On the worktree it finds
`args` (test_full_pipeline), `_console` and `finish` (console_ui), the run
logger's three, `ENABLED` (slip_fixes). move_check still prints the
module-attribute form as residual (its tokens and its free name differ from
the old body; the closed list has no rewrite for it), so R reads it there.

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

### Pin 47's scripted tapes (`scripted_tapes.py`, `tests/readable/executor_stubs.py`)

The live replays reach the success path only. `p47_scripted_<scenario>`
replays a scripted tape that `scripted_tapes.py` makes from the live tapes
of READABLE_TAPES by rules over the live ledger: live calls copied as they
are (facts, goal and RNG still checked), then calls cut from a live plan
(the actions before a sense, the sense alone, a pick alone, all but a final
move to q_home), an argument replaced by a text, or no plan (the end).
`replay_stub.scripted_solution` serves them; no action is invented. Some
scenarios add a test-level executor stub (pin 47 allows them;
`tests/readable/executor_stubs.py`, set in the episode child by
`record_episode.py --stubs`) that forces a physical failure; every stub
call is a row of the pin's `stubs.json`.

| scenario | source and rule | branch reached |
|---|---|---|
| `sense_still_blocked` | rp0's first plan, its sense alone at the start | sense_still_blocked |
| `sense_missing_shadow` | the same sense, shadow `shadow_of_no_such_body` | sense_missing_shadow |
| `sense_found_target` | the first live found_target sense, split off as a sense-only plan | sense_found_target |
| `sense_clear_but_empty` | the first live clear_but_empty sense (br0 or br5), split off | sense_clear_but_empty |
| `sense_contains_nontarget` | the found_target split; stub: outcome contains_nontarget, the moved occluder as the body | sense_contains_nontarget |
| `sense_contains_unlocalizable` | the same with a body the render does not show | sense_contains_unlocalizable |
| `empty_hand_place`, `_carry`, `_stack` | the first plan with a place, a move after a pick, a stack; stub: EmptyHandError at the place or stack entry, a carry loss | step_end empty_hand (three sites) |
| `integrity_replan` | rp0's first plan; stub: a disturbed bystander after the first move | integrity_replan |
| `knocked_off_table` | the same with the goal object knocked off | exit knocked_off_table |
| `integrity_after_place` | the first plan with a place that ended ok; stub: a disturbed bystander after that place (label `plan#N place(`) | integrity_replan at the place site |
| `integrity_after_stack` | stack0; stub: a disturbed bystander after its stack | integrity_replan at the stack site (then success: the stack was the goal) |
| `knocked_after_pick` | the first plan with a sense and a pick that ended ok; stub: the goal object knocked off after that pick, while holding | integrity_replan at the pick site, exit knocked_off_table |
| `pick_giveup` | the found_target plan up to the target's pick, the pick alone twice; stub: the target's picks fail | pick_failure x3, exit pick_giveup |
| `home_split` | the last bridge plan split before its final move to q_home | success one plan later (the at_home_ok path) |
| `home_not_reached` | the last bridge plan, its final move twice more; stub: readback 0.01 rad off | home_not_reached |

A tape set without a source for a rule makes the pin error with the rule's
name. `READABLE_TFP_COPY=<file>` (planted-change checks of PLAN 24.3 (e)
only) runs a copy of test_full_pipeline.py instead of the checkout's: the
copy is named in `INFO_run.json` only.

`planted_changes.py --out <dir>` writes those copies, one folder per plant
(`at_home_drop`: `at_home_ok = False` dropped; `empty_hand_swap`: two
statements of the place empty-hand path swapped; `empty_hand_swap_quiet`:
the same swap without the crash), each as one exact text replacement that
must match once in the checkout's file; `--list` names the pin each must
turn red. Never written into the checkout.

`tests/readable/test_pin_replay.py`: unit tests of the recorder, the stub
and the normalisation (no pipeline import; Windows too); with
`READABLE_TAPES`, each replay's step and step_end rows against the live
episode's and the per-call facts, goal and RNG checks; with
`READABLE_GOLDEN`, every pin against its golden copy.
`READABLE_EPISODE_ONLY=<ids>` limits the generation.

## paired_sets.py and DECLARATION_TEMPLATE.md: the paired sets N, S, A, B

`paired_sets.py` runs a declared paired set and recomputes its numbers from
`results.jsonl` (PLAN 8 and 24.4; PLAN_REVIEW S-o to S-r and note 3). It
imports no pipeline and no pybullet. A set's folder holds `DECLARATION.md`
(copied from `DECLARATION_TEMPLATE.md`; its one block marked `json
paired-set` is the machine-read part), then `results.jsonl`, `episodes/`
(one folder per run: `episode.sh`, `gate.txt`, `launch.txt`, stdout,
stderr, the copied `timing_summary.json` or the bridge's `save/`).

```
python tools/readable/paired_sets.py plan    --set-dir evals/<id>
python tools/readable/paired_sets.py scripts --set-dir evals/<id> --out <folder>
python tools/readable/paired_sets.py run     --set-dir evals/<id>
python tools/readable/paired_sets.py analyse --set-dir evals/<id> [--crash-reviews F] [--json OUT]
```

- `plan` checks the declaration and prints the ABBA list (pair k: A B when
  k is even, B A when odd, carried across worlds) to paste into `runs`.
- `scripts` writes every episode script for reading; nothing is launched.
- `run` (Windows: pwsh and wsl.exe) refuses a folder that already has
  `results.jsonl` (a repeat is a new declaration), a zero sha, a checkout
  whose HEAD is not its sha or that is not clean, and a stored statistics
  copy whose sha256 is not the declared one. Then per declared run: a
  `start` row (written before the launch, so a run that vanishes leaves a
  row), the episode through `gate_run.ps1`, an `end` row classified from
  the run's files. The episode script takes `flock` on the pipeline lock,
  checks MemAvailable (rule 16), restores the statistics copy for boxels
  under the same hold, runs the child under `timeout -k 30 <cap>`, and
  exits 0; what happened is in its files. A run that does not start stops
  the set. `set_start` and `set_end` rows carry each arm's HEAD and status,
  the library commit and the venv's pip freeze sha256 (S-p).
- `analyse` prints the per-seed table, the "full" line with every reason
  the set is not full, the items of 24.4 (b) per world (set A and B), PLAN
  8's rule (set S) or the noise count (set N), the validity notes, and a
  verdict: PASS (exit 0), RECORDED (set N, exit 0), FAIL (1), PENDING
  REVIEW (3: a crash of the new arm without its review pair's verdict in
  `--crash-reviews`, a JSON map of run position to `migration` or
  `not_migration`), NOT FULL (4).

Statuses: boxels success, failure, timeout, preflight_rejected, crashed,
wrong_scene. A pre-flight rejection is the `[pre-flight] seed N rejected: M`
line with no summary; test_full_pipeline re-raises the RuntimeError, so
under `--log-level quiet` its traceback follows the line in stderr. That one
traceback (after the line, ending in `<type>: M`) is part of the rejection;
any other traceback (a second one, one before the line, one in stdout or a
log, one with another message) makes the run `crashed`. Bridge: success
(reward 1.0, no failed gate but G19), failure,
gate_failed, killed, crashed, wrong_scene; both not_started and vanished.
Item 2 compares outcome kinds without crashed (item 1's) and without the
not-full statuses, exit reasons, and failed gates without G19.

`tests/readable/test_paired_sets.py`: a fake launcher plants each case of
S-o; on WSL the generated bash scripts also run for real with a fake python
and a private lock file (never the pipeline lock).

## console_replay.py and group `console`: pin 27

`console_replay.py` plays a recorded run through the real Console of
`console_ui.py`, its terminal a pipe (the static layout), in a child
interpreter per environment set (`plain`, `ascii`: NO_COLOR; `color`,
`color_ascii`: FORCE_COLOR; the `ascii` sets with SB_CONSOLE_ASCII). The
child freezes `time.perf_counter` and `time.strftime`, installs the Console
as `install_early` does, plays the calls and ends with `console_ui.finish`
or an uncaught exception, as an entry point does. No pipeline file is
patched.

- A run directory (`ledger.jsonl`, `run_<stamp>.log`, for a bridge run also
  `bridge_episode.json` two levels up) becomes a tape: the run log's stdout
  lines go to `narration`, its ERROR and CRITICAL logging lines to the
  Console's log handler, and the ledger rows to `on_ledger_event`, placed
  among the lines by anchors read from test_full_pipeline.py (plan rows
  before their eye or timing line, step rows before `Executing:`, step_end
  rows before the next step boundary, at_home_test rows before their D7
  line; every other row before the next anchored row). The header,
  summary and the bridge driver's own calls (start-up note, G19 note,
  set_context, gate table and outcome line through `terminal()`) are rebuilt
  from the run's files; `inputs.json` says from which.
- The made tapes (`console_replay.MADE`, R's plan review S-d) reach every
  regex rule of console_ui (44 at the checkpoint), every ledger kind, end
  status and sense reason, the stderr, log, say, warn and `terminal()`
  paths, a G19 stop before the run, a crash and an interrupt.
- `--live-check RUN_DIR` replays a smart run (one with `console_debug.log`)
  and compares the replay's `[console]` lines with the live ones, times,
  stamp and run folder masked: the check of the anchors.
- Outputs per set: `console.txt` (the `[console]` lines, R's compared
  output), `terminal.txt`, `debug.txt`, `run.json`; per pin `inputs.json`;
  `INFO_tape.json` and `INFO_coverage.json` are not compared.

Group `console` in `pin_outputs.py`: `p27_made_*` (the made tapes),
`p27_run_*` (two archived bridge runs tracked in the repo), `p27_tape_*`
(the live runs behind pin 47's tapes, with READABLE_TAPES). In WSL:

    READABLE_TAPES=<tapes> PYTHONHASHSEED=0 flock /root/sb_pipeline.lock \
        /root/armO-venvA/bin/python tools/readable/pin_outputs.py --group console --out <folder>
    PYTHONHASHSEED=0 flock /root/sb_pipeline.lock /root/armO-venvA/bin/python \
        -m pytest -q tests/readable/test_pin_console.py

`tests/readable/test_pin_console.py`: unit tests of the log reader, the
anchors, the header derivation, the tapes' form and the masks (Windows
too); in WSL every pin played in all four sets, the colour-independence of
the `[console]` lines, the anchors of every recorded run, the made tapes'
reach, two plays equal, and with READABLE_GOLDEN each pin against its
golden copy. Pin 26 is `p26_console_pure` in group `low`.
