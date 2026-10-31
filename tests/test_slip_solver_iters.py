"""BF#59 solver_iters: 200 contact-solver iterations per step on the
executing world (tampura_bridge/policy.py d9_setup, boxel_env.py's own
world, re-applied after BoxelTestEnv.reset()), behind
slip_fixes.on('solver_iters'), default off.  Every value is read back with
getPhysicsEngineParameters on a fresh DIRECT client."""
import inspect
from types import SimpleNamespace

import pybullet as p
import pytest

import boxel_env               # registers 'solver_iters' at import
import robot_utils
import slip_fixes
from boxel_env import BoxelTestEnv


@pytest.fixture
def registry():
    """The registry as the imports left it (the name registered), every
    switch off for the test; the module's state restored after."""
    known, enabled = dict(slip_fixes.KNOWN), slip_fixes.ENABLED
    slip_fixes.ENABLED = frozenset()
    yield slip_fixes
    slip_fixes.KNOWN.clear()
    slip_fixes.KNOWN.update(known)
    slip_fixes.ENABLED = enabled


def _iters(client):
    return p.getPhysicsEngineParameters(physicsClientId=client)['numSolverIterations']


def _default_iters():
    c = p.connect(p.DIRECT)
    try:
        return _iters(c)
    finally:
        p.disconnect(physicsClientId=c)


def _d9_on_fresh_client():
    """d9_setup on a bare DIRECT client: a stub world with no task bodies
    and a model with no finger joints, so only the world settings run."""
    from tampura_bridge import policy as bridge_policy
    c = p.connect(p.DIRECT)
    world = SimpleNamespace(client=SimpleNamespace(_client=c), objects=[],
                            categories=[], robot=SimpleNamespace(body=-1))
    bridge_policy.d9_setup(world, SimpleNamespace(finger_joints=[]))
    return c


def test_registered_and_off_by_default(registry):
    assert 'solver_iters' in registry.KNOWN
    assert 'solver_iters' in boxel_env.slip_fixes.KNOWN
    registry.configure('')
    assert not registry.on('solver_iters')
    assert robot_utils.SOLVER_ITERATIONS == 200
    assert _default_iters() == 50          # PyBullet's default, which base keeps


def test_off_d9_setup_keeps_the_default(registry):
    registry.configure('')
    c = _d9_on_fresh_client()
    try:
        assert _iters(c) == _default_iters()
    finally:
        p.disconnect(physicsClientId=c)


def test_on_d9_setup_sets_200(registry, capsys):
    registry.configure('solver_iters')
    c = _d9_on_fresh_client()
    try:
        assert _iters(c) == robot_utils.SOLVER_ITERATIONS == 200
    finally:
        p.disconnect(physicsClientId=c)
    assert 'solver_iters: numSolverIterations 200 on the executing world' in capsys.readouterr().out


def test_off_our_world_keeps_the_default(registry):
    registry.configure('')
    env = BoxelTestEnv(gui=False)
    try:
        assert _iters(env.client_id) == _default_iters()
        env.reset()
        assert _iters(env.client_id) == _default_iters()
    finally:
        env.close()


def test_on_our_world_sets_200_and_keeps_it_after_reset(registry, capsys):
    registry.configure('solver_iters')
    env = BoxelTestEnv(gui=False)
    try:
        assert _iters(env.client_id) == 200
        # The plan twin never steps; it keeps the default.
        assert _iters(env.plan_client_id) == _default_iters()
        env.reset()                         # resetSimulation sets 50 again
        assert _iters(env.client_id) == 200
        assert _iters(env.plan_client_id) == _default_iters()
    finally:
        env.close()
    out = capsys.readouterr().out
    assert 'solver_iters: numSolverIterations 200 on our world (client' in out
    assert 'solver_iters: numSolverIterations 200 on our world after reset' in out


def test_the_bridge_configures_the_switch_before_d9_setup():
    """main() configures the slip fixes only after D9's set-up has run, so
    execute_fn configures them from the same flag first."""
    from tampura_bridge import policy as bridge_policy
    src = inspect.getsource(bridge_policy.make_execute_fn)
    conf = src.index("slip_fixes.configure(cfg.switches.get('slip_fixes', ''))")
    assert conf < src.index('d9_setup(world, model)')
