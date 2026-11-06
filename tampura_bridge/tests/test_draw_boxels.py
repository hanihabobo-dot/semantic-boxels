"""BF#68 (run tampura -Draw boxels): the bridge's boxel overlay is debug lines
and labels.  On the executing client, after phase 'setup', it passes every
runtime gate, and the phantom overlay it replaces does not: a createMultiBody
there is a G14 violation, which is why audit R4.2 turned the overlay off and
why the bridge never takes the phantoms.  The option is off by default and the
driver refuses a kind it does not know."""
import os
import subprocess
import sys
import types

import numpy as np
import pybullet as p
import pybullet_data
import pytest

import run_logger
import visualization
from boxel_data import BoxelData, BoxelRegistry, BoxelType
from tampura_bridge import gate_hooks as gh
from tampura_bridge import policy
from visualization import BoxelVisualizer

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MISSION = ('and', ('holding', 'die'), ('at_config', 'q_home'))


@pytest.fixture
def w(tmp_path):
    # BoxelVisualizer calls the default client, which is client 0 in the
    # pipeline (the bridge's executing world adopts it, BF#4 (d)).
    c0 = p.connect(p.DIRECT)
    if c0 != 0:
        p.disconnect(c0)
        pytest.skip('client 0 is held by another test: the visualizer draws on it')
    c1 = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=c0)
    robot = p.loadURDF('franka_panda/panda.urdf', [0, 0, 0], useFixedBase=True,
                       physicsClientId=c0)
    known = p.loadURDF('cube_small.urdf', [0.5, 0.0, 0.05], physicsClientId=c0)
    run_logger.ledger_open(tmp_path)
    gh.install(gh.GateConfig(executing_client=c0, robot_id=robot,
                             task_body_ids=frozenset({known}),
                             has_object_boxel=lambda b: b == known,
                             mission_goal=MISSION, target_symbol='die'))
    gh.set_phase('main')
    yield types.SimpleNamespace(c0=c0, robot=robot, known=known)
    run_logger.dispatch_end('ok')
    gh.uninstall()
    run_logger.ledger_close()
    p.disconnect(c1)
    p.disconnect(c0)


def _registry():
    reg = BoxelRegistry()
    reg.add_boxel(BoxelData(
        id='die', boxel_type=BoxelType.OBJECT, object_name='die',
        min_corner=np.array([0.45, -0.05, 0.0]),
        max_corner=np.array([0.55, 0.05, 0.1])))
    reg.add_boxel(BoxelData(
        id='shadow_of_die', boxel_type=BoxelType.SHADOW, created_by_object='die',
        min_corner=np.array([0.45, 0.05, 0.0]),
        max_corner=np.array([0.55, 0.20, 0.10])))
    return reg


def test_the_lines_only_overlay_trips_no_gate_on_the_executing_client(w):
    homes = dict(visualization._PHANTOM_HOME)
    n_bodies = p.getNumBodies(physicsClientId=w.c0)
    viz = BoxelVisualizer(phantoms=False)
    reg = _registry()
    viz.draw_registry(reg, duration=0, label_size=1.0)
    viz.remove_boxel_viz('shadow_of_die')
    viz.draw_boxel_data(reg.get_boxel('die'))
    # the observation chokepoint's conceal and restore around a render
    visualization.conceal_overlay_for_observation()
    visualization.restore_overlay_after_observation()
    viz.clear_all()
    assert gh.counts() == {}
    assert p.getNumBodies(physicsClientId=w.c0) == n_bodies
    assert visualization._PHANTOM_HOME == homes


def test_the_phantom_overlay_trips_g14_on_the_executing_client(w):
    viz = BoxelVisualizer()
    with pytest.raises(gh.GateViolation):
        viz.draw_registry(_registry(), duration=0, label_size=1.0)
    assert gh.counts().get('G14', 0) == 1


def test_drawing_is_off_by_default_and_boxels_is_the_one_kind():
    cfg = policy.EpisodeConfig(seed=0, scene_file='f.json', log_dir='x')
    assert cfg.draw == frozenset()
    assert policy.DRAW_KINDS == ('boxels',)


def test_the_driver_refuses_a_kind_it_does_not_know():
    driver = os.path.join(REPO, 'tampura_bridge', 'run_bridge_on_finddice.py')
    proc = subprocess.run(
        [sys.executable, driver, '--global-seed', '0', '--draw', 'boxles'],
        capture_output=True, text=True, timeout=300)
    assert proc.returncode == 2
    assert 'boxels' in proc.stderr and 'boxles' in proc.stderr
