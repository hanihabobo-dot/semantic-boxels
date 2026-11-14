"""pin_outputs.py: the generator of the Phase 0 pins (readable migration).

    python tools/readable/pin_outputs.py --group low --out DIR [--only p05_registry,p08_domain]
    python tools/readable/pin_outputs.py --list [--group low]
    python tools/readable/pin_outputs.py --compare DIR_A DIR_B

A pin is a function that calls today's pipeline code on fixed inputs and
writes what it returns as files.  ``--group G --out DIR`` writes every pin of
group G under ``DIR/<pin id>/`` and ``DIR/MANIFEST.json`` (status and the
sha256 of every file per pin).  Each pin runs in its own child process
(``--child``): a fresh interpreter, cwd a fresh temporary folder (the
pipeline writes ``boxel_data.json``, ``temp/`` and ``logs/`` into the cwd),
``HOME`` that folder too, ``PYTHONHASHSEED=0``, ``COLUMNS=80``,
``LC_ALL=LANG=C.UTF-8``, ``PYTHONDONTWRITEBYTECODE=1``, and none of the
console's switches (``FORCE_COLOR``, ``SB_CONSOLE_ASCII``, ``SB_AUDIO``,
``SB_VOICE``) inherited.  So no pin sees another pin's module state.

R's rules (review/BEHAVIOUR.md 6.2) as this file applies them:
  1. No stored output yet: golden outputs are made later on tag
     refactor-checkpoint-2, by this script, into a folder given by --out.
  2. Two passes on unchanged code must give equal files (``--compare``).
  3. Exact: floats as json.dumps writes them (repr round trip; inf and nan
     as Infinity and NaN), big float arrays as the sha256 of their float64
     bytes plus the shape.  No rounding anywhere unless a pin's NOTES say so.
  4. A list that comes from a set is sorted and the pin's NOTES.txt says so;
     ``plain()`` refuses a set, so a set can never be written unsorted.
  5. Run in WSL with /root/armO-venvA/bin/python under
     ``flock /root/sb_pipeline.lock`` (the pins import pybullet but start no
     physics client; none is a whole episode).

Paths are masked in every file: the repo as ``<REPO>``, the pin's work
folder as ``<WORK>``, the output folder as ``<OUT>``.

Groups: ``low`` (this build: the low-cost pins and the AST pins of the
index phase0/index/pins_low.md); later builds add their own groups (world,
episode) with the same ``@pin`` decorator.
"""
import argparse
import ast
import contextlib
import enum
import hashlib
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve()
PIN_TIMEOUT_S = 600

# group -> {pin id: Pin}, in registration order.
GROUPS = {}


class Pin:
    def __init__(self, group, pin_id, about, func, timeout):
        self.group, self.id, self.about = group, pin_id, about
        self.func, self.timeout = func, timeout


def pin(group, pin_id, about, timeout=PIN_TIMEOUT_S):
    """Register a pin function f(out: Out) under group/pin_id."""
    def deco(func):
        GROUPS.setdefault(group, {})[pin_id] = Pin(group, pin_id, about, func, timeout)
        return func
    return deco


# ---------------------------------------------------------------------------
# Writing outputs
# ---------------------------------------------------------------------------

class Masker:
    def __init__(self, pairs):
        # Longest first, so a path inside another is replaced whole.
        self.pairs = sorted(((str(a), b) for a, b in pairs if a), key=lambda t: -len(t[0]))

    def __call__(self, s):
        for a, b in self.pairs:
            if a in s:
                s = s.replace(a, b)
        return s


def plain(obj, mask=lambda s: s):
    """A JSON-ready copy of obj.  numpy arrays and scalars become lists and
    numbers, tuples lists, Paths masked strings.  A set is refused (R's rule
    4: the pin sorts it itself and says so)."""
    try:
        import numpy as np
    except ImportError:            # pragma: no cover
        np = None
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, str):
        return mask(obj)
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return obj
    if np is not None:
        if isinstance(obj, np.ndarray):
            return plain(obj.tolist(), mask)
        if isinstance(obj, np.generic):
            return plain(obj.item(), mask)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"non-str dict key {k!r}: convert it in the pin")
            out[mask(k)] = plain(v, mask)
        return out
    if isinstance(obj, (list, tuple)):
        return [plain(v, mask) for v in obj]
    if isinstance(obj, (set, frozenset)):
        raise TypeError("a set reached plain(): sort it in the pin and note it (R rule 4)")
    if isinstance(obj, Path):
        return mask(str(obj))
    if isinstance(obj, enum.Enum):
        return plain(obj.value, mask)
    raise TypeError(f"cannot write {type(obj).__name__}: convert it in the pin")


def dumps(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=True) + "\n"


def array_digest(a):
    """sha256 of an array's float64 C-order bytes, with its shape."""
    import numpy as np
    arr = np.ascontiguousarray(np.asarray(a, dtype=np.float64))
    return {"shape": list(arr.shape), "float64_sha256": hashlib.sha256(arr.tobytes()).hexdigest()}


def text_digest(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


class Out:
    """The folder of one pin's outputs."""

    def __init__(self, folder, masker):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.mask = masker
        self.notes = []

    def json(self, name, obj):
        (self.folder / name).write_text(dumps(plain(obj, self.mask)), encoding='utf-8', newline='\n')

    def text(self, name, s):
        (self.folder / name).write_text(self.mask(s), encoding='utf-8', newline='\n')

    def note(self, line):
        self.notes.append(line)

    def close(self):
        head = [f"python {sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}"]
        (self.folder / "NOTES.txt").write_text(
            "\n".join(head + self.notes) + "\n", encoding='utf-8', newline='\n')


@contextlib.contextmanager
def captured():
    """Capture stdout and stderr text written inside the block."""
    o, e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        box = {'out': o, 'err': e}
        yield box


def outcome(fn, *a, **k):
    """Call fn; return {'value': ..., 'stdout': ..., 'stderr': ...} or the
    exception's type and text."""
    with captured() as box:
        try:
            v = fn(*a, **k)
            res = {'value': v}
        except SystemExit as ex:
            res = {'system_exit': ex.code}
        except Exception as ex:          # the exception is the output
            res = {'raises': type(ex).__name__, 'message': str(ex)}
    res['stdout'] = box['out'].getvalue()
    res['stderr'] = box['err'].getvalue()
    return res


def repo_py_files(which=('root', 'bridge', 'tools')):
    """The AST pins' scope (index open point 1, the indexer's choice): root
    *.py, tampura_bridge/*.py (not its tests), tools/*.py (not subfolders),
    sorted by path.  Files found on disk, so an untracked file shows."""
    files = []
    if 'root' in which:
        files += sorted(REPO.glob('*.py'))
    if 'bridge' in which:
        files += sorted((REPO / 'tampura_bridge').glob('*.py'))
    if 'tools' in which:
        files += sorted((REPO / 'tools').glob('*.py'))
    return files


def rel(path):
    return Path(path).resolve().relative_to(REPO).as_posix()


# ---------------------------------------------------------------------------
# Child and parent
# ---------------------------------------------------------------------------

def child_env(work):
    env = dict(os.environ)
    for k in ('FORCE_COLOR', 'NO_COLOR', 'SB_CONSOLE_ASCII', 'SB_AUDIO', 'SB_VOICE',
              'PYTHONSTARTUP', 'PYTHONINSPECT', 'BOXEL_EYE_IMAGES'):
        env.pop(k, None)
    env.update({'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                'HOME': str(work), 'COLUMNS': '80', 'LINES': '24',
                'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'TERM': 'dumb',
                'MPLBACKEND': 'Agg', 'PYTHONPATH': str(REPO),
                'PYTHONIOENCODING': 'utf-8'})
    return env


def run_child(group, pin_id, out_dir):
    """Run one pin in-process (we are the child).  Exit code 0 ok, 1 error."""
    p = GROUPS[group][pin_id]
    work = Path.cwd()
    out = Path(out_dir).resolve()
    folder = out / pin_id
    if folder.exists():
        shutil.rmtree(folder)
    masker = Masker([(REPO, '<REPO>'), (work, '<WORK>'), (out, '<OUT>'),
                     (os.path.realpath(work), '<WORK>')])
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    o = Out(folder, masker)
    try:
        p.func(o)
        o.close()
        return 0
    except Exception:
        o.close()
        (folder / "ERROR.txt").write_text(masker(traceback.format_exc()),
                                          encoding='utf-8', newline='\n')
        return 1


def run_group(group, out_dir, only=None, log=print):
    out = Path(out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    logs = out / "_logs"
    logs.mkdir(exist_ok=True)
    pins = GROUPS[group]
    ids = [i for i in pins if not only or i in only]
    unknown = sorted(set(only or ()) - set(pins))
    if unknown:
        raise SystemExit(f"unknown pin(s) {unknown} in group {group}")
    manifest_path = out / "MANIFEST.json"
    manifest = (json.loads(manifest_path.read_text(encoding='utf-8'))
                if manifest_path.exists() else {})
    manifest.update({'group': group, 'python': sys.version.split()[0]})
    manifest.setdefault('pins', {})
    worst = 0
    for pid in ids:
        work = Path(tempfile.mkdtemp(prefix=f"pin_{pid}_"))
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, str(HERE), '--child', '--group', group, '--only', pid,
                 '--out', str(out)], cwd=str(work), env=child_env(work),
                capture_output=True, text=True, timeout=pins[pid].timeout)
            rc = proc.returncode
            (logs / f"{pid}.log").write_text(
                f"rc={rc}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}",
                encoding='utf-8')
            status = 'ok' if rc == 0 else 'error'
        except subprocess.TimeoutExpired:
            status, rc = 'timeout', -1
            folder = out / pid
            folder.mkdir(exist_ok=True)
            (folder / "TIMEOUT.txt").write_text(f"no output within {pins[pid].timeout} s\n")
        finally:
            shutil.rmtree(work, ignore_errors=True)
        dt = time.monotonic() - t0
        files = {}
        folder = out / pid
        if folder.is_dir():
            for f in sorted(folder.rglob('*')):
                if f.is_file():
                    files[f.relative_to(folder).as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
        manifest['pins'][pid] = {'status': status, 'about': pins[pid].about, 'files': files}
        log(f"[pins] {group}/{pid}: {status} ({dt:.1f} s)")
        if status != 'ok':
            worst = 1
    manifest_path.write_text(dumps(manifest), encoding='utf-8', newline='\n')
    return worst


def pin_files(folder):
    """The compared files of one pin folder: every file except INFO_* (line
    numbers and other information that may change without a behaviour
    change, PLAN 5.2 "line numbers informational")."""
    folder = Path(folder)
    if not folder.is_dir():
        return {}
    return {f.relative_to(folder).as_posix(): f for f in sorted(folder.rglob('*'))
            if f.is_file() and not f.name.startswith('INFO_')}


def compare(a, b, log=print):
    """Compare two output folders pin by pin.  Returns {pin: verdict}."""
    a, b = Path(a), Path(b)
    ma = json.loads((a / "MANIFEST.json").read_text(encoding='utf-8')) if (a / "MANIFEST.json").exists() else {'pins': {}}
    mb = json.loads((b / "MANIFEST.json").read_text(encoding='utf-8')) if (b / "MANIFEST.json").exists() else {'pins': {}}
    pins = sorted({d.name for d in a.iterdir() if d.is_dir() and not d.name.startswith('_')}
                  | {d.name for d in b.iterdir() if d.is_dir() and not d.name.startswith('_')})
    verdicts = {}
    for pid in pins:
        fa, fb = pin_files(a / pid), pin_files(b / pid)
        diffs = sorted(set(fa) ^ set(fb))
        diffs += sorted(k for k in set(fa) & set(fb) if fa[k].read_bytes() != fb[k].read_bytes())
        sa = ma['pins'].get(pid, {}).get('status', '?')
        sb = mb['pins'].get(pid, {}).get('status', '?')
        if diffs:
            v = f"differs: {', '.join(diffs)}"
        elif sa != 'ok' or sb != 'ok':
            v = f"not runnable (status {sa}/{sb}, equal output)"
        else:
            v = "equal"
        verdicts[pid] = v
        log(f"{pid}: {v}")
    return verdicts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--group')
    ap.add_argument('--out')
    ap.add_argument('--only', help='comma separated pin ids')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--compare', nargs=2, metavar=('A', 'B'))
    ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.compare:
        v = compare(*a.compare)
        return 0 if all(x == 'equal' for x in v.values()) else 1
    if a.list:
        for g, pins in GROUPS.items():
            if a.group and g != a.group:
                continue
            for pid, p in pins.items():
                print(f"{g}\t{pid}\t{p.about}")
        return 0
    if not a.group or not a.out:
        ap.error('--group and --out are needed (or --list, --compare)')
    if a.group not in GROUPS:
        ap.error(f"unknown group {a.group}; known: {sorted(GROUPS)}")
    only = [s for s in (a.only or '').split(',') if s]
    if a.child:
        return run_child(a.group, only[0], a.out)
    return run_group(a.group, a.out, only)


# ===========================================================================
# Group "low": the low-cost pins and the AST pins (index phase0/index/pins_low.md)
# ===========================================================================

TABLE_Z = 0.625                     # boxel_env.py:903 (0.625 + table_z_offset 0)
BF45 = 'archive/tampura_bridge_plan_2026-10-25/bf/BF45_46/s10_headless_2026-10-30_14-02-25'
BF45_RUN = BF45 + '/ours/run_2026-10-30_14-03-01'
BF2_LEDGER = 'archive/tampura_bridge_plan_2026-10-25/bf/BF2_b0/smoke_random-pairs_holding_seed0_ledger.jsonl'


def _boxel_row(b):
    return [b.id, b.boxel_type.value, b.min_corner.tolist(), b.max_corner.tolist()]


def _load_tool(name):
    """Import tools/<name>.py by path (tools/ is not a package)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(REPO / 'tools' / f'{name}.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ----- pin 4: free space ---------------------------------------------------

@pin('low', 'p04_free_space', 'R4: octree, merge, uniform grid, split and reboxelize on fixed obstacles')
def p04_free_space(out):
    import types
    import numpy as np
    import boxel_env
    from boxel_data import BoxelData, BoxelType, BoxelRegistry
    from free_space import FreeSpaceGenerator, split_free_boxel
    from cell_merger import merge_free_space_cells
    from uniform_grid import UniformGridGenerator
    from reboxelize import reboxelize_free_space
    Env = boxel_env.BoxelTestEnv
    XR, YR = Env._SAFE_TABLE_X_RANGE, Env._SAFE_TABLE_Y_RANGE
    z = TABLE_Z
    O, S = BoxelType.OBJECT, BoxelType.SHADOW

    def ob(c, e, t=O, name=None):
        return BoxelData.from_center_extent(c, e, t, object_name=name)

    def box(mn, mx, t=O, name=None):
        return BoxelData(boxel_type=t, min_corner=np.array(mn, dtype=float),
                         max_corner=np.array(mx, dtype=float), object_name=name)

    def cases():
        return {
            'none': [],
            'one_centre_cube': [ob((0.3, 0.0, z + 0.03), (0.03, 0.03, 0.03), name='a')],
            'two_overlapping': [ob((0.3, 0.0, z + 0.03), (0.03, 0.03, 0.03), name='a'),
                                ob((0.33, 0.02, z + 0.05), (0.03, 0.03, 0.05), name='b')],
            'object_and_shadow': [ob((0.4, 0.1, z + 0.075), (0.02, 0.04, 0.075), name='occ'),
                                  ob((0.4, 0.2, z + 0.075), (0.02, 0.06, 0.075), t=S)],
            'touching_node_face': [box((0.3, 0.0, z), (0.36, 0.06, z + 0.06), name='a')],
            'above_table': [ob((0.2, -0.2, z + 0.3), (0.03, 0.03, 0.03), name='a')],
            'outside_workspace': [ob((0.9, 0.6, z + 0.03), (0.03, 0.03, 0.03), name='a')],
        }
    out.note('table z 0.625 (boxel_env.py:903); generator ranges = BoxelTestEnv._SAFE_TABLE_X/Y_RANGE '
             '(boxel_env.py:632-648, 1059-1060); octree min_resolution default 0.035')
    out.note('rows are [id, type, min_corner, max_corner] in produced order (ids are empty until a registry adds them)')
    gen = FreeSpaceGenerator(z, table_x_range=XR, table_y_range=YR)
    octree = {}
    for name, obs in cases().items():
        r = outcome(gen.generate, obs, visualize=False)
        cells = r.pop('value', None)
        rows = [_boxel_row(b) for b in cells] if cells is not None else None
        octree[name] = {'n': len(rows) if rows is not None else None, 'rows': rows, **r}
        cells2 = gen.generate(cases()[name], visualize=False)
        m = outcome(merge_free_space_cells, cells2)
        merged = m.pop('value', None)
        out.json(f'octree_{name}.json', octree[name])
        out.json(f'merged_{name}.json', {'n': len(merged) if merged is not None else None,
                                         'rows': [_boxel_row(b) for b in merged] if merged is not None else None,
                                         **m})
    # The generator with its own default ranges (table 0..1 x -0.5..0.5).
    d = FreeSpaceGenerator(z).generate(cases()['two_overlapping'], visualize=False)
    out.json('octree_default_ranges_two_overlapping.json', [_boxel_row(b) for b in d])
    uni = {}
    for cs in (0.05, 0.17):
        ug = UniformGridGenerator(z, cell_size=cs, table_x_range=XR, table_y_range=YR)
        ug_def = UniformGridGenerator(z, cell_size=cs)
        for name in ('none', 'two_overlapping', 'touching_node_face'):
            for label, g in (('env_ranges', ug), ('default_ranges', ug_def)):
                rows = [_boxel_row(b) for b in g.generate(cases()[name])]
                uni[f'{cs}_{label}_{name}'] = {'n': len(rows), 'rows_sha256': text_digest(dumps(rows)),
                                               'first': rows[:3], 'last': rows[-3:]}
    out.json('uniform_grid.json', uni)
    out.note('uniform_grid.json: per case the count, the sha256 of the rows as this file writes JSON, '
             'and the first and last three rows (the full lists are thousands of cells)')
    free = box((0.0, 0.0, z), (0.2, 0.2, z + 0.2), t=BoxelType.FREE_SPACE)
    splits = {}
    for name, o in (('inside', box((0.05, 0.05, z), (0.1, 0.1, z + 0.05))),
                    ('partly_outside', box((0.15, -0.05, z), (0.3, 0.1, z + 0.05))),
                    ('covers_all', box((-0.1, -0.1, z - 0.1), (0.3, 0.3, z + 0.3))),
                    ('touching_face', box((0.2, 0.05, z), (0.25, 0.1, z + 0.05))),
                    ('thin_sliver_left', box((0.003, 0.05, z), (0.1, 0.1, z + 0.05)))):
        r = outcome(split_free_boxel, free, o)
        v = r.pop('value', None)
        splits[name] = {'rows': [_boxel_row(b) for b in v] if v is not None else None, **r}
    out.json('split_free_boxel.json', splits)

    def stub_env(uniform, cell=0.17):
        env = types.SimpleNamespace(
            use_uniform_grid=uniform, table_surface_height=z,
            _SAFE_TABLE_X_RANGE=XR, _SAFE_TABLE_Y_RANGE=YR,
            free_space_generator=FreeSpaceGenerator(z, table_x_range=XR, table_y_range=YR),
            uniform_grid_generator=UniformGridGenerator(z, cell_size=cell, table_x_range=XR,
                                                        table_y_range=YR))
        env.generate_free_space = types.MethodType(Env.generate_free_space, env)
        env.annotate_free_space_surface = types.MethodType(Env.annotate_free_space_surface, env)
        return env
    out.note('reboxelize: a stub env whose generate_free_space and annotate_free_space_surface are '
             "BoxelTestEnv's own methods bound to a namespace (no client); viz None")
    out.note('reboxelize: old_removed is a set (reboxelize.py:73): written sorted')
    for uniform in (False, True):
        reg = BoxelRegistry()
        a = ob((0.3, 0.0, z + 0.03), (0.03, 0.03, 0.03), name='a')
        reg.add_boxel(a)
        sh = ob((0.3, 0.1, z + 0.03), (0.03, 0.05, 0.03), t=S)
        reg.add_boxel(sh)
        env = stub_env(uniform)
        centres = {}
        steps = []

        def snap(label):
            r = outcome(reboxelize_free_space, reg, env, centres, None, False)
            new_ids, removed = r.pop('value')
            steps.append({
                'step': label, 'new_ids': new_ids, 'old_removed_sorted': sorted(removed), **r,
                'dirty': reg.dirty,
                'free': [_boxel_row(b) + [b.on_surface, b.surface_z] for b in reg.get_free_space_boxels()],
                'boxel_centers': {k: v.tolist() for k, v in centres.items()},
            })
        snap('initial')
        a.min_corner, a.max_corner = a.min_corner + [0.2, 0.0, 0.0], a.max_corner + [0.2, 0.0, 0.0]
        reg.update_after_place('free_missing', a.id, a.min_corner, a.max_corner, z)
        steps.append({'step': 'moved a', 'dirty_after_update_after_place': reg.dirty})
        snap('after move')
        reg.remove_boxel(sh.id)
        snap('after shadow removed')
        snap('unchanged')
        out.json(f"reboxelize_{'uniform' if uniform else 'octree'}.json", steps)


# ----- pin 5: registry -----------------------------------------------------

@pin('low', 'p05_registry', 'R5: BoxelRegistry ids, refusal, update_after_place, to_dict, ledger rows')
def p05_registry(out):
    import numpy as np
    import boxel_data
    from boxel_data import BoxelData, BoxelType, BoxelRegistry
    calls = []
    boxel_data.ledger_belief = lambda region, op, status=None: calls.append([region, op, status])
    out.note('boxel_data.ledger_belief replaced by a recorder (test-level stub, the name imported at '
             'boxel_data.py:18); recorded calls in calls')
    F, O, S = BoxelType.FREE_SPACE, BoxelType.OBJECT, BoxelType.SHADOW
    reg = BoxelRegistry()
    log = []

    def step(label, fn, *a, **k):
        r = outcome(fn, *a, **k)
        r['dirty'] = reg.dirty
        r['calls_so_far'] = list(calls)
        log.append({'step': label, **r})
        return r.get('value')

    def bx(t, c, e, **k):
        return BoxelData.from_center_extent(c, e, t, **k)
    z = TABLE_Z
    step('add free', reg.add_boxel, bx(F, (0.1, 0.1, z + 0.05), (0.05, 0.05, 0.05)))
    step('add free', reg.add_boxel, bx(F, (0.2, 0.1, z + 0.05), (0.05, 0.05, 0.05)))
    step('add object a', reg.add_boxel, bx(O, (0.3, 0.0, z + 0.03), (0.03,) * 3, object_name='a'))
    step('add shadow', reg.add_boxel, bx(S, (0.3, 0.1, z + 0.03), (0.03, 0.05, 0.03), created_by_object='a'))
    step('add free', reg.add_boxel, bx(F, (0.1, 0.2, z + 0.05), (0.05, 0.05, 0.05)))
    step('add object b', reg.add_boxel, bx(O, (0.5, 0.0, z + 0.03), (0.03,) * 3, object_name='b'))
    step('add shadow', reg.add_boxel, bx(S, (0.5, 0.1, z + 0.03), (0.03, 0.05, 0.03)))
    step('add second object named a, other id (refused)', reg.add_boxel,
         bx(O, (0.6, 0.0, z + 0.03), (0.03,) * 3, object_name='a'))
    dup = reg.get_boxel('obj_002')
    step('add obj_002 again (same id)', reg.add_boxel, dup)
    step('add explicit id', reg.add_boxel, bx(F, (0.7, 0.0, z + 0.05), (0.05,) * 3, id='my_free'))
    step('generate_id plain', reg.generate_id)
    step('adjacent free to [0.15..0.25]^2', lambda: [b.id for b in reg.get_adjacent_free_boxels(
        np.array([0.15, 0.05, z]), np.array([0.25, 0.15, z + 0.1]))])
    step('adjacent excluding free_000', lambda: [b.id for b in reg.get_adjacent_free_boxels(
        np.array([0.15, 0.05, z]), np.array([0.25, 0.15, z + 0.1]), exclude_ids={'free_000'})])
    step('update_after_place on table', reg.update_after_place, 'free_001', 'obj_002',
         [0.18, 0.08, z + 0.01], [0.24, 0.14, z + 0.07], z)
    step('mark_clean', reg.mark_clean)
    step('update_after_place above table', reg.update_after_place, 'free_missing', 'obj_005',
         [0.48, -0.03, z + 0.0101], [0.54, 0.03, z + 0.07], z)
    step('remove shadow', reg.remove_boxel, 'shadow_003')
    step('remove free', reg.remove_boxel, 'free_000')
    step('remove unknown', reg.remove_boxel, 'nope')
    for e in log:
        if isinstance(e.get('value'), BoxelData):
            e['value'] = e['value'].to_dict()
    out.json('steps.json', log)
    out.json('to_dict.json', reg.to_dict())
    r = outcome(reg.save_to_json, 'reg.json')
    loaded = BoxelRegistry.load_from_json('reg.json')
    out.json('save_load.json', {'save': r, 'file_text_sha256': text_digest(Path('reg.json').read_text()),
                                'loaded_to_dict': loaded.to_dict(), 'loaded_next_id': loaded._next_id})
    out.json('calls.json', calls)


# ----- pin 8: domain text --------------------------------------------------

@pin('low', 'p08_domain', 'R8: m8_domain.generate, file shas, anchors, G10 helpers')
def p08_domain(out):
    import m8_domain as m
    live = m.read(m.LIVE_FILE)
    gen_file = m.read(m.GENERATED_FILE)
    stream = m.read(m.STREAM_LIVE_FILE)
    generated = m.generate(live)
    res = {
        'generated_equals_file': generated == gen_file,
        'sha_generate_live': m.sha(generated),
        'sha_read': {'domain_pddlstream.pddl': m.sha(live), 'domain_pddlstream_m8.pddl': m.sha(gen_file),
                     'stream.pddl': m.sha(stream)},
        'raw_bytes': {},
        'domain_file_off': rel(m.domain_file(False)),
        'domain_file_on': rel(m.domain_file(True)),
        'stream_live_file': rel(m.STREAM_LIVE_FILE),
    }
    for name in ('domain_pddlstream.pddl', 'domain_pddlstream_m8.pddl', 'stream.pddl'):
        raw = (REPO / 'pddl' / name).read_bytes()
        res['raw_bytes'][name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'has_crlf': b'\r\n' in raw,
                                  'sha256_crlf_to_lf': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}
    out.json('shas.json', res)
    out.note('raw_bytes depend on the checkout eol state (has_crlf says which); sha_read is what the planner '
             'and G10 hash (m8_domain.read, universal newlines)')
    out.text('generated.pddl', generated)
    neg = []
    for i, (anchor, _) in enumerate(m.EDITS):
        neg.append({'case': f'anchor {i} removed', **outcome(m.generate, live.replace(anchor, '', 1))})
        neg.append({'case': f'anchor {i} twice', **outcome(m.generate, live + anchor)})
    neg.append({'case': 'not ending with )', **outcome(m.generate, live.rstrip() + '\nx\n')})
    neg.append({'case': 'trailing blank lines', 'sha': m.sha(m.generate(live + '\n\n\n'))})
    out.json('negative.json', neg)
    bg = _load_tool('bridge_gates')
    report = bg.Report()
    r = outcome(bg.run_domain, report)
    out.json('g10.json', {'pddl_sha': {n: bg._pddl_sha(n) for n in
                                       ('domain_pddlstream.pddl', 'domain_pddlstream_m8.pddl', 'stream.pddl')},
                          'run_domain_rows': report.rows, **r})


# ----- pin 11: sense ray slices --------------------------------------------

@pin('low', 'p11_sense_slices', 'R11: perception.sense_ray_slices on 20 AABBs')
def p11_sense_slices(out):
    from perception import sense_ray_slices
    z = TABLE_Z
    boxes = [
        ('standard', (0.3, -0.05, z), (0.4, 0.05, z + 0.1)),
        ('tall_0.15', (0.3, -0.05, z), (0.4, 0.05, z + 0.15)),
        ('thin_4mm_elevated', (0.3, -0.05, z + 0.1), (0.4, 0.05, z + 0.104)),
        ('wide_0.9', (-0.2, -0.45, z), (0.7, 0.45, z + 0.1)),
        ('wide_x_0.76_capped', (0.0, 0.0, z), (0.76, 0.1, z + 0.1)),
        ('wide_x_0.755_not_capped', (0.0, 0.0, z), (0.755, 0.1, z + 0.1)),
        ('elevated_0.3', (0.3, -0.05, z + 0.3), (0.4, 0.05, z + 0.35)),
        ('zero_height', (0.3, -0.05, z), (0.4, 0.05, z)),
        ('zero_width_x', (0.3, -0.05, z), (0.3, 0.05, z + 0.1)),
        ('min_above_max', (0.4, 0.05, z + 0.1), (0.3, -0.05, z)),
        ('height_0.04', (0.3, -0.05, z), (0.4, 0.05, z + 0.04)),
        ('height_0.006', (0.3, -0.05, z), (0.4, 0.05, z + 0.006)),
        ('height_0.012', (0.3, -0.05, z), (0.4, 0.05, z + 0.012)),
        ('tiny_xy_5mm', (0.3, 0.0, z), (0.305, 0.005, z + 0.05)),
        ('point', (0.3, 0.0, z), (0.3, 0.0, z)),
        ('negative_coords', (-0.4, -0.4, z), (-0.3, -0.25, z + 0.07)),
        ('width_0.12_exact_multiple', (0.1, 0.1, z), (0.22, 0.22, z + 0.1)),
        ('width_0.1201', (0.1, 0.1, z), (0.2201, 0.2201, z + 0.1)),
        ('tall_0.5', (0.0, -0.1, z), (0.2, 0.1, z + 0.5)),
        ('height_0.03', (0.3, -0.05, z), (0.4, 0.05, z + 0.03)),
    ]
    full = {'standard', 'tiny_xy_5mm'}
    res = []
    for name, mn, mx in boxes:
        r = outcome(sense_ray_slices, mn, mx)
        v = r.pop('value', None)
        row = {'case': name, 'min': list(mn), 'max': list(mx), **r}
        if v is not None:
            slices, capped = v
            row['capped'] = capped
            row['slices'] = [{'z': s.z, 'spacing_x': s.spacing_x, 'spacing_y': s.spacing_y,
                              'pad_z_down': s.pad_z_down, 'pad_z_up': s.pad_z_up, 'dense': s.dense,
                              'n_points': int(len(s.points)), 'points': array_digest(s.points),
                              **({'points_full': s.points} if name in full else {})}
                             for s in slices]
        res.append(row)
    out.json('slices.json', res)
    out.note('points: sha256 of the float64 bytes and the shape; points_full only for standard and tiny_xy_5mm')


# ----- pin 12: render interceptors -----------------------------------------

@pin('low', 'p12_interceptors', 'R12: project_points_to_pixels and first_surface_interceptors on a synthetic render')
def p12_interceptors(out):
    import numpy as np
    import pybullet as pb
    import robot_utils
    from perception import project_points_to_pixels, first_surface_interceptors
    eye, target, up = [0.1, -0.8, 0.7], [0.1, 0.0, 0.5], [0, 0, 1]
    view = pb.computeViewMatrix(cameraEyePosition=eye, cameraTargetPosition=target, cameraUpVector=up)
    proj = pb.computeProjectionMatrixFOV(fov=60.0, aspect=640 / 480, nearVal=0.01, farVal=5.0)
    pose = np.eye(4)
    pose[:3, 0], pose[:3, 1], pose[:3, 2] = [-1, 0, 0], [0, 1, 0], [0, 0, -1]
    pose[:3, 3] = [0.4, 0.0, 1.0]
    wview, wproj = robot_utils.wrist_camera_matrices(pose)
    out.note('matrices from pybullet computeViewMatrix / computeProjectionMatrixFOV (no client), as '
             'boxel_env.py:1780-1790 builds the eye (defaults 513-517, 464-468) and '
             'robot_utils.wrist_camera_matrices builds the wrist camera for a fixed straight-down pose; '
             'the 16 numbers of each are written in matrices.json, so a pybullet change shows there')
    out.json('matrices.json', {'eye_view': list(view), 'eye_proj': list(proj),
                               'wrist_pose': pose, 'wrist_view': list(wview), 'wrist_proj': list(wproj)})
    H, W = 480, 640
    depth = np.full((H, W), 0.9)
    seg = np.full((H, W), 1, dtype=int)
    depth[200:280, 250:350], seg[200:280, 250:350] = 0.7, 3
    depth[220:260, 400:450], seg[220:260, 400:450] = 0.6, 4
    depth[0:40, :], seg[0:40, :] = 4.0, -1

    def points_for(cam_eye, cam_target, cam_up):
        e, t = np.asarray(cam_eye, float), np.asarray(cam_target, float)
        f = (t - e) / np.linalg.norm(t - e)
        r = np.cross(f, np.asarray(cam_up, float))
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        pts = []
        for d in (0.5, 0.6, 0.6029, 0.603, 0.6031, 0.65, 0.7, 0.703, 0.72, 0.9, 0.95):
            for dx in (-0.2, -0.05, 0.0, 0.1, 0.17):
                for dy in (-0.1, 0.0, 0.05):
                    pts.append(e + d * (f + dx * r + dy * u))
        pts.append(e + 1.0 * (f + 5.0 * r))       # outside the frame
        pts.append(e - 0.5 * f)                   # behind the camera
        return np.array(pts)
    res = {}
    for label, v, p_, cam in (('eye', view, proj, (eye, target, up)),
                              ('wrist', wview, wproj, ([0.4, 0.0, 1.0], [0.4, 0.0, 0.0], [0, -1, 0]))):
        pts = points_for(*cam)
        rows, cols, dm, iv = project_points_to_pixels(pts, v, p_, W, H)
        case = {'points': pts, 'rows': rows, 'cols': cols, 'depth_m': dm, 'in_view': iv}
        for tol in (None, 0.0, 0.01):
            kw = {} if tol is None else {'depth_tol': tol}
            ic, hid, iv2 = first_surface_interceptors(pts, depth, seg, v, p_, **kw)
            case[f'interceptors_tol_{"default" if tol is None else tol}'] = {
                'intercepted': ic, 'hit_ids': hid, 'in_view': iv2,
                'n_intercepted': int(ic.sum()), 'n_in_view': int(iv2.sum())}
        res[label] = case
    out.json('interceptors.json', res)
    out.note('synthetic render 480x640: background depth 0.9 id 1, block id 3 at rows 200-280 cols 250-350 '
             'depth 0.7, block id 4 rows 220-260 cols 400-450 depth 0.6, top 40 rows depth 4.0 id -1')


# ----- pin 17: pose belief -------------------------------------------------

@pin('low', 'p17_pose_belief', 'R17: pose_belief pure functions and scripted record_detection sequences')
def p17_pose_belief(out):
    import math
    import numpy as np
    import pose_belief as pb
    import slip_fixes
    from boxel_data import BoxelData, BoxelType
    from perception import ObjectDetection
    AABB, TOP = 0.0696, 0.051
    C0 = np.array([0.50, 0.10])
    WY = math.radians(5.0)

    def det(centre, yaw=0.0, top=TOP, aabb=AABB, valid=True, extents=True):
        c = np.asarray(centre, dtype=float)
        h = aabb / 2.0
        return ObjectDetection(
            name='cup', body_id=1, pixel_count=900,
            est_min=np.array([c[0] - h, c[1] - h, 0.0]), est_max=np.array([c[0] + h, c[1] + h, 0.07]),
            yaw=yaw, yaw_valid=valid, rect_center=c.copy(),
            body_extents=np.array([top, top * 0.8, 0.07]) if extents else None,
            pixel_steps=np.array([[0.0005, 0.0], [0.0, 0.0005]]),
            raw_xy_ext=np.array([aabb * 0.9, aabb]))

    def cup():
        h = AABB / 2.0
        return BoxelData(id='cup', boxel_type=BoxelType.OBJECT,
                         min_corner=np.array([C0[0] - h, C0[1] - h, 0.0]),
                         max_corner=np.array([C0[0] + h, C0[1] + h, 0.07]))

    def state(b):
        ref = getattr(b, '_prk_ref', None)
        return {'pose_radius': b.pose_radius, 'yaw': b.yaw, 'yaw_valid': b.yaw_valid,
                'body_extents': b.body_extents, 'rect_center': b.rect_center,
                'complete_detections': b.complete_detections,
                'min_corner': b.min_corner, 'max_corner': b.max_corner,
                '_prk_ref': (None if ref is None else {k: ref[k] for k in sorted(ref)}),
                '_prk_yaw_cam': getattr(b, '_prk_yaw_cam', None)}
    out.note('_prk_ref keys written sorted (a dict built in _prk_apply); values as they are')
    out.note('pose_radius is NOT stubbed (unlike tests/test_slip_pose_radius_keep.py)')
    pure = {}
    dets = {'square_valid': det(C0), 'yawed_30': det(C0, math.radians(30.0)),
            'invalid_yaw': det(C0, valid=False), 'no_extents': det(C0, extents=False),
            'big_aabb': det(C0, aabb=0.1)}
    for name, d in dets.items():
        for cam in ('eye', 'wrist'):
            for fp in (False, True):
                pure[f'pose_radius {name} {cam} first_partial={fp}'] = pb.pose_radius(
                    d, pb.YAW_NOISE[cam], first_partial=fp)
        pure[f'pose_radius {name} with body_extents and rigid_ext'] = pb.pose_radius(
            d, pb.YAW_NOISE['eye'], np.array([0.05, 0.04, 0.07]), np.array([0.05, 0.05, 0.07]))
    for ext in ((0.05, 0.05), (0.05, 0.053), (0.03, 0.06), (0.08, 0.02), (0.09, 0.09), (0.0696, 0.0696)):
        pure[f'commit_margin {ext}'] = pb.commit_margin(ext, 0.04, 0.076, 0.005)
    for yaw in (0.0, 0.3, -1.2, 2.0, math.pi):
        for ext in ((0.05, 0.05, 0.07), (0.03, 0.06, 0.07)):
            pure[f'fitted_grasp_candidates yaw={yaw} ext={ext}'] = pb.fitted_grasp_candidates(yaw, ext, 0.005)
            pure[f'fitted_grasp_candidates yaw={yaw} ext={ext} aabb'] = pb.fitted_grasp_candidates(
                yaw, ext, 0.005, aabb_ext=np.array([0.07, 0.07, 0.07]))
    for gy in (0.0, 0.5, -1.0, 2.5, 3.0):
        for txy in ((0.5, 0.1), (0.3, -0.3), (0.6, 0.4)):
            pure[f'wrist_joint7_top_down t={txy} yaw={gy}'] = pb.wrist_joint7_top_down(txy, (0.0, 0.0), gy)
            pure[f'wrist_home_twin t={txy} yaw={gy}'] = pb.wrist_home_twin(gy, txy, (0.0, 0.0), 0.785)
    out.json('pure.json', pure)
    saved_sw, saved_en = dict(pb.SWITCHES), slip_fixes.ENABLED
    configs = [('M8_M9_keep_off', {'M8': True, 'M9': True}, 'none'),
               ('M8_M9_keep_on', {'M8': True, 'M9': True}, 'pose_radius_keep'),
               ('M8_only_keep_on', {'M8': True, 'M9': False}, 'pose_radius_keep'),
               ('all_off', {}, 'pose_radius_keep')]
    seqs = {}
    for cname, sw, keep in configs:
        pb.SWITCHES.clear()
        pb.SWITCHES.update(saved_sw)
        pb.SWITCHES.update(sw)
        slip_fixes.configure(keep)
        for sname, offset in (('cup_loop_1.66mm', (1.66, 0.0)), ('moved_body_100mm', (100.0, 0.0))):
            b = cup()
            log = []

            def write(label, d, cam, first=False, complete=True):
                r = outcome(pb.record_detection, b, d, cam, complete, first=first)
                b.min_corner, b.max_corner = d.est_min.copy(), d.est_max.copy()
                log.append({'call': label, 'stdout': r['stdout'], **({'raises': r['raises']} if 'raises' in r else {}),
                            'state': state(b),
                            'pose_known': pb.pose_known(b, 0.04, 0.076, 0.005),
                            'believed_margin': pb.believed_margin(b, 0.04, 0.076, 0.005),
                            'uses_fitted_pose': pb.uses_fitted_pose(b)})
            write('eye first', det(C0), 'eye', first=True)
            cw = C0 + np.array([0.0002, 0.0])
            write('wrist complete', det(cw, WY), 'wrist')
            write('eye refresh', det(cw + np.asarray(offset) * 1e-3, 0.0), 'eye')
            write('eye refresh 2', det(cw + np.array([0.00166, 0.0003]), 0.0), 'eye')
            write('eye partial', det(cw + np.array([0.002, 0.0])), 'eye', complete=False)
            write('eye yaw 35 deg', det(cw + np.array([0.00166, 0.0]), math.radians(35.0)), 'eye')
            write('eye larger rectangle', det(cw, 0.0, top=0.07), 'eye')
            r = outcome(pb.mark_pose_commanded, b)
            log.append({'call': 'mark_pose_commanded', 'state': state(b)})
            write('eye after commanded', det(cw + np.array([0.00166, 0.0]), 0.0), 'eye')
            pb.mark_pose_unknown(b)
            log.append({'call': 'mark_pose_unknown', 'state': state(b)})
            write('eye after unknown', det(cw + np.array([0.00166, 0.0]), 0.0), 'eye')
            write('partial first on a fresh box', det(C0), 'eye', first=True, complete=False)
            seqs[f'{cname} {sname}'] = log
    pb.SWITCHES.clear()
    pb.SWITCHES.update(saved_sw)
    slip_fixes.ENABLED = saved_en
    out.json('sequences.json', seqs)
    out.json('constants.json', {'YAW_NOISE': pb.YAW_NOISE, 'PLACE_POSE_TOL': pb.PLACE_POSE_TOL,
                                'SWITCHES_default': saved_sw, '_PRK_BOX_TOL': pb._PRK_BOX_TOL,
                                'WRIST_HOME_TIE_BAND': pb.WRIST_HOME_TIE_BAND})


# ----- pin 18: belief ------------------------------------------------------

@pin('low', 'p18_belief', 'R18: belief.BeliefState scripted sequence with ledger rows recorded')
def p18_belief(out):
    import belief as bmod
    calls = []
    bmod.ledger_belief = lambda region, op, status=None: calls.append([region, op, status])
    out.note('belief.ledger_belief replaced by a recorder (the name imported at belief.py:14)')
    out.note('redetected is a set: written sorted; shadow_status written as [key, value] pairs in insertion order')
    b = bmod.BeliefState(['s1', 's2', 's3'], 'dice')
    log = []

    def step(label, fn=None, *a):
        r = outcome(fn, *a) if fn else {}
        log.append({'step': label, **{k: v for k, v in r.items() if k != 'value'},
                    'shadow_status': [[k, v] for k, v in b.shadow_status.items()],
                    'target_found_in': b.target_found_in, 'occluders_moved': b.occluders_moved,
                    'redetected_sorted': sorted(b.redetected),
                    'unknown': b.get_unknown_shadows(), 'known_empty': b.get_known_empty_shadows(),
                    'parked': b.get_parked_shadows(), 'is_target_found': b.is_target_found(),
                    'calls_so_far': list(calls)})
    step('construct')
    step('add new s4', b.add_shadow, 's4')
    step('add existing s2', b.add_shadow, 's2')
    step('sensed s1 not found', b.mark_sensed, 's1', False)
    step('unresolved s3', b.mark_unresolved, 's3')
    step('sensed s2 found', b.mark_sensed, 's2', True)
    step('unresolved s2 (found: no-op)', b.mark_unresolved, 's2')
    step('remove s4', b.remove_shadow, 's4')
    step('remove absent', b.remove_shadow, 'nope')
    step('re-add s4', b.add_shadow, 's4')
    step('re-add s1 (has status)', b.add_shadow, 's1')
    step('occluder moved', b.mark_occluder_moved, 'obj_003', 'free_007')
    b.redetected.update({'zeta', 'alpha', 'mid'})
    step('redetected filled')
    step('sensed unknown id', b.mark_sensed, 'new_x', False)
    out.json('steps.json', log)
    out.json('calls.json', calls)


# ----- pin 19: slip_fixes --------------------------------------------------

@pin('low', 'p19_slip_fixes', 'R19: slip_fixes parse, resolve, configure, register in a process that imports only it')
def p19_slip_fixes(out):
    import slip_fixes as sf
    out.note('the child process imports slip_fixes alone (KNOWN empty at start, as the module itself '
             'knows the four defaults); configure results written sorted (a frozenset)')
    res = {'KNOWN_at_import': list(sf.KNOWN), 'DEFAULT_ON_sorted': sorted(sf.DEFAULT_ON),
           'ENABLED_at_import_sorted': sorted(sf.ENABLED), 'NONE': sf.NONE, 'DEFAULT': sf.DEFAULT}
    specs = [None, '', ' ', 'none', 'default', 'default,a', 'a', 'b_fix, a_fix', 'a+b', 'b,a,b',
             'default,a,default', ' , ,a', 'none,a', 'A', 'none,default', 'force_hold',
             'solver_iters+force_hold', 'pose_radius_keep,none', ',,,']
    res['parse'] = [[s, sf.parse(s)] for s in specs]
    res['resolve'] = [[s, sf.resolve(s)] for s in specs]
    cfg = []
    for s in specs:
        r = outcome(sf.configure, s)
        if 'value' in r:
            r['value'] = sorted(r['value'])
        r['spec_after'] = sf.spec()
        r['on_force_hold'] = sf.on('force_hold')
        cfg.append([s, r])
    res['configure_before_register'] = cfg
    regs = []
    for name, desc in (('a', 'fix a'), ('b_fix', 'fix b'), ('a_fix', 'fix a2'), ('a', 'fix a'),
                       ('a', 'other line'), ('A_fix', 'x'), ('a,b', 'x'), ('a+b', 'x'), ('none', 'x'),
                       ('default', 'x'), ('', 'x'), (' a', 'x')):
        regs.append([name, desc, outcome(sf.register, name, desc)])
    res['register'] = regs
    res['KNOWN_after_register'] = list(sf.KNOWN)
    cfg2 = []
    for s in ('a', 'b_fix, a_fix', 'default,a', 'a+zzz', 'none'):
        r = outcome(sf.configure, s)
        if 'value' in r:
            r['value'] = sorted(r['value'])
        r['spec_after'] = sf.spec()
        cfg2.append([s, r])
    res['configure_after_register'] = cfg2
    out.json('slip_fixes.json', res)


# ----- pin 20: world_eye ---------------------------------------------------

def _read_jsonl(path):
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _pddl_init_facts(text):
    """The atoms of a PDDL problem's :init, as tuples of strings."""
    import re
    text = re.sub(r';[^\n]*', '', text)
    toks = re.findall(r'\(|\)|[^\s()]+', text)
    i = toks.index(':init')
    facts, depth, cur = [], 1, None
    for t in toks[i + 1:]:
        if t == '(':
            depth += 1
            if depth == 2:
                cur = []
        elif t == ')':
            depth -= 1
            if depth == 1 and cur is not None:
                facts.append(tuple(cur))
                cur = None
            if depth == 0:
                break
        elif cur is not None and depth == 2:
            cur.append(t)
    return facts


@pin('low', 'p20_world_eye', 'R20: render_snapshot of a stored eye.jsonl, WorldEye._symbolic and _view')
def p20_world_eye(out):
    import numpy as np
    import world_eye
    recs = _read_jsonl(REPO / BF45_RUN / 'eye.jsonl')
    out.note(f'records: {BF45_RUN}/eye.jsonl ({len(recs)} records, tracked in git)')
    for label, kw in (('default', {}), ('no_view', {'view': False}), ('no_facts', {'facts': False}),
                      ('free', {'free': True})):
        out.text(f'render_{label}.txt', ''.join(world_eye.render_snapshot(r, **kw) + '\n' for r in recs))
    facts = _pddl_init_facts((REPO / BF45_RUN / 'problem_initial.pddl').read_text(encoding='utf-8'))
    hand = [('obj_at_boxel', 'dice', 'shadow_003'), ('obj_at_boxel_KIF', 'dice', 'free_004'),
            ('obj_at_boxel_KIF', 'dice', 'obj_002'), ('blocks_view_at', 'a', 'free_1', 'q'),
            ('blocks_view_at', 'a', 'shadow_2', 'q', 'x'), ('blocks_view_at', 'a', 'shadow_2', 'q'),
            ('handempty',), ('Boxel', 'free_004'), (), ('look_config', 'q1', 'dice')]
    out.json('symbolic.json', {'problem_initial_facts': len(facts),
                               'problem_initial': world_eye.WorldEye._symbolic(facts),
                               'hand': world_eye.WorldEye._symbolic(hand),
                               'empty': world_eye.WorldEye._symbolic([])})
    out.note('_symbolic: facts parsed from problem_initial.pddl :init with a small s-expression reader in this '
             'file (comments dropped), plus a hand list; counts in input order, facts sorted by the function itself')
    names = {0: 'plane', 1: 'table', 2: 'robot', 3: 'dice', 4: 'cup_1', 5: 'cup_2', 6: 'die_b', 7: 'box'}
    eye = world_eye.WorldEye(Path('eye_run'), env=None, robot_id=2, body_names=names)
    seg = np.zeros((480, 640), dtype=int)
    seg[240:, :] = 1
    seg[100:300, 0:120] = 2
    seg[300:340, 200:260] = 3
    seg[260:330, 300:380] = 4
    seg[262:266, 400:404] = 5
    seg[200:400, 500:560] = 6
    seg[350:352, 600:640] = 7
    seg[0:20, 0:640] = -1
    view = eye._view(seg)
    small = world_eye.WorldEye(Path('eye_run_small'), env=None, robot_id=2, body_names=names,
                               ascii_cols=700, ascii_rows=10)
    eye.close()
    small.close()
    out.json('view.json', {'letters': {str(k): v for k, v in sorted(eye._letters.items())},
                           'view': view, 'view_too_small': small._view(seg), 'view_none': eye._view(None),
                           'eye_log_header': Path('eye_run/eye.log').read_text(encoding='utf-8')})
    out.json('helpers.json', {'_r': world_eye._r([1.23456789, -0.000049, 2]),
                              '_r_2': world_eye._r(np.array([[1.005, 2.675]]), 2),
                              '_fmt3': world_eye._fmt3([0.1234, -0.0005, 12.3456])})


# ----- pin 22: CLI table ---------------------------------------------------

_BRIDGE_SWITCHES = {'m8': 'on', 'm9': 'on', 'm10': 'on', 'pick_aperture_from_pose': 'on',
                    'sense_over_region': 'on', 'grip_squeeze_mm': '0.5', 'world_counts': 'auto',
                    'corridor_test': 'cell+object', 'search_effort_weight': '1',
                    'search_initial_complexity': '3',
                    'slip_fixes': 'force_hold,grasp_wrist_home,pose_radius_keep,solver_iters',
                    'save_screenshots': 'off'}


def _cli_corpus():
    """(name, argv, sys.argv[1:] or None for the same list)."""
    policy = (['--no-gui', '--goal', 'holding', '--log-level', 'smart', '--max-plan-time', str(900.0)]
              + [x for k, v in sorted(_BRIDGE_SWITCHES.items()) for x in (f"--{k.replace('_', '-')}", v)])
    rp = ['--no-gui', '--scene', 'random-pairs', '--seed', '3', '--goal', 'holding', '--n-occluders', '2']
    off = ['--m8', 'off', '--m9', 'off', '--m10', 'off', '--pick-aperture-from-pose', 'off']
    return [
        ('empty', [], None),
        ('help', ['--help'], None),
        ('all_flags_once', ['--no-gui', '--no-boxel-viz', '--show-free', '--log-level', 'verbose',
                            '--scene', 'mixed', '--n-occluders', '2', '--n-targets', '3',
                            '--n-extra-distractors', '1', '--n-objects', '4', '--seed', '5',
                            '--goal', 'holding', '--stack-height', '3', '--allow-unwinnable',
                            '--unit-costs', '--corridor-test', 'object', '--path-check-diag',
                            '--path-check-step', '0.02', '--search-sample-ratio', '0.5',
                            '--sense-gate', 'strict', '--sense-over-region', 'off',
                            '--search-effort-weight', '0.5', '--search-initial-complexity', '2',
                            '--slip-fixes', 'none', '--grip-squeeze-mm', '1', '--save-screenshots', 'on',
                            '--planner', 'ff-astar', '--baseline', 'uniform', '--uniform-cell-size', '0.1',
                            '--min-boxel-size', '0.05', '--telemetry', '--world-counts', 'on',
                            '--telemetry-period', '0.1', '--telemetry-heartbeat', '1.0',
                            '--max-plan-time', '60'] + off, None),
        ('no_telemetry', ['--no-telemetry'], None),
        ('telemetry_then_no', ['--telemetry', '--no-telemetry'], None),
        ('each_planner', ['--planner', 'dijkstra'], None),
        ('log_levels', ['--log-level', 'quiet'], None),
        ('run_ps1_boxels', rp, None),
        ('run_ps1_boxels_off_squeeze_screens', rp + off + ['--grip-squeeze-mm', '1', '--save-screenshots', 'on'], None),
        ('run_ps1_extra_args', rp + ['--max-plan-time', '60', '--slip-fixes', 'default,carry_trapezoid'], None),
        ('policy_call', policy, ['--global-seed', '0', '--vis', '0', '--save-dir', '/x']),
        ('policy_call_same_sys_argv', policy, None),
        ('promote_default_to_scalability_n_occluders', ['--n-occluders', '2'], None),
        ('promote_by_n_targets', ['--n-targets', '2'], None),
        ('promote_by_n_hidden', ['--n-hidden', '1'], None),
        ('abbreviation_no_promotion', ['--n-occ', '2'], None),
        ('n_hidden_capped', ['--scene', 'scalability', '--n-hidden', '6', '--n-targets', '4'], None),
        ('n_hidden_wrong_scene', ['--scene', 'mixed', '--n-hidden', '1'], None),
        ('n_hidden_wrong_goal', ['--scene', 'scalability', '--n-hidden', '1', '--goal', 'stack'], None),
        ('n_hidden_no_occluders', ['--scene', 'scalability', '--n-hidden', '1', '--n-occluders', '0'], None),
        ('random_pairs_stack_goal', ['--scene', 'random-pairs', '--goal', 'stack', '--seed', '1'], None),
        ('random_pairs_n_hidden', ['--scene', 'random-pairs', '--n-hidden', '1', '--seed', '1'], None),
        ('random_pairs_n_targets', ['--scene', 'random-pairs', '--n-targets', '2', '--seed', '1'], None),
        ('random_pairs_zero_occluders', ['--scene', 'random-pairs', '--n-occluders', '0', '--seed', '1'], None),
        ('random_pairs_auto_seed', ['--scene', 'random-pairs'], None),
        ('random_pairs_tray_bump', ['--scene', 'random-pairs', '--goal', 'find-and-tray-stack', '--seed', '2'], None),
        ('random_pairs_tray_no_bump', ['--scene', 'random-pairs', '--goal', 'find-and-tray-stack', '--seed', '2',
                                       '--n-extra-distractors', '2'], None),
        ('stack_promotion', ['--goal', 'stack'], None),
        ('stack_explicit_scene', ['--goal', 'stack', '--scene', 'scalability'], None),
        ('bad_choice', ['--scene', 'nowhere'], None),
        ('bad_type', ['--seed', 'x'], None),
        ('unknown_flag', ['--frobnicate'], None),
        ('effort_weight_string', ['--search-effort-weight', 'inf'], None),
    ]


def _parse_case(rl, argv, sys_rest, prog='test_full_pipeline.py'):
    import random
    saved = sys.argv
    sys.argv = [prog] + list(argv if sys_rest is None else sys_rest)
    random.seed(12345)
    try:
        r = outcome(rl.parse_pipeline_args, list(argv))
    finally:
        sys.argv = saved
    if 'value' in r:
        r['value'] = {k: v for k, v in sorted(vars(r['value']).items())}
    return r


@pin('low', 'p22_cli', 'R22: run_logger.parse_pipeline_args over an argv corpus (vars, errors, --help)')
def p22_cli(out):
    import run_logger as rl
    out.note('sys.argv is patched to [test_full_pipeline.py] + the list (or the driver\'s own argv for '
             'policy_call); random.seed(12345) before each case (the auto seed draws from the global stream); '
             'COLUMNS=80; vars() written with keys sorted; errors as SystemExit code plus stderr')
    res = []
    for name, argv, sys_rest in _cli_corpus():
        res.append({'case': name, 'argv': argv, 'sys_argv_rest': sys_rest, **_parse_case(rl, argv, sys_rest)})
    out.json('cli.json', res)
    out.text('help.txt', next(r['stdout'] for r in res if r['case'] == 'help'))


# ----- pin 23: run_config --------------------------------------------------

def _main_block_slice(tree, first_text, last_target):
    """The statements of the __main__ block from the one whose source starts
    with first_text through the assignment to last_target."""
    for node in tree.body:
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)
                and isinstance(node.test.left, ast.Name) and node.test.left.id == '__name__'):
            body = node.body
            break
    else:
        raise LookupError('no __main__ block')
    start = end = None
    for i, st in enumerate(body):
        if start is None and isinstance(st, ast.Expr) and ast.unparse(st).startswith(first_text):
            start = i
        if (isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == last_target
                                               for t in st.targets)):
            end = i
            break
    if start is None or end is None:
        raise LookupError(f'slice {first_text!r} .. {last_target!r} not found')
    return body[start:end + 1]


@pin('low', 'p23_run_config', 'R23: the __main__ run_config dict for an argv corpus (AST slice executed)')
def p23_run_config(out):
    import run_logger as rl
    import test_full_pipeline as tfp
    src = (REPO / 'test_full_pipeline.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    stmts = _main_block_slice(tree, 'random.seed(args.seed)', 'run_config')
    code = compile(ast.Module(body=stmts, type_ignores=[]), 'test_full_pipeline.py', 'exec')
    out.note('the statements of the __main__ block from "random.seed(args.seed)" through the run_config '
             'assignment (seeding, scene_builders, scene_cfg, the tray switch, effective counts, run_config) '
             'are cut out with ast and executed in a copy of test_full_pipeline\'s globals with args from '
             'parse_pipeline_args; nothing else of the block runs')
    out.json('slice.json', [ast.unparse(s).splitlines()[0] for s in stmts])
    corpus = [(f'random_pairs_seed{s}', ['--no-gui', '--scene', 'random-pairs', '--seed', str(s), '--goal',
                                         'holding', '--n-occluders', '2']) for s in range(20)]
    corpus += [('default', ['--no-gui']), ('mixed_3', ['--scene', 'mixed', '--seed', '3']),
               ('scalability_3_4_1', ['--scene', 'scalability', '--n-occluders', '3', '--n-targets', '4',
                                      '--n-hidden', '1', '--seed', '0']),
               ('stack_3', ['--goal', 'stack', '--stack-height', '3', '--seed', '0']),
               ('tray', ['--scene', 'random-pairs', '--goal', 'find-and-tray-stack', '--seed', '1']),
               ('off_squeeze', ['--scene', 'random-pairs', '--seed', '4', '--m8', 'off', '--m9', 'off',
                                '--m10', 'off', '--pick-aperture-from-pose', 'off', '--grip-squeeze-mm', '1',
                                '--slip-fixes', 'none', '--search-sample-ratio', '0.25']),
               ('uniform', ['--baseline', 'uniform', '--uniform-cell-size', '0.1', '--min-boxel-size', '0.04'])]
    res = []
    for name, argv in corpus:
        p = _parse_case(rl, argv, None)
        if 'value' not in p:
            res.append({'case': name, 'parse': p})
            continue
        saved = sys.argv
        sys.argv = ['test_full_pipeline.py'] + argv
        args = rl.parse_pipeline_args(argv)
        sys.argv = saved
        ns = dict(vars(tfp))
        ns['args'] = args
        r = outcome(exec, code, ns)
        row = {'case': name, 'argv': argv, **{k: v for k, v in r.items() if k != 'value'}}
        if 'run_config' in ns and 'raises' not in r:
            rc = ns['run_config']
            row['run_config_keys_in_order'] = list(rc)
            row['run_config'] = rc
            row['scene_cfg'] = {'occluders': len(ns['scene_cfg'].occluders),
                                'targets': len(ns['scene_cfg'].targets),
                                'n_hidden_targets': ns['scene_cfg'].n_hidden_targets,
                                'enable_tray': getattr(ns['scene_cfg'], 'enable_tray', None)}
        res.append(row)
    out.json('run_config.json', res)


# ----- pins 24, 25: goal logic, carry schedule -----------------------------

@pin('low', 'p24_goals', 'R24: build_stack_goal and goal_satisfied')
def p24_goals(out):
    import random
    import test_full_pipeline as tfp
    names = ['cube_a', 'cube_b', 'cube_c', 'cube_d', 'cube_e']
    res = {'stack_rng': [], 'stack_global': [], 'errors': [], 'satisfied': []}
    for k in range(10):
        for h in (2, 3, 4):
            res['stack_rng'].append([k, h, outcome(tfp.build_stack_goal, list(names), h, rng=random.Random(k))])
            random.seed(k)
            g = outcome(tfp.build_stack_goal, list(names), h)
            g['global_state_after_sha256'] = text_digest(repr(random.getstate()))
            res['stack_global'].append([k, h, g])
    for h, objs in ((1, names), (0, names), (6, names), (2, ['only']), (2, [])):
        res['errors'].append([h, objs, outcome(tfp.build_stack_goal, list(objs), h, rng=random.Random(0))])
    rel_ = {'cube_a': 'cube_b', 'cube_b': 'cube_c', 'dice': 'table'}
    goals = [('holding', 'dice'), ('on', 'cube_a', 'cube_b'), ('on', 'cube_a', 'cube_c'),
             ('on_table', 'cube_c'), ('on_table', 'cube_a'), ('on_table', 'zzz'),
             ('and', ('on', 'cube_a', 'cube_b'), ('on', 'cube_b', 'cube_c')),
             ('and', ('on', 'cube_a', 'cube_b'), ('holding', 'dice')),
             ('and',), ('and', ('and', ('on', 'cube_b', 'cube_c'))), ('at_config', 'q_home'),
             ['on', 'cube_a', 'cube_b'], 'holding', None, ()]
    for g in goals:
        for onr in (None, {}, rel_):
            for tf in (False, True):
                res['satisfied'].append([repr(g), repr(onr), tf, outcome(tfp.goal_satisfied, g, onr, tf)])
    out.json('goals.json', res)
    out.note('goal inputs written as repr text (tuples and lists differ, which goal_satisfied tests)')


@pin('low', 'p25_carry', 'R25: carry_trapezoid_schedule on six fixed polylines')
def p25_carry(out):
    import numpy as np
    import test_full_pipeline as tfp
    Q0 = np.array([0.6, 0.3, -0.2, -2.0, 0.1, 2.0, -2.4])
    HOME = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785])
    bend = 0.5 * (Q0 + HOME) + np.array([0.25, -0.35, 0.0, 0.25, 0.0, 0.0, 0.0])
    lines = {
        'straight_pair': [Q0, HOME],
        'collinear_middle': [Q0, 0.5 * (Q0 + HOME), HOME],
        'linear_10': [Q0 + (HOME - Q0) * t for t in np.linspace(0.0, 1.0, 10)],
        'bent': [Q0, bend, HOME],
        'short_hop': [Q0, Q0 + np.array([0.01, 0, 0, 0, 0, 0, 0.002])],
        'zero_length_pair': [Q0, Q0, HOME],
        'four_points': [Q0, Q0 + 0.3, Q0 + np.array([0.3, 0.3, 0.3, 0.3, 0.3, 0.3, -0.5]), HOME],
    }
    res = {}
    for name, pts in lines.items():
        r = outcome(tfp.carry_trapezoid_schedule, pts)
        v = r.pop('value', None)
        if v is not None:
            commands, vertices = v
            r.update({'n_vertices': len(vertices), 'vertices': [np.asarray(x) for x in vertices],
                      'n_commands': len(commands), 'commands': array_digest(np.asarray(commands, float)),
                      'first_command': commands[0] if len(commands) else None,
                      'last_command': commands[-1] if len(commands) else None})
        res[name] = r
    res['defaults'] = {'CARRY_TRAP_ACCEL_LIMITS': tfp.CARRY_TRAP_ACCEL_LIMITS,
                       'CARRY_TRAP_COLLINEAR_COS': tfp.CARRY_TRAP_COLLINEAR_COS}
    out.json('carry.json', res)
    out.note('commands: exact float64 bytes digest and shape (R rule 3; R\'s row said "rounded", rule 3 wins)')


# ----- pin 26: pure console functions --------------------------------------

@pin('low', 'p26_console_pure', 'R26: console_ui pure text functions over real ledger rows and hand cases')
def p26_console_pure(out):
    import console_ui as cu
    rows = _read_jsonl(REPO / BF45_RUN / 'ledger.jsonl')
    steps = [r for r in rows if r.get('kind') == 'step']
    plans = [r for r in rows if r.get('kind') == 'plan']
    out.note(f'ledger rows: {BF45_RUN}/ledger.jsonl ({len(steps)} step rows, {len(plans)} plan rows)')
    res = {'describe_step_ledger': [[r['action'], r['args'], cu.describe_step(r['action'], r['args'])]
                                    for r in steps],
           'intention_ledger': [[r.get('plan_id'), cu.intention(r['actions'])] for r in plans]}
    names = ['view__look_dice_3', 'view__sense_retract', 'view__sense_retract_2', 'free_007',
             'shadow_of_cup_1__03', 'shadow_of_x', 'home', 'q_home', 'view__q_home', 'cfg:q_home',
             'Trajectory@1234', 'b_cups_ud', '', 'cfg:q_kin_dice_1', 'obj_003', 'tray']
    res['_place'] = [[n, cu._place(n)] for n in names]
    res['_move_phrase'] = [[n, cu._move_phrase(n)] for n in names]
    res['_where'] = [[n, cu._where(n)] for n in names]
    res['_symbols'] = cu._symbols(['cfg:q_home', 'Type@1', 'free_007', 'dice', 'Grasp@99'])
    hand_steps = [('move', ['cfg:q_home', 'cfg:view__look_dice_1', 'view__look_dice_1', 'T@1']),
                  ('move', ['cfg:a', 'cfg:q_home', 'home', 'T@1']), ('pick', ['dice', 'dice', 'G@1', 'cfg:x']),
                  ('place', ['dice', 'free_007', 'G@1', 'cfg:x']), ('place_hiding', ['cup', 'shadow_of_x__1']),
                  ('stack', ['cube_a', 'cube_b']), ('stack', ['cube_a']), ('sense', ['dice', 'shadow_of_cup_1__02']),
                  ('sense', ['dice', 'free_003']), ('sense', ['dice']), ('observe', ['dice', 'cfg:q']),
                  ('frobnicate', ['a', 'b']), ('move', []), ('pick', [])]
    res['describe_step_hand'] = [[a, s, cu.describe_step(a, s)] for a, s in hand_steps]
    plan_hand = [[['pick', 'a'], ['place', 'a', 'free_1'], ['move', 'x', 'q_home', 'home'],
                  ['sense', 'dice', 'shadow_of_a__1']],
                 [['move', 'x', 'y', 'free_2'], ['move', 'x', 'y', 'home']],
                 [['observe', 'dice'], ['pick', 'dice'], ['stack', 'dice', 'tray']],
                 [['sense', 'dice', 'free_3'], ['sense', 'x']],
                 [['zap', 'a']] * 9, [['pick', 'a']], []]
    res['intention_hand'] = [cu.intention(p) for p in plan_hand]
    res['_mission'] = [[g, cu._mission(g)] for g in ('holding dice at home', 'holding dice', 'holding',
                                                      'holding at home', 'stack', 'stack 3',
                                                      'find-and-tray-stack', '', None, 'other goal')]
    res['_found_in'] = [[v, cu._found_in(v)] for v in ('shadow_of_x', 'shadow_of_cup_1__02', 'free_3',
                                                        'free_x', 'picked', None, '', 'obj_002')]
    saved_repo = cu.REPO
    cu.REPO = '/r'
    res['_short_path'] = [[p, lim, cu._short_path(p, lim)]
                          for p in ('/r/logs/run_2026-10-30_14-03-01', '/r/archive/a/b/c/d/run_x',
                                    '/elsewhere/logs/run_1', 'C:\\r\\logs\\run_1', '/r/x')
                          for lim in (None, 10, 30)]
    cu.REPO = saved_repo
    out.note('_short_path with console_ui.REPO set to "/r" (restored after)')
    parts = cu._mark('pick up `dice` and set it down on `free_007` now')
    res['_mark'] = parts
    res['_plain'] = cu._plain(parts)
    res['_wrap'] = [[w, i, h, cu._wrap(parts, w, i, h)] for w, i, h in ((None, 2, 4), (20, 2, 4), (8, 0, 0),
                                                                         (80, 4, 6), (12, 10, 2))]
    res['_wrap_empty'] = cu._wrap([], 20, 2, 2)
    res['_clip'] = [[lim, ell, cu._clip(parts, lim, ell)] for lim, ell in ((None, '...'), (10, '...'),
                                                                          (25, '\u2026'), (200, '...'), (2, '...'))]
    con = cu.Console.__new__(cu.Console)
    frames = []
    for frame in range(0, 25):
        con._frame = frame
        frames.append([frame,
                       con._sprite_frame({'frames': ['a', 'b', 'c', 'd'], 'period_ms': 200}, {'frame0': 1}),
                       con._sprite_frame({'frames': ['a', 'b', 'c', 'd'], 'period_ms': 300, 'pingpong': True}, {}),
                       con._sprite_frame({'frames': ['x'], 'pingpong': True}, {'frame0': 3}),
                       con._sprite_frame({'frames': ['p', 'q'], 'period_ms': 40}, {})])
    res['_sprite_frame'] = frames
    out.note('_sprite_frame on Console.__new__(Console) with _frame set (no constructor, no thread)')
    out.json('console_pure.json', res)


# ----- pins 28, 29: sprites, audio -----------------------------------------

@pin('low', 'p28_sprites', 'R28: tools/sprite_tool.assemble against console_art.py')
def p28_sprites(out):
    import difflib
    st = _load_tool('sprite_tool')
    target = Path('console_art_assembled.py')
    r = outcome(st.assemble, str(REPO / 'tools' / 'sprites'), str(target))
    built = target.read_bytes() if target.exists() else b''
    have = (REPO / 'console_art.py').read_bytes()
    res = {'assemble': r, 'equal_bytes': built == have,
           'equal_after_crlf_to_lf': built.replace(b'\r\n', b'\n') == have.replace(b'\r\n', b'\n'),
           'console_art_has_crlf': b'\r\n' in have, 'assembled_sha256': hashlib.sha256(built).hexdigest(),
           'console_art_sha256_crlf_to_lf': hashlib.sha256(have.replace(b'\r\n', b'\n')).hexdigest(),
           'sources': sorted(p.name for p in (REPO / 'tools' / 'sprites').glob('*.txt'))}
    if not res['equal_after_crlf_to_lf']:
        res['diff'] = list(difflib.unified_diff(have.decode('utf-8').splitlines(),
                                                built.decode('utf-8').splitlines(), lineterm='', n=1))[:200]
    out.json('sprites.json', res)
    out.note('the assembled file goes to the work folder; sources listed sorted (a glob)')


@pin('low', 'p29_audio', 'R29: console_audio.PIECES synthesized, sha256 of each WAV', timeout=1500)
def p29_audio(out):
    import console_audio as ca
    res = {'RATE': ca.RATE, 'pieces': {}}
    for name, make in ca.PIECES.items():
        mix = make()
        path = Path(f'{name}.wav')
        mix.write(str(path))
        res['pieces'][name] = {'n': mix.n, 'wav_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                               'wav_bytes': path.stat().st_size}
    out.json('audio.json', res)
    out.note('ensure_sounds() is not called (it writes under the repo logs/); WAVs written in the work folder')


# ----- pin 30: report_run_outcome ------------------------------------------

@pin('low', 'p30_report', 'R30: run_logger.report_run_outcome for every ending, stdout and timing_summary.json')
def p30_report(out):
    import types
    import numpy as np
    import run_logger as rl
    from boxel_data import BoxelData, BoxelType, BoxelRegistry

    def belief(found=None, unknown=(), parked=()):
        return types.SimpleNamespace(target_found_in=found, get_unknown_shadows=lambda: list(unknown),
                                     get_parked_shadows=lambda: list(parked))
    reg = BoxelRegistry()
    for t, c in ((BoxelType.OBJECT, (0.3, 0, 0.66)), (BoxelType.SHADOW, (0.3, 0.1, 0.66)),
                 (BoxelType.FREE_SPACE, (0.1, 0.1, 0.7)), (BoxelType.FREE_SPACE, (0.5, 0.1, 0.7))):
        reg.add_boxel(BoxelData.from_center_extent(c, (0.03, 0.04, 0.035), t,
                                                   object_name='a' if t == BoxelType.OBJECT else None))
    events = [{'kind': 'disturbed', 'object': 'cup_2', 'label': 'pick'},
              {'kind': 'knocked_off_table', 'object': 'cube_b', 'label': 'place'},
              {'kind': 'lost', 'object': 'dice', 'label': 'move'}]
    shadows = ['shadow_001', 'shadow_002', 'shadow_003']
    base = dict(goal_kind='holding', goal=('holding', 'dice'), target_name='dice', on_relations={},
                belief=belief(unknown=['shadow_003'], parked=['shadow_002']), plan_count=4, sense_count=2,
                shadows=shadows, blocked_giveup_shadows=set(), plan_times=[1.25, 0.5, 3.0, 0.125],
                total_plan_time=4.875, physical_failures=[{'action': 'pick', 'why': 'slip'}],
                physics_failures=[], run_config={'scene': 'random-pairs', 'seed': 0}, registry=None)
    cases = [
        ('success_holding', dict(success=True, exit_reason=None,
                                 belief=belief('shadow_001', ['shadow_003'], ['shadow_002']),
                                 integrity_events=events[:1], m8_stats={'observes': 1})),
        ('success_holding_no_parked', dict(success=True, exit_reason=None, belief=belief('shadow_001'))),
        ('success_stack', dict(success=True, exit_reason=None, goal_kind='stack',
                               goal=('and', ('on', 'cube_a', 'cube_b')), on_relations={'cube_a': 'cube_b'})),
        ('all_searched', dict(success=False, exit_reason='all_searched')),
        ('all_searched_blocked', dict(success=False, exit_reason='all_searched',
                                      blocked_giveup_shadows={'shadow_003', 'shadow_001'})),
        ('pick_giveup', dict(success=False, exit_reason='pick_giveup', pick_giveup_objects={'cup_2', 'cup_1'})),
        ('no_plan_while_holding', dict(success=False, exit_reason='no_plan_while_holding')),
        ('planner_failed', dict(success=False, exit_reason='planner_failed')),
        ('no_plan_binding_death', dict(success=False, exit_reason='no_plan_binding_death')),
        ('drop_failed', dict(success=False, exit_reason='drop_failed')),
        ('knocked_off_table', dict(success=False, exit_reason='knocked_off_table', integrity_events=events)),
        ('target_lost', dict(success=False, exit_reason='target_lost', integrity_events=events)),
        ('stack_giveup', dict(success=False, exit_reason='stack_giveup', goal_kind='stack',
                              stack_fail_counts={('cube_a', 'cube_b'): 3, ('cube_c', 'cube_a'): 1,
                                                 ('cube_b', 'cube_c'): 2, ('x', 'y'): 1})),
        ('physics_mismatch', dict(success=False, exit_reason='physics_mismatch',
                                  physics_failures=[{'check': 'gripper', 'ok': False}])),
        ('timeout_none', dict(success=False, exit_reason=None)),
        ('stack_fallthrough', dict(success=False, exit_reason='other', goal_kind='stack',
                                   goal=('on', 'a', 'b'), on_relations={'a': 'table'})),
        ('else_fallthrough', dict(success=False, exit_reason='other')),
        ('counts_given', dict(success=True, exit_reason=None, belief=belief('shadow_001'), registry=reg,
                              last_init=[('Boxel', 'free_1'), ('Boxel', 'free_2'), ('handempty',), (),
                                         ('obj_at_boxel', 'dice', 'shadow_001')],
                              boxel_counts_per_replan=[{'free': 4}, {'free': 5}],
                              observer_counts={'drops': [{'object': 'dice', 'phase': 'carry'}],
                                               'collisions': [{'object': 'cup_1', 'phase': 'move'}],
                                               'check_s': 0.25},
                              drops_noticed={'grip_check': 1, 'eye': 0}, collisions_reported=2,
                              integrity_events=events)),
        ('no_plans', dict(success=False, exit_reason='planner_failed', plan_times=[], total_plan_time=0.0,
                          plan_count=0)),
        ('no_run_logger', dict(success=False, exit_reason='planner_failed', run_logger=None)),
    ]
    out.note('belief is a namespace with target_found_in and the two getters; run_logger a namespace with '
             'run_dir = a relative folder per case in the work folder and log_path None; no console installed')
    res = []
    for name, kw in cases:
        run_dir = Path('runs') / name
        run_dir.mkdir(parents=True)
        args = dict(base)
        args['run_logger'] = types.SimpleNamespace(run_dir=run_dir, log_path=None)
        args.update(kw)
        r = outcome(rl.report_run_outcome, **args)
        summary = run_dir / 'timing_summary.json'
        r['timing_summary_json'] = summary.read_text() if summary.exists() else None
        res.append({'case': name, **r})
    out.json('report.json', res)


# ----- pin 31: eval matrix -------------------------------------------------

@pin('low', 'p31_eval_matrix', 'R31: eval_runner presets as (tag, argv) and run_cell with a fake subprocess.run')
def p31_eval_matrix(out):
    import subprocess as sp
    import types
    import eval_runner as er
    out.note('argv[0] (sys.executable) dropped; presets of more than 100 cells written as count, sha256 '
             'of the lines and the first and last 20 lines (one compact JSON [tag, argv] per line)')
    res = {}
    for preset, matrix in er.MATRIX_PRESETS.items():
        lines = [json.dumps([er.cell_tag(c), er.cell_to_argv(c, [])[1:]]) for c in er.iterate_matrix(matrix)]
        entry = {'n': len(lines), 'sha256': text_digest('\n'.join(lines))}
        if len(lines) <= 100:
            entry['lines'] = lines
        else:
            entry['first'], entry['last'] = lines[:20], lines[-20:]
        res[preset] = entry
    res['cell_to_argv_extra'] = er.cell_to_argv(next(iter(er.iterate_matrix(er.MATRIX_PRESETS['smoke']))),
                                                ['--max-plan-time', '60'])[1:]
    out.json('matrix.json', res)
    cell = dict(next(iter(er.iterate_matrix(er.MATRIX_PRESETS['smoke']))))
    clock = {'t': 0.0}

    def perf_counter():
        clock['t'] += 1.5
        return clock['t']
    er.time = types.SimpleNamespace(perf_counter=perf_counter)
    out.note('eval_runner.time replaced by a namespace whose perf_counter steps 1.5 s per call, so '
             'wall_clock_s is fixed; eval_runner.subprocess replaced by a namespace with a fake run')
    mode = {'m': None}
    counter = {'n': 0}

    def fake_run(argv, capture_output, text, timeout, cwd):
        m = mode['m']
        counter['n'] += 1
        if m == 'timeout':
            raise sp.TimeoutExpired(argv, timeout)
        if m == 'crash':
            return sp.CompletedProcess(argv, 3, 'some output', 'Traceback ...')
        if m in ('good', 'mismatch'):
            d = Path('logs') / f'run_fake_{counter["n"]:02d}'
            d.mkdir(parents=True)
            rc = {'scene': cell['scene'], 'seed': cell['seed'] + (7 if m == 'mismatch' else 0),
                  'goal': cell['goal'], 'baseline': cell.get('baseline', 'semantic'),
                  'unit_costs': bool(cell['unit_costs'])}
            if cell.get('min_boxel_size') is not None:
                rc['min_boxel_size'] = cell['min_boxel_size']
            (d / 'timing_summary.json').write_text(json.dumps(
                {'run_config': rc, 'success': True, 'plan_count': 3, 'total_planning_time_s': 1.5}))
            return sp.CompletedProcess(argv, 0, 'ok', '')
        if m == 'preflight':
            return sp.CompletedProcess(argv, 1, '', 'x\n[pre-flight] seed 0 rejected: no scene\n')
        return sp.CompletedProcess(argv, 1, 'nothing', '')
    er.subprocess = types.SimpleNamespace(run=fake_run, TimeoutExpired=sp.TimeoutExpired)
    runs = []
    for i, (m, skip) in enumerate((('timeout', False), ('crash', False), ('no_summary', False),
                                   ('preflight', False), ('mismatch', False), ('good', False),
                                   ('good', True), ('crash', True))):
        mode['m'] = m
        sweep = Path(f'sweep_{i}_{m}{"_skip" if skip else ""}')
        if skip:
            sweep = Path('sweep_5_good')
        r = outcome(er.run_cell, cell, sweep, 30.0, [], skip)
        files = {}
        cdir = sweep / 'cells' / er.cell_tag(cell)
        for f in sorted(cdir.glob('*')):
            files[f.name] = f.read_text(encoding='utf-8')
        runs.append({'mode': m, 'skip_existing': skip, **r, 'files': files})
    out.json('run_cell.json', runs)


# ----- pin 32: run.ps1 dry runs --------------------------------------------

@pin('low', 'p32_run_ps1', 'R32: run.ps1 -DryRun over a grid of switches (pwsh.exe through WSL interop)')
def p32_run_ps1(out):
    import re
    import shutil as sh
    pwsh = sh.which('pwsh.exe')
    if pwsh is None:
        raise RuntimeError('pwsh.exe not found (needs WSL interop and PowerShell 7 on Windows)')
    win = subprocess.run(['wslpath', '-w', str(REPO / 'run.ps1')], capture_output=True, text=True,
                         check=True).stdout.strip()
    cases = [
        ('tampura_default', "tampura -Seed 7"), ('tampura_headless', "tampura -Seed 7 -Headless"),
        ('tampura_gen', "tampura -Seed 118 -Gen -Headless"), ('tampura_gen_missing', "tampura -Seed 5 -Gen"),
        ('tampura_off', "tampura -Seed 0 -Off"), ('tampura_squeeze', "tampura -Seed 0 -Squeeze 1"),
        ('tampura_squeeze_frac', "tampura -Seed 0 -Squeeze 0.75"),
        ('tampura_screenshots', "tampura -Seed 0 -Screenshots"),
        ('tampura_draw', "tampura -Seed 0 -Draw boxels"), ('tampura_draw_case_list', "tampura -Seed 0 -Draw Boxels,boxels"),
        ('tampura_draw_bad', "tampura -Seed 0 -Draw lines"), ('tampura_draw_headless', "tampura -Seed 0 -Draw boxels -Headless"),
        ('boxels_draw', "boxels -Seed 0 -Draw boxels"), ('tampura_music', "tampura -Seed 0 -Music"),
        ('tampura_sfx', "tampura -Seed 0 -Sfx"), ('tampura_voice', "tampura -Seed 0 -Voice"),
        ('tampura_args', "tampura -Seed 0 -Args '--max-plan-time 60'"),
        ('tampura_rest', "tampura -Seed 0 --log-level quiet"),
        ('seed_list_comma', "tampura -Seed 118,102 -Headless"),
        ('seed_list_brackets', "tampura -Seed '[118, 102, 103]' -Headless"),
        ('seed_list_spaces', "tampura -Seed 118 102 -Headless"),
        ('seed_bad', "tampura -Seed x"), ('target_bad', "foo -Seed 1"),
        ('boxels_default', "boxels -Seed 3"), ('boxels_headless_off', "boxels -Seed 3 -Headless -Off"),
        ('boxels_scene_goal', "boxels -Seed 0 -Scene stack -Goal stack -Occluders 0"),
        ('alias_d', "tampura -Seed 1 -D"),
    ]
    script = []
    for name, args in cases:
        script += [f"'@@CASE {name}'", "$global:LASTEXITCODE = 0",
                   f"& '{win}' {args}{'' if name == 'alias_d' else ' -DryRun'} *>&1 | ForEach-Object {{ \"$_\" }}",
                   "'@@RC ' + $LASTEXITCODE"]
    proc = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-Command', '; '.join(script)],
                          capture_output=True, text=True, timeout=300, cwd=str(REPO))
    stamp = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}')
    text = stamp.sub('<STAMP>', proc.stdout.replace('\r\n', '\n'))
    res, cur = [], None
    for line in text.split('\n'):
        if line.startswith('@@CASE '):
            cur = {'case': line[7:], 'args': dict(cases)[line[7:]], 'lines': []}
            res.append(cur)
        elif line.startswith('@@RC '):
            cur['rc'] = line[5:]
        elif cur is not None and line:
            cur['lines'].append(line)
    out.json('dry_runs.json', {'pwsh_rc': proc.returncode, 'stderr': stamp.sub('<STAMP>', proc.stderr),
                               'cases': res})
    out.note('pwsh.exe -NoProfile -NonInteractive through WSL interop, one call for all cases; host output '
             'merged (*>&1); the folder stamp masked as <STAMP>; the checkout path masked as <REPO>')


# ----- pin 33: records of a recorded run -----------------------------------

@pin('low', 'p33_recorded_run', 'R33: tools/episode_metrics and tools/eye.py on the tracked BF45_46 run')
def p33_recorded_run(out):
    em = _load_tool('episode_metrics')
    run = REPO / BF45_RUN
    out.json('metrics.json', {'metrics': em.metrics(str(run)),
                              'main': outcome(em.main, [str(run)])})
    eye = []
    for args in (['--list'], ['--audit'], ['--index', '3'], ['--plan', '2'], ['--tag', 'pick'],
                 ['--diff', '1', '5'], ['--index', '3', '--no-view'], ['--index', '3', '--no-facts'],
                 ['--index', '3', '--free'], ['--step', '500'], ['--index', '999']):
        p = subprocess.run([sys.executable, str(REPO / 'tools' / 'eye.py'), str(run)] + args,
                           capture_output=True, text=True, timeout=120)
        eye.append({'args': args, 'rc': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    out.json('eye.json', eye)
    out.note(f'run folder {BF45_RUN} (tracked); eye.py run as a subprocess per call')


# ----- pin 36: gate table from a recorded ledger ---------------------------

@pin('low', 'p36_ledger_gates', 'R36: tools/bridge_gates.run_ledger on recorded ledgers, episode_outcome, the CLI')
def p36_ledger_gates(out):
    bg = _load_tool('bridge_gates')
    bf2 = Path('bf2_run')
    bf2.mkdir()
    shutil.copyfile(REPO / BF2_LEDGER, bf2 / 'ledger.jsonl')
    bf38 = 'archive/tampura_bridge_plan_2026-10-25/bf/BF38_q14/seed0_sq0.5mm/ours/run_2026-10-30_09-00-03'
    res = []
    for label, run, m7 in (('BF45_46 m7 on', REPO / BF45_RUN, 'on'), ('BF45_46 m7 off', REPO / BF45_RUN, 'off'),
                           ('BF38_q14 m7 on', REPO / bf38, 'on'), ('BF2_b0 boxels m7 on', bf2, 'on')):
        report = bg.Report()
        r = outcome(bg.run_ledger, report, str(run), m7)
        res.append({'case': label, 'rows': report.rows, 'failed': report.failed(), **r})
    out.json('run_ledger.json', res)
    rep_fail = bg.Report()
    rep_fail.add('G3', 'FAIL', 'x')
    rep_ok = bg.Report()
    rep_ok.add('G3', 'PASS', 'y')
    out.json('episode_outcome.json', [
        bg.episode_outcome([0.0, 1.0], 'Traceback: boom', rep_fail),
        bg.episode_outcome([0.0, 1.0], None, rep_fail),
        bg.episode_outcome([0.0, 1.0], None, rep_ok),
        bg.episode_outcome([0.0, 0.0], None, rep_ok),
        bg.episode_outcome([], None, rep_ok)])
    cli = []
    for args in (['ledger', str(REPO / BF45_RUN)], ['ledger', str(REPO / BF45_RUN), '--m7', 'off'],
                 ['ledger']):
        p = subprocess.run([sys.executable, str(REPO / 'tools' / 'bridge_gates.py')] + args,
                           capture_output=True, text=True, timeout=120)
        cli.append({'args': args, 'rc': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
    out.json('cli.json', cli)
    out.note('BF2_b0 ledger copied into the work folder as ledger.jsonl (run_ledger reads that name)')


# ----- pin 37: static gates ------------------------------------------------

@pin('low', 'p37_static_gates', 'R37: tools/bridge_gates.py static and allowlist-draft, whole output and exit code')
def p37_static_gates(out):
    import re
    res = []
    for cmd in ('static', 'allowlist-draft'):
        p = subprocess.run([sys.executable, str(REPO / 'tools' / 'bridge_gates.py'), cmd],
                           capture_output=True, text=True, timeout=300, cwd=str(REPO))
        res.append({'cmd': cmd, 'rc': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr,
                    'hit_counts': re.findall(r'(\S+)\s+\S+\s+(\d+) hits', p.stdout)})
    allow = (REPO / 'tools' / 'bridge_gates_allowlist.txt').read_text(encoding='utf-8').splitlines()
    rows = [ln for ln in allow if ln.strip() and not ln.lstrip().startswith('#')]
    out.json('static.json', {'runs': res, 'allowlist_rows': len(rows),
                             'allowlist_by_gate': {g: sum(1 for r in rows if r.split('|')[0].strip() == g)
                                                   for g in ('G1', 'G2')},
                             'eval_results_tampura_bridge_dirs': sorted(
                                 p.name for p in (REPO / 'eval_results').glob('tampura_bridge_*'))})
    out.note('run from the repo root; eval_results/tampura_bridge_* (walked by G17, outside git) listed sorted')


# ----- pin 38: episode record key sets -------------------------------------

def _key_types(obj, depth):
    """Key names and value types in file order, recursively to depth."""
    if isinstance(obj, dict):
        if depth <= 0:
            return 'dict'
        return [[k, _key_types(v, depth - 1)] for k, v in obj.items()]
    if isinstance(obj, list):
        if depth <= 0 or not obj:
            return f'list[{len(obj)}]' if depth <= 0 else 'list[0]'
        return ['list', _key_types(obj[0], depth - 1)]
    return type(obj).__name__


@pin('low', 'p38_record_keys', 'R38: key names and value types of stored episode records (readers, not writers)')
def p38_record_keys(out):
    base = 'archive/tampura_bridge_plan_2026-10-25'
    files = {
        'BF45_46 bridge_episode.json (seed 10)': f'{BF45}/bridge_episode.json',
        'BF38_q14 bridge_episode.json (seed 0)': f'{base}/bf/BF38_q14/seed0_sq0.5mm/bridge_episode.json',
        'BF45_46 timing_summary.json': f'{BF45_RUN}/timing_summary.json',
        'tb25_ab world_counts.json (seed 0)': f'{base}/tracks/freeze/board_2026-11-13/tb25_ab/s0_cell_r1/world_counts.json',
    }
    res = {}
    for label, path in files.items():
        res[label] = {'path': path, 'keys': _key_types(json.loads((REPO / path).read_text(encoding='utf-8')), 3)}
    jl = f'{base}/bf/BF59_slip/eval/A_5006486/results.jsonl'
    first = _read_jsonl(REPO / jl)[0]
    res['BF59 results.jsonl row 1 (seed 0)'] = {'path': jl, 'keys': _key_types(first, 3)}
    out.json('record_keys.json', res)
    out.note('depth 3; lists show the type of their first element; this pin reads stored records and does '
             'not guard the writers (a writer change shows only in a new run, pin 47 scope)')


# ----- AST helpers ---------------------------------------------------------

def _parse(path):
    return ast.parse(Path(path).read_text(encoding='utf-8'), filename=str(path))


class _Scoped(ast.NodeVisitor):
    """Walk a module keeping the qualified name of the enclosing def/class;
    calls self.on(node, qualname) for every node."""

    def __init__(self, on):
        self.on, self.stack = on, []

    def generic_visit(self, node):
        self.on(node, '.'.join(self.stack) or '<module>')
        named = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        if named:
            self.stack.append(node.name)
        super().generic_visit(node)
        if named:
            self.stack.pop()


def _walk_scoped(tree, on):
    _Scoped(on).visit(tree)


def _template(node):
    """A string node as a text template: a Constant its value, a JoinedStr
    its constant parts with each field as {expr!c:spec}."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant):
                parts.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                s = '{' + ast.unparse(v.value)
                if v.conversion != -1:
                    s += '!' + chr(v.conversion)
                if v.format_spec is not None:
                    s += ':' + (_template(v.format_spec) or '')
                parts.append(s + '}')
        return ''.join(parts)
    return None


def _templates_in(node):
    """Every string template in a subtree; an f-string counts once."""
    t = _template(node)
    if t is not None:
        return [t]
    if isinstance(node, ast.Constant):
        return []
    out = []
    for ch in ast.iter_child_nodes(node):
        out += _templates_in(ch)
    return out


_LEVELS = {'debug', 'info', 'warning', 'error', 'exception', 'critical'}


def _text_callee(call):
    """The callee kind of a call that prints, logs or records text, or None."""
    fn = call.func
    if isinstance(fn, ast.Name):
        if fn.id in ('print', 'ledger_event', 'dispatch_begin', 'dispatch_end', 'note'):
            return fn.id
        return None
    if isinstance(fn, ast.Attribute):
        recv = ast.unparse(fn.value)
        if fn.attr in _LEVELS:
            return f'log.{fn.attr}'
        if fn.attr == 'write' and (recv in ('sys.stderr', 'sys.stdout') or recv.endswith(('stderr', 'stdout'))):
            return f'{recv}.write'
        if fn.attr == 'warn' and recv == 'warnings':
            return 'warnings.warn'
        if recv == 'console_ui':
            return f'console_ui.{fn.attr}'
        if fn.attr in ('ledger_event', 'dispatch_begin', 'dispatch_end', 'note'):
            return fn.attr
    return None


# ----- pin 39: printed text ------------------------------------------------

@pin('low', 'p39_printed_text', 'P39: multiset of text templates in print, log, stderr, ledger and console calls (AST)')
def p39_printed_text(out):
    from collections import Counter
    counts, files, callees = Counter(), {}, Counter()
    scope = repo_py_files()
    for path in scope:
        r = rel(path)
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                kind = _text_callee(node)
                if kind is None:
                    continue
                callees[kind] += 1
                for sub in list(node.args) + [k.value for k in node.keywords]:
                    for t in _templates_in(sub):
                        counts[t] += 1
                        files.setdefault(t, set()).add(r)
    out.json('templates.json', [[t, counts[t]] for t in sorted(counts)])
    out.json('INFO_files.json', {t: sorted(files[t]) for t in sorted(files)})
    out.json('callees.json', {k: callees[k] for k in sorted(callees)})
    out.json('scope.json', [rel(p) for p in scope])
    out.note('scope: root *.py, tampura_bridge/*.py, tools/*.py (index open point 1: the indexer\'s choice, '
             'PLAN says "the repo"); templates sorted by text with their count (a Counter); INFO_files.json '
             '(the files of each template, sorted sets) is information only and not compared')
    out.note('callees: print, ledger_event, dispatch_begin, dispatch_end, note, any .debug/.info/.warning/'
             '.error/.exception/.critical, .write on a stderr/stdout name, warnings.warn, console_ui.*')
    out.note('f-string fields written as {ast.unparse(expr)!c:spec}: valid for this Python version only')


# ----- pin 40: ledger schema -----------------------------------------------

@pin('low', 'p40_ledger_schema', 'P40: per ledger_event call site the kind and keyword names (AST)')
def p40_ledger_schema(out):
    from collections import Counter
    sites = []
    for path in repo_py_files():
        r = rel(path)
        tree = _parse(path)
        aliases = {'ledger_event'}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == 'ledger_event' and a.asname:
                        aliases.add(a.asname)

        def on(node, qual):
            if not isinstance(node, ast.Call):
                return
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
            if name not in aliases:
                return
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                kind = node.args[0].value
            elif node.args:
                kind = f'<dynamic: {ast.unparse(node.args[0])}>'
            else:
                kind = '<no kind>'
            kws = [k.arg if k.arg is not None else '**' + ast.unparse(k.value) for k in node.keywords]
            sites.append({'file': r, 'function': qual, 'line': node.lineno, 'callee': ast.unparse(fn),
                          'kind': kind, 'keywords': kws, 'n_positional': len(node.args)})
        _walk_scoped(tree, on)
    multi = Counter((s['kind'], tuple(s['keywords']), s['n_positional']) for s in sites)
    out.json('schema.json', [[k, list(kw), npos, multi[(k, kw, npos)]] for (k, kw, npos) in sorted(multi)])
    out.json('kinds.json', sorted({s['kind'] for s in sites}))
    rl_tree = _parse(REPO / 'run_logger.py')
    statuses = None
    for node in rl_tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'STEP_END_STATUSES'
                                                for t in node.targets):
            statuses = list(ast.literal_eval(node.value))
    out.json('step_end_statuses.json', statuses)
    out.json('INFO_sites.json', sorted(sites, key=lambda s: (s['file'], s['line'])))
    out.note('schema.json: [kind, keyword names in source order, positional count, number of sites], sorted '
             '(a multiset); kinds.json a sorted set; STEP_END_STATUSES in source order (a tuple); '
             'INFO_sites.json (file, function, line per site) is information only and not compared')


# ----- pin 41: RNG sites ---------------------------------------------------

_RNG_PREFIXES = ('random.', 'np.random.', 'numpy.random.', 'rng.', 'self.rng.', 'self._rng.', '_rng.')
_RNG_CTORS = ('random.Random', 'np.random.RandomState', 'np.random.default_rng',
              'numpy.random.RandomState', 'numpy.random.default_rng')


@pin('low', 'p41_rng_sites', 'P41: per function, in source order, every random/np.random/rng call (AST)')
def p41_rng_sites(out):
    table, info = {}, []
    for path in repo_py_files():
        r = rel(path)
        tree = _parse(path)
        bound = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
                if ast.unparse(node.value.func) in _RNG_CTORS:
                    for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                        bound.add(ast.unparse(t))
        found = []

        def on(node, qual):
            if not isinstance(node, ast.Call):
                return
            callee = ast.unparse(node.func)
            recv = callee.rsplit('.', 1)[0] if '.' in callee else None
            if callee.startswith(_RNG_PREFIXES) or callee in _RNG_CTORS or (recv in bound):
                seed = None
                if callee in _RNG_CTORS:
                    seed = ', '.join([ast.unparse(a) for a in node.args]
                                     + [f'{k.arg}={ast.unparse(k.value)}' for k in node.keywords])
                found.append((node.lineno, node.col_offset, qual, callee, seed))
        _walk_scoped(tree, on)
        for line, col, qual, callee, seed in sorted(found):
            table.setdefault(f'{r}::{qual}', []).append([callee, seed])
            info.append([r, qual, line, callee])
    out.json('rng_sites.json', {k: table[k] for k in sorted(table)})
    out.json('INFO_lines.json', info)
    out.note('keys "file::qualname" sorted; per function the calls in source order (line, column) as '
             '[callee text, constructor arguments or null]; receivers: random., np.random., numpy.random., '
             'rng., self.rng., self._rng., _rng. and names assigned from random.Random / RandomState / '
             'default_rng in the same file')
    out.note('rng = rng or random (test_full_pipeline build_stack_goal): rng.shuffle is the global '
             'random.shuffle when rng is None; the AST cannot tell')
    out.note('not done here: the call chain of main (the global order of draws at run time); that is a '
             'property of calls, covered by the episode pins (34, 47)')


# ----- pin 42: gate surface ------------------------------------------------

_REBOUND = [('robot_utils', 'solve_ik'), ('robot_utils', 'move_robot_smooth'),
            ('robot_utils', 'is_config_collision_free'), ('robot_utils', 'is_path_collision_free'),
            ('world_eye', 'enable'), ('world_eye', 'snapshot'), ('world_eye', 'disable'),
            ('telemetry', 'enable'), ('telemetry', 'tick'), ('telemetry', 'phase'), ('telemetry', 'note'),
            ('telemetry', 'disable'), ('telemetry', 'attach_robot'), ('telemetry', 'register_bodies'),
            ('boxel_env', 'BoxelTestEnv.sync_to_plan_client'), ('boxel_data', 'BoxelRegistry.__init__'),
            ('pddlstream_planner', 'PDDLStreamPlanner.plan'), ('pddlstream_planner', 'solve')]


def _module_binds(tree, dotted):
    """Where a module binds a name (or Class.method): [kind, line] or None."""
    parts = dotted.split('.')
    body = tree.body
    if len(parts) == 2:
        for node in body:
            if isinstance(node, ast.ClassDef) and node.name == parts[0]:
                for n in node.body:
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == parts[1]:
                        return ['method in class body', n.lineno]
                return None
        return None
    name = parts[0]
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return ['def', node.lineno]
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                if (a.asname or a.name).split('.')[0] == name:
                    return ['import', node.lineno]
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ['assign', node.lineno]
    return None


@pin('low', 'p42_gate_surface', 'P42: the names the gate hooks rebind and the facts they rely on (AST)')
def p42_gate_surface(out):
    scope = repo_py_files()
    trees = {rel(p): _parse(p) for p in scope}
    facts, info = [], []
    for mod, name in _REBOUND:
        b = _module_binds(trees[f'{mod}.py'], name)
        facts.append({'fact': 1, 'subject': f'{mod}.{name}', 'found': b is not None,
                      'kind': b[0] if b else None})
        info.append([f'{mod}.{name}', b[1] if b else None])
    sync = _module_binds(trees['boxel_env.py'], 'BoxelTestEnv.sync_to_plan_client')
    facts.append({'fact': 2, 'subject': 'BoxelTestEnv.sync_to_plan_client in the class body',
                  'found': sync is not None})
    from_pyb, aliased, solve_sites, tfp_importers, pddl_importers = [], [], [], [], []
    rebound_names = {n.split('.')[-1] for _, n in _REBOUND if '.' not in n}
    rebound_mods = {m for m, n in _REBOUND}
    for r, tree in trees.items():
        def on(node, qual, r=r):
            if isinstance(node, ast.ImportFrom) and not node.level:
                m = node.module or ''
                if m == 'pybullet' or m.startswith('pybullet.'):
                    from_pyb.append([r, qual])
                if m in rebound_mods:
                    for a in node.names:
                        if a.name in rebound_names and a.asname and a.asname != a.name:
                            aliased.append([r, qual, m, a.name, a.asname])
                if m == 'test_full_pipeline':
                    tfp_importers.append([r, qual, 'from'])
                if m == 'pddlstream' or m.startswith('pddlstream.'):
                    pddl_importers.append([r, qual, m])
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == 'test_full_pipeline':
                        tfp_importers.append([r, qual, 'import'])
                    if a.name == 'pddlstream' or a.name.startswith('pddlstream.'):
                        pddl_importers.append([r, qual, a.name])
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'solve':
                solve_sites.append([r, qual])
        _walk_scoped(tree, on)
    facts.append({'fact': 3, 'subject': 'from pybullet import ...', 'sites': sorted(from_pyb)})
    facts.append({'fact': 4, 'subject': 'aliased import of a rebound name', 'sites': sorted(aliased)})
    plan_args = None
    for node in trees['pddlstream_planner.py'].body:
        if isinstance(node, ast.ClassDef) and node.name == 'PDDLStreamPlanner':
            for n in node.body:
                if isinstance(n, ast.FunctionDef) and n.name == 'plan':
                    a = n.args
                    plan_args = ([x.arg for x in a.posonlyargs + a.args]
                                 + (['*' + a.vararg.arg] if a.vararg else [])
                                 + [x.arg for x in a.kwonlyargs] + (['**' + a.kwarg.arg] if a.kwarg else []))
    facts.append({'fact': 5, 'subject': 'solve( call sites', 'sites': sorted(solve_sites),
                  'plan_parameters': plan_args})
    # 6: names the tests patch on test_full_pipeline, and whether tfp still reads them.
    test_files = sorted((REPO / 'tests').rglob('*.py')) + sorted((REPO / 'tampura_bridge' / 'tests').rglob('*.py'))
    patched = {}
    for tf in test_files:
        tree = _parse(tf)
        alias = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name == 'test_full_pipeline':
                        alias.add(a.asname or a.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in ('setattr', 'object') or len(node.args) < 1:
                continue
            a0 = node.args[0]
            if isinstance(a0, ast.Name) and a0.id in alias and len(node.args) >= 2 \
                    and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                patched.setdefault(node.args[1].value, set()).add(rel(tf))
            elif isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                    and a0.value.startswith('test_full_pipeline.'):
                patched.setdefault(a0.value.split('.', 1)[1], set()).add(rel(tf))
    tfp_loads = set()
    for node in ast.walk(trees['test_full_pipeline.py']):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            tfp_loads.add(node.id)
    facts.append({'fact': 6, 'subject': 'names tests patch on test_full_pipeline',
                  'names': [[n, n in tfp_loads] for n in sorted(patched)]})
    facts.append({'fact': 7, 'subject': 'importers of test_full_pipeline and pddlstream',
                  'test_full_pipeline': sorted(tfp_importers), 'pddlstream': sorted(pddl_importers)})
    out.json('facts.json', facts)
    out.json('INFO_lines.json', info)
    out.json('INFO_patching_tests.json', {n: sorted(v) for n, v in sorted(patched.items())})
    out.note('the rebound list is gate_hooks.install (tampura_bridge/gate_hooks.py:621-667) written out here; '
             'sites lists are [file, qualname] sorted (from a walk); line numbers only in INFO_* files, '
             'which are not compared')
    out.note('fact 6 reads tests/**/*.py and tampura_bridge/tests/**/*.py: setattr(X, "name", ...) and '
             'patch.object(X, "name") on an alias X of test_full_pipeline, and "test_full_pipeline.name" strings')


# ----- pin 43: import block ------------------------------------------------

@pin('low', 'p43_import_block', 'P43: test_full_pipeline.py from the first statement after the docstring to the first def, as text')
def p43_import_block(out):
    path = REPO / 'test_full_pipeline.py'
    text = path.read_text(encoding='utf-8')
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    body = tree.body
    doc = body[0] if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                      and isinstance(body[0].value.value, str)) else None
    first = body[1] if doc is not None else body[0]
    first_def = next(n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    def_line = min([first_def.lineno] + [d.lineno for d in first_def.decorator_list])
    frozen = ''.join(lines[first.lineno - 1:def_line - 1])
    out.text('frozen_block.py.txt', frozen)
    stmts = [n for n in body if first.lineno <= n.lineno < def_line]
    out.json('block.json', {'n_lines': frozen.count('\n'), 'sha256': text_digest(frozen),
                            'first_def': first_def.name,
                            'docstring_sha256': text_digest(''.join(lines[:first.lineno - 1])),
                            'statements': [[type(n).__name__, ast.get_source_segment(text, n)] for n in stmts]})
    out.json('INFO_lines.json', {'first_statement_line': first.lineno, 'first_def_line': def_line,
                                 'docstring_end_line': doc.end_lineno if doc else None})
    out.note('text read with universal newlines; frozen_block.py.txt holds the text byte for byte (comments '
             'and blank lines included); docstring_sha256 covers the lines before the block (open point: '
             'whether the module docstring is frozen); line numbers only in INFO_lines.json')


# ----- pin 44: loggers and globals -----------------------------------------

_DESCRIBE = r'''
import importlib, json, sys, types
name, names = sys.argv[1], json.loads(sys.argv[2])
try:
    mod = importlib.import_module(name)
except Exception as ex:
    print('@@JSON ' + json.dumps({'import_error': type(ex).__name__ + ': ' + str(ex)}))
    raise SystemExit(0)
def describe(n):
    if not hasattr(mod, n):
        return '<not bound at import>'
    o = getattr(mod, n)
    if isinstance(o, types.ModuleType):
        return 'module ' + o.__name__
    if isinstance(o, (bool, int, float, complex, type(None))):
        return type(o).__name__ + ' ' + repr(o)
    if isinstance(o, str):
        return 'str ' + (repr(o) if len(o) <= 120 else 'len %d' % len(o))
    if isinstance(o, type) or callable(o) and hasattr(o, '__qualname__'):
        return '%s %s.%s' % (type(o).__name__, getattr(o, '__module__', None), getattr(o, '__qualname__', None))
    return 'instance of %s.%s' % (type(o).__module__, type(o).__qualname__)
print('@@JSON ' + json.dumps({n: describe(n) for n in names}))
'''


@pin('low', 'p44_loggers_globals', 'P44: logger per logging call and the globals each function reads, with what they are at import')
def p44_loggers_globals(out):
    import builtins
    import symtable
    builtin_names = set(dir(builtins))
    loggers, globals_, frees, used = {}, {}, {}, {}
    mods = sorted(REPO.glob('*.py'))
    for path in mods:
        r = rel(path)
        modname = path.stem
        src = path.read_text(encoding='utf-8')
        tree = ast.parse(src)
        module_loggers = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and ast.unparse(node.value.func) == 'logging.getLogger':
                a = node.value.args
                lname = ('<root>' if not a else modname if ast.unparse(a[0]) == '__name__'
                         else a[0].value if isinstance(a[0], ast.Constant) else f'<{ast.unparse(a[0])}>')
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        module_loggers[t.id] = lname

        def on(node, qual, r=r, modname=modname, module_loggers=module_loggers):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _LEVELS):
                return
            recv = ast.unparse(node.func.value)
            if recv == 'logging' or recv == 'logging.getLogger()':
                lname = '<root>'
            elif recv == 'logging.getLogger(__name__)':
                lname = modname
            elif recv in module_loggers:
                lname = module_loggers[recv]
            else:
                return
            loggers.setdefault(f'{r}::{qual}', []).append([node.func.attr, recv, lname])
        _walk_scoped(tree, on)
        top = symtable.symtable(src, str(path), 'exec')

        seen = {}

        def walk(tab, prefix):
            for ch in tab.get_children():
                q = f'{prefix}.{ch.get_name()}' if prefix else ch.get_name()
                seen[q] = seen.get(q, 0) + 1
                if seen[q] > 1:
                    q = f'{q}#{seen[q]}'
                if ch.get_type() == 'function':
                    g = sorted(n for n in ch.get_globals() if n not in builtin_names)
                    if g:
                        globals_[f'{r}::{q}'] = g
                        used.setdefault(modname, set()).update(g)
                    fr = sorted(ch.get_frees())
                    if fr:
                        frees[f'{r}::{q}'] = fr
                walk(ch, q)
        walk(top, '')
    described = {}
    for modname in sorted(used):
        p = subprocess.run([sys.executable, '-c', _DESCRIBE, modname, json.dumps(sorted(used[modname]))],
                           capture_output=True, text=True, timeout=180, cwd=os.getcwd())
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith('@@JSON ')), None)
        described[modname] = (json.loads(line[7:]) if line else
                              {'no_output': f'rc {p.returncode}', 'stderr_tail': p.stderr[-400:]})
    out.json('loggers.json', {k: loggers[k] for k in sorted(loggers)})
    out.json('globals.json', {k: globals_[k] for k in sorted(globals_)})
    out.json('free_variables.json', {k: frees[k] for k in sorted(frees)})
    out.json('globals_described.json', described)
    out.note('root modules only; symtable globals of every function (builtins left out) and free variables '
             'of closures, each list sorted (symtable returns sets); globals_described: each module imported '
             'in a fresh interpreter (cwd the work folder) and every global name its functions read described '
             'as type plus module.qualname (functions, classes), repr (numbers, short strings) or the type of '
             'an instance; loggers: per function in source order [level, receiver, logger name]')
    out.note('this pin stores the table; the identity check across old and new modules after a move '
             '(new_mod.x is old_mod.x) is a runtime step of each cut, not done here')


# ----- pin 45: fresh imports -----------------------------------------------

_FRESH = r'''
import importlib, json, logging, os, sys
repo, name = sys.argv[1], sys.argv[2]
err = None
try:
    importlib.import_module(name)
except BaseException as ex:
    err = type(ex).__name__ + ': ' + str(ex)
order = list(sys.modules)
def in_repo(m):
    f = getattr(sys.modules.get(m), '__file__', None) or ''
    return os.path.abspath(f).startswith(repo + os.sep)
repo_mods = [m for m in order if in_repo(m)]
sf = sys.modules.get('slip_fixes')
cu = sys.modules.get('console_ui')
res = {'import_error': err, 'sys_path': sys.path, 'repo_modules_in_order': repo_mods,
       'slip_fixes_KNOWN': list(sf.KNOWN) if sf else None,
       'root_handlers': [type(h).__module__ + '.' + type(h).__name__ for h in logging.getLogger().handlers],
       'console_installed': (cu._console is not None) if cu else None,
       'console_ui_before_pybullet': (order.index('console_ui') < order.index('pybullet'))
                                     if ('console_ui' in order and 'pybullet' in order) else None,
       'pybullet_loaded': 'pybullet' in order}
print('@@JSON ' + json.dumps(res))
'''


@pin('low', 'p45_fresh_imports', 'P45: each root module and tampura_bridge.policy imported first in a fresh interpreter', timeout=1200)
def p45_fresh_imports(out):
    tw = '/root/tampura-work'
    masker = Masker([(REPO, '<REPO>'), (tw, '<TW>')])
    res = {}
    mods = [p.stem for p in sorted(REPO.glob('*.py'))] + ['tampura_bridge.policy']
    for m in mods:
        env = dict(os.environ)
        if m.startswith('tampura_bridge'):
            env['PYTHONPATH'] = ':'.join([str(REPO), str(REPO / 'pddlstream_lib'), f'{tw}/tampura',
                                          f'{tw}/tampura_environments'])
        p = subprocess.run([sys.executable, '-c', _FRESH, str(REPO), m], capture_output=True, text=True,
                           timeout=180, cwd=os.getcwd(), env=env)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith('@@JSON ')), None)
        res[m] = json.loads(masker(line[7:])) if line else {'no_output': f'rc {p.returncode}',
                                                           'stderr_tail': masker(p.stderr[-600:])}
    out.json('fresh_imports.json', res)
    p = subprocess.run([sys.executable, str(REPO / 'test_full_pipeline.py'), '--no-gui', '--help'],
                       capture_output=True, text=True, timeout=180, cwd=os.getcwd())
    out.json('entry_help.json', {'rc': p.returncode, 'stdout_sha256': text_digest(p.stdout),
                                 'stdout_lines': len(p.stdout.splitlines()), 'stderr': masker(p.stderr),
                                 'home_cache_written': (Path.home() / '.cache' / 'semantic_boxels').exists()})
    out.note('one `python -c` per module, cwd the work folder, HOME the work folder, PYTHONHASHSEED=0; '
             'tampura_bridge.policy with PYTHONPATH as run.ps1:149-151 (<TW> = /root/tampura-work); '
             'sys.modules order and slip_fixes.KNOWN order kept (order is the point); repo modules = those '
             'whose __file__ lies in the repo')
    out.note('entry_help: python test_full_pipeline.py --no-gui --help (the --help path installs no console)')


# ----- pin 48: twin constants ----------------------------------------------

@pin('low', 'p48_twin_constants', 'P48: the numbers written in several places (REVIEW 3.6), each site with its context (AST)')
def p48_twin_constants(out):
    from collections import Counter
    sites, info = [], []

    def stmt_text(src_lines, node):
        return src_lines[node.lineno - 1].strip()
    for path in repo_py_files():
        r = rel(path)
        src = path.read_text(encoding='utf-8')
        src_lines = src.splitlines()
        tree = ast.parse(src)

        def add(name, node, qual, value):
            sites.append([name, r, qual, stmt_text(src_lines, node), value])
            info.append([name, r, qual, node.lineno])

        def on(node, qual):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float):
                v = node.value
                if v == 0.005 and r in ('execution.py', 'streams.py'):
                    add('5 mm (grasp height and look-alikes)', node, qual, v)
                if v == 1.96:
                    add('1.96 interval', node, qual, v)
                if v in (900, 900.0, 1800, 1800.0):
                    add('900 s / 1800 s caps', node, qual, v)
                if v == 0.0005 and r == 'robot_utils.py':
                    add('squeeze module default', node, qual, v)
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) \
                    and isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant) \
                    and node.right.value in (240, 240.0):
                add('time step 1/240', node, qual, ast.unparse(node))
            if isinstance(node, ast.Call):
                consts = [a.value for a in node.args if isinstance(a, ast.Constant)]
                if 'grip_squeeze_mm' in consts or '--grip-squeeze-mm' in consts:
                    vals = [ast.unparse(a) for a in node.args[1:]] + \
                           [f'{k.arg}={ast.unparse(k.value)}' for k in node.keywords if k.arg == 'default']
                    add('squeeze 0.5 mm', node, qual, vals)
            if r == 'console_ui.py':
                t = _template(node) if isinstance(node, (ast.Constant, ast.JoinedStr)) else None
                if t and ('of 3' in t or '/3' in t):
                    add('"of 3" console pattern', node, qual, t)
        _walk_scoped(tree, on)
    multi = Counter((s[0], s[1], s[2], s[3], json.dumps(s[4])) for s in sites)
    out.json('twins.json', [[k[0], k[1], k[2], k[3], json.loads(k[4]), multi[k]] for k in sorted(multi)])
    sb = []
    for f in sorted(list(REPO.glob('*.sbatch')) + list((REPO / 'tools' / 'cluster').glob('*.sbatch'))):
        for ln in f.read_text(encoding='utf-8', errors='replace').splitlines():
            if '900' in ln or '1800' in ln:
                sb.append([rel(f), ln.strip()])
    out.json('sbatch_caps.json', sb)
    out.json('INFO_lines.json', info)
    out.note('twins.json: [constant, file, qualname, the source line, value, count] sorted (a multiset); '
             'scope as pin 39; 5 mm only in execution.py and streams.py (all sites, look-alikes too); '
             'line numbers only in INFO_lines.json; sbatch_caps.json: lines with 900 or 1800 in root and '
             'tools/cluster *.sbatch files')

#@@LOW_PINS@@


if __name__ == '__main__':
    sys.exit(main())
