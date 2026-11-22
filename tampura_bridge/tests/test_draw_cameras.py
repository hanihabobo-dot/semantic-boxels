"""BF#68 (run tampura -Draw cameras): the camera observer sits on the gates'
G20 hook, not under it.  A render the gate lets through is shown; one it
refuses still trips G20 and shows nothing; the observer reaches BulletClient
calls with their client id; the gates' uninstall alone drops it; and the
option is off by default."""
import ast
import contextlib
import json
import os
import subprocess
import sys
import types

import pybullet as p
import pybullet_data
import pytest

from console import run_logger
from tampura_bridge import camera_overlay
from tampura_bridge import gate_hooks as gh
from tampura_bridge import policy

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MISSION = ('and', ('holding', 'die'), ('at_config', 'q_home'))
W, H = 160, 120


@pytest.fixture
def w(tmp_path):
    c0 = p.connect(p.DIRECT)
    c1 = p.connect(p.DIRECT)
    for c in (c0, c1):
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=c)
        p.loadURDF('plane.urdf', physicsClientId=c)
    robot = p.loadURDF('franka_panda/panda.urdf', [0, 0, 0], useFixedBase=True,
                       physicsClientId=c0)
    known = p.loadURDF('cube_small.urdf', [0.5, 0.0, 0.05], physicsClientId=c0)
    view = p.computeViewMatrix([0.18, 0.05, 0.59], [0.5, 0, 0], [0, 0, 1])
    proj = p.computeProjectionMatrixFOV(49.13, W / H, 0.02, 5.0)
    run_logger.ledger_open(tmp_path)
    original = p.getCameraImage
    # wrist_robots as the episode declares it: the robot's own wrist camera
    # at its forward kinematics passes G20 beside the declared eye
    gh.install(gh.GateConfig(executing_client=c0, robot_id=robot,
                             task_body_ids=frozenset({known}),
                             has_object_boxel=lambda b: b == known,
                             camera_view=tuple(view), camera_proj=tuple(proj),
                             wrist_robots={c0: robot},
                             mission_goal=MISSION, target_symbol='die'))
    gh.set_phase('main')
    yield types.SimpleNamespace(c0=c0, c1=c1, view=view, proj=proj, robot=robot,
                                original=original, cams=tmp_path / 'cams')
    run_logger.dispatch_end('ok')
    gh.uninstall()
    # whatever a failed assert left installed: back to the function found
    p.getCameraImage = original
    run_logger.ledger_close()
    p.disconnect(c1)
    p.disconnect(c0)


def _render(w, view, client=None, **kw):
    return p.getCameraImage(W, H, viewMatrix=view, projectionMatrix=w.proj,
                            renderer=p.ER_TINY_RENDERER,
                            physicsClientId=w.c0 if client is None else client, **kw)


@contextlib.contextmanager
def _observed(w):
    obs = camera_overlay.CameraObserver(w.cams, w.c0, w.view, w.proj)
    obs.install()
    try:
        yield obs
    finally:
        obs.uninstall()


def test_a_render_the_gate_passes_is_shown_and_one_it_refuses_is_not(w):
    with _observed(w) as obs:
        _render(w, w.view)
        assert obs.counts == {'eye': 1} and gh.counts() == {}
        other = p.computeViewMatrix([0.0, 0.0, 2.0], [0.5, 0, 0], [0, 1, 0])
        with pytest.raises(gh.GateViolation):
            _render(w, other)
        assert gh.counts().get('G20', 0) == 1
        assert obs.counts == {'eye': 1}
        # the plan twin's test renders are the gate's business and not shown
        _render(w, w.view, client=w.c1)
        assert obs.counts == {'eye': 1}


def test_a_render_at_the_wrist_cameras_pose_passes_the_gate_and_is_shown_as_the_wrist(w):
    from acting import robot_utils
    wv, wp = robot_utils.wrist_camera_matrices(robot_utils.wrist_camera_pose(w.robot, w.c0))
    with _observed(w) as obs:
        p.getCameraImage(W, H, viewMatrix=wv, projectionMatrix=wp,
                         renderer=p.ER_TINY_RENDERER, physicsClientId=w.c0)
        _render(w, w.view)
        assert obs.counts == {'wrist': 1, 'eye': 1} and gh.counts() == {}
        assert json.loads((w.cams / 'wrist.json').read_text())['camera'] == 'wrist'
        assert json.loads((w.cams / 'eye.json').read_text())['camera'] == 'eye'


def test_the_observer_is_on_top_of_the_gate_and_comes_off_first(w):
    gate_hook = p.getCameraImage
    assert gate_hook is not w.original
    obs = camera_overlay.CameraObserver(w.cams, w.c0, w.view, w.proj)
    obs.install()
    assert p.getCameraImage is not gate_hook
    obs.uninstall()
    assert p.getCameraImage is gate_hook
    gh.uninstall()
    assert p.getCameraImage is w.original
    obs.uninstall()
    assert p.getCameraImage is w.original


def test_the_gates_uninstall_alone_drops_the_observer(w):
    obs = camera_overlay.CameraObserver(w.cams, w.c0, w.view, w.proj)
    obs.install()
    gh.uninstall()
    assert p.getCameraImage is w.original
    obs.uninstall()
    assert p.getCameraImage is w.original


def test_bullet_client_calls_reach_the_observer_with_their_client_id(w):
    from pybullet_utils import bullet_client
    bc = bullet_client.BulletClient(connection_mode=p.DIRECT)
    obs = camera_overlay.CameraObserver(w.cams, bc._client, w.view, w.proj)
    try:
        obs.install()
        bc.getCameraImage(W, H, viewMatrix=w.view, projectionMatrix=w.proj,
                          renderer=p.ER_TINY_RENDERER)
        assert obs.counts == {'eye': 1}
        _render(w, w.view)                   # client 0 is not the shown one
        assert obs.counts == {'eye': 1}
    finally:
        obs.uninstall()
        bc.disconnect()


def test_drawing_cameras_is_a_known_kind_and_off_by_default():
    cfg = policy.EpisodeConfig(seed=0, scene_file='f.json', log_dir='x')
    assert cfg.draw == frozenset() and cfg.camera_dir == ''
    assert 'cameras' in policy.DRAW_KINDS and 'boxels' in policy.DRAW_KINDS


def test_the_driver_takes_cameras_and_refuses_a_kind_it_does_not_know(tmp_path):
    driver = os.path.join(REPO, 'tampura_bridge', 'run_bridge_on_finddice.py')
    # HOME in tmp_path: the console writes its start-up debug file under
    # ~/.cache/semantic_boxels, which no tool sweeps; a test run leaves none there.
    proc = subprocess.run(
        [sys.executable, driver, '--global-seed', '0', '--draw', 'cameras,camras'],
        capture_output=True, text=True, timeout=300,
        env=dict(os.environ, HOME=str(tmp_path)))
    assert proc.returncode == 2
    # The driver's console shows argparse's text on its terminal stream
    # (stdout here), so both streams are read.
    out = proc.stdout + proc.stderr
    assert '--draw takes boxels, cameras' in out and 'not camras' in out, out


# What a unit test cannot run is execute_fn (a whole TAMPURA world), so the
# wiring that decides the order of the layers is pinned as written.
def _tree(*parts):
    with open(os.path.join(REPO, *parts), encoding='utf-8') as f:
        return ast.parse(f.read())


def _calls_in(node, text):
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call) and ast.unparse(n.func) == text]


def test_the_observer_goes_on_after_the_gates_and_comes_off_before_them():
    (make,) = [n for n in _tree('tampura_bridge', 'policy.py').body
               if isinstance(n, ast.FunctionDef) and n.name == 'make_execute_fn']
    gates_on = _calls_in(make, 'gate_hooks.install')
    obs_on = _calls_in(make, 'observer.install')
    obs_off = _calls_in(make, 'observer.uninstall')
    gates_off = _calls_in(make, 'gate_hooks.uninstall')
    assert len(gates_on) == len(obs_on) == len(obs_off) == len(gates_off) == 1
    assert gates_on[0].lineno < obs_on[0].lineno
    assert obs_off[0].lineno < gates_off[0].lineno
    # only on request, and built from the declared eye's own matrices
    (ask,) = [n for n in ast.walk(make) if isinstance(n, ast.If)
              and "'cameras' in cfg.draw" in ast.unparse(n.test)]
    assert ast.unparse(ask.test) == "'cameras' in cfg.draw and cfg.camera_dir"
    assert [c.lineno for c in _calls_in(ask, 'observer.install')] == [obs_on[0].lineno]
    (made,) = _calls_in(ask, 'camera_overlay.CameraObserver')
    assert [ast.unparse(a) for a in made.args] == ['cfg.camera_dir', 'c', 'view', 'proj']
    # with the gates' own tolerance for "the declared eye's matrices"
    assert {k.arg: ast.unparse(k.value) for k in made.keywords} == {
        'tol': 'gate_hooks.GateConfig.camera_tol'}
    # `observer = None` ahead of the try that holds the install, and the
    # uninstall in that try's finally (guarded), before the gates'
    (none,) = [n for n in ast.walk(make) if isinstance(n, ast.Assign)
               and ast.unparse(n) == 'observer = None']
    (episode,) = [n for n in ast.walk(make) if isinstance(n, ast.Try)
                  and any(_calls_in(f, 'gate_hooks.uninstall') for f in n.finalbody)]
    assert none.lineno < episode.lineno
    assert obs_on[0].lineno > episode.lineno and obs_on[0].lineno <= episode.body[-1].end_lineno
    final = [ast.unparse(s) for s in episode.finalbody]
    off = [i for i, s in enumerate(final) if 'observer.uninstall()' in s]
    gates = [i for i, s in enumerate(final) if s == 'gate_hooks.uninstall()']
    assert len(off) == len(gates) == 1 and off[0] < gates[0], final
    assert final[off[0]].startswith('if observer is not None:'), final


def test_the_driver_gives_the_observer_an_absolute_folder_only_for_cameras():
    (cfg,) = _calls_in(_tree('tampura_bridge', 'run_bridge_on_finddice.py'),
                       'bridge_policy.EpisodeConfig')
    value = {k.arg: ast.unparse(k.value) for k in cfg.keywords}['camera_dir']
    assert value == ("os.path.abspath(os.path.join(config['save_dir'], 'cameras')) "
                     "if 'cameras' in draw else ''")
