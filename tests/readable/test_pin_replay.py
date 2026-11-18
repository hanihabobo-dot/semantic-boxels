"""Phase 0 pins, group "episode" (PLAN 5.2 pins 30, 34, 46, 47 and 24.3 (a)
to (d); index phase0/index/episode_path.md).

Pin 47: whole episodes recorded live on the checkpoint by
tools/readable/record_episode.py (each solver answer and the solver's
printed text per call, in call order) and replayed with
tests/readable/replay_stub.py.  The tests below

  * (a) compare each replay's ``step`` and ``step_end`` rows with the live
    episode the tape was recorded from; a difference fails unless it is in
    KNOWN_LIVE_DIFFERENCES with its cause;
  * (c) check that every solver call of the replay got the live call's init
    facts and goal and the live RNG state, and that the replay asked the
    solver exactly as often as the live episode did (a call beyond the tape
    is ReplayTapeError, never a None plan);
  * (d) rely on record_episode's normalisation: plan_obj ints and Type@id
    strings mapped to their order of first use, times and pids removed;
  * compare the whole generation with READABLE_GOLDEN/<pin> when that is set.

No golden output is stored before tag refactor-checkpoint-2 (R's condition),
so the golden comparison skips without READABLE_GOLDEN, and the episode
tests skip without READABLE_TAPES (the folder written by
``record_episode.py --record-set <folder>``).  On the checkpoint, in WSL,
under the pipeline lock and through the health gate (PLAN rule 17):

    python tools/readable/record_episode.py --record-set <tapes>
    READABLE_TAPES=<tapes> python tools/readable/pin_outputs.py --group episode --out <folder>
    READABLE_TAPES=<tapes> READABLE_GOLDEN=<folder> PYTHONHASHSEED=0 \\
        flock /root/sb_pipeline.lock /root/armO-venvA/bin/python -m pytest -q tests/readable/test_pin_replay.py

READABLE_EPISODE_ONLY=p47_replay_rp0,p30_planner_failed limits the fresh
generation.  The unit tests at the top need neither folder, start no
physics client and import no pipeline module (they run on Windows too).
"""
import collections
import difflib
import importlib.util
import json
import os
import pickle
import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def _load(name, path):
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


rec = _load('readable_record_episode', REPO / 'tools' / 'readable' / 'record_episode.py')
stub = _load('readable_replay_stub', HERE / 'replay_stub.py')
sys.path.insert(0, str(REPO / 'tools' / 'readable'))
import pin_outputs as po  # noqa: E402

GOLDEN = os.environ.get('READABLE_GOLDEN')
TAPES = os.environ.get('READABLE_TAPES')
ONLY = [s for s in os.environ.get('READABLE_EPISODE_ONLY', '').split(',') if s]
PINS = [p for p in po.GROUPS['episode'] if not ONLY or p in ONLY]
REPLAY_PINS = [p for p in PINS if p.startswith('p47_')]

# PLAN 24.3 (a): differences between a replay's step/step_end rows and the
# live episode's, each with its cause.  Key: (episode, row index).  Empty:
# on refactor-checkpoint-1 every replay's rows equal the live rows (record
# phase0/build/episode.md).
KNOWN_LIVE_DIFFERENCES = {}

needs_golden = pytest.mark.skipif(
    not GOLDEN, reason='READABLE_GOLDEN is not set: no stored golden output exists before tag '
                       'refactor-checkpoint-2 (R\'s condition)')
needs_tapes = pytest.mark.skipif(
    not TAPES, reason='READABLE_TAPES is not set: record the live tapes first with '
                      '"record_episode.py --record-set <folder>" (in WSL, under the lock)')


# ---------------------------------------------------------------------------
# Unit tests: the stub, the recorder and the normalisation (no pipeline)
# ---------------------------------------------------------------------------

Problem = collections.namedtuple('Problem', 'init goal')


class _StdoutTee:
    """Same name and shape as pddlstream_planner._StdoutTee."""

    def __init__(self, stream):
        self._stream = stream
        self.chunks = []

    def write(self, s):
        self._stream.write(s)
        self.chunks.append(s)

    def flush(self):
        self._stream.flush()


class _Sink:
    def __init__(self):
        self.parts = []

    def write(self, s):
        self.parts.append(s)

    def flush(self):
        pass


@pytest.fixture
def tee_on():
    """tee_on() sets a tee as sys.stdout from inside the test body (pytest's
    capture sets sys.stdout again between the setup and the call phase, so a
    fixture cannot set it); the old stream is put back after the test."""
    saved = []

    def install():
        saved.append(sys.stdout)
        t = _StdoutTee(_Sink())
        sys.stdout = t
        return t
    yield install
    if saved:
        sys.stdout = saved[0]


def _np_or_skip():
    return pytest.importorskip('numpy')


def test_recorder_stores_each_call_at_call_time(tmp_path, tee_on):
    tee = tee_on()
    np = _np_or_skip()
    tape = tmp_path / 'tape'
    sys.stdout.write('printed before solve\n')         # plan()'s own print, not the solver's

    def real_solve(problem, max_time=None):
        print('Stream plan (1, 0, 0.000): [x]')
        random.random()
        np.random.random()
        return ([('move', 'q0', 'q1')], 1.0, None)
    solve = rec.make_recorder(real_solve, tape)
    got = solve(Problem([('Conf', 'q0'), ('at', 'a', 1)], ('holding', 'a')), max_time=5.0)
    assert got == ([('move', 'q0', 'q1')], 1.0, None)
    calls = rec.tape_calls(tape)
    assert len(calls) == 1 and calls[0]['k'] == 0
    assert calls[0]['facts'] == ['(Conf q0)', '(at a 1)'] and calls[0]['goal'] == '(holding a)'
    assert calls[0]['kwargs'] == {'max_time': 5.0}
    assert calls[0]['rng_before'] != calls[0]['rng_after']
    text = json.loads((tape / 'text_0000.json').read_text(encoding='utf-8'))
    assert ''.join(text) == 'Stream plan (1, 0, 0.000): [x]\n'   # only this call's chunks
    assert pickle.loads((tape / 'solution_0000.pkl').read_bytes()) == got


def test_stub_replays_in_order_prints_text_and_restores_rng(tmp_path, tee_on):
    tee = tee_on()
    np = _np_or_skip()
    tape, out = tmp_path / 'tape', tmp_path / 'rec'
    answers = [([('move', 'q0', 'q1')], 1.0, None), (None, float('inf'), None)]
    texts = [['a\n'], ['Stream plan (1, 0, 0.000): [y]\n', 'Summary: {skeletons: 1}\n']]

    def real_solve(problem):
        k = len(rec.tape_calls(tape))
        for c in texts[k]:
            sys.stdout.write(c)
        random.random()
        np.random.random()
        return answers[k]
    recorder = rec.make_recorder(real_solve, tape)
    states_after = []
    random.seed(7)
    np.random.seed(7)
    for i in range(2):
        recorder(Problem([('f', i)], ('g',)))
        states_after.append(rec.rng_digest())

    random.seed(7)
    np.random.seed(7)
    s = stub.make_stub(tape, out, rng='restore')
    tee.chunks.clear()
    first = s(Problem([('f', 0)], ('g',)))
    assert first == answers[0] and first is not answers[0]
    assert rec.rng_digest() == states_after[0]
    second = s(Problem([('f', 1)], ('g',)))
    assert second[0] is None
    assert ''.join(tee.chunks) == 'a\nStream plan (1, 0, 0.000): [y]\nSummary: {skeletons: 1}\n'
    assert rec.rng_digest() == states_after[1]
    rows = [json.loads(x) for x in (out / 'calls.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [r['facts_equal_tape'] for r in rows] == [True, True]
    assert [r['rng_before_equal_tape'] for r in rows] == [True, True]
    with pytest.raises(stub.ReplayTapeError, match='tape holds 2 calls'):
        s(Problem([], ('g',)))
    assert stub.calls_used(out) == 3


def test_stub_flags_a_different_fact_list(tmp_path, tee_on):
    tee = tee_on()
    tape, out = tmp_path / 'tape', tmp_path / 'rec'
    rec.make_recorder(lambda p: (None, 0.0, None), tape)(Problem([('a',), ('b',)], ('g',)))
    s = stub.make_stub(tape, out, rng='keep')
    s(Problem([('b',), ('a',)], ('g',)))       # the same facts, another order
    row = json.loads((out / 'calls.jsonl').read_text(encoding='utf-8').splitlines()[0])
    assert row['facts_equal_tape'] is False and row['goal_equal_tape'] is True


def test_stub_installed_before_the_gate_wrapper_keeps_plan_as_the_caller(tmp_path, tee_on):
    tee = tee_on()
    """G11 (gate_hooks._make_solve) reads sys._getframe(1).f_code: with the
    stub set first and the gate wrapper around it, plan() is still the
    caller of the outermost solve."""
    import types
    tape = tmp_path / 'tape'
    rec.write_synthetic_tape(tape, [((None, float('inf'), None), [])])
    mod = types.ModuleType('fake_planner')
    exec('def plan():\n    return solve(None)\n', mod.__dict__)
    mod.solve = lambda problem: (None, 0.0, None)
    stub.install(mod, tape, tmp_path / 'rec')
    seen = []
    inner = mod.solve

    def gate_solve(*a, **k):
        seen.append(sys._getframe(1).f_code)
        return inner(*a, **k)
    mod.solve = gate_solve                       # what gate_hooks.install does next
    assert mod.plan() == (None, float('inf'), None)
    assert seen == [mod.plan.__code__]


def test_stub_restores_the_stream_counters_the_live_search_left(tmp_path, tee_on):
    """The live search advances planner.streams' name counters; the stub
    sets them to their values after the live call, found through the
    plan() frame up the stack."""
    tee_on()
    import types
    tape = tmp_path / 'tape'
    mod = types.ModuleType('fake_planner2')
    exec('class Streams:\n    def __init__(self):\n        self._config_counter = 0\n'
         '        self.view_kin_skips = 0\n        self.name = "s"\n'
         'class Planner:\n    def __init__(self):\n        self.streams = Streams()\n'
         '    def plan(self):\n        return solve(None)\n', mod.__dict__)

    def live_solve(problem):
        p = rec.planner_on_stack()
        p.streams._config_counter += 5
        p.streams.view_kin_skips += 2
        return (None, 0.0, None)
    mod.solve = rec.make_recorder(live_solve, tape)
    live = mod.Planner()
    live.plan()
    row = rec.tape_calls(tape)[0]
    assert row['stream_ints_before'] == {'_config_counter': 0, 'view_kin_skips': 0}
    assert row['stream_ints_after'] == {'_config_counter': 5, 'view_kin_skips': 2}
    stub.install(mod, tape, tmp_path / 'rec')
    again = mod.Planner()
    again.plan()
    assert (again.streams._config_counter, again.streams.view_kin_skips) == (5, 2)
    check = json.loads((tmp_path / 'rec' / 'calls.jsonl').read_text(encoding='utf-8').splitlines()[0])
    assert check['stream_ints_before_equal_tape'] is True


def test_synthetic_binding_death_text_takes_the_branch():
    """The text of pin 30's binding-death run matches the regexes of
    pddlstream_planner.py:1356-1369 (re-stated here; pin 39 pins the code)."""
    import re
    captured = ''.join(po.BINDING_DEATH_TEXT)
    lines = [ln for ln in captured.splitlines()
             if ln.startswith('Stream plan (') and not ln.rstrip().endswith((': None', ': False'))]
    m = None
    for m in re.finditer(r'Summary: \{([^}]*)\}', captured):
        pass
    assert len(lines) == 2 and m is not None
    assert re.search(r'skeletons: (\d+)', m.group(1)).group(1) == '2'


def test_ledger_normalisation_maps_ids_by_first_use():
    rows = [
        {'t': 1.0, 'wall': 2.0, 'kind': 'ledger_open', 'pid': 99},
        {'t': 1.0, 'wall': 2.0, 'kind': 'plan', 'plan_id': 1, 'call': 'mission', 'plan_time_s': 3.2,
         'plan_obj': 140001, 'actions': [['move', 'q0', 'Trajectory@555'], ['pick', 'a', 'Grasp@777']]},
        {'t': 1.0, 'wall': 2.0, 'kind': 'step', 'plan': 1, 'step': 1, 'action': 'move',
         'args': ['q0', 'Trajectory@555'], 'plan_obj': 140001},
        {'t': 1.0, 'wall': 2.0, 'kind': 'step_end', 'plan': 1, 'step': 1, 'status': 'ok'},
        {'t': 1.0, 'wall': 2.0, 'kind': 'plan', 'plan_id': 2, 'call': 'mission', 'plan_time_s': 1.0,
         'plan_obj': 140001, 'actions': [['move', 'q1', 'Trajectory@555']]},
        {'t': 1.0, 'wall': 2.0, 'kind': 'note', 'text': '<obj at 0x7f00deadbeef>'},
    ]
    n = rec.norm_ledger(rows, lambda s: s)
    assert n[0] == {'kind': 'ledger_open'}
    assert n[1]['plan_obj'] == 'obj#1' and 'plan_time_s' not in n[1] and 't' not in n[1]
    assert n[1]['actions'] == [['move', 'q0', 'Trajectory@#1'], ['pick', 'a', 'Grasp@#2']]
    assert n[2]['plan_obj'] == 'obj#1' and n[2]['args'] == ['q0', 'Trajectory@#1']
    # A reused address in a later plan is a new token (keyed by plan id).
    assert n[4]['plan_obj'] == 'obj#2' and n[4]['actions'] == [['move', 'q1', 'Trajectory@#3']]
    assert n[5]['text'] == '<obj at 0x#1>'
    # The same rows with other addresses normalise to the same result.
    other = json.loads(json.dumps(rows).replace('140001', '150002').replace('555', '556')
                       .replace('777', '778').replace('deadbeef', 'feedbeef'))
    assert rec.norm_ledger(other, lambda s: s) == n


def test_console_masks_times_only():
    text = ('  [#76-diag] outcome=plan_found, elapsed=12.345s, plan_len=3, cost=3\n'
            '  [timing] planner.plan() #1: 12.400s (cumulative 12.400s)\n'
            '  Per-call (s)             : [12.400, 1.000]\n'
            'Plan: 3 actions\n')
    got = rec.norm_console(text, lambda s: s)
    assert 'elapsed=<T>s, plan_len=3' in got and '#1: <T>s (cumulative <T>s)' in got
    assert 'Per-call (s)             : [<T>]' in got and 'Plan: 3 actions' in got


def test_group_episode_registers_pins_30_34_46_47():
    ids = list(po.GROUPS['episode'])
    assert [i for i in ids if i.startswith('p30_')] == ['p30_planner_failed', 'p30_binding_death']
    assert [i for i in ids if i.startswith('p34_')] == [f'p34_start_rp{s}' for s in range(5)]
    assert [i for i in ids if i.startswith('p46_')] == [f'p46_bridge_start_s{s}' for s in (0, 1, 5, 100)]
    assert [i for i in ids if i.startswith('p47_')] == [f'p47_replay_{e}' for e in rec.PIN47_EPISODES]
    for pid in ids:
        if pid.startswith('p46_') or pid in ('p47_replay_br0', 'p47_replay_br5'):
            assert 'needs the bridge venv' in po.GROUPS['episode'][pid].about


def test_coverage_sites_are_read_from_main():
    sites = rec.main_sites()
    statuses = {s['status'] for s in sites['dispatch_end']}
    assert {'ok', 'sense_outcome', 'pick_failure', 'unlabelled'} <= statuses
    assert {s['value'] for s in sites['exit_reason']} >= {'planner_failed', 'no_plan_binding_death',
                                                          'all_searched', 'home_not_reached'}
    assert sites['break'] and sites['branch']


# ---------------------------------------------------------------------------
# Episode tests: a fresh generation of the group (each pin in its own child)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def fresh(tmp_path_factory):
    """Only what a test here reads: the replay pins with READABLE_TAPES, every
    pin with READABLE_GOLDEN."""
    out = tmp_path_factory.mktemp('pins_episode')
    for pid in PINS:
        if pid.startswith('p47_') and not TAPES:
            continue
        if not pid.startswith('p47_') and not GOLDEN:
            continue
        po.run_group('episode', out, only=[pid], log=lambda s: None)
    return out


def _status(fresh, pid):
    manifest = json.loads((fresh / 'MANIFEST.json').read_text(encoding='utf-8'))
    err = fresh / pid / 'ERROR.txt'
    text = err.read_text(encoding='utf-8') if err.exists() else ''
    if 'needs the bridge venv' in text:
        pytest.skip(f'{pid} needs the bridge venv (TAMPURA\'s tree at {po.TW_ENVS})')
    return manifest['pins'][pid]['status'], text


@needs_tapes
@pytest.mark.parametrize('pin_id', REPLAY_PINS)
def test_replay_steps_equal_the_live_episode(fresh, pin_id):
    status, text = _status(fresh, pin_id)
    assert status == 'ok', f'{pin_id} did not run: {status}\n{text}'
    episode = pin_id[len('p47_replay_'):]
    vs = json.loads((fresh / pin_id / 'vs_live.json').read_text(encoding='utf-8'))
    unexplained = [d for d in vs['steps']['differences']
                   if (episode, d['index']) not in KNOWN_LIVE_DIFFERENCES]
    assert vs['steps']['live_rows'] == vs['steps']['replay_rows'] or unexplained, vs['steps']
    assert not unexplained, f'{pin_id}: step rows differ from the live episode: {unexplained[:3]}'


@needs_tapes
@pytest.mark.parametrize('pin_id', REPLAY_PINS)
def test_replay_asks_the_solver_as_the_live_episode_did(fresh, pin_id):
    status, text = _status(fresh, pin_id)
    assert status == 'ok', f'{pin_id} did not run: {status}\n{text}'
    res = json.loads((fresh / pin_id / 'result.json').read_text(encoding='utf-8'))
    assert res['solve_calls'] == res['tape_calls'], res
    checks = json.loads((fresh / pin_id / 'stub_checks.json').read_text(encoding='utf-8')) \
        if (fresh / pin_id / 'stub_checks.json').exists() else []
    for c in checks:
        assert c['error'] is None, c
        assert c['facts_equal_tape'] in (True, None), f'call {c["k"]}: the init facts differ from live'
        assert c['goal_equal_tape'] in (True, None), f'call {c["k"]}: the goal differs from live'
        assert c['rng_before_equal_tape'] in (True, None), f'call {c["k"]}: the RNG state differs from live'
        assert c.get('stream_ints_before_equal_tape') in (True, None), \
            f'call {c["k"]}: the streams\' counters differ from live before the call'


def _first_difference(a, b):
    la = a.read_text(encoding='utf-8', errors='replace').splitlines()
    lb = b.read_text(encoding='utf-8', errors='replace').splitlines()
    return '\n'.join(list(difflib.unified_diff(la, lb, 'golden', 'fresh', lineterm='', n=2))[:40])


@needs_golden
@pytest.mark.parametrize('pin_id', PINS)
def test_pin_equals_golden(fresh, pin_id):
    if pin_id.startswith('p47_') and not TAPES:
        pytest.skip('READABLE_TAPES is not set')
    golden = Path(GOLDEN) / pin_id
    assert golden.is_dir(), f'the golden folder {GOLDEN} has no {pin_id}'
    status, text = _status(fresh, pin_id)
    assert status == 'ok', f'{pin_id} did not run: {status}\n{text}'
    want, have = po.pin_files(golden), po.pin_files(fresh / pin_id)
    assert sorted(want) == sorted(have), f'file sets differ: golden {sorted(want)}, fresh {sorted(have)}'
    for name in sorted(want):
        if want[name].read_bytes() != have[name].read_bytes():
            pytest.fail(f'{pin_id}/{name} differs from the golden copy:\n'
                        + _first_difference(want[name], have[name]))
