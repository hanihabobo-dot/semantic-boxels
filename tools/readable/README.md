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
