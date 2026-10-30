"""BF#52: the fixed eye senses from any configuration that keeps the arm out
of its view of the region.  The stream delta (test-sense-view in the
generated M8 stream file), ObserveViews.sense_view_test on a DIRECT world
with pybullet_data's Panda (the eye straight above a region: the arm at rest
is out of the view, a hand parked over the region is in it), and
BoxelStreams.test_sense_view's gate on the tester and the region."""
from types import SimpleNamespace

import numpy as np
import pybullet as p
import pybullet_data
import pytest

import m8_domain
import observe_views
import robot_utils
import streams
from boxel_data import BoxelData, BoxelRegistry, BoxelType

BASE = (-0.4, 0.0)
REGION = (0.20, 0.0)                      # the shadow's centre on the table, 0.6 m out


def test_generated_stream_is_the_live_file_plus_the_test_stream():
    live = m8_domain.read(m8_domain.STREAM_LIVE_FILE)
    gen = m8_domain.generate_stream(live)
    assert '(:stream test-sense-view' in gen and '(:stream test-sense-view' not in live
    assert gen.startswith(m8_domain.STREAM_HEADER)
    # only over the region itself: the target's pick configurations there
    assert '(config_for_boxel ?q ?region)' in gen.split('(:stream test-sense-view')[1]
    for name in ('sample-grasp', 'plan-motion', 'compute-kin', 'compute-stack-kin'):
        assert f'(:stream {name}' in gen
    assert m8_domain.stream_file(False) == m8_domain.STREAM_LIVE_FILE
    assert m8_domain.read(m8_domain.stream_file(True)) == gen
    with pytest.raises(ValueError):
        m8_domain.generate_stream(gen)          # the delta applies once


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


def test_the_stream_gate_needs_the_tester_and_a_shadow_region(world):
    env = _env(world.cid, world.robot, world.plane, eye=(REGION[0], REGION[1], 1.4))
    reg = BoxelRegistry()
    reg.add_boxel(_shadow())
    reg.add_boxel(BoxelData(id='free_0', boxel_type=BoxelType.FREE_SPACE,
                            min_corner=np.array([0.1, 0.2, 0.0]),
                            max_corner=np.array([0.2, 0.3, 0.05])))
    st = streams.BoxelStreams(reg, robot_id=world.robot, physics_client=world.cid)
    assert st.test_sense_view(_rest(), 'shadow_of_x') is False      # M8 off: no tester
    st.sense_view_test = observe_views.ObserveViews(env, BASE).sense_view_test
    assert st.test_sense_view(_rest(), 'shadow_of_x') is True
    assert st.test_sense_view(_rest(), 'free_0') is False            # not a shadow
    assert st.test_sense_view(_rest(), 'nowhere') is False
    assert (st.sense_view_tests, st.sense_view_passes) == (1, 1)
