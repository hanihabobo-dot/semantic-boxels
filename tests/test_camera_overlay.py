"""BF#68 (run tampura -Draw cameras): the camera observer shows what the
cameras saw and changes nothing.  Throwaway DIRECT clients stand in for the
executing world (c0) and our plan twin (c1); the eye and the wrist are two
views of the same small scene."""
import hashlib
import json
import os
import random

import numpy as np
import pybullet as p
import pybullet_data
import pytest
from PIL import Image

from tampura_bridge import camera_overlay
from tampura_bridge.camera_overlay import (CameraObserver, camera_pose,
                                           near_far, view_volume)

W, H = 160, 120
EYE_POS, EYE_TARGET = [0.18, 0.05, 0.59], [0.5, 0.0, 0.0]
EYE_VIEW = p.computeViewMatrix(EYE_POS, EYE_TARGET, [0, 0, 1])
PROJ = p.computeProjectionMatrixFOV(49.13, W / H, 0.02, 5.0)
WRIST_VIEW = p.computeViewMatrix([0.45, 0.0, 0.40], [0.5, 0.0, 0.0],
                                 [-1, 0, 0])


@pytest.fixture(autouse=True)
def restore_the_render_call():
    """Whatever a failed assert leaves installed goes back to the function found."""
    found = p.getCameraImage
    yield
    p.getCameraImage = found


@pytest.fixture
def world():
    c0 = p.connect(p.DIRECT)
    c1 = p.connect(p.DIRECT)
    for c in (c0, c1):
        p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=c)
        p.loadURDF('plane.urdf', physicsClientId=c)
        p.loadURDF('cube_small.urdf', [0.5, 0.0, 0.05], physicsClientId=c)
    yield c0, c1
    p.disconnect(c0)
    p.disconnect(c1)


def _render(client, view, **kw):
    kw.setdefault('renderer', p.ER_TINY_RENDERER)
    return p.getCameraImage(W, H, viewMatrix=view, projectionMatrix=PROJ,
                            physicsClientId=client, **kw)


def _digest(result):
    return [hashlib.sha256(np.ascontiguousarray(np.asarray(a)).tobytes()).hexdigest()
            for a in result[2:5]]


def test_the_render_comes_back_unchanged_and_both_cameras_are_written(world, tmp_path):
    c0, _ = world
    original = p.getCameraImage
    plain_eye = _digest(_render(c0, EYE_VIEW))
    plain_wrist = _digest(_render(c0, WRIST_VIEW))
    n_bodies = p.getNumBodies(physicsClientId=c0)
    obs = CameraObserver(tmp_path / 'cams', c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        assert _digest(_render(c0, EYE_VIEW)) == plain_eye
        assert _digest(_render(c0, WRIST_VIEW)) == plain_wrist
        _render(c0, EYE_VIEW)
    finally:
        obs.uninstall()
    assert p.getCameraImage is original
    assert p.getNumBodies(physicsClientId=c0) == n_bodies
    folder = tmp_path / 'cams'
    assert sorted(os.listdir(folder)) == ['eye.json', 'eye.png', 'wrist.json', 'wrist.png']
    eye = json.loads((folder / 'eye.json').read_text())
    assert (eye['camera'], eye['n'], eye['size'], eye['plan']) == ('eye', 2, '160x120', None)
    assert json.loads((folder / 'wrist.json').read_text())['n'] == 1
    assert Image.open(folder / 'eye.png').size == (W, H + H // 2)


def test_the_picture_shows_rgb_depth_and_segmentation(world, tmp_path):
    c0, _ = world
    rgba = np.asarray(_render(c0, EYE_VIEW)[2], dtype=np.uint8).reshape(H, W, 4)
    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        _render(c0, EYE_VIEW)
    finally:
        obs.uninstall()
    img = np.asarray(Image.open(tmp_path / 'eye.png').convert('RGB'))
    assert np.array_equal(img[:H], rgba[:, :, :3])
    depth = img[H:, :W // 2]
    seg = img[H:, W // 2:]
    assert depth.max() > depth.min()
    assert len({tuple(px) for px in seg.reshape(-1, 3)}) >= 2
    meta = json.loads((tmp_path / 'eye.json').read_text())
    assert 0.02 < meta['depth_m'][0] < meta['depth_m'][1] < 5.0


def test_only_tiny_renders_on_the_executing_client_are_shown(world, tmp_path):
    c0, c1 = world
    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        _render(c1, EYE_VIEW)                       # the plan twin
        p.getCameraImage(W, H, viewMatrix=EYE_VIEW, projectionMatrix=PROJ,
                         physicsClientId=c0)         # no renderer named
        obs._see((), {'physicsClientId': c0, 'viewMatrix': EYE_VIEW,
                      'projectionMatrix': PROJ,
                      'renderer': p.ER_BULLET_HARDWARE_OPENGL}, None)
    finally:
        obs.uninstall()
    assert os.listdir(tmp_path) == [] and obs.counts == {}
    obs.install()
    try:
        _render(c0, EYE_VIEW)
    finally:
        obs.uninstall()
    assert obs.counts == {'eye': 1}


def test_the_observer_draws_no_random_number(world, tmp_path):
    """The planner's RRT-Connect searches draw from the global generators, so the
    BF#68 comparison of two runs looks at their final RNG states: the observer
    (images read, files written, lines drawn) must leave both generators where
    they were."""
    c0, _ = world
    random.seed(1234)
    np.random.seed(1234)
    py_before, np_before = random.getstate(), np.random.get_state()
    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        for view in (EYE_VIEW, WRIST_VIEW, EYE_VIEW):
            _render(c0, view)
    finally:
        obs.uninstall()
    assert obs.counts == {'eye': 2, 'wrist': 1} and not obs.disabled
    assert random.getstate() == py_before
    np_after = np.random.get_state()
    assert np_after[0] == np_before[0] and np.array_equal(np_after[1], np_before[1])
    assert np_after[2:] == np_before[2:]


def test_a_failure_of_the_observer_never_reaches_the_run(world, tmp_path, monkeypatch, capsys):
    """An error in the observer's own work (a bug, not a busy disk: see the write
    tests below) turns it off with one warning and the render goes through."""
    c0, _ = world
    plain = _digest(_render(c0, EYE_VIEW))
    plain_wrist = _digest(_render(c0, WRIST_VIEW))

    def bug(*args):
        raise ValueError('a bug in the observer')

    monkeypatch.setattr(CameraObserver, '_depth_image', staticmethod(bug))
    obs = CameraObserver(tmp_path / 'cams', c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        assert _digest(_render(c0, EYE_VIEW)) == plain
        assert obs.disabled and 'ValueError' in obs.error
        assert _digest(_render(c0, WRIST_VIEW)) == plain_wrist
        assert _digest(_render(c0, EYE_VIEW)) == plain
    finally:
        obs.uninstall()
    assert capsys.readouterr().out.count('camera view: turned off') == 1
    assert obs.counts == {'eye': 1}                  # nothing counted after it was off


def test_a_folder_that_cannot_be_made_leaves_the_observer_off_and_the_run_untouched(
        world, tmp_path, capsys):
    """install() runs inside the episode's try: a raise would end the episode."""
    c0, _ = world
    original = p.getCameraImage
    plain = _digest(_render(c0, EYE_VIEW))
    blocker = tmp_path / 'cams'
    blocker.write_text('a file where the folder should be')
    obs = CameraObserver(blocker, c0, EYE_VIEW, PROJ)
    obs.install()                                    # does not raise
    assert obs.disabled and 'could not start' in capsys.readouterr().out
    assert p.getCameraImage is original              # nothing was put on the call
    assert _digest(_render(c0, EYE_VIEW)) == plain
    obs.uninstall()                                  # a no-op
    assert p.getCameraImage is original and obs.counts == {}


def test_a_write_that_fails_once_is_tried_again(world, tmp_path, monkeypatch, capsys):
    c0, _ = world
    monkeypatch.setattr(camera_overlay, '_PAUSE_S', 0)
    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 1:
            raise PermissionError(13, 'in use', dst)
        return real(src, dst)

    monkeypatch.setattr(os, 'replace', flaky)
    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        _render(c0, EYE_VIEW)
    finally:
        obs.uninstall()
    assert obs.skipped == 0 and not obs.disabled
    assert (tmp_path / 'eye.png').exists() and (tmp_path / 'eye.json').exists()
    assert len(calls) == 3                           # the picture twice, its caption once
    assert 'camera view' not in capsys.readouterr().out


def test_a_picture_that_cannot_be_written_is_skipped_and_ten_in_a_row_turn_the_view_off(
        world, tmp_path, monkeypatch, capsys):
    c0, _ = world
    plain = _digest(_render(c0, EYE_VIEW))
    monkeypatch.setattr(camera_overlay, '_PAUSE_S', 0)
    real = os.replace

    def refuse(src, dst):
        raise PermissionError(13, 'in use', dst)

    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        monkeypatch.setattr(os, 'replace', refuse)
        for k in range(1, 10):
            assert _digest(_render(c0, EYE_VIEW)) == plain
            assert obs.skipped == k and not obs.disabled
        assert capsys.readouterr().out.count('could not be written') == 1    # once, not nine times
        assert not (tmp_path / 'eye.png').exists()
        monkeypatch.setattr(os, 'replace', real)                              # the disk is back
        assert _digest(_render(c0, EYE_VIEW)) == plain
        assert obs.skipped == 0 and (tmp_path / 'eye.json').exists()
        monkeypatch.setattr(os, 'replace', refuse)                            # and gone for good
        for _ in range(10):
            assert _digest(_render(c0, EYE_VIEW)) == plain
        assert obs.disabled and 'PermissionError' in obs.error
        assert capsys.readouterr().out.count('turned off') == 1
    finally:
        obs.uninstall()


def test_the_warning_never_raises_into_the_run(monkeypatch):
    def broken(*args, **kwargs):
        raise OSError('the console is gone')

    monkeypatch.setattr('builtins.print', broken)
    camera_overlay._warn('a warning')                # no exception


def test_the_observer_only_reads_the_images_it_is_given(world, tmp_path):
    """Read-only arrays: a write into the caller's result would raise, and the
    observer would turn itself off."""
    c0, _ = world
    n = W * H
    rgb = np.random.RandomState(1).randint(0, 255, n * 4).astype(np.uint8)
    depth = np.linspace(0.2, 0.99, n).astype(np.float32)
    seg = (np.arange(n) % 5 - 1).astype(np.int32)
    for a in (rgb, depth, seg):
        a.flags.writeable = False
    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ, frustums=False)
    obs._see((), {'physicsClientId': c0, 'viewMatrix': EYE_VIEW, 'projectionMatrix': PROJ,
                  'renderer': p.ER_TINY_RENDERER}, (W, H, rgb, depth, seg))
    assert obs.counts == {'eye': 1} and not obs.disabled, obs.error
    assert (tmp_path / 'eye.png').exists()


def test_a_second_install_is_refused_and_uninstall_is_idempotent(world, tmp_path):
    c0, _ = world
    original = p.getCameraImage
    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ)
    obs.install()
    with pytest.raises(RuntimeError):
        obs.install()
    obs.uninstall()
    obs.uninstall()
    assert p.getCameraImage is original


def test_the_view_volume_runs_from_the_eye_to_the_image_corners():
    eye, right, up, fwd = camera_pose(EYE_VIEW)
    assert np.allclose(eye, EYE_POS, atol=1e-5)
    want = np.array(EYE_TARGET) - np.array(EYE_POS)
    assert np.allclose(fwd, want / np.linalg.norm(want), atol=1e-5)
    assert abs(float(np.dot(right, fwd))) < 1e-6 and abs(float(np.dot(up, fwd))) < 1e-6
    near, far = near_far(PROJ)
    # pybullet hands out the matrix in float32; far is recovered to about 1e-5
    assert abs(near - 0.02) < 1e-6 and abs(far - 5.0) < 1e-3
    lines = view_volume(EYE_VIEW, PROJ, 0.7)
    assert len(lines) == 8
    v = np.array(EYE_VIEW).reshape(4, 4, order='F')
    pr = np.array(PROJ).reshape(4, 4, order='F')
    for (start, end), (sx, sy) in zip(lines[:4], camera_overlay._CORNERS):
        assert np.allclose(start, eye)
        clip = pr @ v @ np.append(end, 1.0)
        assert np.allclose(clip[:2] / clip[3], [sx, sy], atol=1e-5)


def test_the_view_volume_is_drawn_as_debug_items_and_redrawn_for_the_wrist(world, tmp_path, monkeypatch):
    c0, _ = world
    calls = {'line': 0, 'text': 0, 'removed': []}
    ids = iter(range(100, 10000))

    def line(*a, **k):
        calls['line'] += 1
        return next(ids)

    def text(*a, **k):
        calls['text'] += 1
        return next(ids)

    monkeypatch.setattr(p, 'addUserDebugLine', line)
    monkeypatch.setattr(p, 'addUserDebugText', text)
    monkeypatch.setattr(p, 'removeUserDebugItem',
                        lambda item, **k: calls['removed'].append(item))
    obs = CameraObserver(tmp_path, c0, EYE_VIEW, PROJ)
    obs.install()
    try:
        _render(c0, EYE_VIEW)
        assert (calls['line'], calls['text'], calls['removed']) == (8, 1, [])
        _render(c0, WRIST_VIEW)
        assert (calls['line'], calls['text']) == (16, 2)
        _render(c0, WRIST_VIEW)
        assert (calls['line'], calls['text']) == (24, 3)
        assert len(calls['removed']) == 9
    finally:
        obs.uninstall()
    quiet = CameraObserver(tmp_path / 'q', c0, EYE_VIEW, PROJ, frustums=False)
    quiet.install()
    try:
        _render(c0, EYE_VIEW)
    finally:
        quiet.uninstall()
    assert (calls['line'], calls['text']) == (24, 3)
    assert (tmp_path / 'q' / 'eye.png').exists()
