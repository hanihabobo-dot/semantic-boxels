"""Unit tests of the recorder's gate 7 parts (SPEC gate 7, WP-B): the F and R
entries and their twins (D2, D3), the first-plan record (P8, E3, D15's
S-b), the crash record under C-01 (D7), the planted change at_home_drop
(D8, in test_pin_replay.py), the coverage map (D12), the stub place_fail
(D16), the counts at storing (D3, D4), the masks (D6) and --set (D5).

None of these starts a simulation or an episode: the entries are built and
printed, the child runs small scripts written here, the stubs patch stand-in
modules, and the coverage map reads source files and trace files.
"""
import hashlib
import importlib.util
import json
import os
import shlex
import subprocess
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
