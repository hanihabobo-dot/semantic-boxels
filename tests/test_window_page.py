"""Hani, 2026-11-22: our own window without PyBullet's own panels and a page
of our own beside it (gui_page, --gui-page on).  What the env does when a
run has the page, and that nothing differs when it has none.

No test here opens a window (tracks rule 13): as in test_window_panes.py a
GUI connection is handed a DIRECT client in a process of its own, and the
calls are written down in order.  What the window and the page look like is
the screen check's finding (tracks/dbgcams/STATE.md)."""
import ast
import io
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from console import gui_page
from console import run_logger
from world.boxel_env import BoxelTestEnv

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = Path(REPO) / 'test_full_pipeline.py'

# A window that opens, an observation and a refresh, with every connection,
# every switch of PyBullet's window, every render and every hand-over to the
# page written down in order.  argv[1] says whether the run has a page.
_OPENING = r'''
import json, sys
import pybullet as p

real_connect, real_render, real_switch = p.connect, p.getCameraImage, p.configureDebugVisualizer
log = []
SWITCHES = {p.COV_ENABLE_GUI: "PyBullet's panels", p.COV_ENABLE_MOUSE_PICKING: 'mouse picking'}


def connect(mode, *args, **kwargs):
    client = real_connect(p.DIRECT)
    log.append(['connect', 'window' if mode == p.GUI else 'no window'])
    return client


def render(*args, **kwargs):
    log.append(['render', 'TinyRenderer' if kwargs.get('renderer') == p.ER_TINY_RENDERER
                else 'hardware'])
    return real_render(*args, **kwargs)


def switch(flag, value, *args, **kwargs):
    log.append(['switch', SWITCHES.get(flag, flag), value])
    return real_switch(flag, value, *args, **kwargs)


p.connect, p.getCameraImage, p.configureDebugVisualizer = connect, render, switch
from world import boxel_env
from console import gui_page


class Page:
    def offer_render(self, width, height, rgb, depth, seg, near, far, kind):
        log.append(['page', kind, width, height, near, far])


if sys.argv[1] == 'page':
    gui_page._page = Page()

seen = {}
own = boxel_env.BoxelTestEnv(gui=True)
seen['opening'], log = log, []
own.get_camera_observation()
seen['observation'], log = log, []
own.refresh_debug_camera_views()
seen['refresh'], log = log, []
seen['own has the page'] = own._page is not None

headless = boxel_env.BoxelTestEnv(gui=False)
headless.get_camera_observation()
headless.refresh_debug_camera_views()
seen['headless'], log = log, []
seen['headless has the page'] = headless._page is not None


class Stop(Exception):
    pass


class Adopted(boxel_env.BoxelTestEnv):
    def _adopt_scene(self):
        raise Stop()


world = real_connect(p.DIRECT)
try:
    Adopted(gui=True, adopt_client=world)
except Stop:
    pass
seen['adopted'] = log
print(json.dumps(seen))
'''


def _opening(with_page):
    done = subprocess.run([sys.executable, '-c', _OPENING, 'page' if with_page else 'none'],
                          cwd=REPO, capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout.strip().splitlines()[-1])


@pytest.fixture(scope='module')
def plain():
    return _opening(False)


@pytest.fixture(scope='module')
def paged():
    return _opening(True)


def test_without_the_page_the_window_is_todays(plain):
    """No page started: PyBullet's panels are never switched and no render
    is handed anywhere."""
    assert plain['opening'] == [['connect', 'window'],
                                ['switch', 'mouse picking', 0],
                                ['render', 'hardware'],
                                ['connect', 'no window']]
    assert plain['observation'] == [['render', 'hardware'], ['render', 'TinyRenderer']]
    assert plain['refresh'] == [['render', 'hardware']]
    assert plain['own has the page'] is False


def test_with_the_page_pybullets_panels_go_when_the_window_opens(paged):
    assert paged['opening'] == [['connect', 'window'],
                                ['switch', 'mouse picking', 0],
                                ['switch', "PyBullet's panels", 0],
                                ['render', 'hardware'],
                                ['page', 'display', 640, 480, 0.01, 5.0],
                                ['connect', 'no window']]
    assert paged['own has the page'] is True


def test_with_the_page_the_same_renders_are_made_and_handed_over(plain, paged):
    """The page gets the robot's own render at an observation and the
    display render at a refresh; no render is made for the page."""
    assert paged['observation'] == [['render', 'hardware'],
                                    ['render', 'TinyRenderer'],
                                    ['page', 'observation', 640, 480, 0.01, 5.0]]
    assert paged['refresh'] == [['render', 'hardware'],
                                ['page', 'display', 640, 480, 0.01, 5.0]]

    def calls(rows):
        return [row for row in rows if row[0] != 'page' and row[1] != "PyBullet's panels"]

    for part in ('opening', 'observation', 'refresh'):
        assert calls(paged[part]) == plain[part], part


def test_a_headless_env_and_an_adopted_world_never_have_the_page(plain, paged):
    """A page started by the run changes nothing for an env that opens no
    window of its own: the pre-flight's headless env and the bridge's
    adopted world."""
    for seen in (plain, paged):
        assert seen['headless'] == [['connect', 'no window'], ['connect', 'no window'],
                                    ['render', 'TinyRenderer']]
        assert seen['headless has the page'] is False
        assert seen['adopted'] == [['connect', 'no window']]


@pytest.fixture
def env():
    e = BoxelTestEnv(gui=False)
    yield e
    e._gui = False
    e._page = None
    e.close()


class _Kept:
    def __init__(self):
        self.renders = []

    def offer_render(self, width, height, rgb, depth, seg, near, far, kind):
        self.renders.append((kind, np.array(rgb), np.array(depth), np.array(seg)))


def test_the_robot_gets_the_same_observation_with_and_without_the_page(env):
    plain = env.get_camera_observation()
    env._gui, env._page = True, _Kept()
    paged = env.get_camera_observation()
    assert plain.visible_objects == paged.visible_objects
    assert np.array_equal(plain.rgb_image, paged.rgb_image)
    assert np.array_equal(plain.depth_image, paged.depth_image)
    assert np.array_equal(plain.seg_mask, paged.seg_mask)
    # and what the page was handed is that observation's own render
    ((kind, rgb, depth, seg),) = env._page.renders
    assert kind == 'observation'
    assert np.array_equal(rgb.reshape(480, 640, 4)[:, :, :3], paged.rgb_image)
    assert np.array_equal(seg.reshape(480, 640), paged.seg_mask)
    assert np.allclose(env._depth_buffer_to_meters(depth.reshape(480, 640).astype(float)),
                       paged.depth_image)


def test_a_real_page_shows_the_observations_own_picture(env):
    page = gui_page.start(console=None, port=0)
    try:
        env._gui, env._page = True, page
        seen = env.get_camera_observation()
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', page.port, timeout=10)
        conn.request('GET', '/cam/rgb.png')
        shown = np.asarray(Image.open(io.BytesIO(conn.getresponse().read())).convert('RGB'))
        conn.close()
        assert np.array_equal(shown, seen.rgb_image)
        assert page.state()['camera']['kind'] == 'observation'
    finally:
        gui_page.stop()


def test_a_page_that_fails_never_reaches_the_observation(env):
    """gui_page.Page.offer_render swallows its own errors; the env calls
    nothing else of the page."""
    page = gui_page.Page(None, 0)
    try:
        env._gui, env._page = True, page
        page._lock = None                       # every hand-over fails inside
        seen = env.get_camera_observation()
        assert seen.rgb_image.shape == (480, 640, 3)
    finally:
        page.close()


def test_the_switch_is_off_unless_asked():
    assert run_logger.parse_pipeline_args(['--no-gui']).gui_page == 'off'
    assert run_logger.parse_pipeline_args([]).gui_page == 'off'
    assert run_logger.parse_pipeline_args(['--gui-page', 'on']).gui_page == 'on'


# The entry block's own statement that starts the page, taken from the source
# by ast (as tests/test_pipeline_entry_exit_codes.py takes the block's tail)
# and run with stand-ins.
def _start_statement():
    tree = ast.parse(ENTRY.read_text(encoding='utf-8'))
    (entry,) = [n for n in tree.body if isinstance(n, ast.If)
                and ast.unparse(n.test) == "__name__ == '__main__'"]
    starts = [s for s in entry.body if isinstance(s, ast.If) and 'gui_page.start' in ast.unparse(s)]
    (start,) = starts
    # it sits before the scene is built and before the pre-flight's env
    first_env = min(s.lineno for s in entry.body if 'BoxelTestEnv(' in ast.unparse(s))
    assert start.lineno < first_env
    return compile(ast.Module(body=[start], type_ignores=[]), str(ENTRY), 'exec')


def _run_start(monkeypatch, gui_page_flag, no_gui, page):
    calls = []
    fake = types.SimpleNamespace(
        start=lambda console=None: calls.append('start') or page,
        last_error=OSError('all ten are taken'), DEFAULT_PORT=8765)
    # `from console import gui_page` takes the package's attribute when the module is
    # loaded and the entry of sys.modules otherwise: both are the stand-in here
    monkeypatch.setitem(sys.modules, 'console.gui_page', fake)
    monkeypatch.setattr(sys.modules['console'], 'gui_page', fake, raising=False)
    console = types.SimpleNamespace(
        installed=lambda: True,
        startup=lambda text: calls.append(('startup', text)),
        warn=lambda text: calls.append(('warn', text)))
    args = types.SimpleNamespace(gui_page=gui_page_flag, no_gui=no_gui)
    exec(_start_statement(), {'args': args, 'console_ui': console})
    return calls


def test_the_entry_starts_the_page_only_for_a_window_run_that_asks(monkeypatch):
    page = types.SimpleNamespace(url='http://localhost:8765/')
    assert _run_start(monkeypatch, 'off', False, page) == []
    assert _run_start(monkeypatch, 'on', True, page) == []          # --no-gui: no page
    assert _run_start(monkeypatch, 'on', False, page) == [
        'start', ('startup', 'the page of this run: http://localhost:8765/')]


def test_the_entry_says_so_when_no_port_is_free(monkeypatch):
    calls = _run_start(monkeypatch, 'on', False, None)
    assert calls[0] == 'start' and calls[1][0] == 'warn'
    assert 'no page' in calls[1][1] and 'all ten are taken' in calls[1][1]
