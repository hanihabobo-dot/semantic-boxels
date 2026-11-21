"""Phase 0 pins, group "low" (the low-cost and AST pins of the readable
migration): a fresh generation by tools/readable/pin_outputs.py compared,
pin by pin and file by file, with a stored folder named by the environment
variable READABLE_GOLDEN.

No golden output is stored before tag refactor-checkpoint-2 (R's condition
on the Phase 0 plan), so without READABLE_GOLDEN the pin tests skip.  Make
the folder on the checkpoint with

    python tools/readable/pin_outputs.py --group low --out <folder>

and run, in WSL under the pipeline lock (R's rule 5):

    READABLE_GOLDEN=<folder> PYTHONHASHSEED=0 flock /root/sb_pipeline.lock \
        /root/armO-venvA/bin/python -m pytest -q tests/readable/test_pins_low.py

Files named INFO_* (line numbers and other information) are not compared.
The two small tests at the end check the comparator itself and need no
golden folder.

A relative READABLE_GOLDEN is taken against pytest's working directory, and
one that names no existing folder is refused (SPEC D11, gate 7); the tests
after the comparator's show the same for the variables a pin child reads and
for the READABLE_GOLDEN of every pin test file, and need no golden folder
either.
"""
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePath

import pytest

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO / 'tools' / 'readable'))
import pin_outputs as po  # noqa: E402

GOLDEN = po.readable_path(po.GOLDEN_VAR)   # absolute, or None when unset (SPEC D11)
PINS = list(po.GROUPS['low'])
needs_golden = pytest.mark.skipif(
    not GOLDEN,
    reason='READABLE_GOLDEN is not set: no stored golden output exists before tag '
           'refactor-checkpoint-2 (R\'s condition); set it to a folder written by '
           '"pin_outputs.py --group low --out <folder>" on that tag')


@pytest.fixture(scope='module')
def fresh(tmp_path_factory):
    """One generation of the whole group (each pin in its own child process)."""
    out = tmp_path_factory.mktemp('pins_low')
    po.run_group('low', out, log=lambda s: None)
    return out


def _first_difference(a, b):
    la = a.read_text(encoding='utf-8', errors='replace').splitlines()
    lb = b.read_text(encoding='utf-8', errors='replace').splitlines()
    diff = list(difflib.unified_diff(la, lb, 'golden', 'fresh', lineterm='', n=2))
    return '\n'.join(diff[:40])


@needs_golden
@pytest.mark.parametrize('pin_id', PINS)
def test_pin_equals_golden(fresh, pin_id):
    golden = Path(GOLDEN) / pin_id
    assert golden.is_dir(), f'the golden folder {GOLDEN} has no {pin_id}'
    manifest = json.loads((fresh / 'MANIFEST.json').read_text(encoding='utf-8'))
    status = manifest['pins'][pin_id]['status']
    err = fresh / pin_id / 'ERROR.txt'
    assert status == 'ok', f'{pin_id} did not run: {status}\n' + (
        err.read_text(encoding='utf-8') if err.exists() else '')
    want, have = po.pin_files(golden), po.pin_files(fresh / pin_id)
    assert sorted(want) == sorted(have), f'file sets differ: golden {sorted(want)}, fresh {sorted(have)}'
    for name in sorted(want):
        if want[name].read_bytes() != have[name].read_bytes():
            pytest.fail(f'{pin_id}/{name} differs from the golden copy:\n'
                        + _first_difference(want[name], have[name]))


def test_compare_reports_equal_and_differs(tmp_path):
    """The comparator: equal folders are equal, INFO_* files are ignored,
    a changed byte is a difference."""
    for side in ('a', 'b'):
        d = tmp_path / side / 'p00_demo'
        d.mkdir(parents=True)
        (d / 'out.json').write_text('[1, 2.5]\n')
        (d / 'INFO_lines.json').write_text(f'[{len(side)}{side!r}]\n')
        (tmp_path / side / 'MANIFEST.json').write_text(
            json.dumps({'pins': {'p00_demo': {'status': 'ok'}}}))
    assert po.compare(tmp_path / 'a', tmp_path / 'b', log=lambda s: None) == {'p00_demo': 'equal'}
    (tmp_path / 'b' / 'p00_demo' / 'out.json').write_text('[1, 2.50000001]\n')
    v = po.compare(tmp_path / 'a', tmp_path / 'b', log=lambda s: None)
    assert v['p00_demo'].startswith('differs: out.json')


def test_plain_refuses_a_set_and_keeps_floats_exact():
    """R's rule 4 (a set must be sorted by the pin) and rule 3 (floats as
    json.dumps writes them, inf included)."""
    with pytest.raises(TypeError):
        po.plain({'a': {1, 2}})
    assert po.dumps(po.plain([0.1 + 0.2, float('inf')])) == '[\n 0.30000000000000004,\n Infinity\n]\n'


def test_relative_readable_paths_are_made_absolute_in_the_parent(tmp_path, monkeypatch):
    """SPEC D11 (C10): a relative READABLE_TAPES or READABLE_RENDER_FIXTURE is made absolute
    against the parent's working directory before a child starts, so the child, whose working
    directory is its work folder, reads the folder the parent meant.  Catches a relative value
    passed to the child as typed; READABLE_GOLDEN goes through the same function."""
    (tmp_path / 'tapes').mkdir()
    (tmp_path / 'fixture').mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(po.TAPES_VAR, 'tapes')
    monkeypatch.setenv(po.RENDER_FIXTURE_VAR, 'fixture/../fixture')
    want = {po.TAPES_VAR: str((tmp_path / 'tapes').resolve()),
            po.RENDER_FIXTURE_VAR: str((tmp_path / 'fixture').resolve())}
    assert po.child_paths() == want
    env = po.child_env(work)
    for var, value in want.items():
        assert env[var] == value and Path(env[var]).is_absolute()
        assert not (work / os.environ[var]).exists()    # the value as typed, read from the child's folder
    assert po.readable_path(po.GOLDEN_VAR, {po.GOLDEN_VAR: 'tapes'}) == (tmp_path / 'tapes').resolve()
    assert po.readable_path(po.GOLDEN_VAR, {}) is None
    assert po.readable_path(po.GOLDEN_VAR, {po.GOLDEN_VAR: ''}) is None


def test_missing_readable_path_is_refused_before_any_child(tmp_path, monkeypatch):
    """SPEC D11: a READABLE variable that names no existing path stops run_group with a message
    before any child starts and before the output folder is made.  Catches a missing path
    passed on to the children (each failing on its own, or reading the default instead)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(po.RENDER_FIXTURE_VAR, 'no_such_fixture')
    out = tmp_path / 'out'
    with pytest.raises(po.ReadablePathError, match="READABLE_RENDER_FIXTURE='no_such_fixture' names "):
        po.run_group('low', out, only=['p24_goals'], log=lambda s: None)
    assert not out.exists()
    with pytest.raises(po.ReadablePathError, match='READABLE_GOLDEN'):
        po.readable_path(po.GOLDEN_VAR, {po.GOLDEN_VAR: 'no_such_golden'})


# A fresh interpreter imports one test file by its path and prints what its GOLDEN became.
_GOLDEN_PROBE = r'''
import importlib.util, sys
spec = importlib.util.spec_from_file_location('golden_probe', sys.argv[1])
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
except Exception as ex:
    print('@@ERROR', type(ex).__name__, ex)
else:
    print('@@GOLDEN', mod.GOLDEN)
'''


def _golden_as_imported(test_file, value, cwd):
    """The '@@' line a fresh interpreter prints after importing test_file with READABLE_GOLDEN=value
    (the other READABLE variables unset) and the working directory cwd."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('READABLE_')}
    env.update({po.GOLDEN_VAR: value, 'PYTHONDONTWRITEBYTECODE': '1'})
    p = subprocess.run([sys.executable, '-c', _GOLDEN_PROBE, str(test_file)], cwd=str(cwd), env=env,
                       capture_output=True, text=True, timeout=180)
    lines = [ln for ln in p.stdout.splitlines() if ln.startswith('@@')]
    assert p.returncode == 0 and len(lines) == 1, (test_file.name, p.returncode, p.stdout[-400:], p.stderr[-800:])
    return lines[0]


def test_pin_test_files_resolve_golden_as_the_tool_does(tmp_path):
    """SPEC D11: every test file here that names READABLE_GOLDEN resolves it with po.readable_path:
    imported in a fresh interpreter whose working directory is tmp_path, it makes a relative value
    absolute against that folder and refuses one that names no folder with the tool's message.
    The files are found by the variable's name in their text.  Catches a file that reads the
    variable as typed (a relative value kept relative, a missing folder passed on to the golden
    tests)."""
    files = [f for f in sorted(HERE.glob('test_*.py')) if po.GOLDEN_VAR in f.read_text(encoding='utf-8')]
    assert Path(__file__).name in [f.name for f in files], files
    (tmp_path / 'golden').mkdir()
    want = f"@@GOLDEN {(tmp_path / 'golden').resolve()}"
    for f in files:
        got = _golden_as_imported(f, 'golden', tmp_path)
        assert got == want, (f.name, got)
        refused = _golden_as_imported(f, 'no_such_golden', tmp_path)
        assert refused.startswith(f"@@ERROR ReadablePathError {po.GOLDEN_VAR}='no_such_golden' names "), \
            (f.name, refused)


# A fresh interpreter imports pin_outputs from the given folder and prints its module-level paths.
_PATHS_PROBE = r'''
import json, sys
from pathlib import PurePath
sys.path.insert(0, sys.argv[1])
import pin_outputs as po
print('@@PATHS ' + json.dumps({k: str(v) for k, v in sorted(vars(po).items()) if isinstance(v, PurePath)}))
'''


def test_default_paths_are_built_from_repo(tmp_path):
    """SPEC D11 (C10): the default folders are built from the file's place (REPO), never from
    the working directory: absolute and under REPO here, and every module-level path of
    pin_outputs (REPO, HERE and the defaults) the same when it is imported in a fresh interpreter
    whose working directory is another folder.  Catches a default made relative, and one built
    from the working directory (which equals REPO while pytest runs in the checkout)."""
    assert po.REPO == Path(po.__file__).resolve().parents[2]
    assert po.RENDER_FIXTURE_DEFAULT.is_absolute() and po.REPO in po.RENDER_FIXTURE_DEFAULT.parents
    here = {k: str(v) for k, v in sorted(vars(po).items()) if isinstance(v, PurePath)}
    assert 'RENDER_FIXTURE_DEFAULT' in here, here
    env = {k: v for k, v in os.environ.items() if not k.startswith('READABLE_')}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    p = subprocess.run([sys.executable, '-c', _PATHS_PROBE, str(Path(po.__file__).parent)], cwd=str(tmp_path),
                       env=env, capture_output=True, text=True, timeout=180)
    line = next((ln for ln in p.stdout.splitlines() if ln.startswith('@@PATHS ')), None)
    assert line is not None, (p.returncode, p.stderr[-800:])
    there = json.loads(line[len('@@PATHS '):])
    assert there == here, {k: (here.get(k), there.get(k)) for k in sorted(set(here) | set(there))
                           if here.get(k) != there.get(k)}
