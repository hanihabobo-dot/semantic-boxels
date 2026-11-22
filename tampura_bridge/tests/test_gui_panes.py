"""Hani, 2026-11-21 (BF#27): our window's debug camera panes in TAMPURA's
window.  gui_panes.show and hide set flags of the window and nothing else;
the panes are the ones our own window keeps (RGB, depth and the segmentation
mask); the driver shows them once, in a --vis 1 run alone, after their
initialize and before the rollout, and puts them away before its own
overview renders, which are not the robot's view."""
import ast
import os

import numpy as np
import pybullet as p
import pybullet_data
from pybullet_utils import bullet_client

from tampura_bridge import gui_panes

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _tree(*parts):
    with open(os.path.join(REPO, *parts), encoding='utf-8') as f:
        return ast.parse(f.read())


def _calls_in(node, text):
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call) and ast.unparse(n.func) == text]


class _Window:
    """In place of their BulletClient: it keeps what show() asks of it, and
    anything but a window flag is an error (which show() reports in a line,
    so the tests also read what was printed)."""

    def __init__(self, fails=False):
        self.asked = []
        self.fails = fails

    def configureDebugVisualizer(self, flag, value):
        self.asked.append((flag, value))
        if self.fails:
            raise RuntimeError('Not connected to physics server.')

    def __getattr__(self, name):
        raise AssertionError(f"show() asked the client for {name}")


def test_show_switches_the_panel_on_with_the_rgb_depth_and_segmentation_panes(capsys):
    window = _Window()
    gui_panes.show(window)
    assert window.asked == [(p.COV_ENABLE_GUI, 1),
                            (p.COV_ENABLE_RGB_BUFFER_PREVIEW, 1),
                            (p.COV_ENABLE_DEPTH_BUFFER_PREVIEW, 1),
                            (p.COV_ENABLE_SEGMENTATION_MARK_PREVIEW, 1)]
    assert capsys.readouterr().out == ''


def test_hide_puts_the_panel_away_as_their_window_setup_leaves_it(capsys):
    window = _Window()
    gui_panes.hide(window)
    assert window.asked == [(p.COV_ENABLE_GUI, 0)]
    assert capsys.readouterr().out == ''


def test_a_window_that_takes_no_flag_is_reported_and_never_breaks_the_run(capsys):
    """Display only: with the window closed by hand, say, the driver's two
    calls print one line with the cause and return."""
    gui_panes.show(_Window(fails=True))
    gui_panes.hide(_Window(fails=True))
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith('gui_panes: the camera panes were not shown (RuntimeError')
    assert lines[1].startswith('gui_panes: the camera panes were not put away (RuntimeError')


def test_these_are_the_panes_our_own_window_keeps():
    """boxel_env.py opens our window with PyBullet's panel as it comes, all
    three panes on (Hani, 2026-11-21: "put segmentation pane back on all
    over"); were a pane switched off there, their window would no longer
    show what ours shows."""
    flags = {(ast.unparse(c.args[0]), ast.unparse(c.args[1]))
             for c in _calls_in(_tree('boxel_env.py'), 'p.configureDebugVisualizer')}
    assert not [f for f, _ in flags
                if f in ('p.COV_ENABLE_GUI', 'p.COV_ENABLE_RGB_BUFFER_PREVIEW',
                         'p.COV_ENABLE_DEPTH_BUFFER_PREVIEW',
                         'p.COV_ENABLE_SEGMENTATION_MARK_PREVIEW')]


def test_show_asks_pybullet_for_window_flags_and_nothing_else():
    """The module's only call on the client is configureDebugVisualizer, it
    calls no function of pybullet itself (p.<NAME> is read for the flag
    constants alone), and it imports nothing else."""
    tree = _tree('tampura_bridge', 'gui_panes.py')
    called = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    assert called == {'client.configureDebugVisualizer', '_set', 'print', 'type'}
    imported = [ast.unparse(n) for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert imported == ['import pybullet as p']


def test_a_real_client_takes_the_calls(capsys):
    """Through a real BulletClient, as the driver calls it: the flag
    constants exist and the calls are taken (nothing is reported).  A DIRECT
    client has no window, so the flags do nothing there and the world and
    the image below would be the same for any flag: what a render returns
    with the panel on, off and put away again is the screen check's finding
    (a window's client on a screen in memory, the same pixels from both
    renderers: tracks/dbgcams/STATE.md)."""
    bc = bullet_client.BulletClient(connection_mode=p.DIRECT)
    try:
        bc.setAdditionalSearchPath(pybullet_data.getDataPath())
        bc.loadURDF('plane.urdf')
        robot = bc.loadURDF('franka_panda/panda.urdf', [0, 0, 0], useFixedBase=True)
        cube = bc.loadURDF('cube_small.urdf', [0.5, 0.0, 0.05])
        view = p.computeViewMatrix([0.18, 0.05, 0.59], [0.5, 0, 0], [0, 0, 1])
        proj = p.computeProjectionMatrixFOV(49.13, 64 / 48, 0.02, 5.0)

        def world():
            return (bc.getNumBodies(), bc.getBasePositionAndOrientation(cube),
                    [bc.getJointState(robot, j)[:2]
                     for j in range(bc.getNumJoints(robot))],
                    bc.getPhysicsEngineParameters())

        def image():
            out = bc.getCameraImage(64, 48, viewMatrix=view, projectionMatrix=proj,
                                    renderer=p.ER_TINY_RENDERER)
            return [np.asarray(part).tobytes() for part in out[2:5]]

        before, seen = world(), image()
        gui_panes.show(bc)
        assert world() == before
        assert image() == seen
        gui_panes.hide(bc)
        assert world() == before
        assert image() == seen
        assert 'gui_panes' not in capsys.readouterr().out
    finally:
        bc.disconnect()


# What a unit test cannot run is the driver's main() (a whole TAMPURA world),
# so where the call sits is pinned as written.
def test_the_driver_shows_the_panes_once_under_vis_alone_between_initialize_and_rollout():
    tree = _tree('tampura_bridge', 'run_bridge_on_finddice.py')
    (main,) = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == 'main']
    (show,) = _calls_in(tree, 'gui_panes.show')
    assert [ast.unparse(a) for a in show.args] == ['env.world.client']
    assert not show.keywords
    # a statement of its own in the body (no else branch) of an `if a.vis:`
    # that is a statement of main() itself
    holders = [n for n in main.body
               if isinstance(n, ast.If) and ast.unparse(n.test) == 'a.vis'
               and any(isinstance(s, ast.Expr) and s.value is show for s in n.body)]
    assert len(holders) == 1
    (initialize,) = _calls_in(main, 'env.initialize')
    (rollout,) = _calls_in(main, 'policy.rollout')
    assert initialize.lineno < show.lineno < rollout.lineno


def test_the_driver_puts_the_panes_away_before_its_overview_renders():
    """PyBullet copies every render into the panes, and the overview's two
    views are not the robot's: under --vis 1 the panel is hidden after the
    rollout and before _save_overview renders."""
    tree = _tree('tampura_bridge', 'run_bridge_on_finddice.py')
    (main,) = [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == 'main']
    (hide,) = _calls_in(tree, 'gui_panes.hide')
    assert [ast.unparse(a) for a in hide.args] == ['env.world.client']
    assert not hide.keywords
    holders = [n for n in main.body
               if isinstance(n, ast.If) and ast.unparse(n.test) == 'a.vis'
               and not n.orelse
               and [ast.unparse(s) for s in n.body] == ['gui_panes.hide(env.world.client)']]
    assert len(holders) == 1
    (rollout,) = _calls_in(main, 'policy.rollout')
    (overview,) = _calls_in(main, '_save_overview')
    assert rollout.lineno < hide.lineno < overview.lineno
    # the overview is the driver's only render call of its own
    assert len(_calls_in(tree, 'client.getCameraImage')) == 1
    assert not _calls_in(tree, 'p.getCameraImage')


def test_nothing_but_the_driver_uses_gui_panes():
    """The episode (policy.py), the pipeline and the gates do not know the
    module: a headless run and an eval never import a caller of it other
    than the driver's `if a.vis:`."""
    users = []
    for folder in ('', 'tampura_bridge', 'tools'):
        for name in sorted(os.listdir(os.path.join(REPO, folder))):
            if not name.endswith('.py') or name == 'gui_panes.py':
                continue
            with open(os.path.join(REPO, folder, name), encoding='utf-8',
                      errors='replace') as f:
                if 'gui_panes' in f.read():
                    users.append(os.path.join(folder, name).replace(os.sep, '/'))
    assert users == ['tampura_bridge/run_bridge_on_finddice.py']
