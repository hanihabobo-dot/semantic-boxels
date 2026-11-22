"""BF#68 (run tampura -Draw boxels): the bridge's boxel overlay is debug lines
and labels.  On the executing client, after phase 'setup', it passes every
runtime gate, and the phantom overlay it replaces does not: a createMultiBody
there is a G14 violation, which is why audit R4.2 turned the overlay off and
why the bridge never takes the phantoms.  The option is off by default and the
driver refuses a kind it does not know."""
import ast
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


def test_drawing_is_off_by_default_and_the_kinds_are_boxels_and_cameras():
    cfg = policy.EpisodeConfig(seed=0, scene_file='f.json', log_dir='x')
    assert cfg.draw == frozenset() and cfg.camera_dir == ''
    assert policy.DRAW_KINDS == ('boxels', 'cameras')


def test_the_driver_refuses_a_kind_it_does_not_know(tmp_path):
    driver = os.path.join(REPO, 'tampura_bridge', 'run_bridge_on_finddice.py')
    # HOME in tmp_path: the console writes its start-up debug file under
    # ~/.cache/semantic_boxels, which no tool sweeps; a test run leaves none there.
    proc = subprocess.run(
        [sys.executable, driver, '--global-seed', '0', '--draw', 'boxles'],
        capture_output=True, text=True, timeout=300,
        env=dict(os.environ, HOME=str(tmp_path)))
    assert proc.returncode == 2
    # The driver's console takes fds 1 and 2 over and shows argparse's text on
    # its terminal stream (stdout here), so both streams are read.  The usage
    # block names --draw but not the bad kind: only the refusal says "not boxles".
    out = proc.stdout + proc.stderr
    assert '--draw takes boxels' in out and 'not boxles' in out, out


# What a unit test cannot run is execute_fn (a whole TAMPURA world) or a GUI
# session, and the keywords at three call sites decide the whole feature: so
# they are pinned as written.  A change of any of them fails here, not only in
# the first GUI run.
def _tree(*parts):
    with open(os.path.join(REPO, *parts), encoding='utf-8') as f:
        return ast.parse(f.read())


def _calls(tree, name):
    """Every call in tree to `name` or `x.name`."""
    out = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if (f.attr if isinstance(f, ast.Attribute) else getattr(f, 'id', None)) == name:
                out.append(n)
    return out


def _kw(call, name):
    return {k.arg: ast.unparse(k.value) for k in call.keywords}.get(name)


def _main_and_its_stages(tree):
    """main() of test_full_pipeline.py (its tree is given) and the functions
    cut out of it: those whose first parameter is the episode state st,
    defined in that file or in a file of the checkout's root that it imports
    them from by name."""
    defs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    for imp in tree.body:
        if isinstance(imp, ast.ImportFrom) and os.path.exists(os.path.join(REPO, f'{imp.module}.py')):
            names = {a.name for a in imp.names}
            defs += [n for n in _tree(f'{imp.module}.py').body
                     if isinstance(n, ast.FunctionDef) and n.name in names]
    return [n for n in defs if n.name == 'main' or [a.arg for a in n.args.args][:1] == ['st']]


def test_the_bridge_asks_main_for_lines_only_and_only_on_request():
    mains = [c for c in _calls(_tree('tampura_bridge', 'policy.py'), 'main')
             if ast.unparse(c.func) == 'test_full_pipeline.main']
    assert len(mains) == 1
    assert _kw(mains[0], 'draw_boxel_overlays') == "'boxels' in cfg.draw"
    assert _kw(mains[0], 'overlay_bodies') == 'False'


def test_main_builds_a_lines_only_visualizer_from_overlay_bodies():
    tree = _tree('test_full_pipeline.py')
    (main,) = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    pos = main.args.args
    defaults = dict(zip([a.arg for a in pos[len(pos) - len(main.args.defaults):]],
                        map(ast.unparse, main.args.defaults)))
    # `run boxels` and every other caller keep the phantom overlay
    assert defaults['overlay_bodies'] == 'True'
    # The visualizer is built in build_registry, cut out of main(): main()
    # hands it its own overlay_bodies, and it is the one BoxelVisualizer call
    # of main() and of the functions cut out of it (first parameter st).
    cut = _main_and_its_stages(tree)
    (build,) = [n for n in cut if n.name == 'build_registry']
    assert [a.arg for a in build.args.args] == ['st', 'env', 'overlay_bodies']
    assert [ast.unparse(c) for c in _calls(main, 'build_registry')] == [
        'build_registry(st, env, overlay_bodies)']
    assert [(fn.name, _kw(c, 'phantoms')) for fn in cut
            for c in _calls(fn, 'BoxelVisualizer')] == [('build_registry', 'overlay_bodies')]
    assert not [c for c in _calls(tree, 'main') if _kw(c, 'overlay_bodies') is not None]


def test_the_driver_passes_the_kinds_on_and_draws_nothing_by_default():
    tree = _tree('tampura_bridge', 'run_bridge_on_finddice.py')
    (cfg,) = _calls(tree, 'EpisodeConfig')
    assert _kw(cfg, 'draw') == 'frozenset(draw)'
    flag = [c for c in _calls(tree, 'add_argument') if c.args
            and ast.unparse(c.args[0]) == "'--draw'"]
    assert len(flag) == 1 and _kw(flag[0], 'default') == "''"
