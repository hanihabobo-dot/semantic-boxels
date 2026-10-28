"""#P4 GF3: G2's wider AST scan, the 'gate hook' allowlist class and the
raising ObjectInfo.position of the bridge's object table (G16).

The leak test itself runs whole episodes: tampura_bridge/tests/leak_probe.py.
Run in the arm-O venv (D12) with their trees on PYTHONPATH.
"""
import ast
import importlib.util
import os

import numpy as np
import pytest

from tampura_bridge import gate_hooks

REPO = gate_hooks.REPO


def _gates():
    spec = importlib.util.spec_from_file_location(
        '_bridge_gates_gf3', os.path.join(REPO, 'tools', 'bridge_gates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _hits(src):
    bg = _gates()
    tree = ast.parse(src)
    sc = bg._Scanner(os.path.join(REPO, 'x.py'), src.splitlines(), tree)
    sc.visit(tree)
    return [(h['gate'], h['what']) for h in sc.hits]


def test_direct_call_is_one_hit():
    assert _hits("import pybullet as p\np.getAABB(1)\n") == [('G2', 'getAABB')]


def test_reference_through_a_module_alias():
    hits = _hits("import pybullet as pb\nget = pb.getAABB\nget(1)\n")
    assert hits == [('G2', 'pb.getAABB referenced, not called')]


def test_reference_on_pybullet_and_p():
    hits = _hits("f = pybullet.resetJointState\ng = p.getBasePositionAndOrientation\n")
    assert [g for g, _ in hits] == ['G1', 'G2']


def test_string_constant_names_a_function():
    assert _hits("name = 'resetJointState'\n") == [
        ('G1', "name 'resetJointState' as a string")]


def test_getattr_constant_counted_once():
    assert _hits("f = getattr(p, 'getAABB')\n") == [('G2', 'getattr getAABB')]


def test_docstring_and_other_strings_ignored():
    assert _hits('"""getAABB"""\nx = "getAABB of the cup"\n') == []


def test_gate_hook_class_only_in_gate_hooks(tmp_path):
    bg = _gates()
    good = ("G2 | tampura_bridge/gate_hooks.py | f | 1 | gate hook | its own "
            "check | x = 1")
    bad = "G2 | boxel_env.py | f | 1 | gate hook | not allowed here | x = 1"
    path = tmp_path / 'allow.txt'
    path.write_text(good + '\n' + bad + '\n')
    bg.ALLOWLIST = str(path)
    _, problems = bg._parse_allowlist()
    assert problems == ['allowlist line 2: gate hook outside '
                        'tampura_bridge/gate_hooks.py']


def test_static_gates_green_on_the_repo():
    bg = _gates()
    files, _, forbidden = bg.import_graph()
    hits = bg.scan(files)
    for gate in ('G1', 'G2'):
        unmatched, stale, problems = bg.check_allowlisted(hits, gate)
        assert (unmatched, stale, problems) == ([], [], [])
    assert forbidden == []


# ----- G16: the poseless object table -----------------------------------

def _entry(**kw):
    from tampura_bridge.env_adapter import PoselessObjectInfo
    return PoselessObjectInfo(object_id=3, name='cup', position=kw.get('position'),
                              orientation=None, size=np.zeros(3),
                              is_visible=False, is_occluder=True)


def test_position_none_is_allowed():
    gate_hooks.reset_counts()
    e = _entry()
    assert e.object_id == 3 and gate_hooks.counts() == {}


def test_reading_position_raises_and_counts():
    gate_hooks.reset_counts()
    e = _entry()
    with pytest.raises(gate_hooks.GateViolation):
        _ = e.position
    assert gate_hooks.counts() == {'G16': 1}


def test_setting_a_position_raises():
    gate_hooks.reset_counts()
    with pytest.raises(gate_hooks.GateViolation):
        _entry(position=np.zeros(3))
    assert gate_hooks.counts() == {'G16': 1}
