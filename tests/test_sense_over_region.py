"""BF#52, the fold.  ObserveViews.sense_view_test (the executor's render
rule on any configuration) on a DIRECT world with pybullet_data's Panda:
the arm at rest is out of a top-down eye's view of a region, a hand parked
over the region is in it, the arm is put back, the render is cached per
configuration.  pddlstream_planner.over_region_facts: the static facts for
a (target, region) pair, the streams' own grasp and configuration, offered
only when the view test passes."""
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pybullet_data
import pytest

import observe_views
import pddlstream_planner
import robot_utils
import streams
from boxel_data import BoxelData, BoxelRegistry, BoxelType

BASE = (-0.4, 0.0)
REGION = (0.20, 0.0)                      # the shadow's centre on the table, 0.6 m out


def _env(cid, robot, plane, eye):
    view = p.computeViewMatrix(list(eye), [REGION[0], REGION[1], 0.0], [1.0, 0.0, 0.0])
    proj = p.computeProjectionMatrixFOV(50.0, 160.0 / 120.0, 0.05, 4.0)
    objs = {'plane': SimpleNamespace(object_id=plane),
            'robot': SimpleNamespace(object_id=robot)}
    return SimpleNamespace(client_id=cid, plan_client_id=cid, plan_robot_id=robot,
                           objects=objs, _gui_to_plan={plane: plane, robot: robot},
                           table_surface_height=0.0, image_width=160, image_height=120,
                           near_plane=0.05, far_plane=4.0,
                           _view_and_projection_matrices=lambda: (view, proj))


@pytest.fixture
def world():
    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath(), physicsClientId=cid)
    plane = p.loadURDF('plane.urdf', physicsClientId=cid)
    robot = p.loadURDF('franka_panda/panda.urdf', [BASE[0], BASE[1], 0.0],
                       useFixedBase=True, physicsClientId=cid)
    for j, v in zip(robot_utils.robot_model().arm_joints, robot_utils.REST_POSES):
        p.resetJointState(robot, j, v, physicsClientId=cid)
    yield SimpleNamespace(cid=cid, robot=robot, plane=plane)
    p.disconnect(cid)


def _shadow():
    lo = np.array([REGION[0] - 0.05, REGION[1] - 0.05, 0.0])
    return BoxelData(id='shadow_of_x', boxel_type=BoxelType.SHADOW, min_corner=lo,
                     max_corner=lo + np.array([0.10, 0.10, 0.06]))


def _rest():
    return streams.RobotConfig(joint_positions=np.array(robot_utils.REST_POSES, dtype=float),
                               name='q_rest')


def _hand_over_region(cid, robot):
    q = robot_utils.solve_ik(robot, np.array([REGION[0], REGION[1], 0.20]),
                             physics_client=cid)
    assert q is not None, 'IK over the region'
    return streams.RobotConfig(joint_positions=np.asarray(q, dtype=float), name='q_over')


def test_the_arm_at_rest_is_out_of_the_view_and_a_hand_over_the_region_is_in_it(world):
    env = _env(world.cid, world.robot, world.plane, eye=(REGION[0], REGION[1], 1.4))
    views = observe_views.ObserveViews(env, BASE)
    shadow = _shadow()
    saved = views._arm()
    assert views.sense_view_test(_rest(), shadow) is True
    assert views.sense_view_test(_hand_over_region(world.cid, world.robot), shadow) is False
    assert views._arm() == pytest.approx(saved)          # the arm is put back
    assert (views.test_stats['tests'], views.test_stats['passes']) == (2, 1)
    assert views.test_stats['renders'] == 2
    assert views.sense_view_test(_rest(), shadow) is True   # cached: no new render
    assert views.test_stats['renders'] == 2


def test_over_region_facts_follow_the_view_test(world):
    env = _env(world.cid, world.robot, world.plane, eye=(REGION[0], REGION[1], 1.4))
    views = observe_views.ObserveViews(env, BASE)
    reg = BoxelRegistry()
    reg.add_boxel(_shadow())
    shadow = reg.get_boxel('shadow_of_x')
    st = streams.BoxelStreams(reg, robot_id=world.robot, physics_client=world.cid)
    # The real rule: the hand over the region is in a top-down eye's view,
    # so nothing is offered (one render spent).
    facts, stats = pddlstream_planner.over_region_facts(
        st, views, ['dice'], [shadow], lambda t, r: True)
    assert facts == []
    assert (stats['over_region_pairs'], stats['over_region_pass'],
            stats['over_region_renders']) == (1, 0, 1)
    # A clear view: the six facts, with the streams' own grasp and
    # configuration (what compute-kin would yield first for the pick).
    views.sense_view_test = lambda q, r: True
    facts, stats = pddlstream_planner.over_region_facts(
        st, views, ['dice'], [shadow], lambda t, r: True)
    assert [f[0] for f in facts] == ['Grasp', 'valid_grasp', 'Config', 'kin_solution',
                                     'config_for_boxel', 'sense_view']
    g, q = facts[0][1], facts[2][1]
    assert isinstance(g, streams.Grasp) and isinstance(q, streams.RobotConfig)
    assert facts[1] == ('valid_grasp', 'dice', g)
    assert facts[3] == ('kin_solution', 'dice', 'shadow_of_x', g, q)
    assert facts[4] == ('config_for_boxel', q, 'shadow_of_x')
    assert facts[5] == ('sense_view', q, 'shadow_of_x')
    assert q.name.startswith('q_kin_dice_')
    assert (stats['over_region_pairs'], stats['over_region_pass']) == (1, 1)
    # A pair the sense cannot ground on is not a candidate.
    facts, stats = pddlstream_planner.over_region_facts(
        st, views, ['dice'], [shadow], lambda t, r: False)
    assert facts == [] and stats['over_region_pairs'] == 0
