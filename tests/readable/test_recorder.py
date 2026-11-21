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


def _first_plan_run(tmp_path, first_plan):
    run = tmp_path / 'run'
    (run / 'rec').mkdir(parents=True)
    rec.write_json(run / 'RESULT.json', {'mode': 'first-plan', 'status': 'ended', 'rc': 0,
                                         'pipeline_run_dir': None})
    (run / 'stdout.txt').write_text('', encoding='utf-8')
    rec.write_json(run / 'rec' / 'first_plan.json', first_plan)
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
    n = rec.normalise(_first_plan_run(tmp_path, raw))['first_plan.json']
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
