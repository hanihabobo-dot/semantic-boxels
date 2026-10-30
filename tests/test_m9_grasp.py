"""PLAN_P4_POSE_GRASP_SAMPLERS.md step 3: M9's object-fitted grasp."""
import math
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pytest

import pose_belief
import robot_utils
import streams
from boxel_data import BoxelData, BoxelType


@pytest.fixture
def m9_on():
    saved = dict(pose_belief.SWITCHES)
    pose_belief.SWITCHES['M9'] = True
    yield
    pose_belief.SWITCHES.clear()
    pose_belief.SWITCHES.update(saved)


def test_fitted_candidates_rectangle_and_square():
    c = pose_belief.fitted_grasp_candidates(0.3, [0.04, 0.02, 0.02], 0.005)
    assert c[0] == pytest.approx((0.3, 0.02))
    assert c[1][0] == pytest.approx(0.3 + math.pi / 2 - math.pi)
    assert c[1][1] == pytest.approx(0.04)
    assert pose_belief.fitted_grasp_candidates(1.0, [0.0176, 0.0173, 0.0178], 0.005) == \
        [pytest.approx((1.0 - math.pi / 2, 0.0176))]


@pytest.mark.parametrize('yaw', [0.0, 0.3, -0.7, 1.2])
def test_pinch_direction_matches_pinch_axis_and_the_sampler(yaw):
    q = p.getQuaternionFromEuler([0, math.pi, yaw])
    d = robot_utils.pinch_direction(q)
    assert np.allclose(d, [-math.sin(yaw), math.cos(yaw)], atol=1e-9)
    assert robot_utils.pinch_axis(q) == (0 if abs(d[0]) > abs(d[1]) else 1)


def test_pinch_half_extent_at_and_off_the_object_yaw():
    ext = [0.04, 0.02, 0.02]
    for grasp_yaw, span in pose_belief.fitted_grasp_candidates(0.3, ext, 0.005):
        d = robot_utils.pinch_direction(p.getQuaternionFromEuler([0, math.pi, grasp_yaw]))
        assert pose_belief.pinch_half_extent(d, 0.3, ext) == pytest.approx(span / 2)
    # A die yawed 8 deg pinched at yaw 0: the pads meet its corners.
    d = robot_utils.pinch_direction(p.getQuaternionFromEuler([0, math.pi, 0.0]))
    w = pose_belief.pinch_half_extent(d, math.radians(8), [0.0176, 0.0176, 0.0176])
    assert w == pytest.approx(0.0088 * (math.cos(math.radians(8)) + math.sin(math.radians(8))))


def sampler(boxel):
    reg = SimpleNamespace(get_boxel=lambda i: boxel)
    s = SimpleNamespace(ungraspable_objects=set(), registry=reg, _grasp_counter=0,
                        GRASP_MAX_SPAN=streams.BoxelStreams.GRASP_MAX_SPAN,
                        GRASP_SQUARE_TOL=streams.BoxelStreams.GRASP_SQUARE_TOL,
                        _GRASP_Z_OFFSETS=list(streams.BoxelStreams._GRASP_Z_OFFSETS))
    out = []
    for (g,) in streams.BoxelStreams.sample_grasp(s, 'o'):
        d = robot_utils.pinch_direction(g.orientation)
        out.append((round(math.atan2(-d[0], d[1]), 6), float(g.position[2])))
    return out


def boxel(yaw_valid):
    b = BoxelData(id='o', boxel_type=BoxelType.OBJECT,
                  min_corner=np.array([0.0, 0.0, 0.0]),
                  max_corner=np.array([0.044, 0.035, 0.02]))
    b.yaw, b.yaw_valid = 0.4, yaw_valid
    b.body_extents = np.array([0.04, 0.02, 0.02])
    return b


def test_sample_grasp_off_is_the_aabb_sampler():
    got = sampler(boxel(True))
    assert [y for y, _ in got] == [pytest.approx(0.0)] * 2 + [pytest.approx(math.pi / 2)] * 2


def test_sample_grasp_m9_uses_the_fitted_yaw(m9_on):
    got = sampler(boxel(True))
    assert [y for y, _ in got] == [pytest.approx(0.4)] * 2 + \
        [pytest.approx(0.4 + math.pi / 2 - math.pi)] * 2


def test_sample_grasp_m9_without_a_valid_yaw_falls_back(m9_on):
    pose_belief.SWITCHES['M9'] = False
    off = sampler(boxel(False))
    pose_belief.SWITCHES['M9'] = True
    assert sampler(boxel(False)) == off


def test_q_h_a_sizes_the_pinch_on_the_wider_of_fitted_and_aabb():
    # Q-H (a): an upturned cup's top face (52.8 mm) is narrower than its
    # body (71.8 mm AABB); the pinch is sized on the body.
    top, aabb = np.array([0.0528, 0.0528, 0.1]), np.array([0.0718, 0.0718, 0.1])
    d = pose_belief.pad_direction(0.0)
    assert pose_belief.sized_pinch_half(d, 0.0, top, aabb) == pytest.approx(0.0359)
    assert pose_belief.fitted_grasp_candidates(0.0, top, 0.005, aabb) == \
        [(pytest.approx(0.0), pytest.approx(0.0718))]
    # A prism at yaw 0: the two agree, nothing changes.
    die = np.array([0.0176, 0.0176, 0.0178])
    assert pose_belief.sized_pinch_half(d, 0.0, die, die) == pytest.approx(0.0088)
    assert pose_belief.fitted_grasp_candidates(0.0, die, 0.005, die) == \
        pose_belief.fitted_grasp_candidates(0.0, die, 0.005)
    # The pad direction is the hand's y axis of the sampler's orientation.
    orn = p.getQuaternionFromEuler([0, math.pi, 0.7])
    assert abs(float(robot_utils.pinch_direction(orn) @ pose_belief.pad_direction(0.7))) \
        == pytest.approx(1.0)


def test_q_h_a_margin_uses_the_sized_span(m9_on):
    b = BoxelData(id='c', boxel_type=BoxelType.OBJECT, min_corner=np.zeros(3),
                  max_corner=np.array([0.0718, 0.0718, 0.1]))
    b.yaw, b.yaw_valid = 0.0, True
    b.body_extents = np.array([0.0528, 0.0528, 0.1])
    m = pose_belief.believed_margin(b, 0.04, 0.076, 0.005)
    assert m == pytest.approx(0.04 - 0.0359 - 0.002)

def test_aabb_sizing_uses_the_nearest_axis_side_not_the_projection(m9_on):
    # BF#46: a cup is a square 69.6 mm box with an arbitrary fitted yaw (a
    # round footprint); the support projection read 85 mm at 0.3 rad and
    # the cup lost every grasp family.  The side along the nearest axis
    # is its width along the pads whatever the yaw.
    aabb = np.array([0.0696, 0.0696, 0.0703])
    body = np.array([0.0696, 0.0696, 0.0703])
    for gy in (0.0, 0.3, -0.7, 1.2):
        d = robot_utils.pinch_direction(p.getQuaternionFromEuler([0, math.pi, gy]))
        assert pose_belief.aabb_half_along(d, aabb) == pytest.approx(0.0348)
    cands = pose_belief.fitted_grasp_candidates(0.3, body, 0.005, aabb)
    assert [span for _, span in cands] == [pytest.approx(0.0696)]
    b = BoxelData(id='cup', boxel_type=BoxelType.OBJECT,
                  min_corner=np.zeros(3), max_corner=aabb.copy())
    b.yaw, b.yaw_valid, b.body_extents = 0.3, True, body
    assert pose_belief.believed_margin(b, 0.04, 0.076, 0.005) is not None
    # A rectangle pinched along its own axes keeps its sides (the axis
    # nearest the pads is the one the fitted yaw aligns them with).
    rect = np.array([0.04, 0.02, 0.02])
    d = robot_utils.pinch_direction(p.getQuaternionFromEuler([0, math.pi, 0.0]))
    assert pose_belief.aabb_half_along(d, rect) == pytest.approx(0.01)
    d = robot_utils.pinch_direction(p.getQuaternionFromEuler([0, math.pi, math.pi / 2]))
    assert pose_belief.aabb_half_along(d, rect) == pytest.approx(0.02)
