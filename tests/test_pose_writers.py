"""PLAN_P4_POSE_GRASP_SAMPLERS.md step 4: the pose writers' rules (M8 A)
and the M9 fusion."""
import math
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pytest

import perception
import pose_belief
from boxel_data import BoxelData, BoxelRegistry, BoxelType
from perception import ObjectDetection


@pytest.fixture
def switches_on():
    saved = dict(pose_belief.SWITCHES)
    pose_belief.SWITCHES.update({k: True for k in saved})
    saved_tol = pose_belief.PLACE_POSE_TOL
    pose_belief.PLACE_POSE_TOL = 0.004
    yield
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)
    pose_belief.PLACE_POSE_TOL = saved_tol


def det(yaw=0.0, ext=(0.02, 0.02), valid=True, raw=None):
    e = np.array([ext[0], ext[1], 0.02])
    return ObjectDetection(name='o', body_id=1, pixel_count=500,
                           est_min=np.zeros(3), est_max=e.copy(), yaw=yaw,
                           yaw_valid=valid, rect_center=e[:2] / 2,
                           body_extents=e.copy() if valid else None,
                           pixel_steps=np.array([[0.0005, 0.0], [0.0, 0.0005]]),
                           raw_xy_ext=np.array(raw if raw else ext))


def boxel():
    return BoxelData(id='o', boxel_type=BoxelType.OBJECT,
                     min_corner=np.zeros(3), max_corner=np.array([0.02, 0.02, 0.02]))


def test_writers_are_no_ops_while_off():
    b = boxel()
    pose_belief.record_detection(b, det(), 'wrist', complete=True)
    pose_belief.mark_pose_commanded(b)
    assert b.pose_radius == math.inf and b.body_extents is None


def test_complete_sets_formula_partial_leaves_first_partial_adds(switches_on):
    b = boxel()
    pose_belief.record_detection(b, det(valid=False), 'eye', complete=False)
    assert b.pose_radius == math.inf
    pose_belief.record_detection(b, det(valid=False, raw=(0.02, 0.012)), 'eye',
                                 complete=False, first=True)
    first = b.pose_radius
    assert math.isfinite(first)
    pose_belief.record_detection(b, det(), 'wrist', complete=True)
    assert b.pose_radius < first
    tight = b.pose_radius
    pose_belief.record_detection(b, det(valid=False), 'eye', complete=False)
    assert b.pose_radius == tight
    pose_belief.mark_pose_unknown(b)
    assert b.pose_radius == math.inf
    pose_belief.mark_pose_commanded(b)
    assert b.pose_radius == 0.004


def test_fusion_aligns_by_quarter_turns_and_swaps(switches_on):
    b = boxel()
    pose_belief.record_detection(b, det(yaw=0.3, ext=(0.04, 0.02)), 'wrist', True)
    pose_belief.record_detection(b, det(yaw=0.3 - math.pi / 2, ext=(0.02, 0.0405)),
                                 'wrist', True)
    assert b.yaw == pytest.approx(0.3)
    assert np.allclose(b.body_extents[:2], [0.0405, 0.02])


def test_fusion_outlier_not_fused_and_span_capped(switches_on):
    b = boxel()
    pose_belief.record_detection(b, det(ext=(0.04, 0.02)), 'wrist', True)
    pose_belief.record_detection(b, det(ext=(0.06, 0.02)), 'wrist', True)
    assert np.allclose(b.body_extents[:2], [0.04, 0.02])
    c = boxel()
    pose_belief.record_detection(c, det(ext=(0.09, 0.02)), 'wrist', True)
    assert c.body_extents[0] == pytest.approx(0.076)


def test_deadband_zeroes_small_yaws_per_camera(switches_on):
    b = boxel()
    pose_belief.record_detection(b, det(yaw=math.radians(5)), 'eye', True)
    assert b.yaw == 0.0 and b.yaw_valid
    c = boxel()
    pose_belief.record_detection(c, det(yaw=math.radians(5)), 'wrist', True)
    assert c.yaw == pytest.approx(math.radians(5))


def test_refresh_tightens_the_radius_of_an_unchanged_box(switches_on):
    import execution
    cid = p.connect(p.DIRECT)
    try:
        p.createMultiBody(0, p.createCollisionShape(p.GEOM_PLANE, physicsClientId=cid),
                          physicsClientId=cid)
        half = [0.02, 0.02, 0.03]
        body = p.createMultiBody(
            0.1, p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
            p.createVisualShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
            basePosition=[0.5, 0.0, 0.03], physicsClientId=cid)
        view = p.computeViewMatrix([0.0, 0.0, 0.6], [0.5, 0.0, 0.0], [0, 0, 1])
        proj = p.computeProjectionMatrixFOV(50, 640 / 480, 0.02, 5.0)
        _, _, _, d, seg = p.getCameraImage(640, 480, viewMatrix=view, projectionMatrix=proj,
                                           renderer=p.ER_TINY_RENDERER, physicsClientId=cid)
        buf = np.asarray(d, dtype=float).reshape(480, 640)
        seg = np.asarray(seg).reshape(480, 640)
        dets = perception.detect_objects_from_render(seg, buf, view, proj, {body: 'o'},
                                                     (0.0, 0.0), 0.0)
        dm = 5.0 * 0.02 / (5.0 - (5.0 - 0.02) * buf)
        env = SimpleNamespace(objects={'o': SimpleNamespace(object_id=body)})
        reg = BoxelRegistry()
        b = BoxelData(id='o', boxel_type=BoxelType.OBJECT,
                      min_corner=dets['o'].est_min.copy(), max_corner=dets['o'].est_max.copy())
        reg.add_boxel(b)
        assert b.pose_radius == math.inf
        execution.refresh_object_aabbs(env, reg, detections=dets,
                                       render=(dm, seg, view, proj))
        assert np.allclose(b.min_corner, dets['o'].est_min)      # unchanged box
        assert math.isfinite(b.pose_radius)
    finally:
        p.disconnect(cid)
