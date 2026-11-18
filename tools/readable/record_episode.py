"""record_episode.py: one whole episode, headless, with the solver's answers
recorded or replayed (Phase 0 of the readable migration, PLAN 5.2 pin 47 and
24.3, pins 30, 34 and 46).

    python tools/readable/record_episode.py --episode rp0 --mode record --run-dir DIR
    python tools/readable/record_episode.py --episode rp0 --mode replay --run-dir DIR --tape DIR/tape
    python tools/readable/record_episode.py --episode br0 --mode first-plan --run-dir DIR
    python tools/readable/record_episode.py --record-set SET --episodes rp0,rp1,stack0,br0,br5
    python tools/readable/record_episode.py --renorm DIR          # normalise a run folder again
    python tools/readable/record_episode.py --coverage DIR [DIR ...]

The tool never takes the pipeline lock itself: its caller runs it under
``flock /root/sb_pipeline.lock`` (a nested flock on the same file from a
child would wait for ever).  Whole episodes go through the health gate
(tracks/meeting_2026-11-13/scripts/gate_run.ps1).

The parent starts one child interpreter per episode (cwd, environment and
argv as ``run boxels -Headless`` and ``run tampura -Headless`` build them,
run.ps1:149-171, with ``--log-level normal`` so no console takes over the
terminal, and ``--no-telemetry`` for boxels as the eval runner passes it).
The child patches only inside its own process, never a pipeline file:

  record      ``pddlstream_planner.solve`` is wrapped when that module has
              been executed (an import hook, so the import order of the real
              entry is kept, PLAN rule 6).  Each call stores, at the time of
              the call, the returned solution (pickle), the text the solver
              printed into plan()'s ``_StdoutTee`` during the call (the chunks
              added by this call only), the init facts and goal of the
              problem, the RNG digests before and after, and the RNG states
              after.  The wrapper is set before tampura_bridge.gate_hooks
              wraps ``solve``, so the gate wrapper stays the outermost one and
              G11 still sees plan() as the caller.
  replay      tests/readable/replay_stub.py's stub is set the same way: call
              k returns a fresh unpickled copy of solution k, prints the
              stored text into the tee, and (``--rng restore``, the default)
              puts back the RNG states the live search left, so the draws
              after the call are the live ones.  A call beyond the tape stops
              the run (ReplayTapeError, a BaseException nothing in the
              pipeline catches).  ``--trace-main`` records the lines of
              test_full_pipeline.py that ran (sys.settrace, the coverage
              table of PLAN 24.3 (b)); it changes no value.
  first-plan  ``PDDLStreamPlanner.plan`` is replaced by a recorder that
              writes its keyword arguments, the module switches set by
              main's stage B, the RNG digests and (bridge) the gate counts,
              then raises StopAtPlan.  main's parameters at entry come from a
              sys.setprofile hook that removes itself at main's first call.

After the child the parent writes RESULT.json and the normalised outputs
(``norm/``): times, pids and wall clocks removed, ``plan_obj`` ints and
``Type@id`` strings mapped to their order of first use (PLAN 24.3 (d)),
paths and stamps masked.  Nothing here edits a plan between planner and
executor in the pipeline: the replay is test code (PLAN D9).
"""
import argparse
import ast
import contextlib
import hashlib
import importlib.abc
import importlib.machinery
import importlib.util
import json
import os
import pickle
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve()
STUB_FILE = REPO / 'tests' / 'readable' / 'replay_stub.py'
TFP = REPO / 'test_full_pipeline.py'
DRIVER = REPO / 'tampura_bridge' / 'run_bridge_on_finddice.py'
TW = '/root/tampura-work'
TW_ENVS = TW + '/tampura_environments'
GEN_DIR = REPO / 'tampura_bridge' / 'gen_scenes' / 'find_dice'
EPISODE_TIMEOUT_S = 3600

_BOXELS = ['--no-gui', '--log-level', 'normal', '--no-telemetry']


def _rp(seed):
    # run.ps1:170 (run boxels: random-pairs, holding, 2 occluders) -Headless.
    return {'kind': 'boxels', 'argv': ['--no-gui', '--scene', 'random-pairs', '--seed', str(seed),
                                       '--goal', 'holding', '--n-occluders', '2',
                                       '--log-level', 'normal', '--no-telemetry']}


def _br(seed, gen=False):
    # run.ps1:142-166 (run tampura -Headless [-Gen]).
    return {'kind': 'bridge', 'gen': gen,
            'argv': ['--global-seed', str(seed), '--vis', '0', '--save-dir', '<SAVE>',
                     '--allow-g19-mismatch', '1', '--log-level', 'normal']}


EPISODES = {f'rp{s}': _rp(s) for s in range(5)}
# Seed 1 with run boxels' 2 occluders is rejected at the pre-flight ("Could
# not place 2 hidden targets"), so rp1 is a pre-flight crash; rp1o3 is seed 1
# with the CLI's default 3 occluders, a whole episode.
EPISODES['rp1o3'] = {'kind': 'boxels', 'argv': ['--no-gui', '--scene', 'random-pairs', '--seed', '1',
                                                '--goal', 'holding', '--n-occluders', '3',
                                                '--log-level', 'normal', '--no-telemetry']}
EPISODES['stack0'] = {'kind': 'boxels', 'argv': ['--no-gui', '--scene', 'stack', '--seed', '0',
                                                 '--goal', 'stack', '--log-level', 'normal',
                                                 '--no-telemetry']}
EPISODES.update({'br0': _br(0), 'br1': _br(1), 'br5': _br(5), 'br100': _br(100, gen=True)})
PIN47_EPISODES = ('rp0', 'rp1', 'rp1o3', 'stack0', 'br0', 'br5')


# ---------------------------------------------------------------------------
# Small helpers shared with tests/readable/replay_stub.py
# ---------------------------------------------------------------------------

_ADDR = re.compile(r' at 0x[0-9a-fA-F]+')


def atom_text(x):
    """One fact argument as stable text: names stay names, a stream object
    is Type:name, numbers by repr, anything else by repr with addresses
    masked."""
    if isinstance(x, str):
        return x
    if isinstance(x, (bool, int, float)):
        return repr(x)
    if isinstance(x, (tuple, list)):
        return '(' + ' '.join(atom_text(v) for v in x) + ')'
    name = getattr(x, 'name', None)
    if isinstance(name, str) and name:
        return f'{type(x).__name__}:{name}'
    if hasattr(x, 'tolist'):
        return repr(x.tolist())
    return _ADDR.sub(' at 0x?', repr(x))


def problem_facts(problem):
    """(init facts as text in list order, goal as text) of a PDDLProblem."""
    init = getattr(problem, 'init', None)
    goal = getattr(problem, 'goal', None)
    return ([atom_text(f) for f in (init or [])], atom_text(goal))


def rng_digest():
    """sha256 of the global random and np.random states."""
    import random
    import numpy as np
    n = np.random.get_state()
    h = hashlib.sha256(repr(random.getstate()).encode())
    h.update(repr((n[0], n[1].tolist(), n[2], n[3], n[4])).encode())
    return h.hexdigest()


def rng_states():
    import random
    import numpy as np
    return pickle.dumps((random.getstate(), np.random.get_state()))


def set_rng_states(blob):
    import random
    import numpy as np
    py, nps = pickle.loads(blob)
    random.setstate(py)
    np.random.set_state(nps)


def planner_on_stack(depth=8):
    """The PDDLStreamPlanner whose plan() frame is up the stack (the caller
    of solve, or of the gate wrapper around it), or None."""
    f = sys._getframe(1)
    for _ in range(depth):
        if f is None:
            return None
        if f.f_code.co_name == 'plan':
            me = f.f_locals.get('self')
            if me is not None and hasattr(me, 'streams'):
                return me
        f = f.f_back
    return None


def stream_ints(planner):
    """The int attributes of planner.streams (its name counters
    _config_counter, _traj_counter, _grasp_counter and counts such as
    view_kin_skips), sorted by name."""
    s = getattr(planner, 'streams', None)
    if s is None:
        return None
    return {k: v for k, v in sorted(vars(s).items()) if type(v) is int}


def tee_chunks():
    """The chunk list of plan()'s _StdoutTee if sys.stdout is one, else None."""
    s = sys.stdout
    if type(s).__name__ == '_StdoutTee' and isinstance(s.__dict__.get('chunks'), list):
        return s.__dict__['chunks']
    return None


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, allow_nan=True,
                                     default=_default) + '\n', encoding='utf-8', newline='\n')


def _default(o):
    if hasattr(o, 'tolist'):
        return o.tolist()
    if isinstance(o, (set, frozenset)):
        return sorted(_default_key(v) for v in o)
    if isinstance(o, Path):
        return str(o)
    return _ADDR.sub(' at 0x?', repr(o))


def _default_key(v):
    return v if isinstance(v, (str, int, float)) else repr(v)


def append_jsonl(path, row):
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(row, ensure_ascii=False, allow_nan=True, default=_default) + '\n')
        f.flush()
        os.fsync(f.fileno())


def _write_bytes(path, data):
    with open(path, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _plain_kwargs(kw):
    return {k: (v if isinstance(v, (str, int, float, bool, type(None))) else _default(v))
            for k, v in sorted(kw.items())}


# ---------------------------------------------------------------------------
# The tape: what the recorder writes, what the stub reads
# ---------------------------------------------------------------------------
# pickle, not JSON: a solution holds the streams' RobotConfig, Trajectory and
# Grasp objects with numpy arrays, and the stub must hand plan() the same
# kind of objects.  A tape is only ever read back from a folder this tool
# wrote on this machine (scratch, or the stored set made on the checkpoint),
# never from outside input.

def tape_calls(tape_dir):
    p = Path(tape_dir) / 'calls.jsonl'
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding='utf-8').splitlines() if ln.strip()]


def tape_write_call(tape_dir, k, solution, chunks, facts, goal, rng_before, kwargs,
                    raised=None, streams_before=None, streams_after=None):
    """Store call k (0-based) at the time of the call."""
    tape = Path(tape_dir)
    tape.mkdir(parents=True, exist_ok=True)
    cert = 'kept'
    try:
        blob = pickle.dumps(solution)
    except Exception as ex:          # the certificate is not read by plan()
        plan, cost = solution[0], solution[1]
        blob = pickle.dumps((plan, cost, None))
        cert = f'dropped ({type(ex).__name__}: {ex})'
    _write_bytes(tape / f'solution_{k:04d}.pkl', blob)
    _write_bytes(tape / f'rng_{k:04d}.pkl', rng_states())
    write_json(tape / f'text_{k:04d}.json', list(chunks))
    plan = solution[0] if solution is not None else None
    append_jsonl(tape / 'calls.jsonl', {
        'k': k, 'plan_len': (None if plan is None else len(plan)),
        'cost': repr(solution[1]) if solution is not None else None,
        'certificate': cert, 'n_chunks': len(chunks),
        'text_sha256': hashlib.sha256(''.join(chunks).encode('utf-8')).hexdigest(),
        'rng_before': rng_before, 'rng_after': rng_digest(), 'raised': raised,
        'stream_ints_before': streams_before, 'stream_ints_after': streams_after,
        'kwargs': _plain_kwargs(kwargs), 'goal': goal,
        'facts_sha256': hashlib.sha256('\n'.join(facts).encode('utf-8')).hexdigest(),
        'facts': facts})


def write_synthetic_tape(tape_dir, calls):
    """A tape made by hand: calls = [(solution, chunks), ...].  No facts and
    no RNG states of a live search exist, so the stub keeps the RNG as it is
    for these calls (rng_after is None)."""
    tape = Path(tape_dir)
    if tape.exists():
        shutil.rmtree(tape)
    tape.mkdir(parents=True)
    for k, (solution, chunks) in enumerate(calls):
        _write_bytes(tape / f'solution_{k:04d}.pkl', pickle.dumps(solution))
        write_json(tape / f'text_{k:04d}.json', list(chunks))
        append_jsonl(tape / 'calls.jsonl', {
            'k': k, 'synthetic': True, 'plan_len': None if solution[0] is None else len(solution[0]),
            'cost': repr(solution[1]), 'n_chunks': len(chunks),
            'text_sha256': hashlib.sha256(''.join(chunks).encode('utf-8')).hexdigest(),
            'rng_before': None, 'rng_after': None, 'facts': None, 'goal': None})


# ---------------------------------------------------------------------------
# The child: patches inside its own process, then runs the entry as __main__
# ---------------------------------------------------------------------------

class StopAtPlan(BaseException):
    """First-plan mode: the run stops at the first plan() call."""


class _PatchOnLoad(importlib.abc.MetaPathFinder):
    """Call fn(module) right after `name` has been executed by its normal
    import, wherever and whenever the pipeline imports it."""

    def __init__(self, name, fn):
        self.name, self.fn = name, fn

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.name:
            return None
        sys.meta_path.remove(self)
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return spec
        loader, fn = spec.loader, self.fn
        orig_exec = loader.exec_module

        def exec_module(module):
            orig_exec(module)
            fn(module)
        loader.exec_module = exec_module
        return spec


def _load_stub():
    spec = importlib.util.spec_from_file_location('readable_replay_stub', str(STUB_FILE))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['readable_replay_stub'] = mod
    spec.loader.exec_module(mod)
    return mod


def make_recorder(orig_solve, tape_dir):
    """The record-mode wrapper of pddlstream_planner.solve."""
    count = {'k': 0}

    def solve(problem, *args, **kwargs):
        k = count['k']
        count['k'] += 1
        facts, goal = problem_facts(problem)
        before = rng_digest()
        planner = planner_on_stack()
        s_before = stream_ints(planner)
        chunks = tee_chunks()
        n0 = len(chunks) if chunks is not None else 0
        try:
            solution = orig_solve(problem, *args, **kwargs)
        except BaseException as ex:
            added = list(chunks[n0:]) if chunks is not None else []
            tape_write_call(tape_dir, k, (None, float('inf'), None), added, facts, goal, before,
                            kwargs, raised=f'{type(ex).__name__}: {ex}',
                            streams_before=s_before, streams_after=stream_ints(planner))
            raise
        added = list(chunks[n0:]) if chunks is not None else []
        tape_write_call(tape_dir, k, solution, added, facts, goal, before, kwargs,
                        streams_before=s_before, streams_after=stream_ints(planner))
        return solution
    solve.__wrapped__ = orig_solve
    return solve


def _plain_value(v, depth=0):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if depth > 4:
        return type(v).__name__
    if isinstance(v, dict):
        return {str(k): _plain_value(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_plain_value(x, depth + 1) for x in v]
    if isinstance(v, (set, frozenset)):
        return {'sorted_from_set': sorted(atom_text(x) for x in v)}
    if hasattr(v, 'joint_positions'):
        return {'type': type(v).__name__, 'name': getattr(v, 'name', None),
                'joint_positions': _plain_value(getattr(v, 'joint_positions'), depth + 1)}
    if hasattr(v, 'tolist'):
        return v.tolist()
    if callable(v):
        return f'<callable {getattr(v, "__qualname__", type(v).__name__)}>'
    if hasattr(v, '__dataclass_fields__'):
        return {'type': type(v).__name__,
                **{f: _plain_value(getattr(v, f, None), depth + 1) for f in v.__dataclass_fields__}}
    return {'type': type(v).__name__}


def module_switches():
    """The module state main's stage B sets (test_full_pipeline.py 767-806),
    read at the first plan() call."""
    out = {}
    mods = sys.modules
    if 'pose_belief' in mods:
        out['pose_belief.SWITCHES'] = dict(mods['pose_belief'].SWITCHES)
    if 'robot_utils' in mods:
        ru = mods['robot_utils']
        out['robot_utils.GRIP_SQUEEZE'] = ru.GRIP_SQUEEZE
        try:
            out['robot_utils.robot_model_is_pybullet_data'] = ru.robot_model() == ru.PANDA_PYBULLET_DATA
        except Exception as ex:
            out['robot_utils.robot_model'] = f'{type(ex).__name__}'
    if 'world_eye' in mods:
        we = mods['world_eye']
        out['world_eye.SAVE_IMAGES'] = we.SAVE_IMAGES
        out['world_eye._ACTIVE'] = type(we._ACTIVE).__name__ if we._ACTIVE is not None else None
    if 'slip_fixes' in mods:
        sf = mods['slip_fixes']
        out['slip_fixes.ENABLED (sorted from a frozenset)'] = sorted(sf.ENABLED)
        out['slip_fixes.KNOWN (order of registration)'] = list(sf.KNOWN)
    if 'telemetry' in mods:
        act = mods['telemetry']._ACTIVE
        out['telemetry._ACTIVE'] = (None if act is None else
                                    {'type': type(act).__name__,
                                     'counts_only': getattr(act, 'counts_only', None)})
    if 'world_counts' in mods:
        wc = mods['world_counts']
        out['world_counts._noticed'] = dict(wc._noticed)
        out['world_counts._reported'] = dict(wc._reported)
    return out


def make_first_plan_recorder(orig_plan, rec_dir):
    import functools
    import inspect
    sig = inspect.signature(orig_plan)

    @functools.wraps(orig_plan)
    def plan(self, *args, **kwargs):
        bound = sig.bind(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = {k: _plain_value(v) for k, v in bound.arguments.items() if k != 'self'}
        rec = {'plan_kwargs': arguments,
               'plan_kwargs_passed': sorted(kwargs),
               'module_switches': module_switches(),
               'rng_digest': rng_digest(),
               'planner': {'type': type(self).__name__,
                           'search_options': _plain_value(getattr(self, 'search_options', None)),
                           'search_sample_ratio': getattr(self, 'search_sample_ratio', None),
                           'domain_sha256': hashlib.sha256(
                               getattr(self, 'domain_pddl', '').encode('utf-8')).hexdigest(),
                           'stream_sha256': hashlib.sha256(
                               getattr(self, 'stream_pddl', '').encode('utf-8')).hexdigest()}}
        gh = sys.modules.get('tampura_bridge.gate_hooks')
        if gh is not None and gh.installed():
            rec['gate'] = {'counts': gh.counts(), 'info': dict(gh._info), 'steps': dict(gh._steps),
                           'solve_calls': gh._solve_calls}
        write_json(Path(rec_dir) / 'first_plan.json', rec)
        raise StopAtPlan('first plan() call reached')
    return plan


def _install_main_params_hook(rec_dir, tfp_path):
    """main's parameters at entry (sys.setprofile; removed at the call)."""
    target = os.path.realpath(tfp_path)
    seen = {}

    def prof(frame, event, arg):
        if event != 'call' or frame.f_code.co_name != 'main':
            return
        code = frame.f_code
        if code not in seen:
            seen[code] = os.path.realpath(code.co_filename) == target
        if not seen[code]:
            return
        sys.setprofile(None)
        names = code.co_varnames[:code.co_argcount + code.co_kwonlyargcount]
        params = {n: _plain_value(frame.f_locals.get(n)) for n in names}
        write_json(Path(rec_dir) / 'main_params.json', {'order': list(names), 'values': params})
    sys.setprofile(prof)


class _LineTrace:
    """Lines of one file that ran, per function (co_name, first line)."""

    def __init__(self, path):
        self.target = os.path.realpath(path)
        self.known = {}
        self.reached = {}

    def _glob(self, frame, event, arg):
        code = frame.f_code
        hit = self.known.get(code)
        if hit is None:
            hit = self.known[code] = (os.path.realpath(code.co_filename) == self.target)
        if not hit:
            return None
        lines = self.reached.setdefault(f'{code.co_name}:{code.co_firstlineno}', set())

        def local(frame, event, arg):
            if event == 'line':
                lines.add(frame.f_lineno)
            return local
        return local

    def start(self):
        sys.settrace(self._glob)

    def dump(self, path):
        sys.settrace(None)
        write_json(path, {k: sorted(v) for k, v in sorted(self.reached.items())})


def _absolute_log_dir(mod):
    """Boxels runs only: RunLogger's relative log_dir ('logs', the __main__
    block's default) resolved against the cwd.  The export joins a relative
    run directory to the code directory (pddlstream_planner.py:434-439), so
    a run started outside the checkout would stop there; a real `run boxels`
    starts in the checkout (run.ps1:171), where both resolve alike.  Only the
    path's spelling changes (it is masked in every output)."""
    import functools
    import inspect
    orig = mod.RunLogger.__init__
    sig = inspect.signature(orig)

    @functools.wraps(orig)
    def __init__(self, *args, **kwargs):
        b = sig.bind(self, *args, **kwargs)
        b.apply_defaults()
        b.arguments['log_dir'] = os.path.abspath(str(b.arguments['log_dir']))
        return orig(*b.args, **b.kwargs)
    mod.RunLogger.__init__ = __init__


def child_main(a):
    rec = Path(a.rec)
    rec.mkdir(parents=True, exist_ok=True)
    script = os.path.abspath(a.script)
    trace = None
    if os.path.realpath(script) == os.path.realpath(TFP):
        sys.meta_path.insert(0, _PatchOnLoad('run_logger', _absolute_log_dir))
    if a.mode in ('record', 'replay'):
        if a.mode == 'record':
            def patch(mod):
                mod.solve = make_recorder(mod.solve, a.tape)
        else:
            stub = _load_stub()

            def patch(mod):
                stub.install(mod, a.tape, rec, rng=a.rng)
        sys.meta_path.insert(0, _PatchOnLoad('pddlstream_planner', patch))
    elif a.mode == 'first-plan':
        def patch(mod):
            mod.PDDLStreamPlanner.plan = make_first_plan_recorder(mod.PDDLStreamPlanner.plan, rec)
        sys.meta_path.insert(0, _PatchOnLoad('pddlstream_planner', patch))
        _install_main_params_hook(rec, TFP)
    else:
        raise SystemExit(f'unknown mode {a.mode}')
    if a.trace_main:
        trace = _LineTrace(TFP)
    sys.argv = [script] + list(a.argv)
    sys.path[0] = os.path.dirname(script)
    code, how = 0, 'returned'
    try:
        if trace is not None:
            trace.start()
        import runpy
        runpy.run_path(script, run_name='__main__')
    except SystemExit as ex:
        how = 'system_exit'
        code = ex.code if isinstance(ex.code, int) else (0 if ex.code is None else 1)
        if not isinstance(ex.code, (int, type(None))):
            how = f'system_exit: {ex.code}'
    except StopAtPlan:
        how, code = 'stopped at the first plan() call', 0
    except BaseException as ex:
        name = type(ex).__name__
        how = f'raised {name}: {ex}'
        code = 5 if name == 'ReplayTapeError' else 1
        (rec / 'CRASH.txt').write_text(traceback.format_exc(), encoding='utf-8')
    finally:
        if trace is not None:
            trace.dump(rec / 'main_lines.json')
    write_json(rec / 'EXIT.json', {'code': code, 'how': how})
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


# ---------------------------------------------------------------------------
# The parent: one episode in a child, then RESULT.json and norm/
# ---------------------------------------------------------------------------

def episode_env(spec, extra=None):
    env = dict(os.environ)
    for k in ('FORCE_COLOR', 'NO_COLOR', 'SB_CONSOLE_ASCII', 'SB_AUDIO', 'SB_VOICE',
              'PYTHONSTARTUP', 'PYTHONINSPECT', 'BOXEL_EYE_IMAGES', 'BRIDGE_SCENE_MANIFEST',
              'PYTHONPATH'):
        env.pop(k, None)
    env.update({'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1', 'COLUMNS': '80',
                'LINES': '24', 'LC_ALL': 'C.UTF-8', 'LANG': 'C.UTF-8', 'TERM': 'dumb',
                'MPLBACKEND': 'Agg', 'PYTHONIOENCODING': 'utf-8'})
    if spec['kind'] == 'bridge':
        # run.ps1:149, the pddlstream_lib entry included as it builds it.
        env['PYTHONPATH'] = f'{REPO}:{REPO}/pddlstream_lib:{TW}/tampura:{TW_ENVS}'
        if spec.get('gen'):
            env['BRIDGE_SCENE_MANIFEST'] = str(GEN_DIR / 'manifest.json')
    env.update(extra or {})
    return env


def prepare(name, run_dir):
    """(script, argv, cwd) of episode `name` in run_dir (made fresh)."""
    spec = EPISODES[name]
    run_dir = Path(run_dir)
    if spec['kind'] == 'boxels':
        work = run_dir / 'work'
        work.mkdir(parents=True, exist_ok=True)
        return spec, TFP, list(spec['argv']), work
    if not os.path.isdir(TW_ENVS):
        raise RuntimeError(f'needs the bridge venv: TAMPURA tree {TW_ENVS} absent')
    save = run_dir / 'save'
    argv = [str(save) if x == '<SAVE>' else x for x in spec['argv']]
    if spec.get('gen'):
        seed = argv[argv.index('--global-seed') + 1]
        d = run_dir / 'gen'
        probs = d / 'tampura_environments' / 'find_dice' / 'problems'
        probs.mkdir(parents=True, exist_ok=True)
        shutil.copy2(GEN_DIR / f'find_dice_gen_s{seed}.json', probs)
        link = d / 'env_configs'
        if not link.exists():
            os.symlink(TW_ENVS + '/env_configs', link)
        return spec, DRIVER, argv, d
    return spec, DRIVER, argv, Path(TW_ENVS)


def pipeline_run_dir(run_dir, spec):
    base = Path(run_dir) / ('work/logs' if spec['kind'] == 'boxels' else 'save/ours')
    runs = sorted(base.glob('run_*')) if base.is_dir() else []
    return runs[-1] if runs else None


def run_episode(name, mode, run_dir, tape=None, rng='restore', trace_main=False,
                timeout=EPISODE_TIMEOUT_S, log=print):
    """Run episode `name` in a child process; returns the RESULT dict."""
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    spec, script, argv, cwd = prepare(name, run_dir)
    rec = run_dir / 'rec'
    if mode == 'record':
        tape = run_dir / 'tape'
        tape.mkdir()
        (tape / 'calls.jsonl').touch()       # a run that never plans has an empty tape
    cmd = [sys.executable, str(HERE), '--child', '--mode', mode, '--rec', str(rec),
           '--script', str(script), '--rng', rng]
    if tape is not None:
        cmd += ['--tape', str(Path(tape).resolve())]
    if trace_main:
        cmd += ['--trace-main']
    cmd += ['--'] + argv
    t0 = time.monotonic()
    status = 'ended'
    with open(run_dir / 'stdout.txt', 'wb') as out, open(run_dir / 'stderr.txt', 'wb') as err:
        proc = subprocess.Popen(cmd, cwd=str(cwd), env=episode_env(spec), stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL)
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()                  # our own child only
            rc = proc.wait()
            status = 'timeout'
    seconds = time.monotonic() - t0
    pr = pipeline_run_dir(run_dir, spec)
    exit_info = {}
    if (rec / 'EXIT.json').exists():
        exit_info = json.loads((rec / 'EXIT.json').read_text(encoding='utf-8'))
    result = {'episode': name, 'mode': mode, 'rng': rng, 'status': status, 'rc': rc,
              'child_exit': exit_info, 'argv': argv, 'script': str(script), 'cwd': str(cwd),
              'pipeline_run_dir': str(pr) if pr else None, 'seconds': round(seconds, 1),
              'tape': str(tape) if tape is not None else None}
    write_json(run_dir / 'RESULT.json', result)
    write_norm(run_dir)
    log(f'[record_episode] {name} {mode}: rc {rc}, {status}, {seconds:.0f} s, '
        f'{exit_info.get("how", "no EXIT.json")}')
    return result


# ---------------------------------------------------------------------------
# Normalisation (times, pids, addresses, paths) and comparison
# ---------------------------------------------------------------------------

TYPE_AT_ID = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)@(\d+)\b')
HEX_ADDR = re.compile(r'0x[0-9a-fA-F]{6,}')
STAMP = re.compile(r'\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}')
# Ledger fields that are times or clocks (index episode_path.md section 5).
LEDGER_DROP = {'t', 'wall'}
LEDGER_DROP_BY_KIND = {'ledger_open': {'pid'}, 'plan': {'plan_time_s'}}
# Console text that is a time (masked, the rest of the line kept).
CONSOLE_MASKS = [
    (re.compile(r'elapsed=\d+\.\d+s'), 'elapsed=<T>s'),
    (re.compile(r'(\[timing\] planner\.plan\(\) #\d+: )[\d.]+s \(cumulative [\d.]+s\)'),
     r'\1<T>s (cumulative <T>s)'),
    (re.compile(r'(Cumulative planning time : )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(Average per call\s+: )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(Per-call \(s\)\s+: )\[[^\]]*\]'), r'\1[<T>]'),
    (re.compile(r'(twin renders )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(over-region folds )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'(total )[\d.]+s'), r'\1<T>s'),
    (re.compile(r'( at 0x)[0-9a-fA-F]+'), r'\1?'),
    # G18's detail (tools/bridge_gates.py): the driver's clock stamps.
    (re.compile(r'(initialize return to rollout start )\d+\.\d+ s'), r'\1<T> s'),
    (re.compile(r'(_[a-z0-9]+ )\+\d+\.\d+ s'), r'\1+<T> s'),
]


class IdMap:
    """plan_obj ints and Type@id strings to their order of first use, keyed
    by (plan id, value) so a freed address reused by a later plan is a new
    token (index episode_path.md section 4); hex addresses likewise."""

    def __init__(self):
        self.objs, self.types, self.hexes = {}, {}, {}

    def obj(self, plan_id, value):
        if value is None:
            return None
        key = (plan_id, value)
        if key not in self.objs:
            self.objs[key] = f'obj#{len(self.objs) + 1}'
        return self.objs[key]

    def text(self, plan_id, s):
        def typ(m):
            key = (plan_id, m.group(0))
            if key not in self.types:
                self.types[key] = len(self.types) + 1
            return f'{m.group(1)}@#{self.types[key]}'

        def hx(m):
            if m.group(0) not in self.hexes:
                self.hexes[m.group(0)] = len(self.hexes) + 1
            return f'0x#{self.hexes[m.group(0)]}'
        return HEX_ADDR.sub(hx, TYPE_AT_ID.sub(typ, s))


class Masker:
    def __init__(self, pairs):
        self.pairs = sorted(((str(a), b) for a, b in pairs if a), key=lambda t: -len(t[0]))

    def __call__(self, s):
        for a, b in self.pairs:
            if a in s:
                s = s.replace(a, b)
        s = STAMP.sub('<STAMP>', s)
        for rx, rep in CONSOLE_MASKS:
            s = rx.sub(rep, s)
        return s


def _walk(obj, fn):
    if isinstance(obj, str):
        return fn(obj)
    if isinstance(obj, list):
        return [_walk(v, fn) for v in obj]
    if isinstance(obj, dict):
        return {fn(k) if isinstance(k, str) else k: _walk(v, fn) for k, v in obj.items()}
    return obj


def _read_jsonl(path):
    if not path or not Path(path).exists():
        return None
    rows = []
    for ln in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
        if ln.strip():
            try:
                rows.append(json.loads(ln))
            except json.JSONDecodeError:
                rows.append({'unparsable_line': ln})
    return rows


def norm_ledger(rows, mask):
    ids = IdMap()
    out = []
    for r in rows or []:
        r = dict(r)
        for k in LEDGER_DROP | LEDGER_DROP_BY_KIND.get(r.get('kind'), set()):
            r.pop(k, None)
        kind = r.get('kind')
        if kind == 'bridge_timing':
            r = {k: v for k, v in r.items() if not k.endswith('_s')}
        if kind == 'driver_clock' and isinstance(r.get('events'), list):
            r['events'] = [e[0] if isinstance(e, list) and e else e for e in r['events']]
        pid = r.get('plan_id', r.get('plan'))
        if 'plan_obj' in r:
            r['plan_obj'] = ids.obj(pid, r['plan_obj'])
        r = _walk(r, lambda s: ids.text(pid, mask(s)))
        out.append(r)
    return out


EYE_DROP = {'t_wall'}


def norm_eye(rows, mask):
    out = []
    for r in rows or []:
        r = {k: v for k, v in r.items() if k not in EYE_DROP}
        if isinstance(r.get('extra'), dict):
            r['extra'] = {k: v for k, v in r['extra'].items() if k != 'plan_time_s'}
        out.append(_walk(r, mask))
    return out


SUMMARY_DROP = {'total_planning_time_s', 'per_call_planning_time_s', 'counts_cost_s'}


def _drop_time_keys(obj):
    if isinstance(obj, dict):
        return {k: _drop_time_keys(v) for k, v in obj.items()
                if not (k in SUMMARY_DROP or (k.endswith('_s') and isinstance(v, (int, float))
                                              and not isinstance(v, bool)))}
    if isinstance(obj, list):
        return [_drop_time_keys(v) for v in obj]
    return obj


def norm_console(text, mask):
    lines = []
    for ln in text.splitlines():
        ln = mask(ln)
        for rx, rep in CONSOLE_MASKS:          # also when mask is a plain function
            ln = rx.sub(rep, ln)
        lines.append(ln)
    return '\n'.join(lines) + '\n'


def norm_bridge_episode(obj, mask):
    if not isinstance(obj, dict):
        return obj
    obj = dict(obj)
    obj.pop('time_deltas', None)
    drv = obj.get('driver_clock') or obj.get('driver')
    if isinstance(drv, dict) and isinstance(drv.get('events'), list):
        drv['events'] = [e[0] if isinstance(e, list) and e else e for e in drv['events']]
    return _walk(_drop_time_keys(obj), mask)


def normalise(run_dir):
    """{file name: content} of the normalised outputs of one run folder."""
    run_dir = Path(run_dir)
    res = json.loads((run_dir / 'RESULT.json').read_text(encoding='utf-8'))
    pr = Path(res['pipeline_run_dir']) if res.get('pipeline_run_dir') else None
    mask = Masker([(pr, '<PIPE_RUN>'), (run_dir, '<RUN>'), (os.path.realpath(run_dir), '<RUN>'),
                   (REPO, '<REPO>'), (TW, '<TW>')])
    out = {}
    if pr is not None:
        out['ledger.json'] = norm_ledger(_read_jsonl(pr / 'ledger.jsonl'), mask)
        eye = _read_jsonl(pr / 'eye.jsonl')
        if eye is not None:
            out['eye.json'] = norm_eye(eye, mask)
        for f in ('timing_summary.json', 'world_counts.json'):
            if (pr / f).exists():
                out[f] = _walk(_drop_time_keys(json.loads((pr / f).read_text(encoding='utf-8'))), mask)
        for f in ('boxel_data.json', 'problem_initial.pddl'):
            if (pr / f).exists():
                txt = (pr / f).read_text(encoding='utf-8')
                out[f] = json.loads(txt) if f.endswith('.json') else mask(txt)
    be = run_dir / 'save' / 'bridge_episode.json'
    if be.exists():
        out['bridge_episode.json'] = norm_bridge_episode(json.loads(be.read_text(encoding='utf-8')), mask)
    out['console.txt'] = norm_console((run_dir / 'stdout.txt').read_text(encoding='utf-8', errors='replace'), mask)
    calls = None
    if res['mode'] == 'record':
        calls = tape_calls(run_dir / 'tape')
        out['facts.json'] = [{'k': c['k'], 'goal': c['goal'], 'facts': c['facts']} for c in calls]
    elif res['mode'] == 'replay':
        calls = _read_jsonl(run_dir / 'rec' / 'calls.jsonl') or []
        out['facts.json'] = [{'k': c['k'], 'goal': c.get('goal'), 'facts': c.get('facts')} for c in calls]
        out['stub_checks.json'] = [{k: c.get(k) for k in ('k', 'facts_equal_tape', 'goal_equal_tape',
                                                          'rng_before_equal_tape',
                                                          'stream_ints_before_equal_tape', 'error')}
                                   for c in calls]
    for f in ('first_plan.json', 'main_params.json'):
        p = run_dir / 'rec' / f
        if p.exists():
            out[f] = _walk(json.loads(p.read_text(encoding='utf-8')), mask)
    summary = out.get('timing_summary.json') or {}
    out['result.json'] = {
        'mode': res['mode'], 'status': res['status'], 'rc': res['rc'],
        'child_exit': _walk(res.get('child_exit', {}), mask),
        'exit_reason': summary.get('exit_reason'), 'success': summary.get('success'),
        'solve_calls': None if calls is None else len(calls),
        'tape_calls': (len(tape_calls(res['tape'])) if res.get('tape') and res['mode'] == 'replay'
                       else None),
        'outcome': (out.get('bridge_episode.json') or {}).get('outcome')}
    return out


def write_norm(run_dir):
    run_dir = Path(run_dir)
    norm = run_dir / 'norm'
    if norm.exists():
        shutil.rmtree(norm)
    norm.mkdir()
    for name, obj in normalise(run_dir).items():
        if isinstance(obj, str):
            (norm / name).write_text(obj, encoding='utf-8', newline='\n')
        else:
            write_json(norm / name, obj)
    return norm


def _load_norm(folder):
    out = {}
    for f in sorted(Path(folder).iterdir()):
        if f.is_file():
            out[f.name] = (f.read_text(encoding='utf-8') if f.suffix in ('.txt', '.pddl')
                           else json.loads(f.read_text(encoding='utf-8')))
    return out


def _rows_diff(a, b, limit=10):
    diffs = []
    for i in range(max(len(a), len(b))):
        ra = a[i] if i < len(a) else None
        rb = b[i] if i < len(b) else None
        if ra != rb:
            diffs.append({'index': i, 'live': ra, 'replay': rb})
            if len(diffs) >= limit:
                break
    return diffs


def _dict_diff(a, b, path=''):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f'{path}/{k}: only in {"replay" if k not in a else "live"}')
            else:
                out += _dict_diff(a[k], b[k], f'{path}/{k}')
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += _dict_diff(x, y, f'{path}[{i}]')
    elif a != b:
        out.append(f'{path}: live {json.dumps(a)[:160]} replay {json.dumps(b)[:160]}')
    return out


def compare_live(live_norm, replay_norm):
    """PLAN 24.3 (a): the replay's step and step_end rows against the live
    episode's, and a summary of every other difference."""
    live, rep = _load_norm(live_norm), _load_norm(replay_norm)
    out = {}
    la = [r for r in live.get('ledger.json', []) if r.get('kind') in ('step', 'step_end')]
    ra = [r for r in rep.get('ledger.json', []) if r.get('kind') in ('step', 'step_end')]
    out['steps'] = {'live_rows': len(la), 'replay_rows': len(ra), 'equal': la == ra,
                    'differences': _rows_diff(la, ra)}
    ll, rl = live.get('ledger.json', []), rep.get('ledger.json', [])
    out['ledger'] = {'live_rows': len(ll), 'replay_rows': len(rl), 'equal': ll == rl,
                     'kinds_live': _count([r.get('kind') for r in ll]),
                     'kinds_replay': _count([r.get('kind') for r in rl]),
                     'first_differences': _rows_diff(ll, rl, 5)}
    lf, rf = live.get('facts.json', []), rep.get('facts.json', [])
    out['facts'] = {'calls_live': len(lf), 'calls_replay': len(rf), 'equal': lf == rf,
                    'equal_per_call': [x == y for x, y in zip(lf, rf)]}
    for name in ('eye.json', 'timing_summary.json', 'world_counts.json', 'bridge_episode.json',
                 'boxel_data.json', 'problem_initial.pddl'):
        if name in live or name in rep:
            a, b = live.get(name), rep.get(name)
            if isinstance(a, list) and isinstance(b, list):
                out[name] = {'equal': a == b, 'n_live': len(a), 'n_replay': len(b),
                             'differing_records': [i for i in range(min(len(a), len(b))) if a[i] != b[i]][:20],
                             'first': _dict_diff(*next(((x, y) for x, y in zip(a, b) if x != y), (None, None)))[:10]}
            else:
                out[name] = {'equal': a == b, 'paths': _dict_diff(a, b)[:30]}
    lc = live.get('console.txt', '').splitlines()
    rc = rep.get('console.txt', '').splitlines()
    import difflib
    d = [x for x in difflib.unified_diff(lc, rc, 'live', 'replay', lineterm='', n=0)
         if not x.startswith(('---', '+++', '@@'))]
    out['console'] = {'equal': lc == rc, 'live_lines': len(lc), 'replay_lines': len(rc),
                      'changed_lines': len(d), 'first': d[:40]}
    out['result'] = {'live': live.get('result.json'), 'replay': rep.get('result.json')}
    return out


def _count(xs):
    c = {}
    for x in xs:
        c[str(x)] = c.get(str(x), 0) + 1
    return dict(sorted(c.items()))


# ---------------------------------------------------------------------------
# Coverage of test_full_pipeline.main (PLAN 24.3 (b))
# ---------------------------------------------------------------------------

def _str_arg(call):
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    return None


def main_sites(path=TFP):
    """From the source: every break, dispatch_end(...) and exit_reason = '...'
    inside main (nested functions included), and the dispatcher branches."""
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    sites = {'break': [], 'dispatch_end': [], 'exit_reason': [], 'branch': []}
    for node in ast.walk(main):
        if isinstance(node, ast.Break):
            sites['break'].append({'line': node.lineno})
        elif isinstance(node, ast.Call) and getattr(node.func, 'id', None) == 'dispatch_end':
            sites['dispatch_end'].append({'line': node.lineno, 'status': _str_arg(node)
                                          or ast.unparse(node.args[0]) if node.args else None})
        elif isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'exit_reason' for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                sites['exit_reason'].append({'line': node.lineno, 'value': node.value.value})
        elif isinstance(node, ast.If):
            t = node.test
            if (isinstance(t, ast.Compare) and getattr(t.left, 'id', None) == 'action_name'
                    and all(isinstance(op, (ast.Eq, ast.In)) for op in t.ops)):
                vals = [c.value for c in ast.walk(t) if isinstance(c, ast.Constant)]
                sites['branch'].append({'line': node.lineno, 'body_line': node.body[0].lineno,
                                        'actions': vals})
    for v in sites.values():
        v.sort(key=lambda d: d['line'])
    return sites


def coverage_table(trace_files, path=TFP):
    reached = set()
    for tf in trace_files:
        for key, lines in json.loads(Path(tf).read_text(encoding='utf-8')).items():
            reached.update(lines)
    sites = main_sites(path)
    table = {}
    for kind, rows in sites.items():
        table[kind] = []
        for r in rows:
            line = r.get('body_line', r['line'])
            table[kind].append(dict(r, reached=line in reached))
    return table


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def record_set(out_dir, episodes, log=print):
    """Record each live episode into out_dir/<name>/ (tape/, norm/, raw)."""
    worst = 0
    for name in episodes:
        res = run_episode(name, 'record', Path(out_dir) / name, log=log)
        if res['status'] != 'ended':
            worst = 1
    return worst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--episode', choices=sorted(EPISODES))
    ap.add_argument('--mode', choices=('record', 'replay', 'first-plan'))
    ap.add_argument('--run-dir')
    ap.add_argument('--tape')
    ap.add_argument('--rng', choices=('restore', 'keep'), default='restore')
    ap.add_argument('--trace-main', action='store_true')
    ap.add_argument('--timeout', type=float, default=EPISODE_TIMEOUT_S)
    ap.add_argument('--record-set')
    ap.add_argument('--episodes', default=','.join(PIN47_EPISODES))
    ap.add_argument('--renorm')
    ap.add_argument('--coverage', nargs='+')
    ap.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--rec', help=argparse.SUPPRESS)
    ap.add_argument('--script', help=argparse.SUPPRESS)
    ap.add_argument('argv', nargs='*')
    a = ap.parse_args(argv)
    if a.child:
        return child_main(a)
    if a.renorm:
        write_norm(a.renorm)
        return 0
    if a.coverage:
        print(json.dumps(coverage_table(a.coverage), indent=1))
        return 0
    if a.record_set:
        return record_set(a.record_set, [e for e in a.episodes.split(',') if e])
    if not (a.episode and a.mode and a.run_dir):
        ap.error('--episode, --mode and --run-dir are needed (or --record-set, --renorm, --coverage)')
    if a.mode == 'replay' and not a.tape:
        ap.error('--mode replay needs --tape')
    res = run_episode(a.episode, a.mode, a.run_dir, tape=a.tape, rng=a.rng,
                      trace_main=a.trace_main, timeout=a.timeout)
    return 0 if res['status'] == 'ended' and res['child_exit'].get('code') is not None else 1


if __name__ == '__main__':
    sys.exit(main())
