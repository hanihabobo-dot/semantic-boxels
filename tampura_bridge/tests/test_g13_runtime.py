"""#P4 GF1: G13's runtime half (tampura_bridge/g13_runtime.py) and the
ordered T-driver check (tools/bridge_gates.py tdriver_diff).

Each check is shown to pass on the real set-up and to fail on the
violation it exists for.  Run in the arm-O venv (D12) with their trees on
PYTHONPATH; nothing here builds a scene or plans.
"""
import importlib.util
import os
import shutil
import sys
import types

import pytest

from tampura_bridge import g13_runtime
from tampura_bridge import policy as bridge_policy

REPO = g13_runtime.REPO
CONFIG = {'print_options': ''}


def _gates():
    spec = importlib.util.spec_from_file_location(
        '_bridge_gates_t', os.path.join(REPO, 'tools', 'bridge_gates.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _execute_fn(*args, **kwargs):
    return None


def _arm_o():
    """A real BoxelBridgePolicy and a stand-in env holding their problem spec's one field."""
    env = types.SimpleNamespace(problem_spec=types.SimpleNamespace(action_schemas=[]))
    bridge_policy.register_schema(env, _execute_fn)
    policy = bridge_policy.bridge_policy_class()(CONFIG, env.problem_spec)
    return env, policy


def _check_o(env, policy):
    return g13_runtime.check_arm_o(env, policy, object(), bridge_policy.SCHEMA_NAME, _execute_fn)


# --- arm O ---------------------------------------------------------------------

def test_arm_o_passes_on_the_real_setup():
    env, policy = _arm_o()
    rec = _check_o(env, policy)
    assert rec['ok'], rec['failures']
    assert rec['their_modules']['in_checkout'] > 0
    assert rec['policy_methods'] == ['__init__', 'get_action']


def test_arm_o_env_step_attribute_fails():
    env, policy = _arm_o()
    env.step = lambda *a: None
    assert "instance attribute 'step'" in ' '.join(_check_o(env, policy)['failures'])


def test_arm_o_second_schema_of_ours_fails():
    from tampura.structs import ActionSchema
    env, policy = _arm_o()
    env.problem_spec.action_schemas.append(ActionSchema(
        name='helper', inputs=[], input_types=[], preconditions=[], effects=[],
        execute_fn=_execute_fn))
    assert not _check_o(env, policy)['ok']


def test_arm_o_rollout_override_fails():
    env, _ = _arm_o()
    base = bridge_policy.bridge_policy_class()

    class Sneaky(base):
        def rollout(self, env, b, store):
            return None

    rec = _check_o(env, Sneaky(CONFIG, env.problem_spec))
    assert any('rollout is not Policy.rollout' in f for f in rec['failures'])
    assert any('not only __init__ and get_action' in f for f in rec['failures'])


def test_monkeypatch_of_their_class_fails(monkeypatch):
    from tampura.policies.policy import Policy
    monkeypatch.setattr(Policy, 'helper', _execute_fn, raising=False)
    env, policy = _arm_o()
    assert any('monkeypatch' in f for f in _check_o(env, policy)['failures'])


def test_registration_of_ours_in_their_registry_fails(monkeypatch):
    from tampura.config import config as tconfig
    monkeypatch.setitem(tconfig.env_registry.items, 'ours_env', type('OursEnv', (), {}))
    env, policy = _arm_o()
    assert any('registrations' in f for f in _check_o(env, policy)['failures'])


def test_sync_override_fails(monkeypatch):
    from tampura_bridge.env_adapter import TampuraWorldEnv
    monkeypatch.setattr(TampuraWorldEnv, 'sync_to_plan_client', _execute_fn, raising=False)
    env, policy = _arm_o()
    assert any('sync_to_plan_client' in f for f in _check_o(env, policy)['failures'])


# --- their modules: in the checkout or a byte-identical copy -------------------

def _fake_copy(tmp_path, monkeypatch, tamper):
    """tampura loaded from a copy outside their checkout (arm T's site-packages case)."""
    import tampura
    import tampura.policies.policy as real
    tw = g13_runtime._tw()
    copy = tmp_path / 'site-packages' / 'tampura'
    (copy / 'policies').mkdir(parents=True)
    shutil.copy(tampura.__file__, copy / '__init__.py')
    shutil.copy(real.__file__, copy / 'policies' / 'policy.py')
    if tamper:
        with open(copy / 'policies' / 'policy.py', 'a') as f:
            f.write('\n# changed\n')
    fake_pkg = types.ModuleType('tampura')
    fake_pkg.__file__ = str(copy / '__init__.py')
    fake_mod = types.ModuleType('tampura.policies.policy')
    fake_mod.__file__ = str(copy / 'policies' / 'policy.py')
    monkeypatch.setitem(sys.modules, 'tampura', fake_pkg)
    monkeypatch.setitem(sys.modules, 'tampura.policies.policy', fake_mod)
    return g13_runtime._module_files(tw)


def test_identical_copy_of_their_module_passes(tmp_path, monkeypatch):
    counts, failures = _fake_copy(tmp_path, monkeypatch, tamper=False)
    assert not failures and counts['identical_copy'] >= 2


def test_changed_copy_of_their_module_fails(tmp_path, monkeypatch):
    _, failures = _fake_copy(tmp_path, monkeypatch, tamper=True)
    assert any('tampura.policies.policy' in f for f in failures)


# --- arm T -------------------------------------------------------------------

def _timed():
    from tampura_bridge.timed_policy import PLANNER_NAME, TampuraPolicyTimed
    # their TampuraPolicy.__init__ is not needed for the class-level checks
    return object.__new__(TampuraPolicyTimed), PLANNER_NAME, TampuraPolicyTimed


def test_arm_t_passes_on_the_real_setup():
    policy, name, cls = _timed()
    rec = g13_runtime.check_arm_t(policy, types.SimpleNamespace(action_schemas=[]), name, cls)
    assert rec['ok'], rec['failures']


def test_arm_t_records_the_reviewed_wrapper_and_its_three_methods():
    # DV-1's amendment: rollout is the one reviewed wrapper, nothing else is added
    policy, name, cls = _timed()
    rec = g13_runtime.check_arm_t(policy, types.SimpleNamespace(action_schemas=[]), name, cls)
    assert rec['policy_methods'] == ['__init__', 'get_action', 'rollout']
    assert 'reviewed wrapper' in rec['rollout']


def test_arm_t_another_rollout_fails():
    from tampura_bridge.timed_policy import PLANNER_NAME, TampuraPolicyTimed

    class Sneaky(TampuraPolicyTimed):
        def rollout(self, env, b, store):
            return None

    rec = g13_runtime.check_arm_t(object.__new__(Sneaky), types.SimpleNamespace(action_schemas=[]),
                                  PLANNER_NAME, TampuraPolicyTimed)
    assert any('is not the reviewed wrapper' in f for f in rec['failures'])


def test_arm_t_an_extra_method_fails():
    from tampura_bridge.timed_policy import PLANNER_NAME, TampuraPolicyTimed

    class Extra(TampuraPolicyTimed):
        def helper(self):
            return None

    rec = g13_runtime.check_arm_t(object.__new__(Extra), types.SimpleNamespace(action_schemas=[]),
                                  PLANNER_NAME, TampuraPolicyTimed)
    assert any("not only __init__, get_action and rollout" in f for f in rec['failures'])


def test_arm_t_extra_planner_of_ours_fails(monkeypatch):
    from tampura.config import config as tconfig
    policy, name, cls = _timed()
    monkeypatch.setitem(tconfig.planner_registry.items, 'helper', type('Helper', (), {}))
    rec = g13_runtime.check_arm_t(policy, types.SimpleNamespace(action_schemas=[]), name, cls)
    assert any('registrations' in f for f in rec['failures'])


def test_write_and_enforce_stops_on_failure(tmp_path):
    g13_runtime.write_and_enforce({'ok': True, 'failures': []}, str(tmp_path))
    assert (tmp_path / 'g13_runtime.json').exists()
    with pytest.raises(SystemExit):
        g13_runtime.write_and_enforce({'ok': False, 'failures': ['x']}, str(tmp_path))


# --- the ordered T-driver check -----------------------------------------------

def _driver_texts():
    tw = g13_runtime._tw()
    with open(os.path.join(REPO, 'tools', 'run_tampura_timed.py')) as f:
        ours = f.read()
    with open(os.path.join(tw, 'tampura_environments', 'run_planner.py')) as f:
        theirs = f.read()
    return ours, theirs


def test_tdriver_real_files_pass():
    ok, msg = _gates().tdriver_diff(*_driver_texts())
    assert ok, msg


def test_tdriver_reordered_lines_fail():
    ours, theirs = _driver_texts()
    a, b = 'random.seed(config["global_seed"])', 'np.random.seed(config["global_seed"])'
    swapped = ours.replace(a, '\0').replace(b, a).replace('\0', b)
    assert swapped != ours
    assert not _gates().tdriver_diff(swapped, theirs)[0]


def test_tdriver_extra_line_fails():
    ours, theirs = _driver_texts()
    extra = ours.replace('    parser = create_parser()\n',
                         '    parser = create_parser()\n    config_patch = 1\n')
    assert not _gates().tdriver_diff(extra, theirs)[0]


def test_tdriver_import_outside_main_fails():
    ours, theirs = _driver_texts()
    line = '    import tampura_bridge.timed_policy  # noqa: F401  registers tampura_policy_timed\n'
    moved = ours.replace(line, '').replace('def create_parser():\n', 'def create_parser():\n' + line)
    assert not _gates().tdriver_diff(moved, theirs)[0]
