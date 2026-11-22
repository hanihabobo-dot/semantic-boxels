#!/usr/bin/env python3
"""Path 6: run one seed slot of phase 1a (or the cluster smoke's cells) through
the arm's OWN eval_runner.

Run it with the arm's python and with the arm's code directory as the working
directory (the node-local copy of the arm's snapshot): the pipeline writes logs/
and temp/ in its working directory, and `import eval_runner` must find that
commit's own runner there, so each arm runs through its own runner (arm A: the
tag's with TB-8 and TB-20; arm B: the thesis commit's, with its seed retry).

  cd <arm code dir> && <python> <A snapshot>/tools/cluster/p6_run.py \\
      --arm A|B --slot N --out DIR [--timeout 1800]        a slot: 9 cells
  ... --set smoke ...                                       the smoke's 3 cells
  ... --set all --only-tags TAG[,TAG...] ...                a final pass
  ... --dry-run                                             print, run nothing
  ... [--min-avail-gb 4] [--peak-report-gb 6]               rule 16's limits, GB (0: only record)
  ... [--fresh-stream-stats]                                TB-24: no statistics carried between cells

TB-24 (--fresh-stream-stats): every pipeline run loads pddlstream's stream statistics from
statistics/py<N>/ in its working directory and rewrites them with its own measured times.  The
working directory is the arm's code copy, so a cell starts from the times of the arm's cells
before it in the same job.  With the switch that folder is removed before every cell that runs
(the runner's run_cell is wrapped at run time, as for rule 16; the arm's files stay unedited),
and every cell starts as the first run in a fresh copy does.  p6_run.json records the switch.

Rule 16 (tools/memwatch.py): the runner's run_cell is wrapped at run time (the arm's own
file stays unedited) so that each cell's MemAvailable at its start and end, its peak RSS
and its process sum are recorded in OUT/mem_cells.jsonl (`mem`, `peak_over_6gb`) and in the
log; MemAvailable under the limit stops the batch after that cell: STOPPED_LOW_MEMORY in
the log and in OUT/STOPPED_LOW_MEMORY.txt, the cells so far aggregated, exit code 4.

The cells are injected into the runner's MATRIX_PRESETS as the preset
'p6-slot' (tools/p6_slots.py names them); nothing else of the runner is touched
and no --extra-arg is passed: an extra argument that overrides a cell's knob
(scene, seed, goal, baseline, unit costs, boxel size, --n-occluders on a scene
that takes the cell's own) turns every cell into a summary_mismatch stub
(TB-20's caution), and tests/test_p6_tools.py checks the argv.
"""
import argparse
import hashlib
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
PRESET = 'p6-slot'
STATS_DIR = 'statistics'        # pddlstream: statistics/py<N>/<domain>-streams.pkl under the working directory


def statistics_files(target):
    """The files under a pddlstream statistics folder, or SystemExit when it holds anything that
    is not statistics/py<N>/<name>.pkl: only such a folder is ever removed."""
    found = []
    for root, _, files in os.walk(target):
        rel = os.path.relpath(root, target)
        for name in files:
            if rel == '.' or os.sep in rel or not rel.startswith('py') or not name.endswith('.pkl'):
                raise SystemExit(f"{target} holds {os.path.join(rel, name)}, which is not pddlstream's "
                                 "statistics/py<N>/<name>.pkl: nothing removed, nothing run")
            found.append(os.path.join(root, name))
    return found


def install_fresh_statistics(er, code_dir, log=print):
    """TB-24 (tracks/BUGS.md): wrap `run_cell` of the arm's own runner so that pddlstream's stream
    statistics are removed before every cell that runs.  Each pipeline run loads
    statistics/py<N>/boxel-streams.pkl from its working directory (the arm's code copy) and
    rewrites it with its own measured times, so without this a cell starts from the times of the
    arm's cells before it in the same job and its plan can depend on its place in the job.  With
    it every cell starts as the first run in a fresh copy does.  A cell the runner skips
    (--skip-existing, its summary is banked) removes nothing.  The arm's files stay unedited: the
    one folder under the working directory is removed by its path, and only when it holds nothing
    but such files.  Returns the wrapper."""
    orig = er.run_cell
    target = os.path.join(code_dir, STATS_DIR)

    def fresh(cell, sweep_dir, timeout_s, extra_args, skip_existing):
        tag = er.cell_tag(cell)
        banked = skip_existing and os.path.exists(os.path.join(str(sweep_dir), 'cells', tag, 'timing_summary.json'))
        if not banked and os.path.isdir(target):
            files = statistics_files(target)
            shutil.rmtree(target)
            log(f"stats {tag}: removed {target} ({len(files)} file(s)) before the cell")
        return orig(cell, sweep_dir, timeout_s, extra_args, skip_existing)
    er.run_cell = fresh
    return fresh


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()


def cpu_model():
    try:
        with open('/proc/cpuinfo', 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith('model name'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return None


def select_cells(ps, arm, which, slot, only_tags):
    """The cells to run, in order: a slot's nine, the smoke's three, or every
    cell of the arm (for a final pass), cut down to only_tags when given."""
    if which == 'smoke':
        cells = ps.smoke_cells()
    elif which == 'slot':
        if slot is None:
            raise SystemExit('--set slot needs --slot')
        cells = ps.slot_cells(arm, slot)
    else:
        cells = [c for s in range(ps.N_SLOTS) for c in ps.slot_cells(arm, s)]
    if only_tags is not None:
        wanted = [t for t in only_tags.split(',') if t.strip()]
        known = {ps.expected_tag(c) for c in cells}
        unknown = [t for t in wanted if t not in known]
        if unknown:
            raise SystemExit(f"--only-tags names cells not in this set: {unknown}")
        cells = [c for c in cells if ps.expected_tag(c) in wanted]
    return cells


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--arm', required=True, choices=('A', 'B'))
    ap.add_argument('--set', dest='which', choices=('slot', 'smoke', 'all'), default='slot')
    ap.add_argument('--slot', type=int, default=None)
    ap.add_argument('--out', required=True, help="the arm's sweep folder (cells/, matrix.json, aggregated.*)")
    ap.add_argument('--timeout', type=float, default=1800.0, help='per-cell wall cap, s')
    ap.add_argument('--only-tags', default=None)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--min-avail-gb', type=float, default=None,
                    help="rule 16: MemAvailable under this stops the batch after the cell (default 4; 0 only records)")
    ap.add_argument('--peak-report-gb', type=float, default=None,
                    help="rule 16: a peak RSS over this is flagged peak_over_6gb (default 6; 0 only records)")
    ap.add_argument('--fresh-stream-stats', action='store_true',
                    help="TB-24: remove the working directory's statistics/ (pddlstream's stream statistics) "
                         "before every cell that runs, so that no cell starts from the cells before it")
    a = ap.parse_args(argv)

    code = os.getcwd()
    sys.path.insert(0, code)          # this commit's own eval_runner, before anything else
    if TOOLS not in sys.path:
        sys.path.append(TOOLS)
    # The arm's code is a commit of the folder layout (eval_runner in evaluation/) or one from
    # before the folder move, such as the thesis commit (eval_runner.py at its root).
    folders = os.path.isfile(os.path.join(code, 'evaluation', 'eval_runner.py'))
    if folders:
        from evaluation import eval_runner as er
    else:
        import eval_runner as er
    import memwatch
    import p6_slots as ps

    er_dir = os.path.dirname(os.path.realpath(er.__file__))
    if er_dir != os.path.realpath(os.path.join(code, 'evaluation') if folders else code):
        raise SystemExit(f"eval_runner came from {er_dir}, not from the working directory {code}: "
                         "run p6_run.py from the arm's code directory")

    cells = select_cells(ps, a.arm, a.which, a.slot, a.only_tags)
    if not cells:
        raise SystemExit('no cells selected')
    er.MATRIX_PRESETS[PRESET] = ps.as_matrix(cells)

    # The runner's own expansion must give exactly the cells and tags this
    # script names: a drift between the two would run other cells than planned.
    expanded = list(er.iterate_matrix(er.MATRIX_PRESETS[PRESET]))
    tags = [er.cell_tag(c) for c in expanded]
    if tags != [ps.expected_tag(c) for c in cells]:
        raise SystemExit('the runner expands the preset to other cell tags than p6_slots names:\n'
                         f"{tags}\n{[ps.expected_tag(c) for c in cells]}")

    out = os.path.abspath(a.out)
    runner_argv = ['--matrix', PRESET, '--output', out, '--timeout', str(a.timeout), '--skip-existing']
    if a.dry_run:
        print(f"arm {a.arm}, {len(cells)} cells, runner {er.__file__}")
        for c in expanded:
            print(f"  {er.cell_tag(c)}: " + ' '.join(er.cell_to_argv(c, [])[1:]))
        print('runner argv: ' + ' '.join(runner_argv))
        return 0

    os.makedirs(out, exist_ok=True)
    meta = {'arm': a.arm, 'set': a.which, 'slot': a.slot, 'cells': tags, 'timeout_s': a.timeout,
            'code_dir': code, 'eval_runner': os.path.realpath(er.__file__),
            'eval_runner_sha256': sha256_file(er.__file__), 'python': sys.executable,
            'python_version': sys.version.split()[0], 'host': platform.node(),
            'cpu': cpu_model(), 'job': os.environ.get('SLURM_JOB_ID'),
            'pythonhashseed': os.environ.get('PYTHONHASHSEED'),
            'started': time.strftime('%Y-%m-%d %H:%M:%S')}
    meta_path = os.path.join(out, 'p6_run.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)
    min_kb = memwatch.limit_kb(memwatch.MIN_AVAIL_GB if a.min_avail_gb is None else a.min_avail_gb)
    peak_kb = memwatch.limit_kb(memwatch.PEAK_REPORT_GB if a.peak_report_gb is None else a.peak_report_gb)
    meta.update(min_avail_limit_kb=min_kb, peak_limit_kb=peak_kb, fresh_stream_stats=bool(a.fresh_stream_stats))
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)
    if a.fresh_stream_stats:
        if not hasattr(er, 'run_cell'):
            raise SystemExit('--fresh-stream-stats needs a runner with run_cell')
        # inside the memory guard, so that a cell's record covers its own run only
        install_fresh_statistics(er, code, log=lambda s: print('[stats] ' + s, flush=True))
    if hasattr(er, 'run_cell'):
        memwatch.install_run_cell_guard(er, out, min_kb, peak_kb, log=lambda s: print('[mem] ' + s, flush=True))
    t0 = time.time()
    try:
        rc = er.main(runner_argv)
    except memwatch.LowMemory as e:
        # the cells that ran have their summaries on disk; the runner's own end-of-run aggregation did not run
        if hasattr(er, 'aggregate'):
            try:
                er.aggregate(Path(out))
            except Exception as err:      # the stop is the verdict, not the aggregation
                print(f"[mem] aggregation after the stop failed: {err!r}", flush=True)
        memwatch.write_stop(out, e)
        meta.update(finished=time.strftime('%Y-%m-%d %H:%M:%S'), wall_s=round(time.time() - t0, 1),
                    runner_rc=None, stopped='STOPPED_LOW_MEMORY', stopped_at=str(e))
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=1)
        return memwatch.EXIT_LOW_MEMORY
    meta.update(finished=time.strftime('%Y-%m-%d %H:%M:%S'), wall_s=round(time.time() - t0, 1),
                runner_rc=rc)
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)
    # the runner's rc is 1 when any cell did not succeed, which is a result;
    # only its fatal rc (2: the interpreter cannot import numpy, pybullet) is ours
    return 2 if rc == 2 else 0


if __name__ == '__main__':
    sys.exit(main())
