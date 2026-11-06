"""BF#68 (run tampura -Draw boxels): the bridge's boxel overlay is debug lines
and labels only.  BoxelVisualizer(phantoms=False) creates, moves and removes
no body, so the executing world is untouched (a body creation on the executing
client is a G14 violation, audit R4.2) and a camera render is the same with
the overlay drawn as without it.  The control: the default visualizer adds a
body per boxel and those bodies do enter a TinyRenderer image (the F19
pollution that conceal/restore guards), so the comparison can fail."""
import numpy as np
import pybullet as p
import pybullet_data
import pytest

import visualization
from boxel_data import BoxelData, BoxelRegistry, BoxelType
from visualization import BoxelVisualizer

HALF = (0.05, 0.05, 0.05)
W, H = 64, 48


@pytest.fixture
def world():
    cid = p.connect(p.DIRECT)
    if cid != 0:
        # BoxelVisualizer draws on the default client, which is client 0 in
        # the pipeline; a test world on another id would not see its bodies
        p.disconnect(cid)
        pytest.skip('client 0 is held by another test: the visualizer draws on it')
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
    p.loadURDF('plane.urdf', physicsClientId=cid)
    box = p.createMultiBody(
        0.0, p.createCollisionShape(p.GEOM_BOX, halfExtents=HALF, physicsClientId=cid),
        p.createVisualShape(p.GEOM_BOX, halfExtents=HALF, physicsClientId=cid),
        basePosition=[0.0, 0.0, HALF[2]], physicsClientId=cid)
    view = p.computeViewMatrix([0.0, -0.5, 0.4], [0.0, 0.0, 0.0], [0, 0, 1])
    proj = p.computeProjectionMatrixFOV(60, W / H, 0.05, 3.0)
    yield cid, box, view, proj
    p.disconnect(cid)


def _registry():
    reg = BoxelRegistry()
    reg.add_boxel(BoxelData(
        id='die', boxel_type=BoxelType.OBJECT, object_name='die',
        min_corner=np.array([-HALF[0], -HALF[1], 0.0]),
        max_corner=np.array([HALF[0], HALF[1], 2 * HALF[2]])))
    reg.add_boxel(BoxelData(
        id='shadow_of_die', boxel_type=BoxelType.SHADOW, created_by_object='die',
        min_corner=np.array([-0.05, 0.05, 0.0]),
        max_corner=np.array([0.05, 0.20, 0.10])))
    return reg


def _render(cid, view, proj):
    _, _, rgb, depth, seg = p.getCameraImage(
        W, H, viewMatrix=view, projectionMatrix=proj,
        renderer=p.ER_TINY_RENDERER, physicsClientId=cid)
    return (np.asarray(rgb, dtype=np.uint8).copy(),
            np.asarray(depth, dtype=float).copy(),
            np.asarray(seg).copy())


def test_lines_only_overlay_adds_no_body(world):
    cid, box, view, proj = world
    homes = dict(visualization._PHANTOM_HOME)
    n_bodies = p.getNumBodies(physicsClientId=cid)
    viz = BoxelVisualizer(phantoms=False)
    viz.draw_registry(_registry(), duration=0, label_size=1.0)
    # 12 edges and one label per boxel (a DIRECT client gives every debug
    # item the id -1, so the per-boxel lists are what counts them)
    assert [len(viz._items_by_id[b]) for b in ('die', 'shadow_of_die')] == [13, 13]
    assert p.getNumBodies(physicsClientId=cid) == n_bodies
    assert viz.shadow_bodies == set()
    assert visualization._PHANTOM_HOME == homes
    assert all(ids == [] for ids in viz._bodies_by_id.values())
    # the pipeline's own calls on it: redraw one boxel, remove it, clear all
    bd = _registry().get_boxel('die')
    viz.remove_boxel_viz('die')
    assert not viz.tracks_boxel('die') and viz.tracks_boxel('shadow_of_die')
    viz.draw_boxel_data(bd)
    assert viz.tracks_boxel('die')
    viz.clear_all()
    assert viz.debug_items == set()
    assert p.getNumBodies(physicsClientId=cid) == n_bodies
    assert visualization._PHANTOM_HOME == homes


def test_lines_only_overlay_leaves_a_render_unchanged(world):
    """The render is taken with the overlay drawn and NOT concealed (the
    observation chokepoint's conceal would hide a phantom and the test could
    not tell): had the overlay put a body into the world, this image would
    differ, as the control below shows for phantoms.  What a DIRECT client
    cannot show is that GUI debug lines stay out of a TinyRenderer image (it
    draws no line at all and gives every debug item the id -1): that is held
    by TinyRenderer drawing visual shapes only and by the GUI equivalence
    runs, which hash every render (tools/draw_equiv_run.py)."""
    cid, box, view, proj = world
    before = _render(cid, view, proj)
    viz = BoxelVisualizer(phantoms=False)
    try:
        viz.draw_registry(_registry(), duration=0, label_size=1.0)
        during = _render(cid, view, proj)
    finally:
        viz.clear_all()
    for a, b in zip(before, during):
        assert np.array_equal(a, b)


def test_control_the_default_overlay_adds_bodies_that_a_render_sees(world):
    cid, box, view, proj = world
    before = _render(cid, view, proj)
    n_bodies = p.getNumBodies(physicsClientId=cid)
    viz = BoxelVisualizer()
    try:
        viz.draw_registry(_registry(), duration=0, label_size=1.0)
        assert p.getNumBodies(physicsClientId=cid) == n_bodies + 2
        after = _render(cid, view, proj)
        assert not np.array_equal(before[2], after[2])
    finally:
        viz.clear_all()
    assert p.getNumBodies(physicsClientId=cid) == n_bodies


def test_lines_only_overlay_refuses_a_phantom(world):
    cid, box, view, proj = world
    n_bodies = p.getNumBodies(physicsClientId=cid)
    viz = BoxelVisualizer(phantoms=False)
    with pytest.raises(RuntimeError):
        viz._draw_boxel_phantom([0.0, 0.0, 0.0], [0.1, 0.1, 0.1], [1, 0, 0], 0.05)
    assert p.getNumBodies(physicsClientId=cid) == n_bodies


def test_the_default_is_still_the_phantom_overlay():
    assert BoxelVisualizer()._phantoms is True
