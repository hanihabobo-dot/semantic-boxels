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
episode) with the same ``@pin`` decorator.  ``world`` (the world and its
sensing, index phase0/index/pins_world.md): scenes, first observation,
shadows, plan twin, init facts, streams, motion step counts, the stored eye
renders of tests/readable/make_render_fixture.py (pins 13 to 16), one
scripted pick, the bridge's pure parts and the find_dice scene files.
``episode`` (whole episodes and episode starts through
tools/readable/record_episode.py, index phase0/index/episode_path.md): pin
30's real runs, pin 34's starts, pin 46's bridge starts and pin 47's
replays of tapes recorded live on the checkpoint (READABLE_TAPES).
``console`` (pin 27, tools/readable/console_replay.py): recorded runs (two
archived bridge runs, the pin 47 tapes' live runs with READABLE_TAPES) and
the made tapes of R's plan review S-d, played through the real Console with
its terminal a pipe, in four environment sets.
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

# Gate 7, REVIEW_PHASE0 item 5 (R's rule 4 as amended, PLAN 5.1): the last NOTES line of every pin
# of group low (run_child).  The check behind it is WP-A's (record, item 9): every low pin run
# with the children's PYTHONHASHSEED=1 gave the same outputs as under 0.
LOW_ORDER_NOTE = ("lists compared in an order that comes from a set (R's rule 4 as amended, REVIEW_PHASE0 "
                  "item 5): none in this pin's outputs; at gate 7 every low pin gave the same outputs under "
                  "PYTHONHASHSEED=1 as under 0 (plain() refuses a set, so the pin sorts any set it writes)")

# Gate 7, SPEC D10 (REVIEW_PHASE0 item 1, R_PHASE0 3.1): the one NOTES line of pins 41, 44 and 48.
D10_NOTE = ("D10 (REVIEW_PHASE0 item 1): {} use the old code's file and qualname, and the stored outputs keep "
            "those names; the compare maps a new name back through MIGRATION_MAP.tsv (due before P2)")

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

# SPEC D11 (C10, R_PHASE0 "G1 and G2 read" point 1): a pin child runs with its work folder as
# the working directory, so the READABLE variables it reads (TAPES_VAR, RENDER_FIXTURE_VAR) are
# made absolute in the parent, against the parent's working directory, before any child starts,
# and a value that names no existing path is refused.  The tests resolve READABLE_GOLDEN (read
# in the parent) with the same function.  Every default path is built from REPO.
GOLDEN_VAR = 'READABLE_GOLDEN'


class ReadablePathError(ValueError):
    """A READABLE variable names a path that does not exist."""


def readable_path(var, environ=None, cwd=None):
    """The path the variable var names, made absolute against cwd (default: this process's
    working directory) and resolved; None when var is unset or empty.  A value naming no
    existing path is refused with ReadablePathError."""
    value = (os.environ if environ is None else environ).get(var)
    if not value:
        return None
    base = Path(os.getcwd() if cwd is None else cwd)
    path = (base / value).resolve()
    if not path.exists():
        raise ReadablePathError(f'{var}={value!r} names {path}, which does not exist (a relative value is '
                                f'taken against the working directory {base})')
    return path


def child_paths(environ=None, cwd=None):
    """{variable: absolute path} for the READABLE variables a pin child reads that are set
    (readable_path refuses a missing one)."""
    paths = {}
    for var in (TAPES_VAR, RENDER_FIXTURE_VAR):
        path = readable_path(var, environ, cwd)
        if path is not None:
            paths[var] = str(path)
    return paths


def child_env(work, paths=None):
    """The environment of a pin child; paths (default: child_paths()) replaces the READABLE
    variables by their absolute values."""
    env = dict(os.environ)
    for k in ('FORCE_COLOR', 'NO_COLOR', 'SB_CONSOLE_ASCII', 'SB_AUDIO', 'SB_VOICE',
              'PYTHONSTARTUP', 'PYTHONINSPECT', 'BOXEL_EYE_IMAGES'):
        env.pop(k, None)
    env.update({'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1',
                'HOME': str(work), 'COLUMNS': '80', 'LINES': '24',
                'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'TERM': 'dumb',
                'MPLBACKEND': 'Agg', 'PYTHONPATH': str(REPO),
                'PYTHONIOENCODING': 'utf-8'})
    env.update(child_paths() if paths is None else paths)
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
        if group == 'low':
            o.note(LOW_ORDER_NOTE)
        o.close()
        return 0
    except Exception:
        o.close()
        (folder / "ERROR.txt").write_text(masker(traceback.format_exc()),
                                          encoding='utf-8', newline='\n')
        return 1


def run_group(group, out_dir, only=None, log=print):
    paths = child_paths()              # D11: before any child starts (and before --out is made)
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
                 '--out', str(out)], cwd=str(work), env=child_env(work, paths),
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
    try:
        return run_group(a.group, a.out, only)
    except ReadablePathError as ex:
        ap.error(str(ex))


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
    _p08_look(out, m, live)


def _p08_look(out, m, live):
    """Gate 7 (INDEX_PINS P2): the two generated look domain files, as pin 8 keeps the M8 file."""
    import look_domain as look
    shas = {}
    for mode in look.MODES:
        path = look.GENERATED_FILES[mode]
        generated = look.generate(live, mode)
        raw = Path(path).read_bytes()
        shas[mode] = {'file': rel(path), 'generated_equals_file': generated == look.read(path),
                      'sha_generate_live': look.sha(generated), 'sha_read': look.sha(look.read(path)),
                      'raw_bytes': {'sha256': hashlib.sha256(raw).hexdigest(), 'has_crlf': b'\r\n' in raw,
                                    'sha256_crlf_to_lf': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()}}
        out.text(f'generated_look_{mode}.pddl', generated)
    out.json('look_shas.json', shas)
    values = _flag_specs(('--look',))['--look']['choices'] + ['nowhere']
    files = {'mode_of': [{'look': v, **outcome(look.mode_of, v)} for v in values + [True, False, None]],
             'domain_file': []}
    for v in values:
        for m8_on in (True, False):
            r = outcome(look.domain_file, v, m8_on)
            if 'value' in r:
                r['value'] = rel(r['value'])
            files['domain_file'].append({'look': v, 'm8_on': m8_on, **r})
    out.json('look_files.json', files)
    # The anchors of the look delta: the constants generate() passes to _once, in source order.
    tree = ast.parse((REPO / 'look_domain.py').read_text(encoding='utf-8'))
    gen = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'generate')
    calls = sorted((n for n in ast.walk(gen) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == '_once'), key=lambda n: (n.lineno, n.col_offset))
    anchors = [(c.args[1].id, c.args[2].value) for c in calls]
    m8_text = m.generate(live)
    real = look.m8_domain.generate
    neg = []
    for mode in look.MODES:
        for name, what in anchors:
            anchor = getattr(look, name)
            for case, text in (('removed', m8_text.replace(anchor, '', 1)),
                               ('twice', m8_text.replace(anchor, anchor + anchor, 1))):
                look.m8_domain.generate = lambda _live, t=text: t
                try:
                    r = outcome(look.generate, live, mode)
                finally:
                    look.m8_domain.generate = real
                if 'value' in r:
                    r = {'sha': look.sha(r.pop('value')), **r}
                neg.append({'mode': mode, 'anchor': name, 'what': what, 'case': case, **r})
    out.json('negative_look.json', neg)
    out.note('look_shas.json (gate 7, INDEX_PINS P2): for each mode of look_domain.MODES its file of '
             'look_domain.GENERATED_FILES: generate(live, mode) against the file as read (look_domain.read, '
             'universal newlines), the sha of both, the raw bytes as for the three files above (the two look files '
             'are CRLF in a Windows working tree and LF in the index, SPEC section 3: has_crlf says which); '
             'generated_look_<mode>.pddl: the generated text')
    out.note('look_files.json: look_domain.mode_of for each --look choice (read from run_logger.py\'s syntax tree), '
             'a value outside them, True, False and None; look_domain.domain_file for each of those strings with '
             'm8_on True and False (paths relative to the checkout)')
    out.note('negative_look.json: the anchors of the look delta are the module constants look_domain.generate '
             'passes to _once (read from its syntax tree, in source order); for each mode and anchor, '
             'm8_domain.generate is replaced for one call by a stand-in that returns its text of the live file with '
             'the anchor removed once or written twice, and look_domain.generate\'s answer is kept (a text as its '
             'sha)')


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


# Gate 7 (INDEX_PINS P1, PLAN 5.2 rows 22, 23, 32, SPEC D2): the five flags the parser gained
# since refactor-checkpoint-1, their choices read from its syntax tree; the F and R strings read
# from wave 2's declaration by text; the harness's command for arm O, caught at its Popen; the
# bridge driver's switches and the argv policy.py builds from them, by slices of their syntax
# trees executed (as pin 23 does with the __main__ block); and REVIEW_PHASE0 item 2, the eval
# presets' cell_to_argv lists through parse_pipeline_args.

TAG2_FLAGS = ('--look', '--eye', '--eye-start-joints', '--interior-regions', '--m7')
DECLARATION_WAVE2 = 'archive/tampura_bridge_plan_2026-10-25/tracks/evalfinal/wave2/DECLARATION.md'
DRIVER = 'tampura_bridge/run_bridge_on_finddice.py'


def git_blob_sha1(data):
    """The hash git gives these bytes as a text blob under core.autocrlf=true (CRLF stored as LF),
    so the same on a CRLF and on an LF checkout."""
    lf = data.replace(b'\r\n', b'\n')
    return hashlib.sha1(b'blob %d\x00' % len(lf) + lf).hexdigest()


def declared_o_args():
    """({'F': .., 'R': ..}, source) from wave 2's declaration (D2): for each arm the one line that
    starts it ('- F,', '- R,'), which must run arm O ('P4_ARMS=O,'), and the one value inside
    P4_O_ARGS='...' on that line; any other count fails.  source: the path and the blob hash."""
    import re
    data = (REPO / DECLARATION_WAVE2).read_bytes()
    found = {}
    for arm in ('F', 'R'):
        lines = [ln for ln in data.decode('utf-8').splitlines() if ln.startswith(f'- {arm},')]
        if len(lines) != 1:
            raise LookupError(f'{DECLARATION_WAVE2}: {len(lines)} lines start the {arm} arm, not one')
        if 'P4_ARMS=O,' not in lines[0]:
            raise LookupError(f'{DECLARATION_WAVE2}: the {arm} line does not run arm O: {lines[0]!r}')
        values = re.findall(r"P4_O_ARGS='([^']*)'", lines[0])
        if len(values) != 1:
            raise LookupError(f"{DECLARATION_WAVE2}: {len(values)} P4_O_ARGS='...' on the {arm} line, not one")
        found[arm] = values[0]
    return found, {'path': DECLARATION_WAVE2, 'git_blob_sha1': git_blob_sha1(data)}


def _flag_specs(flags):
    """{flag: {'choices', 'default'}} of the add_argument calls in run_logger.parse_pipeline_args,
    read from its syntax tree; a flag without such a call fails."""
    tree = ast.parse((REPO / 'run_logger.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'parse_pipeline_args')
    specs = {}
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'add_argument' and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value in flags):
            kw = {k.arg: k.value for k in node.keywords}
            specs[node.args[0].value] = {
                'choices': ast.literal_eval(kw['choices']) if 'choices' in kw else None,
                'default': ast.literal_eval(kw['default']) if 'default' in kw else None}
    missing = [f for f in flags if f not in specs]
    if missing:
        raise LookupError(f'run_logger.parse_pipeline_args has no add_argument for {missing}')
    return {f: specs[f] for f in flags}


def _module_literal(path, name):
    """The value of the one module-level assignment to name in path, by ast.literal_eval."""
    tree = ast.parse((REPO / path).read_text(encoding='utf-8'))
    vals = [ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    if len(vals) != 1:
        raise LookupError(f'{path} binds {name} {len(vals)} times at module level, not once')
    return vals[0]


def _writes_keys(st, target):
    """True for a statement that only adds keys to the dict whose source text is target: an
    assignment to target[...], or an if statement whose branches hold only such statements."""
    if isinstance(st, ast.Assign):
        return all(isinstance(t, ast.Subscript) and ast.unparse(t.value) == target for t in st.targets)
    if isinstance(st, ast.If):
        return all(_writes_keys(s, target) for s in st.body + st.orelse)
    return False


def harness_argv_arm_o(o_args, seed=140):
    """(ARM_O, the command) the paper's harness builds for arm O with the declared string o_args:
    tools/gen_scene_eval.py's ARM_O (read from its syntax tree) and tuple(shlex.split(o_args)), as
    its run_one passes them with P4_SHOTS=none (so no --save-screenshots), handed to
    tools/slip_eval.run_episode, whose subprocess.Popen is replaced by one that keeps the command
    and stops the call: no process starts.  The python and the snapshot are the placeholders
    <PYTHON> and <SNAPSHOT>; the save directory is relative to the work folder."""
    import shlex
    import types
    arm_o = _module_literal('tools/gen_scene_eval.py', 'ARM_O')
    saved = list(sys.path)
    try:
        se = sys.modules.get('slip_eval') or _load_tool('slip_eval')
    finally:
        sys.path[:] = saved

    class _Caught(Exception):
        pass
    seen = {}

    def popen(cmd, **kw):
        seen['cmd'] = list(cmd)
        raise _Caught
    real = se.subprocess
    se.subprocess = types.SimpleNamespace(Popen=popen, TimeoutExpired=subprocess.TimeoutExpired,
                                          STDOUT=subprocess.STDOUT, PIPE=subprocess.PIPE)
    try:
        ns = types.SimpleNamespace(out='harness', python='<PYTHON>', snapshot='<SNAPSHOT>', cwd='.', cap=900)
        try:
            se.run_episode(ns, arm_o, seed, 1, extra_args=tuple(shlex.split(o_args)))
        except _Caught:
            pass
    finally:
        se.subprocess = real
    if 'cmd' not in seen:
        raise LookupError('tools/slip_eval.run_episode reached no Popen')
    return arm_o, seen['cmd']


def driver_config(driver_argv):
    """(cfg, policy_argv, after) for the bridge driver started with driver_argv.  Its main()'s
    statements from 'ap = argparse.ArgumentParser()' through 'a = ap.parse_args()' run with
    sys.argv = [the driver's file name] + driver_argv (bridge_policy stands in by its DRAW_KINDS,
    read from policy.py's syntax tree; it feeds one help text); the keywords log_level,
    max_plan_time and switches of its one EpisodeConfig(...) call are evaluated, and the statements
    right after that call that only add keys to cfg.switches run (after: their first lines).
    policy_argv: the argument of policy.py's one parse_pipeline_args(...) call, evaluated with
    that cfg.  exec and eval here run the repository's own code (the reference under the pin,
    read from its files), as pin 23 runs its slice of the __main__ block."""
    import argparse as argparse_mod
    import types
    import slip_fixes
    body = next(n for n in ast.parse((REPO / DRIVER).read_text(encoding='utf-8')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'main').body
    texts = [ast.unparse(s) for s in body]
    starts = [i for i, t in enumerate(texts) if t.startswith('ap = argparse.ArgumentParser(')]
    ends = [i for i, t in enumerate(texts) if t == 'a = ap.parse_args()']
    cfgs = [i for i, s in enumerate(body) if isinstance(s, ast.Assign) and texts[i].startswith('cfg = ')
            and isinstance(s.value, ast.Call) and ast.unparse(s.value.func) == 'bridge_policy.EpisodeConfig']
    if not (len(starts) == len(ends) == len(cfgs) == 1 and starts[0] < ends[0] < cfgs[0]):
        raise LookupError(f'{DRIVER} main(): parser {starts} .. {ends}, EpisodeConfig {cfgs}: not one each in order')
    ns = {'argparse': argparse_mod, 'os': os, 'time': time,
          'bridge_policy': types.SimpleNamespace(
              DRAW_KINDS=_module_literal('tampura_bridge/policy.py', 'DRAW_KINDS'))}
    saved = sys.argv
    sys.argv = [Path(DRIVER).name] + list(driver_argv)
    try:
        exec(compile(ast.Module(body=body[starts[0]:ends[0] + 1], type_ignores=[]), DRIVER, 'exec'), ns)
    finally:
        sys.argv = saved
    kw = {k.arg: k.value for k in body[cfgs[0]].value.keywords}
    env = {'a': ns['a'], 'slip_fixes': slip_fixes}
    cfg = types.SimpleNamespace(**{k: eval(compile(ast.Expression(body=kw[k]), DRIVER, 'eval'), env)
                                   for k in ('log_level', 'max_plan_time', 'switches')})
    after = []
    for st in body[cfgs[0] + 1:]:
        if not _writes_keys(st, 'cfg.switches'):
            break
        after.append(st)
    exec(compile(ast.Module(body=after, type_ignores=[]), DRIVER, 'exec'), {'a': ns['a'], 'cfg': cfg})
    calls = [n for n in ast.walk(ast.parse((REPO / 'tampura_bridge' / 'policy.py').read_text(encoding='utf-8')))
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == 'parse_pipeline_args']
    if len(calls) != 1 or len(calls[0].args) != 1:
        raise LookupError(f'tampura_bridge/policy.py: {len(calls)} parse_pipeline_args(...) calls, not one')
    policy_argv = eval(compile(ast.Expression(body=calls[0].args[0]), 'tampura_bridge/policy.py', 'eval'),
                       {'cfg': cfg})
    return cfg, policy_argv, [ast.unparse(s).splitlines()[0] for s in after]


def _cli_corpus_tag2(specs, declared):
    """(name, argv, None) for the five flags: each choice, one value outside the choices, the free
    text of --eye-start-joints empty and as a list; --eye arm without and with a look; the
    declared F and R strings alone."""
    import shlex
    cases = []
    for flag, spec in specs.items():
        stem = flag[2:].replace('-', '_')
        if spec['choices']:
            cases += [(f'{stem}_{c}', [flag, c], None) for c in spec['choices']]
            cases.append((f'{stem}_bad_choice', [flag, 'nowhere'], None))
        else:
            cases += [(f'{stem}_empty', [flag, ''], None),
                      (f'{stem}_list', [flag, '0,-0.5,0,-2,0,1.5,0.8'], None)]
    cases += [('eye_arm_without_look', ['--eye', 'arm'], None),
              ('look_boxel_eye_arm', ['--look', 'boxel', '--eye', 'arm'], None),
              ('declared_F', shlex.split(declared['F']), None),
              ('declared_R', shlex.split(declared['R']), None)]
    return cases


def _compact(lines, limit=100):
    """pin 31's form for a list of JSON lines: the count, the sha256 of the lines joined by
    newlines, and the lines, or the first and the last 20 of more than limit."""
    entry = {'n': len(lines), 'sha256': text_digest('\n'.join(lines))}
    if len(lines) <= limit:
        entry['lines'] = lines
    else:
        entry['first'], entry['last'] = lines[:20], lines[-20:]
    return entry


def _bridge_configs():
    """[(name, o_args)]: arm O alone, then the declared F and R strings."""
    declared, _ = declared_o_args()
    return [('O', ''), ('F', declared['F']), ('R', declared['R'])]


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
    # Gate 7: the tag's flags, the F and R strings, the bridge's argv, the eval cells.
    import eval_runner as er
    specs = _flag_specs(TAG2_FLAGS)
    declared, source = declared_o_args()
    cases = [{'case': name, 'argv': argv, 'sys_argv_rest': sys_rest, **_parse_case(rl, argv, sys_rest)}
             for name, argv, sys_rest in _cli_corpus_tag2(specs, declared)]
    bridge = []
    for name, o_args in _bridge_configs():
        arm_o, cmd = harness_argv_arm_o(o_args)
        cfg, policy_argv, after = driver_config(cmd[2:])
        bridge.append({'config': name, 'o_args': o_args, 'arm_o': arm_o, 'harness_cmd': cmd,
                       'cfg_switches_keys_in_order': list(cfg.switches),
                       'cfg': {'log_level': cfg.log_level, 'max_plan_time': cfg.max_plan_time,
                               'switches': cfg.switches},
                       'statements_after_cfg': after, 'policy_argv': policy_argv,
                       **_parse_case(rl, policy_argv, cmd[2:], prog=Path(DRIVER).name)})
    out.json('cli_tag2.json', {'flags': specs, 'declared': declared, 'cases': cases, 'bridge': bridge})
    cells = {}
    for preset, matrix in er.MATRIX_PRESETS.items():
        lines = []
        for c in er.iterate_matrix(matrix):
            argv = er.cell_to_argv(c, [])[1:]
            lines.append(json.dumps(plain([er.cell_tag(c), _parse_case(rl, argv[1:], None, prog=argv[0])]),
                                    ensure_ascii=False))
        cells[preset] = _compact(lines)
    out.json('cell_argv.json', cells)
    out.note('cli_tag2.json (gate 7, INDEX_PINS P1): flags: the add_argument calls of the five flags added '
             'since refactor-checkpoint-1 (' + ', '.join(TAG2_FLAGS) + '), choices and default read from '
             'run_logger.py\'s syntax tree; cases: each choice, a value outside the choices, the free text of '
             '--eye-start-joints, --eye arm without a look (the parser takes it; main refuses it), and the '
             'declared F and R strings alone; parsed as in cli.json')
    out.note(f'declared: the P4_O_ARGS strings of the F and R arms read by text from {source["path"]} '
             f'(git blob {source["git_blob_sha1"]}): the one line that starts each arm, the one value '
             'inside P4_O_ARGS=\'...\' (D2)')
    out.note('bridge: for arm O alone, F and R: harness_cmd is the command tools/slip_eval.run_episode builds '
             'for ARM_O of tools/gen_scene_eval.py with tuple(shlex.split(o_args)) (P4_SHOTS=none: no '
             '--save-screenshots), caught at its Popen; cfg: the bridge driver\'s main() from its ArgumentParser '
             'through parse_args() run on harness_cmd[2:], then EpisodeConfig\'s log_level, max_plan_time and '
             'switches (keys in their insertion order) and the statements after it that add keys to '
             'cfg.switches; policy_argv: the argument of policy.py\'s parse_pipeline_args call evaluated with '
             'that cfg; parsed with sys.argv = [run_bridge_on_finddice.py] + harness_cmd[2:]')
    out.note('cell_argv.json (REVIEW_PHASE0 item 2): every cell of every eval_runner preset, '
             'cell_to_argv(cell, [])[2:] through parse_pipeline_args with sys.argv = cell_to_argv(cell, [])[1:]; '
             'per preset pin 31\'s form: count, sha256 of the lines, the lines or the first and last 20 of more '
             'than 100 (one compact JSON [tag, parse] per line)')


# ----- pin 23: run_config --------------------------------------------------

def _main_block_slice(tree, first_text, last_target):
    """The statements of the __main__ block from the one whose source starts
    with first_text through the assignment to last_target and the statements
    right after it that only add keys to last_target (D9: the tag adds
    run_config["eye"] in an if statement after the dict)."""
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
    while end + 1 < len(body) and _writes_keys(body[end + 1], last_target):
        end += 1
    return body[start:end + 1]


def _run_config_case(rl, tfp, code, name, argv):
    """One row of pin 23: the parse, then the slice executed with those args."""
    p = _parse_case(rl, argv, None)
    if 'value' not in p:
        return {'case': name, 'parse': p}
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
    return row


@pin('low', 'p23_run_config', 'R23: the __main__ run_config dict for an argv corpus (AST slice executed)')
def p23_run_config(out):
    import run_logger as rl
    import test_full_pipeline as tfp
    src = (REPO / 'test_full_pipeline.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    stmts = _main_block_slice(tree, 'random.seed(args.seed)', 'run_config')
    code = compile(ast.Module(body=stmts, type_ignores=[]), 'test_full_pipeline.py', 'exec')
    out.note('the statements of the __main__ block from "random.seed(args.seed)" through the run_config '
             'assignment and the statements right after it that only add keys to run_config (seeding, '
             'scene_builders, scene_cfg, the tray switch, effective counts, run_config, the "eye" key: D9) '
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
    res = [_run_config_case(rl, tfp, code, name, argv) for name, argv in corpus]
    out.json('run_config.json', res)
    # Gate 7: the tag's flags and the F and R strings (INDEX_PINS P1), the eval cells (REVIEW item 2).
    import shlex
    import eval_runner as er
    specs = _flag_specs(TAG2_FLAGS)
    declared, source = declared_o_args()
    tag2 = [(f'{flag[2:].replace("-", "_")}_{c}', ['--no-gui', flag, c])
            for flag, spec in specs.items() for c in (spec['choices'] or ())]
    tag2 += [('eye_start_joints_list', ['--no-gui', '--eye-start-joints', '0,-0.5,0,-2,0,1.5,0.8']),
             ('look_boxel_eye_arm', ['--no-gui', '--look', 'boxel', '--eye', 'arm']),
             ('look_centred_eye_arm', ['--no-gui', '--look', 'centred', '--eye', 'arm']),
             ('declared_F', ['--no-gui'] + shlex.split(declared['F'])),
             ('declared_R', ['--no-gui'] + shlex.split(declared['R']))]
    out.json('run_config_tag2.json', [_run_config_case(rl, tfp, code, name, argv) for name, argv in tag2])
    cells = {}
    for preset, matrix in er.MATRIX_PRESETS.items():
        cells[preset] = _compact([json.dumps(plain(_run_config_case(rl, tfp, code, er.cell_tag(c),
                                                                    er.cell_to_argv(c, [])[2:])),
                                             ensure_ascii=False) for c in er.iterate_matrix(matrix)])
    out.json('cell_run_config.json', cells)
    out.note('run_config_tag2.json (gate 7, INDEX_PINS P1): --no-gui with each choice of the four flags of '
             + ', '.join(f for f in TAG2_FLAGS if specs[f]['choices']) + ' (read from run_logger.py\'s syntax '
             'tree), --eye-start-joints as a list, --look boxel and centred with --eye arm, and the declared F '
             f'and R strings (read by text from {source["path"]}, git blob {source["git_blob_sha1"]}); rows as '
             'in run_config.json. The slice never runs main(), so --eye arm without a look shows the key that '
             'main would refuse')
    out.note('cell_run_config.json (REVIEW_PHASE0 item 2): every cell of every eval_runner preset, '
             'cell_to_argv(cell, [])[2:] as the argv of a row as in run_config.json, the case named by the '
             'cell tag; per preset pin 31\'s form (count, sha256 of the lines, the lines or the first and last '
             '20 of more than 100)')


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
    done_tag2 = _p30_tag2(out, rl, base, events)
    _p30_exit_reasons(out, [('report.json', [(name, kw, r) for (name, kw), r in zip(cases, res)]),
                            ('report_tag2.json', done_tag2)])


# Pin 30's additions at the tag (INDEX_PINS P7, SPEC D15): the M7 lines over a real
# belief.BeliefState, home_not_reached, and the exit reasons by AST.  New files, so report.json
# stays as it was.
P30_SHADOWS_TAG2 = ('shadow_001', 'shadow_002', 'shadow_003', 'shadow_004')


def _p30_tag2(out, rl, base, events):
    """report_tag2.json: report_run_outcome over a belief.BeliefState that suspend(),
    release_suspended(), mark_sensed(), mark_unresolved() and remove_shadow() brought to each
    case's state at fixed times.  Returns [(case, arguments, outcome)]."""
    import types
    from belief import BeliefState

    def S(sid, bodies, now):
        return ('suspend', (sid,), {'bodies': bodies, 'now': now, 'seconds': 120.0})

    def E(sid):
        return ('mark_sensed', (sid, False), {})

    def U(sid):
        return ('mark_unresolved', (sid,), {})

    def R(now):
        return ('release_suspended', (now,), {})

    m7 = {'m7_suspend_s': 120.0}
    one = [S('shadow_002', {'cup_1': 3}, 10.0)]
    several = [S('shadow_003', {'cup_2': 3, 'cube_b': 4}, 12.5), S('shadow_002', {'cup_1': 3}, 20.0)]
    cases = [
        ('rediscovery_giveup_one', one + [E('shadow_001'), E('shadow_003'), E('shadow_004')], None,
         dict(success=False, exit_reason='rediscovery_giveup', **m7)),
        ('rediscovery_giveup_several', several + [E('shadow_001'), E('shadow_004')], None,
         dict(success=False, exit_reason='rediscovery_giveup', **m7)),
        ('rediscovery_giveup_one_blocked', one + [U('shadow_001'), E('shadow_003'), U('shadow_004')], None,
         dict(success=False, exit_reason='rediscovery_giveup',
              blocked_giveup_shadows={'shadow_004', 'shadow_001'}, **m7)),
        ('rediscovery_giveup_several_blocked', several + [E('shadow_001'), U('shadow_004')], None,
         dict(success=False, exit_reason='rediscovery_giveup', blocked_giveup_shadows={'shadow_004'}, **m7)),
        ('planner_failed_suspended', one + [E('shadow_001')], None,
         dict(success=False, exit_reason='planner_failed', **m7)),
        ('planner_failed_released', one + [E('shadow_001'), R(130.0)], None,
         dict(success=False, exit_reason='planner_failed', **m7)),
        ('planner_failed_m7_off', [E('shadow_001')], None,
         dict(success=False, exit_reason='planner_failed')),
        ('target_lost_suspended', one + [S('shadow_004', {'cube_b': 5}, 40.0), E('shadow_001')], None,
         dict(success=False, exit_reason='target_lost', integrity_events=events, **m7)),
        ('target_lost_no_suspension', [E('shadow_001')], None,
         dict(success=False, exit_reason='target_lost', integrity_events=events, **m7)),
        ('target_lost_m7_off', [E('shadow_001')], None,
         dict(success=False, exit_reason='target_lost', integrity_events=events)),
        ('suspensions_ended', [S('shadow_001', {'cup_1': 3}, 5.0), E('shadow_001'), R(30.0),
                               S('shadow_002', {'cup_2': 3}, 10.0), S('shadow_002', {'cup_2': 4}, 50.0),
                               S('shadow_003', {'cube_b': 3}, 60.0), S('shadow_004', {'cup_1': 3}, 70.0),
                               ('remove_shadow', ('shadow_004',), {}), R(175.0)], None,
         dict(success=False, exit_reason='planner_failed', **m7)),
        ('ledger_t0_1000', [S('shadow_002', {'cup_1': 3}, 1010.0), E('shadow_001'), E('shadow_003'),
                            E('shadow_004')], 1000.0,
         dict(success=False, exit_reason='rediscovery_giveup', **m7)),
        ('success_m7', one + [R(130.0), ('mark_sensed', ('shadow_002', True), {})], None,
         dict(success=True, exit_reason=None, **m7)),
        ('home_not_reached', [E('shadow_001')], None,
         dict(success=False, exit_reason='home_not_reached', **m7)),
        ('home_not_reached_stack', [], None,
         dict(success=False, exit_reason='home_not_reached', goal_kind='stack',
              goal=('on', 'cube_a', 'cube_b'), on_relations={'cube_a': 'table'}, **m7)),
    ]
    out.note('report_tag2.json (INDEX_PINS P7, SPEC D15): belief is a real belief.BeliefState over '
             'shadow_001 to shadow_004 with target dice, brought to each case by its steps at fixed times '
             '(suspend seconds 120.0), its state stored before the call; no ledger is open, so '
             'run_logger._ledger_t0 is None except in case ledger_t0_1000, which sets it to 1000.0 for the '
             'call and puts the old value back; the other arguments as in report.json, with a run folder '
             'per case under runs_tag2')
    rows, done = [], []
    for name, steps, t0, kw in cases:
        b = BeliefState(list(P30_SHADOWS_TAG2), 'dice')
        for meth, a, k in steps:
            getattr(b, meth)(*a, **k)
        state = {'shadow_status': dict(b.shadow_status), 'target_found_in': b.target_found_in,
                 'suspended': {s: dict(r) for s, r in b.suspended.items()},
                 'suspensions': [dict(r) for r in b.suspensions],
                 'get_suspended_shadows': b.get_suspended_shadows()}
        run_dir = Path('runs_tag2') / name
        run_dir.mkdir(parents=True)
        args = dict(base, shadows=list(P30_SHADOWS_TAG2), belief=b,
                    run_logger=types.SimpleNamespace(run_dir=run_dir, log_path=None))
        args.update(kw)
        old_t0 = rl._ledger_t0
        rl._ledger_t0 = t0
        try:
            r = outcome(rl.report_run_outcome, **args)
        finally:
            rl._ledger_t0 = old_t0
        summary = run_dir / 'timing_summary.json'
        r['timing_summary_json'] = summary.read_text() if summary.exists() else None
        rows.append({'case': name, 'steps': [[m, list(a), k] for m, a, k in steps], 'ledger_t0': t0,
                     'belief': state, **r})
        done.append((name, kw, r))
    out.json('report_tag2.json', rows)
    return done


def _p30_exit_reasons(out, results):
    """exit_reasons.json: the values main() of test_full_pipeline.py assigns to exit_reason (its
    nested functions included) and the ones run_logger.report_run_outcome compares it with or
    assigns, by AST (PLAN rule 3), and the failed cases of results per exit reason as their
    timing_summary.json writes it (the case's argument when no summary is written).  results is
    [(file, [(case, arguments, outcome)])].  The lines go to INFO_exit_reason_lines.json."""
    def top_def(path, name):
        tree = ast.parse((REPO / path).read_text(encoding='utf-8'))
        found = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(found) != 1:
            raise LookupError(f'{path} defines {name} {len(found)} times at module level, not once')
        return found[0]

    def binds(t):
        if isinstance(t, ast.Name):
            return t.id == 'exit_reason'
        if isinstance(t, (ast.Tuple, ast.List)):
            return any(binds(e) for e in t.elts)
        return isinstance(t, ast.Starred) and binds(t.value)

    def sites(fn):
        assigns, other, compares = {}, [], {}
        for n in ast.walk(fn):
            if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                if not any(binds(t) for t in targets):
                    continue
                v = n.value
                if (isinstance(n, ast.Assign) and len(targets) == 1 and isinstance(targets[0], ast.Name)
                        and isinstance(v, ast.Constant) and isinstance(v.value, str)):
                    assigns.setdefault(v.value, []).append(n.lineno)
                else:
                    other.append({'line': n.lineno, 'code': ast.unparse(n)})
            elif isinstance(n, ast.Compare) and isinstance(n.left, ast.Name) and n.left.id == 'exit_reason':
                for c in n.comparators:
                    for e in (c.elts if isinstance(c, (ast.Tuple, ast.List, ast.Set)) else [c]):
                        if isinstance(e, ast.Constant) and isinstance(e.value, str):
                            compares.setdefault(e.value, []).append(n.lineno)
        return assigns, other, compares

    m_as, m_other, m_cmp = sites(top_def('test_full_pipeline.py', 'main'))
    r_as, r_other, r_cmp = sites(top_def('run_logger.py', 'report_run_outcome'))
    by_reason, success_cases = {}, []
    for file, items in results:
        for name, kw, r in items:
            s = r.get('timing_summary_json')
            summ = json.loads(s) if s else None
            ok = summ['success'] if summ else kw['success']
            reason = summ['exit_reason'] if summ else kw.get('exit_reason')
            label = f'{file}:{name}'
            if ok:
                success_cases.append(label)
            else:
                by_reason.setdefault(str(reason), []).append(label)
    named = sorted(set(m_as) | set(r_cmp) | set(r_as))
    out.json('exit_reasons.json', {
        'main_assigns': sorted(m_as),
        'main_other_assignments': [o['code'] for o in m_other],
        'main_compares': sorted(m_cmp),
        'report_compares': sorted(r_cmp),
        'report_assigns': sorted(r_as),
        'report_other_assignments': [o['code'] for o in r_other],
        'main_assigns_without_a_report_branch': sorted(set(m_as) - set(r_cmp)),
        'report_branches_main_never_assigns': sorted(set(r_cmp) - set(m_as)),
        'failed_cases_by_exit_reason': {k: by_reason[k] for k in sorted(by_reason)},
        'success_cases': success_cases,
        'named_values_without_a_case': [v for v in named if v not in by_reason],
        'case_values_the_code_does_not_name': sorted(set(by_reason) - set(named)),
    })
    def lines(d):
        return {k: sorted(d[k]) for k in sorted(d)}
    out.json('INFO_exit_reason_lines.json', {
        'test_full_pipeline.py main assigns': lines(m_as),
        'test_full_pipeline.py main other assignments': sorted(m_other, key=lambda o: o['line']),
        'test_full_pipeline.py main compares': lines(m_cmp),
        'run_logger.py report_run_outcome compares': lines(r_cmp),
        'run_logger.py report_run_outcome assigns': lines(r_as),
        'run_logger.py report_run_outcome other assignments': sorted(r_other, key=lambda o: o['line'])})
    out.note('exit_reasons.json: the exit_reason values main() of test_full_pipeline.py assigns (nested '
             'functions included), compares, and the ones report_run_outcome compares or assigns, by AST and '
             'sorted; the failed cases of report.json and report_tag2.json by the exit_reason their '
             'timing_summary.json writes (the argument when none is written); lines in '
             'INFO_exit_reason_lines.json')
    out.note('not reached here: the relabel in main() of all_searched and rediscovery_giveup to target_lost '
             'when target_lost_seen; it is code of main(), which only an episode runs (group episode)')


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

    long_tail = '\n'.join(['Traceback (most recent call last):'] + [f'  frame {k}' for k in range(1, 24)]
                          + ["KeyError: 'red_object'"]) + '\n'
    short_tail = "Traceback (most recent call last):\n  frame 1\nKeyError: 'red_object'\n"

    def fake_run(argv, capture_output, text, timeout, cwd):
        m = mode['m']
        counter['n'] += 1
        if m == 'timeout':
            raise sp.TimeoutExpired(argv, timeout)
        if m == 'crash':
            return sp.CompletedProcess(argv, 3, 'some output', 'Traceback ...')
        if m in ('crash70_long', 'crash70_short'):          # gate 7: C-01's exit 70
            return sp.CompletedProcess(argv, 70, 'some output', long_tail if m == 'crash70_long' else short_tail)
        if m in ('good', 'mismatch', 'crash70_after_summary'):
            d = Path('logs') / f'run_fake_{counter["n"]:02d}'
            d.mkdir(parents=True)
            rc = {'scene': cell['scene'], 'seed': cell['seed'] + (7 if m == 'mismatch' else 0),
                  'goal': cell['goal'], 'baseline': cell.get('baseline', 'semantic'),
                  'unit_costs': bool(cell['unit_costs'])}
            if cell.get('min_boxel_size') is not None:
                rc['min_boxel_size'] = cell['min_boxel_size']
            (d / 'timing_summary.json').write_text(json.dumps(
                {'run_config': rc, 'success': True, 'plan_count': 3, 'total_planning_time_s': 1.5}))
            if m == 'crash70_after_summary':
                return sp.CompletedProcess(argv, 70, 'ok', short_tail)
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
    # Gate 7 (INDEX_PINS P6, trap 11): C-01's crash_exit70 row with its stderr_tail, after the
    # modes above (the fake clock and the run counter go on from them).
    runs = []
    for i, (m, call) in enumerate((('crash70_long', 'run_cell'), ('crash70_short', 'run_cell'),
                                   ('crash70_after_summary', 'run_cell'),
                                   ('crash70_long', 'run_cell_counted'))):
        mode['m'] = m
        sweep = Path(f'sweep_tag2_{i}_{m}_{call}')
        r = outcome(getattr(er, call), cell, sweep, 30.0, [], False)
        cdir = sweep / 'cells' / er.cell_tag(cell)
        files = {f.name: f.read_text(encoding='utf-8') for f in sorted(cdir.glob('*'))}
        runs.append({'mode': m, 'call': call, **r, 'files': files,
                     'run_dirs_in_logs': sorted(p.name for p in Path('logs').glob('*'))})
    agg = outcome(er.aggregate, Path('sweep_tag2_0_crash70_long_run_cell'))
    if 'value' in agg:
        agg['value'] = Path(agg['value']).name
    agg['files'] = {n: (Path('sweep_tag2_0_crash70_long_run_cell') / n).read_text(encoding='utf-8')
                    for n in ('aggregated.csv', 'aggregated.jsonl')}
    out.json('run_cell_tag2.json', {'stderr_tail_lines': er.STDERR_TAIL_LINES,
                                    'long_stderr_lines': len(long_tail.splitlines()),
                                    'runs': runs, 'aggregate_of_the_first': agg})
    out.note('run_cell_tag2.json (gate 7, INDEX_PINS P6): the fake run also answers exit 70 (C-01: an exception '
             'in main exits 70) with a stderr of 25 lines and of 3, and once after writing a run\'s summary '
             '(the exit code is read first: a crash row, that summary not banked); the last mode runs '
             'run_cell_counted; aggregate over the first sweep (stderr_tail is in aggregated.jsonl, not in the '
             'csv); run_dirs_in_logs: the fake runs\' folders after each call')


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
    win_repo = subprocess.run(['wslpath', '-w', str(REPO)], capture_output=True, text=True,
                              check=True).stdout.strip()

    def dry_runs(cases, catch=False):
        script = []
        for name, args in cases:
            call = f"& '{win}' {args}{'' if name == 'alias_d' else ' -DryRun'} *>&1 | ForEach-Object {{ \"$_\" }}"
            if catch:       # a refused parameter: its error id, not the message in the host's language
                call = f"try {{ {call} }} catch {{ '@@ERROR ' + $_.FullyQualifiedErrorId }}"
            script += [f"'@@CASE {name}'", "$global:LASTEXITCODE = 0", call, "'@@RC ' + $LASTEXITCODE"]
        proc = subprocess.run([pwsh, '-NoProfile', '-NonInteractive', '-Command', '; '.join(script)],
                              capture_output=True, text=True, encoding='utf-8', errors='replace',
                              timeout=300, cwd=str(REPO))
        stamp = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}')
        text = stamp.sub('<STAMP>', proc.stdout.replace('\r\n', '\n').replace(win_repo, '<REPO>'))
        res, cur = [], None
        for line in text.split('\n'):
            if line.startswith('@@CASE '):
                cur = {'case': line[7:], 'args': dict(cases)[line[7:]], 'lines': []}
                res.append(cur)
            elif line.startswith('@@RC '):
                cur['rc'] = line[5:]
            elif cur is not None and line:
                cur['lines'].append(line)
        return {'pwsh_rc': proc.returncode,
                'stderr': stamp.sub('<STAMP>', proc.stderr.replace(win_repo, '<REPO>')), 'cases': res}
    out.json('dry_runs.json', dry_runs(cases))
    out.note('pwsh.exe -NoProfile -NonInteractive through WSL interop, one call for all cases; host output '
             'merged (*>&1); the folder stamp masked as <STAMP>; the checkout path masked as <REPO>')
    # Gate 7 (INDEX_PINS P1): -Look and -Eye with every value of their ValidateSet (read from run.ps1),
    # a value outside it, -Eye arm without a look, --m7 off and the declared F and R strings through -Args.
    src = (REPO / 'run.ps1').read_text(encoding='utf-8')
    sets = {}
    for par in ('Look', 'Eye'):
        found = re.findall(r"\[ValidateSet\(([^)]*)\)\]\[string\]\$" + par + r"\b", src)
        if len(found) != 1:
            raise LookupError(f'run.ps1: {len(found)} ValidateSet lines for ${par}, not one')
        sets[par] = [v for v in re.findall(r"'([^']*)'", found[0]) if v]
    declared, source = declared_o_args()
    if any("'" in v for v in declared.values()):
        raise ValueError(f'a declared string holds a quote: {declared}')
    tag2 = []
    for target in ('tampura', 'boxels'):
        tag2 += [(f'{target}_look_{v}', f"{target} -Seed 0 -Look {v}") for v in sets['Look']]
        tag2 += [(f'{target}_eye_{v}_alone', f"{target} -Seed 0 -Eye {v}") for v in sets['Eye']]
        tag2 += [(f'{target}_look_{v}_eye_arm', f"{target} -Seed 0 -Look {v} -Eye arm")
                 for v in sets['Look']]
        tag2 += [(f'{target}_look_bad', f"{target} -Seed 0 -Look nowhere"),
                 (f'{target}_eye_bad', f"{target} -Seed 0 -Eye nowhere"),
                 (f'{target}_m7_off_args', f"{target} -Seed 0 -Args '--m7 off'"),
                 (f'{target}_declared_F', f"{target} -Seed 0 -Headless -Args '{declared['F']}'"),
                 (f'{target}_declared_R', f"{target} -Seed 0 -Headless -Args '{declared['R']}'")]
    out.json('dry_runs_tag2.json', {'validate_sets': sets, 'declared': declared, **dry_runs(tag2, catch=True)})
    out.note('dry_runs_tag2.json (gate 7, INDEX_PINS P1): a second pwsh call as above, for run tampura and run '
             'boxels: -Look with each value of its ValidateSet and with -Eye arm, -Eye with each value alone '
             '(the sets read from run.ps1\'s param block), a value outside each set, -Args \'--m7 off\', and the '
             f'declared F and R strings as -Args with -Headless (read by text from {source["path"]}, git blob '
             f'{source["git_blob_sha1"]}); each call inside try/catch, a refused call written as "@@ERROR" and '
             'its FullyQualifiedErrorId (the message itself is in the host\'s language); the Windows path of the '
             'checkout is masked as <REPO> too')


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

def _call_sites(callee, files=None):
    """Every call of the function named callee (a bare name, an attribute, or an import alias of
    it) in the AST pins' scope: file, function, line, callee text, kind (the first argument if a
    str constant, else <dynamic: ...> or <no kind>), keyword names, positional count."""
    sites = []
    for path in (repo_py_files() if files is None else files):
        r = rel(path)
        tree = _parse(path)
        aliases = {callee}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == callee and a.asname:
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
    return sites


def ledger_kinds():
    """The row kinds of every ledger_event call in the AST pins' scope, sorted: pin 40's
    kinds.json, read from the code (PLAN rule 3).  A call whose kind is not a str constant shows
    as <dynamic: ...>.  The console's made-tape test reads the kinds here (SPEC D14 (d))."""
    return sorted({s['kind'] for s in _call_sites('ledger_event')})


M7_ROW_KINDS = ('sense_discovery', 'm7_suspension')     # U3: the two kinds M7 added


@pin('low', 'p40_ledger_schema', 'P40: per ledger_event call site the kind and keyword names (AST)')
def p40_ledger_schema(out):
    from collections import Counter
    sites = _call_sites('ledger_event')
    multi = Counter((s['kind'], tuple(s['keywords']), s['n_positional']) for s in sites)
    out.json('schema.json', [[k, list(kw), npos, multi[(k, kw, npos)]] for (k, kw, npos) in sorted(multi)])
    kinds = sorted({s['kind'] for s in sites})
    out.json('kinds.json', kinds)
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
    # Gate 7 (INDEX_PINS P3, PLAN rule 3, trap 7, U3): the counts, bridge_gates' own list, the
    # statuses dispatch_end is called with, the two M7 kinds.
    g3 = list(_module_literal('tools/bridge_gates.py', 'G3_STATUSES'))
    out.json('bridge_gates_statuses.json', g3)
    ends = _call_sites('dispatch_end')
    end_count = Counter(s['kind'] for s in ends)
    out.json('dispatch_end_statuses.json', [[k, end_count[k], k in statuses] for k in sorted(end_count)])
    out.json('INFO_dispatch_end_sites.json', sorted(ends, key=lambda s: (s['file'], s['line'])))
    out.json('counts.json', {
        'ledger_event_sites': len(sites),
        'row_kinds': len(kinds),
        'row_kinds_not_a_constant': [k for k in kinds if k.startswith('<')],
        'step_end_statuses': len(statuses),
        'bridge_gates_G3_STATUSES': len(g3),
        'step_end_statuses_not_in_G3_STATUSES': [s for s in statuses if s not in g3],
        'G3_STATUSES_not_in_step_end_statuses': [s for s in g3 if s not in statuses],
        'dispatch_end_sites': len(ends),
        'dispatch_end_not_a_constant': sorted(k for k in end_count if k.startswith('<')),
        'dispatch_end_constants_not_in_step_end_statuses': sorted(k for k in end_count
                                                                  if not k.startswith('<') and k not in statuses)})
    out.json('m7_kinds.json', {k: [[list(kw), npos, multi[(kk, kw, npos)]] for (kk, kw, npos) in sorted(multi)
                                   if kk == k] for k in M7_ROW_KINDS})
    out.note('counts.json (gate 7, INDEX_PINS P3; PLAN rule 3: counted here, never typed): the ledger_event sites, '
             'the row kinds of kinds.json (and those that are not a str constant), the statuses of '
             'run_logger.STEP_END_STATUSES and of tools/bridge_gates.py\'s G3_STATUSES (bridge_gates_statuses.json, '
             'source order; trap 7: the two lists differ by design) with what each holds that the other lacks, the '
             'dispatch_end call sites, those whose status is not a str constant (their values are not read here), '
             'and any constant status STEP_END_STATUSES lacks (dispatch_end turns such a value into unlabelled)')
    out.note('dispatch_end_statuses.json: [status (the first argument, or <dynamic: ...>), number of call sites, '
             'in STEP_END_STATUSES], sorted, over the same scope as schema.json; INFO_dispatch_end_sites.json '
             '(file, function, line) is information only')
    out.note('m7_kinds.json (U3): for each of the kinds ' + ', '.join(M7_ROW_KINDS) + ' its rows of '
             'schema.json ([keyword names, positional count, number of sites]); an empty list would say the kind '
             'is gone')


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
    out.note(D10_NOTE.format('the keys "file::qualname"'))


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
    _p42_tag2(out, trees)


# Gate 7 (INDEX_PINS P4, PLAN 4.4): the module run state of traps 2, 14, 15 and 16, the names M6's
# list holds for them.
_RUN_STATE = [('interior_regions', 'ENABLED'), ('interior_regions', '_seen_under'),
              ('interior_regions', '_no_plan_regions'), ('run_logger', '_ledger_t0'),
              ('execution', 'M7'), ('execution', 'M7_SUSPEND_S')]


def _run_state_fact(trees, mod, name):
    """Where one module-level name of run state is bound, rebound, read and changed, by the
    syntax trees of the AST pins' scope: its module-level binding (kind and value text), the
    module's functions with 'global name', the module's bare loads and stores of the name per
    function, the method calls on it and the item stores and deletes (name[...] = ..., del
    name[...]) per function (a container changed in place), and in the other files the loads and
    stores of mod.name and every 'from mod import name' (a copy by value).  Names are not resolved
    by scope: a bare name is counted wherever it is spelled."""
    from collections import Counter
    home = f'{mod}.py'
    binding = None
    for node in trees[home].body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            binding = ['assign', ast.unparse(node.value)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            binding = ['annotated assign', ast.unparse(node.annotation),
                       ast.unparse(node.value) if node.value is not None else None]
    glob, loads, stores, methods, items = set(), Counter(), Counter(), Counter(), Counter()

    def on_home(node, qual):
        if isinstance(node, ast.Global) and name in node.names:
            glob.add(qual)
        if isinstance(node, ast.Name) and node.id == name:
            (loads if isinstance(node.ctx, ast.Load) else stores)[qual] += 1
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == name):
            methods[(qual, node.func.attr)] += 1
        if (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == name
                and isinstance(node.ctx, (ast.Store, ast.Del))):
            items[(qual, 'store' if isinstance(node.ctx, ast.Store) else 'del')] += 1
    _walk_scoped(trees[home], on_home)
    m_loads, m_stores, by_value = Counter(), Counter(), []
    for r, tree in trees.items():
        if r == home:
            continue

        def on(node, qual, r=r):
            if (isinstance(node, ast.Attribute) and node.attr == name and isinstance(node.value, ast.Name)
                    and node.value.id == mod):
                (m_loads if isinstance(node.ctx, ast.Load) else m_stores)[(r, qual)] += 1
            if isinstance(node, ast.ImportFrom) and not node.level and node.module == mod:
                by_value.extend([r, qual, a.asname] for a in node.names if a.name in (name, '*'))
        _walk_scoped(tree, on)
    return {'binding': binding, 'global_in': sorted(glob),
            'bare_loads': [[q, n] for q, n in sorted(loads.items())],
            'bare_stores': [[q, n] for q, n in sorted(stores.items())],
            'method_calls': [[q, m, n] for (q, m), n in sorted(methods.items())],
            'item_writes': [[q, k, n] for (q, k), n in sorted(items.items())],
            'module_loads': [[r, q, n] for (r, q), n in sorted(m_loads.items())],
            'module_stores': [[r, q, n] for (r, q), n in sorted(m_stores.items())],
            'from_imports': sorted(by_value)}


def _follow_arm_standin():
    """Trap 1 at run time, on a stand-in env (no physics client): arm_eye.follow_arm patches the
    instance, the class keeps its method, and a call through the instance runs use_start_view
    first.  arm_eye.start_camera, the one pybullet reader on that path, is replaced for the call by
    a stand-in that returns a camera named by its arguments; restored afterwards."""
    import types
    import arm_eye

    class StandInEnv:
        def _view_and_projection_matrices(self):
            return ['matrices of', self.camera_position, self.fov]
    env = StandInEnv()
    env.objects = {'robot': types.SimpleNamespace(object_id=7)}
    env.client_id = 0
    env.camera_position, env.fov = 'fixed camera', 60
    env.shadow_calculator = types.SimpleNamespace(camera_position='fixed camera')
    calls = []

    def start_camera(robot_id, physics_client=0):
        calls.append([robot_id, physics_client])
        return {n: f'{n} of the arm camera, call {len(calls)}' for n in arm_eye.CAMERA_ATTRIBUTES}
    method = StandInEnv.__dict__['_view_and_projection_matrices']
    res = {'before': {'instance_attribute': '_view_and_projection_matrices' in vars(env),
                      'following': arm_eye.following(env)}}
    real = arm_eye.start_camera
    arm_eye.start_camera = start_camera
    try:
        arm_eye.follow_arm(env)
        res['after_follow_arm'] = {
            'instance_attribute': '_view_and_projection_matrices' in vars(env),
            'instance_attribute_is_the_class_method': vars(env).get('_view_and_projection_matrices') is method,
            'class_attribute_is_the_class_method': type(env).__dict__['_view_and_projection_matrices'] is method,
            'following': arm_eye.following(env), 'flag': [arm_eye.FOLLOW_FLAG, getattr(env, arm_eye.FOLLOW_FLAG)],
            'start_camera_calls': list(calls)}
        value = env._view_and_projection_matrices()
        res['after_one_call'] = {'returned': value, 'start_camera_calls': list(calls),
                                 'env_camera': {n: getattr(env, n) for n in arm_eye.CAMERA_ATTRIBUTES},
                                 'shadow_calculator_camera_position': env.shadow_calculator.camera_position}
    finally:
        arm_eye.start_camera = real
    return res


def _p42_tag2(out, trees):
    """Gate 7: trap 1 (the instance patch), the run state of traps 2, 14, 15, 16, and REVIEW
    item 13 (solve by any spelling), as facts 8 to 13 in facts_tag2.json."""
    attr = '_view_and_projection_matrices'
    vpm = _module_binds(trees['boxel_env.py'], f'BoxelTestEnv.{attr}')
    assigned, type_reads, calls, cam_writes, info = [], [], [], [], []
    arm_setattr, solve_calls, solve_imports = [], [], []
    for r, tree in trees.items():
        def on(node, qual, r=r):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(t, ast.Attribute) and t.attr == attr:
                        assigned.append([r, qual, ast.unparse(node).splitlines()[0]])
                        info.append(['assigned', r, qual, node.lineno])
                    if isinstance(t, ast.Attribute) and t.attr == 'camera_position':
                        cam_writes.append([r, qual, ast.unparse(node).splitlines()[0]])
                        info.append(['camera_position', r, qual, node.lineno])
            if (isinstance(node, ast.Attribute) and node.attr == attr and isinstance(node.value, ast.Call)
                    and isinstance(node.value.func, ast.Name) and node.value.func.id == 'type'):
                type_reads.append([r, qual, ast.unparse(node)])
                info.append(['type_read', r, qual, node.lineno])
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Attribute) and fn.attr == attr:
                    calls.append([r, qual, ast.unparse(fn.value)])
                    info.append(['call', r, qual, node.lineno])
                if r == 'arm_eye.py' and isinstance(fn, ast.Name) and fn.id == 'setattr':
                    arm_setattr.append([qual, ast.unparse(node)])
                if (isinstance(fn, ast.Name) and fn.id == 'solve') or (isinstance(fn, ast.Attribute)
                                                                       and fn.attr == 'solve'):
                    solve_calls.append([r, qual, ast.unparse(fn)])
                    info.append(['solve_call', r, qual, node.lineno])
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name == 'solve' or a.asname == 'solve':
                        solve_imports.append([r, qual, '.' * node.level + (node.module or ''), a.name, a.asname])
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname == 'solve':
                        solve_imports.append([r, qual, a.name, None, a.asname])
        _walk_scoped(tree, on)
    ae = trees['arm_eye.py']
    facts = [
        {'fact': 8, 'trap': 1, 'subject': f'BoxelTestEnv.{attr} in the class body (reachable as '
                                          f'type(env).{attr})', 'found': vpm is not None},
        {'fact': 9, 'trap': 1, 'subject': f'{attr}: assignments to an attribute of that name, reads through '
                                          'type(...), and every call (its receiver)',
         'assigned': sorted(assigned), 'type_reads': sorted(type_reads), 'calls': sorted(calls)},
        {'fact': 10, 'trap': 1, 'subject': 'the camera attributes: assignments to an attribute camera_position, '
                                           'setattr calls in arm_eye.py, arm_eye.CAMERA_ATTRIBUTES and FOLLOW_FLAG',
         'camera_position_assignments': sorted(cam_writes), 'arm_eye_setattr': sorted(arm_setattr),
         'CAMERA_ATTRIBUTES': _module_literal('arm_eye.py', 'CAMERA_ATTRIBUTES'),
         'FOLLOW_FLAG': _module_literal('arm_eye.py', 'FOLLOW_FLAG'),
         'follow_arm_defined': _module_binds(ae, 'follow_arm') is not None,
         'use_start_view_defined': _module_binds(ae, 'use_start_view') is not None},
        {'fact': 11, 'trap': 1, 'subject': 'arm_eye.follow_arm on a stand-in env, run', **_follow_arm_standin()},
        {'fact': 12, 'traps': '2, 14, 15, 16', 'subject': 'module run state: binding, global, bare and module '
                                                         'reads and writes, in-place changes, copies by value',
         'names': {f'{m}.{n}': _run_state_fact(trees, m, n) for m, n in _RUN_STATE}},
        {'fact': 13, 'review_item': 13, 'subject': 'solve by any spelling: calls of solve and of x.solve, and '
                                                   'every import that binds the name solve (its scope)',
         'calls': sorted(solve_calls), 'imports': sorted(solve_imports, key=lambda s: [str(x) for x in s])},
    ]
    out.json('facts_tag2.json', facts)
    out.json('INFO_lines_tag2.json', sorted(info))
    out.note('facts_tag2.json (gate 7, INDEX_PINS P4, PLAN 4.4 traps 1, 2, 14, 15, 16, REVIEW_PHASE0 item 13): '
             'facts 8 to 13, over the same syntax trees as facts 1 to 7; sites as [file, qualname, text] sorted, '
             'line numbers only in INFO_lines_tag2.json (not compared)')
    out.note('fact 11 is the one fact that runs code: arm_eye imported, follow_arm called on a stand-in env '
             '(a class with its own _view_and_projection_matrices, no physics client) with arm_eye.start_camera '
             'replaced for the call by a stand-in; then one call of env._view_and_projection_matrices()')
    out.note('fact 12 counts Name nodes by spelling, not by scope (a local of the same name would count); '
             'the run-state names are those of PLAN 4.4 traps 2, 14, 15 and 16 (M6\'s list)')


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
    out.note(D10_NOTE.format('the keys "file::qualname" of loggers.json, globals.json and free_variables.json'))


# ----- pin 45: fresh imports -----------------------------------------------

# REVIEW_PHASE0 item 12: whether console_ui.install_early ran before pybullet was imported.  An
# audit hook sees the start of the first import of console_ui and of pybullet; from the start of
# console_ui's import until pybullet's import starts (to the end when pybullet came first or not
# at all) a trace function sees every call of console_ui.install_early, its caller's module, its
# module_name argument and what it returned (a call after pybullet's import cannot change the
# answer, and tracing the rest of an import doubles the pin's time).  They import nothing and
# change none of the facts the pin stores.  importlib.import_module, by which _FRESH imports the
# module under test, raises no "import" event for that module itself (only the import statements
# inside it do), so _FRESH hands its start to the hook (fix round 1 of WP-A, CHECK_A_1 note 3).
_EARLY_HOOKS = r'''
early = []
_early_seen = set()
_early_file = os.path.join(repo, 'console_ui.py')
def _early_audit(event, args):
    if event == 'import' and args[0] in ('console_ui', 'pybullet') and args[0] not in _early_seen:
        _early_seen.add(args[0])
        early.append({'event': 'import', 'module': args[0]})
        sys.settrace(_early_trace if args[0] == 'console_ui' else None)
def _early_trace(frame, event, arg):
    code = frame.f_code
    if code.co_name != 'install_early' or os.path.abspath(code.co_filename) != _early_file:
        return None
    back = frame.f_back
    row = {'event': 'call', 'function': 'console_ui.install_early',
           'caller': back.f_globals.get('__name__') if back is not None else None,
           'module_name': frame.f_locals.get('module_name')}
    early.append(row)
    def _early_return(frame, event, arg):
        if event == 'exception':
            row['raised'] = arg[0].__name__
        elif event == 'return':
            row['returned'] = arg
        return _early_return
    return _early_return
sys.addaudithook(_early_audit)
'''

_FRESH = r'''
import importlib, json, logging, os, sys
repo, name = sys.argv[1], sys.argv[2]
''' + _EARLY_HOOKS + r'''
_early_audit('import', (name,))
err = None
try:
    importlib.import_module(name)
except BaseException as ex:
    err = type(ex).__name__ + ': ' + str(ex)
sys.settrace(None)
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
print('@@EARLY ' + json.dumps(early))
'''

# An entry script run as __main__ (runpy, sys.path[0] its folder as for `python script`), with the
# same hooks; the arguments end in --help, so the script stops at its parser.
_ENTRY_EARLY = r'''
import json, os, runpy, sys
repo, script = sys.argv[1], sys.argv[2]
''' + _EARLY_HOOKS + r'''
sys.argv = [script] + sys.argv[3:]
sys.path.insert(0, os.path.dirname(script))
code = None
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit as ex:
    code = ex.code
sys.settrace(None)
print('@@EARLY ' + json.dumps({'events': early, 'system_exit': code}))
'''


def _early_order(events):
    """One fresh interpreter's install_early record: the events in order, and whether
    console_ui.install_early was called before the import of pybullet began (None when pybullet was
    not imported)."""
    calls = [i for i, e in enumerate(events) if e['event'] == 'call']
    pyb = next((i for i, e in enumerate(events) if e == {'event': 'import', 'module': 'pybullet'}), None)
    return {'events': events,
            'install_early_ran_before_pybullet': None if pyb is None else bool(calls) and calls[0] < pyb}


@pin('low', 'p45_fresh_imports', 'P45: each root module and tampura_bridge.policy imported first in a fresh interpreter', timeout=1200)
def p45_fresh_imports(out):
    tw = '/root/tampura-work'
    masker = Masker([(REPO, '<REPO>'), (tw, '<TW>')])
    res = {}
    early = {}
    tb_path = ':'.join([str(REPO), str(REPO / 'pddlstream_lib'), f'{tw}/tampura', f'{tw}/tampura_environments'])
    mods = [p.stem for p in sorted(REPO.glob('*.py'))] + ['tampura_bridge.policy']
    for m in mods:
        env = dict(os.environ)
        if m.startswith('tampura_bridge'):
            env['PYTHONPATH'] = tb_path
        p = subprocess.run([sys.executable, '-c', _FRESH, str(REPO), m], capture_output=True, text=True,
                           timeout=180, cwd=os.getcwd(), env=env)
        line = next((ln for ln in p.stdout.splitlines() if ln.startswith('@@JSON ')), None)
        res[m] = json.loads(masker(line[7:])) if line else {'no_output': f'rc {p.returncode}',
                                                           'stderr_tail': masker(p.stderr[-600:])}
        eline = next((ln for ln in p.stdout.splitlines() if ln.startswith('@@EARLY ')), None)
        early[m] = _early_order(json.loads(eline[8:])) if eline else None
    out.json('fresh_imports.json', res)
    entries = {}
    for script, argv, env_path in (('test_full_pipeline.py', ['--no-gui', '--help'], None),
                                   ('tampura_bridge/run_bridge_on_finddice.py', ['--help'], tb_path)):
        env = dict(os.environ)
        if env_path:
            env['PYTHONPATH'] = env_path
        p = subprocess.run([sys.executable, '-c', _ENTRY_EARLY, str(REPO), str(REPO / script)] + argv,
                           capture_output=True, text=True, timeout=180, cwd=os.getcwd(), env=env)
        eline = next((ln for ln in p.stdout.splitlines() if ln.startswith('@@EARLY ')), None)
        if eline:
            d = json.loads(eline[8:])
            entries[' '.join([script] + argv)] = {**_early_order(d['events']), 'system_exit': d['system_exit']}
        else:
            entries[' '.join([script] + argv)] = {'no_output': f'rc {p.returncode}',
                                                  'stderr_tail': masker(p.stderr[-600:])}
    out.json('fresh_install_early.json', {'imports': early, 'entry_scripts': entries})
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
    out.note('fresh_install_early.json (REVIEW_PHASE0 item 12): in the same fresh interpreters an audit hook '
             'records the start of the first import of console_ui and of pybullet (the import of the module '
             'under test, which importlib.import_module does not announce, is handed to the hook by the '
             'script), and a trace function, on '
             "from the start of console_ui's import until pybullet's import starts (to the end when pybullet "
             'came first or not at all), every call of console_ui.install_early (caller module, module_name, '
             'returned), in order; '
             'install_early_ran_before_pybullet is whether the first call came before the pybullet import '
             '(null when pybullet was not imported); entry_scripts: test_full_pipeline.py --no-gui --help and '
             'tampura_bridge/run_bridge_on_finddice.py --help run as __main__ by runpy with sys.path[0] the '
             "script's folder and the same hooks (--help: install_early returns False, no console is "
             'installed; the smart-level install itself redirects the terminal and is not run here)')


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
    _p48_tag2(out)
    out.note(D10_NOTE.format('the file and qualname fields of twins.json and twins_tag2.json'))


# Gate 7 (INDEX_PINS P5, PLAN 4.4 trap 8, R_PHASE0 3.3, U3): the twins the look and M7 code
# wrote, by name, and the strike caps behind "of 3".
TRAP8_NAMES = ('LOOK_BOXEL_TOL_M', 'FRAME_MARGIN_PX', 'LOOK_IMAGE_MARGIN_PX', '_FOV_V_HALF_TAN', 'STRIKE_PARK')
STRIKE_CAP_FILES = ('test_full_pipeline.py', 'execution.py', 'look_action.py')


def _p48_tag2(out):
    """twins_tag2.json: every binding and import of a name of TRAP8_NAMES; every division
    240 / 525 (the wrist camera's vertical half tangent, robot_utils' and look_views'); in
    STRIKE_CAP_FILES every comparison '>= 3' or '>= STRIKE_PARK' and every text template that
    holds '/3', 'of 3' or '/{STRIKE_PARK}' (the print sites the console's "of 3" patterns read)."""
    from collections import Counter
    sites, info = [], []
    for path in repo_py_files():
        r = rel(path)
        src = path.read_text(encoding='utf-8')
        src_lines = src.splitlines()
        tree = ast.parse(src)
        inner = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        inner |= {id(n.body[0].value) for n in ast.walk(tree)          # docstrings are no templates
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                  and n.body and isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant)}

        def add(name, node, qual, value, r=r, src_lines=src_lines):
            sites.append([name, r, qual, src_lines[node.lineno - 1].strip(), value])
            info.append([name, r, qual, node.lineno])

        def on(node, qual, r=r, inner=inner):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    if isinstance(t, ast.Name) and t.id in TRAP8_NAMES and node.value is not None:
                        add(f'{t.id} (trap 8)', node, qual, ast.unparse(node.value))
            if isinstance(node, ast.ImportFrom):
                for a in node.names:
                    if a.name in TRAP8_NAMES:
                        add(f'{a.name} (trap 8)', node, qual, f'from {node.module} import {a.name}'
                            + (f' as {a.asname}' if a.asname else ''))
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
                    and isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant)
                    and node.left.value in (240, 240.0) and node.right.value in (525, 525.0)):
                add('wrist camera 240 / 525 (trap 8)', node, qual, ast.unparse(node))
            if r not in STRIKE_CAP_FILES:
                return
            if isinstance(node, ast.Compare):
                for op, right in zip(node.ops, node.comparators):
                    if isinstance(op, ast.GtE) and (
                            (isinstance(right, ast.Constant) and right.value == 3)
                            or (isinstance(right, ast.Name) and right.id == 'STRIKE_PARK')):
                        add('strike cap >= 3', node, qual, ast.unparse(node))
            if isinstance(node, (ast.Constant, ast.JoinedStr)) and id(node) not in inner:
                t = _template(node)
                if t and ('/3' in t or 'of 3' in t or '/{STRIKE_PARK}' in t):
                    add('"of 3" print template', node, qual, t)
        _walk_scoped(tree, on)
    multi = Counter((s[0], s[1], s[2], s[3], json.dumps(s[4])) for s in sites)
    out.json('twins_tag2.json', [[k[0], k[1], k[2], k[3], json.loads(k[4]), multi[k]] for k in sorted(multi)])
    out.json('INFO_lines_tag2.json', info)
    out.note('twins_tag2.json (gate 7, INDEX_PINS P5): rows as twins.json, over the same scope; the names of PLAN '
             '4.4 trap 8 (' + ', '.join(TRAP8_NAMES) + ') at every binding and import; every division 240 / 525; '
             'in ' + ', '.join(STRIKE_CAP_FILES) + ' every comparison ">= 3" or ">= STRIKE_PARK" (look-alikes such as '
             'len(seq) >= 3 too) and every text template holding "/3", "of 3" or "/{STRIKE_PARK}" (an f-string once, '
             'its parts not again; docstrings not); line numbers only in INFO_lines_tag2.json')

#@@LOW_PINS@@


# ===========================================================================
# Group "world": the world and its sensing (index phase0/index/pins_world.md)
# ===========================================================================
#
# Every pin of this group starts a fresh child with no physics client.  A
# scene is built headless (BoxelTestEnv(gui=False): DIRECT) and must get
# client 0 for the executing world and client 1 for the plan twin, because
# half the PyBullet calls of the pipeline name no client and mean client 0
# (index 0.2); _make_env refuses anything else.  Module state the pins set:
# pose_belief.SWITCHES (written per case into the outputs), slip_fixes at
# its import default (DEFAULT_ON, the CLI default; spec() written), and
# robot_utils.GRIP_SQUEEZE for the pick pin.

TW = '/root/tampura-work'
TW_ENVS = TW + '/tampura_environments'
RENDER_FIXTURE_VAR = 'READABLE_RENDER_FIXTURE'
RENDER_FIXTURE_DEFAULT = REPO / 'tests' / 'readable' / '_scratch' / 'render_fixture'
SWITCH_NAMES = ('M8', 'M9', 'M10', 'pick_aperture_from_pose')
STATIC_NAMES = ('plane', 'table', 'robot')
SCENE_SEEDS = (0, 1, 7, 13, 999)


def _pb():
    import pybullet
    return pybullet


def _live_clients():
    pb = _pb()
    return [i for i in range(16) if pb.isConnected(physicsClientId=i)]


def _disconnect_all():
    pb = _pb()
    for i in _live_clients():
        try:
            pb.disconnect(physicsClientId=i)
        except Exception:
            pass


def _set_switches(on):
    import pose_belief
    for k in SWITCH_NAMES:
        pose_belief.SWITCHES[k] = bool(on)


def _module_state():
    import pose_belief
    import robot_utils
    import slip_fixes
    return {'slip_fixes': slip_fixes.spec(), 'switches': dict(pose_belief.SWITCHES),
            'grip_squeeze': robot_utils.GRIP_SQUEEZE,
            'robot_model_is_pybullet_data': robot_utils.robot_model() == robot_utils.PANDA_PYBULLET_DATA}


def _rng_digest():
    """sha256 of the global random and np.random states (index 0.5)."""
    import random
    import numpy as np
    n = np.random.get_state()
    h = hashlib.sha256(repr(random.getstate()).encode())
    h.update(repr((n[0], n[1].tolist(), n[2], n[3], n[4])).encode())
    return h.hexdigest()


def _py_rng_digest():
    import random
    return hashlib.sha256(repr(random.getstate()).encode()).hexdigest()


def _make_env(cfg):
    """BoxelTestEnv(gui=False, scene_config=cfg) on clients 0 and 1; returns
    (env, the constructor's printed text)."""
    from boxel_env import BoxelTestEnv
    live = _live_clients()
    if live:
        raise RuntimeError(f'clients still connected before a scene build: {live}')
    with captured() as box:
        env = BoxelTestEnv(gui=False, scene_config=cfg)
    if (env.client_id, env.plan_client_id) != (0, 1):
        env.close()
        raise RuntimeError(f'scene built on clients {env.client_id}, {env.plan_client_id}, not 0, 1')
    return env, box['out'].getvalue()


def _first_registry(env):
    """test_full_pipeline.main lines 858-997 replayed (semantic baseline, no
    --min-boxel-size, no oracle phase): the effective cell, main's 50 settle
    steps, the observation, free space, merge, surface tags, the registry and
    record_initial_detections.  Returns (obs, registry, effective_cell)."""
    import numpy as np
    from boxel_data import BoxelRegistry
    from cell_merger import merge_free_space_cells
    from execution import record_initial_detections
    max_extent = 0.0
    for name, info in env.objects.items():
        if name in STATIC_NAMES:
            continue
        if getattr(info, 'is_tray', False):
            continue
        if info.size is None:
            continue
        max_extent = max(max_extent, float(np.max(info.size)))
    effective_cell = max_extent + 0.01
    env.free_space_generator.min_resolution = effective_cell
    for _ in range(50):
        env.step_simulation()
    env.update_object_positions()
    obs = env.get_camera_observation()
    all_known = obs.boxels
    free_boxels = env.generate_free_space(all_known, visualize=False)
    merged_free = merge_free_space_cells(free_boxels)
    env.annotate_free_space_surface(merged_free)
    all_boxels = all_known + merged_free
    registry = BoxelRegistry()
    for bd in all_boxels:
        registry.add_boxel(bd)
    record_initial_detections(env, registry)
    return obs, registry, effective_cell


def _boxel_tuple(b):
    """R's tuple (id, type, min, max, is_occluder, shadow_boxel_ids,
    created_by_boxel_id, on_surface) plus object_name, created_by_object,
    surface_z."""
    return [b.id, b.boxel_type.value, b.min_corner.tolist(), b.max_corner.tolist(),
            b.is_occluder, list(b.shadow_boxel_ids), b.created_by_boxel_id, b.on_surface,
            b.object_name, b.created_by_object, b.surface_z]


def _pose_fields(b):
    return {'pose_radius': b.pose_radius, 'yaw': b.yaw, 'yaw_valid': b.yaw_valid,
            'body_extents': b.body_extents, 'rect_center': b.rect_center,
            'complete_detections': b.complete_detections}


def _config_rec(c):
    if c is None:
        return None
    return {'name': c.name, 'joint_positions': c.joint_positions, 'is_heuristic': c.is_heuristic,
            'ignored_body_ids': sorted(int(x) for x in c.ignored_body_ids),
            'held_body_ids': sorted(int(x) for x in c.held_body_ids),
            'grasp_ee_offset': c.grasp_ee_offset}


def _grasp_rec(g):
    return {'name': g.name, 'position': g.position, 'orientation': g.orientation}


def _targets_of(env):
    """Non-static, non-occluder, non-tray objects in env.objects order."""
    return [n for n, i in env.objects.items()
            if n not in STATIC_NAMES and not i.is_occluder and not getattr(i, 'is_tray', False)]


def _env_constants(env):
    import pose_belief
    import robot_utils
    import slip_fixes
    pb = _pb()
    rid = env.objects['robot'].object_id
    model = robot_utils.robot_model()
    sc, fs = env.shadow_calculator, env.free_space_generator
    n_con = pb.getNumConstraints(physicsClientId=env.client_id)
    return {
        'table_surface_height': env.table_surface_height,
        'table_x_range': env.table_x_range, 'table_y_range': env.table_y_range,
        'camera_position': env.camera_position, 'camera_target': env.camera_target,
        'camera_up': env.camera_up,
        'shadow_calculator': {'camera_position': sc.camera_position,
                              'table_surface_height': sc.table_surface_height,
                              'x': [sc.table_x_min, sc.table_x_max],
                              'y': [sc.table_y_min, sc.table_y_max]},
        'free_space_generator': {'min_resolution': fs.min_resolution, 'ws_min': fs.ws_min,
                                 'ws_max': fs.ws_max},
        'tray_xy': env._tray_xy,
        'gui_to_plan': [[g, p_] for g, p_ in env._gui_to_plan.items()],
        'plan_robot_id': env.plan_robot_id,
        'finger_joint_states': {
            'client0': [list(pb.getJointState(rid, fj, physicsClientId=env.client_id)[:2])
                        for fj in model.finger_joints],
            'client1': [list(pb.getJointState(env.plan_robot_id, fj, physicsClientId=env.plan_client_id)[:2])
                        for fj in model.finger_joints]},
        'finger_lateral_friction_client0': [pb.getDynamicsInfo(rid, fl, physicsClientId=env.client_id)[1]
                                            for fl in model.finger_joints],
        'num_constraints_client0': n_con,
        'constraints_client0': [list(pb.getConstraintInfo(pb.getConstraintUniqueId(i, physicsClientId=env.client_id),
                                                          physicsClientId=env.client_id))
                                for i in range(n_con)],
        'num_solver_iterations': {
            'client0': pb.getPhysicsEngineParameters(physicsClientId=env.client_id)['numSolverIterations'],
            'client1': pb.getPhysicsEngineParameters(physicsClientId=env.plan_client_id)['numSolverIterations']},
        'slip_fixes': slip_fixes.spec(), 'switches': dict(pose_belief.SWITCHES),
    }


def _scene_record(env, cfg):
    """Every object in env.objects order: the ObjectInfo fields, its spec,
    the spawn pose (read from the plan twin, created at the spawn position and
    never stepped) and the settled pose (client 0 after the 10 settle steps)."""
    pb = _pb()
    specs = {}
    for i, s in enumerate(cfg.occluders):
        specs[s.name if s.name is not None else f'occluder_{i + 1}'] = s
    for i, s in enumerate(cfg.targets):
        specs[s.name if s.name is not None else f'target_{i + 1}'] = s
    objs = []
    for name, info in env.objects.items():
        gid = info.object_id
        pid = env._gui_to_plan.get(gid)
        row = {'name': name, 'object_id': gid, 'plan_id': pid, 'is_occluder': info.is_occluder,
               'is_visible': info.is_visible, 'is_tray': getattr(info, 'is_tray', False),
               'size': info.size, 'info_position': info.position,
               'info_orientation': info.orientation,
               'spawn_pose_from_twin': (list(pb.getBasePositionAndOrientation(pid, physicsClientId=env.plan_client_id))
                                        if pid is not None else None),
               'settled_pose_client0': list(pb.getBasePositionAndOrientation(gid, physicsClientId=env.client_id))}
        s = specs.get(name)
        if s is not None:
            row['spec'] = {'shape': s.shape.value, 'size': s.size, 'color': s.color, 'mass': s.mass,
                           'lateral_friction': s.lateral_friction}
        objs.append(row)
    return {'scene_config': {'seed': cfg.seed, 'constrain_to_reach': cfg.constrain_to_reach,
                             'n_hidden_targets': cfg.n_hidden_targets, 'enable_tray': cfg.enable_tray,
                             'occluder_positions': cfg.occluder_positions,
                             'target_positions': cfg.target_positions},
            'objects': objs, 'constants': _env_constants(env)}


def _scene_case(label, make_cfg, tray=False):
    """Build one scene; its record, or the exception's type and text."""
    import random
    import numpy as np
    cfg = make_cfg()
    if tray:
        cfg.enable_tray = True     # set after the preset call, as main does
    random.seed(1234)
    np.random.seed(1234)
    before = _rng_digest()
    try:
        env, printed = _make_env(cfg)
    except Exception as ex:
        live = _live_clients()
        _disconnect_all()
        return {'case': label, 'raises': type(ex).__name__, 'message': str(ex),
                'global_rng_unchanged': _rng_digest() == before, 'clients_left_connected': live}
    try:
        rec = {'case': label, **_scene_record(env, cfg),
               'global_rng_unchanged': _rng_digest() == before, 'stdout': printed}
    finally:
        env.close()
    return rec


def _scene_notes(out):
    out.note('each case: BoxelTestEnv(gui=False, scene_config=preset(...)), tray set after the preset call '
             'as main does (test_full_pipeline.py:3214); clients asserted 0 (executing) and 1 (plan twin)')
    out.note('spawn_pose_from_twin: the plan twin body is created at the spawn position and never stepped; '
             'settled_pose_client0: after the env\'s 10 settle steps (boxel_env.py:1003)')
    out.note('global_rng_unchanged: random and np.random states hashed before and after the build '
             '(both seeded 1234 first): the builders draw only from local RandomState (index 0.5)')
    out.note('slip_fixes at the import default (DEFAULT_ON, the CLI default); spec() in constants')


# ----- pin 1: scene per seed -----------------------------------------------

@pin('world', 'p01_scene_presets', 'R1: default (tray off/on), mixed, stack n=3 and scalability 3/4/1 at seeds 0,1,7,13,999',
     timeout=1800)
def p01_scene_presets(out):
    from boxel_env import default_scene, mixed_shapes_scene, stack_scene, scalability_scene
    _set_switches(False)
    _scene_notes(out)
    out.json('state.json', _module_state())
    out.json('default.json', _scene_case('default', default_scene))
    out.json('default_tray.json', _scene_case('default tray', default_scene, tray=True))
    out.json('mixed_seed0.json', _scene_case('mixed seed 0', lambda: mixed_shapes_scene(seed=0)))
    for s in SCENE_SEEDS:
        out.json(f'stack3_seed{s}.json', _scene_case(f'stack 3 seed {s}', lambda: stack_scene(n_objects=3, seed=s)))
    for s in SCENE_SEEDS:
        out.json(f'scalability_3_4_1_seed{s}.json', _scene_case(
            f'scalability 3/4/1 seed {s}',
            lambda: scalability_scene(n_occluders=3, n_targets=4, n_hidden=1, seed=s)))


@pin('world', 'p01_scene_random_pairs', 'R1: random-pairs 3 occ + 1 distractor, the bridge form, run boxels (2 occ, seeds 0-19), tray',
     timeout=2400)
def p01_scene_random_pairs(out):
    from boxel_env import random_pairs_scene
    _set_switches(False)
    _scene_notes(out)
    out.note('run boxels = random-pairs, --n-occluders 2 (run.ps1:42), --n-extra-distractors 0 (run_logger.py:740)')
    out.json('state.json', _module_state())
    for s in SCENE_SEEDS:
        out.json(f'rp_3occ_1dist_seed{s}.json', _scene_case(
            f'random-pairs 3 occ 1 distractor seed {s}',
            lambda: random_pairs_scene(n_occluders=3, extra_distractors=1, seed=s)))
        out.json(f'rp_bridge_form_seed{s}.json', _scene_case(
            f'random_pairs_scene(seed={s})', lambda: random_pairs_scene(seed=s)))
    for s in range(20):
        out.json(f'rp_2occ_seed{s}.json', _scene_case(
            f'random-pairs 2 occ seed {s}', lambda: random_pairs_scene(n_occluders=2, extra_distractors=0, seed=s)))
    out.json('rp_3occ_1dist_seed0_tray.json', _scene_case(
        'random-pairs 3 occ 1 distractor seed 0 tray',
        lambda: random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0), tray=True))
    out.json('rp_2occ_seed0_tray.json', _scene_case(
        'random-pairs 2 occ seed 0 tray', lambda: random_pairs_scene(n_occluders=2, seed=0), tray=True))


@pin('world', 'p01_scene_failures', 'R1: placement scans (which seeds raise, with the exact RuntimeError text)',
     timeout=2400)
def p01_scene_failures(out):
    from boxel_env import random_pairs_scene, scalability_scene, stack_scene
    _set_switches(False)
    out.note('scan: each seed built once; ok rows carry only the object names (the full records are the '
             'other p01 pins), failing rows the exception type and text and the clients left connected')
    out.json('state.json', _module_state())

    def scan(label, make):
        rows = []
        for s in range(30):
            r = _scene_case(f'{label} seed {s}', lambda: make(s))
            if 'raises' in r:
                rows.append({'seed': s, 'raises': r['raises'], 'message': r['message'],
                             'clients_left_connected': r['clients_left_connected'],
                             'global_rng_unchanged': r['global_rng_unchanged']})
            else:
                rows.append({'seed': s, 'ok': [o['name'] for o in r['objects']]})
        return rows
    out.json('scan_rp_3occ_1dist.json', scan('rp 3/1', lambda s: random_pairs_scene(
        n_occluders=3, extra_distractors=1, seed=s)))
    out.json('scan_rp_3occ_3dist.json', scan('rp 3/3', lambda s: random_pairs_scene(
        n_occluders=3, extra_distractors=3, seed=s)))
    out.json('scan_scalability_3_4_2.json', scan('scal 3/4/2', lambda s: scalability_scene(
        n_occluders=3, n_targets=4, n_hidden=2, seed=s)))
    out.json('stack_too_many.json', [_scene_case(f'stack {n} seed 0', lambda: stack_scene(n_objects=n, seed=0))
                                     for n in (12, 16)])


# ----- pin 1b: find_dice scene files (needs the bridge venv) ----------------

def _need_tampura():
    if not os.path.isdir(TW_ENVS):
        raise RuntimeError(f'needs the bridge venv: TAMPURA tree {TW_ENVS} absent')
    for pth in (TW + '/tampura', TW_ENVS):
        if pth not in sys.path:
            sys.path.append(pth)


@pin('world', 'p01b_find_dice_scenes', 'R1b: their world built from every committed generated scene and the 3 shipped ones (needs the bridge venv)',
     timeout=2400)
def p01b_find_dice_scenes(out):
    _need_tampura()
    import warnings
    with captured(), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        from tampura_environments.panda_utils.panda_env_utils import setup_robot
        from tampura_environments.find_dice import env as fd_env
    out.note('needs the bridge venv: /root/armO-venvA with TAMPURA\'s tree on sys.path (run.ps1:149)')
    out.note('the world as their initialize builds it (find_dice/env.py:816-838) without their env object: '
             'setup_robot(vis=False), setup_world(robot, client, categories, poses, vis=False); the file is '
             'named, never picked by their os.listdir loader (BF#8)')
    out.note('sha256_raw: the working-tree bytes (core.autocrlf decides the eol); sha256_lf: CRLF turned LF')
    gen = REPO / 'tampura_bridge' / 'gen_scenes' / 'find_dice'
    shipped = Path(TW_ENVS) / 'tampura_environments' / 'find_dice' / 'problems'
    files = [('gen', f) for f in sorted(gen.glob('find_dice_gen_s*.json'))]
    files += [('shipped', f) for f in sorted(shipped.glob('*.json'))]
    man_raw = (gen / 'manifest.json').read_bytes()
    manifest = json.loads(man_raw.decode('utf-8'))
    out.json('manifest.json', {'sha256_raw': hashlib.sha256(man_raw).hexdigest(),
                               'sha256_lf': hashlib.sha256(man_raw.replace(b'\r\n', b'\n')).hexdigest(),
                               'content': manifest})
    excluded = list(getattr(fd_env, 'EXCLUDE_CLASSES', []))
    rows = []
    for kind, f in files:
        raw = f.read_bytes()
        scene = json.loads(raw.decode('utf-8'))
        if _live_clients():
            raise RuntimeError(f'clients connected before {f.name}: {_live_clients()}')
        with captured() as box, warnings.catch_warnings():
            warnings.simplefilter('ignore')
            robot, client = setup_robot(vis=False)
            world = fd_env.setup_world(robot, client, scene['categories'], scene['poses'], vis=False)
        try:
            body = getattr(robot, 'body', robot)
            arm = robot.get_group_joints(fd_env.ARM_GROUP, client=client)
            grip = robot.get_group_joints(fd_env.GRIPPER_GROUP, client=client)
            rows.append({
                'kind': kind, 'file': f.name,
                'sha256_raw': hashlib.sha256(raw).hexdigest(),
                'sha256_lf': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest(),
                'categories': scene['categories'], 'excluded_class_present': not set(excluded).isdisjoint(scene['categories']),
                'world_categories': list(world.categories), 'n_objects': len(world.objects),
                'object_poses': [list(client.getBasePositionAndOrientation(int(b))) for b in world.objects],
                'environment_bodies': [int(b) for b in world.environment], 'floor': int(world.floor),
                'arm_joints': [list(client.getJointState(int(body), int(j))[:2]) for j in arm],
                'gripper_joints': [list(client.getJointState(int(body), int(j))[:2]) for j in grip],
                'num_bodies': client.getNumBodies(),
                'stdout': box['out'].getvalue()})
        finally:
            client.disconnect()
    out.json('scenes.json', rows)
    out.json('exclude_classes.json', excluded)


# ----- pin 2: first observation and boxels ---------------------------------

def _first_observation_cases():
    from boxel_env import default_scene, stack_scene, scalability_scene, random_pairs_scene
    cases = [('default', default_scene, False),
             ('stack3_seed0', lambda: stack_scene(n_objects=3, seed=0), False),
             ('scalability_3_4_1_seed0', lambda: scalability_scene(n_occluders=3, n_targets=4, n_hidden=1, seed=0), False),
             ('scalability_3_4_1_seed1', lambda: scalability_scene(n_occluders=3, n_targets=4, n_hidden=1, seed=1), False),
             ('rp_3occ_1dist_seed0', lambda: random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0), False),
             ('rp_3occ_1dist_seed1', lambda: random_pairs_scene(n_occluders=3, extra_distractors=1, seed=1), False),
             ('rp_3occ_1dist_seed0_tray', lambda: random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0), True)]
    for s in range(5):
        cases.append((f'rp_2occ_seed{s}', lambda s=s: random_pairs_scene(n_occluders=2, seed=s), False))
    return cases


@pin('world', 'p02_first_observation', 'R2: main\'s first observation, free space, merge and registry (switches off and on)',
     timeout=2400)
def p02_first_observation(out):
    out.note('main lines 858-998 replayed (_first_registry): effective cell = largest object extent + 0.01 '
             'set as the octree min_resolution, 50 settle steps, get_camera_observation, generate_free_space, '
             'merge_free_space_cells, annotate_free_space_surface, BoxelRegistry, record_initial_detections, '
             'save_to_json("boxel_data.json") in the work folder')
    out.note('boxels rows: [id, type, min, max, is_occluder, shadow_boxel_ids, created_by_boxel_id, on_surface, '
             'object_name, created_by_object, surface_z] in registry order; pose fields only for OBJECT boxels')
    out.note('switches "on" = M8, M9, M10, pick_aperture_from_pose all on (what run boxels runs)')
    out.note('a scene whose build raises (scalability 3/4/1 seed 0: placement) is written as the exception '
             'type and text with the clients left connected; seed 1 of the same preset is the built case')
    for label, make, tray in _first_observation_cases():
        for sw in (False, True):
            _set_switches(sw)
            cfg = make()
            if tray:
                cfg.enable_tray = True
            try:
                env, printed = _make_env(cfg)
            except Exception as ex:          # a placement failure is the output (as pin 1 writes it)
                live = _live_clients()
                _disconnect_all()
                out.json(f'{label}_{"on" if sw else "off"}.json', {
                    'state': _module_state(), 'scene_build_raises': type(ex).__name__, 'message': str(ex),
                    'clients_left_connected': live})
                continue
            try:
                r = outcome(_first_registry, env)
                if 'value' not in r:
                    out.json(f'{label}_{"on" if sw else "off"}.json', r)
                    continue
                obs, registry, cell = r.pop('value')
                registry.save_to_json('boxel_data.json')
                text = Path('boxel_data.json').read_text(encoding='utf-8')
                out.json(f'{label}_{"on" if sw else "off"}.json', {
                    'state': _module_state(), 'effective_cell': cell,
                    'visible_objects': obs.visible_objects,
                    'object_poses': {n: [c, q] for n, (c, q) in obs.object_poses.items()},
                    'boxels': [_boxel_tuple(b) for b in registry.boxels.values()],
                    'object_pose_fields': {b.id: _pose_fields(b) for b in registry.boxels.values()
                                           if b.boxel_type.value == 'object'},
                    'boxel_data_json_sha256': text_digest(text),
                    'next_id': registry._next_id, 'stdout': r['stdout']})
                if not sw:
                    out.text(f'{label}_off_boxel_data.json', text)
            finally:
                env.close()
    _set_switches(False)


# ----- pin 3: shadow geometry alone ----------------------------------------

@pin('world', 'p03_shadow_geometry', 'R3: ShadowCalculator on a bare plane and table with hand-made OBJECT boxels')
def p03_shadow_geometry(out):
    import numpy as np
    import pybullet_data
    from boxel_data import BoxelData, BoxelType
    from shadow_calculator import ShadowCalculator
    pb = _pb()
    if _live_clients():
        raise RuntimeError('a client is connected')
    c = pb.connect(pb.DIRECT)
    if c != 0:
        raise RuntimeError(f'bare world on client {c}, not 0')
    try:
        pb.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=c)
        pb.loadURDF('plane.urdf', [0, 0, 0], [0, 0, 0, 1], physicsClientId=c)
        pb.loadURDF('table/table.urdf', [0.5, 0.0, -0.3], [0, 0, 0, 1], useFixedBase=True, physicsClientId=c)
        if pb.getNumBodies(physicsClientId=0) != 2:
            raise RuntimeError('client 0 must hold the plane and the table only')
        tz = 0.625 + (-0.3)                      # boxel_env.py:899-903
        sc = ShadowCalculator(np.array([0.1, -0.8, 0.7]), tz,
                              table_x_range=(-0.4, 0.6), table_y_range=(-0.5, 0.5))
        out.note('client 0: plane.urdf and table/table.urdf at [0.5, 0, -0.3] fixed (boxel_env.py:891-902); '
                 'ShadowCalculator(eye [0.1, -0.8, 0.7], 0.625 + (-0.3), x (-0.4, 0.6), y (-0.5, 0.5)), the '
                 'env\'s values (boxel_env.py:513, 617-620, 903-909); rays on client 0 (physics_client None)')
        out.note('fragment rows: [type, min, max, created_by_object, id] in returned order')

        def ob(name, cx, cy, hx, hy, h, z0=0.0):
            return BoxelData(id=name, boxel_type=BoxelType.OBJECT, object_name=name,
                             min_corner=np.array([cx - hx, cy - hy, tz + z0]),
                             max_corner=np.array([cx + hx, cy + hy, tz + z0 + h]))

        def frag(fs):
            return [[f.boxel_type.value, f.min_corner.tolist(), f.max_corner.tolist(),
                     f.created_by_object, f.id] for f in fs]

        def run(label, obj, obstacles):
            r = outcome(sc.calculate_shadow_boxel, obj, obstacles)
            v = r.pop('value', None)
            return {'case': label, 'object': _boxel_tuple(obj), 'n_obstacles': len(obstacles),
                    'fragments': frag(v) if v is not None else None, **r}
        rows = []
        a = ob('cube', 0.1, 0.1, 0.03, 0.03, 0.06)
        rows.append(run('a one cube on the table', a, []))
        A = ob('occ_a', 0.1, 0.1, 0.03, 0.03, 0.12)
        B = ob('occ_b', 0.12, 0.18, 0.03, 0.03, 0.10)
        rows.append(run('b A with B as obstacle', A, [B]))
        rows.append(run('b B with A as obstacle', B, [A]))
        shadows = []
        for o in sorted([B, A], key=lambda b: b.id):          # generate_boxels order (boxel_env.py:1663-1671)
            obst = [x for x in (A, B) if x.id != o.id] + shadows
            r = run(f'b sequence {o.id}', o, obst)
            rows.append(r)
            shadows.extend(sc.calculate_shadow_boxel(o, obst))
        rows.append(run('c far from the camera, clipped by the table range', ob('far', 0.5, 0.42, 0.03, 0.03, 0.1), []))
        rows.append(run('d held above the table', ob('held', 0.1, 0.1, 0.02, 0.02, 0.04, z0=0.05), []))
        rows.append(run('d just inside the 1 cm on-surface margin', ob('low', 0.1, 0.1, 0.02, 0.02, 0.04, z0=0.009), []))
        T = ob('tall', 0.1, 0.0, 0.03, 0.03, 0.15)
        S = ob('behind', 0.17, 0.12, 0.02, 0.02, 0.05)
        rows.append(run('e two-slab carve (overhang meets an obstacle)', T, [S]))
        rows.append(run('e obstacle inside the shadow', T, [ob('inside', 0.1, 0.2, 0.02, 0.02, 0.04)]))
        rows.append(run('f beyond the table y edge (degenerate)', ob('edge', 0.1, 0.55, 0.03, 0.03, 0.06), []))
        rows.append(run('f beyond the table x edge', ob('xedge', 0.7, 0.0, 0.03, 0.03, 0.06), []))
        out.json('shadows.json', rows)
    finally:
        _disconnect_all()


# ----- pin 6: plan twin sync -----------------------------------------------

@pin('world', 'p06_twin_sync', 'R6: sync_to_plan_client without and with the registry, held body, moved arm (tray scene)')
def p06_twin_sync(out):
    import numpy as np
    import robot_utils
    from boxel_env import random_pairs_scene
    pb = _pb()
    _set_switches(False)
    cfg = random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0)
    cfg.enable_tray = True
    env, _ = _make_env(cfg)
    try:
        with captured():
            obs, registry, _ = _first_registry(env)
        names = {i.object_id: n for n, i in env.objects.items()}
        rid, prid = env.objects['robot'].object_id, env.plan_robot_id
        nj = pb.getNumJoints(prid, physicsClientId=env.plan_client_id)

        def reset_twin():
            for gid, pid in env._gui_to_plan.items():
                pb.resetBasePositionAndOrientation(pid, [3.0, 3.0, 3.0], [0, 0, 0, 1],
                                                   physicsClientId=env.plan_client_id)
            for j in range(nj):
                pb.resetJointState(prid, j, 0.0, targetVelocity=0.0, physicsClientId=env.plan_client_id)

        def twin():
            return {'bodies': {names[g]: list(pb.getBasePositionAndOrientation(p_, physicsClientId=env.plan_client_id))
                               for g, p_ in env._gui_to_plan.items()},
                    'robot_joints': [list(pb.getJointState(prid, j, physicsClientId=env.plan_client_id)[:2])
                                     for j in range(nj)]}
        held = next(n for n in _targets_of(env) if registry.get_boxel(n) is not None)
        parked = [n for n in env.objects if n not in STATIC_NAMES and registry.get_boxel(n) is None
                  and not getattr(env.objects[n], 'is_tray', False)]
        ee = robot_utils.robot_model().ee_link
        cases = []
        reset_twin()
        env.sync_to_plan_client()
        cases.append({'case': '1 no registry', **twin()})
        reset_twin()
        env.sync_to_plan_client(registry=registry)
        cases.append({'case': '2 registry (belief poses, boxel-less bodies parked)', **twin()})
        reset_twin()
        env.sync_to_plan_client(held_body_id=env.objects[held].object_id, registry=registry)
        cases.append({'case': f'3 registry, holding {held}', 'ee_client0': pb.getLinkState(rid, ee, physicsClientId=env.client_id)[0],
                      **twin()})
        q = np.array(robot_utils.REST_POSES) + np.array([0.3, 0.2, -0.2, 0.3, 0.1, -0.2, 0.4])
        for j, v in zip(robot_utils.robot_model().arm_joints, q):
            pb.resetJointState(rid, j, float(v), physicsClientId=env.client_id)
        reset_twin()
        env.sync_to_plan_client(held_body_id=env.objects[held].object_id, registry=registry)
        cases.append({'case': f'4 arm moved on client 0, holding {held}',
                      'ee_client0': pb.getLinkState(rid, ee, physicsClientId=env.client_id)[0], **twin()})
        out.json('twin.json', {'held': held, 'parked_expected': parked, 'park_pose': env._PLAN_CLIENT_PARK,
                               'state': _module_state(), 'cases': cases})
        out.note('scene: random_pairs_scene(3, 1, seed 0) with the tray, switches off, registry of _first_registry; '
                 'the twin is reset (bodies to [3, 3, 3], robot joints to 0) before each case')
        out.note('parked_expected: non-static, non-tray bodies without a boxel (case 2 must show them at the park pose)')
    finally:
        env.close()


# ----- pin 7: init fact set ------------------------------------------------

def _build_planner(env, registry, m8_on, sense_gate='off', corridor='cell+object'):
    """The planner as main builds it (test_full_pipeline.py:1215-1392)."""
    import m8_domain
    from boxel_data import BoxelType
    from execution import compute_shadow_blockers, pick_contact_floor
    from pddlstream_planner import PDDLStreamPlanner
    shadows = [b.id for b in registry.boxels.values() if b.boxel_type == BoxelType.SHADOW]
    occluders = [b.id for b in registry.boxels.values() if b.boxel_type == BoxelType.OBJECT]
    som = compute_shadow_blockers(env.camera_position, registry, shadows, occluders, env)
    object_body_ids = {}
    for name, info in env.objects.items():
        if name not in STATIC_NAMES:
            object_body_ids[name] = env.plan_body_id(info.object_id)
    for b in registry.boxels.values():
        if b.object_name and b.object_name in object_body_ids:
            object_body_ids[b.id] = object_body_ids[b.object_name]
    support = frozenset({env.plan_body_id(env.objects['plane'].object_id),
                         env.plan_body_id(env.objects['table'].object_id)})
    tray_name = next((n for n, i in env.objects.items() if i.is_tray), None)
    planner = PDDLStreamPlanner(registry, robot_id=env.plan_robot_id, shadow_occluder_map=som,
                                physics_client=env.plan_client_id, object_body_ids=object_body_ids,
                                support_body_ids=support, camera_pos=env.camera_position,
                                tray_name=tray_name,
                                domain_file=m8_domain.domain_file(True) if m8_on else None)
    if env.reach_envelope is not None:
        planner.streams.set_reach(*env.reach_envelope)
    planner.streams.contact_floor = pick_contact_floor(env)
    planner.streams.surface_z_default = float(env.table_surface_height)
    planner.sense_gate = sense_gate
    planner.corridor_test = corridor
    return planner, som, shadows, occluders


class _ShuffleRecorder:
    """Test-level wrapper on random.shuffle (the shared module attribute
    pddlstream_planner.random.shuffle): copies the list before and after the
    real shuffle and hashes the global random state around it."""

    def __init__(self):
        import random
        self.random, self.real, self.calls = random, random.shuffle, []

    def __call__(self, x, *a, **k):
        pre = [str(f) for f in x]
        s0 = _py_rng_digest()
        self.real(x, *a, **k)
        self.calls.append({'pre': pre, 'post': [str(f) for f in x], 'rng_before': s0, 'rng_after': _py_rng_digest()})

    def __enter__(self):
        self.random.shuffle = self
        return self

    def __exit__(self, *exc):
        self.random.shuffle = self.real
        return False


def _indices(facts, universe):
    idx = {f: i for i, f in enumerate(universe)}
    return [idx[f] for f in facts]


def _facts_block(calls, universe):
    return [{'pre_idx': _indices(c['pre'], universe), 'post_idx': _indices(c['post'], universe),
             'rng_before': c['rng_before'], 'rng_after': c['rng_after']} for c in calls]


@pin('world', 'p07_init_facts', 'R7: _build_init through export_problem_pddl and create_problem, M8 x sense_gate x corridor, later states',
     timeout=2400)
def p07_init_facts(out):
    import observe_views
    from boxel_data import BoxelType
    from boxel_env import random_pairs_scene, stack_scene
    out.note('per case a fresh planner (names carry counters, streams.py:306-310), built as main does; '
             'sync_to_plan_client(registry) before the export and again before create_problem; '
             'random.seed(7) before the export, random.seed(8) before create_problem; with M8 on, '
             'm8_views and sense_over_region are set between the two calls, as main does (1452-1456)')
    out.note('facts are str(tuple) (R: sorted(set(map(str, init)))); sorted_set is that list; the export and '
             'create_problem blocks give the list before and after random.shuffle as indices into sorted_set, '
             'with the global random state hashed around the shuffle; pre-shuffle order needs PYTHONHASHSEED=0')
    out.note('target: the first non-occluder, non-tray target without a boxel (hidden), else the first target; '
             'visible_target_locations as main 1089-1097 (target named); known_empty_shadows [] for the first plan')
    out.note('m8_stats: keys ending in _s and keys with "time" removed (timings)')
    cases = []

    def run_case(label, env, registry, m8_on, gate, corridor, target_objects, goal, known_empty=(),
                 moved=None, observed_clear=None, on_relations=None, stackable=None, held=None, vtl=None):
        planner, som, shadows, occluders = _build_planner(env, registry, m8_on, gate, corridor)
        env.sync_to_plan_client(registry=registry)
        import random
        with _ShuffleRecorder() as rec, captured() as box:
            random.seed(7)
            path = planner.export_problem_pddl(target_objects=target_objects, goal=goal,
                                               visible_target_locations=vtl,
                                               filepath=os.path.abspath('problem_debug.pddl'))
            n_export = len(rec.calls)
            if m8_on:
                planner.m8_views = observe_views.ObserveViews(env, planner.streams._robot_base_xy)
                planner.sense_over_region = True
            env.sync_to_plan_client(registry=registry)
            random.seed(8)
            planner.create_problem(target_objects, goal, current_config=planner.home_config,
                                   known_empty_shadows=list(known_empty), moved_occluders=moved or {},
                                   observed_clear_regions=observed_clear, visible_target_locations=vtl,
                                   on_relations=on_relations, stackable_objects=stackable, held_obj=held)
        export_text = Path(path).read_text(encoding='utf-8')
        universe = sorted({f for c in rec.calls for f in c['pre']})
        last = [str(f) for f in planner.last_init]
        configs = {}
        for f in planner.last_init:
            for a in f[1:]:
                if hasattr(a, 'joint_positions') and getattr(a, 'name', None):
                    configs[a.name] = a.joint_positions
        stats = {k: v for k, v in sorted((planner.last_m8_stats or {}).items())
                 if not k.endswith('_s') and 'time' not in k}
        cases.append(label)
        safe = label.replace(' ', '_').replace('/', '-').replace('+', 'p')
        out.json(f'case_{len(cases):02d}_{safe}.json', {
            'case': label, 'state': _module_state(), 'sense_gate': gate, 'corridor_test': corridor,
            'target_objects': target_objects, 'goal': goal,
            'shadow_occluder_map_sorted': {k: sorted(v) for k, v in som.items()},
            'sorted_set': universe, 'export': _facts_block(rec.calls[:n_export], universe),
            'create_problem': _facts_block(rec.calls[n_export:], universe),
            'n_shuffle_calls': [n_export, len(rec.calls) - n_export],
            'last_init_idx': _indices(last, universe),
            'export_text_sha256': text_digest(export_text),
            'configs_in_init': {k: configs[k] for k in sorted(configs)},
            'm8_stats': stats})
        out.text(f'case_{len(cases):02d}_export.pddl', export_text)

    def scene(make, tray, sw):
        _set_switches(sw)
        cfg = make()
        cfg.enable_tray = tray
        env, _ = _make_env(cfg)
        with captured():
            obs, registry, _ = _first_registry(env)
        return env, registry

    for sw in (False, True):
        env, registry = scene(lambda: random_pairs_scene(n_occluders=3, extra_distractors=1, seed=0), True, sw)
        try:
            tg = _targets_of(env)
            hidden = [t for t in tg if registry.get_boxel(t) is None]
            target = hidden[0] if hidden else tg[0]
            vtl = {}
            for b in registry.boxels.values():
                if b.object_name == target:
                    vtl[target] = b.id
                    break
            for gate in ('off', 'strict'):
                for corridor in ('cell+object', 'object'):
                    run_case(f'rp tray M8 {"on" if sw else "off"} gate {gate} corridor {corridor}', env, registry,
                             sw, gate, corridor, [target], ('holding', target), vtl=vtl)
            if not sw:
                visible = next(t for t in tg if registry.get_boxel(t) is not None)
                shadows = [b.id for b in registry.boxels.values() if b.boxel_type == BoxelType.SHADOW]
                occl = [b.id for b in registry.boxels.values() if b.boxel_type == BoxelType.OBJECT and b.is_occluder]
                frees = [b.id for b in registry.boxels.values() if b.boxel_type == BoxelType.FREE_SPACE]
                run_case('rp tray later state: held, known empty, moved occluder, observed clear', env, registry,
                         False, 'off', 'cell+object', [target], ('holding', target),
                         known_empty=shadows[:1], moved={occl[0]: frees[0]} if occl and frees else {},
                         observed_clear=frees[1:2], held=visible, vtl=vtl)
        finally:
            env.close()
    env, registry = scene(lambda: stack_scene(n_objects=3, seed=0), False, False)
    try:
        cubes = _targets_of(env)
        vtl = {}
        for t in cubes:
            for b in registry.boxels.values():
                if b.object_name == t:
                    vtl[t] = b.id
                    break
        run_case('stack3 seed0 stackable, one on relation', env, registry, False, 'off', 'cell+object',
                 list(cubes), ('and', ('on', cubes[1], cubes[0])), on_relations={cubes[2]: cubes[0]},
                 stackable=list(cubes), vtl=vtl)
    finally:
        env.close()
    _set_switches(False)
    out.json('cases.json', cases)


# ----- pin 9: stream outputs without search --------------------------------

@pin('world', 'p09_streams', 'R9: sample_grasp, compute_kin_solution, test_boxel_fits, hideability, ee_reachable (default scene)',
     timeout=1800)
def p09_streams(out):
    import numpy as np
    import slip_fixes
    from boxel_data import BoxelData, BoxelType
    from boxel_env import default_scene
    from execution import pick_contact_floor
    from streams import BoxelStreams
    out.note('default_scene, switches off and on (M9 grasps need the fitted pose that '
             'record_initial_detections writes with the switches on); hand boxels added to the registry: '
             'hand_rect (3 x 6 cm), hand_wide (9 x 9 cm), hand_far_free (a free box 1.0 m from the base); '
             '"ghost" has no boxel')
    out.note('one fresh BoxelStreams per call group (counters); contact_floor and surface_z_default as main; '
             'sync_to_plan_client(registry) first (the hideability test raycasts the twin)')
    out.note('grasp_wrist_home on = the default slip set; off = the default set without it (slip_fixes.ENABLED '
             'set directly and restored)')
    saved = slip_fixes.ENABLED
    for sw in (False, True):
        _set_switches(sw)
        env, _ = _make_env(default_scene())
        try:
            with captured():
                obs, registry, _ = _first_registry(env)
            tz = env.table_surface_height
            O = BoxelType.OBJECT
            registry.add_boxel(BoxelData(id='hand_rect', boxel_type=O, object_name='hand_rect',
                                         min_corner=np.array([0.30, -0.33, tz]), max_corner=np.array([0.33, -0.27, tz + 0.05])))
            registry.add_boxel(BoxelData(id='hand_wide', boxel_type=O, object_name='hand_wide',
                                         min_corner=np.array([0.30, 0.25, tz]), max_corner=np.array([0.39, 0.34, tz + 0.05])))
            registry.add_boxel(BoxelData(id='hand_far_free', boxel_type=BoxelType.FREE_SPACE,
                                         min_corner=np.array([0.55, 0.25, tz]), max_corner=np.array([0.65, 0.35, tz + 0.1])))
            env.sync_to_plan_client(registry=registry)
            obj_ids = {}
            for name, info in env.objects.items():
                if name not in STATIC_NAMES:
                    obj_ids[name] = env.plan_body_id(info.object_id)
            support = frozenset({env.plan_body_id(env.objects['plane'].object_id),
                                 env.plan_body_id(env.objects['table'].object_id)})

            def streams():
                s = BoxelStreams(registry, robot_id=env.plan_robot_id, physics_client=env.plan_client_id,
                                 object_body_ids=obj_ids, support_body_ids=support)
                s.contact_floor = pick_contact_floor(env)
                s.surface_z_default = float(env.table_surface_height)
                return s
            objects = [b.id for b in registry.boxels.values() if b.boxel_type == O]
            grasps = {}
            for obj in objects + ['ghost']:
                for wrist in (True, False):
                    slip_fixes.ENABLED = saved if wrist else frozenset(saved - {'grasp_wrist_home'})
                    r = outcome(lambda: [g for (g,) in streams().sample_grasp(obj)])
                    v = r.pop('value', None)
                    grasps[f'{obj} wrist_home={wrist}'] = {'grasps': [_grasp_rec(g) for g in v] if v is not None else None,
                                                          **r}
            slip_fixes.ENABLED = saved
            kin = {}
            red_grasp = next(streams().sample_grasp('red_object'))[0]
            for label, boxel_id, view in (('own boxel', 'red_object', None), ('beyond reach', 'hand_far_free', None),
                                          ('home pseudo-boxel', 'home', None), ('view boxel', 'view_x', 'view_x'),
                                          ('missing boxel', 'nope', None), ('green boxel', 'green_object', None)):
                s = streams()
                if view:
                    s.view_boxel_ids = frozenset({view})
                r = outcome(lambda: [c for (c,) in s.compute_kin_solution('red_object', boxel_id, red_grasp)])
                v = r.pop('value', None)
                kin[label] = {'boxel': boxel_id, 'configs': [_config_rec(c) for c in v] if v is not None else None,
                              'contact_ik_rejects': s.contact_ik_rejects, 'view_kin_skips': s.view_kin_skips, **r}
            s = streams()
            boxel_ids = list(registry.boxels)
            fits = {obj: [bid for bid in boxel_ids if s.test_boxel_fits(obj, bid)] for obj in objects + ['ghost']}
            shadow_ids = [b.id for b in registry.boxels.values() if b.boxel_type == BoxelType.SHADOW]
            hide = {}
            for obj in _targets_of(env) + ['ghost']:
                for sh in shadow_ids:
                    hide[f'{obj} in {sh}'] = s.test_target_can_hide_in_shadow(obj, sh, camera_pos=env.camera_position)
            reach = []
            for rad in (0.5, 0.79, 0.8, 0.81, 0.9):
                for ang in (0.0, 0.7853981633974483, 1.5707963267948966):
                    for z in (0.0, 0.325, 0.6, 0.9):
                        pt = [-0.4 + rad * float(np.cos(ang)), rad * float(np.sin(ang)), z]
                        reach.append([pt, s.ee_reachable(pt)])
            out.json(f'streams_switches_{"on" if sw else "off"}.json', {
                'state': _module_state(), 'grasps': grasps, 'red_grasp': _grasp_rec(red_grasp), 'kin': kin,
                'boxel_fits': fits, 'can_hide': hide, 'ee_reachable': reach,
                'class_defaults': {'contact_floor': BoxelStreams.contact_floor,
                                   'surface_z_default': BoxelStreams.surface_z_default,
                                   'GRASP_MAX_SPAN': BoxelStreams.GRASP_MAX_SPAN,
                                   'GRASP_SQUARE_TOL': BoxelStreams.GRASP_SQUARE_TOL}})
        finally:
            slip_fixes.ENABLED = saved
            env.close()
    _set_switches(False)


@pin('world', 'p09_ik_tables', 'R9: solve_ik on 20 targets, resolve_robot_model, executor helpers, observe_views pure functions')
def p09_ik_tables(out):
    import types
    import numpy as np
    import pybullet_data
    import execution
    import observe_views
    import robot_utils
    pb = _pb()
    if _live_clients():
        raise RuntimeError('a client is connected')
    c = pb.connect(pb.DIRECT)
    if c != 0:
        raise RuntimeError(f'bare world on client {c}, not 0')
    out.note('bare DIRECT client 0 with pybullet_data\'s Panda at [-0.4, 0, 0] fixed (boxel_env.py:918-920); '
             'targets: FK of REST_POSES at the ee link (worldLinkFramePosition) plus a 5 x 4 grid '
             'dx (-0.25, -0.1, 0.05, 0.2, 0.35) x dy (-0.3, -0.1, 0.1, 0.3), dz -0.25 (index open 4: '
             'the construction is this builder\'s)')
    try:
        rb = pb.loadURDF(os.path.join(pybullet_data.getDataPath(), 'franka_panda/panda.urdf'),
                         [-0.4, 0.0, 0.0], [0, 0, 0, 1], useFixedBase=True, physicsClientId=c)

        def model_rec(m):
            return {'arm_joints': list(m.arm_joints), 'finger_joints': list(m.finger_joints), 'ee_link': m.ee_link,
                    'gripper_links_sorted': sorted(m.gripper_links),
                    'ignored_self_pairs_sorted': sorted(list(x) for x in m.ignored_self_pairs),
                    'finger_limits': m.finger_limits}
        m = robot_utils.resolve_robot_model(rb, c)
        models = {'pybullet_data': model_rec(m), 'equals_PANDA_PYBULLET_DATA': m == robot_utils.PANDA_PYBULLET_DATA}
        for j, q in zip(m.arm_joints, robot_utils.REST_POSES):
            pb.resetJointState(rb, j, q, physicsClientId=c)
        ee = np.array(pb.getLinkState(rb, m.ee_link, computeForwardKinematics=True, physicsClientId=c)[4])
        targets = [ee + np.array([dx, dy, -0.25]) for dx in (-0.25, -0.1, 0.05, 0.2, 0.35)
                   for dy in (-0.3, -0.1, 0.1, 0.3)]
        yawed = pb.getQuaternionFromEuler([0, np.pi, 0.6])
        ik = []
        for t in targets:
            for orn_label, orn in (('down', None), ('yaw 0.6', yawed)):
                for seed_label, seed in (('none', None), ('REST_POSES', robot_utils.REST_POSES)):
                    q = robot_utils.solve_ik(rb, t, orn, c, seed=seed)
                    ik.append({'target': t, 'orn': orn_label, 'seed': seed_label,
                               'joints': None if q is None else np.asarray(q)})
        after = [pb.getJointState(rb, j, physicsClientId=c)[0] for j in m.arm_joints]
        out.json('solve_ik.json', {'ee_rest': ee, 'cases': ik, 'arm_after_all_calls': after})
        their = TW_ENVS + '/models/srl/franka_panda/panda.urdf'
        if os.path.isfile(their):
            c2 = pb.connect(pb.DIRECT)
            try:
                rb2 = pb.loadURDF(their, useFixedBase=True, physicsClientId=c2)
                models['tampura_panda'] = model_rec(robot_utils.resolve_robot_model(rb2, c2))
            finally:
                pb.disconnect(physicsClientId=c2)
        else:
            models['tampura_panda'] = 'absent (needs the bridge venv)'
        out.json('robot_models.json', models)
    finally:
        _disconnect_all()
    rows = []
    for name, aabb in (('cube 4 cm', ([0, 0, 0.325], [0.04, 0.04, 0.365])),
                       ('cube 6 cm', ([0, 0, 0.325], [0.06, 0.06, 0.385])),
                       ('tall 15 cm', ([0, 0, 0.325], [0.06, 0.06, 0.475])),
                       ('die 1.6 cm', ([0, 0, 0.325], [0.016, 0.016, 0.341]))):
        for floor in (None, 0.0, 0.0132, 0.035):
            rows.append([name, floor, execution._grasp_ee_to_obj_z(aabb, 0.325, floor)])
    floors = [['attribute missing', execution.pick_contact_floor(types.SimpleNamespace())],
              ['None', execution.pick_contact_floor(types.SimpleNamespace(pick_contact_floor=None))],
              ['0.0132', execution.pick_contact_floor(types.SimpleNamespace(pick_contact_floor=0.0132))]]
    cargo = []
    for floor in (None, 0.0132):
        stub = types.SimpleNamespace(plan_body_id=lambda g: g + 100, table_surface_height=0.325,
                                     pick_contact_floor=floor)
        cargo.append(_config_rec(execution.held_cargo_config(
            [0.1, -0.7, 0.0, -2.3, 0.0, 1.6, 0.8], 'q_readback_3', stub, 7,
            ([0.0, 0.0, 0.325], [0.05, 0.05, 0.4]), [0.001, -0.002])))
    out.json('executor_helpers.json', {'grasp_ee_to_obj_z': rows, 'pick_contact_floor': floors,
                                       'held_cargo_config': cargo})
    lat = [observe_views.lattice([0, 0, 0], [1, 2, 3], n) for n in (1, 2, 3)]
    lat.append(observe_views.lattice([0.1, -0.2, 0.3], [0.4, 0.2, 0.33]))
    quats = {}
    for label, eul in (('identity', (0, 0, 0)), ('z 90', (0, 0, 1.5707963267948966)), ('x 180', (3.141592653589793, 0, 0)),
                       ('y 170 deg', (0, 2.9670597283903604, 0)), ('down yaw 0.6', (0, 3.141592653589793, 0.6)),
                       ('mixed', (0.3, -1.1, 2.4))):
        R = np.array(_pb().getMatrixFromQuaternion(_pb().getQuaternionFromEuler(eul))).reshape(3, 3)
        quats[label] = {'matrix': R, 'quat': observe_views._quat(R)}
    quats['diag(1,-1,-1)'] = {'matrix': np.diag([1.0, -1.0, -1.0]), 'quat': observe_views._quat(np.diag([1.0, -1.0, -1.0]))}
    quats['diag(-1,1,-1)'] = {'matrix': np.diag([-1.0, 1.0, -1.0]), 'quat': observe_views._quat(np.diag([-1.0, 1.0, -1.0]))}
    quats['diag(-1,-1,1)'] = {'matrix': np.diag([-1.0, -1.0, 1.0]), 'quat': observe_views._quat(np.diag([-1.0, -1.0, 1.0]))}
    out.json('observe_views.json', {'lattice': lat, 'quat': quats})


# ----- pin 10: move_robot_smooth step count --------------------------------

@pin('world', 'p10_move_steps', 'R10: move_robot_smooth stepSimulation count per case (default scene)')
def p10_move_steps(out):
    import numpy as np
    import robot_utils
    from boxel_env import default_scene
    pb = _pb()
    _set_switches(False)
    env, _ = _make_env(default_scene())
    out.note('default_scene (finger gear and solver iterations as the pipeline), main\'s 50 settle steps; then '
             'per case the arm reset to REST_POSES (resetJointState, client 0) and move_robot_smooth with '
             'pybullet.stepSimulation and setJointMotorControl2 wrapped (test-level, call through)')
    out.note('steps for settle=False is arithmetic: max(steps, min(ceil(max(delta / (limit * dt))), 1200)); '
             'settle=True adds the convergence hold (physics); final_arm is the readback after the move')
    try:
        for _ in range(50):
            env.step_simulation()
        rid = env.objects['robot'].object_id
        arm = robot_utils.robot_model().arm_joints
        rest = np.array(robot_utils.REST_POSES, dtype=float)
        calls = {'step': 0, 'motor': []}
        real_step, real_motor = pb.stepSimulation, pb.setJointMotorControl2

        def step(*a, **k):
            calls['step'] += 1
            return real_step(*a, **k)

        def motor(*a, **k):
            calls['motor'].append([list(a), {kk: k[kk] for kk in sorted(k)}])
            return real_motor(*a, **k)
        cases = [('tiny', [0.01, 0, 0, 0, 0, 0, 0], 60, False, True),
                 ('tiny steps 10', [0.01, 0, 0, 0, 0, 0, 0], 10, False, True),
                 ('tiny steps 30', [0.01, 0, 0, 0, 0, 0, 0], 30, False, True),
                 ('stretch joint 2', [0, 1.5, 0, 0, 0, 0, 0], 60, False, True),
                 ('stretch joint 6', [0, 0, 0, 0, 0, 2.0, 0], 60, False, True),
                 ('capped at 1200', [11.0, 0, 0, 0, 0, 0, 0], 60, False, True),
                 ('not bounded', [0, 1.5, 0, 0, 0, 0, 0], 60, False, False),
                 ('tiny settle', [0.01, 0, 0, 0, 0, 0, 0], 60, True, True),
                 ('medium settle', [0, 0, 0, 0.5, 0, 0, 0], 60, True, True)]
        rows = []
        pb.stepSimulation, pb.setJointMotorControl2 = step, motor
        try:
            for label, delta, steps, settle, bounded in cases:
                for j, q in zip(arm, rest):
                    pb.resetJointState(rid, j, float(q), targetVelocity=0.0, physicsClientId=env.client_id)
                calls['step'], calls['motor'] = 0, []
                target = (rest + np.array(delta)).tolist()
                robot_utils.move_robot_smooth(rid, target, gui=False, steps=steps, settle=settle,
                                              velocity_bounded=bounded)
                rows.append({'case': label, 'delta': delta, 'steps_arg': steps, 'settle': settle,
                             'velocity_bounded': bounded, 'step_calls': calls['step'],
                             'motor_calls': len(calls['motor']),
                             'motor_sha256': text_digest(dumps(plain(calls['motor']))),
                             'first_motor_calls': calls['motor'][:7],
                             'final_arm': [pb.getJointState(rid, j, physicsClientId=env.client_id)[0] for j in arm]})
        finally:
            pb.stepSimulation, pb.setJointMotorControl2 = real_step, real_motor
        out.json('steps.json', {'state': _module_state(), 'cases': rows,
                                'constants': {'JOINT_VELOCITY_LIMITS': robot_utils.JOINT_VELOCITY_LIMITS,
                                              'SIM_TIMESTEP': robot_utils.SIM_TIMESTEP,
                                              'MAX_INTERP_STEPS': robot_utils.MAX_INTERP_STEPS}})
    finally:
        env.close()


# ----- pins 13 to 16: the stored eye renders --------------------------------

def _fixture_dir():
    return Path(os.environ.get(RENDER_FIXTURE_VAR) or RENDER_FIXTURE_DEFAULT)


def _load_fixture():
    """The renders written by tests/readable/make_render_fixture.py:
    {name: {'depth_buffer', 'seg', 'view', 'proj', 'meta'}}, plus the
    fixture's own FIXTURE.json."""
    import numpy as np
    d = _fixture_dir()
    man = d / 'FIXTURE.json'
    if not man.is_file():
        raise RuntimeError(f'no render fixture: run tests/readable/make_render_fixture.py (or set '
                           f'{RENDER_FIXTURE_VAR}); looked for FIXTURE.json under the fixture folder')
    fixture = json.loads(man.read_text(encoding='utf-8'))
    renders = {}
    for name in fixture['renders']:
        meta = json.loads((d / f'{name}.json').read_text(encoding='utf-8'))
        renders[name] = {'depth_buffer': np.load(d / f'{name}_depth.npy').astype(np.float64),
                         'seg': np.load(d / f'{name}_seg.npy'),
                         'view': tuple(meta['view']), 'proj': tuple(meta['proj']), 'meta': meta}
    return fixture, renders


def _fixture_registry(fixture):
    from boxel_data import BoxelRegistry
    return BoxelRegistry.load_from_json(str(_fixture_dir() / fixture['registry_file']))


def _depth_m(depth_buffer, meta):
    import types
    from boxel_env import BoxelTestEnv
    ns = types.SimpleNamespace(far_plane=meta['far_plane'], near_plane=meta['near_plane'])
    return BoxelTestEnv._depth_buffer_to_meters(ns, depth_buffer)


def _fixture_note(out, fixture):
    out.note('input: the render fixture of tests/readable/make_render_fixture.py (folder from '
             f'{RENDER_FIXTURE_VAR}, default tests/readable/_scratch/render_fixture); fixture.json holds the '
             'sha256 of every fixture file, so another fixture shows as a difference')
    out.json('fixture.json', {'files': fixture['files'], 'renders': fixture['renders'],
                              'scenes': fixture.get('scenes')})


def _det_rec(d):
    return {'name': d.name, 'body_id': d.body_id, 'pixel_count': d.pixel_count, 'est_min': d.est_min,
            'est_max': d.est_max, 'yaw': d.yaw, 'yaw_valid': d.yaw_valid, 'rect_center': d.rect_center,
            'body_extents': d.body_extents, 'pixel_steps': d.pixel_steps, 'raw_xy_ext': d.raw_xy_ext}


@pin('world', 'p13_detections', 'R13: detect_objects_from_render and _rest_on_support on the stored renders')
def p13_detections(out):
    import numpy as np
    from perception import ObjectDetection, _rest_on_support, detect_objects_from_render
    fixture, renders = _load_fixture()
    _fixture_note(out, fixture)
    out.note('per render: min_pixels default and 200; for A also without no_footprint_completion (the tray grown '
             'like any body); detections in dict order, every field')
    res = {}
    for name in ('A', 'B2', 'A2', 'C'):
        r = renders[name]
        meta = r['meta']
        bmap = {int(k): v for k, v in meta['body_id_to_name']}
        trays = frozenset(meta['trays'])
        variants = [('default', {}), ('min_pixels 200', {'min_pixels': 200})]
        if name == 'A':
            variants.append(('no tray exemption', {'no_footprint_completion': frozenset()}))
        for label, kw in variants:
            kwargs = {'no_footprint_completion': trays, **kw}
            dets = detect_objects_from_render(r['seg'], r['depth_buffer'], r['view'], r['proj'], bmap,
                                              meta['camera_xy'], meta['support_z'], **kwargs)
            res[f'{name} {label}'] = [_det_rec(d) for d in dets.values()]
    out.json('detections.json', res)

    def det(name, mn, mx):
        return ObjectDetection(name=name, body_id=1, pixel_count=50, est_min=np.array(mn, dtype=float),
                               est_max=np.array(mx, dtype=float))
    z = 0.325
    hand = {
        'below support (fell off)': {'a': det('a', [0, 0, 0.1], [0.04, 0.04, 0.3])},
        'bottom within snap': {'a': det('a', [0, 0, z + 0.004], [0.04, 0.04, z + 0.04])},
        'floating, nothing under': {'a': det('a', [0, 0, z + 0.05], [0.04, 0.04, z + 0.09])},
        'stacked on another': {'low': det('low', [0, 0, z], [0.05, 0.05, z + 0.05]),
                               'up': det('up', [0.005, 0.005, z + 0.07], [0.045, 0.045, z + 0.1])},
        'small overlap only': {'low': det('low', [0, 0, z], [0.05, 0.05, z + 0.05]),
                               'up': det('up', [0.045, 0.045, z + 0.07], [0.085, 0.085, z + 0.1])},
        'other in front, taller': {'front': det('front', [0, 0, z], [0.05, 0.05, z + 0.2]),
                                   'back': det('back', [0.01, 0.01, z + 0.1], [0.04, 0.04, z + 0.15])},
    }
    rows = {}
    for label, dets in hand.items():
        _rest_on_support(dets, z)
        rows[label] = {k: [v.est_min, v.est_max] for k, v in dets.items()}
    out.json('rest_on_support_hand.json', rows)


def _sense_inputs(renders, name, registry):
    r = renders[name]
    meta = r['meta']
    return r, meta, _depth_m(r['depth_buffer'], meta)


@pin('world', 'p14_sense_render', 'R14: sense_shadow_from_render on the stored renders (A, A2, C) for every fragment')
def p14_sense_render(out):
    import numpy as np
    from boxel_data import BoxelType
    from execution import sense_shadow_from_render
    fixture, renders = _load_fixture()
    _fixture_note(out, fixture)
    registry = _fixture_registry(fixture)
    frags = [b for b in registry.boxels.values() if b.boxel_type == BoxelType.SHADOW]
    meta_a = renders['A']['meta']
    occ_all = sorted(meta_a['occluder_body_ids'])
    support = frozenset({meta_a['plane_id'], meta_a['table_id']} | set(meta_a['tray_ids']))
    targets = [('hidden', meta_a['hidden_target_ids'][0] if meta_a['hidden_target_ids'] else -2),
               ('visible', meta_a['visible_target_ids'][0] if meta_a['visible_target_ids'] else -3),
               ('absent', 99999)]
    occs = [('none', None), ('all', set(occ_all)), ('all but first', set(occ_all[1:]))]
    robots = [('none', None), ('robot', meta_a['robot_id'])]
    sups = [('none', None), ('plane table tray', support)]
    out.note('the full product: render (A, A2, C) x fragment x target (hidden, visible, absent id 99999) x '
             'occluder ids (None, all, all but the first) x robot id (None, robot) x support ids (None, plane '
             'table tray); printed NOTE lines discarded (pin 39\'s); detected bodies and interceptor counts sorted')
    rows = []
    counts = {}
    for name in ('A', 'A2', 'C'):
        r, meta, dm = _sense_inputs(renders, name, registry)
        for f in frags:
            for tl, tid in targets:
                for ol, oids in occs:
                    for rl, rbid in robots:
                        for sl, sids in sups:
                            with captured():
                                o, frac, bodies, bbox, icounts = sense_shadow_from_render(
                                    f, tid, dm, r['seg'], r['view'], r['proj'],
                                    occluder_pybullet_ids=oids, robot_id=rbid, support_body_ids=sids)
                            counts[o] = counts.get(o, 0) + 1
                            rows.append([name, f.id, tl, ol, rl, sl, o, frac, sorted(int(x) for x in bodies),
                                         None if bbox is None else [bbox[0].tolist(), bbox[1].tolist()],
                                         sorted([int(k), v] for k, v in icounts.items())])
    out.json('sense.json', rows)
    out.json('outcome_counts.json', {k: counts[k] for k in sorted(counts)})


@pin('world', 'p15_shadow_blockers', 'R15: compute_shadow_blockers with a stub env returning the stored renders')
def p15_shadow_blockers(out):
    import copy
    import types
    from boxel_data import BoxelType
    from execution import compute_shadow_blockers
    fixture, renders = _load_fixture()
    _fixture_note(out, fixture)
    base = _fixture_registry(fixture)
    out.note('stub env: objects {name: object_id}, detect_objects returns the stored buffer and seg, '
             '_depth_buffer_to_meters BoxelTestEnv\'s formula on far 5.0, near 0.01, '
             '_view_and_projection_matrices the stored matrices; registry rebuilt from the stored boxel_data.json '
             'and deep-copied per case; blocker lists sorted (they come from a set)')
    res = {}
    cases = [('A', 'A', False), ('A2', 'A2', False), ('C', 'C', False),
             ('A2 creators removed (no fallback)', 'A2', True), ('A creators removed', 'A', True)]
    for label, name, strip in cases:
        r = renders[name]
        meta = r['meta']
        reg = copy.deepcopy(base)
        if strip:
            for b in [b for b in reg.boxels.values() if b.boxel_type == BoxelType.OBJECT and b.is_occluder]:
                reg.remove_boxel(b.id)
        env = types.SimpleNamespace(
            objects={n: types.SimpleNamespace(object_id=i) for n, i in meta['objects']},
            camera_position=meta['camera_position'],
            detect_objects=lambda r=r: (None, None, r['depth_buffer'], r['seg']),
            _depth_buffer_to_meters=lambda b, meta=meta: _depth_m(b, meta),
            _view_and_projection_matrices=lambda r=r: (r['view'], r['proj']))
        shadows = [b.id for b in reg.boxels.values() if b.boxel_type == BoxelType.SHADOW]
        objects = [b.id for b in reg.boxels.values() if b.boxel_type == BoxelType.OBJECT]
        o = outcome(compute_shadow_blockers, meta['camera_position'], reg, shadows, objects, env)
        m = o.pop('value', None)
        res[label] = {'map_sorted': None if m is None else {k: sorted(v) for k, v in m.items()},
                      'blocked_fraction': {s: getattr(reg.get_boxel(s), 'blocked_fraction', None) for s in shadows},
                      **o}
    out.json('blockers.json', res)


@pin('world', 'p16_fragment_render', 'R16: _fragment_renders_empty and _shrink_shadow_fragment on the stored renders')
def p16_fragment_render(out):
    import copy
    import numpy as np
    from boxel_data import BoxelData, BoxelType
    from execution import _fragment_renders_empty, _shrink_shadow_fragment, sense_shadow_from_render
    fixture, renders = _load_fixture()
    _fixture_note(out, fixture)
    base = _fixture_registry(fixture)
    frags = [b for b in base.boxels.values() if b.boxel_type == BoxelType.SHADOW]
    tz = renders['A']['meta']['support_z']
    extra = [BoxelData(id='hand_zero_height', boxel_type=BoxelType.SHADOW,
                       min_corner=np.array([0.1, 0.1, tz]), max_corner=np.array([0.2, 0.2, tz])),
             BoxelData(id='hand_partly_outside_image', boxel_type=BoxelType.SHADOW,
                       min_corner=np.array([-1.2, 0.2, tz]), max_corner=np.array([-0.6, 0.4, tz + 0.05]))]
    out.note('_fragment_renders_empty: every fragment plus a zero-height box and a box partly outside the image, '
             'on A, A2, C with render (depth in metres, seg, view, proj)')
    out.note('_shrink_shadow_fragment: the still_blocked bboxes of sense_shadow_from_render on A (real occluder '
             'set, robot id, support ids) for each fragment, plus hand cases; fragment and registry deep-copied '
             'per case; viz None; printed lines discarded')
    empty = {}
    for name in ('A', 'A2', 'C'):
        r = renders[name]
        render = (_depth_m(r['depth_buffer'], r['meta']), r['seg'], r['view'], r['proj'])
        for f in frags + extra:
            empty[f'{name} {f.id}'] = _fragment_renders_empty(f, render)
    out.json('renders_empty.json', empty)
    r = renders['A']
    meta = r['meta']
    dm = _depth_m(r['depth_buffer'], meta)
    support = frozenset({meta['plane_id'], meta['table_id']} | set(meta['tray_ids']))
    shrink = []

    def do(label, f, bmin, bmax):
        reg = copy.deepcopy(base)
        fd = reg.get_boxel(f.id) if reg.get_boxel(f.id) is not None else copy.deepcopy(f)
        centres = {}
        with captured():
            ret = _shrink_shadow_fragment(reg, fd, bmin, bmax, None, centres)
        shrink.append({'case': label, 'fragment': f.id, 'blocked_min': bmin, 'blocked_max': bmax,
                       'returned': ret, 'min_after': fd.min_corner, 'max_after': fd.max_corner,
                       'boxel_centers': {k: v for k, v in centres.items()},
                       'registry_dirty_attr': getattr(reg, '_dirty', None)})
    for f in frags:
        with captured():
            o, frac, _, bbox, _ = sense_shadow_from_render(
                f, -1, dm, r['seg'], r['view'], r['proj'], occluder_pybullet_ids=set(meta['occluder_body_ids']),
                robot_id=meta['robot_id'], support_body_ids=support)
        if bbox is not None:
            do(f'from the sense on A ({o})', f, bbox[0], bbox[1])
    f0 = frags[0]
    mn, mx = np.asarray(f0.min_corner, dtype=float), np.asarray(f0.max_corner, dtype=float)
    do('degenerate (new box within 1 mm)', f0, mn, mn + np.array([0.0005, 1.0, 1.0]))
    do('reveal under 2 mm on every axis', f0, mn + 0.0009, mx - 0.0009)
    do('meaningful reveal', f0, mn, (mn + mx) / 2.0)
    do('box covering all (no change)', f0, mn - 1.0, mx + 1.0)
    out.json('shrink.json', shrink)


# ----- pin 21: executor motion record (written last) ------------------------

class _CallRecorder:
    """Test-level wrappers on pybullet module attributes: every call of the
    named functions with its arguments, and runs of stepSimulation."""
    NAMES = ('setJointMotorControl2', 'setJointMotorControlArray', 'resetJointState',
             'createConstraint', 'changeConstraint', 'removeConstraint', 'changeDynamics',
             'resetBasePositionAndOrientation')

    def __init__(self):
        self.pb = _pb()
        self.seq, self.counts, self.real = [], {}, {}

    def _wrap(self, name, real):
        def w(*a, **k):
            self.counts[name] = self.counts.get(name, 0) + 1
            if name == 'stepSimulation':
                if self.seq and self.seq[-1][0] == 'steps':
                    self.seq[-1][1] += 1
                else:
                    self.seq.append(['steps', 1])
            else:
                self.seq.append([name, plain(list(a)), plain({kk: k[kk] for kk in sorted(k)})])
            return real(*a, **k)
        return w

    def __enter__(self):
        for n in self.NAMES + ('stepSimulation',):
            self.real[n] = getattr(self.pb, n)
            setattr(self.pb, n, self._wrap(n, self.real[n]))
        return self

    def __exit__(self, *exc):
        for n, f in self.real.items():
            setattr(self.pb, n, f)
        return False


@pin('world', 'p21_pick_record', 'R21: one scripted pick of red_object in the default scene, motor calls and step runs recorded',
     timeout=1200)
def p21_pick_record(out):
    import numpy as np
    import robot_utils
    import execution
    from boxel_env import default_scene
    from execution import pick_contact_floor
    from streams import BoxelStreams
    pb = _pb()
    _set_switches(True)
    robot_utils.GRIP_SQUEEZE = 0.5 / 1000.0
    out.note('default_scene, switches on (run boxels), GRIP_SQUEEZE 0.0005 (main 776), slip fixes default; '
             '_first_registry; BoxelStreams as main; grasp = the first of sample_grasp(red_object); config = the '
             'first of compute_kin_solution(red_object, red_object, grasp); move_robot_smooth(config, steps 60, '
             'settle True) to the approach; then the recorder and execute_pick(..., obj_aabb=(min, max), pose=boxel)')
    out.note('sequence: every recorded call as [name, args, kwargs] and stepSimulation runs as ["steps", n]; '
             'written whole as its sha256 and the first and last 60 entries')
    env, _ = _make_env(default_scene())
    try:
        with captured():
            obs, registry, _ = _first_registry(env)
        env.sync_to_plan_client(registry=registry)
        obj_ids = {n: env.plan_body_id(i.object_id) for n, i in env.objects.items() if n not in STATIC_NAMES}
        support = frozenset({env.plan_body_id(env.objects['plane'].object_id),
                             env.plan_body_id(env.objects['table'].object_id)})
        s = BoxelStreams(registry, robot_id=env.plan_robot_id, physics_client=env.plan_client_id,
                         object_body_ids=obj_ids, support_body_ids=support)
        s.contact_floor = pick_contact_floor(env)
        s.surface_z_default = float(env.table_surface_height)
        obj = 'red_object'
        bd = registry.get_boxel(obj)
        grasp = next(s.sample_grasp(obj))[0]
        config = next(s.compute_kin_solution(obj, obj, grasp))[0]
        rid = env.objects['robot'].object_id
        with captured() as box:
            robot_utils.move_robot_smooth(rid, config.joint_positions, steps=60, settle=True)
        before = {'arm': robot_utils.arm_joint_positions(rid, env.client_id),
                  'object_pose': list(pb.getBasePositionAndOrientation(env.objects[obj].object_id,
                                                                     physicsClientId=env.client_id))}
        with _CallRecorder() as rec, captured() as box:
            res = execution.execute_pick(rid, env, obj, bd.center, grasp, config, False,
                                         obj_aabb=(bd.min_corner, bd.max_corner), pose=bd)
        seq = rec.seq
        out.json('pick.json', {
            'state': _module_state(), 'grasp': _grasp_rec(grasp), 'config': _config_rec(config),
            'before': before,
            'result': {'held_body_id': res[0], 'config': _config_rec(res[1]),
                       'touched_sorted': sorted(str(x) for x in (res[2] or ()))},
            'after': {'arm': robot_utils.arm_joint_positions(rid, env.client_id),
                      'object_pose': list(pb.getBasePositionAndOrientation(env.objects[obj].object_id,
                                                                         physicsClientId=env.client_id))},
            'call_counts': {k: rec.counts[k] for k in sorted(rec.counts)},
            'sequence_len': len(seq), 'sequence_sha256': text_digest(dumps(seq)),
            'sequence_first': seq[:60], 'sequence_last': seq[-60:],
            'stdout_sha256': text_digest(box['out'].getvalue())})
    finally:
        env.close()
        _set_switches(False)


# ----- pin 35: bridge pure parts -------------------------------------------

@pin('world', 'p35_bridge_pure', 'R35: symbol_names, task_spec hash and constants, search_options_from, episode_outcome')
def p35_bridge_pure(out):
    import types
    from tampura_bridge import env_adapter, task_spec
    from pddlstream_planner import search_options_from
    os.environ.pop('BRIDGE_SCENE_MANIFEST', None)
    bg = _load_tool('bridge_gates')
    out.note('bridge_gates loaded by path with BRIDGE_SCENE_MANIFEST removed from the environment (R S-g); '
             'task_spec: the file sha256 (raw bytes and CRLF turned LF) and repr of every upper-case constant, '
             'sorted by name (a repr with an address is written as its type name)')
    gen = REPO / 'tampura_bridge' / 'gen_scenes' / 'find_dice'
    syms = []
    for f in sorted(gen.glob('find_dice_gen_s*.json')):
        cats = json.loads(f.read_text(encoding='utf-8'))['categories']
        syms.append([f.name, cats, env_adapter.symbol_names(cats)])
    shipped = Path(TW_ENVS) / 'tampura_environments' / 'find_dice' / 'problems'
    for f in sorted(shipped.glob('*.json')) if shipped.is_dir() else []:
        cats = json.loads(f.read_text(encoding='utf-8'))['categories']
        syms.append([f.name, cats, env_adapter.symbol_names(cats)])
    for cats in (['a_cups_ud', 'a_cups_ud', 'dice', 'a_cups_ud'], [], ['x'], ['b', 'a', 'b', 'a', 'c']):
        syms.append(['synthetic', cats, env_adapter.symbol_names(cats)])
    out.json('symbol_names.json', syms)
    raw = Path(task_spec.__file__).read_bytes()
    consts = {}
    for k in sorted(vars(task_spec)):
        if k.isupper():
            rp = repr(getattr(task_spec, k))
            consts[k] = type(getattr(task_spec, k)).__name__ if ' at 0x' in rp else rp
    out.json('task_spec.json', {'sha256_raw': hashlib.sha256(raw).hexdigest(),
                                'sha256_lf': hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest(),
                                'constants': consts})
    table = []
    for ew, ic in (('1', 3), ('off', 0), ('0.5', 0), ('off', 5), ('2.5', 3), ('0', 0), ('1e-3', 1)):
        table.append([ew, ic, outcome(search_options_from, ew, ic)])
    out.json('search_options_from.json', table)
    rows = []
    for rewards in ([], [0.0], [1.0], [0.0, 1.0], [1.0, 0.0]):
        for error in (None, '', 'x'):
            for gates in ((), (('G1', 'PASS', 'ok'),), (('G1', 'FAIL', 'bad'), ('G2', 'PASS', '')),
                          (('G3', 'FAIL', 'one'), ('G3', 'FAIL', 'two'))):
                rep = bg.Report()
                for g in gates:
                    rep.add(*g)
                rows.append([rewards, error, [list(g) for g in gates], bg.episode_outcome(rewards, error, rep)])
    out.json('episode_outcome.json', rows)


@pin('world', 'p35b_bridge_table', 'R35: env_adapter.shadow_table_ranges from their module (needs the bridge venv)')
def p35b_bridge_table(out):
    _need_tampura()
    import warnings
    with captured(), warnings.catch_warnings():
        warnings.simplefilter('ignore')
        from tampura_bridge import env_adapter
        r = env_adapter.shadow_table_ranges()
    out.note('needs the bridge venv (TAMPURA\'s tree on sys.path)')
    out.json('shadow_table_ranges.json', r)


# ===========================================================================
# Group "episode": whole episodes and episode starts (index phase0/index/episode_path.md)
# ===========================================================================
#
# Every pin here runs a whole episode or an episode start, headless, through
# tools/readable/record_episode.py (one child interpreter per episode, its
# cwd and environment as run.ps1 builds them).  The caller runs the group
# under flock /root/sb_pipeline.lock and through the health gate (PLAN rule
# 17); nothing here takes the lock.  The written files are the episode's
# normalised outputs (record_episode.normalise: times and wall clocks
# masked to <s> with their keys kept, pids removed, plan_obj and Type@id
# mapped to their order of first use, paths and stamps masked); files named
# INFO_* (line numbers, seconds) are not compared.
#
#   p30_*            pin 30's real runs: rp0 with a synthetic one-call tape,
#                    a no-plan with no text (planner_failed) and a no-plan
#                    whose text names two skeletons (no_plan_binding_death).
#   p34_start_rp*    pin 34: random-pairs seeds 0 to 4 up to the first plan()
#                    call (main's parameters at entry, the stage B switches,
#                    the first plan() keyword arguments, boxel_data.json,
#                    problem_initial.pddl, the ledger, eye and console).
#   p46_bridge_*     pin 46: the bridge driver up to the first plan() call
#                    with the gate hooks installed (shipped seeds 0, 1, 5,
#                    generated seed 100); gate counts in first_plan.json.
#   p47_replay_*     pin 47: the tapes recorded live on the checkpoint
#                    (READABLE_TAPES/<episode>/tape, made by
#                    "record_episode.py --record-set"), replayed; vs_live.json
#                    holds the differences from the live episode's own
#                    normalised outputs (PLAN 24.3 (a)).

TAPES_VAR = 'READABLE_TAPES'
EPISODE_PIN_TIMEOUT_S = 3600
BINDING_DEATH_TEXT = [
    'Stream plan (1, 0, 0.000): [sample-grasp:(orange_object)->(#g0)]\n',
    'Stream plan (2, 1, 0.000): [sample-grasp:(orange_object)->(#g1)]\n',
    'Summary: {complexity: 3, cost: inf, evaluations: 12, iterations: 2, length: inf, '
    'run_time: 1.000, sample_time: 0.000, search_time: 1.000, skeletons: 2, solutions: 0, '
    'solved: False, timeout: False}\n',
]


def _episode_tool():
    import importlib.util
    mod = sys.modules.get('readable_record_episode')
    if mod is None:
        spec = importlib.util.spec_from_file_location(
            'readable_record_episode', str(REPO / 'tools' / 'readable' / 'record_episode.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['readable_record_episode'] = mod
        spec.loader.exec_module(mod)
    return mod


def _write_norm_files(out, run_dir, skip=()):
    norm = Path(run_dir) / 'norm'
    for f in sorted(norm.iterdir()):
        if f.is_file() and f.name not in skip:
            out.text(f.name, f.read_text(encoding='utf-8'))


def _episode_notes(out, tool, name):
    for line in tool.entry_notes(name) + tool.episode_notes():   # the entry's, then the recorder's
        out.note(line)


def _synthetic_noplan(out, chunks, label):
    tool = _episode_tool()
    work = Path.cwd()
    tape = work / 'tape'
    tool.write_synthetic_tape(tape, [((None, float('inf'), None), chunks)])
    res = tool.run_episode('rp0', 'replay', work / 'run', tape=tape, log=lambda s: None)
    _episode_notes(out, tool, 'rp0')
    out.note(f'pin 30 real run: rp0 with a synthetic one-call tape ({label}); the solver answer is '
             'replaced (plan() itself runs, builds the init and reads the text), PLAN 5.2 row 30')
    _write_norm_files(out, work / 'run')
    out.text('INFO_seconds.txt', f"{res['seconds']}\n")


@pin('episode', 'p30_planner_failed', 'R30: rp0 to the planner_failed ending (synthetic tape: no plan, no text)',
     timeout=EPISODE_PIN_TIMEOUT_S)
def p30_planner_failed(out):
    _synthetic_noplan(out, [], 'no plan, no solver text')


@pin('episode', 'p30_binding_death', 'R30: rp0 to the no_plan_binding_death ending (synthetic tape: no plan, two skeletons in the text)',
     timeout=EPISODE_PIN_TIMEOUT_S)
def p30_binding_death(out):
    _synthetic_noplan(out, BINDING_DEATH_TEXT, 'no plan, text with two skeleton lines and a Summary')


def _first_plan(out, name):
    tool = _episode_tool()
    work = Path.cwd()
    res = tool.run_episode(name, 'first-plan', work / 'run', log=lambda s: None)
    _episode_notes(out, tool, name)
    out.note('first-plan mode: PDDLStreamPlanner.plan replaced (in the child only) by a recorder that writes '
             'its bound arguments, the stage B module switches, the RNG digest and the gate counts, then '
             'raises StopAtPlan; main\'s parameters from a sys.setprofile hook at its first call')
    out.note('first_plan.json known_empty_shadows and other set-valued arguments: sorted_from_set lists')
    for line in tool.first_plan_notes():     # gate 7: P8, E3 and R's S-b
        out.note(line)
    _write_norm_files(out, work / 'run')
    out.text('INFO_seconds.txt', f"{res['seconds']}\n")


def _p34(seed):
    def f(out):
        _first_plan(out, f'rp{seed}')
    f.__name__ = f'p34_start_rp{seed}'
    return f


for _s in range(5):
    pin('episode', f'p34_start_rp{_s}',
        f'R34: random-pairs seed {_s} (run boxels -Headless) up to the first plan() call',
        timeout=EPISODE_PIN_TIMEOUT_S)(_p34(_s))


def _p46(seed):
    def f(out):
        _need_tampura()
        _first_plan(out, f'br{seed}')
        out.note('needs the bridge venv (TAMPURA\'s tree at /root/tampura-work); seeds 1 and 5 load '
                 'another scene than the campaign pins on this machine (index 12): '
                 '--allow-g19-mismatch 1 as run.ps1 -Headless passes it')
    f.__name__ = f'p46_bridge_start_s{seed}'
    return f


for _s in (0, 1, 5, 100):
    pin('episode', f'p46_bridge_start_s{_s}',
        f'P46: the bridge driver, seed {_s}{" (generated)" if _s >= 100 else ""}, up to the first plan() '
        f'call with the gate hooks installed (needs the bridge venv)',
        timeout=EPISODE_PIN_TIMEOUT_S)(_p46(_s))


def _tapes_root():
    root = os.environ.get(TAPES_VAR)
    if not root:
        raise RuntimeError(f'needs READABLE_TAPES: a folder written by "record_episode.py '
                           f'--record-set <folder>" on the checkpoint')
    return Path(root)


def _p47(name):
    def f(out):
        tool = _episode_tool()
        if tool.EPISODES[name]['kind'] == 'bridge':
            _need_tampura()
        live = _tapes_root() / name
        if not (live / 'tape' / 'calls.jsonl').exists():
            raise RuntimeError(f'needs READABLE_TAPES: no tape for {name} under {live}')
        work = Path.cwd()
        res = tool.run_episode(name, 'replay', work / 'run', tape=live / 'tape', rng='restore',
                               trace_main=True, log=lambda s: None)
        _episode_notes(out, tool, name)
        out.note('replay: pddlstream_planner.solve replaced by tests/readable/replay_stub.py before the '
                 'gate hooks wrap it; call k returns tape solution k, prints its text into the tee and '
                 'restores the live RNG states after the call (rng restore)')
        out.note('vs_live.json: this replay against the live episode recorded with the tape '
                 '(READABLE_TAPES/<episode>/norm), PLAN 24.3 (a)')
        _write_norm_files(out, work / 'run')
        out.json('vs_live.json', tool.compare_live(live / 'norm', work / 'run' / 'norm'))
        lines = work / 'run' / 'rec' / 'main_lines.json'
        if lines.exists():
            out.text('INFO_main_lines.json', lines.read_text(encoding='utf-8'))
            out.json('INFO_coverage.json', tool.coverage_table([lines]))
        out.text('INFO_seconds.txt', f"{res['seconds']}\n")
    f.__name__ = f'p47_replay_{name}'
    return f


for _e in ('rp0', 'rp1', 'rp1o3', 'stack0', 'br0', 'br5'):
    pin('episode', f'p47_replay_{_e}',
        f'P47: episode {_e} replayed from its recorded tape (needs READABLE_TAPES'
        + ('; needs the bridge venv)' if _e.startswith('br') else ')'),
        timeout=EPISODE_PIN_TIMEOUT_S)(_p47(_e))


# Pin 47's scripted tapes (PLAN 5.2 row 47 "one scripted sense-only plan per
# sense outcome", 24.3 (b) and (e), REVIEW_PHASE0 B3): made from the live
# tapes of READABLE_TAPES by tools/readable/scripted_tapes.py, some with the
# test-level executor stubs of tests/readable/executor_stubs.py.

def _scripted_tool():
    import importlib.util
    mod = sys.modules.get('readable_scripted_tapes')
    if mod is None:
        spec = importlib.util.spec_from_file_location(
            'readable_scripted_tapes', str(REPO / 'tools' / 'readable' / 'scripted_tapes.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['readable_scripted_tapes'] = mod
        spec.loader.exec_module(mod)
    return mod


def _p47s(scenario):
    def f(out):
        tool, st = _episode_tool(), _scripted_tool()
        work = Path.cwd()
        info = st.build(scenario, _tapes_root(), work / 'tape')
        name = info['episode']
        if tool.EPISODES[name]['kind'] == 'bridge':
            _need_tampura()
        stubs = info['stubs'] if info['stubs'].get('stubs') else None
        res = tool.run_episode(name, 'replay', work / 'run', tape=work / 'tape', rng='restore',
                               trace_main=True, log=lambda s: None, stubs=stubs)
        _episode_notes(out, tool, name)
        out.note(f'scripted tape {scenario}: {st.SCENARIOS[scenario]}; made by '
                 'tools/readable/scripted_tapes.py from READABLE_TAPES/' + name + '; live calls copied, '
                 'scripted calls cut from live plans (replay_stub.scripted_solution), no action invented')
        if stubs:
            out.note('executor stubs (tests/readable/executor_stubs.py, in the episode child only): '
                     + json.dumps(stubs, sort_keys=True))
        out.json('script.json', {'scenario': scenario, 'episode': name, 'stubs': info['stubs'],
                                 'calls': info['calls']})
        _write_norm_files(out, work / 'run')
        lines = work / 'run' / 'rec' / 'main_lines.json'
        if lines.exists():
            out.text('INFO_main_lines.json', lines.read_text(encoding='utf-8'))
            out.json('INFO_coverage.json', tool.coverage_table([lines]))
        out.json('INFO_run.json', {'seconds': res['seconds'], 'tfp_copy': res.get('tfp_copy'),
                                   'source_tape_sha256': info['source_tape_sha256']})
    f.__name__ = f'p47_scripted_{scenario}'
    return f


def _register_scripted():
    for _sc in _scripted_tool().SCENARIOS:
        pin('episode', f'p47_scripted_{_sc}',
            f'P47: scripted tape {_sc} (needs READABLE_TAPES'
            + ('; needs the bridge venv)' if _sc.startswith('home') else ')'),
            timeout=EPISODE_PIN_TIMEOUT_S)(_p47s(_sc))


_register_scripted()


# ===========================================================================
# Group "console": pin 27, runs and made tapes through the real Console
# ===========================================================================
#
# Every pin plays one tape through console_ui's Console with
# tools/readable/console_replay.py: one child interpreter per environment
# set (plain, ascii, color, color_ascii), its stdout a pipe (the static
# layout), the clock frozen.  Written per set: console.txt (the [console]
# lines of the debug file, R's compared output), terminal.txt, debug.txt and
# run.json; per pin inputs.json (the tape's calls, the anchors that placed
# the ledger rows, the derived header and summary arguments).
# INFO_tape.json and INFO_coverage.json are not compared.
#
#   p27_made_*   the made tapes of R's plan review S-d (console_replay.MADE):
#                a sample line per regex rule, a row of every ledger kind,
#                every end status, the stderr, log, say, warn and terminal()
#                paths, a G19 stop before the run, a crash, an interrupt.
#   p27_run_*    archived bridge runs (tracked in the repo): the ledger, the
#                run log and bridge_episode.json as recorded.
#   p27_tape_*   the live runs behind pin 47's tapes (READABLE_TAPES), the
#                run's own ledger and run log.

CONSOLE_PIN_TIMEOUT_S = 900
CONSOLE_RUNS = {
    'bf45_s10': 'archive/tampura_bridge_plan_2026-10-25/bf/BF45_46/s10_headless_2026-10-30_14-02-25/'
                'ours/run_2026-10-30_14-03-01',
    'bf38_s0': 'archive/tampura_bridge_plan_2026-10-25/bf/BF38_q14/seed0_sq0.5mm/ours/run_2026-10-30_09-00-03',
}
CONSOLE_TAPE_RUNS = ('rp0', 'rp1o3', 'stack0', 'br0', 'br5')


def _console_tool():
    import importlib.util
    mod = sys.modules.get('readable_console_replay')
    if mod is None:
        spec = importlib.util.spec_from_file_location(
            'readable_console_replay', str(REPO / 'tools' / 'readable' / 'console_replay.py'))
        mod = importlib.util.module_from_spec(spec)
        sys.modules['readable_console_replay'] = mod
        spec.loader.exec_module(mod)
    return mod


def _console_play(out, tape, info=None):
    tool = _console_tool()
    bad = tool.check_tape(tape)
    if bad:
        raise RuntimeError('bad tape: ' + '; '.join(bad[:5]))
    tool.play(tape, out.folder, tool.DEFAULT_ENVS)
    tool.write_inputs(out.folder, tape, info, tool.coverage([tape]))
    out.note('console_replay: one child per environment set (plain, ascii: NO_COLOR; color, color_ascii: '
             'FORCE_COLOR; *ascii: SB_CONSOLE_ASCII), stdout a pipe, LC_ALL=C.UTF-8, TERM=dumb, '
             'time.perf_counter and time.strftime frozen in the child')
    out.note('masks: the replay folder <RUN>, <REPO>, the source run <SRC> and its save folder <SAVE>, '
             'the early debug file\'s random name, console_replay.py line numbers in a traceback')


def _p27_made(name):
    def f(out):
        _console_play(out, _console_tool().made_tape(name))
        out.note(f'made tape {name} (console_replay.MADE), R\'s plan review S-d')
    f.__name__ = f'p27_made_{name}'
    return f


for _m in _console_tool().MADE:
    pin('console', f'p27_made_{_m}', f'R27: the made tape {_m} through the real Console',
        timeout=CONSOLE_PIN_TIMEOUT_S)(_p27_made(_m))


def _p27_run(key):
    def f(out):
        tape, info = _console_tool().build_run_tape(REPO / CONSOLE_RUNS[key])
        _console_play(out, tape, info)
        out.note(f'archived run {CONSOLE_RUNS[key]}: ledger.jsonl, run log, bridge_episode.json')
    f.__name__ = f'p27_run_{key}'
    return f


for _k in CONSOLE_RUNS:
    pin('console', f'p27_run_{_k}', f'R27: the archived bridge run {_k} (ledger and run log) through the real Console',
        timeout=CONSOLE_PIN_TIMEOUT_S)(_p27_run(_k))


def _console_tape_run(name):
    live = _tapes_root() / name
    runs = sorted((live / 'work' / 'logs').glob('run_*')) + sorted((live / 'save' / 'ours').glob('run_*'))
    runs = [r for r in runs if r.is_dir() and (r / 'ledger.jsonl').exists()]
    if not runs:
        raise RuntimeError(f'needs READABLE_TAPES: no live run with a ledger under {live}')
    return runs[-1]


def _p27_tape(name):
    def f(out):
        run = _console_tape_run(name)
        tape, info = _console_tool().build_run_tape(run)
        _console_play(out, tape, info)
        out.note(f'the live run behind pin 47\'s tape {name} (READABLE_TAPES/{name}), recorded with '
                 f'--log-level normal: its ledger and run log as a smart run writes them')
    f.__name__ = f'p27_tape_{name}'
    return f


for _e in CONSOLE_TAPE_RUNS:
    pin('console', f'p27_tape_{_e}', f'R27: the live run of pin 47\'s tape {_e} through the real Console '
        f'(needs READABLE_TAPES)', timeout=CONSOLE_PIN_TIMEOUT_S)(_p27_tape(_e))


if __name__ == '__main__':
    sys.exit(main())
