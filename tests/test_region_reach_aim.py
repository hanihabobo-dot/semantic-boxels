"""BF#65 2(c): a pick out of a region whose centre the arm cannot reach aims
at the region's reachable part; where the centre is reachable nothing
changes, and place destinations and known objects are never re-aimed.
A DIRECT world with pybullet_data's Panda on the ground plane, as
tests/test_kin_contact.py builds it."""
import numpy as np
import pybullet as p
import pybullet_data
import pytest

import robot_utils
import streams
from boxel_data import BoxelData, BoxelRegistry, BoxelType

BASE = (-0.4, 0.0)
TOP_DOWN = np.array(p.getQuaternionFromEuler([0, np.pi, 0]))


@pytest.fixture
def world():
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
    p.loadURDF('plane.urdf', physicsClientId=cid)
    robot = p.loadURDF('franka_panda/panda.urdf', [BASE[0], BASE[1], 0.0],
                       useFixedBase=True, physicsClientId=cid)
    yield cid, robot
    p.disconnect(cid)


def _box(name, kind, x_lo, x_hi, y_lo=-0.06, y_hi=0.06, top=0.07):
    return BoxelData(id=name, boxel_type=kind,
                     min_corner=np.array([x_lo, y_lo, 0.0]),
                     max_corner=np.array([x_hi, y_hi, top]),
                     on_surface='table', surface_z=0.0)


def _streams(cid, robot, boxels):
    reg = BoxelRegistry()
    for b in boxels:
        reg.add_boxel(b)
    return streams.BoxelStreams(reg, robot_id=robot, physics_client=cid,
                                object_body_ids={}, support_body_ids=frozenset())


def _grasp(z=0.10):
    return streams.Grasp(position=np.array([0.0, 0.0, z]), orientation=TOP_DOWN,
                         name='g')


def _limit_x(s, g, top=0.07):
    """The largest x on the base's bearing (y = 0) that ee_reachable admits
    at the height a pick out of a ``top`` tall region aims at."""
    z = top / 2.0 + float(g.position[2])
    xs = np.arange(BASE[0] + 0.40, BASE[0] + 0.95, 0.001)
    ok = [x for x in xs if s.ee_reachable(np.array([x, 0.0, z]))]
    return max(ok)


def test_no_aim_for_a_reachable_centre_and_the_kin_is_the_old_one(world):
    """Where the centre is reachable the stream never asks for an aim: the
    target is the centre plus the grasp offset, as before."""
    cid, robot = world
    region = _box('shadow_of_x', BoxelType.SHADOW, BASE[0] + 0.40, BASE[0] + 0.55)
    s = _streams(cid, robot, [region])
    g = _grasp()
    assert s.ee_reachable(region.center + g.position)
    calls = []
    real = s.region_reach_aim
    s.region_reach_aim = lambda *a, **k: calls.append(a) or real(*a, **k)
    configs = [c for (c,) in s.compute_kin_solution('dice', 'shadow_of_x', g)]
    assert configs, 'no kin over a region near the base'
    assert calls == [] and s.region_aim_shifts == 0
    # Every certified config's end effector stands over the centre.
    for c in configs:
        for j, v in zip(robot_utils.robot_model().arm_joints, c.joint_positions):
            p.resetJointState(robot, j, float(v), physicsClientId=cid)
        ee = p.getLinkState(robot, robot_utils.robot_model().ee_link,
                            computeForwardKinematics=True, physicsClientId=cid)[4]
        assert np.allclose(ee[:2], region.center[:2], atol=5e-3)
    # The contact rule without an aim is the centre's, as before.
    assert s.contact_target('dice', region, g)[:2] == pytest.approx(region.center[:2])


def test_a_region_straddling_the_limit_binds_at_its_reachable_part(world):
    cid, robot = world
    s = _streams(cid, robot, [])
    g = _grasp()
    limit = _limit_x(s, g)
    # 6 cm of the region inside the limit, 14 cm outside: the centre is out.
    region = _box('shadow_of_far', BoxelType.SHADOW, limit - 0.06, limit + 0.14)
    s.registry.add_boxel(region)
    assert not s.ee_reachable(region.center + g.position)
    aim = s.region_reach_aim('dice', region, g)
    assert aim is not None
    # Inside the region's footprint, and in reach at the pick's height.
    assert region.min_corner[0] <= aim[0] <= region.max_corner[0]
    assert region.min_corner[1] <= aim[1] <= region.max_corner[1]
    assert s.ee_reachable(np.array([aim[0], aim[1], region.center[2] + g.position[2]]))
    # Not on the limit itself: the centroid of the reachable part.
    assert aim[0] < limit - 0.005
    configs = [c for (c,) in s.compute_kin_solution('dice', 'shadow_of_far', g)]
    assert s.region_aim_shifts == 1
    if not configs:
        pytest.skip('the aim is in the envelope but this Panda has no IK there')
    # The contact check ran at the aim, not at the centre.
    contact = s.contact_target('dice', region, g, aim_xy=aim)
    assert contact[:2] == pytest.approx(aim)
    for c in configs:
        assert robot_utils.solve_ik(robot, contact, g.orientation, cid,
                                    seed=c.joint_positions) is not None


def test_a_region_wholly_out_of_reach_has_no_kin(world):
    cid, robot = world
    s = _streams(cid, robot, [])
    g = _grasp()
    limit = _limit_x(s, g)
    region = _box('shadow_of_gone', BoxelType.SHADOW, limit + 0.05, limit + 0.25)
    s.registry.add_boxel(region)
    assert s.region_reach_aim('dice', region, g) is None
    assert list(s.compute_kin_solution('dice', 'shadow_of_gone', g)) == []
    assert s.region_aim_shifts == 0


def test_places_and_known_objects_are_never_re_aimed(world):
    """A free cell or an object's own boxel with an unreachable centre stays
    refused, whatever part of it is in reach."""
    cid, robot = world
    s = _streams(cid, robot, [])
    g = _grasp()
    limit = _limit_x(s, g)
    cell = _box('free_far', BoxelType.FREE_SPACE, limit - 0.06, limit + 0.14)
    cup = _box('cup', BoxelType.OBJECT, limit - 0.06, limit + 0.14)
    s.registry.add_boxel(cell)
    s.registry.add_boxel(cup)
    for b in (cell, cup):
        assert not s.ee_reachable(b.center + g.position)
        assert s.region_reach_aim('cup', b, g) is None
        assert list(s.compute_kin_solution('cup', b.id, g)) == []
    assert s.region_aim_shifts == 0


def test_the_aim_keeps_the_object_inside_a_wide_region(world):
    """The lattice is inset by half the object's footprint: the hypothesised
    object at the aim lies inside the region."""
    cid, robot = world
    s = _streams(cid, robot, [])
    g = _grasp()
    limit = _limit_x(s, g)
    region = _box('shadow_wide', BoxelType.SHADOW, limit - 0.03, limit + 0.20,
                  y_lo=-0.10, y_hi=0.10)
    s.registry.add_boxel(region)
    aim = s.region_reach_aim('dice', region, g)
    assert aim is not None
    half = streams.NOMINAL_HIDDEN_EXTENTS[0] / 2.0
    assert aim[0] >= region.min_corner[0] + half - 1e-9
    assert abs(aim[1]) <= 0.10 - half + 1e-9
