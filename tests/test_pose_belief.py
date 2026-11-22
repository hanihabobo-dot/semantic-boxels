"""PLAN_P4_POSE_GRASP_SAMPLERS.md step 2: the yaw fit (M9) and the pose
belief's radius and margin (M8 A, B), on synthetic point sets and
synthetic renders in a DIRECT client."""
import math

import numpy as np
import pybullet as p
import pytest

from sensing import perception
from sensing import pose_belief
from acting import robot_utils
from sensing.perception import ObjectDetection


def rect_points(cx, cy, a, b, yaw, n=40):
    u = np.linspace(-a / 2, a / 2, n)
    v = np.linspace(-b / 2, b / 2, n)
    g = np.array([[x, y] for x in u for y in v])
    c, s = math.cos(yaw), math.sin(yaw)
    return g @ np.array([[c, s], [-s, c]]) + [cx, cy]


def test_min_area_rect_recovers_a_rotated_rectangle():
    centre, ext, ang = perception.min_area_rect(rect_points(0.3, -0.1, 0.04, 0.02, 0.4))
    yaw, ext = perception.canonical_yaw(ang, ext)
    assert np.allclose(centre, [0.3, -0.1], atol=1e-6)
    assert np.allclose(ext, [0.04, 0.02], atol=1e-6)
    assert yaw == pytest.approx(0.4, abs=1e-6)


def test_min_area_rect_degenerate():
    assert perception.min_area_rect(np.array([[0, 0], [1, 1]])) is None
    assert perception.min_area_rect(np.array([[0, 0], [1, 1], [2, 2]])) is None


def test_canonical_yaw_square_modulo_quarter_turn_swaps_extents():
    yaw, ext = perception.canonical_yaw(math.radians(100), [0.0176, 0.0173])
    assert math.degrees(yaw) == pytest.approx(10.0)
    assert np.allclose(ext, [0.0173, 0.0176])


def test_canonical_yaw_rectangle_modulo_half_turn():
    yaw, ext = perception.canonical_yaw(math.radians(100), [0.04, 0.02])
    assert math.degrees(yaw) == pytest.approx(-80.0)
    assert np.allclose(ext, [0.04, 0.02])


@pytest.fixture
def client():
    cid = p.connect(p.DIRECT)
    p.createMultiBody(0, p.createCollisionShape(p.GEOM_PLANE, physicsClientId=cid),
                      physicsClientId=cid)
    yield cid
    p.disconnect(cid)


def add_box(cid, ext, xy, yaw):
    half = [e / 2 for e in ext]
    return p.createMultiBody(
        0.1, p.createCollisionShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
        p.createVisualShape(p.GEOM_BOX, halfExtents=half, physicsClientId=cid),
        basePosition=[xy[0], xy[1], half[2]],
        baseOrientation=p.getQuaternionFromEuler([0, 0, yaw]), physicsClientId=cid)


def top_down_render(cid, xy, height):
    cam = np.eye(4)
    cam[:3, :3] = np.column_stack([[1, 0, 0], [0, -1, 0], [0, 0, -1]])
    cam[:3, 3] = [xy[0], xy[1], height]
    view, proj = robot_utils.wrist_camera_matrices(cam)
    w, h = robot_utils.WRIST_CAMERA_WIDTH, robot_utils.WRIST_CAMERA_HEIGHT
    _, _, _, d, seg = p.getCameraImage(w, h, viewMatrix=view, projectionMatrix=proj,
                                       renderer=p.ER_TINY_RENDERER, physicsClientId=cid)
    return (np.asarray(seg).reshape(h, w), np.asarray(d, dtype=float).reshape(h, w),
            view, proj)


@pytest.mark.parametrize('ext,yaw_deg,expect_deg', [
    ((0.030, 0.020, 0.020), 25.0, 25.0),
    ((0.0176, 0.0173, 0.0178), 40.0, 40.0),
    ((0.0176, 0.0173, 0.0178), 70.0, -20.0),
])
def test_wrist_render_recovers_yaw_extents_and_centre(client, ext, yaw_deg, expect_deg):
    body = add_box(client, ext, (0.5, 0.1), math.radians(yaw_deg))
    seg, depth, view, proj = top_down_render(client, (0.5, 0.1), ext[2] + 0.25)
    det = perception.detect_objects_from_render(
        seg, depth, view, proj, {body: 'box'}, (0.5, 0.1), 0.0,
        no_footprint_completion=frozenset({'box'}))['box']
    assert det.yaw_valid
    assert math.degrees(det.yaw) == pytest.approx(expect_deg, abs=1.0)
    assert np.allclose(det.rect_center, [0.5, 0.1], atol=1e-3)
    assert np.allclose(sorted(det.body_extents[:2]), sorted(ext[:2]), atol=1.5e-3)
    assert det.body_extents[2] == pytest.approx(ext[2], abs=1.5e-3)
    fp = pose_belief.pixel_footprint(det.pixel_steps, det.yaw)
    assert 0.0002 < fp < 0.0008          # about 0.5 mm per pixel at 0.25 m


def test_too_few_top_pixels_leaves_yaw_invalid(client):
    body = add_box(client, (0.0176, 0.0173, 0.0178), (0.5, 0.1), 0.3)
    seg, depth, view, proj = top_down_render(client, (0.5, 0.1), 3.0)
    det = perception.detect_objects_from_render(
        seg, depth, view, proj, {body: 'box'}, (0.5, 0.1), 0.0, min_pixels=1,
        no_footprint_completion=frozenset({'box'}))['box']
    assert det.pixel_count < perception.YAW_MIN_TOP_PIXELS
    assert not det.yaw_valid and det.body_extents is None


def det(est_min, est_max, yaw_valid=False, yaw=0.0, body=None, raw=None,
        steps=((0.001, 0.0), (0.0, 0.004))):
    return ObjectDetection(name='o', body_id=1, pixel_count=100,
                           est_min=np.array(est_min, dtype=float),
                           est_max=np.array(est_max, dtype=float),
                           yaw=yaw, yaw_valid=yaw_valid,
                           body_extents=None if body is None else np.array(body, dtype=float),
                           pixel_steps=np.array(steps, dtype=float),
                           raw_xy_ext=None if raw is None else np.array(raw, dtype=float))


def test_pixel_footprint_takes_the_larger_axis():
    steps = np.array([[0.001, 0.0], [0.0, 0.004]])
    assert pose_belief.pixel_footprint(steps, 0.0) == pytest.approx(0.004)
    assert pose_belief.pixel_footprint(steps, math.pi / 2) == pytest.approx(0.004)
    assert pose_belief.pixel_footprint(steps, math.pi / 4) == pytest.approx(0.004 / math.sqrt(2))


def test_completion_term_branches():
    d = det([0, 0, 0], [0.03, 0.02, 0.02])
    assert pose_belief.completion_term(det([0, 0, 0], [0.03, 0.02, 0.02], yaw_valid=True,
                                           body=[0.03, 0.02, 0.02])) == 0.0
    assert pose_belief.completion_term(d, body_extents=[0.02, 0.026, 0.02]) == pytest.approx(0.002)
    assert pose_belief.completion_term(d, rigid_ext=[0.03, 0.02, 0.02]) == pytest.approx(0.0)
    assert pose_belief.completion_term(d, body_extents=[0.02, 0.02, 0.02],
                                       rigid_ext=[0.0, 0.0, 0.0]) == pytest.approx(0.005)
    assert pose_belief.completion_term(d) == 0.0


def test_pose_radius_formula_and_first_partial():
    d = det([0, 0, 0], [0.02, 0.02, 0.02], raw=[0.02, 0.012])
    r = pose_belief.pose_radius(d, yaw_noise=0.01)
    assert r == pytest.approx(0.004 + 0.01 * 0.01)
    assert pose_belief.pose_radius(d, 0.01, first_partial=True) == pytest.approx(r + 0.004)
    v = det([0, 0, 0], [0.03, 0.03, 0.02], yaw_valid=True, body=[0.02, 0.016, 0.02])
    assert pose_belief.pose_radius(v, 0.01) == pytest.approx(0.004 + 0.01 * 0.01)


def test_commit_margin_families():
    m = pose_belief.commit_margin([0.016, 0.016], 0.04, 0.076, 0.005)
    assert m == pytest.approx(0.004)                      # die: 0.5 * 8 mm
    m = pose_belief.commit_margin([0.070, 0.0701], 0.04, 0.076, 0.005)
    assert m == pytest.approx(0.04 - 0.03505 - 0.002)     # cup: m_pinch
    m = pose_belief.commit_margin([0.08, 0.03], 0.04, 0.076, 0.005)
    assert m == pytest.approx(0.02)                       # only the 0.03 pinch offered
    assert pose_belief.commit_margin([0.08, 0.079], 0.04, 0.076, 0.005) is None


def test_boxel_data_pose_defaults():
    from world.boxel_data import BoxelData
    b = BoxelData(id='x')
    assert b.pose_radius == math.inf and b.yaw == 0.0
    assert not b.yaw_valid and b.body_extents is None
    assert 'pose_radius' not in b.to_dict()
