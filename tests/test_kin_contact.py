"""BF#45: compute-kin certifies an approach configuration only when the
contact pose the executor lowers to from it has an IK solution as well.
A DIRECT world with pybullet_data's Panda on the ground plane, as
tests/test_m8_observe.py builds it; the geometry of the find_dice case
(the table top at the base's height, a cup 69.6 mm wide and 70.3 mm tall,
a free cell 0.72 m out whose approach 10 cm above the cell's centre has IK
and whose contact 5 mm below the cup's top has none)."""
import numpy as np
import pybullet as p
import pybullet_data
import pytest

import robot_utils
import streams
from boxel_data import BoxelData, BoxelRegistry, BoxelType

BASE = (-0.4, 0.0)
CUP = (0.0696, 0.0703)                     # footprint side, height (seed 10's d_cups_ud)
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


def _cup(x, y):
    lo = np.array([x - CUP[0] / 2, y - CUP[0] / 2, 0.0])
    return BoxelData(id='cup', boxel_type=BoxelType.OBJECT, min_corner=lo,
                     max_corner=lo + np.array([CUP[0], CUP[0], CUP[1]]),
                     on_surface='table', surface_z=0.0)


def _cell(name, x, y, top=0.25):
    lo = np.array([x - 0.03, y - 0.03, 0.0])
    return BoxelData(id=name, boxel_type=BoxelType.FREE_SPACE, min_corner=lo,
                     max_corner=lo + np.array([0.06, 0.06, top]),
                     on_surface='table', surface_z=0.0)


def _streams(cid, robot, boxels):
    reg = BoxelRegistry()
    for b in boxels:
        reg.add_boxel(b)
    return streams.BoxelStreams(reg, robot_id=robot, physics_client=cid,
                                object_body_ids={}, support_body_ids=frozenset())


def _grasp():
    return streams.Grasp(position=np.array([0.0, 0.0, 0.10]), orientation=TOP_DOWN,
                         name='g')


def test_contact_target_is_the_executors_rule(world):
    cid, robot = world
    cup = _cup(BASE[0] + 0.45, 0.0)
    cell = _cell('free_near', BASE[0] + 0.45, -0.2)
    s = _streams(cid, robot, [cup, cell])
    g = _grasp()
    # A pick: the cup's own top minus 5 mm (above the 35 mm floor).
    pick = s.contact_target('cup', cup, g)
    assert pick[2] == pytest.approx(CUP[1] - 0.005)
    assert pick[:2] == pytest.approx(cup.center[:2])
    # A place: the same height at the destination cell.
    place = s.contact_target('cup', cell, g)
    assert place[2] == pytest.approx(CUP[1] - 0.005)
    assert place[:2] == pytest.approx(cell.center[:2])
    # A pick out of a region of a target without a box: the floor.
    s.contact_floor = 0.0132
    region = _cell('shadow_of_x', BASE[0] + 0.45, 0.2, top=0.07)
    assert s.contact_target('dice', region, g)[2] == pytest.approx(
        max(streams.NOMINAL_HIDDEN_EXTENTS[2] - 0.005, 0.0132))


def _reach_split(cid, robot, s, g):
    """A cell where the approach has IK and the contact has none, scanning
    outward along the find_dice bearing, or None."""
    for r in np.arange(0.55, 0.81, 0.01):
        cell = _cell('probe', BASE[0] + r, -0.2025)
        approach = cell.center + g.position
        if not s.ee_reachable(approach):
            continue
        q = robot_utils.solve_ik(robot, approach, g.orientation, cid)
        if q is None:
            continue
        contact = s.contact_target('cup', cell, g)
        if robot_utils.solve_ik(robot, contact, g.orientation, cid, seed=q) is None:
            return cell
    return None


def test_compute_kin_certifies_only_reachable_contacts(world):
    cid, robot = world
    cup = _cup(BASE[0] + 0.45, 0.0)
    near = _cell('free_near', BASE[0] + 0.45, -0.2)
    s = _streams(cid, robot, [cup, near])
    g = _grasp()
    # Near the base the cell is certified, and every certified config has
    # a reachable contact (an IK branch whose contact has none is turned
    # away even here: it counts, it is not yielded).
    configs = [c for (c,) in s.compute_kin_solution('cup', 'free_near', g)]
    assert configs, 'no approach configuration over the near cell'
    contact = s.contact_target('cup', near, g)
    for c in configs:
        assert robot_utils.solve_ik(robot, contact, g.orientation, cid,
                                    seed=c.joint_positions) is not None
    # At the reach edge the approach alone certified every IK branch; now
    # the branch whose contact has no IK (the rest-seeded one, by the
    # cell's construction) is counted and not yielded, and whatever is
    # yielded lowers to a reachable contact.
    far = _reach_split(cid, robot, s, g)
    if far is None:
        pytest.skip('no cell with a reachable approach and an unreachable contact')
    s.registry.add_boxel(far)
    before = s.contact_ik_rejects
    far_configs = [c for (c,) in s.compute_kin_solution('cup', far.id, g)]
    contact = s.contact_target('cup', far, g)
    for c in far_configs:
        assert robot_utils.solve_ik(robot, contact, g.orientation, cid,
                                    seed=c.joint_positions) is not None
    assert s.contact_ik_rejects > before
