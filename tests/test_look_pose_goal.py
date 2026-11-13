"""Path 9: the boxel look's pose look of a partly seen body.

Why (development run of 2026-11-13, seed 100, --look boxel, track/look
3d5b2f5, logs/run_2026-11-13_02-14-13): a look past the edge of the green
block saw 23 px of the target and registered it on that sliver (a box 5 mm
wide, 20 mm off the truth, pose radius 20 mm).  The plan twin then tested the
pose look on the believed box alone, which is the sliver that very view had
seen, so the configuration the arm stood in was certified as a clear view of
the target.  The real image from it was incomplete every time; nothing
withdrew the view, the same look ran three times, the target was parked and
the planner had no plan.

Two rules, both in look_views:
  A  an object's look goal is its believed box grown in x and y by its pose
     radius: the view must hold the body wherever the belief allows it;
  C  a view whose image did not give a body's pose no longer counts as
     revealing that body (LookViews.refute), until the body is re-posed
     (LookViews.forget): the counterpart of the centred look removing its own
     configuration.
"""
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import look_views  # noqa: E402
import robot_utils  # noqa: E402
from boxel_data import BoxelType  # noqa: E402
from streams import RobotConfig  # noqa: E402
from test_look_views import _boxel, _render, world  # noqa: E402,F401


def _sliver(radius):
    """A sliver of a body just outside what the fixture's occluder hides from
    the camera of _behind(): 5 mm wide, 20 mm tall."""
    b = _boxel('sliver', BoxelType.OBJECT, [0.19, 0.085, 0.0], [0.21, 0.090, 0.02],
               object_name='sliver')
    b.pose_radius = radius
    return b


def _behind(world):
    """A camera on the robot's side of the occluder, looking past its edge at
    the sliver: the table behind the occluder is hidden for |y| < 0.08 at
    x = 0.20."""
    return _render(world, (-0.20, 0.0, 0.30), (0.20, 0.05, 0.0))


# ----- A: the goal follows the belief ------------------------------------------

def test_an_objects_goal_is_its_box_grown_by_the_pose_radius():
    b = _sliver(0.02)
    g = look_views.object_goal(b)
    assert np.allclose(g.lo, [0.17, 0.065, 0.0]) and np.allclose(g.hi, [0.23, 0.110, 0.02])
    pts = g.slices[0]
    assert np.allclose(pts.min(axis=0), g.lo) and np.allclose(pts.max(axis=0), g.hi)
    assert np.allclose(b.min_corner, [0.19, 0.085, 0.0])        # the boxel is not touched


def test_a_radius_of_zero_leaves_the_box_and_a_large_or_unknown_one_is_capped():
    plain = look_views.object_goal(_sliver(0.0))
    assert np.allclose(plain.lo, [0.19, 0.085, 0.0]) and np.allclose(plain.hi, [0.21, 0.090, 0.02])
    cap = look_views.LOOK_OBJECT_GROW_MAX_M
    assert 0.0 < cap <= 0.05
    for r in (math.inf, 0.5, float('nan')):
        g = look_views.object_goal(_sliver(r))
        assert np.allclose(g.lo[:2], [0.19 - cap, 0.085 - cap]), r
        assert np.allclose(g.hi[:2], [0.21 + cap, 0.090 + cap]), r
        assert g.lo[2] == 0.0 and g.hi[2] == 0.02


def test_a_sliver_seen_past_a_block_is_not_a_clear_view_of_the_body(world):
    """Seed 100's case: the sliver itself is in view, the body it belongs to
    may reach behind the block."""
    movable, _ = world.lv._movable(world.reg)
    render = _behind(world)
    seen = look_views.object_goal(_sliver(0.0))
    st = world.lv._statuses([seen], render, movable, world.reg)['sliver']
    assert st.revealed and st.blockers == []                    # what the old rule certified
    body = look_views.object_goal(_sliver(0.02))
    st = world.lv._statuses([body], render, movable, world.reg)['sliver']
    assert st.revealed and st.blockers == ['occluder']          # the block is in front of it
    assert st.total_frac > look_views.LOOK_TOL_OBJECT


def test_stage_one_counts_a_block_that_touches_an_objects_goal(world):
    """Stage 1 skipped every box that overlaps the goal (right for a region,
    whose content is seen).  An object's goal has one content, the body
    itself: a block inside the grown box hides it."""
    b = _boxel('near', BoxelType.OBJECT, [0.155, -0.01, 0.0], [0.175, 0.01, 0.02],
               object_name='near')
    b.pose_radius = 0.02                                        # grown: reaches into the occluder
    goal = look_views.object_goal(b)
    _movable, boxes = world.lv._movable(world.reg)
    depth_m, seg, view, proj = _render(world, (-0.20, 0.0, 0.30), (0.165, 0.0, 0.0))
    cam = np.array([-0.20, 0.0, 0.30])
    hard, total = world.lv._probe(goal, cam, view, proj, boxes, True)
    assert hard == 0.0 and total > 0.0


# ----- C: a view that did not deliver is withdrawn -----------------------------

def _die_views(world, here):
    die = world.reg.get_boxel('die')
    facts, stats = world.lv.facts(world.reg, [], [die], here)
    return [f[1] for f in facts if f[0] == 'reveals' and f[2] == 'die'], stats


def _camera(world, q):
    world.views._set_arm(q.joint_positions)
    return robot_utils.wrist_camera_pose(world.robot, world.cid)


def _a_view_of_the_die(world):
    from test_look_views import _home
    views, _ = _die_views(world, _home())
    assert views, 'the fixture has a view of the die'
    return RobotConfig(joint_positions=np.array(views[0].joint_positions, dtype=float),
                       name='q_here')


def test_the_spot_the_arm_stands_in_is_a_view_until_its_image_fails(world):
    world.reg.get_boxel('die').pose_radius = 0.005
    here = _a_view_of_the_die(world)
    views, stats = _die_views(world, here)
    assert any(q is here for q in views)
    assert stats['refuted'] == 0

    world.lv.refute('die', here.joint_positions)
    views, stats = _die_views(world, here)
    assert not any(q is here for q in views)                    # the same look is not planned again
    assert stats['refuted'] >= 1
    cam_here = _camera(world, here)
    for q in views:                                             # what is left is another view
        cam = _camera(world, q)
        far = float(np.linalg.norm(cam[:3, 3] - cam_here[:3, 3])) > look_views.LOOK_SAME_VIEW_M
        turned = float(cam[:3, 2] @ cam_here[:3, 2]) < math.cos(look_views.LOOK_SAME_VIEW_RAD)
        assert far or turned


def test_a_refuted_view_still_reveals_other_goals(world):
    world.reg.get_boxel('die').pose_radius = 0.005
    here = _a_view_of_the_die(world)
    world.lv.refute('other_body', here.joint_positions)
    views, stats = _die_views(world, here)
    assert any(q is here for q in views) and stats['refuted'] == 0


def test_forgetting_a_body_gives_its_views_back(world):
    world.reg.get_boxel('die').pose_radius = 0.005
    here = _a_view_of_the_die(world)
    world.lv.refute('die', here.joint_positions)
    assert not any(q is here for q in _die_views(world, here)[0])
    world.lv.forget('die')
    assert any(q is here for q in _die_views(world, here)[0])
    world.lv.forget('die')                                      # nothing to forget is no error


def test_a_refuted_view_is_never_a_stage_two_result(world):
    """A candidate pose that falls on a refuted view is rejected in stage 2
    like one whose render does not show the goal."""
    world.reg.get_boxel('die').pose_radius = 0.005
    from test_look_views import _home
    views, _ = _die_views(world, _home())
    for q in views:
        world.lv.refute('die', q.joint_positions)
    again, stats = _die_views(world, _home())
    cams = [_camera(world, q) for q in views]
    for q in again:
        cam = _camera(world, q)
        for old in cams:
            far = float(np.linalg.norm(cam[:3, 3] - old[:3, 3])) > look_views.LOOK_SAME_VIEW_M
            turned = float(cam[:3, 2] @ old[:3, 2]) < math.cos(look_views.LOOK_SAME_VIEW_RAD)
            assert far or turned
    assert stats['refuted'] >= 1
