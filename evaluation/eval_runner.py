#!/usr/bin/env python3
"""
Batch evaluation runner for the Semantic Boxels pipeline (audit #9).

Walks a configuration matrix (n_occluders × n_targets × seed × goal × ...),
launches test_full_pipeline.py once per cell as a subprocess, collects each
cell's timing_summary.json, and writes an aggregated CSV/JSONL for the
plotter (eval_plotter.py).

Subprocess-per-cell: RunLogger replaces sys.stdout, SmartConsoleFilter is
process-global, and PyBullet GUI/DIRECT clients don't always tear down
cleanly.  A fresh process per cell keeps state isolation cheap and lets
one bad cell not poison the rest of the sweep.

Usage:
    python eval_runner.py --matrix scalability \\
        --output eval_results/sweep_2026-05-08
    python eval_runner.py --matrix smoke --output eval_results/smoke
    python eval_runner.py --matrix scalability --skip-existing --timeout 300
    python eval_runner.py --matrix scalability --dry-run

Exit code 0 if every cell produced a timing_summary.json (success or fail);
non-zero if any cell crashed/timed out (or above --max-failures).
"""
# SmartConsoleFilter (smart_filter.py, named in the docstring above) was deleted in the readable migration, phase P1, 22 Nov 2026.

import argparse
import csv
import itertools
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional
if not __package__: sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # run as a file
from world import world_counts       # TB-22: drops, collisions, clean_success per row


# ---------------------------------------------------------------------------
# Matrix presets
# ---------------------------------------------------------------------------

# Scalability evaluation matrix (audit #9, absorbing #12).
# n_occluders ∈ 1..6 × n_targets ∈ 1..3 × 5 seeds × baseline {sem,uni}
# = 180 cells.  --goal holding only — find-and-tray-stack adds a third
# data series later.  n_hidden = min(n_targets, n_occluders) so every
# cell has the deepest search this scene size can support without
# overconstraining placement.  baseline axis (audit #10) drives the
# uniform-vs-semantic free-space comparison plotted by eval_plotter via
# the --baseline-csv overlay hook.
SCALABILITY_MATRIX = {
    "n_occluders": [1, 2, 3, 4, 5, 6],
    "n_targets":   [1, 2, 3],
    "seed":        list(range(5)),
    "goal":        ["holding"],
    "unit_costs":  [False],
    "scene":       ["scalability"],
    "baseline":    ["semantic", "uniform"],
    "_n_hidden_strategy": "all_or_max",
}

# 1-cell smoke test for runner sanity checks.
SMOKE_MATRIX = {
    "n_occluders": [1],
    "n_targets":   [1],
    "seed":        [0],
    "goal":        ["holding"],
    "unit_costs":  [False],
    "scene":       ["scalability"],
    "baseline":    ["semantic"],
    "_n_hidden_strategy": "all_or_max",
}

# "default" matrix — semantic-vs-uniform comparison across goal types
# on canonical default scenes (vs. SCALABILITY_MATRIX, which sweeps
# n_occluders / n_targets on the random scalability scene).  3 (scene,
# goal) pairs × 10 seeds × 2 baselines = 60 cells.
#
# Per-seed variation:
#   - 'default' scene has fixed object positions, so --seed only varies
#     planner-level RNG (Phase 4 random.choice() target pick + PDDLStream
#     stream sampling).  Same scene geometry across all 10 seeds for
#     holding and find-and-tray-stack.
#   - 'stack' scene has random per-seed cube placement
#     (constrain_to_reach=True), so layout varies across seeds.
#
# (default, stack) is intentionally skipped because run_logger
# auto-promotes it to (stack, stack).  (stack, holding) and
# (stack, find-and-tray-stack) are skipped because no occluders means
# 0 hidden — degenerate for both goals.
DEFAULT_MATRIX = [
    {
        "scene":              [scene],
        "goal":               [goal],
        "seed":               list(range(10)),
        "baseline":           ["semantic", "uniform"],
        "unit_costs":         [False],
        "n_occluders":        [3],
        "n_targets":          [4],
        "_n_hidden_strategy": "none",
    }
    for scene, goal in [
        ("default", "holding"),
        ("stack",   "stack"),
        ("default", "find-and-tray-stack"),
    ]
]

# Random-pairs sweep (audit #68 + #73 step 1(d) re-run).  Mixed-scene
# list so all 3 goals are covered: random-pairs sub-tier carries the
# 2 occluder-driven goals (holding, find-and-tray-stack) at
# n_occluders ∈ {2, 3, 4}; stack sub-tier carries the 3rd goal (stack),
# which random-pairs hard-rejects at parse time (run_logger.py:531).
# stack_scene ignores --n-occluders / --n-targets (no occluders;
# n_objects defaults to 3 — boxel_env.stack_scene); those values are
# tag-only for the stack sub-tier.  Cells: random-pairs
# (3 occluders × 2 goals × 5 seeds × 2 baselines = 60) +
# stack       (5 seeds × 2 baselines = 10) = 70.
RANDOM_PAIRS_MATRIX = [
    {
        "n_occluders": [2, 3, 4],
        "seed":        [0, 1, 2, 3, 4],
        "goal":        ["holding", "find-and-tray-stack"],
        "baseline":    ["semantic", "uniform"],
        "unit_costs":  [False],
        "scene":       ["random-pairs"],
        "_n_hidden_strategy": "none",
    },
    {
        "n_occluders": [3],
        "n_targets":   [3],
        "seed":        [0, 1, 2, 3, 4],
        "goal":        ["stack"],
        "baseline":    ["semantic", "uniform"],
        "unit_costs":  [False],
        "scene":       ["stack"],
        "_n_hidden_strategy": "none",
    },
]


def _load_corpus_seeds(n: int = 100) -> List[int]:
    """First ``n`` pre-vetted seeds from eval_corpus.json (audit #77 step 0)."""
    corpus_path = Path(__file__).resolve().parent / "eval_corpus.json"
    return json.loads(corpus_path.read_text())["seeds"][:n]


# Anytime compactness sweep (audit #77 step 3b) — IPC-style cumulative-
# solved-vs-wall-clock curve.  SEMANTIC runs at 2 resolution points:
# "current" (min_boxel_size=None -> the audit-#67 auto_cell, ~0.16 m
# occluder / ~0.06 m stack) and an explicit 5 cm.  UNIFORM runs once
# per scene as the baseline point — it is hard-clamped to auto_cell
# (a uniform cell finer than the largest object breaks placement, #66),
# so it has exactly one feasible resolution.  Seeds are the pre-vetted
# eval corpus (step 0).  Time budget is NOT a matrix axis — run once at
# --timeout 1800 and post-process aggregated.csv at any shorter
# wall_clock_s threshold.
# Cells at 30 corpus seeds: semantic 540 + uniform 270 = 810.
# audit #113: reduced 100 -> 30 for the canonical re-run (bump back to
# 100 to restore the original full-power statistics).
_CORPUS_SEEDS = _load_corpus_seeds(30)

SCALABILITY_VS_TIME = [
    {  # semantic, occluder-driven goals — resolution swept
        "n_occluders":        [2, 3, 4],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["holding", "find-and-tray-stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [None, 0.05],
        "unit_costs":         [False],
        "scene":              ["random-pairs"],
        "_n_hidden_strategy": "none",
    },
    {  # uniform, occluder-driven goals — single baseline point (auto_cell)
        "n_occluders":        [2, 3, 4],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["holding", "find-and-tray-stack"],
        "baseline":           ["uniform"],
        "unit_costs":         [False],
        "scene":              ["random-pairs"],
        "_n_hidden_strategy": "none",
    },
    {  # semantic, stack goal — resolution swept
        "n_occluders":        [2, 3, 4],
        "n_targets":          [3],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [None, 0.05],
        "unit_costs":         [False],
        "scene":              ["stack"],
        "_n_hidden_strategy": "none",
    },
    {  # uniform, stack goal — single baseline point (auto_cell)
        "n_occluders":        [2, 3, 4],
        "n_targets":          [3],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["stack"],
        "baseline":           ["uniform"],
        "unit_costs":         [False],
        "scene":              ["stack"],
        "_n_hidden_strategy": "none",
    },
]

# audit #98 — coarse-end resolution sweep, sibling of SCALABILITY_VS_TIME.
# Probes min_boxel_size at 1.5x and 2x the per-scene auto_cell to
# characterise the resolution-vs-success curve ABOVE the audit-#67
# auto_cell floor (SCALABILITY_VS_TIME only sweeps at-or-below it).
# Per audit #98 Fix Step 1 option (b): per-scene numeric mbs values —
# random-pairs auto_cell ~9 cm so 1.5x / 2x = 0.135 / 0.18 m; stack
# auto_cell ~6 cm so 1.5x / 2x = 0.09 / 0.12 m.  Uniform arm omitted —
# its cell size is hard-clamped to auto_cell by audit #66 and cannot
# move along the resolution axis.  Cell count: 30 corpus seeds x 3
# difficulty points x 2 random-pairs goals x 2 mbs values = 360 cells
# for random-pairs; + 30 x 3 (stack_height) x 1 goal x 2 mbs = 180
# cells for stack; 540 cells total.  Output dir defaults to
# eval_results/sweep_<timestamp>_scalability-vs-resolution; pass
# --output eval_results/sweep_anytime to merge into the existing sweep
# (--skip-existing reuses already-completed cells safely).
SCALABILITY_VS_RESOLUTION = [
    {  # semantic, occluder-driven goals — coarse-end sweep
        "n_occluders":        [2, 3, 4],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["holding", "find-and-tray-stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [0.135, 0.18],
        "unit_costs":         [False],
        "scene":              ["random-pairs"],
        "_n_hidden_strategy": "none",
    },
    {  # semantic, stack goal — coarse-end sweep
        "n_occluders":        [2, 3, 4],
        "n_targets":          [3],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [0.09, 0.12],
        "unit_costs":         [False],
        "scene":              ["stack"],
        "_n_hidden_strategy": "none",
    },
]

# audit #108 — a distinct semantic+mbs0.1 floor point. The sweep has semantic
# auto / mbs0.05 / 1.5x / 2x but no 0.10 m floor; this fills it so the
# boxel-count-vs-config figure has an evenly spaced resolution axis. 0.10 m is
# just above random-pairs auto_cell (~0.09) and above stack auto_cell (~0.06).
RESOLUTION_MBS01 = [
    {  # semantic, occluder-driven goals
        "n_occluders":        [2, 3, 4],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["holding", "find-and-tray-stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [0.10],
        "unit_costs":         [False],
        "scene":              ["random-pairs"],
        "_n_hidden_strategy": "none",
    },
    {  # semantic, stack goal
        "n_occluders":        [2, 3, 4],
        "n_targets":          [3],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [0.10],
        "unit_costs":         [False],
        "scene":              ["stack"],
        "_n_hidden_strategy": "none",
    },
]

# audit #113 — fine-end resolution arm.  Probes semantic min_boxel_size at
# 1 cm (0.01) AND 1 mm (0.001): both below auto_cell (~6-9 cm) AND below the
# 3.5 cm octree min_resolution floor, characterising the FINE extreme of the
# resolution axis (complement to the coarse 0.135/0.18 rp / 0.09/0.12 stack).
#
# BLOWUP WARNING (0.001): FreeSpaceGenerator.generate() subdivides every
# MIXED node (one straddling an object/shadow boundary) until max_dim <=
# min_resolution, i.e. to octree depth ~log2(1.0/mbs).  0.035 -> depth 5;
# 0.01 -> depth 7 (~16x boundary cells, slower but feasible); 0.001 -> depth
# 10 (~1000x boundary cells), rebuilt every replan -> expect minutes-to-hours
# of planning and many --timeout 1800 hits.  Those land as exit_reason=
# "timeout" stub rows (NOT no_summary), so they stay valid data points that
# document the implementation limit rather than silently corrupting the sweep.
# Cell count at 30 corpus seeds: 3 x 30 x 2 x 2 = 360 rp + 3 x 30 x 1 x 2 =
# 180 stack = 540 cells.
RESOLUTION_FINE = [
    {  # semantic, occluder-driven goals
        "n_occluders":        [2, 3, 4],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["holding", "find-and-tray-stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [0.001, 0.01],
        "unit_costs":         [False],
        "scene":              ["random-pairs"],
        "_n_hidden_strategy": "none",
    },
    {  # semantic, stack goal
        "n_occluders":        [2, 3, 4],
        "n_targets":          [3],
        "seed":               _CORPUS_SEEDS,
        "goal":               ["stack"],
        "baseline":           ["semantic"],
        "min_boxel_size":     [0.001, 0.01],
        "unit_costs":         [False],
        "scene":              ["stack"],
        "_n_hidden_strategy": "none",
    },
]

# audit #113 — THE full canonical sweep.  Unions every resolution arm into
# one run so a single pass into a FRESH --output dir reproduces EVERY thesis
# figure (success / planning-time / boxel-count / failure-mode / resolution /
# plan-count / wallclock-vs-planning / solved-vs-time) from one clean
# aggregated.csv.  no_summary holes are fixed by the 5bd5f55 pre-flight
# (find-and-tray-stack random-pairs 0-visible seeds re-roll deterministically).
#   SCALABILITY_VS_TIME        semantic auto(None)/0.05 + uniform     810
#   SCALABILITY_VS_RESOLUTION  semantic coarse 0.135/0.18, 0.09/0.12  540
#   RESOLUTION_MBS01           semantic 0.10                          270
#   RESOLUTION_FINE            semantic 0.001 + 0.01                  540
#                                                              total 2160
CANONICAL_FULL = (
    SCALABILITY_VS_TIME
    + SCALABILITY_VS_RESOLUTION
    + RESOLUTION_MBS01
    + RESOLUTION_FINE
)

MATRIX_PRESETS = {
    "scalability":               SCALABILITY_MATRIX,
    "smoke":                     SMOKE_MATRIX,
    "default":                   DEFAULT_MATRIX,
    "random-pairs":              RANDOM_PAIRS_MATRIX,
    "scalability-vs-time":       SCALABILITY_VS_TIME,
    "scalability-vs-resolution": SCALABILITY_VS_RESOLUTION,
    "resolution-mbs01":          RESOLUTION_MBS01,
    "resolution-fine":           RESOLUTION_FINE,
    "canonical-full":            CANONICAL_FULL,
}


# ---------------------------------------------------------------------------
# Cell expansion
# ---------------------------------------------------------------------------

def iterate_matrix(matrix) -> Iterator[Dict]:
    """Expand the matrix into cell dicts.

    A dict value is a single axis-bundle and gets cartesian-product
    expansion.  A list value means union — iterate each sub-matrix in
    turn.  The list form is useful when two axes need to be paired
    (e.g. scene + goal in the "default" matrix), not crossed.

    Keys starting with ``_`` are policies, not axes — they don't multiply
    the product but instead derive fields from other axes.  Currently
    supported: ``_n_hidden_strategy`` ∈ {"all_or_max", "none"}.
    """
    if isinstance(matrix, list):
        for sub in matrix:
            yield from iterate_matrix(sub)
        return
    axis_keys = [k for k in matrix.keys() if not k.startswith("_")]
    axis_vals = [matrix[k] for k in axis_keys]
    n_hidden_strategy = matrix.get("_n_hidden_strategy", "none")
    for combo in itertools.product(*axis_vals):
        cell = dict(zip(axis_keys, combo))
        if n_hidden_strategy == "all_or_max":
            cell["n_hidden"] = min(int(cell["n_targets"]),
                                   int(cell["n_occluders"]))
        else:
            cell["n_hidden"] = 0
        yield cell


def cell_tag(cell: Dict) -> str:
    """Deterministic short label used as the cell directory name."""
    # audit #77 — min_boxel_size is a matrix axis in scalability-vs-time;
    # without it in the tag the size variants of a cell collide on one
    # directory.  Empty for presets that don't sweep it.
    mbs = cell.get("min_boxel_size")
    mbs_sfx = f"_mbs{mbs}" if mbs is not None else ""
    if cell["scene"] == "random-pairs":
        # n_targets / n_hidden are randomized inside the scene builder
        # per seed, so they are NOT part of the matrix axis and would
        # be confusing in the directory name (they vary across runs of
        # the same cell).  Tag by the user-controlled knobs only.
        return (f"randpairs_occ{cell['n_occluders']}"
                f"_seed{cell['seed']}"
                f"_{cell['goal']}_uc{int(cell['unit_costs'])}"
                f"_{cell.get('baseline', 'semantic')}{mbs_sfx}")
    return (f"occ{cell['n_occluders']}_tgt{cell['n_targets']}"
            f"_hid{cell['n_hidden']}_seed{cell['seed']}"
            f"_{cell['goal']}_uc{int(cell['unit_costs'])}"
            f"_{cell.get('baseline', 'semantic')}{mbs_sfx}")


def cell_to_argv(cell: Dict, extra_args: List[str]) -> List[str]:
    """Build ``python test_full_pipeline.py ...`` argv for one cell."""
    argv = [
        sys.executable, "test_full_pipeline.py",
        "--no-gui",
        "--scene", str(cell["scene"]),
        "--seed", str(cell["seed"]),
        "--goal", str(cell["goal"]),
        "--baseline", str(cell.get("baseline", "semantic")),
        "--log-level", "quiet",
        # #P1 F17: the world telemetry recorder defaults ON for headless
        # runs, but it samples the simulator every step and the sweep
        # MEASURES wall-clock — an observer that costs time would shift
        # the very numbers this harness reports (and write ~1-2 MB per
        # cell).  Sweeps therefore opt out; interactive headless
        # diagnostics keep it.
        # TB-22 (tracks rule 18): the opt-out drops the recorder, not the
        # counts.  A headless run without the recorder arms its counts
        # mode (drops and collisions only, a few hundred bytes), so every
        # row carries drops, collisions and clean_success; its cost in
        # wall time is measured in tracks/freeze (--world-counts off in
        # extra_args is the arm without it).
        "--no-telemetry",
    ]
    # audit #67 follow-up — only emit count knobs when the scene
    # actually consumes them.  run_logger auto-promotes
    # --scene default --goal holding to --scene scalability whenever
    # --n-occluders / --n-targets / --n-hidden is on the CLI, so passing
    # them unconditionally turned every (default, holding) cell into a
    # scalability run.
    if cell["scene"] == "scalability":
        # SEED RETRY REMOVED (2026-08-23, user directive): the F5
        # sensable-guarantee pre-flight still vets every cell but now
        # FAILS LOUD instead of re-rolling — a cell whose seed draws an
        # unbuildable or structurally unwinnable scene fails outright
        # and must be counted as a scene failure (or the seed list
        # pre-vetted).  See the PAPER_AUDIT.txt seed-retry-removal
        # note before CB#113.
        argv.extend([
            "--n-occluders", str(cell["n_occluders"]),
            "--n-targets",   str(cell["n_targets"]),
            "--n-hidden",    str(cell["n_hidden"]),
        ])
    elif cell["scene"] == "random-pairs":
        # random-pairs derives n_hidden/n_targets internally from seed
        # and the user-supplied --n-occluders; the other count flags
        # are mutually exclusive with this scene.  Seed retry removed
        # (2026-08-23): infeasible-geometry seeds fail outright, see
        # the scalability comment above.
        argv.extend([
            "--n-occluders", str(cell["n_occluders"]),
        ])
    elif cell["scene"] == "stack":
        # audit #77 — stack has no occluders, so the stack sub-tier
        # reuses the n_occluders axis as the stack tower height.
        # --n-objects stays at its default 3; the pipeline spawns
        # max(n_objects, stack_height) cubes, so heights {2,3,4} spawn
        # {3,3,4} — all within the {3,4,5} the eval corpus vetted.
        argv.extend(["--stack-height", str(cell["n_occluders"])])
    # audit #77 — semantic free-space granularity knob.  Emitted only
    # when the cell carries it (scalability-vs-time); other presets
    # omit it so run_logger keeps the audit-#67 default.
    if cell.get("min_boxel_size") is not None:
        argv.extend(["--min-boxel-size", str(cell["min_boxel_size"])])
    if cell["unit_costs"]:
        argv.append("--unit-costs")
    return argv + list(extra_args)


# ---------------------------------------------------------------------------
# Per-cell execution
# ---------------------------------------------------------------------------

def _run_dir_names() -> set:
    """Names of the ``logs/run_*`` directories that exist right now."""
    logs_dir = Path("logs")
    if not logs_dir.is_dir():
        return set()
    return {d.name for d in logs_dir.iterdir()
            if d.is_dir() and d.name.startswith("run_")}


def _find_new_timing_summary(before: set) -> Optional[Path]:
    """Locate the timing_summary.json written by the just-finished cell.

    test_full_pipeline.py creates ``logs/run_<ts>/timing_summary.json``
    via report_run_outcome.  Only a run directory that did NOT exist
    before the subprocess started can belong to this cell (``before`` is
    _run_dir_names() captured just before launch).

    The old rule took the newest summary whose mtime was within a 1 s
    slack of the launch time.  A cell rejected by the pre-flight exits 1
    before it creates any run directory, so that rule handed it the
    PREVIOUS cell's summary whenever the previous cell had finished less
    than a second earlier: CB#113 banked 10 of its 43 pre-flight-rejected
    find-and-tray-stack cells as the preceding holding run's success.
    """
    logs_dir = Path("logs")
    candidates = []
    for name in _run_dir_names() - before:
        summary = logs_dir / name / "timing_summary.json"
        if summary.exists():
            candidates.append((summary.stat().st_mtime, summary))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def _summary_mismatch(run_config: Optional[Dict], cell: Dict) -> Optional[str]:
    """Why a summary's run_config cannot belong to ``cell``, or None.

    Compares the knobs the runner passes on the command line, so a
    summary from any other cell (a neighbouring goal, seed, baseline or
    boxel size) is caught even if it lands in a new run directory.
    """
    if not isinstance(run_config, dict):
        return "no run_config"
    expected = {
        "scene": cell["scene"],
        "seed": cell["seed"],
        "goal": cell["goal"],
        "baseline": cell.get("baseline", "semantic"),
        "unit_costs": bool(cell["unit_costs"]),
    }
    if cell.get("min_boxel_size") is not None:
        expected["min_boxel_size"] = cell["min_boxel_size"]
    diffs = [f"{k}={run_config.get(k)!r} (cell {v!r})"
             for k, v in expected.items() if run_config.get(k) != v]
    return ", ".join(diffs) or None


def _preflight_rejection(output: str) -> Optional[str]:
    """The pre-flight rejection line in a cell's output, or None.

    test_full_pipeline.py prints ``[pre-flight] seed N rejected: ...``
    to stderr when the scene cannot be built or the tray-stack goal
    cannot be formed, then exits 1 without a run directory.
    """
    for line in output.splitlines():
        if line.startswith("[pre-flight] seed ") and " rejected: " in line:
            return line.strip()
    return None


def _stored_rejection(cell_dir: Path) -> Optional[str]:
    """The pre-flight rejection line in a cell's stored stdout.log, or None."""
    stdout_log = cell_dir / "stdout.log"
    if not stdout_log.exists():
        return None
    return _preflight_rejection(
        stdout_log.read_text(encoding="utf-8", errors="replace"))


def _run_dir_claims(cells_root: Path) -> Dict[str, int]:
    """How many cells of a sweep name each run directory in run_dir.txt."""
    claims: Dict[str, int] = {}
    if cells_root.is_dir():
        for p in cells_root.glob("*/run_dir.txt"):
            run_dir = p.read_text().strip()
            claims[run_dir] = claims.get(run_dir, 0) + 1
    return claims


def _another_cells_run(cell_dir: Path, claims: Dict[str, int]) -> bool:
    """Whether a stored summary whose run_config differs from its cell
    shows that it is not the cell's own run (TB-20).

    A differing run_config alone proves nothing: until 2026-08-23 the
    pre-flight re-rolled a rejected seed, so a cell's own run of that time
    carries another seed.  A summary the pre-fix runner banked from
    another cell shows it: the cell's own output holds the pre-flight's
    rejection (the cell made no run), or another cell of the sweep names
    the same run directory.
    """
    if _stored_rejection(cell_dir):
        return True
    run_dir_txt = cell_dir / "run_dir.txt"
    return (run_dir_txt.exists()
            and claims.get(run_dir_txt.read_text().strip(), 0) > 1)


# C-01: how many of the last lines of a crashed cell's stderr its row
# keeps (the end of the traceback; the whole output is in stdout.log).
STDERR_TAIL_LINES = 20


def run_cell(
    cell: Dict,
    sweep_dir: Path,
    timeout_s: float,
    extra_args: List[str],
    skip_existing: bool,
) -> Dict:
    """Run one cell in a subprocess and collect its timing_summary.json.

    Returns a dict suitable for aggregation: cell config + metrics, or a
    stub row with ``success=False`` and a diagnostic ``exit_reason`` on
    timeout / crash / pre-flight rejection / missing summary / a new
    run's summary that belongs to another cell.
    """
    tag = cell_tag(cell)
    cell_dir = sweep_dir / "cells" / tag
    cell_dir.mkdir(parents=True, exist_ok=True)

    summary_path = cell_dir / "timing_summary.json"
    stdout_path = cell_dir / "stdout.log"

    if skip_existing and summary_path.exists():
        try:
            existing = json.loads(summary_path.read_text())
        except Exception:
            existing = None
        # A summary banked from another cell (the pre-fix runner, see
        # _find_new_timing_summary) is not a result for this cell: run
        # it again instead of resuming from it.  Its run_config differs
        # from the cell and the cell's files show it (_another_cells_run);
        # a differing run_config alone is the cell's own run (TB-20).
        # Runner stubs (timeout, crash, pre-flight) carry no run_config
        # and are kept as is.
        mismatch = (_summary_mismatch(existing["run_config"], cell)
                    if existing is not None and "run_config" in existing
                    else None)
        if existing is not None and (
                mismatch is None
                or not _another_cells_run(cell_dir,
                                          _run_dir_claims(cell_dir.parent))):
            return {**cell, **existing}
        if existing is not None:
            print(f"[runner] {tag}: stored summary belongs to another cell "
                  f"({mismatch}); re-running")

    argv = cell_to_argv(cell, extra_args)
    print(f"[runner] {tag}: launching")
    t0 = time.perf_counter()
    runs_before = _run_dir_names()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=os.getcwd(),
        )
    except subprocess.TimeoutExpired:
        wall = time.perf_counter() - t0
        stub = {
            **cell,
            "success": False,
            "exit_reason": "timeout",
            "wall_clock_s": round(wall, 3),
        }
        summary_path.write_text(json.dumps(stub, indent=2))
        print(f"[runner] {tag}: TIMEOUT after {timeout_s}s")
        return stub

    wall = time.perf_counter() - t0
    stdout_path.write_text(
        (proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or ""),
        encoding="utf-8",
    )

    # test_full_pipeline.py exits 0 on success, 1 on run-level failure
    # (exit_reason set by report_run_outcome).  Anything else = crash.
    # C-01: an exception in main() exits 70 (crash_exit70).  The exit
    # code is read before any summary, so a crash after the summary was
    # written is a crash row too, and that summary is not banked.
    if proc.returncode not in (0, 1):
        tail = (proc.stderr or "").splitlines()[-STDERR_TAIL_LINES:]
        stub = {
            **cell,
            "success": False,
            "exit_reason": f"crash_exit{proc.returncode}",
            "wall_clock_s": round(wall, 3),
            "stderr_tail": tail,
        }
        summary_path.write_text(json.dumps(stub, indent=2))
        print(f"[runner] {tag}: CRASH exit={proc.returncode}")
        return stub

    ts_path = _find_new_timing_summary(runs_before)
    if ts_path is None:
        rejection = _preflight_rejection(proc.stderr or "")
        stub = {
            **cell,
            "success": False,
            "exit_reason": ("preflight_rejected" if rejection
                            else "no_summary"),
            "wall_clock_s": round(wall, 3),
        }
        if rejection:
            stub["preflight_message"] = rejection
        summary_path.write_text(json.dumps(stub, indent=2))
        print(f"[runner] {tag}: "
              + (rejection or "NO timing_summary.json found"))
        return stub

    mismatch = _summary_mismatch(
        json.loads(ts_path.read_text()).get("run_config"), cell)
    if mismatch is not None:
        stub = {
            **cell,
            "success": False,
            "exit_reason": "summary_mismatch",
            "summary_mismatch": mismatch,
            "foreign_run_dir": str(ts_path.parent.absolute()),
            "wall_clock_s": round(wall, 3),
        }
        summary_path.write_text(json.dumps(stub, indent=2))
        print(f"[runner] {tag}: the new run's summary belongs to another "
              f"cell ({mismatch}); not banked")
        return stub

    shutil.copy2(ts_path, summary_path)
    (cell_dir / "run_dir.txt").write_text(str(ts_path.parent.absolute()))

    summary = json.loads(summary_path.read_text())
    summary["wall_clock_s"] = round(wall, 3)
    summary_path.write_text(json.dumps(summary, indent=2))

    out_row = {**cell, **summary}
    ok = "OK" if summary.get("success") else "FAIL"
    print(f"[runner] {tag}: {ok} "
          f"plan_count={summary.get('plan_count')} "
          f"plan_time_s={summary.get('total_planning_time_s')}")
    return out_row


def run_cell_counted(
    cell: Dict,
    sweep_dir: Path,
    timeout_s: float,
    extra_args: List[str],
    skip_existing: bool,
) -> Dict:
    """run_cell, with rule 18's fields in every row (TB-22).

    A cell whose run wrote its summary carries the fields already.  A stub
    row gets them here, and so does the cell's stored stub: a rejected
    cell ran no episode; a cell killed at the wall-clock budget, crashed
    or left without a summary has the counts its run kept in
    world_counts.json up to its end (only a run directory that did not
    exist before the launch can be the cell's, as for the summary, TB-8);
    with none, and for every other row without counts (a summary of
    another cell, a stored row from before the counts), the fields say
    "not detected" and the counts stay empty, never 0.  A stored row that
    this call only resumed (--skip-existing) is not rewritten.
    """
    summary_path = sweep_dir / "cells" / cell_tag(cell) / "timing_summary.json"
    stored_before = (summary_path.read_text()
                     if summary_path.exists() else None)
    runs_before = _run_dir_names()
    row = run_cell(cell, sweep_dir, timeout_s, extra_args, skip_existing)
    if "drops" in row:
        return row
    reason = str(row.get("exit_reason"))
    if reason == "preflight_rejected":
        fields = world_counts.not_detected(
            False, why="pre-flight rejected: no episode ran")
    elif reason == "summary_mismatch":
        fields = world_counts.not_detected(
            False, why="the new run's summary belongs to another cell")
    elif reason in ("timeout", "no_summary") or reason.startswith("crash_exit"):
        fields = world_counts.from_run_dir(
            world_counts.newest_counts_dir("logs", runs_before), success=False)
    else:
        fields = world_counts.not_detected(
            bool(row.get("success")), why="the record has no counts")
    row.update(fields)
    try:
        text = summary_path.read_text()
        stored = json.loads(text)
        if text != stored_before and "drops" not in stored:
            stored.update(fields)
            summary_path.write_text(json.dumps(stored, indent=2))
    except Exception as e:
        print(f"[runner] {cell_tag(cell)}: the stored row did not get the "
              f"count fields: {e}")
    return row


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

# Stable column ordering so the CSV is diffable across sweeps.
PRIMARY_COLUMNS = [
    "scene", "n_occluders", "n_targets", "n_hidden", "seed",
    "goal", "unit_costs",
    "baseline", "uniform_cell_size",
    "success", "exit_reason",
    # TB-22 (tracks rule 18): success with no drop and no collision, and
    # the two counts (empty where nothing could see the event).
    "clean_success", "drops", "collisions",
    "plan_count", "total_planning_time_s", "wall_clock_s",
]

# Fields that are list-valued (per-call timings, per-action failures);
# don't fit a flat CSV so we drop them from the aggregated CSV but keep
# them in aggregated.jsonl for downstream tooling.  Despite the name,
# also covers dict-valued keys (e.g. audit #73's n_facts_by_predicate)
# — anything non-scalar that would stringify badly in a CSV cell.
LIST_VALUED = {
    "per_call_planning_time_s",
    "physical_failures_per_action",
    "physical_failures_at_goal",
    "n_facts_by_predicate",
    # Audit #73 step 2(c): per-boxel volume lists for plot 3
    # (heterogeneity histogram).  Variable-length, jsonl-only.
    "boxel_volumes_object",
    "boxel_volumes_shadow",
    "boxel_volumes_free_space",
    # Audit #73 step 2(d): per-replan boxel count snapshots for plot 11
    # (boxel evolution across replans).  List-of-dicts, jsonl-only.
    "boxel_counts_per_replan",
    # TB-22: what the drop and collision counts counted, jsonl-only.
    "drop_events", "collision_events", "drops_noticed_by",
    # C-01: a crashed cell's last stderr lines, jsonl-only.
    "stderr_tail",
}


def aggregate(sweep_dir: Path) -> Path:
    """Walk sweep_dir/cells/*/timing_summary.json into aggregated.csv +
    aggregated.jsonl.

    Cells are checked against sweep_dir/matrix.json, so sweeps run by the
    pre-fix runner aggregate correctly without touching their cell files:
    a summary banked from another cell becomes a ``preflight_rejected``
    (or ``summary_mismatch``) row for this cell, and a ``no_summary`` stub
    whose output shows a pre-flight rejection is relabelled the same way.
    A summary counts as banked when its run_config differs from the cell
    and the cell's files show it (_another_cells_run); a differing
    run_config alone, such as a seed the pre-flight re-rolled before
    2026-08-23, stays the cell's own run (TB-20).
    """
    cells_root = sweep_dir / "cells"
    claims = _run_dir_claims(cells_root)
    cells_by_tag: Dict[str, Dict] = {}
    matrix_path = sweep_dir / "matrix.json"
    if matrix_path.exists():
        try:
            cells_by_tag = {
                cell_tag(c): c
                for c in json.loads(matrix_path.read_text()).get("cells", [])
            }
        except Exception as e:
            print(f"[aggregate] cannot read {matrix_path}: {e}")
    rows: List[dict] = []
    n_relabelled = 0
    n_own = 0
    if cells_root.is_dir():
        for tag_dir in sorted(cells_root.iterdir()):
            if not tag_dir.is_dir():
                continue
            ts = tag_dir / "timing_summary.json"
            if not ts.exists():
                continue
            try:
                data = json.loads(ts.read_text())
            except Exception as e:
                print(f"[aggregate] skipping {tag_dir.name}: {e}")
                continue
            cell = cells_by_tag.get(tag_dir.name)
            mismatch = (_summary_mismatch(data["run_config"], cell)
                        if cell is not None and "run_config" in data
                        else None)
            if mismatch is not None and not _another_cells_run(tag_dir,
                                                               claims):
                n_own += 1
                print(f"[aggregate] {tag_dir.name}: run_config differs from "
                      f"the cell ({mismatch}); kept as the cell's own run")
                mismatch = None
            if mismatch is not None or data.get("exit_reason") == "no_summary":
                stdout_log = tag_dir / "stdout.log"
                rejection = (_preflight_rejection(stdout_log.read_text(
                                 encoding="utf-8", errors="replace"))
                             if stdout_log.exists() else None)
                if mismatch is not None:
                    data = {**cell, "success": False,
                            "exit_reason": "summary_mismatch",
                            "summary_mismatch": mismatch,
                            "wall_clock_s": data.get("wall_clock_s")}
                if rejection:
                    data["exit_reason"] = "preflight_rejected"
                    data["preflight_message"] = rejection
                if mismatch is not None or rejection:
                    n_relabelled += 1
                    print(f"[aggregate] {tag_dir.name}: "
                          f"{data['exit_reason']}"
                          + (f" (banked summary of another cell: {mismatch})"
                             if mismatch is not None else ""))
            rc = data.get("run_config")
            if isinstance(rc, dict):
                for k, v in rc.items():
                    data.setdefault(k, v)
            if "drops" not in data:
                # TB-22: a record made without the counts (a sweep from
                # before them, or a row relabelled above): every row still
                # carries the fields, and they say that nothing watched.
                data.update(world_counts.not_detected(
                    bool(data.get("success")),
                    why="the record has no counts"))
            rows.append(data)

    extra_keys = sorted({k for r in rows for k in r.keys()}
                        - set(PRIMARY_COLUMNS) - LIST_VALUED - {"run_config"})
    columns = PRIMARY_COLUMNS + extra_keys

    csv_path = sweep_dir / "aggregated.csv"
    jsonl_path = sweep_dir / "aggregated.jsonl"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"[aggregate] wrote {csv_path} ({len(rows)} rows, "
          f"{n_relabelled} relabelled, {n_own} kept as their own runs "
          f"with a run_config unlike their cell)")
    print(f"[aggregate] wrote {jsonl_path}")
    return csv_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_seed_spec(spec: str) -> List[int]:
    """'0:5' -> [0,1,2,3,4]; '0,2,4' -> [0,2,4]; '7' -> [7]."""
    if ":" in spec:
        a, b = spec.split(":", 1)
        return list(range(int(a), int(b)))
    return [int(s) for s in spec.split(",") if s.strip()]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--matrix", choices=list(MATRIX_PRESETS.keys()),
                        default="scalability",
                        help="Built-in matrix preset.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Sweep output directory (default: "
                             "eval_results/sweep_<timestamp>_<matrix>).")
    parser.add_argument("--seeds", type=str, default=None,
                        help="Override seed list, e.g. '0:5' or '0,2,4'.")
    parser.add_argument("--timeout", type=float, default=300.0,
                        help="Per-cell wall-clock timeout in seconds "
                             "(default: 300).")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Reuse existing timing_summary.json in cell dirs "
                             "(resume after crash without re-running).")
    parser.add_argument("--max-failures", type=int, default=-1,
                        help="Abort the sweep after this many crash/timeout "
                             "cells (-1 = never abort).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the cell list and exit.")
    parser.add_argument("--extra-arg", action="append", default=[],
                        metavar="ARG",
                        help="Pass-through argv for test_full_pipeline.py "
                             "(repeatable).")
    args = parser.parse_args(argv)

    matrix_preset = MATRIX_PRESETS[args.matrix]
    seeds_override = (_parse_seed_spec(args.seeds)
                      if args.seeds is not None else None)
    if isinstance(matrix_preset, list):
        if seeds_override is not None:
            matrix = [{**sub, "seed": seeds_override}
                      for sub in matrix_preset]
        else:
            matrix = matrix_preset
    else:
        matrix = dict(matrix_preset)
        if seeds_override is not None:
            matrix["seed"] = seeds_override

    cells = list(iterate_matrix(matrix))
    print(f"[runner] matrix={args.matrix}, {len(cells)} cells")

    if args.dry_run:
        for c in cells:
            print(f"  {cell_tag(c)}")
        return 0

    # Audit #96 — verify the subprocess interpreter can import the
    # eval's core deps before spawning thousands of subprocesses that
    # all fail.  The 2026-05-19 sweep had 5 cells crash with "No module
    # named 'numpy'" because eval_runner.py had been launched with a
    # Python (e.g. native Windows) that lacks the wsl_env packages.
    probe = subprocess.run(
        [sys.executable, "-c", "import numpy, pybullet"],
        capture_output=True, text=True,
    )
    if probe.returncode != 0:
        print(f"[runner] FATAL: subprocess interpreter "
              f"{sys.executable} cannot import numpy/pybullet.",
              file=sys.stderr)
        print(f"[runner] launch via wsl bash tools/_run_in_wsl.sh "
              f"eval_runner.py ... to use the wsl_env Python.",
              file=sys.stderr)
        if probe.stderr.strip():
            print(f"[runner] probe stderr:\n{probe.stderr.rstrip()}",
                  file=sys.stderr)
        return 2

    sweep_dir = args.output or (
        Path("eval_results")
        / f"sweep_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}_{args.matrix}"
    )
    sweep_dir.mkdir(parents=True, exist_ok=True)
    (sweep_dir / "matrix.json").write_text(
        json.dumps({"preset": args.matrix, "cells": cells}, indent=2)
    )

    n_failures = 0
    for i, cell in enumerate(cells, 1):
        print(f"\n[runner] cell {i}/{len(cells)}")
        row = run_cell_counted(cell, sweep_dir, args.timeout,
                               args.extra_arg, args.skip_existing)
        if not row.get("success"):
            n_failures += 1
            if 0 <= args.max_failures < n_failures:
                print(f"[runner] aborting: {n_failures} failures > "
                      f"--max-failures {args.max_failures}")
                break

    aggregate(sweep_dir)
    print(f"\n[runner] sweep complete: {sweep_dir} "
          f"(failures: {n_failures}/{len(cells)})")
    return 0 if n_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
