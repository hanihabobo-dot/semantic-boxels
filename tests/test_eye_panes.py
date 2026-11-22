"""TB-40 (Hani, 2026-11-15: "the two debug cameras on the side should just
reflect what the robot sees and nothing else").  Under the GUI, with the eye
images wanted, world_eye saves the window's own view (eye_<k>_gui.png) with a
hardware render, which also refills the GUI's camera panes.  Right after
it the robot's camera is rendered again (env.refresh_debug_camera_views), so
the panes end on the robot's image.  Without the GUI neither render is made."""
import ast
import inspect

import numpy as np

from world import world_eye


class _Env:
    def __init__(self, gui, log, refresh_fails=False):
        self._gui = gui
        self._log = log
        self._refresh_fails = refresh_fails

    def refresh_debug_camera_views(self):
        self._log.append('robot view')
        if self._refresh_fails:
            raise RuntimeError('no render')


def _window(monkeypatch, log, fails=False):
    """The window's camera and the render call, in place of PyBullet's."""
    monkeypatch.setattr(world_eye.p, 'getDebugVisualizerCamera',
                        lambda *a, **k: (8, 6, [0.0] * 16, [0.0] * 16))

    def render(*args, **kwargs):
        assert kwargs['renderer'] == world_eye.p.ER_BULLET_HARDWARE_OPENGL
        log.append('user view')
        if fails:
            raise RuntimeError('no render')
        return 8, 6, np.zeros((6, 8, 4), dtype=np.uint8), None, None

    monkeypatch.setattr(world_eye.p, 'getCameraImage', render)


def _saved(tmp_path, env, rgb=None):
    eye = world_eye.WorldEye(tmp_path, env, None, {})
    try:
        return eye._save_images(1, rgb)
    finally:
        eye.close()


def test_after_the_window_screenshot_the_panes_get_the_robots_view_again(tmp_path, monkeypatch):
    log = []
    _window(monkeypatch, log)
    names = _saved(tmp_path, _Env(True, log))
    assert log == ['user view', 'robot view']
    assert names == ['eye_001_gui.png'] and (tmp_path / 'eye_001_gui.png').is_file()


def test_a_failed_window_screenshot_still_ends_on_the_robots_view(tmp_path, monkeypatch):
    log = []
    _window(monkeypatch, log, fails=True)
    assert _saved(tmp_path, _Env(True, log)) == []
    assert log == ['user view', 'robot view']


def test_a_failed_robot_view_render_never_breaks_the_snapshot(tmp_path, monkeypatch):
    log = []
    _window(monkeypatch, log)
    names = _saved(tmp_path, _Env(True, log, refresh_fails=True))
    assert log == ['user view', 'robot view'] and names == ['eye_001_gui.png']


def test_without_the_gui_neither_view_is_rendered(tmp_path, monkeypatch):
    log = []
    _window(monkeypatch, log)
    rgb = np.zeros((6, 8, 3), dtype=np.uint8)
    names = _saved(tmp_path, _Env(False, log), rgb=rgb)
    assert log == []
    assert names == ['eye_001_camera.png']


def test_the_snapshot_reaches_the_image_code_only_when_images_are_wanted():
    """A GUI run without --save-screenshots on makes no render for a picture,
    so none for the panes either: snapshot() calls _save_images in one place,
    guarded by save_image, which images_wanted() has gated before it."""
    tree = ast.parse(inspect.getsource(world_eye))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and ast.unparse(n.func) == 'self._save_images']
    assert len(calls) == 1
    # WorldEye.snapshot, the one function the call sits in (the module also
    # has a snapshot() of its own, which hands over to it)
    (snapshot,) = [n for n in ast.walk(tree)
                   if isinstance(n, ast.FunctionDef) and n.name == 'snapshot'
                   and any(m is calls[0] for m in ast.walk(n))]
    gate = [n for n in snapshot.body
            if ast.unparse(n) == 'save_image = save_image and images_wanted()']
    guarded = [n for n in ast.walk(snapshot)
               if isinstance(n, ast.IfExp) and n.body is calls[0]
               and ast.unparse(n.test) == 'save_image']
    assert len(gate) == 1 and len(guarded) == 1
    assert gate[0].lineno < guarded[0].lineno
