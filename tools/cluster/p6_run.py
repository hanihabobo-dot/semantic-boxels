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
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
PRESET = 'p6-slot'


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
    a = ap.parse_args(argv)

    code = os.getcwd()
    sys.path.insert(0, code)          # this commit's own eval_runner, before anything else
    if TOOLS not in sys.path:
        sys.path.append(TOOLS)
    import eval_runner as er
    import p6_slots as ps

    er_dir = os.path.dirname(os.path.realpath(er.__file__))
    if er_dir != os.path.realpath(code):
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
    t0 = time.time()
    rc = er.main(runner_argv)
    meta.update(finished=time.strftime('%Y-%m-%d %H:%M:%S'), wall_s=round(time.time() - t0, 1),
                runner_rc=rc)
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=1)
    # the runner's rc is 1 when any cell did not succeed, which is a result;
    # only its fatal rc (2: the interpreter cannot import numpy, pybullet) is ours
    return 2 if rc == 2 else 0


if __name__ == '__main__':
    sys.exit(main())
