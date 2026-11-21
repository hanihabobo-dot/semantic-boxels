"""Unit tests of the recorder's gate 7 parts (SPEC gate 7, WP-B): the F and R
entries and their twins (D2, D3), the first-plan record (P8, E3, D15's
S-b), the crash record under C-01 (D7), the planted change at_home_drop
(D8, in test_pin_replay.py), the coverage map (D12), the stub place_fail
(D16), the counts at storing (D3, D4), the masks (D6) and --set (D5).

None of these starts a simulation or an episode: the entries are built and
printed, the child runs small scripts written here, the stubs patch stand-in
modules, and the coverage map reads source files and trace files.
"""
import ast
import dataclasses
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
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
stubs = _load('readable_executor_stubs', HERE / 'executor_stubs.py')


# ---------------------------------------------------------------------------
# D2: the F and R entries, the declared strings, the printed argv
# ---------------------------------------------------------------------------

# Run the harness's own run_episode (tools/slip_eval.py) for arm O with
# Popen replaced, and print the command it would start: the reference the
# entries are checked against, built by the harness's code, not by the
# recorder's reading of it.
_HARNESS_RUN = r'''
import json, shlex, subprocess, sys, types
sys.path.insert(0, sys.argv[1])
import gen_scene_eval, slip_eval
seen = {}
class Stop(Exception):
    pass
def popen(cmd, **kw):
    seen['cmd'] = list(cmd)
    raise Stop()
slip_eval.subprocess.Popen = popen
a = types.SimpleNamespace(out=sys.argv[2], python='<python>', snapshot='<SNAP>', cwd=sys.argv[2], cap=1)
try:
    slip_eval.run_episode(a, gen_scene_eval.ARM_O, int(sys.argv[3]), 0,
                          extra_args=tuple(shlex.split(sys.argv[4])))
except Stop:
    pass
print(json.dumps(seen['cmd']))
'''


def _harness_cmd(tmp_path, seed, o_args):
    p = subprocess.run([sys.executable, '-I', '-B', '-c', _HARNESS_RUN, str(REPO / 'tools'), str(tmp_path),
                        str(seed), o_args], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize('name, arm', [('f140', 'F'), ('r141', 'R'), ('f293', 'F')])
def test_config_entry_is_the_harness_command_then_the_declared_string(tmp_path, name, arm):
    """SPEC D2: an F or R entry starts the driver with what the harness's
    run_episode starts for arm O with the declared string as P4_O_ARGS, plus
    --log-level normal and nothing else.  Catches a flag, value or order the
    tool would type or read wrongly, and a declared string not passed
    unchanged."""
    spec = rec.entry(name)
    declared = rec.declared_string(arm)
    seed = int(name[1:])
    want = _harness_cmd(tmp_path, seed, declared['value'])
    assert want[:2] == ['<python>', os.path.join('<SNAP>', 'tampura_bridge', 'run_bridge_on_finddice.py')]
    save = want[want.index('--save-dir') + 1]
    got = [save if x == '<SAVE>' else x for x in spec['argv']]
    assert got == want[2:] + ['--log-level', 'normal']
    assert spec['kind'] == 'bridge' and spec['gen'] is True and spec['config'] == arm
    assert spec['m7'] == 'default' and '--m7' not in spec['argv']
    assert got[-2 - len(shlex.split(declared['value'])):-2] == shlex.split(declared['value'])


def test_declared_strings_of_wave_2_are_read_by_text():
    """The F and R strings as the declaration states them (by text, its
    blob hash beside them).  The expected values are the declaration's own
    words, read here as the line that names the arm."""
    text = rec.DECLARATION.read_text(encoding='utf-8')
    for arm, words in (('F', 'fixed camera'), ('R', 'robot camera only')):
        d = rec.declared_string(arm)
        line = text.replace('\r\n', '\n').split('\n')[d['line'] - 1]
        assert line == d['text'] and line.startswith(f'- {arm}, ours, {words}: P4_ARMS=O, P4_O_ARGS=')
        assert f"P4_O_ARGS='{d['value']}'" in line
        assert d['file'] == 'archive/tampura_bridge_plan_2026-10-25/tracks/evalfinal/wave2/DECLARATION.md'
        assert d['git_blob_sha1'] == rec.git_blob_sha1(rec.DECLARATION.read_bytes())


def test_git_blob_sha1_is_git_s_hash():
    """Two hashes git gives for these contents (`git hash-object`), and CRLF
    read as LF.  Catches a hash that is not git's (the NOTES would name a
    blob no `git rev-parse` finds)."""
    assert rec.git_blob_sha1(b'') == 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'
    assert rec.git_blob_sha1(b'hello\n') == 'ce013625030ba8dba906f756967f9e9ca394464a'
    assert rec.git_blob_sha1(b'hello\r\n') == rec.git_blob_sha1(b'hello\n')


def _declaration(tmp_path, body):
    p = tmp_path / 'DECLARATION.md'
    p.write_text(body, encoding='utf-8', newline='\n')
    return p


def test_declared_string_fails_unless_exactly_one_line_and_one_value(tmp_path):
    """Exactly one line that starts the arm, exactly one P4_O_ARGS on it,
    arm O, or the tool fails (it never picks)."""
    ok = "- F, ours: P4_ARMS=O, P4_O_ARGS='--interior-regions on'.\n- R, x: P4_ARMS=O, P4_O_ARGS='-a b'\n"
    assert rec.declared_string('F', _declaration(tmp_path, ok))['value'] == '--interior-regions on'
    assert rec.declared_string('R', _declaration(tmp_path, ok))['value'] == '-a b'
    for body, why in (
            ("- R, x: P4_ARMS=O, P4_O_ARGS='-a'\n", '0 lines start the F arm'),
            ("- F, a: P4_ARMS=O, P4_O_ARGS='-a'\n- F, b: P4_ARMS=O, P4_O_ARGS='-b'\n", '2 lines start'),
            ("- F, a: P4_ARMS=O, no value\n", "0 values P4_O_ARGS"),
            ("- F, a: P4_ARMS=O, P4_O_ARGS='-a' P4_O_ARGS='-b'\n", "2 values P4_O_ARGS"),
            ("- F, a: P4_ARMS=T, P4_O_ARGS='-a'\n", "not the harness's arm O")):
        with pytest.raises(rec.EntryError, match=why):
            rec.declared_string('F', _declaration(tmp_path, body))


def test_harness_command_of_another_shape_is_refused(tmp_path):
    """The harness's command is read from run_episode's own list; an
    element the tool does not know (here a new flag value from a variable)
    makes it fail instead of building a command the harness does not
    build."""
    src = (rec.SLIP_EVAL.read_text(encoding='utf-8')
           .replace("'--allow-g19-mismatch', '1',", "'--allow-g19-mismatch', g19,", 1))
    assert src != rec.SLIP_EVAL.read_text(encoding='utf-8')
    changed = tmp_path / 'slip_eval.py'
    changed.write_text(src, encoding='utf-8')
    with pytest.raises(rec.EntryError, match='does not read: g19'):
        rec.harness_arm_o(slip_eval=changed)


def test_twin_puts_m7_off_after_the_command_before_the_departures():
    """SPEC D2 and D3: a twin is its entry with --m7 off after the command it
    reproduces (for F after the declared string), before --log-level
    normal; the D entries' twins the same way."""
    for base in ('f204', 'r140', 'rp0', 'br0'):
        on, off = rec.entry(base), rec.entry(base + rec.TWIN_SUFFIX)
        i = on['argv'].index('--log-level')
        assert off['argv'] == on['argv'][:i] + ['--m7', 'off'] + on['argv'][i:]
        assert (off['m7'], off['twin_of'], on['m7']) == ('off', base, 'default')
    assert rec.entry('f204_m7off')['argv'][-6:] == ['--interior-regions', 'on', '--m7', 'off',
                                                   '--log-level', 'normal']
    with pytest.raises(rec.EntryError):
        rec.entry('f204_m7off_m7off')


def test_tabletop_look_entry_is_run_boxels_look_boxel_eye_arm():
    """PLAN 5.8's tabletop start in R: rp<seed> with run.ps1's -Look boxel
    -Eye arm words after the launcher's command (run.ps1:129, 138), before
    the recorder's own additions; no --interior-regions (run.ps1 has no
    switch for it).  Catches the words in another place or missing."""
    ps1 = (REPO / 'run.ps1').read_text(encoding='utf-8')
    assert 'if ($Look) { $sw += " --look $Look" }' in ps1 and "$sw += ' --eye arm'" in ps1
    for s in range(5):
        e = rec.entry(f'rp{s}_look')
        base = rec.EPISODES[f'rp{s}']['argv']
        i = base.index('--log-level')
        assert e['argv'] == base[:i] + ['--look', 'boxel', '--eye', 'arm'] + base[i:]
        assert (e['config'], e['kind'], e['tabletop_of']) == ('R', 'boxels', f'rp{s}')
        assert '--interior-regions' not in e['argv']
    with pytest.raises(rec.EntryError):
        rec.entry('br0_look')                # the bridge is not run boxels


def test_d_entries_are_unchanged():
    """The D entries keep their argv (the episode pins' first NOTES line)."""
    for name, spec in rec.EPISODES.items():
        e = rec.entry(name)
        assert e['argv'] == spec['argv'] and e['kind'] == spec['kind'] and e['config'] == 'D'
        assert rec.entry_notes(name) == [f'episode {name}: {spec["kind"]}, argv {spec["argv"]}']


def test_unknown_names_are_refused():
    for bad in ('f0140', 'f99', 'x1', 'f', 'r140x', ''):
        with pytest.raises(rec.EntryError):
            rec.entry(bad)


def test_parent_refuses_positional_argv(capsys):
    """SPEC D2: the parent never drops argv silently."""
    with pytest.raises(SystemExit) as ex:
        rec.main(['--episode', 'rp0', '--mode', 'record', '--run-dir', 'x', '--', '--seed', '3'])
    assert ex.value.code == 2
    assert "positional arguments ['--seed', '3'] are not passed" in capsys.readouterr().err


def test_print_argv_starts_nothing(monkeypatch, capsys, tmp_path):
    """--print-argv prints the built command and starts no child (Popen is
    made to fail here); the printed argv is the entry's."""
    def no_child(*a, **k):
        raise AssertionError('a child was started')
    monkeypatch.setattr(rec.subprocess, 'Popen', no_child)
    monkeypatch.setattr(rec.subprocess, 'run', no_child)
    monkeypatch.chdir(tmp_path)
    assert rec.main(['--episode', 'r140', '--print-argv']) == 0
    d = json.loads(capsys.readouterr().out)
    assert d['command'][2:] == rec.entry('r140')['argv'] and d['configuration'] == 'R'
    assert d['sources']['declared']['value'] == rec.declared_string('R')['value']
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# P8, E3 and R's S-b: the module switches and the first-plan record
# ---------------------------------------------------------------------------

# The shape of test_full_pipeline.main around its plan() call: a function
# named main in the file that runs as that module, env among its locals.
_MAIN_SRC = 'def main(env, call):\n    return call()\n'


def _fake_main(tmp_path):
    path = tmp_path / 'fake_tfp.py'
    path.write_text(_MAIN_SRC, encoding='utf-8')
    spec = importlib.util.spec_from_file_location('readable_fake_tfp', str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return path, mod


def _stand_ins(monkeypatch, m7=False, suspend_s=7.25, enabled=True):
    """Stand-ins of the three modules (the recorder reads sys.modules)."""
    ex = types.ModuleType('execution')
    ex.M7, ex.M7_SUSPEND_S = m7, suspend_s
    ir = types.ModuleType('interior_regions')
    ir.ENABLED = enabled
    ae = types.ModuleType('arm_eye')
    ae.FOLLOW_FLAG = 'arm_eye_follows'
    ae.following = lambda env: bool(getattr(env, ae.FOLLOW_FLAG, False))   # arm_eye.py:207-211
    for mod in (ex, ir, ae):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)


def test_module_switches_hold_m7_its_length_interior_regions_and_the_follow_flag(tmp_path, monkeypatch):
    """P8 and E3: execution.M7, execution.M7_SUSPEND_S and
    interior_regions.ENABLED as the modules hold them, and the arm camera's
    follow flag read with arm_eye.following on the env of main's frame.
    Catches a switch left out, a value typed instead of read, and the flag
    read from another frame's env (here the nearer caller's) or not read."""
    path, fake = _fake_main(tmp_path)
    _stand_ins(monkeypatch)
    env = types.SimpleNamespace()                   # a nearer frame's env, not following
    follows = types.SimpleNamespace(arm_eye_follows=True)

    def at_plan():
        return env, rec.module_switches(rec.main_frame(path).f_locals)
    got = fake.main(follows, at_plan)[1]
    assert got['execution.M7'] is False and got['execution.M7_SUSPEND_S'] == 7.25
    assert got['interior_regions.ENABLED'] is True
    assert got[rec.FOLLOW_KEY] is True
    _stand_ins(monkeypatch, m7=True, suspend_s=120.0, enabled=False)
    got = fake.main(types.SimpleNamespace(), at_plan)[1]
    assert (got['execution.M7'], got['execution.M7_SUSPEND_S'], got['interior_regions.ENABLED'],
            got[rec.FOLLOW_KEY]) == (True, 120.0, False, False)
    assert rec.main_frame(path) is None
    assert rec.module_switches(None)[rec.FOLLOW_KEY] == rec.NO_MAIN_FRAME
    for name in ('execution', 'interior_regions', 'arm_eye'):
        monkeypatch.delitem(sys.modules, name)
    got = rec.module_switches(None)
    assert not {'execution.M7', 'execution.M7_SUSPEND_S', 'interior_regions.ENABLED', rec.FOLLOW_KEY} & set(got)


@dataclasses.dataclass
class _Config:
    joint_positions: object
    name: str = ''
    ignored: frozenset = frozenset()


class _Views:
    pass


class _Streams:
    def __init__(self):
        self.registry = object()
        self.home_config = _Config(np.array([0.5, -1.0]), 'q_home')
        self._config_counter = 3
        self.support_body_ids = frozenset({4, 2})
        self.path_check_diag = False


class _Planner:
    def __init__(self):
        self.streams = _Streams()
        self.look_on, self.look_mode = True, 'boxel'
        self.look_views, self.m8_views = _Views(), None
        self.domain_pddl = '(define (domain d)\n  (:predicates))\n'
        self.stream_pddl = ''
        self.search_options = {'max_effort': 1}
        self.last_m8_stats = {'twin_render_s': 0.25, 'twin_renders': 3, 'build_s': None}
        self.camera_pos = np.array([1.0, 2.0, 3.0])
        self.last_init = [('Boxel', 'b1'), ('Config', object())]
        self.home_joints = (0.1, 0.2)
        self.by_id = {3: 'a'}
        self.fn = len

    def plan(self, init_state=None, goal=None, held_obj=None):
        raise AssertionError('the recorder calls no planner')


def test_first_plan_record_holds_every_attribute_of_the_planner_and_its_streams(tmp_path, monkeypatch):
    """R's S-b (SPEC D15): every attribute by name, a plain value as itself
    with its container's type named, an object by its type only, so
    look_on and look_mode show by value and m8_views and look_views as null
    or set; the follow flag through the recorder's own lookup of main's
    frame (main_file).  Catches a typed list of attribute names, an object
    recorded by its text, a container type lost, and the recorder looking
    for main in another file."""
    path, fake = _fake_main(tmp_path)
    _stand_ins(monkeypatch)
    p = _Planner()
    recorder = rec.make_first_plan_recorder(_Planner.plan, tmp_path, main_file=path)
    with pytest.raises(rec.StopAtPlan):
        fake.main(types.SimpleNamespace(arm_eye_follows=True), lambda: recorder(p, goal=('g',)))
    d = json.loads((tmp_path / 'first_plan.json').read_text(encoding='utf-8'))
    pa, sa = d['planner_attributes'], d['streams_attributes']
    assert list(pa) == sorted(vars(p)) and list(sa) == sorted(vars(p.streams))
    assert (pa['look_on'], pa['look_mode'], pa['m8_views'], pa['look_views']) == (
        True, 'boxel', None, {'object': '_Views'})
    assert pa['streams'] == {'object': '_Streams'} and sa['registry'] == {'object': 'object'}
    assert pa['domain_pddl'] == {'str_lines': 2,
                                 'sha256': hashlib.sha256(p.domain_pddl.encode('utf-8')).hexdigest()}
    assert pa['stream_pddl'] == '' and pa['search_options'] == {'max_effort': 1}
    assert pa['camera_pos'] == {'ndarray': [1.0, 2.0, 3.0], 'dtype': 'float64'}
    assert pa['last_init'] == {'object': 'list', 'len': 2}
    assert pa['home_joints'] == {'tuple': [0.1, 0.2]} and pa['by_id'] == {'dict': [[3, 'a']]}
    assert pa['fn'] == {'object': 'builtin_function_or_method', 'qualname': 'len'}
    assert pa['last_m8_stats'] == {'twin_render_s': 0.25, 'twin_renders': 3, 'build_s': None}
    assert sa['home_config'] == {'object': '_Config'}       # a RobotConfig is an object, not plain
    assert sa['support_body_ids'] == {'frozenset': [2, 4]} and sa['_config_counter'] == 3
    assert d['module_switches'][rec.FOLLOW_KEY] is True
    assert d['module_switches']['execution.M7_SUSPEND_S'] == 7.25
    assert d['plan_kwargs']['goal'] == ['g'] and d['plan_kwargs_passed'] == ['goal']


def test_plain_form_names_containers_and_refuses_objects_inside():
    """A container is plain only if all of it is; an instance of a class of
    the pipeline (here a dataclass like RobotConfig) is not; sets come
    sorted, a dict keeps its own order, and nesting stops at PLAIN_DEPTH."""
    assert rec.plain_form([1, 'a', None, True, 2.5]) == [1, 'a', None, True, 2.5]
    assert rec.plain_form([1, object()]) is rec.NOT_PLAIN
    assert rec.plain_form({'k': {'j': [object()]}}) is rec.NOT_PLAIN
    assert list(rec.plain_form({'b': 1, 'a': 2})) == ['b', 'a']
    assert rec.plain_form({'x'}) == {'set': ['x']}
    assert rec.plain_form(frozenset({3, 1, 2})) == {'frozenset': [1, 2, 3]}
    assert rec.plain_form(('a', ('b',))) == {'tuple': ['a', {'tuple': ['b']}]}
    assert rec.plain_form(np.array([[1, 2]], dtype=np.int32)) == {'ndarray': [[1, 2]], 'dtype': 'int32'}
    assert rec.plain_form(np.array([object()], dtype=object)) is rec.NOT_PLAIN
    assert rec.plain_form(_Config(np.zeros(2))) is rec.NOT_PLAIN
    assert rec.plain_form([('Config', _Config(np.zeros(2)))]) is rec.NOT_PLAIN
    deep = []
    for _ in range(rec.PLAIN_DEPTH):
        deep = [deep]
    assert rec.plain_form(deep) is rec.NOT_PLAIN and rec.plain_form(deep[0]) is not rec.NOT_PLAIN
    assert rec.plain_form('one line') == 'one line'


def _run_folder(tmp_path, first_plan=None, crash=None, pipeline=None, bridge=None):
    """A run folder as the parent leaves it (RESULT.json, stdout, rec/):
    what normalise reads of it.  pipeline ({file name: rows of a .jsonl or
    the object of a .json}) makes the pipeline run directory beside it,
    bridge the folder's save/bridge_episode.json; without them there is
    none."""
    run = tmp_path / 'run'
    (run / 'rec').mkdir(parents=True)
    pr = None
    if pipeline is not None:
        pr = tmp_path / 'pipeline_run'
        pr.mkdir()
        for name, obj in pipeline.items():
            text = (''.join(json.dumps(r) + '\n' for r in obj) if name.endswith('.jsonl')
                    else json.dumps(obj))
            (pr / name).write_text(text, encoding='utf-8')
    rec.write_json(run / 'RESULT.json', {'mode': 'first-plan', 'status': 'ended', 'rc': 0,
                                         'pipeline_run_dir': None if pr is None else str(pr)})
    (run / 'stdout.txt').write_text('', encoding='utf-8')
    if first_plan is not None:
        rec.write_json(run / 'rec' / 'first_plan.json', first_plan)
    if crash is not None:
        (run / 'rec' / 'CRASH.txt').write_text(crash, encoding='utf-8')
    if bridge is not None:
        (run / 'save').mkdir()
        rec.write_json(run / 'save' / 'bridge_episode.json', bridge)
    return run


def test_first_plan_seconds_masked_in_the_attribute_records_keys_kept(tmp_path):
    """SPEC D6's form for the new records: a number under a key that ends in
    _s becomes <s> (also in a list), the key stays, null stays; the other
    parts of first_plan.json and an uppercase _S setting are not touched.
    Catches a time left in (the pin would differ run to run), a key
    dropped, and a mask that reaches the module switches or the
    arguments."""
    stats = {'twin_render_s': 0.25, 'twin_renders': 3, 'build_s': None, 'per_call_s': [0.5, 1.5]}
    raw = {'plan_kwargs': {'max_s': 3}, 'module_switches': {'execution.M7_SUSPEND_S': 120.0},
           'planner_attributes': {'last_m8_stats': stats, 'look_on': False},
           'streams_attributes': {'step_s': 0.25, 'counter': 2}}
    n = rec.normalise(_run_folder(tmp_path, first_plan=raw))['first_plan.json']
    assert n['planner_attributes']['last_m8_stats'] == {
        'twin_render_s': '<s>', 'twin_renders': 3, 'build_s': None, 'per_call_s': ['<s>', '<s>']}
    assert list(n['planner_attributes']['last_m8_stats']) == list(stats)
    assert n['streams_attributes'] == {'step_s': '<s>', 'counter': 2}
    assert n['plan_kwargs'] == {'max_s': 3} and n['module_switches'] == {'execution.M7_SUSPEND_S': 120.0}
    assert rec.mask_seconds({'a_s': True, 'b_s': 'text'}) == {'a_s': True, 'b_s': 'text'}


def test_first_plan_notes_name_the_new_parts_and_the_pins_write_them():
    """The NOTES of pins 34 and 46 (pin_outputs._first_plan) carry the
    recorder's lines on the gate 7 parts: the three switches, the follow
    key, the two attribute records and their mask."""
    notes = '\n'.join(rec.first_plan_notes())
    for word in ('execution.M7,', 'execution.M7_SUSPEND_S', 'interior_regions.ENABLED', rec.FOLLOW_KEY,
                 rec.NO_MAIN_FRAME, *rec.FIRST_PLAN_SECONDS_MASKED, '<s>'):
        assert word in notes, word
    tree = ast.parse((REPO / 'tools' / 'readable' / 'pin_outputs.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_first_plan')
    calls = [n.func.attr for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert 'first_plan_notes' in calls


# ---------------------------------------------------------------------------
# D7: the crash record under C-01
# ---------------------------------------------------------------------------

_TOOL = REPO / 'tools' / 'readable' / 'record_episode.py'
# C-01's shape (test_full_pipeline.py:3681-3699): the exception is kept, the
# hook shows it, then the entry exits with the code.
_C01 = ("import sys\n"
        "try:\n"
        "    {}['missing_key']\n"
        "except Exception:\n"
        "    crash = sys.exc_info()\n"
        "sys.excepthook(*crash)\n"
        "sys.exit(CODE)\n")
_ENTRIES = {
    'c01_exit70': _C01.replace('CODE', '70'),
    'exit70_no_hook': "import sys\nsys.exit(70)\n",
    'hook_then_exit1': _C01.replace('CODE', '1'),
    'raised_out': "raise ValueError('seed 3 rejected')\n",
    # The bridge's shape (tampura_bridge/policy.py:291-319): the crash is
    # kept as the episode's error, no hook is called, the driver exits 1.
    'caught_then_exit1': ("import sys\n"
                          "try:\n"
                          "    {}['missing_key']\n"
                          "except Exception as e:\n"
                          "    error = f'{type(e).__name__}: {e}'\n"
                          "sys.exit(1)\n"),
}


class _Exit(BaseException):
    pass


def _child_in_process(tmp_path, monkeypatch, entry):
    """record_episode's child (main --child) on a small entry, in this
    process: os._exit raises instead, and what the child sets on sys is put
    back.  The hook it replaces is a recorder of its own calls."""
    script = tmp_path / 'entry.py'
    script.write_text(_ENTRIES[entry], encoding='utf-8')
    prev_calls = []

    def prev_hook(*exc):
        prev_calls.append(exc)

    def fake_exit(code):
        raise _Exit(code)
    monkeypatch.setattr(rec.os, '_exit', fake_exit)
    monkeypatch.setattr(sys, 'excepthook', prev_hook)
    for name in ('argv', 'path', 'meta_path'):
        monkeypatch.setattr(sys, name, list(getattr(sys, name)))
    with pytest.raises(_Exit) as ex:
        rec.main(['--child', '--rec', str(tmp_path / 'rec'), '--script', str(script), '--mode', 'record',
                  '--tape', str(tmp_path / 'tape')])
    crash = tmp_path / 'rec' / 'CRASH.txt'
    return (ex.value.args[0], json.loads((tmp_path / 'rec' / 'EXIT.json').read_text(encoding='utf-8')),
            crash.read_text(encoding='utf-8') if crash.exists() else None, prev_calls)


@pytest.mark.parametrize('entry, code, how, last', [
    ('c01_exit70', 70, 'crash_exit70', "KeyError: 'missing_key'"),
    ('exit70_no_hook', 70, 'system_exit', None),
    ('hook_then_exit1', 1, 'system_exit', "KeyError: 'missing_key'"),
    ('raised_out', 1, 'raised ValueError: seed 3 rejected', 'ValueError: seed 3 rejected'),
    ('caught_then_exit1', 1, 'system_exit', None)])
def test_child_crash_record(tmp_path, monkeypatch, capsys, entry, code, how, last):
    """SPEC D7: the child's own sys.excepthook writes rec/CRASH.txt and then
    calls the hook it replaced; how is crash_exit70 only for exit 70 after a
    call of the hook (a 70 without one stays system_exit, another code
    after a call too); an exception out of the entry keeps today's record,
    and so does a crash the entry keeps itself and ends with exit 1, as the
    bridge does (no CRASH.txt).  Catches the hook not installed, the old
    hook not called, any 70 taken for a crash, CRASH.txt not written, and
    CRASH.txt written for an exit without the hook's call."""
    got_code, exit_, crash, prev_calls = _child_in_process(tmp_path, monkeypatch, entry)
    assert (got_code, exit_) == (code, {'code': code, 'how': how})
    if last is None:
        assert crash is None
    else:
        assert crash.startswith('Traceback (most recent call last):')
        assert crash.rstrip('\n').splitlines()[-1] == last
    hooked = entry in ('c01_exit70', 'hook_then_exit1')
    assert [c[0] for c in prev_calls] == ([KeyError] if hooked else [])
    capsys.readouterr()


def test_c01_crash_in_a_child_process_exits_70_with_the_traceback_on_stderr(tmp_path):
    """The same as a real child: its own process, its own exit code; the
    replaced hook (Python's own) still prints the traceback to stderr."""
    script = tmp_path / 'entry.py'
    script.write_text(_ENTRIES['c01_exit70'], encoding='utf-8')
    p = subprocess.run([sys.executable, '-B', str(_TOOL), '--child', '--rec', str(tmp_path / 'rec'),
                        '--script', str(script), '--mode', 'record', '--tape', str(tmp_path / 'tape')],
                       capture_output=True, text=True, timeout=120, cwd=str(tmp_path))
    assert p.returncode == 70, p.stderr
    assert json.loads((tmp_path / 'rec' / 'EXIT.json').read_text(encoding='utf-8')) == {
        'code': 70, 'how': 'crash_exit70'}
    assert "KeyError: 'missing_key'" in p.stderr and 'Traceback (most recent call last):' in p.stderr
    assert (tmp_path / 'rec' / 'CRASH.txt').read_text(encoding='utf-8').rstrip().endswith("KeyError: 'missing_key'")


def test_crash_txt_normalised_last_line_compared_frames_info(tmp_path):
    """Of CRASH.txt the last line is compared (crash.json); the frames, with
    their line numbers, go to INFO_crash.txt (no compare reads INFO_
    files); paths masked in both."""
    text = (f'Traceback (most recent call last):\n  File "{REPO}/test_full_pipeline.py", line 2860, in main\n'
            '    transit_loss_counts[obj_str]\n'
            f"KeyError: 'red_object' at {REPO}/x\n\n")
    n = rec.normalise(_run_folder(tmp_path, crash=text))
    assert n['crash.json'] == {'last_line': "KeyError: 'red_object' at <REPO>/x"}
    assert n['INFO_crash.txt'].startswith('Traceback') and 'line 2860' in n['INFO_crash.txt']
    assert str(REPO) not in n['INFO_crash.txt'] and n['INFO_crash.txt'].endswith("<REPO>/x\n")
    assert [k for k in n if 'crash' in k.lower()] == ['crash.json', 'INFO_crash.txt']
    assert 'crash.json' not in rec.normalise(_run_folder(tmp_path / 'b'))


def test_c01_site_is_excepthook_then_finish_with_the_code_the_recorder_takes():
    """crash_exit70 rests on C-01's shape in the entry: sys.excepthook(*crash)
    and then console_ui.finish(N), once; N is the recorder's code."""
    tree = ast.parse((REPO / 'test_full_pipeline.py').read_text(encoding='utf-8'))
    found = []
    for node in ast.walk(tree):
        body = getattr(node, 'body', None)
        if not isinstance(body, list):
            continue
        for a, b in zip(body, body[1:]):
            if (isinstance(a, ast.Expr) and isinstance(a.value, ast.Call)
                    and ast.unparse(a.value.func) == 'sys.excepthook'
                    and isinstance(b, ast.Expr) and isinstance(b.value, ast.Call)
                    and ast.unparse(b.value.func) == 'console_ui.finish'):
                found.append(ast.literal_eval(b.value.args[0]))
    assert found == [rec.CRASH_EXIT_CODE]


def test_episode_notes_name_the_crash_record_and_the_pins_write_them():
    notes = '\n'.join(rec.episode_notes())
    for word in ('rec/CRASH.txt', rec.CRASH_HOW, 'system_exit', 'pre-flight', 'bridge', 'crash.json',
                 'INFO_crash.txt'):
        assert word in notes, word
    # SPEC D7's two cases that keep today's record, a line each: a crash of
    # main() in a bridge episode is not an exception out of the entry.
    lines = rec.episode_notes()
    assert [ln for ln in lines if 'bridge episode' in ln] == [rec.BRIDGE_CRASH_NOTE]
    assert [ln for ln in lines if '"raised' in ln] == [rec.RAISED_NOTE]
    assert 'raised' not in rec.BRIDGE_CRASH_NOTE and 'pre-flight' in rec.RAISED_NOTE
    for word in ('does not pass the C-01 handler', 'execute_fn', 'child_exit is system_exit', 'no rec/CRASH.txt',
                 'result.json outcome (status crashed)', 'bridge_episode.json'):
        assert word in rec.BRIDGE_CRASH_NOTE, word
    tree = ast.parse((REPO / 'tools' / 'readable' / 'pin_outputs.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_episode_notes')
    calls = [n.func.attr for n in ast.walk(fn) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert 'episode_notes' in calls and 'entry_notes' in calls


def _tries_around(tree, pred):
    """For each node pred accepts: the try statements whose body holds it,
    the innermost last (a handler, else or finally part is not the body)."""
    found = []

    def walk(node, stack):
        if pred(node):
            found.append(stack)
        if isinstance(node, ast.Try):
            for s in node.body:
                walk(s, stack + [node])
            for s in node.handlers + node.orelse + node.finalbody:
                walk(s, stack)
            return
        for child in ast.iter_child_nodes(node):
            walk(child, stack)
    walk(tree, [])
    return found


def test_bridge_crash_note_rests_on_the_bridge_s_code():
    """BRIDGE_CRASH_NOTE rests on the tag's bridge: main() is called once,
    inside a try whose except Exception keeps the error as cfg.out['error']
    and raises nothing; the driver hands that error to episode_outcome,
    which makes it crashed (run here from its own source); the driver's main
    returns the code the note names when the outcome is no success, and the
    entry ends with console_ui.finish(main()).  Catches the note filing a
    bridge crash among the exceptions out of the entry, or a code of its own."""
    pol = ast.parse((REPO / 'tampura_bridge' / 'policy.py').read_text(encoding='utf-8'))
    around = _tries_around(pol, lambda n: isinstance(n, ast.Call)
                           and ast.unparse(n.func) == 'test_full_pipeline.main')
    assert len(around) == 1 and around[0], 'main() is called once, inside a try'
    handlers = [h for h in around[0][-1].handlers if h.type is not None and ast.unparse(h.type) == 'Exception']
    assert len(handlers) == 1
    assert [n for n in ast.walk(handlers[0]) if isinstance(n, ast.Assign)
            and [ast.unparse(t) for t in n.targets] == ["cfg.out['error']"]]
    assert not [n for n in ast.walk(handlers[0]) if isinstance(n, ast.Raise)]
    gates = ast.parse((REPO / 'tools' / 'bridge_gates.py').read_text(encoding='utf-8'))
    fn = next(n for n in gates.body if isinstance(n, ast.FunctionDef) and n.name == 'episode_outcome')
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'tools/bridge_gates.py', 'exec'), ns)
    out = ns['episode_outcome']([1.0], 'KeyError: x', types.SimpleNamespace(rows=[]))
    assert (out['status'], out['success'], out['error']) == ('crashed', False, 'KeyError: x')
    drv = ast.parse((REPO / 'tampura_bridge' / 'run_bridge_on_finddice.py').read_text(encoding='utf-8'))
    main = next(n for n in drv.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    outcome = [n for n in ast.walk(main) if isinstance(n, ast.Call)
               and ast.unparse(n.func).endswith('episode_outcome')]
    assert len(outcome) == 1 and ast.unparse(outcome[0].args[1]) == "cfg.out.get('error')"
    last = main.body[-1]
    assert isinstance(last, ast.Return) and isinstance(last.value, ast.IfExp)
    assert ast.unparse(last.value.test) == "cfg.out['outcome']['success']"
    code = ast.literal_eval(last.value.orelse)
    assert code != rec.CRASH_EXIT_CODE and f'system_exit with code {code},' in rec.BRIDGE_CRASH_NOTE
    tail = [n for n in drv.body if isinstance(n, ast.If) and ast.unparse(n.test) == "__name__ == '__main__'"]
    assert len(tail) == 1 and ast.unparse(tail[0].body[-1]) == 'console_ui.finish(main())'


# ---------------------------------------------------------------------------
# D12: the coverage table and the map of sites between two files
# ---------------------------------------------------------------------------

# A main of the pipeline's shape, an older and a newer version: the newer
# one has a new exit reason with its break before the loop, a new look
# branch between pick and place, and its lines moved.
_OLD_MAIN = '''\
def main():
    while True:
        if done:
            exit_reason = 'planner_failed'
            break
        for action_name in plan:
            if action_name == 'pick':
                if a:
                    dispatch_end('stale_precondition')
                    break
                if b:
                    dispatch_end('stale_precondition')
                    print('b')
                    break
                dispatch_end('ok')
            elif action_name in ('place', 'place_hiding'):
                if c:
                    dispatch_end('place_failure')
                    break
                dispatch_end('ok')
            if stop:
                break
'''
_NEW_MAIN = '''\
def main():
    while True:
        if gave_up:
            exit_reason = 'rediscovery_giveup'
            break
        if done:
            exit_reason = 'planner_failed'
            break
        for action_name in plan:
            if action_name == 'pick':
                if a:
                    dispatch_end('stale_precondition')
                    break
                if b:
                    dispatch_end('stale_precondition')
                    print('b')
                    break
                dispatch_end('ok')
            elif action_name == 'look':
                if d:
                    dispatch_end('stale_precondition')
                    break
                dispatch_end('look_outcome')
            elif action_name in ('place', 'place_hiding'):
                if c:
                    dispatch_end('place_failure')
                    break
                dispatch_end('ok')
            if stop:
                break
'''


def _src(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding='utf-8')
    return p


def _anchor(s):
    return (s['kind'], s['value'], s['branch'], s['ordinal'])


def test_anchors_hold_kind_value_branch_and_ordinal(tmp_path):
    """SPEC D12's anchor: the kind, the value (a break's: the site it
    closes, or none), the dispatcher branch whose body holds the site (an
    elif is its own branch, not the body of the one before) and the
    ordinal among the sites with that kind, value and branch.  Catches a
    branch left out of the anchor, an elif taken as the body before it, and
    a break without the site it closes."""
    sites = rec.anchored_sites(_src(tmp_path, 'old.py', _OLD_MAIN))
    got = [(s['line'],) + _anchor(s) for s in sites]
    assert got == [
        (4, 'exit_reason', 'planner_failed', None, 0),
        (5, 'break', 'exit_reason:planner_failed', None, 0),
        (7, 'branch', ['pick'], None, 0),
        (9, 'dispatch_end', 'stale_precondition', ['pick', 0], 0),
        (10, 'break', 'dispatch_end:stale_precondition', ['pick', 0], 0),
        (12, 'dispatch_end', 'stale_precondition', ['pick', 0], 1),
        (14, 'break', 'dispatch_end:stale_precondition', ['pick', 0], 1),
        (15, 'dispatch_end', 'ok', ['pick', 0], 0),
        (16, 'branch', ['place', 'place_hiding'], None, 0),
        (18, 'dispatch_end', 'place_failure', ['place', 'place_hiding', 0], 0),
        (19, 'break', 'dispatch_end:place_failure', ['place', 'place_hiding', 0], 0),
        (20, 'dispatch_end', 'ok', ['place', 'place_hiding', 0], 0),
        (22, 'break', None, None, 0)]
    mine = {(s['kind'], s['line']) for s in sites}
    assert mine == {(k, r['line']) for k, rows in rec.main_sites(tmp_path / 'old.py').items() for r in rows}


def test_anchors_of_the_tag_are_its_main_sites_each_once():
    """On the tag's test_full_pipeline.py: the anchored sites are exactly
    main_sites' (kind and line), and no two share an anchor."""
    sites = rec.anchored_sites()
    assert {(s['kind'], s['line']) for s in sites} == {
        (k, r['line']) for k, rows in rec.main_sites().items() for r in rows}
    anchors = [json.dumps(_anchor(s)) for s in sites]
    assert len(anchors) == len(set(anchors))


def test_site_map_pairs_by_anchor_names_new_and_gone(tmp_path):
    """One to one and total: every old site paired or gone, every new one
    paired or new; lines play no part.  Catches pairing by line or by
    order of appearance (the look's stale_precondition would take the
    place of the pick's)."""
    old, new = _src(tmp_path, 'old.py', _OLD_MAIN), _src(tmp_path, 'new.py', _NEW_MAIN)
    m = rec.site_map(old, new)
    assert [(o['line'], n['line']) for o, n in m['pairs']] == [
        (4, 7), (5, 8), (7, 10), (9, 12), (10, 13), (12, 15), (14, 17), (15, 18), (16, 24), (18, 26),
        (19, 27), (20, 28), (22, 30)]
    added = [(4, 'exit_reason'), (5, 'break'), (19, 'branch'), (21, 'dispatch_end'), (22, 'break'),
             (23, 'dispatch_end')]
    assert [(n['line'], n['kind']) for n in m['new']] == added and m['gone'] == []
    back = rec.site_map(new, old)                    # the other way round: the same sites are gone
    assert [(s['line'], s['kind']) for s in back['gone']] == added and back['new'] == []


def test_site_map_fails_on_an_ambiguous_anchor(tmp_path):
    """A group the two files hold in different numbers cannot be paired
    without picking: the tool fails and names the lines."""
    third = _OLD_MAIN.replace("                dispatch_end('ok')\n            elif",
                              "                if e:\n                    dispatch_end('stale_precondition')\n"
                              "                    break\n                dispatch_end('ok')\n            elif", 1)
    assert third != _OLD_MAIN
    with pytest.raises(rec.SiteMapError, match=r"stale_precondition.*\[9, 12\] in the old file, \[9, 12, 16\]"):
        rec.site_map(_src(tmp_path, 'old.py', _OLD_MAIN), _src(tmp_path, 'third.py', third))


def _baseline(folder, path, reached):
    """A coverage file of `path` as phase0/G1's: its sites, reached when
    (kind, line) is in `reached`."""
    sites = [dict(r, kind=k, reached=(k, r['line']) in reached)
             for k, rows in rec.main_sites(path).items() for r in rows]
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / 'baseline.json'
    p.write_text(json.dumps({'sites': sites}), encoding='utf-8')
    return p


def _trace(tmp_path, lines):
    p = tmp_path / 'main_lines.json'
    p.write_text(json.dumps({'main:1': sorted(lines)}), encoding='utf-8')
    return p


def test_coverage_compare_names_a_pair_reached_before_and_not_now(tmp_path):
    """The old pins reached the place branch, place_failure and its break
    (old 16, 18, 19), the new ones do not (new 24, 26, 27): named lost.
    A branch counts as reached by the first line of its body, not by its
    if line (evaluated for every action).  A baseline of another file is
    refused.  Catches a lost pair not named, reach read at the old lines,
    a branch's if line taken as its reach, and a baseline not checked."""
    old, new = _src(tmp_path, 'old.py', _OLD_MAIN), _src(tmp_path, 'new.py', _NEW_MAIN)
    base = _baseline(tmp_path / 'b', old, {('branch', 7), ('dispatch_end', 9), ('break', 10),
                                           ('branch', 16), ('dispatch_end', 18), ('break', 19)})
    trace = _trace(tmp_path, {11, 12, 13, 24})        # the pick's first guard; the place's if line only
    c = rec.coverage_compare([trace], base, old, new)
    assert [(r['kind'], r['old_line'], r['new_line']) for r in c['lost']] == [
        ('branch', 16, 24), ('dispatch_end', 18, 26), ('break', 19, 27)]
    assert c['summary']['dispatch_end'] == {'old': 5, 'new': 7, 'paired': 5, 'new_sites': 2, 'gone': 0,
                                            'old_reached': 2, 'new_reached': 1}
    assert c['summary']['branch']['new_reached'] == 1     # the pick (body line 11), not the place
    with pytest.raises(rec.SiteMapError, match='is not of'):
        rec.coverage_compare([trace], _baseline(tmp_path / 'x', new, set()), old, new)


def test_coverage_command_prints_the_table_and_the_comparison(tmp_path, capsys, monkeypatch):
    """One call: --coverage TRACES prints the table of main_sites; with
    --baseline and --old-tfp also the comparison.  Here the tag's file
    against itself, the baseline reaching the first site of each kind and
    the trace nothing: every site paired, none new or gone, those lost."""
    sites = rec.main_sites()
    reached = {(k, rows[0]['line']) for k, rows in sites.items()}
    base = _baseline(tmp_path / 'b', rec.TFP, reached)
    trace = _trace(tmp_path, set())
    assert rec.main(['--coverage', str(trace), '--baseline', str(base), '--old-tfp', str(rec.TFP)]) == 0
    d = json.loads(capsys.readouterr().out)
    assert set(d) == {'table', 'compare'} and d['table'] == rec.coverage_table([trace])
    assert d['compare']['new'] == [] and d['compare']['gone'] == []
    assert {(r['kind'], r['old_line']) for r in d['compare']['lost']} == reached
    assert all(r['old_line'] == r['new_line'] for r in d['compare']['map'])
    with pytest.raises(SystemExit):
        rec.main(['--coverage', str(trace), '--baseline', str(base)])

    def ambiguous(*a, **k):
        raise rec.SiteMapError('ambiguous anchors, not paired: x')
    monkeypatch.setattr(rec, 'coverage_compare', ambiguous)
    capsys.readouterr()
    assert rec.main(['--coverage', str(trace), '--baseline', str(base), '--old-tfp', str(rec.TFP)]) == 3
    out = capsys.readouterr()
    assert 'ambiguous anchors' in out.err and out.out == ''


# ---------------------------------------------------------------------------
# D16: the executor stub place_fail
# ---------------------------------------------------------------------------

def _execution_stand_in(calls):
    """execution's two names the stub uses, with the tag's signatures."""
    mod = types.ModuleType('execution')

    def execute_place(robot_id, env, obj_name, place_pos, grasp, config, held_body_id, gui, held_aabb=None):
        calls.append(('execute_place', obj_name))
        return 'placed'

    def open_gripper(robot_id, gui=False, placing=False):
        calls.append(('open_gripper', robot_id, gui, placing))
    mod.execute_place, mod.open_gripper = execute_place, open_gripper
    return mod


def _place_fail(tmp_path, fingers):
    calls = []
    mod = _execution_stand_in(calls)
    hooks = {}
    stubs.install({'stubs': [{'name': 'place_fail', 'object': 'orange', 'fingers': fingers}]}, tmp_path,
                  lambda name, fn: hooks.setdefault(name, fn))
    assert sorted(hooks) == ['execution']
    hooks['execution'](mod)
    return mod, calls


def _stub_rows(tmp_path):
    return [json.loads(x) for x in (tmp_path / 'stubs.jsonl').read_text(encoding='utf-8').splitlines()]


def test_place_fail_closed_returns_none_for_the_named_object_and_touches_nothing(tmp_path, capsys):
    """Arm (a): None for the named object at every call, the gripper left
    as it is; any other object placed for real.  Catches the stub firing
    for another object or only once, and a closed arm that moves the
    fingers."""
    mod, calls = _place_fail(tmp_path, 'closed')
    assert mod.execute_place(0, None, 'orange', [0, 0, 0], 'g', 'q', 7, True, held_aabb=None) is None
    assert mod.execute_place(0, None, 'orange', [0, 0, 0], 'g', 'q', 7, True) is None
    assert mod.execute_place(0, None, 'red', [0, 0, 0], 'g', 'q', 8, False) == 'placed'
    assert calls == [('execute_place', 'red')]
    assert _stub_rows(tmp_path) == [{'fingers': 'closed', 'obj': 'orange', 'result': None,
                                     'stub': 'execute_place'}] * 2
    assert capsys.readouterr().out.count('place of orange: failed, fingers closed (executor stub)') == 2


def test_place_fail_open_opens_with_the_executor_s_own_function_then_returns_none(tmp_path, capsys):
    """Arm (b): the executor's own open_gripper with the call's gui and
    placing=True (a place's release, which the drop count does not count),
    then None.  Catches the open left out, another gui, placing left out."""
    mod, calls = _place_fail(tmp_path, 'open')
    assert mod.execute_place(3, None, 'orange', [0, 0, 0], 'g', 'q', 7, True) is None
    assert mod.execute_place(3, None, 'orange', [0, 0, 0], 'g', 'q', 7, gui=False, held_aabb=(0, 1)) is None
    assert calls == [('open_gripper', 3, True, True), ('open_gripper', 3, False, True)]
    assert [r['fingers'] for r in _stub_rows(tmp_path)] == ['open', 'open']
    capsys.readouterr()


def test_place_fail_needs_its_object_and_an_arm(tmp_path):
    """The name list stays closed and a place_fail says which object and
    which arm, or nothing is installed or written."""
    assert 'place_fail' in stubs.NAMES
    for bad in ({'name': 'place_fail', 'object': 'orange'}, {'name': 'place_fail', 'fingers': 'open'},
                {'name': 'place_fail', 'object': 'orange', 'fingers': 'half'}):
        with pytest.raises(ValueError, match='place_fail needs'):
            stubs.install({'stubs': [bad]}, tmp_path / 'rec', lambda n, f: None)
    assert not (tmp_path / 'rec').exists()


def test_place_fail_reaches_both_arms_of_the_tag_s_place_branch():
    """What the stub rests on, read from the tag's code: the dispatcher
    takes `place_result is None` with the fingers' probe (a finger at or
    over a threshold means open); execution's open_gripper is
    robot_utils.open_gripper, which drives both fingers to a target at or
    over that threshold; execute_place takes gui.  So arm (b) finds the
    fingers open, arm (a) leaves them on the object."""
    tfp = ast.parse((REPO / 'test_full_pipeline.py').read_text(encoding='utf-8'))
    branch = [n for n in ast.walk(tfp) if isinstance(n, ast.If) and ast.unparse(n.test) == 'place_result is None']
    assert len(branch) == 1
    probes = [n for n in branch[0].body if isinstance(n, ast.Assign)
              and [getattr(t, 'id', None) for t in n.targets] == ['fingers_open']]
    assert len(probes) == 1
    cmp = next(n for n in ast.walk(probes[0].value) if isinstance(n, ast.Compare))
    assert isinstance(cmp.ops[0], ast.GtE)
    threshold = ast.literal_eval(cmp.comparators[0])
    ru = ast.parse((REPO / 'robot_utils.py').read_text(encoding='utf-8'))
    og = next(n for n in ru.body if isinstance(n, ast.FunctionDef) and n.name == 'open_gripper')
    targets = [ast.literal_eval(k.value) for n in ast.walk(og) if isinstance(n, ast.Call)
               for k in n.keywords if k.arg == 'targetPosition']
    assert len(targets) == 2 and min(targets) >= threshold
    ex = ast.parse((REPO / 'execution.py').read_text(encoding='utf-8'))
    assert any(isinstance(n, ast.ImportFrom) and n.module == 'robot_utils'
               and 'open_gripper' in [a.name for a in n.names] for n in ex.body)
    ep = next(n for n in ex.body if isinstance(n, ast.FunctionDef) and n.name == 'execute_place')
    assert [a.arg for a in ep.args.args][:3] == ['robot_id', 'env', 'obj_name'] and 'gui' in [
        a.arg for a in ep.args.args]


# ---------------------------------------------------------------------------
# Item 7: the counts at storing, D3's twins
# ---------------------------------------------------------------------------

_ROWS = [
    {'kind': 'step', 'plan': 1, 'step': 1},
    {'kind': 'sense_result', 'reason': 'sense_found_target', 'continue_': True},
    {'kind': 'sense_result', 'reason': 'sense_contains_unlocalizable', 'continue_': False},
    {'kind': 'sense_result', 'reason': 'sense_contains_nontarget', 'continue_': False},
    {'kind': 'sense_discovery', 'body': 'cup', 'region': 'shadow_1'},
    {'kind': 'sense_discovery', 'body': 'ball', 'region': 'shadow_1'},
    {'kind': 'm7_suspension', 'op': 'start', 'region': 'shadow_1', 'seconds': 120.0},
    {'kind': 'm7_suspension', 'op': 'end', 'region': 'shadow_1', 'ended_by': 'released'},
]


def test_ledger_counts_count_the_rows_d3_and_d4_decide_on():
    """The unlocalizable sense returns before M7's code and does not count;
    a suspension's start and end are counted apart."""
    assert rec.ledger_counts(_ROWS) == {'m7_suspension_start': 1, 'm7_suspension_end': 1,
                                        'sense_discovery': 2, 'sense_result_contains_nontarget': 1}
    assert rec.ledger_counts(None) == rec.ledger_counts([])


def test_twin_rule_of_d3():
    """A sense_discovery row or a contains_nontarget sense: a twin, also for
    a D entry and an R entry; none for an entry that sets --m7 itself, none
    without such a row (an unlocalizable sense alone included).  R has no
    sense action with the look (SPEC D1), so no such row is expected there,
    but the rule is the same: catches a rule that gives R no twin."""
    c = rec.ledger_counts
    assert rec.twin_rule('f204', c(_ROWS))['name'] == 'f204_m7off'
    assert rec.twin_rule('f140', c(_ROWS[:3])) == {'name': None, 'reasons': [], 'none_because': 'no such row'}
    assert rec.twin_rule('rp0', c(_ROWS[3:4]))['name'] == 'rp0_m7off'
    assert rec.twin_rule('br0', c(_ROWS[4:5]))['reasons'] == ['1 sense_discovery row(s)']
    assert rec.twin_rule('r140', c(_ROWS[4:5]))['name'] == 'r140_m7off'
    assert rec.twin_rule('r141', c(_ROWS[:3])) == {'name': None, 'reasons': [], 'none_because': 'no such row'}
    assert rec.twin_rule('rp0_look', c(_ROWS[3:4]))['name'] == 'rp0_look_m7off'
    for twin in ('f204_m7off', 'r140_m7off'):
        off = rec.twin_rule(twin, c(_ROWS))
        assert off['name'] is None and off['none_because'] == 'the entry sets --m7 itself'


def _fake_recorder(monkeypatch, ledgers, status=None, sets_seen=None):
    """run_episode replaced by one that writes, as the real one does, the
    normalised ledger it is given, RESULT.json with the folder's paths and
    a tape META.json for a set; the names asked for in calls, the sets in
    sets_seen."""
    calls = []

    def fake(name, mode, run_dir, log=print, sets=None, **k):
        assert mode == 'record'
        calls.append(name)
        if sets_seen is not None:
            sets_seen.append(sets)
        run_dir = Path(run_dir).resolve()
        (run_dir / 'norm').mkdir(parents=True)
        (run_dir / 'tape').mkdir()
        (run_dir / 'norm' / 'ledger.json').write_text(json.dumps(ledgers.get(name, [])), encoding='utf-8')
        if sets:
            rec.write_json(run_dir / 'tape' / 'META.json', {'set': sets})
        result = {'status': (status or {}).get(name, 'ended'), 'set': sets or None, 'tape': str(run_dir / 'tape'),
                  'pipeline_run_dir': str(run_dir / 'save' / 'ours' / 'run_x'), 'cwd': str(run_dir / 'gen'),
                  'argv': ['--save-dir', str(run_dir / 'save'), '--vis', '0']}
        rec.write_json(run_dir / 'RESULT.json', result)
        return result
    monkeypatch.setattr(rec, 'run_episode', fake)
    return calls


def test_record_set_stores_the_counts_and_records_the_twin_right_after(tmp_path, monkeypatch):
    """At storing: STORED.json beside each tape and STORE.json over the set,
    the twin recorded right after its on recording, once, and none after a
    recording the time limit ended.  Catches a twin not recorded, recorded
    twice, recorded after a timeout, and the counts not written."""
    calls = _fake_recorder(monkeypatch, {'f204': _ROWS, 'f293': _ROWS}, {'f293': 'timeout'})
    assert rec.record_set(tmp_path / 'a', ['f204', 'f140'], log=lambda s: None) == 0
    assert calls == ['f204', 'f204', 'f204_m7off', 'f140']      # D4 (item 10): _ROWS hold m7_suspension rows
    stored = json.loads((tmp_path / 'a' / 'f204' / 'STORED.json').read_text(encoding='utf-8'))
    assert stored['counts'] == rec.ledger_counts(_ROWS) and stored['ledger_rows'] == len(_ROWS)
    assert stored['twin']['name'] == 'f204_m7off' and stored['d4']['m7_suspension_rows'] == 2
    store = json.loads((tmp_path / 'a' / 'STORE.json').read_text(encoding='utf-8'))
    assert list(store) == ['f204', 'f204_m7off', 'f140'] and store['f140']['twin']['name'] is None
    calls.clear()
    assert rec.record_set(tmp_path / 'b', ['f204', 'f204_m7off'], log=lambda s: None) == 0
    assert calls == ['f204', 'f204', 'f204_m7off']
    calls.clear()
    assert rec.record_set(tmp_path / 'c', ['f293'], log=lambda s: None) == 1
    assert calls == ['f293']
    assert json.loads((tmp_path / 'c' / 'f293' / 'STORED.json').read_text(encoding='utf-8'))['twin'] == {
        'name': None, 'reasons': [], 'none_because': 'the recording ended as timeout'}
    assert rec.record_set(tmp_path / 'a', ['f141'], log=lambda s: None) == 0    # one set, two calls
    assert list(json.loads((tmp_path / 'a' / 'STORE.json').read_text(encoding='utf-8'))) == [
        'f204', 'f204_m7off', 'f140', 'f141']


# ---------------------------------------------------------------------------
# Item 8: D6 for the older time keys (masked, the key kept)
# ---------------------------------------------------------------------------

def _raw_episode(times=0.0, count=5):
    """The raw outputs of one episode in the shapes of T9's br0: every wall
    time moved by times, and count, a number that is no time, in each of
    the five files."""
    t = 837.0 + times
    ledger = [
        {'t': t, 'wall': 1795247506.5 + times, 'kind': 'ledger_open', 'pid': 1146},
        {'t': t + 0.1, 'wall': 1795247506.6 + times, 'kind': 'driver_clock',
         'events': [['seeded', 832.9 + times], ['rollout_start', 836.9 + times]], 'seed': 0},
        {'t': t + 0.2, 'wall': 1795247506.7 + times, 'kind': 'bridge_timing', 'd9_setup_s': 0.5 + times,
         'env_build_s': 1.25 + times, 'client': count},
        {'t': t + 1.0, 'wall': 1795247507.5 + times, 'kind': 'plan', 'plan_id': 1, 'call': 'mission',
         'plan_time_s': 1.25 + times, 'plan_obj': 140001, 'actions': [['move', 'q0']]},
        {'t': None, 'wall': 1795247508.0 + times, 'kind': 'step', 'plan': 1, 'step': 1, 'action': 'move'},
        {'t': t + 2.0, 'wall': 1795247509.0 + times, 'kind': 'm7_suspension', 'op': 'start',
         'region': 'shadow_1', 'bodies': {'cup': 3}, 'seconds': 120.0},
    ]
    eye = [
        {'k': 1, 'tag': 'initial observation', 't_wall': 0.11 + times, 'sim_step': 0, 'sim_t': 0.0},
        {'k': 2, 'tag': 'plan#1 planned', 't_wall': 1.44 + times, 'sim_step': 360, 'sim_t': 1.5,
         'extra': {'plan_time_s': 1.25 + times, 'n_actions': count}},
    ]
    summary = {
        'success': True, 'plan_count': 1,
        'm8': {'per_plan': [{'twin_render_s': 0.42 + times, 'twin_renders': count, 'build_s': None,
                             'over_region_s': 0.155 + times, 'plan': 1}]},
        'total_planning_time_s': 1.25 + times, 'per_call_planning_time_s': [1.25 + times],
        'm7_suspend_s': 120.0,
        'm7_suspensions': [{'region': 'shadow_1', 'bodies': {'cup': 3}, 'start_s': 2.0 + times,
                            'until_s': 122.0 + times, 'end_s': None, 'ended_by': 'open_at_end'}],
        'counts_cost_s': 0.05 + times}
    counts = {'drops': [], 'mode': 'counts', 'steps': count, 'closed': True, 'check_s': 0.05 + times}
    bridge = {'seed': 0, 'rewards': [0.0, 1.0], 'time_deltas': [9.59 + times, 9.62 + times],
              'driver_clock': {'events': [['seeded', 832.9 + times]], 'seed': 0},
              'ledger_gates': [['G18', 'PASS', f'initialize return to rollout start {0.027 + times:.3f} s '
                                               f'(initialize_call +{0.008 + times:.3f} s)']],
              'drops': count, 'counts_cost_s': 0.05 + times}
    return {'ledger.jsonl': ledger, 'eye.jsonl': eye, 'timing_summary.json': summary,
            'world_counts.json': counts}, bridge


def _norm_episode(folder, **kw):
    pipeline, bridge = _raw_episode(**kw)
    return rec.normalise(_run_folder(folder, pipeline=pipeline, bridge=bridge))


_TIME_FILES = ('ledger.json', 'eye.json', 'timing_summary.json', 'world_counts.json', 'bridge_episode.json')


def test_ledger_and_eye_times_masked_keys_and_rows_kept_pid_removed(tmp_path):
    """R's ruling on the older time keys (SPEC D6): t, wall, plan_time_s,
    the bridge_timing *_s, the driver_clock event times, t_wall and
    extra.plan_time_s become <s>, null stays null, every key and row stays
    in its order; the pid is removed as before; sim_t and the M7 row's
    configured length are compared.  Catches a time dropped or left in, a
    kept pid and a masked null."""
    pipeline, _ = _raw_episode()
    n = rec.normalise(_run_folder(tmp_path, pipeline=pipeline))
    s = '<s>'
    led = n['ledger.json']
    assert led[0] == {'t': s, 'wall': s, 'kind': 'ledger_open'}
    assert led[1]['events'] == [['seeded', s], ['rollout_start', s]] and led[1]['seed'] == 0
    assert led[2] == {'t': s, 'wall': s, 'kind': 'bridge_timing', 'd9_setup_s': s, 'env_build_s': s, 'client': 5}
    assert led[3]['plan_time_s'] == s and led[3]['plan_obj'] == 'obj#1'
    assert led[4]['t'] is None and led[4]['wall'] == s
    assert led[5]['seconds'] == 120.0 and led[5]['t'] == s
    assert [list(r) for r in led] == [[k for k in r if k != 'pid'] for r in pipeline['ledger.jsonl']]
    eye = n['eye.json']
    assert [r['t_wall'] for r in eye] == [s, s] and [r['sim_t'] for r in eye] == [0.0, 1.5]
    assert eye[1]['extra'] == {'plan_time_s': s, 'n_actions': 5}
    assert [list(r) for r in eye] == [list(r) for r in pipeline['eye.jsonl']]


def test_timing_files_mask_every_s_number_m7_rows_masked_length_kept(tmp_path):
    """timing_summary.json and world_counts.json: every number under a key
    ending in _s, the three keys once dropped by name among them, becomes
    <s>, also in a list; null stays.  The M7 keys as D6's M7 part says
    (item 10): m7_suspend_s kept with its value, start_s and until_s of
    each m7_suspensions row masked, end_s null kept.  Catches the old drop
    and a masked null."""
    pipeline, _ = _raw_episode()
    n = rec.normalise(_run_folder(tmp_path, pipeline=pipeline))
    s = '<s>'
    ts = n['timing_summary.json']
    assert (ts['total_planning_time_s'], ts['per_call_planning_time_s'], ts['counts_cost_s']) == (s, [s], s)
    assert ts['m8']['per_plan'] == [{'twin_render_s': s, 'twin_renders': 5, 'build_s': None,
                                     'over_region_s': s, 'plan': 1}]
    assert ts['m7_suspend_s'] == 120.0          # D6's M7 part (item 10c): the length stays with its value
    assert ts['m7_suspensions'] == [{'region': 'shadow_1', 'bodies': {'cup': 3}, 'start_s': s, 'until_s': s,
                                     'end_s': None, 'ended_by': 'open_at_end'}]
    assert list(ts) == list(pipeline['timing_summary.json'])
    assert n['world_counts.json'] == {'drops': [], 'mode': 'counts', 'steps': 5, 'closed': True, 'check_s': s}


def test_bridge_episode_time_deltas_and_s_numbers_masked_list_kept(tmp_path):
    """bridge_episode.json: time_deltas keeps its list with every number
    masked, counts_cost_s and the driver_clock event times masked, the G18
    detail's seconds masked by the console masks, the rest compared."""
    pipeline, bridge = _raw_episode()
    be = rec.normalise(_run_folder(tmp_path, pipeline=pipeline, bridge=bridge))['bridge_episode.json']
    s = '<s>'
    assert be['time_deltas'] == [s, s] and be['counts_cost_s'] == s and be['rewards'] == [0.0, 1.0]
    assert be['driver_clock'] == {'events': [['seeded', s]], 'seed': 0}
    assert be['ledger_gates'] == [['G18', 'PASS', 'initialize return to rollout start <T> s '
                                                  '(initialize_call +<T> s)']]
    assert list(be) == list(bridge) and be['drops'] == 5


def test_runs_that_differ_in_times_alone_normalise_equal_a_count_shows(tmp_path):
    """Two runs whose wall times differ normalise to the same five files;
    a number that is no time shows in each of them.  Catches a time left
    in and a mask so wide that it hides a count."""
    a = _norm_episode(tmp_path / 'a')
    b = _norm_episode(tmp_path / 'b', times=7.5)
    c = _norm_episode(tmp_path / 'c', count=6)
    assert {f: a[f] for f in _TIME_FILES} == {f: b[f] for f in _TIME_FILES}
    assert [f for f in _TIME_FILES if a[f] == c[f]] == []


def test_episode_notes_name_every_masked_time_key():
    """The normalisation line of every episode pin's NOTES names each time
    key the code masks, the mask, the M7 keys (the length and each time key
    of a suspension row, read from run_logger) and the pid still removed;
    nothing of the old removals."""
    line = rec.episode_notes()[0]
    keys = [*rec.LEDGER_TIME_KEYS, *[k for ks in rec.LEDGER_TIME_KEYS_BY_KIND.values() for k in ks],
            *rec.EYE_TIME_KEYS, *rec.EYE_EXTRA_TIME_KEYS, rec.M7_LENGTH_KEY, rec.M7_ROWS_KEY,
            *_suspension_row_keys(), rec.SECONDS_MASK]
    for word in keys + ['bridge_timing *_s', 'driver_clock', 'time_deltas', 'timing_summary', 'world_counts',
                        'bridge_episode', 'null kept', 'SPEC D6']:
        assert word in line, word
    for kind, dropped in rec.LEDGER_DROP_BY_KIND.items():
        for k in dropped:
            assert f'{kind}.{k} removed' in line
    assert 'times removed' not in line and 'time keys removed' not in line
    assert 'as before' not in line and 'm7_suspensions removed' not in line


def _suspension_row_keys():
    """The keys of an m7_suspensions row, read from the dict that
    run_logger.suspension_rows builds (run_logger.py:421-423)."""
    tree = ast.parse((REPO / 'run_logger.py').read_text(encoding='utf-8'))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'suspension_rows')
    row, = [n for n in ast.walk(fn) if isinstance(n, ast.Dict)]
    return [k.value for k in row.keys]


def test_m7_rows_keep_every_key_their_times_masked_the_length_kept(tmp_path):
    """SPEC D6's M7 part (U2 and R's ruling; item 10c): each m7_suspensions
    row keeps the keys run_logger.suspension_rows writes, those ending in
    _s with a number masked and null kept; region, bodies and ended_by are
    compared as they are, a body whose name ends in _s too; m7_suspend_s,
    the configured length, keeps its value, so D4's length shows and the
    rest stays equal.  Catches a row's times dropped or left in, the length
    masked or dropped, a mask that reaches into bodies, a masked null."""
    keys = _suspension_row_keys()
    masked = [k for k in keys if k.endswith('_s')]
    pipeline, _ = _raw_episode()
    first = pipeline['timing_summary.json']['m7_suspensions'][0]
    assert list(first) == keys and masked
    first.update(bodies={'cup': 3, 'lid_s': 2}, end_s=130.5, ended_by='released')
    second = dict(first, region='shadow_2', end_s=None, ended_by='open_at_end')
    pipeline['timing_summary.json']['m7_suspensions'].append(second)
    ts = rec.normalise(_run_folder(tmp_path / 'a', pipeline=pipeline))['timing_summary.json']
    assert ts['m7_suspend_s'] == pipeline['timing_summary.json']['m7_suspend_s']
    assert ts['m7_suspensions'] == [{k: ('<s>' if k in masked and v is not None else v) for k, v in r.items()}
                                    for r in (first, second)]
    assert ts['m7_suspensions'][0]['bodies'] == {'cup': 3, 'lid_s': 2} and ts['m7_suspensions'][1]['end_s'] is None
    pipeline['timing_summary.json']['m7_suspend_s'] = rec.D4_SET['execution.M7_SUSPEND_S']
    long = rec.normalise(_run_folder(tmp_path / 'b', pipeline=pipeline))['timing_summary.json']
    assert long['m7_suspend_s'] == rec.D4_SET['execution.M7_SUSPEND_S'] != ts['m7_suspend_s']
    assert dict(long, m7_suspend_s=None) == dict(ts, m7_suspend_s=None)


# ---------------------------------------------------------------------------
# Item 9: REVIEW_PHASE0 item 5's NOTES for the episode pins
# ---------------------------------------------------------------------------

# (file of the tag, function, statement): what each claim of the order NOTES
# rests on.
_ORDER_SITES = [
    ('pddlstream_planner.py', '_build_init', 'random.shuffle(init)'),
    ('pddlstream_planner.py', '_build_init',
     'for shadow_id, blocker_ids in self.shadow_occluder_map.items():'),
    ('pddlstream_planner.py', '_build_init', 'for (free_id, shadow_id) in placement_blocks:'),
    ('pddlstream_planner.py', '_build_init', 'all_obj_ids = {fact[1] for fact in init'),
    ('pddlstream_planner.py', '_build_init', 'for obj_id in all_obj_ids:'),
    ('pddlstream_planner.py', '_compute_placement_view_blocks', 'blocking = set()'),
    ('pddlstream_planner.py', '_compute_placement_view_blocks', 'return blocking, egregious'),
    ('pddlstream_planner.py', 'create_problem', 'self.last_init = init'),
    ('execution.py', 'compute_shadow_blockers', 'blocker_set = set()'),
    ('execution.py', 'compute_shadow_blockers', 'blockers[shadow_id] = list(blocker_set)'),
    ('test_full_pipeline.py', 'main', '_named = [str(f[2]) for f in planner.last_init'),
    ('test_full_pipeline.py', 'main', "ledger_event('look_reveals', config=look_q.name, named=_named)"),
    ('run_logger.py', '_ledger_default', 'return list(obj)'),
]


def _site_holds(text, fn, stmt):
    """The statement stands once in the one function of that name."""
    fns = [n for n in ast.walk(ast.parse(text)) if isinstance(n, ast.FunctionDef) and n.name == fn]
    return len(fns) == 1 and ast.get_source_segment(text, fns[0]).count(stmt) == 1


def test_order_notes_rest_on_the_tag_s_code():
    """Each site the order NOTES describe stands in the tag's code as they
    say: the shuffle of the init list, the three sets read before it, the
    shuffled list kept as last_init and read for look_reveals, the ledger's
    writing of a set.  Catches a NOTES line that no longer matches the
    code (a changed site fails here, as the sorted blockers below do)."""
    texts = {f: (REPO / f).read_text(encoding='utf-8') for f in {s[0] for s in _ORDER_SITES}}
    assert [s for s in _ORDER_SITES if not _site_holds(texts[s[0]], s[1], s[2])] == []
    sorted_blockers = texts['execution.py'].replace('blockers[shadow_id] = list(blocker_set)',
                                                    'blockers[shadow_id] = sorted(blocker_set)')
    assert not _site_holds(sorted_blockers, 'compute_shadow_blockers',
                           'blockers[shadow_id] = list(blocker_set)')


def test_order_notes_name_each_list_and_the_sets_it_comes_from():
    """R's rule 4 as amended: the NOTES of every episode pin name each list
    compared in an order that comes from a set (facts.json, the ledger's
    look_reveals.named), the sets, and boxel_data.json as found without
    one; the first-plan pins also name planner_attributes.shadow_occluder_map.
    Catches a list or a set left unnamed and the notes not written."""
    notes = '\n'.join(rec.episode_notes())
    for word in ('facts.json', 'random.shuffle(init)', '_build_init', 'compute_shadow_blockers',
                 'list(blocker_set)', 'shadow_occluder_map', '_compute_placement_view_blocks',
                 'placement_blocks', 'all_obj_ids', 'look_reveals.named', 'planner.last_init',
                 '_ledger_default', 'boxel_data.json', 'PYTHONHASHSEED=0', "R's rule 4",
                 'REVIEW_PHASE0 item 5', 'real until shown to be order only'):
        assert word in notes, word
    first = '\n'.join(rec.first_plan_notes())
    for word in ('planner_attributes.shadow_occluder_map', 'list(blocker_set)', 'PYTHONHASHSEED=0',
                 "R's rule 4"):
        assert word in first, word
    assert rec.plain_form({'b', 'a'}) == {'set': ['a', 'b']}        # "written sorted by the recorder"


# ---------------------------------------------------------------------------
# Item 10, D5: --set NAME=VALUE in the child
# ---------------------------------------------------------------------------

def test_set_takes_a_name_of_the_closed_list_and_a_value_float_reads():
    """SPEC D5: NAME from SET_NAMES only, VALUE through float() and nothing
    else.  Catches an open list and a value read another way."""
    name = rec.SET_NAMES[0]
    assert rec.parse_set(f'{name}=1e9') == (name, 1e9) and rec.parse_set(f'{name}=120') == (name, 120.0)
    for bad in ('execution.M7=0', name, f'{name}=2*60', f'{name}=', f'{name}_X=1', f'x{name}=1'):
        with pytest.raises(rec.SetError):
            rec.parse_set(bad)


def _fake_popen(monkeypatch):
    """The recorder's subprocess.Popen replaced: each child's command is
    kept and nothing starts."""
    cmds = []

    class Proc:
        def __init__(self, cmd, **kw):
            cmds.append(cmd)

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass
    monkeypatch.setattr(rec.subprocess, 'Popen', Proc)
    return cmds


def _sets_in(cmd):
    return [cmd[i + 1] for i, x in enumerate(cmd) if x == '--set']


def test_parent_refuses_an_unlisted_set_and_starts_nothing(tmp_path, monkeypatch, capsys):
    cmds = _fake_popen(monkeypatch)
    with pytest.raises(SystemExit) as ex:
        rec.main(['--episode', 'rp0', '--mode', 'record', '--run-dir', str(tmp_path / 'r'),
                  '--set', 'execution.M7=0'])
    assert ex.value.code == 2 and cmds == [] and not (tmp_path / 'r').exists()
    assert 'execution.M7=0' in capsys.readouterr().err


def test_recording_puts_the_set_in_the_tape_meta_and_the_replay_takes_it(tmp_path, monkeypatch):
    """A recording with a set writes it to tape/META.json and hands it to the
    child; a replay of that tape hands the child the meta's value unasked;
    a --set that differs from the meta, also on a tape without one, is
    refused before anything starts.  Catches a replay without the recorded
    value, a differing set taken, and no meta."""
    cmds = _fake_popen(monkeypatch)
    name, quiet = rec.SET_NAMES[0], (lambda s: None)
    res = rec.run_episode('rp0', 'record', tmp_path / 'live', sets={name: '1e9'}, log=quiet)
    assert rec.tape_meta(tmp_path / 'live' / 'tape') == {'set': {name: 1e9}} and res['set'] == {name: 1e9}
    assert [rec.parse_set(s) for s in _sets_in(cmds[-1])] == [(name, 1e9)]
    res = rec.run_episode('rp0', 'replay', tmp_path / 'rep', tape=tmp_path / 'live' / 'tape', log=quiet)
    assert [rec.parse_set(s) for s in _sets_in(cmds[-1])] == [(name, 1e9)] and res['set'] == {name: 1e9}
    started = len(cmds)
    with pytest.raises(rec.SetError):
        rec.run_episode('rp0', 'replay', tmp_path / 'rep2', tape=tmp_path / 'live' / 'tape',
                        sets={name: 120.0}, log=quiet)
    rec.run_episode('rp0', 'record', tmp_path / 'plain', log=quiet)
    assert _sets_in(cmds[-1]) == [] and rec.tape_meta(tmp_path / 'plain' / 'tape') == {}
    with pytest.raises(rec.SetError):
        rec.run_episode('rp0', 'replay', tmp_path / 'rep3', tape=tmp_path / 'plain' / 'tape',
                        sets={name: 1e9}, log=quiet)
    assert len(cmds) == started + 1 and not (tmp_path / 'rep2').exists() and not (tmp_path / 'rep3').exists()


_STAND_IN = 'M7_SUSPEND_S = 120.0\n\n\ndef suspend_length():\n    return M7_SUSPEND_S\n'


def _import_stand_in(tmp_path, monkeypatch, module, source):
    """Import a stand-in module from tmp_path through the hooks the test
    set; sys.meta_path and sys.modules as they were afterwards."""
    monkeypatch.syspath_prepend(str(tmp_path))
    (tmp_path / f'{module}.py').write_text(source, encoding='utf-8')
    try:
        return importlib.import_module(module)
    finally:
        sys.modules.pop(module, None)


def test_set_applied_right_after_its_module_is_executed_beside_a_stub(tmp_path, monkeypatch):
    """The child's --set: the value is on the module right after the module
    is executed, before anything reads it, and the applied pair is in
    rec/SET.json; a stub of the same module (the executor stubs take the
    same path) still fires, after it.  Catches a second finder for one
    module (one of the two would never fire) and a set not written."""
    monkeypatch.setattr(sys, 'meta_path', list(sys.meta_path))
    (tmp_path / 'rec').mkdir()
    seen = []
    rec._install_sets({'wpb_set_target.M7_SUSPEND_S': 1e9}, tmp_path / 'rec')
    rec.patch_on_load('wpb_set_target', lambda mod: seen.append(mod.suspend_length()))
    mod = _import_stand_in(tmp_path, monkeypatch, 'wpb_set_target', _STAND_IN)
    assert mod.M7_SUSPEND_S == 1e9 and mod.suspend_length() == 1e9 and seen == [1e9]
    assert json.loads((tmp_path / 'rec' / 'SET.json').read_text(encoding='utf-8')) == {
        'wpb_set_target.M7_SUSPEND_S': 1e9}
    assert [f for f in sys.meta_path if isinstance(f, rec._PatchOnLoad)] == []


def test_set_of_an_attribute_the_module_lacks_fails_at_its_import(tmp_path, monkeypatch):
    """A name the module does not hold would set nothing: the import fails."""
    monkeypatch.setattr(sys, 'meta_path', list(sys.meta_path))
    (tmp_path / 'rec').mkdir()
    rec._install_sets({'wpb_set_bare.M7_SUSPEND_S': 1.0}, tmp_path / 'rec')
    with pytest.raises(rec.SetError):
        _import_stand_in(tmp_path, monkeypatch, 'wpb_set_bare', 'OTHER = 1\n')
    assert not (tmp_path / 'rec' / 'SET.json').exists()


def test_result_json_and_the_notes_carry_the_value_the_child_set(tmp_path):
    """The compared result.json holds what the child set (rec/SET.json),
    and the pin's NOTES say it, for a replay with where it came from;
    nothing when nothing was set.  The episode pins hand their run folder
    to the notes."""
    run = _run_folder(tmp_path)
    name = rec.SET_NAMES[0]
    assert 'set' not in rec.normalise(run)['result.json'] and rec.run_notes(run) == []
    rec.write_json(run / 'rec' / 'SET.json', {name: 1e9})
    assert rec.normalise(run)['result.json']['set'] == {name: 1e9}
    (line,) = rec.run_notes(run)
    assert name in line and repr(1e9) in line and 'SPEC D5' in line and 'META.json' not in line
    tape = tmp_path / 'tape'
    tape.mkdir()
    rec.write_json(tape / 'META.json', {'set': {name: 1e9}, 'd4': 'SPEC D4: the reason'})
    res = json.loads((run / 'RESULT.json').read_text(encoding='utf-8'))
    rec.write_json(run / 'RESULT.json', dict(res, mode='replay', tape=str(tape)))
    (line,) = rec.run_notes(run)
    assert 'META.json' in line and 'SPEC D4: the reason' in line and rec.run_notes(None) == []
    tree = ast.parse((REPO / 'tools' / 'readable' / 'pin_outputs.py').read_text(encoding='utf-8'))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, 'id', None) == '_episode_notes']
    assert len(calls) == 4 and all(len(c.args) == 4 for c in calls)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_episode_notes')
    assert 'run_notes' in [n.func.attr for n in ast.walk(fn) if isinstance(n, ast.Call)
                           and isinstance(n.func, ast.Attribute)]


# ---------------------------------------------------------------------------
# Item 10, D4: a tape with m7_suspension rows recorded again
# ---------------------------------------------------------------------------

def test_d4_records_again_with_the_region_never_coming_back_and_keeps_the_first(tmp_path, monkeypatch):
    """SPEC D4: a recording whose live run holds m7_suspension rows is made
    again at once with D4_SET in the child; the tape's META.json holds the
    value and D4's reason; the first recording stays beside it as
    <name>.as_recorded with the paths of its RESULT.json moved along;
    STORED.json names both.  A recording without such rows is stored as
    recorded, and so is one the time limit ended, its STORED.json saying
    why.  Catches no second recording, one without the value, the first
    one lost, its paths left on the new folder, no reason in the meta, the
    first one unnamed, and a timeout said to be recorded again."""
    seen = []
    calls = _fake_recorder(monkeypatch, {'f293': _ROWS, 'f140': _ROWS[:3]}, sets_seen=seen)
    assert rec.record_set(tmp_path, ['f293', 'f140'], log=lambda s: None) == 0
    assert calls == ['f293', 'f293', 'f293_m7off', 'f140'] and seen == [None, rec.D4_SET, None, None]
    meta = rec.tape_meta(tmp_path / 'f293' / 'tape')
    assert meta == {'set': rec.D4_SET, 'd4': rec.D4_REASON}
    kept = (tmp_path / ('f293' + rec.AS_RECORDED_SUFFIX)).resolve()
    first = json.loads((kept / 'RESULT.json').read_text(encoding='utf-8'))
    assert (first['tape'], first['pipeline_run_dir'], first['cwd']) == (
        str(kept / 'tape'), str(kept / 'save' / 'ours' / 'run_x'), str(kept / 'gen'))
    assert first['argv'] == ['--save-dir', str(kept / 'save'), '--vis', '0'] and first['set'] is None
    assert rec.tape_meta(kept / 'tape') == {}
    stored = json.loads((tmp_path / 'f293' / 'STORED.json').read_text(encoding='utf-8'))
    assert stored['d4']['set'] == rec.D4_SET and stored['d4']['as_recorded'] == {
        'folder': kept.name, 'status': 'ended', 'm7_suspension_rows': 2}
    assert rec.D4_REASON in stored['d4']['rule'] and kept.name in stored['d4']['rule']
    assert json.loads((kept / 'STORED.json').read_text(encoding='utf-8'))['d4']['set'] is None
    assert list(json.loads((tmp_path / 'STORE.json').read_text(encoding='utf-8'))) == ['f293', 'f293_m7off', 'f140']
    assert not (tmp_path / ('f140' + rec.AS_RECORDED_SUFFIX)).exists()
    assert rec.D4_SET == dict([rec.parse_set(f'{k}={v}') for k, v in rec.D4_SET.items()])
    calls = _fake_recorder(monkeypatch, {'f293': _ROWS}, {'f293': 'timeout'})
    assert rec.record_set(tmp_path / 't', ['f293'], log=lambda s: None) == 1 and calls == ['f293']
    d4 = json.loads((tmp_path / 't' / 'f293' / 'STORED.json').read_text(encoding='utf-8'))['d4']
    assert d4['set'] is None and 'as_recorded' not in d4 and d4['rule'].endswith(
        'not recorded again, the recording ended as timeout')


def test_move_run_replaces_the_target_and_moves_only_the_paths_inside_the_folder(tmp_path):
    """move_run, by which D4 keeps the first recording: an older folder of
    the target's name is replaced; the folder itself and a path inside it
    follow the move; a path that only starts with the folder's name, a
    path elsewhere and a null stay; a run without RESULT.json moves as it
    is.  Catches the older folder left in the way and a bare prefix moved."""
    src, to = (tmp_path / 'f293').resolve(), (tmp_path / 'f293.as_recorded').resolve()
    (to / 'old').mkdir(parents=True)
    (to / 'old' / 'x.txt').write_text('older', encoding='utf-8')
    (src / 'tape').mkdir(parents=True)
    rec.write_json(src / 'RESULT.json', {'status': 'ended', 'tape': str(src / 'tape'), 'cwd': str(src),
                                         'pipeline_run_dir': None,
                                         'argv': [str(src) + 'x', '--save-dir', str(src / 'save'), '/elsewhere']})
    assert rec.move_run(src, to) == to and not src.exists() and not (to / 'old').exists()
    assert json.loads((to / 'RESULT.json').read_text(encoding='utf-8')) == {
        'status': 'ended', 'tape': str(to / 'tape'), 'cwd': str(to), 'pipeline_run_dir': None,
        'argv': [str(src) + 'x', '--save-dir', str(to / 'save'), '/elsewhere']}
    bare, kept = tmp_path / 'r1', (tmp_path / 'r1.as_recorded').resolve()
    (bare / 'tape').mkdir(parents=True)
    assert rec.move_run(bare, kept) == kept and (kept / 'tape').is_dir() and not bare.exists()
    assert not (kept / 'RESULT.json').exists()
