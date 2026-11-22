"""Hani, 2026-11-21: "Fix how the three look in our env."  Our own window
(BoxelTestEnv(gui=True), `run boxels`) and PyBullet's three camera panes in
it: all three fit in full, they are filled when the window opens, and no
render made for them shows the boxel overlay's bodies (TB-48).

No test here opens a window (tracks rule 13).  The renders run on a DIRECT
client, where PyBullet answers a hardware render request with the
TinyRenderer: with the env's GUI switch set by hand, or, for what __init__
does when a window opens, in a process of its own in which a GUI connection
is handed a DIRECT client.  What the window shows is the screen check's
finding (tracks/dbgcams/STATE.md)."""
import inspect
import json
import os
import subprocess
import sys

import numpy as np
import pybullet as p
import pytest

from world import boxel_env
from console import visualization
from world.boxel_env import BoxelTestEnv

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# PyBullet, examples/SharedMemory/PhysicsServerExample.cpp: the panes are made
# at fixed places, 228 x 192 each (gCamVisualizerWidth, gCamVisualizerHeight),
# the third at y = 95 + 2 * 192, each under a title bar.  The other two numbers
# are measured on the screen check, in a window 720 high: the third pane ends
# at y = 695 (24 px of title and frame) and the status bar starts at y = 698
# (22 px).  In a window 600 high the third pane is pushed up over the lower
# half of the second.
THIRD_PANE_TOP = 95 + 2 * 192
PANE_HEIGHT = 192
TITLE_AND_FRAME = 24            # measured
STATUS_BAR = 22                 # measured


def test_the_window_is_high_enough_for_the_three_panes():
    arguments = inspect.signature(BoxelTestEnv.__init__).parameters
    needed = THIRD_PANE_TOP + TITLE_AND_FRAME + PANE_HEIGHT + STATUS_BAR
    assert needed == 717
    assert arguments['window_height'].default >= needed
    # the size itself, as Hani's window opens
    assert (arguments['window_width'].default,
            arguments['window_height'].default) == (1280, 720)


# What __init__ does when a window opens, without a window: in a process of
# its own (so the env's client is PyBullet's default client, as in a run) a
# GUI connection is handed a DIRECT client, and every connection, every
# render (with the number of bodies in the world at that moment) and the
# overlay's two calls are written down in order.  Once for our own world and
# once for an adopted one, whose build is stopped where the scene would be
# registered: the window's first render sits before that.
_OPENING = r'''
import json
import pybullet as p

real_connect, real_render = p.connect, p.getCameraImage
log = []


def connect(mode, *args, **kwargs):
    client = real_connect(p.DIRECT)
    log.append(['connect', 'window' if mode == p.GUI else 'no window', client])
    return client


def render(*args, **kwargs):
    log.append(['render',
                'TinyRenderer' if kwargs.get('renderer') == p.ER_TINY_RENDERER else 'hardware',
                p.getNumBodies(physicsClientId=kwargs.get('physicsClientId', 0))])
    return real_render(*args, **kwargs)


p.connect, p.getCameraImage = connect, render
import boxel_env

boxel_env.conceal_overlay_for_observation = lambda: log.append(['overlay out of view'])
boxel_env.restore_overlay_after_observation = lambda: log.append(['overlay back'])

own = boxel_env.BoxelTestEnv(gui=True)
own_log = list(log)
headless_from = len(log)
boxel_env.BoxelTestEnv(gui=False)
headless_log = log[headless_from:]


class Stop(Exception):
    pass


class Adopted(boxel_env.BoxelTestEnv):
    def _adopt_scene(self):
        raise Stop()


world = real_connect(p.DIRECT)
adopted_from = len(log)
try:
    Adopted(gui=True, adopt_client=world)
except Stop:
    pass
print(json.dumps({'own': own_log, 'own_client': own.client_id,
                  'headless': headless_log, 'adopted': log[adopted_from:]}))
'''


def test_the_panes_are_filled_when_our_own_window_opens():
    """PyBullet opens the panes empty (a white field with a diagonal line).
    Our own window makes one pane render at once, on the still empty world,
    with the overlay's two calls around it, and no other render while it is
    built.  A headless env and an adopted world (the bridge's) make none."""
    done = subprocess.run([sys.executable, '-c', _OPENING], cwd=REPO,
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    seen = json.loads(done.stdout.strip().splitlines()[-1])
    assert seen['own_client'] == 0
    assert seen['own'] == [['connect', 'window', 0],
                           ['overlay out of view'],
                           ['render', 'hardware', 0],
                           ['overlay back'],
                           ['connect', 'no window', 1]]       # the plan twin
    assert [row[:2] for row in seen['headless']] == [['connect', 'no window'],
                                                     ['connect', 'no window']]
    assert [row[:2] for row in seen['adopted']] == [['connect', 'no window']]


@pytest.fixture
def env():
    e = BoxelTestEnv(gui=False)
    yield e
    e._gui = False
    e.close()


def _recorded(monkeypatch):
    """The overlay's two calls and every render, in the order they happen.
    The renders are made for real."""
    log = []
    monkeypatch.setattr(boxel_env, 'conceal_overlay_for_observation',
                        lambda: log.append('overlay out of view'))
    monkeypatch.setattr(boxel_env, 'restore_overlay_after_observation',
                        lambda: log.append('overlay back'))
    real = p.getCameraImage

    def render(*args, **kwargs):
        log.append('TinyRenderer' if kwargs['renderer'] == p.ER_TINY_RENDERER
                   else 'hardware')
        return real(*args, **kwargs)

    monkeypatch.setattr(boxel_env.p, 'getCameraImage', render)
    return log


def test_a_headless_env_renders_nothing_for_the_panes(env, monkeypatch):
    log = _recorded(monkeypatch)
    env.refresh_debug_camera_views()
    assert log == []
    env.get_camera_observation()
    assert log == ['overlay out of view', 'TinyRenderer', 'overlay back']


def test_the_pane_refresh_renders_with_the_overlay_out_of_view(env, monkeypatch):
    env._gui = True                     # what the window sets
    log = _recorded(monkeypatch)
    env.refresh_debug_camera_views()
    assert log == ['overlay out of view', 'hardware', 'overlay back']


def test_the_pane_render_of_an_observation_has_the_overlay_out_of_view(env, monkeypatch):
    env._gui = True
    log = _recorded(monkeypatch)
    env.get_camera_observation()
    assert log == ['overlay out of view', 'hardware', 'overlay back',
                   'overlay out of view', 'TinyRenderer', 'overlay back']


def test_the_overlay_comes_back_when_a_pane_render_fails(env, monkeypatch):
    env._gui = True
    log = []
    monkeypatch.setattr(boxel_env, 'conceal_overlay_for_observation',
                        lambda: log.append('overlay out of view'))
    monkeypatch.setattr(boxel_env, 'restore_overlay_after_observation',
                        lambda: log.append('overlay back'))

    def fails(*args, **kwargs):
        raise p.error('Not connected to physics server.')

    monkeypatch.setattr(boxel_env.p, 'getCameraImage', fails)
    with pytest.raises(p.error):
        env.refresh_debug_camera_views()
    assert log == ['overlay out of view', 'overlay back']
    log.clear()
    with pytest.raises(p.error):
        env.get_camera_observation()
    assert log == ['overlay out of view', 'overlay back']


def test_the_robot_gets_the_same_observation_with_and_without_the_pane_renders(env):
    """The pane renders are display only: what get_camera_observation hands
    the pipeline is the same image, depth and mask with them and without."""
    plain = env.get_camera_observation()
    env._gui = True
    with_panes = env.get_camera_observation()
    assert plain.visible_objects == with_panes.visible_objects
    assert np.array_equal(plain.rgb_image, with_panes.rgb_image)
    assert np.array_equal(plain.depth_image, with_panes.depth_image)
    assert np.array_equal(plain.seg_mask, with_panes.seg_mask)


def test_an_overlay_body_is_away_during_the_pane_render_and_back_after(env, monkeypatch):
    """The real thing, one body of the overlay in front of the camera: it is
    100 m below while the pane render is made and at its place after."""
    if env.client_id != 0:
        pytest.skip("the overlay draws on PyBullet's default client, which "
                    "another test's world holds in this process")
    viz = visualization.BoxelVisualizer()
    home = np.array([0.1, 0.0, 0.6])
    body = viz._draw_boxel_phantom(home, np.array([0.05, 0.05, 0.05]),
                                   [0.5, 0.5, 0.5], 0.05)
    try:
        env._gui = True
        seen = []
        real = p.getCameraImage

        def render(*args, **kwargs):
            seen.append(p.getBasePositionAndOrientation(body)[0][2])
            return real(*args, **kwargs)

        monkeypatch.setattr(boxel_env.p, 'getCameraImage', render)
        env.refresh_debug_camera_views()
        assert seen == [pytest.approx(home[2] - visualization._CONCEAL_DROP)]
        assert p.getBasePositionAndOrientation(body)[0] == pytest.approx(tuple(home))
    finally:
        viz.clear_all()
